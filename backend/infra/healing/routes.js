'use strict';

/**
 * Self-Healing Infrastructure API routes.
 *
 * GET  /api/healing/status                    — overall system health score
 * GET  /api/healing/agents                    — per-agent health + circuit state
 * POST /api/healing/agents/:id/quarantine     — manual quarantine
 * POST /api/healing/agents/:id/restore        — lift quarantine
 * GET  /api/healing/circuits                  — all circuit breaker states
 * POST /api/healing/circuits/:svc/reset       — force CLOSED
 * GET  /api/healing/events                    — recent healing events log
 * POST /api/healing/simulate                  — inject synthetic failure
 * GET  /api/healing/predictions               — upcoming predicted failures
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy } = require('../proxy');

const router = Router();
const _proxy = makeProxy('Healing');

const sysRead  = requirePermission(PERMISSIONS.SYSTEM_READ);
const sysWrite = requirePermission(PERMISSIONS.SYSTEM_CONFIGURE);

router.get('/status',                      sysRead,  (req, res) => _proxy(req, res, '/healing/status'));
router.get('/agents',                      sysRead,  (req, res) => _proxy(req, res, '/healing/agents'));
router.post('/agents/:id/quarantine',      sysWrite, (req, res) => _proxy(req, res, `/healing/agents/${req.params.id}/quarantine`, req.body, 'POST'));
router.post('/agents/:id/restore',         sysWrite, (req, res) => _proxy(req, res, `/healing/agents/${req.params.id}/restore`, {}, 'POST'));
router.get('/circuits',                    sysRead,  (req, res) => _proxy(req, res, '/healing/circuits'));
router.post('/circuits/:svc/reset',        sysWrite, (req, res) => _proxy(req, res, `/healing/circuits/${req.params.svc}/reset`, {}, 'POST'));
router.get('/events',                      sysRead,  (req, res) => _proxy(req, res, '/healing/events'));
router.post('/simulate',                   sysWrite, (req, res) => {
  const qs = new URLSearchParams({ service: req.query.service || 'ai_backend' }).toString();
  _proxy(req, res, `/healing/simulate?${qs}`, req.body, 'POST');
});
router.get('/predictions',                 sysRead,  (req, res) => _proxy(req, res, '/healing/predictions'));

module.exports = router;
