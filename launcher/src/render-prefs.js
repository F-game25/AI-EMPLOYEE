// Persisted rendering preference so the WebGL mode is controllable from INSIDE the
// app (Settings) instead of a terminal env var. Read at startup BEFORE app.ready
// (GPU switches must be set that early), so this uses a plain home-based path and
// does not depend on Electron's `app` being ready.
const fs = require('fs')
const path = require('path')
const os = require('os')

const VALID = ['auto', 'hardware', 'software']

function configDir() {
  const home = process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
  return path.join(home, 'config')
}
function prefsFile() { return path.join(configDir(), 'render-prefs.json') }

function getRenderMode() {
  // Env var always wins (escape hatch).
  if (process.env.AI_EMPLOYEE_FORCE_SOFTGL === '1') return 'software'
  try {
    const m = JSON.parse(fs.readFileSync(prefsFile(), 'utf8')).mode
    return VALID.includes(m) ? m : 'auto'
  } catch { return 'auto' }
}

function setRenderMode(mode) {
  if (!VALID.includes(mode)) return { ok: false, error: `invalid mode (use ${VALID.join('/')})` }
  try {
    fs.mkdirSync(configDir(), { recursive: true })
    fs.writeFileSync(prefsFile(), JSON.stringify({ mode, updated_at: new Date().toISOString() }, null, 2))
    return { ok: true, mode }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

module.exports = { getRenderMode, setRenderMode, VALID }
