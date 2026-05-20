import { useState } from 'react'
import { Panel, SectionLabel, StatusPill, EmptyState, ErrorState } from '../nexus-ui'
import { useLiveData } from '../../hooks/useLiveData'
import { useCognitiveStore } from '../../store/cognitiveStore'
import { toastSuccess, toastError } from '../nexus-ui/Toaster'
import './CognitionPage.css'

const PHASES = [
  ['input', 'Input'],
  ['retrieve', 'Retrieve'],
  ['context', 'Context'],
  ['classify', 'Classify'],
  ['llm', 'Model'],
  ['validate', 'Validate'],
  ['execute', 'Execute'],
  ['memory', 'Memory'],
]

function PipelineVisualizer({ phases }) {
  const live = phases || {}
  const hasActivity = Object.keys(live).length > 0
  if (!hasActivity) return <EmptyState icon="[]" title="No live cognition trace" sub="Start a main AI task to see classification, retrieval, model routing, tool decisions and memory writeback." />
  return (
    <div className="cog-pipeline">
      {PHASES.map(([id, label]) => {
        const phase = live[id] || { status: 'pending', ms: null }
        return (
          <div key={id} className={`cog-phase cog-phase--${phase.status || 'pending'}`}>
            <div className="cog-phase__dot" />
            <div className="cog-phase__label">{label}</div>
            {phase.ms != null && <div className="cog-phase__ms">{phase.ms}ms</div>}
          </div>
        )
      })}
    </div>
  )
}

function LLMCallStream() {
  const { data, loading, error } = useLiveData({
    endpoint: '/api/intelligence/llm-calls',
    wsEvent: 'llm:call',
    pollMs: 5000,
    transform: (d) => d?.calls || [],
  })
  const calls = data || []
  return (
    <Panel title="Model Activity">
      {loading && <EmptyState icon="..." title="Loading model calls" />}
      {error && <ErrorState title="Model telemetry degraded" message={error} />}
      {!loading && !error && !calls.length && <EmptyState icon="[]" title="No model calls yet" sub="The local/external model router has not recorded calls in this window." />}
      {!!calls.length && (
        <>
          <div className="cog-call-head">
            <span>Model</span><span>Agent</span><span>Latency</span><span>Tokens</span><span>Status</span>
          </div>
          <div className="cog-call-list">
            {calls.slice(0, 20).map((call, index) => (
              <div key={call.id || index} className={`cog-call-row cog-call-row--${call.status || 'ok'}`}>
                <span className="cog-call-model">{call.model || call.provider || 'unknown'}</span>
                <span className="cog-call-agent">{call.agent || 'main-ai'}</span>
                <span className="cog-call-ms">{call.ms || call.latency_ms || 0}ms</span>
                <span className="cog-call-tokens">{(call.tokens || call.total_tokens || 0).toLocaleString()}</span>
                <span className={`cog-call-status cog-call-status--${call.status || 'ok'}`}>{call.status || 'ok'}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Panel>
  )
}

function DecisionLog() {
  const { data, loading, error } = useLiveData({
    endpoint: '/api/cognition/decisions',
    wsEvent: 'cognition:decision',
    pollMs: 8000,
    transform: (d) => d?.decisions || [],
  })
  const decisions = data || []
  return (
    <Panel title="Decision Intelligence">
      {loading && <EmptyState icon="..." title="Loading decisions" />}
      {error && <ErrorState title="Decision stream degraded" message={error} />}
      {!loading && !error && !decisions.length && <EmptyState icon="[]" title="No decisions recorded" sub="Agent/model/tool choices will appear here when the main AI runs tasks." />}
      {decisions.map((decision) => (
        <div key={decision.id} className="cog-decision">
          <div className="cog-decision__head">
            <span className="cog-decision__task">{decision.task || decision.goal}</span>
            <span className="cog-decision__score">{Math.round((decision.score || decision.confidence || 0) * 100)}%</span>
          </div>
          <div className="cog-decision__winner">Selected: <strong>{decision.winner || decision.selected || 'unknown'}</strong></div>
          <div className="cog-decision__reason">{decision.reason || 'No reason stored.'}</div>
          {!!decision.alternatives?.length && <div className="cog-decision__alts">Rejected: {decision.alternatives.join(', ')}</div>}
        </div>
      ))}
    </Panel>
  )
}

function LearningTab() {
  const { data: strategiesData, error: strategiesError } = useLiveData({
    endpoint: '/api/cognition/learning/strategies',
    transform: (d) => d?.strategies || [],
  })
  const { data: successData } = useLiveData({
    endpoint: '/api/cognition/learning/success-rate',
    transform: (d) => d || { data: [], series: [], state: 'empty' },
  })
  const strategies = strategiesData || []
  const success = successData?.series || []

  return (
    <div className="cog-tab-content">
      <Panel title="Learning Panel">
        {strategiesError && <ErrorState title="Learning store degraded" message={strategiesError} />}
        {!strategies.length && <EmptyState icon="[]" title="No learned strategies yet" sub="Successful real task patterns can be promoted to workflows once enough evidence exists." />}
        {strategies.map((strategy) => (
          <div key={strategy.id} className="cog-strategy">
            <div className="cog-strategy__head">
              <span className="cog-strategy__agent">{strategy.agent || 'main-ai'}</span>
              <span className="cog-strategy__conf">{Math.round((strategy.confidence || 0) * 100)}% confidence</span>
            </div>
            <div className="cog-strategy__pattern">{strategy.pattern}</div>
          </div>
        ))}
      </Panel>
      <Panel title="Task Success History">
        {!success.length && <EmptyState icon="[]" title="No success-rate history" sub="The chart will appear after task outcomes are persisted." />}
        {!!success.length && (
          <div className="cog-call-list">
            {success.map((row) => (
              <div key={row.day} className="cog-call-row">
                <span>{row.day}</span>
                <span>{Math.round(row.rate * 100)}%</span>
                <span>{row.success}/{row.total} tasks</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <ABTestsPanel />
    </div>
  )
}

function ABTestsPanel() {
  const { data, loading, error, refresh } = useLiveData({
    endpoint: '/api/cognition/learning/ab-tests',
    pollMs: 12000,
    transform: (d) => d?.tests || [],
  })
  const tests = data || []
  const [draft, setDraft] = useState({ name: '', hypothesis: '', metric: 'success_rate' })
  const [busy, setBusy] = useState(false)

  async function createTest(e) {
    e.preventDefault()
    if (!draft.name.trim()) return
    setBusy(true)
    try {
      const res = await fetch('/api/cognition/learning/ab-tests', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...(sessionStorage.getItem('ai_jwt') ? { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt')}` } : {}) },
        body: JSON.stringify(draft),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || 'Failed to create A/B test')
      toastSuccess('A/B test draft created')
      setDraft({ name: '', hypothesis: '', metric: 'success_rate' })
      refresh()
    } catch (err) {
      toastError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function updateStatus(test, status) {
    try {
      const res = await fetch(`/api/cognition/learning/ab-tests/${encodeURIComponent(test.id)}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...(sessionStorage.getItem('ai_jwt') ? { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt')}` } : {}) },
        body: JSON.stringify({ status }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || 'Failed to update test')
      toastSuccess(`A/B test marked ${status}`)
      refresh()
    } catch (err) {
      toastError(err.message)
    }
  }

  return (
    <Panel title="A/B Experiments">
      <form className="ops-create-form" onSubmit={createTest}>
        <input className="ops-input" placeholder="Experiment name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <input className="ops-input" placeholder="Hypothesis" value={draft.hypothesis} onChange={(e) => setDraft({ ...draft, hypothesis: e.target.value })} />
        <input className="ops-input" placeholder="Metric" value={draft.metric} onChange={(e) => setDraft({ ...draft, metric: e.target.value })} />
        <button className="ops-btn ops-btn--primary" disabled={busy}>{busy ? 'Creating...' : 'Create Experiment'}</button>
      </form>
      {loading && <EmptyState icon="..." title="Loading experiments" />}
      {error && <ErrorState title="A/B store degraded" message={error} />}
      {!loading && !error && !tests.length && <EmptyState icon="[]" title="No A/B experiments yet" sub="Create tests to compare prompts, model routes, tool policies or workflow strategies." />}
      <div className="cog-call-list">
        {tests.map((test) => (
          <div key={test.id} className="cog-ab-test">
            <div className="cog-ab-test__name">{test.name}</div>
            <div className="cog-ab-test__result">
              <StatusPill label={(test.status || 'draft').toUpperCase()} tone={test.status === 'completed' ? 'success' : 'idle'} size="sm" />
              <span>{test.metric || 'success_rate'}</span>
              {test.winner && <strong style={{ color: 'var(--nx-success)' }}>Winner: {test.winner}</strong>}
            </div>
            <div className="cog-decision__reason">{test.hypothesis || 'No hypothesis stored.'}</div>
            <div className="cog-decision__alts">
              {(test.variants || []).join(' vs ')}
            </div>
            <div className="mem-convo__actions">
              <button className="mem-btn mem-btn--xs" onClick={() => updateStatus(test, 'running')}>Start</button>
              <button className="mem-btn mem-btn--xs" onClick={() => updateStatus(test, 'paused')}>Pause</button>
              <button className="mem-btn mem-btn--xs mem-btn--primary" onClick={() => updateStatus(test, 'completed')}>Complete</button>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function TraceTab() {
  const pipeline = useCognitiveStore((s) => s.pipelinePhases)
  return (
    <div className="cog-tab-content">
      <Panel title="Live Cognition Trace">
        <PipelineVisualizer phases={pipeline} />
      </Panel>
      <LLMCallStream />
      <DecisionLog />
      <Panel title="Ownership">
        <SectionLabel>Main AI is the system brain</SectionLabel>
        <p className="cog-empty">Workflows, task routing, memory and economy decisions belong to the main AI. AscendForge is a supervised code/build workspace for websites, tools and project artifacts.</p>
        <StatusPill label="BOUNDARY ENFORCED" tone="success" size="sm" />
      </Panel>
    </div>
  )
}

export default function CognitionPage() {
  const [tab, setTab] = useState('trace')
  return (
    <div className="cog-page">
      <div className="cog-header">
        <span className="cog-header__title">COGNITION ENGINE</span>
        <div className="cog-header__tabs">
          {[['trace', 'Live Trace'], ['learning', 'Learning']].map(([id, label]) => (
            <button key={id} className={`cog-tab-btn ${tab === id ? 'cog-tab-btn--active' : ''}`} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {tab === 'trace' && <TraceTab />}
      {tab === 'learning' && <LearningTab />}
    </div>
  )
}
