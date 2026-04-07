'use strict';

const { Router } = require('express');

const router = Router();

router.get('/status', (req, res) => {
  res.json({
    status: 'online',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
  });
});

module.exports = router;
