# Cognitive Infrastructure Architecture

Phase 4 cognitive layer for AI-EMPLOYEE: coherence, executive function, and autonomy guardrails.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 COGNITIVE INFRASTRUCTURE                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │  COHERENCE      │  │   EXECUTIVE      │  │ GUARDRAILS │  │
│  │  (Logic)        │  │   (Strategy)     │  │ (Safety)   │  │
│  ├─────────────────┤  ├──────────────────┤  ├────────────┤  │
│  │ • Consistency   │  │ • Initiatives    │  │ • Spawn    │  │
│  │ • Dedup         │  │ • Workload       │  │   Limits   │  │
│  │ • Loop-free     │  │ • Budget         │  │ • Trust    │  │
│  │                 │  │ • Planning       │  │   Tiers    │  │
│  │ [SQLite]        │  │ [SQLite]         │  │ • Events   │  │
│  └─────────────────┘  └──────────────────┘  └────────────┘  │
│         ▲                    ▲                    ▲           │
│         │ metrics            │ planning           │ gates     │
│         └────────────────────┼────────────────────┘           │
│                              │                                │
│                    [Message Bus: bus.jsonl]                  │
│                    [Unified DB: cognitive.db]                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Architecture Components

### 1. Coherence Engine (`coherence/`)

Ensures logical consistency across distributed agent decisions.

**Modules:**
- `objective_hierarchy.py` — SQLite-backed objective tree (parent-child relationships, priorities)
- `contradiction_detector.py` — Detects conflicting agent claims using cosine similarity (< 0.3 = contradiction)
- `loop_detector.py` — DFS-based cycle detection in agent trigger chains; auto-resets every 60s
- `deduplication_engine.py` — Workflow fingerprinting (sha256: workflow_type+input_keys+tenant_id); 5min TTL
- `coherence_scorer.py` — Composite score: 40% consistency + 30% dedup + 30% loop-free

**Data:**
```sqlite
objectives: {id, tenant_id, title, priority, parent_id, status, created_at}
contradictions: {id, tenant_id, agent_a, agent_b, claim_a, claim_b, resolved, resolution}
wf_fingerprints: {hash, workflow_id, tenant_id, started_at, expires_at}
```

**Public API:**
```python
from infra.cognitive.coherence import (
    add_objective, list_objectives, update_status, get_priority_stack,
    ingest_result,  # for contradiction detection
    resolve_contradiction,
    check_or_register,  # workflow dedup
    expire_old,
    get_loop_detector,  # .add_trigger(source, target, tenant)
    record_event,  # for scoring
)
```

**HTTP Routes:**
```
GET /cognitive/coherence/status              # composite score
GET /cognitive/coherence/objectives          # list all
POST /cognitive/coherence/objectives         # create
PATCH /cognitive/coherence/objectives/{id}   # update status
GET /cognitive/coherence/contradictions      # list unresolved
POST /cognitive/coherence/contradictions/{id}/resolve
GET /cognitive/coherence/loops               # detected cycles
GET /cognitive/coherence/duplicates          # active fingerprints
POST /cognitive/coherence/cleanup            # expire old fingerprints
```

### 2. Executive Layer (`executive/`)

Strategic planning and workload management for autonomous execution.

**Modules:**
- `initiative_manager.py` — FIFO queue: pending → active → completed/blocked; dependency tracking
- `workload_balancer.py` — Polls per-agent health scores; emits rebalance signals when utilization > 85%
- `budget_tracker.py` — Daily token budget (default 1M/day per tenant); rolling window tracking
- `strategic_planner.py` — LLM-guided ranking of top 3 pending initiatives; stores decisions

**Data:**
```sqlite
initiatives: {id, tenant_id, title, status, priority, estimated_cost, actual_cost, deadline, dependencies[], assigned_agents[]}
executive_decisions: {id, tenant_id, decision_type, rationale, affected_initiatives[], affected_agents[], confidence}
budget_usage: {tenant_id, day, tokens_used}
```

**Lifecycle:**
1. Initiative created in `pending` status
2. Dependencies resolved → auto-promoted to `active`
3. Deadline exceeded → marked `blocked`
4. Completion → `completed` (lifecycle manager handles)

**Public API:**
```python
from infra.cognitive.executive import (
    create, update, list_initiatives,
    record_usage, get_status, get_used_today,
    plan_next,  # async: LLM-guided planning
    list_decisions,
    get_initiative_manager,
    get_workload_balancer,
    get_budget_tracker,
)
```

**HTTP Routes:**
```
GET /cognitive/executive/status               # active/pending/blocked counts
GET /cognitive/executive/initiatives          # list all
POST /cognitive/executive/initiatives         # create
PATCH /cognitive/executive/initiatives/{id}   # update
GET /cognitive/executive/workload             # per-agent queue depth
GET /cognitive/executive/decisions            # past strategic decisions
POST /cognitive/executive/plan                # trigger planning
GET /cognitive/executive/budget               # token budget used/limit
```

### 3. Guardrails (`guardrails/`)

Safety mechanisms for autonomous agent execution.

**Modules:**
- `spawn_limiter.py` — Async token bucket per tenant (max 50) and per agent (max 10)
- `trust_tier_policy.py` — Per-agent autonomy levels (supervised/assisted/autonomous/trusted)
- `rate_governor.py` — Token bucket for cognitive decisions (60/min per agent)
- `event_storm_detector.py` — Detects + suppresses event flood (>100/s per channel)
- `budget_enforcer.py` — Blocks execution when daily token budget exhausted
- `escalation_gate.py` — Routes risky actions (hire, fire, financial) to HITL based on trust tier

**Data:**
```sqlite
trust_tiers: {tenant_id, agent_id, tier}
guardrail_violations: {id, tenant_id, agent_id, violation_type, detail, occurred_at}
```

**Trust Tiers:**
- `supervised` — ALL actions require HITL approval
- `assisted` — Risky actions (hire, fire, send_offer, financial_transfer, delete_data, publish_external) require escalation
- `autonomous` — Default; no escalation
- `trusted` — Fully autonomous (reserved for proven agents)

**Public API:**
```python
from infra.cognitive.guardrails import (
    # Spawn limits (async)
    acquire, release, reset_agent,
    # Trust tiers
    get_tier, set_tier, list_tiers,
    # Rate limiting
    acquire_decision,
    # Escalation
    should_escalate, list_violations,
    # Events
    check_event_storm, get_suppressions,
    # Budget
    check_budget, enforce,
)
```

**HTTP Routes:**
```
GET /cognitive/guardrails/status              # spawn/suppressions/rate state
GET /cognitive/guardrails/violations          # escalation history
GET /cognitive/guardrails/trust-tiers         # agent trust assignments
POST /cognitive/guardrails/trust-tiers/{agent_id}  # set tier
GET /cognitive/guardrails/spawn-state         # current counts
POST /cognitive/guardrails/reset/{agent_id}   # clear deadlock
GET /cognitive/guardrails/budget              # budget used/limit
POST /cognitive/guardrails/check-escalation/{agent_id}  # test escalation
GET /cognitive/guardrails/suppressions        # event storm status
```

## Database Schema

**Central database:** `~/.ai-employee/cognitive.db` (SQLite WAL mode)

All tables tenant-scoped. Indexes on {tenant_id, status}, {tenant_id, time} for efficient queries.

```sql
CREATE TABLE objectives (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority INTEGER DEFAULT 5,
    parent_id TEXT,
    status TEXT DEFAULT 'active',  -- active, completed, archived
    source_agent TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE contradictions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    detected_at REAL NOT NULL,
    resolved INTEGER DEFAULT 0,
    resolution TEXT
);

CREATE TABLE wf_fingerprints (
    hash TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    expires_at REAL NOT NULL  -- TTL: 5 minutes
);

CREATE TABLE initiatives (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',  -- pending, active, blocked, completed
    priority INTEGER DEFAULT 5,
    estimated_cost_tokens INTEGER DEFAULT 0,
    actual_cost_tokens INTEGER DEFAULT 0,
    deadline REAL,
    dependencies TEXT DEFAULT '[]',  -- JSON array of initiative IDs
    assigned_agents TEXT DEFAULT '[]',  -- JSON array of agent IDs
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE executive_decisions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,  -- schedule, rebalance, escalate, etc.
    rationale TEXT NOT NULL,
    affected_initiatives TEXT DEFAULT '[]',
    affected_agents TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.8,
    decided_at REAL NOT NULL
);

CREATE TABLE budget_usage (
    tenant_id TEXT NOT NULL,
    day TEXT NOT NULL,  -- ISO date YYYY-MM-DD
    tokens_used INTEGER DEFAULT 0,
    PRIMARY KEY (tenant_id, day)
);

CREATE TABLE trust_tiers (
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tier TEXT NOT NULL,  -- supervised, assisted, autonomous, trusted
    PRIMARY KEY (tenant_id, agent_id)
);

CREATE TABLE guardrail_violations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    violation_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    occurred_at REAL NOT NULL
);
```

## Integration Points

### With Unified Pipeline

Cognitive checks happen at key pipeline stages:

```python
# runtime/core/unified_pipeline.py

# Stage: build_context
from infra.cognitive.coherence import ingest_result
ingest_result(agent_id, tenant_id, agent_output)  # check for contradictions

# Stage: execute_tasks
from infra.cognitive.integration import (
    detect_trigger_loop,
    acquire_spawn_quota,
    check_action_escalation,
)

loop_detected = detect_trigger_loop(source, triggered, tenant)
spawn_allowed = await acquire_spawn_quota(tenant, agent_id)
requires_escalation = check_action_escalation(agent, action, tenant)

# Stage: update_graph
from infra.cognitive.integration import record_token_usage
record_token_usage(tenant, token_count)

# Stage: validate_pipeline_integrity
from infra.cognitive.coherence import check_or_register
dup_check = check_or_register(workflow_type, input_keys, workflow_id, tenant)
```

### With Message Bus

Cognitive events published to `bus.jsonl` channels:

```python
# Coherence events
{"event": "cognitive:contradiction", "tenant_id": "...", "agents": [...], "id": "..."}
{"event": "cognitive:loop_detected", "tenant_id": "...", "agents": [...]}
{"event": "cognitive:duplicate_blocked", "tenant_id": "...", "workflow_id": "..."}

# Executive events
{"event": "executive:rebalance", "agent_id": "...", "utilization": 0.87}
{"event": "executive:budget_warning", "tenant_id": "...", "used": 800000, "limit": 1000000}
{"event": "executive:budget_exhausted", "tenant_id": "...", "used": 1000000, "limit": 1000000}
{"event": "executive:plan_updated", "tenant_id": "...", "decision": {...}}

# Guardrail events
{"event": "guardrail:event_storm", "channel": "...", "tenant_id": "...", "rate": 150}
```

### With HITL (Human-in-the-Loop)

When escalation gates trigger:

```python
from infra.cognitive.guardrails import should_escalate

if should_escalate(agent_id, "fire", tenant):
    # Route to HITL queue
    from core.hitl_gate import hitl_gate
    result = await hitl_gate.queue_approval(
        action_type="fire",
        agent_id=agent_id,
        context={...}
    )
```

## Initialization and Lifecycle

```python
# In FastAPI app startup
from infra.cognitive.integration import get_cognitive_infrastructure

async def startup():
    cognitive = get_cognitive_infrastructure()
    await cognitive.initialize()  # starts background tasks
    # - loop detector (60s cycle detection)
    # - initiative lifecycle manager (60s lifecycle advancement)
    # - workload balancer (30s health polling)

async def shutdown():
    cognitive.shutdown()  # stops all background tasks
```

## Monitoring and Observability

**Coherence Health:**
```python
from infra.cognitive.integration import get_coherence_score
score = get_coherence_score(tenant_id)
# {
#   "tenant_id": "...",
#   "overall": 97.5,           # 0-100, good if >80
#   "consistency_score": 100.0, # 0-100, no contradictions
#   "dedup_score": 95.0,        # 0-100, few duplicates
#   "loop_free_score": 100.0    # 0-100, no detected loops
# }
```

**Executive Status:**
```python
from infra.cognitive.executive import list_initiatives, get_status as budget_status
initiatives = list_initiatives(tenant_id, "active")  # active count
budget = budget_status(tenant_id)
# {"tenant_id": "...", "used": 500000, "limit": 1000000, "pct": 50.0}
```

**Guardrail Violations:**
```python
from infra.cognitive.guardrails import list_violations
violations = list_violations(tenant_id)  # escalation history
```

## Performance Characteristics

- **Coherence scoring:** O(events_in_window) = O(1000) @ 5min window
- **Loop detection:** O(vertices + edges) DFS = O(max_edges) = O(500)
- **Dedup check:** O(1) hash lookup + SQLite index seek
- **Spawn limits:** O(1) async token bucket
- **Budget tracking:** O(1) daily aggregate + SQLite index

**Storage:**
- Cognitive database typical size: 10-50MB (months of data, auto-compacting)
- Event fingerprints: 5-minute TTL, ~100-1000 active per tenant
- Contradictions: ~50 retained per tenant (recent unresolved)

## Failure Handling

All modules designed for graceful degradation:

1. **DB failures** → in-memory fallback (memory bounded)
2. **Bus failures** → log warnings, continue (lose telemetry only)
3. **LLM failures in strategic planner** → fallback to priority ordering
4. **Background task failures** → logged, continue (don't break request path)

No single cognitive module failure blocks main pipeline.

## Testing

```bash
# Run cognitive infrastructure tests
pytest tests/test_cognitive/ -v

# Specific test files
pytest tests/test_coherence.py          # objective hierarchy, dedup, contradictions
pytest tests/test_executive.py          # initiatives, budget, planning
pytest tests/test_guardrails.py         # spawn limits, trust tiers, escalation
pytest tests/test_cognitive_integration.py  # end-to-end integration
```

## Configuration

Environment variables (optional):

```bash
# Budget limits
COGNITIVE_DAILY_BUDGET_TOKENS=1000000     # default
COGNITIVE_SPAWN_MAX_TENANT=50              # per-tenant concurrency
COGNITIVE_SPAWN_MAX_AGENT=10               # per-agent concurrency
COGNITIVE_DECISION_RATE_PER_MIN=60         # cognitive decisions/min per agent
```

## Future Enhancements

1. **Distributed coherence** — Replicate cognitive.db across regions for HA
2. **ML-based contradiction detection** — Replace cosine sim with embeddings
3. **Predictive planning** — Forecast initiative completion using historical data
4. **Dynamic trust tier adjustment** — Promote agents based on success history
5. **Cost optimization** — Recommend cheaper LLM models based on task complexity
6. **Adaptive rate limits** — Adjust spawn/decision limits based on system load
