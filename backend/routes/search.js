'use strict';
/**
 * /api/search — Unified QCE Search API
 *
 * Proxies to Python QCE SearchOrchestrator. Falls back gracefully when
 * Python backend is offline. Legacy callers using { query, sources, max_results }
 * are still supported — the base POST / route accepts both schemas.
 */
const http    = require('http');
const express = require('express');

const PYTHON_HOST = '127.0.0.1';
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const TIMEOUT_MS  = 5000;

const QCE_ENGINE_NAMES = [
  'brave_search', 'bing_search', 'knowledge_graph',
  'vector_memory', 'agent_registry', 'skill_catalog',
];

function _httpPost(pyPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request(
      {
        hostname: PYTHON_HOST, port: PYTHON_PORT, path: pyPath,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
        timeout: TIMEOUT_MS,
      },
      (res) => {
        let data = '';
        res.on('data', (c) => { data += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(data || '{}')); }
          catch { reject(new Error('invalid JSON from Python')); }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.write(payload);
    req.end();
  });
}

function _httpGet(pyPath) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: PYTHON_HOST, port: PYTHON_PORT, path: pyPath, method: 'GET', timeout: TIMEOUT_MS },
      (res) => {
        let data = '';
        res.on('data', (c) => { data += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(data || '{}')); }
          catch { reject(new Error('invalid JSON from Python')); }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.end();
  });
}

// Proxy to Python; on error return fallback(). Always sends exactly one response.
async function proxyToPython(pyPath, body, res, fallback) {
  try {
    const result = body === null ? await _httpGet(pyPath) : await _httpPost(pyPath, body);
    return res.json(result);
  } catch (_err) {
    return res.json(fallback());
  }
}

module.exports = function createSearchRouter(requireAuth) {
  const router = express.Router();

  // POST /api/search — unified QCE fan-out (+ legacy CloakBrowser passthrough)
  router.post('/', requireAuth, async (req, res) => {
    const {
      query = '', bangs = [], complexity = 'medium', task_type = '',
      tenant_id = '', max_results = 50,
      sources, include_screenshot,          // legacy fields — forwarded as-is
    } = req.body || {};

    if (!String(query).trim()) {
      return res.status(400).json({ error: 'query is required' });
    }

    await proxyToPython(
      '/api/search',
      { query, bangs, complexity, task_type, tenant_id, max_results, sources, include_screenshot },
      res,
      () => ({ results: [], engine_stats: {}, fallback: true, message: 'Search backend offline' })
    );
  });

  // POST /api/search/context-pack — full amplification → ContextPack
  router.post('/context-pack', requireAuth, async (req, res) => {
    const { query = '', task_type = '', tenant_id = '', max_results = 50 } = req.body || {};
    await proxyToPython('/api/search/context-pack',
      { query, task_type, tenant_id, max_results }, res,
      () => ({ candidates: [], confidence: 0, reasoning: '', fallback: true }));
  });

  // POST /api/search/explain — why candidates were selected
  router.post('/explain', requireAuth, async (req, res) => {
    const { query = '', tenant_id = '' } = req.body || {};
    await proxyToPython('/api/search/explain',
      { query, tenant_id }, res,
      () => ({ query, candidates: [], confidence: 0, reasoning: '', fallback: true }));
  });

  // POST /api/search/reasoning — search + intent superposition
  router.post('/reasoning', requireAuth, async (req, res) => {
    const { query = '', tenant_id = '' } = req.body || {};
    await proxyToPython('/api/search/reasoning',
      { query, tenant_id }, res,
      () => ({ query, candidates: [], intents: [], fallback: true }));
  });

  // POST /api/search/plan — search + strategy superposition
  router.post('/plan', requireAuth, async (req, res) => {
    const { query = '', task_type = '', tenant_id = '' } = req.body || {};
    await proxyToPython('/api/search/plan',
      { query, task_type, tenant_id }, res,
      () => ({ strategies: [], fallback: true }));
  });

  // POST /api/search/agent-route — amplitude route to agents
  router.post('/agent-route', requireAuth, async (req, res) => {
    const { query = '', preferred_agent_id = '', tenant_id = '' } = req.body || {};
    await proxyToPython('/api/search/agent-route',
      { query, preferred_agent_id, tenant_id }, res,
      () => ({ agent_id: null, confidence: 0, gate: 'direct', fallback: true }));
  });

  // GET /api/search/engines — list registered engines + status
  router.get('/engines', requireAuth, async (req, res) => {
    await proxyToPython('/api/search/engines', null, res, () => ({
      engines: QCE_ENGINE_NAMES.map((name) => ({ name, enabled: false, status: 'unknown' })),
      fallback: true,
    }));
  });

  return router;
};
