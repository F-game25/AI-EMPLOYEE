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

## 8. AscendForge  — `ASCENDFORGE_SYSTEM_AUDIT.md` Phase E (2026-07-01, current)
- 🟡 **Phase E — Goal Achievement System** (plan approved; execution starting) — reframed from
  "task queue" to "goal in → plan → agents on sub-tasks" per Lars. Full plan:
  `/home/lf/.claude/plans/clever-wandering-dragon.md`.
  - ⬜ E1 — canonical queue: durable `autopilot_sessions`, finish the `forge_cycles` lifecycle
    (progress tracking + completion detection), `/submit` adapter mode, backlog cancel/retry
  - ⬜ E2 — goal fast-path (skip full decompose for simple asks) + skill/agent routing (wire
    `runDecomposerAgent`'s unused `required_skills` → `skill_selector.select_skills()`; verify
    reuse of `runtime/agents/business_swarm/*` before writing new logic)
  - ⬜ E3 — execution capability uplift: scoped file read/grep/glob tools, iterative per-file
    verify, sub-task delegation via the existing-but-unused `forge_child_runs` table, branching
  - ⬜ E4 — concurrency gate for local LLM calls (measured: 4 concurrent forge runs → 2-of-4
    Ollama calls failed on 8GB VRAM) + retry tuning against a clean serialized baseline
  - ⬜ E5 — UI: Cycles/Backlog/Autopilot/Decomposer currently have zero UI surface; collapse the
    3 fragmented approval views into one
  - ⬜ E6 — safety hardening cross-cutting (no autonomy-gate bypass via conversion/delegation)
- ✅ Two live codegen bugs found + fixed 2026-07-01 (dangling unclosed code fence; fence-hint path
  leakage e.g. `"python calc.py"`) in `extractCodeActions`/`_buildCodeAction`, `backend/routes/
  forge.js` — benefits both the basic `/runs` path and the agentic `runCoderAgent` path. Regression
  tests: `tests/test_forge_codegen_extract.js`. New local benchmark task `codegen_local_model` in
  `tests/benchmarks/` measures real coding-model reliability (not just "did it run").
- ⬜ Older v2→v7 controlled-execution docs (`docs/ASCEND_FORGE_V7_CONTROLLED_EXECUTION_*`) —
  superseded by the live audit doc; archive once Phase E lands.

## 9. Security & privacy  — `CLAUDE.md`, `SECURITY*.md`, `docs/PRIVACY_ARCHITECTURE.md`
- ⬜ Increase route auth coverage (was 44/119 Node routes)
- ⬜ Prompt-injection tests for RAG/agent paths; secret scanning; sandbox hardening

## 10. Tech debt / testing / CI  — `docs/TECHNICAL_DEBT_CLEANUP.md`
- ⬜ Tech-debt cleanup items
- ⬜ Desktop tests + CI coverage
- ⬜ Archive superseded/duplicate plans (see inventory)

## 11. Cross-system gap audit — PR #335 (`claude/gap-analysis-deep-dive-twiozu`, **not yet merged**)
A file-level audit of every path/DoD claimed across all of `MASTER_PLAN_V3.md` (P1-P10 + Modules
1-12), landing here so it isn't lost regardless of whether/when that PR merges. Full detail:
`docs/GAP_ANALYSIS_2026_06_30.md` (on that branch). Cross-confirms two AscendForge findings
independently (Module 3 Forge Lifecycle OS essentially complete; Module 7 Business Swarm fully
built — see section 8 above). Total: 4 modules entirely missing, 9 partially built, ~25 individual
missing files, 5 cross-cutting issues, 7 fully done.

**Tier 1 — fix broken / safety gaps:**
- ⬜ `runtime/evolution/trace_store.py` — traces don't survive a restart, no replay/promotion query
- ⬜ `runtime/companion/audit_logger.py` — companion actions currently unlogged (compliance gap)
- ⬜ `runtime/tools/browser/browser_events.py` — companion can't stream browser activity without it
- ⬜ `runtime/money/work_engine/submission_queue.py` — the two-gate approval safety invariant is unenforced without it
- ⬜ RPA proxy auth fix — `/api/rpa/*` 500s at the Node→Python boundary (`makeProxy('RPA')` doesn't forward a valid token)

**Tier 2 — complete partial modules:** `browser_session.py`+`browser_sandbox.py` (profile isolation); `context_node.py`+`retrieval_trace.py`+`memory_writer.py` (Context DB); `component_quality_checker.py`+`image_to_code_pipeline.py` (Forge UI quality); `source_collector.py` (Research Quality); extract `human_review_gate.py` as a hard enforcement module (FinanceOps).

**Tier 3 — complete P10 CompanyOS backend:** `agent_team_orchestrator.py`, `task_cycle_engine.py`, `build_integration.py`, `marketing_engine.py`, `support_engine.py`, `metrics_engine.py`; memory graph linkage; frontend TaskCycle/AgentTeam/Marketing/Metrics cockpit pages.

**Tier 4 — build missing modules:** M12 Model Arena (`runtime/core/arena/`, 6 files); M9 Blacklight Defensive Skill OS (`runtime/security/skills/`+`security/tools/`, 16 files, entirely absent); M5 voice/media (`runtime/voice/` + `runtime/media/`, entirely absent); M4 Work Engine completion (6 files + `marketplace_adapters/`); M10 Harness Compat (`runtime/harness/`, entirely absent); M11 Reference Learning Library (entirely absent).

**Tier 5 — P2 perf + P9.5 Rust:** `useDeferredValue` (zero uses anywhere in `frontend/src/`); virtualize event feed + logs (extend the `@tanstack/react-virtual` pattern already used on `OrdersPage`); P9.5 gather profiling data first, before any native rewrite.

---

## Plan inventory (duplicates to resolve)
| Doc | Note |
|---|---|
| ✅ `MASTER_PLAN.md`, `V2_MASTER_PLAN.md`, `MASTER_PLAN_V3.md` | **RESOLVED (2026-06-30):** older two → `docs/archive/`. `MASTER_PLAN_V3.md` KEPT as the feature-roadmap + build-status **companion** to the canonical plan. |
| `DESKTOP_APP_PLAN.md` vs `ENTERPRISE_DESKTOP_APP_PLAN.md` | two desktop plans — `DESKTOP_APP_PLAN.md` is the active one (this effort) |
| `ASCENDFORGE_*` / `ASCEND_FORGE_*` v2→v7 | many iterations — v7 is latest |
| ✅ `SYSTEM_COHERENCE_PLAN.md` | **CANONICAL (2026-06-30)** — single authoritative architecture/control plan; incoming research lands in its Appendix A (R-1…R-5 added 2026-07-01). `SYSTEM_CONNECTIVITY_ROADMAP.md`/`TARGET_ARCHITECTURE.md`/`SYSTEM_REALITY_AUDIT.md` remain reference inputs to reconcile into it over time. |
| 🟡 `docs/GAP_ANALYSIS_2026_06_30.md` | Lives on unmerged PR #335 (`claude/gap-analysis-deep-dive-twiozu`) — file-level gap audit of `MASTER_PLAN_V3.md`. Reconciled into section 11 above 2026-07-01 so nothing is lost regardless of merge status. |

## Needs-decision (Lars)
- ✅ **Which master plan is authoritative?** → `SYSTEM_COHERENCE_PLAN.md` (canonical); `MASTER_PLAN_V3.md` kept as companion; `MASTER_PLAN.md` + `V2_MASTER_PLAN.md` archived. _(decided 2026-06-30)_
- ❓ Desktop milestone order after M3 — updater (M4) next, or jump to Linux bundle (M5)?
- ❓ Do the AETERNUS→AETHERNUS rename now (touches identity contract) or after desktop v1?
- ❓ Re-run the full 40-doc audit agent (fresh session) to make this list exhaustive?
- ❓ Merge PR #335 (`claude/gap-analysis-deep-dive-twiozu`)? Real, already-verified gap-audit work sitting unmerged; recommend merging so `MASTER_PLAN_V3.md`'s gap annotations become the live version everyone works from — but merging is Lars's call, not done silently as part of this reconciliation pass.
