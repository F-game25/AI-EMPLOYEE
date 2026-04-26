import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { ProgressBar } from '../components/ProgressBar'

const page = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.25 } }

interface AgentFairness {
  agent: string
  checks_total: number
  flagged_count: number
  blocked: number
  risk_score: number
  flagged: boolean
}

interface AgentDetail {
  agent: string
  groups: { group: string; n: number; n_positive: number; selection_rate: number }[]
  metrics: {
    demographic_parity_diff: number
    demographic_parity_ratio: number
    disparate_impact: number
    tpr_diff: number
    fpr_diff: number
    bias_risk_score: number
    flagged: boolean
  }
  checks_total: number
  blocked: number
  flagged_count: number
  last_check: string
}

interface Summary {
  agents_monitored: number
  flagged_agents: string[]
  avg_bias_risk: number
  compliance_status: string
  di_ratio_min: number
}

interface RecentCheck {
  check_id: string
  ts: string
  agent: string
  action: string
  demographic_group: string
  decision: boolean
  outcome: string
  high_risk: boolean
  summary: string
}

function RiskBadge({ flagged, score }: { flagged: boolean; score: number }) {
  const color = flagged ? 'var(--offline)' : score > 0.2 ? 'var(--warning)' : 'var(--online)'
  const label = flagged ? 'FLAGGED' : score > 0.2 ? 'WARN' : 'FAIR'
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 4,
      background: `${color}22`, border: `1px solid ${color}66`,
      color, fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
    }}>
      {label}
    </span>
  )
}

export function FairnessDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [agents, setAgents] = useState<AgentFairness[]>([])
  const [details, setDetails] = useState<AgentDetail[]>([])
  const [recentChecks, setRecentChecks] = useState<RecentCheck[]>([])
  const [selected, setSelected] = useState<AgentDetail | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [sumRes, agentsRes, reportRes] = await Promise.all([
        fetch('/api/fairness/summary').then((r) => r.json()),
        fetch('/api/fairness/agents').then((r) => r.json()),
        fetch('/api/fairness/report').then((r) => r.json()),
      ])
      setSummary(sumRes)
      setAgents(agentsRes)
      setDetails(reportRes.agents || [])
      setRecentChecks(reportRes.recent_checks || [])
    } catch {
      // keep empty state
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const statusColor = summary?.compliance_status === 'PASS' ? 'var(--online)'
    : summary?.compliance_status === 'WARN' ? 'var(--warning)' : 'var(--offline)'

  return (
    <motion.div {...page}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            ⚖ FAIRNESS DASHBOARD — Bias Detection & Compliance
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 4 }}>
            EU AI Act / EEOC compliance • Demographic Parity • Disparate Impact
          </p>
        </div>
        <motion.button onClick={load} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} className="btn-outline">
          ↻ REFRESH
        </motion.button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          {[
            { label: 'COMPLIANCE', value: summary.compliance_status, color: statusColor },
            { label: 'AGENTS MONITORED', value: summary.agents_monitored, color: 'var(--gold)' },
            { label: 'FLAGGED AGENTS', value: summary.flagged_agents.length, color: summary.flagged_agents.length > 0 ? 'var(--warning)' : 'var(--online)' },
            { label: 'AVG BIAS RISK', value: `${(summary.avg_bias_risk * 100).toFixed(1)}%`, color: summary.avg_bias_risk > 0.3 ? 'var(--offline)' : summary.avg_bias_risk > 0.15 ? 'var(--warning)' : 'var(--online)' },
          ].map(({ label, value, color }) => (
            <div key={label} className="panel" style={{ padding: 20, textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 8 }}>{label}</div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: 26, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* DI gauge row */}
      {summary && (
        <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 14 }}>
            DISPARATE IMPACT (EEOC 4/5ths RULE — minimum ratio across agents)
          </div>
          <ProgressBar
            value={Math.round(summary.di_ratio_min * 100)}
            label={`DI Ratio: ${summary.di_ratio_min.toFixed(2)}`}
            variant={summary.di_ratio_min < 0.8 ? 'gold' : 'bronze'}
          />
          <div style={{ marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
            ≥ 0.80 = compliant (EEOC standard) &nbsp;•&nbsp; {summary.di_ratio_min >= 0.8 ? '✓ PASS' : '⚠ ADVERSE IMPACT DETECTED'}
          </div>
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Loading fairness metrics...
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1fr' : '1fr', gap: 20, marginBottom: 20 }}>
        {/* Agent table */}
        <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: 'var(--border-subtle)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2 }}>
            AGENT FAIRNESS ({agents.length})
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: 'var(--border-subtle)' }}>
                  {['AGENT', 'CHECKS', 'FLAGGED', 'BLOCKED', 'RISK SCORE', 'STATUS'].map((h) => (
                    <th key={h} style={{ padding: '8px 16px', textAlign: 'left', color: 'var(--text-dim)', fontSize: 9, letterSpacing: 1 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => {
                  const det = details.find((d) => d.agent === a.agent) || null
                  return (
                    <tr
                      key={a.agent}
                      onClick={() => setSelected(selected?.agent === a.agent ? null : det)}
                      style={{
                        borderBottom: 'var(--border-subtle)',
                        cursor: 'pointer',
                        background: selected?.agent === a.agent ? 'rgba(212,175,55,0.06)' : 'transparent',
                      }}
                    >
                      <td style={{ padding: '10px 16px', color: 'var(--text-primary)' }}>{a.agent}</td>
                      <td style={{ padding: '10px 16px', color: 'var(--text-secondary)' }}>{a.checks_total}</td>
                      <td style={{ padding: '10px 16px', color: a.flagged_count > 0 ? 'var(--warning)' : 'var(--text-dim)' }}>{a.flagged_count}</td>
                      <td style={{ padding: '10px 16px', color: a.blocked > 0 ? 'var(--offline)' : 'var(--text-dim)' }}>{a.blocked}</td>
                      <td style={{ padding: '10px 16px' }}>
                        <ProgressBar value={Math.round(a.risk_score * 100)} label="" variant={a.risk_score > 0.3 ? 'gold' : 'bronze'} />
                      </td>
                      <td style={{ padding: '10px 16px' }}>
                        <RiskBadge flagged={a.flagged} score={a.risk_score} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2 }}>
            <div className="panel" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2 }}>
                  DETAIL — {selected.agent.toUpperCase()}
                </div>
                <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 14 }}>✕</button>
              </div>

              {/* Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
                {[
                  { label: 'DP DIFF', value: selected.metrics.demographic_parity_diff.toFixed(3) },
                  { label: 'DP RATIO', value: selected.metrics.demographic_parity_ratio.toFixed(3) },
                  { label: 'DI RATIO', value: selected.metrics.disparate_impact.toFixed(3) },
                  { label: 'BIAS RISK', value: (selected.metrics.bias_risk_score * 100).toFixed(1) + '%' },
                  { label: 'TPR DIFF', value: selected.metrics.tpr_diff.toFixed(3) },
                  { label: 'FPR DIFF', value: selected.metrics.fpr_diff.toFixed(3) },
                ].map(({ label, value }) => (
                  <div key={label} style={{ background: 'rgba(255,255,255,0.02)', border: 'var(--border-subtle)', borderRadius: 8, padding: '10px 14px' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginBottom: 4, letterSpacing: 1 }}>{label}</div>
                    <div style={{ fontFamily: 'var(--font-heading)', fontSize: 18, color: 'var(--gold)' }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Group bars */}
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 8 }}>GROUP SELECTION RATES</div>
              {selected.groups.map((g) => (
                <div key={g.group} style={{ marginBottom: 8 }}>
                  <ProgressBar value={Math.round(g.selection_rate * 100)} label={`${g.group} (n=${g.n})`} variant="bronze" />
                </div>
              ))}

              {selected.last_check && (
                <div style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
                  Last check: {new Date(selected.last_check).toLocaleString()}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </div>

      {/* Recent checks */}
      {recentChecks.length > 0 && (
        <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: 'var(--border-subtle)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2 }}>
            RECENT CHECKS ({recentChecks.length})
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: 'var(--border-subtle)' }}>
                  {['TIME', 'AGENT', 'ACTION', 'GROUP', 'DECISION', 'OUTCOME'].map((h) => (
                    <th key={h} style={{ padding: '8px 14px', textAlign: 'left', color: 'var(--text-dim)', fontSize: 9, letterSpacing: 1 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentChecks.slice().reverse().map((c) => (
                  <tr key={c.check_id} style={{ borderBottom: 'var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', color: 'var(--text-dim)' }}>{new Date(c.ts).toLocaleTimeString()}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-primary)' }}>{c.agent}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{c.action}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--bronze)' }}>{c.demographic_group}</td>
                    <td style={{ padding: '8px 14px', color: c.decision ? 'var(--online)' : 'var(--offline)' }}>{c.decision ? 'YES' : 'NO'}</td>
                    <td style={{ padding: '8px 14px' }}>
                      <span style={{
                        color: c.outcome === 'block' ? 'var(--offline)' : c.outcome === 'log' ? 'var(--warning)' : 'var(--online)',
                        fontWeight: 700,
                      }}>
                        {c.outcome.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </motion.div>
  )
}
