/**
 * AscendForge — Agentic Vibecoder
 * 3-pane layout: Project tree + chat | File diff viewer + editor | Action queue + terminal
 * Multi-turn agentic loop with per-action approval gates.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { SectionLabel, StatusPill, EmptyState } from '../nexus-ui'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './AscendForgePage.css'
import { JPOST, LLM_PROVIDERS, compactId, normalizeAction, isPendingAction, canBatchApprove, mergeActionLists, postFirst } from './forge/helpers'
import { MiniField, StructuredList, StructuredMessageBlock, SkillPackSelector, ProjectPicker, NewProjectModal, FileTree, ChatPane, DiffViewer, ActionQueue, Terminal, PolicyPreview, ForgeSystemPanel, AgentBlueprintPanel, FileEditor, UnderstandPane, AgenticPane } from './forge/components'



/* ─── Main page ────────────────────────────────────────────────────── */

export default function AscendForgePage() {
  const [project, setProject]       = useState(null)
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
  const [tab, setTab]               = useState('chat') // 'chat' | 'tree'
  const [fileViewTab, setFileViewTab] = useState('diff') // 'diff' | 'editor'
  const [editorFile, setEditorFile] = useState(null) // file path string for editor

  const addTerm = (text, type = 'out') => setTermLines(p => [...p.slice(-200), { text, type, ts: Date.now() }])
  const mergeActions = useCallback((items) => {
    setActions(prev => mergeActionLists(prev, items))
  }, [])

  // Create/resume forge session when project changes
  useEffect(() => {
    if (!project) return
    JPOST('/api/forge/sessions', { project_id: project.id, provider, selected_skill_ids: selectedSkillIds }).then(r => r.json()).then(d => {
      setSessionId(d.session_id)
      setMessages(d.history || [])
    }).catch(e => toastError(`Session error: ${e.message}`))
  }, [project?.id, provider])

  const sendMessage = useCallback(async (text) => {
    if (!sessionId || sending) return
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setMessages(prev => [...prev, { role: 'assistant', content: '▋', ts: new Date().toISOString(), _streaming: true }])

    let accumulated = ''
    try {
      // streaming: raw fetch intentional (SSE body reader; api client buffers JSON)
      const jwt = sessionStorage.getItem('ai_jwt')
      const resp = await fetch(`/api/forge/sessions/${sessionId}/messages/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}) },
        body: JSON.stringify({ content: text, selected_skill_ids: selectedSkillIds }),
      })
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.text !== undefined) {
              accumulated += ev.text
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: accumulated + '▋' } : m))
            } else if (ev.content !== undefined) {
              // done event — finalise message
              const finalMsg = { role: 'assistant', ts: new Date().toISOString(), content: ev.content, actions: ev.actions || [], _streaming: false }
              setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? finalMsg : m))
              if (ev.actions?.length) {
                mergeActions(ev.actions.map(a => ({ ...a, id: a.id || compactId(), source: a.source || 'session' })))
              }
            } else if (ev.error) {
              toastError(`Forge error: ${ev.error}`)
            }
          } catch { /* malformed SSE line — skip */ }
        }
      }
    } catch (e) {
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, content: `Error: ${e.message}`, _streaming: false } : m))
      toastError(`Send failed: ${e.message}`)
    } finally {
      setSending(false)
    }
  }, [sessionId, sending, selectedSkillIds, mergeActions])

  const approveAction = async (id) => {
    const action = actions.find(a => a.id === id)
    if (!action) return
    const normalized = normalizeAction(action)
    setBusyActions(prev => ({ ...prev, [id]: true }))
    addTerm(`Approving: ${normalized.label}`, 'cmd')
    try {
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
    const safe = actions.map(normalizeAction).filter(canBatchApprove)
    if (safe.length === 0 || safe.length !== actions.filter(isPendingAction).length) {
      toastError('Batch approval is available only for all-low-risk action sets')
      return
    }
    safe.forEach(a => approveAction(a.id))
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
              sessionId={sessionId}
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
