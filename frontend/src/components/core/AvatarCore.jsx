import { useRef, useEffect, useState, useCallback } from 'react'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useAgentStore } from '../../store/agentStore'
import { useTaskStore } from '../../store/taskStore'
import { useSecurityStore } from '../../store/securityStore'
import { useEventFeedStore } from '../../store/eventFeedStore'
import './AvatarCore.css'

// ── 9-State machine ──────────────────────────────────────────────────────────
function deriveState({ reasoningCount, runningAgents, threatScore, activeTaskCount, memWrites }) {
  if (threatScore >= 75) return 'error'
  if (threatScore >= 40) return 'warning'
  if (reasoningCount > 15) return 'focused'
  if (reasoningCount > 8) return 'thinking'
  if (runningAgents > 0 || activeTaskCount > 0) return 'executing'
  if (memWrites > 2) return 'learning'
  if (reasoningCount > 0) return 'planning'
  return 'idle'
}

const STATE_LABELS = {
  idle: 'STANDBY',
  thinking: 'ANALYZING',
  planning: 'PLANNING',
  executing: 'EXECUTING',
  learning: 'LEARNING',
  warning: 'ALERT',
  focused: 'FOCUSED',
  sleeping: 'DORMANT',
  error: 'CRITICAL',
}

// Eye target positions per state (x, y in px from center)
const EYE_TARGETS = {
  idle:      { x: 0,   y: 0   },
  thinking:  { x: 6,   y: -8  },
  planning:  { x: -6,  y: 4   },
  executing: { x: 0,   y: 8   },
  learning:  { x: -8,  y: -6  },
  warning:   { x: 10,  y: -10 },
  focused:   { x: 0,   y: -10 },
  sleeping:  { x: 0,   y: 4   },
  error:     { x: 0,   y: 0   },
}

const PILL_METRICS = ['agents', 'queue', 'memory', 'threat', 'steps']

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}

function categorizeFeedEvent(evt) {
  const cat = evt.category || evt.type || ''
  if (cat.includes('cogni') || cat.includes('reason') || cat.includes('think')) return 'cognition'
  if (cat.includes('memo') || cat.includes('mem')) return 'memory'
  if (cat.includes('agent')) return 'agent'
  if (cat.includes('econom') || cat.includes('revenue') || cat.includes('money')) return 'economy'
  if (cat.includes('secur') || cat.includes('threat')) return 'security'
  return 'system'
}

// ── Component ────────────────────────────────────────────────────────────────
export default function AvatarCore() {
  const eyeRef = useRef(null)
  const orbRef = useRef(null)

  // ── Store subscriptions ──────────────────────────────────────────────────
  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps) || []
  const memoryWrites   = useCognitiveStore(s => s.memoryWrites) || []
  const agents          = useAgentStore(s => s.agents) || []
  const executionSteps  = useTaskStore(s => s.executionSteps) || []
  const workflowState   = useTaskStore(s => s.workflowState) || {}
  const threatScore     = useSecurityStore(s => s.securityStatus?.threat_score) || 0
  const feedEvents      = useEventFeedStore(s => s.events) || []

  // ── Derived ─────────────────────────────────────────────────────────────
  const runningAgents   = agents.filter(a => a.status === 'running' || a.active).length
  const activeTaskCount = executionSteps.filter(s => s.status === 'running').length
  const queueDepth      = executionSteps.filter(s => s.status === 'pending').length || activeTaskCount
  const state = deriveState({
    reasoningCount: reasoningSteps.length,
    runningAgents,
    threatScore,
    activeTaskCount,
    memWrites: memoryWrites.length,
  })

  // ── Eye movement on state change ─────────────────────────────────────────
  useEffect(() => {
    if (!eyeRef.current) return
    const target = EYE_TARGETS[state] || { x: 0, y: 0 }
    eyeRef.current.style.transform = `translate(${target.x}px, ${target.y}px)`
  }, [state])

  // ── Rotatable activity pills ─────────────────────────────────────────────
  const [pillState, setPillState] = useState({ tl: 0, tr: 1, bl: 2, br: 3 })

  const rotatePill = useCallback((pos) => {
    setPillState(prev => ({ ...prev, [pos]: (prev[pos] + 1) % PILL_METRICS.length }))
  }, [])

  const getPillData = (metricKey) => {
    switch (metricKey) {
      case 'agents': return { value: runningAgents, label: 'Running Agents' }
      case 'queue':  return { value: queueDepth, label: 'Queue Depth' }
      case 'memory': return { value: memoryWrites.length, label: 'Mem Writes' }
      case 'threat': return { value: threatScore, label: 'Threat Score' }
      case 'steps':  return { value: reasoningSteps.length, label: 'Reasoning Steps' }
      default:       return { value: 0, label: '—' }
    }
  }

  // ── Thought feed (last 6 high-priority events) ───────────────────────────
  const feedItems = feedEvents
    .filter(e => e.priority === 'high' || e.priority === 'critical' || !e.priority)
    .slice(-6)
    .reverse()

  return (
    <div className="avatar-core">
      {/* ── Avatar Container (rings + orb + pills) ── */}
      <div className="avatar-container">

        {/* Orbit rings — each rotates independently via CSS */}
        <div className="avatar-ring avatar-ring--4" />
        <div className="avatar-ring avatar-ring--3" />
        <div className="avatar-ring avatar-ring--2" />
        <div className="avatar-ring avatar-ring--1" />

        {/* Core orb — 3 shells + eye */}
        <div className={`avatar-orb avatar-orb--${state}`} ref={orbRef}>
          <div className="avatar-orb__shell avatar-orb__shell--outer" />
          <div className="avatar-orb__shell avatar-orb__shell--mid" />
          <div className="avatar-orb__shell avatar-orb__shell--inner" />
          <div className="avatar-orb__eye" ref={eyeRef}>
            <div className="avatar-orb__pupil" />
          </div>

          {/* State label below the orb */}
          <div className="avatar-state-badge">{STATE_LABELS[state]}</div>
        </div>

        {/* Activity pills (corners, clickable to rotate metric) */}
        <Pill pos="tl" data={getPillData(PILL_METRICS[pillState.tl])} onClick={() => rotatePill('tl')} />
        <Pill pos="tr" data={getPillData(PILL_METRICS[pillState.tr])} onClick={() => rotatePill('tr')} />
        <Pill pos="bl" data={getPillData(PILL_METRICS[pillState.bl])} onClick={() => rotatePill('bl')} />
        <Pill pos="br" data={getPillData(PILL_METRICS[pillState.br])} onClick={() => rotatePill('br')} />
      </div>

      {/* ── Live thought feed ── */}
      <div className="avatar-thought-feed">
        {feedItems.length === 0 ? (
          <div className="feed-empty">Awaiting cognitive events…</div>
        ) : feedItems.map((evt, i) => {
          const cat = categorizeFeedEvent(evt)
          const text = evt.text || evt.message || evt.content || ''
          return (
            <div key={i} className="feed-event">
              <span className="feed-dot">▸</span>
              <span className="feed-text">{text.slice(0, 80)}</span>
              <span className={`feed-category feed-category--${cat}`}>{cat}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Pill({ pos, data, onClick }) {
  return (
    <div className={`avatar-pill avatar-pill--${pos}`} onClick={onClick} title="Click to cycle metric">
      <div className="pill-metric">{data.value}</div>
      <div className="pill-label">{data.label}</div>
      <div className="pill-hint">click to cycle</div>
    </div>
  )
}
