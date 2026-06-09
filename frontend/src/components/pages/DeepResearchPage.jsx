import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import './DeepResearchPage.css'

const authHeaders = () => {
  const t = sessionStorage.getItem('ai_jwt') || ''
  return { 'content-type': 'application/json', ...(t ? { authorization: `Bearer ${t}` } : {}) }
}

const API = '/api/research/deep'

const DEPTHS = [
  { id: 'shallow', label: 'SHALLOW', sub: '3 questions · ~15 sources · 2-4 min', color: '#60A5FA' },
  { id: 'normal',  label: 'NORMAL',  sub: '5 questions · ~25 sources · 5-8 min', color: '#A78BFA' },
  { id: 'deep',    label: 'DEEP',    sub: '6 questions · up to 40 sources · 10-20 min', color: '#00FFB4' },
]

const PRESETS = [
  'AI agent frameworks and orchestration patterns 2025',
  'Dropshipping niche research — high margin, low competition',
  'SaaS pricing models and conversion optimization strategies',
  'Competitor intelligence — what are the top 5 players doing?',
  'LLM fine-tuning vs RAG — when to use which approach',
  'E-commerce SEO strategies that work in 2025',
]

const PHASE_LABELS = {
  decompose: 'Breaking into sub-questions',
  discover: 'Searching the web',
  fetch: 'Reading sources',
  synthesize: 'Synthesizing findings',
  gaps: 'Detecting knowledge gaps',
  fetch_gaps: 'Reading gap sources',
  report: 'Writing report',
}

// ── Utility ────────────────────────────────────────────────────────────────

function fmtDuration(s) {
  if (!s) return ''
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

function fmtDate(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString()
}

// ── Sub-components ────────────────────────────────────────────────────────

function DepthPicker({ value, onChange }) {
  return (
    <div className="drp-depth-picker">
      {DEPTHS.map(d => (
        <button
          key={d.id}
          className={`drp-depth-btn ${value === d.id ? 'drp-depth-btn--active' : ''}`}
          style={{ '--depth-color': d.color }}
          onClick={() => onChange(d.id)}
        >
          <span className="drp-depth-label">{d.label}</span>
          <span className="drp-depth-sub">{d.sub}</span>
        </button>
      ))}
    </div>
  )
}

function ProgressLog({ events }) {
  const bottomRef = useRef(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [events.length])

  return (
    <div className="drp-progress-log">
      {events.map((e, i) => {
        const { event, data } = e
        if (event === 'phase') return (
          <div key={i} className="drp-log-phase">
            <span className="drp-log-phase-icon">▶</span>
            {PHASE_LABELS[data.phase] || data.msg || data.phase}
          </div>
        )
        if (event === 'sub_questions') return (
          <div key={i} className="drp-log-questions">
            {(data.questions || []).map((q, qi) => (
              <div key={qi} className="drp-log-question"><span className="drp-log-qnum">{qi + 1}</span>{q}</div>
            ))}
          </div>
        )
        if (event === 'sources_found') return (
          <div key={i} className="drp-log-info">Found <b>{data.count}</b> candidate sources</div>
        )
        if (event === 'source_read') return (
          <div key={i} className="drp-log-source">
            <span className="drp-log-source-dot" />
            <span className="drp-log-source-title">{data.title || data.url}</span>
            <span className="drp-log-source-chars">{(data.chars / 1000).toFixed(1)}k chars</span>
          </div>
        )
        if (event === 'section_done') return (
          <div key={i} className="drp-log-section">
            <span className="drp-log-section-icon">✓</span>
            Section synthesized: <em>{data.question}</em>
          </div>
        )
        if (event === 'gaps_found') return (
          <div key={i} className="drp-log-gaps">
            <div className="drp-log-gaps-title">Knowledge gaps detected:</div>
            {(data.gaps || []).map((g, gi) => <div key={gi} className="drp-log-gap">→ {g}</div>)}
          </div>
        )
        if (event === 'done') return (
          <div key={i} className="drp-log-done">
            Research complete — {data.sources} sources in {fmtDuration(data.duration_s)}
          </div>
        )
        if (event === 'failed') return (
          <div key={i} className="drp-log-error">Research failed: {data.error}</div>
        )
        return null
      })}
      <div ref={bottomRef} />
    </div>
  )
}

function ReportViewer({ report, onCommit, committing, committed }) {
  const [tab, setTab] = useState('summary')

  return (
    <div className="drp-report">
      <div className="drp-report-header">
        <div className="drp-report-title">{report.topic}</div>
        <div className="drp-report-meta">
          <span>{report.sources_fetched} sources</span>
          <span>{fmtDuration(report.duration_s)}</span>
          <span>{fmtDate(report.created_at)}</span>
          {report.status === 'done' && !committed && (
            <button
              className={`drp-commit-btn ${committing ? 'drp-commit-btn--loading' : ''}`}
              onClick={onCommit}
              disabled={committing}
            >
              {committing ? 'COMMITTING…' : '⬆ COMMIT TO MEMORY'}
            </button>
          )}
          {committed && <span className="drp-committed-badge">✓ IN MEMORY</span>}
        </div>
      </div>

      <div className="drp-report-tabs">
        {['summary', 'sections', 'raw', 'sources'].map(t => (
          <button
            key={t}
            className={`drp-tab-btn ${tab === t ? 'drp-tab-btn--active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="drp-report-body">
        {tab === 'summary' && (
          <div className="drp-tab-summary">
            {report.key_findings?.length > 0 && (
              <div className="drp-findings">
                <div className="drp-findings-title">KEY FINDINGS</div>
                {report.key_findings.map((kf, i) => (
                  <div key={i} className="drp-finding"><span className="drp-finding-num">{i + 1}</span>{kf}</div>
                ))}
              </div>
            )}
            <div className="drp-exec-summary">
              <div className="drp-exec-title">EXECUTIVE SUMMARY</div>
              <div className="drp-exec-body">{report.executive_summary || 'Summary not available.'}</div>
            </div>
            {report.gaps_identified?.length > 0 && (
              <div className="drp-gaps-section">
                <div className="drp-gaps-title">KNOWLEDGE GAPS</div>
                {report.gaps_identified.map((g, i) => (
                  <div key={i} className="drp-gap-item">→ {g}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'sections' && (
          <div className="drp-tab-sections">
            {(report.sections || []).map((s, i) => (
              <div key={i} className="drp-section">
                <div className="drp-section-title">{s.title}</div>
                <div className="drp-section-body">{s.content}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'raw' && (
          <div className="drp-tab-raw">
            <pre className="drp-raw-md">{report.report_md || 'No markdown generated.'}</pre>
          </div>
        )}

        {tab === 'sources' && (
          <div className="drp-tab-sources">
            {(report.citations || []).map((c, i) => (
              <div key={i} className="drp-citation">
                <span className="drp-citation-num">{i + 1}</span>
                <div className="drp-citation-info">
                  <a href={c.url} target="_blank" rel="noopener noreferrer" className="drp-citation-link">
                    {c.title || c.url}
                  </a>
                  <span className="drp-citation-url">{c.url}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ReportCard({ report, onSelect, onDelete }) {
  const statusColor = { done: '#00FFB4', failed: '#F87171', in_progress: '#E5C76B' }[report.status] || '#6B7280'
  return (
    <div className="drp-card" onClick={() => onSelect(report.id)}>
      <div className="drp-card-status" style={{ background: statusColor }} />
      <div className="drp-card-body">
        <div className="drp-card-topic">{report.topic}</div>
        <div className="drp-card-meta">
          <span>{fmtDate(report.created_at)}</span>
          {report.sources_fetched > 0 && <span>{report.sources_fetched} sources</span>}
          {report.committed_to_memory && <span className="drp-card-badge">IN MEMORY</span>}
        </div>
      </div>
      <button className="drp-card-del" onClick={e => { e.stopPropagation(); onDelete(report.id) }}>✕</button>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function DeepResearchPage() {
  const wsRef = useRef(null)
  const [topic, setTopic] = useState('')
  const [depth, setDepth] = useState('deep')
  const [phase, setPhase] = useState('idle') // idle | running | viewing
  const [activeId, setActiveId] = useState(null)
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const [reports, setReports] = useState([])
  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(false)
  const [loadingReport, setLoadingReport] = useState(false)

  // Load report list on mount
  useEffect(() => {
    fetch(API, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => setReports(d.reports || []))
      .catch(() => {})
  }, [])

  // Subscribe to WS for live progress
  useEffect(() => {
    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${wsProtocol}//${location.host}/ws`)
    wsRef.current = ws
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'research:progress' && msg.payload?.report_id === activeId) {
          const evt = { event: msg.payload.event, data: msg.payload.data || {}, ts: msg.payload.ts }
          setEvents(prev => [...prev, evt])
          if (msg.payload.event === 'done') {
            setPhase('done')
            loadFullReport(msg.payload.report_id)
            refreshList()
          }
          if (msg.payload.event === 'failed') {
            setPhase('failed')
            refreshList()
          }
        }
      } catch {}
    }
    return () => ws.close()
  }, [activeId])

  const refreshList = useCallback(() => {
    fetch(API, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => setReports(d.reports || []))
      .catch(() => {})
  }, [])

  const loadFullReport = useCallback((id) => {
    setLoadingReport(true)
    fetch(`${API}/${id}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        setReport(d.report || null)
        setCommitted(d.report?.committed_to_memory || false)
        setLoadingReport(false)
        setPhase('viewing')
      })
      .catch(() => setLoadingReport(false))
  }, [])

  const handleStart = useCallback(async () => {
    if (!topic.trim()) return
    setEvents([])
    setReport(null)
    setCommitted(false)
    setPhase('running')
    try {
      const r = await fetch(`${API}/start`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ topic: topic.trim(), depth }),
      })
      const d = await r.json()
      if (d.ok) {
        setActiveId(d.report_id)
        setEvents([{ event: 'phase', data: { phase: 'decompose' }, ts: Date.now() / 1000 }])
      } else {
        setPhase('idle')
      }
    } catch {
      setPhase('idle')
    }
  }, [topic, depth])

  const handleSelectReport = useCallback((id) => {
    setActiveId(id)
    setEvents([])
    loadFullReport(id)
  }, [loadFullReport])

  const handleDelete = useCallback(async (id) => {
    await fetch(`${API}/${id}`, { method: 'DELETE', headers: authHeaders() })
    setReports(prev => prev.filter(r => r.id !== id))
    if (activeId === id) { setReport(null); setPhase('idle'); setActiveId(null) }
  }, [activeId])

  const handleCommit = useCallback(async () => {
    if (!activeId) return
    setCommitting(true)
    try {
      const r = await fetch(`${API}/${activeId}/commit`, { method: 'POST', headers: authHeaders() })
      const d = await r.json()
      if (d.ok) {
        setCommitted(true)
        refreshList()
      }
    } catch {}
    setCommitting(false)
  }, [activeId, refreshList])

  const handleReset = () => {
    setPhase('idle')
    setTopic('')
    setEvents([])
    setReport(null)
    setActiveId(null)
    setCommitted(false)
  }

  return (
    <div className="drp-page">
      {/* Left panel — list + launcher */}
      <div className="drp-sidebar">
        <div className="drp-sidebar-header">
          <div className="drp-sidebar-title">DEEP RESEARCH</div>
          <div className="drp-sidebar-sub">Multi-hop · Up to 40 sources · Full report</div>
        </div>

        {/* Launch form */}
        <div className="drp-launch">
          <textarea
            className="drp-topic-input"
            placeholder="Research topic or question…"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            rows={3}
            disabled={phase === 'running'}
          />
          <div className="drp-presets">
            {PRESETS.map(p => (
              <button key={p} className="drp-preset-btn" onClick={() => setTopic(p)}>{p}</button>
            ))}
          </div>
          <DepthPicker value={depth} onChange={setDepth} />
          <button
            className={`drp-start-btn ${phase === 'running' ? 'drp-start-btn--running' : ''}`}
            onClick={phase === 'running' ? undefined : handleStart}
            disabled={phase === 'running' || !topic.trim()}
          >
            {phase === 'running' ? '⟳ RESEARCHING…' : '▶ START DEEP RESEARCH'}
          </button>
          {phase !== 'idle' && (
            <button className="drp-reset-btn" onClick={handleReset}>NEW RESEARCH ↺</button>
          )}
        </div>

        {/* Report list */}
        <div className="drp-report-list">
          <div className="drp-list-label">PREVIOUS REPORTS</div>
          {reports.length === 0 && <div className="drp-list-empty">No reports yet</div>}
          {reports.map(r => (
            <ReportCard
              key={r.id}
              report={r}
              onSelect={handleSelectReport}
              onDelete={handleDelete}
            />
          ))}
        </div>
      </div>

      {/* Right panel — progress or report */}
      <div className="drp-main">
        {phase === 'idle' && (
          <div className="drp-empty-state">
            <div className="drp-empty-icon">⬡</div>
            <div className="drp-empty-title">DEEP RESEARCH ENGINE</div>
            <div className="drp-empty-body">
              Enter a topic and start a deep research run. The engine will break the topic into
              sub-questions, search and read up to 40 sources, synthesize findings, detect gaps,
              and produce a structured report with citations. Commit the report to memory so all
              agents can use it when executing tasks.
            </div>
          </div>
        )}

        {phase === 'running' && (
          <div className="drp-running-panel">
            <div className="drp-running-header">
              <div className="drp-running-title">{topic}</div>
              <div className="drp-running-badge">RESEARCHING</div>
            </div>
            <ProgressLog events={events} />
          </div>
        )}

        {(phase === 'done' || phase === 'failed') && events.length > 0 && !report && !loadingReport && (
          <div className="drp-running-panel">
            <ProgressLog events={events} />
          </div>
        )}

        {loadingReport && (
          <div className="drp-loading">Loading report…</div>
        )}

        {report && (
          <ReportViewer
            report={report}
            onCommit={handleCommit}
            committing={committing}
            committed={committed}
          />
        )}
      </div>
    </div>
  )
}
