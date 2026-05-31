# Enterprise Bundling Security Plan

AETERNUS NEXUS must ship as a complete offline-first application. Crucial runtime capabilities are built in, not treated as optional extensions.

## Core Runtime Contract

The canonical list is `runtime/config/core_dependency_manifest.json`.

Core entries must be importable before startup:

- launcher and first-boot checks
- `runtime/core/startup.py --preflight`
- `scripts/verify_core_dependencies.py`
- packaged installer verification

If a core dependency is missing, startup must fail clearly. The app may not silently download it on first boot.

## Open-Source Code Policy

Open-source code that becomes part of the core system must be vendored deliberately:

- place patched copies under a project namespace such as `runtime/vendor/aeternus_vendor/<project>`
- rename local modules/packages so they cannot shadow the upstream package name
- record upstream name, version, source URL, license, checksum and local patch notes
- keep license files and notices with the distributed app
- block build output if license metadata or checksums are missing

Unmodified third-party Python packages should prefer signed or hash-pinned wheels in `runtime/wheelhouse/<platform>/<python-version>/` instead of copied source.

## Offline Build Flow

1. Resolve Python, Node and browser/runtime dependencies from lockfiles.
2. Download or build platform wheels into the offline wheelhouse.
3. Generate checksums and license notices.
4. Install from wheelhouse with `--no-index --find-links`.
5. Build `frontend/dist`.
6. Package Electron with `runtime/`, `backend/`, `frontend/dist/`, wheelhouse, vendor metadata and verification scripts.
7. Run `scripts/verify_core_dependencies.py` inside the packaged runtime.
8. Fail the build on missing imports, missing licenses, checksum mismatch or unexpected network dependency.

Connectors for external services remain policy-gated. They may be bundled, but they cannot be required for offline boot unless they are promoted into the core manifest with security review.

## Local Build Commands

Build the Python core wheelhouse for the current OS/Python:

```bash
npm run build:python-core
```

Build Python core plus Playwright browser binaries for offline RPA:

```bash
npm run build:python-core:full
```

Verify an existing wheelhouse without network access:

```bash
npm run verify:python-core
```

Create the first-boot venv from the bundled wheelhouse:

```bash
npm run bootstrap:python-core
```

The bootstrap creates `AI_HOME/python-core` and installs with `--no-index --find-links`. The launcher and `start.sh` prefer that venv automatically when it exists.

Playwright browser binaries are stored under `runtime/browsers/playwright`; runtime exports `PLAYWRIGHT_BROWSERS_PATH` so browser automation cannot trigger a first-use download.
