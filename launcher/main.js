// Bootstrap logger FIRST — every boot leaves a trail on disk, even if Electron
// fails to spawn a window. Any future "doesn't load" report becomes triagable.
const { log } = require('./src/log')

// Defensive guard: if ELECTRON_RUN_AS_NODE is set, electron will execute this
// file as plain Node and `require('electron')` returns the binary path string
// — every Electron API access then throws. This is a common shell-config trap
// (some users set it for tooling). Log clearly and exit instead of crashing.
if (process.env.ELECTRON_RUN_AS_NODE === '1') {
  log.error('ELECTRON_RUN_AS_NODE=1 is set — Electron is running as plain Node. ' +
            'Unset it (`unset ELECTRON_RUN_AS_NODE`) and re-run, or run with ' +
            '`env -u ELECTRON_RUN_AS_NODE npm start`.')
  process.exit(2)
}

const electron = require('electron')
if (!electron || typeof electron === 'string' || !electron.app) {
  log.error('require(\'electron\') did not return the Electron API. ' +
            'This usually means main.js is running under plain Node instead of ' +
            'the Electron binary. Check that you launched via `npm start` (which ' +
            'runs `electron .`), not `node main.js`.')
  process.exit(3)
}
const { app, BrowserWindow, ipcMain, shell, clipboard, screen } = electron
const path = require('path')
const fs = require('fs')

function clearGpuShaderCaches() {
  const removed = []
  try {
    const roots = [
      app.getPath('userData'),
      process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || null,
    ].filter(Boolean)
    const names = ['GPUCache', 'ShaderCache', 'DawnCache']
    for (const root of roots) {
      for (const name of names) {
        const target = path.join(root, name)
        if (!fs.existsSync(target)) continue
        fs.rmSync(target, { recursive: true, force: true })
        removed.push(target)
      }
    }
  } catch (e) {
    log.warn(`GPU shader cache cleanup failed: ${e.message}`)
  }
  if (removed.length) log.info(`GPU shader cache cleared (${removed.length} director${removed.length === 1 ? 'y' : 'ies'})`)
}

// Capture Chromium internals to disk so renderer crashes/GPU init failures
// are visible without DevTools.
try {
  const os = require('os')
  const chromiumLog = path.join(
    process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'),
    'logs', 'electron.log'
  )
  app.commandLine.appendSwitch('enable-logging')
  app.commandLine.appendSwitch('log-file', chromiumLog)
  log.info(`chromium log → ${chromiumLog}`)
} catch (e) { log.warn('failed to wire chromium logging:', e.message) }

// ── WebGL stability (in-app controllable) ────────────────────────────────────
// The dashboard/neural pages render a heavy three.js scene. On Linux+Electron the
// GPU WebGL context was being LOST ("THREE.WebGLRenderer: Context Lost"), crashing
// every 3D page. The mode is set from INSIDE the app (Settings → Display), persisted
// to ~/.ai-employee/config/render-prefs.json, and read here before app.ready:
//   auto     — hardware first, SwiftShader software fallback always allowed (default)
//   hardware — trust the GPU (no forced software), fallback still permitted
//   software — force SwiftShader software rendering (most stable, slower)
try {
  const { getRenderMode } = require('./src/render-prefs')
  const mode = getRenderMode()
  app.commandLine.appendSwitch('ignore-gpu-blocklist')
  app.commandLine.appendSwitch('enable-gpu-rasterization')
  app.commandLine.appendSwitch('disable-gpu-process-crash-limit')
  app.commandLine.appendSwitch('enable-unsafe-swiftshader')   // software WebGL fallback
  if (mode === 'software') {
    app.commandLine.appendSwitch('use-gl', 'angle')
    app.commandLine.appendSwitch('use-angle', 'swiftshader')
    log.info('WebGL: SwiftShader software rendering (mode=software)')
  } else {
    log.info(`WebGL: mode=${mode}`)
  }
} catch (e) { log.warn('failed to set WebGL flags:', e.message) }

const { PATHS } = require('./src/paths')
const { BackendManager } = require('./src/backend')
const health = require('./src/health')
const { checkReadiness, waitForNodePort, waitForHealth, waitForPythonPort } = health
const { tracker, PHASES, PHASE_LABELS } = require('./src/phases')
const updater = require('./src/update')
const { loadPolicy } = require('./src/policy')
const { checkFirstBoot, writeSetupComplete, checkAndFixNativeModules, resolvePython } = require('./src/first_boot')

// ── Constants ─────────────────────────────────────────────────────────
const HTML_LOAD_TIMEOUT_MS    = 8000     // BrowserWindow.loadURL → did-finish-load (tight: html arrives fast or backend is wedged)
const REACT_RENDER_TIMEOUT_MS = 45000    // did-finish-load → react-rendered ping (soft warning, not failure)
const REACT_MOUNT_TIMEOUT_MS  = 15000    // react-rendered → react-mounted ping (warn-and-continue; window is already visible)
const READINESS_CAP_MS        = 90000    // exponential backoff on health
const MAX_LOAD_RETRIES        = 1        // auto-reload once before diagnostics

// ── State ─────────────────────────────────────────────────────────────
let launcherWindow = null
let appWindow = null
let loadAttempts = 0
let timers = { html: null, render: null, mount: null }

const backend = new BackendManager()
try {
  const lock = JSON.parse(fs.readFileSync(path.join(PATHS.runDir, 'runtime-lock.json'), 'utf8'))
  if (lock?.ports?.node && lock?.uiOrigin) {
    health.configureRuntimeRoute({
      nodePort: lock.ports.node,
      pythonPort: lock.ports.python,
      uiOrigin: lock.uiOrigin,
      dashboardUrl: lock.dashboardUrl,
      nonce: lock.nonce,
    })
    log.info(`loaded runtime route from lock: ${lock.dashboardUrl || lock.uiOrigin}`)
  }
} catch {}
let launchStatus = {
  state: 'idle',
  phase: 'idle',
  message: 'Launcher ready',
  lastError: null,
  updatedAt: Date.now(),
}

function acquireSingletonLock() {
  const lock = app.requestSingleInstanceLock()
  if (lock) return true
  log.warn('singleton lock held by another launcher instance — exiting secondary process')
  return false
}

if (!acquireSingletonLock()) {
  app.quit()
} else {
  log.info('singleton lock acquired')
  app.on('second-instance', () => {
    log.info('second-instance event received — focusing existing window')
    const win = appWindow && !appWindow.isDestroyed() ? appWindow : launcherWindow
    if (!win || win.isDestroyed()) return
    if (win.isMinimized()) win.restore()
    win.show()
    win.focus()
  })
}

// ── Helpers ───────────────────────────────────────────────────────────
function sendToLauncher(channel, ...args) {
  if (launcherWindow && !launcherWindow.isDestroyed()) {
    launcherWindow.webContents.send(channel, ...args)
  }
}

function setStatus(patch = {}) {
  launchStatus = { ...launchStatus, ...patch, updatedAt: Date.now() }
  sendToLauncher('ui-load-status', launchStatus)
}

function clearTimers() {
  for (const k of Object.keys(timers)) {
    if (timers[k]) { clearTimeout(timers[k]); timers[k] = null }
  }
}

function broadcastPhase(entry) {
  sendToLauncher('phase', entry)
}

// Fetch Python subsystem startup timings and forward them to the renderer.
// Each timing renders as a row in the boot console under a PYTHON SUBSYSTEMS header.
function fetchPythonSubsystemTimings() {
  const http = require('http')
  const req = http.request(
    `${health.getUIOrigin()}/api/system/startup-timings`,
    { method: 'GET', timeout: 3000 },
    (res) => {
      let data = ''
      res.on('data', (c) => { data += c })
      res.on('end', () => {
        try {
          const payload = JSON.parse(data || '{}')
          const timings = Array.isArray(payload.timings) ? payload.timings : []
          if (timings.length) {
            sendToLauncher('python-subsystems', { timings })
            log.info(`forwarded ${timings.length} python subsystem timings to launcher`)
          }
        } catch (e) { log.warn(`python timings parse failed: ${e.message}`) }
      })
    }
  )
  req.on('error', (e) => log.warn(`python timings fetch failed: ${e.message}`))
  req.on('timeout', () => { req.destroy() })
  req.end()
}

// ── Boot metrics persistence ──────────────────────────────────────────
// After the last canonical phase fires, persist a record to state/boot_metrics.json.
// Keeps last 20 records; atomic write via .tmp+rename; never throws into the boot path.
const BOOT_METRICS_MAX = 20
const COLD_BOOT_GAP_MS = 30 * 60 * 1000 // 30 min since last boot → cold
let bootStartedAtIso = null
tracker.on('reset', () => { bootStartedAtIso = new Date().toISOString() })

function persistBootMetrics() {
  try {
    const summary = tracker.summary()
    const finishedAt = Date.now()
    const file = path.join(PATHS.repoDir, 'state', 'boot_metrics.json')
    let prev = []
    try {
      if (fs.existsSync(file)) {
        const parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
        if (Array.isArray(parsed)) prev = parsed
        else if (Array.isArray(parsed?.records)) prev = parsed.records
      }
    } catch (e) { log.warn(`boot_metrics: prior file unreadable (${e.message}) — starting fresh`) }

    const lastFinished = prev[0]?.finished_at ? Date.parse(prev[0].finished_at) : 0
    const cold = !lastFinished || (finishedAt - lastFinished) > COLD_BOOT_GAP_MS

    const record = {
      boot_id: `${finishedAt}-${Math.random().toString(36).slice(2, 8)}`,
      started_at: bootStartedAtIso || new Date(finishedAt - summary.total_ms).toISOString(),
      finished_at: new Date(finishedAt).toISOString(),
      total_ms: summary.total_ms,
      cold,
      phases: summary.phases,
    }
    const next = [record, ...prev].slice(0, BOOT_METRICS_MAX)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    const tmp = `${file}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(next, null, 2))
    fs.renameSync(tmp, file)
    log.info(`boot_metrics: wrote record total=${summary.total_ms}ms cold=${cold} (${next.length} kept)`)
  } catch (e) {
    log.warn(`boot_metrics: persist failed (${e.message}) — non-fatal`)
  }
}

const FINAL_PHASE = PHASES[PHASES.length - 1]
tracker.on('phase', (entry) => {
  if (entry.phase === FINAL_PHASE) persistBootMetrics()
})

tracker.on('phase', broadcastPhase)
tracker.on('fail', (entry) => sendToLauncher('phase:fail', entry))
backend.on('log', (entry) => sendToLauncher('start-log', entry.line))

// Backend crash auto-restart — only triggers if BOTH of these are true:
//   1. The backend previously reached "backend-ready" (we know it was up)
//   2. After start.sh exit, /api/health no longer responds (services dead)
//
// CRITICAL: start.sh exits CLEANLY (code 0) after spawning services — that's
// normal, not a crash. The v5 first-cut treated every start.sh exit as a
// crash and locked the launcher into the "auto-restart disabled" state after
// 3 false-positives. The fix: probe health post-exit and only treat as crash
// if services are actually dead.
const MAX_RESTARTS = 3
let restartCount = 0
let lastBackendUpTs = 0
backend.on('exit', async ({ code, expected }) => {
  log.info(`backend exited (code=${code}, expected=${expected})`)
  if (expected) {
    restartCount = 0
    sendToLauncher('backend-state', { state: 'stopped', expected: true })
    return
  }
  // Post-exit health probe — if services are still up, exit was a clean
  // handoff (start.sh spawned services then returned). NOT a crash.
  try {
    const { httpProbe, waitFor, getUIOrigin } = require('./src/health')
    const probe = await waitFor(() => httpProbe(`${getUIOrigin()}/api/health`, 3000), {
      delays: [500, 1000, 2000, 4000, 4000, 4000],
      capMs: 15000,
    })
    if (probe.ok) {
      log.info('backend exit was a clean handoff — /api/health still responding')
      restartCount = 0
      lastBackendUpTs = Date.now()
      sendToLauncher('backend-state', { state: 'running', expected: false })
      return
    }
  } catch { /* fall through to crash handling */ }

  // Only auto-restart if we actually saw the backend up before
  if (lastBackendUpTs === 0) {
    log.warn('backend exited before reaching backend-ready — not auto-restarting')
    sendToLauncher('backend-state', { state: 'failed', expected: false })
    return
  }
  // Reset counter if backend ran cleanly for >60s before this exit
  if ((Date.now() - lastBackendUpTs) > 60000) restartCount = 0
  if (restartCount >= MAX_RESTARTS) {
    log.error(`backend crashed ${restartCount}× — giving up auto-restart`)
    sendToLauncher('backend-state', { state: 'crashed', restartCount })
    showDiagnostics(`Backend has crashed ${restartCount} times in a row. Auto-restart disabled. Use RESTART WITH VERBOSE to diagnose.`)
    return
  }
  restartCount++
  log.warn(`backend crash detected — auto-restart attempt ${restartCount}/${MAX_RESTARTS}`)
  sendToLauncher('backend-state', { state: 'restarting', restartCount })
  setTimeout(() => {
    backend.start({}).catch((err) => log.error('auto-restart failed:', err.message))
  }, 1500 * restartCount)
})
backend.on('milestone', ({ phase }) => {
  if (phase === 'backend-ready') lastBackendUpTs = Date.now()
})

// Reset restart counter on any user-initiated restart action so the user
// isn't locked into "auto-restart disabled" after old false-positive crashes.
function resetRestartCounter() { restartCount = 0; lastBackendUpTs = 0 }

// ── Diagnostics ───────────────────────────────────────────────────────
function buildDiagnostics(extraMessage = null) {
  const firstBoot = checkFirstBoot()
  let runtimeLock = null
  try { runtimeLock = JSON.parse(fs.readFileSync(path.join(PATHS.runDir, 'runtime-lock.json'), 'utf8')) } catch {}
  return {
    message: extraMessage,
    launchStatus,
    runtimeRoute: health.getRuntimeRoute(),
    runtimeLock,
    platform: {
      os: process.platform,
      arch: process.arch,
      packaged: app.isPackaged,
      electron: process.versions.electron,
      node: process.versions.node,
      resourcesPath: process.resourcesPath || null,
    },
    phases: tracker.snapshot(),
    logs: backend.tailLogs(20),
    logFiles: ['python-backend.log', 'server.log', 'launcher-start.log'].map(name => {
      const file = path.join(PATHS.logDir, name)
      let bytes = 0
      try { bytes = fs.statSync(file).size } catch {}
      return { name, bytes, path: file }
    }),
    paths: {
      repoDir: PATHS.repoDir,
      appHome: PATHS.appHome,
      stateDir: PATHS.stateDir,
      logDir: PATHS.logDir,
      runDir: PATHS.runDir,
    },
    policy: loadPolicy(),
    firstBoot,
  }
}

function showDiagnostics(message, extras = {}) {
  clearTimers()
  if (appWindow && !appWindow.isDestroyed()) {
    appWindow.close()
  }
  appWindow = null
  loadAttempts = 0
  setStatus({ state: 'failed', message: 'Dashboard load failed', lastError: message })
  const payload = buildDiagnostics(message)
  if (launcherWindow && !launcherWindow.isDestroyed()) {
    launcherWindow.show()
    launcherWindow.focus()
    launcherWindow.webContents.send('ui-load-failed', { message, diagnostics: payload, ...extras })
  }
}

// ── Launcher window ───────────────────────────────────────────────────
// IMPORTANT: opaque + show-on-ready. Transparent + frameless windows render
// invisible on non-composited X sessions (the v2 cause of "won't load"). Set
// AI_LAUNCHER_TRANSPARENT=1 to opt back into transparency on systems that
// definitely have a compositor.
function createLauncherWindow() {
  const wantTransparent = process.env.AI_LAUNCHER_TRANSPARENT === '1'
  log.info(`creating launcher window (transparent=${wantTransparent})`)
  launcherWindow = new BrowserWindow({
    width: 800,
    height: 620,
    frame: false,
    transparent: wantTransparent,
    resizable: false,
    show: false, // wait for ready-to-show to avoid the empty-frame flash
    backgroundColor: wantTransparent ? '#00000000' : '#06070d',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    title: 'AETERNUS NEXUS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  })

  launcherWindow.once('ready-to-show', () => {
    log.info('launcher window ready-to-show')
    launcherWindow.show()
    launcherWindow.focus()
  })

  // Safety net: if ready-to-show doesn't fire within 4 s (e.g. preload crashed),
  // force-show the window so the user always sees the app exists. The dark
  // background guarantees something visible even if the renderer is blank.
  setTimeout(() => {
    if (launcherWindow && !launcherWindow.isDestroyed() && !launcherWindow.isVisible()) {
      log.warn('ready-to-show did not fire within 4s; force-showing')
      launcherWindow.show()
      launcherWindow.focus()
    }
  }, 4000)

  launcherWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
    log.error(`renderer did-fail-load (${code}): ${desc} url=${url}`)
    if (launcherWindow && !launcherWindow.isDestroyed()) launcherWindow.show()
  })
  launcherWindow.webContents.on('render-process-gone', (_e, details) => {
    log.error(`renderer process gone: ${details.reason} exitCode=${details.exitCode}`)
  })
  launcherWindow.webContents.on('preload-error', (_e, preload, err) => {
    log.error(`preload error in ${preload}:`, err)
  })
  launcherWindow.webContents.on('console-message', (_e, level, message, line, source) => {
    // Mirror renderer console errors to launcher.log
    if (level >= 2) log.warn(`[renderer:${level}] ${message} (${source}:${line})`)
  })

  launcherWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
    .catch(err => log.error('loadFile failed:', err))

  launcherWindow.on('closed', () => {
    log.info('launcher window closed')
    launcherWindow = null
  })
}

// ── Dashboard window: open with adaptive timeouts + auto-retry ────────
function attachDashboardEvents(win, readiness) {
  clearTimers()

  // Phase 1: HTML load
  timers.html = setTimeout(() => {
    handleLoadFailure('html-load-timeout', readiness)
  }, HTML_LOAD_TIMEOUT_MS)

  win.webContents.once('did-finish-load', () => {
    if (timers.html) { clearTimeout(timers.html); timers.html = null }
    tracker.complete('html-loaded')
    tracker.start('react-rendered')
    setStatus({ state: 'ui-loading', phase: 'html-loaded', message: 'Dashboard HTML loaded' })

    // v4: SHOW THE DASHBOARD WINDOW NOW. We do not gate visibility on the
    // React-side `notifyUiBootPhase('react-rendered')` handshake because that
    // handshake silently fails when window.ai is undefined in the dashboard
    // renderer (preload not running / CSP / etc.). The backend is observably
    // serving HTTP 200 — show the user what's there. The React signal is
    // still wanted as a richer "fully mounted" indicator, but the window is
    // no longer hidden waiting for it.
    log.info('did-finish-load fired — showing dashboard window')
    showDashboardWindow()

    // Stream Python subsystem timings into the launcher boot console so a slow
    // subsystem (>2 s amber, >5 s red) is visible at a glance. Fire-and-forget;
    // never block the boot path.
    setTimeout(() => fetchPythonSubsystemTimings(), 1500)

    // Phase 2 (soft): React first paint. Timeout = warning, not failure.
    timers.render = setTimeout(() => {
      log.warn(`react-rendered ping not received after ${REACT_RENDER_TIMEOUT_MS}ms — marking phase done with degraded note`)
      tracker.complete('react-rendered')
      setStatus({ state: 'ui-mounted', phase: 'react-rendered', message: 'Dashboard live (react-rendered handshake missing — preload may not be injecting)' })
      // Still start the mount timer so the rail advances naturally
      timers.mount = setTimeout(() => {
        tracker.complete('react-mounted')
        setStatus({ state: 'ui-mounted', phase: 'react-mounted', message: 'Dashboard live (mount handshake missing)' })
      }, REACT_MOUNT_TIMEOUT_MS)
    }, REACT_RENDER_TIMEOUT_MS)
  })

  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    // -3 / ABORTED happens during reload; ignore it
    if (code === -3) return
    log.error(`appWindow did-fail-load (${code}): ${desc} url=${url}`)
    handleLoadFailure(`HTTP load failed (${code}): ${desc || url}`, readiness)
  })

  win.webContents.on('render-process-gone', (_e, details) => {
    log.error(`appWindow renderer process gone: ${details.reason} exitCode=${details.exitCode}`)
    handleLoadFailure(`Dashboard renderer crashed: ${details.reason}`, readiness)
  })

  // v4 Step 5: surface preload-error + renderer console errors so any failure
  // inside the dashboard reaches launcher.log.
  win.webContents.on('preload-error', (_e, preload, err) => {
    log.error(`appWindow PRELOAD ERROR in ${preload}:`, err)
  })
  // Track recent console errors so we can self-heal on a single chunk hiccup
  let _rendererHardError = null
  let _rendererSelfHealed = false
  win.webContents.on('console-message', (_e, level, message, line, source) => {
    if (level >= 2) log.warn(`[dash-renderer:${level}] ${message} (${source}:${line})`)
    // Detect chunk-level crashes — stale bundle, missing import, syntax bug.
    // One auto-reload with a fresh cache fixes 99% of these without user action.
    if (level >= 2 && !_rendererSelfHealed && /Uncaught (TypeError|SyntaxError)|ChunkLoadError|Loading chunk \d+ failed/.test(message)) {
      _rendererHardError = { message, source, line, ts: Date.now() }
    }
  })
  // Give the error 800 ms to materialize after did-finish-load. If one appeared,
  // clear the HTTP cache and reload once. Subsequent errors are user-visible.
  win.webContents.once('did-finish-load', () => {
    setTimeout(async () => {
      if (_rendererHardError && !_rendererSelfHealed && win && !win.isDestroyed()) {
        _rendererSelfHealed = true
        log.warn(`renderer hard error detected — self-healing reload: ${_rendererHardError.message}`)
        try {
          await win.webContents.session.clearCache()
        } catch (e) { log.warn(`clearCache during self-heal failed: ${e.message}`) }
        try {
          win.webContents.reloadIgnoringCache()
        } catch (e) { log.warn(`reload during self-heal failed: ${e.message}`) }
      }
    }, 800)
  })

  win.on('unresponsive', () => {
    log.warn('appWindow became unresponsive')
    handleLoadFailure('Dashboard window became unresponsive', readiness)
  })

  win.on('closed', () => {
    log.info('appWindow closed')
    clearTimers()
    appWindow = null
    if (launcherWindow && !launcherWindow.isDestroyed()) launcherWindow.show()
  })
}

async function handleLoadFailure(reason, readiness) {
  clearTimers()
  if (loadAttempts < MAX_LOAD_RETRIES && appWindow && !appWindow.isDestroyed()) {
    loadAttempts++
    setStatus({ state: 'retrying', message: `Reload attempt ${loadAttempts} (${reason})` })
    backend.appendLog(`[launcher] reload attempt ${loadAttempts}: ${reason}`, 'warn')
    try {
      await appWindow.webContents.reload()
      attachDashboardEvents(appWindow, readiness)
      await appWindow.loadURL(health.getRuntimeRoute().dashboardUrl)
      return
    } catch (e) {
      // fall through to diagnostics
      reason = `${reason} (reload also failed: ${e.message})`
    }
  }
  tracker.fail(tracker.current || 'react-rendered', reason)
  showDiagnostics(reason, { readiness })
}

function onReactRendered() {
  if (timers.render) { clearTimeout(timers.render); timers.render = null }
  tracker.complete('react-rendered')
  tracker.start('react-mounted')
  setStatus({ state: 'ui-loading', phase: 'react-rendered', message: 'React rendered — waiting for full mount' })

  // Phase 3: full mount (optional — show the window now anyway)
  showDashboardWindow()

  timers.mount = setTimeout(() => {
    // Mount didn't fully complete, but window is already shown. Not a failure;
    // just complete the phase so the rail looks finished.
    tracker.complete('react-mounted')
    setStatus({ state: 'ui-mounted', phase: 'react-mounted', message: 'Dashboard live (full mount handshake not received)' })
  }, REACT_MOUNT_TIMEOUT_MS)
}

function onReactMounted(payload) {
  clearTimers()
  tracker.complete('react-mounted')
  setStatus({ state: 'ui-mounted', phase: 'react-mounted', message: payload?.message || 'Dashboard fully mounted', lastError: null })
  showDashboardWindow()
}

function showDashboardWindow() {
  if (!appWindow || appWindow.isDestroyed()) return
  if (appWindow.isVisible()) return
  if (launcherWindow && !launcherWindow.isDestroyed()) launcherWindow.hide()
  appWindow.show()
  appWindow.focus()
}

async function openInterface() {
  // Reset state for a fresh attempt
  tracker.reset()
  for (const p of ['deps-check', 'backend-spawn', 'node-port-bound', 'health-ok']) {
    if (launchStatus.state !== 'idle') { tracker.start(p); tracker.complete(p) } // assume completed if we got here from a running system
  }

  log.info('openInterface: starting')
  setStatus({ state: 'checking', phase: 'health-ok', message: 'Click received — verifying dashboard readiness', lastError: null })

  // Quick readiness check before opening the window
  let readiness = await checkReadiness()
  if (!readiness.ready && !readiness.degraded) {
    log.warn('openInterface: runtime not ready; starting unified runtime route first')
    await startSystem(null, { skipExisting: true })
    readiness = await checkReadiness()
  }
  if (!readiness.ready && !readiness.degraded) {
    tracker.fail('health-ok', readiness.errors[0] || 'Dashboard not ready')
    showDiagnostics(readiness.errors[0] || 'Dashboard not ready', { readiness })
    throw new Error(readiness.errors[0] || 'Dashboard not ready')
  }
  tracker.complete('health-ok')

  // Re-use an existing window if alive
  if (appWindow && !appWindow.isDestroyed()) {
    appWindow.show()
    appWindow.focus()
    return { success: true, existing: true, readiness }
  }

  loadAttempts = 0
  tracker.start('window-create')
  const primary = screen.getPrimaryDisplay()
  const { width, height } = primary.workAreaSize
  appWindow = new BrowserWindow({
    width,
    height,
    show: false,
    backgroundColor: '#050608',
    fullscreen: false,
    fullscreenable: false,  // prevents OS F11 + GPU context loss on Linux
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
      backgroundThrottling: false,  // prevents WebGL context loss on minimize/hide
    },
  })

  // Intercept F11 before it reaches the renderer — fullscreen is disabled for
  // this window because fullscreen transitions on Linux tear all WebGL contexts.
  appWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type === 'keyDown' && input.key === 'F11') {
      event.preventDefault()
    }
  })

  tracker.complete('window-create')
  tracker.start('html-loaded')
  setStatus({ state: 'ui-loading', phase: 'window-create', message: readiness.degraded ? 'Opening dashboard (degraded)' : 'Opening dashboard', lastError: null })

  attachDashboardEvents(appWindow, readiness)
  log.info('openInterface: created appWindow, loading dashboard URL')
  await appWindow.loadURL(health.getRuntimeRoute().dashboardUrl)
  return { success: true, readiness }
}

// ── Start system: spawn start.sh + watch for port-bound milestones ────
async function startSystem(event, { extraEnv = {}, skipExisting = true } = {}) {
  tracker.reset()

  // ── Pre-flight: fast env + binary checks before anything is spawned ──
  tracker.start('preflight')
  setStatus({ state: 'starting', phase: 'preflight', message: 'Running pre-flight checks', lastError: null })

  const preflightEnv = backend.buildEnv(extraEnv)
  const jwtKey = preflightEnv.JWT_SECRET_KEY || process.env.JWT_SECRET_KEY
  if (!jwtKey) {
    tracker.fail('preflight', 'JWT_SECRET_KEY could not be generated or loaded')
    showDiagnostics('JWT_SECRET_KEY could not be generated or loaded. Check the launcher app-home permissions and retry.')
    return { success: false }
  }

  const python = resolvePython()
  if (!python.command) {
    tracker.fail('preflight', 'Python 3 not found — install Python 3.10+')
    showDiagnostics('Python 3 not found. Install Python 3.10+ and retry.')
    return { success: false }
  }

  log.info(`preflight OK: python=${python.command} jwt_key=set`)
  tracker.complete('preflight')

  tracker.start('deps-check')
  setStatus({ state: 'starting', phase: 'deps-check', message: 'Verifying dependencies', lastError: null })

  // Auto-fix native module ABI mismatch before the backend is spawned.
  // Runs synchronously on first boot / after npm install; fast no-op if already compatible.
  try {
    const nativeCheck = checkAndFixNativeModules(PATHS.repoDir)
    if (nativeCheck.rebuilt) log.info('native modules rebuilt for Electron node ABI')
    else if (!nativeCheck.ok) log.warn(`native module check failed: ${nativeCheck.reason}`)
    else log.info(`native modules OK (${nativeCheck.reason})`)
  } catch (e) {
    log.warn(`native module check threw: ${e.message}`)
  }

  log.info('running first-boot check...')
  const firstBoot = checkFirstBoot()
  log.info(`first-boot result: ready=${firstBoot.local_runtime_ready} missing=[${(firstBoot.missing || []).join(',')}]`)
  if (!firstBoot.local_runtime_ready) {
    const message = `Local runtime is incomplete: ${firstBoot.missing.join(', ')}`
    tracker.fail('deps-check', message)
    showDiagnostics(message, { firstBoot })
    return { success: false }
  }
  tracker.complete('deps-check')

  // Skip-if-running: if Node port already bound and health responds, treat as ready
  if (skipExisting) {
    log.info('checking existing system readiness...')
    const existing = await checkReadiness()
    if ((existing.ready || existing.degraded) && existing.checks.python_port) {
      tracker.start('backend-spawn');     tracker.complete('backend-spawn')
      tracker.start('node-port-bound');   tracker.complete('node-port-bound')
      if (existing.checks.python_port) { tracker.start('python-port-bound'); tracker.complete('python-port-bound') }
      tracker.start('health-ok');         tracker.complete('health-ok')
      setStatus({ state: 'backend-ready', phase: 'health-ok', message: existing.degraded ? 'System running (degraded)' : 'System already running', lastError: existing.degraded ? existing.errors[0] : null })
      lastBackendUpTs = Date.now()
      event?.sender?.send('start-ready', existing)
      return { success: true, alreadyRunning: true, readiness: existing }
    }
    if (existing.ready || existing.degraded) {
      log.warn('Existing Node gateway is reachable but Python backend is not; restarting full stack')
      tracker.start('process-cleanup')
      setStatus({ state: 'starting', phase: 'process-cleanup', message: 'Killing stale processes (waiting for ports to free)' })
      backend.appendLog('[launcher] Killing stale processes before fresh start', 'warn')
      backend.cancel()
      await new Promise(r => setTimeout(r, 2000))
      log.info('stale processes cancelled — proceeding with fresh start')
      tracker.complete('process-cleanup')
    }
  }

  // Spawn start.sh (fire and don't await — we wait on port-bound instead)
  tracker.start('backend-spawn')
  setStatus({ state: 'starting', phase: 'backend-spawn', message: 'Spawning backend services' })
  const launchResult = await backend.start({ extraEnv }).catch(err => ({ error: err }))
  if (launchResult?.error) {
    tracker.fail('backend-spawn', launchResult.error.message)
    showDiagnostics(`Runtime failed to spawn: ${launchResult.error.message}`)
    return { success: false }
  }
  if (launchResult?.ports) {
    health.configureRuntimeRoute({
      nodePort: launchResult.ports.node,
      pythonPort: launchResult.ports.python,
      uiOrigin: launchResult.uiOrigin,
      dashboardUrl: launchResult.dashboardUrl,
      nonce: launchResult.nonce,
    })
  }
  tracker.complete('backend-spawn')

  // Crash latch: if Node exits with non-zero code before the port binds, fail fast.
  let _nodeCrashReason = null
  backend.once('child-exit', ({ name, code }) => {
    if (name === 'node' && code !== 0 && !_nodeCrashReason) {
      _nodeCrashReason = `Node process exited (code ${code}) — check ~/.ai-employee/logs/server.log`
    }
  })

  // Wait for Node gateway (required)
  tracker.start('node-port-bound')
  setStatus({ state: 'starting', phase: 'node-port-bound', message: 'Waiting for Node gateway...' })
  const nodeBound = await waitForNodePort(60000, () => _nodeCrashReason)
  if (!nodeBound.ok) {
    const route = health.getRuntimeRoute()
    const reason = _nodeCrashReason || `Node :${route.nodePort} never bound after ${Math.round(nodeBound.elapsedMs / 1000)}s`
    tracker.fail('node-port-bound', reason)
    showDiagnostics(`${reason}\n\nCheck: ~/.ai-employee/logs/server.log`)
    return { success: false }
  }
  tracker.complete('node-port-bound')

  // Wait for Python AI backend (optional — degraded if missing)
  const pyStartTs = Date.now()
  const pyPort = health.getRuntimeRoute().pythonPort
  tracker.start('python-port-bound')
  setStatus({ state: 'starting', phase: 'python-port-bound', message: `Starting Python AI backend on :${pyPort}...` })
  const pyElapsedTimer = setInterval(() => {
    const elapsed = Math.round((Date.now() - pyStartTs) / 1000)
    setStatus({ state: 'starting', phase: 'python-port-bound', message: `Starting Python AI backend on :${pyPort}... (${elapsed}s — cold start can take 20s)` })
    log.info(`still waiting for Python port :${pyPort} (${elapsed}s elapsed)`)
  }, 5000)
  const pyBound = await waitForPythonPort(45000)
  clearInterval(pyElapsedTimer)
  if (pyBound.ok) tracker.complete('python-port-bound')
  else log.warn(`Python port :${pyPort} never bound — continuing in degraded mode`)

  // Wait for /api/health
  tracker.start('health-ok')
  setStatus({ state: 'starting', phase: 'health-ok', message: 'Probing health endpoints' })
  // NB: local must NOT be named `health` — that shadows the module-level `health`
  // (require('./src/health')) across this whole function and TDZ-crashes the earlier
  // health.configureRuntimeRoute()/getRuntimeRoute() calls. (Fixes restart-verbose.)
  const healthProbe = await waitForHealth(30000)
  if (!healthProbe.ok) {
    tracker.fail('health-ok', `/api/health never returned 2xx after ${Math.round(healthProbe.elapsedMs / 1000)}s`)
    showDiagnostics('Backend started but /api/health is not responding. The system may be in a degraded state.')
    return { success: false }
  }
  tracker.complete('health-ok')

  const finalReadiness = await checkReadiness()
  const nodeUp   = finalReadiness.checks?.api_health || finalReadiness.checks?.health
  const pythonUp = finalReadiness.checks?.python_port
  const aiCore   = finalReadiness.readiness?.neuralBrainReady && finalReadiness.readiness?.graphReady

  if (nodeUp && pythonUp && aiCore) {
    setStatus({ state: 'backend-ready', phase: 'health-ok', message: 'System online', lastError: null })
  } else if (nodeUp && pythonUp) {
    setStatus({
      state: 'backend-ready', phase: 'health-ok',
      message: 'System online (AI core loading)',
      lastError: finalReadiness.readiness?.degradedReasons?.join(', ') || null,
    })
  } else if (nodeUp) {
    setStatus({
      state: 'degraded', phase: 'health-ok',
      message: 'System degraded — Python AI backend offline',
      lastError: 'python_offline',
    })
  } else {
    setStatus({
      state: 'degraded', phase: 'health-ok',
      message: 'System degraded — health check failed',
      lastError: finalReadiness.errors?.[0] || 'health_fail',
    })
  }
  event?.sender?.send('start-ready', { ready: Boolean(nodeUp), readiness: finalReadiness })

  return { success: true, launch: launchResult, readiness: finalReadiness }
}

// ── Updater wiring (Step 6) ───────────────────────────────────────────
let updaterApi = { available: false }

// ── IPC handlers ──────────────────────────────────────────────────────
ipcMain.handle('start-system', async (event, opts) => {
  resetRestartCounter()
  const result = await startSystem(event, opts)
  if (result?.success) {
    openInterface().catch(err => log.warn(`auto openInterface: ${err.message}`))
  }
  return result
})
ipcMain.handle('stop-system', async () => { resetRestartCounter(); return backend.stop() })
ipcMain.handle('cancel-start', async () => { resetRestartCounter(); return { success: true, cancelled: backend.cancel() } })
ipcMain.handle('check-status', async () => {
  const readiness = await checkReadiness()
  return { running: readiness.ready || readiness.degraded, readiness }
})
ipcMain.handle('open-interface', openInterface)
ipcMain.handle('retry-open-interface', openInterface)
ipcMain.handle('restart-system', async (event) => {
  resetRestartCounter()
  await backend.stop()
  return startSystem(event, { skipExisting: false })
})
ipcMain.handle('restart-verbose', async (event) => {
  resetRestartCounter()
  await backend.stop()
  return startSystem(event, {
    skipExisting: false,
    extraEnv: { LOG_LEVEL: 'DEBUG', STRICT_PIPELINE: '1' },
  })
})

ipcMain.handle('get-launch-status', async () => launchStatus)
ipcMain.handle('get-diagnostics', async () => buildDiagnostics())
ipcMain.handle('get-policy', async () => loadPolicy())

// Rendering mode (WebGL) — controllable from Settings; takes effect on next restart.
ipcMain.handle('get-render-mode', async () => {
  const { getRenderMode, VALID } = require('./src/render-prefs')
  return { mode: getRenderMode(), options: VALID }
})
ipcMain.handle('set-render-mode', async (_e, mode) => {
  const { setRenderMode } = require('./src/render-prefs')
  const r = setRenderMode(mode)
  log.info(`render mode set → ${mode} (ok=${r.ok})`)
  return r  // caller restarts to apply
})
ipcMain.handle('get-phases', async () => tracker.snapshot())

ipcMain.handle('open-logs-folder', async () => {
  await shell.openPath(PATHS.logDir)
  return { success: true }
})

ipcMain.handle('copy-diagnostics', async () => {
  const dump = JSON.stringify(buildDiagnostics(), null, 2)
  clipboard.writeText(dump)
  return { success: true, bytes: dump.length }
})

ipcMain.handle('export-diagnostics', async () => {
  const dump = JSON.stringify(buildDiagnostics(), null, 2)
  const file = path.join(PATHS.logDir, `diagnostics-${new Date().toISOString().replace(/[:.]/g, '-')}.json`)
  fs.mkdirSync(PATHS.logDir, { recursive: true })
  fs.writeFileSync(file, dump)
  return { success: true, path: file, bytes: dump.length }
})

ipcMain.handle('return-to-launcher', async () => {
  if (appWindow && !appWindow.isDestroyed()) appWindow.close()
  appWindow = null
  if (launcherWindow && !launcherWindow.isDestroyed()) {
    launcherWindow.show()
    launcherWindow.focus()
  }
  setStatus({ state: 'idle', message: 'Returned to launcher' })
  return { success: true }
})

ipcMain.handle('get-version', async () => {
  const pkg = { version: app.getVersion() }
  try {
    if (fs.existsSync(PATHS.versionFile)) {
      return { ...pkg, ...JSON.parse(fs.readFileSync(PATHS.versionFile, 'utf8')) }
    }
  } catch {}
  return { ...pkg, last_commit: 'unknown', last_updated_at: null }
})

ipcMain.handle('check-updates', async () => {
  const policy = loadPolicy()
  if (policy.network?.allowAutoUpdate !== true) {
    return { update_available: false, skipped: true, reason: 'auto-update disabled by offline-first policy' }
  }
  if (updaterApi.available && updaterApi.checkForUpdates) {
    await updaterApi.checkForUpdates()
    return { triggered: true }
  }
  try {
    if (fs.existsSync(PATHS.updaterFile)) {
      return JSON.parse(fs.readFileSync(PATHS.updaterFile, 'utf8'))
    }
  } catch {}
  return { update_available: false }
})
ipcMain.handle('apply-update', async () => {
  const policy = loadPolicy()
  if (policy.network?.allowAutoUpdate !== true) {
    return { ok: false, error: 'Auto-update is disabled by offline-first policy' }
  }
  if (updaterApi.available && updaterApi.quitAndInstall) {
    updaterApi.quitAndInstall()
    return { ok: true }
  }
  return { ok: false, error: 'Updater not available' }
})

ipcMain.handle('check-dependencies', async () => {
  const report = checkFirstBoot()
  const policy = loadPolicy()
  return {
    ...report,
    node: report.checks.node_runtime,
    node_version: process.version,
    python: report.checks.python,
    python_version: report.python?.version || null,
    npm_packages: report.checks.backend_node_modules,
    pip_packages: report.checks.pip_fastapi,
    frontend_dist: report.checks.frontend_dist,
    offline: policy.network?.offlineByDefault !== false,
  }
})

// REBUILD frontend dist — used after a code update or when frontend/dist is stale.
// Runs `npm run build` in frontend/ and streams progress lines via 'rebuild-log'.
ipcMain.handle('rebuild-frontend', async (event) => {
  const { spawn } = require('child_process')
  const frontendDir = path.join(PATHS.repoDir, 'frontend')
  if (!fs.existsSync(path.join(frontendDir, 'package.json'))) {
    return { success: false, error: `frontend/package.json not found at ${frontendDir}` }
  }
  log.info(`rebuild-frontend: starting (cwd=${frontendDir})`)
  event?.sender?.send('rebuild-log', { line: '▸ Building dashboard bundle…', level: 'info' })
  return new Promise((resolve) => {
    const proc = spawn('npm', ['run', 'build'], { cwd: frontendDir, stdio: 'pipe' })
    let lastTransform = ''
    proc.stdout.on('data', (d) => {
      d.toString().split('\n').filter(l => l.trim()).forEach(line => {
        // Compress noisy "transforming N modules" lines into one rotating row
        const m = line.match(/transforming.*?(\d+)\s*modules/)
        if (m) { lastTransform = `transforming ${m[1]} modules…`; return }
        event?.sender?.send('rebuild-log', { line, level: 'info' })
      })
    })
    proc.stderr.on('data', (d) => {
      d.toString().split('\n').filter(l => l.trim()).forEach(line => {
        event?.sender?.send('rebuild-log', { line, level: 'warn' })
      })
    })
    proc.on('exit', (code) => {
      const success = code === 0
      log.info(`rebuild-frontend: exit code=${code}`)
      event?.sender?.send('rebuild-log', {
        line: success ? '✓ Frontend rebuilt successfully' : `✗ Build failed (exit ${code})`,
        level: success ? 'info' : 'error',
      })
      event?.sender?.send('rebuild-complete', { success, exit_code: code })
      resolve({ success, exit_code: code })
    })
    proc.on('error', (err) => {
      log.error('rebuild-frontend spawn error:', err.message)
      event?.sender?.send('rebuild-log', { line: `spawn error: ${err.message}`, level: 'error' })
      event?.sender?.send('rebuild-complete', { success: false, error: err.message })
      resolve({ success: false, error: err.message })
    })
  })
})

ipcMain.handle('run-dependency-install', async (event, type) => {
  const { spawn } = require('child_process')
  const firstBoot = checkFirstBoot()
  if (!firstBoot.install_allowed) {
    return { success: false, error: firstBoot.install_reason }
  }
  return new Promise(resolve => {
    const cmd = type === 'npm'
      ? { cmd: 'npm', args: ['install'], cwd: PATHS.repoDir }
      : { cmd: 'bash', args: ['install.sh', '--deps-only'], cwd: PATHS.repoDir }
    const proc = spawn(cmd.cmd, cmd.args, { cwd: cmd.cwd, stdio: 'pipe' })
    proc.stdout.on('data', d => {
      d.toString().split('\n').filter(l => l.trim()).forEach(l => {
        event.sender.send('setup-log', l)
      })
    })
    proc.on('exit', code => resolve({ success: code === 0 }))
    proc.on('error', err => resolve({ success: false, error: err.message }))
  })
})

ipcMain.handle('mark-setup-complete', async () => {
  try {
    writeSetupComplete(checkFirstBoot())
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
})

// React renderer → main signals
ipcMain.on('ui-boot-phase', (event, payload) => {
  if (appWindow && event.sender !== appWindow.webContents) return
  const phase = typeof payload === 'string' ? payload : (payload?.phase || '')
  if (phase === 'react-rendered' || phase === 'first-paint') {
    onReactRendered()
  }
  // Also propagate as a status update so the launcher rail keeps moving
  setStatus({ state: 'ui-loading', phase: phase || 'ui-boot', message: payload?.message || phase || 'UI boot phase', lastError: null })
})
ipcMain.on('ui-mounted', (event, payload) => {
  if (appWindow && event.sender !== appWindow.webContents) return
  onReactMounted(payload || {})
})
ipcMain.on('ui-failed', (event, payload) => {
  if (appWindow && event.sender !== appWindow.webContents) return
  const message = payload?.message || payload?.error || 'React reported a UI failure'
  const severity = payload?.severity || 'fatal'
  const dashboardMounted = tracker.completed.has('react-mounted')
  log.error(`dashboard UI failure (${severity}): ${message}`)
  if (payload?.stack) log.error(payload.stack)
  if (severity === 'fatal' && !dashboardMounted) {
    tracker.fail(tracker.current || 'react-rendered', message)
    showDiagnostics(message, { uiFailure: payload || {} })
    return
  }
  setStatus({
    state: 'degraded',
    phase: tracker.current || 'react-mounted',
    message: severity === 'page' ? 'Dashboard page failed' : 'Dashboard widget degraded',
    lastError: message,
  })
})

// Window control passthrough (used by both windows)
function focusedWindow() {
  return BrowserWindow.getFocusedWindow() || appWindow || launcherWindow
}
ipcMain.on('window-minimize', () => {
  const w = focusedWindow()
  if (w && !w.isDestroyed()) w.minimize()
})
ipcMain.on('window-close', () => {
  const w = focusedWindow()
  if (w && !w.isDestroyed()) w.close()
})
ipcMain.on('window-toggle-fullscreen', () => {
  const w = focusedWindow()
  if (!w || w.isDestroyed()) return
  w.setFullScreen(!w.isFullScreen())
})

// ── App lifecycle ─────────────────────────────────────────────────────
app.on('ready', () => {
  // Nuke any cached HTTP responses from prior runs — a stale React chunk
  // (e.g. cognitiveStore from before the zustand chunk fix) will crash the
  // dashboard on load. The Cache-Control headers from the Node backend
  // should prevent this, but old caches from prior installs can persist.
  try {
    const { session } = require('electron')
    session.defaultSession.clearCache().then(() => log.info('electron cache cleared on boot'))
  } catch (e) {
    log.warn(`clearCache failed (non-fatal): ${e.message}`)
  }
  clearGpuShaderCaches()
  createLauncherWindow()
  // Defer updater wiring until AFTER the launcher window has finished loading
  // its renderer. Loading electron-updater synchronously here (which does I/O
  // to read app.getVersion and constructs AppUpdater) can block the event loop
  // long enough that Chromium's file:// load for the launcher HTML times out
  // with ERR_FAILED (-2). See LAUNCHER_FIXES.md v4 for the diagnosis.
  if (launcherWindow) {
    launcherWindow.webContents.once('did-finish-load', () => {
      try {
        const policy = loadPolicy()
        if (policy.network?.allowAutoUpdate === true) {
          updaterApi = updater.wire(launcherWindow)
          if (updaterApi.available && updaterApi.checkForUpdates) {
            // Run on next tick so it never blocks the renderer
            setImmediate(() => updaterApi.checkForUpdates())
          }
        } else {
          updaterApi = { available: false, reason: 'auto-update disabled by offline-first policy' }
        }
        log.info(`updater wired (available=${updaterApi.available})`)
      } catch (e) {
        log.warn('updater wire failed:', e.message)
      }
    })
  }
})

app.on('window-all-closed', () => {
  backend.cancel()
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (launcherWindow === null) createLauncherWindow()
})
