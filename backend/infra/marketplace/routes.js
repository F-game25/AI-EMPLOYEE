'use strict';

/**
 * Agent Marketplace API routes.
 *
 * GET  /api/marketplace/plugins              — list installed plugins
 * POST /api/marketplace/plugins/install      — install .aiepkg
 * GET  /api/marketplace/plugins/:id          — plugin detail
 * DELETE /api/marketplace/plugins/:id        — uninstall
 * POST /api/marketplace/plugins/:id/enable   — activate
 * POST /api/marketplace/plugins/:id/disable  — deactivate
 * GET  /api/marketplace/approvals            — pending approvals
 * POST /api/marketplace/approvals/:id/approve
 * POST /api/marketplace/approvals/:id/reject
 * GET  /api/marketplace/capabilities
 * POST /api/marketplace/validate             — validate .aiepkg
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy, PYTHON_BASE } = require('../proxy');

const router = Router();
const _proxy = makeProxy('Marketplace', 60000);

// multer stores upload in memory for proxying
const upload = (() => {
  try { return require('multer')({ storage: require('multer').memoryStorage() }); }
  catch { return { single: () => (req, res, next) => next() }; }
})();

async function _proxyMultipart(req, res, path) {
  try {
    const fileBuffer = req.file?.buffer || req.body;
    const opts = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Tenant-Id': req.tenantId || req.headers['x-tenant-id'] || 'system',
        'Content-Disposition': `attachment; filename="${req.file?.originalname || 'plugin.aiepkg'}"`,
      },
      body: fileBuffer,
      signal: AbortSignal.timeout(120000),
    };
    const r = await fetch(`${PYTHON_BASE}${path}`, opts);
    const data = await r.json();
    res.status(r.status).json(data);
  } catch (e) {
    res.status(502).json({ ok: false, error: `Marketplace upload proxy error: ${e.message}` });
  }
}

const read   = requirePermission(PERMISSIONS.SYSTEM_READ);
const write  = requirePermission(PERMISSIONS.SYSTEM_CONFIGURE);
const admin  = requirePermission(PERMISSIONS.AUDIT_READ);

router.get('/plugins',                    read,  (req, res) => _proxy(req, res, '/marketplace/plugins'));
router.post('/plugins/install',           write, upload.single('file'), (req, res) => _proxyMultipart(req, res, '/marketplace/plugins/install'));
router.get('/plugins/:id',                read,  (req, res) => _proxy(req, res, `/marketplace/plugins/${req.params.id}`));
router.delete('/plugins/:id',             write, (req, res) => _proxy(req, res, `/marketplace/plugins/${req.params.id}`, null, 'DELETE'));
router.post('/plugins/:id/enable',        write, (req, res) => _proxy(req, res, `/marketplace/plugins/${req.params.id}/enable`, {}, 'POST'));
router.post('/plugins/:id/disable',       write, (req, res) => _proxy(req, res, `/marketplace/plugins/${req.params.id}/disable`, {}, 'POST'));
router.get('/approvals',                  admin, (req, res) => _proxy(req, res, `/marketplace/approvals${req.query.status ? '?status='+req.query.status : ''}`));
router.post('/approvals/:id/approve',     admin, (req, res) => _proxy(req, res, `/marketplace/approvals/${req.params.id}/approve`, req.body, 'POST'));
router.post('/approvals/:id/reject',      admin, (req, res) => _proxy(req, res, `/marketplace/approvals/${req.params.id}/reject`, {}, 'POST'));
router.get('/capabilities',               read,  (req, res) => _proxy(req, res, '/marketplace/capabilities'));
router.post('/validate',                  write, upload.single('file'), (req, res) => _proxyMultipart(req, res, '/marketplace/validate'));

module.exports = router;
