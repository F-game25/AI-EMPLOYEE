import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/', icon: '◈', label: 'Dashboard' },
  { to: '/forge', icon: '⚗', label: 'Ascend Forge' },
  { to: '/money', icon: '💰', label: 'Money Mode' },
  { to: '/blacklight', icon: '🔒', label: 'Blacklight' },
  { to: '/doctor', icon: '🩺', label: 'Doctor' },
  { to: '/live', icon: '📡', label: 'Live Feedback' },
  { to: '/fairness', icon: '⚖', label: 'Fairness' },
  { to: '/governance', icon: '🏛', label: 'Governance' },
  { to: '/settings', icon: '⚙', label: 'Settings' },
]

export function Sidebar() {
  return (
    <nav className="sidebar" style={{
      background: 'var(--bg-panel)',
      borderRight: 'var(--border-gold)',
      padding: '16px 0',
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
    }}>
      <div className="nav-label" style={{ padding: '0 16px 12px', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2 }}>
        NAVIGATION
      </div>
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === '/'}
          className={({ isActive }) => isActive ? 'nav-active' : ''}
          style={({ isActive }) => ({
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 16px',
            textDecoration: 'none',
            fontFamily: 'var(--font-body)',
            fontSize: 13,
            color: isActive ? 'var(--gold)' : 'var(--text-secondary)',
            borderLeft: isActive ? '2px solid var(--gold)' : '2px solid transparent',
            background: isActive ? 'rgba(212,175,55,0.06)' : 'transparent',
            transition: 'all 0.2s ease',
          })}
        >
          <span style={{ fontSize: 15, width: 20, textAlign: 'center' }}>{n.icon}</span>
          <span className="nav-label">{n.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
