'use strict';

/**
 * Sandbox management routes.
 *   GET  /api/sandbox/status   — sandbox type + limits
 *   POST /api/sandbox/run      — execute a command in sandbox (admin only)
 */

const { Router } = require('express');
const { getSandboxExecutor, LIMITS } = require('./executor');
const router = Router();

router.get('/status', async (req, res) => {
  const executor = await getSandboxExecutor();
  res.json({ ok: true, sandbox_type: executor.sandboxType, available_profiles: Object.keys(LIMITS) });
});

// Admin-only direct execution endpoint (for testing / agent orchestrator)
router.post('/run', async (req, res) => {
  const { agent_id, command, env = {}, profile = 'default' } = req.body || {};
  if (!agent_id || !Array.isArray(command) || command.length === 0) {
    return res.status(400).json({ ok: false, error: 'agent_id and command[] required' });
  }
  try {
    const executor = await getSandboxExecutor();
    const result = await executor.run({
      agent_id,
      command,
      env,
      profile,
      tenant_id: req.tenantId || 'system',
      trace_id:  req.headers['x-trace-id'],
    });
    // Strip env from response — never echo injected secrets
    const { audit, success, exit_code, stdout, stderr, duration_ms, sandbox_type } = result;
    res.json({ ok: success, exit_code, stdout, stderr, duration_ms, audit });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

module.exports = router;
