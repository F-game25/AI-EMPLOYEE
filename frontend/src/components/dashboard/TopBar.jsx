import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const MODE_ACTIVATION_COUNTS = {
  MANUAL: 2,
  AUTO: 4,
  BLACKLIGHT: 6,
}

export default function TopBar() {
  const wsConnected = useAppStore(s => s.wsConnected)
  const systemStatus = useAppStore(s => s.systemStatus)
  const user = useAppStore(s => s.user)
  const [time, setTime] = useState(new Date())
  const [mode, setMode] = useState('MANUAL')
  const [modePending, setModePending] = useState(false)
  const [activating, setActivating] = useState(false)

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

  const currentMode = systemStatus?.mode || mode

  const setModeRemote = (next) => {
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

  const activateAgents = () => {
    setActivating(true)
    fetch(`http://${window.location.hostname}:3001/agents/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: MODE_ACTIVATION_COUNTS[currentMode] || MODE_ACTIVATION_COUNTS.MANUAL }),
    })
      .catch((err) => {
        console.error('[TopBar] Failed to activate agents', err)
      })
      .finally(() => setActivating(false))
  }

  return (
    <header
      className="flex items-center justify-between px-4 py-2 gap-4 flex-shrink-0"
      style={{
        minHeight: '70px',
        background: 'linear-gradient(180deg, rgba(14,14,14,0.98), rgba(7,7,7,0.96))',
        borderBottom: '1px solid var(--border-gold)',
        backdropFilter: 'blur(10px)',
        zIndex: 'var(--z-topbar)',
        boxShadow: '0 0 22px rgba(245,196,0,0.14)',
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={activateAgents}
          disabled={activating}
          className="font-mono text-xs font-semibold px-3 py-2"
          style={{
            color: '#111',
            background: 'var(--gold)',
            border: '1px solid rgba(245,196,0,0.9)',
            borderRadius: '6px',
            boxShadow: '0 0 18px rgba(245,196,0,0.35)',
            opacity: activating ? 0.8 : 1,
            cursor: activating ? 'wait' : 'pointer',
          }}
        >
          {activating ? 'ACTIVATING…' : 'START / ACTIVATE AGENTS'}
        </button>

        <select
          value={currentMode}
          onChange={(e) => setModeRemote(e.target.value)}
          disabled={modePending}
          className="font-mono text-xs px-2 py-2"
          style={{
            background: 'rgba(255,255,255,0.04)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-gold-dim)',
            borderRadius: '6px',
            minWidth: '128px',
          }}
          aria-label="Operating mode selector"
        >
          <option value="MANUAL">MANUAL</option>
          <option value="AUTO">AUTO</option>
          <option value="BLACKLIGHT">BLACKLIGHT</option>
        </select>

        <div
          className="font-mono text-xs px-2 py-2"
          style={{
            color: 'var(--gold)',
            background: 'rgba(245,196,0,0.08)',
            border: '1px solid rgba(245,196,0,0.2)',
            borderRadius: '6px',
          }}
          aria-live="polite"
        >
          RUNNING {systemStatus.running_agents || 0}/{systemStatus.total_agents || 0}
        </div>
      </div>

      <div
        className="flex items-center gap-2 px-2 py-1 rounded-md overflow-x-auto"
        style={{
          border: '1px solid var(--border-gold-dim)',
          background: 'rgba(0,0,0,0.28)',
        }}
        role="status"
        aria-label="Unified system stats"
      >
        <Metric label="CPU" value={`${systemStatus.cpu_usage || 0}%`} warn={(systemStatus.cpu_usage || 0) > 80} />
        <Metric label="GPU" value={`${systemStatus.gpu_usage || 0}%`} warn={(systemStatus.gpu_usage || 0) > 80} />
        <Metric label="CPU °C" value={systemStatus.cpu_temperature || 0} warn={(systemStatus.cpu_temperature || 0) > 80} />
        <Metric label="GPU °C" value={systemStatus.gpu_temperature || 0} warn={(systemStatus.gpu_temperature || 0) > 80} />
        <Metric label="HEARTBEAT" value={systemStatus.heartbeat || 0} subtle />
      </div>

      <div className="flex items-center gap-3">
        <span className="font-mono text-xs font-bold tracking-widest" style={{ color: 'var(--gold)' }}>
          AI-EMPLOYEE
        </span>
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

function Metric({ label, value, warn, subtle }) {
  return (
    <div className="flex flex-col px-2 min-w-[64px]">
      <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span
        className="font-mono text-xs font-medium"
        style={{ color: subtle ? 'var(--gold-dim)' : (warn ? 'var(--warning)' : 'var(--text-secondary)') }}
      >
        {value}
      </span>
    </div>
  )
}
