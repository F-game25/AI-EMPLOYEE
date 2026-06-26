'use strict';

/**
 * Kokoro 82M TTS engine adapter (kokoro-onnx via a Python synth — no torch).
 *
 * Same interface as the other voice engines (voice_lite/fish_speech) so tts_engine
 * can select it via engineProvider='kokoro': getStatus(), synthesize(), saveArtifact().
 *
 * GRACEFUL by design — if the python package or model files are absent, getStatus()
 * reports not-ready and synthesize() returns { ok:false, reason }, so the teammate
 * degrades to a text reply instead of crashing. Activate by installing the models
 * (see runtime/agents/voice/kokoro_synth.py) and setting engineProvider='kokoro'.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'));
const MODEL_DIR = path.join(process.env.VOICE_MODEL_ROOT || path.join(AI_HOME, 'models', 'voice'), 'kokoro');
const ARTIFACT_DIR = path.join(AI_HOME, 'state', 'voice');
const SYNTH = path.resolve(__dirname, '..', '..', '..', 'runtime', 'agents', 'voice', 'kokoro_synth.py');
const PYTHON = process.env.PYTHON_BIN || 'python3';

const DEFAULT_OPTIONS = { enabled: true, voice: 'af_sarah', speed: 1.0, language: 'en-us', timeoutMs: 30000 };
let options = { ...DEFAULT_OPTIONS };
let lastError = null;

function configure(next = {}) { options = { ...options, ...next }; return options; }

function modelsPresent() {
  try {
    return fs.existsSync(path.join(MODEL_DIR, 'kokoro-v1.0.onnx')) &&
           fs.existsSync(path.join(MODEL_DIR, 'voices-v1.0.bin'));
  } catch { return false; }
}

async function getStatus() {
  const present = modelsPresent();
  return {
    engine: 'kokoro',
    label: 'Kokoro 82M (kokoro-onnx, CPU)',
    ready: present,                 // python package is verified at synth time
    model_ready: present,
    model_dir: MODEL_DIR,
    voice: options.voice,
    last_error: lastError,
    install: present ? null : 'pip install kokoro-onnx soundfile; place kokoro-v1.0.onnx + voices-v1.0.bin in ' + MODEL_DIR,
  };
}

/** Synthesize `text` to a WAV Buffer. Returns { ok, audioBuf?, sampleRate?, reason? }. */
function synthesize(text, opts = {}) {
  const phrase = String(text || '').trim();
  if (!phrase) return Promise.resolve({ ok: false, reason: 'empty text' });
  if (!modelsPresent()) {
    lastError = 'kokoro model files not installed';
    return Promise.resolve({ ok: false, reason: lastError });
  }
  const o = { ...options, ...opts };
  return new Promise((resolve) => {
    const args = [SYNTH, '--text', phrase, '--voice', String(o.voice || 'af_sarah'),
      '--speed', String(o.speed || 1.0), '--lang', String(o.language || 'en-us'), '--out', '-'];
    const child = spawn(PYTHON, args, { timeout: o.timeoutMs || 30000 });
    const out = [];
    let err = '';
    child.stdout.on('data', (d) => out.push(d));
    child.stderr.on('data', (d) => { err += d.toString(); });
    child.on('error', (e) => { lastError = String(e.message || e); resolve({ ok: false, reason: lastError }); });
    child.on('close', (code) => {
      if (code === 0 && out.length) {
        let rate = 24000;
        try { const j = JSON.parse(err.trim().split('\n').pop() || '{}'); if (j.sample_rate) rate = j.sample_rate; } catch { /* noop */ }
        resolve({ ok: true, audioBuf: Buffer.concat(out), sampleRate: rate });
      } else {
        try { lastError = (JSON.parse(err.trim().split('\n').pop() || '{}').reason) || `exit ${code}`; }
        catch { lastError = `exit ${code}: ${err.slice(0, 160)}`; }
        resolve({ ok: false, reason: lastError });
      }
    });
  });
}

function saveArtifact(audioBuf) {
  try {
    fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
    const file = path.join(ARTIFACT_DIR, `kokoro-${Date.now()}.wav`);
    fs.writeFileSync(file, audioBuf);
    return { path: file };
  } catch (e) { lastError = String(e.message || e); return { path: null }; }
}

module.exports = { DEFAULT_OPTIONS, configure, getStatus, synthesize, saveArtifact, modelsPresent, MODEL_DIR };
