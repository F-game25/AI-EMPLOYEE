'use strict';

const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { getNativeMemoryGraph } = require('../core/native-memory-graph');
const { createRouteRateLimit } = require('../middleware/route-rate-limit');

const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'));
const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(AI_HOME, 'state'));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON_BACKEND_HOST = process.env.PYTHON_BACKEND_HOST || '127.0.0.1';
const PYTHON_BACKEND_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const TRACE_FILE = path.join(STATE_DIR, 'memory_router_traces.jsonl');
const SQL_AUDIT_FILE = path.join(STATE_DIR, 'memory_sql_audit.jsonl');

const ROUTES = {
  semantic: 'semantic_rag',
  graph: 'knowledge_graph',
  sql: 'structured_sql',
  episodic: 'episodic_session',
  procedural: 'procedural_skills',
};

const MAX_CONTEXT_CHARS = 12000;
const MAX_SQL_ROWS = 100;

function readJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function readJsonl(file, limit = 100) {
  try {
    return fs.readFileSync(file, 'utf8')
      .trim()
      .split('\n')
      .filter(Boolean)
      .slice(-limit)
      .map((line) => {
        try { return JSON.parse(line); } catch { return null; }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

function appendJsonl(file, item) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.appendFileSync(file, `${JSON.stringify(item)}\n`, 'utf8');
  } catch {}
}

function nowIso() {
  return new Date().toISOString();
}

function hashId(input) {
  return crypto.createHash('sha256').update(String(input)).digest('hex').slice(0, 12);
}

function tokens(text) {
  return String(text || '')
    .toLowerCase()
    .match(/[a-z0-9][a-z0-9_-]{1,}/g) || [];
}

function scoreText(query, text) {
  const q = [...new Set(tokens(query).filter((t) => t.length > 2))];
  if (!q.length) return 0;
  const body = String(text || '').toLowerCase();
  const hits = q.filter((t) => body.includes(t)).length;
  return Number((hits / q.length).toFixed(4));
}

function safeSlice(value, n = 1200) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, n);
}

function stateFile(...parts) {
  return path.join(STATE_DIR, ...parts);
}

function repoFile(...parts) {
  return path.join(REPO_ROOT, ...parts);
}

function fileExists(file) {
  try { return fs.existsSync(file); } catch { return false; }
}

function readKnowledgeEntries() {
  const repo = readJSON(repoFile('state', 'knowledge_store.json'), null);
  const home = readJSON(stateFile('knowledge_store.json'), null) || readJSON(stateFile('state', 'knowledge_store.json'), null);
  const entries = [];
  for (const store of [repo, home]) {
    if (Array.isArray(store?.entries)) entries.push(...store.entries);
    else if (Array.isArray(store)) entries.push(...store);
  }
  return entries;
}

function readStateJson(name, fallback = null) {
  return readJSON(stateFile(name), fallback);
}

function nativeGraph() {
  const graph = getNativeMemoryGraph({ stateDir: STATE_DIR, repoRoot: REPO_ROOT });
  graph.bootstrapFromState({ readKnowledgeEntries, readJson: readStateJson });
  return graph;
}

function vectorStatus() {
  const vector = readJSON(stateFile('vector_store.json'), null) || readJSON(stateFile('state', 'vector_store.json'), null);
  const knowledge = readKnowledgeEntries();
  const memories = Array.isArray(vector?.memories) ? vector.memories : [];
  const entries = Array.isArray(vector?.entries) ? vector.entries : [];
  const chromaDir = path.join(AI_HOME, 'rag_chroma');
  const itemCount = memories.length || entries.length || knowledge.length;
  return {
    state: itemCount ? 'live' : 'empty',
    ready: itemCount > 0 || fileExists(chromaDir),
    source: memories.length || entries.length ? 'local_vector_store' : (knowledge.length ? 'knowledge_store' : 'none'),
    item_count: itemCount,
    chroma_present: fileExists(chromaDir),
    degraded_reason: itemCount ? null : 'No vector or knowledge entries are indexed yet.',
  };
}

async function fetchPythonJSON(pathname, timeoutMs = 900) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}${pathname}`, { signal: ctrl.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function graphStatus() {
  const live = await fetchPythonJSON('/api/neural-brain/graph/status');
  const snapshot = await fetchPythonJSON('/api/neural-brain/graph/snapshot');
  if (snapshot) nativeGraph().ingestSnapshot(snapshot, 'python_neural_brain_snapshot');
  const status = nativeGraph().status();
  const pythonNodeCount = Number(live?.node_count ?? live?.nodes ?? 0);
  const pythonEdgeCount = Number(live?.edge_count ?? live?.links ?? 0);
  return {
    ...status,
    source: 'native_memory_graph',
    backend: 'native_sqlite_graph',
    graph_engine: 'aeternus_native_graph',
    extension_required: false,
    neo4j_native_capability: true,
    neo4j_optional: false,
    python_bridge: live ? 'online' : 'offline_or_initializing',
    python_node_count: pythonNodeCount,
    python_edge_count: pythonEdgeCount,
    degraded_reason: status.ready ? null : status.degraded_reason,
  };
}

function discoverSqlDatabases() {
  const roots = [...new Set([STATE_DIR, repoFile('state')])].filter(fileExists);
  const found = new Map();
  const scan = (dir, depth = 0) => {
    if (depth > 4) return;
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!entry.name.startsWith('.') && entry.name !== 'node_modules') scan(full, depth + 1);
        continue;
      }
      if (!/\.(db|sqlite|sqlite3)$/i.test(entry.name)) continue;
      if (/-wal$|-shm$/i.test(entry.name)) continue;
      const id = `${entry.name.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase()}_${hashId(full)}`;
      found.set(id, { id, name: entry.name, path: full });
    }
  };
  roots.forEach((root) => scan(root));
  return [...found.values()].slice(0, 40);
}

function inspectSqlDatabase(dbInfo) {
  let Database;
  try { Database = require('better-sqlite3'); } catch {
    return { ...dbInfo, state: 'degraded', tables: [], error: 'better-sqlite3 unavailable' };
  }
  try {
    const db = new Database(dbInfo.path, { readonly: true, fileMustExist: true, timeout: 1000 });
    const rows = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 100").all();
    const tables = rows.map((row) => {
      let columns = [];
      try {
        columns = db.prepare('SELECT name FROM pragma_table_info(?)').all(String(row.name)).map((col) => col.name);
      } catch {}
      return { name: row.name, columns };
    });
    db.close();
    return { ...dbInfo, state: tables.length ? 'live' : 'empty', tables };
  } catch (err) {
    return { ...dbInfo, state: 'degraded', tables: [], error: err.message };
  }
}

function sqlStatus() {
  const databases = discoverSqlDatabases().map(inspectSqlDatabase);
  return {
    state: databases.length ? 'live' : 'empty',
    ready: databases.length > 0,
    source: 'local_sqlite',
    readonly: true,
    max_rows: MAX_SQL_ROWS,
    databases,
    degraded_reason: databases.length ? null : 'No local SQLite databases were discovered.',
  };
}

function stripTrailingSemicolons(value) {
  let s = String(value || '').trim();
  while (s.endsWith(';')) s = s.slice(0, -1).trimEnd();
  return s;
}

function sqlTokens(value) {
  return String(value || '')
    .toLowerCase()
    .split(/[^a-z_]+/)
    .filter(Boolean);
}

function validateReadOnlySql(sql) {
  const cleaned = stripTrailingSemicolons(sql);
  if (!cleaned) return { ok: false, error: 'sql required' };
  if (cleaned.length > 5000) return { ok: false, error: 'sql too large' };
  if (cleaned.includes(';')) return { ok: false, error: 'multiple statements are blocked' };
  const tokens = sqlTokens(cleaned);
  if (!['select', 'with'].includes(tokens[0])) return { ok: false, error: 'only SELECT/WITH read-only queries are allowed' };
  const blocked = new Set(['insert', 'update', 'delete', 'drop', 'alter', 'create', 'replace', 'attach', 'detach', 'vacuum', 'reindex', 'pragma']);
  if (tokens.some((token) => blocked.has(token))) {
    return { ok: false, error: 'write/admin SQL keywords are blocked' };
  }
  return { ok: true, sql: tokens.includes('limit') ? cleaned : `${cleaned} LIMIT ${MAX_SQL_ROWS}` };
}

function runReadOnlySql({ database, sql, params = [] }, actor = 'operator') {
  const dbInfo = discoverSqlDatabases().find((db) => db.id === database);
  if (!dbInfo) return { ok: false, status: 404, error: 'database not found' };
  const validated = validateReadOnlySql(sql);
  const audit = {
    id: `sql_${Date.now()}_${hashId(sql)}`,
    ts: nowIso(),
    actor,
    database,
    sql: String(sql || '').slice(0, 2000),
    allowed: validated.ok,
    error: validated.error || null,
  };
  if (!validated.ok) {
    appendJsonl(SQL_AUDIT_FILE, audit);
    return { ok: false, status: 400, error: validated.error };
  }
  let Database;
  try { Database = require('better-sqlite3'); } catch {
    audit.allowed = false;
    audit.error = 'better-sqlite3 unavailable';
    appendJsonl(SQL_AUDIT_FILE, audit);
    return { ok: false, status: 503, error: audit.error };
  }
  try {
    const db = new Database(dbInfo.path, { readonly: true, fileMustExist: true, timeout: 1500 });
    const started = Date.now();
    // lgtm [js/sql-injection] validated.sql is limited to one read-only SELECT/WITH statement with write/admin keywords blocked.
    const rows = db.prepare(validated.sql).all(Array.isArray(params) ? params.slice(0, 20) : []);
    db.close();
    audit.row_count = rows.length;
    audit.ms = Date.now() - started;
    appendJsonl(SQL_AUDIT_FILE, audit);
    return { ok: true, database: dbInfo.id, sql: validated.sql, rows, row_count: rows.length, ms: audit.ms };
  } catch (err) {
    audit.allowed = false;
    audit.error = err.message;
    appendJsonl(SQL_AUDIT_FILE, audit);
    return { ok: false, status: 400, error: err.message };
  }
}

function episodicStatus() {
  const convos = readJSON(stateFile('conversations_index.json'), []);
  const memory = readJSON(stateFile('memory.json'), { recent_interactions: [] });
  return {
    state: convos.length || memory.recent_interactions?.length ? 'live' : 'empty',
    ready: true,
    source: convos.length ? 'conversations_index' : 'memory_json',
    conversation_count: convos.length,
    recent_interactions: Array.isArray(memory.recent_interactions) ? memory.recent_interactions.length : 0,
  };
}

function proceduralStatus() {
  const skills = readJSON(repoFile('runtime', 'config', 'skills_library.json'), { skills: [] });
  const agents = readJSON(repoFile('runtime', 'config', 'agent_capabilities.json'), { agents: [] });
  const workflows = readJSON(stateFile('workflow_definitions.json'), []);
  const skillList = Array.isArray(skills.skills) ? skills.skills : Array.isArray(skills) ? skills : [];
  const agentList = Array.isArray(agents.agents) ? agents.agents : Array.isArray(agents) ? agents : Object.values(agents.agents || {});
  return {
    state: skillList.length || agentList.length ? 'live' : 'empty',
    ready: skillList.length > 0,
    source: 'runtime_config',
    skill_count: skillList.length,
    agent_count: agentList.length,
    workflow_count: Array.isArray(workflows) ? workflows.length : 0,
    packs: [...new Set(skillList.map((skill) => skill.source_pack || skill.category || 'core'))].slice(0, 30),
  };
}

async function routerStatus() {
  const [graph, sql] = await Promise.all([graphStatus(), Promise.resolve(sqlStatus())]);
  const semantic = vectorStatus();
  const episodic = episodicStatus();
  const procedural = proceduralStatus();
  const lanes = {
    semantic_rag: semantic,
    knowledge_graph: graph,
    structured_sql: sql,
    episodic_session: episodic,
    procedural_skills: procedural,
  };
  const readyCount = Object.values(lanes).filter((lane) => lane.ready).length;
  const degradedReasons = Object.entries(lanes)
    .filter(([, lane]) => lane.state === 'degraded' || lane.degraded_reason)
    .map(([name, lane]) => `${name}: ${lane.degraded_reason || lane.error || 'degraded'}`);
  return {
    state: readyCount ? (degradedReasons.length ? 'degraded' : 'live') : 'empty',
    ready: readyCount > 0,
    source: 'hybrid_memory_router',
    offline_first: true,
    lanes,
    degraded: degradedReasons.length > 0,
    degradedReasons,
    updated_at: nowIso(),
  };
}

function classifyRoutes(query) {
  const q = String(query || '').toLowerCase();
  const selected = new Set();
  const reasons = {};
  const add = (route, reason) => { selected.add(route); reasons[route] = reason; };

  if (/\b(count|how many|total|average|sum|revenue|cost|ledger|wallet|schedule|audit|task status|failed tasks|completed tasks|last month|today|yesterday|between)\b/.test(q)) {
    add(ROUTES.sql, 'exact structured records or metrics requested');
  }
  if (/\b(related|relationship|connect|connected|path|dependency|depends|affect|caused|between|graph|who worked|same auditor|linked)\b/.test(q)) {
    add(ROUTES.graph, 'relationship or multi-hop reasoning requested');
  }
  if (/\b(previous|before|remember|conversation|session|as i said|continue|last time|history)\b/.test(q)) {
    add(ROUTES.episodic, 'session or conversation continuity requested');
  }
  if (/\b(skill|tool|workflow|template|agent can|how do you|procedure|process|capability|hook)\b/.test(q)) {
    add(ROUTES.procedural, 'skills, tools or workflow capability requested');
  }
  if (/\b(doc|document|knowledge|explain|what is|how does|why|policy|research|article|notes|semantic|similar|find me something)\b/.test(q)) {
    add(ROUTES.semantic, 'fuzzy semantic knowledge requested');
  }
  if (!selected.size) {
    add(ROUTES.semantic, 'default broad semantic grounding');
    add(ROUTES.episodic, 'default session continuity check');
  }
  return { routes: [...selected], reasons };
}

function semanticRetrieve(query, topK = 6) {
  const vector = readJSON(stateFile('vector_store.json'), null) || readJSON(stateFile('state', 'vector_store.json'), null);
  const memories = [
    ...(Array.isArray(vector?.memories) ? vector.memories : []),
    ...(Array.isArray(vector?.entries) ? vector.entries : []),
  ];
  const knowledge = readKnowledgeEntries().map((entry) => ({
    id: entry.id || `knowledge_${hashId(entry.content || entry.topic)}`,
    text: entry.content || entry.text || entry.summary || '',
    title: entry.topic || entry.title || entry.source || 'Knowledge entry',
    metadata: { source: entry.source || 'knowledge_store', memory_type: 'semantic' },
  }));
  const candidates = [...memories, ...knowledge].map((item, index) => {
    const text = item.text || item.content || item.value || item.summary || '';
    return {
      id: item.key || item.id || `semantic_${index}`,
      route: ROUTES.semantic,
      title: item.title || item.metadata?.title || item.key || item.id || 'Semantic memory',
      content: safeSlice(text),
      source: item.metadata?.source || item.source || 'vector_or_knowledge_store',
      score: Math.max(Number(item._score || item.score || 0), scoreText(query, text)),
      citation: item.metadata?.url || item.source || item.key || item.id || 'local-memory',
    };
  }).filter((item) => item.content && item.score > 0);
  return candidates.sort((a, b) => b.score - a.score).slice(0, topK);
}

async function graphRetrieve(query, topK = 6) {
  const snapshot = await fetchPythonJSON('/api/neural-brain/graph/snapshot', 900);
  if (snapshot) nativeGraph().ingestSnapshot(snapshot, 'python_neural_brain_snapshot');
  const nativeResults = nativeGraph().search(query, topK).map((item) => ({
    ...item,
    route: ROUTES.graph,
    source: item.source || 'native_memory_graph',
  }));
  if (nativeResults.length) return nativeResults;

  const nodes = Array.isArray(snapshot?.nodes) ? snapshot.nodes : [];
  const links = Array.isArray(snapshot?.links) ? snapshot.links : Array.isArray(snapshot?.connections) ? snapshot.connections : [];
  const nodeResults = nodes.map((node) => {
    const label = node.label || node.name || node.id;
    return {
      id: node.id || `graph_${hashId(label)}`,
      route: ROUTES.graph,
      title: label,
      content: safeSlice(`${label} ${node.type || ''} ${node.group || ''} ${node.description || ''}`),
      source: snapshot ? 'neural_brain_graph_import' : 'native_memory_graph',
      score: scoreText(query, `${label} ${node.type || ''} ${node.group || ''} ${node.description || ''}`),
      citation: node.id || label,
      paths: links
        .filter((link) => [link.source, link.target, link.from, link.to].some((x) => String(x) === String(node.id)))
        .slice(0, 4),
    };
  }).filter((item) => item.score > 0);
  if (nodeResults.length) return nodeResults.sort((a, b) => b.score - a.score).slice(0, topK);

  return readKnowledgeEntries()
    .map((entry) => ({
      id: entry.id || `graph_fallback_${hashId(entry.content || entry.topic)}`,
      route: ROUTES.graph,
      title: entry.topic || entry.title || 'Knowledge relationship candidate',
      content: safeSlice(entry.content || entry.text || ''),
      source: 'knowledge_store_graph_fallback',
      score: scoreText(query, `${entry.topic || ''} ${entry.content || ''}`) * 0.6,
      citation: entry.id || entry.source || 'knowledge-store',
      paths: [],
    }))
    .filter((item) => item.content && item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
}

function structuredRetrieve(query, topK = 6) {
  const tasks = readJSON(stateFile('tasks.json'), { tasks: {} }).tasks || {};
  const schedules = readJSON(stateFile('schedules.json'), []);
  const wallet = readJSON(stateFile('wallet_vault.json'), {});
  const audit = readJsonl(stateFile('audit.jsonl'), 50);
  const rows = [
    ...Object.values(tasks).flatMap((v) => (v && typeof v === 'object' && !v.id ? Object.values(v) : [v])).filter(Boolean).map((task) => ({
      id: task.id || task.task_id || `task_${hashId(JSON.stringify(task))}`,
      title: task.title || task.intent || task.description || 'Task record',
      content: JSON.stringify({
        status: task.status,
        priority: task.priority,
        agent: task.agent || task.owner,
        created_at: task.created_at,
        updated_at: task.updated_at,
      }),
      source: 'tasks_json',
    })),
    ...schedules.map((job) => ({ id: job.id, title: job.name || 'Schedule', content: JSON.stringify(job), source: 'schedules_json' })),
    ...(Object.keys(wallet).length ? [{ id: 'wallet', title: 'Wallet vault', content: JSON.stringify(wallet), source: 'wallet_vault' }] : []),
    ...audit.map((event, index) => ({ id: event.id || `audit_${index}`, title: event.action || event.type || 'Audit event', content: JSON.stringify(event), source: 'audit_log' })),
  ];
  return rows.map((row) => ({
    ...row,
    route: ROUTES.sql,
    score: scoreText(query, `${row.title} ${row.content}`),
    citation: row.source,
  })).filter((row) => row.score > 0).sort((a, b) => b.score - a.score).slice(0, topK);
}

function episodicRetrieve(query, topK = 6) {
  const convos = readJSON(stateFile('conversations_index.json'), []);
  const memory = readJSON(stateFile('memory.json'), { recent_interactions: [] });
  const rows = [
    ...convos.map((c) => ({
      id: c.id || `conversation_${hashId(c.title || c.summary)}`,
      title: c.title || 'Conversation',
      content: c.summary || c.full_summary || JSON.stringify(c),
      source: 'conversations_index',
    })),
    ...(Array.isArray(memory.recent_interactions) ? memory.recent_interactions : []).map((item, index) => ({
      id: item.id || item.ts || `interaction_${index}`,
      title: item.title || item.agent || 'Recent interaction',
      content: item.summary || item.message || JSON.stringify(item),
      source: 'memory_recent_interactions',
    })),
  ];
  return rows.map((row) => ({
    ...row,
    route: ROUTES.episodic,
    score: scoreText(query, `${row.title} ${row.content}`),
    citation: row.id,
  })).filter((row) => row.score > 0).sort((a, b) => b.score - a.score).slice(0, topK);
}

function proceduralRetrieve(query, topK = 8) {
  const skills = readJSON(repoFile('runtime', 'config', 'skills_library.json'), { skills: [] });
  const agents = readJSON(repoFile('runtime', 'config', 'agent_capabilities.json'), { agents: [] });
  const skillList = Array.isArray(skills.skills) ? skills.skills : Array.isArray(skills) ? skills : [];
  const agentList = Array.isArray(agents.agents) ? agents.agents : Array.isArray(agents) ? agents : Object.values(agents.agents || {});
  const rows = [
    ...skillList.map((skill) => ({
      id: skill.id || skill.name,
      title: skill.name || skill.id || 'Skill',
      content: [skill.description, skill.category, skill.source_pack, skill.prompt_hint, skill.execution_steps].filter(Boolean).join(' '),
      source: skill.source_pack || 'skills_library',
    })),
    ...agentList.map((agent) => ({
      id: agent.id || agent.name,
      title: agent.name || agent.id || 'Agent capability',
      content: [agent.description, agent.job_description, (agent.skills || []).join(' '), (agent.workflows || []).join(' ')].filter(Boolean).join(' '),
      source: 'agent_capabilities',
    })),
  ];
  return rows.map((row) => ({
    ...row,
    route: ROUTES.procedural,
    score: scoreText(query, `${row.title} ${row.content}`),
    citation: row.source,
  })).filter((row) => row.score > 0).sort((a, b) => b.score - a.score).slice(0, topK);
}

function assembleContext(query, resultsByRoute, maxTokens = 2500) {
  const maxChars = Math.min(MAX_CONTEXT_CHARS, Math.max(800, Number(maxTokens || 2500) * 4));
  const parts = [];
  let used = 0;
  for (const [route, results] of Object.entries(resultsByRoute)) {
    if (!results.length) continue;
    const header = `\n[${route}]\n`;
    if (used + header.length > maxChars) break;
    parts.push(header.trim());
    used += header.length;
    for (const item of results) {
      const line = `- ${item.title}: ${item.content} (source: ${item.citation || item.source})`;
      if (used + line.length > maxChars) break;
      parts.push(line);
      used += line.length;
    }
  }
  return {
    text: parts.join('\n'),
    estimated_tokens: Math.ceil(used / 4),
    query,
  };
}

async function runHybridQuery(payload) {
  const query = String(payload.query || '').trim();
  if (!query) return { error: 'query required' };
  const traceId = `memtrace_${Date.now()}_${hashId(query)}`;
  const started = Date.now();
  const classified = classifyRoutes(query);
  const resultsByRoute = {};
  const diagnostics = [];

  await Promise.all(classified.routes.map(async (route) => {
    try {
      if (route === ROUTES.semantic) resultsByRoute[route] = semanticRetrieve(query);
      else if (route === ROUTES.graph) resultsByRoute[route] = await graphRetrieve(query);
      else if (route === ROUTES.sql) resultsByRoute[route] = structuredRetrieve(query);
      else if (route === ROUTES.episodic) resultsByRoute[route] = episodicRetrieve(query);
      else if (route === ROUTES.procedural) resultsByRoute[route] = proceduralRetrieve(query);
      if (!resultsByRoute[route]?.length) diagnostics.push(`${route}: no matching records`);
    } catch (err) {
      resultsByRoute[route] = [];
      diagnostics.push(`${route}: ${err.message}`);
    }
  }));

  const citations = Object.values(resultsByRoute).flat().map((item) => ({
    route: item.route,
    title: item.title,
    source: item.source,
    citation: item.citation,
    score: item.score,
  }));
  const allScores = Object.values(resultsByRoute).flat().map((item) => Number(item.score || 0));
  const confidence = allScores.length ? Number((allScores.reduce((a, b) => a + b, 0) / allScores.length).toFixed(4)) : 0;
  const context = assembleContext(query, resultsByRoute, payload.max_tokens);
  const trace = {
    trace_id: traceId,
    ts: nowIso(),
    query,
    mode: payload.mode || 'operator_test',
    routes: classified.routes.map((route) => ({ id: route, reason: classified.reasons[route], hits: resultsByRoute[route]?.length || 0 })),
    results: resultsByRoute,
    context,
    citations,
    confidence,
    degraded: diagnostics.length > 0 || confidence < 0.25,
    diagnostics,
    ms: Date.now() - started,
    owner: 'main_ai_orchestrator',
    ascendforge_boundary: 'AscendForge may consume approved project context for code/build tasks, but does not own memory routing.',
  };
  appendJsonl(TRACE_FILE, trace);
  return trace;
}

function createHybridMemoryRouter(requireAuth) {
  const router = express.Router();
  const protect = requireAuth || ((_req, _res, next) => next());
  router.use(createRouteRateLimit({ keyPrefix: 'hybrid-memory', max: 120, windowMs: 60_000 }));

  router.get('/router/status', protect, async (_req, res) => {
    res.json(await routerStatus());
  });

  router.post('/router/query', protect, async (req, res) => {
    const trace = await runHybridQuery(req.body || {});
    if (trace.error) return res.status(400).json({ ok: false, error: trace.error });
    res.json({ ok: true, ...trace });
  });

  router.get('/router/trace/:id', protect, (req, res) => {
    const trace = readJsonl(TRACE_FILE, 500).reverse().find((item) => item.trace_id === req.params.id);
    if (!trace) return res.status(404).json({ ok: false, error: 'trace not found' });
    res.json({ ok: true, trace });
  });

  router.get('/graph/status', protect, async (_req, res) => {
    res.json(await graphStatus());
  });

  router.get('/graph/snapshot', protect, (_req, res) => {
    res.json({ ok: true, source: 'native_memory_graph', ...nativeGraph().snapshot(Number(_req.query?.limit || 250)) });
  });

  router.get('/graph/maintenance', protect, (_req, res) => {
    const graph = nativeGraph();
    res.json({
      ok: true,
      source: 'native_memory_graph',
      status: graph.status(),
      integrity: graph.integrityCheck({ includePragma: true }),
      backups: graph.listBackups(20),
      conflicts: graph.duplicateCandidates(20),
    });
  });

  router.post('/graph/backup', protect, (req, res) => {
    const graph = nativeGraph();
    const result = graph.createBackup({
      kind: req.body?.kind || 'operator',
      metadata: {
        actor: req.user?.id || req.tenant?.id || 'operator',
        reason: req.body?.reason || 'manual backup',
      },
    });
    if (!result.ok) return res.status(503).json(result);
    res.json({ ok: true, source: 'native_memory_graph', ...result });
  });

  router.post('/graph/repair', protect, (req, res) => {
    const graph = nativeGraph();
    const result = graph.repair({ backupFirst: req.body?.backupFirst !== false });
    if (!result.ok) return res.status(500).json(result);
    res.json({ ok: true, source: 'native_memory_graph', ...result });
  });

  router.post('/graph/restore', protect, (req, res) => {
    const graph = nativeGraph();
    const result = graph.restoreBackup({
      id: req.body?.backup_id || req.body?.id,
      confirm: req.body?.confirm,
      actor: req.user?.id || req.tenant?.id || 'operator',
    });
    if (!result.ok) return res.status(result.status || 500).json(result);
    res.json({ ok: true, source: 'native_memory_graph', ...result });
  });

  router.post('/graph/merge', protect, (req, res) => {
    const graph = nativeGraph();
    const result = graph.mergeNodes({
      survivorId: req.body?.survivor_id,
      duplicateIds: req.body?.duplicate_ids,
      confirm: req.body?.confirm,
      actor: req.user?.id || req.tenant?.id || 'operator',
    });
    if (!result.ok) return res.status(result.status || 500).json(result);
    res.json({ ok: true, source: 'native_memory_graph', ...result });
  });

  router.get('/sql/status', protect, (_req, res) => {
    const status = sqlStatus();
    status.audit = readJsonl(SQL_AUDIT_FILE, 20).reverse();
    res.json(status);
  });

  router.post('/sql/query', protect, (req, res) => {
    const result = runReadOnlySql(req.body || {}, req.user?.id || req.tenant?.id || 'operator');
    if (!result.ok) return res.status(result.status || 400).json(result);
    res.json({ ok: true, state: 'live', source: 'local_sqlite_readonly', ...result });
  });

  router.get('/procedural/status', protect, (_req, res) => {
    res.json(proceduralStatus());
  });

  router._internals = {
    classifyRoutes,
    validateReadOnlySql,
    semanticRetrieve,
    structuredRetrieve,
    episodicRetrieve,
    proceduralRetrieve,
  };

  return router;
}

module.exports = createHybridMemoryRouter;
module.exports.runHybridQuery = runHybridQuery;
module.exports.routerStatus = routerStatus;
module.exports.graphStatus = graphStatus;
module.exports.sqlStatus = sqlStatus;
module.exports.proceduralStatus = proceduralStatus;
module.exports.runReadOnlySql = runReadOnlySql;
module.exports.validateReadOnlySql = validateReadOnlySql;
module.exports.nativeGraph = nativeGraph;
