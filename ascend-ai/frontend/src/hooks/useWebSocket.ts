import { useEffect, useRef } from 'react'
import { useStore } from '../store/ascendStore'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const { setWsConnected, setSystemStats, setAgents, addChartPoint, setMoneyRevenue, addFeedLine } = useStore()

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
  }, [setWsConnected, setSystemStats, setAgents, addChartPoint, setMoneyRevenue, addFeedLine])
}
