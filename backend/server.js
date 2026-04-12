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
} = require('./agents');
const subsystems = require('./subsystems');
const { buildMoneyTemplate, buildThinkingSummary } = require('./money_mode');

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
const BASE_PIPELINE_ROI = 250;
const PIPELINE_ROI_SWING = 400;
const REVENUE_CONVERSION_RATE = 0.45;

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
    pipelines: {
      total_estimated_roi: runtimeState.pipelineRoiTotal,
      runs: runtimeState.pipelineRuns.length,
    },
    pipeline_runs: runtimeState.pipelineRuns,
    pending_actions: [],
    learning: {
      mode: getMode(),
    },
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
    cpu_temperature: cpuTemp,
    gpu_temperature: gpuTemp,
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
  res.json(subsystems.getNNStatus());
});

app.get('/api/memory/tree', (req, res) => {
  res.json(subsystems.getMemoryTree());
});

app.get('/api/doctor/status', (req, res) => {
  res.json(subsystems.getDoctorStatus());
});

app.get('/api/product/dashboard', (req, res) => {
  res.json(buildDashboardPayload());
});

app.post('/api/automation/control', (req, res) => {
  const action = String((req.body || {}).action || '').toLowerCase();
  const goal = String((req.body || {}).goal || '').trim();
  const overrideActionId = String((req.body || {}).override_action_id || '').trim();

  if (action === 'start') {
    activateAgents(3);
    runtimeState.automationRunning = true;
    addActivity(`[AUTOMATION] started${goal ? ` • goal: ${goal}` : ''}`, 'automation');
    // Submit initial tasks so the agent execution loop becomes visible immediately
    const taskMessages = [
      goal || 'Analyze current market conditions',
      'Generate value opportunities',
      'Route prioritized tasks to agents',
    ];
    const queued = taskMessages.map(msg => orchestrator.submitTask(msg));
    return res.json({ status: 'running', message: 'Automation started.', tasks_queued: queued.length });
  }

  if (action === 'stop') {
    activateAgents(1);
    runtimeState.automationRunning = false;
    addActivity('[AUTOMATION] stopped', 'automation');
    return res.json({ status: 'stopped', message: 'Automation stopped.' });
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
  const result = orchestrator.submitTask(message);
  addActivity(`[TASK] Submitted: ${message}`, 'task');
  res.json({ ok: true, ...result });
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
        const queued = orchestrator.submitTask(parsed.message);
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
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] completed ${task.id}`,
    level: 'success',
    heartbeat: heartbeatCounter,
  });
});

orchestrator.on('orchestrator:reply', (data) => {
  broadcaster.broadcast('orchestrator:message', data);
});

setInterval(() => {
  broadcaster.broadcast('system:status', sampleSystemStatus());
  broadcaster.broadcast('nn:status', subsystems.getNNStatus());
  broadcaster.broadcast('memory:update', subsystems.getMemoryTree());
  broadcaster.broadcast('doctor:check', subsystems.getDoctorStatus());
}, 2000);

server.listen(PORT, () => {
  console.log(`[SERVER] AI Employee backend running on port ${PORT}`);
});
