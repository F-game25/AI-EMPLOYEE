import { useEffect, useState, useCallback } from 'react'
import api from '../../api/client'

function relativeTime(ts) {
  if (!ts) return 'never'
  const now = Date.now() / 1000
  const diff = now - (ts > 1e12 ? ts / 1000 : ts) // accept ms or s
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function SkillGauge({ level, breakdown }) {
  const pct = Math.round((level || 0) * 100)
  return (
    <div className="stp-gauge" title={breakdown || `${pct}% intelligence`}>
      <div className="stp-gauge-track">
        <div className="stp-gauge-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="stp-gauge-label">{pct}%</span>
    </div>
  )
}

export default function StandingTopicsPanel({ onLearnNew, onOpenTopic }) {
  const [topics, setTopics] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(new Set())

  const fetchTopics = useCallback(() => {
    api.get('/api/topics')
      .then(d => {
        const list = Array.isArray(d) ? d : (d?.topics || [])
        setTopics(list)
        setError(null)
      })
      .catch(e => {
        // 404 = endpoint not yet wired; surface as empty rather than fatal
        if (e?.status === 404) { setTopics([]); setError(null) }
        else { setError(e?.message || 'failed to load topics'); setTopics([]) }
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchTopics()
    const t = setInterval(fetchTopics, 30000)

    const wsHandler = (ev) => {
      const detail = ev?.detail || {}
      const type = detail.type || ev?.type
      if (type === 'topic:skill_updated' || type === 'topic:updated') fetchTopics()
    }
    window.addEventListener('ws:event', wsHandler)
    window.addEventListener('topic:skill_updated', wsHandler)
    window.addEventListener('ws:topic-update', wsHandler)

    return () => {
      clearInterval(t)
      window.removeEventListener('ws:event', wsHandler)
      window.removeEventListener('topic:skill_updated', wsHandler)
      window.removeEventListener('ws:topic-update', wsHandler)
    }
  }, [fetchTopics])

  const refreshTopic = async (id) => {
    setRefreshing(prev => { const s = new Set(prev); s.add(id); return s })
    try { await api.post(`/api/topics/${id}/refresh`, {}) } catch { /* swallow — surface via topics refetch */ }
    setTimeout(() => {
      setRefreshing(prev => { const s = new Set(prev); s.delete(id); return s })
      fetchTopics()
    }, 1500)
  }

  const unpinTopic = async (id) => {
    if (typeof window !== 'undefined' && !window.confirm(`Unpin "${id}"?`)) return
    try { await api.post(`/api/topics/${id}/pin`, { pinned: false }) } catch { /* fall through to refetch */ }
    fetchTopics()
  }

  const pinned = topics.filter(t => t.pinned)

  return (
    <div className="stp-root">
      <style>{`
        .stp-root { display: flex; flex-direction: column; gap: 12px; padding: 16px; font-family: 'JetBrains Mono', monospace; }
        .stp-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
        .stp-title { font-size: 11px; letter-spacing: 2px; color: #e5c76b; }
        .stp-teach-btn {
          padding: 8px 14px;
          background: linear-gradient(180deg, #fbbf24 0%, #d4a82e 100%);
          color: #1a1408;
          border: 0;
          border-radius: 3px;
          font-family: inherit;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 1px;
          cursor: pointer;
          box-shadow: 0 0 12px rgba(251,191,36,0.3);
        }
        .stp-teach-btn:hover { box-shadow: 0 0 18px rgba(251,191,36,0.5); }
        .stp-card {
          background: rgba(13,13,24,0.55);
          border: 1px solid rgba(229,199,107,0.1);
          border-left: 3px solid var(--topic-color, #22d3ee);
          border-radius: 4px;
          padding: 14px;
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 12px;
          transition: border-color 200ms;
        }
        .stp-card:hover { border-color: rgba(229,199,107,0.3); }
        .stp-card__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .stp-card__title { font-size: 14px; color: #fff; font-weight: 600; }
        .stp-card__pin { padding: 2px 6px; background: rgba(229,199,107,0.12); color: #e5c76b; font-size: 8px; border-radius: 2px; letter-spacing: 1px; }
        .stp-card__meta { font-size: 9px; color: rgba(255,255,255,0.45); margin-top: 4px; letter-spacing: 1px; }
        .stp-subtopics { display: flex; gap: 4px; margin-top: 8px; flex-wrap: wrap; }
        .stp-subtopic { padding: 1px 6px; background: rgba(34,211,238,0.08); color: #22d3ee; font-size: 9px; border-radius: 2px; }
        .stp-open-q { margin-top: 6px; font-size: 10px; color: #fbbf24; cursor: pointer; }
        .stp-open-q:hover { text-decoration: underline; }
        .stp-right { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; min-width: 200px; }
        .stp-gauge { display: flex; align-items: center; gap: 8px; min-width: 180px; cursor: help; }
        .stp-gauge-track { flex: 1; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; }
        .stp-gauge-fill { height: 100%; background: linear-gradient(90deg, #ef4444 0%, #fbbf24 50%, #22c55e 100%); transition: width 800ms ease-out; }
        .stp-gauge-label { font-size: 12px; color: #fff; min-width: 36px; text-align: right; }
        .stp-actions { display: flex; gap: 6px; }
        .stp-action-btn {
          padding: 4px 8px;
          background: transparent;
          border: 1px solid rgba(255,255,255,0.15);
          color: rgba(255,255,255,0.7);
          font-family: inherit;
          font-size: 9px;
          border-radius: 2px;
          cursor: pointer;
          letter-spacing: 1px;
        }
        .stp-action-btn:hover { border-color: #e5c76b; color: #e5c76b; }
        .stp-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .stp-action-btn--danger:hover { border-color: #ef4444; color: #ef4444; }
        .stp-empty { text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.4); font-size: 12px; line-height: 1.6; }
        .stp-empty strong { color: #e5c76b; }
        .stp-error { color: #ef4444; padding: 16px; font-size: 11px; }
        @keyframes stp-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .stp-refreshing { animation: stp-pulse 800ms ease-in-out infinite; }
      `}</style>

      <div className="stp-header">
        <div className="stp-title">STANDING TOPICS ({pinned.length})</div>
        <button className="stp-teach-btn" onClick={onLearnNew} type="button">+ TEACH ME ABOUT …</button>
      </div>

      {loading && <div className="stp-empty">loading topics…</div>}
      {error && <div className="stp-error">⚠ {error}</div>}
      {!loading && !error && pinned.length === 0 && (
        <div className="stp-empty">
          No pinned topics yet.<br />
          Click <strong>+ TEACH ME ABOUT …</strong> to start.
        </div>
      )}

      {pinned.map(t => {
        const memCount = t.memory_count ?? t.memories ?? 0
        const srcCount = t.sources_consulted ?? t.sources ?? 0
        const openQ = Array.isArray(t.open_questions) ? t.open_questions : []
        const subs = Array.isArray(t.subtopics) ? t.subtopics : []
        const confidence = typeof t.confidence_avg === 'number' ? t.confidence_avg.toFixed(2) : '—'
        const breakdown = `memories: ${memCount} · sources: ${srcCount} · confidence: ${confidence} · open Q: ${openQ.length}`

        return (
          <div key={t.id}
               className={`stp-card ${refreshing.has(t.id) ? 'stp-refreshing' : ''}`}
               style={{ '--topic-color': t.color || '#22d3ee' }}>
            <div>
              <div className="stp-card__head">
                <span className="stp-card__title">{t.label || t.id}</span>
                {t.schedule && t.schedule !== 'manual' && (
                  <span className="stp-card__pin">{String(t.schedule).toUpperCase()}</span>
                )}
              </div>
              <div className="stp-card__meta">
                {memCount} memories · {srcCount} sources · last {relativeTime(t.last_studied || t.last_updated)}
              </div>
              {subs.length > 0 && (
                <div className="stp-subtopics">
                  {subs.slice(0, 4).map(s => <span key={s} className="stp-subtopic">{s}</span>)}
                  {subs.length > 4 && <span className="stp-subtopic">+{subs.length - 4} more</span>}
                </div>
              )}
              {openQ.length > 0 && (
                <div className="stp-open-q" onClick={() => onOpenTopic?.(t.id, 'questions')}>
                  ? {openQ.length} open question{openQ.length === 1 ? '' : 's'}
                </div>
              )}
            </div>
            <div className="stp-right">
              <SkillGauge level={t.skill_level ?? t.intelligence_level ?? 0} breakdown={breakdown} />
              <div className="stp-actions">
                <button type="button" className="stp-action-btn"
                        onClick={() => refreshTopic(t.id)}
                        disabled={refreshing.has(t.id)}>
                  {refreshing.has(t.id) ? '…' : 'REFRESH'}
                </button>
                <button type="button" className="stp-action-btn" onClick={() => onOpenTopic?.(t.id)}>
                  OPEN
                </button>
                <button type="button" className="stp-action-btn stp-action-btn--danger" onClick={() => unpinTopic(t.id)}>
                  UNPIN
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
