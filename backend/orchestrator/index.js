'use strict';

const { Router } = require('express');
const { EventEmitter } = require('events');
const subsystems = require('../subsystems');
const { classifyMessage } = require('../routing');
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
  const moneyTemplate = task && task.metadata ? task.metadata.moneyTemplate : null;
  const moneyLine = moneyTemplate && moneyTemplate.enabled
    ? ` | [MONEYMODE] ${moneyTemplate.template} -> ${moneyTemplate.objective}`
    : '';
  const target = task.subsystem;
  if (target === 'nn') {
    const nn = subsystems.getNNStatus();
    return `[NEURAL BRAIN] Mode: ${nn.mode} | Step: ${nn.learn_step} | Buffer: ${nn.buffer_size} | Confidence: ${(nn.confidence * 100).toFixed(1)}%${moneyLine}`;
  }
  if (target === 'memory') {
    const mem = subsystems.getMemoryTree();
    const lastUpdate = (mem.recent_updates && mem.recent_updates[0]) ? mem.recent_updates[0].entity_id : 'none';
    return `[MEMORY TREE] ${mem.total_entities} entities stored | Last: ${lastUpdate}${moneyLine}`;
  }
  if (target === 'doctor') {
    const dr = subsystems.getDoctorStatus();
    return `[DOCTOR] Grade: ${dr.grade || 'N/A'} | Score: ${dr.overall_score}/100 | Issues: ${dr.issues.length}${moneyLine}`;
  }
  return `[ORCHESTRATOR] Task complete: ${task.message}${moneyLine}`;
}

function submitTask(message) {
  const subsystem = classifyMessage(message) || 'general';
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
    },
  });
  return {
    ...assignment,
    subsystem,
    status: 'queued',
    agent: 'ORCHESTRATOR',
    moneyTemplate,
    timestamp: new Date().toISOString(),
  };
}

onAgentEvent('task:completed', ({ agent, task }) => {
  events.emit('orchestrator:reply', {
    message: buildReply(task),
    subsystem: task.subsystem,
    taskId: task.id,
    from: agent.name,
    agentId: agent.id,
    timestamp: new Date().toISOString(),
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
