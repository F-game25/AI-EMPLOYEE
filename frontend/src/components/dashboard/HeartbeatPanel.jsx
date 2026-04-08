import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const LEVEL_COLORS = {
  info: 'var(--text-secondary)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--error)',
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
        background: 'var(--bg-panel)',
        borderRight: '1px solid var(--border-gold-dim)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2.5 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
          HEARTBEAT
        </span>
        <motion.div
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          className="w-1.5 h-1.5 rounded-full"
          aria-hidden="true"
          style={{ background: 'var(--gold)' }}
        />
      </div>

      {/* Logs — announced to screen readers as a live region */}
      <div
        ref={scrollRef}
        role="log"
        aria-label="System heartbeat log"
        aria-live="polite"
        aria-atomic="false"
        className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5"
        style={{ scrollBehavior: 'smooth' }}
      >
        <AnimatePresence initial={false}>
          {logs.map((log, idx) => (
            <motion.div
              key={`${log.ts}-${idx}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              className="font-mono text-xs leading-relaxed"
              style={{ color: LEVEL_COLORS[log.level] || 'var(--text-secondary)' }}
            >
              <span style={{ color: 'var(--text-dim)', marginRight: '6px' }}>
                {new Date(log.ts).toLocaleTimeString('en-US', {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>
              {log.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
