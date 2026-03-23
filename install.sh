#!/usr/bin/env bash
# AI Employee — Main Installer v4.0 (runtime-first)
# Called by quick-install.sh
set -euo pipefail

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; C='\033[0;36m'; M='\033[0;35m'; NC='\033[0m'

AI_HOME="$HOME/.ai-employee"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
START_TIME=$(date +%s)
CONFIG_FILES_UPDATED=0

log()   { echo -e "${C}▸${NC} $1"; }
ok()    { echo -e "${G}✓${NC} $1"; }
warn()  { echo -e "${Y}⚠${NC} $1"; }
err()   { echo -e "${R}✗${NC} $1"; exit 1; }
step()  { echo ""; echo -e "${M}━━━ $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo ""; }
info()  { echo -e "    ${B}$1${NC}"; }
ask()   { echo -e "${Y}?${NC} $1"; }

banner() {
cat << 'EOF'
╔══════════════════════════════════════════════════════════╗
║          AI EMPLOYEE — Installer v4.0                    ║
║   Runtime-first • Wizard • WhatsApp • Auto-open UI       ║
╚══════════════════════════════════════════════════════════╝
EOF
}

# ─── Requirements ─────────────────────────────────────────────────────────────

check_requirements() {
    step "1/8 — Checking requirements"

    [ "$EUID" -eq 0 ] && err "Do not run as root. Run as your regular user."

    local missing=()
    command -v curl    >/dev/null 2>&1 || missing+=("curl")
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v openssl >/dev/null 2>&1 || missing+=("openssl")

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required dependencies: ${missing[*]}
Install them with your package manager, e.g.:
  sudo apt install curl python3 openssl   # Debian/Ubuntu/Linux Mint
  brew install python3 openssl             # macOS"
    fi

    if command -v node >/dev/null 2>&1; then
        local NODE_V
        NODE_V=$(node -v 2>/dev/null | cut -d'v' -f2 | cut -d'.' -f1 || echo "0")
        [[ "$NODE_V" -lt 20 ]] && warn "Node.js 20+ recommended (you have v${NODE_V:-?}). Upgrade if issues occur." || ok "Node.js $(node -v)"
    else
        warn "Node.js not found (optional but recommended)"
    fi

    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            ok "Docker: running"
        else
            warn "Docker installed but not running. Sandbox mode disabled."
        fi
    else
        warn "Docker not found. Agents will run in local exec mode."
    fi

    ok "Requirements checked"
}

# ─── OpenClaw ─────────────────────────────────────────────────────────────────

install_openclaw() {
    step "2/8 — OpenClaw gateway"

    if command -v openclaw >/dev/null 2>&1; then
        local ver
        ver=$(openclaw --version 2>/dev/null || echo "unknown")
        ok "OpenClaw already installed: $ver"
        return
    fi

    log "OpenClaw not found. Attempting install..."
    if curl -fsSL https://openclaw.ai/install.sh | bash; then
        export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
        ok "OpenClaw installed"
    else
        warn "OpenClaw auto-install failed. Install manually:
  curl -fsSL https://openclaw.ai/install.sh | bash
  Then re-run this installer."
    fi
}

# ─── Ollama ───────────────────────────────────────────────────────────────────

install_ollama() {
    local want_ollama="$1"
    [[ "$want_ollama" != "y" ]] && return 0

    step "3/8 — Ollama (local LLM)"

    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama already installed"
        return
    fi

    log "Installing Ollama..."
    if curl -fsSL https://ollama.ai/install.sh | sh; then
        ok "Ollama installed"
    else
        warn "Ollama auto-install failed. Install manually: https://ollama.ai/download"
    fi
}

# ─── Wizard ───────────────────────────────────────────────────────────────────

wizard() {
    step "4/8 — Configuration wizard"
    info "Answer each question (press Enter for default)."
    echo ""

    # 1) WhatsApp phone
    ask "WhatsApp phone number in E.164 format (e.g. +31612345678):"
    read -r PHONE
    while [[ ! $PHONE =~ ^\+[0-9]{7,15}$ ]]; do
        warn "Invalid format. Use E.164: +<country_code><number> (e.g. +31612345678)"
        ask "WhatsApp phone number:"
        read -r PHONE
    done
    ok "Phone: $PHONE"

    # 2) Local LLM
    echo ""
    ask "Use Ollama for local LLM? (recommended for privacy) [y/N]:"
    read -r WANT_OLLAMA
    WANT_OLLAMA="${WANT_OLLAMA:-n}"
    WANT_OLLAMA=$(echo "$WANT_OLLAMA" | tr '[:upper:]' '[:lower:]')
    OLLAMA_MODEL="llama3.2"
    if [[ "$WANT_OLLAMA" == "y" ]]; then
        ask "Ollama model name [default: llama3.2]:"
        read -r OLLAMA_MODEL_INPUT
        OLLAMA_MODEL="${OLLAMA_MODEL_INPUT:-llama3.2}"
        MODEL_PRIMARY="ollama/$OLLAMA_MODEL"
        ok "Ollama model: $OLLAMA_MODEL"
    else
        MODEL_PRIMARY="anthropic/claude-opus-4-5"
        ok "Using cloud LLM (set API key below)"
    fi

    # 3) Anthropic API key
    echo ""
    ask "Anthropic API key (optional, Enter to skip):"
    read -rsp "" ANTHROPIC_KEY; echo
    [[ -n "$ANTHROPIC_KEY" ]] && ok "Anthropic key: set" || info "Anthropic key: skipped"

    # 4) OpenAI API key
    ask "OpenAI API key (optional, Enter to skip):"
    read -rsp "" OPENAI_KEY; echo
    [[ -n "$OPENAI_KEY" ]] && ok "OpenAI key: set" || info "OpenAI key: skipped"

    # 5) Trading bot path
    echo ""
    ask "Path to trading bot directory (optional, Enter to skip):"
    read -r BOT_PATH
    BOT_PATH="${BOT_PATH/#\~/$HOME}"
    if [[ -n "$BOT_PATH" && -d "$BOT_PATH" ]]; then
        ok "Trading bot path: $BOT_PATH"
    elif [[ -n "$BOT_PATH" ]]; then
        warn "Path does not exist ($BOT_PATH) — skipping"
        BOT_PATH=""
    else
        info "Trading bot path: skipped"
    fi

    # 6) Hourly status reports
    echo ""
    ask "Enable hourly WhatsApp status updates? [Y/n]:"
    read -r WANT_STATUS
    WANT_STATUS="${WANT_STATUS:-y}"
    STATUS_INTERVAL=3600
    if [[ ! "$WANT_STATUS" =~ ^[Nn] ]]; then
        ok "Status reports: every hour"
    else
        ask "Status interval in seconds [default: 3600]:"
        read -r STATUS_INTERVAL_INPUT
        STATUS_INTERVAL="${STATUS_INTERVAL_INPUT:-3600}"
        ok "Status interval: ${STATUS_INTERVAL}s"
    fi

    # 7) UI ports
    echo ""
    ask "Dashboard port [default: 3000]:"
    read -r DASHBOARD_PORT_INPUT
    DASHBOARD_PORT="${DASHBOARD_PORT_INPUT:-3000}"

    ask "Problem Solver UI port [default: 8787]:"
    read -r UI_PORT_INPUT
    UI_PORT="${UI_PORT_INPUT:-8787}"
    ok "Ports: dashboard=$DASHBOARD_PORT, ui=$UI_PORT"

    # 8) Number of workers
    echo ""
    ask "How many AI agents to enable? (1-13, default 13 = all):"
    read -r WORKERS_INPUT
    WORKERS="${WORKERS_INPUT:-13}"
    [[ "$WORKERS" =~ ^[0-9]+$ ]] || { warn "Invalid number; using 13"; WORKERS=13; }
    if (( WORKERS > 13 )); then warn "Maximum is 13; clamping to 13"; WORKERS=13; fi
    if (( WORKERS < 1  )); then warn "Minimum is 1; clamping to 1";  WORKERS=1;  fi
    ok "Workers: $WORKERS enabled"

    TOKEN=$(openssl rand -hex 32)
    ok "Wizard complete"
}

# ─── Directory structure ───────────────────────────────────────────────────────

setup_directories() {
    step "5/8 — Creating directory structure"

    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups,bin,run,bots,config,state,improvements}

    for a in orchestrator lead-hunter content-master social-guru intel-agent product-scout \
              email-ninja support-bot data-analyst creative-studio crypto-trader bot-dev web-sales; do
        mkdir -p "$AI_HOME/workspace-$a/skills"
    done

    chmod 700 "$AI_HOME/credentials"
    ok "Directories created"
}

# ─── Install runtime files ────────────────────────────────────────────────────

install_runtime() {
    step "6/8 — Installing runtime files"

    local src="$RUNTIME_DIR"

    if [[ ! -d "$src" ]]; then
        log "Runtime dir not found locally. Downloading from GitHub..."
        local TMP_RUNTIME
        TMP_RUNTIME=$(mktemp -d)
        local BASE_URL="https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main"

        dl() {
            local rel="$1"
            mkdir -p "$TMP_RUNTIME/$(dirname "$rel")"
            curl -fsSL "$BASE_URL/runtime/$rel" -o "$TMP_RUNTIME/$rel" || warn "Could not download $rel"
        }

        dl "bin/ai-employee"
        dl "bots/problem-solver/run.sh"
        dl "bots/problem-solver/problem_solver.py"
        dl "bots/problem-solver-ui/run.sh"
        dl "bots/problem-solver-ui/server.py"
        dl "bots/problem-solver-ui/requirements.txt"
        dl "bots/polymarket-trader/run.sh"
        dl "bots/polymarket-trader/trader.py"
        dl "bots/status-reporter/run.sh"
        dl "bots/status-reporter/status_reporter.py"
        dl "bots/scheduler-runner/run.sh"
        dl "bots/scheduler-runner/scheduler.py"
        dl "bots/discovery/run.sh"
        dl "bots/discovery/discovery.py"
        dl "config/openclaw.template.json"
        dl "config/problem-solver.env"
        dl "config/problem-solver-ui.env"
        dl "config/status-reporter.env"
        dl "config/scheduler-runner.env"
        dl "config/discovery.env"
        dl "config/polymarket-trader.env"
        dl "config/polymarket_estimates.json"
        dl "config/schedules.json"
        dl "start.sh"
        dl "stop.sh"

        src="$TMP_RUNTIME"
    fi

    # bin/
    mkdir -p "$AI_HOME/bin"
    cp -f "$src/bin/ai-employee" "$AI_HOME/bin/ai-employee"
    chmod +x "$AI_HOME/bin/ai-employee"

    # bots/ (overwrite code; never overwrite .env)
    for bot_dir in "$src/bots"/*/; do
        bot_name="$(basename "$bot_dir")"
        mkdir -p "$AI_HOME/bots/$bot_name"
        for f in "$bot_dir"*; do
            [[ -f "$f" ]] || continue
            fname="$(basename "$f")"
            cp -f "$f" "$AI_HOME/bots/$bot_name/$fname"
            [[ "$f" == *.sh ]] && chmod +x "$AI_HOME/bots/$bot_name/$fname"
        done
    done

    # start.sh / stop.sh
    cp -f "$src/start.sh" "$AI_HOME/start.sh"
    cp -f "$src/stop.sh"  "$AI_HOME/stop.sh"
    chmod +x "$AI_HOME/start.sh" "$AI_HOME/stop.sh"

    # config templates (only if file does NOT yet exist — never overwrite user config)
    mkdir -p "$AI_HOME/config"
    for f in "$src/config"/*; do
        [[ -f "$f" ]] || continue
        fname="$(basename "$f")"
        if [[ ! -f "$AI_HOME/config/$fname" ]]; then
            cp "$f" "$AI_HOME/config/$fname"
            CONFIG_FILES_UPDATED=$((CONFIG_FILES_UPDATED + 1))
        fi
    done

    ok "Runtime files installed"

    # Python deps
    local req="$AI_HOME/bots/problem-solver-ui/requirements.txt"
    if [[ -f "$req" ]]; then
        if command -v pip3 >/dev/null 2>&1; then
            pip3 install --user -q -r "$req" 2>/dev/null \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip3 install failed. Run: pip3 install --user fastapi uvicorn"
        else
            warn "pip3 not found. Run: pip3 install --user fastapi uvicorn"
        fi
    fi
}

# ─── Skills ───────────────────────────────────────────────────────────────────

install_skills() {
    log "Installing agent skills..."

    local all_skills=(
        "lead-hunter:linkedin_scraper:Find decision makers on LinkedIn"
        "lead-hunter:email_finder:Find and verify email addresses"
        "lead-hunter:lead_scorer:Score lead quality 0-100"
        "lead-hunter:company_enrichment:Enrich company data"
        "content-master:keyword_research:SEO keyword research"
        "content-master:blog_writer:Write 2000+ word SEO articles"
        "content-master:content_optimizer:Optimize existing content"
        "social-guru:viral_finder:Find trending viral content"
        "social-guru:caption_writer:Write platform-specific captions"
        "social-guru:hashtag_generator:Generate relevant hashtags"
        "social-guru:content_calendar:Create 30-day content calendar"
        "intel-agent:pricing_tracker:Track competitor pricing"
        "intel-agent:review_scraper:Scrape and analyze reviews"
        "intel-agent:feature_comparison:Compare features with competitors"
        "intel-agent:traffic_estimator:Estimate competitor traffic"
        "product-scout:arbitrage_finder:Find AliExpress to Amazon arbitrage"
        "product-scout:trend_spotter:Find trending products"
        "product-scout:supplier_validator:Validate supplier reliability"
        "product-scout:profit_calculator:Calculate true profit"
        "email-ninja:sequence_builder:Build cold email sequences"
        "email-ninja:deliverability_checker:Check email deliverability"
        "email-ninja:personalization_engine:Personalize emails at scale"
        "support-bot:faq_trainer:Extract FAQs from docs"
        "support-bot:ticket_classifier:Classify support tickets"
        "support-bot:sentiment_analyzer:Analyze customer sentiment"
        "data-analyst:trend_analyzer:Analyze market trends"
        "data-analyst:swot_generator:Generate SWOT analysis"
        "data-analyst:survey_analyzer:Analyze survey responses"
        "creative-studio:design_brief:Create design briefs"
        "creative-studio:image_prompt:Generate AI image prompts"
        "creative-studio:brand_voice:Define brand voice"
        "creative-studio:ad_copy:Write ad copy"
        "crypto-trader:technical_analysis:Full technical analysis"
        "crypto-trader:pattern_recognition:Identify chart patterns"
        "crypto-trader:whale_tracker:Track large wallet movements"
        "crypto-trader:prediction_markets_research:Scan prediction markets for mispricing"
        "bot-dev:code_review:Review code for issues"
        "bot-dev:feature_implementation:Implement new features"
        "bot-dev:bug_finder:Find bugs in code"
        "web-sales:ux_audit:Audit website UX"
        "web-sales:seo_audit:Technical SEO audit"
        "web-sales:speed_test:Website speed analysis"
        "orchestrator:complex_problem_solving:Complex problem solving for system issues"
        "orchestrator:tool_language_selector:Select best tools and language for a task"
    )

    for skill in "${all_skills[@]}"; do
        IFS=':' read -r agent skill_name desc <<< "$skill"
        local skill_file="$AI_HOME/workspace-$agent/skills/${skill_name}.md"
        if [[ ! -f "$skill_file" ]]; then
            cat > "$skill_file" << SKILL
---
name: $skill_name
description: $desc
---
Use this skill to $desc. Provide structured output with clear, actionable results.
SKILL
        fi
    done

    ok "Skills installed"
}

# ─── Config files ─────────────────────────────────────────────────────────────

generate_configs() {
    step "7/8 — Generating configuration"

    local template="$RUNTIME_DIR/config/openclaw.template.json"
    [[ -f "$template" ]] || template="$AI_HOME/config/openclaw.template.json"

    if [[ ! -f "$AI_HOME/config.json" ]]; then
        if [[ -f "$template" ]]; then
            cp "$template" "$AI_HOME/config.json"
        else
            # Minimal fallback
            cat > "$AI_HOME/config.json" << 'CFG_END'
{
  "gateway": {
    "mode": "local",
    "bind": "loopback",
    "port": 18789,
    "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
    "controlUi": { "enabled": true, "port": 18789 }
  },
  "channels": {
    "whatsapp": { "dmPolicy": "allowlist", "allowFrom": ["PHONE_PLACEHOLDER"] }
  },
  "cron": { "enabled": true },
  "discovery": { "mdns": { "mode": "off" } }
}
CFG_END
        fi
        sed -i.bak \
            -e "s|TOKEN_PLACEHOLDER|$TOKEN|g" \
            -e "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" \
            -e "s|PHONE_PLACEHOLDER|$PHONE|g" \
            -e "s|MODEL_PLACEHOLDER|$MODEL_PRIMARY|g" \
            "$AI_HOME/config.json"
        rm -f "$AI_HOME/config.json.bak"
        chmod 600 "$AI_HOME/config.json"
        ok "OpenClaw config.json created"
    else
        # Existing config: patch gateway.mode=local if missing (fixes old installs)
        if ! grep -q '"mode".*"local"' "$AI_HOME/config.json" 2>/dev/null; then
            warn "Existing config.json missing gateway.mode=local — backing up and replacing"
            cp "$AI_HOME/config.json" "$AI_HOME/config.json.bak.$(date +%s)"
            if [[ -f "$template" ]]; then
                cp "$template" "$AI_HOME/config.json"
            else
                cat > "$AI_HOME/config.json" << 'CFG_END'
{
  "gateway": {
    "mode": "local",
    "bind": "loopback",
    "port": 18789,
    "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
    "controlUi": { "enabled": true, "port": 18789 }
  },
  "channels": {
    "whatsapp": { "dmPolicy": "allowlist", "allowFrom": ["PHONE_PLACEHOLDER"] }
  },
  "cron": { "enabled": true },
  "discovery": { "mdns": { "mode": "off" } }
}
CFG_END
            fi
            sed -i.bak \
                -e "s|TOKEN_PLACEHOLDER|$TOKEN|g" \
                -e "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" \
                -e "s|PHONE_PLACEHOLDER|$PHONE|g" \
                -e "s|MODEL_PLACEHOLDER|$MODEL_PRIMARY|g" \
                "$AI_HOME/config.json"
            rm -f "$AI_HOME/config.json.bak"
            chmod 600 "$AI_HOME/config.json"
            ok "OpenClaw config.json updated (gateway.mode=local added)"
        else
            ok "OpenClaw config.json already exists — not overwritten"
        fi
    fi

    # Symlink for openclaw (always ensure it points to current config)
    mkdir -p "$HOME/.openclaw"
    ln -sf "$AI_HOME/config.json" "$HOME/.openclaw/openclaw.json" 2>/dev/null || true

    # .env file
    if [[ ! -f "$AI_HOME/.env" ]]; then
        {
            echo "OPENCLAW_GATEWAY_TOKEN=$TOKEN"
            [[ -n "${ANTHROPIC_KEY:-}" ]] && echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY"
            [[ -n "${OPENAI_KEY:-}" ]]    && echo "OPENAI_API_KEY=$OPENAI_KEY"
            echo "OPENCLAW_DISABLE_BONJOUR=1"
            echo "DASHBOARD_PORT=${DASHBOARD_PORT:-3000}"
            echo "TZ=Europe/Amsterdam"
        } > "$AI_HOME/.env"
        chmod 600 "$AI_HOME/.env"
        ok ".env created"
    else
        ok ".env already exists — not overwritten"
    fi

    # Patch status-reporter.env
    local sr_env="$AI_HOME/config/status-reporter.env"
    if [[ -f "$sr_env" ]]; then
        grep -q "^WHATSAPP_PHONE=" "$sr_env" || \
            echo "WHATSAPP_PHONE=$PHONE" >> "$sr_env"
        grep -q "^OPENCLAW_GATEWAY_TOKEN=" "$sr_env" || \
            echo "OPENCLAW_GATEWAY_TOKEN=$TOKEN" >> "$sr_env"
        sed -i.bak "s|^STATUS_REPORT_INTERVAL_SECONDS=.*|STATUS_REPORT_INTERVAL_SECONDS=${STATUS_INTERVAL:-3600}|" "$sr_env"
        rm -f "${sr_env}.bak"
        chmod 600 "$sr_env"
    fi

    # Patch problem-solver-ui.env
    local ui_env="$AI_HOME/config/problem-solver-ui.env"
    if [[ -f "$ui_env" ]]; then
        sed -i.bak "s|^PROBLEM_SOLVER_UI_PORT=.*|PROBLEM_SOLVER_UI_PORT=${UI_PORT:-8787}|" "$ui_env"
        rm -f "${ui_env}.bak"
        chmod 600 "$ui_env"
    fi

    ok "Configuration complete"
}

# ─── Static dashboard ─────────────────────────────────────────────────────────

install_dashboard_ui() {
    mkdir -p "$AI_HOME/ui"

    cat > "$AI_HOME/ui/index.html" << 'HTMLEND'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Employee</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:20px}
.container{max-width:1000px;margin:0 auto}
header{background:linear-gradient(135deg,#667eea,#764ba2);padding:28px;border-radius:15px;margin-bottom:28px;text-align:center}
h1{color:#fff;font-size:2.2em;margin-bottom:8px}
.sub{color:rgba(255,255,255,.85)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:16px}
.card{background:#1e293b;padding:22px;border-radius:12px;border:1px solid #334155}
.card h2{color:#667eea;margin-bottom:14px;font-size:1.1em}
.btn{display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:.9em;margin:4px;text-decoration:none}
.stat{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #334155}
.stat:last-child{border:none}
.stat-val{color:#10b981;font-weight:bold}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:8px;background:#10b981;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
code{background:#334155;padding:2px 8px;border-radius:4px;font-family:monospace;color:#10b981;font-size:.9em}
footer{text-align:center;margin-top:32px;color:#64748b;font-size:.9em}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>🤖 AI Employee</h1>
  <p class="sub">Autonomous Multi-Agent System</p>
</header>
<div class="grid">
  <div class="card">
    <h2>System Status</h2>
    <div class="stat"><span><span class="dot"></span>Gateway</span><span class="stat-val" id="gw-status">checking...</span></div>
    <div class="stat"><span><span class="dot"></span>Dashboard</span><span class="stat-val" id="ui-status">checking...</span></div>
  </div>
  <div class="card">
    <h2>Quick Access</h2>
    <a class="btn" href="http://127.0.0.1:8787" target="_blank">🛠️ Full Dashboard</a>
    <a class="btn" href="http://localhost:18789" target="_blank">📡 Gateway</a>
  </div>
</div>
<div class="card">
  <h2>💬 WhatsApp Commands</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
    <div><code>status</code> — get status report</div>
    <div><code>workers</code> — list active workers</div>
    <div><code>switch to &lt;agent&gt;</code> — change agent</div>
    <div><code>schedule</code> — list tasks</div>
    <div><code>improvements</code> — pending proposals</div>
    <div><code>help</code> — all commands</div>
  </div>
</div>
<footer>
  <p>🤖 AI Employee v4.0 • <a href="http://127.0.0.1:8787" style="color:#667eea">Open full dashboard →</a></p>
</footer>
</div>
<script>
async function check(url, id) {
  try { await fetch(url,{mode:'no-cors',signal:AbortSignal.timeout(2000)}); document.getElementById(id).textContent='Online'; document.getElementById(id).style.color='#10b981'; }
  catch { document.getElementById(id).textContent='Offline'; document.getElementById(id).style.color='#ef4444'; }
}
check('http://localhost:18789','gw-status');
check('http://127.0.0.1:8787','ui-status');
</script>
</body>
</html>
HTMLEND
    ok "Dashboard UI installed"
}

# ─── Startup message ──────────────────────────────────────────────────────────

queue_startup_message() {
    local f="$AI_HOME/state/startup_message.json"
    if [[ ! -f "$f" ]]; then
        cat > "$f" << MSG
{
  "pending": true,
  "message": "🤖 *AI Employee installed!*\n\nSend me a task:\n• switch to lead-hunter\n• find 20 SaaS CTOs\n• status\n• help\n\nDashboard: http://127.0.0.1:${UI_PORT:-8787}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
MSG
    fi
}

# ─── PATH ─────────────────────────────────────────────────────────────────────

add_to_path() {
    local path_line='export PATH="$HOME/.ai-employee/bin:$PATH"'
    for profile in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.zshrc"; do
        if [[ -f "$profile" ]] && ! grep -q "\.ai-employee/bin" "$profile" 2>/dev/null; then
            { echo ""; echo "# AI Employee"; echo "$path_line"; } >> "$profile"
        fi
    done
    export PATH="$AI_HOME/bin:$PATH"
    ok "ai-employee added to PATH"
}

# ─── Done ─────────────────────────────────────────────────────────────────────

done_message() {
    step "8/8 — Complete"
    local elapsed=$(($(date +%s)-START_TIME))
    echo ""
    echo -e "${G}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${G}║         ✓ AI Employee installed in ${elapsed}s!              ║${NC}"
    echo -e "${G}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${C}Configuration:${NC}"
    echo "  Phone:      $PHONE"
    echo "  Model:      ${MODEL_PRIMARY:-anthropic/claude-opus-4-5}"
    echo "  Dashboard:  http://localhost:${DASHBOARD_PORT:-3000}"
    echo "  Solver UI:  http://127.0.0.1:${UI_PORT:-8787}"
    echo "  Gateway:    http://localhost:18789"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo "  1.  cd ~/.ai-employee && ./start.sh"
    echo "  2.  openclaw channels login     ← link WhatsApp (new terminal)"
    echo "  3.  Send WhatsApp: 'Hello!'"
    echo ""
    echo -e "  UI opens automatically when you run ${G}./start.sh${NC}"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
    clear
    banner
    echo ""

    check_requirements
    install_openclaw
    wizard
    install_ollama "${WANT_OLLAMA:-n}"
    setup_directories
    install_runtime
    install_skills
    generate_configs
    install_dashboard_ui
    queue_startup_message
    add_to_path
    done_message
}

main
