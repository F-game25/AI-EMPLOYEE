let state = 'checking'
const particles = new ParticleSystem()

// DOM elements
const startBtn = document.getElementById('startBtn')
const stopBtn = document.getElementById('stopBtn')
const openBtn = document.getElementById('openBtn')
const logArea = document.getElementById('logArea')
const versionBadge = document.getElementById('version')
const updateBadge = document.getElementById('updateBadge')
const cancelBtn = document.getElementById('cancelBtn')

async function init() {
  particles.init()

  const deps = await window.ai.checkDependencies()

  if (!deps.setup_complete || !deps.node || !deps.python) {
    setState('setup')
    renderSetupScreen(deps)
    return
  }

  const status = await window.ai.checkStatus()
  const version = await window.ai.getVersion()
  const updates = await window.ai.checkUpdates()

  updateVersionBadge(version)
  if (updates.update_available) showUpdateBadge()

  setState(status.running ? 'idle-running' : 'idle')
  setupEventListeners()
}

function setState(newState) {
  state = newState
  document.body.className = newState === 'idle-running' ? 'idle' : newState
  updateButtonStates()
}

function updateButtonStates() {
  const isRunning = state === 'idle-running' || state === 'idle'
  const isStarting = state === 'starting'

  startBtn.disabled = isRunning || isStarting
  openBtn.disabled = !isRunning
  stopBtn.disabled = isStarting || state === 'checking'
  cancelBtn.disabled = false
}

function updateVersionBadge(versionInfo) {
  const commit = versionInfo.last_commit || versionInfo.last_installed_commit || 'unknown'
  versionBadge.textContent = commit.slice(0, 7)
}

function showUpdateBadge() {
  updateBadge.style.display = 'flex'
}

function setupEventListeners() {
  startBtn.addEventListener('click', handleStart)
  stopBtn.addEventListener('click', handleStop)
  openBtn.addEventListener('click', handleOpen)
  cancelBtn.addEventListener('click', handleCancel)
}

async function handleStart() {
  setState('starting')
  logArea.innerHTML = ''

  window.ai.onStartLog(line => appendLog(line))
  window.ai.onStartReady(() => {
    setState('ready')
    setTimeout(() => {
      setState('idle-running')
    }, 2000)
  })
  window.ai.onStartError(msg => {
    appendLog('[ERROR] ' + msg)
    setState('idle')
  })

  try {
    await window.ai.startSystem()
  } catch (err) {
    appendLog('[ERROR] Failed to start system: ' + err.message)
    setState('idle')
  }
}

async function handleStop() {
  startBtn.disabled = true
  const result = await window.ai.stopSystem()
  if (result.success) {
    setState('idle')
  }
}

async function handleOpen() {
  document.body.className = 'opening'
  await window.ai.openInterface()
}

function handleCancel() {
  setState('idle')
}

function renderSetupScreen(deps) {
  const depList = document.getElementById('depList')
  const items = [
    { key: 'node', label: 'Node.js', ok: deps.node, version: deps.node_version },
    { key: 'python', label: 'Python 3', ok: deps.python, version: deps.python_version },
    { key: 'npm_packages', label: 'npm packages', ok: deps.npm_packages },
    { key: 'pip_packages', label: 'Python packages', ok: deps.pip_packages },
  ]

  depList.innerHTML = items.map(item => `
    <div class="dep-item ${item.ok ? 'dep-ok' : 'dep-missing'}">
      <span class="dep-icon">${item.ok ? '✓' : '✗'}</span>
      <span class="dep-name">${item.label}</span>
      <span class="dep-status">${item.ok ? (item.version || 'OK') : 'MISSING'}</span>
      ${!item.ok && (item.key === 'node' || item.key === 'python') ? `<a href="#" class="dep-download" data-dep="${item.key}">Download →</a>` : ''}
    </div>
  `).join('')

  const installBtn = document.getElementById('installDepsBtn')
  const setupLog = document.getElementById('setupLog')
  const setupActions = document.getElementById('setupActions')

  installBtn.addEventListener('click', async () => {
    installBtn.disabled = true
    setupLog.style.display = 'block'
    setupLog.innerHTML = '<div style="color: var(--text-secondary);">Installing dependencies...</div>'

    const types = ['npm', 'pip']
    for (const type of types) {
      await window.ai.runDependencyInstall(type)
    }

    setupLog.innerHTML += '<div style="color: var(--success); margin-top: 8px;">✓ Dependencies installed successfully</div>'
    setupLog.innerHTML += '<div style="color: var(--text-dim); margin-top: 8px; font-size: 9px;">Reloading in 2 seconds...</div>'

    await window.ai.markSetupComplete()
    setTimeout(() => location.reload(), 2000)
  })

  window.ai.onSetupLog(line => {
    const entry = document.createElement('div')
    entry.textContent = line
    setupLog.appendChild(entry)
    setupLog.scrollTop = setupLog.scrollHeight
  })
}

function appendLog(line) {
  const entry = document.createElement('div')
  entry.textContent = line
  logArea.appendChild(entry)
  logArea.scrollTop = logArea.scrollHeight
}

// PARTICLE SYSTEM
class ParticleSystem {
  constructor() {
    this.canvas = document.getElementById('particles')
    this.ctx = this.canvas.getContext('2d')
    this.particles = []
    this.connections = []
    this.animId = null

    this.resizeCanvas()
    window.addEventListener('resize', () => this.resizeCanvas())
  }

  resizeCanvas() {
    this.canvas.width = window.innerWidth
    this.canvas.height = window.innerHeight
  }

  init() {
    this.particles = []
    for (let i = 0; i < 30; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        radius: Math.random() * 1.5 + 0.5,
        color: Math.random() > 0.5 ? 'rgba(32,214,199,' : 'rgba(229,199,107,',
      })
    }

    // Create 3 random connections
    for (let i = 0; i < 3; i++) {
      const a = Math.floor(Math.random() * this.particles.length)
      const b = Math.floor(Math.random() * this.particles.length)
      if (a !== b) this.connections.push({ a, b, life: 0 })
    }

    this.animate()
  }

  animate() {
    this.ctx.fillStyle = 'rgba(7,8,16,1)'
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height)

    // Update particles
    this.particles.forEach(p => {
      p.x += p.vx
      p.y += p.vy

      if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1
      if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1

      p.x = Math.max(0, Math.min(this.canvas.width, p.x))
      p.y = Math.max(0, Math.min(this.canvas.height, p.y))

      this.ctx.fillStyle = p.color + '0.6)'
      this.ctx.beginPath()
      this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      this.ctx.fill()
    })

    // Draw connections
    this.connections.forEach(c => {
      const a = this.particles[c.a]
      const b = this.particles[c.b]
      c.life += 1

      if (c.life > 200) {
        c.a = Math.floor(Math.random() * this.particles.length)
        c.b = Math.floor(Math.random() * this.particles.length)
        c.life = 0
      }

      const dx = b.x - a.x
      const dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist < 150) {
        this.ctx.strokeStyle = `rgba(32,214,199,${0.1 * (1 - dist / 150)})`
        this.ctx.lineWidth = 0.5
        this.ctx.beginPath()
        this.ctx.moveTo(a.x, a.y)
        this.ctx.lineTo(b.x, b.y)
        this.ctx.stroke()
      }
    })

    this.animId = requestAnimationFrame(() => this.animate())
  }
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', init)
