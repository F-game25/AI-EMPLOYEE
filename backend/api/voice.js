'use strict';

const { Router } = require('express');
const voiceManager = require('../core/voice_manager');
const { VOICE_PROFILES } = require('../services/voice/tts_engine');

const router = Router();

// GET /api/voice/config
// Returns the current voice configuration and available profiles/tones.
router.get('/config', (_req, res) => {
  res.json({
    config: voiceManager.getConfig(),
    profiles: Object.keys(VOICE_PROFILES),
    tones: ['futuristic', 'neutral', 'calm', 'sharp'],
    verbosity_levels: {
      0: 'silent',
      1: 'critical',
      2: 'important',
      3: 'normal',
      4: 'verbose',
    },
  });
});

// POST /api/voice/config
// Accepts a partial config patch and applies it immediately.
router.post('/config', (req, res) => {
  const patch = req.body;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    return res.status(400).json({ ok: false, error: 'Body must be a JSON object.' });
  }
  try {
    voiceManager.applyConfig(patch);
    res.json({ ok: true, config: voiceManager.getConfig() });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

// POST /api/voice/test
// Speaks a short test phrase using the current voice settings.
router.post('/test', async (_req, res) => {
  try {
    const cfg = voiceManager.getConfig();
    if (!cfg.enabled) {
      return res.json({ ok: false, message: 'Voice is disabled.' });
    }
    void voiceManager.speak('Voice system online. All systems operational.', true);
    res.json({ ok: true, message: 'Test phrase dispatched.' });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err.message || err) });
  }
});

module.exports = router;
