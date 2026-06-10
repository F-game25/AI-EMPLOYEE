'use strict';
/**
 * /api/evolution — Evolution Engine (Node side of the offline learning engine).
 * All learning logic lives in runtime/evolution/{controller,candidate_registry,
 * reflection_engine,...}.py. This file only shuttles JSON between HTTP and the
 * persistent Python worker, and reflects promote/rollback onto the WS bus.
 *
 * Ops mapped 1:1 to EvolutionController.handle_evolution_op (the only ops it
 * implements): status / traces / lessons / candidates / promote / rollback.
 * candidate_test (standalone replay) and candidate_reject are NOT implemented
 * by the controller, so they are intentionally not exposed here.
 */

const express = require('express');
const { getWorker } = require('../py_worker_client');

const w = () => getWorker(); // resolved lazily so the module loads before the worker is ready

// Lazy broadcast helper — avoids circular require with server.js (matches companion.js).
function _broadcast(event, data) {
  try {
    require('../events/broadcaster').broadcast(event, { ...data, ts: Date.now() });
  } catch { /* WS not ready — non-fatal */ }
}

module.exports = function createEvolutionRouter(requireAuth) {
  const r = express.Router();

  // GET /api/evolution/status
  r.get('/status', requireAuth, async (req, res) => {
    try {
      const result = await w().call('evolution.status', {}, 10_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, enabled: false, error: err.message });
    }
  });

  // GET /api/evolution/traces?limit=50
  r.get('/traces', requireAuth, async (req, res) => {
    try {
      const limit = Number(req.query.limit) || 50;
      const result = await w().call('evolution.traces', { limit }, 15_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, traces: [], error: err.message });
    }
  });

  // GET /api/evolution/lessons?limit=50
  r.get('/lessons', requireAuth, async (req, res) => {
    try {
      const limit = Number(req.query.limit) || 50;
      const result = await w().call('evolution.lessons', { limit }, 15_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, lessons: [], error: err.message });
    }
  });

  // GET /api/evolution/candidates?status=&limit=50
  r.get('/candidates', requireAuth, async (req, res) => {
    try {
      const args = { limit: Number(req.query.limit) || 50 };
      if (req.query.status) args.status = String(req.query.status);
      const result = await w().call('evolution.candidates', args, 15_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, candidates: [], error: err.message });
    }
  });

  // POST /api/evolution/candidates/:id/promote
  // Controller op 'promote' replays + runs the promotion gate, and on success
  // updates the registry + rollback artifact. Broadcasts on a real promotion.
  r.post('/candidates/:id/promote', requireAuth, async (req, res) => {
    try {
      const candidate_id = req.params.id;
      const result = await w().call('evolution.candidate_promote', { candidate_id }, 120_000);
      if (result?.ok && result?.decision?.promote) {
        _broadcast('evolution:candidate_promoted', { candidate_id, decision: result.decision });
      }
      res.status(result?.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ok: false, error: err.message });
    }
  });

  // POST /api/evolution/candidates/:id/rollback
  // Controller op 'rollback' reverts a promoted target. The candidate id is
  // forwarded for traceability; target (optional) + trigger drive the revert.
  r.post('/candidates/:id/rollback', requireAuth, async (req, res) => {
    try {
      const candidate_id = req.params.id;
      const args = { candidate_id, trigger: req.body?.trigger || 'manual' };
      if (req.body?.target) args.target = String(req.body.target);
      const result = await w().call('evolution.candidate_rollback', args, 60_000);
      if (result?.ok) {
        _broadcast('evolution:rollback_triggered', { candidate_id, trigger: args.trigger });
      }
      res.status(result?.ok === false ? 502 : 200).json(result);
    } catch (err) {
      res.status(503).json({ ok: false, error: err.message });
    }
  });

  return r;
};
