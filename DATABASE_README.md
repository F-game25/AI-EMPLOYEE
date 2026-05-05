# PostgreSQL Database Migration — Complete Design Package

## Quick Navigation

**New to this project?** Start here:
1. Read `DATABASE_QUICK_START.md` (5 min overview)
2. Read `DATABASE_MIGRATION_STRATEGY.md` (30 min deep dive)
3. Read `DATABASE_MIGRATION_CHECKLIST.md` (implementation guide)

**Ready to implement?**
- Execute phases in `DATABASE_MIGRATION_CHECKLIST.md`
- Use code templates in `backend/db/` and `runtime/db/`
- Run Alembic migrations in `runtime/alembic/`

---

## What's Included

### Documentation (4 Files, 2000+ Lines)

| File | Purpose | Length | Read Time |
|---|---|---|---|
| **DATABASE_QUICK_START.md** | Navigation guide, quick reference | 200 lines | 5 min |
| **DATABASE_MIGRATION_STRATEGY.md** | Full architecture & strategy | 820 lines | 30 min |
| **DATABASE_MIGRATION_CHECKLIST.md** | Step-by-step execution | 373 lines | 20 min |
| **DATABASE_IMPLEMENTATION_SUMMARY.md** | Deliverables & decisions | 312 lines | 15 min |

### Code Templates (6 Files, 1500+ Lines)

| File | Purpose | Type | Status |
|---|---|---|---|
| `backend/db/pool.js` | Node.js connection pool | Template | Ready |
| `runtime/db/pool.py` | Python async pool | Template | Ready |
| `backend/routes/health.js` | Health check endpoints | Template | Ready |
| `runtime/alembic/env.py` | Alembic configuration | Template | Ready |
| `runtime/alembic/alembic.ini` | CLI settings | Template | Ready |
| `runtime/alembic/versions/001_initial_schema.py` | Database schema | Migration | Ready |

---

## The Challenge (P0 Blocker)

Current system uses SQLite + JSON files for persistence:
- ✗ Not suitable for multi-instance deployments (file locking)
- ✗ No ACID guarantees (revenue/deal consistency issues)
- ✗ Volatile on container restarts
- ✗ No horizontal scaling possible
- ✗ Cannot support production workloads

**Required Solution:** Migrate to PostgreSQL with zero downtime

---

## The Solution: 4-Phase Expand-Contract Pattern

```
PHASE 1: EXPAND (4-6h, LOW RISK)
─────────────────────────────────
Create PostgreSQL schema → Validate in staging
✓ Low risk (no production change)
✓ Rollback: just delete PostgreSQL tables

PHASE 2: CONTRACT (6-8h, MEDIUM RISK)
───────────────────────────────────────
Enable dual-write → Migrate data → Validate
✓ Fallback: disable dual-write, revert to SQLite
✓ Validation checkpoint: row counts match?

PHASE 3: CUTOVER (4-6h, HIGH RISK - 30 MIN WINDOW)
────────────────────────────────────────────────
Switch to PostgreSQL only → Monitor 30 min
✓ Reversible: 48h rollback window available
✓ Auto-rollback on errors

PHASE 4: CLEANUP (2-4h, LOW RISK)
──────────────────────────────────
Archive SQLite → Remove fallback → Update docs
✓ Low risk (post-stabilization)
✓ Can pause for weeks if needed
```

**Total Time:** 20-24 hours across 3-4 days  
**Downtime:** 0 seconds (true zero-downtime migration)  
**Rollback Window:** 48 hours after Phase 3

---

## Architecture Highlights

### Connection Pooling

**Node.js (backend):**
- Pool size: 2-20 (configurable)
- Prepared statement caching (40 statements)
- Health check endpoint
- Graceful shutdown support

**Python (runtime):**
- Async/await compatible
- Pool size: 5-20 (configurable)
- Query timeout protection
- Transaction wrapper for ACID operations

### Database Schema

**Tables:** 12 core tables
- Tenants (multi-tenancy foundation)
- Users, Team Members (personnel)
- Deals, Leads (CRM pipeline)
- Tasks (operations)
- Knowledge Entries (content)
- Revenue Events (billing)
- Audit Logs (compliance)
- Job Queue (async jobs)
- Subscriptions, Usage Metrics (billing)

**Features:**
- Multi-tenancy enforced at schema layer (every table has tenant_id)
- 30+ indexes (tenant_id, status, created_at, etc.)
- Foreign key constraints with CASCADE delete
- CHECK constraints (enum validation)
- UNIQUE constraints (data integrity)
- 7 triggers (auto-update timestamps)

### Health Checks

5 endpoints for different use cases:
- `GET /health` — Simple liveness (< 10ms)
- `GET /health/db` — Database connectivity + pool stats
- `GET /health/system` — Full system health
- `GET /health/ready` — Readiness probe (Kubernetes)
- `GET /health/live` — Liveness probe (Kubernetes)

### Migrations (Alembic)

Version control for schema changes:
- Automatic detection of DATABASE_URL from environment
- Forward/backward migrations (upgrade/downgrade)
- Auto-run on startup (configurable)
- Support for future schema improvements

---

## Environment Variables

```bash
# Core database config
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ai_employee
DATABASE_USER=ai_user
DATABASE_PASSWORD=<secret>

# Connection pool sizes
DATABASE_POOL_MIN=2             # Keep idle connections ready
DATABASE_POOL_MAX=20            # Max concurrent connections
DATABASE_POOL_IDLE_TIMEOUT=30000  # 30 seconds

# SSL (production only)
DATABASE_SSL=require            # or 'prefer' for optional

# Migration behavior
ENABLE_AUTO_MIGRATIONS=1        # Run migrations on startup
REQUIRE_POSTGRES=1              # Fail if DB unavailable (Phase 3+)

# Fallback mode (Phase 1-2 only)
DB_FALLBACK_SQLITE=1            # Read from SQLite if PostgreSQL unavailable
```

---

## Success Metrics

| Metric | Target | Verified By |
|---|---|---|
| **Data Consistency** | 100% match SQLite↔PostgreSQL | Row count verification |
| **Zero Downtime** | 0 seconds interruption | Health checks during cutover |
| **Query Latency** | p95 < 500ms | Prometheus metrics |
| **Connection Pool** | < 80% utilization peak | Pool stats endpoint |
| **Error Rate** | < 0.1% post-cutover | Request logs |
| **Replication Lag** | < 10 seconds | PostgreSQL WAL position |

---

## Rollback Procedures

### Quick Rollback (< 2 minutes)
```bash
export DB_FALLBACK_SQLITE=1
export REQUIRE_POSTGRES=0
docker-compose restart ai-employee
curl http://localhost:8787/health
```

### Automatic Rollback Triggers
- > 5% query errors for 5 minutes → ROLLBACK
- Connection pool exhaustion (90%+) → ROLLBACK
- Manual triggers available in Phase 3

### Rollback Window
- Phase 1: Immediate (delete PostgreSQL)
- Phase 2: Immediate (disable dual-write)
- Phase 3: 48 hours (keep SQLite backup)
- Phase 4+: 0 (SQLite deleted)

---

## File Structure

```
/home/lf/AI-EMPLOYEE/
├── DATABASE_README.md                    ← You are here
├── DATABASE_QUICK_START.md               ← Start here
├── DATABASE_MIGRATION_STRATEGY.md        ← Full strategy
├── DATABASE_MIGRATION_CHECKLIST.md       ← Execute this
├── DATABASE_IMPLEMENTATION_SUMMARY.md    ← Architecture details
│
├── backend/db/
│   └── pool.js                          ← Node connection pool
│
├── backend/routes/
│   └── health.js                        ← Health endpoints
│
├── runtime/db/
│   ├── schema.sql                       ← Original schema (reference)
│   └── pool.py                          ← Python async pool
│
├── runtime/alembic/
│   ├── env.py                           ← Migration engine
│   ├── alembic.ini                      ← CLI config
│   └── versions/
│       └── 001_initial_schema.py        ← Schema creation
│
└── docker-compose.yml                   ← Already has PostgreSQL
```

---

## Reading Order (Recommended)

### For Project Managers
1. `DATABASE_QUICK_START.md` (5 min) — Timeline & risk
2. `DATABASE_IMPLEMENTATION_SUMMARY.md` (15 min) — Deliverables

### For Engineers (Implementation)
1. `DATABASE_QUICK_START.md` (5 min) — Overview
2. `DATABASE_MIGRATION_STRATEGY.md` (30 min) — Architecture
3. `DATABASE_MIGRATION_CHECKLIST.md` (20 min) — Execute phases
4. Code templates (30 min) — Understand implementation

### For Database Administrators
1. `DATABASE_MIGRATION_STRATEGY.md` sections 1-6 (30 min)
2. `runtime/alembic/versions/001_initial_schema.py` (15 min)
3. `DATABASE_MIGRATION_CHECKLIST.md` sections 1-3 (20 min)

### For DevOps
1. `DATABASE_MIGRATION_STRATEGY.md` section 4 (10 min) — Env vars
2. `DATABASE_MIGRATION_CHECKLIST.md` section "Phase 3" (15 min) — Cutover
3. `backend/routes/health.js` (5 min) — Health probes

---

## Key Decisions Made

### Why PostgreSQL?
- ACID transactions (critical for revenue/deals)
- Native UUID support (multi-tenancy)
- JSONB data type (flexible schema)
- Connection pooling built-in
- Read replicas (future scaling)
- Excellent documentation

### Why Expand-Contract Pattern?
- Minimal downtime (not zero-downtime until cutover)
- Easy rollback (SQLite remains active)
- Data validation checkpoints
- Reversible at each phase
- Proven pattern at scale (Shopify, GitHub, etc.)

### Why Alembic?
- Python-native (matches codebase)
- SQLAlchemy integration (future ORM)
- Already in requirements
- Version control for schemas
- Automatic migration generation

### Why These Pools?
- Node `pg` package: mature, stable, widely used
- Python `asyncpg`: fastest async driver, native connection pool
- Sizes (2-20 dev, 5-50 prod): standard for OLTP workloads

---

## Common Questions

**Q: How long does Phase 3 cutover take?**
A: The actual switch (code deploy) takes 2-3 minutes. Monitoring takes 30 minutes. Rollback stays available for 48 hours.

**Q: What if something breaks during Phase 3?**
A: Fallback to SQLite instantly. We keep both systems running for 48 hours, so you can switch back without losing data.

**Q: Do we need to change application code?**
A: Yes, but minimally. Pool APIs are almost identical. We provide all templates.

**Q: Can we do partial migration?**
A: Not recommended. All-or-nothing approach is cleaner. But you can pause after Phase 2 indefinitely.

**Q: What about read replicas?**
A: Added in Phase 2+ as advanced option. Not required for Phase 1.

**Q: Who should execute this?**
A: Ideally a database engineer or DevOps person familiar with PostgreSQL and Node/Python.

---

## Next Steps

1. **Today (30 min):** Read `DATABASE_QUICK_START.md`
2. **Tomorrow (1h):** Read `DATABASE_MIGRATION_STRATEGY.md` sections 1-6
3. **Day 2 (4-6h):** Execute Phase 1 (schema setup)
4. **Day 2 (6-8h):** Execute Phase 2 (dual-write, staging)
5. **Day 3 (Evening, 4-6h):** Execute Phase 3 (cutover)
6. **Day 4 (2-4h):** Execute Phase 4 (cleanup)

---

## Support

- **Questions about strategy?** See `DATABASE_MIGRATION_STRATEGY.md` sections 1-6
- **How to implement?** See `DATABASE_MIGRATION_CHECKLIST.md` (step-by-step)
- **Code help?** See comments in `pool.js`, `pool.py`, migration files
- **Architecture?** See `DATABASE_IMPLEMENTATION_SUMMARY.md`

---

**Status:** Design complete ✓  
**Code:** Ready for integration ✓  
**Documentation:** Complete ✓  
**Estimated Execution:** 20-24 hours over 3-4 days  
**Risk Level:** MEDIUM (with full rollback capability)

**Ready to begin? Start with `DATABASE_QUICK_START.md`**
