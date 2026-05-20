import { useAppStore } from '../../store/appStore'
import './QuickActionsPanel.css'

const ACTIONS = [
  { icon: '+', label: 'NEW TASK',       section: 'workspace',  danger: false },
  { icon: '⊕', label: 'SPAWN AGENT',   section: 'agents',     danger: false },
  { icon: '↑', label: 'DEPLOY MODEL',  section: 'models',     danger: false },
  { icon: '⊞', label: 'WORKSPACE',     section: 'workspace',  danger: false },
  { icon: '⚡', label: 'SYSTEM SCAN',   section: 'audit',      danger: false },
  { icon: '⛔', label: 'EMRG STOP',    section: null,         danger: true  },
]

export default function QuickActionsPanel() {
  const setActiveSection = useAppStore(s => s.setActiveSection)

  const handleAction = (action) => {
    if (action.danger) {
      if (!window.confirm('Confirm Emergency Stop?')) return
      fetch('/api/system/stop', { method: 'POST' }).catch(() => {})
      return
    }
    if (action.section) setActiveSection(action.section)
  }

  return (
    <div className="qa-panel">
      <div className="qa-panel__header">QUICK ACTIONS</div>
      <div className="qa-panel__grid">
        {ACTIONS.map(a => (
          <button
            key={a.label}
            className={`qa-btn ${a.danger ? 'qa-btn--danger' : ''}`}
            onClick={() => handleAction(a)}
            title={a.label}
          >
            <span className="qa-btn__icon">{a.icon}</span>
            <span className="qa-btn__label">{a.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
