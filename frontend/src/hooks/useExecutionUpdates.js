import { useEffect, useRef, useState, useCallback } from 'react'

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_HOST = window.location.host

export const useExecutionUpdates = () => {
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptRef = useRef(0)
  const subscriptionsRef = useRef(new Set())

  const [state, setState] = useState({
    tasks: [],
    pipeline: null,
    agents: [],
    loading: true,
    error: null,
  })

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(`${WS_PROTOCOL}//${WS_HOST}/ws/execution`)
      ws.onopen = () => {
        reconnectAttemptRef.current = 0
        setState(prev => ({ ...prev, error: null }))
        // Resubscribe after reconnect
        if (subscriptionsRef.current.has('tasks')) {
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'tasks' }))
        }
        if (subscriptionsRef.current.has('agents')) {
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'agents' }))
        }
        if (subscriptionsRef.current.has('pipeline')) {
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'execution-trace' }))
        }
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          setState(prev => {
            const updated = { ...prev }
            if (msg.type === 'tasks' && Array.isArray(msg.data)) {
              updated.tasks = msg.data.slice(0, 100).sort((a, b) =>
                new Date(b.createdAt || 0) - new Date(a.createdAt || 0)
              )
            } else if (msg.type === 'agents' && Array.isArray(msg.data)) {
              updated.agents = msg.data
                .sort((a, b) => new Date(b.lastSeen || 0) - new Date(a.lastSeen || 0))
                .slice(0, 5)
            } else if (msg.type === 'execution-trace' && msg.data) {
              updated.pipeline = msg.data
            }
            return updated
          })
        } catch (parseErr) {
          console.error('WS parse error:', parseErr)
        }
      }

      ws.onerror = (err) => {
        console.error('WS error:', err)
        setState(prev => ({ ...prev, error: 'Connection error' }))
      }

      ws.onclose = () => {
        wsRef.current = null
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000)
        reconnectAttemptRef.current++
        reconnectTimeoutRef.current = setTimeout(connect, delay)
      }

      wsRef.current = ws
    } catch (err) {
      console.error('WS creation error:', err)
      setState(prev => ({ ...prev, error: 'Failed to connect' }))
    }
  }, [])

  const subscribe = useCallback((channel) => {
    subscriptionsRef.current.add(channel)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', channel }))
    }
  }, [])

  const unsubscribe = useCallback((channel) => {
    subscriptionsRef.current.delete(channel)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', channel }))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [connect])

  return {
    ...state,
    subscribe,
    unsubscribe,
  }
}
