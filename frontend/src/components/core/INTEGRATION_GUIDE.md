# Central Cognitive Core — Integration Guide

This guide walks through integrating the CentralCognitiveCore component into the dashboard.

## Quick Start (5 minutes)

### 1. Import the Component

In your main dashboard or layout file:

```jsx
import CentralCognitiveCore from './components/core/CentralCognitiveCore';
```

### 2. Add to Your Layout

The component needs a container with specific dimensions. Add to your JSX:

```jsx
<div className="dashboard-layout">
  {/* ... other components ... */}
  
  <div className="cognitive-core-container">
    <CentralCognitiveCore />
  </div>

  {/* ... rest of layout ... */}
</div>
```

### 3. Style the Container

Add CSS to your stylesheet:

```css
.cognitive-core-container {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 600px;
  height: 600px;
  z-index: 5;
  pointer-events: none; /* Let interactions pass through */
}

@media (max-width: 1024px) {
  .cognitive-core-container {
    width: 500px;
    height: 500px;
  }
}

@media (max-width: 768px) {
  .cognitive-core-container {
    width: 400px;
    height: 400px;
  }
}
```

### 4. Verify Store Integration

The component requires these Zustand stores to be properly initialized:

```javascript
// frontend/src/store/cognitiveStore.js
import { useCognitiveStore } from '../store/cognitiveStore';

// frontend/src/store/systemStore.js
import { useSystemStore } from '../store/systemStore';

// frontend/src/store/securityStore.js
import { useSecurityStore } from '../store/securityStore';

// frontend/src/store/taskStore.js
import { useTaskStore } from '../store/taskStore';
```

All stores already exist and are properly configured. No changes needed.

## Detailed Integration Steps

### Step 1: Verify Dependencies

Ensure these npm packages are installed:

```bash
npm list gsap zustand react-three-fiber three @react-three/drei
```

All should be present. If not, install:

```bash
npm install gsap zustand react-three-fiber three @react-three/drei
```

### Step 2: Choose Placement

The CentralCognitiveCore is typically placed in one of these locations:

**Option A: Centered overlay in dashboard**
```jsx
<div className="dashboard-container">
  <Sidebar />
  <MainContent />
  <CentralCognitiveCore />  {/* Overlays all content */}
</div>
```

**Option B: Dedicated section with panels around it**
```jsx
<div className="dashboard-grid">
  <LeftPanels />
  <CentralCognitiveCore />   {/* Centered */}
  <RightPanels />
</div>
```

**Option C: Part of a 3D viewport**
```jsx
<Canvas>
  <OrbitControls />
  <CentralCognitiveCore />   {/* Integrated into 3D space */}
</Canvas>
```

### Step 3: Wire Up Store Updates

The component automatically subscribes to all stores. Verify data flows:

```javascript
// In your app initialization or boot sequence:

// 1. System metrics flow
setSystemStatus({
  cpu_usage: cpuLoad,
  memory: ramUsage,
  // ...
});

// 2. Security status flows
setSecurityStatus({
  threat_score: threatScore,
  mode: threatMode,
  // ...
});

// 3. Cognitive events flow
appendReasoningStep({ tool: 'web_search', ... });
recordModelCall({ ... });

// 4. Task updates flow
upsertWorkflowRun({ run_id: 'task-123', ... });
addChatMessage({ role: 'ai', content: '...', ... });
```

All of these should already be in place in your WebSocket message handlers.

### Step 4: Test State Transitions

Manually trigger state transitions using React DevTools:

```javascript
// In browser console:

// Force state transitions for testing
const { useCognitiveStore } = window.zustandStores;

// Test THINKING
useCognitiveStore.getState().appendReasoningStep({
  phase: 'reasoning',
  tool: 'web_search'
});

// Test EXECUTING
useCognitiveStore.getState().setAvatarState('executing');

// Test WARNING
useSecurityStore.getState().setSecurityStatus({
  mode: 'CRITICAL',
  threat_score: 90
});

// Test ERROR
useSystemStore.getState().setError('Test error');
```

### Step 5: Performance Testing

Monitor performance in Chrome DevTools:

```javascript
// Measure render time
console.time('CognitiveCoreRender');
// ... component render ...
console.timeEnd('CognitiveCoreRender');

// Check FPS
// DevTools → Performance → Record → interact with avatar
// Look for 60+ FPS, <16ms per frame
```

### Step 6: Responsive Testing

Test on different breakpoints:

```bash
# Mobile (480px): Badges hidden, state indicator only
# Tablet (768px): Reduced scale, lower opacity
# Desktop (1024px+): Full visual fidelity
```

## Dashboard Integration Examples

### Example 1: Full-Screen Overlay

```jsx
// frontend/src/components/Dashboard.jsx

import CentralCognitiveCore from './core/CentralCognitiveCore';

export const Dashboard = () => {
  return (
    <div className="dashboard">
      <Sidebar />
      <MainContentArea />
      
      <div className="cognitive-core-overlay">
        <CentralCognitiveCore />
      </div>
    </div>
  );
};

// CSS
const styles = `
  .dashboard {
    position: relative;
    width: 100%;
    height: 100vh;
    display: flex;
  }

  .cognitive-core-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 15;
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }
`;
```

### Example 2: Split Layout

```jsx
// frontend/src/components/DashboardLayout.jsx

import CentralCognitiveCore from './core/CentralCognitiveCore';

export const DashboardLayout = () => {
  return (
    <div className="dashboard-split">
      <div className="left-panel">
        <OperationsPanel />
      </div>

      <div className="center-core">
        <CentralCognitiveCore />
      </div>

      <div className="right-panel">
        <MetricsPanel />
      </div>
    </div>
  );
};

// CSS
const styles = `
  .dashboard-split {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    height: 100vh;
    gap: 1rem;
  }

  .center-core {
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
`;
```

### Example 3: Floating Widget

```jsx
// frontend/src/components/WidgetDashboard.jsx

import CentralCognitiveCore from './core/CentralCognitiveCore';

export const WidgetDashboard = () => {
  const [position, setPosition] = useState({ x: 0, y: 0 });

  return (
    <div className="widget-container">
      <div
        className="floating-widget"
        style={{
          transform: `translate(${position.x}px, ${position.y}px)`
        }}
      >
        <CentralCognitiveCore />
      </div>

      <div className="widgets-grid">
        {/* Your widgets here */}
      </div>
    </div>
  );
};

// CSS
const styles = `
  .floating-widget {
    position: fixed;
    width: 400px;
    height: 400px;
    bottom: 20px;
    right: 20px;
    z-index: 50;
    background: rgba(7, 8, 16, 0.8);
    border: 1px solid rgba(60, 231, 255, 0.3);
    border-radius: 12px;
    backdrop-filter: blur(10px);
    box-shadow: 0 0 40px rgba(60, 231, 255, 0.1);
  }
`;
```

## Store Integration Checklist

Before deploying, verify all store integrations:

### useCognitiveStore
- [ ] `avatarState` updates from business logic
- [ ] `reasoningSteps` appended during reasoning phases
- [ ] `modelCalls` tracked for queue depth visualization
- [ ] `brainActivity` updated with insights

### useSystemStore
- [ ] `wsConnected` updates on connection changes
- [ ] `systemStatus` updates with CPU/memory metrics
- [ ] `appState` reflects boot/ready/error states
- [ ] Heartbeat logs flowing correctly

### useSecurityStore
- [ ] `securityStatus` updates threat level
- [ ] `threat_score` ranges 0-100
- [ ] Mode correctly set: NORMAL/ALERT/CRITICAL/LOCKDOWN

### useTaskStore
- [ ] `workflowState.active_run` updates with task IDs
- [ ] `chatMessages` array growing with interactions
- [ ] Execution steps tracked for reasoning display

## Debugging Guide

### Avatar stuck in IDLE
**Symptom**: Avatar never changes state even with active tasks
**Check**:
1. Verify WebSocket connection in DevTools Network tab
2. Check store subscriptions: `useCognitiveStore.getState()`
3. Verify `computeState()` trigger conditions
4. Check browser console for errors

### Particles not rendering
**Symptom**: Rings visible but no particles around core
**Check**:
1. Verify `particleCount > 0` in state config
2. Check DOM: inspect `.particles-system` div
3. Verify CSS z-index isn't buried (should be 5)
4. Check particle opacity settings

### Rings not rotating
**Symptom**: Static rings with no animation
**Check**:
1. Verify GSAP animations applied: DevTools → Elements → styles
2. Check `--orbit-speed` CSS variable is set
3. Verify `animation: orbit` is in CSS
4. Check browser prefers-reduced-motion setting

### Performance degradation
**Symptom**: Frame rate drops when avatar active
**Check**:
1. Cap particle count: should be <100
2. Profile in DevTools Performance tab
3. Check for layout thrashing in rings/badges
4. Verify no re-renders on every metric update

## Network & Data Flow

```
WebSocket Message
       ↓
System State Update (useSystemStore.setSystemStatus)
       ↓
CentralCognitiveCore Subscription Triggered
       ↓
Triggers Computed (CPU, memory, queue depth, threat)
       ↓
State Machine Logic (computeState)
       ↓
Avatar State Derived
       ↓
CSS Variables Updated (element.style.setProperty)
       ↓
Animations Morph (GSAP.to)
       ↓
Visual Feedback to User
```

## Accessibility Testing

Ensure the component respects accessibility preferences:

```javascript
// Test prefers-reduced-motion
// DevTools → Rendering → Emulate CSS media feature prefers-reduced-motion

// Expected: Animations disabled, static state display

// Test prefers-contrast
// DevTools → Rendering → Emulate CSS media feature prefers-contrast: more

// Expected: Thicker borders, higher opacity, better visibility
```

## Production Deployment Checklist

- [ ] Component builds without errors: `npm run build`
- [ ] All store subscriptions connected
- [ ] Performance profiled on target devices
- [ ] Mobile responsiveness verified
- [ ] Accessibility compliance checked (WCAG AA)
- [ ] Error states tested (WebSocket down, errors in stores)
- [ ] state transitions smooth and responsive
- [ ] No memory leaks in long-running sessions
- [ ] Browser DevTools console clean (no errors/warnings)
- [ ] QA sign-off on visual design and functionality

## Support & Troubleshooting

If issues arise:

1. Check browser console for errors
2. Verify store subscriptions active: DevTools → React DevTools
3. Check network tab for WebSocket messages
4. Profile performance: DevTools → Performance
5. Inspect elements: DevTools → Elements → Computed Styles
6. Check animation state: DevTools → Animation Inspector

## Next Steps

After integration:

1. Monitor performance in production
2. Collect user feedback on visual design
3. Tune state thresholds based on real data
4. Consider enhancements (physics particles, gestures, etc.)
5. Plan Phase 2 improvements

---

**Integration Date**: 2026-05-12  
**Status**: Ready for Production  
**Support**: Contact UI Designer Agent
