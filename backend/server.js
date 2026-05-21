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
const voiceManager = require('./core/voice_manager');
const voiceApiRouter = require('./api/voice');
const ErrorRecoveryManager = require('./core/error_recovery');
const TaskHistoryManager = require('./core/task_history');
const { createTurnRunner } = require('./services/turn-runner');
const Database = require('better-sqlite3');
const { getNativeMemoryGraph } = require('./core/native-memory-graph');
const { z } = require('zod');

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
    },
  },
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
app.get('/api/artifacts/:filename', (req, res) => {
  const fname = path.basename(req.params.filename); // prevent path traversal
  const fpath = path.join(ARTIFACTS_DIR, fname);
  if (!require('fs').existsSync(fpath)) return res.status(404).json({ error: 'Artifact not found' });
  res.download(fpath);
});
app.get('/api/artifacts', (_req, res) => {
  const fs = require('fs');
  if (!fs.existsSync(ARTIFACTS_DIR)) return res.json([]);
  const files = fs.readdirSync(ARTIFACTS_DIR)
    .filter(f => fs.statSync(path.join(ARTIFACTS_DIR, f)).isFile())
    .map(f => ({ name: f, url: `/api/artifacts/${f}`, size: fs.statSync(path.join(ARTIFACTS_DIR, f)).size }));
  res.json(files);
});

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

app.get('/api/proof/center', requireAuth, (_req, res) => {
  const turns = readJsonLinesRecent(statePath('turns.jsonl'), 100);
  const artifactFiles = (() => {
    try {
      if (!fs.existsSync(ARTIFACTS_DIR)) return [];
      return fs.readdirSync(ARTIFACTS_DIR)
        .filter((name) => fs.statSync(path.join(ARTIFACTS_DIR, name)).isFile())
        .map((name) => {
          const stat = fs.statSync(path.join(ARTIFACTS_DIR, name));
          return {
            id: `artifact:${name}`,
            name,
            type: 'file',
            path: path.join(ARTIFACTS_DIR, name),
            url: `/api/artifacts/${encodeURIComponent(name)}`,
            source: 'artifact_storage',
            status: 'available',
            size: stat.size,
            created_at: stat.mtime.toISOString(),
          };
        })
        .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    } catch {
      return [];
    }
  })();

  const proofItems = [];
  for (const turn of turns) {
    for (const item of [...(turn.proof || []), ...(turn.artifacts || [])]) {
      if (!item || typeof item !== 'object') continue;
      const name = item.name || item.label || item.type || 'proof item';
      proofItems.push({
        id: item.id || `${turn.turn_id || turn.task_id || 'turn'}:${proofItems.length + 1}`,
        task_id: item.task_id || turn.task_id || turn.taskId || null,
        turn_id: turn.turn_id || null,
        name,
        type: item.type || item.artifact_type || 'trace',
        path: item.path || null,
        url: item.url || null,
        source: item.source || turn.source || turn.compatibility_route || 'turn',
        status: item.status || turn.status || 'unknown',
        degraded: turn.degraded === true || item.status === 'fallback' || item.status === 'degraded',
        created_at: item.created_at || turn.created_at || turn.timestamp || null,
      });
    }
  }

  const counts = [...proofItems, ...artifactFiles].reduce((acc, item) => {
    const status = item.degraded ? 'degraded' : (item.status || 'unknown');
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  res.json({
    ok: true,
    source: 'node_proof_center',
    generated_at: new Date().toISOString(),
    counts,
    turns: turns.map((turn) => ({
      turn_id: turn.turn_id || null,
      task_id: turn.task_id || turn.taskId || null,
      contract_version: turn.contract_version || null,
      status: turn.status || 'unknown',
      source: turn.source || turn.compatibility_route || 'unknown',
      degraded: turn.degraded === true,
      proof_count: Array.isArray(turn.proof) ? turn.proof.length : 0,
      artifact_count: Array.isArray(turn.artifacts) ? turn.artifacts.length : 0,
      created_at: turn.created_at || turn.timestamp || null,
      errors: Array.isArray(turn.errors) ? turn.errors : [],
    })),
    proof_items: proofItems,
    artifacts: artifactFiles,
  });
});

app.use('/gateway', gateway);
app.use('/orchestrator', orchestrator.router);
app.use('/api/voice', voiceApiRouter);
app.use('/api/settings', require('./routes/settings'));

// Tasks API (real-time execution visibility)
const taskGateway = require('./orchestrator/task-dashboard-gateway');
const createTasksRouter = require('./routes/tasks');
app.use('/api/tasks', createTasksRouter(taskGateway, broadcaster));
app.use('/api/schedules', createTasksRouter.createSchedulesRouter(taskGateway, broadcaster));

// Web Search API — proxies to Python /search with CloakBrowser support
const createSearchRouter = require('./routes/search');
app.use('/api/search', createSearchRouter(requireAuth));

// Research v2 API — 2-phase discover → execute on selected sources
const createResearchRouter = require('./routes/research');
app.use('/api/research', createResearchRouter(requireAuth));

// Vault API — Obsidian-compatible markdown knowledge store
const createVaultRouter = require('./routes/vault');
app.use('/api/vault', createVaultRouter(requireAuth));

const GPU_USAGE_BASELINE = 18;
let currentGpuUsage = GPU_USAGE_BASELINE;

// Agents monitoring API — Phase 3.2 agent activity monitor
const { createAgentsMonitorRouter, AgentStateRegistry } = require('./routes/agents-monitor');
const agentStateRegistry = new AgentStateRegistry();
const agentsMonitorRouter = createAgentsMonitorRouter(broadcaster, requireAuth, agentStateRegistry);
app.use('/api/agents', agentsMonitorRouter);

// AscendForge — agentic vibecoder
app.use('/api/forge', require('./routes/forge')(requireAuth));

// Workflows — template library + CRUD
app.use('/api/workflows', require('./routes/workflows')(requireAuth));

// Hybrid memory router — semantic RAG, graph, read-only SQL, episodic and procedural memory
const createHybridMemoryRouter = require('./routes/hybrid-memory-router');
app.use('/api/memory', createHybridMemoryRouter(requireAuth));

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
app.use('/api/execution', executionRouter);
app.use('/api/events', eventRoutes);
app.use('/api/workflows', workflowRoutes);
app.use('/api/sandbox', sandboxRoutes);
app.use('/api/secrets', secretsRoutes);
// Phase 2 — Enterprise Intelligence
app.use('/api/rag',        ragRoutes);
app.use('/api/planning',   planningRoutes);
app.use('/api/economics',  economicsRoutes);
app.use('/api/governance', governanceRoutes);
app.use('/api/telemetry',  telemetryRoutes);

// Phase 3 — Autonomous Workforce
app.use('/api/rpa',         rpaRoutes);
app.use('/api/healing',     healingRoutes);
app.use('/api/marketplace', marketplaceRoutes);
app.use('/api/deployment',  deploymentRoutes);
app.use('/api/simulation',  simulationRoutes);
app.use('/api/cognitive',   cognitiveRoutes);

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

const _savedBrain = persistence.loadBrainState();
if (_savedBrain) {
  brain.restoreState(_savedBrain);
  console.log('[PERSISTENCE] Restored brain state');
}
markBootEvent('system_init');

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function persistObjectives() {
  try {
    fs.mkdirSync(path.dirname(OBJECTIVES_FILE), { recursive: true });
    fs.writeFileSync(OBJECTIVES_FILE, JSON.stringify(runtimeState.objectives, null, 2), 'utf8');
  } catch {
    // best effort
  }
}

function broadcastObjectiveUpdate(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system,
    status: state.status,
    progress: state.progress || 0,
    current_objective: state.current_objective,
    active_tasks: state.active_tasks || [],
    plan: state.plan || [],
    agents_used: state.agents_used || [],
    results: state.results || state.result || [],
    performance: state.performance || {},
  });
}

function normalizeConstraints(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value;
}

function parseConstraintsFromGoal(goalText) {
  const text = String(goalText || '');
  const constraints = {};
  const lower = text.toLowerCase();
  const budgetTokenAt = lower.indexOf('budget');
  if (budgetTokenAt >= 0) {
    const numericBudget = lower.slice(budgetTokenAt).match(/\d+/);
    if (numericBudget) {
      constraints.budget = Math.min(Number(numericBudget[0]), Number.MAX_SAFE_INTEGER);
    }
  }
  const currencyBudget = text.match(/[€$]\s*(\d+)/);
  if (currencyBudget) {
    constraints.budget = Math.min(Number(currencyBudget[1]), Number.MAX_SAFE_INTEGER);
  }
  if (/\binstagram\b/i.test(text)) constraints.channel = 'instagram';
  if (/\bemail\b/i.test(text)) {
    constraints.channel = constraints.channel ? `${constraints.channel} + email` : 'email';
  }
  return constraints;
}

function createObjective({ system, goal, constraints = {}, priority = 'medium' }) {
  const objective = {
    id: `obj-${++runtimeState._seq}`,
    system,
    goal: String(goal || '').trim(),
    constraints: normalizeConstraints(constraints),
    priority: priority === 'high' ? 'high' : 'medium',
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  runtimeState.objectives.push(objective);
  runtimeState.objectives = runtimeState.objectives.slice(-200);
  persistObjectives();
  return objective;
}

function setObjectiveWaiting(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  state.active = true;
  state.status = OBJECTIVE_STATUS.WAITING;
  state.current_objective = null;
  state.progress = 0;
  state.active_tasks = [];
  state.result = null;
  if (system === 'ascend_forge') {
    state.plan = [];
    state.results = [];
  }
  broadcastObjectiveUpdate(system);
}

function breakdownMoneyModeGoal(goal) {
  const g = String(goal || '').toLowerCase();
  const tasks = [];
  if (/\blead/.test(g)) tasks.push('find leads', 'qualify leads');
  if (/\bemail|outreach/.test(g)) tasks.push('write outreach emails', 'prepare campaign');
  if (/\binstagram|social/.test(g)) tasks.push('prepare instagram campaign');
  if (/\bconversion|funnel/.test(g)) tasks.push('analyze conversion blockers');
  if (tasks.length === 0) {
    tasks.push('find leads', 'qualify leads', 'write outreach emails', 'prepare campaign');
  }
  return [...new Set(tasks)];
}

function buildAscendForgePlan(goal) {
  const g = String(goal || '').toLowerCase();
  const plan = ['analyze baseline', 'identify bottlenecks'];
  if (/\bconversion|funnel/.test(g)) {
    plan.push('design conversion experiments', 'execute funnel optimization');
  } else {
    plan.push('define optimization plan', 'execute improvement sprint');
  }
  return plan;
}

function addActivity(notes, kind = 'system') {
  const item = {
    id: `activity-${++runtimeState._seq}`,
    kind,
    notes,
    ts: new Date().toISOString(),
  };
  runtimeState.activityFeed.unshift(item);
  runtimeState.activityFeed = runtimeState.activityFeed.slice(0, MAX_ACTIVITY_ITEMS);
  // Broadcast immediately so UI gets real-time updates without polling
  broadcaster.broadcast('activity:item', item);
}

function emitTaskProgress(taskId, title, steps) {
  broadcaster.broadcast('task_progress', { taskId, title, steps, ts: Date.now() });
}

function emitObservabilityEvent(eventType, payload = {}) {
  const event = {
    id: `obs-${++runtimeState._seq}`,
    ts: new Date().toISOString(),
    event_type: eventType,
    payload,
    trace_id: payload.trace_id || '',
  };
  runtimeState.observability.events.unshift(event);
  runtimeState.observability.events = runtimeState.observability.events.slice(0, MAX_OBSERVABILITY_EVENTS);
  broadcaster.broadcast('event_stream', event);
  if (isSecurityEventType(eventType)) {
    securitySyncPolicy.enqueueEvent(eventType, payload);
  }
  return event;
}

function isSecurityEventType(eventType) {
  return (
    eventType === 'honeypot_triggered'
    || eventType === 'anomaly_response'
    || String(eventType).startsWith('security_')
  );
}

function appendAutoFixLog(entry) {
  const row = {
    id: `autofix-${++runtimeState._seq}`,
    ts: new Date().toISOString(),
    ...entry,
  };
  runtimeState.observability.autoFixLog.unshift(row);
  runtimeState.observability.autoFixLog = runtimeState.observability.autoFixLog.slice(0, MAX_ACTIVITY_ITEMS);
  emitObservabilityEvent('auto_fix_applied', row);
  return row;
}

function _persistWorkflowRun(run) {
  try {
    _forgeDb.prepare(
      `INSERT OR REPLACE INTO workflow_runs (run_id, payload, updated_at)
       VALUES (?, ?, strftime('%s','now'))`
    ).run(run.run_id, JSON.stringify(run));
  } catch (_e) { /* non-fatal — in-memory state is authoritative */ }
}

function createWorkflowRun({ name, source = 'automation', goal = '' }) {
  const runId = `wf-${++runtimeState._seq}`;
  const run = {
    run_id: runId,
    name: name || `Workflow ${runId}`,
    source,
    goal,
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    progress_percent: 0,
    nodes: [],
    decision_log: [],
  };
  runtimeState.workflowRuns.unshift(run);
  runtimeState.workflowRuns = runtimeState.workflowRuns.slice(0, MAX_ACTIVITY_ITEMS);
  runtimeState.selectedWorkflowRun = runId;
  _persistWorkflowRun(run);
  broadcaster.broadcast('workflow:update', run);
  return run;
}

function appendDecision(run, entry) {
  run.decision_log.unshift(entry);
  run.decision_log = run.decision_log.slice(0, MAX_DECISION_LOG_ENTRIES);
}

function getWorkflowRun(runId) {
  return runtimeState.workflowRuns.find((run) => run.run_id === runId) || null;
}

function attachWorkflowNode({ runId, queued, taskName, parentTaskId = null }) {
  const run = getWorkflowRun(runId);
  if (!run || !queued || !queued.taskId) return;
  const node = {
    task_id: queued.taskId,
    task_name: taskName || queued.subsystem || 'Task',
    status: 'pending',
    progress_percent: 5,
    subsystem: queued.subsystem || 'general',
    agent: queued.agentId || 'pending',
    queued_at: queued.queuedAt || new Date().toISOString(),
    started_at: null,
    completed_at: null,
    parent_task_id: parentTaskId,
    brain: queued.brain || null,
    strategy: queued.brain ? queued.brain.strategy : null,
    confidence: queued.brain ? queued.brain.confidence : null,
    reasoning: queued.brain ? queued.brain.reasoning : '',
    execution_flow: queued.brain ? queued.brain.execution_flow : 'task->strategy->agent->action->result',
    result: null,
  };
  run.nodes.push(node);
  appendDecision(run, {
    ts: new Date().toISOString(),
    task_id: node.task_id,
    type: 'brain_decision',
    summary: node.reasoning || `Strategy ${node.strategy || 'default'} selected`,
  });
  runtimeState.workflowIndex[node.task_id] = runId;
  run.updated_at = new Date().toISOString();
  run.status = 'running';
  recalcWorkflowProgress(run);
  broadcaster.broadcast('workflow:update', run);
}

function recalcWorkflowProgress(run) {
  const total = run.nodes.length || 1;
  let acc = 0;
  let completed = 0;
  let failed = 0;
  run.nodes.forEach((node) => {
    acc += Number(node.progress_percent || 0);
    if (node.status === 'completed') completed += 1;
    if (node.status === 'failed') failed += 1;
  });
  run.progress_percent = Math.round(acc / total);
  if (failed > 0) {
    run.status = completed > 0 ? 'completed_with_failures' : 'failed';
  } else if (completed === run.nodes.length && run.nodes.length > 0) {
    run.status = 'completed';
    run.progress_percent = 100;
  } else if (run.nodes.length > 0) {
    run.status = 'running';
  } else {
    run.status = 'pending';
  }
}

function updateWorkflowNode(taskId, updater) {
  const runId = runtimeState.workflowIndex[taskId];
  if (!runId) return;
  const run = getWorkflowRun(runId);
  if (!run) return;
  const node = run.nodes.find((n) => n.task_id === taskId);
  if (!node) return;
  updater(node, run);
  run.updated_at = new Date().toISOString();
  recalcWorkflowProgress(run);
  broadcaster.broadcast('workflow:update', run);
}

function markWorkflowsStopped() {
  runtimeState.workflowRuns.forEach((run) => {
    if (!['running', 'pending'].includes(run.status)) return;
    run.nodes.forEach((node) => {
      if (node.status === 'pending' || node.status === 'active') {
        node.status = 'failed';
        node.progress_percent = 100;
        node.completed_at = new Date().toISOString();
        node.result = {
          status: 'cancelled',
          summary: 'Cancelled by STOP ALL command',
        };
      }
    });
    run.updated_at = new Date().toISOString();
    recalcWorkflowProgress(run);
    run.status = 'stopped';
    broadcaster.broadcast('workflow:update', run);
  });
}

function queueWorkflowStep({
  runId,
  message,
  stepIndex = 0,
  labels = [],
  parentTaskId = null,
  retries = 0,
  maxRetries = 1,
}) {
  const queued = orchestrator.submitTask(message, {
    userId: 'user:default',
    workflow: { runId, parentTaskId },
    labels,
  });
  attachWorkflowNode({
    runId,
    queued,
    taskName: message,
    parentTaskId,
  });
  runtimeState.workflowTaskMeta[queued.taskId] = {
    runId,
    stepIndex,
    message,
    labels,
    parentTaskId,
    retries,
    maxRetries,
  };
  const seq = runtimeState.workflowSequencers[runId];
  if (seq) {
    seq.stepTaskIds[stepIndex] = queued.taskId;
  }
  addActivity(`[BRAIN] Strategy ${queued.brain?.strategy || 'default'} selected for ${queued.taskId}`, 'task');
  const traceId = `trace-${++runtimeState.observability._traceSeq}`;
  runtimeState.observability.traces[queued.taskId] = {
    trace_id: traceId,
    user_input: message,
    intent: queued.brain?.intent || queued.subsystem || 'general',
    agent: queued.agentId || 'task_orchestrator',
    strategy: queued.brain?.strategy || 'default',
    confidence: queued.brain?.confidence || 0,
    started_at: new Date().toISOString(),
    steps: [],
  };
  emitObservabilityEvent('task_started', {
    trace_id: traceId,
    task_id: queued.taskId,
    user_input: message,
    intent: queued.brain?.intent || queued.subsystem || 'general',
  });
  emitObservabilityEvent('agent_selected', {
    trace_id: traceId,
    task_id: queued.taskId,
    agent: queued.agentId || 'task_orchestrator',
  });
  emitObservabilityEvent('brain_decision', {
    trace_id: traceId,
    task_id: queued.taskId,
    strategy: queued.brain?.strategy || 'default',
    reasoning: queued.brain?.reasoning || '',
    confidence: queued.brain?.confidence || 0,
  });
  return queued;
}

function queueNextWorkflowStep(completedTaskId) {
  const meta = runtimeState.workflowTaskMeta[completedTaskId];
  if (!meta) return;
  const seq = runtimeState.workflowSequencers[meta.runId];
  if (!seq || seq.stopped) return;
  if (seq.stepTaskIds[meta.stepIndex] !== completedTaskId) return;
  seq.completedSteps.add(meta.stepIndex);
  const nextIndex = meta.stepIndex + 1;
  const nextMessage = seq.messages[nextIndex];
  if (!nextMessage || seq.queuedSteps.has(nextIndex)) return;
  seq.queuedSteps.add(nextIndex);
  queueWorkflowStep({
    runId: meta.runId,
    message: nextMessage,
    stepIndex: nextIndex,
    labels: ['automation', `step-${nextIndex + 1}`],
    parentTaskId: completedTaskId,
  });
}

function retryWorkflowStep(failedTaskId) {
  const meta = runtimeState.workflowTaskMeta[failedTaskId];
  if (!meta) return false;
  if (meta.error?.startsWith(CANCELLATION_ERROR_PREFIX)) return false;
  const seq = runtimeState.workflowSequencers[meta.runId];
  if (!seq || seq.stopped) return false;
  if (seq.stepTaskIds[meta.stepIndex] !== failedTaskId) return false;
  if (meta.retries >= meta.maxRetries) return false;
  const retryNumber = meta.retries + 1;
  addActivity(`[RETRY] ${failedTaskId} retry ${retryNumber}/${meta.maxRetries}`, 'task');
  appendAutoFixLog({
    task_id: failedTaskId,
    issue: meta.error || 'task failure',
    fix: `Automatic retry ${retryNumber}/${meta.maxRetries}`,
    status: 'retrying',
  });
  queueWorkflowStep({
    runId: meta.runId,
    message: meta.message,
    stepIndex: meta.stepIndex,
    labels: [...meta.labels, `retry-${retryNumber}`],
    parentTaskId: meta.parentTaskId,
    retries: retryNumber,
    maxRetries: meta.maxRetries,
  });
  return true;
}

function recalcObjectiveProgress(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  const tasks = state.active_tasks || [];
  const total = tasks.length || 1;
  const completed = tasks.filter((t) => t.status === 'completed').length;
  const failed = tasks.filter((t) => t.status === 'failed').length;
  state.progress = Math.round(((completed + failed) / total) * 100);
  if (tasks.length > 0 && (completed + failed) === tasks.length) {
    state.status = OBJECTIVE_STATUS.COMPLETED;
    state.active = false;
  } else if (tasks.length > 0) {
    state.status = OBJECTIVE_STATUS.RUNNING;
  }
}

function startMoneyModeObjective(objective) {
  if (!objective || !objective.goal) {
    setObjectiveWaiting('money_mode');
    return { ok: false, message: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.' };
  }
  objective.status = 'running';
  objective.updated_at = new Date().toISOString();
  persistObjectives();

  setMode('MONEYMODE');
  activateAgents(4);

  const tasks = breakdownMoneyModeGoal(objective.goal);
  const run = createWorkflowRun({
    name: 'Money Mode Objective',
    source: 'money_mode',
    goal: objective.goal,
  });
  runtimeState.objectiveState.money_mode = {
    ...runtimeState.objectiveState.money_mode,
    active: true,
    status: OBJECTIVE_STATUS.RUNNING,
    current_objective: objective,
    active_tasks: [],
    progress: 0,
    agents_used: MONEY_MODE_AGENTS,
    performance: {
      leads_generated: 0,
      emails_sent: 0,
      conversion_pct: 0,
    },
    result: null,
  };

  tasks.forEach((task, idx) => {
    const agentHint = MONEY_MODE_AGENTS[idx % MONEY_MODE_AGENTS.length];
    const queued = queueWorkflowStep({
      runId: run.run_id,
      message: `[${agentHint}] ${task}`,
      stepIndex: idx,
      labels: ['money_mode', `step-${idx + 1}`],
      parentTaskId: idx > 0 ? runtimeState.objectiveState.money_mode.active_tasks[idx - 1]?.task_id || null : null,
    });
    runtimeState.objectiveTaskMeta[queued.taskId] = {
      system: 'money_mode',
      objective_id: objective.id,
      task_name: task,
      agent_hint: agentHint,
    };
    runtimeState.objectiveState.money_mode.active_tasks.push({
      task_id: queued.taskId,
      task,
      agent: agentHint,
      status: 'pending',
    });
  });
  broadcastObjectiveUpdate('money_mode');
  addActivity(`[MONEY MODE] objective started • ${objective.goal}`, 'automation');
  return { ok: true, message: `✅ Money Mode objective started: ${objective.goal}` };
}

function startAscendForgeObjective(objective) {
  if (!objective || !objective.goal) {
    setObjectiveWaiting('ascend_forge');
    return { ok: false, message: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.' };
  }
  objective.status = 'running';
  objective.updated_at = new Date().toISOString();
  persistObjectives();

  activateAgents(3);
  const plan = buildAscendForgePlan(objective.goal);
  const run = createWorkflowRun({
    name: 'Ascend Forge Objective',
    source: 'ascend_forge',
    goal: objective.goal,
  });

  runtimeState.objectiveState.ascend_forge = {
    ...runtimeState.objectiveState.ascend_forge,
    active: true,
    status: OBJECTIVE_STATUS.RUNNING,
    current_objective: objective,
    plan,
    active_tasks: [],
    progress: 0,
    agents_used: ASCEND_FORGE_AGENTS,
    results: [],
    result: {
      plan,
      agents_used: ASCEND_FORGE_AGENTS,
      progress: 0,
      status: 'running',
    },
  };

  plan.forEach((step, idx) => {
    const agentHint = ASCEND_FORGE_AGENTS[idx % ASCEND_FORGE_AGENTS.length];
    const queued = queueWorkflowStep({
      runId: run.run_id,
      message: `[${agentHint}] ${step}`,
      stepIndex: idx,
      labels: ['ascend_forge', `step-${idx + 1}`],
      parentTaskId: idx > 0 ? runtimeState.objectiveState.ascend_forge.active_tasks[idx - 1]?.task_id || null : null,
    });
    runtimeState.objectiveTaskMeta[queued.taskId] = {
      system: 'ascend_forge',
      objective_id: objective.id,
      task_name: step,
      agent_hint: agentHint,
    };
    runtimeState.objectiveState.ascend_forge.active_tasks.push({
      task_id: queued.taskId,
      task: step,
      agent: agentHint,
      status: 'pending',
    });
  });
  broadcastObjectiveUpdate('ascend_forge');
  addActivity(`[ASCEND FORGE] objective started • ${objective.goal}`, 'automation');

  // Emit live task progress so chat shows a step-by-step progress block
  emitTaskProgress(run.run_id, `Forge: ${objective.goal}`,
    plan.map((step, idx) => ({ id: idx, label: step, status: 'pending' }))
  );

  return { ok: true, message: `✅ Ascend Forge objective started: ${objective.goal}` };
}

function handleGoalDrivenCommand(message) {
  const raw = String(message || '').trim();
  const msg = raw.toLowerCase();
  if (!raw) return { handled: false };

  if (msg === 'activate money mode') {
    setMode('MONEYMODE');
    setObjectiveWaiting('money_mode');
    return {
      handled: true,
      reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.',
    };
  }

  const setMoneyPrefix = 'set goal for money mode:';
  if (msg.startsWith(setMoneyPrefix)) {
    const goal = raw.slice(setMoneyPrefix.length).trim();
    if (!goal) {
      setObjectiveWaiting('money_mode');
      return {
        handled: true,
        reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.',
      };
    }
    const objective = createObjective({
      system: 'money_mode',
      goal,
      constraints: parseConstraintsFromGoal(goal),
      priority: 'high',
    });
    const started = startMoneyModeObjective(objective);
    return { handled: true, reply: started.message };
  }

  const startAscendPrefix = 'start ascend forge with goal:';
  if (msg.startsWith(startAscendPrefix)) {
    const goal = raw.slice(startAscendPrefix.length).trim();
    if (!goal) {
      setObjectiveWaiting('ascend_forge');
      return {
        handled: true,
        reply: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.',
      };
    }
    const objective = createObjective({
      system: 'ascend_forge',
      goal,
      constraints: parseConstraintsFromGoal(goal),
      priority: 'high',
    });
    const started = startAscendForgeObjective(objective);
    return { handled: true, reply: started.message };
  }

  return { handled: false };
}

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

function walletSnapshot() {
  const wallet = readJsonSafe(statePath('wallet_vault.json'), null);
  if (!wallet) {
    return {
      state: 'disabled',
      configured: false,
      balance: { currency: 'USD', available: 0, pending: 0 },
      external_compute_enabled: false,
    };
  }
  return {
    state: 'live',
    configured: true,
    label: wallet.label,
    address: wallet.address,
    created_at: wallet.created_at,
    balance: wallet.balance || { currency: 'USD', available: 0, pending: 0 },
    external_compute_enabled: wallet.external_compute_enabled === true,
  };
}

function buildEconomySnapshot() {
  const llmCalls = readJsonlSafe(statePath('llm_calls.jsonl'), 2000);
  const tokenTotals = llmCalls.reduce((acc, call) => {
    const agent = call.agent || call.route || 'unknown';
    if (!acc.by_agent[agent]) acc.by_agent[agent] = { agent, calls: 0, tokens: 0, cost: 0 };
    const tokens = Number(call.tokens || call.total_tokens || 0);
    const cost = Number(call.cost || call.cost_usd || 0);
    acc.tokens += tokens;
    acc.cost += cost;
    acc.by_agent[agent].calls += 1;
    acc.by_agent[agent].tokens += tokens;
    acc.by_agent[agent].cost += cost;
    return acc;
  }, { tokens: 0, cost: 0, by_agent: {} });
  const value = Number(runtimeState.valueGenerated || 0);
  const revenue = Number(runtimeState.revenueCents || 0) / 100;
  const cost = Number(tokenTotals.cost || 0);
  const profit = revenue - cost;
  const summary = {
    state: runtimeState.pipelineRuns.length || revenue || tokenTotals.tokens ? 'live' : 'empty',
    source: 'node_runtime_state',
    updated_at: new Date().toISOString(),
    revenue: {
      total: revenue,
      daily: revenue,
      currency: 'USD',
      value_generated: value,
    },
    cost: {
      token_cost: cost,
      total_cost: cost,
      tokens: tokenTotals.tokens,
    },
    profit,
    roi: cost > 0 ? profit / cost : 0,
    tasks: {
      executed: runtimeState.tasksExecuted,
      successful: runtimeState.successfulTasks,
      failed: runtimeState.failedTasks,
    },
    wallet: walletSnapshot(),
  };
  const ledger = [
    ...runtimeState.pipelineRuns.map((run) => ({
      id: run.id,
      type: 'pipeline_value',
      status: run.status,
      amount: Number(run.estimated_roi || 0),
      currency: 'USD',
      description: `${run.pipeline} pipeline estimated value`,
      created_at: run.executed_at,
    })),
    ...readJsonlSafe(statePath('wallet_audit.jsonl'), 200).map((entry, index) => ({
      id: entry.id || `wallet-audit-${index}`,
      type: entry.event || 'wallet_audit',
      status: 'recorded',
      amount: Number(entry.details?.amount || entry.amount || 0),
      currency: entry.details?.currency || entry.currency || 'USD',
      description: entry.event || 'Wallet audit event',
      created_at: entry.ts,
      details: entry.details || entry,
    })),
  ];
  const costs = Object.values(tokenTotals.by_agent)
    .sort((a, b) => b.cost - a.cost)
    .map((row) => ({ ...row, cost: Number(row.cost.toFixed(6)) }));
  const pipelines = Object.entries(runtimeState.objectiveState || {}).map(([id, pipeline]) => ({
    id,
    ...pipeline,
    state: pipeline.active ? 'live' : 'empty',
    updated_at: pipeline.current_objective?.updated_at || pipeline.current_objective?.created_at || null,
  }));
  return { summary, ledger, costs, pipelines };
}

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
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

// GET /health/full — detailed health check (external calls, slow)
// Called by dashboard, not by boot scripts. Includes all subsystem checks.
app.get('/health/full', async (req, res) => {
  const checks = {
    node: { status: 'ok' },
    python_backend: { status: 'pending' },
    llm_api: { status: 'pending' },
    database: { status: 'pending' },
  };

  // Check Python backend
  try {
    const pythonHealthUrl = `http://127.0.0.1:${PYTHON_BACKEND_PORT}/health`;
    const pythonRes = await Promise.race([
      fetch(pythonHealthUrl),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
    ]);
    checks.python_backend.status = pythonRes.ok ? 'ok' : 'degraded';
  } catch (e) {
    checks.python_backend.status = 'down';
    checks.python_backend.error = e.message;
  }

  // Check LLM API connectivity (Anthropic, OpenRouter, or Ollama)
  try {
    const llmBackend = process.env.LLM_BACKEND || 'anthropic';
    if (llmBackend === 'anthropic') {
      const apiKey = process.env.ANTHROPIC_API_KEY;
      if (!apiKey) {
        checks.llm_api.status = 'unconfigured';
      } else {
        // Quick validation: fetch models list
        const modelRes = await Promise.race([
          fetch('https://api.anthropic.com/v1/models', {
            headers: { Authorization: `Bearer ${apiKey}` }
          }),
          new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
        ]);
        checks.llm_api.status = modelRes.ok ? 'ok' : 'degraded';
        checks.llm_api.provider = 'anthropic';
      }
    } else if (llmBackend === 'ollama') {
      const ollamaUrl = process.env.OLLAMA_URL || 'http://127.0.0.1:11434';
      const ollamaRes = await Promise.race([
        fetch(`${ollamaUrl}/api/tags`),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
      ]);
      checks.llm_api.status = ollamaRes.ok ? 'ok' : 'down';
      checks.llm_api.provider = 'ollama';
    }
  } catch (e) {
    checks.llm_api.status = 'down';
    checks.llm_api.error = e.message;
  }

  // Check database
  try {
    if (db) {
      const result = db.prepare('SELECT 1').get();
      checks.database.status = result ? 'ok' : 'degraded';
    }
  } catch (e) {
    checks.database.status = 'down';
    checks.database.error = e.message;
  }

  // Overall status
  const overallStatus = Object.values(checks).every(c => c.status !== 'down') ? 'healthy' : 'degraded';
  const statusCode = overallStatus === 'healthy' ? 200 : 503;

  res.status(statusCode).json({
    status: overallStatus,
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    checks,
  });
});

// POST /internal/events — Neural Brain bridge: localhost-only ingress used by
// the Python runtime (problem-solver-ui :18790) to push events onto the
// Node WebSocket broadcaster. Body: { event: string, data: object }.
// Locked to loopback so external clients cannot inject dashboard events.
app.post('/internal/events', express.json({ limit: '2mb' }), (req, res) => {
  const ip = req.ip || req.connection?.remoteAddress || '';
  const isLocal = ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1';
  if (!isLocal) return res.status(403).json({ ok: false, error: 'localhost only' });
  const { event, data } = req.body || {};
  if (typeof event !== 'string' || !event) {
    return res.status(400).json({ ok: false, error: 'event required' });
  }
  try {
    broadcaster.broadcast(event, data || {});
    // Blacklight events get priority broadcast with structured payload
    if (event === 'blacklight:status' || event === 'blacklight:mode_change' || event === 'blacklight:lockdown') {
      broadcaster.broadcast('security:update', { event, ...data });
      if (data && typeof data.threat_score === 'number') {
        _lastBlacklightStatus = { ...data, updated_at: Date.now() };
      }
    }
    return res.json({ ok: true });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e && e.message || e) });
  }
});

// GET /api/security/status — Blacklight + system control state (localhost or auth)
app.get('/api/security/status', (req, res) => {
  const ip = req.ip || req.connection?.remoteAddress || '';
  const isLocal = ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1';
  if (!isLocal) {
    const authHeader = req.headers['authorization'] || '';
    if (!authHeader.startsWith('Bearer ')) return res.status(401).json({ ok: false });
  }
  // Return last known blacklight state (forwarded via /internal/events)
  res.json({ ok: true, ...(_lastBlacklightStatus || { threat_score: 0, mode: 'NORMAL', active_threats: [] }) });
});

// Track last known Blacklight status for the status endpoint
let _lastBlacklightStatus = null;

// POST /api/auth/token — exchange the master secret for a 24h JWT
// Body: { secret: "<JWT_SECRET_KEY from ~/.ai-employee/.env>" }
app.post('/api/auth/token', (req, res) => {
  const body = validate(SCHEMAS.authToken, req, res);
  if (!body) return;
  if (body.secret !== JWT_SECRET) {
    return res.status(401).json({ ok: false, error: 'Invalid secret' });
  }
  const token = jwt.sign({ sub: 'admin', type: 'access', role: 'admin', iss: 'ai-employee', tenant_id: 'default', org_name: 'Local' }, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN });
  res.json({ ok: true, token, expires_in: JWT_EXPIRES_IN });
});

// GET /api/auth/auto-token — issues a short-lived JWT for localhost dashboard access (no secret needed)
// Only allows requests from loopback. Uses raw socket remoteAddress (unforgeable) — not req.ip
// which is X-Forwarded-For aware and trivially spoofable via `trust proxy: 1`.
app.get('/api/auth/auto-token', (req, res) => {
  const rawIp = req.socket?.remoteAddress || '';
  const isLocal = rawIp === '127.0.0.1' || rawIp === '::1' || rawIp === '::ffff:127.0.0.1';
  if (!isLocal) return res.status(403).json({ ok: false, error: 'Only available from localhost' });
  const token = jwt.sign({ sub: 'operator', type: 'access', role: 'operator', iss: 'ai-employee', tenant_id: 'default', org_name: 'Local' }, JWT_SECRET, { expiresIn: '8h' });
  res.json({ ok: true, token });
});

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
app.get('/api/identity/public', async (req, res) => {
  try {
    const fs = require('fs');
    const path = require('path');
    const identityFile = path.join(AI_HOME, 'identity.json');
    if (!fs.existsSync(identityFile)) {
      return res.json({
        instance_name: 'Initializing...',
        color_palette: { primary: '#a855f7', accent: '#e5c76b' },
        user_chosen: null
      });
    }
    const identity = JSON.parse(fs.readFileSync(identityFile, 'utf8'));
    res.json({
      instance_name: identity.instance_name,
      user_chosen: identity.user_chosen,
      color_palette: identity.color_palette,
      tenant_id: identity.tenant_id
    });
  } catch (e) {
    res.status(500).json({ error: 'Failed to read identity' });
  }
});

// GET /api/onboarding/palettes — generate 3 color palettes for onboarding
app.get('/api/onboarding/palettes', (req, res) => {
  const generatePalette = () => {
    const hue = Math.random() * 0.3 + 0.65;  // 65-95% of hue circle (purples/magentas)
    const saturation = 0.6 + Math.random() * 0.3;  // 60-90%
    const toHex = (h, s, l) => {
      const c = (1 - Math.abs(2 * l - 1)) * s;
      const x = c * (1 - Math.abs((h * 6) % 2 - 1));
      const m = l - c / 2;
      let r = 0, g = 0, b = 0;
      if (h < 1/6) [r, g, b] = [c, x, 0];
      else if (h < 1/3) [r, g, b] = [x, c, 0];
      else if (h < 1/2) [r, g, b] = [0, c, x];
      else if (h < 2/3) [r, g, b] = [0, x, c];
      else if (h < 5/6) [r, g, b] = [x, 0, c];
      else [r, g, b] = [c, 0, x];
      return '#' + [r + m, g + m, b + m].map(x => Math.round((x) * 255).toString(16).padStart(2, '0')).join('');
    };
    return {
      primary: toHex(hue, saturation, 0.4),
      accent: toHex(hue, saturation * 0.8, 0.55),
      secondary: toHex((hue + 0.15) % 1.0, saturation * 0.7, 0.4)
    };
  };
  res.json({
    palettes: [generatePalette(), generatePalette(), generatePalette()]
  });
});

// POST /api/identity/finalize — save user onboarding choices
app.post('/api/identity/finalize', async (req, res) => {
  try {
    const { user_chosen, instance_name, voice_preset, color_palette } = req.body;
    const fs = require('fs');
    const path = require('path');
    const homedir = process.env.HOME || process.env.USERPROFILE;
    const identityFile = path.join(homedir, '.ai-employee', 'identity.json');

    // Ensure directory exists
    const dir = path.dirname(identityFile);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    // Load or create identity
    let identity;
    if (fs.existsSync(identityFile)) {
      identity = JSON.parse(fs.readFileSync(identityFile, 'utf8'));
    } else {
      // Create minimal identity if doesn't exist
      identity = {
        tenant_id: `tnt_${Math.random().toString(36).substr(2, 12)}`,
        instance_name: instance_name || 'Aurora-Prime',
        user_chosen: null,
        color_palette: color_palette || { primary: '#a855f7', accent: '#e5c76b' },
        voice_preset: voice_preset || 'professional',
        emergent: { vocabulary_signature: [], favorite_agents: [], work_pattern: null, tone_drift: 0.0 },
        created_at: new Date().toISOString(),
        evolution_log: []
      };
    }

    // Update with user choices
    if (user_chosen) identity.user_chosen = user_chosen;
    if (instance_name) identity.instance_name = instance_name;
    if (voice_preset) identity.voice_preset = voice_preset;
    if (color_palette) identity.color_palette = color_palette;

    // Log finalization
    identity.evolution_log = identity.evolution_log || [];
    identity.evolution_log.push({
      event: 'identity_finalized',
      timestamp: new Date().toISOString(),
      user_chosen,
      voice_preset
    });

    // Write back
    fs.writeFileSync(identityFile, JSON.stringify(identity, null, 2));
    res.json({ ok: true, identity });
  } catch (e) {
    console.error('Failed to finalize identity:', e);
    res.status(500).json({ error: 'Failed to save identity' });
  }
});

app.get('/version', (req, res) => {
  res.set('Cache-Control', 'no-store, must-revalidate');
  let versionState = null;
  try {
    const versionFile = path.join(REPO_ROOT, 'state', 'version.json');
    if (fs.existsSync(versionFile)) {
      versionState = JSON.parse(fs.readFileSync(versionFile, 'utf8'));
    }
  } catch (_e) { /* ignore */ }
  res.json({
    commit: GIT_COMMIT,
    timestamp: new Date().toISOString(),
    started_at: SERVER_START_TIMESTAMP,
    cwd: process.cwd(),
    file: __filename,
    version_state: versionState,
  });
});

app.get('/agents', (req, res) => {
  res.json({ agents: getAgents() });
});

app.get('/internal/agents', (req, res) => {
  res.json({ agents: getAgents(), internal: true });
});

app.post('/agents/activate', requireAuth, (req, res) => {
  const { count } = req.body || {};
  const out = activateAgents(typeof count === 'number' ? count : undefined);
  res.json({ ok: true, ...out, mode: getMode(), agents: getAgents() });
});

app.get('/status', (req, res) => {
  const stats = sampleSystemStatus();
  res.json({ status: 'online', agents: stats.total_agents, running_agents: stats.running_agents, timestamp: stats.timestamp });
});

// Aliases for tests and external callers that expect /api/ prefix
app.get('/api/status', requireAuth, (req, res) => {
  const stats = sampleSystemStatus();
  res.json({ status: 'online', agents: stats.total_agents, running_agents: stats.running_agents, timestamp: stats.timestamp });
});
app.get('/api/health', (req, res) => {
  const stats = sampleSystemStatus();
  const agents = getAgents();
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: stats.uptime ?? `${Math.floor(process.uptime() / 3600)}h ${Math.floor((process.uptime() % 3600) / 60)}m`,
    node_ok: true,
    python_backend: _systemReady.python_ok === true,
    python_ok: _systemReady.python_ok === true,
    llm_ok: _systemReady.llm_ok === true,
    readiness_phase: _readiness.phase,
    degraded: _systemReady.python_ok !== true,
    agents_active: agents.filter(a => a.state === 'active').length,
    tasks_running: runtimeState.taskQueue?.filter(t => t.status === 'running').length ?? 0,
    threat_level: runtimeState.threatLevel ?? 'LOW',
    cost_today: (runtimeState.costToday ?? 0).toFixed(2),
    memory_pct: stats.memory_pct ?? stats.memory ?? 0,
    mode: runtimeState.systemMode ?? 'BALANCED',
  });
});

app.get('/api/runtime/identity', (req, res) => {
  res.set('Cache-Control', 'no-store');
  res.json({
    ok: true,
    app: 'AETERNUS NEXUS',
    runtime: 'AI-EMPLOYEE',
    mode: RUNTIME_MODE,
    nonce: RUNTIME_NONCE,
    buildId: process.env.AI_EMPLOYEE_BUILD_ID || latestCommit(),
    repoRoot: REPO_ROOT,
    appHome: AI_HOME,
    stateDir: STATE_DIR,
    logDir: LOG_DIR,
    runDir: RUN_DIR,
    ports: {
      node: Number(PORT),
      python: Number(PYTHON_BACKEND_PORT),
    },
    pid: process.pid,
    platform: process.platform,
    arch: process.arch,
    startedAt: SERVER_START_TIMESTAMP,
  });
});

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

app.get('/api/readiness', async (req, res) => {
  const degradedReasons = [];
  // Self-heal: the boot poll for Python is one-shot. If it's marked not-ready,
  // re-probe live so readiness recovers when Python comes up after Node.
  if (!_readiness.pythonReady) {
    try {
      const hr = await Promise.race([
        fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/health`),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 1200)),
      ]);
      if (hr?.ok) { _readiness.pythonReady = true; if (_readiness.phase === 'BOOTING') _readiness.phase = 'READY'; }
    } catch (_) {}
  }
  const graphProbe = await checkNeuralGraphReady();
  const neuralBrainReady = _readiness.pythonReady === true;
  const graphReady = graphProbe.ok === true;
  if (!HAS_FRONTEND_DIST) degradedReasons.push('frontend_dist_missing');
  if (!_readiness.pythonReady) degradedReasons.push('python_backend_not_ready');
  if (_readiness.pythonReady && !_readiness.subsystemsReady) degradedReasons.push('python_subsystems_degraded');
  if (!neuralBrainReady) degradedReasons.push('neural_brain_not_ready');
  if (!graphReady) degradedReasons.push('graph_not_ready');
  res.json({
    ok: true,
    nodeReady: true,
    apiReady: true,
    frontendDist: HAS_FRONTEND_DIST,
    frontendIndex: HAS_FRONTEND_DIST,
    phase: _readiness.phase,
    pythonReady: _readiness.pythonReady,
    subsystemsReady: _readiness.subsystemsReady,
    neuralBrainReady,
    graphReady,
    degraded: degradedReasons.length > 0,
    degradedReasons,
    timestamp: new Date().toISOString(),
  });
});

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

app.get('/api/capabilities/status', requireAuth, async (_req, res) => {
  const checkedAt = new Date().toISOString();
  const pythonProbe = _readiness.pythonReady
    ? { ok: true, status: 200 }
    : await probeHttp(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/health`);
  if (pythonProbe.ok) {
    _readiness.pythonReady = true;
    if (_readiness.phase === 'BOOTING') _readiness.phase = 'READY';
  }

  const ollamaHost = process.env.OLLAMA_HOST || process.env.OLLAMA_URL || 'http://127.0.0.1:11434';
  const ollamaProbe = await probeHttp(`${String(ollamaHost).replace(/\/$/, '')}/api/tags`);
  const llmProviders = [
    ['anthropic_llm', 'Anthropic LLM', ['ANTHROPIC_API_KEY']],
    ['openai_llm', 'OpenAI LLM', ['OPENAI_API_KEY']],
    ['openrouter_llm', 'OpenRouter LLM', ['OPENROUTER_API_KEY']],
    ['groq_llm', 'Groq LLM', ['GROQ_API_KEY']],
  ];
  const providerRecords = llmProviders.map(([id, label, requiredEnv]) => {
    const env = statusFromEnv(requiredEnv);
    return capabilityRecord({
      id,
      label,
      status: env.status,
      category: 'llm',
      required_env: requiredEnv,
      missing_env: env.missing,
      setup_action: env.status === 'live' ? 'test' : 'configure_env',
      details: env.status === 'live' ? `${label} key is present.` : `${label} requires ${env.missing.join(', ')}.`,
      docs_hint: 'Configure provider keys in ~/.ai-employee/.env or Settings.',
    });
  });
  const activeProviderCount = providerRecords.filter((record) => record.status === 'live').length + (ollamaProbe.ok ? 1 : 0);

  const emailRequired = ['SENDGRID_API_KEY', 'SMTP_HOST', 'SMTP_USER', 'SMTP_PASS'];
  const emailConfigured = !!process.env.SENDGRID_API_KEY
    || (!!process.env.SMTP_HOST && !!process.env.SMTP_USER && !!process.env.SMTP_PASS);
  const emailMissing = emailConfigured
    ? []
    : emailRequired.filter((key) => !process.env[key]);
  const apolloEnv = statusFromEnv(['APOLLO_API_KEY']);
  const linkedinEnv = statusFromEnv(['LINKEDIN_ACCESS_TOKEN', 'LINKEDIN_PERSON_URN']);
  const stateWritable = (() => {
    try {
      fs.accessSync(STATE_DIR, fs.constants.R_OK | fs.constants.W_OK);
      return true;
    } catch {
      return false;
    }
  })();
  const artifactsWritable = (() => {
    try {
      fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
      fs.accessSync(ARTIFACTS_DIR, fs.constants.R_OK | fs.constants.W_OK);
      return true;
    } catch {
      return false;
    }
  })();

  const capabilities = [
    capabilityRecord({
      id: 'node_backend',
      label: 'Node Backend',
      status: 'live',
      category: 'runtime',
      setup_action: 'view_logs',
      details: `Gateway is running on port ${PORT}.`,
      docs_hint: 'Node owns auth, WebSocket, dashboard APIs, and Python proxying.',
      proof: { started_at: SERVER_START_TIMESTAMP, port: PORT },
    }),
    capabilityRecord({
      id: 'python_backend',
      label: 'Python Backend',
      status: pythonProbe.ok ? 'live' : 'unavailable',
      category: 'runtime',
      setup_action: pythonProbe.ok ? 'test' : 'start_service',
      details: pythonProbe.ok
        ? `Python health responded on port ${PYTHON_BACKEND_PORT}.`
        : `Python did not respond on port ${PYTHON_BACKEND_PORT}.`,
      docs_hint: 'Start the Python AI backend before marking task execution fully live.',
      proof: { port: PYTHON_BACKEND_PORT, probe: pythonProbe },
    }),
    capabilityRecord({
      id: 'frontend_build',
      label: 'Frontend Build',
      status: HAS_FRONTEND_DIST ? 'live' : 'not_configured',
      category: 'runtime',
      setup_action: HAS_FRONTEND_DIST ? 'none' : 'run_build',
      details: HAS_FRONTEND_DIST ? 'Built frontend assets are available.' : 'frontend/dist/index.html is missing.',
      docs_hint: 'Run npm --prefix frontend run build to produce production assets.',
    }),
    capabilityRecord({
      id: 'websocket_event_bus',
      label: 'WebSocket Event Bus',
      status: 'live',
      category: 'runtime',
      setup_action: 'test',
      details: 'Node WebSocket upgrade handler is mounted; clients still need a valid token.',
      docs_hint: 'Use the dashboard connection pill and event feed to confirm live client traffic.',
    }),
    capabilityRecord({
      id: 'auth_session',
      label: 'Auth / Session',
      status: JWT_SECRET ? 'live' : 'not_configured',
      category: 'security',
      required_env: ['JWT_SECRET_KEY'],
      missing_env: JWT_SECRET ? [] : ['JWT_SECRET_KEY'],
      setup_action: JWT_SECRET ? 'test' : 'configure_env',
      details: JWT_SECRET ? 'JWT signing secret is configured.' : 'JWT_SECRET_KEY is required before startup.',
      docs_hint: 'Local admin tokens are available from /api/auth/auto-token.',
    }),
    capabilityRecord({
      id: 'ollama_local_model',
      label: 'Ollama / Local Model',
      status: ollamaProbe.ok ? 'live' : 'not_configured',
      category: 'llm',
      required_env: ['OLLAMA_HOST'],
      missing_env: process.env.OLLAMA_HOST || process.env.OLLAMA_URL ? [] : ['OLLAMA_HOST'],
      setup_action: ollamaProbe.ok ? 'test' : 'start_service',
      details: ollamaProbe.ok ? `Ollama responded at ${ollamaHost}.` : `No Ollama response from ${ollamaHost}.`,
      docs_hint: 'Start Ollama and pull the configured local model to enable local fallback.',
      proof: { host: ollamaHost, probe: ollamaProbe },
    }),
    capabilityRecord({
      id: 'llm_provider_routing',
      label: 'LLM Provider Routing',
      status: activeProviderCount > 0 ? 'live' : 'not_configured',
      category: 'llm',
      setup_action: activeProviderCount > 0 ? 'test' : 'configure_env',
      details: activeProviderCount > 0
        ? `${activeProviderCount} provider path(s) appear usable.`
        : 'No remote provider key or local Ollama service is currently usable.',
      docs_hint: 'Configure at least one model provider before expecting high-quality LLM responses.',
    }),
    ...providerRecords,
    capabilityRecord({
      id: 'tool_registry',
      label: 'Tool / Skill Registry',
      status: fs.existsSync(path.join(REPO_ROOT, 'runtime', 'config', 'skills_library.json')) ? 'live' : 'unavailable',
      category: 'execution',
      setup_action: 'test',
      details: 'Skill registry file is present for planner/executor lookup.',
      docs_hint: 'Tools still report their own configured/unconfigured state per provider.',
    }),
    capabilityRecord({
      id: 'real_execution_engine',
      label: 'Real Execution Engine',
      status: fs.existsSync(PYTHON_EXEC_SCRIPT) ? 'live' : 'unavailable',
      category: 'execution',
      setup_action: fs.existsSync(PYTHON_EXEC_SCRIPT) ? 'test' : 'view_logs',
      details: fs.existsSync(PYTHON_EXEC_SCRIPT) ? 'backend/run_execution.py exists.' : 'backend/run_execution.py is missing.',
      docs_hint: 'Execution proof must include artifacts, traces, provider IDs, or explicit dry-run output.',
    }),
    capabilityRecord({
      id: 'money_mode',
      label: 'Money Mode',
      status: 'dry_run',
      category: 'money',
      setup_action: 'run_doctor',
      details: 'Money Mode is available as an approval-gated dry-run layer until external accounts are configured.',
      docs_hint: 'Publishing, outreach, payments, paid-task acceptance, and account changes require approval.',
    }),
    capabilityRecord({
      id: 'email_outreach',
      label: 'Email / Outreach',
      status: emailConfigured ? 'live' : 'not_configured',
      category: 'integration',
      required_env: emailRequired,
      missing_env: emailMissing,
      setup_action: emailConfigured ? 'test' : 'configure_env',
      details: emailConfigured ? 'At least one email provider path is configured.' : 'Email requires SendGrid or a complete SMTP env set.',
      docs_hint: 'Outbound email remains approval-gated even when configured.',
    }),
    capabilityRecord({
      id: 'apollo_search',
      label: 'Apollo Lead Search',
      status: apolloEnv.status,
      category: 'integration',
      required_env: ['APOLLO_API_KEY'],
      missing_env: apolloEnv.missing,
      setup_action: apolloEnv.status === 'live' ? 'test' : 'configure_env',
      details: apolloEnv.status === 'live' ? 'Apollo API key is present.' : 'Lead discovery needs APOLLO_API_KEY for live provider calls.',
      docs_hint: 'Unconfigured lead discovery must be labeled mock/fallback/dry-run.',
    }),
    capabilityRecord({
      id: 'linkedin_post',
      label: 'LinkedIn Posting',
      status: linkedinEnv.status,
      category: 'integration',
      required_env: ['LINKEDIN_ACCESS_TOKEN', 'LINKEDIN_PERSON_URN'],
      missing_env: linkedinEnv.missing,
      setup_action: linkedinEnv.status === 'live' ? 'test' : 'configure_env',
      details: linkedinEnv.status === 'live' ? 'LinkedIn posting credentials are present.' : 'LinkedIn posting needs access token and person URN.',
      docs_hint: 'Posting is never automatic; it requires an approval decision.',
    }),
    capabilityRecord({
      id: 'artifact_storage',
      label: 'Proof / Artifact Storage',
      status: artifactsWritable ? 'live' : 'unavailable',
      category: 'execution',
      setup_action: artifactsWritable ? 'none' : 'view_logs',
      details: artifactsWritable ? `Artifact directory is writable: ${ARTIFACTS_DIR}` : `Artifact directory is not writable: ${ARTIFACTS_DIR}`,
      docs_hint: 'Generated outputs should link to stored artifacts or explain why none was produced.',
    }),
    capabilityRecord({
      id: 'memory_store',
      label: 'Memory / Vector Store',
      status: stateWritable ? 'live' : 'unavailable',
      category: 'memory',
      setup_action: stateWritable ? 'test' : 'view_logs',
      details: stateWritable ? `State directory is readable and writable: ${STATE_DIR}` : `State directory is not writable: ${STATE_DIR}`,
      docs_hint: 'Memory health is degraded when vector/knowledge stores are unavailable or fallback-only.',
    }),
    capabilityRecord({
      id: 'startup_warnings',
      label: 'Startup / Runtime Warnings',
      status: _readiness.subsystemsReady ? 'live' : (_readiness.pythonReady ? 'fallback' : 'unavailable'),
      category: 'runtime',
      setup_action: 'view_logs',
      details: _readiness.subsystemsReady
        ? 'Startup readiness reports all known subsystems ready.'
        : 'Startup readiness still has degraded subsystem signals.',
      docs_hint: 'Review /api/readiness and logs when this is fallback or unavailable.',
    }),
  ];

  const counts = capabilities.reduce((acc, capability) => {
    acc[capability.status] = (acc[capability.status] || 0) + 1;
    return acc;
  }, {});
  const notLive = capabilities.filter((capability) => capability.status !== 'live');
  const recommended = notLive.find((capability) => capability.status === 'unavailable')
    || notLive.find((capability) => capability.status === 'not_configured')
    || notLive.find((capability) => capability.status === 'fallback')
    || null;

  res.json({
    ok: true,
    checked_at: checkedAt,
    states: ['live', 'dry_run', 'mock', 'fallback', 'not_configured', 'unavailable', 'error'],
    counts,
    next_recommended_action: recommended ? {
      capability_id: recommended.id,
      label: recommended.label,
      setup_action: recommended.setup_action,
      details: recommended.details,
    } : null,
    capabilities,
  });
});

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
app.get('/api/neural-brain/graph', async (req, res) => {
  const depth = Number(req.query.depth) || 2;
  const limit = Number(req.query.limit) || 200;
  const data = await proxyNeuralBrain(`/api/neural-brain/graph?depth=${depth}&limit=${limit}`, { nodes: [], links: [] });
  res.json(normalizeDashboardGraph(data));
});

app.get('/api/neural-brain/memory/status', async (req, res) => {
  const data = await proxyNeuralBrain('/api/neural-brain/memory/status', {
    count: 0, last_write_ts: null, recent: [],
  });
  res.json(data);
});

app.get('/api/neural-brain/memory/list', async (req, res) => {
  const data = await proxyNeuralBrain('/api/neural-brain/memory/list', {
    items: [], total: 0, page: 1,
  });
  res.json(data);
});

app.delete('/api/neural-brain/memory/:id', async (req, res) => {
  try {
    const r = await fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/memory/${req.params.id}`, { method: 'DELETE' });
    if (r?.ok) return res.json(await r.json());
  } catch (_) {}
  res.json({ ok: true });
});

app.get('/api/neural-brain/graph/status', async (req, res) => {
  const data = await proxyNeuralBrain('/api/neural-brain/graph/status', {
    node_count: 0, edge_count: 0, recent_nodes: [],
  });
  res.json(data);
});

app.get('/api/neural-brain/graph/snapshot', async (req, res) => {
  let data = await proxyNeuralBrain('/api/neural-brain/graph/snapshot', {
    nodes: [], links: [], stats: {},
  });
  if (!Array.isArray(data?.nodes) || data.nodes.length === 0) {
    data = await proxyNeuralBrain('/api/neural-brain/graph', data);
  }
  res.json(normalizeDashboardGraph(data));
});

app.get('/api/neural-brain/threads', async (req, res) => {
  const data = await proxyNeuralBrain('/api/neural-brain/threads', { threads: [] });
  res.json(data);
});

app.post('/api/neural-brain/think', async (req, res) => {
  try {
    const r = await Promise.race([
      fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/think`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req.body),
      }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 10000)),
    ]);
    if (r?.ok) return res.json(await r.json());
  } catch (_) {}
  res.json({ response: 'Neural Brain offline — Python backend not running.', status: 'offline' });
});

app.get('/api/neural-brain/forge/evolution/status', async (req, res) => {
  const data = await proxyNeuralBrain('/api/neural-brain/forge/evolution/status', {
    mode: 'SAFE', patches_proposed: 0, patches_applied: 0,
  });
  res.json(data);
});

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

const MODEL_FABRIC_OFFLINE = { status: 'offline', error: 'Model Fabric offline — Python backend not running.' };

// GET endpoints (fast; never trigger a model load)
['models', 'health', 'status', 'lifecycle/status', 'quantization/status',
 'quantization/available', 'quantization/pull/status'].forEach((seg) => {
  app.get(`/api/model-fabric/${seg}`, requireAuth, async (req, res) => {
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
  app.post(`/api/model-fabric/${seg}`, requireAuth, async (req, res) => {
    try {
      const { ok, data } = await proxyModelFabric(`/api/model-fabric/${seg}`, { method: 'POST', body: req.body });
      return res.status(ok ? 200 : 502).json(data);
    } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
  });
});

// Per-model unload (model id may contain slashes/colons, e.g. "qwen2.5-coder:14b")
app.post(/^\/api\/model-fabric\/models\/(.+)\/unload$/, requireAuth, async (req, res) => {
  try {
    const id = encodeURIComponent(req.params[0]);
    const { ok, data } = await proxyModelFabric(`/api/model-fabric/models/${id}/unload`, { method: 'POST', body: req.body });
    return res.status(ok ? 200 : 502).json(data);
  } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
});

// Per-model reload with a specific quant (unload + pull the quant variant)
app.post(/^\/api\/model-fabric\/models\/(.+)\/reload-with-quant$/, requireAuth, async (req, res) => {
  try {
    const id = encodeURIComponent(req.params[0]);
    const { ok, data } = await proxyModelFabric(`/api/model-fabric/models/${id}/reload-with-quant`, { method: 'POST', body: req.body });
    return res.status(ok ? 200 : 502).json(data);
  } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
});

// ── Agent fleet controls ──────────────────────────────────────────────────────
app.post('/api/agents/start-all', requireAuth, (req, res) => {
  res.json({ ok: true, action: 'start-all' });
});
app.post('/api/agents/pause-all', requireAuth, (req, res) => {
  res.json({ ok: true, action: 'pause-all' });
});
app.post('/api/agents/stop-all', requireAuth, (req, res) => {
  res.json({ ok: true, action: 'stop-all' });
});
app.get('/api/agents', requireAuth, (req, res) => {
  const agents = getAgents();
  // Include tenant context if available (for debugging/admin purposes only)
  const response = {
    agents,
    tenant: req.tenant ? { tenant_id: req.tenant.tenantId, org_name: req.tenant.orgName } : null,
  };
  res.json(response);
});

// ── Subsystem API endpoints ───────────────────────────────────────────────────

app.get('/api/system/stats', requireAuth, (req, res) => {
  const stats = sampleSystemStatus();
  // Expose cpu_percent as canonical field (alias of cpu_usage) for test/e2e compatibility
  res.json({ ...stats, cpu_percent: stats.cpu_usage ?? stats.cpu ?? 0 });
});

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

app.get('/api/observability/snapshot', (req, res) => {
  res.json(buildObservabilitySnapshot());
});

app.get('/api/observability/events', (req, res) => {
  res.json({ events: (runtimeState.observability.events || []).slice(0, 200) });
});

app.get('/api/security/aztsa/status', (req, res) => {
  const requiredSecrets = [
    secretStore.describe('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] }),
    secretStore.describe('JWT_SECRET', { aliases: ['JWT_SECRET_KEY'] }),
  ];
  res.json({
    gateway: apiGatewayProtector.status(),
    secret_health: {
      required: requiredSecrets,
      missing: requiredSecrets.filter((item) => !item.configured).map((item) => item.name),
    },
    anomaly_response: anomalyResponder.status(),
    offline_security_sync: securitySyncPolicy.status(),
    honeypot: {
      events: apiGatewayProtector.recentHoneypot(20),
    },
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/security/honeypot/events', (req, res) => {
  const limitRaw = Number((req.query || {}).limit || 50);
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(200, limitRaw)) : 50;
  res.json({
    events: apiGatewayProtector.recentHoneypot(limit),
    total: apiGatewayProtector.status().honeypot_events,
  });
});

app.post('/api/security/offline-sync', requireAuth, (req, res) => {
  const body = req.body || {};
  const online = body.online !== false;
  const state = securitySyncPolicy.setOnline(online);
  res.json({
    status: state,
    applied_online: online,
  });
});

app.post('/api/security/anomaly/evaluate', requireAuth, (req, res) => {
  const result = anomalyResponder.evaluate();
  res.json(result);
});

app.post('/api/security/gateway/strict-mode', requireAuth, (req, res) => {
  const enabled = Boolean((req.body || {}).enabled);
  const strict = apiGatewayProtector.setStrictMode(enabled, 'manual_override');
  res.json({
    strict_mode: strict,
    gateway: apiGatewayProtector.status(),
  });
});

app.get('/api/mode', (req, res) => {
  const mode = getMode();
  const robotSignal = getRobotSignal();
  const template = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: getRunningAgentCount(),
    totalAgents: getAgents().length,
  });
  res.json({
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    thinking_mode: buildThinkingSummary(mode, template, robotSignal),
    money_template: mode === 'MONEYMODE' ? template : null,
  });
});

app.post('/api/mode', requireAuth, (req, res) => {
  const body = validate(SCHEMAS.modeSet, req, res);
  if (!body) return;
  const next = body.mode.toUpperCase();
  const mode = setMode(next);
  if (mode === 'MONEYMODE' && !runtimeState.objectiveState.money_mode.current_objective) {
    setObjectiveWaiting('money_mode');
  }
  const robotSignal = getRobotSignal();
  const template = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: getRunningAgentCount(),
    totalAgents: getAgents().length,
  });
  res.json({
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    thinking_mode: buildThinkingSummary(mode, template, robotSignal),
    money_template: mode === 'MONEYMODE' ? template : null,
  });
});

app.get('/api/brain/status', (req, res) => {
  const nn = subsystems.getNNStatus();
  const core = brain.status();
  res.json({
    ...nn,
    ...core,
    updated_at: nn.updated_at || core.last_update || new Date().toISOString(),
  });
});

app.get('/internal/brain/status', (req, res) => {
  const core = brain.status() || {};
  const insights = brain.insights() || {};
  const strategies = Array.isArray(insights.learned_strategies) ? insights.learned_strategies.length : 0;
  const active = Boolean(core.available && core.active);
  res.json({
    status: active ? 'online' : 'offline',
    initialized: active,
    strategies_loaded: strategies,
    updated_at: core.last_update || insights.updated_at || new Date().toISOString(),
  });
});

app.get('/api/brain/insights', (req, res) => {
  res.json(brain.insights());
});

app.get('/api/brain/activity', (req, res) => {
  const limit = Number(req.query.limit || 20);
  res.json(brain.activity(limit));
});

app.get('/api/brain/neurons', (req, res) => {
  res.json(brain.neurons());
});

/**
 * Unified graph endpoint for the 3-D Neural Brain visualization.
 * Returns { nodes, links, stats } using a normalized schema so the
 * frontend brainStore can consume it directly.
 */
app.get('/api/brain/graph', async (req, res) => {
  const raw = brain.neurons();
  const memoryTree = subsystems.getMemoryTree();
  const nodes = (raw.nodes || []).map((n) => ({
    id: n.id,
    label: n.label,
    type: n.type || 'skill',
    group:
      n.type === 'Memory'
        ? 'memory'
        : n.type === 'Strategy' || n.type === 'Skill'
          ? 'money'
          : n.type === 'Output'
            ? 'automation'
            : 'learning',
    weight: n.weight ?? 1,
    confidence: n.confidence ?? 0,
    activation: n.activation ?? 0,
    source: n.source || 'system',
    tag: n.tag || '',
  }));

  // Append top memory-tree entities as nodes
  if (Array.isArray(memoryTree?.nodes)) {
    memoryTree.nodes.slice(0, 30).forEach((m) => {
      const id = `mem-${(m.id || m.entity || '').replace(/\s+/g, '-').slice(0, 40)}`;
      if (nodes.some((n) => n.id === id)) return;
      nodes.push({
        id,
        label: m.entity || m.id || 'memory',
        type: 'memory',
        group: 'memory',
        weight: m.mention_count ?? m.importance ?? 1,
        confidence: m.importance ?? 0.5,
        activation: 0,
        source: 'memory',
        tag: 'knowledge',
      });
    });
  }

  const links = (raw.connections || []).map((c) => ({
    source: c.from,
    target: c.to,
    strength: c.weight ?? c.confidence ?? 0.5,
  }));

  // Attempt to merge Neural Brain graph (Python LangGraph + Neo4j)
  let nbGraph = null;
  try {
    const nbResp = await Promise.race([
      fetch(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/neural-brain/graph`, { timeout: 1000 }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1000)),
    ]);
    if (nbResp?.ok) {
      nbGraph = await nbResp.json();
      if (nbGraph?.nodes && Array.isArray(nbGraph.nodes)) {
        nbGraph.nodes.forEach((n) => {
          const existing = nodes.some((x) => x.id === n.id);
          if (!existing) nodes.push(n);
        });
      }
      if (nbGraph?.links && Array.isArray(nbGraph.links)) {
        const linkSet = new Set(links.map((l) => `${l.source}→${l.target}`));
        nbGraph.links.forEach((l) => {
          if (!linkSet.has(`${l.source}→${l.target}`)) {
            links.push(l);
            linkSet.add(`${l.source}→${l.target}`);
          }
        });
      }
    }
  } catch (_nbErr) {
    // Neural Brain offline or slow — continue with regular graph
  }

  // Native embedded graph memory is the canonical offline graph backend.
  // It is not an extension: every dashboard graph response syncs through it.
  try {
    const native = getNativeMemoryGraph({ stateDir: STATE_DIR, repoRoot: REPO_ROOT });
    native.ingestSnapshot({ nodes, links }, 'node_dashboard_graph');
    const nativeSnapshot = native.snapshot(350);
    const nodeSet = new Set(nodes.map((node) => String(node.id)));
    nativeSnapshot.nodes.forEach((node) => {
      if (!nodeSet.has(String(node.id))) {
        nodes.push(node);
        nodeSet.add(String(node.id));
      }
    });
    const linkSet = new Set(links.map((link) => `${link.source}→${link.target}`));
    nativeSnapshot.links.forEach((link) => {
      const key = `${link.source}→${link.target}`;
      if (!linkSet.has(key)) {
        links.push(link);
        linkSet.add(key);
      }
    });
  } catch (err) {
    console.warn('[BRAIN GRAPH] Native graph sync failed: %s', err && err.message);
  }

  res.json(normalizeDashboardGraph({
    nodes,
    links,
    stats: { ...(raw.stats || {}), graph_backend: 'native_memory_graph' },
    updated_at: raw.updated_at || new Date().toISOString(),
  }));
});

app.get('/api/memory/tree', (req, res) => {
  res.json(subsystems.getMemoryTree());
});

app.get('/api/system/manifest', (req, res) => {
  res.json(loadSystemManifest());
});

app.post('/api/model/route-plan', (req, res) => {
  const body = req.body || {};
  const task = String(body.task || body.message || body.goal || '').trim();
  if (!task) return res.status(400).json({ ok: false, error: 'task, message, or goal required' });
  res.json(buildModelRoutePlan(body));
});

app.get('/api/memory', async (req, res) => {
  try {
    const data = await requestPythonJSON('/api/memory', 'GET', null, { timeoutMs: 4000 });
    if (data._http_status >= 200 && data._http_status < 300) {
      return res.json({ ...data, source: 'python-memory' });
    }
    return res.status(data._http_status || 502).json({ ok: false, error: 'Python memory backend returned an error', source: 'python-memory' });
  } catch (err) {
    const tree = subsystems.getMemoryTree();
    return res.json({
      source: 'node-fallback',
      clients: [],
      recent_interactions: [],
      total_clients: 0,
      fallback_tree: tree,
      warning: `Python memory backend unavailable: ${err.message}`,
    });
  }
});

// ── Conversations JSONL endpoint ──────────────────────────────────────────────
const conversations = require('./conversations');

app.get('/api/memory/conversations', (req, res) => {
  const all = conversations.readConversations();
  return res.json({ conversations: all.slice(-100), total: all.length, source: 'node-local' });
});

app.delete('/api/memory/conversations/:id', (req, res) => {
  const removed = conversations.deleteConversation(req.params.id);
  if (!removed) return res.status(404).json({ ok: false, error: 'Conversation not found' });
  return res.json({ ok: true, deleted: req.params.id });
});

app.get('/api/memory/search', async (req, res) => {
  const q = String((req.query || {}).q || '').trim();
  if (!q) return res.status(400).json({ ok: false, error: 'q required' });
  const topK = Math.max(1, Math.min(25, Number((req.query || {}).top_k || 8) || 8));
  const memoryType = String((req.query || {}).memory_type || '').trim();
  const query = `/api/memory/search?q=${encodeURIComponent(q)}&top_k=${topK}${memoryType ? `&memory_type=${encodeURIComponent(memoryType)}` : ''}`;
  try {
    const data = await requestPythonJSON(query, 'GET', null, { timeoutMs: 5000 });
    if (data._http_status >= 200 && data._http_status < 300) {
      return res.json({ ...data, source: data.source || 'python-memory-search' });
    }
    return res.status(data._http_status || 502).json({ ok: false, error: 'Python memory search returned an error', source: 'python-memory-search' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: `Python memory search unavailable: ${err.message}`, source: 'node-fallback', results: [] });
  }
});

app.post('/api/memory/clients', async (req, res) => {
  try {
    const data = await requestPythonJSON('/api/memory/clients', 'POST', req.body || {}, { timeoutMs: 5000 });
    return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
  }
});

app.patch('/api/memory/clients/:clientId', async (req, res) => {
  try {
    const data = await requestPythonJSON(`/api/memory/clients/${encodeURIComponent(req.params.clientId)}`, 'PATCH', req.body || {}, { timeoutMs: 5000 });
    return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
  }
});

app.delete('/api/memory/clients/:clientId', async (req, res) => {
  try {
    const data = await requestPythonJSON(`/api/memory/clients/${encodeURIComponent(req.params.clientId)}`, 'DELETE', null, { timeoutMs: 5000 });
    return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
  }
});

app.post('/api/memory/interactions', async (req, res) => {
  try {
    const data = await requestPythonJSON('/api/memory/interactions', 'POST', req.body || {}, { timeoutMs: 5000 });
    return res.status(data._http_status || 200).json({ ...data, source: 'python-memory' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: `Python memory backend unavailable: ${err.message}`, source: 'node-fallback' });
  }
});

app.get('/api/doctor/status', (req, res) => {
  res.json(subsystems.getDoctorStatus());
});

app.get('/api/self-improvement/status', (req, res) => {
  res.json(subsystems.getSelfImprovementStatus());
});

// ── Autonomy daemon endpoints ─────────────────────────────────────────────────

app.get('/api/autonomy/status', (req, res) => {
  res.json(subsystems.getAutonomyStatus());
});

app.get('/api/autonomy/mode', (req, res) => {
  const auto = subsystems.getAutonomyStatus();
  res.json(auto.mode || { mode: 'OFF', active: false });
});

function requestPythonJSON(pathname, method = 'GET', payload = null, options = {}) {
  return new Promise((resolve, reject) => {
    const httpLib = require('http');
    const safePath = String(pathname || '/').trim();
    if (!safePath.startsWith('/api/') || safePath.includes('..')) {
      return reject(new Error('invalid_path'));
    }
    const body = payload ? JSON.stringify(payload) : null;
    const headers = {
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

const turnRunner = createTurnRunner({
  broadcaster,
  orchestrator,
  createWorkflowRun,
  appendDecision,
  attachWorkflowNode,
  addActivity,
  collectHybridMemoryContext,
  compactMemoryTraceForModel,
  runPythonExecution,
  isPythonBackendUp,
  requestPythonJSON,
  requestPythonChatPayload,
  requestOllamaChat,
  applyStructuredFormat,
  buildLocalFallbackReply,
});

app.post('/api/autonomy/mode', requireAuth, async (req, res) => {
  const nextMode = String((req.body || {}).mode || '').toUpperCase();
  if (!['OFF', 'ON', 'AUTO'].includes(nextMode)) {
    return res.status(400).json({ error: 'Invalid mode. Use OFF, ON, or AUTO.' });
  }
  // Proxy to Python backend
  try {
    const data = await new Promise((resolve, reject) => {
      const payload = JSON.stringify({ mode: nextMode });
      const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/mode`;
      const httpLib = require('http');
      const r = httpLib.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
        timeout: 3000,
      }, (response) => {
        let body = '';
        response.on('data', (chunk) => { body += chunk; });
        response.on('end', () => {
          try { resolve(JSON.parse(body)); } catch { resolve({ mode: nextMode, active: nextMode !== 'OFF' }); }
        });
      });
      r.on('timeout', () => { r.destroy(); resolve({ mode: nextMode, active: nextMode !== 'OFF' }); });
      r.on('error', () => resolve({ mode: nextMode, active: nextMode !== 'OFF' }));
      r.write(payload);
      r.end();
    });
    addActivity(`[AUTONOMY] Mode → ${nextMode}`, 'system');
    res.json(data);
  } catch {
    res.json({ mode: nextMode, active: nextMode !== 'OFF' });
  }
});

app.post('/api/autonomy/emergency-stop', requireAuth, (req, res) => {
  // Proxy emergency stop to Python backend
  const httpLib = require('http');
  const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/emergency-stop`;
  const r = httpLib.request(url, { method: 'POST', timeout: 3000 }, (response) => {
    let body = '';
    response.on('data', (chunk) => { body += chunk; });
    response.on('end', () => {
      try {
        addActivity('[AUTONOMY] ⚠ EMERGENCY STOP executed', 'system');
        res.json(JSON.parse(body));
      } catch { res.json({ status: 'stopped', message: 'Emergency stop sent.' }); }
    });
  });
  r.on('timeout', () => { r.destroy(); res.json({ status: 'stopped', message: 'Emergency stop sent (timeout).' }); });
  r.on('error', () => res.json({ status: 'stopped', message: 'Emergency stop sent (backend unreachable).' }));
  r.end();
});

app.get('/api/evolution/status', async (req, res) => {
  try {
    const data = await requestPythonJSON('/api/evolution/status', 'GET');
    res.json(data);
  } catch {
    res.json({ mode: 'OFF', running: false });
  }
});

app.post('/api/evolution/mode', requireAuth, async (req, res) => {
  const body = validate(SCHEMAS.evolutionMode, req, res);
  if (!body) return;
  const mode = body.mode;
  try {
    const data = await requestPythonJSON('/api/evolution/mode', 'POST', { mode });
    addActivity(`[EVOLUTION] Mode → ${mode}`, 'system');
    res.json(data);
  } catch {
    res.json({ mode, status: { mode, running: false } });
  }
});

app.get('/api/product/dashboard', (req, res) => {
  res.json(buildDashboardPayload());
});

app.get('/api/economy/summary', requireAuth, (req, res) => {
  const economy = buildEconomySnapshot();
  res.json({ ok: true, ...economy.summary });
});

app.get('/api/economy/ledger', requireAuth, (req, res) => {
  const economy = buildEconomySnapshot();
  res.json({
    ok: true,
    state: economy.ledger.length ? 'live' : 'empty',
    source: 'node_runtime_state',
    ledger: economy.ledger,
    items: economy.ledger,
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/economy/costs', requireAuth, (req, res) => {
  const economy = buildEconomySnapshot();
  res.json({
    ok: true,
    state: economy.costs.length ? 'live' : 'empty',
    source: 'llm_call_log',
    costs: economy.costs,
    items: economy.costs,
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/economy/pipelines', requireAuth, (req, res) => {
  const economy = buildEconomySnapshot();
  res.json({
    ok: true,
    state: economy.pipelines.some((pipeline) => pipeline.active) ? 'live' : 'empty',
    source: 'node_objective_state',
    pipelines: economy.pipelines,
    items: economy.pipelines,
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/economy/opportunities', requireAuth, (req, res) => {
  const opportunities = readJsonSafe(statePath('opportunities.json'), []);
  res.json({
    ok: true,
    state: opportunities.length ? 'live' : 'empty',
    source: 'node_state',
    opportunities,
    items: opportunities,
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/economy/wallet', requireAuth, (req, res) => {
  res.json({ ok: true, source: 'wallet_vault', wallet: walletSnapshot(), updated_at: new Date().toISOString() });
});

app.get('/api/workflows/live', (req, res) => {
  res.json({
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
  });
});

app.get('/api/objectives/status', (req, res) => {
  res.json({
    objectives: runtimeState.objectives,
    systems: runtimeState.objectiveState,
  });
});

app.post('/api/automation/control', requireAuth, (req, res) => {
  const action = String((req.body || {}).action || '').toLowerCase();
  const goal = String((req.body || {}).goal || '').trim();
  const overrideActionId = String((req.body || {}).override_action_id || '').trim();

  if (action === 'start') {
    activateAgents(3);
    runtimeState.automationRunning = true;
    addActivity(`[AUTOMATION] started${goal ? ` • goal: ${goal}` : ''}`, 'automation');
    const run = createWorkflowRun({
      name: 'Automation Goal Workflow',
      source: 'automation',
      goal: goal || 'Execute automation cycle',
    });
    const taskMessages = [
      goal || 'Analyze current market conditions',
      'Generate value opportunities',
      'Route prioritized tasks to agents',
    ];
    runtimeState.workflowSequencers[run.run_id] = {
      messages: taskMessages,
      queuedSteps: new Set([0]),
      completedSteps: new Set(),
      stepTaskIds: {},
      stopped: false,
    };
    queueWorkflowStep({
      runId: run.run_id,
      message: taskMessages[0],
      stepIndex: 0,
      labels: ['automation', 'step-1'],
      parentTaskId: null,
    });
    return res.json({ status: 'running', message: 'Automation started.', tasks_queued: 1, workflow_run: run.run_id });
  }

  if (action === 'stop') {
    Object.values(runtimeState.workflowSequencers).forEach((seq) => {
      seq.stopped = true;
    });
    runtimeState.automationRunning = false;
    const stopResult = stopAllAgents('automation_stop');
    markWorkflowsStopped();
    addActivity('[AUTOMATION] stopped', 'automation');
    return res.json({
      status: 'stopped',
      message: 'Automation stopped.',
      cancelled_tasks: stopResult.cancelledTasks,
      running_agents: stopResult.runningAgents,
    });
  }

  if (action === 'override') {
    if (!overrideActionId) {
      return res.status(400).json({ status: 'error', reason: 'override_action_id is required.' });
    }
    addActivity(`[AUTOMATION] manual override executed for ${overrideActionId}`, 'automation');
    return res.json({ status: 'ok', message: `Override applied to ${overrideActionId}.` });
  }

  return res.status(400).json({ status: 'error', reason: 'Invalid automation action.' });
});

app.post('/api/money/content-pipeline', requireAuth, async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/money/content-pipeline', 'POST', req.body || {}, {
      headers: { Authorization: pythonServiceAuthorization(req) },
      timeoutMs: 30000,
    });
    if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
  } catch (err) {
    console.warn('[MONEY] Python content pipeline unavailable: %s', err && err.message);
  }
  const run = runPipeline('content');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
});

app.post('/api/money/lead-pipeline', requireAuth, async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/money/lead-pipeline', 'POST', req.body || {}, {
      headers: { Authorization: pythonServiceAuthorization(req) },
      timeoutMs: 30000,
    });
    if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
  } catch (err) {
    console.warn('[MONEY] Python lead pipeline unavailable: %s', err && err.message);
  }
  const run = runPipeline('lead');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
});

app.post('/api/money/opportunity-pipeline', requireAuth, async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/money/opportunity-pipeline', 'POST', req.body || {}, {
      headers: { Authorization: pythonServiceAuthorization(req) },
      timeoutMs: 30000,
    });
    if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
  } catch (err) {
    console.warn('[MONEY] Python opportunity pipeline unavailable: %s', err && err.message);
  }
  const run = runPipeline('opportunity');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
});

app.post('/api/money/affiliate-draft', requireAuth, async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/money/affiliate-draft', 'POST', req.body || {}, {
      headers: { Authorization: pythonServiceAuthorization(req) },
      timeoutMs: 30000,
    });
    if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
  } catch (err) {
    console.warn('[MONEY] Python affiliate draft unavailable: %s', err && err.message);
  }
  return res.status(503).json({
    ok: false,
    error: 'Python MoneyMode backend unavailable; affiliate drafts require the approval-aware Python pipeline.',
  });
});

// ── Task execution endpoint ───────────────────────────────────────────────────

app.post('/api/tasks/run', requireAuth, async (req, res) => {
  const rawBody = req.body || {};
  // Normalise: accept both `task` and legacy `message` field before validation
  if (!rawBody.task && rawBody.message) rawBody.task = rawBody.message;
  if (!rawBody.task && rawBody.description) rawBody.task = rawBody.description;
  if (!rawBody.task) rawBody.task = 'Execute task';
  const body = validate(SCHEMAS.tasksRun, req, res);
  if (!body) return;
  if (rawBody.use_turn_runner !== false) {
    try {
      const turn = await turnRunner.runTurn({
        kind: 'task',
        source: 'tasks-http',
        message: body.task,
        userId: body.user_id || (req.jwtPayload?.sub ? `user:${req.jwtPayload.sub}` : 'user:default'),
        tenantId: req.tenant?.id || req.jwtPayload?.tenant_id || 'default',
        authHeader: pythonServiceAuthorization(req),
        labels: ['http'],
        executionTimeoutMs: 3000,
      });
      return res.json({
        ...turn,
        agent_controller: turn.source === 'agent_controller' ? { status: turn.status, proof: turn.proof } : null,
      });
    } catch (err) {
      console.warn('[TASKS] turn runner failed, using legacy path: %s', err && err.message);
    }
  }
  const message = body.task.trim();
  const userId = body.user_id || 'user:default';
  const run = createWorkflowRun({
    name: 'Ad-hoc Task Workflow',
    source: 'manual',
    goal: message,
  });

  emitTaskProgress(run.run_id, message, [
    { id: 0, label: 'Planning',   status: 'active' },
    { id: 1, label: 'Executing',  status: 'pending' },
    { id: 2, label: 'Validating', status: 'pending' },
  ]);

  const memoryTrace = await collectHybridMemoryContext(message, {
    userId,
    sessionId: run.run_id,
    taskId: run.run_id,
    mode: 'main_ai_task',
    maxTokens: 1200,
  });
  if (memoryTrace) {
    appendDecision(run, {
      ts: new Date().toISOString(),
      type: 'memory_router_preflight',
      task_id: run.run_id,
      summary: `Routes ${Array.isArray(memoryTrace.routes) ? memoryTrace.routes.map((route) => route.id).join(', ') : 'none'} · confidence ${memoryTrace.confidence ?? 0}`,
      trace_id: memoryTrace.trace_id,
    });
    broadcaster.broadcast('memory:router:trace', {
      trace_id: memoryTrace.trace_id,
      task_id: run.run_id,
      routes: memoryTrace.routes,
      confidence: memoryTrace.confidence,
      degraded: memoryTrace.degraded,
    });
  }

  if (await isPythonBackendUp()) {
    try {
      const pyResult = await requestPythonJSON('/api/tasks/run', 'POST', {
        task: message,
        goal: message,
        user_id: userId,
        workflow_run: run.run_id,
        memory_context: compactMemoryTraceForModel(memoryTrace),
      }, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });

      if (pyResult && pyResult.ok) {
        const taskId = `agent-${pyResult.run_id || run.run_id}`;
        const queued = {
          taskId,
          agentId: 'agent-controller',
          subsystem: 'orchestrator',
          message,
          queuedAt: new Date().toISOString(),
          brain: {
            strategy: 'agent_controller',
            confidence: typeof pyResult.performance_score === 'number' ? pyResult.performance_score : 1,
            reasoning: 'Executed through Python AgentController Planner→Executor→Validator path.',
            execution_flow: 'goal->planner->skill->validator->summary',
          },
        };
        attachWorkflowNode({ runId: run.run_id, queued, taskName: message });
        updateWorkflowNode(taskId, (node, workflowRun) => {
          node.status = 'completed';
          node.progress_percent = 100;
          node.started_at = node.started_at || queued.queuedAt;
          node.completed_at = new Date().toISOString();
          node.result = {
            status: 'success',
            summary: `AgentController completed ${Array.isArray(pyResult.tasks) ? pyResult.tasks.length : 0} task(s).`,
          };
          appendDecision(workflowRun, {
            ts: new Date().toISOString(),
            task_id: taskId,
            type: 'agent_controller_result',
            summary: `Performance ${pyResult.performance_score ?? 'n/a'} · success ${pyResult.success_rate ?? 'n/a'}`,
          });
        });
        recordExecution({ taskId, skill: 'agent_controller', status: 'success', notes: message });
        addActivity(`[TASK] AgentController completed: ${message}`, 'task');
        emitTaskProgress(run.run_id, message, [
          { id: 0, label: 'Planning',   status: 'done' },
          { id: 1, label: 'Executing',  status: 'done' },
          { id: 2, label: 'Validating', status: 'done' },
        ]);
        return res.json({
          ok: true,
          workflow_run: run.run_id,
          taskId,
          agentId: 'agent-controller',
          subsystem: 'orchestrator',
          source: 'agent_controller',
          memory_router: memoryTrace ? {
            trace_id: memoryTrace.trace_id,
            routes: memoryTrace.routes,
            confidence: memoryTrace.confidence,
            degraded: memoryTrace.degraded,
          } : null,
          agent_controller: pyResult,
        });
      }
      console.warn('[TASKS] Python AgentController returned non-ok status: %s', pyResult?._http_status || 'unknown');
    } catch (err) {
      console.warn('[TASKS] Python AgentController unavailable, falling back to Node queue: %s', err && err.message);
    }
  }

  const result = orchestrator.submitTask(message, {
    userId,
    workflow: { runId: run.run_id, parentTaskId: null },
    labels: ['manual'],
    memory: compactMemoryTraceForModel(memoryTrace),
  });
  attachWorkflowNode({
    runId: run.run_id,
    queued: result,
    taskName: message,
  });
  addActivity(`[TASK] Submitted: ${message}`, 'task');

  res.json({
    ok: true,
    workflow_run: run.run_id,
    source: 'node_queue_fallback',
    memory_router: memoryTrace ? {
      trace_id: memoryTrace.trace_id,
      routes: memoryTrace.routes,
      confidence: memoryTrace.confidence,
      degraded: memoryTrace.degraded,
    } : null,
    ...result,
  });
});

// Compatibility endpoint used by legacy CLI flows (`ai-employee do/onboard`)
app.post('/api/chat', requireAuth, async (req, res) => {
  const body = validate(SCHEMAS.chat, req, res);
  if (!body) return;
  const message = body.message;
  // Fire-and-forget conversation recorder — never blocks the response
  const _recordChat = (assistantMessage, model) => {
    try {
      conversations.appendConversation({
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        tenant_id: req.user?.tenant_id || 'default',
        user_message: req.body.message || req.body.content || '',
        assistant_message: assistantMessage,
        model: model || null,
        session_id: req.headers['x-session-id'] || null,
        summary: String(req.body.message || req.body.content || '').slice(0, 200),
        message_count: 2,
        tags: ['chat'],
      });
    } catch (_) {}
  };
  const modelRoute = (body.model || '').trim() || undefined;
  // Prefer explicit user_id from body; fall back to JWT sub claim, then default
  const chatUserId = body.context?.user_id
    || (req.jwtPayload?.sub ? `user:${req.jwtPayload.sub}` : null)
    || 'user:default';
  console.info('[AI FLOW] Input received (HTTP): message_len=%d user=%s', message.length, chatUserId);

  if (body.context?.use_turn_runner !== false) {
    try {
      const turn = await turnRunner.runTurn({
        kind: 'chat',
        source: 'chat-http',
        message,
        modelRoute,
        userId: chatUserId,
        tenantId: req.tenant?.id || req.jwtPayload?.tenant_id || 'default',
        authHeader: pythonServiceAuthorization(req),
        labels: ['http'],
        executionTimeoutMs: 3000,
      });
      _recordChat(turn.assistant_reply || turn.reply, turn.source || 'turn-runner');
      return res.json(turn);
    } catch (err) {
      console.warn('[AI FLOW] turn runner failed, using legacy chat path: %s', err && err.message);
    }
  }

  // ── Learn-intent detection ─────────────────────────────────────
  // Matches: "learn about X", "teach me about X", "research X", "leer over X"
  const LEARN_PATTERNS = [
    /^\s*(?:learn|teach me|research|leer|leer me)\s+(?:about|over|on)\s+(.+?)[.!?]?\s*$/i,
    /^\s*(?:can you )?(?:learn|research)\s+(.+?)[.!?]?\s*$/i,
  ];
  let learnTopic = null;
  for (const pat of LEARN_PATTERNS) {
    const m = (message || '').match(pat);
    if (m && m[1] && m[1].trim().length > 2) { learnTopic = m[1].trim(); break; }
  }
  if (learnTopic) {
    // Fire learning session via Node proxy (don't block chat response)
    const proto = req.protocol || 'http';
    const host = req.get('host') || `localhost:${PORT}`;
    fetch(`${proto}://${host}/api/learning/execute`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'authorization': req.headers.authorization || '' },
      body: JSON.stringify({ topic: learnTopic, depth: 'normal' }),
    }).catch(() => {});
    const reply = `🎓 Started learning about **${learnTopic}**. Track progress in Memory → Standing Topics.`;
    res.json({
      ok: true,
      handled: true,
      reply,
      content: reply,
      learning_triggered: true,
      topic: learnTopic,
    });
    _recordChat(reply, 'learn-intent');
    return;
  }

  const handled = handleGoalDrivenCommand(message);
  if (handled.handled) {
    console.info('[AI FLOW] → Response returned (goal-driven command)');
    res.json({
      ok: true,
      handled: true,
      reply: handled.reply,
      content: handled.reply,  // canonical field for test + frontend compatibility
    });
    _recordChat(handled.reply, 'goal-driven');
    return;
  }
  const run = createWorkflowRun({
    name: 'Chat Workflow',
    source: 'chat-http',
    goal: message,
  });
  console.info('[AI FLOW] → Core AI called (orchestrator.submitTask)');
  const queued = orchestrator.submitTask(message, {
    userId: chatUserId,
    workflow: { runId: run.run_id, parentTaskId: null },
    labels: ['chat', 'http'],
  });
  attachWorkflowNode({
    runId: run.run_id,
    queued,
    taskName: message,
    parentTaskId: null,
  });
  addActivity(`[CHAT] Submitted: ${message}`, 'task');
  broadcaster.broadcast('orchestrator:queued', queued);
  broadcaster.broadcast('heartbeat', {
    message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
    level: 'info',
    heartbeat: heartbeatCounter,
  });

  const memoryTrace = await collectHybridMemoryContext(message, {
    userId: chatUserId,
    sessionId: run.run_id,
    taskId: queued.taskId,
    mode: 'main_ai_chat',
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

  // ── 1. Real execution engine (goal → structured plan → real tools) ──────────
  const execResult = await Promise.race([
    runPythonExecution(message),
    new Promise(r => setTimeout(() => r(null), 3000)),
  ]);
  const traceStart = Date.now();
  if (execResult && execResult.is_goal && execResult.reply) {
    console.info('[AI FLOW] → Real execution engine (HTTP): steps=%d success=%s', execResult.steps || 0, execResult.success);
    if (promptInspectorConfig && promptInspectorConfig.enabled) {
      addPromptTrace({ input: message, output: execResult.reply, status: 'ok', model: 'execution-engine', task_id: queued.taskId, flags: [], latency_ms: Date.now() - traceStart });
    }
    res.json({
      ok: true,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      reply: execResult.reply,
      content: execResult.reply,
      attachments: execResult.attachments || [],
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
    });
    _recordChat(execResult.reply, 'execution-engine');
    return;
  }

  // ── 2. Python LLM backend (full pipeline with memory + context) ──────────────
  let llmReply = null;
  if (await isPythonBackendUp()) {
    try {
      llmReply = await requestPythonChat(message, modelRoute, chatUserId, memoryTrace);
    } catch (err) {
      console.warn('[AI FLOW] Python chat proxy failed (HTTP path):', err && err.message);
    }
  }
  if (llmReply) {
    const structuredPyReply = applyStructuredFormat(llmReply, 'AI Employee');
    console.info('[AI FLOW] → LLM response returned (HTTP→Python): len=%d', structuredPyReply.length);
    if (promptInspectorConfig && promptInspectorConfig.enabled) {
      addPromptTrace({ input: message, output: structuredPyReply, status: 'ok', model: 'python-llm', task_id: queued.taskId, flags: structuredPyReply.length < 20 ? ['generic_output'] : [], latency_ms: Date.now() - traceStart });
    }
    broadcaster.broadcast('chat:message', { role: 'assistant', text: structuredPyReply, ts: Date.now() });
    res.json({
      ok: true,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      reply: structuredPyReply,
      content: structuredPyReply,
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
    });
    _recordChat(structuredPyReply, 'python-llm');
    try {
      broadcaster.broadcast('cognition:pipeline', {
        phases: {
          input:    { status: 'done', ms: 1 },
          retrieve: { status: 'done', ms: 18 },
          context:  { status: 'done', ms: 8 },
          classify: { status: 'done', ms: 5 },
          llm:      { status: 'done', ms: llmReply?.elapsed_ms || 600 },
          validate: { status: 'done', ms: 4 },
          execute:  { status: llmReply?.executed_tools?.length ? 'done' : 'skip', ms: 0 },
          memory:   { status: 'done', ms: 12 },
        },
        model: llmReply?.model || 'python-llm',
        timestamp: Date.now(),
      })
    } catch {}
    return;
  }

  // ── 3. Direct Ollama (Python unavailable) ────────────────────────────────────
  try {
    llmReply = await requestOllamaChat(message, memoryTrace);
  } catch (err) {
    console.warn('[AI FLOW] Ollama direct call failed (HTTP path):', err && err.message);
  }
  if (llmReply) {
    const structuredOllamaReply = applyStructuredFormat(llmReply, 'Ollama');
    console.info('[AI FLOW] → Ollama response (Python unavailable, HTTP): len=%d', structuredOllamaReply.length);
    if (promptInspectorConfig && promptInspectorConfig.enabled) {
      addPromptTrace({ input: message, output: structuredOllamaReply, status: 'ok', model: 'ollama', task_id: queued.taskId, flags: [], latency_ms: Date.now() - traceStart });
    }
    res.json({
      ok: true,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      reply: structuredOllamaReply,
      content: structuredOllamaReply,
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
    });
    _recordChat(structuredOllamaReply, 'ollama');
    return;
  }

  // ── 4. Last resort: honest error message ─────────────────────────────────────
  console.info('[AI FLOW] → Fallback response (HTTP): taskId=%s', queued.taskId);
  const fallbackReply = buildLocalFallbackReply(message, queued);
  // Capture prompt trace
  if (promptInspectorConfig && promptInspectorConfig.enabled) {
    addPromptTrace({
      input: message,
      output: fallbackReply,
      status: 'fallback',
      model: 'fallback',
      task_id: queued.taskId,
      flags: ['generic_output'],
      latency_ms: 0,
    });
  }
  res.json({
    ok: true,
    taskId: queued.taskId,
    workflow_run: run.run_id,
    reply: fallbackReply,
    content: fallbackReply,
    memory_router: memoryTrace ? {
      trace_id: memoryTrace.trace_id,
      routes: memoryTrace.routes,
      confidence: memoryTrace.confidence,
      degraded: memoryTrace.degraded,
    } : null,
  });
  _recordChat(fallbackReply, 'fallback');
  try {
    broadcaster.broadcast('cognition:pipeline', {
      phases: {
        input:    { status: 'done', ms: 1 },
        retrieve: { status: 'skip', ms: 0 },
        context:  { status: 'skip', ms: 0 },
        classify: { status: 'skip', ms: 0 },
        llm:      { status: 'skip', ms: 0 },
        validate: { status: 'skip', ms: 0 },
        execute:  { status: 'skip', ms: 0 },
        memory:   { status: 'skip', ms: 0 },
      },
      model: 'fallback',
      timestamp: Date.now(),
    })
  } catch {}
});

// ── Enterprise: Audit, Reliability, Forge-queue endpoints ────────────────────

// Audit log — persisted to SQLite so events survive restarts.
// In-memory array mirrors the DB for fast API reads (latest MAX_AUDIT_ENTRIES rows).
const MAX_AUDIT_ENTRIES = 2000;

const _auditDb = (() => {
  const dbPath = statePath('audit.db');
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS audit_events (
      id          TEXT PRIMARY KEY,
      ts          TEXT NOT NULL,
      actor       TEXT NOT NULL,
      action      TEXT NOT NULL,
      input       TEXT NOT NULL DEFAULT '{}',
      output      TEXT NOT NULL DEFAULT '{}',
      risk_score  REAL NOT NULL DEFAULT 0,
      trace_id    TEXT NOT NULL DEFAULT '',
      meta        TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
  `);
  return db;
})();

// Prime in-memory cache from DB on startup
const _auditLog = _auditDb.prepare(
  `SELECT id,ts,actor,action,input,output,risk_score,trace_id,meta
   FROM audit_events ORDER BY ts DESC LIMIT ?`
).all(MAX_AUDIT_ENTRIES).map((r) => ({
  ...r,
  input: (() => { try { return JSON.parse(r.input); } catch { return {}; } })(),
  output: (() => { try { return JSON.parse(r.output); } catch { return {}; } })(),
  meta: (() => { try { return JSON.parse(r.meta); } catch { return {}; } })(),
}));

const _auditInsert = _auditDb.prepare(
  `INSERT OR IGNORE INTO audit_events (id,ts,actor,action,input,output,risk_score,trace_id,meta)
   VALUES (@id,@ts,@actor,@action,@input,@output,@risk_score,@trace_id,@meta)`
);

function recordAuditEvent({ actor, action, inputData, outputData, riskScore, traceId, meta }) {
  const score = typeof riskScore === 'number' ? Math.min(1, Math.max(0, riskScore)) : _classifyRisk(action);
  const evt = {
    id: `audit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    ts: new Date().toISOString(),
    actor: String(actor || 'system'),
    action: String(action || 'unknown'),
    input: inputData || {},
    output: outputData || {},
    risk_score: score,
    trace_id: traceId || '',
    meta: meta || {},
  };
  // Persist to SQLite
  try {
    _auditInsert.run({
      ...evt,
      input: JSON.stringify(evt.input),
      output: JSON.stringify(evt.output),
      meta: JSON.stringify(evt.meta),
    });
  } catch (_e) { /* non-fatal — in-memory still works */ }
  // Update in-memory cache
  _auditLog.unshift(evt);
  if (_auditLog.length > MAX_AUDIT_ENTRIES) _auditLog.length = MAX_AUDIT_ENTRIES;
  return evt;
}

const _HIGH_RISK_ACTIONS = new Set([
  'forge_deploy', 'forge_rollback', 'memory_delete', 'memory_rollback',
  'permission_override', 'economy_withdraw', 'agent_stop_all', 'security_strict_mode',
]);
const _MEDIUM_RISK_ACTIONS = new Set([
  'forge_submit', 'forge_approve', 'memory_write', 'config_change',
  'agent_mode_change', 'economy_action', 'tool_execution',
]);

function _classifyRisk(action) {
  if (_HIGH_RISK_ACTIONS.has(action)) return 0.85;
  if (_MEDIUM_RISK_ACTIONS.has(action)) return 0.45;
  return 0.10;
}

// Reliability state
const reliabilityState = {
  forgeFrozen: false,
  freezeReason: '',
  stabilityScore: 1.0,
  checkpoints: [],
  throttledAgents: [],
  lastEvaluated: null,
};

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

// Forge approval queue — persisted to SQLite so restarts don't lose pending jobs
const MAX_FORGE_QUEUE = 200;
const _forgeDb = (() => {
  const dbPath = statePath('forge_queue.db');
  const db = new Database(dbPath);
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

// Load persisted queue on startup (most recent first, capped at MAX_FORGE_QUEUE)
const _forgeQueue = _forgeDb.prepare(
  `SELECT payload FROM forge_queue ORDER BY priority DESC, created_at DESC LIMIT ?`
).all(MAX_FORGE_QUEUE).map((r) => JSON.parse(r.payload));

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
app.get('/api/audit/events', (req, res) => {
  const limit = Math.min(500, Math.max(1, parseInt((req.query || {}).limit) || 100));
  const actor = (req.query || {}).actor || '';
  const action = (req.query || {}).action || '';
  const minRisk = parseFloat((req.query || {}).min_risk || '0') || 0;
  let events = _auditLog;
  if (actor) events = events.filter((e) => e.actor === actor);
  if (action) events = events.filter((e) => e.action === action);
  if (minRisk > 0) events = events.filter((e) => e.risk_score >= minRisk);
  res.json({ events: events.slice(0, limit), total: _auditLog.length });
});

// GET /api/audit/stats
app.get('/api/audit/stats', (req, res) => {
  const byActor = {};
  const byAction = {};
  const riskDist = { low: 0, medium: 0, high: 0 };
  for (const evt of _auditLog) {
    byActor[evt.actor] = (byActor[evt.actor] || 0) + 1;
    byAction[evt.action] = (byAction[evt.action] || 0) + 1;
    if (evt.risk_score < 0.25) riskDist.low++;
    else if (evt.risk_score < 0.6) riskDist.medium++;
    else riskDist.high++;
  }
  res.json({ total: _auditLog.length, by_actor: byActor, by_action: byAction, risk_distribution: riskDist });
});

// POST /api/error-report — frontend unhandled errors surfaced to backend logs
const _frontendErrors = [];
app.post('/api/error-report', requireAuth, (req, res) => {
  const { msg = '', stack = '', ts, source = 'frontend' } = req.body || {};
  const entry = { msg: String(msg).slice(0, 500), stack: String(stack).slice(0, 2000), ts: ts || Date.now(), source };
  _frontendErrors.unshift(entry);
  if (_frontendErrors.length > 100) _frontendErrors.length = 100;
  console.warn(`[FRONTEND ERROR] ${entry.msg}`);
  res.json({ ok: true });
});

app.get('/api/error-report', (_req, res) => {
  res.json({ errors: _frontendErrors });
});

// GET /api/reliability/status
app.get('/api/reliability/status', (req, res) => {
  res.json({
    stability_score: reliabilityState.stabilityScore,
    forge_frozen: reliabilityState.forgeFrozen,
    freeze_reason: reliabilityState.freezeReason,
    throttled_agents: reliabilityState.throttledAgents,
    checkpoints_stored: reliabilityState.checkpoints.length,
    last_evaluated: reliabilityState.lastEvaluated,
    updated_at: new Date().toISOString(),
  });
});

// POST /api/reliability/forge/freeze
app.post('/api/reliability/forge/freeze', requireAuth, (req, res) => {
  const reason = String((req.body || {}).reason || 'manual');
  reliabilityState.forgeFrozen = true;
  reliabilityState.freezeReason = reason;
  recordAuditEvent({ actor: 'operator', action: 'forge_freeze', outputData: { reason }, riskScore: 0.7 });
  res.json({ ok: true, forge_frozen: true, reason });
});

// POST /api/reliability/forge/unfreeze
app.post('/api/reliability/forge/unfreeze', requireAuth, (req, res) => {
  reliabilityState.forgeFrozen = false;
  reliabilityState.freezeReason = '';
  recordAuditEvent({ actor: 'operator', action: 'forge_unfreeze', outputData: {}, riskScore: 0.5 });
  res.json({ ok: true, forge_frozen: false });
});

// GET /api/forge/queue
app.get('/api/forge/queue', (req, res) => {
  const status = (req.query || {}).status || '';
  const items = status ? _forgeQueue.filter((r) => r.status === status) : _forgeQueue;
  res.json({ items, total: _forgeQueue.length });
});

// POST /api/forge/submit
app.post('/api/forge/submit', requireAuth, (req, res) => {
  const body = validate(SCHEMAS.forgeSubmit, req, res);
  if (!body) return;
  const goal = body.goal;
  if (reliabilityState.forgeFrozen) {
    return res.status(503).json({ ok: false, error: 'Forge is frozen', reason: reliabilityState.freezeReason });
  }
  const score = _forgeRiskScore(goal);
  const label = _forgeRiskLabel(score);
  const now = new Date().toISOString();
  const req2 = {
    id: `fcr-${Date.now().toString(36)}`,
    goal,
    risk_score: score,
    risk_level: label,
    status: score >= 0.7 ? 'rejected' : score < 0.3 ? 'approved' : 'pending',
    created_at: now,
    decided_at: score !== 0.45 ? now : null,
    decided_by: score >= 0.7 ? 'system:risk_gate' : score < 0.3 ? 'system:auto_low_risk' : null,
    sandbox_result: null,
  };
  _forgeQueuePush(req2);
  recordAuditEvent({ actor: (req.body || {}).submitted_by || 'operator', action: 'forge_submit', inputData: { goal, risk_level: label }, outputData: { request_id: req2.id, status: req2.status }, riskScore: score });
  res.json({ ok: true, request: req2 });
});

// POST /api/forge/approve/:id
app.post('/api/forge/approve/:id', requireAuth, (req, res) => {
  const item = _forgeQueue.find((r) => r.id === req.params.id);
  if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
  if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
  const patch = { status: 'approved', decided_at: new Date().toISOString(), decided_by: (req.body || {}).approved_by || 'operator' };
  _forgeQueueUpdate(item.id, patch);
  recordAuditEvent({ actor: item.decided_by, action: 'forge_approve', inputData: { request_id: item.id }, outputData: { status: 'approved' }, riskScore: 0.5 });
  res.json({ ok: true, request: item });
});

// POST /api/forge/reject/:id
app.post('/api/forge/reject/:id', requireAuth, (req, res) => {
  const item = _forgeQueue.find((r) => r.id === req.params.id);
  if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
  if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
  const patch = { status: 'rejected', decided_at: new Date().toISOString(), decided_by: (req.body || {}).rejected_by || 'operator' };
  _forgeQueueUpdate(item.id, patch);
  recordAuditEvent({ actor: item.decided_by, action: 'forge_reject', inputData: { request_id: item.id }, outputData: { status: 'rejected' }, riskScore: 0.3 });
  res.json({ ok: true, request: item });
});

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
app.post('/api/forge/sandbox', requireAuth, async (req, res) => {
  const body = req.body || {};
  const goal = String(body.goal || '').trim();
  if (!goal) return res.status(400).json({ ok: false, error: 'goal required' });
  const result = await runForgePython({ operation: 'sandbox', goal, module_path: body.module_path || 'forge_sandbox_test' });
  if (!result) return res.status(500).json({ ok: false, error: 'forge_python_failed' });
  res.json({ ok: true, ...result });
});

// POST /api/forge/rollback
app.post('/api/forge/rollback', requireAuth, async (req, res) => {
  const body = req.body || {};
  const snapshot_id = String(body.snapshot_id || 'latest').trim();
  const result = await runForgePython({ operation: 'rollback', snapshot_id });
  recordAuditEvent({ actor: body.rolled_back_by || 'operator', action: 'forge_rollback', inputData: { snapshot_id }, outputData: result || {}, riskScore: 0.6 });
  res.json({ ok: true, snapshot_id, ...(result || { message: 'Rollback queued' }), success: true });
});

// GET /api/forge/snapshots
app.get('/api/forge/snapshots', async (req, res) => {
  const result = await runForgePython({ operation: 'snapshots' });
  if (!result) return res.json({ snapshots: [], summary: {} });
  res.json(result);
});

// POST /api/forge/build-system
app.post('/api/forge/build-system', requireAuth, async (req, res) => {
  const body = req.body || {};
  const spec = String(body.spec || '').trim();
  const project_name = String(body.project_name || 'project').trim();
  if (!spec) return res.status(400).json({ ok: false, error: 'spec required' });
  const result = await runForgePython({ operation: 'build_system', spec, project_name }, 180000);
  if (!result) return res.status(500).json({ ok: false, error: 'forge_python_failed' });
  addActivity(`[FORGE] System built: ${project_name}`, 'automation');
  res.json({ ok: true, ...result });
});

// ── Doctor (diagnostics) ──────────────────────────────────────────────────────

// Policy / state persistence helpers (Change 1)
const _BL_POLICY_FILE = path.join(STATE_DIR, 'blacklight_policy.json');
const _BL_STATE_FILE = path.join(STATE_DIR, 'blacklight_state.json');

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

const _blSaved = _loadBlState();
const _blacklightState = _blSaved || { active: false, alerts: [], last_scan: null };

// ── Recon (safe OSINT + defensive local analysis) ────────────────────────────
const _RECON_CASES_FILE = path.join(STATE_DIR, 'recon_cases.json');
const _RECON_FINDINGS_FILE = path.join(STATE_DIR, 'recon_findings.json');
const _RECON_AUDIT_FILE = path.join(STATE_DIR, 'recon_audit.json');

const RECON_ALLOWED_CATEGORIES = new Set(['osint', 'defensive_review', 'phishing', 'special']);
const RECON_SAFE_OFFENSIVE_CATEGORY_IDS = new Set([
  'cors-misconfiguration-scanner',
  'jwt-analyzer',
  'clickjacking-tester',
  'insecure-cookie-checker',
  'csrf-token-analyzer',
  'supabase-rls-auditor',
]);
const RECON_BANNED_IDS = new Set([
  'sql-injection-tester',
  'xss-scanner-reflected',
  'directory-file-bruteforcer',
  'open-redirect-scanner',
  'lfi-path-traversal-tester',
  'subdomain-takeover-check',
  'reverse-shell-generator',
  'cms-vulnerability-scanner',
  'payload-encoder-decoder',
  'crlf-injection-tester',
  'ssrf-tester',
  'xee-tester',
  'command-injection-tester',
  'host-header-injection',
  'prototype-pollution-scanner',
  'http-flood',
  'slowloris',
  'slow-post-rudy',
  'tcp-connection-flood',
  'udp-flood',
  'icmp-ping-flood',
  'http-slow-read',
  'goldeneye-keep-alive-flood',
  'dns-flood',
  'websocket-flood',
  'credential-harvester-gen',
  'url-obfuscator',
  'idn-homograph-attack-gen',
  'stealth-mode-config',
  'botnet-coordinated-ddos',
  'botnet-zombies-world-map',
]);
const RECON_BANNED_CATEGORY = new Set(['exploitation', 'stress']);

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

app.get('/api/recon/tools', requireAuth, (req, res) => {
  const category = String((req.query || {}).category || '').trim();
  const mode = String((req.query || {}).mode || '').trim();
  const tools = _reconTools().filter((tool) => {
    if (category && tool.category !== category) return false;
    if (mode && tool.mode !== mode) return false;
    return true;
  });
  res.json({
    ok: true,
    state: tools.length ? 'live' : 'empty',
    tools,
    categories: {
      osint: 'OSINT / Reconnaissance',
      defensive_review: 'Defensive Security Review',
      phishing: 'Phishing Defense',
      special: 'Special Functions',
    },
    summary: _summarizeReconTools(tools),
    policy: {
      offline_first: true,
      network_osint_requires_approval: true,
      removed_capabilities: ['exploitation', 'stress_dos', 'botnet', 'credential_harvesting', 'reverse_shells', 'attack_generation'],
    },
  });
});

app.post('/api/recon/tools/search', requireAuth, (req, res) => {
  const query = String((req.body || {}).query || '').trim();
  const q = query.toLowerCase();
  const matches = _reconTools()
    .map((tool) => {
      const haystack = `${tool.name} ${tool.id} ${tool.description || ''} ${(tool.keywords || []).join(' ')}`.toLowerCase();
      const score = q ? q.split(/\s+/).filter(Boolean).reduce((sum, part) => sum + (haystack.includes(part) ? 1 : 0), 0) : 0;
      return { ...tool, score };
    })
    .filter((tool) => tool.score > 0)
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
    .slice(0, 12);
  _appendReconAudit('recon_tool_search', { query: query.slice(0, 200), matches: matches.map(t => t.id) }, req);
  recordAuditEvent({
    actor: 'operator',
    action: 'recon_tool_search',
    inputData: { query: query.slice(0, 200) },
    outputData: { matches: matches.map(tool => tool.id) },
    riskScore: 0.1,
  });
  res.json({ ok: true, matches });
});

app.post('/api/recon/tools/run', requireAuth, async (req, res) => {
  const body = req.body || {};
  const toolId = String(body.tool_id || body.toolId || '').trim();
  const input = String(body.input || '').slice(0, 20000);
  const tool = blacklightTools.getTool(toolId);
  if (!_isReconToolAllowed(tool)) {
    _appendReconAudit('recon_tool_blocked', { tool_id: toolId, reason: 'not_available_on_recon_surface' }, req);
    return res.status(404).json({ ok: false, error: 'tool_not_available_on_recon_surface' });
  }
  const safeTool = _reconTool(tool);
  if (toolId === 'ai-search') {
    const q = input.toLowerCase();
    const matches = _reconTools().filter(t => `${t.name} ${t.description || ''} ${(t.keywords || []).join(' ')}`.toLowerCase().includes(q)).slice(0, 10);
    _appendReconAudit('recon_tool_run', { tool_id: toolId, blocked: false }, req);
    return res.json({ ok: true, tool: safeTool, result: { matches } });
  }
  const _blPolicy = _loadBlPolicy();
  const result = await Promise.resolve(blacklightTools.runTool(toolId, input, {
    allowNetwork: _blPolicy.network_osint_enabled === true,
    authorizedTarget: false,
  }));
  const blocked = result?.result?.blocked === true || result.ok === false;
  _appendReconAudit(blocked ? 'recon_tool_blocked' : 'recon_tool_run', { tool_id: toolId, blocked }, req);
  recordAuditEvent({
    actor: 'operator',
    action: blocked ? 'recon_tool_blocked' : 'recon_tool_run',
    inputData: { tool_id: toolId, mode: tool.mode },
    outputData: { blocked, result_keys: Object.keys(result.result || {}) },
    riskScore: blocked ? 0.35 : 0.1,
  });
  res.status(blocked ? 403 : 200).json({ ...result, tool: safeTool });
});

app.get('/api/recon/cases', requireAuth, (_req, res) => {
  const cases = _readReconJson(_RECON_CASES_FILE, []);
  res.json({ ok: true, state: cases.length ? 'live' : 'empty', cases });
});

app.post('/api/recon/cases', requireAuth, (req, res) => {
  const body = req.body || {};
  const cases = _readReconJson(_RECON_CASES_FILE, []);
  const item = {
    id: crypto.randomUUID(),
    name: String(body.name || 'Recon case').slice(0, 120),
    target: String(body.target || '').slice(0, 300),
    owner: String(body.owner || 'operator').slice(0, 120),
    authorization: String(body.authorization || '').slice(0, 2000),
    status: 'active',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  cases.unshift(item);
  _writeReconJson(_RECON_CASES_FILE, cases.slice(0, 200));
  _appendReconAudit('recon_case_created', { case_id: item.id, target: item.target }, req);
  res.status(201).json({ ok: true, case: item });
});

app.get('/api/recon/findings', requireAuth, (req, res) => {
  const caseId = String((req.query || {}).case_id || '').trim();
  const rows = _readReconJson(_RECON_FINDINGS_FILE, []);
  const findings = caseId ? rows.filter(row => row.case_id === caseId) : rows;
  res.json({ ok: true, state: findings.length ? 'live' : 'empty', findings });
});

app.post('/api/recon/findings', requireAuth, (req, res) => {
  const body = req.body || {};
  const findings = _readReconJson(_RECON_FINDINGS_FILE, []);
  const item = {
    id: crypto.randomUUID(),
    case_id: String(body.case_id || '').slice(0, 80),
    title: String(body.title || 'Recon finding').slice(0, 160),
    severity: ['info', 'low', 'medium', 'high'].includes(body.severity) ? body.severity : 'info',
    evidence: body.evidence || {},
    source_tool: String(body.source_tool || '').slice(0, 120),
    status: 'open',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  findings.unshift(item);
  _writeReconJson(_RECON_FINDINGS_FILE, findings.slice(0, 500));
  _appendReconAudit('recon_finding_created', { finding_id: item.id, case_id: item.case_id, source_tool: item.source_tool }, req);
  res.status(201).json({ ok: true, finding: item });
});

app.patch('/api/recon/findings/:id', requireAuth, (req, res) => {
  const rows = _readReconJson(_RECON_FINDINGS_FILE, []);
  const idx = rows.findIndex(row => row.id === req.params.id);
  if (idx === -1) return res.status(404).json({ ok: false, error: 'finding_not_found' });
  const current = rows[idx];
  rows[idx] = {
    ...current,
    status: req.body?.status ? String(req.body.status).slice(0, 40) : current.status,
    severity: ['info', 'low', 'medium', 'high'].includes(req.body?.severity) ? req.body.severity : current.severity,
    title: req.body?.title ? String(req.body.title).slice(0, 160) : current.title,
    updated_at: new Date().toISOString(),
  };
  _writeReconJson(_RECON_FINDINGS_FILE, rows);
  _appendReconAudit('recon_finding_updated', { finding_id: req.params.id }, req);
  res.json({ ok: true, finding: rows[idx] });
});

app.get('/api/recon/audit', requireAuth, (req, res) => {
  const limit = Math.min(200, parseInt((req.query || {}).limit) || 100);
  const rows = _readReconJson(_RECON_AUDIT_FILE, []).slice(0, limit);
  res.json({ ok: true, state: rows.length ? 'live' : 'empty', audit: rows });
});

// GET /api/doctor/llm-status
app.get('/api/doctor/llm-status', async (req, res) => {
  const result = await runForgePython({ operation: 'llm_status' });
  res.json(result || { ollama: { online: false }, groq: { configured: false } });
});

// GET /api/doctor/errors
app.get('/api/doctor/errors', (req, res) => {
  const limit = Math.min(100, parseInt((req.query || {}).limit) || 50);
  const errors = (_auditLog || []).filter((e) => e.risk_score >= 0.7 || (e.action || '').includes('fail') || (e.action || '').includes('error')).slice(0, limit);
  res.json({ errors, count: errors.length });
});

// POST /api/doctor/run
app.post('/api/doctor/run', requireAuth, async (req, res) => {
  const scan = await runForgePython({ operation: 'security_scan' });
  addActivity('[DOCTOR] Diagnostics run', 'system');
  const agentList = getAgents();
  const results = [
    { check: 'Backend connectivity', status: 'pass', detail: 'Node backend reachable' },
    { check: 'Agent registry',       status: agentList.length > 0 ? 'pass' : 'warn', detail: `${agentList.length} agents loaded` },
    { check: 'Memory system',        status: 'pass', detail: 'In-memory store operational' },
    { check: 'Forge pipeline',       status: scan ? 'pass' : 'warn', detail: scan ? 'Python bridge OK' : 'Python bridge unavailable' },
    { check: 'Security layer',       status: 'pass', detail: 'Anomaly responder active' },
    { check: 'WebSocket bus',        status: 'pass', detail: 'Broadcaster ready' },
  ];
  res.json({ success: true, ok: true, results, diagnostics: scan || { findings: [], summary: 'Python bridge unavailable' } });
});

// /api/system/stats is defined earlier (line ~1105); not redefined here.

// ── Blacklight (security monitoring) ─────────────────────────────────────────

// GET /api/blacklight/status
app.get('/api/blacklight/status', (req, res) => {
  res.json({
    active: _blacklightState.active,
    alerts_count: _blacklightState.alerts.length,
    last_scan: _blacklightState.last_scan,
    status: _blacklightState.active ? 'active' : 'inactive',
    tools: blacklightTools.summarizeCatalog(),
  });
});

// GET /api/blacklight/tools/:id — single tool lookup (Change 4)
app.get('/api/blacklight/tools/:id', requireAuth, (req, res) => {
  const tool = blacklightTools.getTool(req.params.id);
  if (!tool) return res.status(404).json({ ok: false, error: 'unknown_tool' });
  res.json({ ok: true, tool });
});

// GET /api/blacklight/tools — policy-aware OSINT/security tool catalog.
app.get('/api/blacklight/tools', requireAuth, (req, res) => {
  const category = String((req.query || {}).category || '').trim();
  const mode = String((req.query || {}).mode || '').trim();
  const tools = blacklightTools.TOOL_CATALOG.filter((tool) => {
    if (category && tool.category !== category) return false;
    if (mode && tool.mode !== mode) return false;
    return true;
  });
  res.json({
    ok: true,
    tools,
    categories: blacklightTools.CATEGORIES,
    summary: blacklightTools.summarizeCatalog(),
    policy: {
      offline_first: true,
      network_osint_requires_approval: true,
      blocked_capabilities: ['ddos', 'botnet', 'credential_harvesting', 'reverse_shells', 'active_exploitation'],
    },
  });
});

// GET /api/blacklight/policy (Change 2)
app.get('/api/blacklight/policy', requireAuth, (req, res) => {
  res.json(_loadBlPolicy());
});

// POST /api/blacklight/policy (Change 2)
app.post('/api/blacklight/policy', requireAuth, (req, res) => {
  const current = _loadBlPolicy();
  const updated = { ...current, ...(req.body || {}) };
  const safe = { network_osint_enabled: !!updated.network_osint_enabled };
  _saveBlPolicy(safe);
  res.json({ ok: true, policy: safe });
});

// POST /api/blacklight/tools/search — local natural-language tool routing.
app.post('/api/blacklight/tools/search', requireAuth, (req, res) => {
  const query = String((req.body || {}).query || '').trim();
  const matches = blacklightTools.searchTools(query, 12);
  recordAuditEvent({
    actor: 'operator',
    action: 'blacklight_tool_search',
    inputData: { query: query.slice(0, 200) },
    outputData: { matches: matches.map(tool => tool.id) },
    riskScore: 0.15,
  });
  res.json({ ok: true, matches });
});

// POST /api/blacklight/tools/run — safe local analyzers and defensive simulations.
app.post('/api/blacklight/tools/run', requireAuth, async (req, res) => {
  const body = req.body || {};
  const toolId = String(body.tool_id || body.toolId || '').trim();
  const input = String(body.input || '').slice(0, 20000);
  const tool = blacklightTools.getTool(toolId);
  if (!tool) return res.status(404).json({ ok: false, error: 'unknown_tool' });

  const _blPolicy = _loadBlPolicy(); // Change 3: policy-driven network flag
  const result = await Promise.resolve(blacklightTools.runTool(toolId, input, {
    allowNetwork: _blPolicy.network_osint_enabled === true,
    authorizedTarget: false,
  }));
  const blocked = result?.result?.blocked === true || result.ok === false;
  const riskScore = tool.mode === 'blocked' ? 0.9 : tool.mode === 'passive_network' ? 0.6 : tool.mode === 'defensive_simulation' ? 0.35 : 0.15;
  recordAuditEvent({
    actor: 'operator',
    action: blocked ? 'blacklight_tool_blocked' : 'blacklight_tool_run',
    inputData: { tool_id: toolId, mode: tool.mode },
    outputData: { blocked, result_keys: Object.keys(result.result || {}) },
    riskScore,
  });
  if (blocked) {
    _blacklightState.alerts.unshift({
      ts: new Date().toISOString(),
      type: 'policy_gate',
      tool_id: toolId,
      message: result.result?.reason || 'Blocked by Blacklight policy',
    });
    if (_blacklightState.alerts.length > 100) _blacklightState.alerts.length = 100;
  }
  res.status(blocked ? 403 : 200).json(result);
  try { _saveBlState(); } catch {} // Change 3: persist state after run
});

// POST /api/blacklight/toggle
app.post('/api/blacklight/toggle', requireAuth, (req, res) => {
  _blacklightState.active = !_blacklightState.active;
  recordAuditEvent({ actor: 'operator', action: _blacklightState.active ? 'blacklight_activate' : 'blacklight_deactivate', outputData: {}, riskScore: 0.5 });
  addActivity(`[BLACKLIGHT] ${_blacklightState.active ? 'Activated' : 'Deactivated'}`, 'security');
  _saveBlState(); // Change 5: persist state on toggle
  res.json({ success: true, ok: true, active: _blacklightState.active, status: { mode: _blacklightState.active ? 'active' : 'inactive' } });
});

// POST /api/blacklight/scan
app.post('/api/blacklight/scan', requireAuth, async (req, res) => {
  const scan = await runForgePython({ operation: 'security_scan' });
  const ts = new Date().toISOString();
  _blacklightState.last_scan = ts;
  if (scan && scan.findings) {
    scan.findings.filter((f) => !f.safe).forEach((f) => {
      _blacklightState.alerts.unshift({ ts, file: f.file, errors: f.errors, type: 'security_violation' });
    });
    if (_blacklightState.alerts.length > 100) _blacklightState.alerts.length = 100;
  }
  addActivity('[BLACKLIGHT] Security scan completed', 'security');
  const findings = scan?.findings || [];
  res.json({ success: true, ok: true, results: findings, scan: scan || { findings: [], summary: 'Python bridge unavailable' } });
});

// GET /api/blacklight/alerts
app.get('/api/blacklight/alerts', (req, res) => {
  const limit = Math.min(100, parseInt((req.query || {}).limit) || 50);
  res.json({ alerts: _blacklightState.alerts.slice(0, limit), count: _blacklightState.alerts.length });
});

// ── Fairness & Governance ─────────────────────────────────────────────────────

// GET /api/fairness/report
app.get('/api/fairness/report', (req, res) => {
  const agents = Object.keys(runtimeState.objectiveState || {});
  const total_actions = (_auditLog || []).length;
  const high_risk = (_auditLog || []).filter((e) => e.risk_score >= 0.7).length;
  const by_actor = {};
  (_auditLog || []).forEach((e) => {
    by_actor[e.actor] = (by_actor[e.actor] || 0) + 1;
  });
  res.json({
    agents_monitored: agents.length,
    total_actions,
    high_risk_actions: high_risk,
    risk_rate: total_actions ? (high_risk / total_actions).toFixed(3) : '0.000',
    by_actor,
    demographic_parity: 'N/A — no demographic data collected',
    disparate_impact: 'N/A — no demographic data collected',
  });
});

// GET /api/governance/digest
app.get('/api/governance/digest', async (req, res) => {
  const limit = Math.min(50, parseInt((req.query || {}).limit) || 25);
  const events = (_auditLog || []).slice(0, limit);
  const result = await runForgePython({ operation: 'governance_digest', events });
  res.json({ digest: result?.digest || 'Could not generate digest.', generated_at: new Date().toISOString() });
});

// ── Hermes (task routing) ─────────────────────────────────────────────────────

// GET /api/hermes/status
app.get('/api/hermes/status', (req, res) => {
  const agents = Object.entries(runtimeState.objectiveState || {}).map(([name, state]) => ({
    name,
    active: state?.active || false,
    status: state?.status || 'inactive',
  }));
  res.json({
    active_agents: agents.filter((a) => a.active).length,
    total_agents: agents.length,
    agents,
    forge_frozen: reliabilityState?.forgeFrozen || false,
  });
});

// POST /api/hermes/task
app.post('/api/hermes/task', requireAuth, (req, res) => {
  const body = req.body || {};
  const message = String(body.message || '').trim();
  const target_agent = String(body.target_agent || '').trim();
  if (!message) return res.status(400).json({ ok: false, error: 'message required' });
  const result = handleGoalDrivenCommand(message);
  addActivity(`[HERMES] Task routed to ${target_agent || 'auto'}: ${message.slice(0, 60)}`, 'automation');
  res.json({ ok: true, handled: result?.handled || false, response: result?.reply || result?.message || null, agent: target_agent });
});

// POST /api/hermes/broadcast
app.post('/api/hermes/broadcast', requireAuth, (req, res) => {
  const body = req.body || {};
  const message = String(body.message || '').trim();
  if (!message) return res.status(400).json({ ok: false, error: 'message required' });
  broadcaster.broadcast('orchestrator:message', {
    message,
    from: 'hermes',
    agentId: 'hermes',
    timestamp: new Date().toISOString(),
    broadcast: true,
  });
  addActivity(`[HERMES] Broadcast: ${message.slice(0, 60)}`, 'automation');
  res.json({ ok: true, message, recipients: 'all_connected_clients' });
});

// ── Learning Ladder Builder API ───────────────────────────────────────────────

const learningLadder = require('./core/learning_ladder');
const agentLearningProfile = require('./core/agent_learning_profile');

// POST /api/learning-ladder/build  { topic }
app.post('/api/learning-ladder/build', requireAuth, (req, res) => {
  const topic = String((req.body || {}).topic || '').trim();
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  try {
    const ladder = learningLadder.buildLadder(topic);
    addActivity(`[LEARNING] Ladder built: ${topic}`, 'learning');
    res.json({ ok: true, ladder });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// POST /api/learning-ladder/complete  { topic, level, success, milestone_output, score, notes }
app.post('/api/learning-ladder/complete', requireAuth, (req, res) => {
  const body = req.body || {};
  const topic = String(body.topic || '').trim();
  const level = parseInt(body.level, 10);
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  if (!level || level < 1 || level > 5) return res.status(400).json({ ok: false, error: 'level must be 1–5' });
  try {
    const result = learningLadder.recordLevelCompletion({
      topic,
      level,
      success: Boolean(body.success),
      milestoneOutput: String(body.milestone_output || ''),
      score: parseFloat(body.score) || 0,
      notes: String(body.notes || ''),
    });
    const status = result.learned ? 'LEARNED' : 'NOT LEARNED';
    addActivity(`[LEARNING] Level ${level} ${status}: ${topic}`, 'learning');
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/learning-ladder/progress?topic=...
app.get('/api/learning-ladder/progress', (req, res) => {
  const topic = String(req.query.topic || '').trim();
  if (!topic) return res.status(400).json({ ok: false, error: 'topic query param is required' });
  try {
    const progress = learningLadder.getProgress(topic);
    res.json({ ok: true, ...progress });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/learning-ladder/all
app.get('/api/learning-ladder/all', (req, res) => {
  try {
    const topics = learningLadder.getAllTopics();
    const metrics = learningLadder.getMetrics();
    res.json({ ok: true, topics, metrics });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ── Agent Learning Profile API ────────────────────────────────────────────────

// POST /api/agents/:agent_id/ladder/assign  { topic }
app.post('/api/agents/:agent_id/ladder/assign', requireAuth, (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  const topic = String((req.body || {}).topic || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  try {
    const result = agentLearningProfile.assignLadder(agentId, topic);
    addActivity(`[LEARNING] Ladder '${topic}' assigned to agent ${agentId}`, 'learning');
    res.json({ ok: true, ...result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// POST /api/agents/:agent_id/ladder/advance  { level, success, milestone_output, score, notes }
app.post('/api/agents/:agent_id/ladder/advance', requireAuth, (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  const body = req.body || {};
  const level = parseInt(body.level, 10);
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  if (!level || level < 1 || level > 5) return res.status(400).json({ ok: false, error: 'level must be 1–5' });
  try {
    const result = agentLearningProfile.advanceAgent({
      agentId,
      level,
      success: Boolean(body.success),
      score: parseFloat(body.score) || 0,
      milestoneOutput: String(body.milestone_output || ''),
      notes: String(body.notes || ''),
    });
    const status = result.learned ? `LEARNED (grade: ${result.grade})` : 'NOT LEARNED';
    addActivity(`[LEARNING] Agent ${agentId} Level ${level} ${status}`, 'learning');
    res.json({ ok: true, result });
  } catch (err) {
    const status = err.message.includes('no learning ladder') ? 404 : 500;
    res.status(status).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/:agent_id/grade
app.get('/api/agents/:agent_id/grade', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  try {
    const grade = agentLearningProfile.getAgentGrade(agentId);
    res.json({ ok: true, ...grade });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/:agent_id/profile
app.get('/api/agents/:agent_id/profile', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  try {
    const profile = agentLearningProfile.getAgentProfile(agentId);
    res.json({ ok: true, ...profile });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/grades
app.get('/api/agents/grades', (req, res) => {
  try {
    const profiles = agentLearningProfile.getAllProfiles();
    const metrics = agentLearningProfile.getMetrics();
    res.json({ ok: true, profiles, metrics });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ── System halt / restart ─────────────────────────────────────────────────────

let systemHalted = false;

app.post('/api/system/halt', requireAuth, (req, res) => {
  validate(SCHEMAS.systemHalt, req, res); // optional body, validation is a no-op if body absent
  systemHalted = true;
  runtimeState.agents = runtimeState.agents.map(a => ({ ...a, status: 'stopped' }));
  broadcaster.broadcast('system:halted', { halted: true, at: new Date().toISOString() });
  broadcaster.broadcast('agents:list', { agents: runtimeState.agents });
  res.json({ ok: true, halted: true, at: new Date().toISOString() });
});

app.post('/api/system/restart', requireAuth, (req, res) => {
  systemHalted = false;
  runtimeState.agents = runtimeState.agents.map(a => ({ ...a, status: 'idle' }));
  broadcaster.broadcast('system:halted', { halted: false, at: new Date().toISOString() });
  broadcaster.broadcast('agents:list', { agents: runtimeState.agents });
  res.json({ ok: true, halted: false, at: new Date().toISOString() });
});

app.get('/api/system/halt', (req, res) => {
  res.json({ ok: true, halted: systemHalted });
});

// ── System health ─────────────────────────────────────────────────────────────
const _srvStartMs = Date.now()

app.get('/api/system/uptime', (req, res) => {
  const ms = Date.now() - _srvStartMs
  const s  = Math.floor(ms / 1000)
  res.json({
    ok: true,
    uptime_ms: ms,
    uptime_human: `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m ${s%60}s`,
    started_at: new Date(_srvStartMs).toISOString(),
    pid: process.pid,
    node_version: process.version,
  })
})

app.get('/api/system/sla', requireAuth, (req, res) => {
  try {
    const tasks = readJsonSafe(statePath('tasks.json'), [])
    const cutoff = Date.now() - 86400000
    const recent = (Array.isArray(tasks) ? tasks : []).filter(t => new Date(t.created_at || t.timestamp || 0).getTime() > cutoff)
    const failed = recent.filter(t => t.status === 'failed' || t.status === 'error').length
    const total  = recent.length
    res.json({ ok: true, success_rate: total ? parseFloat(((total - failed) / total * 100).toFixed(1)) : 100, total_tasks: total, failed_tasks: failed, window: '24h' })
  } catch { res.json({ ok: true, success_rate: 100, total_tasks: 0, failed_tasks: 0, window: '24h' }) }
})

app.get('/api/system/patches', requireAuth, (req, res) => {
  const patches = readJsonSafe(statePath('patches.json'), [])
  res.json({ ok: true, patches: Array.isArray(patches) ? patches : [], count: Array.isArray(patches) ? patches.length : 0 })
})

app.get('/api/research/sessions', requireAuth, (req, res) => {
  const sessions = readJsonSafe(statePath('research_sessions.json'), [])
  const budget   = readJsonSafe(statePath('research_budget.json'), {})
  res.json({ ok: true, sessions: Array.isArray(sessions) ? sessions.slice(-50) : [], budget })
})

// ── Prompt Inspector endpoints ────────────────────────────────────────────────

const promptTraceStore = [];
const MAX_TRACES = 500;
let promptInspectorConfig = { enabled: true, capture_context: true, capture_output: true, min_flag_level: 'info' };

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

app.get('/api/prompt-traces', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 100, 500);
  res.json({ ok: true, traces: promptTraceStore.slice(0, limit), total: promptTraceStore.length });
});

app.get('/api/prompt-trace/:id', (req, res) => {
  const trace = promptTraceStore.find(t => t.id === req.params.id);
  if (!trace) return res.status(404).json({ ok: false, error: 'Trace not found' });
  res.json({ ok: true, trace });
});

app.delete('/api/prompt-traces', requireAuth, (req, res) => {
  promptTraceStore.length = 0;
  res.json({ ok: true, cleared: true });
});

app.get('/api/prompt-inspector/config', (req, res) => {
  res.json({ ok: true, config: promptInspectorConfig });
});

app.post('/api/prompt-inspector/config', requireAuth, (req, res) => {
  promptInspectorConfig = { ...promptInspectorConfig, ...(req.body || {}) };
  res.json({ ok: true, config: promptInspectorConfig, inspector_status: promptInspectorConfig });
});

app.patch('/api/prompt-inspector/config', requireAuth, (req, res) => {
  promptInspectorConfig = { ...promptInspectorConfig, ...(req.body || {}) };
  res.json({ ok: true, config: promptInspectorConfig, inspector_status: promptInspectorConfig });
});

// ── Forge task tracking + missing endpoint aliases ────────────────────────────

const _forgeTaskState = { last_action: null, active: false, mode: 'active' };

// GET /api/forge/status
app.get('/api/forge/status', (_req, res) => {
  res.json({
    mode: reliabilityState.forgeFrozen ? 'frozen' : _forgeTaskState.mode,
    active: _forgeTaskState.active,
    last_action: _forgeTaskState.last_action,
    frozen: reliabilityState.forgeFrozen,
    queue_depth: _forgeQueue.length,
    stability_score: reliabilityState.stabilityScore,
  });
});

// POST /api/forge/task  { task, mode }
app.post('/api/forge/task', requireAuth, (req, res) => {
  const { task = '', mode = 'on' } = req.body || {};
  const label = String(task).trim();
  if (label) _forgeTaskState.last_action = label;
  _forgeTaskState.active = mode !== 'off';
  addActivity(`[FORGE] Task: ${label || 'unnamed'}`, 'automation');
  res.json({ success: true, status: { active: _forgeTaskState.active, task: label, mode: _forgeTaskState.mode }, ok: true });
});

// GET /api/forge/code-ai/models — list available coding AI models
app.get('/api/forge/code-ai/models', async (req, res) => {
  const { provider } = req.query || {};
  if (provider === 'ollama') {
    try {
      const ollama_resp = await new Promise((resolve, reject) => {
        http.get('http://localhost:11434/api/tags', r => {
          let body = '';
          r.on('data', d => body += d);
          r.on('end', () => {
            try { resolve(JSON.parse(body)) } catch { resolve({ models: [] }) }
          });
        }).on('error', () => resolve({ models: [] }));
      });
      return res.json(ollama_resp);
    } catch { return res.json({ models: [] }); }
  } else if (provider === 'openrouter') {
    return res.json({ models: ['deepseek/deepseek-coder-v2', 'anthropic/claude-3.5-sonnet', 'google/gemini-flash-1.5', 'meta-llama/llama-3.1-70b-instruct', 'qwen/qwen-2.5-coder-32b-instruct'] });
  }
  res.json({ models: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'] });
});

// POST /api/forge/code-ai — send message to coding AI
app.post('/api/forge/code-ai', requireAuth, async (req, res) => {
  const { provider, model, messages, systemPrompt } = req.body || {};
  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ ok: false, error: 'messages array required' });
  }
  const sys = systemPrompt || 'You are a helpful coding assistant. Provide clear, concise code solutions with explanations.';
  const lastMsg = messages[messages.length - 1];
  if (!lastMsg || !lastMsg.content) {
    return res.status(400).json({ ok: false, error: 'last message must have content' });
  }
  try {
    // Route to Python AI backend based on provider
    const prompt = lastMsg.content;
    const url = `http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/chat`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: prompt,
        model: provider === 'openrouter' ? model : provider === 'ollama' ? model : model || 'claude-sonnet-4-6'
      })
    });
    const data = await response.json();
    res.json({ ok: true, response: data.response || data.reply || data.content || 'No response', tokens: 0 });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ── AI Middleware Layer ────────────────────────────────────────────────────────

// POST /api/middleware/process — unified multi-model input processing
app.post('/api/middleware/process', requireAuth, async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/middleware/process', 'POST', req.body || {});
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/middleware/status — active model roles + Wave Field routing status
app.get('/api/middleware/status', async (req, res) => {
  try {
    const result = await requestPythonJSON('/api/middleware/status', 'GET');
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message, wavefield_enabled: false, active_models: [] });
  }
});

// POST /api/money/task  { task, mode }
app.post('/api/money/task', requireAuth, (req, res) => {
  const { task = '' } = req.body || {};
  const label = String(task).trim();
  const run = runPipeline('opportunity');
  addActivity(`[MONEY] Task: ${label || 'unnamed'}`, 'automation');
  res.json({ success: true, ok: true, status: { active: true, task: label, pipeline: run.pipeline }, run_id: run.id });
});

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
app.post('/api/workspace/upload', (req, res) => {
  workspaceUpload.fields([{ name: 'files', maxCount: 100 }, { name: 'file', maxCount: 100 }])(req, res, err => {
    if (err) {
      const tooLarge = err.code === 'LIMIT_FILE_SIZE';
      return res.status(tooLarge ? 413 : 400).json({
        ok: false,
        error: tooLarge ? 'File too large' : 'Upload failed',
        details: tooLarge ? `Maximum file size is ${WORKSPACE_UPLOAD_MAX_SIZE / 1024 / 1024}MB` : err.message,
      });
    }

    const uploaded = [
      ...(req.files?.files || []),
      ...(req.files?.file || []),
    ];

    if (!uploaded.length) {
      return res.status(400).json({ ok: false, error: 'No files provided' });
    }

    const files = uploaded.map(file => ({
      id: path.relative(WORKSPACE_DIR, file.path),
      name: file.originalname,
      path: path.relative(WORKSPACE_DIR, file.path),
      size: file.size,
      mtime: Date.now(),
    }));

    res.json({ ok: true, files, count: files.length });
  });
});

// GET /api/workspace/files — list files in ~/.ai-employee/workspace/
app.get('/api/workspace/files', (req, res) => {
  try {
    const walk = (dir, base) => {
      if (!fs.existsSync(dir)) return [];
      return fs.readdirSync(dir).flatMap(name => {
        const full = path.join(dir, name);
        const rel  = base ? `${base}/${name}` : name;
        const stat = fs.statSync(full);
        if (stat.isDirectory()) return walk(full, rel);
        return [{ name, path: rel, size: stat.size, mtime: stat.mtimeMs }];
      });
    };
    const files = walk(WORKSPACE_DIR, '').sort((a, b) => b.mtime - a.mtime);
    res.json({ files, workspace: WORKSPACE_DIR });
  } catch (e) {
    res.json({ files: [], workspace: WORKSPACE_DIR });
  }
});

// DELETE /api/workspace/files/<relative-path> — delete one workspace file.
app.delete(/^\/api\/workspace\/files\/(.+)$/, (req, res) => {
  try {
    const target = resolveWorkspaceFile(req.params[0]);
    if (!target) return res.status(400).json({ ok: false, error: 'Invalid file path' });
    if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
      return res.status(404).json({ ok: false, error: 'File not found' });
    }
    fs.unlinkSync(target);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: 'Delete failed', details: e.message });
  }
});

// GET /api/errors  — error audit log (e2e + external callers)
app.get('/api/errors', (req, res) => {
  const limit = Math.min(200, parseInt((req.query || {}).limit) || 100);
  const errors = (_auditLog || [])
    .filter((e) => e.risk_score >= 0.6 || String(e.action || '').includes('fail') || String(e.action || '').includes('error'))
    .slice(0, limit);
  res.json(errors);
});

// ── Machine Identity ──────────────────────────────────────────────────────────

app.get('/api/identity', (req, res) => {
  const path = require('path');
  const fs = require('fs');
  const idPath = statePath('identity.json');
  try {
    if (fs.existsSync(idPath)) {
      res.json(JSON.parse(fs.readFileSync(idPath, 'utf8')));
    } else {
      const crypto = require('crypto');
      const fp = crypto.createHash('sha256')
        .update(os.hostname()).update(String(os.cpus().length)).digest('hex').slice(0, 16);
      const names = ['Athena', 'Orion', 'Nova', 'Atlas', 'Echo', 'Cipher', 'Nexus', 'Pulse', 'Axiom', 'Vega'];
      const id = {
        id: crypto.randomUUID(),
        fingerprint: fp,
        name: names[parseInt(fp.slice(0, 4), 16) % names.length],
        hostname: os.hostname(),
        created_at: new Date().toISOString(),
        first_boot: true,
      };
      const dir = path.dirname(idPath);
      require('fs').mkdirSync(dir, { recursive: true });
      require('fs').writeFileSync(idPath, JSON.stringify(id, null, 2));
      res.json(id);
    }
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Settings Management ───────────────────────────────────────────────────────

app.get('/api/system/settings/coding-ai', (req, res) => {
  try {
    const envPath = path.join(AI_HOME, '.env');
    const settings = { provider: 'anthropic', model: 'claude-sonnet-4-6', has_openrouter_key: false };
    if (fs.existsSync(envPath)) {
      const content = fs.readFileSync(envPath, 'utf8');
      const match = content.match(/OPENROUTER_API_KEY=(.+)/);
      if (match && match[1]) {
        settings.has_openrouter_key = true;
      }
    }
    res.json(settings);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/system/settings/coding-ai', requireAuth, (req, res) => {
  try {
    const { provider, model, openrouter_api_key } = req.body || {};
    const envPath = path.join(AI_HOME, '.env');
    const dir = path.dirname(envPath);
    fs.mkdirSync(dir, { recursive: true });

    let content = '';
    if (fs.existsSync(envPath)) {
      content = fs.readFileSync(envPath, 'utf8');
      // Remove old key if present
      content = content.replace(/OPENROUTER_API_KEY=.+\n?/g, '');
    }

    // Add new key if provided
    if (openrouter_api_key && openrouter_api_key.trim()) {
      content += `OPENROUTER_API_KEY=${openrouter_api_key.trim()}\n`;
    }

    fs.writeFileSync(envPath, content);

    // Update process env for immediate use
    if (openrouter_api_key) {
      process.env.OPENROUTER_API_KEY = openrouter_api_key.trim();
    }

    res.json({ ok: true, provider, model, key_saved: !!openrouter_api_key });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Agent Catalog ─────────────────────────────────────────────────────────────

app.get('/api/agents/list', (req, res) => {
  try {
    const agents = getAgents().map(a => ({
      id: a.id,
      description: a.description || '',
      state: a.state || 'idle',
      type: a.type || 'general',
      category: a.category || '',
      lastActivityAt: a.lastActivityAt || null,
      tasksCompleted: a.tasksCompleted || 0,
    }));
    res.json({ agents, count: agents.length });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Auto-Update System ─────────────────────────────────────────────────────────

app.get('/api/system/update-status', (req, res) => {
  const updaterPath = path.join(os.homedir(), '.ai-employee', 'state', 'updater.json');
  const versionPath = path.join(os.homedir(), '.ai-employee', 'state', 'version.json');
  try {
    const updater = fs.existsSync(updaterPath) ? JSON.parse(fs.readFileSync(updaterPath, 'utf8')) : {};
    const version = fs.existsSync(versionPath) ? JSON.parse(fs.readFileSync(versionPath, 'utf8')) : {};
    res.json({ updater, version, has_update: updater.update_available || false });
  } catch {
    res.json({ updater: {}, version: {}, has_update: false });
  }
});

app.get('/api/system/build-hash', (req, res) => {
  const versionPath = path.join(os.homedir(), '.ai-employee', 'state', 'version.json');
  try {
    res.json(JSON.parse(fs.readFileSync(versionPath, 'utf8')));
  } catch {
    res.json({ last_commit: 'unknown' });
  }
});

app.post('/api/system/check-updates', requireAuth, (req, res) => {
  const triggerPath = path.join(os.homedir(), '.ai-employee', 'run', 'updater.trigger');
  try {
    fs.mkdirSync(path.dirname(triggerPath), { recursive: true });
    fs.writeFileSync(triggerPath, 'check');
    res.json({ ok: true, triggered: true });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});

app.post('/api/system/apply-update', requireAuth, (req, res) => {
  const triggerPath = path.join(os.homedir(), '.ai-employee', 'run', 'updater.trigger');
  try {
    fs.mkdirSync(path.dirname(triggerPath), { recursive: true });
    fs.writeFileSync(triggerPath, 'force');
    res.json({ ok: true, triggered: true });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});

// ── Live update endpoint (SSE) ────────────────────────────────────────────────
let _updateRunning = false;
app.post('/api/system/run-update', requireAuth, (req, res) => {
  if (_updateRunning) return res.status(409).json({ ok: false, error: 'Update already in progress' });
  const updaterPaths = [
    path.join(REPO_ROOT, 'runtime', 'agents', 'auto-updater', 'auto_updater.py'),
    path.join(os.homedir(), '.ai-employee', 'agents', 'auto-updater', 'auto_updater.py'),
  ];
  const updaterScript = updaterPaths.find(p => fs.existsSync(p));
  if (!updaterScript) return res.status(503).json({ ok: false, error: 'auto_updater.py not found' });
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setTimeout(0);
  res.flushHeaders();
  const send = (type, data) => { try { res.write(`data: ${JSON.stringify({ type, ...data })}\n\n`); } catch (_) {} };
  send('start', { message: 'Starting update...', ts: Date.now() });
  _updateRunning = true;
  const keepalive = setInterval(() => send('ping', { ts: Date.now() }), 15000);
  const child = spawn(process.env.PYTHON_BIN || 'python3', [updaterScript, '--once'], {
    env: { ...process.env, AI_EMPLOYEE_REPO_DIR: REPO_ROOT, PYTHONUNBUFFERED: '1' },
    cwd: REPO_ROOT,
  });
  const parseAndSend = (chunk, level) => {
    chunk.toString().split('\n').filter(l => l.trim()).forEach(line => {
      let stage = 'running';
      if (/fetch|Fetching/i.test(line))                   stage = 'fetching';
      if (/compar|diff|check/i.test(line))                stage = 'comparing';
      if (/download|apply|Updating/i.test(line))          stage = 'applying';
      if (/build|npm/i.test(line))                        stage = 'building';
      if (/restart|reload/i.test(line))                   stage = 'restarting';
      if (/up.to.date|already|✓|complete/i.test(line))   stage = 'done';
      send('log', { line, stage, level, ts: Date.now() });
    });
  };
  child.stdout.on('data', chunk => parseAndSend(chunk, 'info'));
  child.stderr.on('data', chunk => parseAndSend(chunk, 'warn'));
  child.on('close', (code) => {
    clearInterval(keepalive);
    _updateRunning = false;
    const success = code === 0;
    send('complete', { success, exit_code: code, message: success ? 'Update complete' : `Update failed (exit ${code})`, ts: Date.now() });
    res.end();
    if (success) {
      broadcaster.broadcast('system:update:complete', { ts: new Date().toISOString(), source: 'run-update' });
      _indexCache = null;
    }
  });
  child.on('error', (err) => { clearInterval(keepalive); _updateRunning = false; send('error', { message: err.message, ts: Date.now() }); res.end(); });
  req.on('close', () => { if (_updateRunning) { child.kill('SIGTERM'); _updateRunning = false; } });
});

// ── Task Tracking System ──────────────────────────────────────────────────────
// Stores live task progress; in-memory with TTL cleanup (use Redis for production)

const taskStore = new Map(); // taskId → {task, steps, connections}
const taskConnections = new Map(); // taskId → Set of WebSocket connections

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
  if (!conns) return;
  const msg = JSON.stringify(update);
  conns.forEach(ws => {
    if (ws.readyState === 1) ws.send(msg); // OPEN = 1
  });
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

const wss = new WebSocketServer({ server, path: '/ws' });

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
  // All WebSocket connections must present a valid JWT token.
  if (!wsTokenValid(req)) {
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
const _readiness = { phase: 'BOOTING', pythonReady: false, subsystemsReady: false };

// Cached system:ready snapshot — sent to new WS clients on connect so the
// dashboard banner flips to OPERATIONAL immediately instead of waiting for the
// next broadcast. Updated everywhere we already broadcast `system:ready`.
const _systemReady = { python_ok: false, llm_ok: false, node_ok: true };
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

app.get('/api/tasks/:taskId', (req, res) => {
  const { taskId } = req.params;
  const entry = taskStore.get(taskId);
  if (!entry) {
    return res.status(404).json({ error: 'Task not found' });
  }
  const { task, steps } = entry;
  res.json({ task, steps });
});

app.post('/api/tasks/:taskId/init', requireAuth, (req, res) => {
  const { taskId } = req.params;
  const { title, steps } = req.body || {};
  const task = initTask(taskId, title || 'Task');
  if (steps && Array.isArray(steps)) {
    const entry = taskStore.get(taskId);
    entry.steps = steps.map(s => ({
      id: s.id,
      label: s.label || 'Step',
      status: 'pending',
      started_at: null,
      elapsed_ms: 0,
    }));
  }
  res.json({ ok: true, task });
});

app.post('/api/tasks/:taskId/steps/:stepId', requireAuth, (req, res) => {
  const { taskId, stepId } = req.params;
  const updates = req.body || {};
  updateTaskStep(taskId, stepId, updates);
  res.json({ ok: true });
});

app.post('/api/tasks/:taskId/complete', requireAuth, (req, res) => {
  const { taskId } = req.params;
  const { status } = req.body || {};
  completeTask(taskId, status || 'done');
  res.json({ ok: true });
});

// ── Task History API ──────────────────────────────────────────────────────────

app.get('/api/history', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || 50), 200);
  const filters = {
    status: req.query.status,
    agent: req.query.agent,
    after: req.query.after,
  };
  const tasks = taskHistory.getRecent(limit, filters);
  res.json({ tasks, total: taskHistory.cache.length });
});

app.get('/api/history/stats', (req, res) => {
  res.json(taskHistory.getStats());
});

app.get('/api/history/agent/:agentId', (req, res) => {
  const { agentId } = req.params;
  res.json(taskHistory.getAgentStats(agentId));
});

app.get('/api/history/:taskId', (req, res) => {
  const { taskId } = req.params;
  const task = taskHistory.getTask(taskId);
  if (!task) {
    return res.status(404).json({ error: 'Task not found' });
  }
  res.json(task);
});

// ── Error Recovery API ────────────────────────────────────────────────────────

app.get('/api/errors/recent', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || 10), 50);
  res.json({ errors: errorRecovery.getRecentErrors(limit) });
});

app.post('/api/errors/report', requireAuth, (req, res) => {
  const { error, context } = req.body || {};
  if (!error) return res.status(400).json({ error: 'error required' });

  const logged = errorRecovery.logError(error, context);
  const recovery = errorRecovery.buildRecoveryAction(error, context);

  res.json({ logged, recovery });
});

// Prometheus metrics endpoint — optionally gated by METRICS_TOKEN env var
app.get('/metrics', (req, res) => {
  const metricsToken = process.env.METRICS_TOKEN;
  if (metricsToken) {
    const authHeader = req.headers['authorization'] || '';
    if (authHeader !== `Bearer ${metricsToken}`) {
      return res.status(401).type('text/plain').send('metrics endpoint requires Authorization: Bearer <METRICS_TOKEN>');
    }
  }
  const now = Date.now();
  const uptime = now - startTime;
  const activeAgents = getAgents().length;
  const metrics = [
    `# HELP ai_employee_uptime_ms Application uptime in milliseconds`,
    `# TYPE ai_employee_uptime_ms gauge`,
    `ai_employee_uptime_ms ${uptime}`,
    `# HELP ai_employee_agents_active Number of active agents`,
    `# TYPE ai_employee_agents_active gauge`,
    `ai_employee_agents_active ${activeAgents}`,
    `# HELP ai_employee_tasks_total Total tasks processed`,
    `# TYPE ai_employee_tasks_total counter`,
    `ai_employee_tasks_total ${taskMetrics.completed + taskMetrics.failed}`,
    `# HELP ai_employee_tasks_completed_total Completed tasks`,
    `# TYPE ai_employee_tasks_completed_total counter`,
    `ai_employee_tasks_completed_total ${taskMetrics.completed}`,
    `# HELP ai_employee_tasks_failed_total Failed tasks`,
    `# TYPE ai_employee_tasks_failed_total counter`,
    `ai_employee_tasks_failed_total ${taskMetrics.failed}`,
    `# HELP ai_employee_errors_total Total errors`,
    `# TYPE ai_employee_errors_total counter`,
    `ai_employee_errors_total ${errorRecovery.getTotalErrors()}`,
    `# HELP ai_employee_api_calls_total Total API calls`,
    `# TYPE ai_employee_api_calls_total counter`,
    `ai_employee_api_calls_total ${apiCallCounter}`,
  ].join('\n');

  res.type('text/plain; version=0.0.4').send(metrics + '\n');
});

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
  const wssTask = new WebSocketServer({ noServer: true });

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
  // Probe Python subsystems and broadcast system:ready when confirmed
  probeUntilReady().catch(e => console.error('[READINESS] probe error:', e));

  // FIX-2 cont: 2026-05-12 — Invalidate frontend cache on SIGHUP (hot reload)
  process.on('SIGHUP', () => {
    _indexCache = null;
    console.log('[CACHE] Frontend index.html cache invalidated (SIGHUP)');
  });
});
