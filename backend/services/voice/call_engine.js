'use strict';

/**
 * call_engine.js — Customer-facing call channel
 *
 * Manages voice sessions for external / customer interactions.
 * Reuses the shared TTS engine (same backend process, different config snapshot).
 *
 * Future STT integration: the listen() stub returns a resolved promise today;
 * when a speech-to-text library is added, replace the body of listen() with
 * the real capture logic without changing any callers.
 */

const fs = require('fs');
const path = require('path');
const EventEmitter = require('events');
const ttsEngine = require('./tts_engine');

const LOG_DIR = path.resolve(__dirname, '../../../state/call_logs');
const MAX_CALL_DURATION_MS = 10 * 60 * 1000; // 10 minutes default

// ── Session registry ──────────────────────────────────────────────────────────
// sessionId → session object
const sessions = new Map();

const callEvents = new EventEmitter();

// ── Helpers ───────────────────────────────────────────────────────────────────

function ensureLogDir() {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
  } catch (_err) {
    // best-effort
  }
}

function nowIso() {
  return new Date().toISOString();
}

function appendLog(session, entry) {
  session.log.push(entry);
  // Persist incrementally — ignore errors to stay non-blocking
  const file = path.join(LOG_DIR, `call_${session.sessionId}.json`);
  try {
    fs.writeFileSync(file, JSON.stringify(session, null, 2), 'utf8');
  } catch (_err) {
    // best-effort
  }
}

// ── Customer-voice text expansion ─────────────────────────────────────────────
// Transforms terse system phrases into warm, polite customer-facing language.
const CUSTOMER_EXPANSIONS = [
  [/^Task assigned\.$/, "Your request has been received. We'll take care of that right away."],
  [/^Task complete\.$/, "Your request has been completed successfully. Is there anything else I can help you with?"],
  [/^Error detected\.$/, "We've encountered a small issue. Our team is looking into it right away."],
  [/^Systems online\.$/, 'Hello! Thank you for calling. How can I assist you today?'],
  [/^All systems operational\.$/, 'Everything is running smoothly on our end.'],
];

function expandForCustomer(text) {
  const trimmed = String(text || '').trim();
  for (const [pattern, replacement] of CUSTOMER_EXPANSIONS) {
    if (pattern.test(trimmed)) return replacement;
  }
  return trimmed;
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Start a new call session.
 * @param {string} sessionId  - Unique identifier for this call.
 * @param {object} [options]
 * @param {string} [options.profile]         - Customer voice profile to use.
 * @param {number} [options.maxDurationMs]   - Override max call duration.
 * @param {string} [options.greeting]        - Optional opening phrase.
 * @returns {object} session object
 */
async function startCall(sessionId, options = {}) {
  if (sessions.has(sessionId)) {
    throw new Error(`Call session '${sessionId}' already active.`);
  }

  ensureLogDir();

  const profile = options.profile || 'customer_default';
  const maxDurationMs = options.maxDurationMs || MAX_CALL_DURATION_MS;

  const session = {
    sessionId,
    profile,
    startedAt: nowIso(),
    endedAt: null,
    active: true,
    interrupted: false,
    log: [],
  };

  sessions.set(sessionId, session);

  // Apply customer voice profile to TTS engine
  await ttsEngine.reconfigure({ profile, channel: 'customer' });

  appendLog(session, { ts: nowIso(), role: 'system', event: 'call_started', profile });
  callEvents.emit('call:started', { sessionId, profile });
  console.log(`[CALL] Session started: ${sessionId} (profile: ${profile})`);

  // Auto-end safety timer
  session._timeoutHandle = setTimeout(() => {
    if (sessions.has(sessionId)) {
      console.log(`[CALL] Session ${sessionId} reached max duration — ending automatically.`);
      void endCall(sessionId, 'max_duration');
    }
  }, maxDurationMs);

  // Speak greeting if provided
  if (options.greeting) {
    await speak(sessionId, options.greeting);
  }

  return session;
}

/**
 * Speak text within an active call session.
 * Automatically expands system-style phrases to customer-friendly language.
 * @param {string} sessionId
 * @param {string} text
 */
async function speak(sessionId, text) {
  const session = sessions.get(sessionId);
  if (!session || !session.active) {
    console.warn(`[CALL] speak() called on inactive/unknown session: ${sessionId}`);
    return;
  }

  // Interrupt: stop any in-progress speech immediately
  if (ttsEngine.isSpeaking()) {
    await ttsEngine.stop();
    session.interrupted = true;
  }

  const expanded = expandForCustomer(text);
  appendLog(session, { ts: nowIso(), role: 'agent', text: expanded });
  callEvents.emit('call:speak', { sessionId, text: expanded });

  await ttsEngine.speak(expanded, 'customer');
}

/**
 * Interrupt the currently speaking agent (e.g. user started talking).
 * @param {string} sessionId
 */
async function interrupt(sessionId) {
  const session = sessions.get(sessionId);
  if (!session || !session.active) return;

  if (ttsEngine.isSpeaking()) {
    await ttsEngine.stop();
    session.interrupted = true;
    appendLog(session, { ts: nowIso(), role: 'system', event: 'interrupted' });
    callEvents.emit('call:interrupted', { sessionId });
    console.log(`[CALL] Session ${sessionId} interrupted.`);
  }
}

/**
 * listen() — STT stub.
 * Returns a promise that resolves with a transcript string.
 * Replace body with real STT implementation when available.
 * @param {string} _sessionId
 * @returns {Promise<string>}
 */
async function listen(_sessionId) {
  // STT not yet implemented — placeholder for future integration
  return '';
}

/**
 * End an active call session.
 * @param {string} sessionId
 * @param {string} [reason]  - 'user_ended' | 'max_duration' | 'error' | 'manual_override'
 */
async function endCall(sessionId, reason = 'user_ended') {
  const session = sessions.get(sessionId);
  if (!session) return;

  clearTimeout(session._timeoutHandle);
  session.active = false;
  session.endedAt = nowIso();

  // Stop any ongoing speech immediately (manual override)
  await ttsEngine.stop();

  appendLog(session, { ts: nowIso(), role: 'system', event: 'call_ended', reason });
  callEvents.emit('call:ended', { sessionId, reason, log: session.log });
  sessions.delete(sessionId);

  // Restore system voice profile
  await ttsEngine.reconfigure({ channel: 'system' });

  console.log(`[CALL] Session ended: ${sessionId} (reason: ${reason})`);
}

/**
 * List all active call sessions.
 * @returns {Array<{sessionId, profile, startedAt, interrupted}>}
 */
function listActiveSessions() {
  return Array.from(sessions.values()).map(({ sessionId, profile, startedAt, interrupted }) => ({
    sessionId,
    profile,
    startedAt,
    interrupted,
  }));
}

/**
 * Check whether a session is currently active.
 * @param {string} sessionId
 * @returns {boolean}
 */
function isActive(sessionId) {
  return sessions.has(sessionId) && (sessions.get(sessionId)?.active === true);
}

module.exports = {
  startCall,
  speak,
  listen,
  interrupt,
  endCall,
  listActiveSessions,
  isActive,
  callEvents,
};
