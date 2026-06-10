'use strict';
/**
 * /api/companion — Companion Gateway (Node side of the companion runtime).
 * All conversation logic lives in runtime/companion/{conversation_runtime,
 * capability_registry}.py. This file only shuttles JSON between HTTP and the
 * persistent Python worker, and reflects avatar-state changes onto the WS bus.
 */

const express = require('express');
const { getWorker } = require('../py_worker_client');

const w = () => getWorker(); // resolved lazily so the module loads before the worker is ready

// Lazy broadcast helper — avoids circular require with server.js (matches quantum.js).
function _broadcast(event, data) {
  try {
    require('../events/broadcaster').broadcast(event, { ...data, ts: Date.now() });
  } catch { /* WS not ready — non-fatal */ }
}

// Last known companion/avatar state, served by GET /api/companion/state.
let _lastState = { state: 'idle' };

// Graceful payload when the Python worker is down/unreachable.
const _offline = { ok: false, reply: 'AI backend offline', avatar_state: 'error' };

module.exports = function createCompanionRouter(requireAuth) {
  const r = express.Router();

  // POST /api/companion/message
  r.post('/message', requireAuth, async (req, res) => {
    try {
      const { text, session_id, channel, context } = req.body || {};
      if (!text || typeof text !== 'string')
        return res.status(400).json({ ok: false, error: 'text is verplicht' });
      const resp = await w().call('companion.message', { text, session_id, channel, context }, 120_000);
      if (resp && resp.avatar_state) {
        _lastState = { state: resp.avatar_state, session_id: session_id || null, mode: resp.mode || null };
        _broadcast('companion:avatar_state_changed', _lastState);
      }
      res.status(resp?.ok === false ? 502 : 200).json(resp);
    } catch (err) {
      // Worker down/timeout — degrade gracefully so the UI stays responsive.
      _lastState = { state: 'error' };
      _broadcast('companion:avatar_state_changed', _lastState);
      res.status(503).json({ ..._offline, error: err.message });
    }
  });

  // GET /api/companion/capabilities
  r.get('/capabilities', requireAuth, async (req, res) => {
    try {
      const result = await w().call('companion.capabilities', {}, 10_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, capabilities: [], error: err.message });
    }
  });

  // GET /api/companion/state — last known companion/avatar state
  r.get('/state', requireAuth, (req, res) => {
    res.json({ ok: true, ..._lastState });
  });

  return r;
};
