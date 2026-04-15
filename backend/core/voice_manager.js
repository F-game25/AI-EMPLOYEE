'use strict';

const fs = require('fs');
const path = require('path');
const ttsEngine = require('../services/voice/tts_engine');
const callEngine = require('../services/voice/call_engine');
const { pipeline: sharedPipeline, PRE_ROLL_SYSTEM, PRE_ROLL_CUSTOMER } = require('../services/voice/stream_pipeline');

const VOICE_CONFIG_PATH = path.resolve(__dirname, '../../config/voice.json');
const MAX_CACHEABLE_PHRASE_LENGTH = 120;

// ── Verbosity levels ──────────────────────────────────────────────────────────
const VERBOSITY = { SILENT: 0, CRITICAL: 1, IMPORTANT: 2, NORMAL: 3, VERBOSE: 4 };

const EVENT_VERBOSITY = {
  system_boot:         VERBOSITY.CRITICAL,
  error_detected:      VERBOSITY.CRITICAL,
  task_created:        VERBOSITY.IMPORTANT,
  task_completed:      VERBOSITY.NORMAL,
  ai_learning_update:  VERBOSITY.VERBOSE,
};

// System channel event phrases — terse / futuristic
const SYSTEM_EVENT_PHRASES = {
  system_boot:         (data) => data.greeting || 'Systems online.',
  error_detected:      (data) => data.message  || 'Error detected.',
  task_created:        (data) => {
    if (data.count && data.count > 1) return `${data.count} tasks assigned.`;
    if (data.priority === 'high') return 'High priority task registered.';
    return 'Task assigned.';
  },
  task_completed:      (data) => data.message  || 'Task complete.',
  ai_learning_update:  () => 'Learning update applied.',
};

// Customer channel event phrases — polite / conversational
const CUSTOMER_EVENT_PHRASES = {
  incoming_support:    (data) => data.greeting || 'Hello! Thank you for reaching out. How can I assist you today?',
  outbound_call:       (data) => data.greeting || 'Hello! This is an automated follow-up. How are you today?',
  followup_reminder:   (data) => data.message  || 'Just following up on your recent request. Is there anything else we can help you with?',
};

const EVENT_COOLDOWN_MS = {
  system_boot:         0,
  error_detected:      5000,
  task_created:        4000,
  task_completed:      3000,
  ai_learning_update:  10000,
  // customer
  incoming_support:    2000,
  outbound_call:       5000,
  followup_reminder:   10000,
};

// ── Config defaults ───────────────────────────────────────────────────────────
const DEFAULT_CUSTOMER_CONFIG = {
  enabled: false,
  profile: 'customer_default',
  speed: 1.0,
  warmth: 0.7,
  formality: 0.5,
  maxCallDurationMs: 600000,
  events: {
    incoming_support: true,
    outbound_call:    false,
    followup_reminder: false,
  },
};

const DEFAULT_CONFIG = {
  enabled: true,
  profile: 'default_futuristic',
  verbosity: VERBOSITY.NORMAL,
  volume: 0.9,
  pitch: 1.0,
  speed: 1.0,
  tone: 'futuristic',
  voiceStyle: 'default',
  bootGreeting: true,
  events: {
    system_boot:         true,
    task_created:        true,
    task_completed:      true,
    error_detected:      true,
    ai_learning_update:  false,
  },
  customer: { ...DEFAULT_CUSTOMER_CONFIG },
};

// ── Module state ──────────────────────────────────────────────────────────────
let config = { ...DEFAULT_CONFIG, customer: { ...DEFAULT_CUSTOMER_CONFIG } };
let initialized = false;
let muted = false;
let queue = [];
let draining = false;
let queueEpoch = 0;
const phraseCache = new Map();
const eventCooldownTimestamps = new Map();

let pendingTaskBatch = [];
let taskBatchTimer = null;
const TASK_BATCH_WINDOW_MS = 600;

// Active voice mode: 'system' | 'customer'
let activeMode = 'system';

// ── Config helpers ────────────────────────────────────────────────────────────

function loadConfig() {
  try {
    const raw = fs.readFileSync(VOICE_CONFIG_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      config = {
        ...DEFAULT_CONFIG,
        ...parsed,
        events: { ...DEFAULT_CONFIG.events, ...(parsed.events || {}) },
        customer: {
          ...DEFAULT_CUSTOMER_CONFIG,
          ...(parsed.customer || {}),
          events: { ...DEFAULT_CUSTOMER_CONFIG.events, ...(parsed.customer?.events || {}) },
        },
      };
    }
  } catch (_err) {
    config = { ...DEFAULT_CONFIG, customer: { ...DEFAULT_CUSTOMER_CONFIG } };
  }
}

function saveConfig() {
  try {
    fs.writeFileSync(VOICE_CONFIG_PATH, JSON.stringify(config, null, 2), 'utf8');
  } catch (_err) {
    // best-effort
  }
}

function getConfig() {
  return JSON.parse(JSON.stringify(config));
}

function applyConfig(patch) {
  config = {
    ...config,
    ...patch,
    events: { ...config.events, ...(patch.events || {}) },
    customer: {
      ...config.customer,
      ...(patch.customer || {}),
      events: { ...config.customer.events, ...(patch.customer?.events || {}) },
    },
  };
  saveConfig();
  void ttsEngine.reconfigure({
    profile: config.profile,
    volume: config.volume,
    pitch: config.pitch,
    speed: config.speed,
    tone: config.tone,
    voiceStyle: config.voiceStyle,
  });
}

// ── Mode switching ────────────────────────────────────────────────────────────

/**
 * Switch the active voice mode.
 * 'system'   → futuristic AI voice, terse phrases
 * 'customer' → natural human-like voice, polite phrases
 */
function setMode(mode) {
  activeMode = mode === 'customer' ? 'customer' : 'system';
  const profile = activeMode === 'customer'
    ? (config.customer?.profile || 'customer_default')
    : (config.profile || 'default_futuristic');
  void ttsEngine.reconfigure({ profile, channel: activeMode });
  console.log(`[VOICE] Mode → ${activeMode} (profile: ${profile})`);
}

function getMode() {
  return activeMode;
}

// ── Enabled / cooldown guards ─────────────────────────────────────────────────

function isEnabled() {
  return Boolean(config.enabled) && !muted;
}

function isEventEnabled(eventName) {
  // Customer events live in config.customer.events
  if (CUSTOMER_EVENT_PHRASES[eventName]) {
    return Boolean(config.customer?.enabled) &&
           Boolean(config.customer?.events?.[eventName] !== false);
  }
  return Boolean(config.events && config.events[eventName] !== false);
}

function verbosityAllows(eventName) {
  const required = EVENT_VERBOSITY[eventName] ?? VERBOSITY.NORMAL;
  return (config.verbosity ?? VERBOSITY.NORMAL) >= required;
}

function checkCooldown(eventName) {
  const cooldownMs = EVENT_COOLDOWN_MS[eventName] ?? 3000;
  if (cooldownMs === 0) return true;
  const last = eventCooldownTimestamps.get(eventName) || 0;
  if (Date.now() - last < cooldownMs) return false;
  eventCooldownTimestamps.set(eventName, Date.now());
  return true;
}

// ── Phrase cache ──────────────────────────────────────────────────────────────

function getCachedPhrase(text) {
  const normalized = String(text || '').trim();
  if (!normalized) return '';
  const key = normalized.toLowerCase();
  if (phraseCache.has(key)) return phraseCache.get(key);
  if (normalized.length <= MAX_CACHEABLE_PHRASE_LENGTH) phraseCache.set(key, normalized);
  return normalized;
}

// ── Queue processing ──────────────────────────────────────────────────────────

async function processQueue() {
  if (draining) return;
  draining = true;
  const runEpoch = queueEpoch;
  try {
    while (queue.length > 0 && isEnabled() && runEpoch === queueEpoch) {
      const next = queue.shift();
      const channel = next.channel || 'system';
      // Use the streaming pipeline: sentences play as they arrive
      await sharedPipeline.speakStreaming(next.text, { channel });
      next.resolve(true);
    }
    if (queue.length > 0 && runEpoch === queueEpoch) {
      const skippedBatch = queue.splice(0);
      for (const skipped of skippedBatch) skipped.resolve(false);
    }
  } finally {
    draining = false;
    if (queue.length > 0 && isEnabled()) void processQueue();
  }
}

// ── Core speak ────────────────────────────────────────────────────────────────

async function init() {
  if (initialized) return;
  loadConfig();
  await ttsEngine.init({
    profile: config.profile,
    volume: config.volume,
    pitch: config.pitch,
    speed: config.speed,
    tone: config.tone,
    voiceStyle: config.voiceStyle,
    channel: 'system',
  });
  // Warm the pipeline phrase cache with all known pre-roll phrases
  const allPhrases = [
    ...Object.values(PRE_ROLL_SYSTEM).flat(),
    ...Object.values(PRE_ROLL_CUSTOMER).flat(),
    // Common system event phrases
    'Systems online.', 'Task complete.', 'Task assigned.', 'Error detected.',
    // Common customer phrases
    'Hello! How can I assist you today?',
    'Your request has been completed successfully.',
    'Is there anything else I can help you with?',
  ];
  sharedPipeline.warmCache(allPhrases);
  initialized = true;
}

async function speak(text, priority = false) {
  const phrase = getCachedPhrase(text);
  if (!phrase) return false;
  if (!initialized) await init();
  if (!isEnabled()) return false;

  const channel = activeMode === 'customer' ? 'customer' : 'system';

  // Priority speak: flush queue and interrupt current speech, then stream
  if (priority) {
    for (const pending of queue) pending.resolve(false);
    queue = [];
    queueEpoch += 1;
    await sharedPipeline.interrupt();
  }

  // Use streaming pipeline for all speech (sentence chunking, micro-pauses)
  return new Promise((resolve) => {
    queue.push({
      text: phrase,
      channel,
      resolve,
    });
    void processQueue();
  });
}

// ── Event-driven speak ────────────────────────────────────────────────────────

async function emitEvent(eventName, data = {}, force = false) {
  if (!initialized) await init();
  if (!isEnabled()) return false;

  // Determine which phrase table to use
  const isCustomerEvent = Boolean(CUSTOMER_EVENT_PHRASES[eventName]);

  // Batch task_created events for system channel
  if (eventName === 'task_created' && !force && !isCustomerEvent) {
    return batchTaskCreated(data);
  }

  if (!force) {
    if (!isEventEnabled(eventName)) return false;
    if (!isCustomerEvent && !verbosityAllows(eventName)) return false;
    if (!checkCooldown(eventName)) return false;
  }

  const phraseTable = isCustomerEvent ? CUSTOMER_EVENT_PHRASES : SYSTEM_EVENT_PHRASES;
  const phraseFactory = phraseTable[eventName];
  if (!phraseFactory) return false;
  const text = phraseFactory(data);

  if (isCustomerEvent) {
    // Trigger via call engine if a session exists, otherwise plain speak
    const active = callEngine.listActiveSessions();
    if (active.length > 0) {
      await callEngine.speak(active[0].sessionId, text);
      return true;
    }
  }
  return speak(text, eventName === 'error_detected');
}

function batchTaskCreated(data) {
  pendingTaskBatch.push(data);
  if (taskBatchTimer) clearTimeout(taskBatchTimer);
  taskBatchTimer = setTimeout(() => {
    taskBatchTimer = null;
    if (pendingTaskBatch.length === 0) return;
    const batch = pendingTaskBatch.splice(0);
    const eventName = 'task_created';
    if (!isEventEnabled(eventName)) return;
    if (!verbosityAllows(eventName)) return;
    if (!checkCooldown(eventName)) return;

    const phraseData = batch.length > 1
      ? { count: batch.length }
      : { ...batch[0] };
    const text = SYSTEM_EVENT_PHRASES.task_created(phraseData);
    void speak(text);
  }, TASK_BATCH_WINDOW_MS);
  return false;
}

// ── Call triggers ─────────────────────────────────────────────────────────────

/**
 * Trigger an outbound call session.
 * @param {string} sessionId
 * @param {object} [options]
 */
async function triggerCall(sessionId, options = {}) {
  if (!config.customer?.enabled) return false;
  const callOptions = {
    profile: config.customer?.profile || 'customer_default',
    maxDurationMs: config.customer?.maxCallDurationMs || 600000,
    ...options,
  };
  try {
    await callEngine.startCall(sessionId, callOptions);
    return true;
  } catch (err) {
    console.error(`[VOICE] triggerCall failed: ${err.message}`);
    return false;
  }
}

/**
 * Manually stop an active call.
 * @param {string} sessionId
 */
async function stopCall(sessionId) {
  await callEngine.endCall(sessionId, 'manual_override');
}

// ── Control functions ─────────────────────────────────────────────────────────

async function clearQueue() {
  for (const pending of queue) pending.resolve(false);
  queue = [];
  queueEpoch += 1;
  await sharedPipeline.interrupt();
}

async function mute() {
  muted = true;
  await clearQueue();
}

function unmute() {
  muted = false;
}

function isSpeaking() {
  return sharedPipeline.isSpeaking() || ttsEngine.isSpeaking();
}

function getPipeline() {
  return sharedPipeline;
}

function isBootGreetingEnabled() {
  return Boolean(config.bootGreeting);
}

module.exports = {
  init,
  speak,
  emitEvent,
  clearQueue,
  mute,
  unmute,
  isSpeaking,
  isBootGreetingEnabled,
  getConfig,
  applyConfig,
  loadConfig,
  setMode,
  getMode,
  triggerCall,
  stopCall,
  getPipeline,
  VERBOSITY,
  EVENT_VERBOSITY,
  SYSTEM_EVENT_PHRASES,
  CUSTOMER_EVENT_PHRASES,
};
