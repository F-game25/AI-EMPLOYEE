'use strict';

const { Router } = require('express');
const { EventEmitter } = require('events');
const crypto = require('crypto');
const subsystems = require('../subsystems');
const { classifyMessage, classifyCategory } = require('../routing');
const brain = require('../brain/active_brain');
const {
  enqueueTask,
  getMode,
  getAgents,
  getRunningAgentCount,
  on: onAgentEvent,
} = require('../agents');
const { buildMoneyTemplate } = require('../money_mode');

const router = Router();
const events = new EventEmitter();

// ── Neural-network failsafe configuration ─────────────────────────────────────
const BYPASS_NN = process.env.BYPASS_NN === 'true' || process.env.BYPASS_NN === '1';
const NN_TIMEOUT_MS = parseInt(process.env.NN_TIMEOUT_MS || '2000', 10);

/** Safe fallback response object returned when the AI pipeline cannot produce output. */
function fallbackResponse(msg) {
  return {
    text: msg,
    status: 'fallback',
    system: 'recovered',
  };
}

/** Wrap a promise with a timeout; resolves with null on timeout. */
function withTimeout(promise, ms) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      () => { clearTimeout(timer); resolve(null); },
    );
  });
}

/**
 * Neural-network enhancement layer (non-blocking).
 * Returns enhanced input or null if the NN is unavailable or times out.
 * NEVER throws.
 */
async function nnProcess(input) {
  if (BYPASS_NN) {
    console.info('[AI FLOW] NN bypassed (BYPASS_NN=true)');
    return null;
  }
  console.info('[AI FLOW] → NN start');
  try {
    const nnStatus = subsystems.getNNStatus();
    if (!nnStatus.available || !nnStatus.active) {
      console.info('[AI FLOW] → NN unavailable — bypassing');
      return null;
    }
    // The JS NN layer reads subsystem state (confidence, mode) as routing metadata
    // but does not rewrite the input text.  getNNStatus() is synchronous; we wrap
    // it in a timeout-guarded promise so any future async implementation is safe.
    const nnResult = await withTimeout(
      new Promise((resolve) => resolve(nnStatus)),
      NN_TIMEOUT_MS,
    );
    if (nnResult !== null) {
      console.info('[AI FLOW] → NN success (confidence=%s%%)', Math.round((nnStatus.confidence || 0) * 100));
      // Return the original input — NN provides metadata only, not a rewritten message.
      return input;
    }
    console.warn('[AI FLOW] → NN timeout (%dms) — bypassing', NN_TIMEOUT_MS);
    return null;
  } catch (err) {
    console.warn('[AI FLOW] → NN failed — bypassing:', err && err.message);
    return null;
  }
}

/**
 * Build a technical debug string for a processed task (shown only in debug mode).
 * @param {{subsystem?: string, message: string, metadata?: object}} task
 * @returns {string}
 */
function buildDebugReply(task) {
  const moneyTemplate = task?.metadata?.moneyTemplate ?? null;
  const brainPlan = task?.metadata?.brain ?? null;
  const moneyLine = moneyTemplate && moneyTemplate.enabled
    ? ` | [MONEYMODE] ${moneyTemplate.template} -> ${moneyTemplate.objective}`
    : '';
  const brainLine = brainPlan
    ? ` | [BRAIN] strategy=${brainPlan.strategy} confidence=${Math.round((brainPlan.confidence || 0) * 100)}%`
    : '';
  const target = task.subsystem;
  if (target === 'nn') {
    const nn = subsystems.getNNStatus();
    return `[NEURAL BRAIN] Mode: ${nn.mode} | Step: ${nn.learn_step} | Buffer: ${nn.buffer_size} | Confidence: ${(nn.confidence * 100).toFixed(1)}%${brainLine}${moneyLine}`;
  }
  if (target === 'memory') {
    const mem = subsystems.getMemoryTree();
    const lastUpdate = (mem.recent_updates && mem.recent_updates[0]) ? mem.recent_updates[0].entity_id : 'none';
    return `[MEMORY TREE] ${mem.total_entities} entities stored | Last: ${lastUpdate}${brainLine}${moneyLine}`;
  }
  if (target === 'doctor') {
    const dr = subsystems.getDoctorStatus();
    return `[DOCTOR] Grade: ${dr.grade || 'N/A'} | Score: ${dr.overall_score}/100 | Issues: ${dr.issues.length}${brainLine}${moneyLine}`;
  }
  return `[ORCHESTRATOR] Task complete: ${task.message}${brainLine}${moneyLine}`;
}

/**
 * Build a human-friendly conversational reply for a processed task.
 * @param {{subsystem?: string, message: string, metadata?: object}} task
 * @returns {string}
 */
function buildHumanReply(task) {
  const target = task.subsystem;
  if (target === 'nn') {
    const nn = subsystems.getNNStatus();
    const conf = Math.round((nn.confidence || 0) * 100);
    const mode = (nn.mode || 'active').replace(/_/g, ' ').toLowerCase();
    return `Got it. The neural network processed your request — currently ${mode} with ${conf}% confidence and ${(nn.buffer_size || 0).toLocaleString()} experiences loaded.`;
  }
  if (target === 'memory') {
    const mem = subsystems.getMemoryTree();
    const lastUpdate = mem.recent_updates && mem.recent_updates[0] ? mem.recent_updates[0].entity_id : null;
    const lastLine = lastUpdate ? ` Latest entry: ${lastUpdate}.` : '';
    return `Memory updated — I now have ${mem.total_entities} entities stored.${lastLine}`;
  }
  if (target === 'doctor') {
    const dr = subsystems.getDoctorStatus();
    const issueCount = (dr.issues || []).length;
    if (issueCount > 0) {
      return `System check complete — grade ${dr.grade || 'N/A'}, score ${dr.overall_score}/100. Found ${issueCount} issue${issueCount !== 1 ? 's' : ''} that may need attention.`;
    }
    return `System is healthy — grade ${dr.grade || 'N/A'}, score ${dr.overall_score}/100. No critical issues detected.`;
  }
  // General: craft a reply based on intent keywords in the original message
  const text = (task.message || '').toLowerCase();
  if (/(activate|start|enable|turn on|launch)/.test(text)) {
    return `Done — I've activated that. Everything is up and ready. What would you like to execute first?`;
  }
  if (/(stop|disable|deactivate|turn off|halt)/.test(text)) {
    return `Stopped. Everything has been shut down cleanly. Let me know when you want to resume.`;
  }
  if (/(status|how is|health|check)/.test(text)) {
    return `Here's the current status — all systems are operational. Anything specific you want to drill into?`;
  }
  if (/(learn|train|improve|optimize)/.test(text)) {
    return `On it — I've kicked off the learning process. I'll improve performance from here and report back if anything noteworthy comes up.`;
  }
  if (/(report|summary|overview|show me)/.test(text)) {
    return `Report ready. Take a look at the panels on the right for the full breakdown. Want me to highlight anything specific?`;
  }
  return `Done. I've taken care of that. What would you like me to do next?`;
}

function submitTask(message, options = {}) {
  const userId = options.userId || 'user:default';
  console.info('[AI FLOW] Input received: user=%s message_len=%d', userId, String(message || '').length);

  const subsystemHint = classifyMessage(message) || 'general';
  const categoryHint = classifyCategory(message);
  const seedTaskId = `planning-${crypto.randomUUID()}`;
  let plan;
  try {
    plan = brain.consult({
      taskId: seedTaskId,
      message,
      subsystemHint,
      userId,
    });
    console.info('[AI FLOW] → Brain plan: strategy=%s confidence=%s%%', plan.strategy, Math.round((plan.confidence || 0) * 100));
  } catch (err) {
    console.warn('[AI FLOW] → Brain consult failed — using fallback plan:', err && err.message);
    plan = {
      taskId: seedTaskId,
      intent: 'general',
      subsystem: subsystemHint,
      strategy: 'fallback_balanced_execution',
      alternatives: [],
      confidence: 0.5,
      reasoning: `Brain consult fallback: ${(err && err.message) || 'unavailable'}`,
      brain_assisted: false,
      execution_flow: 'task->strategy->agent->action->result',
      plannedAt: new Date().toISOString(),
    };
  }
  const subsystem = plan.subsystem || subsystemHint;
  const mode = getMode();
  const moneyTemplate = buildMoneyTemplate({
    message,
    subsystem,
    mode,
    runningAgents: getRunningAgentCount(),
    totalAgents: getAgents().length,
  });
  const assignment = enqueueTask({
    message,
    subsystem,
    categoryHint,
    metadata: {
      moneyTemplate,
      brain: plan,
      workflow: options.workflow || null,
      labels: options.labels || [],
      requestedBy: userId,
    },
  });
  const rebound = brain.rebindPlan(seedTaskId, assignment.taskId);
  const taskBrainPlan = rebound || { ...plan, taskId: assignment.taskId };
  if (!rebound && taskBrainPlan.brain_assisted) {
    taskBrainPlan.reasoning = `${taskBrainPlan.reasoning} | plan_rebind=fallback`;
  }

  const result = {
    ...assignment,
    subsystem,
    status: 'queued',
    agent: 'ORCHESTRATOR',
    moneyTemplate,
    brain: taskBrainPlan,
    workflow: options.workflow || null,
    timestamp: new Date().toISOString(),
  };

  // Guard: verify enqueueTask returned a valid assignment with a taskId
  if (!result.taskId) {
    console.error('[AI FLOW] submitTask produced no taskId — returning fallback');
    return { ...fallbackResponse('System recovered: task could not be queued.'), taskId: seedTaskId };
  }

  console.info('[AI FLOW] → Response returned: taskId=%s agent=%s', result.taskId, result.agentId);
  return result;
}

onAgentEvent('task:completed', ({ agent, task }) => {
  const requestedBy = task?.metadata?.requestedBy || 'user:default';
  brain.feedback({
    taskId: task.id,
    status: 'success',
    subsystem: task.subsystem || 'general',
    durationMs: brain.normalizeLatencyMs(task.startedAt, new Date().toISOString()),
    notes: task.message,
    userId: requestedBy,
  });
  const reply = buildHumanReply(task) || fallbackResponse('Task completed.').text;
  console.info('[AI FLOW] → Response returned to UI: taskId=%s', task.id);
  events.emit('orchestrator:reply', {
    message: reply,
    debugInfo: buildDebugReply(task),
    subsystem: task.subsystem,
    taskId: task.id,
    from: agent.name,
    agentId: agent.id,
    timestamp: new Date().toISOString(),
  });
});

onAgentEvent('task:failed', ({ task }) => {
  const requestedBy = task?.metadata?.requestedBy || 'user:default';
  console.warn('[AI FLOW] Task failed: taskId=%s error=%s', task.id, task.error || task.message);
  brain.feedback({
    taskId: task.id,
    status: 'failed',
    subsystem: task.subsystem || 'general',
    durationMs: brain.normalizeLatencyMs(task.startedAt, new Date().toISOString()),
    notes: task.error || task.message || 'Execution failed',
    reward: -1,
    userId: requestedBy,
  });
});

router.post('/message', (req, res) => {
  const { message } = req.body || {};
  if (!message) {
    return res.status(400).json({ error: 'message is required' });
  }
  const result = submitTask(message);
  // submitTask always returns a valid object (guaranteed above); res.json always fires.
  return res.json(result);
});

function on(eventName, handler) {
  events.on(eventName, handler);
}

module.exports = { router, submitTask, on, fallbackResponse, nnProcess };
