'use strict';

/**
 * PostgreSQL Connection Pool for Node.js Backend
 *
 * Manages a reusable pool of database connections with:
 * - Connection pooling (min/max size, idle timeout)
 * - Prepared statement caching
 * - Error handling and reconnection
 * - Prometheus metrics integration
 *
 * Usage:
 *   const pool = require('./pool');
 *   const result = await pool.query('SELECT * FROM deals WHERE tenant_id=$1', [tenantId]);
 */

const { Pool } = require('pg');
const path = require('path');

// Determine environment
const isDev = process.env.NODE_ENV !== 'production';
const isProd = process.env.NODE_ENV === 'production';

// Pool configuration from environment
const poolConfig = {
  host: process.env.DATABASE_HOST || 'localhost',
  port: parseInt(process.env.DATABASE_PORT || '5432', 10),
  database: process.env.DATABASE_NAME || 'ai_employee',
  user: process.env.DATABASE_USER || 'ai_user',
  password: process.env.DATABASE_PASSWORD,

  // Connection pool tuning
  min: parseInt(process.env.DATABASE_POOL_MIN || '2', 10),
  max: parseInt(process.env.DATABASE_POOL_MAX || '20', 10),
  idleTimeoutMillis: parseInt(process.env.DATABASE_POOL_IDLE_TIMEOUT || '30000', 10),
  connectionTimeoutMillis: 5000,

  // Prepared statement caching (pg-specific)
  statement_cache_size: 40,
  max_cached_statement_lifetime_seconds: 3600,
  max_cacheable_statement_size_bytes: 1024 * 15,  // 15KB

  // SSL configuration
  ssl: process.env.DATABASE_SSL
    ? { rejectUnauthorized: process.env.NODE_ENV === 'production' }
    : false,

  // Application identification for server logs
  application_name: 'ai-employee-backend',
};

// Create pool
const pool = new Pool(poolConfig);

// Error event handler
pool.on('error', (err, client) => {
  console.error('Unexpected error on idle client:', err);
  // In production, we let the pool recover; in dev, exit to catch issues early
  if (isProd) {
    // Alert monitoring system
    try {
      const metrics = require('../metrics');
      if (metrics && metrics.dbConnectionErrors) {
        metrics.dbConnectionErrors.inc({ pool: 'main' });
      }
    } catch (e) {
      // Metrics not available
    }
  } else {
    process.exit(-1);
  }
});

// Connection event (for logging/debugging)
pool.on('connect', (client) => {
  if (isDev) {
    console.debug('[DB] Connection acquired from pool');
  }
});

// Idle client removed event
pool.on('remove', (client) => {
  if (isDev) {
    console.debug('[DB] Idle connection removed from pool');
  }
});

/**
 * Health check: verify pool is healthy
 * @returns {Promise<{healthy: boolean, poolStats: object, lag: number|null, error: string|null}>}
 */
async function healthCheck() {
  const start = Date.now();
  const timeout = 5000;

  try {
    // Acquire a client with timeout
    const clientPromise = pool.connect();
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Health check timeout')), timeout)
    );

    const client = await Promise.race([clientPromise, timeoutPromise]);

    try {
      // Simple connectivity check
      const result = await Promise.race([
        client.query('SELECT NOW()'),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Query timeout')), timeout)
        ),
      ]);

      const elapsed = Date.now() - start;
      const poolStats = {
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount,
      };

      return {
        healthy: true,
        poolStats,
        queryTime: elapsed,
        timestamp: result.rows[0].now,
        lag: null,
        error: null,
      };
    } finally {
      client.release();
    }
  } catch (err) {
    const elapsed = Date.now() - start;
    return {
      healthy: false,
      poolStats: {
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount,
      },
      queryTime: elapsed,
      timestamp: null,
      lag: null,
      error: err.message,
    };
  }
}

/**
 * Graceful shutdown: wait for in-flight queries, close pool
 * @param {number} timeoutMs - Max time to wait for queries (default 30s)
 */
async function shutdown(timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      console.warn('Pool shutdown timeout, forcing close');
      pool.end().then(resolve).catch(reject);
    }, timeoutMs);

    pool.end().then(() => {
      clearTimeout(timeout);
      resolve();
    }).catch((err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });
}

/**
 * Get current pool statistics
 * @returns {object} Pool stats (totalCount, idleCount, waitingCount)
 */
function getStats() {
  return {
    totalCount: pool.totalCount,
    idleCount: pool.idleCount,
    waitingCount: pool.waitingCount,
    max: poolConfig.max,
    min: poolConfig.min,
  };
}

// Export pool and utilities
module.exports = pool;
module.exports.healthCheck = healthCheck;
module.exports.shutdown = shutdown;
module.exports.getStats = getStats;
module.exports.config = poolConfig;
