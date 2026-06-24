'use strict'

/**
 * Egress guard — the never-leak gate for the compute fabric.
 *
 * NOTHING leaves this machine to a remote destination (paired peer, rented GPU,
 * or external API) without passing through here first. CLAUDE.md #5/#20: secrets
 * must never be sent off-box; sensitive data must be redacted; data classification
 * rules are enforced server-side, deny-by-default, fail-closed.
 *
 *   classify(payload)            → highest data classification found
 *                                  (public < internal < pii < secret)
 *   guard(payload, destTier)     → { action, payload, classification, ... }
 *                                  action ∈ allow | redact | block
 *   isEndpointAllowed(url)       → only private-LAN / https endpoints dispatch
 *
 * Redaction reuses backend/services/forge_learning.scrubSecretsFromLearningData
 * (battle-tested deep secret scrub). Policy: runtime/config/egress_policy.json,
 * with baked-in defaults so the gate never crashes open.
 *
 * Pure, no network, never throws. On ANY error it returns BLOCK (fail-closed).
 */

const fs = require('fs')
const path = require('path')
const { scrubSecretsFromLearningData } = require('./forge_learning')

const DEFAULTS = {
  destination_tiers: { local: 0, peer_trusted: 1, rented_trusted: 2, external_api: 3 },
  classification_rank: { public: 0, internal: 1, pii: 2, secret: 3 },
  policy_matrix: {
    local: { secret: 'allow', pii: 'allow', internal: 'allow', public: 'allow' },
    peer_trusted: { secret: 'block', pii: 'redact', internal: 'allow', public: 'allow' },
    rented_trusted: { secret: 'block', pii: 'redact', internal: 'redact', public: 'allow' },
    external_api: { secret: 'block', pii: 'redact', internal: 'redact', public: 'allow' },
  },
  caps: { max_payload_bytes: 2097152, dispatch_timeout_ms: 60000, max_result_bytes: 8388608 },
  endpoint_allow: {
    url_patterns: [
      '^https://',
      '^http://(localhost|127\\.0\\.0\\.1)(:\\d+)?(/|$)',
      '^http://10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}(:\\d+)?(/|$)',
      '^http://192\\.168\\.\\d{1,3}\\.\\d{1,3}(:\\d+)?(/|$)',
      '^http://172\\.(1[6-9]|2\\d|3[01])\\.\\d{1,3}\\.\\d{1,3}(:\\d+)?(/|$)',
    ],
  },
}

const CONFIG_PATH = path.join(__dirname, '..', '..', 'runtime', 'config', 'egress_policy.json')

let _cfg = null
function loadPolicy() {
  if (_cfg) return _cfg
  let f = {}
  try { f = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')) } catch (_) { f = {} }
  _cfg = {
    ...DEFAULTS, ...f,
    destination_tiers: { ...DEFAULTS.destination_tiers, ...(f.destination_tiers || {}) },
    classification_rank: { ...DEFAULTS.classification_rank, ...(f.classification_rank || {}) },
    policy_matrix: { ...DEFAULTS.policy_matrix, ...(f.policy_matrix || {}) },
    caps: { ...DEFAULTS.caps, ...(f.caps || {}) },
    endpoint_allow: { ...DEFAULTS.endpoint_allow, ...(f.endpoint_allow || {}) },
  }
  return _cfg
}
function _resetPolicy() { _cfg = null }

// PII / internal detectors (secret detection is delegated to the scrubber).
const PII_RE = [
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/,                 // email
  /\b(?:\+?\d[\d\s().-]{7,}\d)\b/,                                   // phone-ish
  /\b(?:\d[ -]*?){13,19}\b/,                                        // card-ish
]
const INTERNAL_RE = [
  /(?:^|[\s"'`(=])\/(?:home|root|etc|var|usr|opt|Users)\//,         // absolute fs paths
  /\b[A-Za-z0-9_-]+\.(?:local|internal|lan|home)\b/,                // internal hostnames
]

const _stringify = (p) => {
  try { return typeof p === 'string' ? p : JSON.stringify(p) } catch (_) { return String(p) }
}

// Did the deep secret-scrub change anything? If so, the payload contained a secret.
function containsSecret(payload) {
  try {
    const before = _stringify(payload)
    const after = _stringify(scrubSecretsFromLearningData(payload))
    return before !== after
  } catch (_) { return true } // fail-closed: assume secret on error
}

function classify(payload) {
  try {
    if (containsSecret(payload)) return 'secret'
    const text = _stringify(payload)
    if (PII_RE.some(re => re.test(text))) return 'pii'
    if (INTERNAL_RE.some(re => re.test(text))) return 'internal'
    return 'public'
  } catch (_) { return 'secret' } // fail-closed
}

// Redact PII spans (email/phone/card) in a single string.
function redactPIIString(s) {
  let out = String(s)
  for (const re of PII_RE) out = out.replace(new RegExp(re.source, 'g'), '[REDACTED_PII]')
  return out
}

// Walk a JSON-ish structure applying fn to every string value. Bounded depth so a
// hostile deeply-nested payload can't blow the stack.
function _deepMapStrings(v, fn, depth = 0) {
  if (depth > 64) return '[TRUNCATED_DEPTH]'
  if (typeof v === 'string') return fn(v)
  if (Array.isArray(v)) return v.map(x => _deepMapStrings(x, fn, depth + 1))
  if (v && typeof v === 'object') {
    const out = {}
    for (const [k, val] of Object.entries(v)) {
      if (k === '__proto__' || k === 'constructor' || k === 'prototype') continue // strip pollution keys
      out[k] = _deepMapStrings(val, fn, depth + 1)
    }
    return out
  }
  return v
}

// Full redaction: secrets (deep scrub + key-drop) AND PII. Used whenever the
// policy action is 'redact'.
function redact(payload) {
  try {
    const noSecrets = scrubSecretsFromLearningData(payload)
    return _deepMapStrings(noSecrets, redactPIIString)
  } catch (_) { return '[REDACTED]' }
}

function isEndpointAllowed(url) {
  try {
    const u = String(url || '')
    if (!u) return false
    return (loadPolicy().endpoint_allow.url_patterns || []).some(p => {
      try { return new RegExp(p).test(u) } catch (_) { return false }
    })
  } catch (_) { return false }
}

function payloadBytes(payload) {
  try { return Buffer.byteLength(_stringify(payload), 'utf8') } catch (_) { return Infinity }
}

/**
 * Decide whether `payload` may leave to `destinationTier`. NEVER throws.
 * Returns { action, payload, classification, tier, reason }.
 *   - action 'block'  → do not send. payload is null.
 *   - action 'redact' → send the returned (scrubbed) payload.
 *   - action 'allow'  → send payload as-is.
 */
function guard(payload, destinationTier) {
  try {
    const cfg = loadPolicy()
    const tier = String(destinationTier || '')
    // Unknown destination → deny-by-default.
    if (!(tier in cfg.policy_matrix)) {
      return { action: 'block', payload: null, classification: 'unknown', tier, reason: `unknown destination tier '${tier}'` }
    }
    // Oversize → block (an attacker can't exfiltrate a huge blob).
    const bytes = payloadBytes(payload)
    if (bytes > Number(cfg.caps.max_payload_bytes)) {
      return { action: 'block', payload: null, classification: 'oversize', tier, reason: `payload ${bytes}B exceeds cap ${cfg.caps.max_payload_bytes}B` }
    }
    const cls = classify(payload)
    const action = (cfg.policy_matrix[tier] && cfg.policy_matrix[tier][cls]) || 'block' // missing rule → block
    if (action === 'allow') return { action: 'allow', payload, classification: cls, tier, reason: 'within policy' }
    if (action === 'redact') return { action: 'redact', payload: redact(payload), classification: cls, tier, reason: `${cls} redacted for ${tier}` }
    return { action: 'block', payload: null, classification: cls, tier, reason: `${cls} not permitted to ${tier}` }
  } catch (e) {
    return { action: 'block', payload: null, classification: 'error', tier: String(destinationTier || ''), reason: 'egress guard error (fail-closed)' }
  }
}

// Structurally CONTAIN an untrusted inbound value: a compromised/malware-infected
// worker must not be able to contaminate this process. We accept ONLY plain JSON
// primitives, drop prototype-pollution keys (__proto__/constructor/prototype),
// bound depth + string length, and reject functions/symbols/other live objects.
// The result is therefore inert data — it can never be a code/object payload.
function containValue(v, depth = 0) {
  if (depth > 64) return '[TRUNCATED_DEPTH]'
  const t = typeof v
  if (v === null || t === 'boolean' || t === 'number') return v
  if (t === 'string') return v.length > 200000 ? v.slice(0, 200000) + '…[TRUNCATED]' : v
  if (Array.isArray(v)) return v.slice(0, 10000).map(x => containValue(x, depth + 1))
  if (t === 'object') {
    const out = {}
    for (const [k, val] of Object.entries(v)) {
      if (k === '__proto__' || k === 'constructor' || k === 'prototype') continue
      out[String(k).slice(0, 200)] = containValue(val, depth + 1)
    }
    return out
  }
  return undefined // functions, symbols, bigint, undefined → dropped entirely
}

// Inbound results from a worker are UNTRUSTED (CLAUDE.md #1/#10: agent outputs are
// hostile). Containment pipeline: size-cap → structural contain (anti-malware) →
// secret+PII redact. The returned value is inert data, never code, and is tagged
// so downstream code can never silently trust or execute it.
function scanResult(result) {
  try {
    const cfg = loadPolicy()
    const bytes = payloadBytes(result)
    if (bytes > Number(cfg.caps.max_result_bytes)) {
      return { ok: false, result: null, reason: `result ${bytes}B exceeds cap ${cfg.caps.max_result_bytes}B` }
    }
    const had_secret = containsSecret(result)
    const contained = containValue(result)
    const safe = redact(contained)
    return { ok: true, result: safe, had_secret, _untrusted: true }
  } catch (_) { return { ok: false, result: null, reason: 'result scan error (fail-closed)' } }
}

module.exports = {
  loadPolicy, classify, redact, redactPIIString, guard, isEndpointAllowed,
  scanResult, containValue, containsSecret, payloadBytes, _resetPolicy,
}
