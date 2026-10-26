# Security review and operating boundary

The complete upstream tree at the revision in `UPSTREAM.md` was reviewed as
untrusted third-party code before adaptation. Static review covered QML and
JavaScript, Rust, shell and Python helpers, packaging and systemd files, CI,
the Cargo lockfile, and the bundled ELF as non-executed data.

## Capabilities retained

The plugin can observe the PipeWire graph, change PipeWire/WirePlumber audio
state, persist bounded JSON settings under the user's Omarchy configuration,
run fixed local diagnostic/audio tools, write a support report to the clipboard
on request, and optionally invoke Omarchy's fixed audio-recovery UI. Microphone
tests invoke fixed `pw-record`/`pw-play` commands and keep the bounded clip in
memory. It has no privileged helper and no runtime network client.

Developer-only release tooling runs Cargo and executes the newly built backend
to read its build metadata. Production startup does neither build nor download.
The upstream optional systemd files remain in source but are not part of the
Hugin installation plan.

## Resolved findings

- **High — PTT bypass:** upstream allowed microphone changes independently of
  Discord PTT. The owned backend now serializes input mutations with the PTT
  helper and rejects direct and indirect capture changes while PTT owns the
  microphone or its authority cannot be proven.
- **High — unreviewed native execution:** startup previously built or selected
  a cached backend. Hugin startup now accepts only the reviewed bundled ELF
  matching exact release metadata, source build ID, target, ownership/mode, and
  SHA-256.
- **High — vulnerable Tokio:** 1.53.1 was affected by RUSTSEC-2026-0386. The
  lockfile uses 1.53.3, and the two `AsyncFd` registrations document why their
  owned descriptors remain valid for the entire registration lifetime.

## PTT policy

The PTT helper and backend share
`$XDG_RUNTIME_DIR/omarchy-plus-discord-ptt/authority.lock`. The helper holds it
across marker and `wpctl` mute transitions; the backend holds it through every
admitted input mutation. A private versioned state contract is mandatory.

PTT enabled or unverifiable:

- output volume/defaults and playback routing remain available;
- input volume/mute/defaults/ports/routes and recording rules are blocked;
- card profiles, Bluetooth capture policies/device forgetting, scene apply,
  and microphone tests are blocked because they may change capture state.

PTT disabled and verified: those input operations are available normally.

## Remaining uncertainty

Static inspection and isolated tests cannot prove the absence of all defects.
PipeWire, WirePlumber, Bluetooth firmware, Discord, and applications can change
audio outside this backend. The first deployment therefore still requires a
stopped-state backup, immutable-binary verification, and physical confirmation
of Caps Lock press/release PTT behavior, the RØDE input, and Arctis output.
