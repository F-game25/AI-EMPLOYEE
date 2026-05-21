import { useState, useEffect, useCallback } from 'react'
import api from '../../../api/client'
import { buildModelOptions } from './shared'

function RoutingRow({ rule, onChange, onSave, registryData }) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const modelOpts = buildModelOptions(registryData)

  const save = async () => {
    setSaving(true)
    try {
      await onSave?.(rule)
    } finally {
      setSaving(false); setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    }
  }

  return (
    <tr>
      <td><span className="mp-cell-agent">{rule.agent}</span></td>
      <td style={{ minWidth: 180 }}>
        <select
          className="mp-model-select"
          value={rule.preferred}
          onChange={e => onChange({ ...rule, preferred: e.target.value })}
        >
          {modelOpts.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </td>
      <td style={{ minWidth: 160 }}>
        <select
          className="mp-model-select"
          value={rule.fallback}
          onChange={e => onChange({ ...rule, fallback: e.target.value })}
        >
          {modelOpts.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </td>
      <td>
        <input
          className="mp-budget-input"
          type="number"
          min={0}
          step={0.5}
          value={rule.budget}
          onChange={e => onChange({ ...rule, budget: parseFloat(e.target.value) || 0 })}
        />
      </td>
      <td>
        <span className={`mp-row-status mp-row-status--${rule.active ? 'active' : 'inactive'}`}>
          {rule.active ? 'ACTIVE' : 'INACTIVE'}
        </span>
      </td>
      <td>
        <button
          className={`mp-row-save-btn ${saved ? 'mp-row-save-btn--saved' : ''}`}
          onClick={save}
          disabled={saving || saved}
        >
          {saved ? '✓ SAVED' : saving ? 'SAVING…' : 'SAVE'}
        </button>
      </td>
    </tr>
  )
}

/* ── Subsystems Routing ─────────────────────────────────────────────────── */

function SubsystemsRouting() {
  const [subsystems, setSubsystems] = useState([])
  const [saving, setSaving] = useState({})

  const load = useCallback(() => {
    api.get('/api/settings/subsystems')
      .then(d => setSubsystems(d.subsystems || []))
      .catch(() => setSubsystems([]))
  }, [])
  useEffect(() => { load() }, [load])

  const save = async (id, provider, model) => {
    setSaving(s => ({ ...s, [id]: true }))
    try {
      await api.put(`/api/settings/subsystem-routing/${id}`, { provider, model })
      load()
    } catch {}
    setSaving(s => ({ ...s, [id]: false }))
  }

  if (subsystems.length === 0) return null

  return (
    <div className="mp-subsystems">
      <div className="mp-section-label">SUBSYSTEM MODEL ROUTING</div>
      <div className="mp-subsystems__grid">
        {subsystems.map(s => {
          const provider = s.current?.provider || s.default_provider
          const model    = s.current?.model    || s.default_model
          return (
            <div key={s.id} className="mp-subsystem">
              <div className="mp-subsystem__head">
                <span className="mp-subsystem__label">{s.label}</span>
                {s.current && <span className="mp-subsystem__badge">OVERRIDDEN</span>}
              </div>
              <div className="mp-subsystem__desc">{s.description}</div>
              <div className="mp-subsystem__row">
                <select
                  className="mp-select"
                  value={provider}
                  onChange={e => save(s.id, e.target.value, model)}
                  disabled={saving[s.id]}>
                  <option value="anthropic">anthropic</option>
                  <option value="openai">openai</option>
                  <option value="ollama">ollama</option>
                  <option value="openrouter">openrouter</option>
                </select>
                <input
                  className="mp-input"
                  defaultValue={model}
                  onBlur={e => e.target.value !== model && save(s.id, provider, e.target.value)}
                  placeholder="model name"
                  disabled={saving[s.id]}
                />
                {saving[s.id] && <span className="mp-subsystem__saving">SAVING…</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const TASK_TYPE_LABELS = {
  coding:    'Coding',
  reasoning: 'Reasoning',
  creative:  'Creative',
  analytics: 'Analytics',
  bulk:      'Bulk',
  general:   'General',
}

const DEFAULT_TASK_ROUTING = {
  coding:    { provider: 'anthropic', model: 'claude-sonnet-4-6' },
  reasoning: { provider: 'anthropic', model: 'claude-opus-4-7'   },
  creative:  { provider: 'anthropic', model: 'claude-sonnet-4-6' },
  analytics: { provider: 'anthropic', model: 'claude-opus-4-7'   },
  bulk:      { provider: 'anthropic', model: 'claude-haiku-4-5'  },
  general:   { provider: 'anthropic', model: 'claude-haiku-4-5'  },
}

function TaskRoutingRow({ taskType, config, registryData, onChange, onSave, saving, saved }) {
  const providerKeys = registryData?.providers
    ? Object.keys(registryData.providers)
    : ['anthropic', 'openai', 'ollama', 'openrouter']
  const modelOptions = buildModelOptions(registryData).filter(m => m.provider === config.provider)

  return (
    <tr>
      <td><span className="mp-cell-agent">{TASK_TYPE_LABELS[taskType] || taskType}</span></td>
      <td style={{ minWidth: 140 }}>
        <select
          className="mp-model-select"
          value={config.provider}
          onChange={e => onChange(taskType, { ...config, provider: e.target.value })}
        >
          {providerKeys.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </td>
      <td style={{ minWidth: 180 }}>
        {modelOptions.length > 0 ? (
          <select
            className="mp-model-select"
            value={config.model}
            onChange={e => onChange(taskType, { ...config, model: e.target.value })}
          >
            {modelOptions.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        ) : (
          <input
            className="mp-budget-input"
            style={{ width: '100%' }}
            value={config.model}
            onChange={e => onChange(taskType, { ...config, model: e.target.value })}
            placeholder="model name"
          />
        )}
      </td>
      <td>
        <button
          className={`mp-row-save-btn ${saved ? 'mp-row-save-btn--saved' : ''}`}
          onClick={() => onSave(taskType)}
          disabled={saving || saved}
        >
          {saved ? '✓ SAVED' : saving ? 'SAVING…' : 'SAVE'}
        </button>
      </td>
    </tr>
  )
}

function TaskRoutingSection({ registryData }) {
  const [taskRouting, setTaskRouting] = useState(DEFAULT_TASK_ROUTING)
  const [saving, setSaving]           = useState({})
  const [saved, setSaved]             = useState({})
  const [loaded, setLoaded]           = useState(false)

  const load = useCallback(() => {
    api.get('/api/settings/model-routing')
      .then(d => {
        if (d && typeof d === 'object') {
          const taskOnly = Object.fromEntries(Object.keys(DEFAULT_TASK_ROUTING)
            .filter(key => d[key])
            .map(key => [key, d[key]]))
          setTaskRouting(prev => ({ ...prev, ...taskOnly }))
          setLoaded(true)
        }
      })
      .catch(() => setLoaded(true)) // 404 → use defaults silently
  }, [])

  useEffect(() => { load() }, [load])

  const handleChange = (taskType, newConfig) =>
    setTaskRouting(prev => ({ ...prev, [taskType]: newConfig }))

  const handleSave = async (taskType) => {
    setSaving(s => ({ ...s, [taskType]: true }))
    try {
      const current = await api.get('/api/settings/model-routing').catch(() => ({}))
      await api.put('/api/settings/model-routing', { ...current, [taskType]: taskRouting[taskType] })
      setSaved(s => ({ ...s, [taskType]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [taskType]: false })), 2000)
    } catch {}
    setSaving(s => ({ ...s, [taskType]: false }))
  }

  const resetToDefaults = async () => {
    setTaskRouting(DEFAULT_TASK_ROUTING)
    try {
      const current = await api.get('/api/settings/model-routing').catch(() => ({}))
      await api.put('/api/settings/model-routing', { ...current, ...DEFAULT_TASK_ROUTING })
    } catch {}
  }

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="mp-routing-header">
        <div className="mp-section-label" style={{ margin: 0 }}>TASK-TYPE MODEL ROUTING</div>
        <button className="mp-ghost-btn" onClick={resetToDefaults} style={{ fontSize: 10 }}>RESET TO DEFAULTS</button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="mp-routing-table">
          <thead>
            <tr>
              <th>TASK TYPE</th>
              <th>PROVIDER</th>
              <th>MODEL</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(taskRouting).map(([taskType, config]) => (
              <TaskRoutingRow
                key={taskType}
                taskType={taskType}
                config={config}
                registryData={registryData}
                onChange={handleChange}
                onSave={handleSave}
                saving={saving[taskType]}
                saved={saved[taskType]}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RoutingTab() {
  const [agentRules, setAgentRules] = useState([])
  const [registryData, setRegistryData] = useState(null)
  const [rulesSource, setRulesSource] = useState('empty')

  useEffect(() => {
    api.get('/api/models/registry')
      .then(d => { if (d?.providers) setRegistryData(d) })
      .catch(() => {})
    api.get('/api/settings/model-routing')
      .then(d => {
        if (Array.isArray(d?.agent_rules)) {
          setAgentRules(d.agent_rules)
          setRulesSource('backend')
        }
      })
      .catch(() => {})
  }, [])

  const addRule = () => {
    const id = Date.now()
    setAgentRules(prev => [...prev, {
      id,
      agent: 'new-agent',
      preferred: 'claude-sonnet-4-6',
      fallback: 'claude-haiku-4-5',
      budget: 5.00,
      active: true,
    }])
  }

  const updateRule = (id, updated) => setAgentRules(prev => prev.map(r => r.id === id ? updated : r))

  const saveAgentRule = async (rule) => {
    const nextRules = agentRules.map(r => r.id === rule.id ? rule : r)
    setAgentRules(nextRules)
    const current = await api.get('/api/settings/model-routing').catch(() => ({}))
    await api.put('/api/settings/model-routing', { ...current, agent_rules: nextRules })
    setRulesSource('backend')
  }

  return (
    <div>
      <SubsystemsRouting />

      <TaskRoutingSection registryData={registryData} />

      <div className="mp-routing-header">
        <div className="mp-section-label" style={{ margin: 0 }}>AGENT MODEL ROUTING</div>
        {rulesSource === 'backend' && <span className="mp-source-label">SAVED</span>}
        <button className="mp-add-btn" onClick={addRule}>+ ADD RULE</button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="mp-routing-table">
          <thead>
            <tr>
              <th>AGENT</th>
              <th>PREFERRED MODEL</th>
              <th>FALLBACK MODEL</th>
              <th>BUDGET CAP ($/DAY)</th>
              <th>STATUS</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {agentRules.length === 0 && (
              <tr><td colSpan={6} className="mp-routing-empty">No routing rules yet — click “+ Add Rule” to create one.</td></tr>
            )}
            {agentRules.map(rule => (
              <RoutingRow
                key={rule.id}
                rule={rule}
                registryData={registryData}
                onChange={updated => updateRule(rule.id, updated)}
                onSave={saveAgentRule}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default RoutingTab
