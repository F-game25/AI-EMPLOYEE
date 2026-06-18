'use strict';
// Canonical state-directory resolver for Node — mirrors runtime/core/state_paths.py.
// Single source of truth so no module reaches into the repo-local ./state, which
// split runtime state across two trees. See docs/SYSTEM_COHERENCE_PLAN.md (C0).
const path = require('path');
const os = require('os');

function stateDir() {
  const explicit = process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR;
  if (explicit) return path.resolve(explicit);
  const home = process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee');
  return path.resolve(home, 'state');
}

const STATE_DIR = stateDir();
const ARTIFACTS_DIR = path.join(STATE_DIR, 'artifacts');
const statePath = (...parts) => path.join(STATE_DIR, ...parts);

module.exports = { stateDir, STATE_DIR, ARTIFACTS_DIR, statePath };
