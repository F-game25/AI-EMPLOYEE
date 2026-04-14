import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'

const STATUS_CONFIG = {
  running: { color: 'var(--success)', label: 'Active' },
  busy: { color: 'var(--warning)', label: 'Busy' },
  idle: { color: 'var(--text-muted)', label: 'Idle' },
}

function StatCard({ label, value, simulated }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
        {label}
        {simulated && <span style={{ color: 'var(--warning)', fontSize: '10px', marginLeft: '6px' }}>SIMULATED</span>}
      </div>
      <div style={{ fontSize: '24px', fontWeight: 500, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
        {value}
      </div>
    </div>
  )
}

function QuickAction({ label, onClick, disabled, variant = 'secondary' }) {
  return (
    <button
      className={`btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
      style={{ fontSize: '13px' }}
    >
      {label}
    </button>
  )
}

function ActivityItem({ item, index }) {
  const kindColors = {
    automation: 'var(--gold)',
    pipeline: 'var(--info)',
    task: 'var(--success)',
    system: 'var(--text-muted)',
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="ds-card-interactive"
      style={{
        padding: 'var(--space-3) var(--space-4)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--space-3)',
      }}
    >
      <span
        className="status-dot"
        style={{
          background: kindColors[item.kind] || 'var(--text-muted)',
          marginTop: '6px',
          flexShrink: 0,
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: '13px',
          color: 'var(--text-primary)',
          wordBreak: 'break-word',
        }}>
          {item.notes}
        </div>
        {item.kind && (
          <div style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            marginTop: '2px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {item.kind}
          </div>
        )}
      </div>
      <span style={{
        fontSize: '11px',
        color: 'var(--text-muted)',
        flexShrink: 0,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {item.ts ? new Date(item.ts).toLocaleTimeString('en-US', {
          hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
        }) : ''}
      </span>
    </motion.div>
  )
}

function AgentMiniCard({ agent }) {
  const cfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.idle
  return (
    <div className="ds-card-interactive" style={{ padding: 'var(--space-3) var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: '4px' }}>
        <span className={`status-dot ${agent.status === 'running' ? 'status-dot--active status-dot--pulse' : agent.status === 'busy' ? 'status-dot--busy' : 'status-dot--idle'}`} />
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
          {agent.name || agent.id}
        </span>
        <span style={{
          fontSize: '10px',
          padding: '1px 6px',
          borderRadius: '4px',
          background: `${cfg.color}15`,
          color: cfg.color,
          marginLeft: 'auto',
        }}>
          {cfg.label}
        </span>
      </div>
      {agent.current_task && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: '18px' }}>
          {agent.current_task}
        </div>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const systemStatus = useAppStore(s => s.systemStatus)
  const productMetrics = useAppStore(s => s.productMetrics)
  const agents = useAppStore(s => s.agents)
  const activityFeed = useAppStore(s => s.activityFeed)
  const autonomyStatus = useAppStore(s => s.autonomyStatus)
  const setActiveSection = useAppStore(s => s.setActiveSection)

  const stats = useMemo(() => [
    { label: 'Active Agents', value: `${systemStatus?.running_agents ?? 0}` },
    { label: 'Tasks Executed', value: `${productMetrics?.tasks?.tasks_executed ?? 0}` },
    { label: 'Success Rate', value: `${Math.round((productMetrics?.tasks?.success_rate ?? 0) * 100)}%` },
    { label: 'Value Generated', value: `$${(productMetrics?.value?.value_generated ?? 0).toFixed(0)}`, simulated: true },
  ], [systemStatus, productMetrics])

  const systemHealth = useMemo(() => ({
    cpu: systemStatus?.cpu_usage ?? 0,
    memory: systemStatus?.memory ?? 0,
    mode: autonomyStatus?.mode?.mode || 'OFF',
  }), [systemStatus, autonomyStatus])

  const activeAgents = useMemo(() =>
    (agents || []).filter(a => a.status === 'running' || a.status === 'busy').slice(0, 5),
    [agents]
  )

  return (
    <div className="page-enter">
      <PageHeader
        title="Dashboard"
        subtitle="System overview and quick actions"
      />

      {/* System health bar */}
      <div className="ds-card" style={{
        padding: 'var(--space-3) var(--space-4)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-5)',
        marginBottom: 'var(--space-4)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span className={`status-dot ${systemHealth.mode !== 'OFF' ? 'status-dot--active status-dot--pulse' : 'status-dot--idle'}`} />
          <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
            {systemHealth.mode}
          </span>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          CPU <span style={{ color: 'var(--text-primary)' }}>{systemHealth.cpu}%</span>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Memory <span style={{ color: 'var(--text-primary)' }}>{systemHealth.memory}%</span>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Heartbeat <span style={{ color: 'var(--text-primary)' }}>{systemStatus?.heartbeat ?? 0}</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 'var(--space-3)',
        marginBottom: 'var(--space-5)',
      }}>
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* Quick Actions */}
      <div style={{ marginBottom: 'var(--space-5)' }}>
        <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          Quick Actions
        </h2>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <QuickAction label="Open Chat" onClick={() => setActiveSection('ai-control')} variant="primary" />
          <QuickAction label="View Agents" onClick={() => setActiveSection('agents')} />
          <QuickAction label="Operations" onClick={() => setActiveSection('operations')} />
          <QuickAction label="System Settings" onClick={() => setActiveSection('system')} />
        </div>
      </div>

      {/* Two-column: Active Agents + Recent Activity */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: 'var(--space-4)',
      }}>
        {/* Active Agents */}
        <div>
          <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Active Agents
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {activeAgents.length === 0 ? (
              <div className="ds-card" style={{
                padding: 'var(--space-5)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}>
                No active agents — start automation to deploy
              </div>
            ) : activeAgents.map((agent) => (
              <AgentMiniCard key={agent.id || agent.name} agent={agent} />
            ))}
          </div>
        </div>

        {/* Recent Activity */}
        <div>
          <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Recent Activity
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {activityFeed.length === 0 ? (
              <div className="ds-card" style={{
                padding: 'var(--space-5)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}>
                No recent activity
              </div>
            ) : activityFeed.slice(0, 8).map((item, idx) => (
              <ActivityItem key={item.id || idx} item={item} index={idx} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
