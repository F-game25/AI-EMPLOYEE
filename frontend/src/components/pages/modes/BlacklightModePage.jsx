import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../../store/appStore'
import PageHeader from '../../layout/PageHeader'
import { API_URL } from '../../../config/api'
import { eventBus, EVENTS } from '../../../utils/eventBus'

const BASE = API_URL

const STATUS_COLORS = {
  active: 'var(--success)',
  inactive: 'var(--text-muted)',
  running: 'var(--warning)',
  error: 'var(--error)',
  standby: 'var(--info)',
}

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || 'var(--text-muted)'
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      fontSize: '11px',
      fontWeight: 500,
      color,
      padding: '2px 8px',
      borderRadius: '20px',
      background: `${color}14`,
      border: `1px solid ${color}30`,
    }}>
      <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: color }} />
      {status?.toUpperCase()}
    </span>
  )
}

function MetricTile({ label, value, sub, color = 'var(--text-primary)' }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-3) var(--space-4)' }}>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '2px' }}>{sub}</div>}
    </div>
  )
}

function OperationLog({ logs }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Operation Log
      </h3>
      <div style={{ maxHeight: '240px', overflowY: 'auto' }}>
        {logs.length === 0 ? (
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
            No operations logged
          </div>
        ) : logs.map((log, i) => (
          <div key={i} style={{
            padding: 'var(--space-2) 0',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: '12px',
            display: 'flex',
            gap: 'var(--space-2)',
          }}>
            <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>
              {log.ts ? new Date(log.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--:--:--'}
            </span>
            <span style={{ color: log.level === 'error' ? 'var(--error)' : log.level === 'warning' ? 'var(--warning)' : 'var(--text-secondary)', flex: 1 }}>
              {log.message || log.notes || log.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function BlacklightModePage() {
  const navigate = useNavigate()
  const agents = useAppStore(s => s.agents)
  const systemStatus = useAppStore(s => s.systemStatus)
  const activityFeed = useAppStore(s => s.activityFeed)
  const [modeState, setModeState] = useState({
    status: 'inactive',
    activated_at: null,
    optimization_level: 0,
    hidden_ops: 0,
    agents_controlled: 0,
  })
  const [offlineMode, setOfflineMode] = useState(false)
  const [activating, setActivating] = useState(false)

  // Poll mode status
  useEffect(() => {
    const controller = new AbortController()
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BASE}/api/modes/blacklight/status`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setModeState(data || {})
          setOfflineMode(false)
        }
      } catch {
        setOfflineMode(true)
      }
    }
    fetchStatus()
    const i = setInterval(fetchStatus, 3000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  const activateBlacklight = useCallback(async () => {
    setActivating(true)
    try {
      const res = await fetch(`${BASE}/api/modes/blacklight/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: 'full' }),
      })
      if (res.ok) {
        const data = await res.json()
        setModeState(prev => ({ ...prev, status: 'active', ...data }))
        eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'blacklight' })
      } else {
        // Fallback: set locally with offline label
        setModeState(prev => ({ ...prev, status: 'active', activated_at: Date.now() }))
        eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'blacklight', offline: true })
      }
    } catch {
      setModeState(prev => ({ ...prev, status: 'active', activated_at: Date.now() }))
      eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'blacklight', offline: true })
    }
    setActivating(false)
  }, [])

  const deactivateBlacklight = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/modes/blacklight/deactivate`, { method: 'POST' })
    } catch { /* ignore */ }
    setModeState(prev => ({ ...prev, status: 'inactive' }))
    eventBus.emit(EVENTS.MODE_DEACTIVATED, { mode: 'blacklight' })
  }, [])

  const isActive = modeState.status === 'active' || modeState.status === 'running'
  const activeAgents = agents.filter(a => a.status === 'running' || a.status === 'busy')

  return (
    <div className="page-enter">
      <PageHeader
        title="Blacklight Mode"
        subtitle="System optimization engine — advanced agent control and hidden operations layer"
      />

      {offlineMode && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.2)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--warning)',
        }}>
          ⚠ OFFLINE MODE — Backend unreachable. Mode state is managed locally.
        </div>
      )}

      {/* Status + activation */}
      <div className="ds-card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-1)' }}>
              <span style={{ fontSize: '20px' }}>◈</span>
              <span style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                Blacklight Mode
              </span>
              <StatusBadge status={modeState.status} />
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', paddingLeft: '34px' }}>
              Advanced stealth optimization — all agents brought to full capacity
            </div>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {!isActive ? (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={activateBlacklight}
                disabled={activating}
                style={{
                  padding: 'var(--space-3) var(--space-5)',
                  background: 'rgba(212, 175, 55, 0.1)',
                  border: '1px solid rgba(212, 175, 55, 0.4)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--gold)',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: activating ? 'wait' : 'pointer',
                  fontFamily: 'inherit',
                  opacity: activating ? 0.7 : 1,
                }}
              >
                {activating ? 'Activating...' : '⚡ Activate'}
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                onClick={deactivateBlacklight}
                style={{
                  padding: 'var(--space-3) var(--space-5)',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--error)',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                ✕ Deactivate
              </motion.button>
            )}
          </div>
        </div>

        {modeState.activated_at && (
          <div style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
            Activated: {new Date(modeState.activated_at).toLocaleString()}
          </div>
        )}
      </div>

      {/* Metrics grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        <MetricTile
          label="System Optimization"
          value={`${modeState.optimization_level ?? 0}%`}
          sub="Current level"
          color={isActive ? 'var(--success)' : 'var(--text-muted)'}
        />
        <MetricTile
          label="Active Agents"
          value={activeAgents.length}
          sub={`of ${agents.length} total`}
          color="var(--info)"
        />
        <MetricTile
          label="CPU Usage"
          value={`${systemStatus?.cpu_usage ?? 0}%`}
          sub="Real-time"
          color={systemStatus?.cpu_usage > 80 ? 'var(--error)' : 'var(--text-primary)'}
        />
        <MetricTile
          label="Hidden Ops"
          value={modeState.hidden_ops ?? 0}
          sub="Background tasks"
          color="var(--warning)"
        />
      </div>

      {/* Agent control + op log */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
        {/* Advanced agent control */}
        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Advanced Agent Control
          </h3>
          {activeAgents.length === 0 ? (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
              No active agents — activate Blacklight Mode to engage
            </div>
          ) : (
            activeAgents.map((agent, i) => (
              <div key={agent.id || i} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-3)',
                padding: 'var(--space-3) 0',
                borderBottom: '1px solid var(--border-subtle)',
              }}>
                <span style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: 'var(--success)',
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                    {agent.name || agent.id}
                  </div>
                  {agent.current_task && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {agent.current_task}
                    </div>
                  )}
                </div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => navigate('/command-center')}
                  style={{
                    padding: '3px 10px',
                    background: 'transparent',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-secondary)',
                    fontSize: '11px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  Route
                </motion.button>
              </div>
            ))
          )}
        </div>

        {/* Operation log */}
        <OperationLog logs={activityFeed.slice(0, 20)} />
      </div>
    </div>
  )
}
