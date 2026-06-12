# Ascend Forge V6 — Verification & Hardening Audit

_Date: 2026-06-13 · Scope: full V5 project-execution chain on top of the existing Forge run machinery._

> **V6.1 update (2026-06-13):** Hardening refined to exact spec and verified live (13/13 checks
> pass). Publish gate now returns 3 distinct 409 codes; privacy uses `privacy_level`
> (local_only default) + `remote_allowed`/`external_allowed`; secret redaction scrubs by key-name +
> Bearer + PEM; research findings are structured (path/finding/relevance/confidence/source_type) with
> real runtime checks; `write_memory` emits 23 structured fields; reports carry
> goals_blocked/quality_gate_summary/validation_summary/sandbox_summary/external_api_used/remote_compute_used/privacy_level_summary;
> `forge:v5_memory_written`/`_write_failed` events wired. **Blocking bug fixed:** `logger is not defined`
> in `backend/routes/forge.js` execute path (added console shim). Full results in the companion fix report.

This audit verifies the real, end-to-end Ascend Forge V5 chain (not "routes return 200").
It records what is genuinely wired, what is partial, what was fake, and the safety posture —
and the targeted hardening applied (see companion fix report).

---

## 1. Runtime map

### Frontend (`frontend/`)
- **Views** (`src/components/pages/AscendForgePage.jsx`): `v5_project`, `v5_goals`, `v5_reasoning`, `v5_quality`, `github` (plus the legacy run/queue/backlog views).
  - `V5ProjectView` / `V5GoalsView` / `V5ReasoningView` / `V5QualityView` read via the `useV5ProjectData(projectId)` hook (parallel GET of brief/research/goals/report + per-goal quality gates).
  - `GitHubPublishView` reads from the Zustand `forgeStore.github` slice.
- **Store** (`src/store/forgeStore.js`): normalized snapshot — `v5` (brief/researchPack/goals/reasoning/qualityGates/report/phase), `github` (status/draft/result/phase/error), `queue`, `runs`, `actions`, `reports`, `memoryLessons`, `pendingApprovals`. `applyForgeEvent()` routes all `forge:*` events; `github_publish_*` handlers are reachable (prior dead-code bug fixed).
- **API client** (`src/api/client.js`): `forge.v5.*` (startProject/getBrief/getResearch/getGoals/executeGoal/getQualityGate/writeQualityGate/getReport/getComputeBackends/getModels), `forge.github.{status,prepare,publish}`, run lifecycle.

### Backend Node (`backend/routes/forge.js`, mounted at `/api/forge`)
- V5: `POST /v5/projects/start`, `GET /v5/projects/:id/{brief,research,goals,report}`, `POST /v5/projects/:id/research`, `POST /v5/projects/:id/goals/plan`, `POST /v5/goals/:gid/execute` + `POST /v5/projects/:id/goals/:gid/execute`, `GET|POST /v5/goals/:gid/quality-gate`, `GET /v5/compute/backends`, `GET /v5/models`.
- GitHub: `GET /projects/:id/github/status`, `POST /projects/:id/github/prepare`, `POST /projects/:id/github/publish`.
- Helpers: `callPythonV5`/`getPythonV5` (service-JWT to Python :18790), `_codeIndexToken`, `_readV5Json`, `_upsertV5Artifact`, `_redactSecrets` (new), `_buildV5Report`, `_executeAgenticRun`.
- Ollama VRAM: `dashboard-api.js` → `GET /api/ollama/ps`, `POST /api/ollama/load`, `POST /api/ollama/evict`.

### Backend Python (`runtime/agents/problem-solver-ui/server.py`, :18790)
- `POST /api/v5/brief|research|goals|reason|quality`, `GET /api/v5/compute/backends`, `GET /api/v5/models/health`.
- Direct-project endpoints (gated by `FORGE_V5_DIRECT_PROJECT_ENDPOINTS=1`): start, brief, research(POST/GET), goals/plan(POST)+GET, execute, report(GET), quality-gate(GET), **memory(POST)** (new).

### Runtime files
- `runtime/core/forge_v5_runtime.py` — orchestrator (`ForgeV5Runtime`): brief, research, goals, execute, quality gate, write_memory, generate_report.
- `runtime/core/forge_reasoning_orchestrator.py` — QCE wrapper (real `get_qce().process/plan`, `AmplitudeRouter`).
- `runtime/core/compute_router.py` — real `nvidia-smi`/ollama/env health checks.
- `runtime/core/forge_sandbox_manager.py` — maps run/verify output to the 7 quality dimensions.
- Model routing: `runtime/agents/turbo-quant/turbo_quant.py` (`select_model`, OpenRouter overflow), `runtime/engine/inference/llm.py` (`ensure_model_ready`, VRAM warm/evict), `runtime/core/llm_provider_router.py` (anthropic→ollama→openrouter fallback).
- Memory: `runtime/memory/memory_router.py` (`store`/`retrieve` → cache + vector + graph).

---

## 2. Verified working paths

| Path | Test | Result |
|------|------|--------|
| Research codebase scan | `run_research()` on a Forge-improvement brief | 15 live files matched (archive dirs excluded), real paths returned |
| Memory retrieval in research | same | 10 memories retrieved via `memory_router.retrieve` |
| Honest online research | same (no search key set) | `online_findings.available=false`, reason recorded — no faked results |
| Report metadata | `generate_report()` | status `planned`; `compute_backends_used=['local_cpu']` from real router probe |
| Compute health | `ComputeRouter.health()` | real GPU/remote/external states from env + `nvidia-smi`/ollama |
| Goal execution bridge | `POST /v5/projects/:id/goals/:gid/execute` | runs `_executeAgenticRun` → real Forge agentic run → quality gate persisted → memory writeback → report rebuilt |
| Frontend build | `npm run build` | ✓ 1256 modules, 0 errors |
| Python import | `from core.forge_v5_runtime import get_forge_v5_runtime` | clean |

## 3. Partial paths
- `forge_v5_runtime.execute_goal()` (Python) is **prepare-only by design** — returns `prepared_for_existing_forge_run`. Real execution is owned by the **Node** execute route via `_executeAgenticRun`. This split is intentional and now documented.
- Quality dimensions `efficiency/usability/reliability/maintainability` map to `skipped`/`unavailable` unless a matching verification command exists — honest, not faked.

## 4. Broken paths
- None remaining. (Prior: `/api/ollama/ps|load|evict` 404 — fixed by moving to `dashboard-api.js`; forgeStore `github_publish_*` dead code — fixed.)

## 5. Fake/disconnected paths — FIXED
| Was fake | Now |
|----------|-----|
| `run_research` returned 2 hardcoded strings, empty online/recommended | Real codebase walk + memory retrieve + honest online availability + derived recommended goals |
| `generate_report` returned empty `models_used`/`compute_backends_used`/`reasoning_modes_used`/`memory_lessons`, status always `prepared` | Populated from real reasoning/goal/quality-gate metadata; status `planned`/`partial`/`completed`/`failed` |
| `write_memory` existed but was never called | Wired into the Node execute flow via new `POST /api/v5/goals/:gid/memory`; result recorded on the goal (`memory_writeback`), failures surfaced |

## 6. Safety risks & posture
- **GitHub publish** — was `requireAuth`-only, performed real `git push` + PR. **Fixed:** requires a prepared draft AND explicit `{ confirm:true, publish_id }`; UI adds a confirm checkbox. `prepare` stays draft-only.
- **Secret hygiene** — `_redactSecrets()` scrubs `GITHUB_TOKEN`/`GH_TOKEN`/`JWT_SECRET*` from any publish result/error before persist, broadcast, or response.
- **External API / privacy** — `ComputeWorkload.privacy` now defaults to `local_only`; `ComputeRouter.select()` routes to `external_api` only when a caller explicitly sets `external_allowed=True` AND non-`local_only` privacy. Codebase context stays local by default.
- **Remote compute** — honest `unavailable` unless `REMOTE_COMPUTE_HOST` set. No faking.
- **Sandbox** — maps real run/verify output; unavailable dimensions marked, never "verified".
- **Memory writes** — go through `memory_router.store` (cache+vector+graph); write failures returned honestly.

## 7. Missing evidence — addressed
- Goal completion previously claimed done on agent text. Now: completion persists a quality gate, an honest memory-writeback record, and a report that reflects real goal statuses.

## 8. Prioritized fix plan — status
1. GitHub publish approval gate — **done** (`forge.js`, `AscendForgePage.jsx`).
2. Privacy default + token redaction — **done** (`compute_router.py`, `forge.js`).
3. Real research — **done** (`forge_v5_runtime.run_research`).
4. Honest report + memory writeback — **done** (`forge_v5_runtime.generate_report`, new Python `/api/v5/goals/:gid/memory`, Node execute wiring).
