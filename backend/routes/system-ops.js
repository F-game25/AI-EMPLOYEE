'use strict';

/**
 * system-ops.js — extracted inline routes from server.js (pure refactor, no behavior changes)
 *
 * Deps injected via createSystemOpsRouter(deps):
 *   requireAuth           — express middleware
 *   validate              — function(schema, req, res) → body | null
 *   SCHEMAS               — zod schema map
 *   getMode, setMode, getRobotSignal, getRunningAgentCount, getAgents
 *   buildMoneyTemplate, buildThinkingSummary
 *   runtimeState          — shared mutable runtime state object
 *   setObjectiveWaiting   — function(system)
 *   runPipeline           — function(pipelineName) → { id, pipeline }
 *   addActivity           — function(notes, kind)
 *   readJsonSafe          — function(file, fallback)
 *   statePath             — function(...parts) → absolute path
 *   requestPythonJSON     — function(pathname, method, payload, options) → Promise
 *   broadcaster           — { broadcast(event, data) }
 *   autoUpdateWatchdog    — { getStatus(), applySettings(patch), triggerManualUpdate() }
 *   _rl_upload            — rate-limit middleware for upload routes
 *   AI_HOME               — string path to ~/.ai-employee
 *   REPO_ROOT             — string path to repo root
 *   promptTraceStore      — Array (shared mutable, passed by reference)
 *   MAX_TRACES            — number
 *   promptInspectorConfig — { enabled, capture_context, capture_output, min_flag_level } (passed by ref wrapper)
 *   WORKSPACE_DIR         — string path to workspace dir
 */

module.exports = function createSystemOpsRouter(deps) {
  const router = require('express').Router();
  const path   = require('path');
  const fs     = require('fs');
  const os     = require('os');
  const { spawn } = require('child_process');

  const {
    requireAuth,
    validate,
    SCHEMAS,
    getMode,
    setMode,
    getRobotSignal,
    getRunningAgentCount,
    getAgents,
    buildMoneyTemplate,
    buildThinkingSummary,
    runtimeState,
    setObjectiveWaiting,
    runPipeline,
    addActivity,
    readJsonSafe,
    statePath,
    requestPythonJSON,
    broadcaster,
    autoUpdateWatchdog,
    _rl_upload,
    AI_HOME,
    REPO_ROOT,
    getPromptTraces, addPromptTrace, clearPromptTraces,
    getPromptInspectorConfig, setPromptInspectorConfig, patchPromptInspectorConfig,
    WORKSPACE_DIR,
  } = deps;

  // ── Mode ──────────────────────────────────────────────────────────────────────

  router.get('/api/mode', requireAuth, (req, res) => {
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

  router.post('/api/mode', requireAuth, (req, res) => {
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

  // ── Research Sessions ─────────────────────────────────────────────────────────

  router.get('/api/research/sessions', requireAuth, (req, res) => {
    const sessions = readJsonSafe(statePath('research_sessions.json'), []);
    const budget   = readJsonSafe(statePath('research_budget.json'), {});
    res.json({ ok: true, sessions: Array.isArray(sessions) ? sessions.slice(-50) : [], budget });
  });

  // ── Prompt Inspector ──────────────────────────────────────────────────────────

  router.get('/api/prompt-traces', requireAuth, (req, res) => {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    res.json({ ok: true, traces: getPromptTraces().slice(0, limit), total: getPromptTraces().length });
  });

  router.get('/api/prompt-trace/:id', requireAuth, (req, res) => {
    const trace = getPromptTraces().find(t => t.id === req.params.id);
    if (!trace) return res.status(404).json({ ok: false, error: 'Trace not found' });
    res.json({ ok: true, trace });
  });

  router.delete('/api/prompt-traces', requireAuth, (req, res) => {
    clearPromptTraces();
    res.json({ ok: true, cleared: true });
  });

  router.get('/api/prompt-inspector/config', requireAuth, (req, res) => {
    res.json({ ok: true, config: getPromptInspectorConfig() });
  });

  router.post('/api/prompt-inspector/config', requireAuth, (req, res) => {
    patchPromptInspectorConfig(req.body || {});
    res.json({ ok: true, config: getPromptInspectorConfig(), inspector_status: getPromptInspectorConfig() });
  });

  router.patch('/api/prompt-inspector/config', requireAuth, (req, res) => {
    patchPromptInspectorConfig(req.body || {});
    res.json({ ok: true, config: getPromptInspectorConfig(), inspector_status: getPromptInspectorConfig() });
  });

  // ── AI Middleware Layer ───────────────────────────────────────────────────────

  router.post('/api/middleware/process', requireAuth, async (req, res) => {
    const _bodyMiddleware = validate(SCHEMAS.middlewareProcess, req, res);
    if (!_bodyMiddleware) return;
    try {
      const result = await requestPythonJSON('/api/middleware/process', 'POST', _bodyMiddleware);
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  router.get('/api/middleware/status', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/api/middleware/status', 'GET');
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: err.message, wavefield_enabled: false, active_models: [] });
    }
  });

  // ── Money Task ────────────────────────────────────────────────────────────────

  router.post('/api/money/task', requireAuth, (req, res) => {
    const _bodyMoneyTask = validate(SCHEMAS.moneyTask, req, res);
    if (!_bodyMoneyTask) return;
    const { task = '' } = _bodyMoneyTask;
    const label = String(task).trim();
    const run = runPipeline('opportunity');
    addActivity(`[MONEY] Task: ${label || 'unnamed'}`, 'automation');
    res.json({ success: true, ok: true, status: { active: true, task: label, pipeline: run.pipeline }, run_id: run.id });
  });

  // ── Workspace ─────────────────────────────────────────────────────────────────

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

  router.post('/api/workspace/upload', requireAuth, _rl_upload, (req, res) => {
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

  router.get('/api/workspace/files', requireAuth, (req, res) => {
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

  router.delete(/^\/api\/workspace\/files\/(.+)$/, requireAuth, (req, res) => {
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

  // ── Settings Management ───────────────────────────────────────────────────────

  router.get('/api/system/settings/coding-ai', requireAuth, (req, res) => {
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

  router.post('/api/system/settings/coding-ai', requireAuth, (req, res) => {
    const _bodyCodingAi = validate(SCHEMAS.codingAiSettings, req, res);
    if (!_bodyCodingAi) return;
    try {
      const { provider, model, openrouter_api_key } = _bodyCodingAi;
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

  // ── Auto-Update System ────────────────────────────────────────────────────────

  router.get('/api/system/update-status', requireAuth, (req, res) => {
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

  router.get('/api/system/build-hash', requireAuth, (req, res) => {
    const versionPath = path.join(os.homedir(), '.ai-employee', 'state', 'version.json');
    try {
      res.json(JSON.parse(fs.readFileSync(versionPath, 'utf8')));
    } catch {
      res.json({ last_commit: 'unknown' });
    }
  });

  router.post('/api/system/check-updates', requireAuth, (req, res) => {
    const triggerPath = path.join(os.homedir(), '.ai-employee', 'run', 'updater.trigger');
    try {
      fs.mkdirSync(path.dirname(triggerPath), { recursive: true });
      fs.writeFileSync(triggerPath, 'check');
      res.json({ ok: true, triggered: true });
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  router.post('/api/system/apply-update', requireAuth, (req, res) => {
    const triggerPath = path.join(os.homedir(), '.ai-employee', 'run', 'updater.trigger');
    try {
      fs.mkdirSync(path.dirname(triggerPath), { recursive: true });
      fs.writeFileSync(triggerPath, 'force');
      res.json({ ok: true, triggered: true });
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // POST /api/system/run-update — live SSE update stream
  let _updateRunning = false;
  router.post('/api/system/run-update', requireAuth, (req, res) => {
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
        // NOTE: _indexCache is owned by server.js; signal invalidation via broadcaster
        broadcaster.broadcast('system:index_cache:invalidate', {});
      }
    });
    child.on('error', (err) => { clearInterval(keepalive); _updateRunning = false; send('error', { message: err.message, ts: Date.now() }); res.end(); });
    req.on('close', () => { if (_updateRunning) { child.kill('SIGTERM'); _updateRunning = false; } });
  });

  // ── Auto-Update Settings + Watchdog Status ────────────────────────────────────

  router.get('/api/system/auto-update-settings', requireAuth, (_req, res) => {
    res.json(autoUpdateWatchdog.getStatus());
  });

  router.patch('/api/system/auto-update-settings', requireAuth, (req, res) => {
    const allowed = ['auto_update_enabled','update_channel','update_interval_minutes',
                     'auto_restart_on_update','watchdog_enabled','watchdog_interval_seconds',
                     'watchdog_max_failures'];
    const patch = {};
    for (const k of allowed) {
      if (req.body[k] !== undefined) patch[k] = req.body[k];
    }
    // Coerce types
    if (patch.update_interval_minutes !== undefined) patch.update_interval_minutes = Math.max(15, parseInt(patch.update_interval_minutes, 10) || 60);
    if (patch.watchdog_interval_seconds !== undefined) patch.watchdog_interval_seconds = Math.max(10, parseInt(patch.watchdog_interval_seconds, 10) || 30);
    if (patch.watchdog_max_failures !== undefined) patch.watchdog_max_failures = Math.max(1, parseInt(patch.watchdog_max_failures, 10) || 3);
    const settings = autoUpdateWatchdog.applySettings(patch);
    broadcaster.broadcast('system:update:settings_changed', { settings });
    res.json({ ok: true, settings });
  });

  router.post('/api/system/trigger-update', requireAuth, (_req, res) => {
    autoUpdateWatchdog.triggerManualUpdate();
    res.json({ ok: true, message: 'Update triggered' });
  });

  router.get('/api/system/watchdog-status', requireAuth, (_req, res) => {
    res.json(autoUpdateWatchdog.getStatus().watchdog);
  });

  return router;
};
