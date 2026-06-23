'use strict';
// Desktop boot-contract tests (F1 + F2):
//   F1 — GET /api/runtime/identity is tokenless from loopback, JWT-gated for remote.
//   F2 — POST/GET /api/boot/phase handshake works (validated), readiness reflects it.
// Pure-module unit tests + real express+http integration (genuine loopback socket so
// localhostOrAuth runs for real). No supertest dependency.

const assert = require('assert');
const http = require('http');
const path = require('path');
// express lives in backend/node_modules (route modules resolve it from there too).
const express = require(require.resolve('express', { paths: [path.join(__dirname, '..', 'backend')] }));

const { validateBootPhase } = require('../backend/lib/boot-phase');
const { isLoopback, makeLocalhostOrAuth } = require('../backend/middleware/localhost-or-auth');
const createAuthIdentityRouter = require('../backend/routes/auth-identity');
const createHealthRouter = require('../backend/routes/health');

let failures = 0;
function check(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => console.log(`  ok  ${name}`))
    .catch((e) => { failures++; console.error(`  FAIL ${name}: ${e.message}`); });
}

// ── F2 unit: validateBootPhase ────────────────────────────────────────────────
function unitValidate() {
  assert.deepStrictEqual(validateBootPhase({ phase: 'react-rendered' }),
    { ok: true, value: { phase: 'react-rendered', detail: null } });
  assert.strictEqual(validateBootPhase({ phase: 'auth', detail: 'loading' }).value.detail, 'loading');
  assert.strictEqual(validateBootPhase({}).ok, false, 'missing phase rejected');
  assert.strictEqual(validateBootPhase({ phase: '../../etc!!' }).ok, false, 'bad charset rejected');
  assert.strictEqual(validateBootPhase({ phase: 'x'.repeat(65) }).ok, false, 'over-long phase rejected');
  assert.strictEqual(validateBootPhase({ phase: 'a', detail: 42 }).ok, false, 'non-string detail rejected');
  // CR/LF stripped (log-injection safe)
  assert.ok(!/[\r\n]/.test(validateBootPhase({ phase: 'a', detail: 'a\r\nFAKE LOG' }).value.detail));
  // detail capped at 200
  assert.strictEqual(validateBootPhase({ phase: 'a', detail: 'y'.repeat(500) }).value.detail.length, 200);
}

// ── F1 unit: localhost-or-auth ────────────────────────────────────────────────
function unitLocalhost() {
  for (const ip of ['127.0.0.1', '::1', '::ffff:127.0.0.1']) {
    assert.strictEqual(isLoopback({ socket: { remoteAddress: ip } }), true, `${ip} is loopback`);
  }
  assert.strictEqual(isLoopback({ socket: { remoteAddress: '10.0.0.5' } }), false, 'LAN ip not loopback');
  assert.strictEqual(isLoopback({}), false, 'no socket not loopback');

  // loopback → next(), requireAuth NOT consulted
  let authCalled = false;
  const mw = makeLocalhostOrAuth(() => { authCalled = true; });
  let nexted = false;
  mw({ socket: { remoteAddress: '127.0.0.1' } }, {}, () => { nexted = true; });
  assert.ok(nexted && !authCalled, 'loopback bypasses auth');

  // remote → requireAuth consulted
  authCalled = false;
  mw({ socket: { remoteAddress: '8.8.8.8' } }, {}, () => {});
  assert.ok(authCalled, 'remote falls through to requireAuth');

  assert.throws(() => makeLocalhostOrAuth(null), /requireAuth/, 'requires a requireAuth fn');
}

// Shared deps stub: no-op fn for any key not explicitly overridden.
function stubDeps(overrides) {
  return new Proxy({ ...overrides }, { get: (t, p) => (p in t ? t[p] : () => {}) });
}

// reject-all requireAuth (proves remote callers are denied without a token)
const denyAuth = (_req, res) => res.status(401).json({ ok: false, error: 'Authentication required' });
const localhostOrAuth = makeLocalhostOrAuth(denyAuth);

function mountApp(router) {
  const app = express();
  app.use('/', router);
  return http.createServer(app);
}

function request(server, method, path, body) {
  const { port } = server.address();
  return new Promise((resolve, reject) => {
    const data = body != null ? JSON.stringify(body) : null;
    const req = http.request({ host: '127.0.0.1', port, method, path,
      headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {} },
      (res) => {
        let buf = '';
        res.on('data', (c) => (buf += c));
        res.on('end', () => resolve({ status: res.statusCode, json: buf ? JSON.parse(buf) : null }));
      });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

// ── F1 integration: identity tokenless from loopback ──────────────────────────
async function integrationIdentity() {
  const router = createAuthIdentityRouter(stubDeps({
    requireAuth: denyAuth, localhostOrAuth,
    RUNTIME_MODE: 'test', RUNTIME_NONCE: 'nonce-xyz', REPO_ROOT: '/tmp/repo',
    AI_HOME: '/tmp/home', STATE_DIR: '/tmp/state', LOG_DIR: '/tmp/log', RUN_DIR: '/tmp/run',
    PORT: 8787, PYTHON_BACKEND_PORT: 18790, SERVER_START_TIMESTAMP: Date.now(),
    latestCommit: () => 'abc123',
  }));
  const server = mountApp(router);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  try {
    const res = await request(server, 'GET', '/api/runtime/identity');
    assert.strictEqual(res.status, 200, 'loopback identity is tokenless 200');
    assert.strictEqual(res.json.nonce, 'nonce-xyz', 'nonce returned for port-lock match');
    assert.ok(!('jwt' in res.json) && !('JWT_SECRET' in res.json), 'no secrets in payload');
  } finally { server.close(); }
}

// ── F2 integration: boot/phase handshake + readiness reflection ───────────────
async function integrationBootPhase() {
  const _readiness = { phase: 'READY', pythonReady: true, subsystemsReady: true, uiBootPhase: null };
  const router = createHealthRouter(stubDeps({
    requireAuth: denyAuth, localhostOrAuth, _readiness, express,
    PYTHON_BACKEND_PORT: 18790, PYTHON_BACKEND_HOST: '127.0.0.1',
    HAS_FRONTEND_DIST: true,
    checkNeuralGraphReady: async () => ({ ok: true }),
  }));
  const server = mountApp(router);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  try {
    let res = await request(server, 'POST', '/api/boot/phase', { phase: 'react-rendered', detail: 'mounted' });
    assert.strictEqual(res.status, 200, 'valid phase accepted');
    assert.strictEqual(_readiness.uiBootPhase.phase, 'react-rendered', 'readiness state updated');

    res = await request(server, 'GET', '/api/boot/phase');
    assert.strictEqual(res.json.uiBootPhase.phase, 'react-rendered', 'GET reflects last phase');

    res = await request(server, 'POST', '/api/boot/phase', { phase: 'bad!!//' });
    assert.strictEqual(res.status, 400, 'invalid phase rejected');

    res = await request(server, 'GET', '/api/readiness');
    assert.ok('uiBootPhase' in res.json, 'readiness exposes uiBootPhase');
    assert.strictEqual(res.json.uiBootPhase.phase, 'react-rendered', 'readiness carries the phase');
  } finally { server.close(); }
}

(async () => {
  console.log('boot-contract (F1 + F2):');
  await check('F2 unit: validateBootPhase', unitValidate);
  await check('F1 unit: localhost-or-auth', unitLocalhost);
  await check('F1 integration: identity tokenless from loopback', integrationIdentity);
  await check('F2 integration: boot/phase handshake + readiness', integrationBootPhase);
  if (failures) { console.error(`\n${failures} test(s) failed`); process.exit(1); }
  console.log('\nall boot-contract tests passed');
})();
