import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import MemoryGraphCanvas from '../graph/MemoryGraphCanvas'
import './GraphsPage.css'

/* Four living memory graphs (WS3). One tabbed canvas — the unified view is the
   whole-system neural network; the other three are the categorised lanes.
   Polls every 4s so the graph stays alive as memory + tasks change. */

const VIEWS = [
  { id: 'unified',   label: 'Unified',    blurb: 'Everything connected + live tasks — the whole living brain.' },
  { id: 'longterm',  label: 'Long-term',  blurb: 'Persistent knowledge (semantic + procedural) in the vector store.' },
  { id: 'shortterm', label: 'Short-term', blurb: 'Recent episodic memory — nodes fade as they decay toward expiry.' },
  { id: 'relations', label: 'Relations',  blurb: 'Concept↔concept links from the knowledge graph.' },
]
const HINTS = {
  unified: 'No memory or tasks yet — the graph fills as the system works.',
  longterm: 'No long-term knowledge stored yet.',
  shortterm: 'Short-term memory is empty (nothing active right now).',
  relations: 'No concept relations recorded yet.',
}

export default function GraphsPage() {
  const [view, setView] = useState('unified')
  const [data, setData] = useState({ nodes: [], links: [], stats: {} })
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const live = useRef(true)

  const fetchView = useCallback(async (v) => {
    try {
      setErr(null)
      const d = await api.get(`/api/memory/graph/${v}?limit=400`)
      setData(d || { nodes: [], links: [] })
    } catch (e) {
      setErr(e.message || 'Graph offline')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    fetchView(view)
    const i = setInterval(() => { if (live.current) fetchView(view) }, 4000)
    return () => clearInterval(i)
  }, [view, fetchView])

  const meta = VIEWS.find(v => v.id === view)
  const stats = data?.stats || {}

  return (
    <div className="mg-page">
      <header className="mg-head">
        <div>
          <h1>Memory Graphs</h1>
          <p className="mg-sub">{meta?.blurb}</p>
        </div>
        <div className="mg-stats">
          <span className="mg-chip">{data?.nodes?.length || 0} nodes</span>
          <span className="mg-chip">{data?.links?.length || 0} links</span>
          {stats.sources && (
            <span className="mg-chip mg-chip--src">
              LT {stats.sources.longterm} · ST {stats.sources.shortterm} · REL {stats.sources.relations}
            </span>
          )}
          <button className={`mg-live ${live.current ? 'mg-live--on' : ''}`} onClick={() => { live.current = !live.current; setView(v => v) }}
            aria-pressed={live.current} aria-label={live.current ? 'Live updates on — click to pause' : 'Live updates paused — click to resume'}>
            ● Live
          </button>
        </div>
      </header>

      <nav className="mg-tabs" role="tablist" aria-label="Memory graph views">
        {VIEWS.map(v => (
          <button key={v.id} role="tab" aria-selected={view === v.id} aria-label={`${v.label} graph`}
            className={`mg-tab ${view === v.id ? 'mg-tab--active' : ''}`} onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </nav>

      {err && <div className="mg-note mg-note--err">⚠ {err}</div>}

      <div className="mg-stage">
        {loading
          ? <div className="mg-note">Loading {meta?.label} graph…</div>
          : <MemoryGraphCanvas data={data} emptyHint={HINTS[view]} />}
      </div>

      <footer className="mg-legend">
        <span><i style={{ background: '#FFD700' }} />Money</span>
        <span><i style={{ background: '#60A5FA' }} />Semantic</span>
        <span><i style={{ background: '#20D6C7' }} />Episodic</span>
        <span><i style={{ background: '#9333EA' }} />Memory/Concept</span>
        <span><i style={{ background: '#E5C76B' }} />Agent/Task</span>
      </footer>
    </div>
  )
}
