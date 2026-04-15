'use strict';

const fs = require('fs');
const path = require('path');
const ttsEngine = require('../services/voice/tts_engine');

const VOICE_CONFIG_PATH = path.resolve(__dirname, '../../config/voice.json');
const MAX_CACHEABLE_PHRASE_LENGTH = 120;

// ── Verbosity levels ──────────────────────────────────────────────────────────
// 0 = silent, 1 = critical, 2 = important, 3 = normal, 4 = verbose
const VERBOSITY = { SILENT: 0, CRITICAL: 1, IMPORTANT: 2, NORMAL: 3, VERBOSE: 4 };

// Maps each event type to the minimum verbosity level required to speak it.
const EVENT_VERBOSITY = {
  system_boot:         VERBOSITY.CRITICAL,
  error_detected:      VERBOSITY.CRITICAL,
  task_created:        VERBOSITY.IMPORTANT,
  task_completed:      VERBOSITY.NORMAL,
  ai_learning_update:  VERBOSITY.VERBOSE,
};

// Event → default short phrase (futuristic, terse)
const EVENT_PHRASES = {
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

// Cooldown per event type (milliseconds) — prevents repeat announcements.
const EVENT_COOLDOWN_MS = {
  system_boot:         0,
  error_detected:      5000,
  task_created:        4000,
  task_completed:      3000,
  ai_learning_update:  10000,
};

// ── Config defaults ───────────────────────────────────────────────────────────
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
};

// ── Module state ──────────────────────────────────────────────────────────────
let config = { ...DEFAULT_CONFIG };
let initialized = false;
let muted = false;
let queue = [];
let draining = false;
let queueEpoch = 0;
const phraseCache = new Map();
const eventCooldownTimestamps = new Map();

// Pending batch for task_created queue-merge (coalesce bursts into one phrase)
let pendingTaskBatch = [];
let taskBatchTimer = null;
const TASK_BATCH_WINDOW_MS = 600;

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
      };
    }
  } catch (_err) {
    config = { ...DEFAULT_CONFIG };
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
  return { ...config };
}

function applyConfig(patch) {
  config = {
    ...config,
    ...patch,
    events: { ...config.events, ...(patch.events || {}) },
  };
  saveConfig();
  // Re-apply engine settings immediately
  void ttsEngine.reconfigure({
    profile: config.profile,
    volume: config.volume,
    pitch: config.pitch,
    speed: config.speed,
    tone: config.tone,
    voiceStyle: config.voiceStyle,
  });
}

// ── Enabled / cooldown guards ─────────────────────────────────────────────────

function isEnabled() {
  return Boolean(config.enabled) && !muted;
}

function isEventEnabled(eventName) {
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
  // Cache short/high-frequency UI phrases only to avoid unbounded memory usage.
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
      await ttsEngine.speak(next.text);
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
  });
  initialized = true;
}

async function speak(text, priority = false) {
  const phrase = getCachedPhrase(text);
  if (!phrase) return false;
  if (!initialized) await init();
  if (!isEnabled()) return false;

  return new Promise((resolve) => {
    if (priority) {
      for (const pending of queue) pending.resolve(false);
      queue = [];
      queueEpoch += 1;
      void ttsEngine.stop().finally(() => {
        queue.unshift({ text: phrase, resolve });
        void processQueue();
      });
    } else {
      queue.push({ text: phrase, resolve });
      void processQueue();
    }
  });
}

// ── Event-driven speak ────────────────────────────────────────────────────────

/**
 * Emit a named system event and speak the appropriate phrase if all guards pass.
 * @param {string} eventName  - One of the recognised event types.
 * @param {object} [data={}]  - Optional event payload.
 * @param {boolean} [force=false] - Bypass verbosity and cooldown guards.
 */
async function emitEvent(eventName, data = {}, force = false) {
  if (!initialized) await init();
  if (!isEnabled()) return false;

  // task_created events are batched for queue-merging
  if (eventName === 'task_created' && !force) {
    return batchTaskCreated(data);
  }

  if (!force) {
    if (!isEventEnabled(eventName)) return false;
    if (!verbosityAllows(eventName)) return false;
    if (!checkCooldown(eventName)) return false;
  }

  const phraseFactory = EVENT_PHRASES[eventName];
  if (!phraseFactory) return false;
  const text = phraseFactory(data);
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
    const text = EVENT_PHRASES.task_created(phraseData);
    void speak(text);
  }, TASK_BATCH_WINDOW_MS);
  // Returns false: actual speech depends on guards evaluated when the timer fires.
  return false;
}

// ── Control functions ─────────────────────────────────────────────────────────

async function clearQueue() {
  for (const pending of queue) pending.resolve(false);
  queue = [];
  queueEpoch += 1;
  await ttsEngine.stop();
}

async function mute() {
  muted = true;
  await clearQueue();
}

function unmute() {
  muted = false;
}

function isSpeaking() {
  return ttsEngine.isSpeaking();
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
  VERBOSITY,
  EVENT_VERBOSITY,
  EVENT_PHRASES,
};
