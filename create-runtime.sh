#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p runtime/{bin,bots,config}
mkdir -p runtime/bots/{problem-solver,problem-solver-ui,polymarket-trader}

# -----------------------------------------------------------------------------
# runtime/bin/ai-employee
# -----------------------------------------------------------------------------
cat > runtime/bin/ai-employee << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOTS_DIR="$AI_HOME/bots"
LOGS_DIR="$AI_HOME/logs"
RUN_DIR="$AI_HOME/run"

mkdir -p "$LOGS_DIR" "$RUN_DIR"

usage() {
  cat <<'USAGE'
ai-employee commands:
  start --all | <bot>
  stop --all | <bot>
  restart --all | <bot>
  status
  logs <bot>
  doctor
  ui
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
  local bot_dir="$BOTS_DIR/$bot"
  local entry="$bot_dir/run.sh"
  local log="$LOGS_DIR/$bot.log"
  local pid_file
  pid_file="$(bot_pid_file "$bot")"

  if is_running "$bot"; then
    echo "Already running: $bot (pid $(cat "$pid_file"))"
    return 0
  fi

  if [[ ! -x "$entry" ]]; then
    echo "ERROR: missing executable $entry"
    exit 1
  fi

  echo "Starting $bot ..."
  nohup "$entry" >>"$log" 2>&1 &
  echo $! > "$pid_file"
  echo "Started $bot pid=$!"
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
  echo "Stopped $bot"
}

list_bots() {
  if [[ ! -d "$BOTS_DIR" ]]; then
    return 0
  fi
  find "$BOTS_DIR" -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort
}

cmd="${1:-}"
shift || true

case "$cmd" in
  start)
    arg="${1:-}"
    if [[ "$arg" == "--all" ]]; then
      while read -r bot; do
        [[ -n "$bot" ]] && start_bot "$bot"
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
        [[ -n "$bot" ]] && stop_bot "$bot"
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
        [[ -n "$bot" ]] && stop_bot "$bot"
      done < <(list_bots)
      while read -r bot; do
        [[ -n "$bot" ]] && start_bot "$bot"
      done < <(list_bots)
    else
      [[ -n "$arg" ]] || { usage; exit 1; }
      stop_bot "$arg"
      start_bot "$arg"
    fi
    ;;
  status)
    while read -r bot; do
      [[ -n "$bot" ]] || continue
      if is_running "$bot"; then
        echo "RUNNING $bot pid=$(cat "$(bot_pid_file "$bot")")"
      else
        echo "STOPPED $bot"
      fi
    done < <(list_bots)
    ;;
  logs)
    bot="${1:-}"
    [[ -n "$bot" ]] || { usage; exit 1; }
    tail -n 200 -f "$LOGS_DIR/$bot.log"
    ;;
  doctor)
    echo "AI_HOME=$AI_HOME"
    echo "Bots dir: $BOTS_DIR"
    echo "Logs dir: $LOGS_DIR"
    echo "Run dir : $RUN_DIR"
    echo "Bots:"
    list_bots || true
    ;;
  ui)
    start_bot "problem-solver-ui"
    echo "UI started (check logs)."
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
# runtime/bots/problem-solver/*
# -----------------------------------------------------------------------------
cat > runtime/bots/problem-solver/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/problem-solver"

if [[ -f "$AI_HOME/config/problem-solver.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver.env"
  set +a
fi

python3 "$BOT_HOME/problem_solver.py"
EOF

cat > runtime/bots/problem-solver/problem_solver.py << 'EOF'
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
BOTS = os.environ.get("PROBLEM_SOLVER_WATCH_BOTS", "problem-solver-ui,polymarket-trader").split(",")

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
    print(f"[{now()}] problem-solver started; watching bots: {BOTS}; auto_restart={AUTO_RESTART}")
    while True:
        state = {"ts": now(), "bots": []}
        for bot in [b.strip() for b in BOTS if b.strip()]:
            ok = bot_running(bot)
            entry = {"bot": bot, "running": ok}
            if not ok and AUTO_RESTART:
                rc, out = ai_employee("start", bot)
                entry["action"] = "start"
                entry["action_rc"] = rc
                entry["action_out_tail"] = out[-800:]
            state["bots"].append(entry)

        write_state(state)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
EOF

# -----------------------------------------------------------------------------
# runtime/bots/problem-solver-ui/*
# -----------------------------------------------------------------------------
cat > runtime/bots/problem-solver-ui/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/problem-solver-ui"

if [[ -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/problem-solver-ui.env"
  set +a
fi

python3 "$BOT_HOME/server.py"
EOF

cat > runtime/bots/problem-solver-ui/server.py << 'EOF'
import os
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "problem-solver.state.json"
PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")

app = FastAPI()

INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Problem Solver UI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; max-width: 1000px; }
    textarea { width: 100%; height: 90px; }
    pre { background:#f6f8fa; padding:12px; overflow:auto; }
    .row { display:flex; gap:12px; align-items:flex-start; }
    .col { flex:1; }
  </style>
</head>
<body>
  <h1>Problem Solver UI</h1>
  <p>Status + ask. (Improvements tab comes in the next rewrite after your AII signal.)</p>

  <div class="row">
    <div class="col">
      <h3>Ask</h3>
      <textarea id="q" placeholder="Describe the problem..."></textarea>
      <button onclick="ask()">Send</button>
      <h3>Answer</h3>
      <pre id="a"></pre>
    </div>
    <div class="col">
      <h3>System status</h3>
      <button onclick="refresh()">Refresh</button>
      <pre id="s"></pre>
    </div>
  </div>

<script>
async function refresh(){
  const r = await fetch('/api/status');
  document.getElementById('s').textContent = JSON.stringify(await r.json(), null, 2);
}
async function ask(){
  const q = document.getElementById('q').value;
  const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q})});
  document.getElementById('a').textContent = JSON.stringify(await r.json(), null, 2);
}
refresh();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML

@app.get("/api/status")
def status():
    if STATE_FILE.exists():
        return JSONResponse(json.loads(STATE_FILE.read_text()))
    return JSONResponse({"ts": None, "bots": [], "note": "No state file yet. Start problem-solver."})

@app.post("/api/ask")
def ask(payload: dict):
    q = (payload or {}).get("question", "").strip()
    if not q:
        return JSONResponse({"error": "Empty question"}, status_code=400)
    return JSONResponse({
        "question": q,
        "note": "Stub response. After your AII signal, this will use local Ollama first, bridge as fallback."
    })

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
EOF

cat > runtime/bots/problem-solver-ui/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn==0.30.6
EOF

# -----------------------------------------------------------------------------
# runtime/bots/polymarket-trader/*
# -----------------------------------------------------------------------------
cat > runtime/bots/polymarket-trader/run.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/polymarket-trader"

if [[ -f "$AI_HOME/config/polymarket-trader.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/polymarket-trader.env"
  set +a
fi

python3 "$BOT_HOME/trader.py"
EOF

cat > runtime/bots/polymarket-trader/trader.py << 'EOF'
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
PROBLEM_SOLVER_WATCH_BOTS=problem-solver-ui,polymarket-trader
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
chmod +x runtime/bots/problem-solver/run.sh
chmod +x runtime/bots/problem-solver-ui/run.sh
chmod +x runtime/bots/polymarket-trader/run.sh

echo "OK: runtime/ generated under: $ROOT_DIR/runtime"
echo "Next: git add runtime && git commit -m 'Add runtime files' && git push"

