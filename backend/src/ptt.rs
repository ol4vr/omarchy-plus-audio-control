//! Discord PTT is the authoritative owner of microphone capture on Hugin.
//!
//! The PTT helper and this backend serialize state transitions through one
//! private lock. Input mutations retain the lock until PipeWire confirms the
//! change, so PTT cannot be enabled between admission and dispatch.
use crate::files::FileLock;
use crate::protocol::{Failure, Request, Result};
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

const CONTRACT: &[u8] = b"shared-lock-v1\n";
const MAX_MARKER_BYTES: u64 = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Disabled,
    Enabled,
}

pub struct AuthorityGuard {
    _lock: FileLock,
    state: State,
}

#[derive(Clone)]
struct Paths {
    lock: PathBuf,
    state: PathBuf,
}

impl Paths {
    fn from_environment() -> Result<Self> {
        let runtime = std::env::var_os("XDG_RUNTIME_DIR")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .ok_or_else(unavailable)?;
        let state_home = std::env::var_os("XDG_STATE_HOME")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("HOME")
                    .filter(|value| !value.is_empty())
                    .map(|home| PathBuf::from(home).join(".local/state"))
            })
            .ok_or_else(unavailable)?;
        if !runtime.is_absolute() || !state_home.is_absolute() {
            return Err(unavailable());
        }
        Ok(Self {
            lock: runtime
                .join("omarchy-plus-discord-ptt")
                .join("authority.lock"),
            state: state_home.join("omarchy-plus/discord-ptt"),
        })
    }
}

fn unavailable() -> Failure {
    Failure::new(
        "ptt_unavailable",
        "Discord PTT ownership cannot be verified; microphone controls are disabled",
    )
}

fn validate_private_directory(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path).map_err(|_| unavailable())?;
    // SAFETY: geteuid has no preconditions.
    let uid = unsafe { libc::geteuid() };
    if !path.is_absolute()
        || !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != uid
        || metadata.mode() & 0o077 != 0
    {
        return Err(unavailable());
    }
    Ok(())
}

fn read_marker(path: &Path) -> Result<Option<Vec<u8>>> {
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
        .open(path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(None);
        }
        Err(_) => return Err(unavailable()),
    };
    let metadata = file.metadata().map_err(|_| unavailable())?;
    // SAFETY: geteuid has no preconditions.
    let uid = unsafe { libc::geteuid() };
    let linked = fs::symlink_metadata(path).map_err(|_| unavailable())?;
    if !metadata.is_file()
        || metadata.uid() != uid
        || metadata.nlink() != 1
        || metadata.mode() & 0o077 != 0
        || metadata.len() > MAX_MARKER_BYTES
        || linked.file_type().is_symlink()
        || linked.ino() != metadata.ino()
        || linked.dev() != metadata.dev()
    {
        return Err(unavailable());
    }
    let mut value = Vec::new();
    file.take(MAX_MARKER_BYTES + 1)
        .read_to_end(&mut value)
        .map_err(|_| unavailable())?;
    if value.len() as u64 > MAX_MARKER_BYTES {
        return Err(unavailable());
    }
    Ok(Some(value))
}

fn acquire(paths: &Paths) -> Result<AuthorityGuard> {
    let authority_dir = paths.lock.parent().ok_or_else(unavailable)?;
    validate_private_directory(authority_dir)?;
    validate_private_directory(&paths.state)?;
    let lock = FileLock::acquire(&paths.lock).map_err(|error| {
        if error.code == "busy" {
            Failure::new(
                "ptt_busy",
                "Discord PTT is changing state; microphone controls are disabled",
            )
        } else {
            unavailable()
        }
    })?;
    // State is read only after acquiring the lock. The PTT helper holds this
    // same lock across marker changes and wpctl mute transitions.
    validate_private_directory(&paths.state)?;
    if read_marker(&paths.state.join("authority-v1"))?.as_deref() != Some(CONTRACT) {
        return Err(unavailable());
    }
    let enabled = match read_marker(&paths.state.join("enabled"))? {
        Some(value) if value.is_empty() => true,
        Some(_) => return Err(unavailable()),
        None => false,
    };
    Ok(AuthorityGuard {
        _lock: lock,
        state: if enabled {
            State::Enabled
        } else {
            State::Disabled
        },
    })
}

pub async fn status() -> Result<AuthorityGuard> {
    let paths = Paths::from_environment()?;
    tokio::task::spawn_blocking(move || acquire(&paths))
        .await
        .map_err(|_| unavailable())?
}

pub async fn require_input_mutation() -> Result<AuthorityGuard> {
    let guard = status().await?;
    if guard.state == State::Enabled {
        return Err(Failure::new(
            "ptt_owned",
            "Discord PTT is enabled; microphone controls are disabled",
        ));
    }
    Ok(guard)
}

impl AuthorityGuard {
    pub fn state(&self) -> State {
        self.state
    }
}

pub fn input_node(class: &str) -> bool {
    matches!(
        class,
        "Audio/Source" | "Audio/Source/Virtual" | "Stream/Input/Audio"
    )
}

pub fn policy_requires_authority(key: &str) -> bool {
    matches!(
        key,
        "device.routes.default-source-volume"
            | "node.stream.default-capture-volume"
            | "bluetooth.autoswitch-to-headset-profile"
            | "bluetooth.profile-preference"
    )
}

pub fn store_requires_authority(request: &Request) -> bool {
    match request.method.as_str() {
        "preferences.profile" => true,
        "devices.forget" => true,
        "preferences.default" => request.params["direction"] != "output",
        "rules.set_app" | "rules.delete_app" => request.params["direction"] != "playback",
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};
    use std::os::unix::fs::{PermissionsExt, symlink};

    fn fixture() -> (tempfile::TempDir, Paths) {
        let directory = tempfile::tempdir().unwrap();
        let authority = directory.path().join("run/omarchy-plus-discord-ptt");
        let state = directory.path().join("state/omarchy-plus/discord-ptt");
        fs::create_dir_all(&authority).unwrap();
        fs::create_dir_all(&state).unwrap();
        fs::set_permissions(&authority, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&state, fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(state.join("authority-v1"), CONTRACT).unwrap();
        fs::set_permissions(
            state.join("authority-v1"),
            fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        (
            directory,
            Paths {
                lock: authority.join("authority.lock"),
                state,
            },
        )
    }

    #[test]
    fn authoritative_state_is_fail_closed_and_lock_backed() {
        let (_directory, paths) = fixture();
        assert_eq!(acquire(&paths).unwrap().state(), State::Disabled);
        fs::write(paths.state.join("enabled"), b"").unwrap();
        fs::set_permissions(
            paths.state.join("enabled"),
            fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        assert_eq!(acquire(&paths).unwrap().state(), State::Enabled);
        fs::write(paths.state.join("authority-v1"), b"legacy\n").unwrap();
        assert_eq!(acquire(&paths).err().unwrap().code, "ptt_unavailable");
    }

    #[test]
    fn unsafe_or_ambiguous_authority_state_is_rejected() {
        let (directory, paths) = fixture();
        fs::set_permissions(&paths.state, fs::Permissions::from_mode(0o770)).unwrap();
        assert_eq!(acquire(&paths).err().unwrap().code, "ptt_unavailable");
        fs::set_permissions(&paths.state, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_file(paths.state.join("authority-v1")).unwrap();
        let target = directory.path().join("outside");
        fs::write(&target, CONTRACT).unwrap();
        symlink(target, paths.state.join("authority-v1")).unwrap();
        assert_eq!(acquire(&paths).err().unwrap().code, "ptt_unavailable");
    }

    #[test]
    fn admitted_input_mutation_excludes_ptt_state_transitions() {
        use std::os::fd::AsRawFd;
        let (_directory, paths) = fixture();
        let guard = acquire(&paths).unwrap();
        let contender = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&paths.lock)
            .unwrap();
        // SAFETY: contender owns a valid descriptor for both flock calls.
        assert_ne!(
            unsafe { libc::flock(contender.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(guard);
        assert_eq!(
            unsafe { libc::flock(contender.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
    }

    #[test]
    fn mutation_classification_covers_indirect_input_paths() {
        assert!(input_node("Audio/Source"));
        assert!(input_node("Stream/Input/Audio"));
        assert!(!input_node("Audio/Sink"));
        assert!(policy_requires_authority(
            "bluetooth.autoswitch-to-headset-profile"
        ));
        assert!(!policy_requires_authority(
            "node.stream.default-playback-volume"
        ));
        let request = |method: &str, params: Value| Request {
            version: 1,
            id: "ptt-test".into(),
            method: method.into(),
            params,
        };
        assert!(store_requires_authority(&request(
            "preferences.default",
            json!({"direction":"input","name":"mic"})
        )));
        assert!(store_requires_authority(&request(
            "rules.set_app",
            json!({"app":"Discord","direction":"recording","target":"mic"})
        )));
        assert!(store_requires_authority(&request(
            "rules.delete_app",
            json!({"app":"Discord","direction":"recording"})
        )));
        assert!(store_requires_authority(&request(
            "devices.forget",
            json!({"address":"00:11:22:33:44:55"})
        )));
        assert!(!store_requires_authority(&request(
            "rules.set_app",
            json!({"app":"Music","direction":"playback","target":"sink"})
        )));
    }
}
