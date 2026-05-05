import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useUpdateCheck } from '../../hooks/useUpdateCheck'
import { CommandPill, ClockModule, StatusPill, HexButton } from '../nexus-ui'
import './TopBar.css'

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

// Mode → StatusPill tone mapping
const MODE_TONE = {
  AUTONOMOUS:  'gold',
  SUPERVISED:  'cool',
  SAFE:        'success',
  MAINTENANCE: 'warn',
  MANUAL:      'idle',
  PRECISION:   'gold',
  BALANCED:    'cool',
  SPEED:       'gold',
  COST:        'success',
}

function OfflineBanner() {
  const heartbeatLogs = useAppStore(s => s.heartbeatLogs)
  const [countdown, setCountdown] = useState(null)

  useEffect(() => {
    const last = [...heartbeatLogs].reverse().find(l => l.level === 'warning' && l.text.includes('reconnecting in'))
    if (!last) { setCountdown(null); return }
    const match = last.text.match(/reconnecting in (\d+)s/)
    if (!match) { setCountdown(null); return }
    const seconds = parseInt(match[1], 10)
    const target = last.ts + seconds * 1000
    const tick = () => setCountdown(Math.max(0, Math.ceil((target - Date.now()) / 1000)))
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
      className="nx-topbar__offline"
    >
      <span className="nx-topbar__offline-dot" />
      <span className="nx-topbar__offline-text">
        BACKEND DISCONNECTED
        {countdown != null && countdown > 0 ? ` — RECONNECTING IN ${countdown}s` : ' — RECONNECTING…'}
      </span>
    </motion.div>
  )
}

function TopStat({ label, value, tone = 'default' }) {
  return (
    <div className={`nx-topbar__stat nx-topbar__stat--${tone}`}>
      <span className="nx-topbar__stat-label">{label}</span>
      <span className="nx-topbar__stat-value">{value}</span>
    </div>
  )
}

export default function TopBar() {
  const wsConnected   = useAppStore(s => s.wsConnected)
  const systemStatus  = useAppStore(s => s.systemStatus)
  const nnStatus      = useAppStore(s => s.nnStatus)
  const activeSection = useAppStore(s => s.activeSection)
  const { updateReady } = useUpdateCheck()

  const wasConnectedRef = useRef(false)
  if (wsConnected) wasConnectedRef.current = true
  const showOffline = !wsConnected && wasConnectedRef.current

  const cpu  = systemStatus?.cpu ?? systemStatus?.cpu_usage ?? 0
  const ram  = systemStatus?.memory ?? systemStatus?.ram ?? 0
  const uptime = systemStatus?.uptime ?? '—'
  const mode = systemStatus?.mode ?? 'MANUAL'
  const confidence = nnStatus?.confidence ?? 0
  const brainPct = confidence > 1 ? Math.round(confidence) : Math.round(confidence * 100)

  const cpuTone = cpu > 80 ? 'alert' : cpu > 60 ? 'warn' : 'cool'
  const ramTone = ram > 80 ? 'alert' : 'default'

  const openCommandPalette = () => {
    // Hook for future palette overlay; for now, focus a no-op event.
    window.dispatchEvent(new CustomEvent('nx:command-palette:open'))
  }

  return (
    <>
      {updateReady && (
        <div className="nx-topbar__update">
          <span>UPDATE APPLIED — NEW VERSION AVAILABLE</span>
          <button onClick={() => window.location.reload()}>RELOAD NOW →</button>
        </div>
      )}

      <AnimatePresence>
        {showOffline && <OfflineBanner key="offline" />}
      </AnimatePresence>

      <header className="nx-topbar">
        {/* Left: breadcrumb */}
        <div className="nx-topbar__left">
          <span className="nx-topbar__crumb-root">Aeternus Nexus</span>
          <span className="nx-topbar__crumb-sep">/</span>
          <span className="nx-topbar__crumb-page">
            {PAGE_LABELS[activeSection] || activeSection}
          </span>
        </div>

        {/* Center: command pill + clock */}
        <div className="nx-topbar__center">
          <CommandPill
            placeholder="Search or run a command…"
            hotkey="⌘K"
            onClick={openCommandPalette}
          />
          <ClockModule compact showSeconds={false} />
        </div>

        {/* Right: status pills + stats */}
        <div className="nx-topbar__right">
          <StatusPill
            tone={wsConnected ? 'success' : 'alert'}
            label={wsConnected ? 'ONLINE' : 'OFFLINE'}
          />
          <StatusPill
            tone={MODE_TONE[mode] || 'idle'}
            label={mode}
            dot={false}
            icon="◆"
          />

          <span className="nx-topbar__divider" />

          <TopStat label="CPU" value={`${Math.round(cpu)}%`} tone={cpuTone} />
          <TopStat label="RAM" value={`${Math.round(ram)}%`} tone={ramTone} />
          <TopStat label="UPTIME" value={typeof uptime === 'number' ? `${Math.floor(uptime / 3600)}h` : String(uptime)} />

          <span className="nx-topbar__divider" />

          <TopStat label="BRAIN" value={`${brainPct}%`} tone="gold" />

          <HexButton size="sm" variant="outline" tone="gold" icon="◈">
            Console
          </HexButton>
        </div>
      </header>
    </>
  )
}
