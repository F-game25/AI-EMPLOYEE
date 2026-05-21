import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import './ModelFabricPage.css'

/* Model Fabric — the 8 model architectures usable from one console.
   Talks to Node proxy /api/model-fabric/* → Python. No fake states: a subsystem
   reports offline/unavailable honestly and its test button shows the real error. */

const ARCH_META = {
  LLM: { label: 'LLM', blurb: 'General reasoning, coding, planning', test: 'llm' },
  SLM: { label: 'SLM', blurb: 'Fast classify / short answers',       test: 'slm' },
  MoE: { label: 'MoE', blurb: 'Mixture-of-experts router',           test: 'route' },
  VLM: { label: 'VLM', blurb: 'Vision — analyze images',             test: 'vision' },
  MLM: { label: 'MLM/RAG', blurb: 'Embeddings + memory retrieval',   test: 'rag' },
  SAM: { label: 'SAM', blurb: 'Segment / mask regions',              test: null },
  LAM: { label: 'LAM', blurb: 'Actions — run skills/tools',          test: 'action' },
  LCM: { label: 'LCM', blurb: 'Generate visuals / images',           test: null },
}
const ARCH_ORDER = ['LLM', 'SLM', 'MoE', 'VLM', 'MLM', 'LAM', 'LCM', 'SAM']

function StatusDot({ available }) {
  return <span className={`mf-dot ${available ? 'mf-dot--on' : 'mf-dot--off'}`} />
}

export default function ModelFabricPage() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState({})           // per-arch test in-flight
  const [results, setResults] = useState({})     // per-arch last test result

  const refresh = useCallback(async () => {
    try {
      setErr(null)
      const h = await api.get('/api/model-fabric/health')
      setHealth(h)
    } catch (e) {
      setErr(e.message || 'Model Fabric offline')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const i = setInterval(refresh, 15000)
    return () => clearInterval(i)
  }, [refresh])

  const subsystems = health?.subsystems || []
  const byArch = Object.fromEntries(subsystems.map(s => [s.arch, s]))

  const setResult = (arch, r) => setResults(p => ({ ...p, [arch]: r }))

  const testArch = useCallback(async (arch) => {
    const meta = ARCH_META[arch]
    if (!meta?.test) return
    setBusy(p => ({ ...p, [arch]: true }))
    const t0 = performance.now()
    try {
      let res
      if (meta.test === 'llm' || meta.test === 'slm') {
        res = await api.post(`/api/model-fabric/${meta.test}`, { prompt: 'Say hi in 3 words', max_tokens: 40 })
      } else if (meta.test === 'route') {
        res = await api.post('/api/model-fabric/route', { prompt: 'Summarize what you do in one sentence.', max_tokens: 60 })
      } else if (meta.test === 'rag') {
        res = await api.post('/api/model-fabric/rag/query', { query: 'system status', k: 3 })
      } else if (meta.test === 'action') {
        res = await api.post('/api/model-fabric/actions/execute', { skill: 'noop', args: {}, dry_run: true })
      } else if (meta.test === 'vision') {
        res = { status: 'info', output: 'Use the Vision panel below to upload an image.' }
      }
      const ms = Math.round(performance.now() - t0)
      setResult(arch, { ok: res?.status === 'success' || res?.status === 'dry_run' || res?.status === 'ok' || res?.status === 'info', ms, res })
    } catch (e) {
      setResult(arch, { ok: false, res: { status: 'error', error: e.message } })
    } finally {
      setBusy(p => ({ ...p, [arch]: false }))
    }
  }, [])

  return (
    <div className="mf-page">
      <header className="mf-head">
        <div>
          <h1>Model Fabric</h1>
          <p className="mf-sub">8 model architectures — hardware-resolved, local-first. No subsystem is faked: offline means offline.</p>
        </div>
        <div className="mf-head-stats">
          {health && (
            <>
              <span className="mf-chip">tier: <b>{health.tier || '—'}</b></span>
              <span className="mf-chip">{health.online}/{health.total} online</span>
            </>
          )}
          <button className="mf-btn" onClick={refresh}>↻ Refresh</button>
        </div>
      </header>

      {loading && <div className="mf-note">Loading subsystems…</div>}
      {err && <div className="mf-note mf-note--err">⚠ {err}</div>}

      {/* ── Subsystem cards ── */}
      <section className="mf-grid">
        {ARCH_ORDER.map(arch => {
          const meta = ARCH_META[arch]
          const s = byArch[arch] || {}
          const r = results[arch]
          return (
            <div key={arch} className={`mf-card ${s.available ? '' : 'mf-card--off'}`}>
              <div className="mf-card-top">
                <StatusDot available={s.available} />
                <span className="mf-card-title">{meta.label}</span>
                <span className={`mf-badge ${s.available ? 'mf-badge--on' : 'mf-badge--off'}`}>
                  {s.available ? 'online' : 'offline'}
                </span>
              </div>
              <p className="mf-card-blurb">{meta.blurb}</p>
              <div className="mf-card-meta">
                <div><span>model</span><b title={s.model || ''}>{s.model || '—'}</b></div>
                <div><span>provider</span><b>{s.provider || '—'}</b></div>
              </div>
              {!s.available && s.reason && <div className="mf-reason">{s.reason}</div>}
              <div className="mf-card-actions">
                <button
                  className="mf-btn mf-btn--sm"
                  disabled={!meta.test || !s.available || busy[arch]}
                  onClick={() => testArch(arch)}
                >
                  {busy[arch] ? 'Testing…' : meta.test ? 'Test' : 'No test'}
                </button>
                {r && (
                  <span className={`mf-test ${r.ok ? 'mf-test--ok' : 'mf-test--err'}`}>
                    {r.ok ? '✓' : '✗'} {r.ms ? `${r.ms}ms` : ''}
                  </span>
                )}
              </div>
              {r && (
                <pre className="mf-out">{
                  r.res?.output || r.res?.error || r.res?.note ||
                  (r.res?.results ? `${r.res.count ?? r.res.results.length} hit(s)` : JSON.stringify(r.res).slice(0, 200))
                }</pre>
              )}
            </div>
          )
        })}
      </section>

      <LifecyclePanel />
      <QuantPanel />
      <AutoRoutePanel />
      <RagPanel />
      <VisionPanel available={byArch.VLM?.available} />
      <ActionPanel available={byArch.LAM?.available} />
    </div>
  )
}

/* ── Model lifecycle: VRAM + loaded models + unload controls ── */
function LifecyclePanel() {
  const [lc, setLc] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setLc(await api.get('/api/model-fabric/lifecycle/status')) } catch { /* offline */ }
  }, [])
  useEffect(() => { load(); const i = setInterval(load, 8000); return () => clearInterval(i) }, [load])
  const unload = async (id) => {
    setBusy(true)
    try { await api.post(`/api/model-fabric/models/${encodeURIComponent(id)}/unload`, {}) } catch { /* noop */ }
    finally { setBusy(false); load() }
  }
  const unloadIdle = async () => {
    setBusy(true)
    try { await api.post('/api/model-fabric/models/unload-idle', {}) } catch { /* noop */ }
    finally { setBusy(false); load() }
  }
  const free = lc?.free_vram_mb, total = lc?.total_vram_mb
  const usedPct = free != null && total ? Math.round(((total - free) / total) * 100) : null
  return (
    <section className="mf-panel">
      <h2>Model Lifecycle <span className="mf-tag">VRAM</span></h2>
      <p className="mf-panel-sub">Heavy models load on demand; idle ones evict to free GPU. Only one heavy load at a time.</p>
      {total != null && (
        <div className="mf-vram">
          <div className="mf-vram-bar"><div className="mf-vram-fill" style={{ width: `${usedPct}%` }} /></div>
          <span className="mf-vram-label">{total - free} / {total} MB used · {free} MB free</span>
        </div>
      )}
      <div className="mf-row">
        <span className="mf-chip">{lc?.models_loaded ?? 0} loaded / {lc?.models_registered ?? 0} known</span>
        {lc?.heavy_load_busy && <span className="mf-chip">heavy load in progress…</span>}
        <button className="mf-btn mf-btn--sm" onClick={unloadIdle} disabled={busy}>Unload idle</button>
        <button className="mf-btn mf-btn--sm" onClick={load} disabled={busy}>↻</button>
      </div>
      <ul className="mf-hits">
        {(lc?.models || []).length === 0 && <li className="mf-empty">No models resident — all load on demand.</li>}
        {(lc?.models || []).map((m) => (
          <li key={m.model_id}>
            <div className="mf-row" style={{ margin: 0, justifyContent: 'space-between' }}>
              <div className="mf-hit-text">
                <StatusDot available={m.loaded} /> {m.model_id}
                <span className="mf-hit-meta"> {m.arch} · ~{m.est_vram_mb}MB{m.quant ? ` · ${m.quant}` : ''}{m.idle_s != null ? ` · idle ${Math.round(m.idle_s)}s` : ''}</span>
              </div>
              {m.loaded && <button className="mf-btn mf-btn--sm" onClick={() => unload(m.model_id)} disabled={busy}>Unload</button>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

/* ── Quantisation: active quant + selector + owner-gated optimal-quant pull ── */
function QuantPanel() {
  const [status, setStatus] = useState(null)
  const [avail, setAvail] = useState([])
  const [paramsB, setParamsB] = useState(7)
  const [devOverride, setDevOverride] = useState(false)
  const [sel, setSel] = useState(null)
  const [pullModel, setPullModel] = useState('')
  const [pull, setPull] = useState(null)
  const pollRef = useRef(null)
  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        api.get('/api/model-fabric/quantization/status'),
        api.get('/api/model-fabric/quantization/available'),
      ])
      setStatus(s); setAvail(a.quants || [])
    } catch { /* offline */ }
  }, [])
  // Default the pull target to the resolved LLM model (best-effort).
  useEffect(() => {
    api.get('/api/model-fabric/models')
      .then(r => { const m = r?.resolved?.LLM?.model; if (m) setPullModel(p => p || m) })
      .catch(() => {})
  }, [])
  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i) }, [load])
  useEffect(() => () => clearInterval(pollRef.current), [])
  const select = async () => {
    try { setSel(await api.post('/api/model-fabric/quantization/select', { params_b: Number(paramsB), dev_override: devOverride })) }
    catch (e) { setSel({ status: 'error', reason: e.message }) }
  }
  const pollPull = useCallback(() => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.get('/api/model-fabric/quantization/pull/status')
        setPull(s)
        if (!s.running) clearInterval(pollRef.current)
      } catch { clearInterval(pollRef.current) }
    }, 2000)
  }, [])
  const doPull = async () => {
    if (!pullModel.trim()) return
    try {
      const r = await api.post('/api/model-fabric/quantization/pull', { model: pullModel.trim() })
      setPull(r)
      if (r.status === 'started') pollPull()
    } catch (e) { setPull({ status: 'error', error: e.message }) }
  }
  return (
    <section className="mf-panel">
      <h2>Quantisation <span className="mf-tag">GPU-fit</span></h2>
      <p className="mf-panel-sub">{status?.policy || 'Every local load fits a quant tier to free VRAM. FP16/FP32 blocked unless dev-override.'}</p>
      {status && (
        <div className="mf-row">
          <span className="mf-chip">free: <b>{status.free_vram_mb} MB</b></span>
          <span className="mf-chip">7B → <b>{status.recommended_7b?.quant}</b> ({status.recommended_7b?.est_vram_mb}MB)</span>
        </div>
      )}
      <div className="mf-row">
        <label className="mf-q-size">Model size (B):
          <input type="number" min="0.5" max="180" step="0.5" value={paramsB} onChange={e => setParamsB(e.target.value)} />
        </label>
        <label className={`mf-toggle ${devOverride ? 'mf-toggle--hot' : ''}`}>
          <input type="checkbox" checked={devOverride} onChange={e => setDevOverride(e.target.checked)} />
          {devOverride ? '⚠ FP16 override' : 'Quant only'}
        </label>
        <button className="mf-btn" onClick={select}>Select quant</button>
      </div>
      {sel && (
        <div className="mf-panel-out">
          <span className="mf-chip">quant: <b>{sel.quant}</b></span>
          <span className="mf-chip">~{sel.est_vram_mb}MB</span>
          <span className="mf-chip">{sel.quality} / {sel.speed}</span>
          <span className={`mf-chip ${sel.fits ? '' : 'mf-toggle--hot'}`}>{sel.fits ? 'fits locally' : 'too big'}</span>
          {sel.recommend_remote && <span className="mf-chip mf-toggle--hot">→ remote compute</span>}
          <pre>{sel.reason}</pre>
        </div>
      )}
      <div className="mf-quants">
        {avail.map(q => (
          <span key={q.quant} className="mf-chip" title={`${q.quality} quality, ${q.speed}`}>{q.quant}</span>
        ))}
      </div>
      {/* Owner-gated: pull the optimal quant for this host. Local only, single-flight. */}
      <div className="mf-pull">
        <div className="mf-row">
          <input value={pullModel} onChange={e => setPullModel(e.target.value)} placeholder="model (e.g. qwen2.5:7b)" />
          <button className="mf-btn" onClick={doPull} disabled={pull?.running}>
            {pull?.running ? 'Pulling…' : 'Pull optimal quant'}
          </button>
        </div>
        {pull && (
          <div className="mf-panel-out">
            <span className={`mf-chip ${pull.running ? 'mf-pull--run' : pull.ok === false ? 'mf-toggle--hot' : ''}`}>
              {pull.running ? 'running' : pull.status === 'busy' ? 'busy' : pull.ok === false ? 'failed' : pull.ok ? 'done' : pull.status}
            </span>
            {pull.tag && <span className="mf-chip">{pull.tag}</span>}
            {pull.quant && <span className="mf-chip">quant: <b>{pull.quant}</b></span>}
            {(pull.error || pull.reason || pull.output) && (
              <pre>{pull.error || pull.reason || pull.output}</pre>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

/* ── Auto-route console (MoE) ── */
function AutoRoutePanel() {
  const [prompt, setPrompt] = useState('Analyze this screenshot of a dashboard')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true); setOut(null)
    try { setOut(await api.post('/api/model-fabric/route', { prompt, max_tokens: 200 })) }
    catch (e) { setOut({ status: 'error', error: e.message }) }
    finally { setBusy(false) }
  }
  return (
    <section className="mf-panel">
      <h2>Auto-Route Console <span className="mf-tag">MoE</span></h2>
      <p className="mf-panel-sub">Classifies intent → picks the right architecture → dispatches.</p>
      <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={2} />
      <button className="mf-btn" onClick={run} disabled={busy}>{busy ? 'Routing…' : 'Route'}</button>
      {out && (
        <div className="mf-panel-out">
          {out.routed_arch && <span className="mf-chip">→ {out.routed_arch}{out.auto_routed ? ' (auto)' : ''}</span>}
          {out.model && <span className="mf-chip">{out.model}</span>}
          <pre>{out.output || out.error || JSON.stringify(out, null, 2)}</pre>
        </div>
      )}
    </section>
  )
}

/* ── RAG search + ingest ── */
function RagPanel() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState(null)
  const [ingest, setIngest] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const search = async () => {
    if (!query.trim()) return
    setBusy(true); setHits(null)
    try { const r = await api.post('/api/model-fabric/rag/query', { query, k: 5 }); setHits(r.results || []) }
    catch (e) { setMsg(e.message) }
    finally { setBusy(false) }
  }
  const doIngest = async () => {
    if (!ingest.trim()) return
    setBusy(true); setMsg(null)
    try { const r = await api.post('/api/model-fabric/rag/ingest', { text: ingest }); setMsg(`Ingested ${r.chars ?? ''} chars`); setIngest('') }
    catch (e) { setMsg(e.message) }
    finally { setBusy(false) }
  }
  return (
    <section className="mf-panel">
      <h2>Hybrid RAG <span className="mf-tag">MLM</span></h2>
      <div className="mf-row">
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search memory…" onKeyDown={e => e.key === 'Enter' && search()} />
        <button className="mf-btn" onClick={search} disabled={busy}>Search</button>
      </div>
      {hits && (
        <ul className="mf-hits">
          {hits.length === 0 && <li className="mf-empty">No results.</li>}
          {hits.map((h, i) => (
            <li key={i}>
              <div className="mf-hit-text">{h.text || '(empty)'}</div>
              <div className="mf-hit-meta">{h.source}{h.score != null ? ` · ${Number(h.score).toFixed(3)}` : ''}{h.citation ? ` · ${h.citation}` : ''}</div>
            </li>
          ))}
        </ul>
      )}
      <div className="mf-row mf-row--ingest">
        <input value={ingest} onChange={e => setIngest(e.target.value)} placeholder="Ingest text into memory…" />
        <button className="mf-btn" onClick={doIngest} disabled={busy}>Ingest</button>
      </div>
      {msg && <div className="mf-note">{msg}</div>}
    </section>
  )
}

/* ── Vision analyze ── */
function VisionPanel({ available }) {
  const [prompt, setPrompt] = useState('What do you see in this image?')
  const [b64, setB64] = useState(null)
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const onFile = (e) => {
    const f = e.target.files?.[0]; if (!f) return
    const reader = new FileReader()
    reader.onload = () => setB64(String(reader.result))
    reader.readAsDataURL(f)
  }
  const analyze = async () => {
    if (!b64) return
    setBusy(true); setOut(null)
    try { setOut(await api.post('/api/model-fabric/vision/analyze', { prompt, images: [b64], max_tokens: 300 })) }
    catch (e) { setOut({ status: 'error', error: e.message }) }
    finally { setBusy(false) }
  }
  return (
    <section className="mf-panel">
      <h2>Vision <span className="mf-tag">VLM</span> {!available && <span className="mf-badge mf-badge--off">offline</span>}</h2>
      <div className="mf-row">
        <input ref={fileRef} type="file" accept="image/*" onChange={onFile} />
        <button className="mf-btn" onClick={analyze} disabled={busy || !b64 || !available}>{busy ? 'Analyzing…' : 'Analyze'}</button>
      </div>
      <input className="mf-full" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Vision prompt" />
      {b64 && <img className="mf-preview" src={b64} alt="preview" />}
      {out && <pre className="mf-out">{out.output || out.error || JSON.stringify(out, null, 2)}</pre>}
    </section>
  )
}

/* ── Action runner (LAM) — dry-run by default ── */
function ActionPanel({ available }) {
  const [skill, setSkill] = useState('')
  const [argsStr, setArgsStr] = useState('{}')
  const [dryRun, setDryRun] = useState(true)
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!skill.trim()) return
    let args = {}
    try { args = JSON.parse(argsStr || '{}') } catch { setOut({ status: 'error', error: 'args is not valid JSON' }); return }
    setBusy(true); setOut(null)
    try { setOut(await api.post('/api/model-fabric/actions/execute', { skill, args, dry_run: dryRun })) }
    catch (e) { setOut({ status: 'error', error: e.message }) }
    finally { setBusy(false) }
  }
  return (
    <section className="mf-panel">
      <h2>Action Runner <span className="mf-tag">LAM</span> {!available && <span className="mf-badge mf-badge--off">offline</span>}</h2>
      <p className="mf-panel-sub">Dry-run is on by default — no side effects unless you turn it off.</p>
      <div className="mf-row">
        <input value={skill} onChange={e => setSkill(e.target.value)} placeholder="skill / tool name" />
        <label className={`mf-toggle ${dryRun ? '' : 'mf-toggle--hot'}`}>
          <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
          {dryRun ? 'Dry-run' : '⚠ LIVE'}
        </label>
        <button className="mf-btn" onClick={run} disabled={busy}>{busy ? 'Running…' : 'Execute'}</button>
      </div>
      <input className="mf-full" value={argsStr} onChange={e => setArgsStr(e.target.value)} placeholder='args JSON e.g. {"x":1}' />
      {out && <pre className="mf-out">{out.note || out.output || out.error || JSON.stringify(out, null, 2)}</pre>}
    </section>
  )
}
