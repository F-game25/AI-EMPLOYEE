/**
 * Tests for TQ-3: scoped file read/grep/glob tools for forge agents
 * Verifies path traversal protection and basic functionality
 */
'use strict'

const assert = require('assert')
const path = require('path')
const fs = require('fs')
const os = require('os')
const forgeFileTools = require('../backend/forge/forge_file_tools')

let testsPassed = 0
let testsFailed = 0

function test(name, fn) {
  try {
    fn()
    testsPassed++
    console.log(`  ✓ ${name}`)
  } catch (err) {
    testsFailed++
    console.log(`  ✗ ${name}`)
    console.error(`    ${err.message}`)
  }
}

console.log('\nForge File Tools (TQ-3) Tests\n')

// ─────────────────────────────────────────────────────────────
// readFile tests
// ─────────────────────────────────────────────────────────────
console.log('readFile:')
{
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-file-tools-'))
  fs.mkdirSync(path.join(tempDir, 'src'), { recursive: true })
  fs.writeFileSync(path.join(tempDir, 'src', 'main.js'), 'console.log("hello");\n')
  fs.writeFileSync(path.join(tempDir, 'src', 'config.json'), '{"name": "test"}')
  fs.writeFileSync(path.join(tempDir, 'README.md'), '# Test Project\nThis is a test.\n')

  test('reads a file within the workspace', () => {
    const result = forgeFileTools.readFile(tempDir, 'src/main.js')
    assert.strictEqual(result.ok, true)
    assert(result.content.includes('console.log'))
    assert.strictEqual(result.path, 'src/main.js')
    assert(result.lines > 0)
  })

  test('returns error for non-existent file', () => {
    const result = forgeFileTools.readFile(tempDir, 'nonexistent.js')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
    assert(result.error.includes('not found'))
  })

  test('blocks path traversal via ../', () => {
    const result = forgeFileTools.readFile(tempDir, '../etc/passwd')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
    // normalizeRelPath converts .. to ., so '../etc/passwd' becomes '.etc.passwd'
    // which is then safely not found
    assert(result.error.includes('not found') || result.error.includes('denied') || result.error.includes('escape'))
  })

  test('blocks absolute path attempts', () => {
    const result = forgeFileTools.readFile(tempDir, '/etc/passwd')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
  })

  test('returns error for oversized files', () => {
    const largeFile = path.join(tempDir, 'large.txt')
    fs.writeFileSync(largeFile, 'x'.repeat(101 * 1024))
    const result = forgeFileTools.readFile(tempDir, 'large.txt')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
    assert(result.error.includes('too large'))
  })

  test('handles JSON files', () => {
    const result = forgeFileTools.readFile(tempDir, 'src/config.json')
    assert.strictEqual(result.ok, true)
    assert(result.content.includes('"name"'))
  })

  test('blocks ../ at the end', () => {
    const result = forgeFileTools.readFile(tempDir, 'src/../../etc/passwd')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
  })

  test('blocks multiple leading ..', () => {
    const result = forgeFileTools.readFile(tempDir, '../../etc/passwd')
    assert.strictEqual(result.ok, undefined)
    assert(result.error)
  })

  fs.rmSync(tempDir, { recursive: true })
}

// ─────────────────────────────────────────────────────────────
// grepProject tests
// ─────────────────────────────────────────────────────────────
console.log('\ngrepProject:')
{
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-grep-'))
  fs.mkdirSync(path.join(tempDir, 'src'), { recursive: true })
  fs.writeFileSync(path.join(tempDir, 'src', 'main.js'), 'console.log("hello");\n')
  fs.writeFileSync(path.join(tempDir, 'README.md'), '# Test\nConsole usage\n')

  test('finds matches in files', () => {
    const result = forgeFileTools.grepProject(tempDir, 'console')
    assert.strictEqual(result.ok, true)
    assert(result.matches > 0)
    assert(result.results.length > 0)
  })

  test('respects case-insensitive search', () => {
    const result = forgeFileTools.grepProject(tempDir, 'CONSOLE', { flags: 'i' })
    assert(result.matches > 0)
  })

  test('returns empty results for no matches', () => {
    const result = forgeFileTools.grepProject(tempDir, 'xyzabc123')
    assert.strictEqual(result.ok, true)
    assert.strictEqual(result.matches, 0)
    assert.strictEqual(result.results.length, 0)
  })

  test('respects ignore patterns', () => {
    fs.mkdirSync(path.join(tempDir, 'node_modules'), { recursive: true })
    fs.writeFileSync(path.join(tempDir, 'node_modules', 'pkg.js'), 'console.log("ignored")')
    const result = forgeFileTools.grepProject(tempDir, 'ignored')
    assert.strictEqual(result.matches, 0)
  })

  fs.rmSync(tempDir, { recursive: true })
}

// ─────────────────────────────────────────────────────────────
// globProject tests
// ─────────────────────────────────────────────────────────────
console.log('\nglobProject:')
{
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-glob-'))
  fs.mkdirSync(path.join(tempDir, 'src'), { recursive: true })
  fs.writeFileSync(path.join(tempDir, 'src', 'main.js'), 'x')
  fs.writeFileSync(path.join(tempDir, 'README.md'), 'x')

  test('finds matching files', () => {
    const result = forgeFileTools.globProject(tempDir, '**/*.js')
    assert.strictEqual(result.ok, true)
    assert(result.count > 0)
  })

  test('finds markdown files', () => {
    const result = forgeFileTools.globProject(tempDir, '**/*.md')
    assert.strictEqual(result.ok, true)
    assert(result.files.includes('README.md'))
  })

  test('respects ignore patterns', () => {
    fs.mkdirSync(path.join(tempDir, '.git'), { recursive: true })
    fs.writeFileSync(path.join(tempDir, '.git', 'config'), 'x')
    const result = forgeFileTools.globProject(tempDir, '**/*')
    assert(!result.files.some(f => f.startsWith('.git')))
  })

  test('returns empty for no matches', () => {
    const result = forgeFileTools.globProject(tempDir, '*.nonexistent')
    assert.strictEqual(result.ok, true)
    assert.strictEqual(result.count, 0)
  })

  fs.rmSync(tempDir, { recursive: true })
}

// ─────────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────────
console.log(`\n${testsPassed + testsFailed} tests: ${testsPassed} passed, ${testsFailed} failed\n`)

if (testsFailed > 0) {
  process.exit(1)
}
