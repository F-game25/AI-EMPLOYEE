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

  const [tick, setTick] = useState(() => Date.now())

  // Single 1s interval drives both clock and uptime — one re-render per second
  useEffect(() => {
    const id = setInterval(() => setTick(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const _now = new Date(tick)
  const clock = _now.getHours().toString().padStart(2, '0') + ':' +
    _now.getMinutes().toString().padStart(2, '0') + ':' +
    _now.getSeconds().toString().padStart(2, '0')

  const _uptimeSec = Math.floor((systemStatus?.uptime || 0) / 1000)
  const uptime =
    Math.floor(_uptimeSec / 3600).toString().padStart(2, '0') + ':' +
    Math.floor((_uptimeSec % 3600) / 60).toString().padStart(2, '0') + ':' +
    (_uptimeSec % 60).toString().padStart(2, '0')

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
