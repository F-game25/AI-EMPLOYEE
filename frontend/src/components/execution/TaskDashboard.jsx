import React, { useEffect, useState, useCallback } from 'react'
import { useExecutionUpdates } from '../../hooks/useExecutionUpdates'
import TaskList from './TaskList'
import TaskDetail from './TaskDetail'
import ExecutionMetrics from './ExecutionMetrics'
import { Panel } from '../nexus-ui'
import './TaskDashboard.css'

const PHASE_NAMES = [
  'retrieve_relevant_nodes',
  'build_context',
  'classify_decision',
  'call_llm',
  'validate_tasks',
  'execute_tasks',
  'format_response',
  'update_graph',
  'monitor_and_improve',
  'validate_pipeline_integrity',
]

export default function TaskDashboard() {
  const { tasks, loading, error, subscribe } = useExecutionUpdates()
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterPriority, setFilterPriority] = useState('all')
  const [filterAgent, setFilterAgent] = useState('all')

  useEffect(() => {
    subscribe('tasks')
  }, [subscribe])

  const selectedTask = tasks.find(t => t.id === selectedTaskId) || null

  const filteredTasks = useCallback(() => {
    return tasks.filter(t => {
      if (filterStatus !== 'all' && t.status !== filterStatus) return false
      if (filterPriority !== 'all' && t.priority !== filterPriority) return false
      if (filterAgent !== 'all' && t.agentId !== filterAgent) return false
      return true
    })
  }, [tasks, filterStatus, filterPriority, filterAgent])()

  const statusCounts = {
    pending: tasks.filter(t => t.status === 'pending').length,
    running: tasks.filter(t => t.status === 'running').length,
    done: tasks.filter(t => t.status === 'done').length,
    failed: tasks.filter(t => t.status === 'failed').length,
  }

  const successRate = tasks.length > 0
    ? Math.round((statusCounts.done / (statusCounts.done + statusCounts.failed || 1)) * 100)
    : 0

  const avgLatency = tasks.length > 0
    ? Math.round(
        tasks
          .filter(t => t.duration)
          .reduce((sum, t) => sum + t.duration, 0) / tasks.filter(t => t.duration).length
      )
    : 0

  return (
    <div className="task-dashboard">
      {error && <div className="task-dashboard__error">{error}</div>}

      {/* Metrics Strip */}
      <ExecutionMetrics
        totalTasks={tasks.length}
        activeNow={statusCounts.running}
        successRate={successRate}
        avgLatency={avgLatency}
      />

      <div className="task-dashboard__main">
        {/* Left: Task List */}
        <div className="task-dashboard__left">
          <TaskList
            tasks={filteredTasks}
            selectedTaskId={selectedTaskId}
            onSelectTask={setSelectedTaskId}
            filterStatus={filterStatus}
            onFilterStatus={setFilterStatus}
            filterPriority={filterPriority}
            onFilterPriority={setFilterPriority}
            filterAgent={filterAgent}
            onFilterAgent={setFilterAgent}
            statusCounts={statusCounts}
            loading={loading}
          />
        </div>

        {/* Right: Task Detail */}
        <div className="task-dashboard__right">
          {selectedTask ? (
            <TaskDetail task={selectedTask} phaseNames={PHASE_NAMES} />
          ) : (
            <Panel title="Task Detail" corners={false} tone="cool">
              <div className="task-detail__placeholder">
                {loading ? 'Loading tasks...' : 'Select a task to view details'}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}
