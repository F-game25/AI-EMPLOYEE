console.log('Loading electron...')
const electron = require('electron')
console.log('electron loaded:', typeof electron)
console.log('electron keys:', Object.keys(electron).slice(0, 10))

const { app, BrowserWindow, ipcMain, screen } = electron

console.log('app:', typeof app)
console.log('BrowserWindow:', typeof BrowserWindow)

if (!app) {
  console.error('FAILED: app not found in electron module')
  process.exit(1)
}

console.log('SUCCESS: all modules loaded')
process.exit(0)
