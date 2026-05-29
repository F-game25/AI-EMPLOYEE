/**
 * electron-updater wrapper — fully defensive.
 *
 * IMPORTANT: do NOT require('electron-updater') at module load time.
 * It eagerly instantiates `new AppUpdater()` which calls `app.getVersion()`
 * during construction. If `app` is undefined (e.g. in plain Node or in
 * Electron before app.ready), it throws "Cannot read properties of
 * undefined (reading 'getVersion')". Defer require until `wire()` is
 * called from `app.on('ready')`.
 */

const { log } = require('./log')

let autoUpdater = null
let wiredOnce = false

/**
 * Lazy-load and wire the auto-updater after `app.ready`. Returns
 * `{ available, reason?, checkForUpdates?, quitAndInstall? }`.
 * Never throws — failure becomes `{ available: false, reason }`.
 */
function wire(mainWindow, { onPhase = () => {} } = {}) {
  if (wiredOnce) return autoUpdater ? buildApi(mainWindow, onPhase) : { available: false, reason: 'already-wired-without-updater' }
  wiredOnce = true

  try {
    autoUpdater = require('electron-updater').autoUpdater
  } catch (err) {
    log.warn('[updater] electron-updater not available:', err.message)
    return { available: false, reason: err.message }
  }

  if (!autoUpdater) {
    log.warn('[updater] electron-updater module loaded but autoUpdater is null')
    return { available: false, reason: 'no autoUpdater singleton' }
  }

  return buildApi(mainWindow, onPhase)
}

function buildApi(mainWindow, onPhase) {
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  const send = (channel, payload) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      try { mainWindow.webContents.send(channel, payload) } catch { /* window gone */ }
    }
    try { onPhase(channel, payload) } catch { /* user callback */ }
  }

  // Wire events
  autoUpdater.on('checking-for-update',    ()    => { log.info('[updater] checking');         send('updater:checking', {}) })
  autoUpdater.on('update-available',       info  => { log.info('[updater] available', info?.version); send('updater:available', info) })
  autoUpdater.on('update-not-available',   info  => { log.info('[updater] not available');    send('updater:not-available', info) })
  autoUpdater.on('download-progress',      p     => { send('updater:progress', p) })
  autoUpdater.on('update-downloaded',      info  => { log.info('[updater] downloaded');       send('updater:downloaded', info) })
  autoUpdater.on('error',                  err   => { log.warn('[updater] error', err?.message); send('updater:error', { message: err?.message || String(err) }) })

  return {
    available: true,
    checkForUpdates: () => {
      try {
        return autoUpdater.checkForUpdates().catch(err => {
          log.warn('[updater] checkForUpdates rejected:', err.message)
          return null
        })
      } catch (err) {
        log.warn('[updater] checkForUpdates threw:', err.message)
        return Promise.resolve(null)
      }
    },
    quitAndInstall: () => {
      try { autoUpdater.quitAndInstall() }
      catch (err) { log.warn('[updater] quitAndInstall failed:', err.message) }
    },
  }
}

module.exports = { wire }
