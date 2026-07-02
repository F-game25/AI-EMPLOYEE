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

        CREATE TABLE IF NOT EXISTS forge_autopilot_sessions (
          project_id TEXT PRIMARY KEY,
          active INTEGER DEFAULT 0,
          runs_completed INTEGER DEFAULT 0,
          consecutive_fails INTEGER DEFAULT 0,
          max_runs INTEGER DEFAULT 10,
          autonomy_level INTEGER DEFAULT 2,
          cycle_id TEXT,
          current_run_id TEXT,
          started_at TEXT,
          updated_at TEXT
        );

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

        CREATE TABLE IF NOT EXISTS forge_distillation_records (
          distill_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          goal TEXT,
          stack_json TEXT DEFAULT '{}',
          trajectory_summary_json TEXT DEFAULT '{}',
          outcome_summary_json TEXT DEFAULT '{}',
          scores_json TEXT DEFAULT '{}',
          lessons_json TEXT DEFAULT '[]',
          preference_pairs_json TEXT DEFAULT '[]',
          skill_proposals_json TEXT DEFAULT '[]',
          eval_cases_json TEXT DEFAULT '[]',
          confidence TEXT DEFAULT 'low',
          approved_for_training INTEGER DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_distillation_project
          ON forge_distillation_records(project_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_forge_distillation_run
          ON forge_distillation_records(run_id);

        CREATE TABLE IF NOT EXISTS forge_learning_lessons (
          lesson_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          category TEXT NOT NULL,
          lesson TEXT NOT NULL,
          evidence_json TEXT DEFAULT '{}',
          confidence TEXT DEFAULT 'low',
          promoted_to_memory INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_lessons_project
          ON forge_learning_lessons(project_id, category, confidence);

        CREATE TABLE IF NOT EXISTS forge_preference_pairs (
          pair_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          context_json TEXT DEFAULT '{}',
          preferred_json TEXT DEFAULT '{}',
          rejected_json TEXT DEFAULT '{}',
          reason TEXT,
          confidence TEXT DEFAULT 'low',
          approved_for_training INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_preference_pairs_project
          ON forge_preference_pairs(project_id, confidence);

        CREATE TABLE IF NOT EXISTS forge_skill_update_proposals (
          proposal_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          skill_id TEXT NOT NULL,
          proposed_change_json TEXT DEFAULT '{}',
          reason TEXT,
          evidence_json TEXT DEFAULT '{}',
          confidence TEXT DEFAULT 'low',
          status TEXT DEFAULT 'NEW',
          created_at TEXT NOT NULL,
          applied_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_skill_proposals_project
          ON forge_skill_update_proposals(project_id, status);

        CREATE TABLE IF NOT EXISTS forge_evaluation_cases (
          eval_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          eval_type TEXT NOT NULL,
          input_json TEXT DEFAULT '{}',
          expected_json TEXT DEFAULT '{}',
          negative_case_json TEXT DEFAULT '{}',
          source TEXT DEFAULT 'run',
          confidence TEXT DEFAULT 'low',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_eval_cases_project
          ON forge_evaluation_cases(project_id, eval_type);

        CREATE TABLE IF NOT EXISTS forge_learning_datasets (
          dataset_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          name TEXT,
          dataset_type TEXT DEFAULT 'jsonl',
          filters_json TEXT DEFAULT '{}',
          record_count INTEGER DEFAULT 0,
          export_path TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_learning_datasets_project
          ON forge_learning_datasets(project_id, created_at);

        CREATE TABLE IF NOT EXISTS forge_training_runs (
          training_run_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          dataset_id TEXT,
          model_type TEXT NOT NULL,
          base_model TEXT,
          training_method TEXT DEFAULT 'rule_augmented',
          status TEXT DEFAULT 'CREATED',
          config_json TEXT DEFAULT '{}',
          metrics_json TEXT DEFAULT '{}',
          logs_path TEXT,
          output_path TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_training_runs_project
          ON forge_training_runs(project_id, status, created_at);

        CREATE TABLE IF NOT EXISTS forge_model_versions (
          model_version_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          training_run_id TEXT,
          model_type TEXT NOT NULL,
          base_model TEXT,
          model_path TEXT,
          adapter_path TEXT,
          version_label TEXT,
          status TEXT DEFAULT 'CANDIDATE',
          eval_score REAL,
          promoted INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_model_versions_project
          ON forge_model_versions(project_id, model_type, status);

        CREATE TABLE IF NOT EXISTS forge_model_evaluations (
          evaluation_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          model_version_id TEXT,
          eval_dataset_id TEXT,
          eval_type TEXT,
          score_json TEXT DEFAULT '{}',
          passed INTEGER DEFAULT 0,
          failure_reasons_json TEXT DEFAULT '[]',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_model_evaluations_project
          ON forge_model_evaluations(project_id, model_version_id);

        CREATE TABLE IF NOT EXISTS forge_model_promotions (
          promotion_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          model_version_id TEXT NOT NULL,
          previous_model_version_id TEXT,
          promoted_by TEXT,
          reason TEXT,
          created_at TEXT NOT NULL,
          rolled_back_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_forge_model_promotions_project
          ON forge_model_promotions(project_id, model_version_id);

        CREATE TABLE IF NOT EXISTS forge_training_dataset_checks (
          check_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          dataset_id TEXT,
          result TEXT,
          issues_json TEXT DEFAULT '[]',
          record_count INTEGER DEFAULT 0,
          approved_count INTEGER DEFAULT 0,
          rejected_count INTEGER DEFAULT 0,
          secret_scan_passed INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_dataset_checks_project
          ON forge_training_dataset_checks(project_id, dataset_id);

        CREATE TABLE IF NOT EXISTS forge_memory_graph_nodes (
          node_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          node_type TEXT NOT NULL,
          source_id TEXT,
          title TEXT,
          summary TEXT,
          payload_json TEXT DEFAULT '{}',
          confidence TEXT DEFAULT 'medium',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_used_at TEXT,
          usage_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_forge_mg_nodes_project
          ON forge_memory_graph_nodes(project_id, node_type);
        CREATE INDEX IF NOT EXISTS idx_forge_mg_nodes_source
          ON forge_memory_graph_nodes(project_id, node_type, source_id);

        CREATE TABLE IF NOT EXISTS forge_memory_graph_edges (
          edge_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          from_node_id TEXT NOT NULL,
          to_node_id TEXT NOT NULL,
          edge_type TEXT NOT NULL,
          weight REAL DEFAULT 1.0,
          evidence_json TEXT DEFAULT '{}',
          created_at TEXT NOT NULL,
          last_reinforced_at TEXT,
          reinforcement_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_forge_mg_edges_from
          ON forge_memory_graph_edges(project_id, from_node_id);
        CREATE INDEX IF NOT EXISTS idx_forge_mg_edges_to
          ON forge_memory_graph_edges(project_id, to_node_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_forge_mg_edges_uniq
          ON forge_memory_graph_edges(project_id, from_node_id, to_node_id, edge_type);

        CREATE TABLE IF NOT EXISTS forge_context_packets (
          packet_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          stage TEXT,
          goal TEXT,
          selected_nodes_json TEXT DEFAULT '[]',
          selected_edges_json TEXT DEFAULT '[]',
          selected_skills_json TEXT DEFAULT '[]',
          selected_models_json TEXT DEFAULT '[]',
          included_files_json TEXT DEFAULT '[]',
          excluded_reason_json TEXT DEFAULT '[]',
          final_context_json TEXT DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_context_packets_project
          ON forge_context_packets(project_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_forge_context_packets_run
          ON forge_context_packets(run_id, stage);

        CREATE TABLE IF NOT EXISTS forge_advisory_events (
          advisory_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          stage TEXT,
          model_version_id TEXT,
          advisory_type TEXT,
          input_summary_json TEXT DEFAULT '{}',
          advice_json TEXT DEFAULT '{}',
          rule_result_json TEXT DEFAULT '{}',
          agreement TEXT,
          confidence REAL,
          used_by_agent INTEGER DEFAULT 0,
          overridden_by_rule INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_advisory_project
          ON forge_advisory_events(project_id, advisory_type, created_at);

        CREATE TABLE IF NOT EXISTS forge_cognitive_events (
          event_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          event_type TEXT NOT NULL,
          title TEXT,
          details_json TEXT DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_cognitive_project
          ON forge_cognitive_events(project_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_forge_cognitive_run
          ON forge_cognitive_events(run_id, created_at);

        CREATE TABLE IF NOT EXISTS forge_memory_consolidation_runs (
          consolidation_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          trigger_type TEXT,
          input_count INTEGER DEFAULT 0,
          nodes_created INTEGER DEFAULT 0,
          edges_created INTEGER DEFAULT 0,
          edges_reinforced INTEGER DEFAULT 0,
          memories_promoted INTEGER DEFAULT 0,
          contradictions_found INTEGER DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_consolidation_project
          ON forge_memory_consolidation_runs(project_id, created_at);

        CREATE TABLE IF NOT EXISTS forge_stage_context_usage (
          usage_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          run_id TEXT,
          stage TEXT,
          packet_id TEXT,
          agent_name TEXT,
          memory_nodes_used INTEGER DEFAULT 0,
          skills_used INTEGER DEFAULT 0,
          helper_models_consulted INTEGER DEFAULT 0,
          outcome_status TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_stage_usage_project
          ON forge_stage_context_usage(project_id, run_id);

        CREATE TABLE IF NOT EXISTS forge_v5_artifacts (
          artifact_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          artifact_type TEXT NOT NULL,
          status TEXT DEFAULT 'available',
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_v5_artifacts_project
          ON forge_v5_artifacts(project_id, artifact_type, updated_at);

        CREATE TABLE IF NOT EXISTS forge_v5_goals (
          goal_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT,
          status TEXT DEFAULT 'proposed',
          priority INTEGER DEFAULT 50,
          risk_level TEXT DEFAULT 'low',
          approval_required INTEGER DEFAULT 1,
          backlog_id TEXT,
          run_id TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_v5_goals_project
          ON forge_v5_goals(project_id, status, priority);

        CREATE TABLE IF NOT EXISTS forge_v5_quality_gates (
          quality_gate_id TEXT PRIMARY KEY,
          goal_id TEXT NOT NULL,
          project_id TEXT,
          run_id TEXT,
          status TEXT DEFAULT 'partial',
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forge_v5_quality_goal
          ON forge_v5_quality_gates(goal_id, updated_at);
      `)
      this._migrateBacklogSkillRoutingColumns()
      this.backend = 'sqlite'
      this.lastError = null
    } catch (err) {
      this._degrade(err)
    }
  }

  // TQ-2: additive columns on an already-shipped table. SQLite has no
  // `ADD COLUMN IF NOT EXISTS`, so each ALTER is attempted and a "duplicate
  // column" failure (already migrated) is swallowed; any other error is not.
  _migrateBacklogSkillRoutingColumns() {
    const existing = new Set(this._db.prepare('PRAGMA table_info(forge_backlog)').all().map(c => c.name))
    if (!existing.has('assigned_skill_id')) {
      this._db.exec('ALTER TABLE forge_backlog ADD COLUMN assigned_skill_id TEXT')
    }
    if (!existing.has('match_score')) {
      this._db.exec('ALTER TABLE forge_backlog ADD COLUMN match_score REAL')
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
           acceptance_criteria, linked_files, assigned_skill_id, match_score,
           created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        item.backlog_id, item.project_id, item.title || '', item.description || '',
        item.priority ?? 50, item.category || 'FEATURE', item.status || 'IDEA',
        item.risk_level || 'low', item.estimated_complexity || null,
        JSON.stringify(item.dependencies || []), item.source || 'manual',
        item.linked_run_id || null, item.acceptance_criteria || null,
        JSON.stringify(item.linked_files || []),
        item.assigned_skill_id || null, item.match_score ?? null,
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

  // ── Autopilot sessions (durable — TQ-1: previously an in-process Map, lost on restart) ──────
  _rowToAutopilotSession(r) {
    if (!r) return null
    return {
      active: !!r.active,
      runsCompleted: r.runs_completed,
      consecutiveFails: r.consecutive_fails,
      maxRuns: r.max_runs,
      autonomyLevel: r.autonomy_level,
      cycleId: r.cycle_id || null,
      currentRunId: r.current_run_id || null,
      startedAt: r.started_at,
    }
  }

  upsertAutopilotSession(projectId, session = {}) {
    this._ensureDb()
    if (!this._db) return session
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_autopilot_sessions
          (project_id, active, runs_completed, consecutive_fails, max_runs, autonomy_level,
           cycle_id, current_run_id, started_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        projectId,
        session.active ? 1 : 0,
        session.runsCompleted ?? 0,
        session.consecutiveFails ?? 0,
        session.maxRuns ?? 10,
        session.autonomyLevel ?? 2,
        session.cycleId || null,
        session.currentRunId || null,
        session.startedAt || nowIso(),
        nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return session
  }

  getAutopilotSession(projectId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_autopilot_sessions WHERE project_id = ?').get(projectId)
      return this._rowToAutopilotSession(r)
    } catch (err) { this._degrade(err); return null }
  }

  getAllActiveAutopilotSessions() {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare('SELECT * FROM forge_autopilot_sessions WHERE active = 1').all()
        .map(r => ({ projectId: r.project_id, ...this._rowToAutopilotSession(r) }))
    } catch (err) { this._degrade(err); return [] }
  }

  deleteAutopilotSession(projectId) {
    this._ensureDb()
    if (!this._db) return
    try { this._db.prepare('DELETE FROM forge_autopilot_sessions WHERE project_id = ?').run(projectId) }
    catch (err) { this._degrade(err) }
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

  // ── Phase 7 — Learning / Distillation ────────────────────────────────────

  upsertDistillationRecord(rec) {
    this._ensureDb()
    if (!this._db) return rec
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_distillation_records
          (distill_id, project_id, run_id, goal, stack_json, trajectory_summary_json,
           outcome_summary_json, scores_json, lessons_json, preference_pairs_json,
           skill_proposals_json, eval_cases_json, confidence, approved_for_training,
           created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        rec.distill_id, rec.project_id, rec.run_id, rec.goal || '',
        JSON.stringify(rec.stack || {}), JSON.stringify(rec.trajectory_summary || {}),
        JSON.stringify(rec.outcome_summary || {}), JSON.stringify(rec.scores || {}),
        JSON.stringify(rec.lessons || []), JSON.stringify(rec.preference_pairs || []),
        JSON.stringify(rec.skill_proposals || []), JSON.stringify(rec.eval_cases || []),
        rec.confidence || 'low', rec.approved_for_training ? 1 : 0,
        rec.created_at || now, now,
      )
    } catch (err) { this._degrade(err) }
    return rec
  }

  findDistillationByRun(runId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_distillation_records WHERE run_id = ?').get(runId)
      if (!r) return null
      return this._parseDistillRow(r)
    } catch (err) { this._degrade(err); return null }
  }

  getDistillationRecords(projectId, limit = 50) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_distillation_records WHERE project_id = ? ORDER BY created_at DESC LIMIT ?'
      ).all(projectId, limit).map(r => this._parseDistillRow(r))
    } catch (err) { this._degrade(err); return [] }
  }

  _parseDistillRow(r) {
    const p = k => { try { return JSON.parse(r[k]) } catch { return {} } }
    const pa = k => { try { return JSON.parse(r[k]) } catch { return [] } }
    return {
      ...r,
      stack: p('stack_json'), trajectory_summary: p('trajectory_summary_json'),
      outcome_summary: p('outcome_summary_json'), scores: p('scores_json'),
      lessons: pa('lessons_json'), preference_pairs: pa('preference_pairs_json'),
      skill_proposals: pa('skill_proposals_json'), eval_cases: pa('eval_cases_json'),
      approved_for_training: !!r.approved_for_training,
    }
  }

  upsertLesson(lesson) {
    this._ensureDb()
    if (!this._db) return lesson
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_learning_lessons
          (lesson_id, project_id, run_id, category, lesson, evidence_json, confidence,
           promoted_to_memory, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
      `).run(
        lesson.lesson_id, lesson.project_id, lesson.run_id || null,
        lesson.category || 'planning', lesson.lesson,
        JSON.stringify(lesson.evidence || {}),
        lesson.confidence || 'low', lesson.promoted_to_memory ? 1 : 0,
        lesson.created_at || now,
      )
    } catch (err) { this._degrade(err) }
    return lesson
  }

  getLessons(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_learning_lessons WHERE project_id = ?'
      const args = [projectId]
      if (opts.category) { q += ' AND category = ?'; args.push(opts.category) }
      if (opts.promoted === false) { q += ' AND promoted_to_memory = 0' }
      if (opts.promoted === true) { q += ' AND promoted_to_memory = 1' }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 100)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        evidence: (() => { try { return JSON.parse(r.evidence_json) } catch { return {} } })(),
        promoted_to_memory: !!r.promoted_to_memory,
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  markLessonPromoted(lessonId) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare('UPDATE forge_learning_lessons SET promoted_to_memory = 1 WHERE lesson_id = ?').run(lessonId)
    } catch (err) { this._degrade(err) }
  }

  upsertPreferencePair(pair) {
    this._ensureDb()
    if (!this._db) return pair
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_preference_pairs
          (pair_id, project_id, run_id, context_json, preferred_json, rejected_json,
           reason, confidence, approved_for_training, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        pair.pair_id, pair.project_id, pair.run_id || null,
        JSON.stringify(pair.context || {}), JSON.stringify(pair.preferred || {}),
        JSON.stringify(pair.rejected || {}), pair.reason || '',
        pair.confidence || 'low', pair.approved_for_training ? 1 : 0,
        pair.created_at || now,
      )
    } catch (err) { this._degrade(err) }
    return pair
  }

  getPreferencePairs(projectId, limit = 100) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_preference_pairs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?'
      ).all(projectId, limit).map(r => ({
        ...r,
        context: (() => { try { return JSON.parse(r.context_json) } catch { return {} } })(),
        preferred: (() => { try { return JSON.parse(r.preferred_json) } catch { return {} } })(),
        rejected: (() => { try { return JSON.parse(r.rejected_json) } catch { return {} } })(),
        approved_for_training: !!r.approved_for_training,
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  updatePreferencePair(pairId, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_preference_pairs WHERE pair_id = ?').get(pairId)
      if (!r) return null
      if (patch.approved_for_training !== undefined) {
        this._db.prepare('UPDATE forge_preference_pairs SET approved_for_training = ? WHERE pair_id = ?')
          .run(patch.approved_for_training ? 1 : 0, pairId)
      }
      return this._db.prepare('SELECT * FROM forge_preference_pairs WHERE pair_id = ?').get(pairId)
    } catch (err) { this._degrade(err); return null }
  }

  upsertSkillProposal(proposal) {
    this._ensureDb()
    if (!this._db) return proposal
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_skill_update_proposals
          (proposal_id, project_id, run_id, skill_id, proposed_change_json, reason,
           evidence_json, confidence, status, created_at, applied_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        proposal.proposal_id, proposal.project_id, proposal.run_id || null,
        proposal.skill_id, JSON.stringify(proposal.proposed_change || {}),
        proposal.reason || '', JSON.stringify(proposal.evidence || {}),
        proposal.confidence || 'low', proposal.status || 'NEW',
        proposal.created_at || now, proposal.applied_at || null,
      )
    } catch (err) { this._degrade(err) }
    return proposal
  }

  getSkillProposals(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_skill_update_proposals WHERE project_id = ?'
      const args = [projectId]
      if (opts.status) { q += ' AND status = ?'; args.push(opts.status) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 100)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        proposed_change: (() => { try { return JSON.parse(r.proposed_change_json) } catch { return {} } })(),
        evidence: (() => { try { return JSON.parse(r.evidence_json) } catch { return {} } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  updateSkillProposal(proposalId, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_skill_update_proposals WHERE proposal_id = ?').get(proposalId)
      if (!r) return null
      const allowed = ['status', 'applied_at', 'reason']
      const sets = []
      const args = []
      for (const k of allowed) {
        if (patch[k] !== undefined) { sets.push(`${k} = ?`); args.push(patch[k]) }
      }
      if (!sets.length) return r
      args.push(proposalId)
      this._db.prepare(`UPDATE forge_skill_update_proposals SET ${sets.join(', ')} WHERE proposal_id = ?`).run(...args)
      return this._db.prepare('SELECT * FROM forge_skill_update_proposals WHERE proposal_id = ?').get(proposalId)
    } catch (err) { this._degrade(err); return null }
  }

  upsertEvalCase(ec) {
    this._ensureDb()
    if (!this._db) return ec
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_evaluation_cases
          (eval_id, project_id, run_id, eval_type, input_json, expected_json,
           negative_case_json, source, confidence, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        ec.eval_id, ec.project_id, ec.run_id || null, ec.eval_type || 'planner_eval',
        JSON.stringify(ec.input || {}), JSON.stringify(ec.expected || {}),
        JSON.stringify(ec.negative_case || {}), ec.source || 'run',
        ec.confidence || 'low', ec.created_at || now,
      )
    } catch (err) { this._degrade(err) }
    return ec
  }

  getEvalCases(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_evaluation_cases WHERE project_id = ?'
      const args = [projectId]
      if (opts.eval_type) { q += ' AND eval_type = ?'; args.push(opts.eval_type) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 100)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        input: (() => { try { return JSON.parse(r.input_json) } catch { return {} } })(),
        expected: (() => { try { return JSON.parse(r.expected_json) } catch { return {} } })(),
        negative_case: (() => { try { return JSON.parse(r.negative_case_json) } catch { return {} } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  upsertLearningDataset(ds) {
    this._ensureDb()
    if (!this._db) return ds
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_learning_datasets
          (dataset_id, project_id, name, dataset_type, filters_json, record_count, export_path, created_at)
        VALUES (?,?,?,?,?,?,?,?)
      `).run(
        ds.dataset_id, ds.project_id, ds.name || 'export',
        ds.dataset_type || 'jsonl', JSON.stringify(ds.filters || {}),
        ds.record_count || 0, ds.export_path || null, ds.created_at || now,
      )
    } catch (err) { this._degrade(err) }
    return ds
  }

  getLearningDatasets(projectId) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_learning_datasets WHERE project_id = ? ORDER BY created_at DESC LIMIT 50'
      ).all(projectId).map(r => ({
        ...r,
        filters: (() => { try { return JSON.parse(r.filters_json) } catch { return {} } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  getLearningSummary(projectId) {
    this._ensureDb()
    if (!this._db) return { records: 0, lessons: 0, preference_pairs: 0, eval_cases: 0, skill_proposals: 0, datasets: 0, pending_proposals: 0 }
    try {
      const count = (q, ...args) => this._db.prepare(q).get(...args)?.cnt || 0
      return {
        records: count('SELECT COUNT(*) as cnt FROM forge_distillation_records WHERE project_id = ?', projectId),
        lessons: count('SELECT COUNT(*) as cnt FROM forge_learning_lessons WHERE project_id = ?', projectId),
        preference_pairs: count('SELECT COUNT(*) as cnt FROM forge_preference_pairs WHERE project_id = ?', projectId),
        eval_cases: count('SELECT COUNT(*) as cnt FROM forge_evaluation_cases WHERE project_id = ?', projectId),
        skill_proposals: count('SELECT COUNT(*) as cnt FROM forge_skill_update_proposals WHERE project_id = ?', projectId),
        pending_proposals: count("SELECT COUNT(*) as cnt FROM forge_skill_update_proposals WHERE project_id = ? AND status = 'NEW'", projectId),
        datasets: count('SELECT COUNT(*) as cnt FROM forge_learning_datasets WHERE project_id = ?', projectId),
      }
    } catch (err) { this._degrade(err); return { records: 0, lessons: 0, preference_pairs: 0, eval_cases: 0, skill_proposals: 0, datasets: 0, pending_proposals: 0 } }
  }

  // ── Phase 8 — Local Model Training ────────────────────────────────────────

  upsertTrainingRun(tr) {
    this._ensureDb()
    if (!this._db) return tr
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_training_runs
          (training_run_id, project_id, dataset_id, model_type, base_model, training_method,
           status, config_json, metrics_json, logs_path, output_path,
           created_at, started_at, finished_at, error)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        tr.training_run_id, tr.project_id, tr.dataset_id || null,
        tr.model_type, tr.base_model || null, tr.training_method || 'rule_augmented',
        tr.status || 'CREATED', JSON.stringify(tr.config || {}), JSON.stringify(tr.metrics || {}),
        tr.logs_path || null, tr.output_path || null,
        tr.created_at || nowIso(), tr.started_at || null, tr.finished_at || null, tr.error || null,
      )
    } catch (err) { this._degrade(err) }
    return tr
  }

  findTrainingRun(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_training_runs WHERE training_run_id = ?').get(id)
      return r ? this._parseTrainingRow(r) : null
    } catch (err) { this._degrade(err); return null }
  }

  _parseTrainingRow(r) {
    return {
      ...r,
      config: (() => { try { return JSON.parse(r.config_json) } catch { return {} } })(),
      metrics: (() => { try { return JSON.parse(r.metrics_json) } catch { return {} } })(),
    }
  }

  getTrainingRuns(projectId, limit = 100) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare(
        'SELECT * FROM forge_training_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?'
      ).all(projectId, limit).map(r => this._parseTrainingRow(r))
    } catch (err) { this._degrade(err); return [] }
  }

  updateTrainingRun(id, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const existing = this.findTrainingRun(id)
      if (!existing) return null
      const merged = { ...existing, ...patch }
      if (patch.config) merged.config = patch.config
      if (patch.metrics) merged.metrics = patch.metrics
      return this.upsertTrainingRun(merged)
    } catch (err) { this._degrade(err); return null }
  }

  upsertModelVersion(mv) {
    this._ensureDb()
    if (!this._db) return mv
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_model_versions
          (model_version_id, project_id, training_run_id, model_type, base_model,
           model_path, adapter_path, version_label, status, eval_score, promoted, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        mv.model_version_id, mv.project_id, mv.training_run_id || null,
        mv.model_type, mv.base_model || null, mv.model_path || null, mv.adapter_path || null,
        mv.version_label || null, mv.status || 'CANDIDATE',
        mv.eval_score ?? null, mv.promoted ? 1 : 0, mv.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return mv
  }

  findModelVersion(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_model_versions WHERE model_version_id = ?').get(id)
      return r ? { ...r, promoted: !!r.promoted } : null
    } catch (err) { this._degrade(err); return null }
  }

  getModelVersions(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_model_versions WHERE project_id = ?'
      const args = [projectId]
      if (opts.model_type) { q += ' AND model_type = ?'; args.push(opts.model_type) }
      if (opts.status) { q += ' AND status = ?'; args.push(opts.status) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 100)
      return this._db.prepare(q).all(...args).map(r => ({ ...r, promoted: !!r.promoted }))
    } catch (err) { this._degrade(err); return [] }
  }

  // Returns the currently ACTIVE helper model for a given type, if any
  getActiveModelVersion(projectId, modelType) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare(
        "SELECT * FROM forge_model_versions WHERE project_id = ? AND model_type = ? AND status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1"
      ).get(projectId, modelType)
      return r ? { ...r, promoted: !!r.promoted } : null
    } catch (err) { this._degrade(err); return null }
  }

  updateModelVersion(id, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const existing = this.findModelVersion(id)
      if (!existing) return null
      return this.upsertModelVersion({ ...existing, ...patch, model_version_id: id })
    } catch (err) { this._degrade(err); return null }
  }

  upsertModelEvaluation(ev) {
    this._ensureDb()
    if (!this._db) return ev
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_model_evaluations
          (evaluation_id, project_id, model_version_id, eval_dataset_id, eval_type,
           score_json, passed, failure_reasons_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
      `).run(
        ev.evaluation_id, ev.project_id, ev.model_version_id || null,
        ev.eval_dataset_id || null, ev.eval_type || null,
        JSON.stringify(ev.score || {}), ev.passed ? 1 : 0,
        JSON.stringify(ev.failure_reasons || []), ev.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return ev
  }

  getModelEvaluations(projectId, modelVersionId = null) {
    this._ensureDb()
    if (!this._db) return []
    try {
      const q = modelVersionId
        ? 'SELECT * FROM forge_model_evaluations WHERE project_id = ? AND model_version_id = ? ORDER BY created_at DESC'
        : 'SELECT * FROM forge_model_evaluations WHERE project_id = ? ORDER BY created_at DESC LIMIT 100'
      const args = modelVersionId ? [projectId, modelVersionId] : [projectId]
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        score: (() => { try { return JSON.parse(r.score_json) } catch { return {} } })(),
        failure_reasons: (() => { try { return JSON.parse(r.failure_reasons_json) } catch { return [] } })(),
        passed: !!r.passed,
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  upsertModelPromotion(p) {
    this._ensureDb()
    if (!this._db) return p
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_model_promotions
          (promotion_id, project_id, model_version_id, previous_model_version_id,
           promoted_by, reason, created_at, rolled_back_at)
        VALUES (?,?,?,?,?,?,?,?)
      `).run(
        p.promotion_id, p.project_id, p.model_version_id, p.previous_model_version_id || null,
        p.promoted_by || null, p.reason || null, p.created_at || nowIso(), p.rolled_back_at || null,
      )
    } catch (err) { this._degrade(err) }
    return p
  }

  getLatestPromotion(projectId, modelVersionId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      return this._db.prepare(
        'SELECT * FROM forge_model_promotions WHERE project_id = ? AND model_version_id = ? ORDER BY created_at DESC LIMIT 1'
      ).get(projectId, modelVersionId) || null
    } catch (err) { this._degrade(err); return null }
  }

  updateModelPromotion(id, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_model_promotions WHERE promotion_id = ?').get(id)
      if (!r) return null
      if (patch.rolled_back_at !== undefined) {
        this._db.prepare('UPDATE forge_model_promotions SET rolled_back_at = ? WHERE promotion_id = ?').run(patch.rolled_back_at, id)
      }
      return this._db.prepare('SELECT * FROM forge_model_promotions WHERE promotion_id = ?').get(id)
    } catch (err) { this._degrade(err); return null }
  }

  upsertDatasetCheck(c) {
    this._ensureDb()
    if (!this._db) return c
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_training_dataset_checks
          (check_id, project_id, dataset_id, result, issues_json, record_count,
           approved_count, rejected_count, secret_scan_passed, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        c.check_id, c.project_id, c.dataset_id || null, c.result || 'unknown',
        JSON.stringify(c.issues || []), c.record_count || 0,
        c.approved_count || 0, c.rejected_count || 0,
        c.secret_scan_passed ? 1 : 0, c.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return c
  }

  getDatasetChecks(projectId, datasetId = null) {
    this._ensureDb()
    if (!this._db) return []
    try {
      const q = datasetId
        ? 'SELECT * FROM forge_training_dataset_checks WHERE project_id = ? AND dataset_id = ? ORDER BY created_at DESC'
        : 'SELECT * FROM forge_training_dataset_checks WHERE project_id = ? ORDER BY created_at DESC LIMIT 50'
      const args = datasetId ? [projectId, datasetId] : [projectId]
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        issues: (() => { try { return JSON.parse(r.issues_json) } catch { return [] } })(),
        secret_scan_passed: !!r.secret_scan_passed,
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  getTrainingSummary(projectId) {
    this._ensureDb()
    const empty = { datasets: 0, training_runs: 0, candidates: 0, active_helpers: 0, last_eval_score: null, failed_jobs: 0 }
    if (!this._db) return empty
    try {
      const count = (q, ...args) => this._db.prepare(q).get(...args)?.cnt || 0
      const lastEval = this._db.prepare(
        'SELECT eval_score FROM forge_model_versions WHERE project_id = ? AND eval_score IS NOT NULL ORDER BY created_at DESC LIMIT 1'
      ).get(projectId)
      return {
        datasets: count('SELECT COUNT(*) as cnt FROM forge_learning_datasets WHERE project_id = ?', projectId),
        training_runs: count('SELECT COUNT(*) as cnt FROM forge_training_runs WHERE project_id = ?', projectId),
        candidates: count("SELECT COUNT(*) as cnt FROM forge_model_versions WHERE project_id = ? AND status = 'CANDIDATE'", projectId),
        active_helpers: count("SELECT COUNT(*) as cnt FROM forge_model_versions WHERE project_id = ? AND status = 'ACTIVE'", projectId),
        last_eval_score: lastEval?.eval_score ?? null,
        failed_jobs: count("SELECT COUNT(*) as cnt FROM forge_training_runs WHERE project_id = ? AND status = 'FAILED'", projectId),
      }
    } catch (err) { this._degrade(err); return empty }
  }

  // ── Phase 9 — Memory Graph, Context Engine, Cognitive Core ────────────────

  upsertGraphNode(node) {
    this._ensureDb()
    if (!this._db) return node
    const now = nowIso()
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_memory_graph_nodes
          (node_id, project_id, node_type, source_id, title, summary, payload_json,
           confidence, created_at, updated_at, last_used_at, usage_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        node.node_id, node.project_id, node.node_type, node.source_id || null,
        (node.title || '').slice(0, 500), (node.summary || '').slice(0, 2000),
        JSON.stringify(node.payload || {}), node.confidence || 'medium',
        node.created_at || now, now, node.last_used_at || null, node.usage_count || 0,
      )
    } catch (err) { this._degrade(err) }
    return node
  }

  findGraphNode(id) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare('SELECT * FROM forge_memory_graph_nodes WHERE node_id = ?').get(id)
      return r ? this._parseGraphNode(r) : null
    } catch (err) { this._degrade(err); return null }
  }

  findGraphNodeBySource(projectId, nodeType, sourceId) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const r = this._db.prepare(
        'SELECT * FROM forge_memory_graph_nodes WHERE project_id = ? AND node_type = ? AND source_id = ? LIMIT 1'
      ).get(projectId, nodeType, sourceId)
      return r ? this._parseGraphNode(r) : null
    } catch (err) { this._degrade(err); return null }
  }

  _parseGraphNode(r) {
    return { ...r, payload: (() => { try { return JSON.parse(r.payload_json) } catch { return {} } })() }
  }

  getGraphNodes(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_memory_graph_nodes WHERE project_id = ?'
      const args = [projectId]
      if (opts.node_type) { q += ' AND node_type = ?'; args.push(opts.node_type) }
      if (opts.search) { q += ' AND (title LIKE ? OR summary LIKE ?)'; args.push(`%${opts.search}%`, `%${opts.search}%`) }
      q += ' ORDER BY usage_count DESC, updated_at DESC LIMIT ?'
      args.push(opts.limit || 200)
      return this._db.prepare(q).all(...args).map(r => this._parseGraphNode(r))
    } catch (err) { this._degrade(err); return [] }
  }

  touchGraphNode(id) {
    this._ensureDb()
    if (!this._db) return
    try {
      this._db.prepare('UPDATE forge_memory_graph_nodes SET usage_count = usage_count + 1, last_used_at = ? WHERE node_id = ?').run(nowIso(), id)
    } catch (err) { this._degrade(err) }
  }

  updateGraphNode(id, patch) {
    this._ensureDb()
    if (!this._db) return null
    try {
      const existing = this.findGraphNode(id)
      if (!existing) return null
      return this.upsertGraphNode({ ...existing, ...patch, node_id: id, payload: patch.payload || existing.payload })
    } catch (err) { this._degrade(err); return null }
  }

  upsertGraphEdge(edge) {
    this._ensureDb()
    if (!this._db) return edge
    const now = nowIso()
    try {
      // Unique on (project, from, to, type) — reinforce if exists
      const existing = this._db.prepare(
        'SELECT edge_id, reinforcement_count, weight FROM forge_memory_graph_edges WHERE project_id = ? AND from_node_id = ? AND to_node_id = ? AND edge_type = ?'
      ).get(edge.project_id, edge.from_node_id, edge.to_node_id, edge.edge_type)
      if (existing) {
        this._db.prepare('UPDATE forge_memory_graph_edges SET weight = ?, last_reinforced_at = ?, reinforcement_count = reinforcement_count + 1 WHERE edge_id = ?')
          .run((existing.weight || 1) + (edge.weight || 0.5), now, existing.edge_id)
        return { ...edge, edge_id: existing.edge_id, reinforced: true }
      }
      this._db.prepare(`
        INSERT INTO forge_memory_graph_edges
          (edge_id, project_id, from_node_id, to_node_id, edge_type, weight,
           evidence_json, created_at, last_reinforced_at, reinforcement_count)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        edge.edge_id, edge.project_id, edge.from_node_id, edge.to_node_id,
        edge.edge_type, edge.weight ?? 1.0, JSON.stringify(edge.evidence || {}),
        edge.created_at || now, now, 0,
      )
    } catch (err) { this._degrade(err) }
    return edge
  }

  reinforceGraphEdge(edgeId, amount = 0.5) {
    this._ensureDb()
    if (!this._db) return null
    try {
      this._db.prepare('UPDATE forge_memory_graph_edges SET weight = weight + ?, last_reinforced_at = ?, reinforcement_count = reinforcement_count + 1 WHERE edge_id = ?')
        .run(amount, nowIso(), edgeId)
      return this._db.prepare('SELECT * FROM forge_memory_graph_edges WHERE edge_id = ?').get(edgeId) || null
    } catch (err) { this._degrade(err); return null }
  }

  getGraphEdges(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_memory_graph_edges WHERE project_id = ?'
      const args = [projectId]
      if (opts.from_node_id) { q += ' AND from_node_id = ?'; args.push(opts.from_node_id) }
      if (opts.to_node_id) { q += ' AND to_node_id = ?'; args.push(opts.to_node_id) }
      if (opts.edge_type) { q += ' AND edge_type = ?'; args.push(opts.edge_type) }
      q += ' ORDER BY weight DESC LIMIT ?'
      args.push(opts.limit || 500)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r, evidence: (() => { try { return JSON.parse(r.evidence_json) } catch { return {} } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  // Neighborhood: all edges touching nodeId (both directions) + the neighbor nodes
  getGraphNeighborhood(projectId, nodeId, depth = 1) {
    this._ensureDb()
    if (!this._db) return { nodes: [], edges: [] }
    try {
      const seen = new Set([nodeId])
      const collectedEdges = []
      let frontier = [nodeId]
      for (let d = 0; d < Math.min(depth, 3); d++) {
        const next = []
        for (const nid of frontier) {
          const edges = this._db.prepare(
            'SELECT * FROM forge_memory_graph_edges WHERE project_id = ? AND (from_node_id = ? OR to_node_id = ?) ORDER BY weight DESC LIMIT 50'
          ).all(projectId, nid, nid)
          for (const e of edges) {
            collectedEdges.push({ ...e, evidence: (() => { try { return JSON.parse(e.evidence_json) } catch { return {} } })() })
            const other = e.from_node_id === nid ? e.to_node_id : e.from_node_id
            if (!seen.has(other)) { seen.add(other); next.push(other) }
          }
        }
        frontier = next
        if (!frontier.length) break
      }
      const nodes = [...seen].map(id => this.findGraphNode(id)).filter(Boolean)
      // Dedup edges by edge_id
      const edgeMap = new Map(collectedEdges.map(e => [e.edge_id, e]))
      return { nodes, edges: [...edgeMap.values()] }
    } catch (err) { this._degrade(err); return { nodes: [], edges: [] } }
  }

  getGraphSummary(projectId) {
    this._ensureDb()
    const empty = { nodes: 0, edges: 0, high_confidence: 0, contradicted: 0, by_type: {}, top_files: [], top_skills: [], failure_patterns: 0 }
    if (!this._db) return empty
    try {
      const c = (q, ...a) => this._db.prepare(q).get(...a)?.cnt || 0
      const byType = {}
      for (const row of this._db.prepare('SELECT node_type, COUNT(*) as cnt FROM forge_memory_graph_nodes WHERE project_id = ? GROUP BY node_type').all(projectId)) {
        byType[row.node_type] = row.cnt
      }
      const topFiles = this._db.prepare(
        "SELECT n.title, n.usage_count, COUNT(e.edge_id) as links FROM forge_memory_graph_nodes n LEFT JOIN forge_memory_graph_edges e ON (e.from_node_id = n.node_id OR e.to_node_id = n.node_id) WHERE n.project_id = ? AND n.node_type = 'file' GROUP BY n.node_id ORDER BY links DESC LIMIT 8"
      ).all(projectId)
      const topSkills = this._db.prepare(
        "SELECT n.title, n.usage_count FROM forge_memory_graph_nodes n WHERE n.project_id = ? AND n.node_type = 'skill' ORDER BY n.usage_count DESC LIMIT 8"
      ).all(projectId)
      return {
        nodes: c('SELECT COUNT(*) as cnt FROM forge_memory_graph_nodes WHERE project_id = ?', projectId),
        edges: c('SELECT COUNT(*) as cnt FROM forge_memory_graph_edges WHERE project_id = ?', projectId),
        high_confidence: c("SELECT COUNT(*) as cnt FROM forge_memory_graph_nodes WHERE project_id = ? AND confidence = 'high'", projectId),
        contradicted: c("SELECT COUNT(*) as cnt FROM forge_memory_graph_edges WHERE project_id = ? AND edge_type = 'contradicts'", projectId),
        by_type: byType,
        top_files: topFiles,
        top_skills: topSkills,
        failure_patterns: c("SELECT COUNT(*) as cnt FROM forge_memory_graph_nodes WHERE project_id = ? AND node_type = 'failure_pattern'", projectId),
      }
    } catch (err) { this._degrade(err); return empty }
  }

  // ── Context packets ────────────────────────────────────────────────────────
  upsertContextPacket(p) {
    this._ensureDb()
    if (!this._db) return p
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_context_packets
          (packet_id, project_id, run_id, stage, goal, selected_nodes_json,
           selected_edges_json, selected_skills_json, selected_models_json,
           included_files_json, excluded_reason_json, final_context_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        p.packet_id, p.project_id, p.run_id || null, p.stage || null,
        (p.goal || '').slice(0, 500),
        JSON.stringify(p.selected_nodes || []), JSON.stringify(p.selected_edges || []),
        JSON.stringify(p.selected_skills || []), JSON.stringify(p.selected_models || []),
        JSON.stringify(p.included_files || []), JSON.stringify(p.excluded_reason || []),
        JSON.stringify(p.final_context || {}), p.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return p
  }

  getContextPackets(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_context_packets WHERE project_id = ?'
      const args = [projectId]
      if (opts.run_id) { q += ' AND run_id = ?'; args.push(opts.run_id) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 50)
      return this._db.prepare(q).all(...args).map(r => this._parseContextPacket(r))
    } catch (err) { this._degrade(err); return [] }
  }

  getContextPacketsForRun(runId, limit = 50) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare('SELECT * FROM forge_context_packets WHERE run_id = ? ORDER BY created_at DESC LIMIT ?')
        .all(runId, limit).map(r => this._parseContextPacket(r))
    } catch (err) { this._degrade(err); return [] }
  }

  _parseContextPacket(r) {
    const pa = k => { try { return JSON.parse(r[k]) } catch { return [] } }
    return {
      ...r,
      selected_nodes: pa('selected_nodes_json'), selected_edges: pa('selected_edges_json'),
      selected_skills: pa('selected_skills_json'), selected_models: pa('selected_models_json'),
      included_files: pa('included_files_json'), excluded_reason: pa('excluded_reason_json'),
      final_context: (() => { try { return JSON.parse(r.final_context_json) } catch { return {} } })(),
    }
  }

  // ── Advisory events ──────────────────────────────────────────────────────
  upsertAdvisoryEvent(e) {
    this._ensureDb()
    if (!this._db) return e
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_advisory_events
          (advisory_id, project_id, run_id, stage, model_version_id, advisory_type,
           input_summary_json, advice_json, rule_result_json, agreement, confidence,
           used_by_agent, overridden_by_rule, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        e.advisory_id, e.project_id, e.run_id || null, e.stage || null,
        e.model_version_id || null, e.advisory_type || null,
        JSON.stringify(e.input_summary || {}), JSON.stringify(e.advice || {}),
        JSON.stringify(e.rule_result || {}), e.agreement || 'not_applicable',
        e.confidence ?? null, e.used_by_agent ? 1 : 0, e.overridden_by_rule ? 1 : 0,
        e.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return e
  }

  getAdvisoryEvents(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_advisory_events WHERE project_id = ?'
      const args = [projectId]
      if (opts.advisory_type) { q += ' AND advisory_type = ?'; args.push(opts.advisory_type) }
      if (opts.run_id) { q += ' AND run_id = ?'; args.push(opts.run_id) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 200)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r,
        input_summary: (() => { try { return JSON.parse(r.input_summary_json) } catch { return {} } })(),
        advice: (() => { try { return JSON.parse(r.advice_json) } catch { return {} } })(),
        rule_result: (() => { try { return JSON.parse(r.rule_result_json) } catch { return {} } })(),
        used_by_agent: !!r.used_by_agent, overridden_by_rule: !!r.overridden_by_rule,
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  getAdvisoryMetrics(projectId) {
    this._ensureDb()
    const empty = { total: 0, agreement_rate: 0, helpful_disagreement_rate: 0, unsafe_disagreement_rate: 0, advisor_used_rate: 0, advisor_ignored_rate: 0, by_type: {} }
    if (!this._db) return empty
    try {
      const events = this.getAdvisoryEvents(projectId, { limit: 5000 })
      const applicable = events.filter(e => !['no_active_model', 'not_applicable'].includes(e.agreement))
      const total = applicable.length
      if (!total) return { ...empty, total: 0 }
      const agree = applicable.filter(e => e.agreement === 'agree').length
      const disagree = applicable.filter(e => e.agreement === 'disagree')
      // Unsafe disagreement: helper suggested lower risk than rule on a risk classifier
      const unsafe = disagree.filter(e => e.advisory_type === 'risk_classifier' && e.overridden_by_rule).length
      const used = applicable.filter(e => e.used_by_agent).length
      const byType = {}
      for (const e of applicable) {
        byType[e.advisory_type] = byType[e.advisory_type] || { total: 0, agree: 0 }
        byType[e.advisory_type].total++
        if (e.agreement === 'agree') byType[e.advisory_type].agree++
      }
      return {
        total,
        agreement_rate: Math.round((agree / total) * 100) / 100,
        helpful_disagreement_rate: Math.round((disagree.filter(e => e.used_by_agent).length / total) * 100) / 100,
        unsafe_disagreement_rate: Math.round((unsafe / total) * 100) / 100,
        advisor_used_rate: Math.round((used / total) * 100) / 100,
        advisor_ignored_rate: Math.round(((total - used) / total) * 100) / 100,
        by_type: byType,
      }
    } catch (err) { this._degrade(err); return empty }
  }

  // ── Cognitive events ──────────────────────────────────────────────────────
  upsertCognitiveEvent(e) {
    this._ensureDb()
    if (!this._db) return e
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_cognitive_events
          (event_id, project_id, run_id, event_type, title, details_json, created_at)
        VALUES (?,?,?,?,?,?,?)
      `).run(
        e.event_id, e.project_id, e.run_id || null, e.event_type,
        (e.title || '').slice(0, 300), JSON.stringify(e.details || {}), e.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return e
  }

  getCognitiveEvents(projectId, opts = {}) {
    this._ensureDb()
    if (!this._db) return []
    try {
      let q = 'SELECT * FROM forge_cognitive_events WHERE project_id = ?'
      const args = [projectId]
      if (opts.run_id) { q += ' AND run_id = ?'; args.push(opts.run_id) }
      if (opts.event_type) { q += ' AND event_type = ?'; args.push(opts.event_type) }
      q += ' ORDER BY created_at DESC LIMIT ?'
      args.push(opts.limit || 100)
      return this._db.prepare(q).all(...args).map(r => ({
        ...r, details: (() => { try { return JSON.parse(r.details_json) } catch { return {} } })(),
      }))
    } catch (err) { this._degrade(err); return [] }
  }

  // ── Consolidation runs ────────────────────────────────────────────────────
  upsertConsolidationRun(c) {
    this._ensureDb()
    if (!this._db) return c
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_memory_consolidation_runs
          (consolidation_id, project_id, trigger_type, input_count, nodes_created,
           edges_created, edges_reinforced, memories_promoted, contradictions_found, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
      `).run(
        c.consolidation_id, c.project_id, c.trigger_type || 'manual',
        c.input_count || 0, c.nodes_created || 0, c.edges_created || 0,
        c.edges_reinforced || 0, c.memories_promoted || 0, c.contradictions_found || 0,
        c.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return c
  }

  getConsolidationRuns(projectId, limit = 20) {
    this._ensureDb()
    if (!this._db) return []
    try {
      return this._db.prepare('SELECT * FROM forge_memory_consolidation_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?')
        .all(projectId, limit)
    } catch (err) { this._degrade(err); return [] }
  }

  // ── Stage context usage ───────────────────────────────────────────────────
  upsertStageContextUsage(u) {
    this._ensureDb()
    if (!this._db) return u
    try {
      this._db.prepare(`
        INSERT OR REPLACE INTO forge_stage_context_usage
          (usage_id, project_id, run_id, stage, packet_id, agent_name,
           memory_nodes_used, skills_used, helper_models_consulted, outcome_status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
      `).run(
        u.usage_id, u.project_id, u.run_id || null, u.stage || null,
        u.packet_id || null, u.agent_name || null,
        u.memory_nodes_used || 0, u.skills_used || 0, u.helper_models_consulted || 0,
        u.outcome_status || null, u.created_at || nowIso(),
      )
    } catch (err) { this._degrade(err) }
    return u
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

  // ── Forge V5 project runtime ─────────────────────────────────────────────

  _v5File(projectId) {
    return path.join(this.forgeHome, 'v5', `${projectId}.json`)
  }

  _loadV5Data(projectId) {
    return readJson(this._v5File(projectId), { artifacts: [], goals: [], quality_gates: [] })
  }

  _saveV5Data(projectId, data) {
    writeJson(this._v5File(projectId), {
      artifacts: asList(data.artifacts),
      goals: asList(data.goals),
      quality_gates: asList(data.quality_gates),
    })
  }

  upsertV5Artifact(artifact) {
    const now = nowIso()
    const rec = {
      artifact_id: artifact.artifact_id || `v5-artifact-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      project_id: artifact.project_id,
      artifact_type: artifact.artifact_type || artifact.type || 'artifact',
      status: artifact.status || 'available',
      payload: artifact.payload || artifact.data || {},
      created_at: artifact.created_at || now,
      updated_at: now,
    }
    this._ensureDb()
    if (this._db) {
      try {
        this._db.prepare(`
          INSERT OR REPLACE INTO forge_v5_artifacts
            (artifact_id, project_id, artifact_type, status, payload_json, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?)
        `).run(rec.artifact_id, rec.project_id, rec.artifact_type, rec.status, JSON.stringify(rec.payload), rec.created_at, rec.updated_at)
        return rec
      } catch (err) { this._degrade(err) }
    }
    const data = this._loadV5Data(rec.project_id)
    data.artifacts = [rec, ...asList(data.artifacts).filter(item => item.artifact_id !== rec.artifact_id)]
    this._saveV5Data(rec.project_id, data)
    return rec
  }

  getV5Artifacts(projectId, artifactType = null) {
    this._ensureDb()
    if (this._db) {
      try {
        const sql = artifactType
          ? 'SELECT * FROM forge_v5_artifacts WHERE project_id = ? AND artifact_type = ? ORDER BY datetime(updated_at) DESC'
          : 'SELECT * FROM forge_v5_artifacts WHERE project_id = ? ORDER BY datetime(updated_at) DESC'
        const rows = artifactType
          ? this._db.prepare(sql).all(projectId, artifactType)
          : this._db.prepare(sql).all(projectId)
        return rows.map(row => ({
          artifact_id: row.artifact_id,
          project_id: row.project_id,
          artifact_type: row.artifact_type,
          status: row.status,
          payload: (() => { try { return JSON.parse(row.payload_json) } catch { return {} } })(),
          created_at: row.created_at,
          updated_at: row.updated_at,
        }))
      } catch (err) { this._degrade(err) }
    }
    const data = this._loadV5Data(projectId)
    return asList(data.artifacts)
      .filter(item => !artifactType || item.artifact_type === artifactType)
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
  }

  getV5Artifact(projectId, artifactType) {
    return this.getV5Artifacts(projectId, artifactType)[0] || null
  }

  upsertV5Goal(goal) {
    const now = nowIso()
    const rec = {
      ...goal,
      goal_id: goal.goal_id || goal.id || `v5g-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      project_id: goal.project_id,
      title: goal.title || 'Untitled V5 goal',
      description: goal.description || '',
      status: goal.status || 'proposed',
      priority: typeof goal.priority === 'number' ? goal.priority : 50,
      risk_level: goal.risk_level || 'low',
      approval_required: goal.approval_required !== false,
      backlog_id: goal.backlog_id || null,
      run_id: goal.run_id || null,
      created_at: goal.created_at || now,
      updated_at: now,
    }
    this._ensureDb()
    if (this._db) {
      try {
        this._db.prepare(`
          INSERT OR REPLACE INTO forge_v5_goals
            (goal_id, project_id, title, description, status, priority, risk_level,
             approval_required, backlog_id, run_id, payload_json, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
          rec.goal_id, rec.project_id, rec.title, rec.description, rec.status,
          rec.priority, rec.risk_level, rec.approval_required ? 1 : 0,
          rec.backlog_id, rec.run_id, JSON.stringify(rec), rec.created_at, rec.updated_at,
        )
        return rec
      } catch (err) { this._degrade(err) }
    }
    const data = this._loadV5Data(rec.project_id)
    data.goals = [rec, ...asList(data.goals).filter(item => item.goal_id !== rec.goal_id)]
    this._saveV5Data(rec.project_id, data)
    return rec
  }

  getV5Goals(projectId) {
    this._ensureDb()
    if (this._db) {
      try {
        return this._db.prepare(
          'SELECT payload_json FROM forge_v5_goals WHERE project_id = ? ORDER BY priority DESC, datetime(created_at) ASC'
        ).all(projectId).map(row => {
          try { return JSON.parse(row.payload_json) } catch { return null }
        }).filter(Boolean)
      } catch (err) { this._degrade(err) }
    }
    return asList(this._loadV5Data(projectId).goals)
      .sort((a, b) => (b.priority || 0) - (a.priority || 0))
  }

  findV5Goal(goalId) {
    if (!goalId) return null
    this._ensureDb()
    if (this._db) {
      try {
        const row = this._db.prepare('SELECT payload_json FROM forge_v5_goals WHERE goal_id = ?').get(goalId)
        return row ? JSON.parse(row.payload_json) : null
      } catch (err) { this._degrade(err) }
    }
    const dir = path.join(this.forgeHome, 'v5')
    try {
      for (const file of fs.readdirSync(dir)) {
        if (!file.endsWith('.json')) continue
        const data = readJson(path.join(dir, file), { goals: [] })
        const found = asList(data.goals).find(item => item.goal_id === goalId)
        if (found) return found
      }
    } catch {}
    return null
  }

  updateV5Goal(goalId, patch) {
    const goal = this.findV5Goal(goalId)
    if (!goal) return null
    return this.upsertV5Goal({ ...goal, ...patch, goal_id: goalId, updated_at: nowIso() })
  }

  // Remove all V5 goals for a project so re-planning replaces rather than
  // accumulates duplicates. Returns the number of goals removed.
  clearV5Goals(projectId) {
    if (!projectId) return 0
    this._ensureDb()
    if (this._db) {
      try {
        const info = this._db.prepare('DELETE FROM forge_v5_goals WHERE project_id = ?').run(projectId)
        return info.changes || 0
      } catch (err) { this._degrade(err) }
    }
    const data = this._loadV5Data(projectId)
    const removed = asList(data.goals).length
    data.goals = []
    this._saveV5Data(projectId, data)
    return removed
  }

  upsertV5QualityGate(gate) {
    const now = nowIso()
    const rec = {
      ...gate,
      quality_gate_id: gate.quality_gate_id || `qg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      goal_id: gate.goal_id,
      project_id: gate.project_id || null,
      run_id: gate.run_id || null,
      status: gate.status || 'partial',
      created_at: gate.created_at || now,
      updated_at: now,
    }
    this._ensureDb()
    if (this._db) {
      try {
        this._db.prepare(`
          INSERT OR REPLACE INTO forge_v5_quality_gates
            (quality_gate_id, goal_id, project_id, run_id, status, payload_json, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `).run(rec.quality_gate_id, rec.goal_id, rec.project_id, rec.run_id, rec.status, JSON.stringify(rec), rec.created_at, rec.updated_at)
        return rec
      } catch (err) { this._degrade(err) }
    }
    const projectId = rec.project_id || this.findV5Goal(rec.goal_id)?.project_id
    if (!projectId) return rec
    const data = this._loadV5Data(projectId)
    data.quality_gates = [rec, ...asList(data.quality_gates).filter(item => item.quality_gate_id !== rec.quality_gate_id && item.goal_id !== rec.goal_id)]
    this._saveV5Data(projectId, data)
    return rec
  }

  getV5QualityGate(goalId) {
    this._ensureDb()
    if (this._db) {
      try {
        const row = this._db.prepare(
          'SELECT payload_json FROM forge_v5_quality_gates WHERE goal_id = ? ORDER BY datetime(updated_at) DESC LIMIT 1'
        ).get(goalId)
        return row ? JSON.parse(row.payload_json) : null
      } catch (err) { this._degrade(err) }
    }
    const goal = this.findV5Goal(goalId)
    if (!goal?.project_id) return null
    return asList(this._loadV5Data(goal.project_id).quality_gates)
      .filter(item => item.goal_id === goalId)
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))[0] || null
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
