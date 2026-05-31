import { useState, useEffect } from 'react'
import { SectionLabel, StatusPill, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST_JSON, titleize, normalizeAction, isPendingAction, canBatchApprove } from './helpers'
import { MiniField, StructuredList } from './primitives'

const CLOSED_ACTION_STATUSES = new Set(['staged', 'verified', 'applied', 'verify_failed', 'rejected', 'failed', 'blocked', 'deployed'])

function needsOperatorDecision(action) {
  const normalized = normalizeAction(action)
  return isPendingAction(normalized) && !CLOSED_ACTION_STATUSES.has(normalized.status.toLowerCase())
}

export function DiffViewer({ diff }) {
  if (!diff) return <EmptyState icon="📋" title="No changes yet" sub="Start chatting to see proposed file changes" />
  if (typeof diff === 'string') {
    return (
      <div className="af-diff">
        <div className="af-diff__header">
          <span className="af-diff__filename">Unified diff</span>
          <StatusPill tone="gold" label="PATCH" />
        </div>
        <pre className="af-diff__raw">{diff}</pre>
      </div>
    )
  }
  return (
    <div className="af-diff">
      <div className="af-diff__header">
        <span className="af-diff__filename">{diff.path}</span>
        <StatusPill tone={diff.isNew ? 'success' : 'gold'} label={diff.isNew ? 'NEW' : 'MODIFIED'} />
      </div>
      <div className="af-diff__content">
        {diff.hunks?.map((hunk, hi) => (
          <div key={hi} className="af-diff__hunk">
            <div className="af-diff__hunk-header">{hunk.header}</div>
            {hunk.lines.map((line, li) => (
              <div key={li} className={`af-diff__line af-diff__line--${line.type}`}>
                <span className="af-diff__line-prefix">{line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' '}</span>
                <code>{line.content}</code>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ActionQueue({ actions, busyActions, onApprove, onReject, onApproveSafeBatch, expandedActions, onToggleExpand }) {
  if (actions.length === 0) return <EmptyState icon="✓" title="No pending actions" sub="Actions proposed by Forge appear here for approval" />
  const normalized = actions.map(normalizeAction)
  const pending = normalized.filter(needsOperatorDecision)
  const safeBatch = pending.length > 0 && pending.every(canBatchApprove)
  const hasUnsafePending = pending.some(a => !canBatchApprove(a))

  return (
    <div className="af-actions">
      <div className="af-actions__header">
        <span className="af-actions__count">{pending.length} pending / {actions.length} shown</span>
        {safeBatch && <button className="af-btn af-btn--primary af-btn--sm" onClick={onApproveSafeBatch}>Approve Safe Batch</button>}
        {hasUnsafePending && <span className="af-actions__gate">Individual approval required</span>}
      </div>
      {normalized.map(action => {
        const open = needsOperatorDecision(action)
        const busy = !!busyActions[action.id]
        const isExpanded = expandedActions?.has(action.id) ?? false
        return (
        <div key={action.id} className={`af-action ${open ? '' : 'af-action--closed'} af-action--${action.type.toLowerCase()} af-action--risk-${action.risk} ${isExpanded ? 'af-action--expanded' : 'af-action--collapsed'}`}>
          <div className="af-action__rail" />
          <div className="af-action__detail">
            <button className="af-action__collapse-row" onClick={() => onToggleExpand?.(action.id)} aria-expanded={isExpanded}>
              <div className="af-action__type-badge">{action.type.toUpperCase()}</div>
              <div className="af-action__label">{action.label}</div>
              <span className={`af-action__risk af-action__risk--${action.risk}`}>{action.risk.toUpperCase()}</span>
              <span className="af-action__status">{titleize(action.status)}</span>
              <span className="af-action__expand-chevron">▶</span>
            </button>
            <div className="af-action__detail-body">
              {action.description && <div className="af-action__desc">{action.description}</div>}
              <div className="af-mini-grid">
                <MiniField label="Target" value={action.target} />
                <MiniField label="Snapshot" value={action.snapshotId} />
                <MiniField label="Approval" value={action.approval} />
                <MiniField label="Policy" value={action.policyDecision} />
                <MiniField label="Decided by" value={action.decidedBy} />
              </div>
              <MiniField label="Approval reason" value={action.approvalReason} />
              <MiniField label="Expected result" value={action.expectedResult} />
              <StructuredList title="Plan" items={action.plan} />
              <StructuredList title="Lifecycle" items={action.lifecycle} />
              <StructuredList title="Rollback" items={action.rollbackPlan} />
            </div>
          </div>
          <div className="af-action__btns">
            {open ? (
              <>
                <button className="af-btn af-btn--sm af-btn--success" disabled={busy} onClick={() => onApprove(action.id)} title="Approve and stage this action">✓</button>
                <button className="af-btn af-btn--sm af-btn--danger"  disabled={busy} onClick={() => onReject(action.id)} title="Reject this action">✕</button>
              </>
            ) : (
              <span className="af-action__locked">{titleize(action.status, 'closed')}</span>
            )}
          </div>
        </div>
      )})}
    </div>
  )
}

export function PendingApprovalsPanel({ run, onApprove, onReject, onContinue }) {
  const [busy, setBusy] = useState(null)
  if (!run || run.status !== 'waiting_approval') return null

  const pending = (run.actions || []).filter(a => a.status === 'staged' && ['auth', 'security', 'middleware', 'schema', 'migration', '.env', 'secret', 'wallet', 'payment', 'credential', 'password', 'token', 'ssl'].some(k => (a.file_path || '').toLowerCase().includes(k)))

  const doApprove = async (actionId) => {
    setBusy(actionId)
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/approve-action`, { action_id: actionId, ownerApproved: true })
      toastSuccess('Action approved')
      onApprove?.(actionId)
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  const doReject = async (actionId) => {
    setBusy(actionId)
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/reject-action`, { action_id: actionId })
      toastSuccess('Action rejected')
      onReject?.(actionId)
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  const doContinue = async () => {
    setBusy('continue')
    try {
      await JPOST_JSON(`/api/forge/runs/${run.id}/continue`, { ownerApproved: true })
      toastSuccess('Run resumed')
      onContinue?.()
    } catch (e) { toastError(e.message) } finally { setBusy(null) }
  }

  return (
    <div className="af-pending-approvals">
      <SectionLabel>PENDING APPROVALS — HIGH-RISK FILES</SectionLabel>
      <div className="af-understand__hint">These files are classified as high-risk and require your explicit approval before testing proceeds.</div>
      {pending.map(a => (
        <div key={a.id} className="af-approval-card">
          <div className="af-approval-card__header">
            <span className="af-approval-card__file">{a.file_path}</span>
            <span className={`af-agent-badge af-agent-badge--${a.risk_level === 'high' ? 'fail' : 'warn'}`}>{(a.risk_level || 'medium').toUpperCase()}</span>
            <span className="af-approval-card__type">{a.action_type || 'create'}</span>
          </div>
          {a.unified_diff && (
            <pre className="af-approval-card__diff">{a.unified_diff.split('\n').slice(0, 30).join('\n')}{a.unified_diff.split('\n').length > 30 ? '\n… (truncated)' : ''}</pre>
          )}
          <div className="af-approval-card__actions">
            <button className="af-btn af-btn--success af-btn--sm" disabled={busy === a.id} onClick={() => doApprove(a.id)}>{busy === a.id ? '…' : '✓ Approve'}</button>
            <button className="af-btn af-btn--danger af-btn--sm" disabled={busy === a.id} onClick={() => doReject(a.id)}>{busy === a.id ? '…' : '✗ Reject'}</button>
          </div>
        </div>
      ))}
      {!pending.length && <div className="af-understand__hint">All actions resolved. You can continue the run.</div>}
      <button className="af-index-btn" style={{ marginTop: 10 }} disabled={busy === 'continue' || pending.length > 0} onClick={doContinue}>
        {busy === 'continue' ? 'Resuming…' : '▶ Continue Run'}
      </button>
    </div>
  )
}

const REPLAY_ICONS = { agent_start: '▶', agent_done: '✓', patch: '📄', approval: '✋', regression: '⚡', error: '✗', command: '⌨' }
const REPLAY_COLORS = { agent_start: '#60A5FA', agent_done: '#22c55e', patch: '#E5C76B', approval: '#C084FC', regression: '#F59E0B', error: '#ef4444', command: '#20D6C7' }

export function ReplayTimeline({ runId, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    if (!runId) return
    JGET(`/api/forge/runs/${runId}/replay`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData({ ok: false }))
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) return <div className="af-understand__hint">Loading replay…</div>
  if (!data?.ok) return <div className="af-understand__hint">Replay unavailable for this run.</div>

  return (
    <div className="af-replay">
      <div className="af-replay__header">
        <SectionLabel>RUN REPLAY — {(runId || '').slice(-8)}</SectionLabel>
        {onClose && <button className="af-btn af-btn--ghost af-btn--sm" onClick={onClose}>✕ Close</button>}
      </div>
      <div className="af-replay__goal">{data.goal}</div>
      <div className="af-replay__timeline">
        {(data.timeline || []).map((e, i) => {
          const color = REPLAY_COLORS[e.type] || '#888'
          const icon = REPLAY_ICONS[e.type] || '·'
          const isOpen = expanded === i
          return (
            <div key={i} className="af-replay__event" onClick={() => setExpanded(isOpen ? null : i)}>
              <div className="af-replay__event-dot" style={{ background: color }} />
              <div className="af-replay__event-body">
                <div className="af-replay__event-header">
                  <span style={{ color }}>{icon}</span>
                  <span className="af-replay__event-type">{e.type.replace(/_/g,' ')}</span>
                  {e.iteration && <span className="af-replay__event-iter">iter {e.iteration}</span>}
                  {e.agent && <span style={{ color }}>{e.agent}</span>}
                  {e.file && <span className="af-replay__event-file">{e.file}</span>}
                  {e.status && <span className={`af-pill--${e.status === 'done' ? 'ok' : 'fail'}-sm`}>{e.status}</span>}
                  <span className="af-replay__event-ts">{e.ts ? new Date(e.ts).toLocaleTimeString() : ''}</span>
                </div>
                {isOpen && (
                  <pre className="af-replay__event-data">{JSON.stringify(e, null, 2).slice(0, 500)}</pre>
                )}
              </div>
            </div>
          )
        })}
        {!(data.timeline?.length) && <div className="af-understand__hint">No timeline events recorded for this run.</div>}
      </div>
      {data.final_report?.summary && (
        <div className="af-replay__final">
          <SectionLabel>FINAL REPORT</SectionLabel>
          <div className="af-understand__hint">{data.final_report.summary}</div>
          {data.final_report.files_changed?.length > 0 && <div className="af-agent-files-hint">Files: {data.final_report.files_changed.join(', ')}</div>}
          {data.final_report.remaining_issues?.length > 0 && <div className="af-agent-risks">Remaining: {data.final_report.remaining_issues.join(' · ')}</div>}
          {data.final_report.recommended_next_task && <div className="af-agent-risks" style={{ color: '#60A5FA' }}>Next: {data.final_report.recommended_next_task}</div>}
        </div>
      )}
    </div>
  )
}
