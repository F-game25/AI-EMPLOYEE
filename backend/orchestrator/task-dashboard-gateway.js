'use strict';

/**
 * Task Dashboard Gateway
 *
 * Real-time bridge for task execution visibility:
 * - Manages task state in state/tasks.json
 * - Publishes updates via WebSocket connManager
 * - Provides methods for task lifecycle management
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const { CHANNELS } = require('../websocket/channels');

const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'));
const TASKS_FILE = path.join(STATE_DIR, 'tasks.json');

class TaskDashboardGateway {
  constructor() {
    this.connManager = null;
    this.ensureStateFile();
  }

  setConnectionManager(connManager) {
    this.connManager = connManager;
  }

  ensureStateFile() {
    if (!fs.existsSync(STATE_DIR)) {
      fs.mkdirSync(STATE_DIR, { recursive: true });
    }
    if (!fs.existsSync(TASKS_FILE)) {
      fs.writeFileSync(TASKS_FILE, JSON.stringify({ tasks: {} }, null, 2), 'utf8');
    }
  }

  _readTasks() {
    try {
      const data = fs.readFileSync(TASKS_FILE, 'utf8');
      return JSON.parse(data).tasks || {};
    } catch {
      return {};
    }
  }

  _writeTasks(tasks) {
    const dir = path.dirname(TASKS_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(TASKS_FILE, JSON.stringify({ tasks }, null, 2), 'utf8');
  }

  _getTenantTasks(tenantId) {
    const all = this._readTasks();
    return all[tenantId] || {};
  }

  _setTenantTasks(tenantId, tasks) {
    const all = this._readTasks();
    all[tenantId] = tasks;
    this._writeTasks(all);
  }

  publishTaskUpdate(tenantId, taskId, message) {
    if (!this.connManager) return;

    this.connManager.broadcastToTenant(tenantId, CHANNELS.TASKS_UPDATED, {
      type: message.event || 'task-update',
      taskId,
      ...message,
      timestamp: Date.now(),
    });
  }

  createTask(tenantId, { intent, description, priority = 1 }) {
    const taskId = crypto.randomUUID();
    const now = new Date().toISOString();

    const task = {
      id: taskId,
      intent,
      description,
      status: 'pending',
      priority: Math.max(0, Math.min(3, priority)),
      createdAt: now,
      startedAt: null,
      completedAt: null,
      result: null,
      executionTrace: [],
      agentAssignments: [],
    };

    const tenantTasks = this._getTenantTasks(tenantId);
    tenantTasks[taskId] = task;
    this._setTenantTasks(tenantId, tenantTasks);

    this.publishTaskUpdate(tenantId, taskId, { event: 'created', task });

    return task;
  }

  getTask(tenantId, taskId) {
    const tasks = this._getTenantTasks(tenantId);
    return tasks[taskId] || null;
  }

  listTasks(tenantId, { page = 1, pageSize = 20, status = null, priority = null } = {}) {
    const tasks = this._getTenantTasks(tenantId);
    let items = Object.values(tasks);

    if (status && status.length > 0) {
      items = items.filter((t) => status.includes(t.status));
    }

    if (priority !== null && priority !== undefined) {
      items = items.filter((t) => t.priority === priority);
    }

    // Sort by createdAt descending
    items.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    const total = items.length;
    const pages = Math.ceil(total / pageSize);
    const start = (page - 1) * pageSize;
    const end = start + pageSize;

    return {
      items: items.slice(start, end),
      page,
      pageSize,
      total,
      pages,
    };
  }

  updateTaskStatus(tenantId, taskId, status, result = null) {
    const tasks = this._getTenantTasks(tenantId);
    const task = tasks[taskId];

    if (!task) return null;

    const validStatuses = ['pending', 'running', 'done', 'failed', 'cancelled'];
    if (!validStatuses.includes(status)) {
      throw new Error(`Invalid status: ${status}`);
    }

    const now = new Date().toISOString();

    if (status === 'running' && !task.startedAt) {
      task.startedAt = now;
    }

    if (['done', 'failed', 'cancelled'].includes(status) && !task.completedAt) {
      task.completedAt = now;
    }

    task.status = status;
    if (result) {
      task.result = result;
    }

    this._setTenantTasks(tenantId, tasks);
    this.publishTaskUpdate(tenantId, taskId, { event: 'status-changed', task });

    return task;
  }

  addTrace(tenantId, taskId, { agentId, action, duration_ms = 0, output = '' }) {
    const tasks = this._getTenantTasks(tenantId);
    const task = tasks[taskId];

    if (!task) return null;

    const validActions = ['started', 'completed', 'failed'];
    if (!validActions.includes(action)) {
      throw new Error(`Invalid action: ${action}`);
    }

    const trace = {
      timestamp: new Date().toISOString(),
      agentId,
      action,
      duration_ms,
      output,
    };

    task.executionTrace.push(trace);

    if (!task.agentAssignments.includes(agentId)) {
      task.agentAssignments.push(agentId);
    }

    this._setTenantTasks(tenantId, tasks);
    this.publishTaskUpdate(tenantId, taskId, { event: 'trace-added', trace });

    return task;
  }

  getTasks(tenantId) {
    return Object.values(this._getTenantTasks(tenantId));
  }
}

module.exports = new TaskDashboardGateway();
