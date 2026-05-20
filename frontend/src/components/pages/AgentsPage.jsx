import { useState, useEffect, useCallback, memo } from 'react'
import { useAgentStore } from '../../store/agentStore'
import { useAppStore } from '../../store/appStore'
import { KPITile, StatusPill } from '../nexus-ui'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
import './AgentsPage.css'

// ── Constants ─────────────────────────────────────────────────────────────────

const ROLE_COLORS = {
  coordinator: '#00FFB4',
  researcher:  '#00D4FF',
  analyst:     '#FF6B6B',
  optimizer:   '#FFB800',
  deployer:    '#B565F5',
  validator:   '#FF8FA3',
}

const ROLE_GLOWS = {
  coordinator: 'rgba(0,255,180,0.22)',
  researcher:  'rgba(0,212,255,0.22)',
  analyst:     'rgba(255,107,107,0.22)',
  optimizer:   'rgba(255,184,0,0.22)',
  deployer:    'rgba(181,101,245,0.22)',
  validator:   'rgba(255,143,163,0.22)',
}

const STATUS_TONE = {
  running: 'success', active: 'success',
  idle: 'idle', stopped: 'idle',
  error: 'alert', critical: 'alert',
}

const ALL_FILTER_TABS = [
  { id: 'ALL',         label: 'ALL' },
  { id: 'ACTIVE',      label: 'ACTIVE' },
  { id: 'IDLE',        label: 'IDLE' },
  { id: 'ERROR',       label: 'ERROR' },
  { id: 'coordinator', label: 'COORDINATOR' },
  { id: 'researcher',  label: 'RESEARCHER' },
  { id: 'analyst',     label: 'ANALYST' },
  { id: 'optimizer',   label: 'OPTIMIZER' },
  { id: 'deployer',    label: 'DEPLOYER' },
  { id: 'validator',   label: 'VALIDATOR' },
]

const PAGE_SIZE = 24

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('ai_jwt')
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const roleColor = (role) => ROLE_COLORS[role?.toLowerCase()] ?? '#e5c76b'
const roleGlow  = (role) => ROLE_GLOWS[role?.toLowerCase()]  ?? 'rgba(229,199,107,0.22)'
const initials  = (name) => name ? String(name).slice(0, 2).toUpperCase() : '??'
const healthColor = (h) => h >= 75 ? '#22c55e' : h >= 40 ? '#f59e0b' : '#ef4444'

function normalizeAgent(raw, index = 0) {
  const id = String(raw.id ?? raw.agent_id ?? raw.name ?? `agent-${index}`)
  const role = raw.role ?? raw.target_type ?? raw.type ?? 'agent'
  const skills = raw.skills || raw.selected_skill_ids || raw.capabilities || []
  return {
    id,
    name: raw.name ?? raw.title ?? id,
    role,
    status: raw.status ?? raw.state ?? 'idle',
    health: Number.isFinite(Number(raw.health)) ? Number(raw.health) : 0,
    success_pct: Number.isFinite(Number(raw.success_pct)) ? Number(raw.success_pct) : null,
    tasks_completed: raw.tasks_completed ?? raw.tasksCompleted ?? 0,
    last_active: raw.last_active ?? raw.updated_at ?? raw.registered_at ?? null,
    recent_events: Array.isArray(raw.recent_events) ? raw.recent_events : [],
    contract_key: raw.contract_key ?? id,
    created_by: raw.created_by,
    contract: raw.contract,
    skills,
    hooks: raw.hooks || raw.contract?.hooks || [],
    authority_profile: raw.authority_profile || raw.contract?.authority_profile,
  }
}

function mergeAgents(...groups) {
  const map = new Map()
  groups.flat().filter(Boolean).forEach((agent, index) => {
    const normalized = normalizeAgent(agent, index)
    map.set(normalized.id, { ...(map.get(normalized.id) || {}), ...normalized })
  })
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
}

function filterAgents(agents, tab) {
  if (tab === 'ALL')    return agents
  if (tab === 'ACTIVE') return agents.filter(a => a.status === 'active' || a.status === 'running')
  if (tab === 'IDLE')   return agents.filter(a => a.status === 'idle' || a.status === 'stopped')
  if (tab === 'ERROR')  return agents.filter(a => a.status === 'error' || a.status === 'critical')
  return agents.filter(a => a.role?.toLowerCase() === tab.toLowerCase())
}

// ── Sub-components ────────────────────────────────────────────────────────────

const AgentTile = memo(({ agent, selected, onClick }) => {
  const rc = roleColor(agent.role)
  const rg = roleGlow(agent.role)
  const h  = agent.health ?? 0

  return (
    <button
      type="button"
      className={`swarm-tile${selected ? ' swarm-tile--active' : ''}`}
      onClick={() => onClick(agent)}
      style={{ '--role-color': rc, '--role-glow': rg }}
      aria-label={`${agent.name} — ${agent.role ?? 'agent'}`}
    >
      <div className="swarm-tile__avatar-wrap">
        <div className="swarm-tile__avatar" style={{ color: rc, borderColor: rc }}>
          {initials(agent.name)}
        </div>
        <span className={`swarm-tile__status-dot swarm-tile__status-dot--${agent.status === 'active' || agent.status === 'running' ? 'active' : agent.status === 'error' || agent.status === 'critical' ? 'error' : 'idle'}`} />
      </div>
      <div className="swarm-tile__id">{agent.id}</div>
      <div className="swarm-tile__role">{agent.role ?? 'AGENT'}</div>
      {typeof agent.success_pct === 'number' && (
        <div className="swarm-tile__badge" style={{ color: rc }}>{agent.success_pct}%</div>
      )}
      {agent.created_by === 'ascend-forge' && (
        <div className="swarm-tile__badge" style={{ color: '#e5c76b' }}>FORGE</div>
      )}
      <div className="swarm-tile__health-bar">
        <div
          className="swarm-tile__health-fill"
          style={{ width: `${h}%`, background: healthColor(h) }}
        />
      </div>
    </button>
  )
})

AgentTile.displayName = 'AgentTile'

function StatRow({ label, value }) {
  return (
    <div className="drawer-stat">
      <span className="drawer-stat__label">{label}</span>
      <span className="drawer-stat__value">{value}</span>
    </div>
  )
}

function DetailDrawer({ agent, onClose, contract }) {
  const rc = roleColor(agent.role)
  const events = agent.recent_events || []
  const [grade,  setGrade]  = useState(null)
  const [busy,   setBusy]   = useState(null)
  const workflows = contract?.workflows || []
  const hooks = contract?.hooks || []
  const allowedModels = contract?.allowed_models || []

  const callAction = useCallback(async (action) => {
    setBusy(action)
    try {
      if (action === 'grade') {
        const r = await fetch(`/api/agents/${agent.id}/grade`)
        const d = r.ok ? await r.json() : null
        if (d) setGrade(d.grade ?? d.score ?? '—')
      } else if (action === 'reinforce') {
        await fetch(`/api/agents/${agent.id}/reinforce`, { method: 'POST' })
      } else if (action === 'ladder') {
        await fetch(`/api/agents/${agent.id}/ladder/advance`, { method: 'POST' })
      }
    } catch {/* swallow — UI doesn't block on agent endpoints */}
    finally { setBusy(null) }
  }, [agent.id])

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="detail-drawer" role="complementary" aria-label="Agent detail">
        <button type="button" className="drawer-close" onClick={onClose} aria-label="Close drawer">×</button>

        <div className="drawer-hero">
          <div className="drawer-avatar" style={{ color: rc, borderColor: rc }}>
            {initials(agent.name)}
          </div>
          <div className="drawer-hero__text">
            <div className="drawer-hero__name">{agent.name}</div>
            <div className="drawer-hero__role" style={{ color: rc }}>{agent.role ?? 'AGENT'}</div>
            <StatusPill
              tone={STATUS_TONE[agent.status] || 'idle'}
              label={(agent.status ?? 'idle').toUpperCase()}
              size="sm"
            />
          </div>
        </div>

        <div className="drawer-divider" />

        <div className="drawer-stats">
          <StatRow label="Health"          value={`${agent.health ?? 0}%`} />
          <StatRow label="Tasks Completed" value={agent.tasks_completed ?? agent.tasksCompleted ?? 0} />
          <StatRow label="Success Rate"    value={typeof agent.success_pct === 'number' ? `${agent.success_pct}%` : '—'} />
          <StatRow label="Last Active"     value={agent.last_active ?? '—'} />
        </div>

        <div className="drawer-divider" />

        {contract && (
          <>
            <div className="drawer-events-label">JOB CONTRACT</div>
            <div className="drawer-contract">
              <div className="drawer-contract__title">{contract.title || agent.name}</div>
              <p className="drawer-contract__desc">{contract.job_description || contract.description}</p>
              {workflows.length > 0 && (
                <div className="drawer-chip-group">
                  {workflows.slice(0, 6).map(w => <span key={w} className="drawer-chip">{w}</span>)}
                </div>
              )}
              {hooks.length > 0 && (
                <div className="drawer-hook-list">
                  {hooks.slice(0, 5).map(h => <div key={h} className="drawer-hook">{h}</div>)}
                </div>
              )}
              {allowedModels.length > 0 && (
                <div className="drawer-models">{allowedModels.join(' / ')}</div>
              )}
            </div>
            <div className="drawer-divider" />
          </>
        )}

        <div className="drawer-events-label">RECENT EVENTS</div>
        <div className="drawer-events">
          {events.length === 0 && (
            <div className="drawer-event">
              <span className="drawer-event__dot" style={{ background: rc }} />
              <span className="drawer-event__text">No recent events recorded.</span>
            </div>
          )}
          {events.map((ev, i) => (
            <div key={i} className="drawer-event">
              <span className="drawer-event__dot" style={{ background: rc }} />
              <span className="drawer-event__text">
                {typeof ev === 'string' ? ev : `${ev.time} — ${ev.msg}`}
              </span>
            </div>
          ))}
        </div>

        <div className="drawer-divider" />

        <div className="drawer-events-label">TRAINING</div>
        <div className="drawer-training">
          <div className="drawer-training-row">
            <span className="drawer-training-label">Grade</span>
            <span className="drawer-training-val">{grade ?? '—'}</span>
            <button
              type="button"
              className="drawer-train-btn"
              disabled={busy !== null}
              onClick={() => callAction('grade')}
            >{busy === 'grade' ? '…' : 'CHECK'}</button>
          </div>
          <button
            type="button"
            className="drawer-train-btn drawer-train-btn--wide"
            disabled={busy !== null}
            onClick={() => callAction('reinforce')}
          >{busy === 'reinforce' ? 'REINFORCING…' : '↻ REINFORCE'}</button>
          <button
            type="button"
            className="drawer-train-btn drawer-train-btn--wide"
            disabled={busy !== null}
            onClick={() => callAction('ladder')}
          >{busy === 'ladder' ? 'ADVANCING…' : '↑ ADVANCE LADDER'}</button>
        </div>

        <div className="drawer-actions">
          <button
            type="button"
            className="drawer-btn drawer-btn--danger"
            onClick={() => console.info('Terminate agent:', agent.id)}
          >
            RETIRE WITH APPROVAL
          </button>
          <button
            type="button"
            className="drawer-btn drawer-btn--gold"
            onClick={() => console.info('Assign task to:', agent.id)}
          >
            ASSIGN TASK
          </button>
        </div>
      </aside>
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export const AgentsPage = () => {
  const storeAgents = useAgentStore(s => s.agents)
  const appAgents   = useAppStore(s => s.agents)

  const [agents,        setAgents]        = useState([])
  const [loading,       setLoading]       = useState(true)
  const [activeTab,     setActiveTab]     = useState('ALL')
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [page,          setPage]          = useState(0)
  const [manifest,      setManifest]      = useState(null)
  const [forgeAgents,   setForgeAgents]   = useState([])

  useEffect(() => {
    fetch('/api/system/manifest', { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setManifest(data))
      .catch(() => {})
    fetch('/api/forge/agents/blueprints', { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const list = Array.isArray(data?.blueprints) ? data.blueprints : []
        setForgeAgents(list.filter(item => item.registration_status === 'registered').map((item, index) => normalizeAgent({
          id: item.id,
          name: item.name,
          role: item.target_type || 'build_agent',
          status: 'idle',
          success_pct: null,
          tasks_completed: 0,
          last_active: item.registered_at || item.updated_at,
          recent_events: [`Registered by AscendForge as a supervised code/build agent`, `${item.selected_skill_ids?.length || 0} skills attached`],
          contract_key: item.id,
          created_by: 'ascend-forge',
          contract: item,
          selected_skill_ids: item.selected_skill_ids,
        }, index)))
      })
      .catch(() => {})
  }, [])

  // Hydrate from stores or API
  useEffect(() => {
    const source = storeAgents.length > 0 ? storeAgents : (appAgents || [])
    if (source.length > 0) { setAgents(mergeAgents(forgeAgents, source)); setLoading(false); return }

    fetch('/api/agents', { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const list = Array.isArray(data?.agents) ? data.agents : []
        setAgents(mergeAgents(forgeAgents, list))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [storeAgents, appAgents, forgeAgents])

  const agentContracts = manifest?.agents || {}
  const selectedContract = selectedAgent
    ? agentContracts[selectedAgent.id] ||
      agentContracts[selectedAgent.contract_key] ||
      selectedAgent.contract ||
      agentContracts[String(selectedAgent.name || '').toLowerCase().replace(/\s+/g, '-')]
    : null

  // KPI computations
  const totalAgents  = agents.length
  const activeCount  = agents.filter(a => a.status === 'active' || a.status === 'running').length
  const avgHealth    = Math.round(agents.reduce((s, a) => s + (a.health ?? 0), 0) / Math.max(1, agents.length))
  const tasksDone    = agents.reduce((s, a) => s + (a.tasks_completed ?? a.tasksCompleted ?? 0), 0)

  // Filter + paginate
  const filtered  = filterAgents(agents, activeTab)
  const pageCount = Math.ceil(filtered.length / PAGE_SIZE)
  const visible   = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const handleTabChange = useCallback((id) => {
    setActiveTab(id)
    setPage(0)
  }, [])

  const handleTileClick = useCallback((agent) => {
    setSelectedAgent(prev => prev?.id === agent.id ? null : agent)
  }, [])

  const handleDrawerClose = useCallback(() => setSelectedAgent(null), [])

  const handleSpawn = () => window.dispatchEvent(new CustomEvent('nx:spawn-agent'))

  return (
    <div className="agents-page">

      {/* TOP BAR */}
      <header className="agents-header">
        <div className="agents-kpi-row">
          <KPITile icon="⚉" iconTone="gold"    label="Total Agents" value={totalAgents || '—'} sub="REGISTERED" />
          <KPITile icon="◉" iconTone="success"  label="Active"       value={activeCount}        sub={`${totalAgents - activeCount} idle`} />
          <KPITile icon="✦" iconTone="cool"     label="Avg Health"   value={`${avgHealth}%`}    sub="MEAN" accent />
          <KPITile icon="◎" iconTone="gold"     label="Tasks Done"   value={tasksDone}           sub="COMPLETED" />
        </div>

        <div className="agents-toolbar">
          <nav className="agents-filter-bar" aria-label="Filter agents">
            {ALL_FILTER_TABS.map(tab => (
              <button
                key={tab.id}
                type="button"
                className={`filter-tab${activeTab === tab.id ? ' filter-tab--active' : ''}`}
                onClick={() => handleTabChange(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
          <button type="button" className="spawn-btn" onClick={handleSpawn} aria-label="Spawn agent">
            <span className="spawn-btn__icon">⊕</span> SPAWN AGENT
          </button>
        </div>
        <div className="agents-contract-strip">
          <span className="agents-contract-strip__label">CONTRACT SOURCE</span>
          <span className="agents-contract-strip__value">{manifest ? `${Object.keys(agentContracts).length} detailed roles loaded` : 'loading system manifest'}</span>
        </div>
      </header>

      {/* SWARM GRID */}
      <main className="agents-body">
        <div className="swarm-grid" role="list" aria-label="Agent swarm">
          {loading && <LoadingSkeleton variant="card-grid" rows={6} />}
          {!loading && visible.map(agent => (
            <AgentTile
              key={agent.id}
              agent={agent}
              selected={selectedAgent?.id === agent.id}
              onClick={handleTileClick}
            />
          ))}
          {!loading && visible.length === 0 && (
            <div className="swarm-empty">NO AGENTS MATCH THIS FILTER</div>
          )}
        </div>

        {pageCount > 1 && (
          <div className="swarm-pagination" role="navigation" aria-label="Page navigation">
            <button
              type="button"
              className="page-btn"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
              aria-label="Previous page"
            >
              ‹ PREV
            </button>
            {Array.from({ length: pageCount }, (_, i) => (
              <button
                key={i}
                type="button"
                className={`page-btn${page === i ? ' page-btn--active' : ''}`}
                onClick={() => setPage(i)}
                aria-label={`Page ${i + 1}`}
              >
                {i + 1}
              </button>
            ))}
            <button
              type="button"
              className="page-btn"
              disabled={page === pageCount - 1}
              onClick={() => setPage(p => p + 1)}
              aria-label="Next page"
            >
              NEXT ›
            </button>
          </div>
        )}
      </main>

      {/* DETAIL DRAWER */}
      {selectedAgent && (
        <DetailDrawer agent={selectedAgent} contract={selectedContract} onClose={handleDrawerClose} />
      )}
    </div>
  )
}

export default memo(AgentsPage)
