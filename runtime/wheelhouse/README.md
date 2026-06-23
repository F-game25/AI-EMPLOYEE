# Offline Wheelhouse

Packaged enterprise builds populate this directory with platform-specific wheels.
`scripts/build_python_core_bundle.py` writes them into a per-target subdirectory:

`runtime/wheelhouse/<os>-<arch>-py<major><minor>/`  e.g. `linux-x86_64-py312/`

Startup and first-boot verification must not download core dependencies in offline mode. Build jobs
(and the desktop first-run provisioner) install from the wheel-bearing subdirectory with
`--no-index --find-links`. Note `pip --find-links` does **not** recurse, so the path passed must be
the subdirectory that actually holds the `.whl` files, not this root. The desktop shell resolves it
via `find_wheelhouse()` in `src-tauri/src/lib.rs` (handles this `<tag>/` layout and a nested
`<platform>/<pyver>/` layout).
