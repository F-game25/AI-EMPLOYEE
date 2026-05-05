import React from 'react'
import './PipelineVisualizer.css'

const PHASE_COLORS = {
  retrieve_relevant_nodes: '#FFD97A',
  build_context: '#C084FC',
  classify_decision: '#20D6C7',
  call_llm: '#60A5FA',
  validate_tasks: '#F59E0B',
  execute_tasks: '#22C55E',
  format_response: '#3CE7FF',
  update_graph: '#A855F7',
  monitor_and_improve: '#F97316',
  validate_pipeline_integrity: '#EC4899',
}

export default function PipelineVisualizer({ pipeline = null }) {
  if (!pipeline) {
    return (
      <div className="pipeline-visualizer idle">
        <div className="pipeline-placeholder">
          No pipeline data available
        </div>
      </div>
    )
  }

  const phases = Array.isArray(pipeline.phases) ? pipeline.phases : []
  const currentPhase = pipeline.currentPhase || 0
  const overallProgress = phases.length > 0 ? (currentPhase / phases.length) * 100 : 0

  return (
    <div className="pipeline-visualizer">
      <div className="pipeline-header">
        <h3 className="pipeline-title">Execution Pipeline</h3>
        <div className="pipeline-progress">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${overallProgress}%` }} />
          </div>
          <span className="progress-text">{currentPhase}/{phases.length}</span>
        </div>
      </div>

      <div className="phases-container">
        {phases.length === 0 ? (
          <div className="no-phases">No phases loaded</div>
        ) : (
          phases.map((phase, idx) => {
            const isActive = idx === currentPhase
            const isCompleted = idx < currentPhase
            const color = PHASE_COLORS[phase.name] || '#888'

            return (
              <div key={idx} className="phase-group">
                <div
                  className={`phase-node ${isActive ? 'active' : isCompleted ? 'completed' : ''}`}
                  style={{
                    borderColor: color,
                    backgroundColor: isActive ? `${color}15` : isCompleted ? `${color}08` : 'transparent',
                  }}
                >
                  <div className="phase-number">{idx + 1}</div>
                  <div className="phase-label">{phase.name?.replace(/_/g, ' ')}</div>
                  {isActive && <div className="phase-spinner" style={{ borderTopColor: color }} />}
                  {isCompleted && <div className="phase-checkmark">✓</div>}
                </div>

                {idx < phases.length - 1 && (
                  <div
                    className={`phase-arrow ${isCompleted ? 'completed' : ''}`}
                    style={{ color: isCompleted ? color : '#444' }}
                  >
                    →
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {pipeline.errors && pipeline.errors.length > 0 && (
        <div className="pipeline-errors">
          <h4 className="errors-title">Issues</h4>
          {pipeline.errors.map((err, i) => (
            <div key={i} className="error-item">
              <span className="error-icon">⚠</span>
              <span className="error-msg">{err}</span>
            </div>
          ))}
        </div>
      )}

      {pipeline.metrics && (
        <div className="pipeline-metrics">
          <div className="metric">
            <span className="metric-label">Duration</span>
            <span className="metric-val">{pipeline.metrics.duration || '—'}ms</span>
          </div>
          <div className="metric">
            <span className="metric-label">Tokens</span>
            <span className="metric-val">{pipeline.metrics.tokensUsed || '—'}</span>
          </div>
        </div>
      )}
    </div>
  )
}
