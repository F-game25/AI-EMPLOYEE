#!/usr/bin/env bash
# AI Employee — Start script
# Starts the AI Employee internal gateway + UI agent, then all remaining agents,
# then opens the browser.
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

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${C}▸${NC} $1"; }
ok()   { echo -e "${G}✓${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }

_add_to_path_if_dir() {
  local d="$1"
  [[ -d "$d" ]] || return 0
  [[ ":$PATH:" == *":$d:"* ]] || PATH="$d:$PATH"
}

_bootstrap_runtime_path() {
  _add_to_path_if_dir "$HOME/.local/bin"
  _add_to_path_if_dir "$HOME/.npm-global/bin"
  if command -v npm >/dev/null 2>&1; then
    local npm_prefix npm_bin
    npm_prefix="$(npm config get prefix 2>/dev/null || true)"
    npm_bin="${npm_prefix:+$npm_prefix/bin}"
    [[ -n "$npm_bin" ]] && _add_to_path_if_dir "$npm_bin"
  fi
  export PATH
}

_env_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|y|Y|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

install_docker_if_enabled() {
  command -v docker >/dev/null 2>&1 && return 0
  _env_true "${AI_EMPLOYEE_AUTO_INSTALL_DOCKER:-0}" || return 0
  log "Docker missing, auto-install enabled. Installing for sandbox safety..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y docker.io || warn "Docker install failed via apt"
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y docker || warn "Docker install failed via dnf"
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm docker || warn "Docker install failed via pacman"
  else
    warn "No supported package manager found for Docker auto-install"
  fi
  if command -v systemctl >/dev/null 2>&1 && command -v docker >/dev/null 2>&1; then
    sudo systemctl enable --now docker 2>/dev/null || true
  fi
}

# Load env
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AI_HOME/.env"
  set +a
fi
# Re-read ports (they may be in .env)
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-$UI_PORT}"
_bootstrap_runtime_path

# Keep gateway token consistent between config.json and .env.
if [[ -f "$AI_HOME/config.json" ]] && command -v python3 >/dev/null 2>&1; then
  CFG_GATEWAY_TOKEN="$(python3 - <<'PY' 2>/dev/null
import json
from pathlib import Path
cfg = Path.home()/'.ai-employee'/'config.json'
try:
    data = json.loads(cfg.read_text())
    print(data.get('gateway', {}).get('auth', {}).get('token', ''))
except Exception:
    print('')
PY
)"
  if [[ -n "${CFG_GATEWAY_TOKEN:-}" ]] && [[ "${AI_EMPLOYEE_GATEWAY_TOKEN:-}" != "$CFG_GATEWAY_TOKEN" ]]; then
    export AI_EMPLOYEE_GATEWAY_TOKEN="$CFG_GATEWAY_TOKEN"
    if [[ -f "$AI_HOME/.env" ]]; then
      if grep -q '^AI_EMPLOYEE_GATEWAY_TOKEN=' "$AI_HOME/.env"; then
        sed -i.bak "s|^AI_EMPLOYEE_GATEWAY_TOKEN=.*|AI_EMPLOYEE_GATEWAY_TOKEN=$CFG_GATEWAY_TOKEN|" "$AI_HOME/.env"
        rm -f "$AI_HOME/.env.bak"
      else
        echo "AI_EMPLOYEE_GATEWAY_TOKEN=$CFG_GATEWAY_TOKEN" >> "$AI_HOME/.env"
      fi
    fi
    ok "Gateway token synchronized from config.json"
  fi
fi

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

# ── JWT secret check ──────────────────────────────────────────────────────────
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

# ── Startup update check ──────────────────────────────────────────────────────
log "Checking for updates..."
_UPDATER_PY="$AI_HOME/agents/auto-updater/auto_updater.py"
if command -v python3 >/dev/null 2>&1 && [[ -f "$_UPDATER_PY" ]]; then
  python3 "$_UPDATER_PY" --once || warn "Update check failed (no internet?) — continuing with installed version."
else
  warn "Auto-updater not found — skipping update check."
fi

# ── Internal AI Employee gateway ───────────────────────────────────────────────
install_docker_if_enabled

log "Initialising AI Employee internal engine..."
# The engine layer is fully internal — no external gateway binary is started.
# All gateway functionality is provided by the engine package at runtime/engine/.
ok "AI Employee internal engine ready"

# ── Start Problem Solver UI first (critical — browser will open this) ──────────
log "Starting Problem Solver UI (port $UI_PORT)..."
if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
  "$AI_HOME/bin/ai-employee" start problem-solver-ui || warn "UI bot start returned non-zero (check logs)"
else
  # Fallback for repo-only (non-installed) environments: locate and run run.sh
  # directly so that `python main.py` and `./start.sh` work without a full install.
  _REPO_RUN_SH=""
  if [[ -n "${AI_EMPLOYEE_REPO_DIR:-}" && -x "$AI_EMPLOYEE_REPO_DIR/runtime/agents/problem-solver-ui/run.sh" ]]; then
    _REPO_RUN_SH="$AI_EMPLOYEE_REPO_DIR/runtime/agents/problem-solver-ui/run.sh"
  elif [[ -x "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agents/problem-solver-ui/run.sh" ]]; then
    _REPO_RUN_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agents/problem-solver-ui/run.sh"
  fi

  if [[ -n "$_REPO_RUN_SH" ]]; then
    log "Installed binary not found — using repo run.sh: $_REPO_RUN_SH"
    setsid bash "$_REPO_RUN_SH" >> "$AI_HOME/logs/problem-solver-ui.log" 2>&1 &
    echo $! > "$AI_HOME/run/problem-solver-ui.pid"
    ok "Problem Solver UI started from repo (pid=$!)"
  else
    warn "ai-employee binary not found at $AI_HOME/bin/ai-employee — skipping bot start."
    warn "  Re-run the installer: bash install.sh"
    warn "  Or run directly:      ./start.sh  (from repo root)"
  fi
fi

# ── Start remaining agents in background ────────────────────────────────────────
log "Starting remaining agents..."
if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
  "$AI_HOME/bin/ai-employee" start --all >> "$AI_HOME/logs/startup.log" 2>&1 || warn "Some agents failed to start (see $AI_HOME/logs/startup.log)"
fi

echo ""
ok "AI Employee started!"
echo ""
echo -e "  ${C}🛠️  Problem Solver:${NC} http://127.0.0.1:$UI_PORT"
echo -e "  ${C}🔧 Gateway:${NC}       http://localhost:18789"
echo ""
echo -e "${Y}WhatsApp (quick commands + notifications only):${NC}"
echo -e "  To link your phone, configure the WhatsApp channel in the ${C}dashboard${NC}."
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
    # stop --all excludes infra agents; stop them explicitly so UI truly goes offline
    for infra in problem-solver-ui problem-solver scheduler-runner status-reporter auto-updater discovery; do
      "$AI_HOME/bin/ai-employee" stop "$infra" >/dev/null 2>&1 || true
    done
  fi
  [[ -f "$AI_HOME/run/gateway.pid" ]] && kill "$(cat "$AI_HOME/run/gateway.pid")" 2>/dev/null || true
  rm -f "$AI_HOME/run/gateway.pid"
  ok "All services stopped."
}

trap cleanup EXIT INT TERM
wait
