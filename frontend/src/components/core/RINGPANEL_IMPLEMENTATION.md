# RingPanel Component Implementation Guide

**Version:** 3.0  
**Status:** Production Ready  
**Last Updated:** 2026-05-13

## Overview

RingPanel is a reusable card component that displays metrics for each of the 4 dashboard rings (Cognition, Ops, Economy, Infra). It implements progressive disclosure with smooth animations, health status indicators, context locking, and a detail modal.

## Features

### Progressive Disclosure
- **Collapsed State (Default)**: Shows 4 primary metrics + sparkline + health indicator
- **Hover/Expanded State**: Reveals additional metrics, events, and gauges (200ms fade-in animation)
- **Detail Modal**: Click any metric to open full detail view with complete context

### Health Status Animations
- **Healthy**: Slow breathing pulse (0.3 opacity, 3s cycle)
- **Busy**: Faster pulse with scale animation (1.5s cycle, increased glow)
- **Warning**: Intermittent pulse (600ms on/off, gold color)
- **Critical**: Sharp flashes (300ms intervals, red color)
- **Offline**: Frozen, desaturated (no motion)

### Context Locking
When an event is selected, related RingPanel automatically:
- Highlights border with increased glow
- Scrolls into view if off-screen
- Emits custom `contextLocked` event for other components to listen

### Responsive Design
- **Desktop (1400px+)**: Fixed 280×160px
- **Tablet (768-1399px)**: 240×140px
- **Mobile (<768px)**: 100% width, stacked layout

## Props

```javascript
RingPanel.propTypes = {
  // Core
  title: PropTypes.string.isRequired,           // Ring name (e.g., "COGNITION RING")
  color: PropTypes.string,                      // Color variant (default: 'cyan')
  icon: PropTypes.string,                       // Icon key or emoji

  // Metrics
  metrics: PropTypes.array,                     // Primary 4 metrics
  additionalMetrics: PropTypes.array,           // Extra metrics shown on expand
  
  // Visualization
  sparklineData: PropTypes.array,               // Trend data for sparkline
  gaugeData: PropTypes.object,                  // { value, max } for gauge
  recentEvents: PropTypes.array,                // Recent event list
  
  // State & Behavior
  healthStatus: PropTypes.oneOf([               // Animation state
    'healthy', 'busy', 'warning', 'critical', 'offline'
  ]),
  animated: PropTypes.bool,                     // Pulse on update
  context: PropTypes.object,                    // Context metadata for locking
  onMetricClick: PropTypes.func,                // Custom metric click handler
}
```

## Usage Example

```jsx
import RingPanel from './components/core/RingPanel'

export default function Dashboard() {
  const cognitionMetrics = [
    { label: 'THOUGHT/SEC', value: 124.5, trend: 2.3, unit: 'thoughts' },
    { label: 'CONTEXT SIZE', value: 4280, trend: -1.2, unit: 'tokens' },
    { label: 'INFERENCE TIME', value: 842, trend: 0, unit: 'ms' },
    { label: 'MEMORY USAGE', value: 87.3, trend: 0.5, unit: '%' },
  ]

  const additionalMetrics = [
    { label: 'REASONING CHAINS', value: 42, trend: 3.1, unit: 'chains' },
    { label: 'ACTIVE MEMORY', value: 2.1, trend: 1.8, unit: 'MB' },
  ]

  const recentEvents = [
    { time: '14:32', text: 'Context window refresh (2.1MB freed)' },
    { time: '14:28', text: 'New reasoning chain initiated' },
  ]

  return (
    <RingPanel
      title="COGNITION RING"
      icon="brain"
      color="cyan"
      metrics={cognitionMetrics}
      additionalMetrics={additionalMetrics}
      recentEvents={recentEvents}
      healthStatus="healthy"
      sparklineData={[10, 45, 32, 65, 78, 92, 85, 95, 102]}
      context={{ ringId: 'cognition', type: 'cognitive' }}
      animated
    />
  )
}
```

## Metric Object Format

Each metric in the array should follow this structure:

```javascript
{
  label: string,        // e.g., "THOUGHT/SEC" (will be uppercase)
  value: number|string, // Current value
  unit: string,         // Optional unit suffix (e.g., "ms", "%")
  trend: number,        // Optional trend % (positive = green ↑, negative = orange ↓)
  color: string         // Optional color override
}
```

## Recent Events Format

Events shown in expanded view:

```javascript
{
  time: string,        // e.g., "14:32" or "2 min ago"
  text: string         // Event description (truncated to 1 line)
}
```

## Context Locking Integration

### Dispatching Events

When a user selects an event or component that relates to a specific ring:

```javascript
window.dispatchEvent(
  new CustomEvent('contextLocked', {
    detail: { context: { ringId: 'cognition' } }
  })
)
```

### Listening for Context

RingPanel automatically listens for the `contextLocked` event. Pass a `context` object with `ringId`:

```jsx
<RingPanel
  title="COGNITION RING"
  color="cyan"
  metrics={metrics}
  context={{ ringId: 'cognition', type: 'cognitive' }}
/>
```

When `context.ringId` matches the event, the panel:
- Adds `ring-panel--context-active` class
- Highlights border with increased glow
- Scrolls into view

## Health Status Semantics

| Status | Animation | Meaning |
|--------|-----------|---------|
| healthy | Slow breathing (3s) | All systems normal, low activity |
| busy | Fast pulse (1.5s) + scale | High inference load, queue building |
| warning | Intermittent (600ms) | Issues detected, monitor closely |
| critical | Sharp flashes (300ms) | Failures occurring, immediate action needed |
| offline | Frozen | Component disconnected or unavailable |

## Detail Modal

Clicking any metric opens a detail modal showing:
- Full title and health status
- All metrics in a grid
- Sparkline chart (if provided)
- Gauge visualization (if provided)
- Context information (if provided)

Close with:
- Escape key
- Click outside modal
- Close button

## Styling & Theming

### Color Variants

```css
ring-panel--cyan    /* #00D9FF */
ring-panel--teal    /* #20D6C7 */
ring-panel--gold    /* #E5C76B */
ring-panel--green   /* #22C55E */
ring-panel--orange  /* #F59E0B */
ring-panel--red     /* #EF4444 */
ring-panel--blue    /* #3B82F6 */
ring-panel--purple  /* #A855F7 */
```

### CSS Variables

Override default glow colors via inline styles:

```jsx
<RingPanel
  title="COGNITION"
  color="cyan"
  style={{
    '--glow-border-color': 'rgba(0, 217, 255, 0.3)',
    '--glow-text': '#00D9FF',
  }}
/>
```

## Animation Timing

Per DASHBOARD_DESIGN_PRINCIPLES.md:

| Action | Duration | Easing |
|--------|----------|--------|
| Metric fade-in | 200ms | ease-out |
| Panel transition | 250ms | cubic-bezier(0.16, 1, 0.3, 1) |
| Modal open | 300ms | ease-out |
| Event insertion | 200ms | ease-out |
| Health pulse | 3s (healthy) - 300ms (critical) | ease-in-out or step |

## Accessibility

- Full keyboard support (click to expand, Enter to activate)
- Focus-visible outlines on panel and metric items
- Respects `prefers-reduced-motion` media query (disables all animations)
- Semantic HTML with proper ARIA labels
- High contrast text on dark background (WCAG AA compliant)

## Performance Notes

- Uses React Hooks (useState, useEffect, useRef, useCallback, useMemo)
- Minimal re-renders via memoization
- CSS animations use GPU acceleration (transform, opacity)
- No janky layout shifts (fixed container dimensions)
- Lightweight SVG sparkline rendering

## Testing

Run unit tests:

```bash
npm test -- RingPanel.test.jsx
```

See `RingPanel.test.jsx` for:
- Metric rendering
- State transitions (collapsed/expanded)
- Event dispatch handling
- Modal open/close
- Health status styling
- Accessibility checks

## Integration with Dashboard

In your main dashboard component:

```jsx
import RingPanel from './components/core/RingPanel'
import { useSystemStore } from './store/systemStore'
import { useEventFeedStore } from './store/eventFeedStore'

export default function Dashboard() {
  const { cognitionMetrics, opsMetrics, economyMetrics, infraMetrics } = useSystemStore()
  const { selectedEvent } = useEventFeedStore()

  return (
    <div className="dashboard-rings">
      <RingPanel
        title="COGNITION RING"
        icon="brain"
        color="cyan"
        metrics={cognitionMetrics}
        healthStatus={cognitionMetrics.health}
        context={{ ringId: 'cognition', eventId: selectedEvent?.id }}
        sparklineData={cognitionMetrics.sparkline}
        animated
      />
      {/* Repeat for Ops, Economy, Infra */}
    </div>
  )
}
```

## Troubleshooting

### Modal doesn't close on Escape
Ensure the modal backdrop is the topmost z-index. Check CSS stacking context.

### Health animation not smooth
Check `prefers-reduced-motion` user setting. Some browsers disable animations system-wide.

### Context locking not triggering
Ensure `context.ringId` exactly matches the event's `context.ringId`. Check browser console for `contextLocked` event.

### Metric click not opening modal
If you pass a custom `onMetricClick` handler, implement modal logic yourself.

### Responsive layout broken
Check that parent container allows flex/grid layout. Mobile testing: use DevTools device emulation.

## Future Enhancements

- [ ] Drag-to-reorder panels
- [ ] Collapsible sections (metrics, events)
- [ ] Export metrics as CSV/JSON
- [ ] Custom alert thresholds
- [ ] Sound notifications for critical status
- [ ] Metric history with date range picker

---

**Files:**
- Component: `/frontend/src/components/core/RingPanel.jsx`
- Styles: `/frontend/src/components/core/RingPanel.css`
- Tests: `/frontend/src/components/core/RingPanel.test.jsx`
- Demo: `/frontend/src/components/core/RingPanel.demo.jsx`
