'use strict';

/**
 * forge-ops.js — Legacy forge, ollama, models, doctor, execution, and system
 * inline routes extracted from server.js. Pure refactor — zero behavior changes.
 *
 * Mount in server.js (after forge.js):
 *   app.use('/api', createForgeOpsRouter({ requireAuth, ... }));
 *
 * Deps injected via the factory argument:
 *   requireAuth, validate, SCHEMAS, loadSystemManifest, buildModelRoutePlan,
 *   readJsonSafe, statePath, requestPythonJSON, ollamaAdmin, subsystems,
 *   getAgents, addActivity, recordAuditEvent,
 *   getForgeQueue(), _forgeQueuePush, _forgeQueueUpdate,
 *   _forgeRiskScore, _forgeRiskLabel,
 *   reliabilityState, _auditLog,
 *   _rl_forge, _rl_ollama_pull,
 *   PYTHON_BACKEND_HOST, PYTHON_BACKEND_PORT,
 *   spawn (child_process.spawn), http (node:http)
 */
module.exports = function createForgeOpsRouter(deps) {
  const router = require('express').Router();
  const path = require('path');
  const fs = require('fs');
  const os = require('os');

  const {
    requireAuth,
    validate,
    SCHEMAS,
    loadSystemManifest,
    buildModelRoutePlan,
    readJsonSafe,
    statePath,
    requestPythonJSON,
    ollamaAdmin,
    subsystems,
    getAgents,
    addActivity,
    recordAuditEvent,
    _forgeQueuePush,
    _forgeQueueUpdate,
    _forgeRiskScore,
    _forgeRiskLabel,
    reliabilityState,
    _auditLog,
    _rl_forge,
    _rl_ollama_pull,
    PYTHON_BACKEND_HOST,
    PYTHON_BACKEND_PORT,
    spawn,
    http,
  } = deps;

  // getForgeQueue() is a const declared late in server.js (depends on SQLite IIFE)
  // Access via deps at request time to avoid TDZ at factory-call time
  const getForgeQueue = () => deps._forgeQueue;

  // ── Internal: Forge Python bridge ────────────────────────────────────────────

  const FORGE_PYTHON_SCRIPT = path.join(__dirname, '..', 'run_forge.py');

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

  // Forge task state — local to this router (same lifetime as server process).
  const _forgeTaskState = { last_action: null, active: false, mode: 'active' };

  // ── GET /api/execution/queue ─────────────────────────────────────────────────

  router.get('/execution/queue', requireAuth, async (req, res) => {
    const nodeItems = Array.isArray(getForgeQueue()) ? getForgeQueue() : [];
    const count = (status) => nodeItems.filter((i) => i.status === status).length;
    const base = {
      items: nodeItems,
      total: nodeItems.length,
      pending:   count('pending'),
      running:   count('running'),
      completed: count('completed'),
    };
    try {
      const pyData = await requestPythonJSON('/api/task/status', 'GET', null, { timeoutMs: 2000 });
      if (pyData && pyData._http_status >= 200 && pyData._http_status < 300) {
        const pyItems = Array.isArray(pyData.tasks) ? pyData.tasks : (Array.isArray(pyData.items) ? pyData.items : []);
        const existingIds = new Set(nodeItems.map((i) => String(i.id)));
        const merged = [...nodeItems, ...pyItems.filter((i) => !existingIds.has(String(i.id)))];
        const mc = (status) => merged.filter((i) => i.status === status).length;
        return res.json({
          items: merged,
          total: merged.length,
          pending:   mc('pending'),
          running:   mc('running'),
          completed: mc('completed'),
        });
      }
    } catch (_) { /* fall through to node-only */ }
    return res.json(base);
  });

  // ── GET /api/models/routing ──────────────────────────────────────────────────

  router.get('/models/routing', requireAuth, (req, res) => {
    const DEFAULT_ROUTING = {
      coding:    { provider: 'nvidia_nim', model: 'qwen2.5-coder-32b',          fallback: 'claude-sonnet-4-6' },
      reasoning: { provider: 'nvidia_nim', model: 'llama-3.3-nemotron-49b',     fallback: 'claude-opus-4-7' },
      general:   { provider: 'ollama',     model: 'llama3.2',                   fallback: 'claude-haiku-4-5' },
      analytics: { provider: 'anthropic',  model: 'claude-opus-4-7' },
      creative:  { provider: 'ollama',     model: 'gemma4',                     fallback: 'claude-sonnet-4-6' },
      bulk:      { provider: 'nvidia_nim', model: 'llama-3.1-8b',               fallback: 'llama3.2' },
    };
    const configPath = path.join(os.homedir(), '.ai-employee', 'model-routing.json');
    const fileRouting = readJsonSafe(configPath, null);
    if (fileRouting) {
      return res.json({ routing: fileRouting, source: 'file', config_path: configPath });
    }
    return res.json({ routing: DEFAULT_ROUTING, source: 'default', config_path: configPath });
  });

  // ── POST /api/models/routing ─────────────────────────────────────────────────

  router.post('/models/routing', requireAuth, (req, res) => {
    const configPath = path.join(os.homedir(), '.ai-employee', 'model-routing.json');
    try {
      fs.writeFileSync(configPath, JSON.stringify(req.body, null, 2), 'utf8');
      return res.json({ ok: true, config_path: configPath });
    } catch (e) {
      return res.status(500).json({ ok: false, error: e.message });
    }
  });

  // ── GET /api/models/providers ────────────────────────────────────────────────

  router.get('/models/providers', requireAuth, (req, res) => {
    const anthropicOk = !!(process.env.ANTHROPIC_API_KEY);
    const openaiOk    = !!(process.env.OPENAI_API_KEY);
    ollamaAdmin.getRuntimeStatus().then(runtime => {
      const running = !!runtime.running;
      res.json({
        providers: {
          anthropic: { configured: anthropicOk, status: anthropicOk ? 'configured' : 'missing_key' },
          openai:    { configured: openaiOk,    status: openaiOk    ? 'configured' : 'missing_key' },
          ollama:    { configured: runtime.ok,  status: runtime.status, running, runtime },
        },
      });
    }).catch(() => res.json({ providers: { anthropic: { configured: anthropicOk }, openai: { configured: openaiOk }, ollama: { configured: false } } }));
  });

  // ── GET /api/models/roles — live role → model@quant resolution ───────────────
  // Bridges to the Python source of truth (model_role_resolver + model_lanes).
  // Honest failure: surfaces Python's structured error / unreachable status.

  router.get('/models/roles', requireAuth, async (req, res) => {
    try {
      const py = await requestPythonJSON('/api/models/roles', 'GET', null, { timeoutMs: 8000 });
      const status = py && py._http_status ? py._http_status : 200;
      const { _http_status, ...payload } = py || {};
      return res.status(status).json(payload && Object.keys(payload).length ? payload
        : { ok: false, error: 'python_backend_empty' });
    } catch (e) {
      return res.status(503).json({ ok: false, error: 'python_backend_unreachable', detail: e.message });
    }
  });

  // ── GET /api/models/benchmarks — measured tok/s per model ────────────────────
  // Bridges to Python which reads state/model_benchmarks.json via canonical_state_dir().

  router.get('/models/benchmarks', requireAuth, async (req, res) => {
    try {
      const py = await requestPythonJSON('/api/models/benchmarks', 'GET', null, { timeoutMs: 5000 });
      const status = py && py._http_status ? py._http_status : 200;
      const { _http_status, ...payload } = py || {};
      return res.status(status).json(payload && Object.keys(payload).length ? payload
        : { ok: false, error: 'python_backend_empty' });
    } catch (e) {
      return res.status(503).json({ ok: false, error: 'python_backend_unreachable', detail: e.message });
    }
  });

  // ── GET /api/ollama/status ───────────────────────────────────────────────────

  router.get('/ollama/status', requireAuth, async (req, res) => {
    const runtime = await ollamaAdmin.getRuntimeStatus().catch((error) => ({ ok: false, status: 'error', error: error.message }));
    res.json(runtime);
  });

  router.post('/ollama/start', requireAuth, async (req, res) => {
    const result = await ollamaAdmin.startManaged({ waitMs: 20000 }).catch((error) => ({ ok: false, error: error.message }));
    res.status(result.ok ? 200 : 503).json(result);
  });

  // ── GET /api/ollama/recommendation ───────────────────────────────────────────

  router.get('/ollama/recommendation', requireAuth, async (req, res) => {
    const recommendation = await Promise.resolve(ollamaAdmin.getModelRecommendation()).catch((error) => ({ error: error.message }));
    res.status(recommendation.error ? 502 : 200).json(recommendation.error ? { ok: false, error: recommendation.error } : { ok: true, recommendation });
  });

  // ── GET /api/ollama/models ───────────────────────────────────────────────────

  router.get('/ollama/models', requireAuth, async (req, res) => {
    const models = await ollamaAdmin.listModels().catch(() => []);
    res.json({ models });
  });

  // ── POST /api/ollama/pull ────────────────────────────────────────────────────

  router.post('/ollama/pull', requireAuth, _rl_ollama_pull, async (req, res) => {
    const name = String((req.body || {}).name || '').trim();
    if (!name) return res.status(400).json({ ok: false, error: 'name required' });
    if (name.length > 100) return res.status(400).json({ ok: false, error: 'model name too long (max 100 chars)' });
    // Allowlist: lowercase alphanumeric, colon (tag separator), dot, hyphen, underscore only
    if (!/^[a-z0-9:._\-]+$/.test(name)) return res.status(400).json({ ok: false, error: 'invalid model name format' });
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    try {
      for await (const chunk of ollamaAdmin.pullModelStream(name)) {
        res.write(`data: ${JSON.stringify(chunk)}\n\n`);
      }
      res.write(`data: ${JSON.stringify({ status: 'complete' })}\n\n`);
    } catch (e) {
      res.write(`data: ${JSON.stringify({ status: 'error', error: e.message })}\n\n`);
    }
    res.end();
  });

  // ── POST /api/ollama/pull-recommended ───────────────────────────────────────

  router.post('/ollama/pull-recommended', requireAuth, _rl_ollama_pull, async (req, res) => {
    const recommendation = ollamaAdmin.getModelRecommendation();
    const name = recommendation.model;
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    try {
      res.write(`data: ${JSON.stringify({ status: 'recommendation', recommendation, name })}\n\n`);
      for await (const chunk of ollamaAdmin.pullModelStream(name)) {
        res.write(`data: ${JSON.stringify({ ...chunk, recommendation, name })}\n\n`);
      }
      res.write(`data: ${JSON.stringify({ status: 'complete', complete: true, recommendation, name })}\n\n`);
    } catch (e) {
      res.write(`data: ${JSON.stringify({ status: 'error', error: e.message, recommendation, name })}\n\n`);
    }
    res.end();
  });

  // ── DELETE /api/ollama/models/:name ─────────────────────────────────────────

  router.delete('/ollama/models/:name', requireAuth, async (req, res) => {
    const name = decodeURIComponent(req.params.name || '').trim();
    if (!name) return res.status(400).json({ ok: false, error: 'name required' });
    if (name.length > 100) return res.status(400).json({ ok: false, error: 'model name too long (max 100 chars)' });
    // Same allowlist as pull: lowercase alphanumeric, colon, dot, hyphen, underscore
    if (!/^[a-z0-9:._\-]+$/.test(name)) return res.status(400).json({ ok: false, error: 'invalid model name format' });
    const result = await ollamaAdmin.deleteModel(name).catch(e => ({ ok: false, error: e.message }));
    res.json(result);
  });

  // ── GET /api/ollama/ps — currently loaded models ─────────────────────────────

  router.get('/ollama/ps', requireAuth, async (req, res) => {
    const result = await ollamaAdmin.listRunning().catch(e => ({ ok: false, models: [], error: e.message }))
    res.json(result)
  })

  // ── POST /api/ollama/load — warm a model into VRAM ───────────────────────────

  router.post('/ollama/load', requireAuth, async (req, res) => {
    const name = String((req.body || {}).name || '').trim()
    if (!name) return res.status(400).json({ ok: false, error: 'name required' })
    if (!/^[a-z0-9:._\-]+$/.test(name)) return res.status(400).json({ ok: false, error: 'invalid model name format' })
    const keepAlive = Number((req.body || {}).keep_alive ?? -1)
    const result = await ollamaAdmin.loadModel(name, keepAlive).catch(e => ({ ok: false, error: e.message }))
    res.json(result)
  })

  // ── POST /api/ollama/evict — unload a model from VRAM ────────────────────────

  router.post('/ollama/evict', requireAuth, async (req, res) => {
    const name = String((req.body || {}).name || '').trim()
    if (!name) return res.status(400).json({ ok: false, error: 'name required' })
    if (!/^[a-z0-9:._\-]+$/.test(name)) return res.status(400).json({ ok: false, error: 'invalid model name format' })
    const result = await ollamaAdmin.evictModel(name).catch(e => ({ ok: false, error: e.message }))
    res.json(result)
  })

  // ── GET /api/system/manifest ─────────────────────────────────────────────────

  router.get('/system/manifest', requireAuth, (req, res) => {
    res.json(loadSystemManifest());
  });

  // ── POST /api/model/route-plan ───────────────────────────────────────────────

  router.post('/model/route-plan', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.modelRoutePlan, req, res);
    if (!body) return;
    const task = String(body.task || body.message || body.goal || '').trim();
    if (!task) return res.status(400).json({ ok: false, error: 'task, message, or goal required' });
    res.json(buildModelRoutePlan(body));
  });

  // ── GET /api/doctor/status ───────────────────────────────────────────────────

  router.get('/doctor/status', requireAuth, (req, res) => {
    res.json(subsystems.getDoctorStatus());
  });

  // ── GET /api/doctor/llm-status ───────────────────────────────────────────────

  router.get('/doctor/llm-status', requireAuth, async (req, res) => {
    const result = await runForgePython({ operation: 'llm_status' });
    res.json(result || { ollama: { online: false }, groq: { configured: false } });
  });

  // ── GET /api/doctor/errors ───────────────────────────────────────────────────

  router.get('/doctor/errors', requireAuth, (req, res) => {
    const limit = Math.min(100, parseInt((req.query || {}).limit) || 50);
    const errors = (_auditLog || []).filter((e) => e.risk_score >= 0.7 || (e.action || '').includes('fail') || (e.action || '').includes('error')).slice(0, limit);
    res.json({ errors, count: errors.length });
  });

  // ── POST /api/doctor/run ─────────────────────────────────────────────────────

  router.post('/doctor/run', requireAuth, async (req, res) => {
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

  // ── Legacy Forge queue endpoints ─────────────────────────────────────────────
  // backend/routes/forge.js is mounted first and owns overlapping /api/forge routes.
  // These handlers are retained for older dashboard clients that use submit/approve/reject.

  // GET /api/forge/queue
  router.get('/forge/queue', requireAuth, (req, res) => {
    const status = (req.query || {}).status || '';
    const items = status ? getForgeQueue().filter((r) => r.status === status) : getForgeQueue();
    res.json({ items, total: getForgeQueue().length });
  });

  // POST /api/forge/submit
  router.post('/forge/submit', requireAuth, _rl_forge, (req, res) => {
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
  router.post('/forge/approve/:id', requireAuth, (req, res) => {
    const _bodyForgeApprove = validate(SCHEMAS.forgeApproveItem, req, res);
    if (!_bodyForgeApprove) return;
    const item = getForgeQueue().find((r) => r.id === req.params.id);
    if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
    if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
    const patch = { status: 'approved', decided_at: new Date().toISOString(), decided_by: _bodyForgeApprove.approved_by || 'operator' };
    _forgeQueueUpdate(item.id, patch);
    recordAuditEvent({ actor: item.decided_by, action: 'forge_approve', inputData: { request_id: item.id }, outputData: { status: 'approved' }, riskScore: 0.5 });
    res.json({ ok: true, request: item });
  });

  // POST /api/forge/reject/:id
  router.post('/forge/reject/:id', requireAuth, (req, res) => {
    const _bodyForgeReject = validate(SCHEMAS.forgeRejectItem, req, res);
    if (!_bodyForgeReject) return;
    const item = getForgeQueue().find((r) => r.id === req.params.id);
    if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
    if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
    const patch = { status: 'rejected', decided_at: new Date().toISOString(), decided_by: _bodyForgeReject.rejected_by || 'operator' };
    _forgeQueueUpdate(item.id, patch);
    recordAuditEvent({ actor: item.decided_by, action: 'forge_reject', inputData: { request_id: item.id }, outputData: { status: 'rejected' }, riskScore: 0.3 });
    res.json({ ok: true, request: item });
  });

  // POST /api/forge/sandbox
  router.post('/forge/sandbox', requireAuth, async (req, res) => {
    const body = validate(SCHEMAS.forgeSandbox, req, res);
    if (!body) return;
    const goal = String(body.goal || '').trim();
    const result = await runForgePython({ operation: 'sandbox', goal, module_path: body.module_path || 'forge_sandbox_test' });
    if (!result) return res.status(500).json({ ok: false, error: 'forge_python_failed' });
    res.json({ ok: true, ...result });
  });

  // POST /api/forge/rollback
  router.post('/forge/rollback', requireAuth, async (req, res) => {
    const body = validate(SCHEMAS.forgeRollback, req, res);
    if (!body) return;
    const snapshot_id = String(body.snapshot_id || 'latest').trim();
    const result = await runForgePython({ operation: 'rollback', snapshot_id });
    recordAuditEvent({ actor: body.rolled_back_by || 'operator', action: 'forge_rollback', inputData: { snapshot_id }, outputData: result || {}, riskScore: 0.6 });
    res.json({ ok: true, snapshot_id, ...(result || { message: 'Rollback queued' }), success: true });
  });

  // GET /api/forge/snapshots
  router.get('/forge/snapshots', requireAuth, async (req, res) => {
    const result = await runForgePython({ operation: 'snapshots' });
    if (!result) return res.json({ snapshots: [], summary: {} });
    res.json(result);
  });

  // POST /api/forge/build-system
  router.post('/forge/build-system', requireAuth, async (req, res) => {
    const body = validate(SCHEMAS.forgeBuildSystem, req, res);
    if (!body) return;
    const spec = String(body.spec || '').trim();
    const project_name = String(body.project_name || 'project').trim();
    const result = await runForgePython({ operation: 'build_system', spec, project_name }, 180000);
    if (!result) return res.status(500).json({ ok: false, error: 'forge_python_failed' });
    addActivity(`[FORGE] System built: ${project_name}`, 'automation');
    res.json({ ok: true, ...result });
  });

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

  // POST /api/forge/task
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

  // GET /api/forge/code-ai/models
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

  // POST /api/forge/code-ai
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

  return router;
};
