'use strict'
/**
 * /api/research/* — Research v2 proxy to Python FastAPI on port 18790.
 *   POST /api/research/discover  → returns candidate sources (no fetch)
 *   POST /api/research/execute   → kicks off backgrounded fetch + summarize on selected URLs
 *
 * Falls back to clearly-labelled mock data when Python backend is unavailable.
 */
const http    = require('http')
const crypto  = require('crypto')
const express = require('express')

const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790
const TIMEOUT_MS  = 30000

// ── Proxy with fallback ───────────────────────────────────────────────────────
function proxy(path, req, res, fallback) {
  const body = JSON.stringify(req.body || {})
  const proxyReq = http.request(
    `http://${PYTHON_HOST}:${PYTHON_PORT}${path}`,
    {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: TIMEOUT_MS,
    },
    (pr) => {
      let data = ''
      pr.on('data', c => { data += c })
      pr.on('end', () => {
        try {
          res.status(pr.statusCode || 200).json(JSON.parse(data || '{}'))
        } catch {
          res.status(502).json({ error: 'invalid response from research backend', raw: data.slice(0, 200) })
        }
      })
    }
  )
  proxyReq.on('error',   () => fallback(res))
  proxyReq.on('timeout', () => { proxyReq.destroy(); fallback(res) })
  proxyReq.write(body); proxyReq.end()
}

// ── Method/auth-preserving proxy (for the Deep Research sub-API) ──────────────
// The POST-only proxy() above can't carry the deep endpoints, which use GET (list/
// poll), POST (start/commit) and DELETE, and require auth on the Python side. This
// forwards method + full path + body + the caller's Authorization header verbatim.
function proxyDeep(req, res) {
  const isWrite = !['GET', 'HEAD', 'DELETE'].includes(req.method)
  const body = isWrite ? JSON.stringify(req.body || {}) : null
  const headers = { 'Content-Type': 'application/json' }
  if (body) headers['Content-Length'] = Buffer.byteLength(body)
  if (req.headers.authorization) headers['Authorization'] = req.headers.authorization
  const proxyReq = http.request(
    `http://${PYTHON_HOST}:${PYTHON_PORT}${req.originalUrl}`,
    { method: req.method, headers, timeout: TIMEOUT_MS },
    (pr) => {
      let data = ''
      pr.on('data', c => { data += c })
      pr.on('end', () => {
        try { res.status(pr.statusCode || 200).json(JSON.parse(data || '{}')) }
        catch { res.status(502).json({ ok: false, error: 'invalid response from research backend', raw: data.slice(0, 200) }) }
      })
    }
  )
  proxyReq.on('error',   () => res.status(503).json({ ok: false, error: 'Deep research backend offline' }))
  proxyReq.on('timeout', () => { proxyReq.destroy(); res.status(504).json({ ok: false, error: 'Deep research backend timeout' }) })
  if (body) proxyReq.write(body)
  proxyReq.end()
}

// ── Mock fallbacks (clearly labelled, no real data) ───────────────────────────
function mockDiscover(query, limit) {
  const domains = ['example.com', 'docs.example.org', 'news.example.net', 'forum.example.io', 'scholar.example.edu']
  const types   = ['web', 'docs', 'news', 'forum', 'academic']
  const sources = Array.from({ length: Math.min(limit, 5) }, (_, i) => ({
    id:          crypto.createHash('md5').update(`${query}-${i}`).digest('hex').slice(0, 12),
    url:         `https://${domains[i]}/mock-result-${i + 1}`,
    title:       `[MOCK] Result ${i + 1} for "${query}"`,
    snippet:     `[MOCK DATA — Python backend offline] Placeholder result ${i + 1} matching "${query}".`,
    domain:      domains[i],
    trust_score: parseFloat((0.5 + i * 0.08).toFixed(2)),
    source_type: types[i],
  }))
  return { ok: true, query, sources, mock: true }
}

function mockExecute(query, sources, session_id) {
  const sid = session_id || crypto.randomBytes(6).toString('hex')
  return {
    ok: true,
    session_id: sid,
    status: 'completed',
    mock: true,
    results: (sources || []).map(url => ({
      source:  url,
      summary: `[MOCK DATA — Python backend offline] No summary available for "${url}" while research backend is down.`,
      tokens:  0,
    })),
  }
}

// ── Rate limiting ─────────────────────────────────────────────────────────────
function makeRateLimit(max, windowMs = 60_000) {
  const buckets = new Map()
  return (req, res, next) => {
    const ip  = req.ip || req.connection?.remoteAddress || 'unknown'
    const now = Date.now()
    const hits = (buckets.get(ip) || []).filter(t => now - t < windowMs)
    hits.push(now)
    buckets.set(ip, hits)
    if (hits.length > max) {
      res.set('Retry-After', Math.ceil(windowMs / 1000))
      return res.status(429).json({ ok: false, error: 'Rate limit exceeded' })
    }
    next()
  }
}
const _rl_discover = makeRateLimit(60)  // 60/min per IP — enough for interactive use
const _rl_execute  = makeRateLimit(30)  // 30/min per IP — execute is heavier so slightly lower

// ── Router ────────────────────────────────────────────────────────────────────
module.exports = function createResearchRouter(requireAuth) {
  const router = express.Router()

  router.post('/discover', requireAuth, _rl_discover, (req, res) => {
    const query = (req.body?.query || '').trim()
    if (!query) return res.status(400).json({ error: 'query required' })
    if (query.length > 500) return res.status(400).json({ error: 'query too long (max 500 chars)' })
    const limitRaw = parseInt(req.body?.limit || req.body?.max_sources || 10, 10)
    const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(limitRaw, 1), 50) : 10
    proxy(
      '/api/research/discover',
      req, res,
      () => res.json(mockDiscover(query, limit))
    )
  })

  router.post('/execute', requireAuth, _rl_execute, (req, res) => {
    const { query = '', selected_source_ids = [], selected_urls = [], session_id } = req.body || {}
    if (!query.trim() || (!selected_source_ids.length && !selected_urls.length)) {
      return res.status(400).json({ error: 'query and selected_source_ids (or selected_urls) required' })
    }
    proxy(
      '/api/research/execute',
      req, res,
      () => res.json(mockExecute(query, selected_urls, session_id))
    )
  })

  // Deep Research sub-API — was unreachable (no proxy) so DeepResearchPage 404'd.
  // GET /deep (list) · POST /deep/start · GET|DELETE /deep/:id · POST /deep/:id/commit
  router.all('/deep', requireAuth, proxyDeep)
  router.all('/deep/*', requireAuth, proxyDeep)

  return router
}
