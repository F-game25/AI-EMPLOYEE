import { useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import { normalizeGraphPayload, useBrainStore } from '../../store/brainStore'
import { useAppStore } from '../../store/appStore'
import { useSystemStore } from '../../store/systemStore'
import UnifiedBrain from '../three/UnifiedBrain'
import ErrorBoundary from '../ErrorBoundary'
import { EmptyState, ErrorState } from '../nexus-ui'
import KPITile from '../nexus-ui/KPITile'
import Panel from '../nexus-ui/Panel'
import SectionLabel from '../nexus-ui/SectionLabel'
import StatusPill from '../nexus-ui/StatusPill'
import './NeuralNetworkPage.css'
import MemoryObservability from './neural/MemoryObservability'

// ── Icons (inline SVG, ~24px) ─────────────────────────────────────────────────

const IconNodes = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.2" />
    <circle cx="1.5" cy="2.5" r="1.2" stroke="currentColor" strokeWidth="1" />
    <circle cx="12.5" cy="2.5" r="1.2" stroke="currentColor" strokeWidth="1" />
    <circle cx="1.5" cy="11.5" r="1.2" stroke="currentColor" strokeWidth="1" />
    <circle cx="12.5" cy="11.5" r="1.2" stroke="currentColor" strokeWidth="1" />
    <line x1="4.3" y1="5.5" x2="2.4" y2="3.6" stroke="currentColor" strokeWidth="0.9" />
    <line x1="9.7" y1="5.5" x2="11.6" y2="3.6" stroke="currentColor" strokeWidth="0.9" />
    <line x1="4.3" y1="8.5" x2="2.4" y2="10.4" stroke="currentColor" strokeWidth="0.9" />
    <line x1="9.7" y1="8.5" x2="11.6" y2="10.4" stroke="currentColor" strokeWidth="0.9" />
  </svg>
)

const IconEdges = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M2 12 L12 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    <circle cx="2" cy="12" r="1.5" fill="currentColor" />
    <circle cx="12" cy="2" r="1.5" fill="currentColor" />
    <circle cx="7" cy="7" r="1.2" fill="currentColor" opacity="0.6" />
  </svg>
)

const IconKnowledge = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M7 1 L13 4.5 L13 9.5 L7 13 L1 9.5 L1 4.5 Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    <path d="M7 5 L9 6.5 L9 9 L7 10.5 L5 9 L5 6.5 Z" stroke="currentColor" strokeWidth="0.9" strokeLinejoin="round" />
  </svg>
)

const IconBrain = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M7 2.5 C5 2.5 3 4 3 6.5 C3 8 3.5 9 4.5 9.5 L4.5 11.5 L9.5 11.5 L9.5 9.5 C10.5 9 11 8 11 6.5 C11 4 9 2.5 7 2.5Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    <line x1="7" y1="5" x2="7" y2="9" stroke="currentColor" strokeWidth="0.9" />
    <line x1="5.5" y1="6.5" x2="8.5" y2="6.5" stroke="currentColor" strokeWidth="0.9" />
  </svg>
)

const IconEmpty = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <path d="M24 4 L44 15 L44 33 L24 44 L4 33 L4 15 Z"
      stroke="rgba(229,199,107,0.25)" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
    <path d="M24 13 L34 18.5 L34 29.5 L24 35 L14 29.5 L14 18.5 Z"
      stroke="rgba(229,199,107,0.15)" strokeWidth="1" strokeLinejoin="round" fill="none" />
    <line x1="24" y1="4" x2="24" y2="13" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <line x1="44" y1="15" x2="34" y2="18.5" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <line x1="44" y1="33" x2="34" y2="29.5" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <line x1="24" y1="44" x2="24" y2="35" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <line x1="4" y1="33" x2="14" y2="29.5" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <line x1="4" y1="15" x2="14" y2="18.5" stroke="rgba(229,199,107,0.15)" strokeWidth="1" />
    <circle cx="24" cy="24" r="3" stroke="rgba(229,199,107,0.2)" strokeWidth="1" fill="none" />
  </svg>
)

// ── Helpers ───────────────────────────────────────────────────────────────────

const TYPE_BADGE_TONE = { LEARN: 'success', QUERY: 'cool', SYNC: 'gold' }

const LAYER_DEFS = [
  { key: 'input',    label: 'Input Layer',  color: 'var(--nx-cyan)',    defaultCount: 8  },
  { key: 'hidden1',  label: 'Hidden-1',     color: 'var(--nx-gold)',    defaultCount: 24 },
  { key: 'hidden2',  label: 'Hidden-2',     color: 'var(--nx-gold)',    defaultCount: 16 },
  { key: 'output',   label: 'Output',       color: 'var(--nx-success)', defaultCount: 4  },
  { key: 'memory',   label: 'Memory',       color: 'var(--nx-purple)',  defaultCount: 12 },
]

function buildLayerCounts(nodes, knowledge) {
  const input  = nodes.filter(n => n.type === 'input').length
  const output = nodes.filter(n => n.type === 'output').length
  const mem    = knowledge?.length || nodes.filter(n => n.type === 'memory').length
  const total  = nodes.length
  const hiddenTotal = Math.max(0, total - input - output - mem)
  const hidden1 = Math.round(hiddenTotal * 0.6)
  const hidden2 = Math.max(0, hiddenTotal - hidden1)
  return { input, hidden1, hidden2, output, memory: mem }
}

const VIEW_LABELS = ['TOP', 'SIDE', 'FRONT']
const MEMORY_TABS = [
  { id: 'graph', label: 'Graph View' },
  { id: 'router', label: 'Memory Router' },
  { id: 'rag', label: 'Semantic RAG' },
  { id: 'kg', label: 'Knowledge Graph' },
  { id: 'sql', label: 'SQL Memory' },
  { id: 'episodic', label: 'Episodic' },
  { id: 'procedural', label: 'Procedural' },
]
const READINESS_POLL_MS = 1500

const BRAIN_STATE_TONE = s => {
  switch ((s || '').toUpperCase()) {
    case 'ACTIVE':   return 'success'
    case 'LEARNING': return 'cool'
    case 'IDLE':     return 'gold'
    case 'ERROR':    return 'alert'
    default:         return 'idle'
  }
}

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('ai_jwt')
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

async function fetchJson(path, options = {}) {
  // Attach the operator JWT (same contract as api/client.js) so protected memory
  // routes don't silently 401.
  const token = sessionStorage.getItem('ai_jwt')
  const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers }
  const res = await fetch(path, { credentials: 'include', ...options, headers })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || data.message || `${res.status} ${res.statusText}`)
  return data
}


// ── Mobile guard ─────────────────────────────────────────────────────────────

function useMediaQuery(query) {
  const getMatch = () => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
    return window.matchMedia(query).matches
  }
  const [matches, setMatches] = useState(getMatch)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mq = window.matchMedia(query)
    const handler = e => setMatches(e.matches)
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
    mq.addListener?.(handler)
    return () => mq.removeListener?.(handler)
  }, [query])
  return matches
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NeuralNetworkPage() {
  const nodes      = useBrainStore(s => s.nodes)          || []
  const edges      = useBrainStore(s => s.links)          || []
  const setGraph   = useBrainStore(s => s.setGraph)
  const setVaultGraph = useBrainStore(s => s.setVaultGraph)
  const knowledge  = useBrainStore(s => s.stats?.knowledge) || []
  const graphStats = useBrainStore(s => s.stats)          || {}
  const brainState = useAppStore(s => s.brainState)
  const readiness = useSystemStore(s => s.readiness)
  const setReadiness = useSystemStore(s => s.setReadiness)

  const [hydrated, setHydrated] = useState(false)
  const [isStaleFallback, setIsStaleFallback] = useState(false)
  const [activeView, setActiveView] = useState('TOP')
  const [showKnowledgeNodes,   setShowKnowledgeNodes]   = useState(true)
  const [showMemoryLinks,      setShowMemoryLinks]       = useState(true)
  const [showAgentConnections, setShowAgentConnections]  = useState(false)
  const [showVaultNetwork,     setShowVaultNetwork]      = useState(true)
  const [density, setDensity] = useState(75)
  const [memoryTab, setMemoryTab] = useState('graph')
  const [memoryStatus, setMemoryStatus] = useState(null)
  const [graphMaintenance, setGraphMaintenance] = useState(null)
  const [memoryStatusError, setMemoryStatusError] = useState(null)
  const [routerQuery, setRouterQuery] = useState('')
  const [retrievalResult, setRetrievalResult] = useState(null)
  const [retrievalBusy, setRetrievalBusy] = useState(false)
  const [retrievalError, setRetrievalError] = useState(null)
  const [sqlForm, setSqlForm] = useState({ database: '', sql: '' })
  const [sqlResult, setSqlResult] = useState(null)
  const [maintenanceBusy, setMaintenanceBusy] = useState(false)
  const [maintenanceMessage, setMaintenanceMessage] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState('')
  const [mergeConfirm, setMergeConfirm] = useState('')
  const [selectedBackup, setSelectedBackup] = useState('')
  const retryCount = useRef(0)

  // ── Vault graph fetch + WS live sync ─────────────────────────────────
  useEffect(() => {
    const loadVault = () => {
      api.get('/api/vault/graph')
        .then(d => setVaultGraph(d?.nodes || [], d?.links || []))
        .catch(() => {})
    }
    loadVault()
    const handler = (e) => {
      const t = e.detail?.type || e.type || ''
      if (t === 'vault:note_updated' || t === 'memory:added' || t.startsWith('vault:')) {
        loadVault()
      }
    }
    window.addEventListener('ws:event', handler)
    window.addEventListener('ws:memory-added', handler)
    return () => {
      window.removeEventListener('ws:event', handler)
      window.removeEventListener('ws:memory-added', handler)
    }
  }, [setVaultGraph])

  useEffect(() => {
    let cancelled = false
    if (readiness?.graphReady) return
    retryCount.current = 0
    const MAX_RETRIES = 8
    const poll = () => {
      fetch('/api/readiness', { signal: AbortSignal.timeout(5000) })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (cancelled) return
          if (data) setReadiness(data)
          if (!data?.graphReady) {
            retryCount.current += 1
            if (retryCount.current >= MAX_RETRIES) {
              setReadiness({ graphReady: true, phase: 'TIMEOUT' })
              setIsStaleFallback(true)
            } else {
              setTimeout(poll, READINESS_POLL_MS)
            }
          }
        })
        .catch(() => {
          if (!cancelled) {
            retryCount.current += 1
            if (retryCount.current >= MAX_RETRIES) {
              setReadiness({ graphReady: true, phase: 'TIMEOUT' })
              setIsStaleFallback(true)
            } else {
              setTimeout(poll, READINESS_POLL_MS)
            }
          }
        })
    }
    poll()
    return () => { cancelled = true }
  }, [readiness?.graphReady, setReadiness])

  useEffect(() => {
    let cancelled = false
    const load = () => {
      Promise.all([
        fetchJson('/api/memory/router/status').catch(error => ({ error: error.message })),
        fetchJson('/api/memory/graph/status').catch(error => ({ error: error.message, state: 'degraded' })),
        fetchJson('/api/memory/graph/maintenance').catch(error => ({ error: error.message, state: 'degraded', backups: [] })),
        fetchJson('/api/memory/sql/status').catch(error => ({ error: error.message, state: 'degraded', databases: [] })),
        fetchJson('/api/memory/procedural/status').catch(error => ({ error: error.message, state: 'degraded' })),
      ]).then(([router, graph, maintenance, sql, procedural]) => {
        if (cancelled) return
        setMemoryStatus({ router, graph, sql, procedural })
        setGraphMaintenance(maintenance)
        setMemoryStatusError(router.error || null)
        if (!sqlForm.database && sql.databases?.[0]?.id) {
          setSqlForm(current => current.database ? current : { ...current, database: sql.databases[0].id })
        }
      }).catch(error => {
        if (!cancelled) setMemoryStatusError(error.message)
      })
    }
    load()
    const id = setInterval(load, 10000)
    return () => { cancelled = true; clearInterval(id) }
  }, [sqlForm.database])

  useEffect(() => {
    let cancelled = false
    if (!readiness?.graphReady) {
      setHydrated(false)
      return () => { cancelled = true }
    }
    if (nodes?.length) { setHydrated(true); return () => { cancelled = true } }
    Promise.all([
      api.get('/api/neural-brain/graph?depth=2&limit=300').catch(() => null),
      api.get('/api/brain/graph').catch(() => null),
      api.get('/api/neural-brain/graph/snapshot').catch(() => null),
    ]).then((payloads) => {
      if (cancelled) return
      // Pick the richest available source (native memory graph → in-memory brain → snapshot)
      const candidates = payloads.map(p => normalizeGraphPayload(p || {}))
      const best = candidates.reduce((a, b) => (b.nodes.length > a.nodes.length ? b : a), { nodes: [], links: [] })
      if (best.nodes.length) setGraph(best)
      setHydrated(true)
    })
    return () => { cancelled = true }
  }, [readiness?.graphReady]) // eslint-disable-line react-hooks/exhaustive-deps

  const runRetrieval = async (event) => {
    event.preventDefault()
    if (!routerQuery.trim()) return
    setRetrievalBusy(true)
    setRetrievalError(null)
    try {
      const result = await fetchJson('/api/memory/router/query', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ query: routerQuery, max_tokens: 2200, mode: 'neural_network_operator_test' }),
      })
      setRetrievalResult(result)
    } catch (error) {
      setRetrievalError(error.message)
    } finally {
      setRetrievalBusy(false)
    }
  }

  const runSql = async (event) => {
    event.preventDefault()
    setSqlResult(null)
    try {
      const result = await fetchJson('/api/memory/sql/query', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(sqlForm),
      })
      setSqlResult(result)
    } catch (error) {
      setSqlResult({ error: error.message })
    }
  }

  const refreshGraphMaintenance = async () => {
    const [graph, maintenance] = await Promise.all([
      fetchJson('/api/memory/graph/status'),
      fetchJson('/api/memory/graph/maintenance'),
    ])
    setMemoryStatus(current => ({ ...(current || {}), graph }))
    setGraphMaintenance(maintenance)
    if (!selectedBackup && maintenance.backups?.[0]?.id) setSelectedBackup(maintenance.backups[0].id)
    return { graph, maintenance }
  }

  const runGraphMaintenance = async (path, body, successLabel) => {
    setMaintenanceBusy(true)
    setMaintenanceMessage('')
    try {
      const result = await fetchJson(path, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body || {}),
      })
      await refreshGraphMaintenance()
      setMaintenanceMessage(`${successLabel}: ${result.integrity?.status || result.backup?.id || 'completed'}`)
      return result
    } catch (error) {
      setMaintenanceMessage(error.message)
      return null
    } finally {
      setMaintenanceBusy(false)
    }
  }

  const createGraphBackup = () => runGraphMaintenance('/api/memory/graph/backup', { reason: 'operator-ui' }, 'Backup created')
  const repairGraph = () => runGraphMaintenance('/api/memory/graph/repair', { backupFirst: true }, 'Repair completed')
  const restoreGraph = async () => {
    const result = await runGraphMaintenance('/api/memory/graph/restore', {
      backup_id: selectedBackup,
      confirm: restoreConfirm,
    }, 'Restore completed')
    if (result?.ok) setRestoreConfirm('')
  }
  const mergeGraphConflict = async (group) => {
    if (!group?.candidates?.length) return
    const survivor = group.survivor_id || group.candidates[0].id
    const duplicateIds = group.candidates.map(candidate => candidate.id).filter(id => id && id !== survivor)
    const result = await runGraphMaintenance('/api/memory/graph/merge', {
      survivor_id: survivor,
      duplicate_ids: duplicateIds,
      confirm: mergeConfirm,
    }, 'Merge completed')
    if (result?.ok) setMergeConfirm('')
  }

  const isMobile = useMediaQuery('(max-width: 768px)')

  if (isMobile) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--nx-text-dim, #888)', fontFamily: 'var(--nx-font-mono, monospace)' }}>
      <div style={{ fontSize: 32, marginBottom: 16 }}>◈</div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>3D NEURAL GRAPH</div>
      <div style={{ fontSize: 11, opacity: 0.6 }}>Desktop only — WebGL 3D requires a larger screen</div>
    </div>
  )

  const hasData           = nodes.length > 0
  const nodeCount         = nodes.length
  const edgeCount         = edges.length
  const knowledgeCount    = Array.isArray(knowledge) ? knowledge.length : 0
  const showFallbackBanner = isStaleFallback || graphStats?.source === 'fallback'
  const brainStatus   = brainState?.status ?? 'IDLE'
  const layerCounts   = buildLayerCounts(nodes, knowledge)
  const maxLayerCount = Math.max(...Object.values(layerCounts))
  const recentEdges   = edges.slice(-5).reverse()
  const routerLanes = memoryStatus?.router?.lanes || {}
  const readyLanes = Object.values(routerLanes).filter(lane => lane?.ready).length

  return (
    <div className="nnp">

      {/* ── TOP KPI STRIP ─────────────────────────────────────────────── */}
      <div className="nnp__kpi-row">
        <KPITile
          label="Active Nodes"
          value={nodeCount}
          icon={<IconNodes />}
          iconTone="gold"
          accent
          sub="graph vertices"
        />
        <KPITile
          label="Active Edges"
          value={edgeCount}
          icon={<IconEdges />}
          iconTone="cool"
          sub="neural connections"
        />
        <KPITile
          label="Knowledge Entries"
          value={knowledgeCount}
          icon={<IconKnowledge />}
          iconTone="success"
          sub="stored facts"
        />
        <div className="nnp__brain-state-tile">
          <KPITile
            label="Brain State"
            value={
              <StatusPill
                label={brainStatus}
                tone={BRAIN_STATE_TONE(brainStatus)}
                size="sm"
                pulse={brainStatus === 'ACTIVE' || brainStatus === 'LEARNING'}
              />
            }
            icon={<IconBrain />}
            iconTone={BRAIN_STATE_TONE(brainStatus)}
            sub="cognitive mode"
          />
        </div>
      </div>

      <div className="nnp-memory-tabs" role="tablist" aria-label="Neural memory views">
        {MEMORY_TABS.map(tab => (
          <button
            key={tab.id}
            className={`nnp-memory-tab ${memoryTab === tab.id ? 'nnp-memory-tab--active' : ''}`}
            onClick={() => setMemoryTab(tab.id)}
            role="tab"
            aria-selected={memoryTab === tab.id}
          >
            {tab.label}
          </button>
        ))}
        <div className="nnp-memory-tabs__status">
          <StatusPill
            label={`${readyLanes}/5 MEMORY LANES`}
            tone={readyLanes >= 4 ? 'success' : readyLanes ? 'warn' : 'idle'}
            size="sm"
            dot={readyLanes > 0}
          />
        </div>
      </div>

      {/* ── MAIN AREA ─────────────────────────────────────────────────── */}
      {memoryTab === 'graph' ? (
      <div className="nnp__main">

        {/* 3D Graph ──────────────────────────────────────────────────── */}
        <div className="nnp__graph-container" aria-label="Neural knowledge graph">
          {showFallbackBanner && (
            <div className="nn-stale-banner">
              Showing representative graph — live brain data unavailable
            </div>
          )}
          {!readiness?.graphReady ? (
            <div className="nnp__empty-state">
              <IconEmpty />
              <div className="nnp__empty-title">NEURAL GRAPH INITIALIZING</div>
              <div className="nnp__empty-sub">
                AI core phase: {readiness?.phase || 'INITIALIZING'}.
                {readiness?.degradedReasons?.length ? ` Waiting on ${readiness.degradedReasons.join(', ')}.` : ' Waiting for graph service.'}
              </div>
            </div>
          ) : hydrated ? (
            <>
              {hasData ? (
                <ErrorBoundary
                  label="neural-graph"
                  severity="widget"
                  fallback={
                    <ErrorState
                      message="3D renderer failed — WebGL may not be available"
                      onRetry={() => window.location.reload()}
                    />
                  }
                >
                  <UnifiedBrain
                    showKnowledgeNodes={showKnowledgeNodes}
                    showMemoryLinks={showMemoryLinks}
                    showAgentConnections={showAgentConnections}
                    showVaultNetwork={showVaultNetwork}
                    activeView={activeView}
                    density={density / 100}
                  />
                </ErrorBoundary>
              ) : (
                <div className="nnp__empty-state">
                  <IconEmpty />
                  <div className="nnp__empty-title">NO NODES LOADED</div>
                  <div className="nnp__empty-sub">
                    Start the system and run tasks to populate the knowledge graph.
                    Nodes appear as the AI reasons.
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="nnp__graph-loading">
              <div className="nnp__graph-loading-pulse" />
              <span>Initializing neural graph…</span>
            </div>
          )}

          {/* Bottom overlay + label */}
          <div className="nnp__graph-overlay" aria-hidden="true" />
          <div className="nnp__graph-label" aria-hidden="true">
            NEURAL KNOWLEDGE GRAPH
          </div>

          {/* Live node/edge badge */}
          {hasData && (
            <div className="nnp__graph-badge" aria-hidden="true">
              <span className="nnp__graph-badge-dot" />
              {nodeCount} nodes · {edgeCount} edges
            </div>
          )}
        </div>

        {/* Right Panel ──────────────────────────────────────────────── */}
        <div className="nnp__right">

          {/* Graph Controls */}
          <Panel title="Graph Controls" size="compact" tight corners>
            <div className="nnp__controls">

              <SectionLabel rule>VISIBILITY</SectionLabel>

              <div className="nnp__toggles">
                <button
                  className={`nnp__toggle ${showKnowledgeNodes ? 'nnp__toggle--on' : ''}`}
                  onClick={() => setShowKnowledgeNodes(v => !v)}
                  aria-pressed={showKnowledgeNodes}
                >
                  <span className="nnp__toggle-dot" />
                  Knowledge Nodes
                </button>
                <button
                  className={`nnp__toggle ${showMemoryLinks ? 'nnp__toggle--on' : ''}`}
                  onClick={() => setShowMemoryLinks(v => !v)}
                  aria-pressed={showMemoryLinks}
                >
                  <span className="nnp__toggle-dot" />
                  Memory Links
                </button>
                <button
                  className={`nnp__toggle ${showAgentConnections ? 'nnp__toggle--on' : ''}`}
                  onClick={() => setShowAgentConnections(v => !v)}
                  aria-pressed={showAgentConnections}
                >
                  <span className="nnp__toggle-dot" />
                  Agent Connections
                </button>
                <button
                  className={`nnp__toggle ${showVaultNetwork ? 'nnp__toggle--on' : ''}`}
                  onClick={() => setShowVaultNetwork(v => !v)}
                  aria-pressed={showVaultNetwork}
                >
                  <span className="nnp__toggle-dot" />
                  Vault Network
                </button>
              </div>

              <SectionLabel rule>NODE DENSITY</SectionLabel>

              <div className="nnp__density-wrap">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={density}
                  onChange={e => setDensity(+e.target.value)}
                  className="nnp__slider"
                  aria-label="Node density"
                />
                <span className="nnp__density-val">{density}%</span>
              </div>

              <SectionLabel rule>VIEW PRESET</SectionLabel>

              <div className="nnp__view-presets">
                {VIEW_LABELS.map(v => (
                  <button
                    key={v}
                    className={`nnp__preset-btn ${activeView === v ? 'nnp__preset-btn--active' : ''}`}
                    onClick={() => setActiveView(v)}
                    aria-pressed={activeView === v}
                  >
                    {v}
                  </button>
                ))}
              </div>

            </div>
          </Panel>

          {/* Layer Breakdown */}
          <Panel title="Layer Breakdown" size="compact" tight corners>
            <div className="nnp__layers">
              {LAYER_DEFS.map(({ key, label, color, defaultCount }) => {
                const count = key === 'input'  ? layerCounts.input
                            : key === 'hidden1' ? layerCounts.hidden1
                            : key === 'hidden2' ? layerCounts.hidden2
                            : key === 'output'  ? layerCounts.output
                            : layerCounts.memory
                const pct = maxLayerCount > 0 ? (count / maxLayerCount) * 100 : defaultCount / 24 * 100

                return (
                  <div key={key} className="nnp__layer-row">
                    <span className="nnp__layer-name">{label}</span>
                    <div className="nnp__layer-bar-wrap">
                      <div
                        className="nnp__layer-bar"
                        style={{ width: `${pct}%`, background: color }}
                      />
                    </div>
                    <span className="nnp__layer-count" style={{ color }}>{count}</span>
                  </div>
                )
              })}
            </div>
          </Panel>

          {/* Active Connections */}
          <Panel title="Active Connections" size="compact" tight corners>
            <div className="nnp__connections">
              {recentEdges.length > 0 ? recentEdges.map((edge, i) => {
                const src = edge.source?.id ?? edge.source ?? '—'
                const tgt = edge.target?.id ?? edge.target ?? '—'
                const weight = typeof edge.strength === 'number'
                  ? edge.strength.toFixed(2)
                  : '0.50'
                const types = ['LEARN', 'QUERY', 'SYNC']
                const type = types[i % types.length]

                return (
                  <div key={i} className="nnp__conn-row">
                    <span className="nnp__conn-src" title={String(src)}>
                      {String(src).slice(0, 10)}
                    </span>
                    <span className="nnp__conn-arrow">→</span>
                    <span className="nnp__conn-tgt" title={String(tgt)}>
                      {String(tgt).slice(0, 10)}
                    </span>
                    <span className="nnp__conn-weight">{weight}</span>
                    <StatusPill
                      label={type}
                      tone={TYPE_BADGE_TONE[type]}
                      size="sm"
                      dot={false}
                    />
                  </div>
                )
              }) : (
                <EmptyState icon="[]" title="No live connections" sub="Connections appear after graph or memory routes produce live edges." />
              )}
            </div>
          </Panel>

        </div>{/* /nnp__right */}
      </div>
      ) : (
              <MemoryObservability
                tab={memoryTab}
                status={memoryStatus}
                statusError={memoryStatusError}
          query={routerQuery}
          setQuery={setRouterQuery}
          retrievalResult={retrievalResult}
          retrievalBusy={retrievalBusy}
          retrievalError={retrievalError}
          onRunRetrieval={runRetrieval}
          sqlForm={sqlForm}
          setSqlForm={setSqlForm}
                sqlResult={sqlResult}
                onRunSql={runSql}
                maintenance={graphMaintenance}
                maintenanceBusy={maintenanceBusy}
                maintenanceMessage={maintenanceMessage}
                restoreConfirm={restoreConfirm}
                setRestoreConfirm={setRestoreConfirm}
                selectedBackup={selectedBackup}
                setSelectedBackup={setSelectedBackup}
                mergeConfirm={mergeConfirm}
                setMergeConfirm={setMergeConfirm}
                onGraphBackup={createGraphBackup}
                onGraphRepair={repairGraph}
                onGraphRestore={restoreGraph}
                onGraphMerge={mergeGraphConflict}
              />
      )}
    </div>
  )
}
