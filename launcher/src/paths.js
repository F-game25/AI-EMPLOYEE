const path = require('path')
const fs = require('fs')
const os = require('os')
const { app } = require('electron')

let _resolvedRepoDir = null
let _resolvedAppHome = null

/**
 * Returns the absolute path to the repo root in both dev and packaged modes.
 *
 *   Dev:      <repo>/launcher/...                -> <repo>
 *   Packaged: <appResources>/repo/...            -> <appResources>/repo
 *
 * We detect packaged mode by the presence of `process.resourcesPath` and
 * an `extraResources` directory named `repo` next to it.
 */
function resolveRepoDir() {
  if (_resolvedRepoDir) return _resolvedRepoDir
  const packagedRepo = process.resourcesPath
    ? path.join(process.resourcesPath, 'repo')
    : null
  const packagedMarkers = packagedRepo ? [
    path.join(packagedRepo, 'backend', 'server.js'),
    path.join(packagedRepo, 'frontend', 'dist', 'index.html'),
    path.join(packagedRepo, 'runtime'),
    path.join(packagedRepo, 'start.sh'),
  ] : []
  if (packagedRepo && packagedMarkers.some(marker => fs.existsSync(marker))) {
    _resolvedRepoDir = packagedRepo
  } else {
    // Dev mode — __dirname is <repo>/launcher/src
    _resolvedRepoDir = path.resolve(__dirname, '..', '..')
  }
  return _resolvedRepoDir
}

function resolveAppHome() {
  if (_resolvedAppHome) return _resolvedAppHome
  if (process.env.AI_EMPLOYEE_HOME) {
    _resolvedAppHome = path.resolve(process.env.AI_EMPLOYEE_HOME)
  } else if (process.env.AI_HOME) {
    _resolvedAppHome = path.resolve(process.env.AI_HOME)
  } else if (app?.isPackaged) {
    _resolvedAppHome = app.getPath('userData')
  } else {
    _resolvedAppHome = path.join(os.homedir(), '.ai-employee')
  }
  for (const dir of ['state', 'logs', 'run', 'config', 'cache']) {
    try { fs.mkdirSync(path.join(_resolvedAppHome, dir), { recursive: true }) } catch {}
  }
  return _resolvedAppHome
}

const HOME = os.homedir()

const PATHS = {
  get repoDir() { return resolveRepoDir() },
  get appHome() { return resolveAppHome() },
  get stateDir() { return path.join(resolveAppHome(), 'state') },
  get logDir() { return path.join(resolveAppHome(), 'logs') },
  get runDir() { return path.join(resolveAppHome(), 'run') },
  get configDir() { return path.join(resolveAppHome(), 'config') },
  home: HOME,
  get versionFile() { return path.join(resolveAppHome(), 'state', 'version.json') },
  get updaterFile() { return path.join(resolveAppHome(), 'state', 'updater.json') },
  get setupCompleteFile() { return path.join(resolveAppHome(), 'state', 'setup_complete') },
  startScript() { return path.join(resolveRepoDir(), 'start.sh') },
  stopScript() { return path.join(resolveRepoDir(), 'stop.sh') },
}

module.exports = { resolveRepoDir, resolveAppHome, PATHS }
