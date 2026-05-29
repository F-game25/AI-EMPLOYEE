# HOW THE NEXUS OS UPDATING SYSTEM WORKS

**This document explains the phase-based modular architecture that enables non-breaking updates to the system.**

---

## DESIGN PRINCIPLE: GRACEFUL DEGRADATION

The system is designed so that:
- ✅ Core system works without optional phases
- ✅ Optional phases fail gracefully if modules missing
- ✅ Each phase is independently deployable
- ✅ Newer phases don't break older code
- ✅ Rollback is a matter of commenting out a router mount

---

## THE PHASE ARCHITECTURE

The system is divided into **4 progressive phases**, each building on previous layers:

```
Phase 4: Cognitive Infrastructure (12 subsystems, 95 files)
    ↑ (depends on Phase 3 running correctly)
    │
Phase 3.3: Performance Optimization (code splitting, CSS tuning)
    ↑ (enhances Phase 3)
    │
Phase 3.2: Security Hardening (JWT rotation, RBAC, CSP)
    ↑ (enhances Phase 3)
    │
Phase 3: Core UI Redesign (Mission Control + event-driven)
    ↑ (depends on backend working)
    │
Backend + Node.js: Express server, WebSocket server
    ↑ (depends on Python working)
    │
Phase 1-2: Python Core (unified pipeline, agent controller)
```

Each phase is **independently mounted** and can **fail without affecting others**.

---

## HOW PHASES ARE MOUNTED

### Backend (Python FastAPI)

In `runtime/agents/problem-solver-ui/server.py`:

```python
# PHASE 3 (existing infrastructure)
try:
    from infra.api.phase3_routes import phase3_router
    app.include_router(phase3_router)
    logger.info("✅ Phase 3 routes mounted")
except Exception as e:
    logger.warning("⚠️  Phase 3 mount failed: %s", e)

# PHASE 4 (new cognitive infrastructure)
try:
    from infra.api.phase4_routes import phase4_router
    app.include_router(phase4_router)
    logger.info("✅ Phase 4 routes mounted")
except Exception as e:
    logger.warning("⚠️  Phase 4 mount failed: %s", e)
    # System continues without Phase 4 — not fatal
```

**Key pattern:** Each phase is wrapped in a try/except. If it fails:
- Phase 3 still works
- Phase 4 still works (optional)
- System continues with degraded features

### Frontend (Node.js Express)

In `backend/server.js`:

```javascript
// Optional cognitive routes (Phase 4)
try {
    const cognitiveRoutes = require('./infra/cognitive/routes');
    app.use('/api/cognitive', cognitiveRoutes);
    console.log('✅ Phase 4 cognitive routes mounted');
} catch (e) {
    console.warn('⚠️  Phase 4 mount failed:', e.message);
    // System continues without Phase 4 endpoints
}
```

Same pattern: if Phase 4 fails, the Node backend keeps serving the frontend and basic APIs.

---

## THE PHASE 4 AGGREGATOR PATTERN

Phase 4 is split into **12 independent subsystems**, each with its own routes file. They're all mounted by a single **aggregator router** (`runtime/infra/api/phase4_routes.py`):

```python
# runtime/infra/api/phase4_routes.py
from fastapi import APIRouter
import importlib

phase4_router = APIRouter()

COGNITIVE_MODULES = [
    ("infra.cognitive.coherence.coherence_routes",        "/cognitive/coherence"),
    ("infra.cognitive.executive.executive_routes",         "/cognitive/executive"),
    ("infra.cognitive.guardrails.guardrail_routes",        "/cognitive/guardrails"),
    # ... 9 more subsystems
]

for module_path, prefix in COGNITIVE_MODULES:
    try:
        module = importlib.import_module(module_path)
        if hasattr(module, 'router'):
            phase4_router.include_router(module.router, prefix=prefix)
            logger.info(f"✅ {prefix} mounted")
    except Exception as e:
        logger.warning(f"⚠️  {prefix} failed: {e}")
        # Continue to next subsystem
```

**Benefits:**
- Add new subsystems without touching the main server
- Disable individual subsystems by commenting out one line
- Each subsystem can fail without breaking the others

---

## ADDING A NEW PHASE

To add Phase 5 (hypothetical):

### Step 1: Create Phase 5 Router

```python
# runtime/infra/api/phase5_routes.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
async def phase5_status():
    return {"phase": 5, "status": "operational"}
```

### Step 2: Mount in Main Server

```python
# In runtime/agents/problem-solver-ui/server.py
try:
    from infra.api.phase5_routes import phase5_router
    app.include_router(phase5_router)
    logger.info("✅ Phase 5 routes mounted")
except Exception as e:
    logger.warning("⚠️  Phase 5 mount failed: %s", e)
```

### Step 3: Start Using Phase 5

No changes needed elsewhere. Phase 5 works immediately. If Phase 5 fails, everything else continues normally.

---

## DEPLOYMENT SCENARIOS

### Scenario 1: New Features Only (Phase 5)

**Current state:** Phases 1-4 in production  
**Change:** Add Phase 5 (new subsystems)

```bash
# No downtime needed
git pull origin main
npm run build
# (restart services)
# Phase 5 mounts during startup
# If Phase 5 has bugs: rollback with git, no code changes needed
```

### Scenario 2: Security Patch (Phase 3.2)

**Current state:** Phase 3.2 already mounted  
**Change:** Update JWT rotation logic

```bash
# Modify: backend/middleware/token-manager.js
git push origin security-patch
# Deploy during non-peak hours (users might get re-authenticated)
# Phase 3.2 re-mounts with new logic
```

### Scenario 3: Phase 4 Rollback (if issues found)

**Current state:** Phase 4 is live  
**Problem:** Cognitive subsystem consuming too much CPU

```python
# Option A: Quick disable in server.py
# Comment out these lines (2 try/except blocks):
# try:
#     from infra.api.phase4_routes import phase4_router
#     ...
# Restart server — Phase 4 routes removed, system works normally

# Option B: Selective subsystem disable
# In phase4_routes.py, comment out one subsystem import:
# ("infra.cognitive.scale.scale_routes", "/cognitive/scale"),  # Commented
# Restart — Phase 4 works except for scale monitoring
```

---

## FILE ORGANIZATION BY PHASE

```
runtime/infra/api/
├── phase3_routes.py       (main Phase 3 aggregator)
└── phase4_routes.py       (main Phase 4 aggregator)

runtime/infra/
├── telemetry/             (Phase 2)
├── security/              (Phase 3.2)
├── performance/           (Phase 3.3)
└── cognitive/             (Phase 4)
    ├── coherence/
    ├── executive/
    ├── guardrails/
    ├── ... (12 subsystems)
    └── db.py             (shared SQLite)

backend/infra/
├── cognitive/routes.js    (Phase 4 Node proxy)
└── security/              (Phase 3.2 middleware)
```

**Design rule:** Each phase owns its directory. Crossing directories = coupling.

---

## THE 5-STEP UPDATE CYCLE

Every update follows this sequence:

### 1. **Development** (on feature branch)

```bash
git checkout -b phase-5-development
# Make changes in runtime/infra/phase5/ + runtime/infra/api/phase5_routes.py
npm run build
npm test
```

### 2. **Testing** (local verification)

```bash
# Unit tests for Phase 5
python3 -m pytest tests/test_phase5.py

# Integration test
python3 runtime/agents/problem-solver-ui/server.py
curl http://localhost:18790/phase5/status  # Should work
```

### 3. **Code Review** (GitHub PR)

```bash
git push origin phase-5-development
# Create PR → code review → approve
# Automated CI runs tests + build verification
```

### 4. **Deployment** (to production)

```bash
# Merge PR to main
git checkout main && git pull origin main
npm run build
# Stop services
bash stop.sh
# (optional: backup state/)
# Start services
bash start.sh
```

### 5. **Verification** (live check)

```bash
# Health checks
curl http://localhost:18790/health
curl http://localhost:8787/health

# Phase 5 check
curl http://localhost:18790/phase5/status

# Monitor logs
tail -f python-backend.log
```

---

## MONITORING PHASE HEALTH

### Check Which Phases are Running

```bash
# From logs
tail -50 python-backend.log | grep "Phase.*mounted"

# Example output:
# ✅ Phase 2 enterprise intelligence routes mounted
# ✅ Phase 3 autonomous workforce routes mounted
# ✅ Phase 4 /cognitive/coherence mounted
# ✅ Phase 4 /cognitive/executive mounted
# [12 total Phase 4 subsystems]

# If Phase 4 failed:
# ⚠️  Phase 4 startup partial failure: [error details]
```

### Check Individual Subsystem Health

```bash
# Phase 4 status endpoints (all live)
curl http://localhost:18790/cognitive/coherence/status
curl http://localhost:18790/cognitive/resilience/status
curl http://localhost:18790/cognitive/temporal/status

# If a subsystem fails, others keep working
# Example: /cognitive/scale fails, others continue:
# GET /cognitive/coherence/status → 200 OK ✓
# GET /cognitive/scale/status     → 500 Error, but system continues
```

---

## ROLLBACK STRATEGY

### Fast Rollback (< 2 minutes)

If Phase 4 (or any phase) has critical issues:

```bash
# Option 1: Disable via code comment
vi runtime/agents/problem-solver-ui/server.py
# Find: try: from infra.api.phase4_routes import phase4_router
# Comment out the try/except block (3 lines)
python3 runtime/agents/problem-solver-ui/server.py
# Phase 4 routes gone, system stable

# Option 2: Revert to previous commit
git revert HEAD
npm run build
bash start.sh
# System reverts to previous state
```

### Selective Subsystem Disable

If only one Phase 4 subsystem has issues (e.g., scale):

```python
# In runtime/infra/api/phase4_routes.py, comment out:
# ("infra.cognitive.scale.scale_routes", "/cognitive/scale"),

# Restart → Phase 4 works except for scaling features
```

---

## CONFIGURATION FOR UPDATES

### Feature Flags (Optional)

Add to `~/.ai-employee/.env`:

```bash
PHASE4_ENABLED=1           # Enable Phase 4
COGNITIVE_DEBUG=0          # Debug subsystems
PHASE4_SUBSYSTEMS="coherence,executive,resilience"  # Only mount these
```

Usage in code:

```python
import os

phase4_enabled = os.getenv("PHASE4_ENABLED", "1") == "1"

if phase4_enabled:
    try:
        from infra.api.phase4_routes import phase4_router
        app.include_router(phase4_router)
    except Exception as e:
        logger.warning("Phase 4 disabled due to error: %s", e)
```

---

## DATABASE VERSIONING (Critical for Updates)

Each phase that needs persistent storage creates its own database:

```python
# Phase 4 uses:
# ~/.ai-employee/cognitive.db (SQLite, WAL mode)

# To migrate to new schema:
# 1. New Phase uses OLD schema for reads (backward compatible)
# 2. NEW schema written to new table
# 3. After verification, old table dropped
# 4. Zero downtime migration
```

---

## BEST PRACTICES FOR UPDATES

### ✅ DO:

- ✅ Each phase in its own directory (`runtime/infra/phase*/`)
- ✅ Wrap phase mounts in try/except
- ✅ Test each phase independently
- ✅ Use feature flags for gradual rollouts
- ✅ Keep database backward compatible
- ✅ Document new endpoints in OpenAPI/Swagger
- ✅ Monitor Phase health after deployment

### ❌ DON'T:

- ❌ Modify Phase 1/2 core (breaks everything)
- ❌ Hard-depend on optional phases
- ❌ Mix multiple phases in one file
- ❌ Deploy without testing phase isolation
- ❌ Assume WebSocket connections survive phase changes
- ❌ Use blocking imports (wrap in try/except)
- ❌ Forget to update SYSTEM_STATUS_REPORT.md

---

## EXAMPLE: Adding Phase 5 (Complete Walkthrough)

**Goal:** Add new "Quantum Reasoning" Phase 5

### Day 1: Development

```bash
# Branch
git checkout -b feat/phase5-quantum-reasoning

# Directory structure
mkdir -p runtime/infra/quantum
touch runtime/infra/quantum/{__init__.py,quantum_core.py,quantum_routes.py}

# Implement
cat > runtime/infra/quantum/quantum_routes.py << 'EOF'
from fastapi import APIRouter
router = APIRouter()

@router.get("/status")
async def quantum_status():
    return {"phase": "5-quantum", "reasoning_model": "quantum-v1"}
EOF

# Aggregator
cat > runtime/infra/api/phase5_routes.py << 'EOF'
from fastapi import APIRouter
from infra.quantum.quantum_routes import router as quantum_router
phase5_router = APIRouter()
phase5_router.include_router(quantum_router, prefix="/quantum")
EOF

# Mount in main server
# (Add to runtime/agents/problem-solver-ui/server.py)
```

### Day 2: Testing

```bash
# Unit test
python3 -m pytest tests/test_phase5_quantum.py

# Integration test
python3 runtime/agents/problem-solver-ui/server.py &
curl http://localhost:18790/quantum/status
# Should return: {"phase": "5-quantum", "reasoning_model": "quantum-v1"}

# Rollback test (disable Phase 5)
# Edit server.py, comment out phase5_router mount
python3 runtime/agents/problem-solver-ui/server.py &
curl http://localhost:18790/quantum/status
# Should return: 404 (Phase 5 disabled)
```

### Day 3: Review & Deploy

```bash
git push origin feat/phase5-quantum-reasoning
# → PR created → review → approve

git checkout main && git pull
npm run build
bash stop.sh && bash start.sh

# Verify
curl http://localhost:18790/quantum/status  # 200 OK ✓
tail python-backend.log | grep "Phase 5"    # ✅ mounted
```

---

## CONCLUSION

The Nexus OS updating system is built on **modular phases** that:
- 🔄 Deploy independently (no system-wide downtime)
- 🛡️ Fail gracefully (broken Phase 4 ≠ broken system)
- 📦 Are easy to add (new Phase 5 = new router file + 5 lines)
- 🔙 Rollback quickly (remove one mount try/except)
- 📊 Are monitorable (health endpoints per subsystem)

**This architecture enables continuous deployment at production scale.**

---

**Document:** SYSTEM_UPDATE_ARCHITECTURE.md  
**Purpose:** Explain how to add, update, and manage phases  
**Date:** 2026-05-13  
**Version:** 1.0.0
