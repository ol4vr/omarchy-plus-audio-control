# Advanced Audio Control for Omarchy

Advanced Audio Control brings persistent routing, saved setups, and device
controls to Omarchy's audio panel.

The Omarchy+ `0.9.1-omarchy.1` release passed Hugin security, compatibility,
rollback, and physical acceptance on 2026-10-26. Its reviewed backend SHA-256
is recorded in `BUILD-PROVENANCE.json` and `backend-release.json`.

Choose which output or microphone each application uses, play through several
outputs together, and restore saved device settings. Keep Omarchy's familiar
quick mixer for everyday volume changes, with an advanced window for profiles,
Bluetooth modes, microphone testing, and diagnostics.

Useful when you regularly switch between speakers, headphones, USB audio
devices, or different setups for music and calls.

## What it adds to Omarchy

Compared with the [stock audio panel in Omarchy 4.0.4](https://github.com/omacom/omarchy/blob/c668141e9c42b13c80c9ca4ea108e11708c5e8a5/shell/plugins/panels/audio/Panel.qml):

| Stock panel | Advanced Audio Control adds |
| --- | --- |
| Output, microphone, and application volume; device selection | A quick mixer plus persistent output and microphone choices for each application |
| Current device controls | Saved scenes for defaults, volume, balance, ports, and profiles |
| One selected output | Groups of two to eight outputs, each with its own volume control |

For example:

- Send music to the speakers while a call uses headphones: set each application's
  output to **Always use** its chosen device.
- Save a **Desk** scene with USB speakers and a desk microphone, and a
  **Headphones** scene for private listening; restore either setup from the
  advanced window.
- With [Advanced Bluetooth Audio](https://github.com/ssupt/omarchy-bluetooth-audio),
  let a headset reconnect without replacing your microphone: choose **Manual**
  or **Output** under **Audio on connect** for that device.

## Screenshots

<table>
  <tr><th>Quick mixer</th><th>Advanced window</th></tr>
  <tr>
    <td valign="top"><a href="screenshot-mixer.png"><img src="screenshot-mixer.png" width="348" alt="Quick mixer with device, microphone and application volume controls"></a></td>
    <td valign="top"><a href="screenshot-advanced.png"><img src="screenshot-advanced.png" width="684" alt="Advanced window with device profiles, balance, microphone test and settings tabs"></a></td>
  </tr>
</table>

## Everyday controls

| Action | Control |
| --- | --- |
| Open mixer | Left-click the audio icon or press `Super+Ctrl+A` |
| Change output volume | Scroll over the audio icon |
| Mute microphone | Middle-click the audio icon |
| Mute all audio | Right-click the audio icon |
| See microphone users | Hover over the audio icon |
| Open advanced window | Select the mixer gear |

For an application, **Follow default output** clears a saved destination;
**Always use** keeps the chosen device across restarts. Recording applications
can also stay pinned to a microphone. The advanced window also offers device
aliases and favorites, stereo balance, supported Bluetooth modes, microphone
activity and a five-second record-and-playback test, speaker identification,
audio recovery, and diagnostics.

An output group can drift when its devices use separate clocks, especially with
Bluetooth. Microphone tests start only when requested; clips stay in memory
until discarded or until the advanced window closes.

## Discord PTT ownership on Hugin

This Omarchy+-owned adaptation treats `io.github.ol4vr.discord-ptt` as the
authoritative microphone owner. The Rust backend verifies its private state
contract while holding the same cross-process authority lock as the PTT helper.
When PTT is enabled, output volume, output selection, and playback routing keep
working, while microphone volume/mute, input defaults and routes, recording
rules, profiles, input ports, Bluetooth capture policy, scenes that may alter
capture, and microphone tests fail closed. The lock is retained until an
admitted input mutation finishes, preventing a PTT transition from racing the
operation. Missing or unsafe PTT state also disables microphone mutations.

The QML surfaces explain the disabled controls, but the backend is the security
boundary. With PTT disabled and its authority contract healthy, normal input
controls remain available.

## Installation contract

Hugin deployment is performed only by the Omarchy+ reconciler from an
immutable reviewed revision. A release contains a native backend built from the
locked Rust source by the controlled release process. Startup verifies the
source build ID, target, executable ownership/mode, and SHA-256 from
`backend-release.json`; it never invokes Cargo, downloads dependencies, or
replaces the binary. A verification failure leaves the audio plugin unavailable
instead of executing an unreviewed binary.

The optional upstream systemd units are retained as attributed source but are
not installed on Hugin. See [BUILD.md](BUILD.md), [SECURITY.md](SECURITY.md), and
[ROLLBACK.md](ROLLBACK.md) for the build, security, and removal contracts.

Disabling or removing the plugin restores Omarchy's built-in audio widget.
The managed integration can add **Setup > Audio** with:

```bash
~/.config/omarchy/plugins/io.github.ol4vr.audio-control/scripts/audio-menu-entry install
```

Use the same helper with `remove` before removing the plugin.

## Saved settings

Settings live under `~/.config/omarchy` (or `$XDG_CONFIG_HOME/omarchy`).
Existing files and supported schemas are preserved.

| File | What it remembers |
| --- | --- |
| `audio-control.json` | Output boost and capture notifications |
| `audio-preferences.json` | Preferred devices and Bluetooth profiles, shared with the Bluetooth companion |
| `audio-rules.json` | Application rules, device preferences, and output groups |
| `audio-scenes.json` | Saved scenes |

## Service architecture

The interface uses Quickshell/QML. A Rust service keeps saved choices and
in-progress changes alive when a panel closes or reloads. It coordinates audio
changes with PipeWire and WirePlumber, then reports whether each requested
change was confirmed, rejected, or left uncertain. The service controls audio;
PipeWire still carries and mixes the sound.

A controlled test against 0.8.1 measured over 99% less CPU with the advanced
window open, using about 3 MiB more memory.

If your Omarchy configuration directory is a symlink, restart the audio service
after retargeting it so file watches follow the new location.

## Contributing

Edit `qml/`, `backend/src/`, and `scripts/`; `runtime/` contains generated QML.
Use `Text.PlainText` for labels; external names and saved text can contain markup.
Builds require Rust/Cargo **1.85+**, libclang, pkg-config, and PipeWire and
libpulse headers. Node.js, Python, jq, and Qt/Quickshell run the tests.

```bash
./test/all
python3 packaging/build-release.py --output /tmp/omarchy-audio-release
python3 packaging/build-release.py --check /tmp/omarchy-audio-release
omarchy-plugin-validate /tmp/omarchy-audio-release
```

Use a fresh directory outside the live plugin for each candidate. Commit the
matching binary, release metadata, manifest, and generated runtime when changing
runtime sources. CI also runs native audio, lifecycle, and upgrade tests under
`test/integration/` with private audio devices and configuration.

`scripts/audio-rust-backend` and `packaging/systemd/` are upstream-compatible
developer facilities. They are not used by the Hugin production contract.

The Bluetooth companion calls `default.compat` with a node ID and name; the
service verifies the live endpoint and reports the outcome. Both plugins share
`audio-preferences.json`, while compatibility helpers support older companions.
Coordinate releases when changing that shared contract.

[MIT license](LICENSE). This adaptation is based on
[`ssupt/omarchy-audio-control`](UPSTREAM.md) and retains its attribution.
