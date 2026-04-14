import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import NeuralGraphPanel from '../dashboard/NeuralGraphPanel'
import { API_URL } from '../../config/api'

const BASE = API_URL

/* ─── Neuron color by state ─── */
const NEURON_COLORS = {
  inactive:   '#1a3a5c',  // dark blue
  processing: '#20D6C7',  // cyan
  learning:   '#22C55E',  // green
  confident:  '#9333EA',  // purple
  error:      '#EF4444',  // orange/red
  newborn:    '#D4AF37',  // gold
}

function neuronColor(node) {
  if (!node) return NEURON_COLORS.inactive
  if (node._age !== null && node._age !== undefined && node._age < 3) return NEURON_COLORS.newborn
  if (node.confidence > 0.8) return NEURON_COLORS.confident
  if (node.type === 'Output') return NEURON_COLORS.processing
  if (node.activation > 0.5) return NEURON_COLORS.learning
  if (node.confidence < 0.3 && node.weight > 0) return NEURON_COLORS.error
  return NEURON_COLORS.inactive
}

/* ─── Layout helpers ─── */
function layoutNodes(nodes, w, h) {
  const cx = w / 2
  const cy = h / 2
  const typeRings = { Input: 0.85, Hidden: 0.55, Skill: 0.55, Memory: 0.4, Strategy: 0.65, Output: 0.25 }
  const grouped = {}
  nodes.forEach((n) => {
    const ring = typeRings[n.type] || 0.6
    if (!grouped[ring]) grouped[ring] = []
    grouped[ring].push(n)
  })
  const positioned = []
  Object.entries(grouped).forEach(([ring, group]) => {
    const r = Math.min(w, h) * Number(ring) * 0.45
    group.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / group.length - Math.PI / 2
      positioned.push({
        ...node,
        x: cx + Math.cos(angle) * r,
        y: cy + Math.sin(angle) * r,
      })
    })
  })
  return positioned
}

/* ─── Canvas renderer ─── */
function drawBrain(ctx, nodes, connections, selectedId, time, w, h) {
  ctx.clearRect(0, 0, w, h)

  // Grid background
  ctx.strokeStyle = 'rgba(255,255,255,0.02)'
  ctx.lineWidth = 1
  for (let x = 0; x < w; x += 48) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 0; y < h; y += 48) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  const nodeMap = new Map()
  nodes.forEach((n) => nodeMap.set(n.id, n))

  // Draw connections
  connections.forEach((conn) => {
    const from = nodeMap.get(conn.from)
    const to = nodeMap.get(conn.to)
    if (!from || !to) return

    const strength = Math.max(0.15, Math.min(1, conn.weight || 0.3))
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.strokeStyle = `rgba(32, 214, 199, ${strength * 0.35})`
    ctx.lineWidth = 1 + strength * 3
    ctx.stroke()

    // Pulse traveling along the line
    const pulsePos = ((time * 0.001 * (1 + strength)) % 1)
    const px = from.x + (to.x - from.x) * pulsePos
    const py = from.y + (to.y - from.y) * pulsePos
    ctx.beginPath()
    ctx.arc(px, py, 2 + strength * 2, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(32, 214, 199, ${0.4 + strength * 0.5})`
    ctx.fill()
  })

  // Draw nodes
  nodes.forEach((node) => {
    const color = neuronColor(node)
    const radius = 6 + Math.min(node.weight || 0, 50) * 0.3 + (node.activation || 0) * 8
    const isSelected = node.id === selectedId
    const glow = isSelected ? 20 : (node.activation > 0.5 ? 10 : 4)

    // Glow (hex → rgba)
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius + glow, 0, Math.PI * 2)
    const r = parseInt(color.slice(1, 3), 16)
    const g = parseInt(color.slice(3, 5), 16)
    const b = parseInt(color.slice(5, 7), 16)
    ctx.fillStyle = `rgba(${r},${g},${b},${isSelected ? 0.25 : 0.08})`
    ctx.fill()

    // Core
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()

    // Border ring
    if (isSelected) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 3, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(255,255,255,0.6)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    // Label
    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.font = '10px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(node.label?.slice(0, 18) || '', node.x, node.y + radius + 14)
  })
}

/* ─── Stat card ─── */
function StatPill({ label, value, color }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '8px 16px',
      background: 'rgba(255,255,255,0.03)',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.06)',
      minWidth: '100px',
    }}>
      <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
      <span style={{ fontSize: '18px', fontWeight: 600, color: color || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  )
}

/* ─── Neuron Detail Callout ─── */
function NeuronDetail({ node }) {
  if (!node) return null
  const color = neuronColor(node)
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      style={{
        padding: 'var(--space-3)',
        background: 'rgba(17,17,24,0.95)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: '10px',
        backdropFilter: 'blur(12px)',
        maxWidth: '220px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}` }} />
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>{node.label}</span>
      </div>
      {[
        { l: 'ID', v: node.id },
        { l: 'Type', v: node.type },
        { l: 'Activation', v: (node.activation ?? 0).toFixed(3) },
        { l: 'Confidence', v: `${Math.round((node.confidence ?? 0) * 100)}%` },
        { l: 'Weight', v: node.weight ?? 0 },
        { l: 'Source', v: node.source },
        { l: 'Tag', v: node.tag },
      ].map(({ l, v }) => (
        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '2px 0' }}>
          <span style={{ color: 'var(--text-muted)' }}>{l}</span>
          <span style={{ color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>{v}</span>
        </div>
      ))}
    </motion.div>
  )
}

/* ─── Loss Graph ─── */
function LossGraph({ history }) {
  const svgW = 260
  const svgH = 60
  if (!history || history.length < 2) {
    return (
      <div style={{ height: svgH, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '11px' }}>
        Waiting for loss data…
      </div>
    )
  }
  const maxVal = Math.max(...history, 0.01)
  const points = history.map((v, i) => {
    const x = (i / (history.length - 1)) * svgW
    const y = svgH - (v / maxVal) * (svgH - 8) - 4
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} style={{ display: 'block' }}>
      <polyline
        points={points}
        fill="none"
        stroke="#EF4444"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <polyline
        points={`0,${svgH} ${points} ${svgW},${svgH}`}
        fill="url(#lossGrad)"
        opacity="0.2"
      />
      <defs>
        <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#EF4444" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
    </svg>
  )
}

/* ─── Skill Module clusters ─── */
function SkillModules({ nodes }) {
  const clusters = useMemo(() => {
    const byTag = {}
    nodes.filter(n => n.type === 'Skill' || n.type === 'Strategy').forEach(n => {
      const tag = n.tag || 'general'
      if (!byTag[tag]) byTag[tag] = { tag, count: 0, totalConf: 0 }
      byTag[tag].count++
      byTag[tag].totalConf += (n.confidence || 0)
    })
    return Object.values(byTag)
      .map(c => ({ ...c, avgConf: c.count ? c.totalConf / c.count : 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6)
  }, [nodes])

  if (clusters.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {clusters.map(c => (
        <div key={c.tag} style={{
          display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px',
          padding: '4px 8px', borderRadius: '6px', background: 'rgba(255,255,255,0.03)',
        }}>
          <span style={{ color: 'var(--neon-teal)', fontWeight: 500, flex: 1 }}>{c.tag}</span>
          <span style={{ color: 'var(--text-muted)' }}>{c.count} nodes</span>
          <span style={{ color: 'var(--gold)', fontVariantNumeric: 'tabular-nums' }}>{Math.round(c.avgConf * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

/* ─── Experience Feed ─── */
function ExperienceFeed({ items }) {
  if (!items || items.length === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '12px' }}>
      No experiences recorded yet
    </div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', maxHeight: '140px', overflowY: 'auto' }}>
      {items.slice(0, 8).map((item, i) => (
        <div key={item.id || i} style={{
          display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px',
          padding: '4px 6px', borderRadius: '4px',
          background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: item.type === 'failure' ? 'var(--error)' : item.type === 'learning_update' ? 'var(--success)' : 'var(--neon-teal)',
          }} />
          <span style={{ color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {item.detail || item.strategy || item.type || '—'}
          </span>
          <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
            {item.confidence != null ? `${Math.round(item.confidence * 100)}%` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ─── Decision Flow (synced with brain path) ─── */
function DecisionPath({ decisions, onSelect }) {
  if (!decisions || decisions.length === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '12px' }}>
      No decisions yet — interact with the AI to generate data
    </div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {decisions.slice(0, 6).map((d, i) => (
        <motion.div
          key={d.task_id || i}
          whileHover={{ x: 3 }}
          onClick={() => onSelect && onSelect(d)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px',
            padding: '6px 8px', borderRadius: '6px', cursor: 'pointer',
            background: 'rgba(212,175,55,0.04)', border: '1px solid rgba(212,175,55,0.1)',
          }}
        >
          <span style={{
            width: 18, height: 18, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(212,175,55,0.1)', color: 'var(--gold)', fontSize: '10px', fontWeight: 600, flexShrink: 0,
          }}>
            {i + 1}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {d.intent || 'general'}
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{d.strategy || '—'}</div>
          </div>
          <span style={{ color: 'var(--gold)', fontVariantNumeric: 'tabular-nums' }}>
            {d.confidence != null ? `${Math.round(d.confidence * 100)}%` : ''}
          </span>
        </motion.div>
      ))}
    </div>
  )
}

/* ─── Panel wrapper (glassmorphism) ─── */
function GlassPanel({ title, badge, children, style }) {
  return (
    <div style={{
      background: 'rgba(17,17,24,0.75)',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '12px',
      padding: '12px',
      backdropFilter: 'blur(16px)',
      ...style,
    }}>
      {title && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {title}
          </span>
          {badge && <span style={{ fontSize: '10px', color: 'var(--gold)' }}>{badge}</span>}
        </div>
      )}
      {children}
    </div>
  )
}

/* ═══════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════ */

export default function NeuralBrainPage() {
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const nnStatus = useAppStore(s => s.nnStatus)
  const brainInsights = useAppStore(s => s.brainInsights)
  const brainActivity = useAppStore(s => s.brainActivity)
  const brainStatus = useAppStore(s => s.brainStatus)

  const [neuronData, setNeuronData] = useState({ nodes: [], connections: [], stats: {} })
  const [selectedNode, setSelectedNode] = useState(null)
  const [lossHistory, setLossHistory] = useState([])

  // Poll neurons from backend
  useEffect(() => {
    const controller = new AbortController()
    const fetchNeurons = async () => {
      try {
        const res = await fetch(`${BASE}/api/brain/neurons`, { signal: controller.signal })
        const data = await res.json()
        if (data?.nodes) {
          // Tag new nodes with age for gold glow
          setNeuronData(prev => {
            const prevIds = new Set((prev.nodes || []).map(n => n.id))
            const tagged = (data.nodes || []).map(n => ({
              ...n,
              _age: prevIds.has(n.id) ? (prev.nodes.find(p => p.id === n.id)?._age ?? 10) + 1 : 0,
            }))
            return { ...data, nodes: tagged }
          })
        }
      } catch { /* ignore */ }
    }
    fetchNeurons()
    const i = setInterval(fetchNeurons, 3000)
    return () => { clearInterval(i); controller.abort() }
  }, [])

  // Track loss history
  useEffect(() => {
    if (nnStatus?.last_loss != null) {
      setLossHistory(prev => [...prev.slice(-49), nnStatus.last_loss])
    }
  }, [nnStatus?.last_loss])

  // Canvas animation loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const parent = canvas.parentElement
    let w = parent.clientWidth
    let h = parent.clientHeight
    canvas.width = w * devicePixelRatio
    canvas.height = h * devicePixelRatio
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    ctx.scale(devicePixelRatio, devicePixelRatio)

    const positioned = layoutNodes(neuronData.nodes || [], w, h)

    const animate = (time) => {
      drawBrain(ctx, positioned, neuronData.connections || [], selectedNode?.id, time, w, h)
      rafRef.current = requestAnimationFrame(animate)
    }
    rafRef.current = requestAnimationFrame(animate)

    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [neuronData, selectedNode])

  // Click detection on canvas
  const handleCanvasClick = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const parent = canvas.parentElement
    const w = parent.clientWidth
    const h = parent.clientHeight
    const positioned = layoutNodes(neuronData.nodes || [], w, h)

    let closest = null
    let closestDist = Infinity
    positioned.forEach(n => {
      const d = Math.hypot(n.x - mx, n.y - my)
      if (d < 30 && d < closestDist) {
        closestDist = d
        closest = n
      }
    })
    setSelectedNode(closest)
  }, [neuronData])

  // Compute learning mode from NN status
  const learningMode = nnStatus?.bg_running ? 'Training' : nnStatus?.mode === 'LIVE' ? 'Live Execution' : 'Idle'
  const stats = neuronData.stats || {}
  const recentDecisions = brainActivity?.recent_decisions || brainActivity?.items?.filter(i => i.type === 'decision') || []
  const experiences = brainActivity?.items || []
  const agentWeights = brainStatus?.agent_weights || brainInsights?.agent_weights || {}
  const learnedTopics = brainInsights?.learned_topics || []
  const learningUpdates = brainInsights?.learning_updates || []
  const lastDecision = brainInsights?.last_decision || null
  const lastReward = brainInsights?.last_reward ?? 0
  const topMemories = brainInsights?.top_memories || []
  const learningPanel = brainInsights?.learning_panel || {}
  const memoryUsed = lastDecision?.memory_used || lastDecision?.relevant_memory || {}
  const memoryUsedCount = ['short_term', 'long_term', 'episodic']
    .reduce((total, key) => total + (memoryUsed?.[key]?.length || 0), 0)
  const bestStrategies = learningPanel?.best_performing_strategies || brainInsights?.learned_strategies || []
  const worstStrategies = learningPanel?.worst_performing_strategies || []
  const rewardTrends = learningPanel?.reward_trends || []
  const successRateSeries = learningPanel?.success_rate_over_time || []
  const lastLearningUpdate = brainStatus?.last_learning_update || brainInsights?.last_learning_update || '—'

  return (
    <div className="page-enter" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '0' }}>
      {/* ── TOP BAR ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: '12px 0',
        flexWrap: 'wrap',
      }}>
        <h1 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>🧠</span> Neural Brain
        </h1>
        <span style={{
          fontSize: '11px', padding: '2px 10px', borderRadius: '10px',
          background: nnStatus?.active ? 'rgba(34,197,94,0.1)' : 'rgba(102,102,112,0.1)',
          color: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)',
          border: `1px solid ${nnStatus?.active ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.06)'}`,
        }}>
          {nnStatus?.active ? '● LIVE' : '○ OFFLINE'}
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <StatPill label="Learn Step" value={(stats.learn_step ?? nnStatus?.learn_step ?? 0).toLocaleString()} color="var(--text-primary)" />
          <StatPill label="Confidence" value={`${Math.round((stats.global_confidence ?? nnStatus?.confidence ?? 0) * 100)}%`} color="var(--gold)" />
          <StatPill label="Active Tasks" value={stats.active_tasks ?? 0} color="var(--neon-teal)" />
          <StatPill label="Learning Mode" value={learningMode} color={learningMode === 'Training' ? 'var(--success)' : learningMode === 'Live Execution' ? 'var(--neon-cyan)' : 'var(--text-muted)'} />
        </div>
      </div>

      {/* ── MAIN AREA ── */}
      <div style={{ flex: 1, display: 'flex', gap: 'var(--space-3)', minHeight: 0 }}>

        {/* LEFT CALLOUT */}
        <div style={{ width: '220px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', overflowY: 'auto' }}>
          <GlassPanel title="Selected Neuron">
            {selectedNode ? <NeuronDetail node={selectedNode} /> : (
              <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '16px 0' }}>
                Click a neuron to inspect
              </div>
            )}
          </GlassPanel>

          <GlassPanel title="Legend">
            {Object.entries(NEURON_COLORS).map(([key, color]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', padding: '2px 0' }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
                <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{key}</span>
              </div>
            ))}
          </GlassPanel>
        </div>

        {/* CENTER — BRAIN CANVAS */}
        <div style={{
          flex: 1,
          position: 'relative',
          borderRadius: '14px',
          overflow: 'hidden',
          border: '1px solid rgba(255,255,255,0.06)',
          background: 'radial-gradient(ellipse at 50% 50%, rgba(20,30,60,0.5), rgba(11,11,15,0.95) 70%)',
          minHeight: '400px',
        }}>
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            style={{ width: '100%', height: '100%', cursor: 'crosshair' }}
          />
          {/* Overlay node count */}
          <div style={{
            position: 'absolute', top: 10, left: 12,
            fontSize: '11px', color: 'var(--text-muted)',
            background: 'rgba(0,0,0,0.4)', padding: '2px 8px', borderRadius: '6px',
          }}>
            {neuronData.nodes?.length || 0} nodes · {neuronData.connections?.length || 0} connections
          </div>
        </div>

        {/* RIGHT PANELS */}
        <div style={{ width: '280px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', overflowY: 'auto' }}>
          <GlassPanel title="🧠 Brain Panel" badge={`${stats.total_nodes || 0} nodes`}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '8px' }}>
              <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Active Nodes</div>
                <div style={{ fontSize: '15px', fontWeight: 500, color: 'var(--text-primary)' }}>{stats.total_nodes || 0}</div>
              </div>
              <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Learning Rate</div>
                <div style={{ fontSize: '15px', fontWeight: 500, color: 'var(--success)' }}>{((stats.learning_rate || 0) * 100).toFixed(2)}%</div>
              </div>
              <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Memory Size</div>
                <div style={{ fontSize: '15px', fontWeight: 500, color: 'var(--neon-teal)' }}>{(stats.memory_size || 0).toLocaleString()}</div>
              </div>
              <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Connections</div>
                <div style={{ fontSize: '15px', fontWeight: 500, color: 'var(--info)' }}>{stats.total_connections || 0}</div>
              </div>
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '6px' }}>
              Last decision: {lastDecision?.agent || lastDecision?.skill || '—'}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--gold)' }}>
              Strategy confidence: {Math.round((lastDecision?.confidence || 0) * 100)}%
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
              Why: {lastDecision?.reasoning || lastDecision?.decision_reasoning || '—'}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--neon-teal)' }}>
              Memory used: {memoryUsedCount}
            </div>
          </GlassPanel>

          <GlassPanel title="Skill Modules">
            <SkillModules nodes={neuronData.nodes || []} />
          </GlassPanel>

          <GlassPanel title="Decision Flow" badge="latest path">
            <DecisionPath decisions={recentDecisions} onSelect={(d) => {
              // Highlight the node for this decision in the canvas
              const found = neuronData.nodes?.find(n => n.label?.includes(d.intent))
              if (found) setSelectedNode(found)
            }} />
          </GlassPanel>

          <GlassPanel title="📈 Learning Panel" badge="live RL">
            {Object.keys(agentWeights).length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>No weight data yet</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {Object.entries(agentWeights).map(([agent, weights]) => (
                  <div key={agent} style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '11px', paddingBottom: '4px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{agent}</span>
                    {typeof weights === 'number' ? (
                      <span style={{ color: 'var(--gold)', fontVariantNumeric: 'tabular-nums' }}>{((weights || 0) * 100).toFixed(1)}%</span>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 8px' }}>
                        {Object.entries(weights || {}).map(([feature, value]) => (
                          <div key={`${agent}-${feature}`} style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{feature}</span>
                            <span style={{ color: 'var(--gold)', fontVariantNumeric: 'tabular-nums' }}>{((value || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                  Last reward: {lastReward}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  Success samples: {successRateSeries.length}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--success)' }}>
                  Best strategies: {bestStrategies.length}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--error)' }}>
                  Worst strategies: {worstStrategies.length}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--gold)' }}>
                  Reward trend points: {rewardTrends.length}
                </div>
                <div style={{ marginTop: '2px', fontSize: '10px', color: 'var(--text-muted)' }}>Last learning update: {lastLearningUpdate}</div>
              </div>
            )}
          </GlassPanel>
        </div>
      </div>

      <div style={{ paddingTop: 'var(--space-3)' }}>
        <NeuralGraphPanel />
      </div>

      {/* ── BOTTOM PANELS ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 'var(--space-3)',
        paddingTop: 'var(--space-3)',
        flexShrink: 0,
      }}>
        <GlassPanel title="Loss" badge={lossHistory.length > 0 ? lossHistory[lossHistory.length - 1]?.toFixed(4) : '—'}>
          <LossGraph history={lossHistory} />
        </GlassPanel>

        <GlassPanel title="Experiences" badge={`${experiences.length} events`}>
          <ExperienceFeed items={experiences} />
        </GlassPanel>

        <GlassPanel title="Replay Buffer">
          <div style={{ marginBottom: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Buffer</span>
              <span style={{ color: 'var(--neon-teal)' }}>{(nnStatus?.buffer_size ?? 0).toLocaleString()} / {(nnStatus?.max_buffer_size ?? 0).toLocaleString()}</span>
            </div>
            <div style={{ height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
              <motion.div
                animate={{ width: `${nnStatus?.max_buffer_size ? Math.round((nnStatus.buffer_size / nnStatus.max_buffer_size) * 100) : 0}%` }}
                transition={{ duration: 0.6 }}
                style={{ height: '100%', background: 'var(--neon-teal)', borderRadius: '3px', boxShadow: '0 0 8px rgba(32,214,199,0.3)' }}
              />
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Experiences</span>
            <span style={{ color: 'var(--text-primary)' }}>{(nnStatus?.experiences ?? 0).toLocaleString()}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginTop: '4px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Device</span>
            <span style={{ color: 'var(--text-primary)' }}>{(nnStatus?.device ?? 'cpu').toUpperCase()}</span>
          </div>
        </GlassPanel>

        <GlassPanel title="Network Status">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {[
              { l: 'Mode', v: nnStatus?.mode || 'INITIALIZING', c: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)' },
              { l: 'Learn Step', v: (nnStatus?.learn_step ?? 0).toLocaleString() },
              { l: 'Last Loss', v: nnStatus?.last_loss != null ? nnStatus.last_loss.toFixed(4) : '—', c: 'var(--error)' },
              { l: 'Confidence', v: `${Math.round((nnStatus?.confidence ?? 0) * 100)}%`, c: 'var(--gold)' },
              { l: 'Total Actions', v: nnStatus?.total_actions ?? 0 },
            ].map(({ l, v, c }) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-muted)' }}>{l}</span>
                <span style={{ color: c || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{v}</span>
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel title="📚 Memory Panel" badge={`${learnedTopics.length} topics`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '6px' }}>
            {learnedTopics.length === 0 ? (
              <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>No learned topics yet</span>
            ) : learnedTopics.slice(0, 6).map((topic) => (
              <span key={topic} style={{ color: 'var(--neon-teal)', fontSize: '11px' }}>{topic}</span>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '6px' }}>
            {topMemories.length === 0 ? (
              <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>No ranked memories yet</span>
            ) : topMemories.slice(0, 3).map((m) => (
              <div key={m.id || m.text} style={{ fontSize: '10px', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '4px' }}>
                <div style={{ color: 'var(--text-primary)' }}>{(m.text || '').slice(0, 80) || 'memory'}</div>
                <div>
                  importance: {((m.importance || 0) * 100).toFixed(1)}% · usage: {m.usage_count || 0}
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Learned strategies: {(bestStrategies || []).length}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Past outcomes: {(learningUpdates || []).length}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Research knowledge: {(learnedTopics || []).length}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
            Updates: {learningUpdates.length}
          </div>
        </GlassPanel>
      </div>
    </div>
  )
}
