import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxField, NxSaveBtn, NxSlider } from './controls'

const NOTIF_EVENTS = ['security:breach', 'task:failed', 'agent:error', 'hitl:request', 'revenue:event', 'system:critical']
const NOTIF_CHANNELS = ['toast', 'email', 'webhook']
const CHANNEL_LABELS = { toast: 'In-app toast', email: 'Email', webhook: 'Webhook' }

export default function NotificationsTab() {
  const [matrix, setMatrix] = useState(() => {
    const m = {}
    NOTIF_EVENTS.forEach(ev => { m[ev] = {}; NOTIF_CHANNELS.forEach(ch => { m[ev][ch] = false }) })
    return m
  })
  const [emailCfg, setEmailCfg] = useState({ address: '', test_sending: false })
  const [webhookCfg, setWebhookCfg] = useState({ url: '', secret: '' })
  const [thresholds, setThresholds] = useState({ threat_score: 75, cost_per_day: 50 })
  const [savingMatrix, setSavingMatrix] = useState(false)
  const [savedMatrix, setSavedMatrix] = useState(false)
  const [testingEmail, setTestingEmail] = useState(false)
  const [testingWebhook, setTestingWebhook] = useState(false)

  useEffect(() => {
    api.get('/api/settings/notifications').then(d => {
      if (d?.matrix) setMatrix(d.matrix)
      if (d?.email) setEmailCfg(p => ({ ...p, ...d.email }))
      if (d?.webhook) setWebhookCfg(p => ({ ...p, ...d.webhook }))
      if (d?.thresholds) setThresholds(p => ({ ...p, ...d.thresholds }))
    }).catch(() => {})
  }, [])

  const toggle = (ev, ch) => setMatrix(p => ({ ...p, [ev]: { ...p[ev], [ch]: !p[ev][ch] } }))

  const saveMatrix = async () => {
    setSavingMatrix(true)
    await api.put('/api/settings/notifications', { matrix, email: emailCfg, webhook: webhookCfg, thresholds }).catch(() => {})
    setSavingMatrix(false); setSavedMatrix(true)
    setTimeout(() => setSavedMatrix(false), 2000)
  }

  const testEmail = async () => {
    setTestingEmail(true)
    await api.post('/api/settings/notifications/test-email', { address: emailCfg.address }).catch(() => {})
    setTestingEmail(false)
  }

  const testWebhook = async () => {
    setTestingWebhook(true)
    await api.post('/api/settings/notifications/test-webhook', { url: webhookCfg.url }).catch(() => {})
    setTestingWebhook(false)
  }

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">NOTIFICATION MATRIX</div>
        <div className="nx-notif-matrix">
          <div className="nx-notif-header-row">
            <span className="nx-notif-event-col">Event</span>
            {NOTIF_CHANNELS.map(ch => <span key={ch} className="nx-notif-ch-col">{CHANNEL_LABELS[ch]}</span>)}
          </div>
          {NOTIF_EVENTS.map(ev => (
            <div key={ev} className="nx-notif-row">
              <span className="nx-notif-event-col nx-sec-mono">{ev}</span>
              {NOTIF_CHANNELS.map(ch => (
                <span key={ch} className="nx-notif-ch-col">
                  <input type="checkbox" className="nx-sec-checkbox" checked={matrix[ev]?.[ch] || false} onChange={() => toggle(ev, ch)} />
                </span>
              ))}
            </div>
          ))}
        </div>
        <NxSaveBtn label="SAVE NOTIFICATION SETTINGS" saving={savingMatrix} saved={savedMatrix} onClick={saveMatrix} />
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">EMAIL CONFIG</div>
        <div className="nx-form-grid">
          <NxField label="ALERT EMAIL ADDRESS" full>
            <div className="nx-btn-row" style={{ gap: 8 }}>
              <input className="nx-input" type="email" value={emailCfg.address} onChange={e => setEmailCfg(p => ({ ...p, address: e.target.value }))} placeholder="alerts@yourcompany.com" />
              <button className="nx-save-btn nx-save-btn--outline" onClick={testEmail} disabled={testingEmail || !emailCfg.address}>
                {testingEmail ? 'SENDING…' : 'SEND TEST'}
              </button>
            </div>
          </NxField>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">WEBHOOK CONFIG</div>
        <div className="nx-form-grid">
          <NxField label="OUTBOUND WEBHOOK URL" full>
            <div className="nx-btn-row" style={{ gap: 8 }}>
              <input className="nx-input" type="url" value={webhookCfg.url} onChange={e => setWebhookCfg(p => ({ ...p, url: e.target.value }))} placeholder="https://…" />
              <button className="nx-save-btn nx-save-btn--outline" onClick={testWebhook} disabled={testingWebhook || !webhookCfg.url}>
                {testingWebhook ? 'SENDING…' : 'SEND TEST'}
              </button>
            </div>
          </NxField>
          <NxField label="WEBHOOK SECRET">
            <input className="nx-input" type="password" value={webhookCfg.secret} onChange={e => setWebhookCfg(p => ({ ...p, secret: e.target.value }))} placeholder="hmac-secret" autoComplete="off" />
          </NxField>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">ALERT THRESHOLDS</div>
        <div className="nx-form-grid">
          <NxField label={`THREAT SCORE THRESHOLD — ${thresholds.threat_score}`} full>
            <NxSlider value={thresholds.threat_score} min={0} max={100} step={1} onChange={v => setThresholds(p => ({ ...p, threat_score: v }))} format={v => v} />
          </NxField>
          <NxField label="COST PER DAY THRESHOLD ($)">
            <input className="nx-input" type="number" min={0} value={thresholds.cost_per_day} onChange={e => setThresholds(p => ({ ...p, cost_per_day: +e.target.value }))} />
          </NxField>
        </div>
      </div>
    </div>
  )
}
