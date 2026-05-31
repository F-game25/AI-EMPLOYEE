# Phase 2 Testing & Verification Framework
## AI-EMPLOYEE System

**Status**: Ready for Execution
**Created**: 2026-05-13
**Branch**: wavefield-routing

---

## Overview

Phase 2 implements comprehensive testing infrastructure for the AI-EMPLOYEE system, covering build verification, feature testing, regression testing, security validation, and performance monitoring.

All test artifacts are located in `/home/lf/AI-EMPLOYEE/tests/`

---

## Test Artifacts

### 1. Automated Verification Script
**File**: `phase2-verify.sh`

Automated testing tool covering:
- Python syntax validation (all runtime/*.py files)
- Node.js syntax validation (all backend/*.js files)
- Frontend build verification
- Import resolution checks
- Backward compatibility verification
- Security baseline validation
- Deployment readiness scoring

**Usage**:
```bash
bash tests/phase2-verify.sh
```

**Output**:
- `build_verification.log` — Build test results
- `verification_errors.log` — Errors found (with severity)
- `verification_results.log` — Complete test output

**Execution Time**: ~5 minutes

---

### 2. Testing Guide (Detailed)
**File**: `PHASE2_TESTING_GUIDE.md`

Comprehensive guide covering:
- Build & syntax verification procedures
- Feature testing requirements and manual tests
- Regression testing checklist
- Security verification procedures
- Performance testing methodology
- Error logging format
- Deployment readiness checklist

**Sections**:
1. Build & Syntax Verification (Python, Node, frontend)
2. Feature Testing Checklist (50+ items)
3. Regression Testing (API, auth, state, components)
4. Security Verification (JWT, WebSocket, rate limiting, CSP, secrets, tenancy)
5. Error Logging (format, severity levels)
6. Deployment Readiness (6-8 item checklist)
7. Testing Approach Summary

**Read Time**: 30 minutes

---

### 3. Feature Testing Checklist (Manual)
**File**: `FEATURE_TESTING_CHECKLIST.md`

Detailed manual testing checklist with 100+ items:
- Build & Syntax Verification
- Backend Startup Verification
- Frontend Load Verification
- Reactive Avatar Testing (9-state machine)
- CommandDock Verification (stats display)
- Event Feed Verification (8 categories)
- Navigation & Pages (20+ sidebar items)
- WebSocket Event Routing
- Performance Metrics
- Regression Testing
- Security Verification
- Deployment Readiness

Features:
- Checkbox for each test item
- Expected values and thresholds
- Notes fields for documentation
- Pass/fail tracking
- Sign-off section

**Use During**: Browser-based manual testing
**Duration**: 2-3 hours (depends on thoroughness)

---

### 4. Deployment Readiness Report
**File**: `DEPLOYMENT_READINESS_REPORT.md`

Strategic deployment assessment including:
- Executive summary
- Testing infrastructure overview
- Pre-deployment verification checklist
- Go/no-go criteria
- Estimated testing timeline
- Handoff to Phase 3
- Error handling procedures
- Testing environment setup
- Monitoring & observability
- Appendix with file locations

**Key Sections**:
- Testing infrastructure created (4 artifacts)
- Pre-deployment checklist (code quality, architecture, features, performance, security, testing, regression)
- Go/no-go criteria (blocking conditions, approval gates)
- Testing execution plan (Phase 2A-2E with time estimates)
- Deployment readiness scoring

**Read Time**: 20 minutes
**Reference During**: Deployment coordination

---

### 5. Error Tracking Template
**File**: `ERROR_TRACKING_TEMPLATE.md`

Error documentation and resolution procedures:
- Error log format and fields
- Severity levels (P0-P3) with definitions
- Error template for consistent documentation
- Common errors with resolutions
- Investigation checklist
- Resolution workflow
- Escalation procedures
- Error statistics tracking
- Tools for error diagnosis
- Communication template
- Sign-off template

**Use When**: Errors found during testing
**Reference For**: Tracking and resolving issues

---

### 6. Quick Start Testing Guide
**File**: `QUICK_START_TESTING.md`

Fast-track testing guide for quick validation:
- 5-minute quick start
- 30-minute testing sprint
- 2-hour thorough testing plan
- Common issues & quick fixes
- Test result logging template
- Pass/fail criteria
- Help commands
- Next steps after testing
- Time estimates

**Duration**: 30 minutes to 2 hours (flexible)
**Use When**: Quick validation needed before deeper testing

---

## Testing Workflow

### STEP 1: Quick Validation (15 minutes)
```bash
cd /home/lf/AI-EMPLOYEE

# Run automated checks
bash tests/phase2-verify.sh

# Review results
cat tests/verification_results.log
cat tests/verification_errors.log
```

**Go/No-Go Decision**: 
- If readiness_score ≥ 6/8 and no P0 errors → continue
- If P0 errors found → fix them first

---

### STEP 2: Start System (5 minutes)
```bash
# Start servers
npm start

# Wait for ready signal
sleep 10
grep "listening\|READY" state/python-backend.log | head -3
```

---

### STEP 3: Manual Feature Testing (2-3 hours)
```bash
# Open browser: http://localhost:8787
# Open DevTools: F12
# Follow FEATURE_TESTING_CHECKLIST.md
# Test each section and mark checkboxes
```

**Key Areas**:
- Frontend load performance (< 5s)
- Avatar animation (smooth, 30+ FPS)
- CommandDock stats display
- Event feed population
- WebSocket event routing
- Navigation functionality

---

### STEP 4: Performance Validation (1 hour)
```bash
# Chrome DevTools → Lighthouse
# Run audit on http://localhost:8787
# Check: FCP < 2s, LCP < 3s, TTI < 5s

# Check bundle size
du -sh frontend/dist/
gzip -c frontend/dist/index.html | wc -c

# Check FPS
# DevTools → Performance → Record 10s → check frame rate
```

---

### STEP 5: Security Verification (1 hour)
```bash
# Test JWT rotation
curl -X POST http://localhost:8787/auth/refresh

# Test rate limiting
for i in {1..20}; do curl -X POST http://localhost:8787/auth/login; done

# Check CSP headers
curl -I http://localhost:8787 | grep -i content-security

# Check for secrets in logs
grep -i "api_key\|password\|secret" state/python-backend.log
```

---

### STEP 6: Regression Testing (1 hour)
```bash
# Test API endpoints
curl http://localhost:8787/api/status
curl http://localhost:8787/api/agents

# Test auth routes
curl -X POST http://localhost:8787/auth/login

# Test chat forwarding
curl -X POST http://localhost:8787/api/chat -d '{"message":"test"}'

# Verify old components render (in browser)
```

---

### STEP 7: Documentation & Sign-Off (30 minutes)
```bash
# Create test results document
cat > tests/test_results_$(date +%Y%m%d).md << 'EOF'
# Test Results — $(date)

## Build Status
- Syntax: PASS / FAIL
- Build: PASS / FAIL

## Feature Testing
- Frontend: PASS / FAIL
- Avatar: PASS / FAIL
- CommandDock: PASS / FAIL
- Events: PASS / FAIL

## Performance
- Load time: [measurement]
- FPS: [measurement]
- Bundle: [measurement]

## Security
- Auth: PASS / FAIL
- Rate limiting: PASS / FAIL
- Secrets: PASS / FAIL
- CSP: PASS / FAIL

## Overall Status: [GO | NO-GO]
EOF

# Review all logs
cat tests/verification_errors.log
cat tests/verification_results.log
```

---

## Estimated Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 2A: Automated Verification | 15 min | Ready |
| Phase 2B: Manual Feature Testing | 2-3 hours | Ready |
| Phase 2C: Performance Validation | 1 hour | Ready |
| Phase 2D: Security Verification | 1 hour | Ready |
| Phase 2E: Regression Testing | 1 hour | Ready |
| Phase 2F: Documentation | 30 min | Ready |
| **TOTAL** | **6-7 hours** | **Ready** |

---

## Success Criteria

### Automated Verification
- [ ] 0 Python syntax errors
- [ ] 0 Node.js syntax errors
- [ ] Frontend builds successfully
- [ ] Readiness score ≥ 6/8
- [ ] 0 P0 errors logged

### Manual Testing
- [ ] Page loads < 5 seconds
- [ ] Avatar renders and animates smoothly
- [ ] CommandDock displays all stats
- [ ] EventFeed shows events
- [ ] WebSocket events route correctly
- [ ] No console errors
- [ ] All navigation items work

### Performance
- [ ] FCP < 2 seconds
- [ ] LCP < 3 seconds
- [ ] TTI < 5 seconds
- [ ] Bundle size (gzipped) < 500 KB
- [ ] FPS > 30 on laptop, > 50 on desktop

### Security
- [ ] JWT tokens rotate on refresh
- [ ] WebSocket requires auth
- [ ] Rate limiting blocks excess requests
- [ ] CSP headers present
- [ ] No secrets in logs
- [ ] Tenant data isolated

### Regression
- [ ] All API endpoints respond
- [ ] Auth routes work
- [ ] Chat forwarding works
- [ ] Old components render
- [ ] State management intact

---

## Go/No-Go Decision

### GO (Proceed to Phase 3)
If ALL of the following are true:
- [ ] Automated verification passes (readiness ≥ 6/8)
- [ ] 0 P0 errors
- [ ] Manual feature testing passes (all major items checked)
- [ ] Performance baseline met
- [ ] Security baseline met
- [ ] Regression tests passing
- [ ] No merge conflicts

### NO-GO (Block deployment)
If ANY of the following are true:
- [ ] P0 errors found
- [ ] Syntax errors present
- [ ] Frontend build fails
- [ ] Page load > 5 seconds
- [ ] Avatar not rendering
- [ ] CommandDock broken
- [ ] Critical console errors
- [ ] Auth broken
- [ ] WebSocket not connecting
- [ ] Merge conflicts present

### CONDITIONAL GO (Proceed with follow-up)
If:
- [ ] P1 errors found (document and schedule fixes)
- [ ] Performance slightly below baseline (10-30% slower)
- [ ] Some non-critical features not working

**Action**: Document issues, create tickets, proceed only if core functionality intact

---

## Error Handling

### P0 Errors (Blocking)
1. Stop testing immediately
2. Document error in `verification_errors.log`
3. Fix source code
4. Re-run affected tests
5. Proceed only when resolved

### P1 Errors (Major)
1. Document in error log
2. Create ticket for next sprint
3. Continue testing with known issues
4. Note in deployment report

### P2/P3 Errors (Minor/Cosmetic)
1. Log for future cleanup
2. No action needed for deployment
3. Fix during refactoring phase

---

## Logs & Outputs

### Verification Logs
```
tests/
├── build_verification.log         # Build test results
├── verification_errors.log        # All errors found (P0-P3)
├── verification_results.log       # Complete test output
└── test_results_YYYYMMDD.md      # Manual test documentation (created after testing)
```

### Application Logs
```
state/
├── python-backend.log            # Python FastAPI logs
└── node-backend.log              # Node.js Express logs (if separate)
```

---

## Key Files Referenced

### Backend
- `/home/lf/AI-EMPLOYEE/backend/server.js` — Express server
- `/home/lf/AI-EMPLOYEE/backend/tenancy.js` — Tenant middleware
- `/home/lf/AI-EMPLOYEE/runtime/agents/problem-solver-ui/server.py` — FastAPI server

### Frontend
- `/home/lf/AI-EMPLOYEE/frontend/src/App.jsx` — React root
- `/home/lf/AI-EMPLOYEE/frontend/src/components/Dashboard.jsx` — Dashboard component
- `/home/lf/AI-EMPLOYEE/frontend/src/components/layout/Sidebar.jsx` — Sidebar navigation

### Python Runtime
- `/home/lf/AI-EMPLOYEE/runtime/core/tenancy.py` — Tenant management
- `/home/lf/AI-EMPLOYEE/runtime/core/unified_pipeline.py` — LLM pipeline
- `/home/lf/AI-EMPLOYEE/runtime/core/agent_controller.py` — Agent orchestration

---

## Testing Commands Quick Reference

```bash
# Run all automated tests
bash tests/phase2-verify.sh

# Run specific checks
python3 -m py_compile runtime/**/*.py
find backend -name "*.js" -exec node --check {} \;
cd frontend && npm run build

# Start system
npm start

# Check logs
tail -f state/python-backend.log

# Test specific endpoint
curl http://localhost:8787/api/status

# Monitor WebSocket
# Chrome DevTools → Network → Filter by "WS"

# Performance audit
# Chrome DevTools → Lighthouse → Analyze page load

# Check memory
# Chrome DevTools → Memory → Record heap snapshot
```

---

## Support & Help

### If Tests Fail
1. Check `verification_errors.log` for error details
2. Review `ERROR_TRACKING_TEMPLATE.md` for resolution procedures
3. Consult common issues in `QUICK_START_TESTING.md`
4. Check application logs in `state/`

### If Stuck
1. Review `PHASE2_TESTING_GUIDE.md` for step-by-step procedures
2. Follow `FEATURE_TESTING_CHECKLIST.md` systematically
3. Check `DEPLOYMENT_READINESS_REPORT.md` for broader context
4. Use troubleshooting section in `QUICK_START_TESTING.md`

---

## Handoff to Phase 3

After Phase 2 completion:

1. **If GO Decision**: Proceed to Phase 3 (Neural Brain integration, API wiring, WebSocket expansion)
2. **If NO-GO Decision**: Fix P0 errors, re-run tests, obtain sign-off
3. **If CONDITIONAL GO**: Document issues, create tickets, proceed with known follow-ups

### Deliverables for Phase 3
- ✓ Build verification infrastructure
- ✓ Feature testing checklists
- ✓ Performance baseline established
- ✓ Security baseline validated
- ✓ Error tracking procedures
- ✓ Testing documentation (4 guides)
- ✓ Regression testing procedures

---

## Document Index

| Document | Purpose | Duration | Type |
|----------|---------|----------|------|
| phase2-verify.sh | Automated testing | 5 min | Script |
| PHASE2_TESTING_GUIDE.md | Detailed procedures | 30 min | Guide |
| FEATURE_TESTING_CHECKLIST.md | Manual checklist | 2-3 hrs | Checklist |
| DEPLOYMENT_READINESS_REPORT.md | Strategic assessment | 20 min | Report |
| ERROR_TRACKING_TEMPLATE.md | Error procedures | Reference | Template |
| QUICK_START_TESTING.md | Fast validation | 30 min-2 hrs | Guide |
| README_PHASE2_TESTING.md | This file | 15 min | Overview |

---

## Version & Changes

**Version**: 1.0.0
**Created**: 2026-05-13
**Status**: Ready for Execution
**Branch**: wavefield-routing

**Next Updates**:
- After Phase 2 execution: Add test results and findings
- After Phase 3 completion: Add integration test results
- Ongoing: Update based on actual testing experience

---

**Phase 2 Testing Framework — Ready for Deployment**

For questions or issues, refer to the appropriate document above or review the application logs in `/home/lf/AI-EMPLOYEE/state/`

