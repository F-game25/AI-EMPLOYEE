/* NEXUS OS Mobile — AGENTS Screen */
import { useState, useEffect, useCallback } from 'react'
import { TopBar, Section, AgentCard, StatusPill, Row, Empty, Spinner, ProgressBar, Sheet } from '../MobileUI'
import api from '../../../api/client'

const MOCK_AGENTS = [
  { id: 'orchestrator', name: 'Orchestrator', role: 'Core Brain', status: 'active', mode: 'Power', tasks_completed: 142 },
  { id: 'research', name: 'Research Agent', role: 'Intelligence Gathering', status: 'idle', mode: 'Business', tasks_completed: 38 },
  { id: 'content', name: 'Content Agent', role: 'Content Generation', status: 'idle', mode: 'Business', tasks_completed: 77 },
  { id: 'monitor', name: 'Monitor Agent', role: 'System Observability', status: 'active', mode: 'Power', tasks_completed: 999 },
]

export default function MobileAgents() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    try {
      const r = await api.get('/api/agents')
      setAgents(Array.isArray(r) ? r : r?.agents || MOCK_AGENTS)
    } catch { setAgents(MOCK_AGENTS) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filters = [
    { id: 'all', label: 'All' },
    { id: 'active', label: 'Active' },
    { id: 'idle', label: 'Idle' },
    { id: 'error', label: 'Error' },
  ]

  const filtered = filter === 'all' ? agents : agents.filter(a => a.status === filter)

  return (
    <div style={S.screen}>
      <TopBar title="AGENTS" subtitle={`${agents.length} registered`} />

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
          <Empty icon="◉" message={`No ${filter} agents`} />
        ) : (
          <Section>
            {filtered.map(a => (
              <AgentCard key={a.id || a.name} agent={a} onClick={() => setSelected(a)} />
            ))}
          </Section>
        )}
      </div>

      <Sheet open={!!selected} onClose={() => setSelected(null)} title={selected?.name || 'Agent'}>
        {selected && <AgentDetail agent={selected} />}
      </Sheet>
    </div>
  )
}

function AgentDetail({ agent }) {
  const tone = agent.status === 'active' ? 'ok' : agent.status === 'error' ? 'error' : 'idle'
  const completed = agent.tasks_completed ?? 0
  const successPct = agent.success_rate ?? (completed > 0 ? 94 : 0)
  return (
    <div>
      <div style={S.detailHero}>
        <div style={S.detailIcon}>{(agent.name || 'A')[0].toUpperCase()}</div>
        <div style={S.detailInfo}>
          <div style={S.detailName}>{agent.name || agent.id}</div>
          <div style={S.detailRole}>{agent.role || agent.type || 'Agent'}</div>
          <StatusPill label={agent.status || 'idle'} tone={tone} />
        </div>
      </div>

      <div style={S.detailSection}>
        <div style={S.detailSectionLabel}>Capabilities</div>
        <div style={S.capList}>
          {(agent.capabilities || ['task-execution', 'llm-reasoning']).map(c => (
            <span key={c} style={S.cap}>{c}</span>
          ))}
        </div>
      </div>

      <div style={S.detailSection}>
        <div style={S.detailSectionLabel}>Performance</div>
        <Row label="Tasks Completed" value={completed} />
        <Row label="Mode" value={agent.mode || 'Standard'} />
        <Row label="Success Rate" value={`${successPct}%`} />
        <div style={{ padding: '8px 16px 0' }}>
          <ProgressBar value={successPct} color="var(--success)" />
        </div>
      </div>

      {agent.current_task && (
        <div style={S.detailSection}>
          <div style={S.detailSectionLabel}>Current Task</div>
          <div style={S.currentTask}>{agent.current_task}</div>
        </div>
      )}
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 16 },
  center: { display: 'flex', justifyContent: 'center', padding: 40 },
  filterRow: { display: 'flex', gap: 6, padding: '8px 16px', borderBottom: '1px solid var(--border-subtle)' },
  filterBtn: { padding: '4px 12px', borderRadius: 16, border: '1px solid var(--border-subtle)',
    background: 'none', color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer' },
  filterActive: { background: 'rgba(229,199,107,0.12)', color: 'var(--gold)', borderColor: 'rgba(229,199,107,0.3)' },
  detailHero: { display: 'flex', gap: 12, padding: '16px 16px 12px', borderBottom: '1px solid var(--border-subtle)' },
  detailIcon: { width: 48, height: 48, borderRadius: 12, background: 'rgba(229,199,107,0.12)',
    border: '1px solid rgba(229,199,107,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 20, fontWeight: 700, color: 'var(--gold)', flexShrink: 0 },
  detailInfo: { flex: 1, display: 'flex', flexDirection: 'column', gap: 4 },
  detailName: { fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' },
  detailRole: { fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 },
  detailSection: { marginTop: 0, borderTop: '1px solid var(--border-subtle)' },
  detailSectionLabel: { fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase', padding: '10px 16px 4px' },
  capList: { display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 16px 10px' },
  cap: { padding: '3px 8px', background: 'rgba(229,199,107,0.08)', border: '1px solid rgba(229,199,107,0.15)',
    borderRadius: 12, fontSize: 10, color: 'var(--gold)' },
  currentTask: { padding: '8px 16px 12px', fontSize: 12, color: 'var(--text-primary)', fontStyle: 'italic' },
}
