import { useEffect, useRef } from 'react'

const NODES = [
  { id: 'main-ai', label: 'MAIN AI', xp: 0.5, yp: 0.5, r: 24, color: '#D4AF37' },
  { id: 'forge', label: 'FORGE', xp: 0.2, yp: 0.3, r: 16, color: '#CD7F32' },
  { id: 'money', label: 'MONEY', xp: 0.8, yp: 0.3, r: 16, color: '#D4AF37' },
  { id: 'black', label: 'BLACKLIGHT', xp: 0.2, yp: 0.7, r: 16, color: '#CD7F32' },
  { id: 'doctor', label: 'DOCTOR', xp: 0.8, yp: 0.7, r: 16, color: '#CD7F32' },
]

const EDGES: [string, string][] = [
  ['main-ai', 'forge'],
  ['main-ai', 'money'],
  ['main-ai', 'black'],
  ['main-ai', 'doctor'],
]

interface Particle {
  x: number
  y: number
  prog: number
  speed: number
  sx: number
  sy: number
  ex: number
  ey: number
}

export function NeuralNetCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particles = useRef<Particle[]>([])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    let raf: number

    const resize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    const getPos = (node: typeof NODES[0]) => ({
      x: node.xp * canvas.width,
      y: node.yp * canvas.height,
    })

    const frame = () => {
      const W = canvas.width
      const H = canvas.height
      ctx.clearRect(0, 0, W, H)

      // Grid
      ctx.strokeStyle = 'rgba(26,26,26,0.5)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += 40) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
      }

      // Edges
      EDGES.forEach(([a, b]) => {
        const na = NODES.find((n) => n.id === a)!
        const nb = NODES.find((n) => n.id === b)!
        const pa = getPos(na)
        const pb = getPos(nb)
        ctx.beginPath()
        ctx.moveTo(pa.x, pa.y)
        ctx.lineTo(pb.x, pb.y)
        ctx.strokeStyle = 'rgba(212,175,55,0.25)'
        ctx.lineWidth = 1.5
        ctx.stroke()

        // Spawn particle occasionally
        if (Math.random() < 0.03) {
          particles.current.push({
            x: pa.x,
            y: pa.y,
            prog: 0,
            speed: 0.008 + Math.random() * 0.006,
            sx: pa.x,
            sy: pa.y,
            ex: pb.x,
            ey: pb.y,
          })
        }
      })

      // Particles
      particles.current = particles.current.filter((p) => {
        p.prog += p.speed
        p.x = p.sx + (p.ex - p.sx) * p.prog
        p.y = p.sy + (p.ey - p.sy) * p.prog
        const op = Math.sin(p.prog * Math.PI)
        ctx.beginPath()
        ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(212,175,55,${op})`
        ctx.fill()
        return p.prog < 1
      })

      // Nodes
      NODES.forEach((node) => {
        const { x, y } = getPos(node)
        const t = Date.now() / 1000
        const pulse = 1 + 0.3 * Math.abs(Math.sin(t + node.xp * 5))

        // Pulse ring
        ctx.beginPath()
        ctx.arc(x, y, node.r * pulse, 0, Math.PI * 2)
        ctx.strokeStyle = node.color + '44'
        ctx.lineWidth = 2
        ctx.stroke()

        // Fill
        const g = ctx.createRadialGradient(x - node.r * 0.3, y - node.r * 0.3, 0, x, y, node.r)
        g.addColorStop(0, node.color + 'CC')
        g.addColorStop(1, node.color + '44')
        ctx.beginPath()
        ctx.arc(x, y, node.r, 0, Math.PI * 2)
        ctx.fillStyle = g
        ctx.fill()

        // Label
        ctx.fillStyle = '#F5F0E8'
        ctx.font = '500 9px JetBrains Mono'
        ctx.textAlign = 'center'
        ctx.fillText(node.label, x, y + node.r + 14)
      })

      raf = requestAnimationFrame(frame)
    }

    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: 300, display: 'block', borderRadius: 8 }}
    />
  )
}
