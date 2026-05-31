import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import './ProofCenter.css'

const FILTERS = ['all', 'file', 'trace', 'memory_trace', 'fallback', 'provider_response', 'approval', 'task_error']

function fmt(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

function statusClass(item) {
  if (item?.degraded) return 'degraded'
  const status = String(item?.status || 'unknown').toLowerCase()
  if (status.includes('fail') || status.includes('error')) return 'failed'
  if (status.includes('fallback') || status.includes('degraded')) return 'degraded'
  if (status.includes('available') || status.includes('complete') || status.includes('live')) return 'live'
  return 'unknown'
}

function normalizeItems(data) {
  const proof = Array.isArray(data?.proof_items) ? data.proof_items : []
  const artifacts = Array.isArray(data?.artifacts) ? data.artifacts : []
  return [...proof, ...artifacts].map((item, index) => ({
    id: item.id || `proof:${index}`,
    name: item.name || item.label || item.type || 'Proof item',
    type: item.type || 'trace',
    status: item.status || 'unknown',
    source: item.source || 'unknown',
    task_id: item.task_id || null,
    turn_id: item.turn_id || null,
    path: item.path || null,
    url: item.url || null,
    created_at: item.created_at || null,
    degraded: item.degraded === true,
  }))
}

function EmptyState({ title, detail, action }) {
  return (
    <div className="proof-empty">
      <b>{title}</b>
      <span>{detail}</span>
      {action}
    </div>
  )
}

export default function ProofCenter() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get('/api/proof/center'))
    } catch (err) {
      setError(err?.message || 'Proof Center unavailable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const items = useMemo(() => normalizeItems(data), [data])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter(item => {
      const typeMatch = filter === 'all' || item.type === filter || item.status === filter
      if (!typeMatch) return false
      if (!q) return true
      return [item.name, item.type, item.status, item.source, item.task_id, item.turn_id]
        .filter(Boolean)
        .some(value => String(value).toLowerCase().includes(q))
    })
  }, [items, filter, query])

  const turns = Array.isArray(data?.turns) ? data.turns : []
  const degradedCount = items.filter(item => item.degraded || statusClass(item) === 'degraded').length
  const failedCount = items.filter(item => statusClass(item) === 'failed').length

  return (
    <main className="proof-center">
      <section className="proof-hero">
        <div>
          <p className="proof-kicker">PROOF CENTER</p>
          <h1>Execution Evidence</h1>
          <p>Generated files, traces, dry-run outputs, provider responses, approval records, and failed tool logs in one place.</p>
        </div>
        <button type="button" className="proof-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing' : 'Refresh'}
        </button>
      </section>

      <section className="proof-metrics">
        <div><span>Proof items</span><b>{items.length}</b></div>
        <div><span>Turns</span><b>{turns.length}</b></div>
        <div><span>Degraded</span><b>{degradedCount}</b></div>
        <div><span>Failed</span><b>{failedCount}</b></div>
      </section>

      {error && <div className="proof-alert">{error}</div>}

      <section className="proof-tools">
        <div className="proof-filters">
          {FILTERS.map(option => (
            <button
              key={option}
              type="button"
              className={filter === option ? 'proof-filter proof-filter--active' : 'proof-filter'}
              onClick={() => setFilter(option)}
            >
              {option.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
        <input
          className="proof-search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Filter by task, turn, source, status, or artifact"
        />
      </section>

      <section className="proof-layout">
        <div className="proof-panel">
          <div className="proof-panel__head">
            <p className="proof-kicker">ARTIFACTS AND PROOF</p>
            <span>{filtered.length} visible</span>
          </div>
          <div className="proof-list">
            {filtered.map(item => (
              <article key={item.id} className={`proof-item proof-item--${statusClass(item)}`}>
                <div className="proof-item__main">
                  <span className="proof-item__dot" />
                  <div>
                    <h2>{item.name}</h2>
                    <p>{item.type} - {item.source} - {fmt(item.created_at)}</p>
                    {(item.turn_id || item.task_id) && (
                      <code>{item.turn_id || 'no-turn'} / {item.task_id || 'no-task'}</code>
                    )}
                  </div>
                </div>
                <div className="proof-item__side">
                  <span>{item.degraded ? 'degraded' : item.status}</span>
                  {item.url && <a href={item.url} target="_blank" rel="noreferrer">Open</a>}
                </div>
              </article>
            ))}
            {!filtered.length && (
              <EmptyState
                title="No proof items match this view"
                detail="Run a safe task from Chat, Operations, or Setup Center to generate fresh proof."
              />
            )}
          </div>
        </div>

        <aside className="proof-panel proof-panel--turns">
          <div className="proof-panel__head">
            <p className="proof-kicker">RECENT TURNS</p>
            <span>{turns.length}</span>
          </div>
          <div className="proof-turns">
            {turns.slice(0, 18).map(turn => (
              <div key={turn.turn_id || turn.task_id} className={`proof-turn proof-turn--${turn.degraded ? 'degraded' : turn.status}`}>
                <div>
                  <b>{turn.turn_id || turn.task_id || 'Turn'}</b>
                  <span>{turn.source} - {turn.status}</span>
                </div>
                <small>{turn.proof_count || 0} proof / {turn.artifact_count || 0} artifacts</small>
              </div>
            ))}
            {!turns.length && (
              <EmptyState
                title="No canonical turns recorded"
                detail="The turn log will populate when chat or task execution runs through the canonical runner."
              />
            )}
          </div>
        </aside>
      </section>
    </main>
  )
}
