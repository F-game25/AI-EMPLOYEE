import { useEffect, useMemo, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { API_URL } from '../../config/api'

const BASE = API_URL

function MetricCard({ label, value }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-3)' }}>
      <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{label}</div>
      <div style={{ color: 'var(--text-primary)', fontSize: '17px', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

export default function ObservabilityDashboard() {
  const observability = useAppStore((s) => s.observability)
  const setObservability = useAppStore((s) => s.setObservability)
  const activityFeed = useAppStore((s) => s.activityFeed)
  const agents = useAppStore((s) => s.agents)
  const workflowState = useAppStore((s) => s.workflowState)

  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${BASE}/api/observability/snapshot`, { signal: controller.signal })
        const data = await res.json()
        setObservability(data)
      } catch {
        // WebSocket snapshot continues updating store.
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 3000)
    return () => {
      clearInterval(interval)
      controller.abort()
    }
  }, [setObservability])

  const metrics = observability?.metrics || {}
  const health = observability?.system_health || {}
  const autoFixLog = observability?.auto_fix_log || []
  const events = observability?.events || []

  const queueViz = useMemo(() => ({
    pending: observability?.queue_visualizer?.pending ?? workflowState?.runs?.filter((run) => run.status === 'pending').length ?? 0,
    processing: observability?.queue_visualizer?.processing ?? workflowState?.runs?.filter((run) => run.status === 'running').length ?? 0,
  }), [observability, workflowState])

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
        <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)' }}>Observability Dashboard</div>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{loading ? 'Refreshing…' : (observability?.updated_at || 'Live')}</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <MetricCard label="System Health" value={health.status || 'unknown'} />
        <MetricCard label="Uptime" value={`${Math.round(Number(health.uptime || 0))}s`} />
        <MetricCard label="Errors/min" value={metrics.errors_per_minute ?? 0} />
        <MetricCard label="Tasks/min" value={metrics.tasks_per_minute ?? 0} />
        <MetricCard label="Latency" value={`${metrics.latency_ms ?? 0} ms`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-3)' }}>
        <div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>Live Activity Feed</div>
          <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
            {(activityFeed.length ? activityFeed : (observability?.activity_feed || [])).slice(0, 20).map((item, idx) => (
              <div key={item.id || idx} style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--border-subtle)', fontSize: '12px', color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-muted)', marginRight: '8px' }}>{item.ts ? new Date(item.ts).toLocaleTimeString() : ''}</span>
                {item.notes || item.event_type || 'event'}
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
            <div className="ds-card" style={{ padding: 'var(--space-3)' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>Agent Grid</div>
              {(observability?.agent_grid || agents || []).slice(0, 12).map((agent, idx) => (
                <div key={agent.id || idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-secondary)' }}>
                  <span>{agent.name || agent.id}</span>
                  <span style={{ color: agent.status === 'error' ? 'var(--error)' : agent.status === 'working' ? 'var(--warning)' : 'var(--success)' }}>
                    {agent.status || 'idle'}
                  </span>
                </div>
              ))}
            </div>

            <div className="ds-card" style={{ padding: 'var(--space-3)' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>Queue Visualizer</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Pending: {queueViz.pending}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Processing: {queueViz.processing}</div>
              <div style={{ height: '8px', background: 'var(--bg-card)', borderRadius: '999px', overflow: 'hidden', marginTop: 'var(--space-2)' }}>
                <div style={{ width: `${Math.min(100, (queueViz.processing / Math.max(queueViz.pending + queueViz.processing, 1)) * 100)}%`, height: '100%', background: 'var(--gold)' }} />
              </div>
            </div>
          </div>
        </div>

        <div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>Auto-Fix Log</div>
          <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-2)' }}>
            {autoFixLog.length === 0 ? (
              <div style={{ padding: 'var(--space-2)', color: 'var(--text-muted)', fontSize: '12px' }}>No auto-fixes recorded.</div>
            ) : autoFixLog.slice(0, 20).map((row, idx) => (
              <div key={row.id || idx} style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-primary)' }}>{row.issue || 'issue'}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.fix || row.status}</div>
              </div>
            ))}
          </div>

          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>Event Stream</div>
          <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
            {events.slice(0, 25).map((event, idx) => (
              <div key={event.id || idx} style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                <div style={{ color: 'var(--text-primary)' }}>{event.event_type}</div>
                <div style={{ color: 'var(--text-muted)' }}>{event.payload?.task_id || event.trace_id || ''}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
