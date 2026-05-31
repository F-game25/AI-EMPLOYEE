import { useState, useEffect, useCallback } from 'react'
import { SectionLabel } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST_JSON } from './helpers'

export function UnderstandPane({ project }) {
  const [summary, setSummary] = useState(null)
  const [indexing, setIndexing] = useState(false)
  const [query, setQuery] = useState('')
  const [ctx, setCtx] = useState(null)
  const [searching, setSearching] = useState(false)

  const loadSummary = useCallback(() => {
    if (!project) return
    JGET(`/api/forge/summary/${project.id}`).then(r => r.json()).then(d => setSummary(d?.ok ? d : null)).catch(() => setSummary(null))
  }, [project])
  useEffect(() => { loadSummary() }, [loadSummary])

  if (!project) return <div className="af-chat__no-project">Select a project to understand its architecture.</div>

  const index = async () => {
    setIndexing(true)
    try { const d = await JPOST_JSON('/api/forge/index', { project_id: project.id }); setSummary(d); toastSuccess(`Indexed ${d.files} files → ${d.chunks} chunks`) }
    catch (e) { toastError(e.message) } finally { setIndexing(false) }
  }
  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try { setCtx(await JPOST_JSON('/api/forge/context', { project_id: project.id, query, k: 6 })) }
    catch (e) { toastError(e.message) } finally { setSearching(false) }
  }

  return (
    <div className="af-understand">
      <div className="af-understand__actions">
        <button className="af-index-btn" onClick={index} disabled={indexing}>{indexing ? 'Indexing…' : '⟳ Index project'}</button>
        {summary?.indexed_at && <span className="af-understand__meta">{summary.files} files · {summary.chunks} chunks</span>}
      </div>

      {summary?.ok && (
        <div className="af-understand__summary">
          <div className="af-understand__row"><span>Languages</span><b>{Object.entries(summary.languages || {}).map(([l, n]) => `${l} ${n}`).join(' · ') || '—'}</b></div>
          <div className="af-understand__row"><span>Entry points</span><b>{(summary.entry_points || []).join(', ') || '—'}</b></div>
          <div className="af-understand__row"><span>Import edges</span><b>{summary.import_edges ?? '—'}</b></div>
          <SectionLabel>TOP MODULES</SectionLabel>
          <ul className="af-understand__modules">
            {(summary.top_modules || []).slice(0, 10).map(m => (
              <li key={m.path}><code>{m.path}</code> <span>{m.symbol_count} symbols</span></li>
            ))}
          </ul>
        </div>
      )}
      {!summary?.ok && !indexing && <div className="af-understand__hint">Not indexed yet — click "Index project" so the builder understands this codebase.</div>}

      <div className="af-understand__search">
        <SectionLabel>FIND RELEVANT CODE</SectionLabel>
        <div className="af-understand__searchrow">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. where is auth handled?" onKeyDown={e => e.key === 'Enter' && search()} />
          <button onClick={search} disabled={searching}>{searching ? '…' : 'Search'}</button>
        </div>
        {ctx?.results?.map((r, i) => (
          <div key={i} className="af-understand__hit">
            <div className="af-understand__hitpath"><code>{r.path}</code>{r.symbol ? ` :: ${r.symbol}` : ''}</div>
            <pre>{(r.snippet || '').slice(0, 500)}</pre>
          </div>
        ))}
        {ctx && !ctx.results?.length && <div className="af-understand__hint">No matches.</div>}
      </div>
    </div>
  )
}
