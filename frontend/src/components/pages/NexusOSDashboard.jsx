import { useState, useEffect, useRef, useMemo } from 'react'
import { useAppStore } from '../../store/appStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useAgentStore } from '../../store/agentStore'
import { useTaskStore } from '../../store/taskStore'
import { useEconomyStore } from '../../store/economyStore'
import { useSecurityStore } from '../../store/securityStore'
import { useEventFeedStore } from '../../store/eventFeedStore'
import { useSystemStore } from '../../store/systemStore'
import { useChannelState, STATE_COLOR } from '../../hooks/useChannelState'
import CognitiveEye from '../avatar/CognitiveEye'
import NeuralActivityStrip from '../dashboard/NeuralActivityStrip'
import AgentGridNew from '../dashboard/AgentGrid'
import QuickActionsNew from '../dashboard/QuickActions'
import CurrentObjectiveNew from '../dashboard/CurrentObjective'
import CognitiveStreamNew from '../dashboard/CognitiveStream'
import TaskPipelineNew from '../dashboard/TaskPipeline'
import SystemTelemetryNew from '../dashboard/SystemTelemetry'
import TaskComposer from '../core/TaskComposer'
import './NexusOSDashboard.css'

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
    <svg width={w} height={h} style={{ overflow:'visible' }}>
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <polyline points={`0,${h} ${line} ${w},${h}`} fill={color} fillOpacity="0.12" strokeWidth="0" />
    </svg>
  )
}

// ── Corner subsystem panel ─────────────────────────────────────────────────────
function CornerPanel({ pos, label, icon, accent, metrics = [], sparkData = [], channelState = 'LIVE' }) {
  const dotColor = STATE_COLOR[channelState] || STATE_COLOR.OFFLINE
  return (
    <div className={`snode snode--${pos} snode--${channelState.toLowerCase()}`} style={{ '--acc': accent }}>
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
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const systemHealth  = useAppStore(s => s.systemHealth) || {}
  const wsConnected   = useAppStore(s => s.wsConnected)

  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps) || []
  const modelCalls     = useCognitiveStore(s => s.modelCalls) || []
  const memoryWrites   = useCognitiveStore(s => s.memoryWrites) || []
  const brainState     = useCognitiveStore(s => s.brainState) || {}
  const brainActivity  = useCognitiveStore(s => s.brainActivity) || {}

  const agents         = useAgentStore(s => s.agents) || []
  const executionSteps = useTaskStore(s => s.executionSteps) || []
  const workflowState  = useTaskStore(s => s.workflowState) || {}
  const opsSummary     = useTaskStore(s => s.opsSummary) || {}

  const revenue               = useEconomyStore(s => s.revenue) || {}
  const monetizationPipelines = useEconomyStore(s => s.monetizationPipelines) || {}

  const threatLevel = useSecurityStore(s => s.securityStatus?.threat_score) || 0
  const events      = useEventFeedStore(s => s.events) || []

  // Rolling history buffers for sparklines
  const cpuHist = useRef(new Array(20).fill(0))
  const revHist = useRef(new Array(20).fill(0))
  const tokHist = useRef(new Array(20).fill(0))
  const ramHist = useRef(new Array(20).fill(0))

  useEffect(() => {
    cpuHist.current = [...cpuHist.current.slice(1), systemHealth.cpu_percent ?? 0]
  }, [systemHealth.cpu_percent])
  useEffect(() => {
    ramHist.current = [...ramHist.current.slice(1), systemHealth.memory_percent ?? 0]
  }, [systemHealth.memory_percent])
  useEffect(() => {
    revHist.current = [...revHist.current.slice(1), revenue.today ?? revenue.daily ?? 0]
  }, [revenue.today, revenue.daily])
  useEffect(() => {
    tokHist.current = [...tokHist.current.slice(1), modelCalls.length]
  }, [modelCalls.length])

  const systemStatus = useSystemStore(s => s.systemStatus) || {}
  const capabilityStatus = useSystemStore(s => s.capabilityStatus)
  const fetchCapabilityStatus = useSystemStore(s => s.fetchCapabilityStatus)

  useEffect(() => {
    fetchCapabilityStatus?.()
  }, [fetchCapabilityStatus])

  const cpu      = systemHealth.cpu_percent ?? systemStatus.cpu ?? systemStatus.cpu_usage ?? 0
  const ram      = systemHealth.memory_percent ?? systemStatus.memory ?? 0
  const gpu      = systemHealth.gpu_percent ?? systemStatus.gpu_usage ?? 0
  const gpuTemp  = systemStatus.gpu_temperature ?? systemHealth.gpu_temp ?? 0
  const load     = Math.min(1, cpu / 100)
  const thinking = reasoningSteps.length > 0
  const running  = executionSteps.filter(s => s.status === 'running').length
  const pending  = executionSteps.filter(s => s.status === 'pending').length
  const activeAgents = agents.filter(a => a.status === 'active' || a.status === 'running' || a.active).length
  const pipelines = Object.values(monetizationPipelines).filter(p => p.active).length
  const currentStep = executionSteps.find(s => s.status === 'running')
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
          <div className="nxd__field" aria-hidden="true">
            <span className="nxd__ring nxd__ring--4" />
            <span className="nxd__ring nxd__ring--5" />
            <span className="nxd__connline nxd__connline--tl" />
            <span className="nxd__connline nxd__connline--tr" />
            <span className="nxd__connline nxd__connline--bl" />
            <span className="nxd__connline nxd__connline--br" />
          </div>

          {/* Robotic Eye centerpiece */}
          <div className="nxd__eye-caption">
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
              mode="dashboard"
              onClick={() => window.dispatchEvent(new CustomEvent('nx:companion:open'))}
            />
          </div>

          {/* TOP-LEFT — Cognition · cyan */}
          <CornerPanel
            pos="tl"
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
          />

          {/* TOP-RIGHT — Operations · gold */}
          <CornerPanel
            pos="tr"
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
          />

          {/* BOTTOM-LEFT — Economy · purple */}
          <CornerPanel
            pos="bl"
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
          />

          {/* BOTTOM-RIGHT — Infrastructure · green */}
          <CornerPanel
            pos="br"
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
