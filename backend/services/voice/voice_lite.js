'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const https = require('https');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');
const { planSpeech } = require('./speech_planner');

const REPO_ROOT = path.resolve(__dirname, '../../..');
const AI_HOME = path.resolve(
  process.env.AI_HOME ||
  process.env.AI_EMPLOYEE_HOME ||
  path.join(os.homedir(), '.ai-employee')
);

const VOICE_LITE_ROOT = path.join(AI_HOME, 'models', 'voice', 'voice-lite');
const VOICE_LITE_STATE_ROOT = path.join(AI_HOME, 'state', 'voice');
const VOICE_LITE_RUNTIME_ROOT = path.join(AI_HOME, 'runtimes', 'voice', 'piper');
const DEFAULT_ARTIFACT_DIR = path.join(REPO_ROOT, 'state', 'artifacts');
const PIPER_REPO = process.env.VOICE_LITE_PIPER_REPO || 'rhasspy/piper-voices';
const PIPER_REVISION = process.env.VOICE_LITE_PIPER_REVISION || 'main';
const PIPER_RUNTIME = {
  component: 'voice_lite_runtime',
  label: 'Piper Linux x86_64 CPU runtime',
  version: process.env.VOICE_LITE_PIPER_RUNTIME_VERSION || '2023.11.14-2',
  asset: process.env.VOICE_LITE_PIPER_RUNTIME_ASSET || 'piper_linux_x86_64.tar.gz',
  url: process.env.VOICE_LITE_PIPER_RUNTIME_URL || null,
  sha256: process.env.VOICE_LITE_PIPER_RUNTIME_SHA256 || null,
  source: 'https://github.com/rhasspy/piper',
  license: 'MIT',
  min_free_bytes: 512 * 1024 * 1024,
};
const MISO_ONE = {
  component: 'voice_lite_miso_one',
  id: 'miso_one',
  label: 'Miso One / MisoTTS 8B foundation voice model',
  repo: 'MisoLabs/MisoTTS',
  revision: 'main',
  language: 'en',
  size_bytes: 32.8 * 1024 * 1024 * 1024,
  license: 'Modified MIT; attribution required above stated commercial scale thresholds.',
  source: 'https://huggingface.co/MisoLabs/MisoTTS',
  github: 'https://github.com/MisoLabsAI/MisoTTS',
  dir: path.join(VOICE_LITE_ROOT, 'foundation', 'miso-one'),
  files: ['model.safetensors', 'LICENSE', 'README.md'],
};
const CACHE_MAX_ITEMS = Math.max(8, Number(process.env.VOICE_LITE_CACHE_ITEMS) || 64);
const CACHE_MAX_BYTES = Math.max(4 * 1024 * 1024, Number(process.env.VOICE_LITE_CACHE_BYTES) || 48 * 1024 * 1024);
const DEFAULT_THREADS = Math.max(2, Math.min(4, Math.floor((os.cpus()?.length || 4) / 3) || 2));

const RUNTIME_CANDIDATES = [
  process.env.VOICE_LITE_PIPER_BIN,
  process.env.PIPER_BIN,
  path.join(VOICE_LITE_RUNTIME_ROOT, 'piper'),
  path.join(AI_HOME, 'runtimes', 'voice', 'piper', 'piper'),
  path.join(REPO_ROOT, 'runtime', 'vendor', 'piper', 'piper'),
  '/usr/local/bin/piper',
  '/usr/bin/piper',
].filter(Boolean);

const MODEL_SLOTS = {
  base_en: {
    id: 'voice_lite_base_en',
    language: 'en',
    tier: 'base',
    dir: path.join(VOICE_LITE_ROOT, 'base', 'en'),
    model: path.join(VOICE_LITE_ROOT, 'base', 'en', 'model.onnx'),
    config: path.join(VOICE_LITE_ROOT, 'base', 'en', 'model.onnx.json'),
    preferred: [/en_US\/amy\/medium\/en_US-amy-medium\.onnx$/i, /en_US\/lessac\/medium\/en_US-lessac-medium\.onnx$/i, /en_US\/.*\/medium\/.*\.onnx$/i, /en\/.*\.onnx$/i],
    label: 'Voice Lite base English Piper voice',
  },
  base_nl: {
    id: 'voice_lite_base_nl',
    language: 'nl',
    tier: 'base',
    dir: path.join(VOICE_LITE_ROOT, 'base', 'nl'),
    model: path.join(VOICE_LITE_ROOT, 'base', 'nl', 'model.onnx'),
    config: path.join(VOICE_LITE_ROOT, 'base', 'nl', 'model.onnx.json'),
    preferred: [/nl_NL\/mls\/medium\/nl_NL-mls-medium\.onnx$/i, /nl_NL\/.*\/medium\/.*\.onnx$/i, /nl\/.*\.onnx$/i],
    label: 'Voice Lite base Dutch Piper voice',
  },
  custom_en: {
    id: 'voice_lite_custom_en',
    language: 'en',
    tier: 'custom',
    dir: path.join(VOICE_LITE_ROOT, 'custom', 'en'),
    model: path.join(VOICE_LITE_ROOT, 'custom', 'en', 'teammate_en.onnx'),
    config: path.join(VOICE_LITE_ROOT, 'custom', 'en', 'teammate_en.onnx.json'),
    label: 'Voice Lite custom teammate English voice',
  },
  custom_nl: {
    id: 'voice_lite_custom_nl',
    language: 'nl',
    tier: 'custom',
    dir: path.join(VOICE_LITE_ROOT, 'custom', 'nl'),
    model: path.join(VOICE_LITE_ROOT, 'custom', 'nl', 'teammate_nl.onnx'),
    config: path.join(VOICE_LITE_ROOT, 'custom', 'nl', 'teammate_nl.onnx.json'),
    label: 'Voice Lite custom teammate Dutch voice',
  },
};

const downloadState = { current: null };
const chunkCache = new Map();
let cacheBytes = 0;
let activeConfig = null;
let activeDownload = null;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function exists(filePath) {
  try { return fs.existsSync(filePath); } catch (_err) { return false; }
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

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${value} B`;
}

function isExecutable(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return fs.statSync(filePath).isFile();
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

function findRuntime() {
  for (const candidate of RUNTIME_CANDIDATES) {
    if (candidate && candidate.includes(path.sep) && isExecutable(candidate)) {
      return { binary: candidate, source: candidate.startsWith(AI_HOME) ? 'app_home' : candidate.startsWith(REPO_ROOT) ? 'bundled' : 'system' };
    }
  }
  const binary = commandPath('piper');
  return binary ? { binary, source: 'system_path' } : { binary: null, source: null };
}

function modelReady(slot) {
  return exists(slot.model) && exists(slot.config);
}

function readJson(filePath, fallback = null) {
  try { return JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch (_err) { return fallback; }
}

function writeJson(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

function healthPath() {
  return path.join(VOICE_LITE_STATE_ROOT, 'voice_lite_health.json');
}

function runtimeManifestPath() {
  return path.join(VOICE_LITE_RUNTIME_ROOT, 'manifest.json');
}

function readHealth() {
  return readJson(healthPath(), null);
}

function writeHealth(data) {
  writeJson(healthPath(), {
    schema: 1,
    checked_at: new Date().toISOString(),
    ...data,
  });
}

function invalidateHealth(reason) {
  writeHealth({
    ok: false,
    state: 'starting',
    reason,
  });
}

function runtimeDownloadUrl() {
  return PIPER_RUNTIME.url ||
    `https://github.com/rhasspy/piper/releases/download/${encodeURIComponent(PIPER_RUNTIME.version)}/${encodeURIComponent(PIPER_RUNTIME.asset)}`;
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
  downloadState.current = null;
  return { ok: true, cancelled: true, component: activeDownload.component };
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

function downloadFile(url, dest, emit, component, label, token = null) {
  return new Promise((resolve, reject) => {
    ensureDir(path.dirname(dest));
    const tmp = `${dest}.download`;
    token?.tempFiles?.add(tmp);
    assertNotCancelled(token);
    const request = https.get(url, (response) => {
      try {
        assertNotCancelled(token);
      } catch (err) {
        response.resume();
        return reject(err);
      }
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume();
        const redirect = new URL(response.headers.location, url).toString();
        return resolve(downloadFile(redirect, dest, emit, component, label, token));
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
        emit?.({
          type: 'download.progress',
          component,
          state: 'downloading',
          bytes_received: received,
          total_bytes: total || null,
          percent: total ? Math.round((received / total) * 100) : null,
          message: label,
        });
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
      reject(token?.cancelled ? new Error(`${component} download cancelled.`) : err);
    });
    request.on('close', () => token?.requests?.delete(request));
  });
}

async function fetchHfSiblings(repo = PIPER_REPO, revision = PIPER_REVISION) {
  const url = `https://huggingface.co/api/models/${repo}?revision=${encodeURIComponent(revision)}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Piper model metadata HTTP ${response.status}`);
  const data = await response.json();
  return (data.siblings || [])
    .map((item) => item.rfilename)
    .filter(Boolean);
}

function choosePiperVoice(slot, siblings) {
  const voices = siblings.filter((name) => String(name || '').endsWith('.onnx'));
  for (const pattern of slot.preferred || []) {
    const match = voices.find((name) => pattern.test(name));
    if (match) return match;
  }
  const lang = slot.language === 'nl' ? /(^|\/)nl(_NL)?\//i : /(^|\/)en(_US|_GB)?\//i;
  return voices.find((name) => lang.test(name) && /medium/i.test(name)) ||
    voices.find((name) => lang.test(name)) ||
    null;
}

function resolveUrl(repo, revision, rfilename) {
  const encoded = rfilename.split('/').map(encodeURIComponent).join('/');
  return `https://huggingface.co/${repo}/resolve/${revision}/${encoded}`;
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

async function downloadBaseModel(slotName, emit = () => {}, token = null) {
  const slot = MODEL_SLOTS[slotName];
  if (!slot || slot.tier !== 'base') throw new Error(`Unknown Voice Lite base model: ${slotName}`);
  const component = slot.id;
  downloadState.current = { component, state: 'downloading', percent: 0 };
  invalidateHealth(`${component} download started`);
  assertFreeSpace(slot.dir, 512 * 1024 * 1024, slot.label);
  emit({ type: 'download.started', component, state: 'downloading', percent: 0, message: `Reading ${PIPER_REPO} file list` });
  assertNotCancelled(token);
  const siblings = await fetchHfSiblings();
  const selected = choosePiperVoice(slot, siblings);
  if (!selected) throw new Error(`No Piper ${slot.language.toUpperCase()} ONNX voice found in ${PIPER_REPO}.`);
  const configName = `${selected}.json`;
  const configExists = siblings.includes(configName);
  if (!configExists) throw new Error(`Piper config file missing in ${PIPER_REPO}: ${configName}`);
  const modelUrl = resolveUrl(PIPER_REPO, PIPER_REVISION, selected);
  const configUrl = resolveUrl(PIPER_REPO, PIPER_REVISION, configName);
  ensureDir(slot.dir);
  await downloadFile(modelUrl, slot.model, emit, component, `Downloading ${path.basename(selected)}`, token);
  await downloadFile(configUrl, slot.config, emit, component, `Downloading ${path.basename(configName)}`, token);
  const modelSha = await sha256File(slot.model);
  const configSha = await sha256File(slot.config);
  writeJson(path.join(slot.dir, 'manifest.json'), {
    schema: 1,
    component,
    provider: 'voice_lite',
    engine: 'piper_onnx_cpu',
    language: slot.language,
    tier: slot.tier,
    source: `https://huggingface.co/${PIPER_REPO}`,
    repo: PIPER_REPO,
    revision: PIPER_REVISION,
    selected_file: selected,
    license: 'Piper voice model license varies per voice; verify manifest/source before redistribution.',
    files: [
      { file: path.basename(slot.model), sha256: modelSha, size: fs.statSync(slot.model).size },
      { file: path.basename(slot.config), sha256: configSha, size: fs.statSync(slot.config).size },
    ],
    downloaded_at: new Date().toISOString(),
    config_found: configExists,
  });
  downloadState.current = null;
  emit({ type: 'download.complete', component, state: 'ready', percent: 100, message: `${slot.label} ready` });
  return { ok: true, component, selected_file: selected };
}

function misoOneStatus() {
  const modelPath = path.join(MISO_ONE.dir, 'model.safetensors');
  const manifest = readJson(path.join(MISO_ONE.dir, 'manifest.json'), null);
  const modelReady = exists(modelPath);
  return {
    id: MISO_ONE.id,
    label: MISO_ONE.label,
    provider: 'miso_labs',
    state: modelReady ? 'ready' : 'model_missing',
    role: 'custom_voice_foundation_base',
    model_ready: modelReady,
    model_path: modelPath,
    model_root: MISO_ONE.dir,
    repo: MISO_ONE.repo,
    revision: MISO_ONE.revision,
    source: MISO_ONE.source,
    github: MISO_ONE.github,
    size_bytes: MISO_ONE.size_bytes,
    license: MISO_ONE.license,
    language_support: ['en'],
    live_cpu_runtime: false,
    recommended_for_cpu_runtime: false,
    runtime_note: 'Miso One is an 8B PyTorch/Safetensors foundation model. Voice Lite still uses Piper/ONNX for live CPU synthesis.',
    manifest,
  };
}

async function downloadMisoOne(emit = () => {}, token = null) {
  const component = MISO_ONE.component;
  downloadState.current = { component, state: 'downloading', percent: 0 };
  assertFreeSpace(MISO_ONE.dir, 45 * 1024 * 1024 * 1024, MISO_ONE.label);
  emit({
    type: 'download.started',
    component,
    state: 'downloading',
    percent: 0,
    message: `Preparing ${MISO_ONE.label}. This is a large ${Math.round(MISO_ONE.size_bytes / 1024 / 1024 / 1024)}GB download.`,
  });

  const apiUrl = `https://huggingface.co/api/models/${MISO_ONE.repo}?revision=${encodeURIComponent(MISO_ONE.revision)}`;
  assertNotCancelled(token);
  const response = await fetch(apiUrl);
  if (!response.ok) throw new Error(`Miso One model metadata HTTP ${response.status}`);
  const data = await response.json();
  const siblings = (data.siblings || []).map((item) => item.rfilename).filter(Boolean);
  const selected = MISO_ONE.files.filter((name) => siblings.includes(name));
  if (!selected.includes('model.safetensors')) throw new Error('Miso One model.safetensors was not found in the Hugging Face repository.');

  ensureDir(MISO_ONE.dir);
  const files = [];
  for (let index = 0; index < selected.length; index += 1) {
    const name = selected[index];
    const url = resolveUrl(MISO_ONE.repo, MISO_ONE.revision, name);
    const dest = safeModelPath(MISO_ONE.dir, name);
    emit({
      type: 'download.progress',
      component,
      state: 'downloading',
      percent: Math.round((index / selected.length) * 100),
      message: `Downloading ${name}`,
    });
    await downloadFile(url, dest, (progress) => {
      const filePercent = Number.isFinite(progress.percent) ? progress.percent : 0;
      const percent = Math.min(99, Math.round(((index + filePercent / 100) / selected.length) * 100));
      emit({
        ...progress,
        type: 'download.progress',
        component,
        state: 'downloading',
        percent,
        message: `Downloading ${name}`,
      });
    }, component, `Downloading ${name}`, token);
    files.push({ file: name, size: fs.statSync(dest).size, sha256: await sha256File(dest) });
  }

  writeJson(path.join(MISO_ONE.dir, 'manifest.json'), {
    schema: 1,
    component,
    id: MISO_ONE.id,
    provider: 'miso_labs',
    role: 'custom_voice_foundation_base',
    repo: MISO_ONE.repo,
    revision: MISO_ONE.revision,
    source: MISO_ONE.source,
    github: MISO_ONE.github,
    license: MISO_ONE.license,
    language_support: ['en'],
    live_cpu_runtime: false,
    files,
    downloaded_at: new Date().toISOString(),
  });
  downloadState.current = null;
  emit({ type: 'download.complete', component, state: 'ready', percent: 100, message: 'Miso One foundation base downloaded.' });
  return { ok: true, component, state: 'ready', model_path: path.join(MISO_ONE.dir, 'model.safetensors') };
}

function runtimeInstallInstructions() {
  return [
    'Voice Lite needs a Piper binary.',
    `Press Download Runtime, set VOICE_LITE_PIPER_BIN/PIPER_BIN, or place piper at ${path.join(VOICE_LITE_RUNTIME_ROOT, 'piper')}.`,
    'Model weights are downloaded separately with the EN/NL base voice buttons.',
  ].join(' ');
}

function findManagedPiperBinary() {
  const direct = [
    path.join(VOICE_LITE_RUNTIME_ROOT, 'piper'),
    path.join(VOICE_LITE_RUNTIME_ROOT, 'piper', 'piper'),
  ];
  for (const candidate of direct) {
    if (isExecutable(candidate)) return candidate;
  }
  try {
    const stack = [VOICE_LITE_RUNTIME_ROOT];
    while (stack.length) {
      const dir = stack.pop();
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory() && full.split(path.sep).length - VOICE_LITE_RUNTIME_ROOT.split(path.sep).length <= 3) {
          stack.push(full);
        } else if (entry.isFile() && entry.name === 'piper') {
          try { fs.chmodSync(full, 0o755); } catch (_err) { /* ignore */ }
          if (isExecutable(full)) return full;
        }
      }
    }
  } catch (_err) {
    // ignore
  }
  return null;
}

function extractTarGz(archivePath, targetDir) {
  const result = spawnSync('tar', ['-xzf', archivePath, '-C', targetDir], { encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`Failed to extract Piper runtime archive: ${result.stderr || result.stdout || 'tar exited non-zero'}`);
  }
}

async function downloadRuntime(emit = () => {}, token = null) {
  const component = 'voice_lite_runtime';
  const existing = findRuntime();
  if (existing.binary) {
    emit({ type: 'download.complete', component, state: 'ready', percent: 100, message: `Piper runtime already available at ${existing.binary}` });
    return { ok: true, component, state: 'ready', binary: existing.binary, already_present: true };
  }

  downloadState.current = { component, state: 'downloading', percent: 0 };
  invalidateHealth('voice_lite_runtime download started');
  const disk = assertFreeSpace(VOICE_LITE_RUNTIME_ROOT, PIPER_RUNTIME.min_free_bytes, PIPER_RUNTIME.label);
  const url = runtimeDownloadUrl();
  const archive = path.join(VOICE_LITE_RUNTIME_ROOT, PIPER_RUNTIME.asset);
  emit({ type: 'download.started', component, state: 'downloading', percent: 0, message: `Downloading ${PIPER_RUNTIME.label}` });
  await downloadFile(url, archive, emit, component, `Downloading ${PIPER_RUNTIME.asset}`, token);
  assertNotCancelled(token);

  const digest = await sha256File(archive);
  if (PIPER_RUNTIME.sha256 && digest !== PIPER_RUNTIME.sha256) {
    throw new Error(`Piper runtime checksum mismatch. Expected ${PIPER_RUNTIME.sha256}, got ${digest}.`);
  }

  emit({ type: 'download.progress', component, state: 'downloading', percent: 92, message: 'Extracting Piper runtime' });
  extractTarGz(archive, VOICE_LITE_RUNTIME_ROOT);
  const binary = findManagedPiperBinary();
  if (!binary) throw new Error(`Piper runtime archive extracted, but no executable piper binary was found under ${VOICE_LITE_RUNTIME_ROOT}.`);

  writeJson(runtimeManifestPath(), {
    schema: 1,
    component,
    provider: 'voice_lite',
    engine: 'piper_onnx_cpu',
    source: PIPER_RUNTIME.source,
    url,
    version: PIPER_RUNTIME.version,
    asset: PIPER_RUNTIME.asset,
    license: PIPER_RUNTIME.license,
    files: [
      { file: path.basename(archive), size: fs.statSync(archive).size, sha256: digest },
      { file: path.relative(VOICE_LITE_RUNTIME_ROOT, binary), role: 'executable' },
    ],
    disk,
    downloaded_at: new Date().toISOString(),
  });

  downloadState.current = null;
  activeDownload = null;
  emit({ type: 'download.complete', component, state: 'ready', percent: 100, message: `Piper runtime ready at ${binary}` });
  return {
    ok: true,
    component,
    state: 'ready',
    binary,
    manifest: runtimeManifestPath(),
  };
}

function detectLanguage(text, explicit) {
  const normalized = String(explicit || '').slice(0, 2).toLowerCase();
  if (normalized === 'nl' || normalized === 'en') return normalized;
  const value = ` ${String(text || '').toLowerCase()} `;
  if (/[ąćęłńóśźż]/i.test(value)) return 'en';
  const dutchHits = [' de ', ' het ', ' een ', ' niet ', ' wel ', ' hoe ', ' kunnen ', ' systeem ', ' stem ', ' snel ', ' licht ', ' waarom ', ' aanpakken ']
    .filter((word) => value.includes(word)).length;
  return dutchHits >= 2 ? 'nl' : 'en';
}

function normalizeVoice(value) {
  const voice = String(value || '').toLowerCase();
  if (voice.includes('custom')) return 'custom';
  if (voice.includes('base')) return 'base';
  return 'custom';
}

function selectModel({ text, language, voice }) {
  const lang = detectLanguage(text, language);
  const preference = normalizeVoice(voice);
  const candidates = preference === 'custom'
    ? [`custom_${lang}`, `base_${lang}`, lang === 'en' ? 'base_nl' : 'base_en']
    : [`base_${lang}`, `custom_${lang}`, lang === 'en' ? 'base_nl' : 'base_en'];
  const selectedKey = candidates.find((key) => modelReady(MODEL_SLOTS[key]));
  if (!selectedKey) return { language: lang, slot: null, selectedKey: null };
  return { language: lang, slot: MODEL_SLOTS[selectedKey], selectedKey };
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

function cacheKey(text, options, selectedKey) {
  const persona = options?.persona || {};
  return crypto.createHash('sha256')
    .update(JSON.stringify({
      text: String(text || '').trim(),
      selectedKey,
      language: options.language || null,
      voice: options.voice || null,
      speed: persona.speed ?? options.speed ?? 1,
      warmth: persona.warmth ?? null,
      tone: persona.tone ?? null,
      emotion: options.emotion ?? persona.emotion ?? null,
      emotion_intensity: options.emotion_intensity ?? persona.emotion_intensity ?? null,
      speaking_rate: options.speaking_rate ?? persona.speaking_rate ?? null,
      energy: options.energy ?? persona.energy ?? null,
      pause_style: options.pause_style ?? persona.pause_style ?? null,
    }))
    .digest('hex');
}

function getCached(key) {
  const entry = chunkCache.get(key);
  if (!entry) return null;
  chunkCache.delete(key);
  chunkCache.set(key, entry);
  return { ...entry, audioBuf: Buffer.from(entry.audioBuf) };
}

function putCached(key, entry) {
  const size = entry.audioBuf.length;
  chunkCache.set(key, { ...entry, audioBuf: Buffer.from(entry.audioBuf), size });
  cacheBytes += size;
  while (chunkCache.size > CACHE_MAX_ITEMS || cacheBytes > CACHE_MAX_BYTES) {
    const [oldKey, oldEntry] = chunkCache.entries().next().value || [];
    if (!oldKey) break;
    cacheBytes -= oldEntry?.size || 0;
    chunkCache.delete(oldKey);
  }
}

async function getStatus(options = {}) {
  const runtime = findRuntime();
  const baseEn = modelReady(MODEL_SLOTS.base_en);
  const baseNl = modelReady(MODEL_SLOTS.base_nl);
  const customEn = modelReady(MODEL_SLOTS.custom_en);
  const customNl = modelReady(MODEL_SLOTS.custom_nl);
  const anyModel = baseEn || baseNl || customEn || customNl;
  const health = readHealth();
  const runtimeManifest = readJson(runtimeManifestPath(), null);
  let state = 'runtime_missing';
  if (runtime.binary && anyModel) state = health?.ok ? 'ready' : 'starting';
  else if (runtime.binary && !anyModel) state = 'model_missing';
  const active = readJson(path.join(VOICE_LITE_STATE_ROOT, 'voice_lite_active.json'), {});
  const benchmark = readJson(path.join(VOICE_LITE_ROOT, 'benchmark.json'), {});
  const language = detectLanguage('', options.language || active.language || 'en');
  return {
    provider: 'voice_lite',
    state,
    runtime_ready: Boolean(runtime.binary),
    device: 'cpu',
    engine: 'piper_onnx_cpu',
    runtime,
    runtime_manifest: runtimeManifest,
    runtime_health: health,
    model_root: VOICE_LITE_ROOT,
    active_language: language,
    active_voice: active.voice || (language === 'nl' ? 'base_nl' : 'base_en'),
    foundation_model: active.foundation_model || 'miso_one',
    miso_one: misoOneStatus(),
    custom_en_ready: customEn,
    custom_nl_ready: customNl,
    base_en_ready: baseEn,
    base_nl_ready: baseNl,
    cpu_threads: Number(process.env.VOICE_LITE_THREADS) || DEFAULT_THREADS,
    ram_mb: benchmark.ram_mb || null,
    rtf: benchmark.rtf || null,
    ttfa_ms: benchmark.ttfa_ms || null,
    cache_items: chunkCache.size,
    cache_bytes: cacheBytes,
    downloading: downloadState.current,
    recommendation: runtime.binary
      ? anyModel
        ? health?.ok
          ? 'Voice Lite CPU is ready. Miso One is selected as the custom voice foundation base; live synthesis still uses Piper/ONNX.'
          : 'Run Start CPU or Voice Self-Test to prove Piper can synthesize with the installed EN/NL model before treating Voice Lite as ready.'
        : 'Download Voice Lite base EN and NL models. Miso One can be downloaded separately as the custom voice foundation base.'
      : runtimeInstallInstructions(),
  };
}

async function prewarm() {
  const runtime = findRuntime();
  if (!runtime.binary) {
    const status = await getStatus();
    return { ok: false, state: status.state, message: status.recommendation };
  }
  const selection = selectModel({ text: 'Voice Lite ready.', language: 'en', voice: 'base' });
  if (!selection.slot) {
    const status = await getStatus();
    return { ok: false, state: status.state, message: status.recommendation };
  }
  const result = await synthesize('Voice Lite ready.', {
    language: selection.language,
    voice: 'base',
    timeoutMs: 15000,
  });
  writeHealth({
    ok: true,
    state: 'ready',
    runtime: runtime.binary,
    model: result.meta?.model || selection.slot.model,
    language: result.meta?.language || selection.language,
    voice: result.meta?.voice || selection.selectedKey,
    ttfa_ms: result.meta?.ttfa_ms ?? null,
    rtf: result.meta?.rtf ?? null,
  });
  return { ok: true, state: 'ready', runtime, meta: result.meta };
}

async function synthesize(text, options = {}) {
  const trimmed = String(text || '').trim();
  if (!trimmed) throw new Error('text is required');
  const planned = planSpeech(trimmed, options);
  const runtime = findRuntime();
  if (!runtime.binary) throw new Error(`Voice Lite runtime missing. ${runtimeInstallInstructions()}`);
  const selection = selectModel({ text: planned.text, language: options.language, voice: options.voice });
  if (!selection.slot) throw new Error(`Voice Lite model missing for ${selection.language.toUpperCase()}. Download base EN/NL or activate a custom model.`);

  const key = cacheKey(planned.text, options, selection.selectedKey);
  const cached = getCached(key);
  if (cached) return { ...cached, meta: { ...cached.meta, cached: true } };

  const out = path.join(os.tmpdir(), `voice-lite-${Date.now()}-${crypto.randomUUID()}.wav`);
  const threads = String(Math.max(1, Math.min(8, Number(options.threads || process.env.VOICE_LITE_THREADS || DEFAULT_THREADS))));
  const args = ['--model', selection.slot.model, '--config', selection.slot.config, '--output_file', out];
  if (planned.speaking_rate) {
    const lengthScale = Math.max(0.75, Math.min(1.25, 1 / planned.speaking_rate));
    args.push('--length_scale', String(lengthScale));
  }
  const started = Date.now();
  const result = await new Promise((resolve, reject) => {
    const child = spawn(runtime.binary, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, OMP_NUM_THREADS: threads, ORT_NUM_THREADS: threads },
    });
    let stderr = '';
    let stdout = '';
    const timeout = setTimeout(() => {
      try { child.kill('SIGTERM'); } catch (_err) { /* ignore */ }
      reject(new Error('Voice Lite synthesis timeout'));
    }, Number(options.timeoutMs || 30000));
    child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.once('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
    child.once('exit', (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(`Voice Lite Piper exited with code ${code}: ${stderr || stdout}`));
      resolve({ stdout, stderr });
    });
    child.stdin.end(planned.text);
  });
  const audioBuf = fs.readFileSync(out);
  try { fs.unlinkSync(out); } catch (_err) { /* ignore */ }
  if (!audioBuf || audioBuf.length < 44) throw new Error(`Voice Lite returned invalid WAV audio: ${result.stderr || result.stdout || 'empty output'}`);
  const elapsedMs = Date.now() - started;
  const durationMs = estimateWavDurationMs(audioBuf);
  const meta = {
    provider: 'voice_lite',
    engine: 'piper_onnx_cpu',
    language: selection.language,
    voice: selection.selectedKey,
    runtime: runtime.binary,
    model: selection.slot.model,
    elapsed_ms: elapsedMs,
    duration_ms: durationMs,
    ttfa_ms: elapsedMs,
    rtf: durationMs ? Number((elapsedMs / durationMs).toFixed(3)) : null,
    cpu_threads: Number(threads),
    cached: false,
    speech_plan: planned,
  };
  putCached(key, { audioBuf, meta });
  return { audioBuf, meta };
}

function artifactName() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return `voice_lite_${stamp}.wav`;
}

function saveArtifact(audioBuf, options = {}) {
  const dir = path.resolve(options.artifactDir || DEFAULT_ARTIFACT_DIR);
  ensureDir(dir);
  const name = artifactName();
  const filePath = path.join(dir, name);
  fs.writeFileSync(filePath, audioBuf);
  return {
    id: `voice:${name}`,
    name,
    type: 'audio',
    source: 'voice_lite_cpu',
    path: filePath,
    url: `/api/artifacts/${encodeURIComponent(name)}`,
    size: audioBuf.length,
    created_at: new Date().toISOString(),
  };
}

function datasetManifestPath() {
  return path.join(VOICE_LITE_STATE_ROOT, 'voice_lite_dataset_manifest.json');
}

function trainingJobPath(jobId) {
  return path.join(VOICE_LITE_STATE_ROOT, 'training', `${jobId}.json`);
}

function datasetStatus() {
  const manifest = readJson(datasetManifestPath(), null);
  if (!manifest) {
    return {
      ok: true,
      state: 'missing',
      ready_for_training: false,
      requirements: 'Provide owned/authorized EN and NL sentence-level WAV data. Minimum 30 minutes per language.',
    };
  }
  const perLanguage = manifest.language_minutes || {};
  const en = Number(perLanguage.en || 0);
  const nl = Number(perLanguage.nl || 0);
  return {
    ok: true,
    state: manifest.owner_confirmed ? 'authorized' : 'ownership_required',
    ready_for_training: Boolean(manifest.owner_confirmed && en >= 30 && nl >= 30),
    manifest,
    blockers: [
      !manifest.owner_confirmed ? 'owner_confirmed must be true' : null,
      en < 30 ? 'English dataset needs at least 30 minutes' : null,
      nl < 30 ? 'Dutch dataset needs at least 30 minutes' : null,
    ].filter(Boolean),
  };
}

function saveDatasetManifest(payload = {}) {
  if (payload.owner_confirmed !== true) {
    throw new Error('Custom voice dataset requires owner_confirmed: true before training.');
  }
  const languages = Array.isArray(payload.languages) ? payload.languages.map((v) => String(v).slice(0, 2).toLowerCase()) : [];
  if (!languages.includes('en') || !languages.includes('nl')) {
    throw new Error('Custom voice dataset must include both en and nl language tags.');
  }
  const languageMinutes = payload.language_minutes && typeof payload.language_minutes === 'object'
    ? { en: Number(payload.language_minutes.en || 0), nl: Number(payload.language_minutes.nl || 0) }
    : { en: 0, nl: 0 };
  const manifest = {
    schema: 1,
    voice_id: String(payload.voice_id || 'teammate_v1').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80),
    owner_confirmed: true,
    languages: ['en', 'nl'],
    language_minutes: languageMinutes,
    minutes_total: Number(payload.minutes_total || languageMinutes.en + languageMinutes.nl || 0),
    license: payload.license || 'private-local-authorized',
    base_model: payload.base_model || 'miso_one',
    base_model_source: payload.base_model === 'piper_vits' ? 'piper_vits' : MISO_ONE.source,
    source_path: payload.source_path ? String(payload.source_path) : null,
    created_at: new Date().toISOString(),
  };
  writeJson(datasetManifestPath(), manifest);
  return datasetStatus();
}

function startTraining(payload = {}) {
  const dataset = datasetStatus();
  const baseModel = payload.base_model || dataset.manifest?.base_model || 'miso_one';
  const baseReady = baseModel === 'miso_one' ? misoOneStatus().model_ready : true;
  const jobId = `voice-lite-train-${Date.now()}`;
  const job = {
    id: jobId,
    provider: 'voice_lite',
    state: dataset.ready_for_training && baseReady ? 'runtime_missing' : 'blocked',
    created_at: new Date().toISOString(),
    language: payload.language || 'en+nl',
    base_model: baseModel,
    message: dataset.ready_for_training
      ? baseReady
        ? 'Miso One foundation base is selected. Training/export tooling is not bundled yet, so training cannot start until the local training runtime is installed.'
        : 'Training blocked: Miso One foundation base is selected but model weights are not downloaded yet.'
      : `Training blocked: ${dataset.blockers?.join(', ') || 'dataset manifest missing'}.`,
    dataset,
    foundation: baseModel === 'miso_one' ? misoOneStatus() : null,
  };
  writeJson(trainingJobPath(jobId), job);
  return job;
}

function getTrainingJob(jobId) {
  const safe = String(jobId || '').replace(/[^a-zA-Z0-9_-]/g, '');
  return readJson(trainingJobPath(safe), null) || { id: safe, state: 'not_found' };
}

async function benchmark(payload = {}) {
  const status = await getStatus(payload);
  if (status.state !== 'ready') return { ok: false, state: status.state, message: status.recommendation, status };
  const phrases = payload.phrases || [
    { language: 'en', text: 'System ready. I am listening.' },
    { language: 'en', text: 'I checked the runtime and found the next useful action.' },
    { language: 'nl', text: 'Systeem klaar. Ik luister.' },
    { language: 'nl', text: 'Ik heb de status gecontroleerd en geef de beste volgende stap.' },
  ];
  const results = [];
  for (const phrase of phrases.slice(0, 16)) {
    try {
      const result = await synthesize(phrase.text, { language: phrase.language, voice: payload.voice || 'base' });
      results.push({ text: phrase.text, ...result.meta, audio_bytes: result.audioBuf.length });
    } catch (err) {
      results.push({ text: phrase.text, language: phrase.language, error: String(err.message || err) });
    }
  }
  const successful = results.filter((item) => !item.error);
  const rtfValues = successful.map((item) => Number(item.rtf)).filter(Number.isFinite);
  const ttfaValues = successful.map((item) => Number(item.ttfa_ms)).filter(Number.isFinite);
  const summary = {
    ok: successful.length > 0,
    provider: 'voice_lite',
    state: successful.length > 0 ? 'complete' : 'error',
    average_rtf: rtfValues.length ? Number((rtfValues.reduce((a, b) => a + b, 0) / rtfValues.length).toFixed(3)) : null,
    average_ttfa_ms: ttfaValues.length ? Math.round(ttfaValues.reduce((a, b) => a + b, 0) / ttfaValues.length) : null,
    results,
    generated_at: new Date().toISOString(),
  };
  writeJson(path.join(VOICE_LITE_ROOT, 'benchmark.json'), {
    rtf: summary.average_rtf,
    ttfa_ms: summary.average_ttfa_ms,
    results,
    generated_at: summary.generated_at,
  });
  return summary;
}

function activate(payload = {}) {
  const language = detectLanguage('', payload.language || 'en');
  const voice = normalizeVoice(payload.voice || 'custom');
  const selected = selectModel({ text: '', language, voice });
  if (!selected.slot) {
    throw new Error(`Cannot activate Voice Lite ${voice} ${language}: model is missing.`);
  }
  const active = {
    provider: 'voice_lite',
    foundation_model: 'miso_one',
    language,
    voice: selected.selectedKey,
    model: selected.slot.model,
    activated_at: new Date().toISOString(),
  };
  writeJson(path.join(VOICE_LITE_STATE_ROOT, 'voice_lite_active.json'), active);
  activeConfig = active;
  return { ok: true, active };
}

async function download(component, options = {}, emit = () => {}) {
  const name = String(component || '').trim();
  const token = createDownloadToken(name || 'voice_lite');
  try {
    if (name === 'voice_lite_runtime' || name === 'piper_runtime') return await downloadRuntime(emit, token);
    if (name === 'voice_lite_base_en' || name === 'base_en') return await downloadBaseModel('base_en', emit, token);
    if (name === 'voice_lite_base_nl' || name === 'base_nl') return await downloadBaseModel('base_nl', emit, token);
    if (name === 'voice_lite_miso_one' || name === 'miso_one' || name === 'miso_tts') return await downloadMisoOne(emit, token);
    throw new Error(`Unknown Voice Lite component: ${name}`);
  } catch (err) {
    downloadState.current = null;
    emit({
      type: 'download.error',
      component: name || 'voice_lite',
      state: 'error',
      error: String(err.message || err),
      message: String(err.message || err),
    });
    throw err;
  } finally {
    if (activeDownload === token) activeDownload = null;
  }
}

module.exports = {
  AI_HOME,
  VOICE_LITE_ROOT,
  VOICE_LITE_RUNTIME_ROOT,
  MODEL_SLOTS,
  PIPER_RUNTIME,
  MISO_ONE,
  getStatus,
  prewarm,
  download,
  cancelDownload,
  synthesize,
  saveArtifact,
  datasetStatus,
  saveDatasetManifest,
  startTraining,
  getTrainingJob,
  benchmark,
  activate,
  detectLanguage,
};
