import { textFrom } from './helpers'

/* ─── Shared display primitives used across Forge panes ───────────────── */

export function MiniField({ label, value }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="af-mini-field">
      <span>{label}</span>
      <strong>{textFrom(value)}</strong>
    </div>
  )
}

export function StructuredList({ title, items }) {
  const list = Array.isArray(items) ? items : items ? [items] : []
  if (list.length === 0) return null
  return (
    <div className="af-structured">
      <div className="af-structured__title">{title}</div>
      {list.slice(0, 6).map((item, i) => (
        <div key={i} className="af-structured__item">
          <span className="af-structured__idx">{i + 1}</span>
          <span>{typeof item === 'string' ? item : textFrom(item.label || item.title || item.step || item.name || item)}</span>
          {typeof item === 'object' && item?.status && <em>{item.status}</em>}
        </div>
      ))}
    </div>
  )
}

export function StructuredMessageBlock({ data }) {
  if (!data) return null
  const plan = data.plan || data.steps || data.execution_plan
  const lifecycle = data.lifecycle || data.action_lifecycle || data.gates
  const status = data.status || data.state
  const snapshot = data.snapshot_id || data.snapshot
  const policyDecision = data.policy_decision || data.policyDecision
  if (!plan && !lifecycle && !status && !snapshot && !policyDecision) return null
  return (
    <div className="af-msg-structured">
      <div className="af-mini-grid">
        <MiniField label="Status" value={status} />
        <MiniField label="Snapshot" value={snapshot} />
        <MiniField label="Policy" value={policyDecision} />
      </div>
      <StructuredList title="Plan" items={plan} />
      <StructuredList title="Lifecycle" items={lifecycle} />
    </div>
  )
}
