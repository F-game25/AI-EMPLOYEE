'use strict';

/**
 * Agents & Brain routes — extracted from server.js (pure refactor, no behavior changes).
 *
 * Mount in server.js:
 *   const { createAgentsBrainRouter } = require('./routes/agents-brain');
 *   const agentsBrainRouter = createAgentsBrainRouter({ ... });
 *   app.use('/', agentsBrainRouter);          // covers /agents, /internal/*
 *   app.use('/', agentsBrainRouter);          // covers /api/*, /api/brain/*, etc.
 *
 * Required deps (all sourced from server.js scope):
 *   - requireAuth        : JWT auth middleware
 *   - requireLocalhost   : localhost-only middleware
 *   - validate           : function(schema, req, res) → parsed body | null
 *   - SCHEMAS            : zod schema map (agentsActivate, learningLadderBuild,
 *                          learningLadderComplete, agentLadderAssign, agentLadderAdvance)
 *   - getAgents          : () → agent[]
 *   - activateAgents     : (count?) → result
 *   - getMode            : () → string
 *   - addActivity        : (notes, kind) → void
 *   - brain              : require('./brain/active_brain')
 *   - subsystems         : require('./subsystems')
 *   - getNativeMemoryGraph : lazy-loaded wrapper around ./core/native-memory-graph
 *   - normalizeDashboardGraph : function(payload) → { nodes, links, stats, updated_at }
 *   - proxyNeuralBrain   : async function(path, fallback) → data
 *   - PYTHON_BACKEND_HOST : string ('127.0.0.1')
 *   - PYTHON_BACKEND_PORT : number | string
 *   - STATE_DIR          : string (absolute path)
 *   - REPO_ROOT          : string (absolute path)
 *   - _cache_grades      : makeTTLCache(30_000) middleware instance
 *   - graphDeltaState    : { lastMtimeMs, lastNodeCount, lastEdgeCount } (mutable ref object)
 */

const router = require('express').Router();

module.exports = function createAgentsBrainRouter(deps) {
  const {
    requireAuth,
    requireLocalhost,
    validate,
    SCHEMAS,
    getAgents,
    activateAgents,
    getMode,
    addActivity,
    brain,
    subsystems,
    getNativeMemoryGraph,
    normalizeDashboardGraph,
    proxyNeuralBrain,
    PYTHON_BACKEND_HOST,
    PYTHON_BACKEND_PORT,
    STATE_DIR,
    REPO_ROOT,
    _cache_grades,
    graphDeltaState,
  } = deps;

  const router = require('express').Router();

  // ── Learning Ladder (require here so the module loads once per server start) ──
  const learningLadder      = require('../core/learning_ladder');
  const agentLearningProfile = require('../core/agent_learning_profile');

  // ── /agents & /internal/agents ────────────────────────────────────────────────

  router.get('/agents', requireAuth, (req, res) => {
    res.json({ agents: getAgents() });
  });

  router.get('/internal/agents', requireLocalhost, (req, res) => {
    res.json({ agents: getAgents(), internal: true });
  });

  router.post('/agents/activate', requireAuth, (req, res) => {
    const _bodyActivate = validate(SCHEMAS.agentsActivate, req, res);
    if (!_bodyActivate) return;
    const { count } = _bodyActivate;
    const out = activateAgents(typeof count === 'number' ? count : undefined);
    res.json({ ok: true, ...out, mode: getMode(), agents: getAgents() });
  });

  // ── /api/agents ───────────────────────────────────────────────────────────────

  router.post('/api/agents/start-all', requireAuth, (req, res) => {
    res.json({ ok: true, action: 'start-all' });
  });

  router.post('/api/agents/pause-all', requireAuth, (req, res) => {
    res.json({ ok: true, action: 'pause-all' });
  });

  router.post('/api/agents/stop-all', requireAuth, (req, res) => {
    res.json({ ok: true, action: 'stop-all' });
  });

  router.get('/api/agents', requireAuth, (req, res) => {
    const agents = getAgents();
    let forgeAgents = [];
    try {
      const { getAscendForgeEngine } = require('../ascendforge/engine');
      const eng = getAscendForgeEngine();
      if (eng.forgeAgentStatus) forgeAgents = Object.values(eng.forgeAgentStatus);
    } catch { /* engine not loaded yet — skip */ }
    const response = {
      agents: [...agents, ...forgeAgents],
      tenant: req.tenant ? { tenant_id: req.tenant.tenantId, org_name: req.tenant.orgName } : null,
    };
    res.json(response);
  });

  // ── /api/agents/list ──────────────────────────────────────────────────────────

  router.get('/api/agents/list', requireAuth, (req, res) => {
    try {
      const agents = getAgents().map(a => ({
        id: a.id,
        description: a.description || '',
        state: a.state || 'idle',
        type: a.type || 'general',
        category: a.category || '',
        lastActivityAt: a.lastActivityAt || null,
        tasksCompleted: a.tasksCompleted || 0,
      }));
      res.json({ agents, count: agents.length });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // ── /api/agents/grades & per-agent grade/profile ──────────────────────────────

  // NOTE: /api/agents/grades must be registered BEFORE /api/agents/:agent_id/* so
  // Express does not treat "grades" as an :agent_id parameter.
  router.get('/api/agents/grades', requireAuth, _cache_grades, (req, res) => {
    try {
      const profiles = agentLearningProfile.getAllProfiles();
      const metrics  = agentLearningProfile.getMetrics();
      res.json({ ok: true, profiles, metrics });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/api/agents/:agent_id/grade', requireAuth, (req, res) => {
    const agentId = String(req.params.agent_id || '').trim();
    if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
    try {
      const grade = agentLearningProfile.getAgentGrade(agentId);
      res.json({ ok: true, ...grade });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/api/agents/:agent_id/profile', requireAuth, (req, res) => {
    const agentId = String(req.params.agent_id || '').trim();
    if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
    try {
      const profile = agentLearningProfile.getAgentProfile(agentId);
      res.json({ ok: true, ...profile });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── /api/agents/:agent_id/ladder ──────────────────────────────────────────────

  router.post('/api/agents/:agent_id/ladder/assign', requireAuth, (req, res) => {
    const agentId     = String(req.params.agent_id || '').trim();
    const _bodyAssign = validate(SCHEMAS.agentLadderAssign, req, res);
    if (!_bodyAssign) return;
    const topic = String(_bodyAssign.topic || '').trim();
    if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
    try {
      const result = agentLearningProfile.assignLadder(agentId, topic);
      addActivity(`[LEARNING] Ladder '${topic}' assigned to agent ${agentId}`, 'learning');
      res.json({ ok: true, ...result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/api/agents/:agent_id/ladder/advance', requireAuth, (req, res) => {
    const agentId = String(req.params.agent_id || '').trim();
    const body    = validate(SCHEMAS.agentLadderAdvance, req, res);
    if (!body) return;
    const level = parseInt(body.level, 10);
    if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
    try {
      const result = agentLearningProfile.advanceAgent({
        agentId,
        level,
        success: Boolean(body.success),
        score: parseFloat(body.score) || 0,
        milestoneOutput: String(body.milestone_output || ''),
        notes: String(body.notes || ''),
      });
      const status = result.learned ? `LEARNED (grade: ${result.grade})` : 'NOT LEARNED';
      addActivity(`[LEARNING] Agent ${agentId} Level ${level} ${status}`, 'learning');
      res.json({ ok: true, result });
    } catch (err) {
      const status = err.message.includes('no learning ladder') ? 404 : 500;
      res.status(status).json({ ok: false, error: err.message });
    }
  });

  // ── /api/learning-ladder ──────────────────────────────────────────────────────

  router.post('/api/learning-ladder/build', requireAuth, (req, res) => {
    const _bodyLadder = validate(SCHEMAS.learningLadderBuild, req, res);
    if (!_bodyLadder) return;
    const topic = String(_bodyLadder.topic || '').trim();
    try {
      const ladder = learningLadder.buildLadder(topic);
      addActivity(`[LEARNING] Ladder built: ${topic}`, 'learning');
      res.json({ ok: true, ladder });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.post('/api/learning-ladder/complete', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.learningLadderComplete, req, res);
    if (!body) return;
    const topic = String(body.topic || '').trim();
    const level = parseInt(body.level, 10);
    try {
      const result = learningLadder.recordLevelCompletion({
        topic,
        level,
        success: Boolean(body.success),
        milestoneOutput: String(body.milestone_output || ''),
        score: parseFloat(body.score) || 0,
        notes: String(body.notes || ''),
      });
      const status = result.learned ? 'LEARNED' : 'NOT LEARNED';
      addActivity(`[LEARNING] Level ${level} ${status}: ${topic}`, 'learning');
      res.json({ ok: true, result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/api/learning-ladder/progress', requireAuth, (req, res) => {
    const topic = String(req.query.topic || '').trim();
    if (!topic) return res.status(400).json({ ok: false, error: 'topic query param is required' });
    try {
      const progress = learningLadder.getProgress(topic);
      res.json({ ok: true, ...progress });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  router.get('/api/learning-ladder/all', requireAuth, (req, res) => {
    try {
      const topics  = learningLadder.getAllTopics();
      const metrics = learningLadder.getMetrics();
      res.json({ ok: true, topics, metrics });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── /api/brain & /internal/brain ─────────────────────────────────────────────

  router.get('/api/brain/status', requireAuth, (req, res) => {
    const nn   = subsystems.getNNStatus();
    const core = brain.status();
    res.json({
      ...nn,
      ...core,
      updated_at: nn.updated_at || core.last_update || new Date().toISOString(),
    });
  });

  router.get('/internal/brain/status', requireLocalhost, (req, res) => {
    const core     = brain.status()   || {};
    const insights = brain.insights() || {};
    const strategies = Array.isArray(insights.learned_strategies) ? insights.learned_strategies.length : 0;
    const active     = Boolean(core.available && core.active);
    res.json({
      status: active ? 'online' : 'offline',
      initialized: active,
      strategies_loaded: strategies,
      updated_at: core.last_update || insights.updated_at || new Date().toISOString(),
    });
  });

  router.get('/api/brain/insights', requireAuth, (req, res) => {
    res.json(brain.insights());
  });

  router.get('/api/brain/activity', requireAuth, (req, res) => {
    const limit = Number(req.query.limit || 20);
    res.json(brain.activity(limit));
  });

  // ── /api/brain/graph/delta ────────────────────────────────────────────────────

  router.get('/api/brain/graph/delta', requireAuth, (req, res) => {
    const since       = Number(req.query.since) || 0;
    const snapshot_ts = graphDeltaState.lastMtimeMs || Date.now();
    res.json({
      delta:       [],
      full:        true,
      snapshot_ts,
      nodes_count: graphDeltaState.lastNodeCount,
      edges_count: graphDeltaState.lastEdgeCount,
    });
  });

  // ── /api/neural-brain ─────────────────────────────────────────────────────────

  router.get('/api/neural-brain/graph', requireAuth, async (req, res) => {
    const depth = Number(req.query.depth) || 2;
    const limit = Number(req.query.limit) || 200;
    const data  = await proxyNeuralBrain(`/api/neural-brain/graph?depth=${depth}&limit=${limit}`, { nodes: [], links: [] });
    const normalized = normalizeDashboardGraph(data);

    // If Python backend returned no nodes, synthesize a graph from the agent catalog
    if (!normalized.nodes || normalized.nodes.length === 0) {
      try {
        const path = require('path');
        const fs   = require('fs');
        const catalogPath = path.join(REPO_ROOT, 'runtime', 'config', 'agent_capabilities.json');
        const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
        const agents  = Array.isArray(catalog) ? catalog : (catalog.agents || []);
        const skillSet = new Set();
        const nodes = [];
        const links = [];

        agents.slice(0, limit).forEach((a, i) => {
          const agentId = `agent_${i}`;
          nodes.push({ id: agentId, label: a.name || a.id || agentId, type: 'agent', group: a.category || 'agent', size: 6 });
          (a.skills || []).slice(0, 5).forEach(skill => {
            const skillId = `skill_${skill}`;
            if (!skillSet.has(skillId)) {
              skillSet.add(skillId);
              nodes.push({ id: skillId, label: skill, type: 'skill', group: 'skill', size: 3 });
            }
            links.push({ source: agentId, target: skillId, weight: 1 });
          });
        });

        return res.json({ nodes, links, stats: { node_count: nodes.length, edge_count: links.length }, synthetic: true, updated_at: new Date().toISOString() });
      } catch (_) { /* fall through to empty */ }
    }

    res.json(normalized);
  });

  router.get('/api/neural-brain/memory/status', requireAuth, async (req, res) => {
    const data = await proxyNeuralBrain('/api/neural-brain/memory/status', {
      count: 0, last_write_ts: null, recent: [],
    });
    res.json(data);
  });

  router.get('/api/neural-brain/memory/list', requireAuth, async (req, res) => {
    const data = await proxyNeuralBrain('/api/neural-brain/memory/list', {
      items: [], total: 0, page: 1,
    });
    res.json(data);
  });

  router.delete('/api/neural-brain/memory/:id', requireAuth, async (req, res) => {
    try {
      const memId = encodeURIComponent(String(req.params.id || '').trim());
      if (!memId) return res.status(400).json({ ok: false, error: 'id required' });
      const r = await fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/memory/${memId}`, { method: 'DELETE' });
      if (r?.ok) return res.json(await r.json());
    } catch (_) {}
    res.json({ ok: true });
  });

  router.get('/api/neural-brain/graph/status', requireAuth, async (req, res) => {
    const data = await proxyNeuralBrain('/api/neural-brain/graph/status', {
      node_count: 0, edge_count: 0, recent_nodes: [],
    });
    res.json(data);
  });

  router.get('/api/neural-brain/graph/snapshot', requireAuth, async (req, res) => {
    let data = await proxyNeuralBrain('/api/neural-brain/graph/snapshot', {
      nodes: [], links: [], stats: {},
    });
    if (!Array.isArray(data?.nodes) || data.nodes.length === 0) {
      data = await proxyNeuralBrain('/api/neural-brain/graph', data);
    }
    res.json(normalizeDashboardGraph(data));
  });

  router.get('/api/neural-brain/threads', requireAuth, async (req, res) => {
    const data = await proxyNeuralBrain('/api/neural-brain/threads', { threads: [] });
    res.json(data);
  });

  router.get('/api/neural-brain/forge/evolution/status', requireAuth, async (req, res) => {
    const data = await proxyNeuralBrain('/api/neural-brain/forge/evolution/status', {
      mode: 'SAFE', patches_proposed: 0, patches_applied: 0,
    });
    res.json(data);
  });

  router.post('/api/neural-brain/think', requireAuth, async (req, res) => {
    try {
      const r = await Promise.race([
        fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/think`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req.body),
        }),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 10000)),
      ]);
      if (r?.ok) return res.json(await r.json());
    } catch (_) {}
    res.json({ response: 'Neural Brain offline — Python backend not running.', status: 'offline' });
  });

  // ── /api/memory/graph/:view ───────────────────────────────────────────────────

  const _MEMORY_GRAPH_VIEWS = new Set(['shortterm', 'longterm', 'relations', 'unified']);

  router.get('/api/memory/graph/:view', requireAuth, async (req, res) => {
    const { view } = req.params;
    if (!_MEMORY_GRAPH_VIEWS.has(view)) return res.status(400).json({ error: 'unknown view', nodes: [], links: [] });
    const limit = Number(req.query.limit) || 300;
    const data  = await proxyNeuralBrain(`/api/neural-brain/graph/views/${view}?limit=${limit}`, { nodes: [], links: [], stats: {}, view });
    if ((!data.nodes || data.nodes.length === 0) && (view === 'relations' || view === 'unified')) {
      try {
        const snap = getNativeMemoryGraph({ stateDir: STATE_DIR, repoRoot: REPO_ROOT }).snapshot(limit);
        if (snap?.nodes?.length) {
          return res.json({
            nodes: snap.nodes,
            links: snap.links || [],
            stats: { node_count: snap.nodes.length, link_count: (snap.links || []).length },
            view,
            source: 'native_fallback',
          });
        }
      } catch (_) { /* fall through to honest empty */ }
    }
    res.json(data);
  });

  return router;
};
