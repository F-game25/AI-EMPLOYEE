import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'

export default function TopBar() {
  const wsConnected = useAppStore(s => s.wsConnected)
  const systemStatus = useAppStore(s => s.systemStatus)
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <header
      className="flex items-center justify-between px-4 py-3 gap-4 flex-shrink-0"
      style={{
        borderBottom: '1px solid var(--border-gold-dim)',
        background: 'linear-gradient(180deg, rgba(8,8,8,0.98), rgba(6,6,6,0.96))',
        zIndex: 'var(--z-topbar)',
      }}
    >
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm font-bold tracking-widest" style={{ color: 'var(--gold)' }}>
          AI EMPLOYEE COMMAND
        </span>
        <span className="font-mono text-xs tier-3-surface px-2 py-1">
          MODE: {systemStatus?.mode || 'MANUAL'}
        </span>
        <span className="font-mono text-xs tier-3-surface px-2 py-1">
          ROBOT: {systemStatus?.active_robot || 'none'}
        </span>
        <span className="font-mono text-xs tier-3-surface px-2 py-1">
          LOCATION: {systemStatus?.robot_location || 'idle'}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="font-mono text-xs tier-3-surface px-2 py-1 max-w-[460px] truncate" title={systemStatus?.thinking_mode || ''}>
          THINKING: {systemStatus?.thinking_mode || 'Awaiting workload'}
        </span>
        <span className="font-mono text-xs tier-3-surface px-2 py-1">
          RUNNING {systemStatus.running_agents || 0}/{systemStatus.total_agents || 0}
        </span>
        <span className="font-mono text-xs tier-3-surface px-2 py-1">
          {wsConnected ? 'LIVE' : 'OFFLINE'}
        </span>
        <time className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
          {time.toLocaleTimeString('en-US', { hour12: false })}
        </time>
      </div>
    </header>
  )
}
