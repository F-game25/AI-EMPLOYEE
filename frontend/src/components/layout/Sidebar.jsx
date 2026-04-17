import { NavLink } from 'react-router-dom'
import { useAppStore } from '../../store/appStore'

const NAV_SECTIONS = [
  {
    label: 'Core',
    items: [
      { to: '/dashboard', icon: '◆', label: 'Dashboard' },
      { to: '/command-center', icon: '◉', label: 'Command Center' },
      { to: '/agents', icon: '⬡', label: 'Agents' },
    ],
  },
  {
    label: 'Modes',
    items: [
      { to: '/modes/blacklight', icon: '◈', label: 'Blacklight' },
      { to: '/modes/ascend-forge', icon: '🔺', label: 'Ascend Forge' },
      { to: '/modes/money', icon: '💰', label: 'Money Mode' },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/memory', icon: '🧠', label: 'Memory' },
      { to: '/health', icon: '♥', label: 'Health' },
      { to: '/system', icon: '⚙', label: 'System' },
      { to: '/settings', icon: '▣', label: 'Settings' },
    ],
  },
]

export default function Sidebar() {
  const wsConnected = useAppStore(s => s.wsConnected)

  return (
    <nav className="sidebar" role="navigation" aria-label="Main navigation">
      {/* Brand */}
      <div style={{ padding: 'var(--space-4) var(--space-4) var(--space-5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{ color: 'var(--gold)', fontSize: '18px', fontWeight: 500 }}>◈</span>
          <span className="sidebar-brand-text" style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: 500, letterSpacing: '-0.02em' }}>
            AI Employee OS
          </span>
        </div>
      </div>

      {/* Navigation */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', overflowY: 'auto' }}>
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <div style={{
              fontSize: '10px',
              fontWeight: 600,
              letterSpacing: '0.08em',
              color: 'var(--text-dim)',
              textTransform: 'uppercase',
              padding: '0 var(--space-4)',
              marginBottom: '4px',
            }}>
              {section.label}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `sidebar-nav-item${isActive ? ' sidebar-nav-item--active' : ''}`
                  }
                  aria-current={({ isActive }) => isActive ? 'page' : undefined}
                >
                  <span className="sidebar-nav-icon">{item.icon}</span>
                  <span className="sidebar-nav-label">{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
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
