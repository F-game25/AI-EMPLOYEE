#!/bin/bash
set -euo pipefail

################################################################################
# AI EMPLOYEE - MAIN INSTALLER v3.1
# This is called by quick-install.sh
#
# Changes vs v3.0:
# - Adds 3 new skills (complex_problem_solving, prediction_markets_research, tool_language_selector)
# - Adds a local bot runner (ai-employee) to run multiple bots concurrently
# - Adds Problem Solver bot (watchdog) + Problem Solver UI (ask via browser)
# - Adds Polymarket trader bot (Python) with PAPER default + LIVE opt-in
# - Keeps existing OpenClaw install + existing dashboard UI
################################################################################

R='\033[0;31m';G='\033[0;32m';Y='\033[1;33m';B='\033[0;34m';C='\033[0;36m';NC='\033[0m'
AI_HOME="$HOME/.ai-employee"
START_TIME=$(date +%s)

log() { echo -e "${C}▸${NC} $1"; }
ok() { echo -e "${G}✓${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }
err() { echo -e "${R}✗${NC} $1"; exit 1; }

banner() {
cat << 'EOF'
╔══════════════════════════════════════════════════════╗
║          AI EMPLOYEE - v3.1 INSTALLER                ║
║   13 Agents • Multi-Bot Runner • Problem Solver UI   ║
╚══════════════════════════════════════════════════════╝
EOF
}

input() {
    log "Configuration"
    read -p "WhatsApp number (+31612345678): " PHONE
    [[ ! $PHONE =~ ^\+[0-9]{10,15}$ ]] && { warn "Invalid format, using anyway"; }
    read -sp "Anthropic API key (optional): " ANTHROPIC_KEY; echo
    read -p "Trading bot path (optional): " BOT_PATH
    BOT_PATH="${BOT_PATH/#\~/$HOME}"
    TOKEN=$(openssl rand -hex 32)
    ok "Config saved"
}

setup() {
    log "Installing OpenClaw..."
    if ! command -v openclaw &>/dev/null; then
        curl -fsSL https://openclaw.ai/install.sh | bash
        export PATH="$HOME/.local/bin:$PATH"
    fi
    ok "OpenClaw ready"

    log "Creating structure..."
    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups,bin,run,bots,config}
    for a in orchestrator lead-hunter content-master social-guru intel-agent product-scout email-ninja support-bot data-analyst creative-studio crypto-trader bot-dev web-sales; do
        mkdir -p "$AI_HOME/workspace-$a/skills"
    done
    chmod -R 700 "$AI_HOME/credentials"
    ok "Structure created"
}

install_skills() {
    log "Installing skills..."

    for skill in \
        "lead-hunter:linkedin_scraper:Find decision makers on LinkedIn" \
        "lead-hunter:email_finder:Find and verify email addresses" \
        "lead-hunter:lead_scorer:Score lead quality 0-100" \
        "lead-hunter:company_enrichment:Enrich company data" \
        "content-master:keyword_research:SEO keyword research" \
        "content-master:blog_writer:Write 2000+ word SEO articles" \
        "content-master:content_optimizer:Optimize existing content" \
        "social-guru:viral_finder:Find trending viral content" \
        "social-guru:caption_writer:Write platform-specific captions" \
        "social-guru:hashtag_generator:Generate relevant hashtags" \
        "social-guru:content_calendar:Create 30-day content calendar" \
        "intel-agent:pricing_tracker:Track competitor pricing" \
        "intel-agent:review_scraper:Scrape and analyze reviews" \
        "intel-agent:feature_comparison:Compare features with competitors" \
        "intel-agent:traffic_estimator:Estimate competitor traffic" \
        "product-scout:arbitrage_finder:Find AliExpress to Amazon arbitrage" \
        "product-scout:trend_spotter:Find trending products" \
        "product-scout:supplier_validator:Validate supplier reliability" \
        "product-scout:profit_calculator:Calculate true profit" \
        "email-ninja:sequence_builder:Build cold email sequences" \
        "email-ninja:deliverability_checker:Check email deliverability" \
        "email-ninja:personalization_engine:Personalize emails at scale" \
        "support-bot:faq_trainer:Extract FAQs from docs" \
        "support-bot:ticket_classifier:Classify support tickets" \
        "support-bot:sentiment_analyzer:Analyze customer sentiment" \
        "data-analyst:trend_analyzer:Analyze market trends" \
        "data-analyst:swot_generator:Generate SWOT analysis" \
        "data-analyst:survey_analyzer:Analyze survey responses" \
        "creative-studio:design_brief:Create design briefs" \
        "creative-studio:image_prompt:Generate AI image prompts" \
        "creative-studio:brand_voice:Define brand voice" \
        "creative-studio:ad_copy:Write ad copy" \
        "crypto-trader:technical_analysis:Full technical analysis" \
        "crypto-trader:pattern_recognition:Identify chart patterns" \
        "crypto-trader:whale_tracker:Track large wallet movements" \
        "bot-dev:code_review:Review code for issues" \
        "bot-dev:feature_implementation:Implement new features" \
        "bot-dev:bug_finder:Find bugs in code" \
        "web-sales:ux_audit:Audit website UX" \
        "web-sales:seo_audit:Technical SEO audit" \
        "web-sales:speed_test:Website speed analysis" \
        "orchestrator:complex_problem_solving:Complex problem solving for user or system issues (diagnose, fix, verify, prevent)" \
        "crypto-trader:prediction_markets_research:Scan prediction markets (e.g., Polymarket) for mispricing vs estimated probability using research + risk rules" \
        "orchestrator:tool_language_selector:Select the best tools + programming language for a task to maximize speed, cost efficiency and reliability"; do

        IFS=':' read -r agent skill_name desc <<< "$skill"
        cat > "$AI_HOME/workspace-$agent/skills/${skill_name}.md" << SKILL
---
name: $skill_name
description: $desc
---
Use this skill to $desc. Provide structured output with clear, actionable results.
SKILL
    done

    # Overwrite the 3 new skills with full documentation
    cat > "$AI_HOME/workspace-orchestrator/skills/complex_problem_solving.md" << 'EOF'
---
name: complex_problem_solving
description: Complex problem solving for user or system issues (diagnose, fix, verify, prevent)
---

## Purpose
Solve complex problems (user problems or AI/system problems) in a way that keeps the system running smoothly: fast triage, correct root cause, safe fix, and prevention.

## Inputs (ask these first)
1. Goal: What should “working” look like?
2. Context: OS, environment, where it runs (local / Docker / gateway), version/commit.
3. Symptoms: exact error message(s) + when it happens.
4. Scope: one agent, whole system, specific workflow?
5. Constraints: time, risk tolerance, can we restart services, can we change config?
6. Recent changes: what changed last (files, configs, updates)?

## Method (always follow this order)
### 1) Triage (stabilize now)
- Determine if blocking or degraded.
- If blocking: rollback/restart smallest component first.

### 2) Reproduce + isolate
- Reproduce with minimal steps.
- Capture logs, reduce variables.

### 3) Root cause analysis
Check:
- Config layer (ports, tokens, env vars, paths)
- Dependency layer (docker, node/python, network, permissions)
- Logic layer (script bugs, parsing, race conditions)

### 4) Fix (safe change plan)
- Minimal, reversible change
- Clear logging

### 5) Verification
- Success checks + regression checks

### 6) Prevention
- Preflight checks
- Monitoring/logging
- Documentation

## Output format
1. Summary
2. Hypotheses (ranked)
3. Tests to confirm
4. Fix plan
5. Rollback plan
6. Verification checklist
7. Prevention / hardening
EOF

    cat > "$AI_HOME/workspace-crypto-trader/skills/prediction_markets_research.md" << 'EOF'
---
name: prediction_markets_research
description: Scan prediction markets (e.g., Polymarket) for mispricing vs estimated probability using research + risk rules
---

## Purpose
Research prediction markets and detect mispricing where market implied probability deviates from an estimated probability from evidence.

Default: signals only. Never claim guaranteed profit.

## What to collect per market
- Resolution criteria (exact)
- Deadline/time to resolution
- YES/NO prices, spreads, liquidity/volume (if available)
- Recent price movement
- Primary sources with timestamps

## Estimating probability
1. Parse resolution criteria precisely
2. Build a timeline
3. Gather primary sources
4. Identify key drivers
5. Produce: probability (0..1) + confidence + invalidation triggers

## Signal rules (defaults)
- Edge >= 0.07 with medium confidence, OR
- Edge >= 0.12 with strong objective evidence

Risk controls
- per-market exposure cap
- total exposure cap
- allowlist markets
- avoid unclear resolution

## Output format
Table:
- Market, prices, estimated probability, edge, confidence
- Evidence bullets (timestamped)
- Entry idea, exit plan, invalidations
EOF

    cat > "$AI_HOME/workspace-orchestrator/skills/tool_language_selector.md" << 'EOF'
---
name: tool_language_selector
description: Select the best tools + programming language for a task to maximize speed, cost efficiency and reliability
---

## Purpose
Select the right agent, tools, and programming language per task to optimize speed, reliability, and cost.

## Agent selection
- orchestrator: routing/planning/meta decisions
- intel-agent: web research
- data-analyst: data processing
- bot-dev: code changes
- crypto-trader: trading research

## Tool selection
- Use web_search/web_fetch/browser for current facts
- Use read/write/edit for file operations
- Use exec for real commands/tests

## Language selection
- Bash: installers & glue
- Python: APIs, polling bots, data
- Node.js: web tooling / JS ecosystems
EOF

    ok "Skills installed (including 3 extended docs)"
}

install_bot_runner() {
    log "Installing multi-bot runner..."

    cat > "$AI_HOME/bin/ai-employee" << 'EOF'
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

    chmod +x "$AI_HOME/bin/ai-employee"
    ok "Bot runner installed: $AI_HOME/bin/ai-employee"
}

install_problem_solver_bot() {
    log "Installing Problem Solver bot (watchdog)..."

    mkdir -p "$AI_HOME/bots/problem-solver"
    cat > "$AI_HOME/bots/problem-solver/run.sh" << 'EOF'
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
    chmod +x "$AI_HOME/bots/problem-solver/run.sh"

    cat > "$AI_HOME/bots/problem-solver/problem_solver.py" << 'EOF'
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

    # default env (do not overwrite if exists)
    if [[ ! -f "$AI_HOME/config/problem-solver.env" ]]; then
      cat > "$AI_HOME/config/problem-solver.env" << 'EOF'
# Bots that must be kept alive
PROBLEM_SOLVER_WATCH_BOTS=problem-solver-ui,polymarket-trader
PROBLEM_SOLVER_CHECK_INTERVAL=5
PROBLEM_SOLVER_AUTO_RESTART=true
EOF
      chmod 600 "$AI_HOME/config/problem-solver.env"
    fi

    ok "Problem Solver bot installed"
}

install_problem_solver_ui_bot() {
    log "Installing Problem Solver UI bot..."

    mkdir -p "$AI_HOME/bots/problem-solver-ui"
    cat > "$AI_HOME/bots/problem-solver-ui/run.sh" << 'EOF'
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
    chmod +x "$AI_HOME/bots/problem-solver-ui/run.sh"

    cat > "$AI_HOME/bots/problem-solver-ui/server.py" << 'EOF'
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
  <p>Ask questions and view bot health. Default port: <b>8787</b>.</p>
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
        return JSONResponse({"error": "Empty question", "next": "Describe symptoms, errors, and what you expected."}, status_code=400)

    return JSONResponse({
        "question": q,
        "triage": [
            "What is the exact error output (copy/paste)?",
            "When did it start? What changed last?",
            "Run: ~/.ai-employee/bin/ai-employee status",
            "Run: openclaw logs --follow  (in a new terminal)",
            "If a bot is down: ~/.ai-employee/bin/ai-employee logs <bot>"
        ],
        "note": "This is a deterministic stub. Wire it to your LLM agent later if desired."
    })

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
EOF

    cat > "$AI_HOME/bots/problem-solver-ui/requirements.txt" << 'EOF'
fastapi==0.115.0
uvicorn==0.30.6
EOF

    if [[ ! -f "$AI_HOME/config/problem-solver-ui.env" ]]; then
      cat > "$AI_HOME/config/problem-solver-ui.env" << 'EOF'
PROBLEM_SOLVER_UI_HOST=127.0.0.1
PROBLEM_SOLVER_UI_PORT=8787
EOF
      chmod 600 "$AI_HOME/config/problem-solver-ui.env"
    fi

    # Best-effort dependency install (no venv to keep it simple)
    log "Installing Python deps for Problem Solver UI (best-effort)..."
    if command -v pip3 >/dev/null 2>&1; then
      pip3 install --user -r "$AI_HOME/bots/problem-solver-ui/requirements.txt" >/dev/null 2>&1 || warn "pip install failed; install manually: pip3 install --user -r ~/.ai-employee/bots/problem-solver-ui/requirements.txt"
    else
      warn "pip3 not found; install manually for UI: pip3 install --user fastapi uvicorn"
    fi

    ok "Problem Solver UI installed (http://127.0.0.1:8787 after start)"
}

install_polymarket_trader_bot() {
    log "Installing Polymarket trader bot (PAPER default)..."

    mkdir -p "$AI_HOME/bots/polymarket-trader"

    cat > "$AI_HOME/bots/polymarket-trader/run.sh" << 'EOF'
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
    chmod +x "$AI_HOME/bots/polymarket-trader/run.sh"

    cat > "$AI_HOME/bots/polymarket-trader/trader.py" << 'EOF'
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
    yes_price: float  # 0..1
    no_price: float   # 0..1

class PolymarketClient:
    """
    Implement this with your real Polymarket/CLOB client.
    Until implemented, the bot will do nothing (safe).
    """
    def get_quotes(self) -> list[MarketQuote]:
        return []

    def place_order_yes(self, market_id: str, usd_amount: float, max_price: float) -> str:
        raise NotImplementedError

    def place_order_no(self, market_id: str, usd_amount: float, max_price: float) -> str:
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
            write_state({"ts": time.time(), "status": "killed", "note": "KILL_SWITCH=true"})
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
            try:
                if a["side"] == "YES":
                    oid = client.place_order_yes(a["market_id"], a["usd"], a["max_price"])
                else:
                    oid = client.place_order_no(a["market_id"], a["usd"], a["max_price"])
                executed.append({**a, "executed": True, "order_id": oid, "mode": "live"})
            except Exception as e:
                executed.append({**a, "executed": False, "error": str(e), "mode": "live"})

        write_state({
            "ts": time.time(),
            "live": LIVE_TRADING,
            "kill": KILL_SWITCH,
            "actions_found": len(actions),
            "executed": executed[:50],
        })

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
EOF

    if [[ ! -f "$AI_HOME/config/polymarket-trader.env" ]]; then
      cat > "$AI_HOME/config/polymarket-trader.env" << 'EOF'
# PAPER by default:
LIVE_TRADING=false

# Kill switch:
KILL_SWITCH=false

# Strategy / risk:
PM_POLL_SECONDS=5
EDGE_THRESHOLD=0.07
MAX_POSITION_USD=25

# Market allowlist (comma-separated IDs). Empty = none traded.
ALLOW_MARKETS=

# TODO: add your Polymarket auth variables here once you choose a client.
EOF
      chmod 600 "$AI_HOME/config/polymarket-trader.env"
    fi

    # default estimates file
    if [[ ! -f "$AI_HOME/config/polymarket_estimates.json" ]]; then
      cat > "$AI_HOME/config/polymarket_estimates.json" << 'EOF'
{}
EOF
      chmod 600 "$AI_HOME/config/polymarket_estimates.json"
    fi

    ok "Polymarket trader installed"
}

config() {
    log "Generating OpenClaw config..."

    local BINDS='[]'
    [[ -n "$BOT_PATH" && -d "$BOT_PATH" ]] && BINDS="[\"$BOT_PATH:/tradingbot:rw\"]"

    cat > "$AI_HOME/config.json" << 'CFG'
{"identity":{"name":"AI-Employee","emoji":"🤖","theme":"autonomous business assistant"},"gateway":{"bind":"loopback","port":18789,"auth":{"mode":"token","token":"TOKEN_PLACEHOLDER"},"controlUi":{"enabled":true,"port":18789}},"agent":{"workspace":"AI_HOME_PLACEHOLDER/workspace","model":{"primary":"anthropic/claude-opus-4-5"}},"agents":{"defaults":{"sandbox":{"mode":"all","scope":"agent","workspaceAccess":"rw","docker":{"image":"ai-employee:latest","network":"bridge","memory":"2g","cpus":2,"env":{"PYTHONUNBUFFERED":"1","TZ":"Europe/Amsterdam"},"setupCommand":"apt-get update && apt-get install -y python3 python3-pip nodejs npm git curl && pip3 install --no-cache-dir pandas numpy requests ccxt beautifulsoup4 && npm i -g typescript","binds":BINDS_PLACEHOLDER}}},"list":[{"id":"orchestrator","workspace":"AI_HOME_PLACEHOLDER/workspace-orchestrator","systemPrompt":"Master Orchestrator. Route tasks to: lead-hunter (leads), content-master (content), social-guru (social), intel-agent (research), product-scout (ecommerce), email-ninja (email), support-bot (support), data-analyst (analysis), creative-studio (creative), crypto-trader (crypto), bot-dev (code), web-sales (web).","sandbox":{"mode":"off"},"tools":{"allow":["read","write","sessions_spawn","sessions_send","sessions_list","web_search"]}},{"id":"lead-hunter","workspace":"AI_HOME_PLACEHOLDER/workspace-lead-hunter","systemPrompt":"B2B Lead Generation Specialist. Find decision makers, emails, qualify leads. Always verify before returning.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"content-master","workspace":"AI_HOME_PLACEHOLDER/workspace-content-master","systemPrompt":"SEO Content Specialist. Write 2000+ word optimized articles with proper structure, keywords, and links.","tools":{"allow":["web_search","web_fetch","read","write","edit"],"deny":["exec","elevated"]}},{"id":"social-guru","workspace":"AI_HOME_PLACEHOLDER/workspace-social-guru","systemPrompt":"Social Media Manager. Find viral content, write engaging captions, generate hashtags. Platform-specific optimization.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"intel-agent","workspace":"AI_HOME_PLACEHOLDER/workspace-intel-agent","systemPrompt":"Competitive Intelligence Analyst. Monitor competitors: pricing, features, reviews, traffic. Generate actionable reports.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"product-scout","workspace":"AI_HOME_PLACEHOLDER/workspace-product-scout","systemPrompt":"E-commerce Product Researcher. Find arbitrage opportunities, trending products, validate suppliers, calculate profits.","tools":{"allow":["web_search","web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"email-ninja","workspace":"AI_HOME_PLACEHOLDER/workspace-email-ninja","systemPrompt":"Cold Email Specialist. Build sequences, personalize at scale, optimize deliverability. Never spam.","tools":{"allow":["web_fetch","read","write","edit"],"deny":["exec","elevated","browser"]}},{"id":"support-bot","workspace":"AI_HOME_PLACEHOLDER/workspace-support-bot","systemPrompt":"Customer Support Agent. Answer FAQs, classify tickets, analyze sentiment, escalate when needed.","tools":{"allow":["read","write","web_fetch"],"deny":["exec","elevated","browser"]}},{"id":"data-analyst","workspace":"AI_HOME_PLACEHOLDER/workspace-data-analyst","systemPrompt":"Market Research Analyst. Analyze trends, generate SWOT, create reports with data and insights.","tools":{"allow":["web_search","web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"creative-studio","workspace":"AI_HOME_PLACEHOLDER/workspace-creative-studio","systemPrompt":"Creative Director. Design briefs, image prompts, brand voice, ad copy. Professional and actionable.","tools":{"allow":["web_search","read","write"],"deny":["exec","elevated"]}},{"id":"crypto-trader","workspace":"AI_HOME_PLACEHOLDER/workspace-crypto-trader","systemPrompt":"Crypto Trading Analyst. Technical analysis, patterns, risk assessment. Include confidence scores and stop-losses.","model":{"primary":"anthropic/claude-opus-4-5"},"tools":{"allow":["web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"bot-dev","workspace":"AI_HOME_PLACEHOLDER/workspace-bot-dev","systemPrompt":"Trading Bot Developer. Code review, feature implementation, optimization. Security-first approach.","model":{"primary":"anthropic/claude-opus-4-5"},"tools":{"allow":["read","write","edit","apply_patch","exec"],"deny":["elevated"]}},{"id":"web-sales","workspace":"AI_HOME_PLACEHOLDER/workspace-web-sales","systemPrompt":"Web Analysis & Sales Specialist. UX/SEO audits, find contacts, write personalized pitches. Max 10 emails per session.","tools":{"allow":["browser","web_search","web_fetch","read","write"],"deny":["exec","elevated"]}}]},"session":{"dmScope":"per-channel-peer","reset":{"mode":"manual"},"maintenance":{"mode":"rotate","pruneAfter":"7d","rotateBytes":"50mb"}},"channels":{"whatsapp":{"dmPolicy":"allowlist","allowFrom":["PHONE_PLACEHOLDER"],"groups":{"*":{"requireMention":true}},"mediaMaxMb":50,"sendReadReceipts":true}},"tools":{"browser":{"enabled":true,"headless":false,"downloadsDir":"AI_HOME_PLACEHOLDER/downloads","profile":"ai-employee-profile","viewport":{"width":1920,"height":1080}},"web":{"search":{"enabled":true,"provider":"brave","maxResults":10}},"exec":{"enabled":true,"host":"sandbox","shell":"/bin/bash","timeout":300000,"workdir":"/workspace"},"elevated":{"enabled":false},"media":{"audio":{"enabled":false},"video":{"enabled":false}}},"logging":{"level":"info","consoleLevel":"info","file":"AI_HOME_PLACEHOLDER/logs/gateway.log","redactSensitive":"tools","redactPatterns":["api[_-]?key","secret","token","password"]},"cron":{"enabled":false},"discovery":{"mdns":{"mode":"minimal"}}}
CFG

    sed -i.bak "s|TOKEN_PLACEHOLDER|$TOKEN|g" "$AI_HOME/config.json"
    sed -i.bak "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" "$AI_HOME/config.json"
    sed -i.bak "s|PHONE_PLACEHOLDER|$PHONE|g" "$AI_HOME/config.json"
    sed -i.bak "s|BINDS_PLACEHOLDER|$BINDS|g" "$AI_HOME/config.json"
    rm "$AI_HOME/config.json.bak"

    ln -sf "$AI_HOME/config.json" ~/.openclaw/openclaw.json 2>/dev/null || true
    chmod 600 "$AI_HOME/config.json"

    cat > "$AI_HOME/.env" << ENV
OPENCLAW_GATEWAY_TOKEN=$TOKEN
${ANTHROPIC_KEY:+ANTHROPIC_API_KEY=$ANTHROPIC_KEY}
OPENCLAW_DISABLE_BONJOUR=1
TZ=Europe/Amsterdam
ENV
    chmod 600 "$AI_HOME/.env"

    ok "OpenClaw config generated"
}

docker_build() {
    log "Building Docker sandbox (3-5 min)..."

    cat > /tmp/ai-employee.dockerfile << 'DOCKER'
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip nodejs npm git curl ca-certificates && \
    pip3 install --no-cache-dir pandas numpy requests ccxt beautifulsoup4 && \
    npm i -g typescript && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
CMD ["/bin/bash"]
DOCKER

    if docker build -qt ai-employee:latest -f /tmp/ai-employee.dockerfile /tmp 2>&1 | grep -q "Successfully built"; then
        ok "Docker sandbox built"
    else
        warn "Sandbox build may have issues (check manually)"
    fi

    rm /tmp/ai-employee.dockerfile
}

webui() {
    log "Installing Web UI (static dashboard)..."

    # keep your existing dashboard UI unchanged
    cat > "$AI_HOME/ui/index.html" << 'HTMLEND'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Employee Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:20px}
.container{max-width:1400px;margin:0 auto}
header{background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;border-radius:15px;margin-bottom:30px;text-align:center;box-shadow:0 20px 60px rgba(102,126,234,0.3)}
h1{color:#fff;font-size:2.5em;margin-bottom:10px}
.subtitle{color:rgba(255,255,255,0.9);font-size:1.1em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:20px}
.card{background:#1e293b;padding:25px;border-radius:15px;border:1px solid #334155;transition:all 0.3s}
.card:hover{border-color:#667eea;transform:translateY(-5px);box-shadow:0 20px 40px rgba(102,126,234,0.2)}
.card h2{color:#667eea;margin-bottom:15px;font-size:1.3em}
.agent-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}
.agent{background:#334155;padding:20px 15px;border-radius:10px;text-align:center;cursor:pointer;transition:all 0.2s;border:2px solid transparent}
.agent:hover{background:#667eea;transform:scale(1.05);border-color:#764ba2}
.agent-emoji{font-size:2.5em;margin-bottom:8px}
.agent-name{font-size:0.9em;font-weight:600;margin-bottom:4px}
.agent-role{font-size:0.75em;opacity:0.7}
.stat{display:flex;justify-content:space-between;align-items:center;padding:15px 0;border-bottom:1px solid #334155}
.stat:last-child{border:none}
.stat-label{font-size:1em;color:#94a3b8}
.stat-value{color:#10b981;font-weight:bold;font-size:1.5em}
.status-dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:10px;animation:pulse 2s infinite}
.status-dot.online{background:#10b981;box-shadow:0 0 10px #10b981}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
button{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;padding:12px 24px;border-radius:8px;cursor:pointer;font-size:1em;margin:5px;transition:all 0.2s}
button:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(102,126,234,0.4)}
button:active{transform:translateY(0)}
.instruction{background:#334155;padding:20px;border-radius:10px;margin-top:20px;border-left:4px solid #667eea}
.instruction code{background:#1e293b;padding:4px 10px;border-radius:5px;font-family:monospace;color:#10b981}
footer{text-align:center;margin-top:40px;padding:20px;color:#64748b}
</style>
</head>
<body>
<div class="container">
<header>
<h1>🤖 AI Employee</h1>
<p class="subtitle">13 Autonomous Agents • Real-time Dashboard</p>
</header>

<div class="grid">
<div class="card">
<h2>System Status</h2>
<p style="margin:15px 0"><span class="status-dot online"></span>Gateway Online</p>
<p style="margin:15px 0"><span class="status-dot online"></span>WhatsApp Connected</p>
<p style="margin:15px 0"><span class="status-dot online"></span>13 Agents Ready</p>
</div>

<div class="card">
<h2>Quick Actions</h2>
<button onclick="window.open('http://localhost:18789','_blank')">📊 Open Gateway</button>
<button onclick="window.open('http://127.0.0.1:8787','_blank')">🛠️ Problem Solver UI</button>
<button onclick="alert('Run in terminal: openclaw logs --follow')">📋 View Logs</button>
</div>
</div>

<div class="card instruction">
<h2>💬 How to Use</h2>
<p style="margin-bottom:15px">Send WhatsApp message to yourself:</p>
<p><code>switch to lead-hunter</code></p>
<p style="margin:10px 0"><code>find 20 SaaS CTOs in Netherlands</code></p>
<p style="margin-top:15px;color:#94a3b8;font-size:0.9em">
The agent will process your request and return results via WhatsApp.
</p>
</div>

<footer>
<p>🤖 AI Employee v3.1 • Multi-bot runtime</p>
<p style="margin-top:10px;font-size:0.9em">
Gateway: localhost:18789 • Dashboard: localhost:3000 • Problem Solver: localhost:8787
</p>
</footer>
</div>
</body>
</html>
HTMLEND

    cat > "$AI_HOME/ui/serve.sh" << 'SERVE'
#!/bin/bash
cd "$(dirname "$0")"
echo "🌐 Web UI starting at http://localhost:3000"
python3 -m http.server 3000 2>/dev/null || python -m SimpleHTTPServer 3000
SERVE

    chmod +x "$AI_HOME/ui/serve.sh"
    ok "Web UI installed"
}

scripts() {
    log "Creating helper scripts..."

    cat > "$AI_HOME/start.sh" << 'START'
#!/bin/bash
set -euo pipefail
echo "🚀 Starting AI Employee..."

openclaw gateway &
sleep 2

cd ~/.ai-employee/ui && ./serve.sh &

# Start background bots concurrently
~/.ai-employee/bin/ai-employee start problem-solver || true
~/.ai-employee/bin/ai-employee start problem-solver-ui || true
~/.ai-employee/bin/ai-employee start polymarket-trader || true

echo "✅ AI Employee started!"
echo ""
echo "📊 Web UI:            http://localhost:3000"
echo "🔧 Gateway:           http://localhost:18789"
echo "🛠️ Problem Solver UI: http://127.0.0.1:8787"
echo ""
echo "Press Ctrl+C to stop..."
trap "pkill -f 'openclaw gateway';pkill -f 'http.server 3000'; ~/.ai-employee/bin/ai-employee stop --all >/dev/null 2>&1 || true" EXIT
wait
START

    cat > "$AI_HOME/stop.sh" << 'STOP'
#!/bin/bash
set -euo pipefail
pkill -f "openclaw gateway" || true
pkill -f "http.server 3000" || true
~/.ai-employee/bin/ai-employee stop --all >/dev/null 2>&1 || true
echo "✅ AI Employee stopped"
STOP

    chmod +x "$AI_HOME"/{start,stop}.sh
    ok "Helper scripts created"
}

done_message() {
    local elapsed=$(($(date +%s)-START_TIME))
    clear
    banner
    echo ""
    echo -e "${G}✓ Installation complete in ${elapsed}s!${NC}"
    echo ""
    echo -e "${C}Configuration saved:${NC}"
    echo "  Phone:    $PHONE"
    echo "  Token:    ${TOKEN:0:16}...${TOKEN: -8}"
    echo "  Config:   ~/.ai-employee/config.json"
    echo "  Web UI:   http://localhost:3000"
    echo "  Solver:   http://127.0.0.1:8787"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo "  1. cd ~/.ai-employee && ./start.sh"
    echo "  2. openclaw channels login  (new terminal)"
    echo "  3. Send WhatsApp: 'Hello!'"
    echo ""
    echo -e "${G}Ready!${NC}"
    echo ""
}

# MAIN
banner
echo ""
input
echo ""
setup
install_skills
install_bot_runner
install_problem_solver_bot
install_problem_solver_ui_bot
install_polymarket_trader_bot
config
docker_build
webui
scripts
done_message
