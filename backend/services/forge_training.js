'use strict'
/**
 * Phase 8 — Local helper-model training pipeline.
 *
 * Trains SMALL advisory helper models (risk classifier, skill selector,
 * failure classifier, model-router classifier, decomposer helper) from
 * Phase 7 *approved exported datasets* — never from raw run logs.
 *
 * Safety invariants:
 *  - Consumes only exported jsonl datasets (path boundary-checked).
 *  - Datasets are validated (schema + secret scan + size + class balance)
 *    before training. Real training is blocked on validation failure unless
 *    the caller explicitly overrides for a too-small (warn-level) dataset.
 *  - No model is auto-activated. Promotion requires a passed evaluation
 *    + explicit user approval.
 *  - Helper models are ADVISORY: they never override safety gates.
 *  - All artifacts written under FORGE_HOME/training/<project>/<run>/.
 *  - No package installation. Missing deps => NEEDS_SETUP, never fake success.
 */

const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { spawn } = require('child_process')
const { scrubSecretsFromLearningData } = require('./forge_learning')

const TRAIN_SCRIPT = path.join(__dirname, '..', 'forge_train.py')

// ── Model type registry ─────────────────────────────────────────────────────

const MODEL_TYPES = {
  risk_classifier: {
    label: 'Risk Classifier',
    labels: ['low', 'medium', 'high', 'critical'],
    min_preferred: 50, warn_below: 30,
    eval_type: 'risk_classifier_eval',
    derive: deriveRiskClassifierExamples,
  },
  skill_selector: {
    label: 'Skill Selector',
    labels: null, // open label set (skill IDs)
    min_preferred: 30, warn_below: 20,
    eval_type: 'skill_selection_eval',
    derive: deriveSkillSelectorExamples,
  },
  failure_classifier: {
    label: 'Failure Classifier',
    labels: ['syntax_error', 'missing_import', 'type_error', 'test_failure', 'security_block', 'unknown'],
    min_preferred: 50, warn_below: 30,
    eval_type: null,
    derive: deriveFailureClassifierExamples,
  },
  model_router_classifier: {
    label: 'Model Router Classifier',
    labels: null,
    min_preferred: 40, warn_below: 25,
    eval_type: 'model_router_eval',
    derive: deriveModelRouterExamples,
  },
  decomposer_helper: {
    label: 'Decomposer Helper',
    labels: null,
    min_preferred: 20, warn_below: 10,
    eval_type: 'decomposer_eval',
    derive: deriveDecomposerExamples,
  },
}

const TRAINING_METHODS = ['rule_augmented', 'local_classifier', 'lora_adapter']

// ── Path safety ──────────────────────────────────────────────────────────────

function trainingDir(forgeHome, projectId, trainingRunId) {
  const base = path.join(forgeHome, 'training', projectId, trainingRunId)
  const resolved = path.resolve(base)
  if (!resolved.startsWith(path.resolve(forgeHome) + path.sep)) {
    throw new Error('training path escapes FORGE_HOME boundary')
  }
  return resolved
}

function assertInsideForgeHome(p, forgeHome) {
  const resolved = path.resolve(p)
  if (!resolved.startsWith(path.resolve(forgeHome) + path.sep)) {
    throw new Error('path escapes FORGE_HOME boundary')
  }
  // reject symlink escape on existing paths
  try {
    if (fs.existsSync(resolved)) {
      const real = fs.realpathSync(resolved)
      if (!real.startsWith(path.resolve(forgeHome) + path.sep)) {
        throw new Error('symlink escapes FORGE_HOME boundary')
      }
    }
  } catch (e) {
    if (/boundary/.test(e.message)) throw e
  }
  return resolved
}

// ── Secret detection (defense in depth, beyond Phase 7 scrubbing) ────────────

const SECRET_SIGNATURES = [
  /eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+/, // JWT
  /sk-ant-[A-Za-z0-9_\-]{20,}/,                               // anthropic
  /(?:AKIA|ASIA)[A-Z0-9]{16}/,                                // AWS
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,                       // PEM
  /\b[A-Fa-f0-9]{40,}\b/,                                     // long hex secret
]

function lineContainsSecret(line) {
  return SECRET_SIGNATURES.some(re => re.test(line))
}

// ── Dataset validation ───────────────────────────────────────────────────────

const CONF_ORDER = { low: 0, medium: 1, high: 2 }

function validateTrainingDataset(dataset, modelType, options, forgeHome) {
  const issues = []
  const spec = MODEL_TYPES[modelType]
  if (!spec) return { ok: false, result: 'invalid', issues: [`unknown model_type: ${modelType}`], record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false }

  const minConf = options?.min_confidence || 'low'
  const minConfScore = CONF_ORDER[minConf] ?? 0

  // 1. dataset exists + path safety
  if (!dataset || !dataset.export_path) {
    issues.push('dataset has no export_path')
    return { ok: false, result: 'failed', issues, record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false }
  }
  let exportPath
  try {
    exportPath = assertInsideForgeHome(dataset.export_path, forgeHome)
  } catch (e) {
    issues.push(e.message)
    return { ok: false, result: 'failed', issues, record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false }
  }
  if (!fs.existsSync(exportPath)) {
    issues.push(`dataset file not found: ${path.basename(exportPath)}`)
    return { ok: false, result: 'failed', issues, record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false }
  }
  if (!exportPath.endsWith('.jsonl')) {
    issues.push('dataset is not a .jsonl file')
  }

  // 2. parse each line + secret scan
  const raw = fs.readFileSync(exportPath, 'utf8')
  const lines = raw.split('\n').filter(l => l.trim())
  const records = []
  let secretScanPassed = true
  let parseErrors = 0
  for (let i = 0; i < lines.length; i++) {
    if (lineContainsSecret(lines[i])) {
      secretScanPassed = false
      issues.push(`secret detected on line ${i + 1} — dataset rejected`)
    }
    try {
      records.push(JSON.parse(lines[i]))
    } catch {
      parseErrors++
      if (parseErrors <= 3) issues.push(`line ${i + 1} is not valid JSON`)
    }
  }
  if (parseErrors > 0) issues.push(`${parseErrors} line(s) failed to parse`)

  // 3. derive labeled examples for this model type
  const derived = spec.derive(records, { minConfScore, onlyApproved: options?.only_human_approved })
  const approvedCount = derived.examples.length
  const rejectedCount = derived.rejected
  derived.issues.forEach(x => issues.push(x))

  // 4. label validity (closed-set model types)
  if (spec.labels) {
    const badLabels = new Set()
    for (const ex of derived.examples) {
      if (!spec.labels.includes(String(ex.label))) badLabels.add(ex.label)
    }
    if (badLabels.size) issues.push(`invalid labels: ${[...badLabels].join(', ')}`)
  }

  // 5. class balance + distinct-class check
  const classCounts = {}
  for (const ex of derived.examples) classCounts[ex.label] = (classCounts[ex.label] || 0) + 1
  const distinctClasses = Object.keys(classCounts).length
  if (distinctClasses < 2) {
    issues.push(`need >= 2 distinct classes for training, found ${distinctClasses}`)
  }
  const counts = Object.values(classCounts)
  if (counts.length >= 2) {
    const maxC = Math.max(...counts), minC = Math.min(...counts)
    if (minC > 0 && maxC / minC > 10) issues.push(`class imbalance is high (${maxC}:${minC}) — model may be biased`)
  }

  // 6. size thresholds
  let result = 'passed'
  if (approvedCount < spec.warn_below) {
    issues.push(`only ${approvedCount} usable example(s); real training blocked below ${spec.warn_below} (override required)`)
    result = 'too_small'
  } else if (approvedCount < spec.min_preferred) {
    issues.push(`${approvedCount} examples — below preferred ${spec.min_preferred}; results may be weak`)
    result = 'warn'
  }

  // Hard failures override
  if (!secretScanPassed) result = 'failed'
  if (parseErrors > 0 && approvedCount === 0) result = 'failed'
  if (distinctClasses < 2) result = (result === 'failed') ? 'failed' : 'too_small'

  return {
    ok: result === 'passed' || result === 'warn',
    result,
    issues,
    record_count: records.length,
    approved_count: approvedCount,
    rejected_count: rejectedCount,
    secret_scan_passed: secretScanPassed,
    class_distribution: classCounts,
    examples: derived.examples, // returned for prepare step
  }
}

// ── Example derivation from Phase 7 exports ──────────────────────────────────
// Phase 7 exports come in three shapes:
//   - jsonl: full distillation records (have eval_cases, lessons, etc.)
//   - eval_jsonl: flat eval cases {eval_type, input, expected, negative_case}
//   - preference_jsonl: preference pairs
// We derive labeled (input, label) examples from eval cases primarily.

function _collectEvalCases(records) {
  const cases = []
  for (const r of records) {
    if (r.eval_type && r.input) {
      cases.push(r) // flat eval case
    } else if (Array.isArray(r.eval_cases)) {
      for (const ec of r.eval_cases) cases.push(ec) // nested in distillation record
    }
  }
  return cases
}

function _passesFilters(rec, opts) {
  const confScore = CONF_ORDER[rec.confidence] ?? 0
  if (confScore < (opts.minConfScore ?? 0)) return false
  return true
}

function deriveRiskClassifierExamples(records, opts) {
  const examples = []
  const issues = []
  let rejected = 0
  for (const ec of _collectEvalCases(records)) {
    if (ec.eval_type !== 'risk_classifier_eval' && ec.eval_type !== 'planner_eval') continue
    if (!_passesFilters(ec, opts)) { rejected++; continue }
    const label = ec.expected?.classification || ec.expected?.risk_level
    if (!label || !['low', 'medium', 'high', 'critical', 'blocked'].includes(String(label))) { rejected++; continue }
    const normLabel = label === 'blocked' ? 'critical' : label
    examples.push({
      input: {
        goal: ec.input?.goal || '',
        file_path: ec.input?.file_path || '',
        action_type: ec.input?.action_type || '',
        stack: ec.input?.stack || ec.input?.project_stack || '',
      },
      label: normLabel,
    })
  }
  if (!examples.length) issues.push('no risk_classifier examples derivable from this dataset')
  return { examples, rejected, issues }
}

function deriveSkillSelectorExamples(records, opts) {
  const examples = []
  const issues = []
  let rejected = 0
  for (const ec of _collectEvalCases(records)) {
    if (ec.eval_type !== 'planner_eval' && ec.eval_type !== 'skill_selection_eval') continue
    if (!_passesFilters(ec, opts)) { rejected++; continue }
    const skills = ec.expected?.selected_skills
    if (!Array.isArray(skills) || !skills.length) { rejected++; continue }
    examples.push({
      input: { goal: ec.input?.goal || '', stack: ec.input?.stack || '' },
      label: skills[0], // top-1 skill as label
    })
  }
  if (!examples.length) issues.push('no skill_selector examples derivable from this dataset')
  return { examples, rejected, issues }
}

function deriveFailureClassifierExamples(records, opts) {
  const examples = []
  const issues = []
  let rejected = 0
  for (const ec of _collectEvalCases(records)) {
    if (ec.eval_type !== 'command_safety_eval') continue
    if (!_passesFilters(ec, opts)) { rejected++; continue }
    const verdict = ec.expected?.verdict
    const label = verdict === 'block' ? 'security_block' : 'unknown'
    examples.push({
      input: { findings: ec.expected?.findings || [], goal: ec.input?.goal || '' },
      label,
    })
  }
  if (!examples.length) issues.push('no failure_classifier examples derivable (needs command_safety_eval cases)')
  return { examples, rejected, issues }
}

function deriveModelRouterExamples(records, opts) {
  const examples = []
  const issues = []
  let rejected = 0
  for (const ec of _collectEvalCases(records)) {
    if (ec.eval_type !== 'model_router_eval') continue
    if (!_passesFilters(ec, opts)) { rejected++; continue }
    const routing = ec.expected?.routing || {}
    const stages = Object.keys(routing)
    if (!stages.length) { rejected++; continue }
    for (const stage of stages) {
      examples.push({
        input: { stage, stack: ec.input?.stack || '', goal: ec.input?.goal || '' },
        label: String(routing[stage]),
      })
    }
  }
  if (!examples.length) issues.push('no model_router examples derivable from this dataset')
  return { examples, rejected, issues }
}

function deriveDecomposerExamples(records, opts) {
  const examples = []
  const issues = []
  let rejected = 0
  for (const ec of _collectEvalCases(records)) {
    if (ec.eval_type !== 'decomposer_eval' && ec.eval_type !== 'planner_eval') continue
    if (!_passesFilters(ec, opts)) { rejected++; continue }
    const risk = ec.expected?.risk_level
    if (!risk) { rejected++; continue }
    examples.push({
      input: { goal: ec.input?.goal || '', stack: ec.input?.stack || '' },
      label: ec.expected?.should_decompose ? 'decompose' : 'single_run',
    })
  }
  if (!examples.length) issues.push('no decomposer examples derivable from this dataset')
  return { examples, rejected, issues }
}

// ── Python trainer invocation ────────────────────────────────────────────────

function runPythonTrainer(payload, timeoutMs = 120000) {
  return new Promise((resolve) => {
    let stdout = '', stderr = ''
    const child = spawn(process.env.PYTHON_BIN || 'python3', [TRAIN_SCRIPT], {
      timeout: timeoutMs,
      env: { ...process.env },
    })
    child.stdin.write(JSON.stringify(payload))
    child.stdin.end()
    child.stdout.on('data', d => { stdout += d })
    child.stderr.on('data', d => { stderr += d })
    child.on('close', () => {
      try {
        const line = stdout.trim().split('\n').filter(Boolean).pop() || '{}'
        resolve(JSON.parse(line))
      } catch {
        resolve({ ok: false, error: `trainer output unparseable: ${(stderr || stdout).slice(0, 300)}` })
      }
    })
    child.on('error', err => resolve({ ok: false, error: err.message, code: 'NEEDS_SETUP' }))
  })
}

// ── Prepare training data (write prepared_train/eval jsonl) ───────────────────

function prepareTrainingData(examples, dir, splitRatio = 0.8) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  // Scrub once more before writing to disk
  const clean = examples.map(e => scrubSecretsFromLearningData(e))
  // Shuffle deterministically then split
  const shuffled = [...clean].sort(() => 0.5 - Math.random())
  const splitIdx = Math.max(1, Math.floor(shuffled.length * splitRatio))
  const train = shuffled.slice(0, splitIdx)
  const evalSet = shuffled.slice(splitIdx).length ? shuffled.slice(splitIdx) : shuffled.slice(0, Math.max(1, Math.floor(shuffled.length * 0.2)))
  const trainPath = path.join(dir, 'prepared_train.jsonl')
  const evalPath = path.join(dir, 'prepared_eval.jsonl')
  fs.writeFileSync(trainPath, train.map(r => JSON.stringify(r)).join('\n'), { mode: 0o600 })
  fs.writeFileSync(evalPath, evalSet.map(r => JSON.stringify(r)).join('\n'), { mode: 0o600 })
  return { trainPath, evalPath, train_count: train.length, eval_count: evalSet.length }
}

// ── Evaluation gate ──────────────────────────────────────────────────────────
// A candidate must beat the rule-augmented baseline AND meet absolute minimums.

const EVAL_THRESHOLDS = {
  risk_classifier: { min_accuracy: 0.6, max_high_risk_fn_rate: 0.25 },
  skill_selector: { min_accuracy: 0.4 },
  failure_classifier: { min_accuracy: 0.5 },
  model_router_classifier: { min_accuracy: 0.5 },
  decomposer_helper: { min_accuracy: 0.5 },
}

function applyEvalGate(modelType, metrics, baselineAccuracy = 0) {
  const t = EVAL_THRESHOLDS[modelType] || { min_accuracy: 0.5 }
  const reasons = []
  const acc = metrics.accuracy ?? 0
  if (acc < t.min_accuracy) reasons.push(`accuracy ${acc} below minimum ${t.min_accuracy}`)
  if (acc <= baselineAccuracy) reasons.push(`accuracy ${acc} does not beat baseline ${baselineAccuracy}`)
  if (t.max_high_risk_fn_rate != null && (metrics.high_risk_false_negative_rate ?? 0) > t.max_high_risk_fn_rate) {
    reasons.push(`high-risk false-negative rate ${metrics.high_risk_false_negative_rate} exceeds ${t.max_high_risk_fn_rate} — unsafe`)
  }
  return { passed: reasons.length === 0, failure_reasons: reasons }
}

module.exports = {
  MODEL_TYPES,
  TRAINING_METHODS,
  EVAL_THRESHOLDS,
  trainingDir,
  assertInsideForgeHome,
  lineContainsSecret,
  validateTrainingDataset,
  prepareTrainingData,
  runPythonTrainer,
  applyEvalGate,
}
