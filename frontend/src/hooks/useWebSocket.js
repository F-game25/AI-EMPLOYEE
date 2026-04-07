import { useEffect, useRef } from 'react'
import { useAppStore } from '../store/appStore'

const WS_URL = `ws://${window.location.hostname}:3001/ws`

export function useWebSocket() {
  const { setWs, setWsConnected, addHeartbeatLog, setAgents, setSystemStatus, addChatMessage } = useAppStore()
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      setWs(ws)
      addHeartbeatLog({ text: '[SYSTEM] WebSocket connected', level: 'success', ts: Date.now() })
    }

    ws.onmessage = (evt) => {
      try {
        const { event, data } = JSON.parse(evt.data)
        switch (event) {
          case 'heartbeat':
            addHeartbeatLog({ text: data.message, level: data.level || 'info', ts: Date.now() })
            break
          case 'agent:update':
            if (data.agents) setAgents(data.agents)
            break
          case 'system:status':
            setSystemStatus(data)
            break
          case 'orchestrator:message':
            addChatMessage({ role: 'ai', content: data.message, ts: Date.now() })
            break
        }
      } catch (e) { /* ignore */ }
    }

    ws.onclose = () => {
      setWsConnected(false)
      setWs(null)
      addHeartbeatLog({ text: '[SYSTEM] Connection lost — reconnecting...', level: 'warning', ts: Date.now() })
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  const sendMessage = (message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', message }))
    }
  }

  return { sendMessage }
}
