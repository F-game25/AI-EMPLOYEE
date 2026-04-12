import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'

function asPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

export default function BrainInsightsPanel() {
  const insights = useAppStore((s) => s.brainInsights)
  const brainStatus = useAppStore((s) => s.brainStatus)
  const brainActivity = useAppStore((s) => s.brainActivity)
  const metrics = insights?.performance_metrics || {}
  const strategies = insights?.learned_strategies || []
  const improvements = insights?.recent_improvements || []
  const activityItems = brainActivity?.items || []
  const activeState = (brainStatus?.status || '').toLowerCase() === 'active' || brainStatus?.active

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>BRAIN INSIGHTS</h2>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>STATUS</div>
          <div style={{ color: activeState ? 'var(--success)' : 'var(--error)' }}>
            {activeState ? 'ACTIVE' : 'INACTIVE'}
          </div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>MEMORY SIZE</div>
          <div style={{ color: 'var(--gold)' }}>{(brainStatus?.memory_size || 0).toLocaleString()}</div>
        </TertiaryPanel>
        <TertiaryPanel className="p-2 font-mono text-[10px]">
          <div style={{ color: 'var(--text-muted)' }}>LAST ACTIVITY</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            {brainStatus?.last_update ? new Date(brainStatus.last_update).toLocaleTimeString() : '—'}
          </div>
        </TertiaryPanel>
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
        BRAIN ACTIVITY FEED
      </div>
      <div className="space-y-1 overflow-y-auto" style={{ maxHeight: '88px' }}>
        {activityItems.length === 0 ? (
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>No activity yet.</div>
        ) : activityItems.slice(0, 4).map((item) => (
          <TertiaryPanel key={`${item.task_id}-${item.ts}-${item.type}-${item.detail || ''}`} className="p-2 font-mono text-[10px]">
            <div style={{ color: 'var(--text-secondary)' }}>{item.type} • {item.strategy || item.intent || 'general'}</div>
            <div style={{ color: 'var(--text-muted)' }}>{item.detail || 'Brain activity update'}</div>
          </TertiaryPanel>
        ))}
      </div>
    </article>
  )
}
