import { useState, useCallback } from 'react'
import { Panel, KPITile, HexButton, StatusPill, HexFrame } from '../nexus-ui'
import { API_URL } from '../../config/api'
import './MoneyModePage.css'

const BASE = API_URL

const PIPELINES = [
  {
    id: 'content',
    label: 'Content Pipeline',
    icon: '✍',
    desc: 'Generate, publish, and distribute content across channels.',
    endpoint: '/api/money/content-pipeline',
    tone: 'cool',
  },
  {
    id: 'lead',
    label: 'Lead Pipeline',
    icon: '◎',
    desc: 'Identify, qualify, and enrich B2B leads via Apollo + scraping.',
    endpoint: '/api/money/lead-pipeline',
    tone: 'gold',
  },
  {
    id: 'opportunity',
    label: 'Opportunity Pipeline',
    icon: '$',
    desc: 'Run outreach sequences and convert opportunities to revenue.',
    endpoint: '/api/money/opportunity-pipeline',
    tone: 'success',
  },
]

function PipelineCard({ pipeline, onRun, running, lastRun }) {
  const isRunning = running === pipeline.id
  return (
    <div className={`mm-card mm-card--${pipeline.tone}`}>
      <div className="mm-card__head">
        <HexFrame size="md" tone={pipeline.tone} glow={isRunning} pulse={isRunning}>
          <span className="mm-card__icon">{pipeline.icon}</span>
        </HexFrame>
        <div className="mm-card__title">
          <div className="mm-card__name">{pipeline.label}</div>
          <div className="mm-card__desc">{pipeline.desc}</div>
        </div>
        {lastRun && (
          <StatusPill tone={pipeline.tone} label={`$${lastRun.estimated_roi} ROI`} />
        )}
      </div>
      {lastRun && (
        <div className="mm-card__last">
          <span>LAST · {new Date(lastRun.executed_at).toLocaleTimeString()}</span>
          <span className="mm-card__last-status">● {lastRun.status}</span>
        </div>
      )}
      <HexButton
        variant="primary"
        size="sm"
        icon={isRunning ? null : '▶'}
        loading={isRunning}
        onClick={() => onRun(pipeline)}
      >
        {isRunning ? 'RUNNING…' : 'RUN PIPELINE'}
      </HexButton>
    </div>
  )
}

export default function MoneyModePage() {
  const [running, setRunning]   = useState(null)
  const [history, setHistory]   = useState([])
  const [totals, setTotals]     = useState({ roi: 0, runs: 0 })
  const [lastRuns, setLastRuns] = useState({})
  const [error, setError]       = useState(null)

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
      setHistory(h => [{ ...data, pipeline: pipeline.id, label: pipeline.label, tone: pipeline.tone, ts: Date.now() }, ...h].slice(0, 50))
      setLastRuns(lr => ({ ...lr, [pipeline.id]: { ...data, executed_at: new Date().toISOString() } }))
      setTotals(t => ({ roi: t.roi + (data.estimated_roi || 0), runs: t.runs + 1 }))
    } catch (e) {
      setError(`${pipeline.label} failed: ${e.message}`)
    } finally {
      setRunning(null)
    }
  }, [])

  return (
    <div className="mm-grid">
      <div className="mm-kpis">
        <KPITile icon="$" iconTone="success" label="Total ROI" value={`$${totals.roi.toFixed(2)}`} sub="THIS SESSION" accent />
        <KPITile icon="◎" iconTone="cool"    label="Runs"      value={totals.runs} sub="PIPELINES TRIGGERED" />
        <KPITile icon="✦" iconTone="gold"    label="Available" value={PIPELINES.length} sub="PIPELINES" />
      </div>

      {error && (
        <div className="mm-error">
          <span className="mm-error__dot" />
          <span>{error}</span>
        </div>
      )}

      <Panel
        icon="⌬"
        title="Money Pipelines"
        actions={<StatusPill tone="gold" label={`${PIPELINES.length} ACTIVE`} dot={false} size="sm" />}
      >
        <div className="mm-list">
          {PIPELINES.map(p => (
            <PipelineCard
              key={p.id}
              pipeline={p}
              onRun={runPipeline}
              running={running}
              lastRun={lastRuns[p.id]}
            />
          ))}
        </div>
      </Panel>

      <Panel
        icon="◷"
        title="Run History"
        actions={<StatusPill tone="idle" label={`${history.length} RUNS`} dot={false} size="sm" />}
      >
        {history.length === 0 ? (
          <div className="mm-empty">No pipelines run yet this session.</div>
        ) : (
          <div className="mm-history">
            {history.map((r, i) => (
              <div key={i} className={`mm-history__row mm-history__row--${r.tone}`}>
                <span className="mm-history__dot" />
                <span className="mm-history__label">{r.label}</span>
                <span className="mm-history__roi">${r.estimated_roi} ROI</span>
                <span className="mm-history__time">{new Date(r.ts).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
