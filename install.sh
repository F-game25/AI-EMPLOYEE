#!/usr/bin/env bash
# AI Employee — Main Installer v4.0 (runtime-first)
# Called by quick-install.sh
# Zero-config mode: ZERO_CONFIG=1 bash install.sh  (no questions, safe defaults)
set -euo pipefail

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; C='\033[0;36m'; M='\033[0;35m'; NC='\033[0m'

AI_HOME="$HOME/.ai-employee"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
START_TIME=$(date +%s)
CONFIG_FILES_UPDATED=0
CLAUDE_MODEL="claude-opus-4-6"
OLLAMA_HOST="http://localhost:11434"
OLLAMA_MODEL="llama3.2"
ZERO_CONFIG="${ZERO_CONFIG:-0}"
AUTO_INSTALL_OPENCLAW="${AUTO_INSTALL_OPENCLAW:-1}"
AUTO_INSTALL_DOCKER="${AUTO_INSTALL_DOCKER:-0}"

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
║      AI EMPLOYEE - v4.0 INSTALLER  (Linux)           ║
║  35 Agents • Claude AI • Ollama Local • WhatsApp     ║
╚══════════════════════════════════════════════════════╝
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
Install them with:
  sudo apt install curl python3 openssl   # Debian/Ubuntu/Linux Mint
  sudo dnf install curl python3 openssl   # Fedora/RHEL
  sudo pacman -S curl python openssl      # Arch Linux"
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
    else
        log "OpenClaw not found. Attempting install..."
        if curl -fsSL https://openclaw.ai/install.sh | bash; then
            export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
            # Also pick up the npm global bin dir (used when installed via npm)
            local npm_prefix npm_bin
            npm_prefix="$(npm config get prefix 2>/dev/null)"
            npm_bin="${npm_prefix:+$npm_prefix/bin}"
            if [[ -n "$npm_bin" ]] && [[ -d "$npm_bin" ]] && [[ ":$PATH:" != *":$npm_bin:"* ]]; then
                export PATH="$npm_bin:$PATH"
                local npm_path_line="export PATH=\"$npm_bin:\$PATH\""
                for profile in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.zshrc"; do
                    if [[ -f "$profile" ]] && ! grep -qF "$npm_bin" "$profile" 2>/dev/null; then
                        { echo ""; echo "# OpenClaw (npm global bin)"; echo "$npm_path_line"; } >> "$profile"
                    fi
                done
                ok "npm global bin dir added to PATH ($npm_bin)"
            fi
            ok "OpenClaw installed"
        else
            warn "OpenClaw auto-install failed. Install manually:
  curl -fsSL https://openclaw.ai/install.sh | bash
  Then re-run this installer."
        fi
    fi

    # The openclaw installer adds a `source ~/.openclaw/completions/openclaw.bash`
    # line to ~/.bashrc, but it does not always create that file.  Create a stub
    # so every new terminal session starts cleanly without a "file not found" error.
    mkdir -p "$HOME/.openclaw/completions"
    if [[ ! -f "$HOME/.openclaw/completions/openclaw.bash" ]]; then
        touch "$HOME/.openclaw/completions/openclaw.bash"
        ok "Created ~/.openclaw/completions/openclaw.bash stub (fixes terminal error)"
    fi
}

# ─── Ollama model catalogue ───────────────────────────────────────────────────

# Associative arrays require bash ≥ 4; we use parallel arrays for portability.
_OLLAMA_MODEL_NAMES=(
    "llama3.2"
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
    "Google Gemma 3 12B — top quality, beats 70B models (8 GB RAM) ★ best free model"
    "Meta Llama 3.1 8B  — smarter, slower               (5 GB RAM)"
    "Mistral 7B         — great instruction following   (4 GB RAM)"
    "Google Gemma 2 9B  — strong reasoning              (5 GB RAM)"
    "Microsoft Phi-3    — tiny but capable, very fast   (2 GB RAM)"
    "Alibaba Qwen 2.5   — multilingual, 7B              (4 GB RAM)"
    "DeepSeek R1 7B     — chain-of-thought reasoning    (4 GB RAM)"
    "CodeLlama 7B       — coding-focused                (4 GB RAM)"
)

select_ollama_model() {
    # Print the model menu and return the chosen model name in OLLAMA_MODEL.
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

    # Validate range; fall back to 1 if out of range
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

    # ── Zero-config mode — skip all questions, use safe defaults ──────────────
    if [[ "$ZERO_CONFIG" == "1" ]]; then
        ok "Zero-config mode: using safe defaults (no questions asked)."
        PHONE="+10000000000"
        WANT_OLLAMA="y"
        OLLAMA_MODEL="llama3.2"
        MODEL_PRIMARY="ollama/$OLLAMA_MODEL"
        ANTHROPIC_KEY=""
        OPENAI_KEY=""
        ALPHA_INSIDER_KEY=""
        TAVILY_KEY=""
        NEWS_API_KEY=""
        TELEGRAM_BOT_TOKEN=""
        DISCORD_WEBHOOK_URL=""
        SMTP_HOST=""; SMTP_USER=""; SMTP_PASS=""
        ELEVEN_LABS_KEY=""
        BOT_PATH=""
        WANT_STATUS="y"
        STATUS_INTERVAL=3600
        DASHBOARD_PORT=3000
        UI_PORT=8787
        WORKERS=5
        AI_EMPLOYEE_MODE="starter"
        AUTO_INSTALL_OPENCLAW="1"
        AUTO_INSTALL_DOCKER="0"
        TOKEN=$(openssl rand -hex 32)
        ok "Zero-config defaults set (5 agents, Starter mode, local Ollama)"
        ok "WhatsApp: set placeholder phone — update ~/.ai-employee/config.json to connect"
        return
    fi

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
        MODEL_PRIMARY="anthropic/claude-opus-4-6"
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

    # 6) Hourly status reports
    echo ""
    ask "Enable hourly WhatsApp status updates? [Y/n]:"
    read -r WANT_STATUS < "$tty_in"
    WANT_STATUS="${WANT_STATUS:-y}"
    STATUS_INTERVAL=3600
    if [[ ! "$WANT_STATUS" =~ ^[Nn] ]]; then
        ok "Status reports: every hour"
    else
        ask "Status interval in seconds [default: 3600]:"
        read -r STATUS_INTERVAL_INPUT < "$tty_in"
        STATUS_INTERVAL="${STATUS_INTERVAL_INPUT:-3600}"
        ok "Status interval: ${STATUS_INTERVAL}s"
    fi

    # 7) UI ports
    echo ""
    ask "Dashboard port [default: 3000]:"
    read -r DASHBOARD_PORT_INPUT < "$tty_in"
    DASHBOARD_PORT="${DASHBOARD_PORT_INPUT:-3000}"

    ask "Problem Solver UI port [default: 8787]:"
    read -r UI_PORT_INPUT < "$tty_in"
    UI_PORT="${UI_PORT_INPUT:-8787}"
    ok "Ports: dashboard=$DASHBOARD_PORT, ui=$UI_PORT"

    # 8) Number of workers
    echo ""
    ask "How many AI agents to enable? (1-35, default 35 = all):"
    read -r WORKERS_INPUT < "$tty_in"
    WORKERS="${WORKERS_INPUT:-35}"
    [[ "$WORKERS" =~ ^[0-9]+$ ]] || { warn "Invalid number; using 35"; WORKERS=35; }
    if (( WORKERS > 35 )); then warn "Maximum is 35; clamping to 35"; WORKERS=35; fi
    if (( WORKERS < 1  )); then warn "Minimum is 1; clamping to 1";  WORKERS=1;  fi
    ok "Workers: $WORKERS enabled"

    # 9) Mode selection
    echo ""
    echo -e "  ${C}Mode options:${NC}"
    echo "    starter  — 3 agents, 5 commands, zero overwhelm (best to start)"
    echo "    business — templates, ROI tracking, scheduling (recommended)"
    echo "    power    — all 35 agents, 147 skills, full dashboard (advanced)"
    ask "Which mode? [default: business]:"
    read -r MODE_INPUT < "$tty_in"
    AI_EMPLOYEE_MODE="${MODE_INPUT:-business}"
    case "$AI_EMPLOYEE_MODE" in
      starter|business|power) ok "Mode: $AI_EMPLOYEE_MODE" ;;
      *) warn "Unknown mode '$AI_EMPLOYEE_MODE'; defaulting to business"; AI_EMPLOYEE_MODE="business" ;;
    esac

    # 10) Runtime self-healing preferences
    echo ""
    ask "Auto-install OpenClaw at runtime if missing? [Y/n]:"
    read -r AUTO_OPENCLAW_INPUT < "$tty_in"
    AUTO_OPENCLAW_INPUT="${AUTO_OPENCLAW_INPUT:-y}"
    if [[ "$(echo "$AUTO_OPENCLAW_INPUT" | tr '[:upper:]' '[:lower:]')" =~ ^(y|yes)$ ]]; then
        AUTO_INSTALL_OPENCLAW="1"
        ok "OpenClaw runtime auto-install: enabled"
    else
        AUTO_INSTALL_OPENCLAW="0"
        info "OpenClaw runtime auto-install: disabled"
    fi

    ask "Auto-install Docker + sandbox safety setup if missing? [y/N]:"
    read -r AUTO_DOCKER_INPUT < "$tty_in"
    AUTO_DOCKER_INPUT="${AUTO_DOCKER_INPUT:-n}"
    if [[ "$(echo "$AUTO_DOCKER_INPUT" | tr '[:upper:]' '[:lower:]')" =~ ^(y|yes)$ ]]; then
        AUTO_INSTALL_DOCKER="1"
        ok "Docker runtime auto-install: enabled"
    else
        AUTO_INSTALL_DOCKER="0"
        info "Docker runtime auto-install: disabled"
    fi

    TOKEN=$(openssl rand -hex 32)
    ok "Wizard complete"
}

# ─── JWT Secret (openclaw-2) ───────────────────────────────────────────────────

setup_jwt_secret() {
    step "JWT / Security secret"

    local env_file="$AI_HOME/.env"
    mkdir -p "$(dirname "$env_file")"

    # Honour an already-exported JWT_SECRET_KEY
    if [[ -n "${JWT_SECRET_KEY:-}" ]]; then
        ok "JWT_SECRET_KEY already set in environment — keeping it"
        # Make sure it is also persisted in the .env file
        if [[ -f "$env_file" ]] && grep -q "^JWT_SECRET_KEY=" "$env_file"; then
            :  # already in file
        else
            echo "JWT_SECRET_KEY=${JWT_SECRET_KEY}" >> "$env_file"
            ok "JWT_SECRET_KEY saved to $env_file"
        fi
        return
    fi

    # Check if already in .env
    if [[ -f "$env_file" ]] && grep -q "^JWT_SECRET_KEY=" "$env_file"; then
        ok "JWT_SECRET_KEY already present in $env_file"
        return
    fi

    # Generate a fresh secure secret
    if command -v python3 >/dev/null 2>&1; then
        local jwt_secret
        jwt_secret=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        echo "JWT_SECRET_KEY=${jwt_secret}" >> "$env_file"
        chmod 600 "$env_file"
        export JWT_SECRET_KEY="$jwt_secret"
        ok "JWT secret generated and saved to $env_file"
        info "Keep this secret safe — rotate it every 90 days."
    else
        warn "python3 not found — cannot generate JWT secret automatically."
        warn "Set JWT_SECRET_KEY manually:  export JWT_SECRET_KEY=\$(openssl rand -hex 32)"
    fi
}

# ─── Directory structure ───────────────────────────────────────────────────────

setup_directories() {
    step "5/8 — Creating directory structure"

    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups,bin,run,bots,config,state,improvements}

    for a in orchestrator lead-hunter content-master social-guru intel-agent product-scout \
              email-ninja support-bot data-analyst creative-studio crypto-trader bot-dev web-sales \
              company-builder memecoin-creator hr-manager finance-wizard brand-strategist growth-hacker project-manager; do
        mkdir -p "$AI_HOME/workspace-$a/skills"
    done

    chmod 700 "$AI_HOME/credentials"
    chmod 700 "$AI_HOME/state"
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
        dl "bots/skills-manager/run.sh"
        dl "bots/skills-manager/skills_manager.py"
        dl "bots/mirofish-researcher/run.sh"
        dl "bots/mirofish-researcher/researcher.py"
        dl "bots/ai-router/ai_router.py"
        dl "bots/ollama-agent/run.sh"
        dl "bots/ollama-agent/ollama_agent.py"
        dl "bots/ollama-agent/requirements.txt"
        dl "bots/claude-agent/run.sh"
        dl "bots/claude-agent/claude_agent.py"
        dl "bots/claude-agent/requirements.txt"
        dl "bots/web-researcher/run.sh"
        dl "bots/web-researcher/web_researcher.py"
        dl "bots/web-researcher/requirements.txt"
        dl "bots/social-media-manager/run.sh"
        dl "bots/social-media-manager/social_media_manager.py"
        dl "bots/social-media-manager/requirements.txt"
        dl "bots/lead-generator/run.sh"
        dl "bots/lead-generator/lead_generator.py"
        dl "bots/lead-generator/requirements.txt"
        dl "bots/recruiter/run.sh"
        dl "bots/recruiter/recruiter.py"
        dl "bots/recruiter/requirements.txt"
        dl "bots/ecom-agent/run.sh"
        dl "bots/ecom-agent/ecom_agent.py"
        dl "bots/ecom-agent/requirements.txt"
        dl "bots/creator-agency/run.sh"
        dl "bots/creator-agency/creator_agency.py"
        dl "bots/creator-agency/requirements.txt"
        dl "bots/signal-community/run.sh"
        dl "bots/signal-community/signal_community.py"
        dl "bots/signal-community/requirements.txt"
        dl "bots/appointment-setter/run.sh"
        dl "bots/appointment-setter/appointment_setter.py"
        dl "bots/appointment-setter/requirements.txt"
        dl "bots/newsletter-bot/run.sh"
        dl "bots/newsletter-bot/newsletter_bot.py"
        dl "bots/newsletter-bot/requirements.txt"
        dl "bots/chatbot-builder/run.sh"
        dl "bots/chatbot-builder/chatbot_builder.py"
        dl "bots/chatbot-builder/requirements.txt"
        dl "bots/faceless-video/run.sh"
        dl "bots/faceless-video/faceless_video.py"
        dl "bots/faceless-video/requirements.txt"
        dl "bots/print-on-demand/run.sh"
        dl "bots/print-on-demand/print_on_demand.py"
        dl "bots/print-on-demand/requirements.txt"
        dl "bots/course-creator/run.sh"
        dl "bots/course-creator/course_creator.py"
        dl "bots/course-creator/requirements.txt"
        dl "bots/arbitrage-bot/run.sh"
        dl "bots/arbitrage-bot/arbitrage_bot.py"
        dl "bots/arbitrage-bot/requirements.txt"
        dl "bots/task-orchestrator/run.sh"
        dl "bots/task-orchestrator/task_orchestrator.py"
        dl "bots/task-orchestrator/requirements.txt"
        dl "bots/company-builder/run.sh"
        dl "bots/company-builder/company_builder.py"
        dl "bots/company-builder/requirements.txt"
        dl "bots/memecoin-creator/run.sh"
        dl "bots/memecoin-creator/memecoin_creator.py"
        dl "bots/memecoin-creator/requirements.txt"
        dl "bots/hr-manager/run.sh"
        dl "bots/hr-manager/hr_manager.py"
        dl "bots/hr-manager/requirements.txt"
        dl "bots/finance-wizard/run.sh"
        dl "bots/finance-wizard/finance_wizard.py"
        dl "bots/finance-wizard/requirements.txt"
        dl "bots/brand-strategist/run.sh"
        dl "bots/brand-strategist/brand_strategist.py"
        dl "bots/brand-strategist/requirements.txt"
        dl "bots/growth-hacker/run.sh"
        dl "bots/growth-hacker/growth_hacker.py"
        dl "bots/growth-hacker/requirements.txt"
        dl "bots/project-manager/run.sh"
        dl "bots/project-manager/project_manager.py"
        dl "bots/project-manager/requirements.txt"
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
        dl "config/task_plans.json"
        dl "start.sh"
        dl "stop.sh"
        dl "bots/auto-updater/run.sh"
        dl "bots/auto-updater/auto_updater.py"

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
            [[ "$fname" == *.sh ]] && chmod +x "$AI_HOME/bots/$bot_name/$fname"
        done
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

    # Python deps for UI bot
    local req="$AI_HOME/bots/problem-solver-ui/requirements.txt"
    if [[ -f "$req" ]]; then
        if command -v pip3 >/dev/null 2>&1; then
            pip3 install --user -q -r "$req" 2>/dev/null \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip3 install failed — run.sh will auto-retry on first start."
        elif command -v pip >/dev/null 2>&1; then
            pip install --user -q -r "$req" 2>/dev/null \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip install failed — run.sh will auto-retry on first start."
        elif command -v python3 >/dev/null 2>&1; then
            python3 -m pip install --user -q -r "$req" 2>/dev/null \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip install failed — run.sh will auto-retry on first start."
        else
            warn "pip not found — run.sh will install deps on first start."
        fi
    fi

    # Python deps for ai-router (requests is needed for Ollama calls)
    if command -v pip3 >/dev/null 2>&1; then
        pip3 install --user -q "requests>=2.31.0" 2>/dev/null \
            && ok "Python deps (requests) installed for AI router" \
            || warn "pip3 install requests failed"
    fi

    ok "Runtime files installed"

    # ── Record the current GitHub commit SHA so the auto-updater has a baseline ─
    mkdir -p "$AI_HOME/state"
    local _commit_sha=""
    if command -v curl >/dev/null 2>&1; then
        _commit_sha=$(curl -sf --max-time 10 \
            -H "Accept: application/vnd.github.v3+json" \
            -H "User-Agent: ai-employee-installer/4.0" \
            "https://api.github.com/repos/F-game25/AI-EMPLOYEE/commits/main" \
            2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sha',''))" \
            2>/dev/null || true)
    fi
    if [[ -n "${_commit_sha:-}" ]]; then
        echo "$_commit_sha" > "$AI_HOME/state/installed_commit.txt"
        ok "Recorded install baseline: ${_commit_sha:0:8}"
    else
        warn "Could not record install commit SHA (offline install?) — auto-updater will bootstrap on first run"
    fi
}

# ─── Claude AI bot ───────────────────────────────────────────────────────────

install_claude_bot() {
    log "Configuring Claude AI agent..."

    # Bot files (claude_agent.py, run.sh, requirements.txt) are deployed by
    # install_runtime() from runtime/bots/claude-agent/. This function only
    # handles config file creation and Python dep installation.

    mkdir -p "$AI_HOME/bots/claude-agent"

    if [[ ! -f "$AI_HOME/config/claude-agent.env" ]]; then
      cat > "$AI_HOME/config/claude-agent.env" << 'EOF'
CLAUDE_AGENT_HOST=127.0.0.1
CLAUDE_AGENT_PORT=8788
EOF
      # Append model from installer variable
      echo "CLAUDE_MODEL=$CLAUDE_MODEL" >> "$AI_HOME/config/claude-agent.env"
      echo "CLAUDE_MAX_TOKENS=4096" >> "$AI_HOME/config/claude-agent.env"
      chmod 600 "$AI_HOME/config/claude-agent.env"
    fi

    log "Installing Python deps for Claude Agent (best-effort)..."
    local req="$AI_HOME/bots/claude-agent/requirements.txt"
    if [[ -f "$req" ]] && command -v pip3 >/dev/null 2>&1; then
      pip3 install --user -q -r "$req" 2>/dev/null \
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
    # install_runtime() from runtime/bots/ollama-agent/. This function only
    # handles config file creation and Python dep installation.

    mkdir -p "$AI_HOME/bots/ollama-agent"

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
    local req="$AI_HOME/bots/ollama-agent/requirements.txt"
    if [[ -f "$req" ]] && command -v pip3 >/dev/null 2>&1; then
      pip3 install --user -q -r "$req" 2>/dev/null \
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

    cat > "$AI_HOME/.env" << ENV
OPENCLAW_GATEWAY_TOKEN=$TOKEN
${ANTHROPIC_KEY:+ANTHROPIC_API_KEY=$ANTHROPIC_KEY}
${OPENAI_KEY:+OPENAI_API_KEY=$OPENAI_KEY}
${ALPHA_INSIDER_KEY:+ALPHA_INSIDER_API_KEY=$ALPHA_INSIDER_KEY}
${TAVILY_KEY:+TAVILY_API_KEY=$TAVILY_KEY}
${NEWS_API_KEY:+NEWS_API_KEY=$NEWS_API_KEY}
${TELEGRAM_BOT_TOKEN:+TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN}
${DISCORD_WEBHOOK_URL:+DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL}
${SMTP_HOST:+SMTP_HOST=$SMTP_HOST}
${SMTP_USER:+SMTP_USER=$SMTP_USER}
${SMTP_PASS:+SMTP_PASS=$SMTP_PASS}
${ELEVEN_LABS_KEY:+ELEVEN_LABS_API_KEY=$ELEVEN_LABS_KEY}
OLLAMA_HOST=$OLLAMA_HOST
OLLAMA_MODEL=$OLLAMA_MODEL
CLAUDE_MODEL=$CLAUDE_MODEL
AI_EMPLOYEE_MODE=${AI_EMPLOYEE_MODE:-business}
AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=${AUTO_INSTALL_OPENCLAW:-1}
AI_EMPLOYEE_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER:-0}
OPENCLAW_DISABLE_BONJOUR=1
TZ=Europe/Amsterdam
ENV
    chmod 600 "$AI_HOME/.env"
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
    "wizard": {
        "lastRunCommand": "install",
        "lastRunMode": "local"
    },
    "agents": {
        "defaults": {
            "workspace": "AI_HOME_PLACEHOLDER/workspace"
        }
    },
    "tools": {
        "profile": "coding"
    },
    "commands": {
        "native": "auto",
        "nativeSkills": "auto",
        "restart": true,
        "ownerDisplay": "raw"
    },
    "session": {
        "dmScope": "per-channel-peer"
    },
    "gateway": {
        "port": 18789,
        "mode": "local",
        "bind": "loopback",
        "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
        "tailscale": { "mode": "off", "resetOnExit": false }
    },
    "channels": {
        "whatsapp": {
            "dmPolicy": "allowlist",
            "allowFrom": ["PHONE_PLACEHOLDER"],
            "groups": { "*": { "requireMention": true } },
            "mediaMaxMb": 50,
            "sendReadReceipts": true
        }
    },
    "skills": {
        "install": { "nodeManager": "npm" }
    }
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
    "wizard": {
        "lastRunCommand": "install",
        "lastRunMode": "local"
    },
    "agents": {
        "defaults": {
            "workspace": "AI_HOME_PLACEHOLDER/workspace"
        }
    },
    "tools": {
        "profile": "coding"
    },
    "commands": {
        "native": "auto",
        "nativeSkills": "auto",
        "restart": true,
        "ownerDisplay": "raw"
    },
    "session": {
        "dmScope": "per-channel-peer"
    },
    "gateway": {
        "port": 18789,
        "mode": "local",
        "bind": "loopback",
        "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
        "tailscale": { "mode": "off", "resetOnExit": false }
    },
    "channels": {
        "whatsapp": {
            "dmPolicy": "allowlist",
            "allowFrom": ["PHONE_PLACEHOLDER"],
            "groups": { "*": { "requireMention": true } },
            "mediaMaxMb": 50,
            "sendReadReceipts": true
        }
    },
    "skills": {
        "install": { "nodeManager": "npm" }
    }
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
            [[ -n "${ANTHROPIC_KEY:-}" ]]        && echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY"
            [[ -n "${OPENAI_KEY:-}" ]]             && echo "OPENAI_API_KEY=$OPENAI_KEY"
            [[ -n "${ALPHA_INSIDER_KEY:-}" ]]     && echo "ALPHA_INSIDER_API_KEY=$ALPHA_INSIDER_KEY"
            [[ -n "${TAVILY_KEY:-}" ]]             && echo "TAVILY_API_KEY=$TAVILY_KEY"
            [[ -n "${NEWS_API_KEY:-}" ]]           && echo "NEWS_API_KEY=$NEWS_API_KEY"
            [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]    && echo "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"
            [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]   && echo "DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL"
            [[ -n "${SMTP_HOST:-}" ]]              && echo "SMTP_HOST=$SMTP_HOST"
            [[ -n "${SMTP_USER:-}" ]]              && echo "SMTP_USER=$SMTP_USER"
            [[ -n "${SMTP_PASS:-}" ]]              && echo "SMTP_PASS=$SMTP_PASS"
            [[ -n "${ELEVEN_LABS_KEY:-}" ]]       && echo "ELEVEN_LABS_API_KEY=$ELEVEN_LABS_KEY"
            echo "AI_EMPLOYEE_MODE=${AI_EMPLOYEE_MODE:-business}"
            echo "AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=${AUTO_INSTALL_OPENCLAW:-1}"
            echo "AI_EMPLOYEE_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER:-0}"
            echo "OPENCLAW_DISABLE_BONJOUR=1"
            echo "DASHBOARD_PORT=${DASHBOARD_PORT:-3000}"
            echo "TZ=Europe/Amsterdam"
        } > "$AI_HOME/.env"
        chmod 600 "$AI_HOME/.env"
        ok ".env created"
    else
        ok ".env already exists — not overwritten"
    fi

        # Ensure runtime self-healing flags exist for older installs.
        grep -q "^AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=" "$AI_HOME/.env" \
            || echo "AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=${AUTO_INSTALL_OPENCLAW:-1}" >> "$AI_HOME/.env"
        grep -q "^AI_EMPLOYEE_AUTO_INSTALL_DOCKER=" "$AI_HOME/.env" \
            || echo "AI_EMPLOYEE_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER:-0}" >> "$AI_HOME/.env"

    # Keep gateway token in .env aligned with config.json to avoid auth mismatch.
    local cfg_token
    cfg_token="$(python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]);
try:
 d=json.loads(p.read_text()); print(d.get("gateway",{}).get("auth",{}).get("token",""))
except Exception:
 print("")' "$AI_HOME/config.json" 2>/dev/null)"
        if [[ -n "${cfg_token:-}" ]]; then
            if grep -q "^OPENCLAW_GATEWAY_TOKEN=" "$AI_HOME/.env"; then
                sed -i.bak "s|^OPENCLAW_GATEWAY_TOKEN=.*|OPENCLAW_GATEWAY_TOKEN=$cfg_token|" "$AI_HOME/.env"
                rm -f "$AI_HOME/.env.bak"
            else
                echo "OPENCLAW_GATEWAY_TOKEN=$cfg_token" >> "$AI_HOME/.env"
            fi
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
<h2>Quick Actions</h2>
<button onclick="window.open('http://localhost:18789','_blank')">📊 Open Gateway</button>
<button onclick="window.open('http://127.0.0.1:8787','_blank')">🛠️ Problem Solver UI</button>
<button onclick="window.open('http://127.0.0.1:8788','_blank')">🤖 Claude AI Agent</button>
<button onclick="window.open('http://127.0.0.1:8789','_blank')">🦙 Ollama Local Agent</button>
<button onclick="alert('Run in terminal: openclaw logs --follow')">📋 View Logs</button>
</div>
</div>

<div class="card instruction">
<h2>💬 How to Use</h2>
<p style="margin-bottom:15px">Send WhatsApp message to yourself:</p>
<p><code>switch to lead-hunter</code></p>
<p style="margin:10px 0"><code>find 20 SaaS CTOs in Netherlands</code></p>
<p style="margin:10px 0"><code>switch to claude-agent</code></p>
<p style="margin:10px 0"><code>switch to ollama-agent</code></p>
<p style="margin-top:15px;color:#94a3b8;font-size:0.9em">
The agent will process your request and return results via WhatsApp.
Claude Agent UI: <a href="http://127.0.0.1:8788" style="color:#a78bfa">http://127.0.0.1:8788</a> •
Ollama Agent UI: <a href="http://127.0.0.1:8789" style="color:#34d399">http://127.0.0.1:8789</a>
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
<p>🤖 AI Employee v4.0 • Multi-bot runtime + Claude &amp; Ollama</p>
<p style="margin-top:10px;font-size:0.9em">
Gateway: localhost:18789 • Dashboard: localhost:3000 • Problem Solver: localhost:8787 • Claude: localhost:8788 • Ollama: localhost:8789
</p>
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
    mkdir -p "$AI_HOME/state"
    # Always overwrite so the message reflects the current install
    cat > "$f" << MSG
{
  "pending": true,
  "message": "👋 *Welcome to AI Employee!*\n\n✅ Setup complete — your bot is connected and ready.\n\n*Available commands:*\n• status — get system status\n• workers — list active agents\n• switch to lead-hunter — activate an agent\n• help — show all commands\n\n*Try it now:*\nType 'hello' or 'status' to get started.\n\n📊 Dashboard: http://127.0.0.1:${UI_PORT:-8787}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
MSG
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

# ─── Desktop launcher & autostart ────────────────────────────────────────────

create_desktop_launcher() {
    # ── Write a smart launcher script that starts the bot OR opens the UI ───────
    # If the bot is already running (UI responds), just open the browser.
    # If it isn't running, launch start.sh in a new terminal window.
    local launcher_script="$AI_HOME/bin/ai-employee-launcher"
    cat > "$launcher_script" << 'LAUNCHER'
#!/usr/bin/env bash
# AI Employee Smart Launcher
# • If the bot is already running  → open the dashboard in the browser
# • If the bot is NOT running      → start the bot (which opens the browser)

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

# Load .env so ports are respected
if [[ -f "$AI_HOME/.env" ]]; then
    set -a; source "$AI_HOME/.env"; set +a
fi

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"
DASHBOARD_URL="http://127.0.0.1:${UI_PORT}"

_open_url() {
    local url="$1"
    if grep -qi microsoft /proc/version 2>/dev/null; then
        powershell.exe start "$url" 2>/dev/null || cmd.exe /c start "$url" 2>/dev/null || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" &
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser "$url" &
    else
        echo "Open: $url"
    fi
}

_bot_running() {
    curl -sf --max-time 2 "$DASHBOARD_URL" >/dev/null 2>&1
}

if _bot_running; then
    echo "AI Employee is running — opening dashboard…"
    _open_url "$DASHBOARD_URL"
else
    echo "Starting AI Employee…"
    # Try to open a terminal emulator with start.sh
    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal -- bash -c "cd \"$AI_HOME\" && ./start.sh; exec bash"
    elif command -v xterm >/dev/null 2>&1; then
        xterm -e bash -c "cd \"$AI_HOME\" && ./start.sh; exec bash" &
    elif command -v konsole >/dev/null 2>&1; then
        konsole -e bash -c "cd \"$AI_HOME\" && ./start.sh; exec bash" &
    elif command -v xfce4-terminal >/dev/null 2>&1; then
        xfce4-terminal -e "bash -c \"cd \\\"$AI_HOME\\\" && ./start.sh; exec bash\"" &
    elif command -v tilix >/dev/null 2>&1; then
        tilix -e "bash -c \"cd \\\"$AI_HOME\\\" && ./start.sh; exec bash\"" &
    else
        # Fallback: run in background, open browser after a delay
        cd "$AI_HOME" && nohup ./start.sh >/dev/null 2>&1 &
        echo "Bot started in background — opening browser in 8s…"
        sleep 8 && _open_url "$DASHBOARD_URL"
    fi
fi
LAUNCHER
    chmod +x "$launcher_script"
    ok "Smart launcher written: $launcher_script"

    # ── Linux: .desktop entry (app menu + Desktop shortcut) ───────────────────
    local app_dir="$HOME/.local/share/applications"
    mkdir -p "$app_dir"
    cat > "$app_dir/ai-employee.desktop" << DESK
[Desktop Entry]
Name=AI Employee
Comment=Start AI Employee or open the dashboard if already running
Exec=$launcher_script
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;Network;
StartupNotify=false
DESK
    chmod +x "$app_dir/ai-employee.desktop"
    ok "App launcher added — search 'AI Employee' in your app menu"
    # Refresh the XDG app-menu index so the entry is searchable immediately
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$app_dir" 2>/dev/null || true

    # ── Place shortcut on the Desktop ────────────────────────────────────────
    # Prefer the XDG-standard path (handles non-English locales such as
    # ~/Schreibtisch, ~/Bureau, ~/桌面 …); fall back to ~/Desktop.
    local xdg_desktop
    xdg_desktop="$(xdg-user-dir DESKTOP 2>/dev/null)" || xdg_desktop=""
    [[ -z "$xdg_desktop" || "$xdg_desktop" == "$HOME" ]] && xdg_desktop="$HOME/Desktop"

    # Create the directory if it doesn't exist yet (headless or first-boot)
    mkdir -p "$xdg_desktop"

    local desk_file="$xdg_desktop/ai-employee.desktop"
    cp "$app_dir/ai-employee.desktop" "$desk_file"
    chmod +x "$desk_file"

    # Mark the file as trusted so GNOME doesn't show the "Untrusted launcher"
    # dialog when the user double-clicks it.
    if command -v gio >/dev/null 2>&1; then
        gio set "$desk_file" metadata::trusted true 2>/dev/null || true
    fi

    ok "Desktop shortcut placed: $desk_file  (double-click to start or open UI)"

    # ── Systemd user service (optional autostart on login) ─────────────
    if command -v systemctl >/dev/null 2>&1; then
        local svc_dir="$HOME/.config/systemd/user"
        mkdir -p "$svc_dir"
        cat > "$svc_dir/ai-employee.service" << SVC
[Unit]
Description=AI Employee multi-agent system
After=network.target

[Service]
Type=simple
WorkingDirectory=$AI_HOME
ExecStart=$AI_HOME/start.sh
ExecStop=$AI_HOME/stop.sh
Restart=on-failure
RestartSec=10
Environment=AI_HOME=$AI_HOME

[Install]
WantedBy=default.target
SVC
        systemctl --user daemon-reload 2>/dev/null || true
        ok "Systemd service created — to auto-start on login run:"
        info "  systemctl --user enable --now ai-employee"
    fi
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
    echo "  Mode:         ${AI_EMPLOYEE_MODE:-business}"
    echo "  Phone:        $PHONE"
    echo "  Claude model: $CLAUDE_MODEL"
    echo "  Ollama model: $OLLAMA_MODEL  (host: $OLLAMA_HOST)"
    echo "  Token:        ${TOKEN:0:16}...${TOKEN: -8}"
    echo "  Config:       ~/.ai-employee/config.json"
    echo "  Dashboard:    http://127.0.0.1:${UI_PORT:-8787}  ← primary control"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo ""
    echo "  1. Start your AI employee:"
    echo "     cd ~/.ai-employee && ./start.sh"
    echo "     (dashboard opens automatically in your browser)"
    echo ""
    echo "  2. Run your first tasks (generates real business value in ~2 min):"
    echo "     ai-employee onboard"
    echo ""
    echo "  3. Send any task:"
    echo "     ai-employee do \"find 10 leads for my business\""
    echo "     ai-employee do \"write a sales email for my agency\""
    echo ""
    echo "  4. Optional — link WhatsApp for notifications & quick commands:"
    echo "     openclaw channels login  (scan QR code)"
    echo "     Use WhatsApp for status checks. Use the dashboard for full control."
    echo ""
    echo -e "  ${G}▸ Desktop launcher (smart — starts bot or opens UI if already running):${NC}"
    if [[ -d "$HOME/Desktop" ]]; then
        echo "    • Double-click  ~/Desktop/ai-employee.desktop  (Linux)"
    fi
    echo "    • Or search 'AI Employee' in your application menu"
    echo "    • Or run directly: ~/.ai-employee/bin/ai-employee-launcher"
    echo "    • Or enable autostart: systemctl --user enable --now ai-employee"
    echo ""
    [[ "${WANT_OLLAMA:-}" == "y" ]] \
        && echo -e "  ${G}▸ Local AI '${OLLAMA_MODEL}' downloaded and ready to use.${NC}"
    echo ""

    # ── Auto-open the dashboard in the default browser ────────────────────────
    local dashboard_url="http://127.0.0.1:${UI_PORT:-8787}"
    echo -e "  ${C}▸ Opening dashboard in your browser…${NC}  $dashboard_url"
    if grep -qi microsoft /proc/version 2>/dev/null; then
        # WSL
        powershell.exe start "$dashboard_url" 2>/dev/null \
            || cmd.exe /c start "$dashboard_url" 2>/dev/null \
            || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$dashboard_url" 2>/dev/null &
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser "$dashboard_url" 2>/dev/null &
    else
        echo "    Open manually: $dashboard_url"
    fi
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
    setup_jwt_secret
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
