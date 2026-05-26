# TARGET ARCHITECTURE — AI Operating System

> Status: Design document. Implementation phases tracked in master plan.

---

## Data Flow (top-level)

```
User Input (chat / task / voice / UI action)
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  CENTRAL ORCHESTRATOR  (runtime/core/orchestrator.py)            │
│  1. Classify intent (chat / task / research / forge / money)     │
│  2. Score context sufficiency via ContextSufficiencyEvaluator    │
│  3. Retrieve relevant memory (MemoryManager)                     │
│  4. Select model via LLMRouter                                   │
│  5. Build task plan (Planner → TaskGraph)                        │
│  6. Gate at HITL if risk level ≥ 2                               │
│  7. Execute via RealExecutionEngine + ToolRegistry               │
│  8. Verify output (validator.py)                                  │
│  9. Persist useful memory (MemoryRouter)                         │
│ 10. Broadcast state to UI (EventBus → WebSocket)                 │
└──────────────────────────────────────────────────────────────────┘
    │              │              │              │
    ▼              ▼              ▼              ▼
MemoryManager  LLMRouter    ToolRegistry   AgentManager
(14 stores)   (6 providers) (atomic tools) (14 agent types)
    │              │              │              │
    ▼              ▼              ▼              ▼
VectorStore   ModelRuntime  ExecutionEngine  SkillRegistry
(Chroma)      (local/API)   (5 risk levels)  (composed skills)
    │
    ▼
Neo4j KnowledgeGraph  ←→  RAGEngine (hybrid search + rerank)
```

---

## Layer Definitions

### Layer 1 — Desktop Shell

| Property | Value |
|----------|-------|
| Current | Electron (`launcher/`) |
| Target | **Tauri v2** (pending audit decision — see `docs/AUDIT.md`) |
| Responsibility | Window management, secure IPC, process supervisor, tray |
| Key rule | Never blocks on AI work. All AI calls go through IPC to backend. |
| Secrets | Encrypted vault via Rust `keyring` crate (replaces plain `.env`) |

### Layer 2 — Core Orchestration (Rust, if Tauri path)

| Component | Responsibility |
|-----------|---------------|
| Process supervisor | Start/stop/restart Python engines, health polling |
| Secrets broker | Encrypted config, API keys, never in env vars |
| Tauri command bridge | `invoke('chat', payload)` → IPC to Python/Node |
| Health monitor | Broadcasts `system:health` events to UI every 5s |

### Layer 3 — Node.js Backend (port 8787)

Serves frontend, handles all `/api/*`, proxies AI calls to Python.

| Module | Path | Status |
|--------|------|--------|
| Main routes | `backend/routes/dashboard-api.js` | 🟢 Live |
| Agent catalog | `backend/agents/index.js` | 🟢 Live |
| WebSocket broadcaster | `backend/events/broadcaster.js` | 🟢 Live |
| Voice (Fish Speech) | `backend/api/voice.js` | 🟢 Live |
| Ollama admin | `backend/services/ollama_admin.js` | 🟢 Live |
| Security (RBAC) | `backend/security/` | 🟡 Partial |
| Audit logger | `backend/infra/secrets/broker.js` | 🟢 Live |

### Layer 4 — Python AI Engine (port 18790)

FastAPI/uvicorn. All LLM work happens here.

| Module | Path | Status |
|--------|------|--------|
| Main server | `runtime/agents/problem-solver-ui/server.py` | 🟢 Live |
| Orchestrator | `runtime/core/orchestrator.py` | 🟢 Live |
| LLM Router | `runtime/core/llm_router.py` | 🟢 Live (6 providers) |
| Real Execution Engine | `runtime/core/real_execution_engine.py` | 🟢 Live |
| HITL Gate | `runtime/core/hitl_gate.py` | 🟢 Live |
| Tool Registry | `runtime/core/tool_registry.py` | 🟢 Live (635 LOC) |
| Skill Registry | `runtime/core/skill_registry.py` | 🟢 Live (862 LOC) |
| Memory Router | `runtime/memory/memory_router.py` | 🟢 Live |
| Auto Research Agent | `runtime/core/auto_research_agent.py` | 🟢 Live |
| Knowledge Store | `runtime/core/knowledge_store.py` | 🟢 Live |
| Money Mode | `runtime/core/money_mode.py` | 🟡 Partial |
| Self Evolution | `runtime/core/self_evolution/` | 🟡 Partial |

### Layer 5 — Memory System

14 memory types, all routed through `runtime/memory/memory_router.py`:

| Type | Store | TTL | Vector indexed |
|------|-------|-----|----------------|
| Session (short-term) | `short_term_cache.py` | 10 min | No |
| Long-term user | `vector_store.py` + Chroma | ∞ | Yes |
| Project | `vault.py` (markdown) | ∞ | Yes |
| Company/business | `strategy_store.py` | ∞ | Yes |
| Skill (what works) | `strategy_store.py` | ∞ | Yes |
| Tool execution history | `pending_queue.py` | 24h | No |
| Research | `vector_store.py` | ∞ | Yes |
| Financial/money | `strategy_store.py` | ∞ | Yes |
| Failure | `strategy_store.py` | ∞ | Yes |
| Decision | `vector_store.py` | ∞ | Yes |
| Preference | `memory_adapter.py` | ∞ | No |
| Knowledge graph | Neo4j | ∞ | Graph |
| Structured DB | SQLite `state/audit.db` | ∞ | No |
| Event timeline | `bus.jsonl` (JSONL) | 30d | No |

### Layer 6 — RAG Engine

```
Document / URL → Ingest → Chunk (512 tok, 10% overlap)
    → Embed (sentence-transformers/all-MiniLM-L6-v2, local)
    → Store (Chroma vector DB)
    → Retrieve: BM25 + vector → fusion score
    → Rerank (cross-encoder, top-10 → top-3)
    → Compress (remove redundant chunks)
    → Inject into LLM context with citations
```

Files: `runtime/core/document_ingestion_pipeline.py`, `runtime/memory/vector_store.py`, `runtime/core/embeddings.py`

### Layer 7 — Model Router

Priority: `subsystem override > agent override > task_type > _default`

| Task type | Default provider | Default model | Fallback |
|-----------|-----------------|---------------|---------|
| coding | nvidia_nim | qwen2.5-coder-32b | claude-sonnet-4-6 |
| reasoning | nvidia_nim | llama-3.3-nemotron-49b | claude-opus-4-7 |
| creative | ollama | gemma4 | claude-sonnet-4-6 |
| analytics | anthropic | claude-opus-4-7 | — |
| bulk | nvidia_nim | llama-3.1-8b | llama3.2 |
| general | ollama | llama3.2 | claude-haiku-4-5 |

Config file: `~/.ai-employee/model-routing.json` (hot-reloaded on `system:config_reload` bus event)

### Layer 8 — Execution Engine (5 Risk Levels)

```
Level 0  Read-only analysis          Always allowed, no approval
Level 1  Local draft/create files    Allowed + logged
Level 2  User-approved local exec    Requires UI approval gate
Level 3  External API/browser        Requires approval + audit trail
Level 4  Financial/public actions    Dual-confirm + reversibility check
Level 5  Blocked unsafe actions      Never allowed
```

Files: `runtime/core/real_execution_engine.py`, `runtime/core/hitl_gate.py`, `runtime/core/sandbox_manager.py`

### Layer 9 — Frontend (React + Vite)

| Page | Component | Status |
|------|-----------|--------|
| Chat | `ChatPage.jsx` | 🟢 |
| Neural Network | `NeuralNetworkPage.jsx` | 🟢 |
| Knowledge | `KnowledgePage.jsx` | 🟢 |
| Research | `ResearchPage.jsx` | 🟢 |
| Models | `ModelsPage.jsx` | 🟢 |
| AscendForge | `AscendForgePage.jsx` | 🟢 |
| Security / Blacklight | `SecurityPanel.jsx` | 🟢 |
| Memory | `MemoryPage.jsx` | 🟡 |
| Money Mode | *(planned)* | 🔴 |
| Roadmap | *(planned)* | 🔴 |

State: Zustand stores (`appStore`, `agentStore`, `cognitiveStore`, `systemStore`, `learningStore`)
Realtime: WebSocket via `useWebSocket.js` hook → 30+ event types

---

## Startup / Shutdown / Recovery Flows

### Startup
```
bash start.sh
  │
  ├─ preflight: Python 3.12, Node, ports free, env OK
  ├─ clean pycache
  ├─ nohup uvicorn server.py → port 18790 (Python AI)
  ├─ nohup node backend/server.js → port 8787 (Node)
  ├─ Node waits for Python readiness (10s timeout → degraded mode)
  └─ Frontend served from frontend/dist/ (pre-built)
```

### Shutdown
```
bash stop.sh → SIGTERM Node + Python PIDs → wait 3s → SIGKILL if needed
```

### Recovery
- Python offline: Node operates in degraded mode (stubs return helpful errors)
- Node crash: restart with `bash start.sh` (restores from state/*.json)
- Memory corruption: `state/*.json.pre-chroma` backups auto-created

---

## Key Invariants (must never be violated)

1. **UI never blocks on AI** — all AI calls are async + WebSocket-streamed
2. **No fake data** — every UI element connects to real data or shows "not connected"
3. **Risk gates enforced** — Level 2+ actions require explicit approval before execution
4. **Memory through router only** — agents never write to stores directly
5. **Model routing centralized** — `LLMRouter` is the single source of truth
6. **Audit everything** — all Level 2+ actions logged to `state/audit.db`
7. **Graceful degradation** — Python offline = degraded mode, not crash

---

## Next Implementation Priorities (Phase 4+)

| Priority | Task | File | Effort |
|----------|------|------|--------|
| P0 | Wire `/api/brain/status` to real orchestrator state | `dashboard-api.js` | 1h |
| P0 | Wire `/api/memory/stats` to real memory counts | `dashboard-api.js` | 1h |
| P1 | Unified `MemoryManager` entry point (14 types) | `runtime/memory/memory_manager.py` | 3h |
| P1 | Money mode pipelines (content, outreach, tracking) | `runtime/core/money_mode.py` | 5h |
| P1 | Roadmap execution engine | `runtime/core/roadmap_engine.py` | 4h |
| P2 | Tauri v2 migration (pending audit decision) | `launcher/` → `src-tauri/` | 15h |
| P2 | Neural brain M1-M8 (LangGraph + Neo4j + Mem0) | `runtime/neural_brain/` | 20h |
| P3 | Nexus OS visual rebuild | `frontend/src/` | 18d |
