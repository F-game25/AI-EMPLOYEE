const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('ai', {
  startSystem: () => ipcRenderer.invoke('start-system'),
  stopSystem: () => ipcRenderer.invoke('stop-system'),
  checkStatus: () => ipcRenderer.invoke('check-status'),
  getVersion: () => ipcRenderer.invoke('get-version'),
  checkUpdates: () => ipcRenderer.invoke('check-updates'),
  checkDependencies: () => ipcRenderer.invoke('check-dependencies'),
  runDependencyInstall: (type) => ipcRenderer.invoke('run-dependency-install', type),
  markSetupComplete: () => ipcRenderer.invoke('mark-setup-complete'),
  openInterface: () => ipcRenderer.invoke('open-interface'),
  onStartLog: (callback) => ipcRenderer.on('start-log', (event, line) => callback(line)),
  onStartReady: (callback) => ipcRenderer.on('start-ready', callback),
  onStartError: (callback) => ipcRenderer.on('start-error', (event, msg) => callback(msg)),
  onSetupLog: (callback) => ipcRenderer.on('setup-log', (event, line) => callback(line)),
})
