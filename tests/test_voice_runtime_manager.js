const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
process.env.AI_HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-employee-voice-test-'));
process.env.VOICE_CORE_BUNDLE_ROOT = path.join(process.env.AI_HOME, 'missing-voice-core-bundle');
process.env.VOICE_CORE_HOME = path.join(process.env.AI_HOME, 'missing-voice-core-install');
process.env.VOICE_LITE_PIPER_BIN = path.join(process.env.AI_HOME, 'missing-piper');
process.env.WHISPER_CPP_BIN = path.join(process.env.AI_HOME, 'missing-whisper');

const voiceRuntime = require('../backend/services/voice/voice_runtime_manager');

async function run() {
  const status = await voiceRuntime.getStatus();
  assert.strictEqual(status.tts.provider, 'voice_core_local');
  assert.ok(['runtime_missing', 'model_missing', 'bundle_missing', 'starting'].includes(status.tts.voice_core_local.state));
  assert.strictEqual(status.tts.voice_core_local.default_voice_ready, false);
  assert.strictEqual(status.tts.voice_core_local.requires_installation, false);
  assert.strictEqual(status.tts.voice_core_local.requires_network, false);
  assert.strictEqual(status.tts.voice_core_local.requires_gpu, false);
  assert.ok(status.tts.voice_core_local.supported_emotions.includes('warm_confident'));
  assert.strictEqual(status.tts.voice_lite.state, 'runtime_missing');
  assert.strictEqual(status.stt.state, 'runtime_missing');
  assert.strictEqual(status.vad.state, 'ready');
  assert.ok(status.vad.provider === 'simple-rms' || status.vad.provider === 'silero-vad');
  assert.ok(status.vad.silero_state === 'model_missing' || status.vad.silero_state === 'runtime_missing' || status.vad.silero_state === 'ready');
  assert.ok(status.tts.voice_lite.miso_one);
  assert.strictEqual(status.tts.voice_lite.miso_one.live_cpu_runtime, false);

  const doctor = await voiceRuntime.doctor();
  assert.ok(Array.isArray(doctor.checks));
  assert.ok(doctor.checks.some((check) => check.id === 'voice_core_bundle' && check.blocking));
  assert.ok(doctor.checks.some((check) => check.id === 'voice_lite_runtime' && check.warning));
  assert.ok(doctor.checks.some((check) => check.id === 'fish_gate'));

  const selfTest = await voiceRuntime.selfTest({ timeoutMs: 1000 });
  assert.strictEqual(selfTest.ok, false);
  assert.ok(selfTest.checks.some((check) => check.id === 'vad_silence_gate'));
  assert.ok(selfTest.checks.some((check) => check.id === 'voice_core_prewarm' && check.blocking));
  assert.strictEqual(selfTest.artifacts.length, 0);

  const planned = voiceRuntime.planSpeech('**System ready**. I found a warning.', { emotion: 'concerned', emotion_intensity: 0.9 });
  assert.strictEqual(planned.emotion, 'concerned');
  assert.ok(planned.emotion_intensity <= 0.7);
  assert.ok(!planned.text.includes('**'));

  const tracked = spawnSync('git', ['ls-files'], { cwd: repoRoot, encoding: 'utf8' });
  assert.strictEqual(tracked.status, 0, tracked.stderr);
  const forbidden = String(tracked.stdout || '')
    .split('\n')
    .filter((file) => /(^|\/)(models|runtimes)\/voice\//.test(file))
    .filter((file) => /\.(onnx|safetensors|bin|pt|pth)$/i.test(file));
  assert.deepStrictEqual(forbidden, [], `voice model/runtime weights must not be tracked: ${forbidden.join(', ')}`);
}

run()
  .then(() => {
    console.log('voice runtime manager tests passed');
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
