#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ASCEND AI — One-command launcher (Linux / macOS)
# ─────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${ASCEND_PORT:-8787}"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         A S C E N D   A I             ║"
echo "  ║   Autonomous Business Assistant       ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. Python dependencies ───────────────────────────────────────────
echo "[ASCEND] Installing Python dependencies..."
python3 --version || { echo "Python 3.10+ required"; exit 1; }
cd "$SCRIPT_DIR/backend" && pip3 install -r ../requirements.txt -q && cd "$SCRIPT_DIR"

# ── 2. Build frontend (if source exists) ─────────────────────────────
if [ -d "$SCRIPT_DIR/frontend" ] && [ -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo "[ASCEND] Building frontend..."
    cd "$SCRIPT_DIR/frontend"
    [ ! -d "node_modules" ] && npm install
    npm run build
    cd "$SCRIPT_DIR"
fi

# ── 3. Launch backend ────────────────────────────────────────────────
echo "[ASCEND] Starting backend on port $PORT..."
cd "$SCRIPT_DIR/backend" && python3 main.py &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait for backend to be ready
for i in {1..20}; do
    curl -s "http://localhost:$PORT/api/health" > /dev/null && break
    sleep 1
done

# Open browser
command -v xdg-open &>/dev/null && xdg-open "http://localhost:$PORT" \
    || open "http://localhost:$PORT" 2>/dev/null || true

echo "ASCEND AI running at http://localhost:$PORT — Ctrl+C to stop"
wait $BACKEND_PID
