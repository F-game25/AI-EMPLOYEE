// Preload self-trace. Sandboxed preloads cannot use `require('fs')`, so we
// log via `console.error` instead — the main process's
// `webContents.on('console-message')` handler mirrors it into launcher.log.
// Two messages: one before contextBridge fires, one after. If only the
// "starting" line shows up in launcher.log, contextBridge.exposeInMainWorld
// threw and `window.ai` won't exist in the renderer.
console.error('[PRELOAD-TRACE] preload starting (pid=' + process.pid + ', url=' + (typeof location !== 'undefined' ? location.href : 'n/a') + ')')

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('ai', {
  // ── Lifecycle ─────────────────────────────────────────────────────
  startSystem: () => ipcRenderer.invoke('start-system'),
  stopSystem: () => ipcRenderer.invoke('stop-system'),
  cancelStart: () => ipcRenderer.invoke('cancel-start'),
  restartSystem: () => ipcRenderer.invoke('restart-system'),
  restartVerbose: () => ipcRenderer.invoke('restart-verbose'),
  checkStatus: () => ipcRenderer.invoke('check-status'),
  openInterface: () => ipcRenderer.invoke('open-interface'),
  retryOpenInterface: () => ipcRenderer.invoke('retry-open-interface'),
  returnToLauncher: () => ipcRenderer.invoke('return-to-launcher'),

  // ── Status / diagnostics ──────────────────────────────────────────
  getLaunchStatus: () => ipcRenderer.invoke('get-launch-status'),
  getDiagnostics: () => ipcRenderer.invoke('get-diagnostics'),
  getPolicy: () => ipcRenderer.invoke('get-policy'),
  getPhases: () => ipcRenderer.invoke('get-phases'),
  openLogsFolder: () => ipcRenderer.invoke('open-logs-folder'),
  copyDiagnostics: () => ipcRenderer.invoke('copy-diagnostics'),
  exportDiagnostics: () => ipcRenderer.invoke('export-diagnostics'),

  // ── Versioning & deps ─────────────────────────────────────────────
  getVersion: () => ipcRenderer.invoke('get-version'),
  checkUpdates: () => ipcRenderer.invoke('check-updates'),
  applyUpdate: () => ipcRenderer.invoke('apply-update'),
  checkDependencies: () => ipcRenderer.invoke('check-dependencies'),
  runDependencyInstall: (type) => ipcRenderer.invoke('run-dependency-install', type),
  markSetupComplete: () => ipcRenderer.invoke('mark-setup-complete'),

  // ── Frontend → main signals (called by the React app at 127.0.0.1:8787) ─
  notifyUiBootPhase: (phase) => ipcRenderer.send('ui-boot-phase', phase),
  notifyUiMounted:   (payload) => ipcRenderer.send('ui-mounted', payload),
  notifyUiFailed:    (payload) => ipcRenderer.send('ui-failed', payload),

  // ── Launcher renderer → main signals ──────────────────────────────
  windowMinimize: () => ipcRenderer.send('window-minimize'),
  windowClose:    () => ipcRenderer.send('window-close'),
  windowToggleFullscreen: () => ipcRenderer.send('window-toggle-fullscreen'),

  // ── v5: Rebuild + backend state ───────────────────────────────────
  rebuildFrontend: () => ipcRenderer.invoke('rebuild-frontend'),
  onRebuildLog:      (cb) => { ipcRenderer.removeAllListeners('rebuild-log');     ipcRenderer.on('rebuild-log',     (_e, data) => cb(data)) },
  onRebuildComplete: (cb) => { ipcRenderer.removeAllListeners('rebuild-complete');ipcRenderer.on('rebuild-complete',(_e, data) => cb(data)) },
  onBackendState:    (cb) => { ipcRenderer.removeAllListeners('backend-state');   ipcRenderer.on('backend-state',   (_e, data) => cb(data)) },
  onBeforeFullscreenToggle: (cb) => { ipcRenderer.removeAllListeners('before-fullscreen-toggle'); ipcRenderer.on('before-fullscreen-toggle', () => cb()) },

  // ── Health probe ──────────────────────────────────────────────────
  // Renderers can read this to confirm window.ai is actually bridged.
  _bridgeVersion: 'v4',

  // ── Subscriptions (launcher renderer) ─────────────────────────────
  // Each subscription replaces any prior listener to prevent accumulation
  // across multiple start/stop cycles in a single session.
  onStartLog:        (cb) => { ipcRenderer.removeAllListeners('start-log');        ipcRenderer.on('start-log',        (_e, line)  => cb(line)) },
  onStartReady:      (cb) => { ipcRenderer.removeAllListeners('start-ready');      ipcRenderer.on('start-ready',      (_e, data)  => cb(data)) },
  onStartError:      (cb) => { ipcRenderer.removeAllListeners('start-error');      ipcRenderer.on('start-error',      (_e, msg)   => cb(msg)) },
  onSetupLog:        (cb) => { ipcRenderer.removeAllListeners('setup-log');        ipcRenderer.on('setup-log',        (_e, line)  => cb(line)) },
  onPhase:           (cb) => { ipcRenderer.removeAllListeners('phase');            ipcRenderer.on('phase',            (_e, entry) => cb(entry)) },
  onPhaseFail:       (cb) => { ipcRenderer.removeAllListeners('phase:fail');       ipcRenderer.on('phase:fail',       (_e, entry) => cb(entry)) },
  onPythonSubsystems:(cb) => { ipcRenderer.removeAllListeners('python-subsystems');ipcRenderer.on('python-subsystems',(_e, data)  => cb(data)) },
  onUiLoadStatus:    (cb) => { ipcRenderer.removeAllListeners('ui-load-status');   ipcRenderer.on('ui-load-status',   (_e, data)  => cb(data)) },
  onUiLoadFailed:    (cb) => { ipcRenderer.removeAllListeners('ui-load-failed');   ipcRenderer.on('ui-load-failed',   (_e, data)  => cb(data)) },
  onUpdaterEvent:    (cb) => {
    const ch = ['updater:checking', 'updater:available', 'updater:not-available', 'updater:progress', 'updater:downloaded', 'updater:error']
    ch.forEach(name => ipcRenderer.on(name, (_e, data) => cb(name, data)))
  },
})

console.error('[PRELOAD-TRACE] contextBridge.exposeInMainWorld(ai) done — window.ai is now available')
