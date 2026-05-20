import { useTaskStore } from '../../store/taskStore'
import './CurrentObjective.css'

export default function CurrentObjective() {
  const objective = useTaskStore(s => s.objective)

  if (!objective || !objective.title) {
    return (
      <div className="co-band co-band--empty">
        <span className="co-band__icon" aria-hidden="true">⚡</span>
        <span className="co-band__label">CURRENT OBJECTIVE</span>
        <span className="co-band__title-empty">No active objective</span>
      </div>
    )
  }

  const priority = String(objective.priority || 'MED').toUpperCase()
  const deadline = objective.deadline || '—'
  const progress = typeof objective.progress === 'number' ? Math.round(objective.progress) : null

  return (
    <div className="co-band">
      <span className="co-band__icon" aria-hidden="true">⚡</span>
      <span className="co-band__label">CURRENT OBJECTIVE</span>
      <span className="co-band__chev" aria-hidden="true">›</span>
      <span className="co-band__title">{objective.title}</span>
      <span className="co-band__stats">
        <span className="co-band__stat">
          <span className="co-band__stat-key">Priority:</span>
          <span className={`co-band__stat-val co-band__stat-val--prio-${priority.toLowerCase()}`}>{priority}</span>
        </span>
        <span className="co-band__stat">
          <span className="co-band__stat-key">Deadline:</span>
          <span className="co-band__stat-val co-band__stat-val--gold">{deadline}</span>
        </span>
        {progress !== null && (
          <span className="co-band__stat">
            <span className="co-band__stat-key">Progress:</span>
            <span className="co-band__stat-val co-band__stat-val--green">{progress}%</span>
          </span>
        )}
      </span>
    </div>
  )
}
