'use strict';

/**
 * RAG API routes — proxies to Python RAG service.
 *
 * GET  /api/rag/status          — sync stats per connector
 * POST /api/rag/query           — semantic search (access-aware)
 * POST /api/rag/sync            — trigger manual sync for a source
 * POST /api/rag/ingest          — ingest a raw document
 * GET  /api/rag/sources         — list registered connectors
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');

const router = Router();
const PYTHON_BASE = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 18790}`;

async function _proxy(req, res, path, body = null, method = 'GET') {
  try {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Tenant-Id': req.tenantId || 'system' },
    };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(`${PYTHON_BASE}${path}`, { ...opts, signal: AbortSignal.timeout(30000) });
    const data = await r.json();
    res.status(r.status).json(data);
  } catch (e) {
    res.status(502).json({ ok: false, error: `RAG proxy error: ${e.message}` });
  }
}

router.get('/status', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/rag/status');
});

router.post('/query', requirePermission(PERMISSIONS.AGENTS_READ), async (req, res) => {
  const { query, top_k = 8, source_filter, rerank = true } = req.body || {};
  if (!query) return res.status(400).json({ ok: false, error: 'query required' });
  await _proxy(req, res, '/rag/query', {
    query,
    top_k,
    source_filter,
    rerank,
    caller_permissions: req.user?.permissions || ['org'],
  }, 'POST');
});

router.post('/sync', requirePermission(PERMISSIONS.SYSTEM_CONFIGURE), async (req, res) => {
  const { source_type, full = false } = req.body || {};
  if (!source_type) return res.status(400).json({ ok: false, error: 'source_type required' });
  await _proxy(req, res, '/rag/sync', { source_type, full }, 'POST');
});

router.post('/ingest', requirePermission(PERMISSIONS.AGENTS_WRITE), async (req, res) => {
  const { title, content, url, source_type = 'file', metadata = {} } = req.body || {};
  if (!content) return res.status(400).json({ ok: false, error: 'content required' });
  await _proxy(req, res, '/rag/ingest', { title, content, url, source_type, metadata }, 'POST');
});

router.get('/sources', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/rag/sources');
});

router.post('/retrieve', requirePermission(PERMISSIONS.AGENTS_READ), async (req, res) => {
  const { query, top_k = 5, alpha = 0.5, rerank = true, compress = true, cite = true } = req.body || {};
  if (!query) return res.status(400).json({ ok: false, error: 'query required' });
  await _proxy(req, res, '/rag/retrieve', { query, top_k, alpha, rerank, compress, cite }, 'POST');
});

module.exports = router;
