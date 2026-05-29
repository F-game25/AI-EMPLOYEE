# Phase 2 Feature Testing Checklist
## AI-EMPLOYEE System

Date: 2026-05-13
Tester: [Your Name]
Branch: wavefield-routing

---

## 1. BUILD & SYNTAX VERIFICATION

### Python Syntax Check
- [ ] All Python files in runtime/ compile without errors
  - Command: `python3 -m py_compile runtime/**/*.py`
  - Status: PASS / FAIL
  - Notes: _________________

### Node.js Syntax Check
- [ ] All JavaScript files in backend/ pass syntax check
  - Command: `find backend -name "*.js" -exec node --check {} \;`
  - Status: PASS / FAIL
  - Notes: _________________

### Frontend Build
- [ ] Build completes successfully
  - Command: `cd frontend && npm run build`
  - Status: PASS / FAIL
  - Duration: _____ seconds
  - Bundle size (uncompressed): _____ MB
  - Bundle size (gzipped): _____ KB
  - Notes: _________________

### Import Validation
- [ ] All imports resolve correctly
  - Node backend imports: PASS / FAIL
  - Frontend imports: PASS / FAIL
  - Python imports: PASS / FAIL
  - Notes: _________________

---

## 2. BACKEND STARTUP VERIFICATION

### Server Initialization (< 200ms non-blocking)
- [ ] Node.js server starts
  - Port: 8787
  - Startup time: _____ ms
  - Blocking: YES / NO
  - Notes: _________________

- [ ] Python FastAPI server starts
  - Port: 18790
  - Startup time: _____ ms
  - Blocking: YES / NO
  - Notes: _________________

### Event Broadcasting
- [ ] system:ready event broadcasts within 3 seconds
  - Time observed: _____ ms
  - Event visible in dashboard: YES / NO
  - Payload correct: YES / NO
  - Notes: _________________

### Resource Loading
- [ ] index.html cached in memory (zero disk I/O on 404)
  - Test: `curl http://localhost:8787/nonexistent.html`
  - Response time: < 10ms: YES / NO
  - Notes: _________________

- [ ] Git commits lazy-load on demand
  - Git accessed at startup: YES / NO
  - Git accessed on demand: YES / NO
  - Startup latency impact: minimal / significant
  - Notes: _________________

### WebSocket Staggering
- [ ] WS messages staggered at 50ms intervals
  - Test: Monitor WS messages in DevTools
  - Backpressure observed: YES / NO
  - Max message rate: _____ msg/sec
  - Notes: _________________

---

## 3. FRONTEND LOAD VERIFICATION

### Page Load Performance (< 3-5s)
- [ ] Page loads in < 5 seconds
  - Time to First Contentful Paint: _____ ms (target < 2s)
  - Time to Largest Contentful Paint: _____ ms (target < 3s)
  - Time to Interactive: _____ ms (target < 5s)
  - Tool: Chrome Lighthouse / DevTools
  - Notes: _________________

### Visual Elements
- [ ] Central Cognitive Core visible immediately
  - Visible within: _____ ms
  - Rendering correctly: YES / NO
  - Animations smooth: YES / NO
  - Notes: _________________

- [ ] EventFeed populates with WS events
  - Events visible: YES / NO
  - Update latency: _____ ms
  - Auto-scroll working: YES / NO
  - Notes: _________________

- [ ] CommandDock shows live PC stats
  - Visible at bottom: YES / NO
  - Stats updating: YES / NO
  - Color indicators working: YES / NO
  - Notes: _________________

### Console Verification
- [ ] No console errors on load
  - Error count: _____
  - Warning count: _____
  - Critical errors: NONE / LIST: _________________

- [ ] No console warnings (non-critical)
  - Deprecation warnings: NONE / COUNT: _____
  - Notes: _________________

### White Screen Test
- [ ] No white screen of death (WSOD)
  - UI elements render: YES / NO
  - Content visible: YES / NO
  - Responsive: YES / NO
  - Notes: _________________

---

## 4. REACTIVE AVATAR TESTING

### CentralCognitiveCore States
- [ ] Avatar cycles through all 9 states correctly
  - idle → thinking → executing → idle: WORKS / FAILS
  - State transitions smooth: YES / NO
  - State duration appropriate: YES / NO
  - Notes: _________________

### CPU Load Correlation
- [ ] Avatar orbit speed correlates with CPU load
  - CPU 10% → orbit period: _____ seconds (expect: ~20s)
  - CPU 50% → orbit period: _____ seconds (expect: ~10s)
  - CPU 90% → orbit period: _____ seconds (expect: ~2s)
  - Linear correlation: YES / NO
  - Notes: _________________

### RAM Usage Reaction
- [ ] Particle count reacts to RAM usage
  - RAM 10% → particles: _____ (expect: ~5-10)
  - RAM 50% → particles: _____ (expect: ~30-50)
  - RAM 90% → particles: _____ (expect: ~90-100)
  - Linear correlation: YES / NO
  - Notes: _________________

### Threat Level Color
- [ ] Avatar color reflects threat level
  - Safe (low threat) → cyan: YES / NO
  - Caution (medium threat) → gold: YES / NO
  - Warning (high threat) → orange: YES / NO
  - Critical (extreme threat) → red: YES / NO
  - Notes: _________________

### Animation Quality
- [ ] GSAP transitions smooth (no jarring snaps)
  - Transitions smooth: YES / NO
  - No visible glitches: YES / NO
  - Performance cost acceptable: YES / NO
  - Notes: _________________

### Frame Rate
- [ ] FPS > 30 on laptop
  - Average FPS: _____ (target > 30)
  - Minimum FPS: _____ (should not drop below 20)
  - Notes: _________________

- [ ] FPS > 50 on desktop
  - Average FPS: _____ (target > 50)
  - Minimum FPS: _____ (should not drop below 30)
  - Notes: _________________

---

## 5. COMMANDDOCK VERIFICATION

### Positioning & Visibility
- [ ] Always visible at bottom
  - Z-index correct: YES / NO
  - Position fixed: YES / NO
  - Not hidden behind content: YES / NO
  - Notes: _________________

- [ ] Z-index 9999 (always on top)
  - Visible over other elements: YES / NO
  - Not covered by modals: YES / NO
  - Notes: _________________

### Live Statistics Display
- [ ] Shows CPU usage %
  - Format correct: _____ % (e.g., "45%")
  - Value accurate: YES / NO
  - Updates regularly: YES / NO
  - Notes: _________________

- [ ] Shows CPU temperature °C
  - Format correct: _____ °C
  - Value accurate: YES / NO
  - Units correct: YES / NO
  - Notes: _________________

- [ ] Shows GPU usage %
  - Format correct: _____ %
  - Value accurate: YES / NO
  - Notes: _________________

- [ ] Shows GPU temperature °C
  - Format correct: _____ °C
  - Value accurate: YES / NO
  - Notes: _________________

- [ ] Shows RAM usage GB
  - Format correct: _____ GB / _____ GB total
  - Value accurate: YES / NO
  - Notes: _________________

- [ ] Shows DISK usage %
  - Format correct: _____ %
  - Value accurate: YES / NO
  - Notes: _________________

### Color Coding
- [ ] Green: < 50% usage
  - Color correct: YES / NO
  - Threshold accurate: YES / NO
  - Notes: _________________

- [ ] Gold: 50-80% usage
  - Color correct: YES / NO
  - Threshold accurate: YES / NO
  - Notes: _________________

- [ ] Orange: 80-95% usage
  - Color correct: YES / NO
  - Threshold accurate: YES / NO
  - Notes: _________________

- [ ] Red: > 95% usage
  - Color correct: YES / NO
  - Threshold accurate: YES / NO
  - Notes: _________________

### Update Frequency
- [ ] Updates every 2-3 seconds
  - Actual interval: _____ seconds
  - Consistent: YES / NO
  - No flickering: YES / NO
  - Notes: _________________

### TALK Button
- [ ] Button clickable
  - Responds to click: YES / NO
  - Visual feedback: YES / NO
  - Notes: _________________

- [ ] Chat panel slides up smoothly
  - Animation smooth: YES / NO
  - Duration: _____ ms (expect: ~300ms)
  - Notes: _________________

### Chat Panel
- [ ] Can type message
  - Input field active: YES / NO
  - Text input works: YES / NO
  - Notes: _________________

- [ ] Can send message
  - Send button visible: YES / NO
  - Message sent to backend: YES / NO
  - Response received: YES / NO
  - Notes: _________________

### CLOSE Button
- [ ] Button clickable
  - Responds to click: YES / NO
  - Notes: _________________

- [ ] Chat panel slides down smoothly
  - Animation smooth: YES / NO
  - Duration: _____ ms (expect: ~300ms)
  - Notes: _________________

---

## 6. EVENT FEED VERIFICATION

### Category Display
- [ ] All 8 categories visible:
  - [ ] Cognition events (purple border)
  - [ ] Task events (blue border)
  - [ ] Agent events (green border)
  - [ ] Memory events (yellow border)
  - [ ] Economy events (red border)
  - [ ] Security events (orange border)
  - [ ] Brain events (cyan border)
  - [ ] Infrastructure events (gray border)

### Event List Behavior
- [ ] Auto-scrolls to newest events
  - New events visible: YES / NO
  - Scroll smooth: YES / NO
  - Notes: _________________

- [ ] Pauses on hover
  - Auto-scroll stops: YES / NO
  - Resumes on unhover: YES / NO
  - Notes: _________________

- [ ] Max 200 events enforced
  - Event count at capacity: _____ (should be 200)
  - Old events fade/remove: YES / NO
  - Notes: _________________

### Filter Buttons
- [ ] All filters work correctly
  - Cognition filter: WORKS / FAILS
  - Task filter: WORKS / FAILS
  - Agent filter: WORKS / FAILS
  - Memory filter: WORKS / FAILS
  - Economy filter: WORKS / FAILS
  - Security filter: WORKS / FAILS
  - Brain filter: WORKS / FAILS
  - Infra filter: WORKS / FAILS
  - All/Clear filters: WORKS / FAILS
  - Notes: _________________

### Styling
- [ ] 4px colored left border per category
  - Border visible: YES / NO
  - Border color matches category: YES / NO
  - Border width: _____ px (should be 4)
  - Notes: _________________

---

## 7. NAVIGATION & PAGES

### Sidebar
- [ ] Shows 20+ items
  - Total items: _____
  - Items visible: YES / NO
  - Scrollable if needed: YES / NO
  - Notes: _________________

- [ ] Organized in 5 groups
  - Group 1: _________________
  - Group 2: _________________
  - Group 3: _________________
  - Group 4: _________________
  - Group 5: _________________

### Avatar Mini-Indicator
- [ ] Pulsing at top of sidebar
  - Visible: YES / NO
  - Pulsing animation: YES / NO
  - Reflects avatar state: YES / NO
  - Notes: _________________

### Page Loading
- [ ] Each sidebar item loads corresponding page
  - Dashboard: LOADS / FAILS
  - Operations: LOADS / FAILS
  - Agents: LOADS / FAILS
  - MoneyMode: LOADS / FAILS
  - Brain: LOADS / FAILS
  - Settings: LOADS / FAILS
  - Other items: LOADS / FAILS
  - Notes: _________________

### OperationsPage
- [ ] Task kanban visible
  - Columns visible: YES / NO
  - Tasks display: YES / NO
  - Drag & drop: WORKS / FAILS
  - Notes: _________________

### AgentsPage
- [ ] Agent grid visible
  - Grid layout: YES / NO
  - Agent cards display: YES / NO
  - Agent count: _____
  - Notes: _________________

### MoneyModePage
- [ ] Revenue metrics visible
  - Revenue chart: VISIBLE / HIDDEN
  - Metrics table: VISIBLE / HIDDEN
  - Numbers accurate: YES / NO
  - Notes: _________________

### SettingsPage
- [ ] Config panels visible
  - Settings form: VISIBLE / HIDDEN
  - All settings: VISIBLE / HIDDEN
  - Save works: YES / NO
  - Notes: _________________

---

## 8. WEBSOCKET EVENT ROUTING

### System Events
- [ ] system:* events route to systemStore
  - system:ready captured: YES / NO
  - system:status captured: YES / NO
  - Notes: _________________

### Cognitive Events
- [ ] cognitive:* events route to cognitiveStore
  - Events captured: YES / NO
  - Avatar state updated: YES / NO
  - Notes: _________________

### Agent Events
- [ ] agent:* events route to agentStore
  - Events captured: YES / NO
  - Agent count updated: YES / NO
  - Notes: _________________

### Task Events
- [ ] task:* events route to taskStore
  - Events captured: YES / NO
  - Task list updated: YES / NO
  - Notes: _________________

### Economy Events
- [ ] economy:* events route to economyStore
  - Events captured: YES / NO
  - Revenue updated: YES / NO
  - Notes: _________________

### Security Events
- [ ] security:* events route to securityStore
  - Events captured: YES / NO
  - Threat level updated: YES / NO
  - Notes: _________________

### Memory Events
- [ ] memory:* events route to eventFeedStore
  - Events visible in feed: YES / NO
  - Notes: _________________

### Unknown Events
- [ ] Unknown events route to eventFeedStore
  - Fallback working: YES / NO
  - Events logged: YES / NO
  - Notes: _________________

### Console Verification
- [ ] No console errors from routing
  - Errors: NONE / COUNT: _____
  - Notes: _________________

---

## 9. PERFORMANCE METRICS

### Bundle Size
- [ ] Total bundle < 1.5 MB
  - Uncompressed size: _____ MB
  - Status: PASS / FAIL
  - Notes: _________________

- [ ] Gzipped bundle < 500 KB
  - Gzipped size: _____ KB
  - Status: PASS / FAIL
  - Notes: _________________

### Page Load Performance
- [ ] Load time < 3 seconds
  - Measured load time: _____ seconds
  - Status: PASS / FAIL
  - Tool: _________________
  - Notes: _________________

### Frame Rate Consistency
- [ ] No sudden FPS drops
  - Minimum FPS: _____ (should stay stable)
  - Average FPS: _____
  - Drops detected: YES / NO
  - Notes: _________________

### Memory Usage
- [ ] < 150 MB during normal use
  - Initial memory: _____ MB
  - Peak memory: _____ MB
  - Final memory: _____ MB
  - Status: PASS / FAIL
  - Notes: _________________

### Layout Thrashing
- [ ] No layout thrashing detected
  - Chrome DevTools warnings: NONE / COUNT: _____
  - Symptoms: NONE / DESCRIBE: _________________

### Render Performance
- [ ] No render storms
  - DevTools "paint" warnings: NONE / COUNT: _____
  - High frequency repaints: YES / NO
  - Notes: _________________

---

## 10. REGRESSION TESTING

### API Endpoints
- [ ] GET /api/status → 200
  - Response time: _____ ms
  - Data structure: CORRECT / BROKEN
  - Notes: _________________

- [ ] POST /auth/login → 200/401
  - Accepts credentials: YES / NO
  - Returns token: YES / NO
  - Notes: _________________

- [ ] GET /api/agents → 200
  - Returns agent list: YES / NO
  - Data structure: CORRECT / BROKEN
  - Notes: _________________

- [ ] POST /api/chat → forwards to Python backend
  - Request forwarded: YES / NO
  - Response received: YES / NO
  - Notes: _________________

### Authentication
- [ ] POST /auth/register creates user
  - User created: YES / NO
  - Token issued: YES / NO
  - Notes: _________________

- [ ] JWT tokens work
  - Token format valid: YES / NO
  - Token accepted by API: YES / NO
  - Notes: _________________

- [ ] Token refresh works
  - Old token rotates: YES / NO
  - New token issued: YES / NO
  - Notes: _________________

### State Management
- [ ] appStore facade works
  - State accessible: YES / NO
  - State updates propagate: YES / NO
  - Notes: _________________

- [ ] Old components render
  - Dashboard: RENDERS / BREAKS
  - Sidebar: RENDERS / BREAKS
  - Pages: RENDER / BREAK
  - Notes: _________________

---

## 11. SECURITY VERIFICATION

### JWT Token Handling
- [ ] Tokens rotate on refresh
  - Old token discarded: YES / NO
  - New token issued: YES / NO
  - Refresh token rotated: YES / NO
  - Notes: _________________

- [ ] Token includes tenant_id
  - Claim present: YES / NO
  - Value correct: YES / NO
  - Notes: _________________

### WebSocket Security
- [ ] WS connections require auth
  - Unauthenticated connection rejected: YES / NO
  - Invalid token rejected: YES / NO
  - Notes: _________________

### Rate Limiting
- [ ] Blocks excess requests
  - Test: Rapid fire 20 requests
  - Requests blocked after: _____ requests
  - Response: 429 / OTHER: _____
  - Notes: _________________

### CSP Headers
- [ ] Content-Security-Policy present
  - Header present: YES / NO
  - Policy strict: YES / NO
  - Notes: _________________

### Secrets Management
- [ ] No secrets in logs
  - API_KEY exposed: YES / NO
  - PASSWORD exposed: YES / NO
  - TOKEN exposed: YES / NO
  - Notes: _________________

### Tenant Isolation
- [ ] Data not leaked between tenants
  - Tenant1 data isolated: YES / NO
  - Tenant2 data isolated: YES / NO
  - Cross-tenant access denied: YES / NO
  - Notes: _________________

---

## 12. DEPLOYMENT READINESS

### Code Quality
- [ ] No syntax errors
  - Python: PASS / FAIL
  - Node.js: PASS / FAIL
  - JSX: PASS / FAIL
  - Notes: _________________

- [ ] No broken imports
  - Frontend: PASS / FAIL
  - Backend: PASS / FAIL
  - Python: PASS / FAIL
  - Notes: _________________

### Functionality
- [ ] All features working
  - Core features: WORKING / BROKEN
  - Secondary features: WORKING / BROKEN
  - Notes: _________________

- [ ] No console errors on load
  - Error count: _____
  - Critical errors: NONE / PRESENT
  - Notes: _________________

### Performance
- [ ] Performance acceptable
  - Load time: _____ seconds (target < 5)
  - FPS: _____ (target > 30)
  - Bundle size: _____ KB (target < 500)
  - Notes: _________________

### Security
- [ ] Security baseline met
  - Auth working: YES / NO
  - Rate limiting: YES / NO
  - Tenant isolation: YES / NO
  - CSP headers: YES / NO
  - Notes: _________________

### Version Control
- [ ] No merge conflicts
  - Conflicts: NONE / COUNT: _____
  - Notes: _________________

- [ ] Git status clean
  - Untracked files: _____
  - Modified files: _____
  - Notes: _________________

---

## SUMMARY

### Overall Status
- **Build Status**: PASS / FAIL
- **Feature Status**: PASS / FAIL
- **Regression Status**: PASS / FAIL
- **Security Status**: PASS / FAIL
- **Performance Status**: PASS / FAIL
- **Deployment Readiness**: READY / NOT READY

### Critical Issues Found
1. _________________
2. _________________
3. _________________

### Action Items
- [ ] Fix P0 issues before deployment
- [ ] Schedule follow-up for P1 issues
- [ ] Monitor P2/P3 issues

### Sign-off

**Tester Name**: _________________ 
**Date**: 2026-05-13
**Approved**: YES / NO
**Notes**: _________________________________________________

