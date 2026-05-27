import { useEffect, useRef } from 'react'
import { useStore } from '../store/ascendStore'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  // Tracks timestamp of the last received chat_chunk to detect hung streams (Break #1)
  const lastChunkRef = useRef<number>(0)
  const streamTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
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

  // Reset the 20-second stream watchdog timer (Break #1)
  const resetStreamTimeout = (context: string) => {
    if (streamTimeoutRef.current) clearTimeout(streamTimeoutRef.current)
    lastChunkRef.current = Date.now()
    streamTimeoutRef.current = setTimeout(() => {
      const state = useStore.getState()
      if (state.activeStream?.context === context) {
        clearStream()
        addChatToContext(context, {
          role: 'system',
          content: 'Response timed out — please try again.',
          tag: 'TIMEOUT',
        })
      }
    }, 20000)
  }

  const cancelStreamTimeout = () => {
    if (streamTimeoutRef.current) {
      clearTimeout(streamTimeoutRef.current)
      streamTimeoutRef.current = null
    }
  }

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

            // Break #7: provider-unavailable errors sent as a distinct type
            case 'chat_error': {
              const { content, context } = msg.data as { content: string; context: string }
              cancelStreamTimeout()
              clearStream()
              if (content?.trim()) {
                addChatToContext(context, {
                  role: 'ai',
                  content,
                  tag: 'ERROR',
                })
              }
              break
            }

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
                // Reset the 20-second watchdog on every incoming chunk (Break #1)
                resetStreamTimeout(context)
              } else {
                // Stream complete — persist message then clear stream
                cancelStreamTimeout()
                const accumulated = useStore.getState().activeStream

                if (accumulated && accumulated.context === context) {
                  // Normal path: stream was active
                  const finalContent = accumulated.content
                  if (finalContent.trim()) {
                    addChatToContext(context, { role: 'ai', content: finalContent })
                  }
                } else if (content && content.trim()) {
                  // Break #2: done=true arrived but no stream was ever started
                  // (single-chunk case, e.g. provider-unavailable fallback via chat_chunk)
                  addChatToContext(context, { role: 'ai', content })
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
        // Break #1: any active stream is dead when the socket closes — clear it
        // so the UI never stays permanently stuck on "loading".
        clearStream()
        cancelStreamTimeout()
        wsRef.current = null
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      alive = false
      clearTimeout(reconnectTimer)
      cancelStreamTimeout()
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
