import { useEffect, useRef, useState, useCallback, useMemo, lazy, Suspense } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import { useBrainStore, GROUP_COLORS } from '../../store/brainStore'
import NeuralGraphPanel from '../dashboard/NeuralGraphPanel'
import { API_URL } from '../../config/api'

const ForceGraph3D = lazy(() => import('react-force-graph-3d'))

const BASE = API_URL
const POLL_INTERVAL = 4000

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

/* ─── Inspector Panel (right side) ─── */
function InspectorPanel({ node, links, onClose }) {
  if (!node) return (
    <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '24px 12px' }}>
      Click a node to inspect
    </div>
  )

  const nodeColor = node.color || GROUP_COLORS[node.group] || '#9A9AA5'
  const connectedLinks = links.filter(
    l => (l.source?.id ?? l.source) === node.id || (l.target?.id ?? l.target) === node.id,
  )
  const connectedIds = new Set()
  connectedLinks.forEach(l => {
    const src = l.source?.id ?? l.source
    const tgt = l.target?.id ?? l.target
    if (src !== node.id) connectedIds.add(src)
    if (tgt !== node.id) connectedIds.add(tgt)
  })

  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 12 }}
      style={{
        padding: '12px',
        background: 'rgba(17,17,24,0.92)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '12px',
        backdropFilter: 'blur(12px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: nodeColor, boxShadow: `0 0 10px ${nodeColor}` }} />
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>{node.label}</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '14px' }}>✕</button>
      </div>
      {[
        { l: 'ID', v: node.id },
        { l: 'Type', v: node.type },
        { l: 'Group', v: node.group },
        { l: 'Weight', v: node.weight ?? 0 },
        { l: 'Confidence', v: `${Math.round((node.confidence ?? 0) * 100)}%` },
        { l: 'Source', v: node.source || '—' },
        { l: 'Tag', v: node.tag || '—' },
        { l: 'Connections', v: connectedIds.size },
      ].map(({ l, v }) => (
        <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
          <span style={{ color: 'var(--text-muted)' }}>{l}</span>
          <span style={{ color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
        </div>
      ))}
      {connectedIds.size > 0 && (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>Connected Nodes</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {Array.from(connectedIds).slice(0, 8).map(cid => (
              <span key={cid} style={{
                fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
                background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}>{cid}</span>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  )
}

/* ─── Legend ─── */
function Legend() {
  return (
    <div style={{
      padding: '12px',
      background: 'rgba(17,17,24,0.75)',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '12px',
      backdropFilter: 'blur(16px)',
    }}>
      <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Legend</div>
      {Object.entries(GROUP_COLORS).map(([key, color]) => (
        <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', padding: '2px 0' }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
          <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{key}</span>
        </div>
      ))}
    </div>
  )
}

/* ─── Glass Panel wrapper ─── */
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
          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{title}</span>
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
  const graphRef = useRef(null)
  const containerRef = useRef(null)
  const nnStatus = useAppStore(s => s.nnStatus)
  const brainActivity = useAppStore(s => s.brainActivity)

  // Brain store (shared state)
  const nodes = useBrainStore(s => s.nodes)
  const links = useBrainStore(s => s.links)
  const stats = useBrainStore(s => s.stats)
  const selectedNodeId = useBrainStore(s => s.selectedNodeId)
  const setSelectedNodeId = useBrainStore(s => s.setSelectedNodeId)
  const setGraph = useBrainStore(s => s.setGraph)

  const [graphDimensions, setGraphDimensions] = useState({ width: 800, height: 500 })
  const [hoveredNode, setHoveredNode] = useState(null)

  // Poll /api/brain/graph
  useEffect(() => {
    const controller = new AbortController()
    const fetchGraph = async () => {
      try {
        const res = await fetch(`${BASE}/api/brain/graph`, { signal: controller.signal })
        if (!res.ok) return
        const data = await res.json()
        setGraph(data)
      } catch {
        // Network error — keep current state
      }
    }
    fetchGraph()
    const timer = setInterval(fetchGraph, POLL_INTERVAL)
    return () => { clearInterval(timer); controller.abort() }
  }, [setGraph])

  // Responsive container sizing
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setGraphDimensions({ width: Math.max(400, width), height: Math.max(300, height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Graph data for ForceGraph3D — build on every nodes/links change
  const graphData = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n })),
    links: links.map(l => ({ ...l })),
  }), [nodes, links])

  // Click handler
  const handleNodeClick = useCallback((node) => {
    setSelectedNodeId(node?.id || null)
    // Focus camera on node
    if (graphRef.current && node) {
      const distance = 120
      const { x, y, z } = node
      graphRef.current.cameraPosition(
        { x: x + distance, y: y + distance / 2, z: z + distance },
        { x, y, z },
        1200,
      )
    }
  }, [setSelectedNodeId])

  // Hover handler
  const handleNodeHover = useCallback((node) => {
    setHoveredNode(node || null)
  }, [])

  const nodeColor = useCallback((node) => {
    if (hoveredNode && hoveredNode.id === node.id) return '#ffffff'
    if (selectedNodeId && selectedNodeId === node.id) return '#ffffff'
    return node.color || GROUP_COLORS[node.group] || '#9A9AA5'
  }, [hoveredNode, selectedNodeId])

  const nodeVal = useCallback((node) => {
    return 1 + Math.min(node.weight || 0, 30) * 0.3
  }, [])

  const linkColor = useCallback((link) => {
    const srcId = link.source?.id ?? link.source
    const tgtId = link.target?.id ?? link.target
    if (hoveredNode && (hoveredNode.id === srcId || hoveredNode.id === tgtId)) return 'rgba(255,215,0,0.6)'
    if (selectedNodeId && (selectedNodeId === srcId || selectedNodeId === tgtId)) return 'rgba(255,215,0,0.4)'
    return 'rgba(255,255,255,0.08)'
  }, [hoveredNode, selectedNodeId])

  const linkWidth = useCallback((link) => {
    const srcId = link.source?.id ?? link.source
    const tgtId = link.target?.id ?? link.target
    if (hoveredNode && (hoveredNode.id === srcId || hoveredNode.id === tgtId)) return 2.5
    return 0.5 + (link.strength || 0.5) * 1.5
  }, [hoveredNode])

  const selectedNode = useMemo(() => nodes.find(n => n.id === selectedNodeId) || null, [nodes, selectedNodeId])

  // Stats derived from brain data
  const learningMode = nnStatus?.bg_running ? 'Training' : nnStatus?.mode === 'LIVE' ? 'Live Execution' : 'Idle'
  const recentDecisions = brainActivity?.recent_decisions || brainActivity?.items?.filter(i => i.type === 'decision') || []
  const experiences = brainActivity?.items || []

  return (
    <div className="page-enter" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0 }}>
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
          <StatPill label="Nodes" value={nodes.length} color="var(--text-primary)" />
          <StatPill label="Connections" value={links.length} color="var(--neon-teal)" />
          <StatPill label="Confidence" value={`${Math.round((stats.global_confidence ?? nnStatus?.confidence ?? 0) * 100)}%`} color="var(--gold)" />
          <StatPill label="Learning Mode" value={learningMode} color={learningMode === 'Training' ? 'var(--success)' : learningMode === 'Live Execution' ? 'var(--neon-cyan)' : 'var(--text-muted)'} />
        </div>
      </div>

      {/* ── MAIN AREA ── */}
      <div style={{ flex: 1, display: 'flex', gap: 'var(--space-3)', minHeight: 0 }}>

        {/* LEFT PANELS */}
        <div style={{ width: '220px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', overflowY: 'auto' }}>
          <AnimatePresence mode="wait">
            <InspectorPanel
              key={selectedNodeId || 'empty'}
              node={selectedNode}
              links={links}
              onClose={() => setSelectedNodeId(null)}
            />
          </AnimatePresence>
          <Legend />
        </div>

        {/* CENTER — 3D BRAIN GRAPH */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            position: 'relative',
            borderRadius: '14px',
            overflow: 'hidden',
            border: '1px solid rgba(255,255,255,0.06)',
            background: '#0a0a0a',
            minHeight: '400px',
          }}
        >
          <Suspense fallback={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '13px' }}>
              Loading 3D visualization…
            </div>
          }>
            <ForceGraph3D
              ref={graphRef}
              graphData={graphData}
              width={graphDimensions.width}
              height={graphDimensions.height}
              backgroundColor="#0a0a0a"
              nodeLabel="label"
              nodeColor={nodeColor}
              nodeVal={nodeVal}
              nodeOpacity={0.9}
              nodeResolution={12}
              linkColor={linkColor}
              linkWidth={linkWidth}
              linkOpacity={0.6}
              linkDirectionalParticles={2}
              linkDirectionalParticleWidth={1.5}
              linkDirectionalParticleSpeed={0.005}
              linkDirectionalParticleColor={() => 'rgba(255,215,0,0.4)'}
              onNodeClick={handleNodeClick}
              onNodeHover={handleNodeHover}
              enableNodeDrag={false}
              warmupTicks={40}
              cooldownTicks={60}
              d3AlphaDecay={0.04}
              d3VelocityDecay={0.3}
            />
          </Suspense>

          {/* Overlay node count */}
          <div style={{
            position: 'absolute', top: 10, left: 12,
            fontSize: '11px', color: 'var(--text-muted)',
            background: 'rgba(0,0,0,0.6)', padding: '2px 8px', borderRadius: '6px',
            pointerEvents: 'none',
          }}>
            {nodes.length} nodes · {links.length} connections
          </div>
        </div>

        {/* RIGHT PANELS */}
        <div style={{ width: '260px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', overflowY: 'auto' }}>
          <GlassPanel title="🧠 Brain Status" badge={nnStatus?.mode || 'INIT'}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '8px' }}>
              {[
                { l: 'Active Nodes', v: stats.total_nodes ?? nodes.length, c: 'var(--text-primary)' },
                { l: 'Memory Size', v: (stats.memory_size ?? nnStatus?.memory_size ?? 0).toLocaleString(), c: 'var(--neon-teal)' },
                { l: 'Learn Step', v: (stats.learn_step ?? nnStatus?.learn_step ?? 0).toLocaleString(), c: 'var(--gold)' },
                { l: 'Device', v: (nnStatus?.device ?? 'cpu').toUpperCase(), c: 'var(--text-primary)' },
              ].map(({ l, v, c }) => (
                <div key={l} style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{l}</div>
                  <div style={{ fontSize: '14px', fontWeight: 500, color: c }}>{v}</div>
                </div>
              ))}
            </div>
          </GlassPanel>

          <GlassPanel title="Decision Flow" badge="latest">
            {recentDecisions.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '12px' }}>
                No decisions yet — interact with the AI to generate data
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {recentDecisions.slice(0, 6).map((d, i) => (
                  <div
                    key={d.task_id || i}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px',
                      padding: '5px 8px', borderRadius: '6px',
                      background: 'rgba(212,175,55,0.04)', border: '1px solid rgba(212,175,55,0.1)',
                    }}
                  >
                    <span style={{
                      width: 16, height: 16, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(212,175,55,0.1)', color: 'var(--gold)', fontSize: '9px', fontWeight: 600, flexShrink: 0,
                    }}>
                      {i + 1}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {d.intent || 'general'}
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{d.strategy || '—'}</div>
                    </div>
                    <span style={{ color: 'var(--gold)', fontVariantNumeric: 'tabular-nums', fontSize: '10px' }}>
                      {d.confidence != null ? `${Math.round(d.confidence * 100)}%` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </GlassPanel>

          <GlassPanel title="Experiences" badge={`${experiences.length} events`}>
            {experiences.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '12px' }}>No experiences recorded yet</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', maxHeight: '140px', overflowY: 'auto' }}>
                {experiences.slice(0, 8).map((item, i) => (
                  <div key={item.id || i} style={{
                    display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px',
                    padding: '3px 6px', borderRadius: '4px',
                    background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                  }}>
                    <span style={{
                      width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                      background: item.type === 'failure' ? 'var(--error)' : item.type === 'learning_update' ? 'var(--success)' : 'var(--neon-teal)',
                    }} />
                    <span style={{ color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.detail || item.strategy || item.type || '—'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </GlassPanel>

          <GlassPanel title="Network Status">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {[
                { l: 'Mode', v: nnStatus?.mode || 'INIT', c: nnStatus?.active ? 'var(--success)' : 'var(--text-muted)' },
                { l: 'Learn Step', v: (nnStatus?.learn_step ?? 0).toLocaleString() },
                { l: 'Last Loss', v: nnStatus?.last_loss != null ? nnStatus.last_loss.toFixed(4) : '—', c: 'var(--error)' },
                { l: 'Confidence', v: `${Math.round((nnStatus?.confidence ?? 0) * 100)}%`, c: 'var(--gold)' },
                { l: 'BG Loop', v: nnStatus?.bg_running ? '● ACTIVE' : '○ IDLE' },
              ].map(({ l, v, c }) => (
                <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{l}</span>
                  <span style={{ color: c || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{v}</span>
                </div>
              ))}
            </div>
          </GlassPanel>
        </div>
      </div>

      {/* ── BOTTOM — Decision graph panel ── */}
      <div style={{ paddingTop: 'var(--space-3)' }}>
        <NeuralGraphPanel />
      </div>
    </div>
  )
}
