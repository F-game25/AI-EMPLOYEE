import { useState } from 'react'
import NeuralNetworkPanel from './NeuralNetworkPanel'
import MemoryTreePanel from './MemoryTreePanel'
import DoctorPanel from './DoctorPanel'
import AgentsPanel from './AgentsPanel'
import HeartbeatPanel from './HeartbeatPanel'

const TABS = [
  { id: 'systems', label: 'SYSTEMS' },
  { id: 'power', label: 'POWER' },
  { id: 'heartbeat', label: 'HEARTBEAT' },
]

export default function SecondaryPanels() {
  const [activeTab, setActiveTab] = useState('systems')

  return (
    <section
      className="flex flex-col h-full"
      style={{
        width: '320px',
        borderLeft: '1px solid var(--border-gold-dim)',
        background: 'var(--bg-panel)',
      }}
      aria-label="Secondary control panels"
    >
      <div className="flex items-center gap-1 px-2 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="font-mono text-[11px] px-2 py-1"
            style={{
              borderRadius: '4px',
              border: activeTab === tab.id ? '1px solid var(--border-gold)' : '1px solid var(--border-subtle)',
              background: activeTab === tab.id ? 'rgba(245,196,0,0.08)' : 'rgba(255,255,255,0.02)',
              color: activeTab === tab.id ? 'var(--gold)' : 'var(--text-secondary)',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'systems' && (
          <div className="h-full overflow-y-auto">
            <NeuralNetworkPanel />
            <MemoryTreePanel />
            <DoctorPanel />
          </div>
        )}

        {activeTab === 'power' && (
          <div className="h-full overflow-hidden">
            <AgentsPanel />
          </div>
        )}

        {activeTab === 'heartbeat' && (
          <div className="h-full overflow-hidden">
            <HeartbeatPanel />
          </div>
        )}
      </div>
    </section>
  )
}
