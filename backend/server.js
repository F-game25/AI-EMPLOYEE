'use strict';

const http = require('http');
const os = require('os');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');

const gateway = require('./gateway');
const orchestrator = require('./orchestrator');
const broadcaster = require('./events/broadcaster');
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

const PORT = process.env.PORT || 3001;

const app = express();

app.use(cors());
app.use(express.json());

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
const BASE_PIPELINE_ROI = 250;
const PIPELINE_ROI_SWING = 400;
const REVENUE_CONVERSION_RATE = 0.45;
const CANCELLATION_ERROR_PREFIX = 'cancelled:';

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
  _seq: 0,
};

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
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

function estimatePipelineRoi() {
  return BASE_PIPELINE_ROI + Math.floor(Math.random() * PIPELINE_ROI_SWING);
}

function runPipeline(pipelineName) {
  const estimatedRoi = estimatePipelineRoi();
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

function sampleSystemStatus() {
  const cpu = cpuUsagePercent();
  const memory = memoryUsagePercent();
  const randomSwing = Math.random() * GPU_RANDOM_SWING - GPU_SWING_OFFSET;
  const cpuInfluence = (cpu - GPU_CPU_BASELINE) * GPU_CPU_INFLUENCE;
  // Intentionally mutates currentGpuUsage to simulate gradual GPU trend across snapshots.
  currentGpuUsage = clamp(
    Math.round(currentGpuUsage + randomSwing + cpuInfluence),
    4,
    97,
  );
  const cpuTemp = clamp(Math.round(CPU_TEMP_BASE + cpu * CPU_TEMP_CPU_FACTOR + Math.random() * CPU_TEMP_JITTER), 32, 95);
  const gpuTemp = clamp(Math.round(GPU_TEMP_BASE + currentGpuUsage * GPU_TEMP_GPU_FACTOR + Math.random() * GPU_TEMP_JITTER), 30, 90);

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
    timestamp: new Date().toISOString(),
  };
}

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() });
});

app.get('/agents', (req, res) => {
  res.json({ agents: getAgents() });
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

app.get('/api/brain/insights', (req, res) => {
  res.json(brain.insights());
});

app.get('/api/brain/activity', (req, res) => {
  const limit = Number(req.query.limit || 20);
  res.json(brain.activity(limit));
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

app.get('/api/product/dashboard', (req, res) => {
  res.json(buildDashboardPayload());
});

app.get('/api/workflows/live', (req, res) => {
  res.json({
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
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
    event: 'workflow:snapshot',
    data: { active_run: runtimeState.selectedWorkflowRun, runs: runtimeState.workflowRuns },
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

onAgentEvent('agent:update', (agents) => {
  broadcaster.broadcast('agent:update', { agents });
});

onAgentEvent('task:started', ({ agent, task }) => {
  addActivity(`[TASK] ${task.id} started on ${agent.name}`, 'task');
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
  broadcaster.broadcast('workflow:snapshot', {
    active_run: runtimeState.selectedWorkflowRun,
    runs: runtimeState.workflowRuns,
  });
}, 2000);

server.listen(PORT, () => {
  console.log(`[SERVER] AI Employee backend running on port ${PORT}`);
});
