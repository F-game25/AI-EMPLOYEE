'use strict';

module.exports = function createBusinessOpsRouter(deps) {
  const router = require('express').Router();
  const {
    requireAuth,
    validate,
    SCHEMAS,
    STATE_DIR,
    path,
    fs,
    runtimeState,
    reliabilityState,
    _auditLog,
    broadcaster,
    readJsonSafe,
    statePath,
    buildEconomySnapshot,
    walletSnapshot,
    buildDashboardPayload,
    runPipeline,
    requestPythonJSON,
    pythonServiceAuthorization,
    activateAgents,
    stopAllAgents,
    addActivity,
    createWorkflowRun,
    queueWorkflowStep,
    markWorkflowsStopped,
    handleGoalDrivenCommand,
    runForgePython,
  } = deps;

  // ── Product ───────────────────────────────────────────────────────────────────

  router.get('/api/product/dashboard', requireAuth, (req, res) => {
    res.json(buildDashboardPayload());
  });

  // ── Economy ───────────────────────────────────────────────────────────────────

  router.get('/api/economy/summary', requireAuth, (req, res) => {
    const economy = buildEconomySnapshot();
    res.json({ ok: true, ...economy.summary });
  });

  router.get('/api/economy/ledger', requireAuth, (req, res) => {
    const economy = buildEconomySnapshot();
    res.json({
      ok: true,
      state: economy.ledger.length ? 'live' : 'empty',
      source: 'node_runtime_state',
      ledger: economy.ledger,
      items: economy.ledger,
      updated_at: new Date().toISOString(),
    });
  });

  router.get('/api/economy/costs', requireAuth, (req, res) => {
    const economy = buildEconomySnapshot();
    res.json({
      ok: true,
      state: economy.costs.length ? 'live' : 'empty',
      source: 'llm_call_log',
      costs: economy.costs,
      items: economy.costs,
      updated_at: new Date().toISOString(),
    });
  });

  router.get('/api/economy/pipelines', requireAuth, (req, res) => {
    const economy = buildEconomySnapshot();
    res.json({
      ok: true,
      state: economy.pipelines.some((pipeline) => pipeline.active) ? 'live' : 'empty',
      source: 'node_objective_state',
      pipelines: economy.pipelines,
      items: economy.pipelines,
      updated_at: new Date().toISOString(),
    });
  });

  router.get('/api/economy/opportunities', requireAuth, (req, res) => {
    const opportunities = readJsonSafe(statePath('opportunities.json'), []);
    res.json({
      ok: true,
      state: opportunities.length ? 'live' : 'empty',
      source: 'node_state',
      opportunities,
      items: opportunities,
      updated_at: new Date().toISOString(),
    });
  });

  router.get('/api/economy/wallet', requireAuth, (req, res) => {
    res.json({ ok: true, source: 'wallet_vault', wallet: walletSnapshot(), updated_at: new Date().toISOString() });
  });

  // ── Objectives ────────────────────────────────────────────────────────────────

  router.get('/api/objectives/status', requireAuth, (req, res) => {
    res.json({
      objectives: runtimeState.objectives,
      systems: runtimeState.objectiveState,
    });
  });

  // ── Automation control ────────────────────────────────────────────────────────

  router.post('/api/automation/control', requireAuth, (req, res) => {
    const _bodyAuto = validate(SCHEMAS.automationControl, req, res);
    if (!_bodyAuto) return;
    const action = String(_bodyAuto.action || '').toLowerCase();
    const goal = String(_bodyAuto.goal || '').trim();
    const overrideActionId = String(_bodyAuto.override_action_id || '').trim();

    if (action === 'start') {
      activateAgents(3);
      runtimeState.automationRunning = true;
      addActivity(`[AUTOMATION] started${goal ? ` • goal: ${goal}` : ''}`, 'automation');
      const run = createWorkflowRun({
        name: 'Automation Goal Workflow',
        source: 'automation',
        goal: goal || 'Execute automation cycle',
      });
      const taskMessages = [
        goal || 'Analyze current market conditions',
        'Generate value opportunities',
        'Route prioritized tasks to agents',
      ];
      runtimeState.workflowSequencers[run.run_id] = {
        messages: taskMessages,
        queuedSteps: new Set([0]),
        completedSteps: new Set(),
        stepTaskIds: {},
        stopped: false,
      };
      queueWorkflowStep({
        runId: run.run_id,
        message: taskMessages[0],
        stepIndex: 0,
        labels: ['automation', 'step-1'],
        parentTaskId: null,
      });
      return res.json({ status: 'running', message: 'Automation started.', tasks_queued: 1, workflow_run: run.run_id });
    }

    if (action === 'stop') {
      Object.values(runtimeState.workflowSequencers).forEach((seq) => {
        seq.stopped = true;
      });
      runtimeState.automationRunning = false;
      const stopResult = stopAllAgents('automation_stop');
      markWorkflowsStopped();
      addActivity('[AUTOMATION] stopped', 'automation');
      return res.json({
        status: 'stopped',
        message: 'Automation stopped.',
        cancelled_tasks: stopResult.cancelledTasks,
        running_agents: stopResult.runningAgents,
      });
    }

    if (action === 'override') {
      if (!overrideActionId) {
        return res.status(400).json({ status: 'error', reason: 'override_action_id is required.' });
      }
      addActivity(`[AUTOMATION] manual override executed for ${overrideActionId}`, 'automation');
      return res.json({ status: 'ok', message: `Override applied to ${overrideActionId}.` });
    }

    return res.status(400).json({ status: 'error', reason: 'Invalid automation action.' });
  });

  // ── Money pipelines ───────────────────────────────────────────────────────────

  router.post('/api/money/content-pipeline', requireAuth, async (req, res) => {
    const _bodyContent = validate(SCHEMAS.moneyPipeline, req, res);
    if (!_bodyContent) return;
    try {
      const result = await requestPythonJSON('/api/money/content-pipeline', 'POST', _bodyContent, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });
      if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] Python content pipeline unavailable: %s', err && err.message);
    }
    const run = runPipeline('content');
    res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
  });

  router.post('/api/money/lead-pipeline', requireAuth, async (req, res) => {
    const _bodyLead = validate(SCHEMAS.moneyPipeline, req, res);
    if (!_bodyLead) return;
    try {
      const result = await requestPythonJSON('/api/money/lead-pipeline', 'POST', _bodyLead, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });
      if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] Python lead pipeline unavailable: %s', err && err.message);
    }
    const run = runPipeline('lead');
    res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
  });

  router.post('/api/money/opportunity-pipeline', requireAuth, async (req, res) => {
    const _bodyOpp = validate(SCHEMAS.moneyPipeline, req, res);
    if (!_bodyOpp) return;
    try {
      const result = await requestPythonJSON('/api/money/opportunity-pipeline', 'POST', _bodyOpp, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });
      if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] Python opportunity pipeline unavailable: %s', err && err.message);
    }
    const run = runPipeline('opportunity');
    res.json({ status: run.status, pipeline: run.pipeline, estimated_roi: run.estimated_roi, run_id: run.id, source: 'node_fallback' });
  });

  router.post('/api/money/affiliate-draft', requireAuth, async (req, res) => {
    const _bodyAffiliate = validate(SCHEMAS.moneyPipeline, req, res);
    if (!_bodyAffiliate) return;
    try {
      const result = await requestPythonJSON('/api/money/affiliate-draft', 'POST', _bodyAffiliate, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });
      if (result && result.job_id) return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] Python affiliate draft unavailable: %s', err && err.message);
    }
    return res.status(503).json({
      ok: false,
      error: 'Python MoneyMode backend unavailable; affiliate drafts require the approval-aware Python pipeline.',
    });
  });

  // ── Business-building money workflows (proxy to Python) ──────────────────────

  router.post('/api/money/niche-research', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/money/niche-research', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 45000,
      });
      return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] niche-research unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'Python backend unavailable', requires_manual: true });
    }
  });

  router.post('/api/money/offer-creation', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/money/offer-creation', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 45000,
      });
      return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] offer-creation unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'Python backend unavailable', requires_manual: true });
    }
  });

  router.post('/api/money/content-calendar', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/money/content-calendar', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 45000,
      });
      return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] content-calendar unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'Python backend unavailable', requires_manual: true });
    }
  });

  router.post('/api/money/lead-research', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/money/lead-research', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 45000,
      });
      return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] lead-research unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'Python backend unavailable', requires_manual: true, cold_outreach_blocked: true });
    }
  });

  router.post('/api/money/proposal', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/money/proposal', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 45000,
      });
      return res.json({ ...result, source: 'python_money_mode' });
    } catch (err) {
      console.warn('[MONEY] proposal unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'Python backend unavailable — proposals require approval-aware pipeline', requires_manual: true });
    }
  });

  router.get('/api/money/content-log', requireAuth, (req, res) => {
    const p = path.join(STATE_DIR, 'content_log.json');
    try { res.json({ ok: true, entries: JSON.parse(fs.readFileSync(p, 'utf8')) }); }
    catch { res.json({ ok: true, entries: [] }); }
  });

  router.get('/api/money/outreach-log', requireAuth, (req, res) => {
    const p = path.join(STATE_DIR, 'outreach_log.json');
    try { res.json({ ok: true, entries: JSON.parse(fs.readFileSync(p, 'utf8')) }); }
    catch { res.json({ ok: true, entries: [] }); }
  });

  // ── Roadmap Engine routes (proxy to Python) ──────────────────────────────────

  router.post('/api/roadmap/create', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/roadmap/create', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 30000,
      });
      return res.json(result);
    } catch (err) {
      console.warn('[ROADMAP] create unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'roadmap service unavailable' });
    }
  });

  router.post('/api/roadmap/generate', requireAuth, async (req, res) => {
    try {
      const result = await requestPythonJSON('/roadmap/generate', 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 60000,
      });
      return res.json(result);
    } catch (err) {
      console.warn('[ROADMAP] generate unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'roadmap service unavailable' });
    }
  });

  router.get('/api/roadmap/list/:tenantId', requireAuth, async (req, res) => {
    try {
      const tenantId = encodeURIComponent(String(req.params.tenantId || '').trim());
      if (!tenantId) return res.status(400).json({ ok: false, error: 'tenantId required' });
      const result = await requestPythonJSON(`/api/roadmap/list/${tenantId}`, 'GET', null, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 15000,
      });
      return res.json(result);
    } catch (err) {
      console.warn('[ROADMAP] list unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, roadmaps: [], error: 'roadmap service unavailable' });
    }
  });

  router.get('/api/roadmap/:roadmapId', requireAuth, async (req, res) => {
    try {
      const roadmapId = encodeURIComponent(String(req.params.roadmapId || '').trim());
      if (!roadmapId) return res.status(400).json({ ok: false, error: 'roadmapId required' });
      const result = await requestPythonJSON(`/api/roadmap/${roadmapId}`, 'GET', null, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 15000,
      });
      return res.json(result);
    } catch (err) {
      console.warn('[ROADMAP] get unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'roadmap service unavailable' });
    }
  });

  router.post('/api/roadmap/:roadmapId/execute', requireAuth, async (req, res) => {
    try {
      const roadmapId = encodeURIComponent(String(req.params.roadmapId || '').trim());
      if (!roadmapId) return res.status(400).json({ ok: false, error: 'roadmapId required' });
      const result = await requestPythonJSON(`/api/roadmap/${roadmapId}/execute`, 'POST', req.body, {
        headers: { Authorization: pythonServiceAuthorization(req) },
        timeoutMs: 120000,
      });
      return res.json(result);
    } catch (err) {
      console.warn('[ROADMAP] execute unavailable: %s', err && err.message);
      return res.status(503).json({ ok: false, error: 'roadmap service unavailable' });
    }
  });

  // ── Fairness & Governance ─────────────────────────────────────────────────────

  router.get('/api/fairness/report', requireAuth, (req, res) => {
    const agents = Object.keys(runtimeState.objectiveState || {});
    const total_actions = (_auditLog || []).length;
    const high_risk = (_auditLog || []).filter((e) => e.risk_score >= 0.7).length;
    const by_actor = {};
    (_auditLog || []).forEach((e) => {
      by_actor[e.actor] = (by_actor[e.actor] || 0) + 1;
    });
    res.json({
      agents_monitored: agents.length,
      total_actions,
      high_risk_actions: high_risk,
      risk_rate: total_actions ? (high_risk / total_actions).toFixed(3) : '0.000',
      by_actor,
      demographic_parity: 'N/A — no demographic data collected',
      disparate_impact: 'N/A — no demographic data collected',
    });
  });

  router.get('/api/governance/digest', requireAuth, async (req, res) => {
    const limit = Math.min(50, parseInt((req.query || {}).limit) || 25);
    const events = (_auditLog || []).slice(0, limit);
    const result = await runForgePython({ operation: 'governance_digest', events });
    res.json({ digest: result?.digest || 'Could not generate digest.', generated_at: new Date().toISOString() });
  });

  // ── Hermes (task routing) ─────────────────────────────────────────────────────

  router.get('/api/hermes/status', requireAuth, (req, res) => {
    const agents = Object.entries(runtimeState.objectiveState || {}).map(([name, state]) => ({
      name,
      active: state?.active || false,
      status: state?.status || 'inactive',
    }));
    res.json({
      active_agents: agents.filter((a) => a.active).length,
      total_agents: agents.length,
      agents,
      forge_frozen: reliabilityState?.forgeFrozen || false,
    });
  });

  router.post('/api/hermes/task', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.hermesTask, req, res);
    if (!body) return;
    const message = String(body.message || '').trim();
    const target_agent = String(body.target_agent || '').trim();
    const result = handleGoalDrivenCommand(message);
    addActivity(`[HERMES] Task routed to ${target_agent || 'auto'}: ${message.slice(0, 60)}`, 'automation');
    res.json({ ok: true, handled: result?.handled || false, response: result?.reply || result?.message || null, agent: target_agent });
  });

  router.post('/api/hermes/broadcast', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.hermesBroadcast, req, res);
    if (!body) return;
    const message = String(body.message || '').trim();
    broadcaster.broadcast('orchestrator:message', {
      message,
      from: 'hermes',
      agentId: 'hermes',
      timestamp: new Date().toISOString(),
      broadcast: true,
    });
    addActivity(`[HERMES] Broadcast: ${message.slice(0, 60)}`, 'automation');
    res.json({ ok: true, message, recipients: 'all_connected_clients' });
  });

  return router;
};
