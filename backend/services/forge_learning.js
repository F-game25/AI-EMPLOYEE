'use strict'
/**
 * Phase 7 — On-Policy Self-Distillation Learning Service
 *
 * Captures run trajectories, scores quality, extracts lessons, generates
 * preference pairs and evaluation cases from real AscendForge runs.
 *
 * Safety invariants:
 *  - Failed runs NEVER create positive training examples.
 *  - Rejected patches become negative examples only.
 *  - Secrets are scrubbed before any write.
 *  - Skill changes are proposals only — no automatic file mutations.
 *  - approved_for_training defaults to false on all generated data.
 */

const crypto = require('crypto')
const fs = require('fs')
const path = require('path')
const os = require('os')

// ── Secret scrubbing ──────────────────────────────────────────────────────────

const SECRET_PATTERNS = [
  // API keys / tokens
  /(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|bearer|auth)[^\s=:]*\s*[:=]\s*["']?([A-Za-z0-9+/=._\-]{16,})["']?/gi,
  // JWT format
  /eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+/g,
  // SK-ant / Anthropic keys
  /sk-ant-[A-Za-z0-9_\-]{20,}/g,
  // Generic long hex secrets (32+ chars)
  /\b[A-Fa-f0-9]{32,}\b/g,
  // AWS-style access keys
  /(?:AKIA|ASIA)[A-Z0-9]{16}/g,
  // Private key PEM blocks
  /-----BEGIN [A-Z ]* PRIVATE KEY-----[\s\S]+?-----END [A-Z ]* PRIVATE KEY-----/g,
  // Cookie / session values
  /(?:cookie|session|csrf)[^\s=:]*\s*[:=]\s*["']?([A-Za-z0-9+/=._\-]{12,})["']?/gi,
  // Authorization headers — capture the full header line
  /authorization\s*:\s*\S+\s*\S*/gi,
  // Bearer tokens (free-standing)
  /bearer\s+[A-Za-z0-9\-._~+\/]+=*/gi,
]

const ENV_VALUE_PATTERN = /^([A-Z][A-Z0-9_]+=).+$/m

function scrubString(str) {
  if (typeof str !== 'string') return str
  let out = str
  // Standalone provider-key redaction first — these are unambiguous secret
  // shapes that must never survive, independent of the generic patterns below.
  out = out.replace(/sk-ant-[A-Za-z0-9_-]{16,}/gi, '[REDACTED]')
  out = out.replace(/sk-[A-Za-z0-9]{20,}/g, '[REDACTED]')               // OpenAI-style
  out = out.replace(/gh[pousr]_[A-Za-z0-9]{20,}/g, '[REDACTED]')        // GitHub tokens
  out = out.replace(/eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[REDACTED]') // JWT
  for (const re of SECRET_PATTERNS) {
    out = out.replace(re, (match, cap) => cap
      ? match.replace(cap, '[REDACTED]')
      : '[REDACTED]')
  }
  // Redact .env-style lines: keep the key name, replace value
  out = out.replace(/^([A-Z][A-Z0-9_]+=).+$/gm, '$1[REDACTED]')
  return out
}

function scrubSecretsFromLearningData(data) {
  if (data === null || data === undefined) return data
  if (typeof data === 'string') return scrubString(data)
  if (typeof data === 'number' || typeof data === 'boolean') return data
  if (Array.isArray(data)) return data.map(scrubSecretsFromLearningData)
  if (typeof data === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(data)) {
      // Drop keys that look like they hold secret values
      const keyLower = k.toLowerCase()
      if (/^(password|passwd|secret|token|api_key|apikey|bearer|auth_token|private_key|access_key|session_id|cookie)$/i.test(keyLower)) {
        out[k] = '[REDACTED]'
      } else {
        out[k] = scrubSecretsFromLearningData(v)
      }
    }
    return out
  }
  return data
}

// ── Scoring ───────────────────────────────────────────────────────────────────

function scoreTrajectory(run) {
  if (!run) return { task_success: 0, test_delta: 0, security_score: 0, reviewer_score: 0, human_approval_score: 0, regression_score: 0, efficiency_score: 0, autopilot_score: 0, learning_value: 0, is_positive: false, confidence: 'low' }

  const status = run.status || ''
  const finalReport = run.final_report || {}
  const testResults = Array.isArray(run.test_results) ? run.test_results : []
  const patches = Array.isArray(run.patches) ? run.patches : []
  const actions = Array.isArray(run.actions) ? run.actions : []

  // task_success: 1 = completed/verified, 0.5 = partial, 0 = failed/blocked
  const task_success = ['verified', 'applied', 'completed'].includes(status) ? 1
    : status === 'waiting_approval' ? 0.5
    : ['failed', 'verify_failed', 'error'].includes(status) ? 0
    : 0.3

  // test_delta: last test result vs first
  const firstTest = testResults[0]
  const lastTest = testResults[testResults.length - 1]
  const test_delta = lastTest?.all_passed ? 1
    : lastTest && !firstTest?.all_passed && !lastTest.all_passed ? 0
    : lastTest?.all_passed === false && firstTest?.all_passed === true ? -1
    : 0

  // security_score: 1 = no blocks, 0.5 = warnings only, 0 = blocked
  const secReview = run.review?.security_findings || finalReport?.security_findings || []
  const secBlocked = actions.some(a => a.status === 'blocked' && a.policy_decision?.reason?.includes('security'))
  const secCritical = secReview.some(f => ['critical', 'high'].includes((f.severity || '').toLowerCase()))
  const security_score = secBlocked || secCritical ? 0 : secReview.length > 0 ? 0.5 : 1

  // reviewer_score: 1 = approved, 0.5 = warnings, 0 = blocked
  const reviewVerdict = run.review?.status || ''
  const reviewerFindings = run.review?.reviewer_findings || []
  const reviewer_score = reviewVerdict === 'verification_passed' ? 1
    : reviewVerdict.includes('block') ? 0
    : reviewerFindings.length > 0 ? 0.6 : 0.8

  // human_approval_score: 1 = no gate needed, 0.7 = gate triggered + resolved, 0 = gate pending
  const approvals = run.approvals || []
  const human_approval_score = approvals.length === 0 ? 1
    : approvals.some(a => a.approved) ? 0.7
    : status === 'waiting_approval' ? 0.3 : 0.5

  // regression_score: whether run introduced regressions
  const regressionData = finalReport?.regression_delta || {}
  const hasRegression = regressionData.had_regression === true
  const regression_score = hasRegression ? 0.2 : 1

  // efficiency_score: fewer iterations is better
  const maxIters = run.max_iterations || 3
  const actualIters = Array.isArray(run.transcript) ? run.transcript.length
    : (lastTest?.iteration || testResults.length || maxIters)
  const efficiency_score = Math.max(0, 1 - (actualIters - 1) / Math.max(maxIters - 1, 1))

  // autopilot_score: if linked to autopilot, did backlog item complete?
  const linkedBacklog = run.linked_backlog_id
  const autopilot_score = linkedBacklog ? task_success : 1

  // learning_value: runs with rich trajectories teach more
  const hasTranscript = Array.isArray(run.transcript) && run.transcript.length > 0
  const hasReport = !!run.final_report
  const hasPatches = patches.length > 0
  const learning_value = (hasTranscript ? 0.4 : 0) + (hasReport ? 0.3 : 0) + (hasPatches ? 0.3 : 0)

  const composite = (task_success * 0.3) + (test_delta * 0.1) + (security_score * 0.15) +
    (reviewer_score * 0.15) + (regression_score * 0.1) + (efficiency_score * 0.1) +
    (human_approval_score * 0.1)

  const is_positive = task_success === 1 && security_score > 0 && reviewer_score > 0 && regression_score === 1

  const confidence = composite >= 0.8 && is_positive ? 'high'
    : composite >= 0.5 ? 'medium' : 'low'

  return {
    task_success, test_delta, security_score, reviewer_score, human_approval_score,
    regression_score, efficiency_score, autopilot_score, learning_value,
    composite: Math.round(composite * 100) / 100,
    is_positive, confidence,
  }
}

// ── Lesson extraction ─────────────────────────────────────────────────────────

const LESSON_CATEGORIES = [
  'planning', 'coding', 'testing', 'debugging', 'security', 'reviewing',
  'autopilot', 'model_routing', 'memory', 'skills', 'ui', 'backend', 'architecture',
]

function extractLessons(run, scores) {
  if (!run) return []
  const lessons = []
  const now = new Date().toISOString()
  const baseEvidence = { run_id: run.id || run.run_id, goal: (run.goal || '').slice(0, 120), status: run.status }

  function mkLesson(category, lesson, evidence = {}, confidence = 'low') {
    if (!LESSON_CATEGORIES.includes(category)) category = 'planning'
    return {
      lesson_id: `les-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
      project_id: run.project_id,
      run_id: run.id || run.run_id,
      category, lesson, confidence,
      evidence: scrubSecretsFromLearningData({ ...baseEvidence, ...evidence }),
      created_at: now,
    }
  }

  // Planning lessons
  const plan = run.plan || {}
  if (plan.risk_level) {
    if (plan.risk_level === 'safe' && scores.task_success === 1) {
      lessons.push(mkLesson('planning', `Goal classified as "safe" risk and completed successfully: "${(run.goal || '').slice(0, 80)}"`, { risk: plan.risk_level, skills: plan.selected_skills?.map(s => s.id) }, 'medium'))
    } else if (plan.risk_level === 'dangerous' && scores.task_success < 1) {
      lessons.push(mkLesson('planning', `Dangerous-risk goal failed — review required before retrying similar goals`, { risk: plan.risk_level }, 'medium'))
    }
  }

  // Coding lessons from patches
  const patches = Array.isArray(run.patches) ? run.patches : []
  const appliedPatches = patches.filter(p => p.status === 'applied')
  const blockedPatches = patches.filter(p => p.status === 'blocked')
  const rejectedPatches = patches.filter(p => p.status === 'rejected')
  if (blockedPatches.length > 0) {
    const files = [...new Set(blockedPatches.map(p => p.file_path).filter(Boolean))]
    lessons.push(mkLesson('coding', `${blockedPatches.length} patch(es) were policy-blocked. Files: ${files.slice(0, 3).join(', ')}`, { files, count: blockedPatches.length }, 'medium'))
  }
  if (rejectedPatches.length > 0 && scores.task_success === 1) {
    lessons.push(mkLesson('coding', `${rejectedPatches.length} patch(es) rejected but run still succeeded — agent adapted correctly`, { count: rejectedPatches.length }, 'medium'))
  }

  // Testing lessons
  const testResults = Array.isArray(run.test_results) ? run.test_results : []
  if (testResults.length > 1) {
    const firstPassed = testResults[0]?.all_passed
    const lastPassed = testResults[testResults.length - 1]?.all_passed
    if (!firstPassed && lastPassed) {
      lessons.push(mkLesson('testing', `Tests failed on first attempt then passed after ${testResults.length - 1} debug iteration(s)`, { iterations: testResults.length }, 'medium'))
    } else if (firstPassed && !lastPassed) {
      lessons.push(mkLesson('testing', `Tests regressed during run — debug loop did not recover`, { iterations: testResults.length }, 'low'))
    }
  }
  if (scores.regression_score < 1) {
    lessons.push(mkLesson('testing', `Run introduced test regressions — regression comparison detected a decline`, { regression: true }, 'high'))
  }

  // Debug lessons
  const transcript = Array.isArray(run.transcript) ? run.transcript : []
  const debugIters = transcript.filter(t => t.debug && t.debug.length > 0)
  if (debugIters.length > 0 && scores.task_success === 1) {
    lessons.push(mkLesson('debugging', `Debug loop ran ${debugIters.length} time(s) and ultimately succeeded`, { debug_iters: debugIters.length }, 'medium'))
  } else if (debugIters.length >= 2 && scores.task_success < 1) {
    lessons.push(mkLesson('debugging', `Debug loop exhausted (${debugIters.length} attempts) without recovery — may need different strategy or smaller goal`, { debug_iters: debugIters.length }, 'medium'))
  }

  // Security lessons
  const secFindings = run.review?.security_findings || run.final_report?.security_findings || []
  if (secFindings.length > 0) {
    const sevs = secFindings.map(f => f.severity || 'medium')
    const critical = sevs.filter(s => s === 'critical').length
    lessons.push(mkLesson('security', `Security agent found ${secFindings.length} finding(s)${critical > 0 ? `, including ${critical} critical` : ''}`, { count: secFindings.length, severities: sevs }, scores.security_score === 0 ? 'high' : 'medium'))
  }
  if (scores.security_score === 0) {
    lessons.push(mkLesson('security', `Security gate blocked this run — similar goals may need security review before execution`, {}, 'high'))
  }

  // Reviewer lessons
  const reviewFindings = run.review?.reviewer_findings || []
  if (reviewFindings.length > 0 && scores.reviewer_score > 0) {
    lessons.push(mkLesson('reviewing', `Reviewer raised ${reviewFindings.length} finding(s) but allowed the run to proceed`, { count: reviewFindings.length }, 'medium'))
  }

  // Autopilot lessons
  if (run.linked_backlog_id) {
    const outcome = scores.task_success === 1 ? 'completed' : scores.task_success === 0 ? 'failed' : 'partial'
    lessons.push(mkLesson('autopilot', `Autopilot backlog item ${outcome} for goal: "${(run.goal || '').slice(0, 60)}"`, { backlog_id: run.linked_backlog_id, outcome }, outcome === 'completed' ? 'medium' : 'low'))
  }

  // Model routing lessons
  const modelLogs = Array.isArray(run.model_routing_logs) ? run.model_routing_logs : []
  const fallbacks = modelLogs.filter(l => l.fallback_model_id)
  if (fallbacks.length > 0) {
    lessons.push(mkLesson('model_routing', `Model routing used ${fallbacks.length} fallback(s) during this run`, { fallbacks: fallbacks.map(f => ({ stage: f.stage, fallback: f.fallback_model_id, reason: f.failure_reason })) }, 'medium'))
  }

  // Memory lessons
  const memFacts = Array.isArray(run.memory_used) ? run.memory_used : []
  if (memFacts.length > 0) {
    lessons.push(mkLesson('memory', `Run retrieved ${memFacts.length} memory fact(s) — context augmentation active`, { count: memFacts.length }, 'low'))
  }

  // Positive overall lesson for successful runs
  if (scores.is_positive) {
    const filesModified = appliedPatches.map(p => p.file_path).filter(Boolean).slice(0, 5)
    lessons.push(mkLesson('coding', `Run completed successfully — files modified: ${filesModified.join(', ') || 'none'}`, { files: filesModified, iterations: transcript.length }, 'high'))
  }

  return lessons
}

// ── Preference pair generation ────────────────────────────────────────────────

function createPreferencePairs(run, scores) {
  if (!run) return []
  const pairs = []
  const now = new Date().toISOString()
  const runId = run.id || run.run_id

  function mkPair(context, preferred, rejected, reason, confidence = 'low') {
    return {
      pair_id: `pair-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
      project_id: run.project_id,
      run_id: runId,
      context: scrubSecretsFromLearningData(context),
      preferred: scrubSecretsFromLearningData(preferred),
      rejected: scrubSecretsFromLearningData(rejected),
      reason, confidence,
      approved_for_training: false,
      created_at: now,
    }
  }

  const patches = Array.isArray(run.patches) ? run.patches : []
  const applied = patches.filter(p => p.status === 'applied')
  const rejected = patches.filter(p => p.status === 'rejected')
  const blocked = patches.filter(p => p.status === 'blocked')

  // approved_patch vs rejected_patch — generate regardless of run outcome
  for (const ap of applied.slice(0, 3)) {
    const rp = rejected.find(r => r.file_path === ap.file_path) || rejected[0]
    if (rp) {
      pairs.push(mkPair(
        { goal: run.goal, file: ap.file_path },
        { action: 'apply', diff: (ap.unified_diff || '').slice(0, 500), file: ap.file_path },
        { action: 'apply', diff: (rp.unified_diff || '').slice(0, 500), file: rp.file_path },
        'Applied patch passed all checks; rejected patch did not',
        'medium',
      ))
    }
  }

  // safe_command vs unsafe_command (blocked policy actions)
  for (const bp of blocked.slice(0, 2)) {
    const ap = applied[0]
    if (ap) {
      pairs.push(mkPair(
        { goal: run.goal },
        { action: 'file_update', file: ap.file_path, risk_level: ap.risk_level || 'low' },
        { action: bp.action_type || 'blocked', file: bp.file_path, reason: 'policy blocked' },
        'Policy-allowed action preferred over blocked action',
        'medium',
      ))
    }
  }

  // good plan vs bad plan — when first iter failed but last succeeded
  const transcript = Array.isArray(run.transcript) ? run.transcript : []
  if (transcript.length > 1 && scores.is_positive) {
    const firstIter = transcript[0]
    const lastIter = transcript[transcript.length - 1]
    if (!firstIter?.verify?.all_passed && lastIter?.verify?.all_passed) {
      pairs.push(mkPair(
        { goal: run.goal, project_stack: run.context_pack?.stack },
        { planner_output: lastIter.planner?.output, iteration: lastIter.iteration },
        { planner_output: firstIter.planner?.output, iteration: firstIter.iteration },
        'Final planner iteration passed tests; first iteration failed',
        'medium',
      ))
    }
  }

  // failed run creates only negative examples (never preferred)
  if (!scores.is_positive && scores.task_success === 0 && run.final_report) {
    pairs.push(mkPair(
      { goal: run.goal },
      { strategy: 'decompose_goal', rationale: 'Goal was too large or risky for single run' },
      { strategy: 'execute_as_is', outcome: 'failed', run_id: runId },
      'Failed runs indicate the current strategy should not be repeated without refinement',
      'low',
    ))
  }

  return pairs
}

// ── Skill update proposals ────────────────────────────────────────────────────

function createSkillUpdateProposals(run, scores) {
  if (!run) return []
  const proposals = []
  const now = new Date().toISOString()
  const runId = run.id || run.run_id

  function mkProposal(skillId, change, reason, evidence, confidence = 'low') {
    return {
      proposal_id: `prop-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
      project_id: run.project_id,
      run_id: runId,
      skill_id: skillId,
      proposed_change: scrubSecretsFromLearningData(change),
      reason, confidence,
      evidence: scrubSecretsFromLearningData(evidence),
      status: 'NEW',
      created_at: now,
    }
  }

  const transcript = Array.isArray(run.transcript) ? run.transcript : []
  const secFindings = run.review?.security_findings || run.final_report?.security_findings || []
  const reviewFindings = run.review?.reviewer_findings || []
  const patches = Array.isArray(run.patches) ? run.patches : []

  // Repeated debug failure → update debugging skill
  const debugIters = transcript.filter(t => t.debug?.length > 0)
  if (debugIters.length >= 2 && scores.task_success === 0) {
    proposals.push(mkProposal(
      'debug-agent',
      { checklist_addition: 'Verify test command availability before iterating', failure_mode: 'debug loop exhaustion without recovery' },
      `Debug loop ran ${debugIters.length} times without recovery on this goal`,
      { goal: run.goal, debug_count: debugIters.length, run_id: runId },
      'medium',
    ))
  }

  // Security findings → update security skill
  if (secFindings.filter(f => ['critical', 'high'].includes((f.severity || '').toLowerCase())).length > 0) {
    proposals.push(mkProposal(
      'security-agent',
      { checklist_addition: `Check for ${secFindings.map(f => f.type || f.rule || 'unknown').join(', ')} patterns before staging patches` },
      `Run produced ${secFindings.length} security finding(s)`,
      { findings: secFindings.map(f => ({ severity: f.severity, type: f.type || f.rule })), run_id: runId },
      'medium',
    ))
  }

  // Reviewer findings → update reviewer skill
  if (reviewFindings.length >= 2) {
    proposals.push(mkProposal(
      'reviewer-agent',
      { checklist_addition: 'Pre-check for common issues: ' + reviewFindings.slice(0, 3).map(f => f.description || f.message || '').join('; ') },
      `Reviewer raised ${reviewFindings.length} findings — could be caught earlier`,
      { findings_count: reviewFindings.length, run_id: runId },
      'low',
    ))
  }

  // Blocked patches → update policy skill
  const blocked = patches.filter(p => p.status === 'blocked')
  if (blocked.length > 0 && scores.task_success === 1) {
    const protectedFiles = [...new Set(blocked.map(p => p.file_path).filter(Boolean))]
    proposals.push(mkProposal(
      'planner-agent',
      { rule_addition: `Avoid targeting protected files: ${protectedFiles.slice(0, 5).join(', ')}`, verification_command: 'Check PROTECTED_PATH_PATTERNS before selecting files' },
      `${blocked.length} action(s) were policy-blocked; planner should avoid these paths`,
      { files: protectedFiles, run_id: runId },
      'medium',
    ))
  }

  // Successful run with model fallbacks → update model routing skill
  const modelLogs = Array.isArray(run.model_routing_logs) ? run.model_routing_logs : []
  const fallbacks = modelLogs.filter(l => l.fallback_model_id)
  if (fallbacks.length > 0 && scores.is_positive) {
    proposals.push(mkProposal(
      'model-router',
      { rule_addition: `Prefer ${fallbacks.map(f => f.fallback_model_id).join(', ')} for ${fallbacks.map(f => f.stage).join(', ')} stages when primary model fails` },
      `Fallback models succeeded where primary failed`,
      { fallbacks: fallbacks.map(f => ({ stage: f.stage, model: f.fallback_model_id, reason: f.failure_reason })), run_id: runId },
      'medium',
    ))
  }

  return proposals
}

// ── Evaluation case generation ────────────────────────────────────────────────

const EVAL_TYPES = ['planner_eval', 'decomposer_eval', 'risk_classifier_eval', 'command_safety_eval', 'reviewer_eval', 'model_router_eval', 'skill_selection_eval', 'autopilot_eval']

function createEvaluationCases(run, scores) {
  if (!run) return []
  const cases = []
  const now = new Date().toISOString()
  const runId = run.id || run.run_id
  const projectId = run.project_id
  const goal = run.goal || ''
  const stack = run.context_pack?.stack || {}
  const plan = run.plan || {}

  function mkCase(evalType, input, expected, negativeCase, confidence = 'low') {
    if (!EVAL_TYPES.includes(evalType)) evalType = 'planner_eval'
    return {
      eval_id: `eval-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
      project_id: projectId,
      run_id: runId,
      eval_type: evalType,
      input: scrubSecretsFromLearningData(input),
      expected: scrubSecretsFromLearningData(expected),
      negative_case: scrubSecretsFromLearningData(negativeCase),
      source: 'run',
      confidence,
      created_at: now,
    }
  }

  // planner_eval: from successful run
  if (scores.is_positive && plan.risk_level) {
    cases.push(mkCase(
      'planner_eval',
      { goal, stack, autonomy_level: run.autonomy_level },
      {
        risk_level: plan.risk_level,
        selected_skills: (plan.selected_skills || []).map(s => s.id),
        required_approvals: plan.required_approvals || [],
      },
      { mistake: 'Selecting dangerous-risk actions for a safe goal' },
      'medium',
    ))
  }

  // risk_classifier_eval: from blocked patches
  const patches = Array.isArray(run.patches) ? run.patches : []
  const blocked = patches.filter(p => p.status === 'blocked')
  for (const bp of blocked.slice(0, 2)) {
    cases.push(mkCase(
      'risk_classifier_eval',
      { file_path: bp.file_path, action_type: bp.action_type, goal },
      { classification: 'blocked', reason: 'protected path or unsafe action' },
      { mistake: `Allowing action on ${bp.file_path} without policy approval` },
      'medium',
    ))
  }

  // command_safety_eval: from security findings
  const secFindings = run.review?.security_findings || run.final_report?.security_findings || []
  if (secFindings.length > 0) {
    cases.push(mkCase(
      'command_safety_eval',
      { goal, security_findings_count: secFindings.length },
      { verdict: scores.security_score === 0 ? 'block' : 'warn', findings: secFindings.slice(0, 3).map(f => ({ severity: f.severity, type: f.type || f.rule })) },
      { mistake: 'Ignoring security findings and proceeding with run' },
      'medium',
    ))
  }

  // reviewer_eval: from review outcome
  const reviewFindings = run.review?.reviewer_findings || []
  if (reviewFindings.length > 0 || scores.reviewer_score === 1) {
    cases.push(mkCase(
      'reviewer_eval',
      { goal, patches_count: patches.length, reviewer_findings_count: reviewFindings.length },
      { verdict: scores.reviewer_score === 0 ? 'block' : scores.reviewer_score < 0.8 ? 'warn' : 'approve' },
      { mistake: 'Approving a run with critical reviewer findings' },
      scores.reviewer_score === 1 ? 'medium' : 'low',
    ))
  }

  // model_router_eval: from model routing logs
  const modelLogs = Array.isArray(run.model_routing_logs) ? run.model_routing_logs : []
  if (modelLogs.length > 0) {
    const byStage = {}
    for (const l of modelLogs) { if (l.stage) byStage[l.stage] = l.selected_model_id }
    cases.push(mkCase(
      'model_router_eval',
      { goal, stack, stages: Object.keys(byStage) },
      { routing: byStage },
      { mistake: 'Routing a large-context planning task to a small model' },
      'low',
    ))
  }

  // autopilot_eval: from autopilot runs
  if (run.linked_backlog_id) {
    cases.push(mkCase(
      'autopilot_eval',
      { goal, linked_backlog_id: run.linked_backlog_id, consecutive_fails: run.autopilot_context?.consecutiveFails || 0 },
      { expected_outcome: scores.task_success === 1 ? 'complete_item' : 'mark_failed', pause_on_approval: true },
      { mistake: 'Continuing autopilot after 3 consecutive failures' },
      'medium',
    ))
  }

  // Negative case from failed run
  if (scores.task_success === 0 && !scores.is_positive) {
    cases.push(mkCase(
      'planner_eval',
      { goal, stack },
      { risk_level: plan.risk_level || 'dangerous', should_decompose: true, note: 'This goal failed — consider decomposing' },
      { mistake: `Executing goal "${goal.slice(0, 60)}" without decomposition or approval` },
      'low',
    ))
  }

  return cases
}

// ── Trajectory summary ────────────────────────────────────────────────────────

function buildTrajectorySummary(run) {
  const transcript = Array.isArray(run.transcript) ? run.transcript : []
  const patches = Array.isArray(run.patches) ? run.patches : []
  return {
    iterations: transcript.length,
    files_touched: [...new Set(patches.map(p => p.file_path).filter(Boolean))],
    patches_applied: patches.filter(p => p.status === 'applied').length,
    patches_blocked: patches.filter(p => p.status === 'blocked').length,
    patches_rejected: patches.filter(p => p.status === 'rejected').length,
    debug_used: transcript.some(t => t.debug?.length > 0),
    security_run: transcript.some(t => t.security),
    reviewer_run: transcript.some(t => t.reviewer),
    agent_stages: transcript.map(t => ({
      iter: t.iteration,
      planner_ok: !!t.planner?.output,
      coder_ok: !!t.coder?.output,
      tester_pass: t.verify?.all_passed,
      security_verdict: t.security?.output?.verdict,
      reviewer_verdict: t.reviewer?.output?.verdict,
    })),
  }
}

function buildOutcomeSummary(run, scores) {
  return {
    final_status: run.status,
    success: scores.is_positive,
    composite_score: scores.composite,
    confidence: scores.confidence,
    final_report_summary: run.final_report?.summary || null,
    security_blocked: scores.security_score === 0,
    reviewer_blocked: scores.reviewer_score === 0,
    had_regression: scores.regression_score < 1,
    linked_backlog_id: run.linked_backlog_id || null,
    workspace_cleaned: run.final_report?.workspace_cleaned || false,
  }
}

// ── Main distillation builder ─────────────────────────────────────────────────

function buildDistillationRecord(run, project) {
  if (!run) throw new Error('run is required')
  const runId = run.id || run.run_id
  const now = new Date().toISOString()
  const scores = scoreTrajectory(run)
  const lessons = extractLessons(run, scores)
  const preferencePairs = createPreferencePairs(run, scores)
  const skillProposals = createSkillUpdateProposals(run, scores)
  const evalCases = createEvaluationCases(run, scores)

  const stack = {
    ...(run.context_pack?.stack || {}),
    project_id: run.project_id,
    root_path: project?.root_path ? '[PROJECT_ROOT]' : undefined,
  }

  const rec = {
    distill_id: `dis-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
    project_id: run.project_id,
    run_id: runId,
    goal: (run.goal || '').slice(0, 300),
    stack,
    trajectory_summary: buildTrajectorySummary(run),
    outcome_summary: buildOutcomeSummary(run, scores),
    scores,
    lessons,
    preference_pairs: preferencePairs,
    skill_proposals: skillProposals,
    eval_cases: evalCases,
    confidence: scores.confidence,
    approved_for_training: false,
    created_at: now,
    updated_at: now,
  }

  return scrubSecretsFromLearningData(rec)
}

// ── Dataset export ────────────────────────────────────────────────────────────

const SAFE_EXPORT_ROOT_NAMES = ['forge', 'learning', 'exports', 'state']

function safeExportPath(projectId, filename, forgeHome) {
  const base = path.join(forgeHome, 'learning', projectId)
  const resolved = path.resolve(base, filename)
  // Must stay inside forgeHome
  if (!resolved.startsWith(path.resolve(forgeHome) + path.sep)) {
    throw new Error('Export path escapes forge home boundary')
  }
  return resolved
}

async function exportLearningDataset(projectId, options, forgeRunStore, forgeHome) {
  const {
    min_confidence = 'low',
    include_positive = true,
    include_negative = true,
    only_human_approved = false,
    dataset_type = 'jsonl',
    name = `export-${Date.now().toString(36)}`,
  } = options || {}

  const CONF_ORDER = { low: 0, medium: 1, high: 2 }
  const minConfScore = CONF_ORDER[min_confidence] ?? 0

  const records = forgeRunStore.getDistillationRecords(projectId, 500)
  let filtered = records.filter(r => {
    const confScore = CONF_ORDER[r.confidence] ?? 0
    if (confScore < minConfScore) return false
    if (only_human_approved && !r.approved_for_training) return false
    if (!include_positive && r.outcome_summary?.success) return false
    if (!include_negative && !r.outcome_summary?.success) return false
    return true
  })

  filtered = filtered.map(r => scrubSecretsFromLearningData(r))

  const exportDir = path.join(forgeHome, 'learning', projectId)
  fs.mkdirSync(exportDir, { recursive: true, mode: 0o700 })
  const filename = `${name.replace(/[^a-z0-9\-_]/gi, '_')}.${dataset_type === 'preference_jsonl' ? 'jsonl' : dataset_type === 'eval_jsonl' ? 'jsonl' : 'jsonl'}`
  const exportPath = safeExportPath(projectId, filename, forgeHome)

  let lines
  if (dataset_type === 'preference_jsonl') {
    lines = filtered.flatMap(r => r.preference_pairs || [])
      .filter(p => !only_human_approved || p.approved_for_training)
      .map(p => JSON.stringify(p))
  } else if (dataset_type === 'eval_jsonl') {
    lines = filtered.flatMap(r => r.eval_cases || []).map(e => JSON.stringify(e))
  } else {
    lines = filtered.map(r => JSON.stringify(r))
  }

  fs.writeFileSync(exportPath, lines.join('\n'), { mode: 0o600 })

  const ds = {
    dataset_id: `ds-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
    project_id: projectId,
    name,
    dataset_type,
    filters: { min_confidence, include_positive, include_negative, only_human_approved },
    record_count: lines.length,
    export_path: exportPath,
    created_at: new Date().toISOString(),
  }
  forgeRunStore.upsertLearningDataset(ds)
  return ds
}

// ── Memory promotion ──────────────────────────────────────────────────────────

function promoteLesson(lesson, forgeRunStore) {
  const CONF_MIN = { high: true, medium: true, low: false }
  if (!CONF_MIN[lesson.confidence]) return { ok: false, error: 'confidence too low for promotion (must be medium or high)' }
  if (lesson.promoted_to_memory) return { ok: false, error: 'already promoted' }

  // Block promotion of known anti-patterns
  const forbidden = ['unsafe', 'rejected patch', 'failed code', 'hallucinated', 'raw secret']
  const lessonLower = (lesson.lesson || '').toLowerCase()
  for (const term of forbidden) {
    if (lessonLower.includes(term)) return { ok: false, error: `Lesson text contains forbidden pattern: "${term}"` }
  }

  const existing = forgeRunStore.findMemoryFactByContent(lesson.project_id, lesson.lesson)
  if (!existing) {
    forgeRunStore.upsertMemoryFact({
      memory_id: `mem-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
      project_id: lesson.project_id,
      source_run_id: lesson.run_id,
      category: lesson.category,
      fact: lesson.lesson,
      evidence: JSON.stringify(lesson.evidence || {}),
      confidence: lesson.confidence,
      usage_count: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
  }
  forgeRunStore.markLessonPromoted(lesson.lesson_id)
  return { ok: true }
}

// ── Summary ───────────────────────────────────────────────────────────────────

function getLearningSummary(projectId, forgeRunStore) {
  return forgeRunStore.getLearningSummary(projectId)
}

module.exports = {
  scrubSecretsFromLearningData,
  scoreTrajectory,
  extractLessons,
  createPreferencePairs,
  createSkillUpdateProposals,
  createEvaluationCases,
  buildDistillationRecord,
  exportLearningDataset,
  promoteLesson,
  getLearningSummary,
}
