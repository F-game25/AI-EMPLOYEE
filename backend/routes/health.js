'use strict';

/**
 * Health Check Routes
 *
 * Endpoints:
 * - GET /health              — Basic liveness check (fast)
 * - GET /health/db          — Detailed database health
 * - GET /health/system      — System-wide health (all dependencies)
 */

const express = require('express');
const os = require('os');

function createHealthRouter(pool, app) {
  const router = express.Router();

  /**
   * GET /health — Fast liveness check
   * Used by load balancers / orchestrators to route traffic
   */
  router.get('/', (req, res) => {
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
    });
  });

  /**
   * GET /health/db — Detailed database health check
   * Verifies connection pool, replication lag, query performance
   */
  router.get('/db', async (req, res) => {
    try {
      const start = Date.now();
      const timeout = 5000;

      // Acquire a client from the pool with timeout
      let client;
      try {
        client = await Promise.race([
          pool.connect(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Pool timeout')), timeout)
          ),
        ]);
      } catch (err) {
        return res.status(503).json({
          status: 'unhealthy',
          database: 'postgresql',
          error: err.message,
          poolStats: {
            totalCount: pool.totalCount,
            idleCount: pool.idleCount,
            waitingCount: pool.waitingCount,
          },
          timestamp: new Date().toISOString(),
        });
      }

      try {
        // Execute test query
        const result = await Promise.race([
          client.query('SELECT NOW(), version()'),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Query timeout')), timeout)
          ),
        ]);

        const elapsed = Date.now() - start;

        // Check for replica lag if replicas configured
        let replicaLag = null;
        if (process.env.DATABASE_REPLICA_HOST) {
          try {
            const lagResult = await client.query(
              "SELECT ABS(EXTRACT(EPOCH FROM (NOW() - pg_last_wal_receive_lsn()))) as lag_seconds"
            );
            replicaLag = parseFloat(lagResult.rows[0]?.lag_seconds || 0);
          } catch (e) {
            // Replica query failed, but primary is OK
          }
        }

        res.json({
          status: 'healthy',
          database: 'postgresql',
          queryTime: elapsed,
          poolStats: {
            totalCount: pool.totalCount,
            idleCount: pool.idleCount,
            waitingCount: pool.waitingCount,
            max: 20,  // TODO: read from pool config
          },
          replicaLag: replicaLag,  // seconds, null if no replica
          timestamp: result.rows[0].now,
          version: result.rows[0].version.split(',')[0],
        });
      } finally {
        client.release();
      }
    } catch (err) {
      res.status(503).json({
        status: 'unhealthy',
        database: 'postgresql',
        error: err.message,
        poolStats: {
          totalCount: pool.totalCount,
          idleCount: pool.idleCount,
          waitingCount: pool.waitingCount,
        },
        timestamp: new Date().toISOString(),
      });
    }
  });

  /**
   * GET /health/system — Full system health check
   * Checks: database, memory, disk, Node process
   */
  router.get('/system', async (req, res) => {
    const checks = {
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      process: {
        memory: process.memoryUsage(),
        cpuUsage: process.cpuUsage(),
      },
      system: {
        loadAverage: os.loadavg(),
        freeMemory: os.freemem(),
        totalMemory: os.totalmem(),
        cpuCount: os.cpus().length,
      },
      database: null,
      status: 'healthy',
    };

    // Database health (non-blocking — don't fail if unavailable)
    try {
      const client = await Promise.race([
        pool.connect(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('timeout')), 2000)
        ),
      ]);

      try {
        await client.query('SELECT 1');
        checks.database = {
          status: 'healthy',
          poolStats: {
            totalCount: pool.totalCount,
            idleCount: pool.idleCount,
            waitingCount: pool.waitingCount,
          },
        };
      } finally {
        client.release();
      }
    } catch (err) {
      checks.database = {
        status: 'unhealthy',
        error: err.message,
      };
      checks.status = 'degraded';  // System partially healthy
    }

    // Memory warning threshold
    const memUsagePercent =
      (checks.process.memory.heapUsed / checks.process.memory.heapTotal) * 100;
    if (memUsagePercent > 90) {
      checks.status = 'degraded';
      checks.warnings = checks.warnings || [];
      checks.warnings.push(`Heap memory usage high: ${memUsagePercent.toFixed(1)}%`);
    }

    // CPU warning threshold
    const avgLoad = checks.system.loadAverage[0];
    const cpuCount = checks.system.cpuCount;
    if (avgLoad > cpuCount * 1.5) {
      checks.status = 'degraded';
      checks.warnings = checks.warnings || [];
      checks.warnings.push(`High CPU load: ${avgLoad.toFixed(2)}`);
    }

    const statusCode = checks.status === 'healthy' ? 200 : 503;
    res.status(statusCode).json(checks);
  });

  /**
   * GET /health/ready — Readiness check (for Kubernetes)
   * Returns 200 only when app is ready to serve traffic
   */
  router.get('/ready', async (req, res) => {
    // Check if database is initialized
    if (!app.locals.dbReady) {
      return res.status(503).json({
        ready: false,
        reason: 'Database not initialized',
      });
    }

    // Quick database connectivity check
    try {
      const client = await Promise.race([
        pool.connect(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('timeout')), 1000)
        ),
      ]);

      try {
        await client.query('SELECT 1');
      } finally {
        client.release();
      }

      res.json({
        ready: true,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      res.status(503).json({
        ready: false,
        reason: 'Database unavailable',
        error: err.message,
      });
    }
  });

  /**
   * GET /health/live — Liveness check (for Kubernetes)
   * Returns 200 if process is alive, 503 if dead
   */
  router.get('/live', (req, res) => {
    res.json({
      live: true,
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
    });
  });

  return router;
}

module.exports = createHealthRouter;
