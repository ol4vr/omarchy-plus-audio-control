# Upstream provenance

- Repository: `https://github.com/ssupt/omarchy-audio-control.git`
- Reviewed commit: `c822e48fa3b0d8f3cc2f0bf96eace416f30f0764`
- Reviewed Git tree: `baae455c1b33a4b62b24e513dbe850b9cce99c92`
- Upstream version: `0.9.1`
- License: MIT; the original `LICENSE` file is retained unchanged.
- Upstream bundled x86_64 backend SHA-256:
  `ce8dd41267eb065d9c2e6bc1db06ff9b3114c0280a7b970a98946d9436cc15c9`

The bundled upstream executable was inspected as data and was never executed.
Omarchy+ builds a replacement from reviewed locked source. The upstream remote
is fetch-only; the owned `ol4vr/omarchy-plus-audio-control` remote is the future
publication authority.

## Omarchy+ delta

- use the owned plugin ID `io.github.ol4vr.audio-control`;
- enforce Discord PTT ownership in the Rust backend and explain it in QML;
- replace Tokio 1.53.1 with patched, exactly locked Tokio 1.53.3;
- use Tokio's unsafe `AsyncFd::register` only where the wrapper owns the file
  descriptor for the complete registration lifetime;
- remove build/download/cache replacement from normal plugin startup;
- verify a reviewed bundled backend against its source build ID and SHA-256;
- add focused PTT, immutable-release, and rollback validation.

No optional service is installed and no application route, scene, group,
profile, or policy is seeded by this owned release.
