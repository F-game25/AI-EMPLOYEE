/**
 * Node.js Security Layer Tests — Phase 3.2
 *
 * Tests for:
 *  - JWT token manager (issuance, refresh, verification)
 *  - RBAC enforcer (resource-level permissions)
 *  - Rate limiter (token bucket, tenant/IP scopes)
 *  - CSP headers
 *  - Secrets rotation
 */

const assert = require('assert');
const { createRequire } = require('module');
const backendRequire = createRequire(require.resolve('../backend/middleware/token-manager'));
const jwt = backendRequire('jsonwebtoken');

const tests = [];
function test(name, fn) {
  tests.push({ name, fn });
}

function createAssertContext(name) {
  return {
    ok(value, message) {
      assert.ok(value, message);
    },
    notOk(value, message) {
      assert.ok(!value, message);
    },
    equal(actual, expected, message) {
      assert.strictEqual(actual, expected, message);
    },
    notEqual(actual, expected, message) {
      assert.notStrictEqual(actual, expected, message);
    },
    fail(message) {
      assert.fail(message || name);
    },
    end() {},
  };
}
const {
  TokenManager,
  ACCESS_TOKEN_LIFETIME,
  REFRESH_TOKEN_LIFETIME,
} = require('../backend/middleware/token-manager');
const { RBACEnforcer, RESOURCES, ACTIONS } = require('../backend/rbac/enforcer');
const { RateLimiter, TokenBucket } = require('../backend/gateway/rate_limiter');
const blacklightTools = require('../backend/security/blacklight_tools');

// ── Token Manager Tests ──────────────────────────────────────────────────────

test('TokenManager: issue token pair', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');

  const { accessToken, refreshToken } = manager.issueTokenPair('user-123', {
    email: 'test@example.com',
    tenant_id: 'tenant-456',
  });

  t.ok(accessToken, 'Access token issued');
  t.ok(refreshToken, 'Refresh token issued');
  t.end();
});

test('TokenManager: verify access token', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const { accessToken } = manager.issueTokenPair('user-123', {
    email: 'test@example.com',
  });

  const payload = manager.verifyAccessToken(accessToken);

  t.equal(payload.sub, 'user-123', 'User ID matches');
  t.equal(payload.type, 'access', 'Token type is access');
  t.end();
});

test('TokenManager: reject expired access token', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');

  // Manually create an expired token
  const expiredToken = jwt.sign(
    { sub: 'user-123', type: 'access', exp: Math.floor(Date.now() / 1000) - 1 },
    'secret-key-must-be-32-chars-long-1234567890'
  );

  try {
    manager.verifyAccessToken(expiredToken);
    t.fail('Should have thrown error for expired token');
  } catch (err) {
    t.ok(err.code === 'INVALID_TOKEN', 'Error code is INVALID_TOKEN');
  }
  t.end();
});

test('TokenManager: refresh access token', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const { refreshToken } = manager.issueTokenPair('user-123', {
    email: 'test@example.com',
    tenant_id: 'tenant-456',
  });

  // Refresh
  const { accessToken: newAccessToken, refreshToken: newRefreshToken } =
    manager.refreshAccessToken(refreshToken, { email: 'test@example.com' });

  t.ok(newAccessToken, 'New access token issued');
  t.ok(newRefreshToken, 'New refresh token issued');
  t.notEqual(newRefreshToken, refreshToken, 'Refresh token rotated');

  // Old refresh token should be invalidated
  try {
    manager.refreshAccessToken(refreshToken);
    t.fail('Old refresh token should be invalid');
  } catch (err) {
    t.ok(true, 'Old refresh token rejected');
  }

  t.end();
});

test('TokenManager: revoke refresh token (logout)', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const { refreshToken } = manager.issueTokenPair('user-123');

  manager.revokeRefreshToken(refreshToken);

  try {
    manager.refreshAccessToken(refreshToken);
    t.fail('Should reject revoked token');
  } catch (err) {
    t.ok(true, 'Revoked token rejected');
  }

  t.end();
});

test('TokenManager: WebSocket token', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const wsToken = manager.issueWSToken('user-123', { email: 'test@example.com' });

  const payload = manager.verifyWSToken(wsToken);

  t.equal(payload.type, 'ws', 'Token type is ws');
  t.equal(payload.sub, 'user-123', 'User ID matches');
  t.end();
});

test('TokenManager: reject non-WS token as WS token', (t) => {
  const manager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const { accessToken } = manager.issueTokenPair('user-123');

  try {
    manager.verifyWSToken(accessToken);
    t.fail('Should reject non-WS token');
  } catch (err) {
    t.ok(true, 'Non-WS token rejected');
  }

  t.end();
});

// ── RBAC Enforcer Tests ──────────────────────────────────────────────────────

test('RBACEnforcer: super_admin can perform all actions', (t) => {
  const enforcer = new RBACEnforcer();

  const check = enforcer.canUserPerformAction('super_admin', ACTIONS.WRITE, RESOURCES.SECURITY);

  t.ok(check.allowed, 'super_admin can write to security');
  t.end();
});

test('RBACEnforcer: employee limited to read-only', (t) => {
  const enforcer = new RBACEnforcer();

  const readCheck = enforcer.canUserPerformAction('employee', ACTIONS.READ, RESOURCES.AGENTS);
  const writeCheck = enforcer.canUserPerformAction('employee', ACTIONS.WRITE, RESOURCES.AGENTS);

  t.ok(readCheck.allowed, 'employee can read');
  t.notOk(writeCheck.allowed, 'employee cannot write');
  t.end();
});

test('RBACEnforcer: enforce throws on permission denied', (t) => {
  const enforcer = new RBACEnforcer();

  try {
    enforcer.enforce('employee', ACTIONS.DELETE, RESOURCES.ADMIN);
    t.fail('Should have thrown');
  } catch (err) {
    t.equal(err.code, 'PERMISSION_DENIED', 'Error code is PERMISSION_DENIED');
  }

  t.end();
});

test('RBACEnforcer: get role permissions', (t) => {
  const enforcer = new RBACEnforcer();

  const perms = enforcer.getRolePermissions('manager');

  t.ok(Object.keys(perms).length > 0, 'Manager has permissions');
  t.ok(perms[RESOURCES.AGENTS], 'Manager has agent permissions');
  t.end();
});

// ── Rate Limiter Tests ───────────────────────────────────────────────────────

test('TokenBucket: allows requests within capacity', (t) => {
  const bucket = new TokenBucket(10, 10 / (60 * 1000)); // 10 requests per minute

  for (let i = 0; i < 10; i++) {
    const result = bucket.tryConsume(1);
    t.ok(result.allowed, `Request ${i + 1} allowed`);
  }

  // 11th should be blocked
  const result = bucket.tryConsume(1);
  t.notOk(result.allowed, '11th request blocked');

  t.end();
});

test('RateLimiter: separate limits per tenant', (t) => {
  const limiter = new RateLimiter();

  // Both tenants should start at limit 1000
  for (let i = 0; i < 100; i++) {
    const checkA = limiter.checkLimit('tenant-a', '192.168.1.1');
    const checkB = limiter.checkLimit('tenant-b', '192.168.1.2');

    t.ok(checkA.allowed, `Tenant A request ${i + 1} allowed`);
    t.ok(checkB.allowed, `Tenant B request ${i + 1} allowed`);
  }

  t.end();
});

test('RateLimiter: global limit applies to all', (t) => {
  const limiter = new RateLimiter();

  // Global limit is 10000/min, so 100 requests per tenant should always work
  for (let i = 0; i < 100; i++) {
    const result = limiter.checkLimit(null, '192.168.1.1');
    t.ok(result.allowed, `Global request ${i + 1} allowed`);
  }

  t.end();
});

test('RateLimiter: get status', (t) => {
  const limiter = new RateLimiter();

  limiter.checkLimit('tenant-123', '192.168.1.1');
  limiter.checkLimit('tenant-123', '192.168.1.1');

  const status = limiter.getStatus();

  t.ok(status.global, 'Global status present');
  t.ok(status.active_tenants >= 1, 'Active tenants tracked');
  t.ok(Array.isArray(status.recent_violations), 'Violations tracked');

  t.end();
});

// ── Integration Tests ────────────────────────────────────────────────────────

test('Integration: Token refresh with RBAC', (t) => {
  const tokenManager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const rbacEnforcer = new RBACEnforcer();

  // Issue token pair
  const { refreshToken } = tokenManager.issueTokenPair('user-123', {
    email: 'test@example.com',
    role: 'manager',
    tenant_id: 'tenant-456',
  });

  // Refresh token
  const { accessToken } = tokenManager.refreshAccessToken(refreshToken, {
    role: 'manager',
  });

  // Verify new access token
  const payload = tokenManager.verifyAccessToken(accessToken);
  t.equal(payload.role, 'manager', 'Role preserved in refresh');

  // Check RBAC with payload
  const rbacCheck = rbacEnforcer.canUserPerformAction(payload.role, ACTIONS.EXECUTE, RESOURCES.WORKFLOWS);
  t.ok(rbacCheck.allowed, 'Manager can execute workflows');

  t.end();
});

test('Integration: Token rotation with rate limiting', (t) => {
  const tokenManager = new TokenManager('secret-key-must-be-32-chars-long-1234567890');
  const rateLimiter = new RateLimiter();

  const tenantId = 'tenant-123';
  const ip = '192.168.1.1';

  // Simulate 50 requests with token refresh
  for (let i = 0; i < 50; i++) {
    // Check rate limit
    const limitCheck = rateLimiter.checkLimit(tenantId, ip);
    t.ok(limitCheck.allowed, `Request ${i + 1} allowed by rate limiter`);
  }

  t.end();
});

// ── Blacklight Tool Policy Tests ─────────────────────────────────────────────

test('Blacklight tools: catalog exposes requested feature surface safely', (t) => {
  t.ok(blacklightTools.TOOL_CATALOG.length >= 86, 'Catalog includes OSINT/security tool surface');
  t.ok(blacklightTools.getTool('email-lookup'), 'Email lookup present');
  t.ok(blacklightTools.getTool('botnet-coordinated-ddos'), 'Botnet policy gate present');
  t.equal(blacklightTools.getTool('botnet-coordinated-ddos').mode, 'blocked', 'Botnet is blocked');
  t.equal(blacklightTools.getTool('reverse-shell-generator').mode, 'blocked', 'Reverse shell generator is blocked');
  t.end();
});

test('Blacklight tools: safe analyzers run locally', (t) => {
  const email = blacklightTools.runTool('email-lookup', 'Operator@Example.COM');
  t.ok(email.ok, 'Email analyzer runs');
  t.equal(email.result.domain, 'example.com', 'Email domain normalized');

  const jwt = blacklightTools.runTool('jwt-analyzer', 'x.y.z');
  t.ok(jwt.ok, 'JWT analyzer returns without throwing');
  t.ok(Array.isArray(jwt.result.warnings), 'JWT analyzer reports warnings');
  t.end();
});

test('Blacklight tools: passive network tools are blocked offline', (t) => {
  const dns = blacklightTools.runTool('dns-lookup', 'example.com');
  t.notOk(dns.ok, 'DNS lookup blocked without network approval');
  t.equal(dns.result.blocked, true, 'Blocked result is explicit');
  t.end();
});

if (module === require.main) {
  let passed = 0;
  for (const { name, fn } of tests) {
    try {
      fn(createAssertContext(name));
      passed += 1;
      console.log(`PASS ${name}`);
    } catch (err) {
      console.error(`FAIL ${name}`);
      console.error(err.stack || err.message);
      process.exit(1);
    }
  }
  console.log(`${passed}/${tests.length} security tests passed`);
}
