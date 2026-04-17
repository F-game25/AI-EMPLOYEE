import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

function GradeIndicator({ grade }) {
  const gradeConfig = {
    A: { color: 'var(--success)', label: 'Excellent' },
    B: { color: 'var(--info)', label: 'Good' },
    C: { color: 'var(--warning)', label: 'Fair' },
    D: { color: 'var(--error)', label: 'Poor' },
    F: { color: 'var(--error)', label: 'Critical' },
  }
  const cfg = gradeConfig[grade] || { color: 'var(--text-muted)', label: 'Unknown' }

  return (
    <div style={{ textAlign: 'center', padding: 'var(--space-4)' }}>
      <div style={{
        width: '80px',
        height: '80px',
        borderRadius: '50%',
        border: `4px solid ${cfg.color}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '0 auto var(--space-2)',
        boxShadow: `0 0 24px ${cfg.color}40`,
      }}>
        <span style={{ fontSize: '32px', fontWeight: 700, color: cfg.color }}>{grade || '—'}</span>
      </div>
      <div style={{ fontSize: '14px', color: cfg.color, fontWeight: 500 }}>{cfg.label}</div>
    </div>
  )
}

function HealthBar({ label, score, color }) {
  const pct = Math.min(Math.max(score ?? 0, 0), 100)
  const autoColor = pct >= 80 ? 'var(--success)' : pct >= 60 ? 'var(--warning)' : 'var(--error)'
  const barColor = color || autoColor

  return (
    <div style={{ marginBottom: 'var(--space-3)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px' }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ color: barColor, fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{Math.round(pct)}%</span>
      </div>
      <div style={{ height: '6px', background: 'var(--bg-base)', borderRadius: '3px', overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          style={{ height: '100%', background: barColor, borderRadius: '3px' }}
        />
      </div>
    </div>
  )
}

function IssueItem({ issue }) {
  const severityColor = {
    critical: 'var(--error)',
    error: 'var(--error)',
    warning: 'var(--warning)',
    info: 'var(--info)',
  }
  const severity = typeof issue === 'string' ? 'info' : (issue.severity || 'info')
  const message = typeof issue === 'string' ? issue : (issue.message || issue.description || JSON.stringify(issue))
  const color = severityColor[severity] || 'var(--text-secondary)'

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: 'var(--space-2)',
      padding: 'var(--space-2) 0',
      borderBottom: '1px solid var(--border-subtle)',
      fontSize: '13px',
    }}>
      <span style={{
        fontSize: '11px',
        color,
        padding: '1px 6px',
        background: `${color}14`,
        borderRadius: '4px',
        flexShrink: 0,
        marginTop: '1px',
      }}>
        {severity}
      </span>
      <span style={{ color: 'var(--text-primary)', flex: 1 }}>{message}</span>
    </div>
  )
}

function RadialGauge({ label, value, color }) {
  const size = 100
  const stroke = 7
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.max(0, Math.min(value, 100)) / 100) * circumference

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label={`${label}: ${Math.round(value)}%`}>
        <circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x={size / 2} y={size / 2 - 4} textAnchor="middle" fontSize="16" fontWeight="600" fill={color}>{Math.round(value)}</text>
        <text x={size / 2} y={size / 2 + 12} textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.4)">%</text>
      </svg>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>{label}</div>
    </div>
  )
}

export default function HealthPage() {
  const doctorStatus = useAppStore(s => s.doctorStatus)
  const systemStatus = useAppStore(s => s.systemStatus)
  const agents = useAppStore(s => s.agents)
  const autonomyStatus = useAppStore(s => s.autonomyStatus)
  const [loading, setLoading] = useState(false)
  const [offlineMode, setOfflineMode] = useState(false)
  const [localDoctor, setLocalDoctor] = useState(null)
  const setDoctorStatus = useAppStore(s => s.setDoctorStatus)

  const runHealthCheck = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${BASE}/api/doctor/run`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setDoctorStatus(data)
        setLocalDoctor(null)
        setOfflineMode(false)
      } else {
        setOfflineMode(true)
      }
    } catch {
      setOfflineMode(true)
    }
    setLoading(false)
  }, [setDoctorStatus])

  // Auto-fetch on mount
  useEffect(() => {
    const controller = new AbortController()
    const fetch_ = async () => {
      try {
        const res = await fetch(`${BASE}/api/doctor/status`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setDoctorStatus(data)
          setOfflineMode(false)
        }
      } catch {
        setOfflineMode(true)
      }
    }
    fetch_()
    const i = setInterval(fetch_, 15000)
    return () => { clearInterval(i); controller.abort() }
  }, [setDoctorStatus])

  const doctor = localDoctor || doctorStatus

  // Compute dynamic health metrics from live data
  const activeAgents = agents.filter(a => a.status === 'running' || a.status === 'busy').length
  const totalAgents = agents.length || systemStatus?.total_agents || 0
  const agentLoad = totalAgents > 0 ? Math.round((activeAgents / totalAgents) * 100) : 0
  const queueDepth = autonomyStatus?.queue?.total || 0
  const consecutiveErrors = autonomyStatus?.daemon?.consecutive_errors || 0
  const errorScore = Math.max(0, 100 - consecutiveErrors * 20)

  const scores = doctor?.scores || {}
  const computedScores = {
    'CPU': systemStatus?.cpu_usage != null ? Math.round(100 - systemStatus.cpu_usage) : null,
    'Memory': systemStatus?.memory != null ? Math.round(100 - systemStatus.memory) : null,
    'Agent Load': agentLoad,
    'Error Rate': errorScore,
    ...(typeof scores === 'object' ? scores : {}),
  }

  const overallScore = doctor?.overall_score ?? Math.round(
    Object.values(computedScores).filter(v => v != null).reduce((sum, v) => sum + v, 0) /
    Math.max(1, Object.values(computedScores).filter(v => v != null).length)
  )

  const gaugeItems = [
    { label: 'CPU', value: systemStatus?.cpu_usage ?? 0, color: 'var(--neon-teal)' },
    { label: 'RAM', value: systemStatus?.memory ?? 0, color: 'var(--neon-amber)' },
    { label: 'GPU', value: systemStatus?.gpu_usage ?? 0, color: 'var(--neon-cyan)' },
    { label: 'Agents', value: agentLoad, color: 'var(--success)' },
  ]

  return (
    <div className="page-enter">
      <PageHeader
        title="System Health"
        subtitle="Real-time diagnostics computed from agent load, task queue, and error logs"
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
          ⚠ OFFLINE MODE — Doctor service unreachable. Showing computed metrics from live data.
        </div>
      )}

      {doctor?.data_source === 'simulated' && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.2)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--warning)',
        }}>
          SIMULATED DATA — Python backend offline
        </div>
      )}

      {/* Top row: Grade + gauges + run button */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr auto', gap: 'var(--space-4)', marginBottom: 'var(--space-4)', alignItems: 'start' }}>
        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <GradeIndicator grade={doctor?.grade} />
          <div style={{ textAlign: 'center', fontSize: '12px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            Overall: {Math.round(overallScore)}%
          </div>
          {doctor?.last_run && (
            <div style={{ textAlign: 'center', fontSize: '11px', color: 'var(--text-dim)', marginTop: 'var(--space-1)' }}>
              Last run: {new Date(doctor.last_run).toLocaleTimeString()}
            </div>
          )}
        </div>

        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
            {gaugeItems.map((item) => (
              <RadialGauge key={item.label} label={item.label} value={item.value} color={item.color} />
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={runHealthCheck}
            disabled={loading}
            style={{
              padding: 'var(--space-3) var(--space-5)',
              background: 'rgba(212, 175, 55, 0.1)',
              border: '1px solid rgba(212, 175, 55, 0.4)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--gold)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: loading ? 'wait' : 'pointer',
              fontFamily: 'inherit',
              whiteSpace: 'nowrap',
            }}
          >
            {loading ? 'Running...' : '♥ Run Diagnostics'}
          </motion.button>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center' }}>
            {queueDepth} tasks queued
          </div>
          <div style={{ fontSize: '11px', color: consecutiveErrors > 0 ? 'var(--error)' : 'var(--text-dim)', textAlign: 'center' }}>
            {consecutiveErrors} consecutive errors
          </div>
        </div>
      </div>

      {/* Score breakdown + issues */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-4)' }}>
            Score Breakdown
          </h3>
          {Object.entries(computedScores).map(([key, value]) => value != null ? (
            <HealthBar key={key} label={key} score={value} />
          ) : null)}
        </div>

        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Issues {doctor?.issues?.length > 0 ? `(${doctor.issues.length})` : ''}
          </h3>
          {(!doctor?.issues || doctor.issues.length === 0) ? (
            <div style={{ fontSize: '13px', color: 'var(--success)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
              ✓ No issues detected
            </div>
          ) : (
            doctor.issues.map((issue, i) => <IssueItem key={i} issue={issue} />)
          )}

          {(doctor?.strengths || []).length > 0 && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <h4 style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
                Strengths
              </h4>
              {doctor.strengths.map((s, i) => (
                <div key={i} style={{ fontSize: '12px', color: 'var(--success)', padding: 'var(--space-1) 0' }}>
                  ✓ {typeof s === 'string' ? s : s.message || JSON.stringify(s)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Live system stats */}
      <div className="ds-card" style={{ padding: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          Live System Stats
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 'var(--space-3)' }}>
          {[
            { label: 'Heartbeat', value: systemStatus?.heartbeat ?? 0 },
            { label: 'Uptime (s)', value: systemStatus?.uptime ?? 0 },
            { label: 'Active Agents', value: `${activeAgents} / ${totalAgents}` },
            { label: 'Task Queue', value: queueDepth },
            { label: 'WS Connections', value: systemStatus?.connections ?? 0 },
            { label: 'CPU Temp', value: `${systemStatus?.cpu_temperature ?? 0}°C` },
          ].map(({ label, value }) => (
            <div key={label} style={{ padding: 'var(--space-3)', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
