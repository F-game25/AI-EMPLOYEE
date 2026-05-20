// IrisStriations.jsx — 96-fiber vertical iris weave with anisotropic falloff.
//
// Drawn inside the iris in viewBox space (-120..120). Fibers run mostly
// vertical, gently curved to follow the dome of the iris, and fade out near
// the horizontal canthi (-X and +X) so the molten-amber rim reads cleanly.
//
// CSS var --eye-iris-color tints the fibers via stroke (multiplied by per-
// fiber opacity stops). A radial soft-edge mask shrinks the weave inside
// the iris radius and an elliptical anisotropic mask thins fibers near the
// 3 o'clock / 9 o'clock canthi.

import React, { useMemo } from 'react'
import './IrisStriations.css'

const N_FIBERS    = 96
const IRIS_R      = 52
const FIBER_TOP_Y = -50   // dome top inside iris
const FIBER_BOT_Y =  50   // dome bottom inside iris

// Cheap deterministic per-index jitter — same input always yields same output.
const rng = (seed) => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return x - Math.floor(x)
}

export default function IrisStriations() {
  const fibers = useMemo(() => {
    const out = []
    for (let i = 0; i < N_FIBERS; i++) {
      // Distribute horizontally across the iris diameter.
      const t = i / (N_FIBERS - 1)               // 0..1
      const x = -IRIS_R + t * (IRIS_R * 2)        // -IRIS_R..IRIS_R
      // Fiber is a cubic curve top→bottom, gently bowed outward to follow the dome.
      // Bow magnitude peaks for fibers at the center column, decreases at edges.
      const centerness = 1 - Math.abs(x) / IRIS_R // 1 at center, 0 at edges
      const bow = 4 * centerness                  // px lateral bulge
      const jit = (rng(i + 1) - 0.5) * 1.2        // ±0.6 px wobble per fiber
      const xMid = x + (x >= 0 ? bow : -bow) * 0.4 + jit
      // Vertical extent — clip slightly inside the iris dome.
      const yTopExtent = FIBER_TOP_Y * Math.sqrt(Math.max(0, 1 - (x / IRIS_R) ** 2))
      const yBotExtent = FIBER_BOT_Y * Math.sqrt(Math.max(0, 1 - (x / IRIS_R) ** 2))
      const d =
        `M ${x.toFixed(2)} ${yTopExtent.toFixed(2)} ` +
        `C ${xMid.toFixed(2)} ${(yTopExtent * 0.4).toFixed(2)}, ` +
        `${xMid.toFixed(2)} ${(yBotExtent * 0.4).toFixed(2)}, ` +
        `${x.toFixed(2)} ${yBotExtent.toFixed(2)}`
      // Anisotropic: fibers near horizontal canthi (|x|→IRIS_R) fade out.
      const aniso = Math.pow(centerness, 0.7)
      // Increased opacity range: 0.28–0.80 (was 0.18–0.50) for visible fiber texture.
      const opacity = (0.28 + rng(i + 50) * 0.52) * aniso
      out.push({ d, opacity: opacity.toFixed(3), key: `it-fib-${i}` })
    }
    return out
  }, [])

  // 8 dark radial crypts — angular offsets evenly spaced (was 3).
  const cryptAngles = useMemo(() => {
    return Array.from({ length: 8 }, (_, i) => (i / 8) * 360)
  }, [])

  return (
    <g
      className="it-striations"
      style={{ filter: 'hue-rotate(var(--is-hue-shift, 0deg))' }}
    >
      <defs>
        {/* 4-stop molten amber radial — bright cream core → rich amber → deep → bronze rim */}
        <radialGradient id="it-iris-base" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%"   stopColor="#fef9ec" />
          <stop offset="35%"  stopColor="#f59e0b" />
          <stop offset="70%"  stopColor="#b45309" />
          <stop offset="100%" stopColor="#78350f" />
        </radialGradient>

        {/* Inner glow: hot center subsurface scatter */}
        <radialGradient id="is-inner-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%"   stopColor="rgba(255,245,200,0.55)" />
          <stop offset="100%" stopColor="rgba(255,200,80,0)" />
        </radialGradient>

        {/* Soft blur for SSS ring */}
        <filter id="is-sss-blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" />
        </filter>

        {/* Soft circular clip keeps fibers off the iris rim */}
        <clipPath id="it-iris-clip">
          <circle cx="0" cy="0" r={IRIS_R - 1} />
        </clipPath>
        {/* Anisotropic overlay — fades fibers near horizontal canthi using
            a horizontal elliptical mask. Black at the canthi, white in the
            vertical column. Applied via <mask>. */}
        <mask id="it-aniso-mask" maskUnits="userSpaceOnUse">
          <rect x="-60" y="-60" width="120" height="120" fill="black" />
          <ellipse cx="0" cy="0" rx={IRIS_R * 0.55} ry={IRIS_R} fill="url(#it-aniso-gradient)" />
        </mask>
        <radialGradient id="it-aniso-gradient" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%"   stopColor="white"  stopOpacity="1" />
          <stop offset="65%"  stopColor="white"  stopOpacity="0.85" />
          <stop offset="100%" stopColor="black"  stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Fiber weave — the iris base circle is painted by the parent RoboticEye */}
      <g clipPath="url(#it-iris-clip)" mask="url(#it-aniso-mask)">
        {fibers.map((f) => (
          <path
            key={f.key}
            d={f.d}
            fill="none"
            stroke="var(--eye-iris-color, #fbbf24)"
            strokeWidth="0.55"
            strokeLinecap="round"
            opacity={f.opacity}
          />
        ))}
      </g>

      {/* Sub-surface scatter ring — simulates light diffusing through iris tissue */}
      <circle
        cx="0" cy="0"
        r={IRIS_R * 0.62}
        stroke="#f59e0b"
        strokeWidth="2.5"
        fill="none"
        opacity="0.35"
        filter="url(#is-sss-blur)"
        clipPath="url(#it-iris-clip)"
      />

      {/* Inner glow overlay — hot molten core */}
      <circle
        cx="0" cy="0"
        r={IRIS_R * 0.4}
        fill="url(#is-inner-glow)"
        style={{ mixBlendMode: 'screen' }}
        clipPath="url(#it-iris-clip)"
      />

      {/* Dark concentric crypts — 8 radial grooves for tissue depth */}
      <g clipPath="url(#it-iris-clip)" fill="none">
        {cryptAngles.map((a) => {
          const rad = ((a - 90) * Math.PI) / 180
          const x1 = (Math.cos(rad) * IRIS_R * 0.18).toFixed(2)
          const y1 = (Math.sin(rad) * IRIS_R * 0.18).toFixed(2)
          const x2 = (Math.cos(rad) * (IRIS_R - 2)).toFixed(2)
          const y2 = (Math.sin(rad) * (IRIS_R - 2)).toFixed(2)
          return (
            <line
              key={`crypt-${a}`}
              x1={x1} y1={y1}
              x2={x2} y2={y2}
              stroke="#451a03"
              strokeWidth="2.5"
              strokeLinecap="round"
              opacity="0.4"
            />
          )
        })}
        {/* Additional thin concentric rings for subtle layering */}
        <circle cx="0" cy="0" r="18" stroke="rgba(0,0,0,0.22)" strokeWidth="0.4" />
        <circle cx="0" cy="0" r="32" stroke="rgba(0,0,0,0.22)" strokeWidth="0.4" />
        <circle cx="0" cy="0" r="44" stroke="rgba(0,0,0,0.22)" strokeWidth="0.4" />
      </g>
    </g>
  )
}
