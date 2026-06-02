'use strict'

const fs = require('fs')
const path = require('path')

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

function asList(value) {
  return Array.isArray(value) ? value : []
}

function nowIso() {
  return new Date().toISOString()
}

class ForgeStore {
  constructor({ forgeHome, runsFile, maxRuns = 500 } = {}) {
    if (!forgeHome) throw new Error('forgeHome is required')
    this.forgeHome = forgeHome
    this.runsFile = runsFile || path.join(forgeHome, 'runs.json')
    this.dbPath = path.join(forgeHome, 'forge_runs.db')
    this.maxRuns = maxRuns
    this.backend = 'json'
    this.lastError = null
    this._db = null
    this._initAttempted = false
    this._migrationAttempted = false
  }

  status() {
    this._ensureDb()
    return {
      backend: this.backend,
      sqlite_available: Boolean(this._db),
      db_path: this._db ? this.dbPath : null,
      json_mirror_path: this.runsFile,
      last_error: this.lastError,
    }
  }

  loadRuns() {
    this._ensureDb()
    if (!this._db) return this._loadJsonRuns()
    this._migrateJsonRunsIfNeeded()
    try {
      const rows = this._db.prepare(`
        SELECT payload_json
        FROM forge_runs
        ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
        LIMIT ?
      `).all(this.maxRuns)
      const sqliteRuns = rows.map(row => JSON.parse(row.payload_json))
      const seen = new Set(sqliteRuns.map(run => run.id || run.run_id))
      const jsonOnlyRuns = this._loadJsonRuns().filter((run) => {
        const id = run.id || run.run_id
        return id && !seen.has(id)
      })
      return [...sqliteRuns, ...jsonOnlyRuns].slice(0, this.maxRuns)
    } catch (err) {
      this._degrade(err)
      return this._loadJsonRuns()
    }
  }

  saveRuns(runs) {
    const normalized = asList(runs).slice(0, this.maxRuns).map(run => this._normalizeRun(run))
    this._saveJsonRuns(normalized)
    this._ensureDb()
    if (!this._db) return
    try {
      const replaceAll = this._db.transaction((items) => {
        this._db.prepare('DELETE FROM forge_run_actions').run()
        this._db.prepare('DELETE FROM forge_runs').run()
        for (const run of items) this._insertRun(run)
      })
      replaceAll(normalized)
    } catch (err) {
      this._degrade(err)
    }
  }

  findRun(id) {
    if (!id) return null
    this._ensureDb()
    if (this._db) {
      this._migrateJsonRunsIfNeeded()
      try {
        const row = this._db.prepare('SELECT payload_json FROM forge_runs WHERE run_id = ?').get(id)
        if (row) return JSON.parse(row.payload_json)
      } catch (err) {
        this._degrade(err)
      }
    }
    return this._loadJsonRuns().find(run => run.id === id || run.run_id === id) || null
  }

  updateRun(id, patch) {
    const runs = this.loadRuns()
    const updated = runs.map(run => (run.id === id || run.run_id === id)
      ? this._normalizeRun({ ...run, ...patch, updated_at: nowIso() })
      : run)
    this.saveRuns(updated)
    return updated.find(run => run.id === id || run.run_id === id) || null
  }

  upsertRun(run) {
    const normalized = this._normalizeRun({ ...run, updated_at: nowIso() })
    const runs = this.loadRuns().filter(item => item.id !== normalized.id && item.run_id !== normalized.run_id)
    const next = [normalized, ...runs].slice(0, this.maxRuns)
    this.saveRuns(next)
    return this.findRun(normalized.id)
  }

  recordAudit(event, details = {}) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare(`
        INSERT INTO forge_run_audit (id, run_id, event, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
      `).run(
        `audit-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        details?.run_id || null,
        event,
        JSON.stringify(details || {}),
        nowIso(),
      )
    } catch (err) {
      this._degrade(err)
    }
  }

  _ensureDb() {
    if (this._initAttempted) return
    this._initAttempted = true
    if (process.env.FORGE_RUN_STORE === 'json') {
      this.backend = 'json'
      return
    }
    try {
      ensureDir(this.forgeHome)
      const Database = require('better-sqlite3')
      this._db = new Database(this.dbPath)
      this._db.pragma('journal_mode = WAL')
      this._db.pragma('foreign_keys = ON')
      this._db.exec(`
        CREATE TABLE IF NOT EXISTS forge_runs (
          run_id TEXT PRIMARY KEY,
          project_id TEXT,
          goal TEXT,
          status TEXT,
          mode TEXT,
          provider TEXT,
          created_at TEXT,
          updated_at TEXT,
          payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_runs_project_status
          ON forge_runs(project_id, status, updated_at);

        CREATE TABLE IF NOT EXISTS forge_run_actions (
          action_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          project_id TEXT,
          type TEXT,
          status TEXT,
          approval_required INTEGER DEFAULT 0,
          risk TEXT,
          file_path TEXT,
          created_at TEXT,
          updated_at TEXT,
          payload_json TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES forge_runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_forge_run_actions_run_status
          ON forge_run_actions(run_id, status);

        CREATE TABLE IF NOT EXISTS forge_run_audit (
          id TEXT PRIMARY KEY,
          run_id TEXT,
          event TEXT NOT NULL,
          details_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_run_audit_run_time
          ON forge_run_audit(run_id, created_at);
      `)
      this.backend = 'sqlite'
      this.lastError = null
    } catch (err) {
      this._degrade(err)
    }
  }

  _migrateJsonRunsIfNeeded() {
    if (this._migrationAttempted || !this._db) return
    this._migrationAttempted = true
    const existing = this._db.prepare('SELECT COUNT(*) AS count FROM forge_runs').get()?.count || 0
    if (existing > 0) return
    const jsonRuns = this._loadJsonRuns()
    if (!jsonRuns.length) return
    const insertMany = this._db.transaction((items) => {
      for (const run of items) this._insertRun(this._normalizeRun(run))
    })
    insertMany(jsonRuns.slice(0, this.maxRuns))
  }

  _insertRun(run) {
    this._db.prepare(`
      INSERT OR REPLACE INTO forge_runs
        (run_id, project_id, goal, status, mode, provider, created_at, updated_at, payload_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      run.id,
      run.project_id || null,
      run.goal || '',
      run.status || '',
      run.mode || '',
      run.provider || '',
      run.created_at || nowIso(),
      run.updated_at || nowIso(),
      JSON.stringify(run),
    )
    const insertAction = this._db.prepare(`
      INSERT OR REPLACE INTO forge_run_actions
        (action_id, run_id, project_id, type, status, approval_required, risk, file_path, created_at, updated_at, payload_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
    for (const action of asList(run.actions)) {
      const actionId = action.id || `${run.id}-action-${Math.random().toString(16).slice(2)}`
      insertAction.run(
        actionId,
        run.id,
        action.project_id || run.project_id || null,
        action.type || '',
        action.status || '',
        action.approval_required ? 1 : 0,
        action.risk || action.risk_level || null,
        action.file_path || action.path || null,
        action.created_at || run.created_at || nowIso(),
        action.updated_at || run.updated_at || nowIso(),
        JSON.stringify({ ...action, id: actionId, run_id: run.id }),
      )
    }
  }

  _normalizeRun(run) {
    const id = run.id || run.run_id
    const createdAt = run.created_at || nowIso()
    const updatedAt = run.updated_at || createdAt
    return {
      ...run,
      id,
      run_id: run.run_id || id,
      actions: asList(run.actions),
      patches: asList(run.patches),
      approvals: asList(run.approvals),
      test_results: asList(run.test_results),
      audit_ids: asList(run.audit_ids),
      created_at: createdAt,
      updated_at: updatedAt,
    }
  }

  _loadJsonRuns() {
    return asList(readJson(this.runsFile, [])).slice(0, this.maxRuns)
  }

  _saveJsonRuns(runs) {
    writeJson(this.runsFile, asList(runs).slice(0, this.maxRuns))
  }

  _degrade(err) {
    this.backend = 'json'
    this.lastError = err?.message || String(err)
    this._db = null
  }

  // ── Training runs ─────────────────────────────────────────────────────────

  _trainingFile(projectId) {
    return path.join(this.forgeHome, 'training', `${projectId}.json`)
  }

  _loadTrainingData(projectId) {
    return readJson(this._trainingFile(projectId), { training_runs: [], model_versions: [] })
  }

  _saveTrainingData(projectId, data) {
    writeJson(this._trainingFile(projectId), data)
  }

  createTrainingRun(projectId, params = {}) {
    const data = this._loadTrainingData(projectId)
    const run = {
      training_run_id: `tr-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`,
      project_id: projectId,
      model_type: params.model_type || 'intent_classifier',
      status: 'PENDING',
      metrics: {},
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    data.training_runs.unshift(run)
    this._saveTrainingData(projectId, data)
    return run
  }

  getTrainingRuns(projectId) {
    return this._loadTrainingData(projectId).training_runs
  }

  findTrainingRun(trainingRunId) {
    const home = this.forgeHome
    const trainingDir = path.join(home, 'training')
    if (!require('fs').existsSync(trainingDir)) return null
    for (const f of require('fs').readdirSync(trainingDir)) {
      if (!f.endsWith('.json')) continue
      const data = readJson(path.join(trainingDir, f), { training_runs: [] })
      const run = data.training_runs.find(r => r.training_run_id === trainingRunId)
      if (run) return run
    }
    return null
  }

  updateTrainingRun(trainingRunId, patch) {
    const home = this.forgeHome
    const trainingDir = path.join(home, 'training')
    if (!require('fs').existsSync(trainingDir)) return null
    for (const f of require('fs').readdirSync(trainingDir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(trainingDir, f)
      const data = readJson(file, { training_runs: [], model_versions: [] })
      const idx = data.training_runs.findIndex(r => r.training_run_id === trainingRunId)
      if (idx === -1) continue
      data.training_runs[idx] = { ...data.training_runs[idx], ...patch, updated_at: nowIso() }
      writeJson(file, data)
      return data.training_runs[idx]
    }
    return null
  }

  getTrainingSummary(projectId) {
    const data = this._loadTrainingData(projectId)
    const runs = data.training_runs || []
    const versions = data.model_versions || []
    return {
      total_runs: runs.length,
      completed: runs.filter(r => r.status === 'COMPLETED').length,
      failed: runs.filter(r => r.status === 'FAILED').length,
      pending: runs.filter(r => r.status === 'PENDING').length,
      training: runs.filter(r => r.status === 'TRAINING').length,
      model_versions: versions.length,
      last_run: runs[0] || null,
    }
  }

  // ── Model versions ────────────────────────────────────────────────────────

  getModelVersions(projectId, opts = {}) {
    const data = this._loadTrainingData(projectId)
    let versions = data.model_versions || []
    if (opts.model_type) versions = versions.filter(v => v.model_type === opts.model_type)
    return versions.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }

  upsertModelVersion(projectId, mv) {
    const data = this._loadTrainingData(projectId)
    const versions = data.model_versions || []
    const idx = versions.findIndex(v => v.model_version_id === mv.model_version_id)
    if (idx >= 0) versions[idx] = { ...versions[idx], ...mv, updated_at: nowIso() }
    else versions.unshift({ ...mv, created_at: mv.created_at || nowIso() })
    data.model_versions = versions
    this._saveTrainingData(projectId, data)
    return versions.find(v => v.model_version_id === mv.model_version_id)
  }

  // ── Cognitive events ──────────────────────────────────────────────────────

  _cognitiveFile(projectId) {
    return path.join(this.forgeHome, 'cognitive', `${projectId}.json`)
  }

  getCognitiveEvents(projectId) {
    return readJson(this._cognitiveFile(projectId), { events: [] }).events
  }

  upsertCognitiveEvent(event) {
    const projectId = event.project_id
    if (!projectId) return event
    return this.addCognitiveEvent(projectId, event)
  }

  addCognitiveEvent(projectId, event) {
    const file = this._cognitiveFile(projectId)
    const data = readJson(file, { events: [] })
    data.events.unshift({ ...event, timestamp: event.timestamp || nowIso() })
    if (data.events.length > 500) data.events = data.events.slice(0, 500)
    writeJson(file, data)
    return data.events[0]
  }
}

module.exports = { ForgeStore }
