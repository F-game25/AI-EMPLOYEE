#!/usr/bin/env bash
# AI Employee — Problem Solver UI launcher
# Auto-installs Python dependencies on every platform before starting the server.
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/problem-solver-ui"
REQ="$BOT_HOME/requirements.txt"

# ── Load config ────────────────────────────────────────────────────────────────
if [[ -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver-ui.env"
  set +a
fi

# ── Resolve python binary (python3 on Linux/macOS, python on Windows/Git Bash) ─
PYTHON=""
for _py in python3 python; do
  if command -v "$_py" >/dev/null 2>&1 && "$_py" -c "import sys; assert sys.version_info >= (3,8)" 2>/dev/null; then
    PYTHON="$_py"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "[problem-solver-ui] ERROR: Python 3.8+ not found."
  echo "  Install Python: https://www.python.org/downloads/"
  exit 1
fi

# ── Auto-install dependencies ──────────────────────────────────────────────────
_need_install=0
if ! "$PYTHON" -c "import fastapi, uvicorn" 2>/dev/null; then
  _need_install=1
fi

if [[ "$_need_install" -eq 1 ]]; then
  echo "[problem-solver-ui] Installing Python dependencies (fastapi, uvicorn)..."
  if [[ -f "$REQ" ]]; then
    "$PYTHON" -m pip install --user -q -r "$REQ" 2>&1 \
      || "$PYTHON" -m pip install --user -q fastapi "uvicorn[standard]" 2>&1 \
      || { echo "[problem-solver-ui] ERROR: pip install failed. Run: pip install fastapi uvicorn"; exit 1; }
  else
    "$PYTHON" -m pip install --user -q fastapi "uvicorn[standard]" 2>&1 \
      || { echo "[problem-solver-ui] ERROR: pip install failed. Run: pip install fastapi uvicorn"; exit 1; }
  fi
  echo "[problem-solver-ui] Dependencies installed."
fi

# ── Start server ───────────────────────────────────────────────────────────────
exec "$PYTHON" "$BOT_HOME/server.py"
