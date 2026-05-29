'use strict';

/**
 * Tasks API Routes
 *
 * Real-time task execution visibility:
 * - GET /api/tasks/list       — Paginated task list with filtering
 * - GET /api/tasks/:id        — Task details with execution trace
 * - POST /api/tasks/queue     — Queue dashboard-visible task
 * - PUT /api/tasks/:id/status — Update task status
 */

const express = require('express');
const crypto = require('crypto');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'));
const SCHEDULES_FILE = path.join(STATE_DIR, 'schedules.json');

function ensureStateDir() {
  fs.mkdirSync(STATE_DIR, { recursive: true });
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  ensureStateDir();
  fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
}

function normalizeTask(task = {}) {
  const created = task.created_at || task.createdAt || task.queuedAt || null;
  const updated = task.updated_at || task.updatedAt || task.completedAt || task.startedAt || created;
  const rawStatus = task.status || 'pending';
  const statusMap = { done: 'completed', cancelled: 'cancelled', pending: 'incoming', running: 'executing' };
  const status = statusMap[rawStatus] || rawStatus;
  const trace = task.trace || task.executionTrace || [];
  const agent = task.agent || task.agentId || task.agentAssignments?.[0] || 'unassigned';
  const title = task.title || task.intent || task.description || task.goal || task.id || 'Untitled task';
  const started = task.startedAt || task.started_at;
  const completed = task.completedAt || task.completed_at;
  const elapsedMs = completed && started
    ? Math.max(0, new Date(completed).getTime() - new Date(started).getTime())
    : started
      ? Math.max(0, Date.now() - new Date(started).getTime())
      : 0;
  return {
    ...task,
    id: task.id || task.taskId || crypto.randomUUID(),
    title,
    description: task.description || title,
    status,
    raw_status: rawStatus,
    progress: task.progress ?? task.progress_percent ?? (status === 'completed' ? 100 : status === 'executing' ? 50 : 0),
    agent,
    priority: task.priority ?? 1,
    created_at: created,
    updated_at: updated,
    elapsed_s: task.elapsed_s ?? Math.round(elapsedMs / 1000),
    trace,
    approval_state: task.approval_state || (task.approval_required ? 'required' : 'not_required'),
    result: task.result || null,
  };
}

function readSchedules() {
  const raw = readJson(SCHEDULES_FILE, []);
  return Array.isArray(raw) ? raw : raw.tasks || [];
}

function saveSchedules(schedules) {
  writeJson(SCHEDULES_FILE, schedules.slice(0, 1000));
}

function normalizeSchedule(schedule = {}) {
  const now = new Date().toISOString();
  return {
    id: schedule.id || `sched-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
    name: String(schedule.name || schedule.task || 'Scheduled task').slice(0, 160),
    goal: String(schedule.goal || schedule.task || schedule.name || '').slice(0, 1000),
    cron: String(schedule.cron || schedule.schedule || '0 9 * * *').slice(0, 80),
    agent: String(schedule.agent || schedule.agent_id || 'orchestrator').slice(0, 120),
    priority: Math.max(0, Math.min(3, Number(schedule.priority ?? 1))),
    status: schedule.status || (schedule.paused ? 'paused' : 'active'),
    paused: schedule.paused === true || schedule.status === 'paused',
    last_status: schedule.last_status || schedule.lastStatus || 'never_run',
    run_history: Array.isArray(schedule.run_history) ? schedule.run_history.slice(0, 50) : [],
    created_at: schedule.created_at || now,
    updated_at: schedule.updated_at || now,
    next_run_hint: schedule.next_run_hint || 'computed by scheduler runner',
  };
}

function createTasksRouter(taskGateway, broadcaster) {
  const router = express.Router();

  // POST /api/tasks/internal/broadcast — localhost-only bridge from the Python
  // backend to the WS broadcaster. Used by the autonomous-research loop to
  // surface task:context_check / task:research_started / task:research_completed.
  router.post('/internal/broadcast', (req, res) => {
    const ip = (req.ip || req.socket?.remoteAddress || '').replace('::ffff:', '');
    if (!['127.0.0.1', '::1', 'localhost'].includes(ip)) {
      return res.status(403).json({ ok: false, error: 'localhost only' });
    }
    const event = String((req.body && req.body.event) || '').trim();
    const payload = (req.body && req.body.payload) || {};
    if (!event) return res.status(400).json({ ok: false, error: 'event required' });
    try {
      if (broadcaster && typeof broadcaster.broadcast === 'function') {
        broadcaster.broadcast(event, payload);
      }
      res.json({ ok: true });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/tasks/list — Paginated task list with filtering
  router.get('/list', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const page = Math.max(1, parseInt(req.query.page || '1', 10));
      const pageSize = Math.min(100, parseInt(req.query.pageSize || '20', 10));
      const status = req.query.status ? req.query.status.split(',') : null;
      const priority = req.query.priority ? parseInt(req.query.priority, 10) : null;

      const tasks = taskGateway.listTasks(tenantId, { page, pageSize, status, priority });
      const normalized = tasks.items.map(normalizeTask);
      res.json({
        ok: true,
        state: normalized.length ? 'live' : 'empty',
        source: 'node_task_gateway',
        data: tasks.items,
        tasks: normalized,
        items: normalized,
        pagination: {
          page: tasks.page,
          pageSize: tasks.pageSize,
          total: tasks.total,
          pages: tasks.pages,
        },
      });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  router.get('/history', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const tasks = taskGateway.listTasks(tenantId, { page: 1, pageSize: 100 });
      const history = tasks.items.map(normalizeTask).filter((task) => ['completed', 'failed', 'cancelled'].includes(task.status));
      res.json({ ok: true, state: history.length ? 'live' : 'empty', source: 'node_task_gateway', history, items: history });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // GET /api/tasks/research/recent — proxy research history from Python backend.
  // This must be declared before `/:id` so "research" is not parsed as a task id.
  router.get('/research/recent', (req, res) => {
    const http = require('http');
    const limit = parseInt(req.query.limit || '20', 10);
    const pyPort = process.env.PYTHON_BACKEND_PORT || 18790;
    const proxyReq = http.request(
      `http://127.0.0.1:${pyPort}/api/research/recent?limit=${limit}`,
      { method: 'GET', timeout: 10000 },
      (pyRes) => {
        let data = '';
        pyRes.on('data', (chunk) => { data += chunk; });
        pyRes.on('end', () => {
          try { res.status(pyRes.statusCode || 200).json(JSON.parse(data || '{}')); }
          catch { res.status(502).json({ sessions: [], error: 'invalid python response' }); }
        });
      },
    );
    proxyReq.on('error', (err) => res.status(503).json({ sessions: [], error: err.message }));
    proxyReq.on('timeout', () => { proxyReq.destroy(); res.status(504).json({ sessions: [], error: 'timeout' }); });
    proxyReq.end();
  });

  // GET /api/tasks/:id — Task details with execution trace
  router.get('/:id', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const task = taskGateway.getTask(tenantId, req.params.id);

      if (!task) {
        return res.status(404).json({ ok: false, error: 'Task not found' });
      }

      res.json({ ok: true, state: 'live', source: 'node_task_gateway', data: task, task: normalizeTask(task) });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // POST /api/tasks/queue — Queue dashboard-visible task.
  //
  // `/api/tasks/run` is owned by backend/server.js and submits work to the
  // main execution/orchestration path. Keeping this dashboard queue endpoint
  // separate avoids shadowing the production task runner.
  router.post('/queue', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const { intent, description, priority } = req.body;

      if (!intent || !description) {
        return res.status(400).json({ ok: false, error: 'intent and description required' });
      }

      const priorityVal = Math.max(0, Math.min(3, priority || 1));
      const task = taskGateway.createTask(tenantId, {
        intent,
        description,
        priority: priorityVal,
      });

      const normalized = normalizeTask(task);
      if (broadcaster?.broadcast) broadcaster.broadcast('task:update', normalized);
      res.status(201).json({ ok: true, state: 'live', source: 'node_task_gateway', data: task, task: normalized });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // PUT /api/tasks/:id/status — Update task status
  router.put('/:id/status', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const { status, result } = req.body;
      const validStatuses = ['pending', 'running', 'done', 'failed', 'cancelled'];

      if (!validStatuses.includes(status)) {
        return res.status(400).json({
          ok: false,
          error: `Invalid status. Must be one of: ${validStatuses.join(', ')}`,
        });
      }

      const task = taskGateway.updateTaskStatus(tenantId, req.params.id, status, result);

      if (!task) {
        return res.status(404).json({ ok: false, error: 'Task not found' });
      }

      const normalized = normalizeTask(task);
      if (broadcaster?.broadcast) broadcaster.broadcast('task:update', normalized);
      res.json({ ok: true, state: 'live', source: 'node_task_gateway', data: task, task: normalized });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // POST /api/tasks/:id/context-response — Forward user's YES/NO choice on the
  // context-check modal to the Python backend (AgentController). Used by the
  // autonomous-research loop.
  router.post('/:id/context-response', (req, res) => {
    const http = require('http');
    const choice = String((req.body && req.body.choice) || 'continue');
    const body = JSON.stringify({ choice });
    const pyPort = process.env.PYTHON_BACKEND_PORT || 18790;
    const proxyReq = http.request(
      `http://127.0.0.1:${pyPort}/api/tasks/${encodeURIComponent(req.params.id)}/context-response`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
        timeout: 10000,
      },
      (pyRes) => {
        let data = '';
        pyRes.on('data', (chunk) => { data += chunk; });
        pyRes.on('end', () => {
          try { res.status(pyRes.statusCode || 200).json(JSON.parse(data || '{}')); }
          catch { res.status(502).json({ ok: false, error: 'invalid python response' }); }
        });
      },
    );
    proxyReq.on('error', (err) => res.status(503).json({ ok: false, error: err.message }));
    proxyReq.on('timeout', () => { proxyReq.destroy(); res.status(504).json({ ok: false, error: 'timeout' }); });
    proxyReq.write(body);
    proxyReq.end();
  });

  router.post('/:id/cancel', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const task = taskGateway.updateTaskStatus(tenantId, req.params.id, 'cancelled', { cancelled_by: 'operator', reason: req.body?.reason || 'cancelled from dashboard' });
      if (!task) return res.status(404).json({ ok: false, error: 'Task not found' });
      const normalized = normalizeTask(task);
      if (broadcaster?.broadcast) broadcaster.broadcast('task:update', normalized);
      res.json({ ok: true, state: 'live', task: normalized });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  router.post('/:id/retry', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const original = taskGateway.getTask(tenantId, req.params.id);
      if (!original) return res.status(404).json({ ok: false, error: 'Task not found' });
      const retry = taskGateway.createTask(tenantId, {
        intent: original.intent || original.title || 'retry',
        description: original.description || original.title || 'Retry task',
        priority: original.priority ?? 1,
      });
      retry.retry_of = original.id;
      const normalized = normalizeTask(retry);
      if (broadcaster?.broadcast) broadcaster.broadcast('task:update', normalized);
      res.json({ ok: true, state: 'live', task: normalized, retry_of: original.id });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // POST /api/tasks/:id/trace — Add execution trace entry
  router.post('/:id/trace', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const { agentId, action, duration_ms, output } = req.body;

      if (!agentId || !action) {
        return res.status(400).json({ ok: false, error: 'agentId and action required' });
      }

      const task = taskGateway.addTrace(tenantId, req.params.id, {
        agentId,
        action,
        duration_ms: duration_ms || 0,
        output: output || '',
      });

      if (!task) {
        return res.status(404).json({ ok: false, error: 'Task not found' });
      }

      res.json({ ok: true, data: task });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  return router;
}

function createSchedulesRouter(taskGateway, broadcaster) {
  const router = express.Router();

  router.get('/', (_req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    res.json({ ok: true, state: schedules.length ? 'live' : 'empty', source: 'node_schedule_store', schedules, items: schedules });
  });

  router.post('/', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const schedule = normalizeSchedule(req.body || {});
    schedules.unshift(schedule);
    saveSchedules(schedules);
    if (broadcaster?.broadcast) broadcaster.broadcast('schedule:update', schedule);
    res.status(201).json({ ok: true, state: 'live', source: 'node_schedule_store', schedule });
  });

  router.patch('/:id', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const idx = schedules.findIndex((schedule) => schedule.id === req.params.id);
    if (idx === -1) return res.status(404).json({ ok: false, error: 'Schedule not found' });
    schedules[idx] = normalizeSchedule({ ...schedules[idx], ...(req.body || {}), id: schedules[idx].id, updated_at: new Date().toISOString() });
    saveSchedules(schedules);
    if (broadcaster?.broadcast) broadcaster.broadcast('schedule:update', schedules[idx]);
    res.json({ ok: true, state: 'live', source: 'node_schedule_store', schedule: schedules[idx] });
  });

  router.post('/:id/run', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const schedule = schedules.find((item) => item.id === req.params.id);
    if (!schedule) return res.status(404).json({ ok: false, error: 'Schedule not found' });
    const tenantId = req.tenant?.id || 'default';
    const task = taskGateway.createTask(tenantId, {
      intent: schedule.goal || schedule.name,
      description: schedule.goal || schedule.name,
      priority: schedule.priority,
    });
    const normalizedTask = normalizeTask({ ...task, agent: schedule.agent });
    schedule.last_status = 'queued';
    schedule.run_history.unshift({ ts: new Date().toISOString(), task_id: normalizedTask.id, status: 'queued' });
    saveSchedules(schedules);
    if (broadcaster?.broadcast) {
      broadcaster.broadcast('schedule:update', schedule);
      broadcaster.broadcast('task:update', normalizedTask);
    }
    res.json({ ok: true, state: 'live', source: 'node_schedule_store', schedule, task: normalizedTask });
  });

  router.post('/:id/pause', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const idx = schedules.findIndex((schedule) => schedule.id === req.params.id);
    if (idx === -1) return res.status(404).json({ ok: false, error: 'Schedule not found' });
    schedules[idx] = normalizeSchedule({ ...schedules[idx], paused: true, status: 'paused', updated_at: new Date().toISOString() });
    saveSchedules(schedules);
    res.json({ ok: true, state: 'live', schedule: schedules[idx] });
  });

  router.post('/:id/resume', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const idx = schedules.findIndex((schedule) => schedule.id === req.params.id);
    if (idx === -1) return res.status(404).json({ ok: false, error: 'Schedule not found' });
    schedules[idx] = normalizeSchedule({ ...schedules[idx], paused: false, status: 'active', updated_at: new Date().toISOString() });
    saveSchedules(schedules);
    res.json({ ok: true, state: 'live', schedule: schedules[idx] });
  });

  router.delete('/:id', (req, res) => {
    const schedules = readSchedules().map(normalizeSchedule);
    const next = schedules.filter((schedule) => schedule.id !== req.params.id);
    if (next.length === schedules.length) return res.status(404).json({ ok: false, error: 'Schedule not found' });
    saveSchedules(next);
    res.json({ ok: true, state: 'live', deleted: req.params.id });
  });

  return router;
}

createTasksRouter.createSchedulesRouter = createSchedulesRouter;
createTasksRouter.normalizeTask = normalizeTask;

module.exports = createTasksRouter;
