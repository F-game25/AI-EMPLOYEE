# Quick Start Testing Guide
## Phase 2 — AI-EMPLOYEE System

**Duration**: ~7 hours total (flexible)
**Tools Needed**: Bash, Node.js 18+, Python 3.9+, Chrome/Chromium

---

## 5-MINUTE QUICK START

```bash
# 1. Navigate to project
cd /home/lf/AI-EMPLOYEE

# 2. Run automated checks
bash tests/phase2-verify.sh

# 3. Review results
cat tests/verification_results.log
cat tests/verification_errors.log

# Expected output:
# ✓ PHASE 2 VERIFICATION PASSED
# (if any P0 errors, fix them first)
```

---

## 30-MINUTE TESTING SPRINT

### Setup (5 min)
```bash
# 1. Install dependencies (if needed)
npm install
cd frontend && npm install && cd ..

# 2. Verify no lingering processes
pkill -f "node\|python3\|uvicorn" || true
sleep 2

# 3. Start system
npm start &
sleep 5
```

### Quick Feature Check (20 min)
```bash
# In browser, visit: http://localhost:8787

# Test checklist (2-3 min each):
# ✓ Page loads (no WSOD)
# ✓ Avatar visible and animating
# ✓ CommandDock shows stats at bottom
# ✓ EventFeed shows events
# ✓ Sidebar navigation works
# ✓ Click Dashboard → page loads
# ✓ No red errors in Chrome DevTools Console

# Optional: Run one Lighthouse audit
# Chrome DevTools → Lighthouse → Generate report
```

### Check Results (5 min)
```bash
# Verify no critical errors
grep -i error tests/verification_results.log

# Check logs for issues
tail -20 state/python-backend.log
tail -20 frontend/dist/.log 2>/dev/null || echo "(No frontend log)"
```

---

## 2-HOUR THOROUGH TESTING

### Phase 1: Automated Verification (20 min)
```bash
cd /home/lf/AI-EMPLOYEE

# Run full verification script
bash tests/phase2-verify.sh | tee test_run_$(date +%s).log

# Check all results
echo "=== Build Log ==="
tail -30 tests/build_verification.log

echo "=== Errors Found ==="
cat tests/verification_errors.log

echo "=== Results Summary ==="
tail -50 tests/verification_results.log
```

**Expected**: 0 P0 errors, readiness score ≥ 6/8

---

### Phase 2: Frontend Testing (40 min)

#### Startup (5 min)
```bash
# Start system (if not already running)
npm start

# Wait for ready signal
sleep 10
grep "READY\|listening" state/python-backend.log | head -5
```

#### Visual Testing (20 min)
1. Open browser: `http://localhost:8787`
2. Open DevTools: `F12`

**Test Features**:
- [ ] Page loads in < 5s (check DevTools Network tab)
- [ ] Avatar visible (center-left area)
- [ ] Avatar animating smoothly (no stuttering)
- [ ] CommandDock visible at bottom (with CPU/RAM/GPU stats)
- [ ] EventFeed showing events
- [ ] Sidebar has 20+ items
- [ ] Click "Dashboard" in sidebar → page loads
- [ ] Click "Operations" → page loads
- [ ] No console errors (F12 → Console tab)
- [ ] No console warnings (F12 → Console tab)

**Performance Check** (10 min)
1. DevTools → Lighthouse tab
2. Click "Analyze page load"
3. Wait for report
4. Check metrics:
   - First Contentful Paint: < 2s ✓
   - Largest Contentful Paint: < 3s ✓
   - Cumulative Layout Shift: < 0.1 ✓

#### Manual Checklist (15 min)
Use `tests/FEATURE_TESTING_CHECKLIST.md` sections 2.1-2.9

---

### Phase 3: Security Quick Check (30 min)

#### Auth Testing (10 min)
```bash
# Test login endpoint
curl -X POST http://localhost:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@test.com",
    "password": "TestPassword123!"
  }'

# Expected: Response with token or error (not 500)
```

#### Rate Limiting (10 min)
```bash
# Rapid fire requests
for i in {1..10}; do
  curl -X POST http://localhost:8787/auth/login \
    -H "Content-Type: application/json" \
    -d '{}'
  echo "Request $i"
done

# Expected: Some requests get rate-limited (429 or similar)
```

#### Security Headers (5 min)
```bash
# Check headers
curl -I http://localhost:8787

# Expected headers:
# - Content-Security-Policy (or X-Content-Type-Options)
# - X-Frame-Options
# - X-Content-Type-Options
```

#### Secrets Check (5 min)
```bash
# Check logs for exposed secrets
grep -i "password\|api_key\|token" state/python-backend.log | head -5

# Expected: No output (or only log message formats, no actual values)
```

---

### Phase 4: Quick Regression (30 min)

#### API Endpoints (10 min)
```bash
# Test critical endpoints
echo "Testing /api/status..."
curl -X GET http://localhost:8787/api/status

echo "Testing /api/agents..."
curl -X GET http://localhost:8787/api/agents

echo "Testing /api/chat..."
curl -X POST http://localhost:8787/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

# Expected: All return data (200) or proper error (400/401)
```

#### Old Components (10 min)
1. Open DevTools → Console
2. Run: `console.log(window.__STORE__)`
3. Verify old store accessible
4. Check pages still render in sidebar

#### WebSocket (10 min)
```bash
# In DevTools → Network tab, filter by "WS"
# You should see active WebSocket connection
# Events flowing with 50ms stagger (not all at once)
```

---

## COMMON ISSUES & QUICK FIXES

### Issue: "Cannot find module X"
```bash
# Fix:
npm install
cd frontend && npm install && cd ..
```

### Issue: Port 8787 Already in Use
```bash
# Find process:
lsof -i :8787

# Kill it:
kill -9 <PID>

# Then restart
npm start
```

### Issue: Python Backend Not Starting
```bash
# Check logs
tail -50 state/python-backend.log

# Ensure Python 3.9+ installed
python3 --version

# Install requirements
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### Issue: Frontend Not Building
```bash
# Clear cache and reinstall
rm -rf frontend/node_modules frontend/dist
cd frontend && npm install && npm run build
```

### Issue: High Memory Usage
```bash
# Check what's consuming memory
ps aux | grep -E "node|python" | grep -v grep

# Kill all background processes
killall node python3 || true

# Restart fresh
npm start
```

### Issue: WebSocket Not Connecting
```bash
# Check Python backend running
curl http://localhost:18790/health

# If failed, check logs
tail -30 state/python-backend.log

# Restart Python backend
pkill -f uvicorn
npm start
```

---

## TEST RESULT LOGGING

### After Each Test Phase
```bash
# Create summary log
cat > test_results_$(date +%Y%m%d_%H%M%S).txt << 'EOF'
DATE: $(date)
BRANCH: $(git rev-parse --abbrev-ref HEAD)
COMMIT: $(git rev-parse --short HEAD)

BUILD STATUS: [ PASS | FAIL ]
FRONTEND STATUS: [ PASS | FAIL ]
PERFORMANCE STATUS: [ PASS | FAIL ]
SECURITY STATUS: [ PASS | FAIL ]
REGRESSION STATUS: [ PASS | FAIL ]

OVERALL: [ GO | NO-GO ]

ISSUES FOUND:
1. [List issues]
2. [...]

NOTES:
[Any additional observations]
EOF
```

---

## PASS/FAIL CRITERIA

### PASS (GO to production)
- [ ] All P0 errors fixed
- [ ] 0 syntax errors
- [ ] Frontend loads < 5s
- [ ] Avatar animates smoothly (30+ FPS)
- [ ] CommandDock shows stats
- [ ] EventFeed shows events
- [ ] No console errors
- [ ] Auth works
- [ ] Security headers present
- [ ] No secrets logged
- [ ] API endpoints respond
- [ ] WebSocket connects
- [ ] Regression tests pass

### FAIL (NO-GO, fix before proceeding)
- [ ] P0 errors exist
- [ ] Syntax errors > 0
- [ ] Frontend build fails
- [ ] Page loads > 5s
- [ ] Avatar not rendering
- [ ] CommandDock broken
- [ ] Critical console errors
- [ ] Auth broken
- [ ] WebSocket not connecting
- [ ] Merge conflicts present

---

## HELP COMMANDS

### System Status
```bash
# Check if servers running
ps aux | grep -E "node|python" | grep -v grep

# Check ports
netstat -tuln | grep -E "8787|18790"

# Check logs
tail -f state/python-backend.log
```

### Quick Restart
```bash
# Kill all
pkill -f "node\|python3\|uvicorn" || true
sleep 2

# Start fresh
npm start
```

### View Test Results
```bash
# See what tests ran
cat tests/verification_results.log

# See errors found
cat tests/verification_errors.log

# See build details
cat tests/build_verification.log
```

### Run Individual Test
```bash
# Just syntax check
python3 -m py_compile runtime/**/*.py

# Just frontend build
cd frontend && npm run build

# Just auth test
curl -X POST http://localhost:8787/auth/login
```

---

## DOCUMENTATION REFERENCE

| Document | Purpose | Duration |
|----------|---------|----------|
| PHASE2_TESTING_GUIDE.md | Detailed testing procedures | 30 min read |
| FEATURE_TESTING_CHECKLIST.md | Comprehensive manual checklist | Use during testing |
| DEPLOYMENT_READINESS_REPORT.md | Strategic assessment | 15 min read |
| ERROR_TRACKING_TEMPLATE.md | Error documentation | Reference |
| QUICK_START_TESTING.md | This file — fast overview | 5-10 min |

---

## NEXT STEPS AFTER TESTING

### If All Tests Pass
1. ✓ Document test results
2. ✓ Commit test files to git
3. ✓ Get sign-off from team lead
4. ✓ Proceed to Phase 3

### If Issues Found
1. Document issues in verification_errors.log
2. Prioritize by severity (P0 > P1 > P2 > P3)
3. Fix P0 issues before anything else
4. Re-run tests to confirm fixes
5. Document resolutions
6. Only proceed when P0 errors = 0

---

## TESTING TIME ESTIMATE

| Activity | Time |
|----------|------|
| Automated Verification | 15 min |
| Frontend Visual Testing | 30 min |
| Performance Audit | 20 min |
| Security Checks | 30 min |
| Regression Testing | 30 min |
| Documentation | 15 min |
| **TOTAL** | **~2.5 hours** |

(Can be extended to 6-7 hours for more thorough testing)

---

## CONTACT & ESCALATION

If critical issues found:
1. Document in verification_errors.log with P0 severity
2. Check tests/DEPLOYMENT_READINESS_REPORT.md for next steps
3. Review ERROR_TRACKING_TEMPLATE.md for resolution procedures

---

**Testing Quick Reference v1.0**
**Created**: 2026-05-13
**Next Review**: After Phase 2 execution

