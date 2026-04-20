#!/usr/bin/env bash
# bootstrap.sh — Canonical startup entry point for AI Employee
#
# This script provides a single, consistent startup sequence regardless of
# how the system is launched:
#   • ./bootstrap.sh               (direct from repo)
#   • bash /path/to/bootstrap.sh  (from installer / desktop launcher)
#   • Called by start.sh / runtime/start.sh
#
# It handles:
#   1. Working directory normalisation (always resolves to repo root)
#   2. Environment setup (.env loading, JWT generation, PATH bootstrap)
#   3. Dependency validation (node, npm, python3, ports)
#   4. Context detection (installed vs repo-only vs CI)
#   5. Unified startup (delegates to the correct launcher for context)
#
# Usage:
#   ./bootstrap.sh              — interactive start
#   ./bootstrap.sh --debug      — verbose mode (set -x)
#   ./bootstrap.sh --preflight  — run checks only, do not start
#   ./bootstrap.sh --no-wait    — start without waiting for health check

set -euo pipefail

# ── Parse flags (before anything else so --debug activates set -x early) ────
_PREFLIGHT_ONLY=0
_NO_WAIT=0
for _arg in "$@"; do
  case "$_arg" in
    --debug)       set -x; export AI_EMPLOYEE_DEBUG=1 ;;
    --preflight)   _PREFLIGHT_ONLY=1 ;;
    --no-wait)     _NO_WAIT=1 ;;
    *) ;;
  esac
done
[[ "${AI_EMPLOYEE_DEBUG:-}" == "1" ]] && set -x
_BOOTSTRAP_SOURCE="${BASH_SOURCE[0]}"
if command -v realpath >/dev/null 2>&1; then
  _BOOTSTRAP_SOURCE="$(realpath "$_BOOTSTRAP_SOURCE" 2>/dev/null || echo "$_BOOTSTRAP_SOURCE")"
elif command -v readlink >/dev/null 2>&1; then
  _BOOTSTRAP_SOURCE="$(readlink -f "$_BOOTSTRAP_SOURCE" 2>/dev/null || echo "$_BOOTSTRAP_SOURCE")"
fi
REPO_ROOT="$(cd "$(dirname "$_BOOTSTRAP_SOURCE")" && pwd -P)"
export AI_EMPLOYEE_REPO_DIR="$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1

# ── Environment setup ─────────────────────────────────────────────────────────
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
export AI_HOME

# 1. Load .env (ports, API keys, JWT, etc.)
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AI_HOME/.env"
  set +a
fi

# 2. Re-read UI port (may have been set in .env)
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

# 3. Auto-generate JWT_SECRET_KEY if missing
if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    export JWT_SECRET_KEY
    mkdir -p "$AI_HOME"
    # Only append if the key is not already recorded in .env (avoids duplicates)
    if ! grep -q "^JWT_SECRET_KEY=" "$AI_HOME/.env" 2>/dev/null; then
      echo "JWT_SECRET_KEY=${JWT_SECRET_KEY}" >> "$AI_HOME/.env"
      echo "ℹ️  JWT secret auto-generated and saved to $AI_HOME/.env"
    fi
  fi
fi

# 4. Bootstrap PATH (user-local bin dirs may not be in PATH in non-login shells)
_add_to_path_if_dir() {
  local d="$1"
  [[ -d "$d" ]] || return 0
  [[ ":$PATH:" == *":$d:"* ]] || PATH="$d:$PATH"
}
_add_to_path_if_dir "$HOME/.local/bin"
_add_to_path_if_dir "$HOME/.npm-global/bin"
if command -v npm >/dev/null 2>&1; then
  _npm_prefix="$(npm config get prefix 2>/dev/null || true)"
  [[ -n "${_npm_prefix:-}" ]] && _add_to_path_if_dir "${_npm_prefix}/bin"
fi
export PATH

# ── Context detection ─────────────────────────────────────────────────────────
_CONTEXT="terminal"
if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && [[ ! -t 0 ]]; then
  _CONTEXT="desktop"
elif [[ -n "${CI:-}${GITHUB_ACTIONS:-}${GITLAB_CI:-}" ]]; then
  _CONTEXT="ci"
elif ! [[ -t 0 ]]; then
  _CONTEXT="service"
fi
export AI_EMPLOYEE_LAUNCH_CONTEXT="$_CONTEXT"

# ── Banner ────────────────────────────────────────────────────────────────────
_G='\033[0;32m'; _Y='\033[1;33m'; _C='\033[0;36m'; _NC='\033[0m'
echo ""
echo -e "${_G}╔══════════════════════════════════════════════╗${_NC}"
echo -e "${_G}║     🚀 AI Employee — Bootstrap Startup        ║${_NC}"
echo -e "${_G}╚══════════════════════════════════════════════╝${_NC}"
echo ""
echo -e "  ${_C}Repo root :${_NC} $REPO_ROOT"
echo -e "  ${_C}AI_HOME   :${_NC} $AI_HOME"
echo -e "  ${_C}Context   :${_NC} $_CONTEXT"
echo -e "  ${_C}Port      :${_NC} $UI_PORT"
_commit="$(git -C "$REPO_ROOT" log -1 --oneline 2>/dev/null || echo unknown)"
echo -e "  ${_C}Commit    :${_NC} $_commit"
echo ""

# ── Validation layer ──────────────────────────────────────────────────────────
_errors=0

_check_cmd() {
  local cmd="$1" label="${2:-$1}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "  ${_Y}⚠${_NC}  Missing: $label"
    _errors=$(( _errors + 1 ))
  else
    echo -e "  ${_G}✓${_NC}  $label: $(command -v "$cmd")"
  fi
}

_check_file() {
  local f="$1" label="${2:-$1}"
  if [[ ! -f "$f" ]]; then
    echo -e "  ${_Y}⚠${_NC}  Missing file: $label"
    _errors=$(( _errors + 1 ))
  else
    echo -e "  ${_G}✓${_NC}  File OK: $label"
  fi
}

echo "Checking dependencies..."
_check_cmd node   "Node.js"
_check_cmd npm    "npm"
_check_cmd python3 "Python 3"
_check_file "$REPO_ROOT/backend/server.js"  "backend/server.js"
_check_file "$REPO_ROOT/frontend/package.json" "frontend/package.json"

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
if _port_in_use "$UI_PORT"; then
  echo -e "  ${_Y}⚠${_NC}  Port $UI_PORT already in use — killing existing process..."
  if command -v lsof >/dev/null 2>&1; then
    for _pid in $(lsof -ti ":$UI_PORT" 2>/dev/null || true); do
      kill "$_pid" 2>/dev/null || true
      sleep 1
      kill -9 "$_pid" 2>/dev/null || true
    done
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${UI_PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi
else
  echo -e "  ${_G}✓${_NC}  Port $UI_PORT is free"
fi

if [[ "$_errors" -gt 0 ]]; then
  echo ""
  echo -e "  ${_Y}⚠${_NC}  $_errors required component(s) missing."
  echo "  Install them and re-run:  bash install.sh"
fi

if [[ "$_PREFLIGHT_ONLY" -eq 1 ]]; then
  echo ""
  if [[ "$_errors" -eq 0 ]]; then
    echo -e "  ${_G}✓${_NC}  Preflight OK — all checks passed."
    exit 0
  else
    echo -e "  ${_Y}⚠${_NC}  Preflight complete with $_errors warning(s)."
    exit 1
  fi
fi

[[ "$_errors" -gt 0 ]] || true  # errors are warnings only; startup continues

# ── Delegate to the appropriate launcher ──────────────────────────────────────
# Prefer the installed system (ai-employee binary) when available; otherwise
# fall back to the repo's start.sh so that both installed and repo-only setups
# produce identical behaviour.
echo ""
echo "Delegating to startup launcher..."

if [[ -x "$AI_HOME/bin/ai-employee" ]]; then
  # Installed system: let the ai-employee CLI handle everything
  exec "$AI_HOME/bin/ai-employee" start problem-solver-ui
elif [[ -f "$REPO_ROOT/start.sh" ]]; then
  # Repo-only: delegate to root start.sh (which starts Node.js backend directly)
  exec bash "$REPO_ROOT/start.sh" "$@"
else
  echo "❌ Cannot find a startup launcher. Run:  bash install.sh"
  exit 1
fi
