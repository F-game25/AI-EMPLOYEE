# PostgreSQL Migration: Quick Start Guide

**Status:** Design complete, ready for implementation  
**Total Effort:** 20-24 hours (4 phases over 3-4 days)  
**Risk Level:** MEDIUM (with rollback window)

## Three Documents to Read (In Order)

1. **DATABASE_MIGRATION_STRATEGY.md** (820 lines)
   - High-level architecture decisions
   - Connection pooling strategy
   - Migration framework (Alembic)
   - Tables to migrate & schema design
   - Environment variables
   - Health checks
   - Rollback procedures

2. **DATABASE_MIGRATION_CHECKLIST.md** (373 lines)
   - Step-by-step execution checklist
   - Phase 1: Schema setup
   - Phase 2: Dual-write integration
   - Phase 3: Cutover (30-min window)
   - Phase 4: Cleanup
   - Validation criteria

3. **DATABASE_IMPLEMENTATION_SUMMARY.md** (312 lines)
   - Overview of all deliverables
   - Architecture decisions explained
   - File locations
   - Next steps for implementer

## Code Templates Provided

| File | Purpose | Lines |
|---|---|---|
| `backend/db/pool.js` | Node.js connection pool | 189 |
| `runtime/db/pool.py` | Python async pool | 317 |
| `backend/routes/health.js` | Health check endpoints (5 endpoints) | 248 |
| `runtime/alembic/env.py` | Alembic migration engine | 95 |
| `runtime/alembic/alembic.ini` | Migration CLI config | 65 |
| `runtime/alembic/versions/001_initial_schema.py` | Schema creation | 600+ |

## 4-Phase Timeline

### Phase 1: Expand (4-6h) — LOW RISK
Create PostgreSQL schema, validate in staging
- Create tables, indexes, triggers
- Verify all constraints work
- Run health checks

### Phase 2: Contract (6-8h) — MEDIUM RISK
Dual-write mode, migrate historical data
- Enable dual-write (PostgreSQL + SQLite)
- Run data migration (JSON → PostgreSQL)
- Validate row counts match
- Run load test in staging

### Phase 3: Cutover (4-6h) — HIGH RISK (Reversible)
Switch to PostgreSQL-only (30-min window, evening)
- Backup both SQLite + PostgreSQL
- Set REQUIRE_POSTGRES=1
- Restart services
- Monitor for 30 minutes
- Ready to rollback if needed

### Phase 4: Cleanup (2-4h) — LOW RISK
Archive SQLite, remove fallback code
- Archive SQLite files to S3
- Remove fallback code from codebase
- Update documentation
- Team training

## Key Environment Variables

```bash
# Core database config
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ai_employee
DATABASE_USER=ai_user
DATABASE_PASSWORD=<secret>

# Connection pool
DATABASE_POOL_MIN=2
DATABASE_POOL_MAX=20

# Migration
ENABLE_AUTO_MIGRATIONS=1
REQUIRE_POSTGRES=1              # Phase 3+
DB_FALLBACK_SQLITE=1            # Phase 1-2 (disable Phase 3)
```

## Success Criteria

After Phase 1:
- [ ] 12 tables created (tenants, users, deals, leads, tasks, etc.)
- [ ] 30+ indexes created
- [ ] All constraints enforced
- [ ] All triggers working

After Phase 2:
- [ ] Data migrated (100% row count match)
- [ ] Dual-write operational
- [ ] Load test passes (1000 concurrent requests)

After Phase 3:
- [ ] PostgreSQL is primary, SQLite is backup
- [ ] Error rate < 0.1% for 30 minutes
- [ ] Query latency p95 < 500ms

After Phase 4:
- [ ] SQLite files archived
- [ ] Fallback code removed
- [ ] Documentation updated

## Critical Files

**Strategy & Planning:**
- `DATABASE_MIGRATION_STRATEGY.md` — Full strategy (read first)
- `DATABASE_MIGRATION_CHECKLIST.md` — Execution guide
- `DATABASE_IMPLEMENTATION_SUMMARY.md` — Overview & architecture

**Code to Implement:**
- `backend/db/pool.js` — Integrate into `backend/server.js`
- `runtime/db/pool.py` — Integrate into FastAPI startup
- `backend/routes/health.js` — Mount on `/health` route
- `runtime/alembic/` — Run migrations on startup

**Existing & Reference:**
- `docker-compose.yml` — Already has PostgreSQL service
- `runtime/db/schema.sql` — Existing schema (for reference)

## Rollback Procedure

**If Phase 3 fails:**
```bash
# Quick rollback (< 2 minutes)
export DB_FALLBACK_SQLITE=1
export REQUIRE_POSTGRES=0
docker-compose restart

# Verify
curl http://localhost:8787/health
```

**Automatic triggers:**
- > 5% errors for 5min → Auto-rollback
- Pool exhaustion (90%+) → Auto-rollback

**Manual rollback window:** 48 hours after Phase 3

## Architecture Overview

```
┌─────────────────────┐
│   Node.js Backend   │  (port 8787)
│   Python Backend    │  (port 18790)
└──────────┬──────────┘
           │ (pg.Pool)
           ↓
┌─────────────────────────────┐
│  PostgreSQL 16 (5432)       │  ← Primary (reads + writes)
│  Multi-tenancy enforced     │  ← 12 tables, 30+ indexes
│  ACID transactions          │  ← Revenue, deals consistency
│  Connection pool: 20 max    │  ← Prepared statements cached
└─────────────────────────────┘

Fallback (Phase 1-2 only):
└─ SQLite state/*.db files ← Deprecated, archived after Phase 4
```

## Pre-Implementation Checklist

Before starting Phase 1:
- [ ] Read `DATABASE_MIGRATION_STRATEGY.md` (all sections)
- [ ] Read `DATABASE_MIGRATION_CHECKLIST.md` (all phases)
- [ ] Confirm PostgreSQL 16+ available
- [ ] Verify Node.js 18+ installed
- [ ] Verify Python 3.10+ installed
- [ ] Confirm team availability for Phase 3 cutover window
- [ ] Schedule Phase 3 for evening (low traffic)

## Getting Started

**Step 1 (30 min):** Review strategy
```bash
cat DATABASE_MIGRATION_STRATEGY.md | less
```

**Step 2 (1h):** Review code
```bash
cat backend/db/pool.js
cat runtime/db/pool.py
cat backend/routes/health.js
```

**Step 3 (30 min):** Review migration
```bash
cat runtime/alembic/versions/001_initial_schema.py | head -200
```

**Step 4 (4-6h):** Execute Phase 1
- Follow checklist in `DATABASE_MIGRATION_CHECKLIST.md`
- Run Alembic migration
- Validate schema
- Test connectivity pools

## Support & Questions

**Strategy questions?**  
→ See `DATABASE_MIGRATION_STRATEGY.md` sections 1-10

**How do I execute?**  
→ See `DATABASE_MIGRATION_CHECKLIST.md` (step-by-step)

**Code integration?**  
→ See inline comments in `pool.js`, `pool.py`

**Schema details?**  
→ See `runtime/alembic/versions/001_initial_schema.py`

**Architecture reasoning?**  
→ See `DATABASE_IMPLEMENTATION_SUMMARY.md`

---

**Ready to start?** Begin with `DATABASE_MIGRATION_STRATEGY.md` section 1.  
**Questions?** All answers are in the three documents above.  
**Time needed?** 20-24 hours spread over 3-4 days (4 reversible phases).
