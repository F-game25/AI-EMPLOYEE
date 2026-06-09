# Phase 4 Test Requirements — Observability, Billing, Intelligence

**Build Date:** 2026-04-29  
**Build Status:** Complete (code written, not yet tested)  
**Next Step:** Execute all tests in order below before considering Phase 4 complete

---

## 1. Sentry Error Tracking Tests

### 1.1 Sentry Initialization

**Test: Sentry initializes when DSN provided**
- Set: `SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id` in `.env`
- Start server: `bash start.sh`
- Check logs: Should show "Sentry initialized: production"
- Expected: Sentry client is available, errors will be captured
- File: `runtime/core/sentry_config.py:15` (init_sentry function)

**Test: Sentry disabled gracefully when DSN missing**
- Unset: `SENTRY_DSN` (or set to empty)
- Start server
- Check logs: Should show "Sentry DSN not configured; error tracking disabled"
- Expected: Server continues normally, no errors from Sentry
- File: `runtime/core/sentry_config.py:9`

### 1.2 Error Capture

**Test: Unhandled exception is captured in Sentry**
- Trigger an error in a route (e.g., divide by zero)
- Check Sentry dashboard: New issue should appear
- Expected: Stack trace, user context, tenant context all visible
- Metadata: environment, release, breadcrumbs
- File: `runtime/core/sentry_config.py:60` (capture_exception)

**Test: Set user context in Sentry**
- Call: `POST /api/chat` with valid token
- Check Sentry: Issue shows user ID, email in context
- Expected: Can filter issues by user_id
- File: `runtime/core/sentry_config.py:70` (set_user_context)

**Test: Set tenant context in Sentry**
- Call: Multiple routes from different tenants
- Check Sentry: Issues tagged with tenant_id
- Expected: Can filter issues by tenant_id
- File: `runtime/core/sentry_config.py:78` (set_tenant_context)

### 1.3 Sentry Status Endpoint

**Test: Get Sentry status**
- Call: `GET /api/observability/sentry`
- Expected: Returns `{"status": "enabled|disabled", "dsn_configured": true|false}`
- With DSN: status="enabled", dsn_configured=true
- Without DSN: status="disabled", dsn_configured=false
- File: `runtime/agents/problem-solver-ui/server.py:26349` (route)

---

## 2. Billing Metrics Tests

### 2.1 Billing Events Recording

**Test: API call is recorded to billing_events**
- Run: Alembic migration `alembic upgrade head` (creates billing_events table)
- Call: `GET /api/agents` with valid token
- Verify: `SELECT COUNT(*) FROM billing_events WHERE event_type='api_call'` > 0
- Expected: Event has tenant_id, endpoint, method, status_code
- File: `runtime/core/billing_metrics.py:25` (record_api_call)

**Test: Agent execution is recorded**
- Call: Agent execution endpoint (e.g., POST /api/agents/run)
- Verify: `SELECT * FROM billing_events WHERE event_type='agent_execution'` has new record
- Expected: Agent ID, duration_ms, tokens_used are captured
- File: `runtime/core/billing_metrics.py:41` (record_agent_execution)

**Test: Database query is recorded**
- Call: `POST /api/db/query` with SELECT statement
- Verify: `SELECT * FROM billing_events WHERE event_type='database_query'` has new record
- Expected: Table, operation (SELECT/INSERT/UPDATE), duration_ms captured
- File: `runtime/core/billing_metrics.py:55` (record_database_query)

### 2.2 Billing Metrics Retrieval

**Test: Get tenant billing metrics**
- Call: `GET /api/billing/metrics`
- Expected: Returns BillingMetrics with:
  - period_start, period_end (30-day window)
  - api_calls, agent_executions, database_queries (counts)
  - estimated_cost_usd (calculated)
  - error_count, storage_mb, trace_spans
- File: `runtime/agents/problem-solver-ui/server.py:26232` (route)

**Test: Cost calculation is correct**
- Setup: Generate known number of API calls, agent executions, database queries
- Call: `GET /api/billing/metrics`
- Expected: estimated_cost_usd matches formula:
  - api_calls × $0.0001 + agent_executions × $0.01 + database_queries × $0.00001
- Example: 100 calls + 10 executions + 1000 queries = $0.01 + $0.10 + $0.01 = $0.12
- File: `runtime/core/billing_metrics.py:130` (_calculate_cost)

### 2.3 All-Tenant Metrics (Admin)

**Test: Admin can view all tenant metrics**
- Setup: Admin user in tenant A
- Call: `GET /api/billing/all-metrics`
- Expected: Returns array of BillingMetrics for all active tenants
- File: `runtime/agents/problem-solver-ui/server.py:26257` (route)

**Test: Non-admin cannot view all metrics**
- Setup: Member user in tenant B
- Call: `GET /api/billing/all-metrics`
- Expected: 403 Forbidden "Admin role required"
- File: `runtime/agents/problem-solver-ui/server.py:26280`

---

## 3. Rate Limiting & Quota Tests

### 3.1 Quota Tier Assignment

**Test: Tenant quota matches subscription tier**
- Setup: Create tenant with tier="starter"
- Call: `GET /api/quota/usage`
- Expected: Returns quota with requests_per_minute=60, agents_per_hour=50, etc.
- Tiers:
  - starter: 60 req/min, 50 agents/hr, 5000 calls/day, 5 GB
  - business: 300, 500, 50000, 50 GB
  - enterprise: 1000, 2000, 500000, 500 GB
- File: `runtime/core/rate_limiter.py:30` (quota_tiers dict)

### 3.2 Request Rate Limiting

**Test: Requests are counted per tenant**
- Setup: Tenant A, send 65 requests in rapid succession
- Expected: First 60 succeed, requests 61-65 blocked with 429 Too Many Requests
- Expected: Error message indicates rate limit exceeded
- File: `runtime/core/rate_limiter.py:57` (check_request_limit)

**Test: Rate limit resets after 1 minute**
- Setup: Hit rate limit (65 requests in <1s)
- Wait: 61 seconds
- Expected: Next request succeeds
- File: `runtime/core/rate_limiter.py:57` (one_minute_ago calculation)

### 3.3 Agent Execution Limiting

**Test: Agent executions limited per hour**
- Setup: Starter tier (50 agents/hour), send 51 agent requests
- Expected: First 50 succeed, 51st blocked
- File: `runtime/core/rate_limiter.py:73` (check_agent_limit)

### 3.4 API Call Daily Limit

**Test: API calls limited per day**
- Setup: Starter tier (5000 calls/day), make 5001 API calls
- Expected: First 5000 succeed, 5001st blocked
- File: `runtime/core/rate_limiter.py:91` (check_api_call_limit)

### 3.5 Quota Usage Endpoint

**Test: Get current quota usage**
- Call: `GET /api/quota/usage`
- Expected: Returns:
  - usage: {requests_this_minute: N, agents_this_hour: M, api_calls_today: K}
  - quota: {requests_per_minute, agents_per_hour, api_calls_per_day, storage_gb}
- File: `runtime/agents/problem-solver-ui/server.py:26297` (route)

---

## 4. Semantic Embeddings Tests

### 4.1 Real Embeddings (sentence-transformers installed)

**Test: Text is embedded to 384 dimensions**
- Setup: `pip install sentence-transformers` (if not already)
- Call: `POST /api/embeddings/embed` with `{"text": "Hello world"}`
- Expected: Returns embedding array of 384 floats, mode="semantic"
- File: `runtime/core/embeddings.py:20` (embed_text with model)

**Test: Same text always produces same embedding**
- Call 1: `POST /api/embeddings/embed` with `{"text": "test"`
- Call 2: `POST /api/embeddings/embed` with same text
- Expected: embedding arrays are identical (deterministic)
- File: `runtime/core/embeddings.py:28` (model.encode is deterministic)

**Test: Similar texts have high similarity**
- Embed: "The cat sat on the mat"
- Embed: "A cat was sitting on a mat"
- Similarity: Should be > 0.8 (semantic similarity)
- File: `runtime/core/embeddings.py:50` (similarity calculation)

**Test: Different texts have low similarity**
- Embed: "The quick brown fox"
- Embed: "Quantum mechanics"
- Similarity: Should be < 0.5
- File: `runtime/core/embeddings.py:50`

### 4.2 Hash-Based Embeddings (sentence-transformers NOT installed)

**Test: Degraded mode when sentence-transformers unavailable**
- Setup: Uninstall or hide sentence-transformers
- Call: `POST /api/embeddings/embed`
- Expected: Returns embedding array of 384 floats, mode="hash-based (degraded)"
- File: `runtime/core/embeddings.py:77` (_hash_based_embedding)

**Test: Hash embeddings are deterministic**
- Same text → same embedding (even in degraded mode)
- File: `runtime/core/embeddings.py:77` (SHA256 hash is deterministic)

### 4.3 Similarity Calculation

**Test: Calculate similarity between embeddings**
- Call: `POST /api/embeddings/similarity`
- Body: `{"embedding_1": [...], "embedding_2": [...]}`
- Expected: Returns `{"similarity": 0.85}` (cosine similarity score, 0-1)
- File: `runtime/agents/problem-solver-ui/server.py:26324` (route)

**Test: Identical embeddings have similarity 1.0**
- Create embedding for "test"
- Compare to itself
- Expected: similarity = 1.0
- File: `runtime/core/embeddings.py:50`

**Test: Zero vectors handled gracefully**
- Call with zero-valued embeddings
- Expected: similarity = 0.0 (not NaN or error)
- File: `runtime/core/embeddings.py:55` (norm1==0 check)

### 4.4 Embeddings Status

**Test: Get embeddings system status**
- Call: `GET /api/observability/embeddings`
- Expected: Returns `{"mode": "semantic|hash-based", "available": true|false, "dimension": 384}`
- With sentence-transformers: mode="semantic", available=true
- Without: mode="hash-based", available=false
- File: `runtime/agents/problem-solver-ui/server.py:26361` (route)

---

## 5. Knowledge Store Bootstrap Tests

### 5.1 Knowledge Seeding

**Test: Knowledge store is bootstrapped on startup**
- Delete: `state/knowledge_store.json`
- Start server
- Check logs: Should show "Knowledge bootstrap: N entries loaded"
- Verify: `state/knowledge_store.json` exists with 10 seed entries
- File: `runtime/core/knowledge_bootstrap.py:102` (bootstrap function)

**Test: Seed entries are loaded correctly**
- Check: `state/knowledge_store.json` contains:
  - kb_system_architecture
  - kb_agent_pattern
  - kb_rbac_roles
  - kb_stripe_integration
  - kb_jaeger_tracing
  - kb_multi_tenancy
  - kb_database_queries
  - kb_authentication
  - kb_rate_limiting
  - kb_error_tracking
- Each entry has: id, title, content, category, tags, created_at
- File: `runtime/core/knowledge_bootstrap.py:11` (SEED_KNOWLEDGE)

**Test: Duplicates are not added on re-bootstrap**
- Run bootstrap twice
- Expected: Same 10 entries, no duplicates
- File: `runtime/core/knowledge_bootstrap.py:115` (check for existing id)

### 5.2 Knowledge Integration

**Test: Knowledge retrieval uses bootstrapped data**
- Setup: Knowledge store bootstrapped with seed data
- Call: Memory retrieval endpoint (if exists) with query "RBAC"
- Expected: Should retrieve kb_rbac_roles entry
- File: `runtime/core/knowledge_bootstrap.py`

---

## 6. Database Migrations Test

### 6.1 Alembic Migrations

**Test: Run all Phase 4 migrations**
- Run: `cd runtime && alembic upgrade head`
- Expected: Three migrations applied:
  - 001_initial_schema
  - 002_add_rbac_tables
  - 003_add_billing_and_observability
- Verify: `alembic current` shows correct revision
- File: `runtime/alembic/versions/003_add_billing_and_observability.py`

**Test: All Phase 4 tables are created**
- Query PostgreSQL:
  ```sql
  SELECT tablename FROM pg_tables WHERE schemaname='public'
  ORDER BY tablename;
  ```
- Expected tables exist:
  - billing_events
  - audit_logs
  - quota_usage
  - embeddings
- File: `runtime/alembic/versions/003_add_billing_and_observability.py:13+`

**Test: All indexes are created**
- Query: `SELECT indexname FROM pg_indexes WHERE schemaname='public'`
- Expected indexes:
  - idx_billing_events_tenant, _type, _created
  - idx_audit_logs_tenant, _user, _action, _created
  - idx_quota_usage_tenant, _metric
  - idx_embeddings_tenant, _created
- File: Same migration file

**Test: Foreign keys are configured correctly**
- Query: `SELECT constraint_name FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY'`
- Expected: tenant_id references tenants(tenant_id) with ON DELETE CASCADE
- File: Migration file

---

## 7. Integration Tests

### 7.1 Full Billing Pipeline

**Test: Tenant execution → billing event → metrics calculation**
1. Execute agent (costs: 1 agent execution @ $0.01)
2. Check billing_events: New entry with event_type='agent_execution'
3. Call `GET /api/billing/metrics`
4. Expected: estimated_cost_usd = $0.01
- File: Integration across multiple modules

### 7.2 Rate Limiting + Billing

**Test: Rate limited requests are still billed**
1. Hit rate limit (60+ requests in <1s for starter tier)
2. Request 61 is rejected with 429
3. Check billing_events: All 61 requests recorded (not just 60)
4. Call `GET /api/billing/metrics`
5. Expected: api_calls = 61
- File: `runtime/core/rate_limiter.py` + `runtime/core/billing_metrics.py`

### 7.3 Embeddings + Knowledge Search

**Test: Use embeddings to find relevant knowledge entries**
1. Embed query: "How do I use RBAC?"
2. Embed all knowledge entries
3. Find most similar: Should be kb_rbac_roles
4. Expected: Cosine similarity > 0.7
- File: `runtime/core/embeddings.py` + `runtime/core/knowledge_bootstrap.py`

### 7.4 Multi-Tenant Isolation in Billing

**Test: Tenant A's billing doesn't leak to Tenant B**
1. Tenant A makes 1000 API calls
2. Tenant B makes 100 API calls
3. Tenant A calls `GET /api/billing/metrics`
4. Expected: api_calls = 1000 (not 1100)
5. Tenant B calls same endpoint
6. Expected: api_calls = 100
- File: `runtime/core/billing_metrics.py:108` (WHERE tenant_id clause)

---

## 8. Error Handling & Edge Cases

### 8.1 Missing Input Handling

**Test: POST /api/embeddings/embed with no text**
- Call: `POST /api/embeddings/embed` with `{"text": ""}`
- Expected: 400 Bad Request with "text required" message
- File: `runtime/agents/problem-solver-ui/server.py:26316`

**Test: Missing embedding in similarity calculation**
- Call: `POST /api/embeddings/similarity` with `{"embedding_1": [...]}`  (missing embedding_2)
- Expected: 400 Bad Request
- File: `runtime/agents/problem-solver-ui/server.py:26335`

### 8.2 Concurrent Billing Events

**Test: Multiple agents execute concurrently, all are billed**
- Setup: 10 agents execute in parallel
- Call: `GET /api/billing/metrics`
- Expected: agent_executions = 10 (all recorded despite concurrency)
- File: `runtime/core/billing_metrics.py` (database insert is atomic)

### 8.3 Rate Limiting with Concurrent Requests

**Test: 100 concurrent requests to same endpoint**
- Send 100 requests in parallel to same route
- Expected: First 60 succeed (starter tier), next 40 return 429
- Order may vary, but total = 60 allowed + 40 rejected
- File: `runtime/core/rate_limiter.py:57` (thread-safe counter)

---

## 9. Performance Tests

### 9.1 Embedding Latency

**Test: Embed text is fast**
- Semantic mode: `POST /api/embeddings/embed` should complete < 500ms
- Hash mode: Should complete < 10ms (no ML model)
- File: `runtime/core/embeddings.py`

### 9.2 Billing Metrics Calculation

**Test: Metrics calculation with 10K events is fast**
- Setup: 10,000 billing_events in database
- Call: `GET /api/billing/metrics`
- Expected: Response < 1 second
- Verify: Database query uses indexes (EXPLAIN ANALYZE)
- File: `runtime/core/billing_metrics.py:108`

### 9.3 Rate Limiter Overhead

**Test: Rate limit check doesn't significantly slow requests**
- Baseline: 100 requests without rate limiting = T ms
- With rate limiting: 100 requests = T + < 50ms overhead
- File: `runtime/core/rate_limiter.py`

---

## 10. Documentation Tests

### 10.1 API Documentation

**Test: All Phase 4 routes documented in OpenAPI**
- Navigate: `http://localhost:8787/docs`
- Expected: All new routes visible:
  - /api/billing/metrics
  - /api/billing/all-metrics
  - /api/quota/usage
  - /api/embeddings/embed
  - /api/embeddings/similarity
  - /api/audit/logs
  - /api/observability/sentry
  - /api/observability/embeddings
- Each route has description, request schema, response schema
- File: Route docstrings in `runtime/agents/problem-solver-ui/server.py`

### 10.2 Environment Variable Documentation

**Test: New env vars documented**
- Check: SENTRY_DSN, JAEGER_*, STRIPE_*
- Expected: All mentioned in CLAUDE.md or docker-compose.yml
- File: `CLAUDE.md` (Environment section)

---

## Test Execution Checklist

When ready to test, execute in this order:

- [ ] Section 1: Sentry Error Tracking Tests (all 3 subsections)
- [ ] Section 2: Billing Metrics Tests (all 3 subsections)
- [ ] Section 3: Rate Limiting & Quota Tests (all 5 subsections)
- [ ] Section 4: Semantic Embeddings Tests (all 4 subsections)
- [ ] Section 5: Knowledge Store Bootstrap Tests (all 2 subsections)
- [ ] Section 6: Database Migrations Test (all 4 subsections)
- [ ] Section 7: Integration Tests (all 4 subsections)
- [ ] Section 8: Error Handling & Edge Cases (all 3 subsections)
- [ ] Section 9: Performance Tests (all 3 subsections)
- [ ] Section 10: Documentation Tests (all 2 subsections)

**Total estimated testing time:** 4-5 hours

**Success criteria:**
- All tests pass without code modifications
- No performance regressions (overhead < 5%)
- No security vulnerabilities
- All new routes properly authenticated
- Multi-tenant isolation verified
- Embeddings work in both modes (semantic and hash-based)
- Billing metrics calculated correctly
- Rate limits enforced correctly
- Knowledge store bootstrapped on startup

---

## Notes for Tester

1. **Sentry Testing:** Requires a Sentry project. Create free account at sentry.io, create project, copy DSN to .env as SENTRY_DSN.

2. **Database Migrations:** Run `cd runtime && alembic upgrade head` before testing. This creates all billing/observability tables.

3. **Sentence-Transformers:** This package is large (~500MB). If bandwidth is limited, test in hash-based mode by temporarily hiding the import.

4. **Rate Limiting:** Uses in-memory counters (local_counters dict). Resets on server restart. For persistent quotas, need to implement database-backed tracking (Phase 5).

5. **Billing Events:** Are recorded for every request. In production, may want to batch inserts or use async logging to avoid performance impact.

6. **Knowledge Store:** Seed data is loaded into JSON file on first boot. For real production, may want to load into database + cache.

7. **Embeddings Dimension:** All embeddings are 384-dim (all-MiniLM-L6-v2 standard). If using different model, adjust dimension constant.

8. **Test Cleanup:** After testing:
   - Delete test billing_events: `DELETE FROM billing_events WHERE created_at < NOW() - INTERVAL 1 DAY`
   - Reset rate limiter: Restart server (or implement manual reset endpoint)
   - Clear test embeddings: `DELETE FROM embeddings WHERE tenant_id = 'test-tenant'`

---

**Test Plan Author:** Claude Code  
**Last Updated:** 2026-04-29  
**Status:** Ready for Execution
