'use strict';

/**
 * Economic orchestration API routes.
 *
 * POST /api/economics/evaluate   — evaluate task ROI before execution
 * POST /api/economics/record     — record actual cost after execution
 * GET  /api/economics/summary    — monthly budget summary for tenant
 * GET  /api/economics/costs      — top cost breakdown
 * GET  /api/economics/models     — pricing catalog
 * PUT  /api/economics/budget     — set tenant budget ceiling
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
    const r = await fetch(`${PYTHON_BASE}${path}`, { ...opts, signal: AbortSignal.timeout(15000) });
    const data = await r.json();
    res.status(r.status).json(data);
  } catch (e) {
    res.status(502).json({ ok: false, error: `Economics proxy error: ${e.message}` });
  }
}

router.post('/evaluate', requirePermission(PERMISSIONS.TASKS_SUBMIT), async (req, res) => {
  const { task_type = 'generation', description = '', required_capabilities,
          expected_input_tokens, expected_output_tokens, sla_latency_tier,
          priority, business_context, hint_value_usd } = req.body || {};
  await _proxy(req, res, '/economics/evaluate', {
    task_id: `eval-${Date.now()}`,
    tenant_id: req.tenantId || 'system',
    task_type, description, required_capabilities,
    expected_input_tokens, expected_output_tokens,
    sla_latency_tier, priority, business_context, hint_value_usd,
  }, 'POST');
});

router.post('/record', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/economics/record', req.body, 'POST');
});

router.get('/summary', requirePermission(PERMISSIONS.FINANCE_READ), async (req, res) => {
  await _proxy(req, res, '/economics/summary');
});

router.get('/costs', requirePermission(PERMISSIONS.FINANCE_READ), async (req, res) => {
  await _proxy(req, res, '/economics/costs');
});

router.get('/models', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/economics/models');
});

router.put('/budget', requirePermission(PERMISSIONS.FINANCE_APPROVE), async (req, res) => {
  const { ceiling_usd, tenant_id } = req.body || {};
  if (!ceiling_usd || ceiling_usd <= 0)
    return res.status(400).json({ ok: false, error: 'ceiling_usd must be positive' });
  await _proxy(req, res, '/economics/budget', { ceiling_usd, tenant_id: tenant_id || req.tenantId }, 'PUT');
});

module.exports = router;
