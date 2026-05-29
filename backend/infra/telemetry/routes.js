'use strict';

/**
 * Observability 2.0 API routes.
 *
 * GET  /api/telemetry/traces            — list recent execution traces
 * GET  /api/telemetry/traces/:traceId   — full trace tree
 * GET  /api/telemetry/lineage/:recordId — agent lineage (parent + children)
 * GET  /api/telemetry/spans             — in-memory OTel spans
 * POST /api/telemetry/replay/:traceId   — replay an execution trace
 * GET  /api/telemetry/anomalies         — recent anomaly detections
 * GET  /api/telemetry/decisions/:taskId — decision audit trail for a task
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
    res.status(502).json({ ok: false, error: `Telemetry proxy error: ${e.message}` });
  }
}

router.get('/traces', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  const qs = new URLSearchParams(req.query).toString();
  await _proxy(req, res, `/telemetry/traces${qs ? '?' + qs : ''}`);
});

router.get('/traces/:traceId', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  await _proxy(req, res, `/telemetry/traces/${req.params.traceId}`);
});

router.get('/lineage/:recordId', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  await _proxy(req, res, `/telemetry/lineage/${req.params.recordId}`);
});

router.get('/spans', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/telemetry/spans');
});

router.post('/replay/:traceId', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  await _proxy(req, res, `/telemetry/replay/${req.params.traceId}`, req.body || {}, 'POST');
});

router.get('/anomalies', requirePermission(PERMISSIONS.SYSTEM_READ), async (req, res) => {
  await _proxy(req, res, '/telemetry/anomalies');
});

router.get('/decisions/:taskId', requirePermission(PERMISSIONS.AUDIT_READ), async (req, res) => {
  await _proxy(req, res, `/telemetry/decisions/${req.params.taskId}`);
});

module.exports = router;
