import { useEffect, useRef, useState } from 'react'
import './WaveformStrip.css'

/**
 * <WaveformStrip>
 *   Canvas oscilloscope-style telemetry strip. DPR-capped, ResizeObserver-driven.
 *   Mirrors Sparkline's perf characteristics. ~150 LOC.
 *
 *   Props:
 *     label      string             — caption, e.g. "CPU LOAD"
 *     value      string|number      — formatted current value, e.g. "62%"
 *     data       number[]           — rolling buffer; renders up to last 60
 *     color      string             — line + glow color (hex preferred)
 *     height     number             — px (default 56)
 *     amplitude  'auto'|number      — 'auto' = max(data); number = explicit ceiling
 *     variant    'oscilloscope'|'mountain'
 */
export function WaveformStrip({
  label,
  value,
  data = [],
  color,
  height = 56,
  amplitude = 'auto',
  variant = 'oscilloscope',
}) {
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const [size, setSize] = useState({ w: 0, h: height })

  // Observe container width
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    if (typeof ResizeObserver === 'undefined') {
      const measure = () => {
        const w = Math.round(el.getBoundingClientRect?.().width || el.clientWidth || 0)
        if (w > 0) setSize(prev => (prev.w === w ? prev : { w, h: height }))
      }
      measure()
      window.addEventListener?.('resize', measure)
      return () => window.removeEventListener?.('resize', measure)
    }
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const w = Math.round(e.contentRect.width)
        if (w > 0) setSize(prev => (prev.w === w ? prev : { w, h: height }))
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [height])

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || size.w === 0) return
    const stroke = color || '#22d3ee'
    const w = size.w
    const h = height
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, w, h)

    // Grid (8 vertical, 3 horizontal)
    ctx.strokeStyle = 'rgba(255,255,255,0.04)'
    ctx.lineWidth = 1
    for (let i = 1; i < 8; i++) {
      const x = (w / 8) * i
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
    }
    for (let i = 1; i < 3; i++) {
      const y = (h / 3) * i
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
    }

    const baseline = h / 2
    const halfH = h / 2 - 4

    // Baseline
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.beginPath(); ctx.moveTo(0, baseline); ctx.lineTo(w, baseline); ctx.stroke()

    const samples = (data || []).slice(-Math.max(60, data?.length || 0))
    if (!samples.length) return

    const cap = amplitude === 'auto' ? Math.max(...samples, 1) : amplitude
    const stepX = samples.length > 1 ? w / (samples.length - 1) : 0
    const pts = samples.map((v, i) => {
      const n = Math.max(0, Math.min(1, (v ?? 0) / cap))
      return { x: i * stepX, n }
    })

    // Quadratic-smoothed path along top curve
    const topPath = () => {
      ctx.beginPath()
      ctx.moveTo(pts[0].x, baseline - pts[0].n * halfH)
      for (let i = 1; i < pts.length - 1; i++) {
        const cx = (pts[i].x + pts[i + 1].x) / 2
        const cy = (baseline - pts[i].n * halfH + baseline - pts[i + 1].n * halfH) / 2
        ctx.quadraticCurveTo(pts[i].x, baseline - pts[i].n * halfH, cx, cy)
      }
      const last = pts[pts.length - 1]
      ctx.lineTo(last.x, baseline - last.n * halfH)
    }
    const bottomPath = () => {
      ctx.beginPath()
      ctx.moveTo(pts[0].x, baseline + pts[0].n * halfH)
      for (let i = 1; i < pts.length - 1; i++) {
        const cx = (pts[i].x + pts[i + 1].x) / 2
        const cy = (baseline + pts[i].n * halfH + baseline + pts[i + 1].n * halfH) / 2
        ctx.quadraticCurveTo(pts[i].x, baseline + pts[i].n * halfH, cx, cy)
      }
      const last = pts[pts.length - 1]
      ctx.lineTo(last.x, baseline + last.n * halfH)
    }

    // Fill (top → baseline)
    const gradTop = ctx.createLinearGradient(0, 0, 0, baseline)
    gradTop.addColorStop(0, hexToRgba(stroke, 0.35))
    gradTop.addColorStop(1, hexToRgba(stroke, 0))
    ctx.fillStyle = gradTop
    topPath()
    ctx.lineTo(w, baseline); ctx.lineTo(0, baseline); ctx.closePath(); ctx.fill()

    if (variant === 'oscilloscope') {
      const gradBot = ctx.createLinearGradient(0, baseline, 0, h)
      gradBot.addColorStop(0, hexToRgba(stroke, 0))
      gradBot.addColorStop(1, hexToRgba(stroke, 0.35))
      ctx.fillStyle = gradBot
      bottomPath()
      ctx.lineTo(w, baseline); ctx.lineTo(0, baseline); ctx.closePath(); ctx.fill()
    }

    // Stroke lines with glow
    ctx.strokeStyle = stroke
    ctx.lineWidth = 1.6
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.shadowColor = stroke
    ctx.shadowBlur = 4
    topPath(); ctx.stroke()
    if (variant === 'oscilloscope') { bottomPath(); ctx.stroke() }
    ctx.shadowBlur = 0
  }, [data, size, color, height, amplitude, variant])

  return (
    <div ref={wrapRef} className="nx-wave" style={{ height }}>
      <span className="nx-wave__label">{label}</span>
      <span className="nx-wave__value" style={{ color: color || '#22d3ee' }}>{value}</span>
      <canvas ref={canvasRef} className="nx-wave__canvas" />
    </div>
  )
}

/** #RRGGBB / #RGB / rgb()/rgba() -> rgba string. Best-effort fallback. */
function hexToRgba(c, a) {
  if (!c) return `rgba(34,211,238,${a})`
  if (c.startsWith('#')) {
    const h = c.slice(1)
    const full = h.length === 3 ? h.split('').map(x => x + x).join('') : h
    const n = parseInt(full, 16)
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
  }
  if (c.startsWith('rgb')) {
    const m = c.match(/rgba?\(([^)]+)\)/)
    if (m) {
      const p = m[1].split(',').map(s => s.trim())
      return `rgba(${p[0]},${p[1]},${p[2]},${a})`
    }
  }
  return `rgba(34,211,238,${a})`
}

export default WaveformStrip
