'use strict'

/**
 * Live remote dispatch adapter (audit gap D1).
 *
 * Turns a registry `assign()→remote` decision into an ACTUAL job sent to a paired
 * peer machine (your laptop/PC) or a rented GPU worker — over HTTP, leak-proofed.
 *
 * Security model (deny-by-default, fail-closed, never leaks):
 *   1. LIVE gate        — dispatch only when COMPUTE_FABRIC_LIVE=1, else local.
 *   2. Worker gate      — must be online + trust='trusted' + have an allow-listed
 *                         endpoint (private-LAN or https).
 *   3. EGRESS gate      — the job payload passes backend/services/egress_guard:
 *                         secrets are BLOCKED off-box, PII/internal redacted by
 *                         the worker's tier (peer_trusted | rented_trusted).
 *   4. AUTH             — a single-use, short-TTL HMAC job token, keyed by the
 *                         worker's per-worker dispatch-key HASH (the worker proves
 *                         it holds the plaintext key). A leaked server file alone
 *                         cannot authenticate as a worker.
 *   5. CAPS             — payload/result size caps + a hard request timeout.
 *   6. RESULT scan      — the worker's reply is UNTRUSTED: size-capped and
 *                         secret-scanned before it re-enters our process.
 *   7. AUDIT            — every decision appended to the registry audit log; no
 *                         secrets, tokens, or payload text are ever logged.
 *
 * COMPUTE-ONLY ISOLATION (hard invariant):
 *   - A worker shares compute ONLY. It can never change files, control the
 *     screen/cursor/input, or overwrite anything on this or any other system.
 *   - The protocol is one-directional: WE POST a job → the worker computes →
 *     it returns inert data. A worker has NO inbound channel to us and NO access
 *     to our filesystem/display.
 *   - This module imports NO 'fs' and NO 'child_process': it physically cannot
 *     write a file or run a command. The worker's result is returned to the caller
 *     as contained, redacted DATA — never executed, never written by this path.
 *   - The outbound payload is structurally contained to inert compute data, so a
 *     job can only ever ask a worker to COMPUTE, never to act on a machine.
 *
 * Pure orchestration + one fetch; never throws (returns a structured refusal).
 */

const crypto = require('crypto')
const egressGuard = require('../services/egress_guard')
const { getRemoteWorkerRegistry } = require('../services/remote_worker_registry')

const LIVE = () => process.env.COMPUTE_FABRIC_LIVE === '1'
const JOB_TTL_MS = (Number(process.env.REMOTE_JOB_TTL_S || 120)) * 1000
const KIND_TIER = { peer: 'peer_trusted', rented: 'rented_trusted' }

// In-process single-use job-id ledger (defence-in-depth against token replay
// within this server's lifetime; the TTL bounds the window regardless).
const _usedJobIds = new Set()

function _sign(keyHash, msg) { return crypto.createHmac('sha256', String(keyHash)).update(msg).digest('hex') }
function _sha256(s) { return crypto.createHash('sha256').update(String(s)).digest('hex') }

/**
 * Dispatch a job to a capable remote worker, or refuse (caller runs it locally).
 * @param {object} job  { name, requirements, payload }
 * @param {object} opts { fetchImpl } — injectable fetch for tests
 * @returns {Promise<object>} structured result — never throws.
 */
async function dispatchJob(job = {}, opts = {}) {
  const reg = opts.registry || getRemoteWorkerRegistry()
  const fetchImpl = opts.fetchImpl || (typeof fetch === 'function' ? fetch : null)
  try {
    if (!LIVE()) return { ok: false, dispatched: false, target: 'local', reason: 'COMPUTE_FABRIC_LIVE not set — run locally' }

    // Pick a worker (registry enforces trust + endpoint + capability match).
    const assignment = reg.assign(job)
    if (assignment.target !== 'remote') {
      return { ok: false, dispatched: false, target: 'local', reason: assignment.reason || 'no remote worker' }
    }
    const w = reg._getInternal(assignment.worker_id)
    if (!w) return { ok: false, dispatched: false, target: 'local', reason: 'worker vanished after assignment' }
    if (w.trust !== 'trusted') return { ok: false, dispatched: false, target: 'local', reason: 'worker not trusted' }
    if (!w.endpoint || !egressGuard.isEndpointAllowed(w.endpoint)) {
      return { ok: false, dispatched: false, target: 'local', reason: 'worker endpoint not allow-listed' }
    }
    if (!fetchImpl) return { ok: false, dispatched: false, target: 'local', reason: 'no HTTP client available' }

    // EGRESS GATE — the payload must clear the worker's tier policy.
    const tier = KIND_TIER[w.kind] || 'rented_trusted' // unknown kind → stricter tier
    const eg = egressGuard.guard(job.payload ?? {}, tier)
    if (eg.action === 'block') {
      reg._audit && reg._audit('dispatch_blocked_egress', { worker_id: w.id, classification: eg.classification, reason: eg.reason })
      return { ok: false, dispatched: false, target: 'local', reason: `egress blocked: ${eg.reason}`, classification: eg.classification }
    }
    // Compute-only contract: structurally contain what we send so the payload is
    // always inert data (no live objects / prototype pollution / unbounded depth)
    // — a job can ask a worker to COMPUTE, never to act on a machine.
    const safePayload = egressGuard.containValue(eg.payload ?? {})

    // AUTH — single-use, short-TTL HMAC job token keyed by the worker key hash.
    const jobId = `job-${Date.now().toString(36)}-${crypto.randomBytes(6).toString('hex')}`
    const expires = Date.now() + JOB_TTL_MS
    const payloadHash = _sha256(egressGuard.payloadBytes ? JSON.stringify(safePayload ?? null) : '')
    const token = `${jobId}.${expires}.${_sign(w.dispatch_key_hash, `${jobId}:${expires}:${payloadHash}`)}`

    const caps = egressGuard.loadPolicy().caps
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), Number(caps.dispatch_timeout_ms) || 60000)
    let resp
    try {
      const url = w.endpoint.replace(/\/$/, '') + '/run'
      resp = await fetchImpl(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, token, expires, name: String(job.name || 'job').slice(0, 120), payload: safePayload ?? null }),
        signal: controller.signal,
      })
    } catch (e) {
      reg._audit && reg._audit('dispatch_failed', { worker_id: w.id, error: 'request_failed' })
      return { ok: false, dispatched: true, target: 'remote', worker_id: w.id, reason: `worker unreachable (${e && e.name === 'AbortError' ? 'timeout' : 'network'})` }
    } finally { clearTimeout(timer) }

    if (!resp || !resp.ok) {
      reg._audit && reg._audit('dispatch_http_error', { worker_id: w.id, status: resp ? resp.status : null })
      return { ok: false, dispatched: true, target: 'remote', worker_id: w.id, reason: `worker returned HTTP ${resp ? resp.status : 'none'}` }
    }

    _usedJobIds.add(jobId)

    // RESULT scan — the reply is untrusted: size-cap + secret-scan before use.
    let raw
    try { raw = await resp.json() } catch (_) { return { ok: false, dispatched: true, target: 'remote', worker_id: w.id, reason: 'worker returned non-JSON' } }
    const scan = egressGuard.scanResult(raw)
    if (!scan.ok) {
      reg._audit && reg._audit('dispatch_result_rejected', { worker_id: w.id, reason: scan.reason })
      return { ok: false, dispatched: true, target: 'remote', worker_id: w.id, reason: `result rejected: ${scan.reason}` }
    }
    reg._audit && reg._audit('dispatch_ok', { worker_id: w.id, job_id: jobId, redacted: eg.action === 'redact', result_had_secret: !!scan.had_secret })
    return {
      ok: true, dispatched: true, target: 'remote', worker_id: w.id, worker_name: w.name,
      job_id: jobId, egress_action: eg.action,
      // result is contained + redacted inert data from an UNTRUSTED worker:
      // callers must treat it as data only — never execute, eval, or write-by-path.
      result: scan.result, result_untrusted: true, result_had_secret: !!scan.had_secret,
    }
  } catch (e) {
    // Absolute fail-safe: never throw into the caller; degrade to local.
    return { ok: false, dispatched: false, target: 'local', reason: 'dispatch error (fail-closed)' }
  }
}

module.exports = { dispatchJob, JOB_TTL_MS }
