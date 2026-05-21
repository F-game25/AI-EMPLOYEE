import { useState, useEffect, useMemo, useRef } from 'react'
import { Panel, SectionLabel } from '../nexus-ui'
import { useLiveData } from '../../hooks/useLiveData'
import { toastSuccess, toastError, toastWarn } from '../nexus-ui/Toaster'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'
import './SecurityPanel.css'

const SECTION_TAB_MAP = { blacklight: 'blacklight', audit: 'audit', security: 'threats', policies: 'threats' }

const API = '/api/security'

function threatColor(s) {
  if (s >= 75) return 'var(--nx-danger)'
  if (s >= 50) return '#f97316'
  if (s >= 30) return 'var(--nx-warning)'
  return 'var(--nx-success)'
}
function threatLabel(s) {
  if (s >= 75) return 'CRITICAL'
  if (s >= 50) return 'ELEVATED'
  if (s >= 30) return 'GUARDED'
  return 'LOW'
}

function Sparkline({ data = [], color = 'var(--nx-gold)', height = 36 }) {
  const ref = useRef()
  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !data.length) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const w = canvas.width, h = canvas.height
    const max = Math.max(...data, 1)
    ctx.clearRect(0, 0, w, h)
    ctx.beginPath()
    data.forEach((v, i) => {
      const x = data.length > 1 ? (i / (data.length - 1)) * w : w / 2
      const y = h - (v / max) * (h - 4)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.stroke()
  }, [data, color])
  return <canvas ref={ref} width={120} height={height} style={{ display: 'block' }} />
}

function ThreatGauge({ score = 0 }) {
  const color = threatColor(score)
  return (
    <div className="sec-gauge">
      <div className="sec-gauge__score" style={{ color }}>{score}</div>
      <div className="sec-gauge__label" style={{ color }}>{threatLabel(score)}</div>
      <div className="sec-gauge__bar-wrap">
        <div className="sec-gauge__bar" style={{ width: `${score}%`, background: color }} />
      </div>
    </div>
  )
}

function LiveBadge({ stale }) {
  return (
    <span className={`sec-live-badge ${stale ? 'sec-live-badge--stale' : ''}`}>
      <span className="sec-live-badge__dot" />
      {stale ? 'STALE' : 'LIVE'}
    </span>
  )
}

function IntrusionRow({ item }) {
  return (
    <div className="sec-intr-row">
      <span className="sec-intr-ip">{item.ip}</span>
      <span className="sec-intr-path">{item.path}</span>
      <span className="sec-intr-reason">{item.reason}</span>
      <span className="sec-intr-score" style={{ color: threatColor(item.score) }}>{item.score}</span>
    </div>
  )
}

function BlockedIPRow({ item, onUnblock }) {
  const [busy, setBusy] = useState(false)
  async function handleUnblock() {
    setBusy(true)
    try {
      await api.delete(`${API}/blocked-ips/${encodeURIComponent(item.ip)}`)
      toastSuccess(`Unblocked ${item.ip}`)
      onUnblock(item.ip)
    } catch {
      toastError(`Could not unblock ${item.ip}`)
    } finally { setBusy(false) }
  }
  return (
    <div className="sec-blocked-row">
      <span className="sec-blocked-ip">{item.ip}</span>
      <span className="sec-blocked-reason">{item.reason || 'Rate limit'}</span>
      <span className="sec-blocked-since">{new Date(item.since || Date.now()).toLocaleTimeString()}</span>
      <button className="sec-btn sec-btn--sm" onClick={handleUnblock} disabled={busy}>
        {busy ? '...' : 'Unblock'}
      </button>
    </div>
  )
}

function AnomalyCard({ item, onAck }) {
  const sev = item.severity || 'medium'
  return (
    <div className={`sec-anomaly sec-anomaly--${sev}`}>
      <div className="sec-anomaly__head">
        <span className="sec-anomaly__sev">{sev.toUpperCase()}</span>
        <span className="sec-anomaly__title">{item.title || item.message}</span>
        <span className="sec-anomaly__time">{new Date(item.detected_at || Date.now()).toLocaleTimeString()}</span>
      </div>
      {item.details && <div className="sec-anomaly__body">{item.details}</div>}
      <div className="sec-anomaly__actions">
        <button className="sec-btn sec-btn--sm" onClick={() => onAck(item.id)}>Acknowledge</button>
        <button className="sec-btn sec-btn--sm sec-btn--warn">Investigate</button>
      </div>
    </div>
  )
}

function GatewayRow({ evt }) {
  return (
    <div className="sec-gw-row">
      <span className="sec-gw-time">{new Date(evt.timestamp || Date.now()).toLocaleTimeString()}</span>
      <span className="sec-gw-type">{evt.type || evt.event}</span>
      <span className="sec-gw-path">{evt.path || ''}</span>
      <span className="sec-gw-detail">{evt.detail || evt.message || ''}</span>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   TAB 1 — Live Threat Console
═══════════════════════════════════════════════════════════════════════════════ */
function ThreatTab() {
  const { data: threats, error, refresh } = useLiveData({
    endpoint: '/api/security/threats',
    wsEvent: 'security:event',
    pollMs: 10000,
  })
  const t = threats || {}
  const [blocked, setBlocked] = useState(t.blockedIPs || [])
  const [acked, setAcked] = useState([])
  const [strict, setStrict] = useState(false)
  const [rotating, setRotating] = useState(false)

  useEffect(() => { setBlocked(t.blockedIPs || []) }, [threats])

  async function toggleStrict() {
    try {
      await api.post(`${API}/strict-mode`, { enabled: !strict })
      setStrict(s => !s)
      toastSuccess(`Strict mode ${!strict ? 'enabled' : 'disabled'}`)
    } catch { toastError('Failed to toggle strict mode') }
  }

  async function rotateJWT() {
    setRotating(true)
    try {
      await api.post(`${API}/rotate-jwt`)
      toastSuccess('JWT secret rotated — all sessions invalidated')
    } catch { toastError('JWT rotation failed') } finally { setRotating(false) }
  }

  const anomalies = (t.anomalies || []).filter(a => !acked.includes(a.id))

  return (
    <div className="sec-tab-content">
      <div className="sec-kpi-row">
        <Panel className="sec-kpi-tile">
          <SectionLabel>Threat Score</SectionLabel>
          <ThreatGauge score={t.score ?? 0} />
        </Panel>
        <Panel className="sec-kpi-tile">
          <SectionLabel>Last 60 min</SectionLabel>
          <Sparkline data={t.sparkline || []} color={threatColor(t.score ?? 0)} />
        </Panel>
        <Panel className="sec-kpi-tile">
          <SectionLabel>Active Intrusions</SectionLabel>
          <div className="sec-kpi-big" style={{ color: 'var(--nx-danger)' }}>{(t.intrusions || []).length}</div>
        </Panel>
        <Panel className="sec-kpi-tile">
          <SectionLabel>Blocked IPs</SectionLabel>
          <div className="sec-kpi-big">{blocked.length}</div>
        </Panel>
      </div>

      <div className="sec-two-col">
        <Panel title="Active Intrusions" right={<LiveBadge stale={!!error} />}>
          <div className="sec-intr-head"><span>IP</span><span>Path</span><span>Reason</span><span>Score</span></div>
          {(t.intrusions || []).length === 0
            ? <div className="sec-empty">No suspicious requests</div>
            : (t.intrusions || []).map((x, i) => <IntrusionRow key={i} item={x} />)
          }
        </Panel>

        <Panel title="Blocked IPs">
          {blocked.length === 0
            ? <div className="sec-empty">No blocked IPs</div>
            : blocked.map((x, i) => <BlockedIPRow key={i} item={x} onUnblock={ip => setBlocked(b => b.filter(y => y.ip !== ip))} />)
          }
        </Panel>
      </div>

      <Panel title="API Gateway Events" right={<LiveBadge stale={!!error} />}>
        <div className="sec-gw-head"><span>Time</span><span>Type</span><span>Path</span><span>Detail</span></div>
        <div className="sec-gw-list">
          {(t.gatewayEvents || []).map((e, i) => <GatewayRow key={i} evt={e} />)}
        </div>
      </Panel>

      {anomalies.length > 0 && (
        <Panel title="Anomaly Detector Findings">
          {anomalies.map(a => <AnomalyCard key={a.id} item={a} onAck={id => setAcked(x => [...x, id])} />)}
        </Panel>
      )}

      <Panel title="API Gateway Controls">
        <div className="sec-controls">
          <div className="sec-ctrl-row">
            <span className="sec-ctrl-label">Strict Mode</span>
            <button className={`sec-toggle ${strict ? 'sec-toggle--on' : ''}`} onClick={toggleStrict}>{strict ? 'ON' : 'OFF'}</button>
          </div>
          <div className="sec-ctrl-row">
            <span className="sec-ctrl-label">JWT Secret</span>
            <button className="sec-btn" onClick={rotateJWT} disabled={rotating}>{rotating ? 'Rotating...' : 'Rotate Secret'}</button>
          </div>
          <div className="sec-ctrl-row">
            <span className="sec-ctrl-label">Lock Down Writes</span>
            <button className="sec-btn sec-btn--danger" onClick={() => toastWarn('Write lockdown requires strict mode confirmation')}>Lock All Writes</button>
          </div>
        </div>
      </Panel>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   TAB 2 — Audit & Compliance
═══════════════════════════════════════════════════════════════════════════════ */
const COMPLIANCE = [
  { name: 'GDPR',    status: 'met',     note: 'Data retention policy active' },
  { name: 'SOC2',    status: 'partial', note: 'Audit logging active; pen test pending' },
  { name: 'CCPA',    status: 'met',     note: 'Data subject rights API active' },
  { name: 'ISO27001', status: 'partial', note: 'Risk assessment scheduled' },
]

function AuditRow({ row }) {
  return (
    <div className={`sec-audit-row ${row.result === 'fail' ? 'sec-audit-row--fail' : ''}`}>
      <span className="sec-audit-time">{new Date(row.timestamp).toLocaleTimeString()}</span>
      <span className="sec-audit-actor">{row.actor}</span>
      <span className="sec-audit-action">{row.action}</span>
      <span className="sec-audit-resource">{row.resource}</span>
      <span className={`sec-audit-result ${row.result === 'fail' ? 'sec-audit-result--fail' : ''}`}>{row.result.toUpperCase()}</span>
    </div>
  )
}

function HITLCard({ item, onApprove, onReject }) {
  const [busy, setBusy] = useState(false)
  const act = async (action) => {
    setBusy(true)
    try {
      await api.post(`${API}/hitl/${item.id}/${action}`)
      action === 'approve' ? onApprove(item.id) : onReject(item.id)
      toastSuccess(`Request ${action}d`)
    } catch { toastError(`Failed to ${action}`) } finally { setBusy(false) }
  }
  const risk = item.risk || 'medium'
  return (
    <div className={`sec-hitl-card sec-hitl-card--${risk}`}>
      <div className="sec-hitl-head">
        <span className="sec-hitl-agent">{item.agent || item.actor || 'agent'}</span>
        <span className={`sec-hitl-risk sec-hitl-risk--${risk}`}>{risk.toUpperCase()}</span>
        <span className="sec-hitl-time">{item.created_at ? new Date(item.created_at).toLocaleTimeString() : ''}</span>
      </div>
      <div className="sec-hitl-action">{item.action}</div>
      {item.payload && <pre className="sec-hitl-payload">{JSON.stringify(item.payload, null, 2)}</pre>}
      <div className="sec-hitl-btns">
        <button className="sec-btn sec-btn--primary" onClick={() => act('approve')} disabled={busy}>Approve</button>
        <button className="sec-btn sec-btn--danger"  onClick={() => act('reject')}  disabled={busy}>Reject</button>
      </div>
    </div>
  )
}

// Fairness & bias monitor — restored from the removed FairnessPage. Backend live
// at /api/fairness/report. Real shape: {agents_monitored, total_actions,
// high_risk_actions, risk_rate, by_actor:{}, demographic_parity, disparate_impact}.
function FairnessPanel() {
  const [rep, setRep] = useState(null)
  useEffect(() => {
    api.get('/api/fairness/report').then(setRep).catch(() => setRep(false))
  }, [])
  if (rep === null) return null
  if (rep === false) return <Panel title="Fairness & Bias"><div className="sec-fair-empty">Fairness report unavailable.</div></Panel>
  const actors = Object.entries(rep.by_actor || {}).sort((a, b) => b[1] - a[1])
  const maxCount = actors.reduce((m, [, n]) => Math.max(m, n), 0) || 1
  const riskPct = Math.round((parseFloat(rep.risk_rate) || 0) * 100)
  return (
    <Panel title="Fairness & Bias" right={<span className={`sec-badge-count ${riskPct > 20 ? 'low' : ''}`}>{riskPct}% risk</span>}>
      <div className="sec-fair-stats">
        <div className="sec-fair-stat"><span>{rep.agents_monitored ?? 0}</span><label>Agents monitored</label></div>
        <div className="sec-fair-stat"><span>{rep.total_actions ?? 0}</span><label>Actions audited</label></div>
        <div className="sec-fair-stat"><span>{rep.high_risk_actions ?? 0}</span><label>High-risk</label></div>
      </div>
      {actors.length > 0 && (
        <div className="sec-fair-list">
          {actors.map(([name, count]) => (
            <div key={name} className="sec-fair-row">
              <span className="sec-fair-name">{name}</span>
              <div className="sec-fair-bar"><div style={{ width: `${(count / maxCount) * 100}%` }} className="mid" /></div>
              <span className="sec-fair-score">{count}</span>
            </div>
          ))}
        </div>
      )}
      <div className="sec-fair-note">Demographic parity: {rep.demographic_parity || 'N/A'}</div>
    </Panel>
  )
}

function AuditTab() {
  const { data: auditData, refresh } = useLiveData({
    endpoint: '/api/security/audit',
    wsEvent: 'security:audit',
    transform: d => d?.entries || d,
  })
  const { data: hitlData } = useLiveData({
    endpoint: '/api/security/hitl',
    wsEvent: 'security:hitl',
    pollMs: 15000,
    transform: d => d?.queue || d,
  })
  const [resolved, setResolved] = useState([])
  const [filter, setFilter] = useState('')
  const entries = Array.isArray(auditData) ? auditData : []
  const hitl = (Array.isArray(hitlData) ? hitlData : []).filter(h => !resolved.includes(h.id))
  const filtered = entries.filter(r =>
    !filter || [r.actor, r.action, r.resource].some(v => v?.includes(filter))
  )

  async function exportCSV() {
    const rows = [['time','actor','action','resource','result'],
      ...entries.map(r => [new Date(r.timestamp).toISOString(), r.actor, r.action, r.resource, r.result])]
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([rows.map(r => r.join(',')).join('\n')], { type: 'text/csv' }))
    a.download = `audit-${Date.now()}.csv`; a.click()
    toastSuccess('Audit log exported')
  }

  return (
    <div className="sec-tab-content">
      <FairnessPanel />
      {hitl.length > 0 && (
        <Panel title="HITL Approval Queue" right={<span className="sec-badge-count">{hitl.length}</span>}>
          {hitl.map(h => (
            <HITLCard key={h.id} item={h}
              onApprove={id => setResolved(x => [...x, id])}
              onReject={id => setResolved(x => [...x, id])} />
          ))}
        </Panel>
      )}

      <Panel title="Compliance Posture">
        <div className="sec-compliance-grid">
          {COMPLIANCE.map(b => (
            <div key={b.name} className={`sec-compliance-badge sec-compliance-badge--${b.status}`}>
              <div className="sec-compliance-name">{b.name}</div>
              <div className="sec-compliance-status">{b.status === 'met' ? 'MET' : 'PARTIAL'}</div>
              <div className="sec-compliance-note">{b.note}</div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Audit Log"
        right={<div style={{ display: 'flex', gap: 8 }}>
          <input className="sec-filter-input" placeholder="Filter..." value={filter} onChange={e => setFilter(e.target.value)} />
          <button className="sec-btn sec-btn--sm" onClick={exportCSV}>Export CSV</button>
          <button className="sec-btn sec-btn--sm" onClick={refresh}>↻</button>
        </div>}>
        <div className="sec-audit-head"><span>Time</span><span>Actor</span><span>Action</span><span>Resource</span><span>Result</span></div>
        <div className="sec-audit-list">
          {filtered.map(r => <AuditRow key={r.id} row={r} />)}
        </div>
      </Panel>

      <Panel title="GDPR / Data Subject Rights">
        <div className="sec-gdpr-actions">
          <button className="sec-btn" onClick={() => toastSuccess('Data export queued')}>Export My Data</button>
          <button className="sec-btn sec-btn--danger" onClick={() => toastWarn('Deletion requires admin confirmation')}>Request Deletion</button>
        </div>
        <div className="sec-empty" style={{ marginTop: 12 }}>No pending data subject requests</div>
      </Panel>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   TAB 3 — Blacklight OSINT & Security Tools
═══════════════════════════════════════════════════════════════════════════════ */
const MODE_LABELS = {
  safe: 'SAFE',
  passive_network: 'APPROVAL',
  defensive_simulation: 'SIM',
  blocked: 'BLOCKED',
}

function modeClass(mode) {
  if (mode === 'blocked') return 'sec-bl-mode--blocked'
  if (mode === 'passive_network') return 'sec-bl-mode--approval'
  if (mode === 'defensive_simulation') return 'sec-bl-mode--sim'
  return 'sec-bl-mode--safe'
}

async function runBlacklightTool(toolId, input) {
  try {
    return await api.post('/api/blacklight/tools/run', { tool_id: toolId, input })
  } catch (e) {
    return { ok: false, error: e.message || 'request failed' }
  }
}

function ToolCard({ tool, selected, onSelect, networkPolicy }) {
  return (
    <button className={`sec-bl-tool ${selected ? 'sec-bl-tool--selected' : ''}`} onClick={() => onSelect(tool)}>
      <div className="sec-bl-tool__head">
        <span className="sec-bl-tool__name">
          {tool.name}
          {tool.mode === 'passive_network' && !networkPolicy && (
            <span className="bl-tool-lock" title="Requires network policy enabled">🔒</span>
          )}
        </span>
        <span className={`sec-bl-mode ${modeClass(tool.mode)}`}>{MODE_LABELS[tool.mode] || tool.mode}</span>
      </div>
      <div className="sec-bl-tool__meta">{tool.categoryLabel}</div>
      <div className="sec-bl-tool__desc">{tool.description}</div>
    </button>
  )
}

function BlacklightToolsTab() {
  const [catalog, setCatalog] = useState([])
  const [categories, setCategories] = useState({})
  const [summary, setSummary] = useState({})
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [query, setQuery] = useState('')
  const [input, setInput] = useState('')
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [networkPolicy, setNetworkPolicy] = React.useState(false)
  const [policyLoading, setPolicyLoading] = React.useState(false)

  React.useEffect(() => {
    // Was reading localStorage('token') (wrong key) → always 401. api client uses ai_jwt.
    api.get('/api/blacklight/policy')
      .then(d => setNetworkPolicy(!!d.network_osint_enabled))
      .catch(() => {})
  }, [])

  async function toggleNetworkPolicy() {
    setPolicyLoading(true)
    try {
      const d = await api.post('/api/blacklight/policy', { network_osint_enabled: !networkPolicy })
      if (d.ok) setNetworkPolicy(d.policy.network_osint_enabled)
    } catch { /* leave unchanged */ } finally {
      setPolicyLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    api.blacklight.tools()
      .then(data => {
        if (cancelled) return
        setCatalog(data.tools || [])
        setCategories(data.categories || {})
        setSummary(data.summary || {})
        setSelected((data.tools || []).find(t => t.id === 'phishing-url-analyzer') || (data.tools || [])[0] || null)
      })
      .catch(() => toastError('Blacklight tool catalog unavailable'))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return catalog.filter(tool => {
      if (selectedCategory !== 'all' && tool.category !== selectedCategory) return false
      if (!q) return true
      const haystack = `${tool.name} ${tool.description} ${(tool.keywords || []).join(' ')}`.toLowerCase()
      return haystack.includes(q)
    })
  }, [catalog, query, selectedCategory])

  async function handleSearch() {
    if (!query.trim()) return
    setBusy(true)
    try {
      const data = await api.blacklight.search(query)
      if (data.matches?.length) {
        setSelected(data.matches[0])
        setSelectedCategory('all')
        toastSuccess(`Matched ${data.matches[0].name}`)
      } else {
        toastWarn('No Blacklight tool matched that query')
      }
    } catch {
      toastError('AI Search failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleRun() {
    if (!selected) return
    setBusy(true)
    setResult(null)
    try {
      const data = await runBlacklightTool(selected.id, input)
      setResult(data)
      if (data?.result?.blocked) toastWarn('Blocked by Blacklight policy')
      else toastSuccess('Tool completed')
    } catch {
      toastError('Tool execution failed')
    } finally {
      setBusy(false)
    }
  }

  const totals = Object.values(summary).reduce((acc, row) => {
    acc.total += row.total || 0
    acc.safe += row.safe || 0
    acc.simulation += row.simulation || 0
    acc.passive += row.passive || 0
    acc.blocked += row.blocked || 0
    return acc
  }, { total: 0, safe: 0, simulation: 0, passive: 0, blocked: 0 })

  return (
    <div className="sec-tab-content">
      <div className="bl-policy-bar">
        <span className="bl-policy-label">
          {networkPolicy ? '🔓 Network OSINT enabled' : '🔒 Network OSINT disabled'}
        </span>
        <button
          className={`bl-policy-btn ${networkPolicy ? 'bl-policy-btn--active' : ''}`}
          onClick={toggleNetworkPolicy}
          disabled={policyLoading}
        >
          {policyLoading ? '...' : networkPolicy ? 'Disable' : 'Enable'}
        </button>
        {!networkPolicy && (
          <span className="bl-policy-hint">Enable to run DNS, WHOIS, SSL and other network tools</span>
        )}
      </div>

      <div className="sec-kpi-row">
        <Panel className="sec-kpi-tile"><SectionLabel>Total Tools</SectionLabel><div className="sec-kpi-big">{totals.total}</div></Panel>
        <Panel className="sec-kpi-tile"><SectionLabel>Safe Local</SectionLabel><div className="sec-kpi-big" style={{ color: 'var(--nx-success)' }}>{totals.safe}</div></Panel>
        <Panel className="sec-kpi-tile"><SectionLabel>Defensive Sims</SectionLabel><div className="sec-kpi-big" style={{ color: 'var(--nx-gold)' }}>{totals.simulation}</div></Panel>
        <Panel className="sec-kpi-tile"><SectionLabel>Blocked</SectionLabel><div className="sec-kpi-big" style={{ color: 'var(--nx-danger)' }}>{totals.blocked}</div></Panel>
      </div>

      <Panel title="Blacklight AI Search">
        <div className="sec-bl-search">
          <input className="sec-bl-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find the right defensive OSINT/security tool..." />
          <button className="sec-btn sec-btn--primary" onClick={handleSearch} disabled={busy || !query.trim()}>AI Search</button>
        </div>
      </Panel>

      <div className="sec-bl-layout">
        <Panel title="Tool Catalog" right={<span className="sec-badge-count">{filtered.length}</span>}>
          <div className="sec-bl-cats">
            <button className={`sec-bl-cat ${selectedCategory === 'all' ? 'sec-bl-cat--active' : ''}`} onClick={() => setSelectedCategory('all')}>All</button>
            {Object.entries(categories).map(([id, label]) => (
              <button key={id} className={`sec-bl-cat ${selectedCategory === id ? 'sec-bl-cat--active' : ''}`} onClick={() => setSelectedCategory(id)}>
                {label}
              </button>
            ))}
          </div>
          <div className="sec-bl-tools">
            {loading ? <div className="sec-empty">Loading tool catalog...</div> : filtered.map(tool => (
              <ToolCard key={tool.id} tool={tool} selected={selected?.id === tool.id} onSelect={setSelected} networkPolicy={networkPolicy} />
            ))}
          </div>
        </Panel>

        <Panel title={selected ? selected.name : 'Select Tool'} right={selected && <span className={`sec-bl-mode ${modeClass(selected.mode)}`}>{MODE_LABELS[selected.mode]}</span>}>
          {selected ? (
            <div className="sec-bl-runner">
              <div className="sec-bl-desc">{selected.description}</div>
              <textarea
                className="sec-bl-textarea"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Paste the URL, headers, token, hash, domain, or text to analyze. Network-backed tools stay blocked unless policy explicitly allows them."
              />
              <div className="sec-bl-actions">
                <button className="sec-btn sec-btn--primary" onClick={handleRun} disabled={busy}>
                  {busy ? 'Running...' : selected.mode === 'blocked' ? 'Show Policy Gate' : 'Run Safe Tool'}
                </button>
                <button className="sec-btn" onClick={() => { setInput(''); setResult(null) }}>Clear</button>
              </div>
              {result && (
                <pre className={`sec-bl-result ${result?.result?.blocked ? 'sec-bl-result--blocked' : ''}`}>
                  {JSON.stringify(result.result || result, null, 2)}
                </pre>
              )}
            </div>
          ) : <div className="sec-empty">Select a Blacklight tool</div>}
        </Panel>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   ROOT
═══════════════════════════════════════════════════════════════════════════════ */
export default function SecurityPanel() {
  const activeSection = useAppStore(s => s.activeSection)
  const [tab, setTab] = useState(SECTION_TAB_MAP[activeSection] || 'threats')
  useEffect(() => {
    const next = SECTION_TAB_MAP[activeSection]
    if (next && next !== tab) setTab(next)
  }, [activeSection]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="sec-page">
      <div className="sec-header">
        <span className="sec-header__title">SECURITY OPERATIONS</span>
        <div className="sec-header__tabs">
          {[{ id: 'threats', label: 'Live Threat Console' }, { id: 'blacklight', label: 'Blacklight Tools' }, { id: 'audit', label: 'Audit & Compliance' }].map(t => (
            <button key={t.id} className={`sec-tab-btn ${tab === t.id ? 'sec-tab-btn--active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {tab === 'threats' && <ThreatTab />}
      {tab === 'blacklight' && <BlacklightToolsTab />}
      {tab === 'audit'   && <AuditTab />}
    </div>
  )
}
