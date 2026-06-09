'use strict'
/**
 * forge_memory_graph.js — AscendForge Phase 9 cognitive memory graph service.
 *
 * Builds and maintains a knowledge graph linking runs, lessons, skills, files,
 * failures, and other memory artifacts. The orchestrator/pipeline consults this
 * graph for "have we seen this before?" recall and contradiction detection.
 *
 * Design contract: this module is read/written on the hot path of the run
 * pipeline. It MUST degrade gracefully — every DB-touching function is wrapped
 * so a store failure returns a safe empty/zero result and NEVER throws. All
 * persisted payloads are scrubbed of secrets first.
 *
 * The `store` instance is injected as the first arg of every export so this
 * service stays stateless and independently testable.
 */
const crypto = require('crypto')
const { scrubSecretsFromLearningData } = require('./forge_learning')

const NODE_TYPES = [
  'memory', 'run', 'lesson', 'skill', 'backlog_item', 'roadmap_item', 'cycle',
  'file', 'patch', 'model_version', 'evaluation_case', 'preference_pair',
  'suggestion', 'failure_pattern', 'command_pattern', 'security_finding',
  'reviewer_finding',
]
const EDGE_TYPES = [
  'relates_to', 'caused_by', 'fixed_by', 'failed_because', 'uses_skill',
  'improves_skill', 'touches_file', 'similar_to', 'contradicts', 'supports',
  'depends_on', 'derived_from', 'promoted_from', 'trained_from', 'evaluated_by',
  'blocked_by', 'approved_by', 'rejected_by', 'repeated_pattern',
  'recommended_for', 'risky_for', 'useful_for',
]

const NODE_SET = new Set(NODE_TYPES)
const EDGE_SET = new Set(EDGE_TYPES)

// Negation markers used by the contradiction heuristic. Presence on one node but
// not its keyword-twin signals opposing guidance ("never use X" vs "use X").
const NEGATION_RE = /\b(never|don't|dont|do not|avoid|stop|no longer|instead of|cannot|must not|shouldn't|shouldnt)\b/i

// ── id + token helpers ──────────────────────────────────────────────────────
const nid = () => `node-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
const eid = () => `edge-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
const nowIso = () => new Date().toISOString()

// Tokenize to lowercased significant words (len > 3 filters noise like "the").
function tokens(...parts) {
  const text = parts.filter(Boolean).join(' ').toLowerCase()
  return new Set(text.split(/[^a-z0-9]+/).filter(t => t.length > 3))
}

function jaccard(a, b) {
  if (!a.size || !b.size) return 0
  let inter = 0
  for (const t of a) if (b.has(t)) inter++
  return inter / (a.size + b.size - inter)
}

// Confidence float for "high" buckets — keeps callers from hardcoding numbers.
const HIGH_CONF = 0.85

// ── core writes ─────────────────────────────────────────────────────────────

// Upsert a node, deduping by (node_type, source_id). Returns the node or null.
function upsertGraphNode(store, projectId, node) {
  try {
    const type = node && node.node_type
    if (!type || !NODE_SET.has(type)) return null
    const sourceId = node.source_id != null ? String(node.source_id) : null
    // Dedup: reuse + touch an existing node for the same source instead of
    // accumulating duplicates every consolidation pass.
    if (sourceId) {
      const existing = store.findGraphNodeBySource(projectId, type, sourceId)
      if (existing) {
        const patch = scrubSecretsFromLearningData({
          title: node.title != null ? node.title : existing.title,
          summary: node.summary != null ? node.summary : existing.summary,
          payload: node.payload != null ? node.payload : existing.payload,
          confidence: node.confidence != null ? node.confidence : existing.confidence,
        })
        store.updateGraphNode(existing.node_id, patch)
        store.touchGraphNode(existing.node_id)
        return store.findGraphNode(existing.node_id) || existing
      }
    }
    const clean = scrubSecretsFromLearningData({
      node_id: node.node_id || nid(),
      project_id: projectId,
      node_type: type,
      source_id: sourceId,
      title: node.title || '',
      summary: node.summary || '',
      payload: node.payload || {},
      confidence: typeof node.confidence === 'number' ? node.confidence : 0.5,
      created_at: node.created_at || nowIso(),
    })
    store.upsertGraphNode(clean)
    return clean
  } catch {
    return null
  }
}

// Create an edge (store auto-reinforces existing ones). Returns edge or null.
function createGraphEdge(store, projectId, edge) {
  try {
    const type = edge && edge.edge_type
    if (!type || !EDGE_SET.has(type)) return null
    if (!edge.from_node_id || !edge.to_node_id) return null
    if (edge.from_node_id === edge.to_node_id) return null // no self-loops
    const clean = scrubSecretsFromLearningData({
      edge_id: edge.edge_id || eid(),
      project_id: projectId,
      from_node_id: edge.from_node_id,
      to_node_id: edge.to_node_id,
      edge_type: type,
      weight: typeof edge.weight === 'number' ? edge.weight : 1,
      evidence: edge.evidence || {},
      created_at: edge.created_at || nowIso(),
    })
    return store.upsertGraphEdge(clean) || clean
  } catch {
    return null
  }
}

function reinforceGraphEdge(store, projectId, edgeId, amount) {
  try {
    if (!edgeId) return null
    return store.reinforceGraphEdge(edgeId, typeof amount === 'number' ? amount : 1)
  } catch {
    return null
  }
}

// ── retrieval ───────────────────────────────────────────────────────────────

// Keyword match across nodes, ranked by Jaccard overlap of query vs title+summary.
function findRelatedNodes(store, projectId, query, options = {}) {
  try {
    const qTokens = tokens(query)
    if (!qTokens.size) return []
    const limit = options.limit || 20
    const nodes = store.getGraphNodes(projectId, {
      node_type: options.node_type,
      search: query,
      limit: limit * 4,
    }) || []
    const scored = nodes.map(n => ({
      node: n,
      score: jaccard(qTokens, tokens(n.title, n.summary)),
    }))
    return scored
      .filter(s => s.score >= (options.threshold || 0.15))
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map(s => ({ ...s.node, _score: s.score }))
  } catch {
    return []
  }
}

// Find memories similar to a working context (goal/stage/files/category).
// Combines keyword Jaccard with structural boosts (shared file/skill/category).
function findSimilarMemories(store, projectId, context = {}, options = {}) {
  try {
    const limit = options.limit || 10
    const ctxTokens = tokens(context.goal, context.stage, context.category,
      ...(Array.isArray(context.files) ? context.files : []))
    if (!ctxTokens.size) return []
    const files = new Set((Array.isArray(context.files) ? context.files : []).map(f => String(f)))
    // Pull a broad candidate set (memory + lesson + run nodes are the recall targets).
    const candidates = store.getGraphNodes(projectId, { limit: 200 }) || []
    const scored = candidates.map(n => {
      let score = jaccard(ctxTokens, tokens(n.title, n.summary))
      const p = n.payload || {}
      // Structural similarity boosts — cheap signals the keyword pass misses.
      if (context.category && p.category && p.category === context.category) score += 0.25
      if (files.size && p.file_path && files.has(String(p.file_path))) score += 0.3
      if (context.stage && p.stage && p.stage === context.stage) score += 0.15
      return { node: n, score }
    })
    return scored
      .filter(s => s.score >= (options.threshold || 0.15))
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map(s => ({ ...s.node, _score: Number(s.score.toFixed(3)) }))
  } catch {
    return []
  }
}

// ── linkers (ingest source records into the graph) ──────────────────────────

// Materialize a run + its surroundings (files, skills, findings, lessons) and
// wire the edges. Returns counts so the pipeline can report graph growth.
function linkRunToMemoryGraph(store, projectId, runId) {
  let nodes_created = 0, edges_created = 0
  try {
    const run = store.findRun(runId)
    if (!run) return { nodes_created, edges_created }
    const failed = /fail/i.test(run.status || '')
    const runNode = upsertGraphNode(store, projectId, {
      node_type: 'run',
      source_id: runId,
      title: run.goal ? `Run: ${String(run.goal).slice(0, 80)}` : `Run ${runId}`,
      summary: run.final_report || run.goal || '',
      payload: { status: run.status, goal: run.goal, outcome: failed ? 'failed' : 'verified' },
      confidence: 0.6,
    })
    if (!runNode) return { nodes_created, edges_created }
    nodes_created++

    const link = (toNode, edge_type, evidence) => {
      if (!toNode) return
      nodes_created++
      if (createGraphEdge(store, projectId, {
        from_node_id: runNode.node_id, to_node_id: toNode.node_id, edge_type, evidence,
      })) edges_created++
    }

    // Patched files → file nodes via touches_file.
    const patches = Array.isArray(run.patches) ? run.patches : []
    const seenFiles = new Set()
    for (const pt of patches) {
      const fp = pt && (pt.file_path || pt.path || pt.file)
      if (!fp || seenFiles.has(fp)) continue
      seenFiles.add(fp)
      link(upsertGraphNode(store, projectId, {
        node_type: 'file', source_id: fp, title: fp,
        summary: `File touched by runs`, payload: { file_path: fp }, confidence: 0.5,
      }), 'touches_file', { run_id: runId })
    }

    // Skills used by the run.
    const skills = Array.isArray(run.skills_used) ? run.skills_used
      : (Array.isArray(run.skills) ? run.skills : [])
    for (const sk of skills) {
      const sid = sk && (sk.id || sk.skill_id || sk)
      if (!sid) continue
      link(upsertGraphNode(store, projectId, {
        node_type: 'skill', source_id: String(sid), title: `Skill ${sid}`,
        summary: typeof sk === 'object' ? (sk.description || '') : '',
        payload: { skill_id: sid }, confidence: 0.5,
      }), 'uses_skill', { run_id: runId })
    }

    // Security + reviewer findings → finding nodes (caused_by from the run).
    const review = run.review || {}
    const findings = [
      ...(Array.isArray(review.security_findings) ? review.security_findings.map(f => ['security_finding', f]) : []),
      ...(Array.isArray(review.reviewer_findings) ? review.reviewer_findings.map(f => ['reviewer_finding', f]) : []),
    ]
    findings.forEach(([ntype, f], i) => {
      const desc = (f && (f.title || f.message || f.description)) || `finding ${i}`
      link(upsertGraphNode(store, projectId, {
        node_type: ntype, source_id: `${runId}:${ntype}:${i}`, title: String(desc).slice(0, 80),
        summary: String(desc), payload: { ...(typeof f === 'object' ? f : { value: f }), run_id: runId },
        confidence: 0.55,
      }), 'caused_by', { run_id: runId })
    })

    // Failure → failure_pattern node (failed_because) for repeat detection.
    if (failed) {
      const reason = run.failure_reason || run.final_report || 'unknown failure'
      link(upsertGraphNode(store, projectId, {
        node_type: 'failure_pattern', source_id: `fail:${String(reason).slice(0, 40)}`,
        title: `Failure: ${String(reason).slice(0, 60)}`, summary: String(reason),
        payload: { reason }, confidence: 0.6,
      }), 'failed_because', { run_id: runId })
    }

    // Lessons derived from this run.
    const lessons = (store.getLessons(projectId, { run_id: runId }) || [])
      .filter(l => !l.run_id || l.run_id === runId)
    for (const lesson of lessons) {
      link(upsertGraphNode(store, projectId, {
        node_type: 'lesson', source_id: String(lesson.id || lesson.lesson_id),
        title: String(lesson.title || lesson.summary || 'lesson').slice(0, 80),
        summary: lesson.summary || lesson.content || '',
        payload: { category: lesson.category }, confidence: 0.6,
      }), 'derived_from', { run_id: runId })
    }
    return { nodes_created, edges_created }
  } catch {
    return { nodes_created, edges_created }
  }
}

function linkLessonToMemoryGraph(store, projectId, lessonId) {
  try {
    const lessons = store.getLessons(projectId, {}) || []
    const lesson = lessons.find(l => String(l.id || l.lesson_id) === String(lessonId))
    if (!lesson) return null
    const node = upsertGraphNode(store, projectId, {
      node_type: 'lesson', source_id: String(lessonId),
      title: String(lesson.title || lesson.summary || 'lesson').slice(0, 80),
      summary: lesson.summary || lesson.content || '',
      payload: { category: lesson.category, count: lesson.count },
      confidence: (lesson.count || 0) >= 2 ? HIGH_CONF : 0.6,
    })
    if (!node) return null
    // Link lesson to runs it derived from when known.
    if (lesson.run_id) {
      const runNode = store.findGraphNodeBySource(projectId, 'run', String(lesson.run_id))
      if (runNode) createGraphEdge(store, projectId, {
        from_node_id: node.node_id, to_node_id: runNode.node_id, edge_type: 'derived_from',
      })
    }
    return node
  } catch {
    return null
  }
}

function linkSkillToMemoryGraph(store, projectId, skillId) {
  try {
    return upsertGraphNode(store, projectId, {
      node_type: 'skill', source_id: String(skillId),
      title: `Skill ${skillId}`, summary: '', payload: { skill_id: skillId }, confidence: 0.5,
    })
  } catch {
    return null
  }
}

function linkFileToMemoryGraph(store, projectId, filePath) {
  try {
    if (!filePath) return null
    return upsertGraphNode(store, projectId, {
      node_type: 'file', source_id: String(filePath), title: String(filePath),
      summary: '', payload: { file_path: filePath }, confidence: 0.5,
    })
  } catch {
    return null
  }
}

// ── contradiction detection ─────────────────────────────────────────────────

// Find existing memory nodes whose guidance opposes `node`: they share >=2
// significant keywords but differ on negation polarity. Conservative by design
// (false positives are worse than misses here). Creates 'contradicts' edges and
// supersedes the loser (older / lower confidence) without deleting it.
function detectContradictions(store, projectId, node) {
  const found = []
  try {
    if (!node) return found
    const newTokens = tokens(node.title, node.summary)
    const newText = `${node.title || ''} ${node.summary || ''}`
    const newNeg = NEGATION_RE.test(newText)
    const candidates = store.getGraphNodes(projectId, { node_type: 'memory', limit: 200 }) || []
    for (const cand of candidates) {
      if (cand.node_id === node.node_id) continue
      if (cand.payload && cand.payload.superseded) continue
      const candText = `${cand.title || ''} ${cand.summary || ''}`
      const candNeg = NEGATION_RE.test(candText)
      if (candNeg === newNeg) continue // same polarity → not a contradiction
      // Count shared significant keywords (len>3) excluding the negation words.
      let shared = 0
      const candTokens = tokens(cand.title, cand.summary)
      for (const t of newTokens) if (candTokens.has(t)) shared++
      if (shared < 2) continue
      const reason = `shared ${shared} keywords with opposing polarity`
      found.push({ node_id: cand.node_id, reason })
      if (node.node_id) createGraphEdge(store, projectId, {
        from_node_id: node.node_id, to_node_id: cand.node_id,
        edge_type: 'contradicts', evidence: { reason, shared },
      })
      // Resolve: newer/higher-confidence wins. Mark the loser superseded.
      const newConf = typeof node.confidence === 'number' ? node.confidence : 0.5
      const candConf = typeof cand.confidence === 'number' ? cand.confidence : 0.5
      const loser = newConf >= candConf ? cand : node
      if (loser.node_id) {
        try {
          store.updateGraphNode(loser.node_id, {
            payload: { ...(loser.payload || {}), superseded: true },
          })
        } catch { /* non-fatal */ }
      }
    }
  } catch {
    return found
  }
  return found
}

// ── consolidation ───────────────────────────────────────────────────────────

// Periodic graph maintenance: ingest recent lessons/runs, link similar items,
// reinforce repeated relationships, promote repeated lessons, detect
// contradictions. Capped to stay fast on the pipeline's idle cycle. Records a
// consolidation run and returns its summary.
function consolidateMemoryGraph(store, projectId, options = {}) {
  const summary = {
    nodes_created: 0, edges_created: 0, edges_reinforced: 0,
    memories_promoted: 0, contradictions_found: 0,
    trigger_type: options.trigger_type || 'manual',
  }
  try {
    const lessons = (store.getLessons(projectId, { limit: 100 }) || []).slice(0, 100)
    const runs = (typeof store.getRuns === 'function'
      ? (store.getRuns(projectId, { limit: 50 }) || []) : []).slice(0, 50)

    // 1) Ingest lessons; promote those seen >=2 times to high confidence.
    const lessonNodes = []
    for (const lesson of lessons) {
      const promoted = (lesson.count || 0) >= 2
      const before = store.findGraphNodeBySource(projectId, 'lesson', String(lesson.id || lesson.lesson_id))
      const node = upsertGraphNode(store, projectId, {
        node_type: 'lesson', source_id: String(lesson.id || lesson.lesson_id),
        title: String(lesson.title || lesson.summary || 'lesson').slice(0, 80),
        summary: lesson.summary || lesson.content || '',
        payload: { category: lesson.category, count: lesson.count, promoted },
        confidence: promoted ? HIGH_CONF : 0.6,
      })
      if (node) {
        if (!before) summary.nodes_created++
        if (promoted && (!before || (before.confidence || 0) < HIGH_CONF)) summary.memories_promoted++
        lessonNodes.push(node)
      }
    }

    // 2) Link similar lessons (similar_to / repeated_pattern). Reinforce repeats.
    for (let i = 0; i < lessonNodes.length; i++) {
      const a = lessonNodes[i]
      const aTok = tokens(a.title, a.summary)
      for (let j = i + 1; j < lessonNodes.length; j++) {
        const b = lessonNodes[j]
        const sim = jaccard(aTok, tokens(b.title, b.summary))
        if (sim < 0.3) continue
        const sameCat = a.payload && b.payload && a.payload.category &&
          a.payload.category === b.payload.category
        const edge = createGraphEdge(store, projectId, {
          from_node_id: a.node_id, to_node_id: b.node_id,
          edge_type: sameCat ? 'repeated_pattern' : 'similar_to',
          weight: sim, evidence: { similarity: Number(sim.toFixed(3)) },
        })
        if (edge) { edge.reinforced ? summary.edges_reinforced++ : summary.edges_created++ }
      }
    }

    // 3) Run nodes + outcome-based similarity (both verified / both failed).
    const runNodes = []
    for (const run of runs) {
      const rid = run.id || run.run_id
      if (!rid) continue
      const res = linkRunToMemoryGraph(store, projectId, rid)
      summary.nodes_created += res.nodes_created
      summary.edges_created += res.edges_created
      const node = store.findGraphNodeBySource(projectId, 'run', String(rid))
      if (node) runNodes.push(node)
    }
    for (let i = 0; i < runNodes.length; i++) {
      for (let j = i + 1; j < runNodes.length; j++) {
        const a = runNodes[i], b = runNodes[j]
        const ao = a.payload && a.payload.outcome, bo = b.payload && b.payload.outcome
        if (!ao || ao !== bo) continue // only link matching outcomes
        const sim = jaccard(tokens(a.title, a.summary), tokens(b.title, b.summary))
        if (sim < 0.2) continue
        const edge = createGraphEdge(store, projectId, {
          from_node_id: a.node_id, to_node_id: b.node_id, edge_type: 'similar_to',
          weight: sim, evidence: { outcome: ao, similarity: Number(sim.toFixed(3)) },
        })
        if (edge) { edge.reinforced ? summary.edges_reinforced++ : summary.edges_created++ }
      }
    }

    // 4) Contradiction sweep over memory nodes (recent first).
    const mems = (store.getGraphNodes(projectId, { node_type: 'memory', limit: 100 }) || [])
    for (const m of mems) {
      const c = detectContradictions(store, projectId, m)
      summary.contradictions_found += c.length
    }

    // 5) Record the run + a cognitive event for the activity feed.
    const runId = `consol-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
    try {
      store.upsertConsolidationRun({
        run_id: runId, project_id: projectId, trigger_type: summary.trigger_type,
        ...summary, created_at: nowIso(),
      })
      store.upsertCognitiveEvent({
        event_id: `cog-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
        project_id: projectId, run_id: runId, event_type: 'memory_consolidation',
        title: `Consolidation: +${summary.nodes_created} nodes, +${summary.edges_created} edges`,
        details: summary, created_at: nowIso(),
      })
    } catch { /* persistence of the audit record is best-effort */ }
  } catch {
    return summary
  }
  return summary
}

// ── thin store wrappers ─────────────────────────────────────────────────────

function getGraphNeighborhood(store, projectId, nodeId, depth) {
  try {
    return store.getGraphNeighborhood(projectId, nodeId, depth || 1) || { nodes: [], edges: [] }
  } catch {
    return { nodes: [], edges: [] }
  }
}

function getGraphSummary(store, projectId) {
  try {
    return store.getGraphSummary(projectId) || {
      nodes: 0, edges: 0, high_confidence: 0, contradicted: 0,
      by_type: {}, top_files: [], top_skills: [], failure_patterns: [],
    }
  } catch {
    return {
      nodes: 0, edges: 0, high_confidence: 0, contradicted: 0,
      by_type: {}, top_files: [], top_skills: [], failure_patterns: [],
    }
  }
}

// All nodes/edges anchored to a run: the run node plus its 1-hop neighborhood.
function getGraphForRun(store, projectId, runId) {
  try {
    const runNode = store.findGraphNodeBySource(projectId, 'run', String(runId))
    if (!runNode) return { nodes: [], edges: [] }
    return getGraphNeighborhood(store, projectId, runNode.node_id, 1)
  } catch {
    return { nodes: [], edges: [] }
  }
}

module.exports = {
  NODE_TYPES, EDGE_TYPES,
  upsertGraphNode,
  createGraphEdge,
  reinforceGraphEdge,
  findRelatedNodes,
  findSimilarMemories,
  linkRunToMemoryGraph,
  linkLessonToMemoryGraph,
  linkSkillToMemoryGraph,
  linkFileToMemoryGraph,
  detectContradictions,
  consolidateMemoryGraph,
  getGraphNeighborhood,
  getGraphSummary,
  getGraphForRun,
}
