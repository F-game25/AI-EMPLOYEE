import { useEffect, useState } from 'react'
import { API_URL } from '../../config/api'

const ROLE_LABELS = { llm: 'LLM', lam: 'LAM', vlm: 'VLM', sam: 'SAM', lcm: 'LCM' }
const ROLE_COLOR  = { llm: '#20D6C7', lam: '#E5C76B', vlm: '#A78BFA', sam: '#34D399', lcm: '#F472B6' }

export default function MiddlewareStatusWidget() {
  const [status, setStatus] = useState(null)
  const [err, setErr]       = useState(null)

  useEffect(() => {
    let alive = true
    const load = () => fetch(`${API_URL}/api/middleware/status`)
      .then(r => r.json())
      .then(d => { if (alive) { setStatus(d); setErr(null) } })
      .catch(e => { if (alive) setErr(e.message) })

    load()
    const t = setInterval(load, 8000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const card = {
    background: 'rgba(12,14,24,0.7)',
    border: '1px solid rgba(229,199,107,0.12)',
    borderRadius: 8,
    padding: '14px 16px',
    fontFamily: 'var(--font-mono, monospace)',
  }
  const label = { fontSize: 9, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.35)', marginBottom: 10 }
  const row   = { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }

  function RoleBadge({ role, active }) {
    return (
      <span style={{
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.1em',
        background: active ? `${ROLE_COLOR[role]}18` : 'rgba(255,255,255,0.04)',
        border: `1px solid ${active ? ROLE_COLOR[role] : 'rgba(255,255,255,0.08)'}`,
        color: active ? ROLE_COLOR[role] : 'rgba(255,255,255,0.25)',
        opacity: active ? 1 : 0.6,
      }}>
        {ROLE_LABELS[role] || role.toUpperCase()}
      </span>
    )
  }

  if (err) return (
    <div style={card}>
      <p style={{ ...label, marginBottom: 0 }}>AI MIDDLEWARE</p>
      <p style={{ fontSize: 9, color: 'rgba(255,59,59,0.7)', marginTop: 6 }}>Middleware offline — {err}</p>
    </div>
  )

  if (!status) return (
    <div style={card}>
      <p style={{ ...label, marginBottom: 0 }}>AI MIDDLEWARE</p>
      <p style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', marginTop: 6 }}>Loading…</p>
    </div>
  )

  const activeRoles = new Set([...(status.active_models || []), ...(status.wavefield_enabled ? ['llm'] : [])])
  const optional    = status.optional_models || {}
  if (optional.vlm) activeRoles.add('vlm')
  if (optional.sam) activeRoles.add('sam')
  if (optional.lcm) activeRoles.add('lcm')

  const wfMetrics = status.wavefield_metrics || {}
  const wfMode    = status.wavefield_rollout_mode || 'off'
  const wfEnabled = !!status.wavefield_enabled

  return (
    <div style={card}>
      <p style={label}>AI MIDDLEWARE LAYER</p>

      {/* Model role badges */}
      <div style={row}>
        {Object.keys(ROLE_LABELS).map(r => (
          <RoleBadge key={r} role={r} active={activeRoles.has(r)} />
        ))}
      </div>

      {/* Wave Field status */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
        padding: '6px 10px',
        background: wfEnabled ? 'rgba(32,214,199,0.06)' : 'rgba(255,255,255,0.03)',
        borderRadius: 5,
        border: `1px solid ${wfEnabled ? 'rgba(32,214,199,0.2)' : 'rgba(255,255,255,0.06)'}`,
      }}>
        <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.1em', color: wfEnabled ? '#20D6C7' : 'rgba(255,255,255,0.25)' }}>
          WAVE FIELD
        </span>
        <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)', flex: 1 }}>
          {wfEnabled ? `${wfMode.toUpperCase()} MODE` : 'DISABLED'}
        </span>
        {wfEnabled && (
          <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)' }}>
            {wfMetrics.wavefield_calls || 0} calls · {wfMetrics.fallbacks || 0} fallbacks
          </span>
        )}
      </div>

      {/* MoE summary */}
      <div style={{ display: 'flex', gap: 16 }}>
        {[
          { label: 'ROUTED',    val: wfMetrics.route_selected || 0 },
          { label: 'WF HITS',  val: wfMetrics.route_selected_wavefield || 0 },
          { label: 'SHADOWS',   val: wfMetrics.shadow_requests || 0 },
          { label: 'ERRORS',    val: wfMetrics.wavefield_errors || 0 },
        ].map(({ label: l, val }) => (
          <div key={l} style={{ textAlign: 'center' }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: val > 0 ? '#E5C76B' : 'rgba(255,255,255,0.3)', margin: 0 }}>{val}</p>
            <p style={{ fontSize: 7, color: 'rgba(255,255,255,0.25)', letterSpacing: '0.1em', margin: 0 }}>{l}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
