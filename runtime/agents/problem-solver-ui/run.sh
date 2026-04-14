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
if command -v readlink >/dev/null 2>&1; then
  _SCRIPT_REALPATH="$(readlink -f "$SCRIPT_SOURCE" 2>/dev/null || true)"
  [[ -n "${_SCRIPT_REALPATH:-}" ]] && SCRIPT_SOURCE="$_SCRIPT_REALPATH"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd -P)"
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
  cur="$(cd "$start" 2>/dev/null && pwd || true)"
  [[ -z "$cur" ]] && return 1
  while [[ -n "$cur" && "$cur" != "/" ]]; do
    if [[ -f "$cur/backend/server.js" && -f "$cur/frontend/package.json" ]]; then
      echo "$cur"
      return 0
    fi
    cur="$(dirname "$cur")"
  done
  return 1
}

_REPO_CAND="$(_find_repo_root "$SCRIPT_DIR/../../.." || true)"
_GITHUB_WORKSPACE_REPO=""
_PWD_REPO=""
BACKEND_DIR=""
FRONTEND_DIR=""

if [[ -n "$_REPO_CAND" ]]; then
  BACKEND_DIR="$_REPO_CAND/backend"
  FRONTEND_DIR="$_REPO_CAND/frontend"
  _info "Repo root: $_REPO_CAND"
elif [[ -n "${AI_EMPLOYEE_REPO_DIR:-}" && -f "$AI_EMPLOYEE_REPO_DIR/backend/server.js" ]]; then
  BACKEND_DIR="$AI_EMPLOYEE_REPO_DIR/backend"
  FRONTEND_DIR="$AI_EMPLOYEE_REPO_DIR/frontend"
  _info "Repo: $AI_EMPLOYEE_REPO_DIR  (AI_EMPLOYEE_REPO_DIR)"
elif [[ -n "${GITHUB_WORKSPACE:-}" ]]; then
  _GITHUB_WORKSPACE_REPO="$(_find_repo_root "$GITHUB_WORKSPACE" || true)"
  if [[ -n "$_GITHUB_WORKSPACE_REPO" ]]; then
    _REPO_CAND="$_GITHUB_WORKSPACE_REPO"
    BACKEND_DIR="$_REPO_CAND/backend"
    FRONTEND_DIR="$_REPO_CAND/frontend"
    _info "Repo: $_REPO_CAND  (GITHUB_WORKSPACE)"
  fi
fi

if [[ -z "$BACKEND_DIR" ]]; then
  _PWD_REPO="$(_find_repo_root "$PWD" || true)"
  if [[ -n "$_PWD_REPO" ]]; then
    _REPO_CAND="$_PWD_REPO"
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
_ok "Backend : $BACKEND_DIR"
_ok "Frontend: $FRONTEND_DIR"

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

_needs_build=0
if [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
  _needs_build=1
  _info "No build found — compiling from source…"
elif find "$FRONTEND_DIR/src" -type f -newer "$FRONTEND_DIR/dist/index.html" 2>/dev/null | grep -q .; then
  _needs_build=1
  _info "Source changes detected — rebuilding…"
fi

if [[ "$_needs_build" -eq 1 ]]; then
  _BUILD_LOG=$(npm --prefix "$FRONTEND_DIR" run build 2>&1)
  _BUILD_TIME=$(echo "$_BUILD_LOG" | grep -oE '\b[0-9]+(\.[0-9]+)?\s*(ms|s)\b' | tail -1 || true)
  _BUILD_SIZE=$(echo "$_BUILD_LOG" | grep -E 'kB|MB' | tail -1 | sed 's/^[[:space:]]*//' || true)
  _ok "Build complete${_BUILD_TIME:+  (${_BUILD_TIME})}"
  [[ -n "$_BUILD_SIZE" ]] && _info "$_BUILD_SIZE"
else
  _DIST_SIZE=$(du -sh "$FRONTEND_DIR/dist" 2>/dev/null | cut -f1 || echo "?")
  _ok "Bundle up to date  ($_DIST_SIZE)"
fi

# ── Step 5: Start server ───────────────────────────────────────────────────────
_step "5/5" "Starting AI Employee server..."

export PORT="$UI_PORT"
# Avoid self-proxy loops in Node fallback calls that use PYTHON_BACKEND_PORT.
export PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}"

_info "http://127.0.0.1:$PORT"
echo ""
exec node "$BACKEND_DIR/server.js"
