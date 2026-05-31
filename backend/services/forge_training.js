'use strict'

/**
 * forge_training.js — Phase 8 Local Model Training Pipeline
 *
 * Provides training dataset validation, data preparation, Python trainer
 * invocation (train/evaluate/predict), evaluation gating, and training
 * directory management. All model paths are constrained inside FORGE_HOME.
 */

const fs = require('fs')
const path = require('path')
const { spawn } = require('child_process')
const crypto = require('crypto')
const os = require('os')

// ── Constants ──────────────────────────────────────────────────────────────────

/** Supported model types and their training requirements. */
const MODEL_TYPES = {
  skill_selector: {
    label: 'Skill Selector',
    description: 'Predicts which skill to apply for a given goal',
    min_preferred: 30,
    warn_below: 10,
    eval_threshold: 0.65,
  },
  risk_classifier: {
    label: 'Risk Classifier',
    description: 'Classifies action risk level (low/medium/high)',
    min_preferred: 50,
    warn_below: 20,
    eval_threshold: 0.70,
  },
  code_reviewer: {
    label: 'Code Reviewer',
    description: 'Advisory code quality scoring',
    min_preferred: 40,
    warn_below: 15,
    eval_threshold: 0.60,
  },
  debug_advisor: {
    label: 'Debug Advisor',
    description: 'Suggests debugging strategies for failing tests',
    min_preferred: 25,
    warn_below: 10,
    eval_threshold: 0.60,
  },
}

/** Supported training methods. */
const TRAINING_METHODS = [
  'local_classifier',   // numpy logistic regression (zero extra deps)
  'rule_augmented',     // no ML weights — uses distilled rules only
  'lora_adapter',       // requires peft/transformers/torch (opt-in)
]

// Secrets that must never appear in training data
const SECRET_PATTERNS = [
  /\b(api[_-]?key|secret|password|token|bearer|credential|private[_-]key)\s*[=:]\s*\S+/i,
  /sk-[A-Za-z0-9]{20,}/,
  /ghp_[A-Za-z0-9]{36}/,
  /AKIA[A-Z0-9]{16}/,
]

// ── Helpers ────────────────────────────────────────────────────────────────────

function nowIso() { return new Date().toISOString() }

function _containsSecret(text) {
  return typeof text === 'string' && SECRET_PATTERNS.some(re => re.test(text))
}

function _deepContainsSecret(value) {
  if (typeof value === 'string') return _containsSecret(value)
  if (Array.isArray(value)) return value.some(_deepContainsSecret)
  if (value && typeof value === 'object') return Object.values(value).some(_deepContainsSecret)
  return false
}

// ── Path safety ────────────────────────────────────────────────────────────────

/**
 * Throws if modelPath is not inside forgeHome (path traversal guard).
 */
function assertInsideForgeHome(modelPath, forgeHome) {
  const resolved = path.resolve(modelPath)
  const base = path.resolve(forgeHome)
  if (!resolved.startsWith(base + path.sep) && resolved !== base) {
    throw new Error(`model_path must be inside FORGE_HOME: ${modelPath}`)
  }
}

// ── Training directory ─────────────────────────────────────────────────────────

/**
 * Returns (and creates) the training directory for a given project + run.
 */
function trainingDir(forgeHome, projectId, trainingRunId) {
  const dir = path.join(forgeHome, 'training', projectId, trainingRunId)
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

// ── Dataset validation ─────────────────────────────────────────────────────────

/**
 * Validate a dataset before training.
 *
 * dataset — { export_path, record_count, dataset_type }
 * modelType — key in MODEL_TYPES
 * opts — { min_confidence, only_human_approved }
 * forgeHome — string (for path assertions)
 *
 * Returns: { ok, result, issues, record_count, approved_count, rejected_count,
 *            secret_scan_passed, class_distribution, examples }
 */
function validateTrainingDataset(dataset, modelType, opts = {}, forgeHome) {
  const spec = MODEL_TYPES[modelType]
  if (!spec) throw new Error(`Unknown model_type: ${modelType}`)

  const issues = []
  let examples = []
  let secretScanPassed = true

  // Read examples from the export_path JSONL
  const exportPath = dataset?.export_path
  if (!exportPath || !fs.existsSync(exportPath)) {
    return { ok: false, result: 'failed', issues: ['dataset export file not found'], record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false, class_distribution: {}, examples: [] }
  }

  // Ensure the path is inside FORGE_HOME (if provided)
  if (forgeHome) {
    try { assertInsideForgeHome(exportPath, forgeHome) }
    catch (err) { return { ok: false, result: 'failed', issues: [err.message], record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: false, class_distribution: {}, examples: [] } }
  }

  const lines = fs.readFileSync(exportPath, 'utf8').split('\n').filter(Boolean)
  for (const line of lines) {
    try {
      const rec = JSON.parse(line)
      if (_deepContainsSecret(rec)) { secretScanPassed = false; continue }
      examples.push(rec)
    } catch { /* skip malformed lines */ }
  }

  if (!secretScanPassed) issues.push('secret scan: one or more records contained secrets and were excluded')

  const { only_human_approved = false } = opts
  if (only_human_approved) {
    const before = examples.length
    examples = examples.filter(e => e.approved_for_training === true || e.label !== undefined)
    const rejected = before - examples.length
    if (rejected > 0) issues.push(`${rejected} records excluded (not human-approved)`)
  }

  const totalCount = examples.length
  const approvedCount = examples.filter(e => e.label !== undefined || e.is_positive !== undefined).length
  const rejectedCount = totalCount - approvedCount

  const classDist = {}
  for (const ex of examples) {
    const label = String(ex.label ?? (ex.is_positive ? 'positive' : 'negative') ?? 'unknown')
    classDist[label] = (classDist[label] || 0) + 1
  }

  if (totalCount === 0) {
    issues.push('no valid examples after filtering')
    return { ok: false, result: 'failed', issues, record_count: 0, approved_count: 0, rejected_count: 0, secret_scan_passed: secretScanPassed, class_distribution: {}, examples: [] }
  }

  if (totalCount < spec.warn_below) {
    issues.push(`only ${totalCount} examples (minimum preferred: ${spec.min_preferred})`)
    return { ok: false, result: 'too_small', issues, record_count: totalCount, approved_count: approvedCount, rejected_count: rejectedCount, secret_scan_passed: secretScanPassed, class_distribution: classDist, examples }
  }

  if (totalCount < spec.min_preferred) {
    issues.push(`${totalCount} examples — below preferred ${spec.min_preferred}, results may be noisy`)
  }

  return {
    ok: true,
    result: 'ok',
    issues,
    record_count: totalCount,
    approved_count: approvedCount,
    rejected_count: rejectedCount,
    secret_scan_passed: secretScanPassed,
    class_distribution: classDist,
    examples,
  }
}

// ── Data preparation ───────────────────────────────────────────────────────────

/**
 * Write validated examples to train/eval split JSONL files.
 * Returns: { trainPath, evalPath, train_count, eval_count }
 */
function prepareTrainingData(examples, dir) {
  fs.mkdirSync(dir, { recursive: true })
  // 80/20 split
  const split = Math.max(1, Math.floor(examples.length * 0.8))
  const trainExamples = examples.slice(0, split)
  const evalExamples = examples.slice(split)

  const trainPath = path.join(dir, 'prepared_train.jsonl')
  const evalPath = path.join(dir, 'prepared_eval.jsonl')
  fs.writeFileSync(trainPath, trainExamples.map(e => JSON.stringify(e)).join('\n') + '\n', { mode: 0o600 })
  fs.writeFileSync(evalPath, evalExamples.map(e => JSON.stringify(e)).join('\n') + '\n', { mode: 0o600 })

  return { trainPath, evalPath, train_count: trainExamples.length, eval_count: evalExamples.length }
}

// ── Python trainer ─────────────────────────────────────────────────────────────

/**
 * Inline Python trainer script (numpy logistic regression).
 * Handles operations: train, evaluate, predict.
 * Self-contained — no peft/torch required for local_classifier.
 */
const PYTHON_TRAINER_SCRIPT = `
import sys, json, os

payload = json.loads(sys.stdin.read())
op = payload.get('operation', 'train')

def _featurize(examples):
    # Simple bag-of-words over goal text
    import re
    vocab = {}
    for ex in examples:
        text = str(ex.get('goal', '') or ex.get('input', {}).get('goal', '') or ex.get('prompt', ''))
        for tok in re.findall(r'[a-z]+', text.lower()):
            if tok not in vocab:
                vocab[tok] = len(vocab)
    X = []
    for ex in examples:
        text = str(ex.get('goal', '') or ex.get('input', {}).get('goal', '') or ex.get('prompt', ''))
        row = [0.0] * len(vocab)
        for tok in re.findall(r'[a-z]+', text.lower()):
            if tok in vocab:
                row[vocab[tok]] = 1.0
        X.append(row)
    return X, vocab

if op == 'train':
    train_path = payload.get('train_path', '')
    model_path = payload.get('model_path', '')
    epochs = int(payload.get('epochs', 100))

    try:
        import numpy as np
        lines = open(train_path).read().strip().split('\\n') if os.path.exists(train_path) else []
        examples = [json.loads(l) for l in lines if l.strip()]
        if not examples:
            print(json.dumps({'ok': False, 'error': 'no training examples'}))
            sys.exit(0)

        labels_raw = [ex.get('label', 1 if ex.get('is_positive') else 0) for ex in examples]
        classes = sorted(set(str(l) for l in labels_raw))
        label_map = {c: i for i, c in enumerate(classes)}
        y = np.array([label_map[str(l)] for l in labels_raw])
        X_list, vocab = _featurize(examples)
        X = np.array(X_list) if X_list and X_list[0] else np.zeros((len(examples), 1))

        # Logistic regression via gradient descent
        n, d = X.shape
        k = len(classes)
        W = np.zeros((d, k))
        lr = 0.1
        for _ in range(epochs):
            logits = X @ W
            logits -= logits.max(axis=1, keepdims=True)
            probs = np.exp(logits)
            probs /= probs.sum(axis=1, keepdims=True)
            one_hot = np.eye(k)[y]
            grad = X.T @ (probs - one_hot) / n
            W -= lr * grad

        logits = X @ W
        preds = logits.argmax(axis=1)
        acc = float((preds == y).mean())

        model = {'W': W.tolist(), 'vocab': vocab, 'classes': classes, 'label_map': label_map}
        import json as _json
        open(model_path, 'w').write(_json.dumps(model))
        print(json.dumps({'ok': True, 'train_accuracy': acc, 'classes': classes, 'train_records': n}))
    except ImportError:
        print(json.dumps({'ok': False, 'code': 'NEEDS_SETUP', 'error': 'numpy is required for local_classifier training. Install via: pip install numpy'}))

elif op == 'evaluate':
    model_path = payload.get('model_path', '')
    eval_path = payload.get('eval_path', '')
    try:
        import numpy as np
        model = json.loads(open(model_path).read())
        lines = open(eval_path).read().strip().split('\\n') if os.path.exists(eval_path) else []
        examples = [json.loads(l) for l in lines if l.strip()]
        if not examples:
            print(json.dumps({'ok': True, 'metrics': {'accuracy': 0.0, 'n': 0}}))
            sys.exit(0)
        vocab = model['vocab']
        classes = model['classes']
        label_map = model['label_map']
        W = np.array(model['W'])
        labels_raw = [ex.get('label', 1 if ex.get('is_positive') else 0) for ex in examples]
        y = np.array([label_map.get(str(l), 0) for l in labels_raw])
        X_list = []
        for ex in examples:
            text = str(ex.get('goal', '') or ex.get('input', {}).get('goal', '') or '')
            import re
            row = [0.0] * len(vocab)
            for tok in re.findall(r'[a-z]+', text.lower()):
                if tok in vocab:
                    row[vocab[tok]] = 1.0
            X_list.append(row)
        X = np.array(X_list) if X_list and X_list[0] else np.zeros((len(examples), 1))
        preds = (X @ W).argmax(axis=1)
        acc = float((preds == y).mean())
        print(json.dumps({'ok': True, 'metrics': {'accuracy': acc, 'n': len(examples)}}))
    except ImportError:
        print(json.dumps({'ok': False, 'code': 'NEEDS_SETUP', 'error': 'numpy required for evaluation'}))

elif op == 'predict':
    model_path = payload.get('model_path', '')
    inp = payload.get('input', {})
    try:
        import numpy as np, re
        model = json.loads(open(model_path).read())
        vocab = model['vocab']
        classes = model['classes']
        W = np.array(model['W'])
        text = str(inp.get('goal', '') or inp.get('text', '') or json.dumps(inp))
        row = [0.0] * len(vocab)
        for tok in re.findall(r'[a-z]+', text.lower()):
            if tok in vocab:
                row[vocab[tok]] = 1.0
        X = np.array([row])
        logits = (X @ W)[0]
        logits -= logits.max()
        probs = list(float(p) for p in (lambda e: e / e.sum())(np.exp(logits)))
        ranked = sorted(zip(classes, probs), key=lambda t: -t[1])
        prediction = ranked[0][0]
        confidence = ranked[0][1]
        print(json.dumps({'ok': True, 'prediction': prediction, 'confidence': confidence, 'ranked': [{'label': r[0], 'score': r[1]} for r in ranked]}))
    except ImportError:
        print(json.dumps({'ok': False, 'error': 'numpy required for prediction'}))
    except Exception as e:
        print(json.dumps({'ok': False, 'error': str(e)}))

else:
    print(json.dumps({'ok': False, 'error': f'unknown operation: {op}'}))
`

/**
 * Invoke the inline Python trainer with a payload object.
 * operation: 'train' | 'evaluate' | 'predict'
 * Returns: { ok, ... }
 */
function runPythonTrainer(payload, timeoutMs = 60000) {
  return new Promise(resolve => {
    let stdout = ''
    let stderr = ''
    const child = spawn(process.env.PYTHON || 'python3', ['-c', PYTHON_TRAINER_SCRIPT], {
      timeout: timeoutMs,
    })
    child.stdin.write(JSON.stringify(payload))
    child.stdin.end()
    child.stdout.on('data', d => { stdout += d })
    child.stderr.on('data', d => { stderr += d })
    child.on('close', code => {
      if (code !== 0 && !stdout.trim()) {
        return resolve({ ok: false, error: stderr.slice(0, 400) || `trainer exited ${code}` })
      }
      try {
        const line = stdout.trim().split('\n').pop() || '{}'
        resolve(JSON.parse(line))
      } catch {
        resolve({ ok: false, error: 'could not parse trainer output', stdout: stdout.slice(0, 400) })
      }
    })
    child.on('error', err => resolve({ ok: false, error: err.message }))
  })
}

// ── Evaluation gate ────────────────────────────────────────────────────────────

/**
 * Apply the promotion gate: check if eval metrics pass the threshold for modelType.
 * Returns: { passed, failure_reasons }
 */
function applyEvalGate(modelType, metrics, _unused) {
  const spec = MODEL_TYPES[modelType]
  if (!spec) return { passed: false, failure_reasons: [`unknown model_type: ${modelType}`] }
  const accuracy = metrics?.accuracy ?? 0
  const threshold = spec.eval_threshold
  const failureReasons = []
  if (accuracy < threshold) failureReasons.push(`accuracy ${accuracy.toFixed(3)} below threshold ${threshold}`)
  if (metrics?.n !== undefined && metrics.n < 5) failureReasons.push(`evaluation set too small (${metrics.n} examples)`)
  return { passed: failureReasons.length === 0, failure_reasons: failureReasons }
}

module.exports = {
  MODEL_TYPES,
  TRAINING_METHODS,
  assertInsideForgeHome,
  trainingDir,
  validateTrainingDataset,
  prepareTrainingData,
  runPythonTrainer,
  applyEvalGate,
}
