# Hugin rollback

The accepted Hugin deployment preserves the shell plugin configuration, the
plugin's JSON stores, and the effective WirePlumber defaults, routes, profiles,
ports, and saved settings before activation. That snapshot is the rollback
baseline; a global `wpctl settings --reset` is never part of rollback.

Rollback is deliberately simple:

1. while the reviewed backend is still available, compare current audio state
   with the activation snapshot;
2. remove only positively identified `io.github.ol4vr.audio-control` output
   groups through the backend's verified group-removal operation, after moving
   any active playback to an existing physical output;
3. restore only defaults, routes, profiles, ports, and saved policy values that
   the accepted deployment or physical test changed, using their captured
   pre-activation values; preserve unrelated terminal, application, and
   WirePlumber changes;
4. stop/reconcile Quickshell through the established Omarchy plugin lifecycle;
5. disable and remove only `io.github.ol4vr.audio-control`;
6. restore the backed-up plugin configuration and the stock `omarchy.audio`
   widget placement;
7. start/reconcile Quickshell once and verify that no owned group module or
   saved automatic route remains, then verify RØDE input, Arctis output, and
   Discord PTT Caps Lock press/release behavior.

Do not delete shared audio preferences, reset WirePlumber globally, or operate
the Discord PTT helper during rollback. The owned plugin seeds no routes,
scenes, groups, profiles, or policy overrides. User-created state remains user
data and requires explicit review before removal. Stopping the backend alone is
not group cleanup: active combine modules deliberately survive backend restarts
to avoid interrupting playback, so they must be removed through the owned,
identity-checked operation before the plugin is disabled.
