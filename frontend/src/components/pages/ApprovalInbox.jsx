import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
import { useForgeStore } from '../../store/forgeStore'
import { useAppStore } from '../../store/appStore'
import './ApprovalInbox.css'

const FILTERS = ['pending', 'approved', 'rejected', 'all']

function fmt(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

function riskTone(level = '') {
  const raw = String(level).toLowerCase()
  if (raw === 'high' || raw === 'critical') return 'high'
  if (raw === 'medium') return 'medium'
  return 'low'
}

function ApprovalCard({ item, onDecide, busy, onOpenForge }) {
  const [reason, setReason] = useState('')
  const pending = item.status === 'pending'
  return (
    <article className={`approval-card approval-card--${item.status}`}>
      <div className="approval-card__top">
        <div>
          <p className="approval-kicker">{item.source}</p>
          <h2>{item.requested_action || 'Approval required'}</h2>
        </div>
        <div className="approval-card__badges">
          <span className={`approval-risk approval-risk--${riskTone(item.risk_level)}`}>{item.risk_level || 'risk'}</span>
          <span className="approval-status">{item.status}</span>
        </div>
      </div>

      <div className="approval-grid">
        <div>
          <span>Source task</span>
          <b>{item.source_task || item.turn_id || 'Unknown'}</b>
        </div>
        <div>
          <span>Requested</span>
          <b>{fmt(item.requested_at)}</b>
        </div>
        <div>
          <span>Requested by</span>
          <b>{item.requested_by || 'system'}</b>
        </div>
        {item.run_id && (
          <div>
            <span>Forge run</span>
            <b>{item.run_id}</b>
          </div>
        )}
        {item.action_id && (
          <div>
            <span>Action</span>
            <b>{item.action_id}</b>
          </div>
        )}
      </div>

      <div className="approval-section">
        <span>Expected external effect</span>
        <p>{item.expected_external_effect || 'No external effect details supplied.'}</p>
      </div>
      <div className="approval-section">
        <span>Dry-run preview</span>
        <p>{item.dry_run_preview || item.reason || 'No preview supplied.'}</p>
      </div>
      {Array.isArray(item.proof) && item.proof.length > 0 && (
        <div className="approval-proof">
          {item.proof.slice(0, 4).map((proof, index) => (
            <span key={`${item.id}:proof:${index}`}>{proof.label || proof.type || 'proof'}</span>
          ))}
        </div>
      )}

      {pending ? (
        <div className="approval-actions">
          <input
            value={reason}
            onChange={event => setReason(event.target.value)}
            placeholder="Decision reason"
          />
          <button type="button" className="approval-btn approval-btn--reject" disabled={busy} onClick={() => onDecide(item, 'reject', reason)}>
            Reject
          </button>
          <button type="button" className="approval-btn" disabled={busy} onClick={() => onDecide(item, 'approve', reason)}>
            Approve
          </button>
          {item.run_id && (
            <button type="button" className="approval-btn approval-btn--ghost" disabled={busy} onClick={() => onOpenForge(item)}>
              Open Forge
            </button>
          )}
        </div>
      ) : (
        <div className="approval-decision">
          Decision recorded {item.decision?.decided_at ? fmt(item.decision.decided_at) : ''}
        </div>
      )}
    </article>
  )
}

export default function ApprovalInbox() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const forgePendingApprovals = useForgeStore(s => s.pendingApprovals)
  const forgeRefresh = useForgeStore(s => s.refresh)
  const forgeSelectRun = useForgeStore(s => s.selectRun)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('pending')
  const [query, setQuery] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [inbox] = await Promise.all([
        api.get('/api/approvals/inbox'),
        forgeRefresh({ silent: true, reason: 'approval_inbox_load' }).catch(() => null),
      ])
      setData(inbox)
    } catch (err) {
      setError(err?.message || 'Approval Inbox unavailable')
    } finally {
      setLoading(false)
    }
  }, [forgeRefresh])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const handler = event => {
      const type = event.detail?.type || ''
      if (type.startsWith('approval:') || type.startsWith('forge:approval_')) load()
    }
    window.addEventListener('ws:event', handler)
    return () => window.removeEventListener('ws:event', handler)
  }, [load])

  const forgeItems = useMemo(() => (forgePendingApprovals || []).map(item => ({
    id: item.id || item.action_id,
    source: 'forge',
    status: ['approved', 'rejected'].includes(item.status) ? item.status : 'pending',
    requested_action: item.summary || item.action_type || 'Forge action approval',
    source_task: item.run_id || item.project_id || 'Forge run',
    requested_at: item.created_at || item.updated_at,
    requested_by: 'forge',
    risk_level: item.risk || item.risk_level || 'medium',
    expected_external_effect: item.file_path ? `Modify ${item.file_path} inside a Forge run workspace.` : 'Approve a staged Forge action.',
    dry_run_preview: item.unified_diff || item.summary || 'Forge staged action requires owner approval.',
    run_id: item.run_id,
    action_id: item.action_id || item.id,
    proof: item.file_path ? [{ label: item.file_path, type: 'file' }] : [],
    _forge: item,
  })), [forgePendingApprovals])
  const items = useMemo(() => {
    const base = Array.isArray(data?.items) ? data.items : []
    const seen = new Set(base.map(item => item.id))
    return [...base, ...forgeItems.filter(item => !seen.has(item.id))]
  }, [data?.items, forgeItems])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter(item => {
      const statusMatch = filter === 'all' || item.status === filter
      if (!statusMatch) return false
      if (!q) return true
      return [item.id, item.source, item.requested_action, item.source_task, item.turn_id, item.expected_external_effect]
        .filter(Boolean)
        .some(value => String(value).toLowerCase().includes(q))
    })
  }, [items, filter, query])

  const decide = async (item, action, reason) => {
    setBusyId(item.id)
    setNotice(null)
    try {
      const result = await api.post(`/api/approvals/${encodeURIComponent(item.id)}/${action}`, { reason })
      setNotice(result?.execution?.details || `Approval ${result.decision}`)
      await load()
      await forgeRefresh({ silent: true, reason: `approval_${action}` }).catch(() => null)
    } catch (err) {
      setError(err?.message || `Could not ${action} approval`)
    } finally {
      setBusyId(null)
    }
  }

  const counts = data?.counts || {}
  const displayCounts = {
    pending: items.filter(item => item.status === 'pending').length,
    approved: items.filter(item => item.status === 'approved').length,
    rejected: items.filter(item => item.status === 'rejected').length,
    total: items.length,
  }

  const openForge = (item) => {
    if (item.run_id) forgeSelectRun(item.run_id)
    setActiveSection('ascend-forge')
  }

  return (
    <main className="approval-inbox">
      <section className="approval-hero">
        <div>
          <p className="approval-kicker">APPROVAL INBOX</p>
          <h1>Human Control Surface</h1>
          <p>Review Money Mode, outreach, payment, publishing, external-account, Forge, memory, and other risky actions before anything consequential happens.</p>
        </div>
        <button type="button" className="approval-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing' : 'Refresh'}
        </button>
      </section>

      <section className="approval-metrics">
        <div><span>Pending</span><b>{displayCounts.pending || counts.pending || 0}</b></div>
        <div><span>Approved</span><b>{displayCounts.approved || counts.approved || 0}</b></div>
        <div><span>Rejected</span><b>{displayCounts.rejected || counts.rejected || 0}</b></div>
        <div><span>Total</span><b>{displayCounts.total || counts.total || items.length}</b></div>
      </section>

      {notice && <div className="approval-alert approval-alert--ok">{notice}</div>}
      {error && <div className="approval-alert">{error}</div>}

      <section className="approval-tools">
        <div className="approval-filters">
          {FILTERS.map(option => (
            <button
              key={option}
              type="button"
              className={filter === option ? 'approval-filter approval-filter--active' : 'approval-filter'}
              onClick={() => setFilter(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Filter by source, task, turn, or effect"
        />
      </section>

      <section className="approval-list">
        {loading && !items.length && (
          <div className="approval-empty"><b>Loading approvals…</b></div>
        )}
        {filtered.map(item => (
          <ApprovalCard key={item.id} item={item} onDecide={decide} busy={busyId === item.id} onOpenForge={openForge} />
        ))}
        {!loading && !filtered.length && (
          <div className="approval-empty">
            <b>{filter === 'pending' ? 'No approvals pending ✓' : 'No approvals in this view'}</b>
            <span>Risky actions will appear here when a task requests external effects or Forge needs owner/operator approval.</span>
          </div>
        )}
      </section>
    </main>
  )
}
