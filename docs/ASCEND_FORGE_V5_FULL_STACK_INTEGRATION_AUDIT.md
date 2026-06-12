# Ascend Forge V5 — Full Stack Integration Audit

## 1. Quantum-Style Reasoning

- `runtime/core/quantum/` — full QCE engine: StrategySuperposer, AmplitudeRouter, IntentSuperposer, OracleScorer, ReflectionEngine, AmplitudeAmplifier
- Connected to: `agent_controller.py`, `economy_engine.py`, `decision_engine.py`, `swarm_engine.py`, `llm_provider_router.py`
- Exposed via: `/api/quantum/plan`, `/api/quantum/route`, `/api/quantum/search`, `/api/quantum/feedback`, `/api/quantum/stats`
- V5 connection: `forge_reasoning_orchestrator.py` wraps `get_qce()` for brief → research → goals phases
- All V5 Node→Python calls use `callPythonV5` / `getPythonV5` helpers (forge.js lines 1169–1175)

## 2. Model Routing / Local LLM

- `runtime/core/llm_provider_router.py` + `AmplitudeRouter` for per-task model selection
- Ollama on port 11434; Claude/OpenAI via env-keyed API keys; OpenRouter as overflow
- Node exposes: `/api/models/routing`, `/api/ollama/status`, `/api/ollama/models`
- V5: `GET /api/forge/v5/models` proxies to Python `/api/v5/models/health`; fallback returns honest `available:false` per provider when Python is down

## 3. External API

- Providers: Anthropic (`ANTHROPIC_API_KEY`), OpenAI (`OPENAI_API_KEY`), OpenRouter (via `llm_provider_router.py`)
- Rate-limiting gateway: `backend/gateway/rate_limiter.js`
- Policy: local-first; external only if key present and privacy policy allows
- V5: `compute_router.py` checks key presence before routing to `external_api`; `GET /api/forge/v5/compute/backends` reflects key availability in Node fallback

## 4. Remote Compute

- No active remote compute system exists in codebase
- `REMOTE_COMPUTE_HOST` env var defined in `.env.example`
- V5: `compute_router.py` checks `REMOTE_COMPUTE_HOST`; returns honest `unavailable` if unset
- Default: `local_cpu` always available; all other backends degrade gracefully

## 5. Sandbox / Testing

- Existing: `POST /api/forge/runs/:id/verify` (runs `verification_commands`), `POST /api/forge/sandbox` (Python sandbox), `POST /api/doctor/run` (security scan), `backend/infra/sandbox/executor.js`
- V5 quality gate (`/api/v5/quality`) calls these for `functional_correctness` and `safety` dimensions
- Dimensions `efficiency`, `usability`, `reliability` marked `skipped` until full sandbox integration is wired
- Quality gate results persisted via `forgeRunStore.upsertV5QualityGate()` and broadcast as `forge:v5_quality_gate_completed`

## 6. Memory / Distillation

- `runtime/memory/memory_router.py` — 3-layer: short-term cache + vector store + Neo4j brain graph; `store()` + `retrieve()` production-ready
- Distillation: `backend/services/forge_learning_store.js` captures run lessons per project
- V5: `write_memory_lesson()` appends QCE reasoning + compute metadata on every goal completion
- Artifacts (brief, research_pack, reasoning, report) stored via `_upsertV5Artifact()` and retrievable without re-running Python

## 7. Agent Systems

- 53 conforming BaseAgent subclasses; 86 wrapped via `runtime/agents/compat.py`
- 113 agents registered in `runtime/config/agent_capabilities.json`
- V5 goal execution calls `_executeAgenticRun()` → `AgentController.run_goal()` as primary entry point
- Goal loop: `POST /v5/projects/:id/goals/:gid/execute` (project-scoped) + `POST /v5/goals/:gid/execute` (standalone by goal ID) both available

## 8. Current Forge Project Flow Gap

- Existing Forge: project → context pack → AI plan → actions → HITL approval → verify → apply
- Missing before V5: Project Brief, Research Pack, end-state Goals, Goal Loop, Quality Gate, Project Report
- V5 adds: `forge_v5_runtime.py` orchestrates the full chain; forge runs remain the execution unit per goal
- `/v5/projects/start` runs the full chain in one call; `POST /v5/projects/:id/research` and `POST /v5/projects/:id/goals/plan` allow incremental re-runs of individual phases

## 9. Files Changed in V5

**New Python:**
- `runtime/core/forge_v5_runtime.py` — orchestrates brief → research → goals → quality chain
- `runtime/core/forge_reasoning_orchestrator.py` — wraps QCE for V5 phases
- `runtime/core/compute_router.py` — routes goals to local_cpu / local_gpu / remote / external_api
- `runtime/agents/compat.py` — BaseAgent compatibility wrapper for legacy agents

**Extended:**
- `runtime/agents/problem-solver-ui/server.py` — added `/api/v5/brief`, `/api/v5/research`, `/api/v5/goals`, `/api/v5/quality`, `/api/v5/compute/backends`, `/api/v5/models/health`
- `backend/routes/forge.js` — added `POST /v5/projects/:id/research`, `POST /v5/projects/:id/goals/plan`, `POST /v5/goals/:gid/execute` (standalone)
- `backend/routes/index.js` — V5 route registry expanded to 13 entries (was 10)
- `runtime/agents/base.py` — added `wrap` classmethod for compat layer

**New state dirs:**
- `~/.ai-employee/state/forge/briefs/`
- `~/.ai-employee/state/forge/research_packs/`
- `~/.ai-employee/state/forge/goals/`
- `~/.ai-employee/state/forge/quality_gates/`
- `~/.ai-employee/state/forge/reports/`
