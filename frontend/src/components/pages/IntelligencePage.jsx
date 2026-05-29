import { useState, useEffect } from 'react'
import { Panel, SectionLabel } from '../nexus-ui'
import { useLiveData } from '../../hooks/useLiveData'
import { useAgentStore } from '../../store/agentStore'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import api from '../../api/client'
import './IntelligencePage.css'

/* ── Tab 1: Agent Fleet Summary ─────────────────────────────────────────────── */
function FleetTab() {
  const agents = useAgentStore(s => s.agents) || []
  const { data: agentData } = useLiveData({
    endpoint: '/api/agents/list',
    wsEvent: 'agent:status',
    pollMs: 10000,
    transform: d => d?.agents || d,
  })
  const list = (agentData || agents || []).slice(0, 24)

  const running  = list.filter(a => a.status === 'running').length
  const idle     = list.filter(a => a.status === 'idle').length
  const error    = list.filter(a => a.status === 'error').length

  return (
    <div className="int-tab-content">
      <div className="int-kpi-row">
        {[
          { label: 'Running',  val: running,      color: 'var(--nx-success)' },
          { label: 'Idle',     val: idle,         color: 'var(--nx-text-dim)' },
          { label: 'Erroring', val: error,        color: 'var(--nx-danger)' },
          { label: 'Total',    val: list.length,  color: 'var(--nx-gold)' },
        ].map(({ label, val, color }) => (
          <Panel key={label} className="int-kpi-tile">
            <SectionLabel>{label}</SectionLabel>
            <div className="int-kpi-big" style={{ color }}>{val}</div>
          </Panel>
        ))}
      </div>

      <Panel title="Agent Fleet">
        {list.length === 0 ? (
          <div className="int-empty">No agents loaded — start the system to see fleet status</div>
        ) : (
          <div className="int-fleet-grid">
            {list.map(agent => (
              <div key={agent.id || agent.name} className={`int-fleet-tile int-fleet-tile--${agent.status || 'idle'}`}>
                <div className="int-fleet-tile__name">{agent.name || agent.id}</div>
                <div className="int-fleet-tile__status">{agent.status || 'idle'}</div>
                {agent.task && <div className="int-fleet-tile__task">{agent.task}</div>}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

/* ── Tab 2: Brain / Reasoning Inspector ─────────────────────────────────────── */
function BrainInspectorTab() {
  const { data: calls, refresh } = useLiveData({
    endpoint: '/api/intelligence/llm-calls',
    wsEvent: 'llm:call',
    pollMs: 5000,
    transform: d => d?.calls || d,
  })
  const [selected, setSelected] = useState(null)
  const list = Array.isArray(calls) ? calls : []

  // Per-agent cost breakdown
  const agentCosts = {}
  list.forEach(c => { agentCosts[c.agent] = (agentCosts[c.agent] || 0) + (c.cost_usd || 0) })
  const costEntries = Object.entries(agentCosts).sort((a, b) => b[1] - a[1])
  const maxCost = costEntries[0]?.[1] || 1

  return (
    <div className="int-tab-content">
      {/* Cost breakdown */}
      <Panel title="Per-Agent Cost Breakdown (24h)">
        <div className="int-cost-list">
          {costEntries.slice(0, 8).map(([agent, cost]) => (
            <div key={agent} className="int-cost-row">
              <span className="int-cost-agent">{agent}</span>
              <div className="int-cost-bar-wrap">
                <div className="int-cost-bar" style={{ width: `${(cost / maxCost) * 100}%` }} />
              </div>
              <span className="int-cost-val">${cost.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </Panel>

      {/* LLM call log */}
      <Panel title="Live LLM Call Log" right={
        <button className="int-btn int-btn--sm" onClick={refresh} aria-label="Refresh LLM call log" title="Refresh">↻</button>
      }>
        <div className="int-call-head">
          <span>Model</span><span>Agent</span><span>ms</span><span>Tokens</span><span>Cost</span><span>Status</span>
        </div>
        <div className="int-call-list">
          {list.map(c => (
            <div
              key={c.id}
              className={`int-call-row int-call-row--${c.status} ${selected?.id === c.id ? 'int-call-row--selected' : ''}`}
              onClick={() => setSelected(c)}
            >
              <span className="int-call-model">{c.model}</span>
              <span className="int-call-agent">{c.agent}</span>
              <span className="int-call-ms" style={{ color: c.ms > 3000 ? 'var(--nx-warning)' : 'var(--nx-text-muted)' }}>{c.ms}ms</span>
              <span className="int-call-tokens">{c.tokens.toLocaleString()}</span>
              <span className="int-call-cost">${(c.cost_usd || 0).toFixed(4)}</span>
              <span className={`int-call-status int-call-status--${c.status}`}>{c.status}</span>
            </div>
          ))}
        </div>
        {selected && (
          <div className="int-call-detail">
            <div className="int-call-detail__title">Call {selected.id} — {new Date(selected.ts).toLocaleTimeString()}</div>
            <div className="int-call-detail__rows">
              {[['Model', selected.model], ['Agent', selected.agent], ['Duration', `${selected.ms}ms`], ['Tokens', selected.tokens], ['Cost', `$${(selected.cost_usd || 0).toFixed(6)}`]].map(([k, v]) => (
                <div key={k} className="int-call-detail__row"><span>{k}</span><span>{v}</span></div>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </div>
  )
}

/* ── Tab 3: AI Strategic Insights ───────────────────────────────────────────── */
function InsightsTab() {
  const [insights, setInsights] = useState([])
  const [dismissed, setDismissed] = useState([])
  const [askText, setAskText] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState(null)

  const { data } = useLiveData({
    endpoint: '/api/intelligence/insights',
    wsEvent: 'agent:insight',
    pollMs: 30000,
    transform: d => d?.insights || d,
  })

  useEffect(() => { if (data?.length) setInsights(data) }, [data])

  const visible = insights.filter(i => !dismissed.includes(i.id))

  async function handleAction(insight) {
    try {
      await api.post('/api/intelligence/trigger-action', { insight_id: insight.id, action: insight.actionType })
      toastSuccess(`Action triggered: ${insight.action}`)
      setDismissed(d => [...d, insight.id])
    } catch { toastError('Failed to trigger action') }
  }

  async function askBrain(e) {
    e.preventDefault()
    if (!askText.trim()) return
    setAsking(true)
    try {
      const j = await api.post('/api/intelligence/ask', { question: askText })
      setAnswer(j.insight || j.answer || 'No insight available from current data.')
    } catch {
      setAnswer('Unable to fetch insight — backend may be offline.')
    } finally { setAsking(false) }
  }

  return (
    <div className="int-tab-content">
      {/* Active insight cards */}
      <Panel title="AI Strategic Insights">
        {visible.length === 0
          ? <div className="int-empty">No active insights — system is healthy</div>
          : visible.map(ins => (
            <div key={ins.id} className={`int-insight int-insight--${ins.severity}`}>
              <div className="int-insight__head">
                <span className={`int-insight__sev int-insight__sev--${ins.severity}`}>{ins.severity.toUpperCase()}</span>
                <span className="int-insight__cat">{ins.category}</span>
                <span className="int-insight__title">{ins.title}</span>
              </div>
              <div className="int-insight__detail">{ins.detail}</div>
              <div className="int-insight__actions">
                <button className="int-btn int-btn--primary" onClick={() => handleAction(ins)}>{ins.action}</button>
                <button className="int-btn" onClick={() => setDismissed(d => [...d, ins.id])}>Dismiss</button>
                <button className="int-btn" onClick={() => toastSuccess('Snoozed for 24h')}>Snooze 24h</button>
              </div>
            </div>
          ))
        }
      </Panel>

      {/* Manual ask */}
      <Panel title="Ask the Brain">
        <form className="int-ask-form" onSubmit={askBrain}>
          <input
            className="int-ask-input"
            placeholder="Ask for an insight on... (e.g. 'What's slowing our lead pipeline?')"
            value={askText}
            onChange={e => setAskText(e.target.value)}
          />
          <button className="int-btn int-btn--primary" type="submit" disabled={asking}>
            {asking ? 'Thinking...' : 'Ask'}
          </button>
        </form>
        {answer && (
          <div className="int-ask-answer">{answer}</div>
        )}
      </Panel>
    </div>
  )
}

/* ── Root ────────────────────────────────────────────────────────────────────── */
export default function IntelligencePage() {
  const [tab, setTab] = useState('fleet')
  const TABS = [
    { id: 'fleet',    label: 'Agent Fleet' },
    { id: 'brain',    label: 'Brain Inspector' },
    { id: 'insights', label: 'AI Insights' },
  ]
  return (
    <div className="int-page">
      <div className="int-header">
        <span className="int-header__title">INTELLIGENCE HUB</span>
        <div className="int-header__tabs">
          {TABS.map(t => (
            <button key={t.id} className={`int-tab-btn ${tab === t.id ? 'int-tab-btn--active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'fleet'    && <FleetTab />}
      {tab === 'brain'    && <BrainInspectorTab />}
      {tab === 'insights' && <InsightsTab />}
    </div>
  )
}
