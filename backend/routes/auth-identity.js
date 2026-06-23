'use strict';

// Auth, identity, security, admin, and error routes extracted from server.js.
// Pure refactor — zero behavior changes.

const os = require('os');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const { execSync } = require('child_process');
const { Router } = require('express');
const z = require('zod');

// ── Shared schema primitives (mirrors server.js) ──────────────────────────────
const _zStr    = z.string().trim();
const _zStrMax = (n) => _zStr.max(n);

const SCHEMAS = {
  authToken:           z.object({ secret: _zStr.min(1) }),
  // Scoped service token for non-browser/brain (MCP) access — deny-by-default.
  // scope: 'read' (read-only routes) | 'task-emit' (may queue work for approval).
  serviceToken:        z.object({ secret: _zStr.min(1), scope: z.enum(['read', 'task-emit']), ttl: z.enum(['1h', '8h', '24h', '7d']).optional() }).strict(),
  identityFinalize:    z.object({ user_chosen: _zStrMax(200).optional(), instance_name: _zStrMax(100).optional(), voice_preset: _zStrMax(50).optional(), color_palette: z.record(z.any()).optional() }),
  securityOfflineSync: z.object({ online: z.boolean().optional() }),
  securityGatewayStrict: z.object({ enabled: z.boolean().optional() }),
  errorReport:         z.object({ error: z.any(), context: z.record(z.any()).optional() }),
};

function validate(schema, req, res) {
  const result = schema.safeParse(req.body || {});
  if (!result.success) {
    res.status(400).json({ ok: false, error: 'Validation error', details: result.error.flatten() });
    return null;
  }
  return result.data;
}

// ── Rate limiter factory (mirrors server.js makeRateLimit) ────────────────────
function makeRateLimit(max, windowMs = 60_000) {
  const buckets = new Map();
  return (req, res, next) => {
    const ip = req.ip || req.connection?.remoteAddress || 'unknown';
    const now = Date.now();
    const hits = (buckets.get(ip) || []).filter((t) => now - t < windowMs);
    hits.push(now);
    buckets.set(ip, hits);
    if (hits.length > max) {
      res.set('Retry-After', Math.ceil(windowMs / 1000));
      return res.status(429).json({ ok: false, error: 'Rate limit exceeded' });
    }
    next();
  };
}

const _rl_auth_token = makeRateLimit(5);   // /api/auth/token — 5/min per IP (brute-force guard)
const _rl_auto_token = makeRateLimit(10);  // /api/auth/auto-token — 10/min per IP

// ── Router factory ────────────────────────────────────────────────────────────
// deps: {
//   requireAuth,            — Express middleware
//   JWT_SECRET,             — string
//   JWT_EXPIRES_IN,         — string e.g. '24h'
//   AI_HOME,                — string (resolved path)
//   STATE_DIR,              — string
//   LOG_DIR,                — string
//   RUN_DIR,                — string
//   RUNTIME_MODE,           — string
//   RUNTIME_NONCE,          — string | null
//   REPO_ROOT,              — string
//   PORT,                   — number | string
//   PYTHON_BACKEND_PORT,    — number | string
//   SERVER_START_TIMESTAMP, — ISO string
//   latestCommit,           — () => string
//   statePath,              — (...parts) => string
//   getBlacklightStatus,    — () => object | null
//   apiGatewayProtector,    — { status(), recentHoneypot(n), setStrictMode(b, reason) }
//   securitySyncPolicy,     — { status(), setOnline(bool) }
//   anomalyResponder,       — { status(), evaluate() }
//   secretStore,            — { describe(name, opts) }
//   errorRecovery,          — { getRecentErrors(n), logError(e, ctx), buildRecoveryAction(e, ctx) }
//   _readiness,             — { phase, pythonReady }
//   _auditLog,              — array (reference)
//   collectExpressRoutes,   — () => array
// }
module.exports = function createAuthIdentityRouter(deps) {
  const {
    requireAuth,
    localhostOrAuth,
    JWT_SECRET,
    JWT_EXPIRES_IN,
    AI_HOME,
    STATE_DIR,
    LOG_DIR,
    RUN_DIR,
    RUNTIME_MODE,
    RUNTIME_NONCE,
    REPO_ROOT,
    PORT,
    PYTHON_BACKEND_PORT,
    SERVER_START_TIMESTAMP,
    latestCommit,
    statePath,
    getBlacklightStatus,
    apiGatewayProtector,
    securitySyncPolicy,
    anomalyResponder,
    secretStore,
    errorRecovery,
    _readiness,
    _auditLog,
    recordAuditEvent,
    collectExpressRoutes,
  } = deps;

  const router = Router();

  // ── GET /api/security/status ──────────────────────────────────────────────
  router.get('/api/security/status', requireAuth, (req, res) => {
    const status = getBlacklightStatus();
    res.json({ ok: true, ...(status || { threat_score: 0, mode: 'NORMAL', active_threats: [] }) });
  });

  // ── POST /api/auth/token ──────────────────────────────────────────────────
  // Exchange the master secret for a 24h JWT.
  // Body: { secret: "<JWT_SECRET_KEY from ~/.ai-employee/.env>" }
  router.post('/api/auth/token', _rl_auth_token, (req, res) => {
    const body = validate(SCHEMAS.authToken, req, res);
    if (!body) return;
    if (body.secret !== JWT_SECRET) {
      return res.status(401).json({ ok: false, error: 'Invalid secret' });
    }
    const token = jwt.sign({ sub: 'admin', type: 'access', role: 'admin', iss: 'ai-employee', tenant_id: 'default', org_name: 'Local' }, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN });
    res.json({ ok: true, token, expires_in: JWT_EXPIRES_IN });
  });

  // ── POST /api/auth/service-token ──────────────────────────────────────────
  // Mint a least-privilege scoped token for non-browser/brain (MCP) access.
  // Body: { secret: "<JWT_SECRET_KEY>", scope: "read"|"task-emit", ttl?: "1h"|"8h"|"24h"|"7d" }
  // Deny-by-default: unknown scopes/fields rejected (strict schema); 'read' cannot
  // reach write routes (enforced by requireScope on the routes themselves).
  router.post('/api/auth/service-token', _rl_auth_token, (req, res) => {
    const body = validate(SCHEMAS.serviceToken, req, res);
    if (!body) return;
    if (body.secret !== JWT_SECRET) {
      // Never echo the supplied secret; audit the failed mint attempt.
      if (typeof recordAuditEvent === 'function') {
        recordAuditEvent({ actor: 'service', action: 'service_token_mint_denied', outputData: { reason: 'invalid_secret' }, riskScore: 0.6 });
      }
      return res.status(401).json({ ok: false, error: 'Invalid secret' });
    }
    const ttl = body.ttl || '24h';
    const token = jwt.sign(
      { sub: 'service', type: 'access', role: 'service', scope: body.scope, iss: 'ai-employee', tenant_id: 'default', org_name: 'Local' },
      JWT_SECRET,
      { expiresIn: ttl },
    );
    // Audit the mint — record scope + ttl only, never the token or secret.
    if (typeof recordAuditEvent === 'function') {
      recordAuditEvent({ actor: 'service', action: 'service_token_minted', outputData: { scope: body.scope, ttl }, riskScore: body.scope === 'task-emit' ? 0.4 : 0.2 });
    }
    res.json({ ok: true, token, scope: body.scope, expires_in: ttl });
  });

  // ── GET /api/auth/auto-token ──────────────────────────────────────────────
  // Issues a short-lived JWT for localhost dashboard access (no secret needed).
  // Uses raw socket remoteAddress (unforgeable) — not req.ip which is X-Forwarded-For aware.
  router.get('/api/auth/auto-token', _rl_auto_token, (req, res) => {
    const rawIp = req.socket?.remoteAddress || '';
    const isLocal = rawIp === '127.0.0.1' || rawIp === '::1' || rawIp === '::ffff:127.0.0.1';
    if (!isLocal) return res.status(403).json({ ok: false, error: 'Only available from localhost' });
    const token = jwt.sign({ sub: 'operator', type: 'access', role: 'operator', iss: 'ai-employee', tenant_id: 'default', org_name: 'Local' }, JWT_SECRET, { expiresIn: '8h' });
    res.json({ ok: true, token });
  });

  // ── GET /api/identity/public ──────────────────────────────────────────────
  // Public identity info (no auth required).
  router.get('/api/identity/public', async (req, res) => {
    try {
      const identityFile = path.join(AI_HOME, 'identity.json');
      if (!fs.existsSync(identityFile)) {
        return res.json({
          instance_name: 'Initializing...',
          color_palette: { primary: '#a855f7', accent: '#e5c76b' },
          user_chosen: null
        });
      }
      const identity = JSON.parse(fs.readFileSync(identityFile, 'utf8'));
      res.json({
        instance_name: identity.instance_name,
        user_chosen: identity.user_chosen,
        color_palette: identity.color_palette,
        tenant_id: identity.tenant_id
      });
    } catch (e) {
      res.status(500).json({ error: 'Failed to read identity' });
    }
  });

  // ── GET /api/onboarding/palettes ──────────────────────────────────────────
  // Generate 3 color palettes for onboarding.
  router.get('/api/onboarding/palettes', requireAuth, (req, res) => {
    const generatePalette = () => {
      const hue = Math.random() * 0.3 + 0.65;  // 65-95% of hue circle (purples/magentas)
      const saturation = 0.6 + Math.random() * 0.3;  // 60-90%
      const toHex = (h, s, l) => {
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs((h * 6) % 2 - 1));
        const m = l - c / 2;
        let r = 0, g = 0, b = 0;
        if (h < 1/6) [r, g, b] = [c, x, 0];
        else if (h < 1/3) [r, g, b] = [x, c, 0];
        else if (h < 1/2) [r, g, b] = [0, c, x];
        else if (h < 2/3) [r, g, b] = [0, x, c];
        else if (h < 5/6) [r, g, b] = [x, 0, c];
        else [r, g, b] = [c, 0, x];
        return '#' + [r + m, g + m, b + m].map(x => Math.round((x) * 255).toString(16).padStart(2, '0')).join('');
      };
      return {
        primary: toHex(hue, saturation, 0.4),
        accent: toHex(hue, saturation * 0.8, 0.55),
        secondary: toHex((hue + 0.15) % 1.0, saturation * 0.7, 0.4)
      };
    };
    res.json({
      palettes: [generatePalette(), generatePalette(), generatePalette()]
    });
  });

  // ── POST /api/identity/finalize ───────────────────────────────────────────
  // Save user onboarding choices.
  router.post('/api/identity/finalize', requireAuth, async (req, res) => {
    const _bodyIdentity = validate(SCHEMAS.identityFinalize, req, res);
    if (!_bodyIdentity) return;
    try {
      const { user_chosen, instance_name, voice_preset, color_palette } = _bodyIdentity;
      const homedir = process.env.HOME || process.env.USERPROFILE;
      const identityFile = path.join(homedir, '.ai-employee', 'identity.json');

      const dir = path.dirname(identityFile);
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

      let identity;
      if (fs.existsSync(identityFile)) {
        identity = JSON.parse(fs.readFileSync(identityFile, 'utf8'));
      } else {
        identity = {
          tenant_id: `tnt_${Math.random().toString(36).substr(2, 12)}`,
          instance_name: instance_name || 'Aurora-Prime',
          user_chosen: null,
          color_palette: color_palette || { primary: '#a855f7', accent: '#e5c76b' },
          voice_preset: voice_preset || 'professional',
          emergent: { vocabulary_signature: [], favorite_agents: [], work_pattern: null, tone_drift: 0.0 },
          created_at: new Date().toISOString(),
          evolution_log: []
        };
      }

      if (user_chosen) identity.user_chosen = user_chosen;
      if (instance_name) identity.instance_name = instance_name;
      if (voice_preset) identity.voice_preset = voice_preset;
      if (color_palette) identity.color_palette = color_palette;

      identity.evolution_log = identity.evolution_log || [];
      identity.evolution_log.push({
        event: 'identity_finalized',
        timestamp: new Date().toISOString(),
        user_chosen,
        voice_preset
      });

      fs.writeFileSync(identityFile, JSON.stringify(identity, null, 2));
      res.json({ ok: true, identity });
    } catch (e) {
      console.error('Failed to finalize identity:', e);
      res.status(500).json({ error: 'Failed to save identity' });
    }
  });

  // ── GET /api/identity ─────────────────────────────────────────────────────
  // Machine identity (auth required).
  router.get('/api/identity', requireAuth, (req, res) => {
    const idPath = statePath('identity.json');
    try {
      if (fs.existsSync(idPath)) {
        res.json(JSON.parse(fs.readFileSync(idPath, 'utf8')));
      } else {
        const fp = crypto.createHash('sha256')
          .update(os.hostname()).update(String(os.cpus().length)).digest('hex').slice(0, 16);
        const names = ['Athena', 'Orion', 'Nova', 'Atlas', 'Echo', 'Cipher', 'Nexus', 'Pulse', 'Axiom', 'Vega'];
        const id = {
          id: crypto.randomUUID(),
          fingerprint: fp,
          name: names[parseInt(fp.slice(0, 4), 16) % names.length],
          hostname: os.hostname(),
          created_at: new Date().toISOString(),
          first_boot: true,
        };
        const dir = path.dirname(idPath);
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(idPath, JSON.stringify(id, null, 2));
        res.json(id);
      }
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // ── GET /api/runtime/identity ─────────────────────────────────────────────
  // F1: the desktop supervisor probes this tokenless from loopback to verify it is
  // talking to the right runtime (nonce match) before any operator token exists. Remote
  // callers still need a JWT. Payload carries runtime metadata + port-lock nonce — no secrets.
  router.get('/api/runtime/identity', localhostOrAuth, (req, res) => {
    res.set('Cache-Control', 'no-store');
    res.json({
      ok: true,
      app: 'AETERNUS NEXUS',
      runtime: 'AI-EMPLOYEE',
      mode: RUNTIME_MODE,
      nonce: RUNTIME_NONCE,
      buildId: process.env.AI_EMPLOYEE_BUILD_ID || latestCommit(),
      repoRoot: REPO_ROOT,
      appHome: AI_HOME,
      stateDir: STATE_DIR,
      logDir: LOG_DIR,
      runDir: RUN_DIR,
      ports: {
        node: Number(PORT),
        python: Number(PYTHON_BACKEND_PORT),
      },
      pid: process.pid,
      platform: process.platform,
      arch: process.arch,
      startedAt: SERVER_START_TIMESTAMP,
    });
  });

  // ── GET /api/security/aztsa/status ───────────────────────────────────────
  router.get('/api/security/aztsa/status', requireAuth, (req, res) => {
    const requiredSecrets = [
      secretStore.describe('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] }),
      secretStore.describe('JWT_SECRET', { aliases: ['JWT_SECRET_KEY'] }),
    ];
    res.json({
      gateway: apiGatewayProtector.status(),
      secret_health: {
        required: requiredSecrets,
        missing: requiredSecrets.filter((item) => !item.configured).map((item) => item.name),
      },
      anomaly_response: anomalyResponder.status(),
      offline_security_sync: securitySyncPolicy.status(),
      honeypot: {
        events: apiGatewayProtector.recentHoneypot(20),
      },
      updated_at: new Date().toISOString(),
    });
  });

  // ── GET /api/security/honeypot/events ────────────────────────────────────
  router.get('/api/security/honeypot/events', requireAuth, (req, res) => {
    const limitRaw = Number((req.query || {}).limit || 50);
    const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(200, limitRaw)) : 50;
    res.json({
      events: apiGatewayProtector.recentHoneypot(limit),
      total: apiGatewayProtector.status().honeypot_events,
    });
  });

  // ── POST /api/security/offline-sync ──────────────────────────────────────
  router.post('/api/security/offline-sync', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.securityOfflineSync, req, res);
    if (!body) return;
    const online = body.online !== false;
    const state = securitySyncPolicy.setOnline(online);
    res.json({
      status: state,
      applied_online: online,
    });
  });

  // ── POST /api/security/anomaly/evaluate ──────────────────────────────────
  router.post('/api/security/anomaly/evaluate', requireAuth, (req, res) => {
    const result = anomalyResponder.evaluate();
    res.json(result);
  });

  // ── POST /api/security/gateway/strict-mode ───────────────────────────────
  router.post('/api/security/gateway/strict-mode', requireAuth, (req, res) => {
    const _bodyGateway = validate(SCHEMAS.securityGatewayStrict, req, res);
    if (!_bodyGateway) return;
    const enabled = Boolean(_bodyGateway.enabled);
    const strict = apiGatewayProtector.setStrictMode(enabled, 'manual_override');
    res.json({
      strict_mode: strict,
      gateway: apiGatewayProtector.status(),
    });
  });

  // ── GET /api/admin/api-catalog ────────────────────────────────────────────
  router.get('/api/admin/api-catalog', requireAuth, (_req, res) => {
    const nodeRoutes = collectExpressRoutes();
    const pythonRoutes = [
      { route: '/api/tasks/run', method: 'POST', auth_required: true, source: 'python', compatibility: 'canonical_agent_controller', response_contract: 'agent_controller_task_result', live_status: _readiness.pythonReady ? 'registered' : 'unavailable', last_smoke_result: null },
      { route: '/api/chat', method: 'POST', auth_required: true, source: 'python', compatibility: 'canonical_llm_pipeline', response_contract: 'chat_result', live_status: _readiness.pythonReady ? 'registered' : 'unavailable', last_smoke_result: null },
      { route: '/health', method: 'GET', auth_required: false, source: 'python', compatibility: 'health', response_contract: 'health', live_status: _readiness.pythonReady ? 'registered' : 'unavailable', last_smoke_result: null },
    ];
    const routes = [...nodeRoutes, ...pythonRoutes];
    const counts = routes.reduce((acc, route) => {
      acc.total = (acc.total || 0) + 1;
      acc[route.source] = (acc[route.source] || 0) + 1;
      acc[route.compatibility] = (acc[route.compatibility] || 0) + 1;
      return acc;
    }, { total: 0 });
    res.json({
      ok: true,
      generated_at: new Date().toISOString(),
      counts,
      routes,
    });
  });

  // ── GET /api/errors ───────────────────────────────────────────────────────
  // Error audit log (e2e + external callers).
  router.get('/api/errors', requireAuth, (req, res) => {
    const limit = Math.min(200, parseInt((req.query || {}).limit) || 100);
    const errors = (_auditLog || [])
      .filter((e) => e.risk_score >= 0.6 || String(e.action || '').includes('fail') || String(e.action || '').includes('error'))
      .slice(0, limit);
    res.json(errors);
  });

  // ── GET /api/errors/recent ────────────────────────────────────────────────
  router.get('/api/errors/recent', requireAuth, (req, res) => {
    const limit = Math.min(parseInt(req.query.limit || 10), 50);
    res.json({ errors: errorRecovery.getRecentErrors(limit) });
  });

  // ── POST /api/errors/report ───────────────────────────────────────────────
  router.post('/api/errors/report', requireAuth, (req, res) => {
    const _bodyErrReport = validate(SCHEMAS.errorReport, req, res);
    if (!_bodyErrReport) return;
    const { error, context } = _bodyErrReport;
    if (!error) return res.status(400).json({ error: 'error required' });

    const logged = errorRecovery.logError(error, context);
    const recovery = errorRecovery.buildRecoveryAction(error, context);

    res.json({ logged, recovery });
  });

  return router;
};
