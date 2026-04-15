'use strict';

const fs = require('fs');
const path = require('path');
const ttsEngine = require('../services/voice/tts_engine');

const VOICE_CONFIG_PATH = path.resolve(__dirname, '../../config/voice.json');
const DEFAULT_CONFIG = {
  enabled: true,
  volume: 0.9,
  voiceStyle: 'default',
  bootGreeting: true,
};

let config = { ...DEFAULT_CONFIG };
let initialized = false;
let muted = false;
let queue = [];
let draining = false;
let queueEpoch = 0;
const phraseCache = new Map();

function loadConfig() {
  try {
    const raw = fs.readFileSync(VOICE_CONFIG_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    config = { ...DEFAULT_CONFIG, ...(parsed && typeof parsed === 'object' ? parsed : {}) };
  } catch (_err) {
    config = { ...DEFAULT_CONFIG };
  }
}

function isEnabled() {
  return Boolean(config.enabled) && !muted;
}

function getCachedPhrase(text) {
  const normalized = String(text || '').trim();
  if (!normalized) return '';
  const key = normalized.toLowerCase();
  if (phraseCache.has(key)) return phraseCache.get(key);
  if (normalized.length <= 120) phraseCache.set(key, normalized);
  return normalized;
}

async function init() {
  if (initialized) return;
  loadConfig();
  await ttsEngine.init({ volume: config.volume, voiceStyle: config.voiceStyle });
  initialized = true;
}

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
    while (queue.length > 0 && runEpoch === queueEpoch) {
      const skipped = queue.shift();
      skipped.resolve(false);
    }
  } finally {
    draining = false;
    if (queue.length > 0 && isEnabled()) void processQueue();
  }
}

async function speak(text, priority = false) {
  const phrase = getCachedPhrase(text);
  if (!phrase) return false;
  await init();
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

function isBootGreetingEnabled() {
  return Boolean(config.bootGreeting);
}

function isSpeaking() {
  return ttsEngine.isSpeaking();
}

module.exports = {
  init,
  speak,
  clearQueue,
  mute,
  unmute,
  isSpeaking,
  isBootGreetingEnabled,
};
