'use strict';

/**
 * Learning Ladder Builder — Node.js state management module.
 *
 * Mirrors the Python runtime/core/learning_ladder_builder.py module,
 * providing the same functionality for the Node.js backend API layer.
 *
 * State is persisted to .data/learning_ladder.json using atomic writes.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_DIR = path.resolve(__dirname, '../../.data');
const STATE_FILE = path.join(DATA_DIR, 'learning_ladder.json');

const MAX_TOPICS = 200;
const MAX_HISTORY_PER_LEVEL = 50;

const LEVEL_NAMES = {
  1: 'Beginner',
  2: 'Basic',
  3: 'Intermediate',
  4: 'Advanced',
  5: 'Professional',
};

const LEVEL_TEMPLATES = {
  1: {
    name: 'Beginner',
    description:
      'Understands the fundamental concepts of {topic}. Can identify basic terminology and follow simple examples with guidance.',
    skills: [
      'Define core terms and concepts of {topic}',
      'Identify the primary components and elements in {topic}',
      'Follow a step-by-step tutorial to produce a basic {topic} output',
    ],
    milestone:
      'Complete a beginner-level guided exercise: build or produce a minimal working example of {topic} from a tutorial, then explain what each step does.',
  },
  2: {
    name: 'Basic',
    description:
      "Can independently perform basic {topic} tasks without constant guidance. Understands the 'why' behind foundational concepts.",
    skills: [
      'Independently set up and configure a {topic} environment or workflow',
      'Apply core {topic} techniques to simple, well-defined problems',
      'Debug common beginner-level {topic} errors',
      'Read and understand basic {topic} documentation',
    ],
    milestone:
      'Build a simple standalone {topic} project from scratch (no tutorial) that solves a basic real-world problem. Include error handling and basic documentation.',
  },
  3: {
    name: 'Intermediate',
    description:
      'Solves moderately complex {topic} problems independently. Understands trade-offs and begins to apply best practices.',
    skills: [
      'Design and implement a multi-component {topic} system',
      'Apply best practices and design patterns relevant to {topic}',
      'Optimise {topic} solutions for performance or maintainability',
      'Integrate {topic} with other tools, systems, or frameworks',
      'Test and validate {topic} implementations',
    ],
    milestone:
      'Design, implement, and test a complete intermediate-level {topic} application that integrates with at least one external tool or data source. Document the architecture and key decisions.',
  },
  4: {
    name: 'Advanced',
    description:
      'Handles complex, production-grade {topic} challenges. Can architect systems, mentor others, and make informed technical decisions.',
    skills: [
      'Architect scalable and maintainable {topic} systems',
      'Identify and resolve advanced performance or security issues in {topic}',
      'Evaluate and select appropriate {topic} tools/frameworks for specific contexts',
      'Contribute to or extend {topic} ecosystems (libraries, plugins, or tools)',
    ],
    milestone:
      'Architect and deploy a production-ready {topic} solution that handles real-world constraints (scale, security, reliability). Write a technical design document explaining key decisions and trade-offs.',
  },
  5: {
    name: 'Professional',
    description:
      'Expert-level mastery of {topic}. Can innovate, define standards, lead teams, and solve novel problems autonomously in {topic}.',
    skills: [
      'Define and enforce {topic} standards and best practices across a team or organisation',
      'Innovate and solve novel, unseen problems in {topic} without reference material',
      "Mentor and grow others' {topic} capabilities",
      'Contribute original knowledge to the {topic} community (publications, open-source, talks)',
      'Evaluate and drive adoption of emerging {topic} technologies or methodologies',
    ],
    milestone:
      'Lead a complex {topic} initiative end-to-end: define the problem, architect the solution, execute with a team, deliver measurable outcomes, and document learnings for future reference. Present results to stakeholders.',
  },
};

// ── Utilities ─────────────────────────────────────────────────────────────────

function ts() {
  return new Date().toISOString();
}

function topicKey(topic) {
  return (topic || '').trim().toLowerCase();
}

function ladderId(topic) {
  return crypto.createHash('sha1').update(topic.trim()).digest('hex').slice(0, 12);
}

function renderTemplate(template, topic) {
  return template.replace(/\{topic\}/g, topic);
}

function buildLevel(topic, levelNum) {
  const tmpl = LEVEL_TEMPLATES[levelNum];
  return {
    level: levelNum,
    name: tmpl.name,
    description: renderTemplate(tmpl.description, topic),
    skills: tmpl.skills.map((s) => renderTemplate(s, topic)),
    milestone: renderTemplate(tmpl.milestone, topic),
  };
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
    ladders: {},
    progress: {},
    metrics: {
      total_ladders_built: 0,
      total_levels_completed: 0,
      total_levels_failed: 0,
      total_levels_attempted: 0,
    },
    updated_at: null,
  };
}

function loadState() {
  const saved = readJsonSafe(STATE_FILE);
  if (saved && typeof saved === 'object') {
    const merged = defaultState();
    Object.assign(merged, saved);
    return merged;
  }
  return defaultState();
}

function getState() {
  if (!_state) _state = loadState();
  return _state;
}

function saveState() {
  const s = getState();
  s.updated_at = ts();
  writeJsonSafe(STATE_FILE, s);
}

// ── Next executable level ─────────────────────────────────────────────────────

function nextExecutableLevel(topicKey_) {
  const progress = getState().progress[topicKey_] || {};
  for (let n = 1; n <= 5; n++) {
    const rec = progress[String(n)] || {};
    if (!rec.learned) {
      if (n === 1 || (progress[String(n - 1)] || {}).learned) return n;
      return null; // blocked
    }
  }
  return null; // all complete
}

// ── Adaptation check ─────────────────────────────────────────────────────────

function checkAdaptation(level, attempts) {
  const failures = attempts.filter((a) => !a.learned).length;
  const successes = attempts.filter((a) => a.learned);

  if (failures >= 3) {
    return {
      action: 'break_into_sub_levels',
      reason: `Level ${level} failed ${failures} times. Breaking into sub-levels for simplified progression.`,
    };
  }
  if (successes.length === 1 && attempts.length === 1 && (successes[0].score || 0) >= 0.9) {
    return {
      action: 'accelerate_progression',
      reason: `Level ${level} completed on first attempt with high score. Accelerating to next level.`,
    };
  }
  return { action: 'continue', reason: 'Normal progression.' };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Build (or retrieve) a 5-level learning ladder for a topic.
 * @param {string} topic
 * @returns {object} ladder JSON
 */
function buildLadder(topic) {
  const raw = (topic || '').trim();
  if (!raw) throw new Error('topic must be a non-empty string');

  const key = topicKey(raw);
  const state = getState();

  if (state.ladders[key]) return { ...state.ladders[key] };

  // Evict oldest if at max capacity
  const keys = Object.keys(state.ladders);
  if (keys.length >= MAX_TOPICS) {
    delete state.ladders[keys[0]];
  }

  const levels = [1, 2, 3, 4, 5].map((n) => buildLevel(raw, n));
  const ladder = {
    id: ladderId(raw),
    topic: raw,
    levels,
    built_at: ts(),
  };

  state.ladders[key] = ladder;
  state.metrics.total_ladders_built += 1;
  saveState();

  return { ...ladder };
}

/**
 * Record a level completion attempt.
 * Anti-illusion: success=false means NOT LEARNED.
 */
function recordLevelCompletion({ topic, level, success, milestoneOutput = '', score = 0, notes = '' }) {
  const raw = (topic || '').trim();
  if (!raw) throw new Error('topic must be a non-empty string');
  const lvl = parseInt(level, 10);
  if (lvl < 1 || lvl > 5) throw new Error('level must be 1–5');

  const key = topicKey(raw);
  const clampedScore = Math.max(0, Math.min(1, parseFloat(score) || 0));
  const learned = success && clampedScore >= 0.5;

  const state = getState();
  if (!state.progress[key]) state.progress[key] = {};
  const progress = state.progress[key];
  const lvlStr = String(lvl);

  if (!progress[lvlStr]) {
    progress[lvlStr] = {
      level: lvl,
      name: LEVEL_NAMES[lvl],
      status: 'not_started',
      attempts: [],
      completed_at: null,
      learned: false,
      best_score: 0,
      skill_gaps: [],
    };
  }

  const rec = progress[lvlStr];
  const attempt = {
    ts: ts(),
    success,
    learned,
    score: Math.round(clampedScore * 10000) / 10000,
    milestone_output: (milestoneOutput || '').slice(0, 500),
    notes: (notes || '').slice(0, 300),
  };

  rec.attempts.push(attempt);
  if (rec.attempts.length > MAX_HISTORY_PER_LEVEL) {
    rec.attempts = rec.attempts.slice(-MAX_HISTORY_PER_LEVEL);
  }

  if (learned) {
    rec.status = 'completed';
    rec.learned = true;
    rec.completed_at = ts();
    rec.best_score = Math.max(rec.best_score, clampedScore);
    state.metrics.total_levels_completed += 1;
  } else {
    if (rec.status !== 'completed') {
      rec.status = 'failed';
      rec.learned = false;
    }
    if (notes && !rec.skill_gaps.includes(notes)) {
      rec.skill_gaps.push(notes.slice(0, 200));
      if (rec.skill_gaps.length > 10) rec.skill_gaps = rec.skill_gaps.slice(-10);
    }
    state.metrics.total_levels_failed += 1;
  }

  state.metrics.total_levels_attempted += 1;
  saveState();

  return {
    topic: raw,
    level: lvl,
    learned,
    status: rec.status,
    attempts_count: rec.attempts.length,
    best_score: rec.best_score,
    next_level: nextExecutableLevel(key),
    adaptation: checkAdaptation(lvl, rec.attempts),
  };
}

/**
 * Return full progress for a topic.
 */
function getProgress(topic) {
  const key = topicKey(topic);
  const state = getState();
  const ladder = state.ladders[key] || null;
  const progress = state.progress[key] || {};
  const next = nextExecutableLevel(key);
  const allDone = [1, 2, 3, 4, 5].every((n) => (progress[String(n)] || {}).learned);
  return {
    topic: (topic || '').trim(),
    ladder,
    progress,
    next_level: next,
    completed: allDone,
  };
}

/**
 * Return summaries of all tracked topics.
 */
function getAllTopics() {
  const state = getState();
  return Object.entries(state.ladders)
    .map(([key, ladder]) => {
      const progress = state.progress[key] || {};
      const completed = [1, 2, 3, 4, 5].filter((n) => (progress[String(n)] || {}).learned).length;
      return {
        topic: ladder.topic || key,
        id: ladder.id || key,
        built_at: ladder.built_at,
        levels_completed: completed,
        levels_total: 5,
        completed: completed === 5,
      };
    })
    .sort((a, b) => (b.built_at || '').localeCompare(a.built_at || ''));
}

/**
 * Return global learning ladder metrics.
 */
function getMetrics() {
  const state = getState();
  return {
    ...state.metrics,
    total_topics: Object.keys(state.ladders).length,
    ts: ts(),
  };
}

module.exports = {
  buildLadder,
  recordLevelCompletion,
  getProgress,
  getAllTopics,
  getMetrics,
};
