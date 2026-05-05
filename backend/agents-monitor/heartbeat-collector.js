'use strict';

/**
 * Agent Heartbeat Collector
 *
 * Polls agent logs every 5 seconds to:
 * - Detect agent status changes (busy/idle/dead)
 * - Compute active task IDs
 * - Broadcast heartbeat events via WebSocket
 *
 * Gracefully handles missing agent files (new agents haven't logged yet).
 */

const fs = require('fs');
const path = require('path');

const AGENTS_STATE_DIR = path.resolve(__dirname, '../../state/agents');
const HEARTBEAT_INTERVAL_MS = 5000; // 5s polling
const IDLE_THRESHOLD_MS = 30000; // 30s = idle
const DEAD_THRESHOLD_MS = 60000; // 60s = dead

let heartbeatTimer = null;
let lastHeartbeat = {}; // Track previous state to detect changes

/**
 * Read last entry from agent log
 */
function getLastEntry(agentId) {
  try {
    const logPath = path.join(AGENTS_STATE_DIR, `${agentId}.jsonl`);
    if (!fs.existsSync(logPath)) {
      return null;
    }
    const content = fs.readFileSync(logPath, 'utf8');
    const lines = content.split('\n').filter(l => l.trim());
    if (lines.length === 0) return null;
    return JSON.parse(lines[lines.length - 1]);
  } catch (err) {
    // Log gracefully, don't crash
    return null;
  }
}

/**
 * Compute status based on last entry timestamp
 */
function computeStatus(lastEntry) {
  if (!lastEntry) return 'unknown';
  const lastSeenMs = new Date(lastEntry.timestamp).getTime();
  const nowMs = Date.now();
  const elapsedMs = nowMs - lastSeenMs;

  if (elapsedMs < IDLE_THRESHOLD_MS) return 'busy';
  if (elapsedMs < DEAD_THRESHOLD_MS) return 'idle';
  return 'dead';
}

/**
 * Collect current heartbeat data for all agents
 */
function collectHeartbeats() {
  const heartbeats = [];

  // Ensure dir exists
  if (!fs.existsSync(AGENTS_STATE_DIR)) {
    fs.mkdirSync(AGENTS_STATE_DIR, { recursive: true });
    return heartbeats;
  }

  const files = fs.readdirSync(AGENTS_STATE_DIR);
  const agentLogs = files.filter(f => f.endsWith('.jsonl'));

  agentLogs.forEach(filename => {
    const agentId = filename.replace('.jsonl', '');
    const lastEntry = getLastEntry(agentId);
    const status = computeStatus(lastEntry);

    const heartbeat = {
      agentId,
      status,
      activeTaskId: lastEntry?.taskId || null,
      lastSeen: lastEntry?.timestamp || null,
      event: lastEntry?.event || null,
      timestamp: new Date().toISOString(),
    };

    heartbeats.push(heartbeat);
  });

  return heartbeats;
}

/**
 * Detect changes from previous heartbeat
 */
function detectChanges(current) {
  const changes = [];
  const currentMap = new Map(current.map(h => [h.agentId, h]));
  const previousMap = new Map(Object.entries(lastHeartbeat));

  // Check for status changes or new agents
  currentMap.forEach((curr, agentId) => {
    const prev = previousMap.get(agentId);
    if (!prev) {
      // New agent
      changes.push({
        type: 'agent_discovered',
        agentId,
        status: curr.status,
      });
    } else if (prev.status !== curr.status) {
      // Status change
      changes.push({
        type: 'status_change',
        agentId,
        from: prev.status,
        to: curr.status,
      });
    } else if (prev.activeTaskId !== curr.activeTaskId && curr.activeTaskId) {
      // Task change
      changes.push({
        type: 'task_change',
        agentId,
        taskId: curr.activeTaskId,
      });
    }
  });

  // Check for agents that disappeared
  previousMap.forEach((prev, agentId) => {
    if (!currentMap.has(agentId)) {
      changes.push({
        type: 'agent_lost',
        agentId,
      });
    }
  });

  return changes;
}

/**
 * Start heartbeat collection daemon
 */
function startHeartbeatCollector(broadcasterModule) {
  if (heartbeatTimer) {
    console.warn('[HEARTBEAT] Collector already running');
    return;
  }

  console.log('[HEARTBEAT] Starting collector (interval: ' + HEARTBEAT_INTERVAL_MS + 'ms)');

  heartbeatTimer = setInterval(() => {
    try {
      const heartbeats = collectHeartbeats();
      const changes = detectChanges(heartbeats);

      // Update last heartbeat state
      lastHeartbeat = {};
      heartbeats.forEach(h => {
        lastHeartbeat[h.agentId] = h;
      });

      // Broadcast full heartbeat
      if (broadcasterModule && broadcasterModule.broadcast) {
        broadcasterModule.broadcast('agents:heartbeat', {
          heartbeats,
          changes,
          count: heartbeats.length,
          timestamp: new Date().toISOString(),
        });

        // Also broadcast individual changes for real-time UI updates
        changes.forEach(change => {
          broadcasterModule.broadcast('agents:change', change);
        });
      }
    } catch (err) {
      console.error('[HEARTBEAT] Error in collection loop:', err.message);
    }
  }, HEARTBEAT_INTERVAL_MS);

  heartbeatTimer.unref(); // Don't keep process alive
}

/**
 * Stop heartbeat collector
 */
function stopHeartbeatCollector() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    console.log('[HEARTBEAT] Collector stopped');
  }
}

/**
 * Get current heartbeat state (for health checks, etc.)
 */
function getCurrentHeartbeats() {
  return collectHeartbeats();
}

module.exports = {
  startHeartbeatCollector,
  stopHeartbeatCollector,
  getCurrentHeartbeats,
  HEARTBEAT_INTERVAL_MS,
};
