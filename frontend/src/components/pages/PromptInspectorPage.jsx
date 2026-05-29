import { useState, useEffect } from 'react'
import api from '../../api/client'

export default function PromptInspectorPage() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/prompt-inspector/history')
      .then(d => setHistory(d.history || d.prompts || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 16 }}>Prompt Inspector</h2>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: '#ef4444' }}>Error: {error}</p>}
      {!loading && !error && history.length === 0 && (
        <p style={{ color: '#888' }}>No prompt history yet. Run a task to see LLM prompts recorded here.</p>
      )}
      {history.map((entry, i) => (
        <div key={i} style={{ marginBottom: 16, padding: 12, background: 'rgba(255,255,255,0.04)', borderRadius: 6, border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>
            {entry.model || '—'} · {entry.timestamp || ''}
          </div>
          <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', color: '#ccc', margin: 0 }}>
            {entry.prompt || entry.content || JSON.stringify(entry, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  )
}
