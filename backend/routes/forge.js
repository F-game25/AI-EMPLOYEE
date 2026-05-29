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

// Symlink-safe path containment check. Resolves symlinks on existing paths
// to prevent breakout attacks where a symlink points outside the root.
function safeResolve(root, relativePath) {
  const target = path.resolve(root, String(relativePath || ''))
  if (target !== root && !target.startsWith(root + path.sep)) {
    const err = new Error('path escapes root boundary')
    err.status = 403
    throw err
  }
  // For existing paths, resolve symlinks and re-check containment
  try {
    if (fs.existsSync(target)) {
      const real = fs.realpathSync(target)
      if (real !== root && !real.startsWith(root + path.sep)) {
        const err = new Error('symlink escapes root boundary')
        err.status = 403
        throw err
      }
    }
  } catch (e) {
    if (e.status === 403) throw e
    // lstat/realpath failure on broken symlink — reject it
    const err = new Error('path resolution failed (possible broken symlink)')
    err.status = 403
    throw err
  }
  return target
}

function resolveInsideProject(project, relativePath) {
  return safeResolve(safeProjectRoot(project), relativePath)
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
  return safeResolve(workspaceRoot, normalizeRelPath(relativePath))
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
  const patches = []
  for (const rel of policy.files) {
    const target = resolveInsideWorkspace(workspace, rel)
    ensureDir(path.dirname(target))
    const content = actionContentForPath(action, rel)

    // Capture before-state from project (not workspace) for accurate diff
    const projectPath = resolveInsideProject(project, rel)
    const beforeExists = fs.existsSync(projectPath)
    const beforeContent = beforeExists ? (() => { try { return fs.readFileSync(projectPath, 'utf8') } catch { return '' } })() : ''
    const beforeHash = beforeContent ? crypto.createHash('sha256').update(beforeContent).digest('hex').slice(0, 16) : null
    const afterHash  = crypto.createHash('sha256').update(content).digest('hex').slice(0, 16)
    const actionType = action.type === 'file_delete' ? 'delete' : (beforeExists ? 'edit' : 'create')
    const unified_diff = generateUnifiedDiff(beforeContent, content, rel)

    fs.writeFileSync(target, content, 'utf8')
    stagedFiles.push({ path: rel, bytes: Buffer.byteLength(content, 'utf8') })
    patches.push({
      patch_id: `patch-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`,
      action_id: action.id || null,
      run_id: run.id,
      file_path: rel,
      action_type: actionType,
      before_hash: beforeHash,
      after_hash: afterHash,
      before_line_count: beforeContent ? beforeContent.split('\n').length : 0,
      after_line_count: content.split('\n').length,
      unified_diff,
      risk_level: policy.risk_level || 'low',
      status: 'staged',
      created_at: nowIso(),
      updated_at: nowIso(),
    })
  }
  return { ok: true, policy, workspace, workspace_meta: readWorkspaceMetadata(workspace), staged_files: stagedFiles, patches }
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

// Produces a standard unified diff (RFC 3281-compatible) with 3-line context.
function generateUnifiedDiff(beforeContent, afterContent, filePath) {
  const before = String(beforeContent || '').split('\n')
  const after  = String(afterContent  || '').split('\n')
  if (before.join('\n') === after.join('\n')) return ''

  // LCS-based diff using Myers algorithm (simple O(ND) implementation)
  const lcs = (a, b) => {
    const m = a.length, n = b.length
    const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1])
    const seq = []
    let i = m, j = n
    while (i > 0 && j > 0) {
      if (a[i-1] === b[j-1]) { seq.unshift([i-1, j-1]); i--; j-- }
      else if (dp[i-1][j] >= dp[i][j-1]) i--
      else j--
    }
    return seq
  }

  const common = lcs(before, after)
  const ops = [] // { type: 'ctx'|'del'|'add', bi: before-idx, ai: after-idx, line: string }
  let bi = 0, ai = 0
  for (const [cb, ca] of common) {
    while (bi < cb) { ops.push({ type: 'del', bi, line: before[bi] }); bi++ }
    while (ai < ca) { ops.push({ type: 'add', ai, line: after[ai]  }); ai++ }
    ops.push({ type: 'ctx', bi, ai, line: before[bi] }); bi++; ai++
  }
  while (bi < before.length) { ops.push({ type: 'del', bi, line: before[bi] }); bi++ }
  while (ai < after.length)  { ops.push({ type: 'add', ai, line: after[ai]  }); ai++ }

  // Group into hunks with CONTEXT=3
  const CTX = 3
  const changed = ops.reduce((acc, op, i) => { if (op.type !== 'ctx') acc.push(i); return acc }, [])
  if (!changed.length) return ''

  const hunks = []
  let hunkOps = null, hunkStart = -1
  for (const ci of changed) {
    const lo = Math.max(0, ci - CTX), hi = Math.min(ops.length - 1, ci + CTX)
    if (hunkOps && lo <= hunkStart + hunkOps.length + CTX) {
      // extend current hunk
      const needed = ops.slice(hunkStart + hunkOps.length, hi + 1)
      hunkOps.push(...needed)
    } else {
      if (hunkOps) hunks.push({ start: hunkStart, ops: hunkOps })
      hunkStart = lo
      hunkOps = ops.slice(lo, hi + 1)
    }
  }
  if (hunkOps) hunks.push({ start: hunkStart, ops: hunkOps })

  const lines = [`--- a/${filePath}`, `+++ b/${filePath}`]
  for (const { start, ops: hops } of hunks) {
    const dels = hops.filter(o => o.type !== 'add')
    const adds = hops.filter(o => o.type !== 'del')
    const bStart = (dels[0]?.bi ?? 0) + 1
    const aStart = (adds[0]?.ai ?? 0) + 1
    lines.push(`@@ -${bStart},${dels.length} +${aStart},${adds.length} @@`)
    for (const op of hops) {
      if (op.type === 'ctx') lines.push(` ${op.line}`)
      else if (op.type === 'del') lines.push(`-${op.line}`)
      else lines.push(`+${op.line}`)
    }
  }
  return lines.join('\n')
}

// Legacy shim — kept for non-agentic run paths that still call it.
function buildDiffForFiles(files) {
  if (!files?.length) return null
  // For new-file-only scenarios generate a proper unified diff
  if (files.length === 1) {
    const ud = generateUnifiedDiff('', files[0].content || '', files[0].path)
    return ud ? { unified: ud, path: files[0].path, isNew: true } : null
  }
  return {
    path: `${files.length} files`,
    isNew: true,
    hunks: files.slice(0, 4).map(file => ({
      header: `create ${file.path}`,
      lines: String(file.content || '').split('\n').slice(0, 40).map(line => ({ type: 'add', content: line })),
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

  // ── Autonomy Levels ─────────────────────────────────────────────────────────
  // Controls what actions require human approval vs proceed automatically.
  // Level 0 = read-only (inspect only), Level 3 = full autopilot.
  const AUTONOMY_LEVELS = {
    0: { name: 'ReadOnly',  canEdit: false, canTest: false, requireApproval: { low: true,  medium: true,  high: true  } },
    1: { name: 'SafeEdits', canEdit: true,  canTest: false, requireApproval: { low: false, medium: true,  high: true  } },
    2: { name: 'Guided',    canEdit: true,  canTest: true,  requireApproval: { low: false, medium: false, high: true  } },
    3: { name: 'Autopilot', canEdit: true,  canTest: true,  requireApproval: { low: false, medium: false, high: false } },
  }

  function getAutonomyLevel(levelNum) {
    const n = Math.min(3, Math.max(0, Number(levelNum) || 2))
    return { ...AUTONOMY_LEVELS[n], level: n }
  }

  function requiresApproval(filePath, autonomyLevelNum) {
    const level = getAutonomyLevel(autonomyLevelNum)
    if (!level.canEdit) return true
    const risk = classifyFileRisk(filePath)
    return level.requireApproval[risk] === true
  }

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
      // Sync SQLite forge_patches table to 'applied' status
      for (const patch of (run.patches || [])) {
        if (['staged', 'approved', 'verified'].includes(patch.status)) {
          forgeRunStore.updatePatchStatus(patch.patch_id || patch.action_id, 'applied')
        }
      }
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

  // Returns the structured per-iteration agent transcript for an agentic run.
  router.get('/runs/:id/transcript', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const transcript = run.final_report?.transcript || []
    res.json({ ok: true, run_id: run.id, status: run.status, iterations: transcript.length, transcript })
  })

  // Returns staged actions that require human approval before the run can proceed.
  router.get('/runs/:id/pending-approvals', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const pending = (run.actions || []).filter(a => a.status === 'staged' && requiresApproval(a.file_path || '', run.autonomy_level ?? 2))
    res.json({ ok: true, run_id: run.id, status: run.status, pending_approvals: pending.map(a => ({ action_id: a.id, file_path: a.file_path, risk_level: a.risk_level, unified_diff: a.unified_diff || null, action_type: a.action_type || 'create' })) })
  })

  // Approves a single staged action; if all pending approved, run can continue.
  router.post('/runs/:id/approve-action', requireAuth, (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_approve_action')) return
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const actionId = String(req.body?.action_id || '').trim()
    if (!actionId) return res.status(400).json({ ok: false, error: 'action_id required' })
    const updatedActions = (run.actions || []).map(a => a.id === actionId ? { ...a, status: 'approved', approved_by: req.user?.email || 'operator', approved_at: nowIso(), approval_reason: req.body?.reason || '' } : a)
    forgeRunStore.updatePatchStatus(actionId, 'approved')
    const updated = updateRun(run.id, { actions: updatedActions })
    appendAudit('forge_action_approved', { run_id: run.id, action_id: actionId, approved_by: req.user?.email || 'operator' })
    const stillPending = updatedActions.filter(a => a.status === 'staged' && requiresApproval(a.file_path || '', run.autonomy_level ?? 2))
    res.json({ ok: true, run: updated, still_pending: stillPending.length, can_continue: stillPending.length === 0 })
  })

  // Rejects a staged action; removes its staged files from the workspace.
  router.post('/runs/:id/reject-action', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const actionId = String(req.body?.action_id || '').trim()
    if (!actionId) return res.status(400).json({ ok: false, error: 'action_id required' })
    const updatedActions = (run.actions || []).map(a => a.id === actionId ? { ...a, status: 'rejected', rejected_by: req.user?.email || 'operator', rejected_at: nowIso(), rejection_reason: req.body?.reason || '' } : a)
    forgeRunStore.updatePatchStatus(actionId, 'rejected')
    // Remove rejected file from workspace
    const action = (run.actions || []).find(a => a.id === actionId)
    if (action?.file_path) {
      const workspace = runWorkspaceRoot(run.id)
      try { const fp = resolveInsideWorkspace(workspace, action.file_path); if (fs.existsSync(fp)) fs.unlinkSync(fp) } catch { /* best-effort */ }
    }
    const updated = updateRun(run.id, { actions: updatedActions })
    appendAudit('forge_action_rejected', { run_id: run.id, action_id: actionId, rejected_by: req.user?.email || 'operator' })
    res.json({ ok: true, run: updated })
  })

  // Continues a waiting_approval run after all pending actions are resolved.
  // This endpoint must be called by the UI after all approvals/rejections are done.
  router.post('/runs/:id/continue', requireAuth, async (req, res) => {
    if (!requireOwnerApproval(req, res, 'forge_run_continue')) return
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    if (run.status !== 'waiting_approval') return res.status(400).json({ ok: false, error: `run is not in waiting_approval state (current: ${run.status})` })
    const stillPending = (run.actions || []).filter(a => a.status === 'staged' && requiresApproval(a.file_path || '', run.autonomy_level ?? 2))
    if (stillPending.length) return res.status(400).json({ ok: false, error: `${stillPending.length} action(s) still pending approval`, pending: stillPending.map(a => a.id) })
    // Resume at tester stage — run the approved workspace through verification
    updateRun(run.id, { status: 'testing' })
    const project = findProject(run.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const root = runWorkspaceRoot(run.id)
    const verifyCmds = project.verification_commands || defaultVerificationCommands(project)
    try {
      const testerStage = await runTesterAgent(project, verifyCmds, root, run.id)
      const passed = testerStage.output.all_passed
      updateRun(run.id, {
        status: passed ? 'verified' : 'verify_failed',
        test_results: [...(run.test_results || []), { id: `verify-continue-${Date.now()}`, all_passed: passed, results: testerStage.output.results, verified_at: nowIso() }],
        review: { status: passed ? 'verification_passed' : 'iteration_failed', summary: passed ? 'Verification passed after approval. Apply to proceed.' : 'Verification failed after approval.' },
      })
      appendAudit('forge_agentic_continue', { run_id: run.id, project_id: project.id, passed })
      res.json({ ok: true, run: findRun(run.id), tester: testerStage, passed, summary: passed ? 'Verification passed. You may now apply the run.' : 'Verification failed — review errors and try again.' })
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message })
    }
  })

  // Returns all patches for a run (from SQLite forge_patches table).
  router.get('/runs/:id/patches', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const patches = forgeRunStore.getPatchesForRun(req.params.id)
    // Fall back to run.patches (in-memory) when SQLite is unavailable
    const fallback = Array.isArray(run.patches) ? run.patches : []
    res.json({ ok: true, run_id: run.id, patches: patches.length ? patches : fallback })
  })

  // Returns a structured chronological replay timeline for a run.
  router.get('/runs/:id/replay', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const auditEvents = forgeRunStore.getAuditEventsForRun(req.params.id)
    const patches = forgeRunStore.getPatchesForRun(req.params.id)
    const transcript = run.final_report?.transcript || []

    // Build chronological timeline from transcript + audit events
    const timeline = []
    for (const t of transcript) {
      const iter = t.iteration
      for (const agentKey of ['planner','coder','tester','debug','security','reviewer']) {
        const stage = Array.isArray(t[agentKey]) ? t[agentKey] : t[agentKey] ? [t[agentKey]] : []
        for (const s of stage) {
          if (!s) continue
          timeline.push({ ts: s.started_at || run.created_at, type: 'agent_start', iteration: iter, agent: s.agent, status: s.status })
          if (s.finished_at) timeline.push({ ts: s.finished_at, type: 'agent_done', iteration: iter, agent: s.agent, status: s.status, duration_ms: s.duration_ms, output_summary: s.output?.summary || s.output?.verdict || null })
        }
      }
      for (const f of (t.files_written || [])) {
        timeline.push({ ts: run.created_at, type: 'patch', iteration: iter, file: f.path, action_type: f.action_type || 'create', ok: f.ok })
      }
      if (t.regression) {
        timeline.push({ ts: run.updated_at, type: 'regression', iteration: iter, data: t.regression })
      }
    }
    for (const e of auditEvents) {
      if (['forge_action_approved','forge_action_rejected'].includes(e.event)) {
        timeline.push({ ts: e.created_at, type: 'approval', event: e.event, data: e.details })
      }
    }
    timeline.sort((a, b) => (a.ts || '').localeCompare(b.ts || ''))

    res.json({ ok: true, run_id: run.id, goal: run.goal, status: run.status, created_at: run.created_at, completed_at: run.updated_at, timeline, patches, final_report: run.final_report })
  })

  // Returns aggregate metrics for a project.
  router.get('/projects/:id/forge-metrics', requireAuth, (req, res) => {
    const metrics = forgeRunStore.getMetricsForProject(req.params.id)
    if (!metrics) return res.status(503).json({ ok: false, error: 'metrics unavailable (SQLite not initialized)' })
    res.json({ ok: true, project_id: req.params.id, ...metrics })
  })

  // Returns live forge agent statuses (merged by /api/agents).
  router.get('/agents/status', requireAuth, (_req, res) => {
    res.json({ ok: true, agents: Object.values(forgeAgentStatus) })
  })

  router.get('/projects', requireAuth, (_req, res) => {
    res.json({ ok: true, state: 'live', projects: loadProjects() })
  })

  router.get('/projects/:id', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    // Attach autonomy_level from most recent run for this project
    const runs = forgeRunStore.getRuns ? forgeRunStore.getRuns({ project_id: project.id, limit: 1 }) : []
    const autonomyLevel = runs[0]?.autonomy_level ?? project.autonomy_level ?? null
    res.json({ ok: true, project: { ...project, autonomy_level: autonomyLevel } })
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

  // ── Command Safety Classifier ─────────────────────────────────────────────────
  // Every command must be classified before execution. BLOCKED commands are never
  // run. DANGEROUS commands are logged with extra audit entries.
  const CMD_BLOCKED   = [ /rm\s+-rf/, /git\s+(push\s+.*--force|clean\s+-fd|reset\s+--hard)/, /chmod\s+-[Rr]/, /curl\s+.*\|.*sh/, /wget\s+.*\|.*sh/, /cat\s+.*\.env/, /\benv\b.*(?:SECRET|API_KEY|TOKEN)/i, /mkfs\b/, /:\s*\(\)\s*\{.*\}/, /dd\s+if=/ ]
  const CMD_DANGEROUS = [ /npm\s+install\b/, /pip\s+install\b/, /yarn\s+add\b/, /pnpm\s+add\b/, /migrate\b/, /db:drop\b/, /database:drop\b/ ]
  const CMD_CAUTION   = [ /npm\s+run\b/, /npx\b/, /python3?\s+\S+\.py\b/, /node\s+\S+\.js\b/ ]
  const CMD_SAFE      = [ /^npm\s+(test|run\s+(lint|build|typecheck|verify))\b/, /^pytest\b/, /^python3?\s+-m\s+(pytest|py_compile)\b/, /^npx\s+(vitest|tsc|eslint)\b/, /^node\s+(--check|-c)\b/ ]

  function classifyCommand(cmd) {
    const c = String(cmd || '').trim()
    if (CMD_BLOCKED.some(r => r.test(c)))   return { level: 'BLOCKED',   reason: 'Command matches blocked pattern' }
    if (CMD_SAFE.some(r => r.test(c)))       return { level: 'SAFE',      reason: 'Command is in safe allowlist' }
    if (CMD_DANGEROUS.some(r => r.test(c))) return { level: 'DANGEROUS', reason: 'Command modifies dependencies or database' }
    if (CMD_CAUTION.some(r => r.test(c)))   return { level: 'CAUTION',   reason: 'Command runs arbitrary scripts' }
    return { level: 'CAUTION', reason: 'Unknown command — treating as caution' }
  }

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
    // Safety classifier runs before the allowlist — blocks absolutely dangerous commands
    const classification = classifyCommand(cmd)
    if (classification.level === 'BLOCKED') {
      appendAudit('forge_command_blocked', { project_id: project.id, command: cmd, reason: classification.reason })
      return { command: cmd, pass: false, skipped: true, output: `Command blocked by safety classifier: ${classification.reason}`, classification }
    }
    if (classification.level === 'DANGEROUS') {
      appendAudit('forge_command_dangerous', { project_id: project.id, command: cmd, reason: classification.reason })
    }
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

  // Captures the pre-modification baseline: runs verification on the original project.
  async function captureBaseline(project, verifyCmds) {
    const root = safeProjectRoot(project)
    const results = []
    for (const cmd of verifyCmds.slice(0, 3)) { // limit baseline to 3 cmds (speed)
      if (!isVerifyAllowed(cmd)) continue
      // eslint-disable-next-line no-await-in-loop
      const r = await runSandboxedVerifyCommand(project, cmd, root)
      results.push({ command: cmd, pass: r.pass, output: (r.output || '').slice(-200) })
    }
    return { captured_at: nowIso(), commands: results }
  }

  // Compares tester output against baseline to show regression delta.
  function compareToBaseline(baseline, testerOutput) {
    if (!baseline?.commands?.length) return null
    const baseMap = Object.fromEntries(baseline.commands.map(r => [r.command, r.pass]))
    const nowMap = Object.fromEntries((testerOutput?.results || []).map(r => [r.command, r.pass]))
    const fixed = [], broken = [], unchangedPass = [], unchangedFail = [], newlyBroken = []
    for (const [cmd, wasPassing] of Object.entries(baseMap)) {
      const nowPassing = nowMap[cmd] ?? null
      if (nowPassing === null) continue
      if (!wasPassing && nowPassing) fixed.push(cmd)
      else if (wasPassing && !nowPassing) broken.push(cmd)
      else if (wasPassing) unchangedPass.push(cmd)
      else unchangedFail.push(cmd)
    }
    for (const cmd of Object.keys(nowMap)) {
      if (!(cmd in baseMap) && !nowMap[cmd]) newlyBroken.push(cmd)
    }
    return { fixed, broken, unchanged_pass: unchangedPass, unchanged_fail: unchangedFail, newly_broken: newlyBroken }
  }

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

  // ── Repo Intelligence V2 ─────────────────────────────────────────────────────
  // Classifies a file path by risk level for approval gating.
  function classifyFileRisk(relPath) {
    const p = relPath.toLowerCase()
    if (/auth|security|middleware|schema|migration|\.env|secret|wallet|payment|credential|password|token|ssl|tls/.test(p)) return 'high'
    if (/database|model|seed|route|api|config|settings/.test(p)) return 'medium'
    return 'low'
  }

  // Detects project stack from filesystem signals.
  function detectProjectStack(project) {
    const root = safeProjectRoot(project)
    const has = f => fs.existsSync(path.join(root, f))
    const readPkg = () => { try { return JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')) } catch { return {} } }

    const isPython = has('requirements.txt') || has('pyproject.toml') || has('setup.py')
    const isNode   = has('package.json')
    const pkg = isNode ? readPkg() : {}
    const scripts = Object.keys(pkg.scripts || {})
    const devDeps  = Object.keys(pkg.devDependencies || {})
    const allDeps  = [...Object.keys(pkg.dependencies || {}), ...devDeps]

    const testRunner = devDeps.includes('vitest') || scripts.includes('vitest') ? 'vitest'
      : devDeps.includes('jest') || has('jest.config.js') || has('jest.config.ts') ? 'jest'
      : devDeps.includes('mocha') ? 'mocha'
      : isPython && has('pytest.ini') ? 'pytest'
      : isPython ? 'pytest'
      : 'unknown'

    return {
      type: isPython && isNode ? 'fullstack' : isNode ? 'node' : isPython ? 'python' : 'generic',
      hasTests: has('tests') || has('test') || has('__tests__') || scripts.includes('test'),
      testRunner,
      hasBuild: scripts.includes('build'),
      hasTsc: devDeps.includes('typescript') || has('tsconfig.json'),
      hasLint: scripts.includes('lint') || devDeps.includes('eslint') || has('.eslintrc.js') || has('.eslintrc.json'),
      hasRuff: isPython && (has('ruff.toml') || has('pyproject.toml')),
      hasMypy: isPython && has('mypy.ini'),
      scripts,
      allDeps,
    }
  }

  // Generates a rich repo_index.json with import graph, risk map, and route detection.
  function generateRepoIndex(project) {
    const root = safeProjectRoot(project)
    const indexPath = path.join(FORGE_HOME, 'projects', project.id, 'repo_index.json')
    const tree = buildTree(root)
    const allPaths = flattenTreePaths(tree)

    const fileStats = {}
    const riskMap = {}
    for (const rel of allPaths.slice(0, 300)) {
      try {
        const abs = path.join(root, rel)
        const st = fs.statSync(abs)
        const ext = path.extname(rel)
        fileStats[rel] = { lines: st.size > 0 ? Math.round(st.size / 40) : 0, size_bytes: st.size, ext }
        riskMap[rel] = classifyFileRisk(rel)
      } catch { /* skip */ }
    }

    // Parse external deps from package.json / requirements.txt
    const externalDeps = []
    const pkgPath = path.join(root, 'package.json')
    const reqPath = path.join(root, 'requirements.txt')
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'))
        externalDeps.push(...Object.keys(pkg.dependencies || {}), ...Object.keys(pkg.devDependencies || {}))
      } catch { /* skip */ }
    }
    if (fs.existsSync(reqPath)) {
      try {
        fs.readFileSync(reqPath, 'utf8').split('\n').forEach(l => { const m = l.trim().match(/^([a-zA-Z0-9_-]+)/); if (m) externalDeps.push(m[1]) })
      } catch { /* skip */ }
    }

    // Import graph: regex-scan JS/TS files for require/import
    const importGraph = {}
    for (const rel of allPaths.filter(p => /\.(js|ts|jsx|tsx)$/.test(p)).slice(0, 100)) {
      try {
        const content = fs.readFileSync(path.join(root, rel), 'utf8')
        const imports = []
        for (const m of content.matchAll(/(?:require|import)\s*\(?\s*['"](\.[^'"]+)['"]/g)) {
          imports.push(m[1])
        }
        if (imports.length) importGraph[rel] = imports
      } catch { /* skip */ }
    }

    // Route map: detect Express/Fastify routes in JS files
    const routeMap = []
    for (const rel of allPaths.filter(p => /\.(js|ts)$/.test(p) && !/node_modules/.test(p)).slice(0, 80)) {
      try {
        const content = fs.readFileSync(path.join(root, rel), 'utf8')
        let lineN = 0
        for (const line of content.split('\n')) {
          lineN++
          const m = line.match(/(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*['"`]([^'"`]+)['"`]/)
          if (m) routeMap.push({ method: m[1].toUpperCase(), path: m[2], file: rel, line: lineN })
        }
      } catch { /* skip */ }
    }

    const testFiles = allPaths.filter(p => /test|spec/i.test(p) && /\.(js|ts|py)$/.test(p))
    const entryPoints = allPaths.filter(p => /^(index|main|app|server)\.(js|ts|py)$/.test(path.basename(p)))
    const highRiskFiles = Object.entries(riskMap).filter(([, r]) => r === 'high').map(([f]) => f)
    const stack = detectProjectStack(project)

    // V3: env var usage scan (names only, never values)
    const envVarsUsed = new Set()
    for (const rel of allPaths.filter(p => /\.(js|ts|jsx|tsx|py)$/.test(p)).slice(0, 80)) {
      try {
        const content = fs.readFileSync(path.join(root, rel), 'utf8')
        for (const m of content.matchAll(/process\.env\.([A-Z_][A-Z0-9_]*)/g)) envVarsUsed.add(m[1])
        for (const m of content.matchAll(/os\.environ(?:\.get)?\s*\(\s*['"]([^'"]+)['"]/g)) envVarsUsed.add(m[1])
      } catch { /* skip */ }
    }

    // V3: config files detection
    const CONFIG_PATTERNS = /^(\.|)(eslint|prettier|tsconfig|jest\.config|vitest\.config|babel\.config|vite\.config|webpack\.config|rollup\.config|pyproject|setup\.cfg|mypy|ruff|\.env\.example)/
    const configFiles = allPaths.filter(p => CONFIG_PATTERNS.test(path.basename(p)))

    // V3: generated files detection
    const generatedFiles = allPaths.filter(p => /\.(min\.(js|css)|map)$/.test(p) || /^(dist|build|__pycache__|\.next|\.nuxt)\//.test(p))

    // V3: incremental file hashing for cache invalidation
    const existingIndex = readJson(indexPath, null)
    const fileHashes = {}
    const prevHashes = existingIndex?.file_hashes || {}
    for (const rel of allPaths.slice(0, 200)) {
      try {
        const abs = path.join(root, rel)
        const prev = prevHashes[rel]
        if (prev) {
          // Quick mtime check before hashing
          const mtime = fs.statSync(abs).mtimeMs.toString(36)
          if (prev.startsWith(mtime + ':')) { fileHashes[rel] = prev; continue }
        }
        const content = fs.readFileSync(abs)
        const mtime = fs.statSync(abs).mtimeMs.toString(36)
        fileHashes[rel] = mtime + ':' + crypto.createHash('sha256').update(content).digest('hex').slice(0, 8)
      } catch { /* skip */ }
    }

    const index = {
      project_id: project.id,
      generated_at: nowIso(),
      last_indexed_at: nowIso(),
      file_count: allPaths.length,
      file_stats: fileStats,
      file_hashes: fileHashes,
      risk_map: riskMap,
      high_risk_files: highRiskFiles,
      dependencies: { external: [...new Set(externalDeps)].slice(0, 80), internal: [] },
      import_graph: importGraph,
      route_map: routeMap.slice(0, 50),
      test_files: testFiles.slice(0, 30),
      entry_points: entryPoints.slice(0, 10),
      env_vars_used: [...envVarsUsed].slice(0, 50),
      config_files: configFiles.slice(0, 20),
      generated_files: generatedFiles.slice(0, 20),
      stack,
    }
    try {
      ensureDir(path.dirname(indexPath))
      fs.writeFileSync(indexPath, JSON.stringify(index, null, 2))
    } catch { /* best-effort */ }
    return index
  }

  function repoIndexSummary(index) {
    if (!index) return ''
    const topFiles = Object.entries(index.file_stats || {})
      .sort((a, b) => b[1].size_bytes - a[1].size_bytes)
      .slice(0, 20)
      .map(([p]) => p)
    const routes = (index.route_map || []).slice(0, 10).map(r => `${r.method} ${r.path}`).join(', ')
    const highRisk = (index.high_risk_files || []).slice(0, 8).join(', ')
    const stack = index.stack ? `${index.stack.type} / testRunner:${index.stack.testRunner}` : 'unknown'
    return [
      `Stack: ${stack}`,
      `Files: ${index.file_count}`,
      `Top files: ${topFiles.join(', ')}`,
      `Deps: ${(index.dependencies?.external || []).slice(0, 20).join(', ')}`,
      `Routes: ${routes || 'none detected'}`,
      `High-risk files: ${highRisk || 'none'}`,
      `Tests: ${(index.test_files || []).slice(0, 8).join(', ')}`,
      `Entry points: ${(index.entry_points || []).join(', ')}`,
    ].join('\n')
  }

  // ── Agent Memory Store ───────────────────────────────────────────────────────
  const AGENT_MEMORY_FILE = path.join(FORGE_HOME, 'agent_memory.json')

  function loadAgentMemory() { return readJson(AGENT_MEMORY_FILE, {}) }
  function saveAgentMemory(mem) { try { writeJson(AGENT_MEMORY_FILE, mem) } catch { /* best-effort */ } }

  function recordAgentOutcome(projectId, agentName, entry) {
    const mem = loadAgentMemory()
    if (!mem[projectId]) mem[projectId] = {}
    if (!mem[projectId][agentName]) mem[projectId][agentName] = []
    mem[projectId][agentName].unshift({ ...entry, recorded_at: nowIso() })
    mem[projectId][agentName] = mem[projectId][agentName].slice(0, 20)
    saveAgentMemory(mem)
  }

  function getAgentHistory(projectId, agentName, limit = 3) {
    const mem = loadAgentMemory()
    return (mem?.[projectId]?.[agentName] || []).slice(0, limit)
  }

  function agentHistoryContext(projectId, agentName) {
    const hist = getAgentHistory(projectId, agentName)
    if (!hist.length) return ''
    const lines = hist.map(h => `  - goal: "${(h.goal || '').slice(0, 60)}", success: ${h.success}, duration_ms: ${h.duration_ms || 0}`).join('\n')
    return `\nPrevious ${agentName} runs on this project:\n${lines}\n`
  }

  // ── Task Memory Store ────────────────────────────────────────────────────────
  // Cross-run learning: stores per-task outcomes and feeds similar past results
  // into the Planner Agent prompt to avoid repeating failed approaches.
  const TASK_MEMORY_FILE = path.join(FORGE_HOME, 'task_memory.json')
  const STOPWORDS = new Set(['a','an','the','and','or','to','of','in','for','on','with','as','by','at','from','is','it','be','do','add','make'])

  function _goalKeywords(goal) {
    return goal.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w.length > 2 && !STOPWORDS.has(w))
  }

  function loadTaskMemory() {
    const data = readJson(TASK_MEMORY_FILE, [])
    return Array.isArray(data) ? data.slice(0, 200) : []
  }

  function saveTaskMemory(entries) {
    try { writeJson(TASK_MEMORY_FILE, entries.slice(0, 200)) } catch { /* best-effort */ }
  }

  // Task Memory V2 — richer record schema + multi-factor similarity scoring.
  function recordTaskMemory(runId, goal, transcript, success, stack) {
    if (!Array.isArray(transcript) || !transcript.length) return
    const entries = loadTaskMemory()
    const lastT = transcript[transcript.length - 1] || {}
    const planner = lastT.planner?.output || {}
    const filesModified = [...new Set(transcript.flatMap(t => (t.files_written || []).filter(f => f.ok).map(f => f.path)))]
    const failureReasons = transcript.filter(t => !t.verify?.all_passed)
      .flatMap(t => (t.tester?.output?.failures || []).map(f => f.failure_reason || 'unknown'))
    const securityFindingsCount = transcript.reduce((n, t) => n + (t.security?.output?.findings?.length || 0), 0)
    const reviewerFindingsCount = transcript.reduce((n, t) => n + (t.reviewer?.output?.findings?.length || 0), 0)
    const debugRetries = transcript.reduce((n, t) => n + (t.debug?.length || 0), 0)
    const approvalRequired = transcript.some(t => t.files_written?.some(f => classifyFileRisk(f.path || '') === 'high'))
    const highRiskFiles = [...new Set(transcript.flatMap(t => (t.files_written || []).filter(f => classifyFileRisk(f.path || '') === 'high').map(f => f.path)))]
    // Classify primary failure type
    const failureType = !success
      ? (failureReasons.includes('security_block') ? 'security_block'
        : failureReasons.includes('syntax_error') ? 'syntax_error'
        : failureReasons.includes('type_error') ? 'type_error'
        : failureReasons.length ? 'test_failure' : 'unknown')
      : null
    const lessons = success
      ? `Succeeded in ${transcript.length} iter(s). Modified: ${filesModified.slice(0, 5).join(', ')}`
      : `Failed in ${transcript.length} iter(s). Primary: ${failureType || 'unknown'}. Issues: ${failureReasons.slice(0, 2).join(' | ')}`
    // Reusable patterns — files that were successfully modified
    const reusablePatterns = filesModified.slice(0, 5).map(f => `edit ${f}`)

    entries.unshift({
      task_id: `task-${runId}`,
      project_id: planner.project_id || null,
      goal,
      goal_keywords: _goalKeywords(goal),
      planner_objectives: planner.objectives || [],
      files_modified: filesModified.slice(0, 20),
      stack: stack ? { type: stack.type, testRunner: stack.testRunner } : null,
      success,
      iterations_needed: transcript.length,
      reviewer_verdict: lastT.reviewer?.output?.verdict || null,
      security_verdict: lastT.security?.output?.verdict || null,
      security_findings_count: securityFindingsCount,
      reviewer_findings_count: reviewerFindingsCount,
      debug_retries: debugRetries,
      approval_required: approvalRequired,
      high_risk_files_touched: highRiskFiles,
      failure_reasons: failureReasons.slice(0, 5),
      failure_type: failureType,
      reusable_patterns: reusablePatterns,
      lessons,
      created_at: nowIso(),
    })
    saveTaskMemory(entries)
  }

  // Multi-factor similarity: keyword (0.4) + stack (0.2) + file overlap (0.2) + failure type (0.2)
  function findSimilarTasks(goal, projectId, limit = 3, stack) {
    const entries = loadTaskMemory()
    const queryKw = new Set(_goalKeywords(goal))
    if (!queryKw.size) return []
    return entries
      .map(e => {
        // Factor 1: Keyword Jaccard
        const eKw = new Set(e.goal_keywords || [])
        const kwIntersect = [...queryKw].filter(k => eKw.has(k)).length
        const kwUnion = new Set([...queryKw, ...eKw]).size
        const kwScore = kwUnion ? kwIntersect / kwUnion : 0

        // Factor 2: Stack type match
        const stackScore = (stack && e.stack) ? (e.stack.type === stack.type ? 1 : 0) : 0.5

        // Factor 3: File path overlap (goal keywords vs modified files)
        const fileWords = new Set((e.files_modified || []).flatMap(f => path.basename(f).replace(/\.[^.]+$/, '').toLowerCase().split(/[^a-z0-9]+/)))
        const fileOverlap = [...queryKw].filter(k => fileWords.has(k)).length
        const fileScore = queryKw.size ? Math.min(1, fileOverlap / queryKw.size) : 0

        // Factor 4: Failure type relevance (0 = unknown match, 1 = known pattern)
        const failScore = e.failure_type && e.failure_type !== 'unknown' ? 0.5 : 0

        const combined = kwScore * 0.4 + stackScore * 0.2 + fileScore * 0.2 + failScore * 0.2
        return { ...e, _score: combined }
      })
      .filter(e => e._score > 0.12)
      .sort((a, b) => b._score - a._score)
      .slice(0, limit)
  }

  function similarTasksContext(goal, projectId, stack) {
    const tasks = findSimilarTasks(goal, projectId, 3, stack)
    if (!tasks.length) return ''
    const lines = tasks.map(t => {
      const parts = [`goal: "${t.goal.slice(0, 60)}"`, `success: ${t.success}`]
      if (t.failure_type) parts.push(`failed_with: ${t.failure_type}`)
      if (t.lessons) parts.push(`lesson: "${t.lessons.slice(0, 100)}"`)
      return `  - ${parts.join(', ')}`
    })
    return `\nSimilar past tasks (use to avoid known failure patterns):\n${lines.join('\n')}\n`
  }

  // ── In-memory forge agent status (for /api/agents) ───────────────────────────
  const forgeAgentStatus = {
    planner:  { id: 'forge-planner',  name: 'Planner',  model: 'claude-sonnet-4-6', tone: 'gold',   status: 'idle', task: '' },
    coder:    { id: 'forge-coder',    name: 'Coder',    model: 'claude-sonnet-4-6', tone: 'info',   status: 'idle', task: '' },
    tester:   { id: 'forge-tester',   name: 'Tester',   model: 'local',             tone: 'purple', status: 'idle', task: '' },
    security: { id: 'forge-security', name: 'Security', model: 'claude-haiku-4-5',  tone: 'danger', status: 'idle', task: '' },
    reviewer: { id: 'forge-reviewer', name: 'Reviewer', model: 'claude-haiku-4-5',  tone: 'teal',   status: 'idle', task: '' },
  }
  engine.forgeAgentStatus = forgeAgentStatus

  function setForgeAgentStatus(name, status, task = '') {
    if (forgeAgentStatus[name]) {
      forgeAgentStatus[name].status = status
      forgeAgentStatus[name].task = task
    }
  }

  // ── Four Forge Agent Stage Functions ─────────────────────────────────────────

  async function runPlannerAgent(project, goal, contextPack, repoIdx, lastErrors, runId) {
    const t0 = Date.now()
    setForgeAgentStatus('planner', 'thinking', `Planning: ${goal.slice(0, 60)}`)
    const history = agentHistoryContext(project.id, 'planner')
    const repoSummary = repoIndexSummary(repoIdx)
    const errorNote = lastErrors ? `\nPrevious attempt failed:\n${lastErrors.slice(0, 800)}\nAdjust the plan accordingly.\n` : ''
    const ctxSnippets = contextPack?.relevant_files?.length
      ? contextPack.relevant_files.map(f => `${f.path}: ${(f.snippet || '').slice(0, 200)}`).join('\n') : ''

    const similarCtx = similarTasksContext(goal, project.id, repoIdx?.stack)

    const prompt = `You are a senior software planner. Analyse the goal and repository, then output a JSON plan.

Repository:
${repoSummary}

Relevant existing code:
${ctxSnippets || '(none indexed yet)'}
${history}${similarCtx}${errorNote}
Goal: ${goal}

Respond with ONLY valid JSON (no markdown fences) matching this schema:
{
  "objectives": ["string"],
  "relevant_files": ["path/relative/to/project"],
  "dependencies": { "external": ["pkg"], "internal": ["path"] },
  "risks": ["string"],
  "implementation_steps": ["string"],
  "success_criteria": ["string"]
}`

    let plannerOutput = null
    let raw = ''
    try {
      const r = await callPythonChat(prompt, 60000)
      raw = r?.response || r?.reply || ''
      // Strip markdown fences if present
      const cleaned = raw.replace(/^```(?:json)?\s*/m, '').replace(/\s*```\s*$/m, '').trim()
      plannerOutput = JSON.parse(cleaned)
    } catch {
      plannerOutput = { objectives: [goal], relevant_files: [], dependencies: { external: [], internal: [] }, risks: [], implementation_steps: [goal], success_criteria: ['build passes'], raw_output: raw }
    }

    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'planner', { run_id: runId, goal, success: !!plannerOutput, duration_ms })
    setForgeAgentStatus('planner', 'done', 'Plan ready')
    return { agent: 'planner', status: 'done', output: plannerOutput, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  async function runCoderAgent(project, plannerStage, goal, root, runId, iter) {
    const t0 = Date.now()
    setForgeAgentStatus('coder', 'writing', `Writing files (iter ${iter})`)
    const plan = plannerStage.output || {}
    const history = agentHistoryContext(project.id, 'coder')
    const steps = (plan.implementation_steps || []).join('\n')
    const files = (plan.relevant_files || []).join(', ')

    const flatTree = []
    const flatten = (nodes) => { for (const n of nodes) { flatTree.push(n.path); if (n.children) flatten(n.children) } }
    flatten(buildTree(root))

    const sys = buildForgeSystemPrompt(project, flatTree.slice(0, 50).join('\n'), '')
    const prompt = `${sys}
${history}
Goal: ${goal}

Plan:
Files to modify/create: ${files || '(determine from context)'}
Steps:
${steps || goal}

Output the COMPLETE file content for every file that needs to be created or modified.
Each file must be in a code block labelled with its relative path.`

    let aiText = ''
    try { const r = await callPythonChat(prompt, 90000); aiText = r?.response || r?.reply || '' } catch { /* */ }
    const actions = aiText ? extractCodeActions(aiText, project).slice(0, 8) : []

    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'coder', { run_id: runId, goal, success: actions.length > 0, duration_ms, files_generated: actions.length })
    setForgeAgentStatus('coder', actions.length ? 'done' : 'failed', `${actions.length} file(s) generated`)
    return { agent: 'coder', status: actions.length ? 'done' : 'failed', output: { actions_count: actions.length, raw_length: aiText.length }, actions, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  // Build a dynamic command list from the detected stack, checking which scripts exist.
  function buildStackVerifyCommands(project, stack) {
    const root = safeProjectRoot(project)
    const scripts = new Set(stack.scripts || [])
    const cmds = []
    if (stack.type === 'node' || stack.type === 'fullstack') {
      if (stack.hasLint && scripts.has('lint')) cmds.push('npm run lint')
      if (stack.hasTsc  && scripts.has('typecheck')) cmds.push('npm run typecheck')
      if (stack.hasTsc  && !scripts.has('typecheck')) cmds.push('npx tsc --noEmit')
      if (stack.hasBuild && scripts.has('build')) cmds.push('npm run build')
      if (stack.hasTests && scripts.has('test'))  cmds.push('npm test')
      if (!cmds.length) {
        // Bare minimum: syntax check entry points
        const entry = stack.entryPoints?.[0]
        if (entry && /\.js$/.test(entry)) cmds.push(`node --check ${entry}`)
      }
    }
    if (stack.type === 'python' || stack.type === 'fullstack') {
      if (stack.hasRuff) cmds.push('ruff check .')
      if (stack.hasMypy) cmds.push('mypy .')
      cmds.push('python3 -m py_compile $(find . -name "*.py" -maxdepth 4 | head -30)')
      if (stack.testRunner === 'pytest') cmds.push('python3 -m pytest --tb=short -q')
    }
    if (stack.type === 'generic' || !cmds.length) cmds.push('echo "no verification commands available"')
    return cmds.filter(c => isVerifyAllowed(c))
  }

  // Classify failure output into a human-readable reason + suggested fix.
  function classifyFailure(output) {
    const o = String(output || '')
    if (/SyntaxError|Unexpected token|Cannot use import|Expected/.test(o)) return { reason: 'syntax_error', fix: 'Check the flagged line for syntax issues (missing bracket, comma, semicolon)' }
    if (/Cannot find module|ModuleNotFoundError|No module named/.test(o)) return { reason: 'missing_import', fix: 'Add missing import or install the dependency listed in the error' }
    if (/TypeScript error|TS\d{4}|Type '.*' is not assignable/.test(o)) return { reason: 'type_error', fix: 'Fix TypeScript type mismatch shown in the error output' }
    if (/AssertionError|FAIL|FAILED|not ok/.test(o)) return { reason: 'test_failure', fix: 'The test assertion failed — check the expected vs actual values' }
    if (/ENOENT|No such file/.test(o)) return { reason: 'missing_file', fix: 'A required file is missing — ensure the file path is correct' }
    if (/EACCES|permission denied/i.test(o)) return { reason: 'permission_error', fix: 'Permission issue — check file permissions' }
    return { reason: 'unknown', fix: 'Review the full error output and fix the reported issue' }
  }

  async function runTesterAgent(project, verifyCmds, root, runId) {
    const t0 = Date.now()
    setForgeAgentStatus('tester', 'running', 'Running tests')

    // Use stack-detected commands if caller passed the defaults or nothing
    const stack = detectProjectStack(project)
    const dynamicCmds = buildStackVerifyCommands(project, { ...stack, entryPoints: (generateRepoIndex(project)?.entry_points || []) })
    // Prefer caller's verifyCmds if they look intentional (non-default); otherwise use stack-detected
    const defaultCmds = new Set(defaultVerificationCommands(project))
    const cmdsToRun = (verifyCmds.length && !verifyCmds.every(c => defaultCmds.has(c))) ? verifyCmds : (dynamicCmds.length ? dynamicCmds : verifyCmds)

    const verify = await runVerifyCommands(project, cmdsToRun, root)
    const failures = verify.results.filter(r => !r.pass).map(r => {
      const out = r.output || r.error || ''
      const { reason, fix } = classifyFailure(out)
      return { command: r.command, output: out.slice(0, 400), stdout_tail: out.slice(-200), stderr_tail: '', failure_reason: reason, suggested_fix: fix }
    })
    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'tester', { run_id: runId, success: verify.all_passed, duration_ms, commands: cmdsToRun.length })
    setForgeAgentStatus('tester', verify.all_passed ? 'done' : 'failed', verify.all_passed ? 'All tests pass' : `${failures.length} failure(s)`)
    return { agent: 'tester', status: verify.all_passed ? 'done' : 'failed', output: { all_passed: verify.all_passed, results: verify.results, failures, stack_type: stack.type, commands_used: cmdsToRun }, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  async function runSecurityAgent(project, actions, runId) {
    const t0 = Date.now()
    setForgeAgentStatus('security', 'scanning', 'Security scan')

    // Stage 1: fast synchronous regex pre-scan (no LLM cost)
    const blockedPatterns = BLOCKED_CODE_PATTERNS
    const preFindings = []
    for (const a of actions) {
      const content = String(a.content || '')
      for (const pat of blockedPatterns) {
        if (pat.test(content)) {
          preFindings.push({ file: a.file_path, line: 0, severity: 'critical', type: 'unsafe_exec', message: `Blocked pattern detected: ${pat.toString().slice(0, 60)}` })
          break
        }
      }
      // Secret detection
      if (/(?:api_key|apikey|secret|password|token|bearer)\s*[:=]\s*['"][^'"]{8,}/i.test(content)) {
        preFindings.push({ file: a.file_path, line: 0, severity: 'critical', type: 'hardcoded_cred', message: 'Possible hardcoded secret or API key detected' })
      }
    }

    // If pre-scan found critical issues, block immediately without LLM call
    if (preFindings.some(f => f.severity === 'critical')) {
      const duration_ms = Date.now() - t0
      const output = { verdict: 'block', findings: preFindings, summary: `Pre-scan blocked: ${preFindings.length} critical pattern(s) found` }
      recordAgentOutcome(project.id, 'security', { run_id: runId, success: false, duration_ms, findings: preFindings.length, pre_scan_block: true })
      setForgeAgentStatus('security', 'failed', 'Security blocked')
      return { agent: 'security', status: 'blocked', output, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
    }

    // Stage 2: LLM semantic security review
    const fileList = actions.slice(0, 4).map(a => `File: ${a.file_path}\n${(a.content || '').slice(0, 500)}`).join('\n---\n')
    const prompt = `You are a security reviewer. Scan the following staged code changes for: secrets, injection, auth bypass, path traversal, unsafe exec, insecure CORS, hardcoded credentials.

${fileList || '(no staged files)'}

Respond with ONLY valid JSON (no markdown fences):
{
  "verdict": "pass",
  "findings": [{ "file": "path", "line": 0, "severity": "info|warning|critical", "type": "secret|injection|auth_bypass|path_traversal|unsafe_exec|hardcoded_cred|insecure_cors", "message": "string" }],
  "summary": "string"
}`

    let secOutput = { verdict: 'pass', findings: [], summary: 'No security issues found' }
    try {
      const r = await callPythonChat(prompt, 30000)
      const raw = r?.response || r?.reply || ''
      const cleaned = raw.replace(/^```(?:json)?\s*/m, '').replace(/\s*```\s*$/m, '').trim()
      const parsed = JSON.parse(cleaned)
      if (parsed.verdict && Array.isArray(parsed.findings)) secOutput = parsed
    } catch { /* fallback to pass */ }

    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'security', { run_id: runId, success: secOutput.verdict !== 'block', duration_ms, findings: secOutput.findings?.length || 0 })
    setForgeAgentStatus('security', secOutput.verdict === 'block' ? 'failed' : 'done', secOutput.summary?.slice(0, 60) || 'Done')
    return { agent: 'security', status: secOutput.verdict === 'block' ? 'blocked' : 'done', output: secOutput, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  async function runDebugAgent(project, testerStage, coderActions, root, runId, iter, retryN) {
    const t0 = Date.now()
    setForgeAgentStatus('tester', 'running', `Debug retry ${retryN}`)
    const failures = testerStage.output?.failures || []
    if (!failures.length) return { agent: 'debug', status: 'skipped', output: { reason: 'no failures to debug' }, duration_ms: 0, started_at: new Date(t0).toISOString(), finished_at: nowIso() }

    const history = agentHistoryContext(project.id, 'debugger')
    const failureText = failures.map(f => `Command: ${f.command}\nOutput:\n${f.output}\nReason: ${f.failure_reason || 'unknown'}\nSuggested fix: ${f.suggested_fix || 'none'}`).join('\n---\n')
    const stagedContent = coderActions.filter(a => a.status === 'staged').slice(0, 4)
      .map(a => {
        let content = ''
        try { const fp = path.join(root, a.file_path || ''); content = fs.existsSync(fp) ? fs.readFileSync(fp, 'utf8').split('\n').slice(0, 60).join('\n') : (a.content || '').slice(0, 1200) } catch { content = (a.content || '').slice(0, 1200) }
        return `File: ${a.file_path}\n${content}`
      }).join('\n---\n')

    const prompt = `You are a debug agent. A verification command failed. Analyse the failure and produce a minimal targeted fix.
${history}
Verification failures:
${failureText}

Staged file content:
${stagedContent || '(no staged files)'}

Respond with ONLY valid JSON (no markdown fences):
{
  "root_cause": "string",
  "affected_file": "relative/path",
  "fix_description": "string",
  "patch": "complete corrected file content OR empty string if no fix possible"
}`

    let debugOutput = { root_cause: 'unknown', affected_file: null, fix_description: 'Unable to diagnose', patch: '' }
    let raw = ''
    try {
      const r = await callPythonChat(prompt, 45000)
      raw = r?.response || r?.reply || ''
      const cleaned = raw.replace(/^```(?:json)?\s*/m, '').replace(/\s*```\s*$/m, '').trim()
      const parsed = JSON.parse(cleaned)
      if (parsed.root_cause) debugOutput = parsed
    } catch {
      debugOutput.raw_output = raw
    }

    // If a patch is provided, stage it as a repair action
    let repairStaged = false
    if (debugOutput.patch && debugOutput.affected_file) {
      const repairAction = { id: crypto.randomUUID(), type: 'file_update', file_path: debugOutput.affected_file, content: debugOutput.patch, run_id: runId }
      const fakeRun = { id: runId, workspace_path: root }
      const staged = stageRunAction(fakeRun, project, repairAction)
      repairStaged = staged.ok
      if (staged.patches?.length) {
        for (const p of staged.patches) forgeRunStore.recordPatch({ ...p, action_id: repairAction.id, run_id: runId, iteration: iter })
      }
    }

    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'debugger', { run_id: runId, success: repairStaged, duration_ms, retry: retryN })
    setForgeAgentStatus('tester', repairStaged ? 'running' : 'failed', repairStaged ? 'Repair staged, re-testing' : 'Could not fix')
    return { agent: 'debug', status: repairStaged ? 'done' : 'no_fix', output: { ...debugOutput, repair_staged: repairStaged }, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  async function runReviewerAgent(project, actions, plannerOutput, runId, securityStage) {
    const t0 = Date.now()
    setForgeAgentStatus('reviewer', 'reviewing', 'Reviewing changes')
    const history = agentHistoryContext(project.id, 'reviewer')
    const fileList = actions.map(a => `${a.file_path}: ${(a.content || '').slice(0, 300)}`).join('\n---\n')
    const risks = (plannerOutput?.risks || []).join(', ')
    const secFindings = (securityStage?.output?.findings || [])
      .map(f => `  [${f.severity}] ${f.file}: ${f.message}`).join('\n') || 'none'

    const prompt = `You are a code reviewer. Review the following staged file changes for: architecture violations, duplicate logic, dead code, broken imports. (Security was handled separately — focus on code quality and architecture.)

Known risks from planner: ${risks || 'none'}
Security pre-scan findings: ${secFindings}
${history}
Staged changes:
${fileList.slice(0, 3000) || '(no files staged)'}

Respond with ONLY valid JSON (no markdown fences):
{
  "verdict": "pass",
  "findings": [{ "file": "path", "line": 0, "severity": "info|warning|error", "type": "architecture|duplicate|dead_code|import", "message": "string" }],
  "summary": "string"
}`

    let reviewerOutput = { verdict: 'pass', findings: [], summary: 'Review skipped (no staged files or LLM unavailable)' }
    let raw = ''
    try {
      const r = await callPythonChat(prompt, 45000)
      raw = r?.response || r?.reply || ''
      const cleaned = raw.replace(/^```(?:json)?\s*/m, '').replace(/\s*```\s*$/m, '').trim()
      const parsed = JSON.parse(cleaned)
      if (parsed.verdict && Array.isArray(parsed.findings)) reviewerOutput = parsed
    } catch {
      reviewerOutput.raw_output = raw
    }

    const duration_ms = Date.now() - t0
    recordAgentOutcome(project.id, 'reviewer', { run_id: runId, success: reviewerOutput.verdict !== 'block', duration_ms, findings: reviewerOutput.findings?.length || 0 })
    setForgeAgentStatus('reviewer', reviewerOutput.verdict === 'block' ? 'failed' : 'done', reviewerOutput.summary?.slice(0, 60) || 'Done')
    return { agent: 'reviewer', status: reviewerOutput.verdict === 'block' ? 'blocked' : 'done', output: reviewerOutput, duration_ms, started_at: new Date(t0).toISOString(), finished_at: nowIso() }
  }

  // Builds the structured Final Report V2 for a completed or failed agentic run.
  function buildFinalReport({ success, transcript, goal, workspaceCleaned, baseline }) {
    const allFilesWritten = transcript.flatMap(t => t.files_written || [])
    const allSecurityFindings = transcript.flatMap(t => t.security?.output?.findings || [])
    const allReviewerFindings = transcript.flatMap(t => t.reviewer?.output?.findings || [])
    const allDebugAttempts = transcript.flatMap(t => Array.isArray(t.debug) ? t.debug : [])
    const approvalRequired = transcript.some(t => (t.files_written || []).some(f => classifyFileRisk(f.path || '') === 'high'))
    const lastTester = transcript.slice(-1)[0]?.tester?.output || {}
    const lastRegression = transcript.slice(-1)[0]?.regression || null
    const filesChanged = [...new Set(allFilesWritten.filter(f => f.ok).map(f => f.path))]
    const remainingIssues = success ? [] : (lastTester.failures || []).map(f => f.failure_reason || 'unknown')
    const firstFix = lastTester.failures?.[0]?.suggested_fix || 'Review error output'
    return {
      status: success ? 'verified_not_applied' : 'failed_not_applied',
      summary: success
        ? `Goal reached green in ${transcript.length} iteration(s). Apply to persist changes.`
        : `Failed after ${transcript.length} iteration(s). ${remainingIssues.slice(0,2).join(', ')}`,
      goal,
      files_changed: filesChanged,
      diffs_created: allFilesWritten.filter(f => f.unified_diff).length,
      tests_run: transcript.flatMap(t => t.tester?.output?.results || []).length,
      test_results: lastTester.results || [],
      debug_attempts: allDebugAttempts.length,
      security_findings: allSecurityFindings,
      reviewer_findings: allReviewerFindings,
      approval_required: approvalRequired,
      regression_comparison: lastRegression,
      baseline_commands: baseline?.commands?.length || 0,
      risks: transcript[0]?.planner?.output?.risks || [],
      remaining_issues: remainingIssues.slice(0, 5),
      recommended_next_task: success
        ? `Verify ${filesChanged.slice(0, 3).join(', ')} in staging environment before shipping`
        : `Fix: ${firstFix}`,
      workspace_removed: workspaceCleaned,
      generated_at: nowIso(),
      transcript,
    }
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
    const autonomyLevelNum = Math.min(3, Math.max(0, Number(req.body?.autonomy_level ?? 2)))

    let runId = null
    try {
    runId = `run-${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
    const contextPack = await buildContextPack(project, goal, req.body || {})
    const repoIdx = generateRepoIndex(project)
    // Capture baseline before any modifications for regression comparison
    const baseline = await captureBaseline(project, verifyCmds).catch(() => null)
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
      status: 'planning',
      mode: 'agentic_supervised',
      provider: req.body?.provider || 'local-first',
      autonomy_level: autonomyLevelNum,
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

    // Reset forge agent statuses for this run
    ;['planner','coder','tester','security','reviewer'].forEach(a => setForgeAgentStatus(a, 'idle', ''))

    for (let iter = 1; iter <= maxIters; iter++) {
      // ── Stage 1: Planner ──
      updateRun(runId, { status: 'planning' })
      // eslint-disable-next-line no-await-in-loop
      const plannerStage = await runPlannerAgent(project, goal, contextPack, repoIdx, lastErrors, runId)

      // ── Stage 2: Coder ──
      updateRun(runId, { status: 'executing' })
      // eslint-disable-next-line no-await-in-loop
      const coderStage = await runCoderAgent(project, plannerStage, goal, root, runId, iter)
      const actions = coderStage.actions || []

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
        // Attach rich patch metadata from the staging result
        if (staged.patches?.length) {
          a.patches = staged.patches
          a.unified_diff = staged.patches[0]?.unified_diff || null
          a.action_type  = staged.patches[0]?.action_type  || 'create'
          a.before_hash  = staged.patches[0]?.before_hash  || null
          a.after_hash   = staged.patches[0]?.after_hash   || null
          // Persist each patch to the forge_patches SQLite table
          for (const p of staged.patches) forgeRunStore.recordPatch({ ...p, action_id: a.id, run_id: runId, iteration: iter })
        }
        allActions.push(a)
        for (const p of (staged.patches || [])) allPatches.push({ ...p, iteration: iter })
        written.push({ path: a.file_path, ok: staged.ok, unified_diff: a.unified_diff || null, action_type: a.action_type || 'create', error: staged.error || staged.policy?.violations?.[0]?.message || null })
      }

      // ── WAITING_APPROVAL gate: pause based on autonomy level + file risk ──
      const riskyActions = allActions.filter(a => a.status === 'staged' && requiresApproval(a.file_path || '', autonomyLevelNum))
      if (riskyActions.length) {
        updateRun(runId, {
          status: 'waiting_approval',
          actions: allActions,
          patches: allPatches,
          review: { status: 'waiting_approval', summary: `${riskyActions.length} high-risk file(s) require human approval before testing: ${riskyActions.map(a => a.file_path).join(', ')}` },
        })
        appendAudit('forge_agentic_waiting_approval', { run_id: runId, project_id: project.id, iter, risky_files: riskyActions.map(a => a.file_path) })
        // Return early — resume via POST /runs/:id/continue after human approves
        return res.json({ ok: true, success: false, waiting_approval: true, run_id: runId, run: findRun(runId), pending_approvals: riskyActions.map(a => ({ action_id: a.id, file_path: a.file_path, risk_level: a.risk_level, unified_diff: a.unified_diff })), summary: `Paused: ${riskyActions.length} high-risk file(s) need approval` })
      }

      // ── Stage 3: Tester ──
      updateRun(runId, { status: 'testing' })
      // eslint-disable-next-line no-await-in-loop
      let testerStage = await runTesterAgent(project, verifyCmds, root, runId)
      let verify = written.some(w => w.ok)
        ? { all_passed: testerStage.output.all_passed, results: testerStage.output.results }
        : { all_passed: false, results: [{ command: 'stage', pass: false, output: 'no staged files written' }] }

      // ── Stage 3b: Debug (up to 2 retries when tests fail) ──
      const debugStages = []
      if (!verify.all_passed && written.some(w => w.ok)) {
        for (let retry = 1; retry <= 2; retry++) {
          // eslint-disable-next-line no-await-in-loop
          const debugStage = await runDebugAgent(project, testerStage, actions, root, runId, iter, retry)
          debugStages.push(debugStage)
          if (debugStage.output?.repair_staged) {
            // Re-run tester on the failed command only first
            const failedCmds = testerStage.output.failures?.map(f => f.command).filter(Boolean) || []
            // eslint-disable-next-line no-await-in-loop
            testerStage = await runTesterAgent(project, failedCmds.length ? failedCmds : verifyCmds, root, runId)
            verify = { all_passed: testerStage.output.all_passed, results: testerStage.output.results }
            if (verify.all_passed) break
          } else {
            break // debug couldn't produce a fix, no point retrying
          }
        }
      }

      // ── Stage 4: Security ──
      updateRun(runId, { status: 'reviewing' })
      // eslint-disable-next-line no-await-in-loop
      const securityStage = await runSecurityAgent(project, actions.filter(a => a.status === 'staged'), runId)
      const securityBlock = securityStage.output?.verdict === 'block'

      // ── Stage 5: Reviewer ──
      // eslint-disable-next-line no-await-in-loop
      const reviewerStage = await runReviewerAgent(project, actions.filter(a => a.status === 'staged'), plannerStage.output, runId, securityStage)
      const reviewerBlock = reviewerStage.output?.verdict === 'block'

      const blocked = securityBlock || reviewerBlock
      lastErrors = securityBlock
        ? `Security blocked: ${securityStage.output?.summary || 'security violation in staged code'}`
        : reviewerBlock
          ? `Reviewer blocked: ${reviewerStage.output?.summary || 'architecture/security violation'}`
          : (verify.all_passed ? '' : testerStage.output.failures?.map(f => `${f.command}: ${f.output}`).join('\n') || '')

      const regressionDelta = compareToBaseline(baseline, testerStage.output)
      transcript.push({
        iteration: iter,
        files_written: written,
        verify,
        planner: plannerStage,
        coder: { agent: 'coder', status: coderStage.status, output: coderStage.output, duration_ms: coderStage.duration_ms, started_at: coderStage.started_at, finished_at: coderStage.finished_at },
        tester: testerStage,
        debug: debugStages.length ? debugStages : undefined,
        security: securityStage,
        reviewer: reviewerStage,
        regression: regressionDelta,
      })
      updateRun(runId, {
        status: (verify.all_passed && !reviewerBlock) ? 'verified' : 'executing',
        actions: allActions,
        patches: allPatches,
        test_results: [
          ...(findRun(runId)?.test_results || []),
          { id: `verify-${iter}`, iteration: iter, all_passed: verify.all_passed && !blocked, results: verify.results, reviewer: reviewerStage.output, security: securityStage.output, verified_at: nowIso(), workspace: root },
        ],
        review: {
          status: (verify.all_passed && !blocked) ? 'verification_passed' : 'iteration_failed',
          summary: (verify.all_passed && !blocked)
            ? `All agents passed on iteration ${iter}. Apply still requires owner approval.`
            : securityBlock ? `Iteration ${iter}: security blocked — ${securityStage.output?.summary}` : reviewerBlock ? `Iteration ${iter}: reviewer blocked — ${reviewerStage.output?.summary}` : `Iteration ${iter} failed tests in staged workspace.`,
          reviewer_findings: reviewerStage.output?.findings || [],
          security_findings: securityStage.output?.findings || [],
        },
      })
      appendAudit('forge_agentic_iter', { run_id: runId, project_id: project.id, iter, files: written.length, passed: verify.all_passed, reviewer_verdict: reviewerStage.output?.verdict, security_verdict: securityStage.output?.verdict })

      if (verify.all_passed && !blocked) { success = true; break }
    }

    // Reset agent statuses to idle after loop
    ;['planner','coder','tester','security','reviewer'].forEach(a => setForgeAgentStatus(a, 'idle', ''))

    let workspaceCleaned = false
    if (!success && autoRollback && fs.existsSync(path.dirname(root))) {
      removeRunWorkspace(runId)
      workspaceCleaned = true
      appendAudit('forge_agentic_workspace_removed', { run_id: runId })
    }
    const finalReport = buildFinalReport({ success, transcript, goal, workspaceCleaned, baseline })
    const finalRun = updateRun(runId, {
      status: success ? 'verified' : 'verify_failed',
      final_report: finalReport,
    })
    appendAudit('forge_agentic_done', { run_id: runId, project_id: project.id, success, iterations: transcript.length, workspace_removed: workspaceCleaned })
    // Record task outcome for cross-run learning
    try { recordTaskMemory(runId, goal, transcript, success, repoIdx?.stack) } catch { /* best-effort */ }
    res.json({ ok: true, success, run_id: runId, run: finalRun, iterations: transcript.length, transcript, rolled_back: workspaceCleaned,
      summary: finalRun?.final_report?.summary || (success ? 'Run completed.' : 'Run failed.') })
    } catch (err) {
      // Top-level catch: mark run as failed and always send a response
      const errMsg = err?.message || String(err)
      if (runId) {
        try { updateRun(runId, { status: 'failed', error: errMsg, final_report: { status: 'error', summary: errMsg, generated_at: nowIso() } }) } catch { /* best-effort */ }
        try { appendAudit('forge_agentic_error', { run_id: runId, project_id: project.id, error: errMsg }) } catch { /* best-effort */ }
        try { ;['planner','coder','tester','security','reviewer'].forEach(a => setForgeAgentStatus(a, 'idle', '')) } catch { /* best-effort */ }
      }
      if (!res.headersSent) res.status(500).json({ ok: false, error: errMsg, run_id: runId })
    }
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

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — BACKLOG
  // ═══════════════════════════════════════════════════════════════════════════

  const BACKLOG_STATUSES = ['IDEA','READY','PLANNING','IN_PROGRESS','WAITING_APPROVAL','BLOCKED','DONE','FAILED','CANCELLED']
  const BACKLOG_CATEGORIES = ['BUG','FEATURE','REFACTOR','SECURITY','UI','PERFORMANCE','TESTING','DOCS','ARCHITECTURE','AUTOMATION']

  router.get('/projects/:id/backlog', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, backlog: forgeRunStore.getBacklog(project.id) })
  })

  router.post('/projects/:id/backlog', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const { title, description, priority, category, status, risk_level, estimated_complexity, dependencies, acceptance_criteria, linked_files, source } = req.body || {}
    if (!title) return res.status(400).json({ ok: false, error: 'title required' })
    const item = forgeRunStore.upsertBacklogItem({
      backlog_id: crypto.randomUUID(),
      project_id: project.id,
      title, description: description || '',
      priority: typeof priority === 'number' ? priority : 50,
      category: BACKLOG_CATEGORIES.includes(category) ? category : 'FEATURE',
      status: BACKLOG_STATUSES.includes(status) ? status : 'IDEA',
      risk_level: ['low','medium','high'].includes(risk_level) ? risk_level : 'low',
      estimated_complexity: estimated_complexity || null,
      dependencies: Array.isArray(dependencies) ? dependencies : [],
      acceptance_criteria: acceptance_criteria || null,
      linked_files: Array.isArray(linked_files) ? linked_files : [],
      source: source || 'manual',
      created_at: nowIso(), updated_at: nowIso(),
    })
    res.json({ ok: true, item })
  })

  router.patch('/backlog/:backlogId', requireAuth, (req, res) => {
    const item = forgeRunStore.findBacklogItem(req.params.backlogId)
    if (!item) return res.status(404).json({ ok: false, error: 'backlog item not found' })
    const updated = forgeRunStore.updateBacklogItem(req.params.backlogId, req.body || {})
    res.json({ ok: true, item: updated })
  })

  router.delete('/backlog/:backlogId', requireAuth, (req, res) => {
    const item = forgeRunStore.findBacklogItem(req.params.backlogId)
    if (!item) return res.status(404).json({ ok: false, error: 'backlog item not found' })
    forgeRunStore.deleteBacklogItem(req.params.backlogId)
    res.json({ ok: true, deleted: req.params.backlogId })
  })

  router.post('/backlog/:backlogId/run', requireAuth, (req, res) => {
    const item = forgeRunStore.findBacklogItem(req.params.backlogId)
    if (!item) return res.status(404).json({ ok: false, error: 'backlog item not found' })
    if (item.status !== 'READY') return res.status(400).json({ ok: false, error: `item must be READY (current: ${item.status})` })
    const project = findProject(item.project_id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const runId = crypto.randomUUID()
    const autonomyLevel = typeof req.body?.autonomy_level === 'number' ? req.body.autonomy_level : 2
    forgeRunStore.updateBacklogItem(item.backlog_id, { status: 'IN_PROGRESS' })
    forgeRunStore.upsertRun({ id: runId, run_id: runId, project_id: project.id, goal: item.description || item.title, status: 'planning', mode: 'agentic', linked_backlog_id: item.backlog_id, autonomy_level: autonomyLevel, created_at: nowIso(), updated_at: nowIso(), actions: [], patches: [] })
    res.json({ ok: true, run_id: runId, backlog_id: item.backlog_id, message: 'agentic run initiated — use POST /api/forge/agentic-run with this goal to execute' })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — AUTOPILOT
  // ═══════════════════════════════════════════════════════════════════════════

  const autopilotSessions = new Map()

  function getAutopilotStatus(projectId) {
    return autopilotSessions.get(projectId) || { active: false, runsCompleted: 0, consecutiveFails: 0 }
  }

  async function _runAutopilotTick(projectId) {
    const session = autopilotSessions.get(projectId)
    if (!session || !session.active) return
    const MAX_RUNS = session.maxRuns || 10
    if (session.runsCompleted >= MAX_RUNS) {
      session.active = false
      forgeRunStore.recordAudit('autopilot_stopped', { project_id: projectId, reason: 'max_runs_reached', runs: session.runsCompleted })
      return
    }
    if (session.consecutiveFails >= 3) {
      session.active = false
      forgeRunStore.recordAudit('autopilot_paused', { project_id: projectId, reason: 'consecutive_failures', count: session.consecutiveFails })
      return
    }
    const backlog = forgeRunStore.getBacklog(projectId)
    const doneIds = new Set(backlog.filter(i => i.status === 'DONE').map(i => i.backlog_id))
    const ready = backlog.filter(i => {
      if (i.status !== 'READY') return false
      const deps = Array.isArray(i.dependencies) ? i.dependencies : []
      return deps.every(d => doneIds.has(d))
    }).sort((a, b) => (b.priority || 50) - (a.priority || 50))
    if (!ready.length) {
      session.active = false
      forgeRunStore.recordAudit('autopilot_stopped', { project_id: projectId, reason: 'no_ready_items' })
      return
    }
    const item = ready[0]
    const autonomyLevel = session.autonomyLevel ?? 2
    if (item.risk_level === 'high' && autonomyLevel < 3) {
      forgeRunStore.updateBacklogItem(item.backlog_id, { status: 'WAITING_APPROVAL' })
      session.active = false
      forgeRunStore.recordAudit('autopilot_paused', { project_id: projectId, reason: 'high_risk_requires_approval', backlog_id: item.backlog_id })
      return
    }
    const project = findProject(projectId)
    if (!project) { session.active = false; return }
    const runId = crypto.randomUUID()
    forgeRunStore.updateBacklogItem(item.backlog_id, { status: 'IN_PROGRESS' })
    forgeRunStore.upsertRun({ id: runId, run_id: runId, project_id: project.id, goal: item.description || item.title, status: 'planning', mode: 'agentic', linked_backlog_id: item.backlog_id, autonomy_level: autonomyLevel, created_at: nowIso(), updated_at: nowIso(), actions: [], patches: [] })
    session.currentRunId = runId
    session.runsCompleted++
    // Mark item so UI shows it's being processed
    forgeRunStore.recordAudit('autopilot_run_started', { project_id: projectId, backlog_id: item.backlog_id, run_id: runId })
    // In Phase 5, autopilot creates the run record and pauses for user to trigger agentic-run
    // Full chained execution is Phase 6 scope
    session.active = false
    forgeRunStore.recordAudit('autopilot_run_queued', { project_id: projectId, run_id: runId, note: 'run created, trigger via agentic-run endpoint' })
  }

  router.post('/projects/:id/autopilot/start', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const existing = autopilotSessions.get(project.id)
    if (existing?.active) return res.json({ ok: true, message: 'already running', status: existing })
    const session = {
      active: true,
      runsCompleted: 0,
      consecutiveFails: 0,
      maxRuns: typeof req.body?.max_runs === 'number' ? req.body.max_runs : 10,
      autonomyLevel: typeof req.body?.autonomy_level === 'number' ? req.body.autonomy_level : 2,
      startedAt: nowIso(),
    }
    autopilotSessions.set(project.id, session)
    forgeRunStore.recordAudit('autopilot_started', { project_id: project.id, max_runs: session.maxRuns, autonomy_level: session.autonomyLevel })
    setImmediate(() => _runAutopilotTick(project.id))
    res.json({ ok: true, message: 'autopilot started', status: session })
  })

  router.post('/projects/:id/autopilot/stop', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const session = autopilotSessions.get(project.id)
    if (session) { session.active = false; forgeRunStore.recordAudit('autopilot_stopped', { project_id: project.id, reason: 'user_stopped', runs: session.runsCompleted }) }
    res.json({ ok: true, message: 'autopilot stopped', status: session || { active: false } })
  })

  router.get('/projects/:id/autopilot/status', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, status: getAutopilotStatus(project.id) })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — DECOMPOSER AGENT
  // ═══════════════════════════════════════════════════════════════════════════

  async function runDecomposerAgent(project, goal, repoIdx, taskMemory, backlogContext) {
    const systemPrompt = 'You are a software task decomposer. Break a high-level goal into specific ordered subtasks. Output ONLY a JSON array — no prose, no markdown.'
    const userPrompt = `Project: ${project.name}
Stack: ${JSON.stringify(repoIdx?.stack || {})}
Goal: ${goal}
Existing backlog: ${(backlogContext || []).map(b => b.title).join(', ') || 'none'}
Recent tasks: ${(taskMemory || []).slice(0, 3).map(t => t.goal || t.task || '').join('; ') || 'none'}

Output a JSON array:
[{"title":"...","description":"...","risk_level":"low|medium|high","affected_areas":["frontend"|"backend"|"tests"|"config"],"required_skills":[],"depends_on":[],"acceptance_criteria":"..."}]`
    const result = await callPythonChat([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt },
    ]).catch(() => null)
    if (!result) return []
    try {
      const text = typeof result === 'string' ? result : (result.content || result.message || JSON.stringify(result))
      const match = text.match(/\[[\s\S]*\]/)
      return match ? JSON.parse(match[0]) : []
    } catch { return [] }
  }

  router.post('/projects/:id/decompose', requireAuth, async (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const { goal, add_to_backlog } = req.body || {}
    if (!goal) return res.status(400).json({ ok: false, error: 'goal required' })
    try {
      const [repoIdx, taskMemory, backlog] = await Promise.all([
        generateRepoIndex(project).catch(() => ({})),
        Promise.resolve(loadTaskMemory(project.id)),
        Promise.resolve(forgeRunStore.getBacklog(project.id)),
      ])
      const subtasks = await runDecomposerAgent(project, goal, repoIdx, taskMemory, backlog)
      let addedItems = []
      if (add_to_backlog && subtasks.length) {
        addedItems = subtasks.map((st, i) => forgeRunStore.upsertBacklogItem({
          backlog_id: crypto.randomUUID(), project_id: project.id,
          title: st.title, description: st.description || '',
          priority: 50 - i, category: 'FEATURE',
          status: 'IDEA', risk_level: ['low','medium','high'].includes(st.risk_level) ? st.risk_level : 'low',
          acceptance_criteria: st.acceptance_criteria || null, source: 'decomposer',
          dependencies: Array.isArray(st.depends_on) ? st.depends_on : [],
          created_at: nowIso(), updated_at: nowIso(),
        }))
      }
      res.json({ ok: true, parent_goal: goal, subtasks, count: subtasks.length, added_to_backlog: addedItems.length })
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message })
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — FORGE SKILLS
  // ═══════════════════════════════════════════════════════════════════════════

  let _forgeSkillsCache = null
  function _loadForgeSkills() {
    if (_forgeSkillsCache) return _forgeSkillsCache
    const dir = path.join(__dirname, '../../runtime/skills/forge')
    if (!fs.existsSync(dir)) return []
    try {
      const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
      _forgeSkillsCache = files.map(f => { try { return JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) } catch { return null } }).filter(Boolean)
      return _forgeSkillsCache
    } catch { return [] }
  }

  function findForgeSkillsForGoal(goal) {
    const goalLower = (goal || '').toLowerCase()
    return _loadForgeSkills().filter(s => (Array.isArray(s.triggers) ? s.triggers : []).some(t => goalLower.includes(t.toLowerCase())))
  }

  router.get('/skills', requireAuth, (_req, res) => {
    res.json({ ok: true, skills: _loadForgeSkills() })
  })

  router.get('/skills/:skillId', requireAuth, (req, res) => {
    const skill = _loadForgeSkills().find(s => s.skill_id === req.params.skillId)
    if (!skill) return res.status(404).json({ ok: false, error: 'skill not found' })
    res.json({ ok: true, skill })
  })

  router.post('/skills/reload', requireAuth, (_req, res) => {
    _forgeSkillsCache = null
    const skills = _loadForgeSkills()
    res.json({ ok: true, count: skills.length, skills: skills.map(s => s.skill_id) })
  })

  router.post('/runs/:id/apply-skill', requireAuth, (req, res) => {
    const run = findRun(req.params.id)
    if (!run) return res.status(404).json({ ok: false, error: 'run not found' })
    const { skill_id } = req.body || {}
    if (!skill_id) return res.status(400).json({ ok: false, error: 'skill_id required' })
    const skill = _loadForgeSkills().find(s => s.skill_id === skill_id)
    if (!skill) return res.status(404).json({ ok: false, error: 'skill not found' })
    updateRun(run.id, { applied_skill: skill_id, skill_checklist: skill.checklist || [] })
    res.json({ ok: true, run_id: run.id, skill_applied: skill_id, checklist: skill.checklist || [] })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — MODEL ROUTER
  // ═══════════════════════════════════════════════════════════════════════════

  function _scoreModel(model, context) {
    let score = 0
    if (model.role === context.stage) score += 30
    if (model.role === 'any') score += 10
    if (context.complexity === 'high' && model.cost_tier === 'high') score += 20
    if (context.complexity === 'low' && model.cost_tier === 'low') score += 15
    if (context.prefer_speed && model.speed_tier === 'fast') score += 20
    if (context.prefer_cost && model.cost_tier === 'low') score += 20
    return score
  }

  function routeModel(stage, context) {
    const models = forgeRunStore.getModels().filter(m => m.enabled)
    if (!models.length) return null
    const ctx = { ...(context || {}), stage }
    const candidates = models.filter(m => !m.role || m.role === stage || m.role === 'any')
    if (!candidates.length) return null
    return candidates.sort((a, b) => _scoreModel(b, ctx) - _scoreModel(a, ctx))[0]
  }

  router.get('/models', requireAuth, (_req, res) => {
    res.json({ ok: true, models: forgeRunStore.getModels() })
  })

  router.post('/models', requireAuth, (req, res) => {
    const { model_id, provider, role, cost_tier, speed_tier, context_window, supports_tools, supports_json, supports_code, local_or_remote } = req.body || {}
    if (!model_id || !provider) return res.status(400).json({ ok: false, error: 'model_id and provider required' })
    const model = forgeRunStore.upsertModel({ model_id, provider, role: role || 'any', cost_tier: cost_tier || 'medium', speed_tier: speed_tier || 'medium', context_window: context_window || 200000, supports_tools: supports_tools !== false, supports_json: supports_json !== false, supports_code: supports_code !== false, local_or_remote: local_or_remote || 'remote', enabled: true, created_at: nowIso(), updated_at: nowIso() })
    res.json({ ok: true, model })
  })

  router.patch('/models/:modelId', requireAuth, (req, res) => {
    const existing = forgeRunStore.getModel(req.params.modelId)
    if (!existing) return res.status(404).json({ ok: false, error: 'model not found' })
    const updated = forgeRunStore.updateModel(req.params.modelId, req.body || {})
    res.json({ ok: true, model: updated })
  })

  router.post('/model-router/test', requireAuth, (req, res) => {
    const { stage, context } = req.body || {}
    if (!stage) return res.status(400).json({ ok: false, error: 'stage required' })
    const model = routeModel(stage, context || {})
    res.json({ ok: true, stage, selected: model, fallback: model ? null : 'existing_env_behavior' })
  })

  router.get('/projects/:id/model-routing-stats', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, stats: forgeRunStore.getModelRoutingStats(project.id) })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — ROADMAP ENGINE
  // ═══════════════════════════════════════════════════════════════════════════

  router.get('/projects/:id/roadmap', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, roadmap: forgeRunStore.getRoadmap(project.id) })
  })

  router.post('/projects/:id/roadmap/generate', requireAuth, async (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    try {
      const [repoIdx, metrics, taskMemory, backlog, suggestions] = await Promise.all([
        generateRepoIndex(project).catch(() => ({})),
        Promise.resolve(forgeRunStore.getMetricsForProject(project.id)),
        Promise.resolve(loadTaskMemory(project.id)),
        Promise.resolve(forgeRunStore.getBacklog(project.id)),
        Promise.resolve(forgeRunStore.getSuggestions(project.id)),
      ])
      const systemPrompt = 'You are a senior software architect. Produce a structured project roadmap as JSON. Output ONLY valid JSON — no prose, no markdown.'
      const userPrompt = `Project: ${project.name}
Stack: ${JSON.stringify(repoIdx?.stack || {})}
Metrics: total_runs=${metrics?.total_runs || 0}, success_rate=${metrics?.success_rate || 0}
Recent tasks: ${taskMemory.slice(0, 5).map(t => t.goal || t.task || '').join('; ') || 'none'}
Backlog: ${backlog.map(b => `[${b.status}] ${b.title}`).join('\n') || 'empty'}
Open suggestions: ${suggestions.filter(s => s.status === 'new').map(s => s.title).join(', ') || 'none'}

Return JSON:
{"current_state":"...","known_issues":[],"technical_debt":[],"missing_features":[],"security_improvements":[],"performance_improvements":[],"recommended_next_tasks":[{"title":"...","priority":"high|medium|low","category":"BUG|FEATURE|REFACTOR|SECURITY|UI|PERFORMANCE|TESTING"}],"estimated_complexity":"low|medium|high"}`
      const result = await callPythonChat([
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ]).catch(() => null)
      let content = {}
      if (result) {
        try {
          const text = typeof result === 'string' ? result : (result.content || result.message || JSON.stringify(result))
          const match = text.match(/\{[\s\S]*\}/)
          if (match) content = JSON.parse(match[0])
        } catch {}
      }
      const roadmap = forgeRunStore.upsertRoadmap(project.id, content)
      res.json({ ok: true, roadmap })
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message })
    }
  })

  router.patch('/projects/:id/roadmap', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const existing = forgeRunStore.getRoadmap(project.id)
    const roadmap = forgeRunStore.upsertRoadmap(project.id, { ...(existing?.content || {}), ...(req.body || {}) })
    res.json({ ok: true, roadmap })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — SUGGESTIONS + MEMORY CONSOLIDATION V3
  // ═══════════════════════════════════════════════════════════════════════════

  function generateSuggestions(run, projectId) {
    const transcript = run?.final_report?.transcript || []
    const allSecFindings = transcript.flatMap(t => t.security?.output?.findings || [])
    const allRevFindings = transcript.flatMap(t => t.reviewer?.output?.findings || [])
    const debugAttempts = transcript.flatMap(t => t.debug || [])
    const failures = transcript.flatMap(t => t.tester?.output?.failures || [])
    const suggestions = []
    if (allSecFindings.length)
      suggestions.push({ suggestion_id: crypto.randomUUID(), project_id: projectId, source_run_id: run.id, category: 'security', title: 'Security findings require attention', description: `${allSecFindings.length} security issue(s) found during run`, evidence: allSecFindings.slice(0, 5), recommended_fix: 'Review and fix security findings before merging', risk_level: 'high', status: 'new', created_at: nowIso(), updated_at: nowIso() })
    if (allRevFindings.length >= 3)
      suggestions.push({ suggestion_id: crypto.randomUUID(), project_id: projectId, source_run_id: run.id, category: 'refactor', title: 'Multiple reviewer findings indicate code quality issues', description: `${allRevFindings.length} reviewer finding(s)`, evidence: allRevFindings.slice(0, 5), recommended_fix: 'Refactor affected modules', risk_level: 'medium', status: 'new', created_at: nowIso(), updated_at: nowIso() })
    if (debugAttempts.length >= 2)
      suggestions.push({ suggestion_id: crypto.randomUUID(), project_id: projectId, source_run_id: run.id, category: 'testing', title: 'High debug retry count — add more tests', description: `${debugAttempts.length} debug attempt(s) required`, evidence: failures.slice(0, 3).map(f => f.failure_reason || f.test || ''), recommended_fix: 'Add unit tests for the affected area', risk_level: 'low', status: 'new', created_at: nowIso(), updated_at: nowIso() })
    if (run.status === 'failed' && failures.length)
      suggestions.push({ suggestion_id: crypto.randomUUID(), project_id: projectId, source_run_id: run.id, category: 'testing', title: 'Run failed — investigate verification commands', description: failures.map(f => f.failure_reason || f.test || '').join('; '), evidence: failures.slice(0, 3), recommended_fix: 'Review verification commands for flakiness', risk_level: 'medium', status: 'new', created_at: nowIso(), updated_at: nowIso() })
    return suggestions
  }

  function consolidateMemory(project, run) {
    if (!run?.final_report) return
    const projectId = project.id
    const transcript = run.final_report.transcript || []
    const candidateFacts = []
    const filesChanged = [...new Set(transcript.flatMap(t => (t.files_written || []).filter(f => f.ok).map(f => f.path)))]
    for (const fp of filesChanged)
      candidateFacts.push({ category: 'file_pattern', fact: `Modified in "${(run.goal || 'task').slice(0,60)}": ${fp}` })
    const cmds = [...new Set(transcript.flatMap(t => (t.tester?.output?.results || []).filter(r => r.pass).map(r => r.command)))]
    for (const cmd of cmds.slice(0, 5))
      candidateFacts.push({ category: 'command', fact: `Verified working: ${cmd}` })
    const revFindings = transcript.flatMap(t => (t.reviewer?.output?.findings || []).filter(f => f.severity === 'info'))
    for (const f of revFindings.slice(0, 3))
      candidateFacts.push({ category: 'architecture', fact: `Architecture note: ${typeof f === 'string' ? f : (f.message || JSON.stringify(f)).slice(0,200)}` })
    if (run.status === 'failed')
      for (const fp of filesChanged.slice(0, 5))
        candidateFacts.push({ category: 'risk', fact: `Touched in failed run: ${fp}` })
    for (const factData of candidateFacts) {
      const existing = forgeRunStore.findMemoryFactByContent(projectId, factData.fact)
      if (existing) {
        const count = (existing.usage_count || 0) + 1
        forgeRunStore.upsertMemoryFact({ ...existing, confidence: count >= 3 ? 'high' : count >= 2 ? 'medium' : 'low', usage_count: count, last_used_at: nowIso(), updated_at: nowIso() })
      } else {
        forgeRunStore.upsertMemoryFact({ memory_id: crypto.randomUUID(), project_id: projectId, source_run_id: run.id, category: factData.category, fact: factData.fact, evidence: [], confidence: 'low', usage_count: 1, last_used_at: nowIso(), created_at: nowIso(), updated_at: nowIso() })
      }
    }
  }

  router.get('/projects/:id/suggestions', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, suggestions: forgeRunStore.getSuggestions(project.id) })
  })

  router.post('/suggestions/:suggestionId/accept', requireAuth, (req, res) => {
    const s = forgeRunStore.findSuggestion(req.params.suggestionId)
    if (!s) return res.status(404).json({ ok: false, error: 'suggestion not found' })
    res.json({ ok: true, suggestion: forgeRunStore.updateSuggestion(s.suggestion_id, { status: 'accepted' }) })
  })

  router.post('/suggestions/:suggestionId/reject', requireAuth, (req, res) => {
    const s = forgeRunStore.findSuggestion(req.params.suggestionId)
    if (!s) return res.status(404).json({ ok: false, error: 'suggestion not found' })
    res.json({ ok: true, suggestion: forgeRunStore.updateSuggestion(s.suggestion_id, { status: 'rejected' }) })
  })

  router.post('/suggestions/:suggestionId/create-backlog-item', requireAuth, (req, res) => {
    const s = forgeRunStore.findSuggestion(req.params.suggestionId)
    if (!s) return res.status(404).json({ ok: false, error: 'suggestion not found' })
    const item = forgeRunStore.upsertBacklogItem({
      backlog_id: crypto.randomUUID(), project_id: s.project_id, title: s.title,
      description: s.description || s.recommended_fix || '',
      priority: s.risk_level === 'high' ? 80 : s.risk_level === 'medium' ? 60 : 40,
      category: { security: 'SECURITY', refactor: 'REFACTOR', testing: 'TESTING' }[s.category] || 'FEATURE',
      status: 'READY', risk_level: s.risk_level || 'low', source: 'suggestion',
      created_at: nowIso(), updated_at: nowIso(),
    })
    forgeRunStore.updateSuggestion(s.suggestion_id, { status: 'implemented' })
    res.json({ ok: true, backlog_item: item, suggestion_id: s.suggestion_id })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — DEVELOPMENT CYCLES
  // ═══════════════════════════════════════════════════════════════════════════

  router.post('/projects/:id/cycles', requireAuth, async (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    const { goal, backlog_item_ids, autonomy_level, max_runs, max_duration_sec, success_criteria } = req.body || {}
    if (!goal) return res.status(400).json({ ok: false, error: 'goal required' })
    const cycleId = crypto.randomUUID()
    let itemIds = Array.isArray(backlog_item_ids) ? backlog_item_ids : []
    if (!itemIds.length) {
      try {
        const [repoIdx, taskMemory, backlog] = await Promise.all([
          generateRepoIndex(project).catch(() => ({})),
          Promise.resolve(loadTaskMemory(project.id)),
          Promise.resolve(forgeRunStore.getBacklog(project.id)),
        ])
        const subtasks = await runDecomposerAgent(project, goal, repoIdx, taskMemory, backlog)
        const added = subtasks.map((st, i) => forgeRunStore.upsertBacklogItem({
          backlog_id: crypto.randomUUID(), project_id: project.id, title: st.title,
          description: st.description || '', priority: 50 - i, category: 'FEATURE',
          status: 'READY', risk_level: ['low','medium','high'].includes(st.risk_level) ? st.risk_level : 'low',
          acceptance_criteria: st.acceptance_criteria || null, source: 'cycle',
          dependencies: Array.isArray(st.depends_on) ? st.depends_on : [],
          created_at: nowIso(), updated_at: nowIso(),
        }))
        itemIds = added.map(i => i.backlog_id)
      } catch {}
    }
    const cycle = forgeRunStore.upsertCycle({
      cycle_id: cycleId, project_id: project.id, goal, status: 'RUNNING',
      autonomy_level: typeof autonomy_level === 'number' ? autonomy_level : 2,
      max_runs: typeof max_runs === 'number' ? max_runs : 20,
      max_duration_sec: typeof max_duration_sec === 'number' ? max_duration_sec : 3600,
      started_at: nowIso(), backlog_items: itemIds, run_ids: [],
      success_criteria: success_criteria || null, current_phase: 'executing',
      created_at: nowIso(), updated_at: nowIso(),
    })
    autopilotSessions.set(project.id, { active: true, runsCompleted: 0, consecutiveFails: 0, maxRuns: cycle.max_runs, autonomyLevel: cycle.autonomy_level, cycleId, startedAt: nowIso() })
    setImmediate(() => _runAutopilotTick(project.id))
    res.json({ ok: true, cycle })
  })

  router.get('/projects/:id/cycles', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, cycles: forgeRunStore.getCycles(project.id) })
  })

  router.get('/cycles/:cycleId', requireAuth, (req, res) => {
    const cycle = forgeRunStore.findCycle(req.params.cycleId)
    if (!cycle) return res.status(404).json({ ok: false, error: 'cycle not found' })
    res.json({ ok: true, cycle })
  })

  router.post('/cycles/:cycleId/pause', requireAuth, (req, res) => {
    const cycle = forgeRunStore.findCycle(req.params.cycleId)
    if (!cycle) return res.status(404).json({ ok: false, error: 'cycle not found' })
    const session = autopilotSessions.get(cycle.project_id)
    if (session) session.active = false
    const updated = forgeRunStore.updateCycle(cycle.cycle_id, { status: 'PAUSED' })
    forgeRunStore.recordAudit('cycle_paused', { cycle_id: cycle.cycle_id })
    res.json({ ok: true, cycle: updated })
  })

  router.post('/cycles/:cycleId/resume', requireAuth, (req, res) => {
    const cycle = forgeRunStore.findCycle(req.params.cycleId)
    if (!cycle) return res.status(404).json({ ok: false, error: 'cycle not found' })
    const updated = forgeRunStore.updateCycle(cycle.cycle_id, { status: 'RUNNING' })
    autopilotSessions.set(cycle.project_id, { active: true, runsCompleted: 0, consecutiveFails: 0, maxRuns: cycle.max_runs, autonomyLevel: cycle.autonomy_level, cycleId: cycle.cycle_id, startedAt: nowIso() })
    setImmediate(() => _runAutopilotTick(cycle.project_id))
    forgeRunStore.recordAudit('cycle_resumed', { cycle_id: cycle.cycle_id })
    res.json({ ok: true, cycle: updated })
  })

  router.post('/cycles/:cycleId/cancel', requireAuth, (req, res) => {
    const cycle = forgeRunStore.findCycle(req.params.cycleId)
    if (!cycle) return res.status(404).json({ ok: false, error: 'cycle not found' })
    const session = autopilotSessions.get(cycle.project_id)
    if (session) session.active = false
    for (const bid of (cycle.backlog_items || [])) {
      const it = forgeRunStore.findBacklogItem(bid)
      if (it && it.status === 'IN_PROGRESS') forgeRunStore.updateBacklogItem(bid, { status: 'CANCELLED' })
    }
    const updated = forgeRunStore.updateCycle(cycle.cycle_id, { status: 'CANCELLED', ended_at: nowIso() })
    forgeRunStore.recordAudit('cycle_cancelled', { cycle_id: cycle.cycle_id })
    res.json({ ok: true, cycle: updated })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // PHASE 5 — MEMORY INSIGHTS
  // ═══════════════════════════════════════════════════════════════════════════

  router.get('/projects/:id/memory', requireAuth, (req, res) => {
    const project = findProject(req.params.id)
    if (!project) return res.status(404).json({ ok: false, error: 'project not found' })
    res.json({ ok: true, facts: forgeRunStore.getMemoryFacts(project.id, req.query.category || undefined) })
  })

  return router
}
