import { useMemo } from 'react'
import { useEventFeedStore } from '../../store/eventFeedStore'
import './QuickActions.css'

const ACTIONS = [
  { key: 'new-task',     label: 'NEW TASK',      icon: '+' },
  { key: 'spawn-agent',  label: 'SPAWN AGENT',   icon: '+' },
  { key: 'deploy-model', label: 'DEPLOY MODEL',  icon: '▢' },
  { key: 'open-ws',      label: 'OPEN WORKSPACE',icon: '→' },
  { key: 'system-scan',  label: 'SYSTEM SCAN',   icon: '↻' },
  { key: 'optimize',     label: 'OPTIMIZE NOW',  icon: '▲' },
  { key: 'emergency',    label: 'EMERGENCY STOP',icon: '■', danger: true },
  { key: 'reports',      label: 'VIEW REPORTS',  icon: '▤' },
]

function dispatch(key) {
  window.dispatchEvent(new CustomEvent(`nx:action:${key}`))
}

export default function QuickActions() {
  const events = useEventFeedStore(s => s.events) || []

  const counts = useMemo(() => {
    const out = { critical: 0, warning: 0, info: 0, success: 0 }
    for (const e of events) {
      const lvl = (e.level || e.severity || '').toLowerCase()
      if (lvl === 'critical' || lvl === 'error') out.critical++
      else if (lvl === 'warning' || lvl === 'warn') out.warning++
      else if (lvl === 'success' || lvl === 'ok') out.success++
      else out.info++
    }
    return out
  }, [events])

  return (
    <section className="qa-panel" aria-label="Quick Actions">
      <header className="qa-panel__head">
        <span className="qa-panel__title">QUICK ACTIONS</span>
        <button type="button" className="qa-panel__viewall" onClick={() => dispatch('view-all')}>
          VIEW ALL ›
        </button>
      </header>

      <div className="qa-panel__counts" role="list">
        <div className="qa-count qa-count--critical" role="listitem">
          <span className="qa-count__icon" aria-hidden="true">⚠</span>
          <span className="qa-count__value">{counts.critical}</span>
          <span className="qa-count__label">CRITICAL</span>
        </div>
        <div className="qa-count qa-count--warning" role="listitem">
          <span className="qa-count__icon" aria-hidden="true">⚠</span>
          <span className="qa-count__value">{counts.warning}</span>
          <span className="qa-count__label">WARNING</span>
        </div>
        <div className="qa-count qa-count--info" role="listitem">
          <span className="qa-count__icon" aria-hidden="true">ℹ</span>
          <span className="qa-count__value">{counts.info}</span>
          <span className="qa-count__label">INFO</span>
        </div>
        <div className="qa-count qa-count--success" role="listitem">
          <span className="qa-count__icon" aria-hidden="true">✓</span>
          <span className="qa-count__value">{counts.success}</span>
          <span className="qa-count__label">SUCCESS</span>
        </div>
      </div>

      <div className="qa-panel__actions">
        {ACTIONS.map(a => (
          <button
            key={a.key}
            type="button"
            className={`qa-btn ${a.danger ? 'qa-btn--danger' : ''}`}
            onClick={() => dispatch(a.key)}
          >
            <span className="qa-btn__icon" aria-hidden="true">{a.icon}</span>
            <span className="qa-btn__label">{a.label}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
