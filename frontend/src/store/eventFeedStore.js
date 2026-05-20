import { create } from 'zustand'

const MAX_EVENTS = 200

/**
 * Universal event feed — catch-all for memory, neural brain, and unknown events.
 * Categorized by: memory_write, memory_read, neural_brain, artifact, thread, health, auth, other
 *
 * Enhanced with:
 * - Priority levels (INFO, NOTICE, WARNING, CRITICAL)
 * - Semantic grouping (agent cluster, task group, etc.)
 * - Deduplication counts
 * - Context metadata for UI linking
 */
export const useEventFeedStore = create((set, get) => ({
  // Event stream (max 200 entries)
  events: [],
  addEvent: (event) => set((state) => ({
    events: [
      {
        id: event.id || `evt-${Date.now()}-${Math.random()}`,
        kind: event.kind || event.event_type || 'other',
        category: categorizeEvent(event),
        priority: detectPriority(event),
        notes: event.notes || '',
        data: event,
        ts: event.ts || Date.now(),
        agentId: event.agent_id || event.agentId || extractAgentId(event.notes),
        context: event.context || {},
      },
      ...state.events,
    ].slice(0, MAX_EVENTS),
  })),

  // Batch snapshot load (from event_stream)
  setEventSnapshot: (events) => set({
    events: Array.isArray(events)
      ? events.map(e => ({
          id: e.id || `evt-${Date.now()}-${Math.random()}`,
          kind: e.kind || e.event_type || 'other',
          category: categorizeEvent(e),
          priority: detectPriority(e),
          notes: e.notes || '',
          data: e,
          ts: e.ts || Date.now(),
          agentId: e.agent_id || e.agentId || extractAgentId(e.notes),
          context: e.context || {},
        })).slice(0, MAX_EVENTS)
      : [],
  }),

  // Filter events by category
  getEventsByCategory: (category) => get().events.filter(e => e.category === category),

  // Get recent events (last N)
  getRecentEvents: (n = 20) => get().events.slice(0, n),

  // Group events by agent with deduplication
  getGroupedEvents: () => {
    const events = get().events
    const groups = new Map()

    for (const evt of events) {
      const key = evt.agentId || 'system'
      if (!groups.has(key)) {
        groups.set(key, { agentId: key, events: [], count: 0 })
      }
      groups.get(key).events.push(evt)
      groups.get(key).count++
    }

    return Array.from(groups.values())
      .sort((a, b) => {
        const maxPriorityA = Math.max(...a.events.map(e => priorityScore(e.priority)))
        const maxPriorityB = Math.max(...b.events.map(e => priorityScore(e.priority)))
        if (maxPriorityB !== maxPriorityA) return maxPriorityB - maxPriorityA
        return (b.events[0]?.ts || 0) - (a.events[0]?.ts || 0)
      })
  },
}))

function categorizeEvent(event) {
  const kind = (event.kind || event.event_type || '').toLowerCase()
  const notes = (event.notes || '').toLowerCase()
  const combined = `${kind} ${notes}`

  // Cognitive/Neural categories
  if (combined.includes('memory') && combined.includes('write')) return 'memory'
  if (combined.includes('memory') && combined.includes('read')) return 'memory'
  if (combined.includes('neural') || combined.includes('reasoning') || combined.includes('model_call')) return 'cognition'
  if (combined.includes('brain') || combined.includes('graph') || combined.includes('insight')) return 'brain'

  // Agent & Task execution
  if (combined.includes('agent') || combined.includes('action')) return 'agent'
  if (combined.includes('task') || combined.includes('execution') || combined.includes('workflow')) return 'task'

  // Data & Economy
  if (combined.includes('artifact') || combined.includes('thread')) return 'artifact'
  if (combined.includes('economy') || combined.includes('revenue') || combined.includes('money') || combined.includes('objective')) return 'economy'

  // Infrastructure & Health
  if (combined.includes('health') || combined.includes('degraded') || combined.includes('recovered') || combined.includes('doctor')) return 'health'
  if (combined.includes('infra') || combined.includes('nn_status')) return 'infra'

  // Security & Authentication
  if (combined.includes('auth') || combined.includes('login') || combined.includes('blocked')) return 'auth'
  if (combined.includes('security') || combined.includes('threat') || combined.includes('lockdown') || combined.includes('blacklight')) return 'security'

  return 'other'
}

function detectPriority(event) {
  const notes = (event.notes || '').toLowerCase()
  const data = event.data || {}

  // CRITICAL priority
  if (notes.includes('critical') || notes.includes('error') || notes.includes('failed') || notes.includes('crash')) return 'CRITICAL'
  if (notes.includes('lockdown') || notes.includes('emergency') || notes.includes('threat')) return 'CRITICAL'

  // WARNING priority
  if (notes.includes('warning') || notes.includes('alert') || notes.includes('anomaly')) return 'WARNING'
  if (notes.includes('retry') || notes.includes('timeout') || notes.includes('degraded')) return 'WARNING'

  // NOTICE priority
  if (notes.includes('notice') || notes.includes('info') || notes.includes('complete')) return 'NOTICE'
  if (notes.includes('started') || notes.includes('initialized') || notes.includes('ready')) return 'NOTICE'

  return 'INFO'
}

function priorityScore(priority) {
  const scores = { CRITICAL: 4, WARNING: 3, NOTICE: 2, INFO: 1 }
  return scores[priority] || 0
}

function extractAgentId(notes) {
  if (!notes) return null
  const match = notes.match(/AGENT[_-](\d+)|agent[_-](\d+)|PA[_-](\d+)/i)
  if (match) return `AGENT-${match[1] || match[2] || match[3]}`
  return null
}
