'use strict';

const os = require('os');
const { spawn, spawnSync } = require('child_process');

const DEFAULT_VOLUME = 0.9;

// ── Voice profiles ────────────────────────────────────────────────────────────
const VOICE_PROFILES = {
  default_futuristic: { pitch: 1.0,  speed: 1.0,  amplitude: 180, tone: 'futuristic' },
  minimal_assistant:  { pitch: 0.95, speed: 0.95, amplitude: 160, tone: 'neutral'    },
  system_core:        { pitch: 0.88, speed: 0.9,  amplitude: 180, tone: 'sharp'      },
  stealth_mode:       { pitch: 1.0,  speed: 0.88, amplitude: 80,  tone: 'calm'       },
};

// Tone → espeak voice variant
const TONE_ESPEAK_VARIANT = {
  futuristic: 'rob',
  neutral:    '',
  calm:       'f5',
  sharp:      'croak',
};

// ── Engine state ──────────────────────────────────────────────────────────────
let initialized = false;
let backend = 'silent';
let silentMode = true;
let speaking = false;
let currentProcess = null;
let engineVolume = DEFAULT_VOLUME;
let enginePitch = 1.0;
let engineSpeed = 1.0;
let engineAmplitude = 180;
let engineTone = 'futuristic';
let engineVoiceId = 'default';
let queue = [];
let draining = false;
let consecutiveFailures = 0;

// ── Utility helpers ───────────────────────────────────────────────────────────

function commandExists(command) {
  try {
    const isWindows = os.platform() === 'win32';
    const checker = isWindows ? 'where' : 'which';
    const args = isWindows ? ['/Q', command] : [command];
    const result = spawnSync(checker, args, { stdio: 'ignore' });
    return result.status === 0;
  } catch (_err) {
    return false;
  }
}

function clamp(val, min, max) {
  const parsed = Number(val);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(max, Math.max(min, parsed));
}

function clampVolume(raw) {
  return clamp(raw, 0, 1);
}

function detectBackend() {
  if (os.platform() === 'darwin' && commandExists('say')) return 'say';
  if (os.platform() === 'linux' && commandExists('espeak-ng')) return 'espeak-ng';
  if (os.platform() === 'linux' && commandExists('espeak')) return 'espeak';
  if (os.platform() === 'linux' && commandExists('spd-say')) return 'spd-say';
  if (os.platform() === 'win32' && commandExists('powershell')) return 'powershell';
  return 'silent';
}

// ── Futuristic text normalization ─────────────────────────────────────────────
const PHRASE_TRANSFORMS = [
  [/\bHey[,!]?\s*/gi, ''],
  [/\bexcellent[!.]?/gi, 'Confirmed.'],
  [/\beverything is working fine\b.*/i, 'All systems operational.'],
  [/\btask (?:has been )?added/i, 'Task assigned.'],
  [/\btask (?:has been )?completed/i, 'Task complete.'],
  [/\bError detected\b/i, 'Error detected.'],
  [/\bplease\s+/gi, ''],
  [/\bjust\s+/gi, ''],
];

function normalizeText(raw) {
  let text = String(raw || '').trim();
  for (const [pattern, replacement] of PHRASE_TRANSFORMS) {
    text = text.replace(pattern, replacement);
  }
  return text.replace(/\s{2,}/g, ' ').trim();
}

// ── Command builders ──────────────────────────────────────────────────────────

function buildCommand(text) {
  if (backend === 'say') {
    const wpm = Math.round(clamp(engineSpeed, 0.5, 2) * 180);
    const args = ['-r', String(wpm)];
    if (engineVoiceId && engineVoiceId !== 'default') args.push('-v', String(engineVoiceId));
    args.push(text);
    return { cmd: 'say', args };
  }

  if (backend === 'espeak-ng' || backend === 'espeak') {
    const speedWpm = Math.round(clamp(engineSpeed, 0.5, 2) * 165);
    const pitchVal = Math.round(clamp(enginePitch, 0.5, 2) * 50);
    const amp = engineAmplitude;
    const variant = TONE_ESPEAK_VARIANT[engineTone] || '';
    const voiceArg = variant ? `en+${variant}` : 'en';
    return {
      cmd: backend,
      args: ['-s', String(speedWpm), '-p', String(pitchVal), '-a', String(amp), '-v', voiceArg, text],
    };
  }

  if (backend === 'spd-say') {
    return { cmd: 'spd-say', args: [text] };
  }

  if (backend === 'powershell') {
    const encoded = Buffer.from(text, 'utf8').toString('base64');
    const volumePct = Math.round(clampVolume(engineVolume) * 100);
    const rate = Math.round(clamp((engineSpeed - 1.0) * 10, -10, 10));
    const script = [
      'Add-Type -AssemblyName System.Speech;',
      `$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${encoded}'));`,
      '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;',
      `$s.Volume = ${volumePct};`,
      `$s.Rate = ${rate};`,
      '$s.Speak($text);',
    ].join(' ');
    return { cmd: 'powershell', args: ['-NoProfile', '-Command', script] };
  }

  return null;
}

// ── Public API ────────────────────────────────────────────────────────────────

function loadVoice(voiceId) {
  engineVoiceId = String(voiceId || 'default');
  const profile = VOICE_PROFILES[voiceId];
  if (profile) {
    enginePitch = profile.pitch;
    engineSpeed = profile.speed;
    engineAmplitude = profile.amplitude;
    engineTone = profile.tone;
  }
}

function setPitch(value) {
  enginePitch = clamp(value, 0.5, 2);
}

function setSpeed(value) {
  engineSpeed = clamp(value, 0.5, 2);
}

function setTone(profile) {
  const validTones = Object.keys(TONE_ESPEAK_VARIANT);
  engineTone = validTones.includes(profile) ? profile : 'neutral';
}

async function init(options = {}) {
  engineVolume = clampVolume(options.volume ?? engineVolume);

  if (options.profile && VOICE_PROFILES[options.profile]) {
    loadVoice(options.profile);
  } else {
    if (options.voiceStyle) loadVoice(options.voiceStyle);
    if (options.pitch != null) setPitch(options.pitch);
    if (options.speed != null) setSpeed(options.speed);
    if (options.tone) setTone(options.tone);
  }

  if (!initialized) {
    backend = detectBackend();
    silentMode = backend === 'silent';
    initialized = true;
    console.log(`[VOICE] Engine initialized (${backend}${silentMode ? ', silent mode' : ''})`);
  }
}

function isSpeaking() {
  return speaking;
}

async function runSpeak(text) {
  const normalized = normalizeText(text);
  if (!normalized) return;
  if (!initialized) await init();
  if (silentMode) return;

  const command = buildCommand(normalized);
  if (!command) return;

  await new Promise((resolve) => {
    speaking = true;
    console.log(`[VOICE] Speaking: ${normalized}`);
    try {
      currentProcess = spawn(command.cmd, command.args, { stdio: 'ignore' });
      currentProcess.once('exit', () => {
        currentProcess = null;
        speaking = false;
        consecutiveFailures = 0;
        resolve();
      });
      currentProcess.once('error', () => {
        currentProcess = null;
        speaking = false;
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) silentMode = true;
        resolve();
      });
    } catch (_err) {
      currentProcess = null;
      speaking = false;
      consecutiveFailures += 1;
      if (consecutiveFailures >= 3) silentMode = true;
      resolve();
    }
  });
}

async function drainQueue() {
  if (draining) return;
  draining = true;
  try {
    while (queue.length > 0) {
      const item = queue.shift();
      await runSpeak(item.text);
      item.resolve();
    }
  } finally {
    draining = false;
  }
}

async function speak(text) {
  if (!initialized) await init();
  return new Promise((resolve) => {
    queue.push({ text: String(text || ''), resolve });
    void drainQueue();
  });
}

async function stop() {
  queue = [];
  if (currentProcess && !currentProcess.killed) {
    try { currentProcess.kill('SIGTERM'); } catch (_err) { /* ignore */ }
  }
  currentProcess = null;
  speaking = false;
}

async function reconfigure(options = {}) {
  if (!initialized) {
    await init(options);
    return;
  }
  engineVolume = clampVolume(options.volume ?? engineVolume);
  if (options.profile && VOICE_PROFILES[options.profile]) {
    loadVoice(options.profile);
  } else {
    if (options.voiceStyle) loadVoice(options.voiceStyle);
    if (options.pitch != null) setPitch(options.pitch);
    if (options.speed != null) setSpeed(options.speed);
    if (options.tone) setTone(options.tone);
  }
}

module.exports = {
  init,
  speak,
  stop,
  isSpeaking,
  reconfigure,
  loadVoice,
  setPitch,
  setSpeed,
  setTone,
  VOICE_PROFILES,
};
