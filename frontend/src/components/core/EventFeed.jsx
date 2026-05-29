import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useEventFeedStore } from '../../store/eventFeedStore'
import { useSystemStore } from '../../store/systemStore'
import { useSecurityStore } from '../../store/securityStore'
import { motion, AnimatePresence } from 'framer-motion'
import './EventFeed.css'

const CATEGORY_CONFIG = {
  cognition: { icon: '🧠', label: 'COGNITION', color: 'cyan' },
  task: { icon: '⚡', label: 'TASK', color: 'gold' },
  agent: { icon: '🤖', label: 'AGENT', color: 'blue' },
  memory: { icon: '💾', label: 'MEMORY', color: 'purple' },
  economy: { icon: '💰', label: 'ECONOMY', color: 'success' },
  security: { icon: '🛡', label: 'SECURITY', color: 'warning' },
  brain: { icon: '🧬', label: 'BRAIN', color: 'cyan' },
  infra: { icon: '🖥', label: 'INFRA', color: 'muted' },
  neural_brain: { icon: '🧬', label: 'NEURAL BRAIN', color: 'cyan' },
  artifact: { icon: '📦', label: 'ARTIFACT', color: 'gold' },
  health: { icon: '❤️', label: 'HEALTH', color: 'warning' },
  auth: { icon: '🔐', label: 'AUTH', color: 'warning' },
  other: { icon: '◉', label: 'EVENT', color: 'muted' },
}

const PRIORITY_CONFIG = {
  CRITICAL: { color: 'critical', glow: 'flash', icon: '⚠️', pulse: 300 },
  WARNING: { color: 'warning', glow: 'pulse', icon: '⚠', pulse: 600 },
  NOTICE: { color: 'notice', glow: 'soft', icon: '●', pulse: 0 },
  INFO: { color: 'info', glow: 'none', icon: '○', pulse: 0 },
}

export default function EventFeed({
  autoScroll = true,
  events: externalEvents = null,
  selectedEventId: externalSelectedEventId = null,
  onEventSelect = null,
}) {
  const storeEvents = useEventFeedStore(s => s.events)
  const getGroupedEvents = useEventFeedStore(s => s.getGroupedEvents)
  const storeSelectedEventId = useSystemStore(s => s.selectedEventId)
  const setSelectedEventId = useSystemStore(s => s.setSelectedEventId)

  // Use external events if provided, otherwise use store
  const events = externalEvents || storeEvents
  // Use external selectedEventId if provided, otherwise use store
  const selectedEventId = externalSelectedEventId !== null ? externalSelectedEventId : storeSelectedEventId
  const threatLevel = useSecurityStore(s => s.securityStatus.threat_score)

  const [selectedCategory, setSelectedCategory] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('eventFeedFilter') || 'all'
    }
    return 'all'
  })
  const [severityTab, setSeverityTab] = useState('all')

  const [expandedGroups, setExpandedGroups] = useState(new Set())
  const [isPaused, setIsPaused] = useState(false)
  const scrollContainerRef = useRef(null)
  const lastEventCountRef = useRef(0)
  const scrollTimeoutRef = useRef(null)

  const eventList = events ?? []

  // Persist filter to localStorage
  useEffect(() => {
    localStorage.setItem('eventFeedFilter', selectedCategory)
  }, [selectedCategory])

  // Severity tab filter function
  const matchesSeverityTab = (e, tab) => {
    if (tab === 'all') return true
    const p = (e.priority || '').toLowerCase()
    const t = (e.type || '').toLowerCase()
    if (tab === 'critical') return p === 'critical' || p === 'error'
    if (tab === 'warning')  return p === 'warning' || p === 'warn'
    if (tab === 'info')     return p === 'info' || p === 'notice' || !p
    if (tab === 'success')  return p === 'low' || t.includes('success') || t.includes('complet')
    return true
  }

  // Get grouped events
  const groupedEvents = useMemo(() => {
    const all = getGroupedEvents()
    return all.map(group => ({
      ...group,
      events: group.events
        .filter(e => selectedCategory === 'all' || e.category === selectedCategory)
        .filter(e => matchesSeverityTab(e, severityTab))
    })).filter(group => group.events.length > 0)
  }, [eventList, selectedCategory, severityTab, getGroupedEvents])

  const activeCategories = useMemo(() => {
    return Array.from(new Set(eventList.map(e => e.category).filter(Boolean))).sort()
  }, [eventList])

  // Auto-scroll to newest when events arrive
  useEffect(() => {
    if (!autoScroll || isPaused || !scrollContainerRef.current) return
    if (eventList.length <= lastEventCountRef.current) return

    lastEventCountRef.current = eventList.length

    clearTimeout(scrollTimeoutRef.current)
    scrollTimeoutRef.current = setTimeout(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
      }
    }, 50)

    return () => clearTimeout(scrollTimeoutRef.current)
  }, [eventList.length, autoScroll, isPaused])

  // Auto-expand high-priority groups
  useEffect(() => {
    const newExpanded = new Set(expandedGroups)
    groupedEvents.forEach(group => {
      const maxPriority = Math.max(
        ...group.events.map(e => priorityScore(e.priority))
      )
      if (maxPriority >= 3) newExpanded.add(group.agentId)
    })
    setExpandedGroups(newExpanded)
  }, [groupedEvents])

  const handleMouseEnter = useCallback(() => setIsPaused(true), [])
  const handleMouseLeave = useCallback(() => setIsPaused(false), [])

  const toggleGroup = useCallback((agentId) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(agentId)) next.delete(agentId)
      else next.add(agentId)
      return next
    })
  }, [])

  return (
    <div
      className="event-feed"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role="region"
      aria-label="Event feed"
    >
      {/* Severity tabs (primary) */}
      <div className="event-feed-tabs">
        {['all', 'critical', 'warning', 'info', 'success'].map(tab => (
          <button
            key={tab}
            className={`feed-tab feed-tab--${tab} ${severityTab === tab ? 'feed-tab--active' : ''}`}
            onClick={() => setSeverityTab(tab)}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Category chips (secondary, smaller) */}
      <div className="event-feed-filters">
        <button
          className={`filter-btn ${selectedCategory === 'all' ? 'active' : ''}`}
          onClick={() => setSelectedCategory('all')}
        >
          ALL
        </button>
        {activeCategories.map(cat => {
          const cfg = CATEGORY_CONFIG[cat] || { icon: '◉', label: cat }
          return (
            <button
              key={cat}
              className={`filter-btn ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat)}
              title={cfg.label}
            >
              <span className="filter-icon">{cfg.icon}</span>
            </button>
          )
        })}
      </div>

      {/* Grouped event stream */}
      <div className="event-feed-scroll" ref={scrollContainerRef}>
        <AnimatePresence mode="popLayout">
          {groupedEvents.length > 0 ? (
            groupedEvents.map((group) => (
              <EventGroup
                key={group.agentId}
                group={group}
                isExpanded={expandedGroups.has(group.agentId)}
                onToggle={() => toggleGroup(group.agentId)}
                isSelected={selectedEventId && group.events.some(e => e.id === selectedEventId)}
                onSelectEvent={onEventSelect || setSelectedEventId}
              />
            ))
          ) : (
            <motion.div
              className="event-feed-empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {selectedCategory === 'all'
                ? 'No events yet. System is idle.'
                : `No ${selectedCategory} events.`}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Pause indicator */}
      <AnimatePresence>
        {isPaused && (
          <motion.div
            className="event-feed-paused"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            ⏸ Paused
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function EventGroup({ group, isExpanded, onToggle, isSelected, onSelectEvent }) {
  const maxPriority = useMemo(() => {
    const priorities = group.events.map(e => e.priority)
    return ['CRITICAL', 'WARNING', 'NOTICE', 'INFO'].find(p => priorities.includes(p)) || 'INFO'
  }, [group.events])

  const cfg = PRIORITY_CONFIG[maxPriority]
  const categoryCounts = useMemo(() => {
    const counts = {}
    group.events.forEach(e => {
      counts[e.category] = (counts[e.category] || 0) + 1
    })
    return counts
  }, [group.events])

  const newestEvent = group.events[0]
  const t = new Date(newestEvent?.ts || 0)
  const timeStr = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`

  const pulseAnimation = cfg.pulse > 0 ? {
    animate: { opacity: [1, 0.5, 1] },
    transition: { duration: cfg.pulse / 1000, repeat: Infinity }
  } : {}

  return (
    <motion.div
      className={`event-group event-group--${cfg.color} ${isSelected ? 'context-active' : ''}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      layout
      {...pulseAnimation}
    >
      {/* Group Header - Always visible */}
      <div className="event-group-header" onClick={onToggle} role="button" tabIndex={0}>
        <div className="group-left">
          <span className={`priority-indicator priority-${cfg.color}`}>
            {cfg.icon}
          </span>
          <span className="group-label">
            {group.agentId || 'SYSTEM'}
          </span>
          <span className="group-count">{group.count} event{group.count > 1 ? 's' : ''}</span>
        </div>
        <div className="group-right">
          <span className="group-time">{timeStr}</span>
          <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>
            ▸
          </span>
        </div>
      </div>

      {/* Category breakdown - inline */}
      <div className="group-categories">
        {Object.entries(categoryCounts).map(([cat, count]) => {
          const catCfg = CATEGORY_CONFIG[cat] || { icon: '◉', label: cat }
          return (
            <span key={cat} className="category-tag">
              {catCfg.icon} {count}
            </span>
          )
        })}
      </div>

      {/* Expanded content - events */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="event-group-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {group.events.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                onSelect={() => onSelectEvent(event.id)}
                isSelected={isSelected}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function EventCard({ event, onSelect, isSelected }) {
  const {
    category = 'other',
    priority = 'INFO',
    notes = '',
    ts,
    id,
  } = event

  const catCfg = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.other
  const priCfg = PRIORITY_CONFIG[priority]

  // Format timestamp HH:MM:SS
  const t = new Date(ts || 0)
  const timeStr = `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}:${String(t.getSeconds()).padStart(2, '0')}`

  return (
    <motion.div
      className={`event-card event-card--${catCfg.color} ${isSelected ? 'event-card--selected' : ''}`}
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      transition={{ duration: 0.15 }}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      layout
    >
      {/* Header */}
      <div className="event-header">
        <span className={`priority-dot priority-${priCfg.color}`} aria-hidden="true">
          {priCfg.icon}
        </span>
        <span className="event-label">{catCfg.label}</span>
        <span className="event-timestamp">{timeStr}</span>
      </div>

      {/* Message */}
      {notes && (
        <div className="event-message">
          {notes}
        </div>
      )}
    </motion.div>
  )
}

function priorityScore(priority) {
  const scores = { CRITICAL: 4, WARNING: 3, NOTICE: 2, INFO: 1 }
  return scores[priority] || 0
}
