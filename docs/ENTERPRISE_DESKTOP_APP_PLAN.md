# Enterprise Desktop App Plan

This plan turns AI Employee into a downloadable enterprise desktop app for
Windows, macOS, and Linux while preserving the existing Node, Python, and React
architecture.

## Product Requirements

- Supported OS targets:
  - Windows: NSIS installer and portable build, later MSI.
  - macOS: DMG and ZIP, later signed/notarized PKG.
  - Linux: AppImage and DEB, later RPM if needed.
- Default mode: fully offline.
- Network access: disabled by default and enabled only by OS policy/config or
  explicit user/admin choice.
- First boot: prepare and validate everything locally from bundled resources,
  then launch the dashboard.
- Normal use: no terminal, no manual Node/Python commands.
- Runtime state: stored in OS app data, not in the installed app/resources tree.
- Services: Node gateway and Python backend bind to `127.0.0.1`.
- Security: no default secrets, signed JWTs, explicit approval for risky Money
  Mode actions.

## Current Implementation Baseline

- Electron launcher exists under `launcher/`.
- Frontend builds to `frontend/dist`.
- Node backend runs from `backend/server.js`.
- Python backend runs from `runtime/agents/problem-solver-ui/server.py`.
- Launcher now passes:
  - `AI_EMPLOYEE_HOME`
  - `AI_HOME`
  - `STATE_DIR`
  - `LOG_DIR`
  - `RUN_DIR`
  - `AI_EMPLOYEE_OFFLINE=1`
  - `LISTEN_HOST=127.0.0.1`
- Packaged mode fails clearly if bundled dependencies are missing instead of
  trying to install from the network.
- First-boot validation now checks the local runtime before launch and writes a
  setup marker under app data.
- Linux offline directory packaging works with the local Electron runtime via
  `npm --prefix launcher run package:dir:offline`.
- Windows startup no longer requires `bash`; the launcher can spawn the Node
  gateway through Electron's bundled Node runtime and use `py -3`/`python` for
  the Python backend.

## Phase 1: Runtime Layout

Use the installed app directory as read-only code/resources and app data as the
only mutable runtime location.

```text
Installed app resources/
  repo/
    backend/
    frontend/dist/
    runtime/
    start.sh
    stop.sh

OS app data/
  config/
  state/
  logs/
  run/
  cache/
  tenants/
  models/
```

Acceptance criteria:

- The app can run from a read-only install directory.
- Logs, PID files, SQLite DBs, JSONL event streams, telemetry, and user state are
  written under app data.
- App updates do not overwrite user data.

## Phase 2: Offline First Boot

First boot must not download packages.

Required bundled content:

- `backend/node_modules`
- Electron launcher dependencies packaged by electron-builder
- `frontend/dist`
- Python runtime or Python executable bundle
- Python dependencies, either as a bundled venv, PyInstaller output, or embedded
  Python distribution
- Runtime agents and configs

First boot sequence:

1. Resolve app data directory.
2. Create `config`, `state`, `logs`, `run`, and `cache`.
3. Generate local JWT secret if missing.
4. Validate bundled Node backend dependencies.
5. Validate bundled frontend assets.
6. Validate Python backend availability.
7. Run local schema/state migrations.
8. Start Python backend on `127.0.0.1`.
9. Start Node gateway on `127.0.0.1`.
10. Open dashboard only after health checks pass.

Acceptance criteria:

- Fresh machine starts without internet.
- Missing bundled dependencies produce a clear installer/build error.
- No `npm install`, `pip install`, Git fetch, or external model pull happens in
  default packaged mode.
- Setup UI disables dependency installation while offline policy is active.

## Phase 3: OS Policy And Network Control

Add a managed policy file in app data:

```json
{
  "network": {
    "offlineByDefault": true,
    "allowDependencyInstall": false,
    "allowModelDownloads": false,
    "allowAutoUpdate": false
  },
  "security": {
    "bindHost": "127.0.0.1",
    "requireApprovalForMoneyMode": true
  }
}
```

Policy priority:

1. Enterprise managed policy.
2. Environment variables.
3. User settings.
4. Safe defaults.

Acceptance criteria:

- Admin can enable online installs/updates by OS policy.
- Normal users cannot bypass locked enterprise settings.
- Offline mode is the default on all OSes.
- Launcher diagnostics expose the effective policy source and values.

## Phase 4: Python Runtime Packaging

Decision still required: choose one Python packaging route.

Recommended path:

1. Linux first: bundled venv or PyInstaller Python backend executable.
2. Windows/macOS: PyInstaller or embedded Python distribution.
3. Heavy optional AI dependencies remain optional and are detected at runtime.

Acceptance criteria:

- App runs when system Python is not installed.
- Python backend version and dependency status are visible in diagnostics.
- Missing optional model dependencies create degraded mode, not app failure.

## Phase 5: Build And Installer Pipeline

Root commands:

```bash
npm run build:frontend
npm --prefix launcher run package:dir:offline
npm run dist:desktop:linux
npm run dist:desktop:mac
npm run dist:desktop:win
npm run dist:desktop:all
```

Release artifacts:

```text
launcher/dist/
  *.AppImage
  *.deb
  *.dmg
  *.zip
  *.exe
  *.portable.exe
```

Acceptance criteria:

- Build process produces all OS artifacts from a clean checkout with local
  dependency cache/bundles available.
- Build artifacts are ignored by git.
- Packaged app starts without terminal.

## Phase 6: Security Hardening

Required:

- Bind local services to `127.0.0.1`.
- Enforce JWT signatures between frontend, Node, and Python.
- Store generated secrets in app data config.
- Never ship default secrets.
- Disable network installs in packaged offline mode.
- Keep Electron `contextIsolation` enabled and `nodeIntegration` disabled.
- Add code signing and notarization before enterprise distribution.

Acceptance criteria:

- Forged JWTs fail.
- LAN clients cannot access local API by default.
- Renderer cannot access Node APIs directly.
- Money Mode cannot publish, spend, accept paid work, or modify accounts without
  approval.

## Phase 7: Diagnostics

Diagnostics export must include:

- App version.
- OS/platform.
- App data paths.
- Node/Python health.
- Recent launcher/backend/Python logs.
- Dependency status.
- Redacted config summary.

Diagnostics must not include:

- API keys.
- Wallet secrets.
- Client private data.
- Raw payment credentials.

## Phase 8: Remaining Engineering Work

1. Bundle Python runtime for all three OSes.
2. Add a locked enterprise policy source per OS (Windows registry/Group Policy,
   macOS managed preferences, Linux `/etc` policy) above user config.
3. Add first-boot migration from repo-local state to app data.
4. Move every remaining backend state path to `STATE_DIR`.
5. Add installer smoke tests.
6. Add signed update channel, disabled by default in offline enterprise mode.
7. Add code signing and macOS notarization.
8. Add Windows MSI for enterprise deployment.

## Verification Baseline

```bash
node --check launcher/main.js
node --check launcher/src/paths.js
node --check launcher/src/backend.js
node --check backend/server.js
bash -n start.sh
bash -n stop.sh
npm --prefix frontend run build
npm run test:security:node
PYTHONPATH=runtime python3 -m pytest tests/test_multitenant.py tests/test_economy.py
```
