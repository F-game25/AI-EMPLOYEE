import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import './RingPanel.css'

export default function RingPanel({
  id = null,
  title,
  icon = null,
  metrics = [],
  color = 'cyan',
  glowColor = null,
  healthStatus = 'healthy',
  context = null,
  onMetricClick = null,
  gaugeData = null,
  sparklineData = null,
  animated = true,
  additionalMetrics = [],
  recentEvents = [],
  activityLog = [],     // hybrid layout: live log items [{time, text}]
  isExpanded = false,
  onToggleExpand = null,
  isContextActive = false,
  focusMode = 'OPERATIONS',
}) {
  const [internalExpanded, setInternalExpanded] = useState(isExpanded)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const panelRef = useRef(null)

  // Use external isExpanded prop if provided, otherwise use internal state
  const expanded = onToggleExpand ? isExpanded : internalExpanded
  const setExpanded = onToggleExpand ? onToggleExpand : setInternalExpanded

  // Convert metrics object to array if needed
  const metricsArray = useMemo(() => {
    if (Array.isArray(metrics)) return metrics
    if (typeof metrics === 'object' && metrics !== null) {
      return Object.entries(metrics).map(([label, value]) => ({
        label,
        value,
        color: color,
      }))
    }
    return []
  }, [metrics, color])

  // Take first 4 metrics for default view
  const primaryMetrics = metricsArray.slice(0, 4)
  const expandedMetrics = additionalMetrics && additionalMetrics.length > 0
    ? additionalMetrics
    : metricsArray.slice(4)

  // Determine glow color (use provided color or fallback to primary color)
  const borderColor = glowColor || color

  // Color mappings
  const glowColorMap = {
    cyan: 'rgba(0, 217, 255, 0.3)',
    teal: 'rgba(32, 214, 199, 0.3)',
    gold: 'rgba(229, 199, 107, 0.3)',
    purple: 'rgba(168, 85, 247, 0.3)',
    green: 'rgba(34, 197, 94, 0.3)',
    orange: 'rgba(245, 158, 11, 0.3)',
    red: 'rgba(239, 68, 68, 0.3)',
    blue: 'rgba(59, 130, 246, 0.3)',
  }

  // Icon rendering
  const iconMap = {
    brain: '🧠',
    workflow: '⚡',
    trending: '📈',
    server: '🖥️',
    chain: '⛓️',
    network: '🌐',
    rocket: '🚀',
    shield: '🛡️',
  }

  const displayIcon = typeof icon === 'string' ? iconMap[icon] || icon : icon

  // Health status colors
  const healthColorMap = {
    healthy: '#22C55E',
    busy: '#F59E0B',
    warning: '#F59E0B',
    critical: '#EF4444',
    offline: '#8A8A96',
  }

  // Handle context locking via prop
  useEffect(() => {
    if (isContextActive && panelRef.current) {
      panelRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [isContextActive])

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && showDetailModal) {
        setShowDetailModal(false)
      }
    }

    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [showDetailModal])

  const handlePanelClick = () => {
    if (onToggleExpand) {
      onToggleExpand()
    } else {
      setInternalExpanded(!internalExpanded)
    }
  }

  const handleMetricClick = (metric) => {
    if (onMetricClick) {
      onMetricClick(metric)
    } else {
      setShowDetailModal(true)
    }
  }

  return (
    <>
      <div
        ref={panelRef}
        className={`ring-panel ring-panel--${color}
          ${animated ? 'ring-panel--animated' : ''}
          ${expanded ? 'ring-panel--expanded' : 'ring-panel--collapsed'}
          ${isContextActive ? 'ring-panel--context-active' : ''}
          ring-panel--health-${healthStatus}`}
        style={{
          '--glow-border-color': glowColorMap[borderColor] || glowColorMap.cyan,
          '--health-color': healthColorMap[healthStatus],
          width: 280,
          height: expanded ? undefined : 160,
        }}
        onClick={handlePanelClick}
        onKeyDown={(e) => e.key === 'Enter' && handlePanelClick()}
        role="button"
        tabIndex={0}
        aria-label={`${title} metrics panel`}
        aria-expanded={expanded}
      >
        {/* Grid overlay background */}
        <div className="ring-panel-grid-overlay" />

        {/* Health status indicator dot */}
        <div className={`ring-panel-health-dot ring-panel-health-dot--${healthStatus}`} />

        {/* Header with icon and title */}
        <div className="ring-panel-header">
          {displayIcon && <span className="ring-panel-icon">{displayIcon}</span>}
          <h3 className="ring-panel-title">{title.toUpperCase()}</h3>
        </div>

        {/* Primary Metrics Grid (always visible) */}
        <div className="ring-panel-metrics ring-panel-metrics--primary">
          {primaryMetrics.length > 0 ? (
            primaryMetrics.map((metric, idx) => (
              <MetricItem
                key={idx}
                metric={metric}
                onClick={() => handleMetricClick(metric)}
              />
            ))
          ) : (
            <div className="ring-panel-empty">No metrics</div>
          )}
        </div>

        {/* Sparkline (optional, always visible in collapsed state) */}
        {sparklineData && sparklineData.length > 0 && (
          <div className="ring-panel-sparkline ring-panel-sparkline--compact">
            <SparklineChart data={sparklineData} color={borderColor} />
          </div>
        )}

        {/* Compact gauge is visible even when collapsed so load state is scannable. */}
        {gaugeData && !expanded && (
          <div className="ring-panel-gauge ring-panel-gauge--compact">
            <GaugeVisualization value={gaugeData.value} max={gaugeData.max} />
          </div>
        )}

        {/* Expanded content (appears on hover/expand) */}
        {expanded && (
          <>
            {/* Additional Metrics */}
            {expandedMetrics.length > 0 && (
              <div className="ring-panel-metrics ring-panel-metrics--expanded">
                {expandedMetrics.map((metric, idx) => (
                  <MetricItem
                    key={idx}
                    metric={metric}
                    onClick={() => handleMetricClick(metric)}
                  />
                ))}
              </div>
            )}

            {/* Gauge Visualization */}
            {gaugeData && (
              <div className="ring-panel-gauge">
                <GaugeVisualization value={gaugeData.value} max={gaugeData.max} />
              </div>
            )}

            {/* Recent Events List */}
            {recentEvents && recentEvents.length > 0 && (
              <div className="ring-panel-events">
                <div className="ring-panel-events-header">Recent Events</div>
                <div className="ring-panel-events-list">
                  {recentEvents.slice(0, 3).map((event, idx) => (
                    <div key={idx} className="ring-panel-event-item">
                      <span className="event-time">{event.time || '—'}</span>
                      <span className="event-text">{event.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Hybrid: live activity log (always visible) */}
        {activityLog && activityLog.length > 0 && (
          <>
            <div className="ring-panel-divider" />
            <div className="ring-panel-log-header">LIVE ACTIVITY</div>
            <div className="ring-panel-log">
              {activityLog.slice(0, 5).map((item, i) => (
                <div key={i} className="ring-panel-log-item">
                  {item.time && <span className="ring-panel-log-time">{item.time}</span>}
                  <span className="ring-panel-log-text">{item.text}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Expansion hint (fallback when no activityLog) */}
        {!activityLog?.length && !expanded && (expandedMetrics.length > 0 || gaugeData || (recentEvents && recentEvents.length > 0)) && (
          <div className="ring-panel-expand-hint">Click to expand</div>
        )}
      </div>

      {/* Detail Modal */}
      {showDetailModal && (
        <RingPanelDetailModal
          title={title}
          color={color}
          metrics={metricsArray}
          gaugeData={gaugeData}
          sparklineData={sparklineData}
          healthStatus={healthStatus}
          context={context}
          onClose={() => setShowDetailModal(false)}
        />
      )}
    </>
  )
}

function MetricItem({ metric, onClick }) {
  const { label, value, trend, color = 'cyan', unit = '' } = metric
  const [displayValue, setDisplayValue] = useState(value)
  const [prevValue, setPrevValue] = useState(value)

  useEffect(() => {
    if (value !== prevValue) {
      setPrevValue(value)
      setDisplayValue(value)
    }
  }, [value, prevValue])

  // Determine trend indicator
  let trendIcon = ''
  let trendClass = 'neutral'
  if (trend !== undefined && trend !== null) {
    const trendNum = typeof trend === 'string' ? parseFloat(trend) : trend
    if (trendNum > 0) {
      trendIcon = '↑'
      trendClass = 'positive'
    } else if (trendNum < 0) {
      trendIcon = '↓'
      trendClass = 'negative'
    }
  }

  // Color mapping for values
  const colorMap = {
    cyan: '#00D9FF',
    teal: '#20D6C7',
    gold: '#E5C76B',
    green: '#22C55E',
    orange: '#F59E0B',
    red: '#EF4444',
    blue: '#3B82F6',
    purple: '#A855F7',
  }

  const textColor = colorMap[color] || colorMap.cyan

  const formatValue = () => {
    if (typeof displayValue === 'number') {
      if (displayValue >= 1000000) return `${(displayValue / 1000000).toFixed(1)}M`
      if (displayValue >= 1000) return `${(displayValue / 1000).toFixed(1)}K`
      if (Number.isInteger(displayValue)) return String(displayValue)
      return displayValue.toFixed(displayValue < 100 ? 1 : 0)
    }
    return String(displayValue)
  }

  return (
    <div
      className="metric-item"
      onClick={(e) => {
        e.stopPropagation()
        onClick?.()
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
    >
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: textColor }}>
        {formatValue()}
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      {(trend !== undefined && trend !== null) && (
        <div className={`metric-trend metric-trend--${trendClass}`}>
          {trendIcon} {Math.abs(typeof trend === 'string' ? parseFloat(trend) : trend).toFixed(1)}%
        </div>
      )}
    </div>
  )
}

function GaugeVisualization({ value = 0, max = 100 }) {
  const percentage = Math.min((value / max) * 100, 100)

  return (
    <div className="gauge-container">
      <svg viewBox="0 0 100 50" className="gauge-arc">
        {/* Background arc */}
        <path
          d="M 10 50 A 40 40 0 0 1 90 50"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="4"
          fill="none"
        />
        {/* Value arc */}
        <path
          d="M 10 50 A 40 40 0 0 1 90 50"
          stroke="#00D9FF"
          strokeWidth="4"
          fill="none"
          strokeDasharray={`${(percentage / 100) * 125} 125`}
          style={{ transition: 'stroke-dasharray 0.3s ease' }}
        />
      </svg>
      <div className="gauge-center">
        <div className="gauge-value">{value}</div>
        <div className="gauge-label">of {max}</div>
      </div>
    </div>
  )
}

function SparklineChart({ data = [], color = 'cyan' }) {
  if (data.length === 0) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const width = 240
  const height = 30

  const colorMap = {
    cyan: '#00D9FF',
    gold: '#E5C76B',
    teal: '#20D6C7',
    purple: '#A855F7',
  }

  const strokeColor = colorMap[color] || colorMap.cyan

  // Create path for line chart
  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * width
      const y = height - ((val - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="sparkline">
      <polyline points={points} fill="none" stroke={strokeColor} strokeWidth="2" />
    </svg>
  )
}

function RingPanelDetailModal({
  title,
  color,
  metrics,
  gaugeData,
  sparklineData,
  healthStatus,
  context,
  onClose,
}) {
  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  const colorMap = {
    cyan: '#00D9FF',
    teal: '#20D6C7',
    gold: '#E5C76B',
    green: '#22C55E',
    orange: '#F59E0B',
    red: '#EF4444',
    blue: '#3B82F6',
    purple: '#A855F7',
  }

  const healthStatusMap = {
    healthy: { label: 'Healthy', color: '#22C55E' },
    busy: { label: 'Busy', color: '#F59E0B' },
    warning: { label: 'Warning', color: '#F59E0B' },
    critical: { label: 'Critical', color: '#EF4444' },
    offline: { label: 'Offline', color: '#8A8A96' },
  }

  const accentColor = colorMap[color] || colorMap.cyan
  const status = healthStatusMap[healthStatus]

  return (
    <div
      className="ring-panel-detail-modal-backdrop"
      onClick={handleBackdropClick}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="presentation"
    >
      <div className="ring-panel-detail-modal" style={{ '--accent-color': accentColor }}>
        {/* Header */}
        <div className="ring-panel-detail-header">
          <div className="ring-panel-detail-title-section">
            <h2 className="ring-panel-detail-title">{title.toUpperCase()}</h2>
            <div
              className={`ring-panel-detail-status ring-panel-detail-status--${healthStatus}`}
              style={{ color: status.color }}
            >
              {status.label}
            </div>
          </div>
          <button
            className="ring-panel-detail-close"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="ring-panel-detail-content">
          {/* Metrics Grid */}
          {metrics.length > 0 && (
            <div className="ring-panel-detail-section">
              <h3 className="ring-panel-detail-section-title">Metrics</h3>
              <div className="ring-panel-detail-metrics-grid">
                {metrics.map((metric, idx) => (
                  <div key={idx} className="ring-panel-detail-metric">
                    <div className="ring-panel-detail-metric-label">{metric.label}</div>
                    <div className="ring-panel-detail-metric-value" style={{ color: accentColor }}>
                      {typeof metric.value === 'number'
                        ? metric.value.toLocaleString()
                        : metric.value}
                    </div>
                    {metric.unit && (
                      <div className="ring-panel-detail-metric-unit">{metric.unit}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sparkline */}
          {sparklineData && sparklineData.length > 0 && (
            <div className="ring-panel-detail-section">
              <h3 className="ring-panel-detail-section-title">Trend</h3>
              <div className="ring-panel-detail-sparkline">
                <SparklineChart data={sparklineData} color={color} />
              </div>
            </div>
          )}

          {/* Gauge */}
          {gaugeData && (
            <div className="ring-panel-detail-section">
              <h3 className="ring-panel-detail-section-title">Load</h3>
              <div className="ring-panel-detail-gauge">
                <GaugeVisualization value={gaugeData.value} max={gaugeData.max} />
              </div>
            </div>
          )}

          {/* Context Info */}
          {context && (
            <div className="ring-panel-detail-section">
              <h3 className="ring-panel-detail-section-title">Context</h3>
              <div className="ring-panel-detail-context">
                {Object.entries(context).map(([key, val]) => (
                  <div key={key} className="ring-panel-detail-context-item">
                    <span className="context-label">{key}:</span>
                    <span className="context-value">{String(val)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="ring-panel-detail-footer">
          <button
            className="ring-panel-detail-button ring-panel-detail-button--primary"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
