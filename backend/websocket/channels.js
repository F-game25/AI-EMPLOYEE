'use strict';

/**
 * WebSocket Channel Definitions
 * Defines all real-time update channels and their schemas
 */

/**
 * @typedef {object} TaskCreatedMessage
 * @property {string} type - "task-created"
 * @property {string} taskId - Task identifier
 * @property {string} title - Task title
 * @property {string} status - Task status (pending, running, completed, failed)
 * @property {string} agent - Agent ID
 * @property {number} createdAt - Unix timestamp
 * @property {string} tenantId - Tenant ID for isolation
 */

/**
 * @typedef {object} TaskUpdatedMessage
 * @property {string} type - "task-updated"
 * @property {string} taskId - Task identifier
 * @property {string} status - New task status
 * @property {number} progress - Progress percentage (0-100)
 * @property {object} result - Task result (if completed)
 * @property {number} updatedAt - Unix timestamp
 * @property {string} tenantId - Tenant ID
 */

/**
 * @typedef {object} AgentStatusMessage
 * @property {string} type - "agent-status"
 * @property {string} agentId - Agent identifier
 * @property {string} status - Agent status (idle, running, error)
 * @property {number} tasksCompleted - Cumulative completed tasks
 * @property {number} tasksActive - Currently active tasks
 * @property {number} timestamp - Unix timestamp
 * @property {string} tenantId - Tenant ID
 */

/**
 * @typedef {object} ExecutionTraceMessage
 * @property {string} type - "execution-trace"
 * @property {string} executionId - Execution ID
 * @property {string} phase - Pipeline phase (retrieve, classify, call_llm, validate, execute, format, etc)
 * @property {object} data - Phase-specific data
 * @property {number} durationMs - Phase duration in milliseconds
 * @property {number} timestamp - Unix timestamp
 * @property {string} tenantId - Tenant ID
 */

/**
 * @typedef {object} LogStreamMessage
 * @property {string} type - "log"
 * @property {string} level - Log level (debug, info, warn, error)
 * @property {string} message - Log message
 * @property {object} context - Contextual data
 * @property {number} timestamp - Unix timestamp
 * @property {string} tenantId - Tenant ID
 */

const CHANNELS = {
  TASKS_CREATED: 'tasks-created',
  TASKS_UPDATED: 'tasks-updated',
  AGENTS_STATUS: 'agents-status',
  EXECUTION_TRACE: 'execution-trace',
  LOGS_STREAM: 'logs-stream',
  SYSTEM_EVENTS: 'system-events',
};

/**
 * Validate message for channel
 * @param {string} channel - Channel name
 * @param {object} message - Message object
 * @returns {boolean} True if valid
 */
function validateMessage(channel, message) {
  if (!message || typeof message !== 'object') return false;
  if (!message.tenantId || typeof message.tenantId !== 'string') return false;
  if (message.type && typeof message.type !== 'string') return false;

  switch (channel) {
    case CHANNELS.TASKS_CREATED:
      return message.taskId && message.title && message.status && message.agent;
    case CHANNELS.TASKS_UPDATED:
      return message.taskId && message.status !== undefined && (message.progress !== undefined || message.result !== undefined);
    case CHANNELS.AGENTS_STATUS:
      return message.agentId && message.status;
    case CHANNELS.EXECUTION_TRACE:
      return message.executionId && message.phase && message.data;
    case CHANNELS.LOGS_STREAM:
      return message.level && message.message;
    case CHANNELS.SYSTEM_EVENTS:
      return message.message || message.data;
    default:
      return true;
  }
}

/**
 * Create normalized message for broadcast
 * @param {string} channel - Channel name
 * @param {object} payload - Message payload
 * @param {string} tenantId - Tenant ID
 * @returns {object} Normalized message with metadata
 */
function createMessage(channel, payload, tenantId) {
  return {
    type: payload.type || channel,
    channel,
    tenantId,
    timestamp: Date.now(),
    ...payload,
  };
}

module.exports = {
  CHANNELS,
  validateMessage,
  createMessage,
};
