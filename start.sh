#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

echo "Starting AI Employee..."

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js is required but not installed."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "❌ npm is required but not installed."
  exit 1
fi

python3 runtime/core/startup.py --preflight

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

echo "Tip: For live frontend reload during development, run: cd frontend && npm run dev (and run node backend/server.js separately)"
