/* ─────────────────────────────────────────────────────────────────────────
 * MechanicalIris.jsx
 * ------------------
 * The cinematic iris — 9 stacked sub-layers inside a single SVG.
 * viewBox: -100 -100 200 200 (centered on origin).
 *
 *   1. Outer mechanical housing — 4 chamfered plates, hex bolts, vents
 *   2. Inner mechanical ring    — toroidal ring, 24 LED segments
 *   3. Aperture blades          — 8 camera blades, scaleY by pupilScale
 *   4. Reactor core background  — recessed dark disc
 *   5. Plasma core              — radial gradient + animated turbulence
 *   6. Energy ripples           — 3 expanding concentric rings
 *   7. Iris striations          — 64 radial fibers + 8 crypts
 *   8. Cornea (wet lens)        — Fresnel highlight + chromatic aberration
 *   9. Pupil + triangle sigil   — cat-eye slit, ▽ sigil, catchlight
 *
 * Filter IDs are all prefixed `mi-` to avoid collisions with other SVGs.
 *
 * Plasma noise animation: implemented via SMIL <animate> on the feTurbulence
 * baseFrequency attribute — CSS keyframes cannot reliably animate SVG filter
 * attributes across browsers, so SMIL is the correct primitive.
 * ──────────────────────────────────────────────────────────────────────── */

import { useId, useMemo } from 'react'

// ── Static geometry helpers ──────────────────────────────────────────────
const TAU = Math.PI * 2

function polar(r, deg) {
  const a = (deg * Math.PI) / 180
  return [Math.cos(a) * r, Math.sin(a) * r]
}

// 4 chamfered housing plates (NE / SE / SW / NW). Each is a closed path.
// Inner radius ~78, outer ~95, chamfered corners at the cardinal seams.
const HOUSING_PLATES = [
  { rot: -45, key: 'NE' },
  { rot: 45, key: 'SE' },
  { rot: 135, key: 'SW' },
  { rot: -135, key: 'NW' },
]
const HOUSING_PATH =
  'M -32 -78 L 32 -78 L 28 -82 L -28 -82 Z ' + // top chamfer strip
  'M -36 -94 L 36 -94 A 96 96 0 0 1 76 -36 L 80 -32 ' +
  'L 80 -28 L 78 -26 A 80 80 0 0 0 26 -76 L 22 -78 L -22 -78 ' +
  'A 80 80 0 0 0 -78 -26 L -80 -28 L -80 -32 L -76 -36 ' +
  'A 96 96 0 0 1 -36 -94 Z'

// 12 hex bolts — 3 per plate, positioned along the outer edge of each plate.
const BOLT_POSITIONS = [
  [0, -86], [-30, -82], [30, -82],   // NE plate (rotated -45° conceptually)
  [60, -60], [82, -30], [86, 0],     // SE
  [82, 30], [60, 60], [30, 82],      // SW
  [-30, 82], [-60, 60], [-82, 30],   // NW (continuation)
]

// Hex bolt path centered at origin, radius 1.8
const HEX_BOLT_D = (() => {
  const r = 1.8
  return Array.from({ length: 6 }, (_, i) => {
    const a = (i * 60 - 30) * Math.PI / 180
    return `${i === 0 ? 'M' : 'L'} ${(Math.cos(a) * r).toFixed(2)} ${(Math.sin(a) * r).toFixed(2)}`
  }).join(' ') + ' Z'
})()

// 8 panel seams — diagonal cuts between plates
const PANEL_SEAMS = Array.from({ length: 8 }, (_, i) => i * 45)

// 6 cooling vents on outer rim — short tangential slots
const COOLING_VENTS = [15, 75, 135, 195, 255, 315]

// 24 segment dividers on inner ring, every 15°
const SEG_DIVIDERS = Array.from({ length: 24 }, (_, i) => i * 15)

// Aperture blades: 8 blades, each rotated 45° apart
const BLADES = Array.from({ length: 8 }, (_, i) => i * 45)

// 64 radial striations (fibers) — varied opacity/width
const FIBERS = Array.from({ length: 64 }, (_, i) => {
  const angle = (i * 360) / 64
  // Pseudo-random but deterministic per index
  const seed = (Math.sin(i * 12.9898) * 43758.5453) % 1
  const r = (seed + 1) % 1
  return {
    angle,
    opacity: 0.3 + r * 0.55,
    width: 0.4 + r * 0.8,
  }
})

// 8 darker crypts at irregular angles
const CRYPTS = [12, 47, 88, 134, 178, 223, 271, 318]

// 3 concentric ripple rings, staggered start times
const RIPPLES = [
  { delay: '0s' },
  { delay: '-0.67s' },
  { delay: '-1.33s' },
]

export default function MechanicalIris({
  state = 'IDLE',
  pupilScale = 1,
  gazeX = 0,
  gazeY = 0,
  tokensRate = 0,
  gpuTemp = 0,
  gpuUsage = 0,
  size = 520,
}) {
  // Unique-per-instance id base for filter/gradient refs (collision-proof
  // when multiple irises mount, e.g. mini-eye + main-eye on same page).
  const rawId = useId()
  const uid = useMemo(() => `mi-${rawId.replace(/[^a-zA-Z0-9]/g, '')}`, [rawId])

  const stateLower = String(state || 'idle').toLowerCase()
  const clampedPupil = Math.max(0.55, Math.min(1.4, pupilScale))

  // State-driven visual knobs
  const plasmaOpacity = {
    idle: 0.75, listening: 0.85, thinking: 0.95, executing: 1, error: 0.95,
  }[stateLower] ?? 0.85
  const rippleOpacity = {
    idle: 0.5, listening: 0.6, thinking: 0.7, executing: 0.85, error: 0.7,
  }[stateLower] ?? 0.5
  const rippleDur = stateLower === 'executing' ? '1s' : '2s'

  // Outer iris translates ~2px max with gaze; pupil translates ~8px max.
  // gazeX/Y are expected in approximately [-1, 1] range (or px from hook).
  const outerTx = Math.max(-2, Math.min(2, gazeX * 2))
  const outerTy = Math.max(-2, Math.min(2, gazeY * 2))
  const pupilTx = Math.max(-8, Math.min(8, gazeX * 8))
  const pupilTy = Math.max(-8, Math.min(8, gazeY * 8))

  return (
    <svg
      className={`mi-root mi-root--${stateLower}`}
      viewBox="-100 -100 200 200"
      width={size}
      height={size}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      style={{
        // GPU usage warms the iris hue; gpuTemp adds a touch of redshift.
        '--iris-hue-rotate': `${Math.min(20, gpuTemp * 0.2)}deg`,
        '--iris-saturate': `${1 + Math.min(0.3, gpuUsage * 0.003)}`,
        filter: 'drop-shadow(0 0 18px rgba(251,191,36,0.25))',
      }}
    >
      <defs>
        {/* ── Plasma gradient ── */}
        <radialGradient id={`${uid}-plasma`} cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#fff4d6" stopOpacity="1" />
          <stop offset="28%"  stopColor="#fbbf24" stopOpacity="0.95" />
          <stop offset="58%"  stopColor="#f97316" stopOpacity="0.85" />
          <stop offset="82%"  stopColor="#dc2626" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#7f1d1d" stopOpacity="0" />
        </radialGradient>

        {/* ── Reactor core background (deep recessed bowl) ── */}
        <radialGradient id={`${uid}-bg`} cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#1a0800" />
          <stop offset="60%"  stopColor="#0a0400" />
          <stop offset="100%" stopColor="#000000" />
        </radialGradient>

        {/* ── Pupil gradient ── */}
        <radialGradient id={`${uid}-pupil`} cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#000000" />
          <stop offset="60%"  stopColor="#0d0010" />
          <stop offset="100%" stopColor="#1a0020" />
        </radialGradient>

        {/* ── Triangle sigil gradient ── */}
        <radialGradient id={`${uid}-tri`} cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#fff9e6" />
          <stop offset="55%"  stopColor="#fbbf24" />
          <stop offset="100%" stopColor="#92400e" />
        </radialGradient>

        {/* ── Inner ring (toroidal) gradient ── */}
        <radialGradient id={`${uid}-ring`} cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor="#1f2937" />
          <stop offset="80%"  stopColor="#0b1220" />
          <stop offset="100%" stopColor="#000" />
        </radialGradient>

        {/* ── Housing plate gradient (brushed steel) ── */}
        <linearGradient id={`${uid}-plate`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%"   stopColor="#4a5568" />
          <stop offset="45%"  stopColor="#2d3748" />
          <stop offset="100%" stopColor="#0f1419" />
        </linearGradient>

        {/* ── Fiber gradient (gold radial striation) ── */}
        <linearGradient id={`${uid}-fiber`} x1="0%" y1="50%" x2="100%" y2="50%">
          <stop offset="0%"   stopColor="#fbbf24" stopOpacity="0" />
          <stop offset="40%"  stopColor="#fbbf24" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#fef3c7" stopOpacity="0.9" />
        </linearGradient>

        {/* ── Cornea Fresnel highlight ── */}
        <radialGradient id={`${uid}-cornea`} cx="50%" cy="20%" r="60%">
          <stop offset="0%"   stopColor="rgba(140,215,255,0.92)" />
          <stop offset="60%"  stopColor="rgba(140,215,255,0.18)" />
          <stop offset="100%" stopColor="rgba(140,215,255,0)" />
        </radialGradient>

        {/* ── Brushed metal turbulence ── */}
        <filter id={`${uid}-brushed`} x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9 0.02" numOctaves="2" seed="3" />
          <feColorMatrix values="0 0 0 0 0.3   0 0 0 0 0.3   0 0 0 0 0.3   0 0 0 0.18 0" />
          <feComposite in2="SourceGraphic" operator="in" />
        </filter>

        {/* ── Plasma turbulence (animated via SMIL) ── */}
        <filter id={`${uid}-plasmanoise`} x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="7">
            <animate
              attributeName="baseFrequency"
              dur="4s"
              values="0.9;1.4;0.9"
              repeatCount="indefinite"
            />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" scale="3" />
        </filter>

        {/* ── Bloom (for plasma + triangle) ── */}
        <filter id={`${uid}-bloom`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* ── Soft inner glow (triangle sigil) ── */}
        <filter id={`${uid}-triglow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="g" />
          <feMerge>
            <feMergeNode in="g" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* ── Chromatic aberration (R shift +0.8 / B shift -0.8) ── */}
        <filter id={`${uid}-chroma`} x="-10%" y="-10%" width="120%" height="120%">
          <feColorMatrix
            in="SourceGraphic"
            type="matrix"
            values="1 0 0 0 0
                    0 0 0 0 0
                    0 0 0 0 0
                    0 0 0 1 0"
            result="r"
          />
          <feOffset in="r" dx="0.8" dy="0" result="rs" />
          <feColorMatrix
            in="SourceGraphic"
            type="matrix"
            values="0 0 0 0 0
                    0 1 0 0 0
                    0 0 0 0 0
                    0 0 0 1 0"
            result="g"
          />
          <feColorMatrix
            in="SourceGraphic"
            type="matrix"
            values="0 0 0 0 0
                    0 0 0 0 0
                    0 0 1 0 0
                    0 0 0 1 0"
            result="b"
          />
          <feOffset in="b" dx="-0.8" dy="0" result="bs" />
          <feBlend in="rs" in2="g" mode="screen" result="rg" />
          <feBlend in="rg" in2="bs" mode="screen" />
        </filter>

        {/* ── Lens dust microtexture ── */}
        <filter id={`${uid}-lensdust`} x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="2.4" numOctaves="1" seed="11" />
          <feDisplacementMap in="SourceGraphic" scale="0.6" />
        </filter>
      </defs>

      {/* ═══════════ OUTER IRIS (translates ~2px with gaze) ═══════════ */}
      <g transform={`translate(${outerTx.toFixed(2)} ${outerTy.toFixed(2)})`}>

        {/* ─── LAYER 1 — Outer mechanical housing ───────────────────── */}
        <g className="mi-housing">
          {HOUSING_PLATES.map((plate) => (
            <g key={plate.key} transform={`rotate(${plate.rot})`}>
              <path
                d={HOUSING_PATH}
                fill={`url(#${uid}-plate)`}
                stroke="#0a0e14"
                strokeWidth="0.6"
              />
              {/* Brushed metal overlay */}
              <path
                d={HOUSING_PATH}
                fill={`url(#${uid}-plate)`}
                filter={`url(#${uid}-brushed)`}
                opacity="0.6"
              />
            </g>
          ))}
          {/* 8 panel seams with chamfer highlight */}
          {PANEL_SEAMS.map((deg) => {
            const [x1, y1] = polar(78, deg)
            const [x2, y2] = polar(95, deg)
            return (
              <line
                key={`seam-${deg}`}
                x1={x1.toFixed(2)} y1={y1.toFixed(2)}
                x2={x2.toFixed(2)} y2={y2.toFixed(2)}
                stroke="#cbd5e1"
                strokeWidth="0.35"
                strokeOpacity="0.45"
              />
            )
          })}
          {/* 12 hex bolts */}
          {BOLT_POSITIONS.map(([x, y], i) => (
            <g key={`bolt-${i}`} transform={`translate(${x} ${y})`}>
              <path d={HEX_BOLT_D} fill="#1e293b" stroke="#475569" strokeWidth="0.25" />
              <circle r="0.4" fill="#94a3b8" />
            </g>
          ))}
          {/* 6 cooling vents on outer rim */}
          {COOLING_VENTS.map((deg) => {
            const [cx, cy] = polar(89, deg)
            return (
              <g
                key={`vent-${deg}`}
                transform={`translate(${cx.toFixed(2)} ${cy.toFixed(2)}) rotate(${deg + 90})`}
              >
                <rect x="-4" y="-0.7" width="8" height="1.4" rx="0.7"
                      fill="#000" stroke="#334155" strokeWidth="0.2" />
                <line x1="-3" y1="0" x2="3" y2="0" stroke="#0ea5e9"
                      strokeWidth="0.25" strokeOpacity="0.4" />
              </g>
            )
          })}
        </g>

        {/* ─── LAYER 2 — Inner mechanical ring (toroidal, 24 segments) ─ */}
        <g className="mi-segring">
          <circle r="68" fill="none" stroke={`url(#${uid}-ring)`} strokeWidth="6" />
          <circle r="68" fill="none" stroke="#0a0e14" strokeWidth="6.4" opacity="0.5" />
          {SEG_DIVIDERS.map((deg, i) => {
            const [x1, y1] = polar(65, deg)
            const [x2, y2] = polar(71, deg)
            // Deterministic ~30% glow
            const glow = ((Math.sin(i * 2.39) * 10000) % 1 + 1) % 1 < 0.3
            return (
              <g key={`seg-${deg}`}>
                <line
                  x1={x1.toFixed(2)} y1={y1.toFixed(2)}
                  x2={x2.toFixed(2)} y2={y2.toFixed(2)}
                  stroke="#1f2937" strokeWidth="0.6"
                />
                {glow && (
                  <circle
                    cx={((x1 + x2) / 2).toFixed(2)}
                    cy={((y1 + y2) / 2).toFixed(2)}
                    r="0.7"
                    fill="#fbbf24"
                    opacity="0.85"
                  >
                    <animate
                      attributeName="opacity"
                      values="0.4;0.95;0.4"
                      dur={`${2 + (i % 5) * 0.4}s`}
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            )
          })}
        </g>

        {/* ─── LAYER 3 — Aperture blades (8 camera blades) ───────────── */}
        <g
          className="mi-blades"
          transform={`scale(${clampedPupil.toFixed(3)})`}
          style={{ transition: 'transform 240ms cubic-bezier(.4,0,.2,1)' }}
        >
          {BLADES.map((deg) => (
            <g key={`blade-${deg}`} transform={`rotate(${deg})`}>
              <path
                d="M -22 -2 L 22 -10 L 60 -28 L 56 -8 L 16 6 L -8 4 Z"
                fill="#1a1f2e"
                stroke="#0a0e14"
                strokeWidth="0.4"
                opacity="0.85"
              />
              {/* Specular reflection band */}
              <path
                d="M 12 -8 L 52 -22 L 50 -18 L 14 -6 Z"
                fill="#fde68a"
                opacity="0.18"
              />
            </g>
          ))}
        </g>

        {/* ─── LAYER 4 — Reactor core background (recessed bowl) ─────── */}
        <g className="mi-corebg">
          <circle r="45" fill={`url(#${uid}-bg)`} />
          {/* 3-layer inset shadow stack */}
          <circle r="45" fill="none" stroke="#000" strokeWidth="1.4" opacity="0.85" />
          <circle r="43.5" fill="none" stroke="#1a0a00" strokeWidth="0.8" opacity="0.7" />
          <circle r="42" fill="none" stroke="#3a1f0a" strokeWidth="0.5" opacity="0.4" />
        </g>

        {/* ─── LAYER 5 — Plasma core ─────────────────────────────────── */}
        <g
          className={`mi-plasma mi-plasma--${stateLower}`}
          opacity={plasmaOpacity}
          filter={`url(#${uid}-bloom)`}
          style={{
            mixBlendMode: 'screen',
            filter: stateLower === 'error' ? 'hue-rotate(180deg)' : undefined,
          }}
        >
          <circle r="40" fill={`url(#${uid}-plasma)`} />
          {/* Noise displacement overlay */}
          <circle
            r="36"
            fill={`url(#${uid}-plasma)`}
            filter={`url(#${uid}-plasmanoise)`}
            opacity="0.55"
          />
          <animate
            attributeName="opacity"
            values={`${plasmaOpacity};${Math.min(1, plasmaOpacity + 0.08)};${plasmaOpacity}`}
            dur={stateLower === 'error' ? '0.2s' : '3.2s'}
            repeatCount="indefinite"
          />
        </g>

        {/* ─── LAYER 6 — Energy ripples (3 concentric expanding rings) ─ */}
        <g className="mi-ripples" style={{ mixBlendMode: 'screen' }}>
          {RIPPLES.map((ripple, i) => (
            <circle
              key={`ripple-${i}`}
              cx="0" cy="0"
              r="0"
              fill="none"
              stroke="#fbbf24"
              strokeWidth="0.8"
              opacity={rippleOpacity}
            >
              <animate
                attributeName="r"
                values="0;85"
                dur={rippleDur}
                begin={ripple.delay}
                repeatCount="indefinite"
              />
              <animate
                attributeName="opacity"
                values={`${rippleOpacity};0`}
                dur={rippleDur}
                begin={ripple.delay}
                repeatCount="indefinite"
              />
              <animate
                attributeName="stroke-width"
                values="1.2;0.2"
                dur={rippleDur}
                begin={ripple.delay}
                repeatCount="indefinite"
              />
            </circle>
          ))}
        </g>

        {/* ─── LAYER 7 — Iris striations (64 fibers + 8 crypts) ──────── */}
        <g
          className="mi-fibers"
          style={{
            filter: `hue-rotate(var(--iris-hue-rotate, 0deg)) saturate(var(--iris-saturate, 1))`,
          }}
        >
          {FIBERS.map((fiber, i) => {
            const [x1, y1] = polar(24, fiber.angle)
            const [x2, y2] = polar(68, fiber.angle)
            return (
              <line
                key={`fiber-${i}`}
                x1={x1.toFixed(2)} y1={y1.toFixed(2)}
                x2={x2.toFixed(2)} y2={y2.toFixed(2)}
                stroke={`url(#${uid}-fiber)`}
                strokeWidth={fiber.width.toFixed(2)}
                opacity={fiber.opacity.toFixed(2)}
              />
            )
          })}
          {CRYPTS.map((angle, i) => {
            const [x1, y1] = polar(26, angle)
            const [x2, y2] = polar(58, angle)
            return (
              <line
                key={`crypt-${i}`}
                x1={x1.toFixed(2)} y1={y1.toFixed(2)}
                x2={x2.toFixed(2)} y2={y2.toFixed(2)}
                stroke="#1a0a00"
                strokeWidth="2.2"
                opacity="0.55"
                strokeLinecap="round"
              />
            )
          })}
        </g>

        {/* ─── LAYER 8 — Cornea (wet lens) ──────────────────────────── */}
        <g
          className="mi-cornea"
          style={{ mixBlendMode: 'screen' }}
          filter={`url(#${uid}-lensdust)`}
        >
          {/* Soft cyan highlight on upper hemisphere */}
          <ellipse cx="0" cy="-18" rx="42" ry="26" fill={`url(#${uid}-cornea)`} />
          {/* Hard white Fresnel rim crescent at top */}
          <path
            d="M -30 -32 Q 0 -48 30 -32 Q 0 -38 -30 -32 Z"
            fill="#ffffff"
            opacity="0.55"
          />
          {/* Chromatic aberration ring at iris boundary */}
          <circle
            r="68"
            fill="none"
            stroke="#ffffff"
            strokeWidth="0.4"
            opacity="0.25"
            filter={`url(#${uid}-chroma)`}
          />
        </g>
      </g>

      {/* ═══════════ PUPIL GROUP (translates ~8px with gaze) ═══════════ */}
      <g transform={`translate(${pupilTx.toFixed(2)} ${pupilTy.toFixed(2)})`}>
        {/* ─── LAYER 9 — Pupil + triangle sigil ─────────────────────── */}
        <g
          className={`mi-pupil mi-pupil--${stateLower}`}
          transform={`scale(${clampedPupil.toFixed(3)})`}
          style={{ transition: 'transform 240ms cubic-bezier(.4,0,.2,1)' }}
        >
          {/* Cat-eye slit ellipse */}
          <ellipse cx="0" cy="0" rx="6" ry="14" fill={`url(#${uid}-pupil)`} />
          {/* ▽ triangle sigil (pointing down) */}
          <g filter={`url(#${uid}-triglow)`}>
            <path
              className="mi-tri"
              d="M -3.4 -2.6 L 3.4 -2.6 L 0 3.2 Z"
              fill={`url(#${uid}-tri)`}
              stroke="#fef3c7"
              strokeWidth="0.7"
              strokeLinejoin="round"
            >
              <animate
                attributeName="opacity"
                values="0.88;1;0.88"
                dur={stateLower === 'error' ? '0.2s' : '3.5s'}
                repeatCount="indefinite"
              />
            </path>
          </g>
          {/* Catchlight — upper-left specular highlight */}
          <circle cx="-2" cy="-6" r="1.6" fill="#ffffff" opacity="0.95" />
          {/* Secondary tiny catchlight */}
          <circle cx="-3" cy="-9" r="0.5" fill="#ffffff" opacity="0.7" />
        </g>
      </g>
    </svg>
  )
}
