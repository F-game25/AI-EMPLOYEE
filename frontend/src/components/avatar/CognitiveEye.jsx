/**
 * CognitiveEye — the single system companion avatar.
 *
 * Works at any size: 400px on the dashboard, 32px in the toolbar.
 * The pupil follows the global mouse cursor with NO React state updates
 * (direct DOM ref mutation) → zero re-renders per frame → zero lag.
 *
 * Props:
 *   size       number   — diameter in px (default 400)
 *   mode       string   — 'dashboard' | 'toolbar' (affects max pupil travel)
 *   onClick    fn       — called on click (opens companion/chat)
 *   className  string
 *   style      object
 */
import { useEffect, useRef } from 'react'
import { useRouteTheme } from '../../theme/routeThemes'
import { subscribeGlobalMouse } from '../../hooks/useGlobalMouse'
import './CognitiveEye.css'

export default function CognitiveEye({
  size = 400,
  mode = 'dashboard',
  onClick,
  className = '',
  style,
}) {
  const theme = useRouteTheme()
  const wrapRef  = useRef(null)
  const pupilRef = useRef(null)
  const idSuffix = useRef(Math.random().toString(36).slice(2, 7))
  const id = idSuffix.current

  // Iris radius in SVG units (viewBox is -1 -1 2 2 → unit circle)
  const IRIS_R     = 0.72
  const PUPIL_R    = mode === 'toolbar' ? 0.22 : 0.18
  // Max distance the pupil center can move from the iris center (in SVG units)
  const MAX_TRAVEL = mode === 'toolbar' ? 0.30 : 0.38

  // Pupil tracking — direct DOM mutation, no state
  useEffect(() => {
    const el = pupilRef.current
    const wrap = wrapRef.current
    if (!el || !wrap) return

    const unsub = subscribeGlobalMouse((mx, my) => {
      const rect = wrap.getBoundingClientRect()
      const cx = rect.left + rect.width / 2
      const cy = rect.top  + rect.height / 2
      const dx = mx - cx
      const dy = my - cy
      const dist = Math.sqrt(dx * dx + dy * dy)
      // Convert screen pixels to SVG units (size px = 2 SVG units)
      const scale = 2 / size
      const rawX = dx * scale
      const rawY = dy * scale
      const rawDist = dist * scale
      const travel = Math.min(rawDist, MAX_TRAVEL)
      const angle = Math.atan2(rawY, rawX)
      const ox = rawDist > 0.001 ? (Math.cos(angle) * travel) : 0
      const oy = rawDist > 0.001 ? (Math.sin(angle) * travel) : 0
      el.setAttribute('transform', `translate(${ox.toFixed(4)}, ${oy.toFixed(4)})`)
    })
    return unsub
  }, [size, mode, MAX_TRAVEL])

  const iris  = theme?.iris  || '#E5C76B'
  const halo  = theme?.halo  || '#fbbf24'

  // Triangle glyph points (centered, pointing up)
  const triR = IRIS_R * 0.42
  const triPts = [
    [0, -triR],
    [triR * 0.86,  triR * 0.5],
    [-triR * 0.86, triR * 0.5],
  ].map(([x, y]) => `${x.toFixed(4)},${y.toFixed(4)}`).join(' ')

  const outerRingRx = IRIS_R * 1.30
  const outerRingRy = IRIS_R * 0.52
  const innerRingRx = IRIS_R * 1.15
  const innerRingRy = IRIS_R * 0.62

  return (
    <div
      ref={wrapRef}
      className={`ce-wrap ce-wrap--${mode} ${className}`}
      style={{ width: size, height: size, ...style }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label="Companion — click to open conversation"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick?.() }}
    >
      <svg
        viewBox="-1 -1 2 2"
        width={size}
        height={size}
        style={{ overflow: 'visible' }}
        aria-hidden="true"
      >
        <defs>
          {/* Iris fill gradient */}
          <radialGradient id={`ce-iris-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#fff8e7" stopOpacity="0.95" />
            <stop offset="28%"  stopColor={iris} />
            <stop offset="68%"  stopColor={iris} stopOpacity="0.75" />
            <stop offset="100%" stopColor="#1a1306" />
          </radialGradient>

          {/* Outer glow filter */}
          <filter id={`ce-glow-${id}`} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="0.06" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Specular highlight on cornea */}
          <radialGradient id={`ce-spec-${id}`} cx="35%" cy="28%" r="45%">
            <stop offset="0%"   stopColor="rgba(200,230,255,0.6)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>

          {/* Background deep glow */}
          <radialGradient id={`ce-bg-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor={halo} stopOpacity="0.12" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>

        {/* Layer 0 — ambient glow background */}
        <circle cx="0" cy="0" r="0.98" fill={`url(#ce-bg-${id})`} />

        {/* Layer 1 — outer orbital ring (CSS-animated) */}
        {mode === 'dashboard' && (
          <g className="ce-ring-outer">
            <ellipse cx="0" cy="0" rx={outerRingRx} ry={outerRingRy}
              fill="none" stroke={iris} strokeWidth="0.008" opacity="0.25" />
          </g>
        )}

        {/* Layer 2 — inner orbital ring (CSS-animated, opposite direction) */}
        {mode === 'dashboard' && (
          <g className="ce-ring-inner">
            <ellipse cx="0" cy="0" rx={innerRingRx} ry={innerRingRy}
              fill="none" stroke={halo} strokeWidth="0.006" opacity="0.18" />
          </g>
        )}

        {/* Layer 3 — iris fill */}
        <circle cx="0" cy="0" r={IRIS_R} fill={`url(#ce-iris-${id})`} />

        {/* Layer 4 — iris fiber lines (static radial spokes) */}
        {Array.from({ length: 16 }, (_, i) => {
          const a = (i / 16) * Math.PI * 2
          const cos = Math.cos(a)
          const sin = Math.sin(a)
          return (
            <line key={i}
              x1={(cos * 0.12).toFixed(4)} y1={(sin * 0.12).toFixed(4)}
              x2={(cos * IRIS_R).toFixed(4)} y2={(sin * IRIS_R).toFixed(4)}
              stroke={iris} strokeWidth="0.006" opacity="0.20"
            />
          )
        })}

        {/* Layer 5 — triangle glyph */}
        <polygon points={triPts}
          fill="none"
          stroke="#fff8dc"
          strokeWidth={mode === 'toolbar' ? 0.04 : 0.028}
          strokeLinejoin="round"
          opacity="0.88"
        />

        {/* Layer 6 — center dot */}
        <circle cx="0" cy="0" r={mode === 'toolbar' ? 0.055 : 0.038}
          fill="#fff8dc" opacity="0.92"
        />

        {/* Layer 7 — cornea specular */}
        <ellipse cx="-0.18" cy="-0.22" rx="0.30" ry="0.18"
          fill={`url(#ce-spec-${id})`}
          style={{ mixBlendMode: 'screen' }}
        />

        {/* Layer 8 — pupil (moved by rAF, DOM ref) */}
        <g ref={pupilRef}>
          <circle cx="0" cy="0" r={PUPIL_R}
            fill="#080810" opacity="0.94"
          />
          {/* Tiny highlight in pupil */}
          <circle cx={(-PUPIL_R * 0.32).toFixed(4)} cy={(-PUPIL_R * 0.32).toFixed(4)}
            r={(PUPIL_R * 0.22).toFixed(4)}
            fill="white" opacity="0.18"
          />
        </g>

        {/* Layer 9 — outer rim glow */}
        <circle cx="0" cy="0" r={IRIS_R}
          fill="none"
          stroke={halo}
          strokeWidth="0.022"
          opacity="0.50"
          filter={`url(#ce-glow-${id})`}
          className="ce-rim"
        />

        {/* Eyelid blink overlay */}
        <ellipse cx="0" cy="0" rx={IRIS_R + 0.02} ry={IRIS_R + 0.02}
          fill="#07080F"
          className="ce-eyelid"
          style={{ pointerEvents: 'none' }}
        />
      </svg>
    </div>
  )
}
