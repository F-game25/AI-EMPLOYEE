/* NEXUS OS Mobile — Tasks Screen */
import { useState, useEffect, useCallback } from 'react'
import { Section, TaskCard, StatusPill, Empty, Spinner, Sheet, Row, ProgressBar } from '../MobileUI'
import api from '../../../api/client'

const MOCK_TASKS = [
  { id: '1', name: 'Market Research', goal: 'Analyze competitor landscape', status: 'running', progress: 65, assigned_to: 'research' },
  { id: '2', name: 'Content Generation', goal: 'Write blog post', status: 'completed', progress: 100, assigned_to: 'content' },
  { id: '3', name: 'Lead Qualification', goal: 'Score new leads', status: 'pending', progress: 0 },
  { id: '4', name: 'Data Analysis', goal: 'Weekly metrics report', status: 'failed', progress: 30, error: 'Timeout' },
]

export default function MobileTasks() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    try {
      const r = await api.get('/api/tasks')
      setTasks(Array.isArray(r) ? r : r?.tasks || MOCK_TASKS)
    } catch { setTasks(MOCK_TASKS) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filters = [
    { id: 'all', label: 'All' },
    { id: 'running', label: 'Running' },
    { id: 'pending', label: 'Pending' },
    { id: 'completed', label: 'Done' },
    { id: 'failed', label: 'Failed' },
  ]

  const filtered = filter === 'all' ? tasks : tasks.filter(t => t.status === filter)
  const counts = { running: 0, pending: 0, completed: 0, failed: 0 }
  tasks.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++ })

  return (
    <div style={S.screen}>
      <div style={S.statsRow}>
        {Object.entries(counts).map(([k, v]) => (
          <div key={k} style={S.stat}>
            <div style={{ ...S.statVal, color: k === 'failed' ? 'var(--error)' : k === 'completed' ? 'var(--success)' : 'var(--gold)' }}>{v}</div>
            <div style={S.statLbl}>{k}</div>
          </div>
        ))}
      </div>

      <div style={S.filterRow}>
        {filters.map(f => (
          <button key={f.id} style={{ ...S.filterBtn, ...(filter === f.id ? S.filterActive : {}) }}
            onClick={() => setFilter(f.id)}>{f.label}</button>
        ))}
      </div>

      <div style={S.scroll}>
        {loading ? (
          <div style={S.center}><Spinner /></div>
        ) : filtered.length === 0 ? (
          <Empty icon="◇" message={`No ${filter} tasks`} />
        ) : (
          <Section>
            {filtered.map(t => <TaskCard key={t.id} task={t} onClick={() => setSelected(t)} />)}
          </Section>
        )}
      </div>

      <Sheet open={!!selected} onClose={() => setSelected(null)} title="Task Detail">
        {selected && <TaskDetail task={selected} />}
      </Sheet>
    </div>
  )
}

function TaskDetail({ task }) {
  const tone = task.status === 'completed' ? 'ok' : task.status === 'failed' ? 'error' : 'idle'
  const color = task.status === 'completed' ? 'var(--success)' : task.status === 'failed' ? 'var(--error)' : 'var(--gold)'
  return (
    <div>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{task.name || task.goal}</span>
          <StatusPill label={task.status} tone={tone} />
        </div>
        <ProgressBar value={task.progress ?? 0} color={color} height={4} />
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>{task.progress ?? 0}% complete</div>
      </div>
      <Row label="ID" value={task.id} />
      {task.goal && <Row label="Goal" value={task.goal} />}
      {task.assigned_to && <Row label="Agent" value={task.assigned_to} />}
      {task.error && <Row label="Error" value={task.error} />}
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 16 },
  center: { display: 'flex', justifyContent: 'center', padding: 40 },
  statsRow: { display: 'flex', borderBottom: '1px solid var(--border-subtle)' },
  stat: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '10px 4px' },
  statVal: { fontSize: 18, fontWeight: 700, fontFamily: 'var(--nx-font-mono, monospace)' },
  statLbl: { fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' },
  filterRow: { display: 'flex', gap: 6, padding: '8px 16px', borderBottom: '1px solid var(--border-subtle)', overflowX: 'auto', scrollbarWidth: 'none' },
  filterBtn: { flexShrink: 0, padding: '4px 12px', borderRadius: 16, border: '1px solid var(--border-subtle)',
    background: 'none', color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer' },
  filterActive: { background: 'rgba(229,199,107,0.12)', color: 'var(--gold)', borderColor: 'rgba(229,199,107,0.3)' },
}
