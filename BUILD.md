# Controlled native build

The reviewed x86_64 candidate is built outside production with:

- official Rust 1.85.1 (`rustc 1.85.1 (4eb161250 2025-03-15)`);
- Cargo 1.85.1 (`d73d2caf 2024-12-31`);
- the committed `backend/Cargo.lock` and `cargo build --locked --release`;
- host PipeWire 1.6.8 and libpulse `17.0-98-gb096` development interfaces;
- `packaging/build-release.py` in a fresh temporary output directory.

The release tool calculates a content-derived source build ID, invokes only the
new Cargo artifact to obtain `--build-info`, records its SHA-256 in
`backend-release.json`, generates the matching immutable QML runtime tree, and
then verifies the assembled release. `BUILD-PROVENANCE.json` records the exact
result. The production launcher verifies that record but never builds.

The independent toolchain is installed only in an isolated build directory;
Hugin's package database is not changed. Registry dependencies are resolved by
the committed lockfile. Dependency advisory review must pass before deployment.

For this candidate, cargo-audit 0.22.1 checked 85 locked crates against RustSec
database commit `21d909e4c8bd4e14c7aea58bf980c881a0053ab1` with no vulnerability
or warning.
