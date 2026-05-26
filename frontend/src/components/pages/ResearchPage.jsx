import { useState, useEffect } from 'react'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useAppStore } from '../../store/appStore'
import { Panel, SectionLabel } from '../nexus-ui'
import ResearchActivityPanel from '../dashboard/ResearchActivityPanel'
import './ResearchPage.css'

// ── Constants ─────────────────────────────────────────────────────────────────
const SUGGESTED = [
  'AI agent frameworks 2026', 'competitor pricing analysis', 'LLM cost benchmarks',
  'enterprise automation trends', 'vector database comparison', 'RAG optimization strategies',
]

const TYPES  = ['all', 'academic', 'docs', 'forum', 'social', 'news', 'web']
const DEPTHS = [
  { id: 'shallow', label: 'SHALLOW', sub: '1 hop · 3 pages · ~30s' },
  { id: 'normal',  label: 'NORMAL',  sub: '2 hops · 6 pages · ~1.5min' },
  { id: 'deep',    label: 'DEEP',    sub: '3 hops · 10 pages · ~3min' },
]

const authHeaders = () => {
  const t = sessionStorage.getItem('ai_jwt') || ''
  return { 'content-type': 'application/json', ...(t ? { authorization: `Bearer ${t}` } : {}) }
}

// ── Reusable bits kept from prior version ─────────────────────────────────────
function ScreenshotThumb({ b64 }) {
  const [expanded, setExpanded] = useState(false)
  if (!b64) return null
  return (
    <div className="rp-screenshot-wrap">
      <img
        src={`data:image/png;base64,${b64}`}
        alt="Page screenshot"
        className={`rp-screenshot${expanded ? ' rp-screenshot--expanded' : ''}`}
        onClick={() => setExpanded(v => !v)}
        title="Click to expand"
      />
      <span className="rp-screenshot-hint">VISUAL</span>
    </div>
  )
}

function RelevanceBar({ value }) {
  const color = value >= 90 ? '#22c55e' : value >= 75 ? '#e5c76b' : '#f59e0b'
  return (
    <div className="rp-relevance">
      <div className="rp-relevance__bar">
        <div className="rp-relevance__fill" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="rp-relevance__label" style={{ color }}>{value}%</span>
    </div>
  )
}

// ── Phase header ──────────────────────────────────────────────────────────────
function RPHeader({ phase, onReset }) {
  const phases = ['query', 'select', 'executing', 'done']
  const idx = phases.indexOf(phase)
  return (
    <div className="rp-header">
      <div className="rp-header__title">RESEARCH ENGINE</div>
      <div className="rp-header__phases">
        {phases.map((p, i) => (
          <span
            key={p}
            className={`rp-phase ${phase === p ? 'rp-phase--active' : idx > i ? 'rp-phase--done' : ''}`}
          >
            {String(i + 1).padStart(2, '0')} {p.toUpperCase()}
          </span>
        ))}
      </div>
      {phase !== 'query' && (
        <button className="rp-reset-btn" onClick={onReset}>NEW RESEARCH ↻</button>
      )}
    </div>
  )
}

// ── Phase 1: Query ────────────────────────────────────────────────────────────
function RPQueryPanel({ query, setQuery, onSubmit, loading, locked, suggested }) {
  return (
    <Panel title="QUERY" tone="gold">
      <textarea
        className="rp-query-input"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="What do you want to research? (e.g. 'best vector databases for 100M+ embeddings')"
        rows={3}
        disabled={locked}
      />
      <div className="rp-suggested">
        {suggested.map(s => (
          <button
            key={s}
            className="rp-suggested-chip"
            onClick={() => !locked && setQuery(s)}
            disabled={locked}
          >
            {s}
          </button>
        ))}
      </div>
      <div className="rp-query-actions">
        <button
          className="rp-primary-btn"
          onClick={onSubmit}
          disabled={locked || loading || !query.trim()}
        >
          {loading ? 'DISCOVERING…' : 'DISCOVER SOURCES →'}
        </button>
      </div>
    </Panel>
  )
}

// ── Phase 2: Source Selection ────────────────────────────────────────────────
function RPSourceSelection({ candidates, selected, setSelected, filterType, setFilterType, locked }) {
  const filtered = filterType === 'all' ? candidates : candidates.filter(c => c.source_type === filterType)
  const counts = TYPES.reduce((acc, t) => {
    acc[t] = t === 'all' ? candidates.length : candidates.filter(c => c.source_type === t).length
    return acc
  }, {})

  const toggleAll = (val) => {
    const next = new Set(selected)
    filtered.forEach(c => val ? next.add(c.id) : next.delete(c.id))
    setSelected(next)
  }
  const selectHighTrust = () => {
    const next = new Set()
    candidates.filter(c => c.trust_score >= 0.7).forEach(c => next.add(c.id))
    setSelected(next)
  }

  return (
    <Panel title={`CANDIDATE SOURCES (${selected.size}/${candidates.length} selected)`} tone="cool">
      <div className="rp-filter-row">
        <div className="rp-type-chips">
          {TYPES.map(t => (
            <button
              key={t}
              className={`rp-type-chip ${filterType === t ? 'rp-type-chip--active' : ''}`}
              onClick={() => setFilterType(t)}
            >
              {t.toUpperCase()}
              {counts[t] > 0 && <span className="rp-type-chip__count">{counts[t]}</span>}
            </button>
          ))}
        </div>
        <div className="rp-quick-actions">
          <button onClick={() => toggleAll(true)}  disabled={locked}>ALL</button>
          <button onClick={() => toggleAll(false)} disabled={locked}>NONE</button>
          <button onClick={selectHighTrust}        disabled={locked}>HIGH-TRUST</button>
        </div>
      </div>
      <div className="rp-source-grid">
        {filtered.map(s => {
          const trustColor = s.trust_score >= 0.8 ? '#22c55e' : s.trust_score >= 0.5 ? '#e5c76b' : '#ef4444'
          const isSel = selected.has(s.id)
          return (
            <div
              key={s.id}
              className={`rp-source-card ${isSel ? 'rp-source-card--selected' : ''} ${locked ? 'rp-source-card--locked' : ''}`}
              onClick={() => {
                if (locked) return
                const next = new Set(selected)
                isSel ? next.delete(s.id) : next.add(s.id)
                setSelected(next)
              }}
            >
              <div className="rp-source-card__head">
                <input type="checkbox" checked={isSel} readOnly disabled={locked} />
                <span className="rp-trust-dot" style={{ background: trustColor }} title={`Trust: ${(s.trust_score * 100).toFixed(0)}%`} />
                <span className="rp-source-type">{s.source_type}</span>
                <a
                  className="rp-source-domain"
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={e => e.stopPropagation()}
                >
                  {s.domain} ↗
                </a>
              </div>
              <div className="rp-source-title">{s.title}</div>
              <div className="rp-source-snippet">{s.snippet}</div>
            </div>
          )
        })}
        {filtered.length === 0 && (
          <div className="rp-empty">No sources matching filter.</div>
        )}
      </div>
    </Panel>
  )
}

function ResearchGuidance({ title, detail, primary, onPrimary, secondary, onSecondary }) {
  return (
    <div className="rp-guidance" role="status">
      <div>
        <b>{title}</b>
        <span>{detail}</span>
      </div>
      <div className="rp-guidance__actions">
        {primary && <button className="rp-primary-btn rp-primary-btn--compact" onClick={onPrimary}>{primary}</button>}
        {secondary && <button className="rp-secondary-btn" onClick={onSecondary}>{secondary}</button>}
      </div>
    </div>
  )
}

// ── Research pipeline steps ───────────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: 'discovering', label: 'Discovering' },
  { id: 'fetching',    label: 'Fetching'    },
  { id: 'summarizing', label: 'Summarizing' },
  { id: 'storing',     label: 'Storing'     },
]

function deriveStep(progressLog) {
  // Walk the log in reverse to find the latest meaningful event type
  for (let i = progressLog.length - 1; i >= 0; i--) {
    const t = progressLog[i].type || ''
    if (t.includes('completed') || t.includes('stored')) return 'storing'
    if (t.includes('summar'))    return 'summarizing'
    if (t.includes('fetch') || t.includes('crawl') || t.includes('page')) return 'fetching'
    if (t.includes('discover') || t.includes('search') || t.includes('started')) return 'discovering'
  }
  return 'discovering'
}

function RPProgressSteps({ phase, progressLog }) {
  const current = phase === 'done' ? 'storing' : deriveStep(progressLog)
  const steps   = PIPELINE_STEPS
  const curIdx  = steps.findIndex(s => s.id === current)

  return (
    <div className="rp-steps">
      {steps.map((s, i) => {
        const done    = phase === 'done' || i < curIdx
        const active  = !done && s.id === current
        return (
          <div key={s.id} className={`rp-step ${done ? 'rp-step--done' : active ? 'rp-step--active' : ''}`}>
            <div className="rp-step__icon">
              {done
                ? <span className="rp-step__check">✓</span>
                : active
                  ? <span className="rp-step__spinner" />
                  : <span className="rp-step__dot" />
              }
            </div>
            <span className="rp-step__label">{s.label.toUpperCase()}</span>
            {i < steps.length - 1 && <div className={`rp-step__line ${done ? 'rp-step__line--done' : ''}`} />}
          </div>
        )
      })}
    </div>
  )
}

function RPResultsPanel({ results }) {
  const summary  = results?.summary || results?.content || null
  const sources  = results?.sources || []
  const wordCount = summary ? summary.split(/\s+/).filter(Boolean).length : null

  return (
    <div className="rp-results">
      <SectionLabel>RESULTS</SectionLabel>
      {(wordCount !== null || sources.length > 0) && (
        <div className="rp-results-meta">
          {wordCount !== null && <span className="rp-results-badge rp-results-badge--words">{wordCount} words</span>}
          {sources.length > 0 && <span className="rp-results-badge rp-results-badge--sources">{sources.length} sources</span>}
        </div>
      )}
      {summary && (
        <div className="rp-results-summary">{summary}</div>
      )}
      {sources.length > 0 && (
        <div className="rp-results-sources">
          <div className="rp-results-sources-title">SOURCES</div>
          {sources.map((s, i) => (
            <div key={i} className="rp-results-source-row">
              <span className="rp-results-source-num">{String(i + 1).padStart(2, '0')}</span>
              {s.url
                ? <a className="rp-results-source-link" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                : <span className="rp-results-source-link">{s.title || s.source || String(s)}</span>
              }
            </div>
          ))}
        </div>
      )}
      {!summary && sources.length === 0 && (
        <pre className="rp-results-pre">{JSON.stringify(results, null, 2)}</pre>
      )}
    </div>
  )
}

// ── Phase 3: Execute + Live Log + Results ────────────────────────────────────
function RPExecutePanel({ depth, setDepth, selectedCount, totalCount, onExecute, phase, sessionId, progressLog, results }) {
  return (
    <Panel title="EXECUTE RESEARCH" tone="gold">
      <div className="rp-depth-row">
        {DEPTHS.map(d => (
          <label
            key={d.id}
            className={`rp-depth-card ${depth === d.id ? 'rp-depth-card--active' : ''}`}
          >
            <input
              type="radio"
              checked={depth === d.id}
              onChange={() => setDepth(d.id)}
              disabled={phase !== 'select'}
            />
            <div className="rp-depth-label">{d.label}</div>
            <div className="rp-depth-sub">{d.sub}</div>
          </label>
        ))}
      </div>
      <div className="rp-execute-actions">
        <div className="rp-execute-summary">
          {selectedCount}/{totalCount} sources selected · {depth.toUpperCase()} depth
        </div>
        <button
          className="rp-primary-btn"
          onClick={onExecute}
          disabled={phase !== 'select' || selectedCount === 0}
        >
          {phase === 'executing' ? 'RUNNING…' : phase === 'done' ? 'COMPLETED ✓' : 'RUN RESEARCH →'}
        </button>
      </div>
      {(phase === 'executing' || phase === 'done') && (
        <div className="rp-progress">
          <RPProgressSteps phase={phase} progressLog={progressLog} />
          <SectionLabel>SESSION {sessionId?.slice(0, 8) || '—'} · LIVE LOG</SectionLabel>
          <div className="rp-progress-log">
            {progressLog.length === 0
              ? <div className="rp-log-empty">Waiting for first event…</div>
              : progressLog.map((m, i) => {
                  const variant = (m.type || '').split(':')[1] || 'info'
                  const detail  = m.message || m.detail || m.url || ''
                  return (
                    <div key={i} className={`rp-log-entry rp-log-entry--${variant}`}>
                      <span className="rp-log-type">{m.type || 'event'}</span>
                      <span className="rp-log-detail">{detail || JSON.stringify(m).slice(0, 160)}</span>
                    </div>
                  )
                })}
          </div>
        </div>
      )}
      {phase === 'done' && results && <RPResultsPanel results={results} />}
    </Panel>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function ResearchPage() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [phase, setPhase]             = useState('query')      // 'query' | 'select' | 'executing' | 'done'
  const [query, setQuery]             = useState('')
  const [candidates, setCandidates]   = useState([])
  const [selected, setSelected]       = useState(new Set())
  const [filterType, setFilterType]   = useState('all')
  const [depth, setDepth]             = useState('normal')
  const [sessionId, setSessionId]     = useState(null)
  const [executing, setExecuting]     = useState(false)
  const [results, setResults]         = useState(null)
  const [progressLog, setProgressLog] = useState([])
  const [error, setError]             = useState('')

  const onDiscover = async () => {
    if (!query.trim()) return
    setExecuting(true)
    setError('')
    try {
      const res = await fetch('/api/research/discover', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ query, max_sources: 12 }),
      })
      const r = await res.json()
      if (!res.ok || r.error) throw new Error(r.error || r.message || 'Research discovery failed')
      const sources = r.sources || []
      setCandidates(sources)
      setSelected(new Set(sources.map(s => s.id)))   // default: all selected
      setPhase('select')
    } catch (e) {
      console.error('discover failed', e)
      setError(e.message || 'Research discovery failed')
    } finally {
      setExecuting(false)
    }
  }

  const onExecute = async () => {
    if (selected.size === 0) return
    const selectedSources = candidates.filter(s => selected.has(s.id))
    setExecuting(true)
    setProgressLog([])
    setError('')
    try {
      const res = await fetch('/api/research/execute', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          query,
          selected_source_ids: Array.from(selected),
          selected_urls: selectedSources.map(s => s.url),
          depth,
        }),
      })
      const r = await res.json()
      if (!res.ok || r.error) throw new Error(r.error || r.message || 'Research execution failed')
      setSessionId(r.session_id)
      setPhase('executing')
    } catch (e) {
      console.error('execute failed', e)
      setError(e.message || 'Research execution failed')
      setExecuting(false)
    }
  }

  const onReset = () => {
    setPhase('query')
    setQuery('')
    setCandidates([])
    setSelected(new Set())
    setSessionId(null)
    setResults(null)
    setProgressLog([])
    setExecuting(false)
    setError('')
  }

  // WS listener for task:research_* events
  useEffect(() => {
    if (!sessionId) return
    const handler = (e) => {
      const msg = e.detail || {}
      if (msg.session_id && msg.session_id !== sessionId) return
      setProgressLog(prev => [...prev, msg])
      if (msg.type === 'task:research_completed') {
        setResults(msg.result || null)
        setPhase('done')
        setExecuting(false)
      } else if (msg.type === 'task:research_failed') {
        setPhase('done')
        setExecuting(false)
      }
    }
    window.addEventListener('ws:research', handler)
    return () => window.removeEventListener('ws:research', handler)
  }, [sessionId])

  return (
    <div className="rp-page">
      <RPHeader phase={phase} onReset={onReset} />
      <RPQueryPanel
        query={query} setQuery={setQuery}
        onSubmit={onDiscover}
        loading={executing && phase === 'query'}
        locked={phase !== 'query'}
        suggested={SUGGESTED}
      />
      {error && (
        <ResearchGuidance
          title="Research is blocked or degraded"
          detail={error}
          primary="Open Setup"
          onPrimary={() => setActiveSection('setup')}
          secondary="Check Proof"
          onSecondary={() => setActiveSection('proof')}
        />
      )}
      {(phase === 'select' || phase === 'executing' || phase === 'done') && (
        <RPSourceSelection
          candidates={candidates}
          selected={selected} setSelected={setSelected}
          filterType={filterType} setFilterType={setFilterType}
          locked={phase !== 'select'}
        />
      )}
      {phase === 'select' && candidates.length === 0 && !error && (
        <ResearchGuidance
          title="No sources were discovered"
          detail="Try a broader query or check integrations/model setup before relying on research output."
          primary="Open Setup"
          onPrimary={() => setActiveSection('setup')}
          secondary="New Research"
          onSecondary={onReset}
        />
      )}
      {(phase === 'select' || phase === 'executing' || phase === 'done') && (
        <RPExecutePanel
          depth={depth} setDepth={setDepth}
          selectedCount={selected.size}
          totalCount={candidates.length}
          onExecute={onExecute}
          phase={phase}
          sessionId={sessionId}
          progressLog={progressLog}
          results={results}
        />
      )}
      <ResearchActivityPanel />
    </div>
  )
}

// Re-exports for any external consumers of helper bits
export { ScreenshotThumb, RelevanceBar }
