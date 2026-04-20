import { useEffect, useRef } from 'react'
import { useStore } from '../store/ascendStore'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const {
    setWsConnected,
    setSystemStats,
    setAgents,
    addChartPoint,
    setMoneyRevenue,
    addFeedLine,
    setLlmStatus,
    startStream,
    appendStream,
    clearStream,
    addChatToContext,
    setShowFallbackToast,
    setFallbackNotified,
  } = useStore()

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>
    let alive = true

    function connect() {
      if (!alive) return
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => setWsConnected(true)

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          switch (msg.type) {
            case 'system_stats':
              setSystemStats(msg.data)
              addChartPoint({
                tokens: Math.round(Math.random() * 100),
                latency: msg.data.cpu_percent,
                activity: Math.round(Math.random() * 50 + 20),
              })
              break
            case 'agent_status':
              setAgents(msg.data)
              break
            case 'money_update':
              setMoneyRevenue(msg.data?.revenue ?? 0)
              break
            case 'log_line':
              if (msg.data?.bot?.includes('forge')) addFeedLine('forge', msg.data.message)
              else if (msg.data?.bot?.includes('money')) addFeedLine('money', msg.data.message)
              else if (msg.data?.bot?.includes('black')) addFeedLine('blacklight', msg.data.message)
              break
            case 'llm_status':
              setLlmStatus(msg.data)
              break
            case 'chat_chunk': {
              const { content, done, context, fallback } = msg.data as {
                content: string
                done: boolean
                context: string
                fallback?: boolean
              }
              const state = useStore.getState()
              if (!done) {
                // Show fallback toast once (first chunk with fallback=true)
                if (fallback && !state.fallbackNotified) {
                  setFallbackNotified(true)
                  setShowFallbackToast(true)
                  setTimeout(() => setShowFallbackToast(false), 5000)
                }
                if (state.activeStream?.context === context) {
                  appendStream(content)
                } else {
                  startStream(context, !!fallback)
                  if (content) appendStream(content)
                }
              } else {
                // Stream complete — persist message then clear stream
                const accumulated = useStore.getState().activeStream
                if (accumulated && accumulated.context === context) {
                  const finalContent = accumulated.content
                  if (finalContent.trim()) {
                    addChatToContext(context, { role: 'ai', content: finalContent })
                  }
                }
                clearStream()
              }
              break
            }
          }
        } catch { /* ignore parse errors */ }
      }

      ws.onclose = () => {
        setWsConnected(false)
        wsRef.current = null
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      alive = false
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [
    setWsConnected,
    setSystemStats,
    setAgents,
    addChartPoint,
    setMoneyRevenue,
    addFeedLine,
    setLlmStatus,
    startStream,
    appendStream,
    clearStream,
    addChatToContext,
    setShowFallbackToast,
    setFallbackNotified,
  ])
}
