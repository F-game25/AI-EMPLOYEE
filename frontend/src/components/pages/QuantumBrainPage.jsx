import { useState, useEffect, useRef, useCallback } from 'react'

const BANG_CHIPS = ['!web', '!memory', '!code', '!graph', '!agent', '!tool']
const COMPLEXITY_OPTS = ['simple', 'medium', 'complex', 'critical']

const SOURCE_COLORS = {
  web: '#3b82f6', memory: '#8b5cf6', agent: '#10b981',
  code: '#f59e0b', tool: '#ef4444', doc: '#6b7280',
}
const nodeColor = t => SOURCE_COLORS[t] || '#94a3b8'

const SOURCE_ICONS = {
  web: '🌐', memory: '🧠', agent: '🤖', code: '{}', tool: '🔧', doc: '📄',
}
const iconFor = t => SOURCE_ICONS[t] || '📌'

// ── Canvas renderer ────────────────────────────────────────────────────────────

function QCECanvas({ nodes, edges, selected, onSelect }) {
  const canvasRef = useRef(null)
  const stateRef = useRef({ nodes: [], links: [], raf: 0, t: 0, selected: null })
  const simNodes = stateRef.current

  // Sync props → simulation
  useEffect(() => {
    const sim = stateRef.current
    const prev = new Map(sim.nodes.map(n => [n.id, n]))
    const W = canvasRef.current?.clientWidth || 700
    const H = canvasRef.current?.clientHeight || 500
    sim.nodes = nodes.map(n => {
      const old = prev.get(n.id)
      return old
        ? Object.assign(old, { amplitude: n.amplitude, source_type: n.source_type, label: n.label })
        : { ...n, x: W / 2 + (Math.random() - 0.5) * 300, y: H / 2 + (Math.random() - 0.5) * 300, vx: 0, vy: 0, born: sim.t }
    })
    const ids = new Set(sim.nodes.map(n => n.id))
    sim.links = edges.filter(e => {
      const s = typeof e.source === 'object' ? e.source.id : e.source
      const t = typeof e.target === 'object' ? e.target.id : e.target
      return ids.has(s) && ids.has(t)
    })
    sim.selected = selected
  }, [nodes, edges, selected])

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

    const byId = id => stateRef.current.nodes.find(n => n.id === id)

    const step = () => {
      const sim = stateRef.current
      sim.t += 1
      const { nodes: ns, links } = sim

      // Repulsion
      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const a = ns[i], b = ns[j]
          let dx = a.x - b.x, dy = a.y - b.y
          const d2 = dx * dx + dy * dy || 0.01
          const d = Math.sqrt(d2)
          const f = 900 / d2
          a.vx += dx / d * f; a.vy += dy / d * f
          b.vx -= dx / d * f; b.vy -= dy / d * f
        }
      }
      // Springs
      links.forEach(l => {
        const s = byId(typeof l.source === 'object' ? l.source.id : l.source)
        const t = byId(typeof l.target === 'object' ? l.target.id : l.target)
        if (!s || !t) return
        const dx = t.x - s.x, dy = t.y - s.y
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01
        const f = (d - 100) * 0.01
        s.vx += dx / d * f; s.vy += dy / d * f
        t.vx -= dx / d * f; t.vy -= dy / d * f
      })
      // Centre gravity + integrate
      ns.forEach(n => {
        n.vx += (W / 2 - n.x) * 0.002; n.vy += (H / 2 - n.y) * 0.002
        n.vx *= 0.85; n.vy *= 0.85
        n.x += n.vx; n.y += n.vy
      })

      // Draw
      ctx.clearRect(0, 0, W, H)
      const pulse = 0.5 + 0.5 * Math.sin(sim.t * 0.06)

      // Edges
      ctx.lineWidth = 1
      links.forEach(l => {
        const s = byId(typeof l.source === 'object' ? l.source.id : l.source)
        const t = byId(typeof l.target === 'object' ? l.target.id : l.target)
        if (!s || !t) return
        const bothHigh = (s.amplitude || 0) > 0.7 && (t.amplitude || 0) > 0.7
        const isConstructive = l.type === 'constructive'
        const isDestructive = l.type === 'destructive'
        ctx.strokeStyle = isConstructive || bothHigh ? 'rgba(6,182,212,0.45)'
          : isDestructive ? 'rgba(239,68,68,0.35)'
          : 'rgba(55,65,81,0.6)'
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke()
      })

      // Nodes
      ns.forEach(n => {
        const amp = n.amplitude || 0
        const r = amp * 20 + 5
        const col = nodeColor(n.source_type)
        const isSel = sim.selected === n.id
        const fadeIn = Math.min(1, (sim.t - (n.born || 0)) / 24)

        // Glow for amplitude
        if (amp > 0.3) {
          ctx.shadowColor = col; ctx.shadowBlur = amp * 18 * fadeIn
        }

        // Pulsing ring for selected
        if (isSel) {
          ctx.beginPath(); ctx.arc(n.x, n.y, r + 6 + pulse * 5, 0, Math.PI * 2)
          ctx.strokeStyle = col + 'aa'; ctx.lineWidth = 2; ctx.stroke()
        }

        ctx.shadowBlur = 0
        ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.fillStyle = hexA(col, 0.85 * fadeIn); ctx.fill()
        ctx.strokeStyle = hexA(col, fadeIn); ctx.lineWidth = isSel ? 2 : 1; ctx.stroke()

        // Label
        if (ns.length <= 40 || isSel) {
          ctx.fillStyle = `rgba(236,234,216,0.75)`
          ctx.font = '10px ui-sans-serif, system-ui'
          ctx.fillText((n.label || n.id || '').slice(0, 18), n.x + r + 3, n.y + 3)
        }
      })

      sim.raf = requestAnimationFrame(step)
    }
    sim.raf = requestAnimationFrame(step)

    const onClick = (e) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      let best = null, bd = 20
      stateRef.current.nodes.forEach(n => {
        const r = (n.amplitude || 0) * 20 + 5
        const d = Math.hypot(n.x - mx, n.y - my)
        if (d < r + 4 && d < bd) { bd = d; best = n.id }
      })
      onSelect(best)
    }
    canvas.addEventListener('click', onClick)

    return () => {
      cancelAnimationFrame(stateRef.current.raf)
      ro.disconnect()
      canvas.removeEventListener('click', onClick)
    }
  }, [onSelect])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', display: 'block', cursor: 'crosshair' }}
      aria-label="Quantum brain candidate graph"
    />
  )
}

function hexA(hex, a) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`
}

// ── AmplitudeTimeline ─────────────────────────────────────────────────────────

function AmplitudeTimeline({ rounds }) {
  if (!rounds?.length) return null
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: '100%', padding: '8px 16px' }}>
      {rounds.map((r, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
          <div style={{
            width: '100%', borderRadius: 3,
            background: `linear-gradient(to top, #06b6d4, #8b5cf6)`,
            height: `${Math.max(4, (r.avg_amplitude || 0) * 70)}%`,
            opacity: 0.7 + 0.3 * (i / rounds.length),
            transition: 'height 0.4s ease',
          }} />
          <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>R{r.round ?? i + 1}</span>
        </div>
      ))}
    </div>
  )
}

// ── DetailPanel ───────────────────────────────────────────────────────────────

function DetailPanel({ candidate, onClose, onUseContext }) {
  if (!candidate) return null
  const amp = candidate.amplitude || 0
  return (
    <div style={{
      width: 320, flexShrink: 0, borderLeft: '1px solid rgba(255,255,255,0.07)',
      background: 'rgba(10,11,15,0.85)', overflowY: 'auto',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <span style={{ fontSize: 11, letterSpacing: '0.1em', color: 'rgba(255,255,255,0.4)' }}>CANDIDATE DETAIL</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: 16 }}>×</button>
      </div>

      <div style={{ padding: '16px', flex: 1 }}>
        <div style={{ fontSize: 14, color: '#e8e6d9', marginBottom: 8, fontWeight: 500 }}>
          {candidate.title || candidate.label || candidate.id}
        </div>

        {/* Source type badge */}
        <div style={{ marginBottom: 14 }}>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 4,
            background: nodeColor(candidate.source_type) + '22',
            color: nodeColor(candidate.source_type),
            border: `1px solid ${nodeColor(candidate.source_type)}44`,
          }}>
            {iconFor(candidate.source_type)} {candidate.source_type || 'unknown'}
          </span>
        </div>

        {/* Amplitude bar */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginBottom: 5 }}>AMPLITUDE</div>
          <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 3,
              background: 'linear-gradient(to right, #06b6d4, #8b5cf6)',
              width: `${Math.round(amp * 100)}%`,
              transition: 'width 0.4s ease',
            }} />
          </div>
          <div style={{ fontSize: 10, color: '#06b6d4', marginTop: 3 }}>{(amp * 100).toFixed(1)}%</div>
        </div>

        {/* Oracle score breakdown */}
        {candidate.oracle_scores && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginBottom: 6 }}>ORACLE SCORES</div>
            {Object.entries(candidate.oracle_scores).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'rgba(255,255,255,0.6)', marginBottom: 3 }}>
                <span>{k}</span>
                <span style={{ color: '#e5c76b' }}>{typeof v === 'number' ? v.toFixed(2) : v}</span>
              </div>
            ))}
          </div>
        )}

        {/* Why selected */}
        {candidate.why_selected && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginBottom: 5 }}>WHY SELECTED</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', lineHeight: 1.5 }}>
              {candidate.why_selected}
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <button
          onClick={() => onUseContext(candidate)}
          style={{
            width: '100%', padding: '8px', borderRadius: 8,
            background: 'rgba(6,182,212,0.15)', border: '1px solid rgba(6,182,212,0.3)',
            color: '#06b6d4', cursor: 'pointer', fontSize: 12,
            fontFamily: 'var(--nx-font-mono, monospace)',
          }}
        >
          Use as context
        </button>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function QuantumBrainPage() {
  const [query, setQuery] = useState('')
  const [activeBangs, setActiveBangs] = useState([])
  const [complexity, setComplexity] = useState('simple')
  const [loading, setLoading] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [engineStats, setEngineStats] = useState(null)
  const [confidence, setConfidence] = useState(null)
  const [topAgents, setTopAgents] = useState([])
  const [rounds, setRounds] = useState([])
  const [selected, setSelected] = useState(null)

  const graphNodes = candidates.map(c => ({
    id: c.id || c.title || Math.random().toString(36).slice(2),
    label: c.title || c.label || c.id || '',
    amplitude: c.amplitude || 0,
    source_type: c.source_type || 'doc',
    ...c,
  }))

  // Build edges: same source_type, max 3 per node
  const graphEdges = (() => {
    const edges = []
    const edgeCounts = {}
    for (let i = 0; i < graphNodes.length; i++) {
      const a = graphNodes[i]
      let count = edgeCounts[a.id] || 0
      for (let j = i + 1; j < graphNodes.length; j++) {
        if (count >= 3) break
        const b = graphNodes[j]
        if (a.source_type === b.source_type) {
          edges.push({ source: a.id, target: b.id })
          count++
          edgeCounts[a.id] = count
        }
      }
    }
    return edges
  })()

  const selectedCandidate = graphNodes.find(n => n.id === selected) || null

  const toggleBang = (bang) => {
    setActiveBangs(prev => prev.includes(bang) ? prev.filter(b => b !== bang) : [...prev, bang])
  }

  const buildQuery = () => {
    const bangs = activeBangs.join(' ')
    return bangs ? `${query} ${bangs}` : query
  }

  const doSearch = useCallback(async () => {
    const q = buildQuery()
    if (!q.trim()) return
    setLoading(true)
    const token = sessionStorage.getItem('ai_jwt')
    try {
      const res = await fetch('/api/search/context-pack', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: q, complexity }),
      })
      const data = res.ok ? await res.json() : {}
      setCandidates(Array.isArray(data.candidates) ? data.candidates : [])
      setConfidence(data.confidence ?? null)
      setTopAgents(Array.isArray(data.top_agents) ? data.top_agents : [])
      setEngineStats(data.engine_stats || null)
      // Build amplification rounds from candidates if not provided
      const ampRounds = Array.isArray(data.amplification_rounds)
        ? data.amplification_rounds
        : Array.from({ length: 3 }, (_, i) => ({
            round: i + 1,
            avg_amplitude: (data.candidates || []).reduce((s, c) => s + (c.amplitude || 0), 0) / Math.max(1, (data.candidates || []).length) * (0.7 + i * 0.15),
          }))
      setRounds(ampRounds)
    } catch {
      setCandidates([])
    } finally {
      setLoading(false)
    }
  }, [query, activeBangs, complexity]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleUseContext = (candidate) => {
    window.dispatchEvent(new CustomEvent('nx:use-context', { detail: candidate }))
  }

  // Subscribe to QCE WS event
  useEffect(() => {
    const handler = (e) => {
      const { type, data } = e.detail || {}
      if (type === 'qce:context_pack_ready' && data?.candidates) {
        setCandidates(data.candidates)
        if (data.confidence != null) setConfidence(data.confidence)
        if (Array.isArray(data.top_agents)) setTopAgents(data.top_agents)
        if (data.engine_stats) setEngineStats(data.engine_stats)
      }
    }
    window.addEventListener('ws:event', handler)
    return () => window.removeEventListener('ws:event', handler)
  }, [])

  return (
    <div style={{
      flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column',
      background: 'var(--bg-base, #050608)', color: '#e8e6d9',
      fontFamily: 'var(--nx-font-mono, monospace)',
    }}>
      {/* Main three-panel row */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>

        {/* Left sidebar */}
        <div style={{
          width: 288, flexShrink: 0, borderRight: '1px solid rgba(255,255,255,0.07)',
          background: 'rgba(10,11,15,0.7)', display: 'flex', flexDirection: 'column',
          padding: 16, gap: 14, overflowY: 'auto',
        }}>
          <div style={{ fontSize: 11, letterSpacing: '0.1em', color: 'rgba(255,255,255,0.35)' }}>QUANTUM BRAIN SEARCH</div>

          {/* Query input */}
          <div style={{ position: 'relative' }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') doSearch() }}
              placeholder="Search context-pack…"
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8, padding: '9px 12px', color: '#e8e6d9',
                fontSize: 13, fontFamily: 'inherit', outline: 'none',
              }}
            />
          </div>

          {/* Bang chips */}
          <div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 6 }}>FILTER BANG</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {BANG_CHIPS.map(b => (
                <button
                  key={b}
                  onClick={() => toggleBang(b)}
                  style={{
                    padding: '3px 9px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
                    fontFamily: 'inherit',
                    background: activeBangs.includes(b) ? 'rgba(229,199,107,0.15)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${activeBangs.includes(b) ? 'rgba(229,199,107,0.4)' : 'rgba(255,255,255,0.1)'}`,
                    color: activeBangs.includes(b) ? '#e5c76b' : 'rgba(255,255,255,0.5)',
                  }}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          {/* Complexity */}
          <div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 6 }}>COMPLEXITY</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {COMPLEXITY_OPTS.map(c => (
                <button
                  key={c}
                  onClick={() => setComplexity(c)}
                  style={{
                    flex: 1, padding: '4px 2px', borderRadius: 5, fontSize: 10, cursor: 'pointer',
                    fontFamily: 'inherit',
                    background: complexity === c ? 'rgba(6,182,212,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${complexity === c ? 'rgba(6,182,212,0.4)' : 'rgba(255,255,255,0.08)'}`,
                    color: complexity === c ? '#06b6d4' : 'rgba(255,255,255,0.4)',
                  }}
                >
                  {c.slice(0, 3).toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Search button */}
          <button
            onClick={doSearch}
            disabled={loading}
            style={{
              padding: '10px', borderRadius: 8, cursor: loading ? 'not-allowed' : 'pointer',
              background: loading ? 'rgba(6,182,212,0.07)' : 'rgba(6,182,212,0.15)',
              border: '1px solid rgba(6,182,212,0.3)', color: '#06b6d4',
              fontSize: 12, fontFamily: 'inherit',
            }}
          >
            {loading ? 'Searching…' : 'Search Context Pack'}
          </button>

          {/* Confidence badge */}
          {confidence != null && (
            <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 3 }}>CONFIDENCE</div>
              <div style={{ fontSize: 18, color: '#10b981', fontWeight: 600 }}>{(confidence * 100).toFixed(0)}%</div>
            </div>
          )}

          {/* Engine stats */}
          {engineStats && (
            <div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 6 }}>ENGINE STATS</div>
              {Object.entries(engineStats).map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 3 }}>
                  <span>{k}</span>
                  <span style={{ color: '#e5c76b' }}>{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Top agents */}
          {topAgents.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 6 }}>TOP AGENTS</div>
              {topAgents.slice(0, 5).map((a, i) => (
                <div key={i} style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ color: '#10b981' }}>🤖</span>
                  {a.id || a.name || String(a)}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Center canvas */}
        <div style={{ flex: 1, minWidth: 0, position: 'relative', background: 'rgba(5,6,8,0.95)' }}>
          {candidates.length === 0 && !loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.2)',
              fontSize: 13, gap: 8,
            }}>
              <span style={{ fontSize: 32 }}>⚛</span>
              <span>Search to populate the quantum candidate graph</span>
            </div>
          )}
          {loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#06b6d4', fontSize: 12,
            }}>
              Amplifying candidates…
            </div>
          )}
          <QCECanvas
            nodes={graphNodes}
            edges={graphEdges}
            selected={selected}
            onSelect={setSelected}
          />
          {/* Graph overlay label */}
          <div style={{
            position: 'absolute', bottom: 12, left: 12,
            fontSize: 10, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.2)',
          }}>
            QUANTUM CANDIDATE GRAPH · {candidates.length} nodes
          </div>
        </div>

        {/* Right detail panel */}
        <DetailPanel
          candidate={selectedCandidate}
          onClose={() => setSelected(null)}
          onUseContext={handleUseContext}
        />
      </div>

      {/* Bottom timeline strip */}
      <div style={{
        height: 96, borderTop: '1px solid rgba(255,255,255,0.07)',
        background: 'rgba(5,6,8,0.9)', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ fontSize: 10, letterSpacing: '0.1em', color: 'rgba(255,255,255,0.2)', padding: '6px 16px 0' }}>
          AMPLIFICATION TIMELINE
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <AmplitudeTimeline rounds={rounds} />
        </div>
      </div>
    </div>
  )
}
