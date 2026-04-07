import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/appStore'

const STATUS_CONFIG = {
  idle: { color: '#555', label: 'IDLE', dot: '#555' },
  working: { color: '#F5C400', label: 'WORKING', dot: '#F5C400' },
  error: { color: '#ff3366', label: 'ERROR', dot: '#ff3366' },
}

export default function AgentsPanel() {
  const agents = useAppStore(s => s.agents)

  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: 'rgba(10,10,10,0.8)',
        borderLeft: '1px solid rgba(245,196,0,0.1)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 flex-shrink-0"
        style={{ borderBottom: '1px solid rgba(245,196,0,0.1)' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: '#F5C400' }}>
          AGENTS
        </span>
        <span className="font-mono text-xs" style={{ color: '#444' }}>
          {agents.filter(a => a.status === 'working').length}/{agents.length} active
        </span>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1.5">
        <AnimatePresence>
          {agents.map((agent) => {
            const cfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.idle
            return (
              <motion.div
                key={agent.id}
                layout
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className="px-3 py-2 rounded"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${agent.status === 'working' ? 'rgba(245,196,0,0.2)' : 'rgba(255,255,255,0.04)'}`,
                  boxShadow: agent.status === 'working' ? '0 0 10px rgba(245,196,0,0.05)' : 'none',
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs font-semibold" style={{ color: '#e8e8e8' }}>
                    {agent.name}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <motion.div
                      animate={agent.status === 'working' ? { opacity: [1, 0.3, 1] } : { opacity: 1 }}
                      transition={{ duration: 1, repeat: Infinity }}
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: cfg.dot }}
                    />
                    <span className="font-mono" style={{ fontSize: '10px', color: cfg.color }}>
                      {cfg.label}
                    </span>
                  </div>
                </div>
                {agent.task && (
                  <div className="font-mono leading-tight" style={{ fontSize: '10px', color: '#444' }}>
                    {agent.task}
                  </div>
                )}
                <div className="font-mono mt-1" style={{ fontSize: '10px', color: '#333' }}>
                  {agent.type}
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
