import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import api from '../../api/client'
import VaultBrowser from '../knowledge/VaultBrowser'
import MarkdownEditor from '../knowledge/MarkdownEditor'
import BacklinksPanel from '../knowledge/BacklinksPanel'
import LearnTopicWizard from '../knowledge/LearnTopicWizard'
import StandingTopicsPanel from '../knowledge/StandingTopicsPanel'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
import EmptyState from '../nexus-ui/EmptyState'
import './KnowledgePage.css'

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'alpha',  label: 'Alphabetical' },
]

export default function KnowledgePage() {
  const [activeView, setActiveView] = useState('vault')
  const [selectedId, setSelectedId] = useState(null)
  const [currentNote, setCurrentNote] = useState(null)
  const [allNoteTitles, setAllNoteTitles] = useState([])
  const [resolvedSet, setResolvedSet] = useState(new Set())
  const [wizardOpen, setWizardOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [savingNote, setSavingNote] = useState(false)

  // Search / filter state
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')       // debounced
  const [searchHitIds, setSearchHitIds] = useState(null)  // Set|null — null = no server search active
  const [activeTag, setActiveTag] = useState(null)
  const [sort, setSort] = useState('newest')
  const [allNotes, setAllNotes] = useState([])             // loaded by VaultBrowser via callback
  const [totalNotes, setTotalNotes] = useState(0)
  const debounceRef = useRef(null)
  const searchAbortRef = useRef(null)

  // Knowledge semantic search state
  const [kSearchInput, setKSearchInput] = useState('')
  const [kSearchMode, setKSearchMode] = useState('keyword') // 'keyword' | 'semantic'
  const [kSearchResults, setKSearchResults] = useState(null) // null = no search yet
  const [kSearchLoading, setKSearchLoading] = useState(false)
  const kDebounceRef = useRef(null)
  const kAbortRef = useRef(null)

  useEffect(() => {
    api.get('/api/vault/notes').then(d => {
      const notes = d?.notes || d || []
      setAllNoteTitles(notes.map(n => n.title || n.id))
      const resolved = new Set()
      notes.forEach(n => {
        resolved.add(String(n.title || '').toLowerCase().replace(/\s+/g, '-'))
        resolved.add(String(n.id || '').toLowerCase())
      })
      setResolvedSet(resolved)
    }).catch(() => {})
  }, [refreshKey])

  // Debounce search input → trigger server full-text search after 200ms
  useEffect(() => {
    clearTimeout(debounceRef.current)
    const q = searchInput.trim()
    if (!q) {
      setSearchQuery('')
      setSearchHitIds(null)
      return
    }
    debounceRef.current = setTimeout(() => {
      setSearchQuery(q)
      searchAbortRef.current?.abort?.()
      const ctrl = new AbortController()
      searchAbortRef.current = ctrl
      api.get(`/api/vault/search?q=${encodeURIComponent(q)}`)
        .then(d => {
          if (ctrl.signal.aborted) return
          const hits = d?.hits || []
          setSearchHitIds(new Set(hits.map(h => h.id)))
          setTotalNotes(prev => prev) // keep total from VaultBrowser
        })
        .catch(() => {
          if (ctrl.signal.aborted) return
          // Fall back to client-side filtering (searchHitIds stays null)
          setSearchHitIds(null)
        })
    }, 200)
    return () => clearTimeout(debounceRef.current)
  }, [searchInput])

  // Knowledge search — fires when input or mode changes
  useEffect(() => {
    clearTimeout(kDebounceRef.current)
    const q = kSearchInput.trim()
    if (!q) { setKSearchResults(null); return }
    kDebounceRef.current = setTimeout(() => {
      kAbortRef.current?.abort?.()
      const ctrl = new AbortController()
      kAbortRef.current = ctrl
      setKSearchLoading(true)
      const url = kSearchMode === 'semantic'
        ? `/api/knowledge/search?q=${encodeURIComponent(q)}&mode=hybrid`
        : `/api/knowledge/search?q=${encodeURIComponent(q)}`
      api.get(url)
        .then(d => {
          if (ctrl.signal.aborted) return
          setKSearchResults(d?.entries || [])
        })
        .catch(() => { if (!ctrl.signal.aborted) setKSearchResults([]) })
        .finally(() => { if (!ctrl.signal.aborted) setKSearchLoading(false) })
    }, 250)
    return () => clearTimeout(kDebounceRef.current)
  }, [kSearchInput, kSearchMode])

  // Unique tags derived from loaded notes (top 12 most common)
  const tagChips = useMemo(() => {
    const freq = {}
    allNotes.forEach(n => (n.tags || []).forEach(t => { freq[t] = (freq[t] || 0) + 1 }))
    return Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([t]) => t)
  }, [allNotes])

  // How many notes pass current filters (computed from allNotes for the count badge)
  const filteredCount = useMemo(() => {
    if (!allNotes.length) return 0
    let n = allNotes
    if (searchHitIds !== null) n = n.filter(x => searchHitIds.has(x.id))
    else if (searchQuery) {
      const q = searchQuery.toLowerCase()
      n = n.filter(x => (x.title || x.id || '').toLowerCase().includes(q) ||
        (x.tags || []).join(' ').toLowerCase().includes(q))
    }
    if (activeTag) n = n.filter(x => (x.tags || []).includes(activeTag))
    return n.length
  }, [allNotes, searchHitIds, searchQuery, activeTag])

  useEffect(() => {
    if (!selectedId) { setCurrentNote(null); return }
    api.get(`/api/vault/notes/${selectedId}`)
      .then(d => setCurrentNote(d))
      .catch(() => setCurrentNote(null))
  }, [selectedId, refreshKey])

  const handleSave = useCallback(async (markdown) => {
    if (!currentNote) return
    setSavingNote(true)
    try {
      await api.put(`/api/vault/notes/${currentNote.id}`, {
        body: markdown,
        frontmatter: currentNote.frontmatter || {},
      })
    } catch (e) { console.error('save failed', e) }
    setSavingNote(false)
  }, [currentNote])

  const handleNewNote = async (initialTitle = null) => {
    const title = initialTitle || prompt('Note title:')
    if (!title) return
    try {
      const d = await api.post('/api/vault/notes', {
        title,
        folder: 'concepts',
        body: `# ${title}\n\n`,
        frontmatter: { tags: [], confidence: 0.5, verified_by: 'user' },
      })
      const newId = d?.id
      if (newId) {
        setRefreshKey(k => k + 1)
        setSelectedId(newId)
      }
    } catch (e) { console.error('create failed', e) }
  }

  const handleDelete = async () => {
    if (!currentNote) return
    if (!confirm(`Delete "${currentNote.title}"?`)) return
    try {
      await api.delete(`/api/vault/notes/${currentNote.id}`)
      setSelectedId(null)
      setRefreshKey(k => k + 1)
    } catch (e) { console.error('delete failed', e) }
  }

  const handleExportPath = () => {
    const vaultPath = '~/.ai-employee/vault'
    navigator.clipboard?.writeText(vaultPath).catch(() => {})
    // toast instead of alert — non-blocking
    import('../nexus-ui/Toaster').then(m => (m.toastSuccess || m.default?.toastSuccess)?.('Vault path copied to clipboard'))
      .catch(() => {})
  }

  return (
    <div className="kp-page">
      <div className="kp-toolbar">
        <div className="kp-toolbar__left">
          <button className={`kp-tab ${activeView === 'vault' ? 'is-active' : ''}`} onClick={() => setActiveView('vault')}>NOTES</button>
          <button className={`kp-tab ${activeView === 'graph' ? 'is-active' : ''}`} onClick={() => setActiveView('graph')}>KNOWLEDGE GRAPH</button>
          <button className={`kp-tab ${activeView === 'topics' ? 'is-active' : ''}`} onClick={() => setActiveView('topics')}>STANDING TOPICS</button>
          <button className={`kp-tab ${activeView === 'review' ? 'is-active' : ''}`} onClick={() => setActiveView('review')}>REVIEW QUEUE</button>
          <button className={`kp-tab ${activeView === 'broken' ? 'is-active' : ''}`} onClick={() => setActiveView('broken')}>BROKEN LINKS</button>
          <button className={`kp-tab ${activeView === 'rag' ? 'is-active' : ''}`} onClick={() => setActiveView('rag')}>RAG SOURCES</button>
          <button className={`kp-tab ${activeView === 'search' ? 'is-active' : ''}`} onClick={() => setActiveView('search')}>SEARCH</button>
        </div>
        <div className="kp-toolbar__right">
          <button className="kp-action" onClick={() => setWizardOpen(true)}>+ LEARN TOPIC</button>
          <button className="kp-action" onClick={() => handleNewNote()}>+ NEW NOTE</button>
          <button className="kp-action kp-action--ghost" onClick={handleExportPath} title="Copy vault path to clipboard for backup">⊡ EXPORT PATH</button>
        </div>
      </div>

      {activeView === 'vault' && (
        <div className="kp-vault">
          <div className="kp-vault__left">
            <div className="kp-filter-bar">
              <div className="kp-filter-search">
                <input
                  className="kp-filter-input"
                  type="search"
                  placeholder="Search vault…"
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  aria-label="Full-text search vault"
                />
                {searchInput && (
                  <button
                    className="kp-filter-clear"
                    onClick={() => { setSearchInput(''); setSearchQuery(''); setSearchHitIds(null) }}
                    aria-label="Clear search"
                  >×</button>
                )}
              </div>
              {allNotes.length > 0 && (
                <div className="kp-filter-count">
                  {(searchQuery || activeTag) ? `${filteredCount} / ${allNotes.length}` : allNotes.length} entries
                </div>
              )}
              {tagChips.length > 0 && (
                <div className="kp-filter-chips" role="group" aria-label="Filter by tag">
                  <button
                    className={`kp-chip ${!activeTag ? 'is-active' : ''}`}
                    onClick={() => setActiveTag(null)}
                  >All</button>
                  {tagChips.map(t => (
                    <button
                      key={t}
                      className={`kp-chip ${activeTag === t ? 'is-active' : ''}`}
                      onClick={() => setActiveTag(activeTag === t ? null : t)}
                    >{t}</button>
                  ))}
                </div>
              )}
              <div className="kp-filter-sort">
                <label className="kp-filter-sort-label" htmlFor="kp-sort">SORT</label>
                <select
                  id="kp-sort"
                  className="kp-filter-select"
                  value={sort}
                  onChange={e => setSort(e.target.value)}
                  aria-label="Sort order"
                >
                  {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
            <VaultBrowser
              selectedId={selectedId}
              onSelect={setSelectedId}
              onNewNote={() => handleNewNote()}
              refreshKey={refreshKey}
              filterState={{ query: searchQuery, searchHitIds, activeTag, sort }}
              onNotesLoaded={notes => { setAllNotes(notes); setTotalNotes(notes.length) }}
            />
          </div>

          <div className="kp-vault__center">
            {!currentNote && (
              <div className="kp-welcome">
                <div className="kp-welcome__title">MEMORY VAULT</div>
                <div className="kp-welcome__sub">{allNoteTitles.length} notes · internal knowledge store — fully local, no external apps needed</div>
                <div className="kp-welcome__actions">
                  <button className="kp-primary" onClick={() => setWizardOpen(true)}>+ TEACH ME ABOUT …</button>
                  <button className="kp-secondary" onClick={() => handleNewNote()}>+ NEW BLANK NOTE</button>
                </div>
              </div>
            )}
            {currentNote && (
              <>
                <div className="kp-editor-header">
                  <div className="kp-editor-title">{currentNote.title || currentNote.id}</div>
                  <div className="kp-editor-meta">
                    <span className={`kp-save-state ${savingNote ? 'is-saving' : ''}`}>{savingNote ? 'saving…' : '✓ saved'}</span>
                    <button className="kp-delete-btn" onClick={handleDelete}>DELETE</button>
                  </div>
                </div>
                <MarkdownEditor
                  noteId={currentNote.id}
                  body={currentNote.body || ''}
                  resolvedTargets={resolvedSet}
                  allNoteTitles={allNoteTitles}
                  onSave={handleSave}
                  placeholder="Start writing…"
                />
              </>
            )}
          </div>

          <div className="kp-vault__right">
            <BacklinksPanel
              noteId={currentNote?.id}
              frontmatter={currentNote?.frontmatter}
              wikilinks={currentNote?.wikilinks || []}
              resolvedTargets={resolvedSet}
              onOpenNote={(id) => setSelectedId(id)}
              onCreateNote={(title) => handleNewNote(title)}
            />
          </div>
        </div>
      )}

      {activeView === 'graph' && <VaultGraphView onOpenNote={id => { setActiveView('vault'); setSelectedId(id) }} />}

      {activeView === 'topics' && (
        <StandingTopicsPanel
          onLearnNew={() => setWizardOpen(true)}
          onOpenTopic={(id) => { setActiveView('vault'); setSelectedId(id) }}
        />
      )}

      {activeView === 'review' && <PendingReviewWrapper />}

      {activeView === 'broken' && (
        <BrokenLinksView onCreateNote={(title) => { setActiveView('vault'); handleNewNote(title) }} />
      )}

      {activeView === 'rag' && <RagSourcesView />}

      {activeView === 'search' && (
        <div className="kp-ksearch">
          <div className="kp-ksearch-bar">
            <div className="kp-filter-search" style={{ flex: 1 }}>
              <input
                className="kp-filter-input"
                type="search"
                placeholder="Search knowledge base…"
                value={kSearchInput}
                onChange={e => setKSearchInput(e.target.value)}
                aria-label="Knowledge search"
                autoFocus
              />
              {kSearchInput && (
                <button
                  className="kp-filter-clear"
                  onClick={() => { setKSearchInput(''); setKSearchResults(null) }}
                  aria-label="Clear"
                >×</button>
              )}
            </div>
            <div className="kp-search-mode-toggle" role="group" aria-label="Search mode">
              <button
                className={`kp-mode-btn ${kSearchMode === 'keyword' ? 'is-active' : ''}`}
                onClick={() => setKSearchMode('keyword')}
              >KEYWORD</button>
              <button
                className={`kp-mode-btn ${kSearchMode === 'semantic' ? 'is-active' : ''}`}
                onClick={() => setKSearchMode('semantic')}
              >SEMANTIC</button>
            </div>
          </div>
          {kSearchLoading && <div className="kp-ksearch-status">Searching…</div>}
          {!kSearchLoading && kSearchResults === null && (
            <div className="kp-empty"><div>Type to search the knowledge base</div><div>Toggle KEYWORD / SEMANTIC to switch mode</div></div>
          )}
          {!kSearchLoading && kSearchResults !== null && kSearchResults.length === 0 && (
            <div className="kp-empty"><div>No results found</div></div>
          )}
          {!kSearchLoading && kSearchResults && kSearchResults.length > 0 && (
            <div className="kp-ksearch-results">
              <div className="kp-ksearch-count">{kSearchResults.length} result{kSearchResults.length !== 1 ? 's' : ''} · {kSearchMode === 'semantic' ? 'hybrid' : 'keyword'} mode</div>
              {kSearchResults.map((r, i) => (
                <div key={r.id || i} className="kp-ksearch-row">
                  <div className="kp-ksearch-row__title">{r.title || r.topic || r.id || 'Untitled'}</div>
                  <div className="kp-ksearch-row__body">{(r.content || r.text || '').slice(0, 200)}{(r.content || r.text || '').length > 200 ? '…' : ''}</div>
                  <div className="kp-ksearch-row__meta">
                    {r.source && (
                      <span className="kp-ksearch-badge kp-ksearch-badge--source" title={r.source}>
                        {r.source.length > 40 ? r.source.slice(0, 40) + '…' : r.source}
                      </span>
                    )}
                    {(r.score != null || r._score != null) && (
                      <span className="kp-ksearch-badge kp-ksearch-badge--score">
                        Match: {Math.round((r.score ?? r._score) * 100)}%
                      </span>
                    )}
                    {kSearchMode === 'semantic' && r.bm25_score != null && (
                      <span className="kp-ksearch-badge kp-ksearch-badge--bm25">
                        BM25: {r.bm25_score.toFixed(2)}
                      </span>
                    )}
                    {kSearchMode === 'semantic' && r.vector_score != null && (
                      <span className="kp-ksearch-badge kp-ksearch-badge--vector">
                        Vector: {r.vector_score.toFixed(2)}
                      </span>
                    )}
                    {r.tags?.length > 0 && r.tags.map(t => (
                      <span key={t} className="kp-chip" style={{ fontSize: 9, padding: '1px 5px' }}>{t}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <LearnTopicWizard open={wizardOpen} onClose={() => { setWizardOpen(false); setRefreshKey(k => k + 1) }} />
    </div>
  )
}

function PendingReviewWrapper() {
  const [Component, setComponent] = useState(null)
  useEffect(() => {
    import('../memory/PendingReviewQueue').then(m => setComponent(() => m.default || m)).catch(() => {})
  }, [])
  if (!Component) return <LoadingSkeleton variant="list" rows={5} />
  return <Component />
}

const CHROMA_BADGE = {
  populated: { label: 'POPULATED', color: '#22c55e' },
  empty:     { label: 'EMPTY',     color: '#f59e0b' },
  offline:   { label: 'OFFLINE',   color: '#ef4444' },
}

function RagSourcesView() {
  const [sources, setSources] = useState([])
  const [total, setTotal] = useState(0)
  const [chromaStatus, setChromaStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/rag/sources')
      .then(d => {
        setSources(d?.sources || [])
        setTotal(d?.total ?? (d?.sources?.length ?? 0))
        setChromaStatus(d?.chroma_status || null)
      })
      .catch(() => { setSources([]); setChromaStatus('offline') })
      .finally(() => setLoading(false))
  }, [])

  const badge = CHROMA_BADGE[chromaStatus] || null

  if (loading) return <LoadingSkeleton variant="list" rows={5} />

  return (
    <div className="kp-rag">
      <div className="kp-rag-header">
        <span className="kp-rag-title">RAG KNOWLEDGE SOURCES</span>
        <span className="kp-rag-count">{total} indexed</span>
        {badge && (
          <span className="kp-rag-badge" style={{ color: badge.color, border: `1px solid ${badge.color}`, borderRadius: 4, padding: '2px 8px', fontSize: 11 }}>
            {badge.label}
          </span>
        )}
      </div>
      {sources.length === 0 && (
        <div className="kp-empty">
          <div>No RAG sources indexed yet</div>
          <div>Sources appear here once documents are ingested into the vector store.</div>
        </div>
      )}
      <div className="kp-rag-list">
        {sources.map(src => (
          <div key={src.id} className="kp-rag-row">
            <div className="kp-rag-row__title">{src.title || src.id}</div>
            <div className="kp-rag-row__meta">
              <span>{src.source}</span>
              {src.tags?.length > 0 && src.tags.map(t => (
                <span key={t} className="kp-chip" style={{ fontSize: 10, padding: '1px 6px' }}>{t}</span>
              ))}
              <span style={{ marginLeft: 'auto', opacity: 0.5, fontSize: 11 }}>{src.created_at?.slice(0, 10) || ''}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Vault Knowledge Graph ─────────────────────────────────────────────────────
function VaultGraphView({ onOpenNote }) {
  const canvasRef = useRef(null)
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [hovered, setHovered] = useState(null)
  const simRef = useRef(null)

  useEffect(() => {
    api.get('/api/vault/graph')
      .then(d => setGraphData(d))
      .catch(() => setGraphData({ nodes: [], links: [] }))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !graphData) return
    const { nodes, links } = graphData
    if (!nodes?.length) return

    const W = canvas.offsetWidth || 800
    const H = canvas.offsetHeight || 500
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')

    // Simple force-directed layout (no d3 dependency)
    const pos = nodes.map((_, i) => ({
      x: W / 2 + Math.cos(i / nodes.length * Math.PI * 2) * Math.min(W, H) * 0.35,
      y: H / 2 + Math.sin(i / nodes.length * Math.PI * 2) * Math.min(W, H) * 0.35,
      vx: 0, vy: 0,
    }))
    const nodeMap = Object.fromEntries(nodes.map((n, i) => [n.id, i]))

    const tick = () => {
      // repulsion
      for (let i = 0; i < pos.length; i++) {
        for (let j = i + 1; j < pos.length; j++) {
          const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y
          const d = Math.sqrt(dx * dx + dy * dy) || 1
          const f = 2400 / (d * d)
          pos[i].vx += dx / d * f; pos[i].vy += dy / d * f
          pos[j].vx -= dx / d * f; pos[j].vy -= dy / d * f
        }
        // pull to center
        pos[i].vx += (W / 2 - pos[i].x) * 0.002
        pos[i].vy += (H / 2 - pos[i].y) * 0.002
      }
      // attraction along links
      for (const l of (links || [])) {
        const si = nodeMap[l.source ?? l.from], ti = nodeMap[l.target ?? l.to]
        if (si == null || ti == null) continue
        const dx = pos[ti].x - pos[si].x, dy = pos[ti].y - pos[si].y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = (d - 80) * 0.05
        pos[si].vx += dx / d * f; pos[si].vy += dy / d * f
        pos[ti].vx -= dx / d * f; pos[ti].vy -= dy / d * f
      }
      // integrate + damp
      for (const p of pos) {
        p.vx *= 0.85; p.vy *= 0.85
        p.x = Math.max(20, Math.min(W - 20, p.x + p.vx))
        p.y = Math.max(20, Math.min(H - 20, p.y + p.vy))
      }
    }

    let frame = 0
    const draw = () => {
      if (frame < 120) tick()
      frame++
      ctx.clearRect(0, 0, W, H)
      // edges
      for (const l of (links || [])) {
        const si = nodeMap[l.source ?? l.from], ti = nodeMap[l.target ?? l.to]
        if (si == null || ti == null) continue
        ctx.beginPath()
        ctx.moveTo(pos[si].x, pos[si].y)
        ctx.lineTo(pos[ti].x, pos[ti].y)
        ctx.strokeStyle = 'rgba(229,199,107,0.18)'
        ctx.lineWidth = 1
        ctx.stroke()
      }
      // nodes
      nodes.forEach((n, i) => {
        const r = 5 + Math.min((n.link_count || 0) * 1.5, 10)
        ctx.beginPath()
        ctx.arc(pos[i].x, pos[i].y, r, 0, Math.PI * 2)
        ctx.fillStyle = hovered === n.id ? '#E89A4F' : 'rgba(205,127,50,0.75)'
        ctx.fill()
        ctx.strokeStyle = 'rgba(229,199,107,0.5)'
        ctx.lineWidth = 1
        ctx.stroke()
        if (nodes.length < 60 || r > 8) {
          ctx.fillStyle = 'rgba(255,255,255,0.7)'
          ctx.font = '10px monospace'
          ctx.fillText((n.title || n.id || '').slice(0, 18), pos[i].x + r + 3, pos[i].y + 4)
        }
      })
    }

    simRef.current = pos
    let rafId
    let lastTs = 0
    const loop = (ts) => {
      rafId = requestAnimationFrame(loop)
      if (document.hidden || ts - lastTs < 40) return
      lastTs = ts
      draw()
    }
    rafId = requestAnimationFrame(loop)
    const onVis = () => {
      if (document.hidden) { cancelAnimationFrame(rafId); rafId = null }
      else if (!rafId) rafId = requestAnimationFrame(loop)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelAnimationFrame(rafId)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [graphData, hovered])

  if (loading) return <LoadingSkeleton variant="list" rows={5} />

  const nodes = graphData?.nodes || []
  if (!nodes.length) return (
    <EmptyState
      title="Knowledge graph is empty"
      sub="Add notes to the vault — connections appear when notes link to each other via [[wikilinks]]."
    />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 10, letterSpacing: '0.12em', color: 'var(--nx-gold, #e5c76b)', textTransform: 'uppercase', fontFamily: 'monospace' }}>
          KNOWLEDGE GRAPH · {nodes.length} nodes · {graphData?.links?.length || 0} links
        </span>
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: 'monospace' }}>internal · no external apps required</span>
      </div>
      <canvas
        ref={canvasRef}
        style={{ flex: 1, borderRadius: 6, border: '1px solid rgba(229,199,107,0.12)', background: 'rgba(7,8,15,0.95)', cursor: 'pointer' }}
        onClick={e => {
          const canvas = canvasRef.current
          const pos = simRef.current
          if (!canvas || !pos || !nodes) return
          const rect = canvas.getBoundingClientRect()
          const mx = (e.clientX - rect.left) * (canvas.width / rect.width)
          const my = (e.clientY - rect.top) * (canvas.height / rect.height)
          for (let i = 0; i < pos.length; i++) {
            const dx = pos[i].x - mx, dy = pos[i].y - my
            if (Math.sqrt(dx * dx + dy * dy) < 14) { onOpenNote?.(nodes[i].id); break }
          }
        }}
      />
    </div>
  )
}

function BrokenLinksView({ onCreateNote }) {
  const [links, setLinks] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.get('/api/vault/broken-links')
      .then(d => setLinks(d?.broken_links || d || []))
      .catch(() => setLinks([]))
      .finally(() => setLoading(false))
  }, [])
  if (loading) return <LoadingSkeleton variant="list" rows={5} />
  if (!links.length) return <div className="kp-empty"><div>✓ No broken links</div><div>Every [[wikilink]] in the vault has a target.</div></div>
  return (
    <div className="kp-broken-list">
      <div className="kp-broken-header">{links.length} broken link(s) — wikilinks pointing to non-existent notes</div>
      {links.map((l, i) => (
        <div key={i} className="kp-broken-row">
          <span className="kp-broken-from">{l.source}</span>
          <span className="kp-broken-arrow">→</span>
          <span className="kp-broken-target">[[{l.target}]]</span>
          <button className="kp-broken-fix" onClick={() => onCreateNote(l.target)}>+ Create</button>
        </div>
      ))}
    </div>
  )
}
