import { useEffect, useRef } from 'react'
import { subscribeGlobalMouse } from '../../hooks/useGlobalMouse'
import './CognitiveEye.css'

/**
 * CognitiveEye — single companion avatar component.
 * Design exactly matches the "Cognitive Core Avatar (standalone).html" reference:
 *   - Gold radial iris (#FFE89A → #E5C76B → #A87432 → #1a1306)
 *   - Gold iris rim stroke
 *   - Two flat orbital ellipses (ring1: rx/ry ≈ 1.39/0.39, ring2: ≈ 1.26/0.65)
 *   - Triangle glyph pointing up, center dot slightly below center
 *   - Black pupil that slides toward cursor (no React state — direct DOM ref)
 *
 * Props: size, mode ('dashboard'|'toolbar'), onClick, className, style
 */
export default function CognitiveEye({
  size = 400,
  mode = 'dashboard',
  onClick,
  className = '',
  style,
}) {
  const wrapRef  = useRef(null)
  const pupilRef = useRef(null)
  const id = useRef(Math.random().toString(36).slice(2, 7)).current

  // SVG unit space: viewBox "-1 -1 2 2", iris = unit circle (r=1)
  // These match the reference proportions: iris r=230, ring1 rx=320 ry=90, ring2 rx=290 ry=150
  const IRIS_R     = 0.74
  const RIM_W      = mode === 'toolbar' ? 0.022 : 0.013   // iris rim stroke width
  const RING1_RX   = IRIS_R * (320 / 230)                 // ≈ 1.031 → very flat
  const RING1_RY   = IRIS_R * (90 / 230)                  // ≈ 0.290
  const RING2_RX   = IRIS_R * (290 / 230)                 // ≈ 0.934
  const RING2_RY   = IRIS_R * (150 / 230)                 // ≈ 0.483
  const PUPIL_R    = mode === 'toolbar' ? 0.20 : 0.155
  const MAX_TRAVEL = mode === 'toolbar' ? 0.28 : 0.36

  // Triangle pointing up — reference: top (600,320), base corners (532,452) (668,452)
  // In unit space relative to iris r=230: top = -80/230, base_y = +52/230, half_w = 68/230
  const TRI_SCALE = IRIS_R / 1.0
  const triTopY   = TRI_SCALE * (-80 / 230)              // ≈ -0.257
  const triBaseY  = TRI_SCALE * ( 52 / 230)              // ≈ +0.168
  const triHalfW  = TRI_SCALE * ( 68 / 230)              // ≈ +0.219
  const triPts    = `0,${triTopY.toFixed(4)} ${triHalfW.toFixed(4)},${triBaseY.toFixed(4)} ${(-triHalfW).toFixed(4)},${triBaseY.toFixed(4)}`

  // Center dot — reference: 18px below center → 18/230 in unit coords
  const dotY = TRI_SCALE * (18 / 230)                    // ≈ +0.058
  const dotR = TRI_SCALE * (9 / 230)                     // ≈ 0.029
  // Clamp dotR to something visible at toolbar size
  const dotRFinal = mode === 'toolbar' ? Math.max(dotR, 0.042) : Math.max(dotR, 0.030)

  // Pupil tracking — zero React re-renders, direct SVG transform mutation
  useEffect(() => {
    const el   = pupilRef.current
    const wrap = wrapRef.current
    if (!el || !wrap) return

    const unsub = subscribeGlobalMouse((mx, my) => {
      const rect = wrap.getBoundingClientRect()
      const cx = rect.left + rect.width  / 2
      const cy = rect.top  + rect.height / 2
      const dx = mx - cx
      const dy = my - cy
      const dist = Math.sqrt(dx * dx + dy * dy)
      const scale = 2 / size                             // px → SVG units
      const rawDist = dist * scale
      const travel  = Math.min(rawDist, MAX_TRAVEL)
      const angle   = Math.atan2(dy, dx)
      const ox = rawDist > 0.001 ? Math.cos(angle) * travel : 0
      const oy = rawDist > 0.001 ? Math.sin(angle) * travel : 0
      el.setAttribute('transform', `translate(${ox.toFixed(4)},${oy.toFixed(4)})`)
    })
    return unsub
  }, [size, MAX_TRAVEL])

  return (
    <div
      ref={wrapRef}
      className={`ce-wrap ce-wrap--${mode} ${className}`}
      style={{ width: size, height: size, ...style }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label="Cognitive Core — click to open companion"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick?.() }}
    >
      <svg
        viewBox="-1 -1 2 2"
        width={size}
        height={size}
        style={{ overflow: 'visible', display: 'block' }}
        aria-hidden="true"
      >
        <defs>
          {/* Iris gradient — exact reference colors */}
          <radialGradient id={`ce-iris-${id}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="#FFE89A" />
            <stop offset="35%"  stopColor="#E5C76B" />
            <stop offset="70%"  stopColor="#A87432" />
            <stop offset="100%" stopColor="#1a1306" />
          </radialGradient>

          {/* Soft outer glow for rim */}
          <filter id={`ce-glow-${id}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.04" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Pupil inner shine */}
          <radialGradient id={`ce-pupil-${id}`} cx="38%" cy="32%" r="55%">
            <stop offset="0%"   stopColor="#1a1830" />
            <stop offset="100%" stopColor="#050508" />
          </radialGradient>
        </defs>

        {/* ── Ring 1 — wide flat orbit (reference: rx=320 ry=90 @ iris=230) ── */}
        <g className="ce-ring-outer">
          <ellipse
            cx="0" cy="0"
            rx={RING1_RX.toFixed(4)} ry={RING1_RY.toFixed(4)}
            fill="none"
            stroke="#E5C76B"
            strokeWidth={mode === 'toolbar' ? '0.018' : '0.010'}
            opacity={mode === 'toolbar' ? '0.55' : '0.50'}
          />
        </g>

        {/* ── Ring 2 — rounder inner orbit (reference: rx=290 ry=150 @ iris=230) ── */}
        <g className="ce-ring-inner">
          <ellipse
            cx="0" cy="0"
            rx={RING2_RX.toFixed(4)} ry={RING2_RY.toFixed(4)}
            fill="none"
            stroke="#E5C76B"
            strokeWidth={mode === 'toolbar' ? '0.015' : '0.008'}
            opacity={mode === 'toolbar' ? '0.40' : '0.35'}
          />
        </g>

        {/* ── Iris fill ── */}
        <circle
          cx="0" cy="0" r={IRIS_R}
          fill={`url(#ce-iris-${id})`}
        />

        {/* ── Iris rim stroke (reference: explicit gold stroke around iris circle) ── */}
        <circle
          cx="0" cy="0" r={IRIS_R}
          fill="none"
          stroke="#E5C76B"
          strokeWidth={RIM_W}
          opacity="0.90"
          filter={`url(#ce-glow-${id})`}
          className="ce-rim"
        />

        {/* ── Triangle glyph — pointing up, reference exact proportions ── */}
        <polygon
          points={triPts}
          fill="none"
          stroke="#fff8dc"
          strokeWidth={mode === 'toolbar' ? '0.045' : '0.026'}
          strokeLinejoin="round"
          opacity="0.92"
        />

        {/* ── Center dot — slightly below center per reference ── */}
        <circle
          cx="0" cy={dotY.toFixed(4)} r={dotRFinal.toFixed(4)}
          fill="#fff8dc"
          opacity="0.95"
        />

        {/* ── Pupil — black circle that slides toward cursor ── */}
        <g ref={pupilRef}>
          <circle
            cx="0" cy="0" r={PUPIL_R}
            fill={`url(#ce-pupil-${id})`}
          />
          {/* Tiny specular catch-light in pupil */}
          <ellipse
            cx={(-PUPIL_R * 0.28).toFixed(4)}
            cy={(-PUPIL_R * 0.30).toFixed(4)}
            rx={(PUPIL_R * 0.20).toFixed(4)}
            ry={(PUPIL_R * 0.14).toFixed(4)}
            fill="white" opacity="0.22"
          />
        </g>

        {/* ── Eyelid blink overlay (CSS-driven) ── */}
        <ellipse
          cx="0" cy="0"
          rx={IRIS_R + 0.015} ry={IRIS_R + 0.015}
          fill="#07080F"
          className="ce-eyelid"
          style={{ pointerEvents: 'none' }}
        />
      </svg>
    </div>
  )
}
