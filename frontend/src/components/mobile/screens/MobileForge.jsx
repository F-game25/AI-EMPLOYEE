/* NEXUS OS Mobile — AscendForge Screen */
import { useState, useEffect, useCallback, useRef } from 'react'
import { TopBar, Section, StatusPill, Empty, Spinner, ProgressBar, Row } from '../MobileUI'

const TOKEN = () => localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
const AUTH = () => { const t = TOKEN(); return t ? { Authorization: `Bearer ${t}` } : {} }
const POST = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...AUTH() }, body: JSON.stringify(body) })
const POSTJ = async (url, body) => { const r = await POST(url, body); const d = await r.json(); if (!r.ok) throw new Error(d?.error || `HTTP ${r.status}`); return d }

const CHIPS = [
  { label: 'New feature', prompt: 'Add a new feature: describe the feature here. Include tests.' },
  { label: 'Fix bug', prompt: 'Find and fix the bug causing: describe the issue. Add regression test.' },
  { label: 'Refactor', prompt: 'Refactor: describe the code area. Improve readability without changing behavior.' },
  { label: 'Add API', prompt: 'Create a REST API endpoint for: describe the resource. Include auth and validation.' },
]

const STAGES = ['CONTEXT', 'PLAN', 'BUILD', 'DONE']

const RISK_COLOR = { low: 'var(--success)', safe: 'var(--success)', medium: 'var(--warning)', high: 'var(--error)', dangerous: 'var(--error)', critical: 'var(--error)' }

export default function MobileForge({ onBack }) {
  const [project, setProject] = useState(null)
  const [projects, setProjects] = useState([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [goal, setGoal] = useState('')
  const [step, setStep] = useState('goal') // 'goal' | 'streaming' | 'actions' | 'done'
  const [termLines, setTermLines] = useState([])
  const [stageIdx, setStageIdx] = useState(0)
  const [run, setRun] = useState(null)
  const [actions, setActions] = useState([])
  const [busyIds, setBusyIds] = useState({})
  const [runBusy, setRunBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [expandedActions, setExpandedActions] = useState(new Set())
  const [creatingProject, setCreatingProject] = useState(false)
  const [attachedFile, setAttachedFile] = useState(null)
  const fileRef = useRef(null)
  const logRef = useRef(null)

  const addLine = (text, type = 'out') =>
    setTermLines(p => [...p.slice(-100), { text, type, ts: Date.now() }])

  useEffect(() => {
    fetch('/api/forge/projects', { headers: AUTH() })
      .then(r => r.json())
      .then(d => { setProjects(d.projects || []); if (d.projects?.length) setProject(d.projects[0]) })
      .catch(() => {})
      .finally(() => setLoadingProjects(false))
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [termLines])

  const createWorkspace = useCallback(async () => {
    setCreatingProject(true)
    try {
      const d = await POSTJ('/api/forge/projects', { name: 'Workspace', template: 'scratch' })
      if (d.project) { setProject(d.project); setProjects(p => [d.project, ...p]) }
    } catch (e) { addLine(`Project error: ${e.message}`, 'err') }
    finally { setCreatingProject(false) }
  }, [])

  const sendGoal = useCallback(async () => {
    if (!goal.trim() || step === 'streaming') return
    let currentProject = project
    if (!currentProject) {
      setCreatingProject(true)
      try {
        const pd = await POSTJ('/api/forge/projects', { name: 'Workspace', template: 'scratch' })
        currentProject = pd.project
        setProject(currentProject)
      } catch (e) { addLine(`Could not create project: ${e.message}`, 'err'); setCreatingProject(false); return }
      setCreatingProject(false)
    }

    // init session
    try {
      const sd = await POSTJ('/api/forge/sessions', { project_id: currentProject.id, provider: 'anthropic', selected_skill_ids: [] })
      addLine(`Session: ${sd.session_id?.slice(-8) || 'ok'}`, 'out')
    } catch {}

    setStep('streaming')
    setTermLines([])
    setStageIdx(0)
    setActions([])
    setRun(null)
    setResult(null)
    addLine(`Forging: ${goal}`, 'cmd')

    try {
      const body = { project_id: currentProject.id, goal: goal.trim(), provider: 'anthropic', max_iterations: 3 }
      if (attachedFile) body.context_note = `User attached file: ${attachedFile.name}`
      const resp = await fetch('/api/forge/runs/stream', { method: 'POST', headers: { 'Content-Type': 'application/json', ...AUTH() }, body: JSON.stringify(body) })
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.error || `HTTP ${resp.status}`) }

      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = '', runData = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n'); buf = parts.pop()
        for (const part of parts) {
          let event = 'message', data = ''
          for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) event = line.slice(7).trim()
            else if (line.startsWith('data: ')) data = line.slice(6)
          }
          try {
            const parsed = JSON.parse(data)
            if (event === 'progress') {
              addLine(parsed.message || parsed.stage || '', 'out')
              const si = STAGES.findIndex(s => (parsed.stage || '').toUpperCase().includes(s))
              if (si >= 0) setStageIdx(si)
            } else if (event === 'run') {
              runData = parsed
            } else if (event === 'error') {
              throw new Error(parsed.error || 'stream error')
            }
          } catch (pe) { if (pe.message === 'stream error') throw pe }
        }
      }

      if (!runData) throw new Error('No run data received')
      const r = runData.run || { id: runData.run_id, status: runData.status, actions: runData.actions }
      setRun(r)
      const acts = (runData.actions || []).map(a => ({ ...a, run_id: runData.run_id || r.id }))
      setActions(acts)
      setStageIdx(3)
      addLine(`Run ${r.id?.slice(-8)}: ${acts.length} action(s)`, 'cmd')
      setStep('actions')
    } catch (e) {
      addLine(`FAILED: ${e.message}`, 'err')
      setStep('goal')
    }
  }, [goal, step, project, attachedFile])

  const approveAction = useCallback(async (id) => {
    if (!run?.id || busyIds[id]) return
    setBusyIds(p => ({ ...p, [id]: true }))
    try {
      const d = await POSTJ(`/api/forge/runs/${run.id}/approve`, { action_id: id, ownerApproved: true, approval: 'owner-approved', approved_by: 'operator' })
      setRun(d.run || run)
      setActions(prev => prev.map(a => a.id === id ? { ...a, status: 'staged' } : a))
    } catch (e) {
      setActions(prev => prev.map(a => a.id === id ? { ...a, status: 'error', _err: e.message } : a))
    } finally { setBusyIds(p => ({ ...p, [id]: false })) }
  }, [run, busyIds])

  const rejectAction = useCallback(async (id) => {
    if (!run?.id || busyIds[id]) return
    setBusyIds(p => ({ ...p, [id]: true }))
    try {
      await POST(`/api/forge/actions/${id}/reject`, { reason: 'Rejected from mobile' })
      setActions(prev => prev.map(a => a.id === id ? { ...a, status: 'rejected' } : a))
    } catch {
      setActions(prev => prev.map(a => a.id === id ? { ...a, status: 'rejected' } : a))
    } finally { setBusyIds(p => ({ ...p, [id]: false })) }
  }, [run, busyIds])

  const approveAllSafe = useCallback(() => {
    actions.filter(a => ['low', 'safe'].includes((a.risk || a.risk_level || '').toLowerCase()) && !['staged','applied','rejected'].includes(a.status))
      .forEach(a => approveAction(a.id))
  }, [actions, approveAction])

  const verifyRun = useCallback(async () => {
    if (!run?.id || runBusy) return
    setRunBusy(true)
    try {
      const d = await POSTJ(`/api/forge/runs/${run.id}/verify`, { ownerApproved: true, approval: 'owner-approved', approved_by: 'operator' })
      setRun(d.run || run)
      addLine(d.ok ? 'Verification passed ✓' : 'Verification failed ✗', d.ok ? 'out' : 'err')
    } catch (e) { addLine(`Verify failed: ${e.message}`, 'err') }
    finally { setRunBusy(false) }
  }, [run, runBusy])

  const applyRun = useCallback(async () => {
    if (!run?.id || runBusy) return
    setRunBusy(true)
    try {
      const d = await POSTJ(`/api/forge/runs/${run.id}/apply`, { ownerApproved: true, approval: 'owner-approved', approved_by: 'operator' })
      setRun(d.run || run)
      setResult(d.final_report || { applied_files: [] })
      setStep('done')
    } catch (e) { addLine(`Apply failed: ${e.message}`, 'err') }
    finally { setRunBusy(false) }
  }, [run, runBusy])

  const stagedCount = actions.filter(a => ['staged', 'verified', 'applied'].includes(a.status)).length
  const pendingCount = actions.filter(a => !['staged','verified','applied','rejected','blocked','failed'].includes(a.status)).length
  const canVerify = stagedCount > 0 && !runBusy && run?.status !== 'applied'
  const canApply = run?.status === 'verified' && !runBusy

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (f) setAttachedFile(f)
  }

  // ── DONE step ──
  if (step === 'done') {
    const files = result?.applied_files || []
    return (
      <div style={S.screen}>
        <TopBar title="ASCENDFORGE" subtitle="Build complete" right={<button style={S.backBtn} onClick={onBack}>✕</button>} />
        <div style={S.doneWrap}>
          <div style={S.doneIcon}>✓</div>
          <div style={S.doneTitle}>Applied {files.length} file{files.length !== 1 ? 's' : ''}</div>
          {files.slice(0, 8).map((f, i) => (
            <div key={i} style={S.doneFile}>{typeof f === 'string' ? f : f.path || f.file}</div>
          ))}
          <button style={S.newGoalBtn} onClick={() => { setStep('goal'); setGoal(''); setRun(null); setActions([]); setResult(null); setTermLines([]) }}>
            + New Goal
          </button>
        </div>
      </div>
    )
  }

  // ── STREAMING step ──
  if (step === 'streaming') {
    return (
      <div style={S.screen}>
        <TopBar title="ASCENDFORGE" subtitle="Forging…" right={<button style={S.backBtn} onClick={onBack}>✕</button>} />
        <div style={S.streamWrap}>
          <div style={S.stageRow}>
            {STAGES.map((s, i) => (
              <div key={s} style={S.stageItem}>
                <div style={{ ...S.stageDot, background: i < stageIdx ? 'var(--success)' : i === stageIdx ? 'var(--gold)' : 'var(--border-subtle)', boxShadow: i === stageIdx ? '0 0 8px var(--gold)' : 'none' }} />
                <div style={{ ...S.stageLabel, color: i === stageIdx ? 'var(--gold)' : i < stageIdx ? 'var(--success)' : 'var(--text-dim)' }}>{s}</div>
              </div>
            ))}
          </div>
          <div ref={logRef} style={S.log}>
            {termLines.map((l, i) => (
              <div key={i} style={{ ...S.logLine, color: l.type === 'err' ? 'var(--error)' : l.type === 'cmd' ? 'var(--gold)' : 'var(--text-muted)' }}>
                {l.type === 'cmd' ? '▶ ' : l.type === 'err' ? '✗ ' : '  '}{l.text}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0' }}>
              <Spinner />
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Processing…</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── ACTIONS step ──
  if (step === 'actions') {
    return (
      <div style={S.screen}>
        <TopBar
          title="ASCENDFORGE"
          subtitle={`Run ${run?.id?.slice(-8) || '—'}`}
          right={<button style={S.backBtn} onClick={onBack}>✕</button>}
        />
        <div style={S.scroll}>
          {/* Run status bar */}
          <div style={S.runBar}>
            <span style={S.runStatus}>{(run?.status || 'pending').toUpperCase()}</span>
            <span style={S.runMeta}>{stagedCount}/{actions.length} staged</span>
            {pendingCount > 0 && (
              <button style={S.batchBtn} onClick={approveAllSafe}>APPROVE SAFE</button>
            )}
          </div>

          {/* Action cards */}
          <Section label={`ACTIONS (${actions.length})`}>
            {actions.map(action => {
              const risk = (action.risk || action.risk_level || 'low').toLowerCase()
              const riskColor = RISK_COLOR[risk] || 'var(--text-muted)'
              const isExpanded = expandedActions.has(action.id)
              const isBusy = busyIds[action.id]
              const isPending = !['staged','verified','applied','rejected','blocked','failed'].includes(action.status)
              return (
                <div key={action.id} style={S.actionCard}>
                  <button style={S.actionHead} onClick={() => setExpandedActions(p => { const n = new Set(p); n.has(action.id) ? n.delete(action.id) : n.add(action.id); return n })}>
                    <span style={{ ...S.actionType, background: `${riskColor}18`, color: riskColor, border: `1px solid ${riskColor}44` }}>
                      {(action.type || 'FILE').replace(/_/g, ' ').toUpperCase().slice(0, 12)}
                    </span>
                    <span style={S.actionLabel}>{action.label || action.target || action.id?.slice(-8)}</span>
                    <span style={{ ...S.riskBadge, color: riskColor }}>{risk.toUpperCase()}</span>
                    <span style={S.expandChevron}>{isExpanded ? '▾' : '▸'}</span>
                  </button>

                  {isExpanded && (
                    <div style={S.actionBody}>
                      {action.target && <div style={S.actionDetail}><span style={S.detailLbl}>FILE</span><span style={S.detailVal}>{action.target}</span></div>}
                      {action.description && <div style={S.actionDesc}>{action.description}</div>}
                      {action.diff && (
                        <pre style={S.diffPreview}>
                          {action.diff.split('\n').slice(0, 6).join('\n')}{action.diff.split('\n').length > 6 ? '\n…' : ''}
                        </pre>
                      )}
                      <div style={S.actionDetail}><span style={S.detailLbl}>STATUS</span><span style={{ ...S.detailVal, color: action.status === 'staged' ? 'var(--success)' : action.status === 'rejected' ? 'var(--error)' : 'var(--text-muted)' }}>{action.status?.toUpperCase()}</span></div>
                    </div>
                  )}

                  {isPending && (
                    <div style={S.actionBtns}>
                      <button style={{ ...S.approveBtn, opacity: isBusy ? 0.5 : 1 }} disabled={isBusy} onClick={() => approveAction(action.id)}>
                        {isBusy ? '…' : '✓ APPROVE'}
                      </button>
                      <button style={{ ...S.rejectBtn, opacity: isBusy ? 0.5 : 1 }} disabled={isBusy} onClick={() => rejectAction(action.id)}>
                        ✗
                      </button>
                    </div>
                  )}
                  {action.status === 'staged' && <div style={S.stagedBadge}>✓ STAGED</div>}
                  {action.status === 'rejected' && <div style={S.rejectedBadge}>✗ REJECTED</div>}
                </div>
              )
            })}
          </Section>

          {/* Verify / Apply */}
          <div style={S.actionFooter}>
            <button style={{ ...S.verifyBtn, opacity: canVerify ? 1 : 0.35 }} disabled={!canVerify} onClick={verifyRun}>
              {runBusy ? '⟳ Working…' : '◎ VERIFY'}
            </button>
            <button style={{ ...S.applyBtn, opacity: canApply ? 1 : 0.35 }} disabled={!canApply} onClick={applyRun}>
              {runBusy ? '⟳ Applying…' : '▶ APPLY'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── GOAL step (default) ──
  return (
    <div style={S.screen}>
      <TopBar title="ASCENDFORGE" subtitle="Agentic builder" right={<button style={S.backBtn} onClick={onBack}>✕</button>} />
      <div style={S.scroll}>
        {/* Project picker */}
        <Section label="PROJECT">
          {loadingProjects ? <Spinner /> : (
            <div style={S.projectRow}>
              {project ? (
                <div style={S.projectChip}>
                  <span style={S.projectIcon}>◈</span>
                  <span style={S.projectName}>{project.name}</span>
                </div>
              ) : (
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>No project — will create Workspace automatically</span>
              )}
              {projects.length > 1 && (
                <select style={S.projectSelect} value={project?.id || ''} onChange={e => setProject(projects.find(p => p.id === e.target.value) || null)}>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              )}
              {!project && (
                <button style={S.createProjBtn} onClick={createWorkspace} disabled={creatingProject}>
                  {creatingProject ? '…' : '+ Workspace'}
                </button>
              )}
            </div>
          )}
        </Section>

        {/* Quick chips */}
        <Section label="QUICK START">
          <div style={S.chips}>
            {CHIPS.map(c => (
              <button key={c.label} style={S.chip} onClick={() => setGoal(c.prompt)}>{c.label}</button>
            ))}
          </div>
        </Section>

        {/* Goal input */}
        <Section label="GOAL">
          <div style={S.goalWrap}>
            <textarea
              style={S.goalInput}
              value={goal}
              onChange={e => setGoal(e.target.value)}
              placeholder="Describe what to build…"
              rows={5}
            />
            {/* File attach */}
            <div style={S.attachRow}>
              <button style={S.attachBtn} onClick={() => fileRef.current?.click()}>📎 Attach</button>
              <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={handleFile} />
              {attachedFile && <span style={S.attachName}>{attachedFile.name}</span>}
              {attachedFile && <button style={S.removeAttach} onClick={() => setAttachedFile(null)}>✕</button>}
            </div>
          </div>
        </Section>
      </div>

      <div style={S.footer}>
        <button
          style={{ ...S.forgeBtn, opacity: goal.trim() ? 1 : 0.4 }}
          disabled={!goal.trim() || step === 'streaming' || creatingProject}
          onClick={sendGoal}
        >
          ▶ FORGE
        </button>
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 80 },
  backBtn: { background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 16, cursor: 'pointer', padding: '4px 8px' },
  footer: { padding: '12px 16px', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-deep)' },
  forgeBtn: { width: '100%', padding: '14px', borderRadius: 10, background: 'linear-gradient(135deg, var(--gold), #b8960a)', color: '#0a0800', fontSize: 15, fontWeight: 800, letterSpacing: '0.1em', border: 'none', cursor: 'pointer' },

  // Project
  projectRow: { padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  projectChip: { display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', background: 'rgba(229,199,107,0.08)', border: '1px solid var(--border-gold)', borderRadius: 20 },
  projectIcon: { color: 'var(--gold)', fontSize: 12 },
  projectName: { fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' },
  projectSelect: { flex: 1, padding: '5px 8px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 6, color: 'var(--text-primary)', fontSize: 12 },
  createProjBtn: { padding: '6px 12px', background: 'rgba(229,199,107,0.1)', border: '1px solid var(--border-gold)', borderRadius: 6, color: 'var(--gold)', fontSize: 11, fontWeight: 600, cursor: 'pointer' },

  // Chips
  chips: { display: 'flex', flexWrap: 'wrap', gap: 8, padding: '4px 16px' },
  chip: { padding: '6px 12px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 20, color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer' },

  // Goal
  goalWrap: { padding: '0 16px' },
  goalInput: { width: '100%', padding: '12px', background: 'var(--bg-card)', border: '1px solid var(--border-gold)', borderRadius: 10, color: 'var(--text-primary)', fontSize: 13, resize: 'none', outline: 'none', boxSizing: 'border-box' },
  attachRow: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 },
  attachBtn: { padding: '6px 10px', background: 'none', border: '1px solid var(--border-subtle)', borderRadius: 6, color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer' },
  attachName: { fontSize: 10, color: 'var(--gold)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  removeAttach: { background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 },

  // Streaming
  streamWrap: { flex: 1, display: 'flex', flexDirection: 'column', padding: '16px' },
  stageRow: { display: 'flex', justifyContent: 'space-between', marginBottom: 20 },
  stageItem: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flex: 1 },
  stageDot: { width: 10, height: 10, borderRadius: '50%', transition: 'all 300ms' },
  stageLabel: { fontSize: 8, letterSpacing: '0.1em', textTransform: 'uppercase', transition: 'color 300ms' },
  log: { flex: 1, overflowY: 'auto', background: 'var(--bg-card)', borderRadius: 10, padding: '12px', fontFamily: 'monospace' },
  logLine: { fontSize: 11, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all' },

  // Actions
  runBar: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', background: 'rgba(229,199,107,0.04)', borderBottom: '1px solid var(--border-subtle)' },
  runStatus: { fontSize: 10, fontWeight: 700, color: 'var(--gold)', letterSpacing: '0.1em' },
  runMeta: { fontSize: 10, color: 'var(--text-muted)', flex: 1 },
  batchBtn: { padding: '5px 10px', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 6, color: 'var(--success)', fontSize: 10, fontWeight: 700, cursor: 'pointer' },

  actionCard: { margin: '0 16px 8px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, overflow: 'hidden' },
  actionHead: { display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '10px 12px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' },
  actionType: { fontSize: 8, fontWeight: 700, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0 },
  actionLabel: { flex: 1, fontSize: 11, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  riskBadge: { fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', flexShrink: 0 },
  expandChevron: { fontSize: 10, color: 'var(--text-dim)', flexShrink: 0 },
  actionBody: { padding: '0 12px 10px', display: 'flex', flexDirection: 'column', gap: 6, borderTop: '1px solid var(--border-subtle)' },
  actionDetail: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 6 },
  detailLbl: { fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-dim)', textTransform: 'uppercase' },
  detailVal: { fontSize: 10, color: 'var(--text-muted)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  actionDesc: { fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 },
  diffPreview: { background: 'rgba(0,0,0,0.3)', borderRadius: 6, padding: '6px 8px', fontSize: 10, color: 'var(--text-dim)', margin: 0, overflowX: 'auto', whiteSpace: 'pre', maxHeight: 80 },
  actionBtns: { display: 'flex', gap: 8, padding: '8px 12px', borderTop: '1px solid var(--border-subtle)' },
  approveBtn: { flex: 1, padding: '8px', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 6, color: 'var(--success)', fontSize: 11, fontWeight: 700, cursor: 'pointer' },
  rejectBtn: { padding: '8px 14px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 6, color: 'var(--error)', fontSize: 11, fontWeight: 700, cursor: 'pointer' },
  stagedBadge: { padding: '6px 12px', fontSize: 10, color: 'var(--success)', fontWeight: 700, letterSpacing: '0.08em', background: 'rgba(34,197,94,0.06)' },
  rejectedBadge: { padding: '6px 12px', fontSize: 10, color: 'var(--error)', fontWeight: 700, letterSpacing: '0.08em', background: 'rgba(239,68,68,0.06)' },

  actionFooter: { display: 'flex', gap: 10, padding: '12px 16px', position: 'sticky', bottom: 0, background: 'var(--bg-deep)', borderTop: '1px solid var(--border-subtle)' },
  verifyBtn: { flex: 1, padding: '12px', background: 'rgba(229,199,107,0.08)', border: '1px solid var(--border-gold)', borderRadius: 8, color: 'var(--gold)', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  applyBtn: { flex: 1, padding: '12px', background: 'linear-gradient(135deg, var(--success), #16a34a)', border: 'none', borderRadius: 8, color: '#fff', fontSize: 12, fontWeight: 800, cursor: 'pointer' },

  // Done
  doneWrap: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', gap: 12 },
  doneIcon: { fontSize: 40, color: 'var(--success)', filter: 'drop-shadow(0 0 16px var(--success))' },
  doneTitle: { fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' },
  doneFile: { fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', background: 'var(--bg-card)', padding: '3px 8px', borderRadius: 4 },
  newGoalBtn: { marginTop: 16, padding: '12px 24px', background: 'linear-gradient(135deg, var(--gold), #b8960a)', color: '#0a0800', fontSize: 13, fontWeight: 800, border: 'none', borderRadius: 10, cursor: 'pointer' },
}
