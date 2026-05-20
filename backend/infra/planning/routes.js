'use strict';

/**
 * Planning API routes.
 *
 * POST   /api/planning/goals              — create goal
 * GET    /api/planning/goals              — list goals
 * GET    /api/planning/goals/:id          — get goal + tree
 * PATCH  /api/planning/goals/:id/status   — update status
 * PATCH  /api/planning/goals/:id/kr/:krId — update key result progress
 * GET    /api/planning/goals/:id/events   — audit events
 * POST   /api/planning/plan/weekly        — generate weekly plan
 * POST   /api/planning/plan/reprioritize  — trigger reprioritization
 * GET    /api/planning/tree/:rootId       — objective tree
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
    res.status(502).json({ ok: false, error: `Planning proxy error: ${e.message}` });
  }
}

router.post('/goals', requirePermission(PERMISSIONS.TASKS_SUBMIT), async (req, res) => {
  await _proxy(req, res, '/planning/goals', {
    ...req.body, owner_id: req.user?.id || 'system',
  }, 'POST');
});

router.get('/goals', requirePermission(PERMISSIONS.TASKS_READ), async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  await _proxy(req, res, `/planning/goals${qs ? '?' + qs : ''}`);
});

router.get('/goals/:id', requirePermission(PERMISSIONS.TASKS_READ), async (req, res) => {
  await _proxy(req, res, `/planning/goals/${req.params.id}`);
});

router.patch('/goals/:id/status', requirePermission(PERMISSIONS.TASKS_SUBMIT), async (req, res) => {
  await _proxy(req, res, `/planning/goals/${req.params.id}/status`, req.body, 'PATCH');
});

router.patch('/goals/:id/kr/:krId', requirePermission(PERMISSIONS.TASKS_SUBMIT), async (req, res) => {
  await _proxy(req, res, `/planning/goals/${req.params.id}/kr/${req.params.krId}`, req.body, 'PATCH');
});

router.get('/goals/:id/events', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  await _proxy(req, res, `/planning/goals/${req.params.id}/events`);
});

router.post('/plan/weekly', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/planning/plan/weekly', {}, 'POST');
});

router.post('/plan/reprioritize', requirePermission(PERMISSIONS.SYSTEM_CONFIGURE), async (req, res) => {
  await _proxy(req, res, '/planning/plan/reprioritize', req.body, 'POST');
});

router.get('/tree/:rootId', requirePermission(PERMISSIONS.TASKS_READ), async (req, res) => {
  await _proxy(req, res, `/planning/tree/${req.params.rootId}`);
});

module.exports = router;
