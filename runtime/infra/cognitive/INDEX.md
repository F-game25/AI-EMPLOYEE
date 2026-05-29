# Cognitive Infrastructure — File Index & Quick Reference

## Core Files (Start Here)

- **README.md** — Quick start guide, API overview, usage examples
- **ARCHITECTURE.md** — Complete system design, database schema, performance characteristics
- **INTEGRATION_GUIDE.md** — How to integrate into main system, code examples, troubleshooting

## Modules by Category

### Database & Configuration

| File | Lines | Purpose |
|------|-------|---------|
| `db.py` | 50 | SQLite connection factory with WAL mode |

### Coherence Engine (`coherence/`)

| File | Lines | Purpose |
|------|-------|---------|
| `schema.py` | 40 | ObjectiveNode, Contradiction, CoherenceScore dataclasses |
| `objective_hierarchy.py` | 202 | Objective tree CRUD + priority stacking |
| `contradiction_detector.py` | 210 | Conflict detection via cosine similarity |
| `loop_detector.py` | 220 | Cycle detection using DFS |
| `deduplication_engine.py` | 170 | Workflow fingerprinting with TTL |
| `coherence_scorer.py` | 150 | Composite coherence metric |
| `coherence_routes.py` | 280 | 8 FastAPI endpoints (GET/POST/PATCH) |
| `__init__.py` | 30 | Module exports |

**Key Functions:**
- `add_objective(obj)` — Create objective
- `ingest_result(agent_id, tenant_id, result)` — Check contradictions
- `check_or_register(wf_type, inputs, wf_id, tenant)` — Check dedup
- `add_trigger(source, target, tenant)` — Check loops
- `compute(tenant_id)` — Get coherence score

### Executive Function (`executive/`)

| File | Lines | Purpose |
|------|-------|---------|
| `schema.py` | 35 | Initiative, WorkloadState, ExecutiveDecision dataclasses |
| `initiative_manager.py` | 235 | FIFO queue with lifecycle state machine |
| `workload_balancer.py` | 170 | Per-agent health polling |
| `budget_tracker.py` | 190 | Daily rolling token window |
| `strategic_planner.py` | 225 | LLM-guided initiative ranking |
| `executive_routes.py` | 300 | 8 FastAPI endpoints |
| `__init__.py` | 40 | Module exports |

**Key Functions:**
- `create(initiative)` — Add initiative to queue
- `update(init_id, **kwargs)` — Update status, deadline, cost
- `list_initiatives(tenant_id, status)` — Query initiatives
- `record_usage(tenant_id, tokens)` — Track token usage
- `plan_next(tenant_id)` — Run strategic planning

### Autonomy Guardrails (`guardrails/`)

| File | Lines | Purpose |
|------|-------|---------|
| `schema.py` | 35 | TrustTier, GuardrailViolation, ThrottleState enums/dataclasses |
| `spawn_limiter.py` | 145 | Async token bucket (tenant + agent limits) |
| `trust_tier_policy.py` | 165 | Agent autonomy tier management |
| `rate_governor.py` | 155 | Cognitive decision rate limiting |
| `event_storm_detector.py` | 150 | Event flood detection + suppression |
| `budget_enforcer.py` | 110 | Token budget gate enforcement |
| `escalation_gate.py` | 205 | HITL routing for risky actions |
| `guardrail_routes.py` | 340 | 10 FastAPI endpoints |
| `__init__.py` | 50 | Module exports |

**Key Functions:**
- `acquire(tenant_id, agent_id)` — Acquire spawn quota (async)
- `release(tenant_id, agent_id)` — Release spawn quota (async)
- `get_tier(agent_id, tenant_id)` — Get trust tier
- `set_tier(agent_id, tier, tenant_id)` — Set trust tier
- `should_escalate(agent_id, action_type, tenant_id)` — Check HITL routing
- `check(channel, tenant_id)` — Check event storm (returns bool)
- `enforce(tenant_id)` — Check token budget (returns bool)

### Integration Layer

| File | Lines | Purpose |
|------|-------|---------|
| `integration.py` | 400 | Unified interface + 11 convenience functions |
| `__init__.py` | 5 | Module exports |

**Key Functions:**
- `record_cognitive_event(event_type, tenant_id, metadata)`
- `check_workflow_duplicate(wf_type, inputs, wf_id, tenant)` → dict
- `ingest_agent_result(agent_id, tenant_id, result)`
- `detect_trigger_loop(source, target, tenant)` → bool
- `acquire_spawn_quota(tenant, agent)` → dict (async)
- `release_spawn_quota(tenant, agent)` (async)
- `check_action_escalation(agent, action, tenant)` → bool
- `record_token_usage(tenant, tokens)`
- `check_token_budget(tenant)` → bool
- `get_coherence_score(tenant)` → dict
- `trigger_strategic_planning(tenant)` → dict or None (async)

## HTTP Routes (26 Total)

### Coherence Routes (10 endpoints)

```
GET    /cognitive/coherence/status
GET    /cognitive/coherence/objectives
GET    /cognitive/coherence/objectives/priority-stack
POST   /cognitive/coherence/objectives
PATCH  /cognitive/coherence/objectives/{id}
GET    /cognitive/coherence/contradictions
POST   /cognitive/coherence/contradictions/{id}/resolve
GET    /cognitive/coherence/loops
GET    /cognitive/coherence/duplicates
POST   /cognitive/coherence/cleanup
```

### Executive Routes (8 endpoints)

```
GET    /cognitive/executive/status
GET    /cognitive/executive/initiatives
POST   /cognitive/executive/initiatives
PATCH  /cognitive/executive/initiatives/{id}
GET    /cognitive/executive/workload
GET    /cognitive/executive/decisions
POST   /cognitive/executive/plan
GET    /cognitive/executive/budget
```

### Guardrails Routes (10 endpoints)

```
GET    /cognitive/guardrails/status
GET    /cognitive/guardrails/violations
GET    /cognitive/guardrails/trust-tiers
POST   /cognitive/guardrails/trust-tiers/{id}
GET    /cognitive/guardrails/spawn-state
POST   /cognitive/guardrails/reset/{id}
GET    /cognitive/guardrails/budget
POST   /cognitive/guardrails/check-escalation/{id}
GET    /cognitive/guardrails/suppressions
```

## Database Schema (8 Tables)

```
objectives (id, tenant_id, title, priority, parent_id, status, created_at, updated_at)
contradictions (id, tenant_id, agent_a, agent_b, claim_a, claim_b, detected_at, resolved)
wf_fingerprints (hash, workflow_id, tenant_id, started_at, expires_at)
initiatives (id, tenant_id, title, status, priority, deadline, dependencies[], assigned_agents[])
executive_decisions (id, tenant_id, decision_type, rationale, confidence, decided_at)
budget_usage (tenant_id, day, tokens_used)
trust_tiers (tenant_id, agent_id, tier)
guardrail_violations (id, tenant_id, agent_id, violation_type, detail, occurred_at)
```

## Testing

**Test File:** `tests/test_cognitive_infrastructure.py` (600+ lines, 40+ tests)

**Run tests:**
```bash
pytest tests/test_cognitive_infrastructure.py -v
pytest tests/test_cognitive_infrastructure.py::TestCoherence -v
pytest tests/test_cognitive_infrastructure.py::TestExecutive -v
pytest tests/test_cognitive_infrastructure.py::TestGuardrails -v
```

## Verification & Deployment

**Verify:** `scripts/verify_phase4.py`
- Checks: Files, Database, Imports, Routes, Integration
- Run: `python3 scripts/verify_phase4.py`

**Deployment:** `DEPLOYMENT.md`
- Step-by-step integration guide
- Testing procedures
- Rollback plan
- Post-deployment checklist

## Quick Start Examples

### Check Duplicate Workflow
```python
from infra.cognitive.integration import check_workflow_duplicate

result = check_workflow_duplicate("content-gen", ["prompt"], "wf-1", tenant)
if result["duplicate"]:
    reuse(result["existing_workflow_id"])
```

### Detect Loop
```python
from infra.cognitive.integration import detect_trigger_loop

if detect_trigger_loop("agent-a", "agent-b", tenant):
    logger.error("Loop prevented!")
```

### Enforce Budget
```python
from infra.cognitive.integration import record_token_usage, check_token_budget

if not check_token_budget(tenant):
    raise BudgetExhausted()
record_token_usage(tenant, tokens)
```

### Check Escalation
```python
from infra.cognitive.integration import check_action_escalation

if check_action_escalation("hr-manager", "fire", tenant):
    await escalate_to_human(action, agent, tenant)
```

## Configuration (Env Vars)

```bash
COGNITIVE_DAILY_BUDGET_TOKENS=1000000         # Default budget per tenant
COGNITIVE_SPAWN_MAX_TENANT=50                 # Max concurrent per tenant
COGNITIVE_SPAWN_MAX_AGENT=10                  # Max concurrent per agent
COGNITIVE_DECISION_RATE_PER_MIN=60            # Decisions/min per agent
COGNITIVE_EVENT_STORM_THRESHOLD=100           # Events/sec threshold
```

## Monitoring

**Health Score (0-100):**
- 100-80: Excellent (few conflicts, dedup working, no loops)
- 79-50: Good (some conflicts, system stable)
- 49-30: Warning (high contradiction rate, check agent consistency)
- <30: Critical (system incoherent, immediate investigation needed)

**Key Metrics to Monitor:**
- Coherence score < 50 → Alert
- Budget usage > 80% → Warn
- Budget usage > 100% → Critical (execution blocked)
- Contradictions > 10/min → Alert
- Loops detected > 5/min → Critical
- Violations > 0 → Track escalations

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Database locked | Check: `fuser ~/.ai-employee/cognitive.db` |
| No contradictions detected | Verify `ingest_agent_result()` called |
| Loops not detected | Note: 60s window resets; short cycles may miss |
| Budget not enforced | Verify `record_token_usage()` called in LLM layer |
| High memory | Run: `POST /cognitive/coherence/cleanup` |
| Routes not found | Verify routers mounted in `server.py` |

## Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| README.md | Quick start, API reference | All developers |
| ARCHITECTURE.md | System design, data flow | Architects, integrators |
| INTEGRATION_GUIDE.md | How to integrate, code examples | Developers |
| DEPLOYMENT.md | Deployment procedures, checklist | Ops, deployment engineers |
| PHASE4_STATUS.md | Implementation status, metrics | Project managers, architects |
| This file | Quick reference, file index | All |

## File Locations

```
/home/lf/AI-EMPLOYEE/
├── runtime/infra/cognitive/
│   ├── db.py
│   ├── integration.py
│   ├── README.md                    ← Start here
│   ├── ARCHITECTURE.md
│   ├── INTEGRATION_GUIDE.md
│   ├── INDEX.md                     ← This file
│   ├── coherence/
│   │   ├── __init__.py
│   │   ├── schema.py
│   │   ├── *.py                     (6 modules)
│   │   └── coherence_routes.py
│   ├── executive/
│   │   ├── __init__.py
│   │   ├── schema.py
│   │   ├── *.py                     (4 modules)
│   │   └── executive_routes.py
│   └── guardrails/
│       ├── __init__.py
│       ├── schema.py
│       ├── *.py                     (6 modules)
│       └── guardrail_routes.py
├── tests/
│   └── test_cognitive_infrastructure.py
├── scripts/
│   └── verify_phase4.py
├── DEPLOYMENT.md
├── PHASE4_STATUS.md
└── PHASE4_COMPLETE.txt
```

---

**Quick Navigation:**
- Want to understand the system? → Read **ARCHITECTURE.md**
- Want to integrate? → Read **INTEGRATION_GUIDE.md** + **DEPLOYMENT.md**
- Want to use the API? → Read **README.md**
- Want to verify? → Run `python3 scripts/verify_phase4.py`
- Want to test? → Run `pytest tests/test_cognitive_infrastructure.py -v`
