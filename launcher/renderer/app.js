/* ════════════════════════════════════════════════════════════════════
   LAUNCHER RENDERER — phase-driven state machine.
   No frameworks. The main process emits canonical boot phases; this
   file renders the phase rail, log tail, and screen transitions.
   ════════════════════════════════════════════════════════════════════ */

// ── Canonical phases (must mirror launcher/src/phases.js) ─────────────
const PHASES = [
  { id: 'preflight',         label: 'PRE-FLIGHT' },
  { id: 'deps-check',        label: 'DEPS-CHECK' },
  { id: 'backend-spawn',     label: 'BACKEND-SPAWN' },
  { id: 'node-port-bound',   label: 'NODE-PORT-BOUND' },
  { id: 'python-port-bound', label: 'PYTHON-PORT-BOUND' },
  { id: 'health-ok',         label: 'HEALTH-OK' },
  { id: 'window-create',     label: 'WINDOW-CREATE' },
  { id: 'html-loaded',       label: 'HTML-LOADED' },
  { id: 'react-rendered',    label: 'REACT-RENDERED' },
  { id: 'react-mounted',     label: 'REACT-MOUNTED' },
]
const PHASE_LABEL_WIDTH = 18 // chars — for monospace alignment in the log stream
const BAR_WIDTH = 32         // cells in the ASCII progress bar

const $ = (id) => document.getElementById(id)

const state = {
  screen: 'boot',                     // boot | setup | update | diagnostics
  running: false,
  completedPhases: new Set(),
  currentPhase: null,
  failedPhase: null,
  failedReason: null,
  diagnostics: null,
  lastReadiness: null,
  lastDeps: null,
}

// ── Screen switching ───────────────────────────────────────────────────
function setScreen(name) {
  if (state.screen === name) return
  state.screen = name
  document.body.dataset.screen = name
  document.querySelectorAll('.screen').forEach(el => {
    el.hidden = el.dataset.screenId !== name
  })
}

// ── Cyberpunk terminal: ASCII bar + ticker + log stream ────────────────
let bootStartTs = 0
const phaseStartTs = {}   // phase-id → ms timestamp when first seen
const phaseEndTs   = {}   // phase-id → ms timestamp when completed/failed
const streamLines  = []   // rendered log rows (max ~12)
let ticker = '▸ standing by'
let tickerInterval = null
let consoleEl = null      // cached after first render

function fmtTime(ms) {
  return `t+${(ms / 1000).toFixed(1)}s`
}
function pad(s, n) {
  s = String(s)
  return s.length >= n ? s : s + ' '.repeat(n - s.length)
}
function leader(usedLen, totalLen) {
  return '.'.repeat(Math.max(2, totalLen - usedLen))
}

function bootConsole() {
  if (!consoleEl) consoleEl = document.querySelector('.console')
  return consoleEl
}

function renderBar() {
  const completed = state.completedPhases.size
  const total = PHASES.length
  // Active phase contributes 0.5 cells worth of progress so the bar
  // feels alive even before a phase finishes.
  const activeBoost = state.currentPhase && !state.completedPhases.has(state.currentPhase) ? 0.5 : 0
  const ratio = Math.min(1, (completed + activeBoost) / total)
  const filledCells = Math.round(BAR_WIDTH * ratio)
  const fill  = '█'.repeat(filledCells)
  const empty = '░'.repeat(BAR_WIDTH - filledCells)
  const pct   = Math.round(ratio * 100)
  const bar = $('bootBar')
  if (!bar) return
  bar.innerHTML =
    `SYSTEM BOOT  [<span class="console__bar-fill">${fill}</span>` +
    `<span class="console__bar-empty">${empty}</span>] ` +
    `<span class="console__bar-pct">${String(pct).padStart(3)}%</span>`

  const c = bootConsole()
  if (c) {
    c.classList.toggle('is-done',   ratio >= 1 && !state.failedPhase)
    c.classList.toggle('is-failed', !!state.failedPhase)
  }
}

function renderStream() {
  const pre = $('bootStream')
  if (!pre) return
  pre.innerHTML = streamLines.join('\n')
  pre.scrollTop = pre.scrollHeight
}

function pushStreamLine(html) {
  streamLines.push(html)
  if (streamLines.length > 16) streamLines.shift()
  renderStream()
}

function appendInProgress(phaseId, label) {
  // Adds a row with animated "..." and a blinking cursor; updated in place
  // by replacing the last line of the stream.
  const sinceBoot = bootStartTs ? Date.now() - bootStartTs : 0
  const ts = `[${fmtTime(sinceBoot).padEnd(7)}]`
  const html =
    `<span class="ts">${ts}</span> ` +
    `<span class="name">${pad(label, PHASE_LABEL_WIDTH)}</span> ` +
    `<span class="lead">${leader(0, 12)}</span> ` +
    `<span class="work">…</span><span class="cursor"></span>`
  if (streamLines.length && streamLines[streamLines.length - 1].includes(`name">${pad(label, PHASE_LABEL_WIDTH)}<`)) {
    streamLines[streamLines.length - 1] = html
  } else {
    streamLines.push(html)
    if (streamLines.length > 16) streamLines.shift()
  }
  renderStream()
}

function fmtDuration(durationMs) {
  if (!durationMs || durationMs < 0) return ''
  // Right-pad to a fixed width so columns align in monospace.
  // e.g. "(   4 ms)", "(1234 ms)", "(  12 ms)"
  const cls = durationMs > 5000 ? 'dur dur--err'
            : durationMs > 2000 ? 'dur dur--warn'
            : 'dur'
  const ms = String(durationMs).padStart(4, ' ')
  return ` <span class="${cls}">(${ms} ms)</span>`
}

function finalizePhaseLine(phaseId, label, status /* 'ok' | 'fail' */, sinceBoot, durationMs) {
  const ts = `[${fmtTime(sinceBoot).padEnd(7)}]`
  const statusLabel = status === 'ok' ? 'OK  ' : 'FAIL'
  const statusClass = status === 'ok' ? 'ok' : 'fail'
  const html =
    `<span class="ts">${ts}</span> ` +
    `<span class="name">${pad(label, PHASE_LABEL_WIDTH)}</span> ` +
    `<span class="lead">${leader(0, 12)}</span> ` +
    `<span class="${statusClass}">${statusLabel}</span>` +
    fmtDuration(durationMs)

  // Replace the in-progress line for the same phase if present
  const needle = `name">${pad(label, PHASE_LABEL_WIDTH)}<`
  const idx = streamLines.findIndex(l => l.includes(needle))
  if (idx >= 0) streamLines[idx] = html
  else streamLines.push(html)
  if (streamLines.length > 16) streamLines.shift()
  renderStream()
}

function setTicker(text) {
  ticker = text
  const el = $('bootTicker')
  if (el) el.innerHTML = `<span class="console__chevron">${state.failedPhase ? '✕' : '▸'}</span> ${text}`
}

function startTickerLoop() {
  if (tickerInterval) return
  if (!bootStartTs) bootStartTs = Date.now()
  tickerInterval = setInterval(() => {
    const elapsed = bootStartTs ? Date.now() - bootStartTs : 0
    const clock = $('consoleClock')
    if (clock) clock.textContent = fmtTime(elapsed)
    // If a phase is in flight, update the in-progress line dot count
    if (state.currentPhase && !state.completedPhases.has(state.currentPhase) && !state.failedPhase) {
      const cur = PHASES.find(p => p.id === state.currentPhase)
      if (cur) {
        // animate the elapsed time on the in-progress line
        const phStart = phaseStartTs[cur.id] || bootStartTs
        const phElapsed = Date.now() - phStart
        if (state.subStep) {
          setTicker(`${state.subStep} · t+${(phElapsed / 1000).toFixed(1)}s`)
        } else {
          setTicker(`${cur.label.toLowerCase()} · t+${(phElapsed / 1000).toFixed(1)}s`)
        }
      }
    }
  }, 250)
}

function stopTickerLoop() {
  if (tickerInterval) { clearInterval(tickerInterval); tickerInterval = null }
}

function resetConsole() {
  bootStartTs = Date.now()
  for (const k of Object.keys(phaseStartTs)) delete phaseStartTs[k]
  for (const k of Object.keys(phaseEndTs))   delete phaseEndTs[k]
  streamLines.length = 0
  state.subStep = null
  state.failedPhase = null
  state.failedReason = null
  state.completedPhases.clear()
  state.currentPhase = null
  setTicker('initializing boot sequence')
  renderBar()
  renderStream()
  startTickerLoop()
  const c = bootConsole()
  if (c) c.classList.remove('is-done', 'is-failed')
}

function renderAllRails() {
  renderBar()
  // diagnostics screen still uses the simple dot rail (different markup)
  if (state.screen === 'diagnostics') renderDiagRail()
}

function renderDiagRail() {
  const ol = $('diagRail')
  if (!ol) return
  ol.innerHTML = ''
  PHASES.forEach(({ id, label }) => {
    const li = document.createElement('li')
    li.className = 'phase-rail__item'
    if (state.completedPhases.has(id)) li.classList.add('is-complete')
    if (state.currentPhase === id && !state.completedPhases.has(id)) li.classList.add('is-current')
    if (state.failedPhase === id) li.classList.add('is-failed')
    li.innerHTML = `<span class="phase-rail__dot"></span><span class="phase-rail__label">${label.replace(/-/g, ' ')}</span>`
    ol.appendChild(li)
  })
}

// ── Log tail ──────────────────────────────────────────────────────────
const LOG_MAX = 200
const logBuf = []
function pushLog(line) {
  logBuf.push(line)
  if (logBuf.length > LOG_MAX) logBuf.shift()
  const area = $('logArea')
  if (area) {
    area.textContent = logBuf.join('\n')
    area.scrollTop = area.scrollHeight
  }
}

// ── v5: State-aware action cluster ────────────────────────────────────
// Renders the right set of buttons for the current system state.
// state.running         = startup in progress
// state.systemUp        = backend is reachable / running
// state.rebuilding      = npm run build is in flight
// state.updating        = electron-updater is downloading
// state.failedPhase     = something failed; show diagnostics action
function updateButtons() {
  const slot = $('bootActions')
  if (!slot) return
  // Inline render — no framework, just template strings + delegation
  const btn = (id, label, cls = 'btn--ghost', disabled = false) =>
    `<button class="btn ${cls}" id="${id}" ${disabled ? 'disabled' : ''}>${label}</button>`

  let html = ''
  if (state.rebuilding) {
    html = `<div class="rebuild-bar">
              <span class="rebuild-bar__label">REBUILDING DASHBOARD…</span>
              <span class="rebuild-bar__pulse"></span>
            </div>`
  } else if (state.updating) {
    html = `<div class="rebuild-bar">
              <span class="rebuild-bar__label">DOWNLOADING UPDATE…</span>
              <span class="rebuild-bar__pulse"></span>
            </div>`
  } else if (state.running) {
    // Startup in progress — CANCEL is the only safe action
    html = btn('cancelBtn', 'CANCEL', 'btn--ghost')
  } else if (state.failedPhase) {
    // Something failed — RESTART is the primary action
    html = btn('startBtn', 'RETRY START', 'btn--primary') +
           btn('diagBtn', 'VIEW DIAGNOSTICS', 'btn--ghost')
  } else if (state.systemUp) {
    // Backend running — STOP + OPEN INTERFACE (primary)
    html = btn('stopBtn', 'STOP SYSTEM', 'btn--ghost') +
           btn('openBtn', 'OPEN INTERFACE', 'btn--cta')
  } else {
    // Idle — START is the primary action
    html = btn('startBtn', 'START SYSTEM', 'btn--cta')
  }
  slot.innerHTML = html
  updateStatusBar()

  // Wire the newly-rendered buttons (delegation would also work but explicit is clearer)
  $('startBtn')?.addEventListener('click', handleStart)
  $('cancelBtn')?.addEventListener('click', handleCancel)
  $('openBtn')?.addEventListener('click', handleOpen)
  $('stopBtn')?.addEventListener('click', handleStop)
  $('diagBtn')?.addEventListener('click', () => setScreen('diagnostics'))
}

// ── Live status bar ───────────────────────────────────────────────────
let systemUpTs = 0
let statusBarInterval = null

function updateStatusBar() {
  const bar = $('statusBar')
  if (!bar) return
  if (!state.systemUp) {
    bar.hidden = true
    if (statusBarInterval) { clearInterval(statusBarInterval); statusBarInterval = null }
    return
  }
  bar.hidden = false
  if (!systemUpTs) systemUpTs = Date.now()
  const elapsed = Date.now() - systemUpTs
  const s = Math.floor(elapsed / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const fmt = h > 0
    ? `${h}h ${String(m).padStart(2,'0')}m`
    : `${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`
  const uptimeEl = $('statusUptime')
  if (uptimeEl) uptimeEl.textContent = `uptime ${fmt}`
  if (!statusBarInterval) {
    statusBarInterval = setInterval(updateStatusBar, 1000)
  }
}

function setSystemUp(up) {
  if (up && !state.systemUp) systemUpTs = Date.now()
  if (!up) systemUpTs = 0
  state.systemUp = up
  updateStatusBar()
}

// ── Runtime status matrix ───────────────────────────────────────────────
function setMatrixCard(cardId, valueId, metaId, value, meta, kind = 'idle') {
  const card = $(cardId)
  const valueEl = $(valueId)
  const metaEl = $(metaId)
  if (card) card.dataset.kind = kind
  if (valueEl) valueEl.textContent = value
  if (metaEl) metaEl.textContent = meta
}

function renderStatusMatrix({ readiness = state.lastReadiness, deps = state.lastDeps, diagnostics = state.diagnostics } = {}) {
  const checks = readiness?.checks || {}
  const route = readiness?.route || diagnostics?.runtimeRoute || {}
  const policy = diagnostics?.policy || state.diagnostics?.policy
  const nodePort = route.nodePort || route.node || '8787'
  const pythonPort = route.pythonPort || route.python || '18790'
  const host = route.host || '127.0.0.1'

  const gatewayOk = checks.api_health || checks.health || checks.node_port || state.systemUp
  setMatrixCard(
    'cardGateway', 'statusGateway', 'statusGatewayMeta',
    gatewayOk ? 'online' : state.running ? 'starting' : 'standby',
    `Node ${host}:${nodePort}`,
    gatewayOk ? 'ok' : state.running ? 'warn' : 'idle'
  )

  const pythonOk = checks.python_port || readiness?.readiness?.pythonReady
  setMatrixCard(
    'cardPython', 'statusPython', 'statusPythonMeta',
    pythonOk ? 'online' : gatewayOk ? 'degraded' : state.running ? 'starting' : 'standby',
    `Backend :${pythonPort}`,
    pythonOk ? 'ok' : gatewayOk ? 'warn' : 'idle'
  )

  const bundleReady = deps?.frontend_dist || (checks.index && checks.assets)
  setMatrixCard(
    'cardDashboard', 'statusDashboard', 'statusDashboardMeta',
    bundleReady ? 'ready' : state.running ? 'checking' : 'unknown',
    bundleReady ? 'React bundle available' : 'Run rebuild if missing',
    bundleReady ? 'ok' : state.running ? 'warn' : 'idle'
  )

  const offline = policy?.network?.offlineByDefault !== false
  const updates = policy?.network?.allowAutoUpdate === true
  setMatrixCard(
    'cardPolicy', 'statusPolicy', 'statusPolicyMeta',
    offline ? 'local' : 'network',
    updates ? 'Updates allowed' : 'Updates locked',
    offline ? 'ok' : 'warn'
  )

  setMatrixCard(
    'cardRoute', 'statusRoute', 'statusRouteMeta',
    host,
    `UI :${nodePort} / AI :${pythonPort}`,
    gatewayOk ? 'ok' : 'idle'
  )
}

// ── Boot subtitle ─────────────────────────────────────────────────────
function setSub(text) {
  const el = $('bootSub')
  if (el) el.textContent = text
}

// ── Handlers ──────────────────────────────────────────────────────────
async function handleStart() {
  if (state.running) return
  state.running = true
  state.failedPhase = null
  logBuf.length = 0
  pushLog('Starting AETERNUS NEXUS…')
  setSub('Starting backend services…')
  resetConsole()
  appendInProgress('deps-check', 'DEPS-CHECK')
  state.currentPhase = 'deps-check'
  phaseStartTs['deps-check'] = Date.now()
  updateButtons()
  setScreen('boot')

  try {
    const result = await window.ai.startSystem()
    if (result?.success || result?.alreadyRunning) {
      state.lastReadiness = result.readiness || result.launch?.readiness || state.lastReadiness
      setSystemUp(true)
      setSub(result.alreadyRunning ? 'System already running — open the dashboard' : 'Backend ready — open the dashboard')
      renderStatusMatrix()
    } else {
      setSub('Startup did not complete. See diagnostics.')
    }
  } catch (err) {
    pushLog(`[ERROR] ${err?.message || err}`)
    setSub('Startup failed. See diagnostics.')
  } finally {
    state.running = false
    renderStatusMatrix()
    updateButtons()
  }
}

async function handleCancel() {
  if (!state.running) return
  await window.ai.cancelStart()
  state.running = false
  setSystemUp(false)
  setSub('Startup cancelled.')
  renderStatusMatrix()
  updateButtons()
}

async function handleStop() {
  if (!state.systemUp && !state.running) return
  pushLog('Stopping AETERNUS NEXUS…')
  setSub('Stopping backend services…')
  setTicker('stopping services')
  try {
    await window.ai.stopSystem()
    setSystemUp(false)
    state.completedPhases.clear()
    state.currentPhase = null
    setSub('System stopped. Press START to bring it online again.')
    setTicker('system stopped')
    state.lastReadiness = null
    renderStatusMatrix()
    renderBar()
    renderStream()
  } catch (err) {
    pushLog(`[ERROR] ${err?.message || err}`)
    setSub('Stop failed — services may still be running. Check Activity Monitor.')
  } finally {
    updateButtons()
  }
}

async function handleRebuild() {
  if (state.rebuilding) return
  state.rebuilding = true
  updateButtons()
  setSub('Rebuilding dashboard bundle… this typically takes 5–30 s')
  setTicker('rebuilding dashboard')
  try {
    const r = await window.ai.rebuildFrontend()
    if (r?.success) {
      setSub('Dashboard rebuilt successfully. Reopen INTERFACE to load the new bundle.')
      pushLog('✓ Frontend rebuild succeeded')
    } else {
      setSub(`Rebuild failed: ${r?.error || 'unknown error'} — see backend logs`)
      pushLog(`✗ Rebuild failed: ${r?.error || ('exit ' + r?.exit_code)}`)
    }
  } catch (err) {
    pushLog(`[ERROR] rebuild threw: ${err?.message || err}`)
    setSub('Rebuild crashed — see backend logs')
  } finally {
    state.rebuilding = false
    updateButtons()
  }
}

async function handleCheckUpdates() {
  setSub('Checking for updates…')
  setTicker('contacting update server')
  try {
    const r = await window.ai.checkUpdates()
    if (r?.triggered) {
      setSub('Update check started. If an update is available, it will appear on the UPDATE screen.')
    } else if (r?.update_available) {
      setScreen('update')
      $('updateStage').textContent = 'Update available — ready to download.'
    } else {
      setSub('No updates available — you are on the latest version.')
    }
  } catch (err) {
    setSub(`Update check failed: ${err?.message || err}`)
  }
}

async function handleSysmenuAction(action) {
  hideSysmenu()
  switch (action) {
    case 'check-updates':   return handleCheckUpdates()
    case 'rebuild':         return handleRebuild()
    case 'restart-verbose': return handleRestartVerbose()
    case 'open-logs':       return handleOpenLogs()
    case 'copy-diag':       return handleCopyDiag()
    case 'export-diag':     return handleExportDiag()
  }
}

function toggleSysmenu() {
  const m = $('sysmenu')
  if (!m) return
  m.hidden = !m.hidden
}
function hideSysmenu() { const m = $('sysmenu'); if (m) m.hidden = true }

async function handleOpen() {
  if (!state.systemUp) return
  setSub('Opening interface…')
  try {
    await window.ai.openInterface()
  } catch (err) {
    pushLog(`[ERROR] ${err?.message || err}`)
    setSub('Could not open dashboard. See diagnostics.')
  }
}

async function handleRestart() {
  state.running = true
  updateButtons()
  await window.ai.restartSystem()
  state.running = false
  updateButtons()
}

// ── Diagnostics handlers ──────────────────────────────────────────────
async function handleOpenLogs() {
  await window.ai.openLogsFolder()
}
async function handleCopyDiag() {
  const r = await window.ai.copyDiagnostics()
  if (r?.success) {
    const btn = $('diagCopyBtn')
    const orig = btn.textContent
    btn.textContent = `COPIED (${(r.bytes / 1024).toFixed(1)} KB)`
    setTimeout(() => (btn.textContent = orig), 1800)
  }
}
async function handleExportDiag() {
  const r = await window.ai.exportDiagnostics()
  if (r?.success) {
    pushLog(`[diag] exported ${r.path}`)
    setSub(`Diagnostics exported: ${r.path}`)
  } else {
    setSub(`Diagnostics export failed: ${r?.error || 'unknown error'}`)
  }
}
async function handleRestartVerbose() {
  setScreen('boot')
  setSub('Restarting backend with verbose logging…')
  state.running = true
  state.completedPhases.clear()
  state.currentPhase = null
  state.failedPhase = null
  state.failedReason = null
  renderAllRails()
  updateButtons()
  try {
    await window.ai.restartVerbose()
  } finally {
    state.running = false
    updateButtons()
  }
}

// ── Diagnostics screen population ─────────────────────────────────────
function showDiagnostics({ message, diagnostics }) {
  state.diagnostics = diagnostics
  renderStatusMatrix({ diagnostics })
  // Update phase state from the main-process snapshot (authoritative)
  if (diagnostics?.phases) {
    state.completedPhases = new Set(diagnostics.phases.completed || [])
    state.currentPhase = diagnostics.phases.current
    state.failedPhase = diagnostics.phases.failed
    state.failedReason = diagnostics.phases.failedReason
  }
  setScreen('diagnostics')

  $('diagSummary').textContent = message || diagnostics?.launchStatus?.lastError || 'Dashboard failed to start.'
  $('diagFailure').textContent = state.failedReason || message || 'Unknown failure.'

  const lines = (diagnostics?.logs || []).map(l => l.line || '').filter(Boolean)
  const logArea = $('diagLogs')
  if (logArea) logArea.textContent = lines.length ? lines.join('\n') : '(no logs captured yet)'

  renderAllRails()
}

// ── Setup screen (deps check) ─────────────────────────────────────────
async function checkDeps() {
  const deps = await window.ai.checkDependencies()
  state.lastDeps = deps
  const list = $('depsList')
  list.innerHTML = ''
  const rows = [
    { name: 'Node.js',         ok: deps.node,         val: deps.node_version || '—' },
    { name: 'Python 3',        ok: deps.python,       val: deps.python_version || '—' },
    { name: 'npm packages',    ok: deps.npm_packages, val: deps.npm_packages ? 'installed' : 'missing' },
    { name: 'pip packages',    ok: deps.pip_packages, val: deps.pip_packages ? 'installed' : 'missing' },
    { name: 'frontend bundle', ok: deps.frontend_dist, val: deps.frontend_dist ? 'ready' : 'missing' },
    { name: 'offline policy',  ok: deps.offline,      val: deps.offline ? 'enabled' : 'disabled' },
  ]
  rows.forEach(r => {
    const li = document.createElement('li')
    li.className = `checklist__item ${r.ok ? 'is-ok' : 'is-bad'}`
    li.innerHTML = `<span class="checklist__dot"></span><span class="checklist__name">${r.name}</span><span class="checklist__val">${r.val}</span>`
    list.appendChild(li)
  })
  const installBtn = $('installBtn')
  if (installBtn) {
    installBtn.disabled = !deps.install_allowed
    installBtn.textContent = deps.install_allowed ? 'INSTALL DEPENDENCIES' : 'OFFLINE INSTALL LOCKED'
    installBtn.title = deps.install_reason || ''
  }
  try {
    state.diagnostics = await window.ai.getDiagnostics()
  } catch {}
  renderStatusMatrix({ deps, diagnostics: state.diagnostics })
  return deps.setup_complete
}

// ── Wire main-process events ──────────────────────────────────────────
window.ai.onStartLog((line) => pushLog(line))
window.ai.onStartReady((data) => {
  state.lastReadiness = data?.readiness || data
  renderStatusMatrix()
  setSub(data?.degraded ? 'Backend ready (degraded)' : 'Backend ready')
})
window.ai.onStartError((msg) => pushLog(`[ERROR] ${msg}`))

// Phase tracker drives the cyberpunk terminal. The main process emits a
// 'phase' event each time a phase *completes*; we render the OK line at
// that point and pre-render an in-progress line for the next phase.
window.ai.onPhase(({ phase, label, durationMs }) => {
  if (!bootStartTs) bootStartTs = Date.now()
  if (!phaseStartTs[phase]) phaseStartTs[phase] = bootStartTs
  phaseEndTs[phase] = Date.now()

  const def = PHASES.find(p => p.id === phase) || { id: phase, label: (label || phase).toUpperCase() }
  const sinceBoot = phaseEndTs[phase] - bootStartTs
  // Prefer the main-process duration (authoritative) and fall back to client-side delta
  const dur = Number.isFinite(durationMs) ? durationMs : Math.max(0, phaseEndTs[phase] - (phaseStartTs[phase] || bootStartTs))
  finalizePhaseLine(phase, def.label, 'ok', sinceBoot, dur)

  state.completedPhases.add(phase)
  state.currentPhase = phase
  state.failedPhase = null
  renderAllRails()
  updateButtons()
  if (label) setSub(label)

  // Pre-render the next in-progress phase line
  const idx = PHASES.findIndex(p => p.id === phase)
  const next = PHASES[idx + 1]
  if (next && !state.completedPhases.has(next.id)) {
    state.currentPhase = next.id
    phaseStartTs[next.id] = Date.now()
    appendInProgress(next.id, next.label)
  }
})

window.ai.onPhaseFail(({ phase, reason, durationMs }) => {
  state.failedPhase = phase
  state.failedReason = reason
  const def = PHASES.find(p => p.id === phase) || { id: phase, label: (phase || 'unknown').toUpperCase() }
  const sinceBoot = bootStartTs ? Date.now() - bootStartTs : 0
  const dur = Number.isFinite(durationMs) ? durationMs : Math.max(0, Date.now() - (phaseStartTs[phase] || bootStartTs))
  finalizePhaseLine(phase, def.label, 'fail', sinceBoot, dur)
  setTicker(`FAILED at ${phase} after ${(sinceBoot / 1000).toFixed(1)}s — ${reason}`)
  stopTickerLoop()
  renderAllRails()
})

// Render Python subsystem boot timings under a dedicated header.
// Each subsystem row uses the same alignment as the main phase rail so the
// reader can instantly spot a slow init (amber > 2 s, red > 5 s).
if (window.ai.onPythonSubsystems) {
  window.ai.onPythonSubsystems(({ timings }) => {
    if (!Array.isArray(timings) || timings.length === 0) return
    // Header divider
    streamLines.push(
      `<span class="ts">[--]</span> ` +
      `<span class="name">${pad('--- PYTHON SUBSYSTEMS ---', PHASE_LABEL_WIDTH)}</span>`
    )
    for (const t of timings) {
      const name = String(t.name || 'unknown').toUpperCase()
      const ok = t.ok !== false
      const ms = Math.max(0, Number(t.ms || 0) | 0)
      const statusLabel = ok ? 'OK  ' : 'FAIL'
      const statusClass = ok ? 'ok' : 'fail'
      streamLines.push(
        `<span class="ts">[py]</span> ` +
        `<span class="name">${pad(name, PHASE_LABEL_WIDTH)}</span> ` +
        `<span class="lead">${leader(0, 12)}</span> ` +
        `<span class="${statusClass}">${statusLabel}</span>` +
        fmtDuration(ms)
      )
    }
    if (streamLines.length > 16 + timings.length + 1) {
      streamLines.splice(0, streamLines.length - (12 + timings.length + 1))
    }
    renderStream()
  })
}

window.ai.onUiLoadStatus((status) => {
  if (status?.message) setSub(status.message)
  if (status?.message) state.subStep = String(status.message).toLowerCase()
  if (status?.lastError) pushLog(`[STATE] ${status.lastError}`)
  renderStatusMatrix()
})

window.ai.onUiLoadFailed((payload) => {
  showDiagnostics(payload)
})

// ── Wire DOM ──────────────────────────────────────────────────────────
async function init() {
  // Title bar controls (work in frameless mode)
  $('minimizeBtn').addEventListener('click', () => window.ai.windowMinimize())
  $('closeBtn').addEventListener('click',    () => window.ai.windowClose())
  $('sysmenuBtn')?.addEventListener('click', (e) => { e.stopPropagation(); toggleSysmenu() })

  // Boot screen buttons are now dynamically rendered by updateButtons() —
  // but the sysmenu items are static and need wiring once.
  document.querySelectorAll('.sysmenu__item').forEach((el) => {
    el.addEventListener('click', () => handleSysmenuAction(el.dataset.action))
  })
  // Click anywhere outside the sysmenu closes it
  document.addEventListener('click', (e) => {
    const m = $('sysmenu')
    if (m && !m.hidden && !m.contains(e.target) && e.target.id !== 'sysmenuBtn') hideSysmenu()
  })

  // UPDATE screen handlers
  $('updateSkipBtn')?.addEventListener('click', () => {
    setScreen('boot')
    setSub('Update skipped. You can check again from the ⋯ menu.')
  })
  $('updateReloadBtn')?.addEventListener('click', () => {
    window.ai.applyUpdate?.()
  })

  // Diagnostics screen buttons
  $('diagOpenLogsBtn').addEventListener('click', handleOpenLogs)
  $('diagCopyBtn').addEventListener('click',     handleCopyDiag)
  $('diagExportBtn').addEventListener('click',   handleExportDiag)
  $('diagVerboseBtn').addEventListener('click',  handleRestartVerbose)

  // ── Backend state events: keep state.systemUp accurate so the action
  // cluster shows STOP when running, START when stopped, etc.
  window.ai.onBackendState?.(({ state: backendState, restartCount, expected }) => {
    if (backendState === 'stopped') { setSystemUp(false); state.running = false }
    if (backendState === 'restarting') { setSystemUp(false); state.running = true }
    if (backendState === 'crashed') { setSystemUp(false); state.running = false; state.failedPhase = 'health-ok' }
    if (restartCount) pushLog(`[backend] auto-restart attempt ${restartCount}`)
    updateButtons()
  })

  // ── Rebuild events: stream into the log area + update screen if visible
  window.ai.onRebuildLog?.((data) => pushLog(`[build] ${data.line}`))
  window.ai.onRebuildComplete?.((data) => {
    pushLog(data.success ? '[build] complete' : '[build] FAILED')
  })

  // ── Updater events: route to the UPDATE screen automatically
  window.ai.onUpdaterEvent?.((channel, payload) => {
    if (channel === 'updater:available') {
      setScreen('update')
      $('updateStage').textContent = `Update v${payload?.version || '?'} available — downloading…`
    } else if (channel === 'updater:progress') {
      const pct = Math.round(payload?.percent || 0)
      $('updateProgress').style.width = `${pct}%`
      $('updateStage').textContent = `Downloading… ${pct}%`
    } else if (channel === 'updater:downloaded') {
      $('updateStage').textContent = 'Update downloaded — click APPLY & RESTART to install.'
      $('updateReloadBtn').disabled = false
    } else if (channel === 'updater:error') {
      const m = payload?.message || 'unknown'
      pushLog(`[updater] error: ${m}`)
    } else if (channel === 'updater:not-available') {
      setSub('No updates available — you are on the latest version.')
    }
  })

  // Version label — prefer semver from package.json, fall back to git hash
  try {
    const v = await window.ai.getVersion()
    if (v?.version) $('versionLabel').textContent = `v${v.version}`
    else if (v?.last_commit) $('versionLabel').textContent = `v${(v.last_commit || '').slice(0, 7)}`
  } catch {}

  // Initial render
  renderAllRails()
  updateButtons()

  // Decide initial screen — if deps are missing, route to setup
  const setupOk = await checkDeps()
  if (!setupOk) {
    setScreen('setup')
    setTicker('install required dependencies to continue')
  } else {
    // Auto-detect a running system and pre-fill rail / enable OPEN
    try {
      const status = await window.ai.checkStatus()
      if (status?.running) {
        state.lastReadiness = status.readiness
        bootStartTs = Date.now()
        setSystemUp(true)   // ← tells updateButtons() to show STOP + OPEN
        ;['deps-check', 'backend-spawn', 'node-port-bound', 'health-ok'].forEach(p => state.completedPhases.add(p))
        if (status?.readiness?.checks?.python_port) state.completedPhases.add('python-port-bound')
        // Replay completed lines into the stream
        ;[...state.completedPhases].forEach(id => {
          const def = PHASES.find(p => p.id === id)
          if (def) finalizePhaseLine(id, def.label, 'ok', 0)
        })
        setSub('System already running — open the dashboard')
        setTicker('system already online · ready when you are')
        startTickerLoop()
        renderAllRails()
        renderStatusMatrix()
        updateButtons()
      } else {
        setSub('Press START to bring the AI workforce online.')
        setTicker('press START to bring the system online')
        renderStatusMatrix()
      }
    } catch {
      setSub('Press START to bring the AI workforce online.')
      setTicker('press START to bring the system online')
      renderStatusMatrix()
    }
  }

  // Setup screen install button
  $('installBtn').addEventListener('click', async () => {
    const deps = await window.ai.checkDependencies()
    if (!deps.install_allowed) {
      pushLog(`[SETUP] ${deps.install_reason || 'dependency installation is disabled'}`)
      return
    }
    $('installBtn').disabled = true
    $('installBtn').textContent = 'INSTALLING…'
    try {
      await window.ai.runDependencyInstall?.('npm')
      await window.ai.runDependencyInstall?.('pip')
      await window.ai.markSetupComplete()
      await checkDeps()
      setScreen('boot')
    } finally {
      $('installBtn').disabled = false
      $('installBtn').textContent = 'INSTALL DEPENDENCIES'
    }
  })
}

document.addEventListener('DOMContentLoaded', init)
