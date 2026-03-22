#!/usr/bin/env bash
# AI Employee — Start script
# Starts OpenClaw gateway + all bots, then auto-opens the UI in browser.
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${C}▸${NC} $1"; }
ok()   { echo -e "${G}✓${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }

# Load env
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AI_HOME/.env"
  set +a
fi

echo ""
echo -e "${G}╔══════════════════════════════════════╗${NC}"
echo -e "${G}║       🚀 AI Employee Starting         ║${NC}"
echo -e "${G}╚══════════════════════════════════════╝${NC}"
echo ""

# ── OpenClaw gateway ───────────────────────────────────────────────────────────
log "Starting OpenClaw gateway..."
if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$AI_HOME/config.json}"
  export OPENCLAW_CONFIG
  nohup openclaw gateway \
    --config "$OPENCLAW_CONFIG" \
    >> "$AI_HOME/logs/gateway.log" 2>&1 &
  GATEWAY_PID=$!
  echo "$GATEWAY_PID" > "$AI_HOME/run/gateway.pid"
  sleep 2
  ok "OpenClaw gateway started (pid=$GATEWAY_PID)"
else
  warn "openclaw not found — gateway not started. Run: curl -fsSL https://openclaw.ai/install.sh | bash"
fi

# ── Dashboard (static) ────────────────────────────────────────────────────────
log "Starting dashboard on port $DASHBOARD_PORT..."
if [[ -f "$AI_HOME/ui/index.html" ]]; then
  cd "$AI_HOME/ui"
  nohup python3 -m http.server "$DASHBOARD_PORT" --bind 127.0.0.1 \
    >> "$AI_HOME/logs/dashboard.log" 2>&1 &
  echo $! > "$AI_HOME/run/dashboard.pid"
  cd - >/dev/null
  ok "Dashboard started (http://localhost:$DASHBOARD_PORT)"
fi

# ── Background bots ───────────────────────────────────────────────────────────
log "Starting bots..."
"$AI_HOME/bin/ai-employee" start --all || warn "Some bots failed to start (check logs)"

sleep 1

echo ""
ok "AI Employee started!"
echo ""
echo -e "  ${C}📊 Dashboard:${NC}     http://localhost:$DASHBOARD_PORT"
echo -e "  ${C}🛠️  Problem Solver:${NC} http://127.0.0.1:$UI_PORT"
echo -e "  ${C}🔧 Gateway:${NC}       http://localhost:18789"
echo ""
echo -e "${Y}WhatsApp: run 'openclaw channels login' in a new terminal to link your phone.${NC}"
echo ""

# ── Auto-open UI ──────────────────────────────────────────────────────────────
open_url() {
  local url="$1"
  if grep -qi microsoft /proc/version 2>/dev/null; then
    # WSL
    powershell.exe start "$url" 2>/dev/null || \
    sensible-browser "$url" 2>/dev/null || \
    echo "  → Open manually: $url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" 2>/dev/null &
  elif command -v open >/dev/null 2>&1; then
    open "$url"
  else
    echo "  → Open manually: $url"
  fi
}

log "Opening UI in browser..."
sleep 1
if [[ -n "${UI_PORT:-}" ]] && [[ "$UI_PORT" =~ ^[0-9]+$ ]]; then
  open_url "http://127.0.0.1:$UI_PORT"
else
  echo "  → Open manually: http://127.0.0.1:${UI_PORT:-8787}"
fi

# ── Keep alive ────────────────────────────────────────────────────────────────
echo -e "${Y}Press Ctrl+C to stop all services.${NC}"
echo ""

cleanup() {
  echo ""
  log "Stopping services..."
  "$AI_HOME/bin/ai-employee" stop --all >/dev/null 2>&1 || true
  [[ -f "$AI_HOME/run/gateway.pid" ]] && kill "$(cat "$AI_HOME/run/gateway.pid")" 2>/dev/null || true
  [[ -f "$AI_HOME/run/dashboard.pid" ]] && kill "$(cat "$AI_HOME/run/dashboard.pid")" 2>/dev/null || true
  rm -f "$AI_HOME/run/gateway.pid" "$AI_HOME/run/dashboard.pid"
  ok "All services stopped."
}

trap cleanup EXIT INT TERM
wait
