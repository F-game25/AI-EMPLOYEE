'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const http = require('http');
const https = require('https');
const { spawn } = require('child_process');

const DEFAULT_BASE_URL = process.env.FISH_SPEECH_URL || process.env.FISH_AUDIO_S2_URL || 'http://127.0.0.1:8080';
const DEFAULT_ARTIFACT_DIR = require('../../state-paths').ARTIFACTS_DIR;  // canonical (C0)
const RECHECK_MS = 30_000;

const DEFAULT_OPTIONS = {
  enabled: true,
  baseUrl: DEFAULT_BASE_URL,
  apiKeyEnv: 'FISH_SPEECH_API_KEY',
  referenceId: '',
  format: 'wav',
  latency: 'normal',
  maxNewTokens: 1024,
  chunkLength: 200,
  topP: 0.8,
  repetitionPenalty: 1.1,
  temperature: 0.8,
  streaming: false,
  normalize: true,
  useMemoryCache: 'off',
  seed: null,
  timeoutMs: 45_000,
  healthTimeoutMs: 1500,
  localFallback: true,
  artifactDir: DEFAULT_ARTIFACT_DIR,
};

let currentOptions = { ...DEFAULT_OPTIONS };
let available = false;
let lastCheck = 0;
let lastError = null;

function clamp(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function asBool(value, fallback = false) {
  if (typeof value === 'boolean') return value;
  if (value == null) return fallback;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
}

function configure(options = {}) {
  const merged = { ...currentOptions, ...(options || {}) };
  currentOptions = normalizeOptions(merged);
  lastCheck = 0;
  return getConfig();
}

function normalizeOptions(options = {}) {
  let baseUrl = String(options.baseUrl || DEFAULT_BASE_URL).trim();
  while (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1);
  return {
    ...DEFAULT_OPTIONS,
    ...options,
    enabled: asBool(options.enabled, DEFAULT_OPTIONS.enabled),
    baseUrl,
    apiKeyEnv: String(options.apiKeyEnv || DEFAULT_OPTIONS.apiKeyEnv),
    referenceId: String(options.referenceId || '').trim(),
    format: ['wav', 'pcm', 'mp3', 'opus'].includes(options.format) ? options.format : 'wav',
    latency: ['normal', 'balanced'].includes(options.latency) ? options.latency : 'normal',
    maxNewTokens: Math.round(clamp(options.maxNewTokens, 0, 8192, DEFAULT_OPTIONS.maxNewTokens)),
    chunkLength: Math.round(clamp(options.chunkLength, 100, 1000, DEFAULT_OPTIONS.chunkLength)),
    topP: clamp(options.topP, 0.1, 1.0, DEFAULT_OPTIONS.topP),
    repetitionPenalty: clamp(options.repetitionPenalty, 0.9, 2.0, DEFAULT_OPTIONS.repetitionPenalty),
    temperature: clamp(options.temperature, 0.1, 1.0, DEFAULT_OPTIONS.temperature),
    streaming: asBool(options.streaming, false),
    normalize: asBool(options.normalize, true),
    useMemoryCache: options.useMemoryCache === 'on' ? 'on' : 'off',
    seed: options.seed === '' || options.seed == null ? null : Math.round(Number(options.seed)),
    timeoutMs: Math.round(clamp(options.timeoutMs, 3000, 180000, DEFAULT_OPTIONS.timeoutMs)),
    healthTimeoutMs: Math.round(clamp(options.healthTimeoutMs, 500, 15000, DEFAULT_OPTIONS.healthTimeoutMs)),
    localFallback: asBool(options.localFallback, true),
    artifactDir: path.resolve(String(options.artifactDir || DEFAULT_ARTIFACT_DIR)),
  };
}

function getConfig() {
  return { ...currentOptions };
}

function getApiKey() {
  const keyEnv = currentOptions.apiKeyEnv || 'FISH_SPEECH_API_KEY';
  return process.env[keyEnv] || process.env.FISH_SPEECH_API_KEY || process.env.FISH_AUDIO_API_KEY || '';
}

function buildUrl(endpoint) {
  const trimmed = String(endpoint || '').startsWith('/') ? endpoint : `/${endpoint}`;
  return new URL(`${currentOptions.baseUrl}${trimmed}`);
}

function request(method, endpoint, body, timeoutMs, responseMode = 'json') {
  return new Promise((resolve, reject) => {
    const url = buildUrl(endpoint);
    const isHttps = url.protocol === 'https:';
    const payload = body ? JSON.stringify(body) : null;
    const headers = {
      Accept: responseMode === 'buffer' ? 'audio/wav, audio/mpeg, audio/ogg, application/json' : 'application/json',
      ...(payload ? {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      } : {}),
    };
    const apiKey = getApiKey();
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

    const req = (isHttps ? https : http).request({
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: `${url.pathname}${url.search}`,
      method,
      headers,
      timeout: timeoutMs,
    }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        const contentType = String(res.headers['content-type'] || '');
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const detail = parseErrorBody(buf, contentType);
          return reject(new Error(`Fish Speech ${res.statusCode}: ${detail}`));
        }
        if (responseMode === 'buffer' && contentType.includes('audio')) return resolve(buf);
        if (responseMode === 'buffer' && buf.length > 100 && !contentType.includes('json')) return resolve(buf);
        if (!buf.length) return resolve({});
        try {
          return resolve(JSON.parse(buf.toString('utf8')));
        } catch (_err) {
          return responseMode === 'buffer' ? resolve(buf) : resolve({ raw: buf.toString('utf8') });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Fish Speech local server timeout'));
    });
    if (payload) req.write(payload);
    req.end();
  });
}

function parseErrorBody(buf, contentType) {
  if (!buf || !buf.length) return 'empty response';
  if (String(contentType || '').includes('json')) {
    try {
      const parsed = JSON.parse(buf.toString('utf8'));
      return parsed.error || parsed.detail || parsed.message || JSON.stringify(parsed);
    } catch (_err) {
      return buf.toString('utf8');
    }
  }
  return buf.toString('utf8').slice(0, 500);
}

async function checkAvailability(options = {}) {
  if (options && Object.keys(options).length) configure(options);
  if (!currentOptions.enabled) {
    available = false;
    lastError = 'Fish Speech provider is disabled';
    return false;
  }
  if (Date.now() - lastCheck < RECHECK_MS) return available;
  lastCheck = Date.now();
  try {
    const result = await request('GET', '/v1/health', null, currentOptions.healthTimeoutMs, 'json');
    available = result?.status === 'ok';
    lastError = available ? null : `Unexpected health response: ${JSON.stringify(result)}`;
  } catch (err) {
    available = false;
    lastError = String(err.message || err);
  }
  return available;
}

function buildTtsBody(text, overrides = {}) {
  const p = normalizeOptions({ ...currentOptions, ...(overrides || {}) });
  const body = {
    text: String(text || '').trim(),
    references: Array.isArray(overrides.references) ? overrides.references : [],
    reference_id: String(overrides.referenceId || p.referenceId || '').trim() || null,
    format: p.format,
    latency: p.latency,
    max_new_tokens: p.maxNewTokens,
    chunk_length: p.chunkLength,
    top_p: p.topP,
    repetition_penalty: p.repetitionPenalty,
    temperature: p.temperature,
    streaming: false,
    normalize: p.normalize,
    use_memory_cache: p.useMemoryCache,
    seed: p.seed,
  };
  Object.keys(body).forEach((key) => {
    if (body[key] == null || body[key] === '') delete body[key];
  });
  return body;
}

async function synthesize(text, options = {}) {
  const trimmed = String(text || '').trim();
  if (!trimmed) throw new Error('text is required');
  const body = buildTtsBody(trimmed, options);
  const audioBuf = await request('POST', '/v1/tts', body, currentOptions.timeoutMs, 'buffer');
  if (!Buffer.isBuffer(audioBuf) || audioBuf.length < 100) {
    throw new Error('Fish Speech returned invalid audio data');
  }
  return audioBuf;
}

function artifactName(format = 'wav') {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const ext = ['wav', 'mp3', 'opus', 'pcm'].includes(format) ? format : 'wav';
  return `voice_fish_s2_${stamp}.${ext}`;
}

function saveArtifact(audioBuf, options = {}) {
  const format = options.format || currentOptions.format || 'wav';
  const dir = path.resolve(options.artifactDir || currentOptions.artifactDir || DEFAULT_ARTIFACT_DIR);
  fs.mkdirSync(dir, { recursive: true });
  const name = artifactName(format);
  const filePath = path.join(dir, name);
  fs.writeFileSync(filePath, audioBuf);
  return {
    id: `voice:${name}`,
    name,
    type: 'audio',
    source: 'fish_speech_s2_local',
    path: filePath,
    url: `/api/artifacts/${encodeURIComponent(name)}`,
    size: audioBuf.length,
    created_at: new Date().toISOString(),
  };
}

function playerCommand(filePath) {
  const pf = os.platform();
  if (pf === 'linux') return { cmd: 'aplay', args: ['-q', filePath] };
  if (pf === 'darwin') return { cmd: 'afplay', args: [filePath] };
  if (pf === 'win32') {
    const ps = `(New-Object Media.SoundPlayer '${filePath.replace(/'/g, "''")}').PlaySync()`;
    return { cmd: 'powershell', args: ['-NoProfile', '-c', ps] };
  }
  return null;
}

async function playFile(filePath) {
  const command = playerCommand(filePath);
  if (!command) throw new Error('No local audio player available on this platform');
  await new Promise((resolve, reject) => {
    const child = spawn(command.cmd, command.args, { stdio: 'ignore' });
    child.once('exit', (code) => {
      if (code === 0) return resolve();
      return reject(new Error(`${command.cmd} exited with code ${code}`));
    });
    child.once('error', reject);
  });
}

async function synthesizeAndPlay(text, options = {}) {
  const audioBuf = await synthesize(text, options);
  const artifact = saveArtifact(audioBuf, options);
  await playFile(artifact.path);
  return artifact;
}

function getStatus() {
  const configured = Boolean(currentOptions.enabled && currentOptions.baseUrl);
  let status = 'not_configured';
  if (configured && available) status = 'live';
  else if (configured && lastError) status = 'unavailable';
  else if (configured) status = 'unknown';
  return {
    provider: 'fish_speech_s2_local',
    configured,
    available,
    status,
    baseUrl: currentOptions.baseUrl,
    endpoint: `${currentOptions.baseUrl}/v1/tts`,
    healthUrl: `${currentOptions.baseUrl}/v1/health`,
    model: 'Fish Audio S2/S2-Pro local server',
    local: true,
    last_checked_at: lastCheck ? new Date(lastCheck).toISOString() : null,
    last_error: lastError,
    defaults: getConfig(),
    docs_hint: 'Start Fish Speech locally on 127.0.0.1:8080, then test this provider from Voice settings.',
  };
}

module.exports = {
  DEFAULT_OPTIONS,
  configure,
  getConfig,
  getApiKey,
  checkAvailability,
  getStatus,
  synthesize,
  synthesizeAndPlay,
  saveArtifact,
};
