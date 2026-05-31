# Cognitive Infrastructure — Phase 4 Complete

Production-ready cognitive layer providing coherence, executive function, and autonomy guardrails for AI-EMPLOYEE.

## Quick Start

```python
# Initialize in FastAPI startup
from infra.cognitive.integration import get_cognitive_infrastructure

@app.on_event("startup")
async def startup():
    cognitive = get_cognitive_infrastructure()
    await cognitive.initialize()

# Use convenience functions throughout codebase
from infra.cognitive.integration import (
    check_workflow_duplicate,       # check dedup
    detect_trigger_loop,             # detect cycles
    acquire_spawn_quota,             # async quota
    check_action_escalation,         # HITL routing
    record_token_usage,              # track budget
    get_coherence_score,             # health check
)
```

## Architecture

Three-layer cognitive system:

```
┌──────────────────────────────────────────────────┐
│         COGNITIVE INFRASTRUCTURE                  │
├──────────────────────────────────────────────────┤
│ COHERENCE         EXECUTIVE        GUARDRAILS    │
│ • Consistency    • Initiatives     • Spawn       │
│ • Dedup          • Workload        • Trust       │
│ • Loop-free      • Budget          • Events      │
│                  • Planning        • Escalation  │
├──────────────────────────────────────────────────┤
│        SQLite (coherence.db) + Message Bus       │
└──────────────────────────────────────────────────┘
```

## Modules

### Coherence (`coherence/`)

**Ensures logical consistency across distributed decisions.**

| Module | Purpose | Key Functions |
|--------|---------|----------------|
| `objective_hierarchy.py` | Objective tree management | `add_objective()`, `list_objectives()`, `update_status()` |
| `contradiction_detector.py` | Detects conflicting claims | `ingest_result()`, `resolve_contradiction()` |
| `loop_detector.py` | Detects autonomy cycles | `add_trigger()`, cycle detection via DFS |
| `deduplication_engine.py` | Workflow fingerprinting | `check_or_register()`, `expire_old()` |
| `coherence_scorer.py` | Composite metric | `compute()`, 40% consistency + 30% dedup + 30% loop-free |

**Endpoints:**
- `GET /cognitive/coherence/status` → coherence score
- `GET /cognitive/coherence/objectives` → list objectives
- `POST /cognitive/coherence/objectives` → create
- `GET /cognitive/coherence/contradictions` → conflicts
- `GET /cognitive/coherence/loops` → cycles
- `GET /cognitive/coherence/duplicates` → active fingerprints

### Executive (`executive/`)

**Strategic planning and workload management.**

| Module | Purpose | Key Functions |
|--------|---------|----------------|
| `initiative_manager.py` | FIFO queue | `create()`, `update()`, `list_initiatives()` |
| `workload_balancer.py` | Per-agent monitoring | queue depth, health polling, rebalance signals |
| `budget_tracker.py` | Token budget | `record_usage()`, `get_status()`, daily rolling window |
| `strategic_planner.py` | LLM planning | `plan_next()`, rank top initiatives, decision audit |

**Endpoints:**
- `GET /cognitive/executive/status` → summary
- `GET /cognitive/executive/initiatives` → list
- `POST /cognitive/executive/initiatives` → create
- `GET /cognitive/executive/workload` → queue depth
- `GET /cognitive/executive/decisions` → decision audit
- `POST /cognitive/executive/plan` → trigger planning
- `GET /cognitive/executive/budget` → token usage

### Guardrails (`guardrails/`)

**Safety mechanisms for autonomous execution.**

| Module | Purpose | Key Functions |
|--------|---------|----------------|
| `spawn_limiter.py` | Concurrency control | `acquire()`, `release()`, per-tenant/agent limits |
| `trust_tier_policy.py` | Agent autonomy levels | `get_tier()`, `set_tier()`, supervised/assisted/autonomous |
| `rate_governor.py` | Decision rate limits | `acquire_decision()`, 60 decisions/min per agent |
| `event_storm_detector.py` | Event flood suppression | `check()`, >100/sec threshold, 10s window |
| `budget_enforcer.py` | Token gate | `enforce()`, blocks when budget exhausted |
| `escalation_gate.py` | HITL routing | `should_escalate()`, risky action routing |

**Endpoints:**
- `GET /cognitive/guardrails/status` → full status
- `GET /cognitive/guardrails/violations` → escalation history
- `GET /cognitive/guardrails/trust-tiers` → agent assignments
- `POST /cognitive/guardrails/trust-tiers/{id}` → set tier
- `GET /cognitive/guardrails/spawn-state` → quota counts
- `GET /cognitive/guardrails/budget` → token status

## Database

SQLite at `~/.ai-employee/cognitive.db` (WAL mode):

**Tables:**
- `objectives` — Hierarchical goals (tenant-scoped)
- `contradictions` — Detected conflicts with resolution tracking
- `wf_fingerprints` — Workflow dedup state (5-min TTL)
- `initiatives` — Strategic work queue with lifecycle
- `executive_decisions` — Planning decision history
- `budget_usage` — Daily token tracking
- `trust_tiers` — Agent autonomy assignments
- `guardrail_violations` — Escalation audit trail

## Integration

### Pipeline Integration

```python
# In unified_pipeline.py (10-phase pipeline)

# Phase 2: Check contradictions
from infra.cognitive.integration import ingest_agent_result
ingest_agent_result(agent_id, tenant_id, agent_output)

# Phase 3: Check loops
from infra.cognitive.integration import detect_trigger_loop
if detect_trigger_loop(source, target, tenant):
    return error("Loop detected")

# Phase 5: Check dedup
from infra.cognitive.integration import check_workflow_duplicate
if check_workflow_duplicate(wf_type, inputs, wf_id, tenant)["duplicate"]:
    return cached_result()

# Phase 6: Check spawn & escalation
from infra.cognitive.integration import (
    acquire_spawn_quota,
    check_action_escalation,
)
if (await acquire_spawn_quota(tenant, agent))["blocked"]:
    return error("Spawn limit")

if check_action_escalation(agent, action, tenant):
    await escalate_to_hitl(action, agent, tenant)

# Phase 8: Record usage
from infra.cognitive.integration import record_token_usage
record_token_usage(tenant, token_count)

# Phase 10: Check coherence
from infra.cognitive.integration import get_coherence_score
score = get_coherence_score(tenant)
if score["overall"] < 50:
    alert("Low coherence")
```

### FastAPI Integration

```python
# In problem-solver-ui/server.py (or main app)

from infra.cognitive.coherence.coherence_routes import router as coh_router
from infra.cognitive.executive.executive_routes import router as exec_router
from infra.cognitive.guardrails.guardrail_routes import router as guard_router
from infra.cognitive.integration import get_cognitive_infrastructure

# Mount routers
app.include_router(coh_router)
app.include_router(exec_router)
app.include_router(guard_router)

# Initialize on startup
@app.on_event("startup")
async def startup():
    cognitive = get_cognitive_infrastructure()
    await cognitive.initialize()

@app.on_event("shutdown")
async def shutdown():
    cognitive = get_cognitive_infrastructure()
    cognitive.shutdown()
```

## Usage Examples

### Check Workflow Duplicate

```python
from infra.cognitive.integration import check_workflow_duplicate

result = check_workflow_duplicate(
    workflow_type="content-generation",
    input_keys=["prompt", "style", "tone"],
    workflow_id="wf-12345",
    tenant_id="tenant-abc",
)

if result["duplicate"]:
    print(f"Duplicate! Reuse {result['existing_workflow_id']}")
else:
    print(f"New workflow {result['workflow_id']}")
```

### Detect Loop

```python
from infra.cognitive.integration import detect_trigger_loop

loop_detected = detect_trigger_loop(
    source_agent="content-generator",
    triggered_agent="email-sender",
    tenant_id="tenant-abc",
)

if loop_detected:
    logger.error("Autonomy loop prevented!")
```

### Acquire Spawn Quota

```python
from infra.cognitive.integration import acquire_spawn_quota

quota = await acquire_spawn_quota(
    tenant_id="tenant-abc",
    agent_id="sales-closer",
)

if quota["blocked"]:
    raise Exception(f"Spawn limited: {quota['reason']}")
```

### Check Escalation

```python
from infra.cognitive.integration import check_action_escalation

if check_action_escalation("hr-manager", "fire", "tenant-abc"):
    # Route to HITL instead of auto-executing
    await escalate_to_human_approval(action, agent, tenant)
```

### Track Budget

```python
from infra.cognitive.integration import record_token_usage, check_token_budget

# After LLM call
record_token_usage("tenant-abc", 15000)

# Before LLM call
if not check_token_budget("tenant-abc"):
    raise Exception("Token budget exhausted")
```

### Get Health Score

```python
from infra.cognitive.integration import get_coherence_score

score = get_coherence_score("tenant-abc")
print(f"Coherence: {score['overall']}/100")
print(f"  Consistency: {score['consistency_score']}")
print(f"  Dedup: {score['dedup_score']}")
print(f"  Loop-free: {score['loop_free_score']}")

if score["overall"] < 50:
    alert("Cognitive health degraded")
```

## Configuration

Optional environment variables:

```bash
# Daily token budget per tenant (default 1M)
export COGNITIVE_DAILY_BUDGET_TOKENS=1000000

# Max concurrent workflows per tenant (default 50)
export COGNITIVE_SPAWN_MAX_TENANT=50

# Max concurrent workflows per agent (default 10)
export COGNITIVE_SPAWN_MAX_AGENT=10

# Cognitive decisions per minute per agent (default 60)
export COGNITIVE_DECISION_RATE_PER_MIN=60

# Event storm threshold: events/sec (default 100)
export COGNITIVE_EVENT_STORM_THRESHOLD=100
```

## Monitoring

### Coherence Health

```
Score < 50   → Alert (inconsistent system)
Score < 30   → Critical (high contradiction rate)
Loops > 5/min → Critical (autonomy cycling)
Dups > 20%   → Warning (high duplicate rate)
```

### Budget Tracking

```
Usage > 80%  → Warning (approaching limit)
Usage > 100% → Critical (budget exhausted, execution blocked)
```

### Guardrails

```
Violations > 0      → Track escalations
Storm suppressions  → Log and alert
Spawn limits hit    → Increase quota or reduce load
```

## Testing

```bash
# Full test suite
pytest tests/test_cognitive_infrastructure.py -v

# Specific test class
pytest tests/test_cognitive_infrastructure.py::TestCoherence -v

# With coverage
pytest tests/test_cognitive_infrastructure.py --cov=runtime/infra/cognitive
```

## Performance

| Operation | Complexity | Latency |
|-----------|-----------|---------|
| Coherence score | O(1000) events | <1ms |
| Loop detection | O(500) edges | <5ms |
| Dedup check | O(1) hash + index | <1ms |
| Spawn quota | O(1) token bucket | <1ms |
| Budget check | O(1) aggregate | <1ms |

**Database:** Typical size 10-50MB (months of data, auto-compacting)

## Documentation

- **ARCHITECTURE.md** — Complete system design (750 lines)
- **INTEGRATION_GUIDE.md** — Integration cookbook (600 lines)
- **This README** — Quick reference

## Troubleshooting

| Issue | Solution |
|-------|----------|
| DB locked | Check multiple processes, use `fuser` to identify |
| High memory | Run `POST /cognitive/coherence/cleanup` |
| No contradictions | Verify `ingest_agent_result()` called post-execution |
| Loops not detected | 60s window resets; short cycles may miss detection |
| Budget not enforced | Verify `record_token_usage()` called in LLM layer |

## Future Enhancements

**Phase 4 Part 4:**
- Distributed coherence (replicated DB)
- ML-based contradiction detection (embeddings)
- Predictive planning (ETA estimation)
- Dynamic trust tier (promotion based on success)
- Cost optimization (cheaper model recommendations)
- Adaptive rate limits (load-based adjustment)

**Phase 5:**
- Causal reasoning (decision provenance)
- Counterfactual analysis (what-if planning)
- Multi-agent coordination (consensus)
- Self-healing (auto-recovery)

## License

Part of AI-EMPLOYEE system. See root LICENSE file.

## Contact

For issues or questions about cognitive infrastructure:
1. Check ARCHITECTURE.md for design details
2. Review INTEGRATION_GUIDE.md for integration patterns
3. Run test suite: `pytest tests/test_cognitive_infrastructure.py -v`
4. Check logs: `grep -i cognitive python-backend.log`
