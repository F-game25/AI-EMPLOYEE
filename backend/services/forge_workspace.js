'use strict'

const fs = require('fs')
const path = require('path')
const os = require('os')
const { spawnSync } = require('child_process')

const STATE_DIR = path.resolve(
  process.env.STATE_DIR ||
  process.env.AI_EMPLOYEE_STATE_DIR ||
  path.join(os.homedir(), '.ai-employee', 'state')
)
const FORGE_HOME = path.resolve(
  process.env.AI_EMPLOYEE_FORGE_HOME ||
  path.join(STATE_DIR, 'forge')
)
const RUN_WORKSPACES_DIR = path.join(FORGE_HOME, 'runs')

const PROJECT_SKIP = new Set(['.git', 'node_modules', '__pycache__', '.ascendforge', 'dist', 'build', '.DS_Store'])
const MAX_STAGED_COPY_FILES = 2500
const MAX_STAGED_COPY_BYTES = 50 * 1024 * 1024

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return fallback }
}

function nowIso() { return new Date().toISOString() }

function safeProjectRoot(project) {
  return path.resolve(project.root_path || '')
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
      if (entry.isDirectory()) { copyDir(from, to); continue }
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
  return {
    copied_files: copiedFiles,
    copied_bytes: copiedBytes,
    truncated: copiedFiles >= MAX_STAGED_COPY_FILES || copiedBytes >= MAX_STAGED_COPY_BYTES,
  }
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
  if (!added.ok) return { ok: false, reason: 'worktree_add_failed', detail: added.stderr || added.stdout }
  return {
    ok: true,
    workspace_mode: 'git_worktree',
    git_root: source.root,
    git_head: source.head,
    created_from: source.head,
  }
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
  fs.writeFileSync(
    path.join(workspace, '.forge_workspace.json'),
    JSON.stringify({
      run_id: run.id,
      project_id: project.id,
      source_root: safeProjectRoot(project),
      created_at: nowIso(),
      ...workspaceInfo,
    }, null, 2)
  )
  return workspace
}

module.exports = {
  runWorkspaceRoot,
  copyProjectToWorkspace,
  ensureRunWorkspace,
  removeRunWorkspace,
  readWorkspaceMetadata,
  runGit,
  createGitWorktreeWorkspace,
  gitWorkspaceSource,
}
