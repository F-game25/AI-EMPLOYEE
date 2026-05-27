/**
 * AscendForge — Agentic Vibecoder
 * 3-pane layout: Project tree + chat | File diff viewer + editor | Action queue + terminal
 * Multi-turn agentic loop with per-action approval gates.
 */
import { useCallback, useEffect, useState } from 'react'
import { SectionLabel, StatusPill } from '../nexus-ui'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './AscendForgePage.css'
import { JPOST, JPOST_JSON, LLM_PROVIDERS, compactId, normalizeAction, isPendingAction, canBatchApprove, mergeActionLists, postFirst } from './forge/helpers'
import { ProjectPicker, NewProjectModal, FileTree, ChatPane, DiffViewer, ActionQueue, Terminal, PolicyPreview, ForgeSystemPanel, AgentBlueprintPanel, FileEditor, UnderstandPane, AgenticPane, RunTimeline } from './forge/components'



/* ─── Main page ────────────────────────────────────────────────────── */

const CLOSED_ACTION_STATUSES = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

function needsOperatorDecision(action) {
  const normalized = normalizeAction(action)
  return isPendingAction(normalized) && !CLOSED_ACTION_STATUSES.has(normalized.status.toLowerCase())
}

export default function AscendForgePage() {
  const [project, setProject]       = useState(null)
  const projectId = project?.id
  const [showNewProj, setShowNewProj] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [sessionId, setSessionId]   = useState(null)
  const [messages, setMessages]     = useState([])
  const [sending, setSending]       = useState(false)
  const [actions, setActions]       = useState([])
  const [busyActions, setBusyActions] = useState({})
  const [termLines, setTermLines]   = useState([])
  const [currentDiff, setCurrentDiff] = useState(null)
  const [provider, setProvider]     = useState('anthropic')
  const [selectedSkillIds, setSelectedSkillIds] = useState([])
  const [activeRun, setActiveRun] = useState(null)
  const [runBusy, setRunBusy] = useState(false)
  const [tab, setTab]               = useState('chat') // 'chat' | 'tree'
  const [fileViewTab, setFileViewTab] = useState('diff') // 'diff' | 'editor'
  const [editorFile, setEditorFile] = useState(null) // file path string for editor

  const addTerm = (text, type = 'out') => setTermLines(p => [...p.slice(-200), { text, type, ts: Date.now() }])
  const mergeActions = useCallback((items) => {
    setActions(prev => mergeActionLists(prev, items))
  }, [])

  // Create/resume forge session when project changes
  useEffect(() => {
    if (!projectId) return
    JPOST('/api/forge/sessions', { project_id: projectId, provider, selected_skill_ids: selectedSkillIds }).then(r => r.json()).then(d => {
      setSessionId(d.session_id)
      setMessages(d.history || [])
    }).catch(e => toastError(`Session error: ${e.message}`))
  }, [projectId, provider, selectedSkillIds])

  const sendMessage = useCallback(async (text) => {
    if (!sessionId || sending) return
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    try {
      const d = await JPOST_JSON('/api/forge/runs', {
        project_id: project.id,
        goal: text,
        provider,
        selected_skill_ids: selectedSkillIds,
        max_iterations: 3,
      })
      const run = d.run || { id: d.run_id, status: d.status, context_pack: d.context_pack, plan: d.plan, actions: d.actions }
      setActiveRun(run)
      const runActions = (d.actions || []).map(a => ({ ...a, id: a.id || compactId(), source: 'run', run_id: d.run_id || run.id }))
      mergeActions(runActions)
      const firstDiff = runActions.find(action => action.diff)?.diff || d.patches?.find(patch => patch.diff)?.diff || null
      if (firstDiff) setCurrentDiff(firstDiff)
      setMessages(prev => [...prev, {
        role: 'assistant',
        ts: new Date().toISOString(),
        content: `Run ${d.run_id || run.id} created. Forge gathered context, built a supervised plan, and staged ${runActions.length} action(s) for review.`,
        plan: d.plan,
        actions: runActions,
        run,
      }])
      addTerm(`Created run ${d.run_id || run.id}`, 'cmd')
      addTerm(`Status: ${run.status || d.status}`, 'out')
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
      addTerm(`RUN CREATE FAILED: ${e.message}`, 'err')
      toastError(`Send failed: ${e.message}`)
    } finally {
      setSending(false)
    }
  }, [sessionId, sending, selectedSkillIds, mergeActions, project, provider])

  const approveAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    if (!needsOperatorDecision(normalized)) {
      toastError(`Action is already ${normalized.status}`)
      return
    }
    setBusyActions(prev => ({ ...prev, [id]: true }))
    addTerm(`Approving: ${normalized.label}`, 'cmd')
    try {
      if (activeRun?.id && normalized.run_id === activeRun.id) {
        const d = await JPOST_JSON(`/api/forge/runs/${activeRun.id}/approve`, {
          action_id: normalized.id,
          ownerApproved: true,
          approval: 'owner-approved',
          approved_by: 'operator',
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
      const d = await postFirst(paths, {
        session_id: sessionId,
        ownerApproved: true,
        approval: 'owner-approved',
        approved_by: 'operator',
      })
      if (d.output) {
        setTermLines(prev => [
          ...prev,
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
      const d = await postFirst([
        `/api/forge/reject/${rejectTarget}`,
        `/api/forge/actions/${normalized.id}/reject`,
      ], { session_id: sessionId, reason: 'Rejected from AscendForge UI' })
      const result = d.request || d.action || d
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, ...result, status: result.status || 'rejected' } : a))
      addTerm(`Rejected: ${normalized.label}`, 'warn')
    } catch (e) {
      setActions(prev => prev.map(a => normalizeAction(a).id === id ? { ...a, status: 'rejected' } : a))
      addTerm(`Rejected locally: ${normalized.label}`, 'warn')
    } finally {
      setBusyActions(prev => ({ ...prev, [id]: false }))
    }
  }

  const approveSafeBatch = () => {
    const decisionItems = actions.map(normalizeAction).filter(needsOperatorDecision)
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
        ownerApproved: true,
        approval: 'owner-approved',
        approved_by: 'operator',
      })
      setActiveRun(d.run)
      const result = d.test_result
      ;(result?.results || []).forEach(item => addTerm(`${item.pass ? 'PASS' : 'FAIL'} ${item.command || 'verification'}`, item.pass ? 'out' : 'err'))
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
        ownerApproved: true,
        approval: 'owner-approved',
        approved_by: 'operator',
      })
      setActiveRun(d.run)
      setActions(prev => prev.map(action => action.run_id === activeRun.id ? { ...action, status: 'applied' } : action))
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

  const handleProjectCreated = useCallback((result) => {
    const nextProject = result.project || result
    setProject(nextProject)
    setShowNewProj(false)
    setTab('chat')
    if (result.plan) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Project scaffold prepared for approval.',
        plan: result.plan,
        actions: result.actions || [],
        diff: result.diff || null,
      }])
    }
    if (result.actions?.length) mergeActions(result.actions.map(a => ({ ...a, source: a.source || 'project' })))
    if (result.diff) setCurrentDiff(result.diff)
  }, [mergeActions])

  return (
    <div className="af-page">
      {/* ─ Header ─────────────────────────────────────────────────── */}
      <div className="af-header">
        <div className="af-header__left">
          <span className="af-header__title">◆ ASCENDFORGE</span>
          <span className="af-header__sub">Agentic Vibecoder</span>
        </div>
        <div className="af-header__controls">
          <select className="af-select" value={provider} onChange={e => setProvider(e.target.value)}>
            {LLM_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.icon} {p.label}</option>)}
          </select>
          {project && <StatusPill tone="success" label={project.name} />}
        </div>
      </div>

      {/* ─ 3-pane layout ──────────────────────────────────────────── */}
      <div className="af-layout">

        {/* Left pane — Project tree / chat */}
        <div className="af-pane af-pane--left">
          <div className="af-pane__tabs">
            <button className={`af-tab ${tab === 'chat' ? 'af-tab--active' : ''}`} onClick={() => setTab('chat')}>Chat</button>
            <button className={`af-tab ${tab === 'tree' ? 'af-tab--active' : ''}`} onClick={() => setTab('tree')}>Files</button>
            <button className={`af-tab ${tab === 'understand' ? 'af-tab--active' : ''}`} onClick={() => setTab('understand')}>Understand</button>
            <button className={`af-tab ${tab === 'autobuild' ? 'af-tab--active' : ''}`} onClick={() => setTab('autobuild')}>Auto-build</button>
            <button className={`af-tab ${tab === 'projects' ? 'af-tab--active' : ''}`} onClick={() => setTab('projects')}>Projects</button>
          </div>

          {tab === 'chat' && (
            <ChatPane
              project={project}
              messages={messages}
              onSend={sendMessage}
              sending={sending}
              selectedSkillIds={selectedSkillIds}
              onSkillChange={setSelectedSkillIds}
            />
          )}
          {tab === 'tree' && (
            <FileTree
              project={project}
              selectedFile={selectedFile}
              onSelect={node => { setSelectedFile(node); setEditorFile(node?.path || null) }}
            />
          )}
          {tab === 'understand' && <UnderstandPane project={project} />}
          {tab === 'autobuild' && <AgenticPane project={project} />}
          {tab === 'projects' && (
            <ProjectPicker
              project={project}
              onSelect={p => { setProject(p); setTab('chat') }}
              onNew={() => setShowNewProj(true)}
            />
          )}
        </div>

        {/* Center pane — Diff viewer + Editor */}
        <div className="af-pane af-pane--center">
          <div className="af-pane__header">
            <SectionLabel>CHANGES</SectionLabel>
            <div className="af-file-view-tabs">
              <button
                className={`af-file-view-tab ${fileViewTab === 'diff' ? 'af-file-view-tab--active' : ''}`}
                onClick={() => setFileViewTab('diff')}
              >DIFF</button>
              <button
                className={`af-file-view-tab ${fileViewTab === 'editor' ? 'af-file-view-tab--active' : ''}`}
                onClick={() => setFileViewTab('editor')}
              >EDITOR</button>
            </div>
          </div>
          {fileViewTab === 'diff'
            ? <DiffViewer diff={currentDiff} />
            : <FileEditor project={project} selectedFile={editorFile} />
          }
        </div>

        {/* Right pane — Action queue + terminal */}
        <div className="af-pane af-pane--right">
          <div className="af-pane__section">
            <div className="af-pane__header">
              <SectionLabel>APPROVAL QUEUE</SectionLabel>
              {actions.length > 0 && <span className="af-badge">{actions.length}</span>}
            </div>
            <ForgeSystemPanel onQueueItems={items => mergeActions(items.map(item => ({ ...item, source: 'queue', type: item.type || 'forge_request' })))} />
            <RunTimeline run={activeRun} onVerify={verifyRun} onApply={applyRun} busy={runBusy} />
            <PolicyPreview actions={actions} />
            <AgentBlueprintPanel />
            <ActionQueue
              actions={actions}
              busyActions={busyActions}
              onApprove={approveAction}
              onReject={rejectAction}
              onApproveSafeBatch={approveSafeBatch}
            />
          </div>
          <div className="af-pane__section af-pane__section--grow">
            <Terminal lines={termLines} />
          </div>
        </div>
      </div>

      {showNewProj && (
        <NewProjectModal
          onClose={() => setShowNewProj(false)}
          onCreate={handleProjectCreated}
        />
      )}
    </div>
  )
}
