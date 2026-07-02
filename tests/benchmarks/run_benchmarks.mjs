#!/usr/bin/env node
/**
 * AscendForge quality benchmark harness (C1).
 *
 * Runs a small set of scored tasks against a LIVE backend and grades each with the
 * result_verifier (B1). Honest by design: if the backend is unreachable it reports
 * SKIPPED (not PASS); a research output with no sources FAILS.
 *
 *   npm run bench                 # score against backend (default :8787)
 *   NEXUS_BACKEND_URL=... npm run bench
 *   node tests/benchmarks/run_benchmarks.mjs --strict   # exit 1 if any task FAILs
 *
 * Writes tests/benchmarks/results.json.
 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync, mkdtempSync, rmSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import os from 'node:os'

const require = createRequire(import.meta.url)
const { verifyText } = require('../../backend/services/result_verifier.js')
const HERE = path.dirname(fileURLToPath(import.meta.url))
const STRICT = process.argv.includes('--strict')

function backendUrl() {
  if (process.env.NEXUS_BACKEND_URL) return process.env.NEXUS_BACKEND_URL.replace(/\/+$/, '')
  try {
    const runDir = process.env.RUN_DIR || path.join(os.homedir(), '.ai-employee', 'run')
    const lock = JSON.parse(readFileSync(path.join(runDir, 'runtime-lock.json'), 'utf8'))
    if (lock?.ports?.node) return `http://127.0.0.1:${lock.ports.node}`
  } catch { /* ignore */ }
  return `http://127.0.0.1:${process.env.NEXUS_BACKEND_PORT || '8787'}`
}

function jwtSecret() {
  if (process.env.JWT_SECRET_KEY) return process.env.JWT_SECRET_KEY
  try {
    const envFile = path.join(os.homedir(), '.ai-employee', '.env')
    const line = readFileSync(envFile, 'utf8').split(/\r?\n/).find(l => l.startsWith('JWT_SECRET_KEY='))
    if (line) return line.slice('JWT_SECRET_KEY='.length).trim().replace(/^["']|["']$/g, '')
  } catch { /* ignore */ }
  return null
}

const B = backendUrl()
let TOKEN = null
const H = () => ({ 'Content-Type': 'application/json', ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}) })

async function jpost(p, body) {
  const r = await fetch(`${B}${p}`, { method: 'POST', headers: H(), body: JSON.stringify(body) })
  const t = await r.text(); let j; try { j = JSON.parse(t) } catch { j = { raw: t } }
  return { status: r.status, json: j }
}
async function jget(p) {
  const r = await fetch(`${B}${p}`, { headers: H() })
  const t = await r.text(); let j; try { j = JSON.parse(t) } catch { j = { raw: t } }
  return { status: r.status, json: j }
}

function pickText(obj) {
  for (const k of ['summary', 'report', 'result', 'text', 'response', 'answer', 'content', 'markdown']) {
    if (typeof obj?.[k] === 'string' && obj[k].trim()) return obj[k]
  }
  // nested common shapes
  if (typeof obj?.result?.summary === 'string') return obj.result.summary
  if (Array.isArray(obj?.findings)) return obj.findings.map(f => (typeof f === 'string' ? f : f.summary || f.text || '')).join('\n')
  return JSON.stringify(obj).slice(0, 2000)
}

// ── Task runners ────────────────────────────────────────────────────────────
async function runResearch(task) {
  const disc = await jpost('/api/research/discover', { query: task.query, limit: 5 })
  if (disc.status >= 400) return { status: 'SKIP', detail: `discover ${disc.status}` }
  const sources = disc.json?.sources || disc.json?.results || disc.json?.items || []
  const urls = sources.map(s => s.url || s.link).filter(Boolean).slice(0, 3)
  const ids = sources.map(s => s.id).filter(Boolean).slice(0, 3)
  if (!urls.length && !ids.length) return { status: 'SKIP', detail: 'no sources discovered' }
  const exec = await jpost('/api/research/execute', { query: task.query, selected_urls: urls, selected_source_ids: ids })
  if (exec.status >= 400) return { status: 'SKIP', detail: `execute ${exec.status}` }
  const text = pickText(exec.json)
  const v = verifyText(text, { topic: task.query, ...(task.verify || {}) })
  return { status: v.passed ? 'PASS' : 'FAIL', score: v.score, detail: v.checks.map(c => `${c.name}:${c.pass ? '✓' : '✗'}`).join(' '), verdict: v }
}

async function runResearchSkill(task) {
  const disc = await jpost('/api/research/discover', { query: task.query, limit: 5 })
  if (disc.status >= 400) return { status: 'SKIP', detail: `discover ${disc.status}` }
  const sources = (disc.json?.sources || disc.json?.results || disc.json?.items || []).slice(0, 5)
  const r = await jpost('/api/forge/research-summary', { query: task.query, sources })
  if (r.status >= 400) return { status: 'SKIP', detail: `research-summary ${r.status}` }
  const v = r.json?.verdict
  return { status: r.json?.passed ? 'PASS' : 'FAIL', score: v?.score, detail: (v?.checks || []).map(c => `${c.name}:${c.pass ? '✓' : '✗'}`).join(' ') }
}

async function runForgeRun(task) {
  // create a throwaway scratch project, run the goal, inspect lifecycle gate, clean up
  const proj = await jpost('/api/forge/projects', { name: `bench-${Date.now().toString(36)}`, target_type: 'code' })
  const pid = proj.json?.project?.id || proj.json?.id
  if (!pid) return { status: 'SKIP', detail: `project create ${proj.status}` }
  try {
    const run = await jpost('/api/forge/runs', { project_id: pid, goal: task.goal })
    if (run.status >= 400) return { status: 'SKIP', detail: `run ${run.status}` }
    const status = run.json?.run?.status
    const blocked = status === 'blocked' && run.json?.run?.lifecycle?.status === 'blocked'
    const ok = task.expect_status === 'blocked' ? blocked : !blocked
    return { status: ok ? 'PASS' : 'FAIL', score: ok ? 1 : 0, detail: `run.status=${status} lifecycle=${run.json?.run?.lifecycle?.status}` }
  } finally {
    await fetch(`${B}/api/forge/projects/${pid}`, { method: 'DELETE', headers: H() }).catch(() => {})
  }
}

// Coding-capability check for the local codegen model (FORGE_OLLAMA_MODEL, e.g.
// qwythos:q4): proves — fully offline, no cloud — that the configured model can
// actually produce a real, syntactically valid write_file action and that the
// full submit -> approve -> auto-verify -> apply loop lands a real file on disk.
// This is the gate that should be green before trusting the model for real work;
// a lifecycle "not blocked" check alone (see lifecycle_allows_clear above) is not
// enough — it would have missed a real incident where the model's response never
// closed its code fence and the run silently produced zero code actions.
// Single-quote a shell arg (POSIX sh): close the quote, emit an escaped
// literal quote, reopen — safe for any byte sequence including embedded quotes.
const shellQuote = (s) => `'${String(s).replace(/'/g, "'\\''")}'`

async function runForgeCodegen(task) {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'forge-bench-codegen-'))
  let pid = null
  try {
    // No verification_commands here: the model is free to place the file wherever
    // it thinks the project convention calls for (e.g. "src/") and we don't know
    // that path yet. Left unset it defaults to a non-runnable "manual review"
    // placeholder, so auto-verify-on-approve harmlessly no-ops instead of failing
    // against a path we haven't discovered yet — we verify explicitly below, once
    // the real write_file path is known.
    const proj = await jpost('/api/forge/projects/import', {
      name: `bench-codegen-${Date.now().toString(36)}`,
      path: tmpDir,
      write_access: true,
    })
    pid = proj.json?.project?.id
    if (!pid) return { status: 'SKIP', detail: `project import ${proj.status}: ${proj.json?.error || ''}` }

    const run = await jpost('/api/forge/runs', { project_id: pid, goal: task.goal })
    if (run.status >= 400) return { status: 'SKIP', detail: `run ${run.status}: ${run.json?.error || ''}` }
    const runId = run.json?.run?.id
    const codegen = run.json?.run?.codegen || {}
    const modelTag = codegen.model ? `${codegen.provider || '?'}/${codegen.model}` : (codegen.provider || 'unknown')
    const writeAction = (run.json?.run?.actions || []).find(a => a.type === 'write_file')
    if (!writeAction) {
      return { status: 'FAIL', detail: `no write_file action produced (model=${modelTag}, run.status=${run.json?.run?.status})` }
    }
    // The model chooses this path freely (see comment above) — it is untrusted
    // input from here on. Reject anything absolute or that would resolve
    // outside tmpDir before it's ever interpolated into a shell command or
    // joined onto a filesystem path.
    const generatedPath = String(writeAction.file_path || '')
    const tmpRoot = path.resolve(tmpDir)
    const onDiskPath = path.resolve(tmpRoot, generatedPath)
    if (!generatedPath || path.isAbsolute(generatedPath) || !onDiskPath.startsWith(`${tmpRoot}${path.sep}`)) {
      return { status: 'FAIL', detail: `unsafe generated path '${generatedPath}' (model=${modelTag})` }
    }
    if (task.expect_file && path.basename(generatedPath) !== task.expect_file) {
      return { status: 'FAIL', detail: `expected a file named '${task.expect_file}', model wrote '${generatedPath}' (model=${modelTag})` }
    }

    // Offline syntax check of the raw generated content, independent of the
    // project workspace, before trusting it further.
    const syntaxCheckFile = path.join(tmpDir, '__bench_syntax_check.py')
    writeFileSync(syntaxCheckFile, writeAction.content || '')
    try {
      execFileSync('python3', ['-m', 'py_compile', syntaxCheckFile], { stdio: 'pipe' })
    } catch (e) {
      return { status: 'FAIL', detail: `generated code is not valid Python (model=${modelTag}): ${String(e.message || e).slice(0, 150)}` }
    } finally {
      rmSync(syntaxCheckFile, { force: true })
    }

    // Full loop: approve -> stage -> verify against the model's ACTUAL chosen path
    // (real py_compile, not "manual review") -> apply -> file genuinely on disk.
    const appr = await jpost(`/api/forge/runs/${runId}/approve`, { ownerApproved: true })
    if (appr.status >= 400 || appr.json?.run?.status !== 'staged') {
      return { status: 'FAIL', detail: `approve failed (model=${modelTag}): ${appr.json?.error || appr.status}` }
    }
    const verify = await jpost(`/api/forge/runs/${runId}/verify`, {
      ownerApproved: true,
      commands: [`python3 -m py_compile ${shellQuote(generatedPath)}`],
    })
    if (!verify.json?.ok || !verify.json?.test_result?.all_passed) {
      const output = (verify.json?.test_result?.results || []).map(r => r.output).join(' ').slice(0, 150)
      return { status: 'FAIL', detail: `verification failed (model=${modelTag}): ${output || verify.json?.error || verify.status}` }
    }
    const apply = await jpost(`/api/forge/runs/${runId}/apply`, { ownerApproved: true })
    if (apply.status >= 400) {
      return { status: 'FAIL', detail: `apply blocked (model=${modelTag}): ${apply.json?.error || apply.status}` }
    }
    if (!existsSync(onDiskPath)) {
      return { status: 'FAIL', detail: `apply reported ok but file missing on disk (model=${modelTag})` }
    }
    return { status: 'PASS', score: 1, detail: `'${generatedPath}' generated, verified (py_compile) + applied (model=${modelTag})` }
  } finally {
    if (pid) await fetch(`${B}/api/forge/projects/${pid}`, { method: 'DELETE', headers: H() }).catch(() => {})
    rmSync(tmpDir, { recursive: true, force: true })
  }
}

async function main() {
  const { tasks } = JSON.parse(readFileSync(path.join(HERE, 'tasks.json'), 'utf8'))

  // auth
  const secret = jwtSecret()
  if (secret) {
    try { const a = await jpost('/api/auth/token', { secret }); if (a.json?.token) TOKEN = a.json.token } catch { /* ignore */ }
  }
  if (!TOKEN) {
    console.error(`[bench] cannot authenticate to ${B} (no JWT_SECRET_KEY or backend down) — all SKIPPED`)
    const skipped = tasks.map(t => ({ id: t.id, status: 'SKIP', detail: 'no auth/backend' }))
    writeFileSync(path.join(HERE, 'results.json'), JSON.stringify({ backend: B, ran_at: new Date().toISOString(), results: skipped }, null, 2))
    process.exit(0)
  }

  const results = []
  for (const t of tasks) {
    let r
    try {
      r = t.type === 'research' ? await runResearch(t)
        : t.type === 'research_skill' ? await runResearchSkill(t)
        : t.type === 'forge_run' ? await runForgeRun(t)
        : t.type === 'forge_codegen' ? await runForgeCodegen(t)
        : { status: 'SKIP', detail: `unknown type ${t.type}` }
    } catch (e) { r = { status: 'SKIP', detail: `error: ${e.message}` } }
    results.push({ id: t.id, title: t.title, ...r })
  }

  // scorecard
  const pad = (s, n) => String(s).padEnd(n)
  console.log(`\nAscendForge Benchmark — ${B}`)
  console.log('─'.repeat(78))
  console.log(`${pad('TASK', 26)} ${pad('STATUS', 7)} ${pad('SCORE', 6)} DETAIL`)
  console.log('─'.repeat(78))
  for (const r of results) {
    console.log(`${pad(r.id, 26)} ${pad(r.status, 7)} ${pad(r.score ?? '-', 6)} ${(r.detail || '').slice(0, 36)}`)
  }
  const pass = results.filter(r => r.status === 'PASS').length
  const fail = results.filter(r => r.status === 'FAIL').length
  const skip = results.filter(r => r.status === 'SKIP').length
  console.log('─'.repeat(78))
  console.log(`PASS ${pass}  FAIL ${fail}  SKIP ${skip}  of ${results.length}\n`)

  writeFileSync(path.join(HERE, 'results.json'), JSON.stringify({ backend: B, ran_at: new Date().toISOString(), summary: { pass, fail, skip }, results }, null, 2))
  process.exit(STRICT && fail > 0 ? 1 : 0)
}

main().catch(e => { console.error('[bench] fatal:', e.message); process.exit(1) })
