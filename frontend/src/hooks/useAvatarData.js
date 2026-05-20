import { useMemo } from 'react'
import { useAgentStore } from '../store/agentStore'
import { useTaskStore } from '../store/taskStore'
import { useCognitiveStore } from '../store/cognitiveStore'
import { useEventFeedStore } from '../store/eventFeedStore'
import { useSystemStore } from '../store/systemStore'

// ── 4-char uppercase hex hash (FNV-1a-ish, fast & deterministic) ──
function hash4(input) {
  const s = String(input ?? '')
  if (!s) return '0000'
  let h = 0x811c9dc5 >>> 0
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return (h & 0xffff).toString(16).toUpperCase().padStart(4, '0')
}

function extractTraceId(evt) {
  if (!evt) return null
  return (
    evt.context?.trace_id ||
    evt.data?.trace_id ||
    evt.data?.traceId ||
    evt.context?.traceId ||
    evt.id ||
    null
  )
}

// Truncate-and-uppercase hex-ish trace id to 4 chars; if non-hex, fall back to hash4.
function toHex4(value) {
  const s = String(value ?? '')
  const cleaned = s.replace(/[^0-9a-fA-F]/g, '')
  if (cleaned.length >= 4) return cleaned.slice(0, 4).toUpperCase()
  return hash4(s)
}

// Aperture: 0 → 0.95, 1-5 → 0.7, 6-20 → 0.5, 20+ → 0.3
function deriveAperture(queueDepth) {
  if (queueDepth <= 0) return 0.95
  if (queueDepth <= 5) return 0.7
  if (queueDepth <= 20) return 0.5
  return 0.3
}

// Gear period (seconds per revolution): log-mapped from tokens/sec.
//   0 → 60s, 1k → 20s, 100k → 8s, 1M+ → 3s
function deriveGearSpeed(tokensRate) {
  const r = Math.max(0, Number(tokensRate) || 0)
  if (r <= 0) return 60
  // log10(1) = 0 → 60s. log10(1M) = 6 → 3s. Smooth interpolation.
  const l = Math.log10(r + 1) // 0..~6
  // Anchor points: 0→60, 3→20, 5→8, 6→3
  const period = 60 - l * 9.5
  return Math.max(3, Math.min(60, period))
}

export function useAvatarData() {
  // ── Store reads (kept narrow so Zustand re-renders only on relevant changes) ──
  const agents = useAgentStore(s => s.agents) || []
  const opsSummary = useTaskStore(s => s.opsSummary) || {}
  const executionLogs = useTaskStore(s => s.executionLogs) || []
  const executionSteps = useTaskStore(s => s.executionSteps) || []
  const workflowState = useTaskStore(s => s.workflowState) || {}
  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps) || []
  const modelCalls = useCognitiveStore(s => s.modelCalls) || []
  const memoryWrites = useCognitiveStore(s => s.memoryWrites) || []
  const events = useEventFeedStore(s => s.events) || []
  const systemStatus = useSystemStore(s => s.systemStatus) || {}

  return useMemo(() => {
    // ── Queue depth: prefer opsSummary.queued_tasks; fallback to executionLogs filtered ──
    const queuedFromOps = Number(opsSummary.queued_tasks) || 0
    const activeFromOps = Number(opsSummary.active_tasks) || 0
    const queueDepth = queuedFromOps + activeFromOps || executionLogs.filter(
      l => l && (l.status === 'queued' || l.status === 'pending' || l.status === 'running')
    ).length

    const aperture = deriveAperture(queueDepth)

    // ── Tokens-per-second rate: derive from recent model calls window (last 10s) ──
    const now = Date.now()
    const recentCalls = modelCalls.filter(c => {
      const t = c?.ts || c?.timestamp || 0
      return t && now - t < 10_000
    })
    const recentTokens = recentCalls.reduce((sum, c) => {
      return sum + (Number(c?.tokens) || Number(c?.total_tokens) || Number(c?.output_tokens) || 0)
    }, 0)
    const windowSec = 10
    const tokensRate = recentTokens / windowSec // tokens per second
    const gearSpeed = deriveGearSpeed(tokensRate)

    // ── Hex codes: 8 entries, first 4 from latest trace ids, last 4 from active agents ──
    const traceSeen = new Set()
    const traceHexes = []
    for (const evt of events) {
      const tid = extractTraceId(evt)
      if (!tid) continue
      const key = String(tid)
      if (traceSeen.has(key)) continue
      traceSeen.add(key)
      traceHexes.push(toHex4(tid))
      if (traceHexes.length >= 4) break
    }
    // Fallback: generate from event timestamps if not enough trace ids
    while (traceHexes.length < 4) {
      const evt = events[traceHexes.length]
      traceHexes.push(hash4(evt?.ts || evt?.id || `t-${traceHexes.length}-${now}`))
    }

    const activeAgents = agents.filter(a => a.status && a.status !== 'idle' && a.status !== 'unknown')
    const agentSource = activeAgents.length > 0 ? activeAgents : agents
    const agentHexes = []
    for (let i = 0; i < 4; i++) {
      const a = agentSource[i]
      agentHexes.push(hash4(a?.id || a?.name || `a-${i}`))
    }

    const hexCodes = [...traceHexes, ...agentHexes]

    // ── Ticker text ──
    const latestStep = reasoningSteps[reasoningSteps.length - 1]
    const stepText = latestStep?.step || latestStep?.description || latestStep?.title || latestStep?.label
      || executionSteps[executionSteps.length - 1]?.label
      || executionSteps[executionSteps.length - 1]?.name
      || 'standby'
    const latestModel = modelCalls[modelCalls.length - 1]
    const modelName = latestModel?.model || latestModel?.model_name
      || systemStatus.thinking_mode
      || 'idle'
    const tps = tokensRate >= 1 ? Math.round(tokensRate) : tokensRate.toFixed(1)
    const tickerText = `REASONING: ${stepText} · MODEL: ${modelName} · TPS: ${tps} · QUEUE: ${queueDepth}`

    // ── Critical event in last 5s? ──
    const criticalEvent = events.some(e => {
      if (!e || !e.ts) return false
      if (now - e.ts > 5_000) return false
      return e.priority === 'CRITICAL'
    })

    return {
      aperture,
      gearSpeed,
      hexCodes,
      tickerText,
      criticalEvent,
      queueDepth,
      // ── Extras callers may find useful (non-breaking additions) ──
      tokensRate,
      memoryWriteCount: memoryWrites.length,
      activeAgentCount: activeAgents.length,
      activeRun: workflowState.active_run || null,
    }
  }, [
    agents,
    opsSummary,
    executionLogs,
    executionSteps,
    workflowState,
    reasoningSteps,
    modelCalls,
    memoryWrites,
    events,
    systemStatus,
  ])
}

export default useAvatarData
