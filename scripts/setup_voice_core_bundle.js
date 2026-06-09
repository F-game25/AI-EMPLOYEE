#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..');
const BUNDLE_ROOT = path.resolve(process.env.VOICE_CORE_BUNDLE_ROOT || path.join(REPO_ROOT, 'resources', 'voice-core'));
const CACHE_ROOT = path.join(BUNDLE_ROOT, '.cache');
const PLATFORM = process.env.VOICE_CORE_PLATFORM || 'linux-x64';

const URLS = {
  piperRuntime: process.env.VOICE_CORE_PIPER_RUNTIME_URL || 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz',
  piperEnModel: process.env.VOICE_CORE_PIPER_EN_MODEL_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx',
  piperEnConfig: process.env.VOICE_CORE_PIPER_EN_CONFIG_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json',
  piperEnMaleModel: process.env.VOICE_CORE_PIPER_EN_MALE_MODEL_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx',
  piperEnMaleConfig: process.env.VOICE_CORE_PIPER_EN_MALE_CONFIG_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json',
  piperNlModel: process.env.VOICE_CORE_PIPER_NL_MODEL_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/nl/nl_NL/mls/medium/nl_NL-mls-medium.onnx',
  piperNlConfig: process.env.VOICE_CORE_PIPER_NL_CONFIG_URL || 'https://huggingface.co/rhasspy/piper-voices/resolve/main/nl/nl_NL/mls/medium/nl_NL-mls-medium.onnx.json',
  whisperModel: process.env.VOICE_CORE_WHISPER_MODEL_URL || 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin',
  whisperSource: process.env.VOICE_CORE_WHISPER_SOURCE_URL || 'https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v1.5.4.tar.gz',
  sileroVad: process.env.VOICE_CORE_SILERO_VAD_URL || 'https://huggingface.co/deepghs/silero-vad-onnx/resolve/main/silero_vad.onnx',
};

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function exists(filePath) {
  try { return fs.existsSync(filePath); } catch (_err) { return false; }
}

function run(cmd, args, options = {}) {
  const result = spawnSync(cmd, args, { stdio: 'inherit', ...options });
  if (result.status !== 0) throw new Error(`${cmd} ${args.join(' ')} failed with exit ${result.status}`);
}

function download(url, dest, redirects = 0) {
  ensureDir(path.dirname(dest));
  if (exists(dest) && fs.statSync(dest).size > 0) {
    console.log(`[voice-core] cached ${path.relative(REPO_ROOT, dest)}`);
    return Promise.resolve(dest);
  }
  console.log(`[voice-core] download ${url}`);
  return new Promise((resolve, reject) => {
    const request = https.get(url, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        if (!response.headers.location || redirects > 8) return reject(new Error(`redirect failed for ${url}`));
        return download(new URL(response.headers.location, url).toString(), dest, redirects + 1).then(resolve, reject);
      }
      if (response.statusCode !== 200) {
        response.resume();
        return reject(new Error(`${url} returned HTTP ${response.statusCode}`));
      }
      const tmp = `${dest}.tmp-${process.pid}`;
      const out = fs.createWriteStream(tmp);
      const total = Number(response.headers['content-length'] || 0);
      let received = 0;
      response.on('data', (chunk) => {
        received += chunk.length;
        if (total && received % (8 * 1024 * 1024) < chunk.length) {
          process.stdout.write(`\r[voice-core] ${(received / total * 100).toFixed(1)}% ${path.basename(dest)}   `);
        }
      });
      response.pipe(out);
      out.on('finish', () => {
        out.close(() => {
          if (total) process.stdout.write('\n');
          fs.renameSync(tmp, dest);
          resolve(dest);
        });
      });
      out.on('error', (err) => {
        try { fs.unlinkSync(tmp); } catch (_err) { /* ignore */ }
        reject(err);
      });
    });
    request.on('error', reject);
  });
}

function sha256(filePath) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('hex');
}

function findFile(root, predicate) {
  if (!exists(root)) return null;
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else if (predicate(full, entry)) return full;
    }
  }
  return null;
}

function copyDir(source, target) {
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true, force: true });
}

function rel(filePath) {
  return path.relative(BUNDLE_ROOT, filePath).replace(/\\/g, '/');
}

async function setupPiperRuntime() {
  const archive = await download(URLS.piperRuntime, path.join(CACHE_ROOT, 'piper_linux_x86_64.tar.gz'));
  const temp = path.join(CACHE_ROOT, 'piper-extract');
  fs.rmSync(temp, { recursive: true, force: true });
  ensureDir(temp);
  run('tar', ['-xzf', archive, '-C', temp]);
  const binary = findFile(temp, (full) => path.basename(full) === 'piper');
  if (!binary) throw new Error('Piper archive did not contain a piper executable.');
  const targetDir = path.join(BUNDLE_ROOT, 'runtimes', PLATFORM, 'piper');
  copyDir(path.dirname(binary), targetDir);
  const target = path.join(targetDir, 'piper');
  fs.chmodSync(target, 0o755);
  return target;
}

async function setupPiperVoices() {
  const enDir = path.join(BUNDLE_ROOT, 'models', 'tts', 'piper-en');
  const nlDir = path.join(BUNDLE_ROOT, 'models', 'tts', 'piper-nl');
  const enModel = await download(URLS.piperEnModel, path.join(enDir, 'en_US-lessac-high.onnx'));
  const enConfig = await download(URLS.piperEnConfig, path.join(enDir, 'en_US-lessac-high.onnx.json'));
  const enMaleModel = await download(URLS.piperEnMaleModel, path.join(enDir, 'en_US-ryan-high.onnx'));
  const enMaleConfig = await download(URLS.piperEnMaleConfig, path.join(enDir, 'en_US-ryan-high.onnx.json'));
  const nlModel = await download(URLS.piperNlModel, path.join(nlDir, 'nl_NL-mls-medium.onnx'));
  const nlConfig = await download(URLS.piperNlConfig, path.join(nlDir, 'nl_NL-mls-medium.onnx.json'));
  return { enModel, enConfig, enMaleModel, enMaleConfig, nlModel, nlConfig };
}

async function setupWhisper() {
  const model = await download(URLS.whisperModel, path.join(BUNDLE_ROOT, 'models', 'stt', 'whisper', 'ggml-base.en.bin'));
  const runtimeDir = path.join(BUNDLE_ROOT, 'runtimes', PLATFORM, 'whisper');
  const existing = findFile(runtimeDir, (full) => path.basename(full) === 'whisper-cli' || path.basename(full) === 'main');
  if (existing) return { model, binary: existing };

  const archive = await download(URLS.whisperSource, path.join(CACHE_ROOT, 'whisper.cpp-v1.5.4.tar.gz'));
  fs.rmSync(runtimeDir, { recursive: true, force: true });
  ensureDir(runtimeDir);
  const temp = path.join(CACHE_ROOT, 'whisper-source-extract');
  fs.rmSync(temp, { recursive: true, force: true });
  ensureDir(temp);
  run('tar', ['-xzf', archive, '-C', temp]);
  const sourceDir = fs.readdirSync(temp).map((name) => path.join(temp, name)).find((item) => fs.statSync(item).isDirectory());
  if (!sourceDir) throw new Error('Whisper source archive did not contain a source directory.');
  const targetSource = path.join(runtimeDir, 'whisper.cpp');
  copyDir(sourceDir, targetSource);
  run('make', ['-j', String(Math.max(1, Math.min(4, os.cpus().length || 2)))], { cwd: targetSource });
  const binary = findFile(targetSource, (full) => {
    const name = path.basename(full);
    return (name === 'whisper-cli' || name === 'main') && fs.statSync(full).mode & 0o111;
  });
  if (!binary) throw new Error('Whisper build completed but no whisper-cli/main executable was found.');
  fs.chmodSync(binary, 0o755);
  return { model, binary };
}

async function setupVad() {
  return download(URLS.sileroVad, path.join(BUNDLE_ROOT, 'models', 'vad', 'silero-vad.onnx'));
}

function component(id, role, engine, language, filePath, required, executable, license, source, url) {
  const entry = {
    id,
    role,
    engine,
    language,
    path: rel(filePath),
    required,
    license,
    source,
    url,
  };
  if (executable) entry.executable = true;
  if (exists(filePath)) {
    entry.size = fs.statSync(filePath).size;
    entry.sha256 = sha256(filePath);
  }
  return entry;
}

function writeManifest(paths) {
  const manifest = {
    schema: 1,
    bundle_id: `voice-core-local-${new Date().toISOString().slice(0, 10)}`,
    platform: PLATFORM,
    install_mode: 'bundled',
    requires_network: false,
    requires_gpu: false,
    generated_at: new Date().toISOString(),
    default_voice: {
      provider: 'voice_core_local',
      language: 'en',
      voice: 'female',
      gender: 'female',
      model_voice: 'en_US-lessac-high',
      alternate_voice: 'male',
      emotion: 'warm_confident',
    },
    components: [
      component('piper_cli', 'runtime', 'piper_onnx_cpu', 'multi', paths.piper, true, true, 'MIT', 'https://github.com/rhasspy/piper', URLS.piperRuntime),
      component('piper_en_model', 'model', 'piper_onnx_cpu', 'en', paths.enModel, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperEnModel),
      component('piper_en_config', 'config', 'piper_onnx_cpu', 'en', paths.enConfig, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperEnConfig),
      component('piper_en_male_model', 'model', 'piper_onnx_cpu', 'en', paths.enMaleModel, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperEnMaleModel),
      component('piper_en_male_config', 'config', 'piper_onnx_cpu', 'en', paths.enMaleConfig, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperEnMaleConfig),
      component('piper_nl_model', 'model', 'piper_onnx_cpu', 'nl', paths.nlModel, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperNlModel),
      component('piper_nl_config', 'config', 'piper_onnx_cpu', 'nl', paths.nlConfig, true, false, 'MIT', 'https://huggingface.co/rhasspy/piper-voices', URLS.piperNlConfig),
      component('kokoro_cli', 'runtime', 'kokoro_onnx_cli', 'en', path.join(BUNDLE_ROOT, 'runtimes', PLATFORM, 'kokoro', 'kokoro-tts'), false, true, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M', null),
      component('kokoro_en_model', 'model', 'kokoro_onnx', 'en', path.join(BUNDLE_ROOT, 'models', 'tts', 'kokoro-en', 'kokoro-v1.0.onnx'), false, false, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M', null),
      component('kokoro_en_voices', 'voice_pack', 'kokoro_onnx', 'en', path.join(BUNDLE_ROOT, 'models', 'tts', 'kokoro-en', 'voices-v1.0.bin'), false, false, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md', null),
      component('whisper_cli', 'runtime', 'whisper.cpp', 'en', paths.whisperBinary, true, true, 'MIT', 'https://github.com/ggml-org/whisper.cpp', URLS.whisperSource),
      component('whisper_base_en', 'model', 'whisper.cpp', 'en', paths.whisperModel, true, false, 'MIT', 'https://github.com/ggml-org/whisper.cpp', URLS.whisperModel),
      component('silero_vad', 'model', 'silero_vad_onnx', 'multi', paths.vad, true, false, 'MIT', 'https://github.com/snakers4/silero-vad', URLS.sileroVad),
    ],
    samples: [
      { id: 'en_default', language: 'en', emotion: 'warm_confident', path: 'samples/en-default.wav' },
      { id: 'nl_default', language: 'nl', emotion: 'calm', path: 'samples/nl-default.wav' },
    ],
  };
  fs.writeFileSync(path.join(BUNDLE_ROOT, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
}

async function main() {
  ensureDir(BUNDLE_ROOT);
  ensureDir(CACHE_ROOT);
  const piper = await setupPiperRuntime();
  const voices = await setupPiperVoices();
  const whisper = await setupWhisper();
  const vad = await setupVad();
  writeManifest({
    piper,
    ...voices,
    whisperBinary: whisper.binary,
    whisperModel: whisper.model,
    vad,
  });
  console.log('[voice-core] bundle ready at', BUNDLE_ROOT);
}

main().catch((err) => {
  console.error('[voice-core] setup failed:', err.message || err);
  process.exit(1);
});
