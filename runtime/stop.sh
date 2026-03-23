#!/usr/bin/env bash
# AI Employee — Stop script
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

G='\033[0;32m'; C='\033[0;36m'; NC='\033[0m'
log() { echo -e "${C}▸${NC} $1"; }
ok()  { echo -e "${G}✓${NC} $1"; }

# Load env to pick up DASHBOARD_PORT if set
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AI_HOME/.env" 2>/dev/null || true
  set +a
fi
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

log "Stopping bots..."
"$AI_HOME/bin/ai-employee" stop --all >/dev/null 2>&1 || true

log "Stopping gateway..."
if [[ -f "$AI_HOME/run/gateway.pid" ]]; then
  pid=$(cat "$AI_HOME/run/gateway.pid" 2>/dev/null || true)
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$AI_HOME/run/gateway.pid"
fi
pkill -f "openclaw gateway" 2>/dev/null || true

log "Stopping dashboard..."
if [[ -f "$AI_HOME/run/dashboard.pid" ]]; then
  pid=$(cat "$AI_HOME/run/dashboard.pid" 2>/dev/null || true)
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$AI_HOME/run/dashboard.pid"
fi
pkill -f "http.server $DASHBOARD_PORT" 2>/dev/null || true

ok "AI Employee stopped."
