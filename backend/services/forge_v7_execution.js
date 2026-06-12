'use strict'

const fs = require('fs')
const path = require('path')
const os = require('os')
const crypto = require('crypto')
const { spawnSync } = require('child_process')
const forgeWorkspace = require('./forge_workspace')
const forgeDiff = require('./forge_diff')

function nowIso() { return new Date().toISOString() }

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return fallback }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

function id(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${crypto.randomBytes(4).toString('hex')}`
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function redact(text) {
  return String(text || '')
    .replace(/(ghp_|github_pat_|sk-[A-Za-z0-9_-]{12,})[A-Za-z0-9_\-]*/g, '[REDACTED_TOKEN]')
    .replace(/([A-Z0-9_]*(?:TOKEN|SECRET|KEY|PASSWORD)[A-Z0-9_]*\s*=\s*)[^\s]+/gi, '$1[REDACTED]')
    .slice(0, 12000)
}

function safeRel(filePath) {
  const rel = String(filePath || '').replace(/\\/g, '/').replace(/^\/+/, '')
  if (!rel || rel.includes('\0') || rel.startsWith('../') || rel.includes('/../')) return null
  return rel
}

function commandExists(bin) {
  const result = spawnSync(process.platform === 'win32' ? 'where' : 'which', [bin], { encoding: 'utf8', timeout: 3000 })
  return result.status === 0
}

class ForgeV7ExecutionStore {
  constructor({ forgeHome }) {
    this.forgeHome = forgeHome || path.join(os.homedir(), '.ai-employee', 'state', 'forge')
    this.baseDir = path.join(this.forgeHome, 'v7')
    this.stateFile = path.join(this.baseDir, 'execution_state.json')
    this.workspacesDir = path.join(this.baseDir, 'workspaces')
  }

  blankState() {
    return {
      patchProposals: [],
      workspaces: [],
      validationRuns: [],
      applyApprovals: [],
      appliedChanges: [],
      rollbackArtifacts: [],
      reports: [],
      memoryLessons: [],
      updated_at: nowIso(),
    }
  }

  load() {
    const state = readJson(this.stateFile, this.blankState())
    return { ...this.blankState(), ...state }
  }

  save(state) {
    writeJson(this.stateFile, { ...state, updated_at: nowIso() })
  }

  list(projectId) {
    const state = this.load()
    const byProject = item => !projectId || item.project_id === projectId
    return {
      patchProposals: state.patchProposals.filter(byProject),
      workspaces: state.workspaces.filter(byProject),
      validationRuns: state.validationRuns.filter(byProject),
      applyApprovals: state.applyApprovals.filter(byProject),
      appliedChanges: state.appliedChanges.filter(byProject),
      rollbackArtifacts: state.rollbackArtifacts.filter(byProject),
      reports: state.reports.filter(byProject),
      memoryLessons: state.memoryLessons.filter(byProject),
      updated_at: state.updated_at,
    }
  }

  upsert(key, item, idKey) {
    const state = this.load()
    const list = asArray(state[key])
    const value = item[idKey]
    state[key] = [{ ...item, updated_at: nowIso() }, ...list.filter(existing => existing[idKey] !== value)].slice(0, 1000)
    this.save(state)
    return state[key][0]
  }

  find(key, idKey, value) {
    return asArray(this.load()[key]).find(item => item[idKey] === value) || null
  }

  latestForGoal(key, projectId, goalId) {
    return asArray(this.load()[key]).find(item => item.project_id === projectId && item.goal_id === goalId) || null
  }

  createPatchProposal(project, goal, body = {}) {
    const files = asArray(body.files || body.file_patches).map(file => ({
      path: safeRel(file.path || file.file_path),
      content: typeof file.content === 'string' ? file.content : null,
    })).filter(file => file.path)
    const filesIntended = asArray(body.files_intended).map(safeRel).filter(Boolean)
    for (const file of files) if (!filesIntended.includes(file.path)) filesIntended.push(file.path)
    const diff = String(body.diff || body.patch || '').trim()
    if (!diff && !files.length) {
      const err = new Error('diff or file patch content required')
      err.status = 400
      throw err
    }
    const risk = String(body.risk_level || (filesIntended.length > 5 ? 'CAUTION' : 'SAFE')).toUpperCase()
    const artifact = {
      artifact_id: id('v7patch'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      type: 'patch_proposal',
      title: String(body.title || goal.title || 'Patch proposal').slice(0, 180),
      summary: String(body.summary || goal.description || goal.title || 'Patch proposal').slice(0, 2000),
      files_intended: filesIntended,
      diff: redact(diff),
      file_patches: files,
      risk_level: ['SAFE', 'CAUTION', 'DANGEROUS', 'BLOCKED'].includes(risk) ? risk : 'CAUTION',
      requires_approval: true,
      rollback_plan: String(body.rollback_plan || 'Restore the recorded before-state for every changed file and rerun validation.').slice(0, 2000),
      created_by_agent_run_id: body.created_by_agent_run_id || body.run_id || null,
      created_at: nowIso(),
      status: risk === 'BLOCKED' ? 'blocked' : 'proposed',
    }
    return this.upsert('patchProposals', artifact, 'artifact_id')
  }

  createWorkspace(project, goal, proposal) {
    const workspaceId = id('v7ws')
    const target = path.join(this.workspacesDir, workspaceId)
    const projectRoot = forgeWorkspace.safeProjectRoot(project)
    let mode = 'proposal_only'
    let status = 'blocked'
    let detail = null
    let baseRef = null

    ensureDir(path.dirname(target))
    const inside = forgeWorkspace.runGit(projectRoot, ['rev-parse', '--is-inside-work-tree'], 8000)
    if (inside.ok && inside.stdout === 'true') {
      const top = forgeWorkspace.runGit(projectRoot, ['rev-parse', '--show-toplevel'], 8000)
      const head = forgeWorkspace.runGit(projectRoot, ['rev-parse', 'HEAD'], 8000)
      if (top.ok && head.ok && top.stdout && head.stdout) {
        const add = forgeWorkspace.runGit(top.stdout, ['worktree', 'add', '--detach', target, head.stdout], 60000)
        if (add.ok) {
          mode = 'git_worktree'
          status = 'created'
          baseRef = head.stdout
        } else {
          detail = add.stderr || add.stdout
        }
      }
    }

    if (status !== 'created') {
      try {
        const copied = forgeWorkspace.copyProjectToWorkspace(project, target)
        mode = 'temp_copy'
        status = 'created'
        detail = copied
      } catch (err) {
        detail = err.message
      }
    }

    const workspace = {
      workspace_id: workspaceId,
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      patch_artifact_id: proposal.artifact_id,
      mode,
      path: status === 'created' ? target : null,
      status,
      base_ref: baseRef,
      files_touched: [],
      artifacts: [],
      detail,
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    return this.upsert('workspaces', workspace, 'workspace_id')
  }

  applyPatchInWorkspace(workspace, proposal, project) {
    if (!workspace?.path || !fs.existsSync(workspace.path)) {
      const err = new Error('workspace unavailable')
      err.status = 404
      throw err
    }
    if (proposal.risk_level === 'BLOCKED') {
      const err = new Error('blocked patch cannot be applied')
      err.status = 409
      throw err
    }

    const touched = new Set()
    let applyOutput = ''
    if (proposal.diff) {
      const patchFile = path.join(workspace.path, '.forge_v7_patch.diff')
      fs.writeFileSync(patchFile, proposal.diff, 'utf8')
      const applied = forgeWorkspace.runGit(workspace.path, ['apply', '--whitespace=nowarn', patchFile], 30000)
      applyOutput = applied.stdout || applied.stderr
      try { fs.unlinkSync(patchFile) } catch { /* ignore */ }
      if (!applied.ok) {
        const updated = this.upsert('workspaces', { ...workspace, status: 'failed', apply_error: redact(applyOutput) }, 'workspace_id')
        const err = new Error(redact(applyOutput) || 'patch apply failed')
        err.status = 409
        err.workspace = updated
        throw err
      }
      for (const file of proposal.files_intended || []) touched.add(file)
    }

    for (const file of proposal.file_patches || []) {
      const rel = safeRel(file.path)
      if (!rel || typeof file.content !== 'string') continue
      const target = path.join(workspace.path, rel)
      ensureDir(path.dirname(target))
      fs.writeFileSync(target, file.content, 'utf8')
      touched.add(rel)
    }

    const filesTouched = Array.from(touched)
    const diff = this.diffWorkspace(project, workspace, filesTouched)
    const updated = this.upsert('workspaces', {
      ...workspace,
      status: 'patch_applied',
      files_touched: filesTouched,
      artifacts: [...asArray(workspace.artifacts), { type: 'applied_diff', diff }],
      apply_output: redact(applyOutput),
    }, 'workspace_id')
    return { workspace: updated, applied_diff: diff }
  }

  diffWorkspace(project, workspace, files) {
    const relFiles = asArray(files).map(safeRel).filter(Boolean)
    if (workspace.mode === 'git_worktree') {
      const result = forgeWorkspace.runGit(workspace.path, ['diff', '--', ...relFiles], 20000)
      return redact(result.stdout || '')
    }
    const projectRoot = forgeWorkspace.safeProjectRoot(project)
    return relFiles.map(rel => {
      const beforePath = path.join(projectRoot, rel)
      const afterPath = path.join(workspace.path, rel)
      const before = fs.existsSync(beforePath) ? fs.readFileSync(beforePath, 'utf8') : ''
      const after = fs.existsSync(afterPath) ? fs.readFileSync(afterPath, 'utf8') : ''
      return forgeDiff.generateUnifiedDiff(before, after, rel)
    }).join('\n')
  }

  selectValidationCommands(project, changedFiles, root) {
    const commands = []
    const files = asArray(changedFiles)
    const frontendChanged = files.some(file => file.startsWith('frontend/'))
    const packagePath = frontendChanged ? path.join(root, 'frontend', 'package.json') : path.join(root, 'package.json')
    if (fs.existsSync(packagePath) && commandExists('npm')) {
      const pkg = readJson(packagePath, {})
      const cwd = path.dirname(packagePath)
      if (pkg.scripts?.build) commands.push({ id: 'npm_build', label: 'npm run build', command: 'npm', args: ['run', 'build'], cwd })
      if (pkg.scripts?.lint) commands.push({ id: 'npm_lint', label: 'npm run lint', command: 'npm', args: ['run', 'lint'], cwd })
      if (pkg.scripts?.test) commands.push({ id: 'npm_test', label: 'npm test', command: 'npm', args: ['test'], cwd })
    }
    const pyFiles = files.filter(file => file.endsWith('.py') && fs.existsSync(path.join(root, file)))
    if (pyFiles.length && commandExists('python3')) {
      commands.push({ id: 'python_compile', label: 'python3 -m py_compile', command: 'python3', args: ['-m', 'py_compile', ...pyFiles], cwd: root })
    }
    commands.push({ id: 'secret_scan', label: 'changed file token scan', internal: 'secret_scan', cwd: root })
    commands.push({ id: 'dangerous_scan', label: 'dangerous command scan', internal: 'dangerous_scan', cwd: root })
    return commands
  }

  runValidation(project, workspace, proposal, phase = 'sandbox') {
    const root = phase === 'post_apply' ? forgeWorkspace.safeProjectRoot(project) : workspace.path
    if (!root || !fs.existsSync(root)) {
      const err = new Error('validation root unavailable')
      err.status = 404
      throw err
    }
    const changedFiles = asArray(workspace.files_touched?.length ? workspace.files_touched : proposal.files_intended)
    const commands = this.selectValidationCommands(project, changedFiles, root)
    const started = Date.now()
    const results = commands.map(command => {
      const itemStarted = Date.now()
      if (command.internal) return this.runInternalValidation(command, root, changedFiles, itemStarted)
      const result = spawnSync(command.command, command.args, {
        cwd: command.cwd,
        encoding: 'utf8',
        timeout: 120000,
        maxBuffer: 1024 * 1024,
      })
      return {
        id: command.id,
        label: command.label,
        command: [command.command, ...command.args].join(' '),
        cwd: path.relative(root, command.cwd) || '.',
        status: result.status === 0 ? 'passed' : 'failed',
        duration_ms: Date.now() - itemStarted,
        output_summary: redact(`${result.stdout || ''}\n${result.stderr || result.error?.message || ''}`),
      }
    })
    const failed = results.filter(item => item.status === 'failed')
    const unavailable = results.filter(item => item.status === 'unavailable')
    const validation = {
      validation_id: id('v7val'),
      project_id: project.id,
      goal_id: workspace.goal_id,
      workspace_id: workspace.workspace_id,
      patch_artifact_id: proposal.artifact_id,
      phase,
      status: failed.length ? 'failed' : unavailable.length ? 'partially_verified' : 'passed',
      commands: results,
      duration_ms: Date.now() - started,
      evidence: {
        files_checked: changedFiles,
        failed_checks: failed.map(item => item.id),
        unavailable_checks: unavailable.map(item => item.id),
      },
      created_at: nowIso(),
    }
    const saved = this.upsert('validationRuns', validation, 'validation_id')
    this.upsert('workspaces', { ...workspace, status: phase === 'post_apply' ? workspace.status : 'validated', latest_validation_id: saved.validation_id }, 'workspace_id')
    return saved
  }

  runInternalValidation(command, root, changedFiles, started) {
    const patterns = command.internal === 'secret_scan'
      ? [/(ghp_|github_pat_|sk-[A-Za-z0-9_-]{12,})[A-Za-z0-9_\-]*/g, /\b(?:TOKEN|SECRET|PASSWORD)\s*=\s*['"]?[^'"\s]+/gi]
      : [/\brm\s+-rf\b/, /\bgit\s+push\b/, /\bchild_process\.exec\b/, /\beval\s*\(/]
    const hits = []
    for (const rel of changedFiles) {
      const file = path.join(root, rel)
      if (!fs.existsSync(file) || fs.statSync(file).size > 512 * 1024) continue
      const text = fs.readFileSync(file, 'utf8')
      if (patterns.some(pattern => pattern.test(text))) hits.push(rel)
    }
    return {
      id: command.id,
      label: command.label,
      command: command.internal,
      cwd: '.',
      status: hits.length ? 'failed' : 'passed',
      duration_ms: Date.now() - started,
      output_summary: hits.length ? `Pattern hits in: ${hits.join(', ')}` : 'No blocked patterns detected.',
    }
  }

  requestApply(project, goal, proposal, workspace, validation, body = {}) {
    const filesChanged = workspace.files_touched?.length ? workspace.files_touched : proposal.files_intended
    const approval = {
      approval_id: id('v7approval'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      type: 'apply_patch',
      patch_artifact_id: proposal.artifact_id,
      workspace_id: workspace.workspace_id,
      risk_level: proposal.risk_level,
      summary: proposal.summary,
      files_changed: filesChanged,
      quality_gate_status: validation?.status === 'passed' ? 'passed' : validation?.status || 'unavailable',
      validation_summary: validation ? `${validation.status}: ${validation.commands.length} checks` : 'validation unavailable',
      rollback_plan: proposal.rollback_plan,
      status: 'pending',
      stage_only: Boolean(body.stage_only),
      commit_excluded: true,
      push_excluded: true,
      created_at: nowIso(),
    }
    return this.upsert('applyApprovals', approval, 'approval_id')
  }

  decideApproval(approvalId, status, actor, reason = '') {
    const approval = this.find('applyApprovals', 'approval_id', approvalId)
    if (!approval) {
      const err = new Error('approval not found')
      err.status = 404
      throw err
    }
    return this.upsert('applyApprovals', {
      ...approval,
      status,
      decided_at: nowIso(),
      decided_by: actor || 'operator',
      reason,
    }, 'approval_id')
  }

  applyApproved(project, goal, proposal, workspace, approval, body = {}) {
    if (!approval || approval.status !== 'approved') {
      const err = new Error('approved apply approval required')
      err.status = 403
      throw err
    }
    if (!workspace?.path || !fs.existsSync(workspace.path)) {
      const err = new Error('workspace unavailable')
      err.status = 404
      throw err
    }
    const projectRoot = forgeWorkspace.safeProjectRoot(project)
    const files = asArray(workspace.files_touched?.length ? workspace.files_touched : proposal.files_intended).map(safeRel).filter(Boolean)
    const rollbackPatches = []
    const applied = []
    for (const rel of files) {
      const src = path.join(workspace.path, rel)
      const dst = path.join(projectRoot, rel)
      const before = fs.existsSync(dst) ? fs.readFileSync(dst, 'utf8') : ''
      if (!fs.existsSync(src)) continue
      const after = fs.readFileSync(src, 'utf8')
      ensureDir(path.dirname(dst))
      fs.writeFileSync(dst, after, 'utf8')
      applied.push({ path: rel, bytes: Buffer.byteLength(after, 'utf8') })
      rollbackPatches.push(forgeDiff.generateUnifiedDiff(after, before, rel))
    }
    if (body.stage_only && applied.length) {
      forgeWorkspace.runGit(projectRoot, ['add', '--', ...applied.map(item => item.path)], 30000)
    }
    const rollback = this.upsert('rollbackArtifacts', {
      rollback_id: id('v7rollback'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      patch_artifact_id: proposal.artifact_id,
      approval_id: approval.approval_id,
      files_changed: applied.map(item => item.path),
      reverse_patch: redact(rollbackPatches.join('\n')),
      status: applied.length ? 'available' : 'unavailable',
      created_at: nowIso(),
    }, 'rollback_id')
    const change = this.upsert('appliedChanges', {
      apply_id: id('v7apply'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      patch_artifact_id: proposal.artifact_id,
      workspace_id: workspace.workspace_id,
      approval_id: approval.approval_id,
      files_applied: applied,
      stage_only: Boolean(body.stage_only),
      commit_excluded: true,
      push_excluded: true,
      rollback_id: rollback.rollback_id,
      status: applied.length ? 'applied' : 'no_changes',
      created_at: nowIso(),
    }, 'apply_id')
    return { change, rollback }
  }

  writeReportAndMemory(project, goal, proposal, workspace, validation, approval, change, rollback, postValidation) {
    const report = this.upsert('reports', {
      report_id: id('v7report'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      patch_summary: proposal.summary,
      sandbox_workspace_mode: workspace.mode,
      validation_commands_run: asArray(validation?.commands).map(item => ({ id: item.id, status: item.status, command: item.command })),
      quality_gate_result: validation?.status || 'unavailable',
      apply_approval_decision: approval?.status || 'not_requested',
      files_applied: asArray(change?.files_applied).map(item => item.path),
      post_apply_validation_result: postValidation?.status || null,
      rollback_availability: rollback?.status || 'unavailable',
      final_status: postValidation?.status === 'failed' ? 'applied_with_issues' : change?.status || 'prepared',
      created_at: nowIso(),
    }, 'report_id')
    const lesson = this.upsert('memoryLessons', {
      lesson_id: id('v7lesson'),
      project_id: project.id,
      goal_id: goal.goal_id || goal.id,
      summary: `V7 ${report.final_status}: ${proposal.summary}`,
      patch_proposed: proposal.summary,
      validation_caught: asArray(validation?.commands).filter(item => item.status === 'failed').map(item => item.id),
      sandbox_mode: workspace.mode,
      apply_approved: approval?.status === 'approved',
      changed_files: report.files_applied,
      reuse_later: 'Use patch proposal, sandbox validation, apply approval, and rollback artifact before main workspace edits.',
      blocked_or_failed: report.final_status !== 'applied',
      created_at: nowIso(),
    }, 'lesson_id')
    return { report, lesson }
  }
}

module.exports = { ForgeV7ExecutionStore, safeRel, redact }
