// IrisShutter.jsx — static 24-notch decorative bezel ring at radius 56.
//
// Originally a 6-blade animated camera aperture. Per redesign, the eye is
// no longer mechanical/animated at this layer — it's just a thin notched
// bezel ring sitting between the housing and the iris (~r=56).
//
// Props are accepted (aperture, hot) for backward compatibility but ignored.

import React from 'react'
import './IrisShutter.css'

const R_BEZEL   = 56
const N_NOTCHES = 24
const NOTCH_W   = 0.7
const NOTCH_H   = 2.4

export default function IrisShutter(/* { aperture, hot } */) {
  return (
    <g className="is-bezel" aria-hidden="true">
      <defs>
        <linearGradient id="is-bezel-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#3a3a3e" />
          <stop offset="55%"  stopColor="#1a1a1e" />
          <stop offset="100%" stopColor="#0a0a0e" />
        </linearGradient>
      </defs>
      {/* Base bezel ring */}
      <circle
        cx="0" cy="0" r={R_BEZEL}
        fill="none"
        stroke="url(#is-bezel-grad)"
        strokeWidth="2.2"
      />
      <circle
        cx="0" cy="0" r={R_BEZEL - 1.2}
        fill="none"
        stroke="rgba(0,0,0,0.65)"
        strokeWidth="0.4"
      />
      <circle
        cx="0" cy="0" r={R_BEZEL + 1.2}
        fill="none"
        stroke="rgba(255,255,255,0.08)"
        strokeWidth="0.3"
      />
      {/* 24 notch ticks */}
      {Array.from({ length: N_NOTCHES }).map((_, i) => {
        const a = (i / N_NOTCHES) * 360
        return (
          <g key={`notch-${i}`} transform={`rotate(${a})`}>
            <rect
              x={-NOTCH_W / 2}
              y={-(R_BEZEL + NOTCH_H / 2)}
              width={NOTCH_W}
              height={NOTCH_H}
              fill="rgba(0,0,0,0.85)"
            />
          </g>
        )
      })}
    </g>
  )
}
