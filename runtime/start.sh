#!/usr/bin/env bash
# AI Employee — Start script
# Starts OpenClaw gateway + UI bot first, then all remaining bots, then opens the browser.
set -euo pipefail

# ── Re-entrancy guard (Bug 1) ─────────────────────────────────────────────────
# Prevent an infinite loop if any bot's run.sh somehow calls start.sh again.
if [[ -n "${_AI_EMPLOYEE_START_ACTIVE:-}" ]]; then
  exit 0
fi
export _AI_EMPLOYEE_START_ACTIVE=1

# Cleanup guard — prevents double-invocation when both INT and EXIT traps fire
_AI_CLEANUP_DONE=0

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
# Re-read ports (they may be in .env)
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-$UI_PORT}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

mkdir -p "$AI_HOME/logs" "$AI_HOME/run"
chmod 700 "$AI_HOME/logs" "$AI_HOME/run" 2>/dev/null || true

# Ensure state dir exists with restricted permissions
mkdir -p "$AI_HOME/state"
chmod 700 "$AI_HOME/state" 2>/dev/null || true

# ── Port-in-use helper (Bug 4) ─────────────────────────────────────────────────
_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep -qE ":${port}([[:space:]]|$)" && return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${port}" >/dev/null 2>&1 && return 0
  fi
  return 1
}

echo ""
echo -e "${G}╔══════════════════════════════════════╗${NC}"
echo -e "${G}║       🚀 AI Employee Starting         ║${NC}"
echo -e "${G}╚══════════════════════════════════════╝${NC}"
echo ""

# ── JWT secret check (openclaw-2) ─────────────────────────────────────────────
if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  warn "JWT_SECRET_KEY is not set."
  if command -v python3 >/dev/null 2>&1; then
    JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    export JWT_SECRET_KEY
    echo "JWT_SECRET_KEY=${JWT_SECRET_KEY}" >> "$AI_HOME/.env"
    ok "JWT secret auto-generated for this session and saved to $AI_HOME/.env"
    warn "For production: rotate this key every 90 days (see SECURITY.md)"
  else
    warn "python3 not found — set JWT_SECRET_KEY manually before starting."
  fi
else
  ok "JWT_SECRET_KEY is set"
fi

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
  sleep 1
  ok "OpenClaw gateway started (pid=$GATEWAY_PID)"
else
  warn "openclaw not found — gateway not started."
  warn "  Install: curl -fsSL https://openclaw.ai/install.sh | bash"
fi

# ── Static dashboard ───────────────────────────────────────────────────────────
log "Starting dashboard on port $DASHBOARD_PORT..."
if [[ -f "$AI_HOME/ui/index.html" ]]; then
  if _port_in_use "$DASHBOARD_PORT"; then
    warn "Dashboard port $DASHBOARD_PORT already in use -- skipping (run: ai-employee doctor)"
  else
    cd "$AI_HOME/ui"
    nohup python3 -m http.server "$DASHBOARD_PORT" --bind 127.0.0.1 \
      >> "$AI_HOME/logs/dashboard.log" 2>&1 &
    echo $! > "$AI_HOME/run/dashboard.pid"
    cd - >/dev/null
    ok "Dashboard started (http://localhost:$DASHBOARD_PORT)"
  fi
fi

# ── Start Problem Solver UI first (critical — browser will open this) ──────────
log "Starting Problem Solver UI (port $UI_PORT)..."
if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
  "$AI_HOME/bin/ai-employee" start problem-solver-ui || warn "UI bot start returned non-zero (check logs)"
else
  warn "ai-employee binary not found at $AI_HOME/bin/ai-employee — skipping bot start."
  warn "  Re-run the installer: cd ~/.ai-employee && bash install.sh"
fi

# ── Start remaining bots in background ────────────────────────────────────────
log "Starting remaining bots..."
if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
  "$AI_HOME/bin/ai-employee" start --all >> "$AI_HOME/logs/startup.log" 2>&1 || warn "Some bots failed to start (see $AI_HOME/logs/startup.log)"
fi

echo ""
ok "AI Employee started!"
echo ""
echo -e "  ${C}📊 Dashboard:${NC}     http://localhost:$DASHBOARD_PORT"
echo -e "  ${C}🛠️  Problem Solver:${NC} http://127.0.0.1:$UI_PORT"
echo -e "  ${C}🔧 Gateway:${NC}       http://localhost:18789"
echo ""
echo -e "${Y}WhatsApp (quick commands + notifications only):${NC}"
echo -e "  Run ${C}openclaw channels login${NC} in a new terminal to link your phone."
echo -e "  Use WhatsApp to check status & get alerts — use the ${C}dashboard${NC} for full control."
echo ""

# ── Cross-platform browser open ───────────────────────────────────────────────
open_url() {
  local url="$1"
  # Windows (native or WSL)
  if grep -qi microsoft /proc/version 2>/dev/null; then
    powershell.exe start "$url" 2>/dev/null \
      || cmd.exe /c start "$url" 2>/dev/null \
      || sensible-browser "$url" 2>/dev/null \
      || echo "  → Open manually: $url"
  # macOS
  elif command -v open >/dev/null 2>&1; then
    open "$url" 2>/dev/null &
  # Linux with display
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" 2>/dev/null &
  else
    echo "  → Open manually: $url"
  fi
}

wait_for_ui() {
  local url="$1"
  local max="${UI_STARTUP_TIMEOUT:-30}"
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

log "Waiting for UI to be ready (up to 30s)..."
UI_URL="http://127.0.0.1:${UI_PORT}"
if wait_for_ui "$UI_URL"; then
  ok "UI is ready — opening in browser"
  open_url "$UI_URL"
else
  warn "UI did not respond in time."
  warn "  Check logs: $AI_HOME/logs/problem-solver-ui.log"
  warn "  Open manually: $UI_URL"
fi

# ── First 15 Minutes Value Flow (first install only) ─────────────────────────
if [[ ! -f "$AI_HOME/state/onboarding.json" ]]; then
  echo ""
  echo -e "${G}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${G}║   🚀 First install detected — run your first tasks!   ║${NC}"
  echo -e "${G}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  Run this to generate your first business results in 2 minutes:"
  echo ""
  echo -e "  ${C}ai-employee onboard${NC}"
  echo ""
  echo -e "  Or jump straight to a task:"
  echo -e "  ${C}ai-employee do \"find 10 leads for my business\"${NC}"
  echo ""
fi

# ── Keep alive ────────────────────────────────────────────────────────────────
echo -e "${Y}Press Ctrl+C to stop all services.${NC}"
echo ""

cleanup() {
  # Guard against double-invocation (EXIT fires after INT/TERM has already cleaned up)
  [[ "$_AI_CLEANUP_DONE" -eq 1 ]] && return 0
  _AI_CLEANUP_DONE=1
  echo ""
  log "Stopping services..."
  if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
    "$AI_HOME/bin/ai-employee" stop --all >/dev/null 2>&1 || true
  fi
  [[ -f "$AI_HOME/run/gateway.pid" ]] && kill "$(cat "$AI_HOME/run/gateway.pid")" 2>/dev/null || true
  [[ -f "$AI_HOME/run/dashboard.pid" ]] && kill "$(cat "$AI_HOME/run/dashboard.pid")" 2>/dev/null || true
  rm -f "$AI_HOME/run/gateway.pid" "$AI_HOME/run/dashboard.pid"
  ok "All services stopped."
}

trap cleanup EXIT INT TERM
wait
