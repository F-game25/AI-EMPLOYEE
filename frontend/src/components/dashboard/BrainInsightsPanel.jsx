import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'

function asPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

export default function BrainInsightsPanel() {
  const insights = useAppStore((s) => s.brainInsights)
  const metrics = insights?.performance_metrics || {}
  const strategies = insights?.learned_strategies || []
  const improvements = insights?.recent_improvements || []

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>BRAIN INSIGHTS</h2>
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
    </article>
  )
}
