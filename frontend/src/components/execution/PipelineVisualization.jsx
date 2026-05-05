import React, { useState } from 'react'
import './PipelineVisualization.css'

export default function PipelineVisualization({
  phases = [],
  phaseNames = [],
  onPhaseSelect,
  selectedPhaseIndex,
}) {
  const [hoveredIndex, setHoveredIndex] = useState(null)

  // Ensure we have 10 phases (padded with pending if needed)
  const allPhases = Array(10)
    .fill(null)
    .map((_, i) => phases[i] || { status: 'pending' })

  const getPhaseStatus = (phase) => phase?.status || 'pending'
  const getPhaseShortName = (index) => {
    const name = phaseNames[index] || `Phase ${index + 1}`
    return name.length > 20 ? name.substring(0, 17) + '…' : name
  }

  const duration = (phase) => {
    if (!phase?.startTime || !phase?.endTime) return null
    return Math.round((new Date(phase.endTime) - new Date(phase.startTime)) / 1000)
  }

  return (
    <div className="pipeline-viz">
      <svg
        className="pipeline-viz__svg"
        viewBox="0 0 1000 120"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Connecting arrows */}
        {allPhases.map((_, i) => {
          if (i === allPhases.length - 1) return null
          const x1 = 80 + i * 100
          const x2 = 80 + (i + 1) * 100
          return (
            <line
              key={`arrow-${i}`}
              x1={x1}
              y1="60"
              x2={x2}
              y2="60"
              className={`pipeline-viz__arrow pipeline-viz__arrow--${getPhaseStatus(allPhases[i])}`}
              strokeDasharray={getPhaseStatus(allPhases[i]) === 'pending' ? '5,5' : '0'}
            />
          )
        })}

        {/* Phase boxes */}
        {allPhases.map((phase, i) => {
          const x = 80 + i * 100 - 30
          const y = 30
          const isSelected = i === selectedPhaseIndex
          const isHovered = i === hoveredIndex
          const status = getPhaseStatus(phase)

          return (
            <g
              key={`phase-${i}`}
              className={`pipeline-viz__phase ${
                isSelected ? 'pipeline-viz__phase--selected' : ''
              } ${isHovered ? 'pipeline-viz__phase--hovered' : ''}`}
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
              onClick={() => onPhaseSelect && onPhaseSelect(i)}
              style={{ cursor: 'pointer' }}
            >
              {/* Box background */}
              <rect
                x={x}
                y={y}
                width="60"
                height="60"
                rx="4"
                className={`pipeline-viz__box pipeline-viz__box--${status}`}
              />

              {/* Loading animation for running phase */}
              {status === 'running' && (
                <circle
                  cx={x + 30}
                  cy={y + 30}
                  r="20"
                  className="pipeline-viz__spinner"
                />
              )}

              {/* Phase number */}
              <text
                x={x + 30}
                y={y + 25}
                className="pipeline-viz__num"
                textAnchor="middle"
              >
                {i + 1}
              </text>

              {/* Status icon */}
              <text
                x={x + 30}
                y={y + 45}
                className="pipeline-viz__status-icon"
                textAnchor="middle"
              >
                {status === 'done' && '✓'}
                {status === 'failed' && '✗'}
                {status === 'running' && '…'}
                {status === 'pending' && '○'}
              </text>

              {/* Tooltip on hover */}
              {isHovered && (
                <g>
                  <rect
                    x={Math.max(x - 40, 0)}
                    y={y - 35}
                    width="140"
                    height="30"
                    rx="3"
                    className="pipeline-viz__tooltip-bg"
                  />
                  <text
                    x={x + 30}
                    y={y - 20}
                    className="pipeline-viz__tooltip-text"
                    textAnchor="middle"
                  >
                    {getPhaseShortName(i)}
                  </text>
                  {duration(phase) && (
                    <text
                      x={x + 30}
                      y={y - 8}
                      className="pipeline-viz__tooltip-duration"
                      textAnchor="middle"
                    >
                      {duration(phase)}s
                    </text>
                  )}
                </g>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="pipeline-viz__legend">
        <div className="legend-item">
          <span className="legend-dot legend-dot--pending" />
          <span className="legend-label">Pending</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot legend-dot--running" />
          <span className="legend-label">Running</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot legend-dot--done" />
          <span className="legend-label">Done</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot legend-dot--failed" />
          <span className="legend-label">Failed</span>
        </div>
      </div>
    </div>
  )
}
