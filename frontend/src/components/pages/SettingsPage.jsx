import { useState, useEffect } from 'react'
import { Panel, SectionLabel, HexButton, StatusPill } from '../nexus-ui'
import './SettingsPage.css'

export default function SettingsPage() {
  const [apiKeys, setApiKeys] = useState({
    anthropic: '',
    openrouter: '',
    ollama_endpoint: 'http://localhost:11434',
  })

  const [llmSettings, setLlmSettings] = useState({
    provider: 'anthropic', // 'anthropic' | 'ollama' | 'openrouter'
    model: 'claude-3-5-sonnet',
    temperature: 0.7,
    maxTokens: 2048,
  })

  const [unsavedChanges, setUnsavedChanges] = useState(false)
  const [saveStatus, setSaveStatus] = useState(null) // 'saving' | 'success' | 'error'
  const [testStatus, setTestStatus] = useState({}) // { provider: 'testing' | 'ok' | 'error' }

  // Load settings on mount
  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/settings')
      if (res.ok) {
        const data = await res.json()
        setApiKeys(data.apiKeys || apiKeys)
        setLlmSettings(data.llmSettings || llmSettings)
      }
    } catch (e) {
      console.error('Failed to fetch settings:', e)
    }
  }

  const handleApiKeyChange = (provider, value) => {
    setApiKeys(prev => ({ ...prev, [provider]: value }))
    setUnsavedChanges(true)
  }

  const handleLlmSettingChange = (key, value) => {
    setLlmSettings(prev => ({ ...prev, [key]: value }))
    setUnsavedChanges(true)
  }

  const saveSettings = async () => {
    setSaveStatus('saving')
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKeys, llmSettings }),
      })
      if (res.ok) {
        setSaveStatus('success')
        setUnsavedChanges(false)
        setTimeout(() => setSaveStatus(null), 3000)
      } else {
        setSaveStatus('error')
      }
    } catch (e) {
      console.error('Failed to save settings:', e)
      setSaveStatus('error')
    }
  }

  const testConnection = async (provider) => {
    setTestStatus(prev => ({ ...prev, [provider]: 'testing' }))
    try {
      const res = await fetch(`/api/settings/test/${provider}`)
      if (res.ok) {
        setTestStatus(prev => ({ ...prev, [provider]: 'ok' }))
        setTimeout(() => setTestStatus(prev => ({ ...prev, [provider]: null })), 3000)
      } else {
        setTestStatus(prev => ({ ...prev, [provider]: 'error' }))
      }
    } catch (e) {
      console.error(`Failed to test ${provider}:`, e)
      setTestStatus(prev => ({ ...prev, [provider]: 'error' }))
    }
  }

  return (
    <div className="sg-grid">
      {/* Header */}
      <div className="sg-header">
        <h1 className="sg-title">⚙️ System Settings</h1>
        <p className="sg-subtitle">Configure API keys, LLM provider, and system behavior</p>
      </div>

      {/* API Keys Section */}
      <Panel icon="🔑" title="API Keys" className="sg-panel">
        <div className="sg-form">
          {/* Anthropic */}
          <div className="sg-field">
            <label className="sg-label">
              Anthropic API Key
              <span className="sg-hint">https://console.anthropic.com</span>
            </label>
            <input
              type="password"
              value={apiKeys.anthropic}
              onChange={e => handleApiKeyChange('anthropic', e.target.value)}
              placeholder="sk-ant-..."
              className="sg-input"
            />
            <div className="sg-actions">
              <HexButton
                size="sm"
                variant="outline"
                onClick={() => testConnection('anthropic')}
                disabled={testStatus.anthropic === 'testing'}
              >
                {testStatus.anthropic === 'testing' ? 'Testing...' :
                 testStatus.anthropic === 'ok' ? '✓ Connected' :
                 testStatus.anthropic === 'error' ? '✗ Failed' :
                 'Test Connection'}
              </HexButton>
            </div>
          </div>

          {/* OpenRouter */}
          <div className="sg-field">
            <label className="sg-label">
              OpenRouter API Key (Fallback)
              <span className="sg-hint">https://openrouter.ai</span>
            </label>
            <input
              type="password"
              value={apiKeys.openrouter}
              onChange={e => handleApiKeyChange('openrouter', e.target.value)}
              placeholder="sk-or-..."
              className="sg-input"
            />
            <div className="sg-actions">
              <HexButton
                size="sm"
                variant="outline"
                onClick={() => testConnection('openrouter')}
                disabled={testStatus.openrouter === 'testing'}
              >
                {testStatus.openrouter === 'testing' ? 'Testing...' :
                 testStatus.openrouter === 'ok' ? '✓ Connected' :
                 testStatus.openrouter === 'error' ? '✗ Failed' :
                 'Test Connection'}
              </HexButton>
            </div>
          </div>

          {/* Ollama */}
          <div className="sg-field">
            <label className="sg-label">
              Ollama Endpoint
              <span className="sg-hint">Local LLM server (https://ollama.ai)</span>
            </label>
            <input
              type="text"
              value={apiKeys.ollama_endpoint}
              onChange={e => handleApiKeyChange('ollama_endpoint', e.target.value)}
              placeholder="http://localhost:11434"
              className="sg-input"
            />
            <div className="sg-actions">
              <HexButton
                size="sm"
                variant="outline"
                onClick={() => testConnection('ollama')}
                disabled={testStatus.ollama === 'testing'}
              >
                {testStatus.ollama === 'testing' ? 'Testing...' :
                 testStatus.ollama === 'ok' ? '✓ Connected' :
                 testStatus.ollama === 'error' ? '✗ Failed' :
                 'Test Connection'}
              </HexButton>
            </div>
          </div>
        </div>
      </Panel>

      {/* LLM Settings Section */}
      <Panel icon="🧠" title="LLM Configuration" className="sg-panel">
        <div className="sg-form">
          {/* Provider Selection */}
          <div className="sg-field">
            <label className="sg-label">LLM Provider</label>
            <select
              value={llmSettings.provider}
              onChange={e => handleLlmSettingChange('provider', e.target.value)}
              className="sg-select"
            >
              <option value="anthropic">Anthropic Claude</option>
              <option value="ollama">Local Ollama</option>
              <option value="openrouter">OpenRouter (Fallback)</option>
            </select>
            <p className="sg-help">
              {llmSettings.provider === 'anthropic' && 'Using Anthropic Claude API'}
              {llmSettings.provider === 'ollama' && 'Using local Ollama instance (cost-free)'}
              {llmSettings.provider === 'openrouter' && 'Using OpenRouter API (fallback)'}
            </p>
          </div>

          {/* Model Selection */}
          <div className="sg-field">
            <label className="sg-label">Model</label>
            <select
              value={llmSettings.model}
              onChange={e => handleLlmSettingChange('model', e.target.value)}
              className="sg-select"
            >
              {llmSettings.provider === 'anthropic' && (
                <>
                  <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
                  <option value="claude-3-opus">Claude 3 Opus</option>
                  <option value="claude-3-haiku">Claude 3 Haiku</option>
                </>
              )}
              {llmSettings.provider === 'ollama' && (
                <>
                  <option value="llama2">Llama 2</option>
                  <option value="mistral">Mistral</option>
                  <option value="neural-chat">Neural Chat</option>
                </>
              )}
              {llmSettings.provider === 'openrouter' && (
                <option value="auto">Auto (best available)</option>
              )}
            </select>
          </div>

          {/* Temperature */}
          <div className="sg-field">
            <label className="sg-label">
              Temperature: {llmSettings.temperature.toFixed(1)}
              <span className="sg-hint">0.0 = deterministic, 1.0 = creative</span>
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={llmSettings.temperature}
              onChange={e => handleLlmSettingChange('temperature', parseFloat(e.target.value))}
              className="sg-slider"
            />
          </div>

          {/* Max Tokens */}
          <div className="sg-field">
            <label className="sg-label">
              Max Tokens: {llmSettings.maxTokens}
              <span className="sg-hint">Max output length</span>
            </label>
            <input
              type="range"
              min="256"
              max="4096"
              step="256"
              value={llmSettings.maxTokens}
              onChange={e => handleLlmSettingChange('maxTokens', parseInt(e.target.value))}
              className="sg-slider"
            />
          </div>
        </div>
      </Panel>

      {/* Save Button */}
      <div className="sg-footer">
        {unsavedChanges && (
          <StatusPill tone="warning" label="Unsaved Changes" size="sm" />
        )}
        {saveStatus === 'success' && (
          <StatusPill tone="success" label="✓ Settings Saved" size="sm" />
        )}
        {saveStatus === 'error' && (
          <StatusPill tone="alert" label="✗ Save Failed" size="sm" />
        )}
        <HexButton
          onClick={saveSettings}
          disabled={!unsavedChanges || saveStatus === 'saving'}
          variant="primary"
          tone="gold"
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save Settings'}
        </HexButton>
      </div>
    </div>
  )
}
