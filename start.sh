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

if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Installing backend dependencies (fastapi, uvicorn)..."
  python3 -m pip install --user fastapi "uvicorn[standard]"
fi

python3 runtime/core/startup.py --preflight

# Step 1: Backend
echo "[1/3] Starting backend..."
PYTHONPATH="runtime:${PYTHONPATH:-}" python3 -m uvicorn app.main:app --app-dir runtime/bots/problem-solver-ui --host 127.0.0.1 --port 8787 &
BACKEND_PID=$!

# Step 2: Worker pool
echo "[2/3] Starting workers..."
python3 runtime/core/worker_pool.py &
WORKER_PID=$!

# Step 3: Health check
echo "[3/3] Checking system..."
sleep 2

if curl -fsS http://127.0.0.1:8787/health > /dev/null && curl -fsS http://127.0.0.1:8787/ > /dev/null; then
  echo "✅ System running at http://localhost:8787"
else
  echo "❌ Backend failed to start"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$WORKER_PID" 2>/dev/null || true
  exit 1
fi

echo "$BACKEND_PID" > backend.pid
echo "$WORKER_PID" > worker.pid

echo "Tip: For live frontend reload during development, run: cd frontend && npm run dev"
