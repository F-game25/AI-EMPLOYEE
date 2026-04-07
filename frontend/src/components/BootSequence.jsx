import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const BOOT_LINES = [
  '> INITIALIZING AI-EMPLOYEE OS v2.0...',
  '> Loading neural core modules...',
  '> Establishing secure channels...',
  '> Calibrating agent network [6 agents]...',
  '> Scanning for anomalies... [CLEAR]',
  '> Synchronizing orchestrator...',
  '> All systems nominal.',
  '> BOOT COMPLETE.',
]

export default function BootSequence({ onComplete }) {
  const [visibleLines, setVisibleLines] = useState([])
  const [showRect, setShowRect] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    let i = 0
    const interval = setInterval(() => {
      if (i < BOOT_LINES.length) {
        setVisibleLines(prev => [...prev, BOOT_LINES[i]])
        i++
      } else {
        clearInterval(interval)
        setTimeout(() => setShowRect(true), 300)
        setTimeout(() => setDone(true), 1200)
        setTimeout(() => onComplete?.(), 1600)
      }
    }, 300)
    return () => clearInterval(interval)
  }, [onComplete])

  return (
    <motion.div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{ background: '#050505' }}
      exit={{ opacity: 0, filter: 'blur(4px)' }}
      transition={{ duration: 0.4 }}
    >
      {/* Terminal lines */}
      <div className="w-full max-w-2xl px-8 mb-8">
        {visibleLines.map((line, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.1 }}
            className="font-mono text-sm mb-1"
            style={{ color: line.includes('COMPLETE') ? '#F5C400' : '#666' }}
          >
            {line}
          </motion.div>
        ))}
      </div>

      {/* Expanding rectangle */}
      <AnimatePresence>
        {showRect && (
          <motion.div
            initial={{ scaleX: 0, scaleY: 0, opacity: 0 }}
            animate={{ scaleX: 1, scaleY: 1, opacity: 1 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="flex items-center justify-center"
            style={{
              border: '2px solid #F5C400',
              boxShadow: '0 0 40px rgba(245, 196, 0, 0.6), inset 0 0 40px rgba(245, 196, 0, 0.05)',
              padding: '20px 60px',
              borderRadius: '4px',
            }}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              className="font-mono text-2xl font-bold tracking-widest glow-gold-text"
              style={{ color: '#F5C400' }}
            >
              AI-EMPLOYEE
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
