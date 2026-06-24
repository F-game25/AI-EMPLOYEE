'use strict';

// Kokoro 82M TTS adapter — interface + graceful degradation when the model isn't
// installed (the teammate must fall back to text, never crash). Hermetic: no model,
// no python synth invoked (the empty-text + models-absent paths short-circuit).

const assert = require('assert');
const os = require('os');
const path = require('path');
const fs = require('fs');

// Point the model root at an empty temp dir so models are guaranteed absent.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kokoro-test-'));
process.env.VOICE_MODEL_ROOT = tmp;

const kokoro = require('../backend/services/voice/kokoro');

let passed = 0;
const ok = (n) => { console.log(`  ok  ${n}`); passed += 1; };

(async () => {
  // interface present
  for (const fn of ['getStatus', 'synthesize', 'saveArtifact', 'configure', 'modelsPresent']) {
    assert.strictEqual(typeof kokoro[fn], 'function', `missing ${fn}`);
  }
  ok('exposes the engine interface (getStatus/synthesize/saveArtifact/configure)');

  assert.strictEqual(kokoro.modelsPresent(), false);
  const status = await kokoro.getStatus();
  assert.strictEqual(status.ready, false);
  assert.ok(status.install && /kokoro-onnx/.test(status.install), 'install hint present');
  assert.strictEqual(status.engine, 'kokoro');
  ok('getStatus reports not-ready + an install hint when the model is absent');

  const empty = await kokoro.synthesize('   ');
  assert.strictEqual(empty.ok, false);
  ok('synthesize rejects empty text');

  const r = await kokoro.synthesize('hello there');
  assert.strictEqual(r.ok, false);
  assert.ok(/not installed/.test(r.reason), `reason: ${r.reason}`);
  ok('synthesize degrades gracefully (ok:false + reason) when the model is absent');

  const cfg = kokoro.configure({ voice: 'am_adam', speed: 1.2 });
  assert.strictEqual(cfg.voice, 'am_adam');
  assert.strictEqual(cfg.speed, 1.2);
  ok('configure merges UI-customizable options (voice/speed)');

  // tts_engine recognizes the kokoro provider in its status
  const tts = require('../backend/services/voice/tts_engine');
  const ttsStatus = tts.getStatus();
  assert.ok(ttsStatus.kokoro, 'tts_engine exposes a kokoro engine slot');
  assert.strictEqual(ttsStatus.kokoro.ready, false);
  ok('tts_engine registers kokoro as a selectable provider');

  console.log(`\nkokoro_voice: ${passed} passed, 0 failed`);
  fs.rmSync(tmp, { recursive: true, force: true });
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
