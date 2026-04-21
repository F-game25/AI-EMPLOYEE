#!/usr/bin/env bash
# AI Employee — Problem Solver UI launcher (single-port unified runtime)
# Builds/serves the React UI and Node backend together on one port.
set -euo pipefail

# ── Colors & step helpers ──────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; B='\033[0;34m'; NC='\033[0m'
_ok()   { printf "       ${G}✓${NC}  %s\n" "$1"; }
_err()  { printf "       ${R}✗${NC}  %s\n" "$1" >&2; exit 1; }
_info() { printf "       ${C}▸${NC}  %s\n" "$1"; }
_step() { printf "\n  ${B}[%s]${NC}  %s\n" "$1" "$2"; }

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
_resolve_path() {
  local p="$1"
  [[ -z "${p:-}" ]] && return 1
  if command -v realpath >/dev/null 2>&1; then
    realpath "$p" 2>/dev/null && return 0
  fi
  if command -v readlink >/dev/null 2>&1; then
    readlink -f "$p" 2>/dev/null && return 0
  fi
  return 1
}
_SCRIPT_REALPATH="$(_resolve_path "$SCRIPT_SOURCE" || true)"
[[ -n "${_SCRIPT_REALPATH:-}" ]] && SCRIPT_SOURCE="$_SCRIPT_REALPATH"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

# ── Load env overrides ─────────────────────────────────────────────────────────
if [[ -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver-ui.env"
  set +a
fi
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-$UI_PORT}"

# ── Banner ─────────────────────────────────────────────────────────────────────
echo ""
printf "  ${C}╔═══════════════════════════════════════════════╗${NC}\n"
printf "  ${C}║${NC}  🤖  AI Employee — Unified Runtime           ${C}║${NC}\n"
printf "  ${C}╚═══════════════════════════════════════════════╝${NC}\n"

# ── Step 1: Locate backend & frontend ─────────────────────────────────────────
_step "1/5" "Locating backend & frontend..."

# Priority order:
# 1. SCRIPT_DIR/../../.. (running from within the cloned repo)
# 2. AI_EMPLOYEE_REPO_DIR env var (set by installer for installed copies)
# 3. GITHUB_WORKSPACE / current working directory (dev and CI)
# 4. Common clone locations (auto-detect)
_find_repo_root() {
  local start="$1"
  local cur
  [[ -z "${start:-}" ]] && return 1
  if [[ -f "$start" ]]; then
    start="$(dirname "$start")"
  fi
  cur="$(cd "$start" 2>/dev/null && pwd)" || return 1
  # Repo marker contract: backend/server.js + frontend/package.json must both exist.
  while [[ -n "$cur" && "$cur" != "/" ]]; do
    if [[ -f "$cur/backend/server.js" && -f "$cur/frontend/package.json" ]]; then
      echo "$cur"
      return 0
    fi
    cur="$(dirname "$cur")"
  done
  return 1
}

_REPO_CAND=""
if _repo="$(_find_repo_root "$SCRIPT_DIR" 2>/dev/null)"; then
  _REPO_CAND="$_repo"
fi
BACKEND_DIR=""
FRONTEND_DIR=""

if [[ -n "$_REPO_CAND" ]]; then
  export AI_EMPLOYEE_REPO_DIR="$_REPO_CAND"
  BACKEND_DIR="$_REPO_CAND/backend"
  FRONTEND_DIR="$_REPO_CAND/frontend"
  _info "Repo root: $_REPO_CAND"
elif [[ -n "${AI_EMPLOYEE_REPO_DIR:-}" && -f "$AI_EMPLOYEE_REPO_DIR/backend/server.js" ]]; then
  BACKEND_DIR="$AI_EMPLOYEE_REPO_DIR/backend"
  FRONTEND_DIR="$AI_EMPLOYEE_REPO_DIR/frontend"
  _info "Repo: $AI_EMPLOYEE_REPO_DIR  (AI_EMPLOYEE_REPO_DIR)"
elif [[ -n "${GITHUB_WORKSPACE:-}" ]]; then
  if _repo="$(_find_repo_root "$GITHUB_WORKSPACE" 2>/dev/null)"; then
    _REPO_CAND="$_repo"
    BACKEND_DIR="$_REPO_CAND/backend"
    FRONTEND_DIR="$_REPO_CAND/frontend"
    _info "Repo: $_REPO_CAND  (GITHUB_WORKSPACE)"
  fi
fi

if [[ -z "$BACKEND_DIR" ]]; then
  if _repo="$(_find_repo_root "$PWD" 2>/dev/null)"; then
    _REPO_CAND="$_repo"
    BACKEND_DIR="$_REPO_CAND/backend"
    FRONTEND_DIR="$_REPO_CAND/frontend"
    _info "Repo: $_REPO_CAND  (current directory)"
  fi
fi

if [[ -z "$BACKEND_DIR" ]]; then
  for _c in "$HOME/AI-EMPLOYEE" "$HOME/ai-employee" \
            "$HOME/code/AI-EMPLOYEE" "$HOME/projects/AI-EMPLOYEE" \
            "$HOME/Desktop/AI-EMPLOYEE"; do
    if [[ -f "$_c/backend/server.js" ]]; then
      BACKEND_DIR="$_c/backend"
      FRONTEND_DIR="$_c/frontend"
      _info "Repo: $_c  (auto-detected)"
      break
    fi
  done
fi

[[ -z "$BACKEND_DIR" ]] && _err "Cannot find backend/server.js. Set AI_EMPLOYEE_REPO_DIR in $AI_HOME/.env pointing to the repo root."
[[ ! -f "$FRONTEND_DIR/package.json" ]] && _err "Cannot find frontend/package.json at $FRONTEND_DIR"
REPO_ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
export AI_EMPLOYEE_REPO_DIR="$REPO_ROOT_DIR"
_ok "Backend : $BACKEND_DIR"
_ok "Frontend: $FRONTEND_DIR"
_info "Latest commit: $(git -C "$REPO_ROOT_DIR" log -1 --oneline 2>/dev/null || echo unknown)"
_info "Python: $(command -v python3 || echo missing)"
_info "Uvicorn: $(command -v uvicorn || echo missing)"

# ── Step 2: Runtime requirements ──────────────────────────────────────────────
_step "2/5" "Checking runtime requirements..."

command -v node >/dev/null 2>&1 || _err "node not found. Install Node.js 20+ from https://nodejs.org"
command -v npm  >/dev/null 2>&1 || _err "npm not found. Install Node.js 20+ from https://nodejs.org"
_ok "Node.js $(node -v)  /  npm $(npm -v)"

# ── Step 3: Backend dependencies ──────────────────────────────────────────────
_step "3/5" "Ensuring backend dependencies..."

if [[ ! -d "$BACKEND_DIR/node_modules" ]]; then
  _info "Installing backend packages (express, ws, cors…)"
  npm --prefix "$BACKEND_DIR" install --silent \
    || npm --prefix "$BACKEND_DIR" install
  _ok "Backend packages installed"
else
        _ok "Backend packages ready  ($(find "$BACKEND_DIR/node_modules" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ') packages)"
fi

# ── Step 4: Frontend bundle ────────────────────────────────────────────────────
_step "4/5" "Building UI bundle..."

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  _info "Installing frontend packages…"
  npm --prefix "$FRONTEND_DIR" install --silent \
    || npm --prefix "$FRONTEND_DIR" install
  _ok "Frontend packages installed"
fi

_needs_build=1
_info "Rebuilding frontend to avoid stale dist cache…"
find "$REPO_ROOT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf "$FRONTEND_DIR/dist"

if [[ "$_needs_build" -eq 1 ]]; then
  APP_VERSION="$(git -C "$REPO_ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  _BUILD_LOG=$(VITE_APP_VERSION="$APP_VERSION" npm --prefix "$FRONTEND_DIR" run build 2>&1)
  _BUILD_TIME=$(echo "$_BUILD_LOG" | grep -oE '\b[0-9]+(\.[0-9]+)?\s*(ms|s)\b' | tail -1 || true)
  _BUILD_SIZE=$(echo "$_BUILD_LOG" | grep -E 'kB|MB' | tail -1 | sed 's/^[[:space:]]*//' || true)
  _ok "Build complete${_BUILD_TIME:+  (${_BUILD_TIME})}"
  _info "Build version: ${APP_VERSION}"
  [[ -n "$_BUILD_SIZE" ]] && _info "$_BUILD_SIZE"
else
  _DIST_SIZE=$(du -sh "$FRONTEND_DIR/dist" 2>/dev/null | cut -f1 || echo "?")
  _ok "Bundle up to date  ($_DIST_SIZE)"
fi

# ── Step 5: Start server ───────────────────────────────────────────────────────
_step "5/5" "Starting AI Employee server..."

# Write version state for runtime integrity checks
mkdir -p "$REPO_ROOT_DIR/state"
_FULL_COMMIT="$(git -C "$REPO_ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
cat > "$REPO_ROOT_DIR/state/version.json" <<EOF
{
  "last_commit": "$_FULL_COMMIT",
  "last_updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "run.sh"
}
EOF

export PORT="$UI_PORT"
# Avoid self-proxy loops in Node fallback calls that use PYTHON_BACKEND_PORT.
export PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}"
# Bind explicitly to IPv4 loopback so the server is reachable via
# http://127.0.0.1:<port> regardless of the system's IPv6 configuration.
export LISTEN_HOST="${LISTEN_HOST:-0.0.0.0}"

# ── Start Python AI backend (LLM pipeline) ──────────────────────────────────
# The Node.js proxy calls http://127.0.0.1:${PYTHON_BACKEND_PORT}/api/chat to
# reach the real LLM.  Without this process running, every chat message falls
# back to keyword-matched placeholder replies.
_PYTHON_SERVER="$REPO_ROOT_DIR/runtime/agents/problem-solver-ui/server.py"
_PYTHON_PID=""
if command -v python3 >/dev/null 2>&1 && [[ -f "$_PYTHON_SERVER" ]]; then
  # Stop any stale Python backend from a previous run.
  _PY_PID_FILE="$REPO_ROOT_DIR/python-backend.pid"
  if [[ -f "$_PY_PID_FILE" ]]; then
    _OLD_PYPID="$(cat "$_PY_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${_OLD_PYPID:-}" ]] && kill -0 "$_OLD_PYPID" 2>/dev/null; then
      kill "$_OLD_PYPID" 2>/dev/null || true
      sleep 1
      kill -9 "$_OLD_PYPID" 2>/dev/null || true
    fi
    rm -f "$_PY_PID_FILE"
  fi
  _info "Starting Python AI backend on port ${PYTHON_BACKEND_PORT}…"
  mkdir -p "$REPO_ROOT_DIR/state"
  PROBLEM_SOLVER_UI_PORT="${PYTHON_BACKEND_PORT}" \
    PROBLEM_SOLVER_UI_HOST="127.0.0.1" \
    AI_EMPLOYEE_REPO_DIR="$REPO_ROOT_DIR" \
    python3 "$_PYTHON_SERVER" \
    >> "$REPO_ROOT_DIR/state/python-backend.log" 2>&1 &
  _PYTHON_PID=$!
  echo "$_PYTHON_PID" > "$_PY_PID_FILE"

  # Poll /health until Python is ready (up to 40 s).
  _PY_READY=0
  for _pj in $(seq 1 40); do
    sleep 1
    if curl -fsS --max-time 3 "http://127.0.0.1:${PYTHON_BACKEND_PORT}/health" > /dev/null 2>&1; then
      _PY_READY=1
      break
    fi
    _info "Waiting for Python AI backend… (${_pj}/40)"
  done

  if [[ "$_PY_READY" -eq 1 ]]; then
    _ok "Python AI backend ready on port ${PYTHON_BACKEND_PORT}"
  else
    printf "  ${Y}⚠${NC}  Python AI backend did not respond — LLM pipeline may be unavailable.\n"
    printf "       Check %s/state/python-backend.log for details.\n" "$REPO_ROOT_DIR"
  fi
else
  if [[ ! -f "$_PYTHON_SERVER" ]]; then
    printf "  ${Y}⚠${NC}  Python server not found at %s\n" "$_PYTHON_SERVER"
  else
    printf "  ${Y}⚠${NC}  python3 not found — LLM pipeline unavailable.\n"
  fi
fi

_info "Binding to http://${LISTEN_HOST}:$PORT"
_info "Clearing port $PORT if occupied…"
if command -v lsof >/dev/null 2>&1; then
  for _pid in $(lsof -ti ":$PORT" 2>/dev/null || true); do
    kill "$_pid" 2>/dev/null || true
    sleep 1
    kill -9 "$_pid" 2>/dev/null || true
  done
elif command -v ss >/dev/null 2>&1 && command -v fuser >/dev/null 2>&1; then
  if ss -tlnp 2>/dev/null | grep -qE ":${PORT} "; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi
fi
_info "Launching Node backend…"
echo ""
exec node "$BACKEND_DIR/server.js"
