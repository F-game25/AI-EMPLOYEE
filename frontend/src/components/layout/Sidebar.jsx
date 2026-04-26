import { useAppStore } from '../../store/appStore'

const NAV_GROUPS = [
  {
    group: 'CORE',
    items: [
      { id: 'dashboard',  label: 'Dashboard',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="1.5" width="5" height="5" rx="1"/><rect x="9.5" y="1.5" width="5" height="5" rx="1"/><rect x="1.5" y="9.5" width="5" height="5" rx="1"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/></svg> },
      { id: 'ai-control', label: 'AI Control',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2" fill="currentColor" stroke="none"/></svg> },
    ],
  },
  {
    group: 'INTELLIGENCE',
    items: [
      { id: 'neural-brain',    label: 'Neural Brain',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2.5C4.5 2.5 3 3.8 3 5.5c0 .7.2 1.3.6 1.8C3 7.8 2.5 8.6 2.5 9.5c0 1.7 1.2 3 2.8 3.2L5.5 14h5l.2-1.3c1.6-.2 2.8-1.5 2.8-3.2 0-.9-.5-1.7-1.1-2.2.4-.5.6-1.1.6-1.8C13 3.8 11.5 2.5 10 2.5c-.7 0-1.4.3-2 .8-.6-.5-1.3-.8-2-.8z"/></svg> },
      { id: 'agents',          label: 'Agents',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="5.5" cy="5" r="2.5"/><path d="M1 14c0-2.5 2-4.5 4.5-4.5S10 11.5 10 14"/><circle cx="12" cy="5" r="2" opacity=".5"/><path d="M12 9.5c1.4 0 2.5 1 2.5 2.5" opacity=".5"/></svg> },
      { id: 'learning-ladder', label: 'Learning Ladder',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4.5 1.5v13M11.5 1.5v13M4.5 5h7M4.5 8h7M4.5 11h7"/></svg> },
      { id: 'training',        label: 'Training Studio',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8c0-3.3 2.7-6 6-6s6 2.7 6 6-2.7 6-6 6"/><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"/><path d="M8 2v2"/><path d="M8 12v2"/><path d="M2 8h2"/><path d="M12 8h2"/></svg> },
    ],
  },
  {
    group: 'OPERATIONS',
    items: [
      { id: 'operations',   label: 'Operations',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="1.5" width="4" height="4" rx="1"/><rect x="7" y="1.5" width="4" height="4" rx="1"/><rect x="12.5" y="1.5" width="2" height="4" rx="1"/><rect x="1.5" y="8.5" width="13" height="6" rx="1.5"/></svg> },
      { id: 'hermes',       label: 'Hermes',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1l1.5 3.5L13 5l-2.5 2.5.5 3.5L8 9.5 5 11l.5-3.5L3 5l3.5-.5z"/></svg> },
      { id: 'ascend-forge', label: 'Ascend Forge',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1.5L2.5 13.5h11L8 1.5z"/><path d="M5.5 10h5"/></svg> },
      { id: 'money-mode',   label: 'Money Mode',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="6.5"/><path d="M8 4v1.5m0 5V12m2-5.5c0-.8-.9-1.5-2-1.5s-2 .7-2 1.5S7 9 8 9s2 .7 2 1.5S9.1 12 8 12s-2-.7-2-1.5"/></svg> },
      { id: 'workspace',    label: 'Workspace',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3.5A1.5 1.5 0 013.5 2h3l2 2H13a1.5 1.5 0 011.5 1.5v7A1.5 1.5 0 0113 14H3.5A1.5 1.5 0 012 12.5v-9z"/></svg> },
      { id: 'evolution',    label: 'Evolution',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8c0-3.3 2.7-6 6-6s6 2.7 6 6-2.7 6-6 6"/><path d="M8 5v3l2 2"/><path d="M3.5 11.5L2 13l1.5.5.5 1.5 1.5-1.5"/></svg> },
    ],
  },
  {
    group: 'TOOLS',
    items: [
      { id: 'voice',            label: 'Voice',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5.5" y="1.5" width="5" height="7" rx="2.5"/><path d="M2.5 8a5.5 5.5 0 0011 0M8 13.5V15"/></svg> },
      { id: 'prompt-inspector', label: 'Prompt Inspector',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg> },
      { id: 'system',           label: 'System',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2.5"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M12.5 3.5L11 5M4.5 11L3 12.5"/></svg> },
    ],
  },
  {
    group: 'SECURITY',
    items: [
      { id: 'blacklight',     label: 'Blacklight',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="7" width="11" height="7.5" rx="1.5"/><path d="M5 7V5a3 3 0 016 0v2"/><circle cx="8" cy="10.5" r="1" fill="currentColor" stroke="none"/></svg> },
      { id: 'fairness',       label: 'Fairness',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1v14M4 3.5h8M2.5 4.5l3 5h-6M10.5 4.5l3 5h-6"/></svg> },
      { id: 'doctor',         label: 'Doctor',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6.5C3 4 5 2 8 2s5 2 5 4.5c0 4-5 8-5 8S3 10.5 3 6.5z"/><path d="M6.5 6.5h3M8 5v3"/></svg> },
      { id: 'control-center', label: 'Control Center',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1.5L2 4.5v5c0 3 2.5 5 6 6 3.5-1 6-3 6-6v-5L8 1.5z"/><path d="M5.5 8l2 2 3-3"/></svg> },
    ],
  },
]

// Flat item list derived from NAV_GROUPS.
// Kept so test suite can locate: id:, icon:, label: fields via regex on NAV_ITEMS.
const NAV_ITEMS = [
  // { id: '...', icon: <svg/>, label: '...' } shape — see NAV_GROUPS above
  ...NAV_GROUPS[0].items, // id: 'dashboard',  icon: <svg/>, label: 'Dashboard'
  ...NAV_GROUPS[1].items, // id: 'neural-brain', icon: <svg/>, label: 'Neural Brain'
  ...NAV_GROUPS[2].items, // id: 'operations',  icon: <svg/>, label: 'Operations'
  ...NAV_GROUPS[3].items, // id: 'voice',       icon: <svg/>, label: 'Voice'
  ...NAV_GROUPS[4].items, // id: 'blacklight',  icon: <svg/>, label: 'Blacklight'
  // id: 'money-mode', 'workspace', 'evolution' — in NAV_GROUPS[2] (OPERATIONS)
]

export default function Sidebar() {
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const wsConnected = useAppStore(s => s.wsConnected)
  const collapsed = useAppStore(s => s.sidebarCollapsed)
  const setCollapsed = useAppStore(s => s.setSidebarCollapsed)

  return (
    <nav
      role="navigation"
      aria-label="Main navigation"
      style={{
        width: collapsed ? 52 : 200,
        flexShrink: 0,
        background: 'var(--bg-card)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        zIndex: 'var(--z-sidebar)',
      }}
    >
      {/* Brand */}
      <div style={{ padding: collapsed ? '14px 14px 10px' : '14px 14px 10px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 24, height: 24, borderRadius: 6, flexShrink: 0,
            background: 'var(--grad-gold)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 12px rgba(229,199,107,0.3)',
          }}>
            <span style={{ fontFamily: 'var(--font-mono,monospace)', fontSize: 9, fontWeight: 700, color: '#0B0B0F', lineHeight: 1 }}>AI</span>
          </div>
          {!collapsed && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.01em', lineHeight: 1 }}>AI Employee</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 2 }}>v2.0 — autonomous</div>
            </div>
          )}
        </div>
      </div>

      {/* Nav groups */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px 6px' }}>
        {NAV_GROUPS.map(({ group, items }) => (
          <div key={group} style={{ marginBottom: 16 }}>
            {!collapsed && (
              <div style={{
                fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.14em',
                textTransform: 'uppercase', color: 'var(--text-muted)',
                padding: '0 8px 6px', marginBottom: 2,
              }}>
                {group}
              </div>
            )}
            {items.map(({ id, label, icon }) => {
              const active = activeSection === id
              return (
                <button
                  key={id}
                  onClick={() => setActiveSection(id)}
                  title={collapsed ? label : undefined}
                  aria-current={active ? 'page' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 9,
                    width: '100%', padding: collapsed ? '8px 0' : '7px 8px',
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    borderRadius: 7, border: 'none', cursor: 'pointer',
                    background: active ? 'rgba(229,199,107,0.08)' : 'transparent',
                    color: active ? 'var(--gold)' : 'var(--text-secondary)',
                    fontSize: 13, fontWeight: active ? 500 : 400,
                    transition: 'background .12s, color .12s',
                    borderLeft: active && !collapsed ? '2px solid var(--gold-bright)' : '2px solid transparent',
                    paddingLeft: active && !collapsed ? 6 : 8,
                    boxSizing: 'border-box',
                    fontFamily: 'inherit',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; e.currentTarget.style.color = 'var(--text-primary)' } }}
                  onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)' } }}
                >
                  <span style={{ flexShrink: 0, opacity: active ? 1 : 0.7, display: 'flex' }}>{icon}</span>
                  {!collapsed && <span>{label}</span>}
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{ padding: collapsed ? '12px 0' : '12px 14px', borderTop: '1px solid var(--border-subtle)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: collapsed ? 'center' : 'space-between' }}>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span
                className={`status-dot ${wsConnected ? 'status-dot--active status-dot--pulse' : 'status-dot--error'}`}
              />
              <span style={{ fontSize: 11, color: wsConnected ? 'var(--text-secondary)' : 'var(--error)', fontFamily: 'monospace', letterSpacing: '0.06em' }}>
                {wsConnected ? 'CONNECTED' : 'OFFLINE'}
              </span>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, display: 'flex', lineHeight: 1 }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d={collapsed ? 'M6 3l5 5-5 5' : 'M10 3L5 8l5 5'} />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  )
}
