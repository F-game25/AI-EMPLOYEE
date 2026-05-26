import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import api from '../../api/client'
import VaultBrowser from '../knowledge/VaultBrowser'
import MarkdownEditor from '../knowledge/MarkdownEditor'
import BacklinksPanel from '../knowledge/BacklinksPanel'
import LearnTopicWizard from '../knowledge/LearnTopicWizard'
import StandingTopicsPanel from '../knowledge/StandingTopicsPanel'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
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

  const handleOpenObsidian = () => {
    const path = currentNote?.path || '~/.ai-employee/vault'
    navigator.clipboard?.writeText(path).catch(() => {})
    alert(`Vault path copied:\n${path}\n\nOpen this folder in Obsidian as a vault.`)
  }

  return (
    <div className="kp-page">
      <div className="kp-toolbar">
        <div className="kp-toolbar__left">
          <button className={`kp-tab ${activeView === 'vault' ? 'is-active' : ''}`} onClick={() => setActiveView('vault')}>VAULT</button>
          <button className={`kp-tab ${activeView === 'topics' ? 'is-active' : ''}`} onClick={() => setActiveView('topics')}>STANDING TOPICS</button>
          <button className={`kp-tab ${activeView === 'review' ? 'is-active' : ''}`} onClick={() => setActiveView('review')}>REVIEW QUEUE</button>
          <button className={`kp-tab ${activeView === 'broken' ? 'is-active' : ''}`} onClick={() => setActiveView('broken')}>BROKEN LINKS</button>
          <button className={`kp-tab ${activeView === 'rag' ? 'is-active' : ''}`} onClick={() => setActiveView('rag')}>RAG SOURCES</button>
        </div>
        <div className="kp-toolbar__right">
          <button className="kp-action" onClick={() => setWizardOpen(true)}>+ LEARN TOPIC</button>
          <button className="kp-action" onClick={() => handleNewNote()}>+ NEW NOTE</button>
          <button className="kp-action kp-action--ghost" onClick={handleOpenObsidian}>↗ OPEN IN OBSIDIAN</button>
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
                <div className="kp-welcome__title">VAULT</div>
                <div className="kp-welcome__sub">{allNoteTitles.length} notes · pick one from the left, or start a new one</div>
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
