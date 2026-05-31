# V2 MASTER PLAN — AI Operating System: Production Evolution

> Status: Active. Phases execute sequentially. Each phase has a clear Definition of Done before the next begins.
> Branch: `wavefield-routing` → merge to `main` after Phase 2.

---

## What Phase 1 Delivered (Done ✓)

| Item | Status |
|------|--------|
| Fish Speech S2 TTS integration | ✓ |
| Research v2 routes (discover/execute) | ✓ |
| Knowledge store schema migration | ✓ |
| Brain/graph snapshot-first pattern | ✓ |
| SecurityPanel URL param deep-link | ✓ |
| Full system audit (AUDIT.md, MODULE_MAP.md) | ✓ |
| Neural OS research doc | ✓ |
| Target architecture doc | ✓ |
| Electron vs Tauri decision (stay Electron) | ✓ |
| P0 fix: `/api/workspace/upload` auth | ✓ |
| P0 fix: DiffPolicy content injection scanner | ✓ |
| Route auth coverage: 57% → 86% (58 routes) | ✓ |

---

## Phase 2 — Complete Unfinished Work

**Goal:** Everything that exists works correctly. No stubs. No fake data. No silent failures.

### 2A — Fix Remaining Security Gaps

| Task | File | Detail |
|------|------|--------|
| Protect remaining 14% unauth routes | `backend/server.js` | Audit which of the 28 remaining should be public vs auth-required |
| Internal routes lockdown | `backend/server.js` | `/internal/*` should only accept localhost or internal service token |
| SAM middleware NotImplementedError | `runtime/core/` | Find SAM class, implement or stub-with-error properly |

### 2B — ChromaDB: Populate with Real Embeddings

Current state: Chroma collections exist but are empty. RAG runs on TF-IDF fallback.

| Task | File |
|------|------|
| Embed all 10 knowledge store entries at startup | `runtime/core/knowledge_store.py` |
| Embed conversation history on write | `runtime/memory/memory_router.py` |
| Add embedding health check to `/health/full` | `runtime/agents/problem-solver-ui/server.py` |
| Expose Chroma collection counts in `/api/memory/stats` | `backend/server.js` (new endpoint) |

### 2C — Money Mode: Real Pipelines

Current state: `money_mode.py` returns `len(source_string) * 4` as "scraped records."

| Pipeline | File | Real implementation |
|----------|------|---------------------|
| `content_publish_track` | `runtime/core/money_mode.py` | LLM generates content → saves to `state/content/` → tracks word count + platform |
| `data_scrape_filter_store` | `runtime/core/money_mode.py` | URL fetch → extract text → deduplicate → store to knowledge base |
| `outreach_response_conversion` | `runtime/core/money_mode.py` | Template fill → HITL approval gate → log as "pending send" (no real email without approval) |

### 2D — Phase 4G Observability Endpoints

Add these endpoints to `backend/server.js`, all returning real data:

| Endpoint | Source | Data |
|----------|--------|------|
| `GET /api/memory/stats` | memory router + vector store | Count per memory type, Chroma collection sizes, last write timestamps |
| `GET /api/agents/active` | `getAgents()` | Agents currently in `running`/`busy` state with current task |
| `GET /api/execution/queue` | `_forgeQueue` + Python task queue | Pending/running tasks with risk level and status |
| `GET /api/models/routing` | `~/.ai-employee/model-routing.json` | Current routing rules per task type |
| `GET /api/rag/sources` | Chroma + knowledge store | Indexed document list with embedding counts |

### 2E — Unified Memory Manager

Create `runtime/memory/memory_manager.py` as the single entry point for all 14 memory types:

```python
class MemoryManager:
    def store(self, content, memory_type, metadata={}) -> str   # returns memory_id
    def retrieve(self, query, memory_type=None, top_k=10) -> list
    def stats(self) -> dict  # counts per type, total, vector counts
    def delete(self, memory_id) -> bool
    def clear_type(self, memory_type) -> int  # returns deleted count
```

All agents and the orchestrator call `MemoryManager`, never individual stores directly.

**Definition of Done:**
- All 5 observability endpoints return real data
- Chroma has > 0 entries after startup
- Money mode pipelines produce real artifacts (files/logs), not arithmetic
- MemoryManager routes all 14 types through one interface
- SAM middleware raises a clear "not implemented" 501 rather than crashing

---

## Phase 3 — Enterprise Architecture Refactor

**Goal:** Clean service boundaries. No business logic in route handlers. No direct cross-layer calls.

### 3A — Service Layer Pattern

Extract all business logic from `server.js` route handlers into service modules:

```
backend/
  services/
    brain_service.js     # brain.status(), brain.insights() etc.
    memory_service.js    # memory read/write/search
    agent_service.js     # agent lifecycle, status, grading
    forge_service.js     # forge queue, snapshots, risk scoring
    audit_service.js     # audit log read/write, stats
    economy_service.js   # ledger, costs, wallet, pipelines
```

Route handlers become thin: validate input → call service → return result.

### 3B — Python Service Contracts

Define typed request/response contracts for all Python→Node and Node→Python calls:

```
runtime/core/contracts/
  brain.py        # BrainStatusResponse, BrainLearnRequest
  memory.py       # MemoryStoreRequest, MemoryRetrieveResponse
  research.py     # DiscoverSourcesRequest, ExecuteResearchResponse
  task.py         # TaskGraphNode, TaskResult (already exists, extend)
```

### 3C — WebSocket Event Standardization

All WS events follow: `{ event: string, payload: object, ts: ISO8601, source: 'node'|'python' }`

Add event schema validation at the broadcaster level.

**Definition of Done:**
- `server.js` route handlers average < 10 lines each (no embedded business logic)
- All Python↔Node contracts are typed dataclasses
- WS events all carry `ts` and `source`
- Zero circular requires between service modules

---

## Phase 4 — AI System Optimization

**Goal:** Smarter reasoning, better context handling, faster retrieval.

### 4A — Context Sufficiency Evaluator Improvement

Current: simple keyword count. Target: LLM-based confidence scoring with fallback to heuristics.

File: `runtime/core/context_evaluator.py`

- Add confidence score (0.0–1.0) instead of binary pass/fail
- Cache evaluation result for 60s on identical queries
- Log sufficiency scores to `state/context_scores.jsonl` for analysis

### 4B — RAG Pipeline: Real Hybrid Search

Current: TF-IDF only (Chroma empty). Target: BM25 + vector + cross-encoder rerank.

Files: `runtime/core/auto_research_agent.py`, `runtime/memory/vector_store.py`

| Step | Implementation |
|------|----------------|
| BM25 index | Build on startup from knowledge store; update on write |
| Vector search | Chroma `query()` with `n_results=20` |
| Fusion scoring | RRF (Reciprocal Rank Fusion) across both result sets |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local, lazy-loaded) |
| Compression | Remove duplicate chunks by cosine similarity > 0.92 |

### 4C — LLM Router Config Hot-Reload

Current: `llm_router.py` reads config once at startup.

Target: Watch `~/.ai-employee/model-routing.json` for changes (inotify / polling), reload without restart.

Add `GET /api/models/reload` (requireAuth) to force reload.

### 4D — Orchestrator Reasoning Quality

Add to `runtime/core/orchestrator.py`:
- **Chain-of-thought trace**: log reasoning steps to `state/reasoning_traces.jsonl`
- **Confidence scoring**: each LLM response gets a 0–1 confidence score based on source quality + context sufficiency
- **Self-check step**: for tasks with confidence < 0.7, run a verification pass before returning

**Definition of Done:**
- Chroma has real embeddings; hybrid search returns relevant results
- LLM routing reloads within 5s of config file change
- Reasoning traces visible in `state/reasoning_traces.jsonl`
- Context evaluator returns confidence scores

---

## Phase 5 — UI/UX Evolution

**Goal:** Every dashboard panel shows live, real data. Zero fake/hardcoded values.

### 5A — Live Dashboard Wiring

| Panel | Current state | Target |
|-------|--------------|--------|
| Brain Status | `brain.status()` (Node-only) | Merges Node + Python `/api/brain/status` with 5s polling |
| Memory Stats | Missing endpoint | `/api/memory/stats` → live counts per type |
| Agent Activity | `runtimeState.agents` | Real `running`/`busy` filter from `getAgents()` |
| Execution Queue | `_forgeQueue` in-memory | Combined forge + Python task queue |
| RAG Sources | Missing endpoint | `/api/rag/sources` → Chroma collection listing |
| Model Routing | Missing endpoint | `/api/models/routing` → live routing config |

### 5B — Real-Time Graph Updates

Current: NeuralNetworkPage polls `/api/brain/graph` every 10s.

Target:
- Push updates via WS event `brain:graph_update` when graph changes
- Frontend subscribes and merges delta updates (not full reload)
- Graph shows `source` badge: `live` / `snapshot` / `offline`

### 5C — Research Page: Live Execution Progress

`ResearchPage.jsx` already has 3-panel layout. Wire:
- Progress updates via WS `task:research_progress` events
- Source trust scores shown per URL
- Final summary auto-added to knowledge store with "add to knowledge" button

### 5D — Knowledge Page: Semantic Search Mode

Toggle between keyword search (current) and vector search (`GET /api/knowledge/search/semantic`).
Show `X-Search-Mode` header as a badge on results.

**Definition of Done:**
- All 6 dashboard panels show live data (no hardcoded values)
- Neural graph updates via WS push (not only poll)
- Research page shows live progress per source fetched
- Knowledge page semantic search works

---

## Phase 6 — Security Hardening

**Goal:** Production-ready security posture.

### 6A — Route Coverage: 86% → 100%

Audit remaining 28 unprotected routes. For each:
- Public by design? → Document it explicitly with a comment
- Internal only? → Add localhost-only middleware
- Needs auth? → Add `requireAuth`

### 6B — Input Validation on All Routes

Every route that accepts a request body must validate it against a JSON schema (using the existing `validate()` + `SCHEMAS` pattern already in `server.js`).

Add schemas for: all `/api/neural-brain/*` POST bodies, `/api/memory/*` write routes.

### 6C — Rate Limiting

Add rate limiting middleware (already using `express-rate-limit` per auth routes) to:
- All `/api/blacklight/tools/run` (5 req/min per IP)
- All `/api/forge/submit` (10 req/min per IP)
- All `/api/research/execute` (3 req/min per IP)

### 6D — Secrets: No .env Leaks

Audit all places where `process.env.*` is logged or returned in API responses. Replace with `[REDACTED]`.

Add test: `grep -r "process.env\." backend/ | grep "res.json\|console.log"` must return 0 results.

### 6E — HITL Gate Coverage

Verify all Level 2+ actions flow through `hitl_gate.py`. Add gate to:
- Money mode outreach pipeline (blocks until human approves)
- Any agent that touches `state/deals.json` (CRM writes)

**Definition of Done:**
- 100% of routes are either explicitly public or `requireAuth`
- All write routes have input validation schemas
- Rate limiting on the 3 highest-risk endpoints
- Zero `process.env` values in API responses
- HITL gate verified for outreach + CRM writes

---

## Phase 7 — Performance Optimization

**Goal:** Fast startup, low latency, minimal memory footprint.

### 7A — Startup Time

Current: server.js takes ~3–5s to load all modules at boot.

Target < 2s:
- Lazy-load heavy modules: blacklight tools, learning ladder, audit DB
- Defer Chroma connection until first query
- Add `--max-old-space-size=512` flag to Node process

### 7B — Python Backend Startup

Current: FastAPI loads all agents/models at import time.

Target: lazy-load agent modules on first use. Only pre-load the orchestrator core.

### 7C — API Response Caching

Add 30s in-memory cache for: `/api/brain/neurons`, `/api/agents/grades`, `/api/blacklight/status`.

Use `node-cache` (already likely a dependency) or a simple `Map` with TTL.

### 7D — Bundle Size

Current frontend bundle: unknown. Target < 2MB gzip.

Run `npm run build -- --report` and identify the top 3 heaviest chunks. Apply code splitting:
- Lazy-load: NeuralNetworkPage (Three.js), SecurityPanel, AscendForgePage
- Split vendor chunk: react/react-dom separate from three/framer-motion

**Definition of Done:**
- Node startup < 2s (measure with `time node backend/server.js`)
- Python startup < 5s (measure with `time uvicorn server:app`)
- Frontend bundle < 2MB gzip (measure with `build --report`)
- Cache hit rates > 80% for the 3 cached endpoints

---

## Phase 8 — Money Mode Evolution

**Goal:** Safe, audited, approval-gated pipelines that generate real artifacts.

### 8A — Content Pipeline (Real)

`content_publish_track` pipeline produces:
1. LLM generates article/post for given topic and platform
2. Saves artifact to `state/content/{ts}_{topic}.md`
3. Tracks in `state/content_log.json` with: topic, platform, word_count, status (`draft` → `queued` → `published`)
4. HITL approval required before status moves to `queued`

### 8B — Research→Scrape Pipeline (Real)

`data_scrape_filter_store` pipeline produces:
1. URL fetch via `CloakBrowser.fetch_url()`
2. Text extraction + deduplication
3. Store to knowledge base with source URL + trust score
4. Returns actual record count (not arithmetic)

### 8C — Outreach Pipeline (Safe)

`outreach_response_conversion` pipeline produces:
1. Template personalizes message (LLM)
2. Draft saved to `state/outreach/{ts}.md`
3. HITL approval gate shows draft to operator
4. On approval: status → `approved` (no actual send without explicit external integration)
5. ROI tracked: approved outreach → conversion events update `state/revenue.json`

### 8D — Money Mode Dashboard

New route `GET /api/moneymode/status` returning:
```json
{
  "active_pipelines": 3,
  "content_drafted": 12,
  "outreach_pending_approval": 3,
  "revenue_tracked_cents": 0,
  "last_pipeline_run": "2026-05-26T...",
  "next_scheduled": null
}
```

**Definition of Done:**
- Content pipeline generates real `.md` files in `state/content/`
- Scrape pipeline stores to knowledge base with real record counts
- Outreach pipeline saves drafts and requires HITL approval
- Money mode dashboard route returns live data

---

## Phase 9 — Testing & Validation

**Goal:** Comprehensive automated test coverage. No manual testing required for deployment.

### 9A — Unit Tests

| Module | Test file | Coverage target |
|--------|-----------|----------------|
| DiffPolicy (new injection scanner) | `tests/test_diff_policy.py` | 100% of new rules |
| MemoryManager | `tests/test_memory_manager.py` | All 14 types, store/retrieve/stats |
| Money mode pipelines | `tests/test_money_mode.py` | Each pipeline, happy path + HITL gate |
| Context evaluator | `tests/test_context_evaluator.py` | Score range, cache, fallback |

### 9B — Integration Tests

| Scenario | Test file |
|----------|-----------|
| Auth flow: register → login → access protected route | `tests/test_auth_integration.py` |
| Research: discover → execute → knowledge stored | `tests/test_research_integration.py` |
| Memory: store → embed → retrieve via vector search | `tests/test_memory_integration.py` |
| Forge: submit → HITL approval → deploy → smoke test | `tests/test_forge_integration.py` |

Rules: integration tests hit real services (no mocks). Use `pytest-asyncio` for async tests.

### 9C — Security Tests

```bash
# Run as part of CI
tests/security/
  test_unauth_routes.py      # Every route not in EXPLICITLY_PUBLIC returns 401 without token
  test_injection_scanner.py  # DiffPolicy blocks all 15 injection patterns
  test_hitl_gate.py          # Level 2+ actions are blocked without approval
  test_rate_limiting.py      # Rate limits trigger after threshold
```

### 9D — Smoke Test Suite

Extend `scripts/smoke.sh` to test all Phase 2–8 features automatically after deployment.

### 9E — CI Pipeline

Add `.github/workflows/ci.yml`:
```yaml
on: [push, pull_request]
jobs:
  test:
    - python -m pytest tests/ -v --tb=short
    - node -c backend/server.js
    - cd frontend && npm run build
    - bash scripts/smoke.sh
```

**Definition of Done:**
- pytest passes with > 80% coverage across new modules
- All security tests pass (0 unauth routes, injection patterns blocked)
- Smoke test covers all V2 features
- CI runs on every push

---

## Phase 10 — V3 Planning & Handoff

**Goal:** Define what comes after V2. Document everything. System is maintainable by a new developer.

### 10A — V3 Scope Definition

Based on what V2 delivered, define the next major evolution:
- Tauri v2 migration (if performance targets not met by Phase 7)
- Multi-tenant production deployment (K8s, separate DB per tenant)
- LangGraph neural brain milestones M1–M8 (if not done in Phase 7)
- Marketplace: skills/agents as installable packages
- Public API: expose orchestrator to external integrations

### 10B — Documentation

| Doc | Contents |
|-----|----------|
| `docs/API_REFERENCE.md` | All 198 routes: method, path, auth, request/response schema |
| `docs/DEVELOPER_GUIDE.md` | How to add a new agent, skill, tool, route |
| `docs/DEPLOYMENT.md` | How to run in production: env vars, ports, process supervisor |
| `docs/SECURITY_MODEL.md` | Auth flow, RBAC, HITL gate, audit log, secret handling |

### 10C — Knowledge Capture

Run a retrospective after each phase:
- What took longer than estimated and why?
- What architectural decisions proved correct?
- What should be done differently next time?

Store retrospective notes in `docs/RETROSPECTIVES/phase_N.md`.

---

## Execution Order

```
Phase 2 (Complete unfinished work)    — Start now
Phase 3 (Architecture refactor)       — After Phase 2 DoD met
Phase 4 (AI optimization)             — Parallel with Phase 3 (different modules)
Phase 5 (UI evolution)                — After Phase 4 observability endpoints
Phase 6 (Security hardening)          — Continuous, runs alongside all phases
Phase 7 (Performance)                 — After Phase 3 (needs clean service layer)
Phase 8 (Money mode)                  — After Phase 2 pipeline stubs removed
Phase 9 (Testing)                     — Starts Phase 2, grows with each phase
Phase 10 (V3 planning)                — After all phases complete
```

---

## Effort Estimates

| Phase | Estimated effort |
|-------|-----------------|
| 2 — Complete unfinished work | 8h |
| 3 — Architecture refactor | 12h |
| 4 — AI optimization | 10h |
| 5 — UI evolution | 8h |
| 6 — Security hardening | 6h |
| 7 — Performance | 4h |
| 8 — Money mode | 6h |
| 9 — Testing | 8h |
| 10 — V3 planning + docs | 4h |
| **Total** | **~66h** |

---

## Invariants (Must Never Be Violated)

1. **No fake data** — every UI element shows real data or an explicit "offline" state
2. **No silent failures** — every error is logged, surfaced, and recoverable
3. **HITL on all Level 2+ actions** — no autonomous financial/outreach execution
4. **Auth on all non-public routes** — no information leakage to unauthenticated clients
5. **Tests before deploy** — no phase ships without its Definition of Done met
6. **One thing at a time** — phases execute sequentially; no skipping DoD checks
