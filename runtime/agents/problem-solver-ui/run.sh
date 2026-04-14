#!/usr/bin/env bash
# AI Employee — Problem Solver UI launcher (single-port unified runtime)
# Builds/serves the React UI and Node backend together on one port.
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
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

if ! command -v node >/dev/null 2>&1; then
  echo "[problem-solver-ui] ERROR: node is required for unified UI runtime."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "[problem-solver-ui] ERROR: npm is required for unified UI runtime."
  exit 1
fi
if [[ ! -f "$BACKEND_DIR/server.js" ]]; then
  echo "[problem-solver-ui] ERROR: backend/server.js not found at $BACKEND_DIR."
  exit 1
fi
if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "[problem-solver-ui] ERROR: frontend package not found at $FRONTEND_DIR."
  exit 1
fi

echo "[problem-solver-ui] Ensuring backend dependencies..."
if [[ ! -d "$BACKEND_DIR/node_modules" ]]; then
  npm --prefix "$BACKEND_DIR" install --silent
fi

echo "[problem-solver-ui] Ensuring frontend dependencies..."
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  npm --prefix "$FRONTEND_DIR" install --silent
fi

_needs_build=0
if [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
  _needs_build=1
elif find "$FRONTEND_DIR/src" -type f -newer "$FRONTEND_DIR/dist/index.html" | grep -q .; then
  _needs_build=1
fi

if [[ "$_needs_build" -eq 1 ]]; then
  echo "[problem-solver-ui] Building latest frontend bundle..."
  npm --prefix "$FRONTEND_DIR" run build
else
  echo "[problem-solver-ui] Frontend bundle is up to date."
fi

export PORT="$UI_PORT"
# Avoid self-proxy loops in Node fallback calls that use PYTHON_BACKEND_PORT.
export PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}"

echo "[problem-solver-ui] Starting unified backend+UI on http://127.0.0.1:$PORT"
exec node "$BACKEND_DIR/server.js"
