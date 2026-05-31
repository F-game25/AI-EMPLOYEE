'use strict';

/**
 * Intelligence routes — extracted from server.js (pure refactor, no behavior changes).
 *
 * Mount in server.js:
 *   const createIntelligenceRouter = require('./routes/intelligence');
 *   app.use('/', createIntelligenceRouter({ ... }));
 *
 * Required deps (all sourced from server.js scope):
 *   - requireAuth             : JWT auth middleware
 *   - validate                : function(schema, req, res) → parsed body | null
 *   - SCHEMAS                 : zod schema map (memoryClients, memoryInteraction)
 *   - brain                   : require('./brain/active_brain')
 *   - subsystems              : require('./subsystems')
 *   - getNativeMemoryGraph    : lazy-loaded wrapper around ./core/native-memory-graph
 *   - normalizeDashboardGraph : function(payload) → { nodes, links, stats, updated_at }
 *   - normalizeGraphNode      : function(raw, index) → node | null
 *   - normalizeGraphLink      : function(raw) → link | null
 *   - requestPythonJSON       : function(path, method, payload, opts) → Promise<object>
 *   - readJsonSafe            : function(file, fallback) → object
 *   - statePath               : function(...parts) → string
 *   - conversations           : require('./conversations')
 *   - _cache_neurons          : makeTTLCache(30_000) middleware instance
 *   - PYTHON_BACKEND_HOST     : string ('127.0.0.1')
 *   - PYTHON_BACKEND_PORT     : number | string
 *   - STATE_DIR               : string (absolute path)
 *   - REPO_ROOT               : string (absolute path)
 */

module.exports = function createIntelligenceRouter(deps) {
  const router = require('express').Router();

  const {
    requireAuth,
    validate,
    SCHEMAS,
    brain,
    subsystems,
    getNativeMemoryGraph,
    normalizeDashboardGraph,
    requestPythonJSON,
    readJsonSafe,
    statePath,
    conversations,
    _cache_neurons,
    PYTHON_BACKEND_HOST,
    PYTHON_BACKEND_PORT,
    STATE_DIR,
    REPO_ROOT,
  } = deps;

  // ── Brain endpoints ──────────────────────────────────────────────────────────

  router.get('/api/brain/neurons', requireAuth, _cache_neurons, (req, res) => {
    res.json(brain.neurons());
  });

  /**
   * Unified graph endpoint for the 3-D Neural Brain visualization.
   * Returns { nodes, links, stats } using a normalized schema so the
   * frontend brainStore can consume it directly.
   */
  router.get('/api/brain/graph', requireAuth, async (req, res) => {
    const raw = brain.neurons();
    const memoryTree = subsystems.getMemoryTree();
    const nodes = (raw.nodes || []).map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type || 'skill',
      group:
        n.type === 'Memory'
          ? 'memory'
          : n.type === 'Strategy' || n.type === 'Skill'
            ? 'money'
            : n.type === 'Output'
              ? 'automation'
              : 'learning',
      weight: n.weight ?? 1,
      confidence: n.confidence ?? 0,
      activation: n.activation ?? 0,
      source: n.source || 'system',
      tag: n.tag || '',
    }));

    // Append top memory-tree entities as nodes
    if (Array.isArray(memoryTree?.nodes)) {
      memoryTree.nodes.slice(0, 30).forEach((m) => {
        const id = `mem-${(m.id || m.entity || '').replace(/\s+/g, '-').slice(0, 40)}`;
        if (nodes.some((n) => n.id === id)) return;
        nodes.push({
          id,
          label: m.entity || m.id || 'memory',
          type: 'memory',
          group: 'memory',
          weight: m.mention_count ?? m.importance ?? 1,
          confidence: m.importance ?? 0.5,
          activation: 0,
          source: 'memory',
          tag: 'knowledge',
        });
      });
    }

    const links = (raw.connections || []).map((c) => ({
      source: c.from,
      target: c.to,
      strength: c.weight ?? c.confidence ?? 0.5,
    }));

    // Attempt to merge Neural Brain graph (Python LangGraph + Neo4j)
    let nbGraph = null;
    try {
      const nbResp = await Promise.race([
        fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/graph`, { timeout: 1000 }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1000)),
      ]);
      if (nbResp?.ok) {
        nbGraph = await nbResp.json();
        if (nbGraph?.nodes && Array.isArray(nbGraph.nodes)) {
          nbGraph.nodes.forEach((n) => {
            const existing = nodes.some((x) => x.id === n.id);
            if (!existing) nodes.push(n);
          });
        }
        if (nbGraph?.links && Array.isArray(nbGraph.links)) {
          const linkSet = new Set(links.map((l) => `${l.source}→${l.target}`));
          nbGraph.links.forEach((l) => {
            if (!linkSet.has(`${l.source}→${l.target}`)) {
              links.push(l);
              linkSet.add(`${l.source}→${l.target}`);
            }
          });
        }
      }
    } catch (_nbErr) {
      // Neural Brain offline or slow — continue with regular graph
    }

    // Native embedded graph memory is the canonical offline graph backend.
    // It is not an extension: every dashboard graph response syncs through it.
    try {
      const native = getNativeMemoryGraph({ stateDir: STATE_DIR, repoRoot: REPO_ROOT });
      native.ingestSnapshot({ nodes, links }, 'node_dashboard_graph');
      const nativeSnapshot = native.snapshot(350);
      const nodeSet = new Set(nodes.map((node) => String(node.id)));
      nativeSnapshot.nodes.forEach((node) => {
        if (!nodeSet.has(String(node.id))) {
          nodes.push(node);
          nodeSet.add(String(node.id));
        }
      });
      const linkSet = new Set(links.map((link) => `${link.source}→${link.target}`));
      nativeSnapshot.links.forEach((link) => {
        const key = `${link.source}→${link.target}`;
        if (!linkSet.has(key)) {
          links.push(link);
          linkSet.add(key);
        }
      });
    } catch (err) {
      console.warn('[BRAIN GRAPH] Native graph sync failed: %s', err && err.message);
    }

    res.json(normalizeDashboardGraph({
      nodes,
      links,
      stats: { ...(raw.stats || {}), graph_backend: 'native_memory_graph' },
      updated_at: raw.updated_at || new Date().toISOString(),
    }));
  });

  // ── Memory tree / stats ──────────────────────────────────────────────────────

  router.get('/api/memory/tree', requireAuth, (req, res) => {
    res.json(subsystems.getMemoryTree());
  });

  router.get('/api/memory/stats', requireAuth, async (req, res) => {
    const ks = readJsonSafe(statePath('knowledge_store.json'), { entries: [] });
    const ksEntries = Array.isArray(ks.entries) ? ks.entries : (Array.isArray(ks) ? ks : []);
    const base = {
      types: {
        episodic:   { count: 0, last_write: null },
        semantic:   { count: 0 },
        procedural: { count: 0 },
      },
      total: 0,
      chroma_collections: {},
      knowledge_store_entries: ksEntries.length,
      source: 'node-fallback',
    };
    try {
      const pyData = await requestPythonJSON('/api/memory', 'GET', null, { timeoutMs: 3000 });
      if (pyData && pyData._http_status >= 200 && pyData._http_status < 300) {
        const episodicCount = pyData.total_clients || pyData.episodic_count || 0;
        const semanticCount = pyData.semantic_count || ksEntries.length;
        const proceduralCount = pyData.procedural_count || 0;
        return res.json({
          types: {
            episodic:   { count: episodicCount, last_write: pyData.last_write || null },
            semantic:   { count: semanticCount },
            procedural: { count: proceduralCount },
          },
          total: episodicCount + semanticCount + proceduralCount,
          chroma_collections: pyData.chroma_collections || {},
          knowledge_store_entries: ksEntries.length,
          source: 'node+python',
        });
      }
    } catch (_) { /* fall through to node-fallback */ }
    base.total = ksEntries.length;
    return res.json(base);
  });

  // ── Memory CRUD ──────────────────────────────────────────────────────────────

  router.get('/api/memory', requireAuth, async (req, res) => {
    try {
      const data = await requestPythonJSON('/api/memory', 'GET', null, { timeoutMs: 4000 });
      if (data._http_status >= 200 && data._http_status < 300) {
        return res.json({ ...data, source: 'python-memory' });
      }
      return res.status(data._http_status || 502).json({ ok: false, error: 'Python memory backend returned an error', source: 'python-memory' });
    } catch (err) {
      const tree = subsystems.getMemoryTree();
      return res.json({
        source: 'node-fallback',
        clients: [],
        recent_interactions: [],
        total_clients: 0,
        fallback_tree: tree,
        warning: `Python memory backend unavailable: ${err.message}`,
      });
    }
  });

  // ── Conversations JSONL endpoint ─────────────────────────────────────────────

  router.get('/api/memory/conversations', requireAuth, (req, res) => {
    const all = conversations.readConversations();
    return res.json({ conversations: all.slice(-100), total: all.length, source: 'node-local' });
  });

  router.delete('/api/memory/conversations/:id', requireAuth, (req, res) => {
    const removed = conversations.deleteConversation(req.params.id);
    if (!removed) return res.status(404).json({ ok: false, error: 'Conversation not found' });
    return res.json({ ok: true, deleted: req.params.id });
  });

  router.get('/api/memory/search', requireAuth, async (req, res) => {
    const q = String((req.query || {}).q || '').trim();
    if (!q) return res.status(400).json({ ok: false, error: 'q required' });
    const topK = Math.max(1, Math.min(25, Number((req.query || {}).top_k || 8) || 8));
    const memoryType = String((req.query || {}).memory_type || '').trim();
    const query = `/api/memory/search?q=${encodeURIComponent(q)}&top_k=${topK}${memoryType ? `&memory_type=${encodeURIComponent(memoryType)}` : ''}`;
    try {
      const data = await requestPythonJSON(query, 'GET', null, { timeoutMs: 5000 });
      if (data._http_status >= 200 && data._http_status < 300) {
        return res.json({ ...data, source: data.source || 'python-memory-search' });
      }
      return res.status(data._http_status || 502).json({ ok: false, error: 'Python memory search returned an error', source: 'python-memory-search' });
    } catch (err) {
      return res.status(503).json({ ok: false, error: `Python memory search unavailable: ${err.message}`, source: 'node-fallback', results: [] });
    }
  });

  router.post('/api/memory/clients', requireAuth, async (req, res) => {
    const _bodyMemClients = validate(SCHEMAS.memoryClients, req, res);
    if (!_bodyMemClients) return;
    try {
      const data = await requestPythonJSON('/api/memory/clients', 'POST', _bodyMemClients, { timeoutMs: 5000 });
      return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
    } catch (err) {
      return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
    }
  });

  router.patch('/api/memory/clients/:clientId', requireAuth, async (req, res) => {
    try {
      const data = await requestPythonJSON(`/api/memory/clients/${encodeURIComponent(req.params.clientId)}`, 'PATCH', req.body || {}, { timeoutMs: 5000 });
      return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
    } catch (err) {
      return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
    }
  });

  router.delete('/api/memory/clients/:clientId', requireAuth, async (req, res) => {
    try {
      const data = await requestPythonJSON(`/api/memory/clients/${encodeURIComponent(req.params.clientId)}`, 'DELETE', null, { timeoutMs: 5000 });
      return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
    } catch (err) {
      return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
    }
  });

  router.post('/api/memory/interactions', requireAuth, async (req, res) => {
    const _bodyMemInt = validate(SCHEMAS.memoryInteraction, req, res);
    if (!_bodyMemInt) return;
    try {
      const data = await requestPythonJSON('/api/memory/interactions', 'POST', _bodyMemInt, { timeoutMs: 5000 });
      return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
    } catch (err) {
      return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
    }
  });

  // ── Knowledge search ─────────────────────────────────────────────────────────

  router.get('/api/knowledge/search', requireAuth, async (req, res) => {
    const q = String((req.query || {}).q || '').trim();
    if (!q) return res.status(400).json({ ok: false, error: 'q required' });
    const mode = String((req.query || {}).mode || 'keyword');
    const alpha = Math.max(0, Math.min(1, Number((req.query || {}).alpha ?? 0.5)));
    const limit = Math.max(1, Math.min(50, Number((req.query || {}).limit || 10) || 10));

    if (mode === 'hybrid' || mode === 'semantic') {
      try {
        const pyUrl = `/memory/hybrid-search?q=${encodeURIComponent(q)}&alpha=${alpha}&limit=${limit}`;
        const data = await requestPythonJSON(pyUrl, 'GET', null, { timeoutMs: 6000 });
        if (data._http_status >= 200 && data._http_status < 300) {
          const entries = (data.results || []).map(r => ({
            id: r.source || r.rank,
            title: r.source || 'Knowledge Entry',
            content: r.content || '',
            text: r.content || '',
            source: r.source || '',
            score: r.score ?? 0,
            bm25_score: r.bm25_score ?? null,
            vector_score: r.vector_score ?? null,
            rank: r.rank ?? null,
          }));
          return res.json({ entries, total: entries.length, mode: 'hybrid', query: q });
        }
      } catch (_) { /* fallthrough to keyword */ }
    }

    // Keyword fallback: scan knowledge_store.json
    const ks = readJsonSafe(statePath('knowledge_store.json'), { entries: [] });
    const ksEntries = Array.isArray(ks.entries) ? ks.entries : (Array.isArray(ks) ? ks : []);
    const lower = q.toLowerCase();
    const matched = ksEntries.filter(e =>
      (e.content || e.text || '').toLowerCase().includes(lower) ||
      (e.title || e.source || '').toLowerCase().includes(lower)
    ).slice(0, limit).map(e => ({
      id: e.id || e.title,
      title: e.title || e.source || 'Untitled',
      content: e.content || e.text || '',
      text: e.content || e.text || '',
      source: e.source || '',
      score: null,
      tags: e.tags || [],
    }));
    return res.json({ entries: matched, total: matched.length, mode: 'keyword', query: q });
  });

  // ── Knowledge vault ──────────────────────────────────────────────────────────

  router.get('/api/knowledge/vault/:title', requireAuth, async (req, res) => {
    try {
      const r = await fetch(
        `http://127.0.0.1:18790/knowledge/vault/${encodeURIComponent(req.params.title)}`,
        { headers: { 'Authorization': req.headers.authorization || '' } }
      );
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'vault unavailable' }); }
  });

  router.post('/api/knowledge/vault/:title/verify', requireAuth, async (req, res) => {
    try {
      const r = await fetch(
        `http://127.0.0.1:18790/knowledge/vault/${encodeURIComponent(req.params.title)}/verify`,
        { method: 'POST', headers: { 'Authorization': req.headers.authorization || '' } }
      );
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'vault unavailable' }); }
  });

  // ── RAG sources ──────────────────────────────────────────────────────────────

  router.get('/api/rag/sources', requireAuth, async (req, res) => {
    const ks = readJsonSafe(statePath('knowledge_store.json'), { entries: [] });
    const ksEntries = Array.isArray(ks.entries) ? ks.entries : (Array.isArray(ks) ? ks : []);
    const nodeSourcesMap = new Map(ksEntries.map((e) => [String(e.id || e.title || Math.random()), e]));
    let chromaStatus = 'empty';
    try {
      const pyData = await requestPythonJSON('/api/knowledge/sources', 'GET', null, { timeoutMs: 2000 });
      if (pyData && pyData._http_status >= 200 && pyData._http_status < 300) {
        const pySources = Array.isArray(pyData.sources) ? pyData.sources : [];
        chromaStatus = pySources.length > 0 ? 'populated' : 'empty';
        for (const s of pySources) {
          const key = String(s.id || s.title || '');
          if (key && !nodeSourcesMap.has(key)) nodeSourcesMap.set(key, s);
        }
      }
    } catch (_) { chromaStatus = 'offline'; }
    const sources = [...nodeSourcesMap.values()].map((e) => ({
      id:         e.id         || null,
      title:      e.title      || e.source || 'Untitled',
      source:     e.source     || null,
      tags:       e.tags       || [],
      created_at: e.created_at || null,
    }));
    return res.json({ sources, total: sources.length, chroma_status: chromaStatus, embedding_model: 'all-MiniLM-L6-v2' });
  });

  // ── Tool registry ────────────────────────────────────────────────────────────

  router.get('/api/tools/:name', requireAuth, async (req, res) => {
    try {
      const r = await fetch(
        `http://127.0.0.1:${PYTHON_BACKEND_PORT}/tools/${encodeURIComponent(req.params.name)}`,
        { headers: { 'Authorization': req.headers.authorization || '' } },
      );
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'tools service unavailable' }); }
  });

  return router;
};
