import { useState, useRef, useEffect, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import { useSecurityStore } from '../../store/securityStore'
import { API_URL } from '../../config/api'
import './CommandDock.css'

const FOCUS_MODES = ['OPERATIONS', 'COGNITION', 'SECURITY', 'ECONOMY', 'BALANCED']

export default function CommandDock({ onToggleChat }) {
  const wsConnected = useAppStore(s => s.wsConnected)
  const systemHealth = useAppStore(s => s.systemHealth) || {}
  const threatScore = useSecurityStore(s => s.securityStatus?.threat_score) || 0

  const [focusModeIdx, setFocusModeIdx] = useState(() => {
    const saved = localStorage.getItem('nexus:focusMode')
    const idx = FOCUS_MODES.indexOf(saved)
    return idx >= 0 ? idx : 4
  })
  const focusMode = FOCUS_MODES[focusModeIdx]

  const cycleFocus = useCallback(() => {
    setFocusModeIdx(i => {
      const next = (i + 1) % FOCUS_MODES.length
      localStorage.setItem('nexus:focusMode', FOCUS_MODES[next])
      return next
    })
  }, [])

  const openPalette = useCallback(() => {
    window.dispatchEvent(new CustomEvent('nx:command-palette:open'))
  }, [])

  // Rolling health history for sparkline
  const healthHistory = useRef([50, 50, 50, 50, 50, 50, 50, 50])
  const health = Math.round(systemHealth.cpu_percent ?? systemHealth.cpu ?? 50)
  useEffect(() => {
    healthHistory.current = [...healthHistory.current.slice(1), health]
  }, [health])

  const sparkPoints = healthHistory.current.map((v, i) => {
    const x = (i / 7) * 56 + 2
    const y = 16 - (v / 100) * 14
    return `${x},${y}`
  }).join(' ')

  const systemHealthPct = Math.round(100 - (systemHealth.cpu_percent ?? 0) * 0.3 - (systemHealth.memory_percent ?? 0) * 0.2)

  return (
    <div className="cmd-bar">
      {/* Left: OS identity */}
      <div className="cmd-bar__left">
        <div className="cmd-bar__sigil">◈</div>
        <div className="cmd-bar__os-info">
          <div className="cmd-bar__os-name">SYSTEM OS v2.1.0</div>
          <div className="cmd-bar__os-status">
            <span className={`cmd-bar__status-dot ${wsConnected ? 'cmd-bar__status-dot--online' : 'cmd-bar__status-dot--offline'}`} />
            STATUS: {wsConnected ? 'OPERATIONAL' : 'DISCONNECTED'}
          </div>
        </div>
      </div>

      <div className="cmd-bar__sep" />

      {/* Center-left: actions */}
      <div className="cmd-bar__actions">
        <button className="cmd-bar__btn" onClick={openPalette} title="Ctrl+K">
          <span className="cmd-bar__btn-icon">⌨</span>
          <div className="cmd-bar__btn-text">
            <div className="cmd-bar__btn-label">COMMAND PALETTE</div>
            <div className="cmd-bar__btn-sub">CTRL+K</div>
          </div>
        </button>
        <button className="cmd-bar__btn" onClick={() => onToggleChat?.(true)} title="Open AI chat">
          <span className="cmd-bar__btn-icon">🎙</span>
          <div className="cmd-bar__btn-text">
            <div className="cmd-bar__btn-label">VOICE COMMAND</div>
            <div className="cmd-bar__btn-sub">PRESS TO SPEAK</div>
          </div>
        </button>
      </div>

      {/* Center: orb */}
      <div className="cmd-bar__center">
        <div className={`cmd-bar__orb ${threatScore > 40 ? 'cmd-bar__orb--alert' : ''}`} />
      </div>

      {/* Center-right: modes */}
      <div className="cmd-bar__modes">
        <button className="cmd-bar__btn" onClick={cycleFocus} title="Cycle focus mode">
          <span className="cmd-bar__btn-icon">◎</span>
          <div className="cmd-bar__btn-text">
            <div className="cmd-bar__btn-label">FOCUS MODE</div>
            <div className="cmd-bar__btn-sub">{focusMode}</div>
          </div>
        </button>
        <button className="cmd-bar__btn" title="Workspace">
          <span className="cmd-bar__btn-icon">⊞</span>
          <div className="cmd-bar__btn-text">
            <div className="cmd-bar__btn-label">WORKSPACE</div>
            <div className="cmd-bar__btn-sub">DEFAULT</div>
          </div>
        </button>
      </div>

      <div className="cmd-bar__sep" />

      {/* Right: health sparkline */}
      <div className="cmd-bar__right">
        <div className="cmd-bar__health-label">SYSTEM HEALTH</div>
        <svg className="cmd-bar__sparkline" width="60" height="20" viewBox="0 0 60 20">
          <polyline
            points={sparkPoints}
            fill="none"
            stroke="rgba(255,184,0,0.7)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div className="cmd-bar__health-val">↑ {Math.max(0, systemHealthPct)}%</div>
      </div>
    </div>
  )
}
