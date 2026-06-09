# PostgreSQL Migration Implementation Checklist

## Quick Reference
- **Strategy Document:** `DATABASE_MIGRATION_STRATEGY.md`
- **Connection Pool (Node):** `backend/db/pool.js`
- **Connection Pool (Python):** `runtime/db/pool.py`
- **Health Checks:** `backend/routes/health.js`
- **Alembic Migrations:** `runtime/alembic/`
  - `env.py` — Migration engine config
  - `alembic.ini` — CLI settings
  - `versions/001_initial_schema.py` — Initial schema creation

## Phase 1: Schema Setup (4-6 hours)

### Environment & Docker Preparation
- [ ] Update `.env` template with DATABASE_* variables
  ```
  DATABASE_HOST=postgres
  DATABASE_PORT=5432
  DATABASE_NAME=ai_employee
  DATABASE_USER=ai_user
  DATABASE_PASSWORD=<secure>
  ```

- [ ] Verify `docker-compose.yml` has postgres service configured
  - [ ] Volume mount for `schema.sql`
  - [ ] Healthcheck enabled
  - [ ] Max connections = 100

- [ ] Start PostgreSQL container
  ```bash
  docker-compose up postgres
  ```

### Schema Migration
- [ ] Verify Alembic structure exists
  ```bash
  ls -la runtime/alembic/
  # Should have: env.py, alembic.ini, versions/001_initial_schema.py
  ```

- [ ] Install Alembic and dependencies
  ```bash
  pip install alembic sqlalchemy psycopg[binary]
  ```

- [ ] Run initial migration in staging
  ```bash
  cd runtime && alembic upgrade head
  ```

- [ ] Verify tables were created
  ```bash
  psql -U ai_user -d ai_employee -c "\dt"
  # Should list: tenants, users, deals, leads, tasks, etc.
  ```

- [ ] Verify indexes
  ```bash
  psql -U ai_user -d ai_employee -c "\di"
  # Should have 30+ indexes on tenant_id, status, created_at, etc.
  ```

- [ ] Verify triggers
  ```bash
  psql -U ai_user -d ai_employee -c "SELECT tgname FROM pg_trigger;"
  # Should list: update_*_updated_at triggers
  ```

### Connection Pool Testing
- [ ] Install Node modules (pg package)
  ```bash
  npm install pg --save
  ```

- [ ] Test Node connection pool
  ```bash
  cd backend && node -e "
    const pool = require('./db/pool');
    pool.connect().then(client => {
      client.query('SELECT 1').then(res => {
        console.log('✓ Node pool OK');
        client.release();
        pool.end();
      });
    });
  "
  ```

- [ ] Install Python dependencies
  ```bash
  pip install asyncpg asyncio
  ```

- [ ] Test Python connection pool
  ```bash
  python3 -c "
    import asyncio
    from runtime.db.pool import DatabasePool
    async def test():
      await DatabasePool.init()
      result = await DatabasePool.fetch_val('SELECT 1')
      print('✓ Python pool OK')
      await DatabasePool.close()
    asyncio.run(test())
  "
  ```

### Schema Validation
- [ ] Insert test data (tenants, users, deals)
  ```bash
  psql -U ai_user -d ai_employee << 'SQL'
  INSERT INTO tenants (org_name) VALUES ('Test Org') RETURNING tenant_id;
  INSERT INTO users (tenant_id, username, email, password_hash) 
    VALUES ('<tenant_id>', 'testuser', 'test@example.com', 'hash');
  INSERT INTO deals (tenant_id, title, company, value, stage, owner_id)
    VALUES ('<tenant_id>', 'Test Deal', 'ACME Corp', 50000, 'new_lead', '<user_id>');
  SQL
  ```

- [ ] Verify constraints work
  ```bash
  # Try invalid stage — should fail
  psql -U ai_user -d ai_employee -c "
    INSERT INTO deals (tenant_id, title, stage) 
    VALUES ((SELECT tenant_id FROM tenants LIMIT 1), 'Bad', 'invalid_stage');
  "
  # Should return: constraint violation
  ```

- [ ] Verify FK cascade delete
  ```bash
  psql -U ai_user -d ai_employee -c "
    DELETE FROM tenants WHERE org_name='Test Org';
    SELECT COUNT(*) FROM deals;  -- Should be 0 if cascade worked
  "
  ```

## Phase 2: Dual-Write Integration (6-8 hours)

### Code Integration
- [ ] Integrate Node connection pool into `backend/server.js`
  ```javascript
  const pool = require('./db/pool');
  app.locals.pool = pool;
  ```

- [ ] Integrate Python connection pool into `runtime/agents/problem-solver-ui/server.py`
  ```python
  from db.pool import DatabasePool
  
  @app.on_event('startup')
  async def startup():
      await DatabasePool.init()
  
  @app.on_event('shutdown')
  async def shutdown():
      await DatabasePool.close()
  ```

- [ ] Add health check endpoint to Node backend
  ```javascript
  const createHealthRouter = require('./routes/health');
  const healthRouter = createHealthRouter(pool, app);
  app.use('/health', healthRouter);
  ```

- [ ] Verify health endpoint
  ```bash
  curl http://localhost:8787/health
  curl http://localhost:8787/health/db
  curl http://localhost:8787/health/system
  ```

### Dual-Write Layer (Phase 2 Optional)
- [ ] Create `runtime/db/dual_write.py` (if implementing)
  - [ ] `write_deal()` — write to PostgreSQL, then SQLite
  - [ ] `read_deal()` — read from PostgreSQL, fallback to SQLite
  - [ ] Error handling and logging

- [ ] Enable dual-write mode in environment
  ```bash
  export DB_FALLBACK_SQLITE=1
  export DATABASE_POOL_MIN=2
  export DATABASE_POOL_MAX=20
  ```

- [ ] Deploy to staging and run load test
  ```bash
  ab -n 1000 -c 10 http://localhost:8787/health/db
  # Should complete in < 5s, no errors
  ```

### Historical Data Migration
- [ ] Create migration script: `scripts/migrate_sqlite_to_postgres.py`
  - [ ] Read all JSON state files
  - [ ] Transform to PostgreSQL schema
  - [ ] Insert with tenant_id isolation
  - [ ] Verify row counts match

- [ ] Run migration in staging
  ```bash
  python3 scripts/migrate_sqlite_to_postgres.py
  ```

- [ ] Validate data integrity
  ```bash
  # Check row counts match
  sqlite3 state/deals.json "SELECT COUNT(*) FROM deals;"
  psql -U ai_user -d ai_employee -c "SELECT COUNT(*) FROM deals;"
  
  # Spot-check sample records match
  ```

## Phase 3: Cutover (4-6 hours, Evening/Low-Traffic Window)

### Pre-Cutover
- [ ] Take full database backup
  ```bash
  pg_dump -U ai_user ai_employee > /backup/ai_employee_pre_cutover.sql
  ```

- [ ] Take SQLite backup
  ```bash
  cp state/deals.json state/deals.json.backup
  cp state/tasks.json state/tasks.json.backup
  # ... etc for all JSON files
  ```

- [ ] Final data consistency check
  ```bash
  # Verify row counts match between SQLite and PostgreSQL
  # Verify sample records match
  ```

### Execute Cutover
- [ ] Set environment variables for cutover
  ```bash
  export REQUIRE_POSTGRES=1          # Fail if PostgreSQL unavailable
  export DB_FALLBACK_SQLITE=0        # Don't fall back to SQLite
  export ENABLE_AUTO_MIGRATIONS=1    # Auto-run migrations
  ```

- [ ] Restart services
  ```bash
  docker-compose restart ai-employee
  docker-compose restart python-backend
  ```

- [ ] Monitor for 30 minutes
  ```bash
  # Watch error logs
  docker-compose logs -f ai-employee | grep -i error
  
  # Check metrics
  curl http://localhost:8787/metrics | grep -E "error|pool"
  
  # Verify health checks pass
  watch -n 2 'curl -s http://localhost:8787/health/db | jq'
  ```

### Rollback Procedure (If Needed)
- [ ] If critical errors occur within 30 minutes:
  ```bash
  # Run rollback script
  bash scripts/rollback_to_sqlite.sh
  ```

  - [ ] Verify SQLite health
  - [ ] Confirm data consistency
  - [ ] Notify team

## Phase 4: Cleanup (2-4 hours)

### After 48-Hour Observation Period
- [ ] Archive SQLite files to S3 / cold storage
  ```bash
  aws s3 cp state/deals.json s3://backup-bucket/sqlite-archive/
  # ... etc for all JSON files
  ```

- [ ] Remove fallback code paths
  - [ ] Remove `DB_FALLBACK_SQLITE` env var handling
  - [ ] Remove dual_write.py if created
  - [ ] Clean up conditional imports

- [ ] Update documentation
  - [ ] Update `CLAUDE.md` database section
  - [ ] Remove SQLite references from setup guide
  - [ ] Add PostgreSQL connection string examples

- [ ] Delete SQLite files from production
  ```bash
  rm state/*.db state/*.db-shm state/*.db-wal
  ```

## Validation Checklist

### After Phase 1 (Schema)
- [ ] All tables created (12 tables total)
- [ ] All indexes created (30+ indexes)
- [ ] All triggers created (7 update_*_updated_at triggers)
- [ ] Foreign key constraints enforced
- [ ] CHECK constraints enforced
- [ ] UNIQUE constraints enforced

### After Phase 2 (Dual-Write)
- [ ] Node pool: min=2, max=20, idle=30s
- [ ] Python pool: min=5, max=20, max_queries=50k
- [ ] Dual-write: writes to both PostgreSQL + SQLite
- [ ] Dual-read: reads from PostgreSQL, fallback to SQLite
- [ ] Historical data migrated (deal count, task count match)
- [ ] Checksums validate (no data loss)

### After Phase 3 (Cutover)
- [ ] PostgreSQL is primary, SQLite is backup only
- [ ] Error rate < 0.1% for 30 minutes post-cutover
- [ ] Query latency: p95 < 500ms
- [ ] Pool utilization: < 80% during peak
- [ ] Replication lag (if replicas): < 10s

### After Phase 4 (Cleanup)
- [ ] SQLite files archived to cold storage
- [ ] Fallback code removed from codebase
- [ ] Documentation updated
- [ ] CLAUDE.md updated
- [ ] No references to SQLite in active code

## Monitoring & Alerts

### Key Metrics to Watch
```
db_connection_pool_utilization       (target: < 80%)
db_query_latency_p95                 (target: < 500ms)
db_connection_errors_total           (alert if > 0)
db_replication_lag_seconds           (alert if > 10s)
db_transaction_rollback_rate         (target: < 0.1%)
```

### Alert Rules
- [ ] Connection pool exhaustion: 90% utilization → Alert
- [ ] Query timeout: > 1 error/min → Alert
- [ ] Replication lag: > 30s → Alert
- [ ] Database unavailable: > 5 consecutive health check failures → Rollback

## Rollback Scenarios

| Scenario | Action | Trigger |
|---|---|---|
| Schema broken | Rollback migration | Manual decision |
| Data corruption | Restore from backup | Within 48h |
| Performance regression | Revert to SQLite | > 5% error rate for 5min |
| Scaling issue | Add replicas | Monitor during Phase 3 |

## Success Criteria

- [x] All tests passing (unit, integration, load test)
- [x] Zero-downtime migration (no traffic interruption)
- [x] Data consistency (row counts, checksums match)
- [x] Performance maintained (latency same or better)
- [x] Monitoring in place (metrics, alerts, dashboards)
- [x] Documentation updated
- [x] Team trained on new database layer

---

**Total Estimated Time:** 20-24 hours  
**Phases:** 1-2 (staging), then Phase 3 (production, 30-min window)  
**Rollback Window:** 48 hours after Phase 3  
**Execution Contacts:**
- Database: `DATABASE_MIGRATION_STRATEGY.md`
- Code: `backend/db/pool.js`, `runtime/db/pool.py`
- Migrations: `runtime/alembic/versions/`
