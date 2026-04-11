import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import { useAppStore } from '../store/appStore'

const BASE = `http://${window.location.hostname}:3001`

export default function Dashboard() {
  const setProductMetrics = useAppStore(s => s.setProductMetrics)
  const productMetrics = useAppStore(s => s.productMetrics)
  const automationStatus = useAppStore(s => s.automationStatus)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const [mode, setMode] = useState('MANUAL')
  const [overrideActionId, setOverrideActionId] = useState('')
  const [goal, setGoal] = useState('Run value generation cycle')
  const [running, setRunning] = useState(false)

  const refreshDashboard = async () => {
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
  }

  useEffect(() => {
    refreshDashboard()
    const i = setInterval(refreshDashboard, 8000)
    return () => clearInterval(i)
  }, [])

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
    }
  }

  const runPipeline = async (kind) => {
    const payloads = {
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
        body: { opportunity: 'retainer upgrade campaign', budget: 500, dry_run: false },
      },
    }
    const cfg = payloads[kind]
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

  const kpis = useMemo(() => ([
    { label: 'Tasks Executed', value: productMetrics?.tasks?.tasks_executed ?? 0 },
    { label: 'Success Rate', value: `${Math.round((productMetrics?.tasks?.success_rate ?? 0) * 100)}%` },
    { label: 'Revenue', value: `$${(productMetrics?.revenue?.total_revenue ?? 0).toFixed(2)}` },
    { label: 'Pipeline Runs', value: productMetrics?.pipelines?.runs ?? 0 },
  ]), [productMetrics])

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
            <button className="tier-1-btn font-mono text-xs px-4 py-2" onClick={() => controlAutomation('start')} disabled={running}>
              START AUTOMATION
            </button>

            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => controlAutomation('stop')} disabled={running}>
              STOP
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('content')} disabled={running}>
              RUN CONTENT PIPELINE
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('lead')} disabled={running}>
              RUN LEAD PIPELINE
            </button>
            <button className="tier-2-btn font-mono text-xs px-3 py-2" onClick={() => runPipeline('opportunity')} disabled={running}>
              RUN OPPORTUNITY PIPELINE
            </button>

            <select className="tier-2-btn font-mono text-xs px-2 py-2" value={mode} onChange={(e) => setModeRemote(e.target.value)}>
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
              <button className="tier-3-surface font-mono text-xs px-3 py-2" onClick={() => controlAutomation('override')}>
                OVERRIDE
              </button>
            </div>
          </div>
          <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>{automationStatus}</p>
        </section>

        <section className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {kpis.map((kpi) => (
            <article key={kpi.label} className="ds-card-secondary p-3">
              <div className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>{kpi.label}</div>
              <div className="font-mono text-lg font-semibold" style={{ color: 'var(--gold)' }}>{kpi.value}</div>
            </article>
          ))}
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-3 min-h-0 flex-1">
          <article className="ds-card p-3 min-h-0 flex flex-col">
            <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>REAL-TIME ACTIVITY FEED</h2>
            <div className="overflow-y-auto space-y-1 min-h-0">
              {(productMetrics?.activity_feed || []).slice(0, 12).map((item, idx) => (
                <div key={`${item.id || idx}`} className="tier-3-surface p-2 font-mono text-[11px]">
                  {item.notes || item.action_id || 'activity'}
                </div>
              ))}
            </div>
          </article>

          <article className="ds-card p-3 min-h-0 flex flex-col">
            <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>EXECUTION LOGS</h2>
            <div className="overflow-y-auto space-y-1 min-h-0">
              {(productMetrics?.execution_logs || []).slice(0, 12).map((log, idx) => (
                <div key={`${log.id || idx}`} className="tier-3-surface p-2 font-mono text-[11px]">
                  {log.task_id} · {log.skill} · {log.success ? 'SUCCESS' : 'FAILED'}
                </div>
              ))}
            </div>
          </article>

          <article className="ds-card p-3 min-h-0 flex flex-col">
            <h2 className="font-mono text-xs mb-2" style={{ color: 'var(--gold)' }}>TOP STRATEGIES & EARNINGS</h2>
            <div className="overflow-y-auto space-y-1 min-h-0">
              {(productMetrics?.top_strategies || []).slice(0, 8).map((s, idx) => (
                <div key={`${s.strategy_id || idx}`} className="tier-3-surface p-2 font-mono text-[11px]">
                  {s.agent} · {(s.outcome_score || 0).toFixed(2)} · {s.outcome_status || 'success'}
                </div>
              ))}
              <div className="tier-3-surface p-2 font-mono text-[11px]">
                Earnings Today: ${(productMetrics?.revenue?.total_revenue || 0).toFixed(2)}
              </div>
            </div>
          </article>
        </section>
      </div>
    </motion.div>
  )
}
