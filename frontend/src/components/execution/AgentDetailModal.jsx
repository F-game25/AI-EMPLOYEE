import React, { useEffect, useState } from 'react'
import { API_URL } from '../../config/api'
import './AgentDetailModal.css'

export default function AgentDetailModal({ agent, onClose }) {
  const [details, setDetails] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchDetails = async () => {
      try {
        const res = await fetch(`${API_URL}/api/agents/${agent.id}/metrics`)
        if (res.ok) {
          setDetails(await res.json())
        }
      } catch (e) {
        console.error('Failed to fetch agent details:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchDetails()
  }, [agent.id])

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div className="agent-detail-modal-backdrop" onClick={handleBackdropClick}>
      <div className="agent-detail-modal">
        <div className="modal-header">
          <h2 className="modal-title">{agent.name || agent.id}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {loading ? (
          <div className="modal-loading">Loading metrics…</div>
        ) : details ? (
          <>
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-label">Tasks Completed</div>
                <div className="metric-value">{details.tasksCompleted || 0}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Success Rate</div>
                <div className="metric-value">
                  {details.successRate ? `${(details.successRate * 100).toFixed(1)}%` : '—'}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Avg Duration</div>
                <div className="metric-value">
                  {details.avgDuration ? `${Math.floor(details.avgDuration)}ms` : '—'}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Errors</div>
                <div className="metric-value" style={{ color: details.errors > 0 ? '#EF4444' : '#22C55E' }}>
                  {details.errors || 0}
                </div>
              </div>
            </div>

            {details.activityLog && details.activityLog.length > 0 && (
              <div className="activity-log">
                <h3 className="log-title">Recent Activity</h3>
                <div className="log-entries">
                  {details.activityLog.slice(0, 10).map((entry, i) => (
                    <div key={i} className="log-entry">
                      <span className="log-status" style={{
                        color: entry.status === 'completed' ? '#22C55E' : entry.status === 'failed' ? '#EF4444' : '#FFD97A'
                      }}>
                        {entry.status === 'completed' ? '✓' : entry.status === 'failed' ? '✕' : '⟳'}
                      </span>
                      <span className="log-task">{entry.taskName || 'Task'}</span>
                      <span className="log-duration">{entry.duration ? `${entry.duration}ms` : '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="modal-error">Failed to load metrics</div>
        )}
      </div>
    </div>
  )
}
