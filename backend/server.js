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
const voiceApiRouter = require('./api/voice');

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
app.use('/api/voice', voiceApiRouter);

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
const BOOT_VOICE_PLAYED_FLAG = path.join(os.tmpdir(), `ai-employee-voice-boot-${process.pid}.flag`);

function hasBootVoicePlayed() {
  return fs.existsSync(BOOT_VOICE_PLAYED_FLAG);
}

function markBootVoicePlayed() {
  try {
    fs.writeFileSync(BOOT_VOICE_PLAYED_FLAG, '1', 'utf8');
  } catch (_err) {
    // best effort
  }
}

function getTimeBasedGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return 'Good morning. Control panel online.';
  if (hour >= 12 && hour < 18) return 'Good afternoon. Systems ready.';
  return 'Good evening. All systems operational.';
}

async function maybeSpeakBootGreeting() {
  if (bootVoiceState.triggered || hasBootVoicePlayed()) return;
  if (!bootVoiceState.system_init || !bootVoiceState.ai_core_ready || !bootVoiceState.ui_loaded) return;

  try {
    await voiceManager.init();
    if (!voiceManager.isBootGreetingEnabled()) {
      bootVoiceState.triggered = true;
      markBootVoicePlayed();
      return;
    }
    bootVoiceState.triggered = true;
    markBootVoicePlayed();
    await voiceManager.emitEvent('system_boot', { greeting: getTimeBasedGreeting() }, true);
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
  let versionState = null;
  try {
    const versionFile = path.join(REPO_ROOT, 'state', 'version.json');
    if (fs.existsSync(versionFile)) {
      versionState = JSON.parse(fs.readFileSync(versionFile, 'utf8'));
    }
  } catch (_e) { /* ignore */ }
  res.json({
    commit: GIT_COMMIT,
    timestamp: new Date().toISOString(),
    started_at: SERVER_START_TIMESTAMP,
    cwd: process.cwd(),
    file: __filename,
    version_state: versionState,
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

/**
 * Unified graph endpoint for the 3-D Neural Brain visualization.
 * Returns { nodes, links, stats } using a normalized schema so the
 * frontend brainStore can consume it directly.
 */
app.get('/api/brain/graph', (req, res) => {
  const raw = brain.neurons();
  const memoryTree = subsystems.getMemoryTree();
  const nodes = (raw.nodes || []).map((n) => ({
    id: n.id,
    label: n.label,
    type: n.type || 'skill',
    group:
      n.type === 'Memory'
        ? 'memory'
        : n.type === 'Strategy' || n.type === 'Skill'
          ? 'money'
          : n.type === 'Output'
            ? 'automation'
            : 'learning',
    weight: n.weight ?? 1,
    confidence: n.confidence ?? 0,
    activation: n.activation ?? 0,
    source: n.source || 'system',
    tag: n.tag || '',
  }));

  // Append top memory-tree entities as nodes
  if (Array.isArray(memoryTree?.nodes)) {
    memoryTree.nodes.slice(0, 30).forEach((m) => {
      const id = `mem-${(m.id || m.entity || '').replace(/\s+/g, '-').slice(0, 40)}`;
      if (nodes.some((n) => n.id === id)) return;
      nodes.push({
        id,
        label: m.entity || m.id || 'memory',
        type: 'memory',
        group: 'memory',
        weight: m.mention_count ?? m.importance ?? 1,
        confidence: m.importance ?? 0.5,
        activation: 0,
        source: 'memory',
        tag: 'knowledge',
      });
    });
  }

  const links = (raw.connections || []).map((c) => ({
    source: c.from,
    target: c.to,
    strength: c.weight ?? c.confidence ?? 0.5,
  }));

  res.json({
    nodes,
    links,
    stats: raw.stats || {},
    updated_at: raw.updated_at || new Date().toISOString(),
  });
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

/**
 * Build a contextual local reply when the Python LLM backend is unavailable.
 * Uses live subsystem state to produce a meaningful (non-generic) response.
 */
function buildLocalFallbackReply(message, queuedTask) {
  const lower = (message || '').toLowerCase();
  const subsystem = (queuedTask && queuedTask.subsystem) || 'general';
  const agentId = (queuedTask && queuedTask.agentId) || 'agent';
  const mode = getMode();
  const running = getRunningAgentCount();

  if (/\b(health|diagnos|system check|doctor)\b/.test(lower) || subsystem === 'doctor') {
    const dr = subsystems.getDoctorStatus();
    const score = dr.overall_score || 0;
    const issueCount = (dr.issues || []).length;
    return `[DOCTOR] System health score: ${score}/100. ${issueCount ? `${issueCount} issue(s) detected.` : 'All subsystems clear.'} Grade: ${dr.grade || 'N/A'}.`;
  }
  if (/\b(memory|knowledge|context|recall|entities)\b/.test(lower) || subsystem === 'memory') {
    const mem = subsystems.getMemoryTree();
    return `[MEMORY] ${mem.total_entities || 0} knowledge entities on file. Your request has been indexed for future context.`;
  }
  if (/\b(neural|network|confidence|train|learn|model)\b/.test(lower) || subsystem === 'nn') {
    const nn = subsystems.getNNStatus();
    const conf = Math.round((nn.confidence || 0) * 100);
    return `[NEURAL] Operating in ${nn.mode || 'standard'} mode — confidence ${conf}%, ${(nn.experiences || 0).toLocaleString()} experiences logged.`;
  }
  if (/\b(status|how are you|overview)\b/.test(lower)) {
    return `[ORCHESTRATOR] Mode: ${mode}. Active agents: ${running}. Tasks processed: ${runtimeState.tasksExecuted}. All systems nominal.`;
  }
  if (/\b(hello|hi|hey|greet)\b/.test(lower)) {
    return `Hello! I'm your AI employee operating in ${mode} mode with ${running} active agent${running !== 1 ? 's' : ''}. How can I help?`;
  }
  if (/\b(help|what can you|capabilities)\b/.test(lower)) {
    return `I can: run automation pipelines, manage agents, analyze data, search knowledge, diagnose system health, execute goals via Money Mode or Ascend Forge. What would you like to do?`;
  }
  return `[${agentId.toUpperCase()}] Request received and routed in ${mode} mode (${running} agent${running !== 1 ? 's' : ''} active). Task ${queuedTask ? queuedTask.taskId : 'unknown'} is being processed.`;
}

/**
 * Proxy a chat message to the Python backend's full LLM pipeline.
 * Returns the response string on success, or null if the Python backend
 * is unreachable (callers fall back to the local buildHumanReply).
 *
 * Timeout is generous (30 s) because LLM inference may be slow.
 */
const PYTHON_CHAT_TIMEOUT_MS = 30000;

function requestPythonChat(message, modelRoute) {
  return new Promise((resolve) => {
    const payload = { message };
    if (modelRoute) payload.model_route = modelRoute;
    const body = JSON.stringify(payload);
    const req = http.request(`http://${PYTHON_BACKEND_HOST}:${PYTHON_BACKEND_PORT}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: PYTHON_CHAT_TIMEOUT_MS,
    }, (response) => {
      let text = '';
      response.on('data', (chunk) => { text += chunk; });
      response.on('end', () => {
        try {
          const data = JSON.parse(text || '{}');
          resolve(data.response || data.reply || null);
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.write(body);
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
app.post('/api/chat', async (req, res) => {
  const message = String((req.body || {}).message || '').trim();
  const modelRoute = String((req.body || {}).model_route || '').trim() || undefined;
  if (!message) {
    return res.status(400).json({ ok: false, error: 'message required' });
  }
  console.info('[AI FLOW] Input received (HTTP): message_len=%d', message.length);
  const handled = handleGoalDrivenCommand(message);
  if (handled.handled) {
    console.info('[AI FLOW] → Response returned (goal-driven command)');
    return res.json({
      ok: true,
      handled: true,
      reply: handled.reply,
    });
  }
  const run = createWorkflowRun({
    name: 'Chat Workflow',
    source: 'chat-http',
    goal: message,
  });
  console.info('[AI FLOW] → Core AI called (orchestrator.submitTask)');
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

  // ── Proxy to Python LLM backend for real AI response ──────────────────────
  let llmReply = null;
  try {
    llmReply = await requestPythonChat(message, modelRoute);
  } catch (err) {
    console.warn('[AI FLOW] Python chat proxy failed (HTTP path):', err && err.message);
  }
  if (llmReply) {
    console.info('[AI FLOW] → LLM response returned (HTTP→Python): len=%d', llmReply.length);
    return res.json({
      ok: true,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      reply: llmReply,
    });
  }

  console.info('[AI FLOW] → Fallback response (HTTP): taskId=%s', queued.taskId);
  // MUST ALWAYS FIRE — res.json is called unconditionally
  return res.json({
    ok: true,
    taskId: queued.taskId,
    workflow_run: run.run_id,
    reply: buildLocalFallbackReply(message, queued),
  });
});

// ── Enterprise: Audit, Reliability, Forge-queue endpoints ────────────────────

// In-process audit log (lightweight JS-side; Python audit_engine is the source
// of truth when the Python backend is also running).
const _auditLog = [];
const MAX_AUDIT_ENTRIES = 2000;

function recordAuditEvent({ actor, action, inputData, outputData, riskScore, traceId, meta }) {
  const score = typeof riskScore === 'number' ? Math.min(1, Math.max(0, riskScore)) : _classifyRisk(action);
  const evt = {
    id: `audit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    ts: new Date().toISOString(),
    actor: String(actor || 'system'),
    action: String(action || 'unknown'),
    input: inputData || {},
    output: outputData || {},
    risk_score: score,
    trace_id: traceId || '',
    meta: meta || {},
  };
  _auditLog.unshift(evt);
  if (_auditLog.length > MAX_AUDIT_ENTRIES) _auditLog.length = MAX_AUDIT_ENTRIES;
  return evt;
}

const _HIGH_RISK_ACTIONS = new Set([
  'forge_deploy', 'forge_rollback', 'memory_delete', 'memory_rollback',
  'permission_override', 'economy_withdraw', 'agent_stop_all', 'security_strict_mode',
]);
const _MEDIUM_RISK_ACTIONS = new Set([
  'forge_submit', 'forge_approve', 'memory_write', 'config_change',
  'agent_mode_change', 'economy_action', 'tool_execution',
]);

function _classifyRisk(action) {
  if (_HIGH_RISK_ACTIONS.has(action)) return 0.85;
  if (_MEDIUM_RISK_ACTIONS.has(action)) return 0.45;
  return 0.10;
}

// Reliability state
const reliabilityState = {
  forgeFrozen: false,
  freezeReason: '',
  stabilityScore: 1.0,
  checkpoints: [],
  throttledAgents: [],
  lastEvaluated: null,
};

function updateStabilityScore() {
  const snap = buildObservabilitySnapshot();
  const errorsPerMin = (snap.metrics || {}).errors_per_minute || 0;
  const errorFactor = Math.min(1.0, errorsPerMin / 10);
  const score = Math.max(0.0, 1.0 - 0.6 * errorFactor);
  reliabilityState.stabilityScore = Math.round(score * 1000) / 1000;
  reliabilityState.lastEvaluated = new Date().toISOString();
  if (errorsPerMin >= 10 && !reliabilityState.forgeFrozen) {
    reliabilityState.forgeFrozen = true;
    reliabilityState.freezeReason = `error_rate=${errorsPerMin}/min`;
    recordAuditEvent({ actor: 'system', action: 'forge_freeze', outputData: { reason: reliabilityState.freezeReason }, riskScore: 0.7 });
  }
}

setInterval(updateStabilityScore, 10000);

// Forge approval queue (JS-side mirror of Python AscendForgeExecutor queue)
const _forgeQueue = [];
const MAX_FORGE_QUEUE = 200;

function _forgeRiskScore(goal) {
  const text = (goal || '').toLowerCase();
  const highKw = ['deploy', 'production', 'delete', 'drop', 'rm ', 'overwrite', 'replace all', 'wipe'];
  const midKw = ['refactor', 'update', 'migrate', 'change', 'modify', 'patch', 'rewrite'];
  if (highKw.some((kw) => text.includes(kw))) return 0.80;
  if (midKw.some((kw) => text.includes(kw))) return 0.45;
  return 0.15;
}

function _forgeRiskLabel(score) {
  if (score >= 0.7) return 'HIGH';
  if (score >= 0.3) return 'MEDIUM';
  return 'LOW';
}

// GET /api/audit/events
app.get('/api/audit/events', (req, res) => {
  const limit = Math.min(500, Math.max(1, parseInt((req.query || {}).limit) || 100));
  const actor = (req.query || {}).actor || '';
  const action = (req.query || {}).action || '';
  const minRisk = parseFloat((req.query || {}).min_risk || '0') || 0;
  let events = _auditLog;
  if (actor) events = events.filter((e) => e.actor === actor);
  if (action) events = events.filter((e) => e.action === action);
  if (minRisk > 0) events = events.filter((e) => e.risk_score >= minRisk);
  res.json({ events: events.slice(0, limit), total: _auditLog.length });
});

// GET /api/audit/stats
app.get('/api/audit/stats', (req, res) => {
  const byActor = {};
  const byAction = {};
  const riskDist = { low: 0, medium: 0, high: 0 };
  for (const evt of _auditLog) {
    byActor[evt.actor] = (byActor[evt.actor] || 0) + 1;
    byAction[evt.action] = (byAction[evt.action] || 0) + 1;
    if (evt.risk_score < 0.25) riskDist.low++;
    else if (evt.risk_score < 0.6) riskDist.medium++;
    else riskDist.high++;
  }
  res.json({ total: _auditLog.length, by_actor: byActor, by_action: byAction, risk_distribution: riskDist });
});

// GET /api/reliability/status
app.get('/api/reliability/status', (req, res) => {
  res.json({
    stability_score: reliabilityState.stabilityScore,
    forge_frozen: reliabilityState.forgeFrozen,
    freeze_reason: reliabilityState.freezeReason,
    throttled_agents: reliabilityState.throttledAgents,
    checkpoints_stored: reliabilityState.checkpoints.length,
    last_evaluated: reliabilityState.lastEvaluated,
    updated_at: new Date().toISOString(),
  });
});

// POST /api/reliability/forge/freeze
app.post('/api/reliability/forge/freeze', (req, res) => {
  const reason = String((req.body || {}).reason || 'manual');
  reliabilityState.forgeFrozen = true;
  reliabilityState.freezeReason = reason;
  recordAuditEvent({ actor: 'operator', action: 'forge_freeze', outputData: { reason }, riskScore: 0.7 });
  res.json({ ok: true, forge_frozen: true, reason });
});

// POST /api/reliability/forge/unfreeze
app.post('/api/reliability/forge/unfreeze', (req, res) => {
  reliabilityState.forgeFrozen = false;
  reliabilityState.freezeReason = '';
  recordAuditEvent({ actor: 'operator', action: 'forge_unfreeze', outputData: {}, riskScore: 0.5 });
  res.json({ ok: true, forge_frozen: false });
});

// GET /api/forge/queue
app.get('/api/forge/queue', (req, res) => {
  const status = (req.query || {}).status || '';
  const items = status ? _forgeQueue.filter((r) => r.status === status) : _forgeQueue;
  res.json({ items, total: _forgeQueue.length });
});

// POST /api/forge/submit
app.post('/api/forge/submit', (req, res) => {
  const body = req.body || {};
  const goal = String(body.goal || '').trim();
  if (!goal) return res.status(400).json({ ok: false, error: 'goal required' });
  if (reliabilityState.forgeFrozen) {
    return res.status(503).json({ ok: false, error: 'Forge is frozen', reason: reliabilityState.freezeReason });
  }
  const score = _forgeRiskScore(goal);
  const label = _forgeRiskLabel(score);
  const now = new Date().toISOString();
  const req2 = {
    id: `fcr-${Date.now().toString(36)}`,
    goal,
    risk_score: score,
    risk_level: label,
    status: score >= 0.7 ? 'rejected' : score < 0.3 ? 'approved' : 'pending',
    created_at: now,
    decided_at: score !== 0.45 ? now : null,
    decided_by: score >= 0.7 ? 'system:risk_gate' : score < 0.3 ? 'system:auto_low_risk' : null,
    sandbox_result: null,
  };
  _forgeQueue.unshift(req2);
  if (_forgeQueue.length > MAX_FORGE_QUEUE) _forgeQueue.length = MAX_FORGE_QUEUE;
  recordAuditEvent({ actor: body.submitted_by || 'operator', action: 'forge_submit', inputData: { goal, risk_level: label }, outputData: { request_id: req2.id, status: req2.status }, riskScore: score });
  res.json({ ok: true, request: req2 });
});

// POST /api/forge/approve/:id
app.post('/api/forge/approve/:id', (req, res) => {
  const item = _forgeQueue.find((r) => r.id === req.params.id);
  if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
  if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
  item.status = 'approved';
  item.decided_at = new Date().toISOString();
  item.decided_by = (req.body || {}).approved_by || 'operator';
  recordAuditEvent({ actor: item.decided_by, action: 'forge_approve', inputData: { request_id: item.id }, outputData: { status: 'approved' }, riskScore: 0.5 });
  res.json({ ok: true, request: item });
});

// POST /api/forge/reject/:id
app.post('/api/forge/reject/:id', (req, res) => {
  const item = _forgeQueue.find((r) => r.id === req.params.id);
  if (!item) return res.status(404).json({ ok: false, error: 'request not found' });
  if (item.status !== 'pending') return res.status(409).json({ ok: false, error: `request is already ${item.status}` });
  item.status = 'rejected';
  item.decided_at = new Date().toISOString();
  item.decided_by = (req.body || {}).rejected_by || 'operator';
  recordAuditEvent({ actor: item.decided_by, action: 'forge_reject', inputData: { request_id: item.id }, outputData: { status: 'rejected' }, riskScore: 0.3 });
  res.json({ ok: true, request: item });
});

// ── Learning Ladder Builder API ───────────────────────────────────────────────

const learningLadder = require('./core/learning_ladder');
const agentLearningProfile = require('./core/agent_learning_profile');

// POST /api/learning-ladder/build  { topic }
app.post('/api/learning-ladder/build', (req, res) => {
  const topic = String((req.body || {}).topic || '').trim();
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  try {
    const ladder = learningLadder.buildLadder(topic);
    addActivity(`[LEARNING] Ladder built: ${topic}`, 'learning');
    res.json({ ok: true, ladder });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// POST /api/learning-ladder/complete  { topic, level, success, milestone_output, score, notes }
app.post('/api/learning-ladder/complete', (req, res) => {
  const body = req.body || {};
  const topic = String(body.topic || '').trim();
  const level = parseInt(body.level, 10);
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  if (!level || level < 1 || level > 5) return res.status(400).json({ ok: false, error: 'level must be 1–5' });
  try {
    const result = learningLadder.recordLevelCompletion({
      topic,
      level,
      success: Boolean(body.success),
      milestoneOutput: String(body.milestone_output || ''),
      score: parseFloat(body.score) || 0,
      notes: String(body.notes || ''),
    });
    const status = result.learned ? 'LEARNED' : 'NOT LEARNED';
    addActivity(`[LEARNING] Level ${level} ${status}: ${topic}`, 'learning');
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/learning-ladder/progress?topic=...
app.get('/api/learning-ladder/progress', (req, res) => {
  const topic = String(req.query.topic || '').trim();
  if (!topic) return res.status(400).json({ ok: false, error: 'topic query param is required' });
  try {
    const progress = learningLadder.getProgress(topic);
    res.json({ ok: true, ...progress });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/learning-ladder/all
app.get('/api/learning-ladder/all', (req, res) => {
  try {
    const topics = learningLadder.getAllTopics();
    const metrics = learningLadder.getMetrics();
    res.json({ ok: true, topics, metrics });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ── Agent Learning Profile API ────────────────────────────────────────────────

// POST /api/agents/:agent_id/ladder/assign  { topic }
app.post('/api/agents/:agent_id/ladder/assign', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  const topic = String((req.body || {}).topic || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  if (!topic) return res.status(400).json({ ok: false, error: 'topic is required' });
  try {
    const result = agentLearningProfile.assignLadder(agentId, topic);
    addActivity(`[LEARNING] Ladder '${topic}' assigned to agent ${agentId}`, 'learning');
    res.json({ ok: true, ...result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// POST /api/agents/:agent_id/ladder/advance  { level, success, milestone_output, score, notes }
app.post('/api/agents/:agent_id/ladder/advance', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  const body = req.body || {};
  const level = parseInt(body.level, 10);
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  if (!level || level < 1 || level > 5) return res.status(400).json({ ok: false, error: 'level must be 1–5' });
  try {
    const result = agentLearningProfile.advanceAgent({
      agentId,
      level,
      success: Boolean(body.success),
      score: parseFloat(body.score) || 0,
      milestoneOutput: String(body.milestone_output || ''),
      notes: String(body.notes || ''),
    });
    const status = result.learned ? `LEARNED (grade: ${result.grade})` : 'NOT LEARNED';
    addActivity(`[LEARNING] Agent ${agentId} Level ${level} ${status}`, 'learning');
    res.json({ ok: true, result });
  } catch (err) {
    const status = err.message.includes('no learning ladder') ? 404 : 500;
    res.status(status).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/:agent_id/grade
app.get('/api/agents/:agent_id/grade', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  try {
    const grade = agentLearningProfile.getAgentGrade(agentId);
    res.json({ ok: true, ...grade });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/:agent_id/profile
app.get('/api/agents/:agent_id/profile', (req, res) => {
  const agentId = String(req.params.agent_id || '').trim();
  if (!agentId) return res.status(400).json({ ok: false, error: 'agent_id is required' });
  try {
    const profile = agentLearningProfile.getAgentProfile(agentId);
    res.json({ ok: true, ...profile });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /api/agents/grades
app.get('/api/agents/grades', (req, res) => {
  try {
    const profiles = agentLearningProfile.getAllProfiles();
    const metrics = agentLearningProfile.getMetrics();
    res.json({ ok: true, profiles, metrics });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
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
              message: '⚠️ Emergency stop executed. All autonomous execution has been halted.',
            });
          } else if (cmdMatch === '_STATUS') {
            const auto = subsystems.getAutonomyStatus();
            broadcaster.broadcast('orchestrator:message', {
              taskId: 'system',
              message: `System status — mode: ${auto.mode?.mode || 'OFF'}, daemon ${auto.daemon?.running ? 'running' : 'stopped'}, queue depth: ${auto.queue?.active || 0}, tasks processed: ${auto.daemon?.tasks_processed || 0}.`,
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
              message: `System mode set to ${cmdMatch}. Ready.`,
            });
          }
          return; // handled — don't route to orchestrator
        }

        const objectiveCommand = handleGoalDrivenCommand(parsed.message);
        if (objectiveCommand.handled) {
          broadcaster.broadcast('orchestrator:message', {
            taskId: 'objective',
            message: objectiveCommand.reply,
          });
          return;
        }

        // ── Normal chat routing ────────────────────────────────────────
        console.info('[AI FLOW] Input received (WS): message_len=%d', parsed.message.length);
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

        // ── Proxy to Python backend LLM pipeline for real AI response ──
        // The Python backend has the full pipeline: context injection,
        // memory, LLM call, personalised response. Use it instead of
        // the generic keyword-matched buildHumanReply.
        // When Python is unavailable, we MUST still broadcast an
        // orchestrator:message so the UI does not stay stuck on "processing".
        const wsModelRoute = parsed.model_route || undefined;
        requestPythonChat(parsed.message, wsModelRoute).then((llmReply) => {
          if (llmReply) {
            console.info('[AI FLOW] → LLM response returned (WS→Python): len=%d', llmReply.length);
            broadcaster.broadcast('orchestrator:message', {
              message: llmReply,
              subsystem: queued.subsystem || 'orchestrator',
              taskId: queued.taskId,
              from: queued.agentId,
              agentId: queued.agentId,
              timestamp: new Date().toISOString(),
            });
          } else {
            console.info('[AI FLOW] → Local fallback response (Python unavailable, WS): taskId=%s', queued.taskId);
            broadcaster.broadcast('orchestrator:message', {
              message: buildLocalFallbackReply(parsed.message, queued),
              subsystem: queued.subsystem || 'orchestrator',
              taskId: queued.taskId,
              from: queued.agentId,
              agentId: queued.agentId,
              timestamp: new Date().toISOString(),
            });
          }
        }).catch((err) => {
          console.warn('[AI FLOW] Python chat proxy failed:', err && err.message);
          broadcaster.broadcast('orchestrator:message', {
            message: buildLocalFallbackReply(parsed.message, queued),
            subsystem: queued.subsystem || 'orchestrator',
            taskId: queued.taskId,
            from: queued.agentId,
            agentId: queued.agentId,
            timestamp: new Date().toISOString(),
          });
        });
        console.info('[AI FLOW] → Task queued (WS): taskId=%s', queued.taskId);
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
  void voiceManager.emitEvent('task_created', { priority: task.priority });
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
  void voiceManager.emitEvent('task_completed');
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
  void voiceManager.emitEvent('error_detected', { message: 'Error detected.' });
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
  if (!HAS_FRONTEND_DIST) {
    if (req.path.startsWith('/api/') || req.path === '/health' || req.path === '/version') return next();
    res.status(503).type('html').send(`<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>AI Employee — Build Required</title>
<style>body{font-family:sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:2rem 2.5rem;max-width:480px;text-align:center}
h1{color:#f8fafc;margin-top:0}pre{background:#0f172a;border-radius:6px;padding:1rem;text-align:left;font-size:.85rem;overflow-x:auto}</style>
</head>
<body><div class="box">
<h1>⚠ Frontend Not Built</h1>
<p>The production build of the frontend is missing. Run the following command from the repository root to build it:</p>
<pre>npm --prefix frontend run build</pre>
<p>Or start the full system with:</p>
<pre>./start.sh</pre>
<p>For live development with hot-reload, start the Vite dev server instead:</p>
<pre>cd frontend &amp;&amp; npm run dev</pre>
<p>API health check: <a href="/health" style="color:#60a5fa">/health</a></p>
</div></body></html>`);
    return;
  }
  if (req.path.startsWith('/api/') || req.path === '/health' || req.path === '/version') return next();
  if (req.path.startsWith('/gateway') || req.path.startsWith('/orchestrator')) return next();
  res.set('Cache-Control', 'no-store, must-revalidate');
  const html = FRONTEND_INDEX_TEMPLATE.replace(/__APP_VERSION__/g, GIT_COMMIT);
  res.type('html').send(html);
});

// Bind to all interfaces by default so the server is reachable from the host
// machine when running inside WSL, Docker, or a VM.  Set LISTEN_HOST=127.0.0.1
// in the environment to restrict to loopback only.
const LISTEN_HOST = process.env.LISTEN_HOST || '0.0.0.0';

console.log(`[SERVER] Initializing — binding to ${LISTEN_HOST}:${PORT} …`);

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[SERVER] ❌ Port ${PORT} is already in use. Stop the conflicting process and restart.`);
  } else {
    console.error('[SERVER] ❌ Server error:', err.message);
  }
  process.exit(1);
});

server.listen(PORT, LISTEN_HOST, () => {
  console.log(`[SERVER] ✅ AI Employee backend running on http://${LISTEN_HOST}:${PORT}`);
  console.log(`[SERVER] RUNNING FROM: ${process.cwd()}`);
  console.log(`[SERVER] FILE PATH: ${__filename}`);
  console.log(`[SERVER] LATEST COMMIT: ${GIT_COMMIT}`);
  if (HAS_FRONTEND_DIST) {
    console.log(`[SERVER] Serving frontend bundle from ${FRONTEND_DIST}`);
  } else {
    console.log('[SERVER] ⚠  Frontend bundle not found (expected frontend/dist). Run: npm --prefix frontend run build');
  }
  // Start periodic state persistence (every 30s)
  persistence.startAutoSave(
    () => runtimeState,
    () => brain.exportState(),
  );
  markBootEvent('ui_loaded');
});
