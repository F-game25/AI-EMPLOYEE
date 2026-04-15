'use strict';

const { Router } = require('express');
const voiceManager = require('../core/voice_manager');
const callEngine = require('../services/voice/call_engine');
const { VOICE_PROFILES } = require('../services/voice/tts_engine');

const router = Router();

// ── System voice ──────────────────────────────────────────────────────────────

// GET /api/voice/config
router.get('/config', (_req, res) => {
  const profiles = Object.keys(VOICE_PROFILES);
  const pipeline = voiceManager.getPipeline();
  res.json({
    config: voiceManager.getConfig(),
    profiles: profiles.filter((p) => !p.startsWith('customer_')),
    customer_profiles: profiles.filter((p) => p.startsWith('customer_')),
    tones: ['futuristic', 'neutral', 'calm', 'sharp'],
    customer_tones: ['warm', 'professional'],
    verbosity_levels: { 0: 'silent', 1: 'critical', 2: 'important', 3: 'normal', 4: 'verbose' },
    mode: voiceManager.getMode(),
    pipeline: pipeline.getOptions(),
  });
});

// POST /api/voice/config
router.post('/config', (req, res) => {
  const patch = req.body;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    return res.status(400).json({ ok: false, error: 'Body must be a JSON object.' });
  }
  try {
    voiceManager.applyConfig(patch);
    // If pipeline settings are included, apply them too
    if (patch.pipeline && typeof patch.pipeline === 'object') {
      voiceManager.getPipeline().configure(patch.pipeline);
    }
    res.json({ ok: true, config: voiceManager.getConfig() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/test
router.post('/test', async (_req, res) => {
  try {
    const cfg = voiceManager.getConfig();
    if (!cfg.enabled) return res.json({ ok: false, message: 'Voice is disabled.' });
    void voiceManager.speak('Voice system online. All systems operational.', true);
    res.json({ ok: true, message: 'Test phrase dispatched.' });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// ── Mode switching ────────────────────────────────────────────────────────────

// POST /api/voice/mode   { mode: 'system' | 'customer' }
router.post('/mode', (req, res) => {
  const { mode } = req.body || {};
  if (mode !== 'system' && mode !== 'customer') {
    return res.status(400).json({ ok: false, error: 'mode must be "system" or "customer".' });
  }
  voiceManager.setMode(mode);
  res.json({ ok: true, mode: voiceManager.getMode() });
});

// GET /api/voice/mode
router.get('/mode', (_req, res) => {
  res.json({ mode: voiceManager.getMode() });
});

// ── Pipeline control ──────────────────────────────────────────────────────────

// GET /api/voice/pipeline
// Returns current pipeline settings and speaking status.
router.get('/pipeline', (_req, res) => {
  const pipeline = voiceManager.getPipeline();
  res.json({
    options: pipeline.getOptions(),
    speaking: pipeline.isSpeaking(),
    interrupted: pipeline.isInterrupted(),
  });
});

// POST /api/voice/pipeline/config
// Update pipeline settings (microPauseMs, thinkingDelayMs, preRollEnabled, etc.)
router.post('/pipeline/config', (req, res) => {
  const patch = req.body;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    return res.status(400).json({ ok: false, error: 'Body must be a JSON object.' });
  }
  try {
    voiceManager.getPipeline().configure(patch);
    res.json({ ok: true, options: voiceManager.getPipeline().getOptions() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/pipeline/interrupt
// Immediately stop all speech (manual override — works for both system and call sessions).
router.post('/pipeline/interrupt', async (_req, res) => {
  try {
    await voiceManager.getPipeline().interrupt();
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/pipeline/preroll   { type?, channel? }
// Speak an immediate filler phrase.
router.post('/pipeline/preroll', async (req, res) => {
  const { type = 'thinking', channel } = req.body || {};
  try {
    const phrase = await voiceManager.getPipeline().preRoll(type, channel || voiceManager.getMode());
    res.json({ ok: true, phrase });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// ── Customer call control ─────────────────────────────────────────────────────

// POST /api/voice/calls/start   { sessionId, greeting?, profile? }
router.post('/calls/start', async (req, res) => {
  const { sessionId, greeting, profile } = req.body || {};
  if (!sessionId) return res.status(400).json({ ok: false, error: 'sessionId is required.' });

  const cfg = voiceManager.getConfig();
  if (!cfg.customer?.enabled) {
    return res.status(403).json({ ok: false, error: 'Customer voice is disabled.' });
  }

  try {
    const session = await voiceManager.triggerCall(sessionId, {
      greeting,
      profile: profile || cfg.customer?.profile || 'customer_default',
    });
    res.json({ ok: true, session: session || { sessionId } });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/speak   { text }
router.post('/calls/:sessionId/speak', async (req, res) => {
  const { sessionId } = req.params;
  const { text } = req.body || {};
  if (!text) return res.status(400).json({ ok: false, error: 'text is required.' });
  if (!callEngine.isActive(sessionId)) {
    return res.status(404).json({ ok: false, error: `No active call session: ${sessionId}` });
  }
  try {
    await callEngine.speak(sessionId, text);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/interrupt
router.post('/calls/:sessionId/interrupt', async (req, res) => {
  const { sessionId } = req.params;
  try {
    await callEngine.interrupt(sessionId);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/calls/:sessionId/end
router.post('/calls/:sessionId/end', async (req, res) => {
  const { sessionId } = req.params;
  try {
    await voiceManager.stopCall(sessionId);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// GET /api/voice/calls
router.get('/calls', (_req, res) => {
  res.json({ sessions: callEngine.listActiveSessions() });
});

// POST /api/voice/calls/test  — test customer voice phrase
router.post('/calls/test', async (req, res) => {
  const cfg = voiceManager.getConfig();
  if (!cfg.customer?.enabled) {
    return res.json({ ok: false, message: 'Customer voice is disabled.' });
  }
  const sid = `test-${Date.now()}`;
  try {
    await callEngine.startCall(sid, {
      profile: cfg.customer?.profile || 'customer_default',
      greeting: 'Hello! This is a customer voice test. Everything sounds great.',
    });
    await callEngine.endCall(sid, 'user_ended');
    res.json({ ok: true, message: 'Customer voice test dispatched.' });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

module.exports = router;
