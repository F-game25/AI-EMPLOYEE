import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const MODE_COLORS = {
  ONLINE: 'var(--success)',
  OFFLINE: 'var(--warning)',
  AUTO: 'var(--gold)',
}
const API_BASE = `http://${window.location.hostname}:3001`

function StatRow({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span
        className="font-mono font-medium"
        style={{ fontSize: '11px', color: highlight ? 'var(--gold)' : 'var(--text-secondary)' }}
      >
        {value}
      </span>
    </div>
  )
}

function MiniBar({ pct, color }) {
  return (
    <div
      style={{
        height: '3px',
        background: 'rgba(255,255,255,0.06)',
        borderRadius: '2px',
        overflow: 'hidden',
      }}
    >
      <motion.div
        animate={{ width: `${Math.min(pct, 100)}%` }}
        transition={{ duration: 0.6 }}
        style={{ height: '100%', background: color, borderRadius: '2px' }}
      />
    </div>
  )
}

function statusLabel({ loading, error, available }) {
  if (loading) return 'LOADING'
  if (error) return 'ERROR'
  return available === false ? 'UNAVAILABLE' : 'ACTIVE'
}

export default function NeuralNetworkPanel() {
  const nn = useAppStore(s => s.nnStatus)
  const setNnStatus = useAppStore(s => s.setNnStatus)
  const [expanded, setExpanded] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    const loadBrainStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/brain/status`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (cancelled) return
        setNnStatus(data || {})
        setError('')
      } catch (e) {
        if (cancelled) return
        setError('Unable to load brain status')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadBrainStatus()
    const timer = setInterval(loadBrainStatus, 3000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [setNnStatus])

  const modeColor = MODE_COLORS[nn.mode] || 'var(--text-muted)'
  const isSimulated = nn.data_source === 'simulated'
  const confPct = Math.round((nn.confidence || 0) * 100)
  const bufferSize = nn.buffer_size || 0
  const maxBufferSize = nn.max_buffer_size || 10000
  const bufferPct = bufferSize > 0 ? Math.round((bufferSize / maxBufferSize) * 100) : 0
  const learnStep = nn.learn_step || 0
  const experiences = nn.experiences || 0

  return (
    <div
      className="flex flex-col flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
    >
      {/* Header */}
      <button
        className="flex items-center justify-between px-3 py-2 w-full text-left"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="nn-panel-body"
      >
        <div className="flex items-center gap-2">
          <motion.div
            animate={nn.active ? { opacity: [1, 0.3, 1] } : { opacity: 0.3 }}
            transition={{ duration: 1.2, repeat: Infinity }}
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            aria-hidden="true"
            style={{ background: nn.active ? 'var(--gold)' : 'var(--text-muted)' }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
            NEURAL BRAIN
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="font-mono"
            style={{ fontSize: '10px', color: modeColor, letterSpacing: '0.05em' }}
          >
            {nn.mode}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </button>

      {/* Body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="nn-panel-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="px-3 pb-2">
              {isSimulated && (
                <div
                  className="font-mono mb-2 px-2 py-1 rounded"
                  style={{ fontSize: '9px', color: 'var(--warning)', background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.15)' }}
                >
                  ⚠ DEGRADED — showing simulated data (no live backend)
                </div>
              )}
              {/* Confidence bar */}
              <div className="mb-2">
                <div className="flex justify-between mb-0.5">
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    CONFIDENCE
                  </span>
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--gold)' }}>
                    {confPct}%
                  </span>
                </div>
                <MiniBar pct={confPct} color="var(--gold)" />
              </div>

              {/* Buffer bar */}
              <div className="mb-2">
                <div className="flex justify-between mb-0.5">
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    REPLAY BUFFER
                  </span>
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                    {bufferSize.toLocaleString()}
                  </span>
                </div>
                <MiniBar pct={bufferPct} color="rgba(212,175,55,0.5)" />
              </div>

              {/* Stats */}
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px' }}>
                <StatRow label="LEARN STEP" value={learnStep.toLocaleString()} highlight />
                <StatRow label="EXPERIENCES" value={experiences.toLocaleString()} />
                <StatRow
                  label="STATUS"
                  value={statusLabel({ loading, error, available: nn.available })}
                  highlight={!error && !loading}
                />
                <StatRow
                  label="LOSS"
                  value={nn.last_loss !== null && nn.last_loss !== undefined ? nn.last_loss.toFixed(4) : '—'}
                />
                <StatRow label="DEVICE" value={(nn.device || 'cpu').toUpperCase()} />
                <StatRow label="BG LOOP" value={nn.bg_running ? '● ACTIVE' : '○ IDLE'} />
                <StatRow label="MEMORY SIZE" value={(nn.memory_size || 0).toLocaleString()} />
              </div>

              {error && (
                <div className="font-mono mt-2" style={{ fontSize: '10px', color: 'var(--warning)' }}>
                  {error}
                </div>
              )}

              {/* Recent outputs */}
              {nn.recent_outputs && nn.recent_outputs.length > 0 && (
                <div style={{ marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px' }}>
                  <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                    RECENT DECISIONS
                  </div>
                  {nn.recent_outputs.slice(0, 3).map((o, i) => (
                    <div
                      key={i}
                      className="font-mono truncate"
                      style={{ fontSize: '10px', color: 'var(--text-secondary)', lineHeight: '1.6' }}
                    >
                      <span style={{ color: 'var(--gold)', opacity: 0.6 }}>›</span>{' '}
                      {o.action}
                      {o.confidence !== undefined && (
                        <span style={{ color: 'var(--text-muted)' }}> ({(o.confidence * 100).toFixed(0)}%)</span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {nn.recent_learning_events && nn.recent_learning_events.length > 0 && (
                <div style={{ marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px' }}>
                  <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                    RECENT LEARNING EVENTS
                  </div>
                  {nn.recent_learning_events.slice(0, 3).map((event, i) => (
                    <div
                      key={`${event.ts || i}-${event.event || 'event'}`}
                      className="font-mono truncate"
                      style={{ fontSize: '10px', color: 'var(--text-secondary)', lineHeight: '1.6' }}
                    >
                      <span style={{ color: 'var(--gold)', opacity: 0.6 }}>›</span>{' '}
                      {(event.event || 'update').replaceAll('_', ' ')}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
