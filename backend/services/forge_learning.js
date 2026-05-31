'use strict'

/**
 * forge_learning.js — Phase 7 On-Policy Self-Distillation Learning
 *
 * Builds distillation records from completed runs, manages lessons,
 * promotes lessons to the memory graph, exports training datasets,
 * and scrubs secrets from learning data.
 */

const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const os = require('os')

const SECRET_PATTERNS = [
  /\b(api[_-]?key|secret|password|token|bearer|credential|private[_-]key|auth[_-]?token)\s*[=:]\s*\S+/i,
  /sk-[A-Za-z0-9]{20,}/,
  /ghp_[A-Za-z0-9]{36}/,
  /AKIA[A-Z0-9]{16}/,
]

function nowIso() {
  return new Date().toISOString()
}

function _scoreRun(run) {
  const transcript = run.final_report?.transcript || []
  const success = run.status === 'verified' || run.status === 'applied' || run.final_report?.success === true
  const debugCount = transcript.reduce((acc, t) => acc + (Array.isArray(t.debug) ? t.debug.length : 0), 0)
  const iterations = transcript.length || 1
  const secBlocked = transcript.some(t => t.security?.output?.verdict === 'block')
  const revBlocked = transcript.some(t => t.reviewer?.output?.verdict === 'block')

  let score = success ? 0.8 : 0.2
  if (iterations <= 1) score += 0.1
  if (debugCount === 0) score += 0.05
  if (secBlocked || revBlocked) score -= 0.2
  return Math.max(0, Math.min(1, score))
}

function _scoreLabel(score) {
  if (score >= 0.75) return 'high'
  if (score >= 0.45) return 'medium'
  return 'low'
}

function _extractLessons(run, project) {
  const lessons = []
  const transcript = run.final_report?.transcript || []
  const success = run.final_report?.success === true

  const applied = transcript.flatMap(t =>
    (t.files_written || []).filter(f => f.ok).map(f => f.path)
  )
  for (const fp of [...new Set(applied)].slice(0, 5)) {
    lessons.push({
      lesson_id: `les-${crypto.randomUUID()}`,
      run_id: run.id,
      project_id: project.id,
      category: 'file_pattern',
      lesson: `${success ? 'Successfully modified' : 'Attempted to modify'} ${fp} for goal: ${(run.goal || '').slice(0, 80)}`,
      confidence: success ? 'high' : 'low',
      evidence: { files: applied, success },
      promoted_to_memory: false,
      created_at: nowIso(),
    })
  }

  const revFindings = transcript.flatMap(t => t.reviewer?.output?.findings || [])
  for (const f of revFindings.slice(0, 3)) {
    const text = typeof f === 'string' ? f : (f.message || JSON.stringify(f))
    lessons.push({
      lesson_id: `les-${crypto.randomUUID()}`,
      run_id: run.id,
      project_id: project.id,
      category: 'architecture',
      lesson: text.slice(0, 300),
      confidence: 'medium',
      evidence: { reviewer_verdict: 'finding', run_goal: (run.goal || '').slice(0, 80) },
      promoted_to_memory: false,
      created_at: nowIso(),
    })
  }

  const failures = transcript.flatMap(t => t.tester?.output?.failures || [])
  for (const f of failures.slice(0, 2)) {
    lessons.push({
      lesson_id: `les-${crypto.randomUUID()}`,
      run_id: run.id,
      project_id: project.id,
      category: 'risk',
      lesson: `Command failed: ${f.command || ''} — ${(f.output || '').slice(0, 150)}`,
      confidence: 'medium',
      evidence: { command: f.command, output: (f.output || '').slice(0, 300) },
      promoted_to_memory: false,
      created_at: nowIso(),
    })
  }

  return lessons
}

function _extractPreferencePairs(run, project) {
  const success = run.final_report?.success === true
  return (run.actions || [])
    .filter(a => a.type === 'write_file' || a.type === 'file_update')
    .slice(0, 4)
    .map(a => ({
      pair_id: `pp-${crypto.randomUUID()}`,
      run_id: run.id,
      project_id: project.id,
      goal: (run.goal || '').slice(0, 200),
      chosen: a.proposed_content || a.content || '',
      rejected: '',
      chosen_outcome: success ? 'pass' : 'fail',
      label: success ? 1 : 0,
      confidence: success ? 'high' : 'low',
      approved_for_training: false,
      created_at: nowIso(),
    }))
}

function _extractEvalCases(run, project) {
  const success = run.final_report?.success === true
  return [{
    eval_id: `ev-${crypto.randomUUID()}`,
    run_id: run.id,
    project_id: project.id,
    eval_type: 'run_outcome',
    input: { goal: (run.goal || '').slice(0, 200), stack: run.context_pack?.project?.package_type || 'unknown' },
    expected_output: success ? 'pass' : 'fail',
    actual_output: success ? 'pass' : 'fail',
    passed: true,
    created_at: nowIso(),
  }]
}

/**
 * Build a distillation record from a completed run.
 * Returns: { distillation_id, run_id, project_id, confidence, scores, lessons, preference_pairs, eval_cases, skill_proposals, created_at }
 */
function buildDistillationRecord(run, project) {
  const score = _scoreRun(run)
  const success = run.final_report?.success === true || run.status === 'verified'
  return {
    distillation_id: `dis-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
    run_id: run.id,
    project_id: project.id,
    goal: (run.goal || '').slice(0, 300),
    confidence: _scoreLabel(score),
    scores: {
      overall: score,
      is_positive: success,
      iterations: (run.final_report?.transcript || []).length,
    },
    lessons: _extractLessons(run, project),
    preference_pairs: _extractPreferencePairs(run, project),
    eval_cases: _extractEvalCases(run, project),
    skill_proposals: [],
    created_at: nowIso(),
  }
}

/**
 * Get a summary of learning activity for a project.
 */
function getLearningSummary(projectId, forgeRunStore) {
  try {
    const records = forgeRunStore.getDistillationRecords ? forgeRunStore.getDistillationRecords(projectId, 100) : []
    const lessons = forgeRunStore.getLessons ? forgeRunStore.getLessons(projectId, { limit: 200 }) : []
    const positive = records.filter(r => r.scores?.is_positive).length
    const total = records.length
    const avgConf = total > 0 ? records.reduce((s, r) => s + (r.scores?.overall || 0), 0) / total : 0
    return {
      total_records: total,
      positive_records: positive,
      negative_records: total - positive,
      total_lessons: lessons.length,
      avg_confidence: Math.round(avgConf * 100) / 100,
      promoted_lessons: lessons.filter(l => l.promoted_to_memory).length,
    }
  } catch {
    return { total_records: 0, positive_records: 0, negative_records: 0, total_lessons: 0, avg_confidence: 0, promoted_lessons: 0 }
  }
}

/**
 * Promote a lesson into the memory graph (as a memory fact).
 * Returns: { ok, error? }
 */
function promoteLesson(lesson, forgeRunStore) {
  if (!lesson?.lesson_id) return { ok: false, error: 'invalid lesson' }
  if (lesson.promoted_to_memory) return { ok: false, error: 'already promoted' }
  try {
    if (forgeRunStore.upsertMemoryFact) {
      forgeRunStore.upsertMemoryFact({
        memory_id: crypto.randomUUID(),
        project_id: lesson.project_id,
        source_run_id: lesson.run_id,
        category: lesson.category || 'lesson',
        fact: lesson.lesson,
        evidence: Array.isArray(lesson.evidence) ? lesson.evidence : [lesson.evidence],
        confidence: lesson.confidence || 'medium',
        usage_count: 1,
        last_used_at: nowIso(),
        created_at: nowIso(),
        updated_at: nowIso(),
      })
    }
    if (forgeRunStore.upsertLesson) {
      forgeRunStore.upsertLesson({ ...lesson, promoted_to_memory: true, updated_at: nowIso() })
    }
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
}

/**
 * Export a learning dataset to disk as JSONL.
 * Returns: { dataset_id, record_count, export_path, dataset_type, created_at }
 */
async function exportLearningDataset(projectId, opts = {}, forgeRunStore, forgeHome) {
  const {
    min_confidence = 'low',
    include_positive = true,
    include_negative = true,
    only_human_approved = false,
    dataset_type = 'jsonl',
    name = `export-${Date.now().toString(36)}`,
  } = opts

  const CONF_RANK = { low: 0, medium: 1, high: 2 }
  const minRank = CONF_RANK[min_confidence] ?? 0
  const records = forgeRunStore.getDistillationRecords ? forgeRunStore.getDistillationRecords(projectId, 500) : []

  let lines = []
  const datasetId = `ds-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`

  if (dataset_type === 'preference_jsonl') {
    const pairs = forgeRunStore.getPreferencePairs ? forgeRunStore.getPreferencePairs(projectId, 500) : []
    const filtered = only_human_approved ? pairs.filter(p => p.approved_for_training) : pairs
    lines = filtered.map(p => JSON.stringify({ pair_id: p.pair_id, goal: p.goal, chosen: p.chosen, rejected: p.rejected, label: p.label }))
  } else if (dataset_type === 'eval_jsonl') {
    const cases = forgeRunStore.getEvalCases ? forgeRunStore.getEvalCases(projectId, { limit: 500 }) : []
    lines = cases.map(c => JSON.stringify({ eval_id: c.eval_id, input: c.input, expected: c.expected_output, actual: c.actual_output, passed: c.passed }))
  } else {
    const examples = records.filter(r => {
      const rank = CONF_RANK[r.confidence] ?? 0
      if (rank < minRank) return false
      const isPos = r.scores?.is_positive
      if (isPos && !include_positive) return false
      if (!isPos && !include_negative) return false
      return true
    })
    lines = examples.map(r => JSON.stringify({
      distillation_id: r.distillation_id,
      goal: r.goal,
      is_positive: r.scores?.is_positive || false,
      confidence: r.confidence,
      lessons: (r.lessons || []).map(l => l.lesson),
    }))
  }

  const FORGE_HOME_RESOLVED = forgeHome || path.join(os.homedir(), '.ai-employee', 'state', 'forge')
  const exportDir = path.join(FORGE_HOME_RESOLVED, 'learning', projectId)
  fs.mkdirSync(exportDir, { recursive: true })
  const exportPath = path.join(exportDir, `${name}-${datasetId}.jsonl`)
  fs.writeFileSync(exportPath, lines.join('\n') + (lines.length ? '\n' : ''), { mode: 0o600 })

  const datasetRecord = { dataset_id: datasetId, project_id: projectId, name, dataset_type, record_count: lines.length, export_path: exportPath, created_at: nowIso() }
  if (forgeRunStore.upsertLearningDataset) forgeRunStore.upsertLearningDataset(datasetRecord)
  return datasetRecord
}

/**
 * Scrub secrets from an arbitrary object (deep). Returns a scrubbed copy.
 */
function scrubSecretsFromLearningData(data) {
  if (typeof data === 'string') {
    let s = data
    for (const re of SECRET_PATTERNS) s = s.replace(re, '[REDACTED]')
    return s
  }
  if (Array.isArray(data)) return data.map(scrubSecretsFromLearningData)
  if (data && typeof data === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(data)) {
      out[k] = /secret|password|token|api[_-]?key|credential|private/i.test(k)
        ? '[REDACTED]'
        : scrubSecretsFromLearningData(v)
    }
    return out
  }
  return data
}

module.exports = {
  buildDistillationRecord,
  getLearningSummary,
  promoteLesson,
  exportLearningDataset,
  scrubSecretsFromLearningData,
}
