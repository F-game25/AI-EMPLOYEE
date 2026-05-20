/**
 * /api/forge — canonical AscendForge supervised build pipeline.
 *
 * This router owns the desktop-facing Forge contract. Python ForgeController
 * remains the execution safety layer for sandbox/snapshot/rollback operations,
 * while Node owns persistent project/session/plan/action state for the UI.
 */
'use strict'

const express = require('express')
const path = require('path')
const fs = require('fs')
const os = require('os')
const crypto = require('crypto')
const { spawn } = require('child_process')
const { getAscendForgeEngine, DEFAULT_APPROVAL_POLICY } = require('../ascendforge/engine')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const STATE_DIR = path.resolve(process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR || path.join(os.homedir(), '.ai-employee', 'state'))
const FORGE_HOME = path.resolve(process.env.AI_EMPLOYEE_FORGE_HOME || path.join(STATE_DIR, 'forge'))
const PROJECTS_FILE = path.join(FORGE_HOME, 'projects.json')
const SESSIONS_FILE = path.join(FORGE_HOME, 'sessions.json')
const PLANS_FILE = path.join(FORGE_HOME, 'plans.json')
const ACTIONS_FILE = path.join(FORGE_HOME, 'actions.json')
const AUDIT_FILE = path.join(FORGE_HOME, 'audit.jsonl')
const PYTHON_FORGE_SCRIPT = path.join(REPO_ROOT, 'backend', 'run_forge.py')

const PROJECT_SKIP = new Set(['.git', 'node_modules', '__pycache__', '.ascendforge', 'dist', 'build', '.DS_Store'])
const DANGEROUS_ACTIONS = new Set([
  'file_delete',
  'shell_command',
  'dependency_install',
  'external_delivery',
  'wallet_or_compute',
  'rollback',
])
const WRITE_ACTIONS = new Set(['file_create', 'file_update', 'file_delete', 'scaffold_create'])
const PROTECTED_PATH_PATTERNS = [
  /^launcher\//,
  /^backend\/routes\/auth/i,
  /^backend\/auth/i,
  /^runtime\/runtime\/sandbox_executor\.py$/,
  /^runtime\/runtime\/hot_reload_manager\.py$/,
  /^runtime\/runtime\/version_control\.py$/,
  /^runtime\/core\/forge_controller\.py$/,
  /^runtime\/config\/.*policy/i,
  /^runtime\/config\/.*wallet/i,
  /^start\.sh$/,
  /^stop\.sh$/,
]

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

function appendAudit(event, details = {}) {
  ensureDir(path.dirname(AUDIT_FILE))
  fs.appendFileSync(AUDIT_FILE, JSON.stringify({ ts: new Date().toISOString(), event, details }) + '\n', { mode: 0o600 })
}

function nowIso() {
  return new Date().toISOString()
}

function slugify(value) {
  return String(value || 'project')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'project'
}

function asList(file) {
  const data = readJson(file, [])
  return Array.isArray(data) ? data : []
}

function loadProjects() { return asList(PROJECTS_FILE) }
function saveProjects(list) { writeJson(PROJECTS_FILE, list.slice(0, 500)) }
function loadSessions() { return asList(SESSIONS_FILE) }
function saveSessions(list) { writeJson(SESSIONS_FILE, list.slice(0, 1000)) }
function loadPlans() { return asList(PLANS_FILE) }
function savePlans(list) { writeJson(PLANS_FILE, list.slice(0, 1000)) }
function loadActions() { return asList(ACTIONS_FILE) }
function saveActions(list) { writeJson(ACTIONS_FILE, list.slice(0, 2000)) }

function findProject(id) {
  return loadProjects().find(project => project.id === id) || null
}

function updateProject(project) {
  const list = loadProjects().filter(item => item.id !== project.id)
  list.unshift({ ...project, updated_at: nowIso() })
  saveProjects(list)
}

function findAction(id) {
  return loadActions().find(action => action.id === id) || null
}

function updateAction(id, patch) {
  const actions = loadActions()
  const updated = actions.map(action => action.id === id ? { ...action, ...patch, updated_at: nowIso() } : action)
  saveActions(updated)
  return updated.find(action => action.id === id) || null
}

function safeProjectRoot(project) {
  const root = path.resolve(project.root_path || '')
  return root
}

function resolveInsideProject(project, relativePath) {
  const root = safeProjectRoot(project)
  const target = path.resolve(root, String(relativePath || ''))
  if (target !== root && !target.startsWith(root + path.sep)) {
    const err = new Error('path escapes project root')
    err.status = 403
    throw err
  }
  return target
}

function normalizeRelPath(filePath) {
  return String(filePath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .replace(/\.\.+/g, '.')
}

function isProtectedPath(project, filePath) {
  const normalized = normalizeRelPath(filePath)
  if (project.target_type !== 'internal_repo') return false
  return PROTECTED_PATH_PATTERNS.some(pattern => pattern.test(normalized))
}

function canWritePath(project, filePath) {
  if (project.write_access !== true) return false
  const allowed = Array.isArray(project.allowed_write_paths) && project.allowed_write_paths.length
    ? project.allowed_write_paths
    : ['.']
  const normalized = normalizeRelPath(filePath)
  return allowed.some(prefix => {
    const p = normalizeRelPath(prefix)
    return p === '.' || normalized === p || normalized.startsWith(p.replace(/\/+$/, '') + '/')
  })
}

function buildTree(dir, base = dir, depth = 0) {
  if (depth > 5 || !fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter(entry => !PROJECT_SKIP.has(entry.name) && !entry.name.startsWith('.'))
    .slice(0, 300)
    .map(entry => {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        return {
          name: entry.name,
          type: 'dir',
          path: path.relative(base, full),
          children: buildTree(full, base, depth + 1),
        }
      }
      return {
        name: entry.name,
        type: 'file',
        path: path.relative(base, full),
        bytes: fs.statSync(full).size,
      }
    })
}

function inferPackageType(project) {
  const root = safeProjectRoot(project)
  if (fs.existsSync(path.join(root, 'package.json'))) return 'node'
  if (fs.existsSync(path.join(root, 'pyproject.toml')) || fs.existsSync(path.join(root, 'requirements.txt'))) return 'python'
  return project.template || 'generic'
}

function defaultVerificationCommands(project) {
  if (project.target_type === 'internal_repo') {
    return ['npm --prefix frontend run build', 'npm --prefix launcher run verify']
  }
  const type = inferPackageType(project)
  if (type === 'node') return ['npm test', 'npm run build']
  if (type === 'python') return ['python3 -m py_compile $(find . -name "*.py" -maxdepth 4)']
  return ['manual review']
}

function scaffoldFiles(template, name) {
  const safeName = slugify(name)
  if (template === 'python-api') {
    return [
      { path: 'main.py', content: `from fastapi import FastAPI\n\napp = FastAPI(title="${name}")\n\n@app.get("/")\ndef root():\n    return {"project": "${safeName}", "status": "ok"}\n` },
      { path: 'requirements.txt', content: 'fastapi\nuvicorn\n' },
      { path: 'README.md', content: `# ${name}\n\nGenerated as an AscendForge staged project.\n` },
    ]
  }
  if (template === 'agent') {
    return [
      { path: `${safeName.replace(/-/g, '_')}.py`, content: `class ${safeName.replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase())}Agent:\n    name = "${safeName}"\n\n    def run(self, task):\n        return {"status": "draft", "task": task}\n` },
      { path: 'README.md', content: `# ${name}\n\nSupervised agent scaffold generated by AscendForge.\n` },
    ]
  }
  if (template === 'landing') {
    return [
      { path: 'index.html', content: `<!doctype html>\n<html><head><meta charset="utf-8"><title>${name}</title></head><body><main><h1>${name}</h1></main></body></html>\n` },
      { path: 'README.md', content: `# ${name}\n\nStatic landing page scaffold.\n` },
    ]
  }
  return [
    { path: 'index.html', content: `<!doctype html>\n<html><head><meta charset="utf-8"><title>${name}</title></head><body><h1>${name}</h1></body></html>\n` },
    { path: 'README.md', content: `# ${name}\n\nWeb app scaffold generated by AscendForge.\n` },
  ]
}

function makeAction(type, payload = {}) {
  const risk = payload.risk || (DANGEROUS_ACTIONS.has(type) ? 'dangerous' : WRITE_ACTIONS.has(type) ? 'caution' : 'safe')
  const action = {
    id: payload.id || `act-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
    type,
    label: payload.label || type.replace(/_/g, ' '),
    description: payload.description || '',
    project_id: payload.project_id || null,
    plan_id: payload.plan_id || null,
    status: 'proposed',
    risk,
    approval_required: risk !== 'safe' || WRITE_ACTIONS.has(type),
    approval_reason: payload.approval_reason || (risk === 'dangerous' ? 'Dangerous action requires owner approval.' : 'Supervised Forge action requires review before execution.'),
    expected_result: payload.expected_result || '',
    rollback_plan: payload.rollback_plan || 'Use the snapshot/rollback panel or restore generated files from project history.',
    diff: payload.diff || null,
    command: payload.command || null,
    file_path: payload.file_path || null,
    content: payload.content || null,
    files: payload.files || null,
    created_at: nowIso(),
    updated_at: nowIso(),
    policy_decision: payload.policy_decision || {
      decision: risk === 'safe' ? 'allow_logged' : 'requires_approval',
      risk,
    },
  }
  return action
}

function persistActions(newActions) {
  if (!newActions.length) return []
  const actions = loadActions()
  saveActions([...newActions, ...actions])
  for (const action of newActions) appendAudit('forge_action_proposed', { id: action.id, type: action.type, risk: action.risk, project_id: action.project_id })
  return newActions
}

function buildDiffForFiles(files) {
  if (!files?.length) return null
  return {
    path: files.length === 1 ? files[0].path : `${files.length} files`,
    isNew: true,
    hunks: files.slice(0, 4).map(file => ({
      header: `create ${file.path}`,
      lines: String(file.content || '')
        .split('\n')
        .slice(0, 40)
        .map(line => ({ type: 'add', content: line })),
    })),
  }
}

function createPlan(engine, project, payload = {}) {
  const goal = String(payload.goal || payload.content || payload.task || '').trim()
  if (!goal) {
    const err = new Error('goal required')
    err.status = 400
    throw err
  }
  const recommendation = engine.recommendSkills({
    goal,
    target_type: payload.target_type || 'build_agent',
    limit: 8,
  })
  const verificationCommands = project?.verification_commands?.length
    ? project.verification_commands
    : defaultVerificationCommands(project || { target_type: 'scratch', template: 'generic', root_path: FORGE_HOME })
  const impactedFiles = Array.isArray(payload.target_files) ? payload.target_files.map(normalizeRelPath).filter(Boolean) : []
  const hasWriteIntent = /\b(add|build|create|change|edit|update|delete|fix|refactor|implement|write)\b/i.test(goal)
  const hasDanger = /\b(delete|remove|install|shell|command|deploy|wallet|payment|external|publish)\b/i.test(goal)
  const risk = hasDanger ? 'dangerous' : hasWriteIntent ? 'caution' : 'safe'
  const plan = {
    id: `plan-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
    project_id: project?.id || null,
    goal,
    state: 'planned',
    readiness: {
      node_ready: true,
      python_forge_ready: 'unknown',
      sandbox_ready: 'unknown',
      model_provider: payload.provider || 'local-first',
      project_mode: project?.write_access ? 'writable' : 'read_only_or_staged',
    },
    selected_skills: recommendation.recommendedSkills.map(skill => ({
      id: skill.id,
      name: skill.name,
      category: skill.category,
      risk_level: skill.risk_level,
    })),
    task_plan: [
      'Clarify the intended change and affected surface.',
      'Select the minimal skill pack and retrieve project context.',
      'Generate a supervised diff or scaffold proposal.',
      'Run policy and sandbox checks before any write.',
      'Request owner approval for risky execution.',
      'Verify, audit, and record memory after completion.',
    ],
    impacted_files: impactedFiles,
    risk_level: risk,
    required_approvals: [
      ...(risk !== 'safe' ? ['owner_approval'] : []),
      ...(hasWriteIntent ? ['file_write_review'] : []),
    ],
    verification_commands: verificationCommands,
    rollback_strategy: 'Create/keep snapshots before applying code changes; for scaffold projects remove generated files if rejected.',
    created_at: nowIso(),
    updated_at: nowIso(),
  }
  const plans = loadPlans()
  savePlans([plan, ...plans])
  appendAudit('forge_plan_created', { id: plan.id, project_id: plan.project_id, risk_level: plan.risk_level, goal: goal.slice(0, 160) })
  return plan
}

function actionsForPlan(plan, project, payload = {}) {
  const actions = []
  actions.push(makeAction('security_scan', {
    project_id: project?.id,
    plan_id: plan.id,
    label: 'Run security preflight',
    description: 'Scan the current Forge execution surface before writes.',
    risk: 'safe',
    expected_result: 'Security scan findings are attached to the terminal output.',
    rollback_plan: 'No mutation.',
  }))
  if (plan.risk_level !== 'safe') {
    actions.push(makeAction('test_run', {
      project_id: project?.id,
      plan_id: plan.id,
      label: 'Run verification command',
      description: (plan.verification_commands || []).join(' && '),
      command: (plan.verification_commands || [])[0],
      risk: 'caution',
      expected_result: 'Verification result is recorded before apply.',
      rollback_plan: 'No write is applied by verification alone.',
    }))
  }
  if (payload.scaffold_files?.length) {
    actions.push(makeAction('scaffold_create', {
      project_id: project?.id,
      plan_id: plan.id,
      label: 'Create approved scaffold files',
      description: `Create ${payload.scaffold_files.length} scaffold file(s) inside the project root.`,
      files: payload.scaffold_files,
      diff: buildDiffForFiles(payload.scaffold_files),
      risk: 'caution',
      expected_result: 'Initial project files exist under the approved Forge project root.',
      rollback_plan: 'Delete the generated scaffold files if rejected or failed.',
    }))
  }
  return persistActions(actions)
}

function runForgePython(payload, timeoutMs = 90000) {
  return new Promise(resolve => {
    let stdout = ''
    let stderr = ''
    const child = spawn(process.env.PYTHON || 'python3', [PYTHON_FORGE_SCRIPT], {
      cwd: REPO_ROOT,
      env: { ...process.env, AI_EMPLOYEE_REPO_DIR: REPO_ROOT },
      timeout: timeoutMs,
    })
    child.stdin.write(JSON.stringify(payload))
    child.stdin.end()
    child.stdout.on('data', chunk => { stdout += chunk })
    child.stderr.on('data', chunk => { stderr += chunk })
    child.on('close', code => {
      if (code !== 0) return resolve({ ok: false, error: stderr.slice(0, 500) || `python exited ${code}` })
      try {
        resolve(JSON.parse(stdout.trim().split('\n').pop() || '{}'))
      } catch {
        resolve({ ok: false, error: 'could_not_parse_python_output', stdout: stdout.slice(0, 500) })
      }
    })
    child.on('error', err => resolve({ ok: false, error: err.message }))
  })
}

async function executeAction(action, project) {
  if (!project && action.project_id) {
    const err = new Error('project not found')
    err.status = 404
    throw err
  }
  if (action.type === 'security_scan') {
    return runForgePython({ operation: 'security_scan' }, 120000)
  }
  if (action.type === 'rollback') {
    if (!action.snapshot_id) return { ok: false, error: 'snapshot_id required for rollback' }
    return runForgePython({ operation: 'rollback', snapshot_id: action.snapshot_id }, 120000)
  }
  if (action.type === 'scaffold_create') {
    if (!project || !project.write_access) return { ok: false, error: 'project is not writable' }
    const written = []
    for (const file of action.files || []) {
      const filePath = normalizeRelPath(file.path)
      if (!canWritePath(project, filePath)) return { ok: false, error: `write path not allowed: ${filePath}` }
      if (isProtectedPath(project, filePath)) return { ok: false, error: `protected path blocked: ${filePath}` }
      const target = resolveInsideProject(project, filePath)
      ensureDir(path.dirname(target))
      fs.writeFileSync(target, String(file.content || ''), 'utf8')
      written.push({ path: filePath, bytes: Buffer.byteLength(String(file.content || ''), 'utf8') })
    }
    return { ok: true, output: `Created ${written.length} scaffold file(s).`, files: written, diff: action.diff || buildDiffForFiles(action.files || []) }
  }
  if (action.type === 'file_create' || action.type === 'file_update') {
    const filePath = normalizeRelPath(action.file_path)
    if (!project || !project.write_access) return { ok: false, error: 'project is not writable' }
    if (!canWritePath(project, filePath)) return { ok: false, error: `write path not allowed: ${filePath}` }
    if (isProtectedPath(project, filePath)) return { ok: false, error: `protected path blocked: ${filePath}` }
    const target = resolveInsideProject(project, filePath)
    ensureDir(path.dirname(target))
    fs.writeFileSync(target, String(action.content || ''), 'utf8')
    return { ok: true, output: `${action.type === 'file_create' ? 'Created' : 'Updated'} ${filePath}`, diff: action.diff || null }
  }
  if (action.type === 'write_file') {
    const filePath = normalizeRelPath(action.file_path || '')
    if (!filePath) return { ok: false, error: 'file_path required for write_file' }
    if (!project || !project.write_access) return { ok: false, error: 'project is not writable' }
    if (!canWritePath(project, filePath)) return { ok: false, error: `write path not allowed: ${filePath}` }
    if (isProtectedPath(project, filePath)) return { ok: false, error: `protected path blocked: ${filePath}` }
    const target = resolveInsideProject(project, filePath)
    if (fs.existsSync(target)) {
      const snapDir = path.join(safeProjectRoot(project), '.forge_snapshots')
      ensureDir(snapDir)
      fs.copyFileSync(target, path.join(snapDir, `${Date.now()}_${path.basename(filePath)}`))
    }
    ensureDir(path.dirname(target))
    const body = String(action.proposed_content ?? action.content ?? '')
    fs.writeFileSync(target, body, 'utf8')
    return { ok: true, output: `Wrote ${filePath} (${Buffer.byteLength(body, 'utf8')} bytes)`, diff: action.diff || null }
  }
  if (action.type === 'test_run') {
    return {
      ok: false,
      approval_required: true,
      output: 'Test command execution is staged. Shell execution must be wired through the supervised execution engine before it can run.',
    }
  }
  return { ok: false, approval_required: true, output: `${action.type} is staged but not executable in this safety profile yet.` }
}

const PYTHON_BACKEND_PORT_FORGE = process.env.PYTHON_BACKEND_PORT || 18790

// Shared system prompt for both the non-streaming and SSE message handlers.
// The filename-labelling rules are load-bearing: extractCodeActions falls back to
// generated_N.txt when the model omits a path, so the model MUST label every block.
function buildForgeSystemPrompt(project, treeSnippet, historySnippet) {
  return (
    `You are AscendForge, a supervised AI coding assistant.\n` +
    `Project: ${project?.name || 'unknown'} (${project?.package_type || 'generic'})\n` +
    (project ? `Root: ${safeProjectRoot(project)}\n` : '') +
    `Files (first 50):\n${treeSnippet}\n\n` +
    `Recent session:\n${historySnippet}\n\n` +
    `When you propose file content, you MUST start each code block's info string with the\n` +
    `relative file path, e.g.:\n` +
    '```python src/app.py\n<code>\n```\n' +
    `If you cannot determine a path, put the intended filename as the FIRST line of the code\n` +
    `as a comment (# path/to/file.py). Never omit the filename. One file per code block.\n` +
    `Keep explanations brief. Proposed writes require owner approval before execution.`
  )
}

function extractCodeActions(text, project) {
  const actions = []
  // Group 1: lang, group 2: optional path hint on the fence line, group 3: code body
  const codeBlockRe = /```([\w+]+)?(?:[ \t:]+([^\n`]+))?\n([\s\S]*?)```/g
  const extMap = {
    javascript: 'js', typescript: 'ts', jsx: 'jsx', tsx: 'tsx', python: 'py', rust: 'rs',
    css: 'css', html: 'html', json: 'json', bash: 'sh', shell: 'sh', sh: 'sh', go: 'go',
    java: 'java', yaml: 'yml', yml: 'yml', sql: 'sql', toml: 'toml', md: 'md',
  }
  const PATH_RE = /[\w./-]+\.[a-zA-Z0-9]{1,6}/
  let match
  let idx = 0
  while ((match = codeBlockRe.exec(text)) !== null) {
    const lang = (match[1] || 'txt').toLowerCase()
    const fenceHint = (match[2] || '').trim()
    const code = match[3]
    const ext = extMap[lang] || lang

    // 1. path declared on the fence line, e.g. ```js src/app.js  or  ```python:main.py
    let filePath = ''
    if (fenceHint && PATH_RE.test(fenceHint)) {
      filePath = fenceHint.replace(/^["'`]|["'`]$/g, '').replace(/^title=/, '').trim()
    }
    // 2. path mentioned in the line(s) just before the block (e.g. **src/app.js** or `src/app.js`)
    if (!filePath) {
      const before = text.slice(Math.max(0, match.index - 160), match.index)
      const m = before.match(/([`*#>\s])([\w./-]+\.[a-zA-Z0-9]{1,6})[`*:\s]*$/)
      if (m) filePath = m[2]
    }
    // 3. path from a leading comment on the first code line (# path  // path  <!-- path)
    if (!filePath) {
      const firstLine = (code.split('\n')[0] || '').trim()
      const m = firstLine.match(/^(?:#|\/\/|<!--|\/\*)\s*([\w./-]+\.[a-zA-Z0-9]{1,6})/)
      if (m) filePath = m[1]
    }
    // 4. fallback to a generated name
    if (!filePath) filePath = `generated_${idx + 1}.${ext}`
    filePath = filePath.replace(/^\.?\//, '')

    actions.push({
      id: crypto.randomUUID(),
      type: 'write_file',
      label: `Write ${filePath}`,
      file_path: filePath,
      description: code.slice(0, 100),
      status: 'pending_approval',
      risk_level: 'low',
      risk_score: 0.1,
      project_id: project?.id,
      proposed_content: code,
      content: code,
      language: lang,
      diff: `--- ${filePath}\n+++ ${filePath}\n${code.split('\n').map(l => '+' + l).join('\n')}`,
    })
    idx++
  }
  return actions
}

function _httpJson(url, payload, timeoutMs) {
  return new Promise(resolve => {
    const http = require('http')
    const body = JSON.stringify(payload)
    const req = http.request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: timeoutMs,
    }, response => {
      let text = ''
      response.on('data', chunk => { text += chunk })
      response.on('end', () => {
        try { resolve({ ok: response.statusCode < 400, status: response.statusCode, ...JSON.parse(text || '{}') }) }
        catch { resolve({ ok: false, error: 'parse_error', raw: text.slice(0, 200) }) }
      })
    })
    req.on('error', err => resolve({ ok: false, error: err.message }))
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, error: 'timeout' }) })
    req.write(body)
    req.end()
  })
}

function _replyText(d) {
  return d && (d.response || d.reply || d.content || d.answer || '')
}

// Calls the Python LLM backend; if that yields no usable reply (auth/LLM unavailable),
// falls back to direct local Ollama so AscendForge codegen works in local-first setups.
async function callPythonChat(message, timeoutMs = 30000) {
  const py = await _httpJson(`http://127.0.0.1:${PYTHON_BACKEND_PORT_FORGE}/api/chat`, { message }, timeoutMs)
  if (_replyText(py)) return { ok: true, ...py }

  // Fallback → direct Ollama. Forge codegen prefers a coding-specialized model.
  const host = (process.env.OLLAMA_HOST || 'http://localhost:11434').replace(/\/$/, '')
  const model = process.env.FORGE_OLLAMA_MODEL || process.env.OLLAMA_CODE_MODEL ||
    'qwen2.5-coder:14b'
  const og = await _httpJson(`${host}/api/generate`, { model, prompt: message, stream: false }, timeoutMs)
  if (og && og.response) return { ok: true, response: og.response, provider: 'ollama' }
  return { ok: false, error: py.error || og.error || 'no_reply' }
}

module.exports = function createForgeRouter(requireAuth) {
  const router = express.Router()
  const engine = getAscendForgeEngine()

  function requireOwnerApproval(req, res, action) {
    if (req.body?.ownerApproved === true || req.body?.approval === 'owner-approved') return true
    res.status(403).json({ ok: false, state: 'disabled', action, error: 'owner approval required', approval_required: true })
    return false
  }

  router.get('/engine/status', requireAuth, async (_req, res) => {
    const status = engine.getStatus()
    res.json({
      ...status,
      persistence: 'file_state',
      projects_total: loadProjects().length,
      sessions_total: loadSessions().length,
      plans_total: loadPlans().length,
      actions_total: loadActions().length,
      python_forge: fs.existsSync(PYTHON_FORGE_SCRIPT) ? 'available' : 'missing',
    })
  })

  router.post('/skills/recommend', requireAuth, (req, res) => {
    res.json(engine.recommendSkills(req.body || {}))
  })

  router.post('/plan', requireAuth, (req, res) => {
    try {
      const project = req.body?.project_id ? findProject(req.body.project_id) : null
      if (req.body?.project_id && !project) return res.status(404).json({ ok: false, error: 'project not found' })
      const plan = createPlan(engine, project, req.body || {})
      const actions = actionsForPlan(plan, project, req.body || {})
      res.json({ ok: true, state: 'live', plan, actions })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  router.get('/plans', requireAuth, (req, res) => {
    const projectId = req.query.project_id
    const plans = projectId ? loadPlans().filter(plan => plan.project_id === projectId) : loadPlans()
    res.json({ ok: true, state: 'live', plans })
  })

  router.get('/actions', requireAuth, (req, res) => {
    const projectId = req.query.project_id
    const actions = projectId ? loadActions().filter(action => action.project_id === projectId) : loadActions()
    res.json({ ok: true, state: 'live', actions })
  })

  router.post('/agents/blueprint', requireAuth, (req, res) => {
    try {
      res.json(engine.createBlueprint(req.body || {}))
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  router.get('/agents/blueprints', requireAuth, (_req, res) => {
    res.json({ ok: true, state: 'live', blueprints: engine.listBlueprints() })
  })

  router.post('/agents/:id/register', requireAuth, (req, res) => {
    if (!requireOwnerApproval(req, res, 'register_ascendforge_agent')) return
    try {
      res.json(engine.registerBlueprint(req.params.id, req.body || {}))
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: err.status === 403 ? 'disabled' : 'degraded', error: err.message, approval_required: !!err.approval_required })
    }
  })

  router.post('/execute', requireAuth, (req, res) => {
    try {
      res.json(engine.execute(req.body || {}))
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  router.get('/projects', requireAuth, (_req, res) => {
    res.json({ ok: true, state: 'live', projects: loadProjects() })
  })

  router.post('/projects', requireAuth, (req, res) => {
    const name = String(req.body?.name || '').trim()
    const template = String(req.body?.template || 'web-app')
    if (!name) return res.status(400).json({ ok: false, error: 'name required' })
    const id = crypto.randomUUID()
    const rootPath = path.join(FORGE_HOME, 'projects', id)
    ensureDir(rootPath)
    const project = {
      id,
      name,
      target_type: 'scratch_project',
      root_path: rootPath,
      path: rootPath,
      allowed_write_paths: ['.'],
      write_access: true,
      template,
      package_type: template,
      verification_commands: defaultVerificationCommands({ target_type: 'scratch_project', template, root_path: rootPath }),
      policy_profile: 'supervised_builder',
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    updateProject(project)
    const files = scaffoldFiles(template, name)
    const plan = createPlan(engine, project, { goal: `Create ${template} scaffold for ${name}`, provider: req.body?.provider, scaffold_files: files })
    const actions = actionsForPlan(plan, project, { scaffold_files: files })
    appendAudit('forge_project_created', { id, name, template, root_path: rootPath })
    res.json({ ok: true, state: 'live', project, plan, actions, message: 'Project registered. Scaffold files are staged for owner approval.' })
  })

  router.post('/projects/import', requireAuth, (req, res) => {
    const name = String(req.body?.name || path.basename(String(req.body?.path || 'project'))).trim()
    const root = path.resolve(String(req.body?.path || ''))
    if (!root || !fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
      return res.status(400).json({ ok: false, error: 'valid directory path required' })
    }
    const project = {
      id: crypto.randomUUID(),
      name,
      target_type: root === REPO_ROOT ? 'internal_repo' : 'external_local_repo',
      root_path: root,
      path: root,
      allowed_write_paths: req.body?.allowed_write_paths || [],
      write_access: false,
      package_type: inferPackageType({ root_path: root }),
      verification_commands: req.body?.verification_commands || defaultVerificationCommands({ target_type: root === REPO_ROOT ? 'internal_repo' : 'external_local_repo', root_path: root }),
      policy_profile: 'read_only_until_owner_approval',
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    updateProject(project)
    appendAudit('forge_project_imported_read_only', { id: project.id, root_path: root, target_type: project.target_type })
    res.json({ ok: true, state: 'live', project, tree: buildTree(root) })
  })

  router.delete('/projects/:id', requireAuth, (req, res) => {
    saveProjects(loadProjects().filter(project => project.id !== req.params.id))
    appendAudit('forge_project_removed', { id: req.params.id })
    res.json({ ok: true })
  })

  router.get('/files/tree', requireAuth, (req, res) => {
    const project = findProject(req.query.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, tree: buildTree(safeProjectRoot(project)) })
  })

  router.get('/files/read', requireAuth, (req, res) => {
    try {
      const project = findProject(req.query.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      const filePath = normalizeRelPath(req.query.file_path)
      const abs = resolveInsideProject(project, filePath)
      if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) return res.status(404).json({ ok: false, error: 'file not found' })
      res.json({ ok: true, file_path: filePath, content: fs.readFileSync(abs, 'utf8'), writable: canWritePath(project, filePath) && !isProtectedPath(project, filePath) })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, error: err.message })
    }
  })

  router.post('/files/write', requireAuth, (req, res) => {
    try {
      const project = findProject(req.body?.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      const filePath = normalizeRelPath(req.body?.file_path || '')
      const content  = req.body?.content
      if (typeof content !== 'string') return res.status(400).json({ ok: false, error: 'content must be string' })
      const abs = resolveInsideProject(project, filePath)
      if (!canWritePath(project, filePath)) return res.status(403).json({ ok: false, error: 'path not writable' })
      if (isProtectedPath(project, filePath)) return res.status(403).json({ ok: false, error: 'path is protected' })
      // snapshot before overwrite
      const snapDir = path.join(safeProjectRoot(project), '.forge_snapshots')
      fs.mkdirSync(snapDir, { recursive: true })
      if (fs.existsSync(abs)) {
        const snap = path.join(snapDir, `${Date.now()}_${path.basename(filePath)}`)
        fs.copyFileSync(abs, snap)
      }
      fs.mkdirSync(path.dirname(abs), { recursive: true })
      fs.writeFileSync(abs, content, 'utf8')
      appendAudit('forge_file_written', { project_id: project.id, file_path: filePath, size: content.length })
      res.json({ ok: true, file_path: filePath, size: content.length, snapshot_created: true })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, error: err.message })
    }
  })

  router.post('/sessions', requireAuth, (req, res) => {
    const projectId = req.body?.project_id
    const project = findProject(projectId)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const sessions = loadSessions()
    const existing = sessions.find(session => session.project_id === projectId && session.provider === (req.body?.provider || 'local'))
    if (existing) return res.json({ ok: true, session_id: existing.id, history: existing.history || [], plan: loadPlans().find(plan => plan.id === existing.current_plan_id) || null })
    const session = {
      id: crypto.randomUUID(),
      project_id: projectId,
      provider: req.body?.provider || 'local',
      history: [],
      current_plan_id: null,
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    saveSessions([session, ...sessions])
    appendAudit('forge_session_created', { id: session.id, project_id: projectId, provider: session.provider })
    res.json({ ok: true, session_id: session.id, history: [] })
  })

  router.post('/sessions/:id/messages', requireAuth, async (req, res) => {
    const sessions = loadSessions()
    const session = sessions.find(item => item.id === req.params.id)
    if (!session) return res.status(404).json({ ok: false, error: 'session not found' })
    const project = findProject(session.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const content = String(req.body?.content || '').trim()
    if (!content) return res.status(400).json({ ok: false, error: 'content required' })

    session.history = [...(session.history || []), { role: 'user', content, ts: nowIso() }]

    // Build project context for the AI prompt
    const treeEntries = buildTree(safeProjectRoot(project))
    const flatTree = []
    const flattenTree = (nodes) => { for (const n of nodes) { flatTree.push(n.path); if (n.children) flattenTree(n.children) } }
    flattenTree(treeEntries)
    const treeSnippet = flatTree.slice(0, 50).join('\n')

    const recentHistory = (session.history || []).slice(-4).filter(m => m.role !== 'assistant' || !m.plan)
    const historySnippet = recentHistory.map(m => `${m.role}: ${String(m.content || '').slice(0, 300)}`).join('\n')

    const systemPrompt = buildForgeSystemPrompt(project, treeSnippet, historySnippet)

    const aiMessage = `${systemPrompt}\n\nUser: ${content}`

    let aiText = null
    try {
      const aiResult = await callPythonChat(aiMessage)
      aiText = aiResult?.response || aiResult?.reply || null
    } catch (_) { /* fall through to synthetic plan */ }

    let plan, actions, assistantContent

    if (aiText) {
      // Extract code blocks as proposed write_file actions
      const codeActions = extractCodeActions(aiText, project)
      plan = createPlan(engine, project, { goal: content, provider: session.provider })
      // Persist AI-derived actions alongside the standard preflight actions
      const preflightActions = actionsForPlan(plan, project, {})
      for (const ca of codeActions) {
        ca.plan_id = plan.id
        ca.approval_required = true
        ca.risk = 'caution'
        ca.expected_result = 'File written to project root after owner approval.'
        ca.rollback_plan = 'Snapshot created automatically before any overwrite.'
        ca.created_at = nowIso()
        ca.updated_at = nowIso()
        ca.policy_decision = { decision: 'requires_approval', risk: 'caution' }
      }
      if (codeActions.length) {
        const stored = loadActions()
        saveActions([...codeActions, ...stored])
        for (const ca of codeActions) appendAudit('forge_action_proposed', { id: ca.id, type: ca.type, risk: ca.risk, project_id: ca.project_id })
      }
      actions = [...preflightActions, ...codeActions]
      assistantContent = aiText
    } else {
      // Python backend unavailable — fall back to synthetic plan
      plan = createPlan(engine, project, { goal: content, provider: session.provider })
      actions = actionsForPlan(plan, project, {})
      assistantContent = `Plan created for "${content}". Risk: ${plan.risk_level}. ${actions.length} supervised action(s) are ready for review.`
    }

    session.current_plan_id = plan.id
    const assistant = { role: 'assistant', ts: nowIso(), content: assistantContent, plan, actions }
    session.history.push(assistant)
    saveSessions(sessions.map(item => item.id === session.id ? { ...session, updated_at: nowIso() } : item))
    res.json({ ok: true, state: 'live', message: assistant, plan, actions, diff: actions.find(action => action.diff)?.diff || null })
  })

  router.post('/sessions/:id/messages/stream', requireAuth, async (req, res) => {
    const sessions = loadSessions()
    const session = sessions.find(s => s.id === req.params.id)
    if (!session) return res.status(404).json({ ok: false, error: 'session not found' })
    const project = findProject(session.project_id)
    const content = String(req.body?.content || '').trim()
    if (!content) return res.status(400).json({ ok: false, error: 'content required' })

    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Cache-Control', 'no-cache')
    res.setHeader('Connection', 'keep-alive')
    res.setHeader('X-Accel-Buffering', 'no')
    res.flushHeaders()

    const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)

    session.history = [...(session.history || []), { role: 'user', content, ts: nowIso() }]
    saveSessions(sessions.map(s => s.id === session.id ? { ...session, updated_at: nowIso() } : s))

    const flatTree = []
    const flattenTree = (nodes) => { for (const n of nodes) { flatTree.push(n.path); if (n.children) flattenTree(n.children) } }
    if (project) flattenTree(buildTree(safeProjectRoot(project)))
    const treeSnippet = flatTree.slice(0, 50).join('\n')
    const historySnippet = (session.history || []).slice(-6).map(m => `${m.role}: ${String(m.content || '').slice(0, 300)}`).join('\n')

    const systemPrompt = buildForgeSystemPrompt(project, treeSnippet, historySnippet)

    try {
      const aiResult = await callPythonChat(`${systemPrompt}\n\nUser: ${content}`)
      const text = aiResult?.response || aiResult?.reply || aiResult?.content ||
        `I'll help with: "${content}". Please ensure the Python AI backend is running for full AI responses.`

      // Stream in 3-word chunks at ~30 ms cadence to simulate token streaming
      const words = text.split(' ')
      let i = 0
      await new Promise(resolve => {
        const tick = setInterval(() => {
          const chunk = words.slice(i, i + 3).join(' ')
          if (chunk) send('token', { text: (i > 0 ? ' ' : '') + chunk })
          i += 3
          if (i >= words.length) {
            clearInterval(tick)
            resolve()
          }
        }, 30)
      })

      const actions = extractCodeActions(text, project)
      for (const a of actions) {
        a.approval_required = true
        a.risk = 'caution'
        a.expected_result = 'File written to project root after owner approval.'
        a.rollback_plan = 'Snapshot created automatically before any overwrite.'
        a.created_at = nowIso()
        a.updated_at = nowIso()
        a.policy_decision = { decision: 'requires_approval', risk: 'caution' }
      }
      if (actions.length) {
        const stored = loadActions()
        saveActions([...actions, ...stored])
        for (const a of actions) appendAudit('forge_action_proposed', { id: a.id, type: a.type, risk: a.risk, project_id: a.project_id })
      }

      const assistant = { role: 'assistant', ts: nowIso(), content: text, actions }
      session.history.push(assistant)
      saveSessions(loadSessions().map(s => s.id === session.id ? { ...session, updated_at: nowIso() } : s))

      send('done', { content: text, actions })
    } catch (err) {
      send('error', { error: err.message })
    }
    res.end()
  })

  router.post('/actions/:id/approve', requireAuth, async (req, res) => {
    const action = findAction(req.params.id)
    if (!action) return res.status(404).json({ ok: false, error: 'action not found' })
    if (action.status === 'completed') return res.status(409).json({ ok: false, error: 'action already completed', action })
    if (action.approval_required && !requireOwnerApproval(req, res, `approve_${action.type}`)) return
    const project = action.project_id ? findProject(action.project_id) : null
    updateAction(action.id, { status: 'approved', approved_at: nowIso(), approved_by: req.user?.email || 'operator' })
    appendAudit('forge_action_approved', { id: action.id, type: action.type, project_id: action.project_id })
    try {
      const result = await executeAction(action, project)
      const ok = result.ok !== false
      const updated = updateAction(action.id, {
        status: ok ? 'completed' : 'failed',
        executed_at: nowIso(),
        result,
      })
      appendAudit(ok ? 'forge_action_completed' : 'forge_action_failed', { id: action.id, type: action.type, result: { ok, error: result.error } })
      res.status(ok ? 200 : 409).json({ ok, state: ok ? 'live' : 'degraded', action: updated, output: result.output || result.error || 'action processed', diff: result.diff || action.diff || null, result })
    } catch (err) {
      const updated = updateAction(action.id, { status: 'failed', error: err.message, result: { ok: false, error: err.message } })
      appendAudit('forge_action_failed', { id: action.id, type: action.type, error: err.message })
      res.status(err.status || 500).json({ ok: false, state: 'degraded', action: updated, error: err.message })
    }
  })

  router.post('/actions/:id/reject', requireAuth, (req, res) => {
    const action = findAction(req.params.id)
    if (!action) return res.status(404).json({ ok: false, error: 'action not found' })
    const updated = updateAction(action.id, { status: 'rejected', rejected_at: nowIso(), rejected_by: req.user?.email || 'operator', reject_reason: req.body?.reason || '' })
    appendAudit('forge_action_rejected', { id: action.id, type: action.type, reason: req.body?.reason || '' })
    res.json({ ok: true, state: 'live', action: updated })
  })

  router.post('/sandbox', requireAuth, async (req, res) => {
    const goal = String(req.body?.goal || '').trim()
    if (!goal) return res.status(400).json({ ok: false, error: 'goal required' })
    const result = await runForgePython({ operation: 'sandbox', goal, module_path: req.body?.module_path || 'forge_sandbox_test' })
    res.status(result?.ok === false ? 500 : 200).json({ ok: result?.ok !== false, state: result?.ok === false ? 'degraded' : 'live', ...result })
  })

  router.post('/rollback', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_rollback')) return
    const snapshotId = String(req.body?.snapshot_id || '').trim()
    if (!snapshotId) return res.status(400).json({ ok: false, error: 'snapshot_id required' })
    const result = await runForgePython({ operation: 'rollback', snapshot_id: snapshotId })
    appendAudit('forge_rollback_requested', { snapshot_id: snapshotId, result })
    res.status(result?.ok === false || result?.success === false ? 409 : 200).json({ ok: result?.ok !== false && result?.success !== false, state: result?.success === false ? 'degraded' : 'live', ...result })
  })

  router.get('/snapshots', requireAuth, async (_req, res) => {
    const result = await runForgePython({ operation: 'snapshots' })
    res.json(result?.operation ? result : { operation: 'snapshots', snapshots: [], summary: {}, error: result?.error || null })
  })

  router.get('/queue', requireAuth, (_req, res) => {
    const pending = loadActions().filter(action => ['proposed', 'approved'].includes(action.status))
    res.json({ ok: true, state: 'live', items: pending, total: pending.length })
  })

  router.get('/status', requireAuth, (_req, res) => {
    res.json({
      ok: true,
      state: 'live',
      mode: 'supervised',
      active: true,
      queue_depth: loadActions().filter(action => action.status === 'proposed').length,
      projects_total: loadProjects().length,
      plans_total: loadPlans().length,
      persistence: 'file_state',
      approval_policy: DEFAULT_APPROVAL_POLICY,
    })
  })

  return router
}
