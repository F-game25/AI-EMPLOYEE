# SYSTEM.md — AETERNUS NEXUS

> **AI Operating System for autonomous business operations.**
> Single dashboard, multi-tenant, **121 agent directories / 89 registered agents**, real-world execution.
> Read this file **before touching the codebase**. It exists so other AIs (and humans) get the full mental model without grepping their way to it.

**Owner:** larsfluks@gmail.com
**Current branch:** `wavefield-routing` (main: `main`)
**Date of this snapshot:** 2026-05-16

---

## 🗞 LAST UPDATE — what changed most recently (read this first)

**2026-05-16 — Phase C UI Rebuild closed out.** If you are picking up this codebase, here is the shortest version of what you need to know:

1. **Pages on disk = pages in sidebar.** 23 legacy pages were physically deleted (see §25). `frontend/src/components/pages/` now contains exactly 16 page pairs (`.jsx` + `.css`) — every one is wired in `Dashboard.jsx` and reachable from the sidebar.
2. **Security tabs are one component.** All four sidebar items (`policies`, `permissions`, `sandboxes`, `audit`) route to `SecurityPanel.jsx`. It reads `useAppStore(s => s.activeSection)` and switches its internal tab. Do not split it back into four files.
3. **CommandDock is always mounted.** It lives at the bottom of `Dashboard.jsx` and is no longer conditional on the active page. The voice pill dispatches `nx:voice-open` which `VoiceModal` (in `components/ui/VoiceModal.jsx`) listens for.
4. **Three new feature blocks live inside existing pages** (not separate routes — search for them):
   - `DiagnosticsPanel` + `EmergencyPanel` inside `SystemHealthPage.jsx` (replaces the old DoctorPage + ControlCenterPage).
   - `PromptInspector` component at the bottom of `CognitionPage.jsx` (replaces PromptInspectorPage; uses live `useCognitiveStore.modelCalls`, falls back to demo data when empty).
   - `drawer-training` block in `AgentsPage.jsx` `DetailDrawer` — `CHECK` / `REINFORCE` / `ADVANCE LADDER` buttons hit `/api/agents/{id}/{grade|reinforce|ladder/advance}` (replaces TrainingPage + LearningLadderPage).
5. **NeuralNetworkPage seeds a 12-node demo graph** when the backend snapshot is empty (see `useEffect` in [NeuralNetworkPage.jsx:118](frontend/src/components/pages/NeuralNetworkPage.jsx#L118)) so the visualisation is informative on a cold system.
6. **Build is clean** — 1123 modules, ~600ms. The 723KB `vendor-three-core` chunk is known and tolerated (only loaded on `neural-graph`).

If you're new to this repo, jump to **§30 HOW TO ONBOARD AS A NEW AI** at the bottom of this file, then come back here.

---

## TABLE OF CONTENTS

1. [What this is](#1-what-this-is)
2. [Three runtimes](#2-three-runtimes)
3. [The strict 3-layer model](#3-the-strict-3-layer-model)
4. [The 10-phase unified pipeline](#4-the-10-phase-unified-pipeline)
5. [Core runtime modules](#5-core-runtime-modules)
6. [Task contracts (TaskNode / TaskGraph / ValidationResult)](#6-task-contracts)
7. [The agent catalog — all 89 agents](#7-the-agent-catalog)
8. [Skills library](#8-skills-library)
9. [Persistence layer](#9-persistence-layer)
10. [Multi-tenancy](#10-multi-tenancy)
11. [Security & auth](#11-security--auth)
12. [Observability](#12-observability)
13. [Environment variables](#13-environment-variables)
14. [Commands & workflows](#14-commands--workflows)
15. [Node.js backend — all 142 routes](#15-nodejs-backend--all-142-routes)
16. [Python AI backend — auth, chat, agents, custom skills](#16-python-ai-backend)
17. [WebSocket event taxonomy (full payloads)](#17-websocket-event-taxonomy)
18. [Frontend stack & design system](#18-frontend-stack--design-system)
19. [Zustand stores — full field-by-field](#19-zustand-stores)
20. [Hooks](#20-hooks)
21. [Nexus-UI primitive library](#21-nexus-ui-primitive-library)
22. [The 20 pages — what each does](#22-the-20-pages)
23. [Dashboard.jsx — routing & layout shell](#23-dashboardjsx)
24. [The RoboticEye avatar](#24-the-roboticeye-avatar)
25. [What was removed / consolidated](#25-what-was-removed--consolidated)
26. [Performance & chunk splitting](#26-performance--chunk-splitting)
27. [Working on this codebase — do / don't](#27-working-on-this-codebase)
28. [Project state — 2026-05-16](#28-project-state)
29. [File-by-file map of critical files](#29-file-by-file-map)
30. [How to onboard as a new AI](#30-how-to-onboard-as-a-new-ai)

---

## 1. WHAT THIS IS

A production-grade **AI Operating System** with three jobs:

1. **Run a workforce of 89 specialised AI agents** (lead-hunter, sales-closer, content-master, hr-manager, social-guru, etc.) that produce **real-world outcomes** — sent emails, closed deals, generated content, scraped data, signed contracts.
2. **Orchestrate skills into workflows** through a strict 3-layer model (Orchestrator → Skills → Tools). The LLM **never** calls tools directly.
3. **Present a single cinematic dashboard** (AETERNUS NEXUS aesthetic: dark gold-on-black, monospace, hex frames, scanlines) where **one human operator** observes and steers the entire system.

The user is building this as a **one-person AI company**. Every architectural decision optimises for real-world business outcomes per token spent, not technical novelty. Treat this as a production system, not a demo.

**North Star:** Convert intent → structured workflow → real-world outcome.

**Invalid outputs:** pure explanations, theoretical responses without execution, unactionable suggestions.
**Valid outputs:** completed workflows, generated documents, sent emails, updated databases, executed business actions, delivered reports, triggered external systems.

---

## 2. THREE RUNTIMES

```
┌──────────────────┐     HTTP      ┌──────────────────┐    HTTP+SSE    ┌──────────────────┐
│   React Frontend │ ◄──────────► │  Node.js Backend │ ◄────────────► │  Python AI       │
│  (Vite, :5173)   │   WebSocket   │  (Express :8787) │                │  (FastAPI :18790)│
│                  │ ◄──────────────────────────────► │                │                  │
└──────────────────┘                └──────────────────┘                └──────────────────┘
                                            │                                    │
                                            ▼                                    ▼
                                    ┌───────────────┐                  ┌──────────────────┐
                                    │ state/*.json  │                  │ Agent catalog    │
                                    │ audit.db      │                  │ Memory router    │
                                    │ bus.jsonl     │                  │ Skill library    │
                                    │ llm_calls.    │                  │ HITL gate        │
                                    │   jsonl       │                  │ Money mode       │
                                    └───────────────┘                  └──────────────────┘
```

### Node.js backend (`backend/server.js`, port 8787)

Express + WebSocket server. ~4000 lines, 142 HTTP routes.

**Owns:**
- All `/api/*` HTTP routes (44 of 142 wrapped in `requireAuth`)
- WebSocket bus — fans broadcasts to all connected dashboards
- Proxies `/api/chat` to Python AI on port 18790
- Serves the built React frontend from `frontend/dist/`
- `backend/agents/index.js` — loads catalog from `runtime/config/agent_capabilities.json`
- `backend/orchestrator/` — task routing
- `backend/bridges/python_metrics_bridge.js` — bridges Python SSE → WS broadcasts
- `backend/security/` — secrets vault, API gateway protector, anomaly responder
- `backend/tenancy.js` — extracts tenant from JWT on every request

### Python AI backend (`runtime/agents/problem-solver-ui/server.py`, port 18790)

FastAPI + uvicorn. **20,000+ lines** in one file (yes, really — it's the entry point + auth + chat + agent registry + custom skills + schedules + improvements + workers all consolidated).

Runs the actual LLM pipeline. Without this process, chat falls back to keyword-matched placeholder replies in the Node backend.

Bridged to Node via SSE — Python emits events on its own SSE channel (`/api/events`), Node bridges them to the WS bus, frontend stores update.

### React frontend (`frontend/`)

Vite-bundled SPA. Built into `frontend/dist/` by `start.sh`. During dev: Vite dev server on `:5173` proxies API calls to Node on `:8787`.

**Stack:**
- React 18 + Vite (rolldown, advancedChunks/codeSplitting)
- **Zustand** for state (no Redux, no Recoil)
- **Pure SVG** for all charts (no chart library)
- **CSS custom properties** for design tokens
- **Framer Motion** for page transitions
- **Three.js** only inside `NeuralNetworkPage` for 3D brain graph (lazy-chunked, ~330KB)

---

## 3. THE STRICT 3-LAYER MODEL

This is **non-negotiable**. Every change must respect it.

```
USER INTENT
    │
    ▼
ORCHESTRATOR ──────────► selects skills, plans workflows, never calls tools
    │
    ▼
SKILLS ─────────────────► structured business capabilities, chain tools, validate output
    │
    ▼
TOOLS ──────────────────► atomic actions: search, browse, DB query, send email, LLM inference
```

### Orchestrator

`runtime/core/agent_controller.py` (`AgentController` class). Planner → Executor → Validator loop. Called by `/api/tasks/run`.

**Orchestrator rules:**
- Never hardcode workflows
- Never execute tools directly
- Never bypass skills
- Always select highest-fit skill
- Optimize for outcome success probability
- Minimize cost and latency
- Maintain global context memory

The orchestrator is a **routing + planning system, not an executor**.

### Skills

`runtime/skills/catalog.py` + `runtime/skills/library.py`. 147 skills backed by `runtime/config/skills_library.json`.

> A **skill** is a reusable, versioned, domain-specific workflow that combines multiple tools to achieve a real-world outcome.

**Examples:** Lead Generation, Contract Analysis, Market Research, Appointment Scheduling, Document Intelligence, Customer Support Automation.

**Every skill must:**
- Encapsulate a complete business capability
- Define a deterministic or semi-deterministic workflow
- Use a predefined set of tools
- Handle internal logic, retries, branching
- Validate outputs before returning
- Produce structured artifacts
- Be independently testable

Skills are **products, not utilities**.

### Tools

Atomic primitives. Web search, browser automation, DB query, email send, LLM inference, file processing, API request.

**Every tool must:**
- Perform a single atomic action
- Be deterministic where possible
- Have strict input/output schemas
- Contain **no** business logic
- **Not** orchestrate workflows

---

## 4. THE 10-PHASE UNIFIED PIPELINE

`runtime/core/unified_pipeline.py` — all user input flows through this. No exceptions.

```
Input
  1. retrieve_relevant_nodes      memory retrieval (vector + episodic)
  2. build_context                 assemble LLM context window
  3. classify_decision             intent classification → which skill
  4. call_llm                      LLM inference via runtime/engine/api.py
  5. validate_tasks                schema check on output (TaskNode/TaskGraph)
  6. execute_tasks                 dispatch to skills, skills call tools
  7. format_response               render structured output for UI
  8. update_graph                  memory write-back to brain store
  9. monitor_and_improve           emit signal for self-evolution
  10. validate_pipeline_integrity  post-condition check
Output
```

Set `STRICT_PIPELINE=1` in CI/staging to disable graceful fallbacks and surface real failures.

---

## 5. CORE RUNTIME MODULES

| Module | Purpose |
|---|---|
| `runtime/core/agent_controller.py` | `AgentController` — central orchestrator (Planner→Executor→Validator). Called by `/api/tasks/run`. |
| `runtime/core/contracts.py` | `TaskGraph`, `TaskNode`, `ValidationResult` dataclasses. **The normalized task contract.** |
| `runtime/core/orchestrator.py` | `LLMClient` wrapping Anthropic/Ollama with retry + JSONL call logging. |
| `runtime/core/unified_pipeline.py` | 10-phase pipeline (above). |
| `runtime/core/bus.py` | `SimpleMessageBus` — in-process pub/sub, persists to `state/bus.jsonl`. Channels: `tasks`, `results`, `notifications`, `logs`. |
| `runtime/core/hitl_gate.py` | Human-In-The-Loop gate. Blocks consequential actions by high-risk agents (`hr-manager`, `recruiter`, `lead-scorer`, `lead-hunter-elite`, `qualification-agent`, `data-analyst`) until human approves via dashboard. Timeout: 15min auto-reject for P0, 4hr window for P1. Gate state persisted to SQLite. |
| `runtime/core/money_mode.py` | Three monetization pipelines: `content_publish_track`, `data_scrape_filter_store`, `outreach_response_conversion`. |
| `runtime/core/self_evolution/` | `evolution_controller.py`, `patch_generator.py`, `patch_validator.py`, `safe_deployer.py`. Controlled by `EVOLUTION_MODE` (AUTO/SAFE/OFF). Patch candidates validated by syntax checker, test runner, diff-size limit (max 200 LOC per cycle) before promotion. |
| `runtime/core/tenancy.py` | `TenantManager` — lifecycle, directory structure, request-scoped context. |
| `runtime/core/tenant_middleware.py` | FastAPI middleware — extracts tenant from JWT. |
| `runtime/core/file_lock.py` | `fcntl`-based exclusive locks. Tenant-aware reads/writes via `_tenant_data` structure. |
| `runtime/engine/api.py` | Internal LLM engine public surface: `process_input`, `generate`, `embed`, `memory_store`, `memory_retrieve`. **All agent LLM calls go through here.** |
| `runtime/memory/memory_router.py` | Routes memory ops to vector store, short-term cache, strategy store. |
| `runtime/memory/` (subdirs) | `vector_store/`, `short_term_cache/`, `strategy_store/`, `episodic_memory/`. |
| `runtime/neural_brain/utils/event_bus.py` | Event publish/subscribe. Emits all `nb:*` and `brain:*` events. |
| `runtime/neural_brain/workflows/nodes.py` | Reasoning step emissions (`nb:reasoning_step`). |
| `runtime/neural_brain/memory/neural_memory_manager.py` | Emits `nb:memory_write`. |
| `runtime/neural_brain/telemetry/sanitizer.py` | Sanitises events before WS broadcast (PII scrubbing). |
| `runtime/neural_brain/telemetry/local_analyzer.py` | Local pattern detection on event stream. |
| `runtime/neural_brain/security/blacklight_engine.py` | Anomaly detection in reasoning patterns. |
| `runtime/skills/catalog.py` | Skill registry — versioned, discoverable, replaceable. |
| `runtime/skills/library.py` | Loads all 147 skills from `skills_library.json`. |
| `runtime/core/observability/metrics_collector.py` | 1-second tick, rolling 3600 snapshots. Exposes `ai_employee_*` Prometheus metrics. |
| `runtime/core/observability/event_stream.py` | In-process pub/sub with JSONL persistence. |

`runtime/` is inserted into `sys.path` by `main.py`, so imports like `from core.agent_controller import AgentController` work without packaging.

---

## 6. TASK CONTRACTS

`runtime/core/contracts.py` defines the **only** shapes that pass between orchestrator → skills → tools.

### TaskNode (single task)

```python
@dataclass
class TaskNode:
    task_id: str
    skill: str                                  # which skill executes this
    input: dict[str, Any]
    expected_output: dict[str, Any] = {}
    dependencies: list[str] = []                # other task_ids that must complete first
    allowed_actions: list[str] = ["skill_dispatch"]
    status: Literal["pending","running","success","failed"] = "pending"
    output: dict[str, Any] = {}
    error: str = ""
    attempts: int = 0
    score: float = 0.0                          # validator score 0..1
    passed: bool = False                        # validator binary
    started_at: str = ""
    finished_at: str = ""
```

### TaskGraph (workflow)

```python
@dataclass
class TaskGraph:
    run_id: str
    goal: str
    tasks: list[TaskNode]

    def validate_no_cycles(self) -> None:       # raises ValueError on cycle
    def to_contract(self) -> dict[str, Any]
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    task_id: str
    passed: bool
    score: float
    details: dict[str, Any] = {}
```

**Skills receive a `TaskNode.input`, return a `dict` written to `TaskNode.output`. Validator wraps with `ValidationResult`. Orchestrator advances the graph.**

---

## 7. THE AGENT CATALOG

121 agent directories on disk; **89 registered in `runtime/config/agent_capabilities.json`**. The delta is in-progress / staging agents not yet active.

### Directory structure

```
runtime/agents/<name>/
  <name>.py        # Subclasses BaseAgent (runtime/agents/base.py)
  run.sh           # Sources ~/.ai-employee/.env + runtime/config/<name>.env, execs the module
  requirements.txt # Python deps
```

### Loaded by

`backend/agents/index.js` on Node startup. Behavior templates in `runtime/config/agent_behavior_templates.json`.

### Operating modes

User chooses at first start (interactive prompt) or via `/api/mode`:
- **Starter** — 3 agents
- **Business** — 15 agents
- **Power** — 56+ agents (default for power users)

### The 89 registered agents (by domain)

**Sales & Lead Gen** (15): `lead-hunter`, `lead-hunter-elite`, `lead-generator`, `lead-intelligence`, `lead-crm`, `qualification-agent`, `cold-outreach-assassin`, `sales-closer-pro`, `web-sales`, `discovery`, `follow-up-agent`, `appointment-setter`, `meeting-intelligence`, `crm-pipeline`, `referral-rocket`

**Marketing & Content** (18): `content-master`, `content-calendar`, `social-guru`, `social-media-manager`, `social-poster`, `social-scheduler`, `linkedin-growth-hacker`, `seo-agent`, `email-marketer`, `email-marketing`, `email-ninja`, `email-warmup`, `newsletter-bot`, `creator-agency`, `personal-brand`, `brand-strategist`, `partnership-matchmaker`, `creative-studio`

**Ops & Project Mgmt** (10): `task-orchestrator`, `team-management`, `project-manager`, `company-manager`, `company-builder`, `org-chart`, `hr-manager`, `recruiter`, `ceo-briefing`, `status-reporter`

**Finance & Trading** (9): `bookkeeper`, `invoicing`, `budget-tracker`, `finance-wizard`, `financial-deepsearch`, `financial-tools`, `turbo-quant`, `crypto-trader`, `polymarket-trader`

**E-commerce & Product** (8): `ecom-agent`, `ecom-dashboard`, `inventory-sync`, `order-processor`, `print-on-demand`, `dropshipping-analyst`, `product-researcher`, `product-scout`

**Customer Success** (5): `customer-support`, `customer-journey-mapper`, `support-bot`, `ticket-system`, `feedback-loop`

**Engineering & Dev** (10): `engineering-assistant`, `qa-tester`, `api-tester`, `bot-dev`, `website-builder`, `chatbot-builder`, `workflow-builder`, `course-creator`, `pitch-deck-builder`, `contract-drafter`

**Intelligence & Research** (8): `intel-agent`, `data-analyst`, `data-scraper`, `analytics-bi`, `competitor-watch`, `web-researcher`, `mirofish-researcher`, `signal-community`

**Growth & Conversion** (4): `growth-hacker`, `conversion-rate-optimizer`, `offer-agent`, `ad-campaign-wizard`, `ad-copy-tester`, `paid-media-specialist`

**Core / Platform** (8): `orchestrator`, `ai-router`, `health-check`, `auto-updater`, `export-backup`, `report-generator`, `risk-analyst`, `goal-alignment`, `governance`

**Special / Branded** (4+): `hermes-agent`, `blacklight`, `ascend-forge`, `claude-agent`, `gemma-agent`, `ollama-agent`, `nvidia-nim`, `idea-to-prompt`

**Communication** (3): `discord-bot`, `whatsapp-webhook`, `meeting-intelligence`

**Memory & Brain** (2): `memory`, `obsidian-memory`, `neural_network`

**UI / System** (2): `problem-solver-ui` (the FastAPI server itself), `problem-solver`

**HITL high-risk list** (blocked by `runtime/core/hitl_gate.py`):
- `hr-manager`, `recruiter`, `lead-scorer`, `lead-hunter-elite`, `qualification-agent`, `data-analyst`

Ghost agents (config entries without directory) were eliminated in Week 1. Flat legacy `.py` files in `runtime/agents/` were removed — directory structure is the single active pattern.

---

## 8. SKILLS LIBRARY

`runtime/config/skills_library.json` — 147 skills. Loaded by `runtime/skills/library.py`, exposed via `runtime/skills/catalog.py`.

**Each skill entry has:**
```json
{
  "skill_id": "string",
  "version": "1.0.0",
  "category": "sales|marketing|ops|...",
  "description": "what real-world outcome it produces",
  "tools": ["tool_id_1", "tool_id_2"],
  "workflow": [...steps...],
  "validation_schema": {...},
  "output_schema": {...},
  "metadata": { "cost_est": 0.02, "avg_latency_ms": 1200 }
}
```

**Adding/replacing skills** does not break system integrity — orchestrator selects from registry dynamically.

---

## 9. PERSISTENCE LAYER

### JSON state files (`state/` directory)

All access protected by `runtime/core/file_lock.py` exclusive locks. **Multi-tenant**: each tenant's data lives under `_tenant_data[tenant_id]` keys.

| File | Owner agents | Purpose |
|---|---|---|
| `state/deals.json` | crm-pipeline, sales-closer-pro | CRM deals pipeline |
| `state/tasks.json` | task-orchestrator, team-management | Task tracking |
| `state/team-roster.json` | team-management | Team roster |
| `state/knowledge_store.json` | memory system | Bootstrapped knowledge base |
| `state/leads.json` | lead-* agents | Lead pipeline |
| `state/revenue.json` | bookkeeper, finance-wizard | Revenue tracking |
| `state/bus.jsonl` | `SimpleMessageBus` | Append-only event log |
| `state/llm_calls.jsonl` | `LLMClient` | Every LLM call (cost + debug) |
| `state/python-backend.log` | uvicorn | Rotated, capped 10MB |
| `state/version.json` | start.sh | Build/version tracking |

### SQLite (WAL mode)

- `state/audit.db` — **immutable** audit trail (GDPR/compliance)
- `state/forge_queue.db` — task queue (placeholder, not actively used yet)

Future target: Postgres for horizontal scaling.

### File locking pattern

```python
from core.file_lock import tenant_locked_read, tenant_locked_write

# Reads
data = tenant_locked_read(tenant_id, 'deals.json', default={})

# Writes
tenant_locked_write(tenant_id, 'deals.json', updated_data)
```

Never bypass — concurrent writes will corrupt state.

---

## 10. MULTI-TENANCY

Each tenant is fully isolated. Lives in `~/.ai-employee/tenants/{tenant_id}/state/` + `~/.ai-employee/tenants/{tenant_id}/config/`.

### Flow

1. `POST /auth/register` → creates new tenant with directory structure
2. User entry stored with `tenant_id`
3. JWT issued with `tenant_id` claim
4. Every subsequent request → middleware extracts `tenant_id` from JWT
5. Routes access tenant-specific data via `TenantContext`

### Middleware

- **Python/FastAPI**: `runtime/core/tenant_middleware.py`
- **Node/Express**: `backend/tenancy.js`

### Migration

```bash
python3 scripts/migrate_to_multitenant.py
```
Converts single-tenant state files into the `_tenant_data[tenant_id]` structure. Creates a default tenant, backs up originals.

### Tests

`tests/test_multitenant.py` — 10 tests covering creation, context, data isolation, migration scenarios. All passing.

---

## 11. SECURITY & AUTH

### JWT auth

Issued by `runtime/agents/problem-solver-ui/server.py`:
- `POST /auth/register` — creates tenant + user, returns access + refresh token
- `POST /auth/login` — returns access + refresh token
- `POST /auth/refresh` — rotates refresh token, issues new access
- `POST /auth/logout` — revokes refresh token

**Rate limiting:** `@_auth_rate_limit` decorator → 5 req/min per IP on auth routes.

**Password policy:** 12+ chars, special chars + numbers + uppercase enforced at registration.

### Route coverage

44 of 142 Node routes wrapped in `requireAuth` middleware. Public routes: `/health`, `/status`, `/version`, `/api/identity/public`, `/api/onboarding/palettes`, `/api/security/status` (read), `/internal/events` (machine-only).

### HITL gates

High-risk agents blocked until human approves via dashboard. Gate state persisted to SQLite. See section 5 for the agent list.

### Anomaly responder

`backend/security/anomaly_responder.js` — watches event patterns, auto-blocks suspicious actors.

### Secrets vault

`backend/security/secrets/` — encrypted on-disk, decrypted in-memory only.

---

## 12. OBSERVABILITY

### Prometheus

`/metrics` endpoint on port 8787. Text-format `ai_employee_*` metrics:
- `uptime_ms`
- `agents_active`
- `tasks_total`, `tasks_completed`, `tasks_failed`
- `errors_total`
- `api_calls_total`
- per-skill latency histograms
- per-agent token spend counters

### Metrics collector

`runtime/core/observability/metrics_collector.py` — 1-second tick, rolling 3600 snapshots in memory.

### Event stream

`runtime/core/observability/event_stream.py` — in-process pub/sub + JSONL persistence.

### Audit logger

Writes to `state/audit.db` (compliance) **and** `state/python-backend.log` (rotated, 10MB cap).

---

## 13. ENVIRONMENT VARIABLES

| Var | Where | Purpose |
|---|---|---|
| `JWT_SECRET_KEY` | `~/.ai-employee/.env` | JWT signing |
| `ANTHROPIC_API_KEY` | `~/.ai-employee/.env` | Anthropic LLM |
| `OPENAI_API_KEY` | `~/.ai-employee/.env` | Optional fallback |
| `LLM_BACKEND` | env | `anthropic` (default) or `ollama` |
| `STRICT_PIPELINE` | env | `1` disables pipeline fallbacks (CI/staging) |
| `LOG_LEVEL` | env | Python logging (default: INFO) |
| `EVOLUTION_MODE` | env | `AUTO` / `SAFE` / `OFF`. Prompted at startup if unset. |
| `PORT` | env | Node port (default 8787) |
| `PYTHON_PORT` | env | Python port (default 18790) |

`~/.ai-employee/.env` is auto-sourced by `start.sh`.

---

## 14. COMMANDS & WORKFLOWS

```bash
# Start the full system (builds frontend, starts Python + Node)
bash start.sh        # or: npm start
# Dashboard: http://localhost:8787

# Stop everything
bash stop.sh

# Dev workflow (two terminals)
PORT=8787 node backend/server.js           # Terminal 1: Node
cd frontend && npm run dev                 # Terminal 2: Vite dev :5173 (proxies to :8787)

# Tests
npm test                                   # pytest + agent_selftest.py
python3 -m pytest tests/test_<name>.py    # single test
python3 runtime/agents/agent_selftest.py  # agent selftest only
pip install -r requirements-test.txt      # install test deps first

# Lint (syntax-checks all Python agent modules)
npm run lint

# Migrate single-tenant → multi-tenant
python3 scripts/migrate_to_multitenant.py

# Frontend build only
cd frontend && npm run build
```

---

## 15. NODE.JS BACKEND — ALL 142 ROUTES

Organized by domain. **🔒** = requires `requireAuth` middleware.

### Health & status (8)

```
GET    /health
GET    /health/full
GET    /version
GET    /status
GET    /api/status               🔒
GET    /api/health
GET    /api/readiness
GET    /api/security/status
```

### Auth & identity (4)

```
POST   /api/auth/token
GET    /api/auth/auto-token
GET    /api/identity/public
POST   /api/identity/finalize
```

### Onboarding (1)

```
GET    /api/onboarding/palettes
```

### Agents lifecycle (13)

```
GET    /agents
GET    /internal/agents
POST   /agents/activate          🔒
GET    /api/agents               🔒
POST   /api/agents/start-all
POST   /api/agents/pause-all
POST   /api/agents/stop-all
GET    /api/agents/grades
GET    /api/agents/:agent_id/grade
GET    /api/agents/:agent_id/profile
POST   /api/agents/:agent_id/ladder/assign   🔒
POST   /api/agents/:agent_id/ladder/advance  🔒
```

### Neural brain (7)

```
GET    /api/neural-brain/memory/status
GET    /api/neural-brain/memory/list
DELETE /api/neural-brain/memory/:id
GET    /api/neural-brain/graph/status
GET    /api/neural-brain/graph/snapshot
GET    /api/neural-brain/threads
POST   /api/neural-brain/think
GET    /api/neural-brain/forge/evolution/status
```

### Brain (5)

```
GET    /api/brain/status
GET    /internal/brain/status
GET    /api/brain/insights
GET    /api/brain/activity
GET    /api/brain/neurons
GET    /api/brain/graph
GET    /api/memory/tree
```

### System metrics (4)

```
GET    /api/system/stats         🔒
GET    /api/observability/snapshot
GET    /api/observability/events
POST   /api/system/halt          🔒
POST   /api/system/restart       🔒
GET    /api/system/halt
```

### Security (5)

```
GET    /api/security/aztsa/status
GET    /api/security/honeypot/events
POST   /api/security/offline-sync         🔒
POST   /api/security/anomaly/evaluate     🔒
POST   /api/security/gateway/strict-mode  🔒
```

### Mode (operating mode: starter/business/power) (2)

```
GET    /api/mode
POST   /api/mode                 🔒
```

### Autonomy & evolution (5)

```
GET    /api/autonomy/status
GET    /api/autonomy/mode
POST   /api/autonomy/mode               🔒
POST   /api/autonomy/emergency-stop     🔒
GET    /api/evolution/status
POST   /api/evolution/mode              🔒
```

### Doctor (self-diagnostic) (5)

```
GET    /api/doctor/status
GET    /api/doctor/llm-status
GET    /api/doctor/errors
POST   /api/doctor/run                  🔒
GET    /api/self-improvement/status
```

### Product / workflows / objectives (4)

```
GET    /api/product/dashboard
GET    /api/workflows/live
GET    /api/objectives/status
POST   /api/automation/control          🔒
```

### Money mode (3)

```
POST   /api/money/content-pipeline      🔒
POST   /api/money/lead-pipeline         🔒
POST   /api/money/opportunity-pipeline  🔒
POST   /api/money/task                  🔒
```

### Tasks & chat (2)

```
POST   /api/tasks/run                   🔒
POST   /api/chat                        🔒
```

### Audit (2)

```
GET    /api/audit/events
GET    /api/audit/stats
```

### Errors (2)

```
POST   /api/error-report                🔒
GET    /api/error-report
```

### Reliability (3)

```
GET    /api/reliability/status
POST   /api/reliability/forge/freeze    🔒
POST   /api/reliability/forge/unfreeze  🔒
```

### Forge (self-evolution code generation) (11)

```
GET    /api/forge/queue
POST   /api/forge/submit                🔒
POST   /api/forge/approve/:id           🔒
POST   /api/forge/reject/:id            🔒
POST   /api/forge/sandbox               🔒
POST   /api/forge/rollback              🔒
GET    /api/forge/snapshots
POST   /api/forge/build-system          🔒
GET    /api/forge/status
POST   /api/forge/task                  🔒
GET    /api/forge/code-ai/models
POST   /api/forge/code-ai               🔒
```

### Blacklight (anomaly detection) (4)

```
GET    /api/blacklight/status
POST   /api/blacklight/toggle           🔒
POST   /api/blacklight/scan             🔒
GET    /api/blacklight/alerts
```

### Fairness & governance (2)

```
GET    /api/fairness/report
GET    /api/governance/digest
```

### Hermes (broadcasting agent) (3)

```
GET    /api/hermes/status
POST   /api/hermes/task                 🔒
POST   /api/hermes/broadcast            🔒
```

### Learning ladder (agent skill progression) (4)

```
POST   /api/learning-ladder/build       🔒
POST   /api/learning-ladder/complete    🔒
GET    /api/learning-ladder/progress
GET    /api/learning-ladder/all
```

### Prompt inspector (5)

```
GET    /api/prompt-traces
GET    /api/prompt-trace/:id
DELETE /api/prompt-traces               🔒
GET    /api/prompt-inspector/config
POST   /api/prompt-inspector/config     🔒
PATCH  /api/prompt-inspector/config     🔒
```

### Middleware (2)

```
POST   /api/middleware/process          🔒
GET    /api/middleware/status
```

### Workspace (3)

```
POST   /api/workspace/upload
GET    /api/workspace/files
DELETE /api/workspace/files/:path
```

### Artifacts (2)

```
GET    /api/artifacts
GET    /api/artifacts/:filename
```

### Internal (machine-only) (1)

```
POST   /internal/events           # SSE→WS bridge ingest from Python
```

---

## 16. PYTHON AI BACKEND

`runtime/agents/problem-solver-ui/server.py`. ~20,000 lines. Key endpoints:

### Auth (4)

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
```

### Events stream (2)

```
GET    /api/events     # SSE — Node bridges this to WS
GET    /events         # legacy alias
```

### Health & status (3)

```
GET    /health
GET    /api/status
GET    /api/wavefield/status
GET    /security/status
```

### Doctor (3)

```
GET    /api/doctor
GET    /api/doctor/items
POST   /api/doctor/action
```

### System resources (1)

```
GET    /api/system/resources
```

### LLM gateway (2)

```
POST   /api/gateway/pull-model
GET    /api/gateway/status
```

### Agents (5)

```
POST   /api/agents/start-all
POST   /api/agents/stop-all
POST   /api/agents/start
POST   /api/agents/stop
POST   /api/quick-actions/onboard
```

### Workers (2)

```
GET    /api/workers
GET    /api/workers/bundles
POST   /api/workers/bundles
```

### Chat (4)

```
GET    /api/chat
POST   /api/chat       # the main LLM endpoint
GET    /chat
POST   /chat
```

### Schedules (3)

```
GET    /api/schedules
POST   /api/schedules
DELETE /api/schedules/{task_id}
```

### Improvements (2)

```
GET    /api/improvements
PATCH  /api/improvements/{improvement_id}
```

### Skills (custom user-defined) (2)

```
GET    /api/skills
POST   /api/skills
```

### Custom agents (user-defined) (4)

```
GET    /api/agents/custom
POST   /api/agents/custom
GET    /api/agents/custom/{agent_id}
DELETE /api/agents/custom/{agent_id}
```

---

## 17. WEBSOCKET EVENT TAXONOMY

Single WS connection from frontend (`useWebSocket.js`). All events go through one switch.

### Event channels (prefix-based dispatch)

```js
if (event.startsWith('cognitive:') || event.startsWith('brain:') || event.startsWith('nb:')) {
  dispatchCognitiveEvent(event, data)
} else if (event.startsWith('agent:')) {
  dispatchAgentEvent(event, data)
} else if (event.startsWith('task:') || event.startsWith('orchestrator:') || event.startsWith('chat:') || event.startsWith('execution:')) {
  dispatchTaskEvent(event, data)
}
```

### Full event reference

| Event | Payload shape | Store mutation |
|---|---|---|
| `nb:reasoning_step` | `{step: string, content: string, ts: number}` | `cognitiveStore.appendReasoningStep(step)` — capped at 50 |
| `nb:memory_write` | `{type: 'semantic'\|'episodic'\|'working', content: string, agent: string, ts: number}` | `cognitiveStore.flashMemoryWrite(write)` — capped at 20 |
| `nb:memory_read` | `{ids: string[]}` | `cognitiveStore.pulseMemory(ids)` — visual highlight |
| `nb:graph_update` | `{nodes?: Node[], links?: Link[]}` | `brainStore.addNode(n)` + `brainStore.addLink(l)` per item |
| `nb:model_call` | `{model: string, tokens: number, latency: number, ts: number}` | `cognitiveStore.recordModelCall(call)` — capped at 100 |
| `nb:action_call` | `{id?: string, skill: string, status: string}` | `eventFeedStore.addEvent({kind:'agent_action', notes:'<skill> · <status>'})` |
| `nb:artifact_created` | `{artifacts: [{name, ...}]}` | `eventFeedStore.addEvent({kind:'artifact', notes:'<names>'})` |
| `nb:thread_created` | `{thread_id: string, input_preview: string}` | `systemStore.addHeartbeatLog({level:'info', text:'[BRAIN] Thread started: ...'})` |
| `brain:insights` | `{summary, recommendations, ...}` | `cognitiveStore.setBrainInsights(data)` |
| `brain:activity` | `{memory_writes_per_sec, ...}` | `cognitiveStore.setBrainActivity(data)` |
| `brain:graph` | `{nodes: Node[], links: Link[]}` **OR** `{node: Node, link?: Link}` | `brainStore.setGraph(data)` for bulk; `addNode/addLink` for delta |
| `agent:update` | `{agents: Agent[]}` | `agentStore.setAgents(normalizeAgents(data.agents))` |
| `orchestrator:message` / `chat:message` | `{message: string, reply?: string, text?: string, attachments?: [], debugInfo?: object, ts: number, subsystem?: string}` | Clears `typing`, clears `executionSteps`, appends to `taskStore.chatMessages` as `{role:'ai', content, ...}` |
| `orchestrator:queued` | `{taskId: string, agentId: string}` | `systemStore.addHeartbeatLog({text:'[ORCHESTRATOR] Queued <id> on <agent>'})` |
| `execution:log` | `{step, status, ts, ...}` | `taskStore.addExecutionLog(data)` |
| `system:ready` | — | `appStore.setBackendStatus({python_ok, llm_ok, node_ok})` |

### Node-graph node shape

```ts
type Node = {
  id: string
  label?: string
  type?: 'input'|'hidden'|'output'|'skill'|'memory'|'strategy'|'task'
  weight?: number      // 0..1
  confidence?: number  // 0..1
  activation?: number  // 0..1
  source?: string
  tag?: string
  group?: 'money'|'learning'|'automation'|'memory'|'system'
}

type Link = {
  source: string  // node id
  target: string  // node id
  strength?: number   // 0..1 (also accepted: weight, confidence)
}
```

Auto-derived from `type`: strategy/skill → money, memory → memory, task/output → automation, input/hidden → learning, else system. Colors per group in `brainStore.GROUP_COLORS`.

### Limits

- Max nodes: 300 (oldest evicted)
- Max links: 600 (oldest evicted)
- `reasoningSteps`: 50
- `modelCalls`: 100
- `memoryWrites`: 20

---

## 18. FRONTEND STACK & DESIGN SYSTEM

### Aesthetic — AETERNUS NEXUS 2095

Dark gold-on-black. Monospaced labels in caps. Hex frames, subtle scanlines, rotating gear rings, animated halos. Think "cinematic mission control" not "SaaS dashboard".

### Design tokens (`frontend/src/components/nexus-ui/tokens.css`)

```css
:root {
  /* Colors */
  --nx-gold:        #FFB800;
  --nx-gold-dim:    #8C6500;
  --nx-cyan:        #00D4FF;
  --nx-red:         #FF4444;
  --nx-success:     #00FFB4;
  --nx-purple:      #B565F5;
  --nx-bg:          #0a0a0c;
  --nx-bg-panel:    #14141a;
  --nx-surface:     rgba(20,20,28,0.85);
  --nx-border:      rgba(255,184,0,0.18);
  --nx-border-bright: rgba(255,184,0,0.45);
  --nx-text:        #E5C76B;
  --nx-text-muted:  #8a7d50;

  /* Typography */
  --nx-font-mono:   'JetBrains Mono', monospace;
  --nx-font-sans:   'Inter', system-ui, sans-serif;

  /* Spacing (4px grid) */
  --nx-s1: 4px;  --nx-s2: 8px;  --nx-s3: 12px;  --nx-s4: 16px;
  --nx-s5: 24px; --nx-s6: 32px; --nx-s7: 48px;  --nx-s8: 64px;

  /* Radius */
  --nx-r-sm: 4px; --nx-r-md: 8px; --nx-r-lg: 12px; --nx-r-pill: 999px;

  /* Shadows / glows */
  --nx-glow-gold: 0 0 12px rgba(255,184,0,0.4);
  --nx-glow-cyan: 0 0 12px rgba(0,212,255,0.4);
  --nx-glow-red:  0 0 12px rgba(255,68,68,0.5);

  /* Motion */
  --nx-dur-fast: 120ms;
  --nx-dur-base: 250ms;
  --nx-dur-slow: 400ms;
  --nx-ease-out: cubic-bezier(0.4, 0, 0.2, 1);

  /* Z-index */
  --nx-z-panel: 10;
  --nx-z-overlay: 50;
  --nx-z-modal: 100;
  --nx-z-toast: 200;
}
```

**Rule:** Never hardcode colors. Always reference `var(--nx-*)`.

---

## 19. ZUSTAND STORES

`frontend/src/store/`. No Redux. No Recoil.

### `appStore.js` — global app state

```js
{
  activeSection: string,                    // current page id (drives routing)
  wsConnected: boolean,
  systemHealth: { cpu_percent, memory_percent, gpu_percent, gpu_temp },
  brainState: { status, memory_size, ... },
  productMetrics: object,
  automationStatus: string,
  brainInsights: object,
  workflowSnapshot: { active_run, runs },
  backendStatus: { python_ok, llm_ok, node_ok },  // persisted to localStorage
  // setters: setActiveSection, setWsConnected, setSystemHealth, setBrainState, ...
}
```

### `agentStore.js`

```js
{
  agents: Agent[],          // {id, name, role, status, success_rate, health, ...}
  activeAgentId: string|null,
  setAgents, setActiveAgentId,
}
```

### `taskStore.js`

```js
{
  executionSteps: ExecStep[],     // {step, status: 'pending'|'running'|'done'|'failed', ...}
  workflowState: { active_tasks, queued_tasks, success_rate, avg_exec_time },
  opsSummary: { ... },             // server-computed summary
  chatMessages: Message[],         // {role: 'user'|'ai', content, attachments, debugInfo, ts}
  typing: boolean,
  addChatMessage, setTyping, addExecutionLog, clearExecutionSteps, ...
}
```

### `cognitiveStore.js`

```js
{
  reasoningSteps: Step[],          // capped 50
  modelCalls: Call[],              // capped 100
  memoryWrites: Write[],           // capped 20
  avatarState: { state, tokens_per_sec, context_depth, ... },
  brainInsights, brainActivity,
  appendReasoningStep, recordModelCall, flashMemoryWrite, pulseMemory,
  setAvatarState, setBrainInsights, setBrainActivity,
  clearReasoningSteps, clearModelCalls,
}
```

Persists metrics only (not raw arrays) to localStorage.

### `brainStore.js`

```js
{
  nodes: Node[],     // capped 300
  links: Link[],     // capped 600
  stats: object,     // { knowledge: [...], seeded?: bool }
  updatedAt: ISO string,
  selectedNodeId: string|null,
  reasoningSteps, memoryWrites, modelCalls,  // mirrored from cognitive
  setGraph, addNode, addLink, addNodesAndLinks,
  addFromPrompt, mergeGraphDelta,
  appendReasoningStep, flashMemoryWrite, recordModelCall, pulseMemory,
  setSelectedNodeId,
}
```

Auto-normalizes incoming nodes (color assignment, group derivation).

### `economyStore.js`

```js
{
  revenue: { today, daily, total, roi_trend, roi_7d, token_cost, ... },
  monetizationPipelines: { [pipeline_id]: { active, status, ... } },
  // setters
}
```

### `securityStore.js`

```js
{
  securityStatus: { threat_score, ... },
  policies: Policy[],
  events: SecurityEvent[],
}
```

### `eventFeedStore.js`

```js
{
  events: Event[],        // {id, kind, notes, ts, priority?, severity?}
  addEvent, clearEvents,
}
```

### `systemStore.js`

```js
{
  systemStatus: { cpu, memory, gpu_usage, gpu_temperature, ... },
  heartbeatLogs: Log[],   // {text, level, ts}
  addHeartbeatLog,
}
```

---

## 20. HOOKS

`frontend/src/hooks/`

| Hook | Returns | Purpose |
|---|---|---|
| `useWebSocket()` | — | Mounts single WS connection. Dispatches all events into stores. Handles reconnect with backoff. |
| `useChannelState(value, staleAfterMs)` | `'LIVE' \| 'STALE' \| 'OFFLINE'` | Returns freshness state. `OFFLINE` when `!wsConnected`. `STALE` when value reference unchanged for >`staleAfterMs`. Re-evaluates every 2s. |
| `useAvatarData()` | `{aperture, gearSpeed, hexCodes, tickerText, criticalEvent, queueDepth}` | RoboticEye data binding |
| `useAvatarPersonality({state, queueDepth})` | `{classNames, breath, saccade: {x,y}}` | State-driven micro-movements |
| `useVoiceLipSync()` | `{flareIntensity, finWobble, particleRate}` | Voice reactivity |
| `useAdaptiveQuality()` | `{quality: 'high'\|'med'\|'low'}` | Reduces visual complexity on low-end devices |
| `useAmbientSoundscape()` | — | Optional ambient audio |
| `useAudioBoot()` | — | Boot sound effect |
| `useExecutionUpdates()` | — | Polls execution status when WS down |
| `useFormState(initial)` | `{values, errors, setField, validate, reset}` | Generic form helper |
| `useIntersection(ref, opts)` | `boolean` | IntersectionObserver wrapper |
| `useOrbitNodeInteraction()` | hover/click handlers | For 3D brain graph nodes |
| `usePerformanceMode()` | `{mode}` | Auto-detects performance budget |
| `usePollingCoordinator()` | — | Centralises REST polling cadence (only fires when WS down) |
| `useReducedMotion()` | `boolean` | Respects `prefers-reduced-motion` |
| `useUpdateCheck()` | `{status, progress, log, ...}` | Used in Settings page for system updates |
| `useVisibility()` | `boolean` | Page visibility API wrapper |

---

## 21. NEXUS-UI PRIMITIVE LIBRARY

`frontend/src/components/nexus-ui/` — the visual design system. Use these for consistency. Don't write custom equivalents.

| Component | API | Use |
|---|---|---|
| `Panel` | `{title, accent, size?, tight?, corners?, children}` | Glassmorphic wrapper with accent border |
| `KPITile` | `{label, value, icon, iconTone, accent, sub, trend?, valueClass?}` | Label (9px caps) + value (tabular) + delta + optional sparkline |
| `StatusPill` | `{label, tone: 'gold'\|'cool'\|'success'\|'alert'\|'idle'\|'purple', size?}` | Tag/badge |
| `SectionLabel` | `{rule?, children}` | Caps label, optional rule line below |
| `Sparkline` | `{data, color, w?, h?}` | Inline SVG line chart |
| `HexButton` | `{label, onClick, variant}` | Hexagonal action button |
| `HexFrame` | `{children}` | Decorative hex frame wrapper |
| `ClockModule` | — | Live clock + uptime display |
| `NavRailItem` | `{label, icon, active, onClick, badge?}` | Sidebar nav item |
| `CommandPill` | — | Topbar search/command pill (opens command palette) |

---

## 22. THE 20 PAGES

Routing is **store-driven**, not router-driven. `useAppStore.activeSection` is the source of truth; URL syncs to it inside `Dashboard.jsx`. The `PAGES` map in `Dashboard.jsx` resolves section name → lazy-loaded component.

### CORE

#### `nexus` / `dashboard` → `NexusOSDashboard.jsx`
The cinematic centerpiece. Layout:
- Top status strip: connection state, CPU/RAM, agents, tasks, threat, health %
- Center stage: 4 corner panels around the RoboticEye
  - **TL — COGNITION** (cyan): reasoning chains, tokens/sec, context depth, memory writes/sec, sparkline
  - **TR — OPERATIONS** (gold): active tasks, queued, success %, exec time, CPU sparkline
  - **BL — ECONOMY** (purple): daily revenue, active pipelines, ROI 7D, token cost, revenue sparkline
  - **BR — INFRASTRUCTURE** (green/red): CPU%, GPU%, RAM%, GPU temp, RAM sparkline
  - Center: animated eye with caption "COGNITIVE CORE / AUTONOMOUS AI INTELLIGENCE / [STATE]"
  - Stage decorations: axis lines, beams, 5 rings, corner connlines, 42 sparkbits
- Mission section: `CurrentObjective` + `CognitiveStream` (rolling log)
- Lower section: `TaskPipeline` (5-col kanban) + `SystemTelemetry` (4 sparkline cards)
- Right sidebar: `EventStream` (severity-filtered) + `AgentGrid` (6 tiles + spawn) + `QuickActions` (8 buttons)

Each corner panel uses `useChannelState` to show LIVE/STALE/OFFLINE indicator dot. Stale panels render `— —` instead of zeros.

#### `cognition` → `CognitionPage.jsx`
- 5 KPI tiles: Tokens/Sec, Reasoning Chains, Context Depth, Memory Writes, Latency
- 60-point rolling SVG token throughput chart (1Hz tick, useRef buffer)
- Reasoning Trace viewer (Langfuse-style spans, collapsible). Shows 5 DUMMY_SPANS when reasoningSteps empty.
- Memory Write Stream (newest-first, 12 rows, type badges)

#### `agents` → `AgentsPage.jsx`
- 4 KPI tiles (total, active, idle, error)
- 10 filter tabs: ALL/ACTIVE/IDLE/ERROR + 6 role tabs
- 24-tile grid (`grid-template-columns: repeat(auto-fill, minmax(140px, 1fr))`), pagination
- Each tile: role-colored 40px avatar circle, status dot, ID, role, success % badge, 4px health bar
- Detail drawer: slides from right via translateX 250ms ease-out
  - 64px avatar + stats + event timeline + TERMINATE/ASSIGN buttons
  - Closes on backdrop click or ×

#### `memory` → `MemoryPage.jsx`
- 4 KPI tiles (total/semantic/episodic/working)
- Left: search bar + filter tabs (ALL/SEMANTIC/EPISODIC/WORKING/SKILL) + 12-entry scrollable list
- Right: memory detail (badge/title/abstract/tags/metadata) or empty-state ("SELECT A MEMORY ENTRY TO INSPECT")
- Bottom: 18-node static SVG graph with 27 edges (CSS pulse animation, staggered delays)
- Type colors: semantic=#00D4FF, episodic=#E5C76B, working=#00FFB4, skill=#A855F7
- Falls back to `FALLBACK_ENTRIES` (12 rich entries) when store is empty

#### `economy` → `MoneyModePage.jsx`
- 5 KPI tiles (daily revenue, total, ROI, active pipelines, token cost)
- 7-day SVG bar chart (rounded tops, gradient fill, glow on today's bar)
- Pipeline status cards (3): `content_publish_track`, `data_scrape_filter_store`, `outreach_response_conversion`
- Token cost breakdown table (4 rows + total)
- 3 Monetization Stream cards with sparklines

### OPERATIONS

#### `tasks` → `OperationsPage.jsx`
- 5 KPI tiles
- 5-column kanban: INCOMING → PLANNING → EXECUTING → VALIDATING → COMPLETED
- Task cards with priority pills (P0=red, P1=orange, P2=gold, P3=dim)
- Animated progress bar on EXECUTING cards
- Task list table (8 rows, sortable)
- 2 SVG performance charts (bar + line)

#### `workflows` → `AscendForgePage.jsx`
- Toolbar: RUN/PAUSE/STOP + status pill
- Pure SVG DAG canvas (7 nodes, viewBox 820×400, cubic Bezier edges, arrowhead markers, glow filters on selected)
- Right panel: node inspector (empty state vs. node detail with inputs/outputs/config/buttons)
- Workflow preset strip (3 cards: CHAT PIPELINE, AGENT DISPATCH, DATA INGEST)

#### `infrastructure` / `deployments` / `runtime` → `SystemHealthPage.jsx`
- 5 SVG ring gauges (CPU/GPU/RAM/DISK/GPU_TEMP) with stroke-dasharray animation
- 4-column sparkline row (60-point rolling buffers, 1Hz)
- Sortable process table (10 rows, TYPE badge colors)
- System info panel (OS/Node/Python/uptime/mode/version)
- 6 container status cards

### INTELLIGENCE

#### `neural-graph` → `NeuralNetworkPage.jsx`
- 4 KPI tiles (nodes, edges, knowledge entries, brain state pill)
- 3D Three.js brain graph (`UnifiedBrain` component) — lazy loaded
- Empty state when no nodes
- **Seeds 12 demo nodes + 12 edges** when backend snapshot is empty so the visual is always informative
- Right panel: Graph Controls (3 pill toggles, density slider, TOP/SIDE/FRONT presets), Layer Breakdown (5 rows with bars), Active Connections (last 5 edges)
- CSS prefix: `nnp__`

#### `knowledge` → `KnowledgePage.jsx`
- Knowledge base browser
- Search + filter + entry list + detail with abstracts and related concepts
- 10 pre-populated entries with full abstracts (RAG, SaaS metrics, agents, embeddings, HITL gate, competitor pricing, async queues, contracts, episodic memory, evolution controller)

#### `trends` → `IntelligencePage.jsx`
- Trend analysis dashboard

#### `research` → `ResearchPage.jsx`
- Research workflow page

### SECURITY (all four routes → single `SecurityPanel.jsx` with internal tab switching)

`SecurityPanel.jsx` reads `useAppStore.activeSection` and renders one of four tab contents:

#### `policies` (tab)
- Threat score hero: 52px number + horizontal bar + threat badge
- System flags grid (AGENTS/FORGE/PIPELINE/VAULT)
- Active threats list
- Policy rules table (5 rows): Rate Limiting, JWT Validation, HITL Gate, Anomaly Detector, Secret Vault

#### `permissions` (tab)
- 4×6 CSS grid role×resource permission matrix (✓/⊘/✗ with green/yellow/red coloring)
- API keys table (3 rows, masked)

#### `sandboxes` (tab)
- 6 sandbox cards with CPU/RAM bars, agent count badges
- ISOLATE/TERMINATE buttons per card

#### `audit` (tab)
- Filter buttons (ALL/SECURITY/AGENT_ACTIONS/SYSTEM)
- 12-row audit table with sticky headers

### SYSTEM

#### `settings` → `SettingsPage.jsx` (671 lines)
5 tabs in a `TAB_CONTENT` array, `useSave(endpoint, data)` hook for shared save state:
- **GENERAL** — update check (via `useUpdateCheck`), progress bar, log viewer, system info
- **LLM** — provider radio pills (Anthropic/OpenAI/Ollama), model selector, API key inputs with `/api/settings/test-key`
- **INTEGRATIONS** — 2-col cards (disabled at 0.6 opacity, enabled with gold glow + inline config)
- **APPEARANCE** — 3 theme preview tiles with active checkmark
- **ADVANCED** — raw JSON dev panel (lazy-fetches), red-zone danger actions with typed `CONFIRM` modal, "Download Logs" via fetch+bearer

Custom controls:
- `NxToggle` (sliding gold thumb with glow, `role="switch"`)
- `NxSlider` (custom range with gold thumb)
- `NxField` (label + input wrapper)
- `NxSaveBtn` (variants: default/saved/danger/outline/green/reload)
- `ConfirmModal` (requires typing CONFIRM)

#### `models` / `integrations` → `IntegrationsPage.jsx`
- Integration management

#### `workspace` → `WorkspacePage.jsx`
- File upload zone, working files

---

## 23. DASHBOARD.JSX

`frontend/src/components/Dashboard.jsx` — the layout shell.

### Routing map (PAGES dict)

```js
const PAGES = {
  // Legacy aliases
  'dashboard':      DashboardPage,
  'neural-network': NeuralNetworkPage,
  'intelligence':   IntelligencePage,
  'operations':     OperationsPage,
  'ascend-forge':   AscendForgePage,
  'system':         SystemHealthPage,
  'workspace':      WorkspacePage,
  'integrations':   IntegrationsPage,
  'settings':       SettingsPage,
  // CORE
  'nexus':          DashboardPage,
  'cognition':      CognitionPage,
  'agents':         AgentsPage,
  'memory':         MemoryPage,
  'economy':        MoneyModePage,
  // OPERATIONS
  'tasks':          OperationsPage,
  'workflows':      AscendForgePage,
  'infrastructure': SystemHealthPage,
  'deployments':    SystemHealthPage,
  // INTELLIGENCE
  'neural-graph':   NeuralNetworkPage,
  'knowledge':      KnowledgePage,
  'trends':         IntelligencePage,
  'research':       ResearchPage,
  // SECURITY — all four → SecurityPanel (switches on activeSection internally)
  'policies':       SecurityPanel,
  'permissions':    SecurityPanel,
  'sandboxes':      SecurityPanel,
  'audit':          SecurityPanel,
  'security':       SecurityPanel,
  // SYSTEM
  'models':         IntegrationsPage,
  'runtime':        SystemHealthPage,
}
```

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  Sidebar  │  TopBar                                     │
│           │ ─────────────────────────────────────────── │
│           │                                              │
│           │  <PageComponent /> (lazy, ErrorBoundary)    │
│           │                                              │
│           │ ─────────────────────────────────────────── │
│           │  BottomDrawer + CommandDock (always visible)│
└─────────────────────────────────────────────────────────┘
            + ContextPanel (right rail, conditional)
            + ChatPanel (slide-in via Alt+T / Meta+T)
            + CommandPalette (Cmd-K modal, global)
```

### Key behaviors

- **Store ↔ URL sync** — two `useEffect` hooks keep `activeSection` ↔ `location.pathname` in sync
- **`showCommandDock = true`** — always renders BottomDrawer + CommandDock (used to hide on Settings, now always on per user request)
- **Padding-bottom 116px** on `<main>` to prevent content under CommandDock
- **`isFullscreen`** on `dashboard` / `nexus` → removes padding for the cinematic centerpiece
- **Initial REST hydration** — calls `/api/mode` + `/api/product/dashboard` once on mount; only polls every 8s if `!wsConnected`
- **Keyboard shortcuts**:
  - Alt+T / Meta+T → toggle ChatPanel
  - Cmd-K / Ctrl-K → CommandPalette (owned by CommandPalette, not Dashboard)
  - Escape → close ChatPanel if open

### CommandPalette (`frontend/src/components/ui/CommandPalette.jsx`)

- Mounts globally
- Opens on `nx:command-palette:open` event + global Cmd/Ctrl+K
- 20 page items + 4 quick actions, labeled groups
- Fuzzy filter, ↑↓ arrow nav, Enter selects, Esc closes
- Page selection → `setActiveSection`
- Quick actions → dispatch `nx:*` custom events

---

## 24. THE ROBOTIC EYE AVATAR

`frontend/src/components/core/RoboticEye.jsx` — the centerpiece avatar. SVG-based mechanical eye with 10 Z-layers, data-bound, voice-reactive.

### Layer stack (Z1 → Z10)

| Z | Layer | Component | Behavior |
|---|---|---|---|
| Z0 | Halo (outer aura) | `EyeHalo` | State-driven color, 3s breathe |
| Z1 | Rays (sun rays) | `EyeRays` | Rotate CW 90s |
| Z2 | Particles | inline | Drift outward, fade |
| Z3 | Outer tier (5 rings) | inline | Rotate CW 90s as unit |
| Z4 | Rivets / chassis | `EyeMechanical` | Fixed (no rotation) |
| Z5 | Gear ring | inline | Rotate CCW at `--gear-speed` (var, default 20s, faster on high tokensRate) |
| Z6 | Iris backlight glow | inline | 3s pulse, faster on executing/busy/error |
| Z7 | Iris fins (aperture) | `IrisShutter` | Rotate CCW at 1.6× gear speed |
| Z8 | Lens cage | inline | Fixed |
| Z9 | Lens / iris striations | `IrisStriations` + pupil + halo + hex codes ticker | Hex codes rotate 30s + pulse 4s |
| Z10 | HUD typography | inline | Telemetry text, cardinal markers |

`EyeFilters` provides SVG `<defs>` (glows, blurs, gradients). Must be first child of `<svg>`.

`EyeDataTicker` is a scrolling telemetry text layer between gear-ring and lens-cage.

### Data hooks

```js
useAvatarData()       → { aperture, gearSpeed, hexCodes, tickerText, criticalEvent, queueDepth }
useAvatarPersonality({state, queueDepth}) → { classNames, breath, saccade: {x,y} }
useVoiceLipSync()    → { flareIntensity, finWobble, particleRate }
```

### State variants

| State | Color | Halo period | Behavior |
|---|---|---|---|
| `IDLE` | gold | 3s | calm |
| `LISTENING` | cyan | 1.4s | halo brightens, "leans in" |
| `THINKING` | cool | 3s | subtle fin tint |
| `EXECUTING` | gold-hot | 1.5s | fins hue-rotate -8deg, brightness 1.1 |
| `BUSY` | orange | 1.1s | fins hue-rotate -20deg |
| `ERROR` | red | 0.6s | flash, hue-rotate -60deg, saturate 2 |

### CSS conventions

- Prefix: `re__*`
- Modifier states: `.re--listening`, `.re--executing`, `.re--busy`, `.re--thinking`, `.re--error`, `.re--hot`, `.re--compact` (for 60-72px mini-eye in CommandDock)
- Reduced motion respected: all rotating animations stopped, glow periods extended to 8s
- Gaze tracking: pupil/halo `transform` set inline via React based on cursor position + saccade offset
- Pupil dilation: `r` smooth-transitions on the dynamic radii (250ms cubic-bezier)
- Blink: `.re--blinking` reduces opacity briefly

### Sub-components

`frontend/src/components/core/eye/`:
- `EyeFilters.jsx` — SVG defs
- `EyeHalo.jsx` — outer aura
- `EyeRays.jsx` — sun rays
- `EyeMechanical.jsx` — rivets + chassis (replaces old 16-rivet inline group)
- `IrisShutter.jsx` — aperture fins (replaces old 24-fin sunburst)
- `IrisStriations.jsx` — iris detail
- `EyeDataTicker.jsx` — scrolling telemetry text
- `AvatarPersonality.css` — personality classes

---

## 25. WHAT WAS REMOVED / CONSOLIDATED

These 23 legacy pages were **deleted** on 2026-05-16 (the old `AgentsPageNEW.jsx` was also renamed to `AgentsPage.jsx`). Their key features were folded into the targets shown:

| Removed page | Feature folded into |
|---|---|
| `AIControlPage`        | AgentsPage drawer (mode controls) |
| `AgentsPage` (old)     | replaced by new `AgentsPage` (formerly `AgentsPageNEW`) |
| `AuditPage`            | SecurityPanel `audit` tab |
| `BlacklightPage`       | SecurityPanel `audit` tab |
| `ControlCenterPage`    | SystemHealthPage `EmergencyPanel` (Halt / Restart / Recovery) |
| `DevPanel`             | SettingsPage `ADVANCED` tab |
| `DoctorPage`           | SystemHealthPage `DiagnosticsPanel` (6 checks + RUN ALL) |
| `EvolutionPage`        | SettingsPage `ADVANCED` tab (evolution_mode field) |
| `ExecutionPage`        | OperationsPage kanban |
| `FairnessPage`         | dropped — fairness only surfaces in `/api/fairness/status` diagnostic |
| `FeedbackPanel`        | dropped (was only referenced by DevPanel) |
| `HermesPage`           | dropped |
| `HistoryPage`          | OperationsPage task list |
| `LearningLadderPage`   | AgentsPage drawer (`LADDER ADVANCE` button) |
| `NeuralBrainPage`      | NeuralNetworkPage (seeded graph + UnifiedBrain 3D) |
| `OutputPage`           | CognitionPage memory write stream |
| `PermissionsPage`      | SecurityPanel `permissions` tab |
| `PoliciesPage`         | SecurityPanel `policies` tab |
| `PromptInspectorPage`  | CognitionPage `PromptInspector` panel (live model_calls + demo fallback) |
| `SandboxesPage`        | SecurityPanel `sandboxes` tab |
| `SystemPage`           | SystemHealthPage |
| `TrainingPage`         | AgentsPage drawer (`CHECK` grade + `REINFORCE`) |
| `VoicePage`            | `VoiceModal` (mounted in Dashboard, opened by CommandDock voice pill) |

The on-disk files **were physically deleted** — they no longer exist. Use `git log` if you need history.

---

## 26. PERFORMANCE & CHUNK SPLITTING

Vite rolldown with `advancedChunks/codeSplitting`. Latest build:

| Chunk | Size | gzip |
|---|---|---|
| `vendor-three-core` | 723 KB | 184 KB |
| `NeuralNetworkPage` | 330 KB | 158 KB |
| `vendor-three-extras` | 193 KB | 61 KB |
| `vendor-react` | 191 KB | 60 KB |
| `is-prop-valid_framer-motion` | 93 KB | 30 KB |
| `useWebSocket` | 50 KB | 17 KB |
| `RoboticEye` | 41 KB | 12 KB |
| `vendor-motion` | 32 KB | 11 KB |
| `core-ui` | 27 KB | 7 KB |
| `page-neural-graph` | 25 KB | 8 KB |
| `Dashboard` | 22 KB | 7 KB |
| `page-others` | 22 KB | 7 KB |
| `page-settings` | 21 KB | 6 KB |
| `index` | 15 KB | 6 KB |
| `MoneyModePage` | 12 KB | 4 KB |
| `MemoryPage` | 13 KB | 5 KB |
| `NexusOSDashboard` | 14 KB | 4 KB |
| `KnowledgePage` | 10 KB | 4 KB |
| `OperationsPage` | 9 KB | 3 KB |
| `AgentsPage` | 8 KB | 3 KB |
| `CognitionPage` | 8 KB | 3 KB |
| `ResearchPage` | 6 KB | 2 KB |
| `KPITile` | 5 KB | 2 KB |
| (other pages) | 3-5 KB | 1-2 KB |

- Three.js loaded **only** when `NeuralNetworkPage` mounts
- All other pages target <2.5s first paint
- WS is primary data source; REST polling only when `!wsConnected` (8s interval)
- `appStore.backendStatus` persisted to localStorage
- `useChannelState` flips visual to STALE/OFFLINE when data goes silent

---

## 27. WORKING ON THIS CODEBASE

### DO

- **Run `npm run build` from `frontend/`** after any frontend change to verify rolldown parses (catches en-dash bugs, unclosed JSX, etc.)
- **Add new pages** by: lazy import in `Dashboard.jsx` + entry in `PAGES` map + Sidebar nav item
- **Use existing Zustand stores** — add fields, don't add new stores
- **Use Nexus-UI primitives** (Panel, KPITile, StatusPill, etc.) for visual consistency
- **Follow the 3-layer model** — tools never called directly from LLM, skills wrap them, orchestrator routes
- **Keep all design tokens in `tokens.css`** — never hardcode colors
- **Test multi-tenant isolation** when touching state file access
- **Always lock state files** via `runtime/core/file_lock.py`
- **Register new agents** in `runtime/config/agent_capabilities.json` and add a directory under `runtime/agents/<name>/` with `<name>.py`, `run.sh`, `requirements.txt`
- **Emit events through `runtime/neural_brain/utils/event_bus.py`** so the frontend gets updates

### DON'T

- **Don't bypass the orchestrator** and let the LLM call tools directly
- **Don't write to `state/*.json` without `file_lock`** — concurrent writes will corrupt state
- **Don't use a chart library** — pure SVG only
- **Don't use em-dash `—` or en-dash `–` inside JS string literals** — they parse but copy-paste bugs have bitten us; prefer ASCII `-`
- **Don't add framework-level deps** without a clear performance/UX justification
- **Don't modify `RoboticEye.jsx` core layer order** — Z1..Z10 must remain consistent
- **Don't add comments that say what the code says** — only WHY, not WHAT (CLAUDE.md PULSE rules)
- **Don't write `// removed code` comments** — git remembers
- **Don't introduce new HTTP routes without authorization decision** — default to `requireAuth`
- **Don't commit `.env` or `~/.ai-employee/.env`** — secrets only live there
- **Don't bypass HITL gates** for high-risk agents (`hr-manager`, `recruiter`, etc.) — they must require human approval

---

## 28. PROJECT STATE — 2026-05-16

- ✅ Backend: Python SSE → Node bridge → WS bus working
- ✅ Multi-tenancy: 10/10 tests passing
- ✅ Frontend: all 20 pages built and routed
- ✅ RoboticEye: fully integrated with sub-components + data hooks
- ✅ Security: all 4 tabs route to one tabbed `SecurityPanel` (no longer duplicate pages)
- ✅ CommandDock: always visible on every page including Settings
- ✅ NeuralNetworkPage: seeds 12 demo nodes when backend snapshot is empty
- ✅ CommandPalette (Cmd-K) mounted globally
- ✅ Build clean: 1123 modules transformed, no errors
- ⏳ Polish pass: empty states + loading skeletons (in progress per page)
- ⏳ Three.js bundle reduction — currently 723KB core + 193KB extras; consider lazy chunk
- ⏳ Postgres migration for state files (Week 4 plan)

**Branch:** `wavefield-routing`. Main: `main`.

---

## 29. FILE-BY-FILE MAP

Critical files (read these for full mental model):

### Top-level
- `start.sh` — boot script
- `stop.sh` — shutdown script
- `package.json` — Node deps + scripts
- `CLAUDE.md` — project instructions + PULSE token-efficiency protocol
- `SYSTEM.md` — this file
- `README.md` — user-facing intro

### Node backend (`backend/`)
- `server.js` — Express + WS server (4000+ lines, 142 routes)
- `tenancy.js` — tenant middleware for Express
- `routing.js` — route helpers
- `persistence.js` — file-locked JSON access
- `money_mode.js` — Node-side money mode coordinator
- `database.js` — SQLite helpers
- `agents/index.js` — agent catalog loader
- `orchestrator/` — task routing
- `bridges/python_metrics_bridge.js` — Python SSE → WS broadcaster
- `events/broadcaster.js` — WS broadcast helper
- `events/schema.js` — event name constants
- `security/` — secrets vault, gateway protector, anomaly responder
- `gateway/` — API gateway
- `subsystems/` — node-side subsystems
- `middleware/` — Express middleware (auth, tenancy, rate limit)

### Python runtime (`runtime/`)
- `main.py` — entry point (inserts `runtime/` into sys.path)
- `start.sh` / `stop.sh` — runtime-level boot/stop
- `core/agent_controller.py` — orchestrator
- `core/contracts.py` — TaskNode, TaskGraph, ValidationResult
- `core/orchestrator.py` — LLMClient
- `core/unified_pipeline.py` — 10-phase pipeline
- `core/bus.py` — SimpleMessageBus
- `core/hitl_gate.py` — Human-In-The-Loop gate
- `core/money_mode.py` — 3 monetization pipelines
- `core/tenancy.py` — TenantManager
- `core/tenant_middleware.py` — FastAPI tenant middleware
- `core/file_lock.py` — fcntl exclusive locks
- `core/self_evolution/` — evolution_controller, patch_generator, patch_validator, safe_deployer
- `core/observability/metrics_collector.py` — Prometheus metrics
- `core/observability/event_stream.py` — pub/sub + JSONL
- `engine/api.py` — LLM engine public surface
- `memory/memory_router.py` — memory routing
- `skills/catalog.py` — skill registry
- `skills/library.py` — skill loader
- `neural_brain/utils/event_bus.py` — event publish/subscribe
- `neural_brain/workflows/nodes.py` — reasoning step emitters
- `neural_brain/memory/neural_memory_manager.py` — memory write events
- `neural_brain/telemetry/sanitizer.py` — PII scrubbing
- `neural_brain/telemetry/local_analyzer.py` — pattern detection
- `neural_brain/security/blacklight_engine.py` — anomaly detection
- `agents/base.py` — BaseAgent class
- `agents/<name>/` — one directory per agent (121 total)
- `agents/problem-solver-ui/server.py` — FastAPI server (20k+ lines)
- `config/agent_capabilities.json` — 89 registered agents
- `config/agent_behavior_templates.json` — behavior templates
- `config/skills_library.json` — 147 skills

### Frontend (`frontend/`)
- `src/App.jsx` — root + router
- `src/index.css` — global styles, imports tokens.css
- `src/config/api.js` — API_URL config
- `src/components/Dashboard.jsx` — layout shell + page routing
- `src/components/BootSequence.jsx` — boot animation
- `src/components/ErrorBoundary.jsx` — error boundary
- `src/components/core/RoboticEye.jsx` — the eye
- `src/components/core/eye/*.jsx` — eye sub-components
- `src/components/core/ChatPanel.jsx` — slide-in chat
- `src/components/core/CentralCognitiveCore.jsx` — orchestrator UI
- `src/components/layout/Sidebar.jsx` — sidebar nav with grouped sections
- `src/components/layout/ContextPanel.jsx` — right rail
- `src/components/dashboard/TopBar.jsx` — top status bar
- `src/components/dashboard/BrainInsightsPanel.jsx`
- `src/components/dashboard/HistoryPanel.jsx`
- `src/components/dashboard/MiddlewareStatusWidget.jsx`
- `src/components/dashboard/NeuralNetworkPanel.jsx`
- `src/components/dashboard/ObservabilityDashboard.jsx`
- `src/components/dashboard/SelfImprovementPanel.jsx`
- `src/components/dashboard/AgentGrid.jsx` (in pages/)
- `src/components/dashboard/QuickActions.jsx` (in pages/)
- `src/components/dashboard/CurrentObjective.jsx` (in pages/)
- `src/components/dashboard/CognitiveStream.jsx` (in pages/)
- `src/components/dashboard/TaskPipeline.jsx` (in pages/)
- `src/components/dashboard/SystemTelemetry.jsx` (in pages/)
- `src/components/dock/CommandDock.jsx` — bottom command bar
- `src/components/dock/BottomDrawer.jsx` — task pipeline drawer
- `src/components/ui/CommandPalette.jsx` — Cmd-K modal
- `src/components/nexus-ui/*` — design system primitives + tokens.css
- `src/components/pages/*.jsx` — all 20 pages (+ retired legacy files)
- `src/components/three/DataStreamHighway.jsx` — 3D effect
- `src/components/workspace/FileUploadZone.jsx`
- `src/store/*.js` — Zustand stores (9 stores)
- `src/hooks/*.js` — custom hooks (17 hooks)

### Tests (`tests/`)
- `test_multitenant.py` — 10 tests, all passing
- `test_<name>.py` — per-feature tests
- `runtime/agents/agent_selftest.py` — agent self-tests
- `runtime/agents/smoke_test_agent.py` — smoke tests

### State (`state/`)
- `deals.json`, `tasks.json`, `team-roster.json`, `knowledge_store.json`, `leads.json`, `revenue.json`
- `bus.jsonl`, `llm_calls.jsonl`
- `audit.db`, `forge_queue.db`
- `python-backend.log`, `version.json`

### Per-tenant data (`~/.ai-employee/`)
- `.env` — secrets, API keys, JWT_SECRET_KEY
- `tenants/{tenant_id}/state/` — tenant state files
- `tenants/{tenant_id}/config/` — tenant config

---

## 30. HOW TO ONBOARD AS A NEW AI

Read these files in this order:

1. **`CLAUDE.md`** — project instructions, PULSE token-efficiency protocol (40% of mental model)
2. **`SYSTEM.md`** (this file) — full architectural map (90% of mental model)
3. **`frontend/src/components/Dashboard.jsx`** — see how routing works (95%)
4. **`frontend/src/hooks/useWebSocket.js`** — see the entire WS event taxonomy in action (98%)
5. **`runtime/core/agent_controller.py`** + **`runtime/core/contracts.py`** — orchestrator + task contracts (100%)

If you only have 60 seconds, read:
- Section 3 (3-layer model)
- Section 4 (10-phase pipeline)
- Section 17 (WS event taxonomy)
- Section 22 (the 20 pages)
- Section 27 (do/don't)

If you're touching the frontend, additionally:
- Section 18 (design system)
- Section 19 (Zustand stores)
- Section 22 (the 20 pages)
- Section 24 (RoboticEye)

If you're touching the backend:
- Section 5 (core runtime modules)
- Section 6 (task contracts)
- Section 7 (agent catalog)
- Section 9 (persistence)
- Section 10 (multi-tenancy)
- Section 15 (Node routes)

**One last rule:** This is a real-world execution engine, not an assistant. Every change should make the system produce better real-world outcomes per token spent. Don't over-engineer. Don't add hypothetical abstractions. Don't write code for future requirements that don't exist yet. Ship the right thing.

---

*End of SYSTEM.md*
