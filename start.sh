#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

echo "Starting AI Employee..."

python3 runtime/core/startup.py --preflight

# Step 1: Backend
echo "[1/3] Starting backend..."
uvicorn app.main:app --app-dir runtime/bots/problem-solver-ui --host 127.0.0.1 --port 8787 &
BACKEND_PID=$!

# Step 2: Worker pool
echo "[2/3] Starting workers..."
python3 runtime/core/worker_pool.py &
WORKER_PID=$!

# Step 3: Health check
echo "[3/3] Checking system..."
sleep 2

if curl -s http://127.0.0.1:8787/health > /dev/null && curl -s http://127.0.0.1:8787/ > /dev/null; then
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
