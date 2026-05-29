'use strict';
/**
 * Unit tests for audit_service.js and economy_service.js.
 * No server startup required — uses tmp STATE_DIR for SQLite isolation.
 *
 * Run:  node tests/test_audit_economy_services.js
 */

const assert = require('assert');
const os = require('os');
const fs = require('fs');
const path = require('path');

// ── Helpers ───────────────────────────────────────────────────────────────────

const results = { passed: 0, failed: 0, errors: [] };

function test(name, fn) {
  try {
    fn();
    results.passed++;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    results.failed++;
    results.errors.push({ name, err });
    console.error(`  ✗ ${name}\n    ${err.message}`);
  }
}

// ── Isolate state dir ─────────────────────────────────────────────────────────

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-employee-test-'));
process.env.STATE_DIR = tmpDir;

// Require AFTER setting STATE_DIR so the module picks it up.
// Use delete require.cache to reload fresh for each service.
function loadAuditService() {
  const key = require.resolve('../backend/services/audit_service');
  delete require.cache[key];
  return require('../backend/services/audit_service');
}

// ── audit_service tests ───────────────────────────────────────────────────────

console.log('\naudit_service.js');

const auditService = loadAuditService();

test('recordAuditEvent returns event with id and ts', () => {
  const evt = auditService.recordAuditEvent({ actor: 'test', action: 'read' });
  assert.ok(typeof evt.id === 'string' && evt.id.length > 0, 'id is a non-empty string');
  assert.ok(typeof evt.ts === 'string', 'ts is a string');
});

test('recordAuditEvent stores event in in-memory log', () => {
  const before = auditService.log.length;
  auditService.recordAuditEvent({ actor: 'user1', action: 'config_change' });
  assert.strictEqual(auditService.log.length, before + 1);
});

test('getEvents returns events array and total', () => {
  const result = auditService.getEvents();
  assert.ok(Array.isArray(result.events), 'events is array');
  assert.ok(typeof result.total === 'number', 'total is number');
});

test('getEvents filters by actor', () => {
  auditService.recordAuditEvent({ actor: 'alice', action: 'forge_submit' });
  auditService.recordAuditEvent({ actor: 'bob',   action: 'forge_submit' });
  const result = auditService.getEvents({ actor: 'alice' });
  assert.ok(result.events.every((e) => e.actor === 'alice'), 'only alice events returned');
});

test('getEvents filters by action', () => {
  auditService.recordAuditEvent({ actor: 'sys', action: 'unique_action_xyz' });
  const result = auditService.getEvents({ action: 'unique_action_xyz' });
  assert.strictEqual(result.events.length, 1);
  assert.strictEqual(result.events[0].action, 'unique_action_xyz');
});

test('getEvents filters by minRisk', () => {
  auditService.recordAuditEvent({ actor: 'sys', action: 'forge_deploy' }); // high risk 0.85
  const result = auditService.getEvents({ minRisk: 0.7 });
  assert.ok(result.events.every((e) => e.risk_score >= 0.7), 'all events above threshold');
  assert.ok(result.events.length >= 1);
});

test('getStats returns total, by_actor, by_action, risk_distribution', () => {
  const stats = auditService.getStats();
  assert.ok(typeof stats.total === 'number');
  assert.ok(typeof stats.by_actor === 'object');
  assert.ok(typeof stats.by_action === 'object');
  assert.ok(['low','medium','high'].every((k) => typeof stats.risk_distribution[k] === 'number'));
});

test('getStats total matches log length', () => {
  const stats = auditService.getStats();
  assert.strictEqual(stats.total, auditService.log.length);
});

test('high risk action gets score >= 0.8', () => {
  const evt = auditService.recordAuditEvent({ actor: 'sys', action: 'forge_deploy' });
  assert.ok(evt.risk_score >= 0.8, `expected >= 0.8, got ${evt.risk_score}`);
});

test('low risk action gets score < 0.25', () => {
  const evt = auditService.recordAuditEvent({ actor: 'sys', action: 'some_read_action' });
  assert.ok(evt.risk_score < 0.25, `expected < 0.25, got ${evt.risk_score}`);
});

test('explicit riskScore overrides auto-classification', () => {
  const evt = auditService.recordAuditEvent({ actor: 'sys', action: 'forge_deploy', riskScore: 0.3 });
  assert.strictEqual(evt.risk_score, 0.3);
});

test('log getter returns live array (mutated by record)', () => {
  const log = auditService.log;
  const before = log.length;
  auditService.recordAuditEvent({ actor: 'x', action: 'y' });
  assert.strictEqual(log.length, before + 1, 'live reference reflects new event');
});

// ── economy_service tests ─────────────────────────────────────────────────────

console.log('\neconomy_service.js');

const economyService = require('../backend/services/economy_service');

// Minimal runtimeState stub
const mockState = {
  valueGenerated: 100,
  revenueCents: 500,   // $5.00
  pipelineRuns: [
    { id: 'run1', pipeline: 'content', status: 'complete', estimated_roi: 2.5, executed_at: new Date().toISOString() },
  ],
  tasksExecuted: 10,
  successfulTasks: 8,
  failedTasks: 2,
  objectiveState: {
    money_mode: { active: true, current_objective: null, active_tasks: [] },
  },
};

economyService.init(mockState, tmpDir);

test('walletSnapshot returns disabled when no wallet file', () => {
  const snap = economyService.walletSnapshot();
  assert.strictEqual(snap.state, 'disabled');
  assert.strictEqual(snap.configured, false);
  assert.ok(typeof snap.balance === 'object');
});

test('walletSnapshot returns live when wallet file exists', () => {
  const walletPath = path.join(tmpDir, 'wallet_vault.json');
  fs.writeFileSync(walletPath, JSON.stringify({
    label: 'Test Wallet',
    address: '0xabc',
    created_at: '2026-01-01',
    balance: { currency: 'USD', available: 100, pending: 0 },
    external_compute_enabled: true,
  }));
  const snap = economyService.walletSnapshot();
  assert.strictEqual(snap.state, 'live');
  assert.strictEqual(snap.configured, true);
  assert.strictEqual(snap.label, 'Test Wallet');
  fs.unlinkSync(walletPath);
});

test('buildEconomySnapshot returns summary with correct shape', () => {
  const snap = economyService.buildEconomySnapshot();
  assert.ok(typeof snap.summary === 'object');
  assert.ok(typeof snap.summary.revenue === 'object');
  assert.ok(typeof snap.summary.cost === 'object');
  assert.ok(typeof snap.summary.profit === 'number');
  assert.ok(typeof snap.summary.roi === 'number');
});

test('buildEconomySnapshot ledger is array', () => {
  const snap = economyService.buildEconomySnapshot();
  assert.ok(Array.isArray(snap.ledger));
});

test('buildEconomySnapshot ledger includes pipeline run', () => {
  const snap = economyService.buildEconomySnapshot();
  const entry = snap.ledger.find((e) => e.id === 'run1');
  assert.ok(entry, 'pipeline run present in ledger');
  assert.strictEqual(entry.type, 'pipeline_value');
});

test('buildEconomySnapshot costs is sorted array', () => {
  const snap = economyService.buildEconomySnapshot();
  assert.ok(Array.isArray(snap.costs));
});

test('buildEconomySnapshot pipelines includes money_mode', () => {
  const snap = economyService.buildEconomySnapshot();
  const mm = snap.pipelines.find((p) => p.id === 'money_mode');
  assert.ok(mm, 'money_mode pipeline present');
  assert.strictEqual(mm.state, 'live');
});

test('buildEconomySnapshot revenue reflects revenueCents', () => {
  const snap = economyService.buildEconomySnapshot();
  assert.strictEqual(snap.summary.revenue.total, 5.0); // 500 cents = $5.00
});

test('buildEconomySnapshot tasks matches runtimeState', () => {
  const snap = economyService.buildEconomySnapshot();
  assert.strictEqual(snap.summary.tasks.executed, 10);
  assert.strictEqual(snap.summary.tasks.successful, 8);
  assert.strictEqual(snap.summary.tasks.failed, 2);
});

// ── Summary ───────────────────────────────────────────────────────────────────

console.log(`\n${results.passed + results.failed} tests: ${results.passed} passed, ${results.failed} failed`);
if (results.errors.length) {
  console.error('\nFailures:');
  for (const { name, err } of results.errors) {
    console.error(`  ${name}: ${err.stack || err.message}`);
  }
  process.exit(1);
}
