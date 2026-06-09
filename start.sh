#!/usr/bin/env bash
# AI Employee — enterprise start script (single source of truth)
# Always run from the repo: bash /path/to/AI-EMPLOYEE/start.sh

set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(pwd -P)"
export AI_EMPLOYEE_REPO_DIR="$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1

G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'; R='\033[0;31m'; NC='\033[0m'
_log()  { echo -e "${C}▸${NC} $*"; }
_ok()   { echo -e "${G}✓${NC} $*"; }
_warn() { echo -e "${Y}⚠${NC} $*"; }

_rotate_log_if_large() {
  local file="$1"
  local max_bytes="${2:-26214400}"
  [[ -f "$file" ]] || return 0
  local size
  size="$(stat -c '%s' "$file" 2>/dev/null || echo 0)"
  [[ "$size" =~ ^[0-9]+$ ]] || size=0
  if (( size > max_bytes )); then
    local stamp rotated
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    rotated="${file}.${stamp}.1.log"
    if mv -n "$file" "$rotated"; then
      : > "$file"
      _warn "Rotated large log: $file → $rotated"
    else
      _warn "Could not rotate large log: $file"
    fi
  fi
}

echo ""
echo -e "${G}╔══════════════════════════════════════╗${NC}"
echo -e "${G}║        AI Employee — Starting        ║${NC}"
echo -e "${G}╚══════════════════════════════════════╝${NC}"
echo ""
_log "Repo: $REPO_ROOT"

# ── Consistent environment setup ─────────────────────────────────────────────
# AI_EMPLOYEE_HOME is the packaged-app/user-data location. AI_HOME is kept as
# the runtime-compatible alias used by Python agents and older scripts.
AI_HOME="${AI_EMPLOYEE_HOME:-${AI_HOME:-$HOME/.ai-employee}}"
export AI_HOME
export AI_EMPLOYEE_HOME="$AI_HOME"
APP_STATE_DIR="${STATE_DIR:-$AI_HOME/state}"
APP_LOG_DIR="${LOG_DIR:-$AI_HOME/logs}"
APP_RUN_DIR="${RUN_DIR:-$AI_HOME/run}"
export STATE_DIR="$APP_STATE_DIR"
export LOG_DIR="$APP_LOG_DIR"
export RUN_DIR="$APP_RUN_DIR"
export AI_EMPLOYEE_OFFLINE="${AI_EMPLOYEE_OFFLINE:-1}"
if [[ -d "$REPO_ROOT/runtime/browsers/playwright" ]]; then
  export PLAYWRIGHT_BROWSERS_PATH="$REPO_ROOT/runtime/browsers/playwright"
fi
mkdir -p "$APP_STATE_DIR" "$APP_LOG_DIR" "$APP_RUN_DIR"
_rotate_log_if_large "$APP_LOG_DIR/python-backend.log" 26214400
_rotate_log_if_large "$APP_LOG_DIR/server.log" 26214400
_rotate_log_if_large "$APP_LOG_DIR/launcher-start.log" 26214400

_SYSTEM_PYTHON="${PYTHON_BOOTSTRAP_BIN:-}"
if [[ -z "$_SYSTEM_PYTHON" ]] && command -v python3 >/dev/null 2>&1; then
  _SYSTEM_PYTHON="$(command -v python3)"
elif [[ -z "$_SYSTEM_PYTHON" ]] && command -v python >/dev/null 2>&1; then
  _SYSTEM_PYTHON="$(command -v python)"
fi

_PYTHON_CORE_BIN="$AI_HOME/python-core/bin/python"
if [[ -x "$AI_HOME/python-core/bin/python3" ]]; then
  _PYTHON_CORE_BIN="$AI_HOME/python-core/bin/python3"
fi

_BOOTSTRAP_PY="$REPO_ROOT/scripts/bootstrap_python_core.py"
if [[ ! -x "$_PYTHON_CORE_BIN" && -n "$_SYSTEM_PYTHON" && -f "$_BOOTSTRAP_PY" ]]; then
  if find "$REPO_ROOT/runtime/wheelhouse" -mindepth 2 -maxdepth 2 -type f -name "*.whl" -print -quit 2>/dev/null | grep -q .; then
    _log "Building local Python core venv from bundled wheelhouse…"
    if ! "$_SYSTEM_PYTHON" "$_BOOTSTRAP_PY" --quiet; then
      echo "❌ Failed to build local Python core venv from bundled wheelhouse."
      exit 1
    fi
  fi
fi

if [[ -x "$_PYTHON_CORE_BIN" ]]; then
  export PYTHON_BIN="$_PYTHON_CORE_BIN"
elif [[ -n "$_SYSTEM_PYTHON" ]]; then
  export PYTHON_BIN="$_SYSTEM_PYTHON"
fi

# ── Stop any already-running AI Employee processes ───────────────────────────
# Ensures a clean state before starting, regardless of which start script
# was used previously (repo or deployed copy).
if [[ -f "$REPO_ROOT/stop.sh" ]]; then
  # Only run stop.sh if AI Employee processes are actually running — avoids
  # the unconditional 1 s sleep on every clean (re)start.
  _RUNNING_PIDS=$(pgrep -f "backend/server.js" 2>/dev/null || true)
  if [[ -n "$_RUNNING_PIDS" ]]; then
    _log "Stopping existing AI Employee processes…"
    bash "$REPO_ROOT/stop.sh" 2>/dev/null || true
    sleep 1
  fi
fi

# Load ~/.ai-employee/.env so that JWT_SECRET_KEY, API keys, and port overrides
# are available regardless of which entry point is used to start the system.
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
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    JWT_SECRET_KEY="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(32))')"
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
if [[ "${AI_EMPLOYEE_PACKAGED:-0}" != "1" ]] && command -v npm >/dev/null 2>&1; then
  _npm_prefix="$(npm config get prefix 2>/dev/null || true)"
  [[ -n "${_npm_prefix:-}" ]] && _add_to_path_if_dir "${_npm_prefix}/bin"
fi
export PATH

echo "Starting AI Employee..."
echo "RUNNING FROM: $REPO_ROOT"
echo "LATEST COMMIT: $(git -C "$REPO_ROOT" log -1 --oneline 2>/dev/null || echo unknown)"
echo "PYTHON: ${PYTHON_BIN:-missing}"
echo "UVICORN: $(command -v uvicorn || echo missing)"

# Evolution mode defaults to OFF unless already set in environment / .env
export EVOLUTION_MODE="${EVOLUTION_MODE:-OFF}"

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

_NODE_BIN="${NODE_BIN:-}"
if [[ -z "$_NODE_BIN" ]] && command -v node >/dev/null 2>&1; then
  _NODE_BIN="$(command -v node)"
fi
if [[ -z "$_NODE_BIN" || ! -x "$_NODE_BIN" ]]; then
  echo "❌ Node runtime is required but not available."
  exit 1
fi
export NODE_BIN="$_NODE_BIN"

if [[ "${AI_EMPLOYEE_PACKAGED:-0}" != "1" ]] && ! command -v npm >/dev/null 2>&1; then
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
  if [[ -z "${PYTHON_BIN:-}" ]]; then
    echo "❌ Python runtime is missing."
    exit 1
  fi
  if ! "$PYTHON_BIN" "$_STARTUP_PY" --preflight; then
    echo "❌ Enterprise preflight failed; see startup.py output above for details."
    echo "❌ Core runtime dependencies must be bundled locally and cannot be downloaded on first boot."
    exit 1
  fi
fi

# ── [0/3] Pre-flight: check and apply any pending git updates ─────────────────
_UPDATER_SCRIPT=""
for _up in "$REPO_ROOT/runtime/agents/auto-updater/auto_updater.py" "$HOME/.ai-employee/agents/auto-updater/auto_updater.py"; do
  [[ -f "$_up" ]] && _UPDATER_SCRIPT="$_up" && break
done
if [[ -n "$_UPDATER_SCRIPT" && "${AI_EMPLOYEE_ALLOW_AUTO_UPDATE:-0}" == "1" && "${AI_EMPLOYEE_OFFLINE:-1}" != "1" ]]; then
  echo "[0/3] Checking for system updates..."
  "$PYTHON_BIN" "$_UPDATER_SCRIPT" --once 2>&1 | sed 's/^/  [update] /' || true
  echo "[0/3] Update check complete"
elif [[ -n "$_UPDATER_SCRIPT" ]]; then
  echo "[0/3] Update check skipped (offline-first policy)"
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
  if [[ "${AI_EMPLOYEE_PACKAGED:-0}" == "1" ]]; then
    echo "❌ backend/node_modules is missing from packaged resources."
    exit 1
  fi
  if [[ "${AI_EMPLOYEE_OFFLINE:-1}" == "1" ]]; then
    echo "❌ backend/node_modules is missing and offline mode is enabled."
    echo "   Rebuild the downloadable app with bundled dependencies, or set AI_EMPLOYEE_OFFLINE=0 for development installs."
    exit 1
  fi
  npm --prefix backend install
fi

if [[ ! -d frontend/node_modules ]] && [[ "${AI_EMPLOYEE_PACKAGED:-0}" != "1" ]]; then
  if [[ "${AI_EMPLOYEE_OFFLINE:-1}" == "1" ]]; then
    echo "❌ frontend/node_modules is missing and offline mode is enabled."
    echo "   Rebuild the downloadable app with bundled dependencies, or set AI_EMPLOYEE_OFFLINE=0 for development installs."
    exit 1
  fi
  npm --prefix frontend install
fi

echo "[2/3] Building frontend (checking cache)..."
if [[ "${AI_EMPLOYEE_PACKAGED:-0}" != "1" ]]; then
  echo "✓ Preserving Python cache files (non-destructive startup policy)"
fi

# ── Build cache: only rebuild if source changed ───────────────────────────────
_CACHE_FILE="$REPO_ROOT/frontend/dist/.build-hash"

if [[ "${AI_EMPLOYEE_PACKAGED:-0}" == "1" ]]; then
  if [[ -f "$REPO_ROOT/frontend/dist/index.html" ]]; then
    echo "✓ Packaged frontend bundle present"
  else
    echo "❌ Packaged frontend bundle missing at frontend/dist/index.html"
    exit 1
  fi
else
  # Fast cache check: stat mtime+size of the src/ dir + key config files only.
  # Walking every file with find takes 200ms+ on large trees; this takes <5ms.
  _NEW_HASH=$(
    {
      stat -c '%Y %s' "$REPO_ROOT/frontend/src" 2>/dev/null
      stat -c '%Y %s' "$REPO_ROOT/frontend/package.json" "$REPO_ROOT/frontend/vite.config.js" "$REPO_ROOT/frontend/index.html" 2>/dev/null
    } | sha256sum | cut -d' ' -f1
  )
  _OLD_HASH=$(cat "$_CACHE_FILE" 2>/dev/null || echo "")
  if [[ "$_NEW_HASH" == "$_OLD_HASH" ]] && [[ -f "$REPO_ROOT/frontend/dist/index.html" ]]; then
    echo "✓ Frontend cache hit (no rebuild needed)"
  else
  echo "⚠ Frontend source changed (rebuilding)..."
  APP_VERSION="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  if ! VITE_APP_VERSION="$APP_VERSION" npm --prefix frontend run build -- --emptyOutDir=false; then
    echo "⚠️  Frontend build failed — backend API will still start. Check npm/Vite errors above."
    echo "   Tip: run 'cd frontend && npm install && npm run build' manually to diagnose."
  else
    mkdir -p "$REPO_ROOT/frontend/dist"
    echo "$_NEW_HASH" > "$_CACHE_FILE"
  fi
  fi
fi

# Write version state for runtime integrity checks
mkdir -p "$APP_STATE_DIR"
FULL_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
cat > "$APP_STATE_DIR/version.json" <<EOF
{
  "last_commit": "$FULL_COMMIT",
  "last_updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source": "start.sh"
}
EOF

_PYTHON_BACKEND_PORT="${PYTHON_BACKEND_PORT:-18790}"

# ── [2/3] Ensure Ollama is running (managed local AI) ───────────────────────
_OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
_OLLAMA_MODELS="${OLLAMA_MODELS:-$AI_HOME/models/ollama}"
export OLLAMA_HOST="$_OLLAMA_HOST"
export OLLAMA_MODELS="$_OLLAMA_MODELS"
export OLLAMA_NO_CLOUD="${OLLAMA_NO_CLOUD:-1}"
mkdir -p "$_OLLAMA_MODELS"

_OLLAMA_BIN="${OLLAMA_BIN:-}"
if [[ -z "$_OLLAMA_BIN" && -x "$REPO_ROOT/runtime/vendor/ollama/ollama" ]]; then
  _OLLAMA_BIN="$REPO_ROOT/runtime/vendor/ollama/ollama"
elif [[ -z "$_OLLAMA_BIN" && -x "$REPO_ROOT/runtime/vendor/ollama/bin/ollama" ]]; then
  _OLLAMA_BIN="$REPO_ROOT/runtime/vendor/ollama/bin/ollama"
elif [[ -z "$_OLLAMA_BIN" ]] && command -v ollama > /dev/null 2>&1; then
  _OLLAMA_BIN="$(command -v ollama)"
fi

_OLLAMA_LIBRARY_PATH=""
if [[ -d "$REPO_ROOT/runtime/vendor/ollama/lib" ]]; then
  _OLLAMA_LIBRARY_PATH="$REPO_ROOT/runtime/vendor/ollama/lib"
fi
if [[ -d "/usr/local/lib/ollama" ]]; then
  _OLLAMA_LIBRARY_PATH="${_OLLAMA_LIBRARY_PATH:+$_OLLAMA_LIBRARY_PATH:}/usr/local/lib/ollama"
fi
if [[ -n "$_OLLAMA_LIBRARY_PATH" ]]; then
  export OLLAMA_LIBRARY_PATH="$_OLLAMA_LIBRARY_PATH"
  export LD_LIBRARY_PATH="$_OLLAMA_LIBRARY_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

_ollama_running() { curl -fsS --max-time 2 "${_OLLAMA_HOST}/api/tags" > /dev/null 2>&1; }
if [[ -n "$_OLLAMA_BIN" && -x "$_OLLAMA_BIN" ]]; then
  if _ollama_running; then
    _ok "Ollama already running at ${_OLLAMA_HOST}"
  else
    _log "Starting managed Ollama..."
    _OLLAMA_PID_FILE="$APP_RUN_DIR/ollama.pid"
    nohup env OLLAMA_HOST="$_OLLAMA_HOST" OLLAMA_MODELS="$_OLLAMA_MODELS" OLLAMA_LIBRARY_PATH="${OLLAMA_LIBRARY_PATH:-}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" OLLAMA_NO_CLOUD="$OLLAMA_NO_CLOUD" "$_OLLAMA_BIN" serve >> "$APP_LOG_DIR/ollama.log" 2>&1 </dev/null &
    echo "$!" > "$_OLLAMA_PID_FILE"
    for _oi in $(seq 1 20); do
      sleep 0.5
      if _ollama_running; then
        _ok "Ollama ready at ${_OLLAMA_HOST}"
        _ok "Ollama model storage: ${_OLLAMA_MODELS}"
        break
      fi
    done
    if ! _ollama_running; then
      _warn "Ollama did not respond within 10 s — local chat will remain unavailable until it starts"
      _warn "  Log: $APP_LOG_DIR/ollama.log"
    fi
  fi
else
  _warn "Packaged Ollama runtime missing — local AI unavailable until runtime/vendor/ollama/ollama is bundled."
  _warn "  Model storage is reserved at: ${_OLLAMA_MODELS}"
fi

# ── [2.5/3] Start Python AI backend (LLM pipeline) ───────────────────────────
# The Node.js frontend proxy calls http://127.0.0.1:${_PYTHON_BACKEND_PORT}/api/chat
# to reach the real LLM pipeline.  Without this process, every chat message
# falls back to keyword-matched placeholder replies.
PYTHON_PID=""
_PYTHON_SERVER="$REPO_ROOT/runtime/agents/problem-solver-ui/server.py"
if [[ -n "${PYTHON_BIN:-}" && -f "$_PYTHON_SERVER" ]]; then
  # Stop any stale Python backend from a previous run.
  _PY_PID_FILE="$APP_RUN_DIR/python-backend.pid"
  if [[ -f "$_PY_PID_FILE" ]]; then
    _OLD_PYPID="$(cat "$_PY_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${_OLD_PYPID:-}" ]] && kill -0 "$_OLD_PYPID" 2>/dev/null; then
      kill "$_OLD_PYPID" 2>/dev/null || true
      sleep 1
      kill -9 "$_OLD_PYPID" 2>/dev/null || true
    fi
    rm -f "$_PY_PID_FILE"
  fi
  # Best-effort local Neo4j for the neural-brain graph (no-op if Docker absent;
  # native SQLite graph is the always-on floor either way).
  if [[ -f "$REPO_ROOT/scripts/neo4j.sh" ]]; then
    bash "$REPO_ROOT/scripts/neo4j.sh" 2>&1 | sed 's/^/  /' || true
  fi

  echo "[2.5/3] Starting Python AI backend on port ${_PYTHON_BACKEND_PORT}..."
  # Prefer the venv created by bootstrap.js (PEP 668 systems need this)
  _PY_BIN="$PYTHON_BIN"
  PROBLEM_SOLVER_UI_PORT="${_PYTHON_BACKEND_PORT}" \
    PROBLEM_SOLVER_UI_HOST="127.0.0.1" \
    AI_EMPLOYEE_REPO_DIR="$REPO_ROOT" \
    nohup "$_PY_BIN" "$_PYTHON_SERVER" \
    >> "$APP_LOG_DIR/python-backend.log" 2>&1 </dev/null &
  PYTHON_PID=$!
  echo "$PYTHON_PID" > "$_PY_PID_FILE"

  # Don't block here — the launcher's waitForPythonPort probe handles detection.
  # A brief background check gives a log confirmation without delaying Node startup.
  (
    for _pi in $(seq 1 20); do
      sleep 0.5
      if curl -fsS --max-time 1 "http://127.0.0.1:${_PYTHON_BACKEND_PORT}/health" > /dev/null 2>&1; then
        echo "✅ Python AI backend ready on port ${_PYTHON_BACKEND_PORT}"
        # Mirror the native graph into Neo4j (idempotent; no-op if Neo4j down).
        PYTHONPATH="$REPO_ROOT/runtime" "$PYTHON_BIN" -m neural_brain.graph.sync_native_to_neo4j \
          >> "$APP_LOG_DIR/python-backend.log" 2>&1 || true
        # Pre-warm Ollama model so first chat message is instant
        _WARM_MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
        _OLLAMA_WARM_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
        curl -s --max-time 60 -X POST "${_OLLAMA_WARM_HOST}/api/generate" \
          -H "Content-Type: application/json" \
          -d "{\"model\":\"${_WARM_MODEL}\",\"prompt\":\"hi\",\"stream\":false}" \
          > /dev/null 2>&1 &
        echo "  [warm-up] Loading ${_WARM_MODEL} into VRAM in background..."
        exit 0
      fi
    done
    echo "⚠️  Python AI backend did not respond within 10 s — check $APP_LOG_DIR/python-backend.log"
  ) &
else
  if [[ ! -f "$_PYTHON_SERVER" ]]; then
    echo "⚠️  Python AI backend not found at $_PYTHON_SERVER — LLM pipeline unavailable."
  else
    echo "⚠️  python3 not found — LLM pipeline unavailable."
  fi
fi

echo "[3/3] Starting unified runtime on port ${UI_PORT}..."
_BACKEND_PID_FILE="$APP_RUN_DIR/backend.pid"
if [[ -f "$_BACKEND_PID_FILE" ]]; then
  OLD_PID="$(cat "$_BACKEND_PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
    if kill -0 "$OLD_PID" 2>/dev/null; then
      kill -9 "$OLD_PID" 2>/dev/null || true
    fi
  fi
  rm -f "$_BACKEND_PID_FILE"
fi
_BACKEND_ENV=(
  env
  "PORT=${UI_PORT}"
  "PYTHON_BACKEND_PORT=${_PYTHON_BACKEND_PORT}"
  "LISTEN_HOST=${LISTEN_HOST:-127.0.0.1}"
)
if [[ "${AI_EMPLOYEE_NODE_RUN_AS_NODE:-0}" == "1" ]]; then
  _BACKEND_ENV+=("ELECTRON_RUN_AS_NODE=1")
fi
nohup "${_BACKEND_ENV[@]}" "$_NODE_BIN" --max-old-space-size=512 backend/server.js >> "$APP_LOG_DIR/server.log" 2>&1 </dev/null &
BACKEND_PID=$!

# Poll /health until the server responds (up to ~3 s, 0.1s intervals).
# /health always returns 200 OK as soon as the server is listening (fast!).
_BE_READY=0
for _i in $(seq 1 30); do
  sleep 0.1
  if curl -fsS --max-time 0.2 "http://127.0.0.1:${UI_PORT}/health" > /dev/null 2>&1; then
    _BE_READY=1
    break
  fi
done

if [[ "$_BE_READY" -eq 1 ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
  # Spawn-validation: poll /health up to ~2 s confirming the process stays up
  _STILL_OK=0
  for _i in $(seq 1 20); do
    sleep 0.1
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "❌ Backend process exited immediately after becoming healthy"
      [[ -n "${PYTHON_PID:-}" ]] && kill "$PYTHON_PID" 2>/dev/null || true
      exit 1
    fi
    if curl -fsS --max-time 0.2 "http://127.0.0.1:${UI_PORT}/health" > /dev/null 2>&1; then
      _STILL_OK=1
      break
    fi
  done
  if [[ -n "${PYTHON_PID:-}" ]] && ! kill -0 "$PYTHON_PID" 2>/dev/null; then
    echo "❌ Python AI backend exited immediately after startup"
    kill "$BACKEND_PID" 2>/dev/null || true
    exit 1
  fi
  echo "✅ System running at http://localhost:${UI_PORT}"
else
  echo "❌ Backend did not become healthy within 3 s"
  [[ -n "${PYTHON_PID:-}" ]] && kill "$PYTHON_PID" 2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

echo "$BACKEND_PID" > "$_BACKEND_PID_FILE"
rm -f "$APP_RUN_DIR/worker.pid"

echo "Tip: For live frontend hot-reload, run the backend in one terminal and the Vite dev server in another:"
echo "  Terminal 1: PORT=${UI_PORT} node backend/server.js"
echo "  Terminal 2: cd frontend && npm run dev   # listens on http://127.0.0.1:5173 and proxies API to :${UI_PORT}"
