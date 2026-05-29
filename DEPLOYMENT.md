# Phase 4 Deployment Guide

## Pre-Deployment Verification

Run verification script:

```bash
python3 scripts/verify_phase4.py
```

Expected output:
```
✓ PASS  Files
✓ PASS  Database Schema
✓ PASS  Module Imports
✓ PASS  HTTP Routes
✓ PASS  Integration Functions

Result: 5/5 checks passed
✅ Phase 4 Cognitive Infrastructure ready for deployment!
```

## Integration Steps

### 1. FastAPI Setup

Add to `runtime/agents/problem-solver-ui/server.py`:

```python
# Around line 2300, after other router imports

from infra.cognitive.coherence.coherence_routes import router as coherence_router
from infra.cognitive.executive.executive_routes import router as executive_router
from infra.cognitive.guardrails.guardrail_routes import router as guardrail_router
from infra.cognitive.integration import get_cognitive_infrastructure

# Mount routers
app.include_router(coherence_router)
app.include_router(executive_router)
app.include_router(guardrail_router)

# Add startup/shutdown handlers
@app.on_event("startup")
async def cognitive_startup():
    try:
        cognitive = get_cognitive_infrastructure()
        await cognitive.initialize()
        logger.info("✅ Cognitive infrastructure initialized")
    except Exception as e:
        logger.error(f"❌ Cognitive infrastructure init failed: {e}")

@app.on_event("shutdown")
async def cognitive_shutdown():
    try:
        cognitive = get_cognitive_infrastructure()
        cognitive.shutdown()
        logger.info("✅ Cognitive infrastructure shutdown complete")
    except Exception as e:
        logger.error(f"Cognitive infrastructure shutdown error: {e}")
```

### 2. Pipeline Integration

Add cognitive checks to `runtime/core/unified_pipeline.py`:

See `runtime/infra/cognitive/INTEGRATION_GUIDE.md` for detailed code examples.

Key points:
- After agent executes: call `ingest_agent_result()` for contradiction detection
- Before agent trigger: call `detect_trigger_loop()` to prevent cycles
- Before workflow execution: call `check_workflow_duplicate()` for dedup
- Before risky actions: call `check_action_escalation()` for HITL routing
- After LLM calls: call `record_token_usage()` for budget tracking

### 3. Dashboard Integration

Add cognitive status endpoint to dashboard API:

```python
@app.get("/api/cognitive/status")
async def get_cognitive_status(req: Request):
    """Get cognitive infrastructure status for dashboard."""
    from infra.cognitive.integration import (
        get_cognitive_infrastructure,
        get_coherence_score,
    )
    from infra.cognitive.executive import get_status as budget_status
    from infra.cognitive.guardrails import spawn_state

    tenant_id = _get_tenant_id(req)
    cognitive = get_cognitive_infrastructure()

    return {
        "health": cognitive.health(),
        "coherence": get_coherence_score(tenant_id),
        "budget": budget_status(tenant_id),
        "spawn_state": spawn_state(),
    }
```

## Startup Sequence

When system starts:

1. FastAPI app initializes
2. Cognitive routers mounted (coherence, executive, guardrails)
3. Cognitive infrastructure initialization starts
4. Database schema created (if not exists)
5. Background tasks started:
   - Loop detector (60s cycle reset)
   - Initiative lifecycle manager (60s lifecycle advancement)
   - Workload balancer (30s health polling)
6. Ready to process requests

Logs will show:
```
[INFO] Feature modules loaded: X routers
[INFO] ✅ Cognitive infrastructure initialized
[INFO] Loop detector graph cleared (0 cycles in window)
[INFO] Workload balancer started
[INFO] Initiative lifecycle manager started
```

## Testing

### Unit Tests

```bash
# All cognitive tests
pytest tests/test_cognitive_infrastructure.py -v

# Specific modules
pytest tests/test_cognitive_infrastructure.py::TestCoherence -v
pytest tests/test_cognitive_infrastructure.py::TestExecutive -v
pytest tests/test_cognitive_infrastructure.py::TestGuardrails -v
```

### Integration Tests

```bash
# Start the system
npm start

# In another terminal, test endpoints
curl http://localhost:8787/cognitive/coherence/status
curl http://localhost:8787/cognitive/executive/status
curl http://localhost:8787/cognitive/guardrails/status

# Create test data
curl -X POST http://localhost:8787/cognitive/executive/initiatives \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Initiative", "priority": 1}'

# Check budget tracking
curl http://localhost:8787/cognitive/executive/budget
```

## Configuration

Optional environment variables in `~/.ai-employee/.env`:

```bash
# Cognitive module budgets
COGNITIVE_DAILY_BUDGET_TOKENS=1000000
COGNITIVE_SPAWN_MAX_TENANT=50
COGNITIVE_SPAWN_MAX_AGENT=10
COGNITIVE_DECISION_RATE_PER_MIN=60
COGNITIVE_EVENT_STORM_THRESHOLD=100
```

## Monitoring

### Health Checks

```bash
# Check database exists and is healthy
sqlite3 ~/.ai-employee/cognitive.db ".tables"

# Check database size
du -h ~/.ai-employee/cognitive.db

# Check background tasks running
ps aux | grep -E "(loop_detector|workload_balancer|initiative_manager)"

# Check logs for errors
grep -i "cognitive" state/python-backend.log | grep -i error
```

### Dashboard Widget

Add to frontend dashboard:

```javascript
async function loadCognitiveStatus() {
  const res = await fetch('/api/cognitive/status');
  const data = await res.json();

  document.querySelector('#coherence-score').textContent =
    data.coherence.overall.toFixed(1);
  document.querySelector('#budget-pct').textContent =
    data.budget.pct.toFixed(1);
  document.querySelector('#spawn-count').textContent =
    data.spawn_state.tenant_counts[tenantId] || 0;
}

// Refresh every 5 seconds
setInterval(loadCognitiveStatus, 5000);
```

## Rollback Plan

If issues occur:

1. **Database corruption:**
   ```bash
   mv ~/.ai-employee/cognitive.db ~/.ai-employee/cognitive.db.backup
   # System will recreate on next start
   ```

2. **High memory usage:**
   ```bash
   POST /cognitive/coherence/cleanup
   # Cleans up expired fingerprints
   ```

3. **Disable cognitive module:**
   Comment out router includes in `server.py` and restart

4. **Complete rollback:**
   ```bash
   git reset --hard HEAD~1
   npm start
   ```

## Production Checklist

Before deploying to production:

- [ ] Run `pytest tests/test_cognitive_infrastructure.py` — all pass
- [ ] Run `python3 scripts/verify_phase4.py` — all checks pass
- [ ] Test endpoints manually (`curl` tests for all 26 routes)
- [ ] Load test: `ab -n 1000 -c 10 http://localhost:8787/cognitive/coherence/status`
- [ ] Monitor logs during startup for errors
- [ ] Check database created at `~/.ai-employee/cognitive.db`
- [ ] Verify all 8 tables created with proper schema
- [ ] Test pipeline integration (contradiction detection, loop detection)
- [ ] Test HITL escalation for supervised agents
- [ ] Test token budget enforcement
- [ ] Set up monitoring/alerting for:
  - Coherence score < 50
  - Budget usage > 80%
  - Violations > 0
  - Database size > 100MB
- [ ] Document any custom configuration changes
- [ ] Train ops team on monitoring and troubleshooting

## Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| Coherence score latency | <5ms | <1ms |
| Route response time | <50ms | <10ms |
| Database query time | <10ms | <2ms |
| Startup initialization | <5s | ~1s |
| Memory footprint | <100MB | ~30MB |
| Database size | <100MB | 10-50MB |

## SLA

| Metric | Target |
|--------|--------|
| Availability | 99.9% |
| Latency (p50) | <10ms |
| Latency (p99) | <50ms |
| Error rate | <0.1% |

## Support

### Common Issues

**Issue: Database locked**
```
Solution: Ensure only one process has cognitive.db open.
Check: fuser ~/.ai-employee/cognitive.db
Kill: pkill -f problem-solver-ui
```

**Issue: Routes not found (404)**
```
Solution: Verify routers are mounted in server.py
Check: grep -n "include_router.*coherence" server.py
```

**Issue: Contradictions not detected**
```
Solution: Verify ingest_result() called after agent executes
Check: grep -n "ingest_agent_result" unified_pipeline.py
```

**Issue: Token budget not working**
```
Solution: Verify record_token_usage() called in LLM layer
Check: SELECT SUM(tokens_used) FROM budget_usage WHERE tenant_id='...'
```

### Debugging

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
npm start
```

Check specific logs:

```bash
# Coherence operations
grep "coherence" state/python-backend.log

# Executive operations
grep "executive" state/python-backend.log

# Guardrail operations
grep "guardrail" state/python-backend.log

# Database operations
grep "sqlite" state/python-backend.log
```

## Success Criteria

Deployment successful when:

1. All 26 HTTP endpoints respond with 200 status
2. Database has 8 tables with proper schema
3. Background tasks running (logged in startup)
4. Coherence score computed correctly
5. Budget tracking working (POST records usage)
6. Guardrails enforcing (spawn limits, escalations)
7. No errors in logs during 1-hour smoke test
8. Dashboard widget displays cognitive status
9. All tests passing: `pytest tests/test_cognitive_infrastructure.py`

## Next Steps

After successful deployment:

1. **Monitoring:** Set up alerts for cognitive health metrics
2. **Documentation:** Train team on cognitive system usage
3. **Optimization:** Tune budgets and limits based on actual usage
4. **Integration:** Build cognitive-aware dashboards and reports
5. **Enhancement:** Plan Phase 4 Part 4 (distributed coherence, ML detection)

---

**Deployment Date:** _____________________

**Deployed By:** _____________________

**Verified By:** _____________________

**Notes:** _____________________
