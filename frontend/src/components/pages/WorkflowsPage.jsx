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

// ── N8N-style visual workflow builder ────────────────────────────────────────

const NODE_TYPES = [
  { type: 'trigger.manual',   label: 'Manual Trigger',  color: '#00D4FF', icon: '▶' },
  { type: 'trigger.schedule', label: 'Schedule',         color: '#00D4FF', icon: '⏱' },
  { type: 'trigger.webhook',  label: 'Webhook',          color: '#00D4FF', icon: '🔗' },
  { type: 'action.agent',     label: 'Agent Task',       color: '#E5C76B', icon: '🤖' },
  { type: 'action.llm',       label: 'LLM Call',         color: '#A855F7', icon: '💬' },
  { type: 'action.http',      label: 'HTTP Request',     color: '#6366F1', icon: '🌐' },
  { type: 'action.memory',    label: 'Memory Write',     color: '#10B981', icon: '🧠' },
  { type: 'logic.if',         label: 'IF / ELSE',        color: '#F59E0B', icon: '⚡' },
  { type: 'logic.wait',       label: 'Wait / Delay',     color: '#64748B', icon: '⏳' },
  { type: 'output.vault',     label: 'Save to Vault',    color: '#10B981', icon: '💾' },
  { type: 'output.report',    label: 'Generate Report',  color: '#06B6D4', icon: '📄' },
  { type: 'hitl.approval',    label: 'HITL Approval',    color: '#EF4444', icon: '👁' },
]

function nodeColor(type) { return NODE_TYPES.find(n => n.type === type)?.color || '#888' }
function nodeIcon(type)  { return NODE_TYPES.find(n => n.type === type)?.icon  || '◈'  }

function WFNode({ node, selected, onSelect, onDragStart }) {
  const col = nodeColor(node.type)
  return (
    <div
      draggable
      onDragStart={e => onDragStart(e, node.id)}
      onClick={() => onSelect(node.id)}
      style={{
        position: 'absolute',
        left: node.x, top: node.y,
        width: 160, minHeight: 52,
        background: selected ? 'rgba(20,20,30,0.97)' : 'rgba(10,10,20,0.92)',
        border: `1.5px solid ${selected ? col : 'rgba(255,255,255,0.12)'}`,
        borderRadius: 8,
        padding: '8px 12px',
        cursor: 'grab',
        userSelect: 'none',
        boxShadow: selected ? `0 0 12px ${col}55` : '0 2px 8px rgba(0,0,0,0.4)',
        zIndex: selected ? 10 : 1,
        fontFamily: 'var(--nx-font-mono, monospace)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 14 }}>{nodeIcon(node.type)}</span>
        <span style={{ fontSize: 10, color: col, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
          {node.type.split('.')[0]}
        </span>
      </div>
      <div style={{ fontSize: 12, color: '#e8e8e8', fontWeight: 500 }}>{node.label}</div>
      {/* Output port */}
      <div style={{
        position: 'absolute', right: -7, top: '50%', transform: 'translateY(-50%)',
        width: 13, height: 13, borderRadius: '50%',
        background: col, border: '2px solid #0a0a14', cursor: 'crosshair',
      }} data-port="out" data-node={node.id} />
      {/* Input port */}
      <div style={{
        position: 'absolute', left: -7, top: '50%', transform: 'translateY(-50%)',
        width: 13, height: 13, borderRadius: '50%',
        background: '#1a1a2e', border: `2px solid ${col}`, cursor: 'crosshair',
      }} data-port="in" data-node={node.id} />
    </div>
  )
}

function WFEdges({ nodes, edges }) {
  const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))
  return (
    <svg style={{ position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none' }}>
      {edges.map((e, i) => {
        const from = nodeMap[e.from]; const to = nodeMap[e.to]
        if (!from || !to) return null
        const x1 = from.x + 160, y1 = from.y + 26
        const x2 = to.x,         y2 = to.y + 26
        const mx = (x1 + x2) / 2
        return (
          <path key={i}
            d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
            stroke={nodeColor(from.type)} strokeWidth="2" fill="none" opacity="0.7"
            strokeDasharray="none"
          />
        )
      })}
    </svg>
  )
}

function BuilderPanel({ skills, onCreated }) {
  const [nodes, setNodes] = useState([
    { id: 'n1', type: 'trigger.manual', label: 'Start', x: 60,  y: 80 },
    { id: 'n2', type: 'action.agent',   label: 'Agent Task', x: 280, y: 80 },
    { id: 'n3', type: 'hitl.approval',  label: 'HITL Approval', x: 500, y: 80 },
  ])
  const [edges, setEdges] = useState([
    { from: 'n1', to: 'n2' },
    { from: 'n2', to: 'n3' },
  ])
  const [selected, setSelected] = useState(null)
  const [wfName, setWfName] = useState('My Workflow')
  const [dragging, setDragging] = useState(null)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [connecting, setConnecting] = useState(null) // nodeId being connected from
  const canvasRef = useRef(null)

  const selectedNode = nodes.find(n => n.id === selected)

  const addNode = (type) => {
    const id = `n${Date.now()}`
    setNodes(prev => [...prev, { id, type, label: NODE_TYPES.find(n => n.type === type)?.label || type, x: 120 + prev.length * 50, y: 120 + (prev.length % 3) * 80 }])
  }

  const updateSelected = (key, val) => {
    setNodes(prev => prev.map(n => n.id === selected ? { ...n, [key]: val } : n))
  }

  const deleteSelected = () => {
    setEdges(prev => prev.filter(e => e.from !== selected && e.to !== selected))
    setNodes(prev => prev.filter(n => n.id !== selected))
    setSelected(null)
  }

  const handleCanvasMouseMove = (e) => {
    if (!dragging) return
    const rect = canvasRef.current.getBoundingClientRect()
    setNodes(prev => prev.map(n => n.id === dragging
      ? { ...n, x: Math.max(0, e.clientX - rect.left - dragOffset.x), y: Math.max(0, e.clientY - rect.top - dragOffset.y) }
      : n))
  }

  const saveWorkflow = async () => {
    try {
      await request('/api/workflows', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: wfName, trigger: nodes[0]?.type || 'trigger.manual',
          owner: 'main_ai_orchestrator',
          graph: { nodes, edges },
          steps: nodes.map(n => ({ id: n.id, label: n.label, type: n.type })),
          approval_policy: nodes.some(n => n.type === 'hitl.approval') ? 'owner_approval_required' : 'auto',
        }),
      })
      toastSuccess('Workflow saved')
      onCreated()
    } catch (err) { toastError(err.message) }
  }

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 520, fontFamily: 'var(--nx-font-mono, monospace)' }}>
      {/* Left: node palette */}
      <div style={{ width: 180, background: 'rgba(5,5,15,0.8)', borderRight: '1px solid rgba(255,255,255,0.07)', padding: '12px 8px', overflowY: 'auto', flexShrink: 0 }}>
        <div style={{ fontSize: 10, color: 'rgba(229,199,107,0.6)', letterSpacing: 2, marginBottom: 10 }}>NODE PALETTE</div>
        {NODE_TYPES.map(nt => (
          <button key={nt.type} onClick={() => addNode(nt.type)} style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%',
            background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 6, padding: '6px 8px', marginBottom: 4, cursor: 'pointer',
            color: '#c8c8d8', fontSize: 11, textAlign: 'left',
          }}>
            <span style={{ fontSize: 13 }}>{nt.icon}</span>
            <span>{nt.label}</span>
          </button>
        ))}
      </div>

      {/* Center: canvas */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'rgba(5,5,15,0.9)', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <input value={wfName} onChange={e => setWfName(e.target.value)}
            style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: '#e5c76b', fontFamily: 'inherit', fontSize: 13, padding: '3px 8px', width: 200 }} />
          <button onClick={saveWorkflow} style={{ background: 'rgba(229,199,107,0.15)', border: '1px solid rgba(229,199,107,0.4)', borderRadius: 4, color: '#e5c76b', padding: '4px 14px', cursor: 'pointer', fontSize: 12 }}>
            💾 SAVE
          </button>
          <button onClick={() => { setNodes([]); setEdges([]); setSelected(null) }}
            style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: '#888', padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}>
            CLEAR
          </button>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'rgba(255,255,255,0.3)' }}>
            {nodes.length} nodes · {edges.length} connections — drag nodes to reposition · click palette to add
          </span>
        </div>

        {/* Canvas */}
        <div
          ref={canvasRef}
          style={{ flex: 1, position: 'relative', overflow: 'hidden', background: 'radial-gradient(ellipse at 50% 50%, rgba(229,199,107,0.03) 0%, transparent 70%), repeating-linear-gradient(rgba(255,255,255,0.02) 0 1px, transparent 1px 40px), repeating-linear-gradient(90deg, rgba(255,255,255,0.02) 0 1px, transparent 1px 40px)', backgroundSize: '100% 40px, 40px 40px, 40px 40px', cursor: dragging ? 'grabbing' : 'default' }}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={() => setDragging(null)}
          onClick={e => { if (e.target === canvasRef.current) setSelected(null) }}
        >
          <WFEdges nodes={nodes} edges={edges} />
          {nodes.map(node => (
            <WFNode key={node.id} node={node} selected={node.id === selected}
              onSelect={setSelected}
              onDragStart={(e, id) => {
                const rect = canvasRef.current.getBoundingClientRect()
                const n = nodes.find(x => x.id === id)
                setDragOffset({ x: e.clientX - rect.left - n.x, y: e.clientY - rect.top - n.y })
                setDragging(id)
                e.dataTransfer.setData('text/plain', id)
              }}
            />
          ))}
          {nodes.length === 0 && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.15)', fontSize: 13 }}>
              ← Add nodes from the palette to start building
            </div>
          )}
        </div>
      </div>

      {/* Right: properties panel */}
      <div style={{ width: 220, background: 'rgba(5,5,15,0.8)', borderLeft: '1px solid rgba(255,255,255,0.07)', padding: 12, overflowY: 'auto', flexShrink: 0 }}>
        <div style={{ fontSize: 10, color: 'rgba(229,199,107,0.6)', letterSpacing: 2, marginBottom: 10 }}>PROPERTIES</div>
        {selectedNode ? (
          <>
            <div style={{ fontSize: 11, color: nodeColor(selectedNode.type), marginBottom: 8 }}>{nodeIcon(selectedNode.type)} {selectedNode.type}</div>
            <label style={{ fontSize: 10, color: '#888', display: 'block', marginBottom: 4 }}>LABEL</label>
            <input value={selectedNode.label} onChange={e => updateSelected('label', e.target.value)}
              style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: '#e8e8e8', fontFamily: 'inherit', fontSize: 12, padding: '4px 8px', marginBottom: 10, boxSizing: 'border-box' }} />
            {selectedNode.type === 'action.agent' && (
              <>
                <label style={{ fontSize: 10, color: '#888', display: 'block', marginBottom: 4 }}>AGENT</label>
                <input value={selectedNode.agent || ''} onChange={e => updateSelected('agent', e.target.value)}
                  placeholder="e.g. lead-hunter-elite"
                  style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: '#e8e8e8', fontFamily: 'inherit', fontSize: 11, padding: '4px 8px', marginBottom: 10, boxSizing: 'border-box' }} />
              </>
            )}
            {selectedNode.type === 'trigger.schedule' && (
              <>
                <label style={{ fontSize: 10, color: '#888', display: 'block', marginBottom: 4 }}>CRON</label>
                <input value={selectedNode.cron || '0 9 * * 1'} onChange={e => updateSelected('cron', e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: '#e8e8e8', fontFamily: 'inherit', fontSize: 11, padding: '4px 8px', marginBottom: 10, boxSizing: 'border-box' }} />
              </>
            )}
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.07)', display: 'flex', gap: 6, flexDirection: 'column' }}>
              <button onClick={() => {
                const fromId = selectedNode.id
                const otherNodes = nodes.filter(n => n.id !== fromId)
                if (otherNodes.length) {
                  const target = otherNodes[otherNodes.length - 1]
                  if (!edges.find(e => e.from === fromId && e.to === target.id)) {
                    setEdges(prev => [...prev, { from: fromId, to: target.id }])
                  }
                }
              }} style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.4)', borderRadius: 4, color: '#818cf8', padding: '4px 8px', cursor: 'pointer', fontSize: 11 }}>
                → Connect to last node
              </button>
              <button onClick={deleteSelected}
                style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 4, color: '#f87171', padding: '4px 8px', cursor: 'pointer', fontSize: 11 }}>
                🗑 Delete node
              </button>
            </div>
          </>
        ) : (
          <div style={{ color: 'rgba(255,255,255,0.2)', fontSize: 12 }}>Click a node to edit its properties</div>
        )}
        <div style={{ marginTop: 20, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ fontSize: 10, color: 'rgba(229,199,107,0.4)', letterSpacing: 1, marginBottom: 8 }}>FLOW SUMMARY</div>
          {nodes.map(n => (
            <div key={n.id} style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span>{nodeIcon(n.type)}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
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
      const result = await request(`/api/workflows/${encodeURIComponent(id)}/run`, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({}) })
      const state = result?.run?.state || result?.run?.status || result?.workflow?.state || result?.status || 'submitted'
      toastSuccess(`Workflow ${String(state).replace(/_/g, ' ')}`)
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
