'use strict';

/**
 * Distributed Deployment API routes.
 *
 * GET  /api/deployment/status    — k8s deployment status
 * GET  /api/deployment/pods      — pod list with health
 * POST /api/deployment/scale     — scale a deployment
 * POST /api/deployment/rollback  — rollback to previous revision
 * GET  /api/deployment/history   — helm release history
 * POST /api/deployment/blue-green — initiate blue/green swap
 * GET  /api/deployment/metrics   — resource utilization
 * POST /api/deployment/drain     — cordon + drain a node
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy } = require('../proxy');

const router = Router();
const _proxy = makeProxy('Deployment');

const sysRead  = requirePermission(PERMISSIONS.SYSTEM_READ);
const sysWrite = requirePermission(PERMISSIONS.SYSTEM_CONFIGURE);

router.get('/status',       sysRead,  (req, res) => _proxy(req, res, '/deployment/status'));
router.get('/pods',         sysRead,  (req, res) => _proxy(req, res, '/deployment/pods'));
router.post('/scale',       sysWrite, (req, res) => _proxy(req, res, '/deployment/scale', req.body, 'POST'));
router.post('/rollback',    sysWrite, (req, res) => _proxy(req, res, '/deployment/rollback', req.body, 'POST'));
router.get('/history',      sysRead,  (req, res) => _proxy(req, res, '/deployment/history'));
router.post('/blue-green',  sysWrite, (req, res) => _proxy(req, res, '/deployment/blue-green', req.body, 'POST'));
router.get('/metrics',      sysRead,  (req, res) => _proxy(req, res, '/deployment/metrics'));
router.post('/drain',       sysWrite, (req, res) => {
  const qs = new URLSearchParams({ node: req.query.node || '' }).toString();
  _proxy(req, res, `/deployment/drain?${qs}`, null, 'POST');
});

module.exports = router;
