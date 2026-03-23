#!/usr/bin/env bash
# AI Employee — Stop script
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

G='\033[0;32m'; C='\033[0;36m'; NC='\033[0m'
log() { echo -e "${C}▸${NC} $1"; }
ok()  { echo -e "${G}✓${NC} $1"; }

log "Stopping bots..."
"$AI_HOME/bin/ai-employee" stop --all >/dev/null 2>&1 || true

log "Stopping gateway..."
if [[ -f "$AI_HOME/run/gateway.pid" ]]; then
  pid=$(cat "$AI_HOME/run/gateway.pid" 2>/dev/null || true)
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$AI_HOME/run/gateway.pid"
fi
# fallback: by name
pkill -f "openclaw gateway" 2>/dev/null || true

log "Stopping dashboard..."
if [[ -f "$AI_HOME/run/dashboard.pid" ]]; then
  pid=$(cat "$AI_HOME/run/dashboard.pid" 2>/dev/null || true)
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -f "$AI_HOME/run/dashboard.pid"
fi
pkill -f "http.server $DASHBOARD_PORT" 2>/dev/null || true

ok "AI Employee stopped."
