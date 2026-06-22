# ASCEND FORGE — AI ENGINEER AUDIT

> Inspection date: 2026-06-22 · Branch: `feat/desktop-m4-m5`
> Method: direct code inspection (routes, services, Python runtime, frontend, tests, DB, env).
> Rule followed: every claim is backed by a file/route/function, or marked as missing evidence.

---

# 1. Executive Summary

**Verdict: PARTIALLY — a strong foundation exists, but execution is fragmented and the "AI engineering engine" loop is not yet closed end-to-end.**

AscendForge is **not** a UI shell and **not** a fake prototype. There is real, substantial machinery:

- A real Node forge API (~170 routes in [backend/routes/forge.js](backend/routes/forge.js), 6.5k LOC) with projects, runs, plans, actions, approvals, snapshots/rollback, sandbox, swarm, and a persistent Python worker bridge ([run_forge.py](backend/run_forge.py)).
- A real **project indexing** layer ([runtime/core/code_indexer.py](runtime/core/code_indexer.py) + [runtime/neural_brain/api/code_index_router.py](runtime/neural_brain/api/code_index_router.py)) called over HTTP via `callCodeIndex` ([forge.js:1325](backend/routes/forge.js#L1325)).
- A real **context-compression** engine ([backend/services/forge_context_engine.js](backend/services/forge_context_engine.js): `buildContextPacket` + `compressContext(budget)`).
- A real **multi-provider model router** ([runtime/core/llm_provider_router.py](runtime/core/llm_provider_router.py), [runtime/engine/compute/compute_planner.py](runtime/engine/compute/compute_planner.py) with tiers `local_tiny → local_coder → openrouter_free → rent_gpu`).
- A real **sandbox** ([backend/infra/sandbox/executor.js](backend/infra/sandbox/executor.js): Docker + process fallback, command allowlist, cpu/mem/timeout/net limits).
- A real **Python forge lifecycle** ([runtime/forge/lifecycle/](runtime/forge/lifecycle/): spec→plan→implement→test→review→simplify→ship).
- Real **distillation/learning writeback** ([backend/services/forge_learning.js](backend/services/forge_learning.js), wired at [forge.js:4114](backend/routes/forge.js#L4114)).
- A real **swarm** scaffold ([runtime/agents/business_swarm/](runtime/agents/business_swarm/): decomposer, assignment, parallel executor, aggregator).
- Real **frontend** ([frontend/src/components/pages/AscendForgePage.jsx](frontend/src/components/pages/AscendForgePage.jsx), [forgeStore.js](frontend/src/store/forgeStore.js), [ForgeQueuePanel.jsx](frontend/src/components/forge/ForgeQueuePanel.jsx)).
- Decent **tests** (`test_ascend_forge.py`, `test_forge.py`, `test_forge_run_routes.js`, `test_forge_v5_runtime.py`, `test_business_swarm.py`, `test_model_lanes.py`).

**The brutal-honesty part — why "PARTIALLY" and not "YES":**

1. **Two disconnected forge execution paths.** The UI-facing `POST /api/forge/runs` does *single-LLM Ollama codegen* (`_callOllama`, [forge.js:1454/1551](backend/routes/forge.js#L1454)), while the richer Python lifecycle engines ([runtime/forge/lifecycle/](runtime/forge/lifecycle/)) are only reachable through the **companion** path ([runtime/companion/execution_broker.py:1286](runtime/companion/execution_broker.py#L1286)) and [forge_v5_runtime.py:272](runtime/core/forge_v5_runtime.py#L272) — not from the main run route. The two best halves don't talk.
2. **No high-level orchestrator role for Claude/OpenAI.** Until the work shipped today (MCP brain-connector + scoped service tokens + forge→AgentController dispatcher), there was no programmatic, least-privilege way for an external planner to read state and emit work. That bridge now exists but is *single-tool* (submit) — it is not yet the full plan→decompose→review loop.
3. **Remote compute is scaffolding only.** [backend/compute_fabric/index.js](backend/compute_fabric/index.js) defines `runpod`/`vastai` providers but both `enabled: false` with **no provider adapter** — provisioning is physically refused.
4. **Swarm is not used by forge.** `business_swarm` and `/api/forge/swarm` exist, but the run pipeline never routes work through the swarm.
5. **OpenAI is only reachable via OpenRouter** ([runtime/core/openrouter_client.py](runtime/core/openrouter_client.py)); there is no dedicated direct-OpenAI orchestrator adapter.

So: the *parts* of a real AI engineering engine are mostly present and mostly real, but the **connective tissue** (one run pipeline, an orchestrator bridge, a live remote-compute adapter, swarm routing for heavy work) is missing or fragmented.

---

# 2. Current Architecture Map

```
┌── FRONTEND (React/Vite, :5173 dev / served by Node in prod) ──────────────────┐
│  AscendForgePage.jsx · components/forge/* · components/pages/forge/* ·         │
│  ForgeQueuePanel.jsx · forgeStore.js · MobileForge.jsx                          │
│        │  REST /api/forge/*  +  WS (forge:* events via broadcaster)            │
└────────┼───────────────────────────────────────────────────────────────────────┘
         ▼
┌── NODE BACKEND (:8787) ───────────────────────────────────────────────────────┐
│  server.js (auth: requireAuth + NEW requireScope; tenancy.js middleware)       │
│  routes/forge.js  (~170 routes)                                                 │
│   ├ projects/files/index   → callCodeIndex() → Python code_index_router        │
│   ├ /runs (+/stream)        → buildContextPack() → _callOllama()  [single-LLM] │
│   ├ /sandbox               → runForgePython('sandbox') / infra/sandbox/executor│
│   ├ /swarm /mirofish        → core/swarm/swarm_controller.py                    │
│   ├ /submit /approve /reject→ actions.json  → [NEW] forge/dispatcher.js         │
│   └ snapshots/rollback      → forge_store / forge_v7_execution                  │
│  ascendforge/engine.js (skill recommend + agent blueprint, 306 LOC)            │
│  compute_fabric/index.js  (providers DISABLED — no adapter)                     │
│  services/: forge_store, forge_context_engine, forge_learning(_store),          │
│             forge_v7_execution, forge_workspace, forge_diff, forge_memory_graph │
│  [NEW] forge/dispatcher.js — drains approved queue → POST /api/tasks/run        │
└────────┼───────────────────────────────────────────────────────────────────────┘
         │  requestPythonJSON()  (internal service token)
         ▼
┌── PYTHON AI BACKEND (FastAPI/uvicorn, :18790) ────────────────────────────────┐
│  problem-solver-ui/server.py  → features/system_api.py                          │
│   └ POST /api/tasks/run → core/agent_controller.run_goal (Planner→Exec→Valid)  │
│  core/unified_pipeline.py (10-phase enforced pipeline)                          │
│  core/orchestrator.py  LLMClient → llm_provider_router (anthropic/ollama/       │
│                         openrouter/wavefield) + compute_planner tiers           │
│  forge/lifecycle/* (spec→plan→implement→test→review→ship)  [companion/v5 only]  │
│  core/code_indexer.py · memory_index.py · code_index_router.py                  │
│  agents/business_swarm/* · core/swarm/swarm_controller.py                       │
│  evolution/* + self_evolution/* (patch gen/validate/deploy, distillation)      │
└────────┼───────────────────────────────────────────────────────────────────────┘
         ▼
┌── LOCAL MODELS (Ollama :11434) ─── + ─── OpenRouter (cloud overflow) ──────────┐
│  compute_planner: local_tiny | local_general | local_reasoning | local_coder   │
│                   | openrouter_free | rent_gpu(blocked)                          │
└────────────────────────────────────────────────────────────────────────────────┘

State: state/*.json (deals/tasks/...) · ~/.ai-employee/state/forge/{actions,audit}.jsonl
DB: state/audit.db (audit trail) · state/forge_queue.db (forge_queue + workflow_runs)
Task lifecycle: submit→proposed → approve→approved → [dispatcher] executing → completed/failed
Approval/safety: tenancy.js (tenant gate) → requireAuth/requireScope → HITL gate (Python) → sandbox
```

---

# 3. Actual Capabilities Found

| Capability | Status | Evidence |
|---|---|---|
| project/repo ingestion | **WORKING** | `/api/forge/projects` + `/import` ([forge.js:2366/2398](backend/routes/forge.js#L2366)); files tree/read ([forge.js:2451-2470](backend/routes/forge.js#L2451)) |
| repo indexing | **PARTIAL** | `callCodeIndex('index')` → [code_indexer.py](runtime/core/code_indexer.py); requires Python up; embedding/vector quality unverified here |
| file reading | **WORKING** | `/files/read` + `safeProjectRoot` path scoping |
| architecture summarization | **PARTIAL** | `buildContextPack` + `forge_context_engine` produce tree/relevant-files; no explicit "services/routes/boundaries" structured map |
| task generation | **PARTIAL** | `/plan` ([forge.js:1641](backend/routes/forge.js#L1641)) + plan inside `/runs`; not decomposed into agent-executable task cards |
| planner agent | **PARTIAL** | Python `forge/lifecycle/planning_engine.py`; Node `/runs` does its own LLM "plan" but not via the lifecycle planner |
| coder agent | **PARTIAL** | Node `/runs` `_callOllama` codegen; Python `implementation_engine.py` exists but unwired to `/runs` |
| tester agent | **PARTIAL** | `forge/lifecycle/test_engine.py`; `/runs/:id/verify` ([forge.js:2079](backend/routes/forge.js#L2079)); run `test_results[].all_passed` |
| debugger agent | **MISSING/PARTIAL** | No dedicated debugger loop wired to runs; error forensics is ad-hoc |
| reviewer agent | **PARTIAL** | `forge/lifecycle/review_engine.py` + `consultHelperModel` advisory; not gating Node runs |
| security reviewer | **PARTIAL** | `runForgePython('security_scan')` ([forge.js:1099](backend/routes/forge.js#L1099)); separate `/security-review` skill exists |
| autopilot loop | **PARTIAL** | `/agentic-run` ([forge.js:4129](backend/routes/forge.js#L4129)); autonomy levels defined ([forge.js:1599](backend/routes/forge.js#L1599)) |
| task memory | **WORKING** | distillation → memory graph ([forge.js:4114-4123](backend/routes/forge.js#L4114)); `forge_memory_graph.js` |
| distillation/learning writeback | **WORKING** | `forge_learning.js` distill builder ([forge_learning.js:621](backend/services/forge_learning.js#L621)); `forge_distillation_created` audit |
| local model usage | **WORKING** | `_callOllama` ([forge.js:1454](backend/routes/forge.js#L1454)); compute_planner local tiers |
| API model usage | **PARTIAL** | LLMClient anthropic/openrouter ([orchestrator.py:259](runtime/core/orchestrator.py#L259)); not used as forge orchestrator |
| model routing | **WORKING** | `compute_planner.assess_compute_needs` + `llm_provider_router` + `model_lanes` |
| token compression | **PARTIAL** | `compressContext(budget)` ([forge_context_engine.js:272](backend/services/forge_context_engine.js#L272)); not applied on every API call path |
| semantic caching | **MISSING/UNKNOWN** | No semantic/prompt cache found for forge LLM calls (no evidence) |
| sandbox execution | **WORKING** | `infra/sandbox/executor.js` (Docker+process, allowlist, limits) |
| command approval | **WORKING** | HITL gate (Python) + autonomy levels + `/actions/:id/approve` |
| test execution | **PARTIAL** | sandbox can run tests; not auto-invoked in the default `/runs` path |
| error forensics | **PARTIAL** | dispatcher captures errors + audit; no compressed-failure → re-plan loop |
| frontend task control | **WORKING** | AscendForgePage + ForgeQueuePanel + forgeStore |
| progress streaming | **WORKING** | `/runs/stream` SSE ([forge.js:1824](backend/routes/forge.js#L1824)) + WS `forge:*` |
| remote compute | **BROKEN/MISSING** | `compute_fabric/index.js` providers `enabled:false`, no adapter |
| worker queue | **PARTIAL** | `forge_queue.db` + actions store + [NEW] dispatcher; no remote worker queue |
| coding swarm support | **PARTIAL** | `business_swarm/*` + `/api/forge/swarm`; not wired into runs |
| result verification | **PARTIAL** | `test_results.all_passed`, `verify_failed` status; pipeline `validate_pipeline_integrity` |
| audit logging | **WORKING** | `appendAudit` → `state/forge/audit.jsonl` + `recordAuditEvent` → `audit.db` |

---

# 4. Critical Gaps

### GAP-1 — Two disconnected forge execution paths (CRITICAL)
- **Evidence:** Node `/api/forge/runs` uses `_callOllama` for codegen ([forge.js:1551](backend/routes/forge.js#L1551)); the structured lifecycle (`planning_engine`/`implementation_engine`/`test_engine`/`review_engine`) is only invoked from [companion/execution_broker.py:1286](runtime/companion/execution_broker.py#L1286) and [forge_v5_runtime.py:272](runtime/core/forge_v5_runtime.py#L272).
- **Why it matters:** the UI-facing engine is the *weaker* one (single LLM, no test/review gating); the *stronger* lifecycle is hidden behind the companion.
- **What breaks:** runs created from the cockpit don't get plan→test→review rigor; quality is inconsistent; "verified result" promise is weak on the default path.
- **Severity:** CRITICAL · **Files:** forge.js, forge_v5_runtime.py, forge/lifecycle/*
- **Fix:** make `/api/forge/runs` delegate to the Python lifecycle (one canonical pipeline) OR explicitly demote one path. Do not maintain two.

### GAP-2 — No orchestrator bridge for Claude/OpenAI as planners (CRITICAL → partially addressed today)
- **Evidence:** Today's work added scoped service tokens + MCP connector + forge→AgentController dispatcher, but the only write tool is `forge_submit` (a single goal). No `plan`/`decompose`/`review-failures` contract.
- **Why it matters:** goal of the system is API-as-orchestrator, local-as-executor. We have the *transport* now, not the *loop*.
- **Severity:** CRITICAL · **Files:** mcp/server.js (new), forge.js, system_api.py
- **Fix:** add an orchestrator bridge (Phase 4) exposing plan/decompose/review over the same scoped-token surface.

### GAP-3 — Remote compute has no provider adapter (HIGH)
- **Evidence:** [compute_fabric/index.js:50-51](backend/compute_fabric/index.js#L50) `runpod`/`vastai` `enabled:false`; `compute_planner` lists `rent_gpu` but routing falls back ([compute_planner.py:112-119](runtime/engine/compute/compute_planner.py#L112)).
- **Why it matters:** "rent stronger machines / swarms" is impossible today.
- **Severity:** HIGH · **Files:** compute_fabric/index.js, compute_fabric/persistence.js, compute_router.py
- **Fix:** Phase 7 worker protocol + one real provider adapter, owner-gated by `COMPUTE_FABRIC_LIVE=1`.

### GAP-4 — Swarm exists but forge never uses it (HIGH)
- **Evidence:** `business_swarm/*` + `/api/forge/swarm` + `/mirofish` exist; `/runs` codegen path never calls them.
- **Why it matters:** heavy/parallel coding work can't fan out.
- **Severity:** HIGH · **Fix:** Phase 8 — route heavy run tasks through swarm coordinator after the orchestrator decides parallelism is warranted.

### GAP-5 — No semantic/prompt cache; compression not enforced on API path (MEDIUM)
- **Evidence:** `compressContext` exists but `/runs` builds context independently; no cache layer found for repeated LLM calls.
- **Why it matters:** token waste when the brain re-reads context; violates the cost goal.
- **Severity:** MEDIUM · **Fix:** Phase 3 — token budget manager + semantic cache in front of every API call.

### GAP-6 — `/metrics` 500 + broken programmatic auth (HIGH → FIXED today)
- **Evidence (now fixed):** `/metrics` missing `taskMetrics`/`startTime` deps (500); `/api/auth/token` missing `JWT_EXPIRES_IN` dep (500); `/api/auth/service-token` blocked by tenancy allowlist.
- **Status:** all three fixed and verified live this session.

---

# 5. Bugs and Broken Integrations

### BUG-1 — `GET /metrics` returned 500 *(FIXED)*
- Files: [health.js:1004](backend/routes/health.js#L1004), [server.js](backend/server.js). Cause: `taskMetrics`/`startTime` not passed into health router deps. Fix: added to `_routeDeps`. Verified: 200 + valid Prometheus.

### BUG-2 — `POST /api/auth/token` returned 500 *(FIXED)*
- Files: [auth-identity.js:132](backend/routes/auth-identity.js#L132). Cause: `JWT_EXPIRES_IN` undefined in route deps → `jwt.sign({expiresIn:undefined})` throws. Fix: passed `JWT_EXPIRES_IN` into deps. Verified: 200.

### BUG-3 — Forge approval queue was an open loop *(FIXED)*
- Files: [forge.js:4192](backend/routes/forge.js#L4192) (approve set status but nothing dispatched). Fix: [backend/forge/dispatcher.js](backend/forge/dispatcher.js) drains approved → `run_goal`. Verified: full lifecycle + audit.

### ISSUE-4 — Dual forge pipelines (see GAP-1)
- Repro: create a run via cockpit vs via companion `forge.lifecycle_plan` → different rigor. Fix strategy: unify on the Python lifecycle.

### ISSUE-5 — `requestPythonJSON` default 3s timeout vs LLM runs
- File: [server.js:1996](backend/server.js#L1996) default `timeoutMs: 3000`. The new dispatcher overrides to 180s, but other callers of `/api/tasks/run` may truncate long runs. Fix: audit all callers for explicit timeouts.

### ISSUE-6 — Remote compute providers permanently disabled (see GAP-3)
- File: compute_fabric/index.js. Repro: any rent attempt → refused. Fix: provider adapter behind owner gate.

---

# 6. Token Efficiency Audit

**Present:**
- Hierarchical context packing + per-stage relevance scoring + budget compression: [forge_context_engine.js](backend/services/forge_context_engine.js) (`buildContextPacket`, `compressContext(budget=4000)`, token-overlap scoring).
- Cost ledger / model lanes: [runtime/core/cost_ledger.py](runtime/core/cost_ledger.py), [model_lanes.py](runtime/core/model_lanes.py).
- Local-first routing: [compute_planner.py](runtime/engine/compute/compute_planner.py) prefers local tiers before `openrouter_free`/`rent_gpu`.
- Prompt inspection/tracing: [prompt_inspector.py](runtime/core/prompt_inspector.py), `distributed_tracing.py`.

**Missing / weak:**
- No **semantic cache** or **prompt-cache-aware** request shaping for forge LLM calls.
- Compression is **not enforced** on the default `/runs` path or on the new MCP/orchestrator surface.
- No **token budget manager** that caps per-task/per-run/per-day API spend at the forge layer (cost_ledger records, doesn't enforce a forge budget).
- No **dependency-aware retrieval** beyond keyword overlap (no call-graph/import-graph-driven selection).

**Proposed design (cost-correct):**
1. Claude/OpenAI receive only a **compressed context pack** (tree skeleton + file summaries + top-k relevant snippets), never raw repo.
2. A **token budget manager** gates every API call; over-budget → degrade to local model or queue.
3. A **semantic cache** keyed on (goal-hash, context-hash, model) returns prior plans/reviews.
4. Local agents do summarization/mapping/simple edits; API is reserved for plan/review/hard-debug.
5. Distillation writeback ([forge_learning.js](backend/services/forge_learning.js)) feeds the cache so repeated patterns get cheaper over time.

---

# 7. OpenAI + Claude Orchestrator Design

**Role:** strategic planner · architecture reviewer · task decomposer · error investigator · final reviewer · prompt/task generator for local agents. **Not** for: reading every file, simple edits, running tests, raw log scanning, direct shell.

**Transport already built this session:** scoped service tokens (`read` / `task-emit`) + MCP brain-connector + forge→AgentController dispatcher (approval-gated).

**Loop to implement (Phase 4):**
```
User goal
  → Forge builds compressed context pack (forge_context_engine + code_index)
  → API orchestrator (Claude/OpenAI) reviews pack → produces plan + task graph
  → tasks queued as forge_queue_items (proposed)            [MCP forge_submit / new bridge]
  → human approves (HITL)                                    [existing approval gate]
  → dispatcher → local agents execute (run_goal / lifecycle) [NEW dispatcher]
  → sandbox runs tests                                       [infra/sandbox/executor]
  → failures compressed → API orchestrator reviews ONLY compressed failure context
  → local agents fix → final verification → distillation writeback
```
**Key constraint:** orchestrator I/O always flows through the **scoped-token + approval** surface added today; it never gets shell or unscoped DB access.

---

# 8. Local Agent Task Delegation System

Build on the existing `forge_queue_item` action (already has id/label/description/status/risk/approval fields — [forge.js:4173](backend/routes/forge.js#L4173)) and `AgentController.run_goal`. Extend the action contract to a **task card**:

```
task_id · title · goal · affected_files[] · context_packet_ref · constraints ·
allowed_actions[] · forbidden_actions[] · expected_output · verification_command ·
rollback_plan · status · logs_ref · reviewer_result
```
Local agents (cheap models) handle: file summarization, route/dependency mapping, simple bug fixes, test writing, docs, UI cleanup, refactor *suggestions*, log analysis, security checks, regression checks. **High-risk → approval required** (reuse autonomy levels [forge.js:1599](backend/routes/forge.js#L1599) + HITL gate). Reuse `compute_planner` to pick the cheapest capable model per task.

---

# 9. Remote Compute Architecture

Current state: scaffolding only ([compute_fabric/index.js](backend/compute_fabric/index.js), providers disabled). Design a real **worker protocol** (Phase 7):

- Worker **registration** (pairing token) + **capability report** (GPU/VRAM/RAM/CPU, installed models).
- **Health checks** + heartbeat + disconnect recovery.
- **Secure job dispatch** (signed jobs, scoped secrets, never raw `.env`).
- **Sandboxed execution** on the worker (mirror `infra/sandbox/executor`).
- **Artifact** upload/download + **job logs** streaming + **timeout**.
- **Cost tracking** (extend `cost_ledger`) + **trust levels** + **queue** + **fallback to local**.
- **Approval gates** for dangerous jobs; owner-gated by `COMPUTE_FABRIC_LIVE=1` + provider creds.

Lifecycle: add creds/pairing → worker installs remote agent → registers → reports caps → system assigns compatible jobs → sandboxed exec → streams logs → returns artifacts → system verifies → stored in audit/task memory. **Not** "SSH and hope" — a real protocol with `remote_worker_registry` + `remote_job_dispatcher`.

---

# 10. Security Model

**Existing controls (verified):** JWT auth ([server.js:317](backend/server.js#L317)); **NEW scoped tokens + `requireScope`** (deny-by-default); tenancy isolation ([tenancy.js](backend/tenancy.js)); HITL gate; sandbox allowlist + limits; audit to `audit.db` + jsonl; internal service token for Node→Python; secrets via env/secret broker; `METRICS_TOKEN` gate.

**Action classification:**
- **SAFE:** read files, summarize code, inspect package files, static analysis (no net).
- **CAUTION (require review):** install packages, modify source, run tests, call external APIs, start local servers.
- **DANGEROUS (require explicit approval):** delete/overwrite files, modify system config, sudo/admin, upload secrets, change auth, expose ports, deploy, run unknown scripts.
- **BLOCKED by default:** destructive cmds w/o approval, credential exfiltration, disabling security, unsafe remote shell, touching unrelated user files.

**Gaps to close:** treat repo/file content as untrusted in orchestrator prompts (prompt-injection guard); per-scope rate limits on the MCP write surface; redact failure context before sending to APIs; remote-worker trust levels (Phase 7).

---

# 11. Implementation Plan

## Phase 1 — Truth Audit & Broken-Flow Fixes
- **Goal:** clean baseline; no 500s; closed approval loop. **Status: largely DONE this session.**
- **Files:** server.js, health.js, auth-identity.js, tenancy.js, forge.js, backend/forge/dispatcher.js, mcp/*.
- **Tasks:** ✅ /metrics fix · ✅ /api/auth/token fix · ✅ scoped service tokens + requireScope · ✅ dispatcher · ✅ MCP connector. Remaining: audit `requestPythonJSON` timeouts (ISSUE-5).
- **Verification:** ✅ live curl matrix + dispatch + MCP loop (this session). `npm test` for regression.
- **Risks:** low (additive, reversible).

## Phase 2 — Real Project Understanding Layer
- **Goal:** one structured project map (services/routes/boundaries/data stores/model flow) from real code.
- **Files:** runtime/core/code_indexer.py, code_index_router.py, forge_context_engine.js, forge.js (`/index`, `buildContextPack`).
- **Tasks:** add structured architecture extraction (routes, imports/call graph, frontend/backend boundary) on top of existing index; persist as a reusable project map.
- **Verification:** index this repo; assert the map lists `/api/forge/*`, Node/Python boundary, state files.
- **Risks:** index quality depends on Python up; large repos cost — cap via budget.

## Phase 3 — Context Compression & Token Efficiency
- **Goal:** every API call uses compressed context + budget + cache.
- **Files:** forge_context_engine.js, cost_ledger.py, NEW `services/token_budget_manager.js`, NEW `services/prompt_cache_manager.js`.
- **Tasks:** enforce `compressContext` on all API paths; add semantic cache; add per-task/run/day budget enforcement (extend cost_ledger).
- **Verification:** repeated goal hits cache (0 API tokens); over-budget degrades to local.
- **Risks:** cache invalidation correctness.

## Phase 4 — OpenAI/Claude Orchestrator Bridge
- **Goal:** API acts as planner/decomposer/reviewer over the scoped-token surface.
- **Files:** mcp/server.js (extend), forge.js (orchestrator routes), system_api.py, NEW `services/orchestrator_bridge.js`.
- **Tasks:** add `plan`, `decompose`, `review_failures` tools/routes (read compressed context, emit task graph, review only compressed failures); keep approval-gated.
- **Verification:** goal → plan → task cards queued → approve → execute → review loop end-to-end.
- **Risks:** prompt injection from repo content — add guard.

## Phase 5 — Local Agent Task Graph
- **Goal:** task cards executable by cheap local agents with verification + rollback.
- **Files:** forge.js (extend action contract), agent_controller.py, compute_planner.py.
- **Tasks:** extend `forge_queue_item` → task card (Section 8); route each card to cheapest capable model; capture reviewer_result.
- **Verification:** a simple bug-fix card runs locally, tests pass, reviewer signs off.
- **Risks:** weak-model quality — gate high-risk to approval.

## Phase 6 — Sandbox Execution & Result Verification
- **Goal:** every code change is tested in sandbox; no fake-done.
- **Files:** infra/sandbox/executor.js, forge.js (`/runs/:id/verify`), NEW `services/result_verifier.js`.
- **Tasks:** auto-run verification_command in sandbox after each card; require `all_passed` before `completed`.
- **Verification:** failing tests block completion; status `verify_failed`.
- **Risks:** sandbox coverage (Docker vs process fallback).

## Phase 7 — Remote Compute Worker Protocol
- **Goal:** real worker registration/dispatch (Section 9), owner-gated.
- **Files:** compute_fabric/index.js, persistence.js, compute_router.py, NEW `services/remote_worker_registry.js`, NEW `services/remote_job_dispatcher.js`, NEW `routes/remote_compute.js`.
- **Tasks:** one provider adapter; pairing/registration; capability report; sandboxed remote exec; artifacts; cost; fallback to local.
- **Verification:** register a worker (or mock), dispatch a job, verify artifact + audit.
- **Risks:** HIGH — secrets handling, trust, network. Behind `COMPUTE_FABRIC_LIVE=1`.

## Phase 8 — Coding Swarm Layer
- **Goal:** heavy/parallel run tasks fan out via swarm.
- **Files:** business_swarm/*, core/swarm/swarm_controller.py, forge.js (`/swarm`), NEW `services/swarm_coordinator.js`.
- **Tasks:** orchestrator decides parallelism → swarm decomposes/executes/aggregates → results verified.
- **Verification:** a multi-file refactor runs across N agents and aggregates.
- **Risks:** coordination/merge conflicts.

## Phase 9 — UI Integration
- **Goal:** cockpit panels for orchestration, task graph, remote compute.
- **Files:** AscendForgePage.jsx, components/forge/*, forgeStore.js, NEW orchestration/task-graph/remote-compute panels.
- **Tasks:** surface plan→tasks→approve→execute→verify; show budgets, model routing, worker status.
- **Verification:** drive the full loop from the UI.
- **Risks:** keep UI a view over backend truth (no frontend-only state).

## Phase 10 — Enterprise Hardening
- **Goal:** rate limits, budgets, prompt-injection guards, trust levels, full audit, rollback everywhere.
- **Files:** server.js, tenancy.js, audit service, all new services.
- **Tasks:** per-scope rate limits; failure-context redaction; injection guards; remote trust; circuit breakers (extend `reliabilityState`).
- **Verification:** abuse tests, injection tests, tenant-isolation tests, regression.
- **Risks:** completeness.

---

# 12. Exact Tasks for Local Agents

```
TASK-ID: AF-AUDIT-01
Title: Map all /api/forge/* routes + auth level
Agent type: route-checker
Purpose: produce a route table (path, method, auth/scope) for the audit map
Input files: backend/routes/forge.js, backend/routes/index.js
Output files: docs/forge_route_map.md
Allowed actions: read, summarize
Forbidden actions: edit code, run shell with side effects
Context needed: forge.js route registrations
Verification: count matches grep of router.(get|post|...)
Reviewer: backend-service-checker
```
```
TASK-ID: AF-AUDIT-02
Title: Confirm Node /runs vs Python lifecycle disconnection
Agent type: backend-service-checker
Purpose: document the dual-pipeline gap (GAP-1) with call traces
Input files: forge.js, runtime/forge/lifecycle/*, forge_v5_runtime.py, companion/execution_broker.py
Output files: docs/forge_pipeline_gap.md
Allowed actions: read, summarize
Forbidden actions: edit
Verification: cite exact call sites
Reviewer: repo-mapper
```
```
TASK-ID: AF-CTX-03
Title: Enforce compressContext on the /runs context path
Agent type: context-compressor
Purpose: ensure budget compression applied before any LLM call
Input files: forge.js (buildContextPack), forge_context_engine.js
Output files: forge.js (patch)
Allowed actions: read, propose patch
Forbidden actions: change auth, change schemas
Verification: context tokens <= budget; unit test
Reviewer: code-reviewer (high)
```
```
TASK-ID: AF-CACHE-04
Title: Add semantic prompt cache manager (skeleton + integration point)
Agent type: api-bridge-designer
Purpose: avoid repeated identical API calls
Input files: cost_ledger.py, orchestrator.py
Output files: services/prompt_cache_manager.js (new), integration stub
Allowed actions: create new service file, wire read path
Forbidden actions: enable by default without review
Verification: cache hit returns prior result; miss falls through
Reviewer: reality-checker
```
```
TASK-ID: AF-REMOTE-05
Title: Design remote worker registry + job contract (no live exec)
Agent type: remote-worker-designer
Purpose: spec the Phase 7 protocol before code
Input files: compute_fabric/index.js, persistence.js, compute_router.py
Output files: docs/remote_worker_protocol.md
Allowed actions: read, write doc
Forbidden actions: provision compute, touch creds
Verification: doc covers registration→caps→dispatch→sandbox→artifacts→verify
Reviewer: security-auditor
```
```
TASK-ID: AF-SEC-06
Title: Add prompt-injection guard for repo content in orchestrator prompts
Agent type: security-auditor
Purpose: treat file/repo content as untrusted data, not instructions
Input files: orchestrator bridge (Phase 4), forge_context_engine.js
Output files: services/orchestrator_bridge.js (guard), tests
Allowed actions: propose patch + tests
Forbidden actions: weaken existing auth
Verification: injection test suite passes
Reviewer: reality-checker
```
```
TASK-ID: AF-TEST-07
Title: Auto-run verification_command in sandbox after each task card
Agent type: sandbox-verifier
Purpose: enforce no fake-done
Input files: infra/sandbox/executor.js, forge.js (/runs/:id/verify)
Output files: services/result_verifier.js (new) + wiring
Allowed actions: create service, wire verify path
Forbidden actions: bypass sandbox
Verification: failing tests block 'completed'
Reviewer: code-reviewer (high)
```

---

# 13. Files That Should Exist (but do not)

Only the connective tissue — existing equivalents are reused, not duplicated:

| Proposed file | Why (no existing equivalent) |
|---|---|
| `backend/services/orchestrator_bridge.js` | Phase 4 plan/decompose/review loop (today only single `forge_submit`) |
| `backend/services/token_budget_manager.js` | enforce per-task/run/day API budget (cost_ledger only records) |
| `backend/services/prompt_cache_manager.js` | no semantic/prompt cache exists |
| `backend/services/result_verifier.js` | centralize "no fake-done" verification (logic is scattered) |
| `backend/services/remote_worker_registry.js` | Phase 7 (compute_fabric has no registry) |
| `backend/services/remote_job_dispatcher.js` | Phase 7 dispatch (no adapter today) |
| `backend/services/swarm_coordinator.js` | bridge forge runs → business_swarm (not wired) |
| `backend/routes/orchestrator.js` | HTTP surface for the orchestrator bridge |
| `backend/routes/remote_compute.js` | HTTP surface for worker registration/dispatch |
| `frontend …/OrchestrationPanel.jsx`, `TaskGraphPanel.jsx`, `RemoteComputePanel.jsx` | Phase 9 UI |

**Deliberately NOT proposed (already exist — reuse):** context pack builder → `forge_context_engine.js`; model capability router → `compute_planner.py` + `llm_provider_router.py`; sandbox runner → `infra/sandbox/executor.js`; api usage ledger → `cost_ledger.py`; local agent queue → `forge_queue_item` actions + new `dispatcher.js`; project indexer → `code_indexer.py`.

---

# 14. Final Verdict

**PARTIALLY — the core foundation exists but execution is weak/fragmented.**

The components of a real AI engineering engine are largely present and largely real: project indexing, context compression, multi-provider model routing, a sandbox, a Python lifecycle, distillation, a swarm scaffold, a full UI, and tests. What's missing is the **connective tissue** that turns parts into a system.

**What must be fixed first (in order):**
1. **Unify the forge execution path (GAP-1)** — make the cockpit `/runs` use the Python lifecycle (plan→implement→test→review) instead of single-LLM Ollama codegen. Without this, "verified results" are not guaranteed on the default path.
2. **Build the orchestrator bridge (GAP-2, Phase 4)** on top of the scoped-token + dispatcher surface shipped today, so Claude/OpenAI plan/decompose/review while local agents execute.
3. **Enforce context compression + token budget + cache (Phase 3)** so the API-as-orchestrator design is cost-correct.
4. **Then** remote compute (Phase 7) and swarm routing (Phase 8) for scale.

Today's session closed the highest-leverage prerequisites (clean baseline, programmatic least-privilege auth, and the approval→execution loop). The next highest-leverage move is **GAP-1 (unify the pipeline)**, then **Phase 4 (orchestrator bridge)**.
