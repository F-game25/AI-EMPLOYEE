'use strict';

const http = require('http');
const os = require('os');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');

const gateway = require('./gateway');
const orchestrator = require('./orchestrator');
const broadcaster = require('./events/broadcaster');
const { SecretStore } = require('./security/secrets');
const { createOfflineSecuritySyncPolicy } = require('./security/offline_sync_policy');
const { createApiGatewayProtector } = require('./security/api_gateway');
const { createAnomalyResponder } = require('./security/anomaly_response');
const {
  getAgents,
  on: onAgentEvent,
  activateAgents,
  getRunningAgentCount,
  setMode,
  getMode,
  getRobotSignal,
  stopAllAgents,
} = require('./agents');
const subsystems = require('./subsystems');
const { buildMoneyTemplate, buildThinkingSummary } = require('./money_mode');
const brain = require('./brain/active_brain');
const persistence = require('./persistence');
const voiceManager = require('./core/voice_manager');

const PORT = process.env.PORT || 8787;
const PYTHON_BACKEND_HOST = '127.0.0.1';
const PYTHON_BACKEND_PORT = process.env.PYTHON_BACKEND_PORT || 8787;
const REPO_ROOT = path.resolve(__dirname, '..');
const FRONTEND_DIST = path.resolve(__dirname, '../frontend/dist');
const FRONTEND_INDEX = path.join(FRONTEND_DIST, 'index.html');
const HAS_FRONTEND_DIST = fs.existsSync(FRONTEND_INDEX);
const SERVER_START_TIMESTAMP = new Date().toISOString();
const FRONTEND_INDEX_TEMPLATE = HAS_FRONTEND_DIST ? fs.readFileSync(FRONTEND_INDEX, 'utf8') : '';

function latestCommit() {
  try {
    return execSync('git log -1 --oneline', { cwd: REPO_ROOT, encoding: 'utf8' }).trim();
  } catch (_err) {
    return 'unknown';
  }
}
const GIT_COMMIT = latestCommit();

const app = express();

app.use(cors());
app.use(express.json({ limit: '64kb' }));
if (HAS_FRONTEND_DIST) {
  app.use(express.static(FRONTEND_DIST, {
    index: false,
    maxAge: '1h',
  }));
}

app.use('/gateway', gateway);
app.use('/orchestrator', orchestrator.router);

const GPU_USAGE_BASELINE = 18;
let currentGpuUsage = GPU_USAGE_BASELINE;
// Incremented by broadcaster heartbeat loop; sampled into system status.
let heartbeatCounter = 0;

const GPU_RANDOM_SWING = 8;
const GPU_SWING_OFFSET = 4;
const GPU_CPU_BASELINE = 50;
const GPU_CPU_INFLUENCE = 0.03;
const CPU_TEMP_BASE = 35;
const CPU_TEMP_CPU_FACTOR = 0.58;
const CPU_TEMP_JITTER = 3;
const GPU_TEMP_BASE = 34;
const GPU_TEMP_GPU_FACTOR = 0.52;
const GPU_TEMP_JITTER = 4;
const MAX_ACTIVITY_ITEMS = 50;
const MAX_EXECUTION_LOGS = 100;
const MAX_DECISION_LOG_ENTRIES = 30;
const MAX_OBSERVABILITY_EVENTS = 300;
const BASE_PIPELINE_ROI = 250;
const PIPELINE_ROI_SWING = 400;
const REVENUE_CONVERSION_RATE = 0.45;
const CANCELLATION_ERROR_PREFIX = 'cancelled:';
// Experience scaling: tasks needed to reach maximum multiplier.
const EXPERIENCE_TASK_THRESHOLD = 20;
const MAX_EXPERIENCE_MULTIPLIER = 1.5;
// Deterministic variation seed for pipeline ROI (avoids Math.random).
const VARIATION_SEED = 41;
const OBJECTIVE_STATUS = {
  INACTIVE: 'inactive',
  WAITING: 'waiting',
  RUNNING: 'running',
  COMPLETED: 'completed',
};
const MONEY_MODE_AGENTS = ['lead_hunter', 'email_ninja', 'intel_agent', 'social_guru'];
const ASCEND_FORGE_AGENTS = ['intel_agent', 'email_ninja', 'social_guru'];
const OBJECTIVES_FILE = path.resolve(__dirname, '../state/objectives.json');
const MONEY_LEADS_PER_TASK = 5;
const MONEY_EMAILS_PER_TASK = 10;

const runtimeState = {
  automationRunning: false,
  tasksExecuted: 0,
  successfulTasks: 0,
  failedTasks: 0,
  valueGenerated: 0,
  revenueCents: 0,
  pipelineRuns: [],
  pipelineRoiTotal: 0,
  activityFeed: [],
  executionLogs: [],
  workflowRuns: [],
  workflowIndex: {},
  workflowTaskMeta: {},
  workflowSequencers: {},
  selectedWorkflowRun: null,
  skillStats: {},
  objectives: [],
  objectiveState: {
    money_mode: {
      active: false,
      status: OBJECTIVE_STATUS.INACTIVE,
      current_objective: null,
      active_tasks: [],
      progress: 0,
      agents_used: [],
      performance: { leads_generated: 0, emails_sent: 0, conversion_pct: 0 },
      result: null,
    },
    ascend_forge: {
      active: false,
      status: OBJECTIVE_STATUS.INACTIVE,
      current_objective: null,
      plan: [],
      active_tasks: [],
      progress: 0,
      agents_used: [],
      results: [],
      result: null,
    },
  },
  objectiveTaskMeta: {},
  observability: {
    events: [],
    autoFixLog: [],
    traces: {},
    _traceSeq: 0,
  },
  _seq: 0,
};

const bootVoiceState = {
  system_init: false,
  ai_core_ready: false,
  ui_loaded: false,
  triggered: false,
};
const BOOT_VOICE_FLAG = '__AI_EMPLOYEE_BOOT_VOICE_PLAYED';

function localGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour >= 5 && hour <= 11) return 'Good morning';
  if (hour >= 12 && hour <= 17) return 'Good afternoon';
  return 'Good evening';
}

async function maybeSpeakBootGreeting() {
  if (bootVoiceState.triggered || global[BOOT_VOICE_FLAG]) return;
  if (!bootVoiceState.system_init || !bootVoiceState.ai_core_ready || !bootVoiceState.ui_loaded) return;

  try {
    await voiceManager.init();
    if (!voiceManager.isBootGreetingEnabled()) {
      bootVoiceState.triggered = true;
      global[BOOT_VOICE_FLAG] = true;
      return;
    }
    bootVoiceState.triggered = true;
    global[BOOT_VOICE_FLAG] = true;
    await voiceManager.speak(`${localGreeting()}. Starting control panel.`, true);
  } catch (_err) {
    // best effort
  }
}

function markBootEvent(name) {
  if (!Object.prototype.hasOwnProperty.call(bootVoiceState, name)) return;
  bootVoiceState[name] = true;
  void maybeSpeakBootGreeting();
}

const secretStore = new SecretStore();
const securitySyncPolicy = createOfflineSecuritySyncPolicy({
  queueFile: path.resolve(__dirname, '../state/security_sync_queue.json'),
  historyFile: path.resolve(__dirname, '../state/security_sync_history.log'),
});
const apiGatewayProtector = createApiGatewayProtector({
  secretStore,
  syncPolicy: securitySyncPolicy,
  emitObservabilityEvent,
});
app.use('/api', apiGatewayProtector.middleware);
const anomalyResponder = createAnomalyResponder({
  sampleSnapshot: buildObservabilitySnapshot,
  getMode,
  setMode,
  stopAllAgents,
  addActivity,
  appendAutoFixLog,
  emitObservabilityEvent,
  gatewayProtector: apiGatewayProtector,
  syncPolicy: securitySyncPolicy,
});
setInterval(() => {
  try {
    anomalyResponder.evaluate();
  } catch (error) {
    console.warn('[SECURITY] anomaly responder evaluate failed:', error);
  }
}, 15000).unref();

// ── Restore persisted state on startup ────────────────────────────────────────
const _savedState = persistence.loadRuntimeState();
if (_savedState) {
  runtimeState.tasksExecuted = _savedState.tasksExecuted || 0;
  runtimeState.successfulTasks = _savedState.successfulTasks || 0;
  runtimeState.failedTasks = _savedState.failedTasks || 0;
  runtimeState.valueGenerated = _savedState.valueGenerated || 0;
  runtimeState.revenueCents = _savedState.revenueCents || 0;
  runtimeState.pipelineRoiTotal = _savedState.pipelineRoiTotal || 0;
  runtimeState.pipelineRuns = _savedState.pipelineRuns || [];
  runtimeState.activityFeed = _savedState.activityFeed || [];
  runtimeState.executionLogs = _savedState.executionLogs || [];
  runtimeState.skillStats = _savedState.skillStats || {};
  runtimeState.objectives = Array.isArray(_savedState.objectives) ? _savedState.objectives : [];
  runtimeState.objectiveState = _savedState.objectiveState || runtimeState.objectiveState;
  runtimeState.objectiveTaskMeta = _savedState.objectiveTaskMeta || {};
  console.log(`[PERSISTENCE] Restored state: ${runtimeState.tasksExecuted} tasks, $${(runtimeState.revenueCents / 100).toFixed(2)} revenue`);
}

try {
  if (fs.existsSync(OBJECTIVES_FILE)) {
    const persistedObjectives = JSON.parse(fs.readFileSync(OBJECTIVES_FILE, 'utf8'));
    if (Array.isArray(persistedObjectives)) {
      runtimeState.objectives = persistedObjectives;
    }
  }
} catch (error) {
  console.warn('[OBJECTIVES] Failed to read objective state:', error && error.message ? error.message : error);
}

const _savedBrain = persistence.loadBrainState();
if (_savedBrain) {
  brain.restoreState(_savedBrain);
  console.log('[PERSISTENCE] Restored brain state');
}
markBootEvent('system_init');

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function persistObjectives() {
  try {
    fs.mkdirSync(path.dirname(OBJECTIVES_FILE), { recursive: true });
    fs.writeFileSync(OBJECTIVES_FILE, JSON.stringify(runtimeState.objectives, null, 2), 'utf8');
  } catch {
    // best effort
  }
}

function broadcastObjectiveUpdate(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system,
    status: state.status,
    progress: state.progress || 0,
    current_objective: state.current_objective,
    active_tasks: state.active_tasks || [],
    plan: state.plan || [],
    agents_used: state.agents_used || [],
    results: state.results || state.result || [],
    performance: state.performance || {},
  });
}

function normalizeConstraints(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value;
}

function parseConstraintsFromGoal(goalText) {
  const text = String(goalText || '');
  const constraints = {};
  const lower = text.toLowerCase();
  const budgetTokenAt = lower.indexOf('budget');
  if (budgetTokenAt >= 0) {
    const numericBudget = lower.slice(budgetTokenAt).match(/\d+/);
    if (numericBudget) {
      constraints.budget = Math.min(Number(numericBudget[0]), Number.MAX_SAFE_INTEGER);
    }
  }
  const currencyBudget = text.match(/[€$]\s*(\d+)/);
  if (currencyBudget) {
    constraints.budget = Math.min(Number(currencyBudget[1]), Number.MAX_SAFE_INTEGER);
  }
  if (/\binstagram\b/i.test(text)) constraints.channel = 'instagram';
  if (/\bemail\b/i.test(text)) {
    constraints.channel = constraints.channel ? `${constraints.channel} + email` : 'email';
  }
  return constraints;
}

function createObjective({ system, goal, constraints = {}, priority = 'medium' }) {
  const objective = {
    id: `obj-${++runtimeState._seq}`,
    system,
    goal: String(goal || '').trim(),
    constraints: normalizeConstraints(constraints),
    priority: priority === 'high' ? 'high' : 'medium',
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  runtimeState.objectives.push(objective);
  runtimeState.objectives = runtimeState.objectives.slice(-200);
  persistObjectives();
  return objective;
}

function setObjectiveWaiting(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  state.active = true;
  state.status = OBJECTIVE_STATUS.WAITING;
  state.current_objective = null;
  state.progress = 0;
  state.active_tasks = [];
  state.result = null;
  if (system === 'ascend_forge') {
    state.plan = [];
    state.results = [];
  }
  broadcastObjectiveUpdate(system);
}

function breakdownMoneyModeGoal(goal) {
  const g = String(goal || '').toLowerCase();
  const tasks = [];
  if (/\blead/.test(g)) tasks.push('find leads', 'qualify leads');
  if (/\bemail|outreach/.test(g)) tasks.push('write outreach emails', 'prepare campaign');
  if (/\binstagram|social/.test(g)) tasks.push('prepare instagram campaign');
  if (/\bconversion|funnel/.test(g)) tasks.push('analyze conversion blockers');
  if (tasks.length === 0) {
    tasks.push('find leads', 'qualify leads', 'write outreach emails', 'prepare campaign');
  }
  return [...new Set(tasks)];
}

function buildAscendForgePlan(goal) {
  const g = String(goal || '').toLowerCase();
  const plan = ['analyze baseline', 'identify bottlenecks'];
  if (/\bconversion|funnel/.test(g)) {
    plan.push('design conversion experiments', 'execute funnel optimization');
  } else {
    plan.push('define optimization plan', 'execute improvement sprint');
  }
  return plan;
}

function addActivity(notes, kind = 'system') {
  const item = {
    id: `activity-${++runtimeState._seq}`,
    kind,
    notes,
    ts: new Date().toISOString(),
  };
  runtimeState.activityFeed.unshift(item);
  runtimeState.activityFeed = runtimeState.activityFeed.slice(0, MAX_ACTIVITY_ITEMS);
  // Broadcast immediately so UI gets real-time updates without polling
  broadcaster.broadcast('activity:item', item);
}

function emitObservabilityEvent(eventType, payload = {}) {
  const event = {
    id: `obs-${++runtimeState._seq}`,
    ts: new Date().toISOString(),
    event_type: eventType,
    payload,
    trace_id: payload.trace_id || '',
  };
  runtimeState.observability.events.unshift(event);
  runtimeState.observability.events = runtimeState.observability.events.slice(0, MAX_OBSERVABILITY_EVENTS);
  broadcaster.broadcast('event_stream', event);
  if (isSecurityEventType(eventType)) {
    securitySyncPolicy.enqueueEvent(eventType, payload);
  }
  return event;
}

function isSecurityEventType(eventType) {
  return (
    eventType === 'honeypot_triggered'
    || eventType === 'anomaly_response'
    || String(eventType).startsWith('security_')
  );
}

function appendAutoFixLog(entry) {
  const row = {
    id: `autofix-${++runtimeState._seq}`,
    ts: new Date().toISOString(),
    ...entry,
  };
  runtimeState.observability.autoFixLog.unshift(row);
  runtimeState.observability.autoFixLog = runtimeState.observability.autoFixLog.slice(0, MAX_ACTIVITY_ITEMS);
  emitObservabilityEvent('auto_fix_applied', row);
  return row;
}

function createWorkflowRun({ name, source = 'automation', goal = '' }) {
  const runId = `wf-${++runtimeState._seq}`;
  const run = {
    run_id: runId,
    name: name || `Workflow ${runId}`,
    source,
    goal,
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    progress_percent: 0,
    nodes: [],
    decision_log: [],
  };
  runtimeState.workflowRuns.unshift(run);
  runtimeState.workflowRuns = runtimeState.workflowRuns.slice(0, MAX_ACTIVITY_ITEMS);
  runtimeState.selectedWorkflowRun = runId;
  broadcaster.broadcast('workflow:update', run);
  return run;
}

function appendDecision(run, entry) {
  run.decision_log.unshift(entry);
  run.decision_log = run.decision_log.slice(0, MAX_DECISION_LOG_ENTRIES);
}

function getWorkflowRun(runId) {
  return runtimeState.workflowRuns.find((run) => run.run_id === runId) || null;
}

function attachWorkflowNode({ runId, queued, taskName, parentTaskId = null }) {
  const run = getWorkflowRun(runId);
  if (!run || !queued || !queued.taskId) return;
  const node = {
    task_id: queued.taskId,
    task_name: taskName || queued.subsystem || 'Task',
    status: 'pending',
    progress_percent: 5,
    subsystem: queued.subsystem || 'general',
    agent: queued.agentId || 'pending',
    queued_at: queued.queuedAt || new Date().toISOString(),
    started_at: null,
    completed_at: null,
    parent_task_id: parentTaskId,
    brain: queued.brain || null,
    strategy: queued.brain ? queued.brain.strategy : null,
    confidence: queued.brain ? queued.brain.confidence : null,
    reasoning: queued.brain ? queued.brain.reasoning : '',
    execution_flow: queued.brain ? queued.brain.execution_flow : 'task->strategy->agent->action->result',
    result: null,
  };
  run.nodes.push(node);
  appendDecision(run, {
    ts: new Date().toISOString(),
    task_id: node.task_id,
    type: 'brain_decision',
    summary: node.reasoning || `Strategy ${node.strategy || 'default'} selected`,
  });
  runtimeState.workflowIndex[node.task_id] = runId;
  run.updated_at = new Date().toISOString();
  run.status = 'running';
  recalcWorkflowProgress(run);
  broadcaster.broadcast('workflow:update', run);
}

function recalcWorkflowProgress(run) {
  const total = run.nodes.length || 1;
  let acc = 0;
  let completed = 0;
  let failed = 0;
  run.nodes.forEach((node) => {
    acc += Number(node.progress_percent || 0);
    if (node.status === 'completed') completed += 1;
    if (node.status === 'failed') failed += 1;
  });
  run.progress_percent = Math.round(acc / total);
  if (failed > 0) {
    run.status = completed > 0 ? 'completed_with_failures' : 'failed';
  } else if (completed === run.nodes.length && run.nodes.length > 0) {
    run.status = 'completed';
    run.progress_percent = 100;
  } else if (run.nodes.length > 0) {
    run.status = 'running';
  } else {
    run.status = 'pending';
  }
}

function updateWorkflowNode(taskId, updater) {
  const runId = runtimeState.workflowIndex[taskId];
  if (!runId) return;
  const run = getWorkflowRun(runId);
  if (!run) return;
  const node = run.nodes.find((n) => n.task_id === taskId);
  if (!node) return;
  updater(node, run);
  run.updated_at = new Date().toISOString();
  recalcWorkflowProgress(run);
  broadcaster.broadcast('workflow:update', run);
}

function markWorkflowsStopped() {
  runtimeState.workflowRuns.forEach((run) => {
    if (!['running', 'pending'].includes(run.status)) return;
    run.nodes.forEach((node) => {
      if (node.status === 'pending' || node.status === 'active') {
        node.status = 'failed';
        node.progress_percent = 100;
        node.completed_at = new Date().toISOString();
        node.result = {
          status: 'cancelled',
          summary: 'Cancelled by STOP ALL command',
        };
      }
    });
    run.updated_at = new Date().toISOString();
    recalcWorkflowProgress(run);
    run.status = 'stopped';
    broadcaster.broadcast('workflow:update', run);
  });
}

function queueWorkflowStep({
  runId,
  message,
  stepIndex = 0,
  labels = [],
  parentTaskId = null,
  retries = 0,
  maxRetries = 1,
}) {
  const queued = orchestrator.submitTask(message, {
    userId: 'user:default',
    workflow: { runId, parentTaskId },
    labels,
  });
  attachWorkflowNode({
    runId,
    queued,
    taskName: message,
    parentTaskId,
  });
  runtimeState.workflowTaskMeta[queued.taskId] = {
    runId,
    stepIndex,
    message,
    labels,
    parentTaskId,
    retries,
    maxRetries,
  };
  const seq = runtimeState.workflowSequencers[runId];
  if (seq) {
    seq.stepTaskIds[stepIndex] = queued.taskId;
  }
  addActivity(`[BRAIN] Strategy ${queued.brain?.strategy || 'default'} selected for ${queued.taskId}`, 'task');
  const traceId = `trace-${++runtimeState.observability._traceSeq}`;
  runtimeState.observability.traces[queued.taskId] = {
    trace_id: traceId,
    user_input: message,
    intent: queued.brain?.intent || queued.subsystem || 'general',
    agent: queued.agentId || 'task_orchestrator',
    strategy: queued.brain?.strategy || 'default',
    confidence: queued.brain?.confidence || 0,
    started_at: new Date().toISOString(),
    steps: [],
  };
  emitObservabilityEvent('task_started', {
    trace_id: traceId,
    task_id: queued.taskId,
    user_input: message,
    intent: queued.brain?.intent || queued.subsystem || 'general',
  });
  emitObservabilityEvent('agent_selected', {
    trace_id: traceId,
    task_id: queued.taskId,
    agent: queued.agentId || 'task_orchestrator',
  });
  emitObservabilityEvent('brain_decision', {
    trace_id: traceId,
    task_id: queued.taskId,
    strategy: queued.brain?.strategy || 'default',
    reasoning: queued.brain?.reasoning || '',
    confidence: queued.brain?.confidence || 0,
  });
  return queued;
}

function queueNextWorkflowStep(completedTaskId) {
  const meta = runtimeState.workflowTaskMeta[completedTaskId];
  if (!meta) return;
  const seq = runtimeState.workflowSequencers[meta.runId];
  if (!seq || seq.stopped) return;
  if (seq.stepTaskIds[meta.stepIndex] !== completedTaskId) return;
  seq.completedSteps.add(meta.stepIndex);
  const nextIndex = meta.stepIndex + 1;
  const nextMessage = seq.messages[nextIndex];
  if (!nextMessage || seq.queuedSteps.has(nextIndex)) return;
  seq.queuedSteps.add(nextIndex);
  queueWorkflowStep({
    runId: meta.runId,
    message: nextMessage,
    stepIndex: nextIndex,
    labels: ['automation', `step-${nextIndex + 1}`],
    parentTaskId: completedTaskId,
  });
}

function retryWorkflowStep(failedTaskId) {
  const meta = runtimeState.workflowTaskMeta[failedTaskId];
  if (!meta) return false;
  if (meta.error?.startsWith(CANCELLATION_ERROR_PREFIX)) return false;
  const seq = runtimeState.workflowSequencers[meta.runId];
  if (!seq || seq.stopped) return false;
  if (seq.stepTaskIds[meta.stepIndex] !== failedTaskId) return false;
  if (meta.retries >= meta.maxRetries) return false;
  const retryNumber = meta.retries + 1;
  addActivity(`[RETRY] ${failedTaskId} retry ${retryNumber}/${meta.maxRetries}`, 'task');
  appendAutoFixLog({
    task_id: failedTaskId,
    issue: meta.error || 'task failure',
    fix: `Automatic retry ${retryNumber}/${meta.maxRetries}`,
    status: 'retrying',
  });
  queueWorkflowStep({
    runId: meta.runId,
    message: meta.message,
    stepIndex: meta.stepIndex,
    labels: [...meta.labels, `retry-${retryNumber}`],
    parentTaskId: meta.parentTaskId,
    retries: retryNumber,
    maxRetries: meta.maxRetries,
  });
  return true;
}

function recalcObjectiveProgress(system) {
  const state = runtimeState.objectiveState[system];
  if (!state) return;
  const tasks = state.active_tasks || [];
  const total = tasks.length || 1;
  const completed = tasks.filter((t) => t.status === 'completed').length;
  const failed = tasks.filter((t) => t.status === 'failed').length;
  state.progress = Math.round(((completed + failed) / total) * 100);
  if (tasks.length > 0 && (completed + failed) === tasks.length) {
    state.status = OBJECTIVE_STATUS.COMPLETED;
    state.active = false;
  } else if (tasks.length > 0) {
    state.status = OBJECTIVE_STATUS.RUNNING;
  }
}

function startMoneyModeObjective(objective) {
  if (!objective || !objective.goal) {
    setObjectiveWaiting('money_mode');
    return { ok: false, message: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.' };
  }
  objective.status = 'running';
  objective.updated_at = new Date().toISOString();
  persistObjectives();

  setMode('MONEYMODE');
  activateAgents(4);

  const tasks = breakdownMoneyModeGoal(objective.goal);
  const run = createWorkflowRun({
    name: 'Money Mode Objective',
    source: 'money_mode',
    goal: objective.goal,
  });
  runtimeState.objectiveState.money_mode = {
    ...runtimeState.objectiveState.money_mode,
    active: true,
    status: OBJECTIVE_STATUS.RUNNING,
    current_objective: objective,
    active_tasks: [],
    progress: 0,
    agents_used: MONEY_MODE_AGENTS,
    performance: {
      leads_generated: 0,
      emails_sent: 0,
      conversion_pct: 0,
    },
    result: null,
  };

  tasks.forEach((task, idx) => {
    const agentHint = MONEY_MODE_AGENTS[idx % MONEY_MODE_AGENTS.length];
    const queued = queueWorkflowStep({
      runId: run.run_id,
      message: `[${agentHint}] ${task}`,
      stepIndex: idx,
      labels: ['money_mode', `step-${idx + 1}`],
      parentTaskId: idx > 0 ? runtimeState.objectiveState.money_mode.active_tasks[idx - 1]?.task_id || null : null,
    });
    runtimeState.objectiveTaskMeta[queued.taskId] = {
      system: 'money_mode',
      objective_id: objective.id,
      task_name: task,
      agent_hint: agentHint,
    };
    runtimeState.objectiveState.money_mode.active_tasks.push({
      task_id: queued.taskId,
      task,
      agent: agentHint,
      status: 'pending',
    });
  });
  broadcastObjectiveUpdate('money_mode');
  addActivity(`[MONEY MODE] objective started • ${objective.goal}`, 'automation');
  return { ok: true, message: `✅ Money Mode objective started: ${objective.goal}` };
}

function startAscendForgeObjective(objective) {
  if (!objective || !objective.goal) {
    setObjectiveWaiting('ascend_forge');
    return { ok: false, message: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.' };
  }
  objective.status = 'running';
  objective.updated_at = new Date().toISOString();
  persistObjectives();

  activateAgents(3);
  const plan = buildAscendForgePlan(objective.goal);
  const run = createWorkflowRun({
    name: 'Ascend Forge Objective',
    source: 'ascend_forge',
    goal: objective.goal,
  });

  runtimeState.objectiveState.ascend_forge = {
    ...runtimeState.objectiveState.ascend_forge,
    active: true,
    status: OBJECTIVE_STATUS.RUNNING,
    current_objective: objective,
    plan,
    active_tasks: [],
    progress: 0,
    agents_used: ASCEND_FORGE_AGENTS,
    results: [],
    result: {
      plan,
      agents_used: ASCEND_FORGE_AGENTS,
      progress: 0,
      status: 'running',
    },
  };

  plan.forEach((step, idx) => {
    const agentHint = ASCEND_FORGE_AGENTS[idx % ASCEND_FORGE_AGENTS.length];
    const queued = queueWorkflowStep({
      runId: run.run_id,
      message: `[${agentHint}] ${step}`,
      stepIndex: idx,
      labels: ['ascend_forge', `step-${idx + 1}`],
      parentTaskId: idx > 0 ? runtimeState.objectiveState.ascend_forge.active_tasks[idx - 1]?.task_id || null : null,
    });
    runtimeState.objectiveTaskMeta[queued.taskId] = {
      system: 'ascend_forge',
      objective_id: objective.id,
      task_name: step,
      agent_hint: agentHint,
    };
    runtimeState.objectiveState.ascend_forge.active_tasks.push({
      task_id: queued.taskId,
      task: step,
      agent: agentHint,
      status: 'pending',
    });
  });
  broadcastObjectiveUpdate('ascend_forge');
  addActivity(`[ASCEND FORGE] objective started • ${objective.goal}`, 'automation');
  return { ok: true, message: `✅ Ascend Forge objective started: ${objective.goal}` };
}

function handleGoalDrivenCommand(message) {
  const raw = String(message || '').trim();
  const msg = raw.toLowerCase();
  if (!raw) return { handled: false };

  if (msg === 'activate money mode') {
    setMode('MONEYMODE');
    setObjectiveWaiting('money_mode');
    return {
      handled: true,
      reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.',
    };
  }

  const setMoneyPrefix = 'set goal for money mode:';
  if (msg.startsWith(setMoneyPrefix)) {
    const goal = raw.slice(setMoneyPrefix.length).trim();
    if (!goal) {
      setObjectiveWaiting('money_mode');
      return {
        handled: true,
        reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.',
      };
    }
    const objective = createObjective({
      system: 'money_mode',
      goal,
      constraints: parseConstraintsFromGoal(goal),
      priority: 'high',
    });
    const started = startMoneyModeObjective(objective);
    return { handled: true, reply: started.message };
  }

  const startAscendPrefix = 'start ascend forge with goal:';
  if (msg.startsWith(startAscendPrefix)) {
    const goal = raw.slice(startAscendPrefix.length).trim();
    if (!goal) {
      setObjectiveWaiting('ascend_forge');
      return {
        handled: true,
        reply: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.',
      };
    }
    const objective = createObjective({
      system: 'ascend_forge',
      goal,
      constraints: parseConstraintsFromGoal(goal),
      priority: 'high',
    });
    const started = startAscendForgeObjective(objective);
    return { handled: true, reply: started.message };
  }

  return { handled: false };
}

function recordExecution({ taskId, skill, status, notes }) {
  const logItem = {
    id: `exec-${++runtimeState._seq}`,
    task_id: taskId,
    skill,
    status,
    notes,
    ts: new Date().toISOString(),
  };
  runtimeState.executionLogs.unshift(logItem);
  runtimeState.executionLogs = runtimeState.executionLogs.slice(0, MAX_EXECUTION_LOGS);
  runtimeState.tasksExecuted += 1;
  if (status === 'success') runtimeState.successfulTasks += 1;
  if (status === 'failed') runtimeState.failedTasks += 1;
  runtimeState.skillStats[skill] = runtimeState.skillStats[skill] || { runs: 0, success: 0 };
  runtimeState.skillStats[skill].runs += 1;
  if (status === 'success') runtimeState.skillStats[skill].success += 1;
  // Broadcast so the UI execution log updates in real time
  broadcaster.broadcast('execution:log', logItem);
}

// Pipeline ROI estimation based on actual execution metrics.
// Uses: success rate, tasks completed, pipeline type multiplier.
const PIPELINE_MULTIPLIER = {
  content: 1.0,      // Content pipelines: moderate, steady ROI
  lead: 1.4,         // Lead gen: high value per qualified lead
  opportunity: 1.8,  // Opportunity conversion: highest value per close
};

function estimatePipelineRoi(pipelineName) {
  const successRate = runtimeState.tasksExecuted > 0
    ? runtimeState.successfulTasks / runtimeState.tasksExecuted
    : 0.5;
  const multiplier = PIPELINE_MULTIPLIER[pipelineName] || 1.0;
  // Base ROI scales with actual success rate and cumulative experience
  const experienceFactor = Math.min(runtimeState.tasksExecuted / EXPERIENCE_TASK_THRESHOLD, MAX_EXPERIENCE_MULTIPLIER); // improves with usage
  const baseRoi = BASE_PIPELINE_ROI * successRate * multiplier * Math.max(experienceFactor, 0.5);
  // Deterministic variation based on pipeline run count (no Math.random)
  const variation = ((runtimeState.pipelineRuns.length * VARIATION_SEED) % PIPELINE_ROI_SWING) - (PIPELINE_ROI_SWING / 4);
  return Math.max(50, Math.round(baseRoi + variation));
}

function runPipeline(pipelineName) {
  const estimatedRoi = estimatePipelineRoi(pipelineName);
  const run = {
    id: `pipeline-${++runtimeState._seq}`,
    pipeline: pipelineName,
    status: 'completed',
    estimated_roi: estimatedRoi,
    executed_at: new Date().toISOString(),
  };
  runtimeState.pipelineRuns.unshift(run);
  runtimeState.pipelineRuns = runtimeState.pipelineRuns.slice(0, MAX_ACTIVITY_ITEMS);
  runtimeState.pipelineRoiTotal += estimatedRoi;
  runtimeState.valueGenerated += estimatedRoi;
  runtimeState.revenueCents += Math.round(estimatedRoi * REVENUE_CONVERSION_RATE * 100);
  addActivity(`[PIPELINE] ${pipelineName} completed • ROI $${estimatedRoi}`, 'pipeline');
  return run;
}

function buildDashboardPayload() {
  const successRate = runtimeState.tasksExecuted > 0
    ? runtimeState.successfulTasks / runtimeState.tasksExecuted
    : 0;
  const topSkills = Object.entries(runtimeState.skillStats)
    .map(([skill, stats]) => ({
      skill,
      runs: stats.runs,
      success_rate: stats.runs > 0 ? stats.success / stats.runs : 0,
    }))
    .sort((a, b) => b.runs - a.runs)
    .slice(0, 8);

  return {
    mode: {
      current: getMode(),
      automation_running: runtimeState.automationRunning,
    },
    tasks: {
      tasks_executed: runtimeState.tasksExecuted,
      success_rate: successRate,
      successful_tasks: runtimeState.successfulTasks,
      failed_tasks: runtimeState.failedTasks,
    },
    value: {
      value_generated: runtimeState.valueGenerated,
      components: {
        pipelines: runtimeState.pipelineRoiTotal,
      },
    },
    revenue: {
      total_revenue: runtimeState.revenueCents / 100,
    },
    top_skills: topSkills,
    activity_feed: runtimeState.activityFeed,
    execution_logs: runtimeState.executionLogs,
    workflow_runs: runtimeState.workflowRuns,
    workflow_focus: runtimeState.selectedWorkflowRun,
    pipelines: {
      total_estimated_roi: runtimeState.pipelineRoiTotal,
      runs: runtimeState.pipelineRuns.length,
    },
    pipeline_runs: runtimeState.pipelineRuns,
    pending_actions: [],
    learning: {
      mode: getMode(),
      brain: brain.insights(),
    },
    self_improvement: subsystems.getSelfImprovementStatus(),
    objective_systems: runtimeState.objectiveState,
  };
}

function cpuUsagePercent() {
  const cpus = os.cpus().length || 1;
  const load = os.loadavg()[0];
  return clamp(Math.round((load / cpus) * 100), 0, 100);
}

function memoryUsagePercent() {
  const total = os.totalmem();
  const free = os.freemem();
  if (!total) return 0;
  return clamp(Math.round(((total - free) / total) * 100), 0, 100);
}

let _sampleSeq = 0; // Monotonic counter for deterministic GPU/temp estimation.
function sampleSystemStatus() {
  _sampleSeq += 1;
  const cpu = cpuUsagePercent();
  const memory = memoryUsagePercent();
  // Deterministic swing using sinusoidal wave (no Math.random).
  const deterministicSwing = Math.sin(_sampleSeq * 0.7) * GPU_SWING_OFFSET;
  const cpuInfluence = (cpu - GPU_CPU_BASELINE) * GPU_CPU_INFLUENCE;
  // Intentionally mutates currentGpuUsage to simulate gradual GPU trend across snapshots.
  currentGpuUsage = clamp(
    Math.round(currentGpuUsage + deterministicSwing + cpuInfluence),
    4,
    97,
  );
  // Deterministic temperature jitter via modular arithmetic (no Math.random).
  const cpuTempJitter = ((_sampleSeq * 31) % (CPU_TEMP_JITTER + 1));
  const gpuTempJitter = ((_sampleSeq * 47) % (GPU_TEMP_JITTER + 1));
  const cpuTemp = clamp(Math.round(CPU_TEMP_BASE + cpu * CPU_TEMP_CPU_FACTOR + cpuTempJitter), 32, 95);
  const gpuTemp = clamp(Math.round(GPU_TEMP_BASE + currentGpuUsage * GPU_TEMP_GPU_FACTOR + gpuTempJitter), 30, 90);

  const total = getAgents().length;
  const running = getRunningAgentCount();
  const mode = getMode();
  const robotSignal = getRobotSignal();
  const thinkingTemplate = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: running,
    totalAgents: total,
  });
  const thinkingSummary = buildThinkingSummary(mode, thinkingTemplate, robotSignal);

  return {
    cpu,
    memory,
    uptime: process.uptime(),
    connections: wss ? wss.clients.size : 0,
    cpu_usage: cpu,
    gpu_usage: currentGpuUsage,
    gpu_estimated: true,
    cpu_temperature: cpuTemp,
    gpu_temperature: gpuTemp,
    temperature_estimated: true,
    heartbeat: heartbeatCounter,
    running_agents: running,
    total_agents: total,
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    active_robot: robotSignal && robotSignal.agentName ? `${robotSignal.agentName} (${robotSignal.agentId || 'n/a'})` : 'none',
    active_subsystem: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general',
    thinking_mode: thinkingSummary,
    money_template: mode === 'MONEYMODE' ? thinkingTemplate.template : null,
    money_mode_panel: runtimeState.objectiveState.money_mode,
    ascend_forge_panel: runtimeState.objectiveState.ascend_forge,
    timestamp: new Date().toISOString(),
  };
}

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() });
});

app.get('/version', (req, res) => {
  res.set('Cache-Control', 'no-store, must-revalidate');
  res.json({
    commit: GIT_COMMIT,
    timestamp: new Date().toISOString(),
    started_at: SERVER_START_TIMESTAMP,
    cwd: process.cwd(),
    file: __filename,
  });
});

app.get('/agents', (req, res) => {
  res.json({ agents: getAgents() });
});

app.get('/internal/agents', (req, res) => {
  res.json({ agents: getAgents(), internal: true });
});

app.post('/agents/activate', (req, res) => {
  const { count } = req.body || {};
  const out = activateAgents(typeof count === 'number' ? count : undefined);
  res.json({ ok: true, ...out, mode: getMode(), agents: getAgents() });
});

app.get('/status', (req, res) => {
  const stats = sampleSystemStatus();
  res.json({ status: 'online', agents: stats.total_agents, running_agents: stats.running_agents, timestamp: stats.timestamp });
});

// ── Subsystem API endpoints ───────────────────────────────────────────────────

app.get('/api/system/stats', (req, res) => {
  res.json(sampleSystemStatus());
});

function buildObservabilitySnapshot() {
  const stats = sampleSystemStatus();
  const events = runtimeState.observability.events || [];
  const nowTs = Date.now();
  const recentErrorEvents = events.filter((item) => item.event_type === 'error_detected');
  const errorsPerMinute = recentErrorEvents.filter((item) => (nowTs - Date.parse(item.ts)) <= 60000).length;
  const recentTaskEvents = events.filter((item) => item.event_type === 'task_completed' || item.event_type === 'task_started');
  const tasksPerMinute = recentTaskEvents.filter((item) => (nowTs - Date.parse(item.ts)) <= 60000).length;
  const latestLogs = runtimeState.executionLogs.slice(0, 20);
  const avgLatency = latestLogs.length
    ? Math.round(latestLogs.reduce((acc, row) => acc + (Number(row.duration_ms || 0) || 0), 0) / latestLogs.length)
    : 0;
  return {
    system_health: {
      uptime: stats.uptime,
      errors_per_minute: errorsPerMinute,
      status: errorsPerMinute > 3 ? 'degraded' : 'healthy',
    },
    metrics: {
      tasks_per_minute: tasksPerMinute,
      errors_per_minute: errorsPerMinute,
      latency_ms: avgLatency,
      cpu_percent: stats.cpu_usage,
      memory_percent: stats.memory,
      queue_depth: runtimeState.workflowRuns.filter((run) => run.status === 'pending').length,
    },
    activity_feed: runtimeState.activityFeed,
    agent_grid: getAgents().map((agent) => ({
      id: agent.id,
      name: agent.name,
      status: agent.status || 'idle',
    })),
    queue_visualizer: {
      pending: runtimeState.workflowRuns.filter((run) => run.status === 'pending').length,
      processing: runtimeState.workflowRuns.filter((run) => run.status === 'running').length,
    },
    auto_fix_log: runtimeState.observability.autoFixLog || [],
    events: events.slice(0, 200),
    traces: runtimeState.observability.traces,
    security: {
      gateway: apiGatewayProtector.status(),
      sync: securitySyncPolicy.status(),
      anomaly_response: anomalyResponder.status(),
    },
    updated_at: new Date().toISOString(),
  };
}

app.get('/api/observability/snapshot', (req, res) => {
  res.json(buildObservabilitySnapshot());
});

app.get('/api/observability/events', (req, res) => {
  res.json({ events: (runtimeState.observability.events || []).slice(0, 200) });
});

app.get('/api/security/aztsa/status', (req, res) => {
  const requiredSecrets = [
    secretStore.describe('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] }),
    secretStore.describe('JWT_SECRET', { aliases: ['JWT_SECRET_KEY'] }),
  ];
  res.json({
    gateway: apiGatewayProtector.status(),
    secret_health: {
      required: requiredSecrets,
      missing: requiredSecrets.filter((item) => !item.configured).map((item) => item.name),
    },
    anomaly_response: anomalyResponder.status(),
    offline_security_sync: securitySyncPolicy.status(),
    honeypot: {
      events: apiGatewayProtector.recentHoneypot(20),
    },
    updated_at: new Date().toISOString(),
  });
});

app.get('/api/security/honeypot/events', (req, res) => {
  const limitRaw = Number((req.query || {}).limit || 50);
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(200, limitRaw)) : 50;
  res.json({
    events: apiGatewayProtector.recentHoneypot(limit),
    total: apiGatewayProtector.status().honeypot_events,
  });
});

app.post('/api/security/offline-sync', (req, res) => {
  const body = req.body || {};
  const online = body.online !== false;
  const state = securitySyncPolicy.setOnline(online);
  res.json({
    status: state,
    applied_online: online,
  });
});

app.post('/api/security/anomaly/evaluate', (req, res) => {
  const result = anomalyResponder.evaluate();
  res.json(result);
});

app.post('/api/security/gateway/strict-mode', (req, res) => {
  const enabled = Boolean((req.body || {}).enabled);
  const strict = apiGatewayProtector.setStrictMode(enabled, 'manual_override');
  res.json({
    strict_mode: strict,
    gateway: apiGatewayProtector.status(),
  });
});

app.get('/api/mode', (req, res) => {
  const mode = getMode();
  const robotSignal = getRobotSignal();
  const template = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: getRunningAgentCount(),
    totalAgents: getAgents().length,
  });
  res.json({
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    thinking_mode: buildThinkingSummary(mode, template, robotSignal),
    money_template: mode === 'MONEYMODE' ? template : null,
  });
});

app.post('/api/mode', (req, res) => {
  const next = String((req.body || {}).mode || '').toUpperCase();
  const mode = setMode(next);
  if (mode === 'MONEYMODE' && !runtimeState.objectiveState.money_mode.current_objective) {
    setObjectiveWaiting('money_mode');
  }
  const robotSignal = getRobotSignal();
  const template = buildMoneyTemplate({
    message: robotSignal && robotSignal.subsystem ? robotSignal.subsystem : 'general orchestration',
    subsystem: robotSignal ? robotSignal.subsystem : 'general',
    mode,
    runningAgents: getRunningAgentCount(),
    totalAgents: getAgents().length,
  });
  res.json({
    mode,
    robot_location: robotSignal && robotSignal.location ? robotSignal.location : 'idle',
    thinking_mode: buildThinkingSummary(mode, template, robotSignal),
    money_template: mode === 'MONEYMODE' ? template : null,
  });
});

app.get('/api/brain/status', (req, res) => {
  const nn = subsystems.getNNStatus();
  const core = brain.status();
  res.json({
    ...nn,
    ...core,
    updated_at: nn.updated_at || core.last_update || new Date().toISOString(),
  });
});

app.get('/internal/brain/status', (req, res) => {
  const core = brain.status() || {};
  const insights = brain.insights() || {};
  const strategies = Array.isArray(insights.learned_strategies) ? insights.learned_strategies.length : 0;
  const active = Boolean(core.available && core.active);
  res.json({
    status: active ? 'online' : 'offline',
    initialized: active,
    strategies_loaded: strategies,
    updated_at: core.last_update || insights.updated_at || new Date().toISOString(),
  });
});

app.get('/api/brain/insights', (req, res) => {
  res.json(brain.insights());
});

app.get('/api/brain/activity', (req, res) => {
  const limit = Number(req.query.limit || 20);
  res.json(brain.activity(limit));
});

app.get('/api/brain/neurons', (req, res) => {
  res.json(brain.neurons());
});

app.get('/api/memory/tree', (req, res) => {
  res.json(subsystems.getMemoryTree());
});

app.get('/api/doctor/status', (req, res) => {
  res.json(subsystems.getDoctorStatus());
});

app.get('/api/self-improvement/status', (req, res) => {
  res.json(subsystems.getSelfImprovementStatus());
});

// ── Autonomy daemon endpoints ─────────────────────────────────────────────────

app.get('/api/autonomy/status', (req, res) => {
  res.json(subsystems.getAutonomyStatus());
});

app.get('/api/autonomy/mode', (req, res) => {
  const auto = subsystems.getAutonomyStatus();
  res.json(auto.mode || { mode: 'OFF', active: false });
});

function requestPythonJSON(pathname, method = 'GET', payload = null) {
  return new Promise((resolve, reject) => {
    const httpLib = require('http');
    const safePath = String(pathname || '/').trim();
    if (!safePath.startsWith('/api/') || safePath.includes('..')) {
      return reject(new Error('invalid_path'));
    }
    const body = payload ? JSON.stringify(payload) : null;
    const req = httpLib.request(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}${safePath}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } : {},
      timeout: 3000,
    }, (response) => {
      let text = '';
      response.on('data', (chunk) => { text += chunk; });
      response.on('end', () => {
        try {
          resolve(JSON.parse(text || '{}'));
        } catch {
          resolve({});
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('timeout'));
    });
    if (body) req.write(body);
    req.end();
  });
}

app.post('/api/autonomy/mode', async (req, res) => {
  const nextMode = String((req.body || {}).mode || '').toUpperCase();
  if (!['OFF', 'ON', 'AUTO'].includes(nextMode)) {
    return res.status(400).json({ error: 'Invalid mode. Use OFF, ON, or AUTO.' });
  }
  // Proxy to Python backend
  try {
    const data = await new Promise((resolve, reject) => {
      const payload = JSON.stringify({ mode: nextMode });
      const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/mode`;
      const httpLib = require('http');
      const r = httpLib.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
        timeout: 3000,
      }, (response) => {
        let body = '';
        response.on('data', (chunk) => { body += chunk; });
        response.on('end', () => {
          try { resolve(JSON.parse(body)); } catch { resolve({ mode: nextMode, active: nextMode !== 'OFF' }); }
        });
      });
      r.on('timeout', () => { r.destroy(); resolve({ mode: nextMode, active: nextMode !== 'OFF' }); });
      r.on('error', () => resolve({ mode: nextMode, active: nextMode !== 'OFF' }));
      r.write(payload);
      r.end();
    });
    addActivity(`[AUTONOMY] Mode → ${nextMode}`, 'system');
    res.json(data);
  } catch {
    res.json({ mode: nextMode, active: nextMode !== 'OFF' });
  }
});

app.post('/api/autonomy/emergency-stop', (req, res) => {
  // Proxy emergency stop to Python backend
  const httpLib = require('http');
  const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/emergency-stop`;
  const r = httpLib.request(url, { method: 'POST', timeout: 3000 }, (response) => {
    let body = '';
    response.on('data', (chunk) => { body += chunk; });
    response.on('end', () => {
      try {
        addActivity('[AUTONOMY] ⚠ EMERGENCY STOP executed', 'system');
        res.json(JSON.parse(body));
      } catch { res.json({ status: 'stopped', message: 'Emergency stop sent.' }); }
    });
  });
  r.on('timeout', () => { r.destroy(); res.json({ status: 'stopped', message: 'Emergency stop sent (timeout).' }); });
  r.on('error', () => res.json({ status: 'stopped', message: 'Emergency stop sent (backend unreachable).' }));
  r.end();
});

app.get('/api/evolution/status', async (req, res) => {
  try {
    const data = await requestPythonJSON('/api/evolution/status', 'GET');
    res.json(data);
  } catch {
    res.json({ mode: 'OFF', running: false });
  }
});

app.post('/api/evolution/mode', async (req, res) => {
  const mode = String((req.body || {}).mode || '').toUpperCase();
  if (!['OFF', 'SAFE', 'AUTO'].includes(mode)) {
    return res.status(400).json({ error: 'Invalid mode. Use OFF, SAFE, or AUTO.' });
  }
  try {
    const data = await requestPythonJSON('/api/evolution/mode', 'POST', { mode });
    addActivity(`[EVOLUTION] Mode → ${mode}`, 'system');
    res.json(data);
  } catch {
    res.json({ mode, status: { mode, running: false } });
  }
});

app.get('/api/product/dashboard', (req, res) => {
  res.json(buildDashboardPayload());
});

app.get('/api/workflows/live', (req, res) => {
  res.json({
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
  });
});

app.get('/api/objectives/status', (req, res) => {
  res.json({
    objectives: runtimeState.objectives,
    systems: runtimeState.objectiveState,
  });
});

app.post('/api/automation/control', (req, res) => {
  const action = String((req.body || {}).action || '').toLowerCase();
  const goal = String((req.body || {}).goal || '').trim();
  const overrideActionId = String((req.body || {}).override_action_id || '').trim();

  if (action === 'start') {
    activateAgents(3);
    runtimeState.automationRunning = true;
    addActivity(`[AUTOMATION] started${goal ? ` • goal: ${goal}` : ''}`, 'automation');
    const run = createWorkflowRun({
      name: 'Automation Goal Workflow',
      source: 'automation',
      goal: goal || 'Execute automation cycle',
    });
    const taskMessages = [
      goal || 'Analyze current market conditions',
      'Generate value opportunities',
      'Route prioritized tasks to agents',
    ];
    runtimeState.workflowSequencers[run.run_id] = {
      messages: taskMessages,
      queuedSteps: new Set([0]),
      completedSteps: new Set(),
      stepTaskIds: {},
      stopped: false,
    };
    queueWorkflowStep({
      runId: run.run_id,
      message: taskMessages[0],
      stepIndex: 0,
      labels: ['automation', 'step-1'],
      parentTaskId: null,
    });
    return res.json({ status: 'running', message: 'Automation started.', tasks_queued: 1, workflow_run: run.run_id });
  }

  if (action === 'stop') {
    Object.values(runtimeState.workflowSequencers).forEach((seq) => {
      seq.stopped = true;
    });
    runtimeState.automationRunning = false;
    const stopResult = stopAllAgents('automation_stop');
    markWorkflowsStopped();
    addActivity('[AUTOMATION] stopped', 'automation');
    return res.json({
      status: 'stopped',
      message: 'Automation stopped.',
      cancelled_tasks: stopResult.cancelledTasks,
      running_agents: stopResult.runningAgents,
    });
  }

  if (action === 'override') {
    if (!overrideActionId) {
      return res.status(400).json({ status: 'error', reason: 'override_action_id is required.' });
    }
    addActivity(`[AUTOMATION] manual override executed for ${overrideActionId}`, 'automation');
    return res.json({ status: 'ok', message: `Override applied to ${overrideActionId}.` });
  }

  return res.status(400).json({ status: 'error', reason: 'Invalid automation action.' });
});

app.post('/api/money/content-pipeline', (req, res) => {
  const run = runPipeline('content');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id });
});

app.post('/api/money/lead-pipeline', (req, res) => {
  const run = runPipeline('lead');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id });
});

app.post('/api/money/opportunity-pipeline', (req, res) => {
  const run = runPipeline('opportunity');
  res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id });
});

// ── Task execution endpoint ───────────────────────────────────────────────────

app.post('/api/tasks/run', (req, res) => {
  const message = String((req.body || {}).message || 'Execute task').trim();
  const run = createWorkflowRun({
    name: 'Ad-hoc Task Workflow',
    source: 'manual',
    goal: message,
  });
  const result = orchestrator.submitTask(message, {
    userId: 'user:default',
    workflow: { runId: run.run_id, parentTaskId: null },
    labels: ['manual'],
  });
  attachWorkflowNode({
    runId: run.run_id,
    queued: result,
    taskName: message,
  });
  addActivity(`[TASK] Submitted: ${message}`, 'task');
  res.json({ ok: true, workflow_run: run.run_id, ...result });
});

// Compatibility endpoint used by legacy CLI flows (`ai-employee do/onboard`)
app.post('/api/chat', (req, res) => {
  const message = String((req.body || {}).message || '').trim();
  if (!message) {
    return res.status(400).json({ ok: false, error: 'message required' });
  }
  const handled = handleGoalDrivenCommand(message);
  if (handled.handled) {
    return res.json({
      ok: true,
      handled: true,
      response: handled.reply,
    });
  }
  const run = createWorkflowRun({
    name: 'Chat Workflow',
    source: 'chat-http',
    goal: message,
  });
  const queued = orchestrator.submitTask(message, {
    userId: 'user:default',
    workflow: { runId: run.run_id, parentTaskId: null },
    labels: ['chat', 'http'],
  });
  attachWorkflowNode({
    runId: run.run_id,
    queued,
    taskName: message,
    parentTaskId: null,
  });
  addActivity(`[CHAT] Submitted: ${message}`, 'task');
  broadcaster.broadcast('orchestrator:queued', queued);
  broadcaster.broadcast('heartbeat', {
    message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
    level: 'info',
    heartbeat: heartbeatCounter,
  });
  return res.json({
    ok: true,
    taskId: queued.taskId,
    workflow_run: run.run_id,
    response: `Queued task ${queued.taskId} on ${queued.agentId}.`,
  });
});

// ── WebSocket server ──────────────────────────────────────────────────────────

const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (ws) => {
  ws.send(JSON.stringify({ event: 'system:status', data: sampleSystemStatus(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'agent:update', data: { agents: getAgents() }, timestamp: new Date().toISOString() }));

  // Send current subsystem state immediately on connection
  ws.send(JSON.stringify({ event: 'nn:status', data: subsystems.getNNStatus(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'memory:update', data: subsystems.getMemoryTree(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'doctor:check', data: subsystems.getDoctorStatus(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'brain:insights', data: brain.insights(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'brain:activity', data: brain.activity(20), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'autonomy:status', data: subsystems.getAutonomyStatus(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({
    event: 'objective:update',
    data: {
      type: 'objective_update',
      system: 'money_mode',
      ...runtimeState.objectiveState.money_mode,
    },
    timestamp: new Date().toISOString(),
  }));
  ws.send(JSON.stringify({
    event: 'objective:update',
    data: {
      type: 'objective_update',
      system: 'ascend_forge',
      ...runtimeState.objectiveState.ascend_forge,
    },
    timestamp: new Date().toISOString(),
  }));
  ws.send(JSON.stringify({
    event: 'workflow:snapshot',
    data: { active_run: runtimeState.selectedWorkflowRun, runs: runtimeState.workflowRuns },
    timestamp: new Date().toISOString(),
  }));
  ws.send(JSON.stringify({
    event: 'observability:snapshot',
    data: buildObservabilitySnapshot(),
    timestamp: new Date().toISOString(),
  }));

  // Send existing activity feed so newly connected clients are up to date
  if (runtimeState.activityFeed.length > 0) {
    ws.send(JSON.stringify({ event: 'activity:snapshot', data: runtimeState.activityFeed, timestamp: new Date().toISOString() }));
  }
  if (runtimeState.executionLogs.length > 0) {
    ws.send(JSON.stringify({ event: 'execution:snapshot', data: runtimeState.executionLogs, timestamp: new Date().toISOString() }));
  }

  ws.on('message', (raw) => {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.type === 'chat' && parsed.message) {
        const msg = parsed.message.trim().toLowerCase();

        // ── Autonomy chat commands ─────────────────────────────────────
        const autonomyCmds = {
          'system on': 'ON',
          'system off': 'OFF',
          'system auto': 'AUTO',
          'halt system': '_HALT',
          'emergency stop': '_HALT',
          'status system': '_STATUS',
        };
        const cmdMatch = autonomyCmds[msg];
        if (cmdMatch) {
          if (cmdMatch === '_HALT') {
            const httpLib = require('http');
            const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/emergency-stop`;
            const r = httpLib.request(url, { method: 'POST', timeout: 3000 }, () => {});
            r.on('error', () => {});
            r.end();
            addActivity('[AUTONOMY] ⚠ EMERGENCY STOP via chat', 'system');
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              reply: '⚠️ **EMERGENCY STOP** executed. All autonomous execution halted. Mode set to OFF.',
            });
          } else if (cmdMatch === '_STATUS') {
            const auto = subsystems.getAutonomyStatus();
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              reply: `**System Status**\n- Mode: ${auto.mode?.mode || 'OFF'}\n- Daemon running: ${auto.daemon?.running || false}\n- Queue depth: ${auto.queue?.active || 0}\n- Tasks processed: ${auto.daemon?.tasks_processed || 0}`,
            });
          } else {
            // Set mode
            const httpLib = require('http');
            const payload = JSON.stringify({ mode: cmdMatch });
            const url = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}/api/autonomy/mode`;
            const r = httpLib.request(url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
              timeout: 3000,
            }, () => {});
            r.on('error', () => {});
            r.write(payload);
            r.end();
            addActivity(`[AUTONOMY] Mode → ${cmdMatch} (via chat)`, 'system');
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              reply: `✅ System mode set to **${cmdMatch}**.`,
            });
          }
          return; // handled — don't route to orchestrator
        }

        const objectiveCommand = handleGoalDrivenCommand(parsed.message);
        if (objectiveCommand.handled) {
          broadcaster.broadcast('orchestrator:message', {
            taskId: 'objective',
            reply: objectiveCommand.reply,
          });
          return;
        }

        // ── Normal chat routing ────────────────────────────────────────
        const run = createWorkflowRun({
          name: 'Chat Workflow',
          source: 'chat',
          goal: parsed.message,
        });
        const queued = orchestrator.submitTask(parsed.message, {
          userId: 'user:default',
          workflow: { runId: run.run_id, parentTaskId: null },
          labels: ['chat'],
        });
        attachWorkflowNode({
          runId: run.run_id,
          queued,
          taskName: parsed.message,
          parentTaskId: null,
        });
        broadcaster.broadcast('orchestrator:queued', queued);
        broadcaster.broadcast('heartbeat', {
          message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
          level: 'info',
          heartbeat: heartbeatCounter,
        });
      }
    } catch (err) {
      // ignore malformed messages
    }
  });

  ws.on('error', (err) => {
    console.error('[WS] Client error:', err.message);
  });
});

broadcaster.init(wss);
subsystems.startPolling(5000);
broadcaster.startHeartbeat({
  intervalMs: 1800,
  messageFactory: ({ seq }) => {
    heartbeatCounter = seq;
    const stats = sampleSystemStatus();
    return `[SYSTEM] heartbeat=${seq} mode=${stats.mode} running=${stats.running_agents}/${stats.total_agents}`;
  },
});
markBootEvent('ai_core_ready');

onAgentEvent('agent:update', (agents) => {
  broadcaster.broadcast('agent:update', { agents });
});

onAgentEvent('task:started', ({ agent, task }) => {
  addActivity(`[TASK] ${task.id} started on ${agent.name}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'running';
    recalcObjectiveProgress(objectiveMeta.system);
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'active';
    node.progress_percent = 45;
    node.started_at = task.startedAt || new Date().toISOString();
    node.agent = agent.name;
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'execution_start',
      summary: `Agent ${agent.name} started with strategy ${node.strategy || 'default'}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('step_progress', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    step: 'execution_started',
    agent: agent.name,
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] started ${task.id}`,
    level: 'info',
    heartbeat: heartbeatCounter,
  });
});

onAgentEvent('task:completed', ({ agent, task }) => {
  recordExecution({
    taskId: task.id,
    skill: task.subsystem || 'general',
    status: 'success',
    notes: task.message,
  });
  addActivity(`[TASK] ${task.id} completed by ${agent.name}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'completed';
    if (objectiveMeta.system === 'money_mode' && objState?.performance) {
      if (/lead/i.test(objectiveMeta.task_name)) objState.performance.leads_generated += MONEY_LEADS_PER_TASK;
      if (/email|outreach/i.test(objectiveMeta.task_name)) objState.performance.emails_sent += MONEY_EMAILS_PER_TASK;
      // Lightweight estimate for UI feedback:
      // assume roughly 2 outbound emails per potential converted lead,
      // then scale the ratio by 10 to keep the indicator in a visible 0-100 range.
      const leads = objState.performance.leads_generated || 1;
      objState.performance.conversion_pct = Math.round((objState.performance.emails_sent / Math.max(leads * 2, 1)) * 10);
    }
    if (objectiveMeta.system === 'ascend_forge') {
      objState.results = objState.results || [];
      objState.results.push({
        task_id: task.id,
        step: objectiveMeta.task_name,
        summary: `Completed ${objectiveMeta.task_name}`,
      });
      objState.results = objState.results.slice(-20);
    }
    recalcObjectiveProgress(objectiveMeta.system);
    if (objState?.status === OBJECTIVE_STATUS.COMPLETED && objState?.current_objective) {
      objState.current_objective.status = 'completed';
      objState.current_objective.updated_at = new Date().toISOString();
      const objective = runtimeState.objectives.find((row) => row.id === objState.current_objective.id);
      if (objective) {
        objective.status = 'completed';
        objective.updated_at = objState.current_objective.updated_at;
        persistObjectives();
      }
      if (objectiveMeta.system === 'ascend_forge') {
        objState.result = {
          plan: objState.plan || [],
          agents_used: objState.agents_used || [],
          progress: 100,
          status: 'completed',
          results: objState.results || [],
        };
      }
    }
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'completed';
    node.progress_percent = 100;
    node.completed_at = new Date().toISOString();
    node.agent = agent.name;
    node.result = {
      status: 'success',
      summary: task.message,
    };
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'result',
      summary: `Result success • ${task.message}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('task_completed', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    agent: agent.name,
    result: task.message,
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] completed ${task.id}`,
    level: 'success',
    heartbeat: heartbeatCounter,
  });
  queueNextWorkflowStep(task.id);
});

onAgentEvent('task:failed', ({ agent, task }) => {
  recordExecution({
    taskId: task.id,
    skill: task.subsystem || 'general',
    status: 'failed',
    notes: task.error || task.message || 'Task failed',
  });
  addActivity(`[TASK] ${task.id} failed on ${agent.name}: ${task.error || 'execution error'}`, 'task');
  const objectiveMeta = runtimeState.objectiveTaskMeta[task.id];
  if (objectiveMeta) {
    const objState = runtimeState.objectiveState[objectiveMeta.system];
    const taskRow = objState?.active_tasks?.find((entry) => entry.task_id === task.id);
    if (taskRow) taskRow.status = 'failed';
    if (objectiveMeta.system === 'ascend_forge') {
      objState.results = objState.results || [];
      objState.results.push({
        task_id: task.id,
        step: objectiveMeta.task_name,
        summary: `Failed ${objectiveMeta.task_name}: ${task.error || 'execution error'}`,
        status: 'failed',
      });
      objState.results = objState.results.slice(-20);
    }
    recalcObjectiveProgress(objectiveMeta.system);
    broadcastObjectiveUpdate(objectiveMeta.system);
  }
  if (runtimeState.workflowTaskMeta[task.id]) {
    runtimeState.workflowTaskMeta[task.id].error = task.error || null;
  }
  updateWorkflowNode(task.id, (node, run) => {
    node.status = 'failed';
    node.progress_percent = 100;
    node.completed_at = new Date().toISOString();
    node.agent = agent.name;
    node.result = {
      status: 'failed',
      summary: task.error || task.message || 'Execution failed',
    };
    appendDecision(run, {
      ts: new Date().toISOString(),
      task_id: task.id,
      type: 'result',
      summary: `Result failed • ${task.error || 'execution error'}`,
    });
  });
  const trace = runtimeState.observability.traces[task.id];
  emitObservabilityEvent('error_detected', {
    trace_id: trace ? trace.trace_id : '',
    task_id: task.id,
    agent: agent.name,
    error: task.error || 'execution error',
  });
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] failed ${task.id}`,
    level: 'warning',
    heartbeat: heartbeatCounter,
  });
  retryWorkflowStep(task.id);
});

orchestrator.on('orchestrator:reply', (data) => {
  broadcaster.broadcast('orchestrator:message', data);
});

setInterval(() => {
  broadcaster.broadcast('system:status', sampleSystemStatus());
  broadcaster.broadcast('nn:status', subsystems.getNNStatus());
  broadcaster.broadcast('memory:update', subsystems.getMemoryTree());
  broadcaster.broadcast('doctor:check', subsystems.getDoctorStatus());
  broadcaster.broadcast('brain:insights', brain.insights());
  broadcaster.broadcast('brain:activity', brain.activity(20));
  broadcaster.broadcast('autonomy:status', subsystems.getAutonomyStatus());
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system: 'money_mode',
    ...runtimeState.objectiveState.money_mode,
  });
  broadcaster.broadcast('objective:update', {
    type: 'objective_update',
    system: 'ascend_forge',
    ...runtimeState.objectiveState.ascend_forge,
  });
  broadcaster.broadcast('workflow:snapshot', {
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
  });
  broadcaster.broadcast('observability:snapshot', buildObservabilitySnapshot());
}, 2000);

app.get('*', (req, res, next) => {
  if (!HAS_FRONTEND_DIST) return next();
  if (req.path.startsWith('/api/') || req.path === '/health' || req.path === '/version') return next();
  if (req.path.startsWith('/gateway') || req.path.startsWith('/orchestrator')) return next();
  res.set('Cache-Control', 'no-store, must-revalidate');
  const html = FRONTEND_INDEX_TEMPLATE.replace(/__APP_VERSION__/g, GIT_COMMIT);
  res.type('html').send(html);
});

server.listen(PORT, () => {
  console.log(`[SERVER] AI Employee backend running on port ${PORT}`);
  console.log(`[SERVER] RUNNING FROM: ${process.cwd()}`);
  console.log(`[SERVER] FILE PATH: ${__filename}`);
  console.log(`[SERVER] LATEST COMMIT: ${GIT_COMMIT}`);
  if (HAS_FRONTEND_DIST) {
    console.log(`[SERVER] Serving frontend bundle from ${FRONTEND_DIST}`);
  } else {
    console.log('[SERVER] Frontend bundle not found (expected frontend/dist).');
  }
  // Start periodic state persistence (every 30s)
  persistence.startAutoSave(
    () => runtimeState,
    () => brain.exportState(),
  );
  markBootEvent('ui_loaded');
});
