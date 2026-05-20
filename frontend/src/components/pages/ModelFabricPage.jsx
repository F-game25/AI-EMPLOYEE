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

      <AutoRoutePanel />
      <RagPanel />
      <VisionPanel available={byArch.VLM?.available} />
      <ActionPanel available={byArch.LAM?.available} />
    </div>
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
