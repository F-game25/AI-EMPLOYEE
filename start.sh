#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(pwd -P)"
export AI_EMPLOYEE_REPO_DIR="$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1

# ── Consistent environment setup ─────────────────────────────────────────────
# Load ~/.ai-employee/.env so that JWT_SECRET_KEY, API keys, and port overrides
# are available regardless of which entry point is used to start the system.
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
export AI_HOME
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AI_HOME/.env"
  set +a
fi
# Re-read ports in case they were set in .env
UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

# Auto-generate JWT_SECRET_KEY if it is not already set (mirrors runtime/start.sh)
if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    export JWT_SECRET_KEY
    mkdir -p "$AI_HOME"
    # Only append if the key is not already recorded in .env (avoids duplicates)
    if ! grep -q "^JWT_SECRET_KEY=" "$AI_HOME/.env" 2>/dev/null; then
      echo "JWT_SECRET_KEY=${JWT_SECRET_KEY}" >> "$AI_HOME/.env"
      echo "ℹ️  JWT secret auto-generated and saved to $AI_HOME/.env"
    fi
  fi
fi

# Bootstrap runtime PATH (same logic as runtime/start.sh)
_add_to_path_if_dir() {
  local d="$1"
  [[ -d "$d" ]] || return 0
  [[ ":$PATH:" == *":$d:"* ]] || PATH="$d:$PATH"
}
_add_to_path_if_dir "$HOME/.local/bin"
_add_to_path_if_dir "$HOME/.npm-global/bin"
if command -v npm >/dev/null 2>&1; then
  _npm_prefix="$(npm config get prefix 2>/dev/null || true)"
  [[ -n "${_npm_prefix:-}" ]] && _add_to_path_if_dir "${_npm_prefix}/bin"
fi
export PATH

echo "Starting AI Employee..."
echo "RUNNING FROM: $REPO_ROOT"
echo "LATEST COMMIT: $(git -C "$REPO_ROOT" log -1 --oneline 2>/dev/null || echo unknown)"
echo "PYTHON: $(command -v python3 || echo missing)"
echo "UVICORN: $(command -v uvicorn || echo missing)"

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

# startup.py lives at runtime/core/startup.py in the repo and at core/startup.py
# when deployed to AI_HOME via the auto-updater (runtime/ prefix is stripped).
_STARTUP_PY=""
if [[ -f "$REPO_ROOT/runtime/core/startup.py" ]]; then
  _STARTUP_PY="$REPO_ROOT/runtime/core/startup.py"
elif [[ -f "$REPO_ROOT/core/startup.py" ]]; then
  _STARTUP_PY="$REPO_ROOT/core/startup.py"
fi
if [[ -n "$_STARTUP_PY" ]]; then
  if ! python3 "$_STARTUP_PY" --preflight; then
    echo "⚠️  Preflight checks failed; see startup.py output above for details. Continuing with unified runtime startup."
  fi
fi

echo "[1/3] Ensuring backend/frontend dependencies..."
if [[ ! -f backend/package.json ]]; then
  echo "❌ backend/package.json not found in $REPO_ROOT"
  echo "   This location is missing the Node.js backend files."
  if [[ -n "${AI_EMPLOYEE_REPO_DIR:-}" ]]; then
    echo "   Re-run the installer from the repo:"
    echo "     cd ${AI_EMPLOYEE_REPO_DIR} && bash install.sh"
  else
    echo "   Re-run the installer from your cloned repository directory:"
    echo "     cd /path/to/AI-EMPLOYEE && bash install.sh"
  fi
  exit 1
fi
if [[ ! -d backend/node_modules ]]; then
  npm --prefix backend install
fi

if [[ ! -d frontend/node_modules ]]; then
  npm --prefix frontend install
fi

echo "[2/3] Building frontend..."
find "$REPO_ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf frontend/dist
APP_VERSION="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
VITE_APP_VERSION="$APP_VERSION" npm --prefix frontend run build

# Write version state for runtime integrity checks
mkdir -p "$REPO_ROOT/state"
FULL_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
cat > "$REPO_ROOT/state/version.json" <<EOF
{
  "last_commit": "$FULL_COMMIT",
  "last_updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "start.sh"
}
EOF

echo "[3/3] Starting unified runtime on port ${UI_PORT}..."
if [[ -f backend.pid ]]; then
  OLD_PID="$(cat backend.pid 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
    if kill -0 "$OLD_PID" 2>/dev/null; then
      kill -9 "$OLD_PID" 2>/dev/null || true
    fi
  fi
  rm -f backend.pid
fi
PORT="${UI_PORT}" PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}" LISTEN_HOST="${LISTEN_HOST:-0.0.0.0}" node backend/server.js &
BACKEND_PID=$!

# Poll /health until the server responds (up to 30 s).
# /health always returns 200 OK as soon as the server is listening.
# We do NOT check / (root) here because that requires a built frontend dist
# and would return 404 if the dist is somehow absent.
_BE_READY=0
for _i in $(seq 1 30); do
  sleep 1
  if curl -fsS --max-time 3 "http://127.0.0.1:${UI_PORT}/health" > /dev/null 2>&1; then
    _BE_READY=1
    break
  fi
  echo "  ⏳ Waiting for backend… (${_i}/30)"
done

if [[ "$_BE_READY" -eq 1 ]]; then
  echo "✅ System running at http://localhost:${UI_PORT}"
else
  echo "❌ Backend did not become healthy within 30 s"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

echo "$BACKEND_PID" > backend.pid
rm -f worker.pid

echo "Tip: For live frontend hot-reload, run the backend in one terminal and the Vite dev server in another:"
echo "  Terminal 1: PORT=${UI_PORT} node backend/server.js"
echo "  Terminal 2: cd frontend && npm run dev   # listens on http://127.0.0.1:5173 and proxies API to :${UI_PORT}"
