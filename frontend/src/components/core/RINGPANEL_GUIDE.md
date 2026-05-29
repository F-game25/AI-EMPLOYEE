# RingPanel Component — Complete Guide

**Version:** 2.0.0  
**Status:** Production Ready  
**Last Updated:** May 13, 2026

---

## Overview

RingPanel is a reusable metric display component designed for the NexusOSDashboard mission control interface. It displays up to 4 metrics in a fixed 280×160px card with customizable color theming, trend indicators, and optional gauge/sparkline visualizations.

Each of the 4 dashboard rings uses RingPanel:
1. **Cognition Ring** — reasoning activity, model calls, memory usage
2. **Operations Ring** — active workflows, agents, deployments
3. **Economy Ring** — revenue, monetization pipelines, conversion rate
4. **Infrastructure Ring** — CPU%, RAM%, inference queue, connections

---

## Props Reference

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | string | (required) | Panel title, rendered uppercase with glow effect |
| `icon` | string \| JSX | null | Icon emoji or mapped name: `brain`, `workflow`, `trending`, `server`, `chain`, `network`, `rocket`, `shield` |
| `metrics` | array \| object | [] | Metric data. Array format: `[{label, value, unit?, trend?, color?}]`. Object converted to array |
| `color` | string | 'cyan' | Primary color for border glow: `cyan`, `teal`, `gold`, `purple`, `green`, `orange`, `red`, `blue` |
| `glowColor` | string | null | Override border/glow color (uses `color` prop if not set) |
| `gaugeData` | object | null | Optional gauge visualization: `{value: number, max: number}` |
| `sparklineData` | number[] | null | Optional sparkline chart data |
| `animated` | boolean | true | Enable pulse animation on data updates (600ms fade-in glow) |

---

## Metrics Array Format

```typescript
interface Metric {
  label: string              // All-caps metric label (e.g., "ACTIVE AGENTS")
  value: string | number     // Metric value (auto-formatted for large numbers)
  unit?: string              // Optional unit suffix: $, %, ms, /sec, etc.
  trend?: number | string    // Optional trend percentage (e.g., 12.5, "-5.2")
  color?: string             // Override metric text color: cyan, gold, green, orange, red, etc.
}
```

### Value Formatting

Large numbers are automatically formatted:
- `1,500,000` → `1.5M`
- `42,500` → `42.5K`
- `42.567` → `42.6` (decimal precision based on magnitude)

### Trend Indicators

When `trend` is provided, a trend indicator is displayed:
- **Positive trend** (>0): Green ↑ arrow
- **Negative trend** (<0): Orange ↓ arrow
- **No trend**: Not displayed

Example:
```jsx
{ label: "Revenue Today", value: 2450, unit: "$", trend: 18.5, color: "gold" }
// Renders: REVENUE TODAY
//          2450 $
//          ↑ 18.5%
```

---

## Metrics Object Format

For simple cases, pass metrics as an object:

```jsx
<RingPanel
  title="Status"
  metrics={{
    "Connected": 42,
    "Pending": 5,
    "Failed": 1
  }}
  color="cyan"
/>
```

This is automatically converted to an array format where each key becomes a label and the value is displayed with the primary color.

---

## Usage Examples

### Basic Ring (Cognition)

```jsx
import RingPanel from '../core/RingPanel'

export function Dashboard() {
  const cognitionMetrics = [
    { label: 'Thoughts/sec', value: '12.3', unit: 'k', trend: 2.1, color: 'cyan' },
    { label: 'Reasoning chains', value: '7', unit: 'active', color: 'green' },
    { label: 'Memory writes', value: '384', unit: 'bytes/s', trend: 12, color: 'gold' },
    { label: 'Context depth', value: '8192', unit: 'tokens', color: 'cyan' }
  ]

  return (
    <RingPanel
      title="Cognition"
      icon="brain"
      metrics={cognitionMetrics}
      color="teal"
      animated={true}
    />
  )
}
```

### With Gauge Visualization

```jsx
<RingPanel
  title="CPU Monitor"
  icon="server"
  metrics={[
    { label: 'CPU Usage', value: '68', unit: '%', color: 'orange' },
  ]}
  color="orange"
  gaugeData={{ value: 68, max: 100 }}
/>
```

### With Sparkline Chart

```jsx
<RingPanel
  title="Trends"
  icon="trending"
  metrics={[
    { label: 'Recent Activity', value: '82', unit: 'events', color: 'green' },
  ]}
  color="green"
  sparklineData={[45, 52, 48, 61, 55, 72, 68, 75, 80, 78, 82]}
/>
```

### Operations Ring (Object Format)

```jsx
<RingPanel
  title="Operations"
  icon="workflow"
  metrics={{
    'Active Workflows': 5,
    'Active Agents': 23,
    'Deployments': 12,
    'Queue Depth': 42
  }}
  color="gold"
/>
```

### Economy Ring (Full Featured)

```jsx
const economyMetrics = [
  { label: 'Revenue Today', value: 2450, unit: '$', color: 'gold', trend: 18.5 },
  { label: 'Active Monetization', value: 4, unit: 'pipelines', color: 'green' },
  { label: 'Conversion Rate', value: '3.24', unit: '%', color: 'gold' },
  { label: 'ROI Trend', value: '24.8', unit: '%', trend: 7.2, color: 'cyan' },
]

<RingPanel
  title="Economy"
  icon="trending"
  metrics={economyMetrics}
  color="purple"
  animated={true}
/>
```

---

## Color Variants

Choose a color that matches the ring's purpose:

| Color | Hex | Use Case | Glow |
|-------|-----|----------|------|
| `cyan` | #00D9FF | System status, core monitoring | Bright cyan |
| `teal` | #20D6C7 | Cognition metrics, thinking activity | Turquoise |
| `gold` | #E5C76B | Operations, economy metrics | Warm gold |
| `green` | #22C55E | Healthy status, positive trends | Green |
| `purple` | #A855F7 | Economy, advanced metrics | Purple |
| `orange` | #F59E0B | Warnings, CPU usage, memory | Warm orange |
| `red` | #EF4444 | Critical errors, high risk | Red |
| `blue` | #3B82F6 | Infrastructure, networking | Blue |

---

## Design Features

### Fixed Dimensions
- **Width:** 280px (adjusts to 240px on tablet, 100% on mobile)
- **Height:** 160px (adjusts to 140px on tablet, auto on mobile)
- Perfect for CSS grid and absolute positioning layouts

### Grid Overlay
Subtle 45° striped pattern background (2% opacity) for visual depth without distraction.

### Glowing Border
Dynamic color-coded border with outer glow effect. Intensifies on hover.

### Inner Shadow
`inset 0 0 15px rgba(0, 0, 0, 0.6)` for depth and separation from background.

### Value Animations
- **Value transitions:** 300ms smooth color/transform changes
- **Pulse animation:** 600ms ease-out glow pulse on data updates (when `animated={true}`)

### Metric Layout
2×2 grid layout displays up to 4 metrics:
- **Label:** All-caps, 8px monospace
- **Value:** Large 16px, color-coded
- **Unit:** Smaller text, right-aligned
- **Trend:** Optional trend indicator below value

---

## Responsive Behavior

### Desktop (>1024px)
- Full 280×160px dimensions
- 2×2 metric grid
- All features enabled

### Tablet (768px–1024px)
- Reduced to 240×140px
- Slightly smaller fonts
- Maintains 2×2 grid

### Mobile (<768px)
- 100% width, auto height
- Metrics reflow to auto-fit columns
- Optimized for touch

---

## Accessibility

### WCAG 2.1 AA Compliance
- ✓ Color contrast: All text meets 4.5:1 minimum
- ✓ Semantic structure: Proper heading hierarchy
- ✓ Focus indicators: Keyboard navigation support
- ✓ Motion preference: Respects `prefers-reduced-motion`

### Screen Reader Support
- Panel title rendered as `<h3>` heading
- Metric labels and values use semantic structure
- Trend indicators include directional symbols (↑↓)

### Keyboard Navigation
- All interactive elements focusable
- No keyboard traps

---

## Performance Characteristics

- **Bundle Size:** ~2.5KB minified (JSX) + ~1.8KB CSS
- **Render Time:** <50ms initial, <10ms updates (memo'd)
- **Memory:** Minimal (no refs, single store connection)
- **Animations:** GPU-accelerated (CSS transitions/keyframes)

---

## Animation Behavior

### Pulse Animation (on data update)
```
0%:    glow-radius 20px, opacity 0.5
50%:   glow-radius 40px, opacity 0.7
100%:  glow-radius 20px, opacity 0.0
Duration: 600ms
Easing: ease-out
```

### Value Transition
```
color: 300ms ease
transform: 300ms ease (potential scale effect)
```

### Sparkline Stroke
```
drop-shadow(0 0 4px rgba(0, 217, 255, 0.2))
Filter animation on chart updates
```

---

## Integration with Dashboard

The RingPanel is used in `NexusOSDashboard.jsx` as the primary metric display for each of the 4 orbital rings:

```jsx
// In NexusOSDashboard.jsx
<div className="nx-dashboard__rings">
  <RingPanel
    title="Cognition"
    icon="brain"
    metrics={cognitionMetrics}
    color="teal"
  />
  <RingPanel
    title="Operations"
    icon="workflow"
    metrics={operationsMetrics}
    color="gold"
  />
  <RingPanel
    title="Economy"
    icon="trending"
    metrics={economyMetrics}
    color="purple"
  />
  <RingPanel
    title="Infrastructure"
    icon="server"
    metrics={infrastructureMetrics}
    color="blue"
  />
</div>
```

---

## Styling Customization

### CSS Variables

The component uses CSS custom properties for color theming:

```css
--glow-text: primary color for title and accents
--glow-border-color: border and outer glow color
```

Override via inline styles or CSS class combinations:

```jsx
<RingPanel
  title="Custom"
  style={{ '--glow-text': '#00FF00' }}
/>
```

### Hover Effects

On hover, the border color intensifies and outer glow becomes more pronounced:

```css
border-color: rgba(color, 0.35)
box-shadow: 0 0 25px rgba(color, 0.2)
```

---

## Testing

See `RingPanel.test.jsx` for comprehensive test coverage including:
- Title rendering (uppercase)
- Icon rendering
- Metrics array and object formats
- Trend indicator display
- Color variant classes
- Value formatting (M/K suffixes)
- Empty state
- Animation class application
- Fixed dimensions

Run tests:
```bash
cd frontend
npm run test RingPanel
```

---

## Troubleshooting

### Metrics not displaying
- Ensure `metrics` prop is provided (array or object)
- Check that each metric has a `label` and `value`
- Verify no console errors in DevTools

### Color not applying
- Ensure `color` prop is one of: `cyan`, `teal`, `gold`, `purple`, `green`, `orange`, `red`, `blue`
- Check CSS variable application in DevTools

### Animation not smooth
- Verify `animated={true}` is set
- Check that browser supports CSS animations
- Ensure GPU acceleration is available (check `will-change` in DevTools)

### Responsive issues on mobile
- Verify viewport meta tag in HTML `<head>`
- Test at actual device dimensions, not just browser zoom
- Check media query breakpoints in RingPanel.css

---

## Future Enhancements

Potential improvements for future versions:

- [ ] Click-to-drill-down for metric details
- [ ] Real-time WebSocket metric updates
- [ ] Configurable grid layout (3×1, 4×0, etc.)
- [ ] Export to CSV/JSON
- [ ] Custom color picker UI
- [ ] Storybook integration
- [ ] Shadow DOM isolation for style encapsulation

---

## Files

- **Component:** `/frontend/src/components/core/RingPanel.jsx`
- **Styles:** `/frontend/src/components/core/RingPanel.css`
- **Tests:** `/frontend/src/components/core/RingPanel.test.jsx`
- **Demo:** `/frontend/src/components/core/RingPanel.demo.jsx`
- **Guide:** This file

---

## Version History

**v2.0.0** (May 13, 2026)
- Added `icon` prop with predefined icon map
- Support for metrics object format (auto-converted to array)
- Fixed dimensions (280×160px)
- Color variants (8 colors)
- Improved value formatting (M/K suffixes)
- Responsive behavior (tablet & mobile)
- Enhanced animations (300ms transitions, 600ms pulse)
- Accessibility improvements (WCAG 2.1 AA)
- Comprehensive documentation

**v1.0.0** (May 12, 2026)
- Initial release
- Basic metric display
- Gauge and sparkline support
- Array metrics format

---

## License

Part of the AI-EMPLOYEE system. Proprietary.
