#!/usr/bin/env bash
# End-to-end smoke test for the Nexus OS API surface added in WS3–WS8.
# Hits every new endpoint through the Node backend and reports pass/fail.
# Usage: bash scripts/smoke.sh   (backends must be running — e.g. via start.sh)

set -uo pipefail
BASE="${SMOKE_BASE:-http://localhost:8787}"
PY="${PYTHON_BIN:-$HOME/.ai-employee/python-core/bin/python}"
[[ -x "$PY" ]] || PY="python3"

pass=0; fail=0
TOKEN="$(curl -s --max-time 5 "$BASE/api/auth/auto-token" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)"
[[ -n "$TOKEN" ]] && echo "✓ auth token acquired" || { echo "✗ could not get auth token (is the stack up?)"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

# check NAME METHOD PATH [JSON_BODY] EXPECT_KEY
check() {
  local name="$1" method="$2" path="$3" body="${4:-}" key="${5:-}"
  local out
  if [[ "$method" == GET ]]; then
    out="$(curl -s --max-time 30 -H "$AUTH" "$BASE$path")"
  else
    out="$(curl -s --max-time 120 -X "$method" -H "$AUTH" -H 'Content-Type: application/json' -d "$body" "$BASE$path")"
  fi
  local ok
  ok="$(printf '%s' "$out" | "$PY" -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print('PARSE'); sys.exit()
k='$key'
if not k: print('OK'); sys.exit()
print('OK' if (isinstance(d,dict) and k in d) else 'MISS:'+str(list(d)[:4]))
" 2>/dev/null)"
  if [[ "$ok" == OK ]]; then echo "✓ $name"; pass=$((pass+1)); else echo "✗ $name ($ok)"; fail=$((fail+1)); fi
}

echo "── Model Fabric (WS5/WS8b) ──"
check "model-fabric/health"          GET  /api/model-fabric/health "" subsystems
check "model-fabric/models"          GET  /api/model-fabric/models "" resolved
check "quantization/pull/status"     GET  /api/model-fabric/quantization/pull/status "" status

echo "── Memory Graphs (WS3) ──"
for v in unified longterm shortterm relations; do
  check "memory/graph/$v"            GET  "/api/memory/graph/$v" "" nodes
done

echo "── Compute Fabric (WS6) ──"
check "compute/local-status"         GET  /api/compute/local-status "" ok
check "compute/estimate"             POST /api/compute/estimate '{"params_b":7,"task":"finetune","hours":2}' estimate
check "compute/search-offers"        POST /api/compute/search-offers '{"params_b":7,"hours":2}' offers
check "compute/spend"                GET  /api/compute/spend "" daily_cap
check "compute/purchase dry-run"     POST /api/compute/purchase '{"offer":{"provider":"runpod","hourly_usd":1.0,"hours":1}}' status

echo "── Compute job + persistence (WS7) ──"
JID="$(curl -s --max-time 15 -X POST -H "$AUTH" -H 'Content-Type: application/json' -d '{"name":"smoke","offer":{"provider":"runpod","gpu":"A100-80G","hourly_usd":1.0,"hours":1}}' "$BASE/api/compute/start-job" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["job"]["id"])' 2>/dev/null)"
[[ -n "$JID" ]] && { echo "✓ start-job ($JID)"; pass=$((pass+1)); } || { echo "✗ start-job"; fail=$((fail+1)); }
if [[ -n "$JID" ]]; then
  check "jobs/:id/collect"           POST "/api/compute/jobs/$JID/collect" '{"rel":"out.txt","content":"smoke"}' ok
  check "jobs/:id/sync-status"       GET  "/api/compute/jobs/$JID/sync-status" "" file_count
  check "jobs/:id/force-sync"        POST "/api/compute/jobs/$JID/force-sync" '{}' verified
  check "jobs/:id/recover"           GET  "/api/compute/jobs/$JID/recover" "" manifest
fi

echo "── Code understanding (WS4) ──"
check "forge/status"                 GET  /api/forge/status "" state

echo ""
echo "────────────────────────────"
echo "RESULT: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]] && echo "✅ all smoke checks passed" || echo "❌ $fail check(s) failed"
exit "$fail"
