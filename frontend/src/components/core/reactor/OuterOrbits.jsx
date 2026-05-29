/**
 * OuterOrbits — Z4 eight concentric counter-rotating orbital rings.
 * Mix of solid / dashed / broken (arc) rings, periods 30s..180s.
 * State boosts opacity (executing) or shifts hue (error).
 */
import { useMemo } from 'react'

const RINGS = [
  { r: 140, type: 'solid',  thickness: 0.6, period: 30,  dir: 'cw',  opacity: 0.18 },
  { r: 158, type: 'dashed', thickness: 0.4, period: 47,  dir: 'ccw', opacity: 0.22, dash: '4 8'  },
  { r: 175, type: 'broken', thickness: 0.8, period: 65,  dir: 'cw',  opacity: 0.30 },
  { r: 195, type: 'solid',  thickness: 1.0, period: 90,  dir: 'ccw', opacity: 0.35 },
  { r: 220, type: 'dashed', thickness: 0.5, period: 110, dir: 'cw',  opacity: 0.25, dash: '2 6'  },
  { r: 245, type: 'broken', thickness: 1.2, period: 130, dir: 'ccw', opacity: 0.40 },
  { r: 268, type: 'dashed', thickness: 0.4, period: 150, dir: 'cw',  opacity: 0.18, dash: '6 10' },
  { r: 290, type: 'solid',  thickness: 0.6, period: 180, dir: 'ccw', opacity: 0.30 },
]

// Build an SVG arc path between two angles (degrees) on a circle of radius r.
function arcPath(r, startDeg, endDeg) {
  const s = startDeg * Math.PI / 180
  const e = endDeg   * Math.PI / 180
  const x1 = Math.cos(s) * r, y1 = Math.sin(s) * r
  const x2 = Math.cos(e) * r, y2 = Math.sin(e) * r
  const large = (endDeg - startDeg) > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
}

function brokenArcs(r, gapCount) {
  // gapCount = 1 -> single 30° gap; 2 -> two 20° gaps
  if (gapCount === 1) {
    return [arcPath(r, 15, 345)]
  }
  // two arcs of 160° each with two 20° gaps
  return [arcPath(r, 10, 170), arcPath(r, 190, 350)]
}

export default function OuterOrbits({ state = 'idle' }) {
  const s = String(state).toLowerCase()
  const boost = s === 'executing' ? 1.4 : 1.0
  const errorTint = s === 'error'

  const elements = useMemo(() => RINGS.map((cfg, i) => {
    const op = Math.min(0.8, cfg.opacity * boost)
    const stroke = `rgba(229,199,107,${op.toFixed(3)})`
    const cls = `oo-ring oo-${cfg.dir}-${cfg.period}`

    if (cfg.type === 'solid') {
      return (
        <circle
          key={i}
          className={cls}
          r={cfg.r}
          fill="none"
          stroke={stroke}
          strokeWidth={cfg.thickness}
        />
      )
    }
    if (cfg.type === 'dashed') {
      return (
        <circle
          key={i}
          className={cls}
          r={cfg.r}
          fill="none"
          stroke={stroke}
          strokeWidth={cfg.thickness}
          strokeDasharray={cfg.dash}
        />
      )
    }
    // broken
    const gapCount = i === 2 ? 1 : 2
    const paths = brokenArcs(cfg.r, gapCount)
    return (
      <g key={i} className={cls}>
        {paths.map((d, j) => (
          <path
            key={j}
            d={d}
            fill="none"
            stroke={stroke}
            strokeWidth={cfg.thickness}
            strokeLinecap="round"
          />
        ))}
      </g>
    )
  }), [boost])

  // Generate per-period keyframes once.
  const keyframes = useMemo(() => {
    const periods = [...new Set(RINGS.map(r => r.period))]
    const blocks = periods.flatMap(p => ([
      `@keyframes oo-spin-cw-${p}  { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`,
      `@keyframes oo-spin-ccw-${p} { from { transform: rotate(0deg); } to { transform: rotate(-360deg); } }`,
    ]))
    const rules = RINGS.map(cfg =>
      `.oo-${cfg.dir}-${cfg.period} { transform-origin: center; transform-box: view-box; animation: oo-spin-${cfg.dir}-${cfg.period} ${cfg.period}s linear infinite; }`
    )
    return blocks.concat(rules).join('\n')
  }, [])

  return (
    <svg
      viewBox="-300 -300 600 600"
      className={`oo-svg ${errorTint ? 'oo-error' : ''}`}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      aria-hidden="true"
    >
      <g className="oo-root">
        {elements}
      </g>
      <style>{`
        ${keyframes}
        .oo-svg .oo-ring { will-change: transform; }
        .oo-error .oo-root { filter: hue-rotate(-20deg) saturate(1.2); }
        @media (prefers-reduced-motion: reduce) {
          .oo-svg .oo-ring { animation: none !important; }
        }
      `}</style>
    </svg>
  )
}
