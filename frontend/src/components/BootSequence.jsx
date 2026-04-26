import { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { API_URL } from '../config/api'

// Particle system for immersive boot background
class BootParticleSystem {
  constructor(canvasRef) {
    this.canvas = canvasRef.current
    if (!this.canvas) return
    this.ctx = this.canvas.getContext('2d')
    this.particles = []
    this.animId = null
    this.resizeCanvas()
    window.addEventListener('resize', () => this.resizeCanvas())
  }

  resizeCanvas() {
    this.canvas.width = window.innerWidth
    this.canvas.height = window.innerHeight
  }

  init() {
    this.particles = []
    for (let i = 0; i < 60; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.2,
        vy: (Math.random() - 0.5) * 0.2,
        radius: Math.random() * 0.8 + 0.3,
        color: Math.random() > 0.5 ? 'rgba(32,214,199,' : 'rgba(229,199,107,',
      })
    }
    this.animate()
  }

  animate() {
    this.ctx.fillStyle = 'rgba(7,8,16,1)'
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height)

    this.particles.forEach(p => {
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1
      if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1
      p.x = Math.max(0, Math.min(this.canvas.width, p.x))
      p.y = Math.max(0, Math.min(this.canvas.height, p.y))

      this.ctx.fillStyle = p.color + '0.5)'
      this.ctx.beginPath()
      this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      this.ctx.fill()
    })

    this.animId = requestAnimationFrame(() => this.animate())
  }

  stop() {
    if (this.animId) cancelAnimationFrame(this.animId)
  }
}

function buildBootLines(agentCount) {
  return [
    { text: '> INITIALIZING ULTRON OS v2.0...', delay: 0 },
    { text: '> Loading neural core modules...', delay: 320 },
    { text: '> Establishing secure channels...', delay: 640 },
    { text: `> Calibrating agent network [${agentCount} agents]...`, delay: 960 },
    { text: '> Scanning for anomalies... [CLEAR]', delay: 1280 },
    { text: '> Synchronizing orchestrator...', delay: 1600 },
    { text: '> Verifying memory integrity... [OK]', delay: 1920 },
    { text: '> All systems nominal. BOOT COMPLETE.', delay: 2240 },
  ]
}

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
            color: 'var(--error)',
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
            color: '#00e676',
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

  const canvasRef = useRef(null)
  const particleSystemRef = useRef(null)

  // Detect Electron launch for faster boot
  const isElectronLaunch = typeof window !== 'undefined' && window.navigator.userAgent.includes('Electron')

  // Keep a stable ref to the latest onComplete so the timer effect below
  // never needs to re-run (and reset all timers) when the parent re-renders
  // due to unrelated state changes (e.g. WebSocket events).
  const onCompleteRef = useRef(onComplete)
  useLayoutEffect(() => { onCompleteRef.current = onComplete })

  useEffect(() => {
    if (canvasRef.current && !particleSystemRef.current) {
      particleSystemRef.current = new BootParticleSystem(canvasRef)
      particleSystemRef.current.init()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const timers = []

    // Fetch actual agent count from backend, fall back to 57
    const startBoot = (agentCount) => {
      if (cancelled) return
      const BOOT_LINES = buildBootLines(agentCount)

      BOOT_LINES.forEach((line, i) => {
        timers.push(
          setTimeout(() => {
            if (cancelled) return
            setVisibleLines(prev => [...prev, line.text])
            setProgress(Math.round(((i + 1) / BOOT_LINES.length) * 100))
          }, line.delay)
        )
      })

      const lastDelay = BOOT_LINES[BOOT_LINES.length - 1].delay
      const speedup = isElectronLaunch ? 0.3 : 1.0 // 3x faster boot when launched from Electron
      timers.push(setTimeout(() => { if (!cancelled) setShowLogo(true) }, (lastDelay + 300) * speedup))
      timers.push(setTimeout(() => { if (!cancelled) setLogoReady(true) }, (lastDelay + 700) * speedup))
      timers.push(setTimeout(() => { if (!cancelled) onCompleteRef.current?.() }, (lastDelay + 1400) * speedup))
    }

    fetch(`${API_URL}/agents`)
      .then(r => r.json())
      .then(data => startBoot(data?.agents?.length || 57))
      .catch(() => startBoot(57))

    return () => {
      cancelled = true
      timers.forEach(clearTimeout)
    }
  }, []) // empty deps — run once on mount; onComplete accessed via stable ref

  return (
    <motion.div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{ background: 'var(--bg-base)', overflow: 'hidden' }}
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Particle canvas background */}
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', inset: 0, zIndex: 1 }}
      />

      {/* Scanline effect */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'linear-gradient(transparent 50%, rgba(32,214,199,0.015) 50%)',
          backgroundSize: '100% 4px',
          zIndex: 2,
        }}
      />

      {/* Hexgrid background */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'repeating-linear-gradient(60deg, transparent, transparent 35px, rgba(229,199,107,0.02) 35px, rgba(229,199,107,0.02) 70px)',
          zIndex: 2,
        }}
      />

      {/* Enhanced radial glow */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        animate={{ opacity: [0.10, 0.22, 0.10] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, rgba(212,175,55,1) 0%, transparent 65%)',
          zIndex: 2,
        }}
      />

      <div className="relative w-full px-[15%] z-10">
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
                  ? '#D4AF37'
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
            background: 'rgba(212,175,55,0.1)',
            borderRadius: '1px',
          }}
        >
          <motion.div
            initial={{ width: '0%' }}
            style={{
              height: '100%',
              background: 'linear-gradient(90deg, rgba(212,175,55,0.4), #D4AF37)',
              borderRadius: '1px',
              boxShadow: '0 0 8px rgba(212,175,55,0.6)',
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
              className="flex items-center justify-center relative"
              style={{
                border: '2px solid rgba(212,175,55,0.4)',
                padding: '24px 80px',
                borderRadius: '6px',
                background: 'rgba(212,175,55,0.04)',
                transition: 'box-shadow 0.4s ease',
              }}
            >
              {logoReady && (
                <motion.div
                  className="absolute inset-0 rounded-[6px]"
                  animate={{ boxShadow: ['0 0 20px rgba(212,175,55,0.1)', '0 0 60px rgba(212,175,55,0.3)', '0 0 20px rgba(212,175,55,0.1)'] }}
                  transition={{ duration: 2, repeat: Infinity }}
                  style={{ pointerEvents: 'none' }}
                />
              )}
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.25, duration: 0.4 }}
                className="font-mono text-4xl font-bold tracking-[0.4em]"
                style={{ color: '#D4AF37', position: 'relative', zIndex: 1 }}
              >
                <GlitchText>ULTRON</GlitchText>
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
            borderTop: pos.top !== undefined ? '1px solid rgba(212,175,55,0.3)' : 'none',
            borderBottom: pos.bottom !== undefined ? '1px solid rgba(212,175,55,0.3)' : 'none',
            borderLeft: pos.left !== undefined ? '1px solid rgba(212,175,55,0.3)' : 'none',
            borderRight: pos.right !== undefined ? '1px solid rgba(212,175,55,0.3)' : 'none',
          }}
        />
      ))}
    </motion.div>
  )
}
