import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './SecurityTab.css'

const PASSWORD_POLICIES = [
  {
    value: '12chars_special_number_uppercase',
    label: '12+ chars, special, number, uppercase',
    description: 'Recommended for general use'
  },
  {
    value: '16chars_complex',
    label: '16+ chars, highly complex',
    description: 'For high-security environments'
  },
  {
    value: 'simple_8chars',
    label: '8+ chars, simple',
    description: 'Minimal requirements'
  },
]

export default function SecurityTab({ settings = {}, onChange }) {
  const form = useFormState({
    multi_tenancy_enabled: settings.multi_tenancy_enabled ?? true,
    audit_logging_enabled: settings.audit_logging_enabled ?? true,
    require_mfa: settings.require_mfa ?? false,
    session_timeout_minutes: settings.session_timeout_minutes || 60,
    password_policy: settings.password_policy || '12chars_special_number_uppercase',
  }, (key, val) => {
    if (key === 'session_timeout_minutes') {
      const num = parseInt(val, 10)
      if (num < 1 || num > 480) return 'Must be between 1-480 minutes'
    }
    return null
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.isValid()) {
      onChange?.(form.values)
    }
  }

  return (
    <SettingsForm onSubmit={handleSubmit}>
      <FormSection title="System Security">
        <label className="security-toggle">
          <input
            type="checkbox"
            checked={form.values.multi_tenancy_enabled}
            disabled
            className="security-toggle__input"
          />
          <span className="security-toggle__label">Enable Multi-Tenancy</span>
          <span className="security-toggle__switch" />
          <span className="security-toggle__badge">Always On</span>
        </label>

        <label className="security-toggle">
          <input
            type="checkbox"
            checked={form.values.audit_logging_enabled}
            onChange={(e) => form.setField('audit_logging_enabled', e.target.checked)}
            className="security-toggle__input"
          />
          <span className="security-toggle__label">Enable Audit Logging</span>
          <span className="security-toggle__switch" />
        </label>

        {!form.values.audit_logging_enabled && (
          <div className="security-warning">
            <span className="security-warning__icon">⚠️</span>
            <span className="security-warning__text">Audit logging recommended for production</span>
          </div>
        )}
      </FormSection>

      <FormSection title="Authentication">
        <label className="security-toggle">
          <input
            type="checkbox"
            checked={form.values.require_mfa}
            onChange={(e) => form.setField('require_mfa', e.target.checked)}
            className="security-toggle__input"
          />
          <span className="security-toggle__label">Require Multi-Factor Authentication</span>
          <span className="security-toggle__switch" />
        </label>

        <FormGroup
          label="Session Timeout"
          error={form.errors.session_timeout_minutes}
          isTouched={form.touched.session_timeout_minutes}
          hint="1-480 minutes"
          required
        >
          <div className="security-input-group">
            <input
              type="number"
              min="1"
              max="480"
              {...form.getFieldProps('session_timeout_minutes')}
              className="security-input-group__input"
            />
            <span className="security-input-group__unit">minutes</span>
          </div>
        </FormGroup>
      </FormSection>

      <FormSection title="Password Policy">
        <div className="security-policy-group">
          {PASSWORD_POLICIES.map(policy => (
            <label key={policy.value} className="security-policy-item">
              <input
                type="radio"
                name="password_policy"
                value={policy.value}
                checked={form.values.password_policy === policy.value}
                onChange={(e) => form.setField('password_policy', e.target.value)}
                className="security-policy-radio"
              />
              <div className="security-policy-content">
                <div className="security-policy-label">{policy.label}</div>
                <div className="security-policy-description">{policy.description}</div>
              </div>
            </label>
          ))}
        </div>
      </FormSection>
    </SettingsForm>
  )
}
