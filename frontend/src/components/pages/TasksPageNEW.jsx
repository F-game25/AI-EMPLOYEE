import React, { useState, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import { HolographicPanel } from '../holographic/HolographicPanel';
import { StatusDot, Badge, MiniBar } from '../ui/primitives';
import './TasksPageNEW.css';

/**
 * TasksPageNEW — Task orchestration in spatial holographic layout
 * Grid: Task queue (TL), active tasks (T), priority filters (TR),
 *       task details (L), timeline (C), resource allocation (R),
 *       history (BL), analytics (B), scheduling (BR)
 */

export const TasksPageNEW = () => {
  const { taskList = [] } = useAppStore();
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  useEffect(() => {
    const defaultTasks = [
      { id: 1, name: 'Process Agent Reports', status: 'running', priority: 'HIGH', progress: 65, eta: '12m', assignee: 'Agent-01', memory: 245, cpu: 68 },
      { id: 2, name: 'Update Knowledge Base', status: 'queued', priority: 'MEDIUM', progress: 0, eta: '8m', assignee: 'Agent-02', memory: 0, cpu: 0 },
      { id: 3, name: 'Validate Revenue Pipeline', status: 'running', priority: 'HIGH', progress: 34, eta: '25m', assignee: 'Agent-03', memory: 156, cpu: 42 },
      { id: 4, name: 'Backup System State', status: 'completed', priority: 'LOW', progress: 100, eta: '0m', assignee: 'Agent-04', memory: 0, cpu: 0 },
      { id: 5, name: 'Optimize Memory Index', status: 'running', priority: 'MEDIUM', progress: 78, eta: '5m', assignee: 'Agent-05', memory: 312, cpu: 51 },
    ];
    setTasks(defaultTasks);
    if (!selectedTask && defaultTasks.length > 0) {
      setSelectedTask(defaultTasks[0]);
    }
  }, [selectedTask]);

  const filteredTasks = tasks.filter(t => {
    if (priorityFilter !== 'ALL' && t.priority !== priorityFilter) return false;
    if (statusFilter !== 'ALL' && t.status !== statusFilter) return false;
    return true;
  });

  const activeTasks = tasks.filter(t => t.status === 'running');
  const queuedTasks = tasks.filter(t => t.status === 'queued');
  const completedToday = tasks.filter(t => t.status === 'completed').length;

  return (
    <div className="tasks-page-new">
      {/* TOP-LEFT: Task Queue */}
      <HolographicPanel title="TASK QUEUE" tone="gold" position="TL" isDraggable isResizable>
        <div className="queue-list">
          {filteredTasks.map(task => (
            <div
              key={task.id}
              className={`queue-item ${selectedTask?.id === task.id ? 'selected' : ''}`}
              onClick={() => setSelectedTask(task)}
            >
              <StatusDot status={task.status} />
              <span className="queue-name">{task.name}</span>
              <span className={`queue-priority ${task.priority.toLowerCase()}`}>
                {task.priority[0]}
              </span>
            </div>
          ))}
        </div>
      </HolographicPanel>

      {/* TOP-CENTER: Active Tasks */}
      <HolographicPanel title="ACTIVE EXECUTION" tone="purple" position="T" isDraggable>
        <div className="active-tasks-grid">
          <TaskMetric label="Running" value={activeTasks.length} color="#e5c76b" />
          <TaskMetric label="Queued" value={queuedTasks.length} color="#a855f7" />
          <TaskMetric label="Completed" value={completedToday} color="#22c55e" />
          <TaskMetric label="Total" value={tasks.length} color="#e8e8f0" />
        </div>
      </HolographicPanel>

      {/* TOP-RIGHT: Priority Filters */}
      <HolographicPanel title="FILTERS" tone="bronze" position="TR" isDraggable>
        <div className="filters-container">
          <div className="filter-group">
            <div className="filter-label">Priority</div>
            {['ALL', 'HIGH', 'MEDIUM', 'LOW'].map(p => (
              <button
                key={p}
                className={`filter-btn ${priorityFilter === p ? 'active' : ''}`}
                onClick={() => setPriorityFilter(p)}
              >
                {p}
              </button>
            ))}
          </div>
          <div className="filter-group">
            <div className="filter-label">Status</div>
            {['ALL', 'running', 'queued', 'completed'].map(s => (
              <button
                key={s}
                className={`filter-btn ${statusFilter === s ? 'active' : ''}`}
                onClick={() => setStatusFilter(s)}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </HolographicPanel>

      {/* LEFT: Task Details */}
      {selectedTask && (
        <HolographicPanel title="TASK DETAILS" tone="silver" position="L" isDraggable isResizable>
          <div className="task-details">
            <div className="detail-row">
              <span className="detail-label">Name:</span>
              <span className="detail-value">{selectedTask.name}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Status:</span>
              <Badge label={selectedTask.status.toUpperCase()} color={selectedTask.status === 'running' ? 'gold' : 'silver'} />
            </div>
            <div className="detail-row">
              <span className="detail-label">Priority:</span>
              <Badge label={selectedTask.priority} color={selectedTask.priority === 'HIGH' ? 'crimson' : 'gold'} />
            </div>
            <div className="detail-row">
              <span className="detail-label">Progress:</span>
              <MiniBar value={selectedTask.progress} max={100} />
            </div>
            <div className="detail-row">
              <span className="detail-label">ETA:</span>
              <span className="detail-value">{selectedTask.eta}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Assigned To:</span>
              <span className="detail-value">{selectedTask.assignee}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Memory:</span>
              <span className="detail-value">{selectedTask.memory} MB</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">CPU:</span>
              <span className="detail-value">{selectedTask.cpu}%</span>
            </div>
          </div>
        </HolographicPanel>
      )}

      {/* CENTER: Timeline */}
      <HolographicPanel title="TIMELINE" tone="purple" position="B" isDraggable isResizable>
        <div className="timeline">
          {activeTasks.map((task, idx) => (
            <div key={idx} className="timeline-event">
              <div className="timeline-time">{task.eta}</div>
              <div className="timeline-content">
                <div className="timeline-title">{task.name}</div>
                <div className="timeline-bar">
                  <div className="timeline-fill" style={{ width: `${task.progress}%` }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </HolographicPanel>

      {/* RIGHT: Resource Allocation */}
      <HolographicPanel title="RESOURCES" tone="gold" position="R" isDraggable isResizable>
        <div className="resource-grid">
          {activeTasks.slice(0, 3).map(task => (
            <ResourceCard key={task.id} name={task.assignee} memory={task.memory} cpu={task.cpu} />
          ))}
        </div>
      </HolographicPanel>

      {/* BOTTOM-LEFT: History */}
      <HolographicPanel title="HISTORY" tone="crimson" position="BL" isDraggable isResizable>
        <div className="history-list">
          <HistoryItem time="14:23" event="Task completed" detail="Validate Revenue Pipeline" />
          <HistoryItem time="13:58" event="Task started" detail="Process Agent Reports" />
          <HistoryItem time="13:45" event="Task queued" detail="Update Knowledge Base" />
          <HistoryItem time="13:12" event="Task completed" detail="Backup System State" />
        </div>
      </HolographicPanel>

      {/* BOTTOM-RIGHT: Analytics */}
      <HolographicPanel title="ANALYTICS" tone="silver" position="BR" isDraggable>
        <div className="analytics-stats">
          <StatBox label="Avg Duration" value="8.5m" />
          <StatBox label="Success Rate" value="94.2%" />
          <StatBox label="Throughput" value="12/h" />
        </div>
      </HolographicPanel>
    </div>
  );
};

function TaskMetric({ label, value, color }) {
  return (
    <div className="task-metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function ResourceCard({ name, memory, cpu }) {
  return (
    <div className="resource-card">
      <div className="resource-name">{name}</div>
      <div className="resource-metric">
        <span>RAM:</span>
        <span className="resource-value">{memory}MB</span>
      </div>
      <div className="resource-metric">
        <span>CPU:</span>
        <span className="resource-value">{cpu}%</span>
      </div>
    </div>
  );
}

function HistoryItem({ time, event, detail }) {
  return (
    <div className="history-item">
      <div className="history-time">{time}</div>
      <div className="history-content">
        <div className="history-event">{event}</div>
        <div className="history-detail">{detail}</div>
      </div>
    </div>
  );
}

function StatBox({ label, value }) {
  return (
    <div className="stat-box">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

export default TasksPageNEW;
