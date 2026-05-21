import { useState, useEffect, useCallback } from 'react'
import api from '../../api/client'
import './ComputeCenterPage.css'

/* Compute Center (WS6) — local GPU status, estimate, marketplace, owner-approved
   provisioning, jobs, spend meter, audit. Every money path is dry-run by default;
   the UI makes the safety state explicit (no fake "purchased" states). */

export default function ComputeCenterPage() {
  const [local, setLocal] = useState(null)
  const [spend, setSpend] = useState(null)
  const [jobs, setJobs] = useState([])
  const [audit, setAudit] = useState([])
  const [est, setEst] = useState(null)
  const [offers, setOffers] = useState(null)
  const [form, setForm] = useState({ params_b: 7, task: 'finetune', hours: 2 })
  const [approval, setApproval] = useState(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [l, s, j, a] = await Promise.all([
        api.get('/api/compute/local-status').catch(() => null),
        api.get('/api/compute/spend').catch(() => null),
        api.get('/api/compute/jobs').catch(() => ({ jobs: [] })),
        api.get('/api/compute/audit?limit=20').catch(() => ({ events: [] })),
      ])
      setLocal(l); setSpend(s); setJobs(j?.jobs || []); setAudit(a?.events || [])
    } catch { /* offline */ }
  }, [])
  useEffect(() => { refresh(); const i = setInterval(refresh, 10000); return () => clearInterval(i) }, [refresh])

  const estimate = async () => {
    setBusy(true)
    try {
      const e = await api.post('/api/compute/estimate', form)
      setEst(e.estimate)
      const o = await api.post('/api/compute/search-offers', form)
      setOffers(o)
    } finally { setBusy(false) }
  }

  const requestApproval = async () => {
    const r = await api.post('/api/compute/request-approval', form)
    setApproval({ ...r.approval, token: null, verified: false })
  }
  const verifyOwner = async () => {
    const r = await api.post('/api/compute/verify-owner', { nonce: approval.nonce, ownerApproved: true })
    if (r.ok) setApproval(a => ({ ...a, token: r.approval_token, verified: true }))
    else setApproval(a => ({ ...a, error: r.error }))
  }
  const startJob = async (offer, dryRun = true) => {
    setBusy(true)
    try {
      await api.post('/api/compute/start-job', { name: `${form.task}-${form.params_b}B`, offer: { ...offer, hours: form.hours }, dry_run: dryRun, approval_token: approval?.token })
      refresh()
    } finally { setBusy(false) }
  }
  const stopJob = async (id) => { await api.post('/api/compute/stop-job', { id }); refresh() }
  const [openJob, setOpenJob] = useState(null)

  const live = local?.live_provisioning
  const dayUsd = spend?.day_usd ?? 0
  const cap = spend?.daily_cap ?? 0
  const pct = cap > 0 ? Math.min(100, (dayUsd / cap) * 100) : 0

  return (
    <div className="cc-page">
      <header className="cc-head">
        <div>
          <h1>Compute Center</h1>
          <p className="cc-sub">Estimate compute, search remote GPU, provision with owner approval. Dry-run by default — no charge without explicit approval.</p>
        </div>
        <div className="cc-head-stats">
          <span className={`cc-chip ${live ? 'cc-chip--live' : 'cc-chip--safe'}`}>{live ? '● LIVE provisioning ON' : '● Dry-run (live OFF)'}</span>
          <button className="cc-btn" onClick={refresh} aria-label="Refresh compute status">↻</button>
        </div>
      </header>

      {/* Local hardware */}
      <section className="cc-section">
        <h2>Local compute</h2>
        {local?.gpu
          ? <div className="cc-gpus">{local.gpus.map((g, i) => (
              <div key={i} className="cc-gpu">
                <div className="cc-gpu-name">{g.name}</div>
                <div className="cc-gpu-bar"><div style={{ width: `${Math.min(100, (g.vram_used_mb / g.vram_total_mb) * 100)}%` }} /></div>
                <div className="cc-gpu-meta">{Math.round(g.vram_used_mb / 1024)}/{Math.round(g.vram_total_mb / 1024)} GB · {g.util_pct}% util</div>
              </div>))}
            </div>
          : <div className="cc-note">{local?.note || 'No local GPU detected — remote compute recommended for heavy jobs.'}</div>}
      </section>

      {/* Estimator + marketplace */}
      <section className="cc-section">
        <h2>Estimate &amp; marketplace</h2>
        <div className="cc-form">
          <label>Model size (B)<input type="number" value={form.params_b} onChange={e => setForm(f => ({ ...f, params_b: Number(e.target.value) }))} /></label>
          <label>Task<select value={form.task} onChange={e => setForm(f => ({ ...f, task: e.target.value }))}><option>inference</option><option>finetune</option><option>train</option></select></label>
          <label>Hours<input type="number" value={form.hours} onChange={e => setForm(f => ({ ...f, hours: Number(e.target.value) }))} /></label>
          <button className="cc-btn cc-btn--gold" onClick={estimate} disabled={busy}>Estimate</button>
        </div>
        {est && (
          <div className="cc-est">
            <span>{est.gpu_count}× <b>{est.recommended_gpu}</b></span>
            <span>{est.est_vram_gb} GB VRAM</span>
            <span>~${est.est_hourly_usd}/hr</span>
            <span className="cc-est-total">≈ ${est.est_total_usd} for {est.est_hours}h</span>
          </div>
        )}
        {offers?.offers?.length > 0 && (
          <table className="cc-offers" aria-label="Available GPU offers">
            <thead><tr><th>Provider</th><th>GPU</th><th>$/hr</th><th>Source</th><th></th></tr></thead>
            <tbody>
              {offers.offers.map((o, i) => (
                <tr key={i}>
                  <td>{o.provider_name}</td><td>{o.gpu} ×{o.gpu_count}</td><td>${o.hourly_usd}</td>
                  <td><span className={`cc-tag ${o.live ? 'cc-tag--live' : ''}`}>{o.source}</span></td>
                  <td><button className="cc-btn cc-btn--sm" onClick={() => startJob(o, true)} disabled={busy}>Plan (dry-run)</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {offers && <div className="cc-note cc-note--dim">{offers.note}</div>}
      </section>

      {/* Owner approval */}
      <section className="cc-section">
        <h2>Owner approval</h2>
        <p className="cc-sub">A real purchase needs a single-use owner approval. This never charges by itself.</p>
        {!approval
          ? <button className="cc-btn" onClick={requestApproval}>Request approval for current estimate</button>
          : (
            <div className="cc-approval">
              <div>{approval.plan_summary} — expires in ~5 min</div>
              {!approval.verified
                ? <button className="cc-btn cc-btn--gold" onClick={verifyOwner}>✓ I approve (owner)</button>
                : <span className="cc-ok">✓ Approved — token issued (single-use)</span>}
              {approval.error && <span className="cc-err">{approval.error}</span>}
            </div>
          )}
      </section>

      {/* Spend meter */}
      <section className="cc-section">
        <h2>Spend</h2>
        <div className="cc-spend">
          <div className="cc-spend-bar"><div style={{ width: `${pct}%` }} className={pct > 80 ? 'hot' : ''} /></div>
          <div className="cc-spend-meta">Today ${dayUsd.toFixed(2)} / cap ${cap.toFixed(2)} · total ${(spend?.total_usd ?? 0).toFixed(2)} {cap === 0 && <b>(spending disabled)</b>}</div>
        </div>
      </section>

      {/* Jobs */}
      <section className="cc-section">
        <h2>Jobs</h2>
        {jobs.length === 0 ? <div className="cc-note">No compute jobs yet.</div> : (
          <table className="cc-jobs" aria-label="Compute jobs">
            <thead><tr><th>Name</th><th>Provider</th><th>GPU</th><th>Status</th><th>Mode</th><th></th></tr></thead>
            <tbody>
              {jobs.map(j => (
                <>
                  <tr key={j.id}>
                    <td>{j.name}</td><td>{j.provider || '—'}</td><td>{j.gpu || '—'}</td>
                    <td><span className={`cc-status cc-status--${j.status}`}>{j.status}</span></td>
                    <td>{j.dry_run ? 'dry-run' : 'live'}</td>
                    <td>
                      <button className="cc-btn cc-btn--sm" onClick={() => setOpenJob(openJob === j.id ? null : j.id)}>{openJob === j.id ? 'Hide' : 'Persistence'}</button>
                      {!['stopped', 'refused'].includes(j.status) && <button className="cc-btn cc-btn--sm cc-btn--stop" onClick={() => stopJob(j.id)}>Stop</button>}
                    </td>
                  </tr>
                  {openJob === j.id && <tr key={`${j.id}-p`}><td colSpan={6}><JobPersistence jobId={j.id} /></td></tr>}
                </>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Audit */}
      <section className="cc-section">
        <h2>Audit trail</h2>
        <div className="cc-audit">
          {audit.length === 0 ? <div className="cc-note">No events.</div>
            : audit.slice().reverse().map((e, i) => <div key={i} className="cc-audit-row"><code>{e.event}</code><span>{(e.ts || '').slice(11, 19)}</span></div>)}
        </div>
      </section>
    </div>
  )
}

/* WS7: per-job persistence — local is the source of truth. */
function JobPersistence({ jobId }) {
  const [st, setSt] = useState(null)
  const [arts, setArts] = useState([])
  const [msg, setMsg] = useState(null)
  const load = useCallback(async () => {
    const [s, a] = await Promise.all([
      api.get(`/api/compute/jobs/${jobId}/sync-status`).catch(() => null),
      api.get(`/api/compute/jobs/${jobId}/artifacts`).catch(() => ({ files: [] })),
    ])
    setSt(s); setArts(a?.files || [])
  }, [jobId])
  useEffect(() => { load(); const i = setInterval(load, 8000); return () => clearInterval(i) }, [load])

  const forceSync = async () => { setMsg('Syncing…'); const r = await api.post(`/api/compute/jobs/${jobId}/force-sync`, {}); setMsg(`Verified: ${r.verified}`); load() }
  const recover = async () => { const r = await api.get(`/api/compute/jobs/${jobId}/recover`); setMsg(`Latest checkpoint: ${r.latest_checkpoint?.name || 'none'}`) }
  const teardown = async (force = false) => {
    const r = await api.post(`/api/compute/jobs/${jobId}/safe-teardown`, { force }).catch(e => ({ ok: false, reason: e.message }))
    setMsg(r.allowed ? `Teardown allowed${r.forced ? ' (forced)' : ''} — local archive retained.` : `Refused: ${r.reason}`)
    load()
  }

  if (!st) return <div className="cc-note">Loading persistence…</div>
  return (
    <div className="cc-persist">
      <div className="cc-persist-row">
        <span className={st.unsynced_warning ? 'cc-warn' : 'cc-ok'}>{st.unsynced_warning ? '⚠ unsynced/stale' : '✓ synced & verified'}</span>
        <span>{st.file_count} files</span>
        <span>{st.checkpoints} checkpoints</span>
        <span>heartbeat {st.last_heartbeat_age_s == null ? '—' : `${st.last_heartbeat_age_s}s ago`}{st.heartbeat_stale ? ' (stale)' : ''}</span>
        <span>last sync {st.last_sync ? String(st.last_sync).slice(11, 19) : '—'}</span>
      </div>
      <div className="cc-persist-actions">
        <button className="cc-btn cc-btn--sm" onClick={forceSync}>Force sync</button>
        <button className="cc-btn cc-btn--sm" onClick={recover}>Recover</button>
        <button className="cc-btn cc-btn--sm" onClick={() => teardown(false)}>Safe teardown</button>
        <button className="cc-btn cc-btn--sm cc-btn--stop"
          onClick={() => { if (window.confirm('Force teardown ignores the sync-verified gate and may release the remote before all work is confirmed in the local archive. Continue?')) teardown(true) }}>
          Force teardown
        </button>
      </div>
      {arts.length > 0 && (
        <div className="cc-persist-files">
          {arts.map((f, i) => <div key={i}><code>{f.rel}</code> <span>{f.bytes}b · {String(f.sha256).slice(0, 10)}</span></div>)}
        </div>
      )}
      {msg && <div className="cc-note cc-note--dim">{msg}</div>}
    </div>
  )
}
