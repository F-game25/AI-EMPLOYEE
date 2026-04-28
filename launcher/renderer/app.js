let state = 'checking'
let _ellipsisInterval = null
const particles = new ParticleSystem()

const startBtn  = document.getElementById('startBtn')
const stopBtn   = document.getElementById('stopBtn')
const openBtn   = document.getElementById('openBtn')
const logArea   = document.getElementById('logArea')
const versionEl = document.getElementById('version')
const cancelBtn = document.getElementById('cancelBtn')

// ── State machine ─────────────────────────────────────────────────────────────
// States: idle | idle-running | starting | ready | setup | loading
// CSS body class drives which .state div is visible.
// 'idle-running' = system is already up; body gets class 'idle' + openBtn enabled.

function setState(newState) {
  state = newState

  // Map idle-running → 'idle' for CSS (same look, different button states)
  document.body.className = newState === 'idle-running' ? 'idle' : newState

  // Restart progress bar animation when entering starting state
  if (newState === 'starting') {
    const fill = document.getElementById('progressFill')
    if (fill) { fill.style.animation = 'none'; fill.offsetHeight; fill.style.animation = '' }
  }

  // JS-driven ellipsis (CSS content: doesn't work on inline elements)
  const el = document.querySelector('.ellipsis')
  clearInterval(_ellipsisInterval)
  if (el) {
    if (newState === 'starting') {
      let i = 0
      _ellipsisInterval = setInterval(() => { el.textContent = ['.', '..', '...'][i++ % 3] }, 400)
    } else {
      el.textContent = '...'
    }
  }

  updateButtons()
}

function updateButtons() {
  const running  = state === 'idle-running'
  const starting = state === 'starting'
  const ready    = state === 'ready'

  startBtn.disabled = running || starting
  stopBtn.disabled  = !running
  openBtn.disabled  = !(running || ready)
  cancelBtn.disabled = !starting
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  particles.init()

  const deps = await window.ai.checkDependencies().catch(() => ({}))

  if (!deps.setup_complete || !deps.node || !deps.python) {
    setState('setup')
    renderSetupScreen(deps)
    return
  }

  const [status, version, updates] = await Promise.all([
    window.ai.checkStatus().catch(() => ({ running: false })),
    window.ai.getVersion().catch(() => ({})),
    window.ai.checkUpdates().catch(() => ({})),
  ])

  const commit = version.last_commit || version.last_installed_commit || ''
  versionEl.textContent = commit ? commit.slice(0, 7) : 'unknown'

  if (updates.update_available) document.body.classList.add('has-update')

  setState(status.running ? 'idle-running' : 'idle')

  startBtn.addEventListener('click', handleStart)
  stopBtn.addEventListener('click', handleStop)
  openBtn.addEventListener('click', handleOpen)
  cancelBtn.addEventListener('click', handleCancel)
}

// ── START SYSTEM ──────────────────────────────────────────────────────────────
async function handleStart() {
  if (state === 'starting' || state === 'idle-running' || state === 'ready') return
  setState('starting')
  logArea.innerHTML = ''

  // Wire IPC events before calling startSystem
  window.ai.onStartLog(line => appendLog(line))

  window.ai.onStartReady(() => {
    if (state !== 'starting') return
    setState('ready')
    // Auto-advance to idle-running after 2 s so openBtn stays enabled
    setTimeout(() => { if (state === 'ready') setState('idle-running') }, 2000)
  })

  window.ai.onStartError(msg => {
    appendLog('[ERROR] ' + msg)
    if (state === 'starting') setState('idle')
  })

  try {
    await window.ai.startSystem()
    // start.sh exited 0 but start-ready may not have fired yet (Python backend
    // slow to start). Poll health directly as a fallback signal.
    if (state === 'starting') {
      setState('ready')
      setTimeout(() => { if (state === 'ready') setState('idle-running') }, 2000)
    }
  } catch (err) {
    appendLog('[ERROR] ' + (err?.message || 'Startup failed'))
    if (state === 'starting') setState('idle')
  }
}

// ── STOP SYSTEM ───────────────────────────────────────────────────────────────
async function handleStop() {
  if (state !== 'idle-running') return
  stopBtn.disabled = true
  stopBtn.textContent = 'Stopping…'
  try {
    const result = await window.ai.stopSystem()
    if (result?.success) {
      setState('idle')
    } else {
      appendLog('[WARN] stop.sh returned non-zero')
      setState('idle')
    }
  } catch (err) {
    appendLog('[ERROR] Failed to stop: ' + (err?.message || err))
    setState('idle')
  } finally {
    stopBtn.textContent = 'Stop'
  }
}

// ── OPEN INTERFACE ────────────────────────────────────────────────────────────
async function handleOpen() {
  if (state !== 'ready' && state !== 'idle-running') return
  openBtn.disabled = true
  // Show "CONNECTING TO ULTRON..." overlay while Electron loads the URL
  document.body.className = 'loading'
  try {
    await window.ai.openInterface()
    // openInterface calls mainWindow.loadURL — renderer will be replaced;
    // nothing more needed here.
  } catch (err) {
    // Restore previous state if something went wrong
    setState(state)
    openBtn.disabled = false
    appendLog('[ERROR] Could not open interface: ' + (err?.message || err))
  }
}

// ── CANCEL ────────────────────────────────────────────────────────────────────
function handleCancel() {
  setState('idle')
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function appendLog(line) {
  const entry = document.createElement('div')
  entry.textContent = line
  logArea.appendChild(entry)
  const atBottom = logArea.scrollHeight - logArea.scrollTop <= logArea.clientHeight + 24
  if (atBottom) logArea.scrollTop = logArea.scrollHeight
}

function renderSetupScreen(deps) {
  const depList = document.getElementById('depList')
  const items = [
    { key: 'node',         label: 'Node.js',         ok: deps.node,         version: deps.node_version },
    { key: 'python',       label: 'Python 3',         ok: deps.python,       version: deps.python_version },
    { key: 'npm_packages', label: 'npm packages',     ok: deps.npm_packages },
    { key: 'pip_packages', label: 'Python packages',  ok: deps.pip_packages },
  ]

  depList.innerHTML = items.map(item => `
    <div class="dep-item ${item.ok ? 'dep-ok' : 'dep-missing'}">
      <span class="dep-icon">${item.ok ? '✓' : '✗'}</span>
      <span class="dep-name">${item.label}</span>
      <span class="dep-status">${item.ok ? (item.version || 'OK') : 'MISSING'}</span>
    </div>
  `).join('')

  const installBtn = document.getElementById('installDepsBtn')
  const setupLog   = document.getElementById('setupLog')

  installBtn.addEventListener('click', async () => {
    installBtn.disabled = true
    document.body.classList.add('setup-installing')
    setupLog.innerHTML = '<div style="color:rgba(255,255,255,0.4)">Installing dependencies…</div>'

    for (const type of ['npm', 'pip']) {
      await window.ai.runDependencyInstall(type).catch(() => {})
    }

    setupLog.innerHTML += '<div style="color:#22C55E;margin-top:8px">✓ Done — reloading in 2 s…</div>'
    await window.ai.markSetupComplete().catch(() => {})
    setTimeout(() => location.reload(), 2000)
  })

  window.ai.onSetupLog(line => {
    const e = document.createElement('div')
    e.textContent = line
    setupLog.appendChild(e)
    setupLog.scrollTop = setupLog.scrollHeight
  })
}

// ── PARTICLE SYSTEM ───────────────────────────────────────────────────────────
function ParticleSystem() {
  this.canvas = document.getElementById('particles')
  this.ctx    = this.canvas.getContext('2d')
  this.pts    = []
  this.links  = []
  this.animId = null

  const resize = () => {
    this.canvas.width  = window.innerWidth
    this.canvas.height = window.innerHeight
  }
  resize()
  window.addEventListener('resize', resize)

  this.init = () => {
    this.pts = []
    for (let i = 0; i < 30; i++) {
      this.pts.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 1.5 + 0.5,
        col: Math.random() > 0.5 ? 'rgba(32,214,199,' : 'rgba(229,199,107,',
      })
    }
    for (let i = 0; i < 3; i++) {
      const a = Math.floor(Math.random() * this.pts.length)
      const b = Math.floor(Math.random() * this.pts.length)
      if (a !== b) this.links.push({ a, b, life: 0 })
    }
    this._frame()
  }

  this._frame = () => {
    const { ctx, canvas, pts, links } = this
    ctx.fillStyle = 'rgba(7,8,16,1)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    pts.forEach(p => {
      p.x += p.vx; p.y += p.vy
      if (p.x < 0 || p.x > canvas.width)  p.vx *= -1
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      p.x = Math.max(0, Math.min(canvas.width, p.x))
      p.y = Math.max(0, Math.min(canvas.height, p.y))
      ctx.fillStyle = p.col + '0.6)'
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill()
    })

    links.forEach(c => {
      c.life++
      if (c.life > 200) {
        c.a = Math.floor(Math.random() * pts.length)
        c.b = Math.floor(Math.random() * pts.length)
        c.life = 0
      }
      const a = pts[c.a], b = pts[c.b]
      const dx = b.x - a.x, dy = b.y - a.y
      const d  = Math.sqrt(dx * dx + dy * dy)
      if (d < 150) {
        ctx.strokeStyle = `rgba(32,214,199,${0.1 * (1 - d / 150)})`
        ctx.lineWidth = 0.5
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
      }
    })

    this.animId = requestAnimationFrame(() => this._frame())
  }
}

document.addEventListener('DOMContentLoaded', init)
