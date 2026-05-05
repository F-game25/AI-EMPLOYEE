import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import './PhaseDetail.css'

export default function PhaseDetail({ phase, onClose }) {
  const panelRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        onClose()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose])

  const formatTime = (isoString) => {
    if (!isoString) return '—'
    const date = new Date(isoString)
    return date.toLocaleTimeString()
  }

  const formatDuration = (ms) => {
    if (ms < 1000) return `${ms.toFixed(0)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  return (
    <>
      <motion.div
        className="phase-detail-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.div
        ref={panelRef}
        className="phase-detail-panel"
        initial={{ x: 400, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 400, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      >
        <div className="detail-header">
          <div className="detail-title">
            <h3>{phase.name}</h3>
            <span className={`status-badge ${phase.status}`}>{phase.status}</span>
          </div>
          <button className="close-btn" onClick={onClose}>
            <svg viewBox="0 0 24 24" width="20" height="20">
              <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" strokeWidth="2" />
              <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </div>

        <div className="detail-description">
          <p>{phase.description}</p>
        </div>

        <div className="detail-section">
          <h4>Timing</h4>
          <div className="timing-grid">
            <div className="timing-item">
              <label>Started At</label>
              <code>{formatTime(phase.startedAt)}</code>
            </div>
            <div className="timing-item">
              <label>Duration</label>
              <code>{formatDuration(phase.duration_ms)}</code>
            </div>
            <div className="timing-item">
              <label>Completed At</label>
              <code>{formatTime(phase.completedAt)}</code>
            </div>
          </div>
        </div>

        {phase.logs && phase.logs.length > 0 && (
          <div className="detail-section">
            <h4>Logs ({phase.logs.length})</h4>
            <div className="logs-container">
              {phase.logs.slice(0, 5).map((log, idx) => (
                <div key={idx} className="log-entry">
                  <span className="log-timestamp">{formatTime(log.timestamp)}</span>
                  <span className={`log-level ${log.level || 'info'}`}>
                    {log.level || 'INFO'}
                  </span>
                  <span className="log-message">{log.message}</span>
                </div>
              ))}
              {phase.logs.length > 5 && (
                <div className="log-more">+{phase.logs.length - 5} more logs</div>
              )}
            </div>
          </div>
        )}

        {phase.metrics && Object.keys(phase.metrics).length > 0 && (
          <div className="detail-section">
            <h4>Metrics</h4>
            <div className="metrics-grid">
              {Object.entries(phase.metrics).map(([key, value]) => (
                <div key={key} className="metric-item">
                  <label>{key}</label>
                  <code>
                    {typeof value === 'number'
                      ? value.toFixed(value < 100 ? 2 : 0)
                      : String(value)}
                  </code>
                </div>
              ))}
            </div>
          </div>
        )}

        {phase.error && (
          <div className="detail-section error-section">
            <h4>Error</h4>
            <div className="error-message">{phase.error}</div>
          </div>
        )}

        {phase.status === 'done' && (
          <div className="detail-section success-section">
            <div className="success-badge">Completed Successfully</div>
          </div>
        )}
      </motion.div>
    </>
  )
}
