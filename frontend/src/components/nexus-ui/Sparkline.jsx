import { useEffect, useRef } from 'react'
import { useReducedMotion } from '../../hooks/useReducedMotion'

/**
 * <Sparkline>
 *   Tiny inline trend graph. Canvas-based for performance (50× faster than SVG
 *   when redrawn frequently or with >50 datapoints). Falls back to a static
 *   line when prefers-reduced-motion is on.
 *
 *   Props:
 *     data       number[]    — values to plot (auto-scales y-axis)
 *     width      number      — px (default 120)
 *     height     number      — px (default 28)
 *     color      string      — stroke colour (default gold)
 *     fill       bool        — show gradient fill below line (default true)
 *     thickness  number      — line width in px (default 1.5)
 *     ariaLabel  string      — optional a11y label
 *     className, style
 */
export default function Sparkline({
  data = [],
  width = 120,
  height = 28,
  color,
  fill = true,
  thickness = 1.5,
  ariaLabel,
  className = '',
  style,
}) {
  const canvasRef = useRef(null)
  const reducedMotion = useReducedMotion()

  // Resolve gold default at runtime (CSS var unreachable via raw canvas)
  const stroke = color || '#e5c76b'

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !data || data.length < 2) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2) // cap DPR — saves perf on hi-dpi
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)

    const max = Math.max(...data)
    const min = Math.min(...data)
    const range = max - min || 1
    const stepX = data.length > 1 ? width / (data.length - 1) : 0
    const padY = 3
    const usableH = height - padY * 2

    const points = data.map((v, i) => [
      i * stepX,
      height - padY - ((v - min) / range) * usableH,
    ])

    if (fill) {
      const grad = ctx.createLinearGradient(0, 0, 0, height)
      grad.addColorStop(0, hexToRgba(stroke, 0.30))
      grad.addColorStop(1, hexToRgba(stroke, 0))
      ctx.fillStyle = grad
      ctx.beginPath()
      ctx.moveTo(0, height)
      for (const [x, y] of points) ctx.lineTo(x, y)
      ctx.lineTo(width, height)
      ctx.closePath()
      ctx.fill()
    }

    ctx.strokeStyle = stroke
    ctx.lineWidth = thickness
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    if (!reducedMotion) {
      ctx.shadowColor = hexToRgba(stroke, 0.55)
      ctx.shadowBlur = 4
    }
    ctx.beginPath()
    ctx.moveTo(points[0][0], points[0][1])
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i][0], points[i][1])
    }
    ctx.stroke()
  }, [data, width, height, stroke, fill, thickness, reducedMotion])

  if (!data || data.length < 2) {
    return (
      <div
        className={className}
        style={{ width, height, ...style }}
        aria-label={ariaLabel}
        role="img"
      />
    )
  }

  return (
    <canvas
      ref={canvasRef}
      className={`nx-sparkline ${className}`}
      style={style}
      aria-label={ariaLabel}
      role="img"
    />
  )
}

/** #RRGGBB or rgb()/rgba()/named -> rgba string with alpha. Best-effort. */
function hexToRgba(c, a) {
  if (!c) return `rgba(229,199,107,${a})`
  if (c.startsWith('#')) {
    const h = c.slice(1)
    const full = h.length === 3 ? h.split('').map(x => x + x).join('') : h
    const n = parseInt(full, 16)
    const r = (n >> 16) & 255
    const g = (n >> 8) & 255
    const b = n & 255
    return `rgba(${r},${g},${b},${a})`
  }
  if (c.startsWith('rgb')) {
    const m = c.match(/rgba?\(([^)]+)\)/)
    if (m) {
      const parts = m[1].split(',').map(s => s.trim())
      return `rgba(${parts[0]},${parts[1]},${parts[2]},${a})`
    }
  }
  // Fallback: gold-ish
  return `rgba(229,199,107,${a})`
}
