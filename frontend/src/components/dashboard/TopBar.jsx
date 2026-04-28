import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useUpdateCheck } from '../../hooks/useUpdateCheck'

const PAGE_LABELS = {
  'dashboard':       'Dashboard',
  'ai-control':      'AI Control',
  'neural-brain':    'Neural Brain',
  'agents':          'Agents',
  'operations':      'Operations',
  'hermes':          'Hermes',
  'ascend-forge':    'Ascend Forge',
  'voice':           'Voice',
  'prompt-inspector':'Prompt Inspector',
  'blacklight':      'Blacklight',
  'fairness':        'Fairness',
  'doctor':          'Doctor',
  'control-center':  'Control Center',
  'learning-ladder': 'Learning Ladder',
  'system':          'System',
  'money-mode':      'Money Mode',
  'workspace':       'Workspace',
  'evolution':       'Evolution',
  'training':        'Training Studio',
  'history':         'History',
}

const MODE_COLORS = {
  AUTONOMOUS:  'var(--gold)',
  SUPERVISED:  'var(--neon-teal)',
  SAFE:        'var(--success)',
  MAINTENANCE: 'var(--warning)',
  MANUAL:      'var(--text-secondary)',
  PRECISION:   'var(--gold-bright)',
  BALANCED:    'var(--neon-teal)',
  SPEED:       'var(--bronze)',
  COST:        'var(--success)',
}

function Divider() {
  return <div style={{ width: 1, height: 20, background: 'var(--border-subtle)', flexShrink: 0 }} />
}

function Stat({ label, value, color = 'var(--text-secondary)' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
      <span style={{ fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 12, fontFamily: 'monospace', color, fontWeight: 500 }}>{value}</span>
    </div>
  )
}

// Reconnect countdown banner — shows when WS is offline
function OfflineBanner() {
  const heartbeatLogs = useAppStore(s => s.heartbeatLogs)
  const [countdown, setCountdown] = useState(null)

  // Parse reconnect delay from last warning log
  useEffect(() => {
    const last = [...heartbeatLogs].reverse().find(l => l.level === 'warning' && l.text.includes('reconnecting in'))
    if (!last) { setCountdown(null); return }
    const match = last.text.match(/reconnecting in (\d+)s/)
    if (!match) { setCountdown(null); return }
    const seconds = parseInt(match[1], 10)
    const target = last.ts + seconds * 1000
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((target - Date.now()) / 1000))
      setCountdown(remaining)
    }
    tick()
    const id = setInterval(tick, 500)
    return () => clearInterval(id)
  }, [heartbeatLogs])

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 28, opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        overflow: 'hidden', background: 'rgba(239,68,68,0.12)',
        borderBottom: '1px solid rgba(239,68,68,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--error)', display: 'inline-block' }} />
      <span style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--error)', letterSpacing: '0.08em' }}>
        BACKEND DISCONNECTED
        {countdown != null && countdown > 0 ? ` — RECONNECTING IN ${countdown}s` : ' — RECONNECTING…'}
      </span>
    </motion.div>
  )
}

export default function TopBar() {
  const wsConnected   = useAppStore(s => s.wsConnected)
  const systemStatus  = useAppStore(s => s.systemStatus)
  const nnStatus      = useAppStore(s => s.nnStatus)
  const activeSection = useAppStore(s => s.activeSection)
  const [time, setTime] = useState(new Date())
  const { updateReady } = useUpdateCheck()
  // Track whether we were previously connected to only show banner after first connection
  const wasConnectedRef = useRef(false)
  if (wsConnected) wasConnectedRef.current = true
  const showOffline = !wsConnected && wasConnectedRef.current

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const cpu  = systemStatus?.cpu ?? systemStatus?.cpu_usage ?? 0
  const ram  = systemStatus?.memory ?? systemStatus?.ram ?? 0
  const uptime = systemStatus?.uptime ?? '—'
  const mode = systemStatus?.mode ?? 'MANUAL'
  const confidence = nnStatus?.confidence ?? 0
  const brainPct = confidence > 1 ? Math.round(confidence) : Math.round(confidence * 100)

  const cpuColor = cpu > 80 ? 'var(--error)' : cpu > 60 ? 'var(--warning)' : 'var(--neon-teal)'
  const ramColor = ram > 80 ? 'var(--error)' : 'var(--text-secondary)'

  return (
    <>
      {/* Update banner */}
      {updateReady && (
        <div style={{
          background: 'linear-gradient(90deg, #B8923F, #E5C76B)',
          color: '#1a1000', fontSize: 11, fontWeight: 700,
          padding: '6px 16px', display: 'flex', justifyContent: 'space-between',
          letterSpacing: '0.08em', flexShrink: 0,
        }}>
          <span>UPDATE APPLIED — NEW VERSION AVAILABLE</span>
          <button onClick={() => window.location.reload()} style={{ background: 'none', border: 'none', color: '#1a1000', fontWeight: 700, cursor: 'pointer', fontSize: 11 }}>
            RELOAD NOW →
          </button>
        </div>
      )}

      {/* Offline recovery banner */}
      <AnimatePresence>
        {showOffline && <OfflineBanner key="offline" />}
      </AnimatePresence>

      <header style={{
        height: 48, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 16px', borderBottom: '1px solid var(--border-gold-dim)',
        background: 'var(--bg-card)', gap: 24,
        zIndex: 'var(--z-topbar)',
      }}>
        {/* Breadcrumb */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>Ultron</span>
          <span style={{ color: 'var(--border-subtle)', fontSize: 14 }}>/</span>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
            {PAGE_LABELS[activeSection] || activeSection}
          </span>
        </div>

        {/* Right: live stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* Connection indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className={`status-dot ${wsConnected ? 'status-dot--active status-dot--pulse' : 'status-dot--error'}`} />
            <span style={{ fontSize: 10, fontFamily: 'monospace', color: wsConnected ? 'var(--success)' : 'var(--error)', letterSpacing: '0.06em' }}>
              {wsConnected ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <Divider />

          {/* Mode */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase' }}>MODE</span>
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: MODE_COLORS[mode] || 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>{mode}</span>
          </div>
          <Divider />

          <Stat label="CPU" value={`${Math.round(cpu)}%`} color={cpuColor} />
          <Stat label="RAM" value={`${Math.round(ram)}%`} color={ramColor} />
          <Stat label="Uptime" value={typeof uptime === 'number' ? `${Math.floor(uptime / 3600)}h` : String(uptime)} />
          <Divider />

          <Stat label="Brain" value={`${brainPct}%`} color="var(--gold)" />

          <time style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)', marginLeft: 4 }}>
            {time.toLocaleTimeString('en-US', { hour12: false })}
          </time>
        </div>
      </header>
    </>
  )
}
