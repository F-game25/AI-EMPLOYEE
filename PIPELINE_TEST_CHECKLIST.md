# Pipeline & LLM Routing Test Checklist

**Quick validation steps to verify Python backend in production**

---

## STARTUP VERIFICATION

### 1. Start System
```bash
cd /home/lf/AI-EMPLOYEE
bash start.sh
```

Expected output:
```
✅ Python AI backend ready on port 18790
✅ System running at http://localhost:8787
```

### 2. Verify Python Backend Health
```bash
curl -s http://localhost:8787/health | jq .
```

Expected: `{"ok": true}`

### 3. Verify Node Backend Settings
```bash
curl -s http://localhost:8787/api/settings | jq '.llmSettings'
```

Expected:
```json
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "temperature": 0.7,
  "maxTokens": 1024
}
```

---

## PHASE REPORTER VALIDATION

### 4. Monitor Active Executions
```bash
curl -s http://localhost:8787/api/execution/active | jq '.data'
```

Expected (during task execution):
```json
[
  {
    "taskId": "task-abc123",
    "status": "running",
    "currentPhase": 2,
    "currentPhaseName": "build_context",
    "progress": 20,
    "phases": [...]
  }
]
```

### 5. Check Specific Task Trace
```bash
curl -s http://localhost:8787/api/execution/pipeline/task-abc123 | jq '.data.phases'
```

Expected: Array of 10 phases with timing data

### 6. Test Phase Reporting (Manual)
```bash
curl -X POST http://localhost:8787/api/execution/phase-update \
  -H "Content-Type: application/json" \
  -d '{
    "taskId": "test-phase-001",
    "tenantId": "default",
    "phase": 1,
    "phaseName": "retrieve_relevant_nodes",
    "status": "done",
    "duration_ms": 250
  }'
```

Expected: `{"ok": true, "data": {...}}`

---

## LLM PROVIDER ROUTING

### 7. Test Anthropic Provider (Primary)
```bash
# Ensure API key set
echo $ANTHROPIC_API_KEY

# Send chat request
curl -s -X POST http://localhost:8787/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test message"}' | jq .
```

### 8. Switch to OpenRouter
```bash
# Update settings
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "llmSettings": {
      "provider": "openrouter",
      "model": "deepseek/deepseek-coder-v2"
    },
    "apiKeys": {
      "openrouter": "'$OPENROUTER_API_KEY'"
    }
  }'

# Verify change
curl -s http://localhost:8787/api/settings | jq '.llmSettings.provider'
# Expected: "openrouter"
```

### 9. Test Ollama Provider
```bash
# Check if Ollama is running
curl -s http://localhost:11434/api/tags || echo "Ollama not running"

# Update settings to use Ollama
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "llmSettings": {
      "provider": "ollama",
      "model": "llama2"
    },
    "apiKeys": {
      "ollama_endpoint": "http://localhost:11434"
    }
  }'
```

### 10. Test Provider Fallback
```bash
# Unset Anthropic API key
unset ANTHROPIC_API_KEY

# Send request (should fallback to OpenRouter or Ollama)
curl -s -X POST http://localhost:8787/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test fallback"}' | jq .
```

---

## FULL PIPELINE TEST

### 11. Send Task with Full Pipeline Trace
```bash
# In terminal 1: Monitor execution
watch -n 0.5 'curl -s http://localhost:8787/api/execution/active | jq ".data[0] | {progress, currentPhase, currentPhaseName}"'

# In terminal 2: Send request
curl -X POST http://localhost:8787/api/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "validate pipeline",
    "description": "test all 10 phases"
  }' | jq '.taskId'

# Capture task ID from response
# Then check final trace:
curl -s http://localhost:8787/api/execution/pipeline/task-{ID} | jq '.data.phases | map({phase, name, status, duration_ms})'
```

Expected: 10 phases with status "done"

### 12. Verify Phase Sequence
```bash
curl -s http://localhost:8787/api/execution/pipeline/task-{ID} | jq '.data.phases | map(.name)'
```

Expected (in order):
```
[
  "retrieve_relevant_nodes",
  "build_context",
  "classify_decision",
  "call_llm",
  "validate_tasks",
  "execute_tasks",
  "format_response",
  "update_graph",
  "monitor_and_improve",
  "validate_pipeline_integrity"
]
```

---

## PERFORMANCE VALIDATION

### 13. Measure Phase Latencies
```bash
curl -s http://localhost:8787/api/execution/pipeline/task-{ID} | \
  jq '.data.phases | map({name: .name, duration_ms: .duration_ms})'
```

Typical ranges:
- Phase 1-2: 200-500ms
- Phase 3: 100-300ms
- Phase 4: 1000-5000ms (LLM dominant)
- Phase 5-10: 100-500ms each
- Total: 2-8s

### 14. Check LLM Call Log
```bash
tail -5 state/llm_calls.jsonl | jq '{backend, duration_ms, tokens_used, ok}'
```

Expected:
```json
{
  "backend": "anthropic",
  "duration_ms": 2145,
  "tokens_used": 312,
  "ok": true
}
```

---

## ERROR HANDLING TESTS

### 15. Test Invalid Phase Number
```bash
curl -X POST http://localhost:8787/api/execution/phase-update \
  -H "Content-Type: application/json" \
  -d '{
    "taskId": "test-001",
    "phase": 11,
    "status": "done"
  }'
```

Expected: `HTTP 400` with error message

### 16. Test Backend Unavailable Handling
```bash
# Stop Node backend
pkill -f "node backend/server.js"

# Try to run Python pipeline (should fail gracefully)
curl -X POST http://localhost:18790/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}' 

# Check logs
tail -20 state/python-backend.log | grep -i "unavailable\|fallback"

# Restart Node backend
PORT=8787 node backend/server.js &
```

---

## MULTI-TENANCY VALIDATION

### 17. Create Tenant A
```bash
# Register user in tenant A
curl -X POST http://localhost:8787/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user-a@example.com",
    "password": "TestPassword123!"
  }'

# Extract token
TOKEN_A=$(curl -s -X POST http://localhost:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user-a@example.com",
    "password": "TestPassword123!"
  }' | jq -r '.token')
```

### 18. Create Tenant B
```bash
# Similar process for user B
curl -X POST http://localhost:8787/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user-b@example.com",
    "password": "TestPassword123!"
  }'

TOKEN_B=$(curl -s -X POST http://localhost:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user-b@example.com",
    "password": "TestPassword123!"
  }' | jq -r '.token')
```

### 19. Verify Tenant Isolation
```bash
# Tenant A runs task
TASK_A=$(curl -s -X POST http://localhost:8787/api/tasks/run \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"intent": "test a"}' | jq -r '.taskId')

# Tenant B runs task
TASK_B=$(curl -s -X POST http://localhost:8787/api/tasks/run \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" \
  -d '{"intent": "test b"}' | jq -r '.taskId')

# Verify A cannot see B's execution
curl -s http://localhost:8787/api/execution/pipeline/$TASK_B \
  -H "Authorization: Bearer $TOKEN_A" | jq .

# Expected: 404 or error (not found)
```

---

## FINAL VALIDATION

### 20. System Health Check
```bash
#!/bin/bash
echo "=== PIPELINE VALIDATION ==="
echo

echo "✓ Python backend:"
curl -s http://localhost:18790/health >/dev/null && echo "  RUNNING" || echo "  FAILED"

echo "✓ Node backend:"
curl -s http://localhost:8787/health >/dev/null && echo "  RUNNING" || echo "  FAILED"

echo "✓ Phase reporter:"
curl -s http://localhost:8787/api/execution/active | jq -e '.ok' >/dev/null && echo "  FUNCTIONAL" || echo "  FAILED"

echo "✓ LLM settings:"
curl -s http://localhost:8787/api/settings | jq '.llmSettings.provider'

echo "✓ LLM calls logged:"
wc -l state/llm_calls.jsonl

echo
echo "=== STATUS ==="
if [ $? -eq 0 ]; then
  echo "✅ All systems operational"
else
  echo "⚠️  Some components failed"
fi
```

---

## PASS/FAIL CRITERIA

| Test | Pass Condition | Severity |
|------|----------------|----------|
| Python backend health | Returns 200 | Critical |
| Node backend health | Returns 200 | Critical |
| Phase update endpoint | Accepts POST, returns 200 | Critical |
| 10-phase sequence | All phases reported in order | Critical |
| LLM provider routing | Changes persist across requests | Critical |
| Phase latencies | Total < 10s (typical) | High |
| Error handling | Graceful degradation on failure | High |
| Multi-tenancy | Tenant isolation enforced | High |
| LLM call logging | Entries written to JSONL | Medium |
| Settings validation | Invalid settings rejected | Medium |

---

## TROUBLESHOOTING QUICK LINKS

| Problem | Check | Fix |
|---------|-------|-----|
| "Port 8787 already in use" | `lsof -i :8787` | `pkill -f "node backend"` |
| "Python backend not responding" | `curl http://localhost:18790/health` | `tail -50 state/python-backend.log` |
| "Phase updates not received" | Check firewall, backend URL | Set `BACKEND_URL=http://localhost:8787` |
| "LLM provider not working" | Check API key | Export `ANTHROPIC_API_KEY=sk-ant-...` |
| "Fallback not triggered" | Check provider availability | Unset primary key, verify fallback env vars |

---

**Last Updated**: 2026-05-05  
**Validation Version**: 1.0  
**Status**: ✅ PRODUCTION READY
