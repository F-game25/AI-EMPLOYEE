# EventFeed Component

## Overview

The **EventFeed** is a production-grade operational context stream in the right sidebar (300px fixed width). It provides intelligent semantic event grouping, priority-based animations, and context-aware highlighting to help operators understand system state at a glance.

### Key Features

- **Intelligent Semantic Grouping**: Events grouped by agent ID with deduplication
- **Priority-Based Prioritization**: CRITICAL, WARNING, NOTICE, INFO with distinct animations
- **Context Locking**: Hover/click events to highlight related system elements
- **Smart Auto-Expand**: High-priority groups expand automatically
- **localStorage Persistence**: Filter preferences saved per session
- **Responsive Design**: Scales from desktop (300px) to mobile
- **Accessibility**: Full WCAG 2.1 AA compliance with keyboard navigation

---

## Architecture

### Component Hierarchy

```
EventFeed (main container)
├── Filter Buttons (category selector)
├── Scroll Container
│   └── EventGroup[] (grouped by agentId)
│       ├── Group Header (expandable)
│       ├── Category Breakdown (inline)
│       └── Group Content (conditional expand)
│           └── EventCard[] (individual events)
└── Pause Indicator
```

### Data Flow

1. **Events Stream** → `eventFeedStore.events` (max 200, FIFO)
2. **Categorization** → `categorizeEvent()` (COGNITION, TASK, AGENT, etc.)
3. **Priority Detection** → `detectPriority()` (CRITICAL, WARNING, NOTICE, INFO)
4. **Agent Extraction** → `extractAgentId()` (parse from notes)
5. **Grouping** → `getGroupedEvents()` (group by agentId, sort by max priority)
6. **UI Rendering** → `EventGroup` + `EventCard` with animations

---

## Component Props

### EventFeed

```typescript
interface EventFeedProps {
  autoScroll?: boolean  // Auto-scroll to newest event (default: true)
}
```

---

## Store Integration

### useEventFeedStore

**New Methods:**

```javascript
// Group events semantically
getGroupedEvents() → Array<EventGroup>
  ├─ agentId: string (e.g., "AGENT-07")
  ├─ events: EventRecord[]
  └─ count: number

// Existing methods (unchanged)
addEvent(event)
setEventSnapshot(events)
getEventsByCategory(category)
getRecentEvents(n)
```

**Event Structure:**

```javascript
{
  id: string,              // Unique event ID
  kind: string,            // Original event kind/type
  category: string,        // Categorized: cognition, task, agent, memory, economy, security, brain, infra, artifact, health, auth, other
  priority: string,        // CRITICAL | WARNING | NOTICE | INFO
  notes: string,           // Event message
  data: object,            // Raw event data
  ts: number,              // Timestamp (ms)
  agentId: string | null,  // Extracted agent ID (e.g., "AGENT-07")
  context: object,         // Optional: UI context metadata
}
```

### useSystemStore

**New Properties:**

```javascript
selectedEventId: string | null  // Currently selected event for context locking
setSelectedEventId(id)          // Update selected event
```

---

## Priority Levels

| Level    | Color   | Icon | Animation         | Pulse (ms) | Use Case |
|----------|---------|------|-------------------|------------|----------|
| CRITICAL | Red     | ⚠️   | Flash (300ms)     | 300        | Failures, emergencies |
| WARNING  | Gold    | ⚠    | Pulse (600ms)     | 600        | Retries, timeouts, degraded state |
| NOTICE   | Cyan    | ●    | Soft glow         | 0          | Completed tasks, initialization |
| INFO     | Gray    | ○    | Static            | 0          | Routine events |

---

## Event Categories

| Category      | Icon | Color  | Examples |
|---------------|------|--------|----------|
| COGNITION     | 🧠   | Cyan   | Model calls, reasoning |
| TASK          | ⚡   | Gold   | Execution, workflows |
| AGENT         | 🤖   | Blue   | Agent actions, spawns |
| MEMORY        | 💾   | Purple | Memory reads/writes |
| ECONOMY       | 💰   | Green  | Revenue, monetization |
| SECURITY      | 🛡   | Orange | Threats, lockdown |
| BRAIN         | 🧬   | Cyan   | Graph updates |
| INFRA         | 🖥   | Gray   | System status |
| ARTIFACT      | 📦   | Gold   | Documents, threads |
| HEALTH        | ❤️   | Orange | System health |
| AUTH          | 🔐   | Orange | Login, tokens |

---

## Usage Examples

### Basic Usage

```jsx
import EventFeed from '@/components/core/EventFeed'

export function Dashboard() {
  return (
    <div className="dashboard-layout">
      <main>...</main>
      <aside className="right-sidebar">
        <EventFeed autoScroll={true} />
      </aside>
    </div>
  )
}
```

### Adding Events

```javascript
import { useEventFeedStore } from '@/store/eventFeedStore'

export function AgentExecutor() {
  const addEvent = useEventFeedStore(s => s.addEvent)

  const executeTask = async () => {
    try {
      addEvent({
        kind: 'task_start',
        category: 'task',
        notes: 'AGENT-07: Task execution started',
        ts: Date.now(),
        agentId: 'AGENT-07',
      })

      await performTask()

      addEvent({
        kind: 'task_complete',
        category: 'task',
        priority: 'NOTICE',
        notes: 'AGENT-07: Task completed successfully',
        ts: Date.now(),
        agentId: 'AGENT-07',
      })
    } catch (err) {
      addEvent({
        kind: 'task_error',
        category: 'task',
        priority: 'CRITICAL',
        notes: `AGENT-07: Task failed - ${err.message}`,
        ts: Date.now(),
        agentId: 'AGENT-07',
      })
    }
  }
}
```

### Context Locking (Highlight Relationships)

```jsx
import { useSystemStore } from '@/store/systemStore'

export function RingPanel({ agentId }) {
  const selectedEventId = useSystemStore(s => s.selectedEventId)
  
  // If an event from this agent is selected, highlight
  const isContextLocked = selectedEventId?.includes(agentId)
  
  return (
    <div className={isContextLocked ? 'context-active' : ''}>
      {/* Panel content */}
    </div>
  )
}
```

---

## Styling Guide

### CSS Custom Properties

```css
--ef-critical: #ef4444;   /* Red */
--ef-warning: #fbbf24;    /* Gold */
--ef-notice: #06b6d4;     /* Cyan */
--ef-info: #8b8b96;       /* Gray */
```

### Key Classes

```css
.event-feed                 /* Container */
.event-feed.threat-elevated /* Warning border */
.event-feed.threat-critical /* Critical border + glow */

.event-group                /* Grouped container */
.event-group.context-active /* Highlighted by context lock */
.event-group--critical      /* Priority color variants */
.event-group--warning
.event-group--notice
.event-group--info

.event-group-header         /* Clickable group header */
.event-group-content        /* Expanded events list */
.group-categories           /* Category breakdown */

.event-card                 /* Individual event */
.event-card--selected       /* Selected for context */
.event-card:hover           /* Hover state */

.priority-critical          /* Priority indicator animations */
.priority-warning
.priority-notice
.priority-info
```

---

## Animation Specifications

### Entrance (Event Appears)

```
Duration: 200ms
Easing: easeOut
Opacity: 0 → 1
TranslateX: 20px → 0
TranslateY: 10px → 0
```

### Group Expansion

```
Duration: 200ms
Easing: easeOut
Height: 0 → auto
Opacity: 0 → 1
```

### Priority Animations (Continuous)

**CRITICAL Flash (300ms)**
```
Opacity: 1 → 0.3 → 1
Repeat: infinite
```

**WARNING Pulse (600ms)**
```
Opacity: 1 → 0.6 → 1
Repeat: infinite
```

**NOTICE/INFO**
- Soft glow (no pulse)
- Text shadow: `0 0 6px rgba(6, 182, 212, 0.4)`

---

## Responsive Breakpoints

### Desktop (1280px+)
- Group header: 10px padding
- Event cards: 8-10px padding
- Font sizes: 10-12px
- Full category breakdown visible

### Tablet (1024px - 1280px)
- Group header: 9px padding
- Event cards: 7-9px padding
- Font sizes: 9-11px
- Categories: simplified

### Mobile (768px - 1024px)
- Group header: 8px padding
- Event cards: 6-8px padding
- Font sizes: 8-10px
- Categories: icons only
- Event messages: truncated to 1 line

---

## Accessibility

### WCAG 2.1 AA Compliance

- ✓ Keyboard navigation (Tab, Enter, Arrow keys)
- ✓ Focus visible indicators (2px outline)
- ✓ ARIA labels and roles
- ✓ Color contrast: 4.5:1 minimum
- ✓ Motion respects `prefers-reduced-motion`
- ✓ Semantic HTML structure
- ✓ Screen reader friendly (no decorative elements)

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Cycle through filter buttons, groups |
| Enter/Space | Toggle group expansion, select event |
| Arrow Down | Next event in group |
| Arrow Up | Previous event in group |

---

## Performance Optimizations

1. **Max Events Cap**: 200 events in memory (FIFO queue)
2. **Lazy Grouping**: `getGroupedEvents()` memoized
3. **Framer Motion**: GPU-accelerated animations
4. **CSS Grid Overlay**: 2D background pattern for minimal repaints
5. **Scrollbar Optimization**: Custom webkit scrollbar, 4px width
6. **Will-Change**: Applied to animated elements

---

## Testing

### Test Coverage

- Event grouping logic
- Priority detection
- Agent ID extraction
- Category filtering
- localStorage persistence
- Context locking
- Responsive layout
- Animation triggers

### Run Tests

```bash
npm test -- EventFeed.test.jsx
```

---

## Debugging

### Enable Debug Logging

```javascript
const { events, getGroupedEvents } = useEventFeedStore()
console.log('All events:', events)
console.log('Grouped events:', getGroupedEvents())
```

### Inspect Group Data

```javascript
const groups = useEventFeedStore(s => s.getGroupedEvents())
groups.forEach(group => {
  console.log(`${group.agentId}: ${group.count} events`)
  group.events.forEach(e => {
    console.log(`  - ${e.priority} ${e.category}: ${e.notes}`)
  })
})
```

---

## Future Enhancements

1. **Time Window Filtering**: Show last 5 minutes, 1 hour, etc.
2. **Event Search**: Search by agent, category, priority
3. **Export**: Download event log as JSON/CSV
4. **Correlation**: Link related events across agents
5. **Trend Analysis**: Heatmap of event frequency
6. **Custom Alert Rules**: Fire notifications on specific patterns

---

## API Reference

### Helper Functions

#### categorizeEvent(event) → string
Determines event category based on event type and notes.

#### detectPriority(event) → string
Determines priority level based on event content. Returns: CRITICAL | WARNING | NOTICE | INFO

#### priorityScore(priority) → number
Maps priority to numeric score. CRITICAL=4, WARNING=3, NOTICE=2, INFO=1

#### extractAgentId(notes) → string | null
Extracts agent ID from event notes. Matches patterns: AGENT-01, PA-03, agent_05

---

## Support & Issues

For issues or feature requests, refer to the Dashboard Design Principles in DASHBOARD_DESIGN_PRINCIPLES.md.
