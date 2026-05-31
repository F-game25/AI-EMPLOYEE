import { useState } from 'react'
import api from '../../../api/client'
import { NxToggle, NxSaveBtn } from './controls'

const INTEGRATIONS = [
  { id: 'slack',      label: 'Slack',      icon: '💬', type: 'url',      placeholder: 'https://hooks.slack.com/…'  },
  { id: 'github',     label: 'GitHub',     icon: '🐙', type: 'password', placeholder: 'ghp_…'                      },
  { id: 'notion',     label: 'Notion',     icon: '📝', type: 'password', placeholder: 'secret_…'                   },
  { id: 'zapier',     label: 'Zapier',     icon: '⚡', type: 'url',      placeholder: 'https://hooks.zapier.com/…' },
  { id: 'stripe',     label: 'Stripe',     icon: '💳', type: 'password', placeholder: 'sk_live_…'                  },
  { id: 'postgresql', label: 'PostgreSQL', icon: '🐘', type: 'text',     placeholder: 'postgresql://…'             },
]

function IntegrationCard({ integration }) {
  const [enabled, setEnabled] = useState(false)
  const [value, setValue] = useState('')
  return (
    <div className={`nx-int-card ${enabled ? 'nx-int-card--on' : ''}`}>
      <div className="nx-int-header">
        <span className="nx-int-icon">{integration.icon}</span>
        <span className="nx-int-name">{integration.label}</span>
        <NxToggle checked={enabled} onChange={setEnabled} />
      </div>
      {enabled && (
        <div className="nx-int-body">
          <input
            className="nx-input"
            type={integration.type}
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder={integration.placeholder}
            autoComplete="off"
          />
        </div>
      )}
    </div>
  )
}

export default function IntegrationsTab() {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const saveAll = async () => {
    setSaving(true)
    await api.post('/api/settings', {}).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">CONNECTED SERVICES</div>
        <div className="nx-int-grid">
          {INTEGRATIONS.map(i => <IntegrationCard key={i.id} integration={i} />)}
        </div>
        <NxSaveBtn label="SAVE INTEGRATIONS" saving={saving} saved={saved} onClick={saveAll} />
      </div>
    </div>
  )
}
