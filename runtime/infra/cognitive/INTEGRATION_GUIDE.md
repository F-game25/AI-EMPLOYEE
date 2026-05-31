# Cognitive Infrastructure Integration Guide

How to integrate Phase 4 cognitive infrastructure into the AI-EMPLOYEE system.

## FastAPI Integration

Add cognitive routers to the main FastAPI application:

```python
# In runtime/agents/problem-solver-ui/server.py (or main app startup)

from fastapi import FastAPI
from infra.cognitive.coherence.coherence_routes import router as coherence_router
from infra.cognitive.executive.executive_routes import router as executive_router
from infra.cognitive.guardrails.guardrail_routes import router as guardrail_router
from infra.cognitive.integration import get_cognitive_infrastructure

app = FastAPI()

# Include cognitive routers
app.include_router(coherence_router)
app.include_router(executive_router)
app.include_router(guardrail_router)

# Initialize cognitive infrastructure on startup
@app.on_event("startup")
async def startup():
    cognitive = get_cognitive_infrastructure()
    await cognitive.initialize()

@app.on_event("shutdown")
async def shutdown():
    cognitive = get_cognitive_infrastructure()
    cognitive.shutdown()
```

## Unified Pipeline Integration

Add cognitive checks to the 10-phase pipeline:

```python
# runtime/core/unified_pipeline.py

from infra.cognitive.integration import (
    check_workflow_duplicate,
    ingest_agent_result,
    detect_trigger_loop,
    acquire_spawn_quota,
    check_action_escalation,
    record_token_usage,
    get_coherence_score,
)

async def unified_pipeline(
    user_input: str,
    tenant_id: str,
    agent_id: str,
) -> TaskGraph:
    """10-phase enforced pipeline with cognitive checks."""

    # Phase 1: retrieve_relevant_nodes
    nodes = retrieve_relevant_nodes(user_input, tenant_id)

    # Phase 2: build_context
    context = build_context(nodes, tenant_id)

    # Cognitive check: Ingest agent result for contradiction detection
    if agent_id:
        previous_result = get_agent_cache(agent_id)
        if previous_result:
            ingest_agent_result(agent_id, tenant_id, previous_result)

    # Phase 3: classify_decision
    decision = classify_decision(context)

    # Cognitive check: Detect if decision creates a loop
    triggered_agent = decision.get("next_agent")
    if triggered_agent and agent_id:
        loop_detected = detect_trigger_loop(agent_id, triggered_agent, tenant_id)
        if loop_detected:
            logger.error(f"Loop detected: {agent_id} -> {triggered_agent}")
            return error_response("Autonomy loop detected")

    # Phase 4: call_llm (with budget check)
    # Cognitive check: Check token budget
    budget_ok = check_token_budget(tenant_id)
    if not budget_ok:
        logger.warning(f"Token budget exhausted for {tenant_id}")
        return error_response("Token budget exhausted")

    llm_response = await call_llm(context)

    # Phase 5: validate_tasks
    tasks = validate_tasks(llm_response)

    # Cognitive check: Check for workflow duplicate
    workflow_id = str(uuid.uuid4())
    input_keys = list(context.keys())
    dup_check = check_workflow_duplicate(
        workflow_type=decision.get("workflow_type", "generic"),
        input_keys=input_keys,
        workflow_id=workflow_id,
        tenant_id=tenant_id,
    )
    if dup_check["duplicate"]:
        logger.info(f"Duplicate workflow detected, reusing {dup_check['existing_workflow_id']}")
        return get_cached_result(dup_check["existing_workflow_id"])

    # Phase 6: execute_tasks
    # Cognitive check: Acquire spawn quota
    if tasks:
        spawn_result = await acquire_spawn_quota(tenant_id, agent_id)
        if spawn_result["blocked"]:
            logger.warning(f"Spawn limit exceeded: {spawn_result['reason']}")
            return error_response(f"Spawn limit: {spawn_result['reason']}")

    # Cognitive check: Check escalation
    for task in tasks:
        if should_escalate(agent_id, task.action_type, tenant_id):
            # Route to HITL gate instead of direct execution
            from core.hitl_gate import hitl_gate
            task.requires_approval = True
            await hitl_gate.queue_approval(task, agent_id, tenant_id)

    execution_results = await execute_tasks(tasks)

    # Phase 7: format_response
    response = format_response(execution_results)

    # Phase 8: update_graph
    # Cognitive check: Record token usage
    token_count = estimate_tokens(llm_response)
    record_token_usage(tenant_id, token_count)

    update_graph(tenant_id, response)

    # Phase 9: monitor_and_improve
    monitor_execution(execution_results)

    # Phase 10: validate_pipeline_integrity
    # Cognitive check: Get coherence score
    score = get_coherence_score(tenant_id)
    if score["overall"] < 50:
        logger.warning(f"Low coherence score: {score['overall']}")

    return response
```

## Agent Trigger Loop Monitoring

Monitor agent-to-agent triggers for cycles:

```python
# In agent execution layer

from infra.cognitive.integration import detect_trigger_loop

async def execute_agent_trigger(
    source_agent: str,
    target_agent: str,
    tenant_id: str,
    **kwargs
):
    """Execute agent trigger with loop detection."""

    # Check for loop before triggering
    loop_detected = detect_trigger_loop(source_agent, target_agent, tenant_id)
    if loop_detected:
        logger.error(f"Loop detected: {source_agent} -> {target_agent}")
        return {
            "success": False,
            "error": "Autonomy loop prevented",
        }

    # Execute trigger
    return await run_agent(target_agent, tenant_id, **kwargs)
```

## HITL Escalation Integration

Route risky actions to human approval:

```python
# In action execution layer

from infra.cognitive.integration import check_action_escalation
from core.hitl_gate import hitl_gate

async def execute_action(
    agent_id: str,
    action: dict,
    tenant_id: str,
):
    """Execute action with escalation gate."""

    requires_escalation = check_action_escalation(
        agent_id,
        action.get("type", "unknown"),
        tenant_id,
    )

    if requires_escalation:
        # Queue for human approval
        approval = await hitl_gate.queue_approval(
            action=action,
            agent_id=agent_id,
            tenant_id=tenant_id,
            reason="Action requires human oversight",
        )

        if not approval.approved:
            return {"success": False, "reason": "Human rejected action"}

    # Execute action
    return await run_action(action)
```

## Token Budget Enforcement

Enforce daily token limits:

```python
# In LLM call layer

from infra.cognitive.integration import check_token_budget, record_token_usage

async def call_llm_with_budget(
    prompt: str,
    tenant_id: str,
    model: str = "claude-3-haiku",
):
    """Call LLM with budget enforcement."""

    # Check budget before calling
    if not check_token_budget(tenant_id):
        logger.warning(f"Token budget exhausted for {tenant_id}")
        raise BudgetExhaustedError(f"Daily token budget exceeded for {tenant_id}")

    # Estimate input tokens
    input_tokens = estimate_tokens(prompt)

    # Call LLM
    response = await anthropic_client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    # Record actual usage
    output_tokens = response.usage.output_tokens
    total_tokens = input_tokens + output_tokens
    record_token_usage(tenant_id, total_tokens)

    return response
```

## Workload Balancing Integration

Monitor and rebalance agent workload:

```python
# In agent orchestration layer

from infra.cognitive.executive import get_workload_balancer

async def route_work_to_agent(
    work_item: dict,
    candidate_agents: list[str],
    tenant_id: str,
):
    """Route work to least-loaded agent."""

    balancer = get_workload_balancer()

    # Get current workload
    workload_state = balancer.get_all()
    agent_states = {s["agent_id"]: s for s in workload_state}

    # Select least-loaded agent
    best_agent = min(
        candidate_agents,
        key=lambda a: agent_states.get(a, {}).get("queue_depth", 0),
    )

    # Register agent with balancer
    balancer.register(best_agent)

    # Route work
    return await execute_agent(best_agent, work_item, tenant_id)
```

## Dashboard Integration

Expose cognitive status in dashboard:

```python
# In dashboard API layer

@app.get("/api/cognitive/status")
async def get_cognitive_status(req: Request):
    """Get cognitive infrastructure status for dashboard."""

    from infra.cognitive.integration import get_cognitive_infrastructure, get_coherence_score
    from infra.cognitive.executive import get_status as budget_status, list_initiatives
    from infra.cognitive.guardrails import list_violations, spawn_state

    tenant_id = get_tenant_id(req)
    cognitive = get_cognitive_infrastructure()

    return {
        "health": cognitive.health(),
        "coherence": get_coherence_score(tenant_id),
        "initiatives": {
            "status": get_initiative_summary(tenant_id),
            "count": len(list_initiatives(tenant_id)),
        },
        "budget": budget_status(tenant_id),
        "guardrails": {
            "violations_count": len(list_violations(tenant_id)),
            "spawn_state": spawn_state(),
        },
    }
```

## Configuration

Set optional environment variables for tuning:

```bash
# Daily token budget per tenant (default 1M)
export COGNITIVE_DAILY_BUDGET_TOKENS=1000000

# Spawn limit: concurrent workflows per tenant (default 50)
export COGNITIVE_SPAWN_MAX_TENANT=50

# Spawn limit: concurrent workflows per agent (default 10)
export COGNITIVE_SPAWN_MAX_AGENT=10

# Cognitive decision rate limit: decisions/min per agent (default 60)
export COGNITIVE_DECISION_RATE_PER_MIN=60

# Event storm threshold: events/sec per channel (default 100)
export COGNITIVE_EVENT_STORM_THRESHOLD=100
```

## Monitoring and Alerts

Set up monitoring for cognitive health:

```python
# In observability layer

from infra.cognitive.integration import get_coherence_score
from infra.cognitive.executive import get_status as budget_status

async def monitor_cognitive_health(tenant_id: str):
    """Monitor cognitive health and emit alerts."""

    score = get_coherence_score(tenant_id)

    if score["overall"] < 50:
        emit_alert(
            level="WARNING",
            message=f"Low coherence score: {score['overall']}",
            tenant_id=tenant_id,
        )

    if score["consistency_score"] < 30:
        emit_alert(
            level="ERROR",
            message=f"High contradiction rate: {score['consistency_score']}",
            tenant_id=tenant_id,
        )

    budget = budget_status(tenant_id)
    if budget["pct"] > 90:
        emit_alert(
            level="WARNING",
            message=f"Token budget {budget['pct']}% used",
            tenant_id=tenant_id,
        )
```

## Testing in Development

```bash
# Run cognitive infrastructure tests
pytest tests/test_cognitive_infrastructure.py -v

# Run specific test class
pytest tests/test_cognitive_infrastructure.py::TestCoherence -v

# Run with coverage
pytest tests/test_cognitive_infrastructure.py --cov=runtime/infra/cognitive
```

## Production Checklist

Before deploying to production:

- [ ] Run full test suite: `pytest tests/test_cognitive_infrastructure.py`
- [ ] Verify database schema: Check `~/.ai-employee/cognitive.db` created with all tables
- [ ] Test routers: Hit each endpoint (`/cognitive/coherence/status`, etc.)
- [ ] Verify background tasks: Loop detector, initiative manager, workload balancer started
- [ ] Check log output: No warnings or errors during initialization
- [ ] Monitor database size: Expect 10-50MB for weeks of data
- [ ] Test failover: Unplug database, verify graceful degradation
- [ ] Load test: Ensure routers handle concurrent requests
- [ ] Integration test: Full pipeline with cognitive checks enabled

## Troubleshooting

**Issue: Database locked**
```
Solution: Ensure only one process has cognitive.db open.
Check: ps aux | grep cognitive
```

**Issue: High memory usage**
```
Solution: Deduplication fingerprints accumulate. Run cleanup:
POST /cognitive/coherence/cleanup
```

**Issue: Contradictions not detected**
```
Solution: Verify contradiction_detector.ingest_result() called after agent executes.
Check logs: grep "contradiction" python-backend.log
```

**Issue: Loops not detected**
```
Solution: Verify loop_detector.add_trigger() called when agent triggers another.
Note: Graph resets every 60s; short-lived cycles may miss detection.
```

**Issue: Budget not enforced**
```
Solution: Verify record_token_usage() called in LLM layer.
Check: SELECT * FROM budget_usage WHERE tenant_id='...'
```

## Performance Tuning

**For high-frequency events:**
- Increase event_storm_detector threshold (default 100/s)
- Batch ingest_result() calls (don't check every single output)

**For many initiatives:**
- Consider archiving old initiatives (update_status(..., "archived"))
- Limit list queries with ORDER BY priority LIMIT 100

**For large deployments:**
- Monitor cognitive.db size; consider WAL checkpoint operations
- Use read-only replicas for reporting queries
- Consider distributed setup with sqlite3-backup for HA

## Future: Distributed Cognitive Infrastructure

For multi-region deployment:

```python
# Future: cognitive.db replication
# - Primary node: active write
# - Replica nodes: read-only (streamed via WAL shipped)
# - Failover: promote replica to primary on failure
```
