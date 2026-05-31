import { useState, useEffect, useCallback } from 'react'

const api = {
  get: (path) => fetch(path, { headers: { authorization: `Bearer ${localStorage.getItem('token')}` } }).then(r => r.json()),
  post: (path, body) => fetch(path, { method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${localStorage.getItem('token')}` }, body: JSON.stringify(body) }).then(r => r.json()),
}

export function CognitiveCorePanel({ project }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const load = useCallback(async () => {
    if (!project?.id) return
    setLoading(true)
    try {
      const r = await api.get(`/api/forge/projects/${project.id}/cognitive-events`)
      setEvents(r.events || [])
    } catch { /* best-effort */ }
    setLoading(false)
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function sendEvent() {
    if (!input.trim() || !project?.id) return
    setSending(true)
    try {
      await api.post(`/api/forge/projects/${project.id}/cognitive-events`, { event: input.trim(), type: 'user_observation' })
      setInput('')
      await load()
    } catch { /* best-effort */ }
    setSending(false)
  }

  const s = { color: 'var(--af-text, #ccc)', fontSize: 12, fontFamily: 'monospace' }
  const typeColors = { user_observation: '#60a5fa', agent_insight: '#a78bfa', error: '#f87171', correction: '#34d399' }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ ...s, fontSize: 11, opacity: 0.5, letterSpacing: '0.08em', textTransform: 'uppercase' }}>COGNITIVE CORE — PHASE 9</span>
        <button onClick={load} style={{ fontSize: 11, padding: '3px 8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted, #888)', cursor: 'pointer' }}>↻</button>
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendEvent()}
          placeholder="Log an observation or correction…"
          style={{ flex: 1, fontSize: 12, padding: '6px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, color: 'var(--af-text, #ccc)', fontFamily: 'monospace' }}
        />
        <button onClick={sendEvent} disabled={sending || !input.trim()}
          style={{ fontSize: 11, padding: '6px 12px', background: 'rgba(167,139,250,0.2)', border: '1px solid rgba(167,139,250,0.4)', borderRadius: 4, color: '#a78bfa', cursor: 'pointer' }}>
          {sending ? '…' : 'Log'}
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {loading ? (
          <div style={{ ...s, opacity: 0.4, textAlign: 'center', padding: 32 }}>Loading cognitive events…</div>
        ) : events.length === 0 ? (
          <div style={{ ...s, opacity: 0.4, textAlign: 'center', padding: 32 }}>No cognitive events logged yet.<br />Use the input above to log observations.</div>
        ) : (
          [...events].reverse().map((ev, i) => (
            <div key={i} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 5, padding: '8px 10px', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 10, padding: '2px 5px', borderRadius: 3, background: (typeColors[ev.type] || '#666') + '22', color: typeColors[ev.type] || '#888', flexShrink: 0, marginTop: 1 }}>
                {ev.type?.replace('_', ' ') || 'event'}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ ...s, fontSize: 12, lineHeight: 1.5 }}>{ev.event || ev.content || JSON.stringify(ev)}</div>
                {ev.timestamp && <div style={{ ...s, fontSize: 10, opacity: 0.4, marginTop: 2 }}>{new Date(ev.timestamp).toLocaleString('nl-NL')}</div>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
