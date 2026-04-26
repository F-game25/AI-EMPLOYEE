import { useStore } from '../store/ascendStore'

export function TopBar() {
  const { wsConnected, mockMode } = useStore()

  return (
    <div className="topbar" style={{
      background: 'var(--bg-panel)',
      borderBottom: 'var(--border-gold)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 20px',
      height: 52,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontSize: 16, fontWeight: 700 }} className="metallic-text">
          ASCEND AI
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1 }}>
          v1.0.0
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        {mockMode && (
          <span style={{
            padding: '3px 10px', borderRadius: 4,
            background: 'rgba(245,158,11,0.15)', color: 'var(--warning)',
            fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: 1,
          }}>
            DEMO MODE
          </span>
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 10 }}>
          <span className={`dot ${wsConnected ? 'online' : 'offline'}`} />
          {wsConnected ? 'CONNECTED' : 'RECONNECTING...'}
        </span>
      </div>
    </div>
  )
}
