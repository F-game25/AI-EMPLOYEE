'use strict';

const { Router } = require('express');
const subsystems = require('../subsystems');

const router = Router();

router.post('/message', (req, res) => {
  const { message } = req.body || {};
  if (!message) {
    return res.status(400).json({ error: 'message is required' });
  }

  const msg = message.toLowerCase();
  let reply;
  let subsystem = null;

  if (/brain|neural|nn|learn|network|decision|confidence|loss/.test(msg)) {
    const nn = subsystems.getNNStatus();
    subsystem = 'nn';
    reply = `[NEURAL BRAIN] Mode: ${nn.mode} | Step: ${nn.learn_step} | Buffer: ${nn.buffer_size} | Confidence: ${(nn.confidence * 100).toFixed(1)}%`;
  } else if (/memory|remember|know|entity|fact|store/.test(msg)) {
    const mem = subsystems.getMemoryTree();
    subsystem = 'memory';
    reply = `[MEMORY TREE] ${mem.total_entities} entities stored | Last: ${mem.recent_updates[0] ? mem.recent_updates[0].entity_id : 'none'}`;
  } else if (/doctor|health|check|diagnos|status|grade|score/.test(msg)) {
    const dr = subsystems.getDoctorStatus();
    subsystem = 'doctor';
    reply = `[DOCTOR] Grade: ${dr.grade || 'N/A'} | Score: ${dr.overall_score}/100 | Issues: ${dr.issues.length}`;
  } else {
    reply = `Processing your request: ${message}`;
  }

  res.json({
    reply,
    subsystem,
    agent: 'ORCHESTRATOR',
    timestamp: new Date().toISOString(),
  });
});

module.exports = router;
