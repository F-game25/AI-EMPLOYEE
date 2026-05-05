import React, { useState } from 'react'
import AgentDetailModal from './AgentDetailModal'
import './AgentActivityWidget.css'

const STATUS_ICON = {
  idle: '◯',
  busy: '⟳',
  dead: '✕',
}

const STATUS_COLOR = {
  idle: '#888',
  busy: '#FFD97A',
  dead: '#EF4444',
}

export default function AgentActivityWidget({ agents = [] }) {
  const [selectedAgent, setSelectedAgent] = useState(null)

  const getAgentStatus = (agent) => {
    const lastSeen = agent.lastSeen ? new Date(agent.lastSeen).getTime() : 0
    const now = Date.now()
    const elapsed = now - lastSeen
    if (elapsed > 30000) return 'dead'
    if (agent.tasksInProgress && agent.tasksInProgress > 0) return 'busy'
    return 'idle'
  }

  const getUptimeBadge = (agent) => {
    const started = agent.startedAt ? new Date(agent.startedAt).getTime() : null
    if (!started) return null
    const uptimeMs = Date.now() - started
    const uptimeSecs = Math.floor(uptimeMs / 1000)
    if (uptimeSecs < 60) return `${uptimeSecs}s`
    if (uptimeSecs < 3600) return `${Math.floor(uptimeSecs / 60)}m`
    return `${Math.floor(uptimeSecs / 3600)}h`
  }

  return (
    <div className="agent-activity-widget">
      <div className="widget-header">
        <h3 className="widget-title">Active Agents</h3>
        <span className="agent-count">{agents.length}</span>
      </div>

      <div className="agents-list">
        {agents.length === 0 ? (
          <div className="empty-state">No active agents</div>
        ) : (
          agents.map(agent => {
            const status = getAgentStatus(agent)
            const uptime = getUptimeBadge(agent)
            return (
              <div
                key={agent.id}
                className="agent-card"
                onClick={() => setSelectedAgent(agent)}
              >
                <div className="agent-header">
                  <div className="agent-icon" style={{ color: STATUS_COLOR[status] }}>
                    {STATUS_ICON[status]}
                  </div>
                  <div className="agent-name">{agent.name || agent.id}</div>
                </div>
                <div className="agent-details">
                  {agent.currentTask && (
                    <div className="current-task" title={agent.currentTask}>
                      {agent.currentTask}
                    </div>
                  )}
                  {uptime && <div className="uptime-badge">{uptime}</div>}
                </div>
              </div>
            )
          })
        )}
      </div>

      {selectedAgent && (
        <AgentDetailModal
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  )
}
