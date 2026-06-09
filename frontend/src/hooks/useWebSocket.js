import { useEffect } from 'react'
import { useAppStore } from '../store/appStore'
import { useBrainStore } from '../store/brainStore'
import { useSystemStore } from '../store/systemStore'
import { useCognitiveStore } from '../store/cognitiveStore'
import { useAgentStore } from '../store/agentStore'
import { useTaskStore } from '../store/taskStore'
import { useEconomyStore } from '../store/economyStore'
import { useSecurityStore } from '../store/securityStore'
import { useEventFeedStore } from '../store/eventFeedStore'
import { useLearningStore } from '../store/learningStore'
import { WS_URL as API_WS_URL } from '../config/api'

const WS_URL = API_WS_URL

// Module-level singleton — one connection for the app lifetime
let _wsInstance = null
let _reconnectTimer = null
let _initialized = false
let _typingTimeout = null
let _reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30000 // 30s cap

// Pre-store message queue — events received before store is bootstrapped are queued
let _preStoreQueue = []
let _storeBootstrapped = false

// nb:* event throttle — batch high-frequency neural brain events into 100ms windows
let _nbBatch = []
let _nbFlushTimer = null

// Snapshot-style telemetry throttle — coalesce high-frequency full-snapshot streams
// to ~4Hz (one store write per 250ms). Last-wins: only the latest payload in the
// window is written, since each message is a complete snapshot. DOM CustomEvents
// (ws:event / ws:any) still fire immediately in dispatchWsMessage for visualisers —
// only the store write is throttled here.
const TELEMETRY_THROTTLE_MS = 250
const _telemetryLatest = {}   // event name → latest data payload
const _telemetryTimers = {}   // event name → pending flush timer

function scheduleTelemetryFlush(event, data, apply) {
  _telemetryLatest[event] = data
  if (_telemetryTimers[event]) return
  _telemetryTimers[event] = setTimeout(() => {
    _telemetryTimers[event] = null
    const latest = _telemetryLatest[event]
    delete _telemetryLatest[event]
    apply(latest)
  }, TELEMETRY_THROTTLE_MS)
}

function clearTelemetryTimers() {
  for (const k in _telemetryTimers) {
    clearTimeout(_telemetryTimers[k])
    _telemetryTimers[k] = null
  }
}

export function bootstrapWsStore() {
  if (_storeBootstrapped) return
  _storeBootstrapped = true
  const queued = _preStoreQueue.splice(0)
  queued.forEach(msg => dispatchWsMessage(msg))
}

function scheduleNbFlush() {
  if (_nbFlushTimer) return
  _nbFlushTimer = setTimeout(() => {
    _nbFlushTimer = null
    const batch = _nbBatch.splice(0, 20)
    batch.forEach(msg => dispatchWsMessage(msg))
  }, 100)
}

// HMR cleanup — prevent ghost connections on Vite hot-reload
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    _wsInstance?.close(1000)
    _wsInstance = null
    _initialized = false
    _storeBootstrapped = false
    _preStoreQueue = []
    clearTimeout(_reconnectTimer)
    clearTimeout(_nbFlushTimer)
    clearTelemetryTimers()
  })
}

function getStore() { return getTaskStore() }
function getSysStore() { return useSystemStore.getState() }
function getCogStore() { return useCognitiveStore.getState() }
function getAgentStore() { return useAgentStore.getState() }
function getTaskStore() { return useTaskStore.getState() }
function getEconStore() { return useEconomyStore.getState() }
function getSecStore() { return useSecurityStore.getState() }
function getEvtStore() { return useEventFeedStore.getState() }

const HEALTH_MAP = { healthy: 90, degraded: 55, warning: 55, warn: 55, error: 20, critical: 10, idle: 40, unknown: 50 }
function normalizeAgents(agents) {
  return agents.map(a => ({
    ...a,
    status: a.status || a.state || 'idle',
    health: typeof a.health === 'number' ? a.health : (HEALTH_MAP[a.health] ?? 50),
    task: a.task || a.currentTask || null,
  }))
}

function reconnectDelay() {
  // Exponential backoff: 1s, 2s, 4s, 8s … capped at 30s
  return Math.min(1000 * Math.pow(2, _reconnectAttempts), MAX_RECONNECT_DELAY)
}

function buildWsUrl() {
  const url = new URL(WS_URL, window.location.origin)
  const token = sessionStorage.getItem('ai_jwt')
  if (token) url.searchParams.set('token', token)
  return url.toString()
}

function connectSingleton() {
  if (_wsInstance?.readyState === WebSocket.OPEN || _wsInstance?.readyState === WebSocket.CONNECTING) return

  const token = sessionStorage.getItem('ai_jwt')
  if (!token) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = setTimeout(connectSingleton, 500)
    return
  }

  const ws = new WebSocket(buildWsUrl())
  _wsInstance = ws

  ws.onopen = () => {
    _reconnectAttempts = 0
    const sys = getSysStore()
    sys.setWsConnected(true)
    sys.setWs(ws)
    // node_ok = true on WS open; python_ok / llm_ok stay as-is until system:ready arrives
    sys.setBackendStatus?.({ node_ok: true, ws_connected: true })
    sys.addHeartbeatLog({ text: '[SYSTEM] WebSocket connected', level: 'success', ts: Date.now() })
  }

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      // Track last WS event timestamp for LIVE badge
      window.__lastWsEvent = Date.now()
      if (!_storeBootstrapped) {
        _preStoreQueue.push(msg)
        return
      }
      // Throttle high-frequency nb:* events through batch queue
      if (typeof msg.event === 'string' && msg.event.startsWith('nb:')) {
        _nbBatch.push(msg)
        scheduleNbFlush()
        return
      }
      dispatchWsMessage(msg)
    } catch (e) {
      console.error('[ws] message handling failed', e)
    }
  }

  ws.onclose = (evt) => {
    const sys = getSysStore()
    const task = getTaskStore()
    sys.setWsConnected(false)
    sys.setWs(null)
    // ws_connected → false; keep python_ok / llm_ok at last known (STALE not OFFLINE on brief reconnect)
    sys.setBackendStatus?.({ ws_connected: false })
    clearTimeout(_typingTimeout)
    clearTelemetryTimers()
    task.setTyping(false)
    _wsInstance = null
    _initialized = false

    if (evt.code === 1000) {
      sys.addHeartbeatLog({ text: `[SYSTEM] WebSocket closed (${evt.code})`, level: 'info', ts: Date.now() })
      return
    }
    if (evt.code === 4401) {
      // Token expired — try to refresh silently before reconnecting
      import('../api/client').then(({ default: api }) => {
        api.refreshToken?.().then(newToken => {
          if (newToken) {
            sessionStorage.setItem('ai_jwt', newToken)
            localStorage.setItem('ai_jwt', newToken)
            _reconnectAttempts = 0
            clearTimeout(_reconnectTimer)
            _reconnectTimer = setTimeout(connectSingleton, 500)
          } else {
            // Refresh failed — clear token, user needs to log in again
            sessionStorage.removeItem('ai_jwt')
            localStorage.removeItem('ai_jwt')
            sys.addHeartbeatLog({ text: '[SYSTEM] Sessie verlopen — log opnieuw in', level: 'error', ts: Date.now() })
          }
        }).catch(() => {
          sessionStorage.removeItem('ai_jwt')
          localStorage.removeItem('ai_jwt')
        })
        return
      }).catch(() => {
        sessionStorage.removeItem('ai_jwt')
      })
      return
    }

    _reconnectAttempts += 1
    const delay = reconnectDelay()
    sys.addHeartbeatLog({
      text: `[SYSTEM] Connection lost — reconnecting in ${Math.round(delay / 1000)}s (attempt ${_reconnectAttempts})`,
      level: 'warning',
      ts: Date.now(),
    })
    _reconnectTimer = setTimeout(connectSingleton, delay)
  }

  ws.onerror = () => { ws.close() }
}

function dispatchWsMessage({ event, data }) {
    try {
      // Fire generic DOM event for useLiveData and other direct subscribers
      window.dispatchEvent(new CustomEvent('ws:event', { detail: { type: event, data } }))
      // Generic fan-out for reactor/connection visualisers — type at root for cheap predicate checks
      window.dispatchEvent(new CustomEvent('ws:any', { detail: { type: event, data } }))

      // Route events to appropriate domain stores by prefix
      if (event.startsWith('system:')) {
        return dispatchSystemEvent(event, data)
      }
      if (event.startsWith('turn:') || event === 'proof:ready' || event === 'artifact:created' || event.startsWith('action:') || event.startsWith('approval:')) {
        return dispatchTurnEvent(event, data)
      }
      if (event.startsWith('cognitive:') || event.startsWith('brain:') || event.startsWith('nb:')) {
        return dispatchCognitiveEvent(event, data)
      }
      if (event.startsWith('agent:')) {
        return dispatchAgentEvent(event, data)
      }
      if (event.startsWith('task:') || event.startsWith('execution:') || event.startsWith('workflow:') || event === 'orchestrator:message' || event === 'orchestrator:queued' || event.startsWith('chat:')) {
        return dispatchTaskEvent(event, data)
      }
      if (event.startsWith('economy:') || event.startsWith('objective:') || event.startsWith('money:')) {
        return dispatchEconomyEvent(event, data)
      }
      if (event.startsWith('security:') || event.startsWith('blacklight:') || event.startsWith('auth:')) {
        return dispatchSecurityEvent(event, data)
      }
      if (event.startsWith('learning:') || event === 'topic:skill_updated') {
        return dispatchLearningEvent(event, data)
      }
      if (event.startsWith('memory:') && (event === 'memory:added' || event === 'memory:pending_review')) {
        return dispatchMemoryEvent(event, data)
      }

      // Fallback: catch-all events go to event feed
      dispatchDefaultEvent(event, data)
    } catch (e) {
      console.error('[ws] dispatch failed', e)
    }
}

// ── Domain-Specific Event Dispatchers ──────────────────────────

function dispatchTurnEvent(event, data = {}) {
  const task = getTaskStore()
  const sys = getSysStore()
  const turnId = data.turn_id || data.turnId
  if (!turnId && event !== 'artifact:created') return

  if (event === 'turn:started') {
    task.upsertTurnMessage?.({
      ...data,
      status: data.status || 'running',
      assistant_reply: 'I am working on this now...',
      actions: [],
      proof: [],
      artifacts: [],
      ts: data.ts || Date.now(),
    })
    task.setTyping(true)
    sys.addHeartbeatLog({
      text: `[TURN] Started ${turnId}`,
      level: 'info',
      ts: Date.now(),
    })
    return
  }

  if (event === 'turn:thinking') {
    task.upsertTurnMessage?.({
      ...data,
      status: 'running',
      assistant_reply: data.message || 'Thinking...',
      ts: Date.now(),
    })
    return
  }

  if (event.startsWith('action:')) {
    const action = {
      id: data.id || `${event}-${Date.now()}`,
      action: data.action || event,
      label: data.label || data.action || event,
      status: event.endsWith('failed') ? 'failed' : event.endsWith('completed') ? 'completed' : 'running',
      error: data.error || null,
    }
    const existing = (task.chatMessages || []).find(m => m.turn_id === turnId)
    const actions = [...(existing?.actions || []).filter(a => a.action !== action.action), action]
    task.upsertTurnMessage?.({
      ...data,
      status: 'running',
      assistant_reply: existing?.content || `Working: ${action.label}`,
      actions,
      proof: existing?.proof || [],
      artifacts: existing?.artifacts || [],
      ts: Date.now(),
    })
    return
  }

  if (event === 'approval:required') {
    const existing = (task.chatMessages || []).find(m => m.turn_id === turnId)
    task.upsertTurnMessage?.({
      ...data,
      status: 'waiting_approval',
      assistant_reply: data.message || 'This needs approval before I continue.',
      actions: existing?.actions || [],
      proof: existing?.proof || [],
      artifacts: existing?.artifacts || [],
      approvals: [...(existing?.approvals || []), data],
      ts: Date.now(),
    })
    task.setTyping(false)
    return
  }

  if (event === 'proof:ready' || event === 'turn:completed' || event === 'turn:failed') {
    clearTimeout(_typingTimeout)
    task.setTyping(false)
    task.upsertTurnMessage?.({
      ...data,
      status: event === 'turn:failed' ? 'failed' : data.status || 'completed',
      ts: data.ts || Date.now(),
    })
    return
  }

  if (event === 'artifact:created') {
    const existing = (task.chatMessages || []).find(m => m.turn_id === turnId)
    if (!existing) return
    task.upsertTurnMessage?.({
      ...existing,
      artifacts: [...(existing.artifacts || []), data.artifact].filter(Boolean),
      ts: Date.now(),
    })
  }
}

function dispatchSystemEvent(event, data) {
  const sys = getSysStore()
  const task = getTaskStore()
  switch (event) {
    case 'system:status':
      // High-frequency full snapshot — coalesce store writes to ~4Hz (last-wins).
      scheduleTelemetryFlush('system:status', data, (d) => {
        const s = getSysStore()
        s.setSystemStatus(d)
        // Populate systemHealth so CPU/RAM meters and dashboard panels receive live values.
        // The server broadcasts system:status with cpu/memory fields; system:health is an alias.
        s.setSystemHealth?.({
          cpu_percent: d.cpu ?? d.cpu_usage ?? 0,
          memory_percent: d.memory ?? 0,
          gpu_percent: d.gpu_usage ?? 0,
          uptime: d.uptime ?? 0,
          running_agents: d.running_agents ?? 0,
          total_agents: d.total_agents ?? 0,
          status: 'live',
        })
      })
      break
    case 'system:health':
      // High-frequency CPU/RAM/GPU meter snapshot — coalesce to ~4Hz (last-wins).
      scheduleTelemetryFlush('system:health', data, (d) => getSysStore().setSystemHealth?.(d))
      break
    case 'system:degraded':
      sys.addHeartbeatLog({
        text: `[HEALTH] System degraded — error_rate=${(data.error_rate * 100).toFixed(0)}%, latency=${data.avg_latency_ms?.toFixed(0)}ms`,
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'system:recovered':
      sys.addHeartbeatLog({ text: '[HEALTH] System recovered', level: 'success', ts: Date.now() })
      break
    case 'system:error':
      sys.addHeartbeatLog({
        text: `[SYSTEM] Error: ${data.error?.slice(0, 80) || 'unknown'}`,
        level: 'error',
        ts: Date.now(),
      })
      break
    case 'system:ready':
      sys.setBackendStatus?.({
        python_ok: data?.python_ok !== false,
        llm_ok: data?.llm_ok !== false,
        node_ok: true,
      })
      // Preserve legacy event for App.jsx degraded-mode listener
      window.dispatchEvent(new CustomEvent('ws:system:ready', { detail: data }))
      break
    case 'system:update:complete':
      sys.setUpdateStatus({ updateComplete: true, applying: false })
      break
    case 'system:critical_failure':
      sys.addHeartbeatLog({
        text: `[CRITICAL] system:critical_failure — ${data.reason || data.message || ''}`,
        level: 'error',
        ts: Date.now(),
      })
      sys.triggerCriticalAlert?.()
      break
    case 'heartbeat':
      sys.addHeartbeatLog({ text: data.message, level: data.level || 'info', ts: Date.now() })
      break
  }
}

function dispatchCognitiveEvent(event, data) {
  const cog = getCogStore()
  const brain = useBrainStore.getState()
  const evt = getEvtStore()
  switch (event) {
    case 'nb:reasoning_step':
      cog.appendReasoningStep(data)
      break
    case 'nb:memory_write':
      cog.flashMemoryWrite(data)
      break
    case 'nb:memory_read':
      cog.pulseMemory(data.ids || [])
      break
    case 'nb:graph_update':
      if (data?.nodes && Array.isArray(data.nodes)) {
        data.nodes.forEach((n) => brain.addNode({ ...n, source: 'neural_brain' }))
      }
      if (data?.links && Array.isArray(data.links)) {
        data.links.forEach((l) => brain.addLink(l))
      }
      break
    case 'nb:model_call':
      cog.recordModelCall(data)
      break
    case 'nb:action_call':
      evt.addEvent({
        id: data.id || `action-${Date.now()}`,
        kind: 'agent_action',
        notes: `${data.skill || 'action'} · ${data.status || 'pending'}`,
        ts: Date.now(),
      })
      break
    case 'nb:artifact_created':
      evt.addEvent({
        id: `art-${Date.now()}`,
        kind: 'artifact',
        notes: (data.artifacts || []).map(a => a.name).join(', ') || 'artifact created',
        ts: Date.now(),
      })
      break
    case 'nb:thread_created':
      getSysStore().addHeartbeatLog({
        text: `[BRAIN] Thread started: ${(data.thread_id || '').slice(0, 16)}… — ${data.input_preview || ''}`,
        level: 'info',
        ts: Date.now(),
      })
      break
    case 'brain:insights':
      cog.setBrainInsights(data)
      break
    case 'brain:activity':
      // High-frequency brain activity snapshot — coalesce to ~4Hz (last-wins).
      scheduleTelemetryFlush('brain:activity', data, (d) => getCogStore().setBrainActivity(d))
      break
    case 'brain:graph':
      if (data?.nodes && data?.links) {
        brain.setGraph(data)
      } else if (data?.node) {
        brain.addNode(data.node)
        if (data.link) brain.addLink(data.link)
      }
      break
    case 'cognition:pipeline':
      try { useCognitiveStore.getState().setPipelinePhases(data.phases) } catch {}
      break
  }
}

function dispatchAgentEvent(event, data) {
  const agent = getAgentStore()
  const econ = getEconStore()
  switch (event) {
    case 'agent:update':
      if (data.agents) agent.setAgents(normalizeAgents(data.agents))
      break
  }
}

function dispatchTaskEvent(event, data) {
  const task = getTaskStore()
  const sys = getSysStore()
  // Fan-out research-flow events to the ResearchPage 2-phase listener
  if (event.startsWith('task:research_')) {
    window.dispatchEvent(new CustomEvent('ws:research', { detail: { type: event, ...(data || {}) } }))
  }
  switch (event) {
    // Both event names route to the same assistant-reply handler:
    //   - `orchestrator:message` — emitted by the Node orchestrator path
    //   - `chat:message`         — emitted directly by the Python-proxy path
    // Only ONE assistant message is appended per reply; backends are expected to emit
    // exactly one of these per chat turn.
    case 'orchestrator:message':
    case 'chat:message':
      if (data.turn_id || data.turnId) {
        clearTimeout(_typingTimeout)
        task.setTyping(false)
        task.clearExecutionSteps()
        task.upsertTurnMessage?.({
          ...data,
          turn_id: data.turn_id || data.turnId,
          task_id: data.task_id || data.taskId,
          status: data.status || 'completed',
          assistant_reply: data.assistant_reply || data.message || data.reply || data.text || '',
          artifacts: data.artifacts || data.attachments || [],
          ts: data.ts || Date.now(),
        })
        break
      }
      clearTimeout(_typingTimeout)
      task.setTyping(false)
      task.clearExecutionSteps()
      task.addChatMessage({
        role: 'ai',
        content: data.message || data.reply || data.text || '',
        attachments: data.attachments || [],
        debugInfo: data.debugInfo || null,
        ts: data.ts || Date.now(),
        subsystem: data.subsystem,
      })
      break
    case 'orchestrator:queued':
      sys.addHeartbeatLog({
        text: `[ORCHESTRATOR] Queued ${data.taskId} on ${data.agentId}`,
        level: 'info',
        ts: Date.now(),
      })
      break
    case 'execution:log':
      task.addExecutionLog(data)
      break
    case 'execution:step':
      task.addExecutionStep(data)
      break
    case 'execution:snapshot':
      if (Array.isArray(data)) task.setExecutionSnapshot(data)
      break
    case 'task_progress':
      task.upsertTaskProgress({
        taskId: data.taskId,
        title: data.title,
        steps: data.steps || [],
        graph: data.graph || [],
        ts: data.ts || Date.now(),
      })
      break
    case 'task:context_check':
      // Show the YES/NO modal so the user can choose to research first.
      useCognitiveStore.getState().setContextCheck({
        taskId: data.task_id || data.taskId,
        goal: data.goal || '',
        score: Number(data.score || 0),
        gaps: Array.isArray(data.gaps) ? data.gaps : [],
        memory_hits: Number(data.memory_hits || 0),
        graph_hits: Number(data.graph_hits || 0),
      })
      break
    case 'task:research_started':
      useCognitiveStore.getState().setResearchSession({
        taskId: data.task_id || data.taskId,
        goal: data.goal || '',
        hop: Number(data.hop || 0),
        gaps: Array.isArray(data.gaps) ? data.gaps : [],
        status: 'running',
        sources: [],
      })
      break
    case 'task:research_completed': {
      const cog = useCognitiveStore.getState()
      const sess = {
        taskId: data.task_id || data.taskId,
        goal: data.goal || '',
        hop: Number(data.hop || 0),
        gaps: cog.researchSession?.gaps || [],
        findings_count: Number(data.findings_count || 0),
        sources: Array.isArray(data.sources) ? data.sources : [],
        status: 'done',
      }
      cog.setResearchSession(sess)
      cog.appendResearchSession(sess)
      // Drop the active session a few seconds after completion so the UI relaxes.
      setTimeout(() => {
        const cur = useCognitiveStore.getState().researchSession
        if (cur && cur.taskId === sess.taskId) useCognitiveStore.getState().clearResearchSession()
      }, 4000)
      break
    }
    case 'task:research_budget_exhausted':
      useCognitiveStore.getState().setResearchSession({
        taskId: data.task_id || data.taskId,
        goal: data.goal || '',
        status: 'budget_exhausted',
      })
      break
    case 'workflow:snapshot':
      task.setWorkflowSnapshot(data)
      break
    case 'workflow:update':
      task.upsertWorkflowRun(data)
      break
  }
}

function dispatchEconomyEvent(event, data) {
  const econ = getEconStore()
  const sys = getSysStore()
  switch (event) {
    case 'activity:item':
      econ.addActivityItem(data)
      break
    case 'activity:snapshot':
      if (Array.isArray(data)) econ.setActivitySnapshot(data)
      break
    case 'objective:update':
      if (data?.system === 'money_mode') {
        const shared = {
          active: data.active,
          status: data.status,
          current_objective: data.current_objective,
          active_tasks: data.active_tasks || [],
          progress: data.progress || 0,
          agents_used: data.agents_used || [],
          performance: data.performance || {},
          result: data.result || null,
          updated_at: data.current_objective?.updated_at || data.current_objective?.created_at || new Date().toISOString(),
        }
        econ.setPipeline('content_publish_track', shared)
        econ.setPipeline('data_scrape_filter_store', shared)
        econ.setPipeline('outreach_response_conversion', shared)
      } else if (data?.system) {
        econ.setPipeline(data.system, data)
      }
      break
    case 'money_mode_panel':
      econ.setPipeline('content_publish_track', data)
      break
  }
}

function dispatchSecurityEvent(event, data) {
  const sec = getSecStore()
  const sys = getSysStore()
  switch (event) {
    case 'security:update':
    case 'blacklight:status':
      sec.setSecurityStatus({
        threat_score: data.threat_score ?? 0,
        mode: data.mode ?? 'NORMAL',
        active_threats: data.active_threats ?? [],
        agents_paused: data.agents_paused ?? false,
        forge_disabled: data.forge_disabled ?? false,
        sentinel_state: data.sentinel_state ?? undefined,
        sentinel_last_verdict: data.sentinel_last_verdict ?? undefined,
        updated_at: Date.now(),
      })
      break
    case 'blacklight:ai_alert':
      sys.addHeartbeatLog({
        text: `[SENTINEL] AI detected risk ${data.risk} (${data.category || '?'}) — ${data.reason || ''}`,
        level: (data.risk ?? 0) >= 70 ? 'error' : 'warning',
        ts: Date.now(),
      })
      if ((data.risk ?? 0) >= 70) sys.triggerCriticalAlert?.()
      break
    case 'blacklight:ai_defense':
    case 'blacklight:guard_block': {
      const acts = (data.actions || []).map(a => (typeof a === 'string' ? a : `${a.action}→${a.target}`)).join(', ')
      sys.addHeartbeatLog({
        text: `[GUARD] 🛡 Blocked threat: ${acts} (${data.event_type || data.category || 'attack'})`,
        level: 'error',
        ts: Date.now(),
      })
      sys.triggerCriticalAlert?.()
      break
    }
    case 'security:notification':
      sys.addHeartbeatLog({
        text: `[GUARD] ${data.title || 'Security action'} — ${data.detail || ''}`,
        level: data.level === 'critical' ? 'error' : data.level === 'warning' ? 'warning' : 'info',
        ts: Date.now(),
      })
      sec.pushNotification?.({ title: data.title, detail: data.detail, level: data.level, ts: Date.now() })
      break
    case 'blacklight:mode_change':
      sec.setSecurityStatus({
        mode: data.mode,
        previous_mode: data.previous,
        threat_score: data.threat_score ?? 0,
        updated_at: Date.now(),
      })
      sys.addHeartbeatLog({
        text: `[BLACKLIGHT] Mode: ${data.previous} → ${data.mode} (score=${data.threat_score ?? '?'})`,
        level: data.mode === 'NORMAL' ? 'success' : data.mode === 'ALERT' ? 'warning' : 'error',
        ts: Date.now(),
      })
      break
    case 'blacklight:lockdown':
      sec.setSecurityStatus({ mode: 'LOCKDOWN', threat_score: 100, updated_at: Date.now() })
      sys.addHeartbeatLog({
        text: `[BLACKLIGHT] ⚠ LOCKDOWN: ${data.reason || 'threat detected'}`,
        level: 'error',
        ts: Date.now(),
      })
      sys.triggerCriticalAlert?.()
      break
    case 'security:breach':
    case 'system:critical_failure':
      sys.addHeartbeatLog({
        text: `[CRITICAL] ${event}: ${data.reason || data.message || 'critical event'}`,
        level: 'error',
        ts: Date.now(),
      })
      sys.triggerCriticalAlert?.()
      break
    case 'blacklight:input_analyzed':
      if ((data.risk_score ?? 0) >= 30) {
        sys.addHeartbeatLog({
          text: `[BLACKLIGHT] Risk ${data.risk_score} (${data.threat_level}) — user=${data.user_id}`,
          level: data.risk_score >= 60 ? 'error' : 'warning',
          ts: Date.now(),
        })
      }
      break
    case 'auth:login_success':
      sys.addHeartbeatLog({
        text: `[AUTH] Login: ${data.user_id?.slice(0, 8)} role=${data.role} ip=${data.ip}`,
        level: 'success',
        ts: Date.now(),
      })
      break
    case 'auth:login_failed':
      sys.addHeartbeatLog({
        text: `[AUTH] Failed login: ${data.username} from ${data.ip}`,
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'auth:brute_force_detected':
      sys.addHeartbeatLog({
        text: `[AUTH] ⚠ BRUTE FORCE: ${data.attempts} attempts from ${data.ip}`,
        level: 'error',
        ts: Date.now(),
      })
      sec.setSecurityStatus({
        threat_score: Math.min(100, (getSecStore()?.securityStatus?.threat_score || 0) + 40),
      })
      break
    case 'auth:account_locked':
      sys.addHeartbeatLog({
        text: `[AUTH] Account locked: ${data.username} (too many failures from ${data.ip})`,
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'auth:user_blocked':
      sys.addHeartbeatLog({
        text: `[AUTH] User blocked: ${data.user_id} — ${data.reason}`,
        level: 'error',
        ts: Date.now(),
      })
      break
    case 'security:key_rotated':
      sys.addHeartbeatLog({
        text: `[SECURITY] Keys rotated → version ${data.version}`,
        level: 'info',
        ts: Date.now(),
      })
      break
    case 'security:rate_limited':
      sys.addHeartbeatLog({
        text: `[SECURITY] Rate limit: ${data.kind} from ${data.ip} on ${data.path}`,
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'security:access_denied':
      sys.addHeartbeatLog({
        text: `[SECURITY] Access denied: ${data.user_id} → ${data.path} (needs ${data.required_role})`,
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'blacklight:brute_force_response':
      sys.addHeartbeatLog({
        text: `[BLACKLIGHT] Brute force response: keys rotated, IP=${data.ip}`,
        level: 'error',
        ts: Date.now(),
      })
      break
    case 'autonomy:status':
      sec.setAutonomyStatus(data)
      break
  }
}

function dispatchLearningEvent(event, data) {
  const store = useLearningStore.getState()
  const payload = data || {}
  switch (event) {
    case 'learning:started':
      store.startSession(payload.session_id, payload.topic, payload.depth)
      window.dispatchEvent(new CustomEvent('ws:learning', { detail: { type: event, ...payload } }))
      break
    case 'learning:progress':
      store.appendSessionLog(payload.session_id, { ts: Date.now(), ...payload })
      window.dispatchEvent(new CustomEvent('ws:learning', { detail: { type: event, ...payload } }))
      break
    case 'learning:completed':
      store.completeSession(payload.session_id, payload.result || payload)
      window.dispatchEvent(new CustomEvent('ws:learning', { detail: { type: event, ...payload } }))
      break
    case 'learning:failed':
      store.failSession(payload.session_id, payload.error || 'unknown')
      window.dispatchEvent(new CustomEvent('ws:learning', { detail: { type: event, ...payload } }))
      break
    case 'topic:skill_updated':
      window.dispatchEvent(new CustomEvent('ws:topic-update', { detail: payload }))
      break
  }
}

function dispatchMemoryEvent(event, data) {
  const store = useLearningStore.getState()
  const payload = data || {}
  switch (event) {
    case 'memory:added':
      store.addRecentMemory({ ...payload, ts: payload.ts || Date.now() })
      window.dispatchEvent(new CustomEvent('ws:memory-added', { detail: payload }))
      break
    case 'memory:pending_review':
      store.bumpPendingReviewCount()
      window.dispatchEvent(new CustomEvent('ws:memory-pending-review', { detail: payload }))
      break
  }
}

function dispatchDefaultEvent(event, data) {
  const evt = getEvtStore()
  const sys = getSysStore()
  const task = getTaskStore()

  // Special handling for a few legacy events
  switch (event) {
    case 'memory:update':
      evt.addEvent({
        kind: 'memory_update',
        notes: `Memory updated: ${data.total_entities || 0} entities`,
        data,
        ts: Date.now(),
      })
      break
    case 'doctor:check':
      evt.addEvent({
        kind: 'health_check',
        notes: `Doctor check: ${data.grade || 'unknown'}`,
        data,
        ts: Date.now(),
      })
      break
    case 'nn:status':
      evt.addEvent({
        kind: 'nn_status',
        notes: `NN status: ${data.mode || 'unknown'}`,
        data,
        ts: Date.now(),
      })
      break
    case 'event_stream':
      evt.addEvent({
        id: data.id || `evt-${Date.now()}`,
        kind: data.event_type || 'event',
        notes: `${data.event_type || 'event'}${data.payload?.task_id ? ` · ${data.payload.task_id}` : ''}`,
        ts: data.ts || Date.now(),
      })
      break
    case 'observability:snapshot':
      // Merge into system store for backward compatibility
      evt.addEvent({
        kind: 'observability',
        notes: `System metrics updated`,
        data,
        ts: Date.now(),
      })
      break
    case 'prompt:trace':
      if (data && data.id) {
        evt.addEvent({
          kind: 'prompt_trace',
          notes: `Prompt trace: ${data.model || 'unknown'}`,
          data,
          ts: Date.now(),
        })
      }
      break
    case 'chat:input_rejected':
      clearTimeout(_typingTimeout)
      task.setTyping(false)
      sys.addHeartbeatLog({
        text: '[WS] Chat message rejected — use text input',
        level: 'warning',
        ts: Date.now(),
      })
      break
    case 'identity:ready':
      // Legacy auth event
      break
    case 'forge:queue_update':
      evt.addEvent({
        kind: 'forge_update',
        notes: `Forge queue update: ${data.item?.id || 'unknown'}`,
        data: data.item,
        ts: Date.now(),
      })
      break
    default:
      // Catch all unknown events
      evt.addEvent({
        kind: event || 'unknown',
        notes: event || 'unknown event',
        data,
        ts: Date.now(),
      })
  }
}

export function useWebSocket() {
  useEffect(() => {
    if (!_initialized) {
      _initialized = true
      connectSingleton()
    }
    const onAuthReady = () => connectSingleton()
    window.addEventListener('nx:auth-ready', onAuthReady)
    return () => {
      clearTimeout(_reconnectTimer)
      window.removeEventListener('nx:auth-ready', onAuthReady)
    }
  }, [])

  const sendMessage = (message) => {
    sendChatMessage(message)
  }

  return { sendMessage }
}

export function sendChatMessage(message) {
  if (_wsInstance?.readyState === WebSocket.OPEN) {
    _wsInstance.send(JSON.stringify({ type: 'chat', message }))
    getStore().setTyping(true)
    clearTimeout(_typingTimeout)
    _typingTimeout = setTimeout(() => getStore().setTyping(false), 30000)
    return
  }
  getStore().setTyping(true)
  clearTimeout(_typingTimeout)
  _typingTimeout = setTimeout(() => getStore().setTyping(false), 90000)

  const token = sessionStorage.getItem('ai_jwt')
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  // Streaming SSE fetch — tokens appear as they generate
  fetch('/chat/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({ message }),
  })
    .then(async r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let msgAdded = false

      const flush = (text) => {
        if (!text) return
        if (!msgAdded) {
          getStore().setTyping(false)
          clearTimeout(_typingTimeout)
          getStore().addChatMessage?.({ role: 'ai', content: text, ts: Date.now() })
          msgAdded = true
        } else {
          getStore().updateLastAiMessage?.(text)
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.chunk) {
              accumulated += evt.chunk
              flush(accumulated)
            } else if (evt.done) {
              break
            } else if (evt.error) {
              throw new Error(evt.error)
            }
          } catch (_) {}
        }
      }

      if (!msgAdded) {
        getStore().setTyping(false)
        clearTimeout(_typingTimeout)
        getStore().addChatMessage?.({ role: 'ai', content: accumulated || 'No response returned.', ts: Date.now() })
      }
    })
    .catch(err => {
      clearTimeout(_typingTimeout)
      getStore().setTyping(false)
      getStore().addChatMessage?.({ role: 'ai', content: `Request failed: ${err.message}`, degraded: true, ts: Date.now() })
    })
}
