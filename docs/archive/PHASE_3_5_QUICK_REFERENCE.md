# Phase 3.5 Quick Reference

## Integration Quick Start

### Using PhaseReporter in Your Code

```python
from core.phase_reporter import PhaseReporter

# Initialize reporter
reporter = PhaseReporter(
    backend_url="http://localhost:8787",
    task_id="task-123",
    tenant_id="default"
)

# Report phase start
reporter.report_phase(1, "retrieve_relevant_nodes", "running")

# ... do work ...

# Report phase done
reporter.report_phase(1, "retrieve_relevant_nodes", "done", duration_ms=1250)

# Report phase failed
reporter.report_phase(4, "call_llm", "failed", error="Connection timeout")
```

### Phase Names (Use Exactly)

1. `retrieve_relevant_nodes`
2. `build_context`
3. `classify_decision`
4. `call_llm`
5. `validate_tasks`
6. `execute_tasks`
7. `format_response`
8. `update_graph`
9. `monitor_and_improve`
10. `validate_pipeline_integrity`

### Status Values

- `"running"` — Phase started
- `"done"` — Phase completed successfully
- `"failed"` — Phase failed with error

## Environment Variables

```bash
# Backend URL (default: http://localhost:8787)
export BACKEND_URL="http://localhost:8787"

# Enable strict mode (fail on phase errors)
export STRICT_PIPELINE=1

# Debug logging
export LOG_LEVEL=DEBUG
```

## Testing

```bash
# Run phase reporting tests
python3 runtime/core/test_llm_router.py

# Check reporter initialization
python3 -c "from core.phase_reporter import PhaseReporter; print('✓ OK')"

# Verify backend endpoint
curl -X POST http://localhost:8787/api/execution/phase-update \
  -H "Content-Type: application/json" \
  -d '{"taskId":"test","phase":1,"status":"running"}'
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Reports not sent | Check `BACKEND_URL` env var, ensure backend running |
| High latency | Check network, verify backend CPU/memory |
| Connection refused | Start Node backend: `node backend/server.js` |
| Wrong phase names | Use exact names from list above |
| Tenant not propagated | Pass `tenant_id` to PhaseReporter constructor |

## Dashboard Integration

**Phase updates automatically flow to:**
- In-memory trace Map in backend
- WebSocket broadcast to connected clients
- Frontend real-time visualization

**No additional code needed** — just use `PhaseReporter` and the rest happens automatically.

## API Endpoint

```
POST /api/execution/phase-update

{
  "taskId": "task-abc123",
  "tenantId": "default",
  "phase": 1,
  "phaseName": "retrieve_relevant_nodes",
  "status": "done",
  "duration_ms": 1250,
  "input": {...},
  "output": {...}
}
```

## Monitoring

**View active executions:**
```bash
curl http://localhost:8787/api/execution/active
```

**Fetch completed task trace:**
```bash
curl http://localhost:8787/api/execution/pipeline/task-abc123
```

## Integration Points

- `orchestrator.py`: `TaskOrchestrator.route_task()` — phases 1-10
- `unified_pipeline.py`: `process_user_input()` — phases 1-10
- Both auto-generate task IDs and track phases automatically

## Cost

- ~10-20ms per phase report (HTTP POST)
- ~100-200ms total per task execution
- Graceful fallback if backend unavailable (no impact)

## Key Features

✅ Real-time phase tracking  
✅ Graceful fallback when backend unavailable  
✅ Automatic retry with exponential backoff  
✅ Multi-tenancy support  
✅ Zero breaking changes  
✅ Zero performance impact on failures  
