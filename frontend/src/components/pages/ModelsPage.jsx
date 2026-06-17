import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import { useLiveData } from '../../hooks/useLiveData'
import { useSystemStore } from '../../store/systemStore'
import { Sparkline, EmptyState } from '../nexus-ui'
import LoadingSkeleton from '../nexus-ui/LoadingSkeleton'
import './ModelsPage.css'
import { buildModelOptions, modelProvider, FALLBACK_MODEL_OPTIONS } from './models/shared'
import RoutingTab from './models/RoutingTab'
import PromptsTab from './models/PromptsTab'

/* ── Constants ─────────────────────────────────────────────────────────── */

const TABS = ['PROVIDERS', 'PERFORMANCE', 'ROUTING RULES', 'PROMPTS', 'ORCHESTRATION']

// Fallback model list used until registry loads

// Derive a flat MODEL_OPTIONS list from registry data, or fall back to static list




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
  { id: 'anthropic',      name: 'Anthropic',       defaultModel: 'claude-sonnet-4-6',              keyPrefix: 'sk-ant-',   capabilityId: 'anthropic_llm',      color: '#d4a96a' },
  { id: 'openrouter',     name: 'OpenRouter',      defaultModel: 'openai/gpt-4o',                  keyPrefix: 'sk-or-',    capabilityId: 'openrouter_llm',     color: '#6366f1' },
  { id: 'ollama',         name: 'Ollama (Local)',   defaultModel: 'llama3.3',                       keyPrefix: 'http://',   capabilityId: 'ollama_local_model',  color: '#22c55e' },
  { id: 'nvidia_nim',     name: 'NVIDIA NIM',      defaultModel: 'meta/llama-3.3-70b-instruct',    keyPrefix: 'nvapi-',    capabilityId: 'nvidia_nim_llm',     color: '#76b900' },
  { id: 'remote_compute', name: 'Remote Compute',  defaultModel: 'llama3.3',                       keyPrefix: 'http://',   capabilityId: 'remote_compute_llm', color: '#06b6d4' },
]

function capabilityForProvider(provider, capabilitiesById) {
  return capabilitiesById[provider.capabilityId] || {
    id: provider.capabilityId,
    label: provider.name,
    status: 'not_configured',
    missing_env: provider.id === 'ollama' ? ['OLLAMA_HOST'] : [`${provider.id.toUpperCase()}_API_KEY`],
    details: 'Provider capability has not been reported by the backend yet.',
    proof: null,
  }
}

function providerBadgeStatus(status) {
  if (status === 'live') return 'connected'
  if (['dry_run', 'fallback', 'mock'].includes(status)) return 'degraded'
  if (status === 'error') return 'error'
  return 'unconfigured'
}

function ProviderCard({ provider, settings, capability, onRefreshCapabilities }) {
  const [testing, setTesting]     = useState(false)
  const [testResult, setTestResult] = useState(null)

  const configured = capability?.status === 'live'
  const model      = settings?.[provider.id + '_model']      ?? provider.defaultModel
  const status     = providerBadgeStatus(capability?.status)

  const test = async () => {
    setTesting(true); setTestResult(null)
    const capabilities = await onRefreshCapabilities().catch(() => [])
    const fresh = capabilities.find(c => c.id === provider.capabilityId) || capability
    setTestResult({
      ok: fresh?.status === 'live',
      msg: fresh?.status === 'live' ? 'Live' : (fresh?.details || 'Not configured'),
      status: fresh?.status || 'not_configured',
      checked_at: fresh?.last_checked_at || fresh?.updated_at || new Date().toISOString(),
    })
    setTesting(false)
  }

  return (
    <div className={`mp-provider-card ${configured ? 'mp-provider-card--connected' : ''}`}>
      <div className="mp-provider-header">
        <span className="mp-provider-name">{provider.name}</span>
        <span className={`mp-status-badge mp-status-badge--${status}`}>
          {capability?.status === 'live' ? 'LIVE' : (capability?.status || 'NOT CONFIGURED').replaceAll('_', ' ').toUpperCase()}
        </span>
      </div>
      <div className="mp-provider-model">{model}</div>
      <div className="mp-provider-key">
        {configured
          ? `${provider.keyPrefix}${'●'.repeat(16)}`
          : capability?.details || 'API key not set — configure in Settings > LLM'}
      </div>
      {capability?.missing_env?.length > 0 && (
        <div className="mp-provider-proof mp-provider-proof--warn">Missing env: {capability.missing_env.join(', ')}</div>
      )}
      {capability?.proof && (
        <div className="mp-provider-proof">Proof: {JSON.stringify(capability.proof).slice(0, 140)}</div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button className="mp-test-btn" onClick={test} disabled={testing}>
          {testing ? 'TESTING…' : 'TEST CONNECTION'}
        </button>
        {testResult && (
          <span className={`mp-test-result mp-test-result--${testResult.ok ? 'ok' : 'fail'}`}>
            {testResult.ok ? '✓ ' : '✗ '}{testResult.status}: {testResult.msg}
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
    : ['anthropic', 'openrouter', 'ollama', 'nvidia_nim', 'remote_compute']

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

/* ── VRAM Gauge ─────────────────────────────────────────────────────────── */

// totalMb comes from the live hardware snapshot (nvidia-smi memory.total). No
// hardcoded card size — when it's unknown we honestly show used-only, no %.
function VramGauge({ runningModels, totalMb }) {
  const usedMb = runningModels.reduce((s, m) => s + (m.size_vram || 0) / 1e6, 0)
  const total = totalMb && totalMb > 0 ? totalMb : null
  const pct = total ? Math.min(100, (usedMb / total) * 100) : 0
  const color = pct > 85 ? '#ef4444' : pct > 65 ? '#f59e0b' : '#22c55e'
  return (
    <div className="mp-vram-gauge">
      <div className="mp-vram-gauge__label">
        <span>VRAM</span>
        <span style={{ color }}>
          {total
            ? `${usedMb.toFixed(0)} / ${total.toFixed(0)} MB (${pct.toFixed(0)}%)`
            : `${usedMb.toFixed(0)} MB used · total unknown`}
        </span>
      </div>
      {total && (
        <div className="mp-vram-gauge__bar">
          <div className="mp-vram-gauge__fill" style={{ width: `${pct}%`, background: color }} />
          {runningModels.map((m, i) => {
            const mbThis = (m.size_vram || 0) / 1e6
            const pctThis = (mbThis / total) * 100
            const pctStart = runningModels.slice(0, i).reduce((s, r) => s + (r.size_vram || 0) / 1e6, 0) / total * 100
            return (
              <div key={m.name} className="mp-vram-gauge__segment-label" style={{ left: `${pctStart + pctThis / 2}%` }}>
                {m.name?.split(':')[0]}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ── Ollama Local Models Manager ────────────────────────────────────────── */

function OllamaManager() {
  const [models, setModels]       = useState([])
  const [running, setRunning]     = useState([])
  const [error, setError]         = useState(null)
  const [pullName, setPullName]   = useState('')
  const [pulling, setPulling]     = useState(false)
  const [pullStatus, setPullStatus] = useState(null)
  const [loadingModel, setLoadingModel] = useState(null)
  const [vramTotalMb, setVramTotalMb] = useState(null)  // live, from nvidia-smi via backend

  const refresh = useCallback(() => {
    api.get('/api/ollama/models')
      .then(d => { setModels(d.models || []); setError(null) })
      .catch(e => { setError(e.message || 'ollama unavailable'); setModels([]) })
  }, [])

  useEffect(() => {
    api.get('/api/system/resources')
      .then(d => { if (d?.vram_total_mb) setVramTotalMb(d.vram_total_mb) })
      .catch(() => {})
  }, [])

  const refreshRunning = useCallback(() => {
    api.get('/api/ollama/ps')
      .then(d => setRunning(d.models || []))
      .catch(() => setRunning([]))
  }, [])

  useEffect(() => { refresh(); refreshRunning() }, [refresh, refreshRunning])

  // Poll running models every 5s
  useEffect(() => {
    const id = setInterval(refreshRunning, 5000)
    return () => clearInterval(id)
  }, [refreshRunning])

  const remove = async (name) => {
    if (!confirm(`Delete model ${name}?`)) return
    try { await api.delete(`/api/ollama/models/${encodeURIComponent(name)}`) } catch {}
    refresh()
  }

  const load = async (name) => {
    setLoadingModel(name)
    try { await api.post('/api/ollama/load', { name, keep_alive: -1 }) } catch {}
    setLoadingModel(null); refreshRunning()
  }

  const evict = async (name) => {
    setLoadingModel(name)
    try { await api.post('/api/ollama/evict', { name }) } catch {}
    setLoadingModel(null); refreshRunning()
  }

  const pull = async () => {
    if (!pullName.trim()) return
    setPulling(true); setPullStatus({ status: 'starting' })
    try {
      const jwt = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || ''
      const res = await fetch('/api/ollama/pull', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'authorization': `Bearer ${jwt}` },
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
          const line = e.trim()
          if (line.startsWith('data: ')) {
            try { setPullStatus(JSON.parse(line.slice(6))) } catch {}
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

  const runningNames = new Set(running.map(r => r.name))

  return (
    <div className="mp-ollama">
      {/* VRAM gauge — always show when Ollama is reachable */}
      {!error && <VramGauge runningModels={running} totalMb={vramTotalMb} />}

      {/* Currently loaded in VRAM */}
      {running.length > 0 && (
        <>
          <div className="mp-section-label mp-section-label--sub">LOADED IN VRAM</div>
          <div className="mp-ollama__list mp-ollama__list--running">
            {running.map(m => (
              <div key={m.name} className="mp-ollama__row mp-ollama__row--running">
                <span className="mp-vram-dot" />
                <span className="mp-ollama__name">{m.name}</span>
                <span className="mp-ollama__size">{m.size_vram ? `${(m.size_vram/1e9).toFixed(2)} GB VRAM` : '—'}</span>
                <span className="mp-ollama__expires">{m.expires_at ? `expires ${new Date(m.expires_at).toLocaleTimeString()}` : 'permanent'}</span>
                <button
                  className="mp-ghost-btn mp-ghost-btn--warn"
                  onClick={() => evict(m.name)}
                  disabled={loadingModel === m.name}
                >{loadingModel === m.name ? '…' : 'EVICT'}</button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* All installed models */}
      <div className="mp-section-label mp-section-label--sub">
        INSTALLED MODELS {error && <span className="mp-ollama__err">· {error}</span>}
      </div>
      {models.length > 0 && (
        <div className="mp-ollama__list">
          {models.map(m => {
            const isLoaded = runningNames.has(m.name)
            return (
              <div key={m.name} className={`mp-ollama__row ${isLoaded ? 'mp-ollama__row--active' : ''}`}>
                <span className="mp-ollama__name">{m.name}</span>
                <span className="mp-ollama__size">{m.size ? `${(m.size/1e9).toFixed(2)} GB` : '—'}</span>
                <span className="mp-ollama__date">{m.modified_at?.slice(0,10) || '—'}</span>
                {isLoaded
                  ? <span className="mp-badge mp-badge--green">IN VRAM</span>
                  : <button className="mp-ghost-btn mp-ghost-btn--green" onClick={() => load(m.name)} disabled={loadingModel === m.name}>
                      {loadingModel === m.name ? '…' : 'LOAD'}
                    </button>
                }
                <button className="mp-ghost-btn mp-ghost-btn--danger" onClick={() => remove(m.name)}>DELETE</button>
              </div>
            )
          })}
        </div>
      )}
      {!error && models.length === 0 && (
        <EmptyState title="No models configured" sub="Pull a model below to get started with local inference" />
      )}
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
  const capabilityStatus = useSystemStore(s => s.capabilityStatus)
  const fetchCapabilityStatus = useSystemStore(s => s.fetchCapabilityStatus)
  const [registryData, setRegistryData] = useState(null)

  useEffect(() => {
    api.get('/api/models/registry')
      .then(d => { if (d?.providers) setRegistryData(d) })
      .catch(() => {}) // fallback: registry stays null, static list used
    fetchCapabilityStatus().catch(() => {})
  }, [])

  const capabilitiesById = Object.fromEntries((capabilityStatus?.capabilities || []).map(c => [c.id, c]))
  const routingCapability = capabilitiesById.llm_provider_routing
  const calls = llmCalls?.total_calls ?? llmCalls?.calls ?? null
  const tokens = llmCalls?.total_tokens ?? llmCalls?.tokens ?? null
  const cost = llmCalls?.total_cost ?? llmCalls?.cost ?? null

  return (
    <div>
      <MainBrainPicker registryData={registryData} />

      <div className={`mp-ops-banner mp-ops-banner--${routingCapability?.status || 'not_configured'}`}>
        <strong>Routing status:</strong> {(routingCapability?.status || 'not_configured').replaceAll('_', ' ')}
        <span>{routingCapability?.details || 'No model routing capability proof has been reported yet.'}</span>
      </div>

      <div className="mp-kpi-strip">
        <div className="mp-kpi">
          <div className="mp-kpi-label">API CALLS TODAY</div>
          <div className="mp-kpi-value">{calls == null ? '—' : calls.toLocaleString()}</div>
          <div className="mp-kpi-sub">{calls == null ? 'live telemetry unavailable' : 'across all providers'}</div>
        </div>
        <div className="mp-kpi">
          <div className="mp-kpi-label">TOTAL TOKENS USED</div>
          <div className="mp-kpi-value">{tokens == null ? '—' : `${(tokens / 1_000_000).toFixed(2)}M`}</div>
          <div className="mp-kpi-sub">{tokens == null ? 'live telemetry unavailable' : 'input + output'}</div>
        </div>
        <div className="mp-kpi">
          <div className="mp-kpi-label">ESTIMATED COST</div>
          <div className="mp-kpi-value">{cost == null ? '—' : `$${cost.toFixed(2)}`}</div>
          <div className="mp-kpi-sub">{cost == null ? 'live telemetry unavailable' : 'rolling 24h window'}</div>
        </div>
      </div>

      <div className="mp-section-label">LLM PROVIDERS</div>
      <div className="mp-provider-grid">
        {PROVIDERS.map(p => (
          <ProviderCard
            key={p.id}
            provider={p}
            settings={settings}
            capability={capabilityForProvider(p, capabilitiesById)}
            onRefreshCapabilities={fetchCapabilityStatus}
          />
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
  const [metricsSource, setMetricsSource] = useState('loading')

  useEffect(() => {
    setMetricsLoading(true)
    setMetricsSource('loading')
    api.get(`/api/models/metrics?window=${timeWindow}`)
      .then(d => {
        const rawRows = Array.isArray(d?.metrics) ? d.metrics : Array.isArray(d?.models) ? d.models : null
        if (rawRows) {
          // API returns array of model metrics
          setMetricsRows(rawRows.map(m => ({
            model:  m.model,
            calls:  m.calls   ?? 0,
            p50:    m.p50_ms  ?? m.p50  ?? 0,
            p95:    m.p95_ms  ?? m.p95  ?? 0,
            tps:    m.tps     ?? 0,
            cost:   m.cost    ?? 0,
            errors: m.errors  ?? 0,
          })))
          setMetricsSource('live')
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
          setMetricsSource('live')
        } else {
          setMetricsRows([])
          setMetricsSource('unavailable')
        }
      })
      .catch(() => {
        setMetricsRows([])
        setMetricsSource('unavailable')
      })
      .finally(() => setMetricsLoading(false))
  }, [timeWindow])

  const rows = metricsRows ?? []

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
        {!metricsLoading && metricsSource !== 'live' && (
          <span className="mp-source-label mp-source-label--warn">LIVE METRICS UNAVAILABLE</span>
        )}
      </div>
      {!metricsLoading && metricsSource !== 'live' && (
        <div className="mp-ops-banner mp-ops-banner--unavailable">
          No model performance records were returned by `/api/models/metrics`. The table stays empty instead of showing sample telemetry.
        </div>
      )}
      <div className="mp-perf-table-wrap">
        {!metricsLoading && metricsRows?.length === 0 ? (
          <EmptyState title="No models configured" sub="Add a model in Settings to get started" />
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


/* ── Tab 4: PROMPTS ────────────────────────────────────────────────────── */


/* ── Tab 5: ORCHESTRATION (live role→model@quant, gauges, benchmarks) ───── */

// Stream an `ollama pull` over SSE (reuses POST /api/ollama/pull). onStatus gets
// each parsed event; resolves when the stream ends.
async function streamPull(name, onStatus) {
  const jwt = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || ''
  const res = await fetch('/api/ollama/pull', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'authorization': `Bearer ${jwt}` },
    body: JSON.stringify({ name }),
  })
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const events = buf.split('\n\n'); buf = events.pop()
    for (const e of events) {
      const line = e.trim()
      if (line.startsWith('data: ')) { try { onStatus(JSON.parse(line.slice(6))) } catch {} }
    }
  }
}

function Gauge({ label, usedMb, totalMb, unit = 'MB' }) {
  const total = totalMb && totalMb > 0 ? totalMb : null
  const pct = total ? Math.min(100, (usedMb / total) * 100) : 0
  const color = pct > 85 ? '#ef4444' : pct > 65 ? '#f59e0b' : '#22c55e'
  return (
    <div className="mp-gauge">
      <div className="mp-gauge__label">
        <span>{label}</span>
        <span style={{ color }}>
          {total ? `${usedMb.toFixed(0)} / ${total.toFixed(0)} ${unit} (${pct.toFixed(0)}%)` : 'unavailable'}
        </span>
      </div>
      <div className="mp-gauge__bar">
        {total && <div className="mp-gauge__fill" style={{ width: `${pct}%`, background: color }} />}
      </div>
    </div>
  )
}

function RoleRow({ role, r, benchByModel, onPull, pullState }) {
  const avail = r?.available
  const fits = r?.fits
  const model = r?.model
  const quant = r?.quant
  const bench = model ? benchByModel[model] : null
  const ps = model ? pullState[model] : null
  const installState = avail ? (fits ? 'fits' : 'offload') : 'missing'
  const stateLabel = { fits: 'FITS', offload: 'OFFLOAD', missing: 'NOT INSTALLED' }[installState]
  const suggestion = r?.install_suggestion || (r?.preferred_models && r.preferred_models[0])
  const pullTarget = model || suggestion
  return (
    <tr className={`mp-role-row mp-role-row--${installState}`}>
      <td className="mp-role-name">{role}</td>
      <td>{model ? <ModelBadge model={model} /> : <span className="mp-muted">—</span>}</td>
      <td className="mp-num">{quant || '—'}</td>
      <td><span className={`mp-badge mp-badge--${avail ? (fits ? 'green' : 'warn') : 'danger'}`}>{stateLabel}</span></td>
      <td className="mp-num">{r?.vram_needed != null ? `${r.vram_needed} MB` : '—'}</td>
      <td className="mp-num">{r?.offload_layers ? `${r.offload_layers} layers` : (fits ? 'all GPU' : '—')}</td>
      <td className="mp-num">{bench?.tokens_per_s != null ? `${bench.tokens_per_s.toFixed(1)} tok/s` : '—'}</td>
      <td className="mp-role-min">{r?.min_quant || '—'}</td>
      <td>
        {avail ? (
          <span className="mp-muted mp-role-reason" title={r?.reason}>{r?.reason}</span>
        ) : pullTarget ? (
          <button className="mp-ghost-btn mp-ghost-btn--green" onClick={() => onPull(pullTarget)} disabled={ps?.pulling}>
            {ps?.pulling
              ? (ps.status?.completed && ps.status?.total
                  ? `${((ps.status.completed / ps.status.total) * 100).toFixed(0)}%`
                  : (ps.status?.status || 'PULLING…'))
              : `PULL ${pullTarget.split(':')[0]}`}
          </button>
        ) : <span className="mp-muted">no candidate</span>}
      </td>
    </tr>
  )
}

function OrchestrationTab() {
  const [roles, setRoles] = useState(null)       // null=loading, {}=error
  const [rolesErr, setRolesErr] = useState(null)
  const [bench, setBench] = useState(null)
  const [benchErr, setBenchErr] = useState(null)
  const [pullState, setPullState] = useState({})  // model → { pulling, status }

  const loadRoles = useCallback(() => {
    api.get('/api/models/roles')
      .then(d => {
        if (d?.ok && d.roles) { setRoles(d); setRolesErr(null) }
        else { setRoles({}); setRolesErr(d?.error || 'role resolution unavailable') }
      })
      .catch(e => { setRoles({}); setRolesErr(e.body?.error || e.message || 'backend unreachable') })
  }, [])

  const loadBench = useCallback(() => {
    api.get('/api/models/benchmarks')
      .then(d => { if (d?.ok) { setBench(d); setBenchErr(null) } else { setBench({}); setBenchErr(d?.error || 'no benchmarks') } })
      .catch(e => { setBench({}); setBenchErr(e.body?.error || e.message || 'no benchmarks') })
  }, [])

  useEffect(() => { loadRoles(); loadBench() }, [loadRoles, loadBench])
  // Poll live resolution (VRAM fit changes as models load/evict).
  useEffect(() => { const id = setInterval(loadRoles, 8000); return () => clearInterval(id) }, [loadRoles])

  const onPull = useCallback(async (model) => {
    setPullState(s => ({ ...s, [model]: { pulling: true, status: { status: 'starting' } } }))
    try {
      await streamPull(model, st => setPullState(s => ({ ...s, [model]: { pulling: true, status: st } })))
      setPullState(s => ({ ...s, [model]: { pulling: false, status: { status: 'complete' } } }))
      loadRoles()
    } catch (e) {
      setPullState(s => ({ ...s, [model]: { pulling: false, status: { status: 'error', error: e.message } } }))
    }
  }, [loadRoles])

  const hw = roles?.hardware || {}
  const loaded = Array.isArray(hw.ollama_loaded) ? hw.ollama_loaded : []
  const usedVram = loaded.reduce((s, m) => s + (m.vram_mb || 0), 0)
  const benchByModel = Object.fromEntries((bench?.results || []).map(r => [r.model, r]))

  if (roles === null) return <LoadingSkeleton variant="list" rows={5} />

  return (
    <div className="mp-orch">
      {/* Live hardware gauges */}
      <div className="mp-section-label">LIVE HARDWARE</div>
      {hw.vram_total_mb || hw.ram_available_mb ? (
        <div className="mp-gauge-grid">
          <Gauge label="VRAM IN USE" usedMb={usedVram} totalMb={hw.vram_total_mb} />
          <div className="mp-gauge">
            <div className="mp-gauge__label">
              <span>VRAM FREE</span>
              <span>{hw.vram_free_mb != null ? `${hw.vram_free_mb} MB` : 'unavailable'}</span>
            </div>
          </div>
          <div className="mp-gauge">
            <div className="mp-gauge__label">
              <span>RAM AVAILABLE</span>
              <span>{hw.ram_available_mb != null ? `${(hw.ram_available_mb / 1024).toFixed(1)} GB` : 'unavailable'}</span>
            </div>
          </div>
          <div className="mp-gauge">
            <div className="mp-gauge__label">
              <span>CPU THREADS</span>
              <span>{hw.cpu_threads ?? '—'}</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="mp-ops-banner mp-ops-banner--unavailable">
          No GPU/RAM probe returned (nvidia-smi / psutil unavailable). Gauges stay empty rather than show fabricated values.
        </div>
      )}

      {/* Loaded-now with CPU/GPU split */}
      <div className="mp-section-label mp-section-label--sub">LOADED NOW (CPU / GPU SPLIT)</div>
      {loaded.length > 0 ? (
        <div className="mp-ollama__list mp-ollama__list--running">
          {loaded.map(m => (
            <div key={m.name} className="mp-ollama__row mp-ollama__row--running">
              <span className="mp-vram-dot" />
              <span className="mp-ollama__name">{m.name}</span>
              <span className="mp-ollama__size">{m.gpu_fraction != null ? `${(m.gpu_fraction * 100).toFixed(0)}% GPU` : '—'}</span>
              <span className="mp-ollama__size">{m.vram_mb} MB VRAM</span>
              <span className="mp-ollama__size">{m.cpu_mb} MB CPU</span>
              {benchByModel[m.name]?.tokens_per_s != null && (
                <span className="mp-ollama__size">{benchByModel[m.name].tokens_per_s.toFixed(1)} tok/s</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="mp-muted" style={{ padding: '4px 0' }}>
          {hw.ollama_loaded == null ? 'Ollama unreachable — no live load data.' : 'No models currently resident in VRAM.'}
        </div>
      )}

      {/* Role → model@quant resolution */}
      <div className="mp-section-label mp-section-label--sub">
        ROLE → MODEL@QUANT {rolesErr && <span className="mp-ollama__err">· {rolesErr}</span>}
        {benchErr && <span className="mp-ollama__err">· benchmarks: {benchErr}</span>}
      </div>
      {roles?.roles && Object.keys(roles.roles).length > 0 ? (
        <div className="mp-perf-table-wrap">
          <table className="mp-perf-table mp-role-table">
            <thead>
              <tr>
                <th>ROLE</th><th>MODEL</th><th>QUANT</th><th>STATE</th>
                <th>VRAM NEED</th><th>OFFLOAD</th><th>TOK/S</th><th>MIN QUANT</th><th>ACTION / REASON</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(roles.roles).map(([role, r]) => (
                <RoleRow key={role} role={role} r={r} benchByModel={benchByModel}
                  onPull={onPull} pullState={pullState} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No role resolution"
          sub={rolesErr ? `Backend: ${rolesErr}` : 'No roles configured in model_roles.json'} />
      )}
    </div>
  )
}


/* ── Root ──────────────────────────────────────────────────────────────── */

const TAB_COMPONENTS = [ProvidersTab, PerformanceTab, RoutingTab, PromptsTab, OrchestrationTab]

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
