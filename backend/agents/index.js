'use strict';

const { EventEmitter } = require('events');
const path = require('path');
const fs = require('fs');
const { snapshot, agentLoad, formatLocation, taskDurationMs, findBestAgent } = require('../services/agent_lifecycle');

// ── Category → subsystem skill mapping ────────────────────────────────────────
// Maps agent_capabilities.json categories to internal subsystem skill tokens
// so agents can be routed by the orchestrator's subsystem-based routing.
const CATEGORY_SKILLS = {
  sales: ['general', 'memory'],
  marketing: ['general', 'memory'],
  content: ['general', 'nn'],
  analytics: ['general', 'nn', 'doctor'],
  research: ['general', 'memory', 'nn'],
  finance: ['general', 'doctor'],
  trading: ['general', 'nn'],
  ecommerce: ['general', 'memory'],
  social: ['general', 'nn'],
  operations: ['general', 'doctor'],
  coordination: ['general', 'memory', 'nn', 'doctor'],
  strategy: ['general', 'nn', 'doctor'],
  intelligence: ['general', 'memory', 'nn'],
  engineering: ['general', 'nn'],
  development: ['general', 'nn'],
  coding: ['general', 'nn'],
  design: ['general', 'nn'],
  hr: ['general', 'memory'],
  management: ['general', 'doctor'],
  support: ['general', 'memory'],
  testing: ['general', 'doctor'],
  communication: ['general', 'memory'],
  growth: ['general', 'nn', 'memory'],
  creative: ['general', 'nn'],
  crypto: ['general', 'nn'],
  orchestrator: ['general', 'memory', 'nn', 'doctor'],
};

// ── Load agent catalog from runtime/config/agent_capabilities.json ────────────
// Falls back to a minimal built-in catalog if the config file is missing.
function loadAgentCatalog() {
  // Prefer AI_EMPLOYEE_REPO_DIR env var (set by start.sh), then fall back to
  // relative path from __dirname (works when running directly from the repo).
  const repoRoot = process.env.AI_EMPLOYEE_REPO_DIR
    ? path.resolve(process.env.AI_EMPLOYEE_REPO_DIR)
    : path.resolve(__dirname, '../..');
  const configPath = path.join(repoRoot, 'runtime', 'config', 'agent_capabilities.json');
  try {
    const raw = fs.readFileSync(configPath, 'utf8');
    const data = JSON.parse(raw);
    const agentsMap = data.agents || {};
    const catalog = [];
    for (const [agentId, info] of Object.entries(agentsMap)) {
      const category = info.category || 'general';
      const skills = CATEGORY_SKILLS[category] || ['general'];
      catalog.push({
        id: agentId,
        name: agentId
          .split('-')
          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(''),
        type: category,
        skills,
        description: info.description || '',
        capabilities: (info.skills || []).slice(0, 6),
      });
    }
    if (catalog.length === 0) throw new Error('empty catalog');
    return catalog;
  } catch {
    // Fallback: minimal built-in catalog
    return [
      { id: 'orchestrator', name: 'Orchestrator', type: 'coordination', skills: ['general', 'memory', 'nn', 'doctor'], description: 'Master task router', capabilities: [] },
      { id: 'lead-hunter', name: 'LeadHunter', type: 'sales', skills: ['general', 'memory'], description: 'B2B lead generation', capabilities: [] },
      { id: 'content-master', name: 'ContentMaster', type: 'content', skills: ['general', 'nn'], description: 'SEO content specialist', capabilities: [] },
      { id: 'data-analyst', name: 'DataAnalyst', type: 'analytics', skills: ['general', 'nn', 'doctor'], description: 'Data analysis and reporting', capabilities: [] },
      { id: 'social-guru', name: 'SocialGuru', type: 'social', skills: ['general', 'nn'], description: 'Social media management', capabilities: [] },
      { id: 'support-bot', name: 'SupportBot', type: 'support', skills: ['general', 'memory'], description: 'Customer support automation', capabilities: [] },
    ];
  }
}

const AGENT_CATALOG = loadAgentCatalog();

// How long an inactive running agent waits before being scaled back to idle.
const IDLE_SCALE_DOWN_MS = 20000;
// Agent runtime scheduler frequency (persistent event-driven loop tick).
const LOOP_INTERVAL_MS = 250;

const HEALTH_DEGRADED_QUEUE_THRESHOLD = 3;
const MODES = {
  MANUAL: 'MANUAL',
  AUTO: 'AUTO',
  BLACKLIGHT: 'BLACKLIGHT',
  MONEYMODE: 'MONEYMODE',
};

const events = new EventEmitter();
let mode = MODES.MANUAL;
let _seq = 0;
let lastRobotSignal = {
  agentId: null,
  agentName: null,
  taskId: null,
  subsystem: null,
  location: 'idle',
  updatedAt: new Date().toISOString(),
};

const agents = AGENT_CATALOG.map((profile) => ({
  ...profile,
  state: 'running', // all agents start active at full capacity
  health: 'healthy',
  taskQueue: [],
  currentTask: null,
  location: 'standby',
  lastActivityAt: Date.now(),
  tasksCompleted: 0,
}));

// Full capacity — all agents on from the start
let desiredActiveAgents = agents.length;

function _now() {
  return Date.now();
}

function _modeMaxActive() {
  // Always run all agents at full capacity regardless of operational mode.
  return agents.length;
}

function _broadcastAgentUpdate() {
  events.emit('agent:update', getAgents());
}

function _updateRobotSignal(agent, details = {}) {
  lastRobotSignal = {
    agentId: agent.id,
    agentName: agent.name,
    taskId: details.taskId || null,
    subsystem: details.subsystem || null,
    location: details.location || agent.location || agent.state || 'idle',
    updatedAt: new Date().toISOString(),
  };
}

function _setState(agent, nextState) {
  if (agent.state !== nextState) {
    agent.state = nextState;
    agent.lastActivityAt = _now();
  }
}

function createCancellationError(reason) {
  return `cancelled:${reason}`;
}

function _activateAgent(agent) {
  if (agent.state === 'idle') {
    _setState(agent, 'running');
    agent.health = 'healthy';
    agent.location = 'standby';
  }
}

function _deactivateAgent(agent) {
  if (agent.state !== 'busy' && agent.taskQueue.length === 0) {
    _setState(agent, 'idle');
    agent.currentTask = null;
    agent.health = 'offline';
    agent.location = 'idle';
  }
}

function _runningAgents() {
  return agents.filter((a) => a.state === 'running' || a.state === 'busy');
}

function _activateForDemand(subsystem, categoryHint) {
  const maxActive = _modeMaxActive();
  const active = _runningAgents().length;
  if (active >= maxActive) return;

  // Prefer activating an agent whose category matches the hint.
  const candidate =
    (categoryHint && agents.find((a) => a.state === 'idle' && a.type === categoryHint)) ||
    agents.find(
      (a) =>
        a.state === 'idle' &&
        (a.skills.includes(subsystem) || a.skills.includes('general')),
    ) ||
    agents.find((a) => a.state === 'idle');

  if (candidate) _activateAgent(candidate);
}

function _rebalance() {
  const now = _now();
  const maxActive = _modeMaxActive();
  const minDesired = Math.min(desiredActiveAgents, maxActive);

  // Keep at least desired active agents running.
  while (_runningAgents().length < minDesired) {
    const next = agents.find((a) => a.state === 'idle');
    if (!next) break;
    _activateAgent(next);
  }

  // Scale down idle capacity if above desired.
  const running = _runningAgents()
    .filter((a) => a.state === 'running' && a.taskQueue.length === 0)
    .sort((a, b) => a.lastActivityAt - b.lastActivityAt);

  for (const agent of running) {
    if (_runningAgents().length <= minDesired) break;
    if (now - agent.lastActivityAt >= IDLE_SCALE_DOWN_MS) {
      _deactivateAgent(agent);
    }
  }
}

function _tick() {
  let changed = false;
  const now = _now();

  for (const agent of agents) {
    // Complete active task.
    if (agent.currentTask && now >= agent.currentTask.finishAt) {
      const completedTask = agent.currentTask;
      agent.currentTask = null;
      agent.tasksCompleted += 1;
      _setState(agent, 'running');
      agent.location = formatLocation('completed', completedTask.subsystem);
      _updateRobotSignal(agent, {
        taskId: completedTask.id,
        subsystem: completedTask.subsystem || 'general',
        location: agent.location,
      });
      agent.health = 'healthy';
      const shouldFail = Boolean(completedTask?.metadata?.forceFail);
      if (shouldFail) {
        events.emit('task:failed', {
          agent: snapshot(agent),
          task: {
            ...completedTask,
            error: 'forced_failure',
          },
          finishedAt: new Date().toISOString(),
        });
      } else {
        events.emit('task:completed', {
          agent: snapshot(agent),
          task: completedTask,
          finishedAt: new Date().toISOString(),
        });
      }
      changed = true;
    }

    // Pick up next task from queue.
    if (!agent.currentTask && agent.taskQueue.length > 0 && agent.state !== 'idle') {
      const task = agent.taskQueue.shift();
      task.startedAt = new Date().toISOString();
      task.finishAt = now + taskDurationMs(agent, task, _seq);
      agent.currentTask = task;
      _setState(agent, 'busy');
      agent.location = formatLocation('processing', task.subsystem);
      _updateRobotSignal(agent, {
        taskId: task.id,
        subsystem: task.subsystem || 'general',
        location: agent.location,
      });
      agent.health = task.queueDepth > HEALTH_DEGRADED_QUEUE_THRESHOLD ? 'degraded' : 'healthy';
      events.emit('task:started', {
        agent: snapshot(agent),
        task,
        startedAt: task.startedAt,
      });
      changed = true;
    }
  }

  _rebalance();
  if (changed) _broadcastAgentUpdate();
}

setInterval(_tick, LOOP_INTERVAL_MS);

function setMode(nextMode) {
  const allowed = new Set(Object.values(MODES));
  mode = allowed.has(nextMode) ? nextMode : MODES.MANUAL;
  if (desiredActiveAgents > _modeMaxActive()) {
    desiredActiveAgents = _modeMaxActive();
  }
  _rebalance();
  _broadcastAgentUpdate();
  return mode;
}

function getMode() {
  return mode;
}

function activateAgents(count) {
  const maxActive = _modeMaxActive();
  const target = typeof count === 'number'
    ? Math.max(1, Math.min(count, maxActive))
    : Math.max(1, Math.min(3, maxActive));
  desiredActiveAgents = target;
  _rebalance();
  _broadcastAgentUpdate();
  return {
    desiredActiveAgents,
    runningAgents: getRunningAgentCount(),
  };
}

function stopAllAgents(reason = 'manual_stop') {
  let cancelledTasks = 0;
  for (const agent of agents) {
    if (agent.currentTask) {
      cancelledTasks += 1;
      events.emit('task:failed', {
        agent: snapshot(agent),
        task: {
          ...agent.currentTask,
          error: createCancellationError(reason),
        },
        finishedAt: new Date().toISOString(),
      });
    }
    cancelledTasks += agent.taskQueue.length;
    agent.taskQueue = [];
    agent.currentTask = null;
    agent.location = 'idle';
    _setState(agent, 'idle');
    agent.health = 'offline';
  }
  desiredActiveAgents = 0;
  lastRobotSignal = {
    agentId: null,
    agentName: null,
    taskId: null,
    subsystem: null,
    location: 'idle',
    updatedAt: new Date().toISOString(),
  };
  _broadcastAgentUpdate();
  return {
    cancelledTasks,
    runningAgents: getRunningAgentCount(),
  };
}

function enqueueTask({ message, subsystem = 'general', categoryHint = null, metadata = {} }) {
  _activateForDemand(subsystem, categoryHint);
  if (_runningAgents().length === 0) {
    activateAgents(1);
  }

  let selected = findBestAgent(_runningAgents(), subsystem, categoryHint);
  if (!selected) {
    selected = agents
      .slice()
      .sort((a, b) => agentLoad(a) - agentLoad(b))[0];
    _activateAgent(selected);
  }

  const queueDepth = selected.taskQueue.length;
  const task = {
    id: `task-${++_seq}`,
    message,
    subsystem,
    queuedAt: new Date().toISOString(),
    queueDepth,
    metadata,
  };
  selected.taskQueue.push(task);
  selected.lastActivityAt = _now();
  if (selected.state === 'idle') _activateAgent(selected);
  selected.location = formatLocation('queued', subsystem);
  _updateRobotSignal(selected, {
    taskId: task.id,
    subsystem: subsystem || 'general',
    location: selected.location,
  });
  _broadcastAgentUpdate();
  return {
    taskId: task.id,
    agentId: selected.id,
    queuedAt: task.queuedAt,
    queueDepth: selected.taskQueue.length,
  };
}

function getAgents() {
  return agents.map(snapshot);
}

function getRunningAgentCount() {
  return _runningAgents().length;
}

function getRobotSignal() {
  const lastAgentId = lastRobotSignal.agentId;
  let active = null;
  if (lastAgentId) {
    active = agents.find((agent) => (
      agent.id === lastAgentId && (agent.state === 'running' || agent.state === 'busy')
    )) || null;
  }
  if (!active) {
    active = agents.find((agent) => agent.state === 'busy') || null;
  }
  if (!active) return { ...lastRobotSignal };
  const activeLocation = active.currentTask
    ? formatLocation('processing', active.currentTask.subsystem)
    : (active.location || lastRobotSignal.location || 'idle');
  return {
    agentId: active.id,
    agentName: active.name,
    taskId: active.currentTask ? active.currentTask.id : lastRobotSignal.taskId,
    subsystem: active.currentTask ? active.currentTask.subsystem : lastRobotSignal.subsystem,
    location: activeLocation,
    updatedAt: lastRobotSignal.updatedAt,
  };
}

function on(eventName, handler) {
  events.on(eventName, handler);
}

module.exports = {
  getAgents,
  enqueueTask,
  activateAgents,
  getRunningAgentCount,
  setMode,
  getMode,
  getRobotSignal,
  stopAllAgents,
  on,
};
