import { useState, useEffect, useRef } from 'react'
import { useAppStore } from '../../store/appStore'
import { useBrainStore } from '../../store/brainStore'
import { Panel, Badge, StatCard } from '../ui/primitives'

const BOT_WIDTH = 12
const BOT_HEIGHT = 16
const BOT_SPEED_PX = 2

export default function NeuralBrainPage() {
  const canvasRef = useRef(null)
  const animRef = useRef({ bots: [], nodePositions: {}, frame: null, graph: null })
  const graph = useBrainStore(s => s.graph)
  const nnStatus = useAppStore(s => s.nnStatus)
  const identity = useAppStore(s => s.identity)
  const [agents, setAgents] = useState([])
  const [selected, setSelected] = useState(null)

  // Load agent list on mount
  useEffect(() => {
    fetch('/api/agents/list').then(r => r.json())
      .then(d => setAgents(d.agents || []))
      .catch(() => {})
  }, [])

  // Initialize bots and bot stations when agents load
  useEffect(() => {
    if (!agents.length) return
    const A = animRef.current
    A.bots = agents.slice(0, 20).map((agent, i) => ({
      agentId: agent.id,
      label: agent.id.replace(/-/g, ' ').slice(0, 14),
      stationX: 20,
      stationY: 40 + i * 28,
      x: 20,
      y: 40 + i * 28,
      state: 'IDLE',
      active: agent.state === 'active',
      color: agent.state === 'active' ? '#22C55E' : '#20D6C7',
      restUntil: 0,
      targetX: null,
      targetY: null,
      payload: false,
      arrivalTs: null,
    }))
  }, [agents, graph])

  // Start rAF loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let alive = true

    function frame(ts) {
      if (!alive) return
      const A = animRef.current
      const W = canvas.width
      const H = canvas.height

      ctx.fillStyle = 'var(--bg-base, #0A0B12)'
      ctx.fillRect(0, 0, W, H)

      drawNetwork(ctx, A.graph, W, H, A)
      drawBots(ctx, A.bots, ts, W, H, A)
      animRef.current.frame = requestAnimationFrame(frame)
    }
    animRef.current.frame = requestAnimationFrame(frame)
    return () => { alive = false; cancelAnimationFrame(animRef.current.frame) }
  }, [])

  // Update graph when it changes
  useEffect(() => {
    if (!graph?.nodes?.length) return
    const A = animRef.current
    A.graph = graph
  }, [graph])

  const avgConfidence = (nnStatus?.confidence || 0).toFixed(2)
  const totalNodes = graph?.nodes?.length || 0

  return (
    <div style={{ display: 'flex', gap: 10, height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {identity && (
          <div style={{ padding: '12px 14px', background: 'rgba(32,214,199,0.08)', border: '1px solid rgba(32,214,199,0.2)', borderRadius: 8, fontSize: 11, color: '#20D6C7', fontFamily: 'monospace' }}>
            {identity.name} · {identity.fingerprint}
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
          <StatCard label="Confidence" value={`${(avgConfidence * 100).toFixed(0)}%`} color={avgConfidence > 0.7 ? '#22C55E' : '#F59E0B'} sub="Avg confidence" />
          <StatCard label="Graph Nodes" value={totalNodes} color="#20D6C7" sub="Neural network" />
          <StatCard label="Active Bots" value={agents.filter(a => a.state === 'active').length} color="#E5C76B" sub="Working agents" />
        </div>
        <Panel title="Neural Network — Live" style={{ flex: 1 }}>
          <canvas ref={canvasRef} style={{ width: '100%', height: '100%', minHeight: 400, background: 'rgba(0,0,0,0.3)', borderRadius: 8 }} />
        </Panel>
      </div>
      <div style={{ width: 260, display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
        <Panel title="Agents">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {agents.slice(0, 20).map(a => (
              <div key={a.id} onClick={() => setSelected(a.id === selected?.id ? null : a)} style={{
                padding: '8px 10px', borderRadius: 6, background: selected?.id === a.id ? 'rgba(229,199,107,0.1)' : 'rgba(32,214,199,0.04)',
                border: `1px solid ${selected?.id === a.id ? 'rgba(229,199,107,0.3)' : 'rgba(32,214,199,0.1)'}`,
                cursor: 'pointer', fontSize: 10,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: a.state === 'active' ? '#22C55E' : '#20D6C7' }} />
                  <span style={{ color: '#F0E9D2', flex: 1 }}>{a.id}</span>
                  <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>{a.tasksCompleted || 0}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}

function drawNetwork(ctx, graph, W, H, A) {
  if (!graph?.nodes) return

  const centerX = W * 0.65
  const centerY = H * 0.5
  const nodes = graph.nodes || []
  const nodePos = {}

  if (!A.nodePositions || Object.keys(A.nodePositions).length === 0) {
    const rings = {
      'Input': { r: H * 0.35, nodes: [] },
      'Skill': { r: H * 0.22, nodes: [] },
      'Output': { r: H * 0.12, nodes: [] },
      'Agent': { r: H * 0.35, nodes: [] },
      'Strategy': { r: H * 0.22, nodes: [] },
      'Memory': { r: H * 0.15, nodes: [] },
    }

    nodes.forEach(n => {
      const type = n.type || 'Input'
      const ring = rings[type] || rings['Input']
      ring.nodes.push(n)
    })

    Object.values(rings).forEach(ring => {
      ring.nodes.forEach((n, idx) => {
        const angle = (idx / Math.max(ring.nodes.length, 1)) * Math.PI * 2
        const x = centerX + ring.r * Math.cos(angle)
        const y = centerY + ring.r * Math.sin(angle)
        nodePos[n.id] = { x, y }
      })
    })

    A.nodePositions = nodePos
  } else {
    Object.assign(nodePos, A.nodePositions)
  }

  if (graph.connections) {
    graph.connections.forEach(c => {
      const from = nodePos[c.from]
      const to = nodePos[c.to]
      if (!from || !to) return
      ctx.strokeStyle = `rgba(32, 214, 199, ${Math.min(0.4, (c.weight || 0.3) * 0.5)})`
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(from.x, from.y)
      ctx.lineTo(to.x, to.y)
      ctx.stroke()
    })
  }

  nodes.forEach(n => {
    const pos = nodePos[n.id]
    if (!pos) return
    const activation = Math.min(1, n.activation || 0.3)
    const radius = 4 + activation * 5
    const color = n.type === 'Agent' ? '#E5C76B' : n.type === 'Input' ? '#20D6C7' : n.type === 'Output' ? '#F59E0B' : '#22C55E'

    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2)
    ctx.fill()

    if (activation > 0.6) {
      ctx.strokeStyle = `${color}80`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, radius + 2, 0, Math.PI * 2)
      ctx.stroke()
    }
  })
}

function drawBots(ctx, bots, ts, W, H, A) {
  if (!bots) return

  bots.forEach(bot => {
    if (bot.state === 'IDLE') {
      if (ts > (bot.restUntil || 0)) {
        if (Math.random() > 0.98) {
          bot.state = 'WALKING'
          const node = A.graph?.nodes?.[Math.floor(Math.random() * (A.graph?.nodes?.length || 1))]
          if (node && A.nodePositions?.[node.id]) {
            bot.targetX = A.nodePositions[node.id].x
            bot.targetY = A.nodePositions[node.id].y
            bot.payload = true
          }
        }
      }
    } else if (bot.state === 'WALKING') {
      if (bot.targetX && bot.targetY) {
        const dx = bot.targetX - bot.x
        const dy = bot.targetY - bot.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < BOT_SPEED_PX) {
          bot.state = 'ARRIVED'
          bot.arrivalTs = ts
        } else {
          bot.x += (dx / dist) * BOT_SPEED_PX
          bot.y += (dy / dist) * BOT_SPEED_PX
        }
      }
    } else if (bot.state === 'ARRIVED') {
      if (ts - (bot.arrivalTs || 0) > 600) {
        bot.state = 'RETURNING'
      }
    } else if (bot.state === 'RETURNING') {
      const dx = bot.stationX - bot.x
      const dy = bot.stationY - bot.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < BOT_SPEED_PX) {
        bot.state = 'RESTING'
        bot.x = bot.stationX
        bot.y = bot.stationY
        bot.restUntil = ts + 2000 + Math.random() * 3000
        bot.payload = false
      } else {
        bot.x += (dx / dist) * BOT_SPEED_PX
        bot.y += (dy / dist) * BOT_SPEED_PX
      }
    }

    const color = bot.payload ? '#FFD97A' : bot.color
    ctx.fillStyle = color
    ctx.fillRect(bot.x - BOT_WIDTH / 2, bot.y - BOT_HEIGHT / 2, BOT_WIDTH, BOT_HEIGHT)

    ctx.fillStyle = 'white'
    ctx.fillRect(bot.x - 4, bot.y - 5, 2, 2)
    ctx.fillRect(bot.x + 2, bot.y - 5, 2, 2)

    if (bot.state === 'IDLE' || bot.state === 'RESTING') {
      const pulsAmount = Math.sin(ts * 0.005) * 0.3 + 0.5
      ctx.fillStyle = `rgba(32, 214, 199, ${pulsAmount})`
      ctx.beginPath()
      ctx.arc(bot.stationX, bot.stationY, 3, 0, Math.PI * 2)
      ctx.fill()
    }

    if (bot.state === 'WALKING' && bot.payload) {
      ctx.strokeStyle = `${color}60`
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(bot.x, bot.y, 8, 0, Math.PI * 2)
      ctx.stroke()
    }
  })
}
