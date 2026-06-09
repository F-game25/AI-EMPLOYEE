/**
 * CognitiveEye — wraps the real Aeternus Nexus avatar engine (avatar-engine.js).
 *
 * Dashboard mode: full canvas engine — 19 orbital rings, iris fibers, scan beam,
 *   energy rays, particles, shockwave pulses, 6-state machine, cursor gaze tracking.
 * Toolbar mode: lightweight SVG matching the reference thumbnail (32px, no canvas cost).
 *
 * Props:
 *   size    number  — px diameter for dashboard canvas (default 560)
 *   mode    string  — 'dashboard' | 'toolbar'
 *   onClick fn      — pulse on click + optional callback
 *   className / style — pass-through
 */
import { useEffect, useId, useRef } from 'react'
import { avatarStateForVoicePhase, useVoiceStore } from '../../store/voiceStore'
import './CognitiveEye.css'

/* ── Engine bootstrap (once per page) ─────────────────────────────── */
let _enginePromise = null
function loadEngine() {
  if (_enginePromise) return _enginePromise
  _enginePromise = new Promise(resolve => {
    if (window.NX && typeof window.NX.init === 'function') { resolve(); return }
    const s = document.createElement('script')
    s.src = '/avatar-engine.js'
    s.onload = resolve
    s.onerror = resolve
    document.head.appendChild(s)
  })
  return _enginePromise
}

/* ── Gaze tracking — uses canvas rect for accurate eye-relative coords ─ */
let _gazeCanvas = null
function setupGaze(canvasEl) {
  _gazeCanvas = canvasEl
  if (window.__ceGazeInit) return
  window.__ceGazeInit = true
  window.addEventListener('mousemove', e => {
    if (!window.NX?.setGaze) return
    const canvas = _gazeCanvas
    if (!canvas) {
      // Fallback: very gentle screen-relative gaze
      window.NX.setGaze(
        (e.clientX / window.innerWidth  - 0.5) * 0.6,
        (e.clientY / window.innerHeight - 0.5) * 0.6,
      )
      return
    }
    const r = canvas.getBoundingClientRect()
    const cx = r.left + r.width  / 2
    const cy = r.top  + r.height / 2
    // Wider normalization divisor = gentler tracking; clamp to ±0.7 max
    const nx = Math.max(-0.7, Math.min(0.7, (e.clientX - cx) / (r.width  * 1.4)))
    const ny = Math.max(-0.7, Math.min(0.7, (e.clientY - cy) / (r.height * 1.4)))
    window.NX.setGaze(nx, ny)
  }, { passive: true })
  window.addEventListener('mouseleave', () => window.NX?.setGaze?.(0, 0))
}

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/* ══════════════════════════════════════════════════════════════════ */
export default function CognitiveEye({
  size = 560,
  mode = 'dashboard',
  onClick,
  className = '',
  style,
}) {
  const canvasRef = useRef(null)
  const wrapRef   = useRef(null)
  const voicePhase = useVoiceStore(state => state.phase)
  const audioLevel = useVoiceStore(state => state.audioLevel)
  const micLevel = useVoiceStore(state => state.micLevel)
  const isSpeaking = useVoiceStore(state => state.isSpeaking)

  useEffect(() => {
    if (mode !== 'dashboard') return

    let cancelled = false
    let onVisibility = null
    let cancelCleanup = null

    loadEngine().then(() => {
      if (cancelled || !window.NX?.init) return
      const wrap = wrapRef.current
      if (!wrap) return

      const initEngine = () => {
        if (cancelled) return
        const rect = wrap.getBoundingClientRect()
        const sz = Math.max(180, Math.min(rect.width || size, rect.height || size, 520))

        // Pin container size — engine reads this in resize() instead of window dimensions
        window.NX._containerSize = sz

        // perf-lite: disable glow on large/4K displays or reduced-motion
        const perfLite = prefersReducedMotion() || window.screen.width > 3440
        window.__avatarTweaks = {
          accentIdle: { hue: 43, sat: 0.88 },
          energy:  1.4,
          glow:    perfLite ? 0 : 1.0,
          density: 0.50,
          tracking: true,
          autocycle: false,
          perfLite,
        }

        window.NX.init(canvasRef.current)

        // Keep engine size in sync when container changes
        let roTimer = null
        const ro = new ResizeObserver(() => {
          clearTimeout(roTimer)
          roTimer = setTimeout(() => {
            const r = wrap.getBoundingClientRect()
            const s = Math.max(180, Math.min(r.width || size, r.height || size, 520))
            if (Math.abs(s - (window.NX._containerSize || 0)) > 4) {
              window.NX._containerSize = s
              window.dispatchEvent(new Event('resize'))
            }
          }, 120)
        })
        ro.observe(wrap)

        setupGaze(canvasRef.current)

        onVisibility = () => { if (window.NX) window.NX._paused = document.hidden }
        document.addEventListener('visibilitychange', onVisibility)

        // Store cleanup refs on the closure
        cancelCleanup = () => { ro.disconnect(); clearTimeout(roTimer) }
      }

      // Wait one rAF to ensure the container is fully laid out
      requestAnimationFrame(initEngine)
    })

    return () => {
      cancelled = true
      if (onVisibility) document.removeEventListener('visibilitychange', onVisibility)
      if (cancelCleanup) cancelCleanup()
    }
  }, [mode, size])

  useEffect(() => {
    if (mode !== 'dashboard') return undefined
    let timer = null
    const avatarState = avatarStateForVoicePhase(voicePhase)
    loadEngine().then(() => {
      window.NX?.setState?.(avatarState)
      if (avatarState === 'alert') {
        timer = setTimeout(() => {
          if (window.NX?.state === 'alert') window.NX.setState('idle')
        }, 1200)
      }
    })
    return () => {
      if (timer) clearTimeout(timer)
    }
  }, [mode, voicePhase])

  useEffect(() => {
    if (mode !== 'dashboard') return
    const level = prefersReducedMotion()
      ? 0
      : isSpeaking
        ? audioLevel
        : voicePhase === 'listening'
          ? micLevel * 0.45
          : 0
    window.NX?.setSpeakLevel?.(level)
  }, [audioLevel, isSpeaking, micLevel, mode, voicePhase])

  const handleClick = e => {
    window.NX?.pulse?.(1.1)
    onClick?.(e)
  }
  const handleEnter = () => window.NX?.setHover?.(true)
  const handleLeave = () => window.NX?.setHover?.(false)

  if (mode === 'toolbar') {
    return (
      <ToolbarEye
        size={size}
        onClick={handleClick}
        className={className}
        style={style}
      />
    )
  }

  return (
    <div
      ref={wrapRef}
      className={`ce-wrap ce-wrap--dashboard ${className}`}
      style={{ '--ce-size': `${size}px`, ...style }}
      onClick={handleClick}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      role="button"
      tabIndex={0}
      aria-label="Cognitive Core — click to open companion"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleClick(e) }}
    >
      <canvas ref={canvasRef} className="ce-canvas" />
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   ToolbarEye — 32px SVG matching the reference thumbnail exactly.
   Reference: viewBox 0 0 1200 800, center 600,400, iris r=230.
   All proportions derived from those reference coordinates.
══════════════════════════════════════════════════════════════════ */
function ToolbarEye({ size, onClick, className, style }) {
  const id = useId().replace(/:/g, '')
  const IRIS = 0.74
  const R1RX = IRIS * (320 / 230)
  const R1RY = IRIS * (90  / 230)
  const R2RX = IRIS * (290 / 230)
  const R2RY = IRIS * (150 / 230)
  const S  = IRIS
  const ty = (S * (-80 / 230)).toFixed(3)
  const by = (S * ( 52 / 230)).toFixed(3)
  const hw = (S * ( 68 / 230)).toFixed(3)
  const dy  = (S * (18 / 230)).toFixed(3)
  const dr  = Math.max(S * (9 / 230), 0.040).toFixed(3)

  return (
    <div
      className={`ce-wrap ce-wrap--toolbar ${className || ''}`}
      style={{ width: size, height: size, ...style }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label="Cognitive Core"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick?.(e) }}
    >
      <svg viewBox="-1 -1 2 2" width={size} height={size}
        style={{ display: 'block', overflow: 'visible' }} aria-hidden="true">
        <defs>
          <radialGradient id={`te-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#FFE89A" />
            <stop offset="35%"  stopColor="#E5C76B" />
            <stop offset="70%"  stopColor="#A87432" />
            <stop offset="100%" stopColor="#1a1306" />
          </radialGradient>
          <filter id={`tg-${id}`} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="0.06" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <circle cx="0" cy="0" r="0.95"
          fill="none" stroke="#E5C76B" strokeWidth="0.35" opacity="0.06" />

        <g className="ce-ring-outer">
          <ellipse cx="0" cy="0"
            rx={R1RX.toFixed(3)} ry={R1RY.toFixed(3)}
            fill="none" stroke="#E5C76B" strokeWidth="0.022" opacity="0.55" />
        </g>

        <g className="ce-ring-inner">
          <ellipse cx="0" cy="0"
            rx={R2RX.toFixed(3)} ry={R2RY.toFixed(3)}
            fill="none" stroke="#E5C76B" strokeWidth="0.018" opacity="0.38" />
        </g>

        <circle cx="0" cy="0" r={IRIS} fill={`url(#te-${id})`} />

        <circle cx="0" cy="0" r={IRIS}
          fill="none" stroke="#E5C76B" strokeWidth="0.024" opacity="0.92"
          filter={`url(#tg-${id})`} className="ce-rim" />

        <polygon
          points={`0,${ty} ${hw},${by} -${hw},${by}`}
          fill="none" stroke="#fff8dc" strokeWidth="0.050"
          strokeLinejoin="round" opacity="0.92"
        />

        <circle cx="0" cy={dy} r={dr} fill="#fff8dc" opacity="0.95" />
        <circle cx="0" cy="0" r="0.17" fill="#050508" opacity="0.90" />
      </svg>
    </div>
  )
}
