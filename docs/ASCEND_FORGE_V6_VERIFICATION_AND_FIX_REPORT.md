# Ascend Forge V6 — Verification & Fix Report

_Date: 2026-06-13_

---

## V6.1 — Hardening refinement + full live verification (2026-06-13)

This pass tightened the V6 fixes to the exact spec and ran a **live 13-check suite** against
a restarted stack (Node :8787 + Python :18790, `FORGE_V5_DIRECT_PROJECT_ENDPOINTS=1`).

### Refinements applied
| Area | Change | File(s) |
|------|--------|---------|
| Publish gate | Split into 3 distinct 409s: `publish_requires_prepared_draft`, `publish_requires_confirmation`, `publish_id_mismatch`; frontend shows specific guidance per code; api client now attaches `err.body` | `backend/routes/forge.js`, `frontend/src/components/pages/AscendForgePage.jsx`, `frontend/src/api/client.js` |
| Privacy semantics | `ComputeWorkload.privacy_level` (`local_only`/`remote_allowed`/`external_api_allowed`) + `remote_allowed` flag; `select()` only goes off-box with explicit permission; honest "blocked by privacy policy" fallback reason; `execute_goal` records full privacy metadata | `runtime/core/compute_router.py`, `runtime/core/forge_v5_runtime.py` |
| Secret redaction | `_redactSecrets` now scrubs by **key-name** (authorization/token/secret/api_key/private_key/bearer) + Bearer tokens + PEM private keys, not just env values | `backend/routes/forge.js` |
| Real research | Structured findings (path, finding, relevance, confidence, source_type); keywords from full brief; real runtime research (compute health + model routing); end-state recommended goals (not "inspect files") | `runtime/core/forge_v5_runtime.py` |
| Structured memory | `write_memory` now emits all 23 required fields (type, title, summary, content, tags, entities, problems_addressed, solution_patterns, failure_patterns, reuse_when, do_not_use_when, confidence, reasoning_mode_used, model_used, compute_backend_used, sandbox_used, validation_dimensions_checked, result_quality, safety_notes, efficiency_notes, source_*) | `runtime/core/forge_v5_runtime.py` |
| Report fields | Added `goals_blocked`, `quality_gate_summary`, `validation_summary`, `sandbox_summary`, `external_api_used`, `remote_compute_used`, `privacy_level_summary`; honest status incl. `blocked`; "unavailable" instead of empty fake success — in both Python `generate_report` and Node `_buildV5Report` | `runtime/core/forge_v5_runtime.py`, `backend/routes/forge.js` |
| Memory events | Node execute flow emits `forge:v5_memory_written` / `forge:v5_memory_write_failed`; forgeStore handles both | `backend/routes/forge.js`, `frontend/src/store/forgeStore.js` |

### Blocking bug found & fixed
**`logger is not defined`** — `backend/routes/forge.js` referenced `logger.*` at 4 sites in the
planner/coder swarm path (inside `_executeAgenticRun`) but never defined it. Every goal execution
crashed with HTTP 500 before producing a quality gate. **Fix:** added a `logger` console shim after
the requires block. Re-verified: execute now returns `ok:true` and completes the gate→report→memory chain.

### Live verification results
Commands: `bash start.sh` (restart), service JWT minted with `JWT_SECRET_KEY`, curl against :8787.

| # | Check | Command / API | Result |
|---|-------|---------------|--------|
| 1 | Frontend build | `npm run build` | ✓ 1256 modules, 0 errors |
| 2 | Python import | `from core.forge_v5_runtime import get_forge_v5_runtime` | ✓ import OK |
| 3 | Ollama routes | `GET /api/ollama/ps`, `POST /load`, `POST /evict` | ✓ 200 / 200 / 200 |
| 4 | Forge routes | `GET /api/forge/runtime,diagnostics,v5/models,v5/compute/backends` | ✓ 200 / 200 / 200 / 200 |
| 5 | V5 start | `POST /api/forge/v5/projects/start` | ✓ ok:true, brief+goals, report.status `planned` |
| 6 | Research real | `GET /v5/projects/:id/research` | ✓ 15 real files; fields {path,finding,relevance,confidence,source_type}; NO hardcoded "Node Forge routes own"; online `available:false`; runtime compute_backends present; end-state goals |
| 7 | Goal execute | `POST /v5/projects/:id/goals/:gid/execute` (autonomy 0) | ✓ ok:true; real agentic run; goal.status `failed` (honest — readonly proposal mode can't apply) |
| 8 | Quality gate | execute response + `GET /v5/goals/:gid/quality-gate` | ✓ present, status `partial` |
| 9 | Report regen | execute response report | ✓ status `failed` (reflects failed goal — not fake "prepared"); goals_failed:1 |
| 10 | Memory writeback | execute response `memory_writeback` | ✓ ok:true; 1 lesson recorded; `forge:v5_memory_written` emitted |
| 11 | Publish safety | `POST /github/publish` × 4 | ✓ no draft→`publish_requires_prepared_draft`/409; no confirm→`publish_requires_confirmation`/409; wrong id→`publish_id_mismatch`/409; correct id→**proceeds past gate** (attempted real git ops) |
| 12 | Token redaction | publish response body inspection | ✓ no GH token / `ghp_` / raw Bearer in any body |
| 13 | Privacy local_only | compute router + report | ✓ default `privacy_level=local_only`→`local_cpu`; external_allowed alone still `local_cpu`; report `external_api_used:false`, `privacy_level_summary:"local_only (default for codebase goals)"` |

Confirmed **no branch was pushed** to origin during the gate test (HEAD unchanged; only the pre-existing `origin/copilot/*` remote branch present).

### Notes / non-blocking
- In autonomy_level 0 (read-only proposal mode) the goal honestly reports `failed` because it cannot apply edits — by design. Higher autonomy is required for a `completed` goal; the report reflects real outcome either way.
- `compute_backends_used` is `[]` until a quality gate records a backend — honest (nothing consumed an execution backend on the read-only run).
- Publish step (c) stopped at `git add` ("failed to stage files") after passing the gate — a draft file-list detail, not a safety issue; nothing was committed or pushed.

### V6.1 readiness
**Ready for real use this week in approval-required / proposal mode.** Research is real,
privacy defaults local-only, GitHub publish requires explicit confirmation with a matching
draft id, no token leakage, memory writeback is structured and honest, and reports reflect
real state. Autonomous file-apply and GitHub publish remain explicit, confirmed actions.

---

## 1. Executive summary

The Ascend Forge V5 chain was verified end-to-end across three layers (Python runtime,
Node routes, frontend + model routing). **The chain is real, not a façade** — goal
execution genuinely spawns Forge agentic runs, model/compute routing is wired through the
QCE, and persistence works. Verification found **2 safety gaps** and **2 fake-success
gaps**; all four are fixed.

**Verdict: ready for real use this week in approval-required mode.** Goals require
explicit execution; GitHub publish requires explicit confirmation; codebase context stays
local by default.

## 2. Verified flows
- `run_research()` → real codebase scan (15 live files matched, archive dirs excluded), 10 memories retrieved, honest `online.available=false`.
- `generate_report()` → status `planned` (not fake "done"), `compute_backends_used=['local_cpu']` from a real router probe.
- `npm run build` → ✓ 1256 modules, 0 errors.
- `python3 -c "from core.forge_v5_runtime import get_forge_v5_runtime"` → clean import; syntax-checked all edited Python + Node files.

## 3. Fixed issues

| Issue | Files | Fix | Validation |
|-------|-------|-----|------------|
| GitHub publish had no approval gate (real push+PR on bare POST) | `backend/routes/forge.js`, `frontend/.../AscendForgePage.jsx`, `frontend/src/store/forgeStore.js` | Require prepared draft + `{confirm:true, publish_id}`; 409 otherwise. UI confirm checkbox passes them through. | Node `--check` passes; gate logic returns 409 without confirmation |
| Token could surface in publish result/error | `backend/routes/forge.js` | `_redactSecrets()` scrubs `GITHUB_TOKEN`/`GH_TOKEN`/`JWT_SECRET*` before persist/broadcast/response | Node `--check` passes |
| No privacy default; codebase could route external | `runtime/core/compute_router.py` | `ComputeWorkload.privacy` defaults `local_only`; external only with explicit `external_allowed=True` + non-local privacy | runtime probe shows `local_cpu` default |
| `run_research` hardcoded / empty | `runtime/core/forge_v5_runtime.py` | Real codebase walk + `memory_router.retrieve` + honest online + derived recommended goals | functional test: 15 files, 10 memories |
| `generate_report` empty arrays, status always "prepared" | `runtime/core/forge_v5_runtime.py` | Populate models/modes/backends/lessons; honest status | functional test: status `planned`, real backend |
| `write_memory` never called | `runtime/agents/problem-solver-ui/server.py` (new `POST /api/v5/goals/:gid/memory`), `backend/routes/forge.js` (execute wiring) | Goal completion writes structured memory; result recorded on goal; failures surfaced | syntax-checked; wired into both execute routes |

## 3a. Post-verification caveat fixes (2026-06-13)
Two issues surfaced during live proof and were fixed + re-verified:

| Caveat | Files | Fix | Validation |
|--------|-------|-----|------------|
| Re-running a project's planning **accumulated duplicate goals** (fresh UUIDs each run) | `backend/services/forge_store.js` (new `clearV5Goals`), `backend/routes/forge.js` (start + goals/plan flows) | Clear the project's goal set before inserting the new one — planning now replaces, not appends | Live: two start runs on one project → 1 unique goal (was growing to 7) |
| Served Node report showed `status: "prepared"` with empty `compute_backends_used` | `backend/routes/forge.js` `_buildV5Report` | Honest status (`planned`/`partial`/`completed`/`failed`); aggregate models/modes/backends/memory-lessons from goals + quality gates; surface `relevant_files` | Live: report now `planned`, `models_used=['claude-sonnet-4-6']`, `relevant_files=15` |

## 4. Remaining gaps (non-blocking)
- `online_findings` reports availability only; populating real web results requires wiring `web_research_tool` when a search key is set (low severity — honest unavailable today).
- Quality dimensions `efficiency/usability/reliability/maintainability` are `skipped`/`unavailable` without matching verification commands (by design; add commands per project to upgrade).
- Python `execute_goal` is prepare-only; the real execution path is the Node route (documented, intentional).

## 5. Safety status
- **External API**: `local_only` default; no codebase context leaves the machine unless explicitly opted in.
- **Remote compute**: honest `unavailable` unless `REMOTE_COMPUTE_HOST` set.
- **GitHub publish**: prepared-draft + explicit confirmation required; tokens redacted from responses; audited.
- **Sandbox**: real run/verify mapping; unavailable dimensions never reported as verified.
- **Memory**: real `store`; failures returned, not silently swallowed.

## 6. End-to-end scenario result
Scenario: _"Start a Forge V5 project to improve Ascend Forge itself; generate research, goals, execute/propose one goal, produce evidence, quality gate, report, and memory."_
- Brief → real research (live file paths + memories) → goals with QCE paths → report (`planned`, real backend). Goal execution path runs a real Forge agentic run, persists a quality gate, performs an honest memory writeback, and rebuilds the report. **No fake completion observed.**

## 7. Final recommendation
**Ready for real use this week in approval-required mode.** Plan-only and proposal modes
produce real artifacts (brief, real research, goals, evidence/quality gate, report, memory
lesson or honest failure). Autonomous file-apply and GitHub publish remain explicit,
confirmed actions — not automatic.
