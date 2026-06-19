import { useEffect, useMemo, useState } from 'react'
import { Panel, SectionLabel, StatusPill, EmptyState, ErrorState, NxButton } from '../nexus-ui'
import { useLiveData } from '../../hooks/useLiveData'
import { useAppStore } from '../../store/appStore'
import { useForgeStore } from '../../store/forgeStore'
import { toastSuccess, toastError, toastWarn } from '../nexus-ui/Toaster'
import { fmtDate } from '../../utils/format'
import './OperationsPage.css'

const TASK_API = '/api/tasks'
const SCHEDULE_API = '/api/schedules'

const COLUMNS = [
  { id: 'incoming', label: 'INCOMING', color: '#60a5fa' },
  { id: 'planning', label: 'PLANNING', color: '#a855f7' },
  { id: 'executing', label: 'EXECUTING', color: '#f59e0b' },
  { id: 'validating', label: 'VALIDATING', color: '#22d3ee' },
  { id: 'completed', label: 'COMPLETED', color: '#22c55e' },
  { id: 'failed', label: 'FAILED', color: 'var(--nx-danger)' },
]

const tabs = [
  ['board', 'Board'],
  ['live', 'Live Progress'],
  ['list', 'List'],
  ['create', 'Create Task'],
  ['scheduler', 'Scheduler'],
  ['history', 'History'],
]

// elapsed_s is in seconds; fmtDuration in utils expects ms — keep local adapter
function fmtDuration(s = 0) {
  const v = Number(s) || 0
  if (v < 60) return `${v}s`
  if (v < 3600) return `${Math.floor(v / 60)}m ${Math.floor(v % 60)}s`
  return `${Math.floor(v / 3600)}h ${Math.floor((v % 3600) / 60)}m`
}

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('ai_jwt')
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || data.message || `${res.status} ${res.statusText}`)
  return data
}

function TaskCard({ task, onInspect, onRefresh }) {
  async function cancelTask() {
    try {
      await api(`${TASK_API}/${encodeURIComponent(task.id)}/cancel`, { method: 'POST', headers: authHeaders() })
      toastWarn(`Cancelled ${task.title}`)
      onRefresh()
    } catch (e) {
      toastError(e.message)
    }
  }

  async function retryTask() {
    try {
      await api(`${TASK_API}/${encodeURIComponent(task.id)}/retry`, { method: 'POST', headers: authHeaders() })
      toastSuccess(`Retry queued for ${task.title}`)
      onRefresh()
    } catch (e) {
      toastError(e.message)
    }
  }

  return (
    <div className={`ops-card ${task.status === 'failed' ? 'ops-card--failed' : ''}`}>
      <div className="ops-card__title">{task.title || task.intent || task.id}</div>
      <div className="ops-card__agent">{task.agent || task.owner || 'main-ai'}</div>
      {task.progress > 0 && task.progress < 100 && (
        <div className="ops-card__progress-wrap">
          <div className="ops-card__progress-bar" style={{ width: `${task.progress}%` }} />
        </div>
      )}
      <div className="ops-card__meta">
        <span>{fmtDuration(task.elapsed_s)}</span>
        <div className="ops-card__actions">
          {!['completed', 'failed', 'cancelled'].includes(task.status) && (
            <NxButton variant="ghost" size="sm" onClick={cancelTask}>Cancel</NxButton>
          )}
          {task.status === 'failed' && <NxButton variant="warn" size="sm" onClick={retryTask}>Retry</NxButton>}
          <NxButton variant="ghost" size="sm" onClick={() => onInspect(task)}>Inspect</NxButton>
        </div>
      </div>
    </div>
  )
}

function GuidedTaskEmpty({ onCreate, onSetup, onProof }) {
  return (
    <div className="ops-guided-empty">
      <EmptyState
        icon="⬡"
        title="No live tasks"
        sub="Run a safe task to verify the canonical execution path, or check setup if the gateway is not ready."
        action="Create Task"
        onAction={onCreate}
      />
      <div className="ops-guided-empty__actions" aria-label="Task setup actions">
        <NxButton variant="primary" onClick={onCreate}>Create Task</NxButton>
        <NxButton variant="ghost" onClick={onSetup}>Run Setup Check</NxButton>
        <NxButton variant="ghost" onClick={onProof}>View Proof Center</NxButton>
      </div>
    </div>
  )
}

function Board({ tasks, onInspect, onRefresh, onCreate, onSetup, onProof }) {
  if (!tasks.length) {
    return <GuidedTaskEmpty onCreate={onCreate} onSetup={onSetup} onProof={onProof} />
  }
  return (
    <div className="ops-kanban">
      {COLUMNS.map((col) => {
        const colTasks = tasks.filter((task) => task.status === col.id)
        return (
          <div key={col.id} className={`ops-col ${col.id === 'failed' ? 'ops-col--failed' : ''}`}>
            <div className="ops-col__head" style={{ borderTopColor: col.color }}>
              <span className="ops-col__label" style={{ color: col.color }}>{col.label}</span>
              <span className="ops-col__count">{colTasks.length}</span>
            </div>
            <div className="ops-col__cards">
              {colTasks.length === 0 && <div className="ops-col__empty">empty</div>}
              {colTasks.map((task) => (
                <TaskCard key={task.id} task={task} onInspect={onInspect} onRefresh={onRefresh} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TaskTable({ tasks, onInspect, onCreate }) {
  if (!tasks.length) {
    return (
      <EmptyState
        icon="◈"
        title="No task rows"
        sub="The task gateway has no records yet. Run a first task to create visible trace and proof output."
        action="Create Task"
        onAction={onCreate}
      />
    )
  }
  return (
    <Panel title="Task List">
      <div className="ops-sched-head">
        <span>Task</span><span>Agent</span><span>Status</span><span>Priority</span><span>Updated</span><span>Actions</span>
      </div>
      {tasks.map((task) => (
        <div key={task.id} className="ops-sched-row">
          <span className="ops-sched-name">{task.title || task.intent || task.id}</span>
          <span>{task.agent || task.owner || 'main-ai'}</span>
          <StatusPill label={(task.status || 'unknown').toUpperCase()} tone={task.status === 'failed' ? 'alert' : task.status === 'completed' ? 'success' : 'idle'} size="sm" />
          <span>{task.priority ?? '-'}</span>
          <span>{fmtDate(task.updated_at, { time: true })}</span>
          <NxButton variant="ghost" size="sm" onClick={() => onInspect(task)}>Inspect</NxButton>
        </div>
      ))}
    </Panel>
  )
}

function CreateTask({ onCreated }) {
  const [form, setForm] = useState({ intent: '', description: '', priority: 1 })
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    if (!form.intent.trim() || !form.description.trim()) return
    setBusy(true)
    try {
      await api(`${TASK_API}/queue`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(form),
      })
      toastSuccess('Task queued through the main AI task gateway')
      setForm({ intent: '', description: '', priority: 1 })
      onCreated()
    } catch (e) {
      toastError(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Panel title="Create Main AI Task">
      <form className="ops-create-form" onSubmit={submit}>
        <input className="ops-input" placeholder="Intent" value={form.intent} onChange={(e) => setForm({ ...form, intent: e.target.value })} />
        <textarea className="ops-input" rows={4} placeholder="Goal, constraints, expected output" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <input className="ops-input" type="number" min="0" max="3" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} />
        <NxButton variant="primary" type="submit" loading={busy} disabled={busy}>Queue Task</NxButton>
      </form>
    </Panel>
  )
}

function Scheduler() {
  const { data, loading, error, refresh } = useLiveData({
    endpoint: SCHEDULE_API,
    wsEvent: 'schedule:update',
    pollMs: 10000,
    transform: (d) => d.schedules || [],
  })
  const schedules = data || []
  const [form, setForm] = useState({ name: '', cron: '0 9 * * *', agent: 'main-ai', task: '' })

  async function createSchedule(e) {
    e.preventDefault()
    try {
      await api(SCHEDULE_API, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(form),
      })
      toastSuccess('Schedule created')
      setForm({ name: '', cron: '0 9 * * *', agent: 'main-ai', task: '' })
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  async function scheduleAction(id, action) {
    try {
      await api(`${SCHEDULE_API}/${encodeURIComponent(id)}/${action}`, { method: 'POST', headers: authHeaders() })
      toastSuccess(`Schedule ${action} accepted`)
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  async function deleteSchedule(id) {
    try {
      await api(`${SCHEDULE_API}/${encodeURIComponent(id)}`, { method: 'DELETE', headers: authHeaders() })
      toastSuccess('Schedule deleted')
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="ops-scheduler">
      <Panel title="Create Schedule">
        <form className="ops-create-form" onSubmit={createSchedule}>
          <input className="ops-input" placeholder="Schedule name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="ops-input ops-input--mono" placeholder="Cron" value={form.cron} onChange={(e) => setForm({ ...form, cron: e.target.value })} />
          <input className="ops-input" placeholder="Agent" value={form.agent} onChange={(e) => setForm({ ...form, agent: e.target.value })} />
          <input className="ops-input" placeholder="Task goal" value={form.task} onChange={(e) => setForm({ ...form, task: e.target.value })} />
          <NxButton variant="primary" type="submit">Save Schedule</NxButton>
        </form>
      </Panel>
      <Panel title="Scheduled Tasks">
        {loading && <EmptyState icon="…" title="Loading schedules" />}
        {error && <ErrorState title="Scheduler degraded" message={error} />}
        {!loading && !error && !schedules.length && <EmptyState icon="◷" title="No schedules" sub="Recurring tasks will appear here once created." />}
        {!!schedules.length && (
          <>
            <div className="ops-sched-head">
              <span>Name</span><span>Agent</span><span>Cron</span><span>Status</span><span>Last run</span><span>Actions</span>
            </div>
            {schedules.map((job) => (
              <div key={job.id} className={`ops-sched-row ${job.paused ? 'ops-sched-row--paused' : ''}`}>
                <span className="ops-sched-name">{job.name}</span>
                <span>{job.agent}</span>
                <code className="ops-sched-cron">{job.cron}</code>
                <StatusPill label={job.paused ? 'PAUSED' : 'ACTIVE'} tone={job.paused ? 'idle' : 'success'} size="sm" />
                <span>{fmtDate(job.last_run_at, { time: true })}</span>
                <div className="ops-sched-actions">
                  <NxButton variant="ghost" size="sm" onClick={() => scheduleAction(job.id, 'run')}>Run</NxButton>
                  <NxButton variant="ghost" size="sm" onClick={() => scheduleAction(job.id, job.paused ? 'resume' : 'pause')}>{job.paused ? 'Resume' : 'Pause'}</NxButton>
                  <NxButton variant="danger" size="sm" onClick={() => deleteSchedule(job.id)}>Del</NxButton>
                </div>
              </div>
            ))}
          </>
        )}
      </Panel>
    </div>
  )
}

function InspectModal({ task, onClose, onOpenForge, relatedRuns }) {
  if (!task) return null
  return (
    <div className="ops-modal-overlay" onClick={onClose}>
      <div className="ops-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ops-modal__head">
          <span>Task Inspection - {task.id}</span>
          <button className="ops-modal__close" onClick={onClose}>x</button>
        </div>
        <div className="ops-modal__body">
          {[
            ['Title', task.title || task.intent],
            ['Agent', task.agent || task.owner || 'main-ai'],
            ['Status', task.status],
            ['Progress', `${task.progress || 0}%`],
            ['Approval', task.approval_state || 'not_required'],
            ['Created', fmtDate(task.created_at, { time: true })],
            ['Updated', fmtDate(task.updated_at, { time: true })],
          ].map(([key, value]) => (
            <div key={key} className="ops-modal__row">
              <span className="ops-modal__key">{key}</span>
              <span className="ops-modal__val">{value || '-'}</span>
            </div>
          ))}
          {!!task.trace?.length && (
            <div className="ops-modal__row">
              <span className="ops-modal__key">Trace</span>
              <span className="ops-modal__val">{task.trace.length} event(s)</span>
            </div>
          )}
          {!!relatedRuns?.length && (
            <div className="ops-modal__row">
              <span className="ops-modal__key">Forge</span>
              <span className="ops-modal__val">
                {relatedRuns.slice(0, 3).map(run => (
                  <button key={run.run_id || run.id} className="ops-link-btn" type="button" onClick={() => onOpenForge(run)}>
                    {run.run_id || run.id} · {run.status}
                  </button>
                ))}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Live Progress Panel ───────────────────────────────────────────────────────
// Lazy-loads TaskProgressBlock to avoid pulling framer-motion into the initial bundle.
function LiveProgressPanel({ tasks }) {
  const [Block, setBlock] = useState(null)
  useEffect(() => {
    import('../ui/TaskProgressBlock').then(m => setBlock(() => m.default)).catch(() => {})
  }, [])

  const running = (tasks || []).filter(t => {
    const s = (t.status || '').toLowerCase()
    return s === 'running' || s === 'in_progress' || s === 'active'
  })

  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto', flex: 1 }}>
      <div style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--nx-gold,#e5c76b)', fontFamily: 'monospace', textTransform: 'uppercase', marginBottom: 4 }}>
        Live Task Progress · {running.length} running
      </div>
      {running.length === 0 && (
        <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12, fontFamily: 'monospace', padding: '20px 0' }}>
          No tasks currently running — start a task from the Board tab
        </div>
      )}
      {Block && running.map(task => (
        <Block
          key={task.id}
          taskId={task.id}
          title={task.intent || task.title || task.description || task.id}
          steps={task.steps || []}
        />
      ))}
      {!Block && running.length > 0 && (
        <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, fontFamily: 'monospace' }}>Loading…</div>
      )}
    </div>
  )
}

export default function OperationsPage() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const forgeRuns = useForgeStore(s => s.runs)
  const forgeActiveRun = useForgeStore(s => s.activeRun)
  const forgeSelectRun = useForgeStore(s => s.selectRun)
  const [tab, setTab] = useState('board')
  const [inspecting, setInspecting] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [goal, setGoal] = useState('')
  const [mode, setMode] = useState('auto')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const { data, loading, error, refresh } = useLiveData({
    endpoint: '/api/tasks/list',
    wsEvent: 'task:update',
    pollMs: 15000,
    transform: (d) => d.tasks || [],
  })

  const tasks = data || []
  const history = useMemo(() => tasks.filter((task) => ['completed', 'failed', 'cancelled'].includes(task.status)), [tasks])
  const relatedForgeRuns = useMemo(() => {
    if (!inspecting) return []
    const id = inspecting.id || inspecting.task_id || inspecting.turn_id
    const matches = (forgeRuns || []).filter(run => run.task_id === id || run.linked_backlog_id === id || run.goal === inspecting.title || run.goal === inspecting.intent)
    if (matches.length) return matches
    return forgeActiveRun ? [forgeActiveRun] : []
  }, [inspecting, forgeRuns, forgeActiveRun])

  async function submitTask() {
    setSubmitting(true); setSubmitError('')
    try {
      await fetch('/api/tasks/run', {
        method: 'POST',
        credentials: 'include',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ goal, mode, source: 'dashboard' }),
      })
      toastSuccess('Task submitted')
      setGoal(''); setMode('auto'); setShowForm(false)
      refresh()
    } catch (e) {
      setSubmitError('Failed: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }
  function openCreateTask() {
    setTab('create')
    setShowForm(false)
  }

  const completed = tasks.filter((task) => task.status === 'completed').length
  const queued = tasks.filter((task) => ['incoming', 'planning', 'pending'].includes(task.status)).length
  const failed = tasks.filter((task) => task.status === 'failed').length

  return (
    <div className="ops-page">
      <div className="ops-header">
        <div>
          <span className="ops-header__title">MISSION CONTROL</span>
          <SectionLabel>Main AI owns tasks, workflows, schedules, memory and economy. AscendForge only stages approved code/build artifacts.</SectionLabel>
        </div>
        <div className="ops-header__tabs">
          {tabs.map(([id, label]) => (
            <button key={id} className={`ops-tab-btn ${tab === id ? 'ops-tab-btn--active' : ''}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
        <div className="ops-header__actions">
          <NxButton variant="primary" onClick={() => setShowForm(v => !v)}>+ NEW TASK</NxButton>
          <NxButton variant="ghost" size="sm" onClick={refresh}>Refresh</NxButton>
        </div>
      </div>

      {showForm && (
        <div className="ops-task-form">
          <div className="ops-form-row">
            <label>Goal</label>
            <input
              className="ops-input"
              placeholder="Describe what the AI should do..."
              value={goal}
              onChange={e => setGoal(e.target.value)}
            />
          </div>
          <div className="ops-form-row">
            <label>Mode</label>
            <select className="ops-select" value={mode} onChange={e => setMode(e.target.value)}>
              <option value="auto">Auto (AI picks best agent)</option>
              <option value="research">Research</option>
              <option value="coding">Coding</option>
              <option value="analytics">Analytics</option>
              <option value="content">Content</option>
              <option value="sales">Sales</option>
            </select>
          </div>
          <div className="ops-form-actions">
            <NxButton variant="primary" onClick={submitTask} loading={submitting} disabled={!goal.trim() || submitting}>Run Task</NxButton>
            <NxButton variant="ghost" onClick={() => setShowForm(false)}>Cancel</NxButton>
          </div>
          {submitError && <div className="ops-form-error">{submitError}</div>}
        </div>
      )}

      <div className="ops-sla-gauges">
        {[
          ['Total Tasks', tasks.length, 'var(--nx-gold)'],
          ['Completed', completed, 'var(--nx-success)'],
          ['Queued', queued, 'var(--nx-cyan)'],
          ['Failed', failed, 'var(--nx-danger)'],
        ].map(([label, value, color]) => (
          <div key={label} className="ops-sla-gauge">
            <div className="ops-sla-gauge__val" style={{ color }}>{value}</div>
            <div className="ops-sla-gauge__label">{label}</div>
          </div>
        ))}
      </div>

      {loading && <EmptyState icon="…" title="Loading task gateway" />}
      {error && <ErrorState title="Task gateway degraded" message={error} />}
      {!loading && !error && tab === 'board' && (
        <Board
          tasks={tasks}
          onInspect={setInspecting}
          onRefresh={refresh}
          onCreate={openCreateTask}
          onSetup={() => setActiveSection('setup')}
          onProof={() => setActiveSection('proof')}
        />
      )}
      {tab === 'live' && <LiveProgressPanel tasks={tasks} />}
      {!loading && !error && tab === 'list' && <TaskTable tasks={tasks} onInspect={setInspecting} onCreate={openCreateTask} />}
      {tab === 'create' && <CreateTask onCreated={refresh} />}
      {tab === 'scheduler' && <Scheduler />}
      {!loading && !error && tab === 'history' && <TaskTable tasks={history} onInspect={setInspecting} onCreate={openCreateTask} />}

      <InspectModal
        task={inspecting}
        onClose={() => setInspecting(null)}
        relatedRuns={relatedForgeRuns}
        onOpenForge={(run) => {
          const runId = run?.run_id || run?.id
          if (runId) forgeSelectRun(runId)
          setActiveSection('ascend-forge')
        }}
      />
    </div>
  )
}
