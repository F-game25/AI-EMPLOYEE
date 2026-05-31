'use strict'
/**
 * /api/vault/* — Obsidian-compatible markdown vault.
 *   GET    /notes              list .md files (parsed frontmatter, fast Node read)
 *   GET    /notes/:id          read one note + frontmatter
 *   PUT    /notes/:id          proxy to Python (re-indexes backlinks)
 *   POST   /notes              proxy to Python
 *   DELETE /notes/:id          proxy to Python (soft-delete to _trash/)
 *   GET    /search?q=...       grep-style full-text search
 *   GET    /graph              {nodes, links} from _backlinks.json
 *   GET    /broken-links       list of (source_id, broken_target)
 *   POST   /rebuild-indices    proxy to Python
 */
const express = require('express')
const fs      = require('fs')
const http    = require('http')
const os      = require('os')
const path    = require('path')
const { createRouteRateLimit } = require('../middleware/route-rate-limit')

const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790
const TIMEOUT_MS  = 30000
const FOLDERS     = ['concepts', 'people', 'projects', 'topics', 'daily']

// Per-tenant vault path (2026-05-18 security audit CRITICAL #2):
// Resolves the vault root for the request's tenant. Falls back to 'default'
// when called without auth context (legacy/admin paths).
function vaultRootForRequest(req) {
  const tenantId = req?.jwtPayload?.tenant_id || req?.tenant_id || 'default'
  // Defense-in-depth: never trust a tenant_id that has path-traversal chars
  const safe = String(tenantId).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 64) || 'default'
  return path.join(os.homedir(), '.ai-employee', 'tenants', safe, 'vault')
}

// --- minimal YAML frontmatter parser (no deps) ---------------------------
// Handles: key: value, key: [a, b, c], nested only one level (we only need flat).
function parseFrontmatter(raw) {
  if (!raw.startsWith('---')) return { meta: {}, body: raw }
  const end = raw.indexOf('\n---', 3)
  if (end < 0) return { meta: {}, body: raw }
  const fm   = raw.slice(3, end).replace(/^\r?\n/, '')
  const body = raw.slice(end + 4).replace(/^\r?\n/, '')
  const meta = {}
  let currentKey = null
  for (const line of fm.split(/\r?\n/)) {
    if (!line.trim()) { currentKey = null; continue }
    // list item under previous key
    const li = line.match(/^\s*-\s+(.*)$/)
    if (li && currentKey) {
      if (!Array.isArray(meta[currentKey])) meta[currentKey] = []
      meta[currentKey].push(coerceScalar(li[1].trim()))
      continue
    }
    const kv = line.match(/^([A-Za-z0-9_\-]+)\s*:\s*(.*)$/)
    if (!kv) continue
    const k = kv[1]
    const v = kv[2].trim()
    if (v === '' || v === '[]') { meta[k] = []; currentKey = k; continue }
    if (v.startsWith('[') && v.endsWith(']')) {
      meta[k] = v.slice(1, -1).split(',').map(s => coerceScalar(s.trim())).filter(x => x !== '')
      currentKey = null
      continue
    }
    meta[k] = coerceScalar(v)
    currentKey = k
  }
  return { meta, body }
}
function coerceScalar(s) {
  if (s === 'true')  return true
  if (s === 'false') return false
  if (s === 'null' || s === '~') return null
  if (/^-?\d+$/.test(s))            return parseInt(s, 10)
  if (/^-?\d*\.\d+$/.test(s))       return parseFloat(s)
  return s.replace(/^["'](.*)["']$/, '$1')
}

// --- helpers --------------------------------------------------------------
function listMdFiles(rootDir) {
  const out = []
  function walk(dir) {
    let entries
    try { entries = fs.readdirSync(dir, { withFileTypes: true }) }
    catch { return }
    for (const e of entries) {
      if (e.name.startsWith('.') || e.name === '_trash') continue
      const full = path.join(dir, e.name)
      if (e.isDirectory()) walk(full)
      else if (e.isFile() && e.name.endsWith('.md')) out.push(full)
    }
  }
  walk(rootDir)
  return out
}
function relFolder(filePath, vaultRoot) {
  const rel = path.relative(vaultRoot, filePath)
  const parts = rel.split(path.sep)
  return parts.length > 1 ? parts[0] : ''
}
function safeReadJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')) } catch { return fallback }
}

// --- proxy to Python FastAPI ----------------------------------------------
function proxyToPython(method, urlPath, req, res) {
  const body = JSON.stringify(req.body || {})
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    timeout: TIMEOUT_MS,
  }
  const pr = http.request(`http://${PYTHON_HOST}:${PYTHON_PORT}${urlPath}`, opts, (pres) => {
    let data = ''
    pres.on('data', c => { data += c })
    pres.on('end', () => {
      try { res.status(pres.statusCode || 200).json(JSON.parse(data || '{}')) }
      catch { res.status(502).json({ error: 'invalid response from vault backend', raw: data.slice(0, 200) }) }
    })
  })
  pr.on('error',   e => res.status(503).json({ error: `Vault backend unavailable: ${e.message}` }))
  pr.on('timeout', () => { pr.destroy(); res.status(504).json({ error: 'Vault backend timed out' }) })
  if (body && body !== '{}') pr.write(body)
  pr.end()
}

// --- router ---------------------------------------------------------------
module.exports = function createVaultRouter(requireAuth) {
  const router = express.Router()
  router.use(createRouteRateLimit({ keyPrefix: 'vault', max: 120, windowMs: 60_000 }))

  router.get('/notes', requireAuth, (req, res) => {
    const vaultRoot = vaultRootForRequest(req)
    try { fs.mkdirSync(vaultRoot, { recursive: true }) } catch {}
    const { folder, tag } = req.query
    const files = listMdFiles(vaultRoot)
    const notes = []
    for (const f of files) {
      const fld = relFolder(f, vaultRoot)
      if (folder && fld !== folder) continue
      let raw; try { raw = fs.readFileSync(f, 'utf8') } catch { continue }
      const { meta } = parseFrontmatter(raw)
      const tags = Array.isArray(meta.tags) ? meta.tags : []
      if (tag && !tags.includes(tag)) continue
      const st = fs.statSync(f)
      notes.push({
        id:      meta.id    || path.basename(f, '.md').toLowerCase(),
        title:   meta.title || path.basename(f, '.md'),
        folder:  fld,
        // path: REMOVED (security audit HIGH — was leaking absolute filesystem paths)
        tags,
        updated: st.mtimeMs / 1000,
      })
    }
    notes.sort((a, b) => b.updated - a.updated)
    res.json({ notes, count: notes.length })
  })

  router.get('/notes/:id', requireAuth, (req, res) => {
    const vaultRoot = vaultRootForRequest(req)
    const id = req.params.id
    const files = listMdFiles(vaultRoot)
    for (const f of files) {
      let raw; try { raw = fs.readFileSync(f, 'utf8') } catch { continue }
      const { meta, body } = parseFrontmatter(raw)
      const fileId = meta.id || path.basename(f, '.md').toLowerCase()
      if (fileId !== id) continue
      const backlinks = safeReadJson(path.join(vaultRoot, '_backlinks.json'), {})
      const st = fs.statSync(f)
      return res.json({
        id: fileId,
        title:        meta.title || path.basename(f, '.md'),
        folder:       relFolder(f, vaultRoot),
        // path: REMOVED (security audit HIGH)
        frontmatter:  meta,
        body,
        backlinks:    backlinks[fileId] || [],
        updated:      st.mtimeMs / 1000,
      })
    }
    res.status(404).json({ error: 'note not found', id })
  })

  router.put('/notes/:id',  requireAuth, (req, res) => proxyToPython('PUT',  `/api/vault/notes/${encodeURIComponent(req.params.id)}`, req, res))
  router.post('/notes',     requireAuth, (req, res) => proxyToPython('POST', `/api/vault/notes`, req, res))
  router.delete('/notes/:id', requireAuth, (req, res) => proxyToPython('DELETE', `/api/vault/notes/${encodeURIComponent(req.params.id)}`, req, res))
  router.post('/rebuild-indices', requireAuth, (req, res) => proxyToPython('POST', `/api/vault/rebuild-indices`, req, res))

  router.get('/search', requireAuth, (req, res) => {
    const vaultRoot = vaultRootForRequest(req)
    const q = String(req.query.q || '').trim().toLowerCase()
    if (!q) return res.json({ hits: [], count: 0 })
    const files = listMdFiles(vaultRoot)
    const hits = []
    for (const f of files) {
      let raw; try { raw = fs.readFileSync(f, 'utf8').toLowerCase() } catch { continue }
      const occ = raw.split(q).length - 1
      if (occ <= 0) continue
      const { meta } = parseFrontmatter(raw)
      hits.push({
        id:    meta.id    || path.basename(f, '.md').toLowerCase(),
        title: meta.title || path.basename(f, '.md'),
        folder: relFolder(f, vaultRoot),
        // path: REMOVED (security audit HIGH)
        score: occ,
      })
    }
    hits.sort((a, b) => b.score - a.score)
    res.json({ hits: hits.slice(0, 20), count: hits.length })
  })

  router.get('/graph', requireAuth, (req, res) => {
    const vaultRoot = vaultRootForRequest(req)
    const backlinks = safeReadJson(path.join(vaultRoot, '_backlinks.json'), {})
    const index     = safeReadJson(path.join(vaultRoot, '_index.json'), [])
    const nodes = index.map(n => ({ id: n.id, title: n.title, folder: n.folder, tags: n.tags || [] }))
    const links = []
    for (const [target, sources] of Object.entries(backlinks)) {
      for (const src of sources) links.push({ source: src, target })
    }
    res.json({ nodes, links })
  })

  router.get('/broken-links', requireAuth, (req, res) => {
    const vaultRoot = vaultRootForRequest(req)
    const index = safeReadJson(path.join(vaultRoot, '_index.json'), [])
    const knownIds    = new Set(index.map(n => n.id))
    const knownTitles = new Set(index.map(n => n.title.toLowerCase()))
    const files = listMdFiles(vaultRoot)
    const broken = []
    const WL = /\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g
    for (const f of files) {
      let raw; try { raw = fs.readFileSync(f, 'utf8') } catch { continue }
      const { meta, body } = parseFrontmatter(raw)
      const srcId = meta.id || path.basename(f, '.md').toLowerCase()
      let m
      while ((m = WL.exec(body)) !== null) {
        const tgt = m[1].trim()
        const tgtKebab = tgt.toLowerCase().replace(/[^\w\s-]/g, '').replace(/[\s_]+/g, '-')
        if (!knownIds.has(tgtKebab) && !knownTitles.has(tgt.toLowerCase())) {
          broken.push([srcId, tgt])
        }
      }
    }
    res.json({ broken, count: broken.length })
  })

  return router
}
