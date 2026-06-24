'use strict'

/**
 * C4 — Memory closed-loop: provenance-trust gate for the forge codegen path.
 *
 * Ranked memories are pulled by forge_context_engine and would otherwise flow
 * straight into the codegen prompt. CLAUDE.md rule #2 + #18: a memory is
 * UNTRUSTED DATA, never command authority — a poisoned/stale memory must not
 * become an instruction. This gate is the retrieval-side guard:
 *
 *   scoreFact(fact)  → trust in [0,1] from confidence + corroboration + provenance
 *   gateMemories(...) → drop anything below min_trust OR carrying injection
 *                       patterns, rank desc, cap at max_injected
 *   formatForPrompt() → compact, labeled lines (caller still fences via
 *                       prompt_guard.wrapUntrusted before the prompt)
 *
 * Hard rules: pure, config-driven (runtime/config/memory_trust.json with
 * baked-in defaults), never throws into the codegen path, fail-closed
 * (on any doubt a memory is dropped, not injected). Kill-switch:
 * FORGE_MEMORY_INJECTION=0 disables injection entirely.
 */

const fs = require('fs')
const path = require('path')
const promptGuard = require('./prompt_guard')

const DEFAULTS = {
  min_trust: 0.40,
  max_injected: 6,
  weights: { confidence: 0.45, corroboration: 0.30, provenance: 0.25 },
  confidence_rank: { low: 0.2, medium: 0.6, high: 1.0 },
  corroboration: { saturation_uses: 8 },
  provenance: {
    has_source_run: 1.0,
    trusted_sources: ['run', 'verified', 'test_pass', 'memory_service', 'lesson', 'user'],
    trusted_source_credit: 0.8,
    unknown_source_credit: 0.25,
  },
}

const CONFIG_PATH = path.join(__dirname, '..', '..', 'runtime', 'config', 'memory_trust.json')

let _cfg = null
function loadConfig() {
  if (_cfg) return _cfg
  let fileCfg = {}
  try { fileCfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')) } catch (_) { fileCfg = {} }
  // Shallow-merge top level, deep-merge the nested objects we depend on.
  _cfg = {
    ...DEFAULTS,
    ...fileCfg,
    weights: { ...DEFAULTS.weights, ...(fileCfg.weights || {}) },
    confidence_rank: { ...DEFAULTS.confidence_rank, ...(fileCfg.confidence_rank || {}) },
    corroboration: { ...DEFAULTS.corroboration, ...(fileCfg.corroboration || {}) },
    provenance: { ...DEFAULTS.provenance, ...(fileCfg.provenance || {}) },
  }
  return _cfg
}

// Test seam — drop the cached config so a changed file/env is re-read.
function _resetConfig() { _cfg = null }

const clamp01 = (n) => (Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0)

// Memories arrive as forge_memory_v3 rows: { fact, category, confidence:'low|medium|high'
// (or numeric), usage_count, source_run_id, evidence, ... }. Be defensive about every field.
function confidenceScore(fact, cfg) {
  const c = fact && fact.confidence
  if (typeof c === 'number') return clamp01(c)
  const key = String(c || 'low').toLowerCase()
  return clamp01(cfg.confidence_rank[key] != null ? cfg.confidence_rank[key] : cfg.confidence_rank.low)
}

function corroborationScore(fact, cfg) {
  const uses = Math.max(0, Number(fact && fact.usage_count) || 0)
  const sat = Math.max(1, Number(cfg.corroboration.saturation_uses) || 8)
  if (uses <= 0) return 0
  // log-scaled so a couple of reuses earn most of the credit, diminishing after.
  return clamp01(Math.log1p(uses) / Math.log1p(sat))
}

function provenanceScore(fact, cfg) {
  const p = cfg.provenance
  if (fact && fact.source_run_id) return clamp01(p.has_source_run)
  const src = String((fact && (fact.source || fact.category)) || '').toLowerCase()
  const trusted = (p.trusted_sources || []).some(t => src.includes(String(t).toLowerCase()))
  return clamp01(trusted ? p.trusted_source_credit : p.unknown_source_credit)
}

// Trust in [0,1]. Memories whose text trips an injection pattern are hard-zeroed
// (fail-closed) regardless of their other signals.
function scoreFact(fact, cfg = loadConfig()) {
  if (!fact || typeof fact !== 'object') return 0
  const text = `${fact.fact || ''} ${fact.evidence || ''}`
  if (promptGuard.detect(text)) return 0
  const w = cfg.weights
  const wSum = (Number(w.confidence) || 0) + (Number(w.corroboration) || 0) + (Number(w.provenance) || 0) || 1
  const raw =
    (Number(w.confidence) || 0) * confidenceScore(fact, cfg) +
    (Number(w.corroboration) || 0) * corroborationScore(fact, cfg) +
    (Number(w.provenance) || 0) * provenanceScore(fact, cfg)
  return clamp01(raw / wSum)
}

function injectionEnabled() {
  return process.env.FORGE_MEMORY_INJECTION !== '0'
}

/**
 * Filter → rank → cap. Returns { kept, stats } and NEVER throws.
 * kept entries carry a `_trust` field for telemetry/inspection.
 */
function gateMemories(facts, opts = {}) {
  try {
    if (!injectionEnabled()) {
      return { kept: [], stats: { in: Array.isArray(facts) ? facts.length : 0, kept: 0, dropped_low_trust: 0, dropped_injection: 0, disabled: true } }
    }
    const cfg = loadConfig()
    const list = Array.isArray(facts) ? facts : []
    const minTrust = Number(opts.minTrust != null ? opts.minTrust : cfg.min_trust)
    const limit = Math.max(0, Number(opts.limit != null ? opts.limit : cfg.max_injected) || 0)
    let droppedInjection = 0
    let droppedLowTrust = 0
    const scored = []
    for (const f of list) {
      const text = `${(f && f.fact) || ''} ${(f && f.evidence) || ''}`
      if (f && promptGuard.detect(text)) { droppedInjection++; continue }
      const t = scoreFact(f, cfg)
      if (t < minTrust) { droppedLowTrust++; continue }
      scored.push({ ...f, _trust: Number(t.toFixed(3)) })
    }
    scored.sort((a, b) => b._trust - a._trust)
    const kept = scored.slice(0, limit)
    return {
      kept,
      stats: { in: list.length, kept: kept.length, dropped_low_trust: droppedLowTrust, dropped_injection: droppedInjection, min_trust: minTrust },
    }
  } catch (_) {
    // Fail-closed: on any error, inject nothing rather than risk ungated memories.
    return { kept: [], stats: { in: Array.isArray(facts) ? facts.length : 0, kept: 0, dropped_low_trust: 0, dropped_injection: 0, error: true } }
  }
}

// Compact one-line-per-memory rendering. The caller wraps the whole block with
// prompt_guard.wrapUntrusted(...) so it is fenced + sanitized before the prompt.
function formatForPrompt(kept) {
  try {
    const list = Array.isArray(kept) ? kept : []
    if (!list.length) return ''
    return list
      .map((f) => {
        const cat = f.category ? `[${f.category}] ` : ''
        const trust = f._trust != null ? ` (trust ${f._trust})` : ''
        return `- ${cat}${String(f.fact || '').slice(0, 280)}${trust}`
      })
      .join('\n')
  } catch (_) { return '' }
}

module.exports = {
  loadConfig,
  scoreFact,
  gateMemories,
  formatForPrompt,
  injectionEnabled,
  _resetConfig,
}
