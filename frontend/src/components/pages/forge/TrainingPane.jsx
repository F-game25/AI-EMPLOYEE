import { useState, useEffect, useCallback } from 'react'

const api = {
  get: (path) => fetch(path, { headers: { authorization: `Bearer ${localStorage.getItem('token')}` } }).then(r => r.json()),
  post: (path, body) => fetch(path, { method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${localStorage.getItem('token')}` }, body: JSON.stringify(body) }).then(r => r.json()),
}

function StatusBadge({ status }) {
  const colors = { PENDING: '#666', VALIDATING: '#f59e0b', TRAINING: '#3b82f6', COMPLETED: '#22c55e', FAILED: '#ef4444', EVALUATING: '#a855f7' }
  return (
    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: (colors[status] || '#666') + '33', color: colors[status] || '#666', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {status || '—'}
    </span>
  )
}

export function TrainingPane({ project }) {
  const [runs, setRuns] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [modelType, setModelType] = useState('intent_classifier')

  const load = useCallback(async () => {
    if (!project?.id) return
    setLoading(true)
    try {
      const [runsRes, sumRes] = await Promise.all([
        api.get(`/api/forge/projects/${project.id}/training-runs`),
        api.get(`/api/forge/projects/${project.id}/training-summary`),
      ])
      setRuns(runsRes.runs || [])
      setSummary(sumRes.summary || sumRes)
    } catch { /* best-effort */ }
    setLoading(false)
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function startRun() {
    setStarting(true)
    try {
      const r = await api.post(`/api/forge/projects/${project.id}/training-runs`, { model_type: modelType })
      if (r.training_run_id) await api.post(`/api/forge/training-runs/${r.training_run_id}/start`, {})
      await load()
    } catch { /* best-effort */ }
    setStarting(false)
  }

  const s = { color: 'var(--af-text, #ccc)', fontSize: 12, fontFamily: 'monospace' }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ ...s, fontSize: 11, opacity: 0.5, letterSpacing: '0.08em', textTransform: 'uppercase' }}>TRAINING — PHASE 8</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={modelType} onChange={e => setModelType(e.target.value)}
            style={{ fontSize: 11, padding: '3px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text, #ccc)', cursor: 'pointer' }}>
            <option value="intent_classifier">Intent Classifier</option>
            <option value="skill_router">Skill Router</option>
            <option value="quality_gate">Quality Gate</option>
          </select>
          <button onClick={startRun} disabled={starting || !project?.id}
            style={{ fontSize: 11, padding: '4px 10px', background: 'rgba(59,130,246,0.2)', border: '1px solid rgba(59,130,246,0.4)', borderRadius: 3, color: '#60a5fa', cursor: 'pointer' }}>
            {starting ? 'Starting…' : '▶ Start training run'}
          </button>
          <button onClick={load} style={{ fontSize: 11, padding: '3px 8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted, #888)', cursor: 'pointer' }}>↻</button>
        </div>
      </div>

      {summary && (
        <div style={{ display: 'flex', gap: 8 }}>
          {[['Runs', summary.total_runs ?? runs.length], ['Completed', summary.completed ?? runs.filter(r => r.status === 'COMPLETED').length], ['Models', summary.model_versions ?? '—']].map(([label, val]) => (
            <div key={label} style={{ flex: 1, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '8px 12px', textAlign: 'center' }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{val}</div>
              <div style={{ fontSize: 10, opacity: 0.5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ ...s, opacity: 0.4, textAlign: 'center', padding: 32 }}>Loading training runs…</div>
      ) : runs.length === 0 ? (
        <div style={{ ...s, opacity: 0.4, textAlign: 'center', padding: 32 }}>No training runs yet. Start one above.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {runs.map(run => (
            <div key={run.training_run_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <StatusBadge status={run.status} />
              <div style={{ flex: 1 }}>
                <div style={{ ...s, fontSize: 12 }}>{run.model_type || 'training run'}</div>
                {run.metrics?.train_accuracy != null && (
                  <div style={{ ...s, fontSize: 10, opacity: 0.5 }}>accuracy: {(run.metrics.train_accuracy * 100).toFixed(1)}%</div>
                )}
              </div>
              <div style={{ ...s, fontSize: 10, opacity: 0.4 }}>{run.created_at?.slice(0, 10) || ''}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
