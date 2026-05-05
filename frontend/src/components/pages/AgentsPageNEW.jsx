import { useState, useEffect, memo } from 'react'
import { useAppStore } from '../../store/appStore'
import { Panel, KPITile, StatusPill, HexButton, HexFrame, SectionLabel } from '../nexus-ui'
import { MiniBar } from '../ui/primitives'
import './AgentsPageNEW.css'

/**
 * AgentsPageNEW — The Swarm: live agent fleet in Nexus OS layout.
 * Roster (L), KPI strip (T), profile + tasks (C), fleet health (R),
 * reviews + upgrades (B).
 */

const STATUS_TONE = { running: 'success', active: 'success', idle: 'idle', error: 'alert', stopped: 'idle' }

const FLEET_MODES = [
  { id: 'SLEEP', icon: '◌', desc: 'All agents idle'  },
  { id: 'AUTO',  icon: '⊕', desc: 'Adaptive routing' },
  { id: 'AWAKE', icon: '⊛', desc: 'All agents active' },
]

export const AgentsPageNEW = () => {
  const storeAgents = useAppStore(s => s.agents)
  const [agents, setAgents] = useState([])
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [fleetMode, setFleetMode] = useState('AUTO')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchAgents = async () => {
      setLoading(true)
      try {
        const res = await fetch('/api/agents')
        if (res.ok) {
          const data = await res.json()
          const list = Array.isArray(data.agents) ? data.agents : []
          const mapped = list.map((a, i) => ({
            id: a.id || `agent-${i}`,
            name: a.name || a.description?.split(' — ')[0] || 'Unknown',
            status: a.status || 'idle',
            description: a.description || '',
            health: a.health ?? 85,
            tasksCompleted: a.tasksCompleted ?? 0,
            uptime: a.uptime ?? 0,
            errorRate: (a.errorRate ?? 0).toFixed(2),
          }))
          setAgents(mapped)
          if (!selectedAgent && mapped.length > 0) setSelectedAgent(mapped[0])
        }
      } catch (err) {
        console.warn('Failed to fetch agents:', err)
      } finally {
        setLoading(false)
      }
    }

    if (storeAgents.length === 0 && !loading) {
      fetchAgents()
    } else if (storeAgents.length > 0) {
      setAgents(storeAgents)
      if (!selectedAgent && storeAgents.length > 0) setSelectedAgent(storeAgents[0])
    }
  }, [storeAgents, selectedAgent, loading])

  const handleFleetMode = (mode) => {
    setFleetMode(mode)
    setAgents(prev => prev.map(a => ({
      ...a,
      status: mode === 'SLEEP' ? 'idle' : mode === 'AWAKE' ? 'running' : a.status,
    })))
  }

  const activeCount = agents.filter(a => a.status === 'running').length
  const totalHealth = agents.length > 0 ? Math.round(agents.reduce((s, a) => s + a.health, 0) / agents.length) : 0
  const avgError = agents.length > 0 ? (agents.reduce((s, a) => s + parseFloat(a.errorRate || 0), 0) / agents.length).toFixed(2) : '0.00'

  return (
    <div className="agp-grid">
      {/* KPI strip */}
      <div className="agp-kpis">
        <KPITile icon="⚉" iconTone="gold" label="Total Agents" value={agents.length || '—'} sub="REGISTERED" />
        <KPITile icon="◉" iconTone="success" label="Active" value={activeCount} sub={`${agents.length - activeCount} idle`} />
        <KPITile icon="✦" iconTone="cool" label="Fleet Health" value={`${totalHealth}%`} sub="MEAN" accent />
        <KPITile icon="!" iconTone="warn" label="Error Rate" value={`${avgError}%`} sub="ROLLING 1H" />
      </div>

      {/* Roster */}
      <Panel
        icon="⚏"
        title="Agent Roster"
        actions={<StatusPill tone="gold" label={`${agents.length}`} dot={false} size="sm" />}
        className="agp-roster"
      >
        <div className="agp-list">
          {agents.slice(0, 12).map(a => (
            <button
              key={a.id}
              type="button"
              className={`agp-list__row ${selectedAgent?.id === a.id ? 'is-selected' : ''}`}
              onClick={() => setSelectedAgent(a)}
            >
              <span className={`agp-list__dot agp-list__dot--${STATUS_TONE[a.status] || 'idle'}`} />
              <span className="agp-list__name">{a.name}</span>
              <span className="agp-list__health">{a.health}%</span>
            </button>
          ))}
          {agents.length > 12 && (
            <div className="agp-list__more">+{agents.length - 12} more</div>
          )}
          {agents.length === 0 && !loading && (
            <div className="agp-empty">No agents online</div>
          )}
        </div>
      </Panel>

      {/* Profile */}
      <Panel
        icon="◈"
        title="Agent Profile"
        actions={selectedAgent && (
          <StatusPill
            tone={STATUS_TONE[selectedAgent.status] || 'idle'}
            label={selectedAgent.status?.toUpperCase()}
          />
        )}
        className="agp-profile"
      >
        {selectedAgent ? (
          <div className="agp-profile__body">
            <div className="agp-profile__hero">
              <HexFrame size="lg" tone="gold" glow>
                <span style={{ fontSize: 22 }}>⚉</span>
              </HexFrame>
              <div className="agp-profile__title">
                <div className="agp-profile__name">{selectedAgent.name}</div>
                <div className="agp-profile__id">{selectedAgent.id}</div>
              </div>
            </div>
            <div className="agp-profile__rows">
              <DetailRow label="Health">
                <div style={{ width: 120 }}>
                  <MiniBar value={selectedAgent.health} max={100} color="var(--nx-gold)" />
                </div>
                <span className="agp-num">{selectedAgent.health}%</span>
              </DetailRow>
              <DetailRow label="Tasks">
                <span className="agp-num">{selectedAgent.tasksCompleted}</span>
              </DetailRow>
              <DetailRow label="Uptime">
                <span className="agp-num">{selectedAgent.uptime}h</span>
              </DetailRow>
              <DetailRow label="Error Rate">
                <span className="agp-num">{selectedAgent.errorRate}%</span>
              </DetailRow>
            </div>
            {selectedAgent.description && (
              <div className="agp-profile__desc">{selectedAgent.description}</div>
            )}
          </div>
        ) : (
          <div className="agp-empty">Select an agent</div>
        )}
      </Panel>

      {/* Fleet Control */}
      <Panel icon="⌬" title="Fleet Control" className="agp-fleet">
        <SectionLabel size="sm" tone="dim">Mode · {fleetMode}</SectionLabel>
        <div className="agp-fleet__btns">
          {FLEET_MODES.map(m => (
            <HexButton
              key={m.id}
              variant={fleetMode === m.id ? 'primary' : 'outline'}
              size="sm"
              icon={m.icon}
              onClick={() => handleFleetMode(m.id)}
            >
              {m.id}
            </HexButton>
          ))}
        </div>
        <SectionLabel size="sm" tone="dim" rule>Deployments</SectionLabel>
        <div className="agp-deploy">
          <DeploymentCell title="Production" count={activeCount} tone="gold" />
          <DeploymentCell title="Testing"    count={Math.floor(agents.length / 3)} tone="purple" />
          <DeploymentCell title="Dev"        count={Math.floor(agents.length / 4)} tone="cool" />
          <DeploymentCell title="Reserve"    count={Math.max(0, agents.length - activeCount - Math.floor(agents.length / 3))} tone="idle" />
        </div>
      </Panel>

      {/* Active Tasks */}
      <Panel icon="◎" title="Active Tasks" actions={<StatusPill tone="success" label="LIVE" />} className="agp-tasks">
        <div className="agp-tasks__list">
          {agents.filter(a => a.status === 'running').map(a => (
            <div key={a.id} className="agp-task">
              <span className="agp-task__agent">{a.name}</span>
              <div className="agp-task__bar"><div className="agp-task__fill" /></div>
              <span className="agp-task__eta">2m</span>
            </div>
          ))}
          {agents.filter(a => a.status === 'running').length === 0 && (
            <div className="agp-empty">No active tasks</div>
          )}
        </div>
      </Panel>

      {/* Fleet Health */}
      <Panel icon="✚" title="Fleet Health" className="agp-health">
        <HealthMetric label="Overall"      value={totalHealth} max={100} unit="%" />
        <HealthMetric label="Avg Response" value={48}          max={100} unit="ms" />
        <HealthMetric label="Error Rate"   value={parseFloat(avgError)} max={10}  unit="%" />
        <HealthMetric label="Efficiency"   value={94}          max={100} unit="%" />
      </Panel>

      {/* Reviews */}
      <Panel icon="✓" title="Recent Reviews" className="agp-reviews">
        <ReviewItem from="Code Auditor"   to="Agent-01" verdict="APPROVED" tone="success" score={94} />
        <ReviewItem from="Safety Monitor" to="Agent-02" verdict="FLAGGED"  tone="warn"    score={62} />
        <ReviewItem from="Compliance"     to="Agent-03" verdict="APPROVED" tone="success" score={88} />
        <ReviewItem from="Performance"    to="Agent-04" verdict="REVISE"   tone="cool"    score={71} />
      </Panel>

      {/* Upgrades */}
      <Panel icon="▲" title="Upgrade Paths" className="agp-upgrades">
        <UpgradeCard name="Token Efficiency"      current="v2.1" next="v2.3" impact="+14%" />
        <UpgradeCard name="Latency Optimization"  current="v1.8" next="v1.9" impact="-32ms" />
        <UpgradeCard name="Error Handling"        current="v3.0" next="v3.2" impact="-0.8%" />
      </Panel>
    </div>
  )
}

function DetailRow({ label, children }) {
  return (
    <div className="agp-detail">
      <span className="agp-detail__label">{label}</span>
      <div className="agp-detail__val">{children}</div>
    </div>
  )
}

function DeploymentCell({ title, count, tone }) {
  return (
    <div className={`agp-deploy__cell agp-deploy__cell--${tone}`}>
      <div className="agp-deploy__count">{count}</div>
      <div className="agp-deploy__title">{title}</div>
    </div>
  )
}

function HealthMetric({ label, value, max, unit = '' }) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="agp-metric">
      <div className="agp-metric__head">
        <span className="agp-metric__label">{label}</span>
        <span className="agp-metric__value">{value}{unit}</span>
      </div>
      <div className="agp-metric__bar"><div className="agp-metric__fill" style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

function ReviewItem({ from, to, verdict, tone, score }) {
  return (
    <div className="agp-review">
      <div className="agp-review__route">
        <span className="agp-review__from">{from}</span>
        <span className="agp-review__arrow">→</span>
        <span className="agp-review__to">{to}</span>
      </div>
      <StatusPill tone={tone} label={verdict} dot={false} size="sm" />
      <span className="agp-review__score">{score}</span>
    </div>
  )
}

function UpgradeCard({ name, current, next, impact }) {
  return (
    <div className="agp-upgrade">
      <div className="agp-upgrade__name">{name}</div>
      <div className="agp-upgrade__versions">
        <span className="agp-upgrade__current">{current}</span>
        <span className="agp-upgrade__arrow">→</span>
        <span className="agp-upgrade__next">{next}</span>
      </div>
      <div className="agp-upgrade__impact">{impact}</div>
    </div>
  )
}

export default memo(AgentsPageNEW)
