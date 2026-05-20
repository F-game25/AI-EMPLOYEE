#!/usr/bin/env bash
# Post-deploy smoke tests.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8787}"
TIMEOUT="${TIMEOUT:-30}"
FAIL=0

check() {
  local label="$1" url="$2" expected_status="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "${url}" 2>/dev/null || echo "000")
  if [[ "${status}" == "${expected_status}" ]]; then
    echo "  OK  ${label} (${status})"
  else
    echo "  FAIL ${label} — expected ${expected_status}, got ${status}"
    FAIL=1
  fi
}

echo "Smoke tests against ${BASE_URL}"

check "Node health"           "${BASE_URL}/api/health"
check "RPA sessions"          "${BASE_URL}/api/rpa/sessions"          200
check "Healing status"        "${BASE_URL}/api/healing/status"        200
check "Marketplace plugins"   "${BASE_URL}/api/marketplace/plugins"   200
check "Deployment status"     "${BASE_URL}/api/deployment/status"     200
check "Simulation scenarios"  "${BASE_URL}/api/simulation/scenarios"  200
check "RAG status"            "${BASE_URL}/api/rag/status"            200
check "Planning goals"        "${BASE_URL}/api/planning/goals"        200
check "Economics summary"     "${BASE_URL}/api/economics/summary"     200

if [[ "${FAIL}" == "1" ]]; then
  echo "One or more smoke tests FAILED."
  exit 1
fi

echo "All smoke tests passed."
