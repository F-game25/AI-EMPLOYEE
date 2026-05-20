import { useMemo } from 'react'
import { useAgentStore } from '../../store/agentStore'
import './AgentGrid.css'

// Role-based accent colors (per spec)
const ROLE_COLORS = {
  coordinator: '#00FFB4',
  researcher: '#00D4FF',
  analyst: '#FF6B6B',
  optimizer: '#FFB800',
  deployer: '#B565F5',
  validator: '#FF8FA3',
}

const STATUS_COLORS = {
  active: '#00FFB4',
  running: '#00FFB4',
  busy: '#FFB800',
  idle: '#5a5747',
  error: '#FF6B6B',
  unknown: '#5a5747',
}

function formatCount(n) {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`
  return String(n)
}

function getInitials(agent) {
  const id = agent.id || agent.name || ''
  // Extract trailing digits or take first 2 chars
  const m = String(id).match(/(\D*)(\d+)/)
  if (m) {
    const letter = (m[1] || 'A').charAt(0).toUpperCase()
    return `${letter}${m[2].slice(-2)}`
  }
  return String(id).slice(0, 2).toUpperCase() || 'AG'
}

function roleAccent(role) {
  if (!role) return 'var(--nx-gold)'
  const key = String(role).toLowerCase()
  for (const [k, v] of Object.entries(ROLE_COLORS)) {
    if (key.includes(k)) return v
  }
  return 'var(--nx-gold)'
}

function statusColor(status) {
  const k = String(status || 'unknown').toLowerCase()
  return STATUS_COLORS[k] || STATUS_COLORS.unknown
}

function AgentTile({ agent }) {
  const accent = roleAccent(agent.role)
  const initials = getInitials(agent)
  const status = String(agent.status || 'idle').toUpperCase()
  const success =
    typeof agent.success_pct === 'number'
      ? agent.success_pct
      : typeof agent.health === 'number'
      ? agent.health
      : null

  return (
    <div className="ag-tile" role="listitem">
      <div className="ag-tile__avatar" style={{ background: accent, color: '#0a0a0a' }}>
        {initials}
      </div>
      <div className="ag-tile__body">
        <div className="ag-tile__name">{agent.id || agent.name || 'AGENT'}</div>
        <div className="ag-tile__role">{(agent.role || 'agent').toUpperCase()}</div>
        <div className="ag-tile__status">
          <span className="ag-tile__dot" style={{ background: statusColor(agent.status) }} />
          <span className="ag-tile__status-label" style={{ color: statusColor(agent.status) }}>
            {status}
          </span>
          {success !== null && (
            <span className="ag-tile__success">{Math.round(success)}%</span>
          )}
        </div>
      </div>
    </div>
  )
}

function SpawnTile() {
  const onSpawn = () => {
    window.dispatchEvent(new CustomEvent('nx:spawn-agent'))
  }
  return (
    <button
      type="button"
      className="ag-tile ag-tile--spawn"
      onClick={onSpawn}
      aria-label="Spawn new agent"
    >
      <div className="ag-tile__plus">+</div>
      <div className="ag-tile__spawn-label">SPAWN AGENT</div>
    </button>
  )
}

export default function AgentGrid() {
  const agents = useAgentStore(s => s.agents)

  const visible = useMemo(() => agents.slice(0, 5), [agents])
  const total = agents.length

  return (
    <section className="ag-panel" aria-label="Active Agent Swarm">
      <header className="ag-panel__head">
        <span className="ag-panel__title">ACTIVE AGENT SWARM</span>
        <span className="ag-panel__count">{formatCount(total)} AGENTS ONLINE</span>
      </header>

      {total === 0 ? (
        <div className="ag-panel__empty">No active agents</div>
      ) : (
        <div className="ag-panel__grid" role="list">
          {visible.map(a => (
            <AgentTile key={a.id || a.name} agent={a} />
          ))}
          <SpawnTile />
        </div>
      )}
    </section>
  )
}
