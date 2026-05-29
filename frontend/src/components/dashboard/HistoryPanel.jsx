import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useEventFeedStore } from '../../store/eventFeedStore'
import { Panel, HexButton, StatusPill, SectionLabel, KPITile } from '../nexus-ui'
import './HistoryPanel.css'

const STATUS_PILL_TONES = {
  done: 'success',
  failed: 'alert',
  partial: 'warn',
  running: 'cool',
  queued: 'idle',
}

export default function HistoryPanel() {
  const events = useEventFeedStore(s => s.events)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [activeTab, setActiveTab] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')

  const stats = useMemo(() => {
    const total = events.length
    const done = events.filter(e => e.kind === 'complete' || e.status === 'done').length
    const failed = events.filter(e => e.kind === 'error' || e.status === 'failed').length
    return {
      total_tasks: total,
      success_rate: total > 0 ? (done / total) * 100 : 0,
      failed_count: failed,
    }
  }, [events])

  const handleEventSelect = useCallback((event) => {
    setSelectedEvent(selectedEvent?.task_id === event.task_id ? null : event)
  }, [selectedEvent])

  const handleCopyToClipboard = useCallback(() => {
    if (selectedEvent) {
      const json = JSON.stringify(selectedEvent, null, 2)
      navigator.clipboard.writeText(json)
    }
  }, [selectedEvent])

  const formatTime = (ms) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const formatDate = (iso) => {
    const date = new Date(iso)
    const today = new Date()
    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const getEventStatus = useCallback((event) => event.status || 'queued', [])

  const filteredEvents = useMemo(() => {
    const term = searchTerm.toLowerCase()
    return events
      .filter((e) => activeTab === 'all' || getEventStatus(e) === activeTab)
      .filter((e) => {
        if (!searchTerm) return true
        return (
          (e.input || '').toLowerCase().includes(term) ||
          (e.agent_sequence?.some((a) => a.toLowerCase().includes(term))) ||
          (e.task_id || '').toLowerCase().includes(term)
        )
      })
      .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))
  }, [events, activeTab, searchTerm, getEventStatus])

  return (
    <div className="hp-container">
      {/* Main panel */}
      <Panel
        title="Execution History"
        corners
        flush
        className="hp-panel"
        bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
      >
        {/* Header section */}
        <div className="hp-header">
          {/* Stats row */}
          {stats && (
            <div className="hp-stats">
              <KPITile label="Total" value={stats.total_tasks} size="sm" />
              <KPITile
                label="Success"
                value={`${Math.round(stats.success_rate)}%`}
                iconTone="success"
                size="sm"
              />
              <KPITile
                label="Failed"
                value={stats.failed_count || 0}
                iconTone="alert"
                size="sm"
              />
            </div>
          )}

          {/* Tabs */}
          <div className="hp-tabs">
            {['all', 'done', 'failed', 'running'].map((tab) => (
              <HexButton
                key={tab}
                variant={activeTab === tab ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setActiveTab(tab)}
                className={`hp-tab-btn ${activeTab === tab ? 'hp-tab-btn--active' : ''}`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </HexButton>
            ))}
          </div>

          {/* Search */}
          <div className="hp-search-box">
            <input
              type="text"
              placeholder="Filter by agent name or description..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="hp-search-input"
            />
          </div>
        </div>

        {/* Content area */}
        <div className="hp-content">
          {/* Event list */}
          <div className="hp-list">
            {filteredEvents.length === 0 ? (
              <div className="hp-empty">No events yet</div>
            ) : (
              <AnimatePresence initial={false}>
                {filteredEvents.map((event, idx) => (
                  <motion.div
                    key={event.task_id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ delay: idx * 0.02 }}
                    className={`hp-event-row ${selectedEvent?.task_id === event.task_id ? 'hp-event-row--selected' : ''}`}
                    onClick={() => handleEventSelect(event)}
                  >
                    <div className="hp-event-main">
                      <div className="hp-event-header">
                        <StatusPill
                          label={getEventStatus(event).toUpperCase()}
                          tone={STATUS_PILL_TONES[getEventStatus(event)] || 'cool'}
                          size="sm"
                          dot={false}
                        />
                        <span className="hp-event-desc">
                          {(event.input || event.description || '').substring(0, 40)}
                          {((event.input || event.description || '').length > 40 ? '...' : '')}
                        </span>
                        <span className="hp-event-time">{formatDate(event.timestamp)}</span>
                      </div>
                      <div className="hp-event-meta">
                        {event.agent_sequence && event.agent_sequence.length > 0 && (
                          <span className="hp-event-agent">
                            {event.agent_sequence[0]}
                          </span>
                        )}
                        <span className="hp-event-duration">{formatTime(event.duration_ms || 0)}</span>
                        {event.cost_estimate_usd > 0 && (
                          <span className="hp-event-cost">${event.cost_estimate_usd.toFixed(2)}</span>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>

          {/* Detail panel (slide-in from right) */}
          <AnimatePresence>
            {selectedEvent && (
              <motion.div
                className="hp-detail"
                initial={{ x: '100%', opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: '100%', opacity: 0 }}
                transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              >
                <div className="hp-detail-header">
                  <SectionLabel tone="gold">Event Details</SectionLabel>
                  <HexButton
                    variant="outline"
                    size="sm"
                    onClick={handleCopyToClipboard}
                  >
                    Copy JSON
                  </HexButton>
                </div>

                <div className="hp-detail-content">
                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Status</span>
                    <StatusPill
                      label={getEventStatus(selectedEvent).toUpperCase()}
                      tone={STATUS_PILL_TONES[getEventStatus(selectedEvent)] || 'cool'}
                      dot={false}
                    />
                  </div>

                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Task ID</span>
                    <code className="hp-detail-code">{selectedEvent.task_id}</code>
                  </div>

                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Input</span>
                    <span className="hp-detail-text">{selectedEvent.input || selectedEvent.description}</span>
                  </div>

                  {selectedEvent.agent_sequence && selectedEvent.agent_sequence.length > 0 && (
                    <div className="hp-detail-row">
                      <span className="hp-detail-label">Agents</span>
                      <span className="hp-detail-text">{selectedEvent.agent_sequence.join(', ')}</span>
                    </div>
                  )}

                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Duration</span>
                    <span className="hp-detail-text">{formatTime(selectedEvent.duration_ms || 0)}</span>
                  </div>

                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Cost</span>
                    <span className="hp-detail-text">${(selectedEvent.cost_estimate_usd || 0).toFixed(2)}</span>
                  </div>

                  {selectedEvent.confidence != null && (
                    <div className="hp-detail-row">
                      <span className="hp-detail-label">Confidence</span>
                      <span className="hp-detail-text">{Math.round(selectedEvent.confidence * 100)}%</span>
                    </div>
                  )}

                  {selectedEvent.error && (
                    <div className="hp-detail-row hp-detail-row--error">
                      <span className="hp-detail-label">Error</span>
                      <span className="hp-detail-error">{selectedEvent.error}</span>
                    </div>
                  )}

                  <div className="hp-detail-row">
                    <span className="hp-detail-label">Timestamp</span>
                    <span className="hp-detail-text hp-detail-mono">
                      {new Date(selectedEvent.timestamp).toISOString()}
                    </span>
                  </div>

                  {/* Full JSON dump */}
                  <div className="hp-detail-json">
                    <SectionLabel tone="muted" size="sm">Raw JSON</SectionLabel>
                    <pre className="hp-detail-pre">
                      {JSON.stringify(selectedEvent, null, 2)}
                    </pre>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </Panel>
    </div>
  )
}
