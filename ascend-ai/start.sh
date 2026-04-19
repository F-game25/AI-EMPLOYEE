#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ASCEND AI — One-command launcher (Linux / macOS)
# Installs deps, builds frontend, starts backend on port 8787,
# then opens the browser.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
PORT="${ASCEND_PORT:-8787}"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         A S C E N D   A I             ║"
echo "  ║   Autonomous Business Assistant       ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. Python dependencies ───────────────────────────────────────────
echo "[ASCEND] Installing Python dependencies..."
pip install -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || \
    pip3 install -q -r "$SCRIPT_DIR/requirements.txt"

# ── 2. Build frontend (if source exists) ─────────────────────────────
if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "[ASCEND] Building frontend..."
    cd "$FRONTEND_DIR"
    npm install --silent 2>/dev/null || true
    npm run build 2>/dev/null || true

    # Copy build output to backend/static for FastAPI to serve
    if [ -d "$FRONTEND_DIR/dist" ]; then
        rm -rf "$BACKEND_DIR/static"
        cp -r "$FRONTEND_DIR/dist" "$BACKEND_DIR/static"
        echo "[ASCEND] Frontend build copied to backend/static/"
    fi
    cd "$SCRIPT_DIR"
else
    echo "[ASCEND] No frontend source found — serving API only."
fi

# ── 3. Launch backend ────────────────────────────────────────────────
echo "[ASCEND] Starting backend on port $PORT..."
cd "$BACKEND_DIR"

# Open browser after a short delay
(sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:$PORT')" 2>/dev/null || true) &

python3 -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
