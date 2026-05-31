'use strict';

const { Router } = require('express');
const voiceManager = require('../core/voice_manager');
const callEngine = require('../services/voice/call_engine');
const { VOICE_PROFILES } = require('../services/voice/tts_engine');
const personaplex = require('../services/voice/nvidia_personaplex');
const fishSpeech = require('../services/voice/fish_speech');

const router = Router();

// ── System voice ──────────────────────────────────────────────────────────────

// GET /api/voice/config
router.get('/config', async (_req, res) => {
  const profiles = Object.keys(VOICE_PROFILES);
  const pipeline = voiceManager.getPipeline();
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  const fishAvailable = await fishSpeech.checkAvailability();
  res.json({
    config: cfg,
    profiles: profiles.filter((p) => !p.startsWith('customer_')),
    customer_profiles: profiles.filter((p) => p.startsWith('customer_')),
    tones: ['futuristic', 'neutral', 'calm', 'sharp'],
    customer_tones: ['warm', 'professional'],
    providers: [
      {
        id: 'fish_speech',
        label: 'Fish Speech S2 Local',
        status: fishAvailable ? 'live' : 'unavailable',
        local: true,
        docs_hint: 'Run Fish Speech locally on 127.0.0.1:8080 for natural system-owned voice.',
      },
      {
        id: 'local',
        label: 'Local OS voice fallback',
        status: voiceManager.getEngineStatus().silent ? 'unavailable' : 'fallback',
        local: true,
        docs_hint: 'Uses installed OS TTS commands such as espeak-ng, say, or spd-say.',
      },
      {
        id: 'personaplex',
        label: 'Nvidia PersonaPlex',
        status: personaplex.isAvailable() ? 'live' : 'not_configured',
        local: false,
        docs_hint: 'Legacy optional cloud voice route. Fish Speech is preferred for local ownership.',
      },
    ],
    verbosity_levels: { 0: 'silent', 1: 'critical', 2: 'important', 3: 'normal', 4: 'verbose' },
    mode: voiceManager.getMode(),
    pipeline: pipeline.getOptions(),
    engine: voiceManager.getEngineStatus(),
    fish_speech: fishSpeech.getStatus(),
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
    const cfg = voiceManager.getConfig();
    fishSpeech.configure(cfg.fishSpeech || {});
    res.json({ ok: true, config: cfg, engine: voiceManager.getEngineStatus(), fish_speech: fishSpeech.getStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/test
router.post('/test', async (req, res) => {
  try {
    const cfg = voiceManager.getConfig();
    if (!cfg.enabled) return res.json({ ok: false, message: 'Voice is disabled.' });
    const text = String(req.body?.text || 'Voice system online. Fish Speech local voice route ready.').slice(0, 500);
    void voiceManager.speak(text, true);
    res.json({
      ok: true,
      message: 'Test phrase dispatched.',
      provider: cfg.provider || 'fish_speech',
      fish_speech: fishSpeech.getStatus(),
      engine: voiceManager.getEngineStatus(),
    });
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

// ── Local Fish Speech S2 + legacy PersonaPlex synthesis ───────────────────────

// POST /api/voice/synthesize
// Body: { text: string, provider?: 'fish_speech'|'personaplex', persona?: {...} }
// Returns audio/wav binary on success, or JSON error.
router.post('/synthesize', async (req, res) => {
  const { text, persona = {}, provider } = req.body || {};
  if (!text || typeof text !== 'string' || !text.trim()) {
    return res.status(400).json({ ok: false, error: 'text is required.' });
  }
  const cfg = voiceManager.getConfig();
  const selectedProvider = provider || persona.provider || cfg.provider || 'fish_speech';

  if (selectedProvider === 'fish_speech') {
    fishSpeech.configure({ ...(cfg.fishSpeech || {}), ...(persona.fishSpeech || {}) });
    const fishAvailable = await fishSpeech.checkAvailability();
    if (!fishAvailable) {
      return res.status(503).json({
        ok: false,
        provider: 'fish_speech',
        status: 'unavailable',
        error: fishSpeech.getStatus().last_error || 'Fish Speech S2 local server is not reachable.',
        setup: 'Start the local Fish Speech server on http://127.0.0.1:8080, then retry.',
        fallback: cfg.fishSpeech?.localFallback ? 'local_os_voice' : 'disabled',
      });
    }
    try {
      const audioBuf = await fishSpeech.synthesize(text.trim(), {
        ...(cfg.fishSpeech || {}),
        ...(persona.fishSpeech || {}),
      });
      const artifact = fishSpeech.saveArtifact(audioBuf, cfg.fishSpeech || {});
      res.setHeader('Content-Type', contentTypeFor(cfg.fishSpeech?.format || 'wav'));
      res.setHeader('Content-Length', audioBuf.length);
      res.setHeader('X-Voice-Provider', 'fish_speech_s2_local');
      res.setHeader('X-Voice-Artifact-Id', artifact.id);
      res.setHeader('X-Voice-Artifact-Url', artifact.url);
      return res.send(audioBuf);
    } catch (err) {
      return res.status(500).json({ ok: false, provider: 'fish_speech', error: String(err.message || err) });
    }
  }

  if (selectedProvider === 'local') {
    return res.status(501).json({
      ok: false,
      provider: 'local',
      status: 'fallback',
      error: 'Local OS voice fallback can play on the server, but cannot return browser-playable synthesized audio.',
      setup: 'Use /api/voice/test for server playback, or switch to Fish Speech S2 for browser audio artifacts.',
    });
  }

  if (!personaplex.isAvailable()) {
    return res.status(503).json({
      ok: false,
      provider: 'personaplex',
      status: 'not_configured',
      error: 'Nvidia PersonaPlex is not configured. Set NVIDIA_API_KEY, or use provider fish_speech for local voice.',
    });
  }
  try {
    const audioBuf = await personaplex.synthesize(text.trim(), persona);
    res.setHeader('Content-Type', 'audio/wav');
    res.setHeader('Content-Length', audioBuf.length);
    res.send(audioBuf);
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

function contentTypeFor(format) {
  if (format === 'mp3') return 'audio/mpeg';
  if (format === 'opus') return 'audio/ogg';
  if (format === 'pcm') return 'application/octet-stream';
  return 'audio/wav';
}

// GET /api/voice/status
router.get('/status', async (_req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  await fishSpeech.checkAvailability();
  res.json({
    ok: true,
    provider: cfg.provider || 'fish_speech',
    mode: voiceManager.getMode(),
    enabled: Boolean(cfg.enabled),
    engine: voiceManager.getEngineStatus(),
    fish_speech: fishSpeech.getStatus(),
    personaplex: {
      available: personaplex.isAvailable(),
      configured: Boolean(process.env.NVIDIA_API_KEY || process.env.NVIDIA_PERSONAPLEX_KEY),
      model: 'nvidia/personaplex-tts-v1',
    },
  });
});

// GET /api/voice/fish-speech/status
router.get('/fish-speech/status', async (_req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure(cfg.fishSpeech || {});
  await fishSpeech.checkAvailability();
  res.json(fishSpeech.getStatus());
});

// POST /api/voice/fish-speech/test
router.post('/fish-speech/test', async (req, res) => {
  const cfg = voiceManager.getConfig();
  fishSpeech.configure({ ...(cfg.fishSpeech || {}), ...(req.body?.fishSpeech || {}) });
  const available = await fishSpeech.checkAvailability();
  if (!available) {
    return res.status(503).json({
      ok: false,
      provider: 'fish_speech',
      status: 'unavailable',
      error: fishSpeech.getStatus().last_error,
      setup: 'Start the local Fish Speech server on http://127.0.0.1:8080.',
    });
  }
  try {
    const text = String(req.body?.text || 'Fish Speech S2 local voice test.').slice(0, 500);
    const audioBuf = await fishSpeech.synthesize(text, cfg.fishSpeech || {});
    const artifact = fishSpeech.saveArtifact(audioBuf, cfg.fishSpeech || {});
    res.json({ ok: true, provider: 'fish_speech', artifact, status: fishSpeech.getStatus() });
  } catch (err) {
    res.status(500).json({ ok: false, provider: 'fish_speech', error: String(err.message || err) });
  }
});

// GET /api/voice/personaplex/status
router.get('/personaplex/status', async (_req, res) => {
  const available = await personaplex.checkAvailability();
  res.json({
    available,
    configured: Boolean(process.env.NVIDIA_API_KEY || process.env.NVIDIA_PERSONAPLEX_KEY),
    model: 'nvidia/personaplex-tts-v1',
    tones: Object.keys(personaplex.TONE_STYLE_MAP),
    genders: Object.keys(personaplex.GENDER_VOICE_MAP),
    defaults: personaplex.DEFAULT_PERSONA,
  });
});

module.exports = router;
