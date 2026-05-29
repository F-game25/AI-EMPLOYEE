'use strict';
/**
 * Auto-Update + Watchdog Service
 *
 * Two independent loops run inside the Node process:
 *
 * 1. AUTO-UPDATER  — when enabled, spawns auto_updater.py on schedule.
 *    Reads settings from ~/.ai-employee/state/update-settings.json (written by
 *    PATCH /api/system/auto-update-settings). Broadcasts SSE/WS events on
 *    start, progress, and completion.
 *
 * 2. WATCHDOG  — always active when watchdog_enabled=true. Polls /health every
 *    N seconds. On K consecutive failures it calls the provided restartFn(),
 *    then resets the failure counter. Broadcasts system:watchdog:alert and
 *    system:watchdog:recovered events.
 */

const fs    = require('fs');
const path  = require('path');
const os    = require('os');
const { spawn } = require('child_process');

const AI_HOME     = process.env.AI_HOME || path.join(os.homedir(), '.ai-employee');
const SETTINGS_FILE = path.join(AI_HOME, 'state', 'update-settings.json');
const UPDATER_SCRIPTS = [
  path.join(process.env.AI_EMPLOYEE_REPO_DIR || path.join(os.homedir(), 'AI-EMPLOYEE'),
            'runtime', 'agents', 'auto-updater', 'auto_updater.py'),
  path.join(AI_HOME, 'agents', 'auto-updater', 'auto_updater.py'),
];

const DEFAULT_SETTINGS = {
  auto_update_enabled: false,
  update_channel: 'stable',
  update_interval_minutes: 60,
  auto_restart_on_update: true,
  watchdog_enabled: true,
  watchdog_interval_seconds: 30,
  watchdog_max_failures: 3,
};

// ── Shared state (exported for the status endpoint) ──────────────────────────
const state = {
  settings: { ...DEFAULT_SETTINGS },
  watchdog: {
    running: false,
    failures: 0,
    last_check: null,
    last_failure: null,
    last_restart: null,
    status: 'idle',           // idle | healthy | degraded | restarting
    restarts_today: 0,
    _day: null,
  },
  updater: {
    running: false,
    last_run: null,
    last_success: null,
    last_error: null,
    next_run: null,
    applied_today: 0,
    _day: null,
  },
};

let _watchdogTimer = null;
let _updaterTimer  = null;
let _broadcaster   = null;
let _nodePort      = 8787;
let _restartFn     = null;

// ── Helpers ───────────────────────────────────────────────────────────────────
function loadSettings() {
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      const stored = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'));
      state.settings = { ...DEFAULT_SETTINGS, ...stored };
    }
  } catch { /* use defaults */ }
  // Clamp update interval — minimum 15 min to avoid hammering GitHub API
  state.settings.update_interval_minutes = Math.max(15, state.settings.update_interval_minutes || 60);
  state.settings.watchdog_interval_seconds = Math.max(10, state.settings.watchdog_interval_seconds || 30);
  state.settings.watchdog_max_failures = Math.max(1, state.settings.watchdog_max_failures || 3);
  return state.settings;
}

function saveSettings(partial) {
  state.settings = { ...state.settings, ...partial };
  fs.mkdirSync(path.dirname(SETTINGS_FILE), { recursive: true });
  fs.writeFileSync(SETTINGS_FILE, JSON.stringify(state.settings, null, 2));
  return state.settings;
}

function broadcast(event, payload) {
  try { _broadcaster?.broadcast(event, { ...payload, ts: new Date().toISOString() }); } catch { /* ok */ }
}

function todayStr() { return new Date().toISOString().slice(0, 10); }

function resetDailyCounters() {
  const today = todayStr();
  if (state.watchdog._day !== today) { state.watchdog.restarts_today = 0; state.watchdog._day = today; }
  if (state.updater._day  !== today) { state.updater.applied_today   = 0; state.updater._day  = today; }
}

// ── Watchdog loop ─────────────────────────────────────────────────────────────
async function watchdogTick() {
  resetDailyCounters();
  const { watchdog_enabled, watchdog_max_failures } = state.settings;
  if (!watchdog_enabled) { state.watchdog.status = 'idle'; return; }

  state.watchdog.running = true;
  state.watchdog.last_check = new Date().toISOString();

  const url = `http://127.0.0.1:${_nodePort}/health`;
  let ok = false;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    ok = res.ok;
  } catch { ok = false; }

  if (ok) {
    const wasDown = state.watchdog.failures > 0;
    state.watchdog.failures = 0;
    state.watchdog.status = 'healthy';
    if (wasDown) {
      broadcast('system:watchdog:recovered', { node_port: _nodePort });
    }
  } else {
    state.watchdog.failures++;
    state.watchdog.last_failure = new Date().toISOString();
    state.watchdog.status = state.watchdog.failures >= watchdog_max_failures ? 'restarting' : 'degraded';
    broadcast('system:watchdog:alert', {
      failures: state.watchdog.failures,
      max: watchdog_max_failures,
      status: state.watchdog.status,
    });

    if (state.watchdog.failures >= watchdog_max_failures) {
      state.watchdog.failures = 0;
      state.watchdog.last_restart = new Date().toISOString();
      state.watchdog.restarts_today++;
      broadcast('system:watchdog:restarting', { restarts_today: state.watchdog.restarts_today });
      try { await _restartFn?.(); } catch (e) {
        broadcast('system:watchdog:restart_failed', { error: e.message });
      }
    }
  }
}

function startWatchdog() {
  if (_watchdogTimer) clearInterval(_watchdogTimer);
  const iv = (state.settings.watchdog_interval_seconds || 30) * 1000;
  _watchdogTimer = setInterval(() => watchdogTick().catch(() => {}), iv);
  // first tick after 5s so the system has time to settle
  setTimeout(() => watchdogTick().catch(() => {}), 5000);
}

function stopWatchdog() {
  if (_watchdogTimer) { clearInterval(_watchdogTimer); _watchdogTimer = null; }
  state.watchdog.running = false;
  state.watchdog.status = 'idle';
}

// ── Auto-updater loop ─────────────────────────────────────────────────────────
function findUpdaterScript() {
  return UPDATER_SCRIPTS.find(p => fs.existsSync(p)) || null;
}

function runUpdater() {
  if (state.updater.running) return;
  const script = findUpdaterScript();
  if (!script) {
    state.updater.last_error = 'auto_updater.py not found';
    broadcast('system:update:error', { error: state.updater.last_error });
    return;
  }

  state.updater.running = true;
  state.updater.last_run = new Date().toISOString();
  broadcast('system:update:started', { script, channel: state.settings.update_channel });

  const env = {
    ...process.env,
    AI_EMPLOYEE_REPO_DIR: process.env.AI_EMPLOYEE_REPO_DIR || path.join(os.homedir(), 'AI-EMPLOYEE'),
    PYTHONUNBUFFERED: '1',
    AI_EMPLOYEE_BRANCH: state.settings.update_channel === 'beta' ? 'develop' : 'main',
  };

  const child = spawn(process.env.PYTHON_BIN || 'python3', [script, '--once'], {
    env,
    cwd: env.AI_EMPLOYEE_REPO_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const lines = [];
  const onData = (chunk, level) => {
    chunk.toString().split('\n').filter(l => l.trim()).forEach(line => {
      lines.push({ line, level, ts: Date.now() });
      broadcast('system:update:log', { line, level });
    });
  };

  child.stdout.on('data', chunk => onData(chunk, 'info'));
  child.stderr.on('data', chunk => onData(chunk, 'warn'));

  child.on('close', code => {
    state.updater.running = false;
    const success = code === 0;
    if (success) {
      state.updater.last_success = new Date().toISOString();
      state.updater.applied_today++;
      broadcast('system:update:complete', { success: true, lines: lines.length });
      if (state.settings.auto_restart_on_update) {
        broadcast('system:update:restarting', {});
        // Give WS clients 2s to receive the event before restart
        setTimeout(() => _restartFn?.().catch(() => {}), 2000);
      }
    } else {
      state.updater.last_error = `Exit ${code}`;
      broadcast('system:update:complete', { success: false, exit_code: code });
    }
    scheduleNextUpdate();
  });

  child.on('error', err => {
    state.updater.running = false;
    state.updater.last_error = err.message;
    broadcast('system:update:error', { error: err.message });
    scheduleNextUpdate();
  });
}

function scheduleNextUpdate() {
  if (_updaterTimer) clearTimeout(_updaterTimer);
  if (!state.settings.auto_update_enabled) { state.updater.next_run = null; return; }
  const ms = (state.settings.update_interval_minutes || 60) * 60 * 1000;
  state.updater.next_run = new Date(Date.now() + ms).toISOString();
  _updaterTimer = setTimeout(() => runUpdater(), ms);
}

function startAutoUpdater() {
  // First run: small initial delay so startup noise settles
  if (_updaterTimer) clearTimeout(_updaterTimer);
  const initialMs = 30 * 1000; // 30s after enabling
  state.updater.next_run = new Date(Date.now() + initialMs).toISOString();
  _updaterTimer = setTimeout(() => runUpdater(), initialMs);
}

function stopAutoUpdater() {
  if (_updaterTimer) { clearTimeout(_updaterTimer); _updaterTimer = null; }
  state.updater.next_run = null;
}

// ── Public API ────────────────────────────────────────────────────────────────
function init({ broadcaster, nodePort, restartFn }) {
  _broadcaster = broadcaster;
  _nodePort    = nodePort || 8787;
  _restartFn   = restartFn;

  loadSettings();

  if (state.settings.watchdog_enabled) startWatchdog();
  if (state.settings.auto_update_enabled) startAutoUpdater();
}

function applySettings(partial) {
  const prev = { ...state.settings };
  saveSettings(partial);
  loadSettings(); // re-clamp

  // Watchdog: restart if interval changed or toggled
  if (partial.watchdog_enabled !== undefined || partial.watchdog_interval_seconds !== undefined) {
    stopWatchdog();
    if (state.settings.watchdog_enabled) startWatchdog();
  }

  // Auto-updater: restart if toggled or interval changed
  if (partial.auto_update_enabled !== undefined || partial.update_interval_minutes !== undefined
      || partial.update_channel !== undefined) {
    stopAutoUpdater();
    if (state.settings.auto_update_enabled && !prev.auto_update_enabled) {
      startAutoUpdater();
    } else if (state.settings.auto_update_enabled) {
      scheduleNextUpdate(); // reschedule with new interval
    }
  }

  return state.settings;
}

function getStatus() {
  resetDailyCounters();
  return {
    settings: { ...state.settings },
    watchdog: { ...state.watchdog, timer_active: !!_watchdogTimer },
    updater:  { ...state.updater,  timer_active: !!_updaterTimer, script_found: !!findUpdaterScript() },
  };
}

function triggerManualUpdate() {
  runUpdater();
}

module.exports = { init, applySettings, getStatus, triggerManualUpdate, loadSettings };
