'use strict';

/**
 * Nemotron-3.5-ASR streaming adapter (onnxruntime-genai, CPU int4 — no torch).
 *
 * The "hear" engine. Same adapter shape as the TTS engines (kokoro/voice_lite):
 * getStatus(), transcribe(), configure(), modelsPresent() — so voice_runtime_manager
 * can select it as an STT engine alongside whisper.cpp.
 *
 * GRACEFUL by design — if the python package or model files are absent, getStatus()
 * reports not-ready and transcribe() returns { ok:false, reason }, so the STT path
 * falls back to whisper.cpp instead of crashing. Activate by installing the deps and
 * downloading the model (see runtime/agents/voice/nemotron_asr.py + the runtime
 * manager's `nemotron_asr` download component).
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'));
const MODEL_DIR = path.join(process.env.VOICE_MODEL_ROOT || path.join(AI_HOME, 'models', 'voice'), 'nemotron');
const RUNNER = path.resolve(__dirname, '..', '..', '..', 'runtime', 'agents', 'voice', 'nemotron_asr.py');
const PYTHON = process.env.PYTHON_BIN || 'python3';

// Key files that must all be present for the ONNX int4 RNN-T model to load.
const REQUIRED_FILES = ['genai_config.json', 'encoder.onnx', 'decoder.onnx', 'joint.onnx', 'tokenizer.json'];

const DEFAULT_OPTIONS = { enabled: true, language: 'auto', timeoutMs: 120000 };
let options = { ...DEFAULT_OPTIONS };
let lastError = null;

function configure(next = {}) { options = { ...options, ...next }; return options; }

function modelsPresent() {
  try { return REQUIRED_FILES.every((f) => fs.existsSync(path.join(MODEL_DIR, f))); }
  catch { return false; }
}

async function getStatus() {
  const present = modelsPresent();
  return {
    engine: 'nemotron',
    label: 'Nemotron-3.5-ASR streaming 0.6B (onnxruntime-genai int4, CPU)',
    ready: present,                 // python package is verified at transcribe time
    model_ready: present,
    model_dir: MODEL_DIR,
    language: options.language,
    last_error: lastError,
    install: present ? null : `pip install onnxruntime-genai soundfile; download the ONNX int4 model into ${MODEL_DIR}`,
  };
}

/**
 * Transcribe a PCM16 WAV file to text. Returns
 * { ok, text?, language?, elapsed_ms?, engine?, reason? }.
 * `filePath` is created server-side (never user-controlled) and passed as an array
 * arg with no shell, so there is no argument-injection surface.
 */
function transcribe(filePath, opts = {}) {
  const file = String(filePath || '');
  if (!file || !fs.existsSync(file)) return Promise.resolve({ ok: false, reason: 'audio file not found' });
  if (!modelsPresent()) {
    lastError = 'nemotron model files not installed';
    return Promise.resolve({ ok: false, reason: lastError });
  }
  const o = { ...options, ...opts };
  const started = Date.now();
  return new Promise((resolve) => {
    const args = [RUNNER, '--audio', file, '--model-dir', MODEL_DIR, '--language', String(o.language || 'auto')];
    if (o.langId != null && Number.isFinite(Number(o.langId))) args.push('--lang-id', String(Number(o.langId)));
    const child = spawn(PYTHON, args, { timeout: o.timeoutMs || 120000 });
    let out = '';
    let err = '';
    child.stdout.on('data', (d) => { out += d.toString(); });
    child.stderr.on('data', (d) => { err += d.toString(); });
    child.on('error', (e) => { lastError = String(e.message || e); resolve({ ok: false, reason: lastError }); });
    child.on('close', (code) => {
      if (code === 0 && out.trim()) {
        try {
          const j = JSON.parse(out.trim().split('\n').pop() || '{}');
          return resolve({
            ok: true,
            text: String(j.text || '').trim(),
            language: j.lang_id ?? null,
            sample_rate: j.sample_rate || 16000,
            elapsed_ms: Date.now() - started,
            engine: 'nemotron',
          });
        } catch (e) {
          lastError = `bad runner output: ${String(e.message || e)}`;
          return resolve({ ok: false, reason: lastError });
        }
      }
      try { lastError = JSON.parse(err.trim().split('\n').pop() || '{}').reason || `exit ${code}`; }
      catch { lastError = `exit ${code}: ${err.slice(0, 200)}`; }
      resolve({ ok: false, reason: lastError });
    });
  });
}

module.exports = { DEFAULT_OPTIONS, configure, getStatus, transcribe, modelsPresent, MODEL_DIR, REQUIRED_FILES };
