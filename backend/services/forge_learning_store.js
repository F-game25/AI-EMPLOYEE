'use strict'

/**
 * forge_learning_store.js — Phase 7-9 AscendForge learning & memory data layer.
 *
 * All data is persisted as JSON files under FORGE_HOME. Each collection is a
 * separate file per project so reads stay fast even at scale.
 */

const fs   = require('fs')
const path = require('path')
const crypto = require('crypto')

function nowIso() { return new Date().toISOString() }
function uid(prefix) { return `${prefix}-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}` }

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return fallback }
}
function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}
function loadList(file) { return readJson(file, []) }
function saveList(file, list) { writeJson(file, Array.isArray(list) ? list : []) }

class ForgeLearningStore {
  constructor(forgeHome) {
    this.home = forgeHome
  }

  _f(projectId, collection) {
    return path.join(this.home, collection, `${projectId}.json`)
  }

  _list(projectId, collection)            { return loadList(this._f(projectId, collection)) }
  _save(projectId, collection, list)      { saveList(this._f(projectId, collection), list) }

  _upsert(projectId, collection, idField, item) {
    const list = this._list(projectId, collection)
    const idx  = list.findIndex(i => i[idField] === item[idField])
    if (idx >= 0) list[idx] = { ...list[idx], ...item, updated_at: nowIso() }
    else list.unshift({ ...item, created_at: item.created_at || nowIso(), updated_at: nowIso() })
    this._save(projectId, collection, list)
    return list.find(i => i[idField] === item[idField])
  }

  // ── Learning records / lessons ────────────────────────────────────────────

  getLessons(projectId, opts = {}) {
    let list = this._list(projectId, 'lessons')
    if (opts.status) list = list.filter(l => l.status === opts.status)
    return list.slice(0, opts.limit || 200)
  }

  upsertLesson(lesson) {
    if (!lesson.lesson_id) lesson.lesson_id = uid('les')
    return this._upsert(lesson.project_id, 'lessons', 'lesson_id', lesson)
  }

  // ── Preference pairs ──────────────────────────────────────────────────────

  getPreferencePairs(projectId, opts = {}) {
    let list = this._list(projectId, 'preference_pairs')
    if (opts.approved !== undefined) list = list.filter(p => !!p.approved === !!opts.approved)
    return list.slice(0, opts.limit || 200)
  }

  upsertPreferencePair(pair) {
    if (!pair.pair_id) pair.pair_id = uid('pp')
    return this._upsert(pair.project_id, 'preference_pairs', 'pair_id', pair)
  }

  updatePreferencePair(pairId, patch) {
    // scan all projects
    const pairsDir = path.join(this.home, 'preference_pairs')
    if (!fs.existsSync(pairsDir)) return null
    for (const f of fs.readdirSync(pairsDir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(pairsDir, f)
      const list = loadList(file)
      const idx = list.findIndex(p => p.pair_id === pairId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  // ── Eval cases ────────────────────────────────────────────────────────────

  getEvalCases(projectId, opts = {}) {
    return this._list(projectId, 'eval_cases').slice(0, opts.limit || 200)
  }

  upsertEvalCase(evalCase) {
    if (!evalCase.eval_id) evalCase.eval_id = uid('ev')
    return this._upsert(evalCase.project_id, 'eval_cases', 'eval_id', evalCase)
  }

  // ── Learning datasets ─────────────────────────────────────────────────────

  getLearningDatasets(projectId) {
    return this._list(projectId, 'datasets')
  }

  upsertDatasetCheck(check) {
    if (!check.dataset_id) check.dataset_id = uid('ds')
    return this._upsert(check.project_id || 'global', 'datasets', 'dataset_id', check)
  }

  // ── Distillation records ──────────────────────────────────────────────────

  getDistillationRecords(projectId, opts = {}) {
    let list = this._list(projectId, 'distillation')
    if (opts.run_id) list = list.filter(r => r.run_id === opts.run_id)
    return list.slice(0, opts.limit || 100)
  }

  upsertDistillationRecord(record) {
    if (!record.distillation_id) record.distillation_id = uid('dist')
    return this._upsert(record.project_id, 'distillation', 'distillation_id', record)
  }

  findDistillationByRun(runId) {
    const distDir = path.join(this.home, 'distillation')
    if (!fs.existsSync(distDir)) return []
    const results = []
    for (const f of fs.readdirSync(distDir)) {
      if (!f.endsWith('.json')) continue
      const list = loadList(path.join(distDir, f))
      results.push(...list.filter(r => r.run_id === runId))
    }
    return results
  }

  // ── Memory facts / graph ──────────────────────────────────────────────────

  getMemoryFacts(projectId, opts = {}) {
    let list = this._list(projectId, 'memory_facts')
    if (opts.fact_type) list = list.filter(f => f.fact_type === opts.fact_type)
    return list.slice(0, opts.limit || 200)
  }

  upsertMemoryFact(fact) {
    if (!fact.fact_id) fact.fact_id = uid('mf')
    return this._upsert(fact.project_id, 'memory_facts', 'fact_id', fact)
  }

  findMemoryFactByContent(projectId, content) {
    return this._list(projectId, 'memory_facts').find(f => f.content === content) || null
  }

  getGraphNodes(projectId, opts = {}) {
    let list = this._list(projectId, 'graph_nodes')
    if (opts.node_type) list = list.filter(n => n.node_type === opts.node_type)
    return list.slice(0, opts.limit || 500)
  }

  findGraphNode(projectId, nodeId) {
    return this._list(projectId, 'graph_nodes').find(n => n.node_id === nodeId) || null
  }

  touchGraphNode(projectId, nodeId, patch = {}) {
    const list = this._list(projectId, 'graph_nodes')
    const idx = list.findIndex(n => n.node_id === nodeId)
    if (idx >= 0) {
      list[idx] = { ...list[idx], ...patch, last_touched: nowIso() }
    } else {
      list.unshift({ node_id: nodeId, ...patch, created_at: nowIso(), last_touched: nowIso() })
    }
    this._save(projectId, 'graph_nodes', list)
    return list.find(n => n.node_id === nodeId)
  }

  getGraphEdges(projectId, opts = {}) {
    let list = this._list(projectId, 'graph_edges')
    if (opts.from_node) list = list.filter(e => e.from_node === opts.from_node)
    if (opts.to_node)   list = list.filter(e => e.to_node   === opts.to_node)
    return list.slice(0, opts.limit || 500)
  }

  // ── Context packets ───────────────────────────────────────────────────────

  getContextPackets(projectId, opts = {}) {
    return this._list(projectId, 'context_packets').slice(0, opts.limit || 100)
  }

  getContextPacketsForRun(runId) {
    const dir = path.join(this.home, 'context_packets')
    if (!fs.existsSync(dir)) return []
    const results = []
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      results.push(...loadList(path.join(dir, f)).filter(p => p.run_id === runId))
    }
    return results
  }

  // ── Models ────────────────────────────────────────────────────────────────

  getModels(projectId) { return this._list(projectId, 'models') }

  getModel(projectId, modelId) {
    return this._list(projectId, 'models').find(m => m.model_id === modelId) || null
  }

  upsertModel(model) {
    if (!model.model_id) model.model_id = uid('mod')
    return this._upsert(model.project_id, 'models', 'model_id', model)
  }

  updateModel(modelId, patch) {
    const modDir = path.join(this.home, 'models')
    if (!fs.existsSync(modDir)) return null
    for (const f of fs.readdirSync(modDir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(modDir, f)
      const list = loadList(file)
      const idx = list.findIndex(m => m.model_id === modelId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  getModelEvaluations(projectId, modelId) {
    return this._list(projectId, 'model_evals').filter(e => !modelId || e.model_id === modelId)
  }

  upsertModelEvaluation(evalEntry) {
    if (!evalEntry.eval_id) evalEntry.eval_id = uid('mev')
    return this._upsert(evalEntry.project_id, 'model_evals', 'eval_id', evalEntry)
  }

  findModelVersion(projectId, versionId) {
    // Delegate to training data
    const data = readJson(path.join(this.home, 'training', `${projectId}.json`), { model_versions: [] })
    return (data.model_versions || []).find(v => v.model_version_id === versionId) || null
  }

  getActiveModelVersion(projectId, modelType) {
    const data = readJson(path.join(this.home, 'training', `${projectId}.json`), { model_versions: [] })
    const versions = (data.model_versions || []).filter(v => !modelType || v.model_type === modelType)
    return versions.find(v => v.status === 'ACTIVE') || versions[0] || null
  }

  updateModelVersion(projectId, versionId, patch) {
    const file = path.join(this.home, 'training', `${projectId}.json`)
    const data = readJson(file, { training_runs: [], model_versions: [] })
    const idx = (data.model_versions || []).findIndex(v => v.model_version_id === versionId)
    if (idx < 0) return null
    data.model_versions[idx] = { ...data.model_versions[idx], ...patch, updated_at: nowIso() }
    writeJson(file, data)
    return data.model_versions[idx]
  }

  upsertModelPromotion(promotion) {
    if (!promotion.promotion_id) promotion.promotion_id = uid('promo')
    return this._upsert(promotion.project_id, 'model_promotions', 'promotion_id', promotion)
  }

  updateModelPromotion(promotionId, patch) {
    const dir = path.join(this.home, 'model_promotions')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(p => p.promotion_id === promotionId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  getLatestPromotion(projectId, modelType) {
    const list = this._list(projectId, 'model_promotions')
    const filtered = modelType ? list.filter(p => p.model_type === modelType) : list
    return filtered[0] || null
  }

  getModelRoutingStats(projectId) {
    return this._list(projectId, 'model_routing_stats')
  }

  // ── Patches ───────────────────────────────────────────────────────────────

  recordPatch(patch) {
    if (!patch.patch_id) patch.patch_id = uid('patch')
    const projectId = patch.project_id || 'global'
    return this._upsert(projectId, 'patches', 'patch_id', patch)
  }

  getPatchesForRun(runId) {
    const dir = path.join(this.home, 'patches')
    if (!fs.existsSync(dir)) return []
    const results = []
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      results.push(...loadList(path.join(dir, f)).filter(p => p.run_id === runId))
    }
    return results
  }

  updatePatchStatus(patchId, status, extra = {}) {
    const dir = path.join(this.home, 'patches')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(p => p.patch_id === patchId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], status, ...extra, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  // ── Audit ─────────────────────────────────────────────────────────────────

  getAuditEventsForRun(runId) {
    const dir = path.join(this.home, 'audit')
    if (!fs.existsSync(dir)) return []
    const results = []
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      results.push(...loadList(path.join(dir, f)).filter(e => e.run_id === runId))
    }
    return results.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }

  // ── Metrics ───────────────────────────────────────────────────────────────

  getMetricsForProject(projectId, opts = {}) {
    return this._list(projectId, 'metrics').slice(0, opts.limit || 100)
  }

  // ── Skill proposals ───────────────────────────────────────────────────────

  getSkillProposals(projectId, opts = {}) {
    let list = this._list(projectId, 'skill_proposals')
    if (opts.status) list = list.filter(p => p.status === opts.status)
    return list.slice(0, opts.limit || 100)
  }

  upsertSkillProposal(proposal) {
    if (!proposal.proposal_id) proposal.proposal_id = uid('sp')
    return this._upsert(proposal.project_id, 'skill_proposals', 'proposal_id', proposal)
  }

  updateSkillProposal(proposalId, patch) {
    const dir = path.join(this.home, 'skill_proposals')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(p => p.proposal_id === proposalId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  // ── Suggestions ───────────────────────────────────────────────────────────

  getSuggestions(projectId, opts = {}) {
    let list = this._list(projectId, 'suggestions')
    if (opts.category) list = list.filter(s => s.category === opts.category)
    if (opts.status)   list = list.filter(s => s.status   === opts.status)
    return list.slice(0, opts.limit || 100)
  }

  findSuggestion(projectId, suggestionId) {
    return this._list(projectId, 'suggestions').find(s => s.suggestion_id === suggestionId) || null
  }

  upsertSuggestion(suggestion) {
    if (!suggestion.suggestion_id) suggestion.suggestion_id = uid('sug')
    return this._upsert(suggestion.project_id, 'suggestions', 'suggestion_id', suggestion)
  }

  updateSuggestion(suggestionId, patch) {
    const dir = path.join(this.home, 'suggestions')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(s => s.suggestion_id === suggestionId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  // ── Backlog ───────────────────────────────────────────────────────────────

  getBacklog(projectId, opts = {}) {
    let list = this._list(projectId, 'backlog')
    if (opts.status) list = list.filter(i => i.status === opts.status)
    if (opts.type)   list = list.filter(i => i.type   === opts.type)
    return list.slice(0, opts.limit || 200)
  }

  findBacklogItem(projectId, itemId) {
    return this._list(projectId, 'backlog').find(i => i.item_id === itemId) || null
  }

  upsertBacklogItem(item) {
    if (!item.item_id) item.item_id = uid('bl')
    return this._upsert(item.project_id, 'backlog', 'item_id', item)
  }

  updateBacklogItem(itemId, patch) {
    const dir = path.join(this.home, 'backlog')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(i => i.item_id === itemId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  deleteBacklogItem(projectId, itemId) {
    const file = this._f(projectId, 'backlog')
    const list = loadList(file).filter(i => i.item_id !== itemId)
    saveList(file, list)
    return true
  }

  // ── Cycles ────────────────────────────────────────────────────────────────

  getCycles(projectId, opts = {}) {
    let list = this._list(projectId, 'cycles')
    if (opts.status) list = list.filter(c => c.status === opts.status)
    return list.slice(0, opts.limit || 50)
  }

  findCycle(projectId, cycleId) {
    return this._list(projectId, 'cycles').find(c => c.cycle_id === cycleId) || null
  }

  upsertCycle(cycle) {
    if (!cycle.cycle_id) cycle.cycle_id = uid('cyc')
    return this._upsert(cycle.project_id, 'cycles', 'cycle_id', cycle)
  }

  updateCycle(cycleId, patch) {
    const dir = path.join(this.home, 'cycles')
    if (!fs.existsSync(dir)) return null
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue
      const file = path.join(dir, f)
      const list = loadList(file)
      const idx = list.findIndex(c => c.cycle_id === cycleId)
      if (idx < 0) continue
      list[idx] = { ...list[idx], ...patch, updated_at: nowIso() }
      saveList(file, list)
      return list[idx]
    }
    return null
  }

  // ── Roadmap ───────────────────────────────────────────────────────────────

  getRoadmap(projectId) {
    return readJson(path.join(this.home, 'roadmaps', `${projectId}.json`), { milestones: [] })
  }

  upsertRoadmap(projectId, roadmap) {
    const file = path.join(this.home, 'roadmaps', `${projectId}.json`)
    writeJson(file, { ...roadmap, updated_at: nowIso() })
    return readJson(file, {})
  }

  // ── Advisory events ───────────────────────────────────────────────────────

  getAdvisoryEvents(projectId, opts = {}) {
    let list = this._list(projectId, 'advisory_events')
    if (opts.event_type) list = list.filter(e => e.event_type === opts.event_type)
    return list.slice(0, opts.limit || 100)
  }

  upsertAdvisoryEvent(event) {
    if (!event.event_id) event.event_id = uid('adv')
    return this._upsert(event.project_id, 'advisory_events', 'event_id', event)
  }

  getAdvisoryMetrics(projectId) {
    const events = this._list(projectId, 'advisory_events')
    const byType = {}
    for (const e of events) {
      byType[e.event_type] = (byType[e.event_type] || 0) + 1
    }
    return { total: events.length, by_type: byType }
  }

  // ── Training runs (forwarded from ForgeStore) ─────────────────────────────

  upsertTrainingRun(run) {
    if (!run.training_run_id) run.training_run_id = uid('tr')
    const file = path.join(this.home, 'training', `${run.project_id}.json`)
    const data = readJson(file, { training_runs: [], model_versions: [] })
    const idx = data.training_runs.findIndex(r => r.training_run_id === run.training_run_id)
    if (idx >= 0) data.training_runs[idx] = { ...data.training_runs[idx], ...run, updated_at: nowIso() }
    else data.training_runs.unshift({ ...run, created_at: run.created_at || nowIso(), updated_at: nowIso() })
    writeJson(file, data)
    return data.training_runs.find(r => r.training_run_id === run.training_run_id)
  }

  // ── Runs (convenience wrappers so ForgeStore can delegate here) ───────────

  getRuns(projectId, opts = {}) {
    // Delegates to runs in a project directory — for when forge.js calls
    // forgeRunStore.getRuns(projectId, opts) without loading all runs
    return []  // actual runs are managed by ForgeStore.loadRuns()
  }
}

module.exports = { ForgeLearningStore }
