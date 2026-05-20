const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Database = require('../backend/node_modules/better-sqlite3');

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aeternus-memory-router-'));
const stateDir = path.join(tmpRoot, 'state');
fs.mkdirSync(stateDir, { recursive: true });
process.env.AI_EMPLOYEE_HOME = tmpRoot;
process.env.AI_HOME = tmpRoot;
process.env.STATE_DIR = stateDir;
process.env.PYTHON_BACKEND_PORT = '9';

function writeJson(file, value) {
  fs.writeFileSync(path.join(stateDir, file), JSON.stringify(value, null, 2));
}

writeJson('vector_store.json', {
  memories: [
    {
      id: 'doc-refund',
      title: 'Refund policy',
      text: 'Refund policy for enterprise clients requires approval and audit citation.',
      metadata: { source: 'policy-doc' },
    },
  ],
});
writeJson('knowledge_store.json', [
  {
    id: 'kg-apollo',
    topic: 'Project Apollo margin dependency',
    content: 'Project Apollo is connected to Q3 APAC margins through delayed supplier onboarding.',
    source: 'knowledge-store',
  },
]);
writeJson('tasks.json', {
  tasks: {
    t1: {
      id: 't1',
      title: 'Failed import task',
      status: 'failed',
      priority: 'high',
      agent: 'agent-controller',
      created_at: '2026-05-18T10:00:00Z',
    },
  },
});
writeJson('conversations_index.json', [
  {
    id: 'conv-1',
    title: 'Launch planning',
    summary: 'User previously asked to continue launcher reliability work.',
  },
]);

const dbPath = path.join(stateDir, 'audit.db');
const db = new Database(dbPath);
db.exec('CREATE TABLE audit_events (id TEXT PRIMARY KEY, actor TEXT, action TEXT, ts TEXT);');
db.prepare('INSERT INTO audit_events (id, actor, action, ts) VALUES (?, ?, ?, ?)').run('a1', 'system', 'memory_write', '2026-05-18T10:00:00Z');
db.close();

const createHybridMemoryRouter = require('../backend/routes/hybrid-memory-router');

(async () => {
  const status = await createHybridMemoryRouter.routerStatus();
  assert.equal(status.ready, true);
  assert.equal(status.lanes.semantic_rag.ready, true);
  assert.equal(status.lanes.structured_sql.ready, true);
  assert.equal(status.lanes.episodic_session.ready, true);
  assert.equal(status.lanes.procedural_skills.ready, true);
  assert.equal(status.lanes.knowledge_graph.ready, true);
  assert.equal(status.lanes.knowledge_graph.extension_required, false);
  assert.equal(status.lanes.knowledge_graph.backend, 'native_sqlite_graph');

  const semantic = await createHybridMemoryRouter.runHybridQuery({
    query: 'what is the enterprise refund policy',
    max_tokens: 600,
  });
  assert(semantic.routes.some((route) => route.id === 'semantic_rag' && route.hits > 0));
  assert.match(semantic.context.text, /Refund policy/i);

  const graph = await createHybridMemoryRouter.runHybridQuery({
    query: 'how is Project Apollo connected to APAC margins',
    max_tokens: 600,
  });
  assert(graph.routes.some((route) => route.id === 'knowledge_graph'));
  assert.match(graph.context.text, /Project Apollo/i);
  const nativeGraphDbPath = path.join(stateDir, 'native_memory_graph.db');
  assert(fs.existsSync(nativeGraphDbPath), 'native graph db should exist');

  const nativeGraph = createHybridMemoryRouter.nativeGraph();
  const nativeStatus = nativeGraph.status();
  assert.equal(nativeStatus.schema_version, 1);
  assert.equal(nativeStatus.integrity.ok, true);
  const backup = nativeGraph.createBackup({ kind: 'test' });
  assert.equal(backup.ok, true);
  assert(fs.existsSync(backup.backup.path), 'native graph backup should exist');
  assert.equal(nativeGraph.listBackups(5).length >= 1, true);
  const blockedRestore = nativeGraph.restoreBackup({ id: backup.backup.id, confirm: 'wrong' });
  assert.equal(blockedRestore.ok, false);
  assert.equal(blockedRestore.status, 400);

  const graphDb = new Database(nativeGraphDbPath);
  graphDb.prepare('UPDATE graph_nodes SET metadata = ? WHERE id = ?').run('{broken-json', 'kg-apollo');
  graphDb.close();
  const brokenIntegrity = nativeGraph.integrityCheck({ includePragma: true });
  assert.equal(brokenIntegrity.ok, false);
  assert.equal(brokenIntegrity.invalid_node_metadata >= 1, true);
  const repair = nativeGraph.repair({ backupFirst: true });
  assert.equal(repair.ok, true);
  assert.equal(repair.after.ok, true);
  assert.equal(repair.repaired.node_metadata_fixed >= 1, true);
  const restore = nativeGraph.restoreBackup({ id: backup.backup.id, confirm: 'RESTORE_NATIVE_GRAPH', actor: 'test' });
  assert.equal(restore.ok, true);
  assert.equal(restore.integrity.ok, true);

  nativeGraph.upsertNode({ id: 'dup_a', label: 'Duplicate Entity', type: 'entity', group: 'memory' });
  nativeGraph.upsertNode({ id: 'dup_b', label: 'Duplicate Entity', type: 'entity', group: 'memory' });
  nativeGraph.upsertNode({ id: 'dup_target', label: 'Duplicate Target', type: 'entity', group: 'memory' });
  nativeGraph.upsertEdge({ source: 'dup_b', target: 'dup_target', type: 'RELATES_TO', weight: 0.8 });
  const conflicts = nativeGraph.duplicateCandidates();
  assert(conflicts.some((group) => group.candidates.some((node) => node.id === 'dup_a') && group.candidates.some((node) => node.id === 'dup_b')));
  const blockedMerge = nativeGraph.mergeNodes({ survivorId: 'dup_a', duplicateIds: ['dup_b'], confirm: 'wrong' });
  assert.equal(blockedMerge.ok, false);
  assert.equal(blockedMerge.status, 400);
  const merge = nativeGraph.mergeNodes({ survivorId: 'dup_a', duplicateIds: ['dup_b'], confirm: 'MERGE_NATIVE_GRAPH', actor: 'test' });
  assert.equal(merge.ok, true);
  assert.equal(merge.merged_count, 1);
  assert.equal(nativeGraph.hasNode('dup_b'), false);

  const structured = await createHybridMemoryRouter.runHybridQuery({
    query: 'show failed tasks today',
    max_tokens: 600,
  });
  assert(structured.routes.some((route) => route.id === 'structured_sql' && route.hits > 0));
  assert.match(structured.context.text, /failed/i);

  const sqlStatus = createHybridMemoryRouter.sqlStatus();
  const auditDb = sqlStatus.databases.find((item) => item.name === 'audit.db');
  assert(auditDb, 'audit.db should be discovered');

  const select = createHybridMemoryRouter.runReadOnlySql({
    database: auditDb.id,
    sql: 'SELECT actor, action FROM audit_events',
  });
  assert.equal(select.ok, true);
  assert.equal(select.row_count, 1);
  assert.match(select.sql, /LIMIT 100$/);

  const blocked = createHybridMemoryRouter.runReadOnlySql({
    database: auditDb.id,
    sql: 'UPDATE audit_events SET actor = "x"',
  });
  assert.equal(blocked.ok, false);
  assert.equal(blocked.status, 400);
  assert.match(blocked.error, /only SELECT\/WITH|blocked/i);

  const traces = fs.readFileSync(path.join(stateDir, 'memory_router_traces.jsonl'), 'utf8')
    .trim()
    .split('\n')
    .map((line) => JSON.parse(line));
  assert(traces.some((trace) => trace.trace_id === semantic.trace_id));

  console.log('[✓] hybrid memory router contract tests passed');
})().catch((err) => {
  console.error(err);
  process.exitCode = 1;
}).finally(() => {
  try { fs.rmSync(tmpRoot, { recursive: true, force: true }); } catch {}
});
