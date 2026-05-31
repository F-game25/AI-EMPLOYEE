'use strict';

/**
 * Multi-agent governance API.
 *
 * POST /api/governance/validate        — run validation chain for an agent plan
 * GET  /api/governance/agents          — list agents with trust scores
 * GET  /api/governance/agents/:id      — agent trust profile + event history
 * POST /api/governance/agents/:id/veto — manually veto an agent
 * GET  /api/governance/trust/stats     — trust distribution stats
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
    res.status(502).json({ ok: false, error: `Governance proxy error: ${e.message}` });
  }
}

router.post('/validate', requirePermission(PERMISSIONS.AGENTS_EXECUTE), async (req, res) => {
  const { agent_id, task_id, plan, estimated_cost_usd = 0, use_consensus = false, metadata } = req.body || {};
  if (!agent_id || !plan) return res.status(400).json({ ok: false, error: 'agent_id and plan required' });
  await _proxy(req, res, '/governance/validate', {
    agent_id, task_id, plan, estimated_cost_usd, use_consensus, metadata,
  }, 'POST');
});

router.get('/agents', requirePermission(PERMISSIONS.AGENTS_READ), async (req, res) => {
  await _proxy(req, res, '/governance/agents');
});

router.get('/agents/:id', requirePermission(PERMISSIONS.AGENTS_READ), async (req, res) => {
  await _proxy(req, res, `/governance/agents/${req.params.id}`);
});

router.post('/agents/:id/veto', requirePermission(PERMISSIONS.AGENTS_STOP), async (req, res) => {
  await _proxy(req, res, `/governance/agents/${req.params.id}/veto`, {
    reason: req.body?.reason || 'manual veto', actor: req.user?.id || 'admin',
  }, 'POST');
});

router.get('/trust/stats', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/governance/trust/stats');
});

module.exports = router;
