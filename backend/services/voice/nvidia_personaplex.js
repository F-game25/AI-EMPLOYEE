'use strict';

const https = require('https');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const NVIDIA_API_BASE = 'https://integrate.api.nvidia.com/v1';
const PERSONAPLEX_MODEL = 'nvidia/personaplex-tts-v1';

const DEFAULT_PERSONA = {
  gender:       'neutral',      // 'male' | 'female' | 'neutral'
  tone:         'professional', // see TONES list
  pitch:        1.0,            // 0.5 – 2.0
  speed:        1.0,            // 0.5 – 2.0
  articulation: 0.7,            // 0 – 1  (0 = soft/breathy, 1 = crisp/sharp)
  friendliness: 0.6,            // 0 – 1  (0 = cold/formal, 1 = warm/inviting)
};

// Internal style identifiers sent to Nvidia API
const TONE_STYLE_MAP = {
  authoritative: 'authority',
  warm:          'warmth',
  cheerful:      'cheerful',
  calm:          'calm',
  professional:  'professional',
  casual:        'casual',
  empathetic:    'empathetic',
  robotic:       'precise',
};

const GENDER_VOICE_MAP = {
  male:    { voice: 'pm_persona_m1', gender: 'male' },
  female:  { voice: 'pm_persona_f1', gender: 'female' },
  neutral: { voice: 'pm_persona_n1', gender: 'neutral' },
};

let _apiKey = null;
let _available = false;
let _lastCheck = 0;
const RECHECK_MS = 60_000;

function getApiKey() {
  if (!_apiKey) _apiKey = process.env.NVIDIA_API_KEY || process.env.NVIDIA_PERSONAPLEX_KEY || null;
  return _apiKey;
}

function isAvailable() {
  return _available && Boolean(getApiKey());
}

async function checkAvailability() {
  if (Date.now() - _lastCheck < RECHECK_MS) return _available;
  _lastCheck = Date.now();
  const key = getApiKey();
  if (!key) { _available = false; return false; }
  try {
    const result = await _request('GET', '/audio/speech/health', null, key, 5000);
    _available = result?.status === 'ok' || result?.status === 'available';
  } catch (_e) {
    _available = false;
  }
  return _available;
}

function _request(method, endpoint, body, key, timeoutMs = 10_000) {
  return new Promise((resolve, reject) => {
    const url = new URL(`${NVIDIA_API_BASE}${endpoint}`);
    const reqBody = body ? JSON.stringify(body) : null;
    const options = {
      hostname: url.hostname,
      path:     url.pathname + url.search,
      method,
      headers: {
        Authorization: `Bearer ${key}`,
        Accept: 'audio/wav, application/json',
        ...(reqBody ? {
          'Content-Type':   'application/json',
          'Content-Length': Buffer.byteLength(reqBody),
        } : {}),
      },
      timeout: timeoutMs,
    };
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        const ct = res.headers['content-type'] || '';
        if (ct.includes('audio')) return resolve(buf);
        try { resolve(JSON.parse(buf.toString())); } catch (_) { resolve(buf); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Nvidia PersonaPlex API timeout')); });
    if (reqBody) req.write(reqBody);
    req.end();
  });
}

async function synthesize(text, persona = {}) {
  const key = getApiKey();
  if (!key) throw new Error('NVIDIA_API_KEY is not configured');

  const p = { ...DEFAULT_PERSONA, ...persona };
  const voiceInfo = GENDER_VOICE_MAP[p.gender] || GENDER_VOICE_MAP.neutral;
  const styleCode  = TONE_STYLE_MAP[p.tone]    || TONE_STYLE_MAP.professional;

  const body = {
    model:   PERSONAPLEX_MODEL,
    input:   String(text || '').trim(),
    voice:   voiceInfo.voice,
    response_format: 'wav',
    persona_config: {
      style:        styleCode,
      pitch_factor: Number(p.pitch),
      speed_factor: Number(p.speed),
      articulation: Number(p.articulation),
      friendliness: Number(p.friendliness),
    },
  };

  const audioBuf = await _request('POST', '/audio/speech', body, key);
  if (!Buffer.isBuffer(audioBuf) || audioBuf.length < 100) {
    throw new Error('Nvidia PersonaPlex returned invalid audio data');
  }
  return audioBuf;
}

// Synthesize and play through the system audio device
async function synthesizeAndPlay(text, persona = {}) {
  const audioBuf = await synthesize(text, persona);
  const tmpFile = path.join(os.tmpdir(), `pplex_${Date.now()}.wav`);
  fs.writeFileSync(tmpFile, audioBuf);

  await new Promise((resolve, reject) => {
    let player;
    const pf = os.platform();
    if (pf === 'linux') {
      player = spawn('aplay', ['-q', tmpFile], { stdio: 'ignore' });
    } else if (pf === 'darwin') {
      player = spawn('afplay', [tmpFile], { stdio: 'ignore' });
    } else if (pf === 'win32') {
      const ps = `(New-Object Media.SoundPlayer '${tmpFile}').PlaySync()`;
      player = spawn('powershell', ['-NoProfile', '-c', ps], { stdio: 'ignore' });
    } else {
      try { fs.unlinkSync(tmpFile); } catch (_e) { /* ignore */ }
      return reject(new Error('No audio player available on this platform'));
    }
    player.once('exit', () => {
      try { fs.unlinkSync(tmpFile); } catch (_e) { /* ignore */ }
      resolve();
    });
    player.once('error', (e) => {
      try { fs.unlinkSync(tmpFile); } catch (_e) { /* ignore */ }
      reject(e);
    });
  });
}

module.exports = {
  isAvailable,
  checkAvailability,
  synthesize,
  synthesizeAndPlay,
  DEFAULT_PERSONA,
  TONE_STYLE_MAP,
  GENDER_VOICE_MAP,
};
