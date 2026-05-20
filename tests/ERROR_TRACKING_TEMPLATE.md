# Error Tracking & Resolution Template
## Phase 2 Testing — AI-EMPLOYEE System

---

## ERROR LOG FORMAT

All errors logged to `/home/lf/AI-EMPLOYEE/tests/verification_errors.log`

### Standard Format
```
TIMESTAMP | COMPONENT | ERROR_TYPE | MESSAGE | SEVERITY | STATUS
2026-05-13 10:30:45 | Python | SYNTAX | runtime/agents/test.py line 42: invalid syntax | P0 | OPEN
2026-05-13 10:31:12 | Frontend | IMPORT | Module 'nonexistent' not found | P1 | RESOLVED
```

### Fields
- **TIMESTAMP**: ISO 8601 format (YYYY-MM-DD HH:MM:SS)
- **COMPONENT**: Python | Node | Frontend | WebSocket | Auth | Performance | Security | DB
- **ERROR_TYPE**: SYNTAX | IMPORT | BUILD | RUNTIME | LOGIC | PERF | SECURITY | CONFIG
- **MESSAGE**: Description of the error
- **SEVERITY**: P0 | P1 | P2 | P3
- **STATUS**: OPEN | INVESTIGATING | RESOLVED | DEFERRED | WONT_FIX

---

## SEVERITY LEVELS

### P0 — BLOCKING (Critical)
**Definition**: Prevents system from starting or core functionality completely broken

**Examples**:
- Syntax errors that prevent code execution
- Missing critical dependencies
- Authentication system broken
- Database connection failed
- Deployment cannot proceed

**Action**: Stop testing immediately, fix before continuing

**SLA**: Must resolve before going to production

---

### P1 — MAJOR (High)
**Definition**: Significant functionality broken or severely degraded

**Examples**:
- Feature doesn't work as expected
- Performance significantly below baseline (>50% slower)
- Security vulnerability (non-critical)
- Memory leak causing crashes
- Frontend UI broken but functional

**Action**: Document, fix in this sprint if possible

**SLA**: Should fix before Phase 3 merge

---

### P2 — MINOR (Medium)
**Definition**: Limited impact, workaround available, nice-to-have fix

**Examples**:
- Cosmetic UI issues
- Performance slightly below baseline (10-30% slower)
- Non-critical error logging
- Deprecated function usage
- Console warnings

**Action**: Log and schedule for follow-up sprint

**SLA**: Fix in next 1-2 sprints

---

### P3 — COSMETIC (Low)
**Definition**: Negligible impact, no workaround needed

**Examples**:
- Minor text alignment issue
- Unused import warning
- Non-functional dead code
- Comment typos
- Unused CSS classes

**Action**: Log for future cleanup

**SLA**: Fix during refactoring or when touching that code

---

## ERROR TEMPLATE

Use this template for each error found:

```markdown
## Error #N: [Brief Title]

**Date Discovered**: [YYYY-MM-DD HH:MM:SS]
**Component**: [Python | Node | Frontend | etc.]
**Type**: [SYNTAX | IMPORT | RUNTIME | PERF | SECURITY | etc.]
**Severity**: [P0 | P1 | P2 | P3]
**Status**: [OPEN | INVESTIGATING | RESOLVED]

### Description
[What went wrong? Include error message, stack trace if applicable]

### Location
[File path, line number(s)]

### Root Cause
[Why did this happen? What was the mistake?]

### Reproduction Steps
1. [Step 1]
2. [Step 2]
3. [Observe error]

### Impact
[What does this break? Who is affected?]

### Fix Applied
[What was done to fix it? Include code changes if applicable]

### Testing
[How was the fix validated? What tests confirm it's resolved?]

### Resolution Date
[When was this fixed?]

### Lessons Learned
[What can we do to prevent this in the future?]

---
```

---

## COMMON ERRORS & RESOLUTIONS

### SYNTAX ERRORS

#### Error: Python Syntax Error
```
File: runtime/agents/test.py, line 42
Error: SyntaxError: invalid syntax
Code: if x = 5:  # should be ==
```

**Resolution**:
```python
# Fix: Use == for comparison, not =
if x == 5:
    pass
```

**Prevention**: Use linter (flake8, black)

---

#### Error: Node.js Syntax Error
```
File: backend/server.js, line 89
Error: SyntaxError: Unexpected token }
Code: const obj = { name: "test", };  // trailing comma in object
```

**Resolution**:
```javascript
// Fix: Remove trailing comma or enable ES5+ features
const obj = { name: "test" };
```

**Prevention**: Use ESLint with airbnb config

---

### IMPORT ERRORS

#### Error: Python Module Not Found
```
File: runtime/core/agent_controller.py, line 5
Error: ModuleNotFoundError: No module named 'nonexistent'
Code: from nonexistent import something
```

**Resolution**:
```python
# Option 1: Install missing package
# pip install nonexistent

# Option 2: Fix import path
from existing_module import something
```

**Prevention**: Run tests before committing

---

#### Error: Node.js Module Not Found
```
File: backend/server.js, line 3
Error: Cannot find module 'nonexistent'
Code: const pkg = require('nonexistent');
```

**Resolution**:
```javascript
// Option 1: Install missing package
// npm install nonexistent

// Option 2: Fix require path
const pkg = require('./existing-module');
```

**Prevention**: npm install before testing

---

### BUILD ERRORS

#### Error: Frontend Build Fails
```
Error: Module parse failed: Unexpected token
File: frontend/src/components/Test.jsx, line 42
```

**Resolution**:
```bash
# Check for JSX syntax errors
# Common: Invalid JSX, missing closing tags
# Fix: Review JSX syntax in reported file

# Retry build
cd frontend && npm run build
```

**Prevention**: Use Prettier for auto-formatting

---

#### Error: Bundle Too Large
```
Bundle size: 2.3 MB (target: < 1.5 MB)
Gzipped: 750 KB (target: < 500 KB)
```

**Resolution**:
```bash
# Analyze bundle
npm run analyze

# Find large dependencies and consider:
# 1. Code splitting
# 2. Lazy loading
# 3. Alternative libraries
# 4. Tree-shaking optimization

# Rebuild
npm run build
```

**Prevention**: Monitor bundle size in CI

---

### RUNTIME ERRORS

#### Error: Cannot Read Property of Undefined
```
Error: Cannot read property 'name' of undefined
File: runtime/agents/test.py, line 15
Code: agent = None
      print(agent.name)  # agent is None!
```

**Resolution**:
```python
# Option 1: Check before access
if agent:
    print(agent.name)

# Option 2: Use optional attribute access
print(getattr(agent, 'name', 'Unknown'))

# Option 3: Ensure agent is initialized
agent = Agent(name="test")
print(agent.name)
```

**Prevention**: Add type hints, use mypy for type checking

---

#### Error: WebSocket Connection Lost
```
Error: WebSocket closed: code 1006, reason "abnormal closure"
Time: 2026-05-13 10:30:45
```

**Resolution**:
```javascript
// Check server is running
// Check port 18790 is open
// Verify auth token is valid
// Check network connectivity

// Implement reconnection logic with exponential backoff
ws.addEventListener('close', () => {
  setTimeout(() => {
    reconnectWebSocket();
  }, 1000 * Math.pow(2, retryCount));
});
```

**Prevention**: Implement heartbeat/ping-pong

---

### PERFORMANCE ERRORS

#### Error: Page Load Time Exceeds Threshold
```
Load time: 8.5 seconds (target: < 5 seconds)
FCP: 3.2s (target: < 2s)
LCP: 5.1s (target: < 3s)
```

**Resolution**:
```bash
# 1. Profile with Lighthouse
# Chrome DevTools → Lighthouse

# 2. Identify bottlenecks
# - Large images? Use webp + lazy load
# - Large JS? Code split, lazy load routes
# - Large CSS? Remove unused, minify
# - Network slow? Reduce requests

# 3. Optimize
# - Compress assets
# - Enable caching
# - Use CDN
# - Reduce redirects

# 4. Re-test
npm run build
lighthouse http://localhost:8787
```

**Prevention**: Monitor performance in CI

---

#### Error: High Memory Usage
```
Initial: 45 MB
Peak: 280 MB (target: < 150 MB)
After idle: 200 MB (memory leak suspected)
```

**Resolution**:
```javascript
// 1. Use DevTools Memory profiler
// Chrome → DevTools → Memory → Record heap snapshot

// 2. Look for detached DOM nodes
// Event listeners not cleaned up
// Circular references

// 3. Fix memory leaks
// Properly clean up event listeners
window.addEventListener('message', handler);
// Later:
window.removeEventListener('message', handler);

// Use WeakMap for caches
const cache = new WeakMap();
```

**Prevention**: Regular memory profiling

---

### SECURITY ERRORS

#### Error: Secrets Exposed in Logs
```
File: state/python-backend.log
Pattern: API_KEY=sk_live_xyz123...
```

**Resolution**:
```python
# Don't log sensitive values
# BAD:
print(f"Connecting with key: {api_key}")

# GOOD:
logger.info("Connecting to API")
logger.debug(f"Key suffix: {api_key[-4:]}")

# Use environment variables
import os
API_KEY = os.getenv('API_KEY')  # Not in logs
```

**Prevention**: Code review, secret scanning in CI

---

#### Error: CORS Policy Violation
```
Error: Access to XMLHttpRequest blocked by CORS policy
Origin: http://localhost:5173
```

**Resolution**:
```javascript
// backend/server.js
const cors = require('cors');

app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:8787'],
  credentials: true
}));
```

**Prevention**: Configure CORS explicitly

---

## INVESTIGATION CHECKLIST

When an error is found:

- [ ] Reproduce the error consistently
- [ ] Identify exact file and line number
- [ ] Understand root cause
- [ ] Check if this is a regression (was it working before?)
- [ ] Assess impact on other components
- [ ] Determine severity level (P0-P3)
- [ ] Create fix
- [ ] Test fix thoroughly
- [ ] Verify no new errors introduced
- [ ] Update related documentation
- [ ] Log resolution in error_log

---

## RESOLUTION WORKFLOW

### For P0 Errors
```
1. OPEN: Error discovered
2. INVESTIGATING: Root cause analysis
3. FIXING: Code changes applied
4. TESTING: Fix validated
5. RESOLVED: Confirmed working
6. BLOCKED_IF_FAIL: Re-enter FIXING if validation fails
```

### For P1 Errors
```
1. OPEN: Error discovered
2. INVESTIGATING: Root cause analysis
3. FIXING: Code changes applied (or DEFERRED if lower priority)
4. TESTING: Fix validated
5. RESOLVED: Confirmed working
6. DEFERRED: Scheduled for next sprint if P1 is critical
```

### For P2/P3 Errors
```
1. OPEN: Error discovered
2. LOGGED: Added to backlog
3. DEFERRED: Scheduled for future sprint
4. WONT_FIX: If not important enough
5. RESOLVED: Fixed eventually
```

---

## ESCALATION PROCEDURE

### If P0 Error Occurs
1. Immediately notify team lead
2. Stop deployment
3. Focus all efforts on fix
4. Re-test after fix
5. Brief team on what happened
6. Document lessons learned

### If Multiple P1 Errors
1. Assess if deployment can proceed safely
2. If critical path affected: block deployment
3. If isolated: proceed with follow-up plan
4. Create tickets for each issue
5. Schedule resolution in next sprint

---

## ERROR STATISTICS

Track these metrics during testing:

```
METRIC                          | VALUE  | TARGET
Total Errors Found              | ___    | < 20
P0 Errors                       | ___    | 0
P1 Errors                       | ___    | < 3
P2 Errors                       | ___    | < 5
P3 Errors                       | ___    | < 10
Errors Resolved                 | ___    | 100%
Avg Time to Resolve (P0)        | ___ hr | < 1
Avg Time to Resolve (P1)        | ___ hr | < 4
Resolution Rate                 | ___%   | > 95%
```

---

## TOOLS FOR ERROR DIAGNOSIS

### Python
```bash
# Syntax check
python3 -m py_compile file.py

# Type checking
mypy file.py

# Linting
flake8 file.py

# Profiling
python3 -m cProfile -s cumulative script.py
```

### Node.js
```bash
# Syntax check
node --check file.js

# Linting
eslint file.js

# Bundle analysis
webpack-bundle-analyzer

# Profiling
node --prof app.js
node --prof-process isolate*.log
```

### Chrome DevTools
```
F12 → Console: JavaScript errors
F12 → Network: Network errors
F12 → Performance: Performance profiling
F12 → Memory: Memory leaks
F12 → Lighthouse: Accessibility, performance, SEO
```

---

## COMMUNICATION TEMPLATE

### When Reporting Error
```
Subject: [P0] Error Found in [Component]

Summary:
[Brief description of error]

Location:
File: [path]
Line: [number]

Steps to Reproduce:
1. [Step 1]
2. [Step 2]
3. [Error occurs]

Expected Behavior:
[What should happen]

Actual Behavior:
[What actually happens]

Severity:
P0 - Blocks deployment / P1 - Major / P2 - Minor / P3 - Cosmetic

Logs/Screenshots:
[Include relevant logs or screenshots]
```

---

## Sign-Off Template

```markdown
## Error Resolution Sign-Off

**Error ID**: [Number]
**Title**: [Brief title]
**Severity**: [P0-P3]

**Fixed By**: [Developer name]
**Date Fixed**: [YYYY-MM-DD]
**Verified By**: [Tester name]
**Date Verified**: [YYYY-MM-DD]

**Resolution**: [Brief description of fix]

**Testing Done**: [What tests confirm it's fixed?]

**Signed**: _________________ (Developer)
**Signed**: _________________ (Tester)
```

---

**End of Error Tracking Template**

