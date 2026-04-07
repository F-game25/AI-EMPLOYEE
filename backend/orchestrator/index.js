'use strict';

const { Router } = require('express');

const router = Router();

router.post('/message', (req, res) => {
  const { message } = req.body || {};
  if (!message) {
    return res.status(400).json({ error: 'message is required' });
  }
  res.json({
    reply: `Processing your request: ${message}`,
    agent: 'ORCHESTRATOR',
    timestamp: new Date().toISOString(),
  });
});

module.exports = router;
