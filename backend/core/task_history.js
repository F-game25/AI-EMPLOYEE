'use strict';

const path = require('path');
const fs = require('fs');
const os = require('os');

/**
 * Task History Manager
 * Persists task execution history for user visibility
 */

const AI_HOME = path.join(os.homedir(), '.ai-employee');
const HISTORY_FILE = path.join(AI_HOME, 'state', 'task_history.jsonl');

class TaskHistoryManager {
  constructor() {
    this.ensureFile();
    this.cache = this.loadHistory();
  }

  ensureFile() {
    const dir = path.dirname(HISTORY_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    if (!fs.existsSync(HISTORY_FILE)) {
      fs.writeFileSync(HISTORY_FILE, '');
    }
  }

  /**
   * Load history from disk into memory
   */
  loadHistory() {
    try {
      const content = fs.readFileSync(HISTORY_FILE, 'utf8');
      return content
        .split('\n')
        .filter(l => l.trim())
        .map(l => {
          try {
            return JSON.parse(l);
          } catch {
            return null;
          }
        })
        .filter(Boolean);
    } catch (_) {
      return [];
    }
  }

  /**
   * Record a new task execution
   */
  recordTask(taskData) {
    const record = {
      task_id: taskData.task_id || require('crypto').randomBytes(8).toString('hex'),
      timestamp: new Date().toISOString(),
      input: taskData.input || '',
      status: taskData.status || 'pending',
      agent_sequence: taskData.agent_sequence || [],
      result_preview: taskData.result_preview || '',
      duration_ms: taskData.duration_ms || 0,
      cost_estimate_usd: taskData.cost_estimate_usd || 0,
      confidence: taskData.confidence || 0,
      error: taskData.error || null,
    };

    // Append to file
    fs.appendFileSync(HISTORY_FILE, JSON.stringify(record) + '\n');

    // Update cache
    this.cache.push(record);

    // Keep only last 1000 in memory
    if (this.cache.length > 1000) {
      this.cache = this.cache.slice(-1000);
    }

    return record;
  }

  /**
   * Update task status
   */
  updateTask(taskId, updates) {
    const task = this.cache.find(t => t.task_id === taskId);
    if (!task) return null;

    Object.assign(task, updates);

    // Rewrite entire file (not optimal, but safe for small dataset)
    this.saveCache();

    return task;
  }

  /**
   * Get task by ID
   */
  getTask(taskId) {
    return this.cache.find(t => t.task_id === taskId) || null;
  }

  /**
   * Get recent tasks
   */
  getRecent(limit = 50, filters = {}) {
    let results = [...this.cache].reverse();

    // Filter by status
    if (filters.status) {
      results = results.filter(t => t.status === filters.status);
    }

    // Filter by date range
    if (filters.after) {
      const afterTime = new Date(filters.after).getTime();
      results = results.filter(t => new Date(t.timestamp).getTime() >= afterTime);
    }

    // Filter by agent
    if (filters.agent) {
      results = results.filter(t => t.agent_sequence.includes(filters.agent));
    }

    return results.slice(0, limit);
  }

  /**
   * Get statistics
   */
  getStats() {
    const total = this.cache.length;
    const completed = this.cache.filter(t => t.status === 'done').length;
    const failed = this.cache.filter(t => t.status === 'failed').length;
    const avgDuration = total > 0 ? this.cache.reduce((sum, t) => sum + t.duration_ms, 0) / total : 0;
    const totalCost = this.cache.reduce((sum, t) => sum + t.cost_estimate_usd, 0);
    const avgConfidence = total > 0 ? this.cache.reduce((sum, t) => sum + t.confidence, 0) / total : 0;

    return {
      total_tasks: total,
      completed: completed,
      failed: failed,
      success_rate: total > 0 ? (completed / total) * 100 : 0,
      avg_duration_ms: Math.round(avgDuration),
      total_cost_usd: Math.round(totalCost * 100) / 100,
      avg_confidence: Math.round(avgConfidence * 100) / 100,
    };
  }

  /**
   * Get agent performance
   */
  getAgentStats(agentId) {
    const tasks = this.cache.filter(t => t.agent_sequence.includes(agentId));
    if (tasks.length === 0) {
      return { agent_id: agentId, tasks_count: 0 };
    }

    const successful = tasks.filter(t => t.status === 'done').length;
    const avgConfidence = tasks.reduce((sum, t) => sum + t.confidence, 0) / tasks.length;

    return {
      agent_id: agentId,
      tasks_count: tasks.length,
      success_rate: (successful / tasks.length) * 100,
      avg_confidence: Math.round(avgConfidence * 100) / 100,
      avg_duration_ms: Math.round(tasks.reduce((sum, t) => sum + t.duration_ms, 0) / tasks.length),
    };
  }

  /**
   * Save cache back to file
   */
  saveCache() {
    const lines = this.cache.map(t => JSON.stringify(t)).join('\n');
    fs.writeFileSync(HISTORY_FILE, lines + '\n');
  }

  /**
   * Clear old history (older than N days)
   */
  cleanup(daysOld = 30) {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - daysOld);

    const before = this.cache.length;
    this.cache = this.cache.filter(t => new Date(t.timestamp) >= cutoff);

    if (before !== this.cache.length) {
      this.saveCache();
    }

    return {
      removed: before - this.cache.length,
      remaining: this.cache.length,
    };
  }
}

module.exports = TaskHistoryManager;
