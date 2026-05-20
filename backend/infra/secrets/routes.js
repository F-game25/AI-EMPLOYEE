'use strict';

/**
 * Secrets management API routes (admin/security-officer only).
 *
 *   GET  /api/secrets/status         — broker backend + lease count
 *   POST /api/secrets/set            — store a secret
 *   POST /api/secrets/rotate/:key    — rotate a secret
 *   DELETE /api/secrets/:key         — delete a secret
 *
 * IMPORTANT: Secret VALUES are never returned in API responses.
 * Only metadata (key names, paths, rotation status) is returned.
 */

const { Router } = require('express');
const { getSecretsBroker } = require('./broker');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const router = Router();

router.get('/status', requirePermission(PERMISSIONS.SECRETS_READ), async (req, res) => {
  const broker = await getSecretsBroker();
  res.json({ ok: true, backend: broker.backendName });
});

router.post('/set', requirePermission(PERMISSIONS.SECRETS_WRITE), async (req, res) => {
  const { key, value, scope = 'system', agent_id, ttl_seconds } = req.body || {};
  if (!key || value === undefined) return res.status(400).json({ ok: false, error: 'key and value required' });
  const broker = await getSecretsBroker();
  const ok = await broker.set(key, value, {
    tenant_id: req.tenantId || 'system',
    agent_id: agent_id || null,
    scope,
    ttl_seconds: ttl_seconds || null,
  });
  // Return only key name — never the value
  res.json({ ok, key, scope });
});

router.post('/rotate/:key', requirePermission(PERMISSIONS.SECRETS_ROTATE), async (req, res) => {
  const { newValue, scope = 'system', agent_id } = req.body || {};
  if (!newValue) return res.status(400).json({ ok: false, error: 'newValue required' });
  const broker = await getSecretsBroker();
  const ok = await broker.rotate(req.params.key, newValue, {
    tenant_id: req.tenantId || 'system',
    scope,
    agent_id: agent_id || null,
  });
  res.json({ ok, key: req.params.key, rotated_at: new Date().toISOString() });
});

router.delete('/:key', requirePermission(PERMISSIONS.SECRETS_DELETE), async (req, res) => {
  const broker = await getSecretsBroker();
  const ok = await broker.delete(req.params.key, {
    tenant_id: req.tenantId || 'system',
    scope: req.query.scope || 'system',
    agent_id: req.query.agent_id || null,
  });
  res.json({ ok, key: req.params.key });
});

module.exports = router;
