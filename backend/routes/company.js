'use strict';
/**
 * /api/company — CompanyOS (Master Plan V3 — P10). The validate-before-build
 * AI company-builder. Thin HTTP shell over the Python worker (`company.*` ops);
 * all lifecycle logic lives in runtime/companyos/*.
 *
 * Anti-Polsia guarantee reflected here: /build returns blocked:true (HTTP 409)
 * unless validation returned 'build' or an explicit override+reason is supplied.
 * Nothing is fabricated; the worker returns honest verdicts/status.
 */
const express = require('express');
const { getWorker } = require('../py_worker_client');

const w = () => getWorker();
const _offline = { ok: false, error: 'AI backend offline' };

module.exports = function createCompanyRouter(requireAuth) {
  const r = express.Router();

  // POST /api/company — start a company from an idea (intake; does not build)
  r.post('/', requireAuth, async (req, res) => {
    try {
      const b = req.body || {};
      const result = await w().call('company.start',
        { name: b.name, idea: b.idea, answers: b.answers }, 60_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // GET /api/company — list companies
  r.get('/', requireAuth, async (_req, res) => {
    try {
      res.json(await w().call('company.list', {}, 15_000));
    } catch (err) {
      res.status(503).json({ ..._offline, companies: [], detail: err.message });
    }
  });

  // GET /api/company/:id
  r.get('/:id', requireAuth, async (req, res) => {
    try {
      const result = await w().call('company.get', { id: req.params.id }, 15_000);
      res.status(result && result.ok === false ? 404 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/company/:id/validate — the demand-validation gate (can refuse)
  r.post('/:id/validate', requireAuth, async (req, res) => {
    try {
      const result = await w().call('company.validate', { id: req.params.id }, 120_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/company/refine — turn a weak idea into a buildable one (no company needed)
  r.post('/refine', requireAuth, async (req, res) => {
    try {
      const result = await w().call('company.refine', { idea: (req.body || {}).idea || '' }, 120_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/company/:id/build — blocked unless validated 'build' or explicit override
  r.post('/:id/build', requireAuth, async (req, res) => {
    try {
      const b = req.body || {};
      const result = await w().call('company.build',
        { id: req.params.id, override: Boolean(b.override), override_reason: b.override_reason }, 30_000);
      if (result && result.blocked) return res.status(409).json(result); // refused: validate first
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  return r;
};
