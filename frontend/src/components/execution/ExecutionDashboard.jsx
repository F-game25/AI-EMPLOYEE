import React, { useEffect, useState } from 'react'
import { useExecutionUpdates } from '../../hooks/useExecutionUpdates'
import TaskListItem from './TaskListItem'
import PipelineVisualizer from './PipelineVisualizer'
import AgentActivityWidget from './AgentActivityWidget'
import './ExecutionDashboard.css'
import { API_URL } from '../../config/api'

export default function ExecutionDashboard() {
  const { tasks, pipeline, agents, loading, error, subscribe } = useExecutionUpdates()
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const [selectedTaskDetails, setSelectedTaskDetails] = useState(null)

  useEffect(() => {
    subscribe('tasks')
    subscribe('agents')
    subscribe('execution-trace')
  }, [subscribe])

  useEffect(() => {
    if (selectedTaskId && tasks.length > 0) {
      const task = tasks.find(t => t.id === selectedTaskId)
      if (task) setSelectedTaskDetails(task)
    }
  }, [tasks, selectedTaskId])

  const handleTaskSelect = (task) => {
    setSelectedTaskId(task.id)
    setSelectedTaskDetails(task)
  }

  return (
    <div className="execution-dashboard">
      {error && <div className="dashboard-error">{error}</div>}

      <div className="dashboard-container">
        {/* Left Panel: Task List */}
        <div className="dashboard-panel left-panel">
          <div className="panel-header">
            <h3 className="panel-title">Tasks</h3>
            <span className="task-count">{tasks.length}</span>
          </div>
          <div className="tasks-list">
            {loading ? (
              <div className="panel-placeholder">Loading tasks…</div>
            ) : tasks.length === 0 ? (
              <div className="panel-placeholder">No tasks</div>
            ) : (
              tasks.map(task => (
                <TaskListItem
                  key={task.id}
                  task={task}
                  isSelected={selectedTaskId === task.id}
                  onClick={() => handleTaskSelect(task)}
                />
              ))
            )}
          </div>
        </div>

        {/* Center Panel: Pipeline Visualizer */}
        <div className="dashboard-panel center-panel">
          <PipelineVisualizer pipeline={selectedTaskDetails?.pipeline || pipeline} />
        </div>

        {/* Right Panel: Agent Activity */}
        <div className="dashboard-panel right-panel">
          <AgentActivityWidget agents={agents} />
        </div>
      </div>

      {/* Task Detail Footer (Mobile/Compact View) */}
      {selectedTaskDetails && (
        <div className="task-detail-footer">
          <div className="detail-row">
            <span className="detail-label">Task:</span>
            <span className="detail-value">{selectedTaskDetails.name}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Status:</span>
            <span className="detail-value" style={{
              color: selectedTaskDetails.status === 'completed' ? '#22C55E' : selectedTaskDetails.status === 'failed' ? '#EF4444' : '#FFD97A'
            }}>
              {selectedTaskDetails.status}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
