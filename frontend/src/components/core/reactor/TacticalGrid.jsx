/**
 * TacticalGrid — Z3 radial polar grid with 24 spokes, 3 dashed rings,
 * and 4 cardinal coordinate labels. Slow rotation, labels held static.
 */
import { useMemo } from 'react'

export default function TacticalGrid() {
  const { spokes, rings } = useMemo(() => {
    const spokes = []
    for (let i = 0; i < 24; i++) {
      const angle = (i * 15) * Math.PI / 180
      const isCardinal = i % 6 === 0
      const r1 = isCardinal ? 80 : 200
      const r2 = 280
      const x1 = Math.cos(angle) * r1
      const y1 = Math.sin(angle) * r1
      const x2 = Math.cos(angle) * r2
      const y2 = Math.sin(angle) * r2
      spokes.push(
        <line
          key={`s${i}`}
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke="rgba(229,199,107,0.08)"
          strokeWidth={isCardinal ? 0.8 : 0.4}
        />
      )
    }
    const rings = [120, 180, 240].map(r => (
      <circle
        key={r}
        r={r}
        fill="none"
        stroke="rgba(229,199,107,0.06)"
        strokeWidth="0.5"
        strokeDasharray="3 4"
      />
    ))
    return { spokes, rings }
  }, [])

  const labels = [
    { x: 0,    y: -260, t: 'N 000' },
    { x: 260,  y: 0,    t: 'E 090' },
    { x: 0,    y: 260,  t: 'S 180' },
    { x: -260, y: 0,    t: 'W 270' },
  ]

  return (
    <svg
      viewBox="-300 -300 600 600"
      className="tg-grid"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      aria-hidden="true"
    >
      <g className="tg-rotor">
        {rings}
        {spokes}
      </g>
      {labels.map((l, i) => (
        <text
          key={i}
          x={l.x}
          y={l.y}
          fontSize="8"
          fontFamily="JetBrains Mono, monospace"
          fill="rgba(229,199,107,0.35)"
          textAnchor="middle"
          dominantBaseline="middle"
          letterSpacing="1.5"
        >
          {l.t}
        </text>
      ))}
      <style>{`
        .tg-grid .tg-rotor {
          transform-origin: center;
          transform-box: view-box;
          animation: tg-rotate 120s linear infinite;
          will-change: transform;
        }
        @keyframes tg-rotate {
          from { transform: rotate(0deg);   }
          to   { transform: rotate(360deg); }
        }
        @media (prefers-reduced-motion: reduce) {
          .tg-grid .tg-rotor { animation: none !important; }
        }
      `}</style>
    </svg>
  )
}
