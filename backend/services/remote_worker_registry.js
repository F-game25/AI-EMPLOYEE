'use strict'

/**
 * Remote worker registry + capability matching (Phase 7 worker protocol).
 *
 * Complements (does NOT duplicate) backend/compute_fabric/* — that module owns
 * provisioning (renting GPUs, gated/dry-run) and job artifact/heartbeat
 * persistence. THIS module owns the fleet of workers (rented or owned) that can
 * RUN jobs: registration, health, trust, and matching a job to a capable worker.
 *
 * Security model (deny-by-default):
 *   - Registration requires a valid single-use, short-lived, HMAC-signed PAIRING
 *     TOKEN minted by the owner. No token → no registration.
 *   - Worker-reported capabilities are UNTRUSTED data. New workers start at
 *     trust='untrusted'; the owner must promote to 'trusted'. Dangerous jobs only
 *     match 'trusted' workers.
 *   - Remote dispatch happens ONLY when COMPUTE_FABRIC_LIVE=1; otherwise every
 *     assignment falls back to local. This is a refuse-by-default gate, never a
 *     silent remote execution.
 *   - No secrets are ever stored in a worker record or returned.
 *   - Every consequential action is appended to state/remote_compute/audit.jsonl.
 *
 * This is the SERVER side of the protocol. The remote agent that actually executes
 * jobs on a worker reuses compute_fabric/persistence.js (heartbeat/collect/verify)
 * and is installed/run separately — it is intentionally out of scope here.
 */
const fs = require('fs')
const path = require('path')
const os = require('os')
const crypto = require('crypto')
const egressGuard = require('./egress_guard')

function _stateDir() {
  const home = process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
  const base = process.env.STATE_DIR || path.join(home, 'state')
  return path.join(base, 'remote_compute')
}

const SECRET = process.env.JWT_SECRET_KEY || process.env.JWT_SECRET || (() => {
  if (process.env.NODE_ENV === 'production') { throw new Error('remote_worker_registry: JWT_SECRET_KEY required in production') }
  return 'rc-dev-only-not-for-production'
})()
const LIVE = () => process.env.COMPUTE_FABRIC_LIVE === '1'
const HEARTBEAT_STALE_S = Number(process.env.REMOTE_WORKER_STALE_S || 90)
const PAIRING_TTL_MS = (Number(process.env.REMOTE_PAIRING_TTL_S || 600)) * 1000
const TRUST_RANK = { blocked: -1, untrusted: 0, trusted: 1 }

class RemoteWorkerRegistry {
  constructor(opts = {}) {
    this.dir = opts.dir || _stateDir()
    this.workersPath = path.join(this.dir, 'workers.json')
    this.pairingPath = path.join(this.dir, 'pairing.json')
    this.auditPath = path.join(this.dir, 'audit.jsonl')
  }

  _ensure() { fs.mkdirSync(this.dir, { recursive: true }) }
  _read(p, fb) { try { return JSON.parse(fs.readFileSync(p, 'utf8')) } catch { return fb } }
  _write(p, v) { this._ensure(); const t = `${p}.tmp`; fs.writeFileSync(t, JSON.stringify(v, null, 2)); fs.renameSync(t, p) }
  _audit(event, detail = {}) { try { this._ensure(); fs.appendFileSync(this.auditPath, JSON.stringify({ ts: new Date().toISOString(), event, ...detail }) + '\n') } catch { /* never throw */ } }

  // ── Pairing tokens (HMAC, single-use, short-lived) ─────────────────────────
  _sign(nonce, exp) { return crypto.createHmac('sha256', SECRET).update(`${nonce}:${exp}`).digest('hex') }

  createPairingToken(meta = {}) {
    const nonce = crypto.randomBytes(9).toString('hex')
    const exp = Date.now() + PAIRING_TTL_MS
    const store = this._read(this.pairingPath, {})
    store[nonce] = { exp, used: false, created: new Date().toISOString(), note: String(meta.note || '').slice(0, 200) }
    this._write(this.pairingPath, store)
    this._audit('pairing_token_created', { nonce })
    return { pairing_token: `${nonce}.${exp}.${this._sign(nonce, exp)}`, expires_at: exp, ttl_s: PAIRING_TTL_MS / 1000 }
  }

  _consumePairing(token) {
    const [nonce, exp, sig] = String(token || '').split('.')
    if (!nonce || !exp || !sig) return { ok: false, error: 'malformed pairing token' }
    if (sig !== this._sign(nonce, Number(exp))) return { ok: false, error: 'invalid pairing signature' }
    if (Date.now() > Number(exp)) return { ok: false, error: 'pairing token expired' }
    // Guard prototype-polluting keys before indexing the store with the token-derived
    // nonce (defense-in-depth; legit nonces are random hex from createPairingToken).
    if (nonce === '__proto__' || nonce === 'constructor' || nonce === 'prototype') {
      return { ok: false, error: 'invalid pairing token' }
    }
    const store = this._read(this.pairingPath, {})
    const a = store[nonce]
    if (!a) return { ok: false, error: 'unknown pairing token' }
    if (a.used) return { ok: false, error: 'pairing token already used' }
    a.used = true; a.used_at = new Date().toISOString(); store[nonce] = a; this._write(this.pairingPath, store)
    return { ok: true }
  }

  // ── Workers ────────────────────────────────────────────────────────────────
  _loadWorkers() { const d = this._read(this.workersPath, { workers: [] }); return Array.isArray(d.workers) ? d.workers : [] }
  _saveWorkers(ws) { this._write(this.workersPath, { workers: ws, updated_at: new Date().toISOString() }) }

  // Worker-reported capabilities are untrusted input — coerce + bound everything.
  _sanitizeCaps(c = {}) {
    return {
      gpu: !!c.gpu,
      gpu_name: c.gpu_name ? String(c.gpu_name).slice(0, 80) : null,
      vram_mb: Math.max(0, Math.round(Number(c.vram_mb) || 0)),
      ram_mb: Math.max(0, Math.round(Number(c.ram_mb) || 0)),
      cpu: Math.max(0, Math.round(Number(c.cpu) || 0)),
      models: Array.isArray(c.models) ? c.models.slice(0, 50).map(m => String(m).slice(0, 100)) : [],
    }
  }

  _ageS(w) { const t = Date.parse(w.last_heartbeat || ''); return Number.isFinite(t) ? Math.round((Date.now() - t) / 1000) : null }
  _withAge(w) {
    const age = this._ageS(w)
    const status = w.status === 'offline' ? 'offline' : (age != null && age > HEARTBEAT_STALE_S ? 'offline' : 'online')
    return { ...w, heartbeat_age_s: age, status }
  }

  // Validate a worker-reported endpoint against the egress policy allow-list
  // (private LAN for paired machines, https for rented/cloud). Untrusted input.
  _validateEndpoint(endpoint) {
    const url = String(endpoint || '').slice(0, 300)
    if (!url) return { ok: false, error: 'endpoint required for dispatchable worker' }
    if (!egressGuard.isEndpointAllowed(url)) return { ok: false, error: 'endpoint not in allow-list (private-LAN or https only)' }
    return { ok: true, url }
  }

  register({ pairing_token, name, capabilities, endpoint, kind: kindIn } = {}) {
    const pair = this._consumePairing(pairing_token)
    if (!pair.ok) { this._audit('register_denied', { reason: pair.error }); return { ok: false, error: pair.error } }
    // Endpoint is optional at registration but REQUIRED before remote dispatch.
    let url = null
    if (endpoint != null && endpoint !== '') {
      const ev = this._validateEndpoint(endpoint)
      if (!ev.ok) { this._audit('register_denied', { reason: ev.error }); return { ok: false, error: ev.error } }
      url = ev.url
    }
    // 'peer' = your own LAN machine (laptop/PC); 'rented' = cloud GPU. Unknown →
    // 'rented' (the stricter egress tier) so we never under-redact by default.
    const kind = kindIn === 'peer' ? 'peer' : 'rented'
    const workerId = `wkr-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
    // Per-worker dispatch key is DERIVED from the server master secret + a stored
    // per-worker salt: dispatch_key = HMAC(SERVER_SECRET, id:salt). Only the salt
    // (non-secret) is persisted — a leaked workers.json cannot forge a job token
    // without SERVER_SECRET. The derived key is returned to the worker exactly once
    // and re-derived server-side on each dispatch. Rotating the salt revokes it.
    const keySalt = crypto.randomBytes(16).toString('hex')
    const dispatchKey = this._deriveSigningKey(workerId, keySalt)
    const worker = {
      id: workerId,
      name: String(name || 'worker').slice(0, 80),
      kind,
      capabilities: this._sanitizeCaps(capabilities),
      endpoint: url,
      key_salt: keySalt,
      trust: 'untrusted',
      status: 'online',
      registered_at: new Date().toISOString(),
      last_heartbeat: new Date().toISOString(),
    }
    const ws = this._loadWorkers(); ws.unshift(worker); this._saveWorkers(ws)
    this._audit('worker_registered', { id: worker.id, name: worker.name, has_endpoint: !!url })
    // The derived dispatch_key is returned exactly once and never stored/logged.
    return { ok: true, worker: this._publicWorker(this._withAge(worker)), dispatch_key: dispatchKey }
  }

  // Derive a worker's job-token signing key from the server master secret + salt.
  // Never stored; re-derived on demand so workers.json holds no signing material.
  _deriveSigningKey(workerId, salt) {
    return crypto.createHmac('sha256', SECRET).update(`${workerId}:${salt}`).digest('hex')
  }

  // The signing key for a known worker, or null. Internal — never exposed via a route.
  signingKeyFor(workerId) {
    const w = this._getInternal(workerId)
    return w && w.key_salt ? this._deriveSigningKey(w.id, w.key_salt) : null
  }

  // Strip server-only material (the key salt) from any worker returned to callers.
  _publicWorker(w) { if (!w) return w; const { key_salt, ...rest } = w; return rest }

  heartbeat(id, info = {}) {
    const ws = this._loadWorkers(); const w = ws.find(x => x.id === id)
    if (!w) return { ok: false, error: 'worker not found' }
    w.last_heartbeat = new Date().toISOString()
    if (w.status === 'offline') w.status = 'online'
    if (info.capabilities) w.capabilities = this._sanitizeCaps({ ...w.capabilities, ...info.capabilities })
    if (info.endpoint != null && info.endpoint !== '') {
      const ev = this._validateEndpoint(info.endpoint)
      if (!ev.ok) return { ok: false, error: ev.error }
      w.endpoint = ev.url
    }
    this._saveWorkers(ws)
    return { ok: true, worker: this._publicWorker(this._withAge(w)) }
  }

  setTrust(id, trust) {
    if (!Object.prototype.hasOwnProperty.call(TRUST_RANK, trust)) return { ok: false, error: 'invalid trust level (untrusted|trusted|blocked)' }
    const ws = this._loadWorkers(); const w = ws.find(x => x.id === id)
    if (!w) return { ok: false, error: 'worker not found' }
    w.trust = trust; this._saveWorkers(ws); this._audit('worker_trust_set', { id, trust })
    return { ok: true, worker: this._publicWorker(this._withAge(w)) }
  }

  // Internal-only: full record incl. dispatch_key_hash, for the dispatch adapter.
  // NEVER exposed through a route. Returns null if absent.
  _getInternal(id) { return this._loadWorkers().find(x => x.id === id) || null }

  deregister(id) {
    const ws = this._loadWorkers(); const i = ws.findIndex(x => x.id === id)
    if (i < 0) return { ok: false, error: 'worker not found' }
    ws.splice(i, 1); this._saveWorkers(ws); this._audit('worker_deregistered', { id })
    return { ok: true }
  }

  list() { return this._loadWorkers().map(w => this._publicWorker(this._withAge(w))) }
  get(id) { const w = this._loadWorkers().find(x => x.id === id); return w ? this._publicWorker(this._withAge(w)) : null }

  // ── Capability matching + assignment ────────────────────────────────────────
  selectWorker(req = {}) {
    const need = {
      vram_mb: Number(req.vram_mb) || 0,
      needs_gpu: !!req.needs_gpu,
      model: req.model ? String(req.model) : null,
      min_trust: req.dangerous ? 'trusted' : (req.min_trust || 'untrusted'),
    }
    const minRank = TRUST_RANK[need.min_trust] != null ? TRUST_RANK[need.min_trust] : 0
    return this.list()
      .filter(w => {
        if (w.status !== 'online') return false
        if (w.trust === 'blocked') return false
        if (TRUST_RANK[w.trust] < minRank) return false
        if (!w.endpoint) return false // no endpoint → cannot be dispatched to
        if (need.needs_gpu && !w.capabilities.gpu) return false
        if (need.vram_mb && w.capabilities.vram_mb < need.vram_mb) return false
        if (need.model && !(w.capabilities.models || []).includes(need.model)) return false
        return true
      })
      .sort((a, b) => (b.capabilities.vram_mb || 0) - (a.capabilities.vram_mb || 0))[0] || null
  }

  // Decide where a job runs. Deny-by-default: remote only when LIVE *and* a
  // compatible trusted-enough worker exists; otherwise fall back to local.
  assign(job = {}) {
    const req = job.requirements || {}
    if (!LIVE()) { this._audit('assign_local', { reason: 'not_live', job: job.name || null }); return { target: 'local', reason: 'COMPUTE_FABRIC_LIVE not set — running locally' } }
    const w = this.selectWorker(req)
    if (!w) { this._audit('assign_local', { reason: 'no_match', job: job.name || null }); return { target: 'local', reason: 'no compatible online worker — falling back to local' } }
    this._audit('assign_remote', { worker_id: w.id, job: job.name || null })
    return { target: 'remote', worker_id: w.id, worker_name: w.name, worker: w }
  }

  auditTail(limit = 100) {
    try { return fs.readFileSync(this.auditPath, 'utf8').trim().split('\n').filter(Boolean).slice(-limit).map(l => JSON.parse(l)) } catch { return [] }
  }
}

let _inst = null
function getRemoteWorkerRegistry() { return _inst || (_inst = new RemoteWorkerRegistry()) }

module.exports = { RemoteWorkerRegistry, getRemoteWorkerRegistry }
