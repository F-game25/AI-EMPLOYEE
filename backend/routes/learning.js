'use strict'
/**
 * /api/learning/* — Wizard learning session proxy + review queue.
 *   POST /execute                  start learning session (fire-and-forget to Python)
 *   GET  /sessions/:id             poll session status from Python
 *   GET  /pending-review           list pending review queue
 *   POST /pending-review/:id/approve  approve claim
 *   POST /pending-review/:id/reject   reject claim
 */
const express = require('express')
const fs      = require('fs')
const http    = require('http')
const path    = require('path')
const crypto  = require('crypto')

const REVIEW_FILE = path.join(process.env.HOME, '.ai-employee', 'state', 'pending_review_queue.json')
const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = 18790
const TIMEOUT_MS  = 5000

// ── helpers ──────────────────────────────────────────────────────────────────

async function readReview() {
  try {
    return JSON.parse(await fs.promises.readFile(REVIEW_FILE, 'utf8'))
  } catch {
    return { entries: [] }
  }
}

async function writeReview(data) {
  await fs.promises.mkdir(path.dirname(REVIEW_FILE), { recursive: true })
  await fs.promises.writeFile(REVIEW_FILE, JSON.stringify(data, null, 2), 'utf8')
}

function pyRequest(method, urlPath, body, timeoutMs = TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : null
    const headers = { 'Content-Type': 'application/json' }
    if (payload) headers['Content-Length'] = Buffer.byteLength(payload)
    const req = http.request(
      { host: PYTHON_HOST, port: PYTHON_PORT, path: urlPath, method, headers },
      res => {
        let chunks = ''
        res.on('data', d => { chunks += d })
        res.on('end', () => resolve({ status: res.statusCode, body: chunks }))
      }
    )
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error('timeout')) })
    req.on('error', reject)
    if (payload) req.write(payload)
    req.end()
  })
}

// ── router factory ────────────────────────────────────────────────────────────

module.exports = (requireAuth) => {
  const router = express.Router()

  // POST /execute — start wizard learning session
  router.post('/execute', requireAuth, async (req, res) => {
    try {
      const {
        topic,
        depth = 'normal',
        source_prefs = [],
        verification_level = 'normal'
      } = req.body || {}
      if (!topic) return res.status(400).json({ error: 'topic required' })
      const session_id = crypto.randomUUID()
      // fire-and-forget to Python
      pyRequest('POST', '/api/learning/execute', { session_id, topic, depth, source_prefs, verification_level }).catch(() => {})
      res.status(202).json({ session_id, status: 'started', topic })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // GET /sessions/:id — poll session status
  router.get('/sessions/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params
      let result
      try {
        result = await pyRequest('GET', `/api/learning/sessions/${id}`)
      } catch {
        return res.json({ session_id: id, status: 'unknown' })
      }
      if (result.status === 404 || result.status >= 500) {
        return res.json({ session_id: id, status: 'unknown' })
      }
      try {
        res.json(JSON.parse(result.body))
      } catch {
        res.json({ session_id: id, status: 'unknown' })
      }
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // GET /pending-review — list review queue
  router.get('/pending-review', requireAuth, async (_req, res) => {
    try {
      res.json(await readReview())
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // POST /pending-review/:id/approve — approve claim
  router.post('/pending-review/:id/approve', requireAuth, async (req, res) => {
    try {
      const { id } = req.params
      const state = await readReview()
      state.entries = (state.entries || []).filter(e => e.id !== id)
      await writeReview(state)
      // fire-and-forget to Python memory approve
      pyRequest('POST', '/api/memory/approve', { claim_id: id }).catch(() => {})
      res.json({ approved: true })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // POST /pending-review/:id/reject — reject claim
  router.post('/pending-review/:id/reject', requireAuth, async (req, res) => {
    try {
      const { id } = req.params
      const state = await readReview()
      state.entries = (state.entries || []).filter(e => e.id !== id)
      await writeReview(state)
      res.json({ rejected: true })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  return router
}
