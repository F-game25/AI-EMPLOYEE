/* NEXUS OS Mobile — Blacklight OSINT & Security Screen */
import { useState, useEffect, useCallback, useRef } from 'react'
import { TopBar, Section, RingGauge, Row, Sheet, StatusPill, Empty, Spinner, ProgressBar } from '../MobileUI'

const AUTH = () => {
  const t = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const MOCK_THREATS = {
  score: 18,
  sparkline: [10, 14, 12, 18, 22, 16, 18],
  intrusions: [],
  blocked_ips: [],
  anomalies: [],
}

const MOCK_TOOLS = [
  { id: 'whois', name: 'WHOIS Lookup', description: 'Query domain registration info', mode: 'safe', category: 'recon', input_hint: 'domain.com' },
  { id: 'dns', name: 'DNS Resolve', description: 'Resolve DNS records for a domain', mode: 'safe', category: 'recon', input_hint: 'domain.com' },
  { id: 'ip-geo', name: 'IP Geolocation', description: 'Geolocate an IP address', mode: 'safe', category: 'recon', input_hint: '1.2.3.4' },
  { id: 'port-scan', name: 'Port Scanner', description: 'Scan open ports on a host', mode: 'approval', category: 'network', input_hint: '192.168.1.1' },
  { id: 'ssl-check', name: 'SSL Inspector', description: 'Inspect TLS certificate chain', mode: 'safe', category: 'security', input_hint: 'domain.com' },
  { id: 'header-scan', name: 'HTTP Headers', description: 'Analyze HTTP security headers', mode: 'safe', category: 'security', input_hint: 'https://...' },
]

const MODE_COLOR = { safe: 'var(--success)', approval: 'var(--warning)', blocked: 'var(--error)' }
const MODE_LABEL = { safe: 'SAFE', approval: 'APPROVAL', blocked: 'BLOCKED', sim: 'SIM' }

export default function MobileBlacklight({ onBack }) {
  const [threats, setThreats] = useState(null)
  const [tools, setTools] = useState([])
  const [policy, setPolicy] = useState({ network_osint_enabled: false })
  const [loadingThreats, setLoadingThreats] = useState(true)
  const [loadingTools, setLoadingTools] = useState(true)
  const [selectedTool, setSelectedTool] = useState(null)
  const [toolInput, setToolInput] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [live, setLive] = useState(false)
  const pollRef = useRef(null)

  const loadThreats = useCallback(async () => {
    try {
      const r = await fetch('/api/security/threats', { headers: AUTH() })
      const d = await r.json()
      setThreats(d?.score !== undefined ? d : MOCK_THREATS)
    } catch { setThreats(MOCK_THREATS) }
    finally { setLoadingThreats(false); setLive(true) }
  }, [])

  const loadTools = useCallback(async () => {
    try {
      const [tr, pr] = await Promise.all([
        fetch('/api/blacklight/tools', { headers: AUTH() }),
        fetch('/api/blacklight/policy', { headers: AUTH() }),
      ])
      const td = await tr.json()
      const pd = await pr.json()
      setTools(Array.isArray(td.tools) ? td.tools : MOCK_TOOLS)
      setPolicy(pd || { network_osint_enabled: false })
    } catch { setTools(MOCK_TOOLS) }
    finally { setLoadingTools(false) }
  }, [])

  useEffect(() => {
    loadThreats()
    loadTools()
    pollRef.current = setInterval(loadThreats, 10000)
    return () => clearInterval(pollRef.current)
  }, [loadThreats, loadTools])

  const runTool = useCallback(async () => {
    if (!selectedTool || running) return
    setRunning(true)
    setResult(null)
    try {
      const r = await fetch('/api/blacklight/tools/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH() },
        body: JSON.stringify({ tool_id: selectedTool.id, input: toolInput }),
      })
      const d = await r.json()
      setResult(d.result || d.output || d.error || JSON.stringify(d, null, 2))
    } catch (e) {
      setResult(`Error: ${e.message}`)
    } finally { setRunning(false) }
  }, [selectedTool, toolInput, running])

  const openTool = (tool) => {
    setSelectedTool(tool)
    setToolInput('')
    setResult(null)
  }

  const score = threats?.score ?? 0
  const scoreColor = score >= 70 ? 'var(--error)' : score >= 40 ? 'var(--warning)' : 'var(--success)'
  const scoreLabel = score >= 70 ? 'CRITICAL' : score >= 40 ? 'ELEVATED' : 'SECURE'

  const alerts = [...(threats?.intrusions || []), ...(threats?.anomalies || [])]

  return (
    <div style={S.screen}>
      <TopBar
        title="BLACKLIGHT"
        subtitle="OSINT & Security"
        right={
          <button style={S.backBtn} onClick={onBack}>✕</button>
        }
      />

      <div style={S.scroll}>
        {/* ── Threat Overview ── */}
        <Section label={
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            THREAT OVERVIEW
            {live && <span style={S.livePulse} />}
          </span>
        }>
          {loadingThreats ? <Spinner /> : (
            <div style={S.threatCard}>
              <div style={S.ringRow}>
                <RingGauge
                  value={score} max={100} size={80} color={scoreColor}
                  label={
                    <>
                      <div style={{ fontSize: 18, fontWeight: 800, color: scoreColor }}>{score}</div>
                      <div style={{ fontSize: 8, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>SCORE</div>
                    </>
                  }
                />
                <div style={S.threatStats}>
                  <div style={{ ...S.threatLevel, color: scoreColor }}>{scoreLabel}</div>
                  <div style={S.statRow}>
                    <span style={S.statLbl}>Blocked IPs</span>
                    <span style={{ ...S.statVal, color: 'var(--error)' }}>{threats?.blocked_ips?.length ?? 0}</span>
                  </div>
                  <div style={S.statRow}>
                    <span style={S.statLbl}>Intrusions</span>
                    <span style={{ ...S.statVal, color: 'var(--warning)' }}>{threats?.intrusions?.length ?? 0}</span>
                  </div>
                  <div style={S.statRow}>
                    <span style={S.statLbl}>Anomalies</span>
                    <span style={{ ...S.statVal, color: 'var(--gold)' }}>{threats?.anomalies?.length ?? 0}</span>
                  </div>
                </div>
              </div>
              <ProgressBar
                value={score} max={100}
                color={scoreColor}
                height={4}
              />
              <div style={S.zoneRow}>
                {['SAFE', 'MODERATE', 'HIGH', 'CRITICAL'].map((z, i) => (
                  <span key={z} style={{ ...S.zone, opacity: i <= Math.floor(score / 25) ? 1 : 0.3 }}>{z}</span>
                ))}
              </div>
            </div>
          )}
        </Section>

        {/* ── Tool Catalog ── */}
        <Section label="TOOLS" right={
          <span style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>
            {tools.filter(t => t.mode === 'safe').length} SAFE · {tools.filter(t => t.mode === 'approval').length} APPROVAL
          </span>
        }>
          {loadingTools ? <Spinner /> : tools.length === 0 ? (
            <Empty icon="🔍" message="No tools available" />
          ) : tools.map(tool => {
            const modeColor = MODE_COLOR[tool.mode] || 'var(--text-muted)'
            return (
              <Row
                key={tool.id}
                icon={tool.category === 'network' ? '⚡' : tool.category === 'security' ? '🛡' : '🔍'}
                label={tool.name}
                value={
                  <span style={{ fontSize: 9, fontWeight: 700, color: modeColor, letterSpacing: '0.08em' }}>
                    {MODE_LABEL[tool.mode] || tool.mode?.toUpperCase()}
                  </span>
                }
                chevron
                onClick={() => openTool(tool)}
              />
            )
          })}
        </Section>

        {/* ── Recent Alerts ── */}
        <Section label="RECENT ALERTS">
          {alerts.length === 0 ? (
            <div style={S.noAlerts}>
              <span style={{ fontSize: 20 }}>✓</span>
              <span style={{ color: 'var(--success)', fontSize: 12, fontWeight: 600 }}>No active threats</span>
            </div>
          ) : alerts.slice(0, 10).map((alert, i) => (
            <div key={i} style={S.alertRow}>
              <span style={S.alertDot} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={S.alertType}>{alert.type || alert.category || 'Alert'}</div>
                <div style={S.alertDesc}>{alert.message || alert.description || String(alert)}</div>
              </div>
              <div style={S.alertTs}>{alert.ts || alert.timestamp || 'now'}</div>
            </div>
          ))}
        </Section>
      </div>

      {/* ── Tool Sheet ── */}
      <Sheet open={!!selectedTool} onClose={() => setSelectedTool(null)} title={selectedTool?.name || ''}>
        {selectedTool && (
          <div style={S.sheetBody}>
            <div style={S.toolDesc}>{selectedTool.description}</div>
            <div style={{ ...S.toolMode, color: MODE_COLOR[selectedTool.mode] }}>
              {MODE_LABEL[selectedTool.mode] || selectedTool.mode?.toUpperCase()} — {
                selectedTool.mode === 'safe' ? 'Local execution, no network calls' :
                selectedTool.mode === 'approval' ? (policy.network_osint_enabled ? 'Network OSINT enabled' : 'Requires network OSINT policy to be enabled') :
                'Blocked by security policy'
              }
            </div>

            {selectedTool.mode !== 'blocked' && (
              <>
                <input
                  style={S.toolInput}
                  value={toolInput}
                  onChange={e => setToolInput(e.target.value)}
                  placeholder={selectedTool.input_hint || 'Enter target…'}
                  disabled={running}
                />
                <button
                  style={{
                    ...S.runBtn,
                    opacity: (selectedTool.mode === 'approval' && !policy.network_osint_enabled) || running ? 0.4 : 1,
                  }}
                  onClick={runTool}
                  disabled={running || (selectedTool.mode === 'approval' && !policy.network_osint_enabled)}
                >
                  {running ? '⟳ Running…' : '▶ Run Tool'}
                </button>
              </>
            )}

            {selectedTool.mode === 'blocked' && (
              <div style={S.blockedMsg}>⛔ This tool is blocked by security policy</div>
            )}

            {result && (
              <div style={S.resultBox}>
                <div style={S.resultLabel}>RESULT</div>
                <pre style={S.resultPre}>{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>
              </div>
            )}
          </div>
        )}
      </Sheet>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 24 },
  backBtn: { background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 16, cursor: 'pointer', padding: '4px 8px' },
  livePulse: {
    display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
    background: 'var(--success)', boxShadow: '0 0 6px var(--success)',
    animation: 'pulse 2s ease-in-out infinite',
  },
  threatCard: { margin: '0 16px', padding: '14px', background: 'var(--bg-card)', borderRadius: 10, border: '1px solid var(--border-subtle)' },
  ringRow: { display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 },
  threatStats: { flex: 1, display: 'flex', flexDirection: 'column', gap: 5 },
  threatLevel: { fontSize: 14, fontWeight: 800, letterSpacing: '0.14em', marginBottom: 2 },
  statRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  statLbl: { fontSize: 10, color: 'var(--text-muted)' },
  statVal: { fontSize: 12, fontWeight: 700 },
  zoneRow: { display: 'flex', justifyContent: 'space-between', marginTop: 4 },
  zone: { fontSize: 8, letterSpacing: '0.08em', color: 'var(--text-dim)', textTransform: 'uppercase' },
  noAlerts: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '20px 16px', color: 'var(--text-muted)' },
  alertRow: { display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 16px', borderBottom: '1px solid var(--border-subtle)' },
  alertDot: { width: 6, height: 6, borderRadius: '50%', background: 'var(--error)', flexShrink: 0, marginTop: 4 },
  alertType: { fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  alertDesc: { fontSize: 10, color: 'var(--text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  alertTs: { fontSize: 9, color: 'var(--text-dim)', flexShrink: 0 },
  sheetBody: { padding: '0 4px 8px', display: 'flex', flexDirection: 'column', gap: 12 },
  toolDesc: { fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 },
  toolMode: { fontSize: 10, fontWeight: 700, letterSpacing: '0.1em' },
  toolInput: {
    width: '100%', padding: '10px 12px', borderRadius: 8,
    background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-gold)',
    color: 'var(--text-primary)', fontSize: 13,
    outline: 'none', boxSizing: 'border-box',
  },
  runBtn: {
    width: '100%', padding: '12px', borderRadius: 8,
    background: 'linear-gradient(135deg, var(--gold), #b8960a)',
    color: '#0a0800', fontSize: 13, fontWeight: 700, letterSpacing: '0.08em',
    border: 'none', cursor: 'pointer',
  },
  blockedMsg: { padding: '12px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: 'var(--error)', fontSize: 12 },
  resultBox: { background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-subtle)', borderRadius: 8, overflow: 'hidden' },
  resultLabel: { padding: '6px 10px', fontSize: 9, fontWeight: 700, letterSpacing: '0.14em', color: 'var(--gold)', borderBottom: '1px solid var(--border-subtle)' },
  resultPre: { padding: '10px', fontSize: 11, color: 'var(--text-muted)', margin: 0, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 200, overflowY: 'auto' },
}
