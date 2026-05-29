# Phase 4 Operations Checklist

Pre-deployment, deployment, and post-deployment verification steps for cognitive infrastructure.

---

## PRE-DEPLOYMENT CHECKLIST

### 1. Database Preparation

- [ ] **Verify SQLite availability**
  ```bash
  sqlite3 :memory: "SELECT sqlite_version();"
  ```
  Expected: 3.30+

- [ ] **Check ~/.ai-employee directory permissions**
  ```bash
  ls -ld ~/.ai-employee/
  ```
  Should be: `drwxrwxr-x` (755)

- [ ] **Create cognitive.db with proper WAL mode**
  ```bash
  python3 -c "from runtime.infra.cognitive.db import cognitive_conn; c = cognitive_conn(); print('✅ DB initialized')"
  ```

### 2. Python Dependencies

- [ ] **Verify psutil installed** (for AdaptiveThrottler)
  ```bash
  python3 -c "import psutil; print(psutil.cpu_percent())"
  ```

- [ ] **Verify asyncio available** (Python 3.10+)
  ```bash
  python3 -c "import asyncio; print(asyncio.run(asyncio.sleep(0)))"
  ```

- [ ] **Verify FastAPI/uvicorn available**
  ```bash
  python3 -c "from fastapi import APIRouter; print('✅ FastAPI available')"
  ```

### 3. Code Integration

- [ ] **Verify Phase 4 router mounts in server.py**
  ```bash
  grep -c "phase4_router" runtime/agents/problem-solver-ui/server.py
  ```
  Expected: ≥1

- [ ] **Verify all 12 cognitive modules import correctly**
  ```bash
  python3 << 'EOF'
  from runtime.infra.cognitive.resilience import (
      get_event_prioritizer, get_subsystem_isolator, get_adaptive_throttler,
      get_load_shedder, get_backpressure_propagator
  )
  from runtime.infra.cognitive.observability import (
      get_tracer, get_lineage_tracker, get_reasoning_lineage_tracker,
      get_heatmap_aggregator, get_anomaly_correlator
  )
  from runtime.infra.cognitive.scale import (
      get_adaptive_cache, get_graph_partitioner, get_memory_compactor,
      get_ws_batcher, get_event_compressor
  )
  print("✅ All 12 modules imported successfully")
  EOF
  ```

- [ ] **Run test suite**
  ```bash
  python3 -m pytest tests/test_phase4_cognitive_infrastructure.py -v
  ```
  Expected: All tests pass

### 4. Configuration Review

- [ ] **Review resilience thresholds** (in code or settings.json)
  - EventPrioritizer queue sizes (P0=1000, P1=5000, P2=10000, P3=50000)
  - AdaptiveThrottler CPU thresholds (70%, 85%, 95%)
  - BackpressurePropagator thresholds (high=80%, clear=40%)
  - LoadShedder queue thresholds (10k, 50k, 100k)

- [ ] **Review observability config**
  - Database persistence enabled (SQLite)
  - Anomaly correlation time window = 60s
  - Span TTL appropriate for workload

- [ ] **Review scale config**
  - Cache max entries = 1000
  - Cache TTL = 60s
  - Graph partition node limit = 50,000
  - WS batch window = 50ms
  - Event compression threshold = 5/s

---

## DEPLOYMENT CHECKLIST

### 1. Pre-Startup Validation

- [ ] **Stop any running instances**
  ```bash
  bash stop.sh 2>/dev/null || true
  ```

- [ ] **Verify no stale processes**
  ```bash
  ps aux | grep -E "(uvicorn|problem-solver|python)" | grep -v grep
  ```
  Expected: No running server processes

- [ ] **Check disk space**
  ```bash
  df -h ~ | tail -1
  ```
  Expected: >1GB free (for logs + database)

### 2. Startup Verification

- [ ] **Start system**
  ```bash
  bash start.sh
  ```

- [ ] **Wait for readiness** (~30s)
  ```bash
  sleep 30
  curl http://localhost:8787/health || echo "Not ready yet"
  ```

- [ ] **Verify Phase 4 routes mounted**
  ```bash
  curl http://localhost:8787/cognitive/resilience/status | jq .
  ```
  Expected: 200 response with degradation_level

- [ ] **Check for startup errors**
  ```bash
  tail -50 state/python-backend.log | grep -i "error\|failed\|exception"
  ```
  Expected: No critical errors (warnings acceptable)

### 3. Subsystem Checks

- [ ] **Resilience subsystem**
  ```bash
  curl http://localhost:8787/cognitive/resilience/status | jq '.system_load'
  ```
  Expected: `{"cpu_percent": X, "mem_percent": Y, "degradation_level": "none"}`

- [ ] **Observability subsystem**
  ```bash
  curl http://localhost:8787/cognitive/observability/anomaly-correlations | jq '.count'
  ```
  Expected: 0 or number (no error)

- [ ] **Scale subsystem**
  ```bash
  curl http://localhost:8787/cognitive/scale/metrics | jq '.cache_metrics'
  ```
  Expected: `{"hits": 0, "misses": 0, "hit_rate": 0, ...}`

### 4. Database Verification

- [ ] **Check cognitive.db was created**
  ```bash
  ls -lh ~/.ai-employee/cognitive.db
  ```
  Expected: File exists, size >10KB

- [ ] **Verify WAL mode enabled**
  ```bash
  sqlite3 ~/.ai-employee/cognitive.db "PRAGMA journal_mode;"
  ```
  Expected: `wal`

- [ ] **Verify tables created**
  ```bash
  sqlite3 ~/.ai-employee/cognitive.db ".tables"
  ```
  Expected: `spans workflow_lineage anomaly_correlations ...`

### 5. Load Generation Test (Optional)

- [ ] **Generate light traffic**
  ```bash
  for i in {1..10}; do
    curl -s http://localhost:8787/cognitive/resilience/status > /dev/null
  done
  ```

- [ ] **Check metrics updated**
  ```bash
  curl http://localhost:8787/cognitive/scale/metrics | jq '.ws_batch_metrics.total_messages'
  ```
  Expected: ≥0

---

## POST-DEPLOYMENT CHECKLIST

### 1. 5-Minute Smoke Test

- [ ] **Dashboard loads**
  ```bash
  curl -s http://localhost:8787/ | grep -q "<!DOCTYPE" && echo "✅ Dashboard OK"
  ```

- [ ] **All Phase 4 endpoints respond**
  ```bash
  for ep in resilience observability scale; do
    curl -s http://localhost:8787/cognitive/$ep/status | jq -e . > /dev/null && echo "✅ $ep OK"
  done
  ```

- [ ] **No error logs**
  ```bash
  tail -100 state/python-backend.log | grep -i "critical\|fatal" | wc -l
  ```
  Expected: 0

### 2. 1-Hour Stability Test

- [ ] **Monitor system load**
  ```bash
  watch -n 5 'curl -s http://localhost:8787/cognitive/resilience/status | jq .system_load'
  ```
  Expected: Degradation level stays "none" or "light" (not severe)

- [ ] **Monitor queue depths**
  ```bash
  watch -n 10 'curl -s http://localhost:8787/cognitive/resilience/queue-depths | jq .states'
  ```
  Expected: All subsystems have queue_depth <5000

- [ ] **Check no backpressure**
  ```bash
  curl -s http://localhost:8787/cognitive/resilience/queue-depths | jq '.states | to_entries | map(select(.value.is_backpressured)) | length'
  ```
  Expected: 0

### 3. Database Health

- [ ] **Check database size growth**
  ```bash
  ls -lh ~/.ai-employee/cognitive.db
  ```
  Expected: >100KB (spans, lineage being recorded)

- [ ] **Verify no corruption**
  ```bash
  sqlite3 ~/.ai-employee/cognitive.db "PRAGMA integrity_check;"
  ```
  Expected: `ok`

- [ ] **Check WAL checkpoint working**
  ```bash
  ls -lh ~/.ai-employee/cognitive.db-*
  ```
  Expected: WAL files exist but not growing unboundedly

### 4. Metrics & Observability

- [ ] **Create a sample trace**
  ```bash
  curl -X POST http://localhost:8787/cognitive/observability/traces \
    -H "Content-Type: application/json" \
    -d '{"trace_id": "test-trace-123", "operation": "test"}'
  ```

- [ ] **Retrieve the trace**
  ```bash
  curl http://localhost:8787/cognitive/observability/traces/test-trace-123 | jq .
  ```
  Expected: Trace details returned

- [ ] **Cache metrics non-zero**
  ```bash
  curl http://localhost:8787/cognitive/scale/metrics | jq '.cache_metrics | .hits + .misses'
  ```
  Expected: ≥0

### 5. Stress Test (Optional, after stable 1 hour)

- [ ] **Generate 1000 rapid requests**
  ```bash
  for i in {1..1000}; do
    curl -s http://localhost:8787/cognitive/resilience/status > /dev/null &
  done
  wait
  ```

- [ ] **Check degradation handling**
  ```bash
  curl http://localhost:8787/cognitive/resilience/status | jq '.system_load.degradation_level'
  ```
  Expected: "light", "moderate", or "none" (not crash)

- [ ] **Verify event queue didn't overflow**
  ```bash
  curl http://localhost:8787/cognitive/resilience/events | jq '.event_stats'
  ```
  Expected: See `dropped` counts (acceptable if load was extreme)

---

## MONITORING SETUP (ONGOING)

### 1. Prometheus Metrics (if enabled)

- [ ] **Verify /metrics endpoint**
  ```bash
  curl http://localhost:8787/metrics | grep ai_employee
  ```
  Expected: `ai_employee_tasks_total`, `ai_employee_errors_total`, etc.

### 2. Log Rotation

- [ ] **Verify log rotation configured**
  ```bash
  grep -A 5 "handlers.RotatingFileHandler" runtime/agents/problem-solver-ui/server.py
  ```
  Expected: RotatingFileHandler with maxBytes, backupCount

### 3. Database Maintenance

- [ ] **Weekly: Monitor cognitive.db size**
  ```bash
  du -sh ~/.ai-employee/cognitive.db
  ```
  Expected: <100MB (if not, consider archiving old spans)

- [ ] **Weekly: Run VACUUM to reclaim space**
  ```bash
  sqlite3 ~/.ai-employee/cognitive.db "VACUUM;"
  ```

- [ ] **Weekly: Trigger memory compaction**
  ```bash
  curl -X POST http://localhost:8787/cognitive/scale/compact-memory | jq .
  ```

### 4. Alerting Rules (Example for monitoring system)

```yaml
# Alert on high degradation level
- alert: CognitiveInfraHighDegradation
  expr: degradation_level == "severe"
  for: 1m
  action: page-on-call

# Alert on queue overflow
- alert: EventQueueOverflow
  expr: event_queue_size > 50000
  for: 5m
  action: auto-shed-p2-p3

# Alert on cache hit rate collapse
- alert: CacheHitRateCollapse
  expr: cache_hit_rate < 0.3
  for: 10m
  action: investigate-key-cardinality
```

---

## ROLLBACK PROCEDURE

If critical issues detected post-deployment:

### 1. Immediate Rollback

```bash
# 1. Stop current instance
bash stop.sh

# 2. Revert to previous commit (if using git)
git revert HEAD
# OR restore from backup
cp .backup/cognitive.db ~/.ai-employee/cognitive.db

# 3. Restart
bash start.sh

# 4. Verify rollback
curl http://localhost:8787/health
```

### 2. Data Preservation

```bash
# Backup current cognitive.db before rollback
cp ~/.ai-employee/cognitive.db ~/.ai-employee/cognitive.db.$(date +%s).backup
```

### 3. Escalation

- [ ] **If data corruption detected**
  - Do NOT use rolled-back database
  - Restore from last known good backup
  - File incident report

---

## TROUBLESHOOTING DURING DEPLOYMENT

### Issue: "Database locked"
```bash
# Kill any lingering processes
pkill -f "problem-solver-ui"
sleep 2

# Verify lock files gone
ls ~/.ai-employee/cognitive.db-* 2>/dev/null || echo "No lock files"

# Restart
bash start.sh
```

### Issue: "Phase 4 routes not mounted"
```bash
# Check import errors
python3 -c "from runtime.infra.api.phase4_routes import phase4_router"

# Check logs
grep "phase4" state/python-backend.log | tail -20
```

### Issue: "High CPU after startup"
```bash
# Check AdaptiveThrottler polling
grep "adaptive_throttler" state/python-backend.log

# Increase poll interval if needed
# In adaptive_throttler.py: __init__(self, poll_interval_s=10.0)
```

### Issue: "Backpressure never emits signal"
```bash
# Verify message bus available
python3 -c "from runtime.core.bus import get_message_bus; print(get_message_bus())"

# Check bus logs
grep "backpressure" state/python-backend.log
```

---

## SUCCESS CRITERIA

After deployment, confirm:

- [ ] All 12 cognitive subsystems operational (✅ status endpoint responds)
- [ ] Database created with 3+ tables and proper schema
- [ ] Zero critical errors in logs (warnings acceptable)
- [ ] System load stays "none" or "light" under normal traffic
- [ ] No queue overflow or event shedding
- [ ] Cache hit rate >10% after 10 min warmup
- [ ] WebSocket batcher functioning (check metrics endpoint)
- [ ] Traces recorded and retrievable (sampling works)
- [ ] Anomaly correlator has no recent correlations (healthy state)
- [ ] Memory compaction scheduled for weekly execution

---

## Post-Deployment Handoff

**Engineering Owner**: Document in runbook:
- [ ] Baseline metrics captured (CPU, memory, latency)
- [ ] On-call escalation contacts
- [ ] Monitoring dashboard links
- [ ] Rollback procedure tested

**Operations Owner**: Verify:
- [ ] Weekly maintenance scheduled (memory compaction)
- [ ] Database backups configured
- [ ] Log rotation verified
- [ ] Alert thresholds set appropriately

---

## Documentation References

- Architecture: `/docs/PHASE4_COGNITIVE_INFRASTRUCTURE.md`
- Integration: `/docs/PHASE4_INTEGRATION_GUIDE.md`
- Tests: `/tests/test_phase4_cognitive_infrastructure.py`
- Schema: `runtime/infra/cognitive/db.py` and module schema files
