import { useEffect } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import HeartbeatPanel from './dashboard/HeartbeatPanel'
import ChatPanel from './dashboard/ChatPanel'
import AgentsPanel from './dashboard/AgentsPanel'
import NeuralNetworkPanel from './dashboard/NeuralNetworkPanel'
import MemoryTreePanel from './dashboard/MemoryTreePanel'
import DoctorPanel from './dashboard/DoctorPanel'
import { useAppStore } from '../store/appStore'

export default function Dashboard() {
  const setAgents = useAppStore(s => s.setAgents)
  const setNnStatus = useAppStore(s => s.setNnStatus)
  const setMemoryTree = useAppStore(s => s.setMemoryTree)
  const setDoctorStatus = useAppStore(s => s.setDoctorStatus)

  // Fetch initial agents via relative URL (proxied to backend in dev)
  useEffect(() => {
    fetch(`http://${window.location.hostname}:3001/agents`)
      .then(r => r.json())
      .then(d => d.agents && setAgents(d.agents))
      .catch(() => {})
  }, [setAgents])

  // Fetch initial subsystem states from REST API
  useEffect(() => {
    const base = `http://${window.location.hostname}:3001`

    fetch(`${base}/api/brain/status`)
      .then(r => r.json())
      .then(d => setNnStatus(d))
      .catch(() => {})

    fetch(`${base}/api/memory/tree`)
      .then(r => r.json())
      .then(d => setMemoryTree(d))
      .catch(() => {})

    fetch(`${base}/api/doctor/status`)
      .then(r => r.json())
      .then(d => setDoctorStatus(d))
      .catch(() => {})
  }, [setNnStatus, setMemoryTree, setDoctorStatus])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed inset-0 flex flex-col scanlines"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* Top bar */}
      <TopBar />

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Heartbeat */}
        <div className="w-56 flex-shrink-0 overflow-hidden">
          <HeartbeatPanel />
        </div>

        {/* Center: Chat */}
        <div
          className="flex-1 min-w-0 overflow-hidden"
          style={{ borderLeft: '1px solid var(--border-gold-dim)', borderRight: '1px solid var(--border-gold-dim)' }}
        >
          <ChatPanel />
        </div>

        {/* Right: Stacked subsystem panels */}
        <div
          className="flex flex-col flex-shrink-0 overflow-hidden"
          style={{ width: '224px' }}
        >
          {/* Neural Network — top */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)' }}
          >
            <NeuralNetworkPanel />
          </div>

          {/* Memory Tree — middle */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)' }}
          >
            <MemoryTreePanel />
          </div>

          {/* Agents — flex-1 to fill remaining space */}
          <div className="flex-1 overflow-hidden" style={{ background: 'var(--bg-panel)' }}>
            <AgentsPanel />
          </div>

          {/* Doctor — bottom */}
          <div
            className="flex-shrink-0 overflow-y-auto"
            style={{ background: 'var(--bg-panel)', maxHeight: '220px' }}
          >
            <DoctorPanel />
          </div>
        </div>
      </div>

      {/* CRT vignette overlay — decorative only */}
      <div
        className="pointer-events-none fixed inset-0"
        aria-hidden="true"
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(0,0,0,0.45) 100%)',
          zIndex: 'var(--z-overlay)',
        }}
      />
    </motion.div>
  )
}
