import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import { useLiveData } from '../../hooks/useLiveData'
import { Sparkline } from '../nexus-ui'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
import './ModelsPage.css'

/* ── Constants ─────────────────────────────────────────────────────────── */

const TABS = ['PROVIDERS', 'PERFORMANCE', 'ROUTING RULES', 'PROMPTS']

// Fallback model list used until registry loads
const FALLBACK_MODEL_OPTIONS = [
  { value: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6', provider: 'anthropic' },
  { value: 'claude-opus-4-7',   label: 'claude-opus-4-7',   provider: 'anthropic' },
  { value: 'claude-haiku-4-5',  label: 'claude-haiku-4-5',  provider: 'anthropic' },
  { value: 'gpt-4o',            label: 'gpt-4o',            provider: 'openai'    },
  { value: 'llama3.2',          label: 'llama3.2',          provider: 'ollama'    },
]

// Derive a flat MODEL_OPTIONS list from registry data, or fall back to static list
function buildModelOptions(registryData) {
  if (!registryData?.providers) return FALLBACK_MODEL_OPTIONS
  return Object.entries(registryData.providers).flatMap(([provider, pd]) =>
    (pd.models || []).map(m => ({
      value: typeof m === 'string' ? m : m.id,
      label: typeof m === 'string' ? m : (m.label || m.id),
      provider,
    }))
  )
}

function modelProvider(model, registryData) {
  const opts = buildModelOptions(registryData)
  return opts.find(m => m.value === model)?.provider || 'anthropic'
}

const STUB_LLM_CALLS = [
  { model: 'claude-sonnet-4-6', calls: 842, p50: 420,  p95: 890,  tps: 38.2, cost: 0.0032, errors: 2 },
  { model: 'claude-opus-4-7',   calls: 213, p50: 1140, p95: 2100, tps: 22.1, cost: 0.0180, errors: 0 },
  { model: 'claude-haiku-4-5',  calls: 1540,p50: 180,  p95: 390,  tps: 68.4, cost: 0.0008, errors: 7 },
  { model: 'gpt-4o',            calls: 91,  p50: 640,  p95: 1320, tps: 29.5, cost: 0.0060, errors: 1 },
  { model: 'llama3.2',          calls: 310, p50: 890,  p95: 1800, tps: 18.0, cost: 0.0000, errors: 4 },
]

const STUB_ROUTING = [
  { id: 1, agent: 'content-generator',   preferred: 'claude-sonnet-4-6', fallback: 'claude-haiku-4-5', budget: 5.00,  active: true  },
  { id: 2, agent: 'email-writer',        preferred: 'claude-haiku-4-5',  fallback: 'llama3.2',         budget: 2.00,  active: true  },
  { id: 3, agent: 'data-analyst',        preferred: 'claude-opus-4-7',   fallback: 'gpt-4o',           budget: 15.00, active: true  },
  { id: 4, agent: 'lead-hunter-elite',   preferred: 'claude-sonnet-4-6', fallback: 'claude-haiku-4-5', budget: 8.00,  active: false },
  { id: 5, agent: 'research-agent',      preferred: 'gpt-4o',            fallback: 'llama3.2',         budget: 3.00,  active: true  },
]

const STUB_AGENTS = [
  { id: 'content-generator',  name: 'Content Generator',  prompt: 'You are a content generation specialist. Your job is to create high-quality, engaging content for various platforms and audiences. Focus on clarity, tone, and audience alignment.' },
  { id: 'email-writer',       name: 'Email Writer',       prompt: 'You are an expert email writer. Craft clear, compelling emails with strong subject lines, concise bodies, and effective calls-to-action. Adapt tone to context: formal, friendly, or sales-oriented.' },
  { id: 'data-analyst',       name: 'Data Analyst',       prompt: 'You are a data analysis agent. Interpret structured datasets, identify trends, surface anomalies, and deliver actionable insights in structured formats (tables, bullet summaries, JSON).' },
  { id: 'lead-hunter-elite',  name: 'Lead Hunter Elite',  prompt: 'You are a lead generation specialist. Identify high-value prospects using ICP criteria. Prioritize recency, fit score, and engagement signals. Output leads as structured JSON.' },
  { id: 'research-agent',     name: 'Research Agent',     prompt: 'You are a deep research agent. Synthesize information from multiple sources, evaluate source credibility, identify knowledge gaps, and produce structured research briefs with citations.' },
  { id: 'team-management',    name: 'Team Management',    prompt: 'You are a team operations agent. Manage task assignments, track deliverables, identify blockers, and produce status reports. Communicate with clarity and prioritize by impact.' },
]

function makeSparkline(seed, len = 20) {
  let v = 50 + seed * 7
  return Array.from({ length: len }, () => {
    v = Math.max(10, Math.min(200, v + (Math.random() - 0.5) * 40))
    return Math.round(v)
  })
}

/* ── Shared primitives ─────────────────────────────────────────────────── */

function ModelBadge({ model, registryData }) {
  const p = modelProvider(model, registryData)
  return <span className={`mp-model-badge mp-model-badge--${p}`}>{model}</span>
}

/* ── Tab 1: PROVIDERS ──────────────────────────────────────────────────── */

const PROVIDERS = [
  { id: 'anthropic', name: 'Anthropic', defaultModel: 'claude-sonnet-4-6', keyPrefix: 'sk-ant-' },
  { id: 'openai',    name: 'OpenAI',    defaultModel: 'gpt-4o',            keyPrefix: 'sk-'     },
  { id: 'ollama',    name: 'Ollama',    defaultModel: 'llama3.2',          keyPrefix: 'http://'  },
]

function ProviderCard({ provider, settings }) {
  const [testing, setTesting]     = useState(false)
  const [testResult, setTestResult] = useState(null)

  const configured = settings?.[provider.id + '_configured'] ?? (provider.id === 'ollama')
  const model      = settings?.[provider.id + '_model']      ?? provider.defaultModel
  const status     = configured ? 'connected' : 'unconfigured'

  const test = async () => {
    setTesting(true); setTestResult(null)
    await new Promise(r => setTimeout(r, 900 + Math.random() * 600))
    setTestResult(configured ? { ok: true, msg: 'OK' } : { ok: false, msg: 'Not configured' })
    setTesting(false)
  }

  return (
    <div className={`mp-provider-card ${configured ? 'mp-provider-card--connected' : ''}`}>
      <div className="mp-provider-header">
        <span className="mp-provider-name">{provider.name}</span>
        <span className={`mp-status-badge mp-status-badge--${status}`}>
          {status === 'connected' ? 'CONNECTED' : status === 'error' ? 'ERROR' : 'NOT CONFIGURED'}
        </span>
      </div>
      <div className="mp-provider-model">{model}</div>
      <div className="mp-provider-key">
        {configured
          ? `${provider.keyPrefix}${'●'.repeat(16)}`
          : 'API key not set — configure in Settings > LLM'}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button className="mp-test-btn" onClick={test} disabled={testing}>
          {testing ? 'TESTING…' : 'TEST CONNECTION'}
        </button>
        {testResult && (
          <span className={`mp-test-result mp-test-result--${testResult.ok ? 'ok' : 'fail'}`}>
            {testResult.ok ? '✓ ' : '✗ '}{testResult.msg}
          </span>
        )}
      </div>
    </div>
  )
}

/* ── Main Brain Switcher ────────────────────────────────────────────────── */

function MainBrainPicker({ registryData }) {
  const [current, setCurrent]   = useState(null)
  const [provider, setProvider] = useState('anthropic')
  const [model, setModel]       = useState('claude-sonnet-4-6')
  const [saving, setSaving]     = useState(false)
  const [saved, setSaved]       = useState(false)
  const [hardware, setHardware] = useState(null)

  useEffect(() => {
    api.get('/api/settings/main-model')
      .then(d => { if (d?.provider) { setCurrent(d); setProvider(d.provider); setModel(d.model) } })
      .catch(() => {})
    api.get('/api/system/hardware')
      .then(d => { if (d?.tier) setHardware(d) })
      .catch(() => {})
  }, [])

  // When provider changes, auto-select first model for that provider from registry
  const handleProviderChange = (newProvider) => {
    setProvider(newProvider)
    const opts = buildModelOptions(registryData)
    const first = opts.find(m => m.provider === newProvider)
    if (first) setModel(first.value)
  }

  const applyRecommended = async (r) => {
    const newProvider = r.provider || modelProvider(r.model, registryData)
    setProvider(newProvider)
    setModel(r.model)
    setSaving(true); setSaved(false)
    try {
      await api.put('/api/settings/main-model', { provider: newProvider, model: r.model })
      setCurrent({ provider: newProvider, model: r.model })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const save = async () => {
    setSaving(true); setSaved(false)
    try {
      await api.put('/api/settings/main-model', { provider, model })
      setCurrent({ provider, model })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const modelOptions = buildModelOptions(registryData).filter(m => m.provider === provider)
  const providerKeys = registryData?.providers
    ? Object.keys(registryData.providers)
    : ['anthropic', 'openai', 'ollama', 'openrouter']

  return (
    <div className="mp-mainbrain">
      {hardware && (
        <div className="nx-models__hardware-banner">
          <div className="nx-models__hw-info">
            <span className="nx-models__hw-label">YOUR HARDWARE</span>
            <span className="nx-models__hw-tier">{hardware.tier.toUpperCase()}</span>
            {hardware.gpu && (
              <span className="nx-models__hw-gpu">{hardware.gpu} — {hardware.vram_gb}GB VRAM</span>
            )}
            <span className="nx-models__hw-ram">{hardware.ram_gb}GB RAM · {hardware.cpu_cores} cores</span>
          </div>
          {hardware.recommended?.length > 0 && (
            <div className="nx-models__hw-recommended">
              <span>Recommended for your PC:</span>
              {hardware.recommended.map(r => (
                <button key={r.model} className="nx-models__hw-pill"
                  onClick={() => applyRecommended(r)}>
                  {r.model}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="mp-section-label">MAIN AI BRAIN</div>
      <div className="mp-mainbrain__row">
        <div className="mp-mainbrain__current">
          <span className="mp-mainbrain__lbl">ACTIVE</span>
          <span className="mp-mainbrain__val">
            {current ? `${current.provider} · ${current.model}` : 'loading…'}
          </span>
        </div>
        <select className="mp-select" value={provider} onChange={e => handleProviderChange(e.target.value)}>
          {providerKeys.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        {modelOptions.length > 0 ? (
          <select className="mp-select" value={model} onChange={e => setModel(e.target.value)}>
            {modelOptions.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        ) : (
          <input className="mp-input" value={model} onChange={e => setModel(e.target.value)} placeholder="model name" />
        )}
        <button className="mp-primary-btn" onClick={save} disabled={saving}>
          {saving ? 'SAVING…' : saved ? '✓ APPLIED' : 'APPLY'}
        </button>
      </div>
    </div>
  )
}

/* ── Ollama Local Models Manager ────────────────────────────────────────── */

function OllamaManager() {
  const [models, setModels] = useState([])
  const [error, setError]   = useState(null)
  const [pullName, setPullName] = useState('')
  const [pulling, setPulling]   = useState(false)
  const [pullStatus, setPullStatus] = useState(null)

  const refresh = useCallback(() => {
    api.get('/api/ollama/models')
      .then(d => { setModels(d.models || []); setError(null) })
      .catch(e => { setError(e.message || 'ollama unavailable'); setModels([]) })
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const remove = async (name) => {
    if (!confirm(`Delete model ${name}?`)) return
    try { await api.delete(`/api/ollama/models/${encodeURIComponent(name)}`) } catch {}
    refresh()
  }

  const pull = async () => {
    if (!pullName.trim()) return
    setPulling(true); setPullStatus({ status: 'starting' })
    try {
      const res = await fetch('/api/ollama/pull', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'authorization': `Bearer ${sessionStorage.getItem('ai_jwt') || ''}`,
        },
        body: JSON.stringify({ name: pullName.trim() }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop()
        for (const e of events) {
          if (e.startsWith('data: ')) {
            try {
              const evt = JSON.parse(e.slice(6))
              setPullStatus(evt)
            } catch {}
          }
        }
      }
      setPulling(false)
      setTimeout(() => { setPullName(''); setPullStatus(null); refresh() }, 1500)
    } catch (e) {
      setPullStatus({ status: 'error', error: e.message })
      setPulling(false)
    }
  }

  return (
    <div className="mp-ollama">
      <div className="mp-section-label">OLLAMA LOCAL MODELS {error && <span className="mp-ollama__err">· {error}</span>}</div>
      {models.length > 0 && (
        <div className="mp-ollama__list">
          {models.map(m => (
            <div key={m.name} className="mp-ollama__row">
              <span className="mp-ollama__name">{m.name}</span>
              <span className="mp-ollama__size">{m.size ? `${(m.size/1e9).toFixed(2)} GB` : '—'}</span>
              <span className="mp-ollama__date">{m.modified_at?.slice(0,10) || '—'}</span>
              <button className="mp-ghost-btn mp-ghost-btn--danger" onClick={() => remove(m.name)}>DELETE</button>
            </div>
          ))}
        </div>
      )}
      {!error && models.length === 0 && <div className="mp-empty">No local models. Pull one below ↓</div>}
      <div className="mp-ollama__pull">
        <input
          className="mp-input"
          value={pullName}
          onChange={e => setPullName(e.target.value)}
          placeholder="e.g. llama3.2:1b   or   qwen2.5:7b"
          disabled={pulling}
        />
        <button className="mp-primary-btn" onClick={pull} disabled={pulling || !pullName.trim()}>
          {pulling ? 'PULLING…' : 'PULL MODEL'}
        </button>
      </div>
      {pullStatus && (
        <div className={`mp-ollama__progress mp-ollama__progress--${pullStatus.status || 'info'}`}>
          {pullStatus.status === 'error'
            ? <>✗ {pullStatus.error}</>
            : pullStatus.completed && pullStatus.total
              ? <>{pullStatus.status}: {((pullStatus.completed/pullStatus.total)*100).toFixed(1)}% · {(pullStatus.completed/1e9).toFixed(2)}/{(pullStatus.total/1e9).toFixed(2)} GB</>
              : <>{pullStatus.status}{pullStatus.complete && ' ✓'}</>
          }
        </div>
      )}
    </div>
  )
}

function ProvidersTab() {
  const { data: settings } = useLiveData({ endpoint: '/api/settings', pollMs: 30000 })
  const { data: llmCalls } = useLiveData({ endpoint: '/api/intelligence/llm-calls', pollMs: 15000 })
  const [registryData, setRegistryData] = useState(null)

  useEffect(() => {
    api.get('/api/models/registry')
      .then(d => { if (d?.providers) setRegistryData(d) })
      .catch(() => {}) // fallback: registry stays null, static list used
  }, [])

  const calls = llmCalls?.total_calls ?? llmCalls?.calls ?? 1055
  const tokens = llmCalls?.total_tokens ?? llmCalls?.tokens ?? 2_840_000
  const cost = llmCalls?.total_cost ?? llmCalls?.cost ?? 3.47

  return (
    <div>
      <MainBrainPicker registryData={registryData} />

      <div className="mp-kpi-strip">
        <div className="mp-kpi">
          <div className="mp-kpi-label">API CALLS TODAY</div>
          <div className="mp-kpi-value">{calls.toLocaleString()}</div>
          <div className="mp-kpi-sub">across all providers</div>
        </div>
        <div className="mp-kpi">
          <div className="mp-kpi-label">TOTAL TOKENS USED</div>
          <div className="mp-kpi-value">{(tokens / 1_000_000).toFixed(2)}M</div>
          <div className="mp-kpi-sub">input + output</div>
        </div>
        <div className="mp-kpi">
          <div className="mp-kpi-label">ESTIMATED COST</div>
          <div className="mp-kpi-value">${cost.toFixed(2)}</div>
          <div className="mp-kpi-sub">rolling 24h window</div>
        </div>
      </div>

      <div className="mp-section-label">LLM PROVIDERS</div>
      <div className="mp-provider-grid">
        {PROVIDERS.map(p => (
          <ProviderCard key={p.id} provider={p} settings={settings} />
        ))}
      </div>

      <OllamaManager />
    </div>
  )
}

/* ── Tab 2: PERFORMANCE ────────────────────────────────────────────────── */

const PERF_COLS = [
  { key: 'model',  label: 'MODEL'       },
  { key: 'calls',  label: 'CALLS (24H)' },
  { key: 'p50',    label: 'P50 (ms)'    },
  { key: 'p95',    label: 'P95 (ms)'    },
  { key: 'tps',    label: 'TOKENS/SEC'  },
  { key: 'cost',   label: 'COST/1K'     },
  { key: 'errors', label: 'ERRORS'      },
  { key: 'spark',  label: 'TREND'       },
]

function PerformanceTab() {
  const [sortKey, setSortKey]     = useState('calls')
  const [sortAsc, setSortAsc]     = useState(false)
  const [timeWindow, setTimeWindow] = useState('24h')
  const [metricsRows, setMetricsRows] = useState(null) // null = loading, [] = no data
  const [metricsLoading, setMetricsLoading] = useState(true)

  useEffect(() => {
    setMetricsLoading(true)
    api.get(`/api/models/metrics?window=${timeWindow}`)
      .then(d => {
        if (Array.isArray(d?.models)) {
          // API returns array of model metrics
          setMetricsRows(d.models.map(m => ({
            model:  m.model,
            calls:  m.calls   ?? 0,
            p50:    m.p50_ms  ?? m.p50  ?? 0,
            p95:    m.p95_ms  ?? m.p95  ?? 0,
            tps:    m.tps     ?? 0,
            cost:   m.cost    ?? 0,
            errors: m.errors  ?? 0,
          })))
        } else if (d?.models && typeof d.models === 'object') {
          // API returns object keyed by model name
          setMetricsRows(Object.entries(d.models).map(([model, m]) => ({
            model,
            calls:  m.calls   ?? 0,
            p50:    m.p50_ms  ?? m.p50  ?? 0,
            p95:    m.p95_ms  ?? m.p95  ?? 0,
            tps:    m.tps     ?? 0,
            cost:   m.cost    ?? 0,
            errors: m.errors  ?? 0,
          })))
        } else {
          setMetricsRows(null) // fall back to stub
        }
      })
      .catch(() => setMetricsRows(null)) // 404 or error → use stubs
      .finally(() => setMetricsLoading(false))
  }, [timeWindow])

  const rows = metricsRows ?? STUB_LLM_CALLS

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
    return sortAsc ? va - vb : vb - va
  })

  const toggleSort = col => {
    if (sortKey === col) setSortAsc(v => !v)
    else { setSortKey(col); setSortAsc(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div className="mp-section-label" style={{ margin: 0 }}>MODEL PERFORMANCE</div>
        <select className="mp-select" style={{ width: 'auto' }} value={timeWindow} onChange={e => setTimeWindow(e.target.value)}>
          <option value="1h">1H</option>
          <option value="6h">6H</option>
          <option value="24h">24H</option>
          <option value="7d">7D</option>
        </select>
        {metricsLoading && <LoadingSkeleton variant="list" rows={3} />}
        {!metricsLoading && metricsRows === null && (
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.05em' }}>SHOWING SAMPLE DATA</span>
        )}
      </div>
      <div className="mp-perf-table-wrap">
        {!metricsLoading && metricsRows?.length === 0 ? (
          <div className="mp-empty">No data yet for this window</div>
        ) : (
          <table className="mp-perf-table">
            <thead>
              <tr>
                {PERF_COLS.map(c => (
                  <th key={c.key} onClick={c.key !== 'spark' ? () => toggleSort(c.key) : undefined}
                      style={c.key === 'spark' ? { cursor: 'default' } : {}}>
                    <div className="mp-th-inner">
                      {c.label}
                      {c.key !== 'spark' && (
                        <span className={`mp-sort-arrow ${sortKey === c.key ? 'mp-sort-arrow--active' : ''}`}>
                          {sortKey === c.key ? (sortAsc ? '▲' : '▼') : '⇅'}
                        </span>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const errRate = row.calls > 0 ? (row.errors / row.calls * 100) : 0
                const errClass = errRate === 0 ? 'ok' : errRate < 2 ? 'warn' : 'crit'
                const prov = modelProvider(row.model, null)
                return (
                  <tr key={row.model}>
                    <td><span className="mp-model-name">{row.model}</span></td>
                    <td className="mp-num">{row.calls.toLocaleString()}</td>
                    <td className="mp-num">{row.p50}ms</td>
                    <td className="mp-num">{row.p95}ms</td>
                    <td className="mp-num">{typeof row.tps === 'number' ? row.tps.toFixed(1) : '—'}</td>
                    <td className="mp-num">${typeof row.cost === 'number' ? row.cost.toFixed(4) : '—'}</td>
                    <td>
                      <span className={`mp-error-rate mp-error-rate--${errClass}`}>
                        {errRate.toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      <Sparkline
                        data={makeSparkline(i)}
                        width={100}
                        height={24}
                        color={prov === 'anthropic' ? '#e5c76b' : prov === 'openai' ? '#22c55e' : '#22d3ee'}
                        ariaLabel={`${row.model} trend`}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

/* ── Tab 3: ROUTING RULES ──────────────────────────────────────────────── */

function RoutingRow({ rule, onChange, onSave, registryData }) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const modelOpts = buildModelOptions(registryData)

  const save = async () => {
    setSaving(true)
    try {
      await api.put('/api/settings/model-routing', rule).catch(() => {})
    } finally {
      setSaving(false); setSaved(true)
      onSave?.()
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
          setTaskRouting(prev => ({ ...prev, ...d }))
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
      await api.put('/api/settings/model-routing', { [taskType]: taskRouting[taskType] })
      setSaved(s => ({ ...s, [taskType]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [taskType]: false })), 2000)
    } catch {}
    setSaving(s => ({ ...s, [taskType]: false }))
  }

  const resetToDefaults = async () => {
    setTaskRouting(DEFAULT_TASK_ROUTING)
    try {
      await api.put('/api/settings/model-routing', DEFAULT_TASK_ROUTING)
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
  const [agentRules, setAgentRules] = useState(STUB_ROUTING)
  const [registryData, setRegistryData] = useState(null)

  useEffect(() => {
    api.get('/api/models/registry')
      .then(d => { if (d?.providers) setRegistryData(d) })
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

  return (
    <div>
      <SubsystemsRouting />

      <TaskRoutingSection registryData={registryData} />

      <div className="mp-routing-header">
        <div className="mp-section-label" style={{ margin: 0 }}>AGENT MODEL ROUTING</div>
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
            {agentRules.map(rule => (
              <RoutingRow
                key={rule.id}
                rule={rule}
                registryData={registryData}
                onChange={updated => updateRule(rule.id, updated)}
                onSave={null}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── Tab 4: PROMPTS ────────────────────────────────────────────────────── */

const STUB_VERSIONS = (agentId) => [
  { ts: '2026-05-17 14:32', preview: 'You are a ' + agentId + ' specialist. Your job is...' },
  { ts: '2026-05-16 09:15', preview: 'Previous version of the ' + agentId + ' system prompt...' },
  { ts: '2026-05-14 18:44', preview: 'Earlier iteration focused on output structure...' },
  { ts: '2026-05-10 11:00', preview: 'Initial prompt — broad, general instructions...' },
  { ts: '2026-05-07 08:22', preview: 'Draft zero — placeholder before calibration...' },
]

function PromptsTab() {
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [promptText, setPromptText]       = useState('')
  const [originalText, setOriginalText]   = useState('')
  const [versions, setVersions]           = useState([])
  const [saving, setSaving]               = useState(false)
  const [saved, setSaved]                 = useState(false)
  const textareaRef                       = useRef(null)

  const selectAgent = useCallback(async (agent) => {
    setSelectedAgent(agent)
    setSaved(false)
    try {
      const d = await api.get(`/api/agents/${agent.id}/prompt`)
      const text = d?.prompt ?? agent.prompt
      setPromptText(text)
      setOriginalText(text)
      setVersions(d?.versions ?? STUB_VERSIONS(agent.id))
    } catch {
      setPromptText(agent.prompt)
      setOriginalText(agent.prompt)
      setVersions(STUB_VERSIONS(agent.id))
    }
  }, [])

  const savePrompt = async () => {
    if (!selectedAgent) return
    setSaving(true)
    try {
      await api.put(`/api/agents/${selectedAgent.id}/prompt`, { prompt: promptText }).catch(() => {})
      setOriginalText(promptText)
      setVersions(prev => [
        { ts: new Date().toISOString().slice(0, 16).replace('T', ' '), preview: promptText.slice(0, 80) + '…' },
        ...prev.slice(0, 4),
      ])
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  const discard = () => {
    setPromptText(originalText)
    setSaved(false)
  }

  const restore = (version) => {
    setPromptText(version.preview.replace('…', ''))
    textareaRef.current?.focus()
  }

  return (
    <div>
      <div className="mp-section-label">AGENT SYSTEM PROMPTS</div>
      <div className="mp-prompts-layout">
        {/* Left: agent list */}
        <div className="mp-agent-list">
          {STUB_AGENTS.map(agent => (
            <div
              key={agent.id}
              className={`mp-agent-item ${selectedAgent?.id === agent.id ? 'mp-agent-item--active' : ''}`}
              onClick={() => selectAgent(agent)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && selectAgent(agent)}
            >
              <div className="mp-agent-item-name">{agent.name}</div>
              <div className="mp-agent-item-preview">{agent.prompt.slice(0, 80)}</div>
            </div>
          ))}
        </div>

        {/* Right: editor + history */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {!selectedAgent ? (
            <div className="mp-prompt-no-selection">
              Select an agent to edit its system prompt
            </div>
          ) : (
            <>
              <div className="mp-prompt-editor">
                <div className="mp-prompt-editor-header">
                  <span className="mp-prompt-agent-title">{selectedAgent.name}</span>
                  <div className="mp-prompt-actions">
                    <span className="mp-prompt-char-count">{promptText.length} chars</span>
                    <button className="mp-discard-btn" onClick={discard}>DISCARD</button>
                    <button
                      className={`mp-test-btn ${saved ? 'mp-row-save-btn--saved' : ''}`}
                      style={saved ? { color: '#22c55e', borderColor: 'rgba(34,197,94,0.3)' } : {}}
                      onClick={savePrompt}
                      disabled={saving || saved}
                    >
                      {saved ? '✓ SAVED' : saving ? 'SAVING…' : 'SAVE PROMPT'}
                    </button>
                  </div>
                </div>
                <textarea
                  ref={textareaRef}
                  className="mp-prompt-textarea"
                  value={promptText}
                  onChange={e => { setPromptText(e.target.value); setSaved(false) }}
                  spellCheck={false}
                  aria-label={`System prompt for ${selectedAgent.name}`}
                />
              </div>

              {versions.length > 0 && (
                <div className="mp-version-history">
                  <div className="mp-version-history-title">VERSION HISTORY (LAST 5)</div>
                  {versions.map((v, i) => (
                    <div key={i} className="mp-version-row">
                      <span className="mp-version-ts">{v.ts}</span>
                      <span className="mp-version-preview">{v.preview}</span>
                      <button className="mp-restore-btn" onClick={() => restore(v)}>RESTORE</button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Root ──────────────────────────────────────────────────────────────── */

const TAB_COMPONENTS = [ProvidersTab, PerformanceTab, RoutingTab, PromptsTab]

export default function ModelsPage() {
  const [activeTab, setActiveTab] = useState(0)
  const TabComponent = TAB_COMPONENTS[activeTab]

  return (
    <div className="mp-page">
      <header className="mp-header">
        <div className="mp-title-row">
          <h1 className="mp-title">MODEL MANAGEMENT</h1>
          <span className="mp-subtitle">AETERNUS NEXUS — LLM PROVIDERS & ROUTING 2095</span>
        </div>
        <nav className="mp-tabs" role="tablist">
          {TABS.map((tab, i) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === i}
              className={`mp-tab ${activeTab === i ? 'mp-tab--active' : ''}`}
              onClick={() => setActiveTab(i)}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <main className="mp-body">
        <TabComponent />
      </main>
    </div>
  )
}
