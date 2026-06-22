'use strict'

/**
 * Result verifier (B1) — turns "done" from a structural claim into a PROVEN one.
 *
 * Two modes, one entry point:
 *   - code  : run the project's verification commands in a sandbox (runner is
 *             dependency-injected so this module stays pure/testable and the caller
 *             supplies the existing allowlisted sandbox runner). passed = all green.
 *   - text  : score a research/summary/plan output against quality criteria
 *             (non-empty, length, addresses the topic, cites sources). passed =
 *             score >= threshold.
 *
 * Returns a structured verdict — never throws — so it can gate a run's completion
 * without ever silently passing.
 */

const _URL_RE = /\bhttps?:\/\/[^\s)]+/i
const _CITATION_RE = /\[[0-9]+\]|\bsource[s]?:|\breference[s]?:|\baccording to\b/i
const _STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'in', 'on', 'with', 'about', 'is', 'are', 'be', 'how', 'what', 'why', 'write', 'summary', 'research', 'create', 'make', 'give', 'me'])

function _topicTokens(topic) {
  return String(topic || '')
    .toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/)
    .filter(w => w.length >= 4 && !_STOP.has(w))
}

// Score a text output (research/summary/plan/etc.) against quality criteria.
function verifyText(output, opts = {}) {
  const text = String(output || '')
  const minLen = opts.minLen != null ? opts.minLen : 200
  const requireSources = opts.requireSources !== false // default true for research
  const topicTokens = _topicTokens(opts.topic)

  const checks = []
  // `hard` checks must ALL pass for an overall pass, regardless of the averaged score.
  const add = (name, pass, { hard = false, detail = '' } = {}) => checks.push({ name, pass: !!pass, hard, detail })

  add('non_empty', text.trim().length > 0, { hard: true })
  add('min_length', text.length >= minLen, { detail: `${text.length}/${minLen} chars` })

  const lower = text.toLowerCase()
  const hits = topicTokens.filter(t => lower.includes(t))
  const coverage = topicTokens.length ? hits.length / topicTokens.length : 1
  add('addresses_topic', topicTokens.length === 0 || coverage >= 0.5, { detail: `${hits.length}/${topicTokens.length} topic terms` })

  const hasSources = _URL_RE.test(text) || _CITATION_RE.test(text)
  if (requireSources) add('has_sources', hasSources, { hard: true, detail: hasSources ? 'url/citation found' : 'no url/citation' })

  const passedChecks = checks.filter(c => c.pass).length
  const score = checks.length ? passedChecks / checks.length : 0
  const threshold = opts.threshold != null ? opts.threshold : 0.75
  const hardOk = checks.filter(c => c.hard).every(c => c.pass)
  return { type: 'text', passed: hardOk && score >= threshold, score: Number(score.toFixed(3)), threshold, checks }
}

// Run code verification commands via an injected async runner.
// runner(cmd) -> { pass: boolean, output?: string }   (e.g. the forge sandbox runner)
async function verifyCode({ commands = [], runner } = {}) {
  if (typeof runner !== 'function') {
    return { type: 'code', passed: false, score: 0, reason: 'no runner provided', results: [] }
  }
  if (!Array.isArray(commands) || commands.length === 0) {
    // No tests to run is NOT a pass — it's "unverified", never a silent success.
    return { type: 'code', passed: false, score: 0, reason: 'no_verification_commands', results: [] }
  }
  const results = []
  for (const cmd of commands.slice(0, 10)) {
    // eslint-disable-next-line no-await-in-loop
    let r
    try { r = await runner(cmd) } catch (e) { r = { pass: false, output: String(e && e.message || e) } }
    results.push({ command: cmd, pass: !!(r && r.pass), output: String((r && r.output) || '').slice(0, 800) })
  }
  const passedCount = results.filter(r => r.pass).length
  const passed = passedCount === results.length
  return { type: 'code', passed, score: results.length ? Number((passedCount / results.length).toFixed(3)) : 0, results }
}

async function verify(spec = {}) {
  const type = spec.type || 'text'
  if (type === 'code') return verifyCode(spec)
  return verifyText(spec.output, spec)
}

module.exports = { verify, verifyText, verifyCode }
