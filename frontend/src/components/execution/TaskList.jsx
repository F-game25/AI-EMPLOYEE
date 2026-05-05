import React from 'react'
import { Panel, StatusPill } from '../nexus-ui'
import TaskListItem from './TaskListItem'
import './TaskList.css'

const TABS = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'running', label: 'Running' },
  { id: 'done', label: 'Done' },
  { id: 'failed', label: 'Failed' },
]

const PRIORITIES = [
  { id: 'all', label: 'Any Priority' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Medium' },
  { id: 'LOW', label: 'Low' },
]

export default function TaskList({
  tasks,
  selectedTaskId,
  onSelectTask,
  filterStatus,
  onFilterStatus,
  filterPriority,
  onFilterPriority,
  filterAgent,
  onFilterAgent,
  statusCounts,
  loading,
}) {
  // Extract unique agents
  const agents = [...new Set(tasks.map(t => t.agentId).filter(Boolean))]
  const agentOptions = [
    { id: 'all', label: 'All Agents' },
    ...agents.map(agent => ({ id: agent, label: agent })),
  ]

  return (
    <Panel title="Task Queue" corners={false} tone="gold">
      <div className="task-list">
        {/* Tabs */}
        <div className="task-list__tabs">
          {TABS.map(tab => {
            const count = statusCounts[tab.id] || 0
            const isActive = filterStatus === tab.id
            return (
              <button
                key={tab.id}
                className={`task-list__tab ${isActive ? 'task-list__tab--active' : ''}`}
                onClick={() => onFilterStatus(tab.id)}
                title={`${tab.label}: ${count} task${count !== 1 ? 's' : ''}`}
              >
                <span className="task-list__tab-label">{tab.label}</span>
                <span className="task-list__tab-count">{count}</span>
              </button>
            )
          })}
        </div>

        {/* Filters */}
        <div className="task-list__filters">
          <select
            className="task-list__select"
            value={filterPriority}
            onChange={e => onFilterPriority(e.target.value)}
            title="Filter by priority"
          >
            {PRIORITIES.map(p => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>

          <select
            className="task-list__select"
            value={filterAgent}
            onChange={e => onFilterAgent(e.target.value)}
            title="Filter by agent"
          >
            {agentOptions.map(a => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </div>

        {/* Task List */}
        <div className="task-list__items">
          {loading ? (
            <div className="task-list__placeholder">Loading tasks…</div>
          ) : tasks.length === 0 ? (
            <div className="task-list__placeholder">No tasks match filters</div>
          ) : (
            tasks.map(task => (
              <TaskListItem
                key={task.id}
                task={task}
                isSelected={selectedTaskId === task.id}
                onClick={() => onSelectTask(task.id)}
              />
            ))
          )}
        </div>
      </div>
    </Panel>
  )
}
