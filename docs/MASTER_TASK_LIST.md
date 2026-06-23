# MASTER TASK LIST — every unfinished thing, one place

**Why this exists:** the repo has ~40 planning docs in `docs/` (multiple master plans, two desktop
plans, AscendForge v2→v7, etc.). Work is started, then a new plan begins before the last one finishes.
This is the single consolidated backlog so nothing is lost. Keep it updated; archive superseded plans.

> Status legend: ✅ done · 🟡 in progress · ⬜ open · ❓ needs decision
> _Note: a read-only audit agent meant to scan all 40 docs was cut off by a session limit before
> producing output. This list is synthesized from the active plans + memory and should be expanded
> against the source docs (see “Plan inventory” at the bottom)._

---

## 1. Desktop / Nexus OS shell  — `docs/DESKTOP_APP_PLAN.md`
- ✅ M1 — kill the white screen (splash-first + readiness gate) — PR #301
- ✅ M2 — runtime reuse + free-port selection + runtime lock — PR #301
- ✅ Fix — AI CORE always-red (read `pythonReady` from `/api/readiness`) — PR #301
- 🟡 M3 — first-run setup screen + Ollama detect (consent) — branch `feat/desktop-m3` (started)
- ⬜ M4 — updater: `tauri-plugin-updater` + `tauri-plugin-process`, minisign-signed, GitHub Releases, update screen (download→verify→apply→relaunch)
- ⬜ M5 — bundle + ship Linux v1: Node sidecar + Python core + `better-sqlite3` rebuilt for bundled-Node ABI; AppImage + `.deb`; verify on clean VM
- ⬜ M6 — Windows parity: WebView2 bootstrap, NSIS, target-triple sidecars
- ⬜ M7 — macOS parity: dmg (x64+arm64), WKWebView
- ⬜ M8 — retire Electron `launcher/` shell + OS code-signing (removes install warnings)
- ⬜ F1 — make `/api/runtime/identity` unauthenticated on localhost (so reuse can verify identity nonce; currently 401)
- ⬜ F2 — frontend boot handshake via `POST /api/boot/phase` (Tauri-agnostic transport; replaces Electron `window.ai`)
- ⬜ Security — production mode + managed `SETTINGS_ENCRYPTION_KEY` applied uniformly to `start.sh` AND the desktop runtime (currently neither sets `NODE_ENV=production`)
- ⬜ Node-supervisor refactor — de-Electron-ify `launcher/src/{backend,health,first_boot,policy,phases,paths}.js` into a Node supervisor sidecar reused by the Rust shell (the “combination of both” synthesis)
- ❓ `src-tauri/gen/schemas/*.json` — decide commit vs gitignore (regenerated each build)

## 2. Naming / branding  — memory `naming-and-branding`
- ⬜ Coordinated rename `AETERNUS NEXUS` → `AETHERNUS NEXUS` (with H) across ~33 files, **including the identity contract** (`backend/routes/auth-identity.js` emit + `launcher/src/backend.js` compare — both sides together or the port-lock breaks)
- ⬜ React app still shows `AETERNUS NEXUS` (e.g. `frontend/src/components/BootMenu.jsx` brand) → `Nexus OS` / `Aethernus Nexus`

## 3. System coherence  — `docs/SYSTEM_COHERENCE_PLAN.md`
- ✅ GoalRegistry — one canonical goal identity (PR #293, merged)
- ⬜ Land/verify in-flight coherence branches (worktrees present): `c1-280` single-spine, `intent` unify, `skillchain`, `phase1-spine`, `pr-282`, `pr-288`
- ⬜ Remaining of the “4 structural fractures” (re-read the plan for specifics)

## 4. Unified memory  — `docs/UNIFIED_MEMORY_SYSTEM.md` (Codex, ACTIVE)
- 🟡 Codex working on `docs/unified-memory-system-map` (unified store + knowledge/neural adapters + migration). **Coordinate — shared main checkout; do desktop work only in worktrees.**

## 5. Model orchestration  — `docs/MODEL_ORCHESTRATION_PLAN.md`, `docs/LOCAL_QUANTIZATION_AND_MODEL_ORCHESTRATION_PLAN.md`
- ⬜ Per-task model selection; CPU/RAM offload; OpenRouter overflow; local quantization
- ⬜ Ollama VRAM config (fast default `gemma3:4b-it-qat`, `MAX_LOADED_MODELS=2`) — partly noted in memory

## 6. Money / revenue  — `docs/ORDERS_MONEY_PIPELINE_*`, memory `project-ai-employee-overview`
- ⬜ Close the “what’s missing to actually earn money” gaps
- ⬜ Harden `money_mode` pipelines + approval gates

## 7. Sales / demos  — memory `sales-demo-rebuild-progress`
- 🟡 Unique multi-page demos + Sales section (mid-flight)

## 8. AscendForge  — `docs/ASCEND_FORGE_V7_CONTROLLED_EXECUTION_*` (latest of v2→v7)
- ⬜ Finish v7 controlled-execution items (verify against the audit/impl docs)

## 9. Security & privacy  — `CLAUDE.md`, `SECURITY*.md`, `docs/PRIVACY_ARCHITECTURE.md`
- ⬜ Increase route auth coverage (was 44/119 Node routes)
- ⬜ Prompt-injection tests for RAG/agent paths; secret scanning; sandbox hardening

## 10. Tech debt / testing / CI  — `docs/TECHNICAL_DEBT_CLEANUP.md`
- ⬜ Tech-debt cleanup items
- ⬜ Desktop tests + CI coverage
- ⬜ Archive superseded/duplicate plans (see inventory)

---

## Plan inventory (duplicates to resolve)
| Doc | Note |
|---|---|
| `MASTER_PLAN.md`, `V2_MASTER_PLAN.md`, `MASTER_PLAN_V3.md` | 3 master plans — V3 likely newest; confirm + archive older |
| `DESKTOP_APP_PLAN.md` vs `ENTERPRISE_DESKTOP_APP_PLAN.md` | two desktop plans — `DESKTOP_APP_PLAN.md` is the active one (this effort) |
| `ASCENDFORGE_*` / `ASCEND_FORGE_*` v2→v7 | many iterations — v7 is latest |
| `SYSTEM_COHERENCE_PLAN.md`, `SYSTEM_CONNECTIVITY_ROADMAP.md`, `TARGET_ARCHITECTURE.md`, `SYSTEM_REALITY_AUDIT.md` | overlapping architecture/coherence — reconcile into one source of truth |

## Needs-decision (Lars)
- ❓ Which master plan is authoritative (archive the rest)?
- ❓ Desktop milestone order after M3 — updater (M4) next, or jump to Linux bundle (M5)?
- ❓ Do the AETERNUS→AETHERNUS rename now (touches identity contract) or after desktop v1?
- ❓ Re-run the full 40-doc audit agent (fresh session) to make this list exhaustive?
