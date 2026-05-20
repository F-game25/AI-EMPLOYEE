const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')
const { app } = require('electron')
const { PATHS } = require('./paths')
const { loadPolicy } = require('./policy')

function canRun(command, args = ['--version']) {
  try {
    return execFileSync(command, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return null
  }
}

function bundledPythonCandidates() {
  const candidates = []
  if (process.env.AI_EMPLOYEE_BUNDLED_PYTHON) candidates.push(process.env.AI_EMPLOYEE_BUNDLED_PYTHON)
  const exe = process.platform === 'win32' ? 'python.exe' : 'bin/python'
  const roots = [
    path.join(PATHS.repoDir, 'runtime', 'python'),
    process.resourcesPath ? path.join(process.resourcesPath, 'python') : null,
    process.resourcesPath ? path.join(process.resourcesPath, 'repo', 'runtime', 'python') : null,
  ].filter(Boolean)
  const names = [
    `${process.platform}-${process.arch}`,
    process.platform,
    'current',
  ]
  for (const root of roots) {
    for (const name of names) {
      candidates.push(path.join(root, name, exe))
    }
  }
  return [...new Set(candidates)]
}

function loadPythonRuntimeManifest() {
  const manifestPaths = [
    path.join(PATHS.repoDir, 'runtime', 'config', 'python_runtime_manifest.json'),
    process.resourcesPath ? path.join(process.resourcesPath, 'python', 'python_runtime_manifest.json') : null,
  ].filter(Boolean)
  for (const manifestPath of manifestPaths) {
    try {
      return { path: manifestPath, manifest: JSON.parse(fs.readFileSync(manifestPath, 'utf8')) }
    } catch {}
  }
  return { path: null, manifest: null }
}

function sha256(file) {
  const crypto = require('crypto')
  const hash = crypto.createHash('sha256')
  hash.update(fs.readFileSync(file))
  return hash.digest('hex')
}

function verifyBundledPython(command) {
  const { manifest } = loadPythonRuntimeManifest()
  if (!manifest || !Array.isArray(manifest.runtimes)) return { ok: true, reason: 'no manifest' }
  const expected = manifest.runtimes.find(item => {
    if (!item) return false
    const platformOk = !item.platform || item.platform === process.platform
    const archOk = !item.arch || item.arch === process.arch
    return platformOk && archOk
  })
  if (!expected?.sha256) return { ok: true, reason: 'no hash for platform' }
  try {
    const actual = sha256(command)
    return actual === expected.sha256
      ? { ok: true, sha256: actual }
      : { ok: false, reason: 'sha256 mismatch', expected: expected.sha256, actual }
  } catch (error) {
    return { ok: false, reason: error.message }
  }
}

function resolveBundledPython() {
  for (const command of bundledPythonCandidates()) {
    if (!fs.existsSync(command)) continue
    const verification = verifyBundledPython(command)
    if (!verification.ok) {
      return { command: null, argsPrefix: [], version: null, bundled: true, verification }
    }
    const version = canRun(command, ['--version'])
    if (version) return { command, argsPrefix: [], version, bundled: true, verification }
  }
  return { command: null, argsPrefix: [], version: null, bundled: true, verification: { ok: false, reason: 'bundled runtime not found' } }
}

function resolvePython() {
  if (process.env.PYTHON_BIN) {
    const version = canRun(process.env.PYTHON_BIN, ['--version'])
    if (version) return { command: process.env.PYTHON_BIN, argsPrefix: [], version }
  }

  const localCorePython = process.platform === 'win32'
    ? path.join(PATHS.appHome, 'python-core', 'Scripts', 'python.exe')
    : path.join(PATHS.appHome, 'python-core', 'bin', 'python')
  if (fs.existsSync(localCorePython)) {
    const version = canRun(localCorePython, ['--version'])
    if (version) return { command: localCorePython, argsPrefix: [], version, bundled: true }
  }

  const bundledPython = resolveBundledPython()
  if (bundledPython.command) return bundledPython

  if (process.platform === 'win32') {
    const pyVersion = canRun('py', ['-3', '--version'])
    if (pyVersion) return { command: 'py', argsPrefix: ['-3'], version: pyVersion }
    const pythonVersion = canRun('python', ['--version'])
    if (pythonVersion) return { command: 'python', argsPrefix: [], version: pythonVersion }
  }

  const python3Version = canRun('python3', ['--version'])
  if (python3Version) return { command: 'python3', argsPrefix: [], version: python3Version }
  const pythonVersion = canRun('python', ['--version'])
  if (pythonVersion) return { command: 'python', argsPrefix: [], version: pythonVersion }
  return { command: null, argsPrefix: [], version: null }
}

function hasBundledWheelhouse() {
  const root = path.join(PATHS.repoDir, 'runtime', 'wheelhouse')
  try {
    return fs.readdirSync(root, { withFileTypes: true }).some(entry => {
      if (!entry.isDirectory()) return false
      const dir = path.join(root, entry.name)
      return fs.readdirSync(dir).some(name => name.endsWith('.whl'))
    })
  } catch {
    return false
  }
}

function bootstrapPythonCore(python) {
  const script = path.join(PATHS.repoDir, 'scripts', 'bootstrap_python_core.py')
  if (!python.command || !fs.existsSync(script) || !hasBundledWheelhouse()) {
    return { attempted: false, ok: false, reason: 'bootstrap script or wheelhouse unavailable' }
  }
  try {
    const output = execFileSync(
      python.command,
      [...python.argsPrefix, script, '--quiet', '--json'],
      {
        cwd: PATHS.repoDir,
        encoding: 'utf8',
        maxBuffer: 1024 * 1024 * 10,
        env: {
          ...process.env,
          AI_HOME: PATHS.appHome,
          AI_EMPLOYEE_HOME: PATHS.appHome,
        },
      }
    )
    return { attempted: true, ok: true, result: JSON.parse(output) }
  } catch (error) {
    return {
      attempted: true,
      ok: false,
      reason: error.message,
      output: String(error.stdout || error.stderr || '').slice(-4000),
    }
  }
}

function hasPythonPackage(python, packageName) {
  if (!python.command) return false
  try {
    execFileSync(
      python.command,
      [...python.argsPrefix, '-c', 'import importlib, sys; importlib.import_module(sys.argv[1])', packageName],
      { stdio: 'ignore' }
    )
    return true
  } catch {
    return false
  }
}

function loadCoreDependencyManifest() {
  const manifestPath = path.join(PATHS.repoDir, 'runtime', 'config', 'core_dependency_manifest.json')
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
    return {
      path: manifestPath,
      core: Array.isArray(manifest.core) ? manifest.core : [],
      security_requirements: Array.isArray(manifest.security_requirements) ? manifest.security_requirements : [],
      error: null,
    }
  } catch (error) {
    return {
      path: manifestPath,
      core: [],
      security_requirements: [],
      error: error.message,
    }
  }
}

function checkCorePythonDependencies(python, manifest) {
  if (manifest.error) {
    return {
      ok: false,
      missing: [{ import: 'core_dependency_manifest', pip: manifest.path, error: manifest.error }],
      checked: 0,
    }
  }

  const missing = []
  for (const item of manifest.core) {
    if (!item || !item.import) continue
    if (!hasPythonPackage(python, item.import)) {
      missing.push({
        import: item.import,
        pip: item.pip || item.import,
        purpose: item.purpose || '',
      })
    }
  }

  return {
    ok: missing.length === 0,
    missing,
    checked: manifest.core.length,
  }
}

function writeSetupComplete(report) {
  fs.mkdirSync(path.dirname(PATHS.setupCompleteFile), { recursive: true })
  fs.writeFileSync(PATHS.setupCompleteFile, JSON.stringify({
    completed_at: new Date().toISOString(),
    report,
  }, null, 2))
}

function checkFirstBoot() {
  const packaged = app?.isPackaged || process.env.AI_EMPLOYEE_PACKAGED === '1'
  const policy = loadPolicy({ allowEnvOverride: !packaged })
  const offline = policy.network?.offlineByDefault !== false
  const bundledPython = resolveBundledPython()
  let python = resolvePython()
  const coreDependencyManifest = loadCoreDependencyManifest()
  let corePythonDependencies = checkCorePythonDependencies(python, coreDependencyManifest)
  let pythonCoreBootstrap = { attempted: false, ok: false, reason: 'not needed' }

  if (!corePythonDependencies.ok) {
    pythonCoreBootstrap = bootstrapPythonCore(python)
    if (pythonCoreBootstrap.ok) {
      python = resolvePython()
      corePythonDependencies = checkCorePythonDependencies(python, coreDependencyManifest)
    }
  }

  const checks = {
    node_runtime: Boolean(process.execPath),
    backend_package: fs.existsSync(path.join(PATHS.repoDir, 'backend', 'package.json')),
    backend_node_modules: fs.existsSync(path.join(PATHS.repoDir, 'backend', 'node_modules')) ||
      fs.existsSync(path.join(PATHS.repoDir, 'node_modules')),
    frontend_dist: fs.existsSync(path.join(PATHS.repoDir, 'frontend', 'dist', 'index.html')),
    start_script: process.platform === 'win32' || fs.existsSync(PATHS.startScript()),
    stop_script: process.platform === 'win32' || fs.existsSync(PATHS.stopScript()),
    bundled_python: packaged ? Boolean(bundledPython.command) : true,
    bundled_python_verified: packaged ? bundledPython.verification?.ok === true : true,
    python: Boolean(python.command),
    pip_fastapi: hasPythonPackage(python, 'fastapi'),
    python_core_dependencies: corePythonDependencies.ok,
  }

  const required = [
    'node_runtime',
    'backend_package',
    'backend_node_modules',
    'frontend_dist',
    ...(packaged ? [] : ['start_script', 'stop_script']),
    ...(packaged ? ['bundled_python', 'bundled_python_verified'] : []),
    'python',
    'python_core_dependencies',
  ]
  const missing = required.filter(name => !checks[name])
  const installAllowed = !packaged && !offline && policy.network?.allowDependencyInstall === true
  const setupComplete = missing.length === 0

  const report = {
    setup_complete: setupComplete,
    setup_marker_exists: fs.existsSync(PATHS.setupCompleteFile),
    local_runtime_ready: setupComplete,
    packaged,
    offline,
    install_allowed: installAllowed,
    install_reason: installAllowed
      ? 'policy allows online dependency installation in development mode'
      : packaged
        ? 'packaged app must ship with all runtime artifacts'
        : offline
          ? 'offline mode blocks dependency installation'
          : 'policy blocks dependency installation',
    platform: process.platform,
    appHome: PATHS.appHome,
    repoDir: PATHS.repoDir,
    python,
    bundled_python: bundledPython,
    python_runtime_manifest: loadPythonRuntimeManifest().path,
    core_dependency_manifest: coreDependencyManifest.path,
    core_dependency_manifest_error: coreDependencyManifest.error,
    python_core_bootstrap: pythonCoreBootstrap,
    core_python_dependencies: corePythonDependencies,
    missing_core_dependencies: corePythonDependencies.missing,
    checks,
    missing,
    policy,
  }

  if (setupComplete && !fs.existsSync(PATHS.setupCompleteFile)) {
    try { writeSetupComplete(report) } catch {}
  }

  return report
}

// ── Native module compatibility check + auto-rebuild ──────────────────
// The backend runs under Electron's Node (modules version differs from system
// Node). Native addons compiled for system Node crash with ERR_DLOPEN_FAILED.
// We detect this on startup and rebuild if needed.

function getElectronModulesVersion() {
  // process.versions.modules is the ABI version of the CURRENT runtime —
  // Electron's embedded Node when we're inside main.js.
  return Number(process.versions.modules)
}

function nativeModuleNeedsRebuild(modulePath) {
  try {
    // Quick load attempt — if it throws ERR_DLOPEN_FAILED, it needs a rebuild.
    require(modulePath)
    return false
  } catch (e) {
    return e.code === 'ERR_DLOPEN_FAILED' || /NODE_MODULE_VERSION/.test(e.message)
  }
}

function rebuildNativeModules(repoDir) {
  const { spawnSync } = require('child_process')
  const backendDir = path.join(repoDir, 'backend')
  const electronVersion = process.versions.electron || '27.3.11'

  // Use electron-rebuild if available in the launcher's own node_modules
  const rebuildBin = path.join(repoDir, 'launcher', 'node_modules', '.bin', 'electron-rebuild')
  if (!fs.existsSync(rebuildBin)) {
    // Fallback: try npx electron-rebuild from the backend dir
    const result = spawnSync('npx', [
      'electron-rebuild',
      '--version', electronVersion,
      '--module-dir', backendDir,
      '--which-module', 'better-sqlite3',
    ], { cwd: backendDir, encoding: 'utf8', stdio: 'pipe', timeout: 120000 })
    return { ok: result.status === 0, stdout: result.stdout, stderr: result.stderr }
  }
  const result = spawnSync(rebuildBin, [
    '--version', electronVersion,
    '--module-dir', backendDir,
    '--which-module', 'better-sqlite3',
  ], { cwd: backendDir, encoding: 'utf8', stdio: 'pipe', timeout: 120000 })
  return { ok: result.status === 0, stdout: result.stdout, stderr: result.stderr }
}

function checkAndFixNativeModules(repoDir) {
  const sqliteBin = path.join(repoDir, 'backend', 'node_modules', 'better-sqlite3', 'build', 'Release', 'better_sqlite3.node')
  if (!fs.existsSync(sqliteBin)) return { ok: true, reason: 'better-sqlite3 not installed' }
  if (!nativeModuleNeedsRebuild(sqliteBin)) return { ok: true, reason: 'already compatible' }
  const rebuild = rebuildNativeModules(repoDir)
  if (rebuild.ok) return { ok: true, rebuilt: true, reason: 'rebuilt for Electron node' }
  return { ok: false, rebuilt: false, reason: `rebuild failed: ${(rebuild.stderr || '').slice(-500)}` }
}

module.exports = { checkFirstBoot, resolvePython, resolveBundledPython, writeSetupComplete, checkAndFixNativeModules }
