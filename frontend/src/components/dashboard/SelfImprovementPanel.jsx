import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'
import { API_URL } from '../../config/api'

const API_BASE = API_URL

function asPct(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

export default function SelfImprovementPanel() {
  const storeSI = useAppStore((s) => s.selfImprovement)
  const setSI = useAppStore((s) => s.setSelfImprovement)
  const [data, setData] = useState(storeSI)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/self-improvement/status`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (cancelled) return
        setData(json || {})
        setSI(json || {})
        setError('')
      } catch (e) {
        if (cancelled) return
        console.error('Failed to load self-improvement status', e)
        setData(storeSI || {})
        setError('Self-improvement data unavailable')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const timer = setInterval(load, 5000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [storeSI, setSI])

  const events = data?.recent_events || []
  const failures = data?.top_failure_causes || []
  const isActive = data?.active || false
  const isSimulated = data?.data_source === 'simulated'

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>
        SELF-IMPROVEMENT PIPELINE
      </h2>

      {isSimulated && (
        <div
          className="font-mono mb-2 px-2 py-1 rounded"
          style={{ fontSize: '9px', color: 'var(--warning)', background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.15)' }}
        >
          ⚠ DEGRADED — showing cached data (no live backend)
        </div>
      )}

      <div className="font-mono text-[10px] mb-2" style={{ color: error ? 'var(--warning)' : 'var(--text-muted)' }}>
        {loading ? 'Loading pipeline status…' : (error || (isActive ? '● Pipeline active' : '○ Pipeline idle'))}
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-3 gap-2 mb-2">
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>QUEUE</div>
          <div style={{ color: 'var(--gold)' }}>{data?.queue_depth ?? 0}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>DEPLOYED</div>
          <div style={{ color: 'var(--gold)' }}>{data?.deployed ?? 0}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>PROCESSED</div>
          <div style={{ color: 'var(--gold)' }}>{data?.total_tasks_processed ?? 0}</div>
        </TertiaryPanel>
      </div>

      {/* Rates */}
      <div className="grid grid-cols-2 gap-2 mb-2">
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>PASS RATE</div>
          <div style={{ color: 'var(--gold)' }}>{asPct(data?.pass_rate)}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>APPROVAL</div>
          <div style={{ color: 'var(--gold)' }}>{asPct(data?.approval_ratio)}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>ROLLBACK</div>
          <div style={{ color: 'var(--gold)' }}>{asPct(data?.rollback_ratio)}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>REJECTED</div>
          <div style={{ color: 'var(--gold)' }}>{data?.rejected ?? 0}</div>
        </TertiaryPanel>
      </div>

      {/* Top failure causes */}
      <div className="font-mono text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
        TOP FAILURE CAUSES
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '70px' }}>
        {failures.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No failures recorded.</div>
        ) : failures.slice(0, 4).map((f) => (
          <TertiaryPanel key={f.cause} className="p-2 font-mono text-[10px] flex justify-between gap-2">
            <span style={{ color: 'var(--text-secondary)' }}>{(f.cause || '').replaceAll('_', ' ')}</span>
            <span style={{ color: 'var(--warning)' }}>{f.count}</span>
          </TertiaryPanel>
        ))}
      </div>

      {/* Recent events */}
      <div className="font-mono text-[10px] mt-2 mb-1" style={{ color: 'var(--text-muted)' }}>
        RECENT PIPELINE EVENTS
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '80px' }}>
        {events.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No pipeline events yet.</div>
        ) : events.slice(0, 5).map((ev, idx) => (
          <TertiaryPanel key={`${ev.event}-${ev.task_id || idx}`} className="p-2 font-mono text-[10px]">
            <div style={{ color: 'var(--text-secondary)' }}>{(ev.event || 'event').replaceAll('_', ' ')}</div>
            <div style={{ color: 'var(--text-muted)' }}>{ev.task_id ? `task: ${ev.task_id.slice(0, 8)}…` : ''}</div>
          </TertiaryPanel>
        ))}
      </div>
    </article>
  )
}
