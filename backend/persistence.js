'use strict';

/**
 * JSON file-based state persistence for the AI Employee backend.
 *
 * Saves and restores runtime state, brain insights, and agent performance
 * so the dashboard survives restarts without data loss.
 *
 * Write strategy: atomic write (tmp → rename) to avoid corruption.
 * Read strategy: safe JSON parse with fallback to empty state.
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = path.resolve(__dirname, '..', '.data');
const STATE_FILE = path.join(DATA_DIR, 'runtime_state.json');
const BRAIN_FILE = path.join(DATA_DIR, 'brain_state.json');

// Auto-save interval in milliseconds (30 seconds)
const AUTO_SAVE_INTERVAL_MS = 30_000;

let _autoSaveTimer = null;

function ensureDataDir() {
  try {
    if (!fs.existsSync(DATA_DIR)) {
      fs.mkdirSync(DATA_DIR, { recursive: true });
    }
  } catch {
    // Silently fail — persistence is best-effort
  }
}

/**
 * Atomically write JSON data to a file.
 * Writes to a .tmp sibling first, then renames, to avoid partial-write corruption.
 */
function writeJsonSafe(filePath, data) {
  try {
    ensureDataDir();
    const tmp = filePath + '.tmp';
    const json = JSON.stringify(data, null, 2);
    fs.writeFileSync(tmp, json, 'utf8');
    fs.renameSync(tmp, filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Read and parse JSON from a file. Returns null on failure.
 */
function readJsonSafe(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Save runtime state snapshot.
 * Only saves the metrics and logs — not transient fields like WebSocket refs.
 */
function saveRuntimeState(runtimeState) {
  const snapshot = {
    tasksExecuted: runtimeState.tasksExecuted || 0,
    successfulTasks: runtimeState.successfulTasks || 0,
    failedTasks: runtimeState.failedTasks || 0,
    valueGenerated: runtimeState.valueGenerated || 0,
    revenueCents: runtimeState.revenueCents || 0,
    pipelineRoiTotal: runtimeState.pipelineRoiTotal || 0,
    pipelineRuns: (runtimeState.pipelineRuns || []).slice(0, 50),
    activityFeed: (runtimeState.activityFeed || []).slice(0, 50),
    executionLogs: (runtimeState.executionLogs || []).slice(0, 100),
    skillStats: runtimeState.skillStats || {},
    objectives: (runtimeState.objectives || []).slice(-100),
    objectiveState: runtimeState.objectiveState || {},
    objectiveTaskMeta: runtimeState.objectiveTaskMeta || {},
    savedAt: new Date().toISOString(),
  };
  return writeJsonSafe(STATE_FILE, snapshot);
}

/**
 * Load previously saved runtime state.
 * Returns null if no state was saved.
 */
function loadRuntimeState() {
  return readJsonSafe(STATE_FILE);
}

/**
 * Save brain state (strategies, patterns, performance metrics).
 */
function saveBrainState(brainData) {
  return writeJsonSafe(BRAIN_FILE, {
    ...brainData,
    savedAt: new Date().toISOString(),
  });
}

/**
 * Load brain state. Returns null if not available.
 */
function loadBrainState() {
  return readJsonSafe(BRAIN_FILE);
}

/**
 * Start periodic auto-save. Accepts a getter function that returns
 * the current state to save.
 */
function startAutoSave(stateGetter, brainGetter) {
  stopAutoSave();
  _autoSaveTimer = setInterval(() => {
    try {
      if (stateGetter) saveRuntimeState(stateGetter());
      if (brainGetter) saveBrainState(brainGetter());
    } catch {
      // Best-effort — don't crash the server
    }
  }, AUTO_SAVE_INTERVAL_MS);
  // Don't keep the process alive just for auto-save
  if (_autoSaveTimer.unref) _autoSaveTimer.unref();
}

/**
 * Stop periodic auto-save.
 */
function stopAutoSave() {
  if (_autoSaveTimer) {
    clearInterval(_autoSaveTimer);
    _autoSaveTimer = null;
  }
}

module.exports = {
  saveRuntimeState,
  loadRuntimeState,
  saveBrainState,
  loadBrainState,
  startAutoSave,
  stopAutoSave,
  DATA_DIR,
};
