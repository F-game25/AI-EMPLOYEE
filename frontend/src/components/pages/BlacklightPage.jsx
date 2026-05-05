import { useState, useEffect } from 'react'
import { Panel, KPITile, StatusPill, HexButton, LiveBadge, SectionLabel } from '../nexus-ui'
import api from '../../api/client'
import './BlacklightPage.css'

const SEV_TONE = { HIGH:'alert', MED:'warn', LOW:'purple' }

export default function BlacklightPage() {
  const [events, setEvents]   = useState([])
  const [rules, setRules]     = useState([])
  const [loading, setLoading] = useState(true)
  const [sel, setSel]         = useState(null)

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await api.get('/api/blacklight/alerts')
        setEvents(res?.alerts || [])
        setRules(res?.rules || [])
      } catch { /* silent */ }
      finally { setLoading(false) }
    }
    fetchAlerts()
    const t = setInterval(fetchAlerts, 6000)
    return () => clearInterval(t)
  }, [])

  const selE     = sel ?? (events[0] ?? null)
  const blocked  = events.filter(e => e.blocked).length
  const high     = events.filter(e => e.severity === 'HIGH').length
  const activeRules = rules.filter(r => r.active).length
  const threatLevel = high > 2 ? 'HIGH' : high > 0 ? 'MED' : 'LOW'
  const threatTone  = high > 2 ? 'alert' : high > 0 ? 'warn' : 'success'

  const matrix = (() => {
    const map = {}
    events.forEach(e => {
      const key = e.type || 'Unknown'
      if (!map[key]) map[key] = { severity: e.severity, count: 0 }
      map[key].count++
    })
    return Object.entries(map).slice(0, 6).map(([name, d]) => ({ name, sev: d.severity, count: d.count }))
  })()

  return (
    <div className="bl-grid">
      {/* Scan-line accent bar */}
      <div className="bl-scanline" />

      {/* KPI strip */}
      <div className="bl-kpis">
        <KPITile
          icon="◈" iconTone={high > 0 ? 'alert' : 'purple'}
          label="Events Today"
          value={loading ? '—' : events.length}
          sub={`${high} HIGH severity`}
          accent
        />
        <KPITile
          icon="⛨" iconTone="alert"
          label="Blocked"
          value={loading ? '—' : blocked}
          sub="Threats neutralised"
        />
        <KPITile
          icon="⊕" iconTone="purple"
          label="Rules Active"
          value={loading ? '—' : activeRules}
          sub={`of ${rules.length} total`}
        />
        <KPITile
          icon="✺" iconTone={threatTone}
          label="Threat Level"
          value={threatLevel}
          sub="Current posture"
        />
      </div>

      {/* Main two-column body */}
      <div className="bl-cols">
        <div className="bl-col">
          <Panel
            icon="◐"
            title="Security Events"
            className="bl-panel"
            actions={
              loading
                ? <StatusPill tone="idle" label="LOADING" dot={false} size="sm" />
                : high > 0
                  ? <LiveBadge variant="warn" label="THREAT DETECTED" />
                  : <LiveBadge variant="live" label="ALL CLEAR" />
            }
          >
            {loading ? (
              <div className="bl-empty">Fetching alerts…</div>
            ) : !events.length ? (
              <div className="bl-empty bl-empty--ok">✓ No alerts detected</div>
            ) : (
              <div className="bl-events">
                {events.map(e => (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => setSel(e)}
                    className={`bl-event bl-event--${SEV_TONE[e.severity]} ${selE?.id === e.id ? 'is-selected' : ''}`}
                  >
                    <span className="bl-event__rail" />
                    <div className="bl-event__head">
                      <span className={`bl-event__sev bl-event__sev--${SEV_TONE[e.severity]}`}>{e.severity}</span>
                      <span className="bl-event__type">{e.type}</span>
                      {e.blocked && <StatusPill tone="alert" label="BLOCKED" dot={false} size="sm" />}
                      <span className="bl-event__time">{e.ts}</span>
                    </div>
                    <div className="bl-event__detail">{e.detail}</div>
                    <div className="bl-event__agent">{e.agent}</div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          <Panel
            icon="⚙"
            title="Rule Engine"
            className="bl-panel bl-col__grow"
            actions={<StatusPill tone="purple" label={`${activeRules} ACTIVE`} dot={false} size="sm" />}
          >
            {loading ? (
              <div className="bl-empty">Loading rules…</div>
            ) : (
              <div className="bl-rules">
                {rules.map(r => (
                  <div key={r.rule} className={`bl-rule ${r.active ? 'is-on' : 'is-off'}`}>
                    <span className={`bl-rule__dot ${r.active ? 'is-on' : ''}`} />
                    <span className="bl-rule__text">{r.rule}</span>
                    <span className={`bl-rule__hits ${r.hits > 0 ? 'is-hot' : ''}`}>{r.hits}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="bl-col">
          {selE && (
            <Panel
              icon="◈"
              title="Event Detail"
              className="bl-panel"
              actions={<StatusPill tone={SEV_TONE[selE.severity]} label={selE.severity} dot={false} size="sm" />}
            >
              <div className="bl-detail">
                {[
                  ['Type',    selE.type,                       SEV_TONE[selE.severity]],
                  ['Agent',   selE.agent,                      'purple'],
                  ['Time',    selE.ts,                          null],
                  ['Blocked', selE.blocked ? 'YES' : 'NO',     selE.blocked ? 'alert' : 'success'],
                ].map(([l, v, t]) => (
                  <div key={l} className="bl-detail__row">
                    <span className="bl-detail__label">{l}</span>
                    <span className={`bl-detail__val ${t ? `bl-detail__val--${t}` : ''}`}>{v}</span>
                  </div>
                ))}
              </div>

              <div className={`bl-detail__note bl-detail__note--${SEV_TONE[selE.severity]}`}>
                {selE.detail}
              </div>

              {selE.severity === 'HIGH' && (
                <div className="bl-detail__cta">
                  <HexButton variant="primary" size="sm" tone="alert" icon="⛨">Quarantine</HexButton>
                  <HexButton variant="outline" size="sm">Review</HexButton>
                </div>
              )}
            </Panel>
          )}

          <Panel icon="◷" title="Threat Matrix" className="bl-panel bl-col__grow">
            {matrix.length === 0 ? (
              <div className="bl-empty">No threats classified</div>
            ) : (
              <div className="bl-matrix">
                {matrix.map(m => (
                  <div key={m.name} className={`bl-matrix__cell bl-matrix__cell--${SEV_TONE[m.sev]}`}>
                    <div className="bl-matrix__bar" />
                    <div className="bl-matrix__count">{m.count}</div>
                    <div className="bl-matrix__name">{m.name}</div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel icon="✺" title="UV Scan" className="bl-panel">
            <SectionLabel size="sm" tone="purple">Anomaly Signature — Live</SectionLabel>
            <svg viewBox="0 0 240 36" className="bl-uv">
              <defs>
                <linearGradient id="bl-uv-g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor="var(--nx-purple)" stopOpacity=".5" />
                  <stop offset="100%" stopColor="var(--nx-purple)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <polyline
                points="0,28 20,24 40,20 60,26 80,12 100,18 120,8 140,15 160,10 180,18 200,14 220,20 240,16"
                fill="none" stroke="var(--nx-purple)" strokeWidth="1.5"
              />
              <polygon
                points="0,28 20,24 40,20 60,26 80,12 100,18 120,8 140,15 160,10 180,18 200,14 220,20 240,16 240,36 0,36"
                fill="url(#bl-uv-g)"
              />
            </svg>
          </Panel>
        </div>
      </div>
    </div>
  )
}
