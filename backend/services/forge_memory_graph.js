'use strict'

/**
 * forge_memory_graph.js — Phase 9 Memory Graph
 *
 * Manages the project-scoped memory graph: creates nodes from completed runs,
 * creates/reinforces edges between related nodes, detects contradictions,
 * and provides neighborhood traversal.
 *
 * All writes go through ForgeStore (SQLite graph tables).
 * This module is pure computation + ForgeStore delegation — no own state.
 */

const crypto = require('crypto')

function nowIso() { return new Date().toISOString() }

// ── Node types ────────────────────────────────────────────────────────────────
const NODE_TYPE_RUN    = 'run'
const NODE_TYPE_FILE   = 'file'
const NODE_TYPE_GOAL   = 'goal'
const NODE_TYPE_LESSON = 'lesson'

// ── Edge relationship types ───────────────────────────────────────────────────
const EDGE_MODIFIED    = 'modified'
const EDGE_SIMILAR_TO  = 'similar_to'
const EDGE_DERIVED_FROM = 'derived_from'
const EDGE_CONTRADICTS = 'contradicts'

// ── Helpers ───────────────────────────────────────────────────────────────────

function _goalSimilarity(a, b) {
  if (!a || !b) return 0
  const wordsA = new Set(a.toLowerCase().match(/\b\w{4,}\b/g) || [])
  const wordsB = new Set(b.toLowerCase().match(/\b\w{4,}\b/g) || [])
  const intersection = [...wordsA].filter(w => wordsB.has(w)).length
  const union = new Set([...wordsA, ...wordsB]).size
  return union > 0 ? intersection / union : 0
}

function _safeGraphCall(fn, fallback) {
  try { return fn() }
  catch { return fallback }
}

// ── Core API ──────────────────────────────────────────────────────────────────

/**
 * Link a completed run into the memory graph.
 * Creates a run node + file nodes + edges between them.
 * All best-effort — caller wraps in try/catch.
 */
function linkRunToMemoryGraph(forgeRunStore, projectId, runId) {
  const run = _safeGraphCall(() => forgeRunStore.findRun(runId), null)
  if (!run) return

  // Ensure upsertGraphNode exists (SQLite tables may not be initialised)
  if (typeof forgeRunStore.upsertGraphNode !== 'function') return

  const transcript = run.final_report?.transcript || []
  const success = run.final_report?.success === true || run.status === 'verified'

  // Run node
  const runNodeId = `node-run-${runId}`
  forgeRunStore.upsertGraphNode({
    node_id: runNodeId,
    project_id: projectId,
    node_type: NODE_TYPE_RUN,
    label: (run.goal || 'run').slice(0, 200),
    metadata: {
      run_id: runId,
      success,
      status: run.status,
      iterations: transcript.length,
    },
    confidence: success ? 0.9 : 0.3,
    usage_count: 1,
    last_used_at: nowIso(),
    created_at: nowIso(),
    updated_at: nowIso(),
  })

  // File nodes + edges
  const filesChanged = [...new Set(
    transcript.flatMap(t => (t.files_written || []).filter(f => f.ok).map(f => f.path))
  )]
  for (const fp of filesChanged.slice(0, 10)) {
    const fileNodeId = `node-file-${projectId}-${fp.replace(/[^a-z0-9]/gi, '-')}`
    _safeGraphCall(() => {
      forgeRunStore.upsertGraphNode({
        node_id: fileNodeId,
        project_id: projectId,
        node_type: NODE_TYPE_FILE,
        label: fp,
        metadata: { file_path: fp, last_run_id: runId, last_modified_success: success },
        confidence: 0.8,
        usage_count: 1,
        last_used_at: nowIso(),
        created_at: nowIso(),
        updated_at: nowIso(),
      })
    }, null)
    _safeGraphCall(() => {
      forgeRunStore.upsertGraphEdge({
        edge_id: `edge-${runNodeId}-${fileNodeId}`,
        project_id: projectId,
        from_node_id: runNodeId,
        to_node_id: fileNodeId,
        relationship: EDGE_MODIFIED,
        weight: success ? 0.9 : 0.3,
        metadata: { success, run_id: runId },
        created_at: nowIso(),
        updated_at: nowIso(),
      })
    }, null)
  }

  // Cross-run similarity edges (link to recent runs with similar goals)
  const recentRuns = _safeGraphCall(() =>
    (forgeRunStore.getGraphNodes ? forgeRunStore.getGraphNodes(projectId, { node_type: NODE_TYPE_RUN, limit: 20 }) : []),
    []
  )
  for (const other of recentRuns) {
    if (other.node_id === runNodeId) continue
    const sim = _goalSimilarity(run.goal, other.label)
    if (sim >= 0.3) {
      _safeGraphCall(() => {
        forgeRunStore.upsertGraphEdge({
          edge_id: `edge-sim-${runNodeId}-${other.node_id}`,
          project_id: projectId,
          from_node_id: runNodeId,
          to_node_id: other.node_id,
          relationship: EDGE_SIMILAR_TO,
          weight: sim,
          metadata: { similarity: sim },
          created_at: nowIso(),
          updated_at: nowIso(),
        })
      }, null)
    }
  }
}

/**
 * Consolidate the memory graph: reinforce frequently co-occurring nodes,
 * detect contradictions, prune weak edges.
 *
 * Returns: { nodes_processed, edges_reinforced, contradictions_found, trigger_type }
 */
function consolidateMemoryGraph(forgeRunStore, projectId, opts = {}) {
  const { trigger_type = 'manual' } = opts
  const report = { nodes_processed: 0, edges_reinforced: 0, contradictions_found: 0, trigger_type, consolidated_at: nowIso() }

  if (typeof forgeRunStore.getGraphNodes !== 'function') return report

  const nodes = _safeGraphCall(() => forgeRunStore.getGraphNodes(projectId, { limit: 300 }), [])
  report.nodes_processed = nodes.length

  // Reinforce high-traffic file nodes (usage_count > 2)
  for (const node of nodes.filter(n => n.node_type === NODE_TYPE_FILE && (n.usage_count || 0) >= 2)) {
    _safeGraphCall(() => forgeRunStore.touchGraphNode(node.node_id), null)
    report.edges_reinforced++
  }

  // Detect contradictions: same file modified in both successful and failed runs
  const runNodes = nodes.filter(n => n.node_type === NODE_TYPE_RUN)
  const successFiles = new Set()
  const failFiles = new Set()
  for (const rn of runNodes) {
    const meta = rn.metadata || {}
    const edges = _safeGraphCall(() =>
      forgeRunStore.getGraphEdges ? forgeRunStore.getGraphEdges(projectId, { from_node_id: rn.node_id }) : [],
      []
    )
    for (const e of edges.filter(e => e.relationship === EDGE_MODIFIED)) {
      if (meta.success) successFiles.add(e.to_node_id)
      else failFiles.add(e.to_node_id)
    }
  }
  for (const nodeId of successFiles) {
    if (failFiles.has(nodeId)) report.contradictions_found++
  }

  return report
}

/**
 * Get a high-level summary of the memory graph for a project.
 * Returns: { node_count, edge_count, run_nodes, file_nodes, top_files }
 */
function getGraphSummary(forgeRunStore, projectId) {
  if (typeof forgeRunStore.getGraphNodes !== 'function') {
    return { node_count: 0, edge_count: 0, run_nodes: 0, file_nodes: 0, top_files: [] }
  }
  const nodes = _safeGraphCall(() => forgeRunStore.getGraphNodes(projectId, { limit: 500 }), [])
  const runNodes = nodes.filter(n => n.node_type === NODE_TYPE_RUN).length
  const fileNodes = nodes.filter(n => n.node_type === NODE_TYPE_FILE)
  const topFiles = fileNodes
    .sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))
    .slice(0, 10)
    .map(n => ({ label: n.label, usage_count: n.usage_count || 0, confidence: n.confidence }))
  const edges = _safeGraphCall(() =>
    forgeRunStore.getGraphEdges ? forgeRunStore.getGraphEdges(projectId, {}) : [],
    []
  )
  return {
    node_count: nodes.length,
    edge_count: edges.length,
    run_nodes: runNodes,
    file_nodes: fileNodes.length,
    top_files: topFiles,
  }
}

/**
 * Return the neighborhood around a node up to `depth` hops.
 * Returns: { center_node, neighbors: [{ node, distance, path }] }
 */
function getGraphNeighborhood(forgeRunStore, projectId, nodeId, depth = 1) {
  if (typeof forgeRunStore.getGraphEdges !== 'function' || typeof forgeRunStore.findGraphNode !== 'function') {
    return { center_node: null, neighbors: [] }
  }
  const center = _safeGraphCall(() => forgeRunStore.findGraphNode(nodeId), null)
  if (!center) return { center_node: null, neighbors: [] }

  const visited = new Set([nodeId])
  const neighbors = []
  const queue = [{ nodeId, distance: 0, path: [nodeId] }]

  while (queue.length > 0) {
    const { nodeId: curId, distance, path } = queue.shift()
    if (distance >= depth) continue
    const edges = _safeGraphCall(() => forgeRunStore.getGraphEdges(projectId, { from_node_id: curId }), [])
    for (const edge of edges) {
      const nextId = edge.to_node_id
      if (visited.has(nextId)) continue
      visited.add(nextId)
      const nextNode = _safeGraphCall(() => forgeRunStore.findGraphNode(nextId), null)
      if (nextNode) {
        neighbors.push({ node: nextNode, distance: distance + 1, path: [...path, nextId], relationship: edge.relationship, weight: edge.weight })
        queue.push({ nodeId: nextId, distance: distance + 1, path: [...path, nextId] })
      }
    }
  }

  return { center_node: center, neighbors }
}

module.exports = {
  linkRunToMemoryGraph,
  consolidateMemoryGraph,
  getGraphSummary,
  getGraphNeighborhood,
}
