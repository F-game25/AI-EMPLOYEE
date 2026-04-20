import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const STATUS_COLORS = {
  ok: 'var(--success)',
  error: 'var(--error)',
  fallback: 'var(--warning)',
  pending: 'var(--text-muted)',
}

const FLAG_LABELS = {
  missing_context: { label: 'Missing Context', color: 'var(--warning)' },
  empty_prompt: { label: 'Empty Prompt', color: 'var(--error)' },
  empty_output: { label: 'Empty Output', color: 'var(--error)' },
  generic_output: { label: 'Generic Output', color: 'var(--warning)' },
  error: { label: 'Error', color: 'var(--error)' },
}

function FlagBadge({ flag }) {
  const meta = FLAG_LABELS[flag] || { label: flag, color: 'var(--text-muted)' }
  return (
    <span style={{
      fontSize: '10px',
      padding: '2px 6px',
      borderRadius: '4px',
      background: `${meta.color}20`,
      color: meta.color,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
    }}>
      {meta.label}
    </span>
  )
}

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || 'var(--text-muted)'
  return (
    <span style={{
      fontSize: '11px',
      padding: '2px 8px',
      borderRadius: '4px',
      background: `${color}18`,
      color,
      fontWeight: 600,
      textTransform: 'uppercase',
    }}>
      {status}
    </span>
  )
}

function TraceListItem({ trace, isSelected, onClick }) {
  const hasFlags = trace.flags && trace.flags.length > 0
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="ds-card-interactive"
      onClick={onClick}
      style={{
        padding: 'var(--space-3) var(--space-4)',
        cursor: 'pointer',
        borderLeft: isSelected ? '2px solid var(--gold)' : '2px solid transparent',
        background: isSelected ? 'var(--bg-card-hover)' : undefined,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: '6px' }}>
        <span style={{
          width: '7px',
          height: '7px',
          borderRadius: '50%',
          background: STATUS_COLORS[trace.execution_status] || 'var(--text-muted)',
          flexShrink: 0,
        }} />
        <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)' }}>
          {trace.id}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '11px', color: 'var(--text-muted)' }}>
          {trace.duration_ms != null ? `${trace.duration_ms}ms` : '—'}
        </span>
      </div>
      <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500, marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {trace.user_input || '(empty)'}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{trace.agent || 'unknown'}</span>
        <StatusBadge status={trace.execution_status || 'pending'} />
        {hasFlags && trace.flags.map(f => <FlagBadge key={f} flag={f} />)}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
        {new Date(trace.timestamp).toLocaleTimeString()}
      </div>
    </motion.div>
  )
}

function CodeBlock({ label, content, highlight }) {
  if (!content) return null
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <div style={{
        fontSize: '11px',
        fontWeight: 600,
        color: 'var(--text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        marginBottom: 'var(--space-2)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
      }}>
        {label}
        {highlight && <FlagBadge flag={highlight} />}
      </div>
      <pre style={{
        background: 'var(--bg-base)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)',
        fontSize: '12px',
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-mono, monospace)',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        maxHeight: '200px',
        overflowY: 'auto',
        lineHeight: 1.6,
      }}>
        {content}
      </pre>
    </div>
  )
}

function TraceDetailPanel({ trace }) {
  if (!trace) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-muted)',
        fontSize: '14px',
      }}>
        Select a trace to view details
      </div>
    )
  }

  const missingContext = trace.flags?.includes('missing_context')
  const emptyPrompt = trace.flags?.includes('empty_prompt')
  const genericOutput = trace.flags?.includes('generic_output')

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4)' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
          <StatusBadge status={trace.execution_status || 'pending'} />
          {trace.flags?.map(f => <FlagBadge key={f} flag={f} />)}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)' }}>
          {trace.id} · {trace.agent} · {trace.provider}{trace.model ? `/${trace.model}` : ''} · {trace.duration_ms != null ? `${trace.duration_ms}ms` : '—'}
        </div>
        {trace.error && (
          <div style={{ marginTop: 'var(--space-2)', fontSize: '12px', color: 'var(--error)', background: 'rgba(239,68,68,0.08)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-2) var(--space-3)' }}>
            ⚠ {trace.error}
          </div>
        )}
      </div>

      {/* Side-by-side: INPUT | PROMPT | OUTPUT */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: 'var(--space-3)',
        marginBottom: 'var(--space-4)',
      }}>
        {['Input', 'Prompt', 'Output'].map((col, i) => {
          const content = [trace.user_input, trace.constructed_prompt, trace.final_output][i]
          return (
            <div key={col} style={{
              background: 'var(--bg-base)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
            }}>
              <div style={{ fontSize: '10px', fontWeight: 700, color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 'var(--space-2)' }}>
                {col}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono, monospace)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '120px', overflowY: 'auto', lineHeight: 1.5 }}>
                {content || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>empty</span>}
              </div>
            </div>
          )
        })}
      </div>

      {/* Detail blocks */}
      <CodeBlock label="User Input" content={trace.user_input} />
      <CodeBlock label="Context Used" content={trace.context_used} highlight={missingContext ? 'missing_context' : undefined} />
      <CodeBlock label="Constructed Prompt" content={trace.constructed_prompt} highlight={emptyPrompt ? 'empty_prompt' : undefined} />
      <CodeBlock label="Model Raw Output" content={trace.model_raw_output} />
      <CodeBlock label="Final Output" content={trace.final_output} highlight={genericOutput ? 'generic_output' : undefined} />

      {/* Actions triggered */}
      {trace.actions_triggered && trace.actions_triggered.length > 0 && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-2)' }}>
            Actions Triggered
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {trace.actions_triggered.map((a, i) => (
              <span key={i} style={{ fontSize: '12px', padding: '2px 10px', borderRadius: '4px', background: 'rgba(212,175,55,0.12)', color: 'var(--gold)', fontFamily: 'var(--font-mono, monospace)' }}>
                {a}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function PromptInspectorPage() {
  const liveTraces = useAppStore(s => s.promptTraces)
  const inspectorEnabled = useAppStore(s => s.inspectorEnabled)
  const setInspectorEnabled = useAppStore(s => s.setInspectorEnabled)
  const setPromptTraces = useAppStore(s => s.setPromptTraces)

  const [selectedId, setSelectedId] = useState(null)
  const [fullTrace, setFullTrace] = useState(null)
  const [loadingFull, setLoadingFull] = useState(false)
  const [loadingList, setLoadingList] = useState(false)
  const [togglingInspector, setTogglingInspector] = useState(false)

  // Load initial list from API
  const loadTraces = useCallback(async () => {
    setLoadingList(true)
    try {
      const res = await fetch(`${BASE}/api/prompt-traces?limit=100`)
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data.traces)) {
          setPromptTraces(data.traces)
          if (data.inspector_status != null) {
            setInspectorEnabled(data.inspector_status.enabled)
          }
        }
      }
    } catch (_e) {
      // keep current state
    } finally {
      setLoadingList(false)
    }
  }, [setPromptTraces, setInspectorEnabled])

  useEffect(() => {
    loadTraces()
  }, [loadTraces])

  // Load full detail when selection changes
  useEffect(() => {
    if (!selectedId) { setFullTrace(null); return }
    setLoadingFull(true)
    fetch(`${BASE}/api/prompt-trace/${selectedId}`)
      .then(r => r.json())
      .then(data => { if (data.trace) setFullTrace(data.trace) })
      .catch(() => {})
      .finally(() => setLoadingFull(false))
  }, [selectedId])

  // When a live trace comes in and matches selection, refresh detail
  useEffect(() => {
    if (!selectedId) return
    const live = liveTraces.find(t => t.id === selectedId)
    if (live) {
      // Fetch full detail to get all fields
      fetch(`${BASE}/api/prompt-trace/${selectedId}`)
        .then(r => r.json())
        .then(data => { if (data.trace) setFullTrace(data.trace) })
        .catch(() => {})
    }
  }, [liveTraces, selectedId])

  const handleToggleInspector = async () => {
    setTogglingInspector(true)
    try {
      const next = !inspectorEnabled
      const res = await fetch(`${BASE}/api/prompt-inspector/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      })
      if (res.ok) {
        const data = await res.json()
        setInspectorEnabled(data.inspector_status?.enabled ?? next)
      }
    } catch (_e) {
      // best effort
    } finally {
      setTogglingInspector(false)
    }
  }

  const handleClear = async () => {
    try {
      await fetch(`${BASE}/api/prompt-traces`, { method: 'DELETE' })
      setPromptTraces([])
      setSelectedId(null)
      setFullTrace(null)
    } catch (_e) {}
  }

  const displayTrace = loadingFull ? null : (fullTrace || liveTraces.find(t => t.id === selectedId) || null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader title="Prompt Inspector" subtitle="Real-time AI pipeline observability">
        <button
          className="btn-secondary"
          onClick={loadTraces}
          disabled={loadingList}
          style={{ fontSize: '12px', padding: '6px 14px' }}
        >
          {loadingList ? 'Loading…' : '↻ Refresh'}
        </button>
        <button
          className="btn-secondary"
          onClick={handleClear}
          style={{ fontSize: '12px', padding: '6px 14px' }}
        >
          Clear
        </button>
        <button
          className={inspectorEnabled ? 'btn-primary' : 'btn-secondary'}
          onClick={handleToggleInspector}
          disabled={togglingInspector}
          style={{ fontSize: '12px', padding: '6px 14px' }}
        >
          {inspectorEnabled ? '◉ Enabled' : '○ Disabled'}
        </button>
      </PageHeader>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        {[
          { label: 'Total', value: liveTraces.length },
          { label: 'OK', value: liveTraces.filter(t => t.execution_status === 'ok').length, color: 'var(--success)' },
          { label: 'Errors', value: liveTraces.filter(t => t.execution_status === 'error').length, color: 'var(--error)' },
          { label: 'Flagged', value: liveTraces.filter(t => t.flags && t.flags.length > 0).length, color: 'var(--warning)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="ds-card" style={{ padding: 'var(--space-3) var(--space-4)', minWidth: '90px' }}>
            <div style={{ fontSize: '20px', fontWeight: 600, color: color || 'var(--text-primary)' }}>{value}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Main panel: list + detail */}
      <div style={{ flex: 1, display: 'flex', gap: 'var(--space-4)', minHeight: 0 }}>
        {/* Trace list */}
        <div style={{
          width: '340px',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
          overflow: 'hidden',
        }}>
          <div style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Live Stream
            </span>
            {liveTraces.length > 0 && (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{liveTraces.length} traces</span>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px', padding: 'var(--space-2)' }}>
            {liveTraces.length === 0 ? (
              <div style={{ padding: 'var(--space-5)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                {inspectorEnabled ? 'Waiting for requests…' : 'Inspector is disabled'}
              </div>
            ) : (
              <AnimatePresence initial={false}>
                {liveTraces.map(trace => (
                  <TraceListItem
                    key={trace.id}
                    trace={trace}
                    isSelected={trace.id === selectedId}
                    onClick={() => setSelectedId(trace.id === selectedId ? null : trace.id)}
                  />
                ))}
              </AnimatePresence>
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div style={{
          flex: 1,
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Trace Detail
            </span>
          </div>
          {loadingFull ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              Loading…
            </div>
          ) : (
            <TraceDetailPanel trace={displayTrace} />
          )}
        </div>
      </div>
    </div>
  )
}
