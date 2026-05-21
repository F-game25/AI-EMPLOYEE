import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxToggle, NxSaveBtn } from './controls'

/* ── Tab 8: BILLING & USAGE ────────────────────────────────────────────── */

function PieChart({ slices }) {
  // slices: [{ label, pct, color }]
  let angle = 0
  const segments = slices.map(s => {
    const start = angle
    angle += (s.pct / 100) * 360
    return { ...s, start, end: angle }
  })

  const toXY = deg => {
    const rad = (deg - 90) * Math.PI / 180
    return { x: 50 + 40 * Math.cos(rad), y: 50 + 40 * Math.sin(rad) }
  }

  const describeArc = (start, end) => {
    if (end - start >= 360) end = start + 359.99
    const s = toXY(start), e = toXY(end)
    const large = end - start > 180 ? 1 : 0
    return `M 50 50 L ${s.x} ${s.y} A 40 40 0 ${large} 1 ${e.x} ${e.y} Z`
  }

  return (
    <div className="nx-billing-pie-wrap">
      <svg viewBox="0 0 100 100" className="nx-billing-pie">
        {segments.map(s => <path key={s.label} d={describeArc(s.start, s.end)} fill={s.color} opacity={0.85} />)}
        <circle cx="50" cy="50" r="22" fill="var(--nx-bg-deep)" />
      </svg>
      <div className="nx-billing-legend">
        {slices.map(s => (
          <div key={s.label} className="nx-billing-legend-row">
            <span className="nx-billing-legend-dot" style={{ background: s.color }} />
            <span className="nx-billing-legend-label">{s.label}</span>
            <span className="nx-billing-legend-pct">{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const MODEL_COLORS = ['#e5c76b', '#20d6c7', '#ef4444', '#a78bfa', '#fb923c', '#34d399']

function BillingTab() {
  const [spend, setSpend] = useState(0)
  const [budget, setBudget] = useState(500)
  const [editBudget, setEditBudget] = useState(false)
  const [draftBudget, setDraftBudget] = useState(500)
  const [agentRows, setAgentRows] = useState([])
  const [hardCap, setHardCap] = useState(false)
  const [softWarn, setSoftWarn] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/api/intelligence/llm-calls').then(d => {
      const calls = Array.isArray(d?.calls) ? d.calls : Array.isArray(d) ? d : []
      const agg = {}
      calls.forEach(c => {
        const key = `${c.agent}|${c.model}`
        if (!agg[key]) agg[key] = { agent: c.agent, model: c.model, tokens: 0, cost: 0 }
        agg[key].tokens += c.tokens || 0
        agg[key].cost   += c.cost   || 0
      })
      const rows = Object.values(agg).sort((a, b) => b.cost - a.cost).slice(0, 10)
      setAgentRows(rows)
      setSpend(rows.reduce((s, r) => s + r.cost, 0))
    }).catch(() => {})
    api.get('/api/settings/billing').then(d => {
      if (d?.budget) { setBudget(d.budget); setDraftBudget(d.budget) }
      if (d?.hard_cap != null) setHardCap(d.hard_cap)
      if (d?.soft_warn != null) setSoftWarn(d.soft_warn)
    }).catch(() => {})
  }, [])

  const saveBilling = async () => {
    setSaving(true)
    await api.put('/api/settings/billing', { budget, hard_cap: hardCap, soft_warn: softWarn }).catch(() => {})
    setSaving(false); setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const spendPct = Math.min((spend / budget) * 100, 100)

  // Model pie
  const modelTotals = {}
  agentRows.forEach(r => { modelTotals[r.model] = (modelTotals[r.model] || 0) + r.cost })
  const total = Object.values(modelTotals).reduce((s, v) => s + v, 0) || 1
  const pieSlices = Object.entries(modelTotals).map(([label, cost], i) => ({
    label, pct: (cost / total) * 100, color: MODEL_COLORS[i % MODEL_COLORS.length]
  }))

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">SPEND THIS MONTH</div>
        <div className="nx-billing-hero">
          <div className="nx-billing-spend">
            <span className="nx-billing-amount">${spend.toFixed(2)}</span>
            <span className="nx-billing-budget-label"> / </span>
            {editBudget ? (
              <div className="nx-billing-budget-edit">
                <span>$</span>
                <input className="nx-input nx-input--sm" type="number" min={0} value={draftBudget}
                  onChange={e => setDraftBudget(+e.target.value)} style={{ width: 90 }} />
                <button className="nx-save-btn" onClick={() => { setBudget(draftBudget); setEditBudget(false) }}>SET</button>
              </div>
            ) : (
              <button className="nx-billing-budget-btn" onClick={() => setEditBudget(true)}>
                ${budget.toFixed(2)} budget <span className="nx-billing-edit-icon">✎</span>
              </button>
            )}
          </div>
          <div className="nx-billing-bar-wrap">
            <div className="nx-billing-bar">
              <div className="nx-billing-bar-fill"
                style={{ width: `${spendPct}%`, background: spendPct > 90 ? '#ef4444' : spendPct > 80 ? '#fb923c' : 'var(--nx-gold)' }} />
            </div>
            <span className="nx-billing-bar-pct">{spendPct.toFixed(1)}% of budget</span>
          </div>
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PER-AGENT SPEND (TOP 10)</div>
        <div className="nx-sec-table-wrap">
          <div className="nx-sec-thead nx-sec-thead--billing">
            <span>Agent</span><span>Model</span><span>Tokens</span><span>Cost</span><span>% Budget</span>
          </div>
          {agentRows.length === 0 && <div className="nx-sec-empty">No LLM call data yet</div>}
          {agentRows.map((r, i) => (
            <div key={i} className="nx-sec-row nx-sec-row--billing">
              <span className="nx-sec-name">{r.agent || '—'}</span>
              <span className="nx-sec-mono">{r.model || '—'}</span>
              <span className="nx-sec-muted">{r.tokens.toLocaleString()}</span>
              <span className="nx-sec-muted">${r.cost.toFixed(4)}</span>
              <span className="nx-sec-muted">{((r.cost / budget) * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PER-MODEL BREAKDOWN</div>
        {pieSlices.length > 0 ? <PieChart slices={pieSlices} /> : <div className="nx-sec-empty">No model data yet</div>}
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">BUDGET CONTROLS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">HARD CAP</span>
              <span className="nx-toggle-desc">Pause all LLM execution when monthly budget limit is reached</span>
            </div>
            <NxToggle checked={hardCap} onChange={setHardCap} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">SOFT WARNING AT 80%</span>
              <span className="nx-toggle-desc">Send an alert notification when spend reaches 80% of budget</span>
            </div>
            <NxToggle checked={softWarn} onChange={setSoftWarn} />
          </div>
        </div>
        <NxSaveBtn label="SAVE BILLING SETTINGS" saving={saving} saved={saved} onClick={saveBilling} />
      </div>
    </div>
  )
}

export default BillingTab
