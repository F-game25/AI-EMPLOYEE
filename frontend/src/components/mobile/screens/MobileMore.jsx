/* NEXUS OS Mobile — MORE Screen */
import { useAppStore } from '../../../store/appStore'

const SECTIONS = [
  {
    label: 'AI Systems',
    items: [
      { id: 'ascendforge', icon: '◈', label: 'AscendForge', sub: 'Agentic code builder' },
      { id: 'agents', icon: '◉', label: 'All Agents', sub: '70+ registered agents' },
      { id: 'cognition', icon: '◆', label: 'Cognition', sub: 'Reasoning + planning' },
      { id: 'memory', icon: '◎', label: 'Memory', sub: 'Long-term knowledge' },
      { id: 'knowledge', icon: '◗', label: 'Knowledge', sub: 'Document intelligence' },
      { id: 'research', icon: '⬢', label: 'Research', sub: 'Autonomous research' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { id: 'tasks', icon: '▣', label: 'Tasks', sub: 'All task history' },
      { id: 'workflows', icon: '⟳', label: 'Workflows', sub: 'Automation flows' },
      { id: 'approvals', icon: '✓', label: 'Approvals', sub: 'Pending decisions' },
      { id: 'economy', icon: '◎', label: 'Economy', sub: 'Revenue + costs' },
    ],
  },
  {
    label: 'Security & Monitoring',
    items: [
      { id: 'security', icon: '⬡', label: 'Security', sub: 'Threat intelligence' },
      { id: 'recon', icon: '◉', label: 'Recon', sub: 'OSINT + scanning' },
      { id: 'neural-graph', icon: '◈', label: 'Neural Graph', sub: 'Brain visualization' },
      { id: 'proof', icon: '◇', label: 'Proof Center', sub: 'Evidence vault' },
    ],
  },
  {
    label: 'System',
    items: [
      { id: 'models', icon: '◆', label: 'Models', sub: 'LLM routing + config' },
      { id: 'setup', icon: '⚙', label: 'Setup Center', sub: 'Configuration' },
      { id: 'api-catalog', icon: '◎', label: 'API Catalog', sub: '119 endpoints' },
      { id: 'settings', icon: '⚙', label: 'Settings', sub: 'Preferences' },
    ],
  },
]

const NAVIGABLE = new Set(['ascendforge', 'tasks', 'recon', 'security', 'approvals'])

export default function MobileMore({ onNavigate }) {
  const setActiveSection = useAppStore(s => s.setActiveSection)

  const handleTile = (item) => {
    if (onNavigate && NAVIGABLE.has(item.id)) {
      onNavigate(item.id)
    } else {
      setActiveSection(item.id)
    }
  }

  return (
    <div style={S.screen}>
      <div style={S.header}>
        <div style={S.headerTitle}>NEXUS OS</div>
        <div style={S.headerSub}>Command Center v2.0</div>
      </div>
      <div style={S.scroll}>
        {SECTIONS.map(sec => (
          <div key={sec.label} style={S.sectionWrap}>
            <div style={S.sectionLabel}>{sec.label}</div>
            <div style={S.grid}>
              {sec.items.map(item => (
                <button key={item.id} style={S.tile} onClick={() => handleTile(item)}>
                  <span style={S.tileIcon}>{item.icon}</span>
                  <span style={S.tileLabel}>{item.label}</span>
                  <span style={S.tileSub}>{item.sub}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
        <div style={S.footer}>NEXUS OS • AI Operating System</div>
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  header: { padding: '16px 20px 12px', borderBottom: '1px solid var(--border-subtle)',
    background: 'linear-gradient(135deg, rgba(139,90,43,0.2) 0%, transparent 60%)' },
  headerTitle: { fontSize: 16, fontWeight: 800, color: 'var(--gold)', letterSpacing: '0.2em', fontFamily: 'var(--nx-font-mono, monospace)' },
  headerSub: { fontSize: 10, color: 'var(--text-muted)', marginTop: 2 },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 24 },
  sectionWrap: { marginTop: 16 },
  sectionLabel: { fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.14em', textTransform: 'uppercase',
    padding: '0 16px 8px' },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '0 16px' },
  tile: { display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3, padding: '12px 12px',
    background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10,
    cursor: 'pointer', textAlign: 'left', transition: 'border-color 150ms' },
  tileIcon: { fontSize: 18, color: 'var(--gold)', marginBottom: 2 },
  tileLabel: { fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' },
  tileSub: { fontSize: 9, color: 'var(--text-muted)' },
  footer: { textAlign: 'center', padding: '20px 16px 8px', fontSize: 10, color: 'rgba(229,199,107,0.2)',
    letterSpacing: '0.14em', textTransform: 'uppercase' },
}
