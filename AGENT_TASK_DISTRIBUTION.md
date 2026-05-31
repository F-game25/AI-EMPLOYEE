# Parallel Agent Task Distribution

## Current Status: Phase 1.1 (Settings Integration)
Settings UI + backend API created. Need integration + Phase 1-4 parallel execution.

---

## IMMEDIATE BLOCKERS (Do First, Sequential)

### Task 0: Register Settings Route (BLOCKER)
- **Agent**: AF-01 (Backend Architect)
- **Time**: 15 min
- **Action**: Register `/api/settings` route in `backend/server.js`
- **Acceptance**: Route works, test via `/api/settings` GET returns encrypted settings
- **Depends**: None (critical path)

---

## PHASE 1: Dev Features Unlock (Weeks 1-2)

### Task 1.1a: Settings Route Integration + Testing
**Agent**: AF-01 (Backend Architect)  
**Time**: 30 min  
**Files**: `backend/server.js`, test via curl/Postman

Acceptance criteria:
- `GET /api/settings` returns decrypted keys
- `POST /api/settings` saves + encrypts
- `POST /api/settings/test/anthropic` validates connectivity
- All 3 endpoints protected by tenant auth

### Task 1.1b: Frontend Settings UI Polish
**Agent**: UI-02 (Frontend Designer)  
**Time**: 1.5 hours  
**Files**: `frontend/src/components/pages/SettingsPage.jsx`, `SettingsPage.css`

Acceptance criteria:
- Settings page loads without errors
- Fetch on mount populates form
- Test buttons show loading/success/error states
- Save button only enabled when unsaved changes exist
- Visual polish matches Nexus OS theme

### Task 1.2: LLM Provider Routing Logic
**Agent**: PA-03 (Pipeline Architect)  
**Time**: 2 hours  
**Files**: `runtime/core/llm_provider_router.py` (NEW)

Acceptance criteria:
- Routes to Anthropic SDK when provider='anthropic'
- Routes to Ollama when provider='ollama'
- Routes to OpenRouter when provider='openrouter'
- API key sourced from settings (not env vars)
- Fallback chain: preferred → fallback → error

### Task 1.3: Anthropic SDK Integration
**Agent**: AF-02 (AI Engineer)  
**Time**: 3 hours  
**Files**: `runtime/core/anthropic_client.py` (NEW), update `orchestrator.py`

Acceptance criteria:
- Anthropic SDK initialized with user's API key
- Supports all Claude 3.x models (Sonnet, Opus, Haiku)
- Temperature/max tokens sourced from settings
- Streaming responses working
- Error handling for invalid keys

### Task 1.4: Ollama Local Integration
**Agent**: AF-03 (Local LLM Specialist)  
**Time**: 2 hours  
**Files**: `runtime/core/ollama_client.py` (NEW)

Acceptance criteria:
- Connects to Ollama endpoint from settings
- Falls back gracefully if Ollama not running
- Supports llama2, mistral, neural-chat models
- Same streaming/response format as Anthropic
- Health check on startup

### Task 1.5: OpenRouter Fallback
**Agent**: PA-04 (API Integration Specialist)  
**Time**: 1.5 hours  
**Files**: `runtime/core/openrouter_client.py` (NEW)

Acceptance criteria:
- OpenRouter API client working
- Fallback trigger when primary provider unavailable
- Automatic retry logic
- Cost tracking per API call

---

## PHASE 2: File I/O & Codex System (Weeks 3-4)

### Task 2.1: File Upload Backend
**Agent**: AF-04 (Backend File Handler)  
**Time**: 2 hours  
**Files**: `backend/routes/files.js` (NEW), tenant file storage

Acceptance criteria:
- `POST /api/files/upload` accepts multipart/form-data
- Files stored in `~/.ai-employee/tenants/{tenantId}/files/`
- `GET /api/files` lists user's files with metadata
- `DELETE /api/files/{id}` removes file
- File size limits enforced (100MB max)

### Task 2.2: File Upload Frontend
**Agent**: UI-03 (Frontend Component Builder)  
**Time**: 1.5 hours  
**Files**: `frontend/src/components/FileUpload.jsx` (NEW)

Acceptance criteria:
- Drag-drop zone or file picker
- Displays upload progress
- Shows file list with delete buttons
- File preview for text files
- Error handling for oversized files

### Task 2.3: Codex Interface (AI File Modifier)
**Agent**: PA-05 (Codex Integration)  
**Time**: 4 hours  
**Files**: `runtime/core/codex_engine.py` (NEW), `backend/routes/codex.js` (NEW)

Acceptance criteria:
- `POST /api/codex/modify` accepts {fileId, instruction}
- Returns diff (before/after) via frontend
- `POST /api/codex/apply` saves changes
- Support for Python, JavaScript, CSS, Markdown files
- Undo capability (keep original)

### Task 2.4: Codex Frontend UI
**Agent**: UI-04 (Diff Viewer)  
**Time**: 2 hours  
**Files**: `frontend/src/components/CodexEditor.jsx` (NEW)

Acceptance criteria:
- Shows file + modification instruction input
- Displays diff with syntax highlighting
- Approve/reject buttons
- Download modified file
- Undo/revert option

### Task 2.5: AscendForge Full Implementation
**Agent**: AF-05 (Strategic Planning Module)  
**Time**: 5 hours  
**Files**: `runtime/core/ascend_forge.py` (NEW), update `AscendForgePage.jsx`

Acceptance criteria:
- Goal decomposition (3-level breakdown)
- Constraint reasoning (budget/timeline/tools)
- Multi-path strategy planning
- Integration with task executor
- Real-time progress tracking

---

## PHASE 3: Execution Pipeline Visibility (Weeks 5-6)

### Task 3.1: Task Execution Dashboard
**Agent**: AF-06 (Dashboard Engineer)  
**Time**: 3 hours  
**Files**: `frontend/src/components/pages/TaskExecutionPage.jsx` (NEW)

Acceptance criteria:
- Real-time task progress (0% → 100%)
- WebSocket updates
- Phase indicators (1 of 10)
- Agent currently working shown
- Download result when done

### Task 3.2: Agent Activity Monitor
**Agent**: AF-07 (Observability Engineer)  
**Time**: 2 hours  
**Files**: `runtime/core/observability/agent_activity.py` (NEW)

Acceptance criteria:
- Tracks which agents are active
- Logs per-agent execution time
- Captures task start/end events
- Publishes via WebSocket to frontend
- Persists activity log

### Task 3.3: 10-Phase Pipeline Visibility
**Agent**: PA-06 (Pipeline Instrumentation)  
**Time**: 2.5 hours  
**Files**: `runtime/core/unified_pipeline.py` (update for detailed logging)

Acceptance criteria:
- Each phase emits status via message bus
- Frontend receives per-phase updates
- Decision tree visible in UI
- Validation checks logged
- Error recovery shown in real-time

---

## PHASE 4: Settings & Configuration (Weeks 6-7)

### Task 4.1: Advanced Settings Tabs
**Agent**: UI-05 (Settings Specialist)  
**Time**: 2 hours  
**Files**: `frontend/src/components/pages/SettingsPage.jsx` (extend)

Acceptance criteria:
- Agent configuration tab
- Tenant settings tab
- Advanced options tab (rate limiting, timeouts, etc.)
- Per-agent enable/disable toggles
- Help text for all settings

### Task 4.2: Settings Validation & Persistence
**Agent**: AF-08 (Data Integrity)  
**Time**: 1.5 hours  
**Files**: `backend/routes/settings.js` (extend), schema validation

Acceptance criteria:
- Schema validation for all settings
- Atomic writes (no partial saves)
- Backup of previous settings
- Migration for version changes
- Rollback on validation failure

---

## PHASE 5: Payment Integration (Week 8+, OPTIONAL)

### Task 5.1: Stripe Integration (DEFER)
**Agent**: PA-07 (Payment Systems)  
**Time**: 4 hours  
**Status**: DO NOT START YET

---

## PARALLEL EXECUTION MATRIX

```
┌─────────────────────────────────────────────────────────────┐
│ SEQUENTIAL (Blocker)                                        │
├─────────────────────────────────────────────────────────────┤
│ Task 0: Register Settings Route (AF-01) — 15 min           │
└─────────────────────────────────────────────────────────────┘

AFTER Task 0 complete, launch PARALLEL WAVE 1:

┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Task 1.1a            │ Task 1.1b            │ Task 1.2             │
│ Settings Integration │ Settings UI Polish   │ LLM Provider Router  │
│ AF-01 • 30 min       │ UI-02 • 1.5 h        │ PA-03 • 2 h          │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Task 1.3             │ Task 1.4             │ Task 1.5             │
│ Anthropic SDK        │ Ollama Local         │ OpenRouter Fallback  │
│ AF-02 • 3 h          │ AF-03 • 2 h          │ PA-04 • 1.5 h        │
└──────────────────────┴──────────────────────┴──────────────────────┘

PHASE 1 TOTAL: ~12 hours (parallel reduces to ~5 wall-clock hours)

PARALLEL WAVE 2 (after 1.1a complete):

┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Task 2.1             │ Task 2.2             │ Task 2.3             │
│ File Upload Backend  │ File Upload Frontend │ Codex Engine         │
│ AF-04 • 2 h          │ UI-03 • 1.5 h        │ PA-05 • 4 h          │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Task 2.4             │ Task 2.5             │                      │
│ Codex Frontend UI    │ AscendForge Full     │                      │
│ UI-04 • 2 h          │ AF-05 • 5 h          │                      │
└──────────────────────┴──────────────────────┴──────────────────────┘

PHASE 2 TOTAL: ~14.5 hours (parallel reduces to ~5 wall-clock hours)

PARALLEL WAVE 3 (after 2.1 + 2.3 complete):

┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Task 3.1             │ Task 3.2             │ Task 3.3             │
│ Task Execution UI    │ Agent Activity       │ 10-Phase Pipeline    │
│ AF-06 • 3 h          │ AF-07 • 2 h          │ PA-06 • 2.5 h        │
└──────────────────────┴──────────────────────┴──────────────────────┘

PHASE 3 TOTAL: ~7.5 hours (parallel reduces to ~3 wall-clock hours)

SEQUENTIAL (after all above complete):

┌─────────────────────────────────────────────────────────────┐
│ Task 4.1: Advanced Settings (UI-05) — 2 h                  │
│ Task 4.2: Settings Validation (AF-08) — 1.5 h              │
├─────────────────────────────────────────────────────────────┤
│ PHASE 4 TOTAL: ~3.5 hours                                   │
└─────────────────────────────────────────────────────────────┘

DEFER to Week 8+:
- Task 5.1: Stripe Integration (PA-07)
```

---

## CRITICAL PATH SUMMARY

- **Task 0**: 15 min (blocker)
- **Phase 1**: 12 h (5 h parallel) → User can input API keys, select LLM provider
- **Phase 2**: 14.5 h (5 h parallel) → File upload + Codex + AscendForge
- **Phase 3**: 7.5 h (3 h parallel) → Real-time execution visibility
- **Phase 4**: 3.5 h → Complete settings polish
- **Total**: 37.5 h (~16 h wall-clock with parallelization)

**By end of Phase 4: Fully functional AI system the user controls.**

---

## Agent Assignments

| Agent | Role | Load |
|-------|------|------|
| AF-01 | Backend Architect | 0.75 h (blocker critical) |
| AF-02 | AI Engineer | 3 h |
| AF-03 | Local LLM Specialist | 2 h |
| AF-04 | File Handler | 2 h |
| AF-05 | Strategic Planning | 5 h |
| AF-06 | Dashboard Engineer | 3 h |
| AF-07 | Observability | 2 h |
| AF-08 | Data Integrity | 1.5 h |
| PA-03 | Pipeline Architect | 2 h |
| PA-04 | API Integration | 1.5 h |
| PA-05 | Codex Integration | 4 h |
| PA-06 | Pipeline Instrumentation | 2.5 h |
| UI-02 | Frontend Designer | 1.5 h |
| UI-03 | File Upload UI | 1.5 h |
| UI-04 | Diff Viewer | 2 h |
| UI-05 | Settings Specialist | 2 h |

---

## Starting Now: Dispatch Task 0 (Blocker)

Ready to begin. Task 0 (Settings Route Integration) assigned to AF-01.
