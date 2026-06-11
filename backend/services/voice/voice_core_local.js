'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { planSpeech, SUPPORTED_EMOTIONS } = require('./speech_planner');

const REPO_ROOT = path.resolve(__dirname, '../../..');
const AI_HOME = path.resolve(
  process.env.AI_HOME ||
  process.env.AI_EMPLOYEE_HOME ||
  path.join(os.homedir(), '.ai-employee')
);

const PLATFORM = process.env.VOICE_CORE_PLATFORM || 'linux-x64';
const SOURCE_ROOT = path.resolve(process.env.VOICE_CORE_BUNDLE_ROOT || path.join(REPO_ROOT, 'resources', 'voice-core'));
const INSTALL_ROOT = path.resolve(process.env.VOICE_CORE_HOME || path.join(AI_HOME, 'voice-core'));
const STATE_ROOT = path.join(AI_HOME, 'state', 'voice');
const ARTIFACT_ROOT = path.join(REPO_ROOT, 'state', 'artifacts');
const CACHE_MAX_ITEMS = Math.max(8, Number(process.env.VOICE_CORE_CACHE_ITEMS) || 96);
const CACHE_MAX_BYTES = Math.max(4 * 1024 * 1024, Number(process.env.VOICE_CORE_CACHE_BYTES) || 64 * 1024 * 1024);
const DEFAULT_THREADS = Math.max(2, Math.min(4, Math.floor((os.cpus()?.length || 4) / 3) || 2));

const DEFAULT_MANIFEST = {
  schema: 1,
  bundle_id: 'voice-core-local-template',
  platform: PLATFORM,
  install_mode: 'bundled',
  requires_network: false,
  requires_gpu: false,
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
    { id: 'piper_cli', role: 'runtime', engine: 'piper_onnx_cpu', language: 'multi', path: `runtimes/${PLATFORM}/piper/piper`, required: true, executable: true, license: 'MIT' },
    { id: 'piper_en_model', role: 'model', engine: 'piper_onnx_cpu', language: 'en', path: 'models/tts/piper-en/en_US-lessac-high.onnx', required: true, license: 'MIT' },
    { id: 'piper_en_config', role: 'config', engine: 'piper_onnx_cpu', language: 'en', path: 'models/tts/piper-en/en_US-lessac-high.onnx.json', required: true, license: 'MIT' },
    { id: 'piper_en_male_model', role: 'model', engine: 'piper_onnx_cpu', language: 'en', path: 'models/tts/piper-en/en_US-ryan-high.onnx', required: true, license: 'MIT' },
    { id: 'piper_en_male_config', role: 'config', engine: 'piper_onnx_cpu', language: 'en', path: 'models/tts/piper-en/en_US-ryan-high.onnx.json', required: true, license: 'MIT' },
    { id: 'piper_nl_model', role: 'model', engine: 'piper_onnx_cpu', language: 'nl', path: 'models/tts/piper-nl/nl_NL-mls-medium.onnx', required: true, license: 'MIT' },
    { id: 'piper_nl_config', role: 'config', engine: 'piper_onnx_cpu', language: 'nl', path: 'models/tts/piper-nl/nl_NL-mls-medium.onnx.json', required: true, license: 'MIT' },
    { id: 'kokoro_cli', role: 'runtime', engine: 'kokoro_onnx_cli', language: 'en', path: `runtimes/${PLATFORM}/kokoro/kokoro-tts`, required: false, executable: true, license: 'Apache-2.0' },
    { id: 'kokoro_en_model', role: 'model', engine: 'kokoro_onnx', language: 'en', path: 'models/tts/kokoro-en/kokoro-v1.0.onnx', required: false, license: 'Apache-2.0' },
    { id: 'kokoro_en_voices', role: 'voice_pack', engine: 'kokoro_onnx', language: 'en', path: 'models/tts/kokoro-en/voices-v1.0.bin', required: false, license: 'Apache-2.0' },
    { id: 'whisper_cli', role: 'runtime', engine: 'whisper.cpp', language: 'en', path: `runtimes/${PLATFORM}/whisper/whisper-cli`, required: true, executable: true, license: 'MIT' },
    { id: 'whisper_base_en', role: 'model', engine: 'whisper.cpp', language: 'en', path: 'models/stt/whisper/ggml-base.en.bin', required: true, license: 'MIT' },
    { id: 'silero_vad', role: 'model', engine: 'silero_vad_onnx', language: 'multi', path: 'models/vad/silero-vad.onnx', required: true, license: 'MIT' },
  ],
  samples: [
    { id: 'en_default', language: 'en', emotion: 'warm_confident', path: 'samples/en-default.wav' },
    { id: 'nl_default', language: 'nl', emotion: 'calm', path: 'samples/nl-default.wav' },
  ],
};

const cache = new Map();
let cacheBytes = 0;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function exists(filePath) {
  try { return fs.existsSync(filePath); } catch (_err) { return false; }
}

function isExecutable(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return fs.statSync(filePath).isFile();
  } catch (_err) {
    return false;
  }
}

function readJson(filePath, fallback = null) {
  try { return JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch (_err) { return fallback; }
}

function writeJson(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

function manifestPath(root) {
  return path.join(root, 'manifest.json');
}

function healthPath() {
  return path.join(STATE_ROOT, 'voice_core_local_health.json');
}

function locateRoot() {
  if (exists(manifestPath(INSTALL_ROOT))) return { root: INSTALL_ROOT, source: 'app_home' };
  if (exists(manifestPath(SOURCE_ROOT))) return { root: SOURCE_ROOT, source: 'packaged' };
  return { root: INSTALL_ROOT, source: 'missing' };
}

function loadManifest(root) {
  const fromDisk = readJson(manifestPath(root), null);
  if (!fromDisk) return { manifest: null, error: exists(root) ? 'manifest_missing' : 'bundle_missing' };
  const components = Array.isArray(fromDisk.components) && fromDisk.components.length
    ? fromDisk.components
    : DEFAULT_MANIFEST.components;
  return {
    manifest: {
      ...DEFAULT_MANIFEST,
      ...fromDisk,
      components,
      samples: Array.isArray(fromDisk.samples) ? fromDisk.samples : DEFAULT_MANIFEST.samples,
    },
    error: null,
  };
}

function safeResolve(root, relativePath) {
  const resolvedRoot = path.resolve(root);
  const target = path.resolve(root, String(relativePath || ''));
  if (target !== resolvedRoot && !target.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`Unsafe voice bundle path: ${relativePath}`);
  }
  return target;
}

function sha256FileSync(filePath) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('hex');
}

function componentMap(manifest) {
  const map = new Map();
  for (const component of manifest?.components || []) map.set(component.id, component);
  return map;
}

function inspectComponents(root, manifest, options = {}) {
  const checks = [];
  let missingRuntime = false;
  let missingModel = false;
  let corrupt = false;

  for (const component of manifest.components || []) {
    const filePath = safeResolve(root, component.path);
    const fileExists = exists(filePath);
    const executableOk = !component.executable || isExecutable(filePath);
    let sha256 = null;
    let checksumOk = true;
    if (fileExists && options.verifyHashes && component.sha256) {
      sha256 = sha256FileSync(filePath);
      checksumOk = sha256 === component.sha256;
    }
    const passed = fileExists && executableOk && checksumOk;
    if (component.required && !passed) {
      if (!fileExists || !executableOk) {
        if (component.role === 'runtime') missingRuntime = true;
        else missingModel = true;
      }
      if (!checksumOk) corrupt = true;
    }
    checks.push({
      id: component.id,
      role: component.role,
      engine: component.engine,
      language: component.language,
      required: component.required !== false,
      path: filePath,
      exists: fileExists,
      executable: Boolean(component.executable),
      executable_ok: executableOk,
      sha256_expected: component.sha256 || null,
      sha256_actual: sha256,
      checksum_ok: checksumOk,
      passed,
      license: component.license || null,
    });
  }

  return { checks, missingRuntime, missingModel, corrupt };
}

function deriveReadiness(checks) {
  const byId = new Map(checks.map((check) => [check.id, check]));
  const ready = (...ids) => ids.every((id) => byId.get(id)?.passed);
  const kokoroEnReady = ready('kokoro_cli', 'kokoro_en_model', 'kokoro_en_voices');
  const piperEnReady = ready('piper_cli', 'piper_en_model', 'piper_en_config');
  const piperEnMaleReady = ready('piper_cli', 'piper_en_male_model', 'piper_en_male_config');
  return {
    tts_en_ready: kokoroEnReady || piperEnReady,
    tts_en_engine: kokoroEnReady ? 'kokoro_onnx_cpu' : piperEnReady ? 'piper_onnx_cpu' : null,
    tts_kokoro_en_ready: kokoroEnReady,
    tts_piper_en_ready: piperEnReady,
    tts_piper_en_male_ready: piperEnMaleReady,
    tts_nl_ready: ready('piper_cli', 'piper_nl_model', 'piper_nl_config'),
    stt_ready: ready('whisper_cli', 'whisper_base_en'),
    vad_ready: ready('silero_vad'),
  };
}

function readHealth() {
  return readJson(healthPath(), null);
}

function writeHealth(data) {
  try {
    writeJson(healthPath(), data);
    return true;
  } catch (err) {
    return false;
  }
}

function statusFromInspection(rootInfo, manifest, manifestError, inspection, health) {
  if (manifestError === 'bundle_missing' || manifestError === 'manifest_missing') return 'bundle_missing';
  if (!manifest) return 'bundle_corrupt';
  if (inspection.corrupt || health?.ok === false && health?.state === 'bundle_corrupt') return 'bundle_corrupt';
  if (inspection.missingRuntime) return 'runtime_missing';
  if (inspection.missingModel) return 'model_missing';
  if (health?.ok && health?.bundle_id === manifest.bundle_id && health?.root === rootInfo.root) return 'ready';
  return 'starting';
}

async function getStatus(options = {}) {
  const rootInfo = locateRoot();
  const { manifest, error } = loadManifest(rootInfo.root);
  const inspection = manifest
    ? inspectComponents(rootInfo.root, manifest, { verifyHashes: Boolean(options.verifyHashes) })
    : { checks: [], missingRuntime: false, missingModel: false, corrupt: false };
  const health = readHealth();
  const state = statusFromInspection(rootInfo, manifest, error, inspection, health);
  const readiness = deriveReadiness(inspection.checks);
  const defaultVoiceReady = state === 'ready' && readiness.tts_en_ready && readiness.tts_nl_ready;
  return {
    provider: 'voice_core_local',
    state,
    install_mode: 'bundled',
    requires_installation: false,
    requires_network: false,
    requires_gpu: false,
    device: 'cpu',
    platform: PLATFORM,
    source_root: SOURCE_ROOT,
    install_root: INSTALL_ROOT,
    active_root: rootInfo.root,
    root_source: rootInfo.source,
    manifest_path: manifestPath(rootInfo.root),
    manifest_ready: Boolean(manifest),
    manifest_error: error,
    bundle_id: manifest?.bundle_id || null,
    default_voice_ready: defaultVoiceReady,
    active_voice: manifest?.default_voice || DEFAULT_MANIFEST.default_voice,
    supported_languages: ['en', 'nl'],
    supported_emotions: SUPPORTED_EMOTIONS.slice(),
    model_capabilities: {
      en: {
        engine: readiness.tts_en_engine || 'piper_onnx_cpu',
        voice: manifest?.default_voice?.voice || 'female',
        model_voice: manifest?.default_voice?.model_voice || 'en_US-lessac-high',
        alternate_voice: manifest?.default_voice?.alternate_voice || 'male',
        voices: {
          female: {
            ready: readiness.tts_piper_en_ready,
            model_voice: 'en_US-lessac-high',
            gender: 'female',
          },
          male: {
            ready: readiness.tts_piper_en_male_ready,
            model_voice: 'en_US-ryan-high',
            gender: 'male',
          },
        },
        expressive: readiness.tts_kokoro_en_ready,
        emotion_mode: readiness.tts_kokoro_en_ready ? 'model_style' : 'prosody_planner',
      },
      nl: {
        engine: 'piper_onnx_cpu',
        voice: 'nl_NL-mls-medium',
        expressive: false,
        emotion_mode: 'prosody_planner',
      },
    },
    ...readiness,
    cpu_threads: Number(process.env.VOICE_CORE_THREADS) || DEFAULT_THREADS,
    ttfa_ms: health?.ttfa_ms ?? null,
    rtf: health?.rtf ?? null,
    cache_items: cache.size,
    cache_bytes: cacheBytes,
    checks: inspection.checks,
    runtime_health: health,
    fallback_reason: state === 'ready' ? null : recommendationForState(state),
    recommendation: recommendationForState(state),
  };
}

function recommendationForState(state) {
  if (state === 'ready') return 'Default Human Voice is ready. No voice training, GPU, or manual installation is required.';
  if (state === 'bundle_missing') return `Packaged voice-core bundle is missing. Expected manifest at ${manifestPath(SOURCE_ROOT)} or ${manifestPath(INSTALL_ROOT)}.`;
  if (state === 'bundle_corrupt') return 'Packaged voice-core bundle failed verification. Rebuild or repair the release bundle.';
  if (state === 'runtime_missing') return 'Packaged voice-core runtime files are missing or not executable.';
  if (state === 'model_missing') return 'Packaged default voice/STT/VAD model files are missing.';
  if (state === 'starting') return 'Run bundled voice verification once before treating the default voice as ready.';
  return 'Default voice bundle is not ready.';
}

function shouldCopyBundleToInstall() {
  const sourceManifestPath = manifestPath(SOURCE_ROOT);
  const installManifestPath = manifestPath(INSTALL_ROOT);
  if (!exists(sourceManifestPath)) return false;
  if (!exists(installManifestPath)) return true;

  const sourceManifest = readJson(sourceManifestPath, null);
  if (!sourceManifest) return false;
  const sourceComponents = Array.isArray(sourceManifest.components) ? sourceManifest.components : [];
  for (const component of sourceComponents) {
    if (!component?.path) continue;
    const sourcePath = safeResolve(SOURCE_ROOT, component.path);
    const installPath = safeResolve(INSTALL_ROOT, component.path);
    if (!exists(sourcePath)) continue;
    if (!exists(installPath)) return true;
    if (component.sha256 && sha256FileSync(installPath) !== component.sha256) return true;
  }

  return false;
}

function copyBundleToInstall() {
  if (SOURCE_ROOT === INSTALL_ROOT || !exists(manifestPath(SOURCE_ROOT))) return false;
  if (!shouldCopyBundleToInstall()) return false;
  ensureDir(INSTALL_ROOT);
  fs.cpSync(SOURCE_ROOT, INSTALL_ROOT, { recursive: true, force: true, errorOnExist: false });
  return true;
}

async function verifyBundle(options = {}) {
  const copied = options.install !== false ? copyBundleToInstall() : false;
  const rootInfo = locateRoot();
  const { manifest, error } = loadManifest(rootInfo.root);
  if (!manifest) {
    const healthWritten = writeHealth({ ok: false, state: 'bundle_missing', root: rootInfo.root, checked_at: new Date().toISOString() });
    return { ok: false, copied, health_written: healthWritten, status: await getStatus({ verifyHashes: false }), checks: [] };
  }
  const inspection = inspectComponents(rootInfo.root, manifest, { verifyHashes: true });
  const state = statusFromInspection(rootInfo, manifest, error, inspection, { ok: false });
  const ok = state === 'starting';
  const healthWritten = writeHealth({
    ok,
    state: ok ? 'verified' : state,
    bundle_id: manifest.bundle_id,
    root: rootInfo.root,
    checked_at: new Date().toISOString(),
    failed: inspection.checks.filter((check) => !check.passed && check.required),
  });
  return {
    ok,
    copied,
    health_written: healthWritten,
    state: ok ? 'verified' : state,
    status: await getStatus({ verifyHashes: false }),
    checks: inspection.checks,
  };
}

function detectLanguage(text, explicit) {
  const normalized = String(explicit || '').slice(0, 2).toLowerCase();
  if (normalized === 'nl' || normalized === 'en') return normalized;
  const value = ` ${String(text || '').toLowerCase()} `;
  const hits = [' de ', ' het ', ' een ', ' niet ', ' hoe ', ' kunnen ', ' systeem ', ' stem ', ' waarom ', ' aanpakken ', ' klaar ']
    .filter((word) => value.includes(word)).length;
  return hits >= 2 ? 'nl' : 'en';
}

function estimateWavDurationMs(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 44 || buffer.toString('ascii', 0, 4) !== 'RIFF') return null;
  let offset = 12;
  let byteRate = 0;
  let dataSize = 0;
  while (offset + 8 <= buffer.length) {
    const id = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (id === 'fmt ') byteRate = buffer.readUInt32LE(start + 8);
    if (id === 'data') {
      dataSize = Math.min(size, buffer.length - start);
      break;
    }
    offset = start + size + (size % 2);
  }
  return byteRate && dataSize ? Math.round((dataSize / byteRate) * 1000) : null;
}

function cacheKey(text, options, language, voice) {
  const planned = options.speech_plan || {};
  return crypto.createHash('sha256')
    .update(JSON.stringify({
      provider: 'voice_core_local',
      text,
      language,
      voice,
      emotion: planned.emotion || options.emotion || null,
      intensity: planned.emotion_intensity ?? options.emotion_intensity ?? null,
      speed: planned.speaking_rate ?? options.speaking_rate ?? options.speed ?? null,
      warmth: planned.warmth ?? options.warmth ?? options.persona?.warmth ?? null,
      energy: planned.energy ?? options.energy ?? options.persona?.energy ?? null,
    }))
    .digest('hex');
}

function normalizeGender(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (['male', 'masculine', 'man'].includes(normalized)) return 'male';
  if (['female', 'feminine', 'woman'].includes(normalized)) return 'female';
  return 'female';
}

function selectEnglishPiperVoice(options = {}, components, root) {
  const requested = String(options.voice || options.persona?.voice || '').trim().toLowerCase();
  const gender = normalizeGender(
    requested === 'male' || requested === 'female'
      ? requested
      : options.gender || options.persona?.gender || options.voice_gender || options.persona?.voice_gender,
  );
  const requestedMale = gender === 'male';
  const maleModel = components.get('piper_en_male_model');
  const maleConfig = components.get('piper_en_male_config');
  const maleReady = requestedMale && maleModel && maleConfig &&
    exists(safeResolve(root, maleModel.path)) &&
    exists(safeResolve(root, maleConfig.path));
  if (maleReady) {
    return {
      gender: 'male',
      voiceName: 'en_US-ryan-high',
      modelId: 'piper_en_male_model',
      configId: 'piper_en_male_config',
      fallback: null,
    };
  }
  return {
    gender: requestedMale ? 'female' : 'female',
    requested_gender: requestedMale ? 'male' : gender,
    voiceName: 'en_US-lessac-high',
    modelId: 'piper_en_model',
    configId: 'piper_en_config',
    fallback: requestedMale ? 'male_voice_missing_using_female' : null,
  };
}

function getCached(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  cache.delete(key);
  cache.set(key, entry);
  return { ...entry, audioBuf: Buffer.from(entry.audioBuf) };
}

function putCached(key, entry) {
  const size = entry.audioBuf.length;
  cache.set(key, { ...entry, audioBuf: Buffer.from(entry.audioBuf), size });
  cacheBytes += size;
  while (cache.size > CACHE_MAX_ITEMS || cacheBytes > CACHE_MAX_BYTES) {
    const [oldKey, oldEntry] = cache.entries().next().value || [];
    if (!oldKey) break;
    cacheBytes -= oldEntry?.size || 0;
    cache.delete(oldKey);
  }
}

function componentPath(root, manifest, id) {
  const component = componentMap(manifest).get(id);
  if (!component) throw new Error(`Voice core component missing from manifest: ${id}`);
  return safeResolve(root, component.path);
}

function runCli(binary, args, input, options = {}) {
  const libDirs = [
    path.dirname(binary),
    path.join(path.dirname(binary), '..', 'lib'),
    path.join(path.dirname(binary), '..', 'src'),
    path.join(path.dirname(binary), '..', 'ggml', 'src'),
    path.join(path.dirname(binary), '..', 'ggml', 'src', 'cpu'),
    path.join(path.dirname(binary), '..', '..', 'lib'),
    path.join(path.dirname(binary), '..', '..', 'src'),
    path.join(path.dirname(binary), '..', '..', 'ggml', 'src'),
    path.join(path.dirname(binary), '..', '..', 'ggml', 'src', 'cpu'),
  ].map((dir) => path.resolve(dir)).filter(exists);
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        LD_LIBRARY_PATH: [process.env.LD_LIBRARY_PATH, ...libDirs].filter(Boolean).join(path.delimiter),
        OMP_NUM_THREADS: String(options.threads || DEFAULT_THREADS),
        ORT_NUM_THREADS: String(options.threads || DEFAULT_THREADS),
      },
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      try { child.kill('SIGTERM'); } catch (_err) { /* ignore */ }
      reject(new Error('Voice core synthesis timeout'));
    }, Number(options.timeoutMs || 30000));
    child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.once('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.once('exit', (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(`Voice core runtime exited with code ${code}: ${stderr || stdout}`));
      resolve({ stdout, stderr });
    });
    child.stdin.end(input);
  });
}

async function synthesize(text, options = {}) {
  const planned = planSpeech(text, options);
  if (!planned.text) throw new Error('text is required');
  const language = detectLanguage(planned.text, options.language || options.persona?.language);
  const status = await getStatus();
  if (status.state !== 'ready') throw new Error(`Default Human Voice bundle is ${status.state}: ${status.recommendation}`);
  const rootInfo = locateRoot();
  const { manifest } = loadManifest(rootInfo.root);
  const components = componentMap(manifest);
  const hasKokoro = ['kokoro_cli', 'kokoro_en_model', 'kokoro_en_voices']
    .every((id) => {
      const component = components.get(id);
      if (!component) return false;
      const filePath = safeResolve(rootInfo.root, component.path);
      return component.executable ? isExecutable(filePath) : exists(filePath);
    });
  const enVoice = selectEnglishPiperVoice(options, components, rootInfo.root);
  const voiceName = language === 'en'
    ? (hasKokoro && options.voice && options.voice !== 'default' ? options.voice : enVoice.voiceName)
    : 'nl_NL-mls-medium';
  const key = cacheKey(planned.text, { ...options, speech_plan: planned }, language, voiceName);
  const cached = getCached(key);
  if (cached) return { ...cached, meta: { ...cached.meta, cached: true } };

  const out = path.join(os.tmpdir(), `voice-core-${Date.now()}-${crypto.randomUUID()}.wav`);
  const threads = Math.max(1, Math.min(8, Number(options.threads || process.env.VOICE_CORE_THREADS || DEFAULT_THREADS)));
  const started = Date.now();
  if (language === 'nl' || !hasKokoro) {
    const piper = componentPath(rootInfo.root, manifest, 'piper_cli');
    const model = componentPath(rootInfo.root, manifest, language === 'nl' ? 'piper_nl_model' : enVoice.modelId);
    const config = componentPath(rootInfo.root, manifest, language === 'nl' ? 'piper_nl_config' : enVoice.configId);
    const lengthScale = Math.max(0.75, Math.min(1.25, 1 / planned.speaking_rate));
    await runCli(piper, [
      '--model', model,
      '--config', config,
      '--output_file', out,
      '--length_scale', String(lengthScale),
    ], planned.text, { threads, timeoutMs: options.timeoutMs });
  } else {
    const kokoro = componentPath(rootInfo.root, manifest, 'kokoro_cli');
    const model = componentPath(rootInfo.root, manifest, 'kokoro_en_model');
    const voices = componentPath(rootInfo.root, manifest, 'kokoro_en_voices');
    await runCli(kokoro, [
      '--model', model,
      '--voices', voices,
      '--voice', voiceName,
      '--lang', 'en-us',
      '--output', out,
      '--speed', String(planned.speaking_rate),
      '--emotion', planned.emotion,
      '--emotion-intensity', String(planned.emotion_intensity),
    ], planned.text, { threads, timeoutMs: options.timeoutMs });
  }

  const audioBuf = fs.readFileSync(out);
  try { fs.unlinkSync(out); } catch (_err) { /* ignore */ }
  if (!audioBuf || audioBuf.length < 44) throw new Error('Default Human Voice returned invalid WAV audio.');
  const elapsedMs = Date.now() - started;
  const durationMs = estimateWavDurationMs(audioBuf);
  const meta = {
    provider: 'voice_core_local',
    engine: language === 'en' && hasKokoro ? 'kokoro_onnx_cpu' : 'piper_onnx_cpu',
    language,
    voice: voiceName,
    gender: language === 'en' ? enVoice.gender : 'default',
    requested_gender: language === 'en' ? enVoice.requested_gender || enVoice.gender : null,
    voice_fallback: language === 'en' ? enVoice.fallback : null,
    model: language === 'en' && hasKokoro
      ? componentPath(rootInfo.root, manifest, 'kokoro_en_model')
      : componentPath(rootInfo.root, manifest, language === 'nl' ? 'piper_nl_model' : enVoice.modelId),
    elapsed_ms: elapsedMs,
    duration_ms: durationMs,
    ttfa_ms: elapsedMs,
    rtf: durationMs ? Number((elapsedMs / durationMs).toFixed(3)) : null,
    cpu_threads: threads,
    cached: false,
    speech_plan: planned,
  };
  putCached(key, { audioBuf, meta });
  return { audioBuf, meta };
}

async function prewarm(options = {}) {
  const verify = await verifyBundle({ install: options.install !== false });
  if (!verify.ok) return { ok: false, state: verify.state, message: recommendationForState(verify.state), verify };
  const result = await synthesize(options.text || 'Default human voice ready.', {
    language: 'en',
    voice: 'female',
    gender: 'female',
    emotion: 'warm_confident',
    timeoutMs: options.timeoutMs || 20000,
  });
  const rootInfo = locateRoot();
  const { manifest } = loadManifest(rootInfo.root);
  const healthWritten = writeHealth({
    ok: true,
    state: 'ready',
    bundle_id: manifest.bundle_id,
    root: rootInfo.root,
    checked_at: new Date().toISOString(),
    ttfa_ms: result.meta?.ttfa_ms ?? null,
    rtf: result.meta?.rtf ?? null,
    voice: result.meta?.voice || null,
  });
  return { ok: true, state: 'ready', health_written: healthWritten, meta: result.meta, status: await getStatus() };
}

function artifactName() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return `voice_core_${stamp}.wav`;
}

function saveArtifact(audioBuf, options = {}) {
  const dir = path.resolve(options.artifactDir || ARTIFACT_ROOT);
  ensureDir(dir);
  const name = artifactName();
  const filePath = path.join(dir, name);
  fs.writeFileSync(filePath, audioBuf);
  return {
    id: `voice:${name}`,
    name,
    type: 'audio',
    source: 'voice_core_local',
    path: filePath,
    url: `/api/artifacts/${encodeURIComponent(name)}`,
    size: audioBuf.length,
    created_at: new Date().toISOString(),
  };
}

function sampleFiles() {
  const rootInfo = locateRoot();
  const { manifest } = loadManifest(rootInfo.root);
  return (manifest?.samples || []).map((sample) => {
    const filePath = safeResolve(rootInfo.root, sample.path);
    return {
      ...sample,
      path: filePath,
      exists: exists(filePath),
      url: `/api/voice/bundle/samples/${encodeURIComponent(sample.id)}`,
    };
  });
}

function sampleFile(sampleId) {
  const sample = sampleFiles().find((item) => item.id === sampleId);
  if (!sample || !sample.exists) return null;
  return sample;
}

async function benchmark(options = {}) {
  const phrases = [
    { id: 'en_warm', language: 'en', emotion: 'warm_confident', text: options.text_en || 'System ready. I can speak with a natural local default voice.' },
    { id: 'en_focused', language: 'en', emotion: 'focused', text: 'I found the blocker and I can explain the fix clearly.' },
    { id: 'nl_calm', language: 'nl', emotion: 'calm', text: options.text_nl || 'Systeem klaar. Ik kan lokaal spreken met een standaardstem.' },
  ];
  const results = [];
  for (const phrase of phrases) {
    const started = Date.now();
    try {
      const result = await synthesize(phrase.text, {
        language: phrase.language,
        emotion: phrase.emotion,
        timeoutMs: options.timeoutMs || 20000,
      });
      results.push({ ...phrase, ok: true, elapsed_ms: Date.now() - started, meta: result.meta });
    } catch (err) {
      results.push({ ...phrase, ok: false, elapsed_ms: Date.now() - started, error: String(err.message || err) });
    }
  }
  const passed = results.filter((item) => item.ok);
  return {
    ok: results.every((item) => item.ok),
    provider: 'voice_core_local',
    results,
    average_rtf: passed.length
      ? Number((passed.reduce((sum, item) => sum + (item.meta?.rtf || 0), 0) / passed.length).toFixed(3))
      : null,
    average_ttfa_ms: passed.length
      ? Math.round(passed.reduce((sum, item) => sum + (item.meta?.ttfa_ms || 0), 0) / passed.length)
      : null,
  };
}

module.exports = {
  AI_HOME,
  SOURCE_ROOT,
  INSTALL_ROOT,
  DEFAULT_MANIFEST,
  SUPPORTED_EMOTIONS,
  getStatus,
  verifyBundle,
  prewarm,
  synthesize,
  saveArtifact,
  sampleFiles,
  sampleFile,
  benchmark,
  planSpeech,
  detectLanguage,
};
