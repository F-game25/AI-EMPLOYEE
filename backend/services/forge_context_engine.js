'use strict'

// AscendForge Phase 9 — Context Engine.
// Assembles a compact, relevance-ranked "context packet" per pipeline stage so each
// agent runs with the right memories/skills/models/files instead of the whole graph.
// Hard rule: never throw into the pipeline — every public fn degrades to safe defaults.

const crypto = require('crypto')
const { scrubSecretsFromLearningData } = require('./forge_learning')
let memoryGraph = {}
try { memoryGraph = require('./forge_memory_graph') } catch (_) { memoryGraph = {} }

const STAGES = ['planner', 'decomposer', 'coder', 'tester', 'debug', 'security', 'reviewer', 'autopilot', 'roadmap', 'skill_selection', 'model_routing']

// Stage → applicable helper model types. security is intentionally empty (no helper LLM enforced).
const STAGE_MODEL_TYPES = {
  planner: ['skill_selector', 'decomposer_helper', 'risk_classifier'],
  decomposer: ['skill_selector', 'decomposer_helper'],
  coder: [],
  tester: ['failure_classifier'],
  debug: ['failure_classifier'],
  security: [],
  reviewer: [],
  autopilot: ['risk_classifier'],
  roadmap: [],
  skill_selection: ['skill_selector'],
  model_routing: ['model_router_classifier'],
}

const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'is', 'are', 'be', 'add', 'fix', 'make', 'this', 'that', 'it', 'as', 'at', 'by'])

const newId = (p) => `${p}-${crypto.randomBytes(8).toString('hex')}`
const nowIso = () => new Date().toISOString()
const safe = (fn, fallback) => { try { return fn() } catch (_) { return fallback } }
const arr = (v) => (Array.isArray(v) ? v : [])

function tokenize (s) {
  return String(s || '').toLowerCase().match(/[a-z0-9_]+/g)?.filter(t => t.length > 2 && !STOP.has(t)) || []
}

// Overlap count between goal/stage tokens and a candidate's text. Normalized small bonus
// keeps it Jaccard-ish without zeroing single-strong-match items.
function score (queryTokens, text) {
  if (!queryTokens.length) return 0
  const cand = new Set(tokenize(text))
  if (!cand.size) return 0
  let overlap = 0
  for (const t of queryTokens) if (cand.has(t)) overlap++
  return overlap + overlap / (cand.size + queryTokens.length)
}

function rank (items, queryTokens, textOf, k) {
  return items
    .map(it => ({ it, s: score(queryTokens, textOf(it)) }))
    .filter(x => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, k)
    .map(x => x.it)
}

// ── memory ──────────────────────────────────────────────────────────────────
function selectRelevantMemories (store, projectId, goal, stage) {
  return safe(() => {
    const q = tokenize(`${goal} ${stage}`)
    const facts = arr(store.getMemoryFacts && store.getMemoryFacts(projectId))
    const topFacts = rank(facts, q, f => `${f.fact} ${f.category} ${f.evidence || ''}`, 6)
    let nodes = []
    if (memoryGraph.findSimilarMemories) {
      nodes = arr(safe(() => memoryGraph.findSimilarMemories(store, projectId, `${goal} ${stage}`, { limit: 6 }), []))
    }
    return { facts: topFacts, nodes: nodes.slice(0, 6) }
  }, { facts: [], nodes: [] })
}

function selectRelevantSkills (store, projectId, goal, stage) {
  return safe(() => {
    const q = tokenize(`${goal} ${stage}`)
    // Skill knowledge lives in memory facts (category 'skill') + graph related nodes.
    const facts = arr(store.getMemoryFacts && store.getMemoryFacts(projectId, 'skill'))
    let related = []
    if (memoryGraph.findRelatedNodes) {
      related = arr(safe(() => memoryGraph.findRelatedNodes(store, projectId, goal, { type: 'skill', limit: 5 }), []))
    }
    const ranked = rank(facts, q, f => `${f.fact} ${f.evidence || ''}`, 5)
    return [...ranked, ...related].slice(0, 5)
  }, [])
}

function selectRelevantModels (store, projectId, stage, goal) {
  return safe(() => {
    const types = STAGE_MODEL_TYPES[stage] || []
    const out = []
    for (const t of types) {
      const m = safe(() => store.getActiveModelVersion && store.getActiveModelVersion(projectId, t), null)
      if (m && (m.status === undefined || m.status === 'ACTIVE')) out.push({ model_type: t, version: m })
    }
    return out
  }, [])
}

function selectRelevantFiles (store, projectId, goal, repoIndex) {
  return safe(() => {
    const q = tokenize(goal)
    // Risky/frequently-edited file knowledge is stored as memory facts (category 'file'/'risk').
    const facts = [
      ...arr(store.getMemoryFacts && store.getMemoryFacts(projectId, 'file')),
      ...arr(store.getMemoryFacts && store.getMemoryFacts(projectId, 'risk')),
    ]
    const ranked = rank(facts, q, f => `${f.fact} ${f.evidence || ''}`, 8)
      .map(f => ({ path: f.fact, reason: f.category, confidence: f.confidence }))
    // repoIndex (optional): [{path, edits}] — surface most-churned files matching goal.
    const idx = arr(repoIndex)
      .filter(r => r && r.path)
      .map(r => ({ r, s: score(q, r.path) + (Number(r.edits) || 0) / 100 }))
      .sort((a, b) => b.s - a.s)
      .slice(0, 8)
      .map(x => ({ path: x.r.path, reason: 'frequently_edited', edits: x.r.edits }))
    const seen = new Set()
    return [...ranked, ...idx].filter(f => !seen.has(f.path) && seen.add(f.path)).slice(0, 8)
  }, [])
}

function selectRelevantLessons (store, projectId, goal, stage) {
  return safe(() => {
    const q = tokenize(`${goal} ${stage}`)
    // Bias toward reviewer/security lessons for those stages, else general.
    const cats = stage === 'security' ? ['security'] : stage === 'reviewer' ? ['reviewer', 'code_quality'] : [undefined]
    const lessons = []
    for (const c of cats) lessons.push(...arr(store.getLessons && store.getLessons(projectId, { category: c, limit: 20 })))
    return rank(lessons, q, l => `${l.lesson} ${l.category} ${l.evidence || ''}`, 6)
  }, [])
}

function selectRelevantFailures (store, projectId, goal, stage) {
  return safe(() => {
    const q = tokenize(`${goal} ${stage}`)
    let patterns = []
    if (memoryGraph.findRelatedNodes) {
      patterns = arr(safe(() => memoryGraph.findRelatedNodes(store, projectId, goal, { type: 'failure_pattern', limit: 6 }), []))
    }
    const failedLessons = rank(
      arr(store.getLessons && store.getLessons(projectId, { category: 'failure', limit: 20 })),
      q, l => `${l.lesson} ${l.evidence || ''}`, 5
    )
    return { patterns: patterns.slice(0, 6), lessons: failedLessons }
  }, { patterns: [], lessons: [] })
}

function selectRelevantEvalCases (store, projectId, goal, stage) {
  return safe(() => {
    const q = tokenize(`${goal} ${stage}`)
    const cases = arr(store.getEvalCases && store.getEvalCases(projectId, { limit: 20 }))
    return rank(cases, q, c => `${c.name || ''} ${c.description || ''} ${c.eval_type || ''} ${c.input || ''}`, 5)
  }, [])
}

// ── packet assembly ───────────────────────────────────────────────────────────
function buildContextPacket (store, project, run, stage, goal, options = {}) {
  const created_at = nowIso()
  const projectId = (project && (project.id || project.project_id)) || (run && run.project_id) || null
  const runId = (run && (run.id || run.run_id)) || null
  const packetId = newId('pkt')
  const excluded_reason = []

  // Stack from project or run context pack.
  const stack = (project && project.stack) || (run && run.context_pack && run.context_pack.stack) || {}

  const memories = selectRelevantMemories(store, projectId, goal, stage)
  const skills = selectRelevantSkills(store, projectId, goal, stage)
  const models = selectRelevantModels(store, projectId, stage, goal)
  const files = selectRelevantFiles(store, projectId, goal, options.repoIndex)
  const lessons = selectRelevantLessons(store, projectId, goal, stage)
  const failures = selectRelevantFailures(store, projectId, goal, stage)
  const evalCases = selectRelevantEvalCases(store, projectId, goal, stage)

  if (stage === 'security' && (STAGE_MODEL_TYPES[stage] || []).length === 0) {
    excluded_reason.push({ item: 'helper_models', reason: 'no helper model enforced for security stage' })
  }

  // Similar prior runs via graph (split success/failure).
  let similarSuccess = []; let similarFailed = []
  if (memoryGraph.findSimilarMemories) {
    const sims = arr(safe(() => memoryGraph.findSimilarMemories(store, projectId, goal, { type: 'run', limit: 8 }), []))
    for (const s of sims) {
      const ok = s.outcome === 'success' || s.status === 'PASSED' || s.success === true
      ;(ok ? similarSuccess : similarFailed).push(s)
    }
    similarSuccess = similarSuccess.slice(0, 4); similarFailed = similarFailed.slice(0, 4)
  }

  // Backlog / roadmap / cycle context (all guarded — APIs may be absent).
  const backlog = safe(() => arr(store.getBacklogItems && store.getBacklogItems(projectId)).slice(0, 5), [])
  const roadmap = typeof store.getRoadmap === 'function' ? safe(() => store.getRoadmap(projectId), null) : null
  const graphSummary = memoryGraph.getGraphSummary
    ? safe(() => memoryGraph.getGraphSummary(store, projectId), null) : null

  // Known good / failing commands surfaced from memory facts.
  const goodCommands = safe(() => arr(store.getMemoryFacts && store.getMemoryFacts(projectId, 'good_command')).slice(0, 5).map(f => f.fact), [])
  const failingCommands = safe(() => arr(store.getMemoryFacts && store.getMemoryFacts(projectId, 'failing_command')).slice(0, 5).map(f => f.fact), [])

  const selected_nodes = [...arr(memories.nodes), ...arr(failures.patterns)]
  const selected_edges = arr(graphSummary && graphSummary.edges).slice(0, 12)
  const selected_skills = skills
  const selected_models = models
  const included_files = files

  const final_context = {
    goal,
    stage,
    stack,
    memory_facts: memories.facts,
    memory_nodes: memories.nodes,
    skills,
    helper_models: models,
    risky_files: files,
    similar_successful_runs: similarSuccess,
    similar_failed_runs: similarFailed,
    failure_patterns: failures.patterns,
    lessons,
    failed_run_lessons: failures.lessons,
    eval_cases: evalCases,
    backlog,
    roadmap,
    good_commands: goodCommands,
    failing_commands: failingCommands,
  }

  let packet = {
    packet_id: packetId,
    project_id: projectId,
    run_id: runId,
    stage,
    goal,
    selected_nodes,
    selected_edges,
    selected_skills,
    selected_models,
    included_files,
    excluded_reason,
    final_context,
    created_at,
  }

  // Optional pre-persist compression to keep packet small.
  if (options.budget) packet = compressContext(packet, options.budget)

  // Double-scrub: facts are pre-scrubbed but the packet may carry assembled text.
  packet = safe(() => scrubSecretsFromLearningData(packet) || packet, packet)

  safe(() => store.upsertContextPacket && store.upsertContextPacket(packet), null)
  safe(() => store.upsertCognitiveEvent && store.upsertCognitiveEvent({
    event_id: newId('evt'),
    project_id: projectId,
    run_id: runId,
    event_type: 'context_packet_created',
    title: `Context packet for ${stage}`,
    details: {
      packet_id: packetId,
      memories: memories.facts.length,
      skills: skills.length,
      models: models.length,
      files: files.length,
      excluded: excluded_reason.length,
    },
    created_at,
  }), null)

  return packet
}

// Trim string fields in final_context to a char budget; log what was dropped.
function compressContext (packet, budget = 4000) {
  return safe(() => {
    if (!packet || !packet.final_context) return packet
    const fc = packet.final_context
    let used = 0
    // Order by importance — earlier fields keep priority over the budget.
    const order = ['goal', 'stack', 'memory_facts', 'failure_patterns', 'lessons', 'risky_files', 'skills', 'helper_models', 'similar_successful_runs', 'similar_failed_runs', 'eval_cases', 'backlog', 'good_commands', 'failing_commands', 'failed_run_lessons', 'memory_nodes', 'roadmap']
    const excluded = arr(packet.excluded_reason)
    for (const key of order) {
      if (!(key in fc)) continue
      const str = JSON.stringify(fc[key])
      if (used + str.length <= budget) { used += str.length; continue }
      // Over budget: drop progressively from the tail of arrays, else drop field.
      if (Array.isArray(fc[key]) && fc[key].length > 0) {
        const before = fc[key].length
        while (fc[key].length > 0 && used + JSON.stringify(fc[key]).length > budget) fc[key].pop()
        used += JSON.stringify(fc[key]).length
        if (fc[key].length < before) excluded.push({ item: key, reason: `budget trimmed (${before}→${fc[key].length})` })
      } else {
        excluded.push({ item: key, reason: 'budget trimmed (dropped)' })
        delete fc[key]
      }
    }
    packet.excluded_reason = excluded
    return packet
  }, packet)
}

function recordContextUsage (store, packet, outcome) {
  return safe(() => {
    const o = outcome || {}
    const fc = (packet && packet.final_context) || {}
    const usage = {
      usage_id: newId('usage'),
      project_id: packet && packet.project_id,
      run_id: packet && packet.run_id,
      stage: packet && packet.stage,
      packet_id: packet && packet.packet_id,
      agent_name: o.agent_name || (packet && packet.stage) || null,
      memory_nodes_used: o.memory_nodes_used != null ? o.memory_nodes_used : arr(packet && packet.selected_nodes).length,
      skills_used: o.skills_used != null ? o.skills_used : arr(packet && packet.selected_skills).length,
      helper_models_consulted: o.helper_models_consulted != null ? o.helper_models_consulted : arr(packet && packet.selected_models).length,
      outcome_status: o.outcome_status || o.status || 'unknown',
      created_at: nowIso(),
    }
    void fc
    safe(() => store.upsertStageContextUsage && store.upsertStageContextUsage(usage), null)
    return usage
  }, null)
}

module.exports = {
  STAGES,
  buildContextPacket,
  selectRelevantMemories,
  selectRelevantSkills,
  selectRelevantModels,
  selectRelevantFiles,
  selectRelevantLessons,
  selectRelevantFailures,
  selectRelevantEvalCases,
  compressContext,
  recordContextUsage,
}
