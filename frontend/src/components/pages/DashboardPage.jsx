import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'

function MetricCard({ label, value, hint, highlighted = false }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.97 }}
      className={`dashboard-glass-card dashboard-metric-card${highlighted ? ' dashboard-metric-card--highlighted' : ''}`}
    >
      <div className="dashboard-metric-label">
        {label}
      </div>
      <div className="dashboard-metric-value">{value}</div>
      {hint && <div className="dashboard-metric-hint">{hint}</div>}
    </motion.div>
  )
}

function RadialGauge({ label, value, color, ariaUnit = 'percent', displaySuffix = '%' }) {
  const size = 110
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(value, 100)) / 100) * circumference

  return (
    <div className="dashboard-gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} ${Math.round(value)} ${ariaUnit}`}>
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          style={{ filter: `drop-shadow(0 0 8px ${color})` }}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="dashboard-gauge-center">
        <span className="dashboard-gauge-value">{Math.round(value)}{displaySuffix}</span>
        <span className="dashboard-gauge-label">{label}</span>
      </div>
    </div>
  )
}

function ParticleMap() {
  // Kept as lightweight background visual on dashboard
  const particles = useMemo(
    () => Array.from({ length: 14 }, (_, i) => ({
      id: i,
      left: `${(i * 37) % 96 + 2}%`,
      top: `${(i * 23) % 86 + 5}%`,
      size: 4 + (i % 4),
      duration: 7 + (i % 6) * 0.7,
      delay: i * 0.14,
      amber: i % 3 === 0,
    })),
    []
  )

  return (
    <div className="dashboard-particle-map dashboard-particle-map--compact">
      <div className="dashboard-map-grid" />
      {particles.map((particle) => (
        <motion.span
          key={particle.id}
          className={`dashboard-particle${particle.amber ? ' dashboard-particle--amber' : ''}`}
          style={{ left: particle.left, top: particle.top, width: particle.size, height: particle.size }}
          animate={{ y: [0, -8, 0], opacity: [0.45, 1, 0.45] }}
          transition={{ duration: particle.duration, repeat: Infinity, ease: 'easeInOut', delay: particle.delay }}
        />
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const systemStatus = useAppStore(s => s.systemStatus)
  const agents = useAppStore(s => s.agents)
  const wsConnected = useAppStore(s => s.wsConnected)
  const nnStatus = useAppStore(s => s.nnStatus)
  const objectivePanels = useAppStore(s => s.objectivePanels)
  const autonomyStatus = useAppStore(s => s.autonomyStatus)

  const normalizedAgents = useMemo(
    () => (agents || []).map(agent => ({ ...agent, status: agent.status ?? agent.state })),
    [agents]
  )
  const activeAgents = useMemo(
    () => normalizedAgents.filter(a => a.status === 'running' || a.status === 'busy'),
    [normalizedAgents]
  )
  const totalAgents = systemStatus?.total_agents ?? agents?.length ?? 0
  const runningAgents = systemStatus?.running_agents ?? activeAgents.length
  const stoppedAgents = Math.max(totalAgents - runningAgents, 0)

  const metrics = [
    { label: 'Active Agents', value: runningAgents, hint: `${Math.round((runningAgents / Math.max(totalAgents, 1)) * 100)}% utilization` },
    { label: 'Total Agents', value: totalAgents, hint: 'Fleet capacity' },
    { label: 'Stopped Agents', value: stoppedAgents, hint: 'Standby / idle' },
    { label: 'Gateway', value: wsConnected ? 'ONLINE' : 'OFFLINE', hint: wsConnected ? 'Realtime link stable' : 'Reconnect required', highlighted: true },
  ]

  const healthItems = [
    { label: 'CPU', value: systemStatus?.cpu_usage ?? 0, color: 'var(--neon-teal)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'RAM', value: systemStatus?.memory ?? 0, color: 'var(--neon-amber)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'GPU', value: systemStatus?.gpu_usage ?? 0, color: 'var(--neon-cyan)', ariaUnit: 'percent', displaySuffix: '%' },
    { label: 'Temp', value: Math.min(100, Math.round(systemStatus?.cpu_temperature ?? 0)), color: 'var(--warning)', ariaUnit: 'degrees celsius', displaySuffix: '°C' },
  ]

  const moneyModePanel = objectivePanels?.money_mode || {}
  const ascendForgePanel = objectivePanels?.ascend_forge || {}
  const daemon = autonomyStatus?.daemon || {}

  const NAV_CARDS = [
    {
      to: '/command-center',
      icon: '◉',
      label: 'Command Center',
      desc: 'Core Brain Agent — task routing and directives',
      color: 'var(--gold)',
    },
    {
      to: '/agents',
      icon: '⬡',
      label: 'Agents',
      desc: `${runningAgents} active of ${totalAgents} total`,
      color: 'var(--success)',
    },
    {
      to: '/modes/blacklight',
      icon: '◈',
      label: 'Blacklight Mode',
      desc: 'System optimization — advanced agent control',
      color: 'var(--info)',
    },
    {
      to: '/modes/ascend-forge',
      icon: '🔺',
      label: 'Ascend Forge',
      desc: ascendForgePanel?.current_objective?.goal || 'Self-improvement pipeline',
      color: 'var(--gold)',
      status: ascendForgePanel?.status,
    },
    {
      to: '/modes/money',
      icon: '💰',
      label: 'Money Mode',
      desc: moneyModePanel?.current_objective?.goal || 'Monetization workflows',
      color: 'var(--success)',
      status: moneyModePanel?.status,
    },
    {
      to: '/memory',
      icon: '🧠',
      label: 'Memory',
      desc: 'Agent memory graph and entities',
      color: 'var(--neon-teal)',
    },
    {
      to: '/health',
      icon: '♥',
      label: 'Health',
      desc: 'System diagnostics and issue tracker',
      color: 'var(--error)',
    },
    {
      to: '/settings',
      icon: '▣',
      label: 'Settings',
      desc: 'API keys, webhooks, environment config',
      color: 'var(--text-secondary)',
    },
  ]

  return (
    <div className="page-enter dashboard-overview">
      <PageHeader
        title="AI Employee OS"
        subtitle="System overview — select a module below"
      />

      {/* Metrics row */}
      <div className="dashboard-metrics-grid">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      {/* System health gauges */}
      <div className="dashboard-glass-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
          <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', margin: 0 }}>
            System Health
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: '12px', color: 'var(--text-muted)' }}>
            <span className={`status-dot ${daemon.running ? 'status-dot--active status-dot--pulse' : 'status-dot--idle'}`} />
            Daemon {daemon.running ? 'Running' : 'Stopped'}
            {daemon.cycles > 0 && ` · ${daemon.cycles} cycles`}
          </div>
        </div>
        <div className="dashboard-health-grid">
          {healthItems.map((item) => (
            <RadialGauge key={item.label} label={item.label} value={item.value} color={item.color} ariaUnit={item.ariaUnit} displaySuffix={item.displaySuffix} />
          ))}
        </div>
      </div>

      {/* Neural Brain status strip */}
      <div className="dashboard-glass-card" style={{ padding: 'var(--space-3) var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>Core Brain Agent</span>
          <span style={{ fontSize: '12px', color: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)' }}>
            {nnStatus?.active ? '● Active' : '○ Idle'}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Confidence: <span style={{ color: 'var(--gold)' }}>{Math.round((nnStatus?.confidence ?? 0) * 100)}%</span>
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Mode: <span style={{ color: 'var(--text-primary)' }}>{systemStatus?.mode || 'MANUAL'}</span>
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Heartbeat: <span style={{ color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{systemStatus?.heartbeat ?? 0}</span>
          </span>
        </div>
      </div>

      {/* Module navigation grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: 'var(--space-3)',
      }}>
        {NAV_CARDS.map((card) => (
          <motion.button
            key={card.to}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => navigate(card.to)}
            className="dashboard-glass-card"
            style={{
              padding: 'var(--space-4)',
              textAlign: 'left',
              cursor: 'pointer',
              border: '1px solid var(--border-subtle)',
              background: 'transparent',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'inherit',
              width: '100%',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-1)' }}>
              <span style={{ fontSize: '16px' }}>{card.icon}</span>
              <span style={{ fontSize: '14px', fontWeight: 600, color: card.color }}>{card.label}</span>
              {card.status && card.status !== 'inactive' && (
                <span style={{
                  fontSize: '10px',
                  color: card.status === 'running' ? 'var(--success)' : 'var(--warning)',
                  background: card.status === 'running' ? 'rgba(34,197,94,0.1)' : 'rgba(245,158,11,0.1)',
                  padding: '1px 6px',
                  borderRadius: '8px',
                  marginLeft: 'auto',
                }}>
                  {card.status}
                </span>
              )}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', paddingLeft: '26px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {card.desc}
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  )
}
