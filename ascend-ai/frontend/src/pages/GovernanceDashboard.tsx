import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'

const page = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.25 } }

interface GovSummary {
  status: string
  high_risk_events: number
  bias_alerts: number
  system_changes: number
  failures: number
  feedback_net: number
  last_digest_ts: string
  window_days: number
  live_data: boolean
}

interface DigestSection {
  count: number
  events?: EventEntry[]
  alerts?: BiasAlert[]
  changes?: ChangeEntry[]
  items?: FailureEntry[]
  error: string
}

interface EventEntry {
  id: string
  ts: string
  actor: string
  action: string
  risk_score: number
  trace_id: string
}

interface BiasAlert {
  id: string
  ts: string
  actor: string
  action: string
  risk_score: number
  outcome: string
  high_risk: boolean
}

interface ChangeEntry {
  ts: string
  component: string
  change: string
  actor: string
}

interface FailureEntry {
  ts: string
  component: string
  message: string
}

interface FeedbackSummary {
  thumbs_up: number
  thumbs_down: number
  net_reward: number
  total: number
  error: string
}

interface Digest {
  id: string
  ts: string
  window: { days: number; from: string; to: string }
  summary: string
  live_data: boolean
  sections: {
    high_risk_events: DigestSection
    bias_alerts: DigestSection & { alerts?: BiasAlert[] }
    system_changes: DigestSection & { changes?: ChangeEntry[] }
    failures: DigestSection
    feedback_summary: FeedbackSummary
  }
  markdown: string
}

function StatusBadge({ status }: { status: string }) {
  const color = status === 'OK' ? 'var(--online)' : status === 'WARN' ? 'var(--warning)' : 'var(--offline)'
  return (
    <span style={{
      padding: '3px 10px', borderRadius: 4,
      background: `${color}22`, border: `1px solid ${color}66`,
      color, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
    }}>
      {status}
    </span>
  )
}

function SectionCard({ title, count, color, children }: {
  title: string; count: number; color: string; children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="panel" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: '14px 20px', borderBottom: open ? 'var(--border-subtle)' : 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2 }}>{title}</div>
          <span style={{
            padding: '1px 8px', borderRadius: 20,
            background: `${color}22`, border: `1px solid ${color}55`,
            color, fontFamily: 'var(--font-mono)', fontSize: 10,
          }}>{count}</span>
        </div>
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>{open ? '▾' : '▸'}</span>
      </div>
      {open && <div style={{ padding: 20 }}>{children}</div>}
    </div>
  )
}

export function GovernanceDashboard() {
  const [summary, setSummary] = useState<GovSummary | null>(null)
  const [digest, setDigest] = useState<Digest | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [tab, setTab] = useState<'overview' | 'markdown'>('overview')

  const load = async () => {
    setLoading(true)
    try {
      const [sumRes, dgstRes] = await Promise.all([
        fetch('/api/governance/summary').then((r) => r.json()),
        fetch('/api/governance/digest').then((r) => r.json()),
      ])
      setSummary(sumRes)
      setDigest(dgstRes)
    } catch {
      // keep empty state
    }
    setLoading(false)
  }

  const runDigest = async () => {
    setRunning(true)
    try {
      const r = await fetch('/api/governance/digest/run', { method: 'POST' })
      const d = await r.json()
      if (d.digest) setDigest(d.digest)
      await load()
    } catch {
      // ignore
    }
    setRunning(false)
  }

  useEffect(() => { load() }, [])

  return (
    <motion.div {...page}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            🏛 GOVERNANCE DASHBOARD — Compliance & Audit
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 4 }}>
            Weekly digest • High-risk events • Bias alerts • System changes • Failures
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <motion.button onClick={load} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} className="btn-outline">
            ↻ REFRESH
          </motion.button>
          <motion.button
            onClick={runDigest}
            disabled={running}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn-gold"
            style={{ opacity: running ? 0.6 : 1 }}
          >
            {running ? '⏳ GENERATING…' : '▶ RUN DIGEST'}
          </motion.button>
        </div>
      </div>

      {/* Status row */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'STATUS', value: <StatusBadge status={summary.status} />, raw: summary.status },
            { label: 'HIGH-RISK EVENTS', value: summary.high_risk_events, raw: summary.high_risk_events > 0 ? 'warn' : 'ok' },
            { label: 'BIAS ALERTS', value: summary.bias_alerts, raw: summary.bias_alerts > 0 ? 'warn' : 'ok' },
            { label: 'SYS CHANGES', value: summary.system_changes, raw: 'ok' },
            { label: 'FAILURES', value: summary.failures, raw: summary.failures > 0 ? 'warn' : 'ok' },
            { label: 'FEEDBACK NET', value: `+${summary.feedback_net}`, raw: 'ok' },
          ].map(({ label, value, raw }) => (
            <div key={label} className="panel" style={{ padding: 16, textAlign: 'center' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 6 }}>{label}</div>
              <div style={{
                fontFamily: 'var(--font-heading)', fontSize: typeof value === 'number' ? 24 : 14,
                fontWeight: 700,
                color: raw === 'warn' ? 'var(--warning)' : raw === 'ok' ? 'var(--online)' : 'var(--text-primary)',
              }}>
                {value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Meta info */}
      {digest && (
        <div style={{ display: 'flex', gap: 20, marginBottom: 20, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
          <span>Digest ID: {digest.id}</span>
          <span>Generated: {new Date(digest.ts).toLocaleString()}</span>
          <span>Window: {digest.window.days} days</span>
          {!digest.live_data && (
            <span style={{ color: 'var(--warning)' }}>⚠ Demo data — runtime not connected</span>
          )}
          {digest.live_data && (
            <span style={{ color: 'var(--online)' }}>✓ Live data</span>
          )}
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Loading governance digest...
        </div>
      )}

      {/* Summary banner */}
      {digest && (
        <div className="panel" style={{ padding: '14px 20px', marginBottom: 20, background: 'rgba(212,175,55,0.04)' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 1 }}>
            SUMMARY &nbsp;•&nbsp;
          </span>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-secondary)' }}>
            {digest.summary}
          </span>
        </div>
      )}

      {/* Tab bar */}
      <div className="tab-bar" style={{ marginBottom: 20 }}>
        {(['overview', 'markdown'] as const).map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {tab === 'overview' && digest && (
        <div>
          {/* High-risk events */}
          <SectionCard
            title="HIGH-RISK EVENTS"
            count={digest.sections.high_risk_events.count}
            color="var(--offline)"
          >
            {digest.sections.high_risk_events.count === 0 && (
              <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>No high-risk events in window.</div>
            )}
            {(digest.sections.high_risk_events.events || []).map((e) => (
              <div key={e.id} style={{
                display: 'flex', gap: 16, padding: '8px 0', borderBottom: 'var(--border-subtle)',
                fontFamily: 'var(--font-mono)', fontSize: 11, alignItems: 'center',
              }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 160 }}>{new Date(e.ts).toLocaleString()}</span>
                <span style={{ color: 'var(--offline)', minWidth: 120 }}>{e.actor}</span>
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{e.action}</span>
                <span style={{
                  padding: '2px 8px', borderRadius: 4, background: 'rgba(239,68,68,0.15)',
                  color: 'var(--offline)', border: '1px solid rgba(239,68,68,0.3)',
                }}>
                  risk {e.risk_score.toFixed(2)}
                </span>
              </div>
            ))}
          </SectionCard>

          {/* Bias alerts */}
          <SectionCard
            title="BIAS ALERTS"
            count={digest.sections.bias_alerts.count}
            color="var(--warning)"
          >
            {digest.sections.bias_alerts.count === 0 && (
              <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>No bias alerts in window.</div>
            )}
            {(digest.sections.bias_alerts.alerts || []).map((a) => (
              <div key={a.id} style={{
                display: 'flex', gap: 16, padding: '8px 0', borderBottom: 'var(--border-subtle)',
                fontFamily: 'var(--font-mono)', fontSize: 11, alignItems: 'center',
              }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 160 }}>{new Date(a.ts).toLocaleString()}</span>
                <span style={{ color: 'var(--warning)', minWidth: 120 }}>{a.actor}</span>
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{a.action}</span>
                <span style={{
                  padding: '2px 8px', borderRadius: 4,
                  background: a.outcome === 'block' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                  color: a.outcome === 'block' ? 'var(--offline)' : 'var(--warning)',
                  border: '1px solid currentColor',
                }}>
                  {a.outcome.toUpperCase()}
                </span>
              </div>
            ))}
          </SectionCard>

          {/* System changes */}
          <SectionCard
            title="SYSTEM CHANGES"
            count={digest.sections.system_changes.count}
            color="var(--bronze)"
          >
            {(digest.sections.system_changes.changes || []).length === 0 && (
              <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>No system changes in window.</div>
            )}
            {(digest.sections.system_changes.changes || []).map((c, i) => (
              <div key={i} style={{
                display: 'flex', gap: 16, padding: '8px 0', borderBottom: 'var(--border-subtle)',
                fontFamily: 'var(--font-mono)', fontSize: 11,
              }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 160 }}>{new Date(c.ts).toLocaleString()}</span>
                <span style={{ color: 'var(--bronze)', minWidth: 120 }}>{c.component}</span>
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{c.change}</span>
                <span style={{ color: 'var(--text-dim)' }}>{c.actor}</span>
              </div>
            ))}
          </SectionCard>

          {/* Failures */}
          <SectionCard
            title="FAILURES"
            count={digest.sections.failures.count}
            color="var(--offline)"
          >
            {digest.sections.failures.count === 0 && (
              <div style={{ color: 'var(--online)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>✓ No failures in window.</div>
            )}
          </SectionCard>

          {/* Feedback */}
          <div className="panel" style={{ padding: 20 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 14 }}>FEEDBACK SUMMARY</div>
            <div style={{ display: 'flex', gap: 24, fontFamily: 'var(--font-mono)', fontSize: 13 }}>
              <span style={{ color: 'var(--online)' }}>👍 {digest.sections.feedback_summary.thumbs_up}</span>
              <span style={{ color: 'var(--offline)' }}>👎 {digest.sections.feedback_summary.thumbs_down}</span>
              <span style={{ color: 'var(--gold)' }}>Net reward: +{digest.sections.feedback_summary.net_reward}</span>
              <span style={{ color: 'var(--text-dim)' }}>Total: {digest.sections.feedback_summary.total}</span>
            </div>
          </div>
        </div>
      )}

      {tab === 'markdown' && digest && (
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 14 }}>MARKDOWN REPORT</div>
          <pre style={{
            fontFamily: 'var(--font-mono)', fontSize: 12,
            color: 'var(--text-secondary)', lineHeight: 1.7,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {digest.markdown}
          </pre>
        </div>
      )}
    </motion.div>
  )
}
