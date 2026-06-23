# DESKTOP APP PLAN — One Coherent OS Shell (AETERNUS NEXUS)

**Status:** PLAN (approved decisions captured 2026-06-20) — not yet implemented.
**Owner:** Lars.
**Goal (not a task list):** One desktop application that boots, supervises, and updates the
whole AI-EMPLOYEE runtime as a single coherent OS — lightweight, always-live, no white screen,
enterprise-grade on Linux → Windows → macOS.

---

## 0. Decisions locked (from Lars, 2026-06-20)

| Decision | Choice | Consequence for this plan |
|---|---|---|
| Desktop shell | **Combination of both** — Tauri shell + reused Electron-launcher brain | Tauri = lightweight face/lifecycle; the proven Node launcher logic is reused, not rewritten |
| Code signing | **Ship unsigned for now** | OS installers unsigned (Gatekeeper/SmartScreen warnings tolerated in v1); update payloads still cryptographically signed via minisign |
| Ollama | **Manage separately** | Not in the installer; detected + offered on first-run with consent; models pulled once |
| First hardened OS | **Linux first** | v1 nails Linux end-to-end, then the *same* flow ports to Windows + macOS |

---

## 1. Root cause of the white screen (confirmed, not guessed)

`src-tauri/tauri.conf.json:24` creates the main window pointing at `http://localhost:8787`.
Tauri shows that window **immediately**, while `backend/server.js` (Node) and the Python AI
backend are still starting. WebView gets connection-refused → white screen / "cannot connect to
localhost". `src-tauri/src/lib.rs:36` spawns `node backend/server.js` + `python3 …` with **bare
binaries on relative paths** and no readiness gate.

Meanwhile `launcher/` (Electron) already solves this exact problem: it shows a branded splash,
streams boot phases, retries on connection-refused 12× ([main.js:514](../launcher/main.js#L514)),
self-heals stale chunks, and only swaps to the dashboard once `/api/readiness` passes.

**The mushup = two shells. The fix = one shell that keeps the working brain.**

---

## 2. The synthesis architecture ("combination of both")

You cannot literally run one process that is both Electron and Tauri. But you can take the best of
each and you should, because of one hard fact: **`backend/server.js` is a Node.js server.** Any
shell must therefore ship a Node runtime. Electron embeds Node for free; Tauri must bundle it.
Since Node must be bundled with Tauri anyway, we run the **already-battle-tested launcher logic on
that same bundled Node** — zero rewrite, full liveness — under a lightweight Rust shell.

```
AETERNUS NEXUS.app  (single installer, single updater, single lifecycle)
│
├─ TAURI v2 (Rust)  ── the lightweight SHELL  (~10 MB)
│   ├─ AppLifecycle: single-instance, tray, quit, OS integration
│   ├─ WindowManager: splash window (visible) + main window (visible:false)
│   ├─ RuntimeManager: spawns + supervises the Node supervisor sidecar
│   ├─ ReadinessGate: polls /api/readiness; swaps splash→main only when ready
│   ├─ Updater: tauri-plugin-updater (minisign-signed) ← replaces electron-updater
│   └─ EventBridge: forwards supervisor stdout JSON → splash webview (live boot/update)
│
├─ NODE SUPERVISOR sidecar  ── the proven BRAIN  (reuse launcher/src/*.js, de-Electron-ified)
│   ├─ port-lock + identity nonce + stale-runtime cleanup   (backend.js)
│   ├─ health/readiness probes + exponential backoff        (health.js)
│   ├─ first-boot dependency manifest + Python resolution    (first_boot.js)
│   ├─ wheelhouse bootstrap + native-module handling         (first_boot.js)
│   ├─ offline-first policy                                   (policy.js)
│   ├─ phase tracking + timings                               (phases.js)
│   └─ spawns + watches:  Node backend  +  Python AI backend
│
├─ NODE RUNTIME (bundled sidecar, ONE binary)  → runs the supervisor AND backend/server.js
├─ PYTHON CORE (bundled, offline)              → runtime/agents/problem-solver-ui/server.py
└─ OLLAMA (managed separately, consent-gated)  → detected/installed on first run, not bundled
```

**Division of responsibility (no overlap):**

- **Rust shell** owns everything *visible and lifecycle*: windows, splash, tray, single-instance,
  updater, and the **readiness gate** (the white-screen fix). It is deliberately thin.
- **Node supervisor** owns everything *runtime/environment*: the painful, OS-specific orchestration
  that already works. We do **not** port it to Rust (that was the months-of-regression risk).
- **One Node binary** serves both supervisor and backend → "most efficient / lightweight."

This is the literal "combination of both that is efficient, lightweight, and stays live."

> **Honest framing of "no separate processes":** Node, Python, and Ollama remain separate OS
> processes — they are different runtimes; that is unavoidable and correct. What becomes *one* is
> everything the user and operator touch: **one app, one installer, one updater, one boot UI, one
> log stream, one tray, one lifecycle.** No loose terminals, no manual ports, no `start.sh` by hand.

---

## 3. Shell ⇄ Supervisor contract (newline-delimited JSON)

Rust spawns the supervisor sidecar and speaks a tiny protocol — no extra port, cross-platform.

**Supervisor → Rust (stdout, one JSON object per line):**
```jsonc
{"t":"phase","phase":"node-port-bound","label":"Node gateway listening","durationMs":420}
{"t":"log","level":"info","line":"[node] listening on 127.0.0.1:8787"}
{"t":"status","state":"starting","message":"Verifying dependencies"}
{"t":"route","uiOrigin":"http://127.0.0.1:8787","nodePort":8787,"pythonPort":18790,"nonce":"…"}
{"t":"ready","degradedPython":false}
{"t":"fail","phase":"preflight","reason":"Python 3 not found"}
```

**Rust → Supervisor (stdin, one JSON object per line):**
```jsonc
{"cmd":"start","extraEnv":{}}
{"cmd":"restart","verbose":true}
{"cmd":"stop"}
```

Rust **also** independently confirms `/api/readiness` via `reqwest` before showing the main window
(belt-and-suspenders: supervisor reports progress; Rust verifies server-side truth). The dashboard
URL is **whatever the supervisor reports in `route.uiOrigin`** — never hardcoded (port-lock may
pick 8788+).

---

## 4. Runtime readiness contract (already exists — with 2 fixes)

| Endpoint | Auth | Exists | Use |
|---|---|---|---|
| `/api/health` | no | ✓ ([health.js](../backend/routes/health.js)) | liveness |
| `/api/readiness` | no | ✓ ([health.js:539](../backend/routes/health.js#L539)) | **the gate** (node+python+index+assets) |
| `/api/runtime/identity` | **yes** | ✓ ([auth-identity.js:277](../backend/routes/auth-identity.js#L277)) | ownership nonce match |
| Python `/health` | no | ✓ | python liveness |

**Fix F1 — identity probe is auth-gated but the supervisor probes it tokenless.** Either expose a
minimal unauthenticated `/api/runtime/identity` (safe: localhost-bind only, returns app name +
nonce used purely for runtime-ownership) or have the supervisor sign the probe with the JWT it
already mints. Decision: **unauthenticated identity on 127.0.0.1 bind only** (smallest safe change;
nonce is a liveness token, not a secret granting access).

**Fix F2 — frontend boot handshake transport.** The dashboard already emits
`window.ai.notifyUiBootPhase('react-rendered')` ([main.jsx:87](../frontend/src/main.jsx#L87)) — an
Electron preload contract. Under Tauri the dashboard is a **remote (http) origin**, so Tauri IPC
isn't trivially available. Transport options, chosen for least coupling:
- The dashboard POSTs boot phases to the **Node backend** (`POST /api/boot/phase`), the supervisor
  tails them, forwards to Rust → splash. No Tauri-IPC-to-remote-origin dependency.
- A thin `window.ai` shim (injected by Tauri init script) maps the existing calls to that POST, so
  **frontend code stays unchanged**.

This keeps the rich phase rail (`react-rendered` / `react-mounted`) without binding the dashboard to
either shell — the same handshake works under Electron or Tauri.

---

## 5. Boot state machine (first-run, regular, update)

```
        ┌─────────────┐
        │   LAUNCH    │ Rust: single-instance lock, create splash (visible),
        └──────┬──────┘       create main (visible:false)
               │
        ┌──────▼──────┐
        │  FIRST-RUN? │ Rust checks app_data marker AND asks supervisor checkFirstBoot()
        └──┬───────┬──┘
       yes │       │ no
   ┌───────▼──┐    │
   │  SETUP   │    │  Setup screen: show missing deps; with consent → fetch Python core,
   │ (consent)│    │  detect/offer Ollama (manage-separately). Writes setup_complete.
   └───────┬──┘    │
           └───┬───┘
        ┌──────▼──────┐
        │  SUPERVISE  │ Supervisor: port-lock → spawn Python → spawn Node → stream phases.
        │  (live UI)  │ Splash renders phases + live logs the WHOLE time. ← no white screen
        └──────┬──────┘
        ┌──────▼──────┐
        │  READINESS  │ Rust polls /api/readiness (+ supervisor "ready"). Degraded path if
        │    GATE     │ python missing → still open, banner "AI backend degraded".
        └──┬───────┬──┘
      pass │       │ fail (after retries)
   ┌───────▼──┐ ┌──▼─────────┐
   │ SHOW MAIN│ │ DIAGNOSTICS│ failing phase + last 20 logs + open-logs / copy / restart-verbose
   │ load URL │ └────────────┘
   └──────────┘
```

**Update flow (separate from boot):** Tauri updater checks GitHub Releases on launch (policy-gated).
If an update exists → **the same splash/boot UI shows an UPDATE screen** with download progress and
"what's happening" (download → verify signature → apply → relaunch). This satisfies "shows what is
happening inside the system when it is booting/updating."

---

## 6. Boot UI (reuse the Electron renderer, served by Tauri)

The Electron boot UI (`launcher/renderer/index.html` + `app.js` + CSS) already has **boot / setup /
update / diagnostics** screens, a phase rail, ASCII progress, and a live log console. **Reuse it
verbatim as the Tauri splash window content.** Only the transport changes:

- `window.ai.*` (Electron IPC) → thin shim over `@tauri-apps/api` `invoke` + `event.listen`.
- `onPhase / onStartLog / onUpdaterEvent` → Tauri `event.listen('phase'|'log'|'updater:*')`.
- `startSystem / stopSystem / restartVerbose / openLogsFolder` → Tauri `invoke('…')` commands.

Result: identical look-and-feel, zero visual rebuild, runs in the lightweight WebView.

---

## 7. Cross-platform bundling (Linux first)

| Artifact | Linux (v1) | Windows | macOS |
|---|---|---|---|
| Shell | Tauri AppImage + `.deb` | NSIS (currentUser) | `.dmg` (x64+arm64) |
| Node runtime | sidecar `node-x86_64-unknown-linux-gnu` | `node-x86_64-pc-windows-msvc.exe` | `node-…-apple-darwin` |
| Python core | bundled (`build_python_core_bundle.py`) + SHA256 manifest | same | same |
| WebView | `libwebkit2gtk-4.1` (deb depends) | WebView2 (bootstrap if absent) | WKWebView (system) |
| Ollama | detect/offer (not bundled) | detect/offer | detect/offer |

- **Sidecars** follow Tauri's `bundle.externalBin` + target-triple naming
  ([Tauri sidecar docs](https://v2.tauri.app/develop/sidecar/),
  [Node.js as a sidecar](https://v2.tauri.app/learn/sidecar-nodejs/)).
- **Native module** `better-sqlite3` must be compiled for the **bundled Node's ABI** (not system
  Node, not Electron). Build step per target triple; verified at first-boot (reuse first_boot.js's
  native-check, retargeted from Electron ABI to bundled-Node ABI).
- **No hardcoded paths/ports** — everything via env passed from Rust (`AI_EMPLOYEE_HOME`,
  `STATE_DIR`, `LOG_DIR`, `RUN_DIR`, `AI_EMPLOYEE_PACKAGED=1`, chosen ports).

---

## 8. Updater (signed payloads even while OS-unsigned)

- Use **tauri-plugin-updater + tauri-plugin-process**, GitHub Releases provider
  (already the Electron publish target: `F-game25/AI-EMPLOYEE`).
- **OS code-signing = off for v1** (Lars's choice) → installers show OS warnings.
- **Update integrity ≠ OS signing.** Tauri's updater verifies a **minisign** signature on the update
  artifact regardless of OS signing. We generate a minisign keypair, keep the **private key out of
  the repo** (CI secret), publish the public key in `tauri.conf.json`. So updates remain
  tamper-evident in v1; OS code-signing is a later milestone that removes install warnings.
- Policy gate: respect offline-first `allowAutoUpdate` (reuse `policy.js`). Auto-update opt-out
  always honored.

---

## 9. Security threat model (touches: command execution, file access, network, updater, ports)

| Surface | Risk | Control |
|---|---|---|
| Sidecar spawn | arbitrary exec | only allowlisted bundled binaries via `externalBin`; no shell string interpolation; no user-controlled argv |
| Ports | hijack / cross-bind | bind `127.0.0.1` only; port-lock + identity nonce verify we own the runtime before reuse |
| Updater | malicious update | minisign signature verify before apply; HTTPS GitHub Releases; opt-out honored |
| First-run network | silent egress | offline-by-default policy; Python core/Ollama fetches are **consent-gated** and logged |
| Secrets | JWT/API leakage | `JWT_SECRET_KEY` auto-generated to `~/.ai-employee/.env` (never repo, never logged); redact in diagnostics export |
| File scope | path traversal | all runtime writes scoped to `AI_EMPLOYEE_HOME`; no repo writes from packaged app |
| Diagnostics export | secret leak | reuse log redaction; never include `.env` contents |
| Identity endpoint (F1) | nonce exposure | localhost-bind only; nonce is liveness token, grants no access |

---

## 10. Migration & cleanup (smallest safe change, nothing left broken)

1. **De-Electron-ify** `launcher/src/{paths,first_boot,backend,health,policy,phases}.js` into a new
   `supervisor/` package: replace the ~4 `require('electron')` calls (`app.getPath`, `app.isPackaged`)
   with env inputs from Rust. **Keep the logic identical** (the liveness we're protecting).
2. **Drop** `launcher/src/update.js` (electron-updater) — replaced by Tauri updater.
3. **Reuse** `launcher/renderer/*` as Tauri splash assets + add the `window.ai`→Tauri shim.
4. **Rewrite** `src-tauri/src/lib.rs`: remove the `:8787` hardcode + bare-spawn; add WindowManager
   (splash+main), RuntimeManager (spawn supervisor sidecar), ReadinessGate, EventBridge, updater.
5. **Fix npm script drift:** `tauri:install` copies `nexus-os` but the bin is `ai-employee`;
   `productName` differs ("AI Employee" vs "AETERNUS NEXUS"). **Unify to `AETERNUS NEXUS`** (matches
   `/api/runtime/identity.app`).
6. **Retire** the Electron `launcher/` *shell* (main.js/preload.js/electron-builder) **only after**
   the Tauri shell reaches parity — keep it runnable until then so nothing is broken mid-flight.
7. **Keep** `start.sh` as the dev/CI path (bash); the packaged app uses the supervisor's
   direct-spawn (Windows-safe). Both stay valid.

---

## 11. Milestones (goal-oriented; each ends with proof, Linux first)

> A milestone is "done" only when built + tested + demonstrated, per the security CLAUDE.md DoD.

- **M1 — Kill the white screen (Linux).** Tauri: splash window first, main `visible:false`, Rust
  readiness gate against `/api/readiness`, dashboard loaded from supervisor-reported origin.
  *Proof:* cold launch on Linux shows splash → dashboard, never a connection-refused screen; kill
  Node mid-boot → diagnostics screen, not white screen.
- **M2 — Live supervisor brain.** Supervisor package (de-Electron-ified) spawns Node+Python with
  port-lock + identity + degraded mode; streams phases/logs to splash via the JSON protocol.
  *Proof:* phase rail + live logs render during boot; second launch reuses runtime via lock.
- **M3 — First-run setup + Ollama (consent).** Setup screen detects missing deps, fetches Python
  core, detects/offers Ollama. *Proof:* clean `~/.ai-employee` → guided setup → healthy boot.
- **M4 — Updater (signed payload).** Tauri updater vs GitHub Releases, minisign-verified, update
  screen shows download→verify→apply→relaunch. *Proof:* publish vN+1, app self-updates and relaunches.
- **M5 — Bundle + ship Linux v1.** AppImage + `.deb` with Node sidecar + Python core + better-sqlite3
  rebuilt for bundled-Node ABI. *Proof:* installs + runs on a clean Linux VM with nothing
  preinstalled (except WebKitGTK from deb deps).
- **M6 — Windows parity.** WebView2 bootstrap, NSIS, target-triple sidecars. *Proof:* clean Win VM.
- **M7 — macOS parity.** dmg (x64+arm64), WKWebView. *Proof:* clean macOS.
- **M8 — Retire Electron shell + OS code-signing milestone** (removes install warnings).

---

## 12. Definition of done (per security CLAUDE.md)

Code builds on all three OS; readiness gate prevents white screen on every failure mode; sidecar
spawn allowlisted; secrets never logged/committed; updates signature-verified; offline-first policy
enforced; diagnostics redacted; **rollback** = prior installer + `app_data` is backward-compatible;
changed files listed; remaining risks documented.

**Rollback:** keep the Electron `launcher/` shell runnable until M8; `~/.ai-employee` layout is
unchanged (same `state/ logs/ run/ config/`), so a user can revert to the old shell with no data loss.

---

## 13. Open risks

- Bundled-Node ABI vs `better-sqlite3` — must rebuild per target; mitigated by first-boot verify.
- Tauri Linux `webkit2gtk-4.1` version drift across distros — pin deb deps; document supported set.
- Tauri IPC to remote (http) dashboard origin — sidestepped via backend POST transport (F2).
- Unsigned installers (Lars's v1 choice) — warnings on Win/macOS until M8; documented, not a defect.
- Minisign private key handling — CI secret only; never in repo.

---

## 14. Reference map (where the reusable logic already lives)

| Need | Reuse from | Notes |
|---|---|---|
| port-lock + identity + spawn | `launcher/src/backend.js` | drop electron `process.execPath` → bundled Node path |
| health/readiness probes | `launcher/src/health.js` | already framework-agnostic |
| first-boot deps + python + wheelhouse | `launcher/src/first_boot.js` | replace `app.isPackaged` with env flag |
| offline-first policy | `launcher/src/policy.js` | framework-agnostic |
| phase model + timings | `launcher/src/phases.js` | framework-agnostic |
| path resolution | `launcher/src/paths.js` | replace `app.getPath` with env |
| boot/setup/update/diag UI | `launcher/renderer/*` | reuse as Tauri splash + `window.ai` shim |
| readiness contract | `backend/routes/health.js`, `auth-identity.js` | apply F1 (unauth identity) + F2 (boot phase POST) |
| python core bundle | `scripts/build_python_core_bundle.py`, `bootstrap_python_core.py` | already exists |
```
