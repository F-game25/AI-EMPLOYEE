'use strict';

/**
 * call_engine.js — Customer-facing call channel
 *
 * All speech goes through stream_pipeline, giving:
 *   • Sentence-level chunk streaming  (first word plays ~100ms after text arrives)
 *   • Pre-roll fillers                ("One moment…" while response is generating)
 *   • Between-chunk interrupt         (user speaks → AI stops at sentence boundary)
 *   • VAD / STT stubs                 (replace body of listen() / detectSpeech() when ready)
 */

const fs = require('fs');
const path = require('path');
const EventEmitter = require('events');
const ttsEngine = require('./tts_engine');
const { pipeline: sharedPipeline } = require('./stream_pipeline');

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

// Sanitize sessionId to safe filename characters only (alphanumeric, dash, underscore)
function safeSessionFilename(sessionId) {
  return String(sessionId).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 64);
}

function appendLog(session, entry) {
  session.log.push(entry);
  // Persist incrementally — ignore errors to stay non-blocking
  const file = path.join(LOG_DIR, `call_${safeSessionFilename(session.sessionId)}.json`);
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
  // Cap max duration between 10 s and 2 hours to prevent resource exhaustion
  const MAX_ALLOWED_MS = 2 * 60 * 60 * 1000; // 2 hours
  const MIN_ALLOWED_MS = 10 * 1000;           // 10 seconds
  const rawDuration = Number(options.maxDurationMs) || MAX_CALL_DURATION_MS;
  const maxDurationMs = Math.min(MAX_ALLOWED_MS, Math.max(MIN_ALLOWED_MS, rawDuration));

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
 * Speak text within an active call session using the streaming pipeline.
 * Text is sentence-chunked — first chunk plays ~100ms after this call.
 * Automatically expands system-style phrases to customer-friendly language.
 * @param {string} sessionId
 * @param {string} text
 * @param {object} [opts]
 * @param {boolean} [opts.preRoll]         - speak a filler phrase first
 * @param {string}  [opts.preRollType]     - 'thinking' | 'acknowledging' etc.
 * @param {number}  [opts.thinkingDelayMs] - extra pause before first chunk
 */
async function speak(sessionId, text, opts = {}) {
  const session = sessions.get(sessionId);
  if (!session || !session.active) {
    console.warn(`[CALL] speak() called on inactive/unknown session: ${sessionId}`);
    return;
  }

  const expanded = expandForCustomer(text);
  appendLog(session, { ts: nowIso(), role: 'agent', text: expanded });
  callEvents.emit('call:speak', { sessionId, text: expanded });

  await sharedPipeline.speakStreaming(expanded, {
    channel:          'customer',
    preRollEnabled:   opts.preRoll !== false,
    preRollThreshold: 3,            // pre-roll for responses with ≥3 sentences
    microPauseMs:     90,           // 90ms between sentences — warm, conversational
    thinkingDelayMs:  opts.thinkingDelayMs || 0,
  });
}

/**
 * Interrupt the currently speaking agent (e.g. user started talking).
 * Uses the pipeline interrupt so it stops cleanly at a sentence boundary.
 * @param {string} sessionId
 */
async function interrupt(sessionId) {
  const session = sessions.get(sessionId);
  if (!session || !session.active) return;

  await sharedPipeline.interrupt();
  session.interrupted = true;
  appendLog(session, { ts: nowIso(), role: 'system', event: 'interrupted' });
  callEvents.emit('call:interrupted', { sessionId });
  console.log(`[CALL] Session ${sessionId} interrupted.`);
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
