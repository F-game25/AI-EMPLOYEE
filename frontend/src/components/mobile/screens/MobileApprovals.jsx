/* NEXUS OS Mobile — Approvals: unified HITL + Forge pending actions */
import { useState, useEffect, useCallback, useRef } from 'react'
import { TopBar, Section, Empty, Spinner, StatusPill } from '../MobileUI'

const AUTH = () => {
  const t = localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const RISK_COLOR = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--error)', critical: 'var(--error)' }
const RISK_LABEL = { low: 'LOW', medium: 'MED', high: 'HIGH', critical: 'CRIT' }

export default function MobileApprovals({ onBack }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const [hitlRes, forgeRes] = await Promise.allSettled([
        fetch('/api/security/hitl', { headers: AUTH() }),
        fetch('/api/forge/actions?status=pending_approval', { headers: AUTH() }),
      ])

      const hitlItems = hitlRes.status === 'fulfilled' && hitlRes.value.ok
        ? (await hitlRes.value.json()).items || []
        : []

      const forgeItems = forgeRes.status === 'fulfilled' && forgeRes.value.ok
        ? (await forgeRes.value.json()).actions || []
        : []

      const normalized = [
        ...hitlItems.map(i => ({ ...i, _source: 'hitl' })),
        ...forgeItems.map(i => ({
          id: i.id,
          action_type: i.type || 'FORGE',
          description: i.label || i.description || i.path || 'Forge action',
          risk_level: i.risk || 'medium',
          agent: i.run_id ? `run:${i.run_id.slice(-6)}` : 'forge',
          _source: 'forge',
          run_id: i.run_id,
        })),
      ]

      setItems(normalized)
    } catch {
      // keep previous items on error
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    pollRef.current = setInterval(load, 5000)
    return () => clearInterval(pollRef.current)
  }, [load])

  const act = useCallback(async (item, action) => {
    if (busyId) return
    setBusyId(item.id)
    try {
      if (item._source === 'hitl') {
        await fetch(`/api/security/hitl/${item.id}/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...AUTH() },
          body: JSON.stringify({ approved_by: 'operator' }),
        })
      } else {
        const endpoint = action === 'approve'
          ? `/api/forge/runs/${item.run_id}/approve`
          : `/api/forge/runs/${item.run_id}/reject`
        await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...AUTH() },
          body: JSON.stringify({ action_id: item.id, ownerApproved: action === 'approve', approval: 'owner-approved', approved_by: 'operator' }),
        })
      }
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (e) {
      console.error('approval action failed', e)
    } finally {
      setBusyId(null)
    }
  }, [busyId])

  const approveAll = useCallback(async () => {
    const safe = items.filter(i => !['high', 'critical'].includes(i.risk_level))
    for (const item of safe) await act(item, 'approve')
  }, [items, act])

  const safCount = items.filter(i => !['high', 'critical'].includes(i.risk_level)).length

  return (
    <div style={S.screen}>
      <TopBar
        title="APPROVALS"
        subtitle={`${items.length} pending`}
        right={<button style={S.backBtn} onClick={onBack}>✕</button>}
      />

      <div style={S.scroll}>
        {loading ? <Spinner /> : items.length === 0 ? (
          <Empty icon="✓" message="No pending approvals" />
        ) : (
          <>
            {safCount > 0 && (
              <div style={S.batchRow}>
                <button style={S.batchBtn} onClick={approveAll}>
                  ✓ APPROVE ALL SAFE ({safCount})
                </button>
              </div>
            )}

            <Section label="PENDING DECISIONS">
              {items.map(item => {
                const riskColor = RISK_COLOR[item.risk_level] || 'var(--text-muted)'
                const riskLabel = RISK_LABEL[item.risk_level] || (item.risk_level || '?').toUpperCase()
                const busy = busyId === item.id
                return (
                  <div key={item.id} style={S.card}>
                    <div style={S.cardHeader}>
                      <span style={{ ...S.typeBadge, background: item._source === 'hitl' ? 'rgba(239,68,68,0.15)' : 'rgba(229,199,107,0.12)', color: item._source === 'hitl' ? 'var(--error)' : 'var(--gold)' }}>
                        {item._source === 'hitl' ? 'HITL' : 'FORGE'}
                      </span>
                      <span style={{ ...S.riskBadge, color: riskColor, borderColor: riskColor }}>{riskLabel}</span>
                      <span style={S.agent}>{item.agent || item.requesting_agent || '—'}</span>
                    </div>

                    <div style={S.actionType}>{item.action_type || 'ACTION'}</div>
                    <div style={S.desc}>{item.description}</div>

                    <div style={S.btnRow}>
                      <button
                        style={{ ...S.denyBtn, opacity: busy ? 0.4 : 1 }}
                        onClick={() => act(item, 'reject')}
                        disabled={busy}
                      >
                        {busy ? '…' : '✗ DENY'}
                      </button>
                      <button
                        style={{ ...S.allowBtn, opacity: busy ? 0.4 : 1 }}
                        onClick={() => act(item, 'approve')}
                        disabled={busy}
                      >
                        {busy ? '…' : '✓ ALLOW'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

const S = {
  screen: { display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-deep)' },
  scroll: { flex: 1, overflowY: 'auto', paddingBottom: 32 },
  backBtn: { background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 16, cursor: 'pointer', padding: '4px 8px' },
  batchRow: { padding: '12px 16px 4px' },
  batchBtn: {
    width: '100%', padding: '10px', borderRadius: 8, border: '1px solid var(--success)',
    background: 'rgba(34,197,94,0.08)', color: 'var(--success)',
    fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', cursor: 'pointer',
  },
  card: {
    margin: '8px 16px', padding: '14px', borderRadius: 10,
    background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  cardHeader: { display: 'flex', alignItems: 'center', gap: 8 },
  typeBadge: { fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 6px', borderRadius: 4 },
  riskBadge: { fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', padding: '2px 6px', borderRadius: 4, border: '1px solid', background: 'transparent' },
  agent: { flex: 1, fontSize: 9, color: 'var(--text-dim)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  actionType: { fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  desc: { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 },
  btnRow: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  denyBtn: {
    padding: '10px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.3)',
    background: 'rgba(239,68,68,0.08)', color: 'var(--error)',
    fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', cursor: 'pointer',
  },
  allowBtn: {
    padding: '10px', borderRadius: 8, border: 'none',
    background: 'linear-gradient(135deg, var(--success), #16a34a)',
    color: '#fff', fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', cursor: 'pointer',
  },
}
