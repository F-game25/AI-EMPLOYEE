'use strict';

const WebSocket = require('ws');

let wss = null;
let heartbeatTimer = null;
let heartbeatSeq = 0;

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

function startHeartbeat({
  intervalMs = 2000,
  messageFactory = () => '[SYSTEM] Heartbeat OK',
} = {}) {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(() => {
    heartbeatSeq += 1;
    const msg = messageFactory({ seq: heartbeatSeq });
    broadcast('heartbeat', { message: msg, level: 'info', heartbeat: heartbeatSeq });
  }, intervalMs + randomInt(-300, 300));
}

function getHeartbeatSeq() {
  return heartbeatSeq;
}

module.exports = { init, broadcast, startHeartbeat, getHeartbeatSeq };
