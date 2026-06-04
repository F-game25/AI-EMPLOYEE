'use strict';
/**
 * Artifacts, preview, proof center, demo, task tracking, task history,
 * legacy forge status/task/code-ai, and model-fabric per-model routes.
 *
 * All handlers are pure extractions from server.js — zero behavior changes.
 *
 * deps: {
 *   requireAuth,          // Express middleware
 *   path,                 // node:path (already required by server.js)
 *   fs,                   // node:fs
 *   http,                 // node:http  (for Ollama proxy in /forge/code-ai/models)
 *   AI_HOME,              // string — resolved home dir for .ai-employee
 *   ARTIFACTS_DIR,        // string — path.join(__dirname, '..', '..', 'state', 'artifacts')
 *   statePath,            // (...parts) => path.join(STATE_DIR, ...parts)
 *   readJsonLinesRecent,  // (filePath, limit?) => array
 *   validate,             // (schema, req, res) => body | null
 *   SCHEMAS,              // zod schema map
 *   PYTHON_BACKEND_HOST,  // string  '127.0.0.1'
 *   PYTHON_BACKEND_PORT,  // string | number
 *   proxyModelFabric,     // async (path, opts?) => { ok, data }
 *   MODEL_FABRIC_OFFLINE, // object
 *   reliabilityState,     // { forgeFrozen, stabilityScore, ... }
 *   _forgeQueue,          // array — in-memory forge queue
 *   addActivity,          // (notes, kind?) => void
 *   runPipeline,          // (pipelineName) => { id, pipeline }
 *   taskStore,            // Map  taskId → {task, steps}
 *   initTask,             // (taskId, title?) => task
 *   updateTaskStep,       // (taskId, stepId, updates) => void
 *   completeTask,         // (taskId, status?) => void
 *   taskHistory,          // TaskHistoryManager instance
 *   _sseTaskListeners,    // Map  taskId → Set<res>
 * }
 */

const express = require('express');

module.exports = function createArtifactsTasksRouter(deps) {
  const {
    requireAuth,
    path,
    fs,
    http,
    AI_HOME,
    ARTIFACTS_DIR,
    statePath,
    readJsonLinesRecent,
    validate,
    SCHEMAS,
    PYTHON_BACKEND_HOST,
    PYTHON_BACKEND_PORT,
    proxyModelFabric,
    MODEL_FABRIC_OFFLINE,
    reliabilityState,
    addActivity,
    runPipeline,
    taskHistory,
  } = deps;

  // Late-declared deps — accessed via getters to avoid TDZ at factory time
  const getForgeQueue       = () => deps._forgeQueue;
  const getTaskStore        = () => deps.getTaskStore ? deps.getTaskStore() : deps.taskStore;
  const getSseListeners     = () => deps.getSseTaskListeners ? deps.getSseTaskListeners() : deps._sseTaskListeners;
  const getInitTask         = () => deps.initTask;
  const getUpdateTaskStep   = () => deps.updateTaskStep;
  const getCompleteTask     = () => deps.completeTask;

  const router = express.Router();

  // ── Artifacts ──────────────────────────────────────────────────────────────

  // GET /api/artifacts/:filename — download a generated artifact (auth required)
  router.get('/artifacts/:filename', requireAuth, (req, res) => {
    const fname = path.basename(req.params.filename); // prevent path traversal
    const fpath = path.join(ARTIFACTS_DIR, fname);
    if (!require('fs').existsSync(fpath)) return res.status(404).json({ error: 'Artifact not found' });
    res.download(fpath);
  });

  // GET /api/preview/:filename — serve HTML artifact inline; auth via query token or header
  router.get('/preview/:filename', (req, res) => {
    const fname = path.basename(req.params.filename);
    if (!fname.endsWith('.html')) return res.status(400).send('Only HTML files can be previewed');
    const fpath = path.join(ARTIFACTS_DIR, fname);
    if (!fs.existsSync(fpath)) return res.status(404).send('Preview not found');
    // Validate JWT from query param (iframes cannot send Authorization headers)
    const token = req.query.token;
    if (token) {
      try {
        const jwt = require('jsonwebtoken');
        jwt.verify(token, process.env.JWT_SECRET_KEY || '');
      } catch {
        return res.status(401).send('Unauthorized');
      }
    } else {
      // Fall back to cookie-based auth check via requireAuth pattern
      const authHeader = req.headers.authorization;
      if (!authHeader) return res.status(401).send('Unauthorized');
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');
    res.send(fs.readFileSync(fpath, 'utf8'));
  });

  // GET /api/artifacts — list all artifact files
  router.get('/artifacts', requireAuth, (_req, res) => {
    const fs = require('fs');
    if (!fs.existsSync(ARTIFACTS_DIR)) return res.json([]);
    const files = fs.readdirSync(ARTIFACTS_DIR)
      .filter(f => fs.statSync(path.join(ARTIFACTS_DIR, f)).isFile())
      .map(f => ({ name: f, url: `/api/artifacts/${f}`, size: fs.statSync(path.join(ARTIFACTS_DIR, f)).size }));
    res.json(files);
  });

  // ── Proof center ───────────────────────────────────────────────────────────

  // GET /api/proof/center — aggregate turns + artifacts into a proof dashboard payload
  router.get('/proof/center', requireAuth, (_req, res) => {
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

  // ── Demos ──────────────────────────────────────────────────────────────────

  // NOTE: /api/demos/:filename (demo serving) lives canonically in routes/media.js.
  // The duplicate that used to be here was removed to avoid a double route registration.

  // ── Legacy forge (status / task / code-ai) ─────────────────────────────────
  // Note: canonical /api/forge/* routes are served by routes/forge.js which is
  // mounted first. These legacy aliases are preserved for older UI flows.

  const _forgeTaskState = { last_action: null, active: false, mode: 'active' };

  // GET /api/forge/status
  router.get('/forge/status', requireAuth, (_req, res) => {
    res.json({
      mode: reliabilityState.forgeFrozen ? 'frozen' : _forgeTaskState.mode,
      active: _forgeTaskState.active,
      last_action: _forgeTaskState.last_action,
      frozen: reliabilityState.forgeFrozen,
      queue_depth: getForgeQueue().length,
      stability_score: reliabilityState.stabilityScore,
    });
  });

  // POST /api/forge/task  { task, mode }
  router.post('/forge/task', requireAuth, (req, res) => {
    const _bodyForgeTask = validate(SCHEMAS.forgeTask, req, res);
    if (!_bodyForgeTask) return;
    const { task = '', mode = 'on' } = _bodyForgeTask;
    const label = String(task).trim();
    if (label) _forgeTaskState.last_action = label;
    _forgeTaskState.active = mode !== 'off';
    addActivity(`[FORGE] Task: ${label || 'unnamed'}`, 'automation');
    res.json({ success: true, status: { active: _forgeTaskState.active, task: label, mode: _forgeTaskState.mode }, ok: true });
  });

  // GET /api/forge/code-ai/models — list available coding AI models
  router.get('/forge/code-ai/models', requireAuth, async (req, res) => {
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
  router.post('/forge/code-ai', requireAuth, async (req, res) => {
    const _bodyCodeAi = validate(SCHEMAS.forgeCodeAi, req, res);
    if (!_bodyCodeAi) return;
    const { provider, model, messages, systemPrompt } = _bodyCodeAi;
    const sys = systemPrompt || 'You are a helpful coding assistant. Provide clear, concise code solutions with explanations.';
    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || !lastMsg.content) {
      return res.status(400).json({ ok: false, error: 'last message must have content' });
    }
    try {
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

  // ── Model-fabric per-model routes (regex paths) ────────────────────────────

  // POST /api/model-fabric/models/<id>/unload  (id may contain slashes/colons)
  router.post(/^\/model-fabric\/models\/(.+)\/unload$/, requireAuth, async (req, res) => {
    try {
      const id = encodeURIComponent(req.params[0]);
      const { ok, data } = await proxyModelFabric(`/api/model-fabric/models/${id}/unload`, { method: 'POST', body: req.body });
      return res.status(ok ? 200 : 502).json(data);
    } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
  });

  // POST /api/model-fabric/models/<id>/reload-with-quant
  router.post(/^\/model-fabric\/models\/(.+)\/reload-with-quant$/, requireAuth, async (req, res) => {
    try {
      const id = encodeURIComponent(req.params[0]);
      const { ok, data } = await proxyModelFabric(`/api/model-fabric/models/${id}/reload-with-quant`, { method: 'POST', body: req.body });
      return res.status(ok ? 200 : 502).json(data);
    } catch (_) { return res.status(503).json(MODEL_FABRIC_OFFLINE); }
  });

  // ── Task progress (SSE) + task CRUD ───────────────────────────────────────
  // /progress must be declared before /:taskId so Express matches first-wins.

  // GET /api/tasks/:taskId/progress — SSE stream for live task progress
  router.get('/tasks/:taskId/progress', requireAuth, (req, res) => {
    const { taskId } = req.params;
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // disable nginx buffering if present
    res.flushHeaders();

    if (!getSseListeners().has(taskId)) getSseListeners().set(taskId, new Set());
    getSseListeners().get(taskId).add(res);

    // Send current state immediately as snapshot
    const entry = getTaskStore().get(taskId);
    if (entry) {
      res.write(`data: ${JSON.stringify({ type: 'snapshot', taskId, task: entry.task, steps: entry.steps })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({ type: 'connected', taskId })}\n\n`);
    }

    req.on('close', () => {
      const set = getSseListeners().get(taskId);
      if (set) { set.delete(res); if (set.size === 0) getSseListeners().delete(taskId); }
    });
  });

  // GET /api/tasks/:taskId
  router.get('/tasks/:taskId', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const entry = getTaskStore().get(taskId);
    if (!entry) return res.status(404).json({ error: 'Task not found' });
    const { task, steps } = entry;
    res.json({ task, steps });
  });

  // POST /api/tasks/:taskId/init
  router.post('/tasks/:taskId/init', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const { title, steps } = req.body || {};
    const task = getInitTask()(taskId, title || 'Task');
    if (steps && Array.isArray(steps)) {
      const entry = getTaskStore().get(taskId);
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

  // POST /api/tasks/:taskId/steps/:stepId
  router.post('/tasks/:taskId/steps/:stepId', requireAuth, (req, res) => {
    const { taskId, stepId } = req.params;
    const updates = req.body || {};
    getUpdateTaskStep()(taskId, stepId, updates);
    res.json({ ok: true });
  });

  // POST /api/tasks/:taskId/complete
  router.post('/tasks/:taskId/complete', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const { status } = req.body || {};
    getCompleteTask()(taskId, status || 'done');
    res.json({ ok: true });
  });

  // ── Task history ───────────────────────────────────────────────────────────

  // GET /api/history
  router.get('/history', requireAuth, (req, res) => {
    const limit = Math.min(parseInt(req.query.limit || 50), 200);
    const filters = {
      status: req.query.status,
      agent: req.query.agent,
      after: req.query.after,
    };
    const tasks = taskHistory.getRecent(limit, filters);
    res.json({ tasks, total: taskHistory.cache.length });
  });

  // GET /api/history/stats
  router.get('/history/stats', requireAuth, (req, res) => {
    res.json(taskHistory.getStats());
  });

  // GET /api/history/agent/:agentId
  router.get('/history/agent/:agentId', requireAuth, (req, res) => {
    const { agentId } = req.params;
    res.json(taskHistory.getAgentStats(agentId));
  });

  // GET /api/history/:taskId  — must be last among /history/* routes
  router.get('/history/:taskId', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const task = taskHistory.getTask(taskId);
    if (!task) return res.status(404).json({ error: 'Task not found' });
    res.json(task);
  });

  return router;
};
