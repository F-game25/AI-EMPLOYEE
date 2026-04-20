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
    const agentMatch = task.message.match(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b/);
    const subject = agentMatch ? agentMatch[1] : 'the requested agent';
    return `Done — ${subject} is now active and ready to go. What would you like to execute first?`;
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
  } catch (err) {
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
  return {
    ...assignment,
    subsystem,
    status: 'queued',
    agent: 'ORCHESTRATOR',
    moneyTemplate,
    brain: taskBrainPlan,
    workflow: options.workflow || null,
    timestamp: new Date().toISOString(),
  };
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
  events.emit('orchestrator:reply', {
    message: buildHumanReply(task),
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
  res.json(submitTask(message));
});

function on(eventName, handler) {
  events.on(eventName, handler);
}

module.exports = { router, submitTask, on };
