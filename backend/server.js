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
} = require('./agents');
const subsystems = require('./subsystems');

const PORT = process.env.PORT || 3001;

const app = express();

app.use(cors());
app.use(express.json());

app.use('/gateway', gateway);
app.use('/orchestrator', orchestrator.router);

let gpuUsage = 18;
let heartbeat = 0;

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

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
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
  gpuUsage = clamp(
    Math.round(gpuUsage + (Math.random() * GPU_RANDOM_SWING - GPU_SWING_OFFSET) + (cpu - GPU_CPU_BASELINE) * GPU_CPU_INFLUENCE),
    4,
    97,
  );
  const cpuTemp = clamp(Math.round(CPU_TEMP_BASE + cpu * CPU_TEMP_CPU_FACTOR + Math.random() * CPU_TEMP_JITTER), 32, 95);
  const gpuTemp = clamp(Math.round(GPU_TEMP_BASE + gpuUsage * GPU_TEMP_GPU_FACTOR + Math.random() * GPU_TEMP_JITTER), 30, 90);

  const total = getAgents().length;
  const running = getRunningAgentCount();

  return {
    cpu,
    memory,
    uptime: process.uptime(),
    connections: wss ? wss.clients.size : 0,
    cpu_usage: cpu,
    gpu_usage: gpuUsage,
    cpu_temperature: cpuTemp,
    gpu_temperature: gpuTemp,
    heartbeat,
    running_agents: running,
    total_agents: total,
    mode: getMode(),
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
  res.json({ mode: getMode() });
});

app.post('/api/mode', (req, res) => {
  const next = String((req.body || {}).mode || '').toUpperCase();
  const mode = setMode(next);
  res.json({ mode });
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

  ws.on('message', (raw) => {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.type === 'chat' && parsed.message) {
        const queued = orchestrator.submitTask(parsed.message);
        broadcaster.broadcast('orchestrator:queued', queued);
        broadcaster.broadcast('heartbeat', {
          message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
          level: 'info',
          heartbeat,
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
    heartbeat = seq;
    const stats = sampleSystemStatus();
    return `[SYSTEM] heartbeat=${seq} mode=${stats.mode} running=${stats.running_agents}/${stats.total_agents}`;
  },
});

onAgentEvent('agent:update', (agents) => {
  broadcaster.broadcast('agent:update', { agents });
});

onAgentEvent('task:started', ({ agent, task }) => {
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] started ${task.id}`,
    level: 'info',
    heartbeat,
  });
});

onAgentEvent('task:completed', ({ agent, task }) => {
  broadcaster.broadcast('heartbeat', {
    message: `[${agent.name}] completed ${task.id}`,
    level: 'success',
    heartbeat,
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
