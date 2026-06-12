import { useEffect, useMemo, useState } from 'react'
import { Panel, SectionLabel, StatusPill, EmptyState, ErrorState } from '../nexus-ui'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
import { useLiveData } from '../../hooks/useLiveData'
import { useAppStore } from '../../store/appStore'
import { toastSuccess, toastError, toastWarn } from '../nexus-ui/Toaster'
import StandingTopicsPanel from '../knowledge/StandingTopicsPanel'
import PendingReviewQueue from '../memory/PendingReviewQueue'
import LearnTopicWizard from '../knowledge/LearnTopicWizard'
import { useLearningStore } from '../../store/learningStore'
import { useBrainStore, GROUP_COLORS } from '../../store/brainStore'
import { useForgeStore } from '../../store/forgeStore'
import './MemoryPage.css'

const API = '/api/memory'
const tabs = [
  ['facts', 'Personal Facts'],
  ['knowledge', 'Knowledge Base'],
  ['conversations', 'Conversation History'],
  ['semantic', 'Semantic Store'],
  ['standing-topics', 'Standing Topics'],
  ['review-queue', 'Review Queue'],
  ['graph', 'Graph'],
]

// ── Concentric ring layout ────────────────────────────────────────────────────
function layoutNodes(nodes) {
  const cx = 200, cy = 200
  const byGroup = {}
  nodes.forEach(n => { (byGroup[n.group] = byGroup[n.group] || []).push(n) })
  const groups = Object.keys(byGroup)
  const radii = [0, 60, 110, 150, 180]
  const placed = {}
  groups.forEach((g, gi) => {
    const r = radii[Math.min(gi, radii.length - 1)] || 180
    byGroup[g].forEach((n, i) => {
      const angle = (2 * Math.PI * i) / byGroup[g].length - Math.PI / 2
      placed[n.id] = {
        x: gi === 0 && byGroup[g].length === 1 ? cx : cx + r * Math.cos(angle),
        y: gi === 0 && byGroup[g].length === 1 ? cy : cy + r * Math.sin(angle),
      }
    })
  })
  return placed
}

function MemoryGraph() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const rawNodes = useBrainStore(s => s.nodes)
  const rawLinks = useBrainStore(s => s.links)
  const [selected, setSelected] = useState(null)

  const nodes = rawNodes.slice(0, 50)
  const nodeIds = useMemo(() => new Set(nodes.map(n => n.id)), [nodes])
  const links = useMemo(
    () => rawLinks.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target)),
    [rawLinks, nodeIds],
  )
  const pos = useMemo(() => layoutNodes(nodes), [nodes])
  const selNode = selected ? nodes.find(n => n.id === selected) : null

  if (!nodes.length) return (
    <EmptyState
      icon="◈"
      title="No graph data yet"
      sub="Brain graph data appears after tasks, memory writes, or project context ingestion."
      action="Run Task"
      onAction={() => setActiveSection('tasks')}
    />
  )

  return (
    <div className="mem-graph-wrap">
      <svg className="mem-graph-svg" viewBox="0 0 400 400" preserveAspectRatio="xMidYMid meet">
        {links.map((l, i) => {
          const s = pos[l.source], t = pos[l.target]
          if (!s || !t) return null
          return <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="var(--nx-border)" strokeWidth={0.8} opacity={0.5} />
        })}
        {nodes.map(n => {
          const p = pos[n.id]
          if (!p) return null
          const color = GROUP_COLORS[n.group] || GROUP_COLORS.system
          const isSel = n.id === selected
          return (
            <g key={n.id} onClick={() => setSelected(isSel ? null : n.id)} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={isSel ? 6 : 4} fill={color} opacity={isSel ? 1 : 0.8}
                stroke={isSel ? '#fff' : 'none'} strokeWidth={1.5} />
              <text x={p.x} y={p.y + 13} textAnchor="middle" fontSize={9}
                fill="var(--nx-text-dim)" fontFamily="var(--nx-font-mono)">
                {(n.label || n.id).slice(0, 12)}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="mem-graph-panel">
        <div className="mem-graph-legend">
          {Object.entries(GROUP_COLORS).map(([g, c]) => (
            <span key={g} className="mem-graph-legend-item">
              <span className="mem-graph-dot" style={{ background: c }} />{g}
            </span>
          ))}
        </div>
        {selNode ? (
          <Panel title="Node Detail">
            <div className="mem-graph-detail">
              <div><span className="mem-graph-key">id</span>{selNode.id}</div>
              <div><span className="mem-graph-key">group</span>{selNode.group}</div>
              <div><span className="mem-graph-key">type</span>{selNode.type}</div>
              <div><span className="mem-graph-key">label</span>{selNode.label}</div>
              {selNode.weight !== undefined && <div><span className="mem-graph-key">weight</span>{selNode.weight}</div>}
              {selNode.confidence > 0 && <div><span className="mem-graph-key">conf</span>{selNode.confidence.toFixed(2)}</div>}
            </div>
          </Panel>
        ) : (
          <Panel title="Graph">
            <div className="mem-graph-stats">
              <div><span className="mem-graph-key">nodes</span>{nodes.length}</div>
              <div><span className="mem-graph-key">links</span>{links.length}</div>
              <div className="mem-graph-hint">Click a node to inspect</div>
            </div>
          </Panel>
        )}
      </div>
    </div>
  )
}

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('ai_jwt')
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

async function request(path, options = {}) {
  const res = await fetch(path, { credentials: 'include', ...options })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || data.message || `${res.status} ${res.statusText}`)
  return data
}

function MemoryHealth() {
  const { data } = useLiveData({
    endpoint: `${API}/health`,
    wsEvent: 'memory:write',
    pollMs: 10000,
  })
  // CONVERSATIONS tile derives from the live /conversations feed — the health
  // endpoint's total_conversations reads a stale conversations_index.json.
  const { data: convos } = useLiveData({
    endpoint: `${API}/conversations`,
    transform: (d) => (typeof d.total === 'number' ? d.total : (d.conversations || []).length),
  })
  const h = data || {}
  return (
    <div className="mem-health">
      {[
        ['Stored Facts', h.total_facts ?? 0],
        ['Conversations', convos ?? h.total_conversations ?? 0],
        ['Semantic Items', h.semantic_items ?? 0],
        ['Source', h.source || 'local_state'],
      ].map(([label, val]) => (
        <Panel key={label} className="mem-health-tile">
          <SectionLabel>{label}</SectionLabel>
          <div className="mem-health-val">{val}</div>
        </Panel>
      ))}
    </div>
  )
}

function PersonalFacts() {
  const { data, loading, error, refresh } = useLiveData({
    endpoint: `${API}/personal-facts`,
    wsEvent: 'memory:write',
    transform: (d) => d.facts || [],
  })
  const facts = data || []
  const [draft, setDraft] = useState({ key: '', value: '', importance: 0.8 })
  const [editing, setEditing] = useState(null)

  async function addFact(e) {
    e.preventDefault()
    if (!draft.value.trim()) return
    try {
      await request(`${API}/personal-facts`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ ...draft, source: 'manual' }),
      })
      setDraft({ key: '', value: '', importance: 0.8 })
      toastSuccess('Personal fact stored')
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  async function updateFact(fact) {
    try {
      await request(`${API}/personal-facts/${encodeURIComponent(fact.id)}`, {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ value: editing.value }),
      })
      toastSuccess('Fact updated')
      setEditing(null)
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  async function deleteFact(id) {
    try {
      await request(`${API}/personal-facts/${encodeURIComponent(id)}`, { method: 'DELETE', headers: authHeaders() })
      toastWarn('Fact forgotten')
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="mem-main">
      <Panel title="Add Personal Fact">
        <form className="mem-manual-form" onSubmit={addFact}>
          <input className="mem-input" placeholder="Key, e.g. preferred stack" value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} />
          <textarea className="mem-textarea" rows={3} placeholder="What should the system remember?" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
          <button className="mem-btn mem-btn--primary">Remember</button>
        </form>
      </Panel>
      <Panel title="Personal Facts">
        {loading && <LoadingSkeleton variant="list" rows={4} />}
        {error && <ErrorState title="Personal memory degraded" message={error} />}
        {!loading && !error && !facts.length && <EmptyState icon="◈" title="No personal facts yet" sub="Add facts that the main AI should respect across sessions." />}
        <div className="mem-facts">
          {facts.map((fact) => (
            <div key={fact.id} className="mem-fact-row">
              <div className="mem-fact-key">{fact.key || 'Fact'}</div>
              {editing?.id === fact.id ? (
                <div className="mem-fact-edit">
                  <input className="mem-input" value={editing.value} onChange={(e) => setEditing({ ...editing, value: e.target.value })} />
                  <button className="mem-btn mem-btn--xs mem-btn--primary" onClick={() => updateFact(fact)}>Save</button>
                  <button className="mem-btn mem-btn--xs" onClick={() => setEditing(null)}>Cancel</button>
                </div>
              ) : (
                <div className="mem-fact-val">{fact.value}</div>
              )}
              <div className="mem-fact-meta">
                <span>{fact.source || 'local'} · {Math.round((fact.importance || 0) * 100)}%</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="mem-btn mem-btn--xs" onClick={() => setEditing({ id: fact.id, value: fact.value })}>Edit</button>
                  <button className="mem-btn mem-btn--xs mem-btn--danger" onClick={() => deleteFact(fact.id)}>Forget</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function ConversationHistory() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const { data, loading, error, refresh } = useLiveData({
    endpoint: `${API}/conversations`,
    transform: (d) => d.conversations || [],
  })
  const conversations = data || []
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const filtered = useMemo(() => conversations.filter((c) => {
    const haystack = `${c.title || ''} ${c.summary || ''} ${c.full_summary || ''}`.toLowerCase()
    return haystack.includes(query.toLowerCase())
  }), [conversations, query])

  async function forgetConversation(id) {
    try {
      await request(`${API}/forget`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ scope: 'conversation', id }),
      })
      toastWarn('Conversation forgotten')
      setSelected(null)
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="mem-main">
      <Panel title="Conversation Search">
        <input className="mem-input" placeholder="Search conversations" value={query} onChange={(e) => setQuery(e.target.value)} />
      </Panel>
      <Panel title="Conversation History">
        {loading && <LoadingSkeleton variant="list" rows={4} />}
        {error && <ErrorState title="Conversation memory degraded" message={error} />}
        {!loading && !error && !filtered.length && (
          <EmptyState
            icon="◷"
            title="No conversations found"
            sub="Completed sessions will appear here once the main AI records them."
            action="Open Chat"
            onAction={() => setActiveSection('nexus')}
          />
        )}
        <div className="mem-convos">
          {filtered.map((conversation) => (
            <div key={conversation.id || conversation.title} className="mem-convo">
              <div className="mem-convo__head" onClick={() => setSelected(selected?.id === conversation.id ? null : conversation)}>
                <div className="mem-convo__title">{conversation.title || conversation.id || 'Conversation'}</div>
                <div className="mem-convo__meta">
                  <span>{conversation.messages || conversation.message_count || 0} msgs</span>
                  <span>{conversation.date || conversation.created_at || '-'}</span>
                </div>
              </div>
              {selected?.id === conversation.id && (
                <div className="mem-convo__body">
                  <div className="mem-convo__summary">{conversation.summary || conversation.full_summary || 'No summary stored.'}</div>
                  <div className="mem-convo__actions">
                    <button className="mem-btn mem-btn--xs" onClick={() => navigator.clipboard?.writeText(JSON.stringify(conversation, null, 2))}>Copy Export</button>
                    <button className="mem-btn mem-btn--xs mem-btn--danger" onClick={() => forgetConversation(conversation.id)}>Forget this</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function SemanticStore() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const { data: stats } = useLiveData({
    endpoint: `${API}/semantic/stats`,
    pollMs: 15000,
  })

  async function search(e) {
    e.preventDefault()
    if (!query.trim()) return
    setBusy(true)
    try {
      const data = await request(`${API}/search?q=${encodeURIComponent(query)}&top_k=12`)
      setResults(data.results || [])
      setStatus({ source: data.source || 'unknown', state: data.results?.length ? 'live' : 'empty' })
    } catch (err) {
      setStatus({ state: 'degraded', error: err.message })
      setResults([])
    } finally {
      setBusy(false)
    }
  }

  async function requestReindex() {
    try {
      const data = await request(`${API}/semantic/reindex`, { method: 'POST', headers: authHeaders() })
      toastWarn(data.message || 'Reindex requires approval')
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <div className="mem-main">
      <Panel title="Semantic Store Status">
        <div className="mem-health">
          <div className="mem-health-tile">
            <SectionLabel>Items</SectionLabel>
            <div className="mem-health-val">{stats?.item_count ?? 0}</div>
          </div>
          <div className="mem-health-tile">
            <SectionLabel>Embedding Mode</SectionLabel>
            <div className="mem-health-val">{stats?.embedding_mode || 'unknown'}</div>
          </div>
          <StatusPill label={(stats?.state || 'empty').toUpperCase()} tone={stats?.state === 'live' ? 'success' : 'idle'} size="sm" />
        </div>
        {stats?.degradedReason && <div className="mem-convo__summary">{stats.degradedReason}</div>}
      </Panel>
      <Panel title="Semantic Search">
        <form className="mem-manual-form" onSubmit={search}>
          <input className="mem-input" placeholder="Search memory objects, projects, facts, conversations" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="mem-btn mem-btn--primary" disabled={busy}>{busy ? 'Searching...' : 'Search'}</button>
          <button type="button" className="mem-btn" onClick={requestReindex}>Request Reindex</button>
        </form>
        {status?.state === 'degraded' && <ErrorState title="Semantic search degraded" message={status.error} />}
        {status?.state === 'empty' && (
          <EmptyState
            icon="⬡"
            title="No semantic matches"
            sub="Try another query or check memory/vector-store setup before relying on semantic recall."
            action="Open Setup"
            onAction={() => setActiveSection('setup')}
          />
        )}
        <div className="mem-convos">
          {results.map((item) => (
            <div key={item.id || item.title} className="mem-convo">
              <div className="mem-convo__head">
                <div className="mem-convo__title">{item.title || item.id}</div>
                <div className="mem-convo__meta">
                  <span>{item.type || 'semantic'}</span>
                  <span>{item.source || status?.source}</span>
                  <span>{typeof item.score === 'number' ? item.score.toFixed(3) : '-'}</span>
                </div>
              </div>
              <div className="mem-convo__body">
                <div className="mem-convo__summary">{item.content || 'No content preview stored.'}</div>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function MemoryHero() {
  const pendingReviewCount = useLearningStore((s) => s.pendingReviewCount)
  const [hero, setHero] = useState({ totalMemories: '—', pendingReviewN: 0, standingTopicsN: 0, vaultNotes: 0 })
  const [memStats, setMemStats] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () => Promise.allSettled([
      request('/api/memory/adapter/status').catch(() => null),
      request('/api/memory/pending-review').catch(() => null),
      request('/api/topics').catch(() => null),
      request('/api/vault/notes').catch(() => null),
      request('/api/memory/stats').catch(() => null),
    ]).then(([adapterRes, reviewRes, topicsRes, vaultRes, statsRes]) => {
      if (cancelled) return
      const adapter = adapterRes.status === 'fulfilled' ? adapterRes.value : null
      const review  = reviewRes.status === 'fulfilled' ? reviewRes.value : null
      const topics  = topicsRes.status === 'fulfilled' ? topicsRes.value : null
      const vault   = vaultRes.status === 'fulfilled' ? vaultRes.value : null
      const stats   = statsRes.status === 'fulfilled' ? statsRes.value : null
      if (stats) setMemStats(stats)
      setHero({
        totalMemories: stats?.total ?? adapter?.chroma?.count ?? '—',
        pendingReviewN: review?.stats?.by_status?.pending ?? (review?.entries?.length ?? 0),
        standingTopicsN: (topics?.topics || []).filter((t) => t.pinned).length,
        vaultNotes: (vault?.notes || vault || []).length || 0,
      })
    })
    load()
    const t = setInterval(load, 30000)
    return () => { cancelled = true; clearInterval(t) }
  }, [pendingReviewCount])

  return (
    <div className="mem-hero">
      <div className="mem-hero__tile">
        <div className="mem-hero__label">TOTAL MEMORIES</div>
        <div className="mem-hero__value" style={{ color: '#22d3ee' }}>{hero.totalMemories}</div>
        <div className="mem-hero__sub">{memStats?.vector_indexed != null ? `${memStats.vector_indexed} vector indexed` : 'in vector store'}</div>
      </div>
      <div className="mem-hero__tile">
        <div className="mem-hero__label">PENDING REVIEW</div>
        <div className="mem-hero__value" style={{ color: hero.pendingReviewN > 0 ? '#fbbf24' : '#22c55e' }}>{hero.pendingReviewN}</div>
        <div className="mem-hero__sub">awaiting decision</div>
      </div>
      <div className="mem-hero__tile">
        <div className="mem-hero__label">STANDING TOPICS</div>
        <div className="mem-hero__value" style={{ color: '#a855f7' }}>{hero.standingTopicsN}</div>
        <div className="mem-hero__sub">pinned & learning</div>
      </div>
      <div className="mem-hero__tile">
        <div className="mem-hero__label">VAULT NOTES</div>
        <div className="mem-hero__value" style={{ color: '#e5c76b' }}>{hero.vaultNotes}</div>
        <div className="mem-hero__sub">obsidian-style</div>
      </div>
      {memStats?.types && Object.keys(memStats.types).length > 0 && (
        <div className="mem-hero__tile mem-hero__tile--types">
          <div className="mem-hero__label">BY TYPE</div>
          <div className="mem-hero__types">
            {Object.entries(memStats.types).map(([type, count]) => (
              <div key={type} className="mem-hero__type-row">
                <span className="mem-hero__type-name">{type}</span>
                <span className="mem-hero__type-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ForgeLessonsPanel() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const lessons = useForgeStore(s => s.memoryLessons)
  const activeRun = useForgeStore(s => s.activeRun)
  const refresh = useForgeStore(s => s.refresh)

  useEffect(() => {
    refresh({ silent: true, reason: 'memory_forge_lessons' }).catch(() => {})
  }, [refresh])

  if (!lessons?.length && !activeRun) return null

  return (
    <Panel title="Forge Lessons" className="mem-forge">
      <div className="mem-forge__head">
        <div>
          <div className="mem-forge__title">{lessons?.length || 0} lesson candidates</div>
          <div className="mem-forge__sub">Distilled from Forge run reports and audit trails.</div>
        </div>
        <button className="mem-btn mem-btn--xs" type="button" onClick={() => setActiveSection('ascend-forge')}>
          Open Forge
        </button>
      </div>
      <div className="mem-forge__list">
        {(lessons || []).slice(0, 5).map((lesson, index) => (
          <div key={lesson.lesson_id || lesson.id || index} className="mem-convo">
            <div className="mem-convo__head">
              <div className="mem-convo__title">{lesson.title || lesson.summary || lesson.category || 'Forge lesson'}</div>
              <div className="mem-convo__meta">
                <span>{lesson.confidence != null ? `confidence ${lesson.confidence}` : 'candidate'}</span>
                <span>{lesson.source_run_id || lesson.run_id || activeRun?.run_id || 'no run link'}</span>
              </div>
            </div>
            <div className="mem-convo__body">
              <div className="mem-convo__summary">{lesson.content || lesson.text || lesson.rationale || 'No lesson body supplied.'}</div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function KnowledgeBase() {
  const { data, loading, error } = useLiveData({
    endpoint: '/api/knowledge/search',
    wsEvent: 'memory:write',
    transform: (d) => d.entries || [],
  })
  const entries = (data || []).slice(0, 50)
  return (
    <div className="mem-main">
      <Panel title="Knowledge Base">
        {loading && <LoadingSkeleton variant="list" rows={4} />}
        {error && <ErrorState title="Knowledge base unavailable" message={error} />}
        {!loading && !error && !entries.length && (
          <EmptyState icon="◈" title="No knowledge entries yet" sub="Entries are added automatically as the system researches and learns." />
        )}
        <div className="mem-facts">
          {entries.map((e, i) => (
            <div key={e.id || `kb-${i}`} className="mem-fact-row">
              <div className="mem-fact-key">{e.topic || 'Entry'}</div>
              <div className="mem-fact-val">{e.content || '—'}</div>
              <div className="mem-fact-meta">
                <span>
                  {e.source || 'system'}
                  {e.importance != null ? ` · ${Math.round(e.importance * 100)}%` : ''}
                  {e.tags?.length ? ` · ${e.tags.join(', ')}` : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

export default function MemoryPage() {
  const [tab, setTab] = useState('facts')
  const [wizardOpen, setWizardOpen] = useState(false)
  return (
    <div className="mem-page">
      <div className="mem-header">
        <div>
          <span className="mem-header__title">MEMORY SYSTEM</span>
          <span className="mem-header__sub">Main AI memory workspaces. AscendForge writes memory only through approved build artifacts and audit events.</span>
        </div>
        <div className="mem-convo__actions">
          {tabs.map(([id, label]) => (
            <button key={id} className={`mem-btn ${tab === id ? 'mem-btn--primary' : ''}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <MemoryHero />
      <MemoryHealth />
      <ForgeLessonsPanel />
      {tab === 'facts' && <PersonalFacts />}
      {tab === 'knowledge' && <KnowledgeBase />}
      {tab === 'conversations' && <ConversationHistory />}
      {tab === 'semantic' && <SemanticStore />}
      {tab === 'standing-topics' && (
        <StandingTopicsPanel
          onLearnNew={() => setWizardOpen(true)}
          onOpenTopic={(id) => { window.location.hash = `#/knowledge?topic=${id}` }}
        />
      )}
      {tab === 'review-queue' && <PendingReviewQueue />}
      {tab === 'graph' && <MemoryGraph />}
      <LearnTopicWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </div>
  )
}
