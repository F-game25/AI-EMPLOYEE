import { useState, useEffect } from 'react'
import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './LlmSettingsTab.css'

const PROVIDER_MODELS = {
  anthropic: ['claude-3-5-sonnet', 'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku'],
  openrouter: ['deepseek/deepseek-coder-v2', 'openai/gpt-4-turbo', 'anthropic/claude-3.5-sonnet', 'meta-llama/llama-2-70b'],
  ollama: [],
}

const VALIDATORS = {
  max_tokens: (val) => {
    const num = parseInt(val, 10)
    if (num < 100 || num > 4096) return 'Must be between 100-4096'
    return null
  },
  temperature: (val) => {
    const num = parseFloat(val)
    if (num < 0 || num > 1) return 'Must be between 0.0-1.0'
    return null
  },
  top_p: (val) => {
    const num = parseFloat(val)
    if (num < 0 || num > 1) return 'Must be between 0.0-1.0'
    return null
  },
  top_k: (val) => {
    const num = parseInt(val, 10)
    if (num < 0 || num > 100) return 'Must be between 0-100'
    return null
  },
}

export default function LlmSettingsTab({ settings = {}, onChange }) {
  const [availableModels, setAvailableModels] = useState(PROVIDER_MODELS.anthropic)

  const form = useFormState(
    {
      provider: settings.provider || 'anthropic',
      model: settings.model || PROVIDER_MODELS.anthropic[0],
      temperature: settings.temperature !== undefined ? settings.temperature : 0.7,
      max_tokens: settings.max_tokens || 2048,
      top_p: settings.top_p !== undefined ? settings.top_p : 0.9,
      top_k: settings.top_k || 40,
      ollama_model: settings.ollama_model || '',
    },
    (key, val) => VALIDATORS[key]?.(val) || null
  )

  useEffect(() => {
    const provider = form.values.provider
    const models = PROVIDER_MODELS[provider] || []
    setAvailableModels(models)
    if (models.length > 0 && !models.includes(form.values.model)) {
      form.setField('model', models[0])
    }
  }, [form.values.provider])

  const handleProviderChange = (e) => {
    form.setField('provider', e.target.value)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.isValid()) {
      onChange?.(form.values)
    }
  }

  const isOllama = form.values.provider === 'ollama'

  return (
    <SettingsForm onSubmit={handleSubmit}>
      <FormSection title="Model Configuration" description="Configure LLM behavior and constraints">
        <FormGroup label="Provider" required>
          <select value={form.values.provider} onChange={handleProviderChange}>
            <option value="anthropic">Anthropic</option>
            <option value="openrouter">OpenRouter</option>
            <option value="ollama">Ollama</option>
          </select>
        </FormGroup>

        {!isOllama && (
          <FormGroup label="Model" required>
            <select {...form.getFieldProps('model')}>
              {availableModels.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </FormGroup>
        )}

        {isOllama && (
          <FormGroup label="Ollama Model">
            <input
              type="text"
              placeholder="e.g., llama2, mistral, neural-chat"
              {...form.getFieldProps('ollama_model')}
            />
          </FormGroup>
        )}
      </FormSection>

      <FormSection title="Generation Parameters">
        <FormGroup label={`Temperature: ${form.values.temperature.toFixed(1)}`} hint="Lower = deterministic, Higher = creative">
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            className="settings-slider"
            {...form.getFieldProps('temperature')}
          />
        </FormGroup>

        <FormGroup
          label="Max Tokens"
          error={form.errors.max_tokens}
          isTouched={form.touched.max_tokens}
          hint="100-4096"
          required
        >
          <input
            type="number"
            min="100"
            max="4096"
            {...form.getFieldProps('max_tokens')}
          />
        </FormGroup>

        <FormGroup label={`Top P: ${form.values.top_p.toFixed(2)}`} hint="Nucleus sampling threshold">
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            className="settings-slider"
            {...form.getFieldProps('top_p')}
          />
        </FormGroup>

        {isOllama && (
          <FormGroup
            label="Top K"
            error={form.errors.top_k}
            isTouched={form.touched.top_k}
            hint="0-100"
          >
            <input
              type="number"
              min="0"
              max="100"
              {...form.getFieldProps('top_k')}
            />
          </FormGroup>
        )}
      </FormSection>

      <div className="llm-settings-examples">
        <h4 className="llm-settings-examples__title">Available Models</h4>
        <div className="llm-settings-examples__grid">
          {availableModels.length > 0 ? (
            availableModels.map(m => (
              <div key={m} className="llm-settings-examples__item">{m}</div>
            ))
          ) : (
            <p className="llm-settings-examples__empty">Configure Ollama endpoint in API Keys tab</p>
          )}
        </div>
      </div>
    </SettingsForm>
  )
}
