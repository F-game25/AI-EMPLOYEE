/**
 * CognitiveEye — wraps the real Aeternus Nexus avatar engine (avatar-engine.js).
 *
 * Dashboard mode: full canvas engine — 19 orbital rings, iris fibers, scan beam,
 *   energy rays, particles, shockwave pulses, 6-state machine, cursor gaze tracking.
 * Toolbar mode: lightweight SVG matching the reference thumbnail (32px, no canvas cost).
 *
 * Props:
 *   size    number  — px diameter for dashboard canvas (default 420)
 *   mode    string  — 'dashboard' | 'toolbar'
 *   onClick fn      — pulse on click + optional callback
 *   className / style — pass-through
 */
import { useEffect, useRef } from 'react'
import './CognitiveEye.css'

/* ── Engine bootstrap (once per page) ─────────────────────────────── */
let _enginePromise = null
function loadEngine() {
  if (_enginePromise) return _enginePromise
  _enginePromise = new Promise(resolve => {
    if (window.NX && typeof window.NX.init === 'function') { resolve(); return }
    const s = document.createElement('script')
    // Vite serves public/ files at root; we copy the engine there in vite.config
    // Fallback: use the module-relative URL that Vite resolves at build time
    s.src = '/avatar-engine.js'
    s.onload = resolve
    s.onerror = resolve   // resolve even on error so we don't hang
    document.head.appendChild(s)
  })
  return _enginePromise
}

/* ── Shared global mouse → NX.setGaze ─────────────────────────────── */
function setupGaze() {
  if (window.__ceGazeInit) return
  window.__ceGazeInit = true
  window.addEventListener('mousemove', e => {
    if (!window.NX?.setGaze) return
    window.NX.setGaze(
      (e.clientX / window.innerWidth  - 0.5) * 2,
      (e.clientY / window.innerHeight - 0.5) * 2,
    )
  }, { passive: true })
  window.addEventListener('mouseleave', () => window.NX?.setGaze?.(0, 0))
}

/* ══════════════════════════════════════════════════════════════════ */
export default function CognitiveEye({
  size = 420,
  mode = 'dashboard',
  onClick,
  className = '',
  style,
}) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (mode !== 'dashboard') return

    let cancelled = false
    loadEngine().then(() => {
      if (cancelled || !window.NX?.init) return
      const canvas = canvasRef.current
      if (!canvas) return

      // Seed tweaks before init so first frame looks right
      window.__avatarTweaks = {
        accentIdle: { hue: 43, sat: 0.88 },
        energy:  1.8,
        glow:    1.8,
        density: 0.45,
        tracking: true,
        autocycle: false,
      }

      window.NX.init(canvas)

      setupGaze()
    })

    return () => { cancelled = true }
  }, [mode, size])

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
      className={`ce-wrap ce-wrap--dashboard ${className}`}
      style={{ width: size, height: size, ...style }}
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
  const id = useRef(Math.random().toString(36).slice(2, 6)).current
  const IRIS = 0.74
  // Reference ring proportions
  const R1RX = IRIS * (320 / 230)   // 1.031
  const R1RY = IRIS * (90  / 230)   // 0.290 — very flat
  const R2RX = IRIS * (290 / 230)   // 0.934
  const R2RY = IRIS * (150 / 230)   // 0.483
  // Triangle: top at -80/230, base at +52/230, halfW 68/230 (all * IRIS)
  const S  = IRIS
  const ty = (S * (-80 / 230)).toFixed(3)
  const by = (S * ( 52 / 230)).toFixed(3)
  const hw = (S * ( 68 / 230)).toFixed(3)
  // Center dot: 18px below center in reference space
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

        {/* Outer atmosphere glow */}
        <circle cx="0" cy="0" r="0.95"
          fill="none" stroke="#E5C76B" strokeWidth="0.35" opacity="0.06" />

        {/* Ring 1 — wide flat orbit */}
        <g className="ce-ring-outer">
          <ellipse cx="0" cy="0"
            rx={R1RX.toFixed(3)} ry={R1RY.toFixed(3)}
            fill="none" stroke="#E5C76B" strokeWidth="0.022" opacity="0.55" />
        </g>

        {/* Ring 2 — rounder inner orbit */}
        <g className="ce-ring-inner">
          <ellipse cx="0" cy="0"
            rx={R2RX.toFixed(3)} ry={R2RY.toFixed(3)}
            fill="none" stroke="#E5C76B" strokeWidth="0.018" opacity="0.38" />
        </g>

        {/* Iris fill */}
        <circle cx="0" cy="0" r={IRIS} fill={`url(#te-${id})`} />

        {/* Iris rim glow */}
        <circle cx="0" cy="0" r={IRIS}
          fill="none" stroke="#E5C76B" strokeWidth="0.024" opacity="0.92"
          filter={`url(#tg-${id})`} className="ce-rim" />

        {/* Triangle glyph */}
        <polygon
          points={`0,${ty} ${hw},${by} -${hw},${by}`}
          fill="none" stroke="#fff8dc" strokeWidth="0.050"
          strokeLinejoin="round" opacity="0.92"
        />

        {/* Center dot — slightly below center per reference */}
        <circle cx="0" cy={dy} r={dr} fill="#fff8dc" opacity="0.95" />

        {/* Static pupil */}
        <circle cx="0" cy="0" r="0.17" fill="#050508" opacity="0.90" />
      </svg>
    </div>
  )
}

/* Public API passthrough */
export const setAvatarState = name  => window.NX?.setState?.(name)
export const pulseAvatar    = (s=1) => window.NX?.pulse?.(s)
