import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../../store/appStore'
import PageHeader from '../../layout/PageHeader'
import { API_URL } from '../../../config/api'
import { eventBus, EVENTS } from '../../../utils/eventBus'

const BASE = API_URL

function ProgressBar({ value, color = 'var(--gold)', height = 6 }) {
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

function PlanStep({ step, index }) {
  const statusColors = { completed: 'var(--success)', running: 'var(--warning)', pending: 'var(--text-muted)', failed: 'var(--error)' }
  const color = statusColors[step.status] || statusColors.pending
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--space-3)',
        padding: 'var(--space-3) 0',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      <div style={{
        width: '22px',
        height: '22px',
        borderRadius: '50%',
        border: `2px solid ${color}`,
        background: step.status === 'completed' ? color : 'transparent',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: '10px',
        color: step.status === 'completed' ? 'var(--bg-base)' : color,
        fontWeight: 700,
      }}>
        {step.status === 'completed' ? '✓' : index + 1}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '2px' }}>
          {step.description || step.name || `Step ${index + 1}`}
        </div>
        {step.agent && (
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Agent: {step.agent}</div>
        )}
      </div>
      <span style={{
        fontSize: '11px',
        color,
        padding: '2px 8px',
        background: `${color}14`,
        borderRadius: '20px',
        flexShrink: 0,
      }}>
        {step.status || 'pending'}
      </span>
    </motion.div>
  )
}

function ResultCard({ result, index }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="ds-card-interactive"
      style={{ padding: 'var(--space-3)' }}
    >
      <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
        {typeof result === 'string' ? result : result.description || result.title || JSON.stringify(result)}
      </div>
      {result.score != null && (
        <div style={{ fontSize: '11px', color: 'var(--success)', marginTop: '4px' }}>
          Score: {result.score}
        </div>
      )}
    </motion.div>
  )
}

export default function AscendForgePage() {
  const ascendForge = useAppStore(s => s.objectivePanels?.ascend_forge || {})
  const selfImprovement = useAppStore(s => s.selfImprovement)
  const brainInsights = useAppStore(s => s.brainInsights)
  const [goal, setGoal] = useState('')
  const [launching, setLaunching] = useState(false)
  const [offlineMode, setOfflineMode] = useState(false)
  const [localState, setLocalState] = useState(null)
  const [evolutionMode, setEvolutionMode] = useState('OFF')

  const state = localState || ascendForge

  // Poll evolution status
  useEffect(() => {
    const controller = new AbortController()
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BASE}/api/evolution/status`, { signal: controller.signal })
        if (res.ok) {
          const data = await res.json()
          setEvolutionMode(data?.mode || 'OFF')
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

  const launchObjective = useCallback(async () => {
    if (!goal.trim()) return
    setLaunching(true)
    const optimisticState = {
      active: true,
      status: 'running',
      current_objective: { goal: goal.trim() },
      plan: [],
      progress: 0,
      active_tasks: [],
      agents_used: [],
      results: [],
    }
    setLocalState(optimisticState)
    try {
      const res = await fetch(`${BASE}/api/ascend-forge/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal.trim() }),
      })
      if (res.ok) {
        const data = await res.json()
        setLocalState(prev => ({ ...prev, ...data }))
        eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'ascend_forge', goal: goal.trim() })
      }
    } catch {
      // Backend offline — local optimistic state stands
      eventBus.emit(EVENTS.MODE_ACTIVATED, { mode: 'ascend_forge', offline: true })
    }
    setLaunching(false)
    setGoal('')
  }, [goal])

  const stopObjective = useCallback(async () => {
    try {
      await fetch(`${BASE}/api/ascend-forge/stop`, { method: 'POST' })
    } catch { /* ignore */ }
    setLocalState(null)
    eventBus.emit(EVENTS.MODE_DEACTIVATED, { mode: 'ascend_forge' })
  }, [])

  const setEvMode = useCallback(async (mode) => {
    try {
      await fetch(`${BASE}/api/evolution/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      })
    } catch { /* ignore */ }
    setEvolutionMode(mode)
  }, [])

  const isActive = state?.active || state?.status === 'running'
  const progress = state?.progress ?? 0
  const plan = state?.plan || []
  const results = state?.results || []

  return (
    <div className="page-enter">
      <PageHeader
        title="Ascend Forge"
        subtitle="Self-improvement and task evolution pipeline"
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
          ⚠ OFFLINE MODE — Backend unreachable. State managed locally.
        </div>
      )}

      {/* Objective launcher */}
      <div className="ds-card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          <span style={{ fontSize: '20px' }}>🔺</span>
          <div>
            <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Ascend Forge
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Status: <span style={{ color: isActive ? 'var(--success)' : 'var(--text-dim)' }}>{state?.status || 'inactive'}</span>
            </div>
          </div>
        </div>

        {!isActive ? (
          <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
            <input
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') launchObjective() }}
              placeholder="Enter improvement goal (e.g. optimize agent decision accuracy)..."
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
              onClick={launchObjective}
              disabled={!goal.trim() || launching}
              style={{
                padding: 'var(--space-3) var(--space-5)',
                background: 'rgba(212, 175, 55, 0.1)',
                border: '1px solid rgba(212, 175, 55, 0.4)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--gold)',
                fontSize: '14px',
                fontWeight: 600,
                cursor: !goal.trim() || launching ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
                opacity: !goal.trim() ? 0.5 : 1,
              }}
            >
              {launching ? 'Launching...' : '🚀 Launch'}
            </motion.button>
          </div>
        ) : (
          <div>
            <div style={{ marginBottom: 'var(--space-3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-1)', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                  {state?.current_objective?.goal || 'Running objective'}
                </span>
                <span style={{ color: 'var(--gold)' }}>{Math.round(progress)}%</span>
              </div>
              <ProgressBar value={progress} color="var(--gold)" />
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-3)', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
              <span>Plan: {plan.length} steps</span>
              <span>Results: {results.length}</span>
              <span>Agents: {(state?.agents_used || []).join(', ') || '—'}</span>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={stopObjective}
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
              Stop Objective
            </motion.button>
          </div>
        )}
      </div>

      {/* Evolution mode selector */}
      <div className="ds-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
          Evolution Mode
        </h3>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {[
            { mode: 'OFF', label: 'Off', desc: 'No automatic evolution' },
            { mode: 'SAFE', label: 'Safe', desc: 'Human-approved changes only' },
            { mode: 'AUTO', label: 'Auto', desc: 'Fully autonomous evolution' },
          ].map(({ mode, label, desc }) => (
            <motion.button
              key={mode}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setEvMode(mode)}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                borderRadius: 'var(--radius-md)',
                border: evolutionMode === mode ? '1px solid var(--gold)' : '1px solid var(--border-subtle)',
                background: evolutionMode === mode ? 'rgba(212,175,55,0.1)' : 'transparent',
                color: evolutionMode === mode ? 'var(--gold)' : 'var(--text-secondary)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                textAlign: 'left',
              }}
            >
              <div style={{ fontSize: '13px', fontWeight: 600 }}>{label}</div>
              <div style={{ fontSize: '11px', opacity: 0.7, marginTop: '2px' }}>{desc}</div>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Plan + results + metrics grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
        {/* Execution plan */}
        <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Execution Plan
          </h3>
          {plan.length === 0 ? (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-4) 0' }}>
              No plan generated yet
            </div>
          ) : plan.map((step, i) => <PlanStep key={i} step={step} index={i} />)}
        </div>

        {/* Improvement metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
            <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
              Pipeline Metrics
            </h3>
            {[
              { label: 'Tasks Processed', value: selfImprovement?.total_tasks_processed ?? 0 },
              { label: 'Queue Depth', value: selfImprovement?.queue_depth ?? 0 },
              { label: 'Deployed', value: selfImprovement?.deployed ?? 0, color: 'var(--success)' },
              { label: 'Pass Rate', value: selfImprovement?.pass_rate != null ? `${Math.round(selfImprovement.pass_rate * 100)}%` : '—' },
              { label: 'Rollback Rate', value: selfImprovement?.rollback_ratio != null ? `${Math.round(selfImprovement.rollback_ratio * 100)}%` : '—', color: 'var(--warning)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: 'var(--space-2) 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ color: color || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
              </div>
            ))}
          </div>

          <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
            <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
              Learned Strategies
            </h3>
            {(brainInsights?.learned_strategies || []).length === 0 ? (
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center', padding: 'var(--space-3) 0' }}>
                No strategies learned yet
              </div>
            ) : (
              (brainInsights.learned_strategies || []).slice(0, 5).map((s, i) => (
                <div key={i} style={{ padding: 'var(--space-2) 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {typeof s === 'string' ? s : s.name || s.description || JSON.stringify(s)}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="ds-card" style={{ padding: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Results ({results.length})
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 'var(--space-2)' }}>
            {results.map((r, i) => <ResultCard key={i} result={r} index={i} />)}
          </div>
        </div>
      )}
    </div>
  )
}
