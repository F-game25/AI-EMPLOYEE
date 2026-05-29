import { useMemo } from 'react'
import './EyeRays.css'

/**
 * EyeRays — 4 cardinal energy spokes + 8 diagonal secondaries.
 *
 *   • 4 primary spokes at N/S/E/W
 *     - length: 1.6 × iris radius (~85 px)
 *     - width:  4 px, gradient bright #fef3c7 center → --eye-halo-color → transparent
 *     - 4-point star pinpoint at the tip
 *   • 8 secondary diagonal spokes at 22.5°/67.5°/...
 *     - shorter (~70%), thinner (1.6 px), 40% opacity
 *
 * Halo color comes from --eye-halo-color (route-aware).
 *
 * Each layer respects prefers-reduced-motion via EyeRays.css.
 */

const IRIS_R = 53
const PRIMARY_LEN = IRIS_R * 1.6     // ~85
const SECOND_LEN  = PRIMARY_LEN * 0.7

const PRIMARY_ANGLES = [0, 90, 180, 270]
const SECOND_ANGLES  = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]

// 4-point star pinpoint at the tip of each primary spoke.
function StarTip({ size = 5 }) {
  const s = size
  return (
    <g className="er-startip">
      <polygon
        points={`0,-${s} ${s*0.25},0 0,${s} -${s*0.25},0`}
        fill="#fef3c7"
        opacity="0.95"
      />
      <polygon
        points={`-${s},0 0,-${s*0.25} ${s},0 0,${s*0.25}`}
        fill="#fef3c7"
        opacity="0.95"
      />
      <circle r={s * 0.45} fill="#fef3c7" opacity="0.7" />
    </g>
  )
}

// One spoke, pointing UP (negative Y), rotated by `angle`.
function Spoke({ angle, length, width, opacity, isPrimary }) {
  // Each spoke is a rectangle centered on x=0, extending from y=0 (inner) to y=-length.
  // Inner end starts just outside the iris dome (y ≈ -(IRIS_R + 2)).
  const innerY = -(IRIS_R + 2)
  const outerY = innerY - length
  return (
    <g transform={`rotate(${angle})`} className={`er-spoke ${isPrimary ? 'er-primary' : 'er-second'}`}>
      <rect
        x={-width / 2}
        y={outerY}
        width={width}
        height={length}
        fill="url(#er-spoke-grad)"
        opacity={opacity}
      />
      {isPrimary && (
        <g transform={`translate(0 ${outerY})`}>
          <StarTip size={5} />
        </g>
      )}
    </g>
  )
}

export default function EyeRays({ state = 'IDLE', flareIntensity = 0.5 }) {
  const groupStyle = useMemo(() => ({ '--er-flare': flareIntensity }), [flareIntensity])

  return (
    <g className={`er-rays er-state-${state}`} style={groupStyle}>
      <defs>
        {/* Spoke gradient: bright cream center → halo color → transparent tip.
            Y-axis runs along the spoke (0% = tip, 100% = inner end). */}
        <linearGradient id="er-spoke-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="rgba(254, 243, 199, 0)" />
          <stop offset="15%"  stopColor="rgba(254, 243, 199, 0.55)" />
          <stop offset="55%"  stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#fef3c7" stopOpacity="1" />
        </linearGradient>
      </defs>

      {/* Secondary diagonals — drawn first so primaries overlap them. */}
      <g className="er-second-group">
        {SECOND_ANGLES.map((a) => (
          <Spoke
            key={`sec-${a}`}
            angle={a}
            length={SECOND_LEN}
            width={1.6}
            opacity={0.4}
            isPrimary={false}
          />
        ))}
      </g>

      {/* Primaries — N/E/S/W with star pinpoints */}
      <g className="er-primary-group">
        {PRIMARY_ANGLES.map((a) => (
          <Spoke
            key={`pri-${a}`}
            angle={a}
            length={PRIMARY_LEN}
            width={4}
            opacity={0.95}
            isPrimary
          />
        ))}
      </g>
    </g>
  )
}
