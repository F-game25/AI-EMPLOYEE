'use strict';

const { validateBootPhase } = require('../lib/boot-phase');

// Allowlist of valid event names for POST /internal/events.
// Rejects arbitrary event names to prevent state spoofing via blacklight events.
const _INTERNAL_EVENT_ALLOWLIST = new Set([
  'blacklight:status', 'blacklight:mode_change', 'blacklight:lockdown',
  'task:context_check', 'task:research_started', 'task:research_completed',
  'task:research_budget_exhausted', 'task:update', 'task:done',
  'heartbeat', 'activity:item', 'workflow:update', 'execution:log', 'execution:step',
  'orchestrator:queued', 'memory:router:trace', 'event_stream',
  'objective:update', 'chat:message', 'security:update',
]);

/**
 * createHealthRouter — mounts all health/status/observability/system routes.
 *
 * deps shape:
 *   requireAuth          {function}   Express middleware
 *   requireLocalhost     {function}   Express middleware (unused here but kept for symmetry)
 *   PYTHON_BACKEND_PORT  {string|number}
 *   PYTHON_BACKEND_HOST  {string}
 *   JWT_SECRET           {string}
 *   GIT_COMMIT           {string}
 *   SERVER_START_TIMESTAMP {string}
 *   REPO_ROOT            {string}
 *   HAS_FRONTEND_DIST    {boolean}
 *   STATE_DIR            {string}
 *   ARTIFACTS_DIR        {string}
 *   LOG_DIR              {string}
 *   RUN_DIR              {string}
 *   PORT                 {string|number}
 *   PYTHON_EXEC_SCRIPT   {string}
 *   db                   {object|null}  better-sqlite3 instance (may be falsy)
 *   broadcaster          {object}       has .broadcast(event, data)
 *   runtimeState         {object}
 *   _readiness           {object}       { phase, pythonReady, subsystemsReady }
 *   _systemReady         {object}       { python_ok, llm_ok, node_ok }
 *   _lastBlacklightStatus {object|null} mutable ref — pass as wrapper { get, set }
 *   sampleSystemStatus   {function}
 *   getAgents            {function}
 *   stopAllAgents        {function}  (reason?) => { cancelledTasks, runningAgents } — real halt, broadcasts itself
 *   activateAgents       {function}  (count?) => { desiredActiveAgents, runningAgents } — real un-halt, broadcasts itself
 *   apiGatewayProtector  {object}
 *   securitySyncPolicy   {object}
 *   anomalyResponder     {object}
 *   readJsonSafe         {function}
 *   readJsonlSafe        {function}
 *   statePath            {function}
 *   startTime            {number}       Date.now() at server start (for /metrics)
 *   taskMetrics          {object}       { completed, failed }
 *   apiCallCounter       {object|getter} — pass as wrapper { get() }
 *   errorRecovery        {object}       has .getTotalErrors()
 *   validate             {function}
 *   SCHEMAS              {object}
 *   express              {object}       require('express') — for express.json()
 *   jwt                  {object}       require('jsonwebtoken')
 *   fs                   {object}       require('fs')
 *   path                 {object}       require('path')
 *   execSync             {function}
 */
module.exports = function createHealthRouter(deps) {
  const {
    requireAuth,
    localhostOrAuth,
    PYTHON_BACKEND_PORT,
    PYTHON_BACKEND_HOST,
    JWT_SECRET,
    GIT_COMMIT,
    SERVER_START_TIMESTAMP,
    REPO_ROOT,
    HAS_FRONTEND_DIST,
    STATE_DIR,
    ARTIFACTS_DIR,
    LOG_DIR,
    RUN_DIR,
    PORT,
    PYTHON_EXEC_SCRIPT,
    db,
    broadcaster,
    runtimeState,
    _readiness,
    _systemReady,
    _lastBlacklightStatusRef,  // { get(), set(v) } wrapper so mutation is shared
    sampleSystemStatus,
    getAgents,
    stopAllAgents,
    activateAgents,
    apiGatewayProtector,
    securitySyncPolicy,
    anomalyResponder,
    readJsonSafe,
    readJsonlSafe,
    statePath,
    startTime,
    taskMetrics,
    getApiCallCounter,         // () => number
    errorRecovery,
    validate,
    SCHEMAS,
    express,
    jwt,
    fs,
    path,
    execSync,
  } = deps;

  const router = require('express').Router();

  // ── Helper: probe an HTTP URL with a timeout ──────────────────────────────────
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

  // ── Helper: capability record factory ────────────────────────────────────────
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

  // ── Helper: system process list ───────────────────────────────────────────────
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

  // ── Helper: observability snapshot ───────────────────────────────────────────
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

  // ── Halt/restart state (must be shared with server.js if it's also used elsewhere)
  // This is declared in server.js as `let systemHalted = false;` — deps must pass it
  // as a ref wrapper so the value is shared.
  // We accept it as systemHaltedRef = { get(), set(v) } or use deps.systemHalted directly.
  // Because server.js declares it at module scope and reads/writes it inline, we require
  // the caller to pass { getSystemHalted, setSystemHalted }.
  const { getSystemHalted, setSystemHalted } = deps;

  // _srvStartMs for /api/system/uptime
  const _srvStartMs = deps._srvStartMs;

  // ─────────────────────────────────────────────────────────────────────────────
  // Routes
  // ─────────────────────────────────────────────────────────────────────────────

  // GET /health — FAST health check for boot polling (no external calls)
  // Returns immediately with Node.js uptime and status.
  router.get('/health', (req, res) => {
    res.status(200).json({
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
    });
  });

  // GET /health/full — detailed health check (external calls, slow)
  // Called by dashboard, not by boot scripts. Includes all subsystem checks.
  router.get('/health/full', requireAuth, async (req, res) => {
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
  // Uses req.socket.remoteAddress (not req.ip) — trust proxy: 1 makes req.ip
  // X-Forwarded-For-aware and therefore spoofable by external callers.
  const _express = (typeof express === 'object' && express?.json) ? express : require('express');
  router.post('/internal/events', _express.json({ limit: '2mb' }), (req, res) => {
    const rawIp = req.socket?.remoteAddress || req.connection?.remoteAddress || '';
    const isLocal = rawIp === '127.0.0.1' || rawIp === '::1' || rawIp === '::ffff:127.0.0.1';
    if (!isLocal) return res.status(403).json({ ok: false, error: 'localhost only' });
    const { event, data } = req.body || {};
    if (typeof event !== 'string' || !event) {
      return res.status(400).json({ ok: false, error: 'event required' });
    }
    if (event.length > 120) {
      return res.status(400).json({ ok: false, error: 'event name too long' });
    }
    if (!_INTERNAL_EVENT_ALLOWLIST.has(event)) {
      return res.status(400).json({ ok: false, error: 'unknown event type' });
    }
    try {
      broadcaster.broadcast(event, data || {});
      // Blacklight events get priority broadcast with structured payload
      if (event === 'blacklight:status' || event === 'blacklight:mode_change' || event === 'blacklight:lockdown') {
        broadcaster.broadcast('security:update', { event, ...data });
        if (data && typeof data.threat_score === 'number') {
          _lastBlacklightStatusRef.set({ ...data, updated_at: Date.now() });
        }
      }
      return res.json({ ok: true });
    } catch (e) {
      return res.status(500).json({ ok: false, error: String(e && e.message || e) });
    }
  });

  // GET /version
  router.get('/version', (req, res) => {
    res.set('Cache-Control', 'no-store, must-revalidate');
    // Authenticated callers get full version details; unauthenticated get minimal response.
    // This prevents enumeration of git commit hashes and server start timestamps by attackers.
    const isAuthed = (() => {
      try {
        const authHeader = req.headers.authorization || '';
        if (!authHeader.startsWith('Bearer ')) return false;
        jwt.verify(authHeader.slice(7), JWT_SECRET, { algorithms: ['HS256'] });
        return true;
      } catch (_) { return false; }
    })();
    if (!isAuthed) {
      return res.json({ ok: true });
    }
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
      version_state: versionState,
    });
  });

  // GET /status
  router.get('/status', requireAuth, (req, res) => {
    const stats = sampleSystemStatus();
    res.json({ status: 'online', agents: stats.total_agents, running_agents: stats.running_agents, timestamp: stats.timestamp });
  });

  // GET /api/status — alias for /status
  router.get('/api/status', requireAuth, (req, res) => {
    const stats = sampleSystemStatus();
    res.json({ status: 'online', agents: stats.total_agents, running_agents: stats.running_agents, timestamp: stats.timestamp });
  });

  // GET /api/health
  router.get('/api/health', requireAuth, (req, res) => {
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

  // GET /api/readiness
  router.get('/api/readiness', async (req, res) => {
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
    const graphProbe = await deps.checkNeuralGraphReady();
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
      uiBootPhase: _readiness.uiBootPhase,
      degraded: degradedReasons.length > 0,
      degradedReasons,
      timestamp: new Date().toISOString(),
    });
  });

  // ── Desktop boot handshake (F2) ────────────────────────────────────────────
  // The frontend reports UI boot phases here so the shell knows the UI actually
  // mounted — works under Tauri's remote-origin webview, which has no Electron
  // preload bridge. Tokenless from loopback (phases fire before any operator token
  // exists); JWT required for remote callers. Body is validated as hostile input.
  const _localOrAuth = (typeof localhostOrAuth === 'function') ? localhostOrAuth : requireAuth;
  router.post('/api/boot/phase', _localOrAuth, _express.json({ limit: '8kb' }), (req, res) => {
    const result = validateBootPhase(req.body);
    if (!result.ok) return res.status(400).json({ ok: false, error: result.error });
    _readiness.uiBootPhase = { ...result.value, ts: new Date().toISOString() };
    try {
      console.log(`[boot] ui phase: ${result.value.phase}${result.value.detail ? ' - ' + result.value.detail : ''}`);
    } catch (_) { /* logging is best-effort */ }
    res.json({ ok: true });
  });

  router.get('/api/boot/phase', _localOrAuth, (_req, res) => {
    res.set('Cache-Control', 'no-store');
    res.json({ ok: true, uiBootPhase: _readiness.uiBootPhase });
  });

  // GET /api/capabilities/status
  router.get('/api/capabilities/status', requireAuth, async (_req, res) => {
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
    const fishSpeechHost = process.env.FISH_SPEECH_URL || process.env.FISH_AUDIO_S2_URL || 'http://127.0.0.1:8080';
    const fishSpeechProbe = await probeHttp(`${String(fishSpeechHost).replace(/\/$/, '')}/v1/health`);
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
        id: 'fish_speech_s2_local_voice',
        label: 'Fish Speech S2 Local Voice',
        status: fishSpeechProbe.ok ? 'live' : 'not_configured',
        category: 'execution',
        required_env: ['FISH_SPEECH_URL'],
        missing_env: process.env.FISH_SPEECH_URL || process.env.FISH_AUDIO_S2_URL ? [] : ['FISH_SPEECH_URL'],
        setup_action: fishSpeechProbe.ok ? 'test' : 'start_service',
        details: fishSpeechProbe.ok
          ? `Fish Speech responded at ${fishSpeechHost}.`
          : `No Fish Speech response from ${fishSpeechHost}; voice falls back to local OS TTS if available.`,
        docs_hint: 'Run Fish Speech S2 locally on port 8080 to replace robotic OS speech with a natural system-owned voice.',
        proof: { host: fishSpeechHost, probe: fishSpeechProbe },
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

  // GET /api/observability/snapshot
  router.get('/api/observability/snapshot', requireAuth, (req, res) => {
    res.json(buildObservabilitySnapshot());
  });

  // GET /api/observability/events
  router.get('/api/observability/events', requireAuth, (req, res) => {
    res.json({ events: (runtimeState.observability.events || []).slice(0, 200) });
  });

  // GET /api/system/stats
  router.get('/api/system/stats', requireAuth, (req, res) => {
    const stats = sampleSystemStatus();
    // Expose cpu_percent as canonical field (alias of cpu_usage) for test/e2e compatibility
    res.json({ ...stats, cpu_percent: stats.cpu_usage ?? stats.cpu ?? 0 });
  });

  // GET /api/system/processes
  router.get('/api/system/processes', requireAuth, (_req, res) => {
    res.json({ ok: true, generated_at: new Date().toISOString(), processes: parsePsRows() });
  });

  // GET /api/system/ports
  router.get('/api/system/ports', requireAuth, (_req, res) => {
    res.json({ ok: true, generated_at: new Date().toISOString(), ports: parseListeningPorts() });
  });

  // GET /api/system/storage
  router.get('/api/system/storage', requireAuth, (_req, res) => {
    res.json({ ok: true, generated_at: new Date().toISOString(), storage: storageRows() });
  });

  // GET /api/system/runtime-warnings
  router.get('/api/system/runtime-warnings', requireAuth, (_req, res) => {
    const warnings = runtimeWarnings();
    res.json({ ok: true, generated_at: new Date().toISOString(), status: warnings.length ? 'degraded' : 'live', warnings });
  });

  // GET /api/system/services
  router.get('/api/system/services', requireAuth, (_req, res) => {
    const ports = parseListeningPorts();
    const portStatus = (port) => ports.some((row) => row.port === Number(port) && row.status === 'listening');
    const warnings = runtimeWarnings();
    res.json({
      ok: true,
      generated_at: new Date().toISOString(),
      services: [
        { id: 'node_backend', name: 'Node Backend', status: portStatus(PORT) ? 'live' : 'degraded', port: Number(PORT), uptime: process.uptime(), restart_available: false, log_link: null },
        { id: 'python_backend', name: 'Python Backend', status: _readiness.pythonReady || portStatus(PYTHON_BACKEND_PORT) ? 'live' : 'unavailable', port: Number(PYTHON_BACKEND_PORT), uptime: null, restart_available: false, log_link: null },
        { id: 'frontend_build', name: 'Frontend Build', status: HAS_FRONTEND_DIST ? 'live' : 'not_configured', port: null, uptime: null, restart_available: false, log_link: null },
        { id: 'runtime_warnings', name: 'Runtime Warnings', status: warnings.length ? 'degraded' : 'live', port: null, uptime: null, restart_available: false, last_error: warnings[0]?.details || null },
      ],
    });
  });

  // POST /api/system/halt
  router.post('/api/system/halt', requireAuth, (req, res) => {
    validate(SCHEMAS.systemHalt, req, res); // optional body, validation is a no-op if body absent
    setSystemHalted(true);
    // stopAllAgents cancels in-flight/queued tasks, parks every real agent at
    // idle/offline, and broadcasts 'agents:list' itself (wired via
    // onAgentEvent('agent:update', ...) in server.js) — no separate broadcast needed.
    stopAllAgents('system_halt');
    broadcaster.broadcast('system:halted', { halted: true, at: new Date().toISOString() });
    res.json({ ok: true, halted: true, at: new Date().toISOString() });
  });

  // POST /api/system/restart
  router.post('/api/system/restart', requireAuth, (req, res) => {
    setSystemHalted(false);
    // Bring agents back from the halt's idle/offline park back to running/healthy.
    // activateAgents also broadcasts 'agents:list' itself, same wiring as above.
    activateAgents();
    broadcaster.broadcast('system:halted', { halted: false, at: new Date().toISOString() });
    res.json({ ok: true, halted: false, at: new Date().toISOString() });
  });

  // GET /api/system/halt
  router.get('/api/system/halt', requireAuth, (req, res) => {
    res.json({ ok: true, halted: getSystemHalted() });
  });

  // GET /api/system/uptime
  router.get('/api/system/uptime', requireAuth, (req, res) => {
    const ms = Date.now() - _srvStartMs;
    const s  = Math.floor(ms / 1000);
    res.json({
      ok: true,
      status: 'partial',
      source: 'node_process',
      uptime_ms: ms,
      uptime_human: `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m ${s%60}s`,
      started_at: new Date(_srvStartMs).toISOString(),
      pid: process.pid,
      node_version: process.version,
      services: [{
        name: 'backend',
        uptime_30d: null,
        uptime_90d: null,
        incidents_30d: null,
        mttr_minutes: null,
        status: 'live',
        uptime_seconds: s,
        source: 'node_process',
      }],
      details: 'Historical uptime percentages require persisted service checks; unavailable fields are null.',
    });
  });

  // GET /api/system/sla
  router.get('/api/system/sla', requireAuth, (req, res) => {
    try {
      const tasks = readJsonSafe(statePath('tasks.json'), []);
      const llmCalls = readJsonlSafe(statePath('llm_calls.jsonl'), 2000);
      const cutoff = Date.now() - 86400000;
      const recent = (Array.isArray(tasks) ? tasks : []).filter(t => new Date(t.created_at || t.timestamp || 0).getTime() > cutoff);
      const failed = recent.filter(t => t.status === 'failed' || t.status === 'error').length;
      const total  = recent.length;
      const recentCalls = llmCalls.filter(c => new Date(c.timestamp || c.ts || c.created_at || 0).getTime() > cutoff);
      const latencies = recentCalls.map(c => Number(c.duration_ms || c.latency_ms || 0)).filter(Boolean).sort((a, b) => a - b);
      const failedCalls = recentCalls.filter(c => c.ok === false || c.status === 'error').length;
      const successRate = total ? parseFloat(((total - failed) / total * 100).toFixed(1)) : null;
      res.json({
        ok: true,
        status: total || recentCalls.length ? 'live' : 'unavailable',
        source: total || recentCalls.length ? 'task_and_llm_call_logs' : 'no_recent_telemetry',
        success_rate: successRate,
        total_tasks: total,
        failed_tasks: failed,
        window: '24h',
        targets: { p99_9: 99.9, p99_5: 99.5 },
        current: {
          uptime: successRate,
          p95_latency_ms: latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : null,
          error_rate_pct: recentCalls.length ? parseFloat((failedCalls / recentCalls.length * 100).toFixed(2)) : null,
        },
        totals: { tasks_24h: total, failed_tasks_24h: failed, llm_calls_24h: recentCalls.length, failed_llm_calls_24h: failedCalls },
      });
    } catch {
      res.json({ ok: true, status: 'unavailable', source: 'error', success_rate: null, total_tasks: 0, failed_tasks: 0, window: '24h', current: { uptime: null, p95_latency_ms: null, error_rate_pct: null } });
    }
  });

  // GET /api/system/patches
  router.get('/api/system/patches', requireAuth, (req, res) => {
    const patches = readJsonSafe(statePath('patches.json'), []);
    res.json({ ok: true, patches: Array.isArray(patches) ? patches : [], count: Array.isArray(patches) ? patches.length : 0 });
  });

  // GET /metrics — Prometheus metrics endpoint, optionally gated by METRICS_TOKEN env var
  router.get('/metrics', (req, res) => {
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
    let metrics = [
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
      `ai_employee_api_calls_total ${getApiCallCounter()}`,
    ].join('\n');

    // QCE metrics — read from quantum_feedback.jsonl
    try {
      const feedbackPath = path.join(STATE_DIR, 'quantum_feedback.jsonl');
      const lines = fs.existsSync(feedbackPath)
        ? fs.readFileSync(feedbackPath, 'utf8').trim().split('\n').filter(Boolean)
        : [];
      const records = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
      const total = records.length;
      const success = records.filter(r => r.outcome === 'success').length;
      const failure = records.filter(r => r.outcome === 'failure').length;
      const confidences = records.map(r => r.confidence).filter(v => typeof v === 'number');
      const avgConf = confidences.length ? (confidences.reduce((a, b) => a + b, 0) / confidences.length).toFixed(4) : 0;
      metrics += `\n# HELP qce_reflections_total Total QCE reflection events\n`;
      metrics += `# TYPE qce_reflections_total counter\n`;
      metrics += `qce_reflections_total ${total}\n`;
      metrics += `qce_reflections_success_total ${success}\n`;
      metrics += `qce_reflections_failure_total ${failure}\n`;
      metrics += `qce_avg_confidence ${avgConf}\n`;
    } catch {}

    res.type('text/plain; version=0.0.4').send(metrics + '\n');
  });

  return router;
};
