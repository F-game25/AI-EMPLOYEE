import { useTaskStore } from '../../store/taskStore'
import './TaskPipeline.css'

// TODO: backend should broadcast `tasks:pipeline` with this shape:
//   { incoming: [], planning: [], executing: [], validating: [], completed: [] }
// where each item is { id, name, priority: 'HIGH'|'MED'|'LOW' }.

const COLUMNS = [
  { key: 'incoming',   label: 'INCOMING',   accent: 'incoming' },
  { key: 'planning',   label: 'PLANNING',   accent: 'planning' },
  { key: 'executing',  label: 'EXECUTING',  accent: 'executing' },
  { key: 'validating', label: 'VALIDATING', accent: 'validating' },
  { key: 'completed',  label: 'COMPLETED',  accent: 'completed' },
]

function PriorityPill({ value }) {
  const v = String(value || 'MED').toUpperCase()
  return <span className={`tp-pill tp-pill--${v.toLowerCase()}`}>{v}</span>
}

function Column({ col, items }) {
  const visible = items.slice(0, 4)
  const more = Math.max(0, items.length - visible.length)
  const onTaskClick = (item) => {
    window.dispatchEvent(new CustomEvent('nx:task:open', { detail: { id: item.id, col: col.key } }))
  }

  return (
    <div className={`tp-col tp-col--${col.accent}`}>
      <header className="tp-col__head">
        <span className="tp-col__label">{col.label}</span>
        <span className="tp-col__count">{items.length}</span>
      </header>
      <ul className="tp-col__list">
        {visible.length === 0 && <li className="tp-col__empty">—</li>}
        {visible.map((item, i) => (
          <li key={item.id || i} className="tp-task" onClick={() => onTaskClick(item)}>
            <span className="tp-task__name">{item.name || item.title || item.id || 'Task'}</span>
            <PriorityPill value={item.priority} />
          </li>
        ))}
      </ul>
      {more > 0 && <div className="tp-col__more">+{more} more</div>}
    </div>
  )
}

export default function TaskPipeline() {
  const pipeline = useTaskStore(s => s.pipeline) || {}

  return (
    <section className="tp-panel" aria-label="Task Pipeline">
      <header className="tp-panel__head">
        <span className="tp-panel__title">TASK PIPELINE</span>
        <span className="tp-panel__chev" aria-hidden="true">›</span>
      </header>
      <div className="tp-panel__cols">
        {COLUMNS.map(col => (
          <Column key={col.key} col={col} items={pipeline[col.key] || []} />
        ))}
      </div>
    </section>
  )
}
