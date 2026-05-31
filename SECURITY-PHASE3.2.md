# Phase 3.2 Security Hardening — Implementation Guide

## Overview

Phase 3.2 implements defense-in-depth security hardening across the AI-EMPLOYEE system with eight core security components. This document serves as the operational guide for deployment, configuration, and maintenance.

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL REQUESTS                        │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
                ┌──────────────────────┐
                │   Rate Limiter       │ ← Global/Tenant/IP limits
                │   (token bucket)     │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  CSP + Security      │ ← Headers, XSS prevention
                │  Headers Middleware  │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  Tenant Isolation    │ ← JWT verification, spoofing check
                │  Enforcer            │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  Token Manager       │ ← Access/refresh token validation
                │  (JWT verification)  │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  RBAC Enforcer       │ ← Resource-level permissions
                │  (role-based access) │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  Signed Events       │ ← HMAC verification
                │  Validator           │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  Sandbox Manager     │ ← Agent code isolation
                │  (resource limits)   │
                └──────────┬───────────┘
                           ↓
                ┌──────────────────────┐
                │  Audit Logger        │ ← Security event logging
                │  (SQLite append-only)│
                └──────────────────────┘
```

## Component 1: JWT Token Management

**File:** `backend/middleware/token-manager.js`

Enhanced token lifecycle with rotation and scoped tokens.

### Features
- **Access tokens** (15 min): Short-lived, used for API requests
- **Refresh tokens** (7 days): Long-lived, issued only on login or valid refresh
- **WebSocket tokens** (5 min): Separate scoped token for WS connections
- **Token rotation**: New refresh token issued on each use (prevents token reuse)
- **Token revocation**: Refresh token hash stored (not plaintext)
- **Version tracking**: Allows bulk revocation via token version

### Usage

```javascript
const { TokenManager } = require('./backend/middleware/token-manager');

const tokenManager = new TokenManager(process.env.JWT_SECRET_KEY);

// Issue token pair on login
const { accessToken, refreshToken } = tokenManager.issueTokenPair('user-123', {
  email: 'user@example.com',
  tenant_id: 'tenant-456',
  role: 'manager',
});

// Verify access token on each protected request
const payload = tokenManager.verifyAccessToken(accessToken);

// Refresh access token (issues new refresh token too)
const { accessToken: newAccessToken, refreshToken: newRefreshToken } =
  tokenManager.refreshAccessToken(refreshToken);

// Issue WebSocket token
const wsToken = tokenManager.issueWSToken('user-123');

// Logout: revoke refresh token
tokenManager.revokeRefreshToken(refreshToken);

// Get stats
console.log(tokenManager.getStats());
```

### Integration in Express

```javascript
const express = require('express');
const tokenManager = new TokenManager(process.env.JWT_SECRET_KEY);

const app = express();

// Login endpoint
app.post('/auth/login', (req, res) => {
  const { email, password } = req.body;
  
  // Verify credentials (implement)
  const { accessToken, refreshToken } = tokenManager.issueTokenPair(userId, {
    email,
    tenant_id: 'tenant-from-db',
    role: 'employee',
  });

  res.json({
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_in: 15 * 60, // 15 minutes
  });
});

// Refresh endpoint
app.post('/auth/refresh', (req, res) => {
  try {
    const { refreshToken } = req.body;
    const { accessToken, refreshToken: newRefreshToken } =
      tokenManager.refreshAccessToken(refreshToken);

    res.json({
      access_token: accessToken,
      refresh_token: newRefreshToken,
    });
  } catch (err) {
    res.status(401).json({ error: err.message });
  }
});

// Logout endpoint
app.post('/auth/logout', (req, res) => {
  const { refreshToken } = req.body;
  tokenManager.revokeRefreshToken(refreshToken);
  res.json({ ok: true });
});

// Protected endpoint
app.get('/api/profile', (req, res) => {
  const token = req.headers.authorization?.slice(7); // Remove "Bearer "
  try {
    const payload = tokenManager.verifyAccessToken(token);
    res.json({ user_id: payload.sub, email: payload.email });
  } catch (err) {
    res.status(401).json({ error: 'Invalid token' });
  }
});
```

---

## Component 2: RBAC Enforcer

**File:** `backend/rbac/enforcer.js`

Fine-grained resource-level access control.

### Features
- **Resource types**: agents, workflows, memory, economy, security, admin
- **Actions**: read, write, delete, execute, configure
- **Role hierarchy**: super_admin > org_admin > manager > employee/auditor
- **Tenant isolation**: Resources scoped to tenant
- **Audit logging**: Permission decisions logged

### RBAC Matrix

```
super_admin   → All resources, all actions
org_admin     → Agents/workflows (execute+configure), memory/economy (write), security (configure)
manager       → Agents/workflows/memory/economy (read+execute), security (read)
employee      → Agents/workflows/memory/economy (read-only)
auditor       → Agents/workflows/memory/economy/security (read-only)
security_officer → Security (read+write+configure), admin (read)
```

### Usage

```javascript
const { RBACEnforcer, RESOURCES, ACTIONS } = require('./backend/rbac/enforcer');

const enforcer = new RBACEnforcer();

// Check permission
const check = enforcer.canUserPerformAction('manager', ACTIONS.EXECUTE, RESOURCES.WORKFLOWS);
if (check.allowed) {
  // Proceed
} else {
  console.error(check.reason);
}

// Enforce (throw on deny)
try {
  enforcer.enforce('employee', ACTIONS.WRITE, RESOURCES.SECURITY);
} catch (err) {
  console.error(err.message); // "Role 'employee' cannot write security"
}

// Get all permissions for a role
const perms = enforcer.getRolePermissions('manager');
console.log(perms);
// { agents: ['read', 'execute'], workflows: ['read', 'execute'], ... }
```

### Express Middleware

```javascript
const { requireAction, requireResourceAccess, RESOURCES, ACTIONS } = require('./rbac/enforcer');

// Route-level permission check
app.post('/api/agents/:agentId/execute', 
  requireAction(ACTIONS.EXECUTE, RESOURCES.AGENTS),
  (req, res) => {
    // Only users with execute permission reach here
    res.json({ ok: true });
  }
);

// Resource-scoped permission check
app.delete('/api/agents/:agentId',
  requireResourceAccess(ACTIONS.DELETE, RESOURCES.AGENTS, req => req.params.agentId),
  (req, res) => {
    // Only users who can delete this agent reach here
    res.json({ ok: true });
  }
);
```

---

## Component 3: Signed Events

**File:** `runtime/core/signed_events.py`

HMAC-based event integrity verification.

### Features
- **Event signing**: HMAC-SHA256 signature includes event_id, type, timestamp, payload hash
- **Signature verification**: Constant-time comparison prevents timing attacks
- **Batch operations**: Sign/verify multiple events efficiently
- **Validator middleware**: Auto-filters invalid events before processing

### Usage

```python
from core.signed_events import EventSigner, SignedEventValidator

# Initialize signer
signer = EventSigner(os.environ['HMAC_SECRET'])

# Sign an event
event = signer.sign_event(
    'task_completed',
    {
        'task_id': 'task-123',
        'result': 'success',
        'execution_time': 5.2,
    },
)

# Verify signature
if signer.verify_event(event):
    process_event(event)
else:
    log_invalid_event(event)

# Batch operations
events = [
    {'task_id': 't1', 'status': 'done'},
    {'task_id': 't2', 'status': 'done'},
]
signed_events = signer.batch_sign_events(events, 'task_completed')

# Verify batch
result = signer.batch_verify_events(signed_events)
print(f"Valid: {len(result['valid'])}, Invalid: {len(result['invalid'])}")

# Use validator middleware
validator = SignedEventValidator(signer)

@validator.wrap_consumer
def handle_task_event(payload):
    print(f"Processing: {payload}")

# Consume event (signature verified automatically)
handle_task_event(signed_event)
```

### Integration with Event Bus

```python
from core.bus import SimpleMessageBus
from core.signed_events import EventSigner, SignedEventValidator

bus = SimpleMessageBus()
signer = EventSigner('hmac-secret-key')
validator = SignedEventValidator(signer)

# Publish signed event
event = signer.sign_event('task_created', {'task_id': '123'})
bus.publish('tasks', event)

# Consume with validation
def task_handler(event):
    validated = validator.validate_and_process(event)
    if validated:
        process_task(validated['payload'])

bus.subscribe('tasks', task_handler)
```

---

## Component 4: Content Security Policy

**File:** `backend/middleware/csp.js`

Defense against XSS, clickjacking, and data exfiltration.

### Features
- **CSP headers**: Restrict inline scripts, external resources
- **HSTS**: Enforce HTTPS for 1 year
- **X-Frame-Options**: Prevent clickjacking
- **X-Content-Type-Options**: Prevent MIME sniffing
- **Permissions-Policy**: Disable dangerous APIs

### Default Policy

```
default-src 'self'                    (only same-origin by default)
script-src 'self' 'wasm-unsafe-eval'  (block inline scripts, allow WASM)
style-src 'self' 'unsafe-inline'      (allow inline for styled-components)
img-src 'self' data: https:           (data URLs + HTTPS images)
font-src 'self' data:                 (inline fonts)
connect-src 'self' wss: ws:           (only same-origin + WebSocket)
frame-ancestors 'none'                (no embedding in iframes)
base-uri 'self'                       (prevent base tag injection)
form-action 'self'                    (only same-origin forms)
upgrade-insecure-requests             (auto-upgrade HTTP to HTTPS)
```

### Usage

```javascript
const { csrfProtection, cspViolationReporter } = require('./middleware/csp');

const app = express();

// Apply CSP headers to all responses
app.use(csrfProtection);

// Optional: receive CSP violation reports
app.post('/__csp-violation-report', cspViolationReporter);

// Monitor CSP violations
app.use((req, res, next) => {
  res.on('finish', () => {
    const csp = res.getHeader('Content-Security-Policy');
    if (csp) {
      console.log('CSP enabled for', req.path);
    }
  });
  next();
});
```

### Testing CSP

```bash
# Check CSP headers
curl -I https://localhost:8787/api/profile
# Should see: Content-Security-Policy: default-src 'self'; ...
```

---

## Component 5: Rate Limiting

**File:** `backend/gateway/rate_limiter.js`

Token bucket rate limiting with tenant/IP scopes.

### Limits
- **Global**: 10,000 req/min (burst window 1 min)
- **Per-tenant**: 1,000 req/min
- **Per-IP**: 100 req/min (for anonymous)

### Features
- **Sliding window**: Smooth rate limiting (not fixed buckets)
- **Multi-scope**: Global + tenant + IP checks stacked
- **Status headers**: X-RateLimit-* headers on responses
- **Violation logging**: Audit trail of rate limit hits

### Usage

```javascript
const { RateLimiter, rateLimitMiddleware } = require('./gateway/rate_limiter');

const limiter = new RateLimiter();

// Express middleware
app.use(rateLimitMiddleware(limiter));

// Manual check
const { allowed, reason, retryAfter } = limiter.checkLimit('tenant-123', '192.168.1.1');
if (!allowed) {
  res.status(429).json({ error: reason, retry_after: retryAfter });
}

// Get status
const status = limiter.getStatus();
console.log(`Active tenants: ${status.active_tenants}, Violations: ${status.violations_recorded}`);

// Reset tenant limit (admin)
limiter.resetTenantLimit('tenant-123');

// Get tenant status
const tenantStatus = limiter.getTenantStatus('tenant-123');
console.log(`Remaining: ${tenantStatus.tokens}/${tenantStatus.capacity}`);
```

### Response Headers

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1715598060

HTTP/1.1 429 Too Many Requests
Retry-After: 42
```

---

## Component 6: Tenant Isolation Hardening

**File:** `runtime/core/tenant_security.py`

Enhanced multi-tenant isolation and security policies.

### Features
- **Tenant ID verification**: JWT + request params must match (prevent spoofing)
- **Per-tenant rate limiting**: 100 req/min per tenant (configurable)
- **Tenant suspension**: Block all requests from misbehaving tenant
- **Data isolation verification**: Randomized sampling of state files
- **Audit logging**: All security events logged with tenant_id

### Usage

```python
from core.tenancy import TenantManager
from core.tenant_security import init_tenant_security

# Initialize
tenant_manager = TenantManager(Path.home() / '.ai-employee')
tenant_security = init_tenant_security(tenant_manager, audit_log_fn=my_audit_logger)

# Verify tenant access (prevent spoofing)
allowed, reason = tenant_security.verify_tenant_access(
    request_tenant_id='tenant-123',
    jwt_tenant_id='tenant-123',
    context_tenant_id='tenant-123',
)

if not allowed:
    raise HTTPException(status_code=403, detail=reason)

# Check request rate limit
allowed, retry_after = tenant_security.check_request_rate_limit('tenant-123')
if not allowed:
    raise HTTPException(
        status_code=429,
        detail=f'Rate limit exceeded. Retry after {retry_after}s',
    )

# Suspend tenant (blocks all requests)
tenant_security.suspend_tenant('tenant-456', reason='Security violation detected')

# Verify data isolation
result = tenant_security.verify_data_isolation('tenant-123', sample_size=10)
if not result['verified']:
    log_critical_error(f"Data isolation check failed: {result['mismatches']}")

# Get security status
status = tenant_security.get_tenant_security_status('tenant-123')
print(status)
# {
#   'suspended': False,
#   'max_requests_per_minute': 100,
#   'rate_limiter_status': { 'tokens_available': 98, 'fill_percentage': 98 },
# }
```

### FastAPI Middleware Integration

```python
from fastapi import Request, HTTPException
from core.tenant_security import get_tenant_security_enforcer

@app.middleware("http")
async def tenant_security_middleware(request: Request, call_next):
    # Extract tenant from JWT
    tenant_id = request.state.tenant_id  # Set by auth middleware
    
    if not tenant_id:
        return await call_next(request)
    
    enforcer = get_tenant_security_enforcer()
    
    # Check rate limit
    allowed, retry_after = enforcer.check_request_rate_limit(tenant_id)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={'error': f'Rate limit exceeded. Retry after {retry_after}s'},
        )
    
    response = await call_next(request)
    response.headers['X-Tenant-Id'] = tenant_id
    return response
```

---

## Component 7: Executable Sandboxing

**File:** `runtime/core/sandbox_manager.py`

Secure agent code execution with resource limits and operation blocking.

### Features
- **Code validation**: Detects blocked operations before execution
- **Resource limits**: Max 30s CPU, 500MB memory
- **Whitelist imports**: Only safe Python modules allowed
- **Subprocess isolation**: Agent code runs in separate process
- **Timeout handling**: Graceful or force kill on timeout
- **Audit logging**: All executions and blocks logged

### Policy Configuration

```python
from core.sandbox_manager import SandboxPolicy, SandboxManager

# Create policy
policy = SandboxPolicy(
    max_cpu_seconds=30,
    max_memory_mb=500,
    allowed_imports=['json', 'math', 'datetime', 'itertools'],
    blocked_operations=['open', 'exec', 'eval', '__import__'],
    allow_network=False,
    allow_file_system=False,
)

# Create manager
manager = SandboxManager(policy, audit_log_fn=my_audit_logger)
```

### Execution

```python
# Execute agent code
result = manager.execute_agent_code(
    agent_id='agent-sales-closer',
    code='''
result = sum([1, 2, 3, 4, 5])
''',
    context={'input': {'data': 'value'}},
    timeout=10,
)

print(result)
# {
#     'success': True,
#     'result': 15,
#     'execution_time': 0.015,
#     'blocked_operations': [],
# }
```

### Blocking Dangerous Operations

```python
# This will be blocked
dangerous_code = '''
import subprocess
subprocess.call(['rm', '-rf', '/'])
'''

result = manager.execute_agent_code('agent-id', dangerous_code, {})
print(result['success'])  # False
print(result['error'])    # "Code contains blocked operations: subprocess"
```

---

## Component 8: Secrets Rotation

**File:** `backend/security/secrets-rotation.js`

Automated secret rotation with vault integration.

### Features
- **JWT secret rotation**: Every 30 days (keep old keys for transition)
- **HMAC key rotation**: Every 30 days
- **Vault integration**: Store/retrieve secrets from HashiCorp Vault
- **Secret masking**: Redact API keys in logs
- **Rotation endpoint**: Admin-only rotation API

### Setup

```bash
# Set up .env (secure: 0600 permissions)
mkdir -p ~/.ai-employee
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> ~/.ai-employee/.env
echo "HMAC_KEY=$(openssl rand -hex 32)" >> ~/.ai-employee/.env
chmod 600 ~/.ai-employee/.env

# Optional: Configure Vault
export VAULT_ADDR=https://vault.example.com:8200
export VAULT_TOKEN=s.xxxxx
```

### Usage

```javascript
const { SecretsRotationManager, rotateSecretsEndpoint } = require('./secrets-rotation');

const secretsManager = new SecretsRotationManager({
  envPath: path.join(os.homedir(), '.ai-employee', '.env'),
  enableVault: true,
});

// Get a secret
const jwtSecret = await secretsManager.getSecret('JWT_SECRET_KEY');

// Rotate a single secret
const result = await secretsManager.rotateSecret('JWT_SECRET_KEY');
console.log(result);
// { name: 'JWT_SECRET_KEY', rotated_at: '2026-05-13T...', new_key_preview: 'abc1...' }

// Rotate all secrets
const results = await secretsManager.rotateAllSecrets();

// Check rotation status
const status = secretsManager.getRotationStatus();
console.log(status);
// {
//   JWT_SECRET_KEY: {
//     last_rotated: '2026-04-13T...',
//     next_rotation: '2026-05-13T...',
//     days_until_rotation: 30,
//     should_rotate_now: false,
//   },
// }

// Mask secrets in logs
const logLine = 'Failed to authenticate: JWT_SECRET_KEY=abc123def456';
const masked = secretsManager.maskSecrets(logLine);
console.log(masked);  // Failed to authenticate: JWT_SECRET_KEY=[REDACTED]

// Express endpoint (admin only)
app.post('/admin/rotate-secrets',
  requireRole('org_admin'),
  rotateSecretsEndpoint(secretsManager),
);
```

### Vault Configuration Example

```hcl
# vault/auth-payload.hcl
path "secret/data/ai-employee/*" {
  capabilities = ["create", "read", "update", "patch", "list"]
}
```

```bash
# Store secret in Vault
vault kv put secret/ai-employee/JWT_SECRET_KEY value=$(openssl rand -hex 32)

# Retrieve
vault kv get secret/ai-employee/JWT_SECRET_KEY
```

---

## Integration Checklist

### Phase 1: Token Management
- [ ] Replace old auth middleware with TokenManager
- [ ] Update login/refresh endpoints
- [ ] Update WebSocket authentication
- [ ] Test token expiration and refresh
- [ ] Monitor token stats in observability dashboard

### Phase 2: RBAC
- [ ] Enable RBACEnforcer on protected routes
- [ ] Audit log permission decisions
- [ ] Test each role's permissions
- [ ] Document custom role definitions
- [ ] Train team on permission model

### Phase 3: Signed Events
- [ ] Initialize EventSigner on startup
- [ ] Wrap all event publications in sign_event()
- [ ] Update event consumers to verify signatures
- [ ] Test signature validation
- [ ] Enable audit logging for invalid events

### Phase 4: CSP Headers
- [ ] Deploy CSP middleware
- [ ] Test in browser console for CSP violations
- [ ] Collect violation reports (CSP Report-Only mode first)
- [ ] Adjust policy if legitimate use cases blocked
- [ ] Monitor violation metrics

### Phase 5: Rate Limiting
- [ ] Deploy RateLimiter middleware
- [ ] Test with load testing tools
- [ ] Adjust limits based on production traffic
- [ ] Monitor violations per tenant
- [ ] Alert on suspicious patterns

### Phase 6: Tenant Isolation
- [ ] Enable TenantSecurityEnforcer
- [ ] Test tenant ID spoofing prevention
- [ ] Run data isolation verification regularly
- [ ] Test tenant suspension mechanism
- [ ] Document recovery procedures

### Phase 7: Sandboxing
- [ ] Deploy SandboxManager for agent execution
- [ ] Test resource limit enforcement
- [ ] Verify blocked operations are caught
- [ ] Monitor execution performance
- [ ] Tune limits based on agent profiles

### Phase 8: Secrets Rotation
- [ ] Set up .env with secure permissions
- [ ] Optional: Configure HashiCorp Vault
- [ ] Create rotation schedule (cron)
- [ ] Test rotation endpoint
- [ ] Document recovery from rotation failures

---

## Monitoring & Alerting

### Key Metrics to Track

```
Token Manager:
  - active_refresh_tokens (should be < 10k)
  - failed_token_verifications (spike = attack?)
  - token_refresh_rate (normal baseline)

RBAC:
  - permission_denied_count (per role)
  - escalation_required_count (for manual review)
  - permission_error_rate (should be < 1%)

Rate Limiter:
  - violations_per_minute (global, per tenant)
  - rate_limit_hit_by_tenant (identifies misbehaving tenants)
  - ip_violations (identifies attackers)

Tenant Security:
  - suspended_tenants (should be 0)
  - data_isolation_failures (critical: investigate immediately)
  - cross_tenant_access_attempts (critical: block IP)

Sandbox:
  - timeouts_per_agent (agent code too slow?)
  - blocked_operations_per_agent (code quality issue?)
  - memory_usage_by_agent (resource tuning)
  - subprocess_attempts_blocked (security issue)

Signed Events:
  - invalid_signatures_per_minute (tampering attempt?)
  - event_verification_failures (logging/debugging issues)
```

### Alert Rules

```yaml
- name: "Token Verification Spike"
  condition: "failed_token_verifications > 10/min"
  severity: HIGH
  action: "Review auth logs, check for credential stuffing"

- name: "Rate Limit Violations"
  condition: "rate_limit_violations > 100/min"
  severity: MEDIUM
  action: "Check for DDoS, adjust limits if legitimate"

- name: "Tenant Suspension"
  condition: "suspended_tenants > 0"
  severity: CRITICAL
  action: "Investigate immediately, contact customer"

- name: "Data Isolation Failure"
  condition: "data_isolation_verification_failed"
  severity: CRITICAL
  action: "Halt affected tenant, incident investigation"

- name: "Signature Tampering"
  condition: "invalid_signatures > 5/min"
  severity: HIGH
  action: "Review event logs, check for integrity issues"
```

---

## Testing

Run the test suites:

```bash
# Python security tests
python3 -m pytest tests/test_security_phase3.py -v

# Node.js security tests
npm test tests/test_security_node.js

# Full integration test
bash tests/integration_security_test.sh
```

---

## Troubleshooting

### Token Verification Fails
1. Check JWT_SECRET_KEY matches across Node and Python
2. Verify token hasn't expired (15 min lifetime)
3. Check token type (access vs refresh)
4. Review token issuer claim

### RBAC Permission Denied
1. Check user role in JWT
2. Verify role exists in RBAC matrix
3. Check resource/action names (case-sensitive)
4. Review audit log for denial reason

### Rate Limit False Positives
1. Increase per-tenant limit if legitimate traffic
2. Check for token bucket refill logic
3. Verify tenant_id is extracted correctly
4. Review recent traffic patterns

### Tenant Isolation Issues
1. Verify JWT tenant_id claim is present
2. Check request path/params for tenant_id spoofing
3. Run data isolation verification
4. Review tenant state file structure

### Sandbox Timeouts
1. Increase max_cpu_seconds if needed
2. Profile agent code for performance issues
3. Check for infinite loops in code
4. Review resource usage logs

---

## Deployment

### Production Checklist

```
[ ] JWT_SECRET_KEY generated and stored securely
[ ] HMAC_KEY generated and stored securely
[ ] CSP headers enabled (test in Report-Only mode first)
[ ] Rate limit tuned for production traffic
[ ] Tenant isolation verified on staging
[ ] Sandbox resource limits appropriate for agents
[ ] Secrets rotation schedule configured
[ ] Monitoring/alerting configured
[ ] Team trained on new security policies
[ ] Incident response plan updated
[ ] Backup/recovery procedures documented
```

### Rollback Plan

If security hardening causes issues:

1. **Tokens**: Revert to old auth middleware, new tokens still valid for 7 days
2. **RBAC**: Disable requirePermission middleware, fall back to basic auth
3. **CSP**: Switch to Report-Only mode, keep headers for monitoring
4. **Rate Limiting**: Increase limits or disable temporarily
5. **Tenant Isolation**: Revert TenantSecurityEnforcer, audit tenants
6. **Sandboxing**: Disable sandbox, execute agents directly (not recommended)

---

## References

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8949)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CSP Specification](https://w3c.github.io/webappsec-csp/)
