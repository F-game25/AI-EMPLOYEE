import { useAgentStore } from '../../store/agentStore'
import './AgentSwarmPanel.css'

function AgentCard({ agent, idx }) {
  const status = agent.status || (agent.active ? 'active' : 'idle')
  const isActive = status === 'active' || status === 'running'
  const isBusy = status === 'busy' || status === 'executing'
  const name = agent.name || agent.id || `A-${idx + 1}`
  const shortName = name.length > 6 ? name.slice(0, 6) : name
  const role = agent.role || agent.type || 'Agent'
  const metric = agent.performance ?? agent.success_rate ?? null

  return (
    <div className={`swarm-card ${isActive ? 'swarm-card--active' : isBusy ? 'swarm-card--busy' : ''}`}>
      <div className="swarm-card__top">
        <span className={`swarm-card__dot ${isActive ? 'swarm-card__dot--active' : isBusy ? 'swarm-card__dot--busy' : ''}`} />
        <span className="swarm-card__name">{shortName.toUpperCase()}</span>
      </div>
      <div className="swarm-card__role">{role.slice(0, 12)}</div>
      {metric != null && (
        <div className="swarm-card__metric">{Math.round(metric * (metric <= 1 ? 100 : 1))}%</div>
      )}
    </div>
  )
}

export default function AgentSwarmPanel() {
  const agents = useAgentStore(s => s.agents) || []
  const activeCount = agents.filter(a => a.status === 'active' || a.status === 'running' || a.active).length
  const displayAgents = agents.slice(0, 8)

  return (
    <div className="swarm-panel">
      <div className="swarm-panel__header">
        <span className="swarm-panel__title">ACTIVE AGENT SWARM</span>
        <span className="swarm-panel__count">{activeCount || agents.length} ONLINE</span>
      </div>
      {agents.length === 0 ? (
        <div className="swarm-panel__empty">No agents registered</div>
      ) : (
        <div className="swarm-panel__grid">
          {displayAgents.map((agent, i) => (
            <AgentCard key={agent.id || i} agent={agent} idx={i} />
          ))}
          {agents.length > 8 && (
            <div className="swarm-card swarm-card--more">
              +{agents.length - 8}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
