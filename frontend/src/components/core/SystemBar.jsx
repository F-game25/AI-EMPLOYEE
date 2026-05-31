import { useEffect, useState } from 'react'
import { useSystemStore } from '../../store/systemStore'
import { useSecurityStore } from '../../store/securityStore'
import { useEconomyStore } from '../../store/economyStore'
import './SystemBar.css'

export default function SystemBar({
  metrics = {},
  wsConnected: wsConnectedProp = null,
}) {
  const wsConnectedStore = useSystemStore((s) => s.wsConnected)
  const systemStatus = useSystemStore((s) => s.systemStatus)
  const pythonBackendReady = useSystemStore((s) => s.pythonBackendReady)
  const securityStatus = useSecurityStore((s) => s.securityStatus)
  const revenue = useEconomyStore((s) => s.revenue)

  // Use prop value if provided, otherwise use store
  const wsConnected = wsConnectedProp !== null ? wsConnectedProp : wsConnectedStore

  const [clock, setClock] = useState('00:00:00')
  const [uptime, setUptime] = useState('00:00:00')

  // Live clock tick
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(
        now.getHours().toString().padStart(2, '0') +
        ':' +
        now.getMinutes().toString().padStart(2, '0') +
        ':' +
        now.getSeconds().toString().padStart(2, '0')
      )
    }
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [])

  // Uptime formatter from systemStatus
  useEffect(() => {
    const updateUptime = () => {
      const seconds = Math.floor((systemStatus?.uptime || 0) / 1000)
      const h = Math.floor(seconds / 3600)
      const m = Math.floor((seconds % 3600) / 60)
      const s = seconds % 60
      setUptime(
        h.toString().padStart(2, '0') +
        ':' +
        m.toString().padStart(2, '0') +
        ':' +
        s.toString().padStart(2, '0')
      )
    }
    updateUptime()
    const interval = setInterval(updateUptime, 1000)
    return () => clearInterval(interval)
  }, [systemStatus?.uptime])

  // Threat level color and label
  const threatScore = securityStatus?.threat_score || 0
  let threatLevel = 'LOW'
  let threatColor = '#00ff88'
  if (threatScore >= 75) {
    threatLevel = 'CRITICAL'
    threatColor = '#ff3333'
  } else if (threatScore >= 50) {
    threatLevel = 'HIGH'
    threatColor = '#ff6b00'
  } else if (threatScore >= 30) {
    threatLevel = 'MEDIUM'
    threatColor = '#ffa500'
  }

  const handleEmergencyStop = () => {
    if (
      confirm(
        'Trigger EMERGENCY STOP? All autonomous operations will halt immediately.'
      )
    ) {
      const ws = useSystemStore.getState().ws
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            type: 'emergency_stop',
            timestamp: new Date().toISOString(),
          })
        )
      } else {
        console.warn('WebSocket not connected, cannot send emergency stop')
      }
    }
  }

  // Revenue label
  const dailyRevenue = revenue?.daily || 0
  const revenueStr = `$${dailyRevenue.toFixed(2)} TODAY`

  return (
    <div className="system-bar">
      {/* Grid background overlay */}
      <div className="system-bar-grid"></div>

      {/* Content container */}
      <div className="system-bar-content">
        {/* Clock */}
        <div className="system-bar-item clock">
          <span className="system-bar-icon">⏱</span>
          <span className="system-bar-label">{clock}</span>
        </div>

        {/* Mode indicator */}
        <div className="system-bar-item mode-chip">
          <span className="system-bar-label">MODE:</span>
          <span className="mode-value">{systemStatus?.mode || 'MANUAL'}</span>
        </div>

        {/* Uptime */}
        <div className="system-bar-item uptime">
          <span className="system-bar-icon">↑</span>
          <span className="system-bar-label">{uptime}</span>
        </div>

        {/* Threat level */}
        <div
          className="system-bar-item threat"
          style={{ '--threat-color': threatColor }}
        >
          <span className="system-bar-label">THREAT:</span>
          <span
            className="threat-dot"
            style={{ backgroundColor: threatColor }}
          ></span>
          <span className="system-bar-label threat-level">{threatLevel}</span>
        </div>

        {/* Revenue */}
        <div className="system-bar-item revenue">
          <span className="system-bar-label">{revenueStr}</span>
        </div>

        {/* Python backend status */}
        <div className="system-bar-item status-indicator">
          <span className="system-bar-label">PYTHON:</span>
          <span
            className={`status-dot ${pythonBackendReady ? 'connected' : 'disconnected'}`}
          ></span>
        </div>

        {/* WebSocket status */}
        <div className="system-bar-item status-indicator">
          <span className="system-bar-label">WS:</span>
          <span
            className={`status-dot ${wsConnected ? 'connected' : 'disconnected'}`}
          ></span>
        </div>

        {/* Spacer */}
        <div className="system-bar-spacer"></div>

        {/* Emergency stop button */}
        <button className="system-bar-item emergency-stop-btn" onClick={handleEmergencyStop}>
          <span className="system-bar-label">STOP</span>
        </button>
      </div>
    </div>
  )
}
