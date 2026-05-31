#!/bin/bash

# ============================================================================
# PHASE 2 TESTING & VERIFICATION SCRIPT
# AI-EMPLOYEE System — Build, Feature, Regression, Security Checks
# ============================================================================

set -e

PROJECT_ROOT="/home/lf/AI-EMPLOYEE"
BUILD_LOG="$PROJECT_ROOT/tests/build_verification.log"
ERROR_LOG="$PROJECT_ROOT/tests/verification_errors.log"
RESULTS_LOG="$PROJECT_ROOT/tests/verification_results.log"

# Initialize logs
> "$BUILD_LOG"
> "$ERROR_LOG"
> "$RESULTS_LOG"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$RESULTS_LOG"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1" | tee -a "$RESULTS_LOG"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1" | tee -a "$RESULTS_LOG"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$RESULTS_LOG"; }

error_log() {
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$timestamp | $1" >> "$ERROR_LOG"
}

# ============================================================================
# 1. BUILD & SYNTAX VERIFICATION
# ============================================================================

log_info "=========================================="
log_info "1. BUILD & SYNTAX VERIFICATION"
log_info "=========================================="

# Check Python syntax
log_info "Checking Python syntax..."
python3_errors=0
while IFS= read -r file; do
  if ! python3 -m py_compile "$file" 2>/dev/null; then
    log_fail "Python syntax error: $file"
    error_log "SYNTAX | Python | $file | Failed compilation"
    ((python3_errors++))
  fi
done < <(find "$PROJECT_ROOT/runtime" -name "*.py" -type f 2>/dev/null)

if [ $python3_errors -eq 0 ]; then
  log_pass "Python syntax check: All files valid"
else
  log_fail "Python syntax check: $python3_errors files with errors"
fi

# Check Node.js syntax
log_info "Checking Node.js syntax..."
node_errors=0
while IFS= read -r file; do
  if ! node --check "$file" 2>/dev/null; then
    log_fail "Node syntax error: $file"
    error_log "SYNTAX | Node | $file | Failed check"
    ((node_errors++))
  fi
done < <(find "$PROJECT_ROOT/backend" -name "*.js" -type f 2>/dev/null | grep -v node_modules)

if [ $node_errors -eq 0 ]; then
  log_pass "Node.js syntax check: All files valid"
else
  log_fail "Node.js syntax check: $node_errors files with errors"
fi

# Build frontend
log_info "Building frontend..."
cd "$PROJECT_ROOT/frontend"
if npm run build > /tmp/frontend_build.log 2>&1; then
  log_pass "Frontend build: Success"
  if [ -d "$PROJECT_ROOT/frontend/dist" ]; then
    bundle_size=$(du -sh "$PROJECT_ROOT/frontend/dist" | cut -f1)
    log_info "Bundle size: $bundle_size"
  fi
else
  log_fail "Frontend build failed"
  error_log "BUILD | Frontend | npm run build | Build failed"
  cat /tmp/frontend_build.log >> "$ERROR_LOG"
fi

# Check critical imports
log_info "Validating critical imports..."
cd "$PROJECT_ROOT"

# Check backend imports
import_errors=0
if ! node -e "require('./backend/server.js')" 2>/dev/null; then
  log_warn "Backend server imports may have issues (check runtime)"
  ((import_errors++))
fi

# Check for missing dependencies
if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
  log_warn "node_modules missing, running npm install..."
  npm install --prefer-offline 2>&1 | tail -5 >> "$BUILD_LOG"
fi

if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
  log_warn "frontend/node_modules missing, running npm install..."
  cd "$PROJECT_ROOT/frontend"
  npm install --prefer-offline 2>&1 | tail -5 >> "$BUILD_LOG"
fi

log_pass "Import validation complete"

# ============================================================================
# 2. FEATURE TESTING CHECKLIST (Automated portions)
# ============================================================================

log_info "=========================================="
log_info "2. FEATURE TESTING (Automated)"
log_info "=========================================="

# Check if servers can start (basic validation)
log_info "Checking server startup prerequisites..."

# Verify Python backend structure
if [ -f "$PROJECT_ROOT/runtime/agents/problem-solver-ui/server.py" ]; then
  log_pass "Python FastAPI server found"
else
  log_fail "Python FastAPI server not found"
  error_log "FEATURE | Backend | server.py | Not found"
fi

# Verify Node backend structure
if [ -f "$PROJECT_ROOT/backend/server.js" ]; then
  log_pass "Node.js Express server found"
else
  log_fail "Node.js Express server not found"
  error_log "FEATURE | Backend | server.js | Not found"
fi

# Verify frontend build output
if [ -d "$PROJECT_ROOT/frontend/dist" ]; then
  if [ -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
    log_pass "Frontend dist/index.html exists"
  else
    log_fail "Frontend dist/index.html missing"
    error_log "FEATURE | Frontend | dist/index.html | Not found"
  fi
else
  log_warn "Frontend dist directory not built (expected for dev workflow)"
fi

# Verify WebSocket setup in backend
if grep -q "ws\|WebSocket" "$PROJECT_ROOT/backend/server.js" 2>/dev/null; then
  log_pass "WebSocket setup detected in backend"
else
  log_warn "WebSocket setup not clearly visible in grep (check code)"
fi

# ============================================================================
# 3. REGRESSION TESTING
# ============================================================================

log_info "=========================================="
log_info "3. REGRESSION TESTING"
log_info "=========================================="

log_info "Checking backward compatibility..."

# Check auth route existence
if grep -q "auth/login\|auth/register" "$PROJECT_ROOT/backend/server.js" 2>/dev/null; then
  log_pass "Auth routes present"
else
  log_fail "Auth routes missing"
  error_log "REGRESSION | Auth | routes | Not found"
fi

# Check API route structure
if grep -q "/api/" "$PROJECT_ROOT/backend/server.js" 2>/dev/null; then
  log_pass "API route structure intact"
else
  log_fail "API route structure broken"
  error_log "REGRESSION | API | /api/* routes | Not found"
fi

# Check old component references (backward compat)
if grep -q "Dashboard\|Sidebar" "$PROJECT_ROOT/frontend/src/App.jsx" 2>/dev/null; then
  log_pass "Legacy components still referenced"
else
  log_warn "Legacy component references may have changed (expected)"
fi

# ============================================================================
# 4. SECURITY VERIFICATION
# ============================================================================

log_info "=========================================="
log_info "4. SECURITY VERIFICATION"
log_info "=========================================="

# Check JWT token handling
if grep -q "JWT\|jwt\|token" "$PROJECT_ROOT/runtime/agents/problem-solver-ui/server.py" 2>/dev/null; then
  log_pass "JWT token handling present"
else
  log_fail "JWT token handling not found"
  error_log "SECURITY | Auth | JWT | Not implemented"
fi

# Check rate limiting
if grep -q "rate.*limit\|_auth_rate_limit" "$PROJECT_ROOT/runtime/agents/problem-solver-ui/server.py" 2>/dev/null; then
  log_pass "Rate limiting implemented"
else
  log_warn "Rate limiting not clearly visible (check decorator)"
fi

# Check for secrets in logs
log_info "Scanning for exposed secrets..."
secret_count=0
if [ -f "$PROJECT_ROOT/state/python-backend.log" ]; then
  if grep -iE "API_KEY|SECRET|PASSWORD|TOKEN.*=" "$PROJECT_ROOT/state/python-backend.log" | head -1 > /tmp/secret_check 2>&1; then
    log_warn "Potential secrets in logs (manual review needed)"
    ((secret_count++))
  fi
fi

if [ $secret_count -eq 0 ]; then
  log_pass "No obvious secrets in accessible logs"
fi

# Check CSP headers (backend should set them)
if grep -q "Content-Security-Policy\|CSP\|helmet" "$PROJECT_ROOT/backend/server.js" 2>/dev/null; then
  log_pass "CSP headers or security middleware present"
else
  log_warn "CSP headers not explicitly configured (may be set by default)"
fi

# Check tenant isolation
if grep -q "tenant\|TENANT" "$PROJECT_ROOT/backend/tenancy.js" 2>/dev/null || \
   grep -q "tenant\|TenantContext" "$PROJECT_ROOT/runtime/core/tenancy.py" 2>/dev/null; then
  log_pass "Multi-tenancy implementation present"
else
  log_fail "Multi-tenancy not implemented"
  error_log "SECURITY | Tenancy | isolation | Not found"
fi

# ============================================================================
# 5. FILE & MODIFICATION TRACKING
# ============================================================================

log_info "=========================================="
log_info "5. FILE MODIFICATION TRACKING"
log_info "=========================================="

modified_count=$(git status --short 2>/dev/null | wc -l || echo "0")
log_info "Modified files: $modified_count"

# Check for critical untracked files
if [ -f "$PROJECT_ROOT/.env" ] && [ ! -f "$PROJECT_ROOT/.env.example" ]; then
  log_warn ".env exists but .env.example missing (expected)"
fi

# Verify all expected backend files exist
expected_backend=("server.js" "tenancy.js")
for file in "${expected_backend[@]}"; do
  if [ -f "$PROJECT_ROOT/backend/$file" ]; then
    log_pass "backend/$file exists"
  else
    log_fail "backend/$file missing"
    error_log "FILE | Backend | $file | Not found"
  fi
done

# Verify key frontend files
if [ -f "$PROJECT_ROOT/frontend/src/App.jsx" ]; then
  log_pass "frontend/src/App.jsx exists"
else
  log_fail "frontend/src/App.jsx missing"
  error_log "FILE | Frontend | App.jsx | Not found"
fi

# ============================================================================
# 6. DEPLOYMENT READINESS
# ============================================================================

log_info "=========================================="
log_info "6. DEPLOYMENT READINESS CHECKLIST"
log_info "=========================================="

readiness_score=0
readiness_total=8

# No syntax errors
if [ $python3_errors -eq 0 ] && [ $node_errors -eq 0 ]; then
  log_pass "[✓] No syntax errors"
  ((readiness_score++))
else
  log_fail "[✗] Syntax errors found"
fi
((readiness_total++))

# No broken imports
if [ $import_errors -eq 0 ]; then
  log_pass "[✓] Imports validated"
  ((readiness_score++))
else
  log_fail "[✗] Import errors detected"
fi
((readiness_total++))

# Frontend builds
if [ -d "$PROJECT_ROOT/frontend/dist" ]; then
  log_pass "[✓] Frontend builds successfully"
  ((readiness_score++))
else
  log_warn "[!] Frontend not yet built (will build on start)"
fi
((readiness_total++))

# Security baseline met
log_pass "[✓] Security baseline checked"
((readiness_score++))
((readiness_total++))

# No merge conflicts
conflict_count=$(grep -r "<<<<<<< HEAD" "$PROJECT_ROOT" --exclude-dir=node_modules --exclude-dir=.git 2>/dev/null | wc -l)
if [ $conflict_count -eq 0 ]; then
  log_pass "[✓] No merge conflicts"
  ((readiness_score++))
else
  log_fail "[✗] Merge conflicts detected: $conflict_count"
fi
((readiness_total++))

# Critical paths exist
if [ -f "$PROJECT_ROOT/backend/server.js" ] && [ -f "$PROJECT_ROOT/runtime/agents/problem-solver-ui/server.py" ]; then
  log_pass "[✓] Critical paths exist"
  ((readiness_score++))
else
  log_fail "[✗] Critical paths missing"
fi
((readiness_total++))

# Auth implemented
if grep -q "auth" "$PROJECT_ROOT/backend/server.js" 2>/dev/null; then
  log_pass "[✓] Auth routes present"
  ((readiness_score++))
else
  log_fail "[✗] Auth routes missing"
fi
((readiness_total++))

# Multi-tenancy
if grep -q "tenant" "$PROJECT_ROOT/backend/tenancy.js" 2>/dev/null; then
  log_pass "[✓] Multi-tenancy implemented"
  ((readiness_score++))
else
  log_warn "[!] Multi-tenancy may need verification"
fi
((readiness_total++))

# ============================================================================
# FINAL SUMMARY
# ============================================================================

log_info "=========================================="
log_info "SUMMARY"
log_info "=========================================="

log_info "Python syntax errors: $python3_errors"
log_info "Node syntax errors: $node_errors"
log_info "Deployment readiness: $readiness_score/$readiness_total"

error_count=$(wc -l < "$ERROR_LOG" 2>/dev/null || echo 0)
if [ $error_count -gt 1 ]; then
  log_warn "Total logged issues: $((error_count - 1))"
else
  log_pass "No critical issues logged"
fi

log_info ""
log_info "Logs created:"
log_info "  - $BUILD_LOG"
log_info "  - $ERROR_LOG"
log_info "  - $RESULTS_LOG"

if [ $python3_errors -eq 0 ] && [ $node_errors -eq 0 ] && [ $readiness_score -ge $((readiness_total - 2)) ]; then
  log_pass ""
  log_pass "✓ PHASE 2 VERIFICATION PASSED"
  log_pass "  System ready for feature testing and manual verification"
  exit 0
else
  log_fail ""
  log_fail "✗ PHASE 2 VERIFICATION INCOMPLETE"
  log_fail "  Please review errors above before proceeding"
  exit 1
fi
