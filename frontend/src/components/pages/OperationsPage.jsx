import { useState, useMemo, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

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

function WorkflowNode({ node, index }) {
  const statusColors = {
    completed: 'var(--success)',
    running: 'var(--warning)',
    pending: 'var(--text-muted)',
    failed: 'var(--error)',
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className="ds-card-interactive"
      style={{ padding: 'var(--space-3) var(--space-4)' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <span style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: statusColors[node.status] || 'var(--text-muted)',
          flexShrink: 0,
        }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
            {node.task_id || node.name || `Step ${index + 1}`}
          </div>
          {node.agent && (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Agent: {node.agent}
            </div>
          )}
        </div>
        <span style={{
          fontSize: '11px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: `${statusColors[node.status] || 'var(--text-muted)'}15`,
          color: statusColors[node.status] || 'var(--text-muted)',
          textTransform: 'uppercase',
        }}>
          {node.status || 'pending'}
        </span>
      </div>
      {node.progress != null && (
        <div style={{
          marginTop: 'var(--space-2)',
          height: '3px',
          background: 'var(--bg-base)',
          borderRadius: '2px',
          overflow: 'hidden',
        }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(node.progress * 100, 100)}%` }}
            style={{
              height: '100%',
              background: statusColors[node.status] || 'var(--gold)',
              borderRadius: '2px',
            }}
          />
        </div>
      )}
    </motion.div>
  )
}

function SchedulerCard({ productMetrics }) {
  const mode = productMetrics?.mode || {}
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
        Scheduler
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Mode</span>
          <span style={{ color: 'var(--text-primary)' }}>{mode.mode || 'MANUAL'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
          <span style={{ color: 'var(--text-muted)' }}>Automation</span>
          <span style={{ color: mode.automation_running ? 'var(--success)' : 'var(--text-muted)' }}>
            {mode.automation_running ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>
    </div>
  )
}

export default function OperationsPage() {
  const productMetrics = useAppStore(s => s.productMetrics)
  const automationStatus = useAppStore(s => s.automationStatus)
  const setAutomationStatus = useAppStore(s => s.setAutomationStatus)
  const activityFeed = useAppStore(s => s.activityFeed)
  const executionLogs = useAppStore(s => s.executionLogs)
  const workflowState = useAppStore(s => s.workflowState)

  const [running, setRunning] = useState(false)
  const [goal, setGoal] = useState('Run value generation cycle')

  const automationActive = Boolean(productMetrics?.mode?.automation_running)

  const controlAutomation = useCallback(async (action) => {
    setRunning(true)
    try {
      const res = await fetch(`${BASE}/api/automation/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, goal }),
      })
      const data = await res.json()
      setAutomationStatus(data.message || data.reason || `Automation ${action}: ${data.status || 'ok'}`)
    } catch {
      setAutomationStatus(`Automation ${action} failed.`)
    } finally {
      setRunning(false)
    }
  }, [goal, setAutomationStatus])

  const runPipeline = useCallback(async (kind) => {
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
    } catch {
      setAutomationStatus(`${kind} pipeline failed.`)
    } finally {
      setRunning(false)
    }
  }, [setAutomationStatus])

  const workflowNodes = useMemo(() => {
    const run = workflowState?.runs?.find(r => r.run_id === workflowState?.active_run)
    return run?.nodes || run?.tasks || []
  }, [workflowState])

  return (
    <div className="page-enter">
      <PageHeader title="Operations" subtitle="Tasks, workflows, and automation control">
        <button
          className="btn-primary"
          onClick={() => controlAutomation('start')}
          disabled={running || automationActive}
        >
          {running ? 'Starting…' : automationActive ? '● Running' : 'Start Automation'}
        </button>
        <button
          className="btn-danger"
          onClick={() => controlAutomation('stop')}
          disabled={running || !automationActive}
        >
          Stop All
        </button>
      </PageHeader>

      {/* Status bar */}
      {automationStatus && (
        <div className="ds-card" style={{
          padding: 'var(--space-3) var(--space-4)',
          marginBottom: 'var(--space-4)',
          fontSize: '13px',
          color: 'var(--text-secondary)',
        }}>
          {automationStatus}
        </div>
      )}

      {/* Controls row */}
      <div style={{
        display: 'flex',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-4)',
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Automation goal"
          style={{
            flex: '1 1 200px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-3)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            outline: 'none',
          }}
        />
        <button className="btn-secondary" onClick={() => runPipeline('content')} disabled={running}>
          Content Pipeline
        </button>
        <button className="btn-secondary" onClick={() => runPipeline('lead')} disabled={running}>
          Lead Pipeline
        </button>
        <button className="btn-secondary" onClick={() => runPipeline('opportunity')} disabled={running}>
          Outreach Pipeline
        </button>
      </div>

      {/* Two-column: Workflows + Activity Feed */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: 'var(--space-4)',
      }}>
        {/* Workflow view */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
            <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Workflow Pipeline
            </h2>
            {workflowState?.active_run && (
              <span style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(34, 197, 94, 0.1)',
                color: 'var(--success)',
              }}>
                LIVE
              </span>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {workflowNodes.length === 0 ? (
              <div className="ds-card" style={{
                padding: 'var(--space-5)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}>
                Start automation to see workflow pipeline
              </div>
            ) : workflowNodes.map((node, idx) => (
              <WorkflowNode key={node.task_id || idx} node={node} index={idx} />
            ))}
          </div>

          <SchedulerCard productMetrics={productMetrics} />
        </div>

        {/* Live Activity Feed — Stripe-style log */}
        <div>
          <h2 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
            Activity Feed
            {activityFeed.length > 0 && (
              <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>
                ({activityFeed.length})
              </span>
            )}
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            {activityFeed.length === 0 ? (
              <div className="ds-card" style={{
                padding: 'var(--space-5)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}>
                No activity yet
              </div>
            ) : activityFeed.slice(0, 25).map((item, idx) => (
              <motion.div
                key={item.id || idx}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  background: idx % 2 === 0 ? 'var(--bg-card)' : 'transparent',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 'var(--space-3)',
                  fontSize: '13px',
                  borderRadius: idx === 0 ? 'var(--radius-md) var(--radius-md) 0 0' : idx === Math.min(activityFeed.length - 1, 24) ? '0 0 var(--radius-md) var(--radius-md)' : 0,
                }}
              >
                <span style={{
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  flexShrink: 0,
                  width: '60px',
                  fontVariantNumeric: 'tabular-nums',
                  fontFamily: "'JetBrains Mono', monospace",
                }}>
                  {item.ts ? new Date(item.ts).toLocaleTimeString('en-US', {
                    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
                  }) : '—'}
                </span>
                <span style={{ color: 'var(--text-primary)', flex: 1, wordBreak: 'break-word' }}>
                  {item.notes}
                </span>
              </motion.div>
            ))}
          </div>

          {/* Execution logs */}
          {executionLogs.length > 0 && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                Execution Log
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
                {executionLogs.slice(0, 10).map((log, idx) => (
                  <div
                    key={log.id || idx}
                    style={{
                      padding: 'var(--space-2) var(--space-3)',
                      background: 'var(--bg-card)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-2)',
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    <span style={{ color: log.status === 'success' ? 'var(--success)' : 'var(--error)' }}>
                      {log.status === 'success' ? '✓' : '✕'}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{log.task_id}</span>
                    <span style={{ color: 'var(--text-muted)' }}>·</span>
                    <span style={{ color: 'var(--text-muted)' }}>{log.skill}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
