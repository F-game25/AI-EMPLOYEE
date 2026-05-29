// EyeMechanical.jsx — 3-plate segmented housing (cinematic camera-body look).
//
// Three concentric brushed-steel rings (outer/mid/inner) split into 8/12/16
// panel-seam segments. Cool blue-grey reflection on the TOP half (sky/key
// light); warm gold reflection on the BOTTOM half (bounce light).
// Chamfered seam edges, hex bolt heads, and cooling vent slots on the outer
// plate give a machined-metal appearance.
//
// All def IDs prefixed `em-`. Geometry uses the host SVG viewBox -120..120.
//
// Props:
//   heatLevel (0..1) — fades a thin warm rim band when > 0.5

import React, { useMemo } from 'react'
import './EyeMechanical.css'

// Outer / middle / inner plate radii (mean) and widths
const PLATES = [
  { rMean: 110, width: 16, segments: 8,  seamStrength: 0.65 },
  { rMean: 92,  width: 12, segments: 12, seamStrength: 0.55 },
  { rMean: 76,  width: 8,  segments: 16, seamStrength: 0.45 },
]
const HEAT_INNER = 116
const HEAT_OUTER = 120

// Polar → cartesian. 0° = 12 o'clock, clockwise positive.
const polar = (r, deg) => {
  const rad = ((deg - 90) * Math.PI) / 180
  return [r * Math.cos(rad), r * Math.sin(rad)]
}

// Banded arc path (annular slice) from a0→a1 degrees.
const arcBand = (rInner, rOuter, a0, a1) => {
  const [x0o, y0o] = polar(rOuter, a0)
  const [x1o, y1o] = polar(rOuter, a1)
  const [x1i, y1i] = polar(rInner, a1)
  const [x0i, y0i] = polar(rInner, a0)
  let sweep = a1 - a0
  if (sweep < 0) sweep += 360
  const large = sweep > 180 ? 1 : 0
  return [
    `M ${x0o.toFixed(2)} ${y0o.toFixed(2)}`,
    `A ${rOuter} ${rOuter} 0 ${large} 1 ${x1o.toFixed(2)} ${y1o.toFixed(2)}`,
    `L ${x1i.toFixed(2)} ${y1i.toFixed(2)}`,
    `A ${rInner} ${rInner} 0 ${large} 0 ${x0i.toFixed(2)} ${y0i.toFixed(2)}`,
    'Z',
  ].join(' ')
}

// Hex bolt polygon centered at (cx, cy) with inradius r, rotated rot degrees.
const hexPoints = (cx, cy, r, rot = 0) => {
  return Array.from({ length: 6 }, (_, i) => {
    const a = ((i * 60 + rot - 90) * Math.PI) / 180
    return `${(cx + Math.cos(a) * r).toFixed(2)},${(cy + Math.sin(a) * r).toFixed(2)}`
  }).join(' ')
}

// Render a single segmented plate.
function Plate({ rMean, width, segments, seamStrength, idx }) {
  const rInner = rMean - width / 2
  const rOuter = rMean + width / 2
  const rMid   = rMean

  const seamAngles = useMemo(
    () => Array.from({ length: segments }, (_, i) => (i / segments) * 360),
    [segments]
  )

  // Bolt positions — 4 per plate, offset by plate index for variety.
  const boltAngles = useMemo(
    () => [0, 90, 180, 270].map(a => a + idx * 22.5),
    [idx]
  )

  return (
    <g className={`em-plate em-plate-${idx} em-plate-shimmer`}>
      {/* Base annulus — brushed steel */}
      <path
        d={arcBand(rInner, rOuter, 0, 360)}
        fill="#2a2a2e"
        stroke="rgba(0,0,0,0.55)"
        strokeWidth="0.4"
      />

      {/* Metal noise texture overlay */}
      <path
        d={arcBand(rInner, rOuter, 0, 360)}
        fill="#2a2a2e"
        filter="url(#em-noise)"
        opacity="0.04"
      />

      {/* Sky reflection arc — top (280°→80°, cool blue) */}
      <path
        d={arcBand(rInner + 0.6, rOuter - 0.6, 280, 80)}
        fill={`url(#em-plate-top-${idx})`}
        opacity="0.85"
      />
      {/* Warm bounce-light reflection — bottom (100°→260°) */}
      <path
        d={arcBand(rInner + 0.6, rOuter - 0.6, 100, 260)}
        fill={`url(#em-plate-bot-${idx})`}
        opacity="0.6"
      />

      {/* Brushed-metal cross-grain shading */}
      <path
        d={arcBand(rInner, rOuter, 0, 360)}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth="0.3"
      />

      {/* Panel seams with chamfer highlights */}
      <g className="em-seams">
        {seamAngles.map((a) => {
          const [x0, y0] = polar(rInner, a)
          const [x1, y1] = polar(rOuter, a)
          // Offset seam direction perpendicular for chamfer — rotate 90° scaled to 0.6px
          const rad = ((a - 90) * Math.PI) / 180
          const ox = Math.sin(rad) * 0.6   // perpendicular offset
          const oy = -Math.cos(rad) * 0.6
          return (
            <React.Fragment key={`seam-${idx}-${a}`}>
              {/* Primary dark seam */}
              <line
                x1={x0.toFixed(2)} y1={y0.toFixed(2)}
                x2={x1.toFixed(2)} y2={y1.toFixed(2)}
                stroke="rgba(0,0,0,0.78)"
                strokeWidth={seamStrength}
                strokeLinecap="round"
              />
              {/* Chamfer highlight — bright edge offset from seam */}
              <line
                x1={(x0 + ox).toFixed(2)} y1={(y0 + oy).toFixed(2)}
                x2={(x1 + ox).toFixed(2)} y2={(y1 + oy).toFixed(2)}
                stroke="#5a5a6a"
                strokeWidth="0.4"
                strokeLinecap="round"
                opacity="0.7"
              />
            </React.Fragment>
          )
        })}
      </g>

      {/* Hex bolt heads at cardinal junctions */}
      {boltAngles.map((a) => {
        const [bx, by] = polar(rMid, a)
        return (
          <polygon
            key={`bolt-${idx}-${a}`}
            points={hexPoints(bx, by, 2, a)}
            fill="#141420"
            stroke="#3a3a4e"
            strokeWidth="0.5"
          />
        )
      })}

      {/* Cooling vent slots — outer plate only (idx === 0) */}
      {idx === 0 && [0, 60, 120, 180, 240, 300].map((a) => {
        const rad = ((a - 90) * Math.PI) / 180
        const [vx, vy] = polar(rMid, a)
        return (
          <rect
            key={`vent-${a}`}
            x={vx - 0.5}
            y={vy - 2}
            width="1"
            height="4"
            fill="#0a0a12"
            opacity="0.6"
            transform={`rotate(${a}, ${vx.toFixed(2)}, ${vy.toFixed(2)})`}
          />
        )
      })}

      {/* Outer + inner rim micro-bevel */}
      <circle cx="0" cy="0" r={rOuter - 0.1} fill="none" stroke="rgba(0,0,0,0.6)" strokeWidth="0.25" />
      <circle cx="0" cy="0" r={rInner + 0.1} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="0.25" />
    </g>
  )
}

export default function EyeMechanical({ heatLevel = 0 }) {
  const heatActive = heatLevel > 0.5
  const heatOpacity = heatActive ? Math.min(1, (heatLevel - 0.5) * 2) : 0

  return (
    <g className="em-mechanical" aria-hidden="true">
      <defs>
        {/* Metal fractal noise filter for texture on plate surfaces */}
        <filter id="em-noise" x="0%" y="0%" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="4" result="noise" />
          <feColorMatrix type="saturate" values="0" in="noise" result="gray" />
          <feBlend in="SourceGraphic" in2="gray" mode="multiply" />
        </filter>

        {/* Cool top key-light + warm bottom bounce — one pair per plate */}
        {PLATES.map((_, i) => (
          <React.Fragment key={`grads-${i}`}>
            <linearGradient id={`em-plate-top-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="rgba(160, 190, 220, 0.55)" />
              <stop offset="55%"  stopColor="rgba(120, 150, 180, 0.22)" />
              <stop offset="100%" stopColor="rgba(80, 100, 130, 0)" />
            </linearGradient>
            <linearGradient id={`em-plate-bot-${i}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%"   stopColor="rgba(230, 175, 95, 0.55)" />
              <stop offset="55%"  stopColor="rgba(180, 130, 60, 0.22)" />
              <stop offset="100%" stopColor="rgba(120, 80, 30, 0)" />
            </linearGradient>
          </React.Fragment>
        ))}
        {/* Heat band */}
        <linearGradient id="em-heat-gradient" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="rgba(80,100,255,0)" />
          <stop offset="50%"  stopColor="rgba(160,90,220,0.25)" />
          <stop offset="100%" stopColor="rgba(255,80,60,0.4)" />
        </linearGradient>
      </defs>

      {PLATES.map((p, i) => (
        <Plate key={`plate-${i}`} idx={i} {...p} />
      ))}

      {heatActive && (
        <path
          className="em-heat-overlay"
          d={arcBand(HEAT_INNER, HEAT_OUTER, 280, 80)}
          fill="url(#em-heat-gradient)"
          style={{ opacity: heatOpacity }}
        />
      )}
    </g>
  )
}
