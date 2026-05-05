import { useState } from 'react'
import { HexButton } from '../nexus-ui'
import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './AdvancedTab.css'

const VALIDATORS = {
  cache_size_mb: (val) => {
    const num = parseInt(val, 10)
    if (num < 100 || num > 1000) return 'Must be between 100-1000 MB'
    return null
  },
  max_concurrent_tasks: (val) => {
    const num = parseInt(val, 10)
    if (num < 1 || num > 50) return 'Must be between 1-50'
    return null
  },
  retry_attempts: (val) => {
    const num = parseInt(val, 10)
    if (num < 1 || num > 10) return 'Must be between 1-10'
    return null
  },
  retry_delay_seconds: (val) => {
    const num = parseInt(val, 10)
    if (num < 1 || num > 60) return 'Must be between 1-60 seconds'
    return null
  },
  custom_headers: (val) => {
    if (!val) return null
    try {
      JSON.parse(val)
      return null
    } catch {
      return 'Must be valid JSON'
    }
  },
}

export default function AdvancedTab({ settings = {}, onChange }) {
  const [resetConfirmed, setResetConfirmed] = useState(false)

  const form = useFormState(
    {
      pipeline_strict_mode: settings.pipeline_strict_mode ?? false,
      experimental_features: settings.experimental_features ?? false,
      log_level: settings.log_level || 'INFO',
      cache_size_mb: settings.cache_size_mb || 500,
      max_concurrent_tasks: settings.max_concurrent_tasks || 10,
      retry_attempts: settings.retry_attempts || 3,
      retry_delay_seconds: settings.retry_delay_seconds || 5,
      custom_headers: settings.custom_headers ? JSON.stringify(settings.custom_headers, null, 2) : '{}',
    },
    (key, val) => VALIDATORS[key]?.(val) || null
  )

  const handleResetDefaults = async () => {
    if (!resetConfirmed) {
      setResetConfirmed(true)
      return
    }

    try {
      const res = await fetch('/api/settings/reset', { method: 'POST' })
      if (res.ok) {
        window.location.reload()
      }
    } catch (err) {
      console.error('Reset failed:', err)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.isValid()) {
      const values = { ...form.values }
      if (values.custom_headers) {
        try {
          values.custom_headers = JSON.parse(values.custom_headers)
        } catch {
          // Already validated
        }
      }
      onChange?.(values)
    }
  }

  return (
    <SettingsForm onSubmit={handleSubmit}>
      <FormSection title="Pipeline Configuration">
        <label className="advanced-toggle">
          <input
            type="checkbox"
            checked={form.values.pipeline_strict_mode}
            onChange={(e) => form.setField('pipeline_strict_mode', e.target.checked)}
            className="advanced-toggle__input"
          />
          <span className="advanced-toggle__label">Pipeline Strict Mode</span>
          <span className="advanced-toggle__switch" />
        </label>
        <p className="advanced-note">Disable graceful fallbacks, surface real failures</p>

        <label className="advanced-toggle">
          <input
            type="checkbox"
            checked={form.values.experimental_features}
            onChange={(e) => form.setField('experimental_features', e.target.checked)}
            className="advanced-toggle__input"
          />
          <span className="advanced-toggle__label">Enable Experimental Features</span>
          <span className="advanced-toggle__switch" />
        </label>
      </FormSection>

      <FormSection title="Logging & Diagnostics">
        <FormGroup label="Log Level" required>
          <select {...form.getFieldProps('log_level')}>
            <option value="INFO">Info</option>
            <option value="DEBUG">Debug</option>
            <option value="WARN">Warn</option>
            <option value="ERROR">Error</option>
          </select>
        </FormGroup>
      </FormSection>

      <FormSection title="Performance Tuning">
        <FormGroup
          label="Cache Size (MB)"
          error={form.errors.cache_size_mb}
          isTouched={form.touched.cache_size_mb}
          hint="100-1000 MB"
          required
        >
          <input
            type="number"
            min="100"
            max="1000"
            {...form.getFieldProps('cache_size_mb')}
          />
        </FormGroup>

        <FormGroup
          label="Max Concurrent Tasks"
          error={form.errors.max_concurrent_tasks}
          isTouched={form.touched.max_concurrent_tasks}
          hint="1-50 tasks"
          required
        >
          <input
            type="number"
            min="1"
            max="50"
            {...form.getFieldProps('max_concurrent_tasks')}
          />
        </FormGroup>

        <FormGroup
          label="Retry Attempts"
          error={form.errors.retry_attempts}
          isTouched={form.touched.retry_attempts}
          hint="1-10 attempts"
          required
        >
          <input
            type="number"
            min="1"
            max="10"
            {...form.getFieldProps('retry_attempts')}
          />
        </FormGroup>

        <FormGroup
          label="Retry Delay (seconds)"
          error={form.errors.retry_delay_seconds}
          isTouched={form.touched.retry_delay_seconds}
          hint="1-60 seconds"
          required
        >
          <input
            type="number"
            min="1"
            max="60"
            {...form.getFieldProps('retry_delay_seconds')}
          />
        </FormGroup>
      </FormSection>

      <FormSection title="Custom HTTP Headers">
        <FormGroup
          label="Headers (JSON)"
          error={form.errors.custom_headers}
          isTouched={form.touched.custom_headers}
          hint='e.g., {"X-Custom": "value"}'
        >
          <textarea
            placeholder='{"X-Custom": "value"}'
            {...form.getFieldProps('custom_headers')}
          />
        </FormGroup>
      </FormSection>

      <FormSection title="Maintenance">
        {resetConfirmed ? (
          <div className="advanced-reset-confirm">
            <p>This will reset all settings to defaults. Are you sure?</p>
            <div className="advanced-reset-buttons">
              <HexButton
                variant="danger"
                onClick={handleResetDefaults}
              >
                Confirm Reset
              </HexButton>
              <HexButton
                variant="outline"
                onClick={() => setResetConfirmed(false)}
              >
                Cancel
              </HexButton>
            </div>
          </div>
        ) : (
          <HexButton
            variant="outline"
            onClick={handleResetDefaults}
          >
            Reset to Defaults
          </HexButton>
        )}
      </FormSection>
    </SettingsForm>
  )
}
