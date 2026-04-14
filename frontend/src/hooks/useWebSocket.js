import { useEffect } from 'react'
import { useAppStore } from '../store/appStore'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

// Module-level singleton to prevent duplicate connections
let _wsInstance = null
let _reconnectTimer = null
let _initialized = false
// Safety timer: clears the typing indicator if no AI response arrives
let _typingTimeout = null

function getStore() {
  return useAppStore.getState()
}

function connectSingleton() {
  if (_wsInstance?.readyState === WebSocket.OPEN || _wsInstance?.readyState === WebSocket.CONNECTING) return

  const ws = new WebSocket(WS_URL)
  _wsInstance = ws

  ws.onopen = () => {
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
          if (data.agents) store.setAgents(data.agents)
          break
        case 'system:status':
          store.setSystemStatus(data)
          break
        case 'orchestrator:message':
          clearTimeout(_typingTimeout)
          store.setTyping(false)
          store.addChatMessage({ role: 'ai', content: data.message, ts: Date.now(), subsystem: data.subsystem })
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
        case 'autonomy:status':
          store.setAutonomyStatus(data)
          break
        case 'workflow:snapshot':
          store.setWorkflowSnapshot(data)
          break
        case 'workflow:update':
          store.upsertWorkflowRun(data)
          break
      }
    } catch (e) { /* ignore */ }
  }

  ws.onclose = () => {
    const store = getStore()
    store.setWsConnected(false)
    store.setWs(null)
    clearTimeout(_typingTimeout)
    store.setTyping(false)
    store.addHeartbeatLog({ text: '[SYSTEM] Connection lost — reconnecting...', level: 'warning', ts: Date.now() })
    _wsInstance = null
    _reconnectTimer = setTimeout(connectSingleton, 3000)
  }

  ws.onerror = () => {
    ws.close()
  }
}

export function useWebSocket() {
  useEffect(() => {
    if (!_initialized) {
      _initialized = true
      connectSingleton()
    }
    return () => {
      // Module-level singleton intentionally persists for app lifetime.
      // Clear any pending reconnect timer if all consumers unmount.
      clearTimeout(_reconnectTimer)
    }
  }, [])

  const sendMessage = (message) => {
    if (_wsInstance?.readyState === WebSocket.OPEN) {
      _wsInstance.send(JSON.stringify({ type: 'chat', message }))
      getStore().setTyping(true)
      // Safety: clear typing indicator after 30 s if no response arrives
      clearTimeout(_typingTimeout)
      _typingTimeout = setTimeout(() => getStore().setTyping(false), 30000)
    }
  }

  return { sendMessage }
}

/**
 * Standalone `sendMessage` — call without the hook to avoid
 * duplicate cleanup / reconnect-timer interference.
 * Safe to import in any component; the WebSocket singleton is
 * initialised by `useWebSocket()` in App.jsx.
 */
export function sendChatMessage(message) {
  if (_wsInstance?.readyState === WebSocket.OPEN) {
    _wsInstance.send(JSON.stringify({ type: 'chat', message }))
    getStore().setTyping(true)
    clearTimeout(_typingTimeout)
    _typingTimeout = setTimeout(() => getStore().setTyping(false), 30000)
  }
}
