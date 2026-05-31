'use strict';

/**
 * RPA / Browser Control API routes.
 *
 * POST /api/rpa/sessions                      — spawn browser session
 * GET  /api/rpa/sessions                      — list sessions
 * DELETE /api/rpa/sessions/:id                — terminate session
 * POST /api/rpa/sessions/:id/action           — execute single action
 * POST /api/rpa/sessions/:id/workflow         — execute action list
 * POST /api/rpa/sessions/:id/takeover         — return CDP URL for human control
 * GET  /api/rpa/sessions/:id/screenshot       — current viewport PNG (base64)
 * GET  /api/rpa/sessions/:id/replay           — JSONL replay frames
 * POST /api/rpa/workflows                     — save named workflow
 * GET  /api/rpa/workflows                     — list workflows
 * POST /api/rpa/workflows/:id/run             — run saved workflow
 */

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy } = require('../proxy');

const router = Router();
const _proxy = makeProxy('RPA', 60000);

// Require AGENT_RUN permission for all RPA operations
const rpaGuard = requirePermission(PERMISSIONS.AGENT_RUN);

router.post('/sessions',           rpaGuard, (req, res) => _proxy(req, res, '/rpa/sessions', req.body, 'POST'));
router.get('/sessions',            rpaGuard, (req, res) => _proxy(req, res, '/rpa/sessions'));
router.delete('/sessions/:id',     rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}`, null, 'DELETE'));
router.post('/sessions/:id/action',   rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}/action`, req.body, 'POST'));
router.post('/sessions/:id/workflow', rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}/workflow`, req.body, 'POST'));
router.post('/sessions/:id/takeover', rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}/takeover`, {}, 'POST'));
router.get('/sessions/:id/screenshot', rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}/screenshot`));
router.get('/sessions/:id/replay',     rpaGuard, (req, res) => _proxy(req, res, `/rpa/sessions/${req.params.id}/replay`));

router.post('/workflows',        rpaGuard, (req, res) => _proxy(req, res, '/rpa/workflows', req.body, 'POST'));
router.get('/workflows',         rpaGuard, (req, res) => _proxy(req, res, '/rpa/workflows'));
router.post('/workflows/:id/run', rpaGuard, (req, res) => _proxy(req, res, `/rpa/workflows/${req.params.id}/run`, req.body, 'POST'));

module.exports = router;
