// EyeAtmosphere.jsx — orb-grid wireframe + drifting particle field.
//
// Three sub-layers (back→front):
//   1. orb-grid: 48 radial meridian lines + a few parallels (sphere wireframe)
//   2. particles: 130 small circles in concentric arcs (90 gold + 30 cyan + 10 bright stars)
//   3. flare streaks: subtle cardinal flare hints (drawn here so they sit
//      under the spokes rendered by EyeRays)
//
// Everything respects --eye-halo-color so a route change re-tints the field.

import React, { useMemo } from 'react'

const ORB_R          = 110   // wireframe radius
const N_MERIDIANS    = 48
const N_GOLD         = 90    // was 60
const N_CYAN         = 30    // was 20
const N_STARS        = 10    // bright star particles
const N_PARTICLES    = N_GOLD + N_CYAN  // 120 base particles
const PARALLELS_Y    = [-66, -33, 0, 33, 66]

const rng = (seed) => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return x - Math.floor(x)
}

export default function EyeAtmosphere() {
  // ── Meridian lines ───────────────────────────────────────────
  const meridians = useMemo(() => {
    const out = []
    for (let i = 0; i < N_MERIDIANS; i++) {
      const a = (i / N_MERIDIANS) * 360
      const rad = ((a - 90) * Math.PI) / 180
      out.push({
        x2: (Math.cos(rad) * ORB_R).toFixed(2),
        y2: (Math.sin(rad) * ORB_R).toFixed(2),
        key: `mer-${i}`,
      })
    }
    return out
  }, [])

  // ── Parallels (horizontal arcs on the sphere) ────────────────
  const parallels = useMemo(
    () =>
      PARALLELS_Y.map((y) => {
        const rx = Math.sqrt(Math.max(0, ORB_R * ORB_R - y * y))
        return { y, rx, key: `par-${y}` }
      }),
    [],
  )

  // ── Base particles (gold + cyan) ─────────────────────────────
  const particles = useMemo(() => {
    const out = []
    for (let i = 0; i < N_PARTICLES; i++) {
      const angle = rng(i + 1) * Math.PI * 2
      const radius = 95 + rng(i + 30) * 35   // 95..130 concentric ring
      const size = 0.6 + rng(i + 60) * 0.8   // 0.6..1.4 px
      // Wider duration range per particle index: 12s–35s
      const speed = 14 + (i * 0.27) % 20
      const delay = rng(i + 120) * 8
      const isCyan = i >= N_GOLD
      out.push({
        cx: (Math.cos(angle) * radius).toFixed(2),
        cy: (Math.sin(angle) * radius).toFixed(2),
        r: size.toFixed(2),
        fill: isCyan ? '#22d3ee' : 'var(--eye-halo-color, #fbbf24)',
        opacity: (0.35 + rng(i + 150) * 0.45).toFixed(2),
        animDur: `${speed.toFixed(1)}s`,
        animDelay: `${delay.toFixed(1)}s`,
        key: `part-${i}`,
      })
    }
    return out
  }, [])

  // ── Bright star particles ─────────────────────────────────────
  // Larger, with stronger blur — simulate foreground bright specks
  const stars = useMemo(() => {
    const out = []
    for (let i = 0; i < N_STARS; i++) {
      const angle = rng(i + 200) * Math.PI * 2
      const radius = 95 + rng(i + 210) * 55   // 95..150 — slightly wider spread
      const size = 1.6 + rng(i + 220) * 0.4   // 1.6..2.0 px
      const speed = 18 + (i * 0.27) % 15
      const delay = rng(i + 230) * 10
      out.push({
        cx: (Math.cos(angle) * radius).toFixed(2),
        cy: (Math.sin(angle) * radius).toFixed(2),
        r: size.toFixed(2),
        opacity: (0.7 + rng(i + 240) * 0.3).toFixed(2),
        animDur: `${speed.toFixed(1)}s`,
        animDelay: `${delay.toFixed(1)}s`,
        key: `star-${i}`,
      })
    }
    return out
  }, [])

  return (
    <g className="ea-atmosphere" aria-hidden="true">
      <defs>
        {/* Strong blur for star particles */}
        <filter id="ea-star-blur" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="2.5" />
        </filter>
      </defs>

      {/* ── Orb-grid wireframe ──────────────────────────────── */}
      <g className="ea-grid" opacity="0.08">
        {meridians.map((m) => (
          <line
            key={m.key}
            x1="0" y1="0"
            x2={m.x2} y2={m.y2}
            stroke="var(--eye-halo-color, #fbbf24)"
            strokeWidth="0.5"
          />
        ))}
        {parallels.map((p) => (
          <ellipse
            key={p.key}
            cx="0" cy={p.y}
            rx={p.rx} ry={p.rx * 0.18}
            fill="none"
            stroke="var(--eye-halo-color, #fbbf24)"
            strokeWidth="0.5"
          />
        ))}
        {/* Sphere outline */}
        <circle
          cx="0" cy="0" r={ORB_R}
          fill="none"
          stroke="var(--eye-halo-color, #fbbf24)"
          strokeWidth="0.5"
        />
      </g>

      {/* ── Base particle field ──────────────────────────────── */}
      <g className="ea-particles">
        {particles.map((p) => (
          <circle
            key={p.key}
            cx={p.cx} cy={p.cy} r={p.r}
            fill={p.fill}
            opacity={p.opacity}
            style={{
              animation: `ea-drift ${p.animDur} ease-in-out ${p.animDelay} infinite alternate`,
            }}
          />
        ))}
      </g>

      {/* ── Bright star particles — blurred foreground specks ── */}
      <g className="ea-stars" filter="url(#ea-star-blur)">
        {stars.map((s) => (
          <circle
            key={s.key}
            cx={s.cx} cy={s.cy} r={s.r}
            fill="var(--eye-halo-color, #fbbf24)"
            opacity={s.opacity}
            style={{
              animation: `ea-drift ${s.animDur} ease-in-out ${s.animDelay} infinite alternate`,
            }}
          />
        ))}
      </g>

      {/* Inline keyframes — kept here so the file is fully self-contained.
          Reduced-motion override comes from RoboticEye.css. */}
      <style>{`
        @keyframes ea-drift {
          0%   { transform: translate(0, 0); }
          100% { transform: translate(2px, -3px); }
        }
        @media (prefers-reduced-motion: reduce) {
          .ea-particles circle,
          .ea-stars circle { animation: none !important; }
        }
      `}</style>
    </g>
  )
}
