#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "[dev] Stopping any existing server from ~/.ai-employee..."
pkill -f ".ai-employee/backend/server.js" 2>/dev/null || true
sleep 1

echo "[dev] Starting repo backend on :8787..."
PORT=8787 node backend/server.js &
BACKEND_PID=$!

echo ""
echo "[dev] ✓ Backend running at http://localhost:8787"
echo "[dev] Starting Vite dev server with HMR..."
echo "[dev] → Open http://localhost:5173 in your browser"
echo "[dev] → Every file change appears instantly (no refresh needed)"
echo "[dev] → API calls proxy automatically to backend at :8787"
echo ""

trap "echo '[dev] Shutting down...'; kill \$BACKEND_PID 2>/dev/null || true" EXIT

cd frontend && npm run dev
