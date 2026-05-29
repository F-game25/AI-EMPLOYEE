# Phase 2 Testing & Verification Guide
## AI-EMPLOYEE System

### Overview
This guide covers the complete Phase 2 testing suite, including build verification, feature testing, regression testing, and security validation.

---

## 1. BUILD & SYNTAX VERIFICATION

### 1.1 Python Syntax Verification
```bash
# Check all Python files for syntax errors
python3 -m py_compile runtime/**/*.py

# Expected: No errors
# If errors: Fix syntax in reported files, re-run
```

### 1.2 Node.js Syntax Verification
```bash
# Check all JavaScript files for syntax errors
find backend -name "*.js" -type f | xargs -I {} node --check {}

# Expected: All files pass
# If errors: Fix syntax errors in reported files
```

### 1.3 Frontend Build Verification
```bash
cd frontend
npm run build

# Expected output:
# - Build completes without errors
# - dist/ directory created
# - HTML/CSS/JS bundles generated
# - Gzipped bundle < 500KB
```

### 1.4 Dependency Validation
```bash
# Ensure all dependencies installed
npm install
cd frontend && npm install

# Verify no missing imports
node -e "require('./backend/server.js'); console.log('✓ Backend imports OK')"
```

---

## 2. FEATURE TESTING CHECKLIST

### 2.1 Backend Startup (< 200ms non-blocking)
Test Requirements:
- [ ] Server starts without blocking main thread
- [ ] `system:ready` event broadcasts within 3s
- [ ] Git commits lazy-load on demand (not at startup)
- [ ] index.html cached in memory
- [ ] WebSocket messages staggered at 50ms intervals

Verification Steps:
```bash
# Start backend servers
bash start.sh

# Monitor logs
tail -f state/python-backend.log | grep -E "READINESS|Early broadcast|listening"

# Check timing
grep "listening on\|started" state/python-backend.log | head -1
```

### 2.2 Frontend Load (< 3-5s from idle)
Test Requirements:
- [ ] Page loads in < 5s (time to interactive)
- [ ] Central Cognitive Core visible immediately
- [ ] EventFeed populates with WebSocket events
- [ ] CommandDock shows live PC stats
- [ ] No console errors
- [ ] No white screen of death

Manual Testing:
1. Open browser: http://localhost:8787
2. Open Chrome DevTools (F12)
3. Go to Performance tab
4. Click record → reload page → wait for full load
5. Check timeline for:
   - First Contentful Paint < 2s
   - Largest Contentful Paint < 3s
   - Time to Interactive < 5s
6. Go to Console tab → verify no errors

### 2.3 Reactive Avatar (CentralCognitiveCore)
Test Requirements:
- [ ] 9-state machine: idle → thinking → executing → idle
- [ ] Avatar orbit speed correlates with CPU load (2-20s range)
- [ ] Particle count reacts to RAM usage (5-100)
- [ ] Color reflects threat level (cyan/gold/orange/red)
- [ ] Smooth GSAP transitions (no jarring snaps)
- [ ] FPS > 30 on laptop, > 50 on desktop

Manual Testing:
1. Load dashboard at http://localhost:8787
2. Open Chrome DevTools → Performance
3. Record 10 seconds of avatar animation
4. Check:
   - FPS counter shows green (>30)
   - No frame drops
   - Smooth orbit rotation
   - Particle system updates smoothly

### 2.4 Bottom Bar (CommandDock)
Test Requirements:
- [ ] Always visible at bottom (z-index 9999)
- [ ] Live stats: CPU%, GPU%, RAM, DISK%
- [ ] Color coded (green/gold/orange/red by threshold)
- [ ] Updates every 2-3s without flickering
- [ ] TALK button clickable
- [ ] Chat panel slides up smoothly
- [ ] CLOSE button works
- [ ] Chat panel slides down smoothly

Manual Testing:
1. Open dashboard
2. Scroll down to bottom → CommandDock visible
3. Verify stats display and update
4. Click TALK button → chat panel appears
5. Type message → send
6. Click CLOSE → panel disappears

### 2.5 Event Feed
Test Requirements:
- [ ] Shows 8 categories (cognition, task, agent, memory, economy, security, brain, infra)
- [ ] Auto-scrolls to newest events
- [ ] Pauses on hover
- [ ] Max 200 events (oldest fade and remove)
- [ ] Filter buttons work
- [ ] Events have 4px colored left border per category

Manual Testing:
1. Open dashboard
2. Locate EventFeed (left sidebar or right panel)
3. Verify event categories visible
4. Perform action (e.g., run task) → event appears in feed
5. Test filter buttons
6. Generate >200 events → verify old ones remove

### 2.6 Navigation & Pages
Test Requirements:
- [ ] Sidebar shows 20+ items across 5 groups
- [ ] Avatar mini-indicator pulsing at top
- [ ] Each sidebar item loads corresponding page
- [ ] OperationsPage: task kanban visible
- [ ] AgentsPage: agent grid visible
- [ ] MoneyModePage: revenue metrics visible
- [ ] SettingsPage: config panels visible

Manual Testing:
1. Open dashboard
2. Click each sidebar item
3. Verify page loads without errors
4. Check for expected content on each page

### 2.7 WebSocket Event Routing
Test Requirements:
- [ ] system:* events → systemStore
- [ ] cognitive:* events → cognitiveStore + avatar state
- [ ] agent:* events → agentStore
- [ ] task:* events → taskStore
- [ ] economy:* events → economyStore
- [ ] security:* events → securityStore
- [ ] memory:* + unknown → eventFeedStore

Verification:
```bash
# Monitor WebSocket traffic
# In Chrome DevTools → Network tab → WS filter

# Or check application state
# In Chrome DevTools → Console, run:
# console.log(useStore.getState())
```

### 2.8 Performance Metrics
Test Requirements:
- [ ] Bundle size: 1.5 MB (gzipped: 473 KB)
- [ ] Page load time: < 3s
- [ ] FPS consistency: no sudden drops
- [ ] Memory: < 150MB during normal use
- [ ] No layout thrashing
- [ ] No render storms

Verification Tools:
```bash
# Lighthouse audit
# Chrome DevTools → Lighthouse → Generate report

# Check bundle size
du -sh frontend/dist/
gzip -c frontend/dist/index.html | wc -c

# Monitor memory
# Chrome DevTools → Performance → Memory tab
```

---

## 3. REGRESSION TESTING

Verify backward compatibility with Phase 3:

### 3.1 API Endpoints
```bash
# Test critical endpoints
curl -X GET http://localhost:8787/api/status
curl -X POST http://localhost:8787/auth/login -d '{"email":"test@test.com","password":"test"}'
curl -X GET http://localhost:8787/api/agents
```

Expected: All return 200 or proper error codes (not 500)

### 3.2 Authentication Routes
- [ ] POST /auth/register → creates user, returns token
- [ ] POST /auth/login → returns JWT token
- [ ] POST /auth/refresh → rotates refresh token
- [ ] GET /api/profile (with auth header) → returns user profile

### 3.3 Chat Endpoint
- [ ] POST /api/chat → forwards to Python backend
- [ ] Returns LLM responses (or placeholder if backend down)
- [ ] Supports streaming responses

### 3.4 State Management
- [ ] appStore facade still works
- [ ] Old components still render
- [ ] Existing pages accessible

---

## 4. SECURITY VERIFICATION

### 4.1 JWT Token Handling
```bash
# Verify token rotation
curl -X POST http://localhost:8787/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"

# Verify token includes tenant_id
# Decode token at jwt.io and check payload
```

### 4.2 WebSocket Authentication
- [ ] WS connections require valid JWT
- [ ] Invalid tokens rejected
- [ ] Expired tokens handled

### 4.3 Rate Limiting
```bash
# Rapid fire requests to auth endpoint
for i in {1..20}; do curl -X POST http://localhost:8787/auth/login; done

# Expected: Requests after limit blocked (429 or similar)
```

### 4.4 CSP Headers
```bash
curl -I http://localhost:8787

# Verify Content-Security-Policy header present
```

### 4.5 Secrets Management
```bash
# Check logs for exposed secrets
grep -r "API_KEY\|SECRET\|PASSWORD" state/python-backend.log

# Expected: No output (no secrets logged)
```

### 4.6 Tenant Isolation
```bash
# Verify tenant data not leaked
# Login as tenant1 → verify access only to tenant1 data
# Login as tenant2 → verify access only to tenant2 data
# Verify tenant1 cannot access tenant2's deals/tasks/etc.
```

---

## 5. ERROR LOGGING

All errors logged to: `/tests/verification_errors.log`

Format:
```
TIMESTAMP | COMPONENT | ERROR_TYPE | MESSAGE | SEVERITY
2026-05-13 10:30:45 | Python | SYNTAX | runtime/agents/test.py line 42 | P0
2026-05-13 10:31:12 | Frontend | IMPORT | Missing module 'xyz' | P1
```

Severity Levels:
- **P0**: Blocks deployment (must fix)
- **P1**: Major issue (should fix before merge)
- **P2**: Minor issue (can fix in follow-up)
- **P3**: Cosmetic issue (low priority)

---

## 6. DEPLOYMENT READINESS CHECKLIST

Run before final deployment:

```bash
# Run automated verification
bash tests/phase2-verify.sh

# Expected output:
# ✓ PHASE 2 VERIFICATION PASSED
# System ready for feature testing and manual verification
```

Final Checklist:
- [ ] All files created/modified successfully
- [ ] No broken imports
- [ ] No syntax errors
- [ ] No console errors on load
- [ ] All features working
- [ ] Performance acceptable (< 5s load time)
- [ ] Security baseline met
- [ ] Regression tests passing
- [ ] No merge conflicts
- [ ] Git status clean or only expected changes

---

## 7. TESTING APPROACH SUMMARY

### Automated Testing
- **Syntax Checks**: Python, Node, imports
- **Build Verification**: Frontend build, bundle size
- **Deployment Readiness**: File existence, critical paths

### Manual Testing (Chrome DevTools)
- Feature functionality
- UI/UX experience
- Performance (Lighthouse, DevTools Profiler)
- WebSocket event routing
- Mobile responsiveness

### Performance Testing
- Lighthouse audit
- DevTools Performance tab
- Network tab for resource loading
- Memory profiler

### Security Testing
- OWASP checklist
- CSP validation
- Token rotation
- Rate limiting
- Tenant isolation

---

## 8. FAILURE HANDLING

### If P0 Errors Found
- **Action**: Stop deployment
- **Process**: 
  1. Document errors in verification_errors.log
  2. Fix issues
  3. Re-run phase2-verify.sh
  4. Verify fix with targeted test
  5. Proceed only when P0 errors = 0

### If P1 Errors Found
- **Action**: Document, plan follow-up
- **Process**:
  1. Log errors with severity P1
  2. Create tickets for follow-up
  3. Deploy with known P1 issues
  4. Fix in next sprint

### If P2/P3 Errors Found
- **Action**: Log, monitor
- **Process**:
  1. Log errors with severity P2/P3
  2. Continue with deployment
  3. Fix in future iterations

---

## 9. RUNNING THE VERIFICATION

Quick Start:
```bash
cd /home/lf/AI-EMPLOYEE

# Run automated verification
bash tests/phase2-verify.sh

# Review logs
cat tests/build_verification.log
cat tests/verification_errors.log
cat tests/verification_results.log
```

Manual Testing Checklist:
```bash
# Start system
npm start
# or
bash start.sh

# Open browser
# http://localhost:8787

# Test features (see sections 2.1-2.8)
# Document results in testing_checklist.log
```

---

## 10. DOCUMENTATION

All testing artifacts created:
- `tests/phase2-verify.sh` — Automated verification script
- `tests/PHASE2_TESTING_GUIDE.md` — This file
- `tests/build_verification.log` — Build test results
- `tests/verification_errors.log` — Errors found during testing
- `tests/verification_results.log` — Complete test results

