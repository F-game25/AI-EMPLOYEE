import { useEffect } from 'react'
import { motion } from 'framer-motion'
import TopBar from './dashboard/TopBar'
import HeartbeatPanel from './dashboard/HeartbeatPanel'
import ChatPanel from './dashboard/ChatPanel'
import AgentsPanel from './dashboard/AgentsPanel'
import { useAppStore } from '../store/appStore'

export default function Dashboard() {
  const setAgents = useAppStore(s => s.setAgents)

  // Fetch initial agents
  useEffect(() => {
    fetch('http://localhost:3001/agents')
      .then(r => r.json())
      .then(d => d.agents && setAgents(d.agents))
      .catch(() => {})
  }, [setAgents])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed inset-0 flex flex-col scanlines"
      style={{ background: '#050505' }}
    >
      {/* Top bar */}
      <TopBar />

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Heartbeat */}
        <div className="w-64 flex-shrink-0 overflow-hidden">
          <HeartbeatPanel />
        </div>

        {/* Center: Chat */}
        <div
          className="flex-1 overflow-hidden"
          style={{ borderLeft: '1px solid rgba(245,196,0,0.05)', borderRight: '1px solid rgba(245,196,0,0.05)' }}
        >
          <ChatPanel />
        </div>

        {/* Right: Agents */}
        <div className="w-56 flex-shrink-0 overflow-hidden">
          <AgentsPanel />
        </div>
      </div>

      {/* CRT glow overlay */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(0,0,0,0.4) 100%)',
          zIndex: 100,
        }}
      />
    </motion.div>
  )
}
