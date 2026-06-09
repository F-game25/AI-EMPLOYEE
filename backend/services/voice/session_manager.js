'use strict';

const crypto = require('crypto');

const VOICE_PHASES = Object.freeze({
  IDLE: 'idle',
  PRIMED: 'primed',
  LISTENING: 'listening',
  TRANSCRIBING: 'transcribing',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  EXECUTING: 'executing',
  INTERRUPTED: 'interrupted',
  ERROR: 'error',
});

const VALID_PHASES = new Set(Object.values(VOICE_PHASES));
const SESSION_TTL_MS = 2 * 60 * 60 * 1000;
const MAX_EVENTS = 150;

const sessions = new Map();

function nowIso() {
  return new Date().toISOString();
}

function safePhase(phase) {
  return VALID_PHASES.has(phase) ? phase : VOICE_PHASES.IDLE;
}

function publicSession(session) {
  if (!session) return null;
  return {
    id: session.id,
    phase: session.phase,
    transcript: session.transcript,
    reply: session.reply,
    error: session.error,
    latency_ms: session.latency_ms,
    created_at: session.created_at,
    updated_at: session.updated_at,
    interrupted_at: session.interrupted_at,
    runtime: session.runtime,
    event_count: session.events.length,
  };
}

function cleanupExpired() {
  const cutoff = Date.now() - SESSION_TTL_MS;
  for (const [id, session] of sessions.entries()) {
    if (session.updated_ms < cutoff && session.clients.size === 0) {
      sessions.delete(id);
    }
  }
}

function createSession(meta = {}) {
  cleanupExpired();
  const id = crypto.randomUUID();
  const session = {
    id,
    phase: VOICE_PHASES.PRIMED,
    transcript: '',
    reply: '',
    error: null,
    latency_ms: null,
    runtime: meta.runtime || null,
    created_at: nowIso(),
    updated_at: nowIso(),
    updated_ms: Date.now(),
    interrupted_at: null,
    turn_epoch: 0,
    clients: new Set(),
    events: [],
    meta: {
      source: meta.source || 'voice',
      user_id: meta.user_id || null,
      tenant_id: meta.tenant_id || null,
    },
  };
  sessions.set(id, session);
  emit(id, 'session.started', {
    phase: session.phase,
    session: publicSession(session),
    runtime: session.runtime,
  });
  return session;
}

function getSession(id) {
  return sessions.get(String(id || '')) || null;
}

function touch(session) {
  session.updated_at = nowIso();
  session.updated_ms = Date.now();
}

function writeSse(res, event) {
  try {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  } catch (_err) {
    // The close handler removes broken clients.
  }
}

function emit(sessionId, type, payload = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  const event = {
    id: crypto.randomUUID(),
    type,
    sessionId: session.id,
    phase: session.phase,
    timestamp: nowIso(),
    ...payload,
  };
  session.events.push(event);
  if (session.events.length > MAX_EVENTS) {
    session.events.splice(0, session.events.length - MAX_EVENTS);
  }
  touch(session);
  for (const client of session.clients) writeSse(client, event);
  return event;
}

function setRuntime(sessionId, runtime) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.runtime = runtime || null;
  return emit(session.id, 'voice.runtime', { runtime: session.runtime });
}

function setPhase(sessionId, phase, extra = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.phase = safePhase(phase);
  if (session.phase !== VOICE_PHASES.ERROR) session.error = null;
  return emit(session.id, 'phase', { phase: session.phase, ...extra });
}

function setTranscript(sessionId, transcript, final = false) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.transcript = String(transcript || '').trim();
  return emit(session.id, final ? 'transcript.final' : 'transcript.partial', {
    transcript: session.transcript,
    final,
  });
}

function appendReplyChunk(sessionId, chunk, index, total) {
  const session = getSession(sessionId);
  if (!session) return null;
  return emit(session.id, 'reply.chunk', {
    chunk: String(chunk || ''),
    index,
    total,
  });
}

function setReply(sessionId, reply, latencyMs = null, meta = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.reply = String(reply || '').trim();
  session.latency_ms = Number.isFinite(latencyMs) ? Math.round(latencyMs) : null;
  return emit(session.id, 'reply.final', {
    reply: session.reply,
    latency_ms: session.latency_ms,
    ...meta,
  });
}

function setError(sessionId, error, details = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.phase = VOICE_PHASES.ERROR;
  session.error = String(error || 'Voice session error');
  return emit(session.id, 'error', {
    phase: session.phase,
    error: session.error,
    ...details,
  });
}

function interrupt(sessionId, reason = 'user_interrupt') {
  const session = getSession(sessionId);
  if (!session) return null;
  session.turn_epoch += 1;
  session.phase = VOICE_PHASES.INTERRUPTED;
  session.interrupted_at = nowIso();
  session.error = null;
  return emit(session.id, 'interrupt', {
    phase: session.phase,
    reason,
    turn_epoch: session.turn_epoch,
  });
}

function nextTurn(sessionId) {
  const session = getSession(sessionId);
  if (!session) return null;
  session.turn_epoch += 1;
  session.error = null;
  session.reply = '';
  session.latency_ms = null;
  touch(session);
  return session.turn_epoch;
}

function isTurnCurrent(sessionId, epoch) {
  const session = getSession(sessionId);
  return Boolean(session && session.turn_epoch === epoch && session.phase !== VOICE_PHASES.INTERRUPTED);
}

function subscribe(sessionId, res) {
  const session = getSession(sessionId);
  if (!session) return false;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  session.clients.add(res);
  writeSse(res, {
    id: crypto.randomUUID(),
    type: 'session.snapshot',
    sessionId: session.id,
    phase: session.phase,
    timestamp: nowIso(),
    session: publicSession(session),
  });

  const heartbeat = setInterval(() => {
    writeSse(res, {
      id: crypto.randomUUID(),
      type: 'session.heartbeat',
      sessionId: session.id,
      phase: session.phase,
      timestamp: nowIso(),
    });
  }, 25000);

  res.on('close', () => {
    clearInterval(heartbeat);
    session.clients.delete(res);
  });
  return true;
}

module.exports = {
  VOICE_PHASES,
  createSession,
  getSession,
  publicSession,
  subscribe,
  emit,
  setRuntime,
  setPhase,
  setTranscript,
  appendReplyChunk,
  setReply,
  setError,
  interrupt,
  nextTurn,
  isTurnCurrent,
};
