import { useEffect, useMemo, useState } from 'react'
import api from '../../api/client'
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

function ApprovalCard({ item, onDecide, busy }) {
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
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('pending')
  const [query, setQuery] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get('/api/approvals/inbox'))
    } catch (err) {
      setError(err?.message || 'Approval Inbox unavailable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const items = Array.isArray(data?.items) ? data.items : []
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
    } catch (err) {
      setError(err?.message || `Could not ${action} approval`)
    } finally {
      setBusyId(null)
    }
  }

  const counts = data?.counts || {}

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
        <div><span>Pending</span><b>{counts.pending || 0}</b></div>
        <div><span>Approved</span><b>{counts.approved || 0}</b></div>
        <div><span>Rejected</span><b>{counts.rejected || 0}</b></div>
        <div><span>Total</span><b>{counts.total || items.length}</b></div>
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
          <ApprovalCard key={item.id} item={item} onDecide={decide} busy={busyId === item.id} />
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
