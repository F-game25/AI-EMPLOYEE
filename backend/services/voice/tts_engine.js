'use strict';

const os = require('os');
const { spawn, spawnSync } = require('child_process');
const fishSpeech = require('./fish_speech');
const voiceCore = require('./voice_core_local');
const voiceLite = require('./voice_lite');
const kokoro = require('./kokoro');

const DEFAULT_VOLUME = 0.9;

// ── Voice profiles ────────────────────────────────────────────────────────────
// system profiles: futuristic, terse, robotic
// customer profiles: natural, warm, human-like
const VOICE_PROFILES = {
  // ── System (internal AI) ────────────────────────────────────────────────────
  default_futuristic: { pitch: 1.0,  speed: 1.0,  amplitude: 180, tone: 'futuristic', channel: 'system'   },
  minimal_assistant:  { pitch: 0.95, speed: 0.95, amplitude: 160, tone: 'neutral',    channel: 'system'   },
  system_core:        { pitch: 0.88, speed: 0.9,  amplitude: 180, tone: 'sharp',      channel: 'system'   },
  stealth_mode:       { pitch: 1.0,  speed: 0.88, amplitude: 80,  tone: 'calm',       channel: 'system'   },
  // ── Customer (external / call centre) ──────────────────────────────────────
  customer_default:          { pitch: 1.08, speed: 1.0,  amplitude: 160, tone: 'warm',         channel: 'customer' },
  customer_friendly:         { pitch: 1.12, speed: 1.05, amplitude: 155, tone: 'warm',         channel: 'customer' },
  customer_professional:     { pitch: 1.0,  speed: 0.95, amplitude: 170, tone: 'professional', channel: 'customer' },
  customer_fast_response:    { pitch: 1.05, speed: 1.15, amplitude: 160, tone: 'warm',         channel: 'customer' },
};

// Tone → espeak voice variant
// Customer tones use softer/more natural voices
const TONE_ESPEAK_VARIANT = {
  // system
  futuristic:    'rob',
  neutral:       '',
  calm:          'f5',
  sharp:         'croak',
  // customer
  warm:          'f3',
  professional:  '',
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
let engineChannel = 'system'; // 'system' | 'customer'
let engineProvider = 'voice_core_local'; // 'voice_core_local' | 'voice_lite' | 'fish_speech' | 'local'
let engineFishOptions = { ...fishSpeech.DEFAULT_OPTIONS };
let engineVoiceCoreOptions = { enabled: true, language: 'en', voice: 'default', emotion: 'warm_confident', threads: 4, timeoutMs: 30000, localFallback: false };
let engineVoiceLiteOptions = { enabled: true, language: 'en', voice: 'custom', threads: 4, timeoutMs: 30000, localFallback: true };
let engineKokoroOptions = { ...kokoro.DEFAULT_OPTIONS };
let lastProviderError = null;
let lastArtifact = null;
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

// ── Text normalization ────────────────────────────────────────────────────────
// System channel: short, terse, no filler
const SYSTEM_TRANSFORMS = [
  [/\bHey[,!]?\s*/gi, ''],
  [/\bexcellent[!.]?/gi, 'Confirmed.'],
  [/\beverything is working fine\b.*/i, 'All systems operational.'],
  [/\btask (?:has been )?added/i, 'Task assigned.'],
  [/\btask (?:has been )?completed/i, 'Task complete.'],
  [/\bError detected\b/i, 'Error detected.'],
  [/\bplease\s+/gi, ''],
  [/\bjust\s+/gi, ''],
];

// Customer channel: polite, conversational, helpful
const CUSTOMER_TRANSFORMS = [
  [/^Task assigned\.$/, 'Your request has been received. We\'ll take care of that right away.'],
  [/^Task complete\.$/, 'Your request has been completed successfully. Is there anything else I can help you with?'],
  [/^Error detected\.$/, 'We\'ve encountered a small issue. Our team is looking into it right away.'],
  [/^Systems online\.$/, 'Hello! Thank you for calling. How can I assist you today?'],
  [/^All systems operational\.$/, 'Everything is running smoothly on our end.'],
];

function normalizeText(raw, channel) {
  let text = String(raw || '').trim();
  const transforms = channel === 'customer' ? CUSTOMER_TRANSFORMS : SYSTEM_TRANSFORMS;
  for (const [pattern, replacement] of transforms) {
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
    engineChannel = profile.channel || 'system';
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

function setChannel(channel) {
  engineChannel = channel === 'customer' ? 'customer' : 'system';
}

function setProvider(provider) {
  const value = String(provider || '').trim();
  if (value === 'voice_core_local' || value === 'voice_core' || value === 'default_voice') engineProvider = 'voice_core_local';
  else if (value.startsWith('voice_lite')) engineProvider = 'voice_lite';
  else engineProvider = ['fish_speech', 'local'].includes(value) ? value : 'voice_core_local';
}

function getChannel() {
  return engineChannel;
}

async function init(options = {}) {
  setProvider(options.provider || engineProvider);
  if (options.fishSpeech && typeof options.fishSpeech === 'object') {
    engineFishOptions = fishSpeech.configure({ ...engineFishOptions, ...options.fishSpeech });
  } else {
    engineFishOptions = fishSpeech.configure(engineFishOptions);
  }
  if (options.voiceCore && typeof options.voiceCore === 'object') {
    engineVoiceCoreOptions = { ...engineVoiceCoreOptions, ...options.voiceCore };
  }
  if (options.voiceLite && typeof options.voiceLite === 'object') {
    engineVoiceLiteOptions = { ...engineVoiceLiteOptions, ...options.voiceLite };
  }
  if (options.kokoro && typeof options.kokoro === 'object') {
    engineKokoroOptions = kokoro.configure({ ...engineKokoroOptions, ...options.kokoro });
  }

  engineVolume = clampVolume(options.volume ?? engineVolume);

  if (options.profile && VOICE_PROFILES[options.profile]) {
    loadVoice(options.profile);
  } else {
    if (options.voiceStyle) loadVoice(options.voiceStyle);
    if (options.pitch != null) setPitch(options.pitch);
    if (options.speed != null) setSpeed(options.speed);
    if (options.tone) setTone(options.tone);
    if (options.channel) setChannel(options.channel);
  }

  if (!initialized) {
    backend = detectBackend();
    silentMode = backend === 'silent';
    initialized = true;
    console.log(`[VOICE] Engine initialized (provider=${engineProvider}, fallback=${backend}${silentMode ? ', silent mode' : ''})`);
  }
}

function isSpeaking() {
  return speaking;
}

async function runSpeak(text, channel) {
  const resolvedChannel = channel || engineChannel || 'system';
  const normalized = normalizeText(text, resolvedChannel);
  if (!normalized) return;
  if (!initialized) await init();

  if (engineProvider === 'voice_core_local' && engineVoiceCoreOptions.enabled !== false) {
    try {
      const status = await voiceCore.getStatus({ language: engineVoiceCoreOptions.language });
      if (status.state === 'ready') {
        speaking = true;
        console.log(`[VOICE:${resolvedChannel}] Default Human Voice: ${normalized}`);
        const result = await voiceCore.synthesize(normalized, {
          language: engineVoiceCoreOptions.language,
          voice: engineVoiceCoreOptions.voice || 'default',
          gender: engineVoiceCoreOptions.gender,
          tone: engineVoiceCoreOptions.tone || engineTone,
          warmth: engineVoiceCoreOptions.warmth,
          emotion: engineVoiceCoreOptions.emotion || engineTone || 'warm_confident',
          emotion_intensity: engineVoiceCoreOptions.emotionIntensity,
          speaking_rate: engineVoiceCoreOptions.speakingRate || engineSpeed,
          energy: engineVoiceCoreOptions.energy,
          threads: engineVoiceCoreOptions.threads,
          timeoutMs: engineVoiceCoreOptions.timeoutMs,
          persona: {
            speed: engineVoiceCoreOptions.speakingRate || engineSpeed,
            tone: engineVoiceCoreOptions.tone || engineTone,
            warmth: engineVoiceCoreOptions.warmth,
            energy: engineVoiceCoreOptions.energy,
            gender: engineVoiceCoreOptions.gender,
          },
        });
        lastArtifact = voiceCore.saveArtifact(result.audioBuf);
        const played = await playAudioFile(lastArtifact.path).catch((err) => {
          lastProviderError = String(err.message || err);
          return false;
        });
        lastProviderError = null;
        speaking = false;
        consecutiveFailures = 0;
        if (played) return;
        lastProviderError = 'Default Human Voice produced audio, but no local WAV player is available for server-side playback.';
        if (!engineVoiceCoreOptions.localFallback) return;
      }
      lastProviderError = status.recommendation || `Default Human Voice is not ready: ${status.state}`;
      if (!engineVoiceCoreOptions.localFallback) return;
    } catch (err) {
      speaking = false;
      lastProviderError = String(err.message || err);
      consecutiveFailures += 1;
      console.warn(`[VOICE] Default Human Voice failed: ${lastProviderError}`);
      if (!engineVoiceCoreOptions.localFallback) return;
    }
  }

  if (engineProvider === 'kokoro' && engineKokoroOptions.enabled !== false) {
    try {
      const status = await kokoro.getStatus();
      if (status.ready) {
        speaking = true;
        console.log(`[VOICE:${resolvedChannel}] Kokoro 82M: ${normalized}`);
        const result = await kokoro.synthesize(normalized, {
          voice: engineKokoroOptions.voice,
          speed: engineSpeed,
          language: engineKokoroOptions.language,
          timeoutMs: engineKokoroOptions.timeoutMs,
        });
        if (result.ok && result.audioBuf) {
          lastArtifact = kokoro.saveArtifact(result.audioBuf);
          const played = await playAudioFile(lastArtifact.path).catch((err) => {
            lastProviderError = String(err.message || err);
            return false;
          });
          lastProviderError = null;
          speaking = false;
          consecutiveFailures = 0;
          if (played) return;
          lastProviderError = 'Kokoro produced audio, but no local WAV player is available for server-side playback.';
        } else {
          lastProviderError = result.reason || 'Kokoro synthesis failed';
        }
      } else {
        lastProviderError = status.install || 'Kokoro is not ready (model not installed).';
      }
    } catch (err) {
      speaking = false;
      lastProviderError = String(err.message || err);
      consecutiveFailures += 1;
      console.warn(`[VOICE] Kokoro failed, using local fallback: ${lastProviderError}`);
    }
  }

  if (engineProvider === 'voice_lite' && engineVoiceLiteOptions.enabled !== false) {
    try {
      const status = await voiceLite.getStatus({ language: engineVoiceLiteOptions.language });
      if (status.state === 'ready') {
        speaking = true;
        console.log(`[VOICE:${resolvedChannel}] Voice Lite CPU: ${normalized}`);
        const result = await voiceLite.synthesize(normalized, {
          language: engineVoiceLiteOptions.language,
          voice: engineVoiceLiteOptions.voice || 'custom',
          threads: engineVoiceLiteOptions.threads,
          timeoutMs: engineVoiceLiteOptions.timeoutMs,
          persona: { speed: engineSpeed, tone: engineTone },
        });
        lastArtifact = voiceLite.saveArtifact(result.audioBuf);
        const played = await playAudioFile(lastArtifact.path).catch((err) => {
          lastProviderError = String(err.message || err);
          return false;
        });
        lastProviderError = null;
        speaking = false;
        consecutiveFailures = 0;
        if (played) return;
        lastProviderError = 'Voice Lite produced audio, but no local WAV player is available for server-side playback.';
        if (!engineVoiceLiteOptions.localFallback) return;
      }
      lastProviderError = status.recommendation || `Voice Lite is not ready: ${status.state}`;
    } catch (err) {
      speaking = false;
      lastProviderError = String(err.message || err);
      consecutiveFailures += 1;
      console.warn(`[VOICE] Voice Lite failed, using local fallback: ${lastProviderError}`);
      if (!engineVoiceLiteOptions.localFallback) return;
    }
  }

  if (engineProvider === 'fish_speech' && engineFishOptions.enabled) {
    try {
      const ok = await fishSpeech.checkAvailability();
      if (ok) {
        speaking = true;
        console.log(`[VOICE:${resolvedChannel}] Fish Speech S2 local: ${normalized}`);
        lastArtifact = await fishSpeech.synthesizeAndPlay(normalized, {
          ...engineFishOptions,
          speed: engineSpeed,
          channel: resolvedChannel,
        });
        lastProviderError = null;
        speaking = false;
        consecutiveFailures = 0;
        return;
      }
      lastProviderError = fishSpeech.getStatus().last_error || 'Fish Speech local server is unavailable';
    } catch (err) {
      speaking = false;
      lastProviderError = String(err.message || err);
      consecutiveFailures += 1;
      console.warn(`[VOICE] Fish Speech S2 failed, using local fallback: ${lastProviderError}`);
      if (!engineFishOptions.localFallback) return;
    }
  }

  if (silentMode) return;

  const command = buildCommand(normalized);
  if (!command) return;

  await new Promise((resolve) => {
    speaking = true;
    console.log(`[VOICE:${resolvedChannel}] Speaking: ${normalized}`);
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

function audioPlayerCommand(filePath) {
  if (os.platform() === 'linux' && commandExists('aplay')) return { cmd: 'aplay', args: ['-q', filePath] };
  if (os.platform() === 'linux' && commandExists('paplay')) return { cmd: 'paplay', args: [filePath] };
  if (os.platform() === 'darwin' && commandExists('afplay')) return { cmd: 'afplay', args: [filePath] };
  if (os.platform() === 'win32' && commandExists('powershell')) {
    const ps = `(New-Object Media.SoundPlayer '${filePath.replace(/'/g, "''")}').PlaySync()`;
    return { cmd: 'powershell', args: ['-NoProfile', '-Command', ps] };
  }
  return null;
}

function playAudioFile(filePath) {
  const command = audioPlayerCommand(filePath);
  if (!command) return Promise.resolve(false);
  return new Promise((resolve, reject) => {
    const child = spawn(command.cmd, command.args, { stdio: 'ignore' });
    child.once('exit', (code) => code === 0 ? resolve(true) : reject(new Error(`${command.cmd} exited with code ${code}`)));
    child.once('error', reject);
  });
}

async function drainQueue() {
  if (draining) return;
  draining = true;
  try {
    while (queue.length > 0) {
      const item = queue.shift();
      await runSpeak(item.text, item.channel);
      item.resolve();
    }
  } finally {
    draining = false;
  }
}

async function speak(text, channel) {
  if (!initialized) await init();
  return new Promise((resolve) => {
    queue.push({ text: String(text || ''), channel: channel || engineChannel, resolve });
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
  setProvider(options.provider || engineProvider);
  if (options.fishSpeech && typeof options.fishSpeech === 'object') {
    engineFishOptions = fishSpeech.configure({ ...engineFishOptions, ...options.fishSpeech });
  }
  if (options.voiceLite && typeof options.voiceLite === 'object') {
    engineVoiceLiteOptions = { ...engineVoiceLiteOptions, ...options.voiceLite };
  }
  if (options.kokoro && typeof options.kokoro === 'object') {
    engineKokoroOptions = kokoro.configure({ ...engineKokoroOptions, ...options.kokoro });
  }
  engineVolume = clampVolume(options.volume ?? engineVolume);
  if (options.profile && VOICE_PROFILES[options.profile]) {
    loadVoice(options.profile);
  } else {
    if (options.voiceStyle) loadVoice(options.voiceStyle);
    if (options.pitch != null) setPitch(options.pitch);
    if (options.speed != null) setSpeed(options.speed);
    if (options.tone) setTone(options.tone);
    if (options.channel) setChannel(options.channel);
  }
}

function getStatus() {
  return {
    initialized,
    provider: engineProvider,
    fallback_backend: backend,
    silent: silentMode,
    speaking,
    channel: engineChannel,
    voice_core_local: {
      status: engineProvider === 'voice_core_local' ? 'selected' : 'available_when_selected',
      options: { ...engineVoiceCoreOptions },
    },
    voice_lite: {
      status: engineProvider === 'voice_lite' ? 'selected' : 'available_when_selected',
      options: { ...engineVoiceLiteOptions },
    },
    kokoro: {
      status: engineProvider === 'kokoro' ? 'selected' : 'available_when_selected',
      ready: kokoro.modelsPresent(),
      options: { ...engineKokoroOptions },
    },
    fish_speech: fishSpeech.getStatus(),
    last_provider_error: lastProviderError,
    last_artifact: lastArtifact,
  };
}

// ── Chunked speak ─────────────────────────────────────────────────────────────
// Speaks an array of pre-split sentence chunks one by one with an optional
// micro-pause between each.  Used by StreamPipeline; can also be called directly.
async function speakChunked(chunks, channel, microPauseMs = 80) {
  if (!initialized) await init();
  const ch = channel || engineChannel;
  for (let i = 0; i < chunks.length; i++) {
    if (!chunks[i]) continue;
    await speak(chunks[i], ch);
    if (i < chunks.length - 1 && microPauseMs > 0) {
      await new Promise((r) => setTimeout(r, microPauseMs));
    }
  }
}

module.exports = {
  init,
  speak,
  speakChunked,
  stop,
  isSpeaking,
  reconfigure,
  loadVoice,
  setPitch,
  setSpeed,
  setTone,
  setChannel,
  setProvider,
  getChannel,
  getStatus,
  normalizeText,
  VOICE_PROFILES,
};
