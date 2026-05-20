const http = require('http')
const net = require('net')

function intEnv(...names) {
  for (const name of names) {
    const value = Number.parseInt(process.env[name] || '', 10)
    if (Number.isInteger(value) && value > 0) return value
  }
  return null
}

const DEFAULT_NODE_PORT = intEnv('PROBLEM_SOLVER_UI_PORT', 'PORT') || 8787
const DEFAULT_PYTHON_PORT = intEnv('PYTHON_BACKEND_PORT', 'AI_BACKEND_PORT') || 18790
const DEFAULT_UI_HOST = process.env.UI_HOST && process.env.UI_HOST !== '0.0.0.0'
  ? process.env.UI_HOST
  : '127.0.0.1'

let runtimeRoute = {
  nodePort: DEFAULT_NODE_PORT,
  pythonPort: DEFAULT_PYTHON_PORT,
  host: DEFAULT_UI_HOST,
  uiOrigin: process.env.UI_ORIGIN || `http://${DEFAULT_UI_HOST}:${DEFAULT_NODE_PORT}`,
  dashboardUrl: `${process.env.UI_ORIGIN || `http://${DEFAULT_UI_HOST}:${DEFAULT_NODE_PORT}`}/?electron=1`,
}

function configureRuntimeRoute(route = {}) {
  const nodePort = Number.parseInt(route.nodePort || route.node || route.port || runtimeRoute.nodePort, 10)
  const pythonPort = Number.parseInt(route.pythonPort || route.python || runtimeRoute.pythonPort, 10)
  const host = route.host || runtimeRoute.host || '127.0.0.1'
  const uiOrigin = route.uiOrigin || `http://${host}:${nodePort}`
  runtimeRoute = {
    nodePort,
    pythonPort,
    host,
    uiOrigin,
    dashboardUrl: route.dashboardUrl || `${uiOrigin}/?electron=1`,
    nonce: route.nonce || runtimeRoute.nonce || null,
  }
  return getRuntimeRoute()
}

function getRuntimeRoute() {
  return { ...runtimeRoute }
}

function getUIOrigin() {
  return runtimeRoute.uiOrigin
}

/**
 * Single HTTP probe with timeout. Resolves — never rejects.
 */
function httpProbe(url, timeoutMs = 2500) {
  return new Promise(resolve => {
    const req = http.get(url, { timeout: timeoutMs }, res => {
      let body = ''
      res.setEncoding('utf8')
      res.on('data', chunk => { if (body.length < 200000) body += chunk })
      res.on('end', () => resolve({
        ok: res.statusCode >= 200 && res.statusCode < 400,
        status: res.statusCode,
        body,
      }))
      res.resume()
    })
    req.on('timeout', () => {
      req.destroy()
      resolve({ ok: false, status: 0, body: '', error: 'timeout' })
    })
    req.on('error', err => resolve({ ok: false, status: 0, body: '', error: err.message }))
  })
}

/**
 * TCP-level port check — succeeds the moment the listener is up.
 * Much faster than waiting for the first HTTP/health response, useful for
 * detecting "node started" or "python started" the instant it happens.
 */
function tcpProbe(port, host = '127.0.0.1', timeoutMs = 1000) {
  return new Promise(resolve => {
    const sock = new net.Socket()
    let done = false
    const finish = (ok, err) => {
      if (done) return
      done = true
      try { sock.destroy() } catch {}
      resolve({ ok, error: err })
    }
    sock.setTimeout(timeoutMs)
    sock.once('connect', () => finish(true))
    sock.once('timeout', () => finish(false, 'timeout'))
    sock.once('error', err => finish(false, err.message))
    sock.connect(port, host)
  })
}

/**
 * Exponential-backoff waiter. Calls `probeFn` until it returns truthy
 * or the cap is reached. `delays` defines the backoff schedule (ms).
 */
async function waitFor(probeFn, { delays = [50, 100, 200, 500, 1000, 2000, 4000, 4000], capMs = 90000 } = {}) {
  const started = Date.now()
  let attempt = 0
  while (Date.now() - started < capMs) {
    const result = await probeFn()
    if (result && (result.ok === true || result === true)) {
      return { ok: true, attempts: attempt + 1, elapsedMs: Date.now() - started, last: result }
    }
    const delay = delays[Math.min(attempt, delays.length - 1)]
    await new Promise(r => setTimeout(r, delay))
    attempt++
  }
  return { ok: false, attempts: attempt, elapsedMs: Date.now() - started, last: null }
}

/** Wait for the Node gateway to bind the configured UI port.
 *  `crashCheck` is an optional () => string|null callback — if it returns a non-null string
 *  the wait aborts immediately with ok=false and a `crashed` flag. */
async function waitForNodePort(capMs = 60000, crashCheck = null) {
  return waitFor(
    async () => {
      if (crashCheck) {
        const reason = crashCheck()
        if (reason) return { ok: false, crashed: true, reason }
      }
      return tcpProbe(runtimeRoute.nodePort, runtimeRoute.host)
    },
    { capMs, delays: [100, 200, 300, 500, 1000, 2000, 4000, 4000] }
  )
}

/** Wait for the Python AI backend to bind the configured backend port. Returns ok=false on timeout
 *  but the launcher should not block — Python is optional (degraded mode). */
async function waitForPythonPort(capMs = 45000) {
  return waitFor(() => tcpProbe(runtimeRoute.pythonPort, runtimeRoute.host), { capMs })
}

/** Wait for /api/health to return 2xx. */
async function waitForHealth(capMs = 30000) {
  return waitFor(() => httpProbe(`${runtimeRoute.uiOrigin}/api/health`), { capMs })
}

/** Extract first 6 critical asset URLs (JS/CSS) from the dashboard HTML. */
function extractCriticalAssets(html, origin = runtimeRoute.uiOrigin) {
  const assets = new Set()
  const re = /(?:src|href)=["']([^"']*\/assets\/[^"']+\.(?:js|css))["']/g
  let match
  while ((match = re.exec(html))) {
    const url = match[1].startsWith('http') ? match[1] : `${origin}${match[1]}`
    assets.add(url)
  }
  return Array.from(assets).slice(0, 6)
}

/**
 * Full readiness check used to decide whether to even attempt openInterface.
 * Returns a structured result the diagnostic screen can render directly.
 */
async function checkReadiness() {
  const route = getRuntimeRoute()
  const checks = {
    node_port: false,
    python_port: false,
    health: false,
    api_health: false,
    readiness: false,
    index: false,
    assets: false,
  }
  const errors = []

  const nodeTcp = await tcpProbe(route.nodePort, route.host)
  checks.node_port = nodeTcp.ok
  if (!nodeTcp.ok) errors.push(`Node port :${route.nodePort} not bound (${nodeTcp.error || 'no listener'})`)

  const pyTcp = await tcpProbe(route.pythonPort, route.host)
  checks.python_port = pyTcp.ok

  const health = await httpProbe(`${route.uiOrigin}/health`, 2000)
  checks.health = health.ok
  const apiHealth = await httpProbe(`${route.uiOrigin}/api/health`, 2500)
  checks.api_health = apiHealth.ok
  const identityProbe = await httpProbe(`${route.uiOrigin}/api/runtime/identity`, 2500)
  checks.identity = identityProbe.ok
  let identity = null
  if (identityProbe.ok) {
    try { identity = JSON.parse(identityProbe.body) } catch {}
  }
  const readinessProbe = await httpProbe(`${route.uiOrigin}/api/readiness`, 3000)
  checks.readiness = readinessProbe.ok
  let readiness = null
  if (readinessProbe.ok) {
    try { readiness = JSON.parse(readinessProbe.body) } catch {}
  }
  if (readiness?.pythonReady) checks.python_port = true

  const index = await httpProbe(`${route.uiOrigin}/`, 3000)
  checks.index = index.ok && /<div[^>]+id=["']root["']/.test(index.body)
  if (!checks.index) errors.push(`Dashboard HTML missing root div (${index.status || index.error || 'no response'})`)

  let assets = []
  if (checks.index) {
    assets = extractCriticalAssets(index.body, route.uiOrigin)
    if (assets.length === 0) {
      checks.assets = true
    } else {
      const probed = await Promise.all(assets.map(u => httpProbe(u, 3000)))
      checks.assets = probed.every(r => r.ok)
      if (!checks.assets) {
        const failed = probed.findIndex(r => !r.ok)
        errors.push(`Asset unavailable: ${assets[failed]} (${probed[failed].status || probed[failed].error})`)
      }
    }
  }

  const backendReady = checks.health || checks.api_health
  const ready = backendReady && checks.index && checks.assets
  const degraded = !backendReady && checks.index && checks.assets

  return {
    ready,
    degraded,
    checks,
    readiness,
    identity,
    route,
    errors,
    summary: ready ? 'Ready' : degraded ? 'Ready (degraded — backend health failing)' : (errors[0] || 'Not ready'),
  }
}

module.exports = {
  UI_ORIGIN: runtimeRoute.uiOrigin,
  NODE_PORT: runtimeRoute.nodePort,
  PYTHON_PORT: runtimeRoute.pythonPort,
  configureRuntimeRoute, getRuntimeRoute, getUIOrigin,
  httpProbe, tcpProbe, waitFor,
  waitForNodePort, waitForPythonPort, waitForHealth,
  checkReadiness, extractCriticalAssets,
}
