import React, { useState } from 'react'
import { Panel, StatusPill, SectionLabel } from '../nexus-ui'
import PipelineVisualization from './PipelineVisualization'
import './TaskDetail.css'

const STATUS_TONE = {
  pending: 'idle',
  running: 'cool',
  done: 'success',
  failed: 'alert',
}

const STATUS_ICON = {
  pending: '—',
  running: '◉',
  done: '✓',
  failed: '✗',
}

function JSONViewer({ data, maxHeight = 300 }) {
  const [expanded, setExpanded] = useState(false)
  const json = JSON.stringify(data, null, 2)
  const lines = json.split('\n').length

  return (
    <div className="json-viewer">
      <div
        className={`json-viewer__content ${expanded ? 'json-viewer__content--expanded' : ''}`}
        style={{ maxHeight: expanded ? 'none' : `${maxHeight}px` }}
      >
        <pre>{json}</pre>
      </div>
      {lines > 20 && (
        <button
          className="json-viewer__toggle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      )}
    </div>
  )
}

function PhaseRow({ phase, index, phaseNames, onSelect }) {
  const phaseName = phaseNames[index] || `Phase ${index + 1}`
  const duration = phase.endTime && phase.startTime
    ? Math.round((new Date(phase.endTime) - new Date(phase.startTime)) / 1000)
    : null

  return (
    <div
      className={`phase-row phase-row--${phase.status}`}
      onClick={() => onSelect && onSelect(index)}
      role="button"
      tabIndex={0}
    >
      <div className="phase-row__status">
        <span className="phase-row__icon">{STATUS_ICON[phase.status]}</span>
      </div>
      <div className="phase-row__info">
        <div className="phase-row__num">{index + 1}</div>
        <div className="phase-row__name">{phaseName}</div>
      </div>
      <div className="phase-row__time">
        {duration !== null && <span className="phase-row__duration">{duration}s</span>}
        {phase.startTime && <span className="phase-row__timestamp">{new Date(phase.startTime).toLocaleTimeString()}</span>}
      </div>
    </div>
  )
}

export default function TaskDetail({ task, phaseNames }) {
  const [selectedPhaseIndex, setSelectedPhaseIndex] = useState(null)
  const selectedPhase = selectedPhaseIndex !== null ? task.executionTrace?.[selectedPhaseIndex] : null

  const totalDuration = task.duration ? Math.round(task.duration / 1000) : null

  return (
    <Panel title="Task Detail" corners={false} tone="gold" flush>
      <div className="task-detail">
        {/* Header */}
        <div className="task-detail__header">
          <div className="task-detail__id-wrap">
            <span className="task-detail__id">{task.id}</span>
            <StatusPill label={task.status} tone={STATUS_TONE[task.status]} size="sm" dot={true} />
          </div>
          <div className="task-detail__meta">
            <div className="task-detail__intent">{task.intent || 'Untitled Task'}</div>
            {task.description && <div className="task-detail__desc">{task.description}</div>}
            {task.priority && <span className="task-detail__priority">Priority: {task.priority}</span>}
          </div>
        </div>

        {/* Pipeline Visualization */}
        {task.executionTrace && task.executionTrace.length > 0 && (
          <div className="task-detail__pipeline">
            <PipelineVisualization
              phases={task.executionTrace}
              phaseNames={phaseNames}
              onPhaseSelect={setSelectedPhaseIndex}
              selectedPhaseIndex={selectedPhaseIndex}
            />
          </div>
        )}

        {/* Timeline */}
        <div className="task-detail__section">
          <SectionLabel tone="gold" rule={true}>
            Execution Trace
          </SectionLabel>
          <div className="timeline">
            {task.executionTrace && task.executionTrace.length > 0 ? (
              task.executionTrace.map((phase, idx) => (
                <PhaseRow
                  key={idx}
                  phase={phase}
                  index={idx}
                  phaseNames={phaseNames}
                  onSelect={setSelectedPhaseIndex}
                />
              ))
            ) : (
              <div className="timeline__empty">No execution trace available</div>
            )}
          </div>
        </div>

        {/* Phase Detail */}
        {selectedPhase && selectedPhaseIndex !== null && (
          <div className="task-detail__section">
            <SectionLabel tone="muted" rule={false}>
              {phaseNames[selectedPhaseIndex]} Detail
            </SectionLabel>
            <div className="phase-detail">
              {selectedPhase.input && (
                <div className="phase-detail__part">
                  <h4 className="phase-detail__title">Input</h4>
                  <JSONViewer data={selectedPhase.input} />
                </div>
              )}
              {selectedPhase.output && (
                <div className="phase-detail__part">
                  <h4 className="phase-detail__title">Output</h4>
                  <JSONViewer data={selectedPhase.output} />
                </div>
              )}
              {selectedPhase.error && (
                <div className="phase-detail__part phase-detail__part--error">
                  <h4 className="phase-detail__title">Error</h4>
                  <div className="phase-detail__error">{selectedPhase.error}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Agent Assignments */}
        {task.agents && task.agents.length > 0 && (
          <div className="task-detail__section">
            <SectionLabel tone="gold" rule={true}>
              Agents
            </SectionLabel>
            <div className="agents-list">
              {task.agents.map((agent, idx) => (
                <div key={idx} className="agent-row">
                  <span className="agent-row__name">{agent.name || agent.id}</span>
                  {agent.completedAt && (
                    <span className="agent-row__time">{new Date(agent.completedAt).toLocaleTimeString()}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Result */}
        {task.result && (
          <div className="task-detail__section">
            <SectionLabel tone="gold" rule={true}>
              Result
            </SectionLabel>
            <div className="task-result">
              {typeof task.result === 'string' ? (
                <p>{task.result}</p>
              ) : (
                <JSONViewer data={task.result} />
              )}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="task-detail__footer">
          <div className="task-detail__stat">
            <span className="task-detail__stat-label">Created:</span>
            <span className="task-detail__stat-value">{new Date(task.createdAt).toLocaleString()}</span>
          </div>
          {task.completedAt && (
            <div className="task-detail__stat">
              <span className="task-detail__stat-label">Completed:</span>
              <span className="task-detail__stat-value">{new Date(task.completedAt).toLocaleString()}</span>
            </div>
          )}
          {totalDuration !== null && (
            <div className="task-detail__stat">
              <span className="task-detail__stat-label">Duration:</span>
              <span className="task-detail__stat-value">{totalDuration}s</span>
            </div>
          )}
        </div>
      </div>
    </Panel>
  )
}
