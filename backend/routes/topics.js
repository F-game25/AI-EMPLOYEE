'use strict'
/**
 * /api/topics/* — Topic intelligence CRUD + research triggers.
 *   GET    /              list all topics
 *   POST   /              create topic
 *   GET    /:id           topic detail
 *   PUT    /:id           update metadata
 *   DELETE /:id           soft-delete topic
 *   POST   /:id/pin       toggle pinned
 *   POST   /:id/refresh   fire-and-forget research run (202)
 */
const express = require('express')
const fs      = require('fs')
const http    = require('http')
const path    = require('path')

const STATE_FILE = path.join(process.env.HOME, '.ai-employee', 'state', 'topic_intelligence.json')
const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = 18790

// ── helpers ──────────────────────────────────────────────────────────────────

async function readState() {
  try {
    const raw = await fs.promises.readFile(STATE_FILE, 'utf8')
    return JSON.parse(raw)
  } catch {
    return { topics: [] }
  }
}

async function writeState(data) {
  await fs.promises.mkdir(path.dirname(STATE_FILE), { recursive: true })
  await fs.promises.writeFile(STATE_FILE, JSON.stringify(data, null, 2), 'utf8')
}

function slug(title) {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function uniqueId(topics, base) {
  let id = base
  let n = 1
  while (topics.some(t => t.id === id)) id = `${base}-${n++}`
  return id
}

function pyPost(path_, body, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body)
    const req = http.request(
      { host: PYTHON_HOST, port: PYTHON_PORT, path: path_, method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } },
      res => { res.resume(); resolve(res.statusCode) }
    )
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error('timeout')) })
    req.on('error', reject)
    req.write(payload)
    req.end()
  })
}

// ── router factory ────────────────────────────────────────────────────────────

module.exports = (requireAuth) => {
  const router = express.Router()

  // GET / — list all topics
  router.get('/', requireAuth, async (_req, res) => {
    try {
      const { topics } = await readState()
      res.json({ topics: topics.filter(t => !t._deleted) })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // POST / — create topic
  router.post('/', requireAuth, async (req, res) => {
    try {
      const { title, description = '', tags = [], schedule = 'manual' } = req.body || {}
      if (!title) return res.status(400).json({ error: 'title required' })
      const state = await readState()
      const id = uniqueId(state.topics, slug(title))
      const topic = {
        id, title, description, tags,
        pinned: false, schedule,
        skill_level: 0.0, memory_count: 0, source_count: 0,
        last_updated: null, sub_topics: [], open_questions: []
      }
      state.topics.push(topic)
      await writeState(state)
      res.status(201).json({ topic })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // GET /:id — topic detail
  router.get('/:id', requireAuth, async (req, res) => {
    try {
      const { topics } = await readState()
      const topic = topics.find(t => t.id === req.params.id && !t._deleted)
      if (!topic) return res.status(404).json({ error: 'not found' })
      res.json({ topic })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // PUT /:id — update metadata
  router.put('/:id', requireAuth, async (req, res) => {
    try {
      const state = await readState()
      const idx = state.topics.findIndex(t => t.id === req.params.id && !t._deleted)
      if (idx === -1) return res.status(404).json({ error: 'not found' })
      const allowed = ['title','description','tags','schedule','skill_level','sub_topics','open_questions']
      for (const k of allowed) {
        if (req.body && k in req.body) state.topics[idx][k] = req.body[k]
      }
      state.topics[idx].last_updated = new Date().toISOString()
      await writeState(state)
      res.json({ topic: state.topics[idx] })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // DELETE /:id — soft-delete
  router.delete('/:id', requireAuth, async (req, res) => {
    try {
      const state = await readState()
      const idx = state.topics.findIndex(t => t.id === req.params.id)
      if (idx === -1) return res.status(404).json({ error: 'not found' })
      state.topics[idx]._deleted = true
      await writeState(state)
      res.json({ deleted: true })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // POST /:id/pin — toggle pinned
  router.post('/:id/pin', requireAuth, async (req, res) => {
    try {
      const state = await readState()
      const idx = state.topics.findIndex(t => t.id === req.params.id && !t._deleted)
      if (idx === -1) return res.status(404).json({ error: 'not found' })
      state.topics[idx].pinned = !state.topics[idx].pinned
      await writeState(state)
      res.json({ pinned: state.topics[idx].pinned })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  // POST /:id/refresh — trigger research run (fire-and-forget, 202)
  router.post('/:id/refresh', requireAuth, async (req, res) => {
    try {
      const { topics } = await readState()
      const topic = topics.find(t => t.id === req.params.id && !t._deleted)
      if (!topic) return res.status(404).json({ error: 'not found' })
      // fire-and-forget; ignore errors from Python backend
      pyPost('/api/research/discover', { topic_id: topic.id, title: topic.title, tags: topic.tags }).catch(() => {})
      res.status(202).json({ status: 'research_triggered', topic_id: topic.id })
    } catch (err) {
      res.status(500).json({ error: err.message })
    }
  })

  return router
}
