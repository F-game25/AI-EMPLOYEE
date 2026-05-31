'use strict';

// Task processing duration bounds (per task execution).
const PROCESS_MS_MIN = 800;
const PROCESS_MS_MAX = 2400;
const MISMATCH_PENALTY_MS = 600;
const DEFAULT_MSG_LENGTH = 40;
const MSG_LENGTH_NORMALIZATION = 200;

/**
 * Returns a plain snapshot of an agent suitable for broadcasting / serialisation.
 * Pure — does not mutate anything.
 * @param {object} agent
 * @returns {object}
 */
function snapshot(agent) {
  return {
    id: agent.id,
    name: agent.name,
    type: agent.type,
    state: agent.state,
    health: agent.health,
    task: agent.currentTask ? agent.currentTask.message : null,
    queueSize: agent.taskQueue.length,
    tasksCompleted: agent.tasksCompleted,
    location: agent.location || 'idle',
    description: agent.description || '',
    capabilities: agent.capabilities || [],
  };
}

/**
 * Heuristic load score for an agent (lower = more available).
 * Pure.
 * @param {object} agent
 * @returns {number}
 */
function agentLoad(agent) {
  return (agent.currentTask ? 1 : 0) + agent.taskQueue.length;
}

/**
 * Builds the location tag shown in the UI (e.g. "processing:nn").
 * Pure.
 * @param {string} processingStage
 * @param {string|null} subsystem
 * @returns {string}
 */
function formatLocation(processingStage, subsystem) {
  return `${processingStage}:${subsystem || 'general'}`;
}

/**
 * Deterministic task duration model.
 * Factors: base time + message length + subsystem affinity + jitter from seq.
 * Pure given the same inputs.
 * @param {object} agent
 * @param {object|null} task
 * @param {number} seq  — current global sequence counter (for jitter)
 * @returns {number}  milliseconds
 */
function taskDurationMs(agent, task, seq) {
  const msgLen = task?.message?.length ?? DEFAULT_MSG_LENGTH;
  const lengthFactor = Math.min(msgLen / MSG_LENGTH_NORMALIZATION, 1);
  const base = PROCESS_MS_MIN + Math.round(lengthFactor * (PROCESS_MS_MAX - PROCESS_MS_MIN));
  const subsystem = task?.subsystem || 'general';
  const hasSkill = agent?.skills?.includes(subsystem) ?? false;
  const penalty = hasSkill ? 0 : MISMATCH_PENALTY_MS;
  const jitter = ((seq * 37) % 200) - 100; // -100..+100 ms
  return Math.max(PROCESS_MS_MIN, base + penalty + jitter);
}

/**
 * Selects the least-loaded running agent that best fits the requested subsystem
 * and category.  Tries category match → skill specialist → any running agent.
 * Pure given the agents array passed in.
 * @param {object[]} runningAgents  — already-filtered list (state running|busy)
 * @param {string}   subsystem
 * @param {string|null} categoryHint
 * @returns {object|null}
 */
function findBestAgent(runningAgents, subsystem, categoryHint) {
  if (runningAgents.length === 0) return null;

  if (categoryHint) {
    const byCategory = runningAgents.filter((a) => a.type === categoryHint);
    if (byCategory.length > 0)
      return byCategory.slice().sort((a, b) => agentLoad(a) - agentLoad(b))[0];
  }

  if (subsystem && subsystem !== 'general') {
    const specialists = runningAgents.filter((a) => a.skills.includes(subsystem));
    if (specialists.length > 0)
      return specialists.slice().sort((a, b) => agentLoad(a) - agentLoad(b))[0];
  }

  return runningAgents.slice().sort((a, b) => agentLoad(a) - agentLoad(b))[0];
}

module.exports = { snapshot, agentLoad, formatLocation, taskDurationMs, findBestAgent };
