'use strict'

/**
 * forge_context_engine.js — Phase 9 Context Packet Builder
 *
 * Assembles a context packet for a given run stage by pulling together:
 * - Relevant memory graph nodes (most-used files, recent run summaries)
 * - Memory facts for the project
 * - Repo index signals (stack, high-risk files, routes)
 * - Recent session history
 *
 * Returns a compact context_packet that the planner and other agents can
 * inject into their prompts. ADVISORY ONLY — never blocks execution.
 */

const crypto = require('crypto')

function nowIso() { return new Date().toISOString() }

function _safeCall(fn, fallback) {
  try { return fn() }
  catch { return fallback }
}

/**
 * Score a memory node for relevance to a goal string.
 * Simple overlap of ≥4-char words.
 */
function _relevanceScore(nodeLabel, goal) {
  if (!nodeLabel || !goal) return 0
  const wordsGoal = new Set((goal.toLowerCase().match(/\b\w{4,}\b/g) || []))
  const wordsNode = (nodeLabel.toLowerCase().match(/\b\w{4,}\b/g) || [])
  if (!wordsGoal.size) return 0
  const hits = wordsNode.filter(w => wordsGoal.has(w)).length
  return hits / wordsGoal.size
}

/**
 * Build a context packet for the given stage/goal.
 *
 * forgeRunStore — ForgeStore instance (may be SQLite-backed or JSON fallback)
 * project — project object { id, name, package_type, ... }
 * run — current run object { id, goal, context_pack, ... }
 * stage — 'planner' | 'coder' | 'tester' | 'security' | 'reviewer'
 * goal — string
 * opts — { repoIndex? }
 *
 * Returns: {
 *   packet_id, project_id, run_id, stage, goal,
 *   selected_nodes, memory_facts, repo_signals,
 *   created_at
 * }
 */
function buildContextPacket(forgeRunStore, project, run, stage, goal, opts = {}) {
  const { repoIndex } = opts
  const packetId = `ctx-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`

  // ── Memory graph nodes ────────────────────────────────────────────────────
  const allNodes = _safeCall(() =>
    typeof forgeRunStore.getGraphNodes === 'function'
      ? forgeRunStore.getGraphNodes(project.id, { limit: 100 })
      : [],
    []
  )

  // Score each node and pick the top 12
  const scoredNodes = allNodes.map(n => ({
    node: n,
    score: (n.usage_count || 0) * 0.3 + _relevanceScore(n.label, goal) * 0.7 + (n.confidence || 0) * 0.1,
  }))
  scoredNodes.sort((a, b) => b.score - a.score)
  const selectedNodes = scoredNodes.slice(0, 12).map(({ node, score }) => ({
    node_id: node.node_id,
    node_type: node.node_type,
    label: node.label,
    confidence: node.confidence,
    usage_count: node.usage_count || 0,
    relevance_score: Math.round(score * 100) / 100,
    metadata: node.metadata || {},
  }))

  // ── Memory facts ──────────────────────────────────────────────────────────
  const allFacts = _safeCall(() =>
    typeof forgeRunStore.getMemoryFacts === 'function'
      ? forgeRunStore.getMemoryFacts(project.id)
      : [],
    []
  )
  // Pick facts relevant to goal or stage, cap at 8
  const stageFacts = allFacts
    .filter(f => {
      if (!f.fact) return false
      if (_relevanceScore(f.fact, goal) > 0.1) return true
      if (stage === 'security' && /auth|secret|security|credential/i.test(f.fact)) return true
      if (stage === 'tester' && /test|verify|command/i.test(f.fact)) return true
      return false
    })
    .slice(0, 8)
    .map(f => ({ memory_id: f.memory_id, category: f.category, fact: f.fact, confidence: f.confidence }))

  // ── Repo signals ──────────────────────────────────────────────────────────
  const repoSignals = {}
  if (repoIndex) {
    repoSignals.stack = repoIndex.stack || {}
    repoSignals.high_risk_files = (repoIndex.high_risk_files || []).slice(0, 8)
    repoSignals.entry_points = (repoIndex.entry_points || []).slice(0, 5)
    repoSignals.test_files = (repoIndex.test_files || []).slice(0, 5)
    repoSignals.route_count = (repoIndex.route_map || []).length
    repoSignals.dependency_count = (repoIndex.dependencies?.external || []).length
    // Top 10 largest files (most likely impacted)
    repoSignals.top_files = Object.entries(repoIndex.file_stats || {})
      .sort((a, b) => b[1].size_bytes - a[1].size_bytes)
      .slice(0, 10)
      .map(([p]) => p)
  }

  // ── Persist context packet ────────────────────────────────────────────────
  const packet = {
    packet_id: packetId,
    project_id: project.id,
    run_id: run?.id || null,
    stage,
    goal: (goal || '').slice(0, 300),
    selected_nodes: selectedNodes,
    memory_facts: stageFacts,
    repo_signals: repoSignals,
    created_at: nowIso(),
  }

  _safeCall(() => {
    if (typeof forgeRunStore.upsertContextPacket === 'function') {
      forgeRunStore.upsertContextPacket(packet)
    }
  }, null)

  return packet
}

module.exports = {
  buildContextPacket,
}
