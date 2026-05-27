/**
 * /api/forge — canonical AscendForge supervised build pipeline.
 *
 * This router owns the desktop-facing Forge contract. Python ForgeController
 * remains the execution safety layer for sandbox/snapshot/rollback operations,
 * while Node owns persistent project/session/plan/action state for the UI.
 *
 * Mount order is part of the compatibility contract: server.js mounts this
 * router before legacy inline /api/forge handlers, so routes defined here win
 * and legacy-only aliases continue to work behind it.
 */
'use strict'

const express = require('express')
const path = require('path')
const fs = require('fs')
const os = require('os')
const crypto = require('crypto')
const { spawn, spawnSync } = require('child_process')
const { getAscendForgeEngine, DEFAULT_APPROVAL_POLICY } = require('../ascendforge/engine')
const { getSandboxExecutor } = require('../infra/sandbox/executor')
const { ForgeStore } = require('../services/forge_store')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const STATE_DIR = path.resolve(process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR || path.join(os.homedir(), '.ai-employee', 'state'))
const FORGE_HOME = path.resolve(process.env.AI_EMPLOYEE_FORGE_HOME || path.join(STATE_DIR, 'forge'))
const PROJECTS_FILE = path.join(FORGE_HOME, 'projects.json')
const SESSIONS_FILE = path.join(FORGE_HOME, 'sessions.json')
const PLANS_FILE = path.join(FORGE_HOME, 'plans.json')
const ACTIONS_FILE = path.join(FORGE_HOME, 'actions.json')
const RUNS_FILE = path.join(FORGE_HOME, 'runs.json')
const RUN_WORKSPACES_DIR = path.join(FORGE_HOME, 'runs')
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
const RUN_WRITE_ACTIONS = new Set(['write_file', 'file_create', 'file_update', 'scaffold_create'])
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
const SECRET_PATH_PATTERNS = [
  /(^|\/)\.env($|\.)/i,
  /(^|\/)\.ssh\//i,
  /(^|\/)\.aws\//i,
  /secret/i,
  /credential/i,
  /\.pem$/i,
  /\.key$/i,
]
const BLOCKED_CODE_PATTERNS = [
  /\beval\s*\(/,
  /\bexec\s*\(/,
  /\b__import__\s*\(/,
  /\bos\.system\s*\(/,
  /\bsubprocess\.(run|Popen|call|check_output|check_call)\s*\(/,
  /\bshutil\.rmtree\s*\(/,
  /\bfs\.rmSync\s*\(/,
  /\bchild_process\b/,
  /\bfetch\s*\(\s*['"]https?:\/\//,
  /\brequests\.(get|post|put|delete|patch)\s*\(\s*['"]https?:\/\//,
]
const MAX_RUNS = 500
const MAX_STAGED_COPY_FILES = 2500
const MAX_STAGED_COPY_BYTES = 50 * 1024 * 1024
const forgeRunStore = new ForgeStore({ forgeHome: FORGE_HOME, runsFile: RUNS_FILE, maxRuns: MAX_RUNS })

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
  forgeRunStore.recordAudit(event, details)
}

function nowIso() {
  return new Date().toISOString()
}

function latestVerificationPassed(run) {
  const latest = Array.isArray(run?.test_results) ? run.test_results.slice(-1)[0] : null
  return latest ? latest.all_passed === true : null
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
function loadRuns() { return forgeRunStore.loadRuns() }
function saveRuns(list) { forgeRunStore.saveRuns(list) }

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

function findRun(id) {
  return forgeRunStore.findRun(id)
}

function updateRun(id, patch) {
  return forgeRunStore.updateRun(id, patch)
}

function upsertRun(run) {
  return forgeRunStore.upsertRun(run)
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

function flattenTreePaths(nodes, out = []) {
  for (const node of nodes || []) {
    if (node.path) out.push(node.path)
    if (node.children) flattenTreePaths(node.children, out)
  }
  return out
}

function actionFiles(action) {
  if (Array.isArray(action.files)) return action.files.map(file => normalizeRelPath(file.path)).filter(Boolean)
  const filePath = normalizeRelPath(action.file_path || action.path || '')
  return filePath ? [filePath] : []
}

function actionContentForPath(action, relPath) {
  if (Array.isArray(action.files)) {
    const found = action.files.find(file => normalizeRelPath(file.path) === relPath)
    return String(found?.content || '')
  }
  return String(action.proposed_content ?? action.content ?? '')
}

function countChangedLines(action) {
  const text = Array.isArray(action.files)
    ? action.files.map(file => String(file.content || '')).join('\n')
    : String(action.proposed_content ?? action.content ?? '')
  return text.split('\n').length
}

function validateRunActionPolicy(action, project) {
  const violations = []
  const files = actionFiles(action)
  const content = Array.isArray(action.files)
    ? action.files.map(file => String(file.content || '')).join('\n')
    : String(action.proposed_content ?? action.content ?? '')
  if (!project) violations.push({ rule: 'project_required', message: 'Project not found for action.' })
  if (!RUN_WRITE_ACTIONS.has(action.type)) {
    violations.push({ rule: 'unsupported_action', message: `Run apply supports staged write actions only: ${action.type}` })
  }
  if (!files.length) violations.push({ rule: 'file_required', message: 'Write action has no target file.' })
  for (const filePath of files) {
    if (filePath.startsWith('..') || path.isAbsolute(filePath)) {
      violations.push({ rule: 'path_escape', file: filePath, message: 'Path must stay inside the project root.' })
      continue
    }
    try {
      if (project) resolveInsideProject(project, filePath)
    } catch (err) {
      violations.push({ rule: 'path_escape', file: filePath, message: err.message })
    }
    if (project && !canWritePath(project, filePath)) {
      violations.push({ rule: 'write_scope', file: filePath, message: 'Path is outside approved write scope.' })
    }
    if (project && isProtectedPath(project, filePath)) {
      violations.push({ rule: 'protected_path', file: filePath, message: 'Protected system path requires a separate manual change.' })
    }
    if (SECRET_PATH_PATTERNS.some(pattern => pattern.test(filePath))) {
      violations.push({ rule: 'secret_path', file: filePath, message: 'Secret/config path is blocked by default.' })
    }
  }
  if (countChangedLines(action) > 300) {
    violations.push({ rule: 'patch_too_large', message: 'Staged action exceeds the V1 300-line limit.' })
  }
  for (const pattern of BLOCKED_CODE_PATTERNS) {
    if (pattern.test(content)) {
      violations.push({ rule: 'dangerous_code', message: `Blocked code pattern: ${pattern.source}` })
    }
  }
  const risk = violations.length ? 'high' : (files.length > 3 || countChangedLines(action) > 100 ? 'medium' : 'low')
  return {
    allowed: violations.length === 0,
    decision: violations.length === 0 ? 'requires_approval' : 'blocked',
    risk_level: risk,
    files,
    lines_changed: countChangedLines(action),
    violations,
  }
}

function runWorkspaceRoot(runId) {
  return path.join(RUN_WORKSPACES_DIR, runId, 'workspace')
}

function copyProjectToWorkspace(project, workspaceRoot) {
  const srcRoot = safeProjectRoot(project)
  ensureDir(workspaceRoot)
  let copiedFiles = 0
  let copiedBytes = 0

  const copyDir = (src, dest) => {
    if (copiedFiles >= MAX_STAGED_COPY_FILES || copiedBytes >= MAX_STAGED_COPY_BYTES) return
    ensureDir(dest)
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
      if (PROJECT_SKIP.has(entry.name) || entry.name.startsWith('.forge_')) continue
      const from = path.join(src, entry.name)
      const to = path.join(dest, entry.name)
      if (entry.isDirectory()) {
        copyDir(from, to)
        continue
      }
      if (!entry.isFile()) continue
      const stat = fs.statSync(from)
      if (copiedFiles + 1 > MAX_STAGED_COPY_FILES || copiedBytes + stat.size > MAX_STAGED_COPY_BYTES) return
      ensureDir(path.dirname(to))
      fs.copyFileSync(from, to)
      copiedFiles += 1
      copiedBytes += stat.size
    }
  }

  copyDir(srcRoot, workspaceRoot)
  return { copied_files: copiedFiles, copied_bytes: copiedBytes, truncated: copiedFiles >= MAX_STAGED_COPY_FILES || copiedBytes >= MAX_STAGED_COPY_BYTES }
}

function runGit(root, args, timeoutMs = 10000) {
  const result = spawnSync('git', ['-C', root, ...args], {
    encoding: 'utf8',
    timeout: timeoutMs,
    maxBuffer: 1024 * 1024,
  })
  return {
    ok: result.status === 0,
    status: result.status,
    stdout: String(result.stdout || '').trim(),
    stderr: String(result.stderr || result.error?.message || '').trim(),
  }
}

function gitWorkspaceSource(project) {
  const root = safeProjectRoot(project)
  const inside = runGit(root, ['rev-parse', '--is-inside-work-tree'])
  if (!inside.ok || inside.stdout !== 'true') return { ok: false, reason: 'not_git_repo' }
  const top = runGit(root, ['rev-parse', '--show-toplevel'])
  if (!top.ok || !top.stdout) return { ok: false, reason: 'git_root_unavailable', detail: top.stderr }
  const status = runGit(top.stdout, ['status', '--porcelain'])
  if (!status.ok) return { ok: false, reason: 'git_status_failed', detail: status.stderr }
  if (status.stdout) return { ok: false, reason: 'dirty_source_tree' }
  const head = runGit(top.stdout, ['rev-parse', '--verify', 'HEAD'])
  if (!head.ok || !head.stdout) return { ok: false, reason: 'head_unavailable', detail: head.stderr }
  return { ok: true, root: top.stdout, head: head.stdout }
}

function createGitWorktreeWorkspace(project, workspaceRoot) {
  const source = gitWorkspaceSource(project)
  if (!source.ok) return { ok: false, reason: source.reason, detail: source.detail || null }
  ensureDir(path.dirname(workspaceRoot))
  const added = runGit(source.root, ['worktree', 'add', '--detach', workspaceRoot, source.head], 60000)
  if (!added.ok) {
    return { ok: false, reason: 'worktree_add_failed', detail: added.stderr || added.stdout }
  }
  return {
    ok: true,
    workspace_mode: 'git_worktree',
    git_root: source.root,
    git_head: source.head,
    created_from: source.head,
  }
}

function ensureRunWorkspace(run, project) {
  const workspace = runWorkspaceRoot(run.id)
  if (fs.existsSync(path.join(workspace, '.forge_workspace.json'))) return workspace
  if (fs.existsSync(workspace)) removeRunWorkspace(run.id)
  let workspaceInfo = createGitWorktreeWorkspace(project, workspace)
  if (!workspaceInfo.ok) {
    const copy = copyProjectToWorkspace(project, workspace)
    workspaceInfo = {
      workspace_mode: 'directory_copy',
      fallback_reason: workspaceInfo.reason || 'worktree_unavailable',
      fallback_detail: workspaceInfo.detail || null,
      ...copy,
    }
  }
  fs.writeFileSync(path.join(workspace, '.forge_workspace.json'), JSON.stringify({
    run_id: run.id,
    project_id: project.id,
    source_root: safeProjectRoot(project),
    created_at: nowIso(),
    ...workspaceInfo,
  }, null, 2))
  return workspace
}

function resolveInsideWorkspace(workspaceRoot, relativePath) {
  const target = path.resolve(workspaceRoot, normalizeRelPath(relativePath))
  if (target !== workspaceRoot && !target.startsWith(workspaceRoot + path.sep)) {
    const err = new Error('path escapes run workspace')
    err.status = 403
    throw err
  }
  return target
}

function readWorkspaceMetadata(workspaceRoot) {
  return readJson(path.join(workspaceRoot, '.forge_workspace.json'), null)
}

function removeRunWorkspace(runId) {
  const workspace = runWorkspaceRoot(runId)
  const runDir = path.dirname(workspace)
  const meta = readWorkspaceMetadata(workspace)
  if (meta?.workspace_mode === 'git_worktree' && meta.git_root) {
    const removed = runGit(meta.git_root, ['worktree', 'remove', '--force', workspace], 60000)
    if (!removed.ok && fs.existsSync(workspace)) fs.rmSync(workspace, { recursive: true, force: true })
    runGit(meta.git_root, ['worktree', 'prune'], 60000)
  } else if (fs.existsSync(workspace)) {
    fs.rmSync(workspace, { recursive: true, force: true })
  }
  if (fs.existsSync(runDir)) fs.rmSync(runDir, { recursive: true, force: true })
  return { workspace, workspace_mode: meta?.workspace_mode || 'unknown' }
}

function stageRunAction(run, project, action) {
  const policy = validateRunActionPolicy(action, project)
  if (!policy.allowed) return { ok: false, policy }
  const workspace = ensureRunWorkspace(run, project)
  const stagedFiles = []
  for (const rel of policy.files) {
    const target = resolveInsideWorkspace(workspace, rel)
    ensureDir(path.dirname(target))
    const content = actionContentForPath(action, rel)
    fs.writeFileSync(target, content, 'utf8')
    stagedFiles.push({ path: rel, bytes: Buffer.byteLength(content, 'utf8') })
  }
  return { ok: true, policy, workspace, workspace_meta: readWorkspaceMetadata(workspace), staged_files: stagedFiles }
}

function applyStagedRun(run, project) {
  const workspace = runWorkspaceRoot(run.id)
  if (!fs.existsSync(workspace)) return { ok: false, error: 'run workspace missing' }
  const approvedActions = (run.actions || []).filter(action => RUN_WRITE_ACTIONS.has(action.type) && ['approved', 'staged', 'verified'].includes(action.status))
  if (!approvedActions.length) return { ok: false, error: 'no approved staged write actions' }
  const applied = []
  const snapshots = []
  const workspaceMeta = readWorkspaceMetadata(workspace)
  for (const action of approvedActions) {
    for (const rel of actionFiles(action)) {
      const staged = resolveInsideWorkspace(workspace, rel)
      if (!fs.existsSync(staged)) return { ok: false, error: `staged file missing: ${rel}` }
      const target = resolveInsideProject(project, rel)
      if (!canWritePath(project, rel) || isProtectedPath(project, rel)) return { ok: false, error: `blocked target: ${rel}` }
      const snapDir = path.join(safeProjectRoot(project), '.forge_snapshots')
      ensureDir(snapDir)
      if (fs.existsSync(target)) {
        const snap = path.join(snapDir, `${Date.now()}_${path.basename(rel)}`)
        fs.copyFileSync(target, snap)
        snapshots.push({ path: rel, snapshot: snap })
      }
      ensureDir(path.dirname(target))
      fs.copyFileSync(staged, target)
      applied.push({ path: rel, bytes: fs.statSync(target).size })
    }
  }
  return { ok: true, applied, snapshots, workspace_meta: workspaceMeta }
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
    let codeBody = code
    if (!filePath) {
      const firstLine = (code.split('\n')[0] || '').trim()
      const m = firstLine.match(/^(?:#|\/\/|<!--|\/\*)\s*([\w./-]+\.[a-zA-Z0-9]{1,6})/)
      if (m) {
        filePath = m[1]
        // Strip the path-hint comment line from the code body
        codeBody = code.split('\n').slice(1).join('\n').replace(/^\n/, '')
      }
    }
    // 4. fallback to a generated name
    if (!filePath) filePath = `generated_${idx + 1}.${ext}`
    filePath = filePath.replace(/^\.?\//, '')

    actions.push({
      id: crypto.randomUUID(),
      type: 'write_file',
      label: `Write ${filePath}`,
      file_path: filePath,
      description: codeBody.slice(0, 100),
      status: 'pending_approval',
      risk_level: 'low',
      risk_score: 0.1,
      project_id: project?.id,
      proposed_content: codeBody,
      content: codeBody,
      language: lang,
      diff: `--- ${filePath}\n+++ ${filePath}\n${codeBody.split('\n').map(l => '+' + l).join('\n')}`,
    })
    idx++
  }
  return actions
}

function _httpJson(url, payload, timeoutMs, extraHeaders = {}) {
  return new Promise(resolve => {
    const http = require('http')
    const body = JSON.stringify(payload)
    const req = http.request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), ...extraHeaders },
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

// Short-lived service token so Node→Python code-index calls pass the zero-trust
// RequestGuard. Signed with the shared JWT secret; cached ~5 min.
let _ciToken = null
let _ciTokenExp = 0
function _codeIndexToken() {
  const now = Date.now()
  if (_ciToken && now < _ciTokenExp) return _ciToken
  const secret = process.env.JWT_SECRET_KEY || process.env.JWT_SECRET
  if (!secret) return null
  try {
    const jwt = require('jsonwebtoken')
    _ciToken = jwt.sign({ type: 'access', role: 'service', iss: 'ai-employee', tenant_id: 'default', svc: 'forge-index' },
      secret, { algorithm: 'HS256', expiresIn: '10m', subject: 'svc:forge' })
    _ciTokenExp = now + 5 * 60 * 1000
    return _ciToken
  } catch { return null }
}

// Code-index calls go to the venv FastAPI backend (vector store lives there, not
// in run_forge.py's bare python3). Best-effort: returns {ok:false} if backend down.
function callCodeIndex(suffix, payload, timeoutMs = 120000) {
  const token = _codeIndexToken()
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  return _httpJson(`http://127.0.0.1:${PYTHON_BACKEND_PORT_FORGE}/api/code-index/${suffix}`, payload, timeoutMs, headers)
}

function getCodeIndexSummary(projectId, timeoutMs = 8000) {
  return new Promise(resolve => {
    const http = require('http')
    const token = _codeIndexToken()
    const req = http.get(`http://127.0.0.1:${PYTHON_BACKEND_PORT_FORGE}/api/code-index/summary/${projectId}`, {
      timeout: timeoutMs,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }, resp => {
      let text = ''
      resp.on('data', chunk => { text += chunk })
      resp.on('end', () => {
        try { resolve({ ok: resp.statusCode < 400, status: resp.statusCode, ...JSON.parse(text || '{}') }) }
        catch { resolve({ ok: false, error: 'parse_error' }) }
      })
    })
    req.on('error', err => resolve({ ok: false, error: err.message }))
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, error: 'timeout' }) })
  })
}

// Retrieve the most relevant code snippets for a goal, formatted for the prompt.
async function retrieveForgeContext(project, query) {
  try {
    const r = await callCodeIndex('context', { project_id: project.id, query, k: 6 }, 20000)
    if (!r?.ok || !Array.isArray(r.results) || !r.results.length) return ''
    const blocks = r.results.map(h => `--- ${h.path}${h.symbol ? ` :: ${h.symbol}` : ''} ---\n${(h.snippet || '').slice(0, 900)}`).join('\n\n')
    return `\nRelevant existing code (retrieved from the indexed project — read before editing):\n${blocks}\n`
  } catch { return '' }
}

async function buildContextPack(project, goal, payload = {}) {
  const tree = buildTree(safeProjectRoot(project))
  const flatTree = flattenTreePaths(tree).slice(0, 200)
  const [summary, context] = await Promise.allSettled([
    getCodeIndexSummary(project.id),
    callCodeIndex('context', { project_id: project.id, query: goal, k: Number(payload.k) || 6 }, 20000),
  ])
  const sessions = loadSessions()
    .filter(session => session.project_id === project.id)
    .slice(0, 3)
    .map(session => ({
      id: session.id,
      provider: session.provider,
      recent: (session.history || []).slice(-4).map(item => ({
        role: item.role,
        content: String(item.content || '').slice(0, 500),
        ts: item.ts,
      })),
    }))
  const summaryValue = summary.status === 'fulfilled' ? summary.value : { ok: false, error: 'summary unavailable' }
  const contextValue = context.status === 'fulfilled' ? context.value : { ok: false, results: [], error: 'context unavailable' }
  return {
    goal,
    project: {
      id: project.id,
      name: project.name,
      target_type: project.target_type,
      package_type: project.package_type,
      write_access: !!project.write_access,
      allowed_write_paths: project.allowed_write_paths || [],
    },
    repo_summary: summaryValue?.ok ? summaryValue : { ok: false, error: summaryValue?.error || 'not indexed yet' },
    relevant_files: Array.isArray(contextValue?.results) ? contextValue.results : [],
    tree_paths: flatTree,
    recent_sessions: sessions,
    constraints: {
      approval_required_for_writes: true,
      staged_apply_required: true,
      blocked_by_default: ['secrets', 'wallets', 'payments', 'force_push', 'destructive_delete', 'arbitrary_shell'],
    },
    risk_policy: {
      protected_path_patterns: PROTECTED_PATH_PATTERNS.map(pattern => pattern.source),
      secret_path_patterns: SECRET_PATH_PATTERNS.map(pattern => pattern.source),
      max_staged_lines_per_action: 300,
      verify_allowlist: 'build/test/lint/typecheck/py_compile/vitest/tsc/eslint/pytest only',
    },
    verification_commands: project.verification_commands || defaultVerificationCommands(project),
    generated_at: nowIso(),
  }
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

module.exports = function createForgeRouter(requireAuth, opts = {}) {
  const rlRuns = opts.rlRuns || ((_req, _res, next) => next())
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

  router.post('/runs', requireAuth, rlRuns, async (req, res) => {
    try {
      const project = findProject(req.body?.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      const goal = String(req.body?.goal || '').trim()
      if (!goal) return res.status(400).json({ ok: false, error: 'goal required' })

      const runId = `run-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
      const contextPack = await buildContextPack(project, goal, req.body || {})
      const targetFiles = contextPack.relevant_files.map(item => item.path).filter(Boolean).slice(0, 8)
      const plan = createPlan(engine, project, {
        goal,
        provider: req.body?.provider,
        target_files: targetFiles,
        target_type: project.target_type,
      })
      const preflightActions = actionsForPlan(plan, project, {})

      let aiText = ''
      try {
        const treeSnippet = contextPack.tree_paths.slice(0, 50).join('\n')
        const historySnippet = contextPack.recent_sessions
          .flatMap(session => session.recent || [])
          .slice(-6)
          .map(item => `${item.role}: ${String(item.content || '').slice(0, 300)}`)
          .join('\n')
        const codeContext = contextPack.relevant_files
          .map(item => `--- ${item.path}${item.symbol ? ` :: ${item.symbol}` : ''} ---\n${String(item.snippet || '').slice(0, 900)}`)
          .join('\n\n')
        const prompt = `${buildForgeSystemPrompt(project, treeSnippet, historySnippet)}\n${codeContext ? `\nRelevant existing code:\n${codeContext}\n` : ''}\nUser: ${goal}`
        const aiResult = await callPythonChat(prompt, 60000)
        aiText = aiResult?.response || aiResult?.reply || ''
      } catch { /* degraded plan-only run */ }

      const codeActions = aiText ? extractCodeActions(aiText, project).slice(0, 12) : []
      for (const action of codeActions) {
        const policy = validateRunActionPolicy(action, project)
        action.run_id = runId
        action.plan_id = plan.id
        action.approval_required = true
        action.status = policy.allowed ? 'pending_approval' : 'blocked'
        action.risk = policy.risk_level === 'high' ? 'dangerous' : policy.risk_level
        action.risk_level = policy.risk_level
        action.expected_result = 'File is staged in the run workspace, verified, then applied after owner approval.'
        action.rollback_plan = 'Restore from per-file .forge_snapshots copy if apply must be reverted.'
        action.policy_decision = policy
        action.created_at = nowIso()
        action.updated_at = nowIso()
      }
      if (codeActions.length) {
        saveActions([...codeActions, ...loadActions()])
        for (const action of codeActions) appendAudit('forge_run_action_proposed', { id: action.id, type: action.type, risk: action.risk_level, project_id: project.id, allowed: action.policy_decision?.allowed })
      }

      const actions = [...preflightActions, ...codeActions].map(action => ({ ...action, run_id: runId }))
      const patches = actions
        .filter(action => RUN_WRITE_ACTIONS.has(action.type))
        .map(action => ({
          action_id: action.id,
          files: actionFiles(action),
          diff: action.diff || null,
          policy: action.policy_decision || validateRunActionPolicy(action, project),
          status: action.status || 'pending_approval',
        }))
      const run = {
        id: runId,
        run_id: runId,
        project_id: project.id,
        goal,
        status: patches.some(patch => patch.policy?.allowed === false) ? 'blocked' : 'awaiting_approval',
        mode: req.body?.mode || 'supervised',
        provider: req.body?.provider || 'local-first',
        max_iterations: Math.min(5, Math.max(1, Number(req.body?.max_iterations) || 3)),
        context_pack: contextPack,
        plan,
        actions,
        patches,
        approvals: [],
        test_results: [],
        review: {
          status: patches.length ? 'policy_checked' : 'plan_only',
          summary: patches.length ? `${patches.length} patch action(s) generated and policy checked.` : 'No write patch generated; run is ready for planning review.',
          blocked: patches.filter(patch => patch.policy?.allowed === false).length,
        },
        final_report: null,
        audit_ids: [],
        workspace_path: runWorkspaceRoot(runId),
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      upsertRun(run)
      appendAudit('forge_run_created', { run_id: runId, project_id: project.id, goal: goal.slice(0, 160), actions: actions.length, patches: patches.length })
      res.json({ ok: true, state: 'live', run_id: runId, status: run.status, context_pack: contextPack, plan, actions, patches, run })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  // SSE streaming variant of POST /runs — emits progress events then the run object.
  router.post('/runs/stream', requireAuth, rlRuns, async (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Cache-Control', 'no-cache')
    res.setHeader('Connection', 'keep-alive')
    res.setHeader('X-Accel-Buffering', 'no')
    res.flushHeaders()
    const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    try {
      const project = findProject(req.body?.project_id)
      if (!project) { send('error', { error: 'project not found' }); return res.end() }
      const goal = String(req.body?.goal || '').trim()
      if (!goal) { send('error', { error: 'goal required' }); return res.end() }

      send('progress', { stage: 'context', message: 'Building context pack…' })
      const runId = `run-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
      const contextPack = await buildContextPack(project, goal, req.body || {})
      send('progress', { stage: 'plan', message: 'Creating plan…' })
      const targetFiles = contextPack.relevant_files.map(item => item.path).filter(Boolean).slice(0, 8)
      const plan = createPlan(engine, project, { goal, provider: req.body?.provider, target_files: targetFiles, target_type: project.target_type })
      const preflightActions = actionsForPlan(plan, project, {})
      send('progress', { stage: 'llm', message: 'Calling AI model…' })

      let aiText = ''
      try {
        const treeSnippet = contextPack.tree_paths.slice(0, 50).join('\n')
        const historySnippet = contextPack.recent_sessions.flatMap(s => s.recent || []).slice(-6).map(m => `${m.role}: ${String(m.content || '').slice(0, 300)}`).join('\n')
        const codeContext = contextPack.relevant_files.map(item => `--- ${item.path}${item.symbol ? ` :: ${item.symbol}` : ''} ---\n${String(item.snippet || '').slice(0, 900)}`).join('\n\n')
        const prompt = `${buildForgeSystemPrompt(project, treeSnippet, historySnippet)}\n${codeContext ? `\nRelevant existing code:\n${codeContext}\n` : ''}\nUser: ${goal}`
        const aiResult = await callPythonChat(prompt, 60000)
        aiText = aiResult?.response || aiResult?.reply || ''
        if (aiText) send('progress', { stage: 'extract', message: `AI responded — extracting code actions…` })
      } catch { /* degraded plan-only */ }

      const codeActions = aiText ? extractCodeActions(aiText, project).slice(0, 12) : []
      for (const action of codeActions) {
        const policy = validateRunActionPolicy(action, project)
        action.run_id = runId; action.plan_id = plan.id; action.approval_required = true
        action.status = policy.allowed ? 'pending_approval' : 'blocked'
        action.risk = policy.risk_level === 'high' ? 'dangerous' : policy.risk_level
        action.risk_level = policy.risk_level
        action.expected_result = 'File is staged in the run workspace, verified, then applied after owner approval.'
        action.rollback_plan = 'Restore from per-file .forge_snapshots copy if apply must be reverted.'
        action.policy_decision = policy; action.created_at = nowIso(); action.updated_at = nowIso()
      }
      if (codeActions.length) {
        saveActions([...codeActions, ...loadActions()])
        for (const action of codeActions) appendAudit('forge_run_action_proposed', { id: action.id, type: action.type, risk: action.risk_level, project_id: project.id, allowed: action.policy_decision?.allowed })
      }
      const actions = [...preflightActions, ...codeActions].map(action => ({ ...action, run_id: runId }))
      const patches = actions.filter(action => RUN_WRITE_ACTIONS.has(action.type)).map(action => ({
        action_id: action.id, files: actionFiles(action), diff: action.diff || null,
        policy: action.policy_decision || validateRunActionPolicy(action, project),
        status: action.status || 'pending_approval',
      }))
      const run = {
        id: runId, run_id: runId, project_id: project.id, goal, status: patches.some(p => p.policy?.allowed === false) ? 'blocked' : 'awaiting_approval',
        mode: req.body?.mode || 'supervised', provider: req.body?.provider || 'local-first',
        max_iterations: Math.min(5, Math.max(1, Number(req.body?.max_iterations) || 3)),
        context_pack: contextPack, plan, actions, patches, approvals: [], test_results: [],
        review: { status: patches.length ? 'policy_checked' : 'plan_only', summary: patches.length ? `${patches.length} patch action(s) generated and policy checked.` : 'No write patch generated.', blocked: patches.filter(p => p.policy?.allowed === false).length },
        final_report: null, audit_ids: [], workspace_path: runWorkspaceRoot(runId), created_at: nowIso(), updated_at: nowIso(),
      }
      upsertRun(run)
      appendAudit('forge_run_created', { run_id: runId, project_id: project.id, goal: goal.slice(0, 160), actions: actions.length, patches: patches.length })
      send('run', { ok: true, state: 'live', run_id: runId, status: run.status, context_pack: contextPack, plan, actions, patches, run })
      send('done', { run_id: runId })
    } catch (err) {
      send('error', { error: err.message })
    }
    res.end()
  })

  router.get('/runs', requireAuth, (req, res) => {
    const projectId = String(req.query.project_id || '').trim()
    const status = String(req.query.status || '').trim()
    const limit = Math.max(1, Math.min(200, Number(req.query.limit) || 50))
    const runs = loadRuns()
      .filter(run => !projectId || run.project_id === projectId)
      .filter(run => !status || run.status === status)
      .slice(0, limit)
      .map(run => ({
        id: run.id,
        run_id: run.run_id || run.id,
        project_id: run.project_id,
        goal: run.goal,
        status: run.status,
        mode: run.mode,
        provider: run.provider,
        action_count: Array.isArray(run.actions) ? run.actions.length : 0,
        patch_count: Array.isArray(run.patches) ? run.patches.length : 0,
        verification_count: Array.isArray(run.test_results) ? run.test_results.length : 0,
        latest_verification_passed: latestVerificationPassed(run),
        workspace_mode: run.final_report?.workspace_meta?.workspace_mode
          || (Array.isArray(run.test_results) ? run.test_results.slice(-1)[0]?.workspace_meta?.workspace_mode : null)
          || (Array.isArray(run.patches) ? run.patches.find(patch => patch.workspace_meta)?.workspace_meta?.workspace_mode : null)
          || null,
        review_status: run.review?.status || null,
        created_at: run.created_at,
        updated_at: run.updated_at,
      }))
    res.json({ ok: true, state: 'live', runs, total: runs.length, persistence: forgeRunStore.status() })
  })

  router.get('/runs/:id', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    res.json({ ok: true, state: 'live', run })
  })

  router.post('/runs/:id/approve', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_run_approve')) return
    try {
      const run = findRun(req.params.id)
      if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
      const project = findProject(run.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      if (!project.write_access) return res.status(403).json({ ok: false, error: 'project is not writable' })

      const actionId = String(req.body?.action_id || '').trim()
      const actions = run.actions || []
      const targets = actionId ? actions.filter(action => action.id === actionId) : actions.filter(action => RUN_WRITE_ACTIONS.has(action.type))
      if (!targets.length) return res.status(404).json({ ok: false, error: actionId ? 'action not found' : 'no write actions to approve' })

      const staged = []
      const failures = []
      const nextActions = actions.map(action => {
        if (!targets.some(target => target.id === action.id)) return action
        const result = stageRunAction(run, project, action)
        if (result.ok) staged.push({ action_id: action.id, files: result.staged_files, policy: result.policy, workspace_meta: result.workspace_meta })
        else failures.push({ action_id: action.id, policy: result.policy })
        return {
          ...action,
          status: result.ok ? 'staged' : 'blocked',
          approved_at: result.ok ? nowIso() : action.approved_at,
          approved_by: result.ok ? (req.user?.email || req.body?.approved_by || 'operator') : action.approved_by,
          policy_decision: result.policy,
          staged_files: result.staged_files || [],
          workspace_meta: result.workspace_meta || action.workspace_meta || null,
          updated_at: nowIso(),
        }
      })
      const approvals = [
        ...(run.approvals || []),
        ...staged.map(item => ({
          action_id: item.action_id,
          approved_by: req.user?.email || req.body?.approved_by || 'operator',
          approved_at: nowIso(),
          policy: item.policy,
          workspace_meta: item.workspace_meta || null,
        })),
      ]
      const patches = (run.patches || []).map(patch => {
        const stagedPatch = staged.find(item => item.action_id === patch.action_id)
        const failedPatch = failures.find(item => item.action_id === patch.action_id)
        if (stagedPatch) return { ...patch, status: 'staged', policy: stagedPatch.policy, staged_files: stagedPatch.files, workspace_meta: stagedPatch.workspace_meta || null }
        if (failedPatch) return { ...patch, status: 'blocked', policy: failedPatch.policy }
        return patch
      })
      const status = failures.length ? 'blocked' : 'staged'
      const updated = updateRun(run.id, {
        status,
        actions: nextActions,
        patches,
        approvals,
        review: {
          ...(run.review || {}),
          status: failures.length ? 'policy_blocked' : 'staged',
          summary: failures.length
            ? `${failures.length} action(s) blocked by policy.`
            : `${staged.length} action(s) approved and staged in the run workspace.`,
        },
      })
      appendAudit('forge_run_approved', { run_id: run.id, staged: staged.length, failures: failures.length })
      res.status(failures.length ? 409 : 200).json({ ok: failures.length === 0, state: failures.length ? 'degraded' : 'live', run: updated, staged, failures })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  router.post('/runs/:id/verify', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_run_verify')) return
    try {
      const run = findRun(req.params.id)
      if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
      const project = findProject(run.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      const workspace = runWorkspaceRoot(run.id)
      if (!fs.existsSync(workspace)) return res.status(409).json({ ok: false, error: 'run workspace missing; approve/stage a patch first' })
      const cmds = (Array.isArray(req.body?.commands) && req.body.commands.length)
        ? req.body.commands
        : (run.context_pack?.verification_commands || project.verification_commands || defaultVerificationCommands(project))
      const verify = await runVerifyCommands(project, cmds, workspace)
      const workspaceMeta = readWorkspaceMetadata(workspace)
      const testResult = {
        id: `verify-${Date.now().toString(36)}-${crypto.randomBytes(2).toString('hex')}`,
        all_passed: verify.all_passed,
        results: verify.results,
        workspace,
        workspace_meta: workspaceMeta,
        commands: cmds,
        verified_at: nowIso(),
        verified_by: req.user?.email || req.body?.approved_by || 'operator',
      }
      const nextActions = (run.actions || []).map(action => {
        if (!RUN_WRITE_ACTIONS.has(action.type) || !['staged', 'verified'].includes(action.status)) return action
        return { ...action, status: verify.all_passed ? 'verified' : 'verify_failed', updated_at: nowIso() }
      })
      const nextPatches = (run.patches || []).map(patch => {
        if (!['staged', 'verified'].includes(patch.status)) return patch
        return { ...patch, status: verify.all_passed ? 'verified' : 'verify_failed' }
      })
      const updated = updateRun(run.id, {
        status: verify.all_passed ? 'verified' : 'verify_failed',
        actions: nextActions,
        patches: nextPatches,
        test_results: [...(run.test_results || []), testResult],
        review: {
          ...(run.review || {}),
          status: verify.all_passed ? 'verification_passed' : 'verification_failed',
          summary: verify.all_passed
            ? 'All staged verification commands passed.'
            : 'One or more staged verification commands failed.',
        },
      })
      appendAudit('forge_run_verified', { run_id: run.id, all_passed: verify.all_passed, commands: cmds.length })
      res.status(verify.all_passed ? 200 : 409).json({ ok: verify.all_passed, state: verify.all_passed ? 'live' : 'degraded', run: updated, test_result: testResult })
    } catch (err) {
      res.status(err.status || 500).json({ ok: false, state: 'degraded', error: err.message })
    }
  })

  router.post('/runs/:id/apply', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_run_apply')) return
    try {
      const run = findRun(req.params.id)
      if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
      const project = findProject(run.project_id)
      if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
      if (!project.write_access) return res.status(403).json({ ok: false, error: 'project is not writable' })
      const latestTest = (run.test_results || []).slice(-1)[0]
      if (!latestTest?.all_passed && req.body?.force !== true) {
        return res.status(409).json({ ok: false, error: 'verification must pass before apply' })
      }
      const blocked = (run.patches || []).filter(patch => patch.policy?.allowed === false || patch.status === 'blocked')
      if (blocked.length) return res.status(409).json({ ok: false, error: 'blocked patches cannot be applied', blocked })

      const result = applyStagedRun(run, project)
      if (!result.ok) return res.status(409).json({ ok: false, state: 'degraded', ...result })
      const finalReport = {
        status: 'applied',
        summary: `Applied ${result.applied.length} file(s) from staged run ${run.id}.`,
        applied_files: result.applied,
        snapshots: result.snapshots,
        workspace_meta: result.workspace_meta || latestTest?.workspace_meta || null,
        test_result: latestTest || null,
        applied_at: nowIso(),
        applied_by: req.user?.email || req.body?.approved_by || 'operator',
        next_steps: ['Review the diff in git status.', 'Run the broader project verification suite before release.'],
      }
      const nextActions = (run.actions || []).map(action => RUN_WRITE_ACTIONS.has(action.type) && ['verified', 'staged', 'approved'].includes(action.status)
        ? { ...action, status: 'applied', result: finalReport, updated_at: nowIso() }
        : action)
      const nextPatches = (run.patches || []).map(patch => ['verified', 'staged', 'approved'].includes(patch.status)
        ? { ...patch, status: 'applied' }
        : patch)
      const updated = updateRun(run.id, {
        status: 'applied',
        actions: nextActions,
        patches: nextPatches,
        final_report: finalReport,
        review: {
          ...(run.review || {}),
          status: 'applied',
          summary: finalReport.summary,
        },
      })
      appendAudit('forge_run_applied', { run_id: run.id, project_id: project.id, files: result.applied.length, snapshots: result.snapshots.length })
      res.json({ ok: true, state: 'live', run: updated, final_report: finalReport })
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

    const codeContext = await retrieveForgeContext(project, content)
    const systemPrompt = buildForgeSystemPrompt(project, treeSnippet, historySnippet) + codeContext

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

    const codeContext = project ? await retrieveForgeContext(project, content) : ''
    const systemPrompt = buildForgeSystemPrompt(project, treeSnippet, historySnippet) + codeContext

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

  // ── Self-update verify loop (WS4): run allowlisted verification, auto-rollback ──
  // Only build/test/compile commands are permitted — never an arbitrary shell.
  const VERIFY_ALLOW = [
    /^npm(\s+--prefix\s+[\w./-]+)?\s+(run\s+(build|verify|lint|typecheck)|test)\b/,
    /^node\s+-c\s+[\w./-]+$/,
    /^node\s+--check\s+[\w./-]+$/,
    /^python3?\s+-m\s+py_compile\b/,
    /^npx\s+(vitest|tsc|eslint)\b/,
    /^pytest\b/,
  ]
  const isVerifyAllowed = (cmd) => VERIFY_ALLOW.some(re => re.test(String(cmd).trim()))

  function splitVerifyCommand(cmd) {
    const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean)
    if (!parts.length || !isVerifyAllowed(parts.join(' '))) {
      const err = new Error('command not in verify allowlist')
      err.status = 403
      throw err
    }
    return parts
  }

  async function runSandboxedVerifyCommand(project, cmd, root) {
    const started = Date.now()
    const executor = await getSandboxExecutor()
    const command = splitVerifyCommand(cmd)
    const result = await executor.run({
      agent_id: `forge-verify-${project.id}`,
      command,
      workdir: root,
      workspace_path: root,
      profile: 'code',
      sandbox: 'process',
      tenant_id: project.tenant_id || 'default',
      trace_id: `forge-verify-${Date.now().toString(36)}`,
      env: {
        CI: '1',
        NODE_ENV: process.env.NODE_ENV || 'test',
      },
    })
    const output = `${result.stdout || ''}${result.stderr || ''}`.slice(-2000)
    return {
      command: cmd,
      pass: result.success === true,
      code: result.exit_code,
      output,
      duration_ms: result.duration_ms ?? (Date.now() - started),
      sandbox_type: result.container_id ? 'docker' : 'process',
      sandbox_profile: result.audit?.profile || 'code',
      sandbox_audit: result.audit || null,
    }
  }

  router.post('/verify', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_verify')) return
    const project = findProject(req.body?.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const cmds = (Array.isArray(req.body?.commands) && req.body.commands.length)
      ? req.body.commands
      : (project.verification_commands || defaultVerificationCommands(project))
    const root = safeProjectRoot(project)
    const verify = await runVerifyCommands(project, cmds, root)
    const results = verify.results
    const allPassed = results.every(r => r.pass)
    appendAudit('forge_verify', { project_id: project.id, all_passed: allPassed, commands: cmds.length })
    // Optional auto-rollback on failure when a pre-edit snapshot is supplied
    let rolledBack = null
    if (!allPassed && req.body?.rollback_snapshot_id) {
      rolledBack = await runForgePython({ operation: 'rollback', snapshot_id: String(req.body.rollback_snapshot_id) })
      appendAudit('forge_verify_autorollback', { project_id: project.id, snapshot_id: req.body.rollback_snapshot_id })
    }
    res.json({ ok: true, all_passed: allPassed, results, rolled_back: rolledBack })
  })

  // Shared verification runner (used by the agentic loop).
  async function runVerifyCommands(project, cmds, rootOverride = null) {
    const root = rootOverride || safeProjectRoot(project)
    const results = []
    for (const cmd of cmds) {
      if (!isVerifyAllowed(cmd)) { results.push({ command: cmd, pass: false, skipped: true, output: 'not in verify allowlist' }); continue }
      // eslint-disable-next-line no-await-in-loop
      results.push(await runSandboxedVerifyCommand(project, cmd, root))
    }
    return { all_passed: results.length > 0 && results.every(r => r.pass), results }
  }

  // ── WS4 Phase 3: autonomous agentic loop ──────────────────────────────────────
  // One goal → plan → generate → apply → verify → feed errors back → fix → re-verify,
  // bounded and owner-gated. Captures original file contents and auto-rolls-back the
  // whole run if it can't reach green. Reuses the indexer context + verify allowlist.
  router.post('/agentic-run', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_agentic_run')) return
    const project = findProject(req.body?.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    if (!project.write_access) return res.status(403).json({ ok: false, error: 'project is not writable' })
    const goal = String(req.body?.goal || '').trim()
    if (!goal) return res.status(400).json({ ok: false, error: 'goal required' })
    const maxIters = Math.min(5, Math.max(1, Number(req.body?.max_iterations) || 3))
    const verifyCmds = (Array.isArray(req.body?.commands) && req.body.commands.length)
      ? req.body.commands : (project.verification_commands || defaultVerificationCommands(project))
    const autoRollback = req.body?.auto_rollback !== false

    const runId = `run-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
    const contextPack = await buildContextPack(project, goal, req.body || {})
    const plan = createPlan(engine, project, {
      goal,
      provider: req.body?.provider,
      target_files: contextPack.relevant_files.map(item => item.path).filter(Boolean).slice(0, 8),
      target_type: project.target_type,
    })
    const run = upsertRun({
      id: runId,
      run_id: runId,
      project_id: project.id,
      goal,
      status: 'running',
      mode: 'agentic_supervised',
      provider: req.body?.provider || 'local-first',
      max_iterations: maxIters,
      context_pack: contextPack,
      plan,
      actions: [],
      patches: [],
      approvals: [],
      test_results: [],
      review: { status: 'running', summary: 'Agentic staged run started.' },
      final_report: null,
      audit_ids: [],
      workspace_path: runWorkspaceRoot(runId),
      created_at: nowIso(),
      updated_at: nowIso(),
    })
    ensureRunWorkspace(run, project)
    const root = runWorkspaceRoot(runId)
    const transcript = []
    let success = false
    let lastErrors = ''
    const allActions = []
    const allPatches = []
    appendAudit('forge_agentic_start', { run_id: runId, project_id: project.id, goal: goal.slice(0, 120), max_iters: maxIters })

    for (let iter = 1; iter <= maxIters; iter++) {
      const codeContext = await retrieveForgeContext(project, goal)
      const flatTree = []
      const flatten = (nodes) => { for (const n of nodes) { flatTree.push(n.path); if (n.children) flatten(n.children) } }
      flatten(buildTree(root))
      const sys = buildForgeSystemPrompt(project, flatTree.slice(0, 50).join('\n'), '') + codeContext
      const fixNote = lastErrors
        ? `\n\nThe previous attempt FAILED verification with:\n${lastErrors.slice(0, 1500)}\nFix the cause. Re-output the COMPLETE corrected file(s).`
        : ''
      const prompt = `${sys}\n\nGoal: ${goal}${fixNote}\n\nOutput the full file(s) needed, each in a code block labelled with its path.`

      let aiText = ''
      try { const r = await callPythonChat(prompt, 90000); aiText = r?.response || r?.reply || '' } catch { /* */ }
      const actions = aiText ? extractCodeActions(aiText, project).slice(0, 8) : []

      const written = []
      for (const a of actions) {
        a.id = a.id || crypto.randomUUID()
        a.run_id = runId
        a.plan_id = plan.id
        a.status = 'generated'
        a.approval_required = true
        const policy = validateRunActionPolicy(a, project)
        a.policy_decision = policy
        a.risk_level = policy.risk_level
        a.risk = policy.risk_level === 'high' ? 'dangerous' : policy.risk_level
        let staged = { ok: false, error: 'policy blocked' }
        if (policy.allowed) staged = stageRunAction(run, project, a)
        a.status = staged.ok ? 'staged' : 'blocked'
        a.staged_files = staged.staged_files || []
        allActions.push(a)
        allPatches.push({
          action_id: a.id,
          files: actionFiles(a),
          diff: a.diff || null,
          policy: staged.policy || policy,
          status: staged.ok ? 'staged' : 'blocked',
          iteration: iter,
        })
        written.push({ path: a.file_path, ok: staged.ok, error: staged.error || staged.policy?.violations?.[0]?.message || null })
      }

      // eslint-disable-next-line no-await-in-loop
      const verify = written.some(w => w.ok) ? await runVerifyCommands(project, verifyCmds, root) : { all_passed: false, results: [{ output: 'no staged files written' }] }
      lastErrors = verify.all_passed ? '' : verify.results.filter(r => !r.pass).map(r => `${r.command || 'apply'}: ${r.output || r.error}`).join('\n')
      transcript.push({ iteration: iter, files_written: written, verify })
      updateRun(runId, {
        status: verify.all_passed ? 'verified' : 'running',
        actions: allActions,
        patches: allPatches,
        test_results: [
          ...(findRun(runId)?.test_results || []),
          { id: `verify-${iter}`, iteration: iter, all_passed: verify.all_passed, results: verify.results, verified_at: nowIso(), workspace: root },
        ],
        review: {
          status: verify.all_passed ? 'verification_passed' : 'iteration_failed',
          summary: verify.all_passed ? `Verification passed on iteration ${iter}. Apply still requires owner approval.` : `Iteration ${iter} failed verification in staged workspace.`,
        },
      })
      appendAudit('forge_agentic_iter', { run_id: runId, project_id: project.id, iter, files: written.length, passed: verify.all_passed })

      if (verify.all_passed) { success = true; break }
    }

    let workspaceCleaned = false
    if (!success && autoRollback && fs.existsSync(path.dirname(root))) {
      removeRunWorkspace(runId)
      workspaceCleaned = true
      appendAudit('forge_agentic_workspace_removed', { run_id: runId })
    }
    const finalRun = updateRun(runId, {
      status: success ? 'verified' : 'verify_failed',
      final_report: {
        status: success ? 'verified_not_applied' : 'failed_not_applied',
        summary: success
          ? `Goal reached green in ${transcript.length} staged iteration(s). Apply requires owner approval.`
          : `Did not reach green in ${transcript.length} staged iteration(s); no project files were modified.`,
        transcript,
        workspace_removed: workspaceCleaned,
        generated_at: nowIso(),
      },
    })
    appendAudit('forge_agentic_done', { run_id: runId, project_id: project.id, success, iterations: transcript.length, workspace_removed: workspaceCleaned })
    res.json({ ok: true, success, run_id: runId, run: finalRun, iterations: transcript.length, transcript, rolled_back: workspaceCleaned,
      summary: finalRun.final_report.summary })
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

  // ── Code understanding (WS4): index a project + retrieve architecture/context ──
  router.post('/index', requireAuth, async (req, res) => {
    const project = findProject(req.body?.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const r = await callCodeIndex('index', { root: safeProjectRoot(project), project_id: project.id, max_files: Number(req.body?.max_files) || 400 }, 180000)
    if (!r?.ok) return res.status(502).json({ ok: false, error: r?.error || 'indexing failed (is the Python backend up?)' })
    appendAudit('forge_project_indexed', { project_id: project.id, files: r.files, chunks: r.chunks })
    res.json(r)
  })

  router.post('/context', requireAuth, async (req, res) => {
    const project = findProject(req.body?.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const query = String(req.body?.query || '').trim()
    if (!query) return res.status(400).json({ ok: false, error: 'query required' })
    const r = await callCodeIndex('context', { project_id: project.id, query, k: Number(req.body?.k) || 6 }, 20000)
    res.json(r?.ok ? r : { ok: false, error: r?.error || 'context unavailable', results: [] })
  })

  router.get('/summary/:projectId', requireAuth, (req, res) => {
    const project = findProject(req.params.projectId)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const http = require('http')
    const token = _codeIndexToken()
    const r = http.get(`http://127.0.0.1:${PYTHON_BACKEND_PORT_FORGE}/api/code-index/summary/${project.id}`, { timeout: 8000, headers: token ? { Authorization: `Bearer ${token}` } : {} }, resp => {
      let t = ''; resp.on('data', c => { t += c }); resp.on('end', () => { try { res.json(JSON.parse(t || '{}')) } catch { res.json({ ok: false, error: 'parse_error' }) } })
    })
    r.on('error', () => res.json({ ok: false, error: 'python backend offline' }))
    r.on('timeout', () => { r.destroy(); res.json({ ok: false, error: 'timeout' }) })
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
      runs_total: loadRuns().length,
      persistence: forgeRunStore.status(),
      approval_policy: DEFAULT_APPROVAL_POLICY,
    })
  })

  return router
}
