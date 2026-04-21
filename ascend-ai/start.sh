#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ASCEND AI — One-command launcher (Linux / macOS)
# Intentionally does NOT use 'set -e' so that a failed npm build or pip
# install does not prevent the backend API from starting.
# ─────────────────────────────────────────────────────────────────────

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
if ! python3 --version; then
    echo "❌ Python 3.10+ required"; exit 1
fi
cd "$SCRIPT_DIR/backend"
if ! pip3 install -r ../requirements.txt -q; then
    echo "⚠️  Some Python packages failed to install — continuing anyway."
fi
cd "$SCRIPT_DIR"

# ── 2. Build frontend (if source exists) ─────────────────────────────
if [ -d "$SCRIPT_DIR/frontend" ] && [ -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo "[ASCEND] Building frontend..."
    cd "$SCRIPT_DIR/frontend"
    if [ ! -d "node_modules" ]; then
        if ! npm install; then
            echo "⚠️  npm install failed — skipping frontend build."
            cd "$SCRIPT_DIR"
        else
            cd "$SCRIPT_DIR/frontend"
        fi
    fi
    if [ -d "node_modules" ]; then
        if ! npm run build; then
            echo "⚠️  Frontend build failed — the API will still run. UI may be unavailable."
        fi
    fi
    cd "$SCRIPT_DIR"
fi

# ── 3. Launch backend ────────────────────────────────────────────────
echo "[ASCEND] Starting backend on port $PORT..."
cd "$SCRIPT_DIR/backend" && python3 main.py &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait for backend to be ready
echo "[ASCEND] Waiting for backend to become ready..."
_READY=0
for i in $(seq 1 30); do
    if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
        _READY=1
        break
    fi
    sleep 1
done

if [ "$_READY" -eq 1 ]; then
    echo "✅ ASCEND AI ready at http://localhost:$PORT"
else
    echo "⚠️  Backend health check timed out — check logs above for startup errors."
fi

# Open browser
command -v xdg-open &>/dev/null && xdg-open "http://localhost:$PORT" \
    || open "http://localhost:$PORT" 2>/dev/null || true

echo "ASCEND AI running at http://localhost:$PORT — Ctrl+C to stop"
wait $BACKEND_PID
