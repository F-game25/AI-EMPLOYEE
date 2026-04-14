#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

echo "Starting AI Employee..."

# ── Evolution mode prompt ─────────────────────────────────────────────────────
# Ask the operator which self-evolution mode to use, but only when:
#   • EVOLUTION_MODE has NOT already been set in the environment / .env, AND
#   • stdin is an interactive terminal (skip in CI / non-interactive pipes).
if [ -z "${EVOLUTION_MODE:-}" ] && [ -t 0 ]; then
  echo ""
  echo "┌─────────────────────────────────────────────────────┐"
  echo "│          Self-Evolution Mode Selection              │"
  echo "│                                                     │"
  echo "│  AUTO  — fully autonomous (detect, patch, deploy)  │"
  echo "│  SAFE  — generate patches; require API approval    │"
  echo "│  OFF   — disabled (default)                        │"
  echo "└─────────────────────────────────────────────────────┘"
  printf "  EVOLUTION_MODE [OFF]: "
  read -r _evo_input </dev/tty
  _evo_input="$(echo "${_evo_input}" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')"
  case "${_evo_input}" in
    AUTO|SAFE|OFF) EVOLUTION_MODE="${_evo_input}" ;;
    "")            EVOLUTION_MODE="OFF" ;;
    *)
      echo "  Unknown value '${_evo_input}'. Valid choices: AUTO, SAFE, OFF. Defaulting to OFF."
      EVOLUTION_MODE="OFF"
      ;;
  esac
  export EVOLUTION_MODE
  echo "  → Evolution mode set to: ${EVOLUTION_MODE}"
  echo ""
fi

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js is required but not installed."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "❌ npm is required but not installed."
  exit 1
fi

if ! python3 runtime/core/startup.py --preflight; then
  echo "⚠️  Preflight checks failed; see runtime/core/startup.py output above for details. Continuing with unified runtime startup."
fi

echo "[1/3] Ensuring backend/frontend dependencies..."
if [[ ! -d backend/node_modules ]]; then
  npm --prefix backend install
fi

if [[ ! -d frontend/node_modules ]]; then
  npm --prefix frontend install
fi

echo "[2/3] Building frontend..."
npm --prefix frontend run build

echo "[3/3] Starting unified runtime on port ${UI_PORT}..."
PORT="${UI_PORT}" PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}" node backend/server.js &
BACKEND_PID=$!

sleep 2
if curl -fsS "http://127.0.0.1:${UI_PORT}/health" > /dev/null && curl -fsS "http://127.0.0.1:${UI_PORT}/" > /dev/null; then
  echo "✅ System running at http://localhost:${UI_PORT}"
else
  echo "❌ Backend failed to start"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

echo "$BACKEND_PID" > backend.pid
rm -f worker.pid

echo "Tip: For live frontend reload during development, run: PORT=${UI_PORT} node backend/server.js (terminal 1), then cd frontend && npm run dev (terminal 2)"
