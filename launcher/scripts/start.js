#!/usr/bin/env node
const path = require('path')
const { spawn } = require('child_process')

const electron = require('electron')
const electronBin = typeof electron === 'string' ? electron : electron?.toString?.()

if (!electronBin) {
  console.error('[launcher] Electron binary could not be resolved')
  process.exit(1)
}

const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE
delete env.AI_EMPLOYEE_NODE_RUN_AS_NODE

const child = spawn(electronBin, ['.'], {
  cwd: path.resolve(__dirname, '..'),
  stdio: 'inherit',
  env,
  windowsHide: false,
})

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`[launcher] Electron exited from signal ${signal}`)
    process.exit(1)
  }
  process.exit(code ?? 0)
})

child.on('error', (error) => {
  console.error(`[launcher] Failed to start Electron: ${error.message}`)
  process.exit(1)
})
