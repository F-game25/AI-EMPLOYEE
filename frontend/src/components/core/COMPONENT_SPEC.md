# Core Components Library — Mission Control UI System

Complete specifications for the 6 supporting components that form the mission control infrastructure.

---

## 1. RingPanel

**Location:** `RingPanel.jsx` / `RingPanel.css`

**Purpose:** Reusable card component for displaying metrics in orbiting system rings (Cognition, Operations, Economy, Infrastructure).

### Props

```typescript
interface RingPanelProps {
  title: string                    // Panel title, rendered uppercase
  metrics?: Array<{
    label: string                  // All-caps metric label
    value: string | number         // Metric value
    trend?: number                 // Percentage trend (can be negative)
    color?: 'cyan' | 'gold' | 'teal' | 'green' | 'orange' | 'red'
    unit?: string                  // Optional unit suffix ($, %, ms, etc)
  }>
  glowColor?: 'cyan' | 'gold' | 'teal' | 'purple' | 'green' | 'orange' | 'red'
  gaugeData?: {
    value: number                  // Current gauge value
    max: number                    // Gauge maximum
  }
  sparklineData?: number[]         // Array of values for sparkline chart
  animated?: boolean               // Enable pulse animation on data update
}
```

### Styling

- **Background:** `rgba(7, 8, 16, 0.95)` (dark surface)
- **Border:** 1px solid `rgba(0, 217, 255, 0.15)` (cyan glow)
- **Glow Effect:** Inner shadow `inset 0 0 10px rgba(0, 0, 0, 0.5)` + border glow
- **Grid Overlay:** 45° striped pattern at low opacity
- **Animation:** Pulse on data update (600ms, fade-in glow)

### Usage Example

```jsx
<RingPanel
  title="Cognition Ring"
  metrics={[
    { label: 'LLM Calls', value: 342, trend: 12, color: 'gold' },
    { label: 'Reasoning', value: '0.84', color: 'cyan', unit: 'score' },
    { label: 'Memory', value: '78%', trend: -3, color: 'orange' }
  ]}
  glowColor="cyan"
  animated={true}
/>
```

### Variants

- **With Gauge:** Pass `gaugeData` to render semicircular progress meter
- **With Sparkline:** Pass `sparklineData` array to render live trend chart
- **Color-Coded Metrics:** Use `color` prop to highlight health status (green=good, orange=warning, red=critical)

---

## 2. SystemBar

**Location:** `SystemBar.jsx` / `SystemBar.css`

**Purpose:** Fixed top status strip (40px height) displaying live system state.

### Props

```typescript
interface SystemBarProps {
  onEmergencyStop?: () => void     // Callback for emergency stop button
}
```

### Exported Modules (L-to-R)

1. **Timer** — Live HH:MM:SS in cyan monospace
2. **Mode Chip** — BALANCED/PRECISION/PERFORMANCE with gold gradient background
3. **Uptime Counter** — ↑ HH:MM:SS since system start
4. **Threat Indicator** — ◉ colored dot + label (SAFE/CAUTION/WARNING/CRITICAL)
5. **Cost Today** — $X.XX in gold text
6. **Python Backend Status** — ◉ dot cyan (healthy) or gray (down)
7. **WebSocket Status** — ◉ dot cyan (connected) or gray (disconnected)
8. **Emergency Stop** — Red button (fixed right, always visible)

### Data Sources

All values sourced from Zustand stores via WS events (zero polling):
- `systemStatus` — mode
- `securityStatus` — threat_score
- `revenue` — cost_today
- `pythonBackendReady` — backend status
- `wsConnected` — WebSocket connection state

### Styling

- **Height:** 40px, fixed position top of viewport (z-index: 60)
- **Background:** Dark with grid overlay and backdrop blur
- **Modules:** Individual pills with hover effects
- **Status Dots:** 6px radius, pulsing animation with category colors
- **Emergency Stop:** Red gradient, glow effect on hover

### Usage Example

```jsx
<SystemBar
  onEmergencyStop={() => {
    alert('EMERGENCY STOP TRIGGERED')
    stopAllAgents()
  }}
/>
```

---

## 3. EventFeed

**Location:** `EventFeed.jsx` / `EventFeed.css`

**Purpose:** Semantic event stream display with category filtering and auto-scroll.

### Props

```typescript
interface EventFeedProps {
  maxEvents?: number               // Max events to retain (default 200)
  autoScroll?: boolean             // Auto-scroll to newest event (default true)
}
```

### Event Schema

```typescript
interface SystemEvent {
  category: 'cognition' | 'task' | 'agent' | 'memory' | 'economy' | 'security' | 'brain' | 'infra'
  timestamp: Date | string         // ISO 8601 or Date object
  label: string                    // Event type label
  message?: string                 // Detailed event message
  metric?: {
    name: string
    value: number | string
    unit?: string
  }
}
```

### Category Configuration

| Category | Icon | Color | Use Case |
|----------|------|-------|----------|
| `cognition` | 🧠 | Cyan | LLM reasoning, model decisions |
| `task` | ⚡ | Gold | Task execution, workflow steps |
| `agent` | 🤖 | Info Blue | Agent startup, status changes |
| `memory` | 💾 | Purple | Memory writes, vector store updates |
| `economy` | 💰 | Green | Revenue events, cost tracking |
| `security` | 🛡 | Warning Orange | Security alerts, threat detection |
| `brain` | 🧬 | Cyan | Brain state updates, consciousness events |
| `infra` | 🖥 | Muted Gray | System infrastructure, health checks |

### Features

- **Category Filtering:** Radio buttons to filter by event type (default: ALL)
- **Auto-Scroll:** Automatically scrolls to newest event when feed receives data
- **Pause on Hover:** Allows manual inspection without auto-scroll interruption
- **Age-Based Opacity:** Older events fade progressively (min 40%, max 100%)
- **Max Events Limit:** Automatically removes oldest events when limit reached

### Styling

- **Container:** Dark background, cyan border, grid overlay
- **Event Cards:** 4px colored left border (category-specific), hover effects
- **Scrollbar:** Thin, cyan-tinted, smooth scroll
- **Filter Buttons:** Dark background, cyan text, glow when active

### Usage Example

```jsx
<EventFeed maxEvents={200} autoScroll={true} />
```

### Integration with Zustand

Events should be added via:
```javascript
const addEvent = useAppStore(s => s.addEvent)

addEvent({
  category: 'cognition',
  timestamp: new Date(),
  label: 'LLM Call',
  message: 'Claude Opus v4.5 inference completed',
  metric: { name: 'Tokens', value: 1024, unit: 'tokens' }
})
```

---

## Design Tokens (CSS Variables)

All components use these design system tokens for consistency:

```css
/* Colors */
--cyan: #00D9FF
--gold: #E5C76B
--success: #22C55E
--warning: #F59E0B
--error: #EF4444
--text-primary: #F4F4F8
--text-secondary: #B8B8C4
--text-muted: #8A8A96

/* Surfaces */
--mc-black: #070810
--mc-surface: rgba(7, 8, 16, 0.95)

/* Shadows & Glows */
--shadow-glow: 0 0 20px rgba(0, 217, 255, 0.2)
--text-glow: 0 0 10px rgba(0, 217, 255, 0.3)

/* Transitions */
--duration-fast: 150ms
--duration-normal: 250ms
--ease-out: cubic-bezier(0.16, 1, 0.3, 1)

/* Typography */
Font Mono: 'JetBrains Mono', monospace
Font Primary: 'Inter', system-ui, sans-serif
```

---

## Accessibility Features

### WCAG 2.1 AA Compliance

- **Color Contrast:** All text meets WCAG AA (4.5:1 minimum)
- **Focus Indicators:** Keyboard navigation via `:focus-visible`
- **Semantic HTML:** Proper heading hierarchy, button roles
- **Screen Reader Support:** `aria-label` for status indicators, descriptive text
- **Motion:** Animations respect `prefers-reduced-motion`

### Component-Specific A11y

**RingPanel:**
- Metric labels in all-caps for clarity
- Trend indicators include direction arrows and numeric values
- Gauge visualization includes numeric display

**SystemBar:**
- Status dots have `aria-label` describing their state
- Emergency stop button has high contrast (4:1 red on dark)
- All timestamps use monospace for precision

**EventFeed:**
- Category filter buttons accessible via keyboard
- Event cards have sufficient line-height (1.4) for readability
- Timestamp display uses `font-variant-numeric: tabular-nums` for alignment

---

## Performance Considerations

- **Memo:** All components use useMemo for derived state
- **Lazy Rendering:** EventFeed limits DOM nodes via maxEvents
- **Efficient Updates:** Only re-render on actual data changes (WS events)
- **CSS Animations:** Use GPU-accelerated transforms where possible
- **Scrolling:** Virtual scroll not needed (max 200 events, ~3KB per event)

---

## Integration Checklist

- [ ] Import components from `/frontend/src/components/core/index.js`
- [ ] Ensure Zustand stores export required state (systemStatus, securityStatus, revenue, events)
- [ ] Connect WebSocket event broadcaster to event feed
- [ ] Test SystemBar with Python backend down scenario
- [ ] Verify EventFeed category filtering across all 8 categories
- [ ] Validate WCAG 2.1 AA with axe DevTools
- [ ] Test mobile responsiveness (768px, 1024px breakpoints)
- [ ] Verify animations respect `prefers-reduced-motion`

---

## File Manifest

```
frontend/src/components/core/
├── RingPanel.jsx           (120 lines, metric card component)
├── RingPanel.css           (100 lines, styling + animations)
├── SystemBar.jsx           (150 lines, top status bar)
├── SystemBar.css           (80 lines, layout + module styles)
├── EventFeed.jsx           (180 lines, event stream + filtering)
├── EventFeed.css           (120 lines, card styles + scrolling)
├── index.js                (exports for easy importing)
└── COMPONENT_SPEC.md       (this document)
```

---

## Version

- **Created:** May 12, 2026
- **Component Library Version:** 1.0.0
- **Design System:** Mission Control Theme
- **Compatibility:** React 18+, Zustand 4+, Tailwind CSS 3+
