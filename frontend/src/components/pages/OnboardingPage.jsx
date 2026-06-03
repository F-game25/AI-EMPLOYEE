import { useState, useEffect } from 'react'
import api from '../../api/client'

const STEPS = [
  { id: 'welcome',  label: 'Welcome',  icon: '🤖' },
  { id: 'hardware', label: 'Hardware', icon: '⚡' },
  { id: 'provider', label: 'AI Model', icon: '🧠' },
  { id: 'keys',     label: 'API Keys', icon: '🔑' },
  { id: 'ready',    label: 'Ready',    icon: '✅' },
]

const PROVIDERS = [
  { id: 'ollama',         label: 'Ollama (Local, Free)',    desc: 'Run models on your own PC. Best for privacy.',              rec: 'vram' },
  { id: 'anthropic',      label: 'Anthropic Claude',        desc: 'Best reasoning. Requires API key.',                         rec: 'cloud' },
  { id: 'openrouter',     label: 'OpenRouter (200+ models)', desc: 'Access any model with one key.',                           rec: 'cloud' },
  { id: 'nvidia_nim',     label: 'NVIDIA NIM',              desc: 'Enterprise GPU inference. Local or cloud.',                 rec: 'gpu' },
  { id: 'remote_compute', label: 'Remote Compute',          desc: 'Rent GPU (RunPod, Lambda Labs). Ollama-compatible.',       rec: 'rent' },
]

export default function OnboardingPage({ onComplete }) {
  const [step, setStep] = useState(0)
  const [hw, setHw] = useState(null)
  const [provider, setProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [model, setModel] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/api/system/hw-profile').then(d => { if (d) setHw(d) }).catch(() => {})
  }, [])

  // Auto-set recommended provider from hardware
  useEffect(() => {
    if (!hw || provider) return
    setProvider(hw.recommended_provider || 'anthropic')
    setModel(hw.recommended_model || '')
  }, [hw])

  const testConnection = async () => {
    setTesting(true); setTestResult(null)
    try {
      const payload = { provider }
      if (apiKey) payload.key = apiKey
      if (endpoint) payload.endpoint = endpoint
      const r = await api.post('/api/settings/test-key', payload)
      setTestResult(r.ok || r.success ? 'ok' : 'fail')
    } catch { setTestResult('fail') }
    finally { setTesting(false) }
  }

  const finish = async () => {
    setSaving(true)
    try {
      await api.post('/api/settings/llm', { provider, model, api_key: apiKey, endpoint })
      if (provider !== 'anthropic') {
        await api.post('/api/settings/llm/swap', { backend: provider, model, endpoint: endpoint || undefined })
      }
    } catch (_) {}
    onComplete?.()
    setSaving(false)
  }

  const canNext = () => {
    if (step === 2) return !!provider
    if (step === 3) return testResult === 'ok' || provider === 'ollama'
    return true
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'linear-gradient(135deg, #090c14 0%, #0d1220 100%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: 'var(--font-mono, monospace)',
    }}>
      {/* Step indicator */}
      <div style={{ position: 'absolute', top: 32, left: '50%', transform: 'translateX(-50%)',
                    display: 'flex', gap: 8, alignItems: 'center' }}>
        {STEPS.map((s, i) => (
          <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: 13, fontWeight: 700,
              background: i < step ? 'rgba(229,199,107,0.9)' : i === step ? 'rgba(229,199,107,0.2)' : 'rgba(255,255,255,0.06)',
              border: i === step ? '1px solid rgba(229,199,107,0.6)' : '1px solid rgba(255,255,255,0.1)',
              color: i < step ? '#090c14' : i === step ? '#e5c76b' : 'rgba(255,255,255,0.3)',
              transition: 'all 0.3s',
            }}>{i < step ? '✓' : i + 1}</div>
            {i < STEPS.length - 1 && (
              <div style={{ width: 32, height: 1, background: i < step ? 'rgba(229,199,107,0.5)' : 'rgba(255,255,255,0.1)' }} />
            )}
          </div>
        ))}
      </div>

      {/* Card */}
      <div style={{
        width: 560, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(229,199,107,0.15)',
        borderRadius: 16, padding: '48px 48px 40px', backdropFilter: 'blur(20px)',
      }}>
        {step === 0 && <StepWelcome />}
        {step === 1 && <StepHardware hw={hw} />}
        {step === 2 && <StepProvider provider={provider} setProvider={setProvider} model={model} setModel={setModel} hw={hw} />}
        {step === 3 && <StepKeys provider={provider} apiKey={apiKey} setApiKey={setApiKey}
                                  endpoint={endpoint} setEndpoint={setEndpoint}
                                  testing={testing} testResult={testResult} onTest={testConnection} />}
        {step === 4 && <StepReady provider={provider} model={model} hw={hw} />}

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 40 }}>
          {step > 0
            ? <button onClick={() => setStep(s => s - 1)} style={btnStyle(false)}>← Back</button>
            : <div />
          }
          {step < STEPS.length - 1
            ? <button onClick={() => setStep(s => s + 1)} disabled={!canNext()} style={btnStyle(canNext())}>
                Continue →
              </button>
            : <button onClick={finish} disabled={saving} style={btnStyle(true, '#e5c76b')}>
                {saving ? 'Setting up…' : '🚀 Launch AI Employee'}
              </button>
          }
        </div>
      </div>
    </div>
  )
}

function btnStyle(active, accent = 'rgba(229,199,107,0.7)') {
  return {
    padding: '10px 24px', borderRadius: 8, border: `1px solid ${active ? accent : 'rgba(255,255,255,0.1)'}`,
    background: 'transparent', color: active ? accent : 'rgba(255,255,255,0.3)',
    cursor: active ? 'pointer' : 'not-allowed', fontSize: 13, fontFamily: 'inherit',
    transition: 'all 0.2s',
  }
}

function StepWelcome() {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 64, marginBottom: 24 }}>🤖</div>
      <h1 style={{ color: '#e5c76b', fontSize: 28, fontWeight: 700, margin: '0 0 12px' }}>
        Welcome to AI Employee
      </h1>
      <p style={{ color: 'rgba(255,255,255,0.55)', lineHeight: 1.7, margin: '0 0 24px', fontSize: 14 }}>
        Your autonomous AI workforce platform. We'll get you set up in under 2 minutes.
      </p>
      <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
        {['56+ AI Agents', '147 Skills', 'Local & Cloud Models', 'HITL Safety'].map(f => (
          <span key={f} style={{ padding: '4px 12px', borderRadius: 20, background: 'rgba(229,199,107,0.08)',
                                 border: '1px solid rgba(229,199,107,0.2)', color: 'rgba(229,199,107,0.8)', fontSize: 12 }}>
            {f}
          </span>
        ))}
      </div>
    </div>
  )
}

function StepHardware({ hw }) {
  return (
    <div>
      <h2 style={titleStyle}>⚡ Your Hardware</h2>
      <p style={subStyle}>We detected your system specs to recommend the best AI model configuration.</p>
      {hw ? (
        <>
          <div style={infoGrid}>
            <InfoRow label="CPU Cores" value={`${hw.cpu_cores} cores`} />
            <InfoRow label="RAM" value={`${hw.ram_gb} GB`} />
            <InfoRow label="GPU" value={hw.gpu || 'None detected'} />
            {hw.vram_gb > 0 && <InfoRow label="VRAM" value={`${hw.vram_gb} GB`} />}
          </div>
          <div style={{ marginTop: 20, padding: '12px 16px', borderRadius: 8,
                        background: 'rgba(100,220,160,0.08)', border: '1px solid rgba(100,220,160,0.2)' }}>
            <div style={{ color: 'rgba(100,220,160,0.9)', fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
              RECOMMENDED SETUP
            </div>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13 }}>
              {hw.recommended_provider} / {hw.recommended_model}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, marginTop: 4 }}>{hw.notes}</div>
          </div>
        </>
      ) : (
        <div style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center', padding: 32 }}>Scanning hardware…</div>
      )}
    </div>
  )
}

function StepProvider({ provider, setProvider, model, setModel, hw }) {
  return (
    <div>
      <h2 style={titleStyle}>🧠 Choose AI Provider</h2>
      <p style={subStyle}>You can change this anytime in Settings → LLM.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {PROVIDERS.map(p => {
          const isRec = hw && hw.recommended_provider === p.id
          return (
            <button key={p.id} onClick={() => setProvider(p.id)} style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
              borderRadius: 8, border: `1px solid ${provider === p.id ? 'rgba(229,199,107,0.5)' : 'rgba(255,255,255,0.08)'}`,
              background: provider === p.id ? 'rgba(229,199,107,0.06)' : 'transparent',
              cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ color: provider === p.id ? '#e5c76b' : 'rgba(255,255,255,0.8)', fontSize: 13, fontWeight: 600 }}>
                  {p.label}
                  {isRec && <span style={{ marginLeft: 8, fontSize: 10, color: 'rgba(100,220,160,0.8)', fontWeight: 400 }}>★ Recommended for your hardware</span>}
                </div>
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, marginTop: 2 }}>{p.desc}</div>
              </div>
              {provider === p.id && <span style={{ color: '#e5c76b' }}>✓</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function StepKeys({ provider, apiKey, setApiKey, endpoint, setEndpoint, testing, testResult, onTest }) {
  const needsKey = ['anthropic', 'openrouter', 'nvidia_nim'].includes(provider)
  const needsEndpoint = ['ollama', 'nvidia_nim', 'remote_compute'].includes(provider)

  return (
    <div>
      <h2 style={titleStyle}>🔑 Configure Connection</h2>
      {provider === 'ollama' && (
        <div style={{ padding: '12px 16px', borderRadius: 8, background: 'rgba(100,220,160,0.08)',
                      border: '1px solid rgba(100,220,160,0.15)', marginBottom: 20 }}>
          <div style={{ color: 'rgba(100,220,160,0.9)', fontSize: 13, marginBottom: 8 }}>
            Make sure Ollama is running on your machine.
          </div>
          <code style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', display: 'block' }}>
            curl https://ollama.ai/install.sh | sh<br />
            ollama run llama3.3
          </code>
        </div>
      )}
      {needsKey && (
        <label style={labelStyle}>
          API KEY
          <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
            placeholder={provider === 'anthropic' ? 'sk-ant-…' : provider === 'openrouter' ? 'sk-or-v1-…' : 'nvapi-…'}
            style={inputStyle} autoComplete="off" />
        </label>
      )}
      {needsEndpoint && (
        <label style={labelStyle}>
          ENDPOINT
          <input type="text" value={endpoint} onChange={e => setEndpoint(e.target.value)}
            placeholder={provider === 'nvidia_nim' ? 'https://integrate.api.nvidia.com/v1' : 'http://localhost:11434'}
            style={inputStyle} />
        </label>
      )}
      <button onClick={onTest} disabled={testing} style={{ ...btnStyle(true), marginTop: 16 }}>
        {testing ? 'Testing…' : 'Test Connection'}
      </button>
      {testResult === 'ok' && <div style={{ color: 'rgba(100,220,160,0.9)', marginTop: 8, fontSize: 13 }}>✓ Connected!</div>}
      {testResult === 'fail' && <div style={{ color: 'rgba(255,80,80,0.9)', marginTop: 8, fontSize: 13 }}>✗ Could not connect — check your settings</div>}
    </div>
  )
}

function StepReady({ provider, model, hw }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 64, marginBottom: 20 }}>✅</div>
      <h2 style={titleStyle}>You're all set!</h2>
      <p style={subStyle}>AI Employee will start and open your dashboard. The system tray icon lets you quick-access it anytime.</p>
      <div style={infoGrid}>
        <InfoRow label="Provider" value={provider} />
        <InfoRow label="Model" value={model || 'default'} />
        {hw && <InfoRow label="Hardware" value={`${hw.cpu_cores}c / ${hw.ram_gb}GB RAM${hw.gpu ? ` / ${hw.vram_gb}GB VRAM` : ''}`} />}
      </div>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
      <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12 }}>{label}</span>
      <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: 12 }}>{value}</span>
    </div>
  )
}

const titleStyle = { color: '#e5c76b', fontSize: 22, fontWeight: 700, margin: '0 0 8px' }
const subStyle   = { color: 'rgba(255,255,255,0.45)', fontSize: 13, margin: '0 0 24px', lineHeight: 1.6 }
const labelStyle = { display: 'block', color: 'rgba(255,255,255,0.45)', fontSize: 11, letterSpacing: 1, marginBottom: 16 }
const inputStyle = {
  display: 'block', width: '100%', marginTop: 6, padding: '10px 12px',
  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 6, color: '#fff', fontSize: 13, fontFamily: 'inherit', boxSizing: 'border-box',
}
const infoGrid = { marginTop: 16 }
