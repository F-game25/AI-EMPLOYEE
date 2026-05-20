import { useEffect, useState } from 'react'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { Panel, StatusPill } from '../nexus-ui'
import './ResearchActivityPanel.css'

function shortUrl(u) {
  if (!u) return ''
  try {
    const x = new URL(u)
    return `${x.hostname}${x.pathname.length > 16 ? x.pathname.slice(0, 16) + '…' : x.pathname}`
  } catch {
    return u.length > 32 ? u.slice(0, 29) + '…' : u
  }
}

export default function ResearchActivityPanel() {
  const session = useCognitiveStore(s => s.researchSession)
  const history = useCognitiveStore(s => s.researchHistory)
  const [serverHistory, setServerHistory] = useState([])

  useEffect(() => {
    let cancelled = false
    fetch('/api/tasks/research/recent?limit=20')
      .then(r => r.ok ? r.json() : { sessions: [] })
      .then(d => { if (!cancelled) setServerHistory(d.sessions || []) })
      .catch(() => { if (!cancelled) setServerHistory([]) })
    return () => { cancelled = true }
  }, [history.length])

  const merged = (() => {
    const seen = new Set()
    const out = []
    for (const r of history) {
      const key = `${r.taskId || ''}:${r.goal}:${r.hop}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push({
        topic: (r.gaps && r.gaps[0]) || r.goal || 'research',
        goal: r.goal || '',
        findings_count: r.findings_count || 0,
        sources: r.sources || [],
        hop: r.hop,
        stored_at: new Date(r.ts || Date.now()).toISOString(),
      })
    }
    for (const s of serverHistory) {
      out.push({
        topic: s.topic || s.gap || 'research',
        goal: s.goal || '',
        findings_count: (s.findings || []).length,
        sources: (s.findings || []).map(f => f.url).filter(Boolean),
        stored_at: s.stored_at,
      })
    }
    return out.slice(0, 20)
  })()

  const liveCount = session ? 1 : 0

  return (
    <Panel
      title="RESEARCH ACTIVITY"
      icon="◎"
      className="rap-panel"
      actions={<StatusPill label={liveCount ? `${liveCount} LIVE` : 'IDLE'} tone={liveCount ? 'cool' : 'idle'} size="sm" />}
    >
      {session && (
        <div className="rap-live">
          <div className="rap-live-head">
            <span className="rap-live-status">▸ {session.status === 'done' ? 'COMPLETED' : 'RESEARCHING'}</span>
            <span className="rap-live-hop">HOP {session.hop ?? 0} / 3</span>
          </div>
          <div className="rap-live-goal">{session.goal || '(no goal)'}</div>
          {Array.isArray(session.gaps) && session.gaps.length > 0 && (
            <div className="rap-live-gaps">{session.gaps.slice(0, 3).join(' · ')}</div>
          )}
        </div>
      )}

      {merged.length === 0 ? (
        <div className="rap-empty">No research sessions yet. The system will learn online when a task lacks context.</div>
      ) : (
        <div className="rap-list">
          {merged.map((r, i) => (
            <div key={i} className="rap-row">
              <span className="rap-row__topic" title={r.topic}>{r.topic}</span>
              <span className="rap-row__goal" title={r.goal}>{r.goal}</span>
              <span className="rap-row__meta">{r.findings_count} src · {(r.stored_at || '').slice(11, 19)}</span>
              {r.sources && r.sources.length > 0 && (
                <div className="rap-row__sources">
                  {r.sources.slice(0, 4).map((u, j) => (
                    <a key={j} href={u} target="_blank" rel="noopener noreferrer" className="rap-row__src" title={u}>
                      {shortUrl(u)}
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
