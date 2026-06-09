import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useShallow } from 'zustand/react/shallow'
import { useAppStore } from '../../store/appStore'
import { useSystemStore, selectBackendHealth } from '../../store/systemStore'
import { useSecurityStore } from '../../store/securityStore'
import { useEconomyStore } from '../../store/economyStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useUpdateCheck } from '../../hooks/useUpdateCheck'
import { CommandPill, ClockModule, StatusPill, HexButton } from '../nexus-ui'
import MiniEye from '../core/MiniEye'
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
  'recon':           'Recon',
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

function OfflineBanner({ reason }) {
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
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [heartbeatLogs])

  // Show reconnect countdown only when the issue is the WS itself.
  const showCountdown = reason === 'WebSocket reconnecting'
  const suffix = showCountdown
    ? (countdown != null && countdown > 0 ? ` — RECONNECTING IN ${countdown}s` : ' — RECONNECTING…')
    : ''

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
        BACKEND ISSUE — {reason || 'UNKNOWN'}{suffix}
      </span>
    </motion.div>
  )
}

function TopStat({ label, value, tone = 'default', delta = null }) {
  const deltaTone = delta == null ? null : delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  return (
    <div className={`nx-topbar__stat nx-topbar__stat--${tone}`}>
      <span className="nx-topbar__stat-label">{label}</span>
      <div className="nx-topbar__stat-line">
        <span className="nx-topbar__stat-value">{value}</span>
        {delta != null && (
          <span className={`nx-topbar__stat-delta nx-topbar__stat-delta--${deltaTone}`}>
            {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  )
}

// Threat enum → label / tone
function threatToEnum(score) {
  if (score >= 75) return { label: 'CRITICAL', tone: 'alert', color: '#FF4444' }
  if (score >= 50) return { label: 'HIGH',     tone: 'alert', color: '#FF8C42' }
  if (score >= 25) return { label: 'ELEVATED', tone: 'warn',  color: '#FFD93D' }
  return { label: 'OK', tone: 'success', color: '#00FFB4' }
}

const LIVE_THRESHOLD_MS = 30_000

function LiveBadge() {
  const [isLive, setIsLive] = useState(() => {
    const t = window.__lastWsEvent
    return typeof t === 'number' && Date.now() - t < LIVE_THRESHOLD_MS
  })

  useEffect(() => {
    const tick = () => {
      const t = window.__lastWsEvent
      setIsLive(typeof t === 'number' && Date.now() - t < LIVE_THRESHOLD_MS)
    }
    const id = setInterval(tick, 5000)
    // Also update immediately on any WS message
    const onMsg = () => { window.__lastWsEvent = Date.now(); setIsLive(true) }
    window.addEventListener('ws:any', onMsg)
    return () => { clearInterval(id); window.removeEventListener('ws:any', onMsg) }
  }, [])

  return (
    <div className={`nx-topbar__live nx-topbar__live--${isLive ? 'live' : 'standby'}`} aria-label={isLive ? 'Live data' : 'Standby'}>
      <span className="nx-topbar__live-dot" />
      <span className="nx-topbar__live-label">{isLive ? 'LIVE' : 'STANDBY'}</span>
    </div>
  )
}

export default function TopBar() {
  const { wsConnected, systemStatus, systemHealth: _systemHealth, nnStatus, activeSection } = useAppStore(
    useShallow(s => ({ wsConnected: s.wsConnected, systemStatus: s.systemStatus, systemHealth: s.systemHealth, nnStatus: s.nnStatus, activeSection: s.activeSection }))
  )
  const systemHealth = _systemHealth || {}
  const { updateReady, updateComplete, applying, applyUpdate } = useUpdateCheck()
  const toggleMobileSidebar = useSystemStore(s => s.toggleMobileSidebar)

  const threatScore  = useSecurityStore(s => s.securityStatus?.threat_score) ?? 0
  const { revenueToday, revenueYday } = useEconomyStore(
    useShallow(s => ({ revenueToday: s.revenue?.today ?? 0, revenueYday: s.revenue?.yesterday ?? 0 }))
  )
  const modelCalls   = useCognitiveStore(s => s.modelCalls) || []

  // Tokens/sec EMA over last 30 samples (modelCalls is event-stream length proxy)
  const tokEmaRef = useRef(0)
  useEffect(() => {
    const alpha = 0.15
    tokEmaRef.current = alpha * modelCalls.length + (1 - alpha) * tokEmaRef.current
  }, [modelCalls.length])
  const tokensPerSec = Math.round(tokEmaRef.current)
  const formatTokens = (v) => v >= 1_000_000 ? `${(v/1_000_000).toFixed(2)}M` : v >= 1_000 ? `${(v/1_000).toFixed(1)}K` : String(v)

  // Revenue delta
  const revDelta = revenueYday > 0 ? ((revenueToday - revenueYday) / revenueYday) * 100 : null

  // Threat enum
  const threat = threatToEnum(threatScore)

  // New banner state — reads structured backend health, not raw wsConnected.
  // Banner hides on first paint until we've seen a healthy state at least once,
  // matching the prior wasConnectedRef behaviour.
  const backendHealthy = useSystemStore(s => selectBackendHealth(s).healthy)
  const backendReason = useSystemStore(s => selectBackendHealth(s).reason)
  const wasHealthyRef = useRef(false)
  useEffect(() => {
    if (backendHealthy) wasHealthyRef.current = true
  }, [backendHealthy])
  const showOffline = !backendHealthy && wasHealthyRef.current

  const cpu  = systemStatus?.cpu ?? systemStatus?.cpu_usage ?? 0
  const ram  = systemStatus?.memory ?? systemStatus?.ram ?? 0
  const uptime = systemStatus?.uptime ?? '—'
  const mode = systemStatus?.mode ?? 'MANUAL'
  const confidence = nnStatus?.confidence ?? 0
  const brainPct = confidence > 1 ? Math.round(confidence) : Math.round(confidence * 100)

  const cpuTone = cpu > 80 ? 'alert' : cpu > 60 ? 'warn' : 'cool'
  const ramTone = ram > 80 ? 'alert' : 'default'

  // Rolling sparkline for health
  const sparkRef = useRef(new Array(8).fill(0))
  useEffect(() => {
    sparkRef.current = [...sparkRef.current.slice(1), cpu]
  }, [cpu])
  const sparkPoints = sparkRef.current.map((v, i) => {
    const x = (i / 7) * 52 + 2
    const y = 14 - (v / 100) * 11
    return `${x},${y}`
  }).join(' ')

  const formatRevenue = (v) => {
    if (v >= 1000) return `$${(v/1000).toFixed(1)}K`
    return `$${Math.round(v)}`
  }

  const openCommandPalette = () => {
    // Opens the chat panel — the command/search surface for the system.
    // Listened to in Dashboard.jsx.
    window.dispatchEvent(new CustomEvent('nx:chat:open'))
  }

  return (
    <>
      {updateComplete && (
        <div className="nx-topbar__update nx-topbar__update--complete">
          <span>UPDATE APPLIED — NEW VERSION AVAILABLE</span>
          <button onClick={() => window.location.reload()}>RELOAD NOW →</button>
        </div>
      )}
      {updateReady && !updateComplete && (
        <div className="nx-topbar__update nx-topbar__update--available">
          <span>UPDATE AVAILABLE</span>
          <button onClick={applyUpdate} disabled={applying}>
            {applying ? 'UPDATING…' : 'UPDATE NOW →'}
          </button>
        </div>
      )}

      <AnimatePresence>
        {showOffline && <OfflineBanner key="offline" reason={backendReason} />}
      </AnimatePresence>

      <header className="nx-topbar">
        {/* Hamburger — mobile only */}
        <button
          type="button"
          className="nx-topbar__hamburger"
          onClick={toggleMobileSidebar}
          aria-label="Open navigation"
        >
          <span /><span /><span />
        </button>

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

          <div
            className={`nx-topbar__threat nx-topbar__threat--${threat.tone}`}
            title={`Threat score: ${Math.round(threatScore)}`}
          >
            <span className="nx-topbar__threat-label">THREAT LEVEL</span>
            <div className="nx-topbar__threat-line">
              <span className="nx-topbar__threat-dot" style={{ background: threat.color, boxShadow: `0 0 6px ${threat.color}` }} />
              <span className="nx-topbar__threat-value">{threat.label}</span>
            </div>
          </div>
          <TopStat
            label="REVENUE/DAY"
            value={formatRevenue(revenueToday)}
            tone="gold"
            delta={revDelta}
          />
          <TopStat label="TOKENS/SEC" value={formatTokens(tokensPerSec)} />

          <span className="nx-topbar__divider" />

          {/* Health sparkline */}
          <div className="nx-topbar__health">
            <span className="nx-topbar__health-label">HEALTH</span>
            <svg width="56" height="16" viewBox="0 0 56 16" className="nx-topbar__sparkline">
              <polyline points={sparkPoints} fill="none" stroke="rgba(255,184,0,0.7)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="nx-topbar__health-val">{brainPct}%</span>
          </div>

          <span className="nx-topbar__divider" />

          {/* Route-aware mini-eye */}
          <MiniEye size={22} className="nx-topbar__mini-eye" />

          <span className="nx-topbar__divider" />

          {/* LIVE data badge */}
          <LiveBadge />

          <span className="nx-topbar__divider" />

          {/* User avatar */}
          <div className="nx-topbar__user">
            <div className="nx-topbar__avatar">AN</div>
            <span className="nx-topbar__username">ALEX</span>
          </div>
        </div>
      </header>
    </>
  )
}
