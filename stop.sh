#!/usr/bin/env bash
# AI Employee — enterprise stop script
# Kills every AI Employee process regardless of which start script launched it.

REPO_ROOT="$(cd "$(dirname "$0")" && pwd -P)"
AI_HOME="${AI_EMPLOYEE_HOME:-${AI_HOME:-$HOME/.ai-employee}}"
APP_RUN_DIR="${RUN_DIR:-$AI_HOME/run}"

G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'; NC='\033[0m'
log() { echo -e "${C}▸${NC} $*"; }
ok()  { echo -e "${G}✓${NC} $*"; }
warn(){ echo -e "${Y}⚠${NC} $*"; }

_pid_belongs_to_this_app() {
  local pid="$1"
  local cwd cmd
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
  if [[ -n "$cwd" && ( "$cwd" == "$REPO_ROOT" || "$cwd" == "$AI_HOME"* ) ]]; then
    return 0
  fi
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *"$REPO_ROOT"* || "$cmd" == *"$AI_HOME"* ]]
}

_kill_pid() {
  local pid="$1" label="$2"
  [[ -z "$pid" ]] && return 0
  kill -0 "$pid" 2>/dev/null || return 0
  if ! _pid_belongs_to_this_app "$pid"; then
    warn "Skipping $label pid $pid because it does not belong to $REPO_ROOT or $AI_HOME"
    return 0
  fi
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

_kill_repo_processes() {
  local pattern="$1" label="$2"
  command -v pgrep >/dev/null 2>&1 || return 0
  local pid cwd
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$cwd" == "$REPO_ROOT" ]] || continue
    _kill_pid "$pid" "$label"
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
}

log "Stopping AI Employee (all processes)…"

# ── Kill by pid files (repo) ──────────────────────────────────────────────────
_kill_pid_file "$REPO_ROOT/python-backend.pid" "Python AI backend (repo)"
_kill_pid_file "$REPO_ROOT/backend.pid"        "Node.js server (repo)"
_kill_pid_file "$REPO_ROOT/worker.pid"         "Worker (repo)"

# ── Kill by pid files (deployed ~/.ai-employee) ───────────────────────────────
_kill_pid_file "$APP_RUN_DIR/gateway.pid"        "Gateway (app data)"
_kill_pid_file "$APP_RUN_DIR/dashboard.pid"      "Dashboard (app data)"
_kill_pid_file "$APP_RUN_DIR/backend.pid"        "Node.js (app data)"
_kill_pid_file "$APP_RUN_DIR/python.pid"         "Python backend (app data)"
_kill_pid_file "$APP_RUN_DIR/python-backend.pid" "Python AI backend (app data)"

# ── Repo-scoped pattern sweep — catches local processes with matching cwd only.
_kill_repo_processes "node .*backend/server.js|node backend/server.js" "Node.js server (repo cwd)"
_kill_repo_processes "python.*problem-solver-ui/server.py|problem-solver-ui/server.py" "Python AI backend (repo cwd)"

# ── Clean up stale pid files ──────────────────────────────────────────────────
rm -f "$APP_RUN_DIR/"*.pid 2>/dev/null || true

ok "AI Employee stopped."
