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
# Support openclaw 2.0 (safe version): set OPENCLAW_BIN=openclaw2 in .env
# to use ~/.ai-employee/bin/openclaw2 instead of the standard openclaw binary.
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"
if [[ -x "$AI_HOME/bin/$OPENCLAW_BIN" ]]; then
  OPENCLAW_CMD="$AI_HOME/bin/$OPENCLAW_BIN"
elif command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  OPENCLAW_CMD="$OPENCLAW_BIN"
else
  OPENCLAW_CMD=""
fi

if [[ -n "$OPENCLAW_CMD" ]]; then
  OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$AI_HOME/config.json}"
  export OPENCLAW_CONFIG

  # Ensure the symlink exists so openclaw can find config by default path too
  mkdir -p "$HOME/.openclaw"
  ln -sf "$OPENCLAW_CONFIG" "$HOME/.openclaw/openclaw.json" 2>/dev/null || true

  # Verify config has gateway.mode=local before starting
  if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
    warn "No config.json found at $OPENCLAW_CONFIG"
    warn "Re-run the installer: cd ~/.ai-employee && bash install.sh"
  elif ! grep -q '"mode".*"local"\|mode.*local' "$OPENCLAW_CONFIG" 2>/dev/null; then
    warn "config.json is missing gateway.mode=local — re-run installer to fix:"
    warn "  curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash"
  fi

  nohup "$OPENCLAW_CMD" gateway \
    --config "$OPENCLAW_CONFIG" \
    >> "$AI_HOME/logs/gateway.log" 2>&1 &
  GATEWAY_PID=$!
  echo "$GATEWAY_PID" > "$AI_HOME/run/gateway.pid"
  sleep 2
  ok "OpenClaw gateway started via '$OPENCLAW_BIN' (pid=$GATEWAY_PID)"
else
  warn "openclaw not found — gateway not started. Run: curl -fsSL https://openclaw.ai/install.sh | bash"
  warn "For openclaw 2.0: place the binary at $AI_HOME/bin/openclaw2 and set OPENCLAW_BIN=openclaw2 in .env"
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

wait_for_ui() {
  local url="$1"
  local max="${UI_STARTUP_TIMEOUT:-20}"  # configurable via env var
  local i=0
  while (( i < max )); do
    if curl -sf --max-time 1 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    (( i++ )) || true
  done
  return 1
}

log "Waiting for UI to be ready..."
UI_URL="http://127.0.0.1:${UI_PORT:-8787}"
if wait_for_ui "$UI_URL"; then
  ok "UI is ready — opening in browser"
  open_url "$UI_URL"
else
  warn "UI did not respond in time — open manually: $UI_URL"
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
