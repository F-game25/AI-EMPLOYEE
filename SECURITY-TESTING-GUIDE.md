# Phase 3.2 Security Testing Guide

## Pre-Deployment Testing

### 1. Token Manager Tests

Run token manager unit tests:
```bash
cd /home/lf/AI-EMPLOYEE
npm test tests/test_security_node.js -- TokenManager
```

**Manual verification:**

```bash
# Test 1: Token issuance and verification
curl -X POST http://localhost:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"securepass"}'

# Expect: { access_token: "...", refresh_token: "...", expires_in: 900 }

# Test 2: Access token verification
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8787/api/profile

# Expect: 200 OK with user profile

# Test 3: Token refresh
curl -X POST http://localhost:8787/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refreshToken":"<refresh_token>"}'

# Expect: New access_token and refresh_token

# Test 4: Old refresh token invalidated
curl -X POST http://localhost:8787/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refreshToken":"<old_refresh_token>"}'

# Expect: 401 Unauthorized (token revoked after rotation)

# Test 5: Expired token rejected
# (Wait 15 minutes or manually create expired token)
curl -H "Authorization: Bearer <expired_token>" \
  http://localhost:8787/api/profile

# Expect: 401 Unauthorized
```

### 2. RBAC Enforcer Tests

Run RBAC tests:
```bash
npm test tests/test_security_node.js -- RBACEnforcer
```

**Manual verification:**

```bash
# Test 1: Employee cannot write to agents
curl -X POST http://localhost:8787/api/agents \
  -H "Authorization: Bearer <employee_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"test"}'

# Expect: 403 Forbidden (PERMISSION_DENIED)

# Test 2: Manager can execute workflows
curl -X POST http://localhost:8787/api/workflows/execute \
  -H "Authorization: Bearer <manager_token>" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"wf-123"}'

# Expect: 200 OK (execution started)

# Test 3: Org admin can configure agents
curl -X PATCH http://localhost:8787/api/agents/config \
  -H "Authorization: Bearer <org_admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"config":"new_config"}'

# Expect: 200 OK (updated)
```

### 3. Rate Limiting Tests

Run rate limiter tests:
```bash
npm test tests/test_security_node.js -- RateLimiter
```

**Manual verification:**

```bash
# Test 1: Normal request succeeds
curl http://localhost:8787/api/status
# Expect: 200 OK, X-RateLimit-Remaining header

# Test 2: Exceeding per-IP limit triggers 429
for i in {1..150}; do
  curl -s http://localhost:8787/api/status > /dev/null
done

# Last few requests should return:
# HTTP 429 Too Many Requests
# Retry-After: <seconds>

# Test 3: Rate limit resets after time window
sleep 61  # Wait > 1 minute

curl http://localhost:8787/api/status
# Expect: 200 OK (limit reset)

# Test 4: Each tenant has independent limit
curl -H "Authorization: Bearer <tenant_a_token>" \
  http://localhost:8787/api/status

curl -H "Authorization: Bearer <tenant_b_token>" \
  http://localhost:8787/api/status

# Both should succeed even under load (separate limits)
```

### 4. Signed Events Tests

Run signed events tests:
```bash
cd /home/lf/AI-EMPLOYEE
python3 -m pytest tests/test_security_phase3.py::TestSignedEvents -v
```

**Manual verification:**

```python
# Test in Python shell
from runtime.core.signed_events import EventSigner

signer = EventSigner('secret-key-32-chars-or-longer!')

# Test 1: Sign and verify event
event = signer.sign_event('task_completed', {'task_id': '123'})
assert signer.verify_event(event)  # Should pass

# Test 2: Detect tampering
event['payload']['task_id'] = '456'
assert not signer.verify_event(event)  # Should fail

# Test 3: Batch verification
events = [
    signer.sign_event('task_completed', {'task_id': '1'}),
    signer.sign_event('task_completed', {'task_id': '2'}),
]
result = signer.batch_verify_events(events)
assert result['summary']['valid'] == 2
```

### 5. Tenant Isolation Tests

Run tenant isolation tests:
```bash
python3 -m pytest tests/test_security_phase3.py::TestTenantSecurityEnforcer -v
```

**Manual verification:**

```python
from runtime.core.tenant_security import TenantSecurityEnforcer, TenantManager
from pathlib import Path

manager = TenantManager(Path('/tmp/test-tenants'))
enforcer = TenantSecurityEnforcer(manager)

# Test 1: Matching tenant IDs allowed
allowed, reason = enforcer.verify_tenant_access('tenant-a', 'tenant-a')
assert allowed  # Should pass

# Test 2: Mismatched tenant IDs denied
allowed, reason = enforcer.verify_tenant_access('tenant-a', 'tenant-b')
assert not allowed  # Should fail

# Test 3: Rate limit works
for i in range(100):
    enforcer.check_request_rate_limit('tenant-a')

allowed, retry = enforcer.check_request_rate_limit('tenant-a')
# 101st request should be blocked
```

### 6. CSP Headers Test

```bash
# Verify CSP headers present
curl -I http://localhost:8787/ | grep -i "content-security-policy"

# Should return:
# Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; ...

# Test 2: Inline scripts blocked (browser test)
# Open browser console and try:
# <script>alert('XSS')</script>
# Should see CSP violation in console
```

### 7. Sandbox Manager Tests

Run sandbox tests:
```bash
python3 -m pytest tests/test_security_phase3.py::TestSandboxing -v
```

**Manual verification:**

```python
from runtime.core.sandbox_manager import SandboxManager, SandboxPolicy

policy = SandboxPolicy(
    max_cpu_seconds=5,
    max_memory_mb=100,
    allowed_imports=['math'],
)

manager = SandboxManager(policy)

# Test 1: Safe code executes
result = manager.execute_agent_code(
    'test-agent',
    'result = 2 + 2',
    {},
    timeout=5,
)
assert result['success']
assert result['result'] == 4

# Test 2: Dangerous operations blocked
result = manager.execute_agent_code(
    'test-agent',
    'import subprocess; subprocess.call(["ls"])',
    {},
    timeout=5,
)
assert not result['success']
assert 'blocked operations' in result['error']

# Test 3: Timeout enforced
result = manager.execute_agent_code(
    'test-agent',
    'import time; time.sleep(100)',
    {},
    timeout=2,
)
assert not result['success']
assert 'timeout' in result['error'].lower()
```

### 8. Secrets Rotation Tests

```javascript
// Test in Node.js shell
const { SecretsRotationManager } = require('./backend/security/secrets-rotation');
const path = require('path');
const os = require('os');

const manager = new SecretsRotationManager({
  envPath: path.join(os.homedir(), '.ai-employee', '.env'),
  enableVault: false,  // Disable for testing
});

// Test 1: Mask secrets
const logLine = 'JWT_SECRET_KEY=abc123def456789';
const masked = manager.maskSecrets(logLine);
console.log(masked);
// Should output: JWT_SECRET_KEY=[REDACTED]

// Test 2: Get rotation status
const status = manager.getRotationStatus();
console.log(status);
// Should show days until rotation for each secret

// Test 3: Rotate secret (optional)
// manager.rotateSecret('JWT_SECRET_KEY')
```

## Load Testing

### Basic Load Test

Use Apache Bench or similar:

```bash
# Test 1: Rate limit enforcement under load
ab -n 1000 -c 100 http://localhost:8787/api/status

# Expected: Some 429 responses due to rate limits

# Test 2: Token verification performance
ab -n 1000 -c 100 \
  -H "Authorization: Bearer <valid_token>" \
  http://localhost:8787/api/profile

# Expected: < 100ms average response time

# Test 3: RBAC check overhead
ab -n 1000 -c 50 \
  -H "Authorization: Bearer <token>" \
  http://localhost:8787/api/agents

# Expected: < 50ms average overhead from RBAC
```

### Concurrent Tenant Load Test

```bash
# Simulate multiple tenants hitting rate limits independently
for tenant_id in {1..10}; do
  TOKEN=$(./get-tenant-token.sh $tenant_id)
  ab -n 100 -c 10 \
    -H "Authorization: Bearer $TOKEN" \
    http://localhost:8787/api/status &
done

wait

# Each tenant should get ~100 requests through (default 100 req/min per tenant)
# Total: 1000 requests distributed across 10 tenants
```

## Security Penetration Testing

### XSS Prevention (CSP)

```javascript
// Try injection in request parameters
// Should be blocked by CSP

fetch('/api/users', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: '<script>alert("XSS")</script>',
  }),
});

// Check browser console: CSP should block inline script execution
```

### Tenant ID Spoofing

```bash
# Try to access another tenant's data
# Token has tenant_id="tenant-a"
# Request URL path has tenant_id="tenant-b"

curl -H "Authorization: Bearer <tenant_a_token>" \
  http://localhost:8787/api/tenants/tenant-b/data

# Should return 403 Forbidden (tenant ID mismatch)
```

### Token Reuse Prevention

```bash
# Use old refresh token after it's been rotated
# Step 1: Login to get refresh token
TOKEN=$(curl -X POST http://localhost:8787/auth/login \
  -d '...' | jq -r '.refresh_token')

# Step 2: Refresh once
NEW_TOKEN=$(curl -X POST http://localhost:8787/auth/refresh \
  -d "{\"refreshToken\":\"$TOKEN\"}" | jq -r '.refresh_token')

# Step 3: Try to use OLD token again (should fail)
curl -X POST http://localhost:8787/auth/refresh \
  -d "{\"refreshToken\":\"$TOKEN\"}"

# Expect: 401 Unauthorized (token already rotated)
```

### Rate Limit Bypass Attempts

```bash
# Try to bypass with spoofed IP header
curl -H "X-Forwarded-For: 1.1.1.1" \
  http://localhost:8787/api/status

# Should still be rate limited per actual IP or X-Forwarded-For
# (depending on trust model)
```

## Continuous Security Testing

### Automated Security Checks

```bash
# Run security test suite on each commit
npm run test:security

# Run OWASP ZAP scan
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://localhost:8787 \
  -r owasp-report.html

# SCA (Software Composition Analysis)
npm audit
pip install safety && safety check
```

### Monitoring & Alerting

Check these metrics continuously:

```bash
# High-level security metrics
curl http://localhost:8787/metrics | grep security_

# Specific checks:
# - security_token_verify_failures (should be < 1/min)
# - security_permission_denied (normal baseline)
# - security_rate_limit_violations (alert if spike)
# - security_tenant_spoofing_attempts (alert on any)
# - security_sandbox_timeouts (monitor for DoS)
```

## Post-Deployment Verification

Run these checks after deploying to production:

1. Token manager working:
   ```bash
   curl -H "Authorization: Bearer <token>" \
     https://api.example.com/api/profile
   # Should return 200, not 401
   ```

2. RBAC enforced:
   ```bash
   curl -X POST https://api.example.com/api/security \
     -H "Authorization: Bearer <employee_token>"
   # Should return 403, not 200
   ```

3. Rate limiting active:
   ```bash
   # Rapid requests should eventually 429
   for i in {1..1500}; do
     curl -s https://api.example.com/api/status > /dev/null
   done
   ```

4. CSP headers present:
   ```bash
   curl -I https://api.example.com/ | grep -i csp
   # Should have CSP header
   ```

5. Audit logging:
   ```bash
   # Check that security events are logged
   tail -f logs/audit.log | grep -i security
   ```

## Remediation

If security tests fail:

1. Check test output for specific failure
2. Review relevant component code
3. Enable debug logging: `LOG_LEVEL=DEBUG`
4. Check that dependencies are installed:
   ```bash
   pip install RestrictedPython  # For sandbox
   npm install jsonwebtoken      # For tokens
   ```
5. Verify environment variables are set:
   ```bash
   echo $JWT_SECRET_KEY
   echo $HMAC_KEY
   ```
6. Review SECURITY-PHASE3.2.md troubleshooting section

---

**All tests should pass before production deployment.**
