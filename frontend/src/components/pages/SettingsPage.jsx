import { useState, useEffect, useRef } from 'react'
import api from '../../api/client'
import { useUpdateCheck } from '../../hooks/useUpdateCheck'
import './SettingsPage.css'

/* ── Constants ─────────────────────────────────────────────────────────── */

const TABS = ['GENERAL', 'LLM', 'INTEGRATIONS', 'APPEARANCE', 'ADVANCED', 'SECURITY', 'NOTIFICATIONS', 'BILLING & USAGE', 'TEAM & ACCESS']

const LLM_MODELS = {
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
  ollama:    ['llama3.3', 'deepseek-r1', 'mistral'],
  openai:    ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'],
}

const RED_ZONE_ACTIONS = [
  { id: 'reset-state',         label: 'RESET ALL STATE',        endpoint: 'POST /api/admin/reset-state',             warning: 'Resets all runtime state files. This cannot be undone.' },
  { id: 'wipe-memory',         label: 'WIPE MEM0 MEMORY',       endpoint: 'DELETE /api/neural-brain/memory/all',      warning: 'Permanently deletes all stored memories. Cannot be undone.' },
  { id: 'factory-reset',       label: 'FACTORY RESET',          endpoint: 'POST /api/admin/factory-reset',           warning: 'Complete system factory reset. All data will be lost.' },
  { id: 'evolution-rollback',  label: 'EVOLUTION ROLLBACK',     endpoint: 'POST /api/evolution/rollback',            warning: 'Rolls back all applied evolution patches.' },
  { id: 'invalidate-sessions', label: 'INVALIDATE SESSIONS',    endpoint: 'POST /api/admin/sessions/invalidate-all', warning: 'Logs out all active users immediately.' },
  { id: 'flush-telemetry',     label: 'FLUSH TELEMETRY',        endpoint: 'POST /api/neural-brain/telemetry/flush',  warning: 'Clears all queued telemetry data.' },
]

/* ── Shared primitives ─────────────────────────────────────────────────── */

function NxToggle({ checked, onChange }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      className={`nx-toggle ${checked ? 'nx-toggle--on' : ''}`}
      onClick={() => onChange(!checked)}
      type="button"
    >
      <span className="nx-toggle-thumb" />
    </button>
  )
}

function NxSlider({ value, min, max, step = 0.01, onChange, format = v => v }) {
  return (
    <div className="nx-slider-wrap">
      <input
        type="range"
        className="nx-slider"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
      <span className="nx-slider-val">{format(value)}</span>
    </div>
  )
}

function NxField({ label, children, full }) {
  return (
    <div className={`nx-field ${full ? 'nx-field--full' : ''}`}>
      <span className="nx-field-label">{label}</span>
      {children}
    </div>
  )
}

function NxSaveBtn({ label = 'SAVE', saving, saved, onClick, danger }) {
  return (
    <button
      className={`nx-save-btn ${danger ? 'nx-save-btn--danger' : ''} ${saved ? 'nx-save-btn--saved' : ''}`}
      onClick={onClick}
      disabled={saving || saved}
    >
      {saved ? '✓ SAVED' : saving ? 'SAVING…' : label}
    </button>
  )
}

function useSave(endpoint, data) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const save = async () => {
    setSaving(true)
    await api.post(endpoint, data).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }
  return { saving, saved, save }
}

/* ── Tab 1: GENERAL ────────────────────────────────────────────────────── */

function GeneralTab() {
  const [cfg, setCfg] = useState({
    system_name: 'AETERNUS NEXUS',
    operating_mode: 'AUTONOMOUS',
    evolution_mode: 'SAFE',
    log_level: 'INFO',
    max_agents: 15,
  })
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  useEffect(() => {
    api.get('/api/settings').then(d => setCfg(p => ({ ...p, ...d }))).catch(() => {})
  }, [])

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">SYSTEM IDENTITY</div>
        <div className="nx-form-grid">
          <NxField label="SYSTEM NAME">
            <input className="nx-input" value={cfg.system_name} onChange={e => set('system_name', e.target.value)} />
          </NxField>
          <NxField label="OPERATING MODE">
            <select className="nx-input" value={cfg.operating_mode} onChange={e => set('operating_mode', e.target.value)}>
              {['AUTONOMOUS','BALANCED','SUPERVISED','SAFE','MAINTENANCE'].map(m =>
                <option key={m} value={m}>{m}</option>)}
            </select>
          </NxField>
          <NxField label="EVOLUTION MODE">
            <select className="nx-input" value={cfg.evolution_mode} onChange={e => set('evolution_mode', e.target.value)}>
              {['AUTO','SAFE','OFF'].map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </NxField>
          <NxField label="LOG LEVEL">
            <select className="nx-input" value={cfg.log_level} onChange={e => set('log_level', e.target.value)}>
              {['DEBUG','INFO','WARNING','ERROR'].map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </NxField>
          <NxField label="MAX AGENTS">
            <input className="nx-input" type="number" min={1} max={100} value={cfg.max_agents} onChange={e => set('max_agents', +e.target.value)} />
          </NxField>
        </div>
        <NxSaveBtn label="SAVE GENERAL SETTINGS" saving={saving} saved={saved} onClick={save} />
      </div>

      <div className="nx-divider" />
      <UpdateSection />
    </div>
  )
}

function UpdateSection() {
  const {
    checking, applying, progress, stage, log, error,
    lastChecked, currentCommit, remoteCommit, updateComplete,
    checkForUpdates, applyUpdate,
  } = useUpdateCheck()
  const logRef = useRef(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  const stageLabel = {
    starting: 'Initializing…', fetching: 'Fetching remote…', comparing: 'Comparing versions…',
    applying: 'Applying update…', building: 'Building frontend…', restarting: 'Restarting services…',
    done: 'Complete', error: 'Error', running: 'Running…',
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">SYSTEM UPDATES</div>
      <div className="nx-update-meta">
        <div className="nx-update-row">
          <span className="nx-update-key">CURRENT COMMIT</span>
          <code className="nx-commit">{currentCommit || '—'}</code>
        </div>
        {remoteCommit && (
          <div className="nx-update-row">
            <span className="nx-update-key">REMOTE COMMIT</span>
            <code className="nx-commit nx-commit--remote">{remoteCommit}</code>
          </div>
        )}
        {lastChecked && (
          <div className="nx-update-row">
            <span className="nx-update-key">LAST CHECKED</span>
            <span className="nx-update-val">{new Date(lastChecked).toLocaleTimeString()}</span>
          </div>
        )}
        {updateComplete && <div className="nx-badge nx-badge--ok">✓ UPDATE APPLIED — reload to activate</div>}
        {error && <div className="nx-badge nx-badge--err">✗ {error}</div>}
      </div>

      {applying && (
        <div className="nx-progress-wrap">
          <div className="nx-progress-bar"><div className="nx-progress-fill" style={{ width: `${progress}%` }} /></div>
          <span className="nx-progress-label">{stageLabel[stage] || stage || '…'} — {progress}%</span>
        </div>
      )}

      {log.length > 0 && (
        <div className="nx-log" ref={logRef}>
          {log.map((e, i) => (
            <div key={i} className={`nx-log-line nx-log-line--${e.level || 'info'}`}>
              <span className="nx-log-stage">[{e.stage || '—'}]</span>{e.text}
            </div>
          ))}
        </div>
      )}

      <div className="nx-btn-row">
        <button className="nx-save-btn" onClick={checkForUpdates} disabled={checking || applying}>
          {checking ? 'CHECKING…' : 'CHECK FOR UPDATES'}
        </button>
        <button className="nx-save-btn nx-save-btn--green" onClick={applyUpdate} disabled={applying || checking}>
          {applying ? `UPDATING… ${progress}%` : 'UPDATE SYSTEM NOW'}
        </button>
        {updateComplete && (
          <button className="nx-save-btn nx-save-btn--reload" onClick={() => window.location.reload()}>
            RELOAD NOW →
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Tab 2: LLM ────────────────────────────────────────────────────────── */

function LLMTab() {
  const [cfg, setCfg] = useState({
    provider: 'anthropic',
    model: 'claude-opus-4-7',
    api_key: '',
    temperature: 0.7,
    max_tokens: 4096,
    fallback_provider: 'ollama',
  })
  const [showKey, setShowKey] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))

  useEffect(() => {
    api.get('/api/settings/keys')
      .then(d => { if (d) setCfg(p => ({ ...p, api_key: d[p.provider] || '' })) })
      .catch(() => {})
  }, [cfg.provider])

  const handleProviderChange = (p) => {
    const model = LLM_MODELS[p]?.[0] || ''
    setCfg(prev => ({ ...prev, provider: p, model, api_key: '' }))
  }

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    try {
      const r = await api.post('/api/settings/test-key', { provider: cfg.provider, key: cfg.api_key })
      setTestResult(r.ok
        ? { ok: true,  msg: `✓ CONNECTION OK${r.latency_ms ? ` — ${r.latency_ms}ms` : ''}` }
        : { ok: false, msg: `✗ ${r.error || 'Connection failed'}` })
    } catch { setTestResult({ ok: false, msg: '✗ Network error' }) }
    finally { setTesting(false) }
  }

  const { saving, saved, save } = useSave('/api/settings/llm', cfg)

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">PRIMARY PROVIDER</div>
        <div className="nx-radio-pills">
          {Object.keys(LLM_MODELS).map(p => (
            <button
              key={p}
              type="button"
              className={`nx-radio-pill ${cfg.provider === p ? 'nx-radio-pill--active' : ''}`}
              onClick={() => handleProviderChange(p)}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">MODEL CONFIGURATION</div>
        <div className="nx-form-grid">
          <NxField label="MODEL">
            <select className="nx-input" value={cfg.model} onChange={e => set('model', e.target.value)}>
              {(LLM_MODELS[cfg.provider] || []).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </NxField>

          <NxField label="API KEY">
            <div className="nx-key-wrap">
              <input
                className="nx-input nx-input--key"
                type={showKey ? 'text' : 'password'}
                value={cfg.api_key}
                onChange={e => set('api_key', e.target.value)}
                placeholder={cfg.provider === 'anthropic' ? 'sk-ant-…' : cfg.provider === 'openai' ? 'sk-…' : 'http://localhost:11434'}
                autoComplete="off"
              />
              <button type="button" className="nx-eye-btn" onClick={() => setShowKey(v => !v)} aria-label={showKey ? 'Hide' : 'Show'}>
                {showKey ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </NxField>

          <NxField label={`TEMPERATURE — ${cfg.temperature.toFixed(2)}`} full>
            <NxSlider value={cfg.temperature} min={0} max={1} step={0.01} onChange={v => set('temperature', v)} format={v => v.toFixed(2)} />
          </NxField>

          <NxField label="MAX TOKENS">
            <input className="nx-input" type="number" min={256} max={32768} step={256} value={cfg.max_tokens} onChange={e => set('max_tokens', +e.target.value)} />
          </NxField>

          <NxField label="FALLBACK PROVIDER">
            <select className="nx-input" value={cfg.fallback_provider} onChange={e => set('fallback_provider', e.target.value)}>
              {Object.keys(LLM_MODELS).map(p => <option key={p} value={p}>{p.toUpperCase()}</option>)}
            </select>
          </NxField>
        </div>

        <div className="nx-btn-row">
          <button className="nx-save-btn nx-save-btn--outline" onClick={testConnection} disabled={testing || !cfg.api_key}>
            {testing ? 'TESTING…' : 'TEST CONNECTION'}
          </button>
          <NxSaveBtn label="SAVE LLM SETTINGS" saving={saving} saved={saved} onClick={save} />
        </div>

        {testResult && (
          <div className={`nx-test-result ${testResult.ok ? 'nx-test-result--ok' : 'nx-test-result--fail'}`}>
            {testResult.msg}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Tab 3: INTEGRATIONS ───────────────────────────────────────────────── */

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

function IntegrationsTab() {
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

/* ── Tab 4: APPEARANCE ─────────────────────────────────────────────────── */

const THEMES = [
  { id: 'nexus-dark',    label: 'NEXUS DARK',  colors: ['#e5c76b', '#07080f', '#10131f'] },
  { id: 'cyber-blue',    label: 'CYBER BLUE',  colors: ['#20d6c7', '#040c1a', '#0b1629'] },
  { id: 'matrix-green',  label: 'MATRIX GREEN', colors: ['#22c55e', '#030903', '#0a160a'] },
]

function AppearanceTab() {
  const [cfg, setCfg] = useState({ theme: 'nexus-dark', sidebar_collapsed: false, reduced_motion: false, font_size: 13 })
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">THEME</div>
        <div className="nx-theme-grid">
          {THEMES.map(t => (
            <button
              key={t.id}
              type="button"
              className={`nx-theme-tile ${cfg.theme === t.id ? 'nx-theme-tile--active' : ''}`}
              onClick={() => set('theme', t.id)}
            >
              <div className="nx-theme-preview" style={{ background: t.colors[1] }}>
                <div className="nx-theme-swatch" style={{ background: t.colors[0] }} />
                <div className="nx-theme-swatch nx-theme-swatch--2" style={{ background: t.colors[2] }} />
              </div>
              <span className="nx-theme-label">{t.label}</span>
              {cfg.theme === t.id && <span className="nx-theme-check">✓</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">DISPLAY OPTIONS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">COLLAPSED SIDEBAR</span>
              <span className="nx-toggle-desc">Start with navigation rail collapsed by default</span>
            </div>
            <NxToggle checked={cfg.sidebar_collapsed} onChange={v => set('sidebar_collapsed', v)} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">REDUCED MOTION</span>
              <span className="nx-toggle-desc">Override prefers-reduced-motion — disable all animations</span>
            </div>
            <NxToggle checked={cfg.reduced_motion} onChange={v => set('reduced_motion', v)} />
          </div>
        </div>

        <div className="nx-divider" />

        <div className="nx-form-grid">
          <NxField label={`FONT SIZE — ${cfg.font_size}px`} full>
            <NxSlider value={cfg.font_size} min={12} max={18} step={1} onChange={v => set('font_size', v)} format={v => `${v}px`} />
          </NxField>
        </div>

        <NxSaveBtn label="APPLY APPEARANCE" saving={saving} saved={saved} onClick={save} />
      </div>
    </div>
  )
}

/* ── Tab 5: ADVANCED ───────────────────────────────────────────────────── */

function ConfirmModal({ action, onConfirm, onCancel }) {
  const [text, setText] = useState('')
  return (
    <div className="nx-modal-backdrop" role="dialog" aria-modal="true">
      <div className="nx-modal">
        <div className="nx-modal-title">{action.label}</div>
        <div className="nx-modal-body">
          <p className="nx-modal-warning">{action.warning}</p>
          <p className="nx-modal-prompt">Type <strong>CONFIRM</strong> to proceed:</p>
          <input className="nx-input nx-input--danger" value={text} onChange={e => setText(e.target.value)} autoFocus />
        </div>
        <div className="nx-modal-actions">
          <button className="nx-save-btn nx-save-btn--outline" onClick={onCancel}>CANCEL</button>
          <button className="nx-save-btn nx-save-btn--danger" disabled={text !== 'CONFIRM'} onClick={() => onConfirm(action)}>
            {action.label}
          </button>
        </div>
      </div>
    </div>
  )
}

function AdvancedTab() {
  const [cfg, setCfg] = useState({ strict_pipeline: false, hitl_gate: true, data_retention: 30 })
  const [showRawJson, setShowRawJson] = useState(false)
  const [rawSettings, setRawSettings] = useState(null)
  const [pending, setPending] = useState(null)
  const [results, setResults] = useState({})
  const [downloadMsg, setDownloadMsg] = useState(null)
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  useEffect(() => {
    api.get('/api/settings').then(d => setCfg(p => ({ ...p, ...d }))).catch(() => {})
  }, [])

  const toggleRaw = async () => {
    if (!showRawJson && !rawSettings) {
      const d = await api.get('/api/settings').catch(() => null)
      setRawSettings(d)
    }
    setShowRawJson(v => !v)
  }

  const downloadLogs = async () => {
    try {
      const resp = await fetch('/api/logs', { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } })
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'python-backend.log'; a.click()
      URL.revokeObjectURL(url)
      setDownloadMsg('✓ Downloaded')
    } catch { setDownloadMsg('✗ Failed') }
    setTimeout(() => setDownloadMsg(null), 2500)
  }

  const executeAction = async (action) => {
    setPending(null)
    const [method, path] = action.endpoint.split(' ')
    try {
      await (method === 'DELETE' ? api.delete(path) : api.post(path, {}))
      setResults(p => ({ ...p, [action.id]: '✓ Done' }))
    } catch { setResults(p => ({ ...p, [action.id]: '✗ Error' })) }
  }

  return (
    <div className="nx-tab-content">
      {pending && <ConfirmModal action={pending} onConfirm={executeAction} onCancel={() => setPending(null)} />}

      {/* Pipeline controls */}
      <div className="nx-section">
        <div className="nx-section-label">PIPELINE CONTROLS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">STRICT PIPELINE MODE</span>
              <span className="nx-toggle-desc">Sets STRICT_PIPELINE=1 — disables graceful fallbacks. Use in CI/staging to surface real failures.</span>
            </div>
            <NxToggle checked={cfg.strict_pipeline} onChange={v => set('strict_pipeline', v)} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">HITL GATE</span>
              <span className="nx-toggle-desc">Require human approval before high-risk agents (lead-hunter, qualification, data-analyst) execute sensitive operations.</span>
            </div>
            <NxToggle checked={cfg.hitl_gate} onChange={v => set('hitl_gate', v)} />
          </div>
        </div>

        <div className="nx-divider" />

        <div className="nx-form-grid">
          <NxField label="DATA RETENTION (DAYS)">
            <input className="nx-input" type="number" min={1} max={365} value={cfg.data_retention} onChange={e => set('data_retention', +e.target.value)} />
          </NxField>
        </div>
        <NxSaveBtn label="SAVE ADVANCED" saving={saving} saved={saved} onClick={save} />
      </div>

      <div className="nx-divider" />

      {/* Export logs */}
      <div className="nx-section">
        <div className="nx-section-label">DIAGNOSTICS</div>
        <div className="nx-btn-row">
          <button className="nx-save-btn nx-save-btn--outline" onClick={downloadLogs}>
            ⬇ DOWNLOAD LOGS
          </button>
          {downloadMsg && <span className={`nx-test-result ${downloadMsg.startsWith('✓') ? 'nx-test-result--ok' : 'nx-test-result--fail'}`}>{downloadMsg}</span>}
        </div>
        <div className="nx-toggle-list" style={{ marginTop: 16 }}>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">DEVELOPER MODE</span>
              <span className="nx-toggle-desc">Reveal raw JSON dump of current settings object</span>
            </div>
            <NxToggle checked={showRawJson} onChange={toggleRaw} />
          </div>
        </div>
        {showRawJson && rawSettings && (
          <pre className="nx-raw-json">{JSON.stringify(rawSettings, null, 2)}</pre>
        )}
      </div>

      <div className="nx-divider" />

      {/* Danger zone */}
      <div className="nx-section nx-section--danger">
        <div className="nx-section-label nx-section-label--danger">DANGER ZONE</div>
        <div className="nx-danger-warning">
          ⚠ These actions are irreversible. Each requires typing CONFIRM to proceed.
        </div>
        <div className="nx-redzone-list">
          {RED_ZONE_ACTIONS.map(a => (
            <div key={a.id} className="nx-redzone-row">
              <div className="nx-redzone-info">
                <span className="nx-redzone-label">{a.label}</span>
                <span className="nx-redzone-desc">{a.warning}</span>
              </div>
              <div className="nx-redzone-right">
                {results[a.id] && (
                  <span className={`nx-test-result ${results[a.id].startsWith('✓') ? 'nx-test-result--ok' : 'nx-test-result--fail'}`}>
                    {results[a.id]}
                  </span>
                )}
                <button className="nx-save-btn nx-save-btn--danger" onClick={() => setPending(a)}>
                  {a.label}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Tab 6: SECURITY ───────────────────────────────────────────────────── */

const SCOPE_OPTIONS = ['read', 'write', 'admin']
const EXPIRY_OPTIONS = [{ label: '30 days', value: '30d' }, { label: '90 days', value: '90d' }, { label: '1 year', value: '1y' }, { label: 'Never', value: 'never' }]

function ApiTokensSection() {
  const [tokens, setTokens] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', scopes: [], expiry: '90d' })
  const [creating, setCreating] = useState(false)
  const [newSecret, setNewSecret] = useState(null)

  useEffect(() => {
    api.get('/api/security/api-keys').then(d => setTokens(Array.isArray(d?.keys) ? d.keys : [])).catch(() => {})
  }, [])

  const toggleScope = s => setForm(p => ({
    ...p, scopes: p.scopes.includes(s) ? p.scopes.filter(x => x !== s) : [...p.scopes, s]
  }))

  const createToken = async () => {
    setCreating(true)
    try {
      const d = await api.post('/api/security/api-keys', form)
      if (d?.key) setNewSecret(d.key)
      const updated = await api.get('/api/security/api-keys').catch(() => null)
      if (updated?.keys) setTokens(updated.keys)
      setForm({ name: '', scopes: [], expiry: '90d' })
      setShowForm(false)
    } catch {}
    setCreating(false)
  }

  const rotate = async id => {
    if (!window.confirm('Rotate this token? The current key will stop working immediately.')) return
    await api.post(`/api/security/api-keys/${id}/rotate`, {}).catch(() => {})
    const d = await api.get('/api/security/api-keys').catch(() => null)
    if (d?.keys) setTokens(d.keys)
  }

  const revoke = async id => {
    if (!window.confirm('Revoke this token permanently?')) return
    await api.delete(`/api/security/api-keys/${id}`).catch(() => {})
    setTokens(p => p.filter(t => t.id !== id))
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">API TOKENS</div>
      {newSecret && (
        <div className="nx-sec-secret-reveal">
          <span className="nx-sec-secret-label">New token (copy now — shown once):</span>
          <code className="nx-sec-secret-val">{newSecret}</code>
          <button className="nx-save-btn nx-save-btn--outline" onClick={() => { navigator.clipboard.writeText(newSecret); setNewSecret(null) }}>COPY & DISMISS</button>
        </div>
      )}
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--tokens">
          <span>Name</span><span>Scopes</span><span>Last Used</span><span>Expires</span><span>Actions</span>
        </div>
        {tokens.length === 0 && <div className="nx-sec-empty">No API tokens — generate one below</div>}
        {tokens.map(t => (
          <div key={t.id} className="nx-sec-row nx-sec-row--tokens">
            <span className="nx-sec-name">{t.name}</span>
            <span className="nx-sec-scopes">{(t.scopes || []).join(', ') || '—'}</span>
            <span className="nx-sec-muted">{t.last_used ? new Date(t.last_used).toLocaleDateString() : 'Never'}</span>
            <span className={`nx-sec-muted ${t.expired ? 'nx-sec-expired' : ''}`}>
              {t.expiry ? new Date(t.expiry).toLocaleDateString() : '∞'}
            </span>
            <div className="nx-sec-actions">
              <button className="nx-save-btn nx-save-btn--outline nx-save-btn--xs" onClick={() => rotate(t.id)}>Rotate</button>
              <button className="nx-save-btn nx-save-btn--danger nx-save-btn--xs" onClick={() => revoke(t.id)}>Revoke</button>
            </div>
          </div>
        ))}
      </div>
      <button className="nx-save-btn nx-save-btn--outline" style={{ marginTop: 12 }} onClick={() => setShowForm(v => !v)}>
        {showForm ? 'CANCEL' : '+ GENERATE NEW TOKEN'}
      </button>
      {showForm && (
        <div className="nx-sec-token-form">
          <div className="nx-form-grid">
            <NxField label="TOKEN NAME">
              <input className="nx-input" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. CI pipeline key" />
            </NxField>
            <NxField label="EXPIRY">
              <select className="nx-input" value={form.expiry} onChange={e => setForm(p => ({ ...p, expiry: e.target.value }))}>
                {EXPIRY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </NxField>
          </div>
          <div className="nx-sec-scopes-row">
            <span className="nx-field-label">SCOPES</span>
            {SCOPE_OPTIONS.map(s => (
              <label key={s} className="nx-sec-scope-label">
                <input type="checkbox" className="nx-sec-checkbox" checked={form.scopes.includes(s)} onChange={() => toggleScope(s)} />
                {s}
              </label>
            ))}
          </div>
          <NxSaveBtn label="CREATE TOKEN" saving={creating} saved={false} onClick={createToken} />
        </div>
      )}
    </div>
  )
}

function JwtSection() {
  const [cfg, setCfg] = useState({ token_ttl: 60, refresh_ttl: 7 })
  const [rotating, setRotating] = useState(false)
  const [rotated, setRotated] = useState(false)
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings/llm', cfg)

  const rotateJwt = async () => {
    if (!window.confirm('This will invalidate ALL active sessions. Users will be logged out. Type CONFIRM to proceed.\n\nThis action cannot be undone.')) return
    const code = window.prompt('Type CONFIRM to rotate the JWT secret:')
    if (code !== 'CONFIRM') return
    setRotating(true)
    await api.post('/api/security/rotate-jwt', {}).catch(() => {})
    setRotating(false); setRotated(true)
    setTimeout(() => setRotated(false), 3000)
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">JWT SETTINGS</div>
      <div className="nx-form-grid">
        <NxField label="TOKEN TTL (MINUTES)">
          <input className="nx-input" type="number" min={5} max={1440} value={cfg.token_ttl} onChange={e => set('token_ttl', +e.target.value)} />
        </NxField>
        <NxField label="REFRESH TTL (DAYS)">
          <input className="nx-input" type="number" min={1} max={90} value={cfg.refresh_ttl} onChange={e => set('refresh_ttl', +e.target.value)} />
        </NxField>
      </div>
      <div className="nx-btn-row">
        <NxSaveBtn label="SAVE JWT SETTINGS" saving={saving} saved={saved} onClick={save} />
        <button className="nx-save-btn nx-save-btn--danger" onClick={rotateJwt} disabled={rotating}>
          {rotated ? '✓ SECRET ROTATED' : rotating ? 'ROTATING…' : 'ROTATE JWT SECRET'}
        </button>
      </div>
    </div>
  )
}

function RateLimitsSection() {
  const [limits, setLimits] = useState([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/api/security/rate-limits').then(d => setLimits(Array.isArray(d?.limits) ? d.limits : [
      { endpoint: '/api/chat',        rpm: 30,  burst: 5  },
      { endpoint: '/api/tasks/run',   rpm: 60,  burst: 10 },
      { endpoint: '/api/auth/login',  rpm: 5,   burst: 3  },
      { endpoint: '/api/auth/register', rpm: 3, burst: 2  },
      { endpoint: '/api/admin/*',     rpm: 20,  burst: 5  },
    ])).catch(() => {})
  }, [])

  const update = (i, k, v) => setLimits(p => p.map((r, idx) => idx === i ? { ...r, [k]: +v } : r))

  const save = async () => {
    setSaving(true)
    await api.put('/api/security/rate-limits', { limits }).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">RATE LIMITS</div>
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--rl">
          <span>Endpoint</span><span>Req / min</span><span>Burst</span>
        </div>
        {limits.map((r, i) => (
          <div key={r.endpoint} className="nx-sec-row nx-sec-row--rl">
            <span className="nx-sec-endpoint">{r.endpoint}</span>
            <input className="nx-input nx-input--sm" type="number" min={1} max={1000} value={r.rpm}   onChange={e => update(i, 'rpm',   e.target.value)} />
            <input className="nx-input nx-input--sm" type="number" min={1} max={100}  value={r.burst} onChange={e => update(i, 'burst', e.target.value)} />
          </div>
        ))}
      </div>
      <NxSaveBtn label="SAVE RATE LIMITS" saving={saving} saved={saved} onClick={save} />
    </div>
  )
}

function ActiveSessionsSection() {
  const [sessions, setSessions] = useState([])
  const [revoking, setRevoking] = useState(null)
  const [revokingAll, setRevokingAll] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => {
    setErr(null)
    api.get('/api/sessions')
      .then(d => setSessions(Array.isArray(d?.sessions) ? d.sessions : []))
      .catch(e => setErr(e.message || 'Failed to load sessions'))
  }
  useEffect(() => { load() }, [])

  const revokeOne = async sessionId => {
    setRevoking(sessionId)
    await api.delete(`/api/sessions/${sessionId}`).catch(() => {})
    setSessions(p => p.filter(s => s.session_id !== sessionId))
    setRevoking(null)
  }

  const revokeAll = async () => {
    if (!window.confirm('Revoke all other sessions? You will stay logged in on this device.')) return
    setRevokingAll(true)
    await api.delete('/api/sessions').catch(() => {})
    setSessions(p => p.filter(s => s.current))
    setRevokingAll(false)
  }

  const otherCount = sessions.filter(s => !s.current).length

  return (
    <div className="nx-section">
      <div className="nx-section-label">ACTIVE SESSIONS</div>
      {err && <div className="nx-badge nx-badge--err" style={{ marginBottom: 8 }}>{err}</div>}
      <div className="nx-sec-table-wrap">
        <div className="nx-sec-thead nx-sec-thead--sessions">
          <span>Device</span><span>Created</span><span>Last Used</span><span>Action</span>
        </div>
        {sessions.length === 0 && <div className="nx-sec-empty">No active sessions found</div>}
        {sessions.map(s => (
          <div key={s.session_id} className="nx-sec-row nx-sec-row--sessions">
            <span className="nx-sec-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {s.device_hint || 'unknown'}
              {s.current && <span className="nx-badge nx-badge--ok" style={{ fontSize: 10, padding: '1px 6px' }}>This device</span>}
            </span>
            <span className="nx-sec-muted">{s.created_at ? new Date(s.created_at).toLocaleString() : '—'}</span>
            <span className="nx-sec-muted">{s.last_used ? new Date(s.last_used).toLocaleString() : '—'}</span>
            {s.current
              ? <span className="nx-sec-muted" style={{ fontSize: 11 }}>current</span>
              : <button
                  className="nx-save-btn nx-save-btn--danger nx-save-btn--xs"
                  onClick={() => revokeOne(s.session_id)}
                  disabled={revoking === s.session_id}
                >
                  {revoking === s.session_id ? '…' : 'Revoke'}
                </button>
            }
          </div>
        ))}
      </div>
      {otherCount > 0 && (
        <button
          className="nx-save-btn nx-save-btn--danger"
          style={{ marginTop: 12 }}
          onClick={revokeAll}
          disabled={revokingAll}
        >
          {revokingAll ? 'REVOKING…' : `REVOKE ALL OTHER SESSIONS (${otherCount})`}
        </button>
      )}
    </div>
  )
}

function SecurityTab() {
  return (
    <div className="nx-tab-content">
      <ApiTokensSection />
      <div className="nx-divider" />
      <JwtSection />
      <div className="nx-divider" />
      <RateLimitsSection />
      <div className="nx-divider" />
      <ActiveSessionsSection />
    </div>
  )
}

/* ── Tab 7: NOTIFICATIONS ──────────────────────────────────────────────── */

const NOTIF_EVENTS = ['security:breach', 'task:failed', 'agent:error', 'hitl:request', 'revenue:event', 'system:critical']
const NOTIF_CHANNELS = ['toast', 'email', 'webhook']
const CHANNEL_LABELS = { toast: 'In-app toast', email: 'Email', webhook: 'Webhook' }

function NotificationsTab() {
  const [matrix, setMatrix] = useState(() => {
    const m = {}
    NOTIF_EVENTS.forEach(ev => { m[ev] = {}; NOTIF_CHANNELS.forEach(ch => { m[ev][ch] = false }) })
    return m
  })
  const [emailCfg, setEmailCfg] = useState({ address: '', test_sending: false })
  const [webhookCfg, setWebhookCfg] = useState({ url: '', secret: '' })
  const [thresholds, setThresholds] = useState({ threat_score: 75, cost_per_day: 50 })
  const [savingMatrix, setSavingMatrix] = useState(false)
  const [savedMatrix, setSavedMatrix] = useState(false)
  const [testingEmail, setTestingEmail] = useState(false)
  const [testingWebhook, setTestingWebhook] = useState(false)

  useEffect(() => {
    api.get('/api/settings/notifications').then(d => {
      if (d?.matrix) setMatrix(d.matrix)
      if (d?.email) setEmailCfg(p => ({ ...p, ...d.email }))
      if (d?.webhook) setWebhookCfg(p => ({ ...p, ...d.webhook }))
      if (d?.thresholds) setThresholds(p => ({ ...p, ...d.thresholds }))
    }).catch(() => {})
  }, [])

  const toggle = (ev, ch) => setMatrix(p => ({ ...p, [ev]: { ...p[ev], [ch]: !p[ev][ch] } }))

  const saveMatrix = async () => {
    setSavingMatrix(true)
    await api.put('/api/settings/notifications', { matrix, email: emailCfg, webhook: webhookCfg, thresholds }).catch(() => {})
    setSavingMatrix(false); setSavedMatrix(true)
    setTimeout(() => setSavedMatrix(false), 2000)
  }

  const testEmail = async () => {
    setTestingEmail(true)
    await api.post('/api/settings/notifications/test-email', { address: emailCfg.address }).catch(() => {})
    setTestingEmail(false)
  }

  const testWebhook = async () => {
    setTestingWebhook(true)
    await api.post('/api/settings/notifications/test-webhook', { url: webhookCfg.url }).catch(() => {})
    setTestingWebhook(false)
  }

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">NOTIFICATION MATRIX</div>
        <div className="nx-notif-matrix">
          <div className="nx-notif-header-row">
            <span className="nx-notif-event-col">Event</span>
            {NOTIF_CHANNELS.map(ch => <span key={ch} className="nx-notif-ch-col">{CHANNEL_LABELS[ch]}</span>)}
          </div>
          {NOTIF_EVENTS.map(ev => (
            <div key={ev} className="nx-notif-row">
              <span className="nx-notif-event-col nx-sec-mono">{ev}</span>
              {NOTIF_CHANNELS.map(ch => (
                <span key={ch} className="nx-notif-ch-col">
                  <input type="checkbox" className="nx-sec-checkbox" checked={matrix[ev]?.[ch] || false} onChange={() => toggle(ev, ch)} />
                </span>
              ))}
            </div>
          ))}
        </div>
        <NxSaveBtn label="SAVE NOTIFICATION SETTINGS" saving={savingMatrix} saved={savedMatrix} onClick={saveMatrix} />
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">EMAIL CONFIG</div>
        <div className="nx-form-grid">
          <NxField label="ALERT EMAIL ADDRESS" full>
            <div className="nx-btn-row" style={{ gap: 8 }}>
              <input className="nx-input" type="email" value={emailCfg.address} onChange={e => setEmailCfg(p => ({ ...p, address: e.target.value }))} placeholder="alerts@yourcompany.com" />
              <button className="nx-save-btn nx-save-btn--outline" onClick={testEmail} disabled={testingEmail || !emailCfg.address}>
                {testingEmail ? 'SENDING…' : 'SEND TEST'}
              </button>
            </div>
          </NxField>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">WEBHOOK CONFIG</div>
        <div className="nx-form-grid">
          <NxField label="OUTBOUND WEBHOOK URL" full>
            <div className="nx-btn-row" style={{ gap: 8 }}>
              <input className="nx-input" type="url" value={webhookCfg.url} onChange={e => setWebhookCfg(p => ({ ...p, url: e.target.value }))} placeholder="https://…" />
              <button className="nx-save-btn nx-save-btn--outline" onClick={testWebhook} disabled={testingWebhook || !webhookCfg.url}>
                {testingWebhook ? 'SENDING…' : 'SEND TEST'}
              </button>
            </div>
          </NxField>
          <NxField label="WEBHOOK SECRET">
            <input className="nx-input" type="password" value={webhookCfg.secret} onChange={e => setWebhookCfg(p => ({ ...p, secret: e.target.value }))} placeholder="hmac-secret" autoComplete="off" />
          </NxField>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">ALERT THRESHOLDS</div>
        <div className="nx-form-grid">
          <NxField label={`THREAT SCORE THRESHOLD — ${thresholds.threat_score}`} full>
            <NxSlider value={thresholds.threat_score} min={0} max={100} step={1} onChange={v => setThresholds(p => ({ ...p, threat_score: v }))} format={v => v} />
          </NxField>
          <NxField label="COST PER DAY THRESHOLD ($)">
            <input className="nx-input" type="number" min={0} value={thresholds.cost_per_day} onChange={e => setThresholds(p => ({ ...p, cost_per_day: +e.target.value }))} />
          </NxField>
        </div>
      </div>
    </div>
  )
}

/* ── Tab 8: BILLING & USAGE ────────────────────────────────────────────── */

function PieChart({ slices }) {
  // slices: [{ label, pct, color }]
  let angle = 0
  const segments = slices.map(s => {
    const start = angle
    angle += (s.pct / 100) * 360
    return { ...s, start, end: angle }
  })

  const toXY = deg => {
    const rad = (deg - 90) * Math.PI / 180
    return { x: 50 + 40 * Math.cos(rad), y: 50 + 40 * Math.sin(rad) }
  }

  const describeArc = (start, end) => {
    if (end - start >= 360) end = start + 359.99
    const s = toXY(start), e = toXY(end)
    const large = end - start > 180 ? 1 : 0
    return `M 50 50 L ${s.x} ${s.y} A 40 40 0 ${large} 1 ${e.x} ${e.y} Z`
  }

  return (
    <div className="nx-billing-pie-wrap">
      <svg viewBox="0 0 100 100" className="nx-billing-pie">
        {segments.map(s => <path key={s.label} d={describeArc(s.start, s.end)} fill={s.color} opacity={0.85} />)}
        <circle cx="50" cy="50" r="22" fill="var(--nx-bg-deep)" />
      </svg>
      <div className="nx-billing-legend">
        {slices.map(s => (
          <div key={s.label} className="nx-billing-legend-row">
            <span className="nx-billing-legend-dot" style={{ background: s.color }} />
            <span className="nx-billing-legend-label">{s.label}</span>
            <span className="nx-billing-legend-pct">{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const MODEL_COLORS = ['#e5c76b', '#20d6c7', '#ef4444', '#a78bfa', '#fb923c', '#34d399']

function BillingTab() {
  const [spend, setSpend] = useState(0)
  const [budget, setBudget] = useState(500)
  const [editBudget, setEditBudget] = useState(false)
  const [draftBudget, setDraftBudget] = useState(500)
  const [agentRows, setAgentRows] = useState([])
  const [hardCap, setHardCap] = useState(false)
  const [softWarn, setSoftWarn] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/api/intelligence/llm-calls').then(d => {
      const calls = Array.isArray(d?.calls) ? d.calls : Array.isArray(d) ? d : []
      const agg = {}
      calls.forEach(c => {
        const key = `${c.agent}|${c.model}`
        if (!agg[key]) agg[key] = { agent: c.agent, model: c.model, tokens: 0, cost: 0 }
        agg[key].tokens += c.tokens || 0
        agg[key].cost   += c.cost   || 0
      })
      const rows = Object.values(agg).sort((a, b) => b.cost - a.cost).slice(0, 10)
      setAgentRows(rows)
      setSpend(rows.reduce((s, r) => s + r.cost, 0))
    }).catch(() => {})
    api.get('/api/settings/billing').then(d => {
      if (d?.budget) { setBudget(d.budget); setDraftBudget(d.budget) }
      if (d?.hard_cap != null) setHardCap(d.hard_cap)
      if (d?.soft_warn != null) setSoftWarn(d.soft_warn)
    }).catch(() => {})
  }, [])

  const saveBilling = async () => {
    setSaving(true)
    await api.put('/api/settings/billing', { budget, hard_cap: hardCap, soft_warn: softWarn }).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const spendPct = Math.min((spend / budget) * 100, 100)

  // Model pie
  const modelTotals = {}
  agentRows.forEach(r => { modelTotals[r.model] = (modelTotals[r.model] || 0) + r.cost })
  const total = Object.values(modelTotals).reduce((s, v) => s + v, 0) || 1
  const pieSlices = Object.entries(modelTotals).map(([label, cost], i) => ({
    label, pct: (cost / total) * 100, color: MODEL_COLORS[i % MODEL_COLORS.length]
  }))

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">SPEND THIS MONTH</div>
        <div className="nx-billing-hero">
          <div className="nx-billing-spend">
            <span className="nx-billing-amount">${spend.toFixed(2)}</span>
            <span className="nx-billing-budget-label"> / </span>
            {editBudget ? (
              <div className="nx-billing-budget-edit">
                <span>$</span>
                <input className="nx-input nx-input--sm" type="number" min={0} value={draftBudget}
                  onChange={e => setDraftBudget(+e.target.value)} style={{ width: 90 }} />
                <button className="nx-save-btn" onClick={() => { setBudget(draftBudget); setEditBudget(false) }}>SET</button>
              </div>
            ) : (
              <button className="nx-billing-budget-btn" onClick={() => setEditBudget(true)}>
                ${budget.toFixed(2)} budget <span className="nx-billing-edit-icon">✎</span>
              </button>
            )}
          </div>
          <div className="nx-billing-bar-wrap">
            <div className="nx-billing-bar">
              <div className="nx-billing-bar-fill"
                style={{ width: `${spendPct}%`, background: spendPct > 90 ? '#ef4444' : spendPct > 80 ? '#fb923c' : 'var(--nx-gold)' }} />
            </div>
            <span className="nx-billing-bar-pct">{spendPct.toFixed(1)}% of budget</span>
          </div>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PER-AGENT SPEND (TOP 10)</div>
        <div className="nx-sec-table-wrap">
          <div className="nx-sec-thead nx-sec-thead--billing">
            <span>Agent</span><span>Model</span><span>Tokens</span><span>Cost</span><span>% Budget</span>
          </div>
          {agentRows.length === 0 && <div className="nx-sec-empty">No LLM call data yet</div>}
          {agentRows.map((r, i) => (
            <div key={i} className="nx-sec-row nx-sec-row--billing">
              <span className="nx-sec-name">{r.agent || '—'}</span>
              <span className="nx-sec-mono">{r.model || '—'}</span>
              <span className="nx-sec-muted">{r.tokens.toLocaleString()}</span>
              <span className="nx-sec-muted">${r.cost.toFixed(4)}</span>
              <span className="nx-sec-muted">{((r.cost / budget) * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PER-MODEL BREAKDOWN</div>
        {pieSlices.length > 0 ? <PieChart slices={pieSlices} /> : <div className="nx-sec-empty">No model data yet</div>}
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">BUDGET CONTROLS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">HARD CAP</span>
              <span className="nx-toggle-desc">Pause all LLM execution when monthly budget limit is reached</span>
            </div>
            <NxToggle checked={hardCap} onChange={setHardCap} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">SOFT WARNING AT 80%</span>
              <span className="nx-toggle-desc">Send an alert notification when spend reaches 80% of budget</span>
            </div>
            <NxToggle checked={softWarn} onChange={setSoftWarn} />
          </div>
        </div>
        <NxSaveBtn label="SAVE BILLING SETTINGS" saving={saving} saved={saved} onClick={saveBilling} />
      </div>
    </div>
  )
}

/* ── Tab 9: TEAM & ACCESS ──────────────────────────────────────────────── */

const BUILT_IN_ROLES = [
  { id: 'admin',    label: 'Admin',    desc: 'Full system access — can modify settings, manage agents, and control all operations.' },
  { id: 'operator', label: 'Operator', desc: 'Can run tasks and manage agents. Cannot change security settings or billing.' },
  { id: 'viewer',   label: 'Viewer',   desc: 'Read-only access to dashboards, logs, and agent status. No write permissions.' },
]

const PERM_RESOURCES = ['Agents', 'Tasks', 'Security', 'Settings', 'Economy', 'Knowledge']
const PERM_LEVELS    = ['None', 'Read', 'Write']

function TeamTab() {
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState(BUILT_IN_ROLES)
  const [permMatrix, setPermMatrix] = useState({})
  const [showInvite, setShowInvite] = useState(false)
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'viewer' })
  const [inviting, setInviting] = useState(false)

  useEffect(() => {
    api.get('/api/users').then(d => setUsers(Array.isArray(d?.users) ? d.users : [])).catch(() => {})
    api.get('/api/roles').then(d => { if (Array.isArray(d?.roles) && d.roles.length) setRoles(d.roles) }).catch(() => {})
    api.get('/api/permissions-matrix').then(d => { if (d?.matrix) setPermMatrix(d.matrix) }).catch(() => {})
  }, [])

  const defaultPerm = (resource, role) => {
    if (role === 'admin') return 'Write'
    if (role === 'operator') return resource === 'Security' || resource === 'Settings' ? 'None' : 'Write'
    return 'Read'
  }

  const getPerm = (resource, roleId) => permMatrix[resource]?.[roleId] ?? defaultPerm(resource, roleId)
  const setPerm = (resource, roleId, val) => setPermMatrix(p => ({
    ...p, [resource]: { ...(p[resource] || {}), [roleId]: val }
  }))

  const [savingPerms, setSavingPerms] = useState(false)
  const [savedPerms, setSavedPerms] = useState(false)
  const savePerms = async () => {
    setSavingPerms(true)
    await api.put('/api/permissions-matrix', { matrix: permMatrix }).catch(() => {})
    setSavingPerms(false); setSavedPerms(true)
    setTimeout(() => setSavedPerms(false), 2000)
  }

  const invite = async () => {
    setInviting(true)
    try {
      await api.post('/api/users', inviteForm)
      const d = await api.get('/api/users').catch(() => null)
      if (d?.users) setUsers(d.users)
      setInviteForm({ email: '', role: 'viewer' })
      setShowInvite(false)
    } catch {}
    setInviting(false)
  }

  const removeUser = async id => {
    if (!window.confirm('Remove this user from the system?')) return
    await api.delete(`/api/users/${id}`).catch(() => {})
    setUsers(p => p.filter(u => u.id !== id))
  }

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">USERS</div>
        <div className="nx-sec-table-wrap">
          <div className="nx-sec-thead nx-sec-thead--users">
            <span>Email</span><span>Role</span><span>Last Active</span><span>Status</span><span>Actions</span>
          </div>
          {users.length === 0 && <div className="nx-sec-empty">No users found</div>}
          {users.map(u => (
            <div key={u.id} className="nx-sec-row nx-sec-row--users">
              <span className="nx-sec-name">{u.email}</span>
              <span className="nx-sec-muted">{u.role}</span>
              <span className="nx-sec-muted">{u.last_active ? new Date(u.last_active).toLocaleDateString() : '—'}</span>
              <span className={`nx-sec-status nx-sec-status--${u.status || 'active'}`}>{(u.status || 'active').toUpperCase()}</span>
              <button className="nx-save-btn nx-save-btn--danger nx-save-btn--xs" onClick={() => removeUser(u.id)}>Remove</button>
            </div>
          ))}
        </div>
        <button className="nx-save-btn nx-save-btn--outline" style={{ marginTop: 12 }} onClick={() => setShowInvite(v => !v)}>
          {showInvite ? 'CANCEL' : '+ INVITE USER'}
        </button>
        {showInvite && (
          <div className="nx-sec-token-form">
            <div className="nx-form-grid">
              <NxField label="EMAIL ADDRESS">
                <input className="nx-input" type="email" value={inviteForm.email} onChange={e => setInviteForm(p => ({ ...p, email: e.target.value }))} placeholder="user@company.com" />
              </NxField>
              <NxField label="ROLE">
                <select className="nx-input" value={inviteForm.role} onChange={e => setInviteForm(p => ({ ...p, role: e.target.value }))}>
                  {roles.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                </select>
              </NxField>
            </div>
            <NxSaveBtn label="SEND INVITE" saving={inviting} saved={false} onClick={invite} />
          </div>
        )}
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">ROLES</div>
        <div className="nx-team-roles-grid">
          {BUILT_IN_ROLES.map(r => (
            <div key={r.id} className="nx-team-role-card">
              <div className="nx-team-role-name">{r.label}</div>
              <div className="nx-team-role-desc">{r.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PERMISSIONS MATRIX</div>
        <div className="nx-perm-table">
          <div className="nx-perm-thead">
            <span className="nx-perm-resource-col">Resource</span>
            {BUILT_IN_ROLES.map(r => <span key={r.id} className="nx-perm-role-col">{r.label}</span>)}
          </div>
          {PERM_RESOURCES.map(res => (
            <div key={res} className="nx-perm-row">
              <span className="nx-perm-resource-col nx-sec-name">{res}</span>
              {BUILT_IN_ROLES.map(r => (
                <span key={r.id} className="nx-perm-role-col">
                  <select className="nx-input nx-input--sm" value={getPerm(res, r.id)} onChange={e => setPerm(res, r.id, e.target.value)}>
                    {PERM_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </span>
              ))}
            </div>
          ))}
        </div>
        <NxSaveBtn label="SAVE PERMISSIONS" saving={savingPerms} saved={savedPerms} onClick={savePerms} />
      </div>
    </div>
  )
}

/* ── Root ──────────────────────────────────────────────────────────────── */

const TAB_CONTENT = [GeneralTab, LLMTab, IntegrationsTab, AppearanceTab, AdvancedTab, SecurityTab, NotificationsTab, BillingTab, TeamTab]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState(0)
  const TabComponent = TAB_CONTENT[activeTab]

  return (
    <div className="sp-page">
      <header className="sp-header">
        <div className="sp-title-row">
          <h1 className="sp-title">SYSTEM CONFIGURATION</h1>
          <span className="sp-subtitle">AETERNUS NEXUS — COMMAND CENTER 2095</span>
        </div>
        <nav className="sp-tabs" role="tablist">
          {TABS.map((tab, i) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === i}
              className={`sp-tab ${activeTab === i ? 'sp-tab--active' : ''}`}
              onClick={() => setActiveTab(i)}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <main className="sp-body">
        <TabComponent />
      </main>
    </div>
  )
}
