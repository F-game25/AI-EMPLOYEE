import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import TertiaryPanel from '../ui/TertiaryPanel'

const MODE_COLORS = {
  OFF: '#ef4444',
  ON: '#eab308',
  AUTO: '#22c55e',
}

function StatRow({ label, value, color }) {
  return (
    <div className="flex justify-between font-mono text-[10px] py-0.5">
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ color: color || 'var(--text-secondary)' }}>{value}</span>
    </div>
  )
}

export default function AutonomyPanel() {
  const autonomy = useAppStore((s) => s.autonomyStatus)
  const [expanded, setExpanded] = useState(true)

  const mode = autonomy?.mode?.mode || 'OFF'
  const daemon = autonomy?.daemon || {}
  const queue = autonomy?.queue || {}
  const mColor = MODE_COLORS[mode] || '#ef4444'
  const isSimulated = autonomy?.data_source === 'simulated' || autonomy?.data_source === 'initializing'

  return (
    <article className="ds-card p-3 min-h-0 flex flex-col">
      <button
        className="flex items-center justify-between w-full text-left mb-1"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <motion.div
            animate={daemon.running ? { opacity: [1, 0.3, 1] } : { opacity: 0.3 }}
            transition={{ duration: 1.2, repeat: Infinity }}
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: mColor }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
            AUTONOMY ENGINE
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono" style={{ fontSize: '10px', color: mColor }}>
            {mode}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            {isSimulated && (
              <div
                className="font-mono mb-2 px-2 py-1 rounded"
                style={{ fontSize: '9px', color: 'var(--warning)', background: 'rgba(212,175,55,0.08)', border: '1px solid rgba(212,175,55,0.15)' }}
              >
                ⚠ Waiting for live backend connection
              </div>
            )}

            {/* Daemon status */}
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', paddingBottom: '6px', marginBottom: '6px' }}>
              <StatRow label="DAEMON" value={daemon.running ? '● RUNNING' : '○ STOPPED'} color={daemon.running ? '#22c55e' : '#ef4444'} />
              <StatRow label="CYCLES" value={(daemon.cycles || 0).toLocaleString()} />
              <StatRow label="INTERVAL" value={`${daemon.cycle_interval_s || 2}s`} />
              {daemon.last_cycle_at && (
                <StatRow label="LAST CYCLE" value={new Date(daemon.last_cycle_at).toLocaleTimeString('en-US', { hour12: false })} />
              )}
            </div>

            {/* Task stats */}
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', paddingBottom: '6px', marginBottom: '6px' }}>
              <StatRow label="PROCESSED" value={daemon.tasks_processed || 0} color="var(--gold)" />
              <StatRow label="SUCCEEDED" value={daemon.tasks_succeeded || 0} color="#22c55e" />
              <StatRow label="FAILED" value={daemon.tasks_failed || 0} color={daemon.tasks_failed > 0 ? '#ef4444' : 'var(--text-secondary)'} />
              {daemon.consecutive_errors > 0 && (
                <StatRow label="CONSEC ERRORS" value={daemon.consecutive_errors} color="#ef4444" />
              )}
            </div>

            {/* Queue */}
            <div>
              <StatRow label="QUEUE TOTAL" value={queue.total || 0} />
              <StatRow label="QUEUE ACTIVE" value={queue.active || 0} color={queue.active > 0 ? 'var(--gold)' : 'var(--text-muted)'} />
              {daemon.current_task_id && (
                <StatRow label="PROCESSING" value={daemon.current_task_id} color="var(--gold)" />
              )}
              {daemon.last_task_id && (
                <StatRow label="LAST TASK" value={daemon.last_task_id} />
              )}
            </div>

            {/* Emergency stop state */}
            {autonomy?.mode?.emergency_stopped && (
              <TertiaryPanel className="mt-2 p-2 font-mono text-[10px]" style={{ color: '#ef4444' }}>
                ⚠ EMERGENCY STOPPED — set mode to ON or AUTO to resume
              </TertiaryPanel>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  )
}
