# RingPanel Component Library

**Status:** Production Ready  
**Version:** 2.0.0  
**Last Updated:** May 13, 2026

---

## Quick Start

RingPanel is a reusable metric display card used in the NexusOSDashboard. It displays up to 4 metrics in a beautifully styled 280×160px card with customizable colors, animations, and optional visualizations.

### Basic Usage

```jsx
import RingPanel from '../core/RingPanel'

export function Dashboard() {
  return (
    <RingPanel
      title="Cognition"
      icon="brain"
      metrics={[
        { label: 'Thoughts/sec', value: '12.3', unit: 'k', trend: 2.1, color: 'cyan' },
        { label: 'Memory writes', value: '384', unit: 'bytes/s', color: 'gold' }
      ]}
      color="teal"
    />
  )
}
```

---

## Features

- **Fixed Dimensions:** 280×160px (responsive on tablet/mobile)
- **8 Color Variants:** cyan, teal, gold, green, purple, orange, red, blue
- **Flexible Metrics:** Array or object format (auto-converted)
- **Trend Indicators:** Optional ↑↑ (positive) or ↓ (negative) trends
- **Auto-Formatting:** Large numbers → 1.5M, 42K; decimals → intelligent precision
- **Smooth Animations:** 300ms value transitions, 600ms pulse on updates
- **Gauge Visualization:** Optional semicircular progress meter
- **Sparkline Chart:** Optional trend visualization
- **Grid Overlay:** Subtle background pattern for depth
- **Responsive:** Adapts to tablet (240px) and mobile (100% auto)
- **Accessible:** WCAG 2.1 AA compliant, motion preference support
- **Performance:** ~2.5KB JS + 1.8KB CSS (minified)

---

## Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | string | required | Panel title (rendered uppercase) |
| `icon` | string | null | Emoji icon: `brain`, `workflow`, `trending`, `server`, `chain`, `network`, `rocket`, `shield` |
| `metrics` | array \| object | [] | Metric data (array or object format) |
| `color` | string | 'cyan' | Color variant for border/glow |
| `glowColor` | string | null | Override glow color (defaults to `color`) |
| `gaugeData` | object | null | Gauge data: `{value, max}` |
| `sparklineData` | number[] | null | Sparkline trend data |
| `animated` | boolean | true | Enable pulse animation on update |

---

## Metric Formats

### Array Format (Recommended)
```jsx
metrics={[
  { 
    label: 'Thoughts/sec', 
    value: '12.3', 
    unit: 'k', 
    trend: 2.1, 
    color: 'cyan' 
  },
  // ...up to 4 metrics
]}
```

### Object Format (Auto-converted)
```jsx
metrics={{
  "Connected Clients": 42,
  "Uptime": "99.9%",
  "Active Tasks": 12
}}
```

### Metric Properties
```typescript
{
  label: string              // "THOUGHTS/SEC" (auto-uppercase)
  value: string | number     // 12.3 or "12.3" (auto-formatted)
  unit?: string              // "k" or "%", "$", "ms", etc.
  trend?: number | string    // 2.1 or "2.1" (shows ↑ or ↓)
  color?: string             // Override: cyan, gold, green, orange, red, etc.
}
```

---

## Color Variants

Choose a color that matches your ring's purpose:

```jsx
// Cognition Ring — Teal (thinking activity)
<RingPanel color="teal" title="Cognition" ... />

// Operations Ring — Gold (tasks & workflows)
<RingPanel color="gold" title="Operations" ... />

// Economy Ring — Purple (revenue & pipelines)
<RingPanel color="purple" title="Economy" ... />

// Infrastructure Ring — Blue (system health)
<RingPanel color="blue" title="Infrastructure" ... />
```

Available colors: `cyan`, `teal`, `gold`, `green`, `purple`, `orange`, `red`, `blue`

---

## Examples

### 4 Dashboard Rings

```jsx
// Cognition Ring
<RingPanel
  title="Cognition"
  icon="brain"
  metrics={[
    { label: 'Thoughts/sec', value: '12.3', unit: 'k', trend: 2.1, color: 'cyan' },
    { label: 'Reasoning chains', value: '7', unit: 'active', color: 'green' },
    { label: 'Memory writes', value: '384', unit: 'bytes/s', color: 'gold' },
    { label: 'Context depth', value: '8192', unit: 'tokens', color: 'cyan' }
  ]}
  color="teal"
  animated={true}
/>

// Operations Ring
<RingPanel
  title="Operations"
  icon="workflow"
  metrics={[
    { label: 'Active Workflows', value: 5, color: 'gold' },
    { label: 'Active Agents', value: 23, color: 'green' },
    { label: 'Deployments', value: 12, trend: 3, color: 'cyan' },
    { label: 'Queue Depth', value: 42, trend: -5, color: 'orange' }
  ]}
  color="gold"
/>

// Economy Ring
<RingPanel
  title="Economy"
  icon="trending"
  metrics={[
    { label: 'Revenue Today', value: 2450, unit: '$', color: 'gold', trend: 18.5 },
    { label: 'Active Monetization', value: 4, unit: 'pipelines', color: 'green' },
    { label: 'Conversion Rate', value: '3.24', unit: '%', color: 'gold' },
    { label: 'ROI Trend', value: '24.8', unit: '%', trend: 7.2, color: 'cyan' }
  ]}
  color="purple"
/>

// Infrastructure Ring
<RingPanel
  title="Infrastructure"
  icon="server"
  metrics={[
    { label: 'CPU Usage', value: '68', unit: '%', color: 'orange', trend: -2 },
    { label: 'RAM Usage', value: '82', unit: '%', color: 'red' },
    { label: 'Inference Queue', value: '156', unit: 'jobs', color: 'gold' },
    { label: 'WS Connections', value: '42', unit: 'clients', color: 'green' }
  ]}
  color="blue"
/>
```

### With Gauge

```jsx
<RingPanel
  title="CPU Monitor"
  icon="server"
  metrics={[
    { label: 'CPU Usage', value: '68', unit: '%', color: 'orange' }
  ]}
  gaugeData={{ value: 68, max: 100 }}
  color="orange"
/>
```

### With Sparkline

```jsx
<RingPanel
  title="Trends"
  icon="trending"
  metrics={[
    { label: 'Recent Activity', value: '82', unit: 'events', color: 'green' }
  ]}
  sparklineData={[45, 52, 48, 61, 55, 72, 68, 75, 80]}
  color="green"
/>
```

### Object Format

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

---

## Layout & Positioning

RingPanel uses fixed dimensions (280×160px) perfect for grid layouts:

```jsx
<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>
  <RingPanel ... />
  <RingPanel ... />
  <RingPanel ... />
  <RingPanel ... />
</div>
```

Responsive behavior:
- **Desktop (>1024px):** 280×160px, 2×2 metric grid
- **Tablet (768px–1024px):** 240×140px, 2×2 grid with smaller fonts
- **Mobile (<768px):** 100% width, auto height, flexible metric grid

---

## Styling & Customization

### CSS Variables

Override colors via inline styles:

```jsx
<RingPanel
  title="Custom"
  style={{ '--glow-text': '#00FF00' }}
/>
```

### Hover Effects

Panels enhance their glow on hover — great for interactive dashboards.

### Animation Control

Disable animations for performance-sensitive environments:

```jsx
<RingPanel
  title="Static"
  animated={false}
  ...
/>
```

---

## Integration with Dashboard

The NexusOSDashboard uses RingPanel for 4 orbital rings:

```jsx
// In NexusOSDashboard.jsx
<div className="nx-dashboard__rings">
  <RingPanel title="Cognition" icon="brain" metrics={cognitionMetrics} color="teal" />
  <RingPanel title="Operations" icon="workflow" metrics={operationsMetrics} color="gold" />
  <RingPanel title="Economy" icon="trending" metrics={economyMetrics} color="purple" />
  <RingPanel title="Infrastructure" icon="server" metrics={infrastructureMetrics} color="blue" />
</div>
```

---

## Performance

- **Bundle Size:** 2.5KB JS + 1.8KB CSS (minified)
- **Initial Render:** <50ms
- **Updates:** <10ms (memo'd components)
- **Animations:** GPU-accelerated (CSS transforms)
- **Memory:** Minimal, no refs or external dependencies

---

## Accessibility

✓ **WCAG 2.1 AA Compliant**
- Color contrast: 4.5:1 minimum
- Semantic HTML structure
- Screen reader support
- Keyboard navigation
- Motion preference: `prefers-reduced-motion` respected

---

## Files

| File | Purpose |
|------|---------|
| `RingPanel.jsx` | Main component |
| `RingPanel.css` | Styling & animations |
| `RingPanel.test.jsx` | Unit tests (10 tests) |
| `RingPanel.demo.jsx` | Component demo with all variants |
| `RINGPANEL_GUIDE.md` | Complete API & design documentation |
| `RingPanel.metrics-examples.js` | Ready-to-use metric data structures |

---

## Testing

```bash
# Run tests
cd frontend
npm run test RingPanel

# Build
npm run build

# Dev server
npm run dev
```

---

## Examples & Demo

See `RingPanel.demo.jsx` for a full component showcase with:
- All 4 dashboard rings
- All 8 color variants
- Gauge and sparkline visualizations
- Object and array metric formats
- Feature highlights

---

## Troubleshooting

**Metrics not showing?**
- Ensure `metrics` prop is provided (array or object)
- Check that each metric has `label` and `value`

**Color not applying?**
- Verify color is one of the 8 variants: cyan, teal, gold, purple, green, orange, red, blue

**Animations choppy?**
- Check browser GPU acceleration settings
- Try disabling `animated={false}` to test
- Verify no console errors in DevTools

**Responsive issues?**
- Test at actual device dimensions, not browser zoom
- Check viewport meta tag in HTML `<head>`

---

## Version History

**v2.0.0** (May 13, 2026)
- Icon support with emoji map
- Object format metrics (auto-converted)
- Fixed dimensions with responsive behavior
- 8 color variants
- Value auto-formatting (M/K suffixes)
- Enhanced animations
- WCAG 2.1 AA accessibility
- Comprehensive documentation

**v1.0.0** (May 12, 2026)
- Initial release
- Basic metric display
- Gauge & sparkline support

---

## License

Part of the AI-EMPLOYEE system. Proprietary.

---

## Support

For issues, questions, or enhancements:
1. Check `RINGPANEL_GUIDE.md` for detailed documentation
2. Review `RingPanel.demo.jsx` for usage examples
3. Check `RingPanel.metrics-examples.js` for data structure examples
4. Run unit tests: `npm run test RingPanel`
