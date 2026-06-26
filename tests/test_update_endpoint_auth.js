'use strict'

// Regression: the desktop launcher / boot flow calls the system update endpoints
// from loopback BEFORE an operator JWT exists. They were requireAuth-only → 401.
// They now use localhostOrAuth: tokenless from loopback, JWT for remote. Verified by
// driving the router stack directly (no server / no top-level express dependency).

const assert = require('assert')
const { makeLocalhostOrAuth } = require('../backend/middleware/localhost-or-auth')
const createSystemOpsRouter = require('../backend/routes/system-ops')

let passed = 0
const ok = (name) => { console.log(`  ok  ${name}`); passed++ }

// requireAuth stub: always denies (simulates "no operator token yet").
const requireAuth = (_req, res) => res.status(401).json({ error: 'auth required' })
const localhostOrAuth = makeLocalhostOrAuth(requireAuth)

// Other routes in this router use various deps as middleware (validate(schema),
// _rl_upload, ...). We only exercise the update routes, so every other dep is a
// universal passthrough: callable as middleware (req,res,next)->next() AND as a
// factory validate(schema)->middleware. Real auth deps are kept.
const _passthrough = (_req, _res, next) => next && next()
const deps = new Proxy({ requireAuth, localhostOrAuth }, {
  get(target, key) {
    if (key in target) return target[key]
    return (...args) => (args.length === 3 && typeof args[2] === 'function' ? args[2]() : _passthrough)
  },
})
const router = createSystemOpsRouter(deps)

function findRoute(method, pathname) {
  const layer = router.stack.find(l => l.route && l.route.path === pathname && l.route.methods[method.toLowerCase()])
  if (!layer) throw new Error(`route not found: ${method} ${pathname}`)
  return layer.route.stack
}

function run(stack, remoteAddress) {
  return new Promise((resolve) => {
    const req = { method: 'GET', headers: {}, query: {}, body: {}, socket: { remoteAddress }, connection: { remoteAddress } }
    const res = {
      statusCode: 200, _json: null,
      status(c) { this.statusCode = c; return this },
      json(o) { this._json = o; resolve({ status: this.statusCode }); return this },
      setHeader() {}, flushHeaders() {}, write() {}, setTimeout() {},
      end() { resolve({ status: this.statusCode }) },
    }
    let i = 0
    const next = () => { i < stack.length ? stack[i++].handle(req, res, next) : resolve({ status: res.statusCode }) }
    next()
  })
}

;(async () => {
  const updateStatus = findRoute('GET', '/api/system/update-status')

  // 1. Loopback, NO token → reaches handler (200), not 401. (the bug)
  assert.strictEqual((await run(updateStatus, '127.0.0.1')).status, 200)
  ok('loopback reaches /api/system/update-status WITHOUT a token (was 401)')

  // 2. Remote caller, NO token → still 401 (deny-by-default preserved).
  assert.strictEqual((await run(updateStatus, '8.8.8.8')).status, 401)
  ok('remote caller without a token is still 401')

  // 3. Bypass is scoped: settings endpoint stays JWT-only even from loopback.
  const settings = findRoute('GET', '/api/system/auto-update-settings')
  assert.strictEqual((await run(settings, '127.0.0.1')).status, 401)
  ok('auto-update-settings stays JWT-only from loopback (bypass scoped to update ops)')

  console.log(`\nupdate-endpoint-auth: ${passed} passed, 0 failed`)
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1) })
