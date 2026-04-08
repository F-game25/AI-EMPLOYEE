import { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const BOOT_LINES = [
  { text: '> INITIALIZING AI-EMPLOYEE OS v2.0...', delay: 0 },
  { text: '> Loading neural core modules...', delay: 320 },
  { text: '> Establishing secure channels...', delay: 640 },
  { text: '> Calibrating agent network [56 agents]...', delay: 960 },
  { text: '> Scanning for anomalies... [CLEAR]', delay: 1280 },
  { text: '> Synchronizing orchestrator...', delay: 1600 },
  { text: '> Verifying memory integrity... [OK]', delay: 1920 },
  { text: '> All systems nominal. BOOT COMPLETE.', delay: 2240 },
]

function GlitchText({ children, style, className }) {
  const [glitch, setGlitch] = useState(false)
  useEffect(() => {
    const t1 = setTimeout(() => setGlitch(true), 200)
    const t2 = setTimeout(() => setGlitch(false), 350)
    const t3 = setTimeout(() => setGlitch(true), 500)
    const t4 = setTimeout(() => setGlitch(false), 580)
    return () => [t1, t2, t3, t4].forEach(clearTimeout)
  }, [])
  return (
    <span className={className} style={{ position: 'relative', display: 'inline-block', ...style }}>
      {children}
      {glitch && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            color: '#ff3366',
            clipPath: 'inset(30% 0 40% 0)',
            transform: 'translate(-3px, 0)',
            opacity: 0.7,
          }}
        >
          {children}
        </span>
      )}
      {glitch && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            color: '#00ff88',
            clipPath: 'inset(55% 0 10% 0)',
            transform: 'translate(3px, 0)',
            opacity: 0.7,
          }}
        >
          {children}
        </span>
      )}
    </span>
  )
}

export default function BootSequence({ onComplete }) {
  const [visibleLines, setVisibleLines] = useState([])
  const [progress, setProgress] = useState(0)
  const [showLogo, setShowLogo] = useState(false)
  const [logoReady, setLogoReady] = useState(false)

  // Keep a stable ref to the latest onComplete so the timer effect below
  // never needs to re-run (and reset all timers) when the parent re-renders
  // due to unrelated state changes (e.g. WebSocket events).
  const onCompleteRef = useRef(onComplete)
  useLayoutEffect(() => { onCompleteRef.current = onComplete })

  useEffect(() => {
    const timers = []

    BOOT_LINES.forEach((line, i) => {
      timers.push(
        setTimeout(() => {
          setVisibleLines(prev => [...prev, line.text])
          setProgress(Math.round(((i + 1) / BOOT_LINES.length) * 100))
        }, line.delay)
      )
    })

    const lastDelay = BOOT_LINES[BOOT_LINES.length - 1].delay
    timers.push(setTimeout(() => setShowLogo(true), lastDelay + 300))
    timers.push(setTimeout(() => setLogoReady(true), lastDelay + 700))
    timers.push(setTimeout(() => onCompleteRef.current?.(), lastDelay + 1400))

    return () => timers.forEach(clearTimeout)
  }, []) // empty deps — run once on mount; onComplete accessed via stable ref

  return (
    <motion.div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{ background: '#050505' }}
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Subtle radial background pulse */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        animate={{ opacity: [0.03, 0.06, 0.03] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, rgba(245,196,0,1) 0%, transparent 65%)',
        }}
      />

      <div className="relative w-full max-w-2xl px-8">
        {/* Terminal lines */}
        <div className="mb-6 min-h-[200px]">
          {visibleLines.map((line, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15 }}
              className="font-mono text-xs mb-1"
              style={{
                color: line.includes('COMPLETE') || line.includes('OK') || line.includes('CLEAR')
                  ? '#F5C400'
                  : '#888',
              }}
            >
              {line}
            </motion.div>
          ))}
        </div>

        {/* Progress bar */}
        <div
          className="w-full mb-8"
          style={{
            height: '2px',
            background: 'rgba(245,196,0,0.1)',
            borderRadius: '1px',
          }}
        >
          <motion.div
            initial={{ width: '0%' }}
            style={{
              height: '100%',
              background: 'linear-gradient(90deg, rgba(245,196,0,0.4), #F5C400)',
              borderRadius: '1px',
              boxShadow: '0 0 8px rgba(245,196,0,0.6)',
            }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          />
        </div>

        {/* Logo reveal */}
        <AnimatePresence>
          {showLogo && (
            <motion.div
              initial={{ opacity: 0, scaleX: 0 }}
              animate={{ opacity: 1, scaleX: 1 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
              className="flex items-center justify-center"
              style={{
                border: '1px solid rgba(245,196,0,0.4)',
                padding: '18px 60px',
                borderRadius: '4px',
                background: 'rgba(245,196,0,0.03)',
                boxShadow: logoReady
                  ? '0 0 60px rgba(245,196,0,0.25), inset 0 0 40px rgba(245,196,0,0.04)'
                  : 'none',
                transition: 'box-shadow 0.4s ease',
              }}
            >
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.25, duration: 0.3 }}
                className="font-mono text-2xl font-bold tracking-widest"
                style={{ color: '#F5C400' }}
              >
                <GlitchText>AI-EMPLOYEE</GlitchText>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Corner grid marks */}
      {[
        { top: 24, left: 24 },
        { top: 24, right: 24 },
        { bottom: 24, left: 24 },
        { bottom: 24, right: 24 },
      ].map((pos, i) => (
        <div
          key={i}
          className="absolute"
          style={{
            ...pos,
            width: 12,
            height: 12,
            borderTop: pos.top !== undefined ? '1px solid rgba(245,196,0,0.3)' : 'none',
            borderBottom: pos.bottom !== undefined ? '1px solid rgba(245,196,0,0.3)' : 'none',
            borderLeft: pos.left !== undefined ? '1px solid rgba(245,196,0,0.3)' : 'none',
            borderRight: pos.right !== undefined ? '1px solid rgba(245,196,0,0.3)' : 'none',
          }}
        />
      ))}
    </motion.div>
  )
}
