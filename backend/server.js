'use strict';

const http = require('http');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');

const gateway = require('./gateway');
const orchestrator = require('./orchestrator');
const broadcaster = require('./events/broadcaster');
const { getAgents } = require('./agents');

const PORT = process.env.PORT || 3001;

const app = express();

app.use(cors());
app.use(express.json());

app.use('/gateway', gateway);
app.use('/orchestrator', orchestrator);

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() });
});

app.get('/agents', (req, res) => {
  res.json({ agents: getAgents() });
});

app.get('/status', (req, res) => {
  res.json({ status: 'online', agents: getAgents().length, timestamp: new Date().toISOString() });
});

const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (ws) => {
  ws.send(JSON.stringify({ event: 'system:status', data: { connected: true }, timestamp: new Date().toISOString() }));

  ws.on('message', (raw) => {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.type === 'chat' && parsed.message) {
        broadcaster.broadcast('orchestrator:message', {
          message: 'Processing: ' + parsed.message,
          from: 'ORCHESTRATOR',
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
broadcaster.startHeartbeat();

server.listen(PORT, () => {
  console.log(`[SERVER] AI Employee backend running on port ${PORT}`);
});
