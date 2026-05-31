'use strict'
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const os = require('os')

const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'))
const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(AI_HOME, 'state'))
const REPO_ROOT = path.resolve(__dirname, '..', '..')
const SQL_AUDIT_FILE = path.join(STATE_DIR, 'memory_sql_audit.jsonl')

const MAX_SQL_ROWS = 100

// ── File I/O helpers ────────────────────────────────────────────────────────

function readJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return fallback }
}

function readJsonl(file, limit = 100) {
  try {
    return fs.readFileSync(file, 'utf8')
      .trim()
      .split('\n')
      .filter(Boolean)
      .slice(-limit)
      .map((line) => { try { return JSON.parse(line) } catch { return null } })
      .filter(Boolean)
  } catch {
    return []
  }
}

function appendJsonl(file, item) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.appendFileSync(file, `${JSON.stringify(item)}\n`, 'utf8')
  } catch {}
}

// ── Path helpers ─────────────────────────────────────────────────────────────

function stateFile(...parts) {
  return path.join(STATE_DIR, ...parts)
}

function repoFile(...parts) {
  return path.join(REPO_ROOT, ...parts)
}

// ── Text / scoring helpers ────────────────────────────────────────────────────

function hashId(input) {
  return crypto.createHash('sha256').update(String(input)).digest('hex').slice(0, 12)
}

function tokens(text) {
  return String(text || '')
    .toLowerCase()
    .match(/[a-z0-9][a-z0-9_-]{1,}/g) || []
}

function scoreText(query, text) {
  const q = [...new Set(tokens(query).filter((t) => t.length > 2))]
  if (!q.length) return 0
  const body = String(text || '').toLowerCase()
  const hits = q.filter((t) => body.includes(t)).length
  return Number((hits / q.length).toFixed(4))
}

// ── SQL helpers ───────────────────────────────────────────────────────────────

function nowIso() {
  return new Date().toISOString()
}

function fileExists(file) {
  try { return fs.existsSync(file) } catch { return false }
}

function stripTrailingSemicolons(value) {
  let s = String(value || '').trim()
  while (s.endsWith(';')) s = s.slice(0, -1).trimEnd()
  return s
}

function sqlTokens(value) {
  return String(value || '')
    .toLowerCase()
    .split(/[^a-z_]+/)
    .filter(Boolean)
}

function validateReadOnlySql(sql) {
  const cleaned = stripTrailingSemicolons(sql)
  if (!cleaned) return { ok: false, error: 'sql required' }
  if (cleaned.length > 5000) return { ok: false, error: 'sql too large' }
  if (cleaned.includes(';')) return { ok: false, error: 'multiple statements are blocked' }
  const toks = sqlTokens(cleaned)
  if (!['select', 'with'].includes(toks[0])) return { ok: false, error: 'only SELECT/WITH read-only queries are allowed' }
  const blocked = new Set(['insert', 'update', 'delete', 'drop', 'alter', 'create', 'replace', 'attach', 'detach', 'vacuum', 'reindex', 'pragma'])
  if (toks.some((token) => blocked.has(token))) {
    return { ok: false, error: 'write/admin SQL keywords are blocked' }
  }
  return { ok: true, sql: toks.includes('limit') ? cleaned : `${cleaned} LIMIT ${MAX_SQL_ROWS}` }
}

function discoverSqlDatabases() {
  const roots = [...new Set([STATE_DIR, repoFile('state')])].filter(fileExists)
  const found = new Map()
  const scan = (dir, depth = 0) => {
    if (depth > 4) return
    let entries = []
    try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch { return }
    for (const entry of entries) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        if (!entry.name.startsWith('.') && entry.name !== 'node_modules') scan(full, depth + 1)
        continue
      }
      if (!/\.(db|sqlite|sqlite3)$/i.test(entry.name)) continue
      if (/-wal$|-shm$/i.test(entry.name)) continue
      const id = `${entry.name.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase()}_${hashId(full)}`
      found.set(id, { id, name: entry.name, path: full })
    }
  }
  roots.forEach((root) => scan(root))
  return [...found.values()].slice(0, 40)
}

function runReadOnlySql({ database, sql, params = [] }, actor = 'operator') {
  const dbInfo = discoverSqlDatabases().find((db) => db.id === database)
  if (!dbInfo) return { ok: false, status: 404, error: 'database not found' }
  const validated = validateReadOnlySql(sql)
  const audit = {
    id: `sql_${Date.now()}_${hashId(sql)}`,
    ts: nowIso(),
    actor,
    database,
    sql: String(sql || '').slice(0, 2000),
    allowed: validated.ok,
    error: validated.error || null,
  }
  if (!validated.ok) {
    appendJsonl(SQL_AUDIT_FILE, audit)
    return { ok: false, status: 400, error: validated.error }
  }
  let Database
  try { Database = require('better-sqlite3') } catch {
    audit.allowed = false
    audit.error = 'better-sqlite3 unavailable'
    appendJsonl(SQL_AUDIT_FILE, audit)
    return { ok: false, status: 503, error: audit.error }
  }
  try {
    const db = new Database(dbInfo.path, { readonly: true, fileMustExist: true, timeout: 1500 })
    const started = Date.now()
    const rows = db.prepare(validated.sql).all(Array.isArray(params) ? params.slice(0, 20) : []) // lgtm [js/sql-injection] Read-only SELECT/WITH SQL is validated above and opened readonly.
    db.close()
    audit.row_count = rows.length
    audit.ms = Date.now() - started
    appendJsonl(SQL_AUDIT_FILE, audit)
    return { ok: true, database: dbInfo.id, sql: validated.sql, rows, row_count: rows.length, ms: audit.ms }
  } catch (err) {
    audit.allowed = false
    audit.error = err.message
    appendJsonl(SQL_AUDIT_FILE, audit)
    return { ok: false, status: 400, error: err.message }
  }
}

module.exports = {
  readJSON,
  readJsonl,
  appendJsonl,
  hashId,
  tokens,
  scoreText,
  stateFile,
  repoFile,
  validateReadOnlySql,
  runReadOnlySql,
}
