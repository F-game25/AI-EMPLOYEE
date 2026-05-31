'use strict';

const WebSocket = require('ws');

let wss = null;
let heartbeatTimer = null;
let heartbeatSeq = 0;

function init(wsServer) {
  wss = wsServer;
  console.log(`[broadcaster] init called — wss has ${wsServer?.clients?.size ?? 'no'} clients at init`);
  setInterval(() => {
    if (wss) console.log(`[broadcaster] periodic check — wss.clients.size = ${wss.clients.size}`);
  }, 5000).unref();
}

let _bcCount = 0;
function broadcast(event, data) {
  if (_bcCount === 0) {
    console.log('[broadcaster] FIRST broadcast call — wss:', typeof wss, wss ? 'truthy' : 'falsy', 'event:', event);
    console.log('[broadcaster] FIRST call stack:', new Error().stack.split('\n').slice(1, 5).join(' || '));
  }
  if (!wss) return;
  const payload = JSON.stringify({ event, data, timestamp: new Date().toISOString() });
  let sent = 0;
  let total = 0;
  wss.clients.forEach((client) => {
    total++;
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
      sent++;
    }
  });
  _bcCount++;
  if (_bcCount <= 5 || _bcCount % 100 === 0) {
    console.log(`[broadcaster] #${_bcCount} event=${event} clients=${total} sent=${sent}`);
  }
}

// Deterministic jitter based on heartbeat sequence (avoids Math.random).
function deterministicJitter(seq, min, max) {
  const range = max - min + 1;
  return min + ((seq * 37) % range);
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
  }, intervalMs + deterministicJitter(heartbeatSeq, -300, 300));
}

function getHeartbeatSeq() {
  return heartbeatSeq;
}

module.exports = { init, broadcast, startHeartbeat, getHeartbeatSeq };
