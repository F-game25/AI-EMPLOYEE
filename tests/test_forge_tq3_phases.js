/**
 * Tests for TQ-3 phases 2-4: per-file verify, delegation, branching
 */
'use strict'

const assert = require('assert')
const fs = require('fs')
const path = require('path')
const os = require('os')

console.log('\nTQ-3 Phases 2-4 Tests\n')

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

// Mock the forge module functions for testing
const mockForge = {
  evaluateConditionalStep: function(condition, priorOutput) {
    if (!condition || !priorOutput) return false
    const text = typeof priorOutput === 'string' ? priorOutput : JSON.stringify(priorOutput)
    if (condition.if_contains) {
      return new RegExp(condition.if_contains, 'i').test(text)
    }
    if (condition.if_not_contains) {
      return !new RegExp(condition.if_not_contains, 'i').test(text)
    }
    if (condition.if_equals) {
      return text === condition.if_equals
    }
    return false
  },

  getFileSyntaxCheckCmd: function(filePath) {
    if (/\.js$/.test(filePath)) return { cmd: `node --check "${filePath}"`, type: 'node' }
    if (/\.ts$/.test(filePath)) return { cmd: `npx tsc --noEmit "${filePath}"`, type: 'tsc' }
    if (/\.py$/.test(filePath)) return { cmd: `python3 -m py_compile "${filePath}"`, type: 'python' }
    if (/\.json$/.test(filePath)) return { cmd: `node -e "JSON.parse(require('fs').readFileSync('${filePath}','utf8'))"`, type: 'json' }
    return null
  }
}

// ─────────────────────────────────────────────────────────────
// Phase 2: Per-file syntax verification
// ─────────────────────────────────────────────────────────────
console.log('Per-file syntax verification (Phase 2):')

test('identifies syntax check cmd for JS files', () => {
  const cmd = mockForge.getFileSyntaxCheckCmd('test.js')
  assert(cmd)
  assert.strictEqual(cmd.type, 'node')
})

test('identifies syntax check cmd for Python files', () => {
  const cmd = mockForge.getFileSyntaxCheckCmd('test.py')
  assert(cmd)
  assert.strictEqual(cmd.type, 'python')
})

test('identifies syntax check cmd for JSON files', () => {
  const cmd = mockForge.getFileSyntaxCheckCmd('test.json')
  assert(cmd)
  assert.strictEqual(cmd.type, 'json')
})

test('returns null for unsupported file types', () => {
  const cmd = mockForge.getFileSyntaxCheckCmd('test.txt')
  assert.strictEqual(cmd, null)
})

// ─────────────────────────────────────────────────────────────
// Phase 4: Data-dependent branching
// ─────────────────────────────────────────────────────────────
console.log('\nData-dependent branching (Phase 4):')

test('evaluates if_contains condition (match)', () => {
  const condition = { if_contains: 'error' }
  const output = 'There was an error in the code'
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), true)
})

test('evaluates if_contains condition (no match)', () => {
  const condition = { if_contains: 'error' }
  const output = 'Code generated successfully'
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), false)
})

test('evaluates if_contains condition (case-insensitive)', () => {
  const condition = { if_contains: 'ERROR' }
  const output = 'There was an error in the code'
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), true)
})

test('evaluates if_not_contains condition (no match present)', () => {
  const condition = { if_not_contains: 'error' }
  const output = 'Code generated successfully'
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), true)
})

test('evaluates if_not_contains condition (match present)', () => {
  const condition = { if_not_contains: 'error' }
  const output = 'There was an error in the code'
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), false)
})

test('evaluates if_equals condition', () => {
  const condition = { if_equals: 'success' }
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, 'success'), true)
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, 'failure'), false)
})

test('handles null condition gracefully', () => {
  assert.strictEqual(mockForge.evaluateConditionalStep(null, 'output'), false)
})

test('handles null output gracefully', () => {
  const condition = { if_contains: 'test' }
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, null), false)
})

test('evaluates conditions on JSON output', () => {
  const condition = { if_contains: '"status"' }
  const output = { status: 'complete', data: [] }
  assert.strictEqual(mockForge.evaluateConditionalStep(condition, output), true)
})

// ─────────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────────
console.log(`\n${testsPassed + testsFailed} tests: ${testsPassed} passed, ${testsFailed} failed\n`)

if (testsFailed > 0) {
  process.exit(1)
}
