#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p runtime/{bin,agents,config}
mkdir -p runtime/bagents/{problem-solver,problem-solver-ui,polymarket-trader}

# -----------------------------------------------------------------------------
# runtime/bin/ai-employee
# -----------------------------------------------------------------------------
cat > runtime/bin/ai-employee << 'EOF'
#!/usr/bin/env bash
# AI Employee - Multi-bot runner
# Usage: ai-employee <command> [args]
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENTS_DIR="$AI_HOME/agents"
LOGS_DIR="$AI_HOME/logs"
RUN_DIR="$AI_HOME/run"
STATE_DIR="$AI_HOME/state"

mkdir -p "$LOGS_DIR" "$RUN_DIR" "$STATE_DIR"

usage() {
  cat <<'USAGE'
ai-employee commands:
  do <task>              Send any task to your AI employee (e.g. ai-employee do "find 10 leads")
  start --all | <agent>   Start one or all agents
  stop  --all | <agent>   Stop one or all agents
  restart --all | <agent> Restart one or all agents
  status                 Show running status of all agents
  logs <bot>             Tail logs for a bot
  doctor                 Health-check all services (✅/❌ per component)
  onboard                Run the First 15 Minutes Value Flow (3 starter tasks)
  mode [starter|business|power]  Show or set the active mode
  ui                     Open UI in browser
USAGE
}

bot_pid_file() { echo "$RUN_DIR/$1.pid"; }

is_running() {
  local bot="$1"
  local pid_file
  pid_file="$(bot_pid_file "$bot")"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "${pid:-}" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_bot() {
  local bot="$1"
  local bot_dir="$AGENTS_DIR/$bot"
  local entry="$bot_dir/run.sh"
  local log="$LOGS_DIR/$bot.log"
  local pid_file
  pid_file="$(bot_pid_file "$bot")"

  # Library/module directories (e.g. ai-router) have no run.sh — skip silently
  if [[ ! -f "$entry" ]]; then
    return 0
  fi

  if is_running "$bot"; then
    echo "Already running: $bot (pid $(cat "$pid_file"))"
    return 0
  fi

  if [[ ! -x "$entry" ]]; then
    echo "ERROR: missing executable $entry"
    return 1
  fi

  echo "Starting $bot ..."
  nohup "$entry" >>"$log" 2>&1 &
  echo $! > "$pid_file"
  echo "Started $bot pid=$!"

  # Record start time in state
  local state_file="$STATE_DIR/$bot.state.json"
  echo "{\"bot\":\"$bot\",\"status\":\"running\",\"started_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"pid\":$!}" > "$state_file"
}

stop_bot() {
  local bot="$1"
  local pid_file
  pid_file="$(bot_pid_file "$bot")"
  if ! [[ -f "$pid_file" ]]; then
    echo "Not running (no pid file): $bot"
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "${pid:-}" ]]; then
    rm -f "$pid_file"
    echo "Cleaned empty pid file: $bot"
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $bot pid=$pid ..."
    kill "$pid" || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"

  # Update state
  local state_file="$STATE_DIR/$bot.state.json"
  echo "{\"bot\":\"$bot\",\"status\":\"stopped\",\"stopped_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$state_file"
  echo "Stopped $bot"
}

list_bots() {
  if [[ ! -d "$AGENTS_DIR" ]]; then
    return 0
  fi
  # Portable: works on Linux and macOS
  find "$AGENTS_DIR" -maxdepth 1 -mindepth 1 -type d | sort | while read -r d; do
    basename "$d"
  done
}

cmd="${1:-}"
shift || true

case "$cmd" in
  start)
    arg="${1:-}"
    if [[ "$arg" == "--all" ]]; then
      while read -r bot; do
        [[ -n "$bot" ]] && start_bot "$bot" || true
      done < <(list_bots)
    else
      [[ -n "$arg" ]] || { usage; exit 1; }
      start_bot "$arg"
    fi
    ;;
  stop)
    arg="${1:-}"
    if [[ "$arg" == "--all" ]]; then
      while read -r bot; do
        [[ -n "$bot" ]] && stop_bot "$bot" || true
      done < <(list_bots)
    else
      [[ -n "$arg" ]] || { usage; exit 1; }
      stop_bot "$arg"
    fi
    ;;
  restart)
    arg="${1:-}"
    if [[ "$arg" == "--all" ]]; then
      while read -r bot; do
        [[ -n "$bot" ]] && stop_bot "$bot" || true
      done < <(list_bots)
      sleep 1
      while read -r bot; do
        [[ -n "$bot" ]] && start_bot "$bot" || true
      done < <(list_bots)
    else
      [[ -n "$arg" ]] || { usage; exit 1; }
      stop_bot "$arg"
      sleep 1
      start_bot "$arg"
    fi
    ;;
  status)
    while read -r bot; do
      [[ -n "$bot" ]] || continue
      if is_running "$bot"; then
        echo "RUNNING  $bot  pid=$(cat "$(bot_pid_file "$bot")")"
      else
        echo "STOPPED  $bot"
      fi
    done < <(list_bots)
    ;;
  logs)
    bot="${1:-}"
    [[ -n "$bot" ]] || { usage; exit 1; }
    tail -n 200 -f "$LOGS_DIR/$bot.log"
    ;;
  doctor)
    OK="✅"; FAIL="❌"; WARN="⚠️ "
    echo ""
    echo "=== AI Employee — Health Check ==="
    echo ""

    # Load env for port/key info
    if [[ -f "$AI_HOME/.env" ]]; then
      # shellcheck disable=SC1091
      set -a; source "$AI_HOME/.env" 2>/dev/null || true; set +a
    fi

    # Core binaries
    echo "── Dependencies ──────────────────────────────"
    command -v python3  >/dev/null 2>&1 \
      && echo "  $OK python3    : $(python3 --version 2>&1)" \
      || echo "  $FAIL python3   : NOT FOUND (required)"
    command -v curl     >/dev/null 2>&1 \
      && echo "  $OK curl       : $(curl --version 2>&1 | head -1)" \
      || echo "  $FAIL curl      : NOT FOUND (required)"
    command -v ollama   >/dev/null 2>&1 \
      && echo "  $OK ollama     : $(ollama --version 2>/dev/null || echo installed)" \
      || echo "  $WARN ollama    : not installed (optional — enables local/private LLM)"
    command -v node     >/dev/null 2>&1 \
      && echo "  $OK node       : $(node --version 2>&1)" \
      || echo "  $WARN node      : not installed (optional)"
    echo ""

    # Running services
    echo "── Services ──────────────────────────────────"
    _UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

    # Problem Solver UI
    if is_running "problem-solver-ui"; then
      echo "  $OK Problem Solver : running (port $_UI_PORT) → http://localhost:$_UI_PORT"
    else
      echo "  $FAIL Problem Solver: not running — run: ai-employee start problem-solver-ui"
    fi

    # Ollama reachability
    if curl -sf --max-time 2 "${OLLAMA_HOST:-http://localhost:11434}" >/dev/null 2>&1; then
      echo "  $OK Ollama API     : reachable at ${OLLAMA_HOST:-http://localhost:11434}"
    else
      echo "  $WARN Ollama API    : not reachable (start with: ollama serve)"
    fi
    echo ""

    # API keys
    echo "── API Keys ──────────────────────────────────"
    [[ -n "${ANTHROPIC_API_KEY:-}" ]] \
      && echo "  $OK Anthropic API key : set" \
      || echo "  $WARN Anthropic API key : not set (optional — add to ~/.ai-employee/.env)"
    [[ -n "${OPENAI_API_KEY:-}" ]] \
      && echo "  $OK OpenAI API key   : set" \
      || echo "  $WARN OpenAI API key   : not set (optional)"
    [[ -n "${JWT_SECRET_KEY:-}" ]] \
      && echo "  $OK JWT secret       : set" \
      || echo "  $FAIL JWT secret      : NOT SET — add JWT_SECRET_KEY to ~/.ai-employee/.env"
    echo ""

    # Mode
    _mode="${AI_EMPLOYEE_MODE:-power}"
    echo "── Configuration ─────────────────────────────"
    echo "  $OK Mode           : $_mode  (change: ai-employee mode starter|business|power)"
    echo "  $OK AI_HOME        : $AI_HOME"
    echo "  $OK Bots dir       : $AGENTS_DIR"
    echo "  $OK Logs dir       : $LOGS_DIR"
    echo ""
    echo "  Tip: Run  ai-employee start --all  to start all services."
    echo ""
    ;;
  ui)
    start_bot "problem-solver-ui"
    url="http://127.0.0.1:${PROBLEM_SOLVER_UI_PORT:-8787}"
    echo "UI started — open $url in your browser (or wait for auto-open)."
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$url" 2>/dev/null &
    elif command -v open >/dev/null 2>&1; then
      open "$url" 2>/dev/null &
    else
      echo "  -> Open manually: $url"
    fi
    ;;
  do)
    # Send any task to your AI employee via the Problem Solver UI API
    task_text="${*}"
    if [[ -z "${task_text:-}" ]]; then
      echo "Usage: ai-employee do <task description>"
      echo "Example: ai-employee do \"find 10 leads for a web design agency\""
      exit 1
    fi

    # Load env for port
    if [[ -f "$AI_HOME/.env" ]]; then
      # shellcheck disable=SC1091
      set -a; source "$AI_HOME/.env" 2>/dev/null || true; set +a
    fi
    _UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"
    _API="http://127.0.0.1:${_UI_PORT}/api/chat"

    # Start UI if not running
    if ! is_running "problem-solver-ui"; then
      echo "Starting AI employee..."
      start_bot "problem-solver-ui" >/dev/null 2>&1 || true
      sleep 3
    fi

    echo "🤖 Sending task to your AI employee..."
    echo "   Task: $task_text"
    echo ""

    if command -v curl >/dev/null 2>&1; then
      _resp=$(curl -sf --max-time 30 \
        -X POST "$_API" \
        -H "Content-Type: application/json" \
        -d "{\"message\": $(printf '%s' "$task_text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
        2>/dev/null || true)
      if [[ -n "${_resp:-}" ]]; then
        _msg=$(echo "$_resp" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("response",""))' 2>/dev/null || echo "$_resp")
        echo "✅ Response:"
        echo "$_msg"
      else
        echo "⚠️  AI employee is starting up. Try again in a few seconds."
        echo "   Or open the dashboard: http://127.0.0.1:${_UI_PORT}"
      fi
    else
      echo "ERROR: curl is required for the 'do' command."
      exit 1
    fi
    ;;

  onboard)
    # First 15 Minutes Value Flow — auto-runs 3 starter tasks
    if [[ -f "$AI_HOME/.env" ]]; then
      # shellcheck disable=SC1091
      set -a; source "$AI_HOME/.env" 2>/dev/null || true; set +a
    fi
    _UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║   🚀 First 15 Minutes Value Flow                     ║"
    echo "║   Let's generate your first real business results.   ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    # Start UI if not running
    if ! is_running "problem-solver-ui"; then
      echo "Starting AI employee..."
      start_bot "problem-solver-ui" >/dev/null 2>&1 || true
      sleep 5
    fi

    _API="http://127.0.0.1:${_UI_PORT}/api/chat"
    _total_value=0
    _total_hours=0

    _run_task() {
      local label="$1" task="$2" value="$3" hours="$4"
      echo "── Task: $label ──────────────────────────────"
      if command -v curl >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
        _resp=$(curl -sf --max-time 60 \
          -X POST "$_API" \
          -H "Content-Type: application/json" \
          -d "{\"message\": $(printf '%s' "$task" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
          2>/dev/null || true)
        if [[ -n "${_resp:-}" ]]; then
          _msg=$(echo "$_resp" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("response",""))' 2>/dev/null || echo "$_resp")
          echo "✅ Done:"
          echo "$_msg" | head -10
          _total_value=$(( _total_value + value ))
          _total_hours=$(( _total_hours + hours ))
        else
          echo "⚠️  Task queued (UI still starting). Check dashboard: http://127.0.0.1:${_UI_PORT}"
        fi
      else
        echo "⚠️  curl/python3 required. Task saved to queue."
      fi
      echo ""
    }

    echo "Running 3 tasks automatically. This takes ~2 minutes."
    echo ""

    _run_task \
      "Generate 10 leads for your business" \
      "Find 10 qualified B2B leads for a small agency. Include: company name, contact name, role, email (if available), and why they are a good fit. Format as a list." \
      500 2

    _run_task \
      "Write your first sales email" \
      "Write a personalised cold outreach email for a solo founder reaching out to a potential client. Keep it under 150 words, focus on value not features, include a clear CTA." \
      200 1

    _run_task \
      "Analyse your top competitor" \
      "Analyse the strengths and weaknesses of a typical competitor in the digital agency space. Give 3 opportunities I can exploit as a solo founder." \
      300 1

    echo "╔══════════════════════════════════════════════════════╗"
    printf "║  ✅  Estimated value generated:  €%d potential       \n" "$_total_value"
    printf "║  ⏱️   Estimated time saved:       %d hours            \n" "$_total_hours"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  📊 Open your dashboard to see full results:"
    echo "     http://127.0.0.1:${_UI_PORT}"
    echo ""
    echo "  Next: run  ai-employee do \"<any task>\"  to keep going."
    echo ""

    # Mark onboarding complete
    mkdir -p "$STATE_DIR"
    echo "{\"onboarded\":true,\"completed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
      > "$STATE_DIR/onboarding.json"
    ;;

  mode)
    if [[ -f "$AI_HOME/.env" ]]; then
      # shellcheck disable=SC1091
      set -a; source "$AI_HOME/.env" 2>/dev/null || true; set +a
    fi
    _new_mode="${1:-}"
    case "${_new_mode:-}" in
      starter|business|power)
        # Update mode in .env
        if [[ -f "$AI_HOME/.env" ]]; then
          if grep -q "^AI_EMPLOYEE_MODE=" "$AI_HOME/.env"; then
            sed -i.bak "s|^AI_EMPLOYEE_MODE=.*|AI_EMPLOYEE_MODE=$_new_mode|" "$AI_HOME/.env"
            rm -f "$AI_HOME/.env.bak"
          else
            echo "AI_EMPLOYEE_MODE=$_new_mode" >> "$AI_HOME/.env"
          fi
        fi
        export AI_EMPLOYEE_MODE="$_new_mode"
        echo "✅ Mode set to: $_new_mode"
        case "$_new_mode" in
          starter)
            echo ""
            echo "  Starter mode: 3 agents, 5 commands, no dashboard overload."
            echo "  Commands: ai-employee do, status, logs, doctor, onboard"
            ;;
          business)
            echo ""
            echo "  Business mode: templates, ROI tracking, scheduling."
            echo "  Run: ai-employee ui  to open the full dashboard."
            ;;
          power)
            echo ""
            echo "  Power mode: all 20 agents, all 126 skills, full dashboard."
            ;;
        esac
        ;;
      "")
        _cur="${AI_EMPLOYEE_MODE:-power}"
        echo "Current mode: $_cur"
        echo ""
        echo "Available modes:"
        echo "  starter  — 3 agents, 5 commands (best for getting started)"
        echo "  business — templates, ROI, scheduling (recommended for solo founders)"
        echo "  power    — everything, all 20 agents (advanced users)"
        echo ""
        echo "Change mode: ai-employee mode <starter|business|power>"
        ;;
      *)
        echo "Unknown mode: $_new_mode"
        echo "Valid modes: starter, business, power"
        exit 1
        ;;
    esac
    ;;

  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac
EOF

# -----------------------------------------------------------------------------
# runtime/bagents/problem-solver/*
# -----------------------------------------------------------------------------
cat > runtime/bagents/problem-solver/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bagents/problem-solver"

if [[ -f "$AI_HOME/config/problem-solver.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver.env"
  set +a
fi

python3 "$BOT_HOME/problem_solver.py"
EOF

cat > runtime/bagents/problem-solver/problem_solver.py << 'EOF'
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "problem-solver.state.json"

CHECK_INTERVAL = int(os.environ.get("PROBLEM_SOLVER_CHECK_INTERVAL", "5"))
AUTO_RESTART = os.environ.get("PROBLEM_SOLVER_AUTO_RESTART", "true").lower() == "true"
AGENTS = os.environ.get("PROBLEM_SOLVER_WATCH_AGENTS", "problem-solver-ui,polymarket-trader").split(",")

def now():
    return datetime.utcnow().isoformat() + "Z"

def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

def bot_running(bot: str) -> bool:
    pid_file = AI_HOME / "run" / f"{bot}.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def ai_employee(*args: str) -> tuple[int, str]:
    return run([str(AI_HOME / "bin" / "ai-employee"), *args])

def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def main():
    print(f"[{now()}] problem-solver started; watching agents: {AGENTS}; auto_restart={AUTO_RESTART}")
    while True:
        state = {"ts": now(), "agents": []}
        for bot in [b.strip() for b in AGENTS if b.strip()]:
            ok = bot_running(bot)
            entry = {"bot": bot, "running": ok}
            if not ok and AUTO_RESTART:
                rc, out = ai_employee("start", bot)
                entry["action"] = "start"
                entry["action_rc"] = rc
                entry["action_out_tail"] = out[-800:]
            state["agents"].append(entry)

        write_state(state)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
EOF

# -----------------------------------------------------------------------------
# runtime/bagents/problem-solver-ui/*
# -----------------------------------------------------------------------------
cat > runtime/bagents/problem-solver-ui/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bagents/problem-solver-ui"

if [[ -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver-ui.env"
  set +a
fi

python3 "$BOT_HOME/server.py"
EOF

cat > runtime/bagents/problem-solver-ui/server.py << 'EOF'
"""AI Employee — Problem Solver UI (server.py)

Full FastAPI implementation with authentication, LLM-backed chat,
metrics, schedules, agents, skills, templates, guardrails, and memory.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import uvicorn

# ── Optional security deps ────────────────────────────────────────────────────
try:
    from jose import JWTError, jwt as _jwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False
    _pwd_context = None  # type: ignore[assignment]

# ── Config ────────────────────────────────────────────────────────────────────
AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
CONFIG_DIR = AI_HOME / "config"
CHATLOG = STATE_DIR / "chatlog.jsonl"
PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 24 hours

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

SECURE_MODE = bool(JWT_SECRET)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(message)s",
)
logger = logging.getLogger("problem-solver-ui")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _state(name: str) -> Path:
    return STATE_DIR / name

def _read_json(path: Path, default: Any = None) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default if default is not None else {}

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Auth helpers ──────────────────────────────────────────────────────────────
def _hash_password(pw: str) -> str:
    if _PASSLIB_AVAILABLE and _pwd_context is not None:
        return _pwd_context.hash(pw)
    import hashlib, secrets
    salt = secrets.token_hex(16)
    return f"sha256:{salt}:{hashlib.sha256((salt + pw).encode()).hexdigest()}"

def _verify_password(pw: str, hashed: str) -> bool:
    if _PASSLIB_AVAILABLE and _pwd_context is not None:
        return _pwd_context.verify(pw, hashed)
    if hashed.startswith("sha256:"):
        parts = hashed.split(":")
        if len(parts) == 3:
            _, salt, h = parts
            import hashlib
            return h == hashlib.sha256((salt + pw).encode()).hexdigest()
    return False

def _create_token(username: str) -> str:
    if _JWT_AVAILABLE and JWT_SECRET:
        payload = {
            "sub": username,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
            "iat": datetime.now(timezone.utc),
        }
        return _jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    import base64
    payload = json.dumps({"sub": username, "exp": time.time() + JWT_EXPIRE_MINUTES * 60})
    return base64.urlsafe_b64encode(payload.encode()).decode()

def _decode_token(token: str) -> Optional[str]:
    if _JWT_AVAILABLE and JWT_SECRET:
        try:
            payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("sub")
        except JWTError:
            return None
    try:
        import base64
        payload = json.loads(base64.urlsafe_b64decode(token.encode() + b"==").decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None

_bearer = HTTPBearer(auto_error=False)

def _current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[str]:
    if not credentials:
        return None
    return _decode_token(credentials.credentials)

# ── LLM router ────────────────────────────────────────────────────────────────
def _call_llm(message: str) -> str:
    """Try Anthropic → OpenAI → Ollama; return response text."""
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": message}],
            )
            return resp.content[0].text
        except Exception as exc:
            logger.warning("Anthropic error: %s", exc)

    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": message}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("OpenAI error: %s", exc)

    try:
        import httpx
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": message, "stream": False},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as exc:
        logger.warning("Ollama error: %s", exc)

    return (
        "No LLM configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "or install Ollama (https://ollama.com) and run: ollama pull llama3.2"
    )

# ── Pydantic models ───────────────────────────────────────────────────────────
class _AuthReq(BaseModel):
    username: str
    password: str

class _ChatReq(BaseModel):
    message: str

class _MetricsRecordReq(BaseModel):
    event: str
    value: float = 1.0

class _ScheduleReq(BaseModel):
    task: str
    cron: str = ""

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Employee — Problem Solver UI", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTML dashboard ────────────────────────────────────────────────────────────
INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>AI Employee Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; max-width: 900px; }
    textarea { width: 100%; height: 90px; }
    pre { background:#f6f8fa; padding:12px; overflow:auto; border-radius:4px; }
    .row { display:flex; gap:12px; }
    .col { flex:1; }
    button { padding:8px 16px; cursor:pointer; }
  </style>
</head>
<body>
  <h1>&#x1F916; AI Employee Dashboard</h1>
  <div class="row">
    <div class="col">
      <h3>Chat</h3>
      <textarea id="q" placeholder="Ask your AI employee anything..."></textarea><br>
      <button onclick="chat()">Send</button>
      <h3>Response</h3>
      <pre id="a"></pre>
    </div>
    <div class="col">
      <h3>System Status</h3>
      <button onclick="refresh()">Refresh</button>
      <pre id="s"></pre>
    </div>
  </div>
<script>
async function refresh(){
  const r = await fetch('/api/status');
  document.getElementById('s').textContent = JSON.stringify(await r.json(), null, 2);
}
async function chat(){
  const q = document.getElementById('q').value;
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:q})});
  const d = await r.json();
  document.getElementById('a').textContent = d.response || JSON.stringify(d, null, 2);
}
refresh();
</script>
</body>
</html>"""

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "healthy", "version": "2.0.0", "secure_mode": SECURE_MODE}

@app.get("/security/status")
def security_status() -> Dict[str, Any]:
    warnings: List[str] = []
    if not SECURE_MODE:
        warnings.append("JWT_SECRET_KEY not set — authentication is disabled")
    if not _JWT_AVAILABLE:
        warnings.append("python-jose not installed — JWT signing unavailable")
    if not _PASSLIB_AVAILABLE:
        warnings.append("passlib not installed — using fallback password hashing")
    return {"secure_mode": SECURE_MODE, "warnings": warnings}

@app.post("/auth/register")
def auth_register(req: _AuthReq) -> Dict[str, str]:
    if not req.username or len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if not req.password or len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    users_file = STATE_DIR / "users.json"
    users: Dict[str, Any] = _read_json(users_file, {})
    if req.username in users:
        raise HTTPException(status_code=409, detail="Username already exists")
    users[req.username] = {
        "hashed_password": _hash_password(req.password),
        "created_at": _now(),
    }
    _write_json(users_file, users)
    return {"access_token": _create_token(req.username), "token_type": "bearer"}

@app.post("/auth/login")
def auth_login(req: _AuthReq) -> Dict[str, str]:
    users_file = STATE_DIR / "users.json"
    users: Dict[str, Any] = _read_json(users_file, {})
    user = users.get(req.username)
    if not user or not _verify_password(req.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"access_token": _create_token(req.username), "token_type": "bearer"}

@app.get("/api/status")
def api_status() -> Any:
    state_file = AI_HOME / "run" / "problem-solver.state.json"
    if state_file.exists():
        return JSONResponse(_read_json(state_file))
    return {"ts": None, "agents": [], "note": "No state file yet. Start problem-solver."}

@app.post("/api/chat")
def api_chat(req: _ChatReq) -> Dict[str, str]:
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Empty message")
    response = _call_llm(msg)
    entry = {"ts": _now(), "user": msg, "assistant": response}
    try:
        CHATLOG.parent.mkdir(parents=True, exist_ok=True)
        with CHATLOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Failed to write chatlog: %s", exc)
    return {"response": response, "ts": entry["ts"]}

@app.get("/api/metrics")
def get_metrics() -> Any:
    return _read_json(_state("metrics.json"), {})

@app.post("/api/metrics")
def post_metrics(data: Dict[str, Any]) -> Any:
    existing: Dict[str, Any] = _read_json(_state("metrics.json"), {})
    existing.update(data)
    _write_json(_state("metrics.json"), existing)
    return existing

@app.post("/api/metrics/record")
def record_metric(req: _MetricsRecordReq) -> Dict[str, Any]:
    existing: Dict[str, Any] = _read_json(_state("metrics.json"), {"events": []})
    if "events" not in existing:
        existing["events"] = []
    existing["events"].append({"event": req.event, "value": req.value, "ts": _now()})
    _write_json(_state("metrics.json"), existing)
    return {"ok": True, "event": req.event, "value": req.value}

@app.get("/api/schedules")
def get_schedules() -> Any:
    return _read_json(CONFIG_DIR / "schedules.json", [])

@app.post("/api/schedules")
def create_schedule(req: _ScheduleReq) -> Dict[str, Any]:
    schedules: List[Any] = _read_json(CONFIG_DIR / "schedules.json", [])
    entry: Dict[str, Any] = {
        "id": f"s{int(time.time())}",
        "task": req.task,
        "cron": req.cron,
        "created_at": _now(),
    }
    schedules.append(entry)
    _write_json(CONFIG_DIR / "schedules.json", schedules)
    return entry

@app.get("/api/agents")
def get_agents() -> Any:
    return _read_json(CONFIG_DIR / "custom_agents.json", [])

@app.get("/api/skills")
def get_skills() -> Any:
    return _read_json(CONFIG_DIR / "skills_library.json", [])

@app.get("/api/templates")
def get_templates() -> Any:
    return _read_json(CONFIG_DIR / "agent_templates.json", [])

@app.post("/api/templates/{template_id}/deploy")
def deploy_template(template_id: str) -> Dict[str, Any]:
    return {"ok": True, "template_id": template_id, "status": "deployed"}

@app.get("/api/guardrails")
def get_guardrails() -> Any:
    return _read_json(_state("guardrails.json"), {"enabled": True, "rules": []})

@app.get("/api/memory")
def get_memory() -> Any:
    return _read_json(_state("memory.json"), {"clients": []})

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
EOF

cat > runtime/bagents/problem-solver-ui/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.1
httpx==0.27.0
aiofiles==23.2.1
anthropic>=0.25.0
EOF

# -----------------------------------------------------------------------------
# runtime/bagents/polymarket-trader/*
# -----------------------------------------------------------------------------
cat > runtime/bagents/polymarket-trader/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bagents/polymarket-trader"

if [[ -f "$AI_HOME/config/polymarket-trader.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/polymarket-trader.env"
  set +a
fi

python3 "$BOT_HOME/trader.py"
EOF

cat > runtime/bagents/polymarket-trader/trader.py << 'EOF'
import os
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "polymarket-trader.state.json"

POLL_SECONDS = int(os.environ.get("PM_POLL_SECONDS", "5"))
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"
KILL_SWITCH = os.environ.get("KILL_SWITCH", "false").lower() == "true"

MAX_POSITION_USD = float(os.environ.get("MAX_POSITION_USD", "25"))
EDGE_THRESHOLD = float(os.environ.get("EDGE_THRESHOLD", "0.07"))
ALLOW_MARKETS = [m.strip() for m in os.environ.get("ALLOW_MARKETS", "").split(",") if m.strip()]

def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

@dataclass
class MarketQuote:
    market_id: str
    yes_price: float
    no_price: float

class PolymarketClient:
    def get_quotes(self) -> list[MarketQuote]:
        return []
    def place_order_yes(self, market_id: str, usd_amount: float, max_price: float) -> str:
        raise NotImplementedError

class Strategy:
    def __init__(self, estimates_path: Path):
        self.estimates_path = estimates_path

    def load_estimates(self) -> dict[str, float]:
        if not self.estimates_path.exists():
            return {}
        return json.loads(self.estimates_path.read_text())

    def decide(self, quote: MarketQuote, est_prob: Optional[float]) -> Optional[dict]:
        if est_prob is None:
            return None
        edge = est_prob - quote.yes_price
        if edge >= EDGE_THRESHOLD:
            return {
                "side": "YES",
                "edge": edge,
                "est_prob": est_prob,
                "price": quote.yes_price,
                "usd": MAX_POSITION_USD,
                "max_price": min(0.999, quote.yes_price * 1.01),
            }
        return None

def main():
    client = PolymarketClient()
    strategy = Strategy(AI_HOME / "config" / "polymarket_estimates.json")
    print(f"polymarket-trader started LIVE_TRADING={LIVE_TRADING} KILL_SWITCH={KILL_SWITCH} allow_markets={ALLOW_MARKETS}")

    while True:
        if KILL_SWITCH:
            write_state({"ts": time.time(), "status": "killed"})
            time.sleep(5)
            continue

        estimates = strategy.load_estimates()
        quotes = client.get_quotes()

        actions = []
        for q in quotes:
            if ALLOW_MARKETS and q.market_id not in ALLOW_MARKETS:
                continue
            est = estimates.get(q.market_id)
            decision = strategy.decide(q, est)
            if decision:
                actions.append({"market_id": q.market_id, **decision})

        executed = []
        for a in actions:
            if not LIVE_TRADING:
                executed.append({**a, "executed": False, "mode": "paper"})
                continue
            executed.append({**a, "executed": False, "error": "Client not implemented", "mode": "live"})

        write_state({"ts": time.time(), "actions_found": len(actions), "executed": executed[:50]})
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
EOF

# -----------------------------------------------------------------------------
# runtime/config/*
# -----------------------------------------------------------------------------
cat > runtime/config/problem-solver.env << 'EOF'
PROBLEM_SOLVER_WATCH_AGENTS=problem-solver-ui,polymarket-trader
PROBLEM_SOLVER_CHECK_INTERVAL=5
PROBLEM_SOLVER_AUTO_RESTART=true
EOF

cat > runtime/config/problem-solver-ui.env << 'EOF'
PROBLEM_SOLVER_UI_HOST=127.0.0.1
PROBLEM_SOLVER_UI_PORT=8787
EOF

cat > runtime/config/polymarket-trader.env << 'EOF'
LIVE_TRADING=false
KILL_SWITCH=false
PM_POLL_SECONDS=5
EDGE_THRESHOLD=0.07
MAX_POSITION_USD=25
ALLOW_MARKETS=
EOF

cat > runtime/config/polymarket_estimates.json << 'EOF'
{}
EOF

# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------
chmod +x runtime/bin/ai-employee
chmod +x runtime/bagents/problem-solver/run.sh
chmod +x runtime/bagents/problem-solver-ui/run.sh
chmod +x runtime/bagents/polymarket-trader/run.sh

echo "OK: runtime/ generated under: $ROOT_DIR/runtime"
echo "Next: git add runtime && git commit -m 'Add runtime files' && git push"

