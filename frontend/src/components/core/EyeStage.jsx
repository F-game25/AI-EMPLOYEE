import { useEffect, useMemo, useRef, useState } from 'react'
import RoboticEye from './RoboticEye'
import './EyeStage.css'

/**
 * EyeStage — orbital HUD composition wrapper for <RoboticEye>.
 *
 * Layers (back → front):
 *   L5  es-aura          DOM radial-gradient driven by state
 *   L1  es-hud-ring      SVG outer reticle + tick marks + cardinal arcs (rot 60s)
 *   L2  es-scanline      SVG dual-arc scanner (rot 8s, state-paced)
 *   L3  es-orbital-nodes SVG 6 data dots on varied orbits
 *   L4  es-gaze-ray      SVG single line following local cursor
 *   L6  es-orbital-card  DOM N/E/S/W mini-KPI cards
 *       es-eye-mount     centered <RoboticEye />
 *
 * The eye composer itself is untouched — this only wraps it.
 */

const NODES = [
  { r: 140, dur: 30, dir: -1, key: 'agents',   label: 'Agents'    },
  { r: 165, dur: 45, dir:  1, key: 'tasks',    label: 'Tasks'     },
  { r: 175, dur: 18, dir: -1, key: 'memory',   label: 'Memory'    },
  { r: 190, dur: 60, dir:  1, key: 'models',   label: 'Models'    },
  { r: 210, dur: 36, dir: -1, key: 'security', label: 'Security'  },
  { r: 225, dur: 25, dir:  1, key: 'errors',   label: 'Errors'    },
]

const formatNum = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}k`
  return String(Math.round(v))
}
const formatTokens = (n) => formatNum(n)

// Build SVG arc path for cardinal markers — sweeps `widthDeg` centred on `centerDeg`.
const arcPath = (r, centerDeg, widthDeg) => {
  const a0 = ((centerDeg - widthDeg / 2 - 90) * Math.PI) / 180
  const a1 = ((centerDeg + widthDeg / 2 - 90) * Math.PI) / 180
  const x0 = Math.cos(a0) * r
  const y0 = Math.sin(a0) * r
  const x1 = Math.cos(a1) * r
  const y1 = Math.sin(a1) * r
  const large = widthDeg > 180 ? 1 : 0
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

export default function EyeStage({
  state = 'IDLE',
  tokensRate = 0,
  reasoningCount = 0,
  contextDepth = 0,
  memoryRate = 0,
  agentActivity = 0,
  taskActivity = 0,
  gpuTemp = 0,
  gpuUsage = 0,
  focusKeyword = 'NEXUS',
  eyeSize = 520,
}) {
  const stageRef = useRef(null)
  const stageSize = eyeSize * 1.3
  const stateKey = String(state || 'idle').toLowerCase()

  // ── Gaze tracking — local to the stage, drives the gaze ray angle ────────
  const [gazeAngle, setGazeAngle] = useState(0)
  const [gazeActive, setGazeActive] = useState(false)
  const lastMoveRef = useRef(0)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined

    const onMove = (e) => {
      const el = stageRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const dx = e.clientX - (r.left + r.width / 2)
      const dy = e.clientY - (r.top + r.height / 2)
      if (dx === 0 && dy === 0) return
      // SVG: x=right, y=down — angle in degrees, 0 = east.
      setGazeAngle((Math.atan2(dy, dx) * 180) / Math.PI)
      setGazeActive(true)
      lastMoveRef.current = Date.now()
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    const id = setInterval(() => {
      if (Date.now() - lastMoveRef.current > 5000) setGazeActive(false)
    }, 1000)
    return () => { window.removeEventListener('mousemove', onMove); clearInterval(id) }
  }, [])

  // ── HUD ring static geometry — memoized so it only renders once ───────────
  const ticks = useMemo(() => Array.from({ length: 72 }).map((_, i) => {
    const major = i % 6 === 0
    const len = major ? 8 : 4
    return { angle: i * 5, len, major }
  }), [])

  const labels = useMemo(() => Array.from({ length: 12 }).map((_, i) => {
    const deg = i * 30
    const rad = ((deg - 90) * Math.PI) / 180
    const x = Math.cos(rad) * 275
    const y = Math.sin(rad) * 275
    return { deg, x, y, text: String(deg).padStart(3, '0') }
  }), [])

  const cardinals = useMemo(() => [0, 90, 180, 270].map(deg => ({
    deg, d: arcPath(290, deg, 14),
  })), [])

  // Ray length — hidden if gaze never engaged
  const rayHidden = !gazeActive || (state && state.toUpperCase() === 'IDLE' && Date.now() - lastMoveRef.current > 5000)

  return (
    <div
      ref={stageRef}
      className="es-stage"
      style={{ width: stageSize, height: stageSize }}
      data-state={stateKey}
    >
      {/* L5 — State aura (back) */}
      <div className={`es-aura es-aura--${stateKey}`} />

      {/* L1 — Outer HUD reticle */}
      <svg className="es-hud-ring" viewBox="-300 -300 600 600" aria-hidden="true">
        <g stroke="var(--eye-halo-color, #fbbf24)" fill="none">
          <circle cx="0" cy="0" r="290" strokeWidth="1" opacity="0.35" />
          <circle cx="0" cy="0" r="255" strokeWidth="1" opacity="0.18" strokeDasharray="6 4" />
        </g>
        <g stroke="var(--eye-halo-color, #fbbf24)">
          {ticks.map((t) => {
            const rad = ((t.angle - 90) * Math.PI) / 180
            const x1 = Math.cos(rad) * 290
            const y1 = Math.sin(rad) * 290
            const x2 = Math.cos(rad) * (290 - t.len)
            const y2 = Math.sin(rad) * (290 - t.len)
            return (
              <line
                key={t.angle}
                x1={x1.toFixed(2)} y1={y1.toFixed(2)}
                x2={x2.toFixed(2)} y2={y2.toFixed(2)}
                strokeWidth={t.major ? 1.2 : 0.8}
                opacity={t.major ? 0.65 : 0.4}
              />
            )
          })}
        </g>
        <g fontFamily="'JetBrains Mono', monospace" fontSize="9" fill="rgba(229,199,107,0.55)" textAnchor="middle" dominantBaseline="middle">
          {labels.map(l => (
            <text key={l.deg} x={l.x.toFixed(2)} y={l.y.toFixed(2)}>{l.text}</text>
          ))}
        </g>
        <g stroke="var(--eye-halo-color, #fbbf24)" fill="none" strokeWidth="2" opacity="0.7" strokeLinecap="round">
          {cardinals.map(c => <path key={c.deg} d={c.d} />)}
        </g>
      </svg>

      {/* L2 — Scanning ring */}
      <svg className={`es-scanline es-scanline--${stateKey}`} viewBox="-300 -300 600 600" aria-hidden="true">
        <defs>
          <linearGradient id="es-scan-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%"   stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0" />
            <stop offset="50%"  stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="1" />
            <stop offset="100%" stopColor="var(--eye-halo-color, #fbbf24)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g fill="none" stroke="url(#es-scan-grad)" strokeLinecap="round">
          {/* primary arc — 120° wide centred at -90° (top) */}
          <path d={arcPath(200, 0, 120)} strokeWidth="1.6" opacity="0.55" />
          {/* secondary arc — 30° offset behind */}
          <path d={arcPath(200, -30, 120)} strokeWidth="1.2" opacity="0.25" />
        </g>
      </svg>

      {/* L3 — Orbital data nodes */}
      <svg className="es-orbital-nodes" viewBox="-300 -300 600 600" aria-hidden="true">
        {NODES.map(n => (
          <g
            key={n.key}
            className={`es-node es-node--${n.key}`}
            style={{
              '--r': `${n.r}px`,
              '--dur': `${n.dur}s`,
              animationDirection: n.dir < 0 ? 'reverse' : 'normal',
            }}
          >
            <circle cx="0" cy="0" r="3.2" fill="var(--eye-halo-color, #fbbf24)" opacity="0.85">
              <title>{n.label}</title>
            </circle>
            <circle cx="0" cy="0" r="1" fill="#ffffff" opacity="0.95" />
          </g>
        ))}
      </svg>

      {/* L4 — Gaze ray */}
      <svg
        className={`es-gaze-ray ${rayHidden ? 'es-gaze-ray--lost' : ''}`}
        viewBox="-300 -300 600 600"
        aria-hidden="true"
      >
        <line
          x1="0" y1="0"
          x2={(Math.cos((gazeAngle * Math.PI) / 180) * 240).toFixed(2)}
          y2={(Math.sin((gazeAngle * Math.PI) / 180) * 240).toFixed(2)}
          stroke="var(--eye-halo-color, #fbbf24)"
          strokeWidth="0.5"
          strokeLinecap="round"
        />
      </svg>

      {/* L6 — Orbital mini-KPI cards */}
      <div className="es-orbital-card es-orbital-card--n" style={{ '--card-accent': '#a855f7' }}>
        <div className="es-orbital-card__label">REASONING SHARDS</div>
        <div className="es-orbital-card__value">{formatNum(reasoningCount)}</div>
      </div>
      <div className="es-orbital-card es-orbital-card--e" style={{ '--card-accent': '#fbbf24' }}>
        <div className="es-orbital-card__label">TOKENS / SEC</div>
        <div className="es-orbital-card__value">{formatTokens(tokensRate)}</div>
      </div>
      <div className="es-orbital-card es-orbital-card--s" style={{ '--card-accent': '#22d3ee' }}>
        <div className="es-orbital-card__label">CONTEXT DEPTH</div>
        <div className="es-orbital-card__value">{formatNum(contextDepth)}</div>
      </div>
      <div className="es-orbital-card es-orbital-card--w" style={{ '--card-accent': '#22c55e' }}>
        <div className="es-orbital-card__label">MEMORY WRITES</div>
        <div className="es-orbital-card__value">{`${formatNum(memoryRate)}/s`}</div>
      </div>

      {/* Centered eye */}
      <div className="es-eye-mount">
        <RoboticEye
          state={state}
          tokensRate={tokensRate}
          gpuTemp={gpuTemp}
          gpuUsage={gpuUsage}
          focusKeyword={focusKeyword}
          size={eyeSize}
        />
      </div>

      {/* Hidden activity sinks — keep props live for future node-driven rendering */}
      <span hidden aria-hidden="true" data-agent-activity={agentActivity} data-task-activity={taskActivity} />
    </div>
  )
}
