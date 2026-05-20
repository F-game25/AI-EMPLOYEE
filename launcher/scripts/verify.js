#!/usr/bin/env node
/**
 * Launcher preflight verify — catches regressions before `npm start`.
 *
 *   $ npm run verify
 *
 * Checks:
 *   1. All required files exist
 *   2. Every JS file parses (node --check)
 *   3. preload .invoke(X) channels each have a matching ipcMain.handle(X)
 *   4. require('./src/update.js') in plain Node does NOT throw
 *      (proves the defensive electron-updater wrapper works)
 *   5. assets/icon.{png,ico,icns} all present and non-empty
 *
 * Exits 0 on success, 1 on any failure.
 */
const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')

const ROOT = path.resolve(__dirname, '..')
const cd = (p) => path.join(ROOT, p)

let failures = 0
const PASS = '\x1b[32m✓\x1b[0m'
const FAIL = '\x1b[31m✗\x1b[0m'
const DIM  = '\x1b[2m'
const END  = '\x1b[0m'

function check(label, fn) {
  try {
    const result = fn()
    if (result === false) throw new Error('check returned false')
    const detail = typeof result === 'string' ? `  ${DIM}${result}${END}` : ''
    console.log(`  ${PASS} ${label}${detail}`)
  } catch (err) {
    console.log(`  ${FAIL} ${label}\n    ${err.message}`)
    failures++
  }
}

function section(title) {
  console.log(`\n${DIM}═══${END} ${title}`)
}

// ── 1. Required files exist ─────────────────────────────────────────────
section('FILE INVENTORY')
const required = [
  'main.js', 'preload.js', 'package.json',
  'src/log.js', 'src/paths.js', 'src/backend.js',
  'src/health.js', 'src/phases.js', 'src/update.js',
  'renderer/index.html', 'renderer/styles.css', 'renderer/tokens.css', 'renderer/app.js',
  'scripts/after-pack.js', 'scripts/generate-icons.py',
  'assets/icon.svg', 'assets/icon.png', 'assets/icon.ico', 'assets/icon.icns',
]
required.forEach(rel => {
  check(rel, () => {
    const stat = fs.statSync(cd(rel))
    if (stat.size === 0) throw new Error('empty file')
    return `${stat.size} bytes`
  })
})

// ── 2. JS syntax check ────────────────────────────────────────────────────
section('SYNTAX (node --check)')
const jsFiles = [
  'main.js', 'preload.js',
  'src/log.js', 'src/paths.js', 'src/backend.js',
  'src/health.js', 'src/first_boot.js', 'src/phases.js', 'src/update.js',
  'renderer/app.js',
  'scripts/after-pack.js', 'scripts/verify.js',
]
jsFiles.forEach(rel => {
  check(rel, () => { execFileSync(process.execPath, ['-c', cd(rel)], { stdio: 'pipe' }); return 'parses' })
})

// ── 3. IPC contract: every preload .invoke has a main .handle ────────────
section('IPC CONTRACT (preload ↔ main)')
const preload = fs.readFileSync(cd('preload.js'), 'utf8')
const main    = fs.readFileSync(cd('main.js'),    'utf8')

const invokes = [...preload.matchAll(/invoke\('([^']+)'/g)].map(m => m[1])
const sends   = [...preload.matchAll(/send\('([^']+)'/g)].map(m => m[1])
const handles = new Set([...main.matchAll(/ipcMain\.handle\('([^']+)'/g)].map(m => m[1]))
const listens = new Set([...main.matchAll(/ipcMain\.on\('([^']+)'/g)].map(m => m[1]))

invokes.forEach(ch => {
  check(`.invoke('${ch}')`, () => {
    if (!handles.has(ch)) throw new Error(`no ipcMain.handle('${ch}') in main.js`)
    return 'handled'
  })
})
sends.forEach(ch => {
  check(`.send('${ch}')`, () => {
    if (!listens.has(ch)) throw new Error(`no ipcMain.on('${ch}') in main.js`)
    return 'listened'
  })
})

// ── 4. Defensive update.js — must not throw in plain Node ───────────────
section('UPDATE WRAPPER (defensive)')
check('require(./src/update) without electron', () => {
  // Spawn a child so we don't pollute this process
  execFileSync(process.execPath, ['-e', `require(${JSON.stringify(cd('src/update.js'))})`], { stdio: 'pipe' })
  return 'no throw at require time'
})

// ── 5. Tokens file mirrors design system ────────────────────────────────
section('DESIGN TOKENS')
check('tokens.css defines --nx-gold + --nx-cyan + --nx-danger', () => {
  const css = fs.readFileSync(cd('renderer/tokens.css'), 'utf8')
  for (const tok of ['--nx-gold', '--nx-cyan', '--nx-danger', '--nx-font-mono']) {
    if (!css.includes(tok)) throw new Error(`missing token: ${tok}`)
  }
  return '4 critical tokens present'
})

// ── Summary ─────────────────────────────────────────────────────────────
console.log('')
if (failures === 0) {
  console.log(`${PASS} all checks passed — launcher is ready to run`)
  process.exit(0)
} else {
  console.log(`${FAIL} ${failures} failure(s) — fix before launching`)
  process.exit(1)
}
