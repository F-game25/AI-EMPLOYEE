import { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const API_BASE = `http://${window.location.hostname}:3001`

const MODE_CONFIG = {
  OFF: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.35)', label: 'PAUSED', icon: '⏸' },
  ON: { color: '#eab308', bg: 'rgba(234,179,8,0.08)', border: 'rgba(234,179,8,0.35)', label: 'LIMITED', icon: '⚡' },
  AUTO: { color: '#22c55e', bg: 'rgba(34,197,94,0.08)', border: 'rgba(34,197,94,0.35)', label: 'AUTONOMOUS', icon: '🔄' },
}

export default function SystemModeToggle() {
  const autonomy = useAppStore((s) => s.autonomyStatus)
  const [busy, setBusy] = useState(false)

  const currentMode = autonomy?.mode?.mode || 'OFF'
  const cfg = MODE_CONFIG[currentMode] || MODE_CONFIG.OFF
  const daemonRunning = autonomy?.daemon?.running || false

  const setModeRemote = useCallback(async (nextMode) => {
    setBusy(true)
    try {
      await fetch(`${API_BASE}/api/autonomy/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode }),
      })
    } catch { /* handled by next WS update */ }
    setBusy(false)
  }, [])

  const emergencyStop = useCallback(async () => {
    setBusy(true)
    try {
      await fetch(`${API_BASE}/api/autonomy/emergency-stop`, { method: 'POST' })
    } catch { /* handled by next WS update */ }
    setBusy(false)
  }, [])

  return (
    <div className="ds-card p-3">
      {/* Mode indicator */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <motion.div
            animate={currentMode !== 'OFF' ? { opacity: [1, 0.3, 1] } : { opacity: 0.3 }}
            transition={{ duration: 1.2, repeat: Infinity }}
            className="w-2 h-2 rounded-full"
            style={{ background: cfg.color }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: cfg.color }}>
            {cfg.icon} {cfg.label}
          </span>
        </div>
        <span className="font-mono text-[10px]" style={{ color: daemonRunning ? '#22c55e' : 'var(--text-muted)' }}>
          {daemonRunning ? '● DAEMON ACTIVE' : '○ DAEMON IDLE'}
        </span>
      </div>

      {/* Mode toggle buttons */}
      <div className="grid grid-cols-3 gap-1 mb-2">
        {['OFF', 'ON', 'AUTO'].map((m) => {
          const mc = MODE_CONFIG[m]
          const active = currentMode === m
          return (
            <button
              key={m}
              onClick={() => setModeRemote(m)}
              disabled={busy}
              className="font-mono text-[10px] py-1.5 rounded transition-all"
              style={{
                background: active ? mc.bg : 'rgba(255,255,255,0.02)',
                border: `1px solid ${active ? mc.border : 'var(--border-subtle)'}`,
                color: active ? mc.color : 'var(--text-muted)',
                cursor: busy ? 'not-allowed' : 'pointer',
                opacity: busy ? 0.5 : 1,
              }}
            >
              {m}
            </button>
          )
        })}
      </div>

      {/* Emergency stop */}
      <button
        onClick={emergencyStop}
        disabled={busy || currentMode === 'OFF'}
        className="w-full font-mono text-[10px] py-1.5 rounded"
        style={{
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.35)',
          color: '#ef4444',
          cursor: busy || currentMode === 'OFF' ? 'not-allowed' : 'pointer',
          opacity: busy || currentMode === 'OFF' ? 0.4 : 1,
        }}
      >
        ⚠ EMERGENCY STOP
      </button>
    </div>
  )
}
