'use strict';

/**
 * Advanced Rate Limiting — Token bucket with tenant + IP scopes
 *
 * Rate limiting tiers:
 *  - Global: 10,000 req/min (burst window 1 min)
 *  - Per-tenant: 1,000 req/min
 *  - Per-IP: 100 req/min (for anonymous requests)
 *
 * Implements sliding window (not fixed windows) for smooth rate limiting
 */

const LOG = '[RateLimiter]';

// Rate limit configurations (requests per minute)
const LIMITS = {
  GLOBAL: 10000,
  PER_TENANT: 1000,
  PER_IP: 100,
};

// Bucket window (milliseconds)
const WINDOW_MS = 60 * 1000; // 1 minute

class TokenBucket {
  constructor(capacity, refillRatePerMs) {
    this.capacity = capacity;
    this.refillRatePerMs = refillRatePerMs; // tokens per millisecond
    this.tokens = capacity;
    this.lastRefillTime = Date.now();
  }

  /**
   * Try to consume N tokens
   * Returns: { allowed: bool, remaining: int, resetAt: timestamp }
   */
  tryConsume(amount = 1) {
    const now = Date.now();
    const timeSinceRefill = now - this.lastRefillTime;

    // Refill bucket based on time elapsed
    const tokensToAdd = timeSinceRefill * this.refillRatePerMs;
    this.tokens = Math.min(this.capacity, this.tokens + tokensToAdd);
    this.lastRefillTime = now;

    if (this.tokens >= amount) {
      this.tokens -= amount;
      return {
        allowed: true,
        remaining: Math.floor(this.tokens),
        resetAt: null,
      };
    }

    // Calculate when bucket will have enough tokens
    const tokensNeeded = amount - this.tokens;
    const msNeeded = tokensNeeded / this.refillRatePerMs;
    const resetAt = new Date(now + msNeeded);

    return {
      allowed: false,
      remaining: Math.floor(this.tokens),
      resetAt,
    };
  }

  /**
   * Get bucket status without consuming
   */
  getStatus() {
    const now = Date.now();
    const timeSinceRefill = now - this.lastRefillTime;
    const currentTokens = Math.min(
      this.capacity,
      this.tokens + timeSinceRefill * this.refillRatePerMs
    );

    return {
      tokens: Math.floor(currentTokens),
      capacity: this.capacity,
      fillPercentage: (currentTokens / this.capacity) * 100,
    };
  }
}

class RateLimiter {
  constructor(options = {}) {
    this.globalBucket = new TokenBucket(
      LIMITS.GLOBAL,
      LIMITS.GLOBAL / WINDOW_MS
    );
    this.tenantBuckets = new Map(); // tenant_id -> TokenBucket
    this.ipBuckets = new Map(); // ip -> TokenBucket
    this.violations = []; // Array of violation events for logging
    this.maxViolationHistory = options.maxViolationHistory || 1000;
  }

  /**
   * Check if request should be allowed
   * Returns: { allowed: bool, reason: string, retryAfter?: int }
   */
  checkLimit(tenant_id = null, ip = 'unknown') {
    const now = Date.now();

    // 1. Check global limit
    const globalCheck = this.globalBucket.tryConsume(1);
    if (!globalCheck.allowed) {
      this._recordViolation('global', null, ip, 'global_limit_exceeded');
      return {
        allowed: false,
        reason: 'Global rate limit exceeded',
        retryAfter: globalCheck.resetAt,
      };
    }

    // 2. Check tenant limit (if tenant_id provided)
    if (tenant_id) {
      if (!this.tenantBuckets.has(tenant_id)) {
        this.tenantBuckets.set(
          tenant_id,
          new TokenBucket(LIMITS.PER_TENANT, LIMITS.PER_TENANT / WINDOW_MS)
        );
      }
      const tenantBucket = this.tenantBuckets.get(tenant_id);
      const tenantCheck = tenantBucket.tryConsume(1);

      if (!tenantCheck.allowed) {
        this._recordViolation('tenant', tenant_id, ip, 'tenant_limit_exceeded');
        return {
          allowed: false,
          reason: `Tenant rate limit exceeded (${LIMITS.PER_TENANT}/min)`,
          retryAfter: tenantCheck.resetAt,
        };
      }
    }

    // 3. Check IP limit (for anonymous or low-tier requests)
    if (!this.ipBuckets.has(ip)) {
      this.ipBuckets.set(
        ip,
        new TokenBucket(LIMITS.PER_IP, LIMITS.PER_IP / WINDOW_MS)
      );
    }
    const ipBucket = this.ipBuckets.get(ip);
    const ipCheck = ipBucket.tryConsume(1);

    if (!ipCheck.allowed) {
      this._recordViolation('ip', tenant_id, ip, 'ip_limit_exceeded');
      return {
        allowed: false,
        reason: `IP rate limit exceeded (${LIMITS.PER_IP}/min)`,
        retryAfter: ipCheck.resetAt,
      };
    }

    return { allowed: true, reason: 'Request allowed' };
  }

  /**
   * Get current status of all buckets
   */
  getStatus() {
    return {
      global: this.globalBucket.getStatus(),
      active_tenants: this.tenantBuckets.size,
      active_ips: this.ipBuckets.size,
      violations_recorded: this.violations.length,
      recent_violations: this.violations.slice(0, 20),
    };
  }

  /**
   * Reset rate limit for tenant (admin operation)
   */
  resetTenantLimit(tenant_id) {
    this.tenantBuckets.delete(tenant_id);
  }

  /**
   * Get rate limit info for tenant
   */
  getTenantStatus(tenant_id) {
    const bucket = this.tenantBuckets.get(tenant_id);
    if (!bucket) {
      return { configured: false };
    }
    return bucket.getStatus();
  }

  _recordViolation(limitType, tenant_id, ip, reason) {
    const violation = {
      timestamp: new Date().toISOString(),
      type: limitType,
      tenant_id: tenant_id || 'none',
      ip,
      reason,
    };
    this.violations.unshift(violation);
    if (this.violations.length > this.maxViolationHistory) {
      this.violations.pop();
    }
  }
}

/**
 * Express middleware for rate limiting
 * Usage: app.use(rateLimitMiddleware(limiter))
 */
function rateLimitMiddleware(limiter) {
  return (req, res, next) => {
    const tenantId = req.tenant?.tenantId || null;
    const ip = req.ip || req.socket?.remoteAddress || 'unknown';
    const requestId = req.gatewayRequestId || `rl-${Date.now()}`;

    const check = limiter.checkLimit(tenantId, ip);

    if (!check.allowed) {
      res.status(429).json({
        error: check.reason,
        request_id: requestId,
        retry_after: check.retryAfter ? Math.ceil((check.retryAfter - Date.now()) / 1000) : null,
      });

      if (check.retryAfter) {
        res.setHeader('Retry-After', Math.ceil((check.retryAfter - Date.now()) / 1000));
      }

      return;
    }

    // Attach rate limit status headers
    const tenantStatus = tenantId ? limiter.getTenantStatus(tenantId) : null;
    if (tenantStatus && tenantStatus.tokens !== undefined) {
      res.setHeader('X-RateLimit-Limit', LIMITS.PER_TENANT);
      res.setHeader('X-RateLimit-Remaining', tenantStatus.tokens);
      res.setHeader('X-RateLimit-Reset', Math.ceil(Date.now() / 1000) + 60);
    }

    next();
  };
}

module.exports = {
  RateLimiter,
  rateLimitMiddleware,
  TokenBucket,
  LIMITS,
};
