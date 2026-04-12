'use strict';

/**
 * subsystems/index.js — Central subsystem state manager.
 *
 * Manages live state for:
 *   - Neural Network (Brain) — decision-making engine
 *   - Memory Tree — structured entity memory
 *   - Doctor — system health checks
 *
 * Tries to fetch real data from the Python backend (port 8787).
 * Falls back to intelligent simulated state when the Python backend
 * is not reachable, so the UI always has something to display.
 */

const http = require('http');

const PYTHON_BACKEND = `http://127.0.0.1:${process.env.PYTHON_BACKEND_PORT || 8787}`;
const FETCH_TIMEOUT_MS = 2000;

// ── State stores ──────────────────────────────────────────────────────────────

const state = {
  nn: {
    available: true,
    active: true,
    mode: 'SIMULATED',
    learn_step: 0,
    buffer_size: 0,
    max_buffer_size: 10000,
    last_loss: null,
    confidence: 0,
    device: 'cpu',
    total_actions: 8,
    experiences: 0,
    bg_running: false,
    recent_outputs: [],
    updated_at: null,
  },
  memory: {
    total_entities: 0,
    nodes: [],
    recent_updates: [],
    updated_at: null,
  },
  doctor: {
    available: false,
    grade: null,
    overall_score: 0,
    scores: {},
    issues: [],
    strengths: [],
    last_run: null,
    updated_at: null,
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fetchJSON(path, timeoutMs = FETCH_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const url = `${PYTHON_BACKEND}${path}`;
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(new Error('Invalid JSON'));
        }
      });
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    req.on('error', reject);
  });
}

function now() {
  return new Date().toISOString();
}

// ── Simulation helpers (used when Python backend is offline) ─────────────────

let _simStep = 0;
const _simActions = [
  'route_task', 'generate_response', 'search_memory',
  'analyze_sentiment', 'predict_outcome', 'optimize_path',
  'classify_intent', 'extract_entities',
];

const SIM_BUFFER_GROWTH_RATE = 7; // simulated experiences added per learn step
const MAX_SIM_BUFFER_SIZE = 10000; // cap for simulated replay buffer

function _simulateNN() {
  _simStep += 1;
  const confidence = 0.55 + (Math.sin(_simStep * 0.3) * 0.3 + 0.3);
  const loss = Math.max(0.001, 0.08 - _simStep * 0.0002 + Math.random() * 0.01);
  const action = _simActions[_simStep % _simActions.length];

  const output = {
    ts: now(),
    action,
    confidence: Math.round(confidence * 1000) / 1000,
    loss: Math.round(loss * 10000) / 10000,
  };

  state.nn.learn_step = _simStep;
  state.nn.buffer_size = Math.min(_simStep * SIM_BUFFER_GROWTH_RATE, MAX_SIM_BUFFER_SIZE);
  state.nn.experiences = _simStep * SIM_BUFFER_GROWTH_RATE;
  state.nn.max_buffer_size = MAX_SIM_BUFFER_SIZE;
  state.nn.confidence = Math.round(confidence * 1000) / 1000;
  state.nn.last_loss = Math.round(loss * 10000) / 10000;
  state.nn.bg_running = true;
  state.nn.mode = 'SIMULATED';
  state.nn.available = true;
  state.nn.active = true;
  state.nn.recent_outputs = [output, ...state.nn.recent_outputs].slice(0, 5);
  state.nn.updated_at = now();
}

const _memKeys = ['industry', 'budget', 'pain_point', 'last_contact', 'status', 'priority'];

function _simulateMemory() {
  if (state.memory.nodes.length === 0) {
    state.memory.nodes = [
      { id: 'user:default', type: 'user', facts: 4, last_updated: now(), score: 1.0 },
      { id: 'lead:acme-corp', type: 'lead', facts: 6, last_updated: now(), score: 0.85 },
      { id: 'lead:techstart', type: 'lead', facts: 3, last_updated: now(), score: 0.72 },
      { id: 'customer:bigco', type: 'customer', facts: 8, last_updated: now(), score: 0.91 },
      { id: 'agent:orchestrator', type: 'agent', facts: 2, last_updated: now(), score: 0.95 },
    ];
  }

  const idx = _simStep % state.memory.nodes.length;
  const node = state.memory.nodes[idx];
  node.facts += Math.random() > 0.7 ? 1 : 0;
  node.last_updated = now();

  const key = _memKeys[_simStep % _memKeys.length];
  const update = {
    ts: now(),
    entity_id: node.id,
    action: 'update',
    key,
    value: `value_${_simStep}`,
  };

  state.memory.recent_updates = [update, ...state.memory.recent_updates].slice(0, 8);
  state.memory.total_entities = state.memory.nodes.length;
  state.memory.updated_at = now();
}

const _doctorIssues = [
  { area: 'Memory', severity: 'info', issue: 'Memory index has entities', suggestion: 'Continue building entity data' },
  { area: 'Neural Network', severity: 'info', issue: 'Running in offline mode', suggestion: 'Connect to an LLM for online learning' },
  { area: 'Agents', severity: 'warning', issue: 'Some agents in error state', suggestion: 'Check agent logs for errors' },
];

function _simulateDoctor() {
  const baseScore = 65 + Math.sin(_simStep * 0.1) * 15;
  const overall = Math.round(Math.max(10, Math.min(100, baseScore)));
  const grade = overall >= 80 ? 'A' : overall >= 60 ? 'B' : overall >= 40 ? 'C' : 'D';

  state.doctor.overall_score = overall;
  state.doctor.grade = grade;
  state.doctor.scores = {
    neural_network: Math.round(Math.min(100, overall + 15)),
    memory: Math.round(Math.min(100, overall + 5)),
    agents: Math.round(Math.max(0, overall - 10)),
    system: Math.round(Math.min(100, overall + 20)),
  };
  state.doctor.issues = _doctorIssues.slice(0, Math.max(1, Math.floor(Math.random() * 3)));
  state.doctor.strengths = overall > 50 ? ['Neural brain is active', 'Memory system online'] : [];
  state.doctor.last_run = now();
  state.doctor.available = true;
  state.doctor.updated_at = now();
}

// ── Python backend sync ───────────────────────────────────────────────────────

async function syncNNFromPython() {
  try {
    const data = await fetchJSON('/api/brain/status');
    if (data && data.available !== false) {
      state.nn.available = true;
      state.nn.active = true;
      state.nn.mode = data.mode || 'ONLINE';
      state.nn.learn_step = data.learn_step || 0;
      state.nn.buffer_size = data.buffer_size || 0;
      state.nn.max_buffer_size = data.replay_buffer_size || data.max_buffer_size || 10000;
      state.nn.experiences = data.experiences || 0;
      state.nn.last_loss = data.last_loss !== undefined ? data.last_loss : null;
      state.nn.confidence = data.avg_reward || 0;
      state.nn.device = data.device || 'cpu';
      state.nn.bg_running = data.bg_running || false;
      state.nn.updated_at = now();
      return true;
    }
  } catch (_) { /* offline */ }
  return false;
}

async function syncMemoryFromPython() {
  try {
    const data = await fetchJSON('/api/memory');
    if (data) {
      const entities = data.entities || data.clients || [];
      state.memory.total_entities = entities.length;
      state.memory.nodes = entities.slice(0, 20).map((e) => ({
        id: e.entity_id || e.id || String(e),
        type: e.entity_type || e.type || 'unknown',
        facts: e.fact_count !== undefined ? e.fact_count : (e.facts ? e.facts.length : 0),
        last_updated: e.updated_at || now(),
        score: e.score || 0,
      }));
      state.memory.updated_at = now();
      return true;
    }
  } catch (_) { /* offline */ }
  return false;
}

async function syncDoctorFromPython() {
  try {
    const data = await fetchJSON('/api/health-check/latest');
    if (data && data.grade) {
      state.doctor.available = true;
      state.doctor.grade = data.grade;
      state.doctor.overall_score = data.overall_score || 0;
      state.doctor.scores = data.scores || {};
      state.doctor.issues = data.issues || [];
      state.doctor.strengths = data.strengths || [];
      state.doctor.last_run = data.generated_at || now();
      state.doctor.updated_at = now();
      return true;
    }
  } catch (_) { /* offline */ }
  return false;
}

// ── Polling loop ──────────────────────────────────────────────────────────────

let _pollInterval = null;

async function _pollCycle() {
  const nnOk = await syncNNFromPython();
  const memOk = await syncMemoryFromPython();
  const drOk = await syncDoctorFromPython();

  if (!nnOk) _simulateNN();
  if (!memOk) _simulateMemory();
  if (!drOk) _simulateDoctor();
}

function startPolling(intervalMs = 5000) {
  _pollCycle().catch(() => {
    _simulateNN();
    _simulateMemory();
    _simulateDoctor();
  });
  _pollInterval = setInterval(() => {
    _pollCycle().catch(() => {});
  }, intervalMs);
}

function stopPolling() {
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

function getNNStatus() {
  return { ...state.nn };
}

function getMemoryTree() {
  return { ...state.memory };
}

function getDoctorStatus() {
  return { ...state.doctor };
}

module.exports = {
  startPolling,
  stopPolling,
  getNNStatus,
  getMemoryTree,
  getDoctorStatus,
};
