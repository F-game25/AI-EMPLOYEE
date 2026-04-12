import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import ChatPanel from './dashboard/ChatPanel'
import SecondaryPanels from './dashboard/SecondaryPanels'
import { useAppStore } from '../store/appStore'
import SecondaryButton from './ui/SecondaryButton'
import TertiaryPanel from './ui/TertiaryPanel'
import WorkflowTreePanel from './dashboard/WorkflowTreePanel'
import BrainInsightsPanel from './dashboard/BrainInsightsPanel'

const BASE = `http://${window.location.hostname}:3001`
const PIPELINE_DEFAULTS = {
  content: {
    endpoint: '/api/money/content-pipeline',
    body: { topic: 'high-intent niche content', platforms: ['twitter', 'linkedin'], dry_run: false },
  },
  lead: {
    endpoint: '/api/money/lead-pipeline',
    body: { source: 'crm_dataset', audience: 'SaaS founders', channels: ['email'], dry_run: false },
  },
  opportunity: {
    endpoint: '/api/money/opportunity-pipeline',
    body: { opportunity: 'retainer upgrade outreach', budget: 500, dry_run: false },
  },
}

const KIND_COLORS = {
  automation: 'var(--gold)',
  pipeline: '#60a5fa',
  task: 'var(--success)',
  system: 'var(--text-muted)',
}

const MODE_OPTIONS = [
  { id: 'MANUAL', label: 'Manual Control', help: 'Operator-guided execution' },
  { id: 'AUTO', label: 'Auto Ops', help: 'Autonomous scheduling and routing' },
  { id: 'BLACKLIGHT', label: 'Blacklight', help: 'Maximum activation and throughput' },
]

export default function Dashboard() {
  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const productMetrics = useAppStore(s => s.productMetrics)
  const systemStatus = useAppStore(s => s.systemStatus)
  const automationStatus = useAppStore(s => s.automationStatus)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const setBrainInsights = useAppStore(s => s.setBrainInsights)
  const setWorkflowSnapshot = useAppStore(s => s.setWorkflowSnapshot)
  // Real-time feeds from WebSocket
  const activityFeed = useAppStore(s => s.activityFeed)
  const executionLogs = useAppStore(s => s.executionLogs)

  const [mode, setMode] = useState('MANUAL')
  const [overrideActionId, setOverrideActionId] = useState('')
  const [goal, setGoal] = useState('Run value generation cycle')
  const [running, setRunning] = useState(false)

  const refreshDashboard = useCallback(async () => {
    try {
      const [modeRes, dashRes] = await Promise.all([
        fetch(`${BASE}/api/mode`),
        fetch(`${BASE}/api/product/dashboard`),
      ])
      const modeData = await modeRes.json()
      const dashData = await dashRes.json()
      if (modeData?.mode) setMode(modeData.mode)
      setProductMetrics(dashData || {})
      if (dashData?.learning?.brain) setBrainInsights(dashData.learning.brain)
      if (Array.isArray(dashData?.workflow_runs)) {
        setWorkflowSnapshot({
          active_run: dashData?.workflow_focus || null,
          runs: dashData.workflow_runs,
        })
      }
    } catch {
      setAutomationStatus('Unable to refresh dashboard data.')
    }
  }, [setAutomationStatus, setProductMetrics, setBrainInsights, setWorkflowSnapshot])

  useEffect(() => {
    refreshDashboard()
    const i = setInterval(refreshDashboard, 8000)
    return () => clearInterval(i)
  }, [refreshDashboard])

  const setModeRemote = async (nextMode) => {
    try {
      const res = await fetch(`${BASE}/api/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode }),
      })
      const data = await res.json()
      if (data?.mode) {
        setMode(data.mode)
        setAutomationStatus(`Mode switched to ${data.mode}.`)
      }
      refreshDashboard()
    } catch {
      setAutomationStatus('Mode switch failed.')
    }
  }

  const controlAutomation = async (action) => {
    setRunning(true)
    try {
      const res = await fetch(`${BASE}/api/automation/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, goal, override_action_id: overrideActionId }),
      })
      const data = await res.json()
      setAutomationStatus(data.message || data.reason || `Automation ${action}: ${data.status || 'ok'}`)
      refreshDashboard()
    } catch {
      setAutomationStatus(`Automation ${action} failed.`)
    } finally {
      setRunning(false)
    }
  }

  const runPipeline = async (kind) => {
    const cfg = PIPELINE_DEFAULTS[kind]
    if (!cfg) return
    setRunning(true)
    try {
      const res = await fetch(`${BASE}${cfg.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg.body),
      })
      const data = await res.json()
      setAutomationStatus(`${data.pipeline || 'Pipeline'} run ${data.status || 'queued'}.`)
      refreshDashboard()
    } catch {
      setAutomationStatus(`${kind} pipeline failed.`)
    } finally {
      setRunning(false)
    }
  }

  const systemStats = useMemo(() => ([
    { label: 'CPU', value: `${systemStatus?.cpu_usage ?? 0}%` },
    { label: 'GPU', value: `${systemStatus?.gpu_usage ?? 0}%` },
    { label: 'MEMORY', value: `${systemStatus?.memory ?? 0}%` },
    { label: 'AGENTS', value: `${systemStatus?.running_agents ?? 0}/${systemStatus?.total_agents ?? 0}` },
    { label: 'HEARTBEAT', value: `${systemStatus?.heartbeat ?? 0}` },
  ]), [systemStatus])

  const businessKpis = useMemo(() => ([
    { label: 'Tasks Executed', value: productMetrics?.tasks?.tasks_executed ?? 0 },
    { label: 'Success Rate', value: `${Math.round((productMetrics?.tasks?.success_rate ?? 0) * 100)}%` },
    { label: 'Value Generated', value: `$${(productMetrics?.value?.value_generated ?? 0).toFixed(2)}` },
    { label: 'Revenue', value: `$${(productMetrics?.revenue?.total_revenue ?? 0).toFixed(2)}` },
  ]), [productMetrics])
  // `running` is request-in-flight; `automationActive` is backend-reported execution state.
  const automationActive = Boolean(productMetrics?.mode?.automation_running)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 flex flex-col scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      <TopBar />

      {/* Three-panel row: LEFT main content | CENTRE chat | RIGHT secondary */}
      <div className="flex-1 overflow-hidden flex dashboard-main">

        {/* LEFT: Controls + metrics (flex column, scrollable) */}
        <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3 dashboard-left">
          <section className="ds-card p-3">
          <div className="flex flex-wrap items-center gap-2">
            <button className="tier-1-btn font-mono text-xs px-4 py-2" onClick={() => controlAutomation('start')} disabled={running || automationActive} title="Start full automation workflow">
              START AUTOMATION
            </button>

            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => controlAutomation('stop')} disabled={running || !automationActive} title="Stop all agent execution and clear queued tasks">
              STOP ALL
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('content')} disabled={running} title="Run content generation pipeline">
              RUN CONTENT PIPELINE
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('lead')} disabled={running} title="Run lead generation and scoring pipeline">
              RUN LEAD PIPELINE
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('opportunity')} disabled={running} title="Run opportunity conversion pipeline">
              RUN OUTREACH PIPELINE
            </button>
          </div>
          <div className="mt-2 font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            Hint: start automation to render a live Task → Agent → Action → Result chain in Workflow Tree.
          </div>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2">
            {MODE_OPTIONS.map((modeOption) => (
              <button
                key={modeOption.id}
                type="button"
                onClick={() => setModeRemote(modeOption.id)}
                className="text-left p-2"
                title={modeOption.help}
                style={{
                  background: mode === modeOption.id ? 'rgba(245,196,0,0.09)' : 'rgba(255,255,255,0.02)',
                  border: mode === modeOption.id ? '1px solid rgba(245,196,0,0.45)' : '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                }}
              >
                <div className="font-mono text-[11px]" style={{ color: mode === modeOption.id ? 'var(--gold)' : 'var(--text-secondary)' }}>
                  {modeOption.id}
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {modeOption.label}
                </div>
              </button>
            ))}
          </div>

          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            <input
              className="tier-3-surface font-mono text-xs px-3 py-2 outline-none bg-transparent"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Automation goal"
            />
            <div className="flex gap-2">
              <input
                className="tier-3-surface flex-1 font-mono text-xs px-3 py-2 outline-none bg-transparent"
                value={overrideActionId}
                onChange={(e) => setOverrideActionId(e.target.value)}
                placeholder="Pending action ID for manual override"
              />
              <SecondaryButton onClick={() => controlAutomation('override')}>
                OVERRIDE
              </SecondaryButton>
            </div>
          </div>
          <TertiaryPanel className="mt-2 p-2 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
            {automationStatus || 'No actions yet.'}
          </TertiaryPanel>
        </section>

          {/* Three info columns */}
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-3 min-h-0 flex-1">

            {/* System stats — single source of truth */}
            <article className="ds-card p-3 min-h-0 flex flex-col">
              <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>SYSTEM STATS</h2>
              <div className="overflow-y-auto space-y-1 min-h-0">
                {systemStats.map((stat) => (
                  <TertiaryPanel key={stat.label} className="p-2 font-mono text-[11px] flex justify-between gap-3">
                    <span style={{ color: 'var(--text-muted)' }}>{stat.label}</span>
                    <span style={{ color: 'var(--gold)' }}>{stat.value}</span>
                  </TertiaryPanel>
                ))}
              </div>
            </article>

            {/* Live activity feed — WebSocket driven, instant updates */}
            <article className="ds-card p-3 min-h-0 flex flex-col">
              <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>
                LIVE ACTIVITY
                {activityFeed.length > 0 && (
                  <span className="ml-2" style={{ color: 'var(--text-muted)', fontWeight: 'normal' }}>
                    ({activityFeed.length})
                  </span>
                )}
              </h2>
              <div className="overflow-y-auto space-y-1 min-h-0 flex-1">
                {activityFeed.length === 0 ? (
                  <p className="font-mono text-[11px] text-center mt-4" style={{ color: 'var(--text-muted)' }}>
                    Start automation to see live activity
                  </p>
                ) : activityFeed.slice(0, 20).map((item, idx) => (
                  <TertiaryPanel key={item.id || idx} className="p-2 font-mono text-[11px]">
                    <div className="flex justify-between gap-2 items-start">
                      <span style={{ color: KIND_COLORS[item.kind] || 'var(--text-secondary)', flex: 1, minWidth: 0, wordBreak: 'break-word' }}>
                        {item.notes}
                      </span>
                      <span className="flex-shrink-0" style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
                        {item.ts ? new Date(item.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                      </span>
                    </div>
                  </TertiaryPanel>
                ))}
              </div>
            </article>

            {/* Business metrics + execution log */}
            <article className="ds-card p-3 min-h-0 flex flex-col">
              <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>BUSINESS METRICS</h2>
              <div className="overflow-y-auto space-y-1 min-h-0 flex-1">
                {businessKpis.map((kpi) => (
                  <TertiaryPanel key={kpi.label} className="p-2 font-mono text-[11px] flex justify-between gap-3">
                    <span style={{ color: 'var(--text-muted)' }}>{kpi.label}</span>
                    <span style={{ color: 'var(--gold)' }}>{kpi.value}</span>
                  </TertiaryPanel>
                ))}
                {executionLogs.length > 0 && (
                  <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <div className="font-mono text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>RECENT EXECUTIONS</div>
                    {executionLogs.slice(0, 5).map((log, idx) => (
                      <TertiaryPanel key={log.id || idx} className="p-2 font-mono text-[11px] mb-1">
                        <span style={{ color: log.status === 'success' ? 'var(--success)' : 'var(--error)' }}>
                          {log.status === 'success' ? '✓' : '✕'}
                        </span>
                        {' '}
                        <span style={{ color: 'var(--text-secondary)' }}>{log.task_id}</span>
                        {' · '}
                        <span style={{ color: 'var(--text-muted)' }}>{log.skill}</span>
                      </TertiaryPanel>
                    ))}
                  </div>
                )}
              </div>
            </article>

            <WorkflowTreePanel />
            <BrainInsightsPanel />

          </section>
        </div>

        {/* CENTRE: Orchestrator Chat */}
        <div
          className="flex-shrink-0 flex flex-col dashboard-chat-rail"
          style={{
            borderLeft: '1px solid var(--border-gold-dim)',
            borderRight: '1px solid var(--border-gold-dim)',
            background: 'var(--bg-panel)',
          }}
        >
          <ChatPanel />
        </div>

        {/* RIGHT: SYSTEMS / POWER / HEARTBEAT tabs */}
        <SecondaryPanels />
      </div>
    </motion.div>
  )
}
