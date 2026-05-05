# PostgreSQL Migration Strategy
## SQLite → PostgreSQL Production Database Integration

**Status:** Design phase (ready for 20-24h implementation)  
**Priority:** P0 blocker — required to scale beyond single instance  
**Target:** Zero-downtime migration with rollback capability  

---

## EXECUTIVE SUMMARY

Current system uses SQLite (state/*.db) + JSON files for persistence, suitable only for development. Migration to PostgreSQL enables:
- Horizontal scaling (multi-instance deployments)
- ACID transactions (revenue, deals, leads consistency)
- Multi-tenancy enforcement at database layer
- Connection pooling (reduce latency)
- Read replicas (reporting workloads)

**Timeline:** Phase 1 (Schema+Pool, 4-6h) → Phase 2 (Dual-write, 6-8h) → Phase 3 (Cutover, 4-6h) → Phase 4 (Validation, 2-4h)

**Rollback:** Keep SQLite active during Phases 1-2, fall back to SQLite on error until Phase 3 complete.

---

## 1. CONNECTION STRATEGY

### 1.1 Architecture: Native PostgreSQL (Not Dual-Master)

```
┌─────────────────────┐
│   Node.js Backend   │ (port 8787)
└──────────┬──────────┘
           │ (pg.Pool)
           ↓
    ┌─────────────────────────────┐
    │ PostgreSQL Primary (5432)   │ (writes)
    └─────────────────────────────┘
           ↑        ↓
    ┌──────────┐  ┌─────────────────────┐
    │ Python   │  │ Read Replica (5433) │ (analytics, reports)
    │ Backend  │  └─────────────────────┘
    │(18790)   │
    └──────────┘
```

**Rationale:**
- SQLite WAL mode is not suitable for multi-instance (file locking issues)
- PostgreSQL provides ACID guarantees, better performance, native pooling
- Read replicas defer cost (optional for Phase 1, add in Phase 2)

### 1.2 Connection Pooling Configuration

Use `pg` npm package (Node) and `psycopg` (Python) — already in `requirements-extras.txt`.

**Node.js Pool (backend/db/pool.js):**

```javascript
const { Pool } = require('pg');

const pool = new Pool({
  host: process.env.DATABASE_HOST || 'localhost',
  port: process.env.DATABASE_PORT || 5432,
  database: process.env.DATABASE_NAME || 'ai_employee',
  user: process.env.DATABASE_USER || 'ai_user',
  password: process.env.DATABASE_PASSWORD,
  
  // Connection pool tuning
  min: 2,                    // Keep 2 idle connections ready
  max: 20,                   // Max 20 concurrent connections
  idleTimeoutMillis: 30000,  // Close idle conn after 30s
  connectionTimeoutMillis: 5000,
  
  // Prepared statements (improves perf)
  statement_cache_size: 40,
  max_cached_statement_lifetime_seconds: 3600,
  max_cacheable_statement_size_bytes: 1024*15,
  
  // SSL for prod (optional, set via DATABASE_SSL=require)
  ssl: process.env.DATABASE_SSL ? { rejectUnauthorized: false } : false,
  
  // Application name for debugging
  application_name: 'ai-employee-backend',
});

pool.on('error', (err, client) => {
  console.error('Unexpected error on idle client', err);
  process.exit(-1);
});

module.exports = pool;
```

**Python AsyncPool (runtime/db/pool.py):**

```python
import asyncpg
import os

class DatabasePool:
    _pool = None
    
    @classmethod
    async def init(cls):
        """Initialize connection pool on startup."""
        if cls._pool:
            return cls._pool
        
        cls._pool = await asyncpg.create_pool(
            host=os.getenv('DATABASE_HOST', 'localhost'),
            port=int(os.getenv('DATABASE_PORT', 5432)),
            database=os.getenv('DATABASE_NAME', 'ai_employee'),
            user=os.getenv('DATABASE_USER', 'ai_user'),
            password=os.getenv('DATABASE_PASSWORD'),
            
            # Pool tuning
            min_size=5,           # Keep 5 idle connections
            max_size=20,          # Max 20 concurrent
            max_queries=50000,    # Recycle conn after 50k queries
            max_inactive_connection_lifetime=300,  # Reuse after 5min idle
            
            # Timeouts
            timeout=10.0,         # Wait max 10s for available connection
            
            # Command tracking (debugging)
            record_class=dict,
        )
        
        return cls._pool
    
    @classmethod
    async def execute(cls, query: str, *args):
        """Execute a query and return result."""
        pool = await cls.init()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    @classmethod
    async def close(cls):
        """Close pool (on app shutdown)."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
```

**pgBouncer Option (Advanced - Phase 2):**

For multi-instance deployments (later phase), consider `pgbouncer` as connection pooler:
- Sits between app servers and PostgreSQL
- Reduces connection overhead on database
- Enables connection multiplexing
- Config: connection_pooling=transaction, pool_mode=transaction

Setup (docker-compose addition):
```yaml
pgbouncer:
  image: pgbouncer:latest
  environment:
    DATABASES_HOST: postgres
    DATABASES_PORT: 5432
    DATABASES_USER: ai_user
    DATABASES_PASSWORD: ${POSTGRES_PASSWORD}
    DATABASES_DBNAME: ai_employee
  ports:
    - "6432:6432"
  depends_on:
    - postgres
```

---

## 2. MIGRATION FRAMEWORK

### 2.1 Tool Selection: Alembic (Python-Native)

**Why Alembic over Flyway:**
- Python-native (matches runtime stack)
- Already in `requirements-extras.txt`
- Integrates with SQLAlchemy ORM
- Supports branching strategies, auto-generation

**Setup (runtime/alembic/):**

```bash
# Initialize Alembic in runtime/
alembic init --template generic alembic

# Structure:
runtime/alembic/
├── versions/                      # Migration scripts
│   ├── 001_initial_schema.py      # From runtime/db/schema.sql
│   ├── 002_add_pgvector_ext.py
│   └── ...
├── env.py                          # Alembic config (detects DATABASE_URL)
├── script.py.mako                  # Migration template
└── alembic.ini                     # Alembic CLI config
```

### 2.2 Migration Strategy: Expand-Contract Pattern

**Phase 1: Expand (4-6h)**
- Keep SQLite active, read-only
- Create PostgreSQL schema (via Alembic migration 001)
- Add new columns/tables in PostgreSQL without removing from SQLite
- Validate schema in staging

**Phase 2: Contract (6-8h)**
- Enable dual-write: writes go to BOTH SQLite and PostgreSQL
- Read preferentially from PostgreSQL (with SQLite fallback)
- Bulk migrate historical data from SQLite JSON files → PostgreSQL (idempotent)
- Validate data consistency (checksums on both sides)

**Phase 3: Cutover (4-6h)**
- Switch all reads/writes to PostgreSQL only
- Keep SQLite as backup (don't delete, just idle)
- Monitor errors for 30min, ready to revert

**Phase 4: Cleanup (2-4h)**
- Archive SQLite files to S3 / cold storage
- Remove fallback code paths (post-24h window)

### 2.3 Schema Versioning & Automatic Migrations

**On Application Startup:**

```python
# runtime/agents/problem-solver-ui/server.py (startup sequence)

async def startup_event():
    """App startup: health check, database, migrations."""
    
    # 1. Ensure PostgreSQL is healthy
    try:
        pool = await DatabasePool.init()
        async with pool.acquire() as conn:
            await conn.fetchval('SELECT 1')
        logger.info("✓ PostgreSQL healthy")
    except Exception as e:
        logger.error(f"✗ PostgreSQL unavailable: {e}")
        if os.getenv('REQUIRE_POSTGRES'):
            raise  # Fail fast in prod
        logger.warning("Falling back to SQLite (dev mode)")
    
    # 2. Run pending migrations (if ENABLE_AUTO_MIGRATIONS=1)
    if os.getenv('ENABLE_AUTO_MIGRATIONS', '1') == '1':
        from alembic.config import Config
        from alembic.command import upgrade
        
        alembic_cfg = Config("alembic.ini")
        try:
            upgrade(alembic_cfg, "head")
            logger.info("✓ Database migrations complete")
        except Exception as e:
            logger.error(f"✗ Migration failed: {e}")
            raise RuntimeError("Database schema out of sync")
    
    # 3. Initialize agents, memory, etc.
    ...
```

**Manual Migration Rollback:**

```bash
# Revert last migration (before rolling back code)
alembic downgrade -1

# Or downgrade to specific revision
alembic downgrade <revision_hash>

# View migration history
alembic history
```

---

## 3. CORE TABLES TO MIGRATE (PRIORITY ORDER)

### 3.1 Migration Dependency Graph

```
┌─────────────────────────────────┐
│ tenants, users (foundations)    │  ← No dependencies
└──────────┬──────────────────────┘
           ↓
┌─────────────────────────────────┐
│ deals, leads, tasks, team_members│  ← Depends on users
│ knowledge_entries, revenue_events│
│ audit_logs                       │
└──────────┬──────────────────────┘
           ↓
┌─────────────────────────────────┐
│ job_queue (background jobs)     │  ← Depends on agents, tasks
│ subscriptions, usage_metrics     │  ← Depends on tenants
└──────────────────────────────────┘
```

### 3.2 State File → Table Mapping

| Current Source | Target Table | Priority | Hot? | Notes |
|---|---|---|---|---|
| (auth in Node, JWT) | users | 1 | ✓✓ | Auth backend, every request |
| (JWT claims) | tenants | 1 | ✓ | Tenant context, every request |
| deals.json | deals | 2 | ✓ | CRM hot path, frequent updates |
| tasks.json | tasks | 2 | ✓ | Task routing, status updates |
| team-roster.json | team_members | 3 | ○ | Less frequent writes |
| leads.json (future) | leads | 3 | ○ | Secondary to deals |
| knowledge_store.json | knowledge_entries | 4 | ○ | Cached, rarely written |
| (audit.db exists) | audit_logs | 1 | ○ | Append-only, lower urgency |
| (forge_queue.db) | job_queue | 3 | ✓ | Async jobs, dequeue workers |

### 3.3 Transactional Consistency Requirements

| Table | TX Type | Constraint | Solution |
|---|---|---|---|
| **deals** | Multi-row | Deal moves stage, revenue updates | TX: UPDATE deals + UPDATE revenue_events atomic |
| **tasks** | Multi-row | Task status, assignee, updates | TX: UPDATE task + append audit_log |
| **team_members** | Single | Rarely conflicts | Simple UPDATE |
| **knowledge_entries** | Single | Append-only semantics | INSERT only, no lock needed |
| **subscriptions** | Single | Quota enforcement | SELECT FOR UPDATE during quota check |

**Transaction Isolation Level:** READ COMMITTED (default, fast). Upgrade to REPEATABLE READ only for quota/revenue operations.

```python
async def transfer_deal_to_stage(deal_id: str, new_stage: str, tenant_id: str):
    """Update deal stage and log revenue change (transactional)."""
    async with pool.acquire() as conn:
        async with conn.transaction():  # Implicit BEGIN...COMMIT
            await conn.execute(
                'UPDATE deals SET stage=$1, updated_at=NOW() WHERE deal_id=$2 AND tenant_id=$3',
                new_stage, deal_id, tenant_id
            )
            if new_stage == 'closed_won':
                await conn.execute(
                    'INSERT INTO revenue_events (tenant_id, type, amount, source) VALUES ($1, $2, $3, $4)',
                    tenant_id, 'deal_close', 50000, deal_id
                )
            await conn.execute(
                'INSERT INTO audit_logs (tenant_id, action, resource_type, resource_id, changes) VALUES ($1, $2, $3, $4, $5)',
                tenant_id, 'deal_stage_change', 'deal', deal_id, json.dumps({'stage': new_stage})
            )
```

### 3.4 Hot vs. Cold Access Patterns

**Hot Tables (≥10 writes/sec during peak):**
- **deals, tasks** → Index on (tenant_id, updated_at) for "recent modifications"
- **job_queue** → Index on (tenant_id, status) for dequeue polling
- **audit_logs** → Index on (tenant_id, created_at DESC) for recent activity UI

**Cold Tables (historical, analytical):**
- **knowledge_entries** → Only read/appended, rarely updated
- **subscriptions** → Updated monthly
- **revenue_events** → Written once per deal close

**Caching Strategy:**
- Hot tables: Cache in-memory (Redis optional in Phase 2)
- Cold tables: Database-only, cache indefinitely
- Audit logs: Database-only, query with time filters to limit size

---

## 4. CONNECTION STRING & ENVIRONMENT

### 4.1 Environment Variables

**Unified across Node + Python (set in start.sh or docker-compose):**

```bash
# ─── PostgreSQL ──────────────────────────────────────────────────
DATABASE_HOST=localhost              # or 'postgres' in Docker
DATABASE_PORT=5432
DATABASE_NAME=ai_employee
DATABASE_USER=ai_user
DATABASE_PASSWORD=${POSTGRES_PASSWORD}  # From ~/.ai-employee/.env or secret manager

# For read replicas (Phase 2)
DATABASE_REPLICA_HOST=localhost-replica
DATABASE_REPLICA_PORT=5432
DATABASE_REPLICA_READ_ONLY=true

# SSL (production only)
DATABASE_SSL=require                 # or 'prefer' for optional

# Migration control
ENABLE_AUTO_MIGRATIONS=1             # Automatic on startup
REQUIRE_POSTGRES=1                   # Fail if DB unavailable (prod only)

# Fallback mode (Phase 1-2 only)
DB_FALLBACK_SQLITE=1                 # Read from SQLite if PostgreSQL unavailable

# Pooling
DATABASE_POOL_MIN=2
DATABASE_POOL_MAX=20
DATABASE_POOL_IDLE_TIMEOUT=30000     # 30s (ms)
```

### 4.2 Connection String Construction

**Node.js:**
```javascript
const connStr = `postgresql://${process.env.DATABASE_USER}:${process.env.DATABASE_PASSWORD}@${process.env.DATABASE_HOST}:${process.env.DATABASE_PORT}/${process.env.DATABASE_NAME}`;
// OR use Pool constructor with individual variables (more flexible)
```

**Python:**
```python
DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
```

### 4.3 Docker Compose Integration

**docker-compose.yml (existing, verified):**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
      POSTGRES_INITDB_ARGS: >-
        -c max_connections=100
        -c shared_buffers=256MB
        -c max_wal_size=2GB
        -c checkpoint_completion_target=0.9
    volumes:
      - ./runtime/db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
      # Add migrations here
      - ./runtime/alembic:/docker-entrypoint-initdb.d/alembic:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai_user"]
      interval: 10s
      timeout: 5s
      retries: 5
```

---

## 5. HEALTH CHECK IMPLEMENTATION

### 5.1 Database Health Endpoint

**GET /health/db** — Returns detailed DB status:

```javascript
// backend/routes/health.js

app.get('/health/db', async (req, res) => {
  try {
    const pool = require('../db/pool');
    const client = await pool.connect();
    
    try {
      // 1. Simple connectivity check
      const result = await client.query('SELECT NOW()');
      
      // 2. Pool stats
      const poolStats = {
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount,
      };
      
      // 3. Replication lag (if replicas configured)
      let replicaLag = null;
      if (process.env.DATABASE_REPLICA_HOST) {
        const replicaResult = await client.query(
          `SELECT ABS(EXTRACT(EPOCH FROM (NOW() - pg_last_wal_receive_lsn()))) as lag_seconds`
        );
        replicaLag = replicaResult.rows[0].lag_seconds;
      }
      
      res.json({
        status: 'healthy',
        database: 'postgresql',
        timestamp: result.rows[0].now,
        pool: poolStats,
        replicaLag: replicaLag,
      });
    } finally {
      client.release();
    }
  } catch (err) {
    res.status(503).json({
      status: 'unhealthy',
      error: err.message,
      fallback: process.env.DB_FALLBACK_SQLITE === '1' ? 'sqlite' : 'none',
    });
  }
});
```

### 5.2 Startup Health Check

**Before serving requests:**

```javascript
// backend/server.js (startup)

async function waitForDatabase(maxRetries = 10, delayMs = 2000) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const client = await pool.connect();
      await client.query('SELECT 1');
      client.release();
      console.log('✓ Database ready');
      return true;
    } catch (err) {
      console.warn(`Database not ready (attempt ${i+1}/${maxRetries}): ${err.message}`);
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
  
  if (process.env.REQUIRE_POSTGRES === '1') {
    throw new Error('Database unavailable after retries (REQUIRE_POSTGRES=1)');
  }
  
  console.warn('⚠ Database unavailable, operating in fallback mode (SQLite)');
  return false;
}

// In server startup:
const dbReady = await waitForDatabase();
app.locals.dbReady = dbReady;
```

### 5.3 Liveness Monitoring

**Prometheus metrics endpoint (GET /metrics):**

```javascript
// backend/metrics.js

const prometheus = require('prom-client');

const dbConnectionErrors = new prometheus.Counter({
  name: 'db_connection_errors_total',
  help: 'Total database connection errors',
  labelNames: ['pool'],
});

const dbPoolIdle = new prometheus.Gauge({
  name: 'db_pool_idle_connections',
  help: 'Number of idle connections in pool',
});

const dbQueryDuration = new prometheus.Histogram({
  name: 'db_query_duration_seconds',
  help: 'Database query execution time',
  buckets: [0.001, 0.01, 0.05, 0.1, 0.5, 1.0],
});

pool.on('error', (err) => {
  dbConnectionErrors.inc({ pool: 'main' });
});

setInterval(() => {
  dbPoolIdle.set(pool.idleCount);
}, 5000);

module.exports = { dbConnectionErrors, dbPoolIdle, dbQueryDuration };
```

---

## 6. BACKWARD COMPATIBILITY & ROLLBACK

### 6.1 Dual-Write Layer (Phase 2)

Keep SQLite and PostgreSQL in sync during migration:

```python
# runtime/db/dual_write.py

class DualWriter:
    def __init__(self, pg_pool, sqlite_path):
        self.pg = pg_pool
        self.sqlite_path = sqlite_path
    
    async def write_deal(self, deal_id, deal_data, tenant_id):
        """Write to PostgreSQL, then SQLite (best-effort)."""
        
        # 1. Primary write (PostgreSQL)
        try:
            await self.pg.execute(
                '''INSERT INTO deals (deal_id, tenant_id, title, company, value, stage)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (deal_id) DO UPDATE SET
                   title=EXCLUDED.title, company=EXCLUDED.company,
                   value=EXCLUDED.value, stage=EXCLUDED.stage, updated_at=NOW()
                ''',
                deal_id, tenant_id, deal_data['title'], deal_data.get('company'),
                deal_data.get('value'), deal_data.get('stage', 'new_lead')
            )
        except Exception as e:
            logger.error(f"PostgreSQL write failed: {e}")
            raise  # Fail fast on primary
        
        # 2. Fallback write (SQLite) — don't fail if this errors
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute(
                '''REPLACE INTO deals (id, title, company, value, stage)
                   VALUES (?, ?, ?, ?, ?)''',
                (deal_id, deal_data['title'], deal_data.get('company'),
                 deal_data.get('value'), deal_data.get('stage', 'new_lead'))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SQLite fallback write failed (non-critical): {e}")
            # Don't raise — SQLite is being phased out
    
    async def read_deal(self, deal_id, tenant_id):
        """Read from PostgreSQL, fall back to SQLite if error."""
        try:
            result = await self.pg.fetchrow(
                'SELECT * FROM deals WHERE deal_id=$1 AND tenant_id=$2',
                deal_id, tenant_id
            )
            if result:
                return dict(result)
        except Exception as e:
            logger.error(f"PostgreSQL read failed: {e}")
            
            if os.getenv('DB_FALLBACK_SQLITE') != '1':
                raise
        
        # Fallback to SQLite
        logger.info(f"Falling back to SQLite for deal {deal_id}")
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM deals WHERE id=?', (deal_id,))
            cols = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(zip(cols, row))
        except Exception as e:
            logger.error(f"SQLite fallback also failed: {e}")
        
        return None
```

### 6.2 Rollback Procedure (During Phase 3)

**If cutover fails:**

```bash
#!/bin/bash
# scripts/rollback_to_sqlite.sh

set -e

echo "Rolling back to SQLite..."

# 1. Stop all services
docker-compose down

# 2. Revert database code
git checkout backend/db/pool.js
git checkout runtime/db/dual_write.py

# 3. Re-enable SQLite fallback
export DB_FALLBACK_SQLITE=1
export REQUIRE_POSTGRES=0

# 4. Restart services
docker-compose up -d

# 5. Verify health
for i in {1..30}; do
  if curl -s http://localhost:8787/health | grep -q '"status":"healthy"'; then
    echo "✓ Rollback successful"
    exit 0
  fi
  echo "Waiting for services to recover ($i/30)..."
  sleep 2
done

echo "✗ Rollback failed — manual intervention required"
exit 1
```

**Rollback Triggers:**
- > 5% query errors within 5 minutes → auto-rollback
- Replication lag > 30 seconds → warn, manual decision required
- Application startup failure → fallback to SQLite immediately

### 6.3 Zero-Downtime Migration Checklist

- [ ] **Phase 1 (4-6h):** Create PostgreSQL schema, validate in staging
  - [ ] Alembic migration 001 (initial schema)
  - [ ] Index creation, trigger functions
  - [ ] Schema test: INSERT test row, verify constraints
  
- [ ] **Phase 2 (6-8h):** Dual-write mode, historical data sync
  - [ ] Enable `DB_FALLBACK_SQLITE=1`
  - [ ] Deploy DualWriter to production
  - [ ] Run migration job: JSON files → PostgreSQL
  - [ ] Validate row counts match (SELECT COUNT(*) on both sides)
  - [ ] Spot-check data integrity (sample 10 deals, 10 tasks, verify all fields)
  
- [ ] **Phase 3 (4-6h):** Cutover (30min window, evening/low-traffic)
  - [ ] Disable `DB_FALLBACK_SQLITE=1` (read from PostgreSQL only)
  - [ ] Monitor error rate for 30min
  - [ ] Keep SQLite backups for 48h before archival
  
- [ ] **Phase 4 (2-4h):** Archive, cleanup
  - [ ] Archive SQLite files to S3
  - [ ] Remove fallback code paths from source
  - [ ] Delete state/*.db files from production

---

## 7. IMPLEMENTATION ROADMAP (20-24h)

| Phase | Tasks | Duration | Risk |
|---|---|---|---|
| **1: Schema** | 1. Run schema.sql on PostgreSQL<br/>2. Create Alembic project<br/>3. Write migration 001_initial_schema.py<br/>4. Validate indexes, constraints<br/>5. Load in staging, test inserts | 4-6h | LOW |
| **2: Dual-Write** | 1. Implement DatabasePool (Node + Python)<br/>2. Implement DualWriter class<br/>3. Migrate historical JSON → PostgreSQL<br/>4. Validate checksums<br/>5. Deploy to staging, run load test | 6-8h | MEDIUM |
| **3: Cutover** | 1. Set REQUIRE_POSTGRES=1<br/>2. Disable SQLite fallback<br/>3. Monitor for 30min<br/>4. Validate audit logs<br/>5. Rollback if needed | 4-6h | HIGH (reversible) |
| **4: Cleanup** | 1. Archive SQLite files<br/>2. Remove fallback code<br/>3. Update CLAUDE.md<br/>4. Document procedures | 2-4h | LOW |

---

## 8. KEY FILES & CHANGES

**New files to create:**
- `runtime/alembic/` — Migration project
- `backend/db/pool.js` — Node connection pool
- `runtime/db/pool.py` — Python async pool
- `runtime/db/dual_write.py` — Dual-write wrapper (Phase 2 only)
- `scripts/migrate_sqlite_to_postgres.py` — Historical data import
- `scripts/rollback_to_sqlite.sh` — Emergency rollback

**Files to modify:**
- `.env` example → add DATABASE_* variables
- `docker-compose.yml` → add POSTGRES_PASSWORD, alembic volumes
- `backend/server.js` → initialize pool, add /health/db endpoint
- `runtime/agents/problem-solver-ui/server.py` → initialize pool, run migrations at startup
- `start.sh` → export DATABASE_* variables, run migrations
- `CLAUDE.md` → document database layer

**Keep (don't delete):**
- `runtime/db/schema.sql` — Reference for schema
- `state/*.db` → Backup for 48h post-cutover

---

## 9. ENVIRONMENT VARIABLES SUMMARY

```bash
# Development (docker-compose)
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=ai_employee
DATABASE_USER=ai_user
DATABASE_PASSWORD=changeme
DATABASE_SSL=prefer
ENABLE_AUTO_MIGRATIONS=1
REQUIRE_POSTGRES=0
DB_FALLBACK_SQLITE=1

# Production
DATABASE_HOST=prod-postgres.internal
DATABASE_PORT=5432
DATABASE_NAME=ai_employee
DATABASE_USER=ai_user_prod
DATABASE_PASSWORD=<secrets-manager>
DATABASE_SSL=require
DATABASE_REPLICA_HOST=prod-replica.internal
DATABASE_REPLICA_PORT=5432
ENABLE_AUTO_MIGRATIONS=1
REQUIRE_POSTGRES=1
DB_FALLBACK_SQLITE=0
DATABASE_POOL_MIN=10
DATABASE_POOL_MAX=50
DATABASE_POOL_IDLE_TIMEOUT=30000
```

---

## 10. TESTING STRATEGY

**Unit Tests:**
- Test DualWriter: write to PG, verify SQLite fallback
- Test migrations: forward/backward on test DB
- Test pool exhaustion: confirm queue behavior at max_size

**Integration Tests:**
- Deploy to staging with full data set
- Run production load test (simulate 100 concurrent users)
- Verify no data loss, no corruption
- Test rollback: intentionally break PostgreSQL, confirm SQLite fallback

**Monitoring (Post-Deployment):**
- Alert on DB connection pool exhaustion
- Alert on replication lag > 10s
- Alert on query latency > 500ms (p95)
- Dashboard: pool utilization, query latency, error rate

---

## NEXT STEPS

1. **Approval** → Confirm this strategy with stakeholders
2. **Setup** → Initialize Alembic, create base migration
3. **Staging** → Deploy Phase 1 to staging, load test
4. **Production Phase 1** → Deploy schema changes (low-risk)
5. **Production Phase 2** → Enable dual-write, run migration (medium-risk, reversible)
6. **Production Phase 3** → Cutover to PostgreSQL (high-risk, brief window)
7. **Production Phase 4** → Cleanup, delete SQLite files after 48h

---

**Document Version:** 1.0  
**Status:** Ready for implementation  
**Estimated Total Duration:** 20-24 hours across 3-4 days  
**Rollback Point:** Any time during Phases 1-2; reversible until end of Phase 3 (30min window)
