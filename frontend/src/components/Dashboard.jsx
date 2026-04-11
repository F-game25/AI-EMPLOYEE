import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import { useAppStore } from '../store/appStore'
import PrimaryButton from './ui/PrimaryButton'
import SecondaryButton from './ui/SecondaryButton'
import TertiaryPanel from './ui/TertiaryPanel'

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

export default function Dashboard() {
  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const productMetrics = useAppStore(s => s.productMetrics)
  const systemStatus = useAppStore(s => s.systemStatus)
  const automationStatus = useAppStore(s => s.automationStatus)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const [mode, setMode] = useState('MANUAL')
  const [overrideActionId, setOverrideActionId] = useState('')
  const [goal, setGoal] = useState('Run value generation cycle')
  const [running, setRunning] = useState(false)
  const [activeAction, setActiveAction] = useState('')

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
    } catch {
      setAutomationStatus('Unable to refresh dashboard data.')
    }
  }, [setAutomationStatus, setProductMetrics])

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
    setActiveAction(action)
    try {
      const res = await fetch(`${BASE}/api/automation/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          goal,
          override_action_id: overrideActionId,
        }),
      })
      const data = await res.json()
      setAutomationStatus(data.message || data.reason || `Automation ${action}: ${data.status || 'ok'}`)
      refreshDashboard()
    } catch {
      setAutomationStatus(`Automation ${action} failed.`)
    } finally {
      setRunning(false)
      setActiveAction('')
    }
  }

  const runPipeline = async (kind) => {
    const cfg = PIPELINE_DEFAULTS[kind]
    if (!cfg) return
    setRunning(true)
    setActiveAction(`pipeline-${kind}`)
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
      setActiveAction('')
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
  const isAutomationRunning = Boolean(productMetrics?.mode?.automation_running)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 flex flex-col scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      <TopBar />

      <div className="flex-1 overflow-hidden px-4 py-3 flex flex-col gap-3">
        <section className="ds-card p-3">
          <div className="flex flex-wrap items-center gap-2">
            <PrimaryButton
              onClick={() => controlAutomation(isAutomationRunning ? 'stop' : 'start')}
              disabled={running}
            >
              {running && (activeAction === 'start' || activeAction === 'stop')
                ? 'PROCESSING...'
                : isAutomationRunning ? 'STOP AUTOMATION' : 'START AUTOMATION'}
            </PrimaryButton>

            <SecondaryButton onClick={() => runPipeline('content')} disabled={running}>
              {running && activeAction === 'pipeline-content' ? 'RUNNING...' : 'CONTENT PIPELINE'}
            </SecondaryButton>
            <SecondaryButton onClick={() => runPipeline('lead')} disabled={running}>
              {running && activeAction === 'pipeline-lead' ? 'RUNNING...' : 'LEAD PIPELINE'}
            </SecondaryButton>
            <SecondaryButton onClick={() => runPipeline('opportunity')} disabled={running}>
              {running && activeAction === 'pipeline-opportunity' ? 'RUNNING...' : 'OPPORTUNITY PIPELINE'}
            </SecondaryButton>

            <select className="tier-2-btn font-mono text-xs px-3 py-2" value={mode} onChange={(e) => setModeRemote(e.target.value)} aria-label="Execution mode">
              <option value="MANUAL">MANUAL</option>
              <option value="AUTO">AUTO</option>
              <option value="BLACKLIGHT">BLACKLIGHT</option>
            </select>
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

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 min-h-0 flex-1">
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

          <article className="ds-card p-3 min-h-0 flex flex-col">
            <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>REAL-TIME ACTIVITY FEED</h2>
            <div className="overflow-y-auto space-y-1 min-h-0">
              {(productMetrics?.activity_feed || []).slice(0, 12).map((item, idx) => (
                <TertiaryPanel key={`${item.id || idx}`} className="p-2 font-mono text-[11px]">
                  {item.notes || item.action_id || 'activity'}
                </TertiaryPanel>
              ))}
            </div>
          </article>

          <article className="ds-card p-3 min-h-0 flex flex-col">
            <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>BUSINESS METRICS</h2>
            <div className="overflow-y-auto space-y-1 min-h-0">
              {businessKpis.map((kpi) => (
                <TertiaryPanel key={kpi.label} className="p-2 font-mono text-[11px] flex justify-between gap-3">
                  <span style={{ color: 'var(--text-muted)' }}>{kpi.label}</span>
                  <span style={{ color: 'var(--gold)' }}>{kpi.value}</span>
                </TertiaryPanel>
              ))}
              {(productMetrics?.execution_logs || []).slice(0, 5).map((log, idx) => (
                <TertiaryPanel key={`${log.id || idx}`} className="p-2 font-mono text-[11px]">
                  {log.task_id} · {log.skill} · {(log.status === 'success') ? 'SUCCESS' : 'FAILED'}
                </TertiaryPanel>
              ))}
            </div>
          </article>
        </section>
      </div>
    </motion.div>
  )
}
