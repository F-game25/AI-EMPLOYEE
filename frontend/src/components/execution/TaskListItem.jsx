import React from 'react'
import { StatusPill } from '../nexus-ui'
import './TaskListItem.css'

const STATUS_TONE = {
  pending: 'idle',
  running: 'gold',
  done: 'success',
  failed: 'alert',
}

export default function TaskListItem({ task, isSelected, onClick }) {
  const status = task.status || 'pending'
  const createdTime = task.createdAt
    ? new Date(task.createdAt).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'

  return (
    <div
      className={`task-list-item ${isSelected ? 'task-list-item--selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
    >
      <div className="task-list-item__header">
        <span className="task-list-item__id">{task.id}</span>
        <StatusPill
          label={status}
          tone={STATUS_TONE[status]}
          size="sm"
          dot={true}
          pulse={status === 'running'}
        />
      </div>
      <div className="task-list-item__intent">{task.intent || task.name || 'Untitled'}</div>
      {task.description && <div className="task-list-item__desc">{task.description}</div>}
      <div className="task-list-item__footer">
        {task.priority && (
          <span className="task-list-item__priority">{task.priority}</span>
        )}
        {task.agentId && (
          <span className="task-list-item__agent">{task.agentId}</span>
        )}
        <span className="task-list-item__time">{createdTime}</span>
      </div>
    </div>
  )
}
