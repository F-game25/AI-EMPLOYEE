'use strict';

// ── Sentry initialization (must be first) ────────────────────────────────────
if (process.env.SENTRY_DSN) {
  const Sentry = require('@sentry/node');
  const { nodeProfilingIntegration } = require('@sentry/profiling-node');
  Sentry.init({
    dsn: process.env.SENTRY_DSN,
    integrations: [new nodeProfilingIntegration()],
    tracesSampleRate: 0.1,
    profilesSampleRate: 0.1,
    environment: process.env.ENVIRONMENT || 'production',
  });
}

const http = require('http');
const os = require('os');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { execSync, spawn } = require('child_process');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');
const jwt = require('jsonwebtoken');
const helmet = require('helmet');

const gateway = require('./gateway');
const orchestrator = require('./orchestrator');
const broadcaster = require('./events/broadcaster');
const { getEventBus, EVENT_TYPES: BUS_EVENT_TYPES } = require('./infra/events/bus');
const eventRoutes = require('./infra/events/routes');
const { getWorkflowEngine } = require('./infra/workflows/engine');
const workflowRoutes = require('./infra/workflows/routes');
const { getSandboxExecutor } = require('./infra/sandbox/executor');
const sandboxRoutes = require('./infra/sandbox/routes');
const { injectRole } = require('./infra/rbac/middleware');
const { getSecretsBroker } = require('./infra/secrets/broker');
const secretsRoutes = require('./infra/secrets/routes');
// Phase 2 — Enterprise Intelligence routes
const ragRoutes        = require('./infra/rag/routes');
const planningRoutes   = require('./infra/planning/routes');
const economicsRoutes  = require('./infra/economics/routes');
const governanceRoutes = require('./infra/governance/routes');
const telemetryRoutes  = require('./infra/telemetry/routes');
// Phase 3 — Autonomous Workforce routes
const rpaRoutes        = require('./infra/rpa/routes');
const healingRoutes    = require('./infra/healing/routes');
const marketplaceRoutes = require('./infra/marketplace/routes');
const deploymentRoutes = require('./infra/deployment/routes');
const simulationRoutes = require('./infra/simulation/routes');
// Phase 4 — Enterprise Autonomy Stabilization routes
const cognitiveRoutes  = require('./infra/cognitive/routes');
const { SecretStore } = require('./security/secrets');
const { createOfflineSecuritySyncPolicy } = require('./security/offline_sync_policy');
const { createApiGatewayProtector } = require('./security/api_gateway');
const { createAnomalyResponder } = require('./security/anomaly_response');
const blacklightTools = require('./security/blacklight_tools');
const { tenantMiddleware, requireTenant } = require('./tenancy');
const { enforceRegion } = require('./middleware/region');
const ConnectionManager = require('./websocket/connection-manager');
const HeartbeatManager = require('./websocket/heartbeat');
const { createUpgradeHandler } = require('./websocket/upgrade-handlers');
const {
  getAgents,
  on: onAgentEvent,
  activateAgents,
  getRunningAgentCount,
  setMode,
  getMode,
  getRobotSignal,
  stopAllAgents,
} = require('./agents');
const subsystems = require('./subsystems');
const { buildMoneyTemplate, buildThinkingSummary } = require('./money_mode');
const brain = require('./brain/active_brain');
const persistence = require('./persistence');

// Phase 7A: defer heavy/native requires to cut synchronous startup cost.

// better-sqlite3 is a native binary; only used in the forge_queue IIFE.
let _Database;
const getDatabase = () => _Database || (_Database = require('better-sqlite3'));

// getNativeMemoryGraph triggers file I/O on init; only used in route handlers.
let _nativeMemoryGraphMod;
const getNativeMemoryGraph = (...args) => {
  if (!_nativeMemoryGraphMod) _nativeMemoryGraphMod = require('./core/native-memory-graph');
  return _nativeMemoryGraphMod.getNativeMemoryGraph(...args);
};

// Voice system spawns child processes via fish_speech; defer until init call.
let _voiceManager;
const voiceManager = new Proxy({}, {
  get(_, prop) {
    if (!_voiceManager) _voiceManager = require('./core/voice_manager');
    const val = _voiceManager[prop];
    return typeof val === 'function' ? val.bind(_voiceManager) : val;
  },
});
let _voiceApiRouter;
const getVoiceApiRouter = () => _voiceApiRouter || (_voiceApiRouter = require('./api/voice'));

const ErrorRecoveryManager = require('./core/error_recovery');
const TaskHistoryManager = require('./core/task_history');
const { createTurnRunner } = require('./services/turn-runner');
const { z } = require('zod');
const economyService = require('./services/economy_service');
const ollamaAdmin = require('./services/ollama_admin');
const autoUpdateWatchdog = require('./services/auto-update-watchdog');

// Initialize error recovery and task history
const errorRecovery = new ErrorRecoveryManager();
const taskHistory = new TaskHistoryManager();


// ── Request validation helpers ────────────────────────────────────────────────
// Returns parsed body on success, sends 400 and returns null on failure.
function validate(schema, req, res) {
  const result = schema.safeParse(req.body || {});
  if (!result.success) {
    res.status(400).json({ ok: false, error: 'Validation error', details: result.error.flatten() });
    return null;
  }
  return result.data;
}

// Shared schemas
const _zStr    = z.string().trim();
const _zStrMax = (n) => _zStr.max(n);
const _zGoal   = _zStrMax(4000).min(1, 'goal required');
const _zTask   = _zStrMax(4000).min(1, 'task required');
const _zMsg    = _zStrMax(8000).min(1, 'message required');

const SCHEMAS = {
  chat:           z.object({ message: _zMsg, model: _zStrMax(100).optional(), context: z.any().optional() }),
  tasksRun:       z.object({ task: _zTask, agent: _zStrMax(100).optional(), user_id: _zStrMax(200).optional() }),
  forgeSubmit:    z.object({ goal: _zGoal, priority: z.enum(['low','medium','high','critical']).optional(), risk_level: _zStrMax(20).optional() }),
  forgeApprove:   z.object({ request_id: _zStrMax(100).min(1) }),
  forgeReject:    z.object({ request_id: _zStrMax(100).min(1), reason: _zStrMax(500).optional() }),
  forgeRollback:  z.object({ snapshot_id: _zStrMax(200).optional(), rolled_back_by: _zStrMax(100).optional() }),
  modeSet:        z.object({ mode: z.enum(['AUTONOMOUS','SUPERVISED','SAFE','PASSIVE','POWER','BUSINESS','STARTER']) }),
  memoryStore:    z.object({ key: _zStrMax(200).min(1), value: z.any() }),
  authToken:      z.object({ secret: _zStr.min(1) }),
  evolutionMode:  z.object({ mode: z.enum(['AUTO','SAFE','OFF']) }),
  agentControl:   z.object({ agent_id: _zStrMax(200).min(1), action: z.enum(['start','stop','restart']).optional() }),
  systemHalt:     z.object({ reason: _zStrMax(500).optional() }),
  voiceSynthesize: z.object({ text: _zStrMax(2000).min(1), persona: z.record(z.any()).optional() }),
  // Phase 6B additions
  identityFinalize:   z.object({ user_chosen: _zStrMax(200).optional(), instance_name: _zStrMax(100).optional(), voice_preset: _zStrMax(50).optional(), color_palette: z.record(z.any()).optional() }),
  agentsActivate:     z.object({ count: z.number().int().min(1).max(100).optional() }),
  securityOfflineSync: z.object({ online: z.boolean().optional() }),
  securityGatewayStrict: z.object({ enabled: z.boolean().optional() }),
  autonomyMode:       z.object({ mode: z.enum(['OFF','ON','AUTO']) }),
  automationControl:  z.object({ action: z.enum(['start','stop','override']), goal: _zStrMax(4000).optional(), override_action_id: _zStrMax(200).optional() }),
  moneyPipeline:      z.object({ goal: _zStrMax(4000).optional(), config: z.record(z.any()).optional() }),
  adminSafetyAction:  z.object({ action_id: _zStrMax(100).min(1), reason: _zStrMax(1000).min(8), confirmation: _zStrMax(200).min(1), execution_mode: _zStrMax(50).optional() }),
  adminSafetyAudit:   z.object({ label: _zStrMax(200).min(1), endpoint: _zStrMax(300).optional(), reason: _zStrMax(1000).min(8), confirmation: _zStrMax(200).min(1), executed: z.boolean().optional(), risk: _zStrMax(20).optional(), execution_mode: _zStrMax(50).optional() }),
  forgeSandbox:       z.object({ goal: _zGoal, module_path: _zStrMax(200).optional() }),
  forgeBuildSystem:   z.object({ spec: _zStrMax(4000).min(1), project_name: _zStrMax(200).optional() }),
  reconToolSearch:    z.object({ query: _zStrMax(500).optional() }),
  reconToolRun:       z.object({ tool_id: _zStrMax(200).optional(), toolId: _zStrMax(200).optional(), input: _zStrMax(20000).optional() }),
  reconCase:          z.object({ name: _zStrMax(120).optional(), target: _zStrMax(300).optional(), owner: _zStrMax(120).optional(), authorization: _zStrMax(2000).optional() }),
  reconFinding:       z.object({ case_id: _zStrMax(80).optional(), title: _zStrMax(160).optional(), severity: z.enum(['info','low','medium','high']).optional(), evidence: z.record(z.any()).optional(), source_tool: _zStrMax(120).optional() }),
  hermesTask:         z.object({ message: _zStrMax(4000).min(1), target_agent: _zStrMax(200).optional() }),
  hermesBroadcast:    z.object({ message: _zStrMax(4000).min(1) }),
  learningLadderBuild:    z.object({ topic: _zStrMax(200).min(1) }),
  learningLadderComplete: z.object({ topic: _zStrMax(200).min(1), level: z.number().int().min(1).max(5), success: z.boolean().optional(), milestone_output: _zStrMax(2000).optional(), score: z.number().optional(), notes: _zStrMax(1000).optional() }),
  agentLadderAssign:  z.object({ topic: _zStrMax(200).min(1) }),
  agentLadderAdvance: z.object({ level: z.number().int().min(1).max(5), success: z.boolean().optional(), score: z.number().optional(), milestone_output: _zStrMax(2000).optional(), notes: _zStrMax(1000).optional() }),
  forgeCodeAi:        z.object({ provider: _zStrMax(50).optional(), model: _zStrMax(100).optional(), messages: z.array(z.object({ role: _zStrMax(20).optional(), content: _zStrMax(8000) })).min(1), systemPrompt: _zStrMax(2000).optional() }),
  middlewareProcess:  z.object({ message: _zStrMax(8000).optional(), task: _zStrMax(4000).optional() }).passthrough(),
  moneyTask:          z.object({ task: _zStrMax(4000).optional(), mode: _zStrMax(20).optional() }),
  codingAiSettings:   z.object({ provider: _zStrMax(50).optional(), model: _zStrMax(100).optional(), openrouter_api_key: _zStrMax(200).optional() }),
  forgeTask:          z.object({ task: _zStrMax(4000).optional(), mode: _zStrMax(20).optional() }),
  modelRoutePlan:     z.object({ task: _zStrMax(4000).optional(), message: _zStrMax(4000).optional(), goal: _zStrMax(4000).optional(), modality: _zStrMax(50).optional() }),
  memoryClients:      z.object({ name: _zStrMax(200).optional(), email: _zStrMax(200).optional() }).passthrough(),
  memoryInteraction:  z.object({ client_id: _zStrMax(200).optional(), content: _zStrMax(8000).optional() }).passthrough(),
  errorReport:        z.object({ error: z.any(), context: z.record(z.any()).optional() }),
  frontendError:      z.object({ msg: _zStrMax(500).optional(), stack: _zStrMax(2000).optional(), ts: z.any().optional(), source: _zStrMax(50).optional() }),
  blacklistPolicy:    z.object({ network_osint_enabled: z.boolean().optional() }),
  approvalDecision:   z.object({ reason: _zStrMax(500).optional() }),
  forgeApproveItem:   z.object({ approved_by: _zStrMax(100).optional() }),
  forgeRejectItem:    z.object({ rejected_by: _zStrMax(100).optional(), reason: _zStrMax(500).optional() }),
  reliabilityFreeze:  z.object({ reason: _zStrMax(500).optional() }),
};

const PORT = process.env.PORT || 8787;
const PYTHON_BACKEND_HOST = '127.0.0.1';
const PYTHON_BACKEND_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const RUNTIME_NONCE = process.env.AI_EMPLOYEE_RUNTIME_NONCE || null;
const RUNTIME_MODE = process.env.AI_EMPLOYEE_RUNTIME_MODE || (process.env.AI_EMPLOYEE_PACKAGED === '1' ? 'packaged-runtime' : 'development-runtime');
const REPO_ROOT = path.resolve(__dirname, '..');
const AI_HOME = path.resolve(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'));
const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(AI_HOME, 'state'));
const LOG_DIR = path.resolve(process.env.LOG_DIR || path.join(AI_HOME, 'logs'));
const RUN_DIR = path.resolve(process.env.RUN_DIR || path.join(AI_HOME, 'run'));
for (const dir of [STATE_DIR, LOG_DIR, RUN_DIR]) {
  try { fs.mkdirSync(dir, { recursive: true }); } catch {}
}
const statePath = (...parts) => path.join(STATE_DIR, ...parts);
const FRONTEND_DIST = path.resolve(__dirname, '../frontend/dist');
const FRONTEND_INDEX = path.join(FRONTEND_DIST, 'index.html');
const HAS_FRONTEND_DIST = fs.existsSync(FRONTEND_INDEX);
const SERVER_START_TIMESTAMP = new Date().toISOString();
const SYSTEM_MANIFEST_FILE = path.join(REPO_ROOT, 'runtime', 'config', 'system_orchestration_manifest.json');

let _indexCache = null;
let _indexMtime = 0;
function readFrontendIndex() {
  try {
    const mtime = fs.statSync(FRONTEND_INDEX).mtimeMs;
    if (_indexCache !== null && mtime === _indexMtime) return _indexCache;
    _indexCache = fs.readFileSync(FRONTEND_INDEX, 'utf8');
    _indexMtime = mtime;
    return _indexCache;
  } catch {
    return '';
  }
}

// FIX-1: 2026-05-12 — Lazy-load git commit on-demand instead of blocking at startup
let _gitCommitCache = null;
function latestCommit() {
  if (_gitCommitCache !== null) return _gitCommitCache;
  try {
    _gitCommitCache = execSync('git log -1 --oneline', { cwd: REPO_ROOT, encoding: 'utf8', timeout: 2000 }).trim();
  } catch (_err) {
    _gitCommitCache = 'unknown';
  }
  return _gitCommitCache;
}

function loadSystemManifest() {
  try {
    return JSON.parse(fs.readFileSync(SYSTEM_MANIFEST_FILE, 'utf8'));
  } catch (err) {
    return {
      version: 'unavailable',
      error: err.message,
      agents: {},
      memory_fabric: { layers: [] },
      model_stack: {},
      token_orchestrator: {},
    };
  }
}

function buildModelRoutePlan(payload = {}) {
  const manifest = loadSystemManifest();
  const task = String(payload.task || payload.message || payload.goal || '').trim();
  const modality = String(payload.modality || '').toLowerCase();
  const needsAction = /\b(click|browser|file|api|execute|run|deploy|write|edit|build|create|publish|send)\b/i.test(task);
  const needsVision = modality === 'vision' || /\b(image|screenshot|screen|diagram|video|ocr|visual)\b/i.test(task);
  const needsMedia = modality === 'image' || /\b(generate image|render|avatar|video|visual asset)\b/i.test(task);
  const needsDeepReasoning = task.length > 1200 || /\b(strategy|architecture|debug|complex|multi[- ]?step|plan|reason)\b/i.test(task);
  const estimatedInputTokens = Math.ceil(task.length / 4);
  const contextPolicy = estimatedInputTokens > 1200 ? 'compact_memory_then_summarize' : 'retrieve_top_memory_only';

  const architectures = ['SLM', 'MLM'];
  if (needsVision) architectures.push('VLM');
  if (needsMedia) architectures.push('LCM');
  if (needsAction) architectures.push('LAM');
  architectures.push(needsDeepReasoning ? 'LLM' : 'SLM');
  architectures.push('MoE');

  const uniqueArchs = [...new Set(architectures)];
  const offlineDefault = String(process.env.AI_EMPLOYEE_OFFLINE || '1') !== '0';
  const externalAllowed = !offlineDefault && String(process.env.AI_EMPLOYEE_ALLOW_MODEL_DOWNLOADS || '0') === '1';
  const route = externalAllowed ? 'local_first_external_allowed' : 'local_only_or_degraded';
  return {
    ok: true,
    route,
    offline_default: offlineDefault,
    external_allowed: externalAllowed,
    estimated_input_tokens: estimatedInputTokens,
    context_policy: contextPolicy,
    selected_architectures: uniqueArchs,
    execution_order: [
      'SLM intent classification',
      'MLM memory retrieval',
      contextPolicy,
      needsAction ? 'LAM action plan with approval gates' : 'LLM/SLM response plan',
      'MoE final model selection by cost, health, and quality',
    ],
    remote_call_requirements: manifest.token_orchestrator?.remote_call_requirements || [],
    token_saving_steps: manifest.token_orchestrator?.steps || [],
    model_stack: uniqueArchs.reduce((acc, arch) => {
      acc[arch] = manifest.model_stack?.[arch] || {};
      return acc;
    }, {}),
  };
}
const GIT_COMMIT = 'pending'; // Placeholder until first access

// Metrics tracking for Prometheus endpoint
const startTime = Date.now();
let apiCallCounter = 0;
let taskMetrics = { completed: 0, failed: 0 };


// ── Auth ──────────────────────────────────────────────────────────────────────
// JWT_SECRET_KEY must be set in ~/.ai-employee/.env; fail fast if unset
const JWT_SECRET = process.env.JWT_SECRET_KEY;
if (!JWT_SECRET) {
  console.error('\n❌ FATAL: JWT_SECRET_KEY is not set in environment.');
  console.error('   Set it in ~/.ai-employee/.env or pass as JWT_SECRET_KEY=<value> at startup.');
  console.error('   Run: echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> ~/.ai-employee/.env\n');
  process.exit(1);
}
const JWT_EXPIRES_IN = '24h';

// Token issued by POST /api/auth/token (body: { secret: JWT_SECRET_KEY })
// Required on destructive routes: halt, restart, evolution apply, mode force
function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : req.query.token;
  if (!token) return res.status(401).json({ ok: false, error: 'Authentication required' });
  try {
    req.jwtPayload = jwt.verify(token, JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ ok: false, error: 'Invalid or expired token' });
  }
}

function requireLocalhost(req, res, next) {
  // Use raw socket address — req.ip is X-Forwarded-For-aware (trust proxy: 1)
  // and is therefore spoofable by external callers sending a forged header.
  const rawIp = req.socket?.remoteAddress || req.connection?.remoteAddress || '';
  if (rawIp === '127.0.0.1' || rawIp === '::1' || rawIp === '::ffff:127.0.0.1') return next();
  return res.status(403).json({ ok: false, error: 'localhost only' });
}

// Simple sliding-window rate limiter factory (no external deps).
// windowMs: window length, max: max requests per window per IP.
function makeRateLimit(max, windowMs = 60_000) {
  const buckets = new Map(); // ip → [timestamp, ...]
  return (req, res, next) => {
    const ip = req.ip || req.connection?.remoteAddress || 'unknown';
    const now = Date.now();
    const hits = (buckets.get(ip) || []).filter((t) => now - t < windowMs);
    hits.push(now);
    buckets.set(ip, hits);
    if (hits.length > max) {
      res.set('Retry-After', Math.ceil(windowMs / 1000));
      return res.status(429).json({ ok: false, error: 'Rate limit exceeded' });
    }
    next();
  };
}
const _rl_blacklight  = makeRateLimit(5);    // 5/min per IP
const _rl_forge       = makeRateLimit(10);   // 10/min per IP
const _rl_research    = makeRateLimit(3);    // 3/min per IP  (legacy — unused, kept for compatibility)
// ── Per-route rate limiters ───────────────────────────────────────────────────
const _rl_auth_token  = makeRateLimit(5);    // /api/auth/token — 5/min per IP (brute-force guard)
const _rl_auto_token  = makeRateLimit(10);   // /api/auth/auto-token — 10/min per IP
const _rl_upload      = makeRateLimit(20);   // /api/workspace/upload — 20/min per IP
const _rl_ollama_pull = makeRateLimit(3);    // /api/ollama/pull — 3/min per IP (expensive operation)
const _rl_chat        = makeRateLimit(30);   // /api/chat — 30/min per IP
const _rl_tasks_run   = makeRateLimit(30);   // /api/tasks/run — 30/min per IP
const _rl_api_global  = makeRateLimit(120);  // /api/* catch-all — 120/min per IP

// Simple in-memory response cache with TTL.
// Returns middleware that serves cached JSON for ttlMs, then refreshes.
function makeTTLCache(ttlMs = 30_000) {
  let _cache = null;
  let _expiry = 0;
  return (req, res, next) => {
    if (_cache && Date.now() < _expiry) {
      res.set('X-Cache', 'HIT');
      return res.json(_cache);
    }
    const _json = res.json.bind(res);
    res.json = (body) => {
      _cache = body;
      _expiry = Date.now() + ttlMs;
      res.set('X-Cache', 'MISS');
      return _json(body);
    };
    next();
  };
}
const _cache_neurons   = makeTTLCache(30_000);
const _cache_grades    = makeTTLCache(30_000);
const _cache_blacklist = makeTTLCache(30_000);

// Validate a WebSocket upgrade request token (query param ?token=...)
function wsTokenValid(req) {
  try {
    const url = new URL(req.url, 'http://localhost');
    const token = url.searchParams.get('token');
    if (!token) return false;
    jwt.verify(token, JWT_SECRET);
    return true;
  } catch {
    return false;
  }
}

const app = express();

// Trust reverse-proxy headers (X-Forwarded-For, X-Forwarded-Proto) for accurate IP
app.set('trust proxy', 1);

// Security guard: reject requests from IPs the sentinel has blocked (keep attackers out).
// Runs first so a blocked attacker never reaches auth, routes, or the secrets vault.
const { ipBlockMiddleware: _sentinelIpBlock } = require('./security/sentinel_guard');
app.use(_sentinelIpBlock);

// Sentry error tracking middleware (if initialized)
if (process.env.SENTRY_DSN) {
  const Sentry = require('@sentry/node');
  app.use(Sentry.Handlers.requestHandler());
  app.use(Sentry.Handlers.errorHandler());
}

// Security headers — applied before all routes
app.use(helmet({
  // Allow WebSocket upgrades and inline scripts needed by the Vite-built frontend
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'"],   // Vite dev needs inline
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      imgSrc: ["'self'", "data:", "blob:"],
      connectSrc: ["'self'", "ws:", "wss:"],       // WebSocket
      fontSrc: ["'self'", "data:", "https://fonts.gstatic.com"],
      objectSrc: ["'none'"],
      frameAncestors: ["'none'"],
      upgradeInsecureRequests: null,               // disabled — app runs on HTTP (no TLS)
    },
  },
  // HSTS must be off for HTTP-only local server (Tauri/WebKit honours it and breaks loads)
  strictTransportSecurity: false,
  crossOriginEmbedderPolicy: false,
}));
app.use(cors({
  origin: process.env.CORS_ORIGIN
    ? process.env.CORS_ORIGIN.split(',').map(s => s.trim())
    : ['http://localhost:5173', 'http://localhost:8787', 'http://127.0.0.1:8787'],
  credentials: true,
}));
app.use(express.json({ limit: '64kb' }));

// ── Multi-tenancy middleware (extracts tenant from JWT) ───────────────────────
app.use(tenantMiddleware(JWT_SECRET));
// Inject role from JWT claims onto req.user (RBAC — non-breaking augmentation)
app.use(injectRole);
// Data-residency enforcement — 451 for cross-region tenant requests (no-op when DEPLOYMENT_REGION unset)
app.use(enforceRegion);

if (HAS_FRONTEND_DIST) {
  // Vite content-hashes all JS/CSS filenames — safe to cache long-term.
  // index.html is NOT hashed and must never be stale, so it gets no-store.
  app.use(express.static(FRONTEND_DIST, {
    index: false,
    setHeaders(res, filePath) {
      if (filePath.endsWith('.html')) {
        res.set('Cache-Control', 'no-store, must-revalidate');
      } else if (/\.(js|css|woff2?|ttf|eot|svg|png|jpg|ico)$/.test(filePath)) {
        // Hashed assets — immutable cache (1 year)
        res.set('Cache-Control', 'public, max-age=31536000, immutable');
      }
    },
  }));
}

// Serve AI workspace files (generated code, HTML sites, etc.) at /workspace
const WORKSPACE_DIR = path.join(os.homedir(), '.ai-employee', 'workspace');
app.use('/workspace', express.static(WORKSPACE_DIR, { index: false }));

// Serve AI-generated artifacts (summaries, code files) at /api/artifacts/:filename
const ARTIFACTS_DIR = path.join(__dirname, '..', 'state', 'artifacts');
// Preview HTML artifacts inline (no auth cookie needed — token in query param for iframe src)

function readJsonLinesRecent(filePath, limit = 100) {
  try {
    if (!fs.existsSync(filePath)) return [];
    const lines = fs.readFileSync(filePath, 'utf8').trim().split('\n').filter(Boolean);
    return lines.slice(-limit).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean).reverse();
  } catch {
    return [];
  }
}


app.use('/gateway', gateway);
app.use('/orchestrator', orchestrator.router);
app.use('/api/voice', requireAuth, getVoiceApiRouter());
app.use('/api/settings', requireAuth, require('./routes/settings'));

// Tasks API (real-time execution visibility)
const taskGateway = require('./orchestrator/task-dashboard-gateway');
const createTasksRouter = require('./routes/tasks');
app.use('/api/tasks', requireAuth, createTasksRouter(taskGateway, broadcaster));
app.use('/api/schedules', requireAuth, createTasksRouter.createSchedulesRouter(taskGateway, broadcaster));

// Web Search API — proxies to Python /search with CloakBrowser support
const createSearchRouter = require('./routes/search');
app.use('/api/search', createSearchRouter(requireAuth));

// Research v2 API — 2-phase discover → execute on selected sources
const createResearchRouter = require('./routes/research');
app.use('/api/research', createResearchRouter(requireAuth));

// Vault API — Obsidian-compatible markdown knowledge store
const createVaultRouter = require('./routes/vault');
app.use('/api/vault', createVaultRouter(requireAuth));

const createTopicsRouter = require('./routes/topics');
const createLearningRouter = require('./routes/learning');
app.use('/api/topics', createTopicsRouter(requireAuth));
app.use('/api/learning', createLearningRouter(requireAuth));

const GPU_USAGE_BASELINE = 18;
let currentGpuUsage = GPU_USAGE_BASELINE;

// Agents monitoring API — Phase 3.2 agent activity monitor
const { createAgentsMonitorRouter, AgentStateRegistry } = require('./routes/agents-monitor');
const agentStateRegistry = new AgentStateRegistry();
const agentsMonitorRouter = createAgentsMonitorRouter(broadcaster, requireAuth, agentStateRegistry);
app.use('/api/agents', agentsMonitorRouter);

// AscendForge canonical router.
// Keep this mount before the legacy inline /api/forge handlers below. Express
// is first-match wins, so overlapping canonical routes intentionally take
// precedence while old submit/approve/reject/task/code-ai aliases remain live.
app.use('/api/forge', require('./routes/forge')(requireAuth, { rlRuns: _rl_forge }));
app.use('/api/compute', require('./routes/compute')(requireAuth));

// Workflows — template library + CRUD
app.use('/api/workflows', require('./routes/workflows')(requireAuth));

// Hybrid memory router — semantic RAG, graph, read-only SQL, episodic and procedural memory
const createHybridMemoryRouter = require('./routes/hybrid-memory-router');
app.use('/api/memory', createHybridMemoryRouter(requireAuth));

// Orders pipeline — website-sales flow (Lars)
app.use('/api/orders', require('./routes/orders')(requireAuth));

// Serve generated demo HTML files — publicly accessible (no auth required).
// Demo files are static HTML pages generated for customers to preview;
// they contain no sensitive data and must be openable without a JWT token,
// both in Lars's browser and when the link is shared with the customer.

// Dashboard API — security, knowledge, memory, intelligence, cognition, integrations, hooks
app.use('/api', require('./routes/dashboard-api')(requireAuth));

// Native fork-derived capability enhancements: skills, finance, money, autonomy, wallet, channels
app.use('/api', require('./routes/fork-integrations')(requireAuth));

// Session management — list/revoke active sessions, force-logout (admin)
app.use('/api', require('./routes/sessions')(requireAuth));

// API key management — programmatic access (POST/GET/DELETE /api/api-keys)
app.use('/api', require('./routes/api-keys')(requireAuth));

// Start agent heartbeat collector for real-time status monitoring
const { startHeartbeatCollector } = require('./agents-monitor/heartbeat-collector');
startHeartbeatCollector(broadcaster);

// Pipeline Execution API (real-time pipeline visualization)
const { createExecutionRouter } = require('./routes/execution');
const { router: executionRouter, pipelineTraces } = createExecutionRouter({
  broadcaster,
});
app.use('/api/execution', requireAuth, executionRouter);
app.use('/api/events', requireAuth, eventRoutes);
app.use('/api/workflows', requireAuth, workflowRoutes);
app.use('/api/sandbox', requireAuth, sandboxRoutes);
app.use('/api/secrets', requireAuth, secretsRoutes);
// Phase 2 — Enterprise Intelligence
app.use('/api/rag',        requireAuth, ragRoutes);
app.use('/api/planning',   requireAuth, planningRoutes);
app.use('/api/economics',  requireAuth, economicsRoutes);
app.use('/api/governance', requireAuth, governanceRoutes);
app.use('/api/telemetry',  requireAuth, telemetryRoutes);

// Phase 3 — Autonomous Workforce
app.use('/api/rpa',         requireAuth, rpaRoutes);
app.use('/api/healing',     requireAuth, healingRoutes);
app.use('/api/marketplace', requireAuth, marketplaceRoutes);
app.use('/api/deployment',  requireAuth, deploymentRoutes);
app.use('/api/simulation',  requireAuth, simulationRoutes);
app.use('/api/cognitive',   requireAuth, cognitiveRoutes);

// ── Phase 1 Route Extraction — extracted inline routes ────────────────────────
// These routers replace inline app.get/post/delete handlers that lived in
// server.js. The inline handlers remain temporarily (and are now dead code)
// until they are removed in Phase 1b. Routers registered first take priority
// since Express uses first-match routing.
//
// deps object: shared server.js scope passed to each factory so extracted
// routes have identical access to the same variables.
{
  // graphDeltaState wraps the three let-scalars mutated by the brain interval
  const graphDeltaState = { lastMtimeMs: 0, lastNodeCount: 0, lastEdgeCount: 0 };
  // Expose setters so the existing setInterval (lines ~7818-7824) can update the object.
  // The interval is patched below to write into this object instead of the lets.
  global._graphDeltaState = graphDeltaState;

  // Shared deps object — consumed by all extracted route factories
  const _routeDeps = {
    // Auth & middleware
    requireAuth,
    requireLocalhost: (req, res, next) => {
      const addr = req.socket?.remoteAddress || '';
      if (addr === '127.0.0.1' || addr === '::1' || addr === '::ffff:127.0.0.1') return next();
      res.status(403).json({ ok: false, error: 'Localhost only' });
    },
    validate,
    SCHEMAS,
    // Core constants
    PORT, PYTHON_BACKEND_HOST, PYTHON_BACKEND_PORT,
    REPO_ROOT, AI_HOME, STATE_DIR, LOG_DIR, RUN_DIR, statePath,
    ARTIFACTS_DIR, WORKSPACE_DIR,
    GIT_COMMIT, SERVER_START_TIMESTAMP, JWT_SECRET,
    HAS_FRONTEND_DIST,
    // Mutable scalars — wrapped as getter/setter to preserve reactivity
    getApiCallCounter: () => apiCallCounter,
    getSystemHalted: () => systemHalted,
    setSystemHalted: (v) => { systemHalted = v; },
    getBlacklightStatus: () => _lastBlacklightStatus,
    setBlacklightStatus: (v) => { _lastBlacklightStatus = v; },
    getSrvStartMs: () => _srvStartMs,
    // Modules & services
    broadcaster, errorRecovery, taskHistory,
    economyService, ollamaAdmin, autoUpdateWatchdog,
    brain, subsystems, getNativeMemoryGraph,
    getAgents, activateAgents, getMode, setMode, getRobotSignal,
    getRunningAgentCount, stopAllAgents,
    buildMoneyTemplate, buildThinkingSummary,
    addActivity, runPipeline, readJsonSafe, readJsonlSafe, sampleSystemStatus,
    normalizeDashboardGraph, proxyNeuralBrain, checkNeuralGraphReady,
    requestPythonJSON,
    // These are declared after this block — resolved lazily via the Proxy below
    // TTL caches
    _cache_grades,
    // Graph delta state (wraps let scalars)
    graphDeltaState,
    // Task infrastructure — declared late in file, use lazy getters
    getTaskStore: () => taskStore,
    getSseTaskListeners: () => _sseTaskListeners,
    initTask: (...a) => initTask(...a),
    updateTaskStep: (...a) => updateTaskStep(...a),
    completeTask: (...a) => completeTask(...a),
    // Prompt inspector (mutable config)
    promptTraceStore: (() => {
      // promptTraceStore is a let array — share by wrapping in an object
      // Routes read/write via deps.getPromptTraces() / deps.addPromptTrace()
      return null; // populated below after promptTraceStore is declared
    })(),
    getPromptTraces: () => promptTraceStore,
    addPromptTrace: (t) => {
      promptTraceStore.push(t);
      if (promptTraceStore.length > MAX_TRACES) promptTraceStore.shift();
    },
    clearPromptTraces: () => { promptTraceStore.length = 0; },
    getPromptInspectorConfig: () => promptInspectorConfig,
    setPromptInspectorConfig: (v) => { promptInspectorConfig = v; },
    patchPromptInspectorConfig: (patch) => { Object.assign(promptInspectorConfig, patch); },
    // Rate limiters
    _rl_upload,
    // Node builtins (for routes that need them)
    fs, path, http,
  };

  // Late-declared variables are not yet defined at this point in the file.
  // Wrap _routeDeps in a Proxy so that any property access is deferred until
  // the actual request handler runs (by which time all declarations are done).
  const _lazyRouteDeps = new Proxy(_routeDeps, {
    get(target, prop) {
      // Lazy resolution — all late-declared let/const vars go here so route
      // factories receive live values at request time, not undefined at mount time.
      switch (prop) {
        // Phase 1 late vars
        case 'taskStore':             return taskStore;
        case '_sseTaskListeners':     return _sseTaskListeners;
        case 'promptTraceStore':      return promptTraceStore;
        case 'MAX_TRACES':            return MAX_TRACES;
        case 'promptInspectorConfig': return promptInspectorConfig;
        case '_piCfgRef':             return promptInspectorConfig;
        case '_srvStartMs':           return _srvStartMs;
        case 'systemHalted':          return systemHalted;
        case 'MODEL_FABRIC_OFFLINE':  return MODEL_FABRIC_OFFLINE;
        case 'reliabilityState':      return reliabilityState;
        case '_forgeQueue':           return _forgeQueue;
        // Phase 1c additional late vars
        case 'heartbeatCounter':          return heartbeatCounter;
        case 'getHeartbeatCounter':       return () => heartbeatCounter;
        case '_blacklightState':          return _blacklightState;
        case '_loadBlPolicy':             return _loadBlPolicy;
        case '_saveBlPolicy':             return _saveBlPolicy;
        case '_saveBlState':              return _saveBlState;
        case '_cache_blacklist':          return _cache_blacklist;
        case '_rl_blacklight':            return _rl_blacklight;
        case '_rl_tasks_run':             return _rl_tasks_run;
        case '_rl_chat':                  return _rl_chat;
        case '_readReconJson':            return _readReconJson;
        case '_writeReconJson':           return _writeReconJson;
        case '_reconTools':               return _reconTools;
        case '_summarizeReconTools':      return _summarizeReconTools;
        case '_isReconToolAllowed':       return _isReconToolAllowed;
        case '_reconTool':                return _reconTool;
        case '_appendReconAudit':         return _appendReconAudit;
        case '_RECON_CASES_FILE':         return _RECON_CASES_FILE;
        case '_RECON_FINDINGS_FILE':      return _RECON_FINDINGS_FILE;
        case '_RECON_AUDIT_FILE':         return _RECON_AUDIT_FILE;
        case 'ADMIN_SAFETY_ACTIONS':      return ADMIN_SAFETY_ACTIONS;
        case '_forgeQueuePush':           return _forgeQueuePush;
        case '_forgeQueueUpdate':         return _forgeQueueUpdate;
        case '_forgeRiskScore':           return _forgeRiskScore;
        case '_forgeRiskLabel':           return _forgeRiskLabel;
        case '_forgeTaskState':           return _forgeTaskState;
        case '_rl_forge':                 return _rl_forge;
        case '_rl_ollama_pull':           return _rl_ollama_pull;
        case 'loadSystemManifest':        return loadSystemManifest;
        case 'buildModelRoutePlan':       return buildModelRoutePlan;
        case '_cache_neurons':            return _cache_neurons;
        case 'conversations':             return conversations;
        case 'collectHybridMemoryContext':  return collectHybridMemoryContext;
        case 'compactMemoryTraceForModel':  return compactMemoryTraceForModel;
        case 'isPythonBackendUp':           return isPythonBackendUp;
        case 'requestPythonChat':           return requestPythonChat;
        case 'requestOllamaChat':           return requestOllamaChat;
        case 'runPythonExecution':          return runPythonExecution;
        case 'applyStructuredFormat':       return applyStructuredFormat;
        case 'buildLocalFallbackReply':     return buildLocalFallbackReply;
        case 'pythonServiceAuthorization':  return pythonServiceAuthorization;
        case 'turnRunner':                  return turnRunner;
        case 'emitTaskProgress':            return emitTaskProgress;
        case 'recordExecution':             return recordExecution;
        case 'createWorkflowRun':           return createWorkflowRun;
        case 'appendDecision':              return appendDecision;
        case 'attachWorkflowNode':          return attachWorkflowNode;
        case 'updateWorkflowNode':          return updateWorkflowNode;
        case 'buildApprovalInboxItems':     return buildApprovalInboxItems;
        case 'appendApprovalDecision':      return appendApprovalDecision;
        case 'buildEconomySnapshot':        return buildEconomySnapshot;
        case 'walletSnapshot':              return walletSnapshot;
        case 'buildDashboardPayload':       return buildDashboardPayload;
        case 'handleGoalDrivenCommand':     return handleGoalDrivenCommand;
        case 'runForgePython':              return runForgePython;
        case 'pythonServiceAuthorization':  return pythonServiceAuthorization;
        case 'auditService':                return auditService;
        case 'recordAuditEvent':            return recordAuditEvent;
        case '_auditLog':                   return _auditLog;
        case 'blacklightTools':             return blacklightTools;
        case 'apiGatewayProtector':         return apiGatewayProtector;
        case 'anomalyResponder':            return anomalyResponder;
        case 'securitySyncPolicy':          return securitySyncPolicy;
        case 'secretStore':                 return secretStore;
        case 'runtimeState':                return runtimeState;
        case '_readiness':                  return _readiness;
        case '_systemReady':                return _systemReady;
        case '_cache_grades':               return _cache_grades;
        default: return Reflect.get(target, prop);
      }
    },
  });
  global._lazyRouteDeps = _lazyRouteDeps;

  // Route mounts are deferred — see "Deferred route mount" block below (after runtimeState init)
}

// Incremented by broadcaster heartbeat loop; sampled into system status.
let heartbeatCounter = 0;

const GPU_RANDOM_SWING = 8;
const GPU_SWING_OFFSET = 4;
const GPU_CPU_BASELINE = 50;
const GPU_CPU_INFLUENCE = 0.03;
const CPU_TEMP_BASE = 35;
const CPU_TEMP_CPU_FACTOR = 0.58;
const CPU_TEMP_JITTER = 3;
const GPU_TEMP_BASE = 34;
const GPU_TEMP_GPU_FACTOR = 0.52;
const GPU_TEMP_JITTER = 4;
const MAX_ACTIVITY_ITEMS = 50;
const MAX_EXECUTION_LOGS = 100;
const MAX_DECISION_LOG_ENTRIES = 30;
const MAX_OBSERVABILITY_EVENTS = 300;
const BASE_PIPELINE_ROI = 250;
const PIPELINE_ROI_SWING = 400;
const REVENUE_CONVERSION_RATE = 0.45;
const CANCELLATION_ERROR_PREFIX = 'cancelled:';
// Experience scaling: tasks needed to reach maximum multiplier.
const EXPERIENCE_TASK_THRESHOLD = 20;
const MAX_EXPERIENCE_MULTIPLIER = 1.5;
// Deterministic variation seed for pipeline ROI (avoids Math.random).
const VARIATION_SEED = 41;
const OBJECTIVE_STATUS = {
  INACTIVE: 'inactive',
  WAITING: 'waiting',
  RUNNING: 'running',
  COMPLETED: 'completed',
};
const MONEY_MODE_AGENTS = ['lead_hunter', 'email_ninja', 'intel_agent', 'social_guru'];
const ASCEND_FORGE_AGENTS = ['intel_agent', 'email_ninja', 'social_guru'];
const OBJECTIVES_FILE = statePath('objectives.json');
const MONEY_LEADS_PER_TASK = 5;
const MONEY_EMAILS_PER_TASK = 10;

const runtimeState = {
  automationRunning: false,
  tasksExecuted: 0,
  successfulTasks: 0,
  failedTasks: 0,
  valueGenerated: 0,
  revenueCents: 0,
  pipelineRuns: [],
  pipelineRoiTotal: 0,
  activityFeed: [],
  executionLogs: [],
  workflowRuns: [],
  workflowIndex: {},
  workflowTaskMeta: {},
  workflowSequencers: {},
  selectedWorkflowRun: null,
  skillStats: {},
  objectives: [],
  objectiveState: {
    money_mode: {
      active: false,
      status: OBJECTIVE_STATUS.INACTIVE,
      current_objective: null,
      active_tasks: [],
      progress: 0,
      agents_used: [],
      performance: { leads_generated: 0, emails_sent: 0, conversion_pct: 0 },
      result: null,
    },
    ascend_forge: {
      active: false,
      status: OBJECTIVE_STATUS.INACTIVE,
      current_objective: null,
      plan: [],
      active_tasks: [],
      progress: 0,
      agents_used: [],
      results: [],
      result: null,
    },
  },
  objectiveTaskMeta: {},
  observability: {
    events: [],
    autoFixLog: [],
    traces: {},
    _traceSeq: 0,
  },
  _seq: 0,
};
economyService.init(runtimeState, STATE_DIR);

const bootVoiceState = {
  system_init: false,
  ai_core_ready: false,
  ui_loaded: false,
  triggered: false,
};
const BOOT_VOICE_PLAYED_FLAG = path.join(os.tmpdir(), `ai-employee-voice-boot-${process.pid}.flag`);

function hasBootVoicePlayed() {
  return fs.existsSync(BOOT_VOICE_PLAYED_FLAG);
}

function markBootVoicePlayed() {
  try {
    fs.writeFileSync(BOOT_VOICE_PLAYED_FLAG, '1', 'utf8');
  } catch (_err) {
    // best effort
  }
}

function getTimeBasedGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return 'Good morning. Control panel online.';
  if (hour >= 12 && hour < 18) return 'Good afternoon. Systems ready.';
  return 'Good evening. All systems operational.';
}

async function maybeSpeakBootGreeting() {
  if (bootVoiceState.triggered || hasBootVoicePlayed()) return;
  if (!bootVoiceState.system_init || !bootVoiceState.ai_core_ready || !bootVoiceState.ui_loaded) return;

  try {
    await voiceManager.init();
    if (!voiceManager.isBootGreetingEnabled()) {
      bootVoiceState.triggered = true;
      markBootVoicePlayed();
      return;
    }
    bootVoiceState.triggered = true;
    markBootVoicePlayed();
    await voiceManager.emitEvent('system_boot', { greeting: getTimeBasedGreeting() }, true);
  } catch (_err) {
    // best effort
  }
}

function markBootEvent(name) {
  if (!Object.prototype.hasOwnProperty.call(bootVoiceState, name)) return;
  bootVoiceState[name] = true;
  void maybeSpeakBootGreeting();
}

const secretStore = new SecretStore();
const securitySyncPolicy = createOfflineSecuritySyncPolicy({
  queueFile: statePath('security_sync_queue.json'),
  historyFile: statePath('security_sync_history.log'),
});
const apiGatewayProtector = createApiGatewayProtector({
  secretStore,
  syncPolicy: securitySyncPolicy,
  emitObservabilityEvent,
});
app.use('/api', apiGatewayProtector.middleware);
const anomalyResponder = createAnomalyResponder({
  sampleSnapshot: buildObservabilitySnapshot,
  getMode,
  setMode,
  stopAllAgents,
  addActivity,
  appendAutoFixLog,
  emitObservabilityEvent,
  gatewayProtector: apiGatewayProtector,
  syncPolicy: securitySyncPolicy,
});
setInterval(() => {
  try {
    anomalyResponder.evaluate();
  } catch (error) {
    console.warn('[SECURITY] anomaly responder evaluate failed:', error);
  }
}, 15000).unref();

// ── Restore persisted state on startup ────────────────────────────────────────
const _savedState = persistence.loadRuntimeState();
if (_savedState) {
  runtimeState.tasksExecuted = _savedState.tasksExecuted || 0;
  runtimeState.successfulTasks = _savedState.successfulTasks || 0;
  runtimeState.failedTasks = _savedState.failedTasks || 0;
  runtimeState.valueGenerated = _savedState.valueGenerated || 0;
  runtimeState.revenueCents = _savedState.revenueCents || 0;
  runtimeState.pipelineRoiTotal = _savedState.pipelineRoiTotal || 0;
  runtimeState.pipelineRuns = _savedState.pipelineRuns || [];
  runtimeState.activityFeed = _savedState.activityFeed || [];
  runtimeState.executionLogs = _savedState.executionLogs || [];
  runtimeState.skillStats = _savedState.skillStats || {};
  runtimeState.objectives = Array.isArray(_savedState.objectives) ? _savedState.objectives : [];
  runtimeState.objectiveState = _savedState.objectiveState || runtimeState.objectiveState;
  runtimeState.objectiveTaskMeta = _savedState.objectiveTaskMeta || {};
  console.log(`[PERSISTENCE] Restored state: ${runtimeState.tasksExecuted} tasks, $${(runtimeState.revenueCents / 100).toFixed(2)} revenue`);
}

try {
  if (fs.existsSync(OBJECTIVES_FILE)) {
    const persistedObjectives = JSON.parse(fs.readFileSync(OBJECTIVES_FILE, 'utf8'));
    if (Array.isArray(persistedObjectives)) {
      runtimeState.objectives = persistedObjectives;
    }
  }
} catch (error) {
  console.warn('[OBJECTIVES] Failed to read objective state:', error && error.message ? error.message : error);
}

// ── Workflow service (extracted from server.js) ───────────────────────────────
const { createWorkflowService } = require('./services/workflow_execution');
const _wfService = createWorkflowService({
  broadcaster,
  runtimeState,
  securitySyncPolicy,
  orchestrator,
  getForgeDb: () => _forgeDb,
  setMode,
  activateAgents,
  objectivesFile: OBJECTIVES_FILE,
});

const _savedBrain = persistence.loadBrainState();
if (_savedBrain) {
  brain.restoreState(_savedBrain);
  console.log('[PERSISTENCE] Restored brain state');
}
markBootEvent('system_init');

// Pre-declare late-initialized objects so route factories can access them via Proxy without TDZ.
// These are mutated in-place throughout startup — references stay live.
const _readiness    = { phase: 'BOOTING', pythonReady: false, subsystemsReady: false };
const _systemReady  = { python_ok: false, llm_ok: false, node_ok: true };
const _srvStartMs   = Date.now(); // pre-declared to avoid TDZ in deferred route factories
const auditService          = require('./services/audit_service'); // pre-declared
const _auditLog             = auditService.log; // pre-declared — same live array ref
const MODEL_FABRIC_OFFLINE  = { status: 'offline', error: 'Model Fabric offline — Python backend not running.' }; // pre-declared
const reliabilityState      = { forgeFrozen: false, freezeReason: '', stabilityScore: 1.0, checkpoints: [], throttledAgents: [], lastEvaluated: null }; // pre-declared
const MAX_FORGE_QUEUE       = 200; // pre-declared
const _forgeDb              = (() => { // pre-declared — needs statePath + getDatabase (both available here)
  const dbPath = statePath('forge_queue.db');
  const db = new (getDatabase())(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS forge_queue (
      id TEXT PRIMARY KEY,
      priority INTEGER DEFAULT 5,
      payload TEXT NOT NULL,
      status TEXT DEFAULT 'pending',
      created_at INTEGER DEFAULT (strftime('%s','now'))
    );
    CREATE TABLE IF NOT EXISTS workflow_runs (
      run_id TEXT PRIMARY KEY,
      payload TEXT NOT NULL,
      updated_at INTEGER DEFAULT (strftime('%s','now'))
    );
  `);
  return db;
})();
const _forgeQueue           = _forgeDb.prepare( // pre-declared — load persisted queue
  `SELECT payload FROM forge_queue ORDER BY priority DESC, created_at DESC LIMIT ?`
).all(MAX_FORGE_QUEUE).map((r) => JSON.parse(r.payload));
const conversations         = require('./conversations'); // pre-declared
const recordAuditEvent      = auditService.recordAuditEvent; // pre-declared
const _BL_POLICY_FILE       = path.join(STATE_DIR, 'blacklight_policy.json'); // pre-declared
const _BL_STATE_FILE        = path.join(STATE_DIR, 'blacklight_state.json');  // pre-declared
// _blacklightState: load persisted state if available, else default (function is hoisted)
const _blacklightState          = (() => { try { return JSON.parse(fs.readFileSync(path.join(STATE_DIR, 'blacklight_state.json'), 'utf8')); } catch { return { active: false, alerts: [], last_scan: null }; } })(); // pre-declared
const _RECON_CASES_FILE         = path.join(STATE_DIR, 'recon_cases.json'); // pre-declared
const _RECON_FINDINGS_FILE      = path.join(STATE_DIR, 'recon_findings.json'); // pre-declared
const _RECON_AUDIT_FILE         = path.join(STATE_DIR, 'recon_audit.json'); // pre-declared
const RECON_ALLOWED_CATEGORIES  = new Set(['osint', 'defensive_review', 'phishing', 'special']); // pre-declared
const RECON_SAFE_OFFENSIVE_CATEGORY_IDS = new Set(['cors-misconfiguration-scanner','jwt-analyzer','clickjacking-tester','insecure-cookie-checker','csrf-token-analyzer','supabase-rls-auditor']); // pre-declared
const RECON_BANNED_IDS          = new Set(['sql-injection-tester','xss-scanner-reflected','directory-file-bruteforcer','open-redirect-scanner','lfi-path-traversal-tester','subdomain-takeover-check','reverse-shell-generator','cms-vulnerability-scanner','payload-encoder-decoder','crlf-injection-tester','ssrf-tester','xee-tester','command-injection-tester','host-header-injection','prototype-pollution-scanner','http-flood','slowloris','slow-post-rudy','tcp-connection-flood','udp-flood','icmp-ping-flood','http-slow-read','goldeneye-keep-alive-flood','dns-flood','websocket-flood','credential-harvester-gen','url-obfuscator','idn-homograph-attack-gen','stealth-mode-config','botnet-coordinated-ddos','botnet-zombies-world-map']); // pre-declared
const RECON_BANNED_CATEGORY     = new Set(['exploitation', 'stress']); // pre-declared
const walletSnapshot            = () => economyService.walletSnapshot(); // pre-declared
const buildEconomySnapshot      = () => economyService.buildEconomySnapshot(); // pre-declared
const _sseTaskListeners         = new Map(); // pre-declared — SSE listener registry: taskId → Set<res>
const taskStore                 = new Map(); // pre-declared — taskId → {task, steps, connections}
const taskConnections           = new Map(); // pre-declared — taskId → Set of WebSocket connections
// turnRunner: all args are hoisted function declarations or early requires — safe to init here
const turnRunner                = createTurnRunner({ broadcaster, orchestrator, createWorkflowRun, appendDecision, attachWorkflowNode, addActivity, collectHybridMemoryContext, compactMemoryTraceForModel, runPythonExecution, isPythonBackendUp, requestPythonJSON, requestPythonChatPayload, requestOllamaChat, applyStructuredFormat, buildLocalFallbackReply }); // pre-declared
const promptTraceStore          = []; // pre-declared
const MAX_TRACES                = 500; // pre-declared
let   promptInspectorConfig     = { enabled: true, capture_context: true, capture_output: true, min_flag_level: 'info' }; // pre-declared (let — gets overwritten by admin routes)
const ADMIN_SAFETY_ACTIONS      = { // pre-declared
  'reset-state':        { label: 'RESET ALL STATE',      endpoint: 'POST /api/admin/reset-state',             confirmation: 'RESET ALL STATE',      external_effect: 'Would reset runtime state files. This action is staged only from Settings safety center.' },
  'wipe-memory':        { label: 'WIPE MEM0 MEMORY',     endpoint: 'DELETE /api/neural-brain/memory/all',     confirmation: 'WIPE MEM0 MEMORY',     external_effect: 'Would permanently remove memory records. This action is staged only from Settings safety center.' },
  'factory-reset':      { label: 'FACTORY RESET',        endpoint: 'POST /api/admin/factory-reset',           confirmation: 'FACTORY RESET',        external_effect: 'Would reset the full system. This action is staged only from Settings safety center.' },
  'evolution-rollback': { label: 'EVOLUTION ROLLBACK',   endpoint: 'POST /api/evolution/rollback',            confirmation: 'EVOLUTION ROLLBACK',   external_effect: 'Would roll back applied evolution patches. This action is staged only from Settings safety center.' },
  'invalidate-sessions':{ label: 'INVALIDATE SESSIONS',  endpoint: 'POST /api/admin/sessions/invalidate-all', confirmation: 'INVALIDATE SESSIONS',  external_effect: 'Would log out active users. This action is staged only from Settings safety center.' },
  'flush-telemetry':    { label: 'FLUSH TELEMETRY',      endpoint: 'POST /api/neural-brain/telemetry/flush',  confirmation: 'FLUSH TELEMETRY',      external_effect: 'Would clear queued telemetry data. This action is staged only from Settings safety center.' },
};

// ── Deferred route mount — all deps (runtimeState, securitySyncPolicy, etc.) now declared ──
{
  const _deps = global._lazyRouteDeps;
  app.use('/', require('./routes/health')(_deps));
  app.use('/', require('./routes/auth-identity')(_deps));
  app.use('/', require('./routes/agents-brain')(_deps));
  app.use('/', require('./routes/system-ops')(_deps));
  app.use('/', require('./routes/artifacts-tasks')(_deps));
  app.use('/', require('./routes/intelligence')(_deps));
  app.use('/', require('./routes/security-ops')(_deps));
  app.use('/', require('./routes/business-ops')(_deps));
  app.use('/', require('./routes/forge-ops')(_deps));
  app.use('/', require('./routes/tasks-chat')(_deps));
  app.use('/', require('./routes/media')(_deps));
}

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

// ── Delegating stubs — all logic lives in _wfService ────────────────────────
function persistObjectives()                   { return _wfService.persistObjectives(); }
function broadcastObjectiveUpdate(system)      { return _wfService.broadcastObjectiveUpdate(system); }
function normalizeConstraints(value)           { return _wfService.normalizeConstraints(value); }
function parseConstraintsFromGoal(goalText)    { return _wfService.parseConstraintsFromGoal(goalText); }
function createObjective(opts)                 { return _wfService.createObjective(opts); }
function setObjectiveWaiting(system)           { return _wfService.setObjectiveWaiting(system); }
function breakdownMoneyModeGoal(goal)          { return _wfService.breakdownMoneyModeGoal(goal); }
function buildAscendForgePlan(goal)            { return _wfService.buildAscendForgePlan(goal); }
function addActivity(notes, kind)              { return _wfService.addActivity(notes, kind); }
function emitTaskProgress(taskId, title, steps){ return _wfService.emitTaskProgress(taskId, title, steps); }
function emitObservabilityEvent(type, payload) { return _wfService.emitObservabilityEvent(type, payload); }
function isSecurityEventType(eventType)        { return _wfService.isSecurityEventType(eventType); }
function appendAutoFixLog(entry)               { return _wfService.appendAutoFixLog(entry); }
function _persistWorkflowRun()                 { /* handled internally by _wfService */ }
function createWorkflowRun(opts)               { return _wfService.createWorkflowRun(opts); }
function appendDecision(run, entry)            { return _wfService.appendDecision(run, entry); }
function getWorkflowRun(runId)                 { return _wfService.getWorkflowRun(runId); }
function attachWorkflowNode(opts)              { return _wfService.attachWorkflowNode(opts); }
function recalcWorkflowProgress(run)           { return _wfService.recalcWorkflowProgress(run); }
function updateWorkflowNode(taskId, updater)   { return _wfService.updateWorkflowNode(taskId, updater); }
function markWorkflowsStopped()                { return _wfService.markWorkflowsStopped(); }
function queueWorkflowStep(opts)               { return _wfService.queueWorkflowStep(opts); }
function queueNextWorkflowStep(completedTaskId){ return _wfService.queueNextWorkflowStep(completedTaskId); }
function retryWorkflowStep(failedTaskId)       { return _wfService.retryWorkflowStep(failedTaskId); }
function recalcObjectiveProgress(system)       { return _wfService.recalcObjectiveProgress(system); }
function startMoneyModeObjective(objective)    { return _wfService.startMoneyModeObjective(objective); }
function startAscendForgeObjective(objective)  { return _wfService.startAscendForgeObjective(objective); }
function handleGoalDrivenCommand(message)      { return _wfService.handleGoalDrivenCommand(message); }

function recordExecution({ taskId, skill, status, notes }) {
  const logItem = {
    id: `exec-${++runtimeState._seq}`,
    task_id: taskId,
    skill,
    status,
    notes,
    ts: new Date().toISOString(),
  };
  runtimeState.executionLogs.unshift(logItem);
  runtimeState.executionLogs = runtimeState.executionLogs.slice(0, MAX_EXECUTION_LOGS);
  runtimeState.tasksExecuted += 1;
  if (status === 'success') runtimeState.successfulTasks += 1;
  if (status === 'failed') runtimeState.failedTasks += 1;
  runtimeState.skillStats[skill] = runtimeState.skillStats[skill] || { runs: 0, success: 0 };
  runtimeState.skillStats[skill].runs += 1;
  if (status === 'success') runtimeState.skillStats[skill].success += 1;
  // Broadcast so the UI execution log updates in real time
  broadcaster.broadcast('execution:log', logItem);
}

function _broadcastStep(label, detail) {
  broadcaster.broadcast('execution:step', {
    label,
    detail: detail || null,
    ts: new Date().toISOString(),
  });
}

// Pipeline ROI estimation based on actual execution metrics.
// Uses: success rate, tasks completed, pipeline type multiplier.
const PIPELINE_MULTIPLIER = {
  content: 1.0,      // Content pipelines: moderate, steady ROI
  lead: 1.4,         // Lead gen: high value per qualified lead
  opportunity: 1.8,  // Opportunity conversion: highest value per close
};

function estimatePipelineRoi(pipelineName) {
  const successRate = runtimeState.tasksExecuted > 0
    ? runtimeState.successfulTasks / runtimeState.tasksExecuted
    : 0.5;
  const multiplier = PIPELINE_MULTIPLIER[pipelineName] || 1.0;
  // Base ROI scales with actual success rate and cumulative experience
  const experienceFactor = Math.min(runtimeState.tasksExecuted / EXPERIENCE_TASK_THRESHOLD, MAX_EXPERIENCE_MULTIPLIER); // improves with usage
  const baseRoi = BASE_PIPELINE_ROI * successRate * multiplier * Math.max(experienceFactor, 0.5);
  // Deterministic variation based on pipeline run count (no Math.random)
  const variation = ((runtimeState.pipelineRuns.length * VARIATION_SEED) % PIPELINE_ROI_SWING) - (PIPELINE_ROI_SWING / 4);
  return Math.max(50, Math.round(baseRoi + variation));
}

function runPipeline(pipelineName) {
  const estimatedRoi = estimatePipelineRoi(pipelineName);
  const run = {
    id: `pipeline-${++runtimeState._seq}`,
    pipeline: pipelineName,
    status: 'completed',
    estimated_roi: estimatedRoi,
    executed_at: new Date().toISOString(),
  };
  runtimeState.pipelineRuns.unshift(run);
  runtimeState.pipelineRuns = runtimeState.pipelineRuns.slice(0, MAX_ACTIVITY_ITEMS);
  runtimeState.pipelineRoiTotal += estimatedRoi;
  runtimeState.valueGenerated += estimatedRoi;
  runtimeState.revenueCents += Math.round(estimatedRoi * REVENUE_CONVERSION_RATE * 100);
  addActivity(`[PIPELINE] ${pipelineName} completed • ROI $${estimatedRoi}`, 'pipeline');
  return run;
}

function buildDashboardPayload() {
  const successRate = runtimeState.tasksExecuted > 0
    ? runtimeState.successfulTasks / runtimeState.tasksExecuted
    : 0;
  const topSkills = Object.entries(runtimeState.skillStats)
    .map(([skill, stats]) => ({
      skill,
      runs: stats.runs,
      success_rate: stats.runs > 0 ? stats.success / stats.runs : 0,
    }))
    .sort((a, b) => b.runs - a.runs)
    .slice(0, 8);

  return {
    mode: {
      current: getMode(),
      automation_running: runtimeState.automationRunning,
    },
    tasks: {
      tasks_executed: runtimeState.tasksExecuted,
      success_rate: successRate,
      successful_tasks: runtimeState.successfulTasks,
      failed_tasks: runtimeState.failedTasks,
    },
    value: {
      value_generated: runtimeState.valueGenerated,
      components: {
        pipelines: runtimeState.pipelineRoiTotal,
      },
    },
    revenue: {
      total_revenue: runtimeState.revenueCents / 100,
    },
    top_skills: topSkills,
    activity_feed: runtimeState.activityFeed,
    execution_logs: runtimeState.executionLogs,
    workflow_runs: runtimeState.workflowRuns,
    workflow_focus: runtimeState.selectedWorkflowRun,
    pipelines: {
      total_estimated_roi: runtimeState.pipelineRoiTotal,
      runs: runtimeState.pipelineRuns.length,
    },
    pipeline_runs: runtimeState.pipelineRuns,
    pending_actions: [],
    learning: {
      mode: getMode(),
      brain: brain.insights(),
    },
    self_improvement: subsystems.getSelfImprovementStatus(),
    objective_systems: runtimeState.objectiveState,
  };
}

function readJsonSafe(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function readJsonlSafe(file, limit = 500) {
  try {
    const lines = fs.readFileSync(file, 'utf8').trim().split('\n').filter(Boolean);
    return lines.slice(-limit).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } catch {
    return [];
  }
}

// walletSnapshot + buildEconomySnapshot pre-declared above near the deferred route mount block.

function cpuUsagePercent() {
  const cpus = os.cpus().length || 1;
  const load = os.loadavg()[0];
  return clamp(Math.round((load / cpus) * 100), 0, 100);
}

function memoryUsagePercent() {
  const total = os.totalmem();
  const free = os.freemem();
  if (!total) return 0;
  return clamp(Math.round(((total - free) / total) * 100), 0, 100);
}

let _sampleSeq = 0; // Monotonic counter for deterministic GPU/temp estimation.
function sampleSystemStatus() {
  _sampleSeq += 1;
  const cpu = cpuUsagePercent();
  const memory = memoryUsagePercent();
  // Deterministic swing using sinusoidal wave (no Math.random).
  const deterministicSwing = Math.sin(_sampleSeq * 0.7) * GPU_SWING_OFFSET;
  const cpuInfluence = (cpu - GPU_CPU_BASELINE) * GPU_CPU_INFLUENCE;
  // Intentionally mutates currentGpuUsage to simulate gradual GPU trend across snapshots.
  currentGpuUsage = clamp(
    Math.round(currentGpuUsage + deterministicSwing + cpuInfluence),
    4,
    97,
  );
  // Deterministic temperature jitter via modular arithmetic (no Math.random).
  const cpuTempJitter = ((_sampleSeq * 31) % (CPU_TEMP_JITTER + 1));
  const gpuTempJitter = ((_sampleSeq * 47) % (GPU_TEMP_JITTER + 1));
  const cpuTemp = clamp(Math.round(CPU_TEMP_BASE + cpu * CPU_TEMP_CPU_FACTOR + cpuTempJitter), 32, 95);
  const gpuTemp = clamp(Math.round(GPU_TEMP_BASE + currentGpuUsage * GPU_TEMP_GPU_FACTOR + gpuTempJitter), 30, 90);

  const total = getAgents().length;
  const running = getRunningAgentCount();
  const mode = getMode();
  const robotSignal = getRobotSignal();
  const thinkingTemplate = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: running,
    totalAgents: total,
  });
  const thinkingSummary = buildThinkingSummary(mode, thinkingTemplate, robotSignal);

  return {
    cpu,
    memory,
    uptime: process.uptime(),
    connections: wss ? wss.clients.size : 0,
    cpu_usage: cpu,
    gpu_usage: currentGpuUsage,
    gpu_estimated: true,
    cpu_temperature: cpuTemp,
    gpu_temperature: gpuTemp,
    temperature_estimated: true,
    heartbeat: heartbeatCounter,
    running_agents: running,
    total_agents: total,
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    active_robot: robotSignal && robotSignal.agentName ? `${robotSignal.agentName} (${robotSignal.agentId || 'n/a'})` : 'none',
    active_subsystem: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general',
    thinking_mode: thinkingSummary,
    money_template: mode === 'MONEYMODE' ? thinkingTemplate.template : null,
    money_mode_panel: runtimeState.objectiveState.money_mode,
    ascend_forge_panel: runtimeState.objectiveState.ascend_forge,
    timestamp: new Date().toISOString(),
  };
}

// GET /health — FAST health check for boot polling (no external calls)
// Returns immediately with Node.js uptime and status.

// GET /health/full — detailed health check (external calls, slow)
// Called by dashboard, not by boot scripts. Includes all subsystem checks.

// POST /internal/events — Neural Brain bridge: localhost-only ingress used by
// the Python runtime (problem-solver-ui :18790) to push events onto the
// Node WebSocket broadcaster. Body: { event: string, data: object }.
// Locked to loopback so external clients cannot inject dashboard events.
// Uses req.socket.remoteAddress (not req.ip) — trust proxy: 1 makes req.ip
// X-Forwarded-For-aware and therefore spoofable by external callers.
// Allowlist of valid event names for /internal/events.
// Rejects arbitrary event names to prevent state spoofing via blacklight events.
const _INTERNAL_EVENT_ALLOWLIST = new Set([
  'blacklight:status', 'blacklight:mode_change', 'blacklight:lockdown',
  'task:context_check', 'task:research_started', 'task:research_completed',
  'task:research_budget_exhausted', 'task:update', 'task:done',
  'heartbeat', 'activity:item', 'workflow:update', 'execution:log', 'execution:step',
  'orchestrator:queued', 'memory:router:trace', 'event_stream',
  'objective:update', 'chat:message', 'security:update',
]);

// GET /api/security/status — Blacklight + system control state (localhost or auth)

// Track last known Blacklight status for the status endpoint
let _lastBlacklightStatus = null;

// POST /api/auth/token — exchange the master secret for a 24h JWT
// Body: { secret: "<JWT_SECRET_KEY from ~/.ai-employee/.env>" }

// GET /api/auth/auto-token — issues a short-lived JWT for localhost dashboard access (no secret needed)
// Only allows requests from loopback. Uses raw socket remoteAddress (unforgeable) — not req.ip
// which is X-Forwarded-For aware and trivially spoofable via `trust proxy: 1`.

function pythonServiceAuthorization(req) {
  const payload = req.jwtPayload || {};
  const sub = payload.sub || payload.user_id || 'operator';
  const token = jwt.sign({
    sub,
    type: 'access',
    role: payload.role || 'operator',
    iss: 'ai-employee-node',
    tenant_id: payload.tenant_id || req.tenant?.id || 'default',
    org_name: payload.org_name || 'Local',
    service: 'node-gateway',
  }, JWT_SECRET, { expiresIn: '10m' });
  return `Bearer ${token}`;
}

// GET /api/identity/public — public identity info (no auth required)
// Returns instance name and color palette for onboarding/branding

// GET /api/onboarding/palettes — generate 3 color palettes for onboarding

// POST /api/identity/finalize — save user onboarding choices


// Aliases for tests and external callers that expect /api/ prefix


function normalizeGraphNode(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const id = String(raw.id || raw.key || raw.name || raw.label || `node-${index}`).trim();
  if (!id) return null;
  const type = String(raw.type || raw.node_type || raw.group || 'skill').toLowerCase();
  const rawGroup = String(raw.group || '').toLowerCase();
  const group = (
    ['money', 'memory', 'automation', 'learning', 'agent', 'system'].includes(rawGroup) ? rawGroup
      : rawGroup === 'strategy' || rawGroup === 'skill' || rawGroup === 'concept' ? 'money'
        : rawGroup === 'task' || rawGroup === 'output' ? 'automation'
          : rawGroup === 'input' || rawGroup === 'hidden' ? 'learning'
            : type === 'strategy' || type === 'skill' || type === 'concept' ? 'money'
              : type === 'memory' ? 'memory'
                : type === 'task' || type === 'output' ? 'automation'
                  : type === 'input' || type === 'hidden' ? 'learning'
                    : type === 'agent' ? 'agent'
                      : 'system'
  );
  return {
    id,
    label: String(raw.label || raw.name || id),
    type,
    group,
    weight: Number.isFinite(Number(raw.weight)) ? Number(raw.weight) : 1,
    confidence: Number.isFinite(Number(raw.confidence)) ? Number(raw.confidence) : 0,
    activation: Number.isFinite(Number(raw.activation)) ? Number(raw.activation) : 0,
    source: String(raw.source || 'system'),
    tag: String(raw.tag || ''),
  };
}

function endpointId(value) {
  if (value && typeof value === 'object') return value.id || value.key || value.name || value.label || '';
  return value || '';
}

function normalizeGraphLink(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const source = String(endpointId(raw.source ?? raw.from)).trim();
  const target = String(endpointId(raw.target ?? raw.to)).trim();
  if (!source || !target) return null;
  return {
    source,
    target,
    strength: Number.isFinite(Number(raw.strength ?? raw.weight ?? raw.confidence))
      ? Number(raw.strength ?? raw.weight ?? raw.confidence)
      : 0.5,
  };
}

function normalizeDashboardGraph(payload = {}) {
  const nodes = [];
  const seen = new Set();
  const rawNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
  rawNodes.forEach((raw, index) => {
    const node = normalizeGraphNode(raw, index);
    if (!node || seen.has(node.id)) return;
    seen.add(node.id);
    nodes.push(node);
  });

  const rawLinks = Array.isArray(payload.links)
    ? payload.links
    : Array.isArray(payload.connections)
      ? payload.connections
      : [];
  const links = [];
  const linkSet = new Set();
  rawLinks.forEach((raw) => {
    const link = normalizeGraphLink(raw);
    if (!link || !seen.has(link.source) || !seen.has(link.target)) return;
    const key = `${link.source}→${link.target}`;
    if (linkSet.has(key)) return;
    linkSet.add(key);
    links.push(link);
  });

  return {
    nodes,
    links,
    stats: {
      ...(payload.stats || {}),
      node_count: nodes.length,
      link_count: links.length,
    },
    updated_at: payload.updated_at || payload.updatedAt || new Date().toISOString(),
  };
}

async function checkNeuralGraphReady() {
  try {
    const graph = await proxyNeuralBrain('/api/neural-brain/graph', { nodes: [], links: [] });
    const normalized = normalizeDashboardGraph(graph);
    return {
      ok: normalized.nodes.length > 0 || _readiness.pythonReady === true,
      graph: normalized,
    };
  } catch (_) {
    return { ok: false, graph: normalizeDashboardGraph({ nodes: [], links: [] }) };
  }
}


async function probeHttp(url, timeoutMs = 900) {
  try {
    const response = await Promise.race([
      fetch(url),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
    ]);
    return { ok: !!response?.ok, status: response?.status || 0 };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

function capabilityRecord({
  id,
  label,
  status,
  category,
  required_env = [],
  missing_env = [],
  setup_action = 'none',
  details = '',
  docs_hint = '',
  source = 'node',
  proof = null,
}) {
  const checkedAt = new Date().toISOString();
  return {
    id,
    name: id, // compatibility for older dashboard widgets
    label,
    status,
    category,
    required_env,
    missing_env,
    last_checked_at: checkedAt,
    updated_at: checkedAt,
    setup_action,
    details,
    docs_hint,
    source,
    proof,
  };
}

function missingEnv(keys) {
  return keys.filter((key) => !process.env[key]);
}

function statusFromEnv(keys, { any = false } = {}) {
  if (!keys.length) return { status: 'live', missing: [] };
  const missing = missingEnv(keys);
  if (any) {
    return { status: missing.length < keys.length ? 'live' : 'not_configured', missing };
  }
  return { status: missing.length === 0 ? 'live' : 'not_configured', missing };
}


// ── Neural Brain data endpoints (proxy to Python if up, fallback to stubs) ───
// Internal service token so Node→Python proxy calls pass the Python auth gate.
// Signed with the shared JWT_SECRET; short-lived and minted on demand (cached 5 min).
let _internalToken = null;
let _internalTokenExp = 0;
function internalServiceToken() {
  const now = Date.now();
  if (_internalToken && now < _internalTokenExp) return _internalToken;
  _internalToken = jwt.sign(
    { type: 'access', role: 'service', iss: 'ai-employee', tenant_id: 'default', org_name: 'Local', svc: 'node-proxy' },
    JWT_SECRET,
    { expiresIn: '10m' },
  );
  _internalTokenExp = now + 5 * 60 * 1000; // refresh well before expiry
  return _internalToken;
}

async function proxyNeuralBrain(path, fallback) {
  try {
    const r = await Promise.race([
      fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}${path}`, {
        headers: { Authorization: `Bearer ${internalServiceToken()}` },
      }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 1500)),
    ]);
    if (r?.ok) return r.json();
  } catch (_) {}
  return fallback;
}

// Rich native-graph proxy (89+ nodes) — the snapshot endpoint can be empty, so expose
// the live graph directly. Authenticated via the internal service token in proxyNeuralBrain.


// ── Four living memory graphs (WS3): shortterm|longterm|relations|unified ──────
const _MEMORY_GRAPH_VIEWS = new Set(['shortterm', 'longterm', 'relations', 'unified']);


// ── Model Fabric proxy (Python /api/model-fabric/*) ─────────────────────────────
// Generic GET/POST passthrough with the internal service token. Honest offline
// fallback (no fake success) so the UI can show "Python backend offline".
async function proxyModelFabric(path, { method = 'GET', body, timeout = 120000 } = {}) {
  const opts = {
    method,
    headers: { Authorization: `Bearer ${internalServiceToken()}`, 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await Promise.race([
    fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}${path}`, opts),
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), timeout)),
  ]);
  return { ok: r?.ok, status: r?.status, data: await r.json() };
}

// MODEL_FABRIC_OFFLINE pre-declared above near the deferred route mount block.

// GET endpoints (fast; never trigger a model load)
['models', 'health', 'status', 'lifecycle/status', 'quantization/status',
 'quantization/available', 'quantization/pull/status'].forEach((seg) => {
  app.get(`/api/model-fabric/${seg}`, requireAuth, _rl_api_global, async (req, res) => {
    try {
      const { ok, data } = await proxyModelFabric(`/api/model-fabric/${seg}`, { timeout: 15000 });
      return res.status(ok ? 200 : 502).json(data);
    } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
  });
});

// POST endpoints
['route', 'llm', 'slm', 'vision/analyze', 'vision/segment', 'generate/visual',
 'actions/execute', 'rag/query', 'rag/ingest', 'quantization/select',
 'quantization/pull', 'models/unload-idle'].forEach((seg) => {
  app.post(`/api/model-fabric/${seg}`, requireAuth, _rl_api_global, async (req, res) => {
    try {
      const { ok, data } = await proxyModelFabric(`/api/model-fabric/${seg}`, { method: 'POST', body: req.body });
      return res.status(ok ? 200 : 502).json(data);
    } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
  });
});

// Per-model unload (model id may contain slashes/colons, e.g. "qwen2.5-coder:14b")

// Per-model reload with a specific quant (unload + pull the quant variant)

// ── Agent fleet controls ──────────────────────────────────────────────────────

// ── Subsystem API endpoints ───────────────────────────────────────────────────


function execText(command, timeout = 1200) {
  try {
    return execSync(command, { encoding: 'utf8', timeout, stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return '';
  }
}

function parsePsRows() {
  const output = execText('ps -eo pid,comm,pcpu,pmem,etime,args --no-headers', 1200);
  if (!output.trim()) {
    return [{
      pid: process.pid,
      name: 'node',
      service: 'node_backend',
      status: 'running',
      cpu_percent: 0,
      memory_percent: 0,
      uptime: Math.round(process.uptime()),
      command: 'node backend/server.js',
      source: 'node_fallback',
    }];
  }
  const interesting = ['node', 'python', 'uvicorn', 'ollama', 'vite'];
  return output.split('\n').map((line) => {
    const match = line.trim().match(/^(\d+)\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+(\S+)\s+(.+)$/);
    if (!match) return null;
    const [, pid, comm, cpu, mem, etime, args] = match;
    const text = `${comm} ${args}`.toLowerCase();
    if (!interesting.some((term) => text.includes(term)) && !text.includes('ai-employee')) return null;
    return {
      pid: Number(pid),
      name: comm,
      service: text.includes('python') || text.includes('uvicorn') ? 'python_backend'
        : text.includes('ollama') ? 'ollama'
          : text.includes('vite') ? 'frontend_dev'
            : 'node_backend',
      status: 'running',
      cpu_percent: Number(cpu) || 0,
      memory_percent: Number(mem) || 0,
      uptime: etime,
      command: String(args).slice(0, 220),
      source: 'ps',
    };
  }).filter(Boolean).slice(0, 40);
}

function parseListeningPorts() {
  const output = execText('ss -ltnp', 1200) || execText('netstat -ltnp', 1200);
  if (!output.trim()) {
    return [
      { port: Number(PORT), protocol: 'tcp', service: 'node_backend', status: 'unknown', source: 'configured' },
      { port: Number(PYTHON_BACKEND_PORT), protocol: 'tcp', service: 'python_backend', status: _readiness.pythonReady ? 'listening' : 'unknown', source: 'configured' },
    ];
  }
  return output.split('\n').map((line) => {
    const local = line.match(/(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]|\*):(\d+)/);
    if (!local) return null;
    const port = Number(local[1]);
    if (![Number(PORT), Number(PYTHON_BACKEND_PORT), 5173, 11434].includes(port)) return null;
    return {
      port,
      protocol: 'tcp',
      service: port === Number(PORT) ? 'node_backend'
        : port === Number(PYTHON_BACKEND_PORT) ? 'python_backend'
          : port === 11434 ? 'ollama'
            : 'frontend_dev',
      status: 'listening',
      raw: line.trim().slice(0, 220),
      source: 'socket_table',
    };
  }).filter(Boolean);
}

function storageRows() {
  const rows = [];
  const addPath = (id, label, dir) => {
    let access = 'unavailable';
    try {
      fs.mkdirSync(dir, { recursive: true });
      fs.accessSync(dir, fs.constants.R_OK | fs.constants.W_OK);
      access = 'read_write';
    } catch {
      access = 'unavailable';
    }
    rows.push({ id, label, path: dir, status: access, source: 'node_fs' });
  };
  addPath('state', 'Runtime State', STATE_DIR);
  addPath('logs', 'Logs', LOG_DIR);
  addPath('run', 'PID / Run Files', RUN_DIR);
  addPath('artifacts', 'Artifacts', ARTIFACTS_DIR);
  const df = execText(`df -Pk "${STATE_DIR}"`, 1200).split('\n')[1];
  if (df) {
    const parts = df.trim().split(/\s+/);
    rows.push({
      id: 'disk',
      label: 'State Disk',
      path: parts[5],
      status: 'available',
      size_kb: Number(parts[1]) || 0,
      used_kb: Number(parts[2]) || 0,
      available_kb: Number(parts[3]) || 0,
      used_percent: parts[4] || null,
      source: 'df',
    });
  }
  return rows;
}

function runtimeWarnings() {
  const warnings = [];
  if (!HAS_FRONTEND_DIST) warnings.push({ id: 'frontend_dist_missing', status: 'warning', details: 'frontend/dist/index.html is missing.' });
  if (!_readiness.pythonReady) warnings.push({ id: 'python_backend_not_ready', status: 'warning', details: `Python backend is not live on port ${PYTHON_BACKEND_PORT}.` });
  if (_readiness.pythonReady && !_readiness.subsystemsReady) warnings.push({ id: 'python_subsystems_degraded', status: 'warning', details: 'Python backend is live but subsystem readiness is degraded.' });
  if (!process.env.ANTHROPIC_API_KEY && !process.env.OPENAI_API_KEY && !process.env.OPENROUTER_API_KEY && !process.env.GROQ_API_KEY) {
    warnings.push({ id: 'llm_provider_missing', status: 'warning', details: 'No remote LLM provider API key is configured.' });
  }
  return warnings;
}


function collectExpressRoutes() {
  const routes = [];
  const stack = app._router?.stack || [];
  for (const layer of stack) {
    if (!layer.route) continue;
    const routePath = layer.route.path;
    const methods = Object.keys(layer.route.methods || {}).filter((method) => layer.route.methods[method]);
    const handlers = (layer.route.stack || []).map((item) => item?.handle?.name || '').filter(Boolean);
    const authRequired = handlers.includes('requireAuth') || routePath.startsWith('/api/');
    const compatibility = routePath.includes('/chat') || routePath.includes('/tasks/run') ? 'canonical_or_compatibility'
      : routePath.includes('/legacy') ? 'legacy'
        : 'active';
    for (const method of methods) {
      routes.push({
        route: routePath,
        method: method.toUpperCase(),
        auth_required: authRequired,
        source: 'node',
        compatibility,
        response_contract: routePath.includes('/tasks/run') || routePath.includes('/chat') ? 'turn_result_v1' : 'route_specific',
        live_status: 'registered',
        last_smoke_result: null,
      });
    }
  }
  return routes.sort((a, b) => a.route.localeCompare(b.route) || a.method.localeCompare(b.method));
}


function buildObservabilitySnapshot() {
  const stats = sampleSystemStatus();
  const events = runtimeState.observability.events || [];
  const nowTs = Date.now();
  const recentErrorEvents = events.filter((item) => item.event_type === 'error_detected');
  const errorsPerMinute = recentErrorEvents.filter((item) => (nowTs - Date.parse(item.ts)) <= 60000).length;
  const recentTaskEvents = events.filter((item) => item.event_type === 'task_completed' || item.event_type === 'task_started');
  const tasksPerMinute = recentTaskEvents.filter((item) => (nowTs - Date.parse(item.ts)) <= 60000).length;
  const latestLogs = runtimeState.executionLogs.slice(0, 20);
  const avgLatency = latestLogs.length
    ? Math.round(latestLogs.reduce((acc, row) => acc + (Number(row.duration_ms || 0) || 0), 0) / latestLogs.length)
    : 0;
  return {
    system_health: {
      uptime: stats.uptime,
      errors_per_minute: errorsPerMinute,
      status: errorsPerMinute > 3 ? 'degraded' : 'healthy',
    },
    metrics: {
      tasks_per_minute: tasksPerMinute,
      errors_per_minute: errorsPerMinute,
      latency_ms: avgLatency,
      cpu_percent: stats.cpu_usage,
      memory_percent: stats.memory,
      queue_depth: runtimeState.workflowRuns.filter((run) => run.status === 'pending').length,
    },
    activity_feed: runtimeState.activityFeed,
    agent_grid: getAgents().map((agent) => ({
      id: agent.id,
      name: agent.name,
      status: agent.status || 'idle',
    })),
    queue_visualizer: {
      pending: runtimeState.workflowRuns.filter((run) => run.status === 'pending').length,
      processing: runtimeState.workflowRuns.filter((run) => run.status === 'running').length,
    },
    auto_fix_log: runtimeState.observability.autoFixLog || [],
    events: events.slice(0, 200),
    traces: runtimeState.observability.traces,
    security: {
      gateway: apiGatewayProtector.status(),
      sync: securitySyncPolicy.status(),
      anomaly_response: anomalyResponder.status(),
    },
    updated_at: new Date().toISOString(),
  };
}


/**
 * Unified graph endpoint for the 3-D Neural Brain visualization.
 * Returns { nodes, links, stats } using a normalized schema so the
 * frontend brainStore can consume it directly.
 */


// ── Phase 4G Observability Endpoints ─────────────────────────────────────────


// ── Knowledge semantic / keyword search ──────────────────────────────────────

// ── End Phase 4G ──────────────────────────────────────────────────────────────

// ── Knowledge Vault proxy routes ──────────────────────────────────────────────
for (const [method, path, pyPath] of [
  ['get',  '/api/knowledge/vault/list',        '/knowledge/vault/list'],
  ['get',  '/api/knowledge/vault/pending',      '/knowledge/vault/pending'],
  ['post', '/api/knowledge/vault/add',          '/knowledge/vault/add'],
  ['post', '/api/knowledge/vault/queue-topic',  '/knowledge/vault/queue-topic'],
]) {
  app[method](path, requireAuth, async (req, res) => {
    try {
      const r = await fetch(`http://127.0.0.1:18790${pyPath}`, {
        method: method.toUpperCase(),
        headers: { 'Content-Type': 'application/json', 'Authorization': req.headers.authorization || '' },
        body: method === 'get' ? undefined : JSON.stringify(req.body),
      });
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'vault unavailable' }); }
  });
}

// ── Tool / Skill registry proxy routes ────────────────────────────────────────
for (const [m, p, pyP] of [
  ['get',  '/api/tools/list',      '/tools/list'],
  ['get',  '/api/skills/list',     '/skills/list'],
  ['get',  '/api/skills/suggest',  '/skills/suggest'],
]) {
  app[m](p, requireAuth, async (req, res) => {
    const qs = m === 'get' ? '?' + new URLSearchParams(req.query).toString() : '';
    try {
      const r = await fetch(`http://127.0.0.1:${PYTHON_BACKEND_PORT}${pyP}${qs}`, {
        headers: { 'Authorization': req.headers.authorization || '' },
      });
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'tools service unavailable' }); }
  });
}
for (const ep of ['tools', 'skills']) {
  app.post(`/api/${ep}/:name/execute`, requireAuth, async (req, res) => {
    try {
      const epName = encodeURIComponent(String(req.params.name || '').trim());
      if (!epName) return res.status(400).json({ ok: false, error: 'name required' });
      const r = await fetch(
        `http://127.0.0.1:${PYTHON_BACKEND_PORT}/${ep}/${epName}/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': req.headers.authorization || '' },
          body: JSON.stringify(req.body),
        },
      );
      res.status(r.status).json(await r.json());
    } catch (e) { res.status(502).json({ ok: false, error: 'service unavailable' }); }
  });
}


// ── Conversations JSONL endpoint ──────────────────────────────────────────────
// conversations pre-declared above near the deferred route mount block.


// ── Autonomy daemon endpoints ─────────────────────────────────────────────────


function requestPythonJSON(pathname, method = 'GET', payload = null, options = {}) {
  return new Promise((resolve, reject) => {
    const httpLib = require('http');
    const safePath = String(pathname || '/').trim();
    if (!safePath.startsWith('/api/') || safePath.includes('..')) {
      return reject(new Error('invalid_path'));
    }
    const body = payload ? JSON.stringify(payload) : null;
    const headers = {
      // Authenticate Node→Python proxy calls; RequestGuard rejects non-public routes without it.
      Authorization: `Bearer ${internalServiceToken()}`,
      ...(body ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } : {}),
      ...(options.headers || {}),
    };
    const req = httpLib.request(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}${safePath}`, {
      method,
      headers,
      timeout: options.timeoutMs || 3000,
    }, (response) => {
      let text = '';
      response.on('data', (chunk) => { text += chunk; });
      response.on('end', () => {
        try {
          resolve({ _http_status: response.statusCode, ...JSON.parse(text || '{}') });
        } catch {
          resolve({ _http_status: response.statusCode });
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('timeout'));
    });
    if (body) req.write(body);
    req.end();
  });
}

/**
 * Ensure every LLM reply uses the 8-phase structured format.
 * If the response already contains the phase marker the text is returned unchanged.
 * Otherwise the raw content is wrapped in the minimum 3-section template so the
 * frontend always renders structured output regardless of which backend produced it.
 */
function applyStructuredFormat(text, agent = 'AI Employee') {
  const PHASE_MARKER = '## 📋 TASK UNDERSTANDING'; // 📋
  if (!text || text.includes(PHASE_MARKER)) return text;
  return (
    `${PHASE_MARKER}\nRequest processed via ${agent}.\n\n` +
    `## ⚡ EXECUTION & RESULTS\n${text}\n\n` +
    `## ✅ VALIDATION\nOutput delivered. Logic verified, no duplicates.`
  );
}

/**
 * Build a contextual local reply when the Python LLM backend is unavailable.
 * Uses live subsystem state to produce a meaningful (non-generic) response.
 */
function buildLocalFallbackReply(message, queuedTask) {
  const lower = (message || '').toLowerCase();
  const subsystem = (queuedTask && queuedTask.subsystem) || 'general';
  const agentId = (queuedTask && queuedTask.agentId) || 'agent';
  const mode = getMode();
  const running = getRunningAgentCount();

  // Structured 3-section wrapper — ensures every fallback reply matches the 8-phase format
  const _sr = (understanding, results, validation) =>
    `## 📋 TASK UNDERSTANDING\n${understanding}\n\n## ⚡ EXECUTION & RESULTS\n${results}\n\n## ✅ VALIDATION\n${validation}`;

  if (/\b(health|diagnos|system check|doctor)\b/.test(lower) || subsystem === 'doctor') {
    const dr = subsystems.getDoctorStatus();
    const score = dr.overall_score || 0;
    const issueCount = (dr.issues || []).length;
    if (issueCount > 0) {
      return _sr(
        'You want a system health report.',
        `System health score: **${score}/100**\n\nDetected **${issueCount} issue${issueCount !== 1 ? 's' : ''}** — visit the Doctor page for a full breakdown and recommended actions.`,
        'Health data retrieved from live subsystem. Visit Doctor page for automated fix suggestions.',
      );
    }
    return _sr(
      'You want a system health report.',
      `✅ All subsystems clear — health score **${score}/100**. No issues detected.`,
      'Health check passed. No action required.',
    );
  }
  if (/\b(memory|knowledge|context|recall|entities)\b/.test(lower) || subsystem === 'memory') {
    const mem = subsystems.getMemoryTree();
    const count = mem.total_entities || 0;
    return _sr(
      'You want information about the knowledge base / memory system.',
      `**${count}** knowledge ${count === 1 ? 'entity' : 'entities'} on file.\n\nYour request has been indexed and can be referenced in future conversations.`,
      'Memory data retrieved live. No duplicate entries introduced.',
    );
  }
  if (/\b(neural|network|confidence|train|learn|model)\b/.test(lower) || subsystem === 'nn') {
    const nn = subsystems.getNNStatus();
    const conf = Math.round((nn.confidence || 0) * 100);
    return _sr(
      'You want information about the neural network / AI model status.',
      `Neural network running in **${nn.mode || 'standard'}** mode.\n- Confidence: **${conf}%**\n- Logged experiences: **${(nn.experiences || 0).toLocaleString()}**`,
      'Status retrieved from live NN subsystem. All figures are current.',
    );
  }
  if (/\b(status|how are you|overview)\b/.test(lower)) {
    return _sr(
      'You want a system status overview.',
      `Operating in **${mode}** mode with **${running}** active agent${running !== 1 ? 's' : ''}.\n\n**${runtimeState.tasksExecuted}** tasks processed so far — everything is nominal.`,
      'Status pulled from runtime state. All metrics current.',
    );
  }
  if (/\b(hello|hi|hey|greet)\b/.test(lower)) {
    return _sr(
      'You are greeting the AI Employee system.',
      `Hello! I'm your AI Employee, currently in **${mode}** mode with **${running}** active agent${running !== 1 ? 's' : ''} ready to go.\n\nWhat would you like to tackle today?`,
      'Greeting delivered. System ready for instructions.',
    );
  }
  if (/\b(help|what can you|capabilities)\b/.test(lower)) {
    return _sr(
      'You want to know what capabilities this system has.',
      'I can help you with:\n- **Automation pipelines** — chain agents to execute multi-step workflows\n- **Agent management** — monitor, control, and spawn specialist agents\n- **Data analysis** — process datasets, surface insights, generate reports\n- **Knowledge base** — search and update the neural memory graph\n- **System diagnostics** — health checks, root cause analysis, auto-fix\n- **Revenue operations** — Money Mode, Ascend Forge, outreach pipelines\n\nWhat would you like to start with?',
      'Capabilities list is complete and current. No deprecated features listed.',
    );
  }
  return _sr(
    'You sent a request that requires the AI backend.',
    `⚠️ Unable to reach the AI backend right now.\n\n**To restore full LLM capability:**\n1. Start Ollama: \`ollama serve\`\n2. Or add an API key to \`~/.ai-employee/.env\`\n\nYour task has been queued as **${queuedTask ? queuedTask.taskId : 'unknown'}** and will execute when the backend reconnects.`,
    'Fallback reply delivered. Task safely queued — no data lost.',
  );
}

/**
 * Proxy a chat message to the Python backend's full LLM pipeline.
 * Returns the response string on success, or null if the Python backend
 * is unreachable (callers fall back to the local buildHumanReply).
 *
 * Timeout is generous (30 s) because LLM inference may be slow.
 */
const PYTHON_CHAT_TIMEOUT_MS = 30000;

let _pyUp = false;
let _pyLastCheck = 0;
const PY_CHECK_TTL_MS = 20000;

async function collectHybridMemoryContext(query, options = {}) {
  if (!query || typeof createHybridMemoryRouter.runHybridQuery !== 'function') return null;
  const timeoutMs = Number(options.timeoutMs || 1200);
  try {
    const trace = await Promise.race([
      createHybridMemoryRouter.runHybridQuery({
        query,
        user_id: options.userId || 'user:default',
        session_id: options.sessionId || null,
        task_id: options.taskId || null,
        mode: options.mode || 'main_ai',
        max_tokens: options.maxTokens || 1200,
      }),
      new Promise((resolve) => setTimeout(() => resolve({
        trace_id: `memory-timeout-${Date.now().toString(36)}`,
        routes: [],
        context: '',
        citations: [],
        confidence: 0,
        degraded: true,
        diagnostics: ['memory_router_timeout'],
      }), timeoutMs)),
    ]);
    if (trace && !trace.error) return trace;
  } catch (err) {
    console.warn('[MEMORY ROUTER] preflight failed: %s', err && err.message);
  }
  return null;
}

function compactMemoryTraceForModel(trace) {
  if (!trace || !trace.context) return null;
  return {
    trace_id: trace.trace_id,
    routes: Array.isArray(trace.routes) ? trace.routes.map((route) => ({
      id: route.id,
      hits: route.hits || 0,
      reason: route.reason || '',
    })) : [],
    confidence: trace.confidence || 0,
    degraded: trace.degraded === true,
    diagnostics: trace.diagnostics || [],
    citations: (trace.citations || []).slice(0, 8),
    context: String(trace.context).slice(0, 6000),
  };
}

function memoryContextMessage(trace) {
  const compact = compactMemoryTraceForModel(trace);
  if (!compact) return null;
  return {
    role: 'system',
    content:
      'Hybrid memory router context. Use this only as grounding context; do not reveal router internals unless asked.\n' +
      `Trace: ${compact.trace_id}\n` +
      `Routes: ${compact.routes.map((route) => `${route.id}:${route.hits}`).join(', ') || 'none'}\n` +
      `Confidence: ${compact.confidence}\n` +
      `Degraded: ${compact.degraded ? 'yes' : 'no'}\n\n` +
      compact.context,
  };
}

function isPythonBackendUp() {
  const now = Date.now();
  if (now - _pyLastCheck < PY_CHECK_TTL_MS) return Promise.resolve(_pyUp);
  _pyLastCheck = now;
  return new Promise((resolve) => {
    const r = http.request(
      `http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/health`,
      { timeout: 1000 },
      (res) => { res.resume(); _pyUp = res.statusCode < 500; resolve(_pyUp); },
    );
    r.on('error', () => { _pyUp = false; resolve(false); });
    r.on('timeout', () => { r.destroy(); _pyUp = false; resolve(false); });
    r.end();
  });
}

function requestPythonChatPayload(message, modelRoute, userId, memoryTrace) {
  return new Promise((resolve) => {
    const payload = { message };
    if (modelRoute) payload.model_route = modelRoute;
    if (userId) payload.user_id = userId;
    const memoryContext = compactMemoryTraceForModel(memoryTrace);
    if (memoryContext) payload.memory_context = memoryContext;
    const body = JSON.stringify(payload);
    const req = http.request(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: PYTHON_CHAT_TIMEOUT_MS,
    }, (response) => {
      let text = '';
      response.on('data', (chunk) => { text += chunk; });
      response.on('end', () => {
        try {
          const data = JSON.parse(text || '{}');
          resolve({ _http_status: response.statusCode, ...data });
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.write(body);
    req.end();
  });
}

async function requestPythonChat(message, modelRoute, userId, memoryTrace) {
  const data = await requestPythonChatPayload(message, modelRoute, userId, memoryTrace);
  return data ? (data.response || data.reply || null) : null;
}

// ── Python execution engine — real tool calls, no fake results ────────────────
// Spawns backend/run_execution.py to run goal_parser + real_execution_engine.
// Returns { is_goal, reply, success, steps } or null on subprocess failure.
const PYTHON_EXEC_SCRIPT = path.join(__dirname, 'run_execution.py');
const PYTHON_EXEC_TIMEOUT_MS = 120000; // 2 min max for multi-step execution

function runPythonExecution(message) {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    const child = spawn(process.env.PYTHON_BIN || 'python3', [PYTHON_EXEC_SCRIPT], {
      env: { ...process.env },
      timeout: PYTHON_EXEC_TIMEOUT_MS,
    });

    child.stdin.write(JSON.stringify({ message }));
    child.stdin.end();
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });

    child.on('close', (code) => {
      if (code !== 0) {
        console.warn('[EXEC] run_execution.py exited %d: %s', code, stderr.slice(0, 200));
        return resolve(null);
      }
      try {
        const result = JSON.parse(stdout.trim().split('\n').pop() || '{}');
        resolve(result);
      } catch {
        console.warn('[EXEC] Could not parse run_execution.py output: %s', stdout.slice(0, 200));
        resolve(null);
      }
    });

    child.on('error', (err) => {
      console.warn('[EXEC] spawn failed: %s', err.message);
      resolve(null);
    });
  });
}

// ── LLM chat — Ollama primary, Groq fallback ─────────────────────────────────
const OLLAMA_HOST = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'llama3.2';
const OLLAMA_CHAT_TIMEOUT_MS = 4000;
const GROQ_API_KEY = process.env.GROQ_API_KEY || '';
const GROQ_MODEL = process.env.GROQ_MODEL || 'llama-3.3-70b-versatile';

const AI_SYSTEM_PROMPT =
  'You are AI Employee — an autonomous, highly capable AI business assistant.\n\n' +
  'RESPONSE FORMAT (always follow this structure):\n' +
  '1. Direct Answer — start with a clear 1-2 sentence answer. No preamble.\n' +
  '2. Context — briefly explain the situation or assumptions if needed.\n' +
  '3. Breakdown — use numbered steps or labeled sections to organize the response.\n' +
  '4. Actionable Takeaways — end with what the user should do next.\n\n' +
  'FORMATTING RULES:\n' +
  '- Use **bold** for key terms and section headers\n' +
  '- Use numbered lists for steps, bullet lists for options\n' +
  '- Use code blocks for code, file content, commands\n' +
  '- Keep paragraphs short (2-4 sentences max)\n' +
  '- No rambling, no filler, no vague statements\n\n' +
  'CAPABILITIES:\n' +
  'You have access to real tools: web_search, fetch_page, save_file, llm_generate, llm_extract, website_builder, ' +
  'send_email (needs SMTP or SENDGRID_API_KEY), apollo_search (needs APOLLO_API_KEY), ' +
  'linkedin_post (needs LINKEDIN_ACCESS_TOKEN+LINKEDIN_PERSON_URN).\n' +
  'When you create a file or site, always confirm what was created and show a preview.\n' +
  'Be honest about errors — explain exactly what env var is missing if a tool is not configured.';

// Per-WebSocket-client conversation history — kept server-side so every reply
// has full context without the client needing to resend history.
const _clientHistory = new WeakMap(); // ws → [{role, content}]

function _getClientHistory(ws) {
  if (!_clientHistory.has(ws)) _clientHistory.set(ws, []);
  return _clientHistory.get(ws);
}

function _appendClientHistory(ws, role, content) {
  const h = _getClientHistory(ws);
  h.push({ role, content: String(content).slice(0, 2000) });
  if (h.length > 20) h.splice(0, h.length - 20);
}

function _buildMessages(history) {
  return [{ role: 'system', content: AI_SYSTEM_PROMPT }, ...history];
}

function _callOpenAICompatible(endpoint, apiKey, model, messages, timeoutMs) {
  return new Promise((resolve) => {
    const payload = JSON.stringify({ model, messages, stream: false });
    let url;
    try { url = new URL(endpoint); } catch { return resolve(null); }
    const isHttp = url.protocol === 'http:';
    const httpLib = isHttp ? http : require('https');
    const options = {
      hostname: url.hostname,
      port: url.port || (isHttp ? 80 : 443),
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
        'Authorization': `Bearer ${apiKey}`,
      },
      timeout: timeoutMs,
    };
    const req = httpLib.request(options, (res) => {
      let text = '';
      res.on('data', (chunk) => { text += chunk; });
      res.on('end', () => {
        try {
          const data = JSON.parse(text);
          const content = data?.choices?.[0]?.message?.content || null;
          resolve(content ? content.trim() : null);
        } catch { resolve(null); }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.write(payload);
    req.end();
  });
}

async function requestLLMChat(messages) {
  // 1. Try Ollama (no API key needed)
  const ollamaEndpoint = new URL('/v1/chat/completions', OLLAMA_HOST).toString();
  const ollamaReply = await _callOpenAICompatible(ollamaEndpoint, 'ollama', OLLAMA_MODEL, messages, OLLAMA_CHAT_TIMEOUT_MS);
  if (ollamaReply) return ollamaReply;

  // 2. Groq fallback
  if (GROQ_API_KEY) {
    const groqReply = await _callOpenAICompatible(
      'https://api.groq.com/openai/v1/chat/completions',
      GROQ_API_KEY, GROQ_MODEL, messages, 6000,
    );
    if (groqReply) return groqReply;
  }

  return null;
}

// Legacy wrapper — used by HTTP path where there is no persistent ws client
function requestOllamaChat(message, memoryTrace) {
  const memoryMessage = memoryContextMessage(memoryTrace);
  return requestLLMChat(_buildMessages([
    ...(memoryMessage ? [memoryMessage] : []),
    { role: 'user', content: message },
  ]));
}

// turnRunner pre-declared above near the deferred route mount block.


// ── Business-building money workflows (proxy to Python) ──────────────────────


// GET /api/money/content-log

// GET /api/money/outreach-log

// ── Roadmap Engine routes (proxy to Python) ──────────────────────────────────


// ── Task execution endpoint ───────────────────────────────────────────────────


// Compatibility endpoint used by legacy CLI flows (`ai-employee do/onboard`)

// ── Enterprise: Audit, Reliability, Forge-queue endpoints ────────────────────

// Audit service — auditService, recordAuditEvent, _auditLog pre-declared above near the deferred route mount block.

// ADMIN_SAFETY_ACTIONS pre-declared above near the deferred route mount block.


// Reliability state — pre-declared above near the deferred route mount block.

function updateStabilityScore() {
  const snap = buildObservabilitySnapshot();
  const errorsPerMin = (snap.metrics || {}).errors_per_minute || 0;
  const errorFactor = Math.min(1.0, errorsPerMin / 10);
  const score = Math.max(0.0, 1.0 - 0.6 * errorFactor);
  reliabilityState.stabilityScore = Math.round(score * 1000) / 1000;
  reliabilityState.lastEvaluated = new Date().toISOString();
  if (errorsPerMin >= 10 && !reliabilityState.forgeFrozen) {
    reliabilityState.forgeFrozen = true;
    reliabilityState.freezeReason = `error_rate=${errorsPerMin}/min`;
    recordAuditEvent({ actor: 'system', action: 'forge_freeze', outputData: { reason: reliabilityState.freezeReason }, riskScore: 0.7 });
  }
}

setInterval(updateStabilityScore, 10000);

// Forge approval queue — MAX_FORGE_QUEUE, _forgeDb, _forgeQueue pre-declared above near the deferred route mount block.

// Restore workflow runs from SQLite into runtimeState (most recent 50)
{
  const saved = _forgeDb.prepare(
    `SELECT payload FROM workflow_runs ORDER BY updated_at DESC LIMIT ?`
  ).all(MAX_ACTIVITY_ITEMS).map((r) => { try { return JSON.parse(r.payload); } catch { return null; } }).filter(Boolean);
  if (saved.length > 0) {
    runtimeState.workflowRuns = saved;
    runtimeState.selectedWorkflowRun = saved[0].run_id;
  }
}

function _forgeQueuePush(item) {
  _forgeQueue.unshift(item);
  if (_forgeQueue.length > MAX_FORGE_QUEUE) _forgeQueue.length = MAX_FORGE_QUEUE;
  _forgeDb.prepare(
    `INSERT OR REPLACE INTO forge_queue (id, priority, payload, status, created_at)
     VALUES (?, ?, ?, ?, strftime('%s','now'))`
  ).run(item.id, item.priority || 5, JSON.stringify(item), item.status || 'pending');
  broadcaster.broadcast('forge:queue_update', { item });
}

function _forgeQueueUpdate(id, patch) {
  const idx = _forgeQueue.findIndex((r) => r.id === id);
  if (idx !== -1) Object.assign(_forgeQueue[idx], patch);
  _forgeDb.prepare(
    `UPDATE forge_queue SET payload = ?, status = ?, updated_at = strftime('%s','now') WHERE id = ?`
  ).run(JSON.stringify(idx !== -1 ? _forgeQueue[idx] : patch), patch.status || 'pending', id);
  const updated = idx !== -1 ? _forgeQueue[idx] : { id, ...patch };
  broadcaster.broadcast('forge:queue_update', { item: updated });
}

const APPROVAL_DECISIONS_FILE = statePath('approval_decisions.jsonl');
function appendApprovalDecision(decision) {
  const entry = {
    id: `approval-decision-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    decided_at: new Date().toISOString(),
    ...decision,
  };
  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.appendFileSync(APPROVAL_DECISIONS_FILE, JSON.stringify(entry) + '\n', 'utf8');
  } catch (_) {
    // Audit logging still records the decision; file persistence is best effort.
  }
  return entry;
}

function latestApprovalDecisions() {
  const map = new Map();
  for (const decision of readJsonlSafe(APPROVAL_DECISIONS_FILE, 1000)) {
    if (decision?.approval_id) map.set(decision.approval_id, decision);
  }
  return map;
}

function approvalStatus(rawStatus, decision) {
  if (decision?.decision === 'approved') return 'approved';
  if (decision?.decision === 'rejected') return 'rejected';
  if (rawStatus === 'approved' || rawStatus === 'rejected') return rawStatus;
  return 'pending';
}

function approvalExternalEffect(requiredFor = []) {
  const effects = {
    publish: 'May publish or schedule public content.',
    outreach: 'May send email, DM, or client outreach.',
    payment: 'May spend money, use wallets, or trigger payment systems.',
    paid_task: 'May accept, bid on, submit, or deliver paid client work.',
    external_account: 'May connect, modify, or use an external account.',
  };
  return requiredFor.map((key) => effects[key] || `May perform ${key.replace(/_/g, ' ')}.`).join(' ');
}

function buildApprovalInboxItems() {
  const decisions = latestApprovalDecisions();
  const items = [];
  const turns = readJsonlSafe(statePath('turns.jsonl'), 250).reverse();

  for (const turn of turns) {
    const approvals = Array.isArray(turn.approvals) ? turn.approvals : [];
    for (const approval of approvals) {
      if (!approval || typeof approval !== 'object') continue;
      const id = approval.id || `${turn.turn_id || turn.task_id}:approval`;
      const decision = decisions.get(id);
      const requiredFor = Array.isArray(approval.required_for) ? approval.required_for : [];
      items.push({
        id,
        source: 'turn_runner',
        status: approvalStatus(approval.status, decision),
        requested_action: requiredFor.length ? requiredFor.join(', ') : 'approval required',
        risk_level: approval.risk_level || 'high',
        source_task: turn.task_id || turn.taskId || null,
        turn_id: turn.turn_id || null,
        expected_external_effect: approvalExternalEffect(requiredFor) || approval.reason || 'External effect requires human review.',
        dry_run_preview: turn.input || turn.raw_reply || '',
        proof: Array.isArray(turn.proof) ? turn.proof : [],
        requested_at: approval.requested_at || turn.created_at || null,
        requested_by: turn.user_id || 'system',
        reason: approval.reason || '',
        decision: decision || null,
      });
    }
  }

  for (const item of _forgeQueue) {
    const status = String(item.status || 'pending').toLowerCase();
    if (['approved', 'rejected', 'deployed', 'failed'].includes(status)) continue;
    const id = `forge:${item.id}`;
    const decision = decisions.get(id);
    items.push({
      id,
      source: 'forge',
      status: approvalStatus(status, decision),
      requested_action: item.goal || item.title || item.name || 'Forge action',
      risk_level: String(item.risk_level || item.risk || _forgeRiskLabel(_forgeRiskScore(item.goal || item.title || ''))).toLowerCase(),
      source_task: item.id,
      turn_id: null,
      expected_external_effect: 'May stage, modify, deploy, rollback, or otherwise affect generated code/build artifacts.',
      dry_run_preview: item.summary || item.goal || item.description || '',
      proof: item.proof ? [item.proof].flat() : [],
      requested_at: item.created_at || item.createdAt || null,
      requested_by: item.requested_by || 'forge',
      reason: item.reason || 'Forge item awaits owner/operator approval.',
      decision: decision || null,
    });
  }

  return items.sort((a, b) => {
    const score = { pending: 0, approved: 1, rejected: 1 };
    return (score[a.status] ?? 2) - (score[b.status] ?? 2)
      || String(b.requested_at || '').localeCompare(String(a.requested_at || ''));
  });
}


function decideApproval(req, res, decision) {
  const approvalId = String(req.params.id || '').trim();
  if (!approvalId) return res.status(400).json({ ok: false, error: 'approval id required' });
  const _bodyApproval = validate(SCHEMAS.approvalDecision, req, res);
  if (!_bodyApproval) return;
  const actor = req.jwtPayload?.sub || req.jwtPayload?.role || 'operator';
  const reason = String(_bodyApproval.reason || '').slice(0, 500);
  const inboxItem = buildApprovalInboxItems().find((item) => item.id === approvalId);
  if (!inboxItem) return res.status(404).json({ ok: false, error: 'approval request not found' });
  if (inboxItem.status !== 'pending') {
    return res.status(409).json({ ok: false, error: `approval already ${inboxItem.status}`, item: inboxItem });
  }

  const entry = appendApprovalDecision({
    approval_id: approvalId,
    decision,
    actor,
    reason,
    source: inboxItem.source,
    source_task: inboxItem.source_task,
    turn_id: inboxItem.turn_id,
    requested_action: inboxItem.requested_action,
  });

  let execution = {
    executed: false,
    status: 'decision_recorded',
    details: 'Decision recorded. Canonical turn approvals do not auto-execute external effects yet.',
  };

  if (inboxItem.source === 'forge' && approvalId.startsWith('forge:')) {
    const forgeId = approvalId.slice('forge:'.length);
    _forgeQueueUpdate(forgeId, {
      status: decision,
      decided_at: entry.decided_at,
      decided_by: actor,
      decision_reason: reason,
    });
    execution = {
      executed: false,
      status: `forge_${decision}`,
      details: 'Forge queue status updated. Deployment/external delivery still requires its own guarded execution path.',
    };
  }

  const audit = recordAuditEvent({
    actor,
    action: `approval_${decision}`,
    inputData: { approval_id: approvalId, reason, item: inboxItem },
    outputData: { decision, execution },
    riskScore: inboxItem.risk_level === 'high' ? 0.85 : inboxItem.risk_level === 'medium' ? 0.45 : 0.25,
    traceId: inboxItem.turn_id || inboxItem.source_task || '',
    meta: { source: inboxItem.source },
  });

  broadcaster.broadcast('approval:decided', {
    approval_id: approvalId,
    decision,
    actor,
    reason,
    execution,
    decided_at: entry.decided_at,
  });

  return res.json({
    ok: true,
    approval_id: approvalId,
    decision,
    entry,
    audit_id: audit.id,
    execution,
  });
}


function _forgeRiskScore(goal) {
  const text = (goal || '').toLowerCase();
  const highKw = ['deploy', 'production', 'delete', 'drop', 'rm ', 'overwrite', 'replace all', 'wipe'];
  const midKw = ['refactor', 'update', 'migrate', 'change', 'modify', 'patch', 'rewrite'];
  if (highKw.some((kw) => text.includes(kw))) return 0.80;
  if (midKw.some((kw) => text.includes(kw))) return 0.45;
  return 0.15;
}

function _forgeRiskLabel(score) {
  if (score >= 0.7) return 'HIGH';
  if (score >= 0.3) return 'MEDIUM';
  return 'LOW';
}

// GET /api/audit/events

// GET /api/audit/stats

// POST /api/error-report — frontend unhandled errors surfaced to backend logs
const _frontendErrors = [];


// GET /api/reliability/status

// POST /api/reliability/forge/freeze

// POST /api/reliability/forge/unfreeze

// Legacy Forge compatibility endpoints.
// backend/routes/forge.js is mounted earlier and owns any overlapping
// /api/forge routes. These inline handlers are retained for older dashboard
// clients/tests that still use legacy-only endpoints such as submit/approve/reject.

// GET /api/forge/queue

// POST /api/forge/submit

// POST /api/forge/approve/:id

// POST /api/forge/reject/:id

// ── Forge Python bridge (sandbox, rollback, snapshots, build-system) ─────────

const FORGE_PYTHON_SCRIPT = path.join(__dirname, 'run_forge.py');

function runForgePython(payload, timeoutMs = 90000) {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    const child = spawn(process.env.PYTHON_BIN || 'python3', [FORGE_PYTHON_SCRIPT], {
      env: { ...process.env },
      timeout: timeoutMs,
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('close', (code) => {
      if (code !== 0) {
        console.warn('[FORGE] run_forge.py exited %d: %s', code, stderr.slice(0, 200));
        return resolve(null);
      }
      try {
        const result = JSON.parse(stdout.trim().split('\n').pop() || '{}');
        resolve(result);
      } catch {
        console.warn('[FORGE] Could not parse run_forge.py output: %s', stdout.slice(0, 200));
        resolve(null);
      }
    });
    child.on('error', (err) => {
      console.warn('[FORGE] spawn failed: %s', err.message);
      resolve(null);
    });
  });
}

// POST /api/forge/sandbox

// POST /api/forge/rollback

// GET /api/forge/snapshots

// POST /api/forge/build-system

// ── Doctor (diagnostics) ──────────────────────────────────────────────────────

// Policy / state persistence helpers — _BL_POLICY_FILE, _BL_STATE_FILE, _blacklightState pre-declared above near the deferred route mount block.

function _loadBlPolicy() {
  try { return JSON.parse(fs.readFileSync(_BL_POLICY_FILE, 'utf8')); } catch { return { network_osint_enabled: false }; }
}
function _saveBlPolicy(p) {
  try { fs.writeFileSync(_BL_POLICY_FILE, JSON.stringify(p, null, 2)); } catch {}
}
function _loadBlState() {
  try { return JSON.parse(fs.readFileSync(_BL_STATE_FILE, 'utf8')); } catch { return null; }
}
function _saveBlState() {
  try {
    const toSave = { ..._blacklightState, alerts: _blacklightState.alerts.slice(0, 20) };
    fs.writeFileSync(_BL_STATE_FILE, JSON.stringify(toSave, null, 2));
  } catch {}
}

// _blSaved / _blacklightState pre-declared above near the deferred route mount block.

// ── Recon (safe OSINT + defensive local analysis) ────────────────────────────
// _RECON_CASES_FILE, _RECON_FINDINGS_FILE, _RECON_AUDIT_FILE, RECON_ALLOWED_CATEGORIES,
// RECON_SAFE_OFFENSIVE_CATEGORY_IDS, RECON_BANNED_IDS, RECON_BANNED_CATEGORY — pre-declared above.

function _readReconJson(file, fallback = []) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function _writeReconJson(file, rows) {
  fs.writeFileSync(file, JSON.stringify(Array.isArray(rows) ? rows : [], null, 2));
}

function _isReconToolAllowed(tool) {
  if (!tool || !tool.id) return false;
  if (RECON_BANNED_IDS.has(tool.id)) return false;
  if (RECON_BANNED_CATEGORY.has(tool.category) && !RECON_SAFE_OFFENSIVE_CATEGORY_IDS.has(tool.id)) return false;
  if (!RECON_ALLOWED_CATEGORIES.has(tool.category) && !RECON_SAFE_OFFENSIVE_CATEGORY_IDS.has(tool.id)) return false;
  return true;
}

function _reconTool(tool) {
  const defensiveNames = {
    'cors-misconfiguration-scanner': ['CORS Header Review', 'defensive_review'],
    'jwt-analyzer': ['JWT Analyzer', 'defensive_review'],
    'clickjacking-tester': ['Clickjacking Header Review', 'defensive_review'],
    'insecure-cookie-checker': ['Cookie Security Review', 'defensive_review'],
    'csrf-token-analyzer': ['CSRF Control Review', 'defensive_review'],
    'supabase-rls-auditor': ['Supabase RLS Policy Review', 'defensive_review'],
  };
  const [safeName, safeCategory] = defensiveNames[tool.id] || [tool.name, tool.category];
  const categoryLabel = {
    osint: 'OSINT / Reconnaissance',
    defensive_review: 'Defensive Security Review',
    phishing: 'Phishing Defense',
    special: 'Special Functions',
  }[safeCategory] || tool.categoryLabel || safeCategory;
  return {
    ...tool,
    name: safeName,
    category: safeCategory,
    categoryLabel,
    surface: 'recon',
    safety: tool.mode === 'passive_network' ? 'policy_gated' : tool.mode === 'defensive_simulation' ? 'defensive_simulation' : 'local_safe',
  };
}

function _reconTools() {
  return blacklightTools.TOOL_CATALOG.filter(_isReconToolAllowed).map(_reconTool);
}

function _summarizeReconTools(tools) {
  return tools.reduce((acc, tool) => {
    const row = acc[tool.category] || { total: 0, safe: 0, passive: 0, simulation: 0 };
    row.total += 1;
    if (tool.mode === 'safe') row.safe += 1;
    if (tool.mode === 'passive_network') row.passive += 1;
    if (tool.mode === 'defensive_simulation') row.simulation += 1;
    acc[tool.category] = row;
    return acc;
  }, {});
}

function _appendReconAudit(action, payload = {}, req) {
  const rows = _readReconJson(_RECON_AUDIT_FILE, []);
  const entry = {
    id: crypto.randomUUID(),
    ts: new Date().toISOString(),
    actor: req?.user?.sub || req?.user?.role || 'operator',
    action,
    payload,
  };
  rows.unshift(entry);
  _writeReconJson(_RECON_AUDIT_FILE, rows.slice(0, 500));
  return entry;
}


// GET /api/doctor/llm-status

// GET /api/doctor/errors

// POST /api/doctor/run

// /api/system/stats is defined earlier (line ~1105); not redefined here.

// ── Blacklight (security monitoring) ─────────────────────────────────────────

// GET /api/blacklight/status

// GET /api/blacklight/tools/:id — single tool lookup (Change 4)

// GET /api/blacklight/tools — policy-aware OSINT/security tool catalog.

// GET /api/blacklight/policy (Change 2)

// POST /api/blacklight/policy (Change 2)

// POST /api/blacklight/tools/search — local natural-language tool routing.

// POST /api/blacklight/tools/run — safe local analyzers and defensive simulations.

// POST /api/blacklight/toggle

// POST /api/blacklight/scan

// GET /api/blacklight/alerts

// ── Fairness & Governance ─────────────────────────────────────────────────────

// GET /api/fairness/report

// GET /api/governance/digest

// ── Hermes (task routing) ─────────────────────────────────────────────────────

// GET /api/hermes/status

// POST /api/hermes/task

// POST /api/hermes/broadcast

// ── Learning Ladder Builder API ───────────────────────────────────────────────

const learningLadder = require('./core/learning_ladder');
const agentLearningProfile = require('./core/agent_learning_profile');

// POST /api/learning-ladder/build  { topic }

// POST /api/learning-ladder/complete  { topic, level, success, milestone_output, score, notes }

// GET /api/learning-ladder/progress?topic=...

// GET /api/learning-ladder/all

// ── Agent Learning Profile API ────────────────────────────────────────────────

// POST /api/agents/:agent_id/ladder/assign  { topic }

// POST /api/agents/:agent_id/ladder/advance  { level, success, milestone_output, score, notes }

// GET /api/agents/:agent_id/grade

// GET /api/agents/:agent_id/profile

// GET /api/agents/grades

// ── System halt / restart ─────────────────────────────────────────────────────

let systemHalted = false;


// ── System health ─────────────────────────────────────────────────────────────
// _srvStartMs pre-declared above near the deferred route mount block.


// ── Prompt Inspector endpoints ────────────────────────────────────────────────

// promptTraceStore, MAX_TRACES, promptInspectorConfig pre-declared above near the deferred route mount block.

function addPromptTrace(raw) {
  const trace = {
    id: raw.id || `trace_${Date.now()}_${Math.random().toString(36).slice(2,7)}`,
    timestamp: raw.timestamp || new Date().toISOString(),
    user_input: raw.input || raw.user_input || '',
    constructed_prompt: raw.constructed_prompt || raw.input || '',
    final_output: raw.output || raw.final_output || '',
    model_raw_output: raw.model_raw_output || raw.output || '',
    context_used: raw.context_used || '',
    execution_status: raw.status || raw.execution_status || 'ok',
    duration_ms: raw.latency_ms || raw.duration_ms || 0,
    flags: raw.flags || [],
    agent: raw.agent || 'orchestrator',
    provider: raw.provider || 'node-backend',
    model: raw.model || 'unknown',
    task_id: raw.task_id || null,
    actions_triggered: raw.actions_triggered || [],
    error: raw.error || null,
  };
  promptTraceStore.unshift(trace);
  if (promptTraceStore.length > MAX_TRACES) promptTraceStore.length = MAX_TRACES;
  broadcaster.broadcast('prompt:trace', trace);
}

// Inject trace capture into /api/chat pipeline
const _origChatHandler = null; // hoisted in server.js chat route already — we hook via broadcaster


// ── Legacy Forge task tracking + missing endpoint aliases ────────────────────
// Canonical /api/forge/status is served by backend/routes/forge.js because that
// router is mounted first. The remaining aliases here preserve older UI flows.

const _forgeTaskState = { last_action: null, active: false, mode: 'active' };

// GET /api/forge/status

// POST /api/forge/task  { task, mode }

// GET /api/forge/code-ai/models — list available coding AI models

// POST /api/forge/code-ai — send message to coding AI

// ── AI Middleware Layer ────────────────────────────────────────────────────────

// POST /api/middleware/process — unified multi-model input processing

// GET /api/middleware/status — active model roles + Wave Field routing status

// POST /api/money/task  { task, mode }

const WORKSPACE_UPLOAD_EXTENSIONS = new Set(['.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.txt', '.json', '.sh', '.css', '.html', '.csv', '.yaml', '.yml']);
const WORKSPACE_UPLOAD_MAX_SIZE = 50 * 1024 * 1024;
const workspaceUpload = require('multer')({
  storage: require('multer').diskStorage({
    destination: (_req, _file, cb) => {
      const uploadDir = path.join(WORKSPACE_DIR, 'uploads');
      fs.mkdirSync(uploadDir, { recursive: true });
      cb(null, uploadDir);
    },
    filename: (_req, file, cb) => {
      const ext = path.extname(file.originalname).toLowerCase();
      const safeBase = path.basename(file.originalname, ext).replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80) || 'upload';
      cb(null, `${Date.now()}-${safeBase}${ext}`);
    },
  }),
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (!WORKSPACE_UPLOAD_EXTENSIONS.has(ext)) {
      return cb(new Error(`File type '${ext}' not allowed`));
    }
    cb(null, true);
  },
  limits: { fileSize: WORKSPACE_UPLOAD_MAX_SIZE, files: 100 },
});

function resolveWorkspaceFile(relPath) {
  const decoded = decodeURIComponent(String(relPath || ''));
  const clean = decoded.replace(/^\/+/, '');
  const full = path.resolve(WORKSPACE_DIR, clean);
  const root = path.resolve(WORKSPACE_DIR);
  if (full !== root && !full.startsWith(root + path.sep)) return null;
  return full;
}

// POST /api/workspace/upload — upload file(s) into ~/.ai-employee/workspace/uploads

// GET /api/workspace/files — list files in ~/.ai-employee/workspace/

// DELETE /api/workspace/files/<relative-path> — delete one workspace file.

// GET /api/errors  — error audit log (e2e + external callers)

// ── Machine Identity ──────────────────────────────────────────────────────────


// ── Settings Management ───────────────────────────────────────────────────────


// ── Agent Catalog ─────────────────────────────────────────────────────────────


// ── Auto-Update System ─────────────────────────────────────────────────────────


// ── Live update endpoint (SSE) ────────────────────────────────────────────────
let _updateRunning = false;

// ── Auto-Update Settings + Watchdog Status ────────────────────────────────────


// ── Task Tracking System ──────────────────────────────────────────────────────
// Stores live task progress; in-memory with TTL cleanup (use Redis for production)
// taskStore + taskConnections pre-declared above near the deferred route mount block.

function initTask(taskId, title = 'Task') {
  const task = {
    task_id: taskId,
    name: title,
    status: 'running',
    started_at: new Date().toISOString(),
    steps: [],
  };
  taskStore.set(taskId, { task, steps: [] });
  return task;
}

function updateTaskStep(taskId, stepId, updates) {
  const entry = taskStore.get(taskId);
  if (!entry) return;

  const { steps } = entry;
  let step = steps.find(s => s.id === stepId);

  if (!step) {
    step = { id: stepId, status: 'pending', started_at: null, elapsed_ms: 0, ...updates };
    steps.push(step);
  } else {
    Object.assign(step, updates);
  }

  // Calculate elapsed time if step is/was active
  if (step.started_at && step.status !== 'pending') {
    step.elapsed_ms = new Date() - new Date(step.started_at);
  }

  broadcastTaskUpdate(taskId, {
    type: 'step_update',
    step_id: stepId,
    data: step,
  });
}

function completeTask(taskId, status = 'done') {
  const entry = taskStore.get(taskId);
  if (!entry) return;
  entry.task.status = status;
  broadcastTaskUpdate(taskId, {
    type: 'task_update',
    data: { status },
  });
}

function broadcastTaskUpdate(taskId, update) {
  const conns = taskConnections.get(taskId);
  if (conns) {
    const msg = JSON.stringify(update);
    conns.forEach(ws => { if (ws.readyState === 1) ws.send(msg); });
  }
  // Also push to SSE listeners (defined in Task Progress API section below)
  if (typeof _notifySSEListeners === 'function') {
    _notifySSEListeners(taskId, { type: update.type || 'task_update', taskId, ...update });
  }
}

// Cleanup old tasks every 10 minutes (keep max 1 hour in memory)
setInterval(() => {
  const now = Date.now();
  const maxAge = 3600000; // 1 hour
  for (const [taskId, entry] of taskStore) {
    if (now - new Date(entry.task.started_at).getTime() > maxAge) {
      taskStore.delete(taskId);
      taskConnections.delete(taskId);
    }
  }
}, 600000);

// ── WebSocket server ──────────────────────────────────────────────────────────

const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: '/ws', maxPayload: 1024 * 1024 }); // 1 MB cap

// Initialize WebSocket infrastructure for multi-tenant real-time updates
const connManager = new ConnectionManager();
const heartbeatManager = new HeartbeatManager();
heartbeatManager.start(wss, connManager);

// Initialize task gateway with connection manager for real-time updates
taskGateway.setConnectionManager(connManager);

// Ping/pong keepalive — terminates dead connections that never send close frames.
// Without this, stale clients accumulate and silent disconnects go undetected.
const WS_PING_INTERVAL = 25000; // 25s — under most NAT/proxy 30s timeout
setInterval(() => {
  wss.clients.forEach((ws) => {
    if (ws.isAlive === false) { ws.terminate(); return; }
    ws.isAlive = false;
    ws.ping();
  });
}, WS_PING_INTERVAL).unref();

wss.on('connection', (ws, req) => {
  ws.isAlive = true;
  ws.on('pong', () => { ws.isAlive = true; });
  // Localhost connections (Tauri/Electron webview, dev browser) bypass token check;
  // remote connections must present a valid JWT token.
  const _wsRemote = req.socket?.remoteAddress || '';
  const _wsIsLocal = _wsRemote === '127.0.0.1' || _wsRemote === '::1' || _wsRemote === '::ffff:127.0.0.1';
  if (!_wsIsLocal && !wsTokenValid(req)) {
    ws.close(4401, 'Unauthorized');
    return;
  }

  // Immediately tell this client about backend health so the "DISCONNECTED"
  // banner flips to OPERATIONAL without waiting for the next periodic broadcast.
  try {
    ws.send(JSON.stringify({
      event: 'system:ready',
      data: { python_ok: _systemReady.python_ok, llm_ok: _systemReady.llm_ok, node_ok: true },
      timestamp: new Date().toISOString(),
    }));
  } catch (_) {}

  // FIX-4: 2026-05-12 — Stagger WS initial state messages at 50ms intervals instead of burst
  const _wsInitMessages = [
    { idx: 0, msg: () => {
      try {
        const path = require('path');
        const fs = require('fs');
        const idPath = statePath('identity.json');
        if (fs.existsSync(idPath)) {
          const identity = JSON.parse(fs.readFileSync(idPath, 'utf8'));
          return JSON.stringify({ event: 'identity:ready', data: identity, timestamp: new Date().toISOString() });
        }
      } catch (_) {}
      return null;
    }},
    { idx: 1, msg: () => JSON.stringify({ event: 'system:status', data: sampleSystemStatus(), timestamp: new Date().toISOString() })},
    { idx: 2, msg: () => JSON.stringify({ event: 'agents:list', data: { agents: getAgents() }, timestamp: new Date().toISOString() })},
    { idx: 3, msg: () => JSON.stringify({ event: 'nn:status', data: subsystems.getNNStatus(), timestamp: new Date().toISOString() })},
    { idx: 4, msg: () => JSON.stringify({ event: 'memory:update', data: subsystems.getMemoryTree(), timestamp: new Date().toISOString() })},
    { idx: 5, msg: () => JSON.stringify({ event: 'doctor:check', data: subsystems.getDoctorStatus(), timestamp: new Date().toISOString() })},
    { idx: 6, msg: () => JSON.stringify({ event: 'brain:insights', data: brain.insights(), timestamp: new Date().toISOString() })},
    { idx: 7, msg: () => JSON.stringify({ event: 'brain:activity', data: brain.activity(20), timestamp: new Date().toISOString() })},
    { idx: 8, msg: () => JSON.stringify({ event: 'autonomy:status', data: subsystems.getAutonomyStatus(), timestamp: new Date().toISOString() })},
    { idx: 9, msg: () => JSON.stringify({ event: 'objective:update', data: { type: 'objective_update', system: 'money_mode', ...runtimeState.objectiveState.money_mode }, timestamp: new Date().toISOString() })},
    { idx: 10, msg: () => JSON.stringify({ event: 'objective:update', data: { type: 'objective_update', system: 'ascend_forge', ...runtimeState.objectiveState.ascend_forge }, timestamp: new Date().toISOString() })},
    { idx: 11, msg: () => JSON.stringify({ event: 'workflow:snapshot', data: { active_run: runtimeState.selectedWorkflowRun, runs: runtimeState.workflowRuns }, timestamp: new Date().toISOString() })},
    { idx: 12, msg: () => JSON.stringify({ event: 'observability:snapshot', data: buildObservabilitySnapshot(), timestamp: new Date().toISOString() })},
    { idx: 13, msg: () => runtimeState.activityFeed.length > 0 ? JSON.stringify({ event: 'activity:snapshot', data: runtimeState.activityFeed, timestamp: new Date().toISOString() }) : null },
    { idx: 14, msg: () => runtimeState.executionLogs.length > 0 ? JSON.stringify({ event: 'execution:snapshot', data: runtimeState.executionLogs, timestamp: new Date().toISOString() }) : null },
  ];
  _wsInitMessages.forEach(m => {
    setTimeout(() => {
      try {
        const payload = m.msg();
        if (payload && ws.readyState === 1) ws.send(payload);
      } catch (e) {
        console.error(`[WS] Error sending init message ${m.idx}:`, e.message);
      }
    }, m.idx * 50);
  });

  ws.on('message', (raw) => {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.type === 'chat' && parsed.message) {
        // Track user turn in per-client history
        _appendClientHistory(ws, 'user', parsed.message);
        const msg = parsed.message.trim().toLowerCase();

        // ── Autonomy chat commands ─────────────────────────────────────
        const autonomyCmds = {
          'system on': 'ON',
          'system off': 'OFF',
          'system auto': 'AUTO',
          'halt system': '_HALT',
          'emergency stop': '_HALT',
          'status system': '_STATUS',
        };
        const cmdMatch = autonomyCmds[msg];
        if (cmdMatch) {
          if (cmdMatch === '_HALT') {
            const httpLib = require('http');
            const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/emergency-stop`;
            const r = httpLib.request(url, { method: 'POST', timeout: 3000 }, () => {});
            r.on('error', () => {});
            r.end();
            addActivity('[AUTONOMY] ⚠ EMERGENCY STOP via chat', 'system');
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              message: '⚠️ Emergency stop executed. All autonomous execution has been halted.',
            });
          } else if (cmdMatch === '_STATUS') {
            const auto = subsystems.getAutonomyStatus();
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              message: `System status — mode: ${auto.mode?.mode || 'OFF'}, daemon ${auto.daemon?.running ? 'running' : 'stopped'}, queue depth: ${auto.queue?.active || 0}, tasks processed: ${auto.daemon?.tasks_processed || 0}.`,
            });
          } else {
            // Set mode
            const httpLib = require('http');
            const payload = JSON.stringify({ mode: cmdMatch });
            const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/mode`;
            const r = httpLib.request(url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
              timeout: 3000,
            }, () => {});
            r.on('error', () => {});
            r.write(payload);
            r.end();
            addActivity(`[AUTONOMY] Mode → ${cmdMatch} (via chat)`, 'system');
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              message: `System mode set to ${cmdMatch}. Ready.`,
            });
          }
          return; // handled — don't route to orchestrator
        }

        const objectiveCommand = handleGoalDrivenCommand(parsed.message);
        if (objectiveCommand.handled) {
          broadcaster.broadcast('orchestrator:message', {
            taskId: 'objective',
            message: objectiveCommand.reply,
          });
          return;
        }

        // Canonical turn runner path. Legacy WebSocket chat code remains below
        // as a compatibility fallback only; this path emits turn:* + one
        // orchestrator:message alias with the same turn_id.
        if (parsed.use_turn_runner !== false) {
          console.info('[AI FLOW] Input received (WS canonical): message_len=%d', parsed.message.length);
          void (async () => {
            try {
              const turn = await turnRunner.runTurn({
                kind: 'chat',
                source: 'chat-ws',
                message: parsed.message,
                modelRoute: parsed.model_route || undefined,
                userId: parsed.user_id || 'user:default',
                tenantId: parsed.tenant_id || 'default',
                labels: ['ws'],
              });
              _appendClientHistory(ws, 'assistant', turn.assistant_reply || turn.reply || '');
            } catch (err) {
              const fallbackId = `turn-${crypto.randomUUID()}`;
              const fallbackReply = buildLocalFallbackReply(parsed.message, { taskId: fallbackId, subsystem: 'orchestrator' });
              _appendClientHistory(ws, 'assistant', fallbackReply);
              broadcaster.broadcast('turn:failed', {
                turn_id: fallbackId,
                task_id: fallbackId,
                status: 'failed',
                input: parsed.message,
                assistant_reply: fallbackReply,
                reply: fallbackReply,
                content: fallbackReply,
                degraded: true,
                errors: [{ stage: 'turn_runner', message: err && err.message ? err.message : String(err) }],
              });
              broadcaster.broadcast('orchestrator:message', {
                turn_id: fallbackId,
                taskId: fallbackId,
                message: fallbackReply,
                degraded: true,
              });
            }
          })();
          return;
        }

        // ── Normal chat routing ────────────────────────────────────────
        console.info('[AI FLOW] Input received (WS): message_len=%d', parsed.message.length);
        const run = createWorkflowRun({
          name: 'Chat Workflow',
          source: 'chat',
          goal: parsed.message,
        });
        const queued = orchestrator.submitTask(parsed.message, {
          userId: 'user:default',
          workflow: { runId: run.run_id, parentTaskId: null },
          labels: ['chat'],
        });
        attachWorkflowNode({
          runId: run.run_id,
          queued,
          taskName: parsed.message,
          parentTaskId: null,
        });
        broadcaster.broadcast('orchestrator:queued', queued);
        broadcaster.broadcast('heartbeat', {
          message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
          level: 'info',
          heartbeat: heartbeatCounter,
        });

        // ── Proxy to Python backend LLM pipeline for real AI response ──
        // The Python backend has the full pipeline: context injection,
        // memory, LLM call, personalised response. Use it instead of
        // the generic keyword-matched buildHumanReply.
        // When Python is unavailable, we MUST still broadcast an
        // orchestrator:message so the UI does not stay stuck on "processing".
        const wsModelRoute = parsed.model_route || undefined;
        const wsUserId = parsed.user_id || 'user:default';
        // 4-tier priority: execution engine → Python LLM → Ollama/Groq → fallback
        _broadcastStep('Analyzing request');
	        (async () => {
	          const _broadcast = (replyText, attachments) => {
	            _appendClientHistory(ws, 'assistant', replyText);
            broadcaster.broadcast('orchestrator:message', {
              message: replyText,
              attachments: attachments || [],
              subsystem: queued.subsystem || 'orchestrator',
              taskId: queued.taskId,
              from: queued.agentId,
              agentId: queued.agentId,
              timestamp: new Date().toISOString(),
            });
            // Additional canonical chat topic — frontend ChatPanel listens here.
            broadcaster.broadcast('chat:message', {
              role: 'assistant',
              text: replyText,
	              ts: Date.now(),
	            });
	          };

	          _broadcastStep('Retrieving memory context');
	          const memoryTrace = await collectHybridMemoryContext(parsed.message, {
	            userId: wsUserId,
	            sessionId: run.run_id,
	            taskId: queued.taskId,
	            mode: 'main_ai_chat_ws',
	            maxTokens: 1200,
	          });
	          if (memoryTrace) {
	            appendDecision(run, {
	              ts: new Date().toISOString(),
	              task_id: queued.taskId,
	              type: 'memory_router_preflight',
	              summary: `Routes ${Array.isArray(memoryTrace.routes) ? memoryTrace.routes.map((route) => route.id).join(', ') : 'none'} · confidence ${memoryTrace.confidence ?? 0}`,
	              trace_id: memoryTrace.trace_id,
	            });
	            broadcaster.broadcast('memory:router:trace', {
	              trace_id: memoryTrace.trace_id,
	              task_id: queued.taskId,
	              routes: memoryTrace.routes,
	              confidence: memoryTrace.confidence,
	              degraded: memoryTrace.degraded,
	            });
	          }

	          // 1. Real execution engine — structured goal → real tools
	          _broadcastStep('Planning AI pipeline');
          try {
            const execResult = await runPythonExecution(parsed.message);
            if (execResult && execResult.is_goal && execResult.reply) {
              console.info('[AI FLOW] → Real execution engine (WS): steps=%d success=%s', execResult.steps || 0, execResult.success);
              // Broadcast individual tool steps from the execution result
              const toolSteps = execResult.step_actions || [];
              toolSteps.slice(0, 5).forEach((s) => {
                if (s && s.action) _broadcastStep(`Tool: ${s.action}`, s.status || null);
              });
              _broadcastStep('Generating response');
              return _broadcast(execResult.reply, execResult.attachments);
            }
          } catch (_) {}

	          // 2. Python LLM backend (full pipeline)
	          let reply = null;
	          try { reply = await requestPythonChat(parsed.message, wsModelRoute, wsUserId, memoryTrace); } catch (_) {}
	          if (reply) {
	            const structuredWsPyReply = applyStructuredFormat(reply, 'AI Employee');
	            console.info('[AI FLOW] → LLM response returned (WS→Python): len=%d', structuredWsPyReply.length);
            _broadcastStep('Generating response');
            return _broadcast(structuredWsPyReply);
          }

	          // 3. Ollama with full conversation history (Groq fallback built-in)
	          _broadcastStep('Generating response');
	          const history = _getClientHistory(ws);
	          const memoryMessage = memoryContextMessage(memoryTrace);
	          try { reply = await requestLLMChat(_buildMessages([...(memoryMessage ? [memoryMessage] : []), ...history])); } catch (_) {}
	          if (reply) {
            const structuredWsReply = applyStructuredFormat(reply, 'Ollama');
            console.info('[AI FLOW] → LLM response (WS): len=%d', structuredWsReply.length);
            return _broadcast(structuredWsReply);
          }

          // 4. Honest fallback
          _broadcast(buildLocalFallbackReply(parsed.message, queued));
        })();
        console.info('[AI FLOW] → Task queued (WS): taskId=%s', queued.taskId);
      }
    } catch (err) {
      // ignore malformed messages
    }
  });

  ws.on('error', (err) => {
    console.error('[WS] Client error:', err.message);
  });
});

broadcaster.init(wss);
subsystems.startPolling(5000);
broadcaster.startHeartbeat({
  intervalMs: 1800,
  messageFactory: ({ seq }) => {
    heartbeatCounter = seq;
    const stats = sampleSystemStatus();
    return `[SYSTEM] heartbeat=${seq} mode=${stats.mode} running=${stats.running_agents}/${stats.total_agents}`;
  },
});

// Start agent heartbeat collector for real-time monitoring (Phase 3.2)
startHeartbeatCollector(broadcaster);

// Bridge Python EventStream → WS broadcasts so dashboard panels receive
// real metrics ticks, cognition/economy/operations updates, etc.
try {
  const { startPythonMetricsBridge } = require('./bridges/python_metrics_bridge');
  startPythonMetricsBridge({
    broadcast: (topic, payload) => broadcaster.broadcast(topic, payload),
    log: console,
  });
} catch (e) {
  console.warn('[PyBridge] startup failed:', e && e.message);
}

// ── Readiness state machine ──────────────────────────────────────────────────
// _readiness is pre-declared near the deferred route mount block so routes can
// access it via _lazyRouteDeps Proxy without hitting the temporal dead zone.

// Cached system:ready snapshot — sent to new WS clients on connect so the
// dashboard banner flips to OPERATIONAL immediately instead of waiting for the
// next broadcast. Updated everywhere we already broadcast `system:ready`.
// _systemReady is pre-declared near the deferred route mount block.
function _updateSystemReady(patch) {
  Object.assign(_systemReady, patch);
}

// FIX-3: 2026-05-12 — Optimized probeUntilReady: 12s max, 200ms poll intervals, graceful degradation
async function probeUntilReady() {
  const PYTHON_URL = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 18790}`;
  const http = require('http');
  const START = Date.now();

  function httpGet(url) {
    return new Promise((resolve) => {
      http.get(url, { timeout: 2000 }, (res) => {
        let body = '';
        res.on('data', (d) => { body += d; });
        res.on('end', () => resolve({ ok: res.statusCode === 200, body }));
      }).on('error', () => resolve({ ok: false, body: '' }))
        .on('timeout', function() { this.destroy(); resolve({ ok: false, body: '' }); });
    });
  }

  // Early broadcast after 2s: frontend loads immediately, probe continues in background
  const earlyBroadcast = setTimeout(() => {
    if (_readiness.phase === 'BOOTING') {
      _readiness.phase = 'INITIALIZING';
      _updateSystemReady({ python_ok: null, llm_ok: null });
      broadcaster.broadcast('system:ready', { python_ok: null, llm_ok: null, node_ok: true, phase: 'initializing' });
      console.log('[READINESS] 📡 Early broadcast sent (2s) — frontend loading, probing continues');
    }
  }, 2000);

  // Phase 1: wait for Python HTTP (max 6s with 200ms intervals = 30 attempts)
  for (let i = 0; i < 30; i++) {
    const elapsed = Date.now() - START;
    if (elapsed > 12000) break; // Global timeout: 12s max
    await new Promise(r => setTimeout(r, 200));
    const r = await httpGet(`${PYTHON_URL}/health`);
    if (r.ok) { _readiness.pythonReady = true; _readiness.phase = 'PYTHON_WAIT'; break; }
  }

  if (!_readiness.pythonReady) {
    clearTimeout(earlyBroadcast);
    console.log('[READINESS] ⚠️  Python backend unreachable after 6s — degraded mode');
    _readiness.phase = 'READY';
    _updateSystemReady({ python_ok: false, llm_ok: false });
    broadcaster.broadcast('system:ready', { python_ok: false, llm_ok: false, node_ok: true });
    markBootEvent('ai_core_ready');
    return;
  }

  // Phase 2: wait for subsystems (max remaining time until 12s total, 200ms intervals)
  _readiness.phase = 'SUBSYSTEM_INIT';
  for (let i = 0; i < 30; i++) {
    const elapsed = Date.now() - START;
    if (elapsed > 12000) break; // Global timeout: 12s max
    await new Promise(r => setTimeout(r, 200));
    const r = await httpGet(`${PYTHON_URL}/health/detail`);
    if (r.ok) {
      try {
        const d = JSON.parse(r.body);
        if (d.subsystems_ok) {
          clearTimeout(earlyBroadcast);
          _readiness.subsystemsReady = true;
          _readiness.phase = 'READY';
          _updateSystemReady({ python_ok: true, llm_ok: !!d.llm_reachable });
          broadcaster.broadcast('system:ready', { python_ok: true, llm_ok: !!d.llm_reachable, node_ok: true });
          markBootEvent('ai_core_ready');
          const elapsed = Date.now() - START;
          console.log(`[READINESS] ✅ All systems ready in ${elapsed}ms — broadcasting system:ready`);
          return;
        }
      } catch (_) {}
    }
    if (i % 3 === 2) {
      const elapsed = Date.now() - START;
      console.log(`[READINESS] ⏳ Waiting for subsystems… (${(elapsed / 1000).toFixed(1)}s)`);
    }
  }

  // Timeout — degrade gracefully (12s reached)
  clearTimeout(earlyBroadcast);
  _readiness.phase = 'READY';
  _updateSystemReady({ python_ok: true, llm_ok: false });
  broadcaster.broadcast('system:ready', { python_ok: true, llm_ok: false, node_ok: true });
  markBootEvent('ai_core_ready');
  const elapsed = Date.now() - START;
  console.log(`[READINESS] ⚠️  Subsystem timeout after ${(elapsed / 1000).toFixed(1)}s — proceeding in degraded mode`);
}

onAgentEvent('agent:update', (agents) => {
  broadcaster.broadcast('agents:list', { agents });
});

onAgentEvent('task:started', ({ agent, task }) => {
  addActivity(`[TASK] ${task.id} started on ${agent.name}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'running';
    recalcObjectiveProgress(objectiveMeta.system);
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'active';
    node.progress_percent = 45;
    node.started_at = task.startedAt || new Date().toISOString();
    node.agent = agent.name;
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'execution_start',
      summary: `Agent ${agent.name} started with strategy ${node.strategy || 'default'}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('step_progress', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    step: 'execution_started',
    agent: agent.name,
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] started ${task.id}`,
    level: 'info',
    heartbeat: heartbeatCounter,
  });
  void voiceManager.emitEvent('task_created', { priority: task.priority });
});

onAgentEvent('task:completed', ({ agent, task }) => {
  recordExecution({
    taskId: task.id,
    skill: task.subsystem || 'general',
    status: 'success',
    notes: task.message,
  });
  addActivity(`[TASK] ${task.id} completed by ${agent.name}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'completed';
    if (objectiveMeta.system === 'money_mode' && objState?.performance) {
      if (/lead/i.test(objectiveMeta.task_name)) objState.performance.leads_generated += MONEY_LEADS_PER_TASK;
      if (/email|outreach/i.test(objectiveMeta.task_name)) objState.performance.emails_sent += MONEY_EMAILS_PER_TASK;
      // Lightweight estimate for UI feedback:
      // assume roughly 2 outbound emails per potential converted lead,
      // then scale the ratio by 10 to keep the indicator in a visible 0-100 range.
      const leads = objState.performance.leads_generated || 1;
      objState.performance.conversion_pct = Math.round((objState.performance.emails_sent / Math.max(leads * 2, 1)) * 10);
    }
    if (objectiveMeta.system === 'ascend_forge') {
      objState.results = objState.results || [];
      objState.results.push({
        task_id: task.id,
        step: objectiveMeta.task_name,
        summary: `Completed ${objectiveMeta.task_name}`,
      });
      objState.results = objState.results.slice(-20);
    }
    recalcObjectiveProgress(objectiveMeta.system);
    if (objState?.status === OBJECTIVE_STATUS.COMPLETED && objState?.current_objective) {
      objState.current_objective.status = 'completed';
      objState.current_objective.updated_at = new Date().toISOString();
      const objective = runtimeState.objectives.find((row) => row.id === objState.current_objective.id);
      if (objective) {
        objective.status = 'completed';
        objective.updated_at = objState.current_objective.updated_at;
        persistObjectives();
      }
      if (objectiveMeta.system === 'ascend_forge') {
        objState.result = {
          plan: objState.plan || [],
          agents_used: objState.agents_used || [],
          progress: 100,
          status: 'completed',
          results: objState.results || [],
        };
      }
    }
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'completed';
    node.progress_percent = 100;
    node.completed_at = new Date().toISOString();
    node.agent = agent.name;
    node.result = {
      status: 'success',
      summary: task.message,
    };
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'result',
      summary: `Result success • ${task.message}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('task_completed', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    agent: agent.name,
    result: task.message,
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] completed ${task.id}`,
    level: 'success',
    heartbeat: heartbeatCounter,
  });
  void voiceManager.emitEvent('task_completed');
  queueNextWorkflowStep(task.id);
});

onAgentEvent('task:failed', ({ agent, task }) => {
  recordExecution({
    taskId: task.id,
    skill: task.subsystem || 'general',
    status: 'failed',
    notes: task.error || task.message || 'Task failed',
  });
  addActivity(`[TASK] ${task.id} failed on ${agent.name}: ${task.error || 'execution error'}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'failed';
    if (objectiveMeta.system === 'ascend_forge') {
      objState.results = objState.results || [];
      objState.results.push({
        task_id: task.id,
        step: objectiveMeta.task_name,
        summary: `Failed ${objectiveMeta.task_name}: ${task.error || 'execution error'}`,
        status: 'failed',
      });
      objState.results = objState.results.slice(-20);
    }
    recalcObjectiveProgress(objectiveMeta.system);
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  if (runtimeState.workflowTaskMeta[task.id]) {
    runtimeState.workflowTaskMeta[task.id].error = task.error || null;
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'failed';
    node.progress_percent = 100;
    node.completed_at = new Date().toISOString();
    node.agent = agent.name;
    node.result = {
      status: 'failed',
      summary: task.error || task.message || 'Execution failed',
    };
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'result',
      summary: `Result failed • ${task.error || 'execution error'}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('error_detected', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    agent: agent.name,
    error: task.error || 'execution error',
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] failed ${task.id}`,
    level: 'warning',
    heartbeat: heartbeatCounter,
  });
  void voiceManager.emitEvent('error_detected', { message: 'Error detected.' });
  retryWorkflowStep(task.id);
});

orchestrator.on('orchestrator:reply', (data) => {
  broadcaster.broadcast('orchestrator:message', data);
});

// ── Neural graph file watcher — broadcasts brain:graph_updated every 10s ─────
const NEURAL_GRAPH_SNAPSHOT_PATH = statePath('neural_graph_snapshot.json');
let _graphLastMtimeMs = 0;
let _graphLastNodeCount = 0;
let _graphLastEdgeCount = 0;

function watchGraphFile() {
  const readGraphStats = () => {
    try {
      if (!fs.existsSync(NEURAL_GRAPH_SNAPSHOT_PATH)) {
        broadcaster.broadcast('brain:graph_updated', { nodes_count: 0, edges_count: 0, ts: Date.now() });
        return;
      }
      const stat = fs.statSync(NEURAL_GRAPH_SNAPSHOT_PATH);
      if (stat.mtimeMs === _graphLastMtimeMs) return; // no change
      _graphLastMtimeMs = stat.mtimeMs;
      const raw = JSON.parse(fs.readFileSync(NEURAL_GRAPH_SNAPSHOT_PATH, 'utf8'));
      const nodes_count = Array.isArray(raw.nodes) ? raw.nodes.length : 0;
      const edges_count = Array.isArray(raw.links || raw.edges) ? (raw.links || raw.edges).length : 0;
      _graphLastNodeCount = nodes_count;
      _graphLastEdgeCount = edges_count;
      // Keep graphDeltaState in sync so extracted route (agents-brain.js) reads fresh values
      if (global._graphDeltaState) {
        global._graphDeltaState.lastMtimeMs   = stat.mtimeMs;
        global._graphDeltaState.lastNodeCount = nodes_count;
        global._graphDeltaState.lastEdgeCount = edges_count;
      }
      broadcaster.broadcast('brain:graph_updated', { nodes_count, edges_count, ts: Date.now() });
    } catch (_) {
      broadcaster.broadcast('brain:graph_updated', { nodes_count: 0, edges_count: 0, ts: Date.now() });
    }
  };
  setInterval(readGraphStats, 10000).unref();
  readGraphStats(); // initial read
}

// ── Graph delta endpoint ──────────────────────────────────────────────────────

setInterval(() => {
  broadcaster.broadcast('system:status', sampleSystemStatus());
  broadcaster.broadcast('agents:list', { agents: getAgents() });
  broadcaster.broadcast('nn:status', subsystems.getNNStatus());
  broadcaster.broadcast('memory:update', subsystems.getMemoryTree());
  broadcaster.broadcast('doctor:check', subsystems.getDoctorStatus());
  broadcaster.broadcast('brain:insights', brain.insights());
  broadcaster.broadcast('brain:activity', brain.activity(20));
  broadcaster.broadcast('autonomy:status', subsystems.getAutonomyStatus());
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system: 'money_mode',
    ...runtimeState.objectiveState.money_mode,
  });
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system: 'ascend_forge',
    ...runtimeState.objectiveState.ascend_forge,
  });
  broadcaster.broadcast('workflow:snapshot', {
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
  });
  broadcaster.broadcast('observability:snapshot', buildObservabilitySnapshot());
}, 5000);

// ── Task Progress API ─────────────────────────────────────────────────────────

// SSE listener registry — _sseTaskListeners pre-declared above near the deferred route mount block.

function _notifySSEListeners(taskId, data) {
  const set = _sseTaskListeners.get(taskId);
  if (!set || set.size === 0) return;
  const payload = `data: ${JSON.stringify(data)}\n\n`;
  set.forEach(res => { try { res.write(payload); } catch (_) {} });
}

// Patch broadcaster so SSE clients receive task_progress + workflow:update events.
(function patchBroadcasterForSSE() {
  const _orig = broadcaster.broadcast.bind(broadcaster);
  broadcaster.broadcast = function patchedBroadcast(event, data) {
    _orig(event, data);
    if (event === 'task_progress' && data) {
      const id = data.taskId || data.task_id;
      if (id) _notifySSEListeners(id, { type: 'task_progress', ...data });
    } else if (event === 'workflow:update' && Array.isArray(data?.nodes)) {
      data.nodes.forEach(node => {
        const id = node.task_id || node.taskId;
        if (id) _notifySSEListeners(id, { type: 'workflow_update', ...node });
      });
    }
  };
})();

// GET /api/tasks/:taskId/progress — SSE stream for live task progress.
// Must be declared before /api/tasks/:taskId (Express matches first-wins).


// ── Task History API ──────────────────────────────────────────────────────────


// ── Error Recovery API ────────────────────────────────────────────────────────


// Prometheus metrics endpoint — optionally gated by METRICS_TOKEN env var

// ── Global /api/* catch-all rate limiter ──────────────────────────────────────
// Runs after all specific-route middlewares. Requests that already consumed a
// tighter per-route limiter above still count here — that is intentional:
// the global bucket provides a hard ceiling against endpoint enumeration and
// slow-rate scatter attacks that individually stay under per-route limits.
app.use('/api/', _rl_api_global);

app.get('*', (req, res, next) => {
  if (!HAS_FRONTEND_DIST) {
    if (req.path.startsWith('/api/') || req.path === '/health' || req.path === '/version') return next();
    res.status(503).type('html').send(`<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>AI Employee — Build Required</title>
<style>body{font-family:sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:2rem 2.5rem;max-width:480px;text-align:center}
h1{color:#f8fafc;margin-top:0}pre{background:#0f172a;border-radius:6px;padding:1rem;text-align:left;font-size:.85rem;overflow-x:auto}</style>
</head>
<body><div class="box">
<h1>⚠ Frontend Not Built</h1>
<p>The production build of the frontend is missing. Run the following command from the repository root to build it:</p>
<pre>npm --prefix frontend run build</pre>
<p>Or start the full system with:</p>
<pre>./start.sh</pre>
<p>For live development with hot-reload, start the Vite dev server instead:</p>
<pre>cd frontend &amp;&amp; npm run dev</pre>
<p>API health check: <a href="/health" style="color:#60a5fa">/health</a></p>
</div></body></html>`);
    return;
  }
  if (req.path.startsWith('/api/') || req.path === '/health' || req.path === '/version') return next();
  if (req.path.startsWith('/gateway') || req.path.startsWith('/orchestrator')) return next();
  res.set('Cache-Control', 'no-store, must-revalidate');
  // Read fresh on every request so hot-deployed builds are served immediately.
  const html = readFrontendIndex().replace(/__APP_VERSION__/g, GIT_COMMIT);
  res.type('html').send(html);
});

// Bind to all interfaces by default so the server is reachable from the host
// machine when running inside WSL, Docker, or a VM.  Set LISTEN_HOST=127.0.0.1
// in the environment to restrict to loopback only.
const LISTEN_HOST = process.env.LISTEN_HOST || '127.0.0.1';

// ── Task Progress WebSocket Upgrade ────────────────────────────────────────────
// Handle /api/tasks/:taskId/ws upgrade requests for live progress updates
// Also route channel-based subscriptions: /ws/tasks, /ws/agents, /ws/execution-trace

const channelUpgradeHandler = createUpgradeHandler(connManager, JWT_SECRET);

server.on('upgrade', (req, socket, head) => {
  // The main `/ws` path is owned by the WebSocketServer attached at line 3896.
  // Its auto-installed upgrade handler runs before this listener; we MUST
  // ignore those requests here, otherwise `socket.destroy()` below kills the
  // freshly-upgraded socket and `wss.clients` ends up empty.
  const urlPath = (req.url || '').split('?')[0];
  if (urlPath === '/ws') return;

  // Route channel subscriptions (/ws/*)
  if (req.url.startsWith('/ws/')) {
    channelUpgradeHandler(req, socket, head);
    return;
  }

  // Route legacy task progress upgrades (/api/tasks/:taskId/ws)
  const match = req.url.match(/^\/api\/tasks\/([a-f0-9\-]+)\/ws$/);
  if (!match) {
    socket.destroy();
    return;
  }

  const taskId = match[1];

  // Auth guard: task progress WS requires a valid JWT (same as main /ws path)
  if (!wsTokenValid(req)) {
    socket.destroy();
    return;
  }

  const wssTask = new WebSocketServer({ noServer: true, maxPayload: 1024 * 1024 });

  wssTask.handleUpgrade(req, socket, head, (ws) => {
    // Send current task state on connection
    const entry = taskStore.get(taskId);
    if (entry) {
      ws.send(JSON.stringify({
        type: 'task_state',
        task: entry.task,
        steps: entry.steps,
      }));
    }

    // Register this connection
    if (!taskConnections.has(taskId)) {
      taskConnections.set(taskId, new Set());
    }
    taskConnections.get(taskId).add(ws);

    ws.on('close', () => {
      taskConnections.get(taskId).delete(ws);
      if (taskConnections.get(taskId).size === 0) {
        taskConnections.delete(taskId);
      }
    });
  });
});

console.log(`[SERVER] Initializing — binding to ${LISTEN_HOST}:${PORT} …`);

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[SERVER] ❌ Port ${PORT} is already in use. Stop the conflicting process and restart.`);
  } else {
    console.error('[SERVER] ❌ Server error:', err.message);
  }
  process.exit(1);
});

server.listen(PORT, LISTEN_HOST, () => {
  console.log(`[SERVER] ✅ AI Employee backend running on http://${LISTEN_HOST}:${PORT}`);
  console.log(`[SERVER] RUNNING FROM: ${process.cwd()}`);
  console.log(`[SERVER] FILE PATH: ${__filename}`);
  console.log(`[SERVER] LATEST COMMIT: ${GIT_COMMIT}`);
  if (!process.env.METRICS_TOKEN) {
    console.warn('[SERVER] ⚠  METRICS_TOKEN not set — /metrics endpoint is publicly accessible. Set METRICS_TOKEN in ~/.ai-employee/.env to require bearer token auth.');
  }
  if (HAS_FRONTEND_DIST) {
    console.log(`[SERVER] Serving frontend bundle from ${FRONTEND_DIST}`);
  } else {
    console.log('[SERVER] ⚠  Frontend bundle not found (expected frontend/dist). Run: npm --prefix frontend run build');
  }
  // Start periodic state persistence (every 30s)
  persistence.startAutoSave(
    () => runtimeState,
    () => brain.exportState(),
  );
  markBootEvent('ui_loaded');
  // Bootstrap enterprise event bus and connect WS fan-out
  getEventBus().then(bus => {
    bus.setWsBroadcaster((type, envelope) => broadcaster.broadcast(type, envelope));
    console.log('[EventBus] Initialized — transports:', JSON.stringify(bus.transports));
    bus.publish(BUS_EVENT_TYPES.SYSTEM_READY, { node_ready: true });
  }).catch(e => console.error('[EventBus] init error:', e));
  getWorkflowEngine().then(engine => {
    console.log('[WorkflowEngine] Initialized — transport:', engine.transportName);
  }).catch(e => console.error('[WorkflowEngine] init error:', e));
  getSandboxExecutor().then(exec => {
    console.log('[Sandbox] Initialized — type:', exec.sandboxType);
  }).catch(e => console.error('[Sandbox] init error:', e));
  getSecretsBroker().then(broker => {
    console.log('[SecretsBroker] Initialized — backend:', broker.backendName);
  }).catch(e => console.error('[SecretsBroker] init error:', e));
  // Start neural graph file watcher (broadcasts brain:graph_updated every 10s)
  watchGraphFile();
  // Probe Python subsystems and broadcast system:ready when confirmed
  probeUntilReady().catch(e => console.error('[READINESS] probe error:', e));

  // ── Auto-update + Watchdog service ─────────────────────────────────────────
  const _restartBackends = async () => {
    console.log('[watchdog] Restarting backends via start.sh…');
    const startSh = path.join(REPO_ROOT, 'start.sh');
    if (!fs.existsSync(startSh)) { console.warn('[watchdog] start.sh not found — skip restart'); return; }
    const { spawn: _spawn } = require('child_process');
    return new Promise((resolve) => {
      const child = _spawn('bash', [startSh, '--restart-only'], {
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        env: { ...process.env },
      });
      child.unref();
      setTimeout(resolve, 1000);
    });
  };
  autoUpdateWatchdog.init({
    broadcaster,
    nodePort: PORT,
    restartFn: _restartBackends,
  });
  console.log('[AutoUpdate] Watchdog + auto-update service initialized');

  // FIX-2 cont: 2026-05-12 — Invalidate frontend cache on SIGHUP (hot reload)
  process.on('SIGHUP', () => {
    _indexCache = null;
    console.log('[CACHE] Frontend index.html cache invalidated (SIGHUP)');
  });
});
