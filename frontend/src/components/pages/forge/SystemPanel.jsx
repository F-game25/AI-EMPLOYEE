import { useState, useEffect, useCallback } from 'react'
import { StatusPill } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST, JPOST_JSON, textFrom, titleize, normalizeAction } from './helpers'
import { MiniField } from './primitives'

export function PolicyPreview({ actions }) {
  const [policy, setPolicy] = useState(null)
  const [lastDecision, setLastDecision] = useState(null)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    JGET('/api/autonomy/policy')
      .then(r => r.json())
      .then(d => setPolicy(d.policy || null))
      .catch(() => setPolicy({ state: 'degraded' }))
  }, [])

  useEffect(() => {
    const action = actions[0]
    if (!action) return
    const normalized = normalizeAction(action)
    JPOST('/api/autonomy/tool-call/evaluate', {
      tool: normalized.type,
      action: normalized.label,
      intent: normalized.description,
    })
      .then(r => r.json())
      .then(setLastDecision)
      .catch(() => setLastDecision({ state: 'degraded', decision: 'requires_approval' }))
  }, [actions])

  const visibleDecision = actions.length ? lastDecision : null
  const decision = visibleDecision?.decision || 'waiting'
  const tone = decision === 'allow' || decision === 'allow_logged' ? 'success' : decision === 'block' ? 'alert' : 'warn'

  return (
    <div className={`af-accordion ${isOpen ? 'af-accordion--open' : ''}`}>
      <button className="af-accordion__toggle" onClick={() => setIsOpen(o => !o)}>
        <div className="af-accordion__summary">
          <span>Autonomy Policy</span>
          <StatusPill label={decision.toUpperCase()} tone={tone} size="sm" />
        </div>
        <span className="af-accordion__chevron">▾</span>
      </button>
      {isOpen && (
        <div className="af-accordion__body">
          <div className="af-policy__body">
            <div className="af-policy__row">
              <span>Risk levels</span>
              <strong>{Object.keys(policy?.risk_levels || {}).length || 0}</strong>
            </div>
            <div className="af-policy__row">
              <span>Forbidden capabilities</span>
              <strong>{policy?.forbidden_capabilities?.length || 0}</strong>
            </div>
            <div className="af-policy__row">
              <span>First pending action</span>
              <strong>{visibleDecision?.risk || 'none'}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SwarmToggle() {
  const [cfg, setCfg] = useState({ enabled: true, n_agents_code: 5, n_agents_analysis: 3 })
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    JGET('/api/forge/swarm/config').then(r => r.json()).then(r => { if (r.ok) setCfg(r) }).catch(() => {})
  }, [])

  async function patch(update) {
    setBusy(true)
    try {
      const res = await JPOST('/api/forge/swarm/config', update).then(r => r.json())
      if (res.ok) setCfg(res)
    } catch { setCfg(c => ({ ...c, ...update })) }
    finally { setBusy(false) }
  }

  const c = `${cfg.n_agents_code}c/${cfg.n_agents_analysis}a`

  return (
    <div style={{ borderTop: '1px solid var(--af-border)', marginTop: 8, paddingTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--af-text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', flex: 1 }}>
          Swarm {cfg.enabled && <span style={{ color: '#60A5FA', fontWeight: 400 }}>({c})</span>}
        </span>
        <button
          onClick={() => patch({ enabled: !cfg.enabled })}
          disabled={busy}
          style={{
            padding: '3px 10px', fontSize: 10, fontWeight: 700, borderRadius: 4, border: 'none', cursor: 'pointer',
            background: cfg.enabled ? 'rgba(96,165,250,0.2)' : 'rgba(156,163,175,0.15)',
            color: cfg.enabled ? '#60A5FA' : 'var(--af-text-dim)',
            outline: cfg.enabled ? '1px solid rgba(96,165,250,0.4)' : '1px solid var(--af-border)',
          }}
        >{cfg.enabled ? 'ON' : 'OFF'}</button>
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ fontSize: 9, padding: '2px 6px', background: 'transparent', border: '1px solid var(--af-border)', borderRadius: 4, color: 'var(--af-text-dim)', cursor: 'pointer' }}
          title="Configure agent counts"
        >⚙</button>
      </div>
      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
          {[['Code agents', 'n_agents_code', cfg.n_agents_code], ['Analysis agents', 'n_agents_analysis', cfg.n_agents_analysis]].map(([label, key, val]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 10, color: 'var(--af-text-dim)', flex: 1 }}>{label}</span>
              <select
                value={val}
                onChange={e => patch({ [key]: Number(e.target.value) })}
                style={{ fontSize: 10, background: 'var(--af-surface)', color: 'var(--af-text)', border: '1px solid var(--af-border)', borderRadius: 4, padding: '2px 4px' }}
              >
                {[2, 3, 4, 5, 7, 10].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ForgeSystemPanel({ onQueueItems }) {
  const [data, setData] = useState({ loading: true })
  const [isOpen, setIsOpen] = useState(false)

  const load = useCallback(async () => {
    const [readiness, status, snapshots, queue, runs] = await Promise.allSettled([
      JGET('/api/readiness').then(r => r.json()),
      JGET('/api/forge/status').then(r => r.json()),
      JGET('/api/forge/snapshots').then(r => r.json()),
      JGET('/api/forge/queue').then(r => r.json()),
      JGET('/api/forge/runs?limit=5').then(r => r.json()),
    ])
    const next = {
      loading: false,
      readiness: readiness.status === 'fulfilled' ? readiness.value : null,
      status: status.status === 'fulfilled' ? status.value : null,
      snapshots: snapshots.status === 'fulfilled' ? snapshots.value : null,
      queue: queue.status === 'fulfilled' ? queue.value : null,
      runs: runs.status === 'fulfilled' ? runs.value : null,
    }
    setData(next)
    if (next.queue?.items) onQueueItems(next.queue.items)
  }, [onQueueItems])

  useEffect(() => {
    const first = window.setTimeout(load, 0)
    const t = window.setInterval(load, 30000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(t)
    }
  }, [load])

  const readiness = data.readiness?.readiness || data.readiness || {}
  const status = data.status || {}
  const snapshots = data.snapshots?.snapshots || []
  const summary = data.snapshots?.summary || {}
  const latest = snapshots[0] || {}
  const recentRuns = data.runs?.runs || []
  const persistence = status.persistence || data.runs?.persistence || {}
  const readyState = readiness.ready === true || readiness.status === 'ok'
    ? 'ready'
    : readiness.status || (data.loading ? 'loading' : 'degraded')
  const statusTone = status.frozen || readyState === 'degraded' ? 'warn' : readyState === 'ready' ? 'success' : 'idle'

  return (
    <div className={`af-accordion ${isOpen ? 'af-accordion--open' : ''}`}>
      <button className="af-accordion__toggle" onClick={() => setIsOpen(o => !o)}>
        <div className="af-accordion__summary">
          <span>Forge Operations</span>
          <StatusPill label={String(readyState).toUpperCase()} tone={statusTone} size="sm" />
          <span style={{marginLeft:'auto',fontSize:9,color:'var(--nx-text-muted)',fontWeight:400,textTransform:'none',letterSpacing:0}}>
            {(status.runs_total ?? data.runs?.total ?? 0)} runs
          </span>
        </div>
        <span className="af-accordion__chevron">▾</span>
      </button>
      {isOpen && (
        <div className="af-accordion__body">
          <div className="af-ops">
            {data.loading && <div className="af-ops__notice">Loading live Forge status...</div>}
            {!data.loading && !data.status && <div className="af-ops__notice af-ops__notice--warn">Forge status endpoint did not respond.</div>}
            <div className="af-mini-grid">
              <MiniField label="Mode" value={status.mode || status.state} />
              <MiniField label="Active" value={status.active} />
              <MiniField label="Frozen" value={status.frozen ?? status.forge_frozen} />
              <MiniField label="Queue" value={status.queue_depth ?? data.queue?.total} />
              <MiniField label="Run Store" value={persistence.backend || textFrom(status.persistence)} />
              <MiniField label="Runs" value={status.runs_total ?? data.runs?.total} />
              <MiniField label="Snapshots" value={summary.total_snapshots ?? snapshots.length} />
              <MiniField label="Latest" value={latest.id || latest.snapshot_id} />
            </div>
            <SwarmToggle />
            {(readiness.python || readiness.node || readiness.neural_brain || readiness.graph || readiness.ai_core) && (
              <div className="af-ops__chips">
                {['node', 'python', 'ai_core', 'neural_brain', 'graph'].map(key => (
                  readiness[key] !== undefined && <span key={key}>{key}: {textFrom(readiness[key])}</span>
                ))}
              </div>
            )}
            {latest.module && (
              <div className="af-ops__latest">
                <span>{latest.module}</span>
                <strong>{latest.status || latest.tag || 'snapshot'}</strong>
              </div>
            )}
            {recentRuns.length > 0 && (
              <div className="af-ops__runs">
                {recentRuns.slice(0, 3).map(run => (
                  <div className="af-ops__run" key={run.run_id || run.id}>
                    <span>{run.goal || run.run_id || run.id}</span>
                    <strong>{titleize(run.workspace_mode || run.status || 'new')}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function AgentBlueprintPanel({ open, onClose }) {
  const [status, setStatus] = useState(null)
  const [name, setName] = useState('AETERNUS Builder Agent')
  const [purpose, setPurpose] = useState('Build and improve AETERNUS systems with coding, testing, security, and release skills.')
  const [blueprint, setBlueprint] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    JGET('/api/forge/engine/status')
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ state: 'degraded' }))
  }, [open])

  if (!open) return null

  const createBlueprint = async () => {
    setBusy(true)
    try {
      const r = await JPOST('/api/forge/agents/blueprint', { name, purpose, target_type: 'coding_agent' })
      const d = await r.json()
      if (d.blueprint) { setBlueprint(d.blueprint); toastSuccess('Agent blueprint created') }
      else toastError(d.error || 'Blueprint failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  const registerBlueprint = async () => {
    if (!blueprint) return
    setBusy(true)
    try {
      const r = await JPOST(`/api/forge/agents/${blueprint.id}/register`, { ownerApproved: true })
      const d = await r.json()
      if (d.agent) { setBlueprint(d.blueprint); toastSuccess('Supervised builder agent registered') }
      else toastError(d.error || 'Registration failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="af-modal-overlay" onClick={onClose}>
      <div className="af-modal-dialog" onClick={e => e.stopPropagation()}>
        <div className="af-blueprint__header">
          <span>Create Agent</span>
          <StatusPill label={(status?.state || 'loading').toUpperCase()} tone={status?.state === 'live' ? 'success' : 'idle'} size="sm" />
          <button style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--nx-text-muted)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }} onClick={onClose} aria-label="Close">×</button>
        </div>
        <input className="af-blueprint__input" value={name} onChange={e => setName(e.target.value)} placeholder="Agent name" />
        <textarea className="af-blueprint__textarea" value={purpose} onChange={e => setPurpose(e.target.value)} rows={3} />
        <button className="af-btn af-btn--primary af-btn--sm" disabled={busy || !name.trim() || !purpose.trim()} onClick={createBlueprint}>
          {busy ? 'Working…' : 'Generate Blueprint'}
        </button>
        {blueprint && (
          <div className="af-blueprint__result">
            <div className="af-blueprint__name">{blueprint.name}</div>
            <div className="af-blueprint__meta">{blueprint.authority_profile} · {blueprint.risk_level} · {blueprint.registration_status}</div>
            <div className="af-blueprint__chips">
              {(blueprint.selected_skills || []).slice(0, 6).map(skill => (
                <span key={skill.id} className="af-blueprint__chip">{skill.name}</span>
              ))}
            </div>
            <button
              className="af-btn af-btn--success af-btn--sm"
              disabled={busy || blueprint.registration_status === 'registered'}
              onClick={registerBlueprint}
            >
              {blueprint.registration_status === 'registered' ? 'Registered' : 'Approve + Register'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
