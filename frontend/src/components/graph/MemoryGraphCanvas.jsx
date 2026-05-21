import { useEffect, useRef } from 'react'

/* Lightweight 2D force-graph on canvas — Obsidian-style, dependency-free.
   One reusable renderer for all four memory graphs. Nodes repel, links pull,
   everything drifts toward centre. "Alive": active task nodes pulse, short-term
   nodes fade by their `decay`, new nodes ease in. Designed to run one-at-a-time
   (tabbed) so we never pay for four simulations at once. */

const GROUP_COLORS = {
  money: '#FFD700', learning: '#60A5FA', automation: '#20D6C7',
  memory: '#9333EA', system: '#9A9AA5', agent: '#E5C76B',
}
const colorFor = (g) => GROUP_COLORS[g] || GROUP_COLORS.system

export default function MemoryGraphCanvas({ data, emptyHint = 'No nodes yet.' }) {
  const canvasRef = useRef(null)
  const stateRef = useRef({ nodes: [], links: [], raf: 0, hover: null, t: 0 })

  // Merge incoming data into the live simulation (preserve positions of kept nodes)
  useEffect(() => {
    const sim = stateRef.current
    const prev = new Map(sim.nodes.map(n => [n.id, n]))
    const W = canvasRef.current?.clientWidth || 600
    const H = canvasRef.current?.clientHeight || 400
    sim.nodes = (data?.nodes || []).map(n => {
      const old = prev.get(n.id)
      return old
        ? Object.assign(old, n)
        : { ...n, x: W / 2 + (Math.random() - 0.5) * 200, y: H / 2 + (Math.random() - 0.5) * 200, vx: 0, vy: 0, born: sim.t }
    })
    const ids = new Set(sim.nodes.map(n => n.id))
    sim.links = (data?.links || []).filter(l => {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      return ids.has(s) && ids.has(t)
    }).map(l => ({ ...l }))
  }, [data])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    let W = 0, H = 0
    const resize = () => {
      W = canvas.clientWidth; H = canvas.clientHeight
      canvas.width = W * dpr; canvas.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(canvas)

    const byId = (id) => stateRef.current.nodes.find(n => n.id === id)

    const step = () => {
      const sim = stateRef.current
      sim.t += 1
      const nodes = sim.nodes, links = sim.links
      // Repulsion (O(n²) — fine for ≤300 nodes)
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          let dx = a.x - b.x, dy = a.y - b.y
          let d2 = dx * dx + dy * dy || 0.01
          const f = 700 / d2
          const d = Math.sqrt(d2)
          const ux = dx / d, uy = dy / d
          a.vx += ux * f; a.vy += uy * f
          b.vx -= ux * f; b.vy -= uy * f
        }
      }
      // Springs
      links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source : byId(l.source)
        const t = typeof l.target === 'object' ? l.target : byId(l.target)
        if (!s || !t) return
        const dx = t.x - s.x, dy = t.y - s.y
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01
        const f = (d - 90) * 0.012 * (0.5 + (l.weight || 0.5))
        const ux = dx / d, uy = dy / d
        s.vx += ux * f; s.vy += uy * f
        t.vx -= ux * f; t.vy -= uy * f
      })
      // Centre gravity + integrate
      nodes.forEach(n => {
        n.vx += (W / 2 - n.x) * 0.0016
        n.vy += (H / 2 - n.y) * 0.0016
        n.vx *= 0.86; n.vy *= 0.86
        n.x += n.vx; n.y += n.vy
      })

      // Draw
      ctx.clearRect(0, 0, W, H)
      ctx.lineWidth = 1
      links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source : byId(l.source)
        const t = typeof l.target === 'object' ? l.target : byId(l.target)
        if (!s || !t) return
        ctx.strokeStyle = 'rgba(229,199,107,0.13)'
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke()
      })
      const pulse = 0.5 + 0.5 * Math.sin(sim.t * 0.08)
      nodes.forEach(n => {
        const base = n.val || 4
        const decay = n.decay || 0
        const r = Math.max(2.5, base) * (1 - decay * 0.5)
        const alpha = 1 - decay * 0.65
        const col = colorFor(n.group)
        if (n.active) {
          ctx.beginPath(); ctx.arc(n.x, n.y, r + 4 + pulse * 4, 0, Math.PI * 2)
          ctx.fillStyle = hexA(col, 0.18 * pulse); ctx.fill()
        }
        ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.fillStyle = hexA(col, alpha); ctx.fill()
        ctx.strokeStyle = hexA(col, alpha); ctx.lineWidth = 1.2; ctx.stroke()
        if (sim.hover === n.id || nodes.length <= 60) {
          ctx.fillStyle = `rgba(236,234,216,${0.4 + 0.6 * alpha})`
          ctx.font = '10px ui-sans-serif, system-ui'
          ctx.fillText(n.label || n.id, n.x + r + 3, n.y + 3)
        }
      })
      sim.raf = requestAnimationFrame(step)
    }
    stateRef.current.raf = requestAnimationFrame(step)

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const sim = stateRef.current
      let best = null, bd = 14
      sim.nodes.forEach(n => { const d = Math.hypot(n.x - mx, n.y - my); if (d < bd) { bd = d; best = n.id } })
      sim.hover = best
      canvas.style.cursor = best ? 'pointer' : 'default'
    }
    canvas.addEventListener('mousemove', onMove)

    return () => { cancelAnimationFrame(stateRef.current.raf); ro.disconnect(); canvas.removeEventListener('mousemove', onMove) }
  }, [])

  const empty = !(data?.nodes?.length)
  return (
    <div className="mg-canvas-wrap">
      <canvas ref={canvasRef} className="mg-canvas" role="img"
        aria-label={empty ? 'Empty memory graph' : `Memory graph with ${data.nodes.length} nodes and ${data.links?.length || 0} links`} />
      {empty && <div className="mg-empty-overlay" role="status">{emptyHint}</div>}
    </div>
  )
}

function hexA(hex, a) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`
}
