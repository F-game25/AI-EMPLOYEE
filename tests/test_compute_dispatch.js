'use strict'

// D1 — egress guard + live remote dispatch adapter.
// Run: node tests/test_compute_dispatch.js

const assert = require('assert')
const eg = require('../backend/services/egress_guard')
const { dispatchJob } = require('../backend/compute_fabric/remote_dispatch')

let passed = 0
async function test(name, fn) {
  try { await fn(); passed++; console.log(`  ok  ${name}`) }
  catch (e) { console.error(`  FAIL ${name}\n       ${e.stack || e.message}`); process.exitCode = 1 }
}

const SECRET_PAYLOAD = { prompt: 'deploy', env: 'OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123' }
const PII_PAYLOAD = { note: 'contact me at jane.doe@example.com about the run' }
const PUBLIC_PAYLOAD = { prompt: 'summarize the quarterly trend in 3 bullets' }

// ── egress guard ──────────────────────────────────────────────────────────────
;(async () => {
  await test('classify: secret / pii / internal / public', () => {
    eg._resetPolicy()
    assert.strictEqual(eg.classify(SECRET_PAYLOAD), 'secret')
    assert.strictEqual(eg.classify(PII_PAYLOAD), 'pii')
    assert.strictEqual(eg.classify({ path: '/home/lars/.ai-employee/state' }), 'internal')
    assert.strictEqual(eg.classify(PUBLIC_PAYLOAD), 'public')
  })

  await test('guard: secret BLOCKED to every remote tier', () => {
    for (const tier of ['peer_trusted', 'rented_trusted', 'external_api']) {
      const d = eg.guard(SECRET_PAYLOAD, tier)
      assert.strictEqual(d.action, 'block', `${tier} should block secret`)
      assert.strictEqual(d.payload, null)
    }
  })

  await test('guard: pii REDACTED to remote (email actually scrubbed), public ALLOWED', () => {
    const r = eg.guard(PII_PAYLOAD, 'rented_trusted')
    assert.strictEqual(r.action, 'redact')
    assert.ok(!JSON.stringify(r.payload).includes('jane.doe@example.com'), 'email must be gone')
    const a = eg.guard(PUBLIC_PAYLOAD, 'external_api')
    assert.strictEqual(a.action, 'allow')
  })

  await test('containResult: anti-malware — strips prototype pollution + drops functions', () => {
    const hostile = JSON.parse('{"result":"ok","__proto__":{"polluted":true},"constructor":{"x":1}}')
    const contained = eg.containValue(hostile)
    assert.strictEqual(contained.polluted, undefined)
    assert.strictEqual(({}).polluted, undefined, 'global prototype must be clean')
    // live/non-JSON values are dropped, not carried into our process
    const withFn = eg.containValue({ a: 1, run: () => 'evil', nested: { f: function () {} } })
    assert.strictEqual(withFn.run, undefined)
    assert.strictEqual(withFn.nested.f, undefined)
    assert.strictEqual(withFn.a, 1)
  })

  await test('scanResult: contains depth bombs + tags result untrusted', () => {
    let deep = { v: 'x' }
    for (let i = 0; i < 200; i++) deep = { n: deep }
    const s = eg.scanResult(deep)
    assert.ok(s.ok)
    assert.strictEqual(s._untrusted, true)
    assert.ok(JSON.stringify(s.result).includes('TRUNCATED_DEPTH'))
  })

  await test('guard: unknown tier and oversize are BLOCKED (deny-by-default)', () => {
    assert.strictEqual(eg.guard(PUBLIC_PAYLOAD, 'mystery').action, 'block')
    const big = { blob: 'x'.repeat(3 * 1024 * 1024) }
    assert.strictEqual(eg.guard(big, 'external_api').action, 'block')
  })

  await test('guard: local allows everything (no off-box egress)', () => {
    assert.strictEqual(eg.guard(SECRET_PAYLOAD, 'local').action, 'allow')
  })

  await test('isEndpointAllowed: LAN + https ok; public http rejected', () => {
    assert.ok(eg.isEndpointAllowed('https://gpu.runpod.io/worker'))
    assert.ok(eg.isEndpointAllowed('http://192.168.1.50:9000'))
    assert.ok(eg.isEndpointAllowed('http://10.0.0.4:8080/run'))
    assert.ok(!eg.isEndpointAllowed('http://203.0.113.9:8080'))
    assert.ok(!eg.isEndpointAllowed('ftp://x'))
    assert.ok(!eg.isEndpointAllowed(''))
  })

  await test('scanResult: redacts leaked secrets, enforces size cap', () => {
    const s = eg.scanResult({ out: 'token sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA done' })
    assert.ok(s.ok)
    assert.ok(!JSON.stringify(s.result).includes('sk-ant-AAAA'))
    const big = eg.scanResult({ blob: 'x'.repeat(9 * 1024 * 1024) })
    assert.strictEqual(big.ok, false)
  })

  // ── dispatch adapter (mock registry + injected fetch) ────────────────────────
  function mockReg(worker) {
    return {
      assign: () => worker ? { target: 'remote', worker_id: worker.id, worker_name: worker.name } : { target: 'local', reason: 'no worker' },
      _getInternal: (id) => (worker && worker.id === id ? worker : null),
      _audit: () => {},
    }
  }
  const TRUSTED = {
    id: 'wkr-1', name: 'rented-a100', kind: 'rented', trust: 'trusted',
    endpoint: 'https://gpu.example.com', dispatch_key_hash: 'a'.repeat(64), capabilities: { gpu: true },
  }
  const okFetch = (body) => async () => ({ ok: true, status: 200, json: async () => body })

  await test('dispatch: refuses when not LIVE (runs local)', async () => {
    delete process.env.COMPUTE_FABRIC_LIVE
    const r = await dispatchJob({ name: 'j', payload: PUBLIC_PAYLOAD }, { registry: mockReg(TRUSTED), fetchImpl: okFetch({ result: 'x' }) })
    assert.strictEqual(r.dispatched, false)
    assert.strictEqual(r.target, 'local')
  })

  await test('dispatch: LIVE + trusted worker + public payload → dispatches, result scanned', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    const r = await dispatchJob({ name: 'j', payload: PUBLIC_PAYLOAD }, { registry: mockReg(TRUSTED), fetchImpl: okFetch({ result: 'summary done' }) })
    assert.strictEqual(r.ok, true)
    assert.strictEqual(r.dispatched, true)
    assert.strictEqual(r.egress_action, 'allow')
    assert.deepStrictEqual(r.result, { result: 'summary done' })
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  await test('dispatch: LIVE + SECRET payload → egress BLOCK, no dispatch', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    let called = false
    const spyFetch = async () => { called = true; return { ok: true, status: 200, json: async () => ({}) } }
    const r = await dispatchJob({ name: 'j', payload: SECRET_PAYLOAD }, { registry: mockReg(TRUSTED), fetchImpl: spyFetch })
    assert.strictEqual(r.dispatched, false)
    assert.strictEqual(called, false, 'must NOT contact worker with secret payload')
    assert.match(r.reason, /egress blocked/)
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  await test('dispatch: untrusted worker is refused', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    const untrusted = { ...TRUSTED, trust: 'untrusted' }
    const r = await dispatchJob({ name: 'j', payload: PUBLIC_PAYLOAD }, { registry: mockReg(untrusted), fetchImpl: okFetch({ result: 'x' }) })
    assert.strictEqual(r.dispatched, false)
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  await test('dispatch: leaked secret in worker RESULT is redacted before return', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    const r = await dispatchJob({ name: 'j', payload: PUBLIC_PAYLOAD }, { registry: mockReg(TRUSTED), fetchImpl: okFetch({ out: 'here is sk-ant-BBBBBBBBBBBBBBBBBBBBBBBB' }) })
    assert.strictEqual(r.ok, true)
    assert.ok(!JSON.stringify(r.result).includes('sk-ant-BBBB'), 'leaked secret must be redacted')
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  await test('compute-only: dispatcher has no fs / child_process capability', () => {
    const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'backend', 'compute_fabric', 'remote_dispatch.js'), 'utf8')
    assert.ok(!/require\(['"]fs['"]\)/.test(src), 'must not import fs (cannot write files)')
    assert.ok(!/require\(['"]child_process['"]\)/.test(src), 'must not import child_process (cannot run commands)')
  })

  await test('compute-only: a malicious "overwrite" result is returned as inert data, not acted on', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    const evil = okFetch({ write_file: '/etc/passwd', cmd: 'rm -rf /', result: 'x' })
    const r = await dispatchJob({ name: 'j', payload: PUBLIC_PAYLOAD }, { registry: mockReg(TRUSTED), fetchImpl: evil })
    assert.strictEqual(r.ok, true)
    assert.strictEqual(r.result_untrusted, true)
    // the dangerous fields survive only as inert data fields — nothing executes them
    assert.strictEqual(typeof r.result, 'object')
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  await test('dispatch: never throws on garbage', async () => {
    process.env.COMPUTE_FABRIC_LIVE = '1'
    await assert.doesNotReject(dispatchJob(null, { registry: mockReg(null) }))
    await assert.doesNotReject(dispatchJob({}, { registry: mockReg(TRUSTED), fetchImpl: async () => { throw new Error('boom') } }))
    delete process.env.COMPUTE_FABRIC_LIVE
  })

  console.log(`\ncompute_dispatch: ${passed} checks passed`)
})()
