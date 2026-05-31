import { useEffect, useState, useCallback, useMemo } from 'react'
import api from '../../api/client'
import { useLearningStore } from '../../store/learningStore'

function ConfidenceBar({ value, decision }) {
  const pct = Math.round((value || 0) * 100)
  const color = decision === 'auto_save' ? '#22c55e' : decision === 'pending_review' ? '#fbbf24' : '#ef4444'
  return (
    <div className="prq-conf">
      <div className="prq-conf__bar"><div className="prq-conf__fill" style={{ width: `${pct}%`, background: color }} /></div>
      <span className="prq-conf__pct" style={{ color }}>{pct}%</span>
    </div>
  )
}

function hostnameOf(url) {
  try { return new URL(url).hostname } catch { return url }
}

function ReviewCard({ entry, onApprove, onReject, onEdit }) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(entry.claim)
  const verification = entry.verification || {}
  const crossRefs = verification.cross_references || []
  const contradictions = verification.contradictions || []
  const tsMs = typeof entry.ts === 'number' && entry.ts < 1e12 ? entry.ts * 1000 : (entry.ts || 0)

  return (
    <div className={`prq-card ${contradictions.length > 0 ? 'prq-card--has-contradictions' : ''}`}>
      <div className="prq-card__head">
        <ConfidenceBar value={verification.confidence} decision={verification.decision} />
        <span className="prq-card__topic">{entry.topic || 'general'}</span>
        <span className="prq-card__time">{tsMs ? new Date(tsMs).toLocaleTimeString() : ''}</span>
      </div>

      {editing ? (
        <textarea
          className="prq-card__edit"
          value={editValue}
          onChange={e => setEditValue(e.target.value)}
          rows={4}
          autoFocus
        />
      ) : (
        <div className="prq-card__claim">{entry.claim}</div>
      )}

      {verification.reasoning && (
        <div className="prq-card__reasoning">{verification.reasoning}</div>
      )}

      {entry.sources && entry.sources.length > 0 && (
        <div className="prq-card__sources">
          {entry.sources.map((s, i) => (
            <a key={i} href={s} target="_blank" rel="noreferrer" className="prq-source-link">↗ {hostnameOf(s)}</a>
          ))}
        </div>
      )}

      {crossRefs.length > 0 && (
        <details className="prq-card__details">
          <summary>{crossRefs.length} supporting memory match{crossRefs.length === 1 ? '' : 'es'}</summary>
          {crossRefs.map((c, i) => (
            <div key={i} className="prq-ref prq-ref--agrees">
              <span className="prq-ref__score">+{Math.round((c.score || 0) * 100)}%</span> {c.excerpt}
            </div>
          ))}
        </details>
      )}

      {contradictions.length > 0 && (
        <details className="prq-card__details" open>
          <summary style={{ color: '#ef4444' }}>⚠ {contradictions.length} contradiction{contradictions.length === 1 ? '' : 's'}</summary>
          {contradictions.map((c, i) => (
            <div key={i} className="prq-ref prq-ref--contradicts">
              <span className="prq-ref__score">−{Math.round((c.score || 0) * 100)}%</span> {c.excerpt}
            </div>
          ))}
        </details>
      )}

      <div className="prq-card__actions">
        {editing ? (
          <>
            <button className="prq-btn prq-btn--primary" onClick={() => { onEdit(entry.id, editValue); setEditing(false) }}>Save & Approve</button>
            <button className="prq-btn prq-btn--ghost" onClick={() => { setEditing(false); setEditValue(entry.claim) }}>Cancel</button>
          </>
        ) : (
          <>
            <button className="prq-btn prq-btn--primary" onClick={() => onApprove(entry.id)}>APPROVE</button>
            <button className="prq-btn prq-btn--ghost" onClick={() => setEditing(true)}>EDIT</button>
            <button className="prq-btn prq-btn--danger" onClick={() => onReject(entry.id)}>REJECT</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function PendingReviewQueue() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('pending')   // 'pending' | 'approved' | 'rejected' | 'all'
  const setPendingReviewCount = useLearningStore(s => s.setPendingReviewCount)

  const refresh = useCallback(() => {
    setLoading(true)
    api.get(`/api/memory/pending-review?status=${filter}`)
      .then(d => {
        setEntries(d?.entries || [])
        setPendingReviewCount((d?.stats?.by_status?.pending) || 0)
        setError(null)
      })
      .catch(e => {
        // 404 -> backend not yet wired; treat as empty queue rather than hard error
        const msg = e?.message || 'failed'
        if (/404/.test(msg)) {
          setEntries([])
          setError(null)
        } else {
          setError(msg)
          setEntries([])
        }
      })
      .finally(() => setLoading(false))
  }, [filter, setPendingReviewCount])

  useEffect(() => {
    refresh()
    const handler = () => refresh()
    window.addEventListener('ws:memory-pending-review', handler)
    return () => window.removeEventListener('ws:memory-pending-review', handler)
  }, [refresh])

  const onApprove = async (id) => {
    try { await api.post(`/api/memory/pending-review/${id}/approve`, {}) } catch {}
    refresh()
  }
  const onReject = async (id) => {
    try { await api.post(`/api/memory/pending-review/${id}/reject`, {}) } catch {}
    refresh()
  }
  const onEdit = async (id, claim) => {
    try { await api.post(`/api/memory/pending-review/${id}/edit`, { claim }) } catch {}
    refresh()
  }

  const approveBatch = async (predicate) => {
    const toApprove = entries.filter(predicate).map(e => e.id)
    for (const id of toApprove) {
      try { await api.post(`/api/memory/pending-review/${id}/approve`, {}) } catch {}
    }
    refresh()
  }
  const rejectBatch = async (predicate) => {
    const toReject = entries.filter(predicate).map(e => e.id)
    for (const id of toReject) {
      try { await api.post(`/api/memory/pending-review/${id}/reject`, {}) } catch {}
    }
    refresh()
  }

  const stats = useMemo(() => ({
    total: entries.length,
    high: entries.filter(e => (e.verification?.confidence || 0) >= 0.65).length,
    low: entries.filter(e => (e.verification?.confidence || 0) < 0.45).length,
  }), [entries])

  return (
    <div className="prq-root">
      <style>{`
        .prq-root { display: flex; flex-direction: column; gap: 12px; padding: 16px; font-family: 'JetBrains Mono', monospace; color: rgba(255,255,255,0.85); }
        .prq-header { display: flex; justify-content: space-between; align-items: center; }
        .prq-title { font-size: 11px; letter-spacing: 2px; color: #e5c76b; }
        .prq-filter { display: flex; gap: 4px; }
        .prq-filter button { padding: 4px 10px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.65); font-family: inherit; font-size: 10px; border-radius: 3px; cursor: pointer; letter-spacing: 1px; }
        .prq-filter button.is-active { background: rgba(229,199,107,0.15); border-color: #e5c76b; color: #e5c76b; }
        .prq-batch-actions { display: flex; gap: 8px; padding: 8px 12px; background: rgba(13,13,24,0.5); border-radius: 4px; align-items: center; font-size: 10px; color: rgba(255,255,255,0.5); }
        .prq-batch-btn { padding: 4px 10px; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); color: #22c55e; font-family: inherit; font-size: 10px; border-radius: 3px; cursor: pointer; }
        .prq-batch-btn--danger { background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3); color: #ef4444; }
        .prq-card { background: rgba(13,13,24,0.55); border: 1px solid rgba(229,199,107,0.1); border-radius: 4px; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
        .prq-card--has-contradictions { border-left: 3px solid #ef4444; }
        .prq-card__head { display: flex; gap: 12px; align-items: center; font-size: 9px; color: rgba(255,255,255,0.5); letter-spacing: 1px; }
        .prq-conf { display: flex; align-items: center; gap: 6px; }
        .prq-conf__bar { width: 80px; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; }
        .prq-conf__fill { height: 100%; transition: width 400ms; }
        .prq-conf__pct { font-weight: 700; min-width: 32px; }
        .prq-card__topic { padding: 1px 6px; background: rgba(34,211,238,0.1); color: #22d3ee; border-radius: 2px; }
        .prq-card__time { margin-left: auto; }
        .prq-card__claim { font-size: 13px; color: #fff; line-height: 1.5; }
        .prq-card__edit { background: rgba(0,0,0,0.5); border: 1px solid #e5c76b; color: #fff; padding: 8px; border-radius: 3px; font-family: inherit; font-size: 13px; resize: vertical; }
        .prq-card__reasoning { font-size: 10px; color: rgba(255,255,255,0.5); font-style: italic; padding: 4px 0; }
        .prq-card__sources { display: flex; flex-wrap: wrap; gap: 6px; }
        .prq-source-link { font-size: 9px; color: #22d3ee; text-decoration: none; padding: 2px 6px; background: rgba(34,211,238,0.08); border-radius: 2px; }
        .prq-card__details { font-size: 11px; color: rgba(255,255,255,0.7); cursor: pointer; }
        .prq-card__details summary { padding: 4px 0; color: rgba(255,255,255,0.6); }
        .prq-ref { padding: 4px 8px; margin: 3px 0; background: rgba(255,255,255,0.03); border-radius: 2px; font-size: 11px; line-height: 1.4; display: flex; gap: 8px; }
        .prq-ref--agrees { border-left: 2px solid #22c55e; }
        .prq-ref--contradicts { border-left: 2px solid #ef4444; }
        .prq-ref__score { font-weight: 700; min-width: 36px; }
        .prq-card__actions { display: flex; gap: 8px; margin-top: 4px; }
        .prq-btn { padding: 6px 14px; border-radius: 3px; font-family: inherit; font-size: 10px; font-weight: 700; letter-spacing: 1px; cursor: pointer; border: 0; }
        .prq-btn--primary { background: linear-gradient(180deg, #fbbf24, #d4a82e); color: #1a1408; }
        .prq-btn--ghost { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: rgba(255,255,255,0.7); }
        .prq-btn--danger { background: transparent; border: 1px solid rgba(239,68,68,0.3); color: #ef4444; }
        .prq-empty { padding: 32px; text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; }
      `}</style>

      <div className="prq-header">
        <div className="prq-title">REVIEW QUEUE ({entries.length})</div>
        <div className="prq-filter">
          {['pending', 'approved', 'rejected', 'all'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : ''} onClick={() => setFilter(f)}>{f.toUpperCase()}</button>
          ))}
        </div>
      </div>

      {entries.length > 0 && filter === 'pending' && (
        <div className="prq-batch-actions">
          <span>Quick:</span>
          <button className="prq-batch-btn" onClick={() => approveBatch(e => (e.verification?.confidence || 0) >= 0.65)}>
            Approve all ≥ 65% ({stats.high})
          </button>
          <button className="prq-batch-btn prq-batch-btn--danger" onClick={() => rejectBatch(e => (e.verification?.confidence || 0) < 0.45)}>
            Reject all &lt; 45% ({stats.low})
          </button>
        </div>
      )}

      {loading && <div className="prq-empty">loading queue…</div>}
      {error && <div className="prq-empty" style={{ color: '#ef4444' }}>⚠ {error}</div>}
      {!loading && !error && entries.length === 0 && (
        <div className="prq-empty">
          No {filter === 'all' ? '' : filter} entries.<br />
          {filter === 'pending' && 'New findings will appear here for review.'}
        </div>
      )}

      {entries.map(entry => (
        <ReviewCard
          key={entry.id}
          entry={entry}
          onApprove={onApprove}
          onReject={onReject}
          onEdit={onEdit}
        />
      ))}
    </div>
  )
}
