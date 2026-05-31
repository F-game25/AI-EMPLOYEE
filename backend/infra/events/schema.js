'use strict';

/**
 * Typed event schema contracts for the AI Employee event bus.
 *
 * Every event published through the bus MUST conform to one of these schemas.
 * Envelope fields are mandatory; payload shape is schema-specific.
 *
 * Versioning: bump SCHEMA_VERSION on breaking changes, never mutate existing fields.
 */

const SCHEMA_VERSION = '1';

// ── Canonical event names ─────────────────────────────────────────────────────
const EVENT_TYPES = Object.freeze({
  // Agent lifecycle
  AGENT_STARTED:        'agent:started',
  AGENT_COMPLETED:      'agent:completed',
  AGENT_FAILED:         'agent:failed',
  AGENT_PAUSED:         'agent:paused',         // HITL gate opened
  AGENT_RESUMED:        'agent:resumed',          // HITL approved

  // Task lifecycle
  TASK_SUBMITTED:       'task:submitted',
  TASK_PLANNED:         'task:planned',
  TASK_EXECUTING:       'task:executing',
  TASK_COMPLETED:       'task:completed',
  TASK_FAILED:          'task:failed',
  TASK_CANCELLED:       'task:cancelled',

  // Neural brain (nb:* preserved for WS compatibility)
  NB_REASONING_STEP:    'nb:reasoning_step',
  NB_MODEL_CALL:        'nb:model_call',
  NB_MEMORY_WRITE:      'nb:memory_write',
  NB_GRAPH_UPDATE:      'nb:graph_update',

  // System
  SYSTEM_READY:         'system:ready',
  SYSTEM_DEGRADED:      'system:degraded',
  SYSTEM_STATUS:        'system:status',

  // Security / audit
  SECURITY_ALERT:       'security:alert',
  AUDIT_RECORD:         'audit:record',

  // Evolution
  EVOLUTION_PATCH_PROPOSED: 'evolution:patch_proposed',
  EVOLUTION_PATCH_APPLIED:  'evolution:patch_applied',

  // Dead-letter
  DLQ_POISONED:         'dlq:poisoned',
});

/**
 * Build a fully-formed event envelope.
 *
 * @param {string} type   - One of EVENT_TYPES values
 * @param {object} payload - Event-specific payload
 * @param {object} opts   - { tenant_id, trace_id, correlation_id, source, priority }
 * @returns {object} Envelope ready for publication
 */
function buildEvent(type, payload, opts = {}) {
  const {
    tenant_id = 'system',
    trace_id = _genId(),
    correlation_id = null,
    source = 'backend',
    priority = 5,           // 1 (low) – 10 (critical)
  } = opts;

  return {
    // Envelope — never stripped by consumers
    id:             _genId(),
    schema_version: SCHEMA_VERSION,
    type,
    source,
    tenant_id,
    trace_id,
    correlation_id,
    priority,
    ts:             Date.now(),
    // Payload — schema-specific
    payload,
  };
}

/**
 * Validate an envelope against minimum structural requirements.
 * Returns { ok, errors }.
 */
function validateEvent(evt) {
  const errors = [];
  if (!evt || typeof evt !== 'object') return { ok: false, errors: ['not an object'] };
  if (!evt.id)             errors.push('missing id');
  if (!evt.type)           errors.push('missing type');
  if (!evt.tenant_id)      errors.push('missing tenant_id');
  if (!evt.trace_id)       errors.push('missing trace_id');
  if (typeof evt.ts !== 'number') errors.push('ts must be a number');
  if (!evt.payload || typeof evt.payload !== 'object') errors.push('payload must be an object');
  return { ok: errors.length === 0, errors };
}

function _genId() {
  // crypto-safe 16-byte hex
  try {
    return require('crypto').randomBytes(16).toString('hex');
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

// Example payload shapes (documentation + runtime reference)
const PAYLOAD_SCHEMAS = {
  [EVENT_TYPES.AGENT_STARTED]: {
    agent_id: 'string',
    agent_name: 'string',
    task_id: 'string|null',
    mode: 'string',
  },
  [EVENT_TYPES.TASK_SUBMITTED]: {
    task_id: 'string',
    goal: 'string',
    priority: 'string',
    submitted_by: 'string|null',
  },
  [EVENT_TYPES.NB_REASONING_STEP]: {
    node: 'string',
    status: 'active|done|error',
    latency_ms: 'number|null',
    thread_id: 'string|null',
  },
  [EVENT_TYPES.NB_MODEL_CALL]: {
    arch: 'string',
    provider: 'string',
    latency_ms: 'number|null',
    status: 'ok|error',
    tokens_used: 'number|null',
  },
  [EVENT_TYPES.SECURITY_ALERT]: {
    severity: 'low|medium|high|critical',
    category: 'string',
    detail: 'string',
    actor: 'string|null',
  },
};

module.exports = { EVENT_TYPES, SCHEMA_VERSION, buildEvent, validateEvent, PAYLOAD_SCHEMAS };
