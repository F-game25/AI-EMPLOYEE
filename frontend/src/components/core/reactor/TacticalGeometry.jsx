/**
 * TacticalGeometry — Z5 corner brackets, telemetry dots, scan ticks, signal traces.
 * Deterministic random placement (seeded by index) wrapped in useMemo to prevent
 * layout shift on re-render.
 */
import { useMemo } from 'react'

// Tiny seedable PRNG (mulberry32) — deterministic per index.
function rng(seed) {
  let t = seed + 0x6D2B79F5
  return () => {
    t = Math.imul(t ^ (t >>> 15), 1 | t)
    t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const STROKE = 'rgba(229,199,107,0.55)'
const DOT_FILL = 'rgba(245,158,11,0.85)'
const TRACE_STROKE = 'rgba(34,211,238,0.55)'

// 4 corner targeting brackets at cardinal compass positions, just outside r=290.
const BRACKET_R = 305
const BRACKET_LEN = 22
const BRACKET_OFFSET = 14

function CornerBracket({ angleDeg, idx }) {
  const a = angleDeg * Math.PI / 180
  const cx = Math.cos(a) * BRACKET_R
  const cy = Math.sin(a) * BRACKET_R
  // Two short perpendicular lines forming an L pointing inward.
  const tx = Math.cos(a)
  const ty = Math.sin(a)
  // Tangent (perpendicular to radial)
  const px = -ty
  const py = tx
  const inwardX = cx - tx * BRACKET_OFFSET
  const inwardY = cy - ty * BRACKET_OFFSET
  const armA1x = inwardX + px * BRACKET_LEN / 2
  const armA1y = inwardY + py * BRACKET_LEN / 2
  const armA2x = inwardX - px * BRACKET_LEN / 2
  const armA2y = inwardY - py * BRACKET_LEN / 2
  const radialEndX = inwardX + tx * BRACKET_LEN
  const radialEndY = inwardY + ty * BRACKET_LEN
  return (
    <g key={`b${idx}`}>
      <line x1={armA1x} y1={armA1y} x2={armA2x} y2={armA2y}
        stroke={STROKE} strokeWidth="1.2" strokeLinecap="round" />
      <line x1={inwardX} y1={inwardY} x2={radialEndX} y2={radialEndY}
        stroke={STROKE} strokeWidth="1.2" strokeLinecap="round" />
    </g>
  )
}

export default function TacticalGeometry() {
  // Telemetry dots, scan ticks, signal traces — memoized deterministic placement.
  const { dots, ticks, traces } = useMemo(() => {
    // 12 telemetry dots between r=200..270
    const dots = Array.from({ length: 12 }, (_, i) => {
      const r = rng(101 + i)
      const radius = 200 + r() * 70
      const angle = r() * Math.PI * 2
      const x = Math.cos(angle) * radius
      const y = Math.sin(angle) * radius
      const dur = (1.4 + r() * 2.6).toFixed(2)
      const delay = (-r() * 3).toFixed(2)
      return { x, y, dur, delay, i }
    })

    // 8 short scan ticks at random angles, length ~10, at r≈295
    const ticks = Array.from({ length: 8 }, (_, i) => {
      const r = rng(311 + i)
      const angle = r() * Math.PI * 2
      const inner = 286
      const outer = inner + 10 + r() * 6
      const x1 = Math.cos(angle) * inner
      const y1 = Math.sin(angle) * inner
      const x2 = Math.cos(angle) * outer
      const y2 = Math.sin(angle) * outer
      return { x1, y1, x2, y2, i }
    })

    // 3 signal traces: short arcs with a tiny pulsing dot moving along them
    const traces = Array.from({ length: 3 }, (_, i) => {
      const r = rng(701 + i)
      const radius = 215 + r() * 50
      const startDeg = r() * 360
      const sweep = 22 + r() * 14
      const endDeg = startDeg + sweep
      const s = startDeg * Math.PI / 180
      const e = endDeg   * Math.PI / 180
      const x1 = Math.cos(s) * radius, y1 = Math.sin(s) * radius
      const x2 = Math.cos(e) * radius, y2 = Math.sin(e) * radius
      const d = `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radius} ${radius} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`
      const dur = (2.0 + r() * 2.0).toFixed(2)
      const delay = (-r() * 2).toFixed(2)
      return { d, dur, delay, i }
    })

    return { dots, ticks, traces }
  }, [])

  return (
    <svg
      viewBox="-300 -300 600 600"
      className="tgeom"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      aria-hidden="true"
    >
      {/* Corner targeting brackets at N/E/S/W just outside outer orbital ring */}
      <CornerBracket angleDeg={-90} idx={0} />
      <CornerBracket angleDeg={0}   idx={1} />
      <CornerBracket angleDeg={90}  idx={2} />
      <CornerBracket angleDeg={180} idx={3} />

      {/* Telemetry dots */}
      {dots.map(d => (
        <circle key={`d${d.i}`} cx={d.x} cy={d.y} r="1.4" fill={DOT_FILL}
          style={{
            animation: `tgeom-flicker ${d.dur}s ease-in-out ${d.delay}s infinite`,
            transformOrigin: `${d.x}px ${d.y}px`
          }}
        />
      ))}

      {/* Scan ticks */}
      {ticks.map(t => (
        <line key={`t${t.i}`} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
          stroke={STROKE} strokeWidth="0.8" strokeLinecap="round" opacity="0.6" />
      ))}

      {/* Signal traces with a pulsing dot crawling along */}
      {traces.map(tr => (
        <g key={`tr${tr.i}`}>
          <path id={`tgeom-path-${tr.i}`} d={tr.d}
            fill="none" stroke={TRACE_STROKE} strokeWidth="0.8" strokeOpacity="0.6" />
          <circle r="1.6" fill={TRACE_STROKE}>
            <animateMotion dur={`${tr.dur}s`} repeatCount="indefinite" begin={`${tr.delay}s`}>
              <mpath href={`#tgeom-path-${tr.i}`} />
            </animateMotion>
            <animate attributeName="opacity" values="0.2;1;0.2" dur={`${tr.dur}s`}
              repeatCount="indefinite" begin={`${tr.delay}s`} />
          </circle>
        </g>
      ))}

      <style>{`
        @keyframes tgeom-flicker {
          0%, 100% { opacity: 0.25; transform: scale(0.85); }
          50%      { opacity: 1.0;  transform: scale(1.15); }
        }
        @media (prefers-reduced-motion: reduce) {
          .tgeom * { animation: none !important; }
        }
      `}</style>
    </svg>
  )
}
