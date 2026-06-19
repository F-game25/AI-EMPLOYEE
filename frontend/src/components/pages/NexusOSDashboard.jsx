import { useState, useEffect, useRef, useMemo, useCallback, useReducer } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useAppStore } from '../../store/appStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useAgentStore } from '../../store/agentStore'
import { useTaskStore } from '../../store/taskStore'
import { useEconomyStore } from '../../store/economyStore'
import { useSecurityStore } from '../../store/securityStore'
import { useEventFeedStore } from '../../store/eventFeedStore'
import { useSystemStore } from '../../store/systemStore'
import { useForgeStore } from '../../store/forgeStore'
import { useChannelState, STATE_COLOR } from '../../hooks/useChannelState'
import { usePerformanceMode } from '../../hooks/usePerformanceMode'
import CognitiveEye from '../avatar/CognitiveEye'
import NeuralActivityStrip from '../dashboard/NeuralActivityStrip'
import AgentGridNew from '../dashboard/AgentGrid'
import QuickActionsNew from '../dashboard/QuickActions'
import CurrentObjectiveNew from '../dashboard/CurrentObjective'
import CognitiveStreamNew from '../dashboard/CognitiveStream'
import TaskPipelineNew from '../dashboard/TaskPipeline'
import SystemTelemetryNew from '../dashboard/SystemTelemetry'
import TaskComposer from '../core/TaskComposer'
import PanelConnections from '../nexus-ui/PanelConnections'
import './NexusOSDashboard.css'

// ── Banner stack ──────────────────────────────────────────────────────────────
function BannerStack({ rateLimitSeconds, isOffline, onDismissRateLimit }) {
  return (
    <div style={{ position: 'relative', zIndex: 100 }}>
      {isOffline && (
        <div className="nxd__banner nxd__banner--red">
          <span>AI backend offline — responses will be limited</span>
        </div>
      )}
      {rateLimitSeconds > 0 && (
        <div className="nxd__banner nxd__banner--amber">
          <span>Rate limit hit — retry in {rateLimitSeconds}s</span>
          <span className="nxd__banner__dismiss" onClick={onDismissRateLimit} aria-label="Dismiss">✕</span>
        </div>
      )}
    </div>
  )
}

// ── Node detail panel ──────────────────────────────────────────────────────────
const NODE_META = {
  mem:  { id: 'mem',  name: 'Memory System',  category: 'COGNITION',     description: 'Manages vector store, short-term cache, and tiered memory retrieval.' },
  agt:  { id: 'agt',  name: 'Agent Swarm',    category: 'OPERATIONS',    description: 'Orchestrates 70+ active agents across tasks and pipelines.' },
  rsrc: { id: 'rsrc', name: 'Resources',      category: 'ECONOMY',       description: 'Tracks revenue, token cost, active monetization pipelines, and ROI.' },
  sec:  { id: 'sec',  name: 'Security',       category: 'INFRASTRUCTURE',description: 'Monitors threat level, CPU/GPU/RAM health, and system integrity.' },
}

function NodeDetailPanel({ node, isOnline, onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!node) return null
  return (
    <>
      <div className="nxd__node-overlay" onClick={onClose} />
      <div className="nxd__node-detail" role="dialog" aria-modal="true" aria-label={node.name}>
        <div className="nxd__node-detail__header">
          <div>
            <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'rgba(200,212,232,0.45)', marginBottom: 4 }}>{node.category}</div>
            <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '0.04em', color: '#C8D4E8' }}>{node.name}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
            <span className="nxd__node-detail__close" onClick={onClose} aria-label="Close">✕</span>
            <span className="nxd__node-detail__badge" style={isOnline ? {} : { background: 'rgba(239,68,68,.2)', color: '#EF4444' }}>
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
        </div>
        <p style={{ fontSize: 11, color: 'rgba(200,212,232,0.62)', lineHeight: 1.55, margin: 0 }}>{node.description}</p>
        <button
          className="nxd__node-detail__run"
          type="button"
          onClick={() => fetch(`/api/agents/${node.id}/run`, { method: 'POST' }).catch(() => {})}
        >
          RUN
        </button>
      </div>
    </>
  )
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function fmt(ts, seconds = false) {
  if (!ts) return '--:--'
  const d = new Date(typeof ts === 'string' ? ts : Number(ts))
  if (Number.isNaN(d.getTime())) return '--:--'
  const parts = [d.getHours(), d.getMinutes(), ...(seconds ? [d.getSeconds()] : [])]
  return parts.map(v => String(v).padStart(2, '0')).join(':')
}
function num(v, dec = 0) {
  if (typeof v !== 'number') return String(v ?? '0')
  if (v >= 1_000_000) return `${(v/1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v/1_000).toFixed(1)}K`
  return dec > 0 ? v.toFixed(dec) : String(Math.round(v))
}
function money(v) {
  const n = Number(v || 0)
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`
  return `$${Math.round(n)}`
}
function capabilityLabel(capability = '') {
  const raw = typeof capability === 'string' ? capability : (capability.label || capability.id || capability.name || '')
  return String(raw)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}
function capabilityTone(status = '') {
  if (status === 'live') return 'ok'
  if (status === 'dry_run' || status === 'mock') return 'warn'
  if (status === 'fallback') return 'fallback'
  return 'bad'
}

// ── Sparkline ──────────────────────────────────────────────────────────────────
function Spark({ values = [], color = '#FFB800', w = 100, h = 22 }) {
  const pts = values.slice(-20)
  if (pts.length < 2) return <svg width={w} height={h} />
  const max = Math.max(...pts, 1), min = Math.min(...pts)
  const range = max - min || 1
  const step = w / (pts.length - 1)
  const line = pts.map((v, i) => `${i*step},${h - ((v-min)/range)*(h-3) - 1}`).join(' ')
  return (
    <svg width={w} height={h} className="nxd__spark-svg">
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <polyline points={`0,${h} ${line} ${w},${h}`} fill={color} fillOpacity="0.12" strokeWidth="0" />
    </svg>
  )
}

// ── Corner subsystem panel ─────────────────────────────────────────────────────
function CornerPanel({ pos, label, icon, accent, metrics = [], sparkData = [], channelState = 'LIVE', panelId, onClick }) {
  const dotColor = STATE_COLOR[channelState] || STATE_COLOR.OFFLINE
  return (
    <div
      className={`snode snode--${pos} snode--${channelState.toLowerCase()}`}
      style={{ '--acc': accent, cursor: onClick ? 'pointer' : undefined }}
      {...(panelId ? { 'data-panel-id': panelId } : {})}
      onClick={onClick}
    >
      <div className="snode__head">
        <span className="snode__icon">{icon}</span>
        <span className="snode__label">{label}</span>
        {channelState !== 'LIVE' && (
          <span className="snode__state">{channelState}</span>
        )}
        <span className="snode__dot" style={{ background: dotColor, boxShadow: `0 0 6px ${dotColor}` }} />
        <span className="snode__menu">⋯</span>
      </div>
      <div className="snode__metrics">
        {metrics.slice(0, 4).map(([lbl, val], i) => (
          <div key={i} className="snode__metric">
            <div className="snode__m-label">{lbl}</div>
            <div className="snode__m-val">{channelState === 'OFFLINE' ? '— —' : num(val)}</div>
          </div>
        ))}
      </div>
      {sparkData.length > 1 && (
        <div className="snode__spark">
          <Spark values={sparkData} color={accent} w={240} h={18} />
        </div>
      )}
    </div>
  )
}

function CapabilityMatrix({ status, onRefresh, onOpenSetup }) {
  const capabilities = Array.isArray(status?.capabilities) ? status.capabilities : []
  const liveCount = capabilities.filter(c => c.status === 'live').length
  const setupCount = capabilities.filter(c => c.status === 'not_configured' || c.status === 'unavailable').length
  const visible = [...capabilities]
    .sort((a, b) => capabilityTone(a.status).localeCompare(capabilityTone(b.status)))
    .slice(0, 8)
  return (
    <section className="nxd-cap" aria-label="Capability status">
      <div className="nxd-cap__head">
        <div>
          <div className="nxd-cap__kicker">CAPABILITY REGISTRY</div>
          <div className="nxd-cap__title">{liveCount}/{capabilities.length || 0} LIVE</div>
        </div>
        <button className="nxd-cap__refresh" type="button" onClick={onRefresh} disabled={status?.loading}>
          {status?.loading ? 'CHECKING' : 'CHECK'}
        </button>
      </div>
      {status?.next_recommended_action && (
        <button className="nxd-cap__next" type="button" onClick={onOpenSetup}>
          NEXT: {status.next_recommended_action.label}
        </button>
      )}
      {status?.error && <div className="nxd-cap__error">{status.error}</div>}
      <div className="nxd-cap__summary">
        <span>SETUP NEEDED <b>{setupCount}</b></span>
        <span>LAST <b>{status?.lastChecked ? fmt(status.lastChecked, true) : '--:--'}</b></span>
      </div>
      <div className="nxd-cap__list">
        {visible.map(capability => (
          <div key={capability.id || capability.name} className={`nxd-cap__row nxd-cap__row--${capabilityTone(capability.status)}`}>
            <span className="nxd-cap__dot" />
            <span className="nxd-cap__name">{capabilityLabel(capability)}</span>
            <span className="nxd-cap__status">{String(capability.status || 'unknown').replace(/_/g, ' ')}</span>
          </div>
        ))}
        {!visible.length && (
          <div className="nxd-cap__empty">Capability status unavailable</div>
        )}
      </div>
    </section>
  )
}

function ForgeRuntimePanel({ forge, onOpenForge, onOpenApprovals, onOpenProof, onOpenMemory }) {
  const run = forge.activeRun
  const health = forge.health || {}
  const validation = forge.validation || {}
  const report = forge.reports?.[0]
  const agentEngine = forge.agentEngine || {}
  const pending = forge.pendingApprovals?.length || 0
  const state = health.state || (forge.error ? 'degraded' : 'live')
  return (
    <section className="nxd-forge" aria-label="Forge operational runtime">
      <div className="nxd-forge__head">
        <div>
          <div className="nxd-forge__kicker">ASCEND FORGE RUNTIME</div>
          <div className="nxd-forge__title">{run?.status || 'NO ACTIVE RUN'}</div>
        </div>
        <span className={`nxd-forge__state nxd-forge__state--${state}`}>{state}</span>
      </div>
      <button className="nxd-forge__run" type="button" onClick={onOpenForge}>
        <span>{run?.goal || 'Open Forge to create or select a task'}</span>
        <b>{run?.run_id || run?.id || 'FORGE'}</b>
      </button>
      <div className="nxd-forge__grid">
        <button type="button" onClick={onOpenApprovals}>
          <span>APPROVALS</span>
          <b>{pending}</b>
        </button>
        <button type="button" onClick={onOpenProof}>
          <span>VALIDATION</span>
          <b>{validation.status || 'unknown'}</b>
        </button>
        <button type="button" onClick={onOpenForge}>
          <span>REPORTS</span>
          <b>{forge.reports?.length || 0}</b>
        </button>
        <button type="button" onClick={onOpenMemory}>
          <span>MEMORY</span>
          <b>{forge.memoryLessons?.length || 0}</b>
        </button>
      </div>
      <div className="nxd-forge__meta">
        <span>AGENT ENGINE</span>
        <b>{agentEngine.state || 'unknown'}</b>
      </div>
      {report?.summary && <div className="nxd-forge__report">{report.summary}</div>}
      {forge.error && <div className="nxd-forge__error">{forge.error}</div>}
    </section>
  )
}

// ── Orchestrator state derivation ──────────────────────────────────────────────
function deriveOrchestratorState({ thinking, executing, errorCount, busyLoad }) {
  if (errorCount > 0)   return 'ERROR'
  if (executing)        return 'EXECUTING'
  if (busyLoad > 0.75)  return 'BUSY'
  if (thinking)         return 'THINKING'
  return 'IDLE'
}

function eventSeverity(ev) {
  const raw = String(ev?.priority || ev?.level || ev?.severity || 'info').toLowerCase()
  if (raw === 'critical' || raw === 'error') return 'critical'
  if (raw === 'warning' || raw === 'warn') return 'warning'
  if (raw === 'notice' || raw === 'success' || raw === 'ok') return 'success'
  return 'info'
}

function eventText(ev) {
  return ev?.notes || ev?.text || ev?.message || ev?.title || ev?.data?.notes || ev?.data?.message || ev?.kind || 'System event'
}

// ── Sidebar: Event Stream ──────────────────────────────────────────────────────
function EventStream({ events = [] }) {
  const [filter, setFilter] = useState('all')
  const tabs = ['all', 'critical', 'warning', 'info', 'success']
  const items = useMemo(() => {
    return [...events]
      .sort((a, b) => (Number(b.ts || b.timestamp || 0) - Number(a.ts || a.timestamp || 0)))
      .filter(ev => filter === 'all' || eventSeverity(ev) === filter)
      .slice(0, 14)
  }, [events, filter])
  return (
    <div className="estream">
      <div className="estream__hd">
        <span>EVENT INTELLIGENCE STREAM</span>
        <span className="estream__live">● LIVE</span>
      </div>
      <div className="estream__tabs" role="tablist" aria-label="Event filters">
        {tabs.map(tab => (
          <button
            key={tab}
            type="button"
            className={`estream__tab ${filter === tab ? 'estream__tab--active' : ''}`}
            onClick={() => setFilter(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="estream__rows">
        {items.map((ev, i) => {
          const severity = eventSeverity(ev)
          return (
          <div key={ev.id || i} className={`estream__row estream__row--${severity}`}>
            <span className="estream__sev" aria-hidden="true" />
            <span className="estream__body">
              <span className="estream__line">
                <span className="estream__cat">{(ev.category || ev.kind || 'SYS').toUpperCase().slice(0, 12)}</span>
                <span className="estream__t">{fmt(ev.ts || ev.timestamp, true)}</span>
              </span>
              <span className="estream__msg">{eventText(ev).slice(0, 96)}</span>
            </span>
          </div>
        )})}
        {items.length === 0 && <div className="estream__empty">No live events for this filter</div>}
      </div>
    </div>
  )
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────
export default function NexusOSDashboard() {
  const { setActiveSection, systemHealth: _systemHealth, wsConnected } = useAppStore(
    useShallow(s => ({ setActiveSection: s.setActiveSection, systemHealth: s.systemHealth, wsConnected: s.wsConnected }))
  )
  const systemHealth = _systemHealth || {}
  // Auto-adapt to PC specs: heavy canvas avatar only on capable hardware.
  // On low-tier machines fall back to the zero-canvas-cost SVG so the dashboard
  // stays usable (functional before cool).
  const { tier } = usePerformanceMode()
  const avatarMode = tier === 'low' ? 'toolbar' : 'dashboard'

  const { reasoningSteps: _reasoningSteps, modelCalls: _modelCalls, memoryWrites: _memoryWrites, brainState: _brainState, brainActivity: _brainActivity } = useCognitiveStore(
    useShallow(s => ({ reasoningSteps: s.reasoningSteps, modelCalls: s.modelCalls, memoryWrites: s.memoryWrites, brainState: s.brainState, brainActivity: s.brainActivity }))
  )
  const reasoningSteps = _reasoningSteps || []
  const modelCalls     = _modelCalls || []
  const memoryWrites   = _memoryWrites || []
  const brainState     = _brainState || {}
  const brainActivity  = _brainActivity || {}

  const agents = useAgentStore(s => s.agents) || []

  const { executionSteps: _executionSteps, workflowState: _workflowState, opsSummary: _opsSummary } = useTaskStore(
    useShallow(s => ({ executionSteps: s.executionSteps, workflowState: s.workflowState, opsSummary: s.opsSummary }))
  )
  const executionSteps = _executionSteps || []
  const workflowState  = _workflowState || {}
  const opsSummary     = _opsSummary || {}

  const { revenue: _revenue, monetizationPipelines: _monetizationPipelines } = useEconomyStore(
    useShallow(s => ({ revenue: s.revenue, monetizationPipelines: s.monetizationPipelines }))
  )
  const revenue               = _revenue || {}
  const monetizationPipelines = _monetizationPipelines || {}

  const threatLevel = useSecurityStore(s => s.securityStatus?.threat_score) || 0
  const events      = useEventFeedStore(s => s.events) || []

  // Rolling history buffers for sparklines
  const cpuHist = useRef(new Array(20).fill(0))
  const revHist = useRef(new Array(20).fill(0))
  const tokHist = useRef(new Array(20).fill(0))
  const ramHist = useRef(new Array(20).fill(0))

  useEffect(() => {
    cpuHist.current = [...cpuHist.current.slice(1), systemHealth.cpu_percent ?? 0]
    ramHist.current = [...ramHist.current.slice(1), systemHealth.memory_percent ?? 0]
  }, [systemHealth.cpu_percent, systemHealth.memory_percent])

  useEffect(() => {
    revHist.current = [...revHist.current.slice(1), revenue.today ?? revenue.daily ?? 0]
  }, [revenue.today, revenue.daily])

  useEffect(() => {
    tokHist.current = [...tokHist.current.slice(1), modelCalls.length]
  }, [modelCalls.length])

  const { systemStatus: _systemStatus, capabilityStatus, fetchCapabilityStatus } = useSystemStore(
    useShallow(s => ({ systemStatus: s.systemStatus, capabilityStatus: s.capabilityStatus, fetchCapabilityStatus: s.fetchCapabilityStatus }))
  )
  const systemStatus = _systemStatus || {}
  const forge = useForgeStore(
    useShallow(s => ({
      activeRun: s.activeRun,
      health: s.health,
      validation: s.validation,
      reports: s.reports,
      pendingApprovals: s.pendingApprovals,
      memoryLessons: s.memoryLessons,
      agentEngine: s.agentEngine,
      error: s.error,
      refresh: s.refresh,
      ensurePolling: s.ensurePolling,
    }))
  )

  // ── Banner state ──────────────────────────────────────────────────────────
  const [rateLimitSecs, setRateLimitSecs] = useState(0)
  const [isOffline, setIsOffline] = useState(false)

  useEffect(() => {
    const onRateLimit = e => setRateLimitSecs(e.detail?.seconds ?? 60)
    window.addEventListener('nx:rate-limit', onRateLimit)
    return () => window.removeEventListener('nx:rate-limit', onRateLimit)
  }, [])

  useEffect(() => {
    if (rateLimitSecs <= 0) return
    const t = setInterval(() => setRateLimitSecs(s => Math.max(0, s - 1)), 1000)
    return () => clearInterval(t)
  }, [rateLimitSecs])

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch('/api/health')
        const j = await r.json().catch(() => ({}))
        setIsOffline(j?.python_backend === 'offline')
      } catch { setIsOffline(true) }
    }
    check()
    const t = setInterval(check, 15_000)
    return () => clearInterval(t)
  }, [])

  // ── Node detail state ─────────────────────────────────────────────────────
  const [selectedNode, setSelectedNode] = useState(null)

  useEffect(() => {
    fetchCapabilityStatus?.()
  }, [fetchCapabilityStatus])

  useEffect(() => {
    forge.ensurePolling?.()
    forge.refresh?.({ silent: true, reason: 'dashboard_mount' }).catch(() => {})
  }, [forge.ensurePolling, forge.refresh])

  const fieldRef = useRef(null)
  useEffect(() => {
    const onVis = () => fieldRef.current?.classList.toggle('nxd__field--paused', document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  const cpu      = systemHealth.cpu_percent ?? systemStatus.cpu ?? systemStatus.cpu_usage ?? 0
  const ram      = systemHealth.memory_percent ?? systemStatus.memory ?? 0
  const gpu      = systemHealth.gpu_percent ?? systemStatus.gpu_usage ?? 0
  const gpuTemp  = systemStatus.gpu_temperature ?? systemHealth.gpu_temp ?? 0
  const load     = Math.min(1, cpu / 100)
  const thinking = reasoningSteps.length > 0
  const runningSteps  = useMemo(() => executionSteps.filter(s => s.status === 'running'), [executionSteps])
  const pendingSteps  = useMemo(() => executionSteps.filter(s => s.status === 'pending'),  [executionSteps])
  const recentSteps   = useMemo(() => reasoningSteps.slice(-6), [reasoningSteps])
  const running  = runningSteps.length
  const pending  = pendingSteps.length
  const activeAgents = useMemo(() => agents.filter(a => a.status === 'active' || a.status === 'running' || a.active).length, [agents])
  const pipelines = useMemo(() => Object.values(monetizationPipelines).filter(p => p.active).length, [monetizationPipelines])
  const currentStep = runningSteps[0]
  const healthPct = Math.max(0, Math.round(100 - cpu * 0.3 - ram * 0.2))
  const errorCount = events.filter(e => (e.priority||'').toLowerCase() === 'critical' || (e.priority||'').toLowerCase() === 'error').length
  const activeTasks = opsSummary.active_tasks ?? workflowState.active_tasks ?? running
  const queuedTasks = opsSummary.queued_tasks ?? workflowState.queued_tasks ?? pending
  const successRate = opsSummary.success_rate ?? workflowState.success_rate ?? 0
  const avgExecTime = opsSummary.avg_exec_time ?? workflowState.avg_exec_time ?? 0
  const dailyRevenue = revenue.today ?? revenue.daily ?? revenue.total ?? 0
  const roiTrend = revenue.roi_trend ?? revenue.roi_pct ?? revenue.roi_7d ?? 0
  const tokenCost = revenue.token_cost ?? revenue.cost_today ?? 0
  const contextDepth = brainState.memory_size ?? brainActivity.memory_size ?? memoryWrites.length
  const memoryRate = brainActivity.memory_writes_per_sec ?? brainState.memory_writes_per_sec ?? memoryWrites.length
  const orchestratorState = deriveOrchestratorState({
    thinking,
    executing: activeTasks > 0,
    errorCount,
    busyLoad: load,
  })

  // Wire orchestrator state + hardware load → avatar eye color/energy
  useEffect(() => {
    const highLoad = cpu > 70 || gpu > 70
    const hotTemp  = gpuTemp > 78
    const busy     = activeTasks > 3 || thinking

    let state = 'idle'
    if (hotTemp)       state = 'alert'
    else if (highLoad) state = 'executing'
    else if (busy)     state = 'thinking'
    else {
      const stateMap = { idle: 'idle', thinking: 'thinking', executing: 'executing', error: 'alert', busy: 'listening' }
      state = stateMap[orchestratorState?.toLowerCase()] || 'idle'
    }

    window.NX?.setState?.(state)
    window.NX?.setSpeakLevel?.(Math.min(0.9, cpu / 100 * 0.55 + activeTasks * 0.04))
  }, [cpu, gpu, gpuTemp, activeTasks, thinking, orchestratorState])

  const focusKeyword = currentStep?.description?.split(' ')[0] || currentStep?.task?.split(' ')[0] || 'NEXUS'

  // Per-channel freshness states
  const cognitionState = useChannelState(modelCalls.length, 10_000)
  const operationsState = useChannelState(activeTasks + queuedTasks, 15_000)
  const economyState   = useChannelState(dailyRevenue, 30_000)
  const infraState     = useChannelState(systemHealth.cpu_percent, 5_000)

  return (
    <div className="nxd">
      <BannerStack
        rateLimitSeconds={rateLimitSecs}
        isOffline={isOffline}
        onDismissRateLimit={() => setRateLimitSecs(0)}
      />
      <NodeDetailPanel
        node={selectedNode ? NODE_META[selectedNode] : null}
        isOnline={!isOffline}
        onClose={() => setSelectedNode(null)}
      />
      {/* ═══ CENTER STAGE ═════════════════════════════════════════════════════ */}
      <div className="nxd__center">
        {/* Top status strip */}
        <div className="nxd__strip">
          <div className={`nxd__conn ${wsConnected ? 'nxd__conn--ok' : 'nxd__conn--err'}`}>
            <span className="nxd__conn-dot" />
            {wsConnected ? 'CONNECTED' : 'RECONNECTING'}
          </div>
          <span className="nxd__stat">CPU <b>{Math.round(cpu)}%</b></span>
          <span className="nxd__stat">RAM <b>{Math.round(ram)}%</b></span>
          <span className="nxd__stat">AGENTS <b>{activeAgents}</b></span>
          <span className="nxd__stat">TASKS <b>{running}</b></span>
          <span className="nxd__stat">GPU <b>{Math.round(gpu)}%</b></span>
          <span className={`nxd__stat${gpuTemp > 75 ? ' nxd__stat--hot' : ''}`}>TEMP <b>{Math.round(gpuTemp)}°C</b></span>
          <span className={`nxd__threat ${threatLevel >= 40 ? 'nxd__threat--hi' : ''}`}>
            THREAT <b>{threatLevel}</b>
          </span>
          <span className="nxd__health">HEALTH <b>{healthPct}%</b></span>
        </div>

        {/* The arena — eye centerpiece with 4 corner panels */}
        <div className="nxd__stage">
          <div ref={fieldRef} className="nxd__field" aria-hidden="true">
            <span className="nxd__axis nxd__axis--h" />
            <span className="nxd__axis nxd__axis--v" />
            <span className="nxd__beam nxd__beam--h" />
            <span className="nxd__beam nxd__beam--v" />
            <span className="nxd__ring nxd__ring--1" />
            <span className="nxd__ring nxd__ring--2" />
            <span className="nxd__ring nxd__ring--3" />
            <span className="nxd__ring nxd__ring--4" />
            <span className="nxd__ring nxd__ring--5" />
            <span className="nxd__connline nxd__connline--tl" />
            <span className="nxd__connline nxd__connline--tr" />
            <span className="nxd__connline nxd__connline--bl" />
            <span className="nxd__connline nxd__connline--br" />
          </div>

          {/* Robotic Eye centerpiece */}
          <div className="nxd__eye-caption" data-panel-id="neural">
            <div className="nxd__eye-title">COGNITIVE CORE</div>
            <div className="nxd__eye-sub">AUTONOMOUS AI INTELLIGENCE</div>
            <div className={`nxd__eye-state nxd__eye-state--${orchestratorState.toLowerCase()}`}>
              <span className="nxd__eye-state-dot" />
              {orchestratorState}
            </div>
          </div>
          <div className="nxd__orbwrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CognitiveEye
              size={480}
              mode={avatarMode}
              onClick={() => window.dispatchEvent(new CustomEvent('nx:companion:open'))}
            />
          </div>

          {/* TOP-LEFT — Cognition · cyan */}
          <CornerPanel
            pos="tl"
            panelId="mem"
            label="COGNITION"
            icon="◈"
            accent="#00D4FF"
            channelState={cognitionState}
            metrics={[
              ['REASONING CHAINS', reasoningSteps.length],
              ['TOKENS / SEC',     modelCalls.length],
              ['CONTEXT DEPTH',    contextDepth],
              ['MEMORY WRITES',    `${num(memoryRate)}/s`],
            ]}
            sparkData={tokHist.current}
            onClick={() => setSelectedNode('mem')}
          />

          {/* TOP-RIGHT — Operations · gold */}
          <CornerPanel
            pos="tr"
            panelId="agt"
            label="OPERATIONS"
            icon="⚙"
            accent="#F5A623"
            channelState={operationsState}
            metrics={[
              ['ACTIVE TASKS',  activeTasks],
              ['QUEUED TASKS',  queuedTasks],
              ['SUCCESS RATE',  `${successRate}%`],
              ['EXEC TIME',     `${avgExecTime}s`],
            ]}
            sparkData={cpuHist.current}
            onClick={() => setSelectedNode('agt')}
          />

          {/* BOTTOM-LEFT — Economy · purple */}
          <CornerPanel
            pos="bl"
            panelId="rsrc"
            label="ECONOMY"
            icon="$"
            accent="#B565F5"
            channelState={economyState}
            metrics={[
              ['DAILY REVENUE',    money(dailyRevenue)],
              ['PIPELINES ACTIVE', pipelines],
              ['ROI 7D',           `${roiTrend}%`],
              ['TOKEN COST',       money(tokenCost)],
            ]}
            sparkData={revHist.current}
            onClick={() => setSelectedNode('rsrc')}
          />

          {/* BOTTOM-RIGHT — Infrastructure · green */}
          <CornerPanel
            pos="br"
            panelId="sec"
            label="INFRASTRUCTURE"
            icon="▣"
            accent={threatLevel >= 40 ? '#FF4444' : '#00FFB4'}
            channelState={infraState}
            metrics={[
              ['CPU USAGE',  `${Math.round(cpu)}%`],
              ['GPU USAGE',  `${Math.round(gpu)}%`],
              ['RAM USAGE',  `${Math.round(ram)}%`],
              ['GPU TEMP',   `${Math.round(gpuTemp)}°C`],
            ]}
            sparkData={ramHist.current}
            onClick={() => setSelectedNode('sec')}
          />
        </div>

        <NeuralActivityStrip />

        <div className="nxd__mission">
          <CurrentObjectiveNew />
          <CognitiveStreamNew />
        </div>

        <div className="nxd__lower">
          <TaskPipelineNew />
          <SystemTelemetryNew />
        </div>
      </div>

      {/* ═══ RIGHT SIDEBAR ════════════════════════════════════════════════════ */}
      <div className="nxd__sidebar">
        <EventStream events={events} />
        <div className="nxd__div" />
        <ForgeRuntimePanel
          forge={forge}
          onOpenForge={() => setActiveSection('ascend-forge')}
          onOpenApprovals={() => setActiveSection('approvals')}
          onOpenProof={() => setActiveSection('proof')}
          onOpenMemory={() => setActiveSection('memory')}
        />
        <div className="nxd__div" />
        <CapabilityMatrix
          status={capabilityStatus}
          onRefresh={fetchCapabilityStatus}
          onOpenSetup={() => setActiveSection('setup')}
        />
        <div className="nxd__div" />
        <TaskComposer
          title="RUN TASK"
          subtitle="Start work through the canonical turn runner."
          source="dashboard-composer"
          compact
        />
        <div className="nxd__div" />
        <AgentGridNew />
        <div className="nxd__div" />
        <QuickActionsNew />
      </div>
    </div>
  )
}
