'use strict';

/**
 * Agent Learning Profile — Node.js module.
 *
 * Couples agents to learning ladders with a 5-stage grade system:
 *   Ungraded → Beginner → Basic → Mature → Advanced → Pro
 *
 * Mirrors runtime/core/agent_learning_profile.py for the API layer.
 * State is persisted to .data/agent_learning_profiles.json.
 */

const fs = require('fs');
const path = require('path');
const learningLadder = require('./learning_ladder');

const DATA_DIR = path.resolve(__dirname, '../../.data');
const STATE_FILE = path.join(DATA_DIR, 'agent_learning_profiles.json');

const MAX_AGENTS = 500;

// ── Grade system ──────────────────────────────────────────────────────────────

const GRADE_MAP = {
  0: 'Ungraded',
  1: 'Beginner',
  2: 'Basic',
  3: 'Mature',
  4: 'Advanced',
  5: 'Pro',
};

const GRADE_COLORS = {
  Ungraded: 'var(--text-muted)',
  Beginner: '#6ea8fe',
  Basic: '#52d9b2',
  Mature: '#f7c948',
  Advanced: '#e07b39',
  Pro: 'var(--gold)',
};

// ── Utilities ─────────────────────────────────────────────────────────────────

function ts() {
  return new Date().toISOString();
}

function agentKey(agentId) {
  const key = (agentId || '').trim().toLowerCase();
  if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
    throw new Error('Invalid agent ID');
  }
  return key;
}

function computeGrade(levelCompleted) {
  const lvl = Math.max(0, Math.min(5, parseInt(levelCompleted, 10) || 0));
  return GRADE_MAP[lvl] || 'Ungraded';
}

function ensureDataDir() {
  try {
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  } catch (_) {
    // best-effort
  }
}

function writeJsonSafe(filePath, data) {
  try {
    ensureDataDir();
    const tmp = filePath + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
    fs.renameSync(tmp, filePath);
    return true;
  } catch (_) {
    return false;
  }
}

function readJsonSafe(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return null;
  }
}

// ── State ─────────────────────────────────────────────────────────────────────

let _state = null;

function defaultState() {
  return {
    assignments: {},
    grades: {},
    metrics: {
      total_agents_assigned: 0,
      total_levels_completed: 0,
      total_levels_failed: 0,
    },
    updated_at: null,
  };
}

function getState() {
  if (!_state) {
    const saved = readJsonSafe(STATE_FILE);
    _state = saved && typeof saved === 'object' ? Object.assign(defaultState(), saved) : defaultState();
  }
  return _state;
}

function saveState() {
  const s = getState();
  s.updated_at = ts();
  writeJsonSafe(STATE_FILE, s);
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Assign a learning ladder to an agent.
 */
function assignLadder(agentId, topic) {
  const rawAgent = (agentId || '').trim();
  const rawTopic = (topic || '').trim();
  if (!rawAgent) throw new Error('agentId must be a non-empty string');
  if (!rawTopic) throw new Error('topic must be a non-empty string');

  const key = agentKey(rawAgent);
  const state = getState();

  // Build (or retrieve) the ladder
  const ladder = learningLadder.buildLadder(rawTopic);

  // Evict oldest if at capacity
  const assignKeys = Object.keys(state.assignments);
  if (assignKeys.length >= MAX_AGENTS && !Object.prototype.hasOwnProperty.call(state.assignments, key)) {
    delete state.assignments[assignKeys[0]];
  }

  state.assignments[key] = {
    agent_id: rawAgent,
    topic: rawTopic,
    ladder_id: ladder.id,
    assigned_at: ts(),
  };

  // Initialise grade record if absent
  if (!Object.prototype.hasOwnProperty.call(state.grades, key)) {
    state.grades[key] = {
      agent_id: rawAgent,
      topic: rawTopic,
      grade: 'Ungraded',
      grade_level: 0,
      levels_completed: 0,
      last_updated: ts(),
    };
  } else {
    state.grades[key].topic = rawTopic;
  }

  state.metrics.total_agents_assigned += 1;
  saveState();

  return {
    agent_id: rawAgent,
    topic: rawTopic,
    ladder_id: ladder.id,
    grade: state.grades[key].grade,
    assigned_at: state.assignments[key].assigned_at,
  };
}

/**
 * Record a level completion attempt for an agent.
 * Enforces anti-illusion: success + score ≥ 0.5 required to advance grade.
 */
function advanceAgent({ agentId, level, success, score = 0, milestoneOutput = '', notes = '' }) {
  const rawAgent = (agentId || '').trim();
  if (!rawAgent) throw new Error('agentId must be a non-empty string');
  const lvl = parseInt(level, 10);
  if (lvl < 1 || lvl > 5) throw new Error('level must be 1–5');

  const key = agentKey(rawAgent);
  const state = getState();

  const assignment = state.assignments[key];
  if (!assignment) {
    throw new Error(`Agent '${rawAgent}' has no learning ladder assigned. Call assignLadder() first.`);
  }

  const topic = assignment.topic;

  // Delegate to learning_ladder module
  const result = learningLadder.recordLevelCompletion({
    topic,
    level: lvl,
    success,
    milestoneOutput,
    score,
    notes,
  });

  if (result.learned) {
    // Update grade record
    const gradeRec = state.grades[key] || {
      agent_id: rawAgent,
      topic,
      grade: 'Ungraded',
      grade_level: 0,
      levels_completed: 0,
      last_updated: ts(),
    };

    if (lvl > (gradeRec.grade_level || 0)) {
      gradeRec.grade_level = lvl;
      gradeRec.grade = computeGrade(lvl);
    }
    gradeRec.levels_completed = Math.max(gradeRec.levels_completed || 0, lvl);
    gradeRec.last_updated = ts();
    state.grades[key] = gradeRec;
    state.metrics.total_levels_completed += 1;
  } else {
    state.metrics.total_levels_failed += 1;
  }

  saveState();

  const gradeInfo = getAgentGrade(rawAgent);

  return {
    agent_id: rawAgent,
    topic,
    level: lvl,
    learned: result.learned,
    status: result.status,
    grade: gradeInfo.grade,
    grade_level: gradeInfo.grade_level,
    next_level: result.next_level,
    adaptation: result.adaptation,
    best_score: result.best_score,
  };
}

/**
 * Get the current grade for an agent.
 */
function getAgentGrade(agentId) {
  const key = agentKey((agentId || '').trim());
  const state = getState();
  const rec = state.grades[key];
  if (!rec) {
    return {
      agent_id: (agentId || '').trim(),
      topic: null,
      grade: 'Ungraded',
      grade_level: 0,
      levels_completed: 0,
      last_updated: null,
    };
  }
  return { ...rec };
}

/**
 * Get the full learning profile for an agent.
 */
function getAgentProfile(agentId) {
  const key = agentKey((agentId || '').trim());
  const state = getState();
  const assignment = state.assignments[key] || null;
  const gradeRec = state.grades[key] || null;

  if (!assignment) {
    return {
      agent_id: (agentId || '').trim(),
      assignment: null,
      grade: 'Ungraded',
      grade_level: 0,
      ladder_progress: null,
      next_level: null,
    };
  }

  const ladderProgress = learningLadder.getProgress(assignment.topic);

  return {
    agent_id: assignment.agent_id,
    assignment,
    grade: gradeRec ? gradeRec.grade : 'Ungraded',
    grade_level: gradeRec ? gradeRec.grade_level : 0,
    ladder_progress: ladderProgress,
    next_level: ladderProgress.next_level,
  };
}

/**
 * Get grade summaries for all agents.
 */
function getAllProfiles() {
  const state = getState();
  return Object.entries(state.assignments)
    .map(([key, assignment]) => {
      const gradeRec = state.grades[key] || {};
      return {
        agent_id: assignment.agent_id || key,
        topic: assignment.topic || '',
        ladder_id: assignment.ladder_id || '',
        grade: gradeRec.grade || 'Ungraded',
        grade_level: gradeRec.grade_level || 0,
        levels_completed: gradeRec.levels_completed || 0,
        levels_total: 5,
        last_updated: gradeRec.last_updated || null,
      };
    })
    .sort((a, b) => (b.grade_level - a.grade_level) || (b.last_updated || '').localeCompare(a.last_updated || ''));
}

/**
 * Get global metrics.
 */
function getMetrics() {
  const state = getState();
  const dist = {};
  Object.values(GRADE_MAP).forEach((g) => { dist[g] = 0; });
  Object.values(state.grades).forEach((rec) => {
    const g = rec.grade || 'Ungraded';
    dist[g] = (dist[g] || 0) + 1;
  });
  return {
    ...state.metrics,
    total_agents_assigned: Object.keys(state.assignments).length,
    grade_distribution: dist,
    ts: ts(),
  };
}

module.exports = {
  assignLadder,
  advanceAgent,
  getAgentGrade,
  getAgentProfile,
  getAllProfiles,
  getMetrics,
  GRADE_MAP,
  GRADE_COLORS,
};
