'use strict'

/**
 * Per-day token-budget guard for Forge LLM calls (Node codegen path).
 *
 * Complements (does NOT duplicate) runtime/core/cost_ledger.py — that is the
 * per-tenant USD ledger for the Python engine path. This guards the Node Forge
 * codegen path, which never went through any budget before.
 *
 * Safe default: FORGE_LLM_DAILY_TOKEN_BUDGET=0 → unlimited (track-only). Usage is
 * always recorded for observability; enforcement only kicks in when a budget > 0
 * is configured, so it never silently blocks free local calls out of the box.
 *
 * Persisted as JSON under state/forge/. Pure/standalone — unit-testable.
 */
const fs = require('fs')
const path = require('path')
const os = require('os')

function _defaultPath() {
  const home = process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
  return path.join(home, 'state', 'forge', 'llm_budget.json')
}

function _dayKey(d = new Date()) { return d.toISOString().slice(0, 10) }

// ~4 characters per token — a deliberately simple, provider-agnostic estimate.
function estimateTokens(text) { return Math.ceil(String(text || '').length / 4) }

class TokenBudgetManager {
  constructor(opts = {}) {
    this.filePath = opts.filePath || _defaultPath()
    this.dailyBudget = opts.dailyBudget != null
      ? opts.dailyBudget
      : (parseInt(process.env.FORGE_LLM_DAILY_TOKEN_BUDGET, 10) || 0) // 0 = unlimited / track-only
    this._data = this._load()
  }

  _load() {
    try {
      const d = JSON.parse(fs.readFileSync(this.filePath, 'utf8'))
      return d && typeof d === 'object' && !Array.isArray(d) ? d : {}
    } catch { return {} }
  }

  _save() {
    try {
      fs.mkdirSync(path.dirname(this.filePath), { recursive: true })
      fs.writeFileSync(this.filePath, JSON.stringify(this._data))
    } catch { /* best-effort */ }
  }

  _today() {
    const k = _dayKey()
    if (!this._data[k]) this._data[k] = { tokens: 0, calls: 0, cache_hits: 0 }
    return this._data[k]
  }

  // Returns { allowed, reason, remaining, used, budget }.
  check(estTokens = 0) {
    if (!this.dailyBudget || this.dailyBudget <= 0) {
      return { allowed: true, reason: 'unlimited', remaining: Infinity, used: this._today().tokens, budget: 0 }
    }
    const used = this._today().tokens
    const remaining = Math.max(0, this.dailyBudget - used)
    if (used + estTokens > this.dailyBudget) {
      return { allowed: false, reason: 'daily_token_budget_exceeded', remaining, used, budget: this.dailyBudget }
    }
    return { allowed: true, reason: 'ok', remaining, used, budget: this.dailyBudget }
  }

  record(tokens = 0, meta = {}) {
    const t = this._today()
    t.tokens += Math.max(0, Math.round(tokens))
    t.calls += 1
    if (meta.cache_hit) t.cache_hits += 1
    this._save()
    return t
  }

  recordCacheHit() {
    const t = this._today()
    t.cache_hits += 1
    this._save()
    return t
  }

  summary() {
    const t = this._today()
    return {
      date: _dayKey(),
      daily_budget: this.dailyBudget > 0 ? this.dailyBudget : 'unlimited',
      used_tokens: t.tokens,
      calls: t.calls,
      cache_hits: t.cache_hits,
      remaining: this.dailyBudget > 0 ? Math.max(0, this.dailyBudget - t.tokens) : 'unlimited',
    }
  }
}

let _inst = null
function getTokenBudget() { return _inst || (_inst = new TokenBudgetManager()) }

module.exports = { TokenBudgetManager, getTokenBudget, estimateTokens }
