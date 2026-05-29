# AI-EMPLOYEE Module Map
**Generated**: 2026-05-26 | **Branch**: wavefield-routing

Status flags: 🟢 Real+Connected | 🟡 Stub/Demo | 🔴 Broken/Crash | ⚪ Dead code

---

## Layer 0: Desktop Shell

```
launcher/
├── main.js                         🟢  Electron main process (1,127 lines)
│   ├── src/backend.js              🟢  Spawns start.sh, crash detection, auto-restart
│   ├── src/health.js               🟢  HTTP probes: /api/health, port-bound detection
│   ├── src/phases.js               🟢  7-phase boot tracker with EventEmitter
│   ├── src/paths.js                🟢  PATHS constants (repoDir, appHome, stateDir, logDir)
│   ├── src/first_boot.js           🟢  Dependency check, native module ABI fix
│   ├── src/render-prefs.js         🟢  WebGL mode persistence (auto/hardware/software)
│   ├── src/policy.js               🟢  Offline-first policy loader
│   ├── src/update.js               🟢  electron-updater wiring (conditional on policy)
│   └── src/log.js                  🟢  Disk boot logger (pre-window)
├── preload.js                      🟢  contextBridge IPC surface (v4, 35 methods)
└── renderer/                       🟢  Launcher UI (boot console, phase rail)
```

**Security**: `contextIsolation: true`, `nodeIntegration: false` on both windows.

---

## Layer 1: Node.js Gateway (port 8787)

```
backend/
├── server.js                       🟢  Express + WebSocket, ~7,400 lines, ~198 routes
│   ├── requireAuth()               🟡  JWT middleware — covers ~49% of routes
│   ├── helmet CSP                  🟡  unsafe-inline in script-src
│   ├── tenantMiddleware()          🟢  Multi-tenant JWT claim extraction
│   ├── injectRole()                🟢  RBAC role injection from JWT claims
│   └── enforceRegion()             🟢  Data residency 451 enforcement
│
├── agents/index.js                 🟢  Agent catalog loader (agent_capabilities.json)
├── orchestrator/                   🟢  Task routing to Python backend
│   └── routing.js                  🟢  Route /api/chat → Python :18790
│
├── security/
│   ├── secrets.js                  🟢  JWT_SECRET_KEY management
│   ├── secrets-rotation.js         🟢  Key rotation logic
│   ├── blacklight_tools.js         🟢  60+ OSINT tool definitions with mode gating
│   ├── anomaly_response.js         🟢  Threat response actions
│   ├── api_gateway.js              🟢  Rate limiting, API gateway
│   ├── sentinel_guard.js           🟢  Security event forwarding
│   ├── offline_sync_policy.js      🟢  Offline-first policy enforcement
│   └── security_event_forwarder.js 🟢  Bridge to Python security events
│
├── compute_fabric/index.js         🟡  GPU rental planning (all providers disabled)
├── money_mode.js                   🟡  Money mode bridge to Python
├── brain/                          🟢  Neural brain HTTP bridge
├── gateway/                        🟢  API gateway protector
├── services/
│   └── voice/
│       ├── tts_engine.js           🟡  TTS stub (modified on current branch)
│       └── fish_speech.js          🟡  Fish Speech integration (untracked file)
│
├── routes/
│   ├── forge.js                    🟢  Ascend Forge routes (requireAuth)
│   ├── compute.js                  🟢  Compute fabric routes (requireAuth)
│   ├── workflows.js                🟢  Workflow routes (requireAuth)
│   ├── sessions.js                 🟢  Session management (requireAuth)
│   ├── api-keys.js                 🟢  API key management (requireAuth)
│   ├── fork-integrations.js        🟢  Integration routes (requireAuth)
│   └── dashboard-api.js            🟢  Dashboard data routes (requireAuth)
│
├── api/
│   └── voice.js                    🟡  Voice API (modified on current branch)
│
└── subsystems/                     🟢  System health, metrics, observability bridge
```

**Unprotected sensitive routes** (no `requireAuth`):
- `DELETE /api/neural-brain/memory/:id`
- `POST /api/workspace/upload` ← Critical: file upload, no auth
- `GET /api/audit/events` and `/api/audit/stats`
- `GET /api/blacklight/status` and `/api/blacklight/alerts`
- `GET /api/workspace/files`
- `GET /api/history`, `GET /api/tasks/:taskId`

---

## Layer 2: Python AI Backend (port 18790)

```
runtime/agents/problem-solver-ui/
├── server.py                       🟢  FastAPI monolith (27,000+ lines, 382 endpoints)
│   ├── /health                     🟢  Liveness endpoint
│   ├── /health/detail              🟢  Detailed subsystem health
│   ├── /auth/register              🟢  JWT registration (rate-limited)
│   ├── /auth/login                 🟢  JWT login (rate-limited)
│   ├── /auth/refresh               🟢  Token rotation
│   ├── /auth/logout                🟢  Token invalidation
│   ├── /api/break-glass/*          🟢  Emergency access gate
│   ├── /api/chat (GET)             🟢  Chat endpoint (proxied from Node)
│   ├── /ws                         🟢  WebSocket (internal events)
│   ├── /api/events (SSE)           🟢  Server-Sent Events for dashboard
│   └── ... (370+ more)             🟢
├── security.py                     🟢  Auth/JWT implementation
├── config_manager.py               🟢  Agent configuration management
└── routes/                         🟢  Feature router modules (16 loaded)
```

---

## Layer 3: Core Runtime

```
runtime/core/
├── unified_pipeline.py             🟢  10-phase enforced pipeline (INPUT→OUTPUT)
├── agent_controller.py             🟢  AgentController (Planner→Executor→Validator)
├── orchestrator.py                 🟢  LLMClient (Anthropic/Ollama/OpenRouter)
│   └── wavefield_provider.py       🟢  Shadow routing + fallback (current branch)
├── llm_router.py                   🟢  Model routing config reader
├── llm_provider_router.py          🟢  Provider selection with health tracking
├── model_routing.py                🟢  Task-type → provider/model selection
├── contracts.py                    🟢  TaskGraph/TaskNode dataclasses
├── bus.py                          🟢  SimpleMessageBus (in-process pub/sub + JSONL)
├── hitl_gate.py                    🟢  Human-in-the-Loop approval gate
├── money_mode.py                   🔴  Three pipelines: LLM real, lead/outreach stubs
├── real_execution_engine.py        🟢  Strict tool-call loop (no fake results)
├── tool_registry.py                🟢  Tool registration + dispatch
├── planner.py                      🟢  LLM-driven task planning
│
├── security/
│   ├── sandbox_manager.py          🟡  RestrictedPython subprocess (no cgroup/netns)
│   ├── security_layer.py           🟢  Input validation, threat detection
│   ├── break_glass.py              🟢  Emergency access protocol
│   └── rbac.py / rbac_middleware.py 🟢  Role-based access control
│
├── self_evolution/
│   ├── evolution_controller.py     🟡  Controls AUTO/SAFE/OFF mode
│   ├── patch_generator.py          🟡  LLM-generated patches
│   ├── patch_validator.py          🟡  Syntax/test validation
│   └── safe_deployer.py            🔴  `subprocess.run(apply_cmd)` — no patch signing
│
├── observability/
│   ├── metrics_collector.py        🟢  1Hz metrics tick (fixed QueueFull loop)
│   ├── event_stream.py             🟢  SQLite pub/sub (no TTL — unbounded growth)
│   ├── anomaly_detector.py         🟢  Statistical anomaly detection
│   └── trace_logger.py             🟢  Distributed trace logging
│
├── auto_research_agent.py          🟢  3-hop web research (Brave/Bing/Wikipedia)
├── context_evaluator.py            🟢  Context sufficiency scoring
├── tenancy.py                      🟢  Multi-tenant lifecycle manager
├── tenant_middleware.py            🟢  FastAPI tenant extraction middleware
├── file_lock.py                    🟢  fcntl-based exclusive locking
├── audit.py / audit_engine.py      🟢  GDPR-compliant audit trail → SQLite
├── cost_ledger.py                  🟢  LLM cost tracking + budget enforcement
├── stripe_integration.py           🟡  Stripe SDK (key not configured)
└── source_trust.py                 🟢  Per-source trust scoring for research
```

---

## Layer 4: Neural Brain

```
runtime/neural_brain/
├── core/
│   ├── brain_state.py              🟢  Global brain state management
│   ├── consciousness_engine.py     🟢  Cognition loop + feature flag gating
│   ├── feature_flags.py            🟢  Runtime feature toggle system
│   ├── intent_classifier.py        🟢  Intent detection (LLM-backed)
│   ├── reasoning_trace.py          🟢  Chain-of-thought trace recorder
│   ├── task_queue.py               🟢  Priority task queue
│   ├── health_monitor.py           🟢  Per-arch health blacklist
│   └── telemetry.py                🟢  Neural brain telemetry
│
├── models/
│   ├── model_architecture_router.py 🟢  8-arch dispatcher (retry/backoff)
│   ├── model_resolver.py           🟢  Hardware-aware model selection (Ollama)
│   ├── llm_backend.py              🟢  LLM → orchestrator.LLMClient
│   ├── slm_backend.py              🟢  SLM → Ollama phi3/qwen2.5
│   ├── moe_backend.py              🟢  MoE → Ollama mixtral/qwen2.5-moe
│   ├── vlm_backend.py              🟢  VLM → Ollama moondream/qwen2.5-vl
│   ├── lam_backend.py              🟢  LAM → Ollama qwen2.5-coder/llama3.1
│   ├── mlm_backend.py              🟢  MLM → Ollama embeddings
│   ├── sam_backend.py              🟡  SAM → auto-download checkpoint (offline risk)
│   ├── lcm_backend.py              🟡  LCM → diffusers (GPU required, auto-download)
│   ├── performance_tracker.py      🟢  Per-arch latency/success tracking
│   ├── lifecycle_manager.py        🟢  Model load/unload lifecycle
│   └── model_registry.json         🟢  Architecture preference configuration
│
├── memory/
│   ├── chroma_adapter.py           🔴  ChromaDB adapter (collections empty, no ingest)
│   ├── embedding_provider.py       🟢  Embedding abstraction layer
│   ├── memory_manager.py           🟢  Memory lifecycle management
│   └── memory_schemas.py           🟢  MemoryItem/RecallHit dataclasses
│
├── graph/
│   ├── native_graph_store.py       🟢  SQLite-backed graph (real data)
│   ├── neo4j_adapter.py            🟡  Neo4j adapter (minimal data)
│   ├── brain_graph.py              🟢  Graph query + traversal
│   ├── extractors.py               🟡  Entity extraction (some TODO stubs)
│   └── memory_graphs.py            🟡  Graph memory integration (some TODO stubs)
│
├── workflows/
│   ├── deep_reasoning_graph.py     🟢  LangGraph-style reasoning workflow
│   └── nodes.py                    🟢  Workflow node implementations
│
├── api/
│   ├── model_fabric_router.py      🟢  Model fabric REST API
│   └── auth_router.py              🟢  Neural brain auth integration
│
└── forge/
    └── builder.py                  🟡  Self-modification builder (some TODO stubs)
```

---

## Layer 5: Memory System

```
runtime/memory/
├── memory_router.py                🟢  Unified memory interface (episodic/semantic/procedural)
│   ├── → vector_store.py           🟡  JSON TF-IDF store (sparse embeddings, not semantic)
│   ├── → short_term_cache.py       🟢  In-process TTL cache
│   ├── → strategy_store.py         🟢  Learning outcome store
│   └── → NativeGraphStore          🟢  SQLite graph (when available)
├── memory_adapter.py               🟢  ChromaDB/JSON adapter selector
├── vault.py                        🟢  Encrypted secret storage
├── topic_intelligence.py           🟢  Topic-based knowledge clustering
└── vector_store.py                 🟡  JSON vector store backend

State:
├── state/vector_store.json         🟡  18 entries, sparse TF-IDF embeddings
├── state/knowledge_store.json      🟢  Real research data ({topics: {...}})
├── state/native_memory_graph.db    🟢  SQLite graph (non-empty)
├── state/neural_brain/chroma/      🔴  ChromaDB directory (empty — 4KB)
└── state/neural_brain/neo4j/       🟡  Neo4j data (16KB, minimal)
```

---

## Layer 6: Agent Catalog

```
runtime/agents/  (116 directories, 158 Python files)
├── Active (Power mode, 56+)
│   ├── problem-solver-ui/          🟢  Python AI backend + 382 endpoints
│   ├── lead-hunter-elite/          🟢  Lead generation (HITL-gated)
│   ├── email-ninja/                🟢  Email outreach
│   ├── crm-pipeline/               🟢  CRM deal management
│   ├── analytics-bi/               🟢  Business intelligence
│   ├── blacklight/                 🟢  Security monitoring (OSINT)
│   ├── ascend-forge/               🟢  Self-improvement pipeline
│   ├── ai-router/                  🟢  Request routing
│   ├── turbo-quant/                🟡  Model quantization (Ollama-delegated)
│   ├── polymarket-trader/          🔴  Trading agent (order methods NotImplementedError)
│   └── ... (100+ more)             🟢  Most are LLM-backed skill executors
│
├── Base framework
│   └── base.py                     🟢  BaseAgent with abstract run() method
│
└── Config
    ├── runtime/config/agent_capabilities.json  🟢  Agent registry (loaded by Node)
    └── runtime/config/agent_behavior_templates.json 🟢  Behavior templates
```

---

## Layer 7: Observability + State

```
State files (canonical: ~/.ai-employee/state/, 115 files):
├── audit.db                        🟢  SQLite audit trail (WAL mode)
├── forge_queue.db                  🟢  Task queue SQLite (WAL mode)
├── bus.jsonl                       🟢  Message bus event log (3.2MB, append-only)
├── knowledge_store.json            🟢  Research knowledge base
├── vector_store.json               🟡  TF-IDF vectors (not semantic)
├── memory_index.json               🟢  Memory index (93KB)
├── learning_engine.json            🟢  Learning data (4.97MB — large)
├── telemetry.jsonl                 🟢  Telemetry log (17.2MB — no rotation)
└── [100+ agent state files]        🟢  Per-agent state persistence

State files (repo: AI-EMPLOYEE/state/, 46 files):
├── observability_events.db         🟢  Event stream SQLite (18.7MB — no TTL)
├── boot_metrics.json               🟢  Boot timing records (last 20)
├── native_memory_graph.db          🟢  Graph store SQLite
├── llm_calls.jsonl                 🟢  LLM call audit log (9KB)
└── python-backend.log.*.log        🔴  12GB orphaned crash log (DELETE)

Prometheus metrics:
└── GET /metrics (port 8787)        🟢  ai_employee_* metrics in text format
```

---

## Data Flow Map

```
User (Browser/Electron)
        │
        ▼
[Electron launcher/main.js]
        │ opens
        ▼
[React SPA — frontend/dist/] ◄──── [Vite dev server :5173] (dev only)
        │ HTTP/WebSocket
        ▼
[Node.js Gateway :8787 — backend/server.js]
        │                           │
        ├── /api/chat ──────────────┤
        │                           │
        ▼                           ▼
[Python AI Backend :18790]    [Direct Node handlers]
[FastAPI/uvicorn]                   │
        │                     [SQLite: audit.db]
        │                     [~/.ai-employee/state/]
        ├── LLMClient
        │       ├── Anthropic API (cloud)
        │       ├── Ollama :11434 (local)
        │       └── OpenRouter (cloud)
        │
        ├── AgentController
        │       └── unified_pipeline.py (10 phases)
        │               └── tool_registry → agent tools
        │
        ├── MemoryRouter
        │       ├── ShortTermCache (in-process)
        │       ├── VectorStore (JSON/TF-IDF) ← ChromaDB (empty)
        │       ├── NativeGraphStore (SQLite)
        │       └── StrategyStore
        │
        ├── NeuralBrain
        │       ├── ModelArchitectureRouter
        │       │       └── [LLM|SLM|MoE|VLM|LAM|MLM|SAM|LCM] backends
        │       │               └── Ollama :11434 (primary)
        │       └── NativeGraphStore (SQLite)
        │
        ├── AutoResearchAgent
        │       ├── Brave/Bing/Wikipedia (web)
        │       └── → knowledge_store.json + vector_store
        │
        ├── MetricsCollector (1Hz thread)
        │       └── EventStream → observability_events.db (SQLite)
        │               └── SSE → Node → WebSocket → React
        │
        └── SelfEvolution (EVOLUTION_MODE=AUTO/SAFE/OFF)
                ├── PatchGenerator → LLM
                ├── PatchValidator → pytest
                └── SafeDeployer → subprocess.run (no patch signing)

Money Mode pipelines:
[run_content_pipeline] → LLM → ActionBus → [social APIs — NOT WIRED]
[run_lead_pipeline]    → arithmetic stub (no real scraping)
[run_outreach_pipeline]→ hardcoded rates (no real sends)

Remote Compute (all disabled):
[compute_fabric/index.js] → nvidia-smi (real) → [RunPod/Vast.ai/Lambda — disabled]
```

---

## Dependency Web: What Breaks If X Is Down

| Service | Dependents | Degradation |
|---------|-----------|-------------|
| Anthropic API | LLMClient, AgentController, AutoResearch | Falls back to Ollama if available; keyword replies if neither |
| Ollama :11434 | All 8 neural brain backends, LLM fallback | Falls back to Anthropic; SAM/LCM/VLM fully broken |
| Python backend :18790 | Chat, task execution, agent control, memory | Node serves dashboard but chat returns placeholder replies |
| Node gateway :8787 | All frontend features | Frontend blank (Electron shows diagnostics) |
| SQLite (audit.db) | Audit trail, compliance logging | Non-fatal — logged to file instead |
| ChromaDB | RAG retrieval | Falls back to JSON TF-IDF (already the default) |
| Neo4j | Graph queries | Falls back to NativeGraphStore SQLite |
| Brave/Bing APIs | AutoResearchAgent | Falls back to Wikipedia only |

---

## Component Counts

| Layer | Total Components | 🟢 Real | 🟡 Stub | 🔴 Broken | ⚪ Dead |
|-------|-----------------|--------|--------|----------|--------|
| Electron shell | 9 | 8 | 1 | 0 | 0 |
| Node gateway | 25 | 18 | 5 | 2 | 0 |
| Python backend | 15 | 11 | 2 | 2 | 0 |
| Core runtime | 20 | 15 | 3 | 2 | 0 |
| Neural brain | 24 | 18 | 4 | 2 | 0 |
| Memory system | 8 | 4 | 3 | 1 | 0 |
| Agent catalog | 116 dirs | ~100 | ~12 | 4 | 0 |
| State/Observability | 12 | 9 | 1 | 2 | 0 |
| **Total** | **229** | **~183 (80%)** | **~31 (13%)** | **~15 (7%)** | **0** |
