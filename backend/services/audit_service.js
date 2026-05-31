'use strict';

// audit_service.js — owns the audit log (SQLite + in-memory mirror).
// No dependencies on server.js; server.js require()s this module.

const path = require('path');
const os = require('os');
const Database = require('better-sqlite3');

// ── State directory resolution (mirrors server.js logic) ─────────────────────
const AI_HOME = path.resolve(
  process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'),
);
const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(AI_HOME, 'state'));
const statePath = (...parts) => path.join(STATE_DIR, ...parts);

// ── Risk classification ───────────────────────────────────────────────────────
const HIGH_RISK_ACTIONS = new Set([
  'forge_deploy', 'forge_rollback', 'memory_delete', 'memory_rollback',
  'permission_override', 'economy_withdraw', 'agent_stop_all', 'security_strict_mode',
]);
const MEDIUM_RISK_ACTIONS = new Set([
  'forge_submit', 'forge_approve', 'memory_write', 'config_change',
  'agent_mode_change', 'economy_action', 'tool_execution',
]);

function _classifyRisk(action) {
  if (HIGH_RISK_ACTIONS.has(action)) return 0.85;
  if (MEDIUM_RISK_ACTIONS.has(action)) return 0.45;
  return 0.10;
}

// ── SQLite persistence ────────────────────────────────────────────────────────
const MAX_AUDIT_ENTRIES = 2000;

const _auditDb = (() => {
  const dbPath = statePath('audit.db');
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS audit_events (
      id          TEXT PRIMARY KEY,
      ts          TEXT NOT NULL,
      actor       TEXT NOT NULL,
      action      TEXT NOT NULL,
      input       TEXT NOT NULL DEFAULT '{}',
      output      TEXT NOT NULL DEFAULT '{}',
      risk_score  REAL NOT NULL DEFAULT 0,
      trace_id    TEXT NOT NULL DEFAULT '',
      meta        TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
  `);
  return db;
})();

// Prime in-memory cache from DB on startup
const _auditLog = _auditDb.prepare(
  `SELECT id,ts,actor,action,input,output,risk_score,trace_id,meta
   FROM audit_events ORDER BY ts DESC LIMIT ?`,
).all(MAX_AUDIT_ENTRIES).map((r) => ({
  ...r,
  input:  (() => { try { return JSON.parse(r.input);  } catch { return {}; } })(),
  output: (() => { try { return JSON.parse(r.output); } catch { return {}; } })(),
  meta:   (() => { try { return JSON.parse(r.meta);   } catch { return {}; } })(),
}));

const _auditInsert = _auditDb.prepare(
  `INSERT OR IGNORE INTO audit_events (id,ts,actor,action,input,output,risk_score,trace_id,meta)
   VALUES (@id,@ts,@actor,@action,@input,@output,@risk_score,@trace_id,@meta)`,
);

// ── Public API ────────────────────────────────────────────────────────────────

function recordAuditEvent({ actor, action, inputData, outputData, riskScore, traceId, meta }) {
  const score = typeof riskScore === 'number' ? Math.min(1, Math.max(0, riskScore)) : _classifyRisk(action);
  const evt = {
    id: `audit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    ts: new Date().toISOString(),
    actor:    String(actor  || 'system'),
    action:   String(action || 'unknown'),
    input:    inputData  || {},
    output:   outputData || {},
    risk_score: score,
    trace_id: traceId || '',
    meta:     meta || {},
  };
  try {
    _auditInsert.run({
      ...evt,
      input:  JSON.stringify(evt.input),
      output: JSON.stringify(evt.output),
      meta:   JSON.stringify(evt.meta),
    });
  } catch { /* non-fatal — in-memory still works */ }
  _auditLog.unshift(evt);
  if (_auditLog.length > MAX_AUDIT_ENTRIES) _auditLog.length = MAX_AUDIT_ENTRIES;
  return evt;
}

function getEvents({ limit = 100, actor = '', action = '', minRisk = 0 } = {}) {
  const cap = Math.min(500, Math.max(1, parseInt(limit) || 100));
  let events = _auditLog;
  if (actor)      events = events.filter((e) => e.actor === actor);
  if (action)     events = events.filter((e) => e.action === action);
  if (minRisk > 0) events = events.filter((e) => e.risk_score >= minRisk);
  return { events: events.slice(0, cap), total: _auditLog.length };
}

function getStats() {
  const byActor = {};
  const byAction = {};
  const riskDist = { low: 0, medium: 0, high: 0 };
  for (const evt of _auditLog) {
    byActor[evt.actor]   = (byActor[evt.actor]   || 0) + 1;
    byAction[evt.action] = (byAction[evt.action]  || 0) + 1;
    if (evt.risk_score < 0.25)      riskDist.low++;
    else if (evt.risk_score < 0.6)  riskDist.medium++;
    else                            riskDist.high++;
  }
  return { total: _auditLog.length, by_actor: byActor, by_action: byAction, risk_distribution: riskDist };
}

module.exports = {
  recordAuditEvent,
  getEvents,
  getStats,
  // Expose live array reference for backward-compat code in server.js
  // that reads _auditLog directly (e.g. error-report, system-health routes).
  get log() { return _auditLog; },
};
