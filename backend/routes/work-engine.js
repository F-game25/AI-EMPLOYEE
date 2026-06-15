'use strict';
/**
 * /api/work — Work Acquisition + Delivery Engine (Master Plan V3 — Module 4).
 *
 * Thin HTTP shell over the persistent Python worker (`work.*` ops). All
 * lifecycle/business logic lives in runtime/money/work_engine/*. This file only
 * shuttles JSON and degrades gracefully (503) when the worker is unreachable.
 *
 * Governance reflected here: the quote + deliver steps are HARD HITL gates — the
 * Python engine returns `status: 'pending_approval'` + a gate id; nothing is
 * auto-sent. Monetary figures come back labelled `is_estimate: true`.
 */
const express = require('express');
const { getWorker } = require('../py_worker_client');

const w = () => getWorker(); // resolved lazily so the module loads before the worker

const _offline = { ok: false, error: 'AI backend offline' };

module.exports = function createWorkEngineRouter(requireAuth) {
  const r = express.Router();

  // POST /api/work/opportunities — ingest a new opportunity
  r.post('/opportunities', requireAuth, async (req, res) => {
    try {
      const opportunity = req.body && req.body.opportunity ? req.body.opportunity : (req.body || {});
      const result = await w().call('work.ingest', { opportunity }, 30_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // GET /api/work/opportunities[?status=] — list opportunities
  r.get('/opportunities', requireAuth, async (req, res) => {
    try {
      const result = await w().call('work.list', { status: req.query.status || null }, 15_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, opportunities: [], detail: err.message });
    }
  });

  // GET /api/work/opportunities/:id — fetch one
  r.get('/opportunities/:id', requireAuth, async (req, res) => {
    try {
      const result = await w().call('work.get', { id: req.params.id }, 15_000);
      res.status(result && result.ok === false ? 404 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/work/opportunities/:id/evaluate — fit/value/effort/risk
  r.post('/opportunities/:id/evaluate', requireAuth, async (req, res) => {
    try {
      const use_llm = req.body && req.body.use_llm !== undefined ? Boolean(req.body.use_llm) : true;
      const result = await w().call('work.evaluate', { id: req.params.id, use_llm }, 60_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/work/opportunities/:id/quote — HARD HITL GATE 1 (never auto-sends)
  r.post('/opportunities/:id/quote', requireAuth, async (req, res) => {
    try {
      const claims = req.jwtPayload || req.user || {};
      const submitted_by = claims.sub || claims.email || claims.id || 'work-engine';
      const result = await w().call('work.quote', { id: req.params.id, submitted_by }, 60_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  // POST /api/work/opportunities/:id/deliver — HARD HITL GATE 2 (never auto-submits)
  r.post('/opportunities/:id/deliver', requireAuth, async (req, res) => {
    try {
      const claims = req.jwtPayload || req.user || {};
      const submitted_by = claims.sub || claims.email || claims.id || 'work-engine';
      const result = await w().call('work.deliver', { id: req.params.id, submitted_by }, 120_000);
      res.status(result && result.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ..._offline, detail: err.message });
    }
  });

  return r;
};
