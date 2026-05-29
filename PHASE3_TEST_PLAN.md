# Phase 3 Test Requirements — Auth & Security, Stripe, Jaeger, RBAC

**Build Date:** 2026-04-28  
**Build Status:** Complete (code written, not yet tested)  
**Next Step:** Execute all tests in order below before considering Phase 3 complete

---

## 1. RBAC System Tests

### 1.1 Role Creation & Assignment

**Test: Create RBAC users table via migration**
- Run: `cd runtime && alembic upgrade head`
- Expected: No errors, `user_roles` table created with (user_id, tenant_id, role) composite PK
- Verify: `SELECT * FROM user_roles;` returns empty set
- Location: `/home/lf/AI-EMPLOYEE/runtime/alembic/versions/002_add_rbac_tables.py`

**Test: Assign role to user**
- Setup: Create a test tenant and user via API
- Call: `POST /api/rbac/assign-role` with `{ "user_id": "test-user", "role": "member" }`
- Expected: Returns `{"status": "assigned", "user_id": "test-user", "role": "member"}`
- Verify: `SELECT role FROM user_roles WHERE user_id='test-user'` returns "member"
- Negative: Non-admin user calling this endpoint → expect `403 Forbidden`
- File: `runtime/agents/problem-solver-ui/server.py:26101` (route)

### 1.2 Role Permission Checks

**Test: Get current user's role**
- Call: `GET /api/rbac/user-role` with valid JWT token
- Expected: Returns `{"user_id": "...", "role": "admin|member|viewer"}`
- Verify: Role matches what was assigned in 1.1
- File: `runtime/core/rbac.py:60` (RBACManager.get_user_role)

**Test: Admin-only route blocks non-admins**
- Setup: Create member user, get their JWT token
- Call: `POST /api/rbac/assign-role` as member user
- Expected: `403 Forbidden` with message "Admin role required"
- File: `runtime/core/rbac_middleware.py:30` (require_role dependency)

**Test: Permission hierarchy**
- Assign user roles: VIEWER (0) < MEMBER (1) < ADMIN (2)
- VIEWER user: cannot execute agents, manage users, or delete data
- MEMBER user: can execute agents, cannot manage users or billing
- ADMIN user: can do everything
- Verify via: `runtime/core/rbac.py:23` (RolePermission enum)

### 1.3 Multi-Tenant RBAC Isolation

**Test: User A's roles don't leak to User B's tenant**
- Setup: Two tenants (tenant1, tenant2), two users (userA, userB)
- Assign: userA = admin in tenant1, viewer in tenant2
- Verify: userA sees different roles depending on JWT tenant_id claim
- File: `runtime/core/rbac.py:75` (get_user_role checks both user_id AND tenant_id)

---

## 2. Stripe Integration Tests

### 2.1 Stripe Customer Creation

**Test: Create Stripe customer (sandbox)**
- Setup: Ensure `STRIPE_API_KEY` is set to sandbox test key in `.env`
- Call: `POST /api/billing/customer/create` with `{ "email": "test@example.com", "name": "Test Org" }`
- Expected: Returns `{"customer_id": "cus_...", "status": "created"}`
- Verify: Customer appears in Stripe Dashboard (test mode)
- Negative: No API key set → returns error message
- File: `runtime/core/stripe_integration.py:17` (create_customer method)

### 2.2 Payment Intent Creation

**Test: Create payment intent for $50 USD**
- Setup: Create customer first (see 2.1)
- Call: `POST /api/billing/payment-intent/create` with `{ "customer_id": "cus_...", "amount_cents": 5000, "currency": "usd", "description": "Test Plan" }`
- Expected: Returns `{ "client_secret": "pi_..._secret_...", "intent_id": "pi_...", "amount": 5000, "currency": "usd" }`
- Verify: Payment intent appears in Stripe Dashboard
- Test completion: Can create multiple intents for same customer
- File: `runtime/core/stripe_integration.py:37` (create_payment_intent)

### 2.3 Subscription Creation

**Test: Create monthly subscription**
- Setup: Must have a Stripe Product and Price ID created in dashboard (test mode)
- Call: `POST /api/billing/subscription/create` with `{ "customer_id": "cus_...", "price_id": "price_..." }`
- Expected: Returns `{ "subscription_id": "sub_...", "customer_id": "cus_...", "status": "active", "next_billing_date": "2026-05-28..." }`
- Verify: Subscription appears in Stripe Dashboard, billing date is ~30 days from now
- File: `runtime/core/stripe_integration.py:62` (create_subscription)

### 2.4 Subscription Status Check

**Test: Get subscription status**
- Setup: Create subscription (see 2.3)
- Call: `GET /api/billing/subscription/sub_...`
- Expected: Returns full subscription details including items, pricing, next billing date
- Verify: All fields match what's in Stripe Dashboard
- File: `runtime/core/stripe_integration.py:83` (get_subscription_status)

### 2.5 Subscription Cancellation

**Test: Cancel subscription at period end**
- Setup: Active subscription from 2.3
- Call: `POST /api/billing/subscription/sub_.../cancel` with `{ "at_period_end": true }`
- Expected: Returns `{"status": "cancelled"}`
- Verify: Subscription shows `cancel_at_period_end: true` in Dashboard
- Test cancellation now: Call with `"at_period_end": false` → subscription immediately cancelled
- File: `runtime/core/stripe_integration.py:105` (cancel_subscription)

### 2.6 Sandbox Mode Validation

**Test: Verify system runs in sandbox, not live**
- Check: `STRIPE_MODE` env var should be "sandbox"
- Verify: All test keys use `pk_test_*` (public) and `sk_test_*` (secret)
- Negative: Setting live key → should log warning but still work (for future migration)
- File: `runtime/core/stripe_integration.py:8` (STRIPE_MODE initialization)

---

## 3. Jaeger Distributed Tracing Tests

### 3.1 Jaeger Service Startup

**Test: Jaeger container starts successfully**
- Run: `docker-compose up jaeger`
- Expected: Container healthy within 30s
- Verify: `curl http://localhost:14268/api/traces` returns 200 with empty traces
- Verify: Jaeger UI available at `http://localhost:16686`
- File: `docker-compose.yml:45-60` (jaeger service definition)

### 3.2 FastAPI Instrumentation

**Test: FastAPI routes emit traces to Jaeger**
- Run full stack: `docker-compose up` (or `bash start.sh`)
- Make request: `curl -X GET http://localhost:8787/api/agents`
- Check Jaeger UI: Service dropdown should show "ai-employee"
- View traces: Click on "ai-employee" → should see spans for GET /api/agents
- Expected spans: http request, database query (if any)
- File: `runtime/core/tracing.py:33` (setup_fastapi_instrumentation)

### 3.3 Database Query Tracing

**Test: PostgreSQL queries are traced**
- Run: `POST /api/db/query` with a SELECT statement
- Check Jaeger: New trace should show psycopg span with query details
- Expected span tags: `db.statement`, `db.type: "sql"`, `span.kind: "client"`
- File: `runtime/core/tracing.py:43` (setup_psycopg_instrumentation)

### 3.4 Trace Sampling

**Test: Traces appear in Jaeger at correct sample rate**
- Run: 10 requests to various endpoints
- Check Jaeger traces list
- Expected: ~5-10 traces sampled (10% default sample rate)
- Verify: Trace IDs correlate with request logs
- File: `runtime/agents/problem-solver-ui/server.py:1662` (setup_tracing call)

### 3.5 Jaeger Environment Variables

**Test: Jaeger config from environment**
- Check: `JAEGER_ENABLED`, `JAEGER_HOST`, `JAEGER_PORT` can be overridden
- Default: `JAEGER_ENABLED=true`, `JAEGER_HOST=jaeger`, `JAEGER_PORT=6831`
- Override test: Set `JAEGER_HOST=localhost` → should still connect
- File: `docker-compose.yml:64-66` (env vars) and `runtime/core/tracing.py:16` (reading)

---

## 4. Authentication Route Protection Tests

### 4.1 Mutation Routes Now Require Auth

**Test: POST routes reject unauthenticated requests**

Routes protected (should all return 401):
- `POST /api/system/apply-update` (update trigger)
- `POST /api/tasks/:taskId/init` (create task)
- `POST /api/tasks/:taskId/steps/:stepId` (update step)
- `POST /api/tasks/:taskId/complete` (complete task)
- `POST /api/errors/report` (report error)

For each route:
- Call without token: `curl -X POST http://localhost:8787/api/tasks/123/init -H "Content-Type: application/json" -d '{}'`
- Expected: `401 Unauthorized` with message "Authentication required"
- Call with valid token: `curl -X POST ... -H "Authorization: Bearer $TOKEN"`
- Expected: 200 OK (or relevant business logic response)
- File: `backend/server.js` (lines 3362, 3945, 3962, 3969, 4014)

### 4.2 Open Routes (No Auth Required)

**Test: Public endpoints remain accessible**

Routes that should remain open:
- `POST /api/auth/token` — get JWT token (must be open)
- `GET /api/health` — health check
- `GET /api/status` — system status
- `GET /api/agents` — list available agents
- `GET /api/version` — version info

For each:
- Call without token: should return 200 OK
- File: `backend/server.js` (various lines)

### 4.3 Token Validation

**Test: Invalid tokens are rejected**
- Call: `POST /api/tasks/123/init -H "Authorization: Bearer invalid-token"`
- Expected: `401 Unauthorized` with message "Invalid or expired token"
- Call: `POST /api/tasks/123/init -H "Authorization: Bearer <expired-token>"`
- Expected: `401 Unauthorized`
- File: `backend/server.js:112-125` (requireAuth middleware)

---

## 5. FastAPI Route Protection

### 5.1 Python Backend Routes Require Auth

**Test: All database mutation routes protected**

Routes protected:
- `POST /api/db/insert` — insert rows
- `POST /api/db/update` — update rows
- `POST /api/db/delete` — delete rows
- `POST /api/backup/create` — create backup
- `POST /api/backup/restore/{name}` — restore backup
- `POST /api/billing/*` — all Stripe routes
- `POST /api/rbac/*` — all RBAC routes

For each:
- Call without token: `curl -X POST http://localhost:18790/api/db/insert -H "Content-Type: application/json" -d '{"table":"deals"}'`
- Expected: `403 Unauthorized` (FastAPI will return 403 for failed Depends)
- Call with valid token: should process normally
- File: `runtime/agents/problem-solver-ui/server.py:25928+` (all `Depends(require_auth)` calls)

---

## 6. Integration Tests

### 6.1 Full Auth Flow

**Test: Authenticate → execute protected route → verify permissions**
1. Call `POST /api/auth/token` with `JWT_SECRET_KEY` → get token
2. Call `POST /api/billing/customer/create` with token → create customer
3. Call `POST /api/rbac/assign-role` as non-admin → expect 403
4. Call `/api/rbac/assign-role` as admin → expect 200
5. Expected: All 4 calls behave correctly

### 6.2 RBAC + Stripe Integration

**Test: Member user cannot change billing settings, admin can**
1. Create two users: admin, member
2. Member user attempts `POST /api/billing/subscription/create` → expect 403 (no manage_billing permission)
3. Admin user calls same → expect 200 (Stripe API processes it)
4. File: Depends on route checking `require_permission("manage_billing")`

### 6.3 Jaeger Trace Correlation

**Test: Each request is traced end-to-end**
1. Assign JWT `trace_id` header to request
2. Check Jaeger: All related spans have same trace_id
3. Verify: Database query, HTTP request, business logic all in same trace
4. Check logs: `python-backend.log` has request with trace_id

### 6.4 Multi-Tenant Auth + RBAC

**Test: User roles are per-tenant**
1. Create tenant1 and tenant2
2. Assign userA as admin in tenant1, viewer in tenant2
3. Issue JWT with tenant1 claim → userA can manage tenant1
4. Issue JWT with tenant2 claim → userA is viewer, can't manage
5. Expected: Role isolation is enforced at database query layer

---

## 7. Error Cases & Edge Cases

### 7.1 Missing API Keys

**Test: Stripe disabled gracefully when key missing**
- Unset `STRIPE_API_KEY` (or set to empty string)
- Call `POST /api/billing/customer/create`
- Expected: Returns error `{"error": "Stripe API key not configured"}` (not 500)
- Logs: Should log warning "STRIPE_API_KEY not set"
- File: `runtime/core/stripe_integration.py:23` (check in create_customer)

**Test: Jaeger disabled gracefully when unavailable**
- Stop Jaeger container while app is running
- Logs: Should show warning about Jaeger connection, but app continues
- Routes: Should still work (tracing just doesn't export)
- File: `runtime/core/tracing.py:25` (error handling)

### 7.2 Concurrent Requests

**Test: Multiple concurrent authenticated requests**
- Send 10 concurrent requests to protected routes with valid tokens
- Expected: All succeed, tokens validated correctly, trace correlation maintained
- Load test tool: `ab -n 100 -c 10 -H "Authorization: Bearer $TOKEN" http://localhost:8787/api/agents`

### 7.3 Token Expiry

**Test: Expired token is rejected**
- Create token with short expiry (1 second)
- Wait 2 seconds
- Call protected route: `POST /api/tasks/123/init`
- Expected: `401 Unauthorized` "Invalid or expired token"

### 7.4 Invalid Tenant in Token

**Test: Token with invalid tenant_id**
- Create JWT with `tenant_id: "nonexistent"`
- Call route that uses tenant context
- Expected: Either 403 or 404 with appropriate message
- Should NOT return data from other tenants

---

## 8. Performance Tests

### 8.1 Auth Overhead

**Test: Measure request latency with/without auth**
- Baseline: `GET /api/agents` (public) — measure response time
- Protected: `POST /api/db/query` with token — measure response time
- Expected: Auth overhead < 10ms
- Tool: `time curl ...` or load test framework

### 8.2 Jaeger Overhead

**Test: Trace collection doesn't slow down requests significantly**
- Run same endpoint 100 times with Jaeger enabled
- Run same endpoint 100 times with Jaeger disabled (`JAEGER_ENABLED=false`)
- Expected: Overhead < 5% (negligible)

### 8.3 RBAC Lookup Performance

**Test: Role lookup latency**
- Query RBAC for 1000 different users
- Expected: Each < 5ms (database indexed on (tenant_id, user_id))
- File: `runtime/alembic/versions/002_add_rbac_tables.py:22,23` (indexes)

---

## 9. Security Tests

### 9.1 JWT Secret Validation

**Test: Invalid JWT secret rejected**
- Create token with different secret
- Call protected route
- Expected: `401 Invalid or expired token`

**Test: Weak JWT secret detected**
- Unset `JWT_SECRET_KEY` env var
- Restart server
- Expected: Server logs warning about weak secret and uses auto-generated one
- File: `backend/server.js:198-210` (_ensure_jwt_secret)

### 9.2 RBAC Role Enum Validation

**Test: Invalid role value rejected**
- Call `POST /api/rbac/assign-role` with `role: "superuser"` (invalid)
- Expected: 400 Bad Request or validation error
- Only valid roles: admin, member, viewer
- File: `runtime/core/rbac.py:7` (Role enum)

### 9.3 SQL Injection Prevention

**Test: Database queries are parameterized**
- Call `POST /api/db/query` with malicious SQL in params
- Expected: Query fails safely (not executed as code)
- Example: `sql: "SELECT * FROM users WHERE id = %s"` with `params: ["1' OR '1'='1"]`
- File: `runtime/core/database.py` (should use parameterized queries)

### 9.4 Rate Limiting on Auth Routes

**Test: Brute force attempts throttled**
- Send 10 requests to `POST /api/auth/token` in rapid succession
- Expected: After 5th request, get 429 Too Many Requests
- Recovery: Wait 60s, try again
- File: `runtime/agents/problem-solver-ui/server.py` (rate limit decorator on auth routes)

---

## 10. Documentation Tests

### 10.1 API Documentation

**Test: All new routes documented in OpenAPI**
- Start server
- Navigate to `http://localhost:8787/docs` (Swagger UI)
- Verify all `/api/billing/*`, `/api/rbac/*` routes listed
- Expected: Each route has description, request schema, response schema
- File: `runtime/agents/problem-solver-ui/server.py` (route docstrings)

### 10.2 Environment Variable Documentation

**Test: All new env vars documented**
- Check: `STRIPE_MODE`, `STRIPE_API_KEY`, `JAEGER_ENABLED`, `JAEGER_HOST`, `JAEGER_PORT`
- Expected: All mentioned in CLAUDE.md or `.env.example`
- File: `CLAUDE.md` (Environment section) and `docker-compose.yml` (defaults)

---

## Test Execution Checklist

When ready to test, execute in this order:

- [ ] Section 1: RBAC System Tests (all 3 subsections)
- [ ] Section 2: Stripe Integration Tests (all 6 subsections)
- [ ] Section 3: Jaeger Distributed Tracing Tests (all 5 subsections)
- [ ] Section 4: Authentication Route Protection Tests (all 3 subsections)
- [ ] Section 5: FastAPI Route Protection (5.1 subsection)
- [ ] Section 6: Integration Tests (all 4 subsections)
- [ ] Section 7: Error Cases & Edge Cases (all 4 subsections)
- [ ] Section 8: Performance Tests (all 3 subsections)
- [ ] Section 9: Security Tests (all 4 subsections)
- [ ] Section 10: Documentation Tests (all 2 subsections)

**Total estimated testing time:** 3-4 hours

**Success criteria:**
- All tests pass without modifications to code
- No security vulnerabilities discovered
- Performance overhead < 5% (sections 8.1, 8.2)
- All routes properly authenticated (sections 4, 5)
- Jaeger traces visible in dashboard (section 3.2-3.4)
- RBAC isolation verified (section 1.3, 6.4)
- Stripe sandbox integration working (section 2)

---

## Notes for Tester

1. **Stripe Testing:** You'll need a Stripe account with test mode enabled. Generate a test API key (sk_test_*) and set in `.env` as `STRIPE_API_KEY=sk_test_*`. Test mode allows free transactions without real charges.

2. **Jaeger Dashboard:** After starting docker-compose, Jaeger UI is at `http://localhost:16686`. Look for "ai-employee" in the service dropdown on the left side. Traces will appear ~5-10 seconds after making requests.

3. **Database State:** Tests in sections 1.1-1.3 require PostgreSQL running with migrations applied. Run `alembic upgrade head` first.

4. **JWT Tokens:** Generate test tokens via `POST /api/auth/token` with your `JWT_SECRET_KEY`. Use the returned `token` in the `Authorization: Bearer` header for protected routes.

5. **Load Testing:** For performance tests (section 8), use tools like:
   - Apache Bench: `ab -n 1000 -c 10 http://localhost:8787/api/agents`
   - `wrk`: `wrk -t4 -c100 -d30s http://localhost:8787/api/agents`

6. **Log Inspection:** Check `state/python-backend.log` for errors during testing. Look for patterns:
   - `RBAC: assigned role` (successful role assignment)
   - `Stripe: created customer` (successful customer creation)
   - `Jaeger: initialized` (tracing enabled)
   - `Auth: token validated` (auth working)

---

**Test Plan Author:** Claude Code  
**Last Updated:** 2026-04-28  
**Status:** Ready for Execution
