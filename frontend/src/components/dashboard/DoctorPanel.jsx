import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const GRADE_COLORS = {
  A: 'var(--success)',
  B: '#60a5fa',
  C: 'var(--warning)',
  D: 'var(--error)',
}

const SEVERITY_COLORS = {
  critical: 'var(--error)',
  warning: 'var(--warning)',
  info: 'var(--text-secondary)',
}

const SCORE_LABELS = {
  neural_network: 'Neural Brain',
  memory: 'Memory',
  agents: 'Agents',
  system: 'System',
  crm: 'CRM',
  finance: 'Finance',
  email: 'Email',
  support: 'Support',
}

function ScoreBar({ label, score }) {
  const color = score >= 80 ? 'var(--success)' : score >= 60 ? '#60a5fa' : score >= 40 ? 'var(--warning)' : 'var(--error)'
  return (
    <div className="mb-1.5">
      <div className="flex justify-between mb-0.5">
        <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
          {SCORE_LABELS[label] || label.toUpperCase()}
        </span>
        <span className="font-mono" style={{ fontSize: '10px', color }}>
          {score}
        </span>
      </div>
      <div
        style={{
          height: '3px',
          background: 'rgba(255,255,255,0.06)',
          borderRadius: '2px',
          overflow: 'hidden',
        }}
      >
        <motion.div
          animate={{ width: `${Math.min(score, 100)}%` }}
          transition={{ duration: 0.8 }}
          style={{ height: '100%', background: color, borderRadius: '2px' }}
        />
      </div>
    </div>
  )
}

export default function DoctorPanel() {
  const doctor = useAppStore(s => s.doctorStatus)
  const [expanded, setExpanded] = useState(true)

  const gradeColor = doctor.grade ? GRADE_COLORS[doctor.grade] : 'var(--text-muted)'
  const scores = doctor.scores || {}
  const scoreEntries = Object.entries(scores)

  return (
    <div className="flex flex-col flex-shrink-0">
      {/* Header */}
      <button
        className="flex items-center justify-between px-3 py-2 w-full text-left"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          borderTop: '1px solid var(--border-gold-dim)',
        }}
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-controls="doctor-panel-body"
      >
        <div className="flex items-center gap-2">
          <motion.div
            animate={doctor.available ? { opacity: [1, 0.4, 1] } : { opacity: 0.3 }}
            transition={{ duration: 2.5, repeat: Infinity }}
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            aria-hidden="true"
            style={{ background: doctor.available ? 'var(--success)' : 'var(--text-muted)' }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
            DOCTOR
          </span>
        </div>
        <div className="flex items-center gap-2">
          {doctor.grade && (
            <span
              className="font-mono font-bold"
              style={{ fontSize: '13px', color: gradeColor }}
              aria-label={`System grade: ${doctor.grade}`}
            >
              {doctor.grade}
            </span>
          )}
          <span
            className="font-mono"
            style={{ fontSize: '10px', color: 'var(--text-muted)' }}
          >
            {doctor.overall_score}/100
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </button>

      {/* Body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id="doctor-panel-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="px-3 pb-3">
              {doctor.data_source === 'simulated' && (
                <div
                  className="font-mono mb-2 px-2 py-1 rounded"
                  style={{ fontSize: '9px', color: 'var(--warning)', background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.15)' }}
                >
                  ⚠ DEGRADED — showing simulated diagnostics (no live backend)
                </div>
              )}
              {/* Score bars */}
              {scoreEntries.length > 0 && (
                <div className="mb-2">
                  {scoreEntries.map(([key, val]) => (
                    <ScoreBar key={key} label={key} score={val} />
                  ))}
                </div>
              )}

              {/* Issues */}
              {doctor.issues && doctor.issues.length > 0 && (
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px' }}>
                  <div className="font-mono mb-1" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    ISSUES ({doctor.issues.length})
                  </div>
                  {doctor.issues.slice(0, 3).map((issue, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-1.5 mb-1"
                    >
                      <span
                        className="font-mono flex-shrink-0"
                        style={{ fontSize: '9px', color: SEVERITY_COLORS[issue.severity] || 'var(--text-muted)', marginTop: '1px' }}
                      >
                        {issue.severity === 'critical' ? '✕' : issue.severity === 'warning' ? '⚠' : 'ℹ'}
                      </span>
                      <span
                        className="font-mono"
                        style={{ fontSize: '9px', color: 'var(--text-secondary)', lineHeight: '1.5' }}
                      >
                        {issue.area}: {issue.issue}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Strengths */}
              {doctor.strengths && doctor.strengths.length > 0 && (
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px', marginTop: '4px' }}>
                  {doctor.strengths.slice(0, 2).map((s, i) => (
                    <div key={i} className="flex items-center gap-1.5 mb-0.5">
                      <span style={{ fontSize: '9px', color: 'var(--success)' }}>✓</span>
                      <span className="font-mono" style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>
                        {s}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {!doctor.available && (
                <p className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
                  Initializing diagnostics…
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
