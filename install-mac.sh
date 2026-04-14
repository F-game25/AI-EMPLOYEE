#!/usr/bin/env bash
# AI Employee — macOS Installer v4.0 (runtime-first)
# Called by quick-install.sh
set -euo pipefail

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; C='\033[0;36m'; M='\033[0;35m'; NC='\033[0m'

AI_HOME="$HOME/.ai-employee"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
START_TIME=$(date +%s)
CONFIG_FILES_UPDATED=0
CLAUDE_MODEL="claude-sonnet-4-5-20251022"
OLLAMA_HOST="http://localhost:11434"
OLLAMA_MODEL="llama3.2"

log()   { echo -e "${C}▸${NC} $1"; }
ok()    { echo -e "${G}✓${NC} $1"; }
warn()  { echo -e "${Y}⚠${NC} $1"; }
err()   { echo -e "${R}✗${NC} $1"; exit 1; }
step()  { echo ""; echo -e "${M}━━━ $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo ""; }
info()  { echo -e "    ${B}$1${NC}"; }
ask()   { echo -e "${Y}?${NC} $1"; }

banner() {
cat << 'EOF'
╔══════════════════════════════════════════════════════╗
║      AI EMPLOYEE - v4.0 INSTALLER  (macOS)           ║
║  Claude AI • Ollama Local • WhatsApp                 ║
╚══════════════════════════════════════════════════════╝
EOF
}

# ─── Requirements ─────────────────────────────────────────────────────────────

check_requirements() {
    step "1/8 — Checking requirements"

    [ "$EUID" -eq 0 ] && err "Do not run as root. Run as your regular user."

    # Check for Homebrew
    if ! command -v brew >/dev/null 2>&1; then
        warn "Homebrew is not installed."
        echo ""
        ask "Homebrew is required to install dependencies. Install it now? [Y/n]:"
        local tty_in="/dev/tty"
        [[ ! -r "$tty_in" ]] && tty_in="/dev/stdin"
        read -r WANT_BREW < "$tty_in"
        WANT_BREW="${WANT_BREW:-y}"
        WANT_BREW=$(echo "$WANT_BREW" | tr '[:upper:]' '[:lower:]')
        if [[ "$WANT_BREW" == "y" ]]; then
            log "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add Homebrew to PATH for this session (Apple Silicon vs Intel)
            if [[ -f "/opt/homebrew/bin/brew" ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -f "/usr/local/bin/brew" ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            ok "Homebrew installed"
        else
            err "Homebrew is required. Install it manually:
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        fi
    else
        ok "Homebrew: $(brew --version 2>/dev/null | head -1)"
    fi

    local missing=()
    command -v curl    >/dev/null 2>&1 || missing+=("curl")
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v openssl >/dev/null 2>&1 || missing+=("openssl")

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required dependencies: ${missing[*]}
Install them with:
  brew install ${missing[*]}"
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

    # Ensure Homebrew is on PATH for all subsequent operations (Apple Silicon vs Intel)
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -f "/usr/local/bin/brew" ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
}

# ─── OpenClaw ─────────────────────────────────────────────────────────────────

install_openclaw() {
    step "2/8 — OpenClaw gateway"

    if command -v openclaw >/dev/null 2>&1; then
        local ver
        ver=$(openclaw --version 2>/dev/null || echo "unknown")
        ok "OpenClaw already installed: $ver"
    else
        log "OpenClaw not found. Attempting install..."
        # Try standard install script; also check for macOS-specific binary
        if curl -fsSL https://openclaw.ai/install.sh | bash; then
            export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
            ok "OpenClaw installed"
        elif curl -fsSL "https://openclaw.ai/install-macos.sh" | bash 2>/dev/null; then
            export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
            ok "OpenClaw installed (macOS binary)"
        else
            warn "OpenClaw auto-install failed. Install manually:
  curl -fsSL https://openclaw.ai/install.sh | bash
  Then re-run this installer."
        fi
    fi

    # The openclaw installer adds a `source ~/.openclaw/completions/openclaw.bash`
    # line to ~/.zshrc or ~/.bash_profile, but it does not always create that file.
    # Create a stub so every new terminal session starts cleanly without a "file not found" error.
    mkdir -p "$HOME/.openclaw/completions"
    if [[ ! -f "$HOME/.openclaw/completions/openclaw.bash" ]]; then
        touch "$HOME/.openclaw/completions/openclaw.bash"
        ok "Created ~/.openclaw/completions/openclaw.bash stub (fixes terminal error)"
    fi
}

# ─── Ollama model catalogue ───────────────────────────────────────────────────

_OLLAMA_MODEL_NAMES=(
    "llama3.2"
    "gemma4"
    "gemma3"
    "llama3.1"
    "mistral"
    "gemma2"
    "phi3"
    "qwen2.5"
    "deepseek-r1"
    "codellama"
)
_OLLAMA_MODEL_DESCS=(
    "Meta Llama 3.2 3B  — best all-round, fast          (2 GB RAM)"
    "Google Gemma 4     — latest Gemma, multimodal      (5 GB RAM) ★ newest free model"
    "Google Gemma 3 12B — top quality, beats 70B models (8 GB RAM)"
    "Meta Llama 3.1 8B  — smarter, slower               (5 GB RAM)"
    "Mistral 7B         — great instruction following   (4 GB RAM)"
    "Google Gemma 2 9B  — strong reasoning              (5 GB RAM)"
    "Microsoft Phi-3    — tiny but capable, very fast   (2 GB RAM)"
    "Alibaba Qwen 2.5   — multilingual, 7B              (4 GB RAM)"
    "DeepSeek R1 7B     — chain-of-thought reasoning    (4 GB RAM)"
    "CodeLlama 7B       — coding-focused                (4 GB RAM)"
)

select_ollama_model() {
    local tty_in="${1:-/dev/tty}"
    [[ ! -r "$tty_in" ]] && tty_in="/dev/stdin"

    echo ""
    echo -e "  ${C}Available local AI models:${NC}"
    echo ""
    local i=1
    for desc in "${_OLLAMA_MODEL_DESCS[@]}"; do
        if [[ $i -eq 1 ]]; then
            printf "    ${G}%2d)${NC} %s  ${G}← recommended${NC}\n" "$i" "$desc"
        else
            printf "    ${B}%2d)${NC} %s\n" "$i" "$desc"
        fi
        (( i++ ))
    done
    echo ""
    ask "Choose a model [1-${#_OLLAMA_MODEL_NAMES[@]}, default: 1]:"
    local choice
    read -r choice < "$tty_in"
    choice="${choice:-1}"

    if [[ ! "$choice" =~ ^[0-9]+$ ]] \
       || (( choice < 1 )) \
       || (( choice > ${#_OLLAMA_MODEL_NAMES[@]} )); then
        warn "Invalid choice '$choice'. Using default: ${_OLLAMA_MODEL_NAMES[0]}"
        choice=1
    fi

    OLLAMA_MODEL="${_OLLAMA_MODEL_NAMES[$((choice-1))]}"
}

# ─── Ollama ───────────────────────────────────────────────────────────────────

install_ollama() {
    local want_ollama="$1"
    [[ "$want_ollama" != "y" ]] && return 0

    step "3/8 — Ollama (local LLM)"

    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama already installed"
    else
        log "Installing Ollama..."
        if curl -fsSL https://ollama.ai/install.sh | sh; then
            ok "Ollama installed"
        else
            warn "Ollama auto-install failed. Install manually: https://ollama.ai/download"
            return
        fi
    fi

    # ── Auto-pull the chosen model ─────────────────────────────────────────────
    if [[ -n "${OLLAMA_MODEL:-}" ]]; then
        log "Downloading model '${OLLAMA_MODEL}' — this may take a few minutes…"
        if ollama pull "$OLLAMA_MODEL"; then
            ok "Model '${OLLAMA_MODEL}' downloaded and ready"
        else
            warn "Could not pull '${OLLAMA_MODEL}' automatically."
            warn "Start Ollama first (ollama serve) then run: ollama pull ${OLLAMA_MODEL}"
        fi
    fi
}

# ─── Wizard ───────────────────────────────────────────────────────────────────

wizard() {
    step "4/8 — Configuration wizard"
    info "Answer each question (press Enter for default)."
    echo ""

    # Ensure we always read from the terminal, even when stdin is a pipe (curl | bash)
    local tty_in="/dev/tty"
    [[ ! -r "$tty_in" ]] && tty_in="/dev/stdin"

    # 1) WhatsApp phone
    ask "WhatsApp phone number in E.164 format (e.g. +31612345678):"
    read -r PHONE < "$tty_in"
    while [[ ! $PHONE =~ ^\+[0-9]{7,15}$ ]]; do
        warn "Invalid format. Use E.164: +<country_code><number> (e.g. +31612345678)"
        ask "WhatsApp phone number:"
        read -r PHONE < "$tty_in"
    done
    ok "Phone: $PHONE"
    echo ""
    echo -e "  📱 Phone registered! A welcome message will be sent to ${PHONE} via WhatsApp"
    echo -e "     once you connect with: ${C}openclaw channels login${NC}"
    echo ""

    # 2) Local LLM — Ollama is the recommended default (saves tokens, privacy-first)
    ask "Use Ollama for local LLM? (recommended — saves tokens & keeps data private) [Y/n]:"
    read -r WANT_OLLAMA < "$tty_in"
    WANT_OLLAMA="${WANT_OLLAMA:-y}"
    WANT_OLLAMA=$(echo "$WANT_OLLAMA" | tr '[:upper:]' '[:lower:]')
    OLLAMA_MODEL="llama3.2"
    if [[ "$WANT_OLLAMA" == "y" ]]; then
        select_ollama_model "$tty_in"
        MODEL_PRIMARY="ollama/$OLLAMA_MODEL"
        ok "Ollama model: $OLLAMA_MODEL (primary AI -- free & private)"
    else
        MODEL_PRIMARY="anthropic/claude-opus-4-5"
        ok "Cloud LLM selected (Ollama will still be tried first if running)"
    fi

    # 3) Anthropic API key
    echo ""
    ask "Anthropic API key (optional, Enter to skip):"
    read -rs ANTHROPIC_KEY < "$tty_in"; echo
    [[ -n "$ANTHROPIC_KEY" ]] && ok "Anthropic key: set" || info "Anthropic key: skipped"

    # 4) OpenAI API key
    ask "OpenAI API key (optional, Enter to skip):"
    read -rs OPENAI_KEY < "$tty_in"; echo
    [[ -n "$OPENAI_KEY" ]] && ok "OpenAI key: set" || info "OpenAI key: skipped"

    # 4b) Alpha Insider API key (trading strategies)
    echo ""
    ask "Alpha Insider API key (optional — enhances trading strategies, Enter to skip):"
    read -rs ALPHA_INSIDER_KEY < "$tty_in"; echo
    [[ -n "$ALPHA_INSIDER_KEY" ]] && ok "Alpha Insider key: set" || info "Alpha Insider key: skipped"

    # 4c) Tavily API key (web search — best quality for research bot)
    ask "Tavily API key (optional — best web search for research bot, Enter to skip):"
    read -rs TAVILY_KEY < "$tty_in"; echo
    [[ -n "$TAVILY_KEY" ]] && ok "Tavily key: set" || info "Tavily key: skipped (DuckDuckGo/Wikipedia used)"

    # 4d) NewsAPI key (optional news search)
    ask "NewsAPI key (optional — news search for research bot, Enter to skip):"
    read -rs NEWS_API_KEY < "$tty_in"; echo
    [[ -n "$NEWS_API_KEY" ]] && ok "NewsAPI key: set" || info "NewsAPI key: skipped"

    # 4e) Telegram Bot Token (signal-community + appointment-setter)
    ask "Telegram Bot Token (optional — trading signals + outreach, Enter to skip):"
    read -rs TELEGRAM_BOT_TOKEN < "$tty_in"; echo
    [[ -n "$TELEGRAM_BOT_TOKEN" ]] && ok "Telegram: set" || info "Telegram: skipped"

    # 4f) Discord Webhook URL (signal-community)
    ask "Discord Webhook URL (optional — trading signals community, Enter to skip):"
    read -r DISCORD_WEBHOOK_URL < "$tty_in"
    [[ -n "$DISCORD_WEBHOOK_URL" ]] && ok "Discord webhook: set" || info "Discord webhook: skipped"

    # 4g) SMTP for newsletter-bot
    echo ""
    ask "SMTP host for newsletter sending (optional, e.g. smtp.gmail.com, Enter to skip):"
    read -r SMTP_HOST < "$tty_in"
    if [[ -n "$SMTP_HOST" ]]; then
        ask "SMTP username (email address):"
        read -r SMTP_USER < "$tty_in"
        ask "SMTP password (app password):"
        read -rs SMTP_PASS < "$tty_in"; echo
        ok "SMTP: $SMTP_HOST / $SMTP_USER"
    else
        SMTP_USER=""; SMTP_PASS=""
        info "SMTP: skipped (newsletter will save to outbox)"
    fi

    # 4h) ElevenLabs for faceless-video voiceovers
    ask "ElevenLabs API key (optional — voiceover generation for faceless-video bot, Enter to skip):"
    read -rs ELEVEN_LABS_KEY < "$tty_in"; echo
    [[ -n "$ELEVEN_LABS_KEY" ]] && ok "ElevenLabs: set" || info "ElevenLabs: skipped"

    # 5) Trading bot path
    echo ""
    ask "Path to trading bot directory (optional, Enter to skip):"
    read -r BOT_PATH < "$tty_in"
    BOT_PATH="${BOT_PATH/#\~/$HOME}"
    if [[ -n "$BOT_PATH" && -d "$BOT_PATH" ]]; then
        ok "Trading bot path: $BOT_PATH"
    elif [[ -n "$BOT_PATH" ]]; then
        warn "Path does not exist ($BOT_PATH) — skipping"
        BOT_PATH=""
    else
        info "Trading bot path: skipped"
    fi

    # 5b) Trading bot risk disclosure
    echo ""
    echo -e "${Y}⚠ RISK NOTICE:${NC} This system includes trading bots (polymarket-trader, arbitrage-bot)."
    echo "  • All trading bots default to PAPER/SIMULATION mode (no real money)."
    echo "  • To enable live trading, you must manually set LIVE_TRADING=true in the config."
    echo "  • Trading involves risk of financial loss. Use at your own discretion."
    ask "I understand trading bots are in paper mode by default [Y/n]:"
    read -r TRADING_ACK < "$tty_in"
    TRADING_ACK="${TRADING_ACK:-y}"
    if [[ "$TRADING_ACK" =~ ^[Nn] ]]; then
        warn "Trading bots will still be installed in paper mode. No real money will be used."
    fi
    ok "Trading bots: paper/simulation mode (default)"

    # 6) Hourly status reports
    echo ""
    ask "Enable hourly WhatsApp status updates? [Y/n]:"
    read -r WANT_STATUS < "$tty_in"
    WANT_STATUS="${WANT_STATUS:-y}"
    STATUS_INTERVAL=0
    if [[ ! "$WANT_STATUS" =~ ^[Nn] ]]; then
        STATUS_INTERVAL=3600
        ok "Status reports: every hour"
    else
        ok "Status reports: disabled"
    fi

    # 7) UI port (single unified port)
    echo ""
    ask "Problem Solver UI port [default: 8787]:"
    read -r UI_PORT_INPUT < "$tty_in"
    UI_PORT="${UI_PORT_INPUT:-8787}"
    ok "UI port: $UI_PORT"

    # 8) Number of workers
    echo ""
    ask "How many AI agents to enable? (1-35, default 35 = all):"
    read -r WORKERS_INPUT < "$tty_in"
    WORKERS="${WORKERS_INPUT:-35}"
    [[ "$WORKERS" =~ ^[0-9]+$ ]] || { warn "Invalid number; using 35"; WORKERS=35; }
    if (( WORKERS > 35 )); then warn "Maximum is 35; clamping to 35"; WORKERS=35; fi
    if (( WORKERS < 1  )); then warn "Minimum is 1; clamping to 1";  WORKERS=1;  fi
    ok "Workers: $WORKERS enabled"

    # 9) Timezone
    local default_tz
    default_tz=$(systemsetup -gettimezone 2>/dev/null | sed 's/Time Zone: //' || cat /etc/timezone 2>/dev/null || echo "UTC")
    echo ""
    ask "Timezone [default: $default_tz]:"
    read -r TZ_INPUT < "$tty_in"
    TZ="${TZ_INPUT:-$default_tz}"
    ok "Timezone: $TZ"

    TOKEN=$(openssl rand -hex 32)
    ok "Wizard complete"
}

# ─── Directory structure ───────────────────────────────────────────────────────

setup_directories() {
    step "5/8 — Creating directory structure"

    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups,bin,run,agents,config,state,improvements}

    for a in task-orchestrator lead-generator social-media-manager web-researcher lead-hunter-elite \
              cold-outreach-assassin newsletter-bot signal-community ad-campaign-wizard \
              ecom-agent arbitrage-bot hr-manager finance-wizard brand-strategist growth-hacker project-manager \
              company-builder creator-agency faceless-video recruiter; do
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
        log "Runtime dir not found locally — downloading from GitHub..."
        local TMP_RUNTIME
        TMP_RUNTIME=$(mktemp -d)
        local BASE_URL="https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main"

        dl() {
            local rel="$1"
            mkdir -p "$TMP_RUNTIME/$(dirname "$rel")"
            curl -fsSL "$BASE_URL/runtime/$rel" -o "$TMP_RUNTIME/$rel" \
                || { echo "FATAL: could not download $rel"; exit 1; }
            if [[ ! -s "$TMP_RUNTIME/$rel" ]]; then
                echo "FATAL: downloaded $rel is empty"; exit 1
            fi
        }
    else
        log "Using local runtime from $src"
    fi

    if [[ ! -d "$src" ]]; then

        dl "bin/ai-employee"
        # Core agents
        dl "agents/problem-solver/run.sh"
        dl "agents/problem-solver/problem_solver.py"
        dl "agents/problem-solver/requirements.txt"
        dl "agents/problem-solver-ui/run.sh"
        dl "agents/problem-solver-ui/server.py"
        dl "agents/problem-solver-ui/config_manager.py"
        dl "agents/problem-solver-ui/security.py"
        dl "agents/problem-solver-ui/requirements.txt"
        dl "agents/problem-solver-ui/features/__init__.py"
        dl "agents/problem-solver-ui/features/analytics.py"
        dl "agents/problem-solver-ui/features/ceo_briefing.py"
        dl "agents/problem-solver-ui/features/competitor_watch.py"
        dl "agents/problem-solver-ui/features/crm.py"
        dl "agents/problem-solver-ui/features/customer_support.py"
        dl "agents/problem-solver-ui/features/email_marketing.py"
        dl "agents/problem-solver-ui/features/export_backup.py"
        dl "agents/problem-solver-ui/features/health_check.py"
        dl "agents/problem-solver-ui/features/invoicing.py"
        dl "agents/problem-solver-ui/features/meeting_intelligence.py"
        dl "agents/problem-solver-ui/features/personal_brand.py"
        dl "agents/problem-solver-ui/features/social_media.py"
        dl "agents/problem-solver-ui/features/team_management.py"
        dl "agents/problem-solver-ui/features/website_builder.py"
        dl "agents/problem-solver-ui/features/workflow_builder.py"
        dl "agents/utils.py"
        dl "agents/agent_selftest.py"
        # AI providers
        dl "agents/ai-router/ai_router.py"
        dl "agents/ai-router/run.sh"
        dl "agents/ollama-agent/run.sh"
        dl "agents/ollama-agent/ollama_agent.py"
        dl "agents/ollama-agent/requirements.txt"
        dl "agents/claude-agent/run.sh"
        dl "agents/claude-agent/claude_agent.py"
        dl "agents/claude-agent/requirements.txt"
        dl "agents/gemma-agent/run.sh"
        dl "agents/gemma-agent/gemma_agent.py"
        dl "agents/gemma-agent/requirements.txt"
        dl "agents/hermes-agent/run.sh"
        dl "agents/hermes-agent/hermes_agent.py"
        dl "agents/hermes-agent/requirements.txt"
        # Infrastructure agents
        dl "agents/polymarket-trader/run.sh"
        dl "agents/polymarket-trader/trader.py"
        dl "agents/polymarket-trader/requirements.txt"
        dl "agents/status-reporter/run.sh"
        dl "agents/status-reporter/status_reporter.py"
        dl "agents/status-reporter/requirements.txt"
        dl "agents/scheduler-runner/run.sh"
        dl "agents/scheduler-runner/scheduler.py"
        dl "agents/scheduler-runner/requirements.txt"
        dl "agents/discovery/run.sh"
        dl "agents/discovery/discovery.py"
        dl "agents/discovery/requirements.txt"
        dl "agents/skills-manager/run.sh"
        dl "agents/skills-manager/skills_manager.py"
        dl "agents/skills-manager/requirements.txt"
        dl "agents/auto-updater/run.sh"
        dl "agents/auto-updater/auto_updater.py"
        dl "agents/auto-updater/requirements.txt"
        dl "agents/session-manager/run.sh"
        dl "agents/session-manager/session_manager.py"
        dl "agents/session-manager/requirements.txt"
        dl "agents/task-orchestrator/run.sh"
        dl "agents/task-orchestrator/task_orchestrator.py"
        dl "agents/task-orchestrator/requirements.txt"
        dl "agents/discord-bot/run.sh"
        dl "agents/discord-bot/discord_bot.py"
        dl "agents/discord-bot/requirements.txt"
        dl "agents/whatsapp-webhook/run.sh"
        dl "agents/whatsapp-webhook/webhook_server.py"
        dl "agents/whatsapp-webhook/requirements.txt"
        # Web researcher (mirofish-researcher removed — external dependency not bundled)
        dl "agents/web-researcher/run.sh"
        dl "agents/web-researcher/web_researcher.py"
        dl "agents/web-researcher/requirements.txt"
        dl "agents/financial-deepsearch/run.sh"
        dl "agents/financial-deepsearch/financial_deepsearch.py"
        dl "agents/financial-deepsearch/requirements.txt"
        dl "agents/obsidian-memory/run.sh"
        dl "agents/obsidian-memory/obsidian_memory.py"
        dl "agents/obsidian-memory/requirements.txt"
        # Marketing & growth agents
        dl "agents/social-media-manager/run.sh"
        dl "agents/social-media-manager/social_media_manager.py"
        dl "agents/social-media-manager/social_scheduler.py"
        dl "agents/social-media-manager/requirements.txt"
        dl "agents/lead-generator/run.sh"
        dl "agents/lead-generator/lead_generator.py"
        dl "agents/lead-generator/requirements.txt"
        dl "agents/lead-hunter-elite/run.sh"
        dl "agents/lead-hunter-elite/lead_hunter_elite.py"
        dl "agents/lead-hunter-elite/requirements.txt"
        dl "agents/linkedin-growth-hacker/run.sh"
        dl "agents/linkedin-growth-hacker/linkedin_growth_hacker.py"
        dl "agents/linkedin-growth-hacker/requirements.txt"
        dl "agents/cold-outreach-assassin/run.sh"
        dl "agents/cold-outreach-assassin/cold_outreach_assassin.py"
        dl "agents/cold-outreach-assassin/requirements.txt"
        dl "agents/newsletter-bot/run.sh"
        dl "agents/newsletter-bot/newsletter_bot.py"
        dl "agents/newsletter-bot/requirements.txt"
        dl "agents/signal-community/run.sh"
        dl "agents/signal-community/signal_community.py"
        dl "agents/signal-community/requirements.txt"
        dl "agents/ad-campaign-wizard/run.sh"
        dl "agents/ad-campaign-wizard/ad_campaign_wizard.py"
        dl "agents/ad-campaign-wizard/requirements.txt"
        dl "agents/paid-media-specialist/run.sh"
        dl "agents/paid-media-specialist/paid_media_specialist.py"
        dl "agents/paid-media-specialist/requirements.txt"
        dl "agents/growth-hacker/run.sh"
        dl "agents/growth-hacker/growth_hacker.py"
        dl "agents/growth-hacker/requirements.txt"
        dl "agents/brand-strategist/run.sh"
        dl "agents/brand-strategist/brand_strategist.py"
        dl "agents/brand-strategist/requirements.txt"
        dl "agents/referral-rocket/run.sh"
        dl "agents/referral-rocket/referral_rocket.py"
        dl "agents/referral-rocket/requirements.txt"
        # Sales agents
        dl "agents/sales-closer-pro/run.sh"
        dl "agents/sales-closer-pro/sales_closer_pro.py"
        dl "agents/sales-closer-pro/requirements.txt"
        dl "agents/qualification-agent/run.sh"
        dl "agents/qualification-agent/qualification_agent.py"
        dl "agents/qualification-agent/requirements.txt"
        dl "agents/appointment-setter/run.sh"
        dl "agents/appointment-setter/appointment_setter.py"
        dl "agents/appointment-setter/requirements.txt"
        dl "agents/follow-up-agent/run.sh"
        dl "agents/follow-up-agent/follow_up_agent.py"
        dl "agents/follow-up-agent/requirements.txt"
        dl "agents/offer-agent/run.sh"
        dl "agents/offer-agent/offer_agent.py"
        dl "agents/offer-agent/requirements.txt"
        # Business operations agents
        dl "agents/recruiter/run.sh"
        dl "agents/recruiter/recruiter.py"
        dl "agents/recruiter/requirements.txt"
        dl "agents/hr-manager/run.sh"
        dl "agents/hr-manager/hr_manager.py"
        dl "agents/hr-manager/requirements.txt"
        dl "agents/finance-wizard/run.sh"
        dl "agents/finance-wizard/finance_wizard.py"
        dl "agents/finance-wizard/requirements.txt"
        dl "agents/project-manager/run.sh"
        dl "agents/project-manager/project_manager.py"
        dl "agents/project-manager/requirements.txt"
        dl "agents/company-builder/run.sh"
        dl "agents/company-builder/company_builder.py"
        dl "agents/company-builder/requirements.txt"
        dl "agents/company-manager/run.sh"
        dl "agents/company-manager/company_manager.py"
        dl "agents/budget-tracker/run.sh"
        dl "agents/budget-tracker/budget_tracker.py"
        dl "agents/budget-tracker/requirements.txt"
        dl "agents/org-chart/run.sh"
        dl "agents/org-chart/org_chart.py"
        dl "agents/org-chart/requirements.txt"
        dl "agents/ticket-system/run.sh"
        dl "agents/ticket-system/ticket_system.py"
        dl "agents/ticket-system/requirements.txt"
        dl "agents/goal-alignment/run.sh"
        dl "agents/goal-alignment/goal_alignment.py"
        dl "agents/goal-alignment/requirements.txt"
        dl "agents/governance/run.sh"
        dl "agents/governance/governance.py"
        dl "agents/governance/requirements.txt"
        dl "agents/feedback-loop/run.sh"
        dl "agents/feedback-loop/feedback_loop.py"
        dl "agents/feedback-loop/requirements.txt"
        # Content & creator agents
        dl "agents/creator-agency/run.sh"
        dl "agents/creator-agency/creator_agency.py"
        dl "agents/creator-agency/requirements.txt"
        dl "agents/faceless-video/run.sh"
        dl "agents/faceless-video/faceless_video.py"
        dl "agents/faceless-video/requirements.txt"
        dl "agents/course-creator/run.sh"
        dl "agents/course-creator/course_creator.py"
        dl "agents/course-creator/requirements.txt"
        dl "agents/chatbot-builder/run.sh"
        dl "agents/chatbot-builder/chatbot_builder.py"
        dl "agents/chatbot-builder/requirements.txt"
        dl "agents/print-on-demand/run.sh"
        dl "agents/print-on-demand/print_on_demand.py"
        dl "agents/print-on-demand/requirements.txt"
        dl "agents/ui-designer/run.sh"
        dl "agents/ui-designer/ui_designer.py"
        dl "agents/ui-designer/requirements.txt"
        dl "agents/engineering-assistant/run.sh"
        dl "agents/engineering-assistant/engineering_assistant.py"
        dl "agents/engineering-assistant/requirements.txt"
        dl "agents/qa-tester/run.sh"
        dl "agents/qa-tester/qa_tester.py"
        dl "agents/qa-tester/requirements.txt"
        # E-commerce & trading agents
        dl "agents/ecom-agent/run.sh"
        dl "agents/ecom-agent/ecom_agent.py"
        dl "agents/ecom-agent/requirements.txt"
        dl "agents/arbitrage-bot/run.sh"
        dl "agents/arbitrage-bot/arbitrage_bot.py"
        dl "agents/arbitrage-bot/requirements.txt"
        # memecoin-creator removed — reputational/legal risk for enterprise use
        dl "agents/partnership-matchmaker/run.sh"
        dl "agents/partnership-matchmaker/partnership_matchmaker.py"
        dl "agents/partnership-matchmaker/requirements.txt"
        # Advanced agents
        dl "agents/ascend-forge/run.sh"
        dl "agents/ascend-forge/ascend_forge.py"
        dl "agents/ascend-forge/requirements.txt"
        dl "agents/blacklight/run.sh"
        dl "agents/blacklight/blacklight.py"
        dl "agents/blacklight/requirements.txt"
        dl "agents/turbo-quant/run.sh"
        dl "agents/turbo-quant/turbo_quant.py"
        dl "agents/turbo-quant/requirements.txt"
        dl "agents/artifacts/run.sh"
        dl "agents/artifacts/artifacts.py"
        dl "agents/artifacts/requirements.txt"
        # Config files
        dl "config/openclaw.template.json"
        dl "config/problem-solver.env"
        dl "config/problem-solver-ui.env"
        dl "config/status-reporter.env"
        dl "config/scheduler-runner.env"
        dl "config/discovery.env"
        dl "config/polymarket-trader.env"
        dl "config/polymarket_estimates.json"
        dl "config/schedules.json"
        dl "config/ollama-agent.env"
        dl "config/claude-agent.env"
        dl "config/web-researcher.env"
        dl "config/social-media-manager.env"
        dl "config/lead-generator.env"
        dl "config/recruiter.env"
        dl "config/ecom-agent.env"
        dl "config/creator-agency.env"
        dl "config/signal-community.env"
        dl "config/appointment-setter.env"
        dl "config/newsletter-bot.env"
        dl "config/chatbot-builder.env"
        dl "config/faceless-video.env"
        dl "config/print-on-demand.env"
        dl "config/course-creator.env"
        dl "config/arbitrage-bot.env"
        dl "config/task-orchestrator.env"
        dl "config/company-builder.env"
        dl "config/memecoin-creator.env"
        dl "config/hr-manager.env"
        dl "config/finance-wizard.env"
        dl "config/brand-strategist.env"
        dl "config/growth-hacker.env"
        dl "config/project-manager.env"
        dl "config/agent_capabilities.json"
        dl "config/agent_templates.json"
        dl "config/skills_library.json"
        dl "config/task_plans.json"
        dl "config/custom_agents.json"
        dl "start.sh"
        dl "stop.sh"

        src="$TMP_RUNTIME"
    fi

    # bin/
    mkdir -p "$AI_HOME/bin"
    cp -f "$src/bin/ai-employee" "$AI_HOME/bin/ai-employee"
    chmod +x "$AI_HOME/bin/ai-employee"

    # agents/ (overwrite code; never overwrite .env)
    for bot_dir in "$src/agents"/*/; do
        bot_name="$(basename "$bot_dir")"
        mkdir -p "$AI_HOME/agents/$bot_name"
        for f in "$bot_dir"*; do
            [[ -f "$f" ]] || continue
            fname="$(basename "$f")"
            cp -f "$f" "$AI_HOME/agents/$bot_name/$fname"
            [[ "$fname" == *.sh ]] && chmod +x "$AI_HOME/agents/$bot_name/$fname"
        done
        # Copy subdirectories (e.g. problem-solver-ui/features/)
        for sub_dir in "$bot_dir"*/; do
            [[ -d "$sub_dir" ]] || continue
            sub_name="$(basename "$sub_dir")"
            mkdir -p "$AI_HOME/agents/$bot_name/$sub_name"
            for f in "$sub_dir"*; do
                [[ -f "$f" ]] || continue
                cp -f "$f" "$AI_HOME/agents/$bot_name/$sub_name/$(basename "$f")"
            done
        done
    done

    # Copy shared files at agents/ root (utils.py, agent_selftest.py)
    for f in "$src/agents"/*.py; do
        [[ -f "$f" ]] || continue
        cp -f "$f" "$AI_HOME/agents/$(basename "$f")"
    done

    # start.sh / stop.sh
    cp -f "$src/start.sh" "$AI_HOME/start.sh"
    cp -f "$src/stop.sh"  "$AI_HOME/stop.sh"
    chmod +x "$AI_HOME/start.sh" "$AI_HOME/stop.sh"

    # config templates (only if file does NOT yet exist)
    mkdir -p "$AI_HOME/config"
    for f in "$src/config"/*; do
        [[ -f "$f" ]] || continue
        fname="$(basename "$f")"
        if [[ ! -f "$AI_HOME/config/$fname" ]]; then
            cp "$f" "$AI_HOME/config/$fname"
        fi
    done

    # Python deps for UI bot (critical — must succeed)
    local req="$AI_HOME/agents/problem-solver-ui/requirements.txt"
    if [[ -f "$req" ]]; then
        if command -v pip3 >/dev/null 2>&1; then
            pip3 install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || err "pip3 install failed for core UI bot. Fix pip and re-run installer."
        elif command -v pip >/dev/null 2>&1; then
            pip install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || err "pip install failed for core UI bot. Fix pip and re-run installer."
        elif command -v python3 >/dev/null 2>&1; then
            python3 -m pip install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || err "pip install failed for core UI bot. Fix pip and re-run installer."
        else
            warn "pip not found — install manually: pip3 install fastapi uvicorn"
        fi
    fi

    # Python deps for ai-router (requests is needed for Ollama calls)
    if command -v pip3 >/dev/null 2>&1; then
        pip3 install --user -q "requests>=2.31.0" \
            && ok "Python deps (requests) installed for AI router" \
            || warn "pip3 install requests failed — install manually: pip3 install requests"
    fi

    ok "Runtime files installed"
}

# ─── Claude AI bot ───────────────────────────────────────────────────────────

install_claude_bot() {
    log "Configuring Claude AI agent..."

    # Bot files (claude_agent.py, run.sh, requirements.txt) are deployed by
    # install_runtime() from runtime/agents/claude-agent/. This function only
    # handles config file creation and Python dep installation.

    mkdir -p "$AI_HOME/agents/claude-agent"

    if [[ ! -f "$AI_HOME/config/claude-agent.env" ]]; then
      cat > "$AI_HOME/config/claude-agent.env" << 'EOF'
CLAUDE_AGENT_HOST=127.0.0.1
CLAUDE_AGENT_PORT=8788
EOF
      # Append model from installer variable
      echo "CLAUDE_MODEL=$CLAUDE_MODEL" >> "$AI_HOME/config/claude-agent.env"
      echo "CLAUDE_MAX_TOKENS=4096" >> "$AI_HOME/config/claude-agent.env"
      # Write API key so the agent can authenticate independently
      if [[ -n "${ANTHROPIC_KEY:-}" ]]; then
          echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY" >> "$AI_HOME/config/claude-agent.env"
      fi
      chmod 600 "$AI_HOME/config/claude-agent.env"
    fi

    log "Installing Python deps for Claude Agent (best-effort)..."
    local req="$AI_HOME/agents/claude-agent/requirements.txt"
    if [[ -f "$req" ]] && command -v pip3 >/dev/null 2>&1; then
      pip3 install --user -q -r "$req" \
        || warn "pip install failed; run manually: pip3 install --user anthropic fastapi uvicorn"
    else
      [[ ! -f "$req" ]] && warn "requirements.txt not found; run manually: pip3 install --user anthropic fastapi uvicorn"
      ! command -v pip3 >/dev/null 2>&1 && warn "pip3 not found; install manually: pip3 install --user anthropic fastapi uvicorn"
    fi

    ok "Claude AI agent configured (http://127.0.0.1:8788 after start)"
}

# ─── Ollama local AI bot ─────────────────────────────────────────────────────

install_ollama_bot() {
    log "Configuring Ollama local AI agent..."

    # Bot files (ollama_agent.py, run.sh, requirements.txt) are deployed by
    # install_runtime() from runtime/agents/ollama-agent/. This function only
    # handles config file creation and Python dep installation.

    mkdir -p "$AI_HOME/agents/ollama-agent"

    if [[ ! -f "$AI_HOME/config/ollama-agent.env" ]]; then
      cat > "$AI_HOME/config/ollama-agent.env" << 'EOF'
OLLAMA_AGENT_HOST=127.0.0.1
OLLAMA_AGENT_PORT=8789
OLLAMA_TIMEOUT=120
EOF
      # Append host/model from installer variables
      echo "OLLAMA_HOST=$OLLAMA_HOST" >> "$AI_HOME/config/ollama-agent.env"
      echo "OLLAMA_MODEL=$OLLAMA_MODEL" >> "$AI_HOME/config/ollama-agent.env"
      chmod 600 "$AI_HOME/config/ollama-agent.env"
    fi

    log "Installing Python deps for Ollama Agent (best-effort)..."
    local req="$AI_HOME/agents/ollama-agent/requirements.txt"
    if [[ -f "$req" ]] && command -v pip3 >/dev/null 2>&1; then
      pip3 install --user -q -r "$req" \
        || warn "pip install failed; run manually: pip3 install --user fastapi uvicorn requests"
    else
      [[ ! -f "$req" ]] && warn "requirements.txt not found; run manually: pip3 install --user fastapi uvicorn requests"
      ! command -v pip3 >/dev/null 2>&1 && warn "pip3 not found; install manually: pip3 install --user fastapi uvicorn requests"
    fi

    ok "Ollama local AI agent configured (http://127.0.0.1:8789 after start)"
}

# ─── Skills ───────────────────────────────────────────────────────────────────

install_skills() {
    log "Installing agent skills..."

    # Helper: writes a skill file with system prompt, input/output schema, and example
    _write_skill() {
        local skill_file="$1" skill_name="$2" desc="$3" system_prompt="$4" \
              input_schema="$5" output_schema="$6" example_input="$7" example_output="$8"
        [[ -f "$skill_file" ]] && return
        cat > "$skill_file" << SKILL
---
name: $skill_name
description: $desc
---

## System Prompt

$system_prompt

## Input Schema

\`\`\`json
$input_schema
\`\`\`

## Output Schema

\`\`\`json
$output_schema
\`\`\`

## Example

**Input:**
\`\`\`json
$example_input
\`\`\`

**Output:**
\`\`\`json
$example_output
\`\`\`
SKILL
    }

    # ── Lead hunting skills ─────────────────────────────────────────────────────
    local ws="$AI_HOME/workspace-lead-hunter-elite/skills"
    mkdir -p "$ws"

    _write_skill "$ws/linkedin_scraper.md" "linkedin_scraper" \
        "Find decision makers on LinkedIn" \
        "You are a B2B lead research specialist. Given a target company or industry, search LinkedIn for decision makers matching the specified criteria. Focus on C-level, VP, and Director roles. Return structured contact profiles with name, title, company, location, profile URL, and a relevance score (0-100) based on how well they match the search criteria. Prioritize recently active profiles. Exclude recruiters and sales people unless specifically requested. Always verify company match before including a result." \
        '{"type":"object","required":["query"],"properties":{"query":{"type":"string","description":"Target company, industry, or role to search"},"role_filter":{"type":"string","description":"Role titles to filter (e.g. CTO, VP Engineering)"},"location":{"type":"string","description":"Geographic filter"},"limit":{"type":"integer","default":10}}}' \
        '{"type":"object","properties":{"leads":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"title":{"type":"string"},"company":{"type":"string"},"location":{"type":"string"},"profile_url":{"type":"string"},"relevance_score":{"type":"integer","minimum":0,"maximum":100}}}},"total_found":{"type":"integer"}}}' \
        '{"query":"SaaS companies in Netherlands","role_filter":"CTO","location":"Netherlands","limit":5}' \
        '{"leads":[{"name":"Jan de Vries","title":"CTO","company":"CloudFlow BV","location":"Amsterdam","profile_url":"https://linkedin.com/in/jandevries","relevance_score":92}],"total_found":23}'

    _write_skill "$ws/lead_scorer.md" "lead_scorer" \
        "Score lead quality 0-100" \
        "You are a lead qualification analyst. Given a lead profile with company data, evaluate the lead quality on a 0-100 scale using the BANT framework (Budget, Authority, Need, Timeline). Consider company size, industry fit, technology stack, growth indicators, recent funding, and job postings as signals. Provide a breakdown of sub-scores for each BANT dimension, a final composite score, and a recommended next action (e.g., immediate outreach, nurture, disqualify). Be specific about why each sub-score was assigned." \
        '{"type":"object","required":["lead"],"properties":{"lead":{"type":"object","properties":{"name":{"type":"string"},"title":{"type":"string"},"company":{"type":"string"},"industry":{"type":"string"},"company_size":{"type":"string"},"tech_stack":{"type":"array","items":{"type":"string"}}}}}}' \
        '{"type":"object","properties":{"score":{"type":"integer","minimum":0,"maximum":100},"breakdown":{"type":"object","properties":{"budget":{"type":"integer"},"authority":{"type":"integer"},"need":{"type":"integer"},"timeline":{"type":"integer"}}},"recommendation":{"type":"string","enum":["immediate_outreach","nurture","disqualify"]},"reasoning":{"type":"string"}}}' \
        '{"lead":{"name":"Jan de Vries","title":"CTO","company":"CloudFlow BV","industry":"SaaS","company_size":"50-200","tech_stack":["Python","AWS","Kubernetes"]}}' \
        '{"score":78,"breakdown":{"budget":70,"authority":95,"need":75,"timeline":72},"recommendation":"immediate_outreach","reasoning":"CTO at mid-size SaaS with modern tech stack indicates strong decision-making authority and likely budget."}'

    # ── Task orchestrator skills ─────────────────────────────────────────────────
    ws="$AI_HOME/workspace-task-orchestrator/skills"
    mkdir -p "$ws"

    _write_skill "$ws/complex_problem_solving.md" "complex_problem_solving" \
        "Complex problem solving for system issues" \
        "You are a systems problem-solving specialist. Given a complex problem description, break it down into sub-problems, identify root causes, evaluate possible solutions with trade-offs, and recommend an action plan. Use structured reasoning: (1) Problem decomposition, (2) Root cause analysis using the 5-Whys or Ishikawa method, (3) Solution brainstorming with pros/cons, (4) Recommended action plan with steps, owners, and timeline. Be specific and actionable." \
        '{"type":"object","required":["problem"],"properties":{"problem":{"type":"string","description":"Detailed problem description"},"context":{"type":"string","description":"Additional context or constraints"},"urgency":{"type":"string","enum":["critical","high","medium","low"]}}}' \
        '{"type":"object","properties":{"root_causes":{"type":"array","items":{"type":"string"}},"solutions":{"type":"array","items":{"type":"object","properties":{"description":{"type":"string"},"pros":{"type":"array","items":{"type":"string"}},"cons":{"type":"array","items":{"type":"string"}},"effort":{"type":"string"}}}},"recommended_plan":{"type":"array","items":{"type":"object","properties":{"step":{"type":"integer"},"action":{"type":"string"},"owner":{"type":"string"},"timeline":{"type":"string"}}}}}}' \
        '{"problem":"API response times degraded from 200ms to 2s after deployment","context":"Deployed new feature with additional database queries","urgency":"high"}' \
        '{"root_causes":["New feature adds N+1 query pattern","Missing database index on new join column"],"solutions":[{"description":"Add database index","pros":["Quick fix"],"cons":["May slow writes"],"effort":"30 minutes"}],"recommended_plan":[{"step":1,"action":"Add missing index immediately","owner":"DBA","timeline":"30 min"}]}'

    # ── Remaining skills — generate with enhanced template ──────────────────────
    local remaining_skills=(
        "web-researcher:ux_audit:Audit website UX:You are a UX audit specialist. Analyze a website for usability issues including navigation clarity, mobile responsiveness, accessibility compliance (WCAG 2.1), page load performance, call-to-action effectiveness, and form usability. Provide severity ratings for each issue found, with specific recommendations."
        "web-researcher:seo_audit:Technical SEO audit:You are a technical SEO analyst. Perform a comprehensive SEO audit covering meta tags, heading hierarchy, canonical URLs, robots.txt, sitemap.xml, Core Web Vitals, mobile-friendliness, structured data markup, internal linking, broken links, duplicate content, and page speed. Score each category 0-100."
        "social-media-manager:viral_finder:Find trending viral content:You are a social media trend analyst. Monitor and identify currently trending content across platforms. Analyze virality signals including engagement velocity, share ratio, sentiment, and cross-platform spread. Return trending topics with relevance scores and suggested angles for content creation."
        "social-media-manager:content_calendar:Create 30-day content calendar:You are a content strategist. Create a 30-day social media content calendar with daily posts. Balance content types: educational (40%), entertaining (30%), promotional (20%), community (10%). Include post topics, suggested formats, optimal posting times, and cross-promotion opportunities."
    )

    for skill_entry in "${remaining_skills[@]}"; do
        IFS=':' read -r agent skill_name desc system_prompt <<< "$skill_entry"
        local skill_file="$AI_HOME/workspace-$agent/skills/${skill_name}.md"
        if [[ ! -f "$skill_file" ]]; then
            mkdir -p "$(dirname "$skill_file")"
            cat > "$skill_file" << SKILL
---
name: $skill_name
description: $desc
---

## System Prompt

$system_prompt

## Input Schema

\`\`\`json
{"type":"object","required":["query"],"properties":{"query":{"type":"string","description":"The search query or topic to analyze"},"options":{"type":"object","description":"Additional parameters for the analysis"}}}
\`\`\`

## Output Schema

\`\`\`json
{"type":"object","properties":{"results":{"type":"array","items":{"type":"object","properties":{"item":{"type":"string"},"score":{"type":"number"},"details":{"type":"string"}}}},"summary":{"type":"string"},"recommendations":{"type":"array","items":{"type":"string"}}}}
\`\`\`

## Example

**Input:**
\`\`\`json
{"query":"example $desc query"}
\`\`\`

**Output:**
\`\`\`json
{"results":[{"item":"Example result","score":85,"details":"Detailed analysis of the result"}],"summary":"Analysis complete with actionable findings","recommendations":["First recommended action","Second recommended action"]}
\`\`\`
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
            # Minimal fallback — unified on port 8787
            cat > "$AI_HOME/config.json" << 'CFG_END'
{
  "gateway": {
    "mode": "local",
    "bind": "loopback",
    "port": 8787,
    "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" }
  },
  "channels": {
    "whatsapp": { "dmPolicy": "allowlist", "allowFrom": [PHONE_JSON_PLACEHOLDER] }
  },
  "cron": { "enabled": true },
  "discovery": { "mdns": { "mode": "off" } }
}
CFG_END
        fi

        # Build phone placeholder value: empty array or quoted phone
        local phone_json
        if [[ -n "${PHONE:-}" ]]; then
            phone_json="\"$PHONE\""
        else
            phone_json=""
        fi

        # Cross-platform inline substitution
        perl -pi -e "s|TOKEN_PLACEHOLDER|$TOKEN|g" "$AI_HOME/config.json"
        perl -pi -e "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" "$AI_HOME/config.json"
        perl -pi -e "s|PHONE_JSON_PLACEHOLDER|$phone_json|g" "$AI_HOME/config.json"
        perl -pi -e "s|MODEL_PLACEHOLDER|$MODEL_PRIMARY|g" "$AI_HOME/config.json"
        chmod 600 "$AI_HOME/config.json"

        # Validate the generated JSON
        if command -v python3 >/dev/null 2>&1; then
            python3 -m json.tool "$AI_HOME/config.json" >/dev/null 2>&1 \
                || warn "config.json may contain invalid JSON — check manually"
        fi
        ok "OpenClaw config.json created"
    else
        # Existing config: patch gateway.mode=local if missing (fixes old installs)
        local mode_ok=0
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if d.get('gateway',{}).get('mode')=='local' else 1)
" "$AI_HOME/config.json" 2>/dev/null && mode_ok=1
        else
            grep -q '"mode".*"local"' "$AI_HOME/config.json" 2>/dev/null && mode_ok=1
        fi

        if [[ "$mode_ok" -eq 0 ]]; then
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
    "port": 8787,
    "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" }
  },
  "channels": {
    "whatsapp": { "dmPolicy": "allowlist", "allowFrom": [PHONE_JSON_PLACEHOLDER] }
  },
  "cron": { "enabled": true },
  "discovery": { "mdns": { "mode": "off" } }
}
CFG_END
            fi

            local phone_json
            if [[ -n "${PHONE:-}" ]]; then
                phone_json="\"$PHONE\""
            else
                phone_json=""
            fi

            perl -pi -e "s|TOKEN_PLACEHOLDER|$TOKEN|g" "$AI_HOME/config.json"
            perl -pi -e "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" "$AI_HOME/config.json"
            perl -pi -e "s|PHONE_JSON_PLACEHOLDER|$phone_json|g" "$AI_HOME/config.json"
            perl -pi -e "s|MODEL_PLACEHOLDER|$MODEL_PRIMARY|g" "$AI_HOME/config.json"
            chmod 600 "$AI_HOME/config.json"
            ok "OpenClaw config.json updated (gateway.mode=local added)"
        else
            ok "OpenClaw config.json already exists — not overwritten"
        fi
    fi

    # Symlink for openclaw (always ensure it points to current config)
    mkdir -p "$HOME/.openclaw"
    ln -sf "$AI_HOME/config.json" "$HOME/.openclaw/openclaw.json" 2>/dev/null || true

    # ── Write .env once (single canonical writer) ──────────────────────────────
    mkdir -p "$AI_HOME/credentials"
    chmod 700 "$AI_HOME/credentials"
    local env_file="$AI_HOME/credentials/.env"

    if [[ ! -f "$env_file" ]]; then
        {
            # --- Gateway & auth ---
            # OPENCLAW_GATEWAY_TOKEN: used by openclaw gateway for API auth
            echo "OPENCLAW_GATEWAY_TOKEN=$TOKEN"

            # --- AI provider keys ---
            [[ -n "${ANTHROPIC_KEY:-}" ]]        && echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY"
            [[ -n "${OPENAI_KEY:-}" ]]            && echo "OPENAI_API_KEY=$OPENAI_KEY"

            # --- Service keys ---
            [[ -n "${ALPHA_INSIDER_KEY:-}" ]]     && echo "ALPHA_INSIDER_API_KEY=$ALPHA_INSIDER_KEY"
            [[ -n "${TAVILY_KEY:-}" ]]            && echo "TAVILY_API_KEY=$TAVILY_KEY"
            [[ -n "${NEWS_API_KEY:-}" ]]          && echo "NEWS_API_KEY=$NEWS_API_KEY"
            [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]   && echo "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"
            [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]  && echo "DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL"
            [[ -n "${SMTP_HOST:-}" ]]             && echo "SMTP_HOST=$SMTP_HOST"
            [[ -n "${SMTP_USER:-}" ]]             && echo "SMTP_USER=$SMTP_USER"
            [[ -n "${SMTP_PASS:-}" ]]             && echo "SMTP_PASS=$SMTP_PASS"
            [[ -n "${ELEVEN_LABS_KEY:-}" ]]       && echo "ELEVEN_LABS_API_KEY=$ELEVEN_LABS_KEY"

            # --- Model configuration ---
            echo "OLLAMA_HOST=$OLLAMA_HOST"
            echo "OLLAMA_MODEL=$OLLAMA_MODEL"
            echo "CLAUDE_MODEL=$CLAUDE_MODEL"

            # --- Runtime settings ---
            echo "AI_EMPLOYEE_MODE=${AI_EMPLOYEE_MODE:-business}"
            echo "UI_PORT=${UI_PORT:-8787}"
            echo "WORKERS=${WORKERS:-35}"

            # Disables mDNS/Bonjour service discovery in openclaw (not needed for local mode)
            echo "OPENCLAW_DISABLE_BONJOUR=1"

            echo "TZ=${TZ:-UTC}"
        } > "$env_file"
        chmod 600 "$env_file"
        ok ".env created in credentials/"
    else
        ok ".env already exists — not overwritten"
    fi

    # Symlink .env for backward compatibility
    ln -sf "$AI_HOME/credentials/.env" "$AI_HOME/.env" 2>/dev/null || true

    # Patch status-reporter.env
    local sr_env="$AI_HOME/config/status-reporter.env"
    if [[ -f "$sr_env" ]]; then
        grep -q "^WHATSAPP_PHONE=" "$sr_env" || \
            echo "WHATSAPP_PHONE=${PHONE:-}" >> "$sr_env"
        grep -q "^OPENCLAW_GATEWAY_TOKEN=" "$sr_env" || \
            echo "OPENCLAW_GATEWAY_TOKEN=$TOKEN" >> "$sr_env"
        perl -pi -e "s|^STATUS_REPORT_INTERVAL_SECONDS=.*|STATUS_REPORT_INTERVAL_SECONDS=${STATUS_INTERVAL:-3600}|" "$sr_env"
        chmod 600 "$sr_env"
    fi

    # Patch problem-solver-ui.env
    local ui_env="$AI_HOME/config/problem-solver-ui.env"
    if [[ -f "$ui_env" ]]; then
        perl -pi -e "s|^PROBLEM_SOLVER_UI_PORT=.*|PROBLEM_SOLVER_UI_PORT=${UI_PORT:-8787}|" "$ui_env"
        chmod 600 "$ui_env"
    fi

    # Validate all JSON config files
    if command -v python3 >/dev/null 2>&1; then
        for json_file in "$AI_HOME/config"/*.json; do
            [[ -f "$json_file" ]] || continue
            if ! python3 -m json.tool "$json_file" >/dev/null 2>&1; then
                warn "$(basename "$json_file") contains invalid JSON — check manually"
            fi
        done
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
header{background:#1e293b;padding:28px;border-radius:15px;margin-bottom:28px;text-align:center;border:1px solid #334155}
h1{color:#fff;font-size:2.2em;margin-bottom:8px}
.sub{color:rgba(255,255,255,.85)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:16px}
.card{background:#1e293b;padding:22px;border-radius:12px;border:1px solid #334155}
.card h2{color:#D4AF37;margin-bottom:14px;font-size:1.1em}
.btn{display:inline-block;background:#D4AF37;color:#0f172a;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:.9em;margin:4px;text-decoration:none;font-weight:600}
.btn:hover{opacity:0.9}
.stat{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #334155}
.stat:last-child{border:none}
.stat-val{font-weight:bold}
.online{color:#10b981}
.offline{color:#ef4444}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:8px;background:#64748b}
.dot.ok{background:#10b981;animation:pulse 2s infinite}
.dot.fail{background:#ef4444}
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
    <div class="stat"><span><span class="dot" id="ui-dot"></span>Dashboard</span><span class="stat-val" id="ui-status">checking...</span></div>
  </div>
  <div class="card">
    <h2>Quick Access</h2>
    <a class="btn" href="http://127.0.0.1:8787" target="_blank">🛠️ Full Dashboard</a>
  </div>
</div>
<div class="card">
<h2>Quick Actions</h2>
<button class="btn" onclick="window.open('http://127.0.0.1:8787','_blank')">🛠️ Problem Solver UI</button>
<button class="btn" onclick="alert('Run in terminal: openclaw logs --follow')">📋 View Logs</button>
</div>
</div>

<div class="card instruction" style="margin-top:16px">
<h2>💬 How to Use</h2>
<p style="margin-bottom:15px">Send WhatsApp message to yourself:</p>
<p><code>switch to lead-hunter</code></p>
<p style="margin:10px 0"><code>find 20 SaaS CTOs in Netherlands</code></p>
<p style="margin:10px 0"><code>switch to claude-agent</code></p>
<p style="margin:10px 0"><code>switch to ollama-agent</code></p>
<p style="margin-top:15px;color:#94a3b8;font-size:0.9em">
The agent will process your request and return results via WhatsApp.
</p>
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
  <p>🤖 AI Employee v4.0 • <a href="http://127.0.0.1:8787" style="color:#D4AF37">Open full dashboard →</a></p>
</footer>
</div>
<script>
async function checkService(url, statusId, dotId) {
  try {
    const resp = await fetch(url, {signal: AbortSignal.timeout(3000)});
    if (resp.ok) {
      document.getElementById(statusId).textContent = 'Online';
      document.getElementById(statusId).className = 'stat-val online';
      document.getElementById(dotId).className = 'dot ok';
    } else {
      throw new Error('not ok');
    }
  } catch {
    document.getElementById(statusId).textContent = 'Offline';
    document.getElementById(statusId).className = 'stat-val offline';
    document.getElementById(dotId).className = 'dot fail';
  }
}
checkService('http://127.0.0.1:8787', 'ui-status', 'ui-dot');
</script>
</body>
</html>
HTMLEND
    ok "Dashboard UI installed"
}

# ─── Startup message ──────────────────────────────────────────────────────────

queue_startup_message() {
    local f="$AI_HOME/state/startup_message.json"
    mkdir -p "$AI_HOME/state"
    # Always overwrite so the message reflects the current install
    cat > "$f" << MSG
{
  "pending": true,
  "message": "👋 *Welcome to AI Employee!*\\n\\n✅ Setup complete — your bot is connected and ready.\\n\\n*Available commands:*\\n• status — get system status\\n• workers — list active agents\\n• switch to lead-hunter — activate an agent\\n• help — show all commands\\n\\n*Try it now:*\\nType 'hello' or 'status' to get started.\\n\\n📊 Dashboard: http://127.0.0.1:${UI_PORT:-8787}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
MSG
    # Validate JSON
    if command -v python3 >/dev/null 2>&1; then
        python3 -m json.tool "$f" >/dev/null 2>&1 \
            || warn "startup_message.json may contain invalid JSON"
    fi
}

# ─── PATH ─────────────────────────────────────────────────────────────────────

add_to_path() {
    local path_line='export PATH="$HOME/.ai-employee/bin:$PATH"'
    for profile in "$HOME/.zshrc" "$HOME/.bash_profile"; do
        if [[ -f "$profile" ]] && ! grep -q "\.ai-employee/bin" "$profile" 2>/dev/null; then
            { echo ""; echo "# AI Employee"; echo "$path_line"; } >> "$profile"
        fi
    done
    export PATH="$AI_HOME/bin:$PATH"
    ok "ai-employee added to PATH"
}

# ─── Desktop launcher & autostart ────────────────────────────────────────────

create_desktop_launcher() {
    # ── Write a smart launcher script that starts the bot OR opens the UI ───────
    # If the bot is already running (UI responds), just open the browser.
    # If it isn't running, open a new Terminal window and run start.sh.
    local launcher_script="$AI_HOME/bin/ai-employee-launcher"
    cat > "$launcher_script" << 'LAUNCHER'
#!/usr/bin/env bash
# AI Employee Smart Launcher (macOS)
# • If the bot is already running  → open the dashboard in the browser
# • If the bot is NOT running      → open Terminal and start the bot

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

# Load .env so ports are respected
if [[ -f "$AI_HOME/.env" ]]; then
    set -a; source "$AI_HOME/.env"; set +a
fi

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"
DASHBOARD_URL="http://127.0.0.1:${UI_PORT}"

_bot_running() {
    curl -sf --max-time 2 "$DASHBOARD_URL" >/dev/null 2>&1
}

if _bot_running; then
    echo "AI Employee is running — opening dashboard…"
    open "$DASHBOARD_URL"
else
    echo "Starting AI Employee…"
    # Open a new Terminal window running start.sh
    osascript -e "tell application \"Terminal\"
        activate
        do script \"cd \\\"$AI_HOME\\\" && ./start.sh\"
    end tell"
fi
LAUNCHER
    chmod +x "$launcher_script"
    ok "Smart launcher written: $launcher_script"

    # ── macOS: .command file on Desktop (double-click to launch) ──────────────
    # ~/Desktop always exists on macOS, but create it defensively just in case.
    mkdir -p "$HOME/Desktop"
    local cmd_file="$HOME/Desktop/AI-Employee.command"
    cat > "$cmd_file" << CMD
#!/usr/bin/env bash
exec "$AI_HOME/bin/ai-employee-launcher"
CMD
    chmod +x "$cmd_file"
    ok "Desktop launcher placed: ~/Desktop/AI-Employee.command (double-click to start or open UI)"

    # ── macOS LaunchAgent (auto-start on login) ────────────────────────────────
    local launch_agents_dir="$HOME/Library/LaunchAgents"
    mkdir -p "$launch_agents_dir"
    local plist="$launch_agents_dir/com.ai-employee.plist"
    cat > "$plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-employee</string>
    <key>ProgramArguments</key>
    <array>
        <string>$AI_HOME/start.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$AI_HOME</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AI_HOME</key>
        <string>$AI_HOME</string>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$AI_HOME/logs/launchagent.log</string>
    <key>StandardErrorPath</key>
    <string>$AI_HOME/logs/launchagent-error.log</string>
</dict>
</plist>
PLIST
    ok "LaunchAgent plist created — to auto-start on login run:"
    info "  launchctl load -w ~/Library/LaunchAgents/com.ai-employee.plist"
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
    echo -e "${C}Configuration saved:${NC}"
    echo "  Phone:        $PHONE"
    echo "  Claude model: $CLAUDE_MODEL"
    echo "  Ollama model: $OLLAMA_MODEL  (host: $OLLAMA_HOST)"
    echo "  Token:        ${TOKEN:0:16}...${TOKEN: -8}"
    echo "  Config:       ~/.ai-employee/config.json"
    echo "  Dashboard:    http://127.0.0.1:${UI_PORT:-8787}  ← primary control"
    echo "  Claude Agent: http://127.0.0.1:8788"
    echo "  Ollama Agent: http://127.0.0.1:8789"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo ""
    echo "  0. Activate PATH in current shell:"
    echo "     source ~/.zshrc"
    echo "     (or: export PATH=\"\$HOME/.ai-employee/bin:\$PATH\")"
    echo ""
    echo -e "  ${G}▸ Desktop launcher (smart — starts bot or opens UI if already running):${NC}"
    if [[ -d "$HOME/Desktop" ]]; then
        echo "    • Double-click  ~/Desktop/AI-Employee.command  (macOS)"
    fi
    echo "    • Or run directly: ~/.ai-employee/bin/ai-employee-launcher"
    echo "    • Or enable autostart: launchctl load -w ~/Library/LaunchAgents/com.ai-employee.plist"
    echo ""
    echo "  1. First start (terminal needed once to link WhatsApp):"
    echo "     cd ~/.ai-employee && ./start.sh"
    echo "     (the UI will open automatically in your browser)"
    echo ""
    echo "  2. In a new terminal, link your WhatsApp:"
    echo "     openclaw channels login"
    echo "     Scan the QR code with your phone"
    echo ""
    echo "  3. Send 'Hello!' to yourself on WhatsApp"
    echo "     You will receive a welcome message confirming it works"
    echo ""
    echo "  4. Send any task:"
    echo "     ai-employee do \"find 10 leads for my business\""
    echo "     ai-employee do \"write a sales email for my agency\""
    [[ "${WANT_OLLAMA:-}" == "y" ]] \
        && echo -e "  ${G}▸ Local AI '${OLLAMA_MODEL}' downloaded and ready to use.${NC}"
    echo ""

    # ── Auto-open the dashboard in the default browser ────────────────────────
    local dashboard_url="http://127.0.0.1:${UI_PORT:-8787}"
    echo -e "  ${C}▸ Opening dashboard in your browser…${NC}  $dashboard_url"
    open "$dashboard_url" 2>/dev/null || true
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
    install_claude_bot
    install_ollama_bot
    install_skills
    generate_configs
    install_dashboard_ui
    queue_startup_message
    add_to_path
    create_desktop_launcher
    done_message
}

# MAIN
main
