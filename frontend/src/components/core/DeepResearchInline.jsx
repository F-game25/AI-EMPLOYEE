import { useState, useEffect, useRef } from 'react'
import './DeepResearchInline.css'

// Inline deep-research visualization for the chat: shows live phases + the sites
// being visited + progress, then the final report summary — all in the chat,
// reporting back automatically when done. Subscribes to the same WS
// `research:progress` events the backend emits, filtered by this run's report_id.

const authHeaders = () => {
  const t = sessionStorage.getItem('ai_jwt') || ''
  return { 'content-type': 'application/json', ...(t ? { authorization: `Bearer ${t}` } : {}) }
}

const API = '/api/research/deep'

const PHASE_LABELS = {
  decompose: 'Breaking topic into sub-questions',
  discover: 'Searching the web',
  fetch: 'Reading sources',
  synthesize: 'Synthesizing findings',
  gaps: 'Detecting knowledge gaps',
  fetch_gaps: 'Reading gap sources',
  report: 'Writing the report',
}

const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }
// Research source URLs are UNTRUSTED external data (a malicious search result could be
// a javascript:/data: URL → XSS / untrusted redirect). Only allow http(s) into an href.
const safeHref = (url) => {
  try {
    const u = new URL(url, location.origin)
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : undefined
  } catch { return undefined }
}
const fmtDuration = (s) => (!s ? '' : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

export default function DeepResearchInline({ reportId, topic, depth = 'deep' }) {
  const [status, setStatus] = useState('running') // running | done | partial | failed
  const [phase, setPhase] = useState('decompose')
  const [sources, setSources] = useState([])      // { url, host, read, chars }
  const [counts, setCounts] = useState({ found: 0, read: 0 })
  const [report, setReport] = useState(null)
  const [expanded, setExpanded] = useState(true)
  const [error, setError] = useState(null)
  const [reiterating, setReiterating] = useState(null) // { attempt, max, reason }
  const wsRef = useRef(null)

  useEffect(() => {
    if (!reportId) return
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    let closed = false
    const ws = new WebSocket(`${proto}//${location.host}/ws`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      let msg
      try { msg = JSON.parse(e.data) } catch { return }
      if (msg.type !== 'research:progress' || msg.payload?.report_id !== reportId) return
      const { event, data = {} } = msg.payload
      if (event === 'phase') setPhase(data.phase || phase)
      else if (event === 'reiterate') {
        // Never-fail loop is retrying with a broader strategy — show it adapting.
        setStatus('running')
        setReiterating({ attempt: data.attempt, max: data.max_attempts, reason: data.reason })
      }
      else if (event === 'sources_found') setCounts(c => ({ ...c, found: data.count || 0 }))
      else if (event === 'source_visit') {
        setSources(prev => prev.some(s => s.url === data.url) ? prev : [...prev, { url: data.url, host: hostOf(data.url), title: data.title, read: false }].slice(-40))
      } else if (event === 'source_read') {
        setCounts(c => ({ ...c, read: data.count || c.read + 1 }))
        setSources(prev => prev.map(s => s.url === data.url ? { ...s, read: true, chars: data.chars } : s))
      } else if (event === 'source_failed') {
        setSources(prev => prev.map(s => s.url === data.url ? { ...s, failed: true } : s))
      } else if (event === 'done') {
        // The backend never emits a terminal 'failed'; a run that couldn't gather
        // enough sources arrives here as done+partial so the user is always informed.
        setStatus(data.partial ? 'partial' : 'done'); setPhase('report')
        setReiterating(null)
        loadReport(reportId)
      } else if (event === 'failed') {
        setStatus('failed'); setError(data.error || 'research failed')
      }
    }
    ws.onerror = () => { if (!closed) setError(prev => prev) }
    return () => { closed = true; try { ws.close() } catch { /* noop */ } }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId])

  const loadReport = (id) => {
    fetch(`${API}/${id}`, { headers: authHeaders() })
      .then(r => r.json())
      .then(d => {
        const rep = d.report || null
        setReport(rep)
        // Reconcile status from the persisted report so a missed/late WS 'done'
        // can't leave the card stuck on 'running'.
        if (rep && rep.status === 'done') setStatus(rep.partial ? 'partial' : 'done')
        else if (rep && rep.status === 'failed') { setStatus('failed'); setError(rep.error || 'research failed') }
      })
      .catch(() => {})
  }

  // Fallback: the card normally advances on WS events, but if the socket attaches
  // late or drops, poll the persisted report (same report_id) until it resolves so
  // a completed run always reports back. Bounded; stops once terminal.
  useEffect(() => {
    if (!reportId) return
    loadReport(reportId) // initial reconcile (run may already be finished)
    let ticks = 0
    const iv = setInterval(() => {
      ticks += 1
      if (status === 'done' || status === 'partial' || status === 'failed' || ticks > 240) {
        clearInterval(iv); return
      }
      loadReport(reportId)
    }, 5000)
    return () => clearInterval(iv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId, status])

  const statusColor = { running: '#E5C76B', done: '#00FFB4', partial: '#E5A640', failed: '#F87171' }[status]

  return (
    <div className="dri" data-status={status}>
      <div className="dri__head" onClick={() => setExpanded(e => !e)}>
        <span className="dri__dot" style={{ background: statusColor }} />
        <span className="dri__title">Deep Research</span>
        <span className="dri__topic" title={topic}>{topic}</span>
        <span className="dri__depth">{depth}</span>
        <span className="dri__toggle">{expanded ? '▾' : '▸'}</span>
      </div>

      {expanded && (
        <div className="dri__body">
          {reiterating && status === 'running' && (
            <div className="dri__reiterate">
              ↻ Reiterating (attempt {reiterating.attempt}/{reiterating.max}) — {reiterating.reason || 'broadening the search'}
            </div>
          )}

          {status !== 'failed' && (
            <div className="dri__statusline">
              {status === 'running' ? (
                <><span className="dri__spinner" /> {PHASE_LABELS[phase] || phase}…</>
              ) : status === 'partial' ? (
                <>⚠ Completed with partial results{report?.duration_s ? ` · ${fmtDuration(report.duration_s)}` : ''}</>
              ) : (
                <>✓ Research complete{report?.duration_s ? ` · ${fmtDuration(report.duration_s)}` : ''}</>
              )}
              <span className="dri__metric">{counts.read}/{counts.found || sources.length} sources read</span>
            </div>
          )}

          {error && <div className="dri__error">⚠ {error}</div>}

          {sources.length > 0 && (
            <div className="dri__sources">
              <div className="dri__sources-label">Sites visited</div>
              <ul className="dri__source-list">
                {sources.slice(-12).map((s, i) => {
                  const href = safeHref(s.url)
                  return (
                    <li key={`${s.url}-${i}`} className={`dri__source ${s.read ? 'is-read' : s.failed ? 'is-failed' : 'is-visiting'}`}>
                      <span className="dri__source-mark">{s.read ? '✓' : s.failed ? '✕' : '◌'}</span>
                      {href
                        ? <a href={href} target="_blank" rel="noreferrer noopener" title={s.title || s.host}>{s.host}</a>
                        : <span title={s.title || ''}>{s.host}</span>}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {report && (status === 'done' || status === 'partial') && (
            <div className="dri__report">
              {status === 'partial' && report.error && (
                <div className="dri__partial-note">Could not fully complete: {report.error}</div>
              )}
              <div className="dri__report-summary">
                {report.executive_summary || report.report_md?.slice(0, 1500) || '(report saved to library)'}
              </div>
              {Array.isArray(report.key_findings) && report.key_findings.length > 0 && (
                <ul className="dri__findings">
                  {report.key_findings.slice(0, 5).map((k, i) => <li key={i}>{k}</li>)}
                </ul>
              )}
              <div className="dri__report-actions">
                <span>{report.sources_fetched || counts.read} sources</span>
                {report.id && <a href={`/research?report=${encodeURIComponent(report.id)}`} className="dri__open">Open full report →</a>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
