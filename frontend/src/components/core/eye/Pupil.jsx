// Pupil.jsx — cat-eye slit + Pulse triangle pupil mark.
//
// Composition (back→front):
//   1. cat-eye slit (vertical lens shape, dark with recessed depth gradient)
//   2. Pulse triangle (▽ inverted) — radial gradient fill, strong glow filter
//   3. bright chromatic rim outline on the triangle
//   4. small white catchlight on the triangle's upper-left face
//
// Props:
//   pupilScale  dilation multiplier (default 1)
//   gaze        { x, y } offset for cursor tracking
//
// All triangle glow uses --eye-iris-color so the brand mark tints with route.

import React from 'react'

const SLIT_RX = 4.5     // narrow horizontal radius (cat slit)
const SLIT_RY = 11      // tall vertical radius
const TRI_SIZE = 7      // triangle inradius-ish

export default function Pupil({ pupilScale = 1, gaze = { x: 0, y: 0 } }) {
  const scale = pupilScale
  // Triangle: inverted (▽), point down. Path centered on (0,0).
  const triPts = [
    [-TRI_SIZE, -TRI_SIZE * 0.55],
    [TRI_SIZE,  -TRI_SIZE * 0.55],
    [0,          TRI_SIZE * 0.9],
  ]
  const triPath = `M ${triPts[0][0]},${triPts[0][1]} L ${triPts[1][0]},${triPts[1][1]} L ${triPts[2][0]},${triPts[2][1]} Z`
  const triPoints = triPts.map(([x, y]) => `${x},${y}`).join(' ')

  return (
    <g
      className="re-pupil"
      data-role="pupil"
      style={{ transform: `translate(${gaze.x}px, ${gaze.y}px) scale(${scale})` }}
    >
      <defs>
        {/* Slit depth gradient — recessed violet-black for depth */}
        <radialGradient id="pu-slit-grad" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%"   stopColor="#000000" />
          <stop offset="70%"  stopColor="#0d0010" />
          <stop offset="100%" stopColor="#1a0020" />
        </radialGradient>
        {/* Triangle: radial hot-center gradient */}
        <radialGradient id="pu-tri-grad" cx="50%" cy="35%" r="60%">
          <stop offset="0%"   stopColor="#fff9e6" stopOpacity="1" />
          <stop offset="45%"  stopColor="#fbbf24" stopOpacity="1" />
          <stop offset="100%" stopColor="#92400e" stopOpacity="1" />
        </radialGradient>
        {/* Triangle outer glow filter — blooms light outward */}
        <filter id="pu-triangle-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* 1. Cat-eye slit — dark recessed depth */}
      <ellipse
        cx="0" cy="0" rx={SLIT_RX} ry={SLIT_RY}
        fill="url(#pu-slit-grad)"
      />
      {/* Slit rim */}
      <ellipse
        cx="0" cy="0" rx={SLIT_RX + 0.2} ry={SLIT_RY + 0.2}
        fill="none"
        stroke="rgba(0,0,0,0.85)"
        strokeWidth="0.4"
      />

      {/* 2. Pulse triangle — glowing gradient fill with outer bloom */}
      <g className="pu-idle-pulse" filter="url(#pu-triangle-glow)">
        <polygon
          points={triPoints}
          fill="url(#pu-tri-grad)"
        />
      </g>

      {/* 3. Bright triangle rim — crisp brighter outline */}
      <polygon
        points={triPoints}
        fill="none"
        stroke="#fef3c7"
        strokeWidth="0.7"
        strokeLinejoin="round"
        opacity="0.9"
      />

      {/* 4. Catchlight on upper-left face */}
      <circle cx={-1.5} cy={-2.5} r="1.6" fill="white" opacity="0.95" />
    </g>
  )
}
