'use strict';

const http = require('http');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');

const gateway = require('./gateway');
const orchestrator = require('./orchestrator');
const broadcaster = require('./events/broadcaster');
const { getAgents } = require('./agents');
const subsystems = require('./subsystems');

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

// ── Subsystem API endpoints ───────────────────────────────────────────────────

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
  ws.send(JSON.stringify({ event: 'system:status', data: { connected: true }, timestamp: new Date().toISOString() }));

  // Send current subsystem state immediately on connection
  ws.send(JSON.stringify({ event: 'nn:status', data: subsystems.getNNStatus(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'memory:update', data: subsystems.getMemoryTree(), timestamp: new Date().toISOString() }));
  ws.send(JSON.stringify({ event: 'doctor:check', data: subsystems.getDoctorStatus(), timestamp: new Date().toISOString() }));

  ws.on('message', (raw) => {
    try {
      const parsed = JSON.parse(raw);
      if (parsed.type === 'chat' && parsed.message) {
        const msg = parsed.message.toLowerCase();

        // Route to relevant subsystem based on message content
        if (/brain|neural|nn|learn|network|decision|confidence|loss/.test(msg)) {
          const nn = subsystems.getNNStatus();
          broadcaster.broadcast('orchestrator:message', {
            message: `[NEURAL BRAIN] Status: ${nn.mode} | Step: ${nn.learn_step} | Buffer: ${nn.buffer_size} | Confidence: ${(nn.confidence * 100).toFixed(1)}% | Last action: ${nn.recent_outputs[0]?.action || 'N/A'}`,
            from: 'NEURAL-BRAIN',
            subsystem: 'nn',
          });
        } else if (/memory|remember|know|entity|fact|store/.test(msg)) {
          const mem = subsystems.getMemoryTree();
          broadcaster.broadcast('orchestrator:message', {
            message: `[MEMORY TREE] ${mem.total_entities} entities stored. Recent update: ${mem.recent_updates[0] ? `${mem.recent_updates[0].entity_id} → ${mem.recent_updates[0].key}` : 'none'}`,
            from: 'MEMORY-TREE',
            subsystem: 'memory',
          });
        } else if (/doctor|health|check|diagnos|status|grade|score/.test(msg)) {
          const dr = subsystems.getDoctorStatus();
          broadcaster.broadcast('orchestrator:message', {
            message: `[DOCTOR] Grade: ${dr.grade || 'N/A'} | Score: ${dr.overall_score}/100 | Issues: ${dr.issues.length} | Strengths: ${dr.strengths.length}`,
            from: 'DOCTOR',
            subsystem: 'doctor',
          });
        } else {
          broadcaster.broadcast('orchestrator:message', {
            message: `Processing: ${parsed.message}`,
            from: 'ORCHESTRATOR',
          });
        }
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
broadcaster.startHeartbeat();

server.listen(PORT, () => {
  console.log(`[SERVER] AI Employee backend running on port ${PORT}`);
});
