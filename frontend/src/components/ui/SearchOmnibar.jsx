import { useState, useEffect, useRef, useCallback } from 'react'

const BANG_OPTS = ['!web', '!memory', '!code', '!graph', '!agent', '!tool', '!task', '!log']

const TYPE_ICONS = {
  web: '🌐', memory: '🧠', agent: '🤖', code: '{}', tool: '🔧', doc: '📄',
}
const iconFor = t => TYPE_ICONS[t] || '📌'

const TYPE_COLORS = {
  web: '#3b82f6', memory: '#8b5cf6', agent: '#10b981', code: '#f59e0b',
  tool: '#ef4444', doc: '#6b7280',
}
const badgeColor = t => TYPE_COLORS[t] || '#94a3b8'

function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key] || 'other'
    if (!acc[k]) acc[k] = []
    acc[k].push(item)
    return acc
  }, {})
}

export default function SearchOmnibar() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [bangDropdown, setBangDropdown] = useState(false)
  const [stats, setStats] = useState(null) // { count, engines, ms }
  const inputRef = useRef(null)
  const debounceRef = useRef(null)
  const overlayRef = useRef(null)

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setResults([])
    setStats(null)
    setBangDropdown(false)
  }, [])

  // Cmd+K / Ctrl+K to open
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(v => !v)
      }
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  // Auto-focus on open
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  // Debounced search
  const doSearch = useCallback((q) => {
    if (!q.trim()) { setResults([]); setStats(null); return }
    setLoading(true)
    const t0 = Date.now()
    const token = sessionStorage.getItem('ai_jwt')
    fetch('/api/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ query: q, complexity: 'simple', max_results: 20 }),
    })
      .then(r => r.ok ? r.json() : { results: [], engines: [] })
      .then(data => {
        const res = Array.isArray(data.results) ? data.results : Array.isArray(data) ? data : []
        const engineCount = Array.isArray(data.engines) ? data.engines.length : (data.engine_count ?? 1)
        setResults(res)
        setStats({ count: res.length, engines: engineCount, ms: Date.now() - t0 })
      })
      .catch(() => { setResults([]); setStats(null) })
      .finally(() => setLoading(false))
  }, [])

  const onChange = (e) => {
    const val = e.target.value
    setQuery(val)
    setBangDropdown(val.endsWith('!') || val.includes(' !'))
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(val), 250)
  }

  const insertBang = (bang) => {
    const newQ = query.endsWith('!') ? query.slice(0, -1) + bang + ' ' : query + bang + ' '
    setQuery(newQ)
    setBangDropdown(false)
    inputRef.current?.focus()
    doSearch(newQ)
  }

  const handleResult = (result) => {
    if (result.source_type === 'agent') {
      window.dispatchEvent(new CustomEvent('nx:open-task-composer', { detail: { agent_id: result.id || result.agent_id } }))
    } else if (result.url) {
      try { navigator.clipboard.writeText(result.url) } catch {}
    }
    close()
  }

  const grouped = groupBy(results, 'source_type')

  if (!open) return null

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) close() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: '10vh',
      }}
      aria-modal="true"
      role="dialog"
      aria-label="Search"
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 672,
          background: 'rgba(10,11,15,0.97)',
          backdropFilter: 'blur(20px)',
          borderRadius: 16,
          boxShadow: '0 25px 60px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.06)',
          overflow: 'hidden',
          fontFamily: 'var(--nx-font-mono, monospace)',
        }}
      >
        {/* Input row */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 10, flexShrink: 0 }}>
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={onChange}
            placeholder="Search anything… type ! for filters"
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              color: '#e8e6d9', fontSize: 15, fontFamily: 'inherit',
            }}
            autoComplete="off"
            spellCheck={false}
            aria-label="Search query"
          />
          {loading && (
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', marginLeft: 8 }}>...</span>
          )}
          <kbd style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', marginLeft: 8, padding: '2px 5px', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 4 }}>ESC</kbd>
        </div>

        {/* Bang autocomplete */}
        {bangDropdown && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '10px 18px', borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
            {BANG_OPTS.map(b => (
              <button
                key={b}
                onClick={() => insertBang(b)}
                style={{
                  padding: '3px 10px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.12)',
                  background: 'rgba(255,255,255,0.05)', color: '#e5c76b', cursor: 'pointer',
                  fontSize: 12, fontFamily: 'inherit',
                }}
              >
                {b}
              </button>
            ))}
          </div>
        )}

        {/* Engine stats */}
        {stats && (
          <div style={{ padding: '6px 18px', fontSize: 11, color: 'rgba(255,255,255,0.3)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            {stats.count} results from {stats.engines} engine{stats.engines !== 1 ? 's' : ''} in {stats.ms}ms
          </div>
        )}

        {/* Results */}
        <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {results.length === 0 && !loading && query.trim() && (
            <div style={{ padding: '24px 18px', textAlign: 'center', color: 'rgba(255,255,255,0.3)', fontSize: 13 }}>
              No results for "{query}"
            </div>
          )}
          {results.length === 0 && !query.trim() && (
            <div style={{ padding: '24px 18px', textAlign: 'center', color: 'rgba(255,255,255,0.2)', fontSize: 12 }}>
              Start typing to search across web, memory, agents, and more
            </div>
          )}
          {Object.entries(grouped).map(([sourceType, items]) => (
            <div key={sourceType}>
              <div style={{ padding: '8px 18px 4px', fontSize: 10, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase' }}>
                {iconFor(sourceType)} {sourceType}
              </div>
              {items.map((r, i) => (
                <button
                  key={r.id || i}
                  onClick={() => handleResult(r)}
                  style={{
                    display: 'flex', alignItems: 'center', width: '100%',
                    padding: '9px 18px', background: 'none', border: 'none',
                    cursor: 'pointer', textAlign: 'left', gap: 10,
                    transition: 'background 0.12s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                >
                  <span style={{ fontSize: 14, flexShrink: 0 }}>{iconFor(r.source_type || sourceType)}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', color: '#e8e6d9', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title || r.label || r.id || 'Untitled'}
                    </span>
                    {r.content && (
                      <span style={{ display: 'block', color: 'rgba(255,255,255,0.3)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1 }}>
                        {r.content}
                      </span>
                    )}
                  </span>
                  <span style={{
                    fontSize: 10, padding: '2px 7px', borderRadius: 4, flexShrink: 0,
                    background: badgeColor(r.source_type || sourceType) + '22',
                    color: badgeColor(r.source_type || sourceType),
                    border: `1px solid ${badgeColor(r.source_type || sourceType)}44`,
                    fontFamily: 'inherit',
                  }}>
                    {r.source_type || sourceType}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
