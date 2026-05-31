import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxField, NxSaveBtn, useSave, SafetyConfirmModal } from './controls'

/* ── Tab 6: SECURITY ───────────────────────────────────────────────────── */

const SCOPE_OPTIONS = ['read', 'write', 'admin']
const EXPIRY_OPTIONS = [{ label: '30 days', value: '30d' }, { label: '90 days', value: '90d' }, { label: '1 year', value: '1y' }, { label: 'Never', value: 'never' }]

function ApiTokensSection() {
  const [tokens, setTokens] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', scopes: [], expiry: '90d' })
  const [creating, setCreating] = useState(false)
  const [newSecret, setNewSecret] = useState(null)
  const [pendingTokenAction, setPendingTokenAction] = useState(null)

  useEffect(() => {
    api.get('/api/security/api-keys').then(d => setTokens(Array.isArray(d?.keys) ? d.keys : [])).catch(() => {})
  }, [])

  const toggleScope = s => setForm(p => ({
    ...p, scopes: p.scopes.includes(s) ? p.scopes.filter(x => x !== s) : [...p.scopes, s]
  }))

  const createToken = async () => {
    setCreating(true)
    try {
      const d = await api.post('/api/security/api-keys', form)
      if (d?.key) setNewSecret(d.key)
      const updated = await api.get('/api/security/api-keys').catch(() => null)
      if (updated?.keys) setTokens(updated.keys)
      setForm({ name: '', scopes: [], expiry: '90d' })
      setShowForm(false)
    } catch {}
    setCreating(false)
  }

  const rotate = async id => {
    setPendingTokenAction({
      id,
      label: 'ROTATE API TOKEN',
      warning: 'The current API key will stop working immediately.',
      confirmText: 'ROTATE API TOKEN',
      endpoint: `POST /api/security/api-keys/${id}/rotate`,
      risk: 'medium',
      run: async () => api.post(`/api/security/api-keys/${id}/rotate`, {}),
    })
  }

  const revoke = async id => {
    setPendingTokenAction({
      id,
      label: 'REVOKE API TOKEN',
      warning: 'This API token will be permanently revoked.',
      confirmText: 'REVOKE API TOKEN',
      endpoint: `DELETE /api/security/api-keys/${id}`,
      risk: 'high',
      run: async () => api.delete(`/api/security/api-keys/${id}`),
    })
  }

  const confirmTokenAction = async (_action, safety) => {
    const action = pendingTokenAction
    setPendingTokenAction(null)
    if (!action) return
    await action.run().catch(() => {})
    await api.post('/api/admin/safety-audit', {
      label: action.label,
      endpoint: action.endpoint,
      reason: safety.reason,
      confirmation: safety.confirmation,
      risk: action.risk,
      executed: true,
      execution_mode: `ui_confirmed:${action.label}`,
    }).catch(() => {})
    const d = await api.get('/api/security/api-keys').catch(() => null)
    if (d?.keys) setTokens(d.keys)
  }

  return (
    <div className="nx-section">
      {pendingTokenAction && (
        <SafetyConfirmModal
          action={pendingTokenAction}
          onConfirm={confirmTokenAction}
          onCancel={() => setPendingTokenAction(null)}
        />
      )}
      <div className="nx-section-label">API TOKENS</div>
      {newSecret && (
        <div className="nx-sec-secret-reveal">
          <span className="nx-sec-secret-label">New token (copy now — shown once):</span>
          <code className="nx-sec-secret-val">{newSecret}</code>
          <button className="nx-save-btn nx-save-btn--outline" onClick={() => { navigator.clipboard.writeText(newSecret); setNewSecret(null) }}>COPY & DISMISS</button>
        </div>
      )}
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--tokens">
          <span>Name</span><span>Scopes</span><span>Last Used</span><span>Expires</span><span>Actions</span>
        </div>
        {tokens.length === 0 && <div className="nx-sec-empty">No API tokens — generate one below</div>}
        {tokens.map(t => (
          <div key={t.id} className="nx-sec-row nx-sec-row--tokens">
            <span className="nx-sec-name">{t.name}</span>
            <span className="nx-sec-scopes">{(t.scopes || []).join(', ') || '—'}</span>
            <span className="nx-sec-muted">{t.last_used ? new Date(t.last_used).toLocaleDateString() : 'Never'}</span>
            <span className={`nx-sec-muted ${t.expired ? 'nx-sec-expired' : ''}`}>
              {t.expiry ? new Date(t.expiry).toLocaleDateString() : '∞'}
            </span>
            <div className="nx-sec-actions">
              <button className="nx-save-btn nx-save-btn--outline nx-save-btn--xs" onClick={() => rotate(t.id)}>Rotate</button>
              <button className="nx-save-btn nx-save-btn--danger nx-save-btn--xs" onClick={() => revoke(t.id)}>Revoke</button>
            </div>
          </div>
        ))}
      </div>
      <button className="nx-save-btn nx-save-btn--outline" style={{ marginTop: 12 }} onClick={() => setShowForm(v => !v)}>
        {showForm ? 'CANCEL' : '+ GENERATE NEW TOKEN'}
      </button>
      {showForm && (
        <div className="nx-sec-token-form">
          <div className="nx-form-grid">
            <NxField label="TOKEN NAME">
              <input className="nx-input" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. CI pipeline key" />
            </NxField>
            <NxField label="EXPIRY">
              <select className="nx-input" value={form.expiry} onChange={e => setForm(p => ({ ...p, expiry: e.target.value }))}>
                {EXPIRY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </NxField>
          </div>
          <div className="nx-sec-scopes-row">
            <span className="nx-field-label">SCOPES</span>
            {SCOPE_OPTIONS.map(s => (
              <label key={s} className="nx-sec-scope-label">
                <input type="checkbox" className="nx-sec-checkbox" checked={form.scopes.includes(s)} onChange={() => toggleScope(s)} />
                {s}
              </label>
            ))}
          </div>
          <NxSaveBtn label="CREATE TOKEN" saving={creating} saved={false} onClick={createToken} />
        </div>
      )}
    </div>
  )
}

function JwtSection() {
  const [cfg, setCfg] = useState({ token_ttl: 60, refresh_ttl: 7 })
  const [rotating, setRotating] = useState(false)
  const [rotated, setRotated] = useState(false)
  const [pendingJwtRotate, setPendingJwtRotate] = useState(null)
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings/llm', cfg)

  const rotateJwt = async () => {
    setPendingJwtRotate({
      label: 'ROTATE JWT SECRET',
      warning: 'This invalidates all active sessions. Users will be logged out.',
      confirmText: 'ROTATE JWT SECRET',
      endpoint: 'POST /api/security/rotate-jwt',
      risk: 'critical',
    })
  }

  const confirmJwtRotate = async (_action, safety) => {
    setPendingJwtRotate(null)
    setRotating(true)
    await api.post('/api/security/rotate-jwt', {}).catch(() => {})
    await api.post('/api/admin/safety-audit', {
      label: 'ROTATE JWT SECRET',
      endpoint: 'POST /api/security/rotate-jwt',
      reason: safety.reason,
      confirmation: safety.confirmation,
      risk: 'critical',
      executed: true,
    }).catch(() => {})
    setRotating(false); setRotated(true)
    setTimeout(() => setRotated(false), 3000)
  }

  return (
    <div className="nx-section">
      {pendingJwtRotate && (
        <SafetyConfirmModal
          action={pendingJwtRotate}
          onConfirm={confirmJwtRotate}
          onCancel={() => setPendingJwtRotate(null)}
        />
      )}
      <div className="nx-section-label">JWT SETTINGS</div>
      <div className="nx-form-grid">
        <NxField label="TOKEN TTL (MINUTES)">
          <input className="nx-input" type="number" min={5} max={1440} value={cfg.token_ttl} onChange={e => set('token_ttl', +e.target.value)} />
        </NxField>
        <NxField label="REFRESH TTL (DAYS)">
          <input className="nx-input" type="number" min={1} max={90} value={cfg.refresh_ttl} onChange={e => set('refresh_ttl', +e.target.value)} />
        </NxField>
      </div>
      <div className="nx-btn-row">
        <NxSaveBtn label="SAVE JWT SETTINGS" saving={saving} saved={saved} onClick={save} />
        <button className="nx-save-btn nx-save-btn--danger" onClick={rotateJwt} disabled={rotating}>
          {rotated ? '✓ SECRET ROTATED' : rotating ? 'ROTATING…' : 'ROTATE JWT SECRET'}
        </button>
      </div>
    </div>
  )
}

function RateLimitsSection() {
  const [limits, setLimits] = useState([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/api/security/rate-limits').then(d => setLimits(Array.isArray(d?.limits) ? d.limits : [
      { endpoint: '/api/chat',        rpm: 30,  burst: 5  },
      { endpoint: '/api/tasks/run',   rpm: 60,  burst: 10 },
      { endpoint: '/api/auth/login',  rpm: 5,   burst: 3  },
      { endpoint: '/api/auth/register', rpm: 3, burst: 2  },
      { endpoint: '/api/admin/*',     rpm: 20,  burst: 5  },
    ])).catch(() => {})
  }, [])

  const update = (i, k, v) => setLimits(p => p.map((r, idx) => idx === i ? { ...r, [k]: +v } : r))

  const save = async () => {
    setSaving(true)
    await api.put('/api/security/rate-limits', { limits }).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">RATE LIMITS</div>
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--rl">
          <span>Endpoint</span><span>Req / min</span><span>Burst</span>
        </div>
        {limits.map((r, i) => (
          <div key={r.endpoint} className="nx-sec-row nx-sec-row--rl">
            <span className="nx-sec-endpoint">{r.endpoint}</span>
            <input className="nx-input nx-input--sm" type="number" min={1} max={1000} value={r.rpm}   onChange={e => update(i, 'rpm',   e.target.value)} />
            <input className="nx-input nx-input--sm" type="number" min={1} max={100}  value={r.burst} onChange={e => update(i, 'burst', e.target.value)} />
          </div>
        ))}
      </div>
      <NxSaveBtn label="SAVE RATE LIMITS" saving={saving} saved={saved} onClick={save} />
    </div>
  )
}

function ActiveSessionsSection() {
  const [sessions, setSessions] = useState([])
  const [revoking, setRevoking] = useState(null)
  const [revokingAll, setRevokingAll] = useState(false)
  const [err, setErr] = useState(null)
  const [pendingSessionAction, setPendingSessionAction] = useState(null)

  const load = () => {
    setErr(null)
    api.get('/api/sessions')
      .then(d => setSessions(Array.isArray(d?.sessions) ? d.sessions : []))
      .catch(e => setErr(e.message || 'Failed to load sessions'))
  }
  useEffect(() => { load() }, [])

  const revokeOne = async sessionId => {
    setPendingSessionAction({
      label: 'REVOKE SESSION',
      warning: 'This session will be revoked immediately.',
      confirmText: 'REVOKE SESSION',
      endpoint: `DELETE /api/sessions/${sessionId}`,
      risk: 'medium',
      sessionId,
      all: false,
    })
  }

  const revokeAll = async () => {
    setPendingSessionAction({
      label: 'REVOKE ALL OTHER SESSIONS',
      warning: 'All other sessions will be logged out. This device will stay active.',
      confirmText: 'REVOKE ALL OTHER SESSIONS',
      endpoint: 'DELETE /api/sessions',
      risk: 'high',
      all: true,
    })
  }

  const confirmSessionAction = async (action, safety) => {
    setPendingSessionAction(null)
    if (action.all) {
      setRevokingAll(true)
      await api.delete('/api/sessions').catch(() => {})
      setSessions(p => p.filter(s => s.current))
      setRevokingAll(false)
    } else {
      const sessionId = action.sessionId
      setRevoking(sessionId)
      await api.delete(`/api/sessions/${sessionId}`).catch(() => {})
      setSessions(p => p.filter(s => s.session_id !== sessionId))
      setRevoking(null)
    }
    await api.post('/api/admin/safety-audit', {
      label: action.label,
      endpoint: action.endpoint,
      reason: safety.reason,
      confirmation: safety.confirmation,
      risk: action.risk,
      executed: true,
    }).catch(() => {})
  }

  const otherCount = sessions.filter(s => !s.current).length

  return (
    <div className="nx-section">
      {pendingSessionAction && (
        <SafetyConfirmModal
          action={pendingSessionAction}
          onConfirm={confirmSessionAction}
          onCancel={() => setPendingSessionAction(null)}
        />
      )}
      <div className="nx-section-label">ACTIVE SESSIONS</div>
      {err && <div className="nx-badge nx-badge--err" style={{ marginBottom: 8 }}>{err}</div>}
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--sessions">
          <span>Device</span><span>Created</span><span>Last Used</span><span>Action</span>
        </div>
        {sessions.length === 0 && <div className="nx-sec-empty">No active sessions found</div>}
        {sessions.map(s => (
          <div key={s.session_id} className="nx-sec-row nx-sec-row--sessions">
            <span className="nx-sec-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {s.device_hint || 'unknown'}
              {s.current && <span className="nx-badge nx-badge--ok" style={{ fontSize: 10, padding: '1px 6px' }}>This device</span>}
            </span>
            <span className="nx-sec-muted">{s.created_at ? new Date(s.created_at).toLocaleString() : '—'}</span>
            <span className="nx-sec-muted">{s.last_used ? new Date(s.last_used).toLocaleString() : '—'}</span>
            {s.current
              ? <span className="nx-sec-muted" style={{ fontSize: 11 }}>current</span>
              : <button
                  className="nx-save-btn nx-save-btn--danger nx-save-btn--xs"
                  onClick={() => revokeOne(s.session_id)}
                  disabled={revoking === s.session_id}
                >
                  {revoking === s.session_id ? '…' : 'Revoke'}
                </button>
            }
          </div>
        ))}
      </div>
      {otherCount > 0 && (
        <button
          className="nx-save-btn nx-save-btn--danger"
          style={{ marginTop: 12 }}
          onClick={revokeAll}
          disabled={revokingAll}
        >
          {revokingAll ? 'REVOKING…' : `REVOKE ALL OTHER SESSIONS (${otherCount})`}
        </button>
      )}
    </div>
  )
}

function SecurityTab() {
  return (
    <div className="nx-tab-content">
      <ApiTokensSection />
      <div className="nx-divider" />
      <JwtSection />
      <div className="nx-divider" />
      <RateLimitsSection />
      <div className="nx-divider" />
      <ActiveSessionsSection />
    </div>
  )
}

export default SecurityTab
