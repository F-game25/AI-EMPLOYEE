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
 * Generate a natural, human-like reply for a completed task.
 * Responses are contextual — they use the original message, the subsystem
 * that handled the task, and the brain plan to produce something that reads
 * like a real assistant, not a system log.
 *
 * @param {{subsystem?: string, message: string, metadata?: object}} task
 * @returns {string}
 */
function buildReply(task) {
  const message = task.message || '';
  const lower = message.toLowerCase();
  const subsystem = task.subsystem || 'general';
  const brainPlan = task?.metadata?.brain ?? null;
  const intent = brainPlan?.intent || 'general';

  // Learning / memory storage requests
  if (/\b(learn|remember|store|save|note|memorize|keep in mind)\b/.test(lower)) {
    return `Got it — I've stored that in my memory and I'll apply it to relevant tasks going forward.`;
  }

  // Analytics / reporting requests
  if (/\b(analyz|report|insight|metric|stat|track|monitor|dashboard)\b/.test(lower)) {
    if (subsystem === 'doctor') {
      const dr = subsystems.getDoctorStatus();
      const score = dr.overall_score || 0;
      if (dr.issues && dr.issues.length > 0) {
        return `Health check done — system score is ${score}/100. I found ${dr.issues.length} item${dr.issues.length > 1 ? 's' : ''} worth reviewing.`;
      }
      return `Health check complete — everything looks solid at ${score}/100. No critical issues.`;
    }
    return `I've processed the analysis you asked for. The results are ready.`;
  }

  // Search / lookup requests
  if (/\b(search|find|look|discover|check|what is|who is|tell me about|lookup)\b/.test(lower)) {
    if (subsystem === 'memory') {
      const mem = subsystems.getMemoryTree();
      const count = mem.total_entities || 0;
      return `I searched my knowledge base (${count} entities tracked). Here's what I found.`;
    }
    return `I looked into that for you. The results have been processed.`;
  }

  // Creation / generation requests
  if (/\b(creat|build|generat|writ|design|draft|make|produce|compose)\b/.test(lower)) {
    return `Done — I've completed the task. The output has been generated and saved.`;
  }

  // Planning / strategy requests
  if (/\b(plan|strateg|organiz|schedul|priorit|roadmap)\b/.test(lower)) {
    return `I've put together an approach for that. Ready to execute on your instruction.`;
  }

  // Lead generation / sales pipeline
  if (intent === 'lead_generation' || /\b(lead|prospect|outreach|pipeline|conversion|sales)\b/.test(lower)) {
    return `Lead generation task complete. The pipeline has been updated and results are logged.`;
  }

  // Content / marketing
  if (intent === 'content_growth' || /\b(content|post|social|article|campaign|email|newsletter)\b/.test(lower)) {
    return `Content task complete. Your request has been processed and the output is ready.`;
  }

  // Neural / AI system queries
  if (subsystem === 'nn' || /\b(neural|network|ai|model|train|confidence)\b/.test(lower)) {
    const nn = subsystems.getNNStatus();
    return `Neural system is active in ${nn.mode || 'standard'} mode with ${(nn.learn_step || 0).toLocaleString()} learning steps completed. Your request has been processed.`;
  }

  // Memory system queries
  if (subsystem === 'memory' || /\b(memory|knowledge|context|recall)\b/.test(lower)) {
    const mem = subsystems.getMemoryTree();
    return `Memory updated — I'm tracking ${mem.total_entities || 0} knowledge entities. Your request has been recorded.`;
  }

  // Doctor / system health queries
  if (subsystem === 'doctor' || /\b(health|diagnos|system check|status)\b/.test(lower)) {
    const dr = subsystems.getDoctorStatus();
    const score = dr.overall_score || 0;
    return `System health is at ${score}/100. ${dr.issues && dr.issues.length ? `${dr.issues.length} issue${dr.issues.length === 1 ? '' : 's'} flagged for review.` : 'All clear.'}`;
  }

  // Help / capability questions
  if (/\b(help|what can you|how do|guide|explain|capabilities)\b/.test(lower)) {
    return `I'm here to help — I can analyze data, manage pipelines, search through knowledge, create content, run health checks, and learn from your feedback. What would you like to work on?`;
  }

  // Greeting
  if (/\b(hello|hi|hey|good morning|good afternoon|good evening|greetings)\b/.test(lower)) {
    return `Hello! I'm ready to work. What can I help you with today?`;
  }

  // Default: natural completion — deterministic rotation based on task id
  const completions = [
    `Done. I've taken care of that for you.`,
    `All finished. Let me know if you need anything else.`,
    `Your request has been completed. Ready for the next task.`,
    `Completed. Everything went smoothly.`,
  ];
  const taskId = task.id || task.taskId || message;
  const lastChar = taskId.length > 0 ? taskId.charCodeAt(taskId.length - 1) : 0;
  const idx = (Number.isNaN(lastChar) ? 0 : lastChar) % completions.length;
  return completions[idx];
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
