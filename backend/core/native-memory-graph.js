'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const DEFAULT_HOME = path.join(os.homedir(), '.ai-employee');
const CURRENT_SCHEMA_VERSION = 1;

function hashId(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex').slice(0, 16);
}

function nowIso() {
  return new Date().toISOString();
}

function safeJson(value, fallback = {}) {
  if (value == null || value === '') return fallback;
  if (typeof value === 'object') return value;
  try { return JSON.parse(value); } catch { return fallback; }
}

function fileSha256(file) {
  try {
    const hash = crypto.createHash('sha256');
    hash.update(fs.readFileSync(file));
    return hash.digest('hex');
  } catch {
    return null;
  }
}

function fileSize(file) {
  try { return fs.statSync(file).size; } catch { return 0; }
}

function textTokens(text) {
  return String(text || '').toLowerCase().match(/[a-z0-9][a-z0-9_-]{1,}/g) || [];
}

function scoreText(query, text) {
  const q = [...new Set(textTokens(query).filter((token) => token.length > 2))];
  if (!q.length) return 0;
  const body = String(text || '').toLowerCase();
  const hits = q.filter((token) => body.includes(token)).length;
  return Number((hits / q.length).toFixed(4));
}

function normalizeNode(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const id = String(raw.id || raw.key || raw.name || raw.label || `node_${index}`).trim();
  if (!id) return null;
  return {
    id,
    label: String(raw.label || raw.name || raw.title || id),
    type: String(raw.type || raw.node_type || 'memory'),
    group: String(raw.group || raw.category || raw.type || 'memory').toLowerCase(),
    source: String(raw.source || raw.source_system || 'native_memory_graph'),
    confidence: Number.isFinite(Number(raw.confidence)) ? Number(raw.confidence) : 0.7,
    metadata: raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : { raw },
  };
}

function endpointId(value) {
  if (value && typeof value === 'object') return value.id || value.key || value.name || value.label || '';
  return value || '';
}

function normalizeEdge(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const source = String(endpointId(raw.source ?? raw.from)).trim();
  const target = String(endpointId(raw.target ?? raw.to)).trim();
  if (!source || !target) return null;
  const type = String(raw.type || raw.relationship || raw.predicate || 'RELATED_TO');
  return {
    id: String(raw.id || `${source}:${type}:${target}:${index}`),
    source,
    target,
    type,
    weight: Number.isFinite(Number(raw.weight ?? raw.strength ?? raw.confidence)) ? Number(raw.weight ?? raw.strength ?? raw.confidence) : 0.5,
    source_system: String(raw.source_system || raw.source || 'native_memory_graph'),
    metadata: raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : { raw },
  };
}

class NativeMemoryGraph {
  constructor(options = {}) {
    this.stateDir = path.resolve(options.stateDir || process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || DEFAULT_HOME, 'state'));
    this.repoRoot = path.resolve(options.repoRoot || path.join(__dirname, '..', '..'));
    this.dbPath = path.join(this.stateDir, 'native_memory_graph.db');
    this.backupDir = path.join(this.stateDir, 'backups', 'native-memory-graph');
    this._db = null;
    this._initError = null;
  }

  db() {
    if (this._db) return this._db;
    try {
      fs.mkdirSync(this.stateDir, { recursive: true });
      const Database = require('better-sqlite3');
      this._db = new Database(this.dbPath);
      this._db.pragma('journal_mode = WAL');
      this._db.exec(`
        CREATE TABLE IF NOT EXISTS graph_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS graph_nodes (
          id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          type TEXT NOT NULL DEFAULT 'memory',
          "group" TEXT NOT NULL DEFAULT 'memory',
          source TEXT NOT NULL DEFAULT 'native_memory_graph',
          confidence REAL NOT NULL DEFAULT 0.7,
          metadata TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS graph_edges (
          id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          target TEXT NOT NULL,
          type TEXT NOT NULL DEFAULT 'RELATED_TO',
          weight REAL NOT NULL DEFAULT 0.5,
          source_system TEXT NOT NULL DEFAULT 'native_memory_graph',
          metadata TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(source) REFERENCES graph_nodes(id) ON DELETE CASCADE,
          FOREIGN KEY(target) REFERENCES graph_nodes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_label ON graph_nodes(label);
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(type);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(type);
        CREATE TABLE IF NOT EXISTS graph_backups (
          id TEXT PRIMARY KEY,
          path TEXT NOT NULL,
          kind TEXT NOT NULL DEFAULT 'manual',
          bytes INTEGER NOT NULL DEFAULT 0,
          sha256 TEXT,
          created_at TEXT NOT NULL,
          metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS graph_maintenance_log (
          id TEXT PRIMARY KEY,
          type TEXT NOT NULL,
          ok INTEGER NOT NULL DEFAULT 1,
          message TEXT,
          metadata TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
      `);
      this._migrate();
      this._initError = null;
      return this._db;
    } catch (err) {
      this._initError = err.message;
      return null;
    }
  }

  close() {
    if (!this._db) return;
    try { this._db.close(); } catch {}
    this._db = null;
  }

  _meta(key, fallback = null) {
    const db = this.db();
    if (!db) return fallback;
    const row = db.prepare('SELECT value FROM graph_meta WHERE key = ?').get(key);
    if (!row) return fallback;
    return safeJson(row.value, row.value);
  }

  _setMeta(key, value) {
    const db = this.db();
    if (!db) return false;
    db.prepare(`
      INSERT INTO graph_meta (key, value, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
    `).run(key, JSON.stringify(value), nowIso());
    return true;
  }

  _logMaintenance(type, ok, message, metadata = {}) {
    const db = this.db();
    if (!db) return null;
    const id = `${type}_${Date.now()}_${hashId(JSON.stringify(metadata))}`;
    db.prepare(`
      INSERT INTO graph_maintenance_log (id, type, ok, message, metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(id, type, ok ? 1 : 0, message || '', JSON.stringify(metadata || {}), nowIso());
    return id;
  }

  _migrate() {
    const db = this._db;
    if (!db) return;
    const current = Number(this._meta('schema_version', 0) || 0);
    if (current > CURRENT_SCHEMA_VERSION) {
      throw new Error(`native memory graph schema ${current} is newer than runtime ${CURRENT_SCHEMA_VERSION}`);
    }
    if (current < 1) {
      this._setMeta('schema_version', 1);
      this._setMeta('schema_name', 'aeternus_native_memory_graph');
      this._setMeta('schema_created_at', nowIso());
      this._logMaintenance('migration', true, 'initialized native memory graph schema', { from: current, to: 1 });
    }
    db.pragma(`user_version = ${CURRENT_SCHEMA_VERSION}`);
  }

  upsertNode(raw) {
    const db = this.db();
    const node = normalizeNode(raw);
    if (!db || !node) return null;
    const ts = nowIso();
    db.prepare(`
      INSERT INTO graph_nodes (id, label, type, "group", source, confidence, metadata, created_at, updated_at)
      VALUES (@id, @label, @type, @group, @source, @confidence, @metadata, @created_at, @updated_at)
      ON CONFLICT(id) DO UPDATE SET
        label=excluded.label,
        type=excluded.type,
        "group"=excluded."group",
        source=excluded.source,
        confidence=excluded.confidence,
        metadata=excluded.metadata,
        updated_at=excluded.updated_at
    `).run({
      ...node,
      metadata: JSON.stringify(node.metadata || {}),
      created_at: ts,
      updated_at: ts,
    });
    return node;
  }

  hasNode(id) {
    const db = this.db();
    if (!db || !id) return false;
    return Boolean(db.prepare('SELECT 1 FROM graph_nodes WHERE id = ? LIMIT 1').get(String(id)));
  }

  upsertEdge(raw) {
    const db = this.db();
    const edge = normalizeEdge(raw);
    if (!db || !edge) return null;
    if (!this.hasNode(edge.source)) this.upsertNode({ id: edge.source, label: edge.source, type: 'entity', group: 'memory', source: edge.source_system });
    if (!this.hasNode(edge.target)) this.upsertNode({ id: edge.target, label: edge.target, type: 'entity', group: 'memory', source: edge.source_system });
    const ts = nowIso();
    db.prepare(`
      INSERT INTO graph_edges (id, source, target, type, weight, source_system, metadata, created_at, updated_at)
      VALUES (@id, @source, @target, @type, @weight, @source_system, @metadata, @created_at, @updated_at)
      ON CONFLICT(id) DO UPDATE SET
        source=excluded.source,
        target=excluded.target,
        type=excluded.type,
        weight=excluded.weight,
        source_system=excluded.source_system,
        metadata=excluded.metadata,
        updated_at=excluded.updated_at
    `).run({
      ...edge,
      metadata: JSON.stringify(edge.metadata || {}),
      created_at: ts,
      updated_at: ts,
    });
    return edge;
  }

  ingestSnapshot(snapshot = {}, source = 'snapshot') {
    const nodes = Array.isArray(snapshot.nodes) ? snapshot.nodes : [];
    const edges = Array.isArray(snapshot.links) ? snapshot.links : Array.isArray(snapshot.connections) ? snapshot.connections : [];
    let nodeCount = 0;
    let edgeCount = 0;
    for (const [index, raw] of nodes.entries()) {
      if (this.upsertNode({ ...raw, source: raw.source || source, metadata: { ...(raw.metadata || {}), source } }, index)) nodeCount += 1;
    }
    for (const [index, raw] of edges.entries()) {
      if (this.upsertEdge({ ...raw, source_system: raw.source_system || source }, index)) edgeCount += 1;
    }
    return { nodes: nodeCount, edges: edgeCount };
  }

  ingestKnowledgeEntries(entries = []) {
    let nodeCount = 0;
    let edgeCount = 0;
    for (const entry of entries) {
      const title = entry.topic || entry.title || entry.source || entry.id || 'Knowledge entry';
      const content = entry.content || entry.text || entry.summary || '';
      const id = entry.id || `knowledge_${hashId(`${title}:${content}`)}`;
      if (this.upsertNode({
        id,
        label: title,
        type: 'knowledge',
        group: 'memory',
        source: entry.source || 'knowledge_store',
        confidence: Number(entry.confidence || 0.7),
        metadata: { ...entry, content },
      })) nodeCount += 1;

      const entityMatches = String(`${title}. ${content}`).match(/\b[A-Z][A-Za-z0-9_-]+(?:\s+[A-Z][A-Za-z0-9_-]+){0,3}\b/g) || [];
      const entities = [...new Set(entityMatches.map((value) => value.trim()).filter((value) => value.length > 2))].slice(0, 8);
      for (const entity of entities) {
        const entityId = `entity_${hashId(entity.toLowerCase())}`;
        this.upsertNode({
          id: entityId,
          label: entity,
          type: 'entity',
          group: 'memory',
          source: 'knowledge_store_entity',
          confidence: 0.6,
          metadata: { extracted_from: id },
        });
        if (this.upsertEdge({
          id: `${id}:MENTIONS:${entityId}`,
          source: id,
          target: entityId,
          type: 'MENTIONS',
          weight: 0.6,
          source_system: 'knowledge_store_entity_extraction',
        })) edgeCount += 1;
      }
    }
    return { nodes: nodeCount, edges: edgeCount };
  }

  bootstrapFromState({ readKnowledgeEntries, readJson } = {}) {
    if (!this.db()) return { ok: false, error: this._initError };
    const knowledge = typeof readKnowledgeEntries === 'function' ? readKnowledgeEntries() : [];
    const graphSnapshot = typeof readJson === 'function'
      ? (readJson('brain_graph_snapshot.json') || readJson('graph_snapshot.json'))
      : null;
    const a = this.ingestKnowledgeEntries(Array.isArray(knowledge) ? knowledge : []);
    const b = graphSnapshot ? this.ingestSnapshot(graphSnapshot, 'local_graph_snapshot') : { nodes: 0, edges: 0 };
    return { ok: true, nodes_ingested: a.nodes + b.nodes, edges_ingested: a.edges + b.edges };
  }

  status() {
    const db = this.db();
    if (!db) {
      return {
        state: 'degraded',
        ready: false,
        source: 'native_memory_graph',
        backend: 'sqlite_embedded',
        extension_required: false,
        schema_version: 0,
        db_path: this.dbPath,
        node_count: 0,
        edge_count: 0,
        backup_count: 0,
        integrity: { ok: false, status: 'unavailable', errors: [this._initError || 'native graph database unavailable'] },
        degraded_reason: this._initError || 'native graph database unavailable',
      };
    }
    const nodeCount = db.prepare('SELECT COUNT(*) AS n FROM graph_nodes').get().n;
    const edgeCount = db.prepare('SELECT COUNT(*) AS n FROM graph_edges').get().n;
    const backupCount = db.prepare('SELECT COUNT(*) AS n FROM graph_backups').get().n;
    const latestBackup = db.prepare('SELECT id, path, kind, bytes, sha256, created_at FROM graph_backups ORDER BY created_at DESC LIMIT 1').get() || null;
    const integrity = this.integrityCheck({ includePragma: false });
    return {
      state: nodeCount || edgeCount ? 'live' : 'empty',
      ready: integrity.ok,
      source: 'native_memory_graph',
      backend: 'sqlite_embedded',
      extension_required: false,
      neo4j_compatible_schema: true,
      schema_version: Number(this._meta('schema_version', CURRENT_SCHEMA_VERSION) || CURRENT_SCHEMA_VERSION),
      db_path: this.dbPath,
      db_bytes: fileSize(this.dbPath),
      node_count: nodeCount,
      edge_count: edgeCount,
      backup_count: backupCount,
      latest_backup: latestBackup,
      integrity,
      degraded_reason: integrity.ok ? null : 'native graph integrity issues detected',
    };
  }

  listBackups(limit = 20) {
    const db = this.db();
    if (!db) return [];
    const safeLimit = Math.max(1, Math.min(100, Number(limit) || 20));
    return db.prepare(`
      SELECT id, path, kind, bytes, sha256, created_at, metadata
      FROM graph_backups
      ORDER BY created_at DESC
      LIMIT ?
    `).all(safeLimit).map((row) => ({ ...row, metadata: safeJson(row.metadata) }));
  }

  createBackup({ kind = 'manual', metadata = {}, maxBackups = 10 } = {}) {
    const db = this.db();
    if (!db) return { ok: false, error: this._initError || 'native graph database unavailable' };
    fs.mkdirSync(this.backupDir, { recursive: true });
    db.pragma('wal_checkpoint(TRUNCATE)');
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const id = `graph_backup_${timestamp}_${hashId(this.dbPath)}`;
    const dest = path.join(this.backupDir, `${id}.db`);
    fs.copyFileSync(this.dbPath, dest);
    const record = {
      id,
      path: dest,
      kind,
      bytes: fileSize(dest),
      sha256: fileSha256(dest),
      created_at: nowIso(),
      metadata: JSON.stringify(metadata || {}),
    };
    db.prepare(`
      INSERT INTO graph_backups (id, path, kind, bytes, sha256, created_at, metadata)
      VALUES (@id, @path, @kind, @bytes, @sha256, @created_at, @metadata)
    `).run(record);
    this._logMaintenance('backup', true, 'created native memory graph backup', { id, kind, bytes: record.bytes });
    this.pruneBackups(maxBackups);
    return { ok: true, backup: { ...record, metadata: metadata || {} } };
  }

  restoreBackup({ id, confirm, actor = 'operator' } = {}) {
    if (confirm !== 'RESTORE_NATIVE_GRAPH') {
      return { ok: false, status: 400, error: 'restore requires explicit RESTORE_NATIVE_GRAPH confirmation' };
    }
    const db = this.db();
    if (!db) return { ok: false, status: 503, error: this._initError || 'native graph database unavailable' };
    const backup = db.prepare('SELECT id, path, kind, bytes, sha256, created_at, metadata FROM graph_backups WHERE id = ?').get(String(id || ''));
    if (!backup) return { ok: false, status: 404, error: 'backup not found' };
    if (!fs.existsSync(backup.path)) return { ok: false, status: 410, error: 'backup file is missing' };
    if (backup.sha256 && fileSha256(backup.path) !== backup.sha256) {
      return { ok: false, status: 409, error: 'backup checksum mismatch' };
    }
    const preRestore = this.createBackup({
      kind: 'pre_restore',
      metadata: { actor, restoring_backup_id: backup.id },
      maxBackups: 12,
    });
    this.close();
    for (const suffix of ['', '-wal', '-shm']) {
      try { fs.unlinkSync(`${this.dbPath}${suffix}`); } catch {}
    }
    fs.copyFileSync(backup.path, this.dbPath);
    const reopened = this.db();
    if (!reopened) {
      return { ok: false, status: 500, error: this._initError || 'restored graph could not be opened', pre_restore_backup: preRestore };
    }
    const integrity = this.integrityCheck({ includePragma: true });
    this._logMaintenance('restore', integrity.ok, integrity.ok ? 'native graph restore completed' : 'native graph restore completed with integrity issues', {
      actor,
      backup_id: backup.id,
      pre_restore_backup_id: preRestore?.backup?.id || null,
      integrity,
    });
    return {
      ok: integrity.ok,
      restored_backup: { ...backup, metadata: safeJson(backup.metadata) },
      pre_restore_backup: preRestore,
      integrity,
    };
  }

  pruneBackups(maxBackups = 10) {
    const db = this.db();
    if (!db) return { removed: 0 };
    const keep = Math.max(1, Math.min(100, Number(maxBackups) || 10));
    const rows = db.prepare('SELECT id, path FROM graph_backups ORDER BY created_at DESC').all();
    const stale = rows.slice(keep);
    for (const row of stale) {
      try { fs.unlinkSync(row.path); } catch {}
      db.prepare('DELETE FROM graph_backups WHERE id = ?').run(row.id);
    }
    if (stale.length) this._logMaintenance('backup_prune', true, 'pruned native graph backups', { removed: stale.length, keep });
    return { removed: stale.length };
  }

  integrityCheck({ includePragma = true } = {}) {
    const db = this.db();
    if (!db) return { ok: false, status: 'unavailable', errors: [this._initError || 'database unavailable'] };
    const errors = [];
    let pragma = 'skipped';
    if (includePragma) {
      try {
        const rows = db.prepare('PRAGMA integrity_check').all();
        pragma = rows.map((row) => Object.values(row)[0]).join('; ');
        if (pragma !== 'ok') errors.push(`sqlite integrity_check: ${pragma}`);
      } catch (err) {
        errors.push(`sqlite integrity_check failed: ${err.message}`);
      }
    }
    const orphanEdges = db.prepare(`
      SELECT COUNT(*) AS n
      FROM graph_edges e
      LEFT JOIN graph_nodes s ON s.id = e.source
      LEFT JOIN graph_nodes t ON t.id = e.target
      WHERE s.id IS NULL OR t.id IS NULL
    `).get().n;
    if (orphanEdges) errors.push(`${orphanEdges} orphan edge(s)`);
    const invalidNodeMetadata = db.prepare('SELECT id, metadata FROM graph_nodes').all()
      .filter((row) => {
        try { JSON.parse(row.metadata || '{}'); return false; } catch { return true; }
      }).length;
    const invalidEdgeMetadata = db.prepare('SELECT id, metadata FROM graph_edges').all()
      .filter((row) => {
        try { JSON.parse(row.metadata || '{}'); return false; } catch { return true; }
      }).length;
    if (invalidNodeMetadata) errors.push(`${invalidNodeMetadata} node(s) with invalid metadata JSON`);
    if (invalidEdgeMetadata) errors.push(`${invalidEdgeMetadata} edge(s) with invalid metadata JSON`);
    return {
      ok: errors.length === 0,
      status: errors.length ? 'degraded' : 'ok',
      sqlite: pragma,
      orphan_edges: orphanEdges,
      invalid_node_metadata: invalidNodeMetadata,
      invalid_edge_metadata: invalidEdgeMetadata,
      errors,
      checked_at: nowIso(),
    };
  }

  duplicateCandidates(limit = 20) {
    const db = this.db();
    if (!db) return [];
    const rows = db.prepare(`
      SELECT id, label, type, "group", source, confidence, metadata, updated_at
      FROM graph_nodes
      ORDER BY updated_at DESC
      LIMIT 3000
    `).all();
    const groups = new Map();
    for (const row of rows) {
      const key = String(row.label || row.id).trim().toLowerCase().replace(/\s+/g, ' ');
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ ...row, metadata: safeJson(row.metadata) });
    }
    return [...groups.entries()]
      .filter(([, items]) => items.length > 1)
      .map(([label, items]) => ({
        label,
        count: items.length,
        survivor_id: items[0].id,
        candidates: items.slice(0, 12),
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, Math.max(1, Math.min(100, Number(limit) || 20)));
  }

  mergeNodes({ survivorId, duplicateIds = [], confirm, actor = 'operator' } = {}) {
    if (confirm !== 'MERGE_NATIVE_GRAPH') {
      return { ok: false, status: 400, error: 'merge requires explicit MERGE_NATIVE_GRAPH confirmation' };
    }
    const db = this.db();
    if (!db) return { ok: false, status: 503, error: this._initError || 'native graph database unavailable' };
    const survivor = db.prepare('SELECT * FROM graph_nodes WHERE id = ?').get(String(survivorId || ''));
    if (!survivor) return { ok: false, status: 404, error: 'survivor node not found' };
    const ids = [...new Set((Array.isArray(duplicateIds) ? duplicateIds : []).map(String).filter((id) => id && id !== survivor.id))];
    if (!ids.length) return { ok: false, status: 400, error: 'duplicate_ids required' };
    const backup = this.createBackup({ kind: 'pre_merge', metadata: { actor, survivor_id: survivor.id, duplicate_ids: ids } });
    let merged = 0;
    const tx = db.transaction(() => {
      for (const id of ids) {
        const dupe = db.prepare('SELECT * FROM graph_nodes WHERE id = ?').get(id);
        if (!dupe) continue;
        const edges = db.prepare('SELECT * FROM graph_edges WHERE source = ? OR target = ?').all(id, id);
        for (const edge of edges) {
          const nextSource = edge.source === id ? survivor.id : edge.source;
          const nextTarget = edge.target === id ? survivor.id : edge.target;
          if (nextSource === nextTarget) {
            db.prepare('DELETE FROM graph_edges WHERE id = ?').run(edge.id);
            continue;
          }
          const nextId = `${nextSource}:${edge.type}:${nextTarget}`;
          db.prepare(`
            INSERT INTO graph_edges (id, source, target, type, weight, source_system, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              weight=max(graph_edges.weight, excluded.weight),
              metadata=excluded.metadata,
              updated_at=excluded.updated_at
          `).run(nextId, nextSource, nextTarget, edge.type, edge.weight, edge.source_system, edge.metadata || '{}', edge.created_at || nowIso(), nowIso());
          db.prepare('DELETE FROM graph_edges WHERE id = ?').run(edge.id);
        }
        db.prepare('DELETE FROM graph_nodes WHERE id = ?').run(id);
        merged += 1;
      }
      const metadata = safeJson(survivor.metadata);
      metadata.merged_duplicate_ids = [...new Set([...(metadata.merged_duplicate_ids || []), ...ids])];
      metadata.merged_at = nowIso();
      db.prepare('UPDATE graph_nodes SET metadata = ?, updated_at = ? WHERE id = ?').run(JSON.stringify(metadata), nowIso(), survivor.id);
    });
    tx();
    const integrity = this.integrityCheck({ includePragma: true });
    const result = {
      ok: integrity.ok,
      survivor_id: survivor.id,
      merged_count: merged,
      backup,
      integrity,
    };
    this._logMaintenance('merge', result.ok, result.ok ? 'native graph merge completed' : 'native graph merge completed with integrity issues', {
      actor,
      survivor_id: survivor.id,
      duplicate_ids: ids,
      merged,
    });
    return result;
  }

  repair({ backupFirst = true } = {}) {
    const db = this.db();
    if (!db) return { ok: false, error: this._initError || 'native graph database unavailable' };
    const before = this.integrityCheck({ includePragma: true });
    const backup = backupFirst ? this.createBackup({ kind: 'pre_repair', metadata: { before } }) : null;
    const orphanEdges = db.prepare(`
      DELETE FROM graph_edges
      WHERE source NOT IN (SELECT id FROM graph_nodes)
         OR target NOT IN (SELECT id FROM graph_nodes)
    `).run().changes;
    let fixedNodeMetadata = 0;
    for (const row of db.prepare('SELECT id, metadata FROM graph_nodes').all()) {
      try { JSON.parse(row.metadata || '{}'); } catch {
        db.prepare('UPDATE graph_nodes SET metadata = ?, updated_at = ? WHERE id = ?').run('{}', nowIso(), row.id);
        fixedNodeMetadata += 1;
      }
    }
    let fixedEdgeMetadata = 0;
    for (const row of db.prepare('SELECT id, metadata FROM graph_edges').all()) {
      try { JSON.parse(row.metadata || '{}'); } catch {
        db.prepare('UPDATE graph_edges SET metadata = ?, updated_at = ? WHERE id = ?').run('{}', nowIso(), row.id);
        fixedEdgeMetadata += 1;
      }
    }
    db.pragma('wal_checkpoint(TRUNCATE)');
    const after = this.integrityCheck({ includePragma: true });
    const ok = after.ok;
    const result = {
      ok,
      backup,
      before,
      after,
      repaired: {
        orphan_edges_removed: orphanEdges,
        node_metadata_fixed: fixedNodeMetadata,
        edge_metadata_fixed: fixedEdgeMetadata,
      },
    };
    this._logMaintenance('repair', ok, ok ? 'native graph repair completed' : 'native graph repair completed with remaining issues', result.repaired);
    return result;
  }

  snapshot(limit = 250) {
    const db = this.db();
    if (!db) return { nodes: [], links: [], stats: this.status() };
    const safeLimit = Math.max(1, Math.min(1000, Number(limit) || 250));
    const nodes = db.prepare(`
      SELECT id, label, type, "group", source, confidence, metadata
      FROM graph_nodes ORDER BY updated_at DESC LIMIT ?
    `).all(safeLimit).map((row) => ({ ...row, metadata: safeJson(row.metadata) }));
    const ids = new Set(nodes.map((node) => node.id));
    const links = db.prepare(`
      SELECT id, source, target, type, weight AS strength, source_system, metadata
      FROM graph_edges ORDER BY updated_at DESC LIMIT ?
    `).all(safeLimit * 2)
      .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
      .map((row) => ({ ...row, metadata: safeJson(row.metadata) }));
    return { nodes, links, stats: this.status(), updated_at: nowIso() };
  }

  search(query, topK = 8) {
    const db = this.db();
    if (!db) return [];
    const nodeRows = db.prepare(`
      SELECT id, label, type, "group", source, confidence, metadata
      FROM graph_nodes ORDER BY updated_at DESC LIMIT 1000
    `).all();
    const edgeRows = db.prepare(`
      SELECT id, source, target, type, weight, source_system, metadata
      FROM graph_edges ORDER BY updated_at DESC LIMIT 2000
    `).all();
    const byNode = new Map(nodeRows.map((row) => [row.id, row]));
    const candidates = nodeRows.map((row) => {
      const metadata = safeJson(row.metadata);
      const content = [
        row.label,
        row.type,
        row.group,
        row.source,
        metadata.content,
        metadata.summary,
        metadata.description,
        JSON.stringify(metadata).slice(0, 900),
      ].filter(Boolean).join(' ');
      const paths = edgeRows
        .filter((edge) => edge.source === row.id || edge.target === row.id)
        .slice(0, 8)
        .map((edge) => ({
          source: edge.source,
          target: edge.target,
          type: edge.type,
          weight: edge.weight,
          source_label: byNode.get(edge.source)?.label || edge.source,
          target_label: byNode.get(edge.target)?.label || edge.target,
        }));
      return {
        id: row.id,
        title: row.label,
        content: content.replace(/\s+/g, ' ').trim().slice(0, 1200),
        source: row.source || 'native_memory_graph',
        score: scoreText(query, content),
        citation: row.id,
        paths,
      };
    }).filter((item) => item.score > 0);
    return candidates.sort((a, b) => b.score - a.score).slice(0, Math.max(1, Math.min(50, topK)));
  }
}

const instances = new Map();

function getNativeMemoryGraph(options = {}) {
  const stateDir = path.resolve(options.stateDir || process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || DEFAULT_HOME, 'state'));
  const key = `${stateDir}:${path.resolve(options.repoRoot || path.join(__dirname, '..', '..'))}`;
  if (!instances.has(key)) instances.set(key, new NativeMemoryGraph({ ...options, stateDir }));
  return instances.get(key);
}

module.exports = {
  NativeMemoryGraph,
  getNativeMemoryGraph,
  normalizeNode,
  normalizeEdge,
};
