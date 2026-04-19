import { useState, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

// ── helpers ───────────────────────────────────────────────────────────────────

function riskColor(score) {
  if (score >= 0.7) return 'var(--error)'
  if (score >= 0.3) return 'var(--warning)'
  return 'var(--success)'
}

function riskLabel(score) {
  if (score >= 0.7) return 'HIGH'
  if (score >= 0.3) return 'MEDIUM'
  return 'LOW'
}

function stabilityColor(score) {
  if (score >= 0.75) return 'var(--success)'
  if (score >= 0.4) return 'var(--warning)'
  return 'var(--error)'
}

function SectionCard({ title, children, style }) {
  return (
    <div
      className="ds-card"
      style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)', ...style }}
    >
      <h3
        style={{
          fontSize: '13px',
          fontWeight: 500,
          color: 'var(--text-secondary)',
          marginBottom: 'var(--space-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  )
}

function MetricRow({ label, value, valueColor }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 'var(--space-2) 0',
        borderBottom: '1px solid var(--border-subtle)',
        fontSize: '13px',
      }}
    >
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: valueColor || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
    </div>
  )
}

// ── A. System Health Panel ────────────────────────────────────────────────────

function SystemHealthPanel() {
  const [health, setHealth] = useState(null)
  const [reliability, setReliability] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [sysRes, relRes] = await Promise.all([
        fetch(`${BASE}/api/system/stats`),
        fetch(`${BASE}/api/reliability/status`),
      ])
      const [sysData, relData] = await Promise.all([sysRes.json(), relRes.json()])
      setHealth(sysData)
      setReliability(relData)
    } catch (_) {}
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [refresh])

  const score = reliability?.stability_score ?? 1.0

  return (
    <SectionCard title="System Health">
      <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <div
          className="ds-card"
          style={{
            flex: 1,
            padding: 'var(--space-3)',
            textAlign: 'center',
            background: 'var(--surface-2)',
          }}
        >
          <div
            style={{
              fontSize: '24px',
              fontWeight: 700,
              color: stabilityColor(score),
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {(score * 100).toFixed(0)}%
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Stability Score</div>
        </div>
        <div
          className="ds-card"
          style={{
            flex: 1,
            padding: 'var(--space-3)',
            textAlign: 'center',
            background: 'var(--surface-2)',
          }}
        >
          <div
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: reliability?.forge_frozen ? 'var(--error)' : 'var(--success)',
            }}
          >
            {reliability?.forge_frozen ? '🔒 FROZEN' : '✅ ACTIVE'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Forge Status</div>
        </div>
      </div>
      <MetricRow label="CPU Usage" value={`${health?.cpu_usage ?? '—'}%`} />
      <MetricRow label="Memory" value={`${health?.memory ?? '—'}%`} />
      <MetricRow label="Active Agents" value={health?.running_agents ?? '—'} />
      <MetricRow
        label="Forge Frozen"
        value={reliability?.forge_frozen ? `Yes — ${reliability.freeze_reason || 'manual'}` : 'No'}
        valueColor={reliability?.forge_frozen ? 'var(--error)' : 'var(--success)'}
      />
      <MetricRow
        label="Last Evaluated"
        value={reliability?.last_evaluated ? new Date(reliability.last_evaluated).toLocaleTimeString() : '—'}
      />
      {reliability?.forge_frozen && (
        <button
          className="ds-btn ds-btn--ghost"
          style={{ marginTop: 'var(--space-3)', fontSize: '12px' }}
          onClick={async () => {
            try {
              await fetch(`${BASE}/api/reliability/forge/unfreeze`, { method: 'POST' })
              refresh()
            } catch (_) {}
          }}
        >
          Unfreeze Forge
        </button>
      )}
    </SectionCard>
  )
}

// ── B. Audit Log Viewer ───────────────────────────────────────────────────────

function AuditLogViewer() {
  const [events, setEvents] = useState([])
  const [total, setTotal] = useState(0)
  const [actorFilter, setActorFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [minRisk, setMinRisk] = useState(0)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: 100 })
      if (actorFilter) params.set('actor', actorFilter)
      if (actionFilter) params.set('action', actionFilter)
      if (minRisk > 0) params.set('min_risk', String(minRisk))
      const res = await fetch(`${BASE}/api/audit/events?${params}`)
      const data = await res.json()
      setEvents(data.events || [])
      setTotal(data.total || 0)
    } catch (_) {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [actorFilter, actionFilter, minRisk])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 8000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <SectionCard title={`Audit Log (${total} total)`}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)', flexWrap: 'wrap' }}>
        <input
          className="ds-input"
          placeholder="Filter actor…"
          value={actorFilter}
          onChange={(e) => setActorFilter(e.target.value)}
          style={{ fontSize: '12px', padding: 'var(--space-1) var(--space-2)', flex: 1, minWidth: 100 }}
        />
        <input
          className="ds-input"
          placeholder="Filter action…"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          style={{ fontSize: '12px', padding: 'var(--space-1) var(--space-2)', flex: 1, minWidth: 100 }}
        />
        <select
          className="ds-input"
          value={String(minRisk)}
          onChange={(e) => setMinRisk(parseFloat(e.target.value))}
          style={{ fontSize: '12px', padding: 'var(--space-1) var(--space-2)' }}
        >
          <option value="0">All risk</option>
          <option value="0.3">Medium+</option>
          <option value="0.6">High only</option>
        </select>
        <button className="ds-btn ds-btn--ghost" onClick={refresh} style={{ fontSize: '12px' }}>
          {loading ? '…' : '↻'}
        </button>
      </div>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        {events.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: 'var(--space-3) 0' }}>
            No audit events found.
          </div>
        ) : (
          events.map((evt) => (
            <div
              key={evt.id}
              style={{
                borderBottom: '1px solid var(--border-subtle)',
                padding: 'var(--space-2) 0',
                fontSize: '12px',
                display: 'grid',
                gridTemplateColumns: '90px 1fr auto',
                gap: 'var(--space-2)',
                alignItems: 'center',
              }}
            >
              <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                {new Date(evt.ts).toLocaleTimeString()}
              </span>
              <span>
                <span style={{ color: 'var(--text-secondary)' }}>{evt.actor}</span>
                <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>→</span>
                <span style={{ color: 'var(--text-primary)' }}>{evt.action}</span>
              </span>
              <span
                style={{
                  color: riskColor(evt.risk_score),
                  fontWeight: 600,
                  fontSize: '11px',
                  letterSpacing: '0.04em',
                }}
              >
                {riskLabel(evt.risk_score)}
              </span>
            </div>
          ))
        )}
      </div>
    </SectionCard>
  )
}

// ── C. Forge Change Request Panel ─────────────────────────────────────────────

function ForgeChangesPanel() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [goal, setGoal] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${BASE}/api/forge/queue`)
      const data = await res.json()
      setItems(data.items || [])
    } catch (_) {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const submit = async () => {
    const g = goal.trim()
    if (!g) return
    try {
      await fetch(`${BASE}/api/forge/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: g, submitted_by: 'operator' }),
      })
      setGoal('')
      refresh()
    } catch (_) {}
  }

  const decide = async (id, action) => {
    try {
      await fetch(`${BASE}/api/forge/${action}/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [`${action}d_by`]: 'operator' }),
      })
      refresh()
    } catch (_) {}
  }

  return (
    <SectionCard title="Forge Change Queue">
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <input
          className="ds-input"
          placeholder="Describe a Forge change goal…"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          style={{ flex: 1, fontSize: '12px', padding: 'var(--space-2) var(--space-3)' }}
        />
        <button className="ds-btn ds-btn--primary" onClick={submit} style={{ fontSize: '12px' }}>
          Submit
        </button>
        <button className="ds-btn ds-btn--ghost" onClick={refresh} style={{ fontSize: '12px' }}>
          {loading ? '…' : '↻'}
        </button>
      </div>
      <div style={{ maxHeight: 300, overflowY: 'auto' }}>
        {items.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: 'var(--space-2) 0' }}>
            No pending change requests.
          </div>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              style={{
                borderBottom: '1px solid var(--border-subtle)',
                padding: 'var(--space-3) 0',
                fontSize: '12px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ color: 'var(--text-primary)', flex: 1, marginRight: 8 }}>{item.goal}</span>
                <span
                  style={{
                    color: riskColor(item.risk_score),
                    fontWeight: 600,
                    fontSize: '11px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {item.risk_level}
                </span>
              </div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: 'var(--text-muted)' }}>
                  Status:{' '}
                  <span
                    style={{
                      color:
                        item.status === 'approved' || item.status === 'sandbox_passed'
                          ? 'var(--success)'
                          : item.status === 'rejected'
                          ? 'var(--error)'
                          : 'var(--warning)',
                    }}
                  >
                    {item.status}
                  </span>
                </span>
                {item.status === 'pending' && (
                  <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                    <button
                      className="ds-btn ds-btn--ghost"
                      style={{ fontSize: '11px', color: 'var(--success)' }}
                      onClick={() => decide(item.id, 'approve')}
                    >
                      ✓ Approve
                    </button>
                    <button
                      className="ds-btn ds-btn--ghost"
                      style={{ fontSize: '11px', color: 'var(--error)' }}
                      onClick={() => decide(item.id, 'reject')}
                    >
                      ✗ Reject
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </SectionCard>
  )
}

// ── D. Memory Inspector ───────────────────────────────────────────────────────

function MemoryInspectorPanel() {
  const [tree, setTree] = useState(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${BASE}/api/memory/tree`)
      const data = await res.json()
      setTree(data)
    } catch (_) {
      setTree(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const layers = tree
    ? [
        { label: 'Short-term cache', value: tree.short_term_count ?? tree.short_term?.length ?? '—' },
        { label: 'Vector store entries', value: tree.vector_store_count ?? tree.vector?.length ?? '—' },
        { label: 'Knowledge store entries', value: tree.knowledge_count ?? tree.knowledge?.length ?? '—' },
        { label: 'Last updated', value: tree.updated_at ? new Date(tree.updated_at).toLocaleTimeString() : '—' },
      ]
    : []

  return (
    <SectionCard title="Memory Inspector">
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--space-2)' }}>
        <button className="ds-btn ds-btn--ghost" onClick={refresh} style={{ fontSize: '12px' }}>
          {loading ? '…' : '↻ Refresh'}
        </button>
      </div>
      {!tree ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          {loading ? 'Loading memory state…' : 'Memory data unavailable.'}
        </div>
      ) : (
        layers.map((l) => <MetricRow key={l.label} label={l.label} value={l.value} />)
      )}
      {tree && (
        <div
          style={{
            marginTop: 'var(--space-3)',
            padding: 'var(--space-2)',
            background: 'var(--surface-2)',
            borderRadius: '4px',
            fontSize: '11px',
            color: 'var(--text-muted)',
          }}
        >
          Memory mutations are audited via the Audit Log. Rollback requires operator
          approval through the Forge Change Queue.
        </div>
      )}
    </SectionCard>
  )
}

// ── E. Agent Activity Monitor ─────────────────────────────────────────────────

function AgentActivityMonitor() {
  const [snap, setSnap] = useState(null)
  const [anomalies, setAnomalies] = useState([])

  const refresh = useCallback(async () => {
    try {
      const [snapRes, auditRes] = await Promise.all([
        fetch(`${BASE}/api/observability/snapshot`),
        fetch(`${BASE}/api/audit/events?min_risk=0.6&limit=20`),
      ])
      const [snapData, auditData] = await Promise.all([snapRes.json(), auditRes.json()])
      setSnap(snapData)
      setAnomalies((auditData.events || []).filter((e) => e.risk_score >= 0.6))
    } catch (_) {}
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 6000)
    return () => clearInterval(id)
  }, [refresh])

  const agents = snap?.agent_grid || []

  return (
    <SectionCard title="Agent Activity Monitor">
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: 'var(--space-2)',
          marginBottom: 'var(--space-3)',
        }}
      >
        {agents.slice(0, 12).map((a) => (
          <div
            key={a.id}
            className="ds-card"
            style={{
              padding: 'var(--space-2)',
              background: 'var(--surface-2)',
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {a.name || a.id}
            </span>
            <span
              style={{
                fontSize: '11px',
                color:
                  a.status === 'running'
                    ? 'var(--success)'
                    : a.status === 'error'
                    ? 'var(--error)'
                    : 'var(--text-muted)',
              }}
            >
              ● {a.status || 'idle'}
            </span>
          </div>
        ))}
        {agents.length === 0 && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No agents reporting.</span>
        )}
      </div>

      {anomalies.length > 0 && (
        <>
          <div
            style={{
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--error)',
              marginBottom: 'var(--space-2)',
            }}
          >
            ⚠ High-risk events detected
          </div>
          {anomalies.slice(0, 5).map((evt) => (
            <div
              key={evt.id}
              style={{
                borderBottom: '1px solid var(--border-subtle)',
                padding: 'var(--space-2) 0',
                fontSize: '12px',
              }}
            >
              <span style={{ color: 'var(--text-muted)' }}>
                {new Date(evt.ts).toLocaleTimeString()}
              </span>
              {'  '}
              <span style={{ color: 'var(--error)' }}>{evt.action}</span>
              {'  '}
              <span style={{ color: 'var(--text-secondary)' }}>{evt.actor}</span>
            </div>
          ))}
        </>
      )}

      <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Tasks/min:{' '}
          <strong>{snap?.metrics?.tasks_per_minute ?? '—'}</strong>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Errors/min:{' '}
          <strong style={{ color: (snap?.metrics?.errors_per_minute || 0) > 3 ? 'var(--error)' : 'inherit' }}>
            {snap?.metrics?.errors_per_minute ?? '—'}
          </strong>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Latency: <strong>{snap?.metrics?.latency_ms ?? '—'} ms</strong>
        </div>
      </div>
    </SectionCard>
  )
}

// ── Control Center Page ───────────────────────────────────────────────────────

const TABS = [
  { id: 'health', label: 'System Health' },
  { id: 'audit', label: 'Audit Log' },
  { id: 'forge', label: 'Forge Queue' },
  { id: 'memory', label: 'Memory' },
  { id: 'agents', label: 'Agents' },
]

export default function ControlCenterPage() {
  const [activeTab, setActiveTab] = useState('health')

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto' }}
    >
      <PageHeader
        title="Control Center"
        subtitle="Enterprise observability, audit, and Forge governance"
      />

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          marginBottom: 'var(--space-4)',
          borderBottom: '1px solid var(--border-subtle)',
          padding: '0 var(--space-4)',
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 'var(--space-2) var(--space-3)',
              fontSize: '13px',
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
              borderBottom: activeTab === tab.id ? '2px solid var(--gold)' : '2px solid transparent',
              fontWeight: activeTab === tab.id ? 600 : 400,
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div style={{ padding: '0 var(--space-4)', flex: 1 }}>
        {activeTab === 'health' && <SystemHealthPanel />}
        {activeTab === 'audit' && <AuditLogViewer />}
        {activeTab === 'forge' && <ForgeChangesPanel />}
        {activeTab === 'memory' && <MemoryInspectorPanel />}
        {activeTab === 'agents' && <AgentActivityMonitor />}
      </div>
    </motion.div>
  )
}
