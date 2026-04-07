import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

export default function TopBar() {
  const { wsConnected, systemStatus, user } = useAppStore()
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <div
      className="flex items-center justify-between px-4 h-10 flex-shrink-0"
      style={{
        background: 'rgba(10,10,10,0.95)',
        borderBottom: '1px solid rgba(245,196,0,0.15)',
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* Left: logo */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs font-bold tracking-widest" style={{ color: '#F5C400' }}>
          AI-EMPLOYEE
        </span>
        <span className="font-mono text-xs" style={{ color: '#333' }}>|</span>
        <span className="font-mono text-xs" style={{ color: '#555' }}>OS v2.0</span>
      </div>

      {/* Center: system metrics */}
      <div className="flex items-center gap-6">
        <Metric label="CPU" value={`${systemStatus.cpu || 0}%`} warn={systemStatus.cpu > 70} />
        <Metric label="MEM" value={`${systemStatus.memory || 0}%`} warn={systemStatus.memory > 70} />
        <Metric label="CONN" value={systemStatus.connections || 0} />
      </div>

      {/* Right: time + connection + user */}
      <div className="flex items-center gap-4">
        <span className="font-mono text-xs" style={{ color: '#555' }}>
          {time.toLocaleTimeString('en-US', { hour12: false })}
        </span>
        <motion.div
          animate={{ opacity: [1, 0.4, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="flex items-center gap-1.5"
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: wsConnected ? '#00ff88' : '#ff3366' }}
          />
          <span className="font-mono text-xs" style={{ color: wsConnected ? '#00ff88' : '#ff3366' }}>
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </motion.div>
        {user && (
          <span className="font-mono text-xs" style={{ color: '#666' }}>
            [{user.username.toUpperCase()}]
          </span>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, warn }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-xs" style={{ color: '#444' }}>{label}</span>
      <span className="font-mono text-xs" style={{ color: warn ? '#ffaa00' : '#888' }}>{value}</span>
    </div>
  )
}
