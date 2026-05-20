'use strict'
/**
 * /api/research/* — Research v2 proxy to Python FastAPI on port 18790.
 *   POST /api/research/discover  → returns candidate sources (no fetch)
 *   POST /api/research/execute   → kicks off backgrounded fetch + summarize on selected URLs
 */
const http    = require('http')
const express = require('express')

const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790
const TIMEOUT_MS  = 30000

function proxy(path, req, res) {
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
  proxyReq.on('error',   e => res.status(503).json({ error: `Research backend unavailable: ${e.message}` }))
  proxyReq.on('timeout', () => { proxyReq.destroy(); res.status(504).json({ error: 'Research backend timed out' }) })
  proxyReq.write(body); proxyReq.end()
}

module.exports = function createResearchRouter(requireAuth) {
  const router = express.Router()

  router.post('/discover', requireAuth, (req, res) => {
    if (!(req.body?.query || '').trim()) return res.status(400).json({ error: 'query required' })
    proxy('/api/research/discover', req, res)
  })

  router.post('/execute', requireAuth, (req, res) => {
    const { query = '', selected_source_ids = [], selected_urls = [] } = req.body || {}
    if (!query.trim() || (!selected_source_ids.length && !selected_urls.length)) {
      return res.status(400).json({ error: 'query and selected_source_ids (or selected_urls) required' })
    }
    proxy('/api/research/execute', req, res)
  })

  return router
}
