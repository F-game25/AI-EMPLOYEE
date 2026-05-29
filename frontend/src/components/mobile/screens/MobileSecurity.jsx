/* NEXUS OS Mobile — SECURE Screen */
import { useState, useEffect, useCallback } from 'react'
import { TopBar, Section, RingGauge, Row, StatusPill, Empty, Spinner, ProgressBar } from '../MobileUI'
import api from '../../../api/client'

const MOCK_STATUS = {
  threat_score: 18, threat_level: 'LOW',
  active_scans: 0, blocked_threats: 3, vulnerabilities: 0,
  hosts: [
    { id: 'local', name: 'localhost', ip: '127.0.0.1', status: 'secure', open_ports: 2 },
    { id: 'backend', name: 'Python Backend', ip: '127.0.0.1:18790', status: 'secure', open_ports: 1 },
  ],
  alerts: [],
}

export default function MobileSecurity() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/api/security/status')
      setStatus(r || MOCK_STATUS)
    } catch { setStatus(MOCK_STATUS) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const threatScore = status?.threat_score ?? 18
  const threatLevel = status?.threat_level || 'LOW'
  const threatColor = threatScore > 70 ? 'var(--error)' : threatScore > 40 ? 'var(--warning)' : 'var(--success)'
  const threatTone = threatScore > 70 ? 'error' : threatScore > 40 ? 'warn' : 'ok'

  return (
    <div style={S.screen}>
      <TopBar title="SECURE" subtitle="Threat Intelligence" />
      <div style={S.scroll}>
        {loading ? (
          <div style={S.center}><Spinner /></div>
        ) : (
          <>
            <div style={S.heroRow}>
              <RingGauge value={threatScore} max={100} size={80} color={threatColor}
                label={
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: threatColor, fontFamily: 'var(--nx-font-mono, monospace)' }}>{threatScore}</div>
                    <div style={{ fontSize: 8, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>THREAT</div>
                  </div>
                }
              />
              <div style={S.heroStats}>
                <StatusPill label={threatLevel} tone={threatTone} />
                <div style={S.heroStat}><span style={S.heroVal}>{status?.blocked_threats ?? 0}</span><span style={S.heroLbl}>Blocked</span></div>
                <div style={S.heroStat}><span style={S.heroVal}>{status?.vulnerabilities ?? 0}</span><span style={S.heroLbl}>Vulns</span></div>
                <div style={S.heroStat}><span style={S.heroVal}>{status?.active_scans ?? 0}</span><span style={S.heroLbl}>Scans</span></div>
              </div>
            </div>

            <Section label="Threat Level">
              <div style={{ padding: '4px 16px 10px' }}>
                <ProgressBar value={threatScore} color={threatColor} height={6} />
                <div style={S.threatLabels}>
                  <span>SAFE</span><span>MODERATE</span><span>HIGH</span><span>CRITICAL</span>
                </div>
              </div>
            </Section>

            <Section label="Hosts">
              {(status?.hosts || []).length === 0 ? <Empty icon="⬡" message="No hosts found" /> :
                (status?.hosts || []).map(h => (
                  <Row key={h.id}
                    icon={<span style={{ color: h.status === 'secure' ? 'var(--success)' : 'var(--error)' }}>⬡</span>}
                    label={h.name}
                    value={h.ip}
                    right={<StatusPill label={h.status} tone={h.status === 'secure' ? 'ok' : 'error'} />}
                  />
                ))
              }
            </Section>

            <Section label="Recent Alerts">
              {(status?.alerts || []).length === 0 ? (
                <div style={S.noAlerts}>
                  <span style={{ color: 'var(--success)', fontSize: 20 }}>✓</span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>No active threats</span>
                </div>
              ) : (status?.alerts || []).map((a, i) => (
                <Row key={i}
                  icon={<span style={{ color: 'var(--error)' }}>⚠</span>}
                  label={a.message || a.title}
                  value={a.severity}
                />
              ))}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 16 },
  center: { display: 'flex', justifyContent: 'center', padding: 40 },
  heroRow: { display: 'flex', alignItems: 'center', gap: 20, padding: '20px 24px 12px',
    borderBottom: '1px solid var(--border-subtle)' },
  heroStats: { flex: 1, display: 'flex', flexWrap: 'wrap', gap: 10 },
  heroStat: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  heroVal: { fontSize: 18, fontWeight: 700, color: 'var(--gold)', fontFamily: 'var(--nx-font-mono, monospace)' },
  heroLbl: { fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' },
  threatLabels: { display: 'flex', justifyContent: 'space-between', fontSize: 8,
    color: 'var(--text-muted)', marginTop: 4, letterSpacing: '0.06em' },
  noAlerts: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '20px 16px' },
}
