/**
 * PHASE 4 COGNITIVE ROUTES PROXY
 * Node.js proxy layer for all /api/cognitive/* requests
 * Routes to Python backend with tenant validation
 */
'use strict';

const { Router } = require('express');
const { requirePermission } = require('../rbac/policy');
const { PERMISSIONS } = require('../rbac/roles');
const { makeProxy } = require('../proxy');

const router = Router();
const _proxy = makeProxy('Cognitive', 30000);

// Permission middleware
const read = requirePermission(PERMISSIONS.SYSTEM_READ);
const write = requirePermission(PERMISSIONS.SYSTEM_CONFIGURE);

// All cognitive subsystem routes forward to Python with matching paths
router.get('/*', read, (req, res) => {
  _proxy(req, res, `/cognitive${req.path}`);
});

router.post('/*', write, (req, res) => {
  _proxy(req, res, `/cognitive${req.path}`, req.body, 'POST');
});

router.patch('/*', write, (req, res) => {
  _proxy(req, res, `/cognitive${req.path}`, req.body, 'PATCH');
});

router.delete('/*', write, (req, res) => {
  _proxy(req, res, `/cognitive${req.path}`, null, 'DELETE');
});

module.exports = router;
