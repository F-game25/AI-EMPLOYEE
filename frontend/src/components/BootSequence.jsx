import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { API_URL } from '../config/api'
import { ensureOperatorToken } from '../api/auth'
import './BootSequence.css'

const BOOT_STEPS = [
  { id: 'launcher', label: 'Launcher supervisor', detail: 'Nexus OS runtime connected' },
  { id: 'health', label: 'Backend health', detail: 'Waiting for Node gateway' },
  { id: 'agents', label: 'Agent registry', detail: 'Counting active agents' },
  { id: 'auth', label: 'Secure session', detail: 'Binding operator token' },
  { id: 'websocket', label: 'Realtime bus', detail: 'Bootstrapping event stream' },
  { id: 'dashboard', label: 'Dashboard render', detail: 'Mounting command center' },
]

// Cinematic flash lines — scripted messages that appear 400ms apart
const CINEMATIC_LINES = [
  'LOADING NEURAL CORE...',
  'INITIALIZING COGNITIVE MESH',
  'AGENTS ONLINE',
  'SECURE MODE ACTIVE',
  'MEMORY FABRIC LINKED',
  'REALTIME BUS READY',
]

const PHASE_TO_STEP = {
  'app-init': 'launcher',
  auth: 'auth',
  health: 'health',
  'websocket-bootstrap': 'websocket',
  'dashboard-lazy-load': 'dashboard',
  'dashboard-timeout': 'dashboard',
  handoff: 'dashboard',
}

class BootParticleSystem {
  constructor(canvas) {
    this.canvas = canvas
    this.ctx = canvas?.getContext('2d')
    this.particles = []
    this.animId = null
    this.onResize = this.resizeCanvas.bind(this)
    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!this.canvas || !this.ctx) return
    this.resizeCanvas()
    window.addEventListener('resize', this.onResize)
  }

  resizeCanvas() {
    this.canvas.width = window.innerWidth
    this.canvas.height = window.innerHeight
  }

  init() {
    const count = this.reducedMotion ? 18 : 46
    this.particles = Array.from({ length: count }, () => ({
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      radius: Math.random() * 0.9 + 0.25,
      color: Math.random() > 0.55 ? 'rgba(229,199,107,' : 'rgba(32,214,199,',
    }))
    this.animate()
  }

  animate() {
    if (!this.ctx) return
    const { ctx, canvas } = this
    ctx.fillStyle = 'rgba(5,6,8,1)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    this.particles.forEach(p => {
      if (!this.reducedMotion) {
        p.x += p.vx
        p.y += p.vy
      }
      if (p.x < 0 || p.x > canvas.width) p.vx *= -1
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      ctx.fillStyle = `${p.color}0.55)`
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      ctx.fill()
    })

    this.animId = requestAnimationFrame(() => this.animate())
  }

  stop() {
    if (this.animId) cancelAnimationFrame(this.animId)
    window.removeEventListener('resize', this.onResize)
  }
}

function statusForStep(step, checks) {
  if (checks[step.id] === 'ok') return 'ok'
  if (checks[step.id] === 'fail') return 'fail'
  return 'running'
}

export default function BootSequence({ onComplete, subState }) {
  const [progress, setProgress] = useState(8)
  const [checks, setChecks] = useState({ launcher: 'running', health: 'running', agents: 'running', auth: 'running', websocket: 'running', dashboard: 'running' })
  const [lines, setLines] = useState(['> AETERNUS NEXUS boot supervisor engaged'])
  const [cinematicIdx, setCinematicIdx] = useState(0)
  const [agentCount, setAgentCount] = useState(null)
  const [launchMessage, setLaunchMessage] = useState(() => (
    typeof window !== 'undefined' && window.ai
      ? 'Synchronizing with desktop launcher'
      : 'Browser runtime connected'
  ))

  const canvasRef = useRef(null)
  const particlesRef = useRef(null)
  const onCompleteRef = useRef(onComplete)
  const completedRef = useRef(false)
  const startedAtRef = useRef(0)
  const isElectron = typeof window !== 'undefined' && !!window.ai

  useLayoutEffect(() => { onCompleteRef.current = onComplete })

  const activeIndex = useMemo(() => {
    const firstRunning = BOOT_STEPS.findIndex(step => checks[step.id] !== 'ok')
    return firstRunning === -1 ? BOOT_STEPS.length - 1 : firstRunning
  }, [checks])

  useEffect(() => {
    if (!canvasRef.current || particlesRef.current) return
    particlesRef.current = new BootParticleSystem(canvasRef.current)
    particlesRef.current.init()
    return () => particlesRef.current?.stop()
  }, [])

  // Cinematic flash lines — cycle through CINEMATIC_LINES every 400ms
  useEffect(() => {
    if (cinematicIdx >= CINEMATIC_LINES.length) return
    const id = setTimeout(() => {
      setCinematicIdx(i => i + 1)
    }, 400)
    return () => clearTimeout(id)
  }, [cinematicIdx])

  useEffect(() => {
    let cancelled = false
    const timers = []

    const appendLine = text => {
      setLines(prev => [...prev.slice(-6), text])
    }
    const setStep = (id, value, line) => {
      setChecks(prev => ({ ...prev, [id]: value }))
      if (line) appendLine(line)
    }

    setStep('launcher', 'ok', isElectron ? '> Electron supervisor linked' : '> Browser launch detected')

    const onBootPhase = event => {
      const detail = event.detail || {}
      const stepId = PHASE_TO_STEP[detail.phase]
      if (!stepId) return
      const status = detail.status === 'pending'
        ? 'running'
        : detail.status === 'degraded' || detail.status === 'fail'
        ? 'fail'
        : 'ok'
      setStep(stepId, status, `> ${detail.message || detail.phase}`)
      if (stepId === 'auth') setProgress(p => Math.max(p, status === 'ok' ? 78 : 68))
      if (stepId === 'websocket') setProgress(p => Math.max(p, 86))
      if (stepId === 'dashboard') setProgress(p => Math.max(p, 94))
    }
    window.addEventListener('nx:boot-phase', onBootPhase)

    if (isElectron) {
      window.ai.getLaunchStatus?.()
        .then(status => {
          if (cancelled) return
          if (status?.message) setLaunchMessage(status.message)
          if (status?.readiness?.ready || status?.readiness?.degraded) {
            setStep('launcher', 'ok', `> ${status.message || 'Launcher ready'}`)
          }
        })
        .catch(() => {})
      window.ai.onUiLoadStatus?.(status => {
        if (cancelled || !status?.message) return
        setLaunchMessage(status.message)
        appendLine(`> ${status.message}`)
      })
    }

    fetch('/health', { signal: AbortSignal.timeout(4500) })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`health ${r.status}`)))
      .then(data => {
        if (cancelled) return
        const pythonOk = !!(data.python_backend || data.python_ok || data.ai_backend)
        setStep('health', 'ok', pythonOk ? '> Node gateway and Python backend online' : '> Node gateway online; Python degraded')
        setProgress(p => Math.max(p, pythonOk ? 46 : 38))
      })
      .catch(err => {
        if (cancelled) return
        setStep('health', 'fail', `> Backend health delayed: ${err.message || 'timeout'}`)
        setProgress(p => Math.max(p, 30))
      })

    const storedToken = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
    fetch(`${API_URL}/agents`, {
      signal: AbortSignal.timeout(4500),
      headers: storedToken ? { Authorization: `Bearer ${storedToken}` } : {},
    })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`agents ${r.status}`)))
      .then(data => {
        if (cancelled) return
        const count = data?.agents?.length || data?.count || 0
        setAgentCount(count)
        setStep('agents', 'ok', `> Agent registry synchronized [${count || 'unknown'} agents]`)
        setProgress(p => Math.max(p, 62))
      })
      .catch(err => {
        if (cancelled) return
        setStep('agents', 'fail', `> Agent registry delayed: ${err.message || 'timeout'}`)
        setProgress(p => Math.max(p, 54))
      })

    ensureOperatorToken({ timeoutMs: 4500 })
      .then(token => {
        if (cancelled) return
        setStep('auth', token ? 'ok' : 'fail', token ? '> Secure operator token acquired' : '> Secure token unavailable')
        setProgress(p => Math.max(p, token ? 78 : 68))
      })

    timers.push(setTimeout(() => {
      if (cancelled) return
      setStep('dashboard', 'ok', '> Command center visual systems online')
      setProgress(100)
    }, isElectron ? 3000 : 2200))

    timers.push(setTimeout(() => {
      if (cancelled || completedRef.current) return
      completedRef.current = true
      onCompleteRef.current?.()
    }, isElectron ? 3800 : 2600))

    return () => {
      cancelled = true
      window.removeEventListener('nx:boot-phase', onBootPhase)
      timers.forEach(clearTimeout)
    }
  }, [isElectron])

  useEffect(() => {
    startedAtRef.current = Date.now()
    const t = setInterval(() => {
      const elapsed = Date.now() - startedAtRef.current
      setProgress(prev => {
        if (prev >= 96) return prev
        const floor = Math.min(92, 10 + Math.round(elapsed / 80))
        return Math.max(prev, floor)
      })
    }, 300)
    return () => clearInterval(t)
  }, [])

  return (
    <motion.div
      className="boot-sequence"
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      <canvas ref={canvasRef} className="boot-sequence__canvas" />
      <div className="boot-sequence__grid" />
      <div className="boot-sequence__stage">
        <div className="boot-eye" data-state={subState || 'boot'}>
          <div className="boot-eye__orbit boot-eye__orbit--one" />
          <div className="boot-eye__orbit boot-eye__orbit--two" />
          <div className="boot-eye__orbit boot-eye__orbit--three" />
          <div className="boot-eye__aperture" />
          <div className="boot-eye__iris">
            <div className="boot-eye__pupil" />
          </div>
          <div className="boot-eye__scan" />
        </div>

        <div className="boot-sequence__status">
          <div className="boot-sequence__eyebrow">COGNITIVE CORE STARTUP</div>
          <h1>AETERNUS NEXUS</h1>
          <p>{launchMessage}</p>
          <div className="boot-sequence__progress" aria-label="Boot progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="boot-sequence__meta">
            <span>{progress}%</span>
            <span>{agentCount === null ? 'agents syncing' : `${agentCount} agents indexed`}</span>
          </div>
        </div>

        <div className="boot-sequence__steps">
          {BOOT_STEPS.map((step, index) => {
            const status = statusForStep(step, checks)
            return (
              <div key={step.id} className={`boot-step boot-step--${status} ${index === activeIndex ? 'boot-step--active' : ''}`}>
                <span className="boot-step__dot" />
                <div>
                  <b>{step.label}</b>
                  <small>{step.detail}</small>
                </div>
              </div>
            )
          })}
        </div>

        <div className="boot-sequence__terminal">
          {lines.map((line, index) => (
            <motion.div
              key={`${line}-${index}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.18 }}
            >
              {line}
            </motion.div>
          ))}
        </div>

        {/* Cinematic flash line overlay */}
        <div className="boot-sequence__cinematic" aria-hidden="true">
          {CINEMATIC_LINES.slice(0, cinematicIdx).map((line, i) => (
            <div
              key={line}
              className="boot-sequence__cinematic-line"
              style={{ animationDelay: `${i * 0.12}s` }}
            >
              {line}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
