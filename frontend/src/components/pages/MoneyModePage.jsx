import { useState, useEffect, useCallback } from 'react'
import { Panel, Badge, StatCard } from '../ui/primitives'
import { API_URL } from '../../config/api'

const BASE = API_URL

const PIPELINES = [
  {
    id: 'content',
    label: 'Content Pipeline',
    icon: '✍️',
    desc: 'Generate, publish, and distribute content across channels.',
    endpoint: '/api/money/content-pipeline',
    color: '#20D6C7',
  },
  {
    id: 'lead',
    label: 'Lead Pipeline',
    icon: '🎯',
    desc: 'Identify, qualify, and enrich B2B leads via Apollo + scraping.',
    endpoint: '/api/money/lead-pipeline',
    color: '#E5C76B',
  },
  {
    id: 'opportunity',
    label: 'Opportunity Pipeline',
    icon: '💰',
    desc: 'Run outreach sequences and convert opportunities to revenue.',
    endpoint: '/api/money/opportunity-pipeline',
    color: '#22C55E',
  },
]

function PipelineCard({ pipeline, onRun, running, lastRun }) {
  return (
    <div style={{ padding: '16px 18px', borderRadius: 10, border: `1px solid ${pipeline.color}22`, background: `${pipeline.color}08`, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 22 }}>{pipeline.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary, #F0E9D2)' }}>{pipeline.label}</div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{pipeline.desc}</div>
        </div>
        {lastRun && (
          <Badge color={pipeline.color} label={`$${lastRun.estimated_roi} ROI`} />
        )}
      </div>
      {lastRun && (
        <div style={{ display: 'flex', gap: 12, fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.35)' }}>
          <span>Last: {new Date(lastRun.executed_at).toLocaleTimeString()}</span>
          <span style={{ color: '#22C55E' }}>● {lastRun.status}</span>
        </div>
      )}
      <button
        onClick={() => onRun(pipeline)}
        disabled={running === pipeline.id}
        style={{ alignSelf: 'flex-start', padding: '7px 18px', borderRadius: 7, border: `1px solid ${pipeline.color}55`, background: running === pipeline.id ? 'rgba(255,255,255,0.04)' : `${pipeline.color}18`, color: running === pipeline.id ? 'rgba(255,255,255,0.3)' : pipeline.color, fontSize: 12, cursor: running === pipeline.id ? 'not-allowed' : 'pointer', fontWeight: 600 }}
      >
        {running === pipeline.id ? '⏳ Running…' : '▶ Run Pipeline'}
      </button>
    </div>
  )
}

export default function MoneyModePage() {
  const [running, setRunning]     = useState(null)
  const [history, setHistory]     = useState([])
  const [totals, setTotals]       = useState({ roi: 0, runs: 0 })
  const [lastRuns, setLastRuns]   = useState({})
  const [error, setError]         = useState(null)

  const runPipeline = useCallback(async (pipeline) => {
    setRunning(pipeline.id)
    setError(null)
    try {
      const token = localStorage.getItem('auth_token') || ''
      const r = await fetch(`${BASE}${pipeline.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      })
      const data = await r.json()
      setHistory(h => [{ ...data, pipeline: pipeline.id, label: pipeline.label, color: pipeline.color, ts: Date.now() }, ...h].slice(0, 50))
      setLastRuns(lr => ({ ...lr, [pipeline.id]: { ...data, executed_at: new Date().toISOString() } }))
      setTotals(t => ({ roi: t.roi + (data.estimated_roi || 0), runs: t.runs + 1 }))
    } catch (e) {
      setError(`${pipeline.label} failed: ${e.message}`)
    } finally {
      setRunning(null)
    }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, flexShrink: 0 }}>
        <StatCard label="Total ROI" value={`$${totals.roi.toFixed(2)}`} color="#22C55E" sub="this session" />
        <StatCard label="Runs" value={totals.runs} color="#20D6C7" sub="pipelines triggered" />
        <StatCard label="Pipelines" value={PIPELINES.length} color="#E5C76B" sub="available" />
      </div>

      {error && (
        <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#EF4444', fontSize: 12 }}>{error}</div>
      )}

      <Panel title="Money Pipelines">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {PIPELINES.map(p => (
            <PipelineCard key={p.id} pipeline={p} onRun={runPipeline} running={running} lastRun={lastRuns[p.id]} />
          ))}
        </div>
      </Panel>

      <Panel title="Run History">
        {history.length === 0 ? (
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', fontStyle: 'italic' }}>No pipelines run yet this session.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {history.map((r, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', fontSize: 12 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
                <span style={{ flex: 1, color: 'var(--text-primary, #F0E9D2)' }}>{r.label}</span>
                <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#22C55E' }}>${r.estimated_roi} ROI</span>
                <span style={{ fontFamily: 'monospace', fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>{new Date(r.ts).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
