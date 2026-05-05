import { useState } from 'react'
import { HexButton } from '../nexus-ui'
import { useFormState } from '../../hooks/useFormState'
import SettingsForm, { FormGroup, FormSection } from './SettingsForm'
import './NotificationsTab.css'

const VALIDATORS = {
  email_alert: (val) => {
    if (!val) return null
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) return 'Invalid email address'
    return null
  },
  slack_webhook: (val) => {
    if (!val) return null
    if (!val.startsWith('https://hooks.slack.com/')) return 'Must be a valid Slack webhook URL'
    return null
  },
}

export default function NotificationsTab({ settings = {}, onChange }) {
  const [testingSlack, setTestingSlack] = useState(false)
  const [slackTestResult, setSlackTestResult] = useState(null)

  const form = useFormState(
    {
      email_notifications_enabled: settings.email_notifications_enabled ?? false,
      email_alert: settings.email_alert || '',
      slack_notifications_enabled: settings.slack_notifications_enabled ?? false,
      slack_webhook: settings.slack_webhook || '',
    },
    (key, val) => VALIDATORS[key]?.(val) || null
  )

  const handleTestSlack = async () => {
    const webhook = form.values.slack_webhook
    if (!webhook) {
      form.setError('slack_webhook', 'Please provide webhook URL')
      return
    }

    setTestingSlack(true)
    setSlackTestResult(null)

    try {
      const res = await fetch('/api/settings/test/slack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook }),
      })
      const data = await res.json()
      setSlackTestResult({
        success: res.ok,
        message: data.message || (res.ok ? 'Test notification sent!' : 'Failed to send'),
      })
    } catch (err) {
      setSlackTestResult({
        success: false,
        message: err.message || 'Test failed',
      })
    } finally {
      setTestingSlack(false)
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
      <FormSection title="Email Notifications">
        <label className="notifications-toggle">
          <input
            type="checkbox"
            checked={form.values.email_notifications_enabled}
            onChange={(e) => form.setField('email_notifications_enabled', e.target.checked)}
            className="notifications-toggle__input"
          />
          <span className="notifications-toggle__label">Enable Email Notifications</span>
          <span className="notifications-toggle__switch" />
        </label>

        {form.values.email_notifications_enabled && (
          <FormGroup
            label="Email for Alerts"
            error={form.errors.email_alert}
            isTouched={form.touched.email_alert}
            hint="Receive critical alerts and notifications"
            required
          >
            <input
              type="email"
              placeholder="alerts@example.com"
              {...form.getFieldProps('email_alert')}
            />
          </FormGroup>
        )}
      </FormSection>

      <FormSection title="Slack Integration">
        <label className="notifications-toggle">
          <input
            type="checkbox"
            checked={form.values.slack_notifications_enabled}
            onChange={(e) => form.setField('slack_notifications_enabled', e.target.checked)}
            className="notifications-toggle__input"
          />
          <span className="notifications-toggle__label">Enable Slack Notifications</span>
          <span className="notifications-toggle__switch" />
        </label>

        {form.values.slack_notifications_enabled && (
          <>
            <FormGroup
              label="Slack Webhook URL"
              error={form.errors.slack_webhook}
              isTouched={form.touched.slack_webhook}
              hint="Get from https://api.slack.com/messaging/webhooks"
              required
            >
              <input
                type="text"
                placeholder="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
                {...form.getFieldProps('slack_webhook')}
              />
            </FormGroup>

            <HexButton
              variant="outline"
              onClick={handleTestSlack}
              loading={testingSlack}
              disabled={testingSlack}
            >
              Test Slack Connection
            </HexButton>

            {slackTestResult && (
              <div className={`notifications-test-result ${slackTestResult.success ? 'notifications-test-result--success' : 'notifications-test-result--error'}`}>
                {slackTestResult.message}
              </div>
            )}
          </>
        )}
      </FormSection>

      <FormSection title="Preview">
        <div className="notifications-preview">
          <div className="notifications-preview__label">Test notification message:</div>
          <div className="notifications-preview__message">
            Alert: System health check passed
          </div>
        </div>
      </FormSection>
    </SettingsForm>
  )
}
