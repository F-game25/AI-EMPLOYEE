'use strict';

const { getAgents, updateAgentStatus } = require('../agents');
const WebSocket = require('ws');

let wss = null;
let eventIndex = 0;

const LOG_LINES = [
  { msg: '[AI-1] Processing lead analysis...', level: 'info' },
  { msg: '[AI-2] Generating response...', level: 'info' },
  { msg: '[ORCHESTRATOR] Routing task...', level: 'info' },
  { msg: '[SYSTEM] Memory usage stable', level: 'info' },
  { msg: '[AI-3] Searching knowledge base...', level: 'info' },
  { msg: '[GATEWAY] Request received', level: 'info' },
  { msg: '[AI-1] Task completed', level: 'success' },
  { msg: '[ORCHESTRATOR] Assigning to agent...', level: 'info' },
  { msg: '[AI-5] Retrying failed extraction', level: 'warning' },
  { msg: '[AI-4] Route resolved successfully', level: 'success' },
];

const STATUSES = ['idle', 'working', 'error'];
const AGENT_IDS = ['ai-1', 'ai-2', 'ai-3', 'ai-4', 'ai-5', 'ai-6'];

function init(wsServer) {
  wss = wsServer;
}

function broadcast(event, data) {
  if (!wss) return;
  const payload = JSON.stringify({ event, data, timestamp: new Date().toISOString() });
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
    }
  });
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function emitHeartbeat() {
  const log = LOG_LINES[randomInt(0, LOG_LINES.length - 1)];
  broadcast('heartbeat', { message: log.msg, level: log.level });
}

function emitAgentUpdate() {
  const id = AGENT_IDS[randomInt(0, AGENT_IDS.length - 1)];
  const status = STATUSES[randomInt(0, STATUSES.length - 1)];
  const task = status === 'working' ? `[AUTO] Task assigned at ${new Date().toLocaleTimeString()}` : null;
  updateAgentStatus(id, status, task);
  broadcast('agent:update', { agents: getAgents() });
}

function emitSystemStatus() {
  broadcast('system:status', {
    cpu: randomInt(20, 80),
    memory: randomInt(30, 70),
    uptime: process.uptime(),
    connections: wss ? wss.clients.size : 0,
  });
}

function scheduleNext() {
  const delay = randomInt(500, 1500);
  setTimeout(() => {
    const type = eventIndex % 3;
    if (type === 0) emitHeartbeat();
    else if (type === 1) emitAgentUpdate();
    else emitSystemStatus();
    eventIndex++;
    scheduleNext();
  }, delay);
}

function startHeartbeat() {
  scheduleNext();
}

module.exports = { init, broadcast, startHeartbeat };
