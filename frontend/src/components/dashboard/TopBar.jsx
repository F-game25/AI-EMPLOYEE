import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const MODE_COLORS = {
  AUTO: 'var(--success)',
  MANUAL: 'var(--warning)',
  BLACKLIGHT: '#c084fc',
}

const MODE_LABELS = {
  AUTO: 'AUTO',
  MANUAL: 'MANUAL',
  BLACKLIGHT: 'BLACKLIGHT',
}

export default function TopBar() {
  const { wsConnected, systemStatus, user } = useAppStore()
  const [time, setTime] = useState(new Date())
  const [mode, setMode] = useState('MANUAL')
  const [modePending, setModePending] = useState(false)

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  // Fetch initial mode
  useEffect(() => {
    fetch(`http://${window.location.hostname}:3001/api/mode`)
      .then(r => r.json())
      .then(d => d.mode && setMode(d.mode))
      .catch(() => {})
  }, [])

  const cycleMode = () => {
    const modes = ['MANUAL', 'AUTO', 'BLACKLIGHT']
    const next = modes[(modes.indexOf(mode) + 1) % modes.length]
    setModePending(true)
    fetch(`http://${window.location.hostname}:3001/api/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: next }),
    })
      .then(r => r.json())
      .then(d => d.mode && setMode(d.mode))
      .catch(() => {})
      .finally(() => setModePending(false))
  }

  return (
    <header
      className="flex items-center justify-between px-4 flex-shrink-0"
      style={{
        height: '44px',
        background: 'rgba(10,10,10,0.97)',
        borderBottom: '1px solid var(--border-gold-dim)',
        backdropFilter: 'blur(10px)',
        zIndex: 'var(--z-topbar)',
      }}
    >
      {/* Left: logo */}
      <div className="flex items-center gap-3">
        <span
          className="font-mono text-xs font-bold tracking-widest"
          style={{ color: 'var(--gold)' }}
        >
          AI-EMPLOYEE
        </span>
        {/* Vertical divider */}
        <div
          aria-hidden="true"
          style={{ width: '1px', height: '12px', background: 'var(--text-dim)' }}
        />
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>OS v2.0</span>
      </div>

      {/* Center: system metrics + mode switcher */}
      <div className="flex items-center gap-6" role="status" aria-label="System metrics">
        <Metric label="CPU" value={`${systemStatus.cpu || 0}%`} warn={systemStatus.cpu > 70} />
        <Metric label="MEM" value={`${systemStatus.memory || 0}%`} warn={systemStatus.memory > 70} />
        <Metric label="CONN" value={systemStatus.connections || 0} />

        {/* Mode switcher */}
        <button
          onClick={cycleMode}
          disabled={modePending}
          title={`Current mode: ${mode}. Click to cycle.`}
          aria-label={`Operating mode: ${mode}. Click to switch.`}
          className="font-mono text-xs px-2 py-0.5"
          style={{
            color: MODE_COLORS[mode] || 'var(--text-secondary)',
            background: 'rgba(255,255,255,0.05)',
            border: `1px solid ${MODE_COLORS[mode] || 'var(--border-subtle)'}`,
            borderRadius: '3px',
            cursor: modePending ? 'wait' : 'pointer',
            opacity: modePending ? 0.6 : 1,
          }}
        >
          {modePending ? '…' : MODE_LABELS[mode] || mode}
        </button>
      </div>

      {/* Right: time + connection + user */}
      <div className="flex items-center gap-4">
        <time
          className="font-mono text-xs"
          style={{ color: 'var(--text-muted)' }}
          aria-label="Current time"
        >
          {time.toLocaleTimeString('en-US', { hour12: false })}
        </time>

        <motion.div
          animate={{ opacity: [1, 0.45, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="flex items-center gap-1.5"
          role="status"
          aria-label={wsConnected ? 'Connected' : 'Offline'}
          title={wsConnected ? 'WebSocket connected' : 'WebSocket disconnected'}
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: wsConnected ? 'var(--success)' : 'var(--error)' }}
          />
          <span
            className="font-mono text-xs"
            style={{ color: wsConnected ? 'var(--success)' : 'var(--error)' }}
          >
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </motion.div>

        {user && (
          <div
            className="font-mono text-xs px-2 py-0.5"
            style={{
              color: 'var(--text-muted)',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '3px',
            }}
          >
            {user.username.toUpperCase()}
          </div>
        )}
      </div>
    </header>
  )
}

function Metric({ label, value, warn }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span
        className="font-mono text-xs font-medium"
        style={{ color: warn ? 'var(--warning)' : 'var(--text-secondary)' }}
      >
        {value}
      </span>
    </div>
  )
}
