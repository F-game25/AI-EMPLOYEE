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

        CREATE TABLE IF NOT EXISTS forge_patches (
          patch_id    TEXT PRIMARY KEY,
          run_id      TEXT NOT NULL,
          action_id   TEXT,
          iteration   INTEGER,
          file_path   TEXT,
          action_type TEXT,
          before_hash TEXT,
          after_hash  TEXT,
          unified_diff TEXT,
          risk_level  TEXT,
          status      TEXT DEFAULT 'staged',
          created_at  TEXT,
          updated_at  TEXT,
          FOREIGN KEY(run_id) REFERENCES forge_runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_forge_patches_run
          ON forge_patches(run_id, iteration);

        CREATE TABLE IF NOT EXISTS forge_backlog (
          backlog_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT,
          priority INTEGER DEFAULT 50,
          category TEXT DEFAULT 'FEATURE',
          status TEXT DEFAULT 'IDEA',
          risk_level TEXT DEFAULT 'low',
          estimated_complexity TEXT,
          dependencies TEXT DEFAULT '[]',
          source TEXT DEFAULT 'manual',
          linked_run_id TEXT,
          acceptance_criteria TEXT,
          linked_files TEXT DEFAULT '[]',
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_backlog_project_status
          ON forge_backlog(project_id, status, priority);

        CREATE TABLE IF NOT EXISTS forge_cycles (
          cycle_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          goal TEXT,
          status TEXT DEFAULT 'PLANNING',
          autonomy_level INTEGER DEFAULT 2,
          max_runs INTEGER DEFAULT 20,
          max_duration_sec INTEGER DEFAULT 3600,
          started_at TEXT,
          ended_at TEXT,
          backlog_items TEXT DEFAULT '[]',
          run_ids TEXT DEFAULT '[]',
          success_criteria TEXT,
          current_phase TEXT,
          final_report TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_cycles_project
          ON forge_cycles(project_id, status);

        CREATE TABLE IF NOT EXISTS forge_roadmaps (
          roadmap_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL UNIQUE,
          content TEXT NOT NULL,
          generated_at TEXT,
          updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS forge_suggestions (
          suggestion_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          source_run_id TEXT,
          category TEXT,
          title TEXT NOT NULL,
          description TEXT,
          evidence TEXT DEFAULT '[]',
          recommended_fix TEXT,
          risk_level TEXT DEFAULT 'low',
          status TEXT DEFAULT 'new',
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_suggestions_project
          ON forge_suggestions(project_id, status);

        CREATE TABLE IF NOT EXISTS forge_memory_v3 (
          memory_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          source_run_id TEXT,
          category TEXT,
          fact TEXT NOT NULL,
          evidence TEXT DEFAULT '[]',
          confidence TEXT DEFAULT 'low',
          usage_count INTEGER DEFAULT 0,
          last_used_at TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_memory_v3_project
          ON forge_memory_v3(project_id, confidence, category);

        CREATE TABLE IF NOT EXISTS forge_models (
          model_id TEXT PRIMARY KEY,
          provider TEXT,
          role TEXT DEFAULT 'any',
          cost_tier TEXT DEFAULT 'medium',
          speed_tier TEXT DEFAULT 'medium',
          context_window INTEGER DEFAULT 200000,
          supports_tools INTEGER DEFAULT 1,
          supports_json INTEGER DEFAULT 1,
          supports_code INTEGER DEFAULT 1,
          local_or_remote TEXT DEFAULT 'remote',
          enabled INTEGER DEFAULT 1,
          created_at TEXT,
          updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS forge_model_routing_logs (
          log_id TEXT PRIMARY KEY,
          run_id TEXT,
          stage TEXT,
          selected_model_id TEXT,
          reason TEXT,
          fallback_model_id TEXT,
          failure_reason TEXT,
          token_estimate INTEGER,
          created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_model_routing_run
          ON forge_model_routing_logs(run_id, stage);

        CREATE TABLE IF NOT EXISTS forge_child_runs (
          child_id TEXT PRIMARY KEY,
          parent_run_id TEXT NOT NULL,
          child_run_id TEXT,
          dependency_run_ids TEXT DEFAULT '[]',
          merge_status TEXT DEFAULT 'pending',
          conflict_status TEXT,
          final_child_report TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_child_runs_parent
          ON forge_child_runs(parent_run_id);
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

  recordPatch(patch) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_patches
          (patch_id, run_id, action_id, iteration, file_path, action_type,
           before_hash, after_hash, unified_diff, risk_level, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        patch.patch_id,
        patch.run_id,
        patch.action_id || null,
        patch.iteration ?? null,
        patch.file_path || null,
        patch.action_type || 'create',
        patch.before_hash || null,
        patch.after_hash  || null,
        patch.unified_diff || null,
        patch.risk_level || 'low',
        patch.status || 'staged',
        patch.created_at || nowIso(),
        patch.updated_at || nowIso(),
      )
    } catch (err) {
      this._degrade(err)
    }
  }

  updatePatchStatus(patchId, status) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare('UPDATE forge_patches SET status = ?, updated_at = ? WHERE patch_id = ?')
        .run(status, nowIso(), patchId)
    } catch (err) {
      this._degrade(err)
    }
  }

  getPatchesForRun(runId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT patch_id, run_id, action_id, iteration, file_path, action_type, before_hash, after_hash, unified_diff, risk_level, status, created_at, updated_at FROM forge_patches WHERE run_id = ? ORDER BY iteration, created_at'
      ).all(runId)
    } catch (err) {
      this._degrade(err)
      return []
    }
  }

  getAuditEventsForRun(runId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT id, run_id, event, details_json, created_at FROM forge_run_audit WHERE run_id = ? ORDER BY created_at'
      ).all(runId).map(row => ({ ...row, details: (() => { try { return JSON.parse(row.details_json) } catch { return {} } })() }))
    } catch (err) {
      this._degrade(err)
      return []
    }
  }

  getMetricsForProject(projectId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const statusRows = this._db.prepare(
        'SELECT status, COUNT(*) as count FROM forge_runs WHERE project_id = ? GROUP BY status'
      ).all(projectId)
      const totalRow = this._db.prepare('SELECT COUNT(*) as total FROM forge_runs WHERE project_id = ?').get(projectId)
      const successRow = this._db.prepare(
        "SELECT COUNT(*) as cnt FROM forge_runs WHERE project_id = ? AND status IN ('applied','verified')"
      ).get(projectId)
      const durationRow = this._db.prepare(
        "SELECT AVG((julianday(updated_at) - julianday(created_at)) * 86400) as avg_sec FROM forge_runs WHERE project_id = ? AND status IN ('applied','verified','verify_failed','failed')"
      ).get(projectId)
      const patchStats = this._db.prepare(
        "SELECT status, COUNT(*) as count FROM forge_patches WHERE run_id IN (SELECT run_id FROM forge_runs WHERE project_id = ?) GROUP BY status"
      ).all(projectId)
      const securityBlocks = this._db.prepare(
        "SELECT COUNT(*) as cnt FROM forge_run_audit WHERE run_id IN (SELECT run_id FROM forge_runs WHERE project_id = ?) AND event = 'forge_command_blocked'"
      ).get(projectId)
      const topFiles = this._db.prepare(
        "SELECT file_path, COUNT(*) as cnt FROM forge_patches WHERE run_id IN (SELECT run_id FROM forge_runs WHERE project_id = ?) AND status = 'applied' GROUP BY file_path ORDER BY cnt DESC LIMIT 10"
      ).all(projectId)
      const total = totalRow?.total || 0
      const successful = successRow?.cnt || 0
      return {
        total_runs: total,
        success_rate: total > 0 ? Math.round((successful / total) * 100) / 100 : 0,
        avg_duration_sec: Math.round(durationRow?.avg_sec || 0),
        by_status: Object.fromEntries(statusRows.map(r => [r.status, r.count])),
        patch_stats: Object.fromEntries(patchStats.map(r => [r.status, r.count])),
        security_blocks: securityBlocks?.cnt || 0,
        most_edited_files: topFiles.map(r => r.file_path),
      }
    } catch (err) {
      this._degrade(err)
      return null
    }
  }

  // ── Backlog ──────────────────────────────────────────────────────────────────
  upsertBacklogItem(item) {
    this._ensureDb()
    if (!this._db) return item
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_backlog
          (backlog_id, project_id, title, description, priority, category, status,
           risk_level, estimated_complexity, dependencies, source, linked_run_id,
           acceptance_criteria, linked_files, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        item.backlog_id, item.project_id, item.title || '', item.description || '',
        item.priority ?? 50, item.category || 'FEATURE', item.status || 'IDEA',
        item.risk_level || 'low', item.estimated_complexity || null,
        JSON.stringify(item.dependencies || []), item.source || 'manual',
        item.linked_run_id || null, item.acceptance_criteria || null,
        JSON.stringify(item.linked_files || []),
        item.created_at || nowIso(), item.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return item
  }

  getBacklog(projectId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_backlog WHERE project_id = ? ORDER BY priority DESC, created_at ASC'
      ).all(projectId).map(r => ({
        ...r,
        dependencies: (() => { try { return JSON.parse(r.dependencies) } catch { return [] } })(),
        linked_files: (() => { try { return JSON.parse(r.linked_files) } catch { return [] } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  findBacklogItem(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_backlog WHERE backlog_id = ?').get(id)
      if (!r) return null
      return {
        ...r,
        dependencies: (() => { try { return JSON.parse(r.dependencies) } catch { return [] } })(),
        linked_files: (() => { try { return JSON.parse(r.linked_files) } catch { return [] } })(),
      }
    } catch (err) { this._degrade(err); return null }
  }

  updateBacklogItem(id, patch) {
    const item = this.findBacklogItem(id)
    if (!item) return null
    return this.upsertBacklogItem({ ...item, ...patch, backlog_id: id, updated_at: nowIso() })
  }

  deleteBacklogItem(id) {
    this._ensureDb()
    if (!this._db) return
    try { this._db.prepare('DELETE FROM forge_backlog WHERE backlog_id = ?').run(id) }
    catch (err) { this._degrade(err) }
  }

  // ── Cycles ────────────────────────────────────────────────────────────────
  upsertCycle(cycle) {
    this._ensureDb()
    if (!this._db) return cycle
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_cycles
          (cycle_id, project_id, goal, status, autonomy_level, max_runs, max_duration_sec,
           started_at, ended_at, backlog_items, run_ids, success_criteria, current_phase,
           final_report, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        cycle.cycle_id, cycle.project_id, cycle.goal || '',
        cycle.status || 'PLANNING', cycle.autonomy_level ?? 2,
        cycle.max_runs ?? 20, cycle.max_duration_sec ?? 3600,
        cycle.started_at || null, cycle.ended_at || null,
        JSON.stringify(cycle.backlog_items || []),
        JSON.stringify(cycle.run_ids || []),
        cycle.success_criteria || null, cycle.current_phase || null,
        cycle.final_report ? JSON.stringify(cycle.final_report) : null,
        cycle.created_at || nowIso(), cycle.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return cycle
  }

  getCycles(projectId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_cycles WHERE project_id = ? ORDER BY created_at DESC'
      ).all(projectId).map(r => ({
        ...r,
        backlog_items: (() => { try { return JSON.parse(r.backlog_items) } catch { return [] } })(),
        run_ids: (() => { try { return JSON.parse(r.run_ids) } catch { return [] } })(),
        final_report: (() => { try { return r.final_report ? JSON.parse(r.final_report) : null } catch { return null } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  findCycle(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_cycles WHERE cycle_id = ?').get(id)
      if (!r) return null
      return {
        ...r,
        backlog_items: (() => { try { return JSON.parse(r.backlog_items) } catch { return [] } })(),
        run_ids: (() => { try { return JSON.parse(r.run_ids) } catch { return [] } })(),
        final_report: (() => { try { return r.final_report ? JSON.parse(r.final_report) : null } catch { return null } })(),
      }
    } catch (err) { this._degrade(err); return null }
  }

  updateCycle(id, patch) {
    const cycle = this.findCycle(id)
    if (!cycle) return null
    return this.upsertCycle({ ...cycle, ...patch, cycle_id: id, updated_at: nowIso() })
  }

  // ── Roadmap ───────────────────────────────────────────────────────────────
  upsertRoadmap(projectId, content) {
    this._ensureDb()
    if (!this._db) return null
    const id = `roadmap-${projectId}`
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_roadmaps (roadmap_id, project_id, content, generated_at, updated_at)
        VALUES (?,?,?,?,?)
      `).run(id, projectId, JSON.stringify(content), nowIso(), nowIso())
    } catch (err) { this._degrade(err) }
    return { roadmap_id: id, project_id: projectId, content, updated_at: nowIso() }
  }

  getRoadmap(projectId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_roadmaps WHERE project_id = ?').get(projectId)
      if (!r) return null
      return { ...r, content: (() => { try { return JSON.parse(r.content) } catch { return {} } })() }
    } catch (err) { this._degrade(err); return null }
  }

  // ── Suggestions ───────────────────────────────────────────────────────────
  upsertSuggestion(s) {
    this._ensureDb()
    if (!this._db) return s
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_suggestions
          (suggestion_id, project_id, source_run_id, category, title, description,
           evidence, recommended_fix, risk_level, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        s.suggestion_id, s.project_id, s.source_run_id || null,
        s.category || 'general', s.title, s.description || '',
        JSON.stringify(s.evidence || []), s.recommended_fix || null,
        s.risk_level || 'low', s.status || 'new',
        s.created_at || nowIso(), s.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return s
  }

  getSuggestions(projectId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_suggestions WHERE project_id = ? ORDER BY created_at DESC'
      ).all(projectId).map(r => ({
        ...r,
        evidence: (() => { try { return JSON.parse(r.evidence) } catch { return [] } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  findSuggestion(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_suggestions WHERE suggestion_id = ?').get(id)
      if (!r) return null
      return { ...r, evidence: (() => { try { return JSON.parse(r.evidence) } catch { return [] } })() }
    } catch (err) { this._degrade(err); return null }
  }

  updateSuggestion(id, patch) {
    const s = this.findSuggestion(id)
    if (!s) return null
    return this.upsertSuggestion({ ...s, ...patch, suggestion_id: id, updated_at: nowIso() })
  }

  // ── Memory V3 ─────────────────────────────────────────────────────────────
  upsertMemoryFact(fact) {
    this._ensureDb()
    if (!this._db) return fact
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_memory_v3
          (memory_id, project_id, source_run_id, category, fact, evidence,
           confidence, usage_count, last_used_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        fact.memory_id, fact.project_id, fact.source_run_id || null,
        fact.category || 'general', fact.fact,
        JSON.stringify(fact.evidence || []),
        fact.confidence || 'low', fact.usage_count ?? 0,
        fact.last_used_at || null,
        fact.created_at || nowIso(), fact.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return fact
  }

  getMemoryFacts(projectId, category) {
    this._ensureDb()
    if (!this._db) return []
    try {
      const q = category
        ? 'SELECT * FROM forge_memory_v3 WHERE project_id = ? AND category = ? ORDER BY confidence DESC, usage_count DESC'
        : 'SELECT * FROM forge_memory_v3 WHERE project_id = ? ORDER BY confidence DESC, usage_count DESC'
      const args = category ? [projectId, category] : [projectId]
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        evidence: (() => { try { return JSON.parse(r.evidence) } catch { return [] } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  touchMemoryFact(id) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare(
        'UPDATE forge_memory_v3 SET usage_count = usage_count + 1, last_used_at = ?, updated_at = ? WHERE memory_id = ?'
      ).run(nowIso(), nowIso(), id)
    } catch (err) { this._degrade(err) }
  }

  findMemoryFactByContent(projectId, factText) {
    this._ensureDb()
    if (!this._db) return null
    try {
      return this._db.prepare(
        'SELECT * FROM forge_memory_v3 WHERE project_id = ? AND fact = ?'
      ).get(projectId, factText) || null
    } catch (err) { this._degrade(err); return null }
  }

  // ── Models ────────────────────────────────────────────────────────────────
  upsertModel(model) {
    this._ensureDb()
    if (!this._db) return model
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_models
          (model_id, provider, role, cost_tier, speed_tier, context_window,
           supports_tools, supports_json, supports_code, local_or_remote, enabled, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        model.model_id, model.provider || 'anthropic', model.role || 'any',
        model.cost_tier || 'medium', model.speed_tier || 'medium',
        model.context_window ?? 200000,
        model.supports_tools ? 1 : 0, model.supports_json ? 1 : 0,
        model.supports_code ? 1 : 0, model.local_or_remote || 'remote',
        model.enabled !== false ? 1 : 0,
        model.created_at || nowIso(), model.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return model
  }

  getModels() {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare('SELECT * FROM forge_models ORDER BY role, model_id').all()
        .map(r => ({ ...r, supports_tools: !!r.supports_tools, supports_json: !!r.supports_json, supports_code: !!r.supports_code, enabled: !!r.enabled }))
    } catch (err) { this._degrade(err); return [] }
  }

  getModel(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_models WHERE model_id = ?').get(id)
      if (!r) return null
      return { ...r, supports_tools: !!r.supports_tools, supports_json: !!r.supports_json, supports_code: !!r.supports_code, enabled: !!r.enabled }
    } catch (err) { this._degrade(err); return null }
  }

  updateModel(id, patch) {
    const m = this.getModel(id)
    if (!m) return null
    return this.upsertModel({ ...m, ...patch, model_id: id, updated_at: nowIso() })
  }

  // ── Model Routing Logs ────────────────────────────────────────────────────
  recordModelRouting(log) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare(`
        INSERT INTO forge_model_routing_logs
          (log_id, run_id, stage, selected_model_id, reason, fallback_model_id, failure_reason, token_estimate, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
      `).run(
        log.log_id || `mrl-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        log.run_id || null, log.stage || null, log.selected_model_id || null,
        log.reason || null, log.fallback_model_id || null, log.failure_reason || null,
        log.token_estimate || null, log.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
  }

  getModelRoutingStats(projectId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(`
        SELECT mrl.stage, mrl.selected_model_id, COUNT(*) as count
        FROM forge_model_routing_logs mrl
        JOIN forge_runs fr ON mrl.run_id = fr.run_id
        WHERE fr.project_id = ?
        GROUP BY mrl.stage, mrl.selected_model_id
        ORDER BY mrl.stage, count DESC
      `).all(projectId)
    } catch (err) { this._degrade(err); return [] }
  }

  // ── Child Runs ────────────────────────────────────────────────────────────
  upsertChildRun(child) {
    this._ensureDb()
    if (!this._db) return child
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_child_runs
          (child_id, parent_run_id, child_run_id, dependency_run_ids,
           merge_status, conflict_status, final_child_report, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
      `).run(
        child.child_id, child.parent_run_id, child.child_run_id || null,
        JSON.stringify(child.dependency_run_ids || []),
        child.merge_status || 'pending', child.conflict_status || null,
        child.final_child_report ? JSON.stringify(child.final_child_report) : null,
        child.created_at || nowIso(), child.updated_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return child
  }

  getChildRuns(parentRunId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_child_runs WHERE parent_run_id = ? ORDER BY created_at'
      ).all(parentRunId).map(r => ({
        ...r,
        dependency_run_ids: (() => { try { return JSON.parse(r.dependency_run_ids) } catch { return [] } })(),
        final_child_report: (() => { try { return r.final_child_report ? JSON.parse(r.final_child_report) : null } catch { return null } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  updateChildRun(id, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_child_runs WHERE child_id = ?').get(id)
      if (!r) return null
      const existing = {
        ...r,
        dependency_run_ids: (() => { try { return JSON.parse(r.dependency_run_ids) } catch { return [] } })(),
        final_child_report: (() => { try { return r.final_child_report ? JSON.parse(r.final_child_report) : null } catch { return null } })(),
      }
      return this.upsertChildRun({ ...existing, ...patch, child_id: id, updated_at: nowIso() })
    } catch (err) { this._degrade(err); return null }
  }

  _degrade(err) {
    this.backend = 'json'
    this.lastError = err?.message || String(err)
    this._db = null
  }
}

module.exports = { ForgeStore }
