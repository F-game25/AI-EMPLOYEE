#!/usr/bin/env bash
set -e

AI_HOME="${AI_HOME:-/app}"
PORT="${PORT:-8787}"
PYTHON_PORT="${PYTHON_BACKEND_PORT:-18790}"

echo "[entrypoint] Starting Python AI backend on :${PYTHON_PORT}..."
python3 -m uvicorn \
  "runtime.agents.problem-solver-ui.server:app" \
  --host 127.0.0.1 \
  --port "${PYTHON_PORT}" \
  --log-level info &
PYTHON_PID=$!

echo "[entrypoint] Waiting for Python backend to be ready..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PYTHON_PORT}/health" >/dev/null 2>&1; then
    echo "[entrypoint] Python backend ready."
    break
  fi
  sleep 1
done

echo "[entrypoint] Starting Node.js server on :${PORT}..."
exec node backend/server.js
