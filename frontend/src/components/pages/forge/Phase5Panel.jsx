import { useState, useEffect, useCallback } from 'react'
import { SectionLabel, EmptyState } from '../../nexus-ui'
import { toastError } from '../../nexus-ui/Toaster'
import api from '../../../api/client'

const STATUS_COLORS = { IDEA:'#6b7280', READY:'#3b82f6', PLANNING:'#8b5cf6', IN_PROGRESS:'#f59e0b', WAITING_APPROVAL:'#ef4444', BLOCKED:'#dc2626', DONE:'#10b981', FAILED:'#ef4444', CANCELLED:'#6b7280' }
const CATEGORY_ICONS = { BUG:'🐛', FEATURE:'✨', REFACTOR:'♻️', SECURITY:'🔒', UI:'🎨', PERFORMANCE:'⚡', TESTING:'🧪', DOCS:'📄', ARCHITECTURE:'🏗️', AUTOMATION:'🤖' }

export function BacklogPane({ project, onRefreshSummary }) {
  const [backlog, setBacklog] = useState([])
  const [autopilot, setAutopilot] = useState({ active: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newItem, setNewItem] = useState({ title:'', description:'', priority:50, category:'FEATURE', status:'IDEA', risk_level:'low' })
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    Promise.all([
      api.forge.getBacklog(project.id).catch(() => ({ backlog: [] })),
      api.forge.autopilotStatus(project.id).catch(() => ({ status: { active: false } })),
    ]).then(([bl, ap]) => {
      if (bl.ok) setBacklog(bl.backlog || [])
      else setError(bl.error || 'Failed to load backlog')
      setAutopilot(ap.status || { active: false })
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { refresh() }, [refresh])

  const addItem = async () => {
    if (!newItem.title.trim()) return
    setBusy(b => ({ ...b, add: true }))
    try {
      const r = await api.forge.createBacklogItem(project.id, newItem)
      if (r.ok) { setShowAdd(false); setNewItem({ title:'', description:'', priority:50, category:'FEATURE', status:'IDEA', risk_level:'low' }); refresh(); onRefreshSummary?.() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, add: false })) }
  }

  const updateItem = async (id, patch) => {
    setBusy(b => ({ ...b, [id]: true }))
    try { await api.forge.updateBacklogItem(id, patch) } catch { /* ignore, refresh anyway */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  const deleteItem = async (id) => {
    if (!confirm('Delete this backlog item?')) return
    setBusy(b => ({ ...b, [id]: true }))
    try { await api.forge.deleteBacklogItem(id) } catch { /* ignore */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  const toggleAutopilot = async () => {
    try {
      if (autopilot.active) await api.forge.stopAutopilot(project.id)
      else await api.forge.startAutopilot(project.id, {})
    } catch { /* ignore */ }
    refresh(); onRefreshSummary?.()
  }

  if (!project) return <div className="af-backlog__empty"><EmptyState title="No project selected" body="Select a project to manage its backlog." /></div>
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading backlog...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-backlog">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Backlog <span className="af-tab__count">{backlog.length}</span></div>
        <div className="af-backlog__controls">
          <button className={`af-btn af-btn--sm ${autopilot.active ? 'af-btn--danger' : 'af-btn--primary'}`} onClick={toggleAutopilot}>
            {autopilot.active ? 'Stop Autopilot' : 'Start Autopilot'}
          </button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => setShowAdd(s => !s)}>+ Add Item</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {autopilot.active && (
        <div className="af-autopilot__status">
          <span className="af-pill af-pill--success">Autopilot Active</span>
          <span>Runs: {autopilot.runsCompleted || 0} / {autopilot.maxRuns || 10}</span>
          {autopilot.consecutiveFails > 0 && <span className="af-pill af-pill--warn">Fails: {autopilot.consecutiveFails}</span>}
        </div>
      )}
      {showAdd && (
        <div className="af-backlog__add-form">
          <input className="af-input" placeholder="Title *" value={newItem.title} onChange={e => setNewItem(n => ({ ...n, title: e.target.value }))} />
          <textarea className="af-input" placeholder="Description" rows={2} value={newItem.description} onChange={e => setNewItem(n => ({ ...n, description: e.target.value }))} />
          <div className="af-backlog__add-row">
            <select className="af-select" value={newItem.category} onChange={e => setNewItem(n => ({ ...n, category: e.target.value }))}>
              {['BUG','FEATURE','REFACTOR','SECURITY','UI','PERFORMANCE','TESTING','DOCS','ARCHITECTURE','AUTOMATION'].map(c => <option key={c}>{c}</option>)}
            </select>
            <select className="af-select" value={newItem.risk_level} onChange={e => setNewItem(n => ({ ...n, risk_level: e.target.value }))}>
              <option value="low">Low risk</option><option value="medium">Medium risk</option><option value="high">High risk</option>
            </select>
            <select className="af-select" value={newItem.status} onChange={e => setNewItem(n => ({ ...n, status: e.target.value }))}>
              {['IDEA','READY'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={addItem} disabled={busy.add}>{busy.add ? 'Adding...' : 'Add to Backlog'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      )}
      {backlog.length === 0 && <EmptyState title="Backlog is empty" body="Add items manually or use the Decomposer to generate tasks from a goal." />}
      <div className="af-backlog__list">
        {backlog.map(item => (
          <div key={item.backlog_id} className={`af-backlog__item af-backlog__item--${item.status.toLowerCase()}`}>
            <div className="af-backlog__item-head">
              <span className="af-backlog__category">{CATEGORY_ICONS[item.category] || '•'} {item.category}</span>
              <span className="af-backlog__status" style={{ color: STATUS_COLORS[item.status] }}>{item.status}</span>
              <span className="af-backlog__risk">{item.risk_level}</span>
            </div>
            <div className="af-backlog__item-title">{item.title}</div>
            {item.description && <div className="af-backlog__item-desc">{item.description.slice(0, 120)}{item.description.length > 120 ? '…' : ''}</div>}
            <div className="af-backlog__item-actions">
              {item.status === 'IDEA' && <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => updateItem(item.backlog_id, { status: 'READY' })} disabled={busy[item.backlog_id]}>Mark Ready</button>}
              {item.status === 'READY' && <button className="af-btn af-btn--sm af-btn--primary" onClick={() => { if(confirm('Trigger agentic run for this item?')) updateItem(item.backlog_id, { status: 'IN_PROGRESS' }) }} disabled={busy[item.backlog_id]}>Run</button>}
              <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => deleteItem(item.backlog_id)} disabled={busy[item.backlog_id]}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function DecomposerPane({ project, onRefreshSummary }) {
  const [goal, setGoal] = useState('')
  const [addToBacklog, setAddToBacklog] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const decompose = async () => {
    if (!goal.trim() || !project?.id) return
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await api.forge.decomposeTask(project.id, { goal, add_to_backlog: addToBacklog })
      if (r.ok) { setResult(r); if (r.added_to_backlog > 0) onRefreshSummary?.() }
      else setError(r.error || 'Decomposition failed')
    } catch (e) { setError(e.message || 'Decomposition failed') }
    finally { setLoading(false) }
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project first." />

  return (
    <div className="af-decomposer">
      <div className="af-decomposer__header">
        <SectionLabel>TASK DECOMPOSER</SectionLabel>
        <p className="af-decomposer__subtitle">Break a high-level goal into ordered subtasks using the Decomposer Agent.</p>
      </div>
      <div className="af-decomposer__form">
        <textarea className="af-input af-input--mono" rows={3} placeholder="Enter your goal... e.g. 'Add a complete backlog management system to the dashboard'" value={goal} onChange={e => setGoal(e.target.value)} />
        <div className="af-decomposer__options">
          <label className="af-decomposer__checkbox">
            <input type="checkbox" checked={addToBacklog} onChange={e => setAddToBacklog(e.target.checked)} />
            <span>Add subtasks to backlog as IDEA items</span>
          </label>
          <button className="af-btn af-btn--primary" onClick={decompose} disabled={loading || !goal.trim()}>{loading ? 'Decomposing...' : 'Decompose Goal'}</button>
        </div>
      </div>
      {error && <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error}</div>}
      {result && (
        <div className="af-decomposer__result">
          <SectionLabel>SUBTASKS ({result.count})</SectionLabel>
          {result.added_to_backlog > 0 && <div className="af-pill af-pill--success" style={{marginBottom:8}}>{result.added_to_backlog} items added to backlog</div>}
          {(result.subtasks || []).map((st, i) => (
            <div key={i} className="af-decomposer__subtask">
              <div className="af-decomposer__subtask-head">
                <span className="af-decomposer__idx">{i + 1}</span>
                <span className="af-decomposer__subtask-title">{st.title}</span>
                <span className={`af-risk af-risk--${st.risk_level || 'safe'}`}>{st.risk_level || 'low'}</span>
              </div>
              {st.description && <div className="af-decomposer__subtask-desc">{st.description}</div>}
              {st.acceptance_criteria && <div className="af-decomposer__subtask-criteria">Criteria: {st.acceptance_criteria}</div>}
              {st.affected_areas?.length > 0 && <div className="af-decomposer__subtask-areas">{st.affected_areas.join(', ')}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SkillsLibraryPane({ project }) {
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const skillId = (s) => s.id || s.skill_id

  const refresh = useCallback(() => {
    setLoading(true); setError(null)
    api.forge.getSkills()
      .then(d => { if (d.ok) setSkills(d.skills || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const reload = async () => {
    try { await api.forge.reloadSkills() } catch { /* ignore */ }
    refresh()
  }

  if (loading) return <div className="af-skills-lib__loading"><div className="af-spinner" />Loading skills...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-skills-lib">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Forge Skills <span className="af-tab__count">{skills.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={reload}>Reload Skills</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {skills.length === 0 && <EmptyState title="No skills loaded" body="Skills are loaded from the global skills library, with Forge-local definitions used only as supplemental compatibility entries." />}
      <div className="af-skills-lib__list">
        {skills.map(s => (
          <div key={skillId(s)} className={`af-skills-lib__card ${expanded === skillId(s) ? 'af-skills-lib__card--open' : ''}`}>
            <div className="af-skills-lib__card-head" onClick={() => setExpanded(expanded === skillId(s) ? null : skillId(s))}>
              <div className="af-skills-lib__card-name">{s.name}</div>
              <div className="af-skills-lib__card-id">{skillId(s)}</div>
              <span className="af-iconbtn">{expanded === skillId(s) ? '▲' : '▼'}</span>
            </div>
            {expanded === skillId(s) && (
              <div className="af-skills-lib__card-body">
                <p className="af-skills-lib__desc">{s.description}</p>
                <div className="af-skills-lib__tag-list">
                  <span className="af-skills-lib__tag">{s.ui_metadata?.wired === true || s.wired ? 'WIRED' : 'MOCK/UNWIRED'}</span>
                  {s.maturity_level && <span className="af-skills-lib__tag">{s.maturity_level}</span>}
                  {s.safety_level && <span className="af-skills-lib__tag">safety: {s.safety_level}</span>}
                  {s.execution_mode && <span className="af-skills-lib__tag">{s.execution_mode}</span>}
                  <span className="af-skills-lib__tag">{s.requires_human_approval ? 'approval required' : 'no approval required'}</span>
                  {s.test_cases?.length > 0 && <span className="af-skills-lib__tag">{s.test_cases.length} tests</span>}
                </div>
                {s.triggers?.length > 0 && (
                  <div className="af-skills-lib__triggers">
                    <SectionLabel>TRIGGERS</SectionLabel>
                    <div className="af-skills-lib__tag-list">{s.triggers.map(t => <span key={t} className="af-skills-lib__tag">{t}</span>)}</div>
                  </div>
                )}
                {s.when_to_use?.length > 0 && (
                  <div className="af-skills-lib__triggers">
                    <SectionLabel>WHEN TO USE</SectionLabel>
                    <div className="af-skills-lib__tag-list">{s.when_to_use.slice(0, 8).map(t => <span key={t} className="af-skills-lib__tag">{t}</span>)}</div>
                  </div>
                )}
                {s.tools_allowed?.length > 0 && (
                  <div className="af-skills-lib__triggers">
                    <SectionLabel>TOOLS ALLOWED</SectionLabel>
                    <div className="af-skills-lib__tag-list">{s.tools_allowed.map(t => <span key={t} className="af-skills-lib__tag">{t}</span>)}</div>
                  </div>
                )}
                {s.checklist?.length > 0 && (
                  <div className="af-skills-lib__checklist">
                    <SectionLabel>CHECKLIST</SectionLabel>
                    {s.checklist.map((c, i) => <div key={i} className="af-skills-lib__check-item">☐ {c}</div>)}
                  </div>
                )}
                {s.success_criteria?.length > 0 && (
                  <div className="af-skills-lib__checklist">
                    <SectionLabel>SUCCESS CRITERIA</SectionLabel>
                    {s.success_criteria.map((c, i) => <div key={i} className="af-skills-lib__check-item">- {c}</div>)}
                  </div>
                )}
                {s.verification_commands?.length > 0 && (
                  <div className="af-skills-lib__verif">
                    <SectionLabel>VERIFICATION</SectionLabel>
                    {s.verification_commands.map((c, i) => <code key={i} className="af-skills-lib__cmd">{c}</code>)}
                  </div>
                )}
                {s.common_failure_modes?.length > 0 && (
                  <div className="af-skills-lib__failures">
                    <SectionLabel>COMMON FAILURES</SectionLabel>
                    {s.common_failure_modes.map((f, i) => <div key={i} className="af-skills-lib__fail-item">⚠ {f}</div>)}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ModelRouterPane({ project }) {
  const [models, setModels] = useState([])
  const [stats, setStats] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newModel, setNewModel] = useState({ model_id:'', provider:'anthropic', role:'any', cost_tier:'medium', speed_tier:'medium' })
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    setLoading(true); setError(null)
    Promise.all([
      api.forge.getModels(),
      project?.id ? api.forge.modelRoutingStats(project.id).catch(() => ({ stats: [] })) : Promise.resolve({ stats: [] }),
    ]).then(([md, st]) => {
      if (md.ok) setModels(md.models || []); else setError(md.error)
      setStats(st.stats || [])
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const addModel = async () => {
    if (!newModel.model_id || !newModel.provider) return
    setBusy(b => ({ ...b, add: true }))
    try {
      const r = await api.forge.createModel(newModel)
      if (r.ok) { setShowAdd(false); setNewModel({ model_id:'', provider:'anthropic', role:'any', cost_tier:'medium', speed_tier:'medium' }); refresh() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, add: false })) }
  }

  const toggleModel = async (m) => {
    setBusy(b => ({ ...b, [m.model_id]: true }))
    try { await api.forge.updateModel(m.model_id, { enabled: !m.enabled }) } catch { /* ignore */ }
    setBusy(b => ({ ...b, [m.model_id]: false })); refresh()
  }

  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading models...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-model-router">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Model Router <span className="af-tab__count">{models.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => setShowAdd(s => !s)}>+ Add Model</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {models.length === 0 && !showAdd && <EmptyState title="No models configured" body="Add model configurations to enable intelligent routing. Without configuration, the system uses environment-variable defaults." />}
      {showAdd && (
        <div className="af-backlog__add-form">
          <input className="af-input" placeholder="Model ID (e.g. claude-sonnet-4-6) *" value={newModel.model_id} onChange={e => setNewModel(n => ({ ...n, model_id: e.target.value }))} />
          <div className="af-backlog__add-row">
            <select className="af-select" value={newModel.provider} onChange={e => setNewModel(n => ({ ...n, provider: e.target.value }))}>
              {['anthropic','openai','ollama','google','mistral'].map(p => <option key={p}>{p}</option>)}
            </select>
            <select className="af-select" value={newModel.role} onChange={e => setNewModel(n => ({ ...n, role: e.target.value }))}>
              {['any','planner','coder','tester','security','reviewer','decomposer','summarizer'].map(r => <option key={r}>{r}</option>)}
            </select>
            <select className="af-select" value={newModel.cost_tier} onChange={e => setNewModel(n => ({ ...n, cost_tier: e.target.value }))}>
              {['low','medium','high'].map(t => <option key={t}>{t}</option>)}
            </select>
            <select className="af-select" value={newModel.speed_tier} onChange={e => setNewModel(n => ({ ...n, speed_tier: e.target.value }))}>
              {['fast','medium','slow'].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={addModel} disabled={busy.add}>{busy.add ? 'Adding...' : 'Add Model'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      )}
      <div className="af-model-router__list">
        {models.map(m => (
          <div key={m.model_id} className={`af-model-router__card ${m.enabled ? '' : 'af-model-router__card--disabled'}`}>
            <div className="af-model-router__card-head">
              <div className="af-model-router__model-id">{m.model_id}</div>
              <span className="af-pill af-pill--sm">{m.provider}</span>
              <span className="af-pill af-pill--sm">{m.role}</span>
            </div>
            <div className="af-model-router__card-meta">
              cost: {m.cost_tier} · speed: {m.speed_tier} · {m.local_or_remote}
            </div>
            <button className={`af-btn af-btn--sm ${m.enabled ? 'af-btn--danger' : 'af-btn--success'}`} onClick={() => toggleModel(m)} disabled={busy[m.model_id]}>
              {m.enabled ? 'Disable' : 'Enable'}
            </button>
          </div>
        ))}
      </div>
      {stats.length > 0 && (
        <div className="af-model-router__stats">
          <SectionLabel>ROUTING STATS (THIS PROJECT)</SectionLabel>
          {stats.map((s, i) => (
            <div key={i} className="af-model-router__stat-row">
              <span className="af-model-router__stage">{s.stage}</span>
              <span className="af-model-router__model">{s.selected_model_id}</span>
              <span className="af-model-router__count">{s.count}x</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function CyclesPane({ project }) {
  const [cycles, setCycles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newCycle, setNewCycle] = useState({ goal:'', autonomy_level:2, max_runs:10 })
  const [busy, setBusy] = useState({})

  const refresh = () => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getCycles(project.id)
      .then(d => { if (d.ok) setCycles(d.cycles || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { refresh() }, [project?.id])

  const createCycle = async () => {
    if (!newCycle.goal.trim()) return
    setBusy(b => ({ ...b, create: true }))
    try {
      const r = await api.forge.createCycle(project.id, newCycle)
      if (r.ok) { setShowCreate(false); setNewCycle({ goal:'', autonomy_level:2, max_runs:10 }); refresh() }
      else setError(r.error)
    } catch (e) { setError(e.message) }
    finally { setBusy(b => ({ ...b, create: false })) }
  }

  const cycleAction = async (cycleId, action) => {
    setBusy(b => ({ ...b, [cycleId]: true }))
    try {
      if (action === 'pause') await api.forge.pauseCycle(cycleId)
      else if (action === 'resume') await api.forge.resumeCycle(cycleId)
      else if (action === 'cancel') await api.forge.cancelCycle(cycleId)
    } catch { /* ignore */ }
    setBusy(b => ({ ...b, [cycleId]: false })); refresh()
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to manage development cycles." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading cycles...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  return (
    <div className="af-cycle">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Development Cycles <span className="af-tab__count">{cycles.length}</span></div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--primary" onClick={() => setShowCreate(s => !s)}>+ New Cycle</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {showCreate && (
        <div className="af-backlog__add-form">
          <textarea className="af-input" rows={2} placeholder="Cycle goal *" value={newCycle.goal} onChange={e => setNewCycle(n => ({ ...n, goal: e.target.value }))} />
          <div className="af-backlog__add-row">
            <label className="af-model-router__stage">Autonomy Level:</label>
            <select className="af-select" value={newCycle.autonomy_level} onChange={e => setNewCycle(n => ({ ...n, autonomy_level: +e.target.value }))}>
              <option value={0}>0 — ReadOnly</option><option value={1}>1 — SafeEdits</option><option value={2}>2 — Guided</option><option value={3}>3 — Autopilot</option>
            </select>
            <label className="af-model-router__stage">Max Runs:</label>
            <input className="af-input" type="number" min={1} max={50} value={newCycle.max_runs} onChange={e => setNewCycle(n => ({ ...n, max_runs: +e.target.value }))} style={{width:70}} />
          </div>
          <div className="af-backlog__add-actions">
            <button className="af-btn af-btn--primary af-btn--sm" onClick={createCycle} disabled={busy.create}>{busy.create ? 'Creating...' : 'Create Cycle'}</button>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}
      {cycles.length === 0 && <EmptyState title="No cycles yet" body="Create a development cycle to orchestrate multiple backlog items toward a goal." />}
      <div className="af-cycle__list">
        {cycles.map(c => (
          <div key={c.cycle_id} className={`af-cycle__card af-cycle__card--${c.status.toLowerCase()}`}>
            <div className="af-cycle__card-head">
              <span className="af-cycle__status" style={{ color: STATUS_COLORS[c.status] || '#6b7280' }}>{c.status}</span>
              <span className="af-pill af-pill--sm">L{c.autonomy_level}</span>
              <span className="af-cycle__runs">{(c.run_ids || []).length}/{c.max_runs} runs</span>
            </div>
            <div className="af-cycle__goal">{c.goal}</div>
            <div className="af-cycle__meta">
              Items: {(c.backlog_items || []).length} · Started: {c.started_at ? new Date(c.started_at).toLocaleDateString() : 'N/A'}
            </div>
            <div className="af-backlog__item-actions">
              {c.status === 'RUNNING' && <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => cycleAction(c.cycle_id, 'pause')} disabled={busy[c.cycle_id]}>Pause</button>}
              {c.status === 'PAUSED' && <button className="af-btn af-btn--sm af-btn--primary" onClick={() => cycleAction(c.cycle_id, 'resume')} disabled={busy[c.cycle_id]}>Resume</button>}
              {['RUNNING','PAUSED'].includes(c.status) && <button className="af-btn af-btn--sm af-btn--danger" onClick={() => { if(confirm('Cancel this cycle?')) cycleAction(c.cycle_id, 'cancel') }} disabled={busy[c.cycle_id]}>Cancel</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function RoadmapPane({ project }) {
  const [roadmap, setRoadmap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getRoadmap(project.id)
      .then(d => { if (d.ok) setRoadmap(d.roadmap); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const generate = async () => {
    setGenerating(true); setError(null)
    let r
    try { r = await api.forge.generateRoadmap(project.id) } catch (e) { r = { ok: false, error: e.message } }
    setGenerating(false)
    if (r.ok) setRoadmap(r.roadmap)
    else setError(r.error || 'Generation failed')
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to view its roadmap." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading roadmap...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  const content = roadmap?.content || {}

  return (
    <div className="af-roadmap">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Project Roadmap</div>
        <div className="af-backlog__controls">
          <button className="af-btn af-btn--sm af-btn--primary" onClick={generate} disabled={generating}>{generating ? 'Generating...' : 'Generate Roadmap'}</button>
          <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>
      {!roadmap && <EmptyState title="No roadmap yet" body="Click Generate Roadmap to let the AI analyze your project and produce a structured development roadmap." />}
      {roadmap && (
        <>
          {content.current_state && (
            <div className="af-roadmap__section">
              <SectionLabel>CURRENT STATE</SectionLabel>
              <p className="af-roadmap__text">{content.current_state}</p>
              {content.estimated_complexity && <span className="af-pill af-pill--sm">Complexity: {content.estimated_complexity}</span>}
            </div>
          )}
          {content.recommended_next_tasks?.length > 0 && (
            <div className="af-roadmap__section">
              <SectionLabel>RECOMMENDED NEXT TASKS</SectionLabel>
              {content.recommended_next_tasks.map((t, i) => (
                <div key={i} className="af-roadmap__task">
                  <span className={`af-pill af-pill--sm af-pill--${t.priority === 'high' ? 'danger' : t.priority === 'medium' ? 'warn' : 'idle'}`}>{t.priority}</span>
                  <span className="af-roadmap__task-title">{t.title}</span>
                  {t.category && <span className="af-pill af-pill--sm">{t.category}</span>}
                </div>
              ))}
            </div>
          )}
          {['known_issues','technical_debt','missing_features','security_improvements','performance_improvements'].map(key => (
            content[key]?.length > 0 && (
              <div key={key} className="af-roadmap__section">
                <SectionLabel>{key.replace(/_/g,' ').toUpperCase()}</SectionLabel>
                {content[key].map((item, i) => <div key={i} className="af-roadmap__item">• {typeof item === 'string' ? item : JSON.stringify(item)}</div>)}
              </div>
            )
          ))}
          {roadmap.updated_at && <div className="af-roadmap__updated">Last updated: {new Date(roadmap.updated_at).toLocaleString()}</div>}
        </>
      )}
    </div>
  )
}

export function SuggestionsPane({ project, onRefreshSummary }) {
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState({})

  const refresh = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getSuggestions(project.id)
      .then(d => { if (d.ok) setSuggestions(d.suggestions || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])
  useEffect(() => { refresh() }, [refresh])

  const action = async (id, endpoint) => {
    setBusy(b => ({ ...b, [id]: true }))
    try {
      if (endpoint === 'accept') await api.forge.acceptSuggestion(id)
      else if (endpoint === 'reject') await api.forge.rejectSuggestion(id)
      else if (endpoint === 'create-backlog-item') await api.forge.suggestionToBacklog(id)
    } catch { /* ignore */ }
    setBusy(b => ({ ...b, [id]: false })); refresh(); onRefreshSummary?.()
  }

  if (!project) return <EmptyState title="No project selected" body="Select a project to view improvement suggestions." />
  if (loading) return <div className="af-backlog__loading"><div className="af-spinner" />Loading suggestions...</div>
  if (error) return <div className="af-backlog__error"><span className="af-pill af-pill--danger">Error</span> {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={refresh}>Retry</button></div>

  const open = suggestions.filter(s => s.status === 'new')
  const closed = suggestions.filter(s => s.status !== 'new')

  return (
    <div className="af-suggestion">
      <div className="af-backlog__header">
        <div className="af-backlog__title">Self-Improvement <span className="af-tab__count">{open.length} open</span></div>
        <button className="af-btn af-btn--sm af-btn--ghost" onClick={refresh}>Refresh</button>
      </div>
      {suggestions.length === 0 && <EmptyState title="No suggestions yet" body="Suggestions are auto-generated after each agentic run based on security findings, reviewer findings, and failure patterns." />}
      {open.map(s => (
        <div key={s.suggestion_id} className={`af-suggestion__card af-suggestion__card--${s.risk_level}`}>
          <div className="af-suggestion__card-head">
            <span className={`af-pill af-pill--sm af-pill--${s.risk_level === 'high' ? 'danger' : s.risk_level === 'medium' ? 'warn' : 'idle'}`}>{s.risk_level}</span>
            <span className="af-pill af-pill--sm">{s.category}</span>
          </div>
          <div className="af-suggestion__title">{s.title}</div>
          {s.description && <div className="af-suggestion__desc">{s.description}</div>}
          {s.recommended_fix && <div className="af-suggestion__fix">Fix: {s.recommended_fix}</div>}
          <div className="af-suggestion__actions">
            <button className="af-btn af-btn--sm af-btn--success" onClick={() => action(s.suggestion_id, 'accept')} disabled={busy[s.suggestion_id]}>Accept</button>
            <button className="af-btn af-btn--sm af-btn--primary" onClick={() => action(s.suggestion_id, 'create-backlog-item')} disabled={busy[s.suggestion_id]}>Add to Backlog</button>
            <button className="af-btn af-btn--sm af-btn--ghost" onClick={() => action(s.suggestion_id, 'reject')} disabled={busy[s.suggestion_id]}>Dismiss</button>
          </div>
        </div>
      ))}
      {closed.length > 0 && (
        <details className="af-suggestion__closed">
          <summary>Closed suggestions ({closed.length})</summary>
          {closed.map(s => (
            <div key={s.suggestion_id} className="af-suggestion__card af-suggestion__card--closed">
              <span className="af-pill af-pill--sm">{s.status}</span> {s.title}
            </div>
          ))}
        </details>
      )}
    </div>
  )
}
