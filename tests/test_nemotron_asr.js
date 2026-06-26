'use strict';

// Nemotron-3.5-ASR streaming adapter — interface + graceful degradation when the
// model / onnxruntime-genai isn't installed (the STT path must fall back to
// whisper.cpp, never crash). Plus the pure engine-resolution logic that decides
// which "hear" engine handles a turn. Hermetic: no model, no python invoked
// (the file-absent + models-absent paths short-circuit before spawn).

const assert = require('assert');
const os = require('os');
const path = require('path');
const fs = require('fs');

// Point the model root at an empty temp dir so models are guaranteed absent.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nemotron-test-'));
process.env.VOICE_MODEL_ROOT = tmp;

const nemotron = require('../backend/services/voice/nemotron_asr');
const runtime = require('../backend/services/voice/voice_runtime_manager');

let passed = 0;
const ok = (n) => { console.log(`  ok  ${n}`); passed += 1; };

(async () => {
  // ── adapter interface ───────────────────────────────────────────────────────
  for (const fn of ['getStatus', 'transcribe', 'configure', 'modelsPresent']) {
    assert.strictEqual(typeof nemotron[fn], 'function', `missing ${fn}`);
  }
  ok('exposes the engine interface (getStatus/transcribe/configure/modelsPresent)');

  assert.strictEqual(nemotron.modelsPresent(), false);
  const status = await nemotron.getStatus();
  assert.strictEqual(status.ready, false);
  assert.strictEqual(status.engine, 'nemotron');
  assert.ok(status.install && /onnxruntime-genai/.test(status.install), 'install hint present');
  ok('getStatus reports not-ready + an install hint when the model is absent');

  const noFile = await nemotron.transcribe('/no/such/file.wav');
  assert.strictEqual(noFile.ok, false);
  assert.ok(/not found/.test(noFile.reason), `reason: ${noFile.reason}`);
  ok('transcribe rejects a missing audio file');

  // real temp file, but models absent → graceful (no python spawn)
  const wav = path.join(tmp, 'sample.wav');
  fs.writeFileSync(wav, Buffer.alloc(64));
  const r = await nemotron.transcribe(wav);
  assert.strictEqual(r.ok, false);
  assert.ok(/not installed/.test(r.reason), `reason: ${r.reason}`);
  ok('transcribe degrades gracefully (ok:false + reason) when the model is absent');

  const cfg = nemotron.configure({ language: 'nl', timeoutMs: 99999 });
  assert.strictEqual(cfg.language, 'nl');
  assert.strictEqual(cfg.timeoutMs, 99999);
  ok('configure merges UI-customizable options (language/timeout)');

  // ── engine resolution (pure logic) ──────────────────────────────────────────
  const resolve = runtime.resolveAsrEngine;
  assert.strictEqual(typeof resolve, 'function', 'runtime exposes resolveAsrEngine');
  delete process.env.VOICE_ASR_ENGINE;
  // auto prefers nemotron when present, else whisper, else none
  assert.strictEqual(resolve('auto', { whisperReady: true, nemotronReady: true }), 'nemotron');
  assert.strictEqual(resolve('auto', { whisperReady: true, nemotronReady: false }), 'whisper');
  assert.strictEqual(resolve('auto', { whisperReady: false, nemotronReady: true }), 'nemotron');
  assert.strictEqual(resolve('auto', { whisperReady: false, nemotronReady: false }), 'none');
  ok('resolveAsrEngine("auto") prefers nemotron, falls back to whisper, else none');

  // explicit preference with graceful fallback to the other ready engine
  assert.strictEqual(resolve('nemotron', { whisperReady: true, nemotronReady: false }), 'whisper');
  assert.strictEqual(resolve('whisper', { whisperReady: false, nemotronReady: true }), 'nemotron');
  assert.strictEqual(resolve('whisper', { whisperReady: true, nemotronReady: true }), 'whisper');
  ok('resolveAsrEngine honors an explicit engine but falls back when it is not ready');

  // ── runtime status surfaces both engines ─────────────────────────────────────
  const st = await runtime.getStatus();
  assert.ok(st.stt && st.stt.engines, 'stt.engines present');
  assert.ok(st.stt.engines.whisper && st.stt.engines.nemotron, 'both engines surfaced');
  assert.strictEqual(st.stt.engines.nemotron.state, 'not_installed');
  assert.ok(['whisper', 'nemotron', 'none'].includes(st.stt.active_engine), `active_engine: ${st.stt.active_engine}`);
  assert.ok(st.downloadable_assets.nemotron_asr, 'nemotron_asr is a downloadable asset');
  ok('voice_runtime_manager surfaces nemotron as a selectable + downloadable STT engine');

  console.log(`\nnemotron_asr: ${passed} passed, 0 failed`);
  fs.rmSync(tmp, { recursive: true, force: true });
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
