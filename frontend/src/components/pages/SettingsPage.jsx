import { useState, useEffect, useRef } from 'react'
import api from '../../api/client'
import { useUpdateCheck } from '../../hooks/useUpdateCheck'
import { useAppStore } from '../../store/appStore'
import './SettingsPage.css'
import { NxToggle, NxSlider, NxField, NxSaveBtn, useSave, SafetyConfirmModal } from './settings/controls'
import SecurityTab from './settings/SecurityTab'
import BillingTab from './settings/BillingTab'
import TeamTab from './settings/TeamTab'

/* ── Constants ─────────────────────────────────────────────────────────── */

const TABS = ['GENERAL', 'LLM', 'INTEGRATIONS', 'APPEARANCE', 'ADVANCED', 'SECURITY', 'NOTIFICATIONS', 'BILLING & USAGE', 'TEAM & ACCESS']

const LLM_MODELS = {
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
  ollama:    ['llama3.3', 'deepseek-r1', 'mistral'],
  openai:    ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'],
}

const RED_ZONE_ACTIONS = [
  { id: 'reset-state',         label: 'RESET ALL STATE',        endpoint: 'POST /api/admin/reset-state',             warning: 'Resets all runtime state files. This cannot be undone.', confirmText: 'RESET ALL STATE', risk: 'critical' },
  { id: 'wipe-memory',         label: 'WIPE MEM0 MEMORY',       endpoint: 'DELETE /api/neural-brain/memory/all',      warning: 'Permanently deletes all stored memories. Cannot be undone.', confirmText: 'WIPE MEM0 MEMORY', risk: 'critical' },
  { id: 'factory-reset',       label: 'FACTORY RESET',          endpoint: 'POST /api/admin/factory-reset',           warning: 'Complete system factory reset. All data will be lost.', confirmText: 'FACTORY RESET', risk: 'critical' },
  { id: 'evolution-rollback',  label: 'EVOLUTION ROLLBACK',     endpoint: 'POST /api/evolution/rollback',            warning: 'Rolls back all applied evolution patches.', confirmText: 'EVOLUTION ROLLBACK', risk: 'high' },
  { id: 'invalidate-sessions', label: 'INVALIDATE SESSIONS',    endpoint: 'POST /api/admin/sessions/invalidate-all', warning: 'Logs out all active users immediately.', confirmText: 'INVALIDATE SESSIONS', risk: 'high' },
  { id: 'flush-telemetry',     label: 'FLUSH TELEMETRY',        endpoint: 'POST /api/neural-brain/telemetry/flush',  warning: 'Clears all queued telemetry data.', confirmText: 'FLUSH TELEMETRY', risk: 'medium' },
]

/* ── Shared primitives ─────────────────────────────────────────────────── */


/* ── Tab 1: GENERAL ────────────────────────────────────────────────────── */

function GeneralTab() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
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
      <div className="nx-section">
        <div className="nx-section-label">ADMIN SETUP</div>
        <p className="nx-help-text">
          Reopen the technical setup wizard to verify runtime, providers, memory, integrations, approval gates, and the safe smoke test.
        </p>
        <button className="nx-save-btn" type="button" onClick={() => setActiveSection('setup')}>
          OPEN SETUP CENTER
        </button>
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

// Rendering (GPU) mode — controllable in-app instead of a terminal env var.
// Only shown inside the Electron launcher (window.ai present). Applies on restart.
const RENDER_LABELS = { auto: 'Auto (recommended)', hardware: 'Hardware (GPU)', software: 'Software (most stable)' }
const RENDER_DESC = {
  auto: 'Use the GPU; fall back to software if the WebGL context is lost.',
  hardware: 'Force GPU rendering — fastest, but unstable on some Linux drivers.',
  software: 'SwiftShader software rendering — slower, but never loses the WebGL context. Use this if pages flicker or go blank.',
}
function RenderingSection() {
  const [mode, setMode] = useState(null)
  const [options, setOptions] = useState(['auto', 'hardware', 'software'])
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (!window.ai?.getRenderMode) { setMode('unavailable'); return }
    window.ai.getRenderMode()
      .then(r => { setMode(r.mode || 'auto'); if (Array.isArray(r.options)) setOptions(r.options) })
      .catch(() => setMode('unavailable'))
  }, [])
  if (mode === 'unavailable' || mode === null) return null   // browser mode — no launcher
  const choose = async (m) => {
    setMode(m)
    try { await window.ai.setRenderMode(m); setDirty(true) } catch { /* */ }
  }
  return (
    <>
      <div className="nx-divider" />
      <div className="nx-section">
        <div className="nx-section-label">RENDERING (GPU)</div>
        <div className="nx-render-opts" role="radiogroup" aria-label="Rendering mode">
          {options.map(o => (
            <button key={o} type="button" role="radio" aria-checked={mode === o}
              className={`nx-render-opt ${mode === o ? 'nx-render-opt--active' : ''}`} onClick={() => choose(o)}>
              <span className="nx-render-opt__title">{RENDER_LABELS[o] || o}{mode === o && ' ✓'}</span>
              <span className="nx-render-opt__desc">{RENDER_DESC[o] || ''}</span>
            </button>
          ))}
        </div>
        {dirty && (
          <div className="nx-render-restart">
            <span>Saved — restart the app to apply.</span>
            <button className="nx-save-btn" onClick={() => window.ai?.restartSystem?.()}>Restart now</button>
          </div>
        )}
      </div>
    </>
  )
}

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

      <RenderingSection />
    </div>
  )
}

/* ── Tab 5: ADVANCED ───────────────────────────────────────────────────── */


// Self-evolution control — restored from the removed EvolutionPage. Backend live at
// /api/evolution/{status,mode}. AUTO requires explicit confirm (autonomous code deploy).
const EVO_MODES = [
  { id: 'OFF',  label: 'Off',  desc: 'No self-modification. System is frozen.' },
  { id: 'SAFE', label: 'Safe', desc: 'Proposes patches — requires human approval before applying.' },
  { id: 'AUTO', label: 'Auto', desc: 'Autonomously generates, validates, and deploys safe patches.' },
]
function EvolutionModePanel() {
  const [status, setStatus] = useState(null)
  const [mode, setMode] = useState(null)
  const load = () => api.get('/api/evolution/status').then(d => { setStatus(d); setMode(d.mode || 'OFF') }).catch(() => setMode('OFF'))
  useEffect(() => { load() }, [])
  const choose = async (m) => {
    if (m === mode) return
    if (m === 'AUTO' && !window.confirm('Enable AUTO evolution? The system will autonomously generate and deploy code patches without human approval.')) return
    setMode(m)
    try { const d = await api.post('/api/evolution/mode', { mode: m }); setMode(d.mode || m); load() } catch { /* */ }
  }
  return (
    <div className="nx-section">
      <div className="nx-section-label">SELF-EVOLUTION</div>
      <div className="nx-evo-stats">
        <span>Loop: <b>{status?.running ? 'RUNNING' : 'IDLE'}</b></span>
        <span>Patches applied: <b>{status?.patches_applied ?? 0}</b></span>
        {status?.patches_proposed != null && <span>Proposed: <b>{status.patches_proposed}</b></span>}
      </div>
      <div className="nx-render-opts" role="radiogroup" aria-label="Evolution mode">
        {EVO_MODES.map(m => (
          <button key={m.id} type="button" role="radio" aria-checked={mode === m.id}
            className={`nx-render-opt ${mode === m.id ? 'nx-render-opt--active' : ''}`} onClick={() => choose(m.id)}>
            <span className="nx-render-opt__title">{m.label}{mode === m.id && ' ✓'}</span>
            <span className="nx-render-opt__desc">{m.desc}</span>
          </button>
        ))}
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
      const resp = await fetch('/api/logs', { headers: { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt') || ''}` } })
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'python-backend.log'; a.click()
      URL.revokeObjectURL(url)
      setDownloadMsg('✓ Downloaded')
    } catch { setDownloadMsg('✗ Failed') }
    setTimeout(() => setDownloadMsg(null), 2500)
  }

  const executeAction = async (action, safety) => {
    setPending(null)
    try {
      const result = await api.post('/api/admin/safety-action', {
        action_id: action.id,
        endpoint: action.endpoint,
        reason: safety.reason,
        confirmation: safety.confirmation,
        execution_mode: 'staged',
      })
      setResults(p => ({ ...p, [action.id]: `✓ Staged · ${result.audit_id || result.trace_id}` }))
    } catch (e) {
      setResults(p => ({ ...p, [action.id]: `✗ ${e.message || 'Error'}` }))
    }
  }

  return (
    <div className="nx-tab-content">
      {pending && <SafetyConfirmModal action={pending} onConfirm={executeAction} onCancel={() => setPending(null)} />}

      <EvolutionModePanel />
      <div className="nx-divider" />

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
          These actions are staged through the admin safety endpoint first. They require typed confirmation, a reason, a countdown, and an audit record.
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
