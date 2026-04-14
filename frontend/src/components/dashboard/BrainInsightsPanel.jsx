import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'
import { API_URL } from '../../config/api'

const API_BASE = API_URL

function asPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

export default function BrainInsightsPanel() {
  const storeInsights = useAppStore((s) => s.brainInsights)
  const [insights, setInsights] = useState(storeInsights)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    const loadInsights = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/brain/insights`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (cancelled) return
        setInsights(data || {})
        setError('')
      } catch (e) {
        if (cancelled) return
        console.error('Failed to load brain insights', e)
        setInsights(storeInsights || {})
        setError('Brain insights unavailable')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadInsights()
    const timer = setInterval(loadInsights, 3000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [storeInsights])

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
