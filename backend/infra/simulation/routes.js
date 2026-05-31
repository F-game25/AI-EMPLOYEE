'use strict';

/**
 * Simulation + Testing API routes.
 *
 * GET  /api/simulation/scenarios              — list scenarios
 * POST /api/simulation/run                    — start scenario run
 * GET  /api/simulation/runs/:id              — run status
 * GET  /api/simulation/runs/:id/results      — full results
 * GET  /api/simulation/runs/:id/risk         — risk score
 * POST /api/simulation/adversarial           — run adversarial suite on agent
 * GET  /api/simulation/synthetic-users       — list personas
 * POST /api/simulation/digital-twins/:sys    — configure mock system
 * POST /api/simulation/replay                — replay production trace
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy } = require('../proxy');

const router = Router();
const _proxy = makeProxy('Simulation', 120000);

const sysRead  = requirePermission(PERMISSIONS.SYSTEM_READ);
const sysWrite = requirePermission(PERMISSIONS.SYSTEM_CONFIGURE);

router.get('/scenarios',                     sysRead,  (req, res) => _proxy(req, res, '/simulation/scenarios'));
router.post('/run',                          sysWrite, (req, res) => _proxy(req, res, '/simulation/run', req.body, 'POST'));
router.get('/runs/:id',                      sysRead,  (req, res) => _proxy(req, res, `/simulation/runs/${req.params.id}`));
router.get('/runs/:id/results',              sysRead,  (req, res) => _proxy(req, res, `/simulation/runs/${req.params.id}/results`));
router.get('/runs/:id/risk',                 sysRead,  (req, res) => _proxy(req, res, `/simulation/runs/${req.params.id}/risk`));
router.post('/adversarial',                  sysWrite, (req, res) => _proxy(req, res, '/simulation/adversarial', req.body, 'POST'));
router.get('/synthetic-users',               sysRead,  (req, res) => _proxy(req, res, '/simulation/synthetic-users'));
router.post('/digital-twins/:sys',           sysWrite, (req, res) => _proxy(req, res, `/simulation/digital-twins/${req.params.sys}`, req.body, 'POST'));
router.post('/replay',                       sysWrite, (req, res) => _proxy(req, res, '/simulation/replay', req.body, 'POST'));

module.exports = router;
