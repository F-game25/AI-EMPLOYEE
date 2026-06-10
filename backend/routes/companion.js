'use strict';
/**
 * /api/companion — Companion Gateway (Node side of the companion runtime).
 * All conversation logic lives in runtime/companion/{conversation_runtime,
 * capability_registry}.py. This file only shuttles JSON between HTTP and the
 * persistent Python worker, and reflects avatar-state changes onto the WS bus.
 */

const express = require('express');
const { getWorker } = require('../py_worker_client');
const voiceManager = require('../core/voice_manager');

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

// Pick the concise spoken text: prefer the runtime's voice_summary, else the
// full reply. Reuse the EXISTING voice manager to synthesize — never reimplement.
function _spokenText(resp) {
  const summary = resp?.meta?.voice_summary;
  return String((summary && summary.trim()) || resp?.reply || '').trim();
}

// Fire-and-forget TTS via the existing voice manager. Defensive: if voice is
// unavailable the text response still returns; only the spoken layer degrades.
async function _speak(text) {
  const phrase = String(text || '').trim();
  if (!phrase) return { ok: false, reason: 'empty' };
  try {
    // priority=true → flush queue + interrupt current speech, then stream.
    const spoke = await voiceManager.speak(phrase, true);
    return { ok: spoke !== false, spoke };
  } catch (err) {
    return { ok: false, reason: String(err.message || err) };
  }
}

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

  // POST /api/companion/voice-message
  // Body: { transcript, session_id?, context?, speak?: true }
  // STT transcript → companion gateway (channel='voice') → concise spoken reply.
  r.post('/voice-message', requireAuth, async (req, res) => {
    const { transcript, session_id, context, speak = true } = req.body || {};
    if (!transcript || typeof transcript !== 'string' || !transcript.trim())
      return res.status(400).json({ ok: false, error: 'transcript is verplicht' });

    // Avatar goes 'thinking' the moment we start processing (backend-driven).
    _lastState = { state: 'thinking', session_id: session_id || null, mode: null };
    _broadcast('companion:avatar_state_changed', _lastState);

    let resp;
    try {
      resp = await w().call(
        'companion.message',
        { text: transcript.trim(), channel: 'voice', session_id, context },
        120_000,
      );
    } catch (err) {
      _lastState = { state: 'error' };
      _broadcast('companion:avatar_state_changed', _lastState);
      return res.status(503).json({ ..._offline, error: err.message });
    }

    // Reflect the runtime's own avatar state (e.g. approval_needed) onto the bus.
    if (resp && resp.avatar_state) {
      _lastState = { state: resp.avatar_state, session_id: session_id || null, mode: resp.mode || null };
      _broadcast('companion:avatar_state_changed', _lastState);
    }

    const spokenText = _spokenText(resp);
    let voice = { requested: Boolean(speak), spoken: false, text: spokenText };

    if (speak && resp?.ok !== false && spokenText) {
      // Speaking lifecycle is broadcast so the avatar syncs to BACKEND events.
      _broadcast('companion:voice_response_started', { session_id: session_id || null, text: spokenText });
      const result = await _speak(spokenText);
      voice.spoken = result.ok;
      if (!result.ok) voice.error = result.reason;
      _broadcast('companion:voice_response_finished', { session_id: session_id || null, spoken: result.ok });
    }

    res.status(resp?.ok === false ? 502 : 200).json({ ...resp, voice });
  });

  // POST /api/companion/voice-control — barge-in / playback commands.
  // Body: { action: 'stop'|'pause'|'resume'|'cancel' }
  r.post('/voice-control', requireAuth, async (req, res) => {
    const action = String(req.body?.action || '').toLowerCase();
    if (!['stop', 'pause', 'resume', 'cancel'].includes(action))
      return res.status(400).json({ ok: false, error: "action must be 'stop'|'pause'|'resume'|'cancel'" });

    try {
      if (action === 'stop' || action === 'cancel') {
        // Reuse the existing stop mechanism: flush the queue + interrupt speech.
        await voiceManager.clearQueue();
        _broadcast('companion:voice_interrupted', { action });
        _lastState = { state: 'idle' };
        _broadcast('companion:avatar_state_changed', _lastState);
      } else if (action === 'pause') {
        // No native pause in the streaming pipeline — interrupt is the safe stop.
        await voiceManager.getPipeline().interrupt();
        _broadcast('companion:voice_interrupted', { action });
      }
      // 'resume' is a no-op: the next voice-message re-synthesizes fresh.
      res.json({ ok: true, action, speaking: voiceManager.isSpeaking() });
    } catch (err) {
      res.status(500).json({ ok: false, action, error: String(err.message || err) });
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
