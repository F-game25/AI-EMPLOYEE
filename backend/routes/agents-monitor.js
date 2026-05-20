'use strict';

/**
 * Agent Activity Monitor Routes
 *
 * Real-time monitoring API for agent status, metrics, and activity logs.
 *
 * Endpoints:
 * - GET /api/agents/monitor/status           — List all agents with status summary
 * - GET /api/agents/monitor/:agentId         — Agent execution log (last 100 entries)
 * - GET /api/agents/monitor/:agentId/metrics  — Aggregated metrics for agent
 * - POST /api/agents/monitor/:agentId/restart — Force agent restart signal
 * - POST /api/agents/monitor/subscribe       — WebSocket upgrade for real-time updates
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { AgentStateRegistry } = require('../agents-monitor/agent-state');
const { getAscendForgeEngine } = require('../ascendforge/engine');

const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'));
const AGENTS_STATE_DIR = path.join(STATE_DIR, 'agents');

/**
 * Simple requireAuth middleware (can be injected from server.js)
 */
const defaultRequireAuth = (req, res, next) => {
  if (!req.user && !req.tenant) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
};
const ACTIVITY_LOG_LIMIT = 100;
const METRICS_WINDOW_MS = 3600000; // 1 hour for metrics aggregation

/**
 * Parse a JSONL file and return entries as array
 * Returns empty array if file doesn't exist
 */
function readAgentLog(agentId) {
  const logPath = path.join(AGENTS_STATE_DIR, `${agentId}.jsonl`);
  if (!fs.existsSync(logPath)) {
    return [];
  }
  try {
    const content = fs.readFileSync(logPath, 'utf8');
    return content
      .split('\n')
      .filter(line => line.trim())
      .map(line => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  } catch (err) {
    console.error(`[AGENT-MONITOR] Error reading log for ${agentId}:`, err.message);
    return [];
  }
}

/**
 * Get the last entry from agent log (or null if none)
 */
function getLastEntry(agentId) {
  const entries = readAgentLog(agentId);
  return entries.length > 0 ? entries[entries.length - 1] : null;
}

/**
 * Compute agent status based on last activity
 */
function computeAgentStatus(agentId, lastEntry) {
  if (!lastEntry) {
    return 'unknown'; // Agent never logged
  }

  const lastSeenMs = new Date(lastEntry.timestamp).getTime();
  const nowMs = Date.now();
  const idleThresholdMs = 30000; // 30s = idle, 60s = dead

  if (nowMs - lastSeenMs < idleThresholdMs) {
    return 'busy';
  }
  if (nowMs - lastSeenMs < 60000) {
    return 'idle';
  }
  return 'dead';
}

/**
 * Aggregate metrics from agent log entries
 */
function aggregateMetrics(agentId) {
  const entries = readAgentLog(agentId);
  const now = Date.now();
  const windowStart = now - METRICS_WINDOW_MS;

  const metrics = {
    success_rate: 0,
    avg_duration_ms: 0,
    tasks_completed: 0,
    tasks_failed: 0,
    errors_total: 0,
    last_task_result: null,
  };

  const windowEntries = entries.filter(
    e => new Date(e.timestamp).getTime() >= windowStart
  );

  if (windowEntries.length === 0) {
    return metrics;
  }

  let totalDuration = 0;
  let completedCount = 0;
  let failedCount = 0;

  windowEntries.forEach(entry => {
    if (entry.event === 'task_completed') {
      completedCount++;
      metrics.tasks_completed++;
      if (entry.duration_ms) {
        totalDuration += entry.duration_ms;
      }
    } else if (entry.event === 'task_failed') {
      failedCount++;
      metrics.tasks_failed++;
      metrics.errors_total++;
    }
  });

  const taskTotal = completedCount + failedCount;
  if (taskTotal > 0) {
    metrics.success_rate = (completedCount / taskTotal) * 100;
  }

  if (completedCount > 0) {
    metrics.avg_duration_ms = Math.round(totalDuration / completedCount);
  }

  // Last task (regardless of result)
  if (windowEntries.length > 0) {
    const lastTask = windowEntries[windowEntries.length - 1];
    metrics.last_task_result = {
      event: lastTask.event,
      taskId: lastTask.taskId,
      timestamp: lastTask.timestamp,
      output: lastTask.output || null,
      error: lastTask.error || null,
    };
  }

  return metrics;
}

function createAgentsMonitorRouter(broadcasterModule, requireAuthMiddleware, agentStateRegistry) {
  const router = express.Router();
  const requireAuth = requireAuthMiddleware || defaultRequireAuth;
  const registry = agentStateRegistry || new AgentStateRegistry();

  /**
   * GET /api/agents/:agentId/capabilities
   * Return native AscendForge-created agent contract details.
   */
  router.get('/:agentId/capabilities', requireAuth, (req, res) => {
    try {
      const blueprint = getAscendForgeEngine().getBlueprint(req.params.agentId);
      if (!blueprint) {
        return res.status(404).json({ ok: false, error: 'agent capability contract not found' });
      }
      res.json({ ok: true, state: 'live', agent_id: req.params.agentId, capabilities: blueprint });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message || 'failed to load agent capabilities' });
    }
  });

  /**
   * GET /api/agents/:agentId/skills
   * Return resolved global skill records for an AscendForge-created agent.
   */
  router.get('/:agentId/skills', requireAuth, (req, res) => {
    try {
      const engine = getAscendForgeEngine();
      const blueprint = engine.getBlueprint(req.params.agentId);
      if (!blueprint) {
        return res.status(404).json({ ok: false, error: 'agent skill contract not found' });
      }
      const skills = (blueprint.selected_skill_ids || [])
        .map(skillId => engine.getSkill(skillId))
        .filter(Boolean);
      res.json({ ok: true, state: 'live', agent_id: req.params.agentId, skills });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message || 'failed to load agent skills' });
    }
  });

  /**
   * GET /api/agents/monitor/status
   * List all agents with current status (tenant-filtered)
   */
  router.get('/monitor/status', requireAuth, (req, res) => {
    const tenantId = req.tenant?.id || 'default';
    try {
      const agents = registry.getAgentsByTenant(tenantId);
      const withMetrics = agents.map(a => {
        const totalTasks = a.stats.tasksCompleted + a.stats.tasksFailed;
        const errorRate = totalTasks > 0 ? ((a.stats.tasksFailed / totalTasks) * 100).toFixed(2) : 0;
        return {
          agentId: a.id,
          name: a.name,
          status: a.status,
          currentTask: a.currentTask,
          tasksCompleted: a.stats.tasksCompleted,
          averageLatency_ms: a.stats.averageLatency_ms,
          lastActivity: a.stats.lastActivity,
          errorCount: a.stats.tasksFailed,
          errorRate,
        };
      });

      res.json({ agents: withMetrics, count: withMetrics.length, timestamp: new Date().toISOString() });
    } catch (err) {
      console.error('[AGENT-MONITOR] Error fetching agent status:', err.message);
      res.status(500).json({ error: 'Failed to fetch agent status' });
    }
  });

  /**
   * GET /api/agents/monitor/:agentId
   * Get single agent state with execution history
   */
  router.get('/monitor/:agentId', requireAuth, (req, res) => {
    const tenantId = req.tenant?.id || 'default';
    const { agentId } = req.params;

    try {
      const agent = registry.getAgent(agentId, tenantId);
      if (!agent) {
        return res.status(404).json({ error: `Agent ${agentId} not found` });
      }

      const entries = readAgentLog(agentId);
      const activity = entries.slice(-ACTIVITY_LOG_LIMIT);

      res.json({
        agentId,
        agent,
        activity,
        totalHistoryEntries: entries.length,
        activityLimit: ACTIVITY_LOG_LIMIT,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      console.error(`[AGENT-MONITOR] Error fetching activity for ${agentId}:`, err.message);
      res.status(500).json({ error: 'Failed to fetch agent state' });
    }
  });

  /**
   * GET /api/agents/monitor/:agentId/metrics
   * Get aggregated metrics for agent (tenant-filtered)
   */
  router.get('/monitor/:agentId/metrics', requireAuth, (req, res) => {
    const tenantId = req.tenant?.id || 'default';
    const { agentId } = req.params;

    try {
      const agent = registry.getAgent(agentId, tenantId);
      if (!agent) {
        return res.status(404).json({ error: `Agent ${agentId} not found` });
      }

      const metrics = aggregateMetrics(agentId);

      res.json({
        agentId,
        status: agent.status,
        stats: agent.stats,
        metrics,
        windowMs: METRICS_WINDOW_MS,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      console.error(`[AGENT-MONITOR] Error computing metrics for ${agentId}:`, err.message);
      res.status(500).json({ error: 'Failed to compute metrics' });
    }
  });

  /**
   * POST /api/agents/monitor/:agentId/restart
   * Signal agent restart (writes signal to message bus)
   */
  router.post('/monitor/:agentId/restart', requireAuth, (req, res) => {
    const tenantId = req.tenant?.id || 'default';
    const { agentId } = req.params;

    try {
      const agent = registry.getAgent(agentId, tenantId);
      if (!agent) {
        return res.status(404).json({ error: `Agent ${agentId} not found` });
      }

      const signal = {
        event: 'restart_signal',
        agentId,
        timestamp: new Date().toISOString(),
        initiatedBy: req.user?.email || 'unknown',
      };

      // Write signal to agent log
      const logPath = path.join(AGENTS_STATE_DIR, `${agentId}.jsonl`);
      fs.mkdirSync(AGENTS_STATE_DIR, { recursive: true });
      fs.appendFileSync(logPath, JSON.stringify(signal) + '\n');

      // Broadcast restart signal
      if (broadcasterModule && broadcasterModule.broadcast) {
        broadcasterModule.broadcast('agents:restart', {
          agentId,
          tenantId,
          initiatedBy: req.user?.email || 'unknown',
          timestamp: new Date().toISOString(),
        });
      }

      res.json({
        ok: true,
        signal,
      });
    } catch (err) {
      console.error(`[AGENT-MONITOR] Error signaling restart for ${agentId}:`, err.message);
      res.status(500).json({ error: 'Failed to signal restart' });
    }
  });

  /**
   * POST /api/agents/monitor/subscribe
   * WebSocket upgrade for real-time agent updates
   * Broadcaster should handle this via websocket/upgrade-handlers
   */
  router.post('/monitor/subscribe', requireAuth, (req, res) => {
    // This endpoint is a hint for WebSocket upgrade
    // The actual upgrade is handled by websocket middleware
    res.json({ message: 'Use WebSocket connection for real-time updates' });
  });

  return router;
}

module.exports = { createAgentsMonitorRouter, AgentStateRegistry };
