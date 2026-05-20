'use strict';

/**
 * Workflow management API routes.
 *
 *   POST /api/workflows/start            — start a named workflow
 *   GET  /api/workflows/:id              — get execution state
 *   GET  /api/workflows                  — list executions
 *   POST /api/workflows/:id/signal       — send signal (HITL approval, etc.)
 *   POST /api/workflows/:id/cancel       — cancel execution
 */

const { Router } = require('express');
const { getWorkflowEngine, WF_STATE, BUILT_IN_WORKFLOWS } = require('./engine');
const router = Router();

router.get('/', async (req, res) => {
  try {
    const engine = await getWorkflowEngine();
    const { tenant_id, state, limit } = req.query;
    const executions = await engine.listExecutions({
      tenant_id: tenant_id || req.tenantId,
      state,
      limit: parseInt(limit) || 50,
    });
    res.json({ ok: true, executions, transport: engine.transportName });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

router.get('/definitions', (req, res) => {
  res.json({ ok: true, workflows: Object.keys(BUILT_IN_WORKFLOWS) });
});

router.post('/start', async (req, res) => {
  const { workflow_name, input = {}, tenant_id } = req.body || {};
  if (!workflow_name) return res.status(400).json({ ok: false, error: 'workflow_name required' });
  try {
    const engine = await getWorkflowEngine();
    const result = await engine.startWorkflow(workflow_name, input, {
      tenant_id: tenant_id || req.tenantId || 'system',
      trace_id: req.headers['x-trace-id'],
    });
    res.status(202).json({ ok: true, ...result });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const engine = await getWorkflowEngine();
    const execution = await engine.getExecution(req.params.id);
    if (!execution) return res.status(404).json({ ok: false, error: 'Workflow not found' });
    res.json({ ok: true, execution });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

router.post('/:id/signal', async (req, res) => {
  const { signal, payload = {} } = req.body || {};
  if (!signal) return res.status(400).json({ ok: false, error: 'signal name required' });
  try {
    const engine = await getWorkflowEngine();
    const result = await engine.signal(req.params.id, signal, payload);
    res.json(result);
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

router.post('/:id/cancel', async (req, res) => {
  try {
    const engine = await getWorkflowEngine();
    await engine.cancelWorkflow(req.params.id, req.body?.reason || '');
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

module.exports = router;
