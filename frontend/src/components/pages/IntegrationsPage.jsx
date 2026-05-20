import { useState, useEffect, useRef } from 'react'
import { useLiveData } from '../../hooks/useLiveData'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './IntegrationsPage.css'

const API = ''

const INTEGRATIONS = [
  { id: 'google-calendar', name: 'Google Calendar', category: 'productivity', icon: '📅', oauth: true },
  { id: 'google-drive',    name: 'Google Drive',    category: 'productivity', icon: '📄', oauth: true },
  { id: 'google-sheets',   name: 'Google Sheets',   category: 'productivity', icon: '📊', oauth: true },
  { id: 'notion',          name: 'Notion',          category: 'productivity', icon: '📝', oauth: true },
  { id: 'airtable',        name: 'Airtable',        category: 'productivity', icon: '📋', apikey: true },
  { id: 'instagram',  name: 'Instagram',   category: 'social', icon: '📸', oauth: true },
  { id: 'tiktok',     name: 'TikTok',      category: 'social', icon: '🎵', oauth: true },
  { id: 'youtube',    name: 'YouTube',     category: 'social', icon: '📺', oauth: true },
  { id: 'twitter',    name: 'X / Twitter', category: 'social', icon: '🐦', oauth: true },
  { id: 'linkedin',   name: 'LinkedIn',    category: 'social', icon: '💼', oauth: true },
  { id: 'discord', name: 'Discord', category: 'comms', icon: '💬', oauth: true },
  { id: 'gmail',   name: 'Gmail',   category: 'comms', icon: '📧', oauth: true },
  { id: 'slack',   name: 'Slack',   category: 'comms', icon: '💬', apikey: true },
  { id: 'stripe',   name: 'Stripe',   category: 'data', icon: '💳', apikey: true },
  { id: 'tavily',   name: 'Tavily',   category: 'data', icon: '🔍', apikey: true },
  { id: 'hubspot',  name: 'HubSpot',  category: 'crm',  icon: '🎯', apikey: true },
  { id: 'github',   name: 'GitHub',   category: 'dev',  icon: '🐙', oauth: true },
  { id: 'linear',   name: 'Linear',   category: 'dev',  icon: '◆',  apikey: true },
]

const CATEGORIES = [
  { id: 'productivity', label: 'PRODUCTIVITY' },
  { id: 'social',       label: 'SOCIAL MEDIA' },
  { id: 'comms',        label: 'COMMUNICATION' },
  { id: 'data',         label: 'DATA / CRM' },
  { id: 'crm',          label: null },   // merged into data
  { id: 'dev',          label: 'DEVELOPER' },
]

const TABS = [
  { id: 'connectors', label: 'Service Connectors' },
  { id: 'mobile',     label: 'Mobile Pairing' },
  { id: 'webhooks',   label: 'Webhooks & API Gateway' },
]

/* ── ConnectModal ─────────────────────────────────────────────────────────── */
function ConnectModal({ integration, onClose, onConnected }) {
  const [apiKey, setApiKey] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [status, setStatus] = useState(null)
  const pollRef = useRef(null)

  const connectOAuth = async () => {
    setConnecting(true)
    const r = await fetch(`${API}/api/integrations/${integration.id}/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'oauth' }),
    }).catch(() => null)
    const data = r ? await r.json().catch(() => null) : null
    if (data?.oauth_url) {
      window.open(data.oauth_url, '_blank', 'popup,width=600,height=700')
      pollRef.current = setInterval(async () => {
        const check = await fetch(`${API}/api/integrations/${integration.id}`).then(r => r.json()).catch(() => null)
        if (check?.connected) {
          clearInterval(pollRef.current)
          onConnected(integration.id)
          onClose()
        }
      }, 2000)
    } else if (data?.ok) {
      onConnected(integration.id)
      toastSuccess(`${integration.name} connected`)
      onClose()
    } else {
      setStatus('✗ Failed to initiate connection')
      setConnecting(false)
    }
  }

  const connectApiKey = async () => {
    setConnecting(true)
    const r = await fetch(`${API}/api/integrations/${integration.id}/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'apikey', api_key: apiKey }),
    }).catch(() => null)
    if (r?.ok) {
      onConnected(integration.id)
      toastSuccess(`${integration.name} connected`)
      onClose()
    } else {
      setStatus('✗ Connection failed')
      setConnecting(false)
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  return (
    <div className="integ-modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="integ-modal">
        <div className="integ-modal-header">
          <span className="integ-modal-icon">{integration.icon}</span>
          <span className="integ-modal-title">Connect {integration.name}</span>
          <button className="integ-modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="integ-modal-body">
          {integration.oauth && (
            <>
              <p className="integ-modal-desc">Authorize the system to access your {integration.name} account.</p>
              <button className="integ-connect-btn" onClick={connectOAuth} disabled={connecting}>
                {connecting ? 'Opening authorization…' : `Authorize with ${integration.name}`}
              </button>
            </>
          )}
          {integration.apikey && !integration.oauth && (
            <>
              <p className="integ-modal-desc">Paste your {integration.name} API key below.</p>
              <input
                className="integ-key-input"
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="API key…"
                autoFocus
                onKeyDown={e => e.key === 'Enter' && apiKey && connectApiKey()}
              />
              <button className="integ-connect-btn" onClick={connectApiKey} disabled={connecting || !apiKey}>
                {connecting ? 'Connecting…' : 'Save & Connect'}
              </button>
            </>
          )}
          {status && <div className="integ-modal-status">{status}</div>}
        </div>
      </div>
    </div>
  )
}

/* ── IntegrationCard ──────────────────────────────────────────────────────── */
function IntegrationCard({ integration, connected, lastSync, onConnect, onDisconnect }) {
  const [testing, setTesting] = useState(false)

  const testConn = async () => {
    setTesting(true)
    try {
      const r = await fetch(`${API}/api/integrations/${integration.id}/test`, { method: 'POST' })
      const d = await r.json()
      d.ok ? toastSuccess(`${integration.name}: OK (${d.latency_ms}ms)`) : toastError(`${integration.name}: ${d.error}`)
    } catch { toastError('Test failed') }
    setTesting(false)
  }

  return (
    <div className={`integ-card ${connected ? 'integ-card--connected' : ''}`}>
      <div className="integ-card-header">
        <span className="integ-card-icon">{integration.icon}</span>
        <span className={`integ-card-dot ${connected ? 'integ-card-dot--on' : 'integ-card-dot--off'}`} />
      </div>
      <div className="integ-card-name">{integration.name}</div>
      {connected && lastSync
        ? <div className="integ-card-sync">Synced {lastSync}</div>
        : <div className="integ-card-sync integ-card-sync--dim">Not connected</div>
      }
      <div className="integ-card-actions">
        {connected ? (
          <>
            <button className="integ-card-btn integ-card-btn--test" onClick={testConn} disabled={testing}>
              {testing ? '…' : 'Test'}
            </button>
            <button className="integ-card-btn integ-card-btn--disconnect" onClick={() => onDisconnect(integration.id)}>
              Disconnect
            </button>
          </>
        ) : (
          <button className="integ-card-btn integ-card-btn--connect" onClick={() => onConnect(integration)}>Connect</button>
        )}
      </div>
    </div>
  )
}

/* ── ConnectorsTab ────────────────────────────────────────────────────────── */
function ConnectorsTab() {
  const { data } = useLiveData({ endpoint: `${API}/api/integrations`, pollMs: 30000, transform: d => d })
  const [states, setStates] = useState({})
  const [modal, setModal] = useState(null)
  const [activity, setActivity] = useState([])

  useEffect(() => {
    if (Array.isArray(data)) {
      const s = {}
      data.forEach(i => { s[i.id] = { connected: i.connected, lastSync: i.last_sync ? new Date(i.last_sync).toLocaleTimeString() : null } })
      setStates(s)
    }
    fetch(`${API}/api/integrations/activity`).then(r => r.json()).then(setActivity).catch(() => {})
  }, [data])

  const handleConnected = id => setStates(s => ({ ...s, [id]: { connected: true, lastSync: new Date().toLocaleTimeString() } }))

  const handleDisconnect = async id => {
    await fetch(`${API}/api/integrations/${id}`, { method: 'DELETE' }).catch(() => {})
    setStates(s => ({ ...s, [id]: { connected: false } }))
    toastSuccess('Disconnected')
  }

  const visibleCats = CATEGORIES.filter(c => c.label !== null)

  return (
    <div className="integ-tab-body">
      {modal && <ConnectModal integration={modal} onClose={() => setModal(null)} onConnected={handleConnected} />}

      <div className="integ-categories">
        {visibleCats.map(cat => {
          const catIds = cat.id === 'data' ? ['data', 'crm'] : [cat.id]
          const items  = INTEGRATIONS.filter(i => catIds.includes(i.category))
          return (
            <div key={cat.id} className="integ-category">
              <div className="integ-category-label">{cat.label}</div>
              <div className="integ-cards">
                {items.map(integ => (
                  <IntegrationCard
                    key={integ.id}
                    integration={integ}
                    connected={states[integ.id]?.connected || false}
                    lastSync={states[integ.id]?.lastSync}
                    onConnect={i => setModal(i)}
                    onDisconnect={handleDisconnect}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>

      <div className="integ-activity">
        <div className="integ-activity-header">INTEGRATION ACTIVITY LOG</div>
        <div className="integ-activity-list">
          {activity.length === 0
            ? <div className="integ-activity-empty">No recent activity — connect a service to start syncing</div>
            : activity.map((e, i) => (
              <div key={i} className="integ-activity-row">
                <span className="integ-activity-ts">{e.ts ? new Date(e.ts).toLocaleTimeString() : '—'}</span>
                <span className="integ-activity-service">{e.service}</span>
                <span className="integ-activity-action">{e.action}</span>
                <span className={`integ-activity-status ${e.status === 'ok' ? 'integ-activity-status--ok' : 'integ-activity-status--fail'}`}>
                  {e.status === 'ok' ? '✓' : '✗'}
                </span>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  )
}

/* ── WebhookRow ───────────────────────────────────────────────────────────── */
function WebhookRow({ hook }) {
  const [revealed, setRevealed] = useState(false)
  const [secret, setSecret] = useState(null)

  const revealSecret = async () => {
    if (revealed) { setRevealed(false); return }
    try {
      const r = await fetch(`/api/hooks/${hook.name}/secret`)
      const d = await r.json()
      setSecret(d.secret)
      setRevealed(true)
    } catch { toastError('Could not fetch secret') }
  }

  const copyUrl = () => {
    navigator.clipboard.writeText(window.location.origin + hook.url)
    toastSuccess('URL copied')
  }

  return (
    <div className="integ-wh-row">
      <div className="integ-wh-name">{hook.name}</div>
      <div className="integ-wh-url" onClick={copyUrl} title="Click to copy">
        {hook.url} <span className="integ-wh-copy">⎘</span>
      </div>
      <div className="integ-wh-events">
        {hook.events?.map(e => <span key={e} className="integ-wh-event">{e}</span>)}
      </div>
      <div className="integ-wh-secret">
        {revealed ? <code className="integ-wh-secret-val">{secret}</code> : <span className="integ-wh-secret-dots">●●●●●●●●</span>}
        <button className="integ-wh-reveal" onClick={revealSecret}>{revealed ? 'Hide' : 'Reveal'}</button>
      </div>
      <div className={`integ-wh-status ${hook.active ? 'integ-wh-status--on' : 'integ-wh-status--off'}`}>
        {hook.active ? 'ACTIVE' : 'OFF'}
      </div>
    </div>
  )
}

/* ── WebhooksTab ──────────────────────────────────────────────────────────── */
function WebhooksTab() {
  const [hooks, setHooks] = useState([])

  useEffect(() => {
    fetch('/api/hooks/list').then(r => r.json()).then(d => setHooks(d.hooks || [])).catch(() => {})
  }, [])

  const STUB_HOOKS = [
    { name: 'lead-created',    url: '/api/hooks/lead-created',    events: ['lead:created'],    active: true },
    { name: 'task-completed',  url: '/api/hooks/task-completed',  events: ['task:done'],       active: true },
    { name: 'revenue-event',   url: '/api/hooks/revenue-event',   events: ['revenue:event'],   active: true },
    { name: 'agent-error',     url: '/api/hooks/agent-error',     events: ['agent:error'],     active: false },
  ]

  const displayHooks = hooks.length ? hooks : STUB_HOOKS

  return (
    <div className="integ-tab-body">

      <div className="integ-info-banner">
        Rate limit and API token settings have moved to <strong>Settings → Security</strong>
      </div>

      {/* Inbound webhooks */}
      <div className="integ-section">
        <div className="integ-section-title">INBOUND WEBHOOK ENDPOINTS</div>
        <div className="integ-wh-head">
          <span>Name</span><span>URL</span><span>Events</span><span>Secret</span><span>Status</span>
        </div>
        {displayHooks.map(h => <WebhookRow key={h.name} hook={h} />)}
      </div>

      {/* Test sandbox */}
      <div className="integ-section">
        <TestSandbox />
      </div>

    </div>
  )
}

function TestSandbox() {
  const [payload, setPayload] = useState('{\n  "event": "lead:created",\n  "data": { "name": "Test Lead" }\n}')
  const [endpoint, setEndpoint] = useState('/api/hooks/lead-created')
  const [result, setResult] = useState(null)
  const [sending, setSending] = useState(false)

  const send = async () => {
    setSending(true)
    try {
      const body = JSON.parse(payload)
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json().catch(() => ({}))
      setResult({ status: r.status, body: d })
    } catch (e) {
      setResult({ error: e.message })
    }
    setSending(false)
  }

  return (
    <div className="integ-sandbox">
      <div className="integ-section-title">TEST SANDBOX — SEND A TEST WEBHOOK</div>
      <div className="integ-sandbox-row">
        <input className="integ-rl-input integ-sandbox-url" value={endpoint}
          onChange={e => setEndpoint(e.target.value)} placeholder="Endpoint URL" />
        <button className="integ-card-btn integ-card-btn--connect" onClick={send} disabled={sending}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>
      <textarea className="integ-sandbox-payload" value={payload} onChange={e => setPayload(e.target.value)} rows={5} />
      {result && (
        <div className={`integ-sandbox-result ${result.error ? 'integ-sandbox-result--err' : ''}`}>
          {result.error ? `Error: ${result.error}` : `${result.status} — ${JSON.stringify(result.body)}`}
        </div>
      )}
    </div>
  )
}

function MobilePairingTab() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [approving, setApproving] = useState(null)

  const loadStatus = async () => {
    setLoading(true)
    const data = await fetch('/api/mobile/status').then(r => r.json()).catch(() => null)
    setStatus(data)
    setLoading(false)
  }

  useEffect(() => {
    loadStatus()
    const timer = setInterval(loadStatus, 5000)
    return () => clearInterval(timer)
  }, [])

  const approve = async requestId => {
    setApproving(requestId)
    const res = await fetch(`/api/mobile/pair/${requestId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ownerApproved: true }),
    }).then(r => r.json()).catch(() => null)
    setApproving(null)
    if (res?.ok) {
      toastSuccess('Mobile device approved')
      loadStatus()
    } else {
      toastError(res?.error || 'Pairing approval failed')
    }
  }

  const pending = status?.pending_requests || []
  const approved = status?.approved_devices || []

  return (
    <div className="integ-tab-body">
      <div className="integ-info-banner">
        Mobile clients can connect only after owner approval. Use HTTPS outside a trusted local network.
      </div>

      <div className="integ-mobile-grid">
        <div className="integ-mobile-panel">
          <div className="integ-section-title">PENDING MOBILE PAIRING</div>
          {loading && <div className="integ-mobile-empty">Loading pairing requests…</div>}
          {!loading && pending.length === 0 && (
            <div className="integ-mobile-empty">No pending requests. Open the mobile app and enter this PC URL.</div>
          )}
          {pending.map(item => (
            <div key={item.id} className="integ-mobile-row">
              <div className="integ-mobile-main">
                <span className="integ-mobile-name">{item.device_name}</span>
                <span className="integ-mobile-meta">Requested {new Date(item.created_at).toLocaleTimeString()} · expires {new Date(item.expires_at).toLocaleTimeString()}</span>
              </div>
              <button className="integ-card-btn integ-card-btn--connect" onClick={() => approve(item.id)} disabled={approving === item.id}>
                {approving === item.id ? 'Approving…' : 'Approve'}
              </button>
            </div>
          ))}
        </div>

        <div className="integ-mobile-panel">
          <div className="integ-section-title">APPROVED DEVICES</div>
          {approved.length === 0 && <div className="integ-mobile-empty">No mobile devices approved yet.</div>}
          {approved.map(item => (
            <div key={item.id} className="integ-mobile-row integ-mobile-row--approved">
              <div className="integ-mobile-main">
                <span className="integ-mobile-name">{item.device_name || item.device_id}</span>
                <span className="integ-mobile-meta">Approved {item.approved_at ? new Date(item.approved_at).toLocaleString() : 'recently'}</span>
              </div>
              <span className="integ-mobile-status">PAIRED</span>
            </div>
          ))}
        </div>
      </div>

      <div className="integ-mobile-security">
        <span>Auth: {status?.security?.auth || 'jwt_refresh_rotation'}</span>
        <span>Storage: {status?.security?.storage || 'device_keychain_or_keystore'}</span>
        <span>Transport: {status?.security?.recommended_transport || 'https_or_trusted_lan'}</span>
      </div>
    </div>
  )
}

/* ── Root ─────────────────────────────────────────────────────────────────── */
export default function IntegrationsPage() {
  const [tab, setTab] = useState('connectors')
  return (
    <div className="integ-page">
      <div className="integ-header">
        <div className="integ-title-row">
          <span className="integ-title">INTEGRATIONS</span>
          <div className="integ-tabs">
            {TABS.map(t => (
              <button key={t.id} className={`integ-tab-btn ${tab === t.id ? 'integ-tab-btn--active' : ''}`}
                onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tab === 'connectors' && <ConnectorsTab />}
      {tab === 'mobile'     && <MobilePairingTab />}
      {tab === 'webhooks'   && <WebhooksTab />}
    </div>
  )
}
