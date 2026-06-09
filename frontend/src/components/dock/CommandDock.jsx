import { useState, useRef, useEffect, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import { useAgentStore } from '../../store/agentStore'
import { useTaskStore } from '../../store/taskStore'
import { useSecurityStore } from '../../store/securityStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import MiniReactor from './MiniReactor'
import './CommandDock.css'

const FOCUS_MODES = ['BALANCED', 'PERFORMANCE', 'EFFICIENCY', 'SILENT']
const WORKSPACES  = ['DEFAULT', 'DEVELOPMENT', 'RESEARCH', 'OPERATIONS']

// Auth header helper
function authHeader() {
  const t = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
  return t ? { Authorization: 'Bearer ' + t } : {}
}

// ── Brand logo (small diamond mark) ──
function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" className="cmd-brand-mark">
      <path d="M12 1 L23 12 L12 23 L1 12 Z" fill="none" stroke="#F5A623" strokeWidth="1.5" />
      <path d="M12 5 L19 12 L12 19 L5 12 Z" fill="rgba(245,166,35,0.25)" stroke="#FFC966" strokeWidth="1" />
      <circle cx="12" cy="12" r="2" fill="#FFE3A8" />
    </svg>
  )
}

// ── Pill: simple button with icon + label stack ──
function Pill({ icon, label, sub, onClick, title, extraClass = '', children }) {
  return (
    <button type="button" className={`cmd-pill ${extraClass}`} onClick={onClick} title={title}>
      <span className="cmd-pill__icon">{icon}</span>
      <span className="cmd-pill__text">
        <span className="cmd-pill__label">{label}</span>
        {sub && <span className="cmd-pill__sub">{sub}</span>}
      </span>
      {children}
    </button>
  )
}

// ── Mini sparkline for system health ──
function HealthSpark({ points }) {
  return (
    <svg width="60" height="20" viewBox="0 0 60 20" className="cmd-bar__sparkline">
      <polyline points={points} fill="none" stroke="rgba(255,184,0,0.8)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Ring gauge for health % ──
function HealthRing({ value }) {
  const pct = Math.min(100, Math.max(0, Math.round(value)))
  const r = 11; const c = 2 * Math.PI * r
  const tone = pct >= 95 ? '#00FFB4' : pct >= 85 ? '#FFD93D' : '#FF4444'
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" className="cmd-bar__gauge">
      <circle cx="15" cy="15" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
      <circle cx="15" cy="15" r={r} fill="none" stroke={tone} strokeWidth="2"
        strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)}
        strokeLinecap="round" transform="rotate(-90 15 15)"
        style={{ transition: 'stroke-dashoffset 0.6s, stroke 0.4s' }}
      />
    </svg>
  )
}

// ── Voice waveform (3 animated bars) ──
function VoiceWaveform({ active }) {
  return (
    <div className={`cmd-wave ${active ? 'cmd-wave--active' : ''}`}>
      <span className="cmd-wave__bar" /><span className="cmd-wave__bar" /><span className="cmd-wave__bar" />
    </div>
  )
}

// ── Dropdown menu rendered above its pill ──
function Dropdown({ options, value, onChange, onClose }) {
  return (
    <div className="cmd-dropdown" onMouseLeave={onClose}>
      {options.map(opt => (
        <button key={opt} type="button"
          className={`cmd-dropdown__item ${opt === value ? 'cmd-dropdown__item--active' : ''}`}
          onClick={() => { onChange(opt); onClose() }}
        >{opt}</button>
      ))}
    </div>
  )
}

// ── Section 1: System pulse strip ──
const PULSE_NODES = [
  { key: 'memory',   label: 'ME', color: '#22d3ee' },
  { key: 'agents',   label: 'AG', color: '#a855f7' },
  { key: 'research', label: 'RE', color: '#22c55e' },
  { key: 'security', label: 'SE', color: '#ef4444' },
  { key: 'economy',  label: 'EC', color: '#fbbf24' },
  { key: 'knowledge',label: 'KN', color: '#e5c76b' },
]

function PulseStrip({ metrics, lastActive }) {
  return (
    <div className="cmd-pulse-strip">
      {PULSE_NODES.map(({ key, label, color }) => {
        const val = metrics[key] ?? '--'
        const active = lastActive[key] && (Date.now() - lastActive[key] < 10000)
        return (
          <div key={key} className="cmd-pulse-node" title={key.toUpperCase()}>
            <span className={`cmd-pulse-dot ${active ? 'cmd-pulse-dot--active' : ''}`} style={{ '--dot-color': color }} />
            <span className="cmd-pulse-label">{label}</span>
            <span className="cmd-pulse-val">{val}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Section 2: Quick actions row ──
function QuickActions({ onNav, onComposer }) {
  const actions = [
    { icon: '◈', label: 'Forge',    section: 'ascendforge' },
    { icon: '▣', label: 'Tasks',    section: 'tasks' },
    { icon: '◉', label: 'Agents',   section: 'agents' },
    { icon: '⬡', label: 'Security', section: 'security' },
    { icon: '◆', label: 'Compose',  section: null },
  ]
  return (
    <div className="cmd-quick-actions">
      {actions.map(({ icon, label, section }) => (
        <button key={label} type="button" className="cmd-quick-btn"
          onClick={() => section ? onNav(section) : onComposer()}
          title={label} aria-label={label}
        >
          <span className="cmd-quick-icon">{icon}</span>
          <span className="cmd-quick-label">{label}</span>
        </button>
      ))}
    </div>
  )
}

// ── Section 3: Active task ticker ──
function elapsed(startMs) {
  if (!startMs) return '00:00'
  const s = Math.floor((Date.now() - startMs) / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function TaskTicker({ task }) {
  const [, tick] = useState(0)
  useEffect(() => {
    if (!task || task.status !== 'running') return
    const id = setInterval(() => tick(n => n + 1), 1000)
    return () => clearInterval(id)
  }, [task])

  if (!task) return <div className="cmd-task-ticker cmd-task-ticker--idle">SYSTEM IDLE</div>

  const title = (task.title || task.name || task.description || 'Task').slice(0, 32)
  const status = (task.status || 'queued').toUpperCase()
  const statusClass = status === 'RUNNING' ? 'running' : status === 'DONE' || status === 'COMPLETED' ? 'done' : 'queued'
  const startMs = task.started_at || task.startedAt || task.created_at || null
  return (
    <div className="cmd-task-ticker">
      <span className="cmd-task-title">{title}</span>
      <span className={`cmd-task-status cmd-task-status--${statusClass}`}>{status}</span>
      {status === 'RUNNING' && <span className="cmd-task-elapsed">{elapsed(startMs)}</span>}
    </div>
  )
}

// ── Section 4: Resource meters ──
function ResourceMeter({ label, value, max, color }) {
  const pct = value === '--' ? 0 : Math.min(1, (value || 0) / max)
  return (
    <div className="cmd-resource-meter">
      <span className="cmd-resource-label">{label}</span>
      <span className="cmd-resource-value">{value === '--' ? '--' : value}</span>
      <div className="cmd-resource-bar-track">
        <div className="cmd-resource-bar-fill" style={{ width: `${pct * 100}%`, background: color }} />
      </div>
    </div>
  )
}

export default function CommandDock({ onToggleChat, chatOpen = false }) {
  const wsConnected    = useAppStore(s => s.wsConnected)
  const systemHealth   = useAppStore(s => s.systemHealth) || {}
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const threatScore    = useSecurityStore(s => s.securityStatus?.threat_score) || 0
  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps) || []
  const agents         = useAgentStore(s => s.agents)
  const opsSummary     = useTaskStore(s => s.opsSummary)
  const executionLogs  = useTaskStore(s => s.executionLogs)

  // Active task: most recent running, else most recent queued, else null
  const activeTask = (() => {
    if (!Array.isArray(executionLogs) || executionLogs.length === 0) return null
    const running = executionLogs.find(l => l.status === 'running' || l.status === 'RUNNING')
    if (running) return running
    return executionLogs[0] || null
  })()

  // Pulse metrics + last-active timestamps
  const [pulseMetrics, setPulseMetrics] = useState({ memory: '--', agents: 0, research: '--', security: '--', economy: '--', knowledge: '--' })
  const [lastActive, setLastActive] = useState({})
  const [memNodeCount, setMemNodeCount] = useState(null)

  // Poll Section 1 data every 15s
  useEffect(() => {
    async function fetchPulse() {
      const now = Date.now()
      const nextActive = {}
      const next = {}

      // Agents from store (always fresh)
      next.agents = agents.length
      if (agents.length > 0) nextActive.agents = now

      // Tasks from opsSummary
      const taskCount = (opsSummary?.active_tasks || 0) + (opsSummary?.queued_tasks || 0)
      next.research = taskCount
      if (taskCount > 0) nextActive.research = now

      // Economy from opsSummary
      const sr = opsSummary?.success_rate
      next.economy = sr != null ? `${Math.round(sr * 100)}%` : '--'
      if (sr > 0) nextActive.economy = now

      // Security — fetch threats
      try {
        const res = await fetch('/api/security/threats', { headers: authHeader() })
        if (res.ok) {
          const d = await res.json()
          const score = d?.threat_score ?? d?.score ?? d?.total ?? '--'
          next.security = score
          nextActive.security = now
        } else {
          next.security = '--'
        }
      } catch { next.security = '--' }

      // Memory — fetch graph relations
      try {
        const res = await fetch('/api/memory/graph/relations', { headers: authHeader() })
        if (res.ok) {
          const d = await res.json()
          const count = d?.count ?? d?.total ?? (Array.isArray(d?.relations) ? d.relations.length : '--')
          next.memory = count
          next.knowledge = count
          setMemNodeCount(typeof count === 'number' ? count : null)
          nextActive.memory = now
          nextActive.knowledge = now
        } else {
          next.memory = '--'; next.knowledge = '--'
        }
      } catch { next.memory = '--'; next.knowledge = '--' }

      setPulseMetrics(prev => ({ ...prev, ...next }))
      setLastActive(prev => ({ ...prev, ...nextActive }))
    }

    fetchPulse()
    const id = setInterval(fetchPulse, 15000)
    return () => clearInterval(id)
  }, [agents.length, opsSummary])

  // Sync agent count into pulse metrics live (no poll needed)
  useEffect(() => {
    setPulseMetrics(prev => ({ ...prev, agents: agents.length }))
    if (agents.length > 0) setLastActive(prev => ({ ...prev, agents: Date.now() }))
  }, [agents.length])

  // Focus mode + workspace
  const [focusModeIdx, setFocusModeIdx] = useState(() => {
    const i = FOCUS_MODES.indexOf(localStorage.getItem('nexus:focusMode'))
    return i >= 0 ? i : 0
  })
  const focusMode = FOCUS_MODES[focusModeIdx]
  const setFocusMode = useCallback((mode) => {
    const idx = FOCUS_MODES.indexOf(mode)
    if (idx >= 0) { setFocusModeIdx(idx); localStorage.setItem('nexus:focusMode', mode) }
  }, [])
  const [workspace, setWorkspace] = useState(() => localStorage.getItem('nexus:workspace') || 'DEFAULT')
  const setWs = useCallback((w) => { setWorkspace(w); localStorage.setItem('nexus:workspace', w) }, [])
  const [focusOpen, setFocusOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [voiceActive, setVoiceActive] = useState(false)
  const [composerOpen, setComposerOpen] = useState(false)

  // Health sparkline
  const healthHistory = useRef([50, 50, 50, 50, 50, 50, 50, 50])
  const cpuValue = Math.round(systemHealth.cpu_percent ?? systemHealth.cpu ?? 0)
  const memValue = Math.round(systemHealth.memory_percent ?? 0)
  useEffect(() => {
    healthHistory.current = [...healthHistory.current.slice(1), 100 - cpuValue * 0.3 - memValue * 0.2]
  }, [cpuValue, memValue])
  const sparkPoints = healthHistory.current.map((v, i) => {
    const x = (i / 7) * 56 + 2
    const y = 18 - Math.max(0, Math.min(100, v)) / 100 * 16
    return `${x},${y}`
  }).join(' ')
  const healthPct = Math.max(0, Math.round(100 - cpuValue * 0.3 - memValue * 0.2))
  const healthTrend = healthHistory.current[7] - healthHistory.current[0]

  const miniState = threatScore >= 40 ? 'BUSY' : reasoningSteps.length > 0 ? 'THINKING' : 'IDLE'

  const openPalette = useCallback(() => window.dispatchEvent(new CustomEvent('nx:command-palette:open')), [])
  const toggleVoice = useCallback(() => {
    setVoiceActive(v => !v)
    window.dispatchEvent(new CustomEvent('nx:voice-toggle'))
    window.dispatchEvent(new CustomEvent('nx:voice-open'))
  }, [])
  const toggleChat = useCallback(() => { if (typeof onToggleChat === 'function') onToggleChat(v => !v) }, [onToggleChat])
  const handleNav = useCallback((section) => { if (typeof setActiveSection === 'function') setActiveSection(section) }, [setActiveSection])
  const handleComposer = useCallback(() => {
    if (typeof onToggleChat === 'function') onToggleChat(v => !v)
    else setComposerOpen(o => !o)
  }, [onToggleChat])

  return (
    <div className="cmd-bar">

      {/* ── Pulse strip (Section 1) ── */}
      <PulseStrip metrics={pulseMetrics} lastActive={lastActive} />

      <div className="cmd-bar__sep" />

      {/* Zone 1 — Brand identity */}
      <div className="cmd-bar__brand">
        <BrandMark />
        <div className="cmd-bar__brand-text">
          <div className="cmd-bar__brand-os">SYSTEM OS v2.1.0</div>
          <div className="cmd-bar__brand-status">
            <span className={`cmd-bar__status-dot ${wsConnected ? 'cmd-bar__status-dot--online' : 'cmd-bar__status-dot--offline'}`} />
            STATUS: {wsConnected ? 'OPERATIONAL' : 'DISCONNECTED'}
          </div>
        </div>
      </div>

      <div className="cmd-bar__sep" />

      {/* ── Quick actions (Section 2) ── */}
      <QuickActions onNav={handleNav} onComposer={handleComposer} />

      <div className="cmd-bar__sep" />

      {/* Zone 2 — Command palette pill */}
      <Pill
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>}
        label="COMMAND" sub="CTRL+K" onClick={openPalette} title="Open command palette (Ctrl+K)"
      />

      {/* Zone 3 — Voice command pill */}
      <Pill
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="22" /></svg>}
        label="VOICE" sub={voiceActive ? 'LISTENING…' : 'SPEAK'}
        onClick={toggleVoice} title="Toggle voice command"
        extraClass={voiceActive ? 'cmd-pill--active' : ''}
      >
        <VoiceWaveform active={voiceActive} />
      </Pill>

      {/* Zone 4 — Center chat-toggle mini eye */}
      <div className="cmd-bar__center">
        <button type="button"
          className={`cmd-bar__eye-btn ${chatOpen ? 'cmd-bar__eye-btn--active' : ''}`}
          onClick={toggleChat} title={chatOpen ? 'Close chat' : 'Open chat'} aria-label="Toggle chat panel"
        >
          <div className="cmd-bar__eye-orbits">
            <span className="cmd-bar__eye-orbit cmd-bar__eye-orbit--a" />
            <span className="cmd-bar__eye-orbit cmd-bar__eye-orbit--b" />
          </div>
          <MiniReactor state={miniState} size={72} />
        </button>
        <div className="cmd-bar__eye-label">{chatOpen ? '▼ CHAT' : 'CHAT'}</div>
      </div>

      {/* Zone 5 — Focus mode pill */}
      <div className="cmd-bar__dd-wrap">
        <Pill
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="1" fill="currentColor" /></svg>}
          label="FOCUS" sub={focusMode} onClick={() => setFocusOpen(o => !o)} title="Cycle focus mode"
        />
        {focusOpen && <Dropdown options={FOCUS_MODES} value={focusMode} onChange={setFocusMode} onClose={() => setFocusOpen(false)} />}
      </div>

      {/* Zone 6 — Workspace pill */}
      <div className="cmd-bar__dd-wrap">
        <Pill
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>}
          label="WORK" sub={workspace} onClick={() => setWorkspaceOpen(o => !o)} title="Switch workspace"
        />
        {workspaceOpen && <Dropdown options={WORKSPACES} value={workspace} onChange={setWs} onClose={() => setWorkspaceOpen(false)} />}
      </div>

      <div className="cmd-bar__sep" />

      {/* ── Active task ticker (Section 3) ── */}
      <TaskTicker task={activeTask} />

      <div className="cmd-bar__sep cmd-bar__sep--grow" />

      {/* ── Resource meters (Section 4) ── */}
      <div className="cmd-resource-cluster">
        <ResourceMeter label="CPU" value={cpuValue || '--'} max={100} color="#22d3ee" />
        <ResourceMeter label="MEM" value={memValue || '--'} max={100} color="#a855f7" />
        <ResourceMeter label="AGT" value={agents.length} max={120} color="#22c55e" />
      </div>

      <div className="cmd-bar__sep" />

      {/* Zone 7 — System health cluster */}
      <div className="cmd-bar__health">
        <div className="cmd-bar__health-label">
          HEALTH
          <span className={`cmd-bar__health-arrow ${healthTrend > 1 ? 'cmd-bar__health-arrow--up' : healthTrend < -1 ? 'cmd-bar__health-arrow--down' : ''}`}>
            {healthTrend > 1 ? '↑' : healthTrend < -1 ? '↓' : '→'}
          </span>
        </div>
        <HealthSpark points={sparkPoints} />
        <div className="cmd-bar__health-val">{healthPct}%</div>
        <HealthRing value={healthPct} />
      </div>
    </div>
  )
}
