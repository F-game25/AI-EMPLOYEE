import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import './MobileNav.css'

const PRIMARY_NAV = [
  {
    id: 'nexus',
    label: 'Home',
    icon: (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="8" cy="8" r="2.5"/>
        <path d="M8 1.5v2.4M8 12.1v2.4M2.5 8h2.4M11.1 8h2.4M4.2 4.2l1.7 1.7M10.1 10.1l1.7 1.7M11.8 4.2l-1.7 1.7M4.9 10.1l-1.7 1.7"/>
      </svg>
    ),
  },
  {
    id: 'agents',
    label: 'Agents',
    icon: (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="4" cy="5" r="1.5"/><circle cx="12" cy="5" r="1.5"/>
        <path d="M4 6.5v2c0 1 1.3 2 2 2h4c.7 0 2-1 2-2v-2"/>
        <circle cx="8" cy="13" r="1.5" fill="currentColor"/>
      </svg>
    ),
  },
  {
    id: 'tasks',
    label: 'Tasks',
    icon: (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2" width="12" height="12" rx="1"/>
        <path d="M2 6h12M5 10h6"/>
      </svg>
    ),
  },
  {
    id: 'economy',
    label: 'Economy',
    icon: (
      <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 8c0-3.3 2.7-6 6-6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z"/>
        <path d="M8 5v6M6 7h4"/>
      </svg>
    ),
  },
]

const MORE_NAV = [
  { id: 'cognition',      label: 'Cognition' },
  { id: 'memory',         label: 'Memory' },
  { id: 'workflows',      label: 'Workflows' },
  { id: 'neural-graph',   label: 'Neural Graph' },
  { id: 'knowledge',      label: 'Knowledge' },
  { id: 'research',       label: 'Research' },
  { id: 'recon',          label: 'Recon' },
  { id: 'security',       label: 'Security' },
  { id: 'approvals',      label: 'Approvals' },
  { id: 'proof',          label: 'Proof Center' },
  { id: 'setup',          label: 'Setup Center' },
  { id: 'api-catalog',    label: 'API Catalog' },
  { id: 'user-views',     label: 'User Views' },
  { id: 'settings',       label: 'Settings' },
]

export default function MobileNav() {
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [moreOpen, setMoreOpen] = useState(false)

  const navigate = (id) => {
    setActiveSection(id)
    setMoreOpen(false)
  }

  return (
    <>
      {moreOpen && (
        <div className="nx-morenav-sheet">
          <div className="nx-morenav-sheet__handle" onClick={() => setMoreOpen(false)} />
          <div className="nx-morenav-sheet__grid">
            {MORE_NAV.map(({ id, label }) => (
              <button
                key={id}
                className={`nx-morenav-sheet__item ${activeSection === id ? 'nx-morenav-sheet__item--active' : ''}`}
                onClick={() => navigate(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
      {moreOpen && (
        <div className="nx-morenav-overlay" onClick={() => setMoreOpen(false)} />
      )}

      <nav className="nx-mobnav" aria-label="Mobile navigation">
        {PRIMARY_NAV.map(({ id, label, icon }) => (
          <button
            key={id}
            className={`nx-mobnav__item ${activeSection === id ? 'nx-mobnav__item--active' : ''}`}
            onClick={() => navigate(id)}
          >
            <span className="nx-mobnav__icon">{icon}</span>
            <span className="nx-mobnav__label">{label}</span>
          </button>
        ))}

        <button
          className={`nx-mobnav__item ${moreOpen ? 'nx-mobnav__item--active' : ''}`}
          onClick={() => setMoreOpen(v => !v)}
          aria-expanded={moreOpen}
        >
          <span className="nx-mobnav__icon">
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="4" cy="8" r="1.2" fill="currentColor"/>
              <circle cx="8" cy="8" r="1.2" fill="currentColor"/>
              <circle cx="12" cy="8" r="1.2" fill="currentColor"/>
            </svg>
          </span>
          <span className="nx-mobnav__label">More</span>
        </button>
      </nav>
    </>
  )
}
