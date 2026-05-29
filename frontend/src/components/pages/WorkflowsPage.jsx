import { useEffect, useMemo, useRef, useState } from 'react'
import { Panel, SectionLabel, StatusPill, EmptyState, ErrorState } from '../nexus-ui'
import useLiveData from '../../hooks/useLiveData'
import { useAppStore } from '../../store/appStore'
import { toastSuccess, toastError, toastWarn } from '../nexus-ui/Toaster'
import './WorkflowsPage.css'

const tabs = [
  ['canvas', 'Live Canvas'],
  ['roadmap', 'Roadmap'],
  ['templates', 'Templates'],
  ['skills', 'Skill Packs'],
  ['finance', 'Finance'],
  ['business', 'Brand Kit'],
  ['builder', 'Builder'],
]

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('ai_jwt')
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

async function request(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || data.message || `${res.status} ${res.statusText}`)
  return data
}

// ── Roadmap Panel ─────────────────────────────────────────────────────────────
const STATUS_COLORS = { pending: '#9a927e', running: '#e89a4f', done: '#22c55e', failed: '#ef4444', active: '#60a5fa' }
const STATUS_ICONS  = { pending: '○', running: '●', done: '✓', failed: '✗', active: '▶' }

function MilestoneCard({ milestone, isActive }) {
  const [open, setOpen] = useState(isActive)
  const allDone   = milestone.tasks?.every(t => t.status === 'done')
  const hasFailed = milestone.tasks?.some(t => t.status === 'failed')
  const running   = milestone.tasks?.some(t => t.status === 'running')
  const statusColor = allDone ? STATUS_COLORS.done : hasFailed ? STATUS_COLORS.failed : running ? STATUS_COLORS.running : STATUS_COLORS.pending
  const statusKey = allDone ? 'done' : hasFailed ? 'failed' : running ? 'running' : 'pending'

  return (
    <div
      className="mc"
      style={{ border: `1px solid ${statusColor}33`, borderLeft: `3px solid ${statusColor}` }}
    >
      <button className="mc__toggle" onClick={() => setOpen(o => !o)}>
        <span className="mc__icon" style={{ color: statusColor }}>{STATUS_ICONS[statusKey]}</span>
        <span className="mc__title">{milestone.title}</span>
        {milestone.deadline && <span className="mc__deadline">{milestone.deadline}</span>}
        <span className="mc__chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mc__body">
          {(milestone.tasks || []).map(task => (
            <div key={task.id} className="mc__task">
              <span className="mc__task-icon" style={{ color: STATUS_COLORS[task.status] || '#9a927e' }}>{STATUS_ICONS[task.status] || '○'}</span>
              <span className={`mc__task-title${task.status === 'done' ? ' mc__task-title--done' : ' mc__task-title--active'}`}>{task.title}</span>
              {task.agent_id && <span className="mc__agent-badge">{task.agent_id}</span>}
              {task.status && (
                <span
                  className="mc__status-badge"
                  style={{ border: `1px solid ${STATUS_COLORS[task.status] || '#9a927e'}44`, color: STATUS_COLORS[task.status] || '#9a927e' }}
                >{task.status}</span>
              )}
            </div>
          ))}
          {(!milestone.tasks || milestone.tasks.length === 0) && (
            <div className="mc__no-tasks">No tasks generated yet</div>
          )}
        </div>
      )}
    </div>
  )
}

function RoadmapPanel() {
  const [goal, setGoal]           = useState('')
  const [roadmaps, setRoadmaps]   = useState([])
  const [selected, setSelected]   = useState(null)
  const [busy, setBusy]           = useState(false)
  const [execBusy, setExecBusy]   = useState(false)
  const [pollTimer, setPollTimer] = useState(null)
  const goalRef = useRef(null)

  // Derive tenant from JWT
  const tenantId = (() => {
    try {
      const tok = sessionStorage.getItem('ai_jwt')
      if (!tok) return 'default'
      const payload = JSON.parse(atob(tok.split('.')[1]))
      return payload.tenant_id || 'default'
    } catch { return 'default' }
  })()

  const loadList = () =>
    request(`/api/roadmap/list/${encodeURIComponent(tenantId)}`, { headers: authHeaders() })
      .then(d => setRoadmaps(d.roadmaps || []))
      .catch(() => {})

  useEffect(() => { loadList() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll selected roadmap while it's active
  useEffect(() => {
    if (!selected?.id) return
    if (selected.status === 'complete' || selected.status === 'failed') return
    const t = setInterval(() => {
      request(`/api/roadmap/${encodeURIComponent(selected.id)}`, { headers: authHeaders() })
        .then(d => { if (d.roadmap || d.id) setSelected(d.roadmap || d) })
        .catch(() => {})
    }, 3000)
    setPollTimer(t)
    return () => clearInterval(t)
  }, [selected?.id, selected?.status])

  const handleCreate = async () => {
    if (!goal.trim()) return
    setBusy(true)
    try {
      const created = await request('/api/roadmap/create', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ goal: goal.trim(), tenant_id: tenantId }),
      })
      const roadmap = created.roadmap || created
      // auto-generate milestones
      const generated = await request('/api/roadmap/generate', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ roadmap_id: roadmap.id }),
      })
      const full = generated.roadmap || generated
      setSelected(full)
      setRoadmaps(prev => [full, ...prev.filter(r => r.id !== full.id)])
      setGoal('')
      toastSuccess('Roadmap created — milestones generated')
    } catch (e) {
      toastError(`Failed to create roadmap: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const handleExecute = async () => {
    if (!selected?.id) return
    setExecBusy(true)
    try {
      await request(`/api/roadmap/${encodeURIComponent(selected.id)}/execute`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({}),
      })
      toastSuccess('Roadmap execution started')
      // refresh immediately
      const d = await request(`/api/roadmap/${encodeURIComponent(selected.id)}`, { headers: authHeaders() })
      setSelected(d.roadmap || d)
    } catch (e) {
      toastError(`Execution failed: ${e.message}`)
    } finally {
      setExecBusy(false)
    }
  }

  const milestones = selected?.milestones || []
  const totalTasks = milestones.reduce((s, m) => s + (m.tasks?.length || 0), 0)
  const doneTasks  = milestones.reduce((s, m) => s + (m.tasks?.filter(t => t.status === 'done').length || 0), 0)
  const pct = totalTasks > 0 ? Math.round(doneTasks / totalTasks * 100) : 0

  return (
    <div className="rdm-layout">
      {/* Left: list */}
      <div className="rdm-sidebar">
        <div className="rdm-sidebar__top">
          <div className="rdm-sidebar__heading">Roadmaps</div>
          <textarea
            ref={goalRef}
            className="rdm-textarea"
            value={goal}
            onChange={e => setGoal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleCreate() }}
            placeholder="Enter a goal… (⌘↵ to create)"
            rows={3}
          />
          <button
            className="rdm-create-btn"
            onClick={handleCreate}
            disabled={busy || !goal.trim()}
          >{busy ? 'GENERATING…' : '+ CREATE ROADMAP'}</button>
        </div>
        <div className="rdm-list">
          {roadmaps.length === 0 && (
            <div className="rdm-list__empty">No roadmaps yet — enter a goal above</div>
          )}
          {roadmaps.map(r => {
            const isActive = r.id === selected?.id
            const statusColor = r.status === 'complete' ? STATUS_COLORS.done : r.status === 'active' ? STATUS_COLORS.running : STATUS_COLORS.pending
            return (
              <button
                key={r.id}
                className={`rdm-list__item${isActive ? ' rdm-list__item--active' : ''}`}
                onClick={() => setSelected(r)}
              >
                <div className="rdm-list__goal">{r.goal?.slice(0, 40) || 'Untitled'}</div>
                <div className="rdm-list__meta" style={{ color: statusColor }}>{r.status || 'draft'} · {r.milestones?.length || 0} milestones</div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Right: detail */}
      <div className="rdm-main">
        {!selected ? (
          <div className="rdm-main__empty">
            Select a roadmap or create one from a goal
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="rdm-detail-hd">
              <div className="rdm-detail-hd__info">
                <div className="rdm-detail-hd__goal">{selected.goal}</div>
                <div className="rdm-detail-hd__stats">
                  <span className="rdm-detail-hd__stat-label">
                    {selected.status || 'draft'} · {milestones.length} milestones · {totalTasks} tasks
                  </span>
                  {totalTasks > 0 && (
                    <span className="rdm-detail-hd__done">{pct}% done</span>
                  )}
                </div>
                {totalTasks > 0 && (
                  <div className="rdm-progress-track">
                    <div className="rdm-progress-fill" style={{ width: `${pct}%` }} />
                  </div>
                )}
              </div>
              <div className="rdm-detail-hd__actions">
                <button
                  className="rdm-exec-btn"
                  onClick={handleExecute}
                  disabled={execBusy || selected.status === 'complete' || milestones.length === 0}
                >{execBusy ? 'RUNNING…' : selected.status === 'complete' ? '✓ COMPLETE' : '▶ EXECUTE'}</button>
              </div>
            </div>

            {/* Milestones */}
            <div className="rdm-milestones">
              {milestones.length === 0 && (
                <div className="rdm-milestones__empty">
                  No milestones yet — the AI will decompose this goal when generated.
                </div>
              )}
              {milestones.map((m, i) => (
                <MilestoneCard key={m.id || i} milestone={m} isActive={m.status === 'running'} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function WorkflowEmpty({ title, sub, primary, onPrimary, secondary, onSecondary }) {
  return (
    <div className="wf-guided-empty">
      <EmptyState icon="[]" title={title} sub={sub} action={primary} onAction={onPrimary} />
      {secondary && onSecondary && (
        <button className="wf-btn" type="button" onClick={onSecondary}>{secondary}</button>
      )}
    </div>
  )
}

function WorkflowCanvas({ workflows, runs, onSelect, onCreate, onSetup }) {
  const items = runs.length ? runs : workflows
  if (!items.length) {
    return (
      <WorkflowEmpty
        title="No workflow executions"
        sub="Create a workflow draft or run setup if workflow templates and skills are not available."
        primary="Create Workflow"
        onPrimary={onCreate}
        secondary="Open Setup"
        onSecondary={onSetup}
      />
    )
  }
  return (
    <div className="wf-canvas-wrap">
      <div className="wf-canvas-overlay-labels">
        {items.map((item) => (
          <button key={item.id} className="wf-region-label" onClick={() => onSelect(item)}>
            {(item.name || item.workflow_id || item.id).slice(0, 40)}
          </button>
        ))}
      </div>
      <div className="wf-imports__grid">
        {items.map((item) => (
          <div key={item.id} className="wf-imports__panel" onClick={() => onSelect(item)}>
            <div className="wf-imports__panel-head">
              <span>{item.name || item.workflow_id || item.id}</span>
              <StatusPill label={(item.status || 'draft').toUpperCase()} tone={item.status === 'running' ? 'success' : item.status === 'failed' ? 'alert' : 'idle'} size="sm" />
            </div>
            <p className="wf-imports__sub">{item.description || item.approval_state || 'Main AI workflow record'}</p>
            <div className="wf-imports__chips">
              {(item.steps || item.nodes || []).slice(0, 6).map((step, index) => (
                <span key={`${item.id}-${index}`} className="wf-imports__chip">{step.label || step.name || step.agent || step}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="wf-canvas-hud">
        <span className="wf-hud-item">DEFINITIONS {workflows.length}</span>
        <span className="wf-hud-sep">.</span>
        <span className="wf-hud-item">RUNS {runs.length}</span>
        <span className="wf-hud-sep">.</span>
        <span className="wf-hud-item">OWNER main-ai-orchestrator</span>
      </div>
    </div>
  )
}

function WorkflowDetail({ item, onRun }) {
  if (!item) {
    return (
      <div className="wf-detail wf-detail--empty">
        <EmptyState icon="[]" title="Select a workflow" sub="Inspect definition, steps, gates and run state." />
      </div>
    )
  }
  return (
    <div className="wf-detail">
      <div className="wf-detail__header">
        <span className="wf-detail__name">{item.name || item.workflow_id || item.id}</span>
      </div>
      <StatusPill label={(item.status || item.approval_state || 'draft').toUpperCase()} tone={item.status === 'running' ? 'success' : 'idle'} size="sm" />
      <p className="wf-detail__desc">{item.description || 'No description stored.'}</p>
      <SectionLabel>Steps</SectionLabel>
      <div className="wf-detail__agents">
        {(item.steps || item.nodes || []).map((step, index) => (
          <div key={index} className="wf-detail__agent">
            <span className="wf-detail__agent-dot" />
            {step.label || step.name || step.agent || step}
          </div>
        ))}
      </div>
      <div className="wf-detail__actions">
        <button className="wf-btn wf-btn--primary" onClick={() => onRun(item.id)}>Run Through Main AI</button>
      </div>
      <div className="wf-detail__meta">AscendForge boundary: code/build artifacts only, never workflow ownership.</div>
    </div>
  )
}

function TemplatesPanel({ templates, onUse, onCreate }) {
  const [expanded, setExpanded] = useState(null)
  if (!templates.length) {
    return (
      <WorkflowEmpty
        title="No workflow templates"
        sub="Template registry is empty. Create a supervised workflow draft while setup checks provider availability."
        primary="Open Builder"
        onPrimary={onCreate}
      />
    )
  }
  return (
    <div className="wf-templates__grid">
      {templates.map((tpl) => (
        <div key={tpl.id} className="wf-tpl">
          <div className="wf-tpl__header" onClick={() => setExpanded(expanded === tpl.id ? null : tpl.id)}>
            <span className="wf-tpl__name">{tpl.name}</span>
            <StatusPill label={(tpl.risk || 'standard').toUpperCase()} tone={tpl.risk === 'dangerous' ? 'warn' : 'idle'} size="sm" />
          </div>
          <p className="wf-tpl__desc">{tpl.description}</p>
          <div className="wf-tpl__agents">
            {(tpl.agents || tpl.steps || []).slice(0, 4).map((item) => (
              <span key={item.id || item.label || item} className="wf-tpl__agent-pill">{item.label || item.agent || item}</span>
            ))}
          </div>
          {expanded === tpl.id && (
            <div className="wf-detail__agents">
              {(tpl.steps || []).map((step) => (
                <div key={step.id || step.label} className="wf-detail__agent">
                  <span className="wf-detail__agent-dot" />
                  <span>{step.label || step.id}</span>
                </div>
              ))}
              <div className="wf-detail__meta">{tpl.boundary || 'Main AI owns workflow execution.'}</div>
            </div>
          )}
          <div className="wf-tpl__footer">
            <span className="wf-tpl__cost">{tpl.estimatedCost || tpl.estimated_cost || 'cost unknown'}</span>
            <button className="wf-tpl__fork" onClick={() => onUse(tpl)}>Use Template</button>
          </div>
        </div>
      ))}
    </div>
  )
}

function SkillPacksPanel({ packs, onSetup }) {
  if (!packs.length) {
    return (
      <WorkflowEmpty
        title="No skill packs loaded"
        sub="The global skills library did not return any packs. Check capability status before running skill-dependent workflows."
        primary="Open Setup"
        onPrimary={onSetup}
      />
    )
  }
  return (
    <div className="wf-skillpacks">
      {packs.map((pack) => (
        <div key={pack.id || pack.source_pack} className="wf-skillpack">
          <div className="wf-skillpack__head">
            <span>{pack.name || pack.source_pack}</span>
            <StatusPill label={`${pack.skills?.length || pack.skill_count || 0} SKILLS`} tone="success" size="sm" />
          </div>
          <p className="wf-imports__sub">{pack.description || 'Native AETERNUS capability pack.'}</p>
          <div className="wf-imports__chips">
            {(pack.skills || []).slice(0, 16).map((skill) => (
              <span key={skill.id || skill} className="wf-imports__chip">{skill.name || skill.id || skill}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function FinancePanel({ workflows, onEconomy }) {
  if (!workflows.length) {
    return (
      <WorkflowEmpty
        title="No finance workflows"
        sub="Finance templates are unavailable or disabled. Use Money Mode for approval-gated revenue work."
        primary="Open Money Mode"
        onPrimary={onEconomy}
      />
    )
  }
  async function runFinance(id) {
    try {
      await request(`/api/finance/workflows/${encodeURIComponent(id)}/run`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ mode: 'draft', source_documents: [] }),
      })
      toastSuccess('Finance workflow draft queued for review')
    } catch (err) {
      toastError(err.message)
    }
  }
  return (
    <div className="wf-finance-grid">
      {workflows.map((workflow) => (
        <div key={workflow.id} className="wf-finance-card">
          <div className="wf-finance-card__head">
            <span>{workflow.name}</span>
            <StatusPill label="DRAFT ONLY" tone="warn" size="sm" />
          </div>
          <p>{workflow.domain || workflow.description || 'Supervised finance workflow.'}</p>
          <div className="wf-imports__chips">
            {(workflow.outputs || workflow.skills || []).slice(0, 6).map((item) => <span key={item} className="wf-imports__chip">{item}</span>)}
          </div>
          <button className="wf-btn wf-btn--primary" onClick={() => runFinance(workflow.id)}>Run Draft</button>
        </div>
      ))}
    </div>
  )
}

function BusinessPanel({ templates }) {
  const [selected, setSelected] = useState([])
  const [projectId, setProjectId] = useState('default-project')
  const [brandKit, setBrandKit] = useState(null)

  async function generateBrandKit() {
    const id = selected[0] || templates[0]?.id
    if (!id) return
    try {
      const data = await request(`/api/business/templates/${encodeURIComponent(id)}/brand-kit`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ projectId, templateIds: selected.length ? selected : [id] }),
      })
      setBrandKit(data.brandKit)
      toastSuccess('Brand Kit draft created by the main AI orchestration layer')
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="wf-templates">
      <Panel title="Business Template Selection">
        <div className="wf-imports__chips">
          {templates.map((tpl) => (
            <button
              key={tpl.id}
              className={`wf-imports__chip ${selected.includes(tpl.id) ? 'wf-tab--active' : ''}`}
              onClick={() => setSelected((ids) => ids.includes(tpl.id) ? ids.filter((id) => id !== tpl.id) : [...ids, tpl.id])}
            >
              {tpl.name}
            </button>
          ))}
        </div>
        {!templates.length && <EmptyState icon="[]" title="No business templates" sub="Business template registry is empty." />}
        <input className="ops-input" value={projectId} onChange={(e) => setProjectId(e.target.value)} placeholder="Target project id" />
        <button className="wf-btn wf-btn--primary" onClick={generateBrandKit}>Generate Brand Kit Draft</button>
      </Panel>
      {brandKit && (
        <Panel title="Brand Kit Draft">
          <p>{brandKit.boundary}</p>
          <div className="wf-imports__grid">
            {Object.entries(brandKit.artifacts || {}).map(([key, value]) => (
              <div key={key} className="wf-imports__panel">
                <div className="wf-imports__panel-head"><span>{key.replace(/_/g, ' ')}</span></div>
                <pre className="wf-detail__meta">{JSON.stringify(value, null, 2)}</pre>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  )
}

function BuilderPanel({ skills, onCreated }) {
  const [form, setForm] = useState({ name: '', goal: '', trigger: 'manual', approval_policy: 'owner_approval_required' })
  async function createWorkflow(e) {
    e.preventDefault()
    if (!form.name.trim() || !form.goal.trim()) return
    try {
      await request('/api/workflows', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          ...form,
          owner: 'main_ai_orchestrator',
          steps: [
            { id: 'plan', label: 'Main AI plan', agent: 'main-ai' },
            { id: 'execute', label: 'Main AI execute workflow', agent: 'main-ai' },
            { id: 'review', label: 'Owner approval gate', agent: 'owner' },
          ],
          skills: skills.slice(0, 6).map((skill) => skill.id),
        }),
      })
      toastSuccess('Workflow draft saved under main AI ownership')
      setForm({ name: '', goal: '', trigger: 'manual', approval_policy: 'owner_approval_required' })
      onCreated()
    } catch (err) {
      toastError(err.message)
    }
  }
  return (
    <Panel title="Workflow Builder">
      <form className="ops-create-form" onSubmit={createWorkflow}>
        <input className="ops-input" placeholder="Workflow name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <textarea className="ops-input" rows={4} placeholder="Workflow goal" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
        <input className="ops-input" placeholder="Trigger" value={form.trigger} onChange={(e) => setForm({ ...form, trigger: e.target.value })} />
        <button className="wf-btn wf-btn--primary">Save Draft Workflow</button>
      </form>
      <p className="wf-imports__sub">Builder creates orchestration definitions for the main AI. AscendForge can be attached later only for approved code or website artifacts.</p>
    </Panel>
  )
}

export default function WorkflowsPage() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [activeTab, setActiveTab] = useState('canvas')
  const [selected, setSelected] = useState(null)
  const [templates, setTemplates] = useState([])
  const [runs, setRuns] = useState([])
  const [packs, setPacks] = useState([])
  const [finance, setFinance] = useState([])
  const [businessTemplates, setBusinessTemplates] = useState([])

  const { data, loading, error, refresh } = useLiveData({
    endpoint: '/api/workflows',
    wsEvent: 'workflow:update',
    pollMs: 15000,
    transform: (d) => d.workflows || d.definitions || [],
  })
  const workflows = data || []

  useEffect(() => {
    request('/api/workflows/templates').then((d) => setTemplates(d.templates || [])).catch(() => setTemplates([]))
    request('/api/workflows/runs').then((d) => setRuns(d.runs || [])).catch(() => setRuns([]))
    request('/api/skills/packs').then((d) => setPacks(d.packs || [])).catch(() => setPacks([]))
    request('/api/finance/workflows').then((d) => setFinance(d.workflows || [])).catch(() => setFinance([]))
    request('/api/business/templates').then((d) => setBusinessTemplates(d.templates || [])).catch(() => setBusinessTemplates([]))
  }, [])

  const flatSkills = useMemo(() => packs.flatMap((pack) => pack.skills || []), [packs])

  async function useTemplate(template) {
    try {
      const data = await request(`/api/workflows/templates/${encodeURIComponent(template.id)}/instantiate`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: template.name, owner: 'main_ai_orchestrator' }),
      })
      toastSuccess('Workflow draft created')
      setSelected(data.workflow)
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  async function runWorkflow(id) {
    try {
      await request(`/api/workflows/${encodeURIComponent(id)}/run`, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({}) })
      toastSuccess('Workflow run queued through main AI')
      const d = await request('/api/workflows/runs')
      setRuns(d.runs || [])
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="wf-page">
      <div className="wf-header">
        <div className="wf-header__left">
          <span className="wf-header__title">WORKFLOWS</span>
          <span className="wf-header__sub">Main AI workflow orchestration. AscendForge is code/build only.</span>
        </div>
        <div className="wf-header__tabs">
          {tabs.map(([id, label]) => (
            <button key={id} className={`wf-tab ${activeTab === id ? 'wf-tab--active' : ''}`} onClick={() => setActiveTab(id)}>
              {label}
            </button>
          ))}
        </div>
        <div className="wf-header__right">
          <span className="wf-header__count">{workflows.length} workflows</span>
        </div>
      </div>

      <div className="wf-body">
        {loading && <EmptyState icon="..." title="Loading workflow registry" />}
        {error && <ErrorState title="Workflow registry degraded" message={error} />}
        {!loading && !error && activeTab === 'canvas' && (
          <>
            <WorkflowCanvas
              workflows={workflows}
              runs={runs}
              onSelect={setSelected}
              onCreate={() => setActiveTab('builder')}
              onSetup={() => setActiveSection('setup')}
            />
            <WorkflowDetail item={selected} onRun={runWorkflow} />
          </>
        )}
        {activeTab === 'roadmap' && <RoadmapPanel />}
        {activeTab === 'templates' && <div className="wf-templates"><TemplatesPanel templates={templates} onUse={useTemplate} onCreate={() => setActiveTab('builder')} /></div>}
        {activeTab === 'skills' && <div className="wf-templates"><SkillPacksPanel packs={packs} onSetup={() => setActiveSection('setup')} /></div>}
        {activeTab === 'finance' && <div className="wf-templates"><FinancePanel workflows={finance} onEconomy={() => setActiveSection('economy')} /></div>}
        {activeTab === 'business' && <BusinessPanel templates={businessTemplates} />}
        {activeTab === 'builder' && <div className="wf-templates"><BuilderPanel skills={flatSkills} onCreated={refresh} /></div>}
      </div>
    </div>
  )
}
