import { useState } from 'react'
import { HexButton } from '../nexus-ui'
import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './ApiKeysTab.css'

const VALIDATORS = {
  anthropic_key: (val) => {
    if (!val) return 'API key required'
    if (!val.startsWith('sk-ant-')) return 'Must start with sk-ant-'
    return null
  },
  openrouter_key: (val) => {
    if (!val) return 'API key required'
    if (!val.startsWith('sk-or-')) return 'Must start with sk-or-'
    return null
  },
  ollama_endpoint: (val) => {
    if (!val) return 'Endpoint required'
    try {
      new URL(val)
    } catch {
      return 'Must be a valid URL'
    }
    return null
  },
}

export default function ApiKeysTab({ settings = {}, onChange }) {
  const [showKeys, setShowKeys] = useState({
    anthropic: false,
    openrouter: false,
  })
  const [testingProvider, setTestingProvider] = useState(null)
  const [testResult, setTestResult] = useState(null)

  const form = useFormState(
    {
      provider: settings.provider || 'anthropic',
      anthropic_key: settings.anthropic_key || '',
      openrouter_key: settings.openrouter_key || '',
      ollama_endpoint: settings.ollama_endpoint || '',
    },
    (key, val) => VALIDATORS[key]?.(val) || null
  )

  const handleProviderChange = (e) => {
    const newProvider = e.target.value
    form.setField('provider', newProvider)
    form.setError(newProvider === 'anthropic' ? 'anthropic_key' : newProvider === 'openrouter' ? 'openrouter_key' : 'ollama_endpoint', null)
  }

  const toggleShowKey = (provider) => {
    setShowKeys(s => ({ ...s, [provider]: !s[provider] }))
  }

  const handleTestConnection = async () => {
    const provider = form.values.provider
    const key = form.values[provider === 'anthropic' ? 'anthropic_key' : provider === 'openrouter' ? 'openrouter_key' : 'ollama_endpoint']

    if (!key) {
      form.setError(
        provider === 'anthropic' ? 'anthropic_key' : provider === 'openrouter' ? 'openrouter_key' : 'ollama_endpoint',
        'Please provide the required credential'
      )
      return
    }

    setTestingProvider(provider)
    setTestResult(null)

    try {
      const res = await fetch(`/api/settings/test/${provider}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      })
      const data = await res.json()
      setTestResult({
        success: res.ok,
        message: data.message || (res.ok ? 'Connection successful!' : 'Connection failed'),
      })
    } catch (err) {
      setTestResult({
        success: false,
        message: err.message || 'Test failed',
      })
    } finally {
      setTestingProvider(null)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.isValid()) {
      onChange?.(form.values)
    }
  }

  return (
    <SettingsForm onSubmit={handleSubmit}>
      <FormSection title="LLM Provider" description="Select which LLM provider to use">
        <div className="api-keys-provider-group">
          {['anthropic', 'openrouter', 'ollama'].map(provider => (
            <label key={provider} className="api-keys-provider-radio">
              <input
                type="radio"
                name="provider"
                value={provider}
                checked={form.values.provider === provider}
                onChange={handleProviderChange}
              />
              <span className="api-keys-provider-label">
                {provider.charAt(0).toUpperCase() + provider.slice(1)}
              </span>
            </label>
          ))}
        </div>
      </FormSection>

      {form.values.provider === 'anthropic' && (
        <FormSection title="Anthropic API Key">
          <FormGroup
            label="API Key"
            error={form.errors.anthropic_key}
            isTouched={form.touched.anthropic_key}
            hint="Get from https://console.anthropic.com/"
          >
            <div className="password-toggle-group">
              <input
                type={showKeys.anthropic ? 'text' : 'password'}
                placeholder="sk-ant-..."
                {...form.getFieldProps('anthropic_key')}
                className="password-toggle-group__input"
              />
              <button
                type="button"
                className="password-toggle-group__toggle"
                onClick={() => toggleShowKey('anthropic')}
                title={showKeys.anthropic ? 'Hide key' : 'Show key'}
              >
                {showKeys.anthropic ? '🙈' : '👁️'}
              </button>
            </div>
          </FormGroup>
        </FormSection>
      )}

      {form.values.provider === 'openrouter' && (
        <FormSection title="OpenRouter API Key">
          <FormGroup
            label="API Key"
            error={form.errors.openrouter_key}
            isTouched={form.touched.openrouter_key}
            hint="Get from https://openrouter.ai/keys"
          >
            <div className="password-toggle-group">
              <input
                type={showKeys.openrouter ? 'text' : 'password'}
                placeholder="sk-or-..."
                {...form.getFieldProps('openrouter_key')}
                className="password-toggle-group__input"
              />
              <button
                type="button"
                className="password-toggle-group__toggle"
                onClick={() => toggleShowKey('openrouter')}
                title={showKeys.openrouter ? 'Hide key' : 'Show key'}
              >
                {showKeys.openrouter ? '🙈' : '👁️'}
              </button>
            </div>
          </FormGroup>
        </FormSection>
      )}

      {form.values.provider === 'ollama' && (
        <FormSection title="Ollama Endpoint">
          <FormGroup
            label="Endpoint URL"
            error={form.errors.ollama_endpoint}
            isTouched={form.touched.ollama_endpoint}
            hint="e.g., http://localhost:11434"
          >
            <input
              type="text"
              placeholder="http://localhost:11434"
              {...form.getFieldProps('ollama_endpoint')}
            />
          </FormGroup>
        </FormSection>
      )}

      <div className="api-keys-actions">
        <HexButton
          variant="outline"
          onClick={handleTestConnection}
          loading={testingProvider}
          disabled={testingProvider !== null}
        >
          Test Connection
        </HexButton>
        {testResult && (
          <div className={`api-keys-test-result ${testResult.success ? 'api-keys-test-result--success' : 'api-keys-test-result--error'}`}>
            {testResult.message}
          </div>
        )}
      </div>
    </SettingsForm>
  )
}
