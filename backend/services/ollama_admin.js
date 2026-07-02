'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'))
const RUN_DIR = path.resolve(process.env.RUN_DIR || path.join(AI_HOME, 'run'))
const LOG_DIR = path.resolve(process.env.LOG_DIR || path.join(AI_HOME, 'logs'))
const DEFAULT_HOST = 'http://127.0.0.1:11434'
const DEFAULT_MODEL = 'qwythos:q4'
const DEFAULT_MODEL_HOME = path.join(AI_HOME, 'models', 'ollama')
const BUNDLED_ROOT = path.join(REPO_ROOT, 'runtime', 'vendor', 'ollama')
const BUNDLED_LIBRARY_DIR = path.join(BUNDLED_ROOT, 'lib')
const SYSTEM_LIBRARY_DIR = '/usr/local/lib/ollama'
const MODEL_CATALOG = [
  {
    model: 'qwythos:q4',
    label: 'Qwythos 9B (Claude-Mythos)',
    tier: 'recommended',
    estimated_size_gib: 7,
    min_ram_gib: 8,
    min_vram_gib: 6,
    min_cpu_cores: 4,
    priority: 60,
    rationale: 'Primary system model: Claude-distilled 9B with strong reasoning + coding, hardened and tuned for this system. Runs on 8 GB (GPU-accelerated, or CPU on 8 GB+ RAM). Recommended for best overall capability and efficiency.',
  },
  {
    model: 'qwen2.5:32b',
    label: 'Qwen 2.5 32B',
    tier: 'workstation',
    estimated_size_gib: 20,
    min_ram_gib: 64,
    min_vram_gib: 24,
    min_cpu_cores: 12,
    priority: 50,
    rationale: 'Highest local reasoning tier for high-memory workstations or large NVIDIA GPUs.',
  },
  {
    model: 'qwen2.5:14b',
    label: 'Qwen 2.5 14B',
    tier: 'power',
    estimated_size_gib: 9,
    min_ram_gib: 32,
    min_vram_gib: 10,
    min_cpu_cores: 8,
    priority: 40,
    rationale: 'Strong local reasoning while staying practical on modern high-RAM PCs.',
  },
  {
    model: 'qwen2.5:7b',
    label: 'Qwen 2.5 7B',
    tier: 'balanced',
    estimated_size_gib: 5,
    min_ram_gib: 14,
    min_vram_gib: 0,
    min_cpu_cores: 4,
    priority: 30,
    rationale: 'Best first-boot balance for a smart teammate voice: capable, responsive, and not too large.',
  },
  {
    model: 'llama3.2:3b',
    label: 'Llama 3.2 3B',
    tier: 'light',
    estimated_size_gib: 3,
    min_ram_gib: 8,
    min_vram_gib: 0,
    min_cpu_cores: 2,
    priority: 20,
    rationale: 'Lightweight fallback for lower-memory machines and faster voice latency.',
  },
  {
    model: 'llama3.2:1b',
    label: 'Llama 3.2 1B',
    tier: 'minimum',
    estimated_size_gib: 2,
    min_ram_gib: 4,
    min_vram_gib: 0,
    min_cpu_cores: 2,
    priority: 10,
    rationale: 'Minimum local model when RAM or disk is tight.',
  },
]

function normalizeHost(value) {
  const raw = String(value || DEFAULT_HOST).trim()
  if (!raw) return DEFAULT_HOST
  try {
    const url = new URL(/^[a-z]+:\/\//i.test(raw) ? raw : `http://${raw}`)
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/$/, '')
  } catch {
    return DEFAULT_HOST
  }
}

function ollamaHost() {
  return normalizeHost(process.env.OLLAMA_HOST || process.env.OLLAMA_URL || process.env.OLLAMA_ENDPOINT || DEFAULT_HOST)
}

function modelHome() {
  return path.resolve(process.env.OLLAMA_MODELS || DEFAULT_MODEL_HOME)
}

function configuredModel() {
  const recommended = recommendLocalModel(detectHardware({ includeDisk: false }))
  return String(process.env.OLLAMA_MODEL || recommended.model || DEFAULT_MODEL).trim() || DEFAULT_MODEL
}

function pidFile() {
  return path.join(RUN_DIR, 'ollama.pid')
}

function logFile() {
  return path.join(LOG_DIR, 'ollama.log')
}

function mkdirp(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function isExecutable(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK)
    return true
  } catch {
    return false
  }
}

function which(command) {
  try {
    const result = spawnSync('which', [command], { encoding: 'utf8' })
    const found = String(result.stdout || '').trim().split('\n')[0]
    return result.status === 0 && found ? found : null
  } catch {
    return null
  }
}

function resolveBinary() {
  const explicit = process.env.OLLAMA_BIN ? path.resolve(process.env.OLLAMA_BIN) : null
  const candidates = [
    explicit ? { path: explicit, source: 'env', bundled: false } : null,
    { path: path.join(BUNDLED_ROOT, 'ollama'), source: 'bundled', bundled: true },
    { path: path.join(BUNDLED_ROOT, 'bin', 'ollama'), source: 'bundled', bundled: true },
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (isExecutable(candidate.path)) return candidate
  }

  const systemPath = which('ollama')
  return systemPath && isExecutable(systemPath)
    ? { path: systemPath, source: 'system_fallback', bundled: false }
    : null
}

function runtimeLibraryDirs() {
  return [BUNDLED_LIBRARY_DIR, SYSTEM_LIBRARY_DIR].filter((dir) => {
    try { return fs.existsSync(dir) } catch { return false }
  })
}

function runtimeEnv() {
  const libraryDirs = runtimeLibraryDirs()
  const existingLd = String(process.env.LD_LIBRARY_PATH || '').trim()
  const ldLibraryPath = [...libraryDirs, existingLd].filter(Boolean).join(':')
  return {
    ...process.env,
    OLLAMA_HOST: ollamaHost(),
    OLLAMA_MODELS: modelHome(),
    OLLAMA_LIBRARY_PATH: libraryDirs.join(':'),
    OLLAMA_NO_CLOUD: process.env.OLLAMA_NO_CLOUD || '1',
    ...(ldLibraryPath ? { LD_LIBRARY_PATH: ldLibraryPath } : {}),
    AI_HOME,
    AI_EMPLOYEE_HOME: process.env.AI_EMPLOYEE_HOME || AI_HOME,
  }
}

function readPid() {
  try {
    const pid = Number.parseInt(fs.readFileSync(pidFile(), 'utf8').trim(), 10)
    return Number.isFinite(pid) && pid > 0 ? pid : null
  } catch {
    return null
  }
}

function pidAlive(pid) {
  if (!pid) return false
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function gib(bytes) {
  return Number((bytes / 1024 / 1024 / 1024).toFixed(2))
}

function diskStats(target = modelHome()) {
  try {
    mkdirp(target)
    if (typeof fs.statfsSync !== 'function') {
      return { path: target, available: null, available_gib: null, total: null, total_gib: null, error: 'statfs_unavailable' }
    }
    const stat = fs.statfsSync(target)
    const available = Number(stat.bavail) * Number(stat.bsize)
    const total = Number(stat.blocks) * Number(stat.bsize)
    return { path: target, available, available_gib: gib(available), total, total_gib: gib(total) }
  } catch (error) {
    return { path: target, available: null, available_gib: null, total: null, total_gib: null, error: error.message }
  }
}

function parseNvidiaSmi() {
  try {
    const result = spawnSync(
      'nvidia-smi',
      ['--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
      { encoding: 'utf8', timeout: 1500 },
    )
    if (result.status !== 0) return []
    return String(result.stdout || '')
      .trim()
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(',')
        const memoryMiB = Number.parseFloat(String(parts.pop() || '').trim())
        return {
          vendor: 'nvidia',
          name: parts.join(',').trim() || 'NVIDIA GPU',
          vram_gib: Number.isFinite(memoryMiB) ? Number((memoryMiB / 1024).toFixed(2)) : null,
        }
      })
  } catch {
    return []
  }
}

function parseLspciGpus() {
  try {
    const result = spawnSync('lspci', [], { encoding: 'utf8', timeout: 1500 })
    if (result.status !== 0) return []
    return String(result.stdout || '')
      .split('\n')
      .filter((line) => /vga|3d controller|display controller/i.test(line))
      .map((line) => ({
        vendor: /nvidia/i.test(line) ? 'nvidia' : /amd|radeon/i.test(line) ? 'amd' : /intel/i.test(line) ? 'intel' : 'unknown',
        name: line.replace(/^[0-9a-f:.]+\s+/i, '').trim(),
        vram_gib: null,
      }))
  } catch {
    return []
  }
}

function detectHardware(options = {}) {
  const includeDisk = options.includeDisk !== false
  const cpus = os.cpus() || []
  const nvidia = parseNvidiaSmi()
  const fallbackGpus = nvidia.length ? [] : parseLspciGpus()
  const gpus = [...nvidia, ...fallbackGpus]
  const maxVram = gpus.reduce((max, gpu) => Math.max(max, Number(gpu.vram_gib) || 0), 0)
  return {
    platform: process.platform,
    arch: process.arch,
    cpu: {
      model: cpus[0]?.model || 'unknown',
      cores: cpus.length || os.availableParallelism?.() || 1,
    },
    memory: {
      total_gib: gib(os.totalmem()),
      free_gib: gib(os.freemem()),
    },
    gpu: {
      available: gpus.length > 0,
      max_vram_gib: maxVram || null,
      devices: gpus,
    },
    disk: includeDisk ? diskStats() : null,
  }
}

function modelFitsHardware(candidate, hardware) {
  const ram = Number(hardware?.memory?.total_gib) || 0
  const cores = Number(hardware?.cpu?.cores) || 0
  const vram = Number(hardware?.gpu?.max_vram_gib) || 0
  const disk = hardware?.disk
  const diskOk = !disk || typeof disk.available_gib !== 'number' || disk.available_gib >= candidate.estimated_size_gib + 2
  const cpuOk = ram >= candidate.min_ram_gib && cores >= candidate.min_cpu_cores
  const gpuOk = candidate.min_vram_gib > 0 && vram >= candidate.min_vram_gib
  return diskOk && (cpuOk || gpuOk)
}

function recommendLocalModel(hardware = detectHardware()) {
  const ordered = [...MODEL_CATALOG].sort((a, b) => b.priority - a.priority)
  const selected = ordered.find((candidate) => modelFitsHardware(candidate, hardware)) || MODEL_CATALOG[MODEL_CATALOG.length - 1]
  const ram = hardware?.memory?.total_gib ?? 'unknown'
  const cores = hardware?.cpu?.cores ?? 'unknown'
  const vram = hardware?.gpu?.max_vram_gib
  const disk = hardware?.disk
  const diskText = disk?.available_gib ? `${disk.available_gib} GiB free at ${disk.path}` : 'model storage free space unknown'
  return {
    ...selected,
    hardware_summary: `${ram} GiB RAM, ${cores} CPU cores${vram ? `, ${vram} GiB GPU VRAM` : ''}`,
    reason: `${selected.rationale} Detected ${ram} GiB RAM, ${cores} CPU cores${vram ? `, ${vram} GiB GPU VRAM` : ''}; ${diskText}.`,
    alternatives: ordered
      .filter((candidate) => candidate.model !== selected.model)
      .map((candidate) => ({
        model: candidate.model,
        label: candidate.label,
        tier: candidate.tier,
        estimated_size_gib: candidate.estimated_size_gib,
        fits: modelFitsHardware(candidate, hardware),
      })),
    hardware,
  }
}

function getModelRecommendation() {
  return recommendLocalModel(detectHardware())
}

function modelNameVariants(name) {
  const trimmed = String(name || '').trim()
  if (!trimmed) return []
  const variants = new Set([trimmed])
  if (!trimmed.includes(':')) variants.add(`${trimmed}:latest`)
  if (trimmed.endsWith(':latest')) variants.add(trimmed.slice(0, -':latest'.length))
  return [...variants]
}

function hasConfiguredModel(models, model = configuredModel()) {
  const wanted = new Set(modelNameVariants(model))
  return (models || []).some((entry) => wanted.has(entry.name))
}

async function isOllamaRunning(timeoutMs = 2000) {
  try {
    const response = await fetch(`${ollamaHost()}/api/tags`, { signal: AbortSignal.timeout(timeoutMs) })
    return response.ok
  } catch {
    return false
  }
}

async function listModels() {
  try {
    const response = await fetch(`${ollamaHost()}/api/tags`, { signal: AbortSignal.timeout(4000) })
    if (!response.ok) return []
    const data = await response.json()
    return (data.models || []).map((model) => ({
      name: model.name,
      size: model.size,
      modified_at: model.modified_at,
      digest: model.digest,
      details: model.details,
    }))
  } catch {
    return []
  }
}

async function getRuntimeStatus() {
  const binary = resolveBinary()
  const running = await isOllamaRunning().catch(() => false)
  const models = running ? await listModels().catch(() => []) : []
  const pid = readPid()
  const disk = diskStats()
  const libraries = runtimeLibraryDirs()
  const hardware = detectHardware()
  const recommended = recommendLocalModel(hardware)
  const model = String(process.env.OLLAMA_MODEL || recommended.model || DEFAULT_MODEL).trim()
  const modelAvailable = hasConfiguredModel(models, model)
  const minFreeGib = Number.parseFloat(process.env.OLLAMA_MIN_FREE_GIB || '4')
  const lowDisk = typeof disk.available_gib === 'number' && Number.isFinite(minFreeGib) && disk.available_gib < minFreeGib

  let status = 'stopped'
  if (running && modelAvailable) status = 'ready'
  else if (running) status = 'model_missing'
  else if (!binary) status = 'binary_missing'
  else if (disk.error) status = 'storage_error'
  else if (lowDisk) status = 'low_disk'
  else if (pidAlive(pid)) status = 'starting'

  return {
    ok: status === 'ready',
    status,
    setup_state: status,
    running,
    can_start: !!binary,
    host: ollamaHost(),
    binary: binary ? { path: binary.path, source: binary.source, bundled: binary.bundled } : null,
    expected_bundled_paths: [path.join(BUNDLED_ROOT, 'ollama'), path.join(BUNDLED_ROOT, 'bin', 'ollama')],
    library_dirs: libraries,
    library_path: libraries.join(':'),
    model_home: modelHome(),
    model_home_source: process.env.OLLAMA_MODELS ? 'env' : 'app_data_default',
    configured_model: model,
    recommended_model: recommended,
    hardware,
    model_available: modelAvailable,
    model_count: models.length,
    models,
    pid,
    pid_running: pidAlive(pid),
    pid_file: pidFile(),
    log_file: logFile(),
    disk,
    min_free_gib: minFreeGib,
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function ensureStarted(options = {}) {
  const waitMs = Number(options.waitMs || 15000)
  if (await isOllamaRunning()) {
    return { ok: true, already_running: true, runtime: await getRuntimeStatus() }
  }

  const binary = resolveBinary()
  if (!binary) {
    return { ok: false, error: 'Ollama runtime binary is missing. Package runtime/vendor/ollama/ollama or set OLLAMA_BIN.', runtime: await getRuntimeStatus() }
  }

  const disk = diskStats()
  if (disk.error) {
    return { ok: false, error: `Cannot access Ollama model storage at ${disk.path}: ${disk.error}. Set OLLAMA_MODELS to a writable drive.`, runtime: await getRuntimeStatus() }
  }

  mkdirp(RUN_DIR)
  mkdirp(LOG_DIR)
  mkdirp(modelHome())

  const out = fs.openSync(logFile(), 'a')
  let child
  try {
    child = spawn(binary.path, ['serve'], {
      cwd: REPO_ROOT,
      detached: true,
      env: runtimeEnv(),
      stdio: ['ignore', out, out],
    })
  } catch (error) {
    try { fs.closeSync(out) } catch {}
    return { ok: false, error: error.message, runtime: await getRuntimeStatus() }
  }
  try { fs.closeSync(out) } catch {}
  fs.writeFileSync(pidFile(), String(child.pid), 'utf8')
  child.unref()

  const deadline = Date.now() + waitMs
  while (Date.now() < deadline) {
    if (await isOllamaRunning(1000)) return { ok: true, started: true, runtime: await getRuntimeStatus() }
    await sleep(500)
  }

  return { ok: false, error: `Ollama did not become ready within ${Math.round(waitMs / 1000)}s. Check ${logFile()}.`, runtime: await getRuntimeStatus() }
}

async function startManaged(options = {}) {
  return ensureStarted(options)
}

async function stopManaged() {
  const pid = readPid()
  if (!pid || !pidAlive(pid)) return { ok: true, stopped: false }
  try {
    process.kill(pid, 'SIGTERM')
    return { ok: true, stopped: true, pid }
  } catch (error) {
    return { ok: false, error: error.message, pid }
  }
}

function storageHint() {
  const disk = diskStats()
  const free = typeof disk.available_gib === 'number' ? `${disk.available_gib} GiB free` : 'free space unknown'
  return `Ollama stores models at ${disk.path} (${free}). Set OLLAMA_MODELS to a drive with enough space before pulling.`
}

function enrichOllamaError(message) {
  const text = String(message || 'ollama request failed')
  return /space|disk|no such file|no space/i.test(text) ? `${text}. ${storageHint()}` : text
}

async function pullModel(name) {
  const started = await ensureStarted({ waitMs: 20000 })
  if (!started.ok) return { ok: false, status: 0, message: started.error, runtime: started.runtime }
  try {
    const response = await fetch(`${ollamaHost()}/api/pull`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(300000),
    })
    if (!response.ok) return { ok: false, status: response.status, message: enrichOllamaError(await response.text().catch(() => `pull failed (${response.status})`)) }
    return { ok: true, status: 'success', message: 'pulled', runtime: await getRuntimeStatus() }
  } catch (error) {
    return { ok: false, status: 0, message: enrichOllamaError(error.message) }
  }
}

async function deleteModel(name) {
  const started = await ensureStarted({ waitMs: 10000 })
  if (!started.ok) return { ok: false, error: started.error, runtime: started.runtime }
  try {
    const response = await fetch(`${ollamaHost()}/api/delete`, {
      method: 'DELETE',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(10000),
    })
    return { ok: response.ok, status: response.status }
  } catch (error) {
    return { ok: false, error: enrichOllamaError(error.message) }
  }
}

async function* pullModelStream(name) {
  const started = await ensureStarted({ waitMs: 20000 })
  if (!started.ok) throw new Error(started.error)
  yield { status: started.started ? 'runtime_started' : 'runtime_ready', host: ollamaHost(), model_home: modelHome(), disk: diskStats() }

  const response = await fetch(`${ollamaHost()}/api/pull`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, stream: true }),
  })
  if (!response.ok) throw new Error(enrichOllamaError(await response.text().catch(() => `ollama pull failed (${response.status})`)))

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line)
      if (event.error) throw new Error(enrichOllamaError(event.error))
      yield event
    }
  }
}

async function showModel(name) {
  const started = await ensureStarted({ waitMs: 10000 })
  if (!started.ok) return { error: started.error, runtime: started.runtime }
  try {
    const response = await fetch(`${ollamaHost()}/api/show`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
      signal: AbortSignal.timeout(10000),
    })
    if (!response.ok) throw new Error(`ollama show failed (${response.status})`)
    return response.json()
  } catch (error) {
    return { error: enrichOllamaError(error.message) }
  }
}

const listLocalModels = listModels

// ── Running models (currently loaded in VRAM) ────────────────────────────────

async function listRunning() {
  try {
    const response = await fetch(`${ollamaHost()}/api/ps`, { signal: AbortSignal.timeout(5000) })
    if (!response.ok) return { ok: false, models: [], error: `ollama ps failed (${response.status})` }
    const data = await response.json()
    return { ok: true, models: data.models || [] }
  } catch (error) {
    return { ok: false, models: [], error: error.message }
  }
}

// ── Load model into VRAM (warm / keep_alive) ─────────────────────────────────

async function loadModel(name, keepAlive = -1) {
  if (!name) return { ok: false, error: 'name required' }
  const started = await ensureStarted({ waitMs: 10000 })
  if (!started.ok) return { ok: false, error: started.error }
  try {
    const response = await fetch(`${ollamaHost()}/api/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: name, prompt: ' ', keep_alive: keepAlive, stream: false }),
      signal: AbortSignal.timeout(30000),
    })
    return { ok: response.ok, name, keep_alive: keepAlive }
  } catch (error) {
    return { ok: false, error: enrichOllamaError(error.message) }
  }
}

// ── Evict model from VRAM (keep_alive=0 forces unload) ───────────────────────

async function evictModel(name) {
  return loadModel(name, 0)
}

module.exports = {
  DEFAULT_HOST,
  DEFAULT_MODEL,
  ollamaHost,
  modelHome,
  configuredModel,
  detectHardware,
  recommendLocalModel,
  getModelRecommendation,
  getRuntimeStatus,
  startManaged,
  stopManaged,
  ensureStarted,
  listModels,
  listLocalModels,
  listRunning,
  loadModel,
  evictModel,
  showModel,
  deleteModel,
  pullModel,
  pullModelStream,
  isOllamaRunning,
}
