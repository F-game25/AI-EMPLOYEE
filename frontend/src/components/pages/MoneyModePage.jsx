import { useEffect, useRef, useState } from 'react'
import Panel from '../nexus-ui/Panel'
import KPITile from '../nexus-ui/KPITile'
import StatusPill from '../nexus-ui/StatusPill'
import { SectionLabel } from '../nexus-ui/SectionLabel'
import { EmptyState, ErrorState, NxButton } from '../nexus-ui'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'
import TaskComposer, { MONEY_PRESETS } from '../core/TaskComposer'
import { fmtCurrency, fmtNumber, fmtDate } from '../../utils/format'
import './MoneyModePage.css'

const fmt$ = (v) => fmtCurrency(v, { compact: false })
const fmtNum = (v) => fmtNumber(v, { compact: false })

async function fetchJson(path) {
  return api.get(path)
}

function useEconomyData() {
  const [state, setState] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [summary, ledger, costs, pipelines, opportunities, wallet, moneyTasks, contentLog, outreachLog] = await Promise.all([
          fetchJson('/api/economy/summary').catch((e) => ({ state: 'degraded', error: e.message })),
          fetchJson('/api/economy/ledger').catch(() => ({ items: [] })),
          fetchJson('/api/economy/costs').catch(() => ({ items: [] })),
          fetchJson('/api/economy/pipelines').catch(() => ({ pipelines: [] })),
          fetchJson('/api/economy/opportunities').catch(() => ({ opportunities: [] })),
          fetchJson('/api/economy/wallet').catch(() => ({ wallet: { configured: false, state: 'degraded' } })),
          fetchJson('/api/money/tasks').catch(() => ({ tasks: [], policy: null })),
          fetchJson('/api/money/content-log').catch(() => ({ entries: [] })),
          fetchJson('/api/money/outreach-log').catch(() => ({ entries: [] })),
        ])
        if (alive) setState({ loading: false, error: summary.error || null, data: { summary, ledger, costs, pipelines, opportunities, wallet, moneyTasks, contentLog, outreachLog } })
      } catch (err) {
        if (alive) setState({ loading: false, error: err.message, data: null })
      }
    }
    load()
    const id = setInterval(load, 30000)
    const onEconomyUpdate = () => load()
    window.addEventListener('economy:update', onEconomyUpdate)
    window.addEventListener('ws:event', (e) => { if (e.detail?.type?.startsWith('economy:') || e.detail?.type?.startsWith('money:')) onEconomyUpdate() })
    return () => { alive = false; clearInterval(id); window.removeEventListener('economy:update', onEconomyUpdate) }
  }, [])
  return state
}

function SimpleTable({ rows, columns, emptyTitle }) {
  if (!rows.length) return <EmptyState icon="[]" title={emptyTitle} sub="No persisted records exist yet." />
  return (
    <table className="ecc-token-table">
      <thead>
        <tr>{columns.map((col) => <th key={col.key} className="ecc-token-table__th">{col.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={row.id || index} className="ecc-token-table__row">
            {columns.map((col) => <td key={col.key} className="ecc-token-table__op">{col.render ? col.render(row) : row[col.key] || '-'}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PipelineCard({ pipeline }) {
  return (
    <div className="ecc-pipeline-card">
      <div className="ecc-pipeline-card__head">
        <span className="ecc-pipeline-card__name">{pipeline.name || pipeline.id}</span>
        <StatusPill label={(pipeline.status || 'idle').toUpperCase()} tone={pipeline.status === 'active' ? 'success' : 'idle'} size="sm" />
      </div>
      <div className="ecc-pipeline-card__metrics">
        <div className="ecc-pipeline-card__metric">
          <span className="ecc-pipeline-card__metric-label">Runs</span>
          <span className="ecc-pipeline-card__metric-val">{fmtNum(pipeline.runs || 0)}</span>
        </div>
        <div className="ecc-pipeline-card__metric">
          <span className="ecc-pipeline-card__metric-label">Value</span>
          <span className="ecc-pipeline-card__metric-val">{fmt$(pipeline.value || 0)}</span>
        </div>
        <div className="ecc-pipeline-card__metric">
          <span className="ecc-pipeline-card__metric-label">Last Run</span>
          <span className="ecc-pipeline-card__metric-val ecc-pipeline-card__metric-val--muted">{pipeline.last_run_at ? fmtDate(pipeline.last_run_at, { time: true }) : 'never'}</span>
        </div>
      </div>
    </div>
  )
}

function WalletPanel({ wallet }) {
  const w = wallet?.wallet || wallet || {}
  return (
    <Panel
      title="OWNER WALLET VAULT"
      icon="$"
      tone="gold"
      size="compact"
      actions={<StatusPill label={w.configured ? 'CONFIGURED' : 'OWNER SETUP'} tone={w.configured ? 'success' : 'warn'} size="sm" />}
    >
      <div className="ecc-wallet-vault">
        <div className="ecc-wallet-vault__balance">{fmt$(w.balance?.available || w.available || 0)}</div>
        <div className="ecc-wallet-vault__meta">
          <span>{w.address || 'Encrypted local owner vault is not configured.'}</span>
          <span>Claim, spend, wallet and external compute actions require owner approval.</span>
          <span>Autonomous spending is blocked.</span>
        </div>
      </div>
    </Panel>
  )
}

const STATUS_TONE = {
  draft: 'warn',
  published: 'success',
  template: 'idle',
  sent: 'success',
  pending_approval: 'warn',
}

function ContentCalendarPanel({ entries = [] }) {
  return (
    <Panel title="CONTENT CALENDAR" icon="[]" tone="gold" size="compact" actions={<StatusPill label={entries.length ? `${entries.length} ENTRIES` : 'EMPTY'} tone={entries.length ? 'success' : 'idle'} size="sm" />}>
      <div className="ecc-native-list">
        {entries.length ? entries.slice(0, 8).map((e, i) => (
          <div key={e.id || i} className="ecc-native-row">
            <div style={{ flex: 1, minWidth: 0 }}>
              <span className="ecc-native-row__title">{e.topic || e.title || 'Untitled'}</span>
              <span className="ecc-native-row__sub">
                {e.type && <span style={{ marginRight: 6 }}>{e.type}</span>}
                {e.format && <span style={{ marginRight: 6 }}>{e.format}</span>}
                {e.word_count ? `${e.word_count} words · ` : ''}{fmtDate(e.timestamp || e.created_at, { time: true })}
              </span>
            </div>
            <StatusPill label={(e.status || 'draft').toUpperCase()} tone={STATUS_TONE[e.status] || 'idle'} size="sm" />
          </div>
        )) : (
          <div className="ecc-native-empty">No content published yet</div>
        )}
      </div>
    </Panel>
  )
}

function ROITrackingPanel({ summary = {}, pipelines = [] }) {
  const revenue = Number(summary.revenue || summary.total_revenue || 0)
  const cost = Number(summary.cost || summary.total_cost || 0)
  const profit = summary.profit != null ? Number(summary.profit) : revenue - cost
  const roi = cost > 0 ? (profit / cost) * 100 : 0
  const profitColor = profit >= 0 ? 'var(--nx-success)' : 'var(--nx-danger)'
  return (
    <Panel title="ROI TRACKING" icon="%" tone="gold" size="compact">
      {!revenue && !cost && !pipelines.length ? (
        <div className="ecc-native-empty">No economy data</div>
      ) : (
        <>
          <div className="ecc-roi-grid">
            <div className="ecc-roi-stat">
              <span className="ecc-roi-stat__label">REVENUE</span>
              <span className="ecc-roi-stat__val">{fmt$(revenue)}</span>
            </div>
            <div className="ecc-roi-stat">
              <span className="ecc-roi-stat__label">COSTS</span>
              <span className="ecc-roi-stat__val">{fmt$(cost)}</span>
            </div>
            <div className="ecc-roi-stat">
              <span className="ecc-roi-stat__label">PROFIT</span>
              <span className="ecc-roi-stat__val" style={{ color: profitColor }}>{fmt$(profit)}</span>
            </div>
            <div className="ecc-roi-stat">
              <span className="ecc-roi-stat__label">ROI</span>
              <span className="ecc-roi-stat__val" style={{ color: profitColor }}>{roi.toFixed(1)}%</span>
            </div>
          </div>
          {pipelines.length > 0 && (
            <table className="ecc-token-table" style={{ marginTop: 'var(--nx-s-3)' }}>
              <thead>
                <tr>
                  <th className="ecc-token-table__th">Pipeline</th>
                  <th className="ecc-token-table__th">Revenue</th>
                  <th className="ecc-token-table__th">Cost</th>
                  <th className="ecc-token-table__th">Status</th>
                </tr>
              </thead>
              <tbody>
                {pipelines.map((p, i) => (
                  <tr key={p.id || p.name || i} className="ecc-token-table__row">
                    <td className="ecc-token-table__op">{p.name || p.id || '-'}</td>
                    <td className="ecc-token-table__op">{fmt$(p.revenue || p.value || 0)}</td>
                    <td className="ecc-token-table__op">{fmt$(p.cost || 0)}</td>
                    <td className="ecc-token-table__op">{p.status || 'idle'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Panel>
  )
}

function OutreachStatusPanel({ entries = [] }) {
  return (
    <Panel title="OUTREACH STATUS" icon="@" tone="gold" size="compact" actions={<StatusPill label={entries.length ? `${entries.length} RECORDS` : 'EMPTY'} tone={entries.length ? 'success' : 'idle'} size="sm" />}>
      <div className="ecc-native-list">
        {entries.length ? entries.slice(0, 8).map((e, i) => (
          <div key={e.id || i} className="ecc-native-row">
            <div style={{ flex: 1, minWidth: 0 }}>
              <span className="ecc-native-row__title">{e.recipient_name || e.recipient || e.email || 'Unknown'}</span>
              <span className="ecc-native-row__sub">{fmtDate(e.timestamp || e.sent_at || e.created_at, { time: true })}</span>
            </div>
            <StatusPill label={(e.status || 'draft').toUpperCase()} tone={STATUS_TONE[e.status] || 'idle'} size="sm" />
          </div>
        )) : (
          <div className="ecc-native-empty">No outreach drafted yet</div>
        )}
      </div>
    </Panel>
  )
}

// ── Pipeline Builder — end-to-end money workflow ──────────────────────────────
const PIPELINE_STEPS = [
  { id: 'niche',    label: 'Niche Research',  api: '/api/money/niche-research',  icon: '🔍', desc: 'Discover profitable niches and validate demand' },
  { id: 'offer',    label: 'Offer Creation',  api: '/api/money/offer-creation',  icon: '📦', desc: 'Design a sellable offer from niche insights' },
  { id: 'calendar', label: 'Content Plan',    api: '/api/money/content-calendar', icon: '📅', desc: 'Build a content calendar to attract clients' },
  { id: 'leads',    label: 'Lead Research',   api: '/api/money/lead-research',   icon: '👤', desc: 'Find potential clients (approval required before outreach)' },
  { id: 'proposal', label: 'Proposal Draft',  api: '/api/money/proposal',        icon: '📝', desc: 'Generate a proposal — human must approve before sending' },
]

const STEP_STATUS = { idle: 'idle', running: 'running', done: 'done', error: 'error', blocked: 'blocked' }

function StepCard({ step, status, result, error, onRun, disabled, isActive }) {
  const [open, setOpen] = useState(false)
  const statusColors = { idle: '#9a927e', running: '#e89a4f', done: '#22c55e', error: '#ef4444', blocked: '#f59e0b' }
  const statusIcons  = { idle: '○', running: '●', done: '✓', error: '✗', blocked: '!' }
  const c = statusColors[status] || '#9a927e'

  return (
    <div style={{ border: `1px solid ${c}33`, borderLeft: `3px solid ${c}`, borderRadius: 6, marginBottom: 8, background: isActive ? 'rgba(229,199,107,0.04)' : 'rgba(0,0,0,0.2)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px' }}>
        <span style={{ fontSize: 16 }}>{step.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#ecead8', fontFamily: 'Inter, sans-serif' }}>{step.label}</div>
          <div style={{ fontSize: 11, color: '#9a927e', fontFamily: 'monospace' }}>{step.desc}</div>
        </div>
        <span style={{ color: c, fontSize: 12, fontFamily: 'monospace', marginRight: 8 }}>
          {statusIcons[status]} {status.toUpperCase()}
        </span>
        {result && <NxButton variant="ghost" size="sm" onClick={() => setOpen(o => !o)}>{open ? 'HIDE' : 'VIEW'}</NxButton>}
        <NxButton
          variant="primary"
          size="sm"
          onClick={onRun}
          loading={status === 'running'}
          disabled={disabled || status === 'running'}
        >{status === 'done' ? '↺ RE-RUN' : '▶ RUN'}</NxButton>
      </div>
      {error && <div style={{ padding: '0 14px 8px', fontSize: 11, color: '#ef4444', fontFamily: 'monospace' }}>{error}</div>}
      {open && result && (
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', padding: '10px 14px', maxHeight: 200, overflowY: 'auto' }}>
          <pre style={{ fontSize: 10, color: '#9a927e', fontFamily: 'monospace', whiteSpace: 'pre-wrap', margin: 0 }}>
            {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function PipelineBuilder() {
  const [context, setContext]   = useState('')
  const [statuses, setStatuses] = useState({})  // stepId → STEP_STATUS
  const [results, setResults]   = useState({})
  const [errors, setErrors]     = useState({})
  const [activeStep, setActiveStep] = useState(null)
  const token = () => sessionStorage.getItem('ai_jwt') || ''

  const runStep = async (step, ctxOverride) => {
    const ctx = ctxOverride ?? context
    if (!ctx.trim()) return
    setStatuses(s => ({ ...s, [step.id]: 'running' }))
    setErrors(e => ({ ...e, [step.id]: null }))
    setActiveStep(step.id)
    try {
      const prevResults = Object.fromEntries(
        PIPELINE_STEPS.filter(s => results[s.id]).map(s => [s.id, results[s.id]])
      )
      const res = await fetch(step.api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ context: ctx, previous_results: prevResults }),
      })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
      setResults(r => ({ ...r, [step.id]: data }))
      setStatuses(s => ({ ...s, [step.id]: data.requires_approval ? 'blocked' : 'done' }))
    } catch (e) {
      setErrors(err => ({ ...err, [step.id]: e.message }))
      setStatuses(s => ({ ...s, [step.id]: 'error' }))
    } finally {
      setActiveStep(null)
    }
  }

  const runAll = async () => {
    if (!context.trim()) return
    for (const step of PIPELINE_STEPS) {
      await runStep(step)
    }
  }

  const doneCount = PIPELINE_STEPS.filter(s => statuses[s.id] === 'done').length

  return (
    <Panel title="PIPELINE BUILDER" icon="▶" tone="gold" size="compact"
      actions={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {doneCount > 0 && <StatusPill label={`${doneCount}/${PIPELINE_STEPS.length} DONE`} tone="success" size="sm" />}
          <NxButton
            variant="primary"
            size="sm"
            onClick={runAll}
            loading={!!activeStep}
            disabled={!context.trim() || !!activeStep}
          >▶▶ RUN ALL</NxButton>
        </div>
      }
    >
      <div style={{ padding: '12px 14px' }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, letterSpacing: '0.12em', color: '#e5c76b', fontFamily: 'monospace', textTransform: 'uppercase', marginBottom: 6 }}>Your context / skills / goal</div>
          <textarea
            value={context}
            onChange={e => setContext(e.target.value)}
            placeholder="Describe yourself, your skills, your target market, or your income goal. The pipeline will use this throughout."
            rows={3}
            style={{ width: '100%', background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(229,199,107,0.18)', borderRadius: 4, color: '#ecead8', fontSize: 12, fontFamily: 'monospace', padding: '8px 10px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ fontSize: 10, color: '#9a927e', fontFamily: 'monospace', marginBottom: 10 }}>
          Run steps individually or use RUN ALL. Steps build on each other — earlier results are passed as context. Outreach and proposals require human approval before sending.
        </div>
        {PIPELINE_STEPS.map((step, i) => {
          const prevDone = i === 0 || statuses[PIPELINE_STEPS[i - 1].id] === 'done'
          return (
            <StepCard
              key={step.id}
              step={step}
              status={statuses[step.id] || 'idle'}
              result={results[step.id]}
              error={errors[step.id]}
              isActive={activeStep === step.id}
              disabled={!context.trim() || !!activeStep}
              onRun={() => runStep(step)}
            />
          )
        })}
      </div>
    </Panel>
  )
}

export default function MoneyModePage() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const { loading, error, data } = useEconomyData()
  const summary = data?.summary || {}
  const ledger = data?.ledger?.items || data?.ledger?.ledger || []
  const costs = data?.costs?.items || data?.costs?.costs || []
  const pipelines = data?.pipelines?.pipelines || []
  const opportunities = data?.opportunities?.opportunities || []
  const tasks = data?.moneyTasks?.tasks || []
  const policy = data?.moneyTasks?.policy || {}
  const contentEntries = data?.contentLog?.entries || []
  const outreachEntries = data?.outreachLog?.entries || []

  const revenue = summary.revenue || summary.total_revenue || 0
  const cost = summary.cost || summary.total_cost || 0
  const profit = summary.profit ?? (revenue - cost)
  const tokenCost = summary.token_cost || costs.reduce((acc, item) => acc + (Number(item.cost) || 0), 0)
  const roi = cost > 0 ? (profit / cost) * 100 : 0
  const needsFirstRunSetup = !loading && !tasks.length && !pipelines.length && !opportunities.length && !ledger.length

  return (
    <div className="ecc-page" role="main" aria-label="Economy Command Center">
      <header className="ecc-titlebar">
        <div className="ecc-titlebar__left">
          <span className="ecc-titlebar__icon" aria-hidden="true">$</span>
          <h1 className="ecc-titlebar__title">ECONOMY COMMAND CENTER</h1>
          <div className="ecc-titlebar__divider" aria-hidden="true" />
          <span className="ecc-titlebar__sub">Real ledger, wallet, task value and approval gates</span>
        </div>
        <div className="ecc-titlebar__right">
          <StatusPill label={(summary.state || (error ? 'degraded' : 'live')).toUpperCase()} tone={error ? 'alert' : 'gold'} dot={!error} />
          <span className="ecc-titlebar__ts">{new Date().toLocaleTimeString()}</span>
        </div>
      </header>

      {loading && <EmptyState icon="..." title="Loading economy state" />}
      {error && <ErrorState title="Economy degraded" message={error} />}
      {needsFirstRunSetup && (
        <Panel
          title="MONEY MODE SETUP REQUIRED"
          icon="!"
          tone="gold"
          size="compact"
          actions={<StatusPill label="NO LIVE SOURCES" tone="warn" size="sm" />}
        >
          <div className="ecc-guided-setup">
            <div>
              <strong>Money Mode has no active task sources, pipelines, opportunities, or ledger proof yet.</strong>
              <span>Configure providers first, then run a safe draft task. Publishing, outreach, wallet use, spending, and paid-task acceptance stay approval-gated.</span>
            </div>
            <div className="ecc-guided-setup__actions" aria-label="Money Mode setup actions">
              <NxButton variant="primary" onClick={() => setActiveSection('setup')}>Open Setup</NxButton>
              <NxButton variant="ghost" onClick={() => setActiveSection('integrations')}>Check Integrations</NxButton>
              <NxButton variant="ghost" onClick={() => setActiveSection('approvals')}>Approval Inbox</NxButton>
              <NxButton variant="ghost" onClick={() => setActiveSection('proof')}>Proof Center</NxButton>
            </div>
          </div>
        </Panel>
      )}

      <section className="ecc-kpi-strip" aria-label="Key performance indicators">
        <KPITile label="TRACKED VALUE" value={<span className="ecc-tabular">{fmt$(revenue)}</span>} icon="$" iconTone="gold" accent hover sub="persisted ledger" />
        <KPITile label="COST" value={<span className="ecc-tabular">{fmt$(cost)}</span>} icon="-" iconTone="warn" hover sub="tracked spend" />
        <KPITile label="PROFIT" value={<span className="ecc-tabular">{fmt$(profit)}</span>} icon="+" iconTone={profit >= 0 ? 'success' : 'warn'} hover sub="value minus cost" />
        <KPITile label="ROI" value={<span className="ecc-tabular">{roi.toFixed(1)}%</span>} icon="%" iconTone={roi >= 0 ? 'success' : 'warn'} hover sub="real data only" />
        <KPITile label="TOKEN COST" value={<span className="ecc-tabular">{fmt$(tokenCost)}</span>} icon="T" iconTone="warn" hover sub="from call logs" />
      </section>

      <div className="ecc-enhance-grid">
        <TaskComposer
          title="START MONEY TASK"
          subtitle="Draft, evaluate, and prepare work. Risky execution pauses for approval."
          presets={MONEY_PRESETS}
          placeholder="Example: find 3 service offers I can sell this week using my existing skills."
          source="money-mode-composer"
        />
        <Panel title="MONEY MODE TASK INBOX" icon="[]" tone="gold" size="compact" actions={<StatusPill label={tasks.length ? `${tasks.length} TASKS` : 'EMPTY'} tone={tasks.length ? 'success' : 'idle'} size="sm" />}>
          <div className="ecc-native-list">
            {tasks.slice(0, 5).map((task) => (
              <div key={task.id} className="ecc-native-row">
                <div>
                  <span className="ecc-native-row__title">{task.title || task.id}</span>
                  <span className="ecc-native-row__sub">{task.source || 'internal'} - {task.estimated_hours || 0}h - {task.risk || 'standard'}</span>
                </div>
                <StatusPill label={(task.state || 'draft').toUpperCase()} tone={task.risk === 'dangerous' ? 'warn' : 'idle'} size="sm" />
              </div>
            ))}
            {!tasks.length && (
              <div className="ecc-native-empty ecc-native-empty--guided">
                <span>No task sources are active. Discovery is disabled until configured by the owner.</span>
                <NxButton variant="ghost" size="sm" onClick={() => setActiveSection('integrations')}>Configure Sources</NxButton>
              </div>
            )}
          </div>
        </Panel>
        <WalletPanel wallet={data?.wallet} />
        <Panel title="APPROVAL GATES" icon="!" tone="gold" size="compact" actions={<StatusPill label={policy.state?.toUpperCase?.() || 'POLICY'} tone="success" size="sm" />}>
          <div className="ecc-approval-gates">
            {(policy.approval_gates || ['accept_paid_task', 'deliver_client_work', 'claim_funds', 'spend_money', 'buy_external_compute']).map((gate) => (
              <span key={gate} className="ecc-approval-gate">{gate.replace(/_/g, ' ')}</span>
            ))}
          </div>
        </Panel>
      </div>

      <PipelineBuilder />

      <div className="ecc-mid-row">
        <Panel title="PIPELINES" icon="[]" tone="gold" size="compact" className="ecc-pipeline-panel">
          <div className="ecc-pipeline-list">
            {pipelines.map((pipeline) => <PipelineCard key={pipeline.id || pipeline.name} pipeline={pipeline} />)}
            {!pipelines.length && <EmptyState icon="[]" title="No active pipelines" sub="Content, data and outreach pipelines will appear after first real run." />}
          </div>
        </Panel>
        <Panel title="OPPORTUNITIES" icon="+" tone="gold" size="compact" className="ecc-chart-panel">
          <SimpleTable
            rows={opportunities}
            emptyTitle="No opportunities"
            columns={[
              { key: 'title', label: 'Opportunity' },
              { key: 'source', label: 'Source' },
              { key: 'estimated_value', label: 'Value', render: (r) => fmt$(r.estimated_value || r.value) },
              { key: 'state', label: 'State' },
            ]}
          />
        </Panel>
      </div>

      <Panel title="TOKEN/API COSTS" icon="T" tone="gold" size="compact" className="ecc-token-panel">
        <SimpleTable
          rows={costs}
          emptyTitle="No cost history"
          columns={[
            { key: 'operation', label: 'Operation' },
            { key: 'tokens', label: 'Tokens', render: (r) => fmtNum(r.tokens) },
            { key: 'cost', label: 'Cost', render: (r) => fmt$(r.cost) },
            { key: 'provider', label: 'Provider' },
          ]}
        />
      </Panel>

      <section aria-label="Ledger">
        <SectionLabel icon="$" tone="gold" rule>LEDGER</SectionLabel>
        <Panel title="REAL ECONOMY LEDGER" icon="$" tone="gold" size="compact">
          <SimpleTable
            rows={ledger}
            emptyTitle="No ledger records"
            columns={[
              { key: 'type', label: 'Type' },
              { key: 'amount', label: 'Amount', render: (r) => fmt$(r.amount || r.value) },
              { key: 'status', label: 'Status' },
              { key: 'created_at', label: 'Created', render: (r) => fmtDate(r.created_at, { time: true }) },
            ]}
          />
        </Panel>
      </section>

      <section aria-label="Money Mode Tracking Panels">
        <SectionLabel icon="[]" tone="gold" rule>MONEY MODE TRACKING</SectionLabel>
        <div className="ecc-tracking-grid">
          <ContentCalendarPanel entries={contentEntries} />
          <ROITrackingPanel summary={summary} pipelines={pipelines} />
          <OutreachStatusPanel entries={outreachEntries} />
        </div>
      </section>
    </div>
  )
}
