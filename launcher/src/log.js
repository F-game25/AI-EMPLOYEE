/**
 * Bootstrap logger — writes to state/launcher.log on every event so a failed
 * boot leaves a trail on disk. Uses raw fs.appendFileSync (synchronous,
 * dependency-free) so it works *before* Electron's app is ready and even if
 * the renderer never opens.
 *
 * Rotation: single-file, capped at 1 MB. When the cap is exceeded, the file
 * is truncated to the last ~500 KB so the most-recent run is always intact.
 */
const fs = require('fs')
const path = require('path')
const os = require('os')

// Resolve log path WITHOUT touching paths.js (avoid require-cycle during early boot)
function resolveLogDir() {
  const appHome = process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
  return path.join(appHome, 'logs')
}

const LOG_DIR  = resolveLogDir()
const LOG_FILE = path.join(LOG_DIR, 'launcher.log')
const CAP_BYTES   = 1024 * 1024   // 1 MB rotate trigger
const KEEP_BYTES  =  512 * 1024   // 512 KB retained after rotation

try { fs.mkdirSync(LOG_DIR, { recursive: true }) } catch { /* best-effort */ }

function rotateIfNeeded() {
  try {
    const stat = fs.statSync(LOG_FILE)
    if (stat.size > CAP_BYTES) {
      const buf = fs.readFileSync(LOG_FILE)
      const tail = buf.subarray(buf.length - KEEP_BYTES)
      // Find first newline in tail so we don't start mid-line
      const nl = tail.indexOf(0x0a)
      fs.writeFileSync(LOG_FILE, nl >= 0 ? tail.subarray(nl + 1) : tail)
    }
  } catch { /* file doesn't exist yet — fine */ }
}

function write(level, ...args) {
  rotateIfNeeded()
  const ts = new Date().toISOString()
  const msg = args.map(a => {
    if (a instanceof Error) return `${a.message}\n${a.stack || ''}`
    if (typeof a === 'object') { try { return JSON.stringify(a) } catch { return String(a) } }
    return String(a)
  }).join(' ')
  const line = `[${ts}] [${level}] ${msg}\n`
  try { fs.appendFileSync(LOG_FILE, line) } catch { /* swallow — disk full etc. */ }
  // Mirror to stdout so `electron .` in a terminal still shows progress
  try { process.stdout.write(line) } catch { /* no stdout in packaged GUI mode */ }
}

const log = {
  info:  (...a) => write('INFO',  ...a),
  warn:  (...a) => write('WARN',  ...a),
  error: (...a) => write('ERROR', ...a),
  path:  LOG_FILE,
  dir:   LOG_DIR,
}

// Capture last-resort process errors so they always reach disk
process.on('uncaughtException',  (err) => log.error('uncaughtException',  err))
process.on('unhandledRejection', (err) => log.error('unhandledRejection', err))

log.info(`launcher booting — node=${process.versions.node} platform=${process.platform} cwd=${process.cwd()}`)

module.exports = { log }
