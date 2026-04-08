import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

export default function TopBar() {
  const { wsConnected, systemStatus, user } = useAppStore()
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

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

      {/* Center: system metrics */}
      <div className="flex items-center gap-6" role="status" aria-label="System metrics">
        <Metric label="CPU" value={`${systemStatus.cpu || 0}%`} warn={systemStatus.cpu > 70} />
        <Metric label="MEM" value={`${systemStatus.memory || 0}%`} warn={systemStatus.memory > 70} />
        <Metric label="CONN" value={systemStatus.connections || 0} />
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
