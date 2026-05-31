'use strict';

const fs   = require('fs');
const path = require('path');

// ── Constants (mirror values from server.js) ──────────────────────────────────
const OBJECTIVE_STATUS = {
  INACTIVE:  'inactive',
  WAITING:   'waiting',
  RUNNING:   'running',
  COMPLETED: 'completed',
};

const MAX_ACTIVITY_ITEMS       = 50;
const MAX_DECISION_LOG_ENTRIES = 30;
const MAX_EXECUTION_LOGS       = 100; // exported for callers that need it
const MAX_OBSERVABILITY_EVENTS = 300;
const CANCELLATION_ERROR_PREFIX = 'cancelled:';

const MONEY_MODE_AGENTS   = ['lead_hunter', 'email_ninja', 'intel_agent', 'social_guru'];
const ASCEND_FORGE_AGENTS = ['intel_agent', 'email_ninja', 'social_guru'];

/**
 * createWorkflowService — factory that wires shared mutable state into all
 * workflow/objective helper functions, keeping them out of server.js.
 *
 * deps:
 *   broadcaster        — broadcaster module (.broadcast(event, data))
 *   runtimeState       — shared mutable runtime-state object
 *   securitySyncPolicy — offline-sync policy (.enqueueEvent)
 *   orchestrator       — orchestrator module (.submitTask)
 *   getForgeDb         — zero-arg fn returning the _forgeDb sqlite handle
 *   setMode            — fn(mode) from agents module
 *   activateAgents     — fn(count) from agents module
 *   objectivesFile     — absolute path to objectives.json
 */
function createWorkflowService({
  broadcaster,
  runtimeState,
  securitySyncPolicy,
  orchestrator,
  getForgeDb,
  setMode,
  activateAgents,
  objectivesFile,
}) {

  // ── Objective helpers ───────────────────────────────────────────────────────

  function persistObjectives() {
    try {
      fs.mkdirSync(path.dirname(objectivesFile), { recursive: true });
      fs.writeFileSync(objectivesFile, JSON.stringify(runtimeState.objectives, null, 2), 'utf8');
    } catch {
      // best effort
    }
  }

  function broadcastObjectiveUpdate(system) {
    const state = runtimeState.objectiveState[system];
    if (!state) return;
    broadcaster.broadcast('objective:update', {
      type: 'objective_update',
      system,
      status: state.status,
      progress: state.progress || 0,
      current_objective: state.current_objective,
      active_tasks: state.active_tasks || [],
      plan: state.plan || [],
      agents_used: state.agents_used || [],
      results: state.results || state.result || [],
      performance: state.performance || {},
    });
  }

  function normalizeConstraints(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return value;
  }

  function parseConstraintsFromGoal(goalText) {
    const text = String(goalText || '');
    const constraints = {};
    const lower = text.toLowerCase();
    const budgetTokenAt = lower.indexOf('budget');
    if (budgetTokenAt >= 0) {
      const numericBudget = lower.slice(budgetTokenAt).match(/\d+/);
      if (numericBudget) constraints.budget = Math.min(Number(numericBudget[0]), Number.MAX_SAFE_INTEGER);
    }
    const currencyBudget = text.match(/[€$]\s*(\d+)/);
    if (currencyBudget) constraints.budget = Math.min(Number(currencyBudget[1]), Number.MAX_SAFE_INTEGER);
    if (/\binstagram\b/i.test(text)) constraints.channel = 'instagram';
    if (/\bemail\b/i.test(text)) {
      constraints.channel = constraints.channel ? `${constraints.channel} + email` : 'email';
    }
    return constraints;
  }

  function createObjective({ system, goal, constraints = {}, priority = 'medium' }) {
    const objective = {
      id: `obj-${++runtimeState._seq}`,
      system,
      goal: String(goal || '').trim(),
      constraints: normalizeConstraints(constraints),
      priority: priority === 'high' ? 'high' : 'medium',
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    runtimeState.objectives.push(objective);
    runtimeState.objectives = runtimeState.objectives.slice(-200);
    persistObjectives();
    return objective;
  }

  function setObjectiveWaiting(system) {
    const state = runtimeState.objectiveState[system];
    if (!state) return;
    state.active = true;
    state.status = OBJECTIVE_STATUS.WAITING;
    state.current_objective = null;
    state.progress = 0;
    state.active_tasks = [];
    state.result = null;
    if (system === 'ascend_forge') {
      state.plan = [];
      state.results = [];
    }
    broadcastObjectiveUpdate(system);
  }

  function breakdownMoneyModeGoal(goal) {
    const g = String(goal || '').toLowerCase();
    const tasks = [];
    if (/\blead/.test(g)) tasks.push('find leads', 'qualify leads');
    if (/\bemail|outreach/.test(g)) tasks.push('write outreach emails', 'prepare campaign');
    if (/\binstagram|social/.test(g)) tasks.push('prepare instagram campaign');
    if (/\bconversion|funnel/.test(g)) tasks.push('analyze conversion blockers');
    if (tasks.length === 0) tasks.push('find leads', 'qualify leads', 'write outreach emails', 'prepare campaign');
    return [...new Set(tasks)];
  }

  function buildAscendForgePlan(goal) {
    const g = String(goal || '').toLowerCase();
    const plan = ['analyze baseline', 'identify bottlenecks'];
    if (/\bconversion|funnel/.test(g)) {
      plan.push('design conversion experiments', 'execute funnel optimization');
    } else {
      plan.push('define optimization plan', 'execute improvement sprint');
    }
    return plan;
  }

  function recalcObjectiveProgress(system) {
    const state = runtimeState.objectiveState[system];
    if (!state) return;
    const tasks = state.active_tasks || [];
    const total = tasks.length || 1;
    const completed = tasks.filter((t) => t.status === 'completed').length;
    const failed    = tasks.filter((t) => t.status === 'failed').length;
    state.progress = Math.round(((completed + failed) / total) * 100);
    if (tasks.length > 0 && (completed + failed) === tasks.length) {
      state.status = OBJECTIVE_STATUS.COMPLETED;
      state.active = false;
    } else if (tasks.length > 0) {
      state.status = OBJECTIVE_STATUS.RUNNING;
    }
  }

  // ── Activity / observability helpers ────────────────────────────────────────

  function addActivity(notes, kind = 'system') {
    const item = {
      id: `activity-${++runtimeState._seq}`,
      kind,
      notes,
      ts: new Date().toISOString(),
    };
    runtimeState.activityFeed.unshift(item);
    runtimeState.activityFeed = runtimeState.activityFeed.slice(0, MAX_ACTIVITY_ITEMS);
    broadcaster.broadcast('activity:item', item);
  }

  function emitTaskProgress(taskId, title, steps) {
    broadcaster.broadcast('task_progress', { taskId, title, steps, ts: Date.now() });
  }

  function isSecurityEventType(eventType) {
    return (
      eventType === 'honeypot_triggered'
      || eventType === 'anomaly_response'
      || String(eventType).startsWith('security_')
    );
  }

  function emitObservabilityEvent(eventType, payload = {}) {
    const event = {
      id: `obs-${++runtimeState._seq}`,
      ts: new Date().toISOString(),
      event_type: eventType,
      payload,
      trace_id: payload.trace_id || '',
    };
    runtimeState.observability.events.unshift(event);
    runtimeState.observability.events = runtimeState.observability.events.slice(0, MAX_OBSERVABILITY_EVENTS);
    broadcaster.broadcast('event_stream', event);
    if (isSecurityEventType(eventType)) securitySyncPolicy.enqueueEvent(eventType, payload);
    return event;
  }

  function appendAutoFixLog(entry) {
    const row = {
      id: `autofix-${++runtimeState._seq}`,
      ts: new Date().toISOString(),
      ...entry,
    };
    runtimeState.observability.autoFixLog.unshift(row);
    runtimeState.observability.autoFixLog = runtimeState.observability.autoFixLog.slice(0, MAX_ACTIVITY_ITEMS);
    emitObservabilityEvent('auto_fix_applied', row);
    return row;
  }

  // ── Workflow run management ─────────────────────────────────────────────────

  function _persistWorkflowRun(run) {
    try {
      getForgeDb().prepare(
        `INSERT OR REPLACE INTO workflow_runs (run_id, payload, updated_at)
         VALUES (?, ?, strftime('%s','now'))`
      ).run(run.run_id, JSON.stringify(run));
    } catch (_e) { /* non-fatal — in-memory state is authoritative */ }
  }

  function createWorkflowRun({ name, source = 'automation', goal = '' }) {
    const runId = `wf-${++runtimeState._seq}`;
    const run = {
      run_id: runId,
      name: name || `Workflow ${runId}`,
      source,
      goal,
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      progress_percent: 0,
      nodes: [],
      decision_log: [],
    };
    runtimeState.workflowRuns.unshift(run);
    runtimeState.workflowRuns = runtimeState.workflowRuns.slice(0, MAX_ACTIVITY_ITEMS);
    runtimeState.selectedWorkflowRun = runId;
    _persistWorkflowRun(run);
    broadcaster.broadcast('workflow:update', run);
    return run;
  }

  function appendDecision(run, entry) {
    run.decision_log.unshift(entry);
    run.decision_log = run.decision_log.slice(0, MAX_DECISION_LOG_ENTRIES);
  }

  function getWorkflowRun(runId) {
    return runtimeState.workflowRuns.find((r) => r.run_id === runId) || null;
  }

  function recalcWorkflowProgress(run) {
    const total = run.nodes.length || 1;
    let acc = 0, completed = 0, failed = 0;
    run.nodes.forEach((node) => {
      acc += Number(node.progress_percent || 0);
      if (node.status === 'completed') completed += 1;
      if (node.status === 'failed')    failed    += 1;
    });
    run.progress_percent = Math.round(acc / total);
    if (failed > 0) {
      run.status = completed > 0 ? 'completed_with_failures' : 'failed';
    } else if (completed === run.nodes.length && run.nodes.length > 0) {
      run.status = 'completed';
      run.progress_percent = 100;
    } else if (run.nodes.length > 0) {
      run.status = 'running';
    } else {
      run.status = 'pending';
    }
  }

  function attachWorkflowNode({ runId, queued, taskName, parentTaskId = null }) {
    const run = getWorkflowRun(runId);
    if (!run || !queued || !queued.taskId) return;
    const node = {
      task_id:          queued.taskId,
      task_name:        taskName || queued.subsystem || 'Task',
      status:           'pending',
      progress_percent: 5,
      subsystem:        queued.subsystem || 'general',
      agent:            queued.agentId || 'pending',
      queued_at:        queued.queuedAt || new Date().toISOString(),
      started_at:       null,
      completed_at:     null,
      parent_task_id:   parentTaskId,
      brain:            queued.brain || null,
      strategy:         queued.brain ? queued.brain.strategy : null,
      confidence:       queued.brain ? queued.brain.confidence : null,
      reasoning:        queued.brain ? queued.brain.reasoning : '',
      execution_flow:   queued.brain ? queued.brain.execution_flow : 'task->strategy->agent->action->result',
      result:           null,
    };
    run.nodes.push(node);
    appendDecision(run, {
      ts:      new Date().toISOString(),
      task_id: node.task_id,
      type:    'brain_decision',
      summary: node.reasoning || `Strategy ${node.strategy || 'default'} selected`,
    });
    runtimeState.workflowIndex[node.task_id] = runId;
    run.updated_at = new Date().toISOString();
    run.status = 'running';
    recalcWorkflowProgress(run);
    broadcaster.broadcast('workflow:update', run);
  }

  function updateWorkflowNode(taskId, updater) {
    const runId = runtimeState.workflowIndex[taskId];
    if (!runId) return;
    const run = getWorkflowRun(runId);
    if (!run) return;
    const node = run.nodes.find((n) => n.task_id === taskId);
    if (!node) return;
    updater(node, run);
    run.updated_at = new Date().toISOString();
    recalcWorkflowProgress(run);
    broadcaster.broadcast('workflow:update', run);
  }

  function markWorkflowsStopped() {
    runtimeState.workflowRuns.forEach((run) => {
      if (!['running', 'pending'].includes(run.status)) return;
      run.nodes.forEach((node) => {
        if (node.status === 'pending' || node.status === 'active') {
          node.status = 'failed';
          node.progress_percent = 100;
          node.completed_at = new Date().toISOString();
          node.result = { status: 'cancelled', summary: 'Cancelled by STOP ALL command' };
        }
      });
      run.updated_at = new Date().toISOString();
      recalcWorkflowProgress(run);
      run.status = 'stopped';
      broadcaster.broadcast('workflow:update', run);
    });
  }

  // ── Workflow sequencing ─────────────────────────────────────────────────────

  function queueWorkflowStep({
    runId,
    message,
    stepIndex    = 0,
    labels       = [],
    parentTaskId = null,
    retries      = 0,
    maxRetries   = 1,
  }) {
    const queued = orchestrator.submitTask(message, {
      userId:   'user:default',
      workflow: { runId, parentTaskId },
      labels,
    });
    attachWorkflowNode({ runId, queued, taskName: message, parentTaskId });
    runtimeState.workflowTaskMeta[queued.taskId] = { runId, stepIndex, message, labels, parentTaskId, retries, maxRetries };
    const seq = runtimeState.workflowSequencers[runId];
    if (seq) seq.stepTaskIds[stepIndex] = queued.taskId;
    addActivity(`[BRAIN] Strategy ${queued.brain?.strategy || 'default'} selected for ${queued.taskId}`, 'task');
    const traceId = `trace-${++runtimeState.observability._traceSeq}`;
    runtimeState.observability.traces[queued.taskId] = {
      trace_id:   traceId,
      user_input: message,
      intent:     queued.brain?.intent || queued.subsystem || 'general',
      agent:      queued.agentId || 'task_orchestrator',
      strategy:   queued.brain?.strategy || 'default',
      confidence: queued.brain?.confidence || 0,
      started_at: new Date().toISOString(),
      steps:      [],
    };
    emitObservabilityEvent('task_started',   { trace_id: traceId, task_id: queued.taskId, user_input: message, intent: queued.brain?.intent || queued.subsystem || 'general' });
    emitObservabilityEvent('agent_selected', { trace_id: traceId, task_id: queued.taskId, agent: queued.agentId || 'task_orchestrator' });
    emitObservabilityEvent('brain_decision', { trace_id: traceId, task_id: queued.taskId, strategy: queued.brain?.strategy || 'default', reasoning: queued.brain?.reasoning || '', confidence: queued.brain?.confidence || 0 });
    return queued;
  }

  function queueNextWorkflowStep(completedTaskId) {
    const meta = runtimeState.workflowTaskMeta[completedTaskId];
    if (!meta) return;
    const seq = runtimeState.workflowSequencers[meta.runId];
    if (!seq || seq.stopped) return;
    if (seq.stepTaskIds[meta.stepIndex] !== completedTaskId) return;
    seq.completedSteps.add(meta.stepIndex);
    const nextIndex   = meta.stepIndex + 1;
    const nextMessage = seq.messages[nextIndex];
    if (!nextMessage || seq.queuedSteps.has(nextIndex)) return;
    seq.queuedSteps.add(nextIndex);
    queueWorkflowStep({
      runId:        meta.runId,
      message:      nextMessage,
      stepIndex:    nextIndex,
      labels:       ['automation', `step-${nextIndex + 1}`],
      parentTaskId: completedTaskId,
    });
  }

  function retryWorkflowStep(failedTaskId) {
    const meta = runtimeState.workflowTaskMeta[failedTaskId];
    if (!meta) return false;
    if (meta.error?.startsWith(CANCELLATION_ERROR_PREFIX)) return false;
    const seq = runtimeState.workflowSequencers[meta.runId];
    if (!seq || seq.stopped) return false;
    if (seq.stepTaskIds[meta.stepIndex] !== failedTaskId) return false;
    if (meta.retries >= meta.maxRetries) return false;
    const retryNumber = meta.retries + 1;
    addActivity(`[RETRY] ${failedTaskId} retry ${retryNumber}/${meta.maxRetries}`, 'task');
    appendAutoFixLog({
      task_id: failedTaskId,
      issue:   meta.error || 'task failure',
      fix:     `Automatic retry ${retryNumber}/${meta.maxRetries}`,
      status:  'retrying',
    });
    queueWorkflowStep({
      runId:        meta.runId,
      message:      meta.message,
      stepIndex:    meta.stepIndex,
      labels:       [...meta.labels, `retry-${retryNumber}`],
      parentTaskId: meta.parentTaskId,
      retries:      retryNumber,
      maxRetries:   meta.maxRetries,
    });
    return true;
  }

  // ── High-level objective runners ────────────────────────────────────────────

  function startMoneyModeObjective(objective) {
    if (!objective || !objective.goal) {
      setObjectiveWaiting('money_mode');
      return { ok: false, message: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.' };
    }
    objective.status = 'running';
    objective.updated_at = new Date().toISOString();
    persistObjectives();
    setMode('MONEYMODE');
    activateAgents(4);
    const tasks = breakdownMoneyModeGoal(objective.goal);
    const run = createWorkflowRun({ name: 'Money Mode Objective', source: 'money_mode', goal: objective.goal });
    runtimeState.objectiveState.money_mode = {
      ...runtimeState.objectiveState.money_mode,
      active: true,
      status: OBJECTIVE_STATUS.RUNNING,
      current_objective: objective,
      active_tasks: [],
      progress: 0,
      agents_used: MONEY_MODE_AGENTS,
      performance: { leads_generated: 0, emails_sent: 0, conversion_pct: 0 },
      result: null,
    };
    tasks.forEach((task, idx) => {
      const agentHint = MONEY_MODE_AGENTS[idx % MONEY_MODE_AGENTS.length];
      const queued = queueWorkflowStep({
        runId:        run.run_id,
        message:      `[${agentHint}] ${task}`,
        stepIndex:    idx,
        labels:       ['money_mode', `step-${idx + 1}`],
        parentTaskId: idx > 0 ? runtimeState.objectiveState.money_mode.active_tasks[idx - 1]?.task_id || null : null,
      });
      runtimeState.objectiveTaskMeta[queued.taskId] = { system: 'money_mode', objective_id: objective.id, task_name: task, agent_hint: agentHint };
      runtimeState.objectiveState.money_mode.active_tasks.push({ task_id: queued.taskId, task, agent: agentHint, status: 'pending' });
    });
    broadcastObjectiveUpdate('money_mode');
    addActivity(`[MONEY MODE] objective started • ${objective.goal}`, 'automation');
    return { ok: true, message: `✅ Money Mode objective started: ${objective.goal}` };
  }

  function startAscendForgeObjective(objective) {
    if (!objective || !objective.goal) {
      setObjectiveWaiting('ascend_forge');
      return { ok: false, message: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.' };
    }
    objective.status = 'running';
    objective.updated_at = new Date().toISOString();
    persistObjectives();
    activateAgents(3);
    const plan = buildAscendForgePlan(objective.goal);
    const run  = createWorkflowRun({ name: 'Ascend Forge Objective', source: 'ascend_forge', goal: objective.goal });
    runtimeState.objectiveState.ascend_forge = {
      ...runtimeState.objectiveState.ascend_forge,
      active: true,
      status: OBJECTIVE_STATUS.RUNNING,
      current_objective: objective,
      plan,
      active_tasks: [],
      progress: 0,
      agents_used: ASCEND_FORGE_AGENTS,
      results: [],
      result: { plan, agents_used: ASCEND_FORGE_AGENTS, progress: 0, status: 'running' },
    };
    plan.forEach((step, idx) => {
      const agentHint = ASCEND_FORGE_AGENTS[idx % ASCEND_FORGE_AGENTS.length];
      const queued = queueWorkflowStep({
        runId:        run.run_id,
        message:      `[${agentHint}] ${step}`,
        stepIndex:    idx,
        labels:       ['ascend_forge', `step-${idx + 1}`],
        parentTaskId: idx > 0 ? runtimeState.objectiveState.ascend_forge.active_tasks[idx - 1]?.task_id || null : null,
      });
      runtimeState.objectiveTaskMeta[queued.taskId] = { system: 'ascend_forge', objective_id: objective.id, task_name: step, agent_hint: agentHint };
      runtimeState.objectiveState.ascend_forge.active_tasks.push({ task_id: queued.taskId, task: step, agent: agentHint, status: 'pending' });
    });
    broadcastObjectiveUpdate('ascend_forge');
    addActivity(`[ASCEND FORGE] objective started • ${objective.goal}`, 'automation');
    emitTaskProgress(run.run_id, `Forge: ${objective.goal}`, plan.map((step, idx) => ({ id: idx, label: step, status: 'pending' })));
    return { ok: true, message: `✅ Ascend Forge objective started: ${objective.goal}` };
  }

  function handleGoalDrivenCommand(message) {
    const raw = String(message || '').trim();
    const msg = raw.toLowerCase();
    if (!raw) return { handled: false };

    if (msg === 'activate money mode') {
      setMode('MONEYMODE');
      setObjectiveWaiting('money_mode');
      return { handled: true, reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.' };
    }

    const setMoneyPrefix = 'set goal for money mode:';
    if (msg.startsWith(setMoneyPrefix)) {
      const goal = raw.slice(setMoneyPrefix.length).trim();
      if (!goal) {
        setObjectiveWaiting('money_mode');
        return { handled: true, reply: '⚠️ Money Mode is active but has no objective.\nPlease define a goal before execution.' };
      }
      const objective = createObjective({ system: 'money_mode', goal, constraints: parseConstraintsFromGoal(goal), priority: 'high' });
      return { handled: true, reply: startMoneyModeObjective(objective).message };
    }

    const startAscendPrefix = 'start ascend forge with goal:';
    if (msg.startsWith(startAscendPrefix)) {
      const goal = raw.slice(startAscendPrefix.length).trim();
      if (!goal) {
        setObjectiveWaiting('ascend_forge');
        return { handled: true, reply: '⚠️ Ascend Forge is active but has no objective.\nPlease define a goal before execution.' };
      }
      const objective = createObjective({ system: 'ascend_forge', goal, constraints: parseConstraintsFromGoal(goal), priority: 'high' });
      return { handled: true, reply: startAscendForgeObjective(objective).message };
    }

    return { handled: false };
  }

  return {
    // Objective management
    persistObjectives,
    broadcastObjectiveUpdate,
    normalizeConstraints,
    parseConstraintsFromGoal,
    createObjective,
    setObjectiveWaiting,
    breakdownMoneyModeGoal,
    buildAscendForgePlan,
    recalcObjectiveProgress,
    startMoneyModeObjective,
    startAscendForgeObjective,
    handleGoalDrivenCommand,
    // Activity / observability
    addActivity,
    emitTaskProgress,
    emitObservabilityEvent,
    isSecurityEventType,
    appendAutoFixLog,
    // Workflow run management
    createWorkflowRun,
    appendDecision,
    getWorkflowRun,
    recalcWorkflowProgress,
    attachWorkflowNode,
    updateWorkflowNode,
    markWorkflowsStopped,
    // Workflow sequencing
    queueWorkflowStep,
    queueNextWorkflowStep,
    retryWorkflowStep,
  };
}

module.exports = { createWorkflowService };
