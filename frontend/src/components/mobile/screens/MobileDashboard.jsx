/* NEXUS OS Mobile — CMD (Dashboard) Screen */
import { useState, useEffect, useCallback } from 'react'
import { TopBar, Section, KPIGrid, KPITile, Sparkline, AgentCard, TaskCard, Empty, Spinner, StatusPill } from '../MobileUI'
import api from '../../../api/client'

const MOCK_STATUS = { cpu: 42, memory: 61, uptime: 98400, phase: 'ONLINE' }
const MOCK_AGENTS = [
  { id: 'orchestrator', name: 'Orchestrator', role: 'Core Brain', status: 'active' },
  { id: 'research', name: 'Research Agent', role: 'Intelligence', status: 'idle' },
]
const MOCK_TASKS = [
  { id: '1', name: 'Market Analysis', status: 'running', progress: 65, assigned_to: 'research' },
  { id: '2', name: 'Content Generation', status: 'completed', progress: 100 },
]

export default function MobileDashboard({ onBell, unread, onAgentTap }) {
  const [status, setStatus] = useState(null)
  const [agents, setAgents] = useState([])
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [cpuHistory] = useState(() => Array.from({ length: 20 }, () => Math.random() * 40 + 20))

  const load = useCallback(async () => {
    try {
      const [s, a, t] = await Promise.allSettled([
        api.get('/api/status'),
        api.get('/api/agents'),
        api.get('/api/tasks'),
      ])
      if (s.status === 'fulfilled') setStatus(s.value?.system || s.value || MOCK_STATUS)
      else setStatus(MOCK_STATUS)
      if (a.status === 'fulfilled') setAgents(Array.isArray(a.value) ? a.value : a.value?.agents || MOCK_AGENTS)
      else setAgents(MOCK_AGENTS)
      if (t.status === 'fulfilled') setTasks(Array.isArray(t.value) ? t.value.slice(0, 5) : t.value?.tasks?.slice(0, 5) || MOCK_TASKS)
      else setTasks(MOCK_TASKS)
    } catch {
      setStatus(MOCK_STATUS); setAgents(MOCK_AGENTS); setTasks(MOCK_TASKS)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const activeAgents = agents.filter(a => a.status === 'active' || a.status === 'running').length
  const uptimeHrs = status ? Math.floor((status.uptime || 0) / 3600) : 0
  const runningTasks = tasks.filter(t => t.status === 'running' || t.status === 'pending').length

  return (
    <div style={S.screen}>
      <TopBar
        title="NEXUS OS"
        subtitle={status?.phase || 'INITIALIZING'}
        onBell={onBell}
        unread={unread}
      />
      <div style={S.scroll}>
        {loading ? (
          <div style={S.center}><Spinner /></div>
        ) : (
          <>
            <Section label="System Status" right={<StatusPill label={status?.phase === 'ONLINE' ? 'online' : 'degraded'} tone={status?.phase === 'ONLINE' ? 'ok' : 'warn'} />}>
              <KPIGrid>
                <KPITile label="CPU" value={status?.cpu ?? '—'} unit="%" live color="gold"
                  delta={-2.1} />
                <KPITile label="Memory" value={status?.memory ?? '—'} unit="%" live color={status?.memory > 80 ? 'red' : 'cyan'} />
                <KPITile label="Uptime" value={uptimeHrs} unit="h" color="green" />
                <KPITile label="Tasks" value={runningTasks} live={runningTasks > 0} color="gold" />
              </KPIGrid>
            </Section>

            <Section label="CPU Trend">
              <div style={S.sparkRow}>
                <Sparkline data={cpuHistory} width={window.innerWidth - 32} height={40} />
              </div>
            </Section>

            <Section label="Active Agents" right={`${activeAgents} / ${agents.length}`}>
              {agents.length === 0 ? <Empty icon="◉" message="No agents registered" /> :
                agents.slice(0, 4).map(a => (
                  <AgentCard key={a.id || a.name} agent={a} onClick={() => onAgentTap?.(a)} />
                ))
              }
            </Section>

            <Section label="Recent Tasks">
              {tasks.length === 0 ? <Empty icon="◇" message="No tasks found" /> :
                tasks.map(t => <TaskCard key={t.id || t.name} task={t} />)
              }
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 16 },
  center: { display: 'flex', justifyContent: 'center', padding: 40 },
  sparkRow: { padding: '4px 16px 8px', overflow: 'hidden' },
}
