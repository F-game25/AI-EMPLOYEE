import { useState, useMemo, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const STATUS_CONFIG = {
  idle: { dot: 'status-dot--idle', color: 'var(--text-muted)', label: 'Idle' },
  running: { dot: 'status-dot--active status-dot--pulse', color: 'var(--success)', label: 'Active' },
  busy: { dot: 'status-dot--busy', color: 'var(--warning)', label: 'Busy' },
}

const GRADE_COLORS = {
  Ungraded: 'var(--text-muted)',
  Beginner: '#6ea8fe',
  Basic: '#52d9b2',
  Mature: '#f7c948',
  Advanced: '#e07b39',
  Pro: 'var(--gold)',
}

const FILTERS = ['all', 'active', 'busy', 'idle']

function GradeBadge({ grade }) {
  if (!grade || grade === 'Ungraded') return null
  const color = GRADE_COLORS[grade] || 'var(--text-muted)'
  return (
    <span style={{
      fontSize: '10px',
      padding: '2px 7px',
      borderRadius: '10px',
      background: `${color}18`,
      color,
      border: `1px solid ${color}40`,
      fontWeight: 600,
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
    }}>
      {grade}
    </span>
  )
}

function AgentCard({ agent, index, gradeInfo }) {
  const cfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.idle
  const grade = gradeInfo?.grade
  const topic = gradeInfo?.topic
  const levelsCompleted = gradeInfo?.levels_completed || 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02 }}
      className="ds-card-interactive"
      style={{ padding: 'var(--space-4)' }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <span className={`status-dot ${cfg.dot}`} />
        <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)', flex: 1 }}>
          {agent.name || agent.id}
        </span>
        <GradeBadge grade={grade} />
        <span style={{
          fontSize: '11px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: `${cfg.color}12`,
          color: cfg.color,
        }}>
          {cfg.label}
        </span>
      </div>

      {/* Current task */}
      {agent.current_task && (
        <div style={{
          fontSize: '13px',
          color: 'var(--text-secondary)',
          marginBottom: 'var(--space-2)',
          paddingLeft: '20px',
        }}>
          {agent.current_task}
        </div>
      )}

      {/* Learning ladder progress */}
      {topic && (
        <div style={{
          paddingLeft: '20px',
          marginBottom: 'var(--space-2)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
        }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Learning:</span>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{topic}</span>
          <div style={{ display: 'flex', gap: '2px', marginLeft: 'auto' }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <span key={n} style={{
                width: '7px',
                height: '7px',
                borderRadius: '2px',
                background: n <= levelsCompleted ? GRADE_COLORS[grade] || 'var(--gold)' : 'var(--border-subtle)',
              }} />
            ))}
          </div>
        </div>
      )}

      {/* Meta row */}
      <div style={{
        display: 'flex',
        gap: 'var(--space-4)',
        paddingLeft: '20px',
        fontSize: '12px',
        color: 'var(--text-muted)',
      }}>
        {agent.type && <span>Type: {agent.type}</span>}
        {agent.tasks_completed != null && <span>Completed: {agent.tasks_completed}</span>}
        {agent.health != null && (
          <span>
            Health:{' '}
            <span style={{ color: agent.health > 80 ? 'var(--success)' : agent.health > 50 ? 'var(--warning)' : 'var(--error)' }}>
              {Math.round(agent.health)}%
            </span>
          </span>
        )}
      </div>

      {/* Last action */}
      {agent.last_action && (
        <div style={{
          fontSize: '11px',
          color: 'var(--text-dim)',
          paddingLeft: '20px',
          marginTop: 'var(--space-1)',
        }}>
          Last: {agent.last_action}
        </div>
      )}
    </motion.div>
  )
}

function PerformanceBar({ label, value, max = 100, color = 'var(--gold)' }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div style={{ marginBottom: 'var(--space-2)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ color: 'var(--text-secondary)' }}>{value}/{max}</span>
      </div>
      <div style={{
        height: '4px',
        background: 'var(--bg-base)',
        borderRadius: '2px',
        overflow: 'hidden',
      }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(pct, 100)}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          style={{
            height: '100%',
            background: color,
            borderRadius: '2px',
          }}
        />
      </div>
    </div>
  )
}

function GradeDistribution({ distribution }) {
  if (!distribution) return null
  const grades = ['Beginner', 'Basic', 'Mature', 'Advanced', 'Pro']
  const graded = grades.filter(g => (distribution[g] || 0) > 0)
  if (graded.length === 0) return null
  return (
    <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
      {graded.map(g => (
        <div key={g} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: GRADE_COLORS[g], flexShrink: 0 }} />
          <span style={{ color: 'var(--text-muted)' }}>{g}:</span>
          <span style={{ color: GRADE_COLORS[g], fontWeight: 600 }}>{distribution[g]}</span>
        </div>
      ))}
    </div>
  )
}

export default function AgentsPage() {
  const rawAgents = useAppStore(s => s.agents)
  const systemStatus = useAppStore(s => s.systemStatus)
  const [filter, setFilter] = useState('all')
  const [gradesMap, setGradesMap] = useState({})
  const [gradeMetrics, setGradeMetrics] = useState(null)

  // Normalize backend snapshot fields (state→status, task→current_task, etc.)
  const agents = useMemo(() => {
    if (!rawAgents || rawAgents.length === 0) return []
    return rawAgents.map(a => ({
      ...a,
      status: a.status ?? a.state,
      current_task: a.current_task ?? a.task,
      tasks_completed: a.tasks_completed ?? a.tasksCompleted,
    }))
  }, [rawAgents])

  const fetchGrades = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/agents/grades`)
      const data = await res.json()
      if (data.ok) {
        const map = {}
        for (const p of (data.profiles || [])) {
          map[(p.agent_id || '').toLowerCase()] = p
        }
        setGradesMap(map)
        setGradeMetrics(data.metrics || null)
      }
    } catch (_) {
      // non-fatal
    }
  }, [])

  useEffect(() => {
    fetchGrades()
  }, [fetchGrades])

  const filteredAgents = useMemo(() => {
    if (!agents || agents.length === 0) return []
    if (filter === 'all') return agents
    if (filter === 'active') return agents.filter(a => a.status === 'running')
    if (filter === 'busy') return agents.filter(a => a.status === 'busy')
    if (filter === 'idle') return agents.filter(a => a.status === 'idle')
    return agents
  }, [agents, filter])

  const counts = useMemo(() => ({
    all: agents?.length || 0,
    active: agents?.filter(a => a.status === 'running').length || 0,
    busy: agents?.filter(a => a.status === 'busy').length || 0,
    idle: agents?.filter(a => a.status === 'idle').length || 0,
  }), [agents])

  return (
    <div className="page-enter">
      <PageHeader
        title="Agents"
        subtitle={`${systemStatus?.running_agents ?? 0} active of ${systemStatus?.total_agents ?? 0} total`}
      >
        {gradeMetrics?.total_agents_assigned > 0 && (
          <GradeDistribution distribution={gradeMetrics?.grade_distribution} />
        )}
      </PageHeader>

      {/* Filter tabs */}
      <div style={{
        display: 'flex',
        gap: 'var(--space-1)',
        marginBottom: 'var(--space-4)',
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-md)',
        padding: '3px',
        width: 'fit-content',
      }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: filter === f ? 'rgba(212, 175, 55, 0.1)' : 'transparent',
              color: filter === f ? 'var(--gold)' : 'var(--text-secondary)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 150ms',
              fontFamily: 'inherit',
            }}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            <span style={{ marginLeft: '6px', color: 'var(--text-muted)', fontSize: '11px' }}>
              {counts[f]}
            </span>
          </button>
        ))}
      </div>

      {/* Performance overview */}
      <div className="ds-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          Performance
        </h3>
        <PerformanceBar
          label="Active Agents"
          value={systemStatus?.running_agents ?? 0}
          max={systemStatus?.total_agents || 1}
          color="var(--success)"
        />
        <PerformanceBar
          label="CPU Usage"
          value={systemStatus?.cpu_usage ?? 0}
          color="var(--info)"
        />
        <PerformanceBar
          label="Memory Usage"
          value={systemStatus?.memory ?? 0}
          color="var(--warning)"
        />
      </div>

      {/* Agent grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
        gap: 'var(--space-3)',
      }}>
        {filteredAgents.length === 0 ? (
          <div className="ds-card" style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: '14px',
            gridColumn: '1 / -1',
          }}>
            {agents?.length === 0
              ? 'No agents deployed — start automation to bring agents online'
              : `No ${filter} agents`}
          </div>
        ) : filteredAgents.map((agent, idx) => {
          const gradeInfo = gradesMap[(agent.id || '').toLowerCase()] || gradesMap[(agent.name || '').toLowerCase()]
          return (
            <AgentCard
              key={agent.id || agent.name || idx}
              agent={agent}
              index={idx}
              gradeInfo={gradeInfo}
            />
          )
        })}
      </div>
    </div>
  )
}
