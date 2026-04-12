'use strict';

const { EventEmitter } = require('events');

const AGENT_CATALOG = [
  { id: 'ai-1', name: 'LeadAnalyzer', type: 'analysis', skills: ['general', 'memory'] },
  { id: 'ai-2', name: 'ResponseGen', type: 'generation', skills: ['general', 'nn'] },
  { id: 'ai-3', name: 'KnowledgeSearch', type: 'search', skills: ['general', 'memory'] },
  { id: 'ai-4', name: 'TaskRouter', type: 'routing', skills: ['general', 'doctor'] },
  { id: 'ai-5', name: 'DataExtractor', type: 'extraction', skills: ['general', 'memory', 'doctor'] },
  { id: 'ai-6', name: 'ReportBuilder', type: 'reporting', skills: ['general', 'nn', 'doctor'] },
];

// Simulated task processing duration bounds (per task execution).
// 1000-2800ms intentionally keeps end-to-end response under ~3s while remaining
// long enough for operators to observe queueing and state transitions in the UI.
const PROCESS_MS_MIN = 1000;
const PROCESS_MS_MAX = 2800;
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

function _taskDurationMs() {
  return Math.floor(Math.random() * (PROCESS_MS_MAX - PROCESS_MS_MIN + 1)) + PROCESS_MS_MIN;
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

function _findBestAgent(subsystem) {
  const running = _runningAgents().filter((a) => a.skills.includes(subsystem) || a.skills.includes('general'));
  if (running.length === 0) return null;

  return running
    .slice()
    .sort((a, b) => _agentLoad(a) - _agentLoad(b))[0];
}

function _agentLoad(agent) {
  return (agent.currentTask ? 1 : 0) + agent.taskQueue.length;
}

function _activateForDemand(subsystem) {
  const maxActive = _modeMaxActive();
  const active = _runningAgents().length;
  if (active >= maxActive) return;

  const candidate = agents.find(
    (a) =>
      a.state === 'idle' &&
      (a.skills.includes(subsystem) || a.skills.includes('general')),
  ) || agents.find((a) => a.state === 'idle');

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
      task.finishAt = now + _taskDurationMs();
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
    ? Math.max(0, Math.min(count, maxActive))
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
          error: `cancelled:${reason}`,
        },
        finishedAt: new Date().toISOString(),
      });
    }
    cancelledTasks += agent.taskQueue.length;
    agent.taskQueue = [];
    agent.currentTask = null;
    agent.location = 'idle';
    _deactivateAgent(agent);
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

function enqueueTask({ message, subsystem = 'general', metadata = {} }) {
  _activateForDemand(subsystem);
  if (_runningAgents().length === 0) {
    activateAgents(1);
  }

  let selected = _findBestAgent(subsystem);
  if (!selected) {
    selected = _findBestAgent(subsystem);
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
