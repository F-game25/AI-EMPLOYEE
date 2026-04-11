'use strict';

/**
 * routing.js — Shared subsystem routing logic.
 *
 * Determines which subsystem a chat message targets based on keywords.
 * Used by both server.js (WebSocket) and orchestrator/index.js (REST).
 */

const NN_PATTERN = /brain|neural|nn|learn|network|decision|confidence|loss/;
const MEMORY_PATTERN = /memory|remember|know|entity|fact|store/;
const DOCTOR_PATTERN = /doctor|health|check|diagnos|status|grade|score/;

/**
 * Classify a chat message into a subsystem target.
 * @param {string} message
 * @returns {'nn'|'memory'|'doctor'|null}
 */
function classifyMessage(message) {
  const msg = message.toLowerCase();
  if (NN_PATTERN.test(msg)) return 'nn';
  if (MEMORY_PATTERN.test(msg)) return 'memory';
  if (DOCTOR_PATTERN.test(msg)) return 'doctor';
  return null;
}

module.exports = { classifyMessage };
