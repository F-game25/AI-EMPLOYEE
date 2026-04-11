import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const STATUS_CONFIG = {
  idle: { color: 'var(--text-muted)', label: 'IDLE', dot: 'var(--text-muted)' },
  running: { color: 'var(--info)', label: 'RUNNING', dot: 'var(--info)' },
  busy: { color: 'var(--gold)', label: 'BUSY', dot: 'var(--gold)' },
}

export default function AgentsPanel() {
  const agents = useAppStore(s => s.agents)
  const activeCount = agents.filter(a => a.state === 'running' || a.state === 'busy').length

  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: 'var(--bg-panel)',
        borderLeft: '1px solid var(--border-gold-dim)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2.5 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-gold-dim)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: 'var(--gold)' }}>
          AGENTS
        </span>
        {agents.length > 0 && (
          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
            {activeCount}/{agents.length}
          </span>
        )}
      </div>

      {/* Agent list */}
      <div
        role="list"
        aria-label="Agent status list"
        className="flex-1 overflow-y-auto px-2 py-2 space-y-1.5"
      >
        {agents.length === 0 && (
          <p
            className="font-mono text-xs text-center mt-4"
            style={{ color: 'var(--text-muted)' }}
          >
            No agents connected
          </p>
        )}

        <AnimatePresence>
          {agents.map((agent) => {
            const cfg = STATUS_CONFIG[agent.state] || STATUS_CONFIG.idle
            return (
              <motion.div
                key={agent.id}
                role="listitem"
                layout
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className="px-3 py-2 rounded"
                style={{
                  background: agent.state === 'busy'
                    ? 'rgba(245,196,0,0.04)'
                    : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${agent.state === 'busy'
                    ? 'rgba(245,196,0,0.18)'
                    : 'var(--border-subtle)'}`,
                  cursor: 'default',
                  transition: 'background 0.2s, border-color 0.2s',
                }}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span
                    className="font-mono text-xs font-semibold truncate"
                    style={{ color: 'var(--text-primary)' }}
                    title={agent.name}
                  >
                    {agent.name}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
                    <motion.div
                      animate={agent.state === 'busy' ? { opacity: [1, 0.3, 1] } : { opacity: 1 }}
                      transition={{ duration: 1, repeat: Infinity }}
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      aria-hidden="true"
                      style={{ background: cfg.dot }}
                    />
                    <span
                      className="font-mono"
                      style={{ fontSize: '12px', color: cfg.color }}
                      aria-label={`Status: ${cfg.label}`}
                    >
                      {cfg.label}
                    </span>
                  </div>
                </div>

                {agent.task && (
                  <div
                    className="font-mono leading-snug truncate"
                    style={{ fontSize: '11px', color: 'var(--text-muted)' }}
                    title={agent.task}
                  >
                    {agent.task}
                  </div>
                )}

                <div
                  className="font-mono mt-0.5"
                  style={{ fontSize: '11px', color: 'var(--text-muted)' }}
                >
                  {agent.type} · {agent.health || 'healthy'}
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
