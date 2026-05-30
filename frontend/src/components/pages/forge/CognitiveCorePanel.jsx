import { useState, useEffect, useCallback } from 'react'
import { SectionLabel, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import api from '../../../api/client'

// ── shared style tokens ──────────────────────────────────────────────
const BRONZE = 'var(--af-bronze-bright)'
const MONO = "'JetBrains Mono', 'SF Mono', Menlo, monospace"

const CONF_COLORS = { high: '#22c55e', medium: '#f59e0b', low: '#6b7280' }
const AGREE_COLORS = {
  agree: '#22c55e',
  disagree: '#f59e0b',
  no_active_model: '#6b7280',
  not_applicable: '#6b7280',
  failed: '#ef4444',
}
const EVENT_COLORS = {
  consolidation: '#22c55e',
  advisory: '#60a5fa',
  context_packet: '#a78bfa',
  contradiction: '#ef4444',
  promotion: '#f59e0b',
  reinforcement: '#22c55e',
  default: '#9ca3af',
}

const confColor = (c) => {
  const n = typeof c === 'number' ? c : parseFloat(c)
  if (Number.isNaN(n)) return CONF_COLORS.low
  if (n >= 0.75) return CONF_COLORS.high
  if (n >= 0.45) return CONF_COLORS.medium
  return CONF_COLORS.low
}
const agreeColor = (a) => AGREE_COLORS[a] || '#6b7280'
const eventColor = (t) => EVENT_COLORS[t] || EVENT_COLORS.default

const pct = (v) => (v == null ? '—' : `${Math.round((v <= 1 ? v * 100 : v))}%`)
const fmtTime = (t) => {
  if (!t) return '—'
  try {
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return String(t)
    return d.toLocaleString()
  } catch {
    return String(t)
  }
}

// ── small primitives ─────────────────────────────────────────────────
const card = {
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 10,
  padding: 14,
}

function Chip({ label, value, color }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 9px',
        borderRadius: 999,
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.10)',
        fontFamily: MONO,
        fontSize: 11,
        color: '#cbd5e1',
      }}
    >
      <span style={{ color: '#7b8794' }}>{label}</span>
      <strong style={{ color: color || '#e2e8f0' }}>{value}</strong>
    </span>
  )
}

function Btn({ children, onClick, disabled, primary, small }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        fontFamily: MONO,
        fontSize: small ? 11 : 12,
        padding: small ? '4px 10px' : '6px 14px',
        borderRadius: 7,
        border: primary ? `1px solid ${BRONZE}` : '1px solid rgba(255,255,255,0.14)',
        background: primary ? 'rgba(207,138,58,0.14)' : 'rgba(255,255,255,0.03)',
        color: primary ? BRONZE : '#cbd5e1',
        transition: 'all .15s',
      }}
    >
      {children}
    </button>
  )
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 4,
        flexWrap: 'wrap',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        marginBottom: 14,
        paddingBottom: 2,
      }}
    >
      {tabs.map((t) => {
        const on = t.key === active
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            style={{
              cursor: 'pointer',
              fontFamily: MONO,
              fontSize: 12,
              padding: '7px 14px',
              border: 'none',
              borderBottom: on ? `2px solid ${BRONZE}` : '2px solid transparent',
              background: 'transparent',
              color: on ? BRONZE : '#8b95a1',
              fontWeight: on ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

function Loading({ label }) {
  return (
    <div style={{ ...card, fontFamily: MONO, fontSize: 12, color: '#7b8794', textAlign: 'center' }}>
      {label || 'Loading…'}
    </div>
  )
}

function ErrorBox({ message, onRetry }) {
  return (
    <div
      style={{
        ...card,
        borderColor: 'rgba(239,68,68,0.4)',
        background: 'rgba(239,68,68,0.06)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ fontFamily: MONO, fontSize: 12, color: '#fca5a5' }}>
        {message || 'Failed to load.'}
      </div>
      {onRetry && (
        <div>
          <Btn small onClick={onRetry}>
            Retry
          </Btn>
        </div>
      )}
    </div>
  )
}

function PaneHeader({ title, onRefresh, busy, extra }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 12,
        gap: 10,
      }}
    >
      <SectionLabel>{title}</SectionLabel>
      <div style={{ display: 'flex', gap: 8 }}>
        {extra}
        {onRefresh && (
          <Btn small onClick={onRefresh} disabled={busy}>
            {busy ? '…' : 'Refresh'}
          </Btn>
        )}
      </div>
    </div>
  )
}

// ── generic async-list hook ──────────────────────────────────────────
function useAsync(fn, deps, enabled = true) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    setError(null)
    try {
      const res = await fn()
      if (res && res.ok === false) throw new Error(res.error || 'Request failed')
      setData(res)
    } catch (e) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, reload: load, setData }
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 1 — GRAPH
// ═══════════════════════════════════════════════════════════════════════
function GraphTab({ projectId, summary, reloadSummary }) {
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState(null)

  const runConsolidation = async () => {
    setRunning(true)
    try {
      const res = await api.forge.cognitive.consolidateMemoryGraph(projectId, {})
      if (res && res.ok === false) throw new Error(res.error || 'Consolidation failed')
      setReport(res?.consolidation || null)
      toastSuccess('Consolidation complete')
      reloadSummary && reloadSummary()
    } catch (e) {
      toastError(e?.message || 'Consolidation failed')
    } finally {
      setRunning(false)
    }
  }

  if (!summary) {
    return <EmptyState title="No graph data" body="The memory graph has not been populated yet." />
  }

  const byType = summary.by_type || {}
  const topFiles = summary.top_files || []
  const topSkills = summary.top_skills || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Chip label="nodes" value={summary.nodes ?? 0} />
        <Chip label="edges" value={summary.edges ?? 0} />
        <Chip label="high-conf" value={summary.high_confidence ?? 0} color={CONF_COLORS.high} />
        <Chip label="contradicted" value={summary.contradicted ?? 0} color="#ef4444" />
        <Chip label="failure patterns" value={summary.failure_patterns ?? 0} color="#f59e0b" />
      </div>

      <div style={card}>
        <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
          NODES BY TYPE
        </div>
        {Object.keys(byType).length === 0 ? (
          <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>none</div>
        ) : (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(byType).map(([k, v]) => (
              <Chip key={k} label={k} value={v} />
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ ...card, flex: '1 1 280px' }}>
          <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
            TOP FILES
          </div>
          {topFiles.length === 0 ? (
            <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>none</div>
          ) : (
            topFiles.map((f, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: MONO,
                  fontSize: 11,
                  color: '#cbd5e1',
                  padding: '3px 0',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {f.title}
                </span>
                <span style={{ color: BRONZE, marginLeft: 8 }}>{f.links}</span>
              </div>
            ))
          )}
        </div>

        <div style={{ ...card, flex: '1 1 280px' }}>
          <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
            TOP SKILLS
          </div>
          {topSkills.length === 0 ? (
            <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>none</div>
          ) : (
            topSkills.map((s, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: MONO,
                  fontSize: 11,
                  color: '#cbd5e1',
                  padding: '3px 0',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.title}
                </span>
                <span style={{ color: BRONZE, marginLeft: 8 }}>{s.usage_count}×</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <Btn primary onClick={runConsolidation} disabled={running}>
          {running ? 'Running…' : 'Run consolidation now'}
        </Btn>
      </div>

      {report && (
        <div style={{ ...card, borderColor: 'rgba(34,197,94,0.3)' }}>
          <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
            LAST CONSOLIDATION REPORT
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Chip label="nodes +" value={report.nodes_created ?? 0} color={CONF_COLORS.high} />
            <Chip label="edges +" value={report.edges_created ?? 0} color={CONF_COLORS.high} />
            <Chip label="edges reinforced" value={report.edges_reinforced ?? 0} />
            <Chip label="promoted" value={report.memories_promoted ?? 0} color="#f59e0b" />
            <Chip label="contradictions" value={report.contradictions_found ?? 0} color="#ef4444" />
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 2 — EXPLORER
// ═══════════════════════════════════════════════════════════════════════
const NODE_TYPES = ['', 'file', 'skill', 'model', 'pattern', 'failure', 'concept', 'run']

function ExplorerTab({ projectId }) {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [nodeType, setNodeType] = useState('')
  const [selected, setSelected] = useState(null)
  const [neighborhood, setNeighborhood] = useState(null)
  const [nbLoading, setNbLoading] = useState(false)
  const [nbError, setNbError] = useState(null)

  const { data, loading, error, reload } = useAsync(
    () => api.forge.cognitive.getMemoryGraphNodes(projectId, { node_type: nodeType || undefined, search: query || undefined }),
    [projectId, nodeType, query]
  )

  const openNode = async (node) => {
    setSelected(node)
    setNeighborhood(null)
    setNbError(null)
    setNbLoading(true)
    try {
      const res = await api.forge.cognitive.getMemoryGraphNeighborhood(projectId, node.node_id, 1)
      if (res && res.ok === false) throw new Error(res.error || 'Failed to load neighborhood')
      setNeighborhood(res)
    } catch (e) {
      setNbError(e?.message || String(e))
    } finally {
      setNbLoading(false)
    }
  }

  const nodes = data?.nodes || []
  const nbNodes = neighborhood?.nodes || []
  const nbEdges = neighborhood?.edges || []
  const nodeById = Object.fromEntries(nbNodes.map((n) => [n.node_id, n]))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && setQuery(search)}
          placeholder="Search nodes…"
          style={{
            flex: '1 1 200px',
            fontFamily: MONO,
            fontSize: 12,
            padding: '6px 10px',
            borderRadius: 7,
            border: '1px solid rgba(255,255,255,0.14)',
            background: 'rgba(255,255,255,0.03)',
            color: '#e2e8f0',
          }}
        />
        <select
          value={nodeType}
          onChange={(e) => setNodeType(e.target.value)}
          style={{
            fontFamily: MONO,
            fontSize: 12,
            padding: '6px 10px',
            borderRadius: 7,
            border: '1px solid rgba(255,255,255,0.14)',
            background: 'rgba(255,255,255,0.03)',
            color: '#e2e8f0',
          }}
        >
          {NODE_TYPES.map((t) => (
            <option key={t} value={t} style={{ background: '#1a1a1a' }}>
              {t || 'all types'}
            </option>
          ))}
        </select>
        <Btn small onClick={() => setQuery(search)}>
          Search
        </Btn>
        <Btn small onClick={reload} disabled={loading}>
          {loading ? '…' : 'Refresh'}
        </Btn>
      </div>

      {loading && <Loading label="Loading nodes…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!loading && !error && nodes.length === 0 && (
        <EmptyState title="No nodes" body="No memory nodes match the current filter." />
      )}

      {!loading && !error && nodes.length > 0 && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 320px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {nodes.map((n) => {
              const on = selected?.node_id === n.node_id
              return (
                <button
                  key={n.node_id}
                  onClick={() => openNode(n)}
                  style={{
                    textAlign: 'left',
                    cursor: 'pointer',
                    ...card,
                    padding: 10,
                    borderColor: on ? BRONZE : 'rgba(255,255,255,0.08)',
                    background: on ? 'rgba(207,138,58,0.08)' : 'rgba(255,255,255,0.02)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
                      {n.title}
                    </span>
                    <span
                      style={{
                        fontFamily: MONO,
                        fontSize: 10,
                        color: confColor(n.confidence),
                      }}
                    >
                      {n.confidence != null ? n.confidence.toFixed?.(2) ?? n.confidence : '—'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: BRONZE }}>{n.node_type}</span>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>
                      used {n.usage_count ?? 0}×
                    </span>
                  </div>
                  {n.summary && (
                    <div
                      style={{
                        fontFamily: MONO,
                        fontSize: 10,
                        color: '#94a3b8',
                        marginTop: 4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {n.summary}
                    </div>
                  )}
                </button>
              )
            })}
          </div>

          <div style={{ flex: '1 1 320px' }}>
            {!selected && (
              <div style={{ ...card, fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>
                Select a node to view its neighborhood.
              </div>
            )}
            {selected && (
              <div style={card}>
                <div style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
                  {selected.title}
                </div>
                <div style={{ fontFamily: MONO, fontSize: 10, color: BRONZE, marginBottom: 10 }}>
                  {selected.node_type} · conf {selected.confidence ?? '—'} · used{' '}
                  {selected.usage_count ?? 0}×
                </div>
                {nbLoading && <Loading label="Loading neighborhood…" />}
                {nbError && <ErrorBox message={nbError} onRetry={() => openNode(selected)} />}
                {!nbLoading && !nbError && (
                  <>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 6 }}>
                      LINKED NODES ({nbEdges.length})
                    </div>
                    {nbEdges.length === 0 ? (
                      <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>
                        No links.
                      </div>
                    ) : (
                      nbEdges.map((e) => {
                        const other =
                          nodeById[e.to_node_id === selected.node_id ? e.from_node_id : e.to_node_id]
                        return (
                          <div
                            key={e.edge_id}
                            style={{
                              borderTop: '1px solid rgba(255,255,255,0.06)',
                              padding: '6px 0',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                              <span style={{ fontFamily: MONO, fontSize: 11, color: '#e2e8f0' }}>
                                {other?.title || e.to_node_id}
                              </span>
                              <span style={{ fontFamily: MONO, fontSize: 10, color: BRONZE }}>
                                w {e.weight}
                              </span>
                            </div>
                            <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                              <span style={{ fontFamily: MONO, fontSize: 10, color: '#60a5fa' }}>
                                {e.edge_type}
                              </span>
                              {other && (
                                <span
                                  style={{
                                    fontFamily: MONO,
                                    fontSize: 10,
                                    color: confColor(other.confidence),
                                  }}
                                >
                                  conf {other.confidence ?? '—'}
                                </span>
                              )}
                              {other && (
                                <span style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>
                                  used {other.usage_count ?? 0}×
                                </span>
                              )}
                            </div>
                            {e.evidence && (
                              <div
                                style={{
                                  fontFamily: MONO,
                                  fontSize: 10,
                                  color: '#94a3b8',
                                  marginTop: 3,
                                }}
                              >
                                {e.evidence}
                              </div>
                            )}
                          </div>
                        )
                      })
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 3 — CONTEXT PACKETS
// ═══════════════════════════════════════════════════════════════════════
function ContextPacketsTab({ projectId }) {
  const { data, loading, error, reload } = useAsync(
    () => api.forge.cognitive.getProjectContextPackets(projectId),
    [projectId]
  )
  const packets = data?.packets || []

  return (
    <div>
      <PaneHeader title="Context Packets" onRefresh={reload} busy={loading} />
      {loading && <Loading label="Loading packets…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!loading && !error && packets.length === 0 && (
        <EmptyState title="No context packets" body="No context packets have been assembled yet." />
      )}
      {!loading && !error && packets.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {packets.map((p) => (
            <div key={p.packet_id} style={card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
                  {p.stage || 'stage'} · run {p.run_id}
                </span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>
                  {fmtTime(p.created_at)}
                </span>
              </div>
              {p.goal && (
                <div style={{ fontFamily: MONO, fontSize: 11, color: '#94a3b8', margin: '4px 0 8px' }}>
                  {p.goal}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Chip label="memories" value={(p.selected_nodes || []).length} />
                <Chip label="skills" value={(p.selected_skills || []).length} />
                <Chip label="models" value={(p.selected_models || []).length} />
                <Chip label="files" value={(p.included_files || []).length} />
              </div>
              {Array.isArray(p.excluded_reason) && p.excluded_reason.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794', marginBottom: 4 }}>
                    EXCLUDED
                  </div>
                  {p.excluded_reason.map((r, i) => (
                    <div
                      key={i}
                      style={{ fontFamily: MONO, fontSize: 10, color: '#f59e0b', padding: '1px 0' }}
                    >
                      {typeof r === 'string' ? r : `${r.item || r.title || ''} — ${r.reason || ''}`}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 4 — ADVISORY
// ═══════════════════════════════════════════════════════════════════════
function AdvisoryTab({ projectId }) {
  const metricsAsync = useAsync(() => api.forge.cognitive.getAdvisoryMetrics(projectId), [projectId])
  const eventsAsync = useAsync(() => api.forge.cognitive.getAdvisoryEvents(projectId), [projectId])

  const m = metricsAsync.data?.metrics
  const events = eventsAsync.data?.events || []

  const reloadAll = () => {
    metricsAsync.reload()
    eventsAsync.reload()
  }

  return (
    <div>
      <PaneHeader
        title="Advisory"
        onRefresh={reloadAll}
        busy={metricsAsync.loading || eventsAsync.loading}
      />

      {metricsAsync.error && <ErrorBox message={metricsAsync.error} onRetry={metricsAsync.reload} />}
      {m && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Chip label="total" value={m.total ?? 0} />
            <Chip label="agreement" value={pct(m.agreement_rate)} color={CONF_COLORS.high} />
            <Chip label="advisor used" value={pct(m.advisor_used_rate)} color="#60a5fa" />
            <Chip label="advisor ignored" value={pct(m.advisor_ignored_rate)} color="#6b7280" />
            <Chip
              label="helpful disagree"
              value={pct(m.helpful_disagreement_rate)}
              color="#f59e0b"
            />
            <Chip
              label="unsafe disagree"
              value={pct(m.unsafe_disagreement_rate)}
              color="#ef4444"
            />
          </div>
          {m.by_type && Object.keys(m.by_type).length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794', marginBottom: 6 }}>
                BY TYPE
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {Object.entries(m.by_type).map(([k, v]) => (
                  <Chip key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v) : v} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {eventsAsync.loading && <Loading label="Loading advisory events…" />}
      {eventsAsync.error && <ErrorBox message={eventsAsync.error} onRetry={eventsAsync.reload} />}
      {!eventsAsync.loading && !eventsAsync.error && events.length === 0 && (
        <EmptyState title="No advisory events" body="The advisor has not produced any events yet." />
      )}
      {!eventsAsync.loading && !eventsAsync.error && events.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {events.map((ev) => (
            <div key={ev.advisory_id} style={card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: agreeColor(ev.agreement),
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
                    {ev.advisory_type}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: BRONZE }}>{ev.stage}</span>
                </span>
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: agreeColor(ev.agreement) }}>
                    {ev.agreement}
                  </span>
                  {ev.confidence != null && (
                    <span style={{ fontFamily: MONO, fontSize: 10, color: confColor(ev.confidence) }}>
                      {ev.confidence}
                    </span>
                  )}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 200px' }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>ADVICE</div>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: '#94a3b8' }}>
                    {ev.advice || '—'}
                  </div>
                </div>
                <div style={{ flex: '1 1 200px' }}>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>RULE RESULT</div>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: '#94a3b8' }}>
                    {ev.rule_result || '—'}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <Chip
                  label="used by agent"
                  value={ev.used_by_agent ? 'yes' : 'no'}
                  color={ev.used_by_agent ? CONF_COLORS.high : '#6b7280'}
                />
                <Chip
                  label="overridden by rule"
                  value={ev.overridden_by_rule ? 'yes' : 'no'}
                  color={ev.overridden_by_rule ? '#f59e0b' : '#6b7280'}
                />
                <Chip label="at" value={fmtTime(ev.created_at)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 5 — COGNITIVE STREAM
// ═══════════════════════════════════════════════════════════════════════
function CognitiveStreamTab({ projectId }) {
  const { data, loading, error, reload } = useAsync(
    () => api.forge.cognitive.getCognitiveEvents(projectId),
    [projectId]
  )
  const events = [...(data?.events || [])].sort((a, b) => {
    const ta = new Date(a.created_at).getTime() || 0
    const tb = new Date(b.created_at).getTime() || 0
    return tb - ta
  })

  return (
    <div>
      <PaneHeader title="Cognitive Stream" onRefresh={reload} busy={loading} />
      {loading && <Loading label="Loading events…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!loading && !error && events.length === 0 && (
        <EmptyState title="No cognitive events" body="No cognitive activity recorded yet." />
      )}
      {!loading && !error && events.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {events.map((ev) => (
            <div
              key={ev.event_id}
              style={{
                ...card,
                padding: 10,
                borderLeft: `3px solid ${eventColor(ev.event_type)}`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: eventColor(ev.event_type) }}>
                    {ev.event_type}
                  </span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
                    {ev.title}
                  </span>
                </span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>
                  {fmtTime(ev.created_at)}
                </span>
              </div>
              {ev.details && (
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 10,
                    color: '#94a3b8',
                    marginTop: 4,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {typeof ev.details === 'string' ? ev.details : JSON.stringify(ev.details)}
                </div>
              )}
              {ev.run_id && (
                <div style={{ fontFamily: MONO, fontSize: 9, color: '#6b7280', marginTop: 3 }}>
                  run {ev.run_id}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// TAB 6 — CONSOLIDATION
// ═══════════════════════════════════════════════════════════════════════
function ConsolidationTab({ projectId, summary, reloadSummary }) {
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState(null)

  // consolidation history derived from cognitive events of type "consolidation"
  const { data, loading, error, reload } = useAsync(
    () => api.forge.cognitive.getCognitiveEvents(projectId),
    [projectId]
  )
  const history = (data?.events || [])
    .filter((e) => e.event_type === 'consolidation')
    .sort((a, b) => (new Date(b.created_at).getTime() || 0) - (new Date(a.created_at).getTime() || 0))

  const runConsolidation = async () => {
    setRunning(true)
    try {
      const res = await api.forge.cognitive.consolidateMemoryGraph(projectId, {})
      if (res && res.ok === false) throw new Error(res.error || 'Consolidation failed')
      setReport(res?.consolidation || null)
      toastSuccess('Consolidation complete')
      reloadSummary && reloadSummary()
      reload()
    } catch (e) {
      toastError(e?.message || 'Consolidation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <PaneHeader
        title="Consolidation"
        onRefresh={reload}
        busy={loading}
        extra={
          <Btn primary small onClick={runConsolidation} disabled={running}>
            {running ? 'Running…' : 'Run consolidation now'}
          </Btn>
        }
      />

      {summary && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <Chip label="contradicted" value={summary.contradicted ?? 0} color="#ef4444" />
          <Chip label="high-conf" value={summary.high_confidence ?? 0} color={CONF_COLORS.high} />
          <Chip label="nodes" value={summary.nodes ?? 0} />
          <Chip label="edges" value={summary.edges ?? 0} />
        </div>
      )}

      {report && (
        <div style={{ ...card, borderColor: 'rgba(34,197,94,0.3)', marginBottom: 12 }}>
          <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
            LAST REPORT
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Chip label="contradictions" value={report.contradictions_found ?? 0} color="#ef4444" />
            <Chip label="edges reinforced" value={report.edges_reinforced ?? 0} color={CONF_COLORS.high} />
            <Chip label="nodes +" value={report.nodes_created ?? 0} />
            <Chip label="edges +" value={report.edges_created ?? 0} />
            <Chip label="promoted" value={report.memories_promoted ?? 0} color="#f59e0b" />
          </div>
        </div>
      )}

      <div style={{ fontFamily: MONO, fontSize: 11, color: '#7b8794', marginBottom: 8 }}>
        CONSOLIDATION HISTORY
      </div>
      {loading && <Loading label="Loading history…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!loading && !error && history.length === 0 && (
        <EmptyState title="No consolidation runs" body="Run consolidation to populate history." />
      )}
      {!loading && !error && history.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {history.map((ev) => (
            <div
              key={ev.event_id}
              style={{ ...card, padding: 10, borderLeft: `3px solid ${CONF_COLORS.high}` }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontFamily: MONO, fontSize: 12, color: '#e2e8f0' }}>{ev.title}</span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: '#7b8794' }}>
                  {fmtTime(ev.created_at)}
                </span>
              </div>
              {ev.details && (
                <div style={{ fontFamily: MONO, fontSize: 10, color: '#94a3b8', marginTop: 4 }}>
                  {typeof ev.details === 'string' ? ev.details : JSON.stringify(ev.details)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════
const TABS = [
  { key: 'graph', label: 'Graph' },
  { key: 'explorer', label: 'Explorer' },
  { key: 'packets', label: 'Context Packets' },
  { key: 'advisory', label: 'Advisory' },
  { key: 'stream', label: 'Cognitive Stream' },
  { key: 'consolidation', label: 'Consolidation' },
]

export function CognitiveCorePanel({ project }) {
  const projectId = project?.id || project?.project_id
  const [tab, setTab] = useState('graph')

  const summaryAsync = useAsync(
    () => api.forge.cognitive.getMemoryGraphSummary(projectId),
    [projectId],
    !!projectId
  )
  const advisoryMetricsAsync = useAsync(
    () => api.forge.cognitive.getAdvisoryMetrics(projectId),
    [projectId],
    !!projectId
  )
  const cogEventsAsync = useAsync(
    () => api.forge.cognitive.getCognitiveEvents(projectId),
    [projectId],
    !!projectId
  )

  if (!project) {
    return <div className="af-understand__hint">Select a project to view the cognitive core.</div>
  }

  const summary = summaryAsync.data?.summary
  const advAgree = advisoryMetricsAsync.data?.metrics?.agreement_rate
  const cogCount = (cogEventsAsync.data?.events || []).length

  const reloadSummary = () => {
    summaryAsync.reload()
    advisoryMetricsAsync.reload()
    cogEventsAsync.reload()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* SUMMARY CARD */}
      <div style={{ ...card, padding: 16 }}>
        <PaneHeader
          title="Cognitive Core"
          onRefresh={reloadSummary}
          busy={summaryAsync.loading}
        />
        {summaryAsync.loading && !summary && <Loading label="Loading cognitive summary…" />}
        {summaryAsync.error && <ErrorBox message={summaryAsync.error} onRetry={summaryAsync.reload} />}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Chip label="nodes" value={summary?.nodes ?? 0} />
          <Chip label="edges" value={summary?.edges ?? 0} />
          <Chip label="high-conf" value={summary?.high_confidence ?? 0} color={CONF_COLORS.high} />
          <Chip label="contradicted" value={summary?.contradicted ?? 0} color="#ef4444" />
          <Chip label="advisory agreement" value={pct(advAgree)} color={CONF_COLORS.high} />
          <Chip label="cognitive events" value={cogCount} color="#60a5fa" />
        </div>
      </div>

      {/* TAB BAR */}
      <TabBar tabs={TABS} active={tab} onChange={setTab} />

      {/* TAB CONTENT */}
      <div>
        {tab === 'graph' && (
          <GraphTab projectId={projectId} summary={summary} reloadSummary={reloadSummary} />
        )}
        {tab === 'explorer' && <ExplorerTab projectId={projectId} />}
        {tab === 'packets' && <ContextPacketsTab projectId={projectId} />}
        {tab === 'advisory' && <AdvisoryTab projectId={projectId} />}
        {tab === 'stream' && <CognitiveStreamTab projectId={projectId} />}
        {tab === 'consolidation' && (
          <ConsolidationTab projectId={projectId} summary={summary} reloadSummary={reloadSummary} />
        )}
      </div>
    </div>
  )
}

export default CognitiveCorePanel
