/**
 * AscendForge — Agentic Vibecoder
 * Bronze-luxury operator cockpit: TopBar + LeftRail + 8-view router + Footer
 */
import { useCallback, useEffect, useState } from 'react'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './AscendForgePage.css'
import { JPOST, JPOST_JSON, TOKEN, LLM_PROVIDERS, compactId, normalizeAction, isPendingAction, canBatchApprove, mergeActionLists, postFirst } from './forge/helpers'
import { NewProjectModal, AgentBlueprintPanel } from './forge/components'
import {
  ForgeTopBar, ForgeFooter, LeftRail,
  ComposeView, ActivityView, ReviewView, ApprovalsView,
  PipelineView, FilesView, HistoryView, AgentsView,
  ForgeSystemsNav, ForgeSectionView,
} from './forge/shell'

const CLOSED = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

function needsDecision(action) {
  const n = normalizeAction(action)
  return isPendingAction(n) && !CLOSED.has(n.status.toLowerCase())
}

export default function AscendForgePage() {
  // ── State ──────────────────────────────────────────────────────────
  const [project, setProject]             = useState(null)
  const [showNewProj, setShowNewProj]     = useState(false)
  const [selectedFile, setSelectedFile]   = useState(null)
  const [sessionId, setSessionId]         = useState(null)
  const [messages, setMessages]           = useState([])
  const [sending, setSending]             = useState(false)
  const [actions, setActions]             = useState([])
  const [busyActions, setBusyActions]     = useState({})
  const [termLines, setTermLines]         = useState([])
  const [currentDiff, setCurrentDiff]     = useState(null)
  const [provider, setProvider]           = useState('anthropic')
  const [selectedSkillIds, setSelectedSkillIds] = useState([])
  const [activeRun, setActiveRun]         = useState(null)
  const [runBusy, setRunBusy]             = useState(false)
  const [tab, setTab]                     = useState('chat')
  const [fileViewTab, setFileViewTab]     = useState('diff')
  const [editorFile, setEditorFile]       = useState(null)
  const [showBlueprintModal, setShowBlueprintModal] = useState(false)
  const [expandedActions, setExpandedActions] = useState(new Set())
  const [activeView, setActiveView]       = useState('compose')
  const [runState, setRunState]           = useState('idle') // 'idle' | 'running' | 'paused'
  const [showTools, setShowTools]         = useState(false)
  const [draftGoal, setDraftGoal]         = useState('')
  // ── Phase 5 summary state ──────────────────────────────────────────
  const [suggestions, setSuggestions]     = useState([])
  const [backlogCount, setBacklogCount]   = useState(0)
  const [autopilot, setAutopilot]         = useState({ active: false })
  const [metrics, setMetrics]             = useState(null)
  const [activeForgeSection, setActiveForgeSection] = useState(null)

  const projectId = project?.id

  const addTerm = (text, type = 'out') =>
    setTermLines(p => [...p.slice(-200), { text, type, ts: Date.now() }])

  const mergeActions = useCallback(items => {
    setActions(prev => mergeActionLists(prev, items))
  }, [])

  const toggleExpand = useCallback(id => {
    setExpandedActions(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  // ── Session init ───────────────────────────────────────────────────
  useEffect(() => {
    if (!projectId) return
    JPOST('/api/forge/sessions', { project_id: projectId, provider, selected_skill_ids: selectedSkillIds })
      .then(r => r.json())
      .then(d => { setSessionId(d.session_id); setMessages(d.history || []) })
      .catch(e => toastError(`Session error: ${e.message}`))
  }, [projectId, provider, selectedSkillIds])

  // ── Phase 5 summary loader (callable from anywhere) ───────────────
  const refreshForgeSummary = useCallback((pid = projectId) => {
    if (!pid) return
    const H = TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}
    Promise.all([
      fetch(`/api/forge/projects/${pid}/backlog`, { headers: H }).then(r => r.json()).catch(() => ({ backlog: [] })),
      fetch(`/api/forge/projects/${pid}/suggestions`, { headers: H }).then(r => r.json()).catch(() => ({ suggestions: [] })),
      fetch(`/api/forge/projects/${pid}/autopilot/status`, { headers: H }).then(r => r.json()).catch(() => ({ status: { active: false } })),
      fetch(`/api/forge/projects/${pid}/forge-metrics`, { headers: H }).then(r => r.json()).catch(() => null),
    ]).then(([bl, sg, ap, mt]) => {
      setBacklogCount((bl.backlog || []).filter(i => i.status !== 'DONE' && i.status !== 'CANCELLED').length)
      setSuggestions((sg.suggestions || []).filter(s => s.status === 'new'))
      setAutopilot(ap.status || { active: false })
      setMetrics(mt || null)
    })
  }, [projectId])

  useEffect(() => { refreshForgeSummary(projectId) }, [projectId])

  // ── Keyboard navigation (1-8 for views) ───────────────────────────
  useEffect(() => {
    const views = ['compose', 'activity', 'review', 'approvals', 'pipeline', 'files', 'history', 'agents']
    const h = e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      const n = parseInt(e.key)
      if (n >= 1 && n <= 8) setActiveView(views[n - 1])
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [])

  // ── onTemplateSelect — prefill draft goal and switch to chat ──────
  const onTemplateSelect = useCallback((prompt) => {
    setDraftGoal(prompt)
    setTab('chat')
    setActiveView('compose')
  }, [])

  // ── Send message / start run ──────────────────────────────────────
  const sendMessage = useCallback(async (text) => {
    if (sending) return
    setSending(true)
    setRunState('running')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    addTerm(`Sending goal to Forge…`, 'cmd')
    try {
      // Auto-create workspace project if none selected
      let currentProject = project
      let currentSessionId = sessionId
      if (!currentProject) {
        addTerm('No project selected — creating Workspace…', 'out')
        const pd = await JPOST_JSON('/api/forge/projects', { name: 'Workspace', template: 'scratch' })
        if (!pd.project) throw new Error(pd.error || 'Failed to create workspace project')
        currentProject = pd.project
        setProject(currentProject)
        const sd = await JPOST_JSON('/api/forge/sessions', { project_id: currentProject.id, provider, selected_skill_ids: selectedSkillIds })
        currentSessionId = sd.session_id
        setSessionId(currentSessionId)
        setMessages(prev => [...prev.filter(m => m.role !== 'system'), { role: 'system', content: `Project "${currentProject.name}" created` }])
      }
      const body = JSON.stringify({ project_id: currentProject.id, goal: text, provider, selected_skill_ids: selectedSkillIds, max_iterations: 3 })
      const resp = await fetch('/api/forge/runs/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(TOKEN() ? { Authorization: `Bearer ${TOKEN()}` } : {}) },
        body,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }))
        throw new Error(err.error || `HTTP ${resp.status}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = '', runData = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop()
        for (const part of parts) {
          const lines = part.split('\n')
          let event = 'message', data = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) event = line.slice(7).trim()
            else if (line.startsWith('data: ')) data = line.slice(6)
          }
          try {
            const parsed = JSON.parse(data)
            if (event === 'progress') addTerm(parsed.message || parsed.stage, 'out')
            else if (event === 'run') runData = parsed
            else if (event === 'error') throw new Error(parsed.error || 'stream error')
          } catch (parseErr) {
            if (parseErr.message !== 'stream error') continue
            throw parseErr
          }
        }
      }
      if (!runData) throw new Error('No run data received from stream')
      const d = runData
      const run = d.run || { id: d.run_id, status: d.status, context_pack: d.context_pack, plan: d.plan, actions: d.actions }
      setActiveRun(run)
      const runActions = (d.actions || []).map(a => ({ ...a, id: a.id || compactId(), source: 'run', run_id: d.run_id || run.id }))
      mergeActions(runActions)
      const firstDiff = runActions.find(a => a.diff)?.diff || d.patches?.find(p => p.diff)?.diff || null
      if (firstDiff) setCurrentDiff(firstDiff)
      setMessages(prev => [...prev, {
        role: 'assistant', ts: new Date().toISOString(),
        content: `Run ${d.run_id || run.id} created. Forge gathered context, built a supervised plan, and staged ${runActions.length} action(s) for review.`,
        plan: d.plan, actions: runActions, run,
      }])
      addTerm(`Created run ${d.run_id || run.id}`, 'cmd')
      addTerm(`Status: ${run.status || d.status}`, 'out')
      if (runActions.length > 0) setActiveView('approvals')
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
      addTerm(`RUN CREATE FAILED: ${e.message}`, 'err')
      toastError(`Send failed: ${e.message}`)
    } finally {
      setSending(false)
      setRunState(s => s === 'running' ? 'idle' : s)
    }
  }, [sessionId, sending, selectedSkillIds, mergeActions, project, provider])

  // ── Action handlers ────────────────────────────────────────────────
  const approveAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    if (!needsDecision(normalized)) { toastError(`Action is already ${normalized.status}`); return }
    setBusyActions(prev => ({ ...prev, [id]: true }))
    addTerm(`Approving: ${normalized.label}`, 'cmd')
    try {
      if (activeRun?.id && normalized.run_id === activeRun.id) {
        const d = await JPOST_JSON(`/api/forge/runs/${activeRun.id}/approve`, {
          action_id: normalized.id, ownerApproved: true, approval: 'owner-approved', approved_by: 'operator',
        })
        setActiveRun(d.run)
        setActions(prev => prev.map(a => normalizeAction(a).id === id
          ? { ...a, status: d.failures?.length ? 'blocked' : 'staged', policy_decision: d.staged?.[0]?.policy || a.policy_decision }
          : a))
        addTerm(d.ok ? 'Staged in run workspace' : 'Policy blocked staging', d.ok ? 'out' : 'err')
        toastSuccess(`Action staged: ${normalized.label}`)
        return
      }
      const approveTarget = normalized.snapshotId || normalized.id
      const queueFirst = normalized.source === 'queue' || normalized.snapshotId
      const paths = queueFirst
        ? [`/api/forge/approve/${approveTarget}`, `/api/forge/actions/${normalized.id}/approve`]
        : [`/api/forge/actions/${normalized.id}/approve`, `/api/forge/approve/${approveTarget}`]
      const d = await postFirst(paths, { session_id: sessionId, ownerApproved: true, approval: 'owner-approved', approved_by: 'operator' })
      if (d.output) {
        setTermLines(prev => [...prev,
          { text: `[${normalized.type}] ${normalized.label || ''}`, type: 'cmd', ts: Date.now() },
          ...d.output.split('\n').map(l => ({ text: l, type: 'out', ts: Date.now() })),
          { text: d.ok !== false ? '✓ Done' : '✗ Failed', type: d.ok !== false ? 'out' : 'err', ts: Date.now() },
        ])
      }
      if (d.error) addTerm(`ERROR: ${d.error}`, 'err')
      if (d.diff) setCurrentDiff(d.diff)
      const result = d.request || d.action || d
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, ...result, status: result.status || 'approved' } : a))
      toastSuccess(`Action approved: ${normalized.label}`)
    } catch (e) {
      addTerm(`FAILED: ${e.message}`, 'err')
      toastError(`Action failed: ${e.message}`)
    } finally {
      setBusyActions(prev => ({ ...prev, [id]: false }))
    }
  }

  const rejectAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    setBusyActions(prev => ({ ...prev, [id]: true }))
    try {
      const rejectTarget = normalized.snapshotId || normalized.id
      const d = await postFirst([`/api/forge/reject/${rejectTarget}`, `/api/forge/actions/${normalized.id}/reject`],
        { session_id: sessionId, reason: 'Rejected from AscendForge UI' })
      const result = d.request || d.action || d
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, ...result, status: result.status || 'rejected' } : a))
      addTerm(`Rejected: ${normalized.label}`, 'warn')
    } catch {
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, status: 'rejected' } : a))
      addTerm(`Rejected locally: ${normalized.label}`, 'warn')
    } finally {
      setBusyActions(prev => ({ ...prev, [id]: false }))
    }
  }

  const approveSafeBatch = () => {
    const decisionItems = actions.map(normalizeAction).filter(needsDecision)
    const safe = decisionItems.filter(canBatchApprove)
    if (safe.length === 0 || safe.length !== decisionItems.length) {
      toastError('Batch approval is available only for all-low-risk action sets')
      return
    }
    safe.forEach(a => approveAction(a.id))
  }

  const verifyRun = async () => {
    if (!activeRun?.id) return
    setRunBusy(true)
    addTerm(`Verifying staged run ${activeRun.id}`, 'cmd')
    try {
      const d = await JPOST_JSON(`/api/forge/runs/${activeRun.id}/verify`, {
        ownerApproved: true, approval: 'owner-approved', approved_by: 'operator',
      })
      setActiveRun(d.run)
      ;(d.test_result?.results || []).forEach(item =>
        addTerm(`${item.pass ? 'PASS' : 'FAIL'} ${item.command || 'verification'}`, item.pass ? 'out' : 'err'))
      d.ok ? toastSuccess('Run verification passed') : toastError('Run verification failed')
    } catch (e) {
      setActiveRun(prev => prev ? { ...prev, ui_error: e.message } : prev)
      addTerm(`VERIFY FAILED: ${e.message}`, 'err')
      toastError(e.message)
    } finally {
      setRunBusy(false)
    }
  }

  const applyRun = async () => {
    if (!activeRun?.id) return
    setRunBusy(true)
    addTerm(`Applying verified run ${activeRun.id}`, 'cmd')
    try {
      const d = await JPOST_JSON(`/api/forge/runs/${activeRun.id}/apply`, {
        ownerApproved: true, approval: 'owner-approved', approved_by: 'operator',
      })
      setActiveRun(d.run)
      setActions(prev => prev.map(a => a.run_id === activeRun.id ? { ...a, status: 'applied' } : a))
      ;(d.final_report?.applied_files || []).forEach(file => addTerm(`Applied ${file.path}`, 'out'))
      toastSuccess('Verified run applied')
    } catch (e) {
      setActiveRun(prev => prev ? { ...prev, ui_error: e.message } : prev)
      addTerm(`APPLY FAILED: ${e.message}`, 'err')
      toastError(e.message)
    } finally {
      setRunBusy(false)
    }
  }

  const handleProjectCreated = useCallback(result => {
    const next = result.project || result
    setProject(next)
    setShowNewProj(false)
    setTab('chat')
    if (result.plan) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: 'Project scaffold prepared for approval.',
        plan: result.plan, actions: result.actions || [], diff: result.diff || null,
      }])
    }
    if (result.actions?.length) mergeActions(result.actions.map(a => ({ ...a, source: a.source || 'project' })))
    if (result.diff) setCurrentDiff(result.diff)
  }, [mergeActions])

  const pendingCount = actions.filter(a => {
    const s = (a.status || '').toLowerCase()
    return s === 'pending' || s === 'awaiting_approval'
  }).length

  // ── Shared view props ──────────────────────────────────────────────
  const sharedFileProps = {
    project, selectedFile, currentDiff, fileViewTab, setFileViewTab, editorFile,
    onSelectFile: node => { setSelectedFile(node); setEditorFile(node?.path || null) },
  }
  const sharedApprovalProps = {
    actions, busyActions, onApprove: approveAction, onReject: rejectAction,
    onApproveSafeBatch: approveSafeBatch, expandedActions, onToggleExpand: toggleExpand,
    activeRun, onVerify: verifyRun, onApply: applyRun, runBusy,
    onQueueItems: items => mergeActions(items.map(item => ({ ...item, source: 'queue', type: item.type || 'forge_request' }))),
  }

  return (
    <div className="af-page">
      <ForgeTopBar
        project={project}
        provider={provider}
        onProviderChange={setProvider}
        runState={runState}
        onToggleRun={() => setRunState(s => s === 'running' ? 'paused' : s === 'paused' ? 'running' : s)}
        actions={actions}
        suggestions={suggestions}
      />

      <div className="af-body">
        <LeftRail active={activeView} onChange={setActiveView} pendingCount={pendingCount} />

        <main className="af-main">
          <ForgeSystemsNav
            activeSection={activeForgeSection}
            onSection={s => { setActiveForgeSection(s === 'run' ? null : s) }}
            suggestionCount={suggestions.length}
            backlogCount={backlogCount}
          />

          {activeForgeSection && activeForgeSection !== 'run' ? (
            <ForgeSectionView
              section={activeForgeSection}
              project={project}
              activeRun={activeRun}
              onApprove={approveAction}
              onReject={rejectAction}
              onContinue={() => setActiveForgeSection(null)}
              onRefreshSummary={refreshForgeSummary}
            />
          ) : (
            <>
              {activeView === 'compose' && (
                <ComposeView
                  project={project} messages={messages} sending={sending} onSend={sendMessage}
                  selectedSkillIds={selectedSkillIds} onSkillChange={setSelectedSkillIds}
                  tab={tab} setTab={setTab} showTools={showTools} setShowTools={setShowTools}
                  onNewProject={() => setShowNewProj(true)}
                  onSelectProject={p => { setProject(p); setTab('chat') }}
                  draftGoal={draftGoal} setDraftGoal={setDraftGoal}
                  onTemplateSelect={onTemplateSelect}
                  backlogCount={backlogCount} autopilot={autopilot} suggestions={suggestions}
                  onSection={setActiveForgeSection}
                />
              )}
              {activeView === 'activity' && <ActivityView termLines={termLines} activeRun={activeRun} onNavTab={tab => { setActiveView('compose'); setTab(tab) }} />}
              {activeView === 'review' && <ReviewView {...sharedFileProps} />}
              {activeView === 'approvals' && <ApprovalsView {...sharedApprovalProps} />}
              {activeView === 'pipeline' && <PipelineView activeRun={activeRun} actions={actions} />}
              {activeView === 'files' && <FilesView {...sharedFileProps} />}
              {activeView === 'history' && <HistoryView messages={messages} activeRun={activeRun} metrics={metrics} />}
              {activeView === 'agents' && <AgentsView />}
            </>
          )}
        </main>
      </div>

      <ForgeFooter runState={runState} activeRun={activeRun} />


      {showNewProj && (
        <NewProjectModal onClose={() => setShowNewProj(false)} onCreate={handleProjectCreated} />
      )}
      <AgentBlueprintPanel open={showBlueprintModal} onClose={() => setShowBlueprintModal(false)} />
    </div>
  )
}
