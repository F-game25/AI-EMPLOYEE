'use strict';

const { Router } = require('express');
const { EventEmitter } = require('events');
const subsystems = require('../subsystems');
const { classifyMessage } = require('../routing');
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
 * Build a subsystem-specific completion message for a processed task.
 * @param {{subsystem?: string, message: string}} task
 * @returns {string}
 */
function buildReply(task) {
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

function submitTask(message, options = {}) {
  const userId = options.userId || 'user:default';
  const subsystemHint = classifyMessage(message) || 'general';
  const seedTaskId = `planning-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const plan = brain.consult({
    taskId: seedTaskId,
    message,
    subsystemHint,
    userId,
  });
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
    metadata: {
      moneyTemplate,
      brain: plan,
      workflow: options.workflow || null,
      labels: options.labels || [],
      requestedBy: userId,
    },
  });
  const taskBrainPlan = brain.rebindPlan(seedTaskId, assignment.taskId) || { ...plan, taskId: assignment.taskId };
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
    message: buildReply(task),
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
