'use strict';

/**
 * Tasks API Routes
 *
 * Real-time task execution visibility:
 * - GET /api/tasks/list       — Paginated task list with filtering
 * - GET /api/tasks/:id        — Task details with execution trace
 * - POST /api/tasks/run       — Queue new task
 * - PUT /api/tasks/:id/status — Update task status
 */

const express = require('express');
const crypto = require('crypto');
const { spawn } = require('child_process');
const path = require('path');

function createTasksRouter(taskGateway) {
  const router = express.Router();

  // GET /api/tasks/list — Paginated task list with filtering
  router.get('/list', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const page = Math.max(1, parseInt(req.query.page || '1', 10));
      const pageSize = Math.min(100, parseInt(req.query.pageSize || '20', 10));
      const status = req.query.status ? req.query.status.split(',') : null;
      const priority = req.query.priority ? parseInt(req.query.priority, 10) : null;

      const tasks = taskGateway.listTasks(tenantId, { page, pageSize, status, priority });
      res.json({
        ok: true,
        data: tasks.items,
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

  // GET /api/tasks/:id — Task details with execution trace
  router.get('/:id', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const task = taskGateway.getTask(tenantId, req.params.id);

      if (!task) {
        return res.status(404).json({ ok: false, error: 'Task not found' });
      }

      res.json({ ok: true, data: task });
    } catch (err) {
      res.status(400).json({ ok: false, error: err.message });
    }
  });

  // POST /api/tasks/run — Queue new task
  router.post('/run', (req, res) => {
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

      res.status(201).json({ ok: true, data: task });
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

      res.json({ ok: true, data: task });
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

module.exports = createTasksRouter;
