import { useState, useEffect, useCallback, useRef } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../../store/appStore'
import PageHeader from '../../layout/PageHeader'
import { API_URL } from '../../../config/api'
import { eventBus, EVENTS } from '../../../utils/eventBus'

const BASE = API_URL

function ProgressBar({ value, color = 'var(--success)', height = 6 }) {
  return (
    <div style={{ height, background: 'var(--bg-base)', borderRadius: height / 2, overflow: 'hidden' }}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(Math.max(value, 0), 100)}%` }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        style={{ height: '100%', background: color, borderRadius: height / 2 }}
      />
    </div>
  )
}

function RevenueMetric({ label, value, sub, color = 'var(--text-primary)', large = false }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: large ? '28px' : '22px', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '3px' }}>{sub}</div>}
    </div>
  )
}

function PipelineCard({ name, status, progress, onRun, running }) {
  const statusColors = { idle: 'var(--text-muted)', running: 'var(--warning)', completed: 'var(--success)', error: 'var(--error)' }
  const color = statusColors[status] || statusColors.idle
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
        <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>{name}</span>
        <span style={{
          fontSize: '11px',
          color,
          padding: '2px 8px',
          background: `${color}14`,
          borderRadius: '20px',
          border: `1px solid ${color}30`,
        }}>
          {status}
        </span>
      </div>
      {progress > 0 && (
        <div style={{ marginBottom: 'var(--space-2)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            <span>Progress</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <ProgressBar value={progress} color={color} />
        </div>
      )}
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
        onClick={onRun}
        disabled={running || status === 'running'}
        style={{
          width: '100%',
          padding: 'var(--space-2)',
          background: 'transparent',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-secondary)',
          fontSize: '12px',
          cursor: running || status === 'running' ? 'not-allowed' : 'pointer',
          fontFamily: 'inherit',
          opacity: running ? 0.6 : 1,
        }}
      >
        {status === 'running' ? 'Running...' : '▶ Run Pipeline'}
      </motion.button>
    </div>
  )
}

const INITIAL_PIPELINES = [
  { id: 'content', name: 'Content Pipeline', status: 'idle', progress: 0 },
  { id: 'lead', name: 'Lead Generation', status: 'idle', progress: 0 },
  { id: 'opportunity', name: 'Opportunity Pipeline', status: 'idle', progress: 0 },
]

export default function MoneyModePage() {
  const moneyMode = useAppStore(s => s.objectivePanels?.money_mode || {})
  const productMetrics = useAppStore(s => s.productMetrics)
  const [pipelines, setPipelines] = useState(INITIAL_PIPELINES)
  const [goal, setGoal] = useState('')
  const [launching, setLaunching] = useState(false)
  const [offlineMode, setOfflineMode] = useState(false)
  const [localState, setLocalState] = useState(null)
  const [runningPipeline, setRunningPipeline] = useState(null)
  const simTickRef = useRef(null) // tracks offline simulation interval for cleanup

  // Clean up any pending simulation tick on unmount
  useEffect(() => () => { if (simTickRef.current) clearInterval(simTickRef.current) }, [])

  const state = localState || moneyMode

  // Poll money mode status
  useEffect(() => {
    const controller = new AbortController()
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BASE}/api/money/status`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setLocalState(data || {})
          setOfflineMode(false)
        }
      } catch {
        setOfflineMode(true)
      }
    }
    fetchStatus()
    const i = setInterval(fetchStatus, 5000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  const activateMoneyMode = useCallback(async () => {
    if (!goal.trim()) return
    setLaunching(true)
    const optimistic = {
      active: true,
      status: 'running',
      current_objective: { goal: goal.trim() },
      progress: 0,
      active_tasks: [],
      agents_used: [],
      performance: {},
    }
    setLocalState(optimistic)
    try {
      const res = await fetch(`${BASE}/api/money/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal.trim() }),
      })
      if (res.ok) {
        const data = await res.json()
        setLocalState(prev => ({ ...prev, ...data }))
        eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'money_mode', goal: goal.trim() })
      }
    } catch {
      eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'money_mode', offline: true })
    }
    setLaunching(false)
    setGoal('')
  }, [goal])

  const deactivateMoneyMode = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/money/deactivate`, { method: 'POST' })
    } catch { /* ignore */ }
    setLocalState(null)
    eventBus.emit(EVENTS.MODE_DEACTIVATED, { mode: 'money_mode' })
  }, [])

  const runPipeline = useCallback(async (pipelineId) => {
    setRunningPipeline(pipelineId)
    setPipelines(prev => prev.map(p => p.id === pipelineId ? { ...p, status: 'running', progress: 0 } : p))
    try {
      const endpoints = {
        content: '/api/money/content-pipeline',
        lead: '/api/money/lead-pipeline',
        opportunity: '/api/money/opportunity-pipeline',
      }
      const res = await fetch(`${BASE}${endpoints[pipelineId]}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: false }),
      })
      if (res.ok) {
        const data = await res.json()
        setPipelines(prev => prev.map(p => p.id === pipelineId
          ? { ...p, status: data?.status || 'completed', progress: data?.progress ?? 100 }
          : p
        ))
      } else {
        setPipelines(prev => prev.map(p => p.id === pipelineId ? { ...p, status: 'error' } : p))
      }
      setRunningPipeline(null)
    } catch {
      // Simulate progress for offline mode — interval tracked in ref for cleanup on unmount
      if (simTickRef.current) clearInterval(simTickRef.current)
      let progress = 0
      simTickRef.current = setInterval(() => {
        progress += 10
        setPipelines(prev => prev.map(p => p.id === pipelineId ? { ...p, progress } : p))
        if (progress >= 100) {
          clearInterval(simTickRef.current)
          simTickRef.current = null
          setPipelines(prev => prev.map(p => p.id === pipelineId ? { ...p, status: 'completed', progress: 100 } : p))
          setRunningPipeline(null)
        }
      }, 300)
    }
  }, [])

  const isActive = state?.active || state?.status === 'running'
  const perf = state?.performance || {}
  const progress = state?.progress ?? 0
  const revenueData = productMetrics?.revenue || {}

  return (
    <div className="page-enter">
      <PageHeader
        title="Money Mode"
        subtitle="Monetization workflows and revenue tracking"
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
          ⚠ OFFLINE MODE — Backend unreachable. Pipeline results simulated locally.
        </div>
      )}

      {/* Activation panel */}
      <div className="ds-card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          <span style={{ fontSize: '20px' }}>💰</span>
          <div>
            <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Money Mode
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Status: <span style={{ color: isActive ? 'var(--success)' : 'var(--text-dim)' }}>
                {state?.status || 'inactive'}
              </span>
            </div>
          </div>
        </div>

        {!isActive ? (
          <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
            <input
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') activateMoneyMode() }}
              placeholder="Enter revenue objective (e.g. generate 10 qualified leads this week)..."
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                background: 'var(--bg-base)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontSize: '13px',
                fontFamily: 'inherit',
                outline: 'none',
              }}
            />
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={activateMoneyMode}
              disabled={!goal.trim() || launching}
              style={{
                padding: 'var(--space-3) var(--space-5)',
                background: 'rgba(34, 197, 94, 0.1)',
                border: '1px solid rgba(34, 197, 94, 0.4)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--success)',
                fontSize: '14px',
                fontWeight: 600,
                cursor: !goal.trim() || launching ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
                opacity: !goal.trim() ? 0.5 : 1,
              }}
            >
              {launching ? 'Activating...' : '💰 Activate'}
            </motion.button>
          </div>
        ) : (
          <div>
            <div style={{ marginBottom: 'var(--space-3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-1)', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                  {state?.current_objective?.goal || 'Active objective'}
                </span>
                <span style={{ color: 'var(--success)' }}>{Math.round(progress)}%</span>
              </div>
              <ProgressBar value={progress} color="var(--success)" />
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={deactivateMoneyMode}
              style={{
                padding: 'var(--space-2) var(--space-4)',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--error)',
                fontSize: '13px',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Stop Mode
            </motion.button>
          </div>
        )}
      </div>

      {/* Revenue metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        <RevenueMetric
          label="Leads Generated"
          value={perf?.leads_generated ?? revenueData?.leads_generated ?? 0}
          sub="All time"
          color="var(--success)"
          large
        />
        <RevenueMetric
          label="Emails Sent"
          value={perf?.emails_sent ?? 0}
          sub="This session"
          color="var(--info)"
        />
        <RevenueMetric
          label="Conversion Rate"
          value={`${perf?.conversion_pct ?? 0}%`}
          sub="Lead → opportunity"
          color="var(--warning)"
        />
        <RevenueMetric
          label="Active Tasks"
          value={(state?.active_tasks || []).length}
          sub="In progress"
          color="var(--gold)"
        />
      </div>

      {/* Pipelines */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          Monetization Pipelines
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-3)' }}>
          {pipelines.map((p) => (
            <PipelineCard
              key={p.id}
              name={p.name}
              status={p.status}
              progress={p.progress}
              running={runningPipeline === p.id}
              onRun={() => runPipeline(p.id)}
            />
          ))}
        </div>
      </div>

      {/* Active tasks */}
      {(state?.active_tasks || []).length > 0 && (
        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Active Tasks
          </h3>
          {(state.active_tasks || []).map((task, i) => (
            <div key={i} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-3)',
              padding: 'var(--space-2) 0',
              borderBottom: '1px solid var(--border-subtle)',
              fontSize: '13px',
            }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--warning)', flexShrink: 0 }} />
              <span style={{ flex: 1, color: 'var(--text-primary)' }}>
                {typeof task === 'string' ? task : task.description || task.id || JSON.stringify(task)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
