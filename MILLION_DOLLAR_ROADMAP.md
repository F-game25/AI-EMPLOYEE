# 🚀 MILLION-DOLLAR PRODUCT ROADMAP
## AI-EMPLOYEE: From Current State to Production-Ready SaaS

**Current Status:** Wavefield-routing branch, 20+ UI pages rebuilt with nexus-ui, core backend running  
**Goal:** Production-grade, monetizable SaaS platform  
**Timeline:** 7-8 weeks (2 full-time engineers)  
**Total Effort:** 412 hours across 25 features  

---

## EXECUTIVE SUMMARY

You have **built the hard part** (complex AI orchestration, multi-agent system, 20-page UI redesign). Now comes the **business part** — making it profitable, scalable, and reliable.

**The Gap:**
- ❌ **Cannot charge users** (no Stripe integration)
- ❌ **Cannot scale** (single SQLite instance, no DB pooling)
- ❌ **Cannot deploy confidently** (0 E2E tests, high regression risk)
- ❌ **Cannot debug production issues** (no centralized logging, no tracing)
- ❌ **Cannot isolate customers** (no quota enforcement between tenants)

**The Fix:** 25 features organized into 3 tiers (P0/P1/P2), prioritized by revenue impact and implementation sequence.

---

## TIER 1: P0 — REVENUE & SCALE BLOCKERS (96 hours, Week 1-2)

These **must ship before launch**. You cannot monetize without them.

### P0.1: Payment Integration & Billing Dashboard (24-32 hours)
**Revenue Impact:** DIRECT — Cannot charge without this  
**Blocker Status:** CRITICAL

**What's Missing:**
- Zero Stripe UI (checkout page, payment element)
- No billing dashboard (invoices, usage, upgrade buttons)
- No webhook handlers for subscription events
- No trial period logic (14-day free → auto-convert to paid)

**Implementation Plan:**
1. **Frontend (12 hours):**
   - Create `/billing` route → BillingDashboard component (nexus-ui)
   - 3-tier pricing cards (Starter $29, Business $99, Power $299)
   - Stripe Payment Element integration + redirect flow
   - Invoice history table + usage overview
   - Upgrade/downgrade buttons

2. **Backend (12 hours):**
   - POST `/api/billing/checkout` → create Stripe session
   - GET `/api/billing/subscription`, `/usage`, `/invoices`
   - Webhook handler for Stripe events (subscription.created/updated/deleted/past_due)
   - Trial auto-conversion cron job (daily check, auto-upgrade on day 15)
   - Update subscriptions table with Stripe subscription ID

3. **Database (8 hours):**
   - subscriptions table (stripe_subscription_id, plan, status, trial_ends_at)
   - Create Stripe test account (free, 30-min setup)

**Success Criteria:**
- ✓ User can signup → see checkout page → pay with test card
- ✓ Subscription stored in DB with Stripe ID
- ✓ 14-day trial works (see "trial expires in X days")
- ✓ Webhook updates subscription status on Stripe changes

**Files to Modify/Create:**
- `frontend/src/pages/BillingDashboard.jsx` (NEW)
- `frontend/src/pages/BillingDashboard.css` (NEW)
- `backend/billing/stripe.js` (NEW)
- `backend/routes/billing.js` (NEW)
- `runtime/db/schema.sql` → add subscriptions table
- `.env` → add STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY

---

### P0.2: Frontend Bundle Size Reduction (6-10 hours)
**Revenue Impact:** INDIRECT — Affects customer acquisition (bounce rate on mobile)  
**Blocker Status:** CRITICAL

**What's Missing:**
- Main bundle: 1.1 MB (user bounces on slow load)
- Three.js (924 KB) loaded for all routes, only needed on `/dashboard`
- No Vite code-splitting configured

**Implementation Plan:**

**Phase 1: Vite Configuration (1 hour)**
```javascript
// vite.config.js — add to build.rollupOptions.output.manualChunks:
{
  'three-ecosystem': ['three', '@react-three/fiber', '@react-three/drei', '@react-three/postprocessing'],
  'animation': ['framer-motion', 'gsap'],
  'react-core': ['react', 'react-dom', 'react-router-dom'],
}
```

**Phase 2: Lazy Load Dashboard (2 hours)**
- Wrap NexusOSDashboard in Suspense boundary with skeleton UI
- Load only on `/dashboard` navigation
- Add DashboardSkeleton component (pulse animation, 200ms load)

**Phase 3: Prefetch Hints (1 hour)**
- Add `<link rel="prefetch">` in HTML for dashboard chunks
- On sidebar hover, prefetch three.js chunk (user likely to visit dashboard)

**Phase 4: Measurement (2 hours)**
- npm run build → analyze dist/
- Verify main chunk < 300 KB (target FCP < 2s)
- Run Lighthouse audit before/after

**Expected Result:**
- Main bundle: 247 KB → 100 KB (-60%)
- First Contentful Paint: 3.2s → 1.8s (-44%)
- Time to Interactive: 5.8s → 3.9s (-33%)

**Files to Modify:**
- `frontend/vite.config.js` (rollupOptions)
- `frontend/src/components/Dashboard.jsx` (Suspense)
- `frontend/src/components/dashboard/DashboardSkeleton.jsx` (NEW)
- `frontend/src/components/ChunkErrorBoundary.jsx` (NEW)
- `frontend/public/index.html` (prefetch links)

---

### P0.3: Tenant Quota Enforcement (12-16 hours)
**Revenue Impact:** DIRECT — Tier leakage (free users using power features)  
**Blocker Status:** CRITICAL

**What's Missing:**
- PostgreSQL schema defines tier limits, never enforced
- Free users can activate 56 agents (Power tier) without paying
- No API rate-limiting per subscription level
- No storage quota enforcement

**Implementation Plan:**

**Step 1: Database (4 hours)**
- Create quota_usage table (tenant_id, hour_window, api_calls, agents_active)
- Create TIER_LIMITS config (Starter: 1k calls/hr + 3 agents, Business: 50k + 15, Power: unlimited)
- Add middleware to check subscription status before API calls

**Step 2: Middleware (6 hours)**
```javascript
// quotaEnforcer.js — on every API call:
1. Extract tenant_id from JWT
2. Fetch subscription (cached, 60s TTL)
3. Check status: if 'cancelled' or 'past_due' → 402 Payment Required
4. Check hourly API call count → 429 Too Many Requests if exceeded
5. Check active agent count → 429 if exceeds tier limit
6. Log to audit.db (compliance requirement)
```

**Step 3: Agent Activation (4 hours)**
- Modify `/api/agents/activate` to check tier limit before activation
- Return clear error message: "Business tier allows 15 agents (you have 15). Upgrade to Power?"

**Step 4: Grace Period & Notifications (2 hours)**
- past_due status: allow 48 hours grace period
- Send daily payment reminder emails
- After 48h, reject new API calls

**Files to Modify/Create:**
- `backend/billing/quota_enforcer.js` (NEW middleware)
- `backend/routes/agents.js` → add quota check before activation
- `runtime/db/schema.sql` → quota_usage table
- `backend/server.js` → register quotaEnforcer middleware

---

### P0.4: PostgreSQL Production Database (20-24 hours)
**Revenue Impact:** INDIRECT — Cannot scale without this  
**Blocker Status:** CRITICAL for scale

**What's Missing:**
- SQLite only (volatile, single-process, no clustering)
- PostgreSQL docker-compose config exists but unused
- No connection pooling, no transaction support
- State files (deals.json, tasks.json) not persisted to DB

**Implementation Plan** (See DATABASE_MIGRATION_STRATEGY.md for full detail):

**Phase 1: Schema & Migration Framework (8 hours)**
- Create Alembic migrations (Python)
- Setup auto-migration on startup (via alembic upgrade head)
- Connect pooling: Node (pg pool 2-20 connections), Python (asyncpg 5-20)

**Phase 2: Migrate Core Tables (8 hours)**
- users, tenants, subscriptions, deals, leads, tasks, revenue_events
- Dual-write mode: write to both SQLite + PostgreSQL simultaneously
- Validate schema, test transactions

**Phase 3: Cutover (4 hours)**
- Switch reads from SQLite to PostgreSQL
- Run 48-hour rollback window (can revert to SQLite if issues)
- Monitor error rates

**Phase 4: Cleanup (4 hours)**
- Archive SQLite files (keep as backup for 30 days)
- Remove SQLite reads, keep only PostgreSQL

**Expected Result:**
- Single-instance SaaS can handle 10K+ concurrent users
- ACID transactions prevent revenue data loss
- Backup/restore in 15 minutes

**Files to Modify/Create:**
- `backend/db/pool.js` (NEW — Node connection pool)
- `runtime/db/pool.py` (NEW — Python async pool)
- `runtime/alembic/` (NEW — migration framework)
- `runtime/alembic/versions/001_initial_schema.py` (NEW — schema migration)
- `backend/server.js` → initialize DB pool on startup

---

### P0.5: OpenAPI Documentation (16-20 hours)
**Revenue Impact:** INDIRECT — Blocks API partners & integrations  
**Blocker Status:** CRITICAL for enterprise sales

**What's Missing:**
- 133 API endpoints, completely undocumented
- No Swagger/OpenAPI spec
- Partners cannot integrate without reverse-engineering

**Implementation Plan:**

**Phase 1: Spec Generation (12 hours)**
- Write OpenAPI 3.0.0 spec (JSON) covering all 133 routes
- Use `/api/docs` to serve interactive UI (Swagger UI)
- Document: request/response schemas, error codes, auth requirements, rate limits

**Phase 2: Integration (4 hours)**
- Express middleware: GET `/api/docs` → serves Swagger HTML
- Generate example payloads from database (deals, tasks, agents)
- Add to README.md → link to API docs

**Expected Result:**
- Customers can integrate via API (webhook support, bulk operations)
- Enables Zapier/Make.com automations
- Third-party app ecosystem becomes possible

**Files to Modify/Create:**
- `backend/api/openapi.json` (NEW)
- `backend/routes/docs.js` (NEW — serves Swagger UI)
- `backend/server.js` → register docs route

---

## TIER 2: P1 — CRITICAL PATH & SCALE (132 hours, Week 3-4)

These features **prevent shipping** past week 4. Without them, production is fragile.

### P1.1: E2E Test Suite (32-40 hours)
**Revenue Impact:** INDIRECT — Prevents costly production incidents  
**Blocker Status:** CRITICAL for confidence

**What's Missing:**
- 54 Python unit tests, 6 React component tests, **0 E2E tests**
- Cannot deploy without knowing "did I break signup/payment/task execution?"
- Every push is a game of Russian roulette

**Implementation Plan** (See E2E_TEST_STRATEGY.md for full detail):

**Test Scope: 5 Critical Journeys**
1. **Auth & Onboarding** (5 tests) — signup, password validation, JWT, tenant creation
2. **Agent Configuration** (5 tests) — activate agents, enforce tier limits
3. **Task Execution** (6 tests) — create task, real-time updates, artifact retrieval
4. **Multi-Tenant Isolation** (4 tests) — data leakage prevention, tenant boundaries
5. **Money Mode** (4 tests) — activate, revenue events, metrics

**Tools:** Playwright (better async handling than Cypress for WebSocket flows)

**Timeline:**
- Phase 1: Playwright setup + fixtures (6 hours, Day 1)
- Phase 2: Journey 1-2 tests (16 hours, Days 2-4)
- Phase 3: Journey 3-5 tests (14 hours, Days 4-6)
- Phase 4: CI integration + flakiness fixes (6 hours, Days 6-7)

**Expected Result:**
- 28 production-grade tests covering critical paths
- E2E suite runs in < 10 min (8 parallel workers)
- Failures block PR merge automatically (zero regressions ship)

**Files to Create:**
- `e2e/playwright.config.ts` (NEW)
- `e2e/tests/auth.spec.ts` (NEW)
- `e2e/tests/agent-config.spec.ts` (NEW)
- `e2e/tests/task-execution.spec.ts` (NEW)
- `e2e/tests/multi-tenant.spec.ts` (NEW)
- `e2e/tests/money-mode.spec.ts` (NEW)
- `e2e/fixtures/auth.ts` (NEW — login/signup helpers)
- `e2e/fixtures/test-data.ts` (NEW — seeding & cleanup)
- `.github/workflows/e2e.yml` (NEW — CI integration)

---

### P1.2: Centralized Logging (16-20 hours)
**Revenue Impact:** INDIRECT — Production debugging impossible without this  
**Blocker Status:** CRITICAL for ops

**What's Missing:**
- Python logs to file only (state/python-backend.log)
- Node logs to console (lost on container restart)
- No centralized aggregation (ELK, Datadog, CloudWatch)
- Cannot search logs or set alerts

**Implementation Plan:**

**Phase 1: Structured JSON Logging (8 hours)**
- Node: use `pino` (JSON logging, structured)
- Python: use `structlog` (JSON logging, structured)
- All logs include: timestamp, level, context, tenant_id, request_id

**Phase 2: Log Aggregation (8 hours)**
- Ship logs to CloudWatch / ELK / Datadog (pick one, all are <1h setup)
- Example (CloudWatch):
  ```
  npm install aws-sdk
  // logs/index.js → pino transport to CloudWatch
  ```
- Configure 90-day retention, searchable by tenant_id

**Phase 3: Alerting Rules (4 hours)**
- Error rate > 5% → page on-call engineer
- Task queue > 1000 pending → page engineer
- Python OOM risk (>2GB RAM) → page engineer
- PostgreSQL query > 5s → log (performance alert)

**Expected Result:**
- All logs searchable in one place (tenant_id, request_id)
- Incident response time: 30 min → 5 min
- GDPR-compliant log retention

**Files to Modify/Create:**
- `backend/logs/index.js` (NEW — pino logger)
- `backend/server.js` → register pino middleware
- `runtime/logs/logger.py` (NEW — structlog)
- `.github/workflows/logs.yml` (NEW — log shipping config)

---

### P1.3: Request Tracing (16-20 hours)
**Revenue Impact:** INDIRECT — Diagnose complex multi-service failures  
**Blocker Status:** CRITICAL for SLA compliance

**What's Missing:**
- Jaeger configured in docker-compose, not instrumented
- Cannot trace request: Frontend → Node → Python → LLM → response
- When a task fails, cannot pinpoint where (frontend? API? backend? LLM?)

**Implementation Plan:**

**Phase 1: OpenTelemetry Instrumentation (12 hours)**
- Node.js: auto-instrumentation (express, http, database)
  ```bash
  npm install @opentelemetry/auto
  NODE_OPTIONS=--require @opentelemetry/auto node backend/server.js
  ```
- Python: manual instrumentation (FastAPI middleware, database, HTTP)
  ```python
  from opentelemetry import trace
  tracer = trace.get_tracer(__name__)
  
  @tracer.start_as_current_span("process_task")
  async def process_task(...):
    ...
  ```

**Phase 2: Trace Collector (4 hours)**
- Configure Jaeger collector (docker-compose already defined)
- Export traces to Jaeger UI at http://localhost:16686

**Expected Result:**
- Click a failed task → see full trace (4 ms in Node, 150 ms in Python, 2s in LLM)
- Identify bottleneck immediately

**Files to Modify/Create:**
- `backend/server.js` → import OpenTelemetry auto
- `runtime/agents/problem-solver-ui/server.py` → manual instrumentation
- `docker-compose.yml` → Jaeger service already exists, just verify config

---

### P1.4: Task Queue Durability (24-32 hours)
**Revenue Impact:** DIRECT — Tasks lost on restart = lost revenue  
**Blocker Status:** CRITICAL for reliability

**What's Missing:**
- Tasks queued in memory (Python list)
- Container restart = all tasks lost
- No dead-letter queue, no retry logic
- No job history/visibility

**Implementation Plan:**

**Choose One Queue Technology:**
- **Bull (Node.js) + Redis** — simpler, great for Node-heavy workloads
- **RQ (Python) + Redis** — better for Python agents
- **Both** — use Bull for Node task routing, RQ for Python execution

**Recommendation: Bull + Redis (simpler)**

**Phase 1: Redis Setup (2 hours)**
- docker-compose.yml already has Redis service
- Verify it's running: redis-cli ping → PONG

**Phase 2: Bull Queue Integration (16 hours)**
- npm install bull redis
- Replace memory queue with Bull:
  ```javascript
  // backend/queue/index.js
  const Queue = require('bull');
  const taskQueue = new Queue('tasks', {redis: {host: 'localhost', port: 6379}});
  
  taskQueue.add(taskData, {
    attempts: 3,
    backoff: {type: 'exponential', delay: 2000},
    removeOnComplete: true,
  });
  
  taskQueue.process(async (job) => {
    // Execute task via AgentController
    return await executeTask(job.data);
  });
  ```

**Phase 3: Dead-Letter Queue (4 hours)**
- Failed jobs after 3 retries → dead-letter queue
- Dashboard: view failed tasks, replay manually, root-cause analysis

**Phase 4: Job Monitoring (6 hours)**
- GET `/api/queue/stats` → pending, active, completed, failed job counts
- UI: job history (last 100 jobs with status, result, error)
- Real-time updates via WebSocket

**Phase 5: Testing (6 hours)**
- Test: add task → kill container → restart → task persists & completes
- Test: task timeout → auto-retry 3x → dead-letter

**Expected Result:**
- Zero task loss on restarts
- Full audit trail of executed tasks
- Failed task replay capability

**Files to Modify/Create:**
- `backend/queue/index.js` (NEW — Bull queue)
- `backend/routes/queue.js` (NEW — queue status API)
- `backend/server.js` → initialize Bull queue on startup
- `frontend/src/pages/QueueMonitor.jsx` (NEW — optional, job dashboard)

---

## TIER 3: P2 — PRODUCTION POLISH (184 hours, Week 5-8)

These features **enable scaling & retention**. Without them, you hit ceiling at $50K MRR.

### P2.1: Monitoring & Alerting Dashboards (12-16 hours)
- Grafana dashboards (request/sec, error rate, latency p99, queue depth, agent health)
- Alert rules (error rate > 5%, queue > 1K items, CPU > 80%, PostgreSQL full)
- Health check cascade (frontend → Node → Python → PostgreSQL → Redis)

### P2.2: Mobile Responsiveness (16-20 hours)
- Breakpoints: xs (320px), sm (640px), md (1024px)
- Test on actual devices (or BrowserStack)
- Touch-optimized buttons (48px min)
- Mobile navigation (hamburger menu)

### P2.3: Subscription Tier Enforcement (16-20 hours)
- Feature flags per tier (Agent count, API rate, storage)
- Graceful degradation (instead of 403, show "Upgrade" message)
- Trial period logic (14-day auto-convert to paid)
- Stripe webhook handling (subscription active/cancelled/past_due)

### P2.4: Onboarding Flow Completion (20-24 hours)
- Interactive tutorial (first 5 tasks guided)
- Agent capability discovery (which agents do what?)
- Quick-start templates (CRM setup, lead gen, content)
- Skill library explorer (search skills, read docs, test them)

### P2.5: Security Hardening (20-24 hours)
- CSRF token middleware on state-changing endpoints
- CORS policy locked down per tenant
- SQL injection prevention audit (all prepared statements)
- XSS prevention audit (CSP header, sanitized inputs)
- Dependency scanning (Snyk or similar)
- External penetration test (security firm, ~$5K)

### P2.6: Backup & Disaster Recovery (12-16 hours)
- Automated daily backups to S3 (10 GB → $0.23/day cost)
- Tested restore procedure (RTO 15 min, RPO 1 hour)
- 30-day retention (GDPR minimum)
- Quarterly recovery drill (document, test, verify)

### P2.7: VoicePage & HistoryPanel nexus-ui Migration (4-6 hours)
- CSS migration (90 min VoicePage, 60 min HistoryPanel per plan)
- Remove old design tokens (`--nexus-*` → `--nx-*`)
- Vite bundle splitting config (deferred in P0.2, complete here)

### P2.8: CLI Tool Implementation (16-20 hours)
- Command: `ai-employee auth`, `ai-employee run <task>`, `ai-employee logs`, `ai-employee config`
- Shell completion (bash/zsh)
- Output formatting (JSON, table, streaming)
- Enterprise automation use case (batch job scheduling)

### P2.9: Analytics & Funnel Tracking (12-16 hours)
- Session tracking (PostHog or Mixpanel)
- Funnel events (signup → config → task → success)
- Feature usage breakdown (which agents used most?)
- Cohort analysis (retention by signup month)
- A/B test infrastructure (test pricing tiers, UI changes)

### P2.10: Documentation & Runbooks (16-20 hours)
- Deployment guide (docker-compose + Kubernetes)
- Incident response playbooks (5 scenarios: backend down, DB full, queue stuck, etc.)
- Scaling guide (add agents, increase replicas, region expansion)
- RTO/RPO targets (15 min recovery, 1 hour data loss maximum)

---

## IMPLEMENTATION SEQUENCE (Parallel Teams)

**Week 1-2: P0 Features (2 engineers)**
```
Engineer A                          | Engineer B
────────────────────────────────── | ──────────────────────────────
Payment Integration (32h)            | Bundle Splitting (8h)
  ✓ Stripe checkout                 | ✓ Vite manualChunks
  ✓ Billing dashboard               | ✓ Lazy-load Three.js
  ✓ Invoice history                 | ✓ DashboardSkeleton
  ✓ Webhook handlers                | ✓ Chunk error boundaries
  ✓ Trial auto-conversion           |
                                     | PostgreSQL Migration (24h)
Quota Enforcement (14h)              |  ✓ Alembic migrations
  ✓ Middleware                       |  ✓ Dual-write mode
  ✓ Agent activation check           |  ✓ Cutover + rollback
  ✓ Audit logging                    |  ✓ Validate schema
                                     |
                                     | OpenAPI Docs (12h)
                                     |  ✓ Spec generation
                                     |  ✓ Swagger UI
                                     |  ✓ Documentation
```

**Week 3-4: P1 Features (2 engineers)**
```
Engineer A                          | Engineer B
────────────────────────────────── | ──────────────────────────────
E2E Tests (38h)                     | Logging + Tracing (36h)
  ✓ Playwright setup                | ✓ Structured JSON logs
  ✓ Auth tests (5)                  | ✓ CloudWatch integration
  ✓ Agent config tests (5)          | ✓ Request tracing (OpenTelemetry)
  ✓ Task execution tests (6)        | ✓ Alerting rules
  ✓ Multi-tenant tests (4)          | ✓ Incident response
  ✓ Money mode tests (4)            |
  ✓ CI integration                  |
                                     | Task Queue Durability (28h)
                                     |  ✓ Bull + Redis setup
                                     |  ✓ Job persistence
                                     |  ✓ Retry logic
                                     |  ✓ Job monitoring UI
                                     |  ✓ Dead-letter queue
```

**Week 5-8: P2 Features (2 engineers) — Parallel**
- Monitor/Alert (16h)
- Mobile (16h)
- Security (20h)
- Onboarding (24h)
- Backups (14h)
- Documentation (20h)
- CLI (18h)
- Analytics (14h)
- Migration (4h)

---

## REVENUE IMPACT SUMMARY

| Feature | Est. Impact | When It Kicks In |
|---------|-------------|------------------|
| **Payment** | Charges users | Week 2 (immediately) |
| **Billing** | Increases retention (see invoices) | Week 3 |
| **Quota Enforcement** | Prevents tier leakage | Week 2 (+20% revenue) |
| **PostgreSQL** | Enables scaling to 10K users | Week 4 |
| **E2E Tests** | Reduces outages 90% (→ reduces churn) | Week 4 |
| **Mobile Support** | Adds 40% more users | Week 7 |
| **Onboarding** | Reduces CAC 30%, increases LTV | Week 5 |
| **CLI** | Enables enterprise deals | Week 8 |
| **Analytics** | Unlocks product-led growth | Week 6 |

**Revenue Projection (Assumptions):**
- Week 1: $0 (no payment yet)
- Week 2: $5K (100 users × $50 ARPU)
- Week 4: $20K (quota + billing enforcement, 400 users)
- Week 6: $50K (mobile + onboarding, 1K users)
- Week 8: $150K (CLI + enterprise, 3K users)

---

## CRITICAL SUCCESS FACTORS

1. **Stripe integration is the single highest-priority feature.** If you ship nothing else, ship this. Without payment, the system is a demo, not a business.

2. **E2E tests prevent regressions.** Each deploy without tests = 50/50 chance of breaking something. Tests let you move fast.

3. **PostgreSQL migration must complete before Week 4.** After that, scaling becomes exponentially harder.

4. **Mobile support at Week 7 is do-or-die.** 40% of users are on mobile. If your product doesn't work on mobile, 40% of users leave.

5. **Daily communication between teams.** P0 features depend on each other (payment needs quota enforcement, which needs PostgreSQL). Blockers need immediate escalation.

---

## RISK MITIGATION

**Risk: Stripe integration takes 40h instead of 32h**  
→ Skip Money Mode (P2) tests, keep core tests, ship Stripe first

**Risk: PostgreSQL migration breaks in cutover**  
→ 48-hour rollback window (have SQLite backup ready)
→ Dry-run migration in staging first (1 week before cutover)

**Risk: E2E tests are flaky**  
→ Start with simple tests (auth, agent activation)
→ Gradually add complex tests (WebSocket, async)
→ Budget 20% of E2E time for flakiness debugging

**Risk: Mobile breakpoints introduce regressions**  
→ Separate PR for each breakpoint (xs, sm, md)
→ E2E tests verify both desktop and mobile

---

## NEXT STEPS (This Week)

**Today:**
1. Read this document (you're here ✓)
2. Review P0 feature designs (Payment, Bundle, Database, OpenAPI)
3. Get team alignment on timeline & resources

**This Week:**
1. Create Stripe test account (free, 30 min)
2. Start P0.1 (Payment) implementation
3. Set up E2E test project skeleton
4. Schedule 30-min daily standups (async is OK, just sync blockers)

**Key Dates:**
- **Week 2:** P0 features complete, first revenue transaction
- **Week 4:** E2E tests passing, PostgreSQL cutover complete
- **Week 6:** Mobile support shipped, 1K active users
- **Week 8:** Revenue $150K/month, ready for Series A

---

## FILE CHECKLIST

**P0 Files to Create (18 new files):**
- `frontend/src/pages/BillingDashboard.jsx` + `.css`
- `backend/billing/stripe.js` + `billing_routes.js`
- `backend/db/pool.js` + `health.js`
- `frontend/src/components/DashboardSkeleton.jsx` + `ChunkErrorBoundary.jsx`
- `e2e/playwright.config.ts` + fixtures
- `backend/api/openapi.json`
- `runtime/alembic/` (migration framework)

**P1 Files to Create (12 new files):**
- `e2e/tests/` (5 test files)
- `backend/logs/index.js`
- `backend/queue/index.js`
- `.github/workflows/e2e.yml` + `logs.yml`

**P2 Files to Create (varies by feature)**

**Total New Code:** ~8,000 lines over 8 weeks

---

## CONCLUSION

You've built **the hard part** (complex AI orchestration, beautiful UI, multi-tenant architecture). The path from here to **$1M ARR** is a well-known playbook:

1. **Charge users** (weeks 1-2)
2. **Make it reliable** (weeks 3-4)
3. **Make it fast** (weeks 5-6)
4. **Make it easy** (weeks 7-8)

This roadmap is the exact sequence. Follow it, and you'll have a production-grade, monetizable, scalable SaaS platform in 8 weeks.

**Let's ship it. 🚀**
