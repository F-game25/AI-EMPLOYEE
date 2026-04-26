const { app, BrowserWindow, ipcMain, screen } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')
const http = require('http')
const { execSync } = require('child_process')

console.log('Modules loaded. app type:', typeof app)

const REPO_DIR = path.dirname(path.dirname(__dirname))
const HOME = require('os').homedir()
const VERSION_PATH = path.join(HOME, '.ai-employee', 'state', 'version.json')
const UPDATER_PATH = path.join(HOME, '.ai-employee', 'state', 'updater.json')
const SETUP_COMPLETE_PATH = path.join(HOME, '.ai-employee', 'state', 'setup_complete')

let mainWindow = null

function createWindow() {
  console.log('Creating window')
  mainWindow = new BrowserWindow({
    width: 600,
    height: 440,
    frame: false,
    transparent: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    }
  })
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
  mainWindow.on('closed', () => { mainWindow = null })
  console.log('Window created')
}

function cleanLogLine(line) {
  if (/^(npm warn|npm notice|added \d+|audited \d+|found \d+|up to date|\[=+>*\s*\])/.test(line)) return null
  if (/^(Collecting|Downloading|Installing|Building|Successfully installed|Requirement already)/.test(line)) return null
  if (/^(Creating egg|running setup\.py|running build)/.test(line)) return null
  return line
}

function checkServerHealth() {
  return new Promise(resolve => {
    const req = http.get('http://localhost:8787/health', { timeout: 2000 }, res => {
      resolve(res.statusCode === 200)
      req.destroy()
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000)
  })
}

console.log('Defining IPC handlers')

ipcMain.handle('start-system', async event => {
  return new Promise((resolve, reject) => {
    const proc = spawn('bash', ['start.sh'], { cwd: REPO_DIR, stdio: 'pipe' })
    proc.stdout.on('data', data => {
      const lines = data.toString().split('\n').filter(l => l.trim())
      lines.forEach(line => {
        const cleaned = cleanLogLine(line)
        if (cleaned) event.sender.send('start-log', cleaned)
      })
    })
    proc.stderr.on('data', data => {
      const lines = data.toString().split('\n').filter(l => l.trim())
      lines.forEach(line => {
        const cleaned = cleanLogLine(line)
        if (cleaned) event.sender.send('start-log', '[ERROR] ' + cleaned)
      })
    })
    proc.on('exit', code => {
      if (code === 0) {
        let attempts = 0
        const poll = setInterval(async () => {
          attempts++
          const healthy = await checkServerHealth()
          if (healthy) {
            clearInterval(poll)
            event.sender.send('start-ready')
            resolve({ success: true })
          } else if (attempts > 30) {
            clearInterval(poll)
            reject(new Error('Server failed to start'))
          }
        }, 2000)
      } else {
        reject(new Error(`start.sh exited with code ${code}`))
      }
    })
  })
})

ipcMain.handle('stop-system', async () => {
  return new Promise((resolve, reject) => {
    const proc = spawn('bash', ['stop.sh'], { cwd: REPO_DIR })
    proc.on('exit', code => resolve({ success: code === 0 }))
    proc.on('error', err => reject(err))
  })
})

ipcMain.handle('check-status', async () => {
  const running = await checkServerHealth()
  return { running }
})

ipcMain.handle('get-version', async () => {
  try {
    if (fs.existsSync(VERSION_PATH)) {
      return JSON.parse(fs.readFileSync(VERSION_PATH, 'utf8'))
    }
  } catch {}
  return { last_commit: 'unknown', last_updated_at: null }
})

ipcMain.handle('check-updates', async () => {
  try {
    if (fs.existsSync(UPDATER_PATH)) {
      return JSON.parse(fs.readFileSync(UPDATER_PATH, 'utf8'))
    }
  } catch {}
  return { update_available: false }
})

ipcMain.handle('check-dependencies', async () => {
  const result = {
    setup_complete: fs.existsSync(SETUP_COMPLETE_PATH),
    node: false,
    node_version: null,
    python: false,
    python_version: null,
    npm_packages: fs.existsSync(path.join(REPO_DIR, 'node_modules')),
    pip_packages: false,
    platform: process.platform,
  }
  try {
    result.node_version = execSync('node --version').toString().trim()
    result.node = true
  } catch {}
  try {
    result.python_version = execSync('python3 --version').toString().trim()
    result.python = true
  } catch {}
  try {
    execSync('python3 -c "import fastapi"', { stdio: 'ignore' })
    result.pip_packages = true
  } catch {}
  return result
})

ipcMain.handle('run-dependency-install', async (event, type) => {
  return new Promise(resolve => {
    const cmd = type === 'npm'
      ? { cmd: 'npm', args: ['install'], cwd: REPO_DIR }
      : { cmd: 'bash', args: ['install.sh', '--deps-only'], cwd: REPO_DIR }
    const proc = spawn(cmd.cmd, cmd.args, { cwd: cmd.cwd, stdio: 'pipe' })
    proc.stdout.on('data', d => {
      d.toString().split('\n').filter(l => l.trim()).forEach(l => {
        const cleaned = cleanLogLine(l)
        if (cleaned) event.sender.send('setup-log', cleaned)
      })
    })
    proc.on('exit', code => resolve({ success: code === 0 }))
  })
})

ipcMain.handle('mark-setup-complete', async () => {
  try {
    fs.mkdirSync(path.dirname(SETUP_COMPLETE_PATH), { recursive: true })
    fs.writeFileSync(SETUP_COMPLETE_PATH, new Date().toISOString())
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
})

ipcMain.handle('open-interface', async () => {
  const primary = screen.getPrimaryDisplay()
  const { width, height } = primary.workAreaSize
  mainWindow.setSize(width, height, true)
  mainWindow.center()
  await new Promise(r => setTimeout(r, 400))
  mainWindow.loadURL('http://localhost:8787')
  return { success: true }
})

console.log('Setting up app lifecycle')

app.on('ready', () => {
  console.log('App ready event fired')
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})

console.log('Main process setup complete')
