import { useEffect } from 'react'
import { useAppStore } from '../store/appStore'
import { useBrainStore } from '../store/brainStore'
import { WS_URL as API_WS_URL } from '../config/api'

const WS_URL = API_WS_URL

// Module-level singleton — one connection for the app lifetime
let _wsInstance = null
let _reconnectTimer = null
let _initialized = false
let _typingTimeout = null
let _reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30000 // 30s cap

function getStore() { return useAppStore.getState() }

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

function connectSingleton() {
  if (_wsInstance?.readyState === WebSocket.OPEN || _wsInstance?.readyState === WebSocket.CONNECTING) return

  const ws = new WebSocket(WS_URL)
  _wsInstance = ws

  ws.onopen = () => {
    _reconnectAttempts = 0
    const store = getStore()
    store.setWsConnected(true)
    store.setWs(ws)
    store.addHeartbeatLog({ text: '[SYSTEM] WebSocket connected', level: 'success', ts: Date.now() })
  }

  ws.onmessage = (evt) => {
    try {
      const { event, data } = JSON.parse(evt.data)
      const store = getStore()
      switch (event) {
        case 'heartbeat':
          store.addHeartbeatLog({ text: data.message, level: data.level || 'info', ts: Date.now() })
          break
        case 'agent:update':
          if (data.agents) store.setAgents(normalizeAgents(data.agents))
          break
        case 'system:status':
          store.setSystemStatus(data)
          if (data?.money_mode_panel) store.setObjectivePanel('money_mode', data.money_mode_panel)
          if (data?.ascend_forge_panel) store.setObjectivePanel('ascend_forge', data.ascend_forge_panel)
          break
        case 'orchestrator:message':
          clearTimeout(_typingTimeout)
          store.setTyping(false)
          store.clearExecutionSteps()
          store.addChatMessage({
            role: 'ai',
            content: data.message || data.reply || '',
            attachments: data.attachments || [],
            debugInfo: data.debugInfo || null,
            ts: Date.now(),
            subsystem: data.subsystem,
          })
          break
        case 'orchestrator:queued':
          store.addHeartbeatLog({
            text: `[ORCHESTRATOR] Queued ${data.taskId} on ${data.agentId}`,
            level: 'info',
            ts: Date.now(),
          })
          break
        case 'activity:item':
          store.addActivityItem(data)
          break
        case 'activity:snapshot':
          if (Array.isArray(data)) store.setActivitySnapshot(data)
          break
        case 'execution:log':
          store.addExecutionLog(data)
          break
        case 'execution:step':
          store.addExecutionStep(data)
          break
        case 'execution:snapshot':
          if (Array.isArray(data)) store.setExecutionSnapshot(data)
          break
        case 'nn:status':
          store.setNnStatus(data)
          break
        case 'memory:update':
          store.setMemoryTree(data)
          break
        case 'doctor:check':
          store.setDoctorStatus(data)
          break
        case 'brain:insights':
          store.setBrainInsights(data)
          break
        case 'brain:activity':
          store.setBrainActivity(data)
          break
        case 'brain:graph': {
          const brainState = useBrainStore.getState()
          if (data?.nodes && data?.links) {
            brainState.setGraph(data)
          } else if (data?.node) {
            brainState.addNode(data.node)
            if (data.link) brainState.addLink(data.link)
          }
          break
        }
        case 'autonomy:status':
          store.setAutonomyStatus(data)
          break
        case 'workflow:snapshot':
          store.setWorkflowSnapshot(data)
          break
        case 'workflow:update':
          store.upsertWorkflowRun(data)
          break
        case 'objective:update':
          if (data?.system) store.setObjectivePanel(data.system, data)
          break
        case 'event_stream':
          store.addActivityItem({
            id: data.id || `evt-${Date.now()}`,
            kind: data.event_type || 'event',
            notes: `${data.event_type || 'event'}${data.payload?.task_id ? ` · ${data.payload.task_id}` : ''}`,
            ts: data.ts || Date.now(),
          })
          break
        case 'observability:snapshot':
          store.setObservability(data)
          break
        case 'prompt:trace':
          if (data && data.id) store.addPromptTrace(data)
          break
        case 'chat:input_rejected':
          clearTimeout(_typingTimeout)
          store.setTyping(false)
          // Surface rejection so user knows the message was not processed
          store.addHeartbeatLog({ text: '[WS] Chat message rejected — use text input', level: 'warning', ts: Date.now() })
          break
        case 'identity:ready':
          store.setIdentity(data)
          break
        case 'task_progress':
          store.upsertTaskProgress({
            taskId: data.taskId,
            title: data.title,
            steps: data.steps || [],
            graph: data.graph || [],
            ts: data.ts || Date.now(),
          })
          break
      }
    } catch (e) {
      console.error('[ws] message handling failed', e)
    }
  }

  ws.onclose = (evt) => {
    const store = getStore()
    store.setWsConnected(false)
    store.setWs(null)
    clearTimeout(_typingTimeout)
    store.setTyping(false)
    _wsInstance = null

    // Don't reconnect on intentional close (code 1000) or auth failure (4401)
    if (evt.code === 1000 || evt.code === 4401) {
      store.addHeartbeatLog({ text: `[SYSTEM] WebSocket closed (${evt.code})`, level: 'info', ts: Date.now() })
      return
    }

    _reconnectAttempts += 1
    const delay = reconnectDelay()
    store.addHeartbeatLog({
      text: `[SYSTEM] Connection lost — reconnecting in ${Math.round(delay / 1000)}s (attempt ${_reconnectAttempts})`,
      level: 'warning',
      ts: Date.now(),
    })
    _reconnectTimer = setTimeout(connectSingleton, delay)
  }

  ws.onerror = () => { ws.close() }
}

export function useWebSocket() {
  useEffect(() => {
    if (!_initialized) {
      _initialized = true
      connectSingleton()
    }
    return () => {
      clearTimeout(_reconnectTimer)
    }
  }, [])

  const sendMessage = (message) => {
    if (_wsInstance?.readyState === WebSocket.OPEN) {
      _wsInstance.send(JSON.stringify({ type: 'chat', message }))
      getStore().setTyping(true)
      clearTimeout(_typingTimeout)
      _typingTimeout = setTimeout(() => getStore().setTyping(false), 30000)
    }
  }

  return { sendMessage }
}

export function sendChatMessage(message) {
  if (_wsInstance?.readyState === WebSocket.OPEN) {
    _wsInstance.send(JSON.stringify({ type: 'chat', message }))
    getStore().setTyping(true)
    clearTimeout(_typingTimeout)
    _typingTimeout = setTimeout(() => getStore().setTyping(false), 30000)
  }
}
