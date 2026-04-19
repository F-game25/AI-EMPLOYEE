'use strict';

const { EventEmitter } = require('events');
const path = require('path');
const fs = require('fs');

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
  const configPath = path.resolve(__dirname, '../../runtime/config/agent_capabilities.json');
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

// Task processing duration bounds (per task execution).
// Base range 800-2400ms, scaled by agent–task affinity.
// More specialized agents execute faster within their domain.
const PROCESS_MS_MIN = 800;
const PROCESS_MS_MAX = 2400;
// Additional complexity multiplier range for tasks outside agent specialty.
const MISMATCH_PENALTY_MS = 600;
// Default assumed message length when task has no message (baseline complexity).
const DEFAULT_MSG_LENGTH = 40;
// Message length at which tasks are considered maximally complex.
const MSG_LENGTH_NORMALIZATION = 200;
// How long an inactive running agent waits before being scaled back to idle.
const IDLE_SCALE_DOWN_MS = 20000;
// Agent runtime scheduler frequency (persistent event-driven loop tick).
const LOOP_INTERVAL_MS = 250;

const AUTO_MIN_ACTIVE = 3;
const AUTO_ACTIVE_RATIO = 0.7;
const MANUAL_MIN_ACTIVE = 2;
const MANUAL_ACTIVE_RATIO = 0.4;
// MONEYMODE keeps more workers hot to support aggressive monetization templates.
const MONEYMODE_MIN_ACTIVE = 4;
const MONEYMODE_ACTIVE_RATIO = 0.85;
const HEALTH_DEGRADED_QUEUE_THRESHOLD = 3;
const MODES = {
  MANUAL: 'MANUAL',
  AUTO: 'AUTO',
  BLACKLIGHT: 'BLACKLIGHT',
  MONEYMODE: 'MONEYMODE',
};

const events = new EventEmitter();
let mode = MODES.MANUAL;
let desiredActiveAgents = 0;
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
  state: 'idle', // idle | running | busy
  health: 'healthy', // healthy | degraded | offline
  taskQueue: [],
  currentTask: null,
  location: 'idle',
  lastActivityAt: Date.now(),
  tasksCompleted: 0,
}));

function _now() {
  return Date.now();
}

function _modeMaxActive() {
  if (mode === MODES.BLACKLIGHT) return agents.length;
  if (mode === MODES.MONEYMODE) return Math.max(MONEYMODE_MIN_ACTIVE, Math.ceil(agents.length * MONEYMODE_ACTIVE_RATIO));
  if (mode === MODES.AUTO) return Math.max(AUTO_MIN_ACTIVE, Math.ceil(agents.length * AUTO_ACTIVE_RATIO));
  return Math.max(MANUAL_MIN_ACTIVE, Math.ceil(agents.length * MANUAL_ACTIVE_RATIO));
}

// Deterministic task duration model.
// Factors: base time + message length influence + subsystem affinity.
// Agent with matching skill → faster; mismatch → penalty.
function _taskDurationMs(agent, task) {
  const msgLen = (task && task.message) ? task.message.length : DEFAULT_MSG_LENGTH;
  // Base duration: scales linearly with message length (longer = more complex)
  const lengthFactor = Math.min(msgLen / MSG_LENGTH_NORMALIZATION, 1); // 0..1
  const base = PROCESS_MS_MIN + Math.round(lengthFactor * (PROCESS_MS_MAX - PROCESS_MS_MIN));
  // Affinity check: agent has relevant skill for this subsystem?
  const subsystem = (task && task.subsystem) || 'general';
  const hasSkill = agent && agent.skills && agent.skills.includes(subsystem);
  const penalty = hasSkill ? 0 : MISMATCH_PENALTY_MS;
  // Small deterministic jitter based on task sequence to avoid identical timings
  const jitter = ((_seq * 37) % 200) - 100; // -100..+100ms
  return Math.max(PROCESS_MS_MIN, base + penalty + jitter);
}

function _snapshot(agent) {
  return {
    id: agent.id,
    name: agent.name,
    type: agent.type,
    state: agent.state,
    health: agent.health,
    task: agent.currentTask ? agent.currentTask.message : null,
    queueSize: agent.taskQueue.length,
    tasksCompleted: agent.tasksCompleted,
    location: agent.location || 'idle',
    description: agent.description || '',
    capabilities: agent.capabilities || [],
  };
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

function _formatLocation(processingStage, subsystem) {
  return `${processingStage}:${subsystem || 'general'}`;
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

function _findBestAgent(subsystem, categoryHint) {
  const running = _runningAgents();
  if (running.length === 0) return null;

  // 1. Prefer agents whose category (type) matches the intent category hint.
  if (categoryHint) {
    const categoryMatched = running.filter((a) => a.type === categoryHint);
    if (categoryMatched.length > 0) {
      return categoryMatched.slice().sort((a, b) => _agentLoad(a) - _agentLoad(b))[0];
    }
  }

  // 2. Prefer agents with the specific subsystem skill (not just 'general').
  if (subsystem && subsystem !== 'general') {
    const specialists = running.filter((a) => a.skills.includes(subsystem));
    if (specialists.length > 0) {
      return specialists.slice().sort((a, b) => _agentLoad(a) - _agentLoad(b))[0];
    }
  }

  // 3. Fallback: least-loaded running agent.
  return running.slice().sort((a, b) => _agentLoad(a) - _agentLoad(b))[0];
}

function _agentLoad(agent) {
  return (agent.currentTask ? 1 : 0) + agent.taskQueue.length;
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
      agent.location = _formatLocation('completed', completedTask.subsystem);
      _updateRobotSignal(agent, {
        taskId: completedTask.id,
        subsystem: completedTask.subsystem || 'general',
        location: agent.location,
      });
      agent.health = 'healthy';
      const shouldFail = Boolean(completedTask?.metadata?.forceFail);
      if (shouldFail) {
        events.emit('task:failed', {
          agent: _snapshot(agent),
          task: {
            ...completedTask,
            error: 'forced_failure',
          },
          finishedAt: new Date().toISOString(),
        });
      } else {
        events.emit('task:completed', {
          agent: _snapshot(agent),
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
      task.finishAt = now + _taskDurationMs(agent, task);
      agent.currentTask = task;
      _setState(agent, 'busy');
      agent.location = _formatLocation('processing', task.subsystem);
      _updateRobotSignal(agent, {
        taskId: task.id,
        subsystem: task.subsystem || 'general',
        location: agent.location,
      });
      agent.health = task.queueDepth > HEALTH_DEGRADED_QUEUE_THRESHOLD ? 'degraded' : 'healthy';
      events.emit('task:started', {
        agent: _snapshot(agent),
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
        agent: _snapshot(agent),
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

  let selected = _findBestAgent(subsystem, categoryHint);
  if (!selected) {
    selected = _findBestAgent(subsystem, categoryHint);
  }
  if (!selected) {
    selected = agents
      .slice()
      .sort((a, b) => _agentLoad(a) - _agentLoad(b))[0];
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
  selected.location = _formatLocation('queued', subsystem);
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
  return agents.map(_snapshot);
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
    ? _formatLocation('processing', active.currentTask.subsystem)
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
