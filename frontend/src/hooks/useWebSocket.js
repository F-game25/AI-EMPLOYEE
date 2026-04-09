import { useEffect } from 'react'
import { useAppStore } from '../store/appStore'

const WS_URL = `ws://${window.location.hostname}:3001/ws`

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
          store.addChatMessage({ role: 'ai', content: data.message, ts: Date.now() })
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
