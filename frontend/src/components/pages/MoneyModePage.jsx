import { useEffect, useState } from 'react'
import Panel from '../nexus-ui/Panel'
import KPITile from '../nexus-ui/KPITile'
import StatusPill from '../nexus-ui/StatusPill'
import { SectionLabel } from '../nexus-ui/SectionLabel'
import { EmptyState, ErrorState } from '../nexus-ui'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'
import TaskComposer, { MONEY_PRESETS } from '../core/TaskComposer'
import './MoneyModePage.css'

const fmt$ = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(Number(v) || 0)

const fmtNum = (v) => new Intl.NumberFormat('en-US').format(Number(v) || 0)

async function fetchJson(path) {
  return api.get(path)
}

function useEconomyData() {
  const [state, setState] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const [summary, ledger, costs, pipelines, opportunities, wallet, moneyTasks] = await Promise.all([
          fetchJson('/api/economy/summary').catch((e) => ({ state: 'degraded', error: e.message })),
          fetchJson('/api/economy/ledger').catch(() => ({ items: [] })),
          fetchJson('/api/economy/costs').catch(() => ({ items: [] })),
          fetchJson('/api/economy/pipelines').catch(() => ({ pipelines: [] })),
          fetchJson('/api/economy/opportunities').catch(() => ({ opportunities: [] })),
          fetchJson('/api/economy/wallet').catch(() => ({ wallet: { configured: false, state: 'degraded' } })),
          fetchJson('/api/money/tasks').catch(() => ({ tasks: [], policy: null })),
        ])
        if (alive) setState({ loading: false, error: summary.error || null, data: { summary, ledger, costs, pipelines, opportunities, wallet, moneyTasks } })
      } catch (err) {
        if (alive) setState({ loading: false, error: err.message, data: null })
      }
    }
    load()
    const id = setInterval(load, 15000)
    return () => { alive = false; clearInterval(id) }
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
          <span className="ecc-pipeline-card__metric-val ecc-pipeline-card__metric-val--muted">{pipeline.last_run_at ? new Date(pipeline.last_run_at).toLocaleString() : 'never'}</span>
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
              <button className="ecc-action-btn ecc-action-btn--primary" onClick={() => setActiveSection('setup')}>Open Setup</button>
              <button className="ecc-action-btn" onClick={() => setActiveSection('integrations')}>Check Integrations</button>
              <button className="ecc-action-btn" onClick={() => setActiveSection('approvals')}>Approval Inbox</button>
              <button className="ecc-action-btn" onClick={() => setActiveSection('proof')}>Proof Center</button>
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
                <button className="ecc-action-btn ecc-action-btn--sm" onClick={() => setActiveSection('integrations')}>Configure Sources</button>
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
              { key: 'created_at', label: 'Created', render: (r) => r.created_at ? new Date(r.created_at).toLocaleString() : '-' },
            ]}
          />
        </Panel>
      </section>
    </div>
  )
}
