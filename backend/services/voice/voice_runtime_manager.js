'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const https = require('https');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');
const fishSpeech = require('./fish_speech');
const voiceLite = require('./voice_lite');
const voiceCore = require('./voice_core_local');
const nemotronAsr = require('./nemotron_asr');

const REPO_ROOT = path.resolve(__dirname, '../../..');
const AI_HOME = path.resolve(
  process.env.AI_HOME ||
  process.env.AI_EMPLOYEE_HOME ||
  path.join(os.homedir(), '.ai-employee')
);

const VOICE_MODEL_ROOT = path.join(AI_HOME, 'models', 'voice');
const VOICE_STATE_ROOT = path.join(AI_HOME, 'state', 'voice');
const LOG_LIMIT = 300;
const FISH_MIN_VRAM_MIB = 24 * 1024;

const ASSETS = {
  whisper_model: {
    component: 'whisper_model',
    label: 'Whisper base.en STT model',
    url: 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin',
    sha256: 'a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002',
    size: 148 * 1024 * 1024,
    path: path.join(VOICE_MODEL_ROOT, 'whisper', 'ggml-base.en.bin'),
    license: 'MIT',
    source: 'https://github.com/ggml-org/whisper.cpp',
  },
  vad_model: {
    component: 'vad_model',
    label: 'Silero VAD ONNX model',
    url: 'https://huggingface.co/deepghs/silero-vad-onnx/resolve/main/silero_vad.onnx',
    sha256: '2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f',
    size: 2.33 * 1024 * 1024,
    path: path.join(VOICE_MODEL_ROOT, 'vad', 'silero-vad.onnx'),
    license: 'MIT',
    source: 'https://github.com/snakers4/silero-vad',
  },
};

const FISH_MODEL = {
  component: 'fish_speech',
  label: 'Fish Speech S2-Pro model',
  repo: 'fishaudio/s2-pro',
  revision: 'main',
  path: path.join(VOICE_MODEL_ROOT, 'fish-speech', 's2-pro'),
  license: 'Fish Audio Research License',
  source: 'https://huggingface.co/fishaudio/s2-pro',
};

// Nemotron-3.5-ASR streaming 0.6B, ONNX int4 build (CPU-only, no torch). Multi-file
// RNN-T model driven by onnxruntime-genai. Downloaded once via the HF repo file list.
const NEMOTRON_MODEL = {
  component: 'nemotron_asr',
  label: 'Nemotron-3.5-ASR streaming 0.6B (ONNX int4)',
  repo: 'onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4',
  revision: 'main',
  path: path.join(VOICE_MODEL_ROOT, 'nemotron'),
  license: 'MIT',
  source: 'https://huggingface.co/onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4',
  required_files: nemotronAsr.REQUIRED_FILES,
};

const WHISPER_BINARY_CANDIDATES = [
  process.env.WHISPER_CPP_BIN,
  path.join(AI_HOME, 'runtimes', 'voice', 'whisper.cpp', 'build', 'bin', 'whisper-cli'),
  path.join(AI_HOME, 'runtimes', 'voice', 'whisper.cpp', 'main'),
  path.join(REPO_ROOT, 'runtime', 'vendor', 'whisper.cpp', 'build', 'bin', 'whisper-cli'),
  path.join(REPO_ROOT, 'runtime', 'vendor', 'whisper.cpp', 'main'),
  '/usr/local/bin/whisper-cli',
  '/usr/bin/whisper-cli',
].filter(Boolean);

let fishProcess = null;
let fishStarting = false;
let downloadState = null;
let activeDownload = null;
const logLines = [];

function log(level, message) {
  const entry = {
    ts: new Date().toISOString(),
    level,
    message: String(message || ''),
  };
  logLines.push(entry);
  if (logLines.length > LOG_LIMIT) logLines.splice(0, logLines.length - LOG_LIMIT);
  return entry;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function exists(filePath) {
  try { return fs.existsSync(filePath); } catch (_err) { return false; }
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${value} B`;
}

function diskFreeBytes(dir) {
  try {
    ensureDir(dir);
    const result = spawnSync('df', ['-Pk', dir], { encoding: 'utf8' });
    if (result.status !== 0) return null;
    const lines = String(result.stdout || '').trim().split('\n');
    const parts = String(lines[1] || '').trim().split(/\s+/);
    const availableKb = Number(parts[3] || 0);
    return availableKb > 0 ? availableKb * 1024 : null;
  } catch (_err) {
    return null;
  }
}

function assertFreeSpace(dir, requiredBytes, label) {
  const free = diskFreeBytes(dir);
  if (free != null && free < requiredBytes) {
    throw new Error(`${label} needs ${formatBytes(requiredBytes)} free under ${dir}; only ${formatBytes(free)} is available.`);
  }
  return { free_bytes: free, required_bytes: requiredBytes };
}

function createDownloadToken(component) {
  const token = {
    component,
    cancelled: false,
    requests: new Set(),
    tempFiles: new Set(),
  };
  activeDownload = token;
  return token;
}

function assertNotCancelled(token) {
  if (token?.cancelled) throw new Error(`${token.component} download cancelled.`);
}

function cancelDownload(component = null) {
  if (voiceLite.cancelDownload) {
    const liteResult = voiceLite.cancelDownload(component);
    if (liteResult.cancelled) return liteResult;
  }
  if (!activeDownload) return { ok: true, cancelled: false };
  if (component && activeDownload.component !== component) {
    return { ok: true, cancelled: false, active_component: activeDownload.component };
  }
  activeDownload.cancelled = true;
  for (const req of activeDownload.requests) {
    try { req.destroy(new Error('download cancelled')); } catch (_err) { /* ignore */ }
  }
  for (const tmp of activeDownload.tempFiles) {
    try { fs.unlinkSync(tmp); } catch (_err) { /* ignore */ }
  }
  downloadState = null;
  return { ok: true, cancelled: true, component: activeDownload.component };
}

function isExecutable(filePath) {
  try {
    return fs.statSync(filePath).isFile() && fs.accessSync(filePath, fs.constants.X_OK) === undefined;
  } catch (_err) {
    return false;
  }
}

function commandPath(command) {
  try {
    const result = spawnSync('which', [command], { encoding: 'utf8' });
    if (result.status === 0) return String(result.stdout || '').trim() || null;
  } catch (_err) {
    // ignore
  }
  return null;
}

function firstExecutable(candidates) {
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (candidate.includes(path.sep) && isExecutable(candidate)) return candidate;
  }
  return commandPath('whisper-cli') || commandPath('main');
}

function readMemInfo() {
  try {
    const raw = fs.readFileSync('/proc/meminfo', 'utf8');
    const totalKb = Number(raw.match(/^MemTotal:\s+(\d+)/m)?.[1] || 0);
    const availableKb = Number(raw.match(/^MemAvailable:\s+(\d+)/m)?.[1] || 0);
    return {
      total_gib: Math.round((totalKb / 1024 / 1024) * 10) / 10,
      available_gib: Math.round((availableKb / 1024 / 1024) * 10) / 10,
    };
  } catch (_err) {
    const total = os.totalmem();
    const free = os.freemem();
    return {
      total_gib: Math.round((total / 1024 / 1024 / 1024) * 10) / 10,
      available_gib: Math.round((free / 1024 / 1024 / 1024) * 10) / 10,
    };
  }
}

function detectGpuFromLspci() {
  try {
    const result = spawnSync('lspci', [], { encoding: 'utf8' });
    const lines = String(result.stdout || '').split('\n');
    const gpu = lines.find((line) => /vga|3d|display/i.test(line) && /nvidia|amd|radeon|intel/i.test(line));
    if (!gpu) return null;
    return {
      name: gpu.replace(/^[0-9a-f:.]+\s+/i, '').trim(),
      vendor: /nvidia/i.test(gpu) ? 'nvidia' : /amd|radeon/i.test(gpu) ? 'amd' : /intel/i.test(gpu) ? 'intel' : 'unknown',
    };
  } catch (_err) {
    return null;
  }
}

function detectNvidia() {
  try {
    const result = spawnSync('nvidia-smi', ['--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], {
      encoding: 'utf8',
      timeout: 2500,
    });
    if (result.status !== 0) {
      return {
        available: false,
        driver_status: 'unavailable',
        error: String(result.stderr || result.stdout || '').trim() || 'nvidia-smi failed',
      };
    }
    const first = String(result.stdout || '').trim().split('\n')[0] || '';
    const parts = first.split(',').map((part) => part.trim());
    const vram = Number(parts[1] || 0);
    return {
      available: true,
      driver_status: 'ready',
      name: parts[0] || 'NVIDIA GPU',
      vram_mib: Number.isFinite(vram) ? vram : null,
    };
  } catch (err) {
    return {
      available: false,
      driver_status: 'error',
      error: String(err.message || err),
    };
  }
}

function getHardware() {
  const mem = readMemInfo();
  const lspciGpu = detectGpuFromLspci();
  const nvidia = detectNvidia();
  const cpu = os.cpus()?.[0]?.model || 'unknown CPU';
  const gpuName = nvidia.available ? nvidia.name : lspciGpu?.name || null;
  return {
    cpu,
    cpu_threads: os.cpus()?.length || null,
    ram_gib: mem.total_gib,
    ram_available_gib: mem.available_gib,
    gpu: gpuName ? {
      name: gpuName,
      vendor: nvidia.available ? 'nvidia' : lspciGpu?.vendor || 'unknown',
      driver_status: nvidia.driver_status,
      vram_mib: nvidia.vram_mib || null,
      error: nvidia.error || null,
    } : {
      name: null,
      vendor: 'none',
      driver_status: 'missing',
      vram_mib: null,
      error: null,
    },
  };
}

function fishSourcePath() {
  const explicit = process.env.FISH_SPEECH_HOME;
  const candidates = [
    explicit,
    path.join(REPO_ROOT, 'runtime', 'vendor', 'fish-speech'),
    path.join(AI_HOME, 'runtimes', 'voice', 'fish-speech'),
  ].filter(Boolean);
  return candidates.find((candidate) => exists(path.join(candidate, 'tools', 'api_server.py'))) || candidates[0];
}

function fishLicenseAckPath() {
  return path.join(VOICE_STATE_ROOT, 'fish_license_ack.json');
}

function hasFishLicenseAck() {
  try {
    const data = JSON.parse(fs.readFileSync(fishLicenseAckPath(), 'utf8'));
    return Boolean(data.personal_local_use === true);
  } catch (_err) {
    return false;
  }
}

function writeFishLicenseAck(actor = 'local-user') {
  ensureDir(VOICE_STATE_ROOT);
  const data = {
    personal_local_use: true,
    actor,
    accepted_at: new Date().toISOString(),
    license: FISH_MODEL.license,
    source: FISH_MODEL.source,
  };
  fs.writeFileSync(fishLicenseAckPath(), JSON.stringify(data, null, 2) + '\n', 'utf8');
  return data;
}

function hasFishModel() {
  return exists(path.join(FISH_MODEL.path, 'codec.pth')) &&
    (exists(path.join(FISH_MODEL.path, 'model.safetensors.index.json')) ||
     exists(path.join(FISH_MODEL.path, 'model-00001-of-00002.safetensors')) ||
     exists(path.join(FISH_MODEL.path, 'model.pth')));
}

function fishHardwareState(hardware) {
  const gpu = hardware.gpu || {};
  if (gpu.vendor === 'nvidia' && gpu.driver_status !== 'ready') {
    return { blocked: true, reason: `NVIDIA GPU detected, but driver is not ready: ${gpu.error || gpu.driver_status}` };
  }
  if (!gpu.vram_mib || gpu.vram_mib < FISH_MIN_VRAM_MIB) {
    return { blocked: true, reason: `Fish S2-Pro is not recommended below ${FISH_MIN_VRAM_MIB} MiB VRAM.` };
  }
  return { blocked: false, reason: '' };
}

function whisperModelExists() {
  return exists(ASSETS.whisper_model.path);
}

function vadModelExists() {
  return exists(ASSETS.vad_model.path);
}

function hasOnnxRuntime() {
  try {
    require.resolve('onnxruntime-node');
    return true;
  } catch (_err) {
    return false;
  }
}

function getWhisperRuntime() {
  const binary = firstExecutable(WHISPER_BINARY_CANDIDATES);
  return {
    binary,
    source: binary ? (binary.startsWith(REPO_ROOT) ? 'bundled' : binary.startsWith(AI_HOME) ? 'app_home' : 'system') : null,
  };
}

// Pick the active STT engine from a preference ('auto'|'nemotron'|'whisper') and what
// is actually installed. 'auto' prefers Nemotron (multilingual streaming) when present,
// otherwise whisper.cpp. Never hardcoded — preference comes from config/env/options.
function resolveAsrEngine(pref, { whisperReady, nemotronReady }) {
  const want = String(pref || process.env.VOICE_ASR_ENGINE || 'auto').toLowerCase();
  if (want === 'nemotron') return nemotronReady ? 'nemotron' : (whisperReady ? 'whisper' : 'none');
  if (want === 'whisper') return whisperReady ? 'whisper' : (nemotronReady ? 'nemotron' : 'none');
  if (nemotronReady) return 'nemotron';
  if (whisperReady) return 'whisper';
  return 'none';
}

function voiceCoreCheck(status, id) {
  return (status?.checks || []).find((check) => check.id === id) || null;
}

async function getStatus() {
  const hardware = getHardware();
  const voiceCoreStatus = await voiceCore.getStatus();
  const voiceLiteStatus = await voiceLite.getStatus();
  const whisper = getWhisperRuntime();
  const coreWhisperRuntime = voiceCoreCheck(voiceCoreStatus, 'whisper_cli');
  const coreWhisperModel = voiceCoreCheck(voiceCoreStatus, 'whisper_base_en');
  const coreVadModel = voiceCoreCheck(voiceCoreStatus, 'silero_vad');
  const whisperRuntime = whisper.binary ? whisper : {
    binary: coreWhisperRuntime?.passed ? coreWhisperRuntime.path : null,
    source: coreWhisperRuntime?.passed ? 'voice_core_local' : null,
  };
  const whisperModel = whisperModelExists() || Boolean(coreWhisperModel?.passed);
  const whisperModelPath = whisperModelExists() ? ASSETS.whisper_model.path : (coreWhisperModel?.passed ? coreWhisperModel.path : ASSETS.whisper_model.path);
  const vadModel = vadModelExists() || Boolean(coreVadModel?.passed);
  const vadModelPath = vadModelExists() ? ASSETS.vad_model.path : (coreVadModel?.passed ? coreVadModel.path : ASSETS.vad_model.path);
  const fishSource = fishSourcePath();
  const fishSourceReady = exists(path.join(fishSource, 'tools', 'api_server.py'));
  const fishModel = hasFishModel();
  const fishAck = hasFishLicenseAck();
  const fishHw = fishHardwareState(hardware);

  await fishSpeech.checkAvailability().catch(() => false);
  const fishProvider = fishSpeech.getStatus();
  const fishLive = Boolean(fishProvider.available);

  let ttsState = 'runtime_missing';
  if (fishLive) ttsState = 'ready';
  else if (fishStarting || fishProcess) ttsState = 'starting';
  else if (fishHw.blocked) ttsState = 'hardware_blocked';
  else if (!fishSourceReady) ttsState = 'runtime_missing';
  else if (!fishAck) ttsState = 'license_required';
  else if (!fishModel) ttsState = 'model_missing';
  else ttsState = 'error';

  const whisperReady = Boolean(whisperRuntime.binary && whisperModel);
  const nemotronReady = nemotronAsr.modelsPresent();
  const whisperEngineState = whisperReady ? 'ready' : (whisperRuntime.binary ? 'model_missing' : 'runtime_missing');
  let sttState = 'runtime_missing';
  if (whisperReady || nemotronReady) sttState = 'ready';
  else if (whisperRuntime.binary && !whisperModel) sttState = 'model_missing';
  const activeAsrEngine = resolveAsrEngine(null, { whisperReady, nemotronReady });

  const vadRuntimeReady = hasOnnxRuntime();
  const sileroState = vadModel ? (vadRuntimeReady ? 'ready' : 'runtime_missing') : 'model_missing';
  const vadProvider = vadRuntimeReady && vadModel ? 'silero-vad' : 'simple-rms';
  const vadState = 'ready';
  const ttsProviderState = voiceCoreStatus.state;
  const recommendation = buildRecommendation({
    voiceCoreState: voiceCoreStatus.state,
    voiceCoreStatus,
    voiceLiteState: voiceLiteStatus.state,
    voiceLiteStatus,
    fishState: ttsState,
    sttState,
    vadState,
    fishHw,
    whisper,
  });

  return {
    ok: true,
    generated_at: new Date().toISOString(),
    ai_home: AI_HOME,
    model_root: VOICE_MODEL_ROOT,
    downloading: downloadState,
    downloadable_assets: {
      voice_core_bundle: {
        component: 'voice_core_bundle',
        label: 'Bundled default human voice core',
        source_root: voiceCore.SOURCE_ROOT,
        install_root: voiceCore.INSTALL_ROOT,
        install_mode: 'bundled',
        requires_network: false,
        requires_gpu: false,
      },
      voice_lite_runtime: voiceLite.PIPER_RUNTIME || null,
      whisper_model: ASSETS.whisper_model,
      vad_model: ASSETS.vad_model,
      fish_speech: FISH_MODEL,
      nemotron_asr: NEMOTRON_MODEL,
    },
    hardware,
    recommendation,
    tts: {
      provider: 'voice_core_local',
      state: ttsProviderState,
      default_voice_ready: Boolean(voiceCoreStatus.default_voice_ready),
      active_voice: voiceCoreStatus.active_voice,
      supported_languages: voiceCoreStatus.supported_languages,
      supported_emotions: voiceCoreStatus.supported_emotions,
      requires_installation: false,
      requires_network: false,
      requires_gpu: false,
      fallback_reason: voiceCoreStatus.fallback_reason || null,
      ttfa_ms: voiceCoreStatus.ttfa_ms,
      rtf: voiceCoreStatus.rtf,
      voice_core_local: voiceCoreStatus,
      voice_lite: voiceLiteStatus,
      fish_speech: {
        state: ttsState,
        live: fishLive,
        source_path: fishSource,
        source_ready: fishSourceReady,
        model_path: FISH_MODEL.path,
        model_ready: fishModel,
        license_acknowledged: fishAck,
        hardware_blocked: fishHw.blocked,
        hardware_reason: fishHw.reason,
        process_running: Boolean(fishProcess),
        status: fishProvider,
      },
      fallback: {
        provider: 'browser_or_os_tts',
        active_when_fish_unavailable: true,
      },
    },
    stt: {
      provider: activeAsrEngine === 'nemotron' ? 'nemotron_asr' : 'whisper.cpp',
      state: sttState,
      active_engine: activeAsrEngine,
      runtime: whisperRuntime,
      model_path: whisperModelPath,
      model_ready: whisperModel,
      recommended_model: 'base.en',
      bundled: Boolean(coreWhisperRuntime?.passed && coreWhisperModel?.passed),
      engines: {
        whisper: {
          state: whisperEngineState,
          model_ready: whisperModel,
          runtime_ready: Boolean(whisperRuntime.binary),
          model_path: whisperModelPath,
          local: true,
        },
        nemotron: {
          state: nemotronReady ? 'ready' : 'not_installed',
          model_ready: nemotronReady,
          model_dir: NEMOTRON_MODEL.path,
          languages_supported: 33,
          streaming: true,
          local: true,
          requires_gpu: false,
          install_hint: nemotronReady ? null : 'pip install onnxruntime-genai soundfile + download the nemotron_asr component',
        },
      },
    },
    vad: {
      provider: vadProvider,
      state: vadState,
      silero_state: sileroState,
      model_path: vadModelPath,
      model_ready: vadModel,
      runtime_ready: vadRuntimeReady,
      runtime_package: 'onnxruntime-node',
      bundled: Boolean(coreVadModel?.passed),
      fallback: vadRuntimeReady && vadModel ? 'none' : 'simple_rms',
      note: vadRuntimeReady && vadModel
        ? 'Silero VAD model can be used by the ONNX runtime.'
        : `Simple RMS gating is active; Silero ONNX state is ${sileroState}.`,
    },
  };
}

function buildRecommendation({ voiceCoreState, voiceCoreStatus, voiceLiteState, voiceLiteStatus, fishState, sttState, vadState, fishHw, whisper }) {
  if (voiceCoreState !== 'ready') {
    return {
      priority: 'voice_core_bundle',
      label: 'Verify bundled Default Human Voice',
      details: voiceCoreStatus?.recommendation || 'The zero-install voice bundle must be present and verified before local speech is treated as production-ready.',
      action: 'verify_voice_core_bundle',
    };
  }
  if (sttState === 'runtime_missing') {
    return {
      priority: 'stt_runtime',
      label: 'Install or bundle whisper.cpp runtime',
      details: 'Voice transcription needs whisper-cli before backend STT can run.',
      action: 'install_whisper_runtime',
    };
  }
  if (sttState === 'model_missing') {
    return {
      priority: 'stt_model',
      label: 'Download Whisper base.en',
      details: 'Recommended for this PC: ggml-base.en.bin.',
      action: 'download_whisper_model',
    };
  }
  if (vadState === 'model_missing') {
    return {
      priority: 'vad_model',
      label: 'Download Silero VAD',
      details: 'No-speech detection will use simple RMS until the ONNX VAD model is installed.',
      action: 'download_vad_model',
    };
  }
  if (vadState === 'runtime_missing') {
    return {
      priority: 'vad_runtime',
      label: 'Install Silero VAD ONNX runtime',
      details: 'Silero model is present, but onnxruntime-node is not installed. Simple RMS fallback remains active.',
      action: 'install_vad_runtime',
    };
  }
  if (fishState === 'hardware_blocked') {
    return {
      priority: 'ready_or_fallback',
      label: 'Default Human Voice route is ready',
      details: `Bundled Voice Core is ready. Fish is optional and not recommended on this hardware: ${fishHw.reason}`,
      action: 'none',
    };
  }
  if (voiceLiteState === 'runtime_missing' || voiceLiteState === 'model_missing') {
    return {
      priority: 'ready_or_fallback',
      label: 'Default Human Voice route is ready',
      details: `Bundled Voice Core is ready. Legacy Voice Lite compatibility is optional and currently ${voiceLiteState}.`,
      action: 'none',
    };
  }
  return {
    priority: 'ready_or_fallback',
    label: 'Default Human Voice route is ready',
    details: 'Use the bundled default voice for local TTS, backend STT for push-to-talk, and Fish only when explicitly selected and ready.',
    action: 'none',
  };
}

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const input = fs.createReadStream(filePath);
    input.on('error', reject);
    input.on('data', (chunk) => hash.update(chunk));
    input.on('end', () => resolve(hash.digest('hex')));
  });
}

function downloadFile(url, dest, onProgress, token = null) {
  return new Promise((resolve, reject) => {
    ensureDir(path.dirname(dest));
    const tmp = `${dest}.download`;
    token?.tempFiles?.add(tmp);
    assertNotCancelled(token);
    const proto = url.startsWith('https:') ? https : http;
    const request = proto.get(url, (response) => {
      try {
        assertNotCancelled(token);
      } catch (err) {
        response.resume();
        return reject(err);
      }
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        const redirect = new URL(response.headers.location, url).toString();
        return resolve(downloadFile(redirect, dest, onProgress, token));
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        response.resume();
        return reject(new Error(`download HTTP ${response.statusCode}: ${url}`));
      }
      const total = Number(response.headers['content-length'] || 0);
      let received = 0;
      const output = fs.createWriteStream(tmp);
      response.on('data', (chunk) => {
        if (token?.cancelled) {
          try { request.destroy(new Error('download cancelled')); } catch (_err) { /* ignore */ }
          return;
        }
        received += chunk.length;
        onProgress?.({ bytes_received: received, total_bytes: total || null });
      });
      response.pipe(output);
      output.on('finish', () => {
        output.close(() => {
          try {
            assertNotCancelled(token);
            fs.renameSync(tmp, dest);
            token?.tempFiles?.delete(tmp);
            resolve({ bytes_received: received, total_bytes: total || null });
          } catch (err) {
            reject(err);
          }
        });
      });
      output.on('error', reject);
    });
    token?.requests?.add(request);
    request.on('error', (err) => {
      try { fs.unlinkSync(tmp); } catch (_unlinkErr) { /* ignore */ }
      reject(token?.cancelled ? new Error(`${token.component} download cancelled.`) : err);
    });
    request.on('close', () => token?.requests?.delete(request));
  });
}

function writeManifest(dir, data) {
  ensureDir(dir);
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({
    schema: 1,
    generated_at: new Date().toISOString(),
    ...data,
  }, null, 2) + '\n', 'utf8');
}

async function downloadKnownAsset(asset, emit, token = null) {
  downloadState = { component: asset.component, state: 'downloading', percent: 0 };
  const disk = assertFreeSpace(path.dirname(asset.path), Math.max(asset.size * 2, 256 * 1024 * 1024), asset.label);
  emit({ type: 'download.started', component: asset.component, state: 'downloading', percent: 0, message: asset.label });
  await downloadFile(asset.url, asset.path, (progress) => {
    const total = progress.total_bytes || asset.size || 0;
    const percent = total ? Math.max(0, Math.min(100, Math.round((progress.bytes_received / total) * 100))) : null;
    downloadState = { component: asset.component, state: 'downloading', percent };
    emit({
      type: 'download.progress',
      component: asset.component,
      state: 'downloading',
      percent,
      ...progress,
      message: asset.label,
    });
  }, token);
  const digest = await sha256File(asset.path);
  if (asset.sha256 && digest !== asset.sha256) {
    throw new Error(`${asset.component} checksum mismatch`);
  }
  writeManifest(path.dirname(asset.path), {
    component: asset.component,
    label: asset.label,
    source: asset.source,
    url: asset.url,
    license: asset.license,
    disk,
    files: [{ file: path.basename(asset.path), size: fs.statSync(asset.path).size, sha256: digest }],
  });
  downloadState = null;
  emit({ type: 'download.complete', component: asset.component, state: 'ready', percent: 100, message: `${asset.label} ready` });
  return true;
}

function safeModelPath(baseDir, siblingName) {
  const normalized = path.normalize(String(siblingName || '')).replace(/^(\.\.[/\\])+/, '');
  const resolvedBase = path.resolve(baseDir);
  const target = path.resolve(baseDir, normalized);
  if (target !== resolvedBase && !target.startsWith(`${resolvedBase}${path.sep}`)) {
    throw new Error(`Unsafe model file path: ${siblingName}`);
  }
  return target;
}

async function downloadFishModel(options, emit, token = null) {
  if (!options.accept_personal_license && !hasFishLicenseAck()) {
    throw new Error('Fish Speech personal-local license acknowledgement is required before download.');
  }
  writeFishLicenseAck(options.actor || 'local-user');
  const status = await getStatus();
  if (status.tts.fish_speech.hardware_blocked && !options.force) {
    throw new Error(`Fish Speech hardware blocked: ${status.tts.fish_speech.hardware_reason}`);
  }

  const apiUrl = `https://huggingface.co/api/models/${FISH_MODEL.repo}?revision=${encodeURIComponent(FISH_MODEL.revision)}`;
  assertFreeSpace(FISH_MODEL.path, 45 * 1024 * 1024 * 1024, FISH_MODEL.label);
  emit({ type: 'download.started', component: 'fish_speech', state: 'downloading', percent: 0, message: 'Reading Fish S2-Pro file list' });
  assertNotCancelled(token);
  const response = await fetch(apiUrl);
  if (!response.ok) throw new Error(`Fish model metadata HTTP ${response.status}`);
  const data = await response.json();
  const siblings = (data.siblings || [])
    .map((item) => item.rfilename)
    .filter((name) => name && name !== '.gitattributes');
  if (!siblings.length) throw new Error('Fish model file list is empty.');

  let index = 0;
  const files = [];
  for (const name of siblings) {
    index += 1;
    const urlPath = name.split('/').map(encodeURIComponent).join('/');
    const fileUrl = `https://huggingface.co/${FISH_MODEL.repo}/resolve/${FISH_MODEL.revision}/${urlPath}`;
    const dest = safeModelPath(FISH_MODEL.path, name);
    emit({
      type: 'download.progress',
      component: 'fish_speech',
      state: 'downloading',
      percent: Math.round(((index - 1) / siblings.length) * 100),
      message: `Downloading ${name}`,
    });
    await downloadFile(fileUrl, dest, () => {}, token);
    files.push({ file: name, size: fs.statSync(dest).size, sha256: await sha256File(dest) });
  }
  writeManifest(FISH_MODEL.path, {
    component: FISH_MODEL.component,
    label: FISH_MODEL.label,
    repo: FISH_MODEL.repo,
    revision: FISH_MODEL.revision,
    source: FISH_MODEL.source,
    license: FISH_MODEL.license,
    files,
  });
  emit({ type: 'download.complete', component: 'fish_speech', state: 'model_ready', percent: 100, message: 'Fish S2-Pro assets downloaded' });
  return true;
}

async function downloadNemotronModel(emit, token = null) {
  const apiUrl = `https://huggingface.co/api/models/${NEMOTRON_MODEL.repo}?revision=${encodeURIComponent(NEMOTRON_MODEL.revision)}`;
  // ~0.6B int4 + external .data tensors; reserve generously and verify free space.
  assertFreeSpace(NEMOTRON_MODEL.path, 3 * 1024 * 1024 * 1024, NEMOTRON_MODEL.label);
  downloadState = { component: NEMOTRON_MODEL.component, state: 'downloading', percent: 0 };
  emit({ type: 'download.started', component: NEMOTRON_MODEL.component, state: 'downloading', percent: 0, message: 'Reading Nemotron ASR file list' });
  assertNotCancelled(token);
  const response = await fetch(apiUrl);
  if (!response.ok) throw new Error(`Nemotron model metadata HTTP ${response.status}`);
  const data = await response.json();
  const siblings = (data.siblings || [])
    .map((item) => item.rfilename)
    .filter((name) => name && name !== '.gitattributes');
  if (!siblings.length) throw new Error('Nemotron model file list is empty.');

  let index = 0;
  const files = [];
  for (const name of siblings) {
    index += 1;
    assertNotCancelled(token);
    const urlPath = name.split('/').map(encodeURIComponent).join('/');
    const fileUrl = `https://huggingface.co/${NEMOTRON_MODEL.repo}/resolve/${NEMOTRON_MODEL.revision}/${urlPath}`;
    const dest = safeModelPath(NEMOTRON_MODEL.path, name);
    const percent = Math.round(((index - 1) / siblings.length) * 100);
    downloadState = { component: NEMOTRON_MODEL.component, state: 'downloading', percent };
    emit({ type: 'download.progress', component: NEMOTRON_MODEL.component, state: 'downloading', percent, message: `Downloading ${name}` });
    await downloadFile(fileUrl, dest, () => {}, token);
    files.push({ file: name, size: fs.statSync(dest).size, sha256: await sha256File(dest) });
  }
  writeManifest(NEMOTRON_MODEL.path, {
    component: NEMOTRON_MODEL.component,
    label: NEMOTRON_MODEL.label,
    repo: NEMOTRON_MODEL.repo,
    revision: NEMOTRON_MODEL.revision,
    source: NEMOTRON_MODEL.source,
    license: NEMOTRON_MODEL.license,
    files,
  });
  downloadState = null;
  const missing = NEMOTRON_MODEL.required_files.filter((f) => !exists(path.join(NEMOTRON_MODEL.path, f)));
  if (missing.length) throw new Error(`Nemotron download incomplete; missing ${missing.join(', ')}`);
  emit({ type: 'download.complete', component: NEMOTRON_MODEL.component, state: 'ready', percent: 100, message: 'Nemotron ASR model ready' });
  return true;
}

async function download(component, options = {}, emit = () => {}) {
  const name = String(component || '').trim();
  const token = name.startsWith('voice_lite') || name === 'piper_runtime' || name === 'base_en' || name === 'base_nl'
    ? null
    : createDownloadToken(name || 'unknown');
  try {
    if (name === 'voice_core' || name === 'voice_core_local' || name === 'voice_core_bundle') {
      emit({ type: 'bundle.verify.started', component: 'voice_core_bundle', state: 'starting', percent: 0, message: 'Verifying bundled Default Human Voice.' });
      const result = await voiceCore.verifyBundle({ install: true });
      emit({
        type: result.ok ? 'bundle.verify.complete' : 'bundle.verify.error',
        component: 'voice_core_bundle',
        state: result.ok ? 'ready' : (result.state || 'error'),
        percent: result.ok ? 100 : null,
        message: result.ok ? 'Bundled Default Human Voice verified.' : 'Bundled Default Human Voice is missing or incomplete.',
      });
      return result;
    }
    if (name.startsWith('voice_lite') || name === 'piper_runtime' || name === 'base_en' || name === 'base_nl') {
      return await voiceLite.download(name, options, emit);
    }
    if (name === 'whisper' || name === 'whisper_model') return await downloadKnownAsset(ASSETS.whisper_model, emit, token);
    if (name === 'vad' || name === 'vad_model') return await downloadKnownAsset(ASSETS.vad_model, emit, token);
    if (name === 'fish' || name === 'fish_speech') return await downloadFishModel(options, emit, token);
    if (name === 'nemotron' || name === 'nemotron_asr') return await downloadNemotronModel(emit, token);
    throw new Error(`Unknown voice runtime component: ${name}`);
  } catch (err) {
    downloadState = null;
    emit({
      type: 'download.error',
      component: name || 'unknown',
      state: 'error',
      percent: null,
      error: String(err.message || err),
      message: String(err.message || err),
    });
    throw err;
  } finally {
    if (activeDownload === token) activeDownload = null;
  }
}

async function waitForFishReady(timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const ready = await fishSpeech.checkAvailability().catch(() => false);
    if (ready) return true;
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  return false;
}

async function startFish(options = {}) {
  const status = await getStatus();
  if (status.tts.fish_speech.live) return { ok: true, already_running: true, status };
  if (fishProcess) return { ok: true, starting: true, status };
  if (!status.tts.fish_speech.source_ready) throw new Error(`Fish Speech source/runtime missing: ${status.tts.fish_speech.source_path}`);
  if (!status.tts.fish_speech.license_acknowledged) {
    if (!options.accept_personal_license) throw new Error('Fish personal-local license acknowledgement is required.');
    writeFishLicenseAck(options.actor || 'local-user');
  }
  if (!status.tts.fish_speech.model_ready) throw new Error(`Fish Speech model missing: ${status.tts.fish_speech.model_path}`);
  if (status.tts.fish_speech.hardware_blocked && !options.force) {
    throw new Error(`Fish Speech hardware blocked: ${status.tts.fish_speech.hardware_reason}`);
  }

  const source = status.tts.fish_speech.source_path;
  const python = process.env.FISH_SPEECH_PYTHON || 'python3';
  const args = [
    'tools/api_server.py',
    '--listen', process.env.FISH_SPEECH_LISTEN || '127.0.0.1:8080',
    '--llama-checkpoint-path', FISH_MODEL.path,
    '--decoder-checkpoint-path', path.join(FISH_MODEL.path, 'codec.pth'),
    '--decoder-config-name', process.env.FISH_SPEECH_DECODER_CONFIG || 'modded_dac_vq',
    '--device', process.env.FISH_SPEECH_DEVICE || 'cuda',
    '--workers', process.env.FISH_SPEECH_WORKERS || '1',
  ];

  fishStarting = true;
  log('info', `Starting Fish Speech: ${python} ${args.join(' ')}`);
  fishProcess = spawn(python, args, { cwd: source, stdio: ['ignore', 'pipe', 'pipe'] });
  fishProcess.stdout.on('data', (chunk) => log('info', chunk.toString('utf8').trim()));
  fishProcess.stderr.on('data', (chunk) => log('warn', chunk.toString('utf8').trim()));
  fishProcess.once('exit', (code, signal) => {
    log('warn', `Fish Speech exited code=${code} signal=${signal || ''}`);
    fishProcess = null;
    fishStarting = false;
  });
  const ready = await waitForFishReady(Number(options.timeoutMs || 45000));
  fishStarting = false;
  if (!ready) throw new Error('Fish Speech did not become healthy before timeout.');
  return { ok: true, status: await getStatus() };
}

async function stopFish() {
  if (!fishProcess) return { ok: true, stopped: false };
  const proc = fishProcess;
  fishProcess = null;
  fishStarting = false;
  try { proc.kill('SIGTERM'); } catch (_err) { /* ignore */ }
  log('info', 'Fish Speech stop requested.');
  return { ok: true, stopped: true };
}

async function startVoiceLite(options = {}) {
  return voiceLite.prewarm(options);
}

async function startVoiceCore(options = {}) {
  return voiceCore.prewarm(options);
}

function parseWavPcm16(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 44 || buffer.toString('ascii', 0, 4) !== 'RIFF') return null;
  let offset = 12;
  let fmt = null;
  let dataStart = -1;
  let dataSize = 0;
  while (offset + 8 <= buffer.length) {
    const id = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (id === 'fmt ') {
      fmt = {
        audioFormat: buffer.readUInt16LE(start),
        channels: buffer.readUInt16LE(start + 2),
        sampleRate: buffer.readUInt32LE(start + 4),
        bitsPerSample: buffer.readUInt16LE(start + 14),
      };
    } else if (id === 'data') {
      dataStart = start;
      dataSize = size;
      break;
    }
    offset = start + size + (size % 2);
  }
  if (!fmt || dataStart < 0 || fmt.audioFormat !== 1 || fmt.bitsPerSample !== 16) return null;
  return { ...fmt, dataStart, dataSize: Math.min(dataSize, buffer.length - dataStart) };
}

function makePcm16Wav(samples, sampleRate = 16000) {
  const pcm = Buffer.alloc(samples.length * 2);
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, Number(samples[i]) || 0));
    pcm.writeInt16LE(Math.round(sample * 32767), i * 2);
  }
  const buffer = Buffer.alloc(44 + pcm.length);
  buffer.write('RIFF', 0, 'ascii');
  buffer.writeUInt32LE(36 + pcm.length, 4);
  buffer.write('WAVE', 8, 'ascii');
  buffer.write('fmt ', 12, 'ascii');
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36, 'ascii');
  buffer.writeUInt32LE(pcm.length, 40);
  pcm.copy(buffer, 44);
  return buffer;
}

function normalizeWavForWhisper(filePath) {
  const buffer = fs.readFileSync(filePath);
  const wav = parseWavPcm16(buffer);
  if (!wav) throw new Error('Whisper STT expects a PCM16 WAV file.');
  if (wav.sampleRate === 16000 && wav.channels === 1) return { filePath, cleanup: null, normalized: false };

  const frames = Math.floor(wav.dataSize / 2 / wav.channels);
  const mono = new Float32Array(frames);
  for (let frame = 0; frame < frames; frame += 1) {
    let sum = 0;
    for (let ch = 0; ch < wav.channels; ch += 1) {
      const offset = wav.dataStart + ((frame * wav.channels + ch) * 2);
      sum += buffer.readInt16LE(offset) / 32768;
    }
    mono[frame] = sum / wav.channels;
  }

  const targetRate = 16000;
  const outFrames = Math.max(1, Math.round((mono.length * targetRate) / wav.sampleRate));
  const resampled = new Float32Array(outFrames);
  for (let i = 0; i < outFrames; i += 1) {
    const src = (i * wav.sampleRate) / targetRate;
    const left = Math.floor(src);
    const right = Math.min(mono.length - 1, left + 1);
    const frac = src - left;
    resampled[i] = mono[left] * (1 - frac) + mono[right] * frac;
  }

  const normalizedPath = path.join(os.tmpdir(), `voice-whisper-input-${Date.now()}-${crypto.randomUUID()}.wav`);
  fs.writeFileSync(normalizedPath, makePcm16Wav(resampled, targetRate));
  return { filePath: normalizedPath, cleanup: normalizedPath, normalized: true, source_sample_rate: wav.sampleRate, source_channels: wav.channels };
}

function hasLikelySpeech(buffer) {
  const wav = parseWavPcm16(buffer);
  if (!wav || wav.dataSize < 3200) return { detected: true, confidence: 0.5, method: 'unknown_format' };
  const samples = Math.floor(wav.dataSize / 2);
  let sumSquares = 0;
  let peak = 0;
  for (let i = 0; i < samples; i++) {
    const sample = buffer.readInt16LE(wav.dataStart + i * 2) / 32768;
    sumSquares += sample * sample;
    peak = Math.max(peak, Math.abs(sample));
  }
  const rms = Math.sqrt(sumSquares / Math.max(1, samples));
  const detected = rms > 0.008 || peak > 0.05;
  return { detected, confidence: Math.max(0, Math.min(1, rms * 18)), rms, peak, method: 'simple_rms' };
}

function cleanWhisperText(raw) {
  return String(raw || '')
    .split('\n')
    .map((line) => line.replace(/^\s*\[[^\]]+\]\s*/g, '').trim())
    .filter((line) => line && !/^whisper_/i.test(line) && !/^system_info:/i.test(line))
    .join(' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function bundledLibraryPath(binary) {
  const base = path.dirname(binary || '');
  return [
    base,
    path.join(base, '..', 'lib'),
    path.join(base, '..', 'src'),
    path.join(base, '..', 'ggml', 'src'),
    path.join(base, '..', 'ggml', 'src', 'cpu'),
    path.join(base, '..', '..', 'lib'),
    path.join(base, '..', '..', 'src'),
    path.join(base, '..', '..', 'ggml', 'src'),
    path.join(base, '..', '..', 'ggml', 'src', 'cpu'),
  ].map((dir) => path.resolve(dir)).filter(exists).join(path.delimiter);
}

function makeSilenceWav(durationMs = 500, sampleRate = 16000) {
  const samples = Math.max(1, Math.round((durationMs / 1000) * sampleRate));
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write('RIFF', 0, 'ascii');
  buffer.writeUInt32LE(36 + samples * 2, 4);
  buffer.write('WAVE', 8, 'ascii');
  buffer.write('fmt ', 12, 'ascii');
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36, 'ascii');
  buffer.writeUInt32LE(samples * 2, 40);
  return buffer;
}

function checkState(id, label, passed, message, details = {}) {
  return {
    id,
    label,
    state: passed ? 'pass' : details.warning ? 'warning' : 'fail',
    passed: Boolean(passed),
    blocking: Boolean(!passed && !details.warning),
    message,
    ...details,
  };
}

async function doctor() {
  const status = await getStatus();
  const voiceCoreStatus = status.tts?.voice_core_local || {};
  const voiceLiteStatus = status.tts?.voice_lite || {};
  const fish = status.tts?.fish_speech || {};
  const stt = status.stt || {};
  const vad = status.vad || {};
  const checks = [
    checkState(
      'voice_core_bundle',
      'Bundled Default Human Voice',
      voiceCoreStatus.state === 'ready',
      voiceCoreStatus.state === 'ready'
        ? 'Default Human Voice bundle is verified. No user voice training, GPU, internet, or manual install is required.'
        : voiceCoreStatus.recommendation || 'Bundled voice-core is missing or unverified.',
      { action: voiceCoreStatus.state === 'ready' ? 'none' : 'verify_voice_core_bundle' },
    ),
    checkState(
      'voice_core_en_default',
      'English natural default voice',
      Boolean(voiceCoreStatus.tts_en_ready),
      voiceCoreStatus.tts_en_ready
        ? `${voiceCoreStatus.tts_en_engine || 'local CPU'} EN default voice ready: ${voiceCoreStatus.active_voice?.voice || 'en_US-lessac-high'}.`
        : 'English default voice runtime/model/config is missing from the bundled voice core.',
      { action: voiceCoreStatus.tts_en_ready ? 'none' : 'repair_voice_core_bundle' },
    ),
    checkState(
      'voice_core_nl_default',
      'Dutch local default voice',
      Boolean(voiceCoreStatus.tts_nl_ready),
      voiceCoreStatus.tts_nl_ready
        ? 'Piper NL default voice is ready.'
        : 'Piper NL runtime/model/config is missing from the bundled voice core.',
      { action: voiceCoreStatus.tts_nl_ready ? 'none' : 'repair_voice_core_bundle' },
    ),
    checkState(
      'voice_lite_runtime',
      'Optional Voice Lite Piper runtime',
      Boolean(voiceLiteStatus.runtime_ready),
      voiceLiteStatus.runtime_ready
        ? `Piper runtime found at ${voiceLiteStatus.runtime?.binary}`
        : 'Optional compatibility runtime is missing. This does not block the bundled default voice.',
      { action: voiceLiteStatus.runtime_ready ? 'none' : 'download_voice_lite_runtime', warning: !voiceLiteStatus.runtime_ready },
    ),
    checkState(
      'voice_lite_en_model',
      'Optional Voice Lite English base voice',
      Boolean(voiceLiteStatus.base_en_ready || voiceLiteStatus.custom_en_ready),
      voiceLiteStatus.base_en_ready || voiceLiteStatus.custom_en_ready
        ? 'English voice model is installed.'
        : 'Optional Voice Lite English model is missing.',
      { action: voiceLiteStatus.base_en_ready || voiceLiteStatus.custom_en_ready ? 'none' : 'download_voice_lite_base_en', warning: !(voiceLiteStatus.base_en_ready || voiceLiteStatus.custom_en_ready) },
    ),
    checkState(
      'voice_lite_nl_model',
      'Optional Voice Lite Dutch base voice',
      Boolean(voiceLiteStatus.base_nl_ready || voiceLiteStatus.custom_nl_ready),
      voiceLiteStatus.base_nl_ready || voiceLiteStatus.custom_nl_ready
        ? 'Dutch voice model is installed.'
        : 'Optional Voice Lite Dutch model is missing.',
      { action: voiceLiteStatus.base_nl_ready || voiceLiteStatus.custom_nl_ready ? 'none' : 'download_voice_lite_base_nl', warning: !(voiceLiteStatus.base_nl_ready || voiceLiteStatus.custom_nl_ready) },
    ),
    checkState(
      'whisper_runtime',
      'Whisper.cpp runtime',
      Boolean(stt.runtime?.binary),
      stt.runtime?.binary ? `whisper-cli found at ${stt.runtime.binary}` : 'whisper-cli runtime is missing.',
      { action: stt.runtime?.binary ? 'none' : 'install_whisper_runtime' },
    ),
    checkState(
      'whisper_model',
      'Whisper base.en model',
      Boolean(stt.model_ready),
      stt.model_ready ? `Whisper model installed at ${stt.model_path}` : 'Whisper base.en model is missing.',
      { action: stt.model_ready ? 'none' : 'download_whisper_model' },
    ),
    checkState(
      'vad_model',
      'Silero VAD model',
      Boolean(vad.model_ready),
      vad.model_ready ? `Silero VAD model installed at ${vad.model_path}` : 'Silero VAD model is missing; RMS fallback is active.',
      { action: vad.model_ready ? 'none' : 'download_vad_model', warning: !vad.model_ready },
    ),
    checkState(
      'vad_runtime',
      'Silero VAD ONNX runtime',
      Boolean(vad.runtime_ready),
      vad.runtime_ready ? 'onnxruntime-node is installed.' : 'onnxruntime-node is missing; RMS fallback is active.',
      { action: vad.runtime_ready ? 'none' : 'install_vad_runtime', warning: !vad.runtime_ready },
    ),
    checkState(
      'fish_gate',
      'Fish premium hardware gate',
      !fish.hardware_blocked,
      fish.hardware_blocked ? fish.hardware_reason : 'Fish is not hardware-blocked.',
      { action: fish.hardware_blocked ? 'use_voice_lite' : 'none', warning: fish.hardware_blocked },
    ),
  ];
  return {
    ok: checks.every((item) => item.passed || item.warning),
    generated_at: new Date().toISOString(),
    status,
    checks,
    blocking: checks.filter((item) => item.blocking),
    recommendation: status.recommendation,
  };
}

async function selfTest(options = {}) {
  const started = Date.now();
  const checks = [];
  const artifacts = [];
  const statusBefore = await getStatus();

  const silence = hasLikelySpeech(makeSilenceWav());
  checks.push(checkState(
    'vad_silence_gate',
    'No-speech gate',
    silence.detected === false,
    silence.detected === false
      ? `Silence rejected by ${silence.method}.`
      : `Silence was not rejected by ${silence.method}.`,
    { vad: silence, warning: silence.detected !== false },
  ));

  try {
    const prewarm = await startVoiceCore(options);
    checks.push(checkState(
      'voice_core_prewarm',
      'Default Human Voice prewarm',
      Boolean(prewarm.ok),
      prewarm.ok ? 'Default Human Voice produced a warmup sample.' : prewarm.message || 'Default Human Voice prewarm failed.',
      { result: prewarm },
    ));
  } catch (err) {
    checks.push(checkState('voice_core_prewarm', 'Default Human Voice prewarm', false, String(err.message || err)));
  }

  const samplePhrases = [
    { id: 'tts_en', language: 'en', emotion: 'warm_confident', text: options.text_en || 'System ready. I can speak locally with a natural default voice.' },
    { id: 'tts_nl', language: 'nl', emotion: 'calm', text: options.text_nl || 'Systeem klaar. Ik kan lokaal spreken met een standaardstem.' },
  ];
  for (const phrase of samplePhrases) {
    try {
      const result = await voiceCore.synthesize(phrase.text, {
        language: phrase.language,
        voice: options.voice || 'default',
        emotion: phrase.emotion,
        timeoutMs: Number(options.timeoutMs || 20000),
      });
      const artifact = voiceCore.saveArtifact(result.audioBuf, {});
      artifacts.push({ ...artifact, language: phrase.language, text: phrase.text, meta: result.meta });
      checks.push(checkState(
        phrase.id,
        `Default Human Voice ${phrase.language.toUpperCase()} synthesis`,
        true,
        `Generated ${phrase.language.toUpperCase()} WAV. TTFA ${result.meta?.ttfa_ms ?? 'n/a'}ms, RTF ${result.meta?.rtf ?? 'n/a'}.`,
        { artifact, meta: result.meta },
      ));
    } catch (err) {
      checks.push(checkState(
        phrase.id,
        `Default Human Voice ${phrase.language.toUpperCase()} synthesis`,
        false,
        String(err.message || err),
      ));
    }
  }

  const statusAfter = await getStatus();
  const sttReady = statusAfter.stt?.state === 'ready';
  checks.push(checkState(
    'stt_readiness',
    'Backend STT readiness',
    sttReady,
    sttReady
      ? 'Whisper STT is ready for uploaded 16k mono WAV.'
      : `Whisper STT is ${statusAfter.stt?.state || 'unknown'}; push-to-talk will use explicit fallback if needed.`,
    { warning: !sttReady, stt: statusAfter.stt },
  ));

  return {
    ok: checks.every((item) => item.passed || item.warning),
    generated_at: new Date().toISOString(),
    elapsed_ms: Date.now() - started,
    checks,
    artifacts,
    status_before: statusBefore,
    status_after: statusAfter,
    blocking: checks.filter((item) => item.blocking),
  };
}

// Engine-aware STT entry point. Picks Nemotron or whisper.cpp from the caller's
// preference (config.asr.engine / VOICE_ASR_ENGINE) and availability. Nemotron failures
// degrade to whisper when whisper is ready, so a turn is never silently lost.
async function transcribeWav(filePath, options = {}) {
  const status = await getStatus();
  const whisperReady = status.stt.engines.whisper.state === 'ready';
  const nemotronReady = status.stt.engines.nemotron.state === 'ready';
  const engine = resolveAsrEngine(options.engine, { whisperReady, nemotronReady });
  if (engine === 'none') {
    throw new Error(`Local STT is not ready: ${status.stt.state}`);
  }
  if (engine === 'nemotron') {
    const result = await nemotronAsr.transcribe(filePath, {
      language: options.language,
      langId: options.langId,
      timeoutMs: options.timeoutMs,
    });
    if (result.ok) {
      if (!result.text) throw new Error('Nemotron ASR returned an empty transcript.');
      return {
        text: result.text,
        confidence: null,
        elapsed_ms: result.elapsed_ms,
        model: NEMOTRON_MODEL.label,
        runtime: 'onnxruntime-genai',
        engine: 'nemotron',
        normalized: false,
        source_sample_rate: result.sample_rate || 16000,
        source_channels: 1,
      };
    }
    log('warn', `Nemotron ASR failed (${result.reason})${whisperReady ? '; falling back to whisper.cpp' : ''}`);
    if (!whisperReady) throw new Error(`Nemotron ASR failed: ${result.reason}`);
  }
  return transcribeWithWhisper(filePath, options, status);
}

async function transcribeWithWhisper(filePath, options = {}, status = null) {
  status = status || await getStatus();
  if (!status.stt.runtime?.binary || status.stt.engines.whisper.state !== 'ready') {
    throw new Error(`Local Whisper STT is not ready: ${status.stt.engines.whisper.state}`);
  }
  const binary = status.stt.runtime.binary;
  const model = status.stt.model_path;
  const normalizedInput = normalizeWavForWhisper(filePath);
  const outBase = path.join(os.tmpdir(), `voice-whisper-${Date.now()}-${crypto.randomUUID()}`);
  const threads = String(options.threads || Math.max(2, Math.min(8, Math.floor((os.cpus()?.length || 4) / 2))));
  const args = ['-m', model, '-f', normalizedInput.filePath, '-t', threads, '-nt', '-otxt', '-of', outBase];
  log('info', `Running Whisper STT: ${binary} ${args.join(' ')}`);
  const libPath = bundledLibraryPath(binary);
  const started = Date.now();
  let result = null;
  try {
    result = await new Promise((resolve, reject) => {
      const child = spawn(binary, args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
          ...process.env,
          LD_LIBRARY_PATH: [process.env.LD_LIBRARY_PATH, libPath].filter(Boolean).join(path.delimiter),
        },
      });
      let stdout = '';
      let stderr = '';
      const timer = setTimeout(() => {
        try { child.kill('SIGTERM'); } catch (_err) { /* ignore */ }
        reject(new Error('Whisper transcription timeout'));
      }, Number(options.timeoutMs || 120000));
      child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
      child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
      child.once('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });
      child.once('exit', (code) => {
        clearTimeout(timer);
        if (code !== 0 || /failed to read WAV|error:/i.test(`${stderr}\n${stdout}`)) {
          return reject(new Error(`Whisper exited with code ${code}: ${stderr || stdout}`));
        }
        resolve({ stdout, stderr });
      });
    });
  } finally {
    if (normalizedInput.cleanup) {
      try { fs.unlinkSync(normalizedInput.cleanup); } catch (_err) { /* ignore */ }
    }
  }
  let text = '';
  const txtPath = `${outBase}.txt`;
  if (exists(txtPath)) {
    text = fs.readFileSync(txtPath, 'utf8');
    try { fs.unlinkSync(txtPath); } catch (_err) { /* ignore */ }
  }
  text = cleanWhisperText(text || result.stdout);
  if (!text) throw new Error('Whisper returned an empty transcript.');
  return {
    text,
    confidence: null,
    elapsed_ms: Date.now() - started,
    model,
    runtime: binary,
    normalized: normalizedInput.normalized,
    source_sample_rate: normalizedInput.source_sample_rate || 16000,
    source_channels: normalizedInput.source_channels || 1,
  };
}

function getLogs(limit = 100) {
  return {
    ok: true,
    logs: logLines.slice(-Math.max(1, Math.min(500, Number(limit) || 100))),
  };
}

module.exports = {
  ASSETS,
  FISH_MODEL,
  NEMOTRON_MODEL,
  AI_HOME,
  VOICE_MODEL_ROOT,
  resolveAsrEngine,
  nemotronAsrStatus: nemotronAsr.getStatus,
  getStatus,
  getLogs,
  doctor,
  selfTest,
  download,
  cancelDownload,
  startFish,
  stopFish,
  startVoiceCore,
  startVoiceLite,
  voiceCoreStatus: voiceCore.getStatus,
  verifyVoiceCoreBundle: voiceCore.verifyBundle,
  synthesizeVoiceCore: voiceCore.synthesize,
  saveVoiceCoreArtifact: voiceCore.saveArtifact,
  benchmarkVoiceCore: voiceCore.benchmark,
  voiceCoreSamples: voiceCore.sampleFiles,
  getVoiceCoreSampleFile: voiceCore.sampleFile,
  planSpeech: voiceCore.planSpeech,
  voiceLiteStatus: voiceLite.getStatus,
  synthesizeVoiceLite: voiceLite.synthesize,
  saveVoiceLiteArtifact: voiceLite.saveArtifact,
  voiceLiteDatasetStatus: voiceLite.datasetStatus,
  saveVoiceLiteDatasetManifest: voiceLite.saveDatasetManifest,
  startVoiceLiteTraining: voiceLite.startTraining,
  getVoiceLiteTrainingJob: voiceLite.getTrainingJob,
  benchmarkVoiceLite: voiceLite.benchmark,
  activateVoiceLite: voiceLite.activate,
  transcribeWav,
  hasLikelySpeech,
  writeFishLicenseAck,
};
