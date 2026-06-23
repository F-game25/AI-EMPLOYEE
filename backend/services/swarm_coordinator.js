'use strict'

/**
 * Swarm coordinator (Phase 8) — decides whether a Forge codegen goal should run
 * through the parallel swarm (core/swarm_engine.py via callSwarm) or a single
 * agent. Pure decision logic; the caller performs the actual execution.
 *
 * Closes GAP-4 ("swarm exists but Forge never uses it") without forcing every run
 * through N agents: swarm is opt-in / heuristic, gated by the swarm enable flag
 * and the token budget, with single-agent as the safe default.
 *
 * Precedence: disabled → over-budget → explicit opt-out → explicit opt-in →
 * heavy-goal heuristic → simple default.
 */

const _HEAVY_RE = /\b(refactor|refactoring|migrat\w*|rewrite|re-?architect|architecture|redesign|across|multiple files|whole|entire|end-to-end|optimi[sz]e|overhaul)\b/i

function decide({
  goal = '',
  useSwarm = undefined,      // true = force swarm, false = force single, undefined = auto
  swarmEnabled = false,
  taskType = 'code',
  agentCount = 5,
  budgetOk = true,
} = {}) {
  const single = (reason) => ({ mode: 'single', n_agents: 1, task_type: taskType, reason })
  const swarm = (reason) => ({ mode: 'swarm', n_agents: Math.max(2, Math.round(agentCount) || 2), task_type: taskType, reason })

  if (!swarmEnabled) return single('swarm disabled')
  if (!budgetOk) return single('over token budget — single agent')
  if (useSwarm === false) return single('explicit single-agent request')
  if (useSwarm === true) return swarm('explicitly requested')

  const g = String(goal || '')
  const heavy = g.length > 240
    || _HEAVY_RE.test(g)
    || (g.match(/\band\b/gi) || []).length >= 3
  return heavy ? swarm('heavy/complex goal heuristic') : single('simple goal — single agent')
}

module.exports = { decide }
