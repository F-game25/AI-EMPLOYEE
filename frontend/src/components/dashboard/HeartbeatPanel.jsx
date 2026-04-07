import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const LEVEL_COLORS = {
  info: '#888',
  success: '#00ff88',
  warning: '#ffaa00',
  error: '#ff3366',
}

export default function HeartbeatPanel() {
  const logs = useAppStore(s => s.heartbeatLogs)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: 'rgba(10,10,10,0.8)',
        borderRight: '1px solid rgba(245,196,0,0.1)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 flex-shrink-0"
        style={{ borderBottom: '1px solid rgba(245,196,0,0.1)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: '#F5C400' }}>
          HEARTBEAT
        </span>
        <motion.div
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: '#F5C400' }}
        />
      </div>

      {/* Logs */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5"
        style={{ scrollBehavior: 'smooth' }}
      >
        <AnimatePresence initial={false}>
          {logs.map((log, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              className="font-mono text-xs leading-relaxed"
              style={{ color: LEVEL_COLORS[log.level] || '#888' }}
            >
              <span style={{ color: '#333', marginRight: '6px' }}>
                {new Date(log.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              {log.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
