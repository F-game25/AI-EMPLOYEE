import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { useSystemStore } from '../../store/systemStore'
import { NavRailItem, StatusPill } from '../nexus-ui'
import './Sidebar.css'

function MiniMetric({ label, value = 0 }) {
  const pct = Math.min(100, Math.max(0, Math.round(value)))
  const tone = pct > 90 ? 'crit' : pct > 75 ? 'warn' : 'ok'
  return (
    <div className={`nx-sidebar__mm nx-sidebar__mm--${tone}`}>
      <span className="nx-sidebar__mm-dot" />
      <span className="nx-sidebar__mm-label">{label}</span>
      <span className="nx-sidebar__mm-val">{pct}%</span>
    </div>
  )
}

function HealthGauge({ value = 0 }) {
  const pct = Math.min(100, Math.max(0, Math.round(value)))
  const radius = 28
  const circ = 2 * Math.PI * radius
  const offset = circ * (1 - pct / 100)
  const tone = pct >= 95 ? '#00FFB4' : pct >= 85 ? '#FFD93D' : '#FF4444'
  return (
    <div className="nx-sidebar__gauge">
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle cx="34" cy="34" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="3" />
        <circle
          cx="34" cy="34" r={radius}
          fill="none"
          stroke={tone}
          strokeWidth="3"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 34 34)"
          style={{ transition: 'stroke-dashoffset 0.8s ease, stroke 0.4s' }}
        />
      </svg>
      <div className="nx-sidebar__gauge-num">
        <div className="nx-sidebar__gauge-pct" style={{ color: tone }}>{pct}%</div>
        <div className="nx-sidebar__gauge-lbl">HEALTHY</div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Navigation Structure: 5 Groups × 17 Items
// CORE (5): Nexus, Cognition, Agents, Memory, Economy
// OPERATIONS (3): Tasks, Workflows, Infrastructure
// INTELLIGENCE (4): Neural Graph, Knowledge, Trends, Research
// SECURITY (2): Security, Audit
// SYSTEM (3): Integrations, Models, Settings
// ─────────────────────────────────────────────────────────────────────────

const NAV_GROUPS = [
  {
    group: 'CORE',
    icon: '◆',
    items: [
      {
        id: 'nexus',
        label: 'Nexus',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2.5"/><path d="M8 1.5v2.4M8 12.1v2.4M2.5 8h2.4M11.1 8h2.4M4.2 4.2l1.7 1.7M10.1 10.1l1.7 1.7M11.8 4.2l-1.7 1.7M4.9 10.1l-1.7 1.7"/></svg>,
      },
      {
        id: 'cognition',
        label: 'Cognition',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7c0-1.1.9-2 2-2h2l1-2h2l1 2h2c1.1 0 2 .9 2 2v4c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V7z"/><circle cx="8" cy="9" r="1.5" fill="currentColor"/></svg>,
      },
      {
        id: 'agents',
        label: 'Agents',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="4" cy="5" r="1.5"/><circle cx="12" cy="5" r="1.5"/><path d="M4 6.5v2c0 1 1.3 2 2 2h4c.7 0 2-1 2-2v-2"/><circle cx="8" cy="13" r="1.5" fill="currentColor"/></svg>,
      },
      {
        id: 'memory',
        label: 'Memory',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="10" height="10" rx="1"/><path d="M3 8h10M8 3v10"/><circle cx="5.5" cy="5.5" r="0.5" fill="currentColor"/><circle cx="10.5" cy="10.5" r="0.5" fill="currentColor"/></svg>,
      },
      {
        id: 'economy',
        label: 'Economy',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8c0-3.3 2.7-6 6-6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z"/><path d="M8 5v6M6 7h4"/></svg>,
      },
    ],
  },
  {
    group: 'OPERATIONS',
    icon: '▸',
    items: [
      {
        id: 'tasks',
        label: 'Tasks',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="12" height="12" rx="1"/><path d="M2 6h12M5 10h6"/></svg>,
      },
      {
        id: 'workflows',
        label: 'Workflows',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="8" r="1.5"/><circle cx="8" cy="3" r="1.5"/><circle cx="8" cy="13" r="1.5"/><circle cx="13" cy="8" r="1.5"/><path d="M4.5 7.5l2-2M8 4.5v3M11.5 7.5l-2-2M8 11.5v1.5M11.5 8.5l1.5 2M4.5 8.5l-1.5 2"/></svg>,
      },
      {
        id: 'infrastructure',
        label: 'Infrastructure',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="2" width="5" height="4" rx="0.5"/><rect x="10" y="2" width="5" height="4" rx="0.5"/><rect x="5.5" y="10" width="5" height="4" rx="0.5"/><path d="M6 6v2m4 0v2m-2-4v2"/></svg>,
      },
      {
        id: 'ascend-forge',
        label: 'Ascend Forge',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 11h12l-1 4H3l-1-4z"/><path d="M4 6l4-4 4 4v3H4V6z"/><path d="M8 2v7"/></svg>,
      },
    ],
  },
  {
    group: 'INTELLIGENCE',
    icon: '⊡',
    items: [
      {
        id: 'neural-graph',
        label: 'Neural Graph',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="3" r="1"/><circle cx="13" cy="3" r="1"/><circle cx="3" cy="13" r="1"/><circle cx="13" cy="13" r="1"/><circle cx="8" cy="8" r="1"/><path d="M4 4l4 4M12 4l-4 4M4 12l4-4M12 12l-4-4"/></svg>,
      },
      {
        id: 'knowledge',
        label: 'Knowledge',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 2h10a1 1 0 011 1v10a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z"/><path d="M5 6h6M5 9h6M5 12h3"/></svg>,
      },
      {
        id: 'trends',
        label: 'Trends',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12l3-4 3 2 5-6"/><polyline points="12 3 12 8 7 8" /></svg>,
      },
      {
        id: 'research',
        label: 'Research',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="6.5" cy="6.5" r="3.5"/><path d="M9.5 9.5l4 4M1 8c0 3.9 3.1 7 7 7s7-3.1 7-7-3.1-7-7-7-7 3.1-7 7z"/></svg>,
      },
    ],
  },
  {
    group: 'SECURITY',
    icon: '⬤',
    items: [
      {
        id: 'security',
        label: 'Security',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1l5 2v3c0 4-5 6-5 6s-5-2-5-6V3l5-2z"/><path d="M6 8l1.5 1.5 3-3"/></svg>,
      },
      {
        id: 'recon',
        label: 'Recon',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="7" cy="7" r="4"/><path d="M10 10l4 4"/><path d="M7 4v6M4 7h6"/></svg>,
      },
      {
        id: 'blacklight',
        label: 'Blacklight',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5S1 8 1 8z"/><circle cx="8" cy="8" r="2.2"/><circle cx="8" cy="8" r="0.8" fill="currentColor"/></svg>,
      },
      {
        id: 'audit',
        label: 'Audit',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 14h12V4H2v10z"/><path d="M5 2h6M5 6h2M5 9h6M5 12h2"/></svg>,
      },
    ],
  },
  {
    group: 'SYSTEM',
    icon: '⚙',
    items: [
      {
        id: 'integrations',
        label: 'Integrations',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="8" r="1.5"/><circle cx="13" cy="8" r="1.5"/><circle cx="8" cy="3" r="1.5"/><circle cx="8" cy="13" r="1.5"/><path d="M4.5 8h7M8 4.5v7M4.5 4.5l4 4M4.5 11.5l4-4"/></svg>,
      },
      {
        id: 'models',
        label: 'Models',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5l2-2 2 2M12 5l-2-2-2 2M8 3v4M4 11l2 2 2-2M12 11l-2 2-2-2M8 9v4"/></svg>,
      },
      {
        id: 'settings',
        label: 'Settings',
        icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2.5"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M12.5 3.5L11 5M4.5 11L3 12.5"/></svg>,
      },
    ],
  },
]

// Flat item list for test/grep access
const NAV_ITEMS = NAV_GROUPS.flatMap(g => g.items)
export { NAV_ITEMS }

function CognitiveStateIndicator() {
  // Pulsing dot indicating current cognitive state
  const brainState = useCognitiveStore(s => s.brainState) || {}
  const isActive = brainState.status === 'active'

  const stateColor = {
    idle: '#666672',
    active: '#20D6C7',
    thinking: '#A855F7',
    learning: '#E5C76B',
    error: '#EF4444',
  }[brainState.mode] || '#666672'

  return (
    <div
      className="nx-sidebar__cognitive-indicator"
      style={{
        backgroundColor: stateColor,
        boxShadow: isActive ? `0 0 6px ${stateColor}` : 'none',
      }}
      title={`Cognitive state: ${brainState.mode || 'idle'}`}
    />
  )
}

export default function Sidebar() {
  const activeSection = useAppStore(s => s.activeSection)
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const wsConnected = useAppStore(s => s.wsConnected)
  const collapsed = useAppStore(s => s.sidebarCollapsed)
  const setCollapsed = useAppStore(s => s.setSidebarCollapsed)
  const systemHealth = useAppStore(s => s.systemHealth) || {}
  const [collapsedGroups, setCollapsedGroups] = useState({})
  const mobileOpen = useSystemStore(s => s.mobileSidebarOpen)
  const setMobileSidebarOpen = useSystemStore(s => s.setMobileSidebarOpen)

  const cpu  = systemHealth.cpu_percent ?? 0
  const ram  = systemHealth.memory_percent ?? 0
  const gpu  = systemHealth.gpu_percent ?? 0
  const vram = systemHealth.vram_percent ?? systemHealth.gpu_memory_percent ?? 0
  const disk = systemHealth.disk_percent ?? 0
  const healthPct = Math.max(0, Math.round(100 - cpu * 0.25 - ram * 0.2 - Math.max(0, gpu - 80) * 0.5))

  const toggleGroup = (group) => {
    setCollapsedGroups(prev => ({
      ...prev,
      [group]: !prev[group],
    }))
  }

  return (
    <>
      {mobileOpen && (
        <div
          className="nx-sidebar-overlay"
          onClick={() => setMobileSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
    <nav
      role="navigation"
      aria-label="Main navigation"
      className={`nx-sidebar ${collapsed ? 'nx-sidebar--collapsed' : ''} ${mobileOpen ? 'nx-sidebar--mobile-open' : ''}`}
    >
      {/* Brand + Cognitive Indicator */}
      <div className="nx-sidebar__brand">
        <div className="nx-sidebar__brand-mark">
          <span>▼</span>
          <CognitiveStateIndicator />
        </div>
        {!collapsed && (
          <div className="nx-sidebar__brand-text">
            <div className="nx-sidebar__brand-name">AETERNUS NEXUS</div>
            <div className="nx-sidebar__brand-meta">COMMAND OPERATING SYSTEM</div>
            <div className="nx-sidebar__brand-year">2095</div>
          </div>
        )}
      </div>

      {/* Navigation groups */}
      <div className="nx-sidebar__scroll">
        {NAV_GROUPS.map(({ group, icon, items }) => {
          const isCollapsed = collapsedGroups[group]
          return (
            <div key={group} className="nx-sidebar__group">
              <button
                className="nx-sidebar__group-toggle"
                onClick={() => toggleGroup(group)}
                title={isCollapsed ? `Show ${group}` : `Hide ${group}`}
              >
                {!collapsed && (
                  <>
                    <span className="nx-sidebar__group-icon">{icon}</span>
                    <span className="nx-sidebar__group-label">{group}</span>
                  </>
                )}
                {collapsed && (
                  <span className="nx-sidebar__group-icon">{icon}</span>
                )}
              </button>

              {!isCollapsed && (
                <div className="nx-sidebar__group-items">
                  {items.map(({ id, label, icon: itemIcon }) => (
                    <NavRailItem
                      key={id}
                      icon={itemIcon}
                      label={label}
                      active={activeSection === id}
                      compact={collapsed}
                      onClick={() => setActiveSection(id)}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* System Status Widget */}
      {!collapsed && (
        <div className="nx-sidebar__sys-status">
          <div className="nx-sidebar__sys-title">SYSTEM STATUS</div>
          <HealthGauge value={healthPct} />
          <div className="nx-sidebar__sys-metrics">
            <MiniMetric label="CPU"  value={cpu} />
            <MiniMetric label="GPU"  value={gpu} />
            <MiniMetric label="RAM"  value={ram} />
            <MiniMetric label="VRAM" value={vram} />
            <MiniMetric label="DISK" value={disk} />
          </div>
        </div>
      )}

      {/* Footer with connection status + collapse toggle */}
      <div className="nx-sidebar__footer">
        {!collapsed && (
          <StatusPill
            tone={wsConnected ? 'success' : 'alert'}
            label={wsConnected ? 'CONNECTED' : 'OFFLINE'}
            size="sm"
          />
        )}
        <button
          type="button"
          className="nx-sidebar__collapse"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d={collapsed ? 'M6 3l5 5-5 5' : 'M10 3L5 8l5 5'} />
          </svg>
        </button>
      </div>
    </nav>
    </>
  )
}
