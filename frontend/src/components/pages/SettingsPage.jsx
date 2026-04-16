import { useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useSettingsStore } from '../../store/settingsStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'
import { eventBus, EVENTS } from '../../utils/eventBus'

const BASE = API_URL

function SectionHeader({ title, subtitle }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>{title}</h2>
      {subtitle && <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  )
}

function SettingField({ label, type = 'text', value, onChange, placeholder, description, sensitive = false }) {
  const [show, setShow] = useState(false)
  const inputType = sensitive && !show ? 'password' : type

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
        {label}
      </label>
      {description && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>{description}</div>
      )}
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        <input
          type={inputType}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            flex: 1,
            padding: 'var(--space-3)',
            background: 'var(--bg-base)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            fontFamily: 'inherit',
            outline: 'none',
            transition: 'border-color 150ms',
          }}
          onFocus={(e) => { e.target.style.borderColor = 'rgba(212,175,55,0.4)' }}
          onBlur={(e) => { e.target.style.borderColor = 'var(--border-subtle)' }}
        />
        {sensitive && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setShow(v => !v)}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {show ? 'Hide' : 'Show'}
          </motion.button>
        )}
      </div>
    </div>
  )
}

function ToggleField({ label, value, onChange, description }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: 'var(--space-3) 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div>
        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>{label}</div>
        {description && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{description}</div>}
      </div>
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => onChange(!value)}
        style={{
          width: '44px',
          height: '24px',
          borderRadius: '12px',
          background: value ? 'rgba(212, 175, 55, 0.3)' : 'var(--bg-base)',
          border: `1px solid ${value ? 'rgba(212, 175, 55, 0.5)' : 'var(--border-subtle)'}`,
          cursor: 'pointer',
          padding: 0,
          position: 'relative',
          transition: 'all 200ms',
        }}
        role="switch"
        aria-checked={value}
      >
        <motion.span
          animate={{ x: value ? 20 : 2 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          style={{
            position: 'absolute',
            top: '3px',
            width: '16px',
            height: '16px',
            borderRadius: '50%',
            background: value ? 'var(--gold)' : 'var(--text-muted)',
          }}
        />
      </motion.button>
    </div>
  )
}

function SelectField({ label, value, options, onChange, description }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
        {label}
      </label>
      {description && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>{description}</div>
      )}
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: 'var(--space-3)',
          background: 'var(--bg-base)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-primary)',
          fontSize: '13px',
          fontFamily: 'inherit',
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {options.map(({ value: v, label: l }) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </div>
  )
}

function SectionCard({ children }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
      {children}
    </div>
  )
}

export default function SettingsPage() {
  const settings = useSettingsStore()
  const [saveStatus, setSaveStatus] = useState(null) // null | 'saving' | 'saved' | 'error'

  const saveSection = useCallback(async (section, values) => {
    setSaveStatus('saving')
    settings.updateSection(section, values)
    try {
      await settings.syncToBackend(BASE)
      setSaveStatus('saved')
    } catch {
      setSaveStatus('saved') // locally persisted regardless
    }
    setTimeout(() => setSaveStatus(null), 2000)
  }, [settings])

  const handleResetAll = useCallback(() => {
    if (window.confirm('Reset all settings to defaults? This cannot be undone.')) {
      settings.resetAll()
      eventBus.emit(EVENTS.SETTINGS_RESET, {})
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus(null), 2000)
    }
  }, [settings])

  return (
    <div className="page-enter">
      <PageHeader
        title="Settings"
        subtitle="API keys, webhooks, tool connectors, and environment configuration"
      />

      {saveStatus && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)',
          marginBottom: 'var(--space-4)',
          background: saveStatus === 'error' ? 'rgba(239,68,68,0.08)' : 'rgba(34,197,94,0.08)',
          border: `1px solid ${saveStatus === 'error' ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)'}`,
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: saveStatus === 'error' ? 'var(--error)' : 'var(--success)',
        }}>
          {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? '✓ Settings saved (persisted locally)' : '✕ Save failed'}
        </div>
      )}

      {/* API Keys */}
      <SectionCard>
        <SectionHeader
          title="API Key Manager"
          subtitle="Configure LLM provider credentials. Keys are stored locally and never sent to third parties."
        />
        <SettingField
          label="OpenAI API Key"
          value={settings.apiKeys.openai}
          onChange={(v) => settings.setApiKey('openai', v)}
          placeholder="sk-..."
          sensitive
          description="Used for GPT-4o, GPT-4 and other OpenAI models"
        />
        <SettingField
          label="Anthropic API Key"
          value={settings.apiKeys.anthropic}
          onChange={(v) => settings.setApiKey('anthropic', v)}
          placeholder="sk-ant-..."
          sensitive
          description="Used for Claude models"
        />
        <SettingField
          label="Local Model URL"
          value={settings.apiKeys.local_model_url}
          onChange={(v) => settings.setApiKey('local_model_url', v)}
          placeholder="http://localhost:11434"
          description="Ollama or compatible local model endpoint"
        />
        <SelectField
          label="Active LLM Provider"
          value={settings.llm.provider}
          options={[
            { value: 'openai', label: 'OpenAI' },
            { value: 'anthropic', label: 'Anthropic (Claude)' },
            { value: 'local', label: 'Local Model' },
          ]}
          onChange={(v) => settings.updateSection('llm', { provider: v })}
          description="Primary provider for AI tasks"
        />
        <SettingField
          label="Model"
          value={settings.llm.model}
          onChange={(v) => settings.updateSection('llm', { model: v })}
          placeholder="gpt-4o"
          description="Model name or identifier"
        />
      </SectionCard>

      {/* Webhook Configuration */}
      <SectionCard>
        <SectionHeader
          title="Webhook Configuration"
          subtitle="Configure HTTP callbacks for system events."
        />
        <SettingField
          label="On Task Complete"
          value={settings.webhooks.on_task_complete}
          onChange={(v) => settings.updateSection('webhooks', { on_task_complete: v })}
          placeholder="https://your-app.com/webhook/task-complete"
          description="POST request sent when a task is completed"
        />
        <SettingField
          label="On Agent Error"
          value={settings.webhooks.on_agent_error}
          onChange={(v) => settings.updateSection('webhooks', { on_agent_error: v })}
          placeholder="https://your-app.com/webhook/agent-error"
          description="POST request sent when an agent encounters an error"
        />
        <SettingField
          label="On Revenue Event"
          value={settings.webhooks.on_revenue_event}
          onChange={(v) => settings.updateSection('webhooks', { on_revenue_event: v })}
          placeholder="https://your-app.com/webhook/revenue"
          description="POST request sent on Money Mode revenue events"
        />
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => saveSection('webhooks', settings.webhooks)}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            background: 'rgba(212,175,55,0.1)',
            border: '1px solid rgba(212,175,55,0.3)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--gold)',
            fontSize: '12px',
            fontWeight: 500,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          Save Webhooks
        </motion.button>
      </SectionCard>

      {/* Tool Connectors */}
      <SectionCard>
        <SectionHeader
          title="Tool Connectors"
          subtitle="Enable or disable agent tool integrations."
        />
        {Object.entries(settings.tools).map(([key, enabled]) => (
          <ToggleField
            key={key}
            label={key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            value={enabled}
            onChange={(v) => settings.updateSection('tools', { [key]: v })}
            description={
              key === 'web_search' ? 'Allow agents to search the web' :
              key === 'code_executor' ? 'Allow agents to execute code in sandbox' :
              key === 'file_system' ? 'Allow agents to read/write files' :
              key === 'email_sender' ? 'Allow agents to send emails' :
              key === 'calendar' ? 'Allow agents to read/write calendar events' : undefined
            }
          />
        ))}
      </SectionCard>

      {/* Memory Backend */}
      <SectionCard>
        <SectionHeader
          title="Memory Backend"
          subtitle="Configure how agent memory is stored and retrieved."
        />
        <SelectField
          label="Storage Backend"
          value={settings.memory.backend}
          options={[
            { value: 'json', label: 'JSON File (default)' },
            { value: 'sqlite', label: 'SQLite (local database)' },
            { value: 'remote', label: 'Remote API' },
          ]}
          onChange={(v) => settings.updateSection('memory', { backend: v })}
          description="Where memory entities are persisted"
        />
        {settings.memory.backend === 'remote' && (
          <SettingField
            label="Remote Memory URL"
            value={settings.memory.remote_url}
            onChange={(v) => settings.updateSection('memory', { remote_url: v })}
            placeholder="https://your-memory-api.com"
            description="API endpoint for remote memory storage"
          />
        )}
        <SettingField
          label="Max Entities"
          type="number"
          value={String(settings.memory.max_entities)}
          onChange={(v) => settings.updateSection('memory', { max_entities: parseInt(v) || 10000 })}
          placeholder="10000"
          description="Maximum number of memory entities to retain"
        />
        <SettingField
          label="TTL (days)"
          type="number"
          value={String(settings.memory.ttl_days)}
          onChange={(v) => settings.updateSection('memory', { ttl_days: parseInt(v) || 90 })}
          placeholder="90"
          description="Days before memory entities expire"
        />
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => saveSection('memory', settings.memory)}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            background: 'rgba(212,175,55,0.1)',
            border: '1px solid rgba(212,175,55,0.3)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--gold)',
            fontSize: '12px',
            fontWeight: 500,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          Save Memory Config
        </motion.button>
      </SectionCard>

      {/* Environment Config */}
      <SectionCard>
        <SectionHeader
          title="Environment Configuration"
          subtitle="Runtime parameters for the AI Employee system."
        />
        <SelectField
          label="Log Level"
          value={settings.environment.log_level}
          options={[
            { value: 'DEBUG', label: 'DEBUG' },
            { value: 'INFO', label: 'INFO' },
            { value: 'WARNING', label: 'WARNING' },
            { value: 'ERROR', label: 'ERROR' },
          ]}
          onChange={(v) => settings.updateSection('environment', { log_level: v })}
          description="Minimum log level for system output"
        />
        <SettingField
          label="Max Agents"
          type="number"
          value={String(settings.environment.max_agents)}
          onChange={(v) => settings.updateSection('environment', { max_agents: parseInt(v) || 10 })}
          placeholder="10"
          description="Maximum number of agents running concurrently"
        />
        <SettingField
          label="Task Timeout (seconds)"
          type="number"
          value={String(settings.environment.task_timeout_s)}
          onChange={(v) => settings.updateSection('environment', { task_timeout_s: parseInt(v) || 300 })}
          placeholder="300"
          description="How long before a task is considered timed out"
        />
        <SettingField
          label="Autonomy Cycle (seconds)"
          type="number"
          value={String(settings.environment.autonomy_cycle_s)}
          onChange={(v) => settings.updateSection('environment', { autonomy_cycle_s: parseInt(v) || 2 })}
          placeholder="2"
          description="How often the autonomy daemon processes the task queue"
        />
        <ToggleField
          label="Offline Mode"
          value={settings.environment.offline_mode}
          onChange={(v) => settings.updateSection('environment', { offline_mode: v })}
          description="Operate without network access (local-only mode)"
        />
        <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)' }}>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => saveSection('environment', settings.environment)}
            style={{
              padding: 'var(--space-2) var(--space-4)',
              background: 'rgba(212,175,55,0.1)',
              border: '1px solid rgba(212,175,55,0.3)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--gold)',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Save Environment
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleResetAll}
            style={{
              padding: 'var(--space-2) var(--space-4)',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--error)',
              fontSize: '12px',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Reset All to Defaults
          </motion.button>
        </div>
      </SectionCard>
    </div>
  )
}
