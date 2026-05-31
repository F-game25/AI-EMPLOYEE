import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxField, NxSaveBtn, NxSlider, useSave } from './controls'

const LLM_MODELS = {
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
  ollama:    ['llama3.3', 'deepseek-r1', 'mistral'],
  openai:    ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'],
}

export default function LLMTab() {
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
