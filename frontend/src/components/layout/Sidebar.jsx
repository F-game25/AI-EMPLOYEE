import { useAppStore } from '../../store/appStore'

const NAV_ITEMS = [
  { id: 'dashboard', icon: '◆', label: 'Dashboard' },
  { id: 'ai-control', icon: '◉', label: 'AI Control' },
  { id: 'neural-brain', icon: '🧠', label: 'Neural Brain' },
  { id: 'operations', icon: '▣', label: 'Operations' },
  { id: 'agents', icon: '⬡', label: 'Agents' },
  { id: 'control-center', icon: '🛡', label: 'Control Center' },
  { id: 'learning-ladder', icon: '📈', label: 'Learning Ladder' },
  { id: 'system', icon: '⚙', label: 'System' },
  { id: 'voice', icon: '◈', label: 'Voice' },
]

export default function Sidebar() {
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const wsConnected = useAppStore(s => s.wsConnected)

  return (
    <nav className="sidebar" role="navigation" aria-label="Main navigation">
      {/* Brand */}
      <div style={{ padding: 'var(--space-4) var(--space-4) var(--space-5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{ color: 'var(--gold)', fontSize: '18px', fontWeight: 500 }}>◈</span>
          <span className="sidebar-brand-text" style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: 500, letterSpacing: '-0.02em' }}>
            AI Employee
          </span>
        </div>
      </div>

      {/* Navigation */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav-item${activeSection === item.id ? ' sidebar-nav-item--active' : ''}`}
            onClick={() => setActiveSection(item.id)}
            aria-current={activeSection === item.id ? 'page' : undefined}
          >
            <span className="sidebar-nav-icon">{item.icon}</span>
            <span className="sidebar-nav-label">{item.label}</span>
          </button>
        ))}
      </div>

      {/* Footer — connection status */}
      <div style={{
        padding: 'var(--space-4)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
      }}>
        <span
          className={`status-dot ${wsConnected ? 'status-dot--active status-dot--pulse' : 'status-dot--error'}`}
        />
        <span className="sidebar-nav-label" style={{
          fontSize: '12px',
          color: wsConnected ? 'var(--text-secondary)' : 'var(--error)',
        }}>
          {wsConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
    </nav>
  )
}
