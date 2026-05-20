import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'
import { API_URL } from '../../config/api'

const API_BASE = API_URL

function asPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function Sparkline({ values, color = '#D4AF37', width = 120, height = 32 }) {
  if (!values?.length) return null
  const min = Math.min(...values), max = Math.max(...values)
  const range = max - min || 1
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width
    const y = height - ((v - min) / range) * height
    return `${x},${y}`
  }).join(' ')
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  )
}

export default function BrainInsightsPanel() {
  const storeInsights = useAppStore((s) => s.brainInsights)
  const [insights, setInsights] = useState(storeInsights)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])

  // WS broadcast (every 5s) populates brainInsights in store — sync local state from store
  useEffect(() => {
    if (storeInsights && Object.keys(storeInsights).length > 0) {
      setInsights(storeInsights)
      setLoading(false)
      setError('')
    }
  }, [storeInsights])

  useEffect(() => {
    if (storeInsights?.performance_metrics?.avg_confidence != null)
      setHistory(h => [...h.slice(-19), storeInsights.performance_metrics.avg_confidence])
  }, [storeInsights])

  // One-time initial fetch if store is empty
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/brain/insights`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (!cancelled) { setInsights(data || {}); setLoading(false) }
      } catch (e) {
        if (!cancelled) { setInsights(storeInsights || {}); setError('Brain insights unavailable'); setLoading(false) }
      }
    })()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const metrics = insights?.performance_metrics || {}
  const strategies = insights?.learned_strategies || []
  const improvements = insights?.recent_improvements || []
  const events = insights?.recent_learning_events || []

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>BRAIN INSIGHTS</h2>
      <div className="font-mono text-[10px] mb-2" style={{ color: error ? 'var(--warning)' : 'var(--text-muted)' }}>
        {loading ? 'Loading brain insights…' : (error || `Brain ${insights?.active ? 'active' : 'unavailable'}`)}
      </div>
      <div className="grid grid-cols-2 gap-2 mb-2">
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>SUCCESS RATE</div>
          <div style={{ color: 'var(--gold)' }}>{asPercent(metrics.success_rate)}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>AVG CONFIDENCE</div>
          <div style={{ color: 'var(--gold)' }}>{asPercent(metrics.avg_confidence)}</div>
          <Sparkline values={history} />
        </TertiaryPanel>
      </div>

      <div className="font-mono text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
        LEARNED STRATEGIES
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '95px' }}>
        {strategies.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No learned strategies yet.</div>
        ) : strategies.slice(0, 4).map((strategy) => (
          <TertiaryPanel key={`${strategy.intent}-${strategy.strategy}`} className="p-2 font-mono text-[10px] flex justify-between gap-2">
            <span style={{ color: 'var(--text-secondary)' }}>{strategy.strategy}</span>
            <span style={{ color: 'var(--gold)' }}>{asPercent(strategy.success_rate)}</span>
          </TertiaryPanel>
        ))}
      </div>

      <div className="font-mono text-[10px] mt-2 mb-1" style={{ color: 'var(--text-muted)' }}>
        RECENT IMPROVEMENTS
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '80px' }}>
        {improvements.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No improvements logged yet.</div>
        ) : improvements.slice(0, 3).map((item) => (
          <TertiaryPanel key={`${item.task_id}-${item.ts}`} className="p-2 font-mono text-[10px]">
            <div style={{ color: 'var(--text-secondary)' }}>{item.improvement}</div>
            <div style={{ color: 'var(--text-muted)' }}>{item.strategy} • {item.intent}</div>
          </TertiaryPanel>
        ))}
      </div>

      <div className="font-mono text-[10px] mt-2 mb-1" style={{ color: 'var(--text-muted)' }}>
        RECENT LEARNING EVENTS
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '80px' }}>
        {events.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No learning events yet.</div>
        ) : events.slice(0, 3).map((event, index) => (
          <TertiaryPanel key={`${event.ts || 'ts'}-${event.event || 'event'}-${index}`} className="p-2 font-mono text-[10px]">
            <div style={{ color: 'var(--text-secondary)' }}>{(event.event || 'update').replaceAll('_', ' ')}</div>
            <div style={{ color: 'var(--text-muted)' }}>{event.skill || event.goal_type || 'brain'}</div>
          </TertiaryPanel>
        ))}
      </div>
    </article>
  )
}
