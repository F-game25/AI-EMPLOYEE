'use strict';

const os = require('os');
const { spawn, spawnSync } = require('child_process');

const DEFAULT_VOLUME = 0.9;

let initialized = false;
let backend = 'silent';
let silentMode = true;
let speaking = false;
let currentProcess = null;
let volume = DEFAULT_VOLUME;
let voiceStyle = 'default';
let queue = [];
let draining = false;

function commandExists(command) {
  const checker = os.platform() === 'win32' ? 'where' : 'which';
  const result = spawnSync(checker, [command], { stdio: 'ignore' });
  return result.status === 0;
}

function clampVolume(raw) {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_VOLUME;
  return Math.min(1, Math.max(0, parsed));
}

function detectBackend() {
  if (os.platform() === 'darwin' && commandExists('say')) return 'say';
  if (os.platform() === 'linux' && commandExists('espeak-ng')) return 'espeak-ng';
  if (os.platform() === 'linux' && commandExists('espeak')) return 'espeak';
  if (os.platform() === 'linux' && commandExists('spd-say')) return 'spd-say';
  if (os.platform() === 'win32' && commandExists('powershell')) return 'powershell';
  return 'silent';
}

function buildCommand(text) {
  if (backend === 'say') {
    const args = ['-r', '180'];
    if (voiceStyle && voiceStyle !== 'default') args.push('-v', String(voiceStyle));
    args.push(text);
    return { cmd: 'say', args };
  }
  if (backend === 'espeak-ng' || backend === 'espeak') {
    return {
      cmd: backend,
      args: ['-s', '165', '-a', String(Math.round(clampVolume(volume) * 200)), text],
    };
  }
  if (backend === 'spd-say') {
    return { cmd: 'spd-say', args: [text] };
  }
  if (backend === 'powershell') {
    const escaped = text.replace(/'/g, "''");
    const script = [
      'Add-Type -AssemblyName System.Speech;',
      '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;',
      `$s.Volume = ${Math.round(clampVolume(volume) * 100)};`,
      `$s.Speak('${escaped}');`,
    ].join(' ');
    return { cmd: 'powershell', args: ['-NoProfile', '-Command', script] };
  }
  return null;
}

async function init(options = {}) {
  if (initialized) return;
  volume = clampVolume(options.volume);
  voiceStyle = String(options.voiceStyle || 'default');
  backend = detectBackend();
  silentMode = backend === 'silent';
  initialized = true;
  console.log(`[VOICE] Engine initialized (${backend}${silentMode ? ', silent mode' : ''})`);
}

function isSpeaking() {
  return speaking;
}

async function runSpeak(text) {
  if (!text || !String(text).trim()) return;
  if (!initialized) await init();
  if (silentMode) return;

  const command = buildCommand(String(text));
  if (!command) return;

  await new Promise((resolve) => {
    speaking = true;
    console.log(`[VOICE] Speaking: ${String(text)}`);
    try {
      currentProcess = spawn(command.cmd, command.args, { stdio: 'ignore' });
      currentProcess.once('exit', () => {
        currentProcess = null;
        speaking = false;
        resolve();
      });
      currentProcess.once('error', () => {
        currentProcess = null;
        speaking = false;
        silentMode = true;
        resolve();
      });
    } catch (_err) {
      currentProcess = null;
      speaking = false;
      silentMode = true;
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
    try {
      currentProcess.kill('SIGTERM');
    } catch (_err) {
      // ignore
    }
  }
  currentProcess = null;
  speaking = false;
}

module.exports = {
  init,
  speak,
  stop,
  isSpeaking,
};
