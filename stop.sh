#!/usr/bin/env bash
# AI Employee — enterprise stop script
# Kills every AI Employee process regardless of which start script launched it.

REPO_ROOT="$(cd "$(dirname "$0")" && pwd -P)"
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'; NC='\033[0m'
log() { echo -e "${C}▸${NC} $*"; }
ok()  { echo -e "${G}✓${NC} $*"; }
warn(){ echo -e "${Y}⚠${NC} $*"; }

_kill_pid() {
  local pid="$1" label="$2"
  [[ -z "$pid" ]] && return 0
  kill -0 "$pid" 2>/dev/null || return 0
  log "Stopping $label (pid $pid)…"
  kill "$pid" 2>/dev/null || true
  local i=0
  while kill -0 "$pid" 2>/dev/null && [[ $i -lt 20 ]]; do
    sleep 0.3; i=$((i+1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    warn "Force-killing $label…"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

_kill_pid_file() {
  local f="$1" label="$2"
  [[ -f "$f" ]] || return 0
  local pid
  pid="$(cat "$f" 2>/dev/null || true)"
  rm -f "$f"
  _kill_pid "$pid" "$label"
}

log "Stopping AI Employee (all processes)…"

# ── Kill by pid files (repo) ──────────────────────────────────────────────────
_kill_pid_file "$REPO_ROOT/python-backend.pid" "Python AI backend (repo)"
_kill_pid_file "$REPO_ROOT/backend.pid"        "Node.js server (repo)"
_kill_pid_file "$REPO_ROOT/worker.pid"         "Worker (repo)"

# ── Kill by pid files (deployed ~/.ai-employee) ───────────────────────────────
_kill_pid_file "$AI_HOME/run/gateway.pid"   "Gateway (deployed)"
_kill_pid_file "$AI_HOME/run/dashboard.pid" "Dashboard (deployed)"
_kill_pid_file "$AI_HOME/run/backend.pid"   "Node.js (deployed)"
_kill_pid_file "$AI_HOME/run/python.pid"    "Python backend (deployed)"

# ── Pattern sweep — catches everything regardless of pid files ────────────────
# This handles processes started by ~/.ai-employee/start.sh or any other path.
if command -v pkill >/dev/null 2>&1; then
  pkill -f "problem-solver-ui/server.py"    2>/dev/null || true
  pkill -f "node.*AI-EMPLOYEE.*server.js"   2>/dev/null || true
  pkill -f "node.*ai-employee.*server.js"   2>/dev/null || true
  sleep 0.5
  # Force-kill stragglers
  pkill -9 -f "problem-solver-ui/server.py" 2>/dev/null || true
  pkill -9 -f "node.*AI-EMPLOYEE.*server.js" 2>/dev/null || true
  pkill -9 -f "node.*ai-employee.*server.js" 2>/dev/null || true
fi

# ── Clean up stale pid files ──────────────────────────────────────────────────
rm -f "$AI_HOME/run/"*.pid 2>/dev/null || true

ok "AI Employee stopped."
