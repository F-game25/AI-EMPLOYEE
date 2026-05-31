'use strict'
/**
 * /api/search — proxy to Python FastAPI POST /search
 * Supports: web search with optional CloakBrowser visual fetching.
 */
const http    = require('http')
const express = require('express')

const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790
const TIMEOUT_MS  = 30000

module.exports = function createSearchRouter(requireAuth) {
  const router = express.Router()

  router.post('/', requireAuth, (req, res) => {
    const { query = '', sources = ['WEB'], max_results = 8, include_screenshot = false } = req.body || {}

    if (!query.trim()) {
      return res.status(400).json({ error: 'query is required' })
    }

    const body = JSON.stringify({ query, sources, max_results, include_screenshot })

    const proxyReq = http.request(
      `http://${PYTHON_HOST}:${PYTHON_PORT}/search`,
      {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
        timeout: TIMEOUT_MS,
      },
      (proxyRes) => {
        let data = ''
        proxyRes.on('data', (chunk) => { data += chunk })
        proxyRes.on('end', () => {
          try {
            const parsed = JSON.parse(data || '{}')
            res.status(proxyRes.statusCode || 200).json(parsed)
          } catch {
            res.status(502).json({ error: 'invalid response from search backend', raw: data.slice(0, 200) })
          }
        })
      }
    )

    proxyReq.on('error', (err) => {
      res.status(503).json({ error: `Search backend unavailable: ${err.message}`, results: [], total: 0 })
    })
    proxyReq.on('timeout', () => {
      proxyReq.destroy()
      res.status(504).json({ error: 'Search backend timed out', results: [], total: 0 })
    })

    proxyReq.write(body)
    proxyReq.end()
  })

  return router
}
