import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import HeartbeatPanel from './dashboard/HeartbeatPanel'
import ChatPanel from './dashboard/ChatPanel'
import AgentsPanel from './dashboard/AgentsPanel'
import NeuralNetworkPanel from './dashboard/NeuralNetworkPanel'
import MemoryTreePanel from './dashboard/MemoryTreePanel'
import DoctorPanel from './dashboard/DoctorPanel'
import { useAppStore } from '../store/appStore'

function StatCard({ label, value, sub, color }) {
  return (
    <div
      className="flex flex-col px-3 py-1.5"
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '4px',
        minWidth: '90px',
      }}
    >
      <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span
        className="font-mono text-sm font-bold"
        style={{ color: color || 'var(--text-secondary)' }}
      >
        {value}
      </span>
      {sub && (
        <span className="font-mono text-xs" style={{ color: 'var(--text-dim)', fontSize: '0.65rem' }}>
          {sub}
        </span>
      )}
    </div>
  )
}

export default function Dashboard() {
  const setAgents = useAppStore(s => s.setAgents)
  const setNnStatus = useAppStore(s => s.setNnStatus)
  const setMemoryTree = useAppStore(s => s.setMemoryTree)
  const setDoctorStatus = useAppStore(s => s.setDoctorStatus)
  const [dailyStats, setDailyStats] = useState(null)

  // Fetch initial agents via relative URL (proxied to backend in dev)
  useEffect(() => {
    fetch(`http://${window.location.hostname}:3001/agents`)
      .then(r => r.json())
      .then(d => d.agents && setAgents(d.agents))
      .catch(() => {})
  }, [setAgents])

  // Fetch initial subsystem states from REST API
  useEffect(() => {
    const base = `http://${window.location.hostname}:3001`

    fetch(`${base}/api/brain/status`)
      .then(r => r.json())
      .then(d => setNnStatus(d))
      .catch(() => {})

    fetch(`${base}/api/memory/tree`)
      .then(r => r.json())
      .then(d => setMemoryTree(d))
      .catch(() => {})

    fetch(`${base}/api/doctor/status`)
      .then(r => r.json())
      .then(d => setDoctorStatus(d))
      .catch(() => {})
  }, [setNnStatus, setMemoryTree, setDoctorStatus])

  // Fetch daily stats every 30s
  useEffect(() => {
    const load = () => {
      fetch(`http://${window.location.hostname}:3001/api/analytics/daily-stats`)
        .then(r => r.json())
        .then(d => setDailyStats(d))
        .catch(() => {})
    }
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed inset-0 flex flex-col scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* Top bar */}
      <TopBar />

      {/* Daily stats strip */}
      {dailyStats && (
        <div
          className="flex items-center gap-3 px-4 py-1.5 flex-shrink-0 overflow-x-auto"
          style={{ borderBottom: '1px solid var(--border-subtle)', background: 'rgba(0,0,0,0.3)' }}
          role="status"
          aria-label="Daily performance stats"
        >
          <StatCard
            label="TASKS"
            value={dailyStats.tasks?.tasks_executed ?? 0}
            sub="today"
            color="var(--gold)"
          />
          <StatCard
            label="SUCCESS"
            value={`${Math.round((dailyStats.tasks?.success_rate ?? 0) * 100)}%`}
            sub="rate"
            color={
              (dailyStats.tasks?.success_rate ?? 0) >= 0.8
                ? 'var(--success)'
                : 'var(--warning)'
            }
          />
          <StatCard
            label="REVENUE"
            value={`$${(dailyStats.revenue?.total_revenue ?? 0).toFixed(2)}`}
            sub="estimated"
            color="var(--success)"
          />
          <StatCard
            label="ROI"
            value={(dailyStats.revenue?.roi ?? 0).toFixed(4)}
            sub="rev/token"
            color="var(--text-secondary)"
          />
          {dailyStats.best_strategies?.length > 0 && (
            <StatCard
              label="TOP STRATEGY"
              value={dailyStats.best_strategies[0].agent ?? '—'}
              sub={`score ${(dailyStats.best_strategies[0].outcome_score ?? 0).toFixed(2)}`}
              color="#c084fc"
            />
          )}
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Heartbeat */}
        <div className="w-56 flex-shrink-0 overflow-hidden">
          <HeartbeatPanel />
        </div>

        {/* Center: Chat */}
        <div
          className="flex-1 min-w-0 overflow-hidden"
          style={{ borderLeft: '1px solid var(--border-gold-dim)', borderRight: '1px solid var(--border-gold-dim)' }}
        >
          <ChatPanel />
        </div>

        {/* Right: Stacked subsystem panels */}
        <div
          className="flex flex-col flex-shrink-0 overflow-hidden"
          style={{ width: '224px' }}
        >
          {/* Neural Network — top */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)' }}
          >
            <NeuralNetworkPanel />
          </div>

          {/* Memory Tree — middle */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)' }}
          >
            <MemoryTreePanel />
          </div>

          {/* Agents — flex-1 to fill remaining space */}
          <div className="flex-1 overflow-hidden" style={{ background: 'var(--bg-panel)' }}>
            <AgentsPanel />
          </div>

          {/* Doctor — bottom */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)', maxHeight: '220px' }}
          >
            <DoctorPanel />
          </div>
        </div>
      </div>

      {/* CRT vignette overlay — decorative only */}
      <div
        className="pointer-events-none fixed inset-0"
        aria-hidden="true"
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(0,0,0,0.45) 100%)',
          zIndex: 'var(--z-overlay)',
        }}
      />
    </motion.div>
  )
}
