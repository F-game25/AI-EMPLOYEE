import { useState, useEffect } from 'react'
import { Panel } from '../nexus-ui'
import HexButton from '../nexus-ui/HexButton'
import ApiKeysTab from './ApiKeysTab'
import LlmSettingsTab from './LlmSettingsTab'
import WorkspaceTab from './WorkspaceTab'
import NotificationsTab from './NotificationsTab'
import SecurityTab from './SecurityTab'
import AdvancedTab from './AdvancedTab'
import './SettingsPage.css'

const TABS = [
  { id: 'api-keys', label: 'API Keys', icon: '🔑' },
  { id: 'llm', label: 'LLM Settings', icon: '⚙️' },
  { id: 'workspace', label: 'Workspace', icon: '📁' },
  { id: 'notifications', label: 'Notifications', icon: '🔔' },
  { id: 'security', label: 'Security', icon: '🔒' },
  { id: 'advanced', label: 'Advanced', icon: '⚡' },
]

const INITIAL_SETTINGS = {
  provider: 'anthropic',
  anthropic_key: '',
  openrouter_key: '',
  ollama_endpoint: '',
  llm_provider: 'anthropic',
  model: 'claude-3-5-sonnet',
  temperature: 0.7,
  max_tokens: 2048,
  top_p: 0.9,
  top_k: 40,
  ollama_model: '',
  max_file_size_mb: 50,
  max_files: 20,
  allowed_file_types: ['.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.txt', '.json', '.sh', '.css', '.html', '.sql'],
  email_notifications_enabled: false,
  email_alert: '',
  slack_notifications_enabled: false,
  slack_webhook: '',
  multi_tenancy_enabled: true,
  audit_logging_enabled: true,
  require_mfa: false,
  session_timeout_minutes: 60,
  password_policy: '12chars_special_number_uppercase',
  pipeline_strict_mode: false,
  experimental_features: false,
  log_level: 'INFO',
  cache_size_mb: 500,
  max_concurrent_tasks: 10,
  retry_attempts: 3,
  retry_delay_seconds: 5,
  custom_headers: {},
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('api-keys')
  const [settings, setSettings] = useState(INITIAL_SETTINGS)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState(null)

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await fetch('/api/settings')
        if (res.ok) {
          const data = await res.json()
          setSettings(s => ({ ...s, ...data }))
        }
      } catch (err) {
        console.error('Failed to load settings:', err)
      } finally {
        setIsLoading(false)
      }
    }

    loadSettings()
  }, [])

  useEffect(() => {
    // Scroll to top on tab change
    const tabPanel = document.querySelector('.settings-page__content')
    if (tabPanel) {
      tabPanel.scrollTop = 0
    }
  }, [activeTab])

  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
  }

  const handleSaveTab = async (tabSettings) => {
    setIsSaving(true)
    setSaveStatus(null)

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...settings,
          ...tabSettings,
        }),
      })

      if (res.ok) {
        const updated = await res.json()
        setSettings(s => ({ ...s, ...updated }))
        setSaveStatus({ type: 'success', message: 'Settings saved successfully' })
        setTimeout(() => setSaveStatus(null), 3000)
      } else {
        setSaveStatus({ type: 'error', message: 'Failed to save settings' })
      }
    } catch (err) {
      setSaveStatus({ type: 'error', message: err.message })
    } finally {
      setIsSaving(false)
    }
  }

  const currentTab = TABS.find(t => t.id === activeTab)

  return (
    <div className="settings-page">
      <div className="settings-page__header">
        <h1 className="settings-page__title">Settings</h1>
        <p className="settings-page__subtitle">Configure system behavior, integrations, and security</p>
      </div>

      <div className="settings-page__container">
        <nav className="settings-page__tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`settings-page__tab ${activeTab === tab.id ? 'settings-page__tab--active' : ''}`}
              onClick={() => handleTabChange(tab.id)}
              title={tab.label}
            >
              <span className="settings-page__tab-icon">{tab.icon}</span>
              <span className="settings-page__tab-label">{tab.label}</span>
            </button>
          ))}
        </nav>

        <Panel
          title={currentTab?.label}
          icon={currentTab?.icon}
          corners={false}
          size="airy"
          className="settings-page__panel"
        >
          <div className="settings-page__content">
            {isLoading ? (
              <div className="settings-page__loading">Loading settings...</div>
            ) : (
              <>
                {activeTab === 'api-keys' && (
                  <ApiKeysTab settings={settings} onChange={handleSaveTab} />
                )}
                {activeTab === 'llm' && (
                  <LlmSettingsTab settings={settings} onChange={handleSaveTab} />
                )}
                {activeTab === 'workspace' && (
                  <WorkspaceTab settings={settings} onChange={handleSaveTab} />
                )}
                {activeTab === 'notifications' && (
                  <NotificationsTab settings={settings} onChange={handleSaveTab} />
                )}
                {activeTab === 'security' && (
                  <SecurityTab settings={settings} onChange={handleSaveTab} />
                )}
                {activeTab === 'advanced' && (
                  <AdvancedTab settings={settings} onChange={handleSaveTab} />
                )}
              </>
            )}
          </div>

          {saveStatus && (
            <div className={`settings-page__status settings-page__status--${saveStatus.type}`}>
              {saveStatus.message}
            </div>
          )}

          <div className="settings-page__footer">
            <HexButton
              type="submit"
              variant="primary"
              loading={isSaving}
              disabled={isSaving}
              onClick={() => {
                const form = document.querySelector('.settings-form')
                if (form) form.dispatchEvent(new Event('submit', { bubbles: true }))
              }}
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </HexButton>
          </div>
        </Panel>
      </div>
    </div>
  )
}
