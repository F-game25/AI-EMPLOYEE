# Performance Tuning Guide — Wavefield Routing UI

## Current Metrics
- **Frontend bundle**: 255 KB gzipped (79 KB core, 175 KB vendors)
- **Page transition**: ~60ms (spring animation: stiffness 350, damping 25)
- **Boot sequence**: 8.5s cinematic (all timelines synchronized)
- **Panel render**: ~16ms (memoized, GPU-accelerated with CSS transforms)
- **Bloom effect**: Adaptive intensity (0.4–1.0) driven by system load

---

## Tuning Parameters

### 1. Panel Animation (HolographicPanel.jsx)
```javascript
// Current: Snappy, premium feel
transition={{ type: 'spring', stiffness: 350, damping: 25, mass: 0.8 }}

// For slower, bouncier feel:
// stiffness: 250, damping: 20

// For rigid, immediate feel:
// stiffness: 500, damping: 40

// Profile: Measure FPS impact via DevTools Performance tab
```

### 2. Bloom Intensity (NeuralCore/index.jsx)
```javascript
// Current: Driven by system load
<Bloom intensity={metrics.load * 1.5} ... />

// Tuning:
// Reduce multiplier for subtle glow: intensity={metrics.load * 1.0}
// Increase for dramatic effect: intensity={metrics.load * 2.0}
// Fix at constant: intensity={0.7}
```

### 3. Particle System (DataStreamHighway.jsx)
```javascript
// Current: 56 particles (7 lanes × 8 per lane)
// Tuning by lane: search for "instanced_particles" and adjust count
// Reduce for older GPUs: 4–5 particles per lane
// Increase for RTX/high-end: 10–12 particles per lane

// Monitor: GPU memory via Chrome DevTools → Rendering → GPU Memory
```

### 4. Boot Timeline (AwakeningScene.jsx)
```javascript
// Key milestones (all durations in seconds):
// t=0.0:    Black void (no change needed)
// t=0.4:    Horizon ripple (adjust via gsap.from duration)
// t=1.2:    Octahedron unfold
// t=3.5:    Sphere breath cycle
// t=4.5:    Synaptic nodes light
// t=6.0:    Name typewriter
// t=7.5:    Retina scan
// t=8.0:    Welcome message
// t=8.5:    Dashboard reveal (camera dolly)

// To speed up boot by 20%, multiply all durations by 0.8
// To add drama, slow to 1.2x
```

### 5. Ambient Soundscape (useAmbientSoundscape.js)
```javascript
// Master gain: 0.1 (very subtle)
// Tuning: Increase to 0.2 for more presence, reduce to 0.05 for background

// Frequency blending on mood transitions:
// Current: Exponential ramp over 400ms
// To speed up: 200ms
// To smooth out: 600ms
```

### 6. Polling Intervals
```javascript
// Metrics polling: 5000ms (5 seconds)
// Tuning: Reduce to 2000ms for real-time feel (higher CPU)
//         Increase to 10000ms to reduce polling overhead

// Presence update: 100ms
// Tuning: Reduce to 50ms for smoother cursor (network traffic)
//         Increase to 200ms to reduce bandwidth

// Search in DashboardPageNEW.jsx:
// setInterval(poll, 5000);  // ← Change here
```

---

## Bottleneck Diagnosis

### High FPS Drop (below 50 FPS)?
1. **Bloom intensity too high**: Reduce `<Bloom intensity={...} />`
2. **Too many particles**: Reduce particle count in DataStreamHighway
3. **Frequent state updates**: Check that memoization is applied (`React.memo`)
4. **Large JSX trees**: Profile with React DevTools Profiler

### High CPU (>80%)?
1. **Polling too frequent**: Increase interval from 5s to 10s
2. **Mesh complexity**: Reduce `detail` parameter in Three.js geometries
3. **Unmemoized components**: Verify all pages have `export default memo(...)`

### High Memory (>200 MB)?
1. **Vector store cache growing**: Limit in `runtime/core/memory_index.py` (MAX_ENTRIES)
2. **Message history unbounded**: Trim chat in `appStore.js` (keep last 100 messages)
3. **Particle system instancing**: Reduce particle count

### Network Bandwidth (>1 MB/s)?
1. **Presence broadcasts too frequent**: Increase from 100ms to 500ms
2. **Metrics polling too detailed**: Remove unused metrics from polling

---

## Optimization Checklist

- [ ] **Gzip compression**: Verify `npm run build` produces gzipped assets (255 KB target)
- [ ] **Code splitting**: Verify lazy loading of page components in `Dashboard.jsx`
- [ ] **Image optimization**: Convert any PNG→WebP, optimize SVG paths
- [ ] **CSS minification**: Run `npm run build` (automatically minifies)
- [ ] **Component memoization**: All pages wrapped with `React.memo` ✓
- [ ] **Event delegation**: HolographicPanel uses single `onMouseMove` ✓
- [ ] **Virtual scrolling**: Long lists (agents, tasks) should use `react-window` (future)
- [ ] **Service Worker**: Cache-first strategy for assets (future)
- [ ] **Lighthouse audit**: Run via Chrome DevTools (target: 90+)

---

## Real-World Tuning Guide

### For 4G/Slow Network
```javascript
// Reduce polling frequency
5000ms → 15000ms  // metrics polling
100ms → 500ms     // presence updates
// Reduce particle count
7 lanes × 8 particles → 5 particles per lane
// Simplify bloom
intensity = 0.4 (fixed)
```

### For High-End GPU (RTX/RTX4000)
```javascript
// Increase visual fidelity
particles: 12 per lane
bloom intensity: 2.0x multiplier
geometry detail: +2 (sphere: 48 segments vs 32)
```

### For Low-End GPU (Intel Iris/Mobile)
```javascript
// Reduce load
particles: 3 per lane
bloom intensity: 0.5x multiplier (max 0.8)
disable drop shadows (CSS filter: none)
reduce animation frame rate (60 FPS → 30 FPS)
```

---

## Measurement Tools

### 1. Chrome DevTools Performance
```
1. Open DevTools → Performance tab
2. Click record
3. Interact with UI (click pages, drag panels)
4. Stop recording
5. Analyze: Main thread activity, FPS dips, long tasks
```

### 2. React DevTools Profiler
```
1. Install React DevTools extension
2. Open app, go to Profiler tab
3. Record page transitions
4. Check: Render duration, commit time
5. Flag components with >16ms render time
```

### 3. Network Tab
```
1. DevTools → Network
2. Reload page
3. Check: Total bandwidth, gzip ratio, slow requests
4. Target: <2 MB total, <500 KB JavaScript
```

### 4. Lighthouse (PWA audit)
```
1. DevTools → Lighthouse
2. Run audit (mobile)
3. Check: Performance, Accessibility, Best Practices
4. Target: 90+ in all categories
```

---

## Useful Optimizations (Already Applied)

✓ Panel animations: `stiffness: 350, damping: 25` (snappier than default)
✓ Component memoization: All pages wrapped with `React.memo`
✓ Lazy loading: Page components loaded on-demand via `lazy()` + `Suspense`
✓ Event batching: State updates batched within event handlers
✓ Bloom adaptive: Intensity scales with system load, not fixed
✓ Audio compression: WAV oscillators, not loaded files

---

## Future Optimizations (Out of Scope)

- [ ] Virtual scrolling for long agent/task lists
- [ ] Service Worker caching (offline support)
- [ ] Image lazy loading (no images currently)
- [ ] WebP format for graphics (no raster images)
- [ ] Code splitting by route (already using lazy())
- [ ] Preload critical fonts
- [ ] Bundle size analysis (rollup-plugin-visualizer)

---

## Rollback Plan

If performance degrades after changes:
1. `git log --oneline` (find last good commit)
2. `git revert <commit-hash>` (revert specific change)
3. Measure with DevTools again
4. If better, commit the revert; if same, investigate further

---

## Notes for Operators

The system is optimized for **premium feel over raw performance**. Spring animations are slightly stiffer (350 vs typical 200-250) to give responsive, confident feedback. This trades 1-2ms render time for a better **perceived** performance.

For extreme low-end devices (2015 laptops, mid-range phones), disable:
- Bloom post-processing
- Particle effects
- Spring animations (use linear easing instead)
- Audio ambient soundscape

See "Low-End GPU" section above for settings.
