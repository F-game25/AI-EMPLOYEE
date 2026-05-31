const { spawn } = require('child_process')
const { EventEmitter } = require('events')
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const http = require('http')
const net = require('net')
const { PATHS } = require('./paths')
const { loadPolicy } = require('./policy')
const { resolvePython } = require('./first_boot')

const MAX_LIVE_LOG_LINES = 500

function stripAnsi(s) {
  return String(s || '').replace(/\x1B\[[0-9;]*[mGKHF]/g, '').replace(/[─-╿▀-▟]/g, '').trim()
}

function cleanLogLine(line) {
  if (/^(npm warn|npm notice|added \d+|audited \d+|found \d+|up to date|\[=+>*\s*\])/.test(line)) return null
  if (/^(Collecting|Downloading|Installing|Building|Successfully installed|Requirement already)/.test(line)) return null
  if (/^(Creating egg|running setup\.py|running build)/.test(line)) return null
  return line
}

function portOpen(port, host = '127.0.0.1', timeoutMs = 350) {
  return new Promise(resolve => {
    const socket = new net.Socket()
    let done = false
    const finish = (open) => {
      if (done) return
      done = true
      try { socket.destroy() } catch {}
      resolve(open)
    }
    socket.setTimeout(timeoutMs)
    socket.once('connect', () => finish(true))
    socket.once('timeout', () => finish(false))
    socket.once('error', () => finish(false))
    socket.connect(port, host)
  })
}

function httpJson(url, timeoutMs = 900) {
  return new Promise(resolve => {
    const req = http.get(url, { timeout: timeoutMs }, res => {
      let body = ''
      res.setEncoding('utf8')
      res.on('data', chunk => { if (body.length < 50000) body += chunk })
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 400) return resolve(null)
        try { resolve(JSON.parse(body)) } catch { resolve(null) }
      })
      res.resume()
    })
    req.on('timeout', () => { req.destroy(); resolve(null) })
    req.on('error', () => resolve(null))
  })
}

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return null }
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

function processAlive(pid) {
  if (!pid) return false
  try {
    process.kill(Number(pid), 0)
    return true
  } catch {
    return false
  }
}

function isOwnedLock(lock) {
  return lock?.routeId === 'local-packaged-runtime' &&
    lock?.repoDir === PATHS.repoDir &&
    lock?.appHome === PATHS.appHome &&
    typeof lock?.nonce === 'string' &&
    lock.nonce.length >= 16
}

function lockPorts(lock, desiredNode, desiredPython) {
  return {
    nodePort: Number(lock?.ports?.node || desiredNode),
    pythonPort: Number(lock?.ports?.python || desiredPython),
  }
}

function lockAgeMs(lock) {
  const ts = Date.parse(lock?.startedAt || '')
  return Number.isFinite(ts) ? Date.now() - ts : Infinity
}

function loadDotEnv(file) {
  const values = {}
  try {
    const text = fs.readFileSync(file, 'utf8')
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const idx = trimmed.indexOf('=')
      if (idx <= 0) continue
      const key = trimmed.slice(0, idx).trim()
      let value = trimmed.slice(idx + 1).trim()
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1)
      }
      values[key] = value
    }
  } catch {}
  return values
}

function ensureJwtSecret(appHome) {
  const envFile = path.join(appHome, '.env')
  const values = loadDotEnv(envFile)
  if (process.env.JWT_SECRET_KEY || values.JWT_SECRET_KEY) {
    return process.env.JWT_SECRET_KEY || values.JWT_SECRET_KEY
  }
  const secret = crypto.randomBytes(32).toString('hex')
  fs.mkdirSync(appHome, { recursive: true })
  fs.appendFileSync(envFile, `${fs.existsSync(envFile) ? '\n' : ''}JWT_SECRET_KEY=${secret}\n`)
  return secret
}

class BackendManager extends EventEmitter {
  constructor() {
    super()
    this.activeProc = null
    this.serviceProcs = []
    this.liveLogLines = []
    this.launch = null
  }

  appendLog(text, level = 'info') {
    const cleaned = String(text || '').trim()
    if (!cleaned) return
    const entry = { ts: Date.now(), line: cleaned, level }
    this.liveLogLines.push(entry)
    if (this.liveLogLines.length > MAX_LIVE_LOG_LINES) {
      this.liveLogLines.splice(0, this.liveLogLines.length - MAX_LIVE_LOG_LINES)
    }
    this.emit('log', entry)
  }

  /**
   * Spawn start.sh. Streams logs via 'log' events; emits 'exit' when done.
   * `extraEnv` allows the diagnostic "RESTART WITH VERBOSE" path to set
   * LOG_LEVEL=DEBUG, STRICT_PIPELINE=1, etc.
   */
  buildEnv(extraEnv = {}) {
    const packagedRuntime = Boolean(
      process.resourcesPath && PATHS.repoDir.startsWith(process.resourcesPath)
    )
    const policy = loadPolicy({ allowEnvOverride: !packagedRuntime })
    const dotenv = loadDotEnv(path.join(PATHS.appHome, '.env'))
    const jwtSecret = ensureJwtSecret(PATHS.appHome)
    const env = {
      ...process.env,
      ...dotenv,
      ...extraEnv,
      JWT_SECRET_KEY: extraEnv.JWT_SECRET_KEY || process.env.JWT_SECRET_KEY || dotenv.JWT_SECRET_KEY || jwtSecret,
      AI_EMPLOYEE_OFFLINE: policy.network?.offlineByDefault === false ? '0' : '1',
      AI_EMPLOYEE_ALLOW_DEP_INSTALL: policy.network?.allowDependencyInstall ? '1' : '0',
      AI_EMPLOYEE_ALLOW_MODEL_DOWNLOADS: policy.network?.allowModelDownloads ? '1' : '0',
      AI_EMPLOYEE_ALLOW_AUTO_UPDATE: policy.network?.allowAutoUpdate ? '1' : '0',
      LISTEN_HOST: policy.security?.bindHost || '127.0.0.1',
      MONEY_MODE_REQUIRE_APPROVAL: policy.security?.requireApprovalForMoneyMode === false ? '0' : '1',
      AI_HOME: PATHS.appHome,
      AI_EMPLOYEE_HOME: PATHS.appHome,
      STATE_DIR: PATHS.stateDir,
      LOG_DIR: PATHS.logDir,
      RUN_DIR: PATHS.runDir,
      AI_EMPLOYEE_PACKAGED: packagedRuntime ? '1' : '0',
      PLAYWRIGHT_BROWSERS_PATH: path.join(PATHS.repoDir, 'runtime', 'browsers', 'playwright'),
    }
    if (packagedRuntime) {
      env.NODE_BIN = process.execPath
      env.AI_EMPLOYEE_NODE_RUN_AS_NODE = '1'
    }
    return env
  }

  buildPublicEnv() {
    const dotenv = loadDotEnv(path.join(PATHS.appHome, '.env'))
    return {
      JWT_SECRET_KEY: process.env.JWT_SECRET_KEY || dotenv.JWT_SECRET_KEY || null,
    }
  }

  start({ extraEnv = {} } = {}) {
    this.serviceProcs = this.serviceProcs.filter(p => !p.killed && p.exitCode === null)
    if (this.activeProc || this.serviceProcs.length) {
      this.appendLog('Startup already in progress', 'warn')
      return Promise.resolve(this.launch || { alreadyRunning: true })
    }
    if (process.env.AI_EMPLOYEE_DEV_SCRIPTS === '1' && process.platform !== 'win32') {
      return this.startViaScript({ extraEnv })
    }
    return this.startDirect({ extraEnv })
  }

  startViaScript({ extraEnv = {} } = {}) {
    return new Promise((resolve, reject) => {
      const env = this.buildEnv(extraEnv)
      const proc = spawn('bash', ['start.sh'], {
        cwd: PATHS.repoDir,
        stdio: 'pipe',
        env,
      })
      this.activeProc = proc

      const forward = (raw, isError) => {
        String(raw).split('\n').forEach(line => {
          const cleaned = cleanLogLine(stripAnsi(line))
          if (!cleaned) return
          const level = isError ? 'error' : 'info'
          this.appendLog(cleaned, level)
          // Emit semantic events when key milestones are detected
          const lower = cleaned.toLowerCase()
          if (lower.includes('python ai backend')) this.emit('milestone', { phase: 'python-spawn', text: cleaned })
          if (lower.includes('starting unified runtime') || lower.includes('node ')) this.emit('milestone', { phase: 'node-spawn', text: cleaned })
          if (lower.includes('system running') || lower.includes('listening on')) this.emit('milestone', { phase: 'backend-ready', text: cleaned })
        })
      }

      proc.stdout.on('data', d => forward(d, false))
      proc.stderr.on('data', d => forward(d, true))

      proc.on('exit', code => {
        const expected = this._expectedStop
        this._expectedStop = false
        this.activeProc = null
        this.emit('exit', { code, expected })
        resolve({ code, expected })
      })
      proc.on('error', err => {
        this.activeProc = null
        this.appendLog(`spawn error: ${err.message}`, 'error')
        this.emit('error', err)
        reject(err)
      })
    })
  }

  lockFile() {
    return path.join(PATHS.runDir, 'runtime-lock.json')
  }

  async choosePorts(env, nonce) {
    const host = env.LISTEN_HOST || '127.0.0.1'
    const desiredNode = Number.parseInt(env.PROBLEM_SOLVER_UI_PORT || env.PORT || '8787', 10)
    const desiredPython = Number.parseInt(env.PYTHON_BACKEND_PORT || env.AI_BACKEND_PORT || '18790', 10)
    const lock = readJson(this.lockFile())

    if (lock && isOwnedLock(lock)) {
      const { nodePort, pythonPort } = lockPorts(lock, desiredNode, desiredPython)
      const anyPidAlive = Object.values(lock.pids || {}).some(pid => processAlive(pid))
      const nodePortOpen = await portOpen(nodePort, host)
      const identity = await httpJson(`http://${host}:${nodePort}/api/runtime/identity`)
      const health = await httpJson(`http://${host}:${nodePort}/api/health`)
      const identityMatches = identity?.app === 'AETERNUS NEXUS' && identity?.nonce === lock.nonce
      const runtimeLooksAlive = nodePortOpen && (identityMatches || health?.status === 'ok' || health?.node_ok === true)
      const runtimeStillBooting = anyPidAlive && lockAgeMs(lock) < 120000
      if (runtimeLooksAlive || runtimeStillBooting) {
        return {
          reused: true,
          nonce: lock.nonce,
          nodePort,
          pythonPort,
          host,
          identityMatched: identityMatches,
        }
      }
    }

    const ownIdentity = await httpJson(`http://${host}:${desiredNode}/api/runtime/identity`)
    if (ownIdentity?.app === 'AETERNUS NEXUS' && lock?.nonce && ownIdentity.nonce === lock.nonce) {
      return {
        reused: true,
        nonce: lock.nonce,
        nodePort: Number(lock.ports?.node || desiredNode),
        pythonPort: Number(lock.ports?.python || desiredPython),
        host,
      }
    }

    let nodePort = desiredNode
    if (await portOpen(nodePort, host)) {
      for (let port = desiredNode + 1; port < desiredNode + 25; port++) {
        if (!(await portOpen(port, host))) {
          nodePort = port
          break
        }
      }
    }

    let pythonPort = desiredPython
    if (await portOpen(pythonPort, host)) {
      for (let port = desiredPython + 1; port < desiredPython + 25; port++) {
        if (!(await portOpen(port, host)) && port !== nodePort) {
          pythonPort = port
          break
        }
      }
    }

    return { reused: false, nonce, nodePort, pythonPort, host }
  }

  async cleanupOwnedRuntimeIfStale(env) {
    const host = env.LISTEN_HOST || '127.0.0.1'
    const desiredNode = Number.parseInt(env.PROBLEM_SOLVER_UI_PORT || env.PORT || '8787', 10)
    const desiredPython = Number.parseInt(env.PYTHON_BACKEND_PORT || env.AI_BACKEND_PORT || '18790', 10)
    const lock = readJson(this.lockFile())

    if (!isOwnedLock(lock)) {
      for (const pidFile of ['backend.pid', 'python-backend.pid']) {
        try {
          const pid = Number(fs.readFileSync(path.join(PATHS.runDir, pidFile), 'utf8').trim())
          if (!processAlive(pid)) fs.unlinkSync(path.join(PATHS.runDir, pidFile))
        } catch {}
      }
      return false
    }

    const { nodePort } = lockPorts(lock, desiredNode, desiredPython)
    const anyPidAlive = Object.values(lock.pids || {}).some(pid => processAlive(pid))
    const nodePortOpen = await portOpen(nodePort, host)
    const identity = await httpJson(`http://${host}:${nodePort}/api/runtime/identity`)
    const health = await httpJson(`http://${host}:${nodePort}/api/health`)
    const identityMatches = identity?.app === 'AETERNUS NEXUS' && identity?.nonce === lock.nonce
    const runtimeHealthy = nodePortOpen && (identityMatches || health?.status === 'ok' || health?.node_ok === true)
    if (anyPidAlive && lockAgeMs(lock) < 120000) return false
    if (runtimeHealthy) return false

    let killedAny = false
    for (const [name, pid] of Object.entries(lock.pids || {})) {
      if (!processAlive(pid)) continue
      try {
        process.kill(Number(pid), 'SIGTERM')
        killedAny = true
        this.appendLog(`[launcher] Sent SIGTERM to stale owned ${name} PID ${pid}`, 'warn')
      } catch {}
    }
    for (const pidFile of ['backend.pid', 'python-backend.pid']) {
      try { fs.unlinkSync(path.join(PATHS.runDir, pidFile)) } catch {}
    }
    try { fs.unlinkSync(this.lockFile()) } catch {}
    if (killedAny) await new Promise(r => setTimeout(r, 500))
    return killedAny
  }

  buildLaunchResult(route, pids = {}, commands = {}) {
    const uiOrigin = `http://${route.host}:${route.nodePort}`
    return {
      routeId: 'local-packaged-runtime',
      platform: process.platform,
      arch: process.arch,
      packaged: Boolean(process.resourcesPath && PATHS.repoDir.startsWith(process.resourcesPath)),
      appHome: PATHS.appHome,
      repoDir: PATHS.repoDir,
      dashboardUrl: `${uiOrigin}/?electron=1`,
      uiOrigin,
      ports: { node: route.nodePort, python: route.pythonPort },
      pids,
      commands,
      nonce: route.nonce,
      startedAt: new Date().toISOString(),
    }
  }

  async startDirect({ extraEnv = {} } = {}) {
    const env = this.buildEnv(extraEnv)
    fs.mkdirSync(PATHS.logDir, { recursive: true })
    fs.mkdirSync(PATHS.runDir, { recursive: true })

    await this.cleanupOwnedRuntimeIfStale(env)

    const route = await this.choosePorts(env, crypto.randomBytes(16).toString('hex'))
    if (route.reused) {
      const pythonAlive = await portOpen(route.pythonPort, route.host)
      this.launch = this.buildLaunchResult(route, readJson(this.lockFile())?.pids || {}, readJson(this.lockFile())?.commands || {})
      this.appendLog(`Reusing owned runtime at ${this.launch.dashboardUrl}${pythonAlive ? '' : ' (Python backend degraded)'}`)
      return { ...this.launch, alreadyRunning: true, reused: true, degradedPython: !pythonAlive }
    }
    this.cancel()

    const spawnService = (name, command, args, serviceEnv, logFile, pidFile) => {
      const logStream = fs.createWriteStream(path.join(PATHS.logDir, logFile), { flags: 'a' })
      const child = spawn(command, args, {
        cwd: PATHS.repoDir,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env: { ...env, ...serviceEnv },
      })
      child.stdout.on('data', d => {
        logStream.write(d)
        String(d).split('\n').forEach(line => {
          const cleaned = cleanLogLine(stripAnsi(line))
          if (cleaned) this.appendLog(`[${name}] ${cleaned}`)
        })
      })
      child.stderr.on('data', d => {
        logStream.write(d)
        String(d).split('\n').forEach(line => {
          const cleaned = cleanLogLine(stripAnsi(line))
          if (cleaned) this.appendLog(`[${name}] ${cleaned}`, 'error')
        })
      })
      child.on('exit', code => {
        logStream.end()
        this.appendLog(`[${name}] exited with code ${code}`, code === 0 ? 'info' : 'error')
        const idx = this.serviceProcs.indexOf(child)
        if (idx !== -1) this.serviceProcs.splice(idx, 1)
        this.emit('child-exit', { name, code })
      })
      child.on('error', err => {
        logStream.end()
        this.appendLog(`[${name}] spawn error: ${err.message}`, 'error')
      })
      fs.writeFileSync(path.join(PATHS.runDir, pidFile), String(child.pid || ''))
      this.serviceProcs.push(child)
      return child
    }

    const python = resolvePython()
    const pids = {}
    const commands = {}
    if (python.command) {
      const pythonProc = spawnService(
        'python',
        python.command,
        [...python.argsPrefix, path.join(PATHS.repoDir, 'runtime', 'agents', 'problem-solver-ui', 'server.py')],
        {
          PROBLEM_SOLVER_UI_PORT: String(route.pythonPort),
          PYTHON_BACKEND_PORT: String(route.pythonPort),
          PROBLEM_SOLVER_UI_HOST: '127.0.0.1',
          AI_EMPLOYEE_REPO_DIR: PATHS.repoDir,
        },
        'python-backend.log',
        'python-backend.pid'
      )
      pids.python = pythonProc.pid || null
      commands.python = python.command
      this.emit('milestone', { phase: 'python-spawn', text: 'Python AI backend spawned' })
    } else {
      this.appendLog('python runtime not found; Python AI backend unavailable', 'warn')
    }

    const nodeEnv = {
      ...env,
      ELECTRON_RUN_AS_NODE: '1',
      PORT: String(route.nodePort),
      PROBLEM_SOLVER_UI_PORT: String(route.nodePort),
      PYTHON_BACKEND_PORT: String(route.pythonPort),
      LISTEN_HOST: env.LISTEN_HOST || '127.0.0.1',
      AI_EMPLOYEE_RUNTIME_NONCE: route.nonce,
      AI_EMPLOYEE_RUNTIME_MODE: 'local-packaged-runtime',
    }
    const nodeProc = spawnService(
      'node',
      process.execPath,
      [path.join(PATHS.repoDir, 'backend', 'server.js')],
      nodeEnv,
      'server.log',
      'backend.pid'
    )
    pids.node = nodeProc.pid || null
    commands.node = process.execPath
    this.launch = this.buildLaunchResult(route, pids, commands)
    writeJson(this.lockFile(), this.launch)
    try {
      const health = require('./health')
      health.configureRuntimeRoute({
        nodePort: route.nodePort,
        pythonPort: route.pythonPort,
        host: route.host,
        uiOrigin: this.launch.uiOrigin,
        dashboardUrl: this.launch.dashboardUrl,
        nonce: route.nonce,
      })
    } catch {}
    this.emit('milestone', { phase: 'node-spawn', text: 'Node gateway spawned' })
    return this.launch
  }

  /** Kill the running start.sh, if any. Marks the exit as user-initiated. */
  cancel() {
    this._expectedStop = true
    let cancelled = false
    try {
      for (const proc of this.serviceProcs.splice(0)) {
        if (!proc.killed) proc.kill('SIGTERM')
      }
      const lock = readJson(this.lockFile())
      for (const pid of Object.values(isOwnedLock(lock) ? (lock.pids || {}) : {})) {
        if (processAlive(pid)) {
          try { process.kill(Number(pid), 'SIGTERM') } catch {}
        }
      }
      for (const pidFile of ['backend.pid', 'python-backend.pid']) {
        try { fs.unlinkSync(path.join(PATHS.runDir, pidFile)) } catch {}
      }
      try { fs.unlinkSync(this.lockFile()) } catch {}
      this.launch = null
      cancelled = true
    } catch { /* ignore */ }
    if (!this.activeProc) return cancelled
    try {
      this.activeProc.kill('SIGTERM')
      const proc = this.activeProc
      setTimeout(() => {
        if (proc && !proc.killed) proc.kill('SIGKILL')
      }, 2500)
    } catch { /* ignore */ }
    this.activeProc = null
    return true
  }

  /** Spawn stop.sh and wait for it to exit. */
  stop() {
    this._expectedStop = true
    this.cancel()
    if (process.env.AI_EMPLOYEE_DEV_SCRIPTS !== '1' || process.platform === 'win32') {
      return Promise.resolve({ code: 0, direct: true })
    }
    return new Promise((resolve, reject) => {
      const proc = spawn('bash', ['stop.sh'], {
        cwd: PATHS.repoDir,
        stdio: 'pipe',
        env: {
          ...process.env,
          AI_HOME: PATHS.appHome,
          AI_EMPLOYEE_HOME: PATHS.appHome,
          STATE_DIR: PATHS.stateDir,
          LOG_DIR: PATHS.logDir,
          RUN_DIR: PATHS.runDir,
        },
      })
      proc.on('exit', code => resolve({ code }))
      proc.on('error', err => reject(err))
    })
  }

  /** Last `n` log lines for diagnostics screen. */
  tailLogs(n = 20) {
    return this.liveLogLines.slice(-n)
  }
}

module.exports = { BackendManager, cleanLogLine, stripAnsi, MAX_LIVE_LOG_LINES }
