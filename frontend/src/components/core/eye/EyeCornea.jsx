// EyeCornea.jsx — glass dome on top of the iris.
//
// Renders inside the almond-scaled iris group. Uses mix-blend-mode: screen
// (via inline style on each highlight) so highlights add light without
// crushing iris detail underneath.
//
// Sub-layers (back→front):
//   1. cool teal/blue specular highlight on UPPER iris (strong key light)
//   2. smaller warm gold reflection on LOWER hemisphere (bounce)
//   3. hard white crescent rim on upper cornea edge (Fresnel reflection)
//   4. faint cyan crosshair lines through the center (1px, 20% opacity)
//   5. chromatic aberration rings at iris boundary (glass edge color fringe)

import React from 'react'

const IRIS_R = 53

export default function EyeCornea() {
  // Arc path helper — creates an arc stroke from startDeg→endDeg at radius r
  const arcPath = (r, startDeg, endDeg) => {
    const toRad = (d) => ((d - 90) * Math.PI) / 180
    const sx = r * Math.cos(toRad(startDeg))
    const sy = r * Math.sin(toRad(startDeg))
    const ex = r * Math.cos(toRad(endDeg))
    const ey = r * Math.sin(toRad(endDeg))
    const sweep = endDeg - startDeg
    const large = sweep > 180 ? 1 : 0
    return `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`
  }

  return (
    <g className="ec-cornea" aria-hidden="true" style={{ mixBlendMode: 'screen' }}>
      <defs>
        {/* Strong cool key-light highlight — upper left hemisphere */}
        <radialGradient id="ec-keyhi" cx="0.32" cy="0.22" r="0.52">
          <stop offset="0%"   stopColor="rgba(140,215,255,0.92)" />
          <stop offset="40%"  stopColor="rgba(80,180,255,0.55)" />
          <stop offset="100%" stopColor="rgba(80,180,255,0)" />
        </radialGradient>
        {/* Warm bounce light — lower hemisphere, more visible */}
        <radialGradient id="ec-bouncehi" cx="0.7" cy="0.85" r="0.38">
          <stop offset="0%"   stopColor="rgba(255,165,50,0.50)" />
          <stop offset="100%" stopColor="rgba(255,200,120,0)" />
        </radialGradient>
        {/* Crescent Fresnel rim — upper cornea edge */}
        <radialGradient id="ec-crescent" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%"   stopColor="rgba(255,255,255,0)" />
          <stop offset="92%"  stopColor="rgba(255,255,255,0)" />
          <stop offset="97%"  stopColor="rgba(255,255,255,0.85)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </radialGradient>
        <clipPath id="ec-iris-clip">
          <circle cx="0" cy="0" r={IRIS_R} />
        </clipPath>
        {/* Mask the crescent fill to only show on upper hemisphere */}
        <mask id="ec-upper-mask">
          <rect x="-60" y="-60" width="120" height="60" fill="white" />
        </mask>
        {/* Crescent rim path blur — Fresnel "wet lens" edge */}
        <filter id="ec-crescent-blur" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="0.8" />
        </filter>
        {/* Lens micro-texture — subtle displacement for dust/micro-imperfections */}
        <filter id="ec-lens-dust" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="turbulence" baseFrequency="0.9 0.4" numOctaves="2" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="0.5" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>

      <g clipPath="url(#ec-iris-clip)" filter="url(#ec-lens-dust)">
        {/* Strong cool teal/blue key-light highlight — covers upper 30°–150° */}
        <ellipse
          className="ec-spec-sweep"
          cx={-IRIS_R * 0.18}
          cy={-IRIS_R * 0.28}
          rx={IRIS_R * 0.56}
          ry={IRIS_R * 0.42}
          fill="url(#ec-keyhi)"
          style={{ mixBlendMode: 'screen' }}
        />
        {/* Warm gold bounce light — lower hemisphere, clearly visible */}
        <ellipse
          cx={IRIS_R * 0.22}
          cy={IRIS_R * 0.38}
          rx={IRIS_R * 0.30}
          ry={IRIS_R * 0.22}
          fill="url(#ec-bouncehi)"
          style={{ mixBlendMode: 'screen' }}
        />
        {/* Upper crescent fill (subtle ring shimmer) */}
        <circle
          cx="0" cy="0" r={IRIS_R - 0.5}
          fill="url(#ec-crescent)"
          mask="url(#ec-upper-mask)"
        />
      </g>

      {/* Hard crescent rim — "wet lens" Fresnel top edge, 20°→160° arc */}
      <path
        d={arcPath(IRIS_R - 1.5, 20, 160)}
        fill="none"
        stroke="rgba(255,255,255,0.88)"
        strokeWidth="1.5"
        strokeLinecap="round"
        filter="url(#ec-crescent-blur)"
      />

      {/* Chromatic aberration at iris boundary — glass edge color fringe */}
      <circle
        cx="0.8" cy="0"
        r={IRIS_R}
        fill="none"
        stroke="rgba(255,0,0,0.15)"
        strokeWidth="1.5"
      />
      <circle
        cx="-0.8" cy="0"
        r={IRIS_R}
        fill="none"
        stroke="rgba(0,0,255,0.15)"
        strokeWidth="1.5"
      />

      {/* Faint cyan crosshair — horizontal + vertical */}
      <g clipPath="url(#ec-iris-clip)">
        <line
          x1={-IRIS_R + 4} y1="0"
          x2={IRIS_R - 4}  y2="0"
          stroke="#22d3ee" strokeOpacity="0.2" strokeWidth="0.6"
        />
        <line
          x1="0" y1={-IRIS_R + 4}
          x2="0" y2={IRIS_R - 4}
          stroke="#22d3ee" strokeOpacity="0.2" strokeWidth="0.6"
        />
      </g>
    </g>
  )
}
