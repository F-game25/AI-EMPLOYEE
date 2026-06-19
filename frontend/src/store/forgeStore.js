import { create } from 'zustand'
import api from '../api/client'

const POLL_MS = 10000
const STALE_MS = 12000

let _pollTimer = null
let _refreshTimer = null

function idOf(item) {
  return item?.id || item?.run_id || item?.action_id || item?.item_id || item?.lesson_id || item?.cycle_id || item?.goal_id || item?.quality_gate_id || item?.publish_id || item?.artifact_id || item?.workspace_id || item?.validation_id || item?.approval_id || item?.apply_id || item?.rollback_id || item?.report_id || null
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function upsertById(list, item) {
  const id = idOf(item)
  if (!id) return list || []
  return [item, ...asArray(list).filter(existing => idOf(existing) !== id)]
}

function activeQueueItems(actions) {
  return asArray(actions).filter(action => ['proposed', 'pending', 'approved'].includes(String(action?.status || '').toLowerCase()))
}

function mergeV7(state, patch = {}) {
  return {
    ...state.v7,
    ...patch,
    patchProposals: patch.patchProposals || state.v7.patchProposals,
    workspaces: patch.workspaces || state.v7.workspaces,
    sandboxRuns: patch.sandboxRuns || state.v7.sandboxRuns,
    applyApprovals: patch.applyApprovals || state.v7.applyApprovals,
    appliedChanges: patch.appliedChanges || state.v7.appliedChanges,
    rollbackArtifacts: patch.rollbackArtifacts || state.v7.rollbackArtifacts,
    reports: patch.reports || state.v7.reports,
    memoryLessons: patch.memoryLessons || state.v7.memoryLessons,
  }
}

function normalizeSnapshot(input) {
  const snapshot = input?.snapshot || input || {}
  const activeRun = snapshot.active_run || null
  const activeProject = snapshot.active_project || null
  const runs = asArray(snapshot.runs)
  const actions = asArray(snapshot.actions)
  const queueItems = activeQueueItems(actions)
  const reports = asArray(snapshot.reports)
  const pendingApprovals = asArray(snapshot.pending_approvals)
  const memoryLessons = asArray(snapshot.memory_lessons)
  const relationships = asArray(snapshot.relationships)
  return {
    runtime: snapshot,
    projects: asArray(snapshot.projects),
    activeProject,
    activeTask: snapshot.active_task || null,
    activeRun,
    activeCycle: snapshot.active_cycle || null,
    runs,
    actions,
    queue: { items: queueItems, total: queueItems.length, phase: 'ready' },
    pendingApprovals,
    validation: snapshot.validation || null,
    artifacts: asArray(snapshot.artifacts),
    reports,
    memoryLessons,
    diagnostics: snapshot.diagnostics || null,
    agentEngine: snapshot.agent_engine || snapshot.diagnostics?.agent_engine || null,
    metrics: snapshot.metrics || {},
    relationships,
    health: snapshot.health || {},
    unsupportedActions: snapshot.unsupported_actions || {},
    selectedProjectId: snapshot.selected_project_id || activeProject?.id || null,
    selectedRunId: snapshot.selected_run_id || activeRun?.run_id || activeRun?.id || null,
    objectMaps: {
      projects: Object.fromEntries(asArray(snapshot.projects).map(item => [idOf(item), item]).filter(([id]) => id)),
      runs: Object.fromEntries(runs.map(item => [idOf(item), item]).filter(([id]) => id)),
      actions: Object.fromEntries(actions.map(item => [idOf(item), item]).filter(([id]) => id)),
      reports: Object.fromEntries(reports.map(item => [idOf(item), item]).filter(([id]) => id)),
      memoryLessons: Object.fromEntries(memoryLessons.map(item => [idOf(item), item]).filter(([id]) => id)),
    },
  }
}

function scheduleRefresh(get, reason = 'event') {
  if (_refreshTimer) return
  _refreshTimer = setTimeout(() => {
    _refreshTimer = null
    get().refresh({ reason, silent: true }).catch(() => {})
  }, 500)
}

export const useForgeStore = create((set, get) => ({
  runtime: null,
  projects: [],
  activeProject: null,
  activeTask: null,
  activeRun: null,
  activeCycle: null,
  runs: [],
  actions: [],
  queue: { items: [], total: 0, phase: 'idle' },
  pendingApprovals: [],
  validation: null,
  artifacts: [],
  reports: [],
  memoryLessons: [],
  diagnostics: null,
  agentEngine: null,
  metrics: {},
  relationships: [],
  health: {},
  unsupportedActions: {},
  v5: {
    brief: null,
    researchPack: null,
    goals: [],
    reasoning: null,
    qualityGates: {},
    report: null,
    phase: 'idle',
  },
  v5Brief: null,
  v5ResearchPack: null,
  v5Goals: [],
  v5Report: null,
	  github: {
	    status: null,
	    draft: null,
	    result: null,
	    phase: 'idle',
	    error: null,
	  },
	  v7: {
	    patchProposals: [],
	    workspaces: [],
	    sandboxRuns: [],
	    applyApprovals: [],
	    appliedChanges: [],
	    rollbackArtifacts: [],
	    reports: [],
	    memoryLessons: [],
	    executionMode: 1,
	    postApplyValidation: null,
	    phase: 'idle',
	    error: null,
	  },
	  objectMaps: { projects: {}, runs: {}, actions: {}, reports: {}, memoryLessons: {} },
  selectedProjectId: null,
  selectedRunId: null,
  loading: false,
  error: null,
  actionBusy: {},
  lastHydratedAt: 0,
  lastEventAt: 0,
  lastEventType: null,
  polling: false,

  hydrate: (payload, meta = {}) => {
    const normalized = normalizeSnapshot(payload)
    set({
      ...normalized,
      loading: false,
      error: null,
      lastHydratedAt: Date.now(),
      lastEventAt: meta.event ? Date.now() : get().lastEventAt,
      lastEventType: meta.event || get().lastEventType,
    })
  },

  refresh: async (opts = {}) => {
    if (!opts.silent) set({ loading: true, error: null })
    try {
      const params = new URLSearchParams()
      const projectId = opts.project_id || get().selectedProjectId
      const runId = opts.run_id || get().selectedRunId
      if (projectId) params.set('project_id', projectId)
      if (runId) params.set('run_id', runId)
      const suffix = params.toString() ? `?${params.toString()}` : ''
      const data = await api.forge.runtime(suffix)
      get().hydrate(data, { event: opts.reason || null })
      return data
    } catch (err) {
      set({ loading: false, error: err?.message || 'Forge runtime unavailable' })
      throw err
    }
  },

  selectProject: (projectId) => {
    set({ selectedProjectId: projectId || null })
    return get().refresh({ project_id: projectId, silent: true, reason: 'select_project' }).catch(() => {})
  },

  selectRun: (runId) => {
    set({ selectedRunId: runId || null })
    return get().refresh({ run_id: runId, silent: true, reason: 'select_run' }).catch(() => {})
  },

	  setActionBusy: (key, value) => set(state => ({
    actionBusy: value
      ? { ...state.actionBusy, [key]: true }
      : Object.fromEntries(Object.entries(state.actionBusy).filter(([k]) => k !== key)),
	  })),

	  refreshQueue: async () => {
	    set(state => ({ queue: { ...state.queue, phase: 'loading' } }))
	    const data = await api.forge.queue()
	    const items = asArray(data.items)
	    set({ queue: { items, total: data.total ?? items.length, phase: 'ready' } })
	    return data
	  },

	  submitQueueItem: async (body) => {
	    const data = await api.forge.submit(body)
	    const item = data.item || data.action
	    if (item) {
	      set(state => ({ queue: { ...state.queue, items: upsertById(state.queue.items, item), total: upsertById(state.queue.items, item).length, phase: 'ready' } }))
	    }
	    return data
	  },

	  approveQueueItem: async (id, body = {}) => {
	    const data = await api.forge.approve(id, body)
	    const item = data.item || data.action
	    if (item) set(state => ({ queue: { ...state.queue, items: upsertById(state.queue.items, item), total: upsertById(state.queue.items, item).length, phase: 'ready' } }))
	    return data
	  },

	  rejectQueueItem: async (id, body = {}) => {
	    const data = await api.forge.reject(id, body)
	    const item = data.item || data.action
	    if (item) {
	      set(state => {
	        const next = asArray(state.queue.items).filter(existing => idOf(existing) !== idOf(item))
	        return { queue: { ...state.queue, items: next, total: next.length, phase: 'ready' } }
	      })
	    }
	    return data
	  },

	  refreshGithubStatus: async (projectId) => {
	    if (!projectId) return null
	    set(state => ({ github: { ...state.github, phase: 'loading', error: null } }))
	    try {
	      const status = await api.forge.github.status(projectId)
	      set(state => ({ github: { ...state.github, status, phase: 'ready', error: null } }))
	      return status
	    } catch (err) {
	      set(state => ({ github: { ...state.github, phase: 'failed', error: err?.message || 'GitHub status unavailable' } }))
	      throw err
	    }
	  },

	  prepareGithubPublish: async (projectId, body = {}) => {
	    const data = await api.forge.github.prepare(projectId, body)
	    set(state => ({ github: { ...state.github, status: data.status || state.github.status, draft: data.draft || null, phase: 'prepared', error: null } }))
	    return data
	  },

		  publishGithubDraft: async (projectId, body = {}) => {
		    set(state => ({ github: { ...state.github, phase: 'publishing', error: null } }))
		    try {
		      const result = await api.forge.github.publish(projectId, body)
		      set(state => ({ github: { ...state.github, result, phase: result.state || 'published', error: null } }))
		      return result
		    } catch (err) {
		      set(state => ({ github: { ...state.github, phase: 'failed', error: err?.message || 'GitHub publish failed' } }))
		      throw err
		    }
		  },

	  setV7ExecutionMode: (level) => set(state => ({ v7: mergeV7(state, { executionMode: Number(level) || 0 }) })),

	  refreshV7ExecutionState: async (projectId) => {
	    if (!projectId) return null
	    set(state => ({ v7: mergeV7(state, { phase: 'loading', error: null }) }))
	    try {
	      const data = await api.forge.v7.getExecutionState(projectId)
	      const next = data.v7 || {}
	      set(state => ({
	        v7: mergeV7(state, {
	          patchProposals: asArray(next.patchProposals),
	          workspaces: asArray(next.workspaces),
	          sandboxRuns: asArray(next.validationRuns),
	          applyApprovals: asArray(next.applyApprovals),
	          appliedChanges: asArray(next.appliedChanges),
	          rollbackArtifacts: asArray(next.rollbackArtifacts),
	          reports: asArray(next.reports),
	          memoryLessons: asArray(next.memoryLessons),
	          phase: 'ready',
	          error: null,
	        }),
	      }))
	      return data
	    } catch (err) {
	      set(state => ({ v7: mergeV7(state, { phase: 'failed', error: err?.message || 'V7 execution state unavailable' }) }))
	      throw err
	    }
	  },

	  v7ProposePatch: async (projectId, goalId, body) => {
	    const data = await api.forge.v7.proposePatch(projectId, goalId, { ...body, autonomy_level: get().v7.executionMode })
	    if (data.patch_proposal) set(state => ({ v7: mergeV7(state, { patchProposals: upsertById(state.v7.patchProposals, data.patch_proposal), phase: 'proposed', error: null }) }))
	    return data
	  },

	  v7CreateSandbox: async (projectId, goalId, body = {}) => {
	    const data = await api.forge.v7.createSandbox(projectId, goalId, { ...body, autonomy_level: get().v7.executionMode })
	    if (data.workspace) set(state => ({ v7: mergeV7(state, { workspaces: upsertById(state.v7.workspaces, data.workspace), phase: 'sandbox', error: null }) }))
	    return data
	  },

	  v7ApplyPatchSandbox: async (workspaceId, body = {}) => {
	    const data = await api.forge.v7.applyPatchSandbox(workspaceId, { ...body, autonomy_level: get().v7.executionMode })
	    if (data.workspace) set(state => ({ v7: mergeV7(state, { workspaces: upsertById(state.v7.workspaces, data.workspace), phase: 'sandbox_applied', error: null }) }))
	    return data
	  },

	  v7ValidateWorkspace: async (workspaceId, body = {}) => {
	    const data = await api.forge.v7.validateWorkspace(workspaceId, body)
	    if (data.validation) set(state => ({ v7: mergeV7(state, { sandboxRuns: upsertById(state.v7.sandboxRuns, data.validation), phase: 'validated', error: null }) }))
	    return data
	  },

	  v7RequestApply: async (projectId, goalId, body = {}) => {
	    const data = await api.forge.v7.requestApply(projectId, goalId, { ...body, autonomy_level: get().v7.executionMode })
	    if (data.approval) set(state => ({ v7: mergeV7(state, { applyApprovals: upsertById(state.v7.applyApprovals, data.approval), phase: 'approval_requested', error: null }) }))
	    return data
	  },

	  v7ApproveApply: async (approvalId, body = {}) => {
	    const data = await api.forge.v7.approveApply(approvalId, body)
	    if (data.approval) set(state => ({ v7: mergeV7(state, { applyApprovals: upsertById(state.v7.applyApprovals, data.approval), phase: 'approved', error: null }) }))
	    return data
	  },

	  v7RejectApply: async (approvalId, body = {}) => {
	    const data = await api.forge.v7.rejectApply(approvalId, body)
	    if (data.approval) set(state => ({ v7: mergeV7(state, { applyApprovals: upsertById(state.v7.applyApprovals, data.approval), phase: 'rejected', error: null }) }))
	    return data
	  },

	  v7ApplyToWorkspace: async (projectId, goalId, body = {}) => {
	    const data = await api.forge.v7.applyToWorkspace(projectId, goalId, { ...body, autonomy_level: get().v7.executionMode })
	    set(state => ({
	      v7: mergeV7(state, {
	        appliedChanges: data.change ? upsertById(state.v7.appliedChanges, data.change) : state.v7.appliedChanges,
	        rollbackArtifacts: data.rollback ? upsertById(state.v7.rollbackArtifacts, data.rollback) : state.v7.rollbackArtifacts,
	        phase: 'applied',
	        error: null,
	      }),
	    }))
	    return data
	  },

	  v7PostValidate: async (projectId, goalId, body = {}) => {
	    const data = await api.forge.v7.postValidate(projectId, goalId, body)
	    set(state => ({
	      v7: mergeV7(state, {
	        sandboxRuns: data.validation ? upsertById(state.v7.sandboxRuns, data.validation) : state.v7.sandboxRuns,
	        reports: data.report ? upsertById(state.v7.reports, data.report) : state.v7.reports,
	        memoryLessons: data.lesson ? upsertById(state.v7.memoryLessons, data.lesson) : state.v7.memoryLessons,
	        postApplyValidation: data.validation || state.v7.postApplyValidation,
	        phase: 'post_validated',
	        error: null,
	      }),
	    }))
	    return data
	  },

	  v7Rollback: async (projectId, goalId, body = {}) => {
	    const data = await api.forge.v7.rollback(projectId, goalId, body)
	    if (data.rollback) set(state => ({ v7: mergeV7(state, { rollbackArtifacts: upsertById(state.v7.rollbackArtifacts, data.rollback), phase: 'rollback_applied', error: null }) }))
	    return data
	  },

		  applyForgeEvent: (event, data = {}) => {
    const payload = data || {}
    set(state => {
      const base = { lastEventAt: Date.now(), lastEventType: event }

      if (event === 'forge:runtime_snapshot') {
        return { ...base, ...normalizeSnapshot(payload.snapshot || payload) }
      }

      if (event === 'forge:run_created' || event === 'forge:run_updated') {
        const run = payload.run
        if (!run) return base
        return {
          ...base,
          activeRun: run,
          selectedRunId: run.run_id || run.id || state.selectedRunId,
          runs: upsertById(state.runs, run),
          objectMaps: {
            ...state.objectMaps,
            runs: { ...state.objectMaps.runs, [run.run_id || run.id]: run },
          },
        }
      }

	      if (event === 'forge:action_updated') {
	        const action = payload.action
	        if (!action) return base
	        const nextActions = upsertById(state.actions, action)
	        const nextQueue = activeQueueItems(nextActions)
	        return {
	          ...base,
	          actions: nextActions,
	          queue: { ...state.queue, items: nextQueue, total: nextQueue.length, phase: 'ready' },
	          objectMaps: {
            ...state.objectMaps,
            actions: { ...state.objectMaps.actions, [action.id || action.action_id]: action },
          },
	        }
	      }

	      if (event === 'forge:queue_update') {
	        const items = Array.isArray(payload.items)
	          ? payload.items
	          : payload.item
	            ? upsertById(state.queue.items, payload.item)
	            : state.queue.items
	        const activeItems = activeQueueItems(items)
	        return {
	          ...base,
	          queue: { items: activeItems, total: activeItems.length, phase: 'ready' },
	          ...(payload.item ? { actions: upsertById(state.actions, payload.item) } : {}),
	        }
	      }

      if (event === 'forge:approval_required') {
        const next = [...asArray(payload.pending_approvals), ...state.pendingApprovals]
        return { ...base, pendingApprovals: next.slice(0, 100) }
      }

      if (event === 'forge:approval_decided') {
        const actionId = payload.action_id || payload.id
        return {
          ...base,
          pendingApprovals: state.pendingApprovals.map(item => (item.action_id === actionId || item.id === actionId)
            ? { ...item, status: payload.status || 'decided' }
            : item),
        }
      }

      if (event === 'forge:validation_started' || event === 'forge:validation_completed') {
        return {
          ...base,
          validation: {
            ...(state.validation || {}),
            run_id: payload.run_id || state.validation?.run_id,
            status: event === 'forge:validation_started' ? 'running' : (payload.all_passed ? 'passed' : 'failed'),
            latest: payload.test_result || state.validation?.latest || null,
            results: payload.results || payload.test_result?.results || state.validation?.results || [],
          },
        }
      }

      if (event === 'forge:report_generated') {
        const report = payload.report ? {
          id: `report-${payload.run_id || Date.now()}`,
          type: 'report',
          run_id: payload.run_id,
          project_id: payload.project_id,
          status: payload.report.status || 'available',
          summary: payload.report.summary || 'Forge report generated',
          report: payload.report,
        } : null
        return report ? { ...base, reports: upsertById(state.reports, report) } : base
      }

      if (event === 'forge:memory_candidate_created') {
        const lesson = payload.distillation || payload.lesson || payload
        return { ...base, memoryLessons: upsertById(state.memoryLessons, lesson) }
      }

      if (event === 'forge:v5_brief_created') {
        return {
          ...base,
          v5Brief: payload.brief || null,
          v5: { ...state.v5, brief: payload.brief || null, phase: 'brief' },
        }
      }

      if (event === 'forge:v5_research_started') {
        return {
          ...base,
          v5: { ...state.v5, phase: 'researching' },
        }
      }

      if (event === 'forge:v5_research_completed') {
        return {
          ...base,
          v5ResearchPack: payload.research_pack || null,
          v5: { ...state.v5, researchPack: payload.research_pack || null, phase: 'researched' },
        }
      }

      if (event === 'forge:v5_goals_generated') {
        return {
          ...base,
          v5Goals: asArray(payload.goals),
          v5: {
            ...state.v5,
            goals: asArray(payload.goals),
            reasoning: payload.reasoning || state.v5.reasoning,
            phase: 'goals',
          },
        }
      }

      if (event === 'forge:v5_goal_started') {
        const goal = payload.goal || { goal_id: payload.goal_id, status: 'in_progress' }
        return {
          ...base,
          v5: {
            ...state.v5,
            goals: upsertById(state.v5.goals, { ...goal, status: 'in_progress' }),
            phase: 'executing',
          },
        }
      }

      if (event === 'forge:v5_goal_completed') {
        const goal = payload.goal
        return {
          ...base,
          ...(goal ? { v5Goals: upsertById(state.v5Goals, goal) } : {}),
          v5: goal ? {
            ...state.v5,
            goals: upsertById(state.v5.goals, goal),
            phase: 'goals',
          } : state.v5,
        }
      }

      if (event === 'forge:v5_quality_gate_completed') {
        const gate = payload.quality_gate
        if (!gate) return base
        return {
          ...base,
          v5: {
            ...state.v5,
            qualityGates: { ...state.v5.qualityGates, [gate.goal_id || payload.goal_id]: gate },
            phase: 'quality',
          },
        }
      }

      if (event === 'forge:v5_report_generated') {
        return {
          ...base,
          v5Report: payload.report || null,
          v5: { ...state.v5, report: payload.report || null, phase: 'reported' },
        }
      }

      if (event === 'forge:v5_memory_written' || event === 'forge:v5_memory_write_failed') {
        const goalId = payload.goal_id
        const writeback = event === 'forge:v5_memory_written'
          ? { ok: true, memory: payload.memory || null }
          : { ok: false, error: payload.error || 'memory_writeback_failed' }
        const patchGoal = g => (g.goal_id === goalId ? { ...g, memory_writeback: writeback } : g)
        return {
          ...base,
          v5Goals: (state.v5Goals || []).map(patchGoal),
          v5: { ...state.v5, goals: (state.v5.goals || []).map(patchGoal) },
        }
      }

      if (event === 'forge:github_publish_prepared') {
        return {
          ...base,
          github: { ...state.github, status: payload.status || state.github.status, draft: payload.draft || null, phase: 'prepared', error: null },
        }
      }

      if (event === 'forge:github_publish_started') {
        return {
          ...base,
          github: { ...state.github, draft: payload.draft || state.github.draft, phase: 'publishing', error: null },
        }
      }

      if (event === 'forge:github_publish_completed') {
        return {
          ...base,
          github: { ...state.github, result: payload.result || null, phase: payload.result?.state || 'published', error: null },
        }
      }

	      if (event === 'forge:github_publish_failed') {
	        return {
	          ...base,
	          github: { ...state.github, result: payload.result || null, phase: 'failed', error: payload.result?.error || 'GitHub publish failed' },
	        }
	      }

	      if (event === 'forge:v7_patch_proposed') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            patchProposals: upsertById(state.v7.patchProposals, payload.patch_proposal),
	            phase: 'proposed',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_sandbox_created' || event === 'forge:v7_patch_applied_to_sandbox') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            workspaces: upsertById(state.v7.workspaces, payload.workspace),
	            phase: event === 'forge:v7_sandbox_created' ? 'sandbox' : 'sandbox_applied',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_sandbox_validation_started') {
	        return { ...base, v7: mergeV7(state, { phase: 'validating', error: null }) }
	      }

	      if (event === 'forge:v7_sandbox_validation_completed') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            sandboxRuns: upsertById(state.v7.sandboxRuns, payload.validation),
	            phase: 'validated',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_apply_approval_requested' || event === 'forge:v7_apply_approved' || event === 'forge:v7_apply_rejected') {
	        const phase = event === 'forge:v7_apply_approval_requested' ? 'approval_requested' : event === 'forge:v7_apply_approved' ? 'approved' : 'rejected'
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            applyApprovals: upsertById(state.v7.applyApprovals, payload.approval),
	            phase,
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_patch_applied_to_workspace') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            appliedChanges: payload.change ? upsertById(state.v7.appliedChanges, payload.change) : state.v7.appliedChanges,
	            rollbackArtifacts: payload.rollback ? upsertById(state.v7.rollbackArtifacts, payload.rollback) : state.v7.rollbackArtifacts,
	            phase: 'applied',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_post_apply_validation_started') {
	        return { ...base, v7: mergeV7(state, { phase: 'post_validating', error: null }) }
	      }

	      if (event === 'forge:v7_post_apply_validation_completed') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            sandboxRuns: payload.validation ? upsertById(state.v7.sandboxRuns, payload.validation) : state.v7.sandboxRuns,
	            reports: payload.report ? upsertById(state.v7.reports, payload.report) : state.v7.reports,
	            memoryLessons: payload.memory_lesson ? upsertById(state.v7.memoryLessons, payload.memory_lesson) : state.v7.memoryLessons,
	            postApplyValidation: payload.validation || state.v7.postApplyValidation,
	            phase: 'post_validated',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_rollback_available' || event === 'forge:v7_rollback_applied') {
	        return {
	          ...base,
	          v7: mergeV7(state, {
	            rollbackArtifacts: upsertById(state.v7.rollbackArtifacts, payload.rollback),
	            phase: event === 'forge:v7_rollback_applied' ? 'rollback_applied' : 'rollback_available',
	            error: null,
	          }),
	        }
	      }

	      if (event === 'forge:v7_execution_blocked') {
	        return { ...base, v7: mergeV7(state, { phase: 'blocked', error: payload.error || payload.stage || 'V7 execution blocked' }) }
	      }

	      if (event === 'forge:diagnostic') {
        return { ...base, diagnostics: { ...(state.diagnostics || {}), last_event: payload, updated_at: Date.now() } }
      }

      return base
    })

    if (
		      event.startsWith('forge:v5_') ||
		      event.startsWith('forge:v7_') ||
	      event.startsWith('forge:github_') ||
	      event === 'forge:queue_update' ||
      event.startsWith('approval:') ||
      event === 'workflow:update' ||
      event === 'memory:added' ||
      event === 'memory:pending_review'
    ) {
      scheduleRefresh(get, event)
    }
  },

  ensurePolling: () => {
    if (_pollTimer) return
    _pollTimer = setInterval(() => {
      const state = get()
      const now = Date.now()
      const stale = !state.lastHydratedAt || now - Math.max(state.lastEventAt || 0, state.lastHydratedAt || 0) > STALE_MS
      if (stale) state.refresh({ silent: true, reason: 'poll_stale' }).catch(() => {})
    }, POLL_MS)
    set({ polling: true })
  },

  stopPolling: () => {
    if (_pollTimer) clearInterval(_pollTimer)
    _pollTimer = null
    set({ polling: false })
  },
}))

export function ensureForgeRuntimePolling() {
  useForgeStore.getState().ensurePolling()
}
