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
CLAUDE_MODEL="claude-sonnet-4-5-20251022"
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

# ── Progress bar helper ────────────────────────────────────────────────────────
# Usage: _prog_bar <current> <total> <label>
_prog_bar() {
    local cur="$1" tot="$2" label="${3:-}"
    local pct fill empty bar i
    [[ "${tot:-0}" -le 0 ]] && tot=1
    pct=$(( cur * 100 / tot ))
    fill=$(( cur * 30 / tot ))
    empty=$(( 30 - fill ))
    bar="  ["
    for (( i=0; i<fill;  i++ )); do bar+="█"; done
    for (( i=0; i<empty; i++ )); do bar+="░"; done
    bar+="]"
    if [[ -t 2 ]]; then
        printf "\r%s %3d%%  %-50s" "$bar" "$pct" "${label:0:50}" >&2
    else
        printf "%s %3d%%  %s\n" "$bar" "$pct" "${label:0:50}" >&2
    fi
}
_prog_bar_done() { [[ -t 2 ]] && printf "\n" >&2 || true; }

_file_sha256() {
    local f="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$f" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$f" | awk '{print $1}'
    else
        echo ""
    fi
}

_verify_nonempty_file() {
    local file="$1"
    local label="${2:-$file}"
    [[ -f "$file" ]] || err "$label is missing"
    [[ -s "$file" ]] || err "$label is empty"
}

_copy_checked() {
    local src="$1"
    local dst="$2"
    local src_hash dst_hash
    cp -f "$src" "$dst" || err "Copy failed: $src -> $dst"
    _verify_nonempty_file "$dst" "$dst"
    src_hash="$(_file_sha256 "$src")"
    dst_hash="$(_file_sha256 "$dst")"
    if [[ -n "$src_hash" && -n "$dst_hash" && "$src_hash" != "$dst_hash" ]]; then
        err "Checksum mismatch after copy: $src -> $dst"
    fi
}

_copy_template_checked() {
    local src="$1"
    local dst="$2"
    if [[ -f "$dst" ]] && ! cmp -s "$src" "$dst"; then
        cp -f "$dst" "$dst.bak.$(date +%s)" || err "Failed to back up existing config: $dst"
    fi
    _copy_checked "$src" "$dst"
}

_download_checked() {
    local url="$1"
    local dest="$2"
    curl --fail --show-error --silent "$url" -o "$dest" || err "Download failed: $url"
    _verify_nonempty_file "$dest" "$dest"
}

_write_version_state() {
    local commit_sha="$1"
    local source="${2:-installer}"
    local version_file="$AI_HOME/state/version.json"
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$AI_HOME/state"
    cat > "$version_file" << EOF
{
  "last_installed_commit": "$commit_sha",
  "last_installed_at": "$now",
  "source": "$source"
}
EOF
    _verify_nonempty_file "$version_file" "$version_file"
}

_kill_ui_process() {
    local port="${UI_PORT:-8787}"
    local pids=""
    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -ti ":$port" 2>/dev/null || true)"
    fi
    if [[ -n "${pids// /}" ]]; then
        warn "Stopping running process on port $port: $pids"
        while IFS= read -r pid; do
            [[ -n "$pid" ]] || continue
            kill -9 "$pid" 2>/dev/null || true
        done <<< "$pids"
    fi
}

_restart_runtime_and_validate() {
    local port="${UI_PORT:-8787}"
    local health_url="http://127.0.0.1:${port}/health"
    local agents_url="http://127.0.0.1:${port}/internal/agents"
    local launcher_log="$AI_HOME/logs/launcher.log"
    local max_tries=60
    local i=0

    echo "Restarting AI Employee with latest code..."
    _kill_ui_process

    [[ -x "$AI_HOME/start.sh" ]] || err "Missing executable start.sh at $AI_HOME/start.sh"
    mkdir -p "$AI_HOME/logs"
    (cd "$AI_HOME" && nohup ./start.sh >> "$launcher_log" 2>&1 &) || err "Failed to restart AI Employee"

    while (( i < max_tries )); do
        if curl --fail --show-error --silent --max-time 2 "$health_url" >/dev/null 2>&1; then
            break
        fi
        sleep 2
        i=$(( i + 1 ))
    done
    (( i < max_tries )) || err "Update failed: /health is not responding on port $port"

    curl --fail --show-error --silent --max-time 5 "$agents_url" >/dev/null 2>&1 \
        || err "Update failed: /internal/agents validation failed"
    ok "Runtime restart validated via /health and /internal/agents"
}

banner() {
cat << 'EOF'
╔══════════════════════════════════════════════════════╗
║      AI EMPLOYEE - v4.0 INSTALLER  (Linux)           ║
║  Claude AI • Ollama Local • WhatsApp                 ║
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
            err "OpenClaw auto-install failed. Install manually:
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
        PHONE=""
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
        UI_PORT=8787
        WORKERS=5
        AI_EMPLOYEE_MODE="starter"
        AUTO_INSTALL_OPENCLAW="1"
        AUTO_INSTALL_DOCKER="0"
        TZ=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "UTC")
        TOKEN=$(openssl rand -hex 32)
        ok "Zero-config defaults set (5 agents, Starter mode, local Ollama)"
        ok "Phone: not set — run 'ai-employee setup-phone' to configure WhatsApp"
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
    STATUS_INTERVAL=3600
    if [[ ! "$WANT_STATUS" =~ ^[Nn] ]]; then
        ok "Status reports: every hour"
    else
        ask "Status interval in seconds [default: 3600]:"
        read -r STATUS_INTERVAL_INPUT < "$tty_in"
        STATUS_INTERVAL="${STATUS_INTERVAL_INPUT:-3600}"
        ok "Status interval: ${STATUS_INTERVAL}s"
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

    # 11) Timezone
    local default_tz
    default_tz=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "UTC")
    echo ""
    ask "Timezone [default: $default_tz]:"
    read -r TZ_INPUT < "$tty_in"
    TZ="${TZ_INPUT:-$default_tz}"
    ok "Timezone: $TZ"

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

    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups,bin,run,agents,config,state,improvements}

    for a in task-orchestrator lead-generator social-media-manager web-researcher lead-hunter-elite \
              cold-outreach-assassin newsletter-bot signal-community ad-campaign-wizard \
              ecom-agent arbitrage-bot hr-manager finance-wizard brand-strategist growth-hacker project-manager \
              company-builder creator-agency faceless-video recruiter; do
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
    local _DL_COUNT=0
    # Compute total dynamically by counting dl() calls in this script
    local _DL_TOTAL
    _DL_TOTAL=$(grep -Ec '^\s+dl "' "${BASH_SOURCE[0]:-$0}" 2>/dev/null || echo 252)
    [[ "$_DL_TOTAL" -lt 1 ]] && _DL_TOTAL=252

    _kill_ui_process

    if [[ ! -d "$src" ]]; then
        log "Runtime dir not found locally — downloading from GitHub..."
        local TMP_RUNTIME
        TMP_RUNTIME=$(mktemp -d)
        local BASE_URL="https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main"

        dl() {
            local rel="$1"
            _DL_COUNT=$(( _DL_COUNT + 1 ))
            _prog_bar "$_DL_COUNT" "$_DL_TOTAL" "$rel"
            mkdir -p "$TMP_RUNTIME/$(dirname "$rel")"
            _download_checked "$BASE_URL/runtime/$rel" "$TMP_RUNTIME/$rel"
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
        _prog_bar_done
        ok "Downloaded $_DL_TOTAL files from GitHub"

        src="$TMP_RUNTIME"
    fi

    # ── Implementing updates: copy agents ─────────────────────────────────────
    local _COPY_TOTAL=0 _COPY_COUNT=0
    for _d in "$src/agents"/*/; do [[ -d "$_d" ]] && _COPY_TOTAL=$(( _COPY_TOTAL + 1 )); done
    log "Implementing updates: installing ${_COPY_TOTAL} agents..."

    # bin/
    mkdir -p "$AI_HOME/bin"
    _copy_checked "$src/bin/ai-employee" "$AI_HOME/bin/ai-employee"
    chmod +x "$AI_HOME/bin/ai-employee"

    # agents/ (overwrite code; never overwrite .env)
    for bot_dir in "$src/agents"/*/; do
        bot_name="$(basename "$bot_dir")"
        _COPY_COUNT=$(( _COPY_COUNT + 1 ))
        _prog_bar "$_COPY_COUNT" "$_COPY_TOTAL" "agent: $bot_name"
        mkdir -p "$AI_HOME/agents/$bot_name"
        for f in "$bot_dir"*; do
            [[ -f "$f" ]] || continue
            fname="$(basename "$f")"
            _copy_checked "$f" "$AI_HOME/agents/$bot_name/$fname"
            [[ "$fname" == *.sh ]] && chmod +x "$AI_HOME/agents/$bot_name/$fname"
        done
        # Copy subdirectories (e.g. problem-solver-ui/features/)
        for sub_dir in "$bot_dir"*/; do
            [[ -d "$sub_dir" ]] || continue
            sub_name="$(basename "$sub_dir")"
            mkdir -p "$AI_HOME/agents/$bot_name/$sub_name"
            for f in "$sub_dir"*; do
                [[ -f "$f" ]] || continue
                _copy_checked "$f" "$AI_HOME/agents/$bot_name/$sub_name/$(basename "$f")"
            done
        done
    done
    _prog_bar_done
    ok "All agents installed (${_COPY_TOTAL})"

    # Copy shared files at agents/ root (utils.py, agent_selftest.py)
    for f in "$src/agents"/*.py; do
        [[ -f "$f" ]] || continue
        _copy_checked "$f" "$AI_HOME/agents/$(basename "$f")"
    done

    # start.sh / stop.sh
    _copy_checked "$src/start.sh" "$AI_HOME/start.sh"
    _copy_checked "$src/stop.sh" "$AI_HOME/stop.sh"
    chmod +x "$AI_HOME/start.sh" "$AI_HOME/stop.sh"

    # config templates (always overwrite to keep runtime in sync with latest code)
    mkdir -p "$AI_HOME/config"
    for f in "$src/config"/*; do
        [[ -f "$f" ]] || continue
        fname="$(basename "$f")"
        _copy_template_checked "$f" "$AI_HOME/config/$fname"
    done

    # Python deps for UI helper agents (non-critical — UI now uses Node.js backend)
    local req="$AI_HOME/agents/problem-solver-ui/requirements.txt"
    if [[ -f "$req" ]]; then
        if command -v pip3 >/dev/null 2>&1; then
            pip3 install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip3 install failed for UI helper — non-critical (UI runs via Node.js)"
        elif command -v pip >/dev/null 2>&1; then
            pip install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip install failed for UI helper — non-critical (UI runs via Node.js)"
        elif command -v python3 >/dev/null 2>&1; then
            python3 -m pip install --user -q -r "$req" \
                && ok "Python deps (fastapi/uvicorn) installed" \
                || warn "pip install failed for UI helper — non-critical (UI runs via Node.js)"
        else
            warn "pip not found — install manually: pip3 install fastapi uvicorn"
        fi
    fi

    # Node.js backend + React frontend (required for unified UI on port 8787)
    if command -v npm >/dev/null 2>&1; then
        local _be_dir="$SCRIPT_DIR/backend"
        local _fe_dir="$SCRIPT_DIR/frontend"
        if [[ -f "$_be_dir/package.json" ]]; then
            log "Installing Node.js backend packages..."
            npm --prefix "$_be_dir" install --loglevel=error \
                && ok "Backend Node packages installed" \
                || err "npm install for backend failed in $_be_dir (check npm logs)"
        fi
        if [[ -f "$_fe_dir/package.json" ]]; then
            log "Building React UI bundle..."
            if [[ ! -d "$_fe_dir/node_modules" ]]; then
                npm --prefix "$_fe_dir" install --loglevel=error \
                    || err "npm install for frontend failed"
            fi
            npm --prefix "$_fe_dir" run build \
                || err "Frontend build failed in $_fe_dir (check npm build output)"
            _verify_nonempty_file "$_fe_dir/dist/index.html" "$_fe_dir/dist/index.html"
            ok "React UI bundle built (frontend/dist)"
        fi
    elif [[ -f "$SCRIPT_DIR/frontend/package.json" ]]; then
        # npm is missing AND the repo frontend is present — we need npm to build the UI.
        err "npm not found — install Node.js and npm first (https://nodejs.org/) to build frontend/dist"
    else
        warn "npm not found — skipping frontend build (no frontend/package.json in $SCRIPT_DIR)."
        warn "For a full UI install: clone the repo, install Node.js, then re-run install.sh."
    fi

    # Python deps for ai-router (requests is needed for Ollama calls)
    if command -v pip3 >/dev/null 2>&1; then
        pip3 install --user -q "requests>=2.31.0" \
            && ok "Python deps (requests) installed for AI router" \
            || warn "pip3 install requests failed — install manually: pip3 install requests"
    fi

    ok "Runtime files installed"

    # ── Record the current GitHub commit SHA so the auto-updater has a baseline ─
    mkdir -p "$AI_HOME/state"
    local _commit_sha=""
    if command -v git >/dev/null 2>&1 && [[ -d "$SCRIPT_DIR/.git" ]]; then
        _commit_sha="$(git -C "$SCRIPT_DIR" rev-parse HEAD 2>/dev/null || true)"
    fi
    if [[ -z "$_commit_sha" ]] && command -v curl >/dev/null 2>&1; then
        _commit_sha="$(curl --fail --show-error --silent --max-time 10 \
            -H "Accept: application/vnd.github.v3+json" \
            -H "User-Agent: ai-employee-installer/4.0" \
            "https://api.github.com/repos/F-game25/AI-EMPLOYEE/commits/main" \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sha',''))" \
            2>/dev/null || true)"
    fi
    if [[ -n "${_commit_sha:-}" ]]; then
        echo "$_commit_sha" > "$AI_HOME/state/installed_commit.txt"
        _write_version_state "$_commit_sha" "install.sh"
        ok "Recorded install baseline: ${_commit_sha:0:8}"
    else
        warn "Could not record install commit SHA (offline install?) — auto-updater will bootstrap on first run"
    fi
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

    _write_skill "$ws/email_finder.md" "email_finder" \
        "Find and verify email addresses" \
        "You are an email discovery and verification specialist. Given a person name and company, determine the most likely professional email address using common email patterns (first.last@, first@, flast@, etc.) and the company domain. Verify the email exists using MX record checks and SMTP validation where possible. Return the best candidate email, confidence score, and the pattern used. Never fabricate emails — only return addresses with reasonable confidence of delivery. Flag disposable or catch-all domains." \
        '{"type":"object","required":["name","company"],"properties":{"name":{"type":"string"},"company":{"type":"string"},"domain":{"type":"string","description":"Known company domain (optional)"}}}' \
        '{"type":"object","properties":{"email":{"type":"string"},"confidence":{"type":"number","minimum":0,"maximum":1},"pattern_used":{"type":"string"},"domain_type":{"type":"string","enum":["corporate","catch_all","disposable","unknown"]},"mx_valid":{"type":"boolean"}}}' \
        '{"name":"Jan de Vries","company":"CloudFlow BV","domain":"cloudflow.nl"}' \
        '{"email":"jan.devries@cloudflow.nl","confidence":0.85,"pattern_used":"first.last@domain","domain_type":"corporate","mx_valid":true}'

    _write_skill "$ws/lead_scorer.md" "lead_scorer" \
        "Score lead quality 0-100" \
        "You are a lead qualification analyst. Given a lead profile with company data, evaluate the lead quality on a 0-100 scale using the BANT framework (Budget, Authority, Need, Timeline). Consider company size, industry fit, technology stack, growth indicators, recent funding, and job postings as signals. Provide a breakdown of sub-scores for each BANT dimension, a final composite score, and a recommended next action (e.g., immediate outreach, nurture, disqualify). Be specific about why each sub-score was assigned." \
        '{"type":"object","required":["lead"],"properties":{"lead":{"type":"object","properties":{"name":{"type":"string"},"title":{"type":"string"},"company":{"type":"string"},"industry":{"type":"string"},"company_size":{"type":"string"},"tech_stack":{"type":"array","items":{"type":"string"}}}}}}' \
        '{"type":"object","properties":{"score":{"type":"integer","minimum":0,"maximum":100},"breakdown":{"type":"object","properties":{"budget":{"type":"integer"},"authority":{"type":"integer"},"need":{"type":"integer"},"timeline":{"type":"integer"}}},"recommendation":{"type":"string","enum":["immediate_outreach","nurture","disqualify"]},"reasoning":{"type":"string"}}}' \
        '{"lead":{"name":"Jan de Vries","title":"CTO","company":"CloudFlow BV","industry":"SaaS","company_size":"50-200","tech_stack":["Python","AWS","Kubernetes"]}}' \
        '{"score":78,"breakdown":{"budget":70,"authority":95,"need":75,"timeline":72},"recommendation":"immediate_outreach","reasoning":"CTO at mid-size SaaS with modern tech stack indicates strong decision-making authority and likely budget. Growth signals positive."}'

    _write_skill "$ws/company_enrichment.md" "company_enrichment" \
        "Enrich company data" \
        "You are a company intelligence researcher. Given a company name or domain, gather comprehensive company data including: industry, sub-industry, employee count range, estimated revenue range, headquarters location, founding year, key technologies used, recent news, funding history, and key competitors. Use web search and public data sources. Return structured, verified data with confidence levels. Flag any data points that could not be verified. Focus on actionable intelligence that helps sales teams qualify and personalize outreach." \
        '{"type":"object","required":["company"],"properties":{"company":{"type":"string"},"domain":{"type":"string"}}}' \
        '{"type":"object","properties":{"company_name":{"type":"string"},"domain":{"type":"string"},"industry":{"type":"string"},"employee_range":{"type":"string"},"revenue_range":{"type":"string"},"hq_location":{"type":"string"},"founded_year":{"type":"integer"},"technologies":{"type":"array","items":{"type":"string"}},"recent_news":{"type":"array","items":{"type":"string"}},"competitors":{"type":"array","items":{"type":"string"}}}}' \
        '{"company":"CloudFlow BV","domain":"cloudflow.nl"}' \
        '{"company_name":"CloudFlow BV","domain":"cloudflow.nl","industry":"Cloud Infrastructure SaaS","employee_range":"50-200","revenue_range":"5M-20M EUR","hq_location":"Amsterdam, Netherlands","founded_year":2018,"technologies":["Python","AWS","Kubernetes","React"],"recent_news":["Series B funding of 15M EUR (2024)"],"competitors":["Pulumi","Terraform Cloud"]}'

    # ── Task orchestrator skills ─────────────────────────────────────────────────
    ws="$AI_HOME/workspace-task-orchestrator/skills"
    mkdir -p "$ws"

    _write_skill "$ws/complex_problem_solving.md" "complex_problem_solving" \
        "Complex problem solving for system issues" \
        "You are a systems problem-solving specialist. Given a complex problem description, break it down into sub-problems, identify root causes, evaluate possible solutions with trade-offs, and recommend an action plan. Use structured reasoning: (1) Problem decomposition, (2) Root cause analysis using the 5-Whys or Ishikawa method, (3) Solution brainstorming with pros/cons, (4) Recommended action plan with steps, owners, and timeline. Be specific and actionable. If the problem involves code, infrastructure, or business processes, provide concrete steps rather than generic advice." \
        '{"type":"object","required":["problem"],"properties":{"problem":{"type":"string","description":"Detailed problem description"},"context":{"type":"string","description":"Additional context or constraints"},"urgency":{"type":"string","enum":["critical","high","medium","low"]}}}' \
        '{"type":"object","properties":{"root_causes":{"type":"array","items":{"type":"string"}},"solutions":{"type":"array","items":{"type":"object","properties":{"description":{"type":"string"},"pros":{"type":"array","items":{"type":"string"}},"cons":{"type":"array","items":{"type":"string"}},"effort":{"type":"string"}}}},"recommended_plan":{"type":"array","items":{"type":"object","properties":{"step":{"type":"integer"},"action":{"type":"string"},"owner":{"type":"string"},"timeline":{"type":"string"}}}}}}' \
        '{"problem":"API response times degraded from 200ms to 2s after deployment","context":"Deployed new feature with additional database queries","urgency":"high"}' \
        '{"root_causes":["New feature adds N+1 query pattern","Missing database index on new join column"],"solutions":[{"description":"Add database index","pros":["Quick fix","No code changes"],"cons":["May slow writes slightly"],"effort":"30 minutes"},{"description":"Refactor to eager loading","pros":["Eliminates N+1","Better long-term"],"cons":["Code changes needed","Testing required"],"effort":"2-4 hours"}],"recommended_plan":[{"step":1,"action":"Add missing index immediately","owner":"DBA","timeline":"30 min"},{"step":2,"action":"Deploy eager loading fix","owner":"Backend team","timeline":"Next sprint"}]}'

    _write_skill "$ws/tool_language_selector.md" "tool_language_selector" \
        "Select best tools and language for a task" \
        "You are a technical architecture advisor. Given a task or project description, recommend the optimal programming language, framework, and tools. Consider: team expertise, project scale, performance requirements, ecosystem maturity, hiring pool, maintenance burden, and deployment target. Provide a primary recommendation with rationale and one alternative. Include specific library/package recommendations for common needs (HTTP, database, testing, deployment). Be opinionated but justify each choice with concrete trade-offs." \
        '{"type":"object","required":["task"],"properties":{"task":{"type":"string"},"constraints":{"type":"object","properties":{"team_languages":{"type":"array","items":{"type":"string"}},"scale":{"type":"string","enum":["prototype","startup","enterprise"]},"deployment_target":{"type":"string"}}}}}' \
        '{"type":"object","properties":{"primary":{"type":"object","properties":{"language":{"type":"string"},"framework":{"type":"string"},"key_libraries":{"type":"array","items":{"type":"string"}},"rationale":{"type":"string"}}},"alternative":{"type":"object","properties":{"language":{"type":"string"},"framework":{"type":"string"},"rationale":{"type":"string"}}}}}' \
        '{"task":"Build a real-time analytics dashboard with websockets","constraints":{"team_languages":["Python","JavaScript"],"scale":"startup","deployment_target":"AWS"}}' \
        '{"primary":{"language":"TypeScript","framework":"Next.js + Socket.io","key_libraries":["Prisma","Chart.js","Redis","Bull"],"rationale":"Team knows JS, Next.js provides SSR+API routes, Socket.io handles websockets natively, Prisma for type-safe DB access"},"alternative":{"language":"Python","framework":"FastAPI + HTMX","rationale":"If team prefers Python backend, FastAPI websockets + HTMX for progressive enhancement, simpler but less real-time UI capability"}}'

    # ── Remaining skills — generate with enhanced template ──────────────────────
    local remaining_skills=(
        "web-researcher:ux_audit:Audit website UX:You are a UX audit specialist. Analyze a website for usability issues including navigation clarity, mobile responsiveness, accessibility compliance (WCAG 2.1), page load performance, call-to-action effectiveness, and form usability. Provide severity ratings (critical/major/minor) for each issue found, with specific recommendations and before/after descriptions. Focus on conversion-impacting issues first."
        "web-researcher:seo_audit:Technical SEO audit:You are a technical SEO analyst. Perform a comprehensive SEO audit covering: meta tags, heading hierarchy, canonical URLs, robots.txt, sitemap.xml, Core Web Vitals, mobile-friendliness, structured data markup, internal linking, broken links, duplicate content, and page speed. Score each category 0-100 and provide prioritized fix recommendations with estimated traffic impact."
        "social-media-manager:viral_finder:Find trending viral content:You are a social media trend analyst. Monitor and identify currently trending content across platforms (Twitter/X, TikTok, Instagram, LinkedIn, Reddit). Analyze virality signals: engagement velocity, share ratio, sentiment, cross-platform spread. Return trending topics with relevance scores, suggested angles for content creation, and optimal posting windows. Focus on trends relevant to the user's industry."
        "social-media-manager:caption_writer:Write platform-specific captions:You are a social media copywriter specializing in platform-specific content. Write captions optimized for each platform's algorithm and audience behavior. Twitter/X: concise, hook-first, thread-worthy. Instagram: storytelling with line breaks, 3-5 relevant hashtags. LinkedIn: professional insight, question-ending for engagement. TikTok: trend-aware, casual, hook in first 3 words. Include A/B test variants."
        "social-media-manager:hashtag_generator:Generate relevant hashtags:You are a hashtag strategy specialist. Given a topic and target platform, generate optimized hashtag sets: 5 high-volume (>1M posts), 5 medium-volume (100K-1M), 5 niche/specific (<100K). Avoid banned or shadowbanned hashtags. Include engagement rate estimates where possible. Group hashtags by theme for easy rotation across posts."
        "social-media-manager:content_calendar:Create 30-day content calendar:You are a content strategist. Create a 30-day social media content calendar with daily posts across specified platforms. Balance content types: educational (40%), entertaining (30%), promotional (20%), community (10%). Include post topics, suggested formats (carousel, video, story, poll), optimal posting times for the target timezone, and cross-promotion opportunities. Account for industry events and seasonal trends."
        "ecom-agent:arbitrage_finder:Find AliExpress to Amazon arbitrage:You are a product arbitrage analyst. Search for products available on AliExpress at low cost that can be sold on Amazon at a profit. Calculate true margins including shipping, Amazon FBA fees, returns rate, and advertising cost. Minimum viable margin: 30%. Verify the product is not restricted on Amazon. Score opportunities by risk level (competition, IP concerns, seasonal demand)."
        "ecom-agent:trend_spotter:Find trending products:You are an e-commerce trend analyst. Identify products with rising demand using signals from Google Trends, Amazon Best Sellers, TikTok Made Me Buy It, and social media mentions. Focus on products with upward trajectory but not yet saturated. Provide demand score, competition level, estimated monthly search volume, and suggested entry strategy."
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
        "port": 8787,
        "mode": "local",
        "bind": "loopback",
        "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
        "tailscale": { "mode": "off", "resetOnExit": false }
    },
    "channels": {
        "whatsapp": {
            "dmPolicy": "allowlist",
            "allowFrom": [PHONE_JSON_PLACEHOLDER],
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

        # Build phone placeholder value: empty array or quoted phone
        local phone_json
        if [[ -n "${PHONE:-}" ]]; then
            phone_json="\"$PHONE\""
        else
            phone_json=""
        fi

        # Cross-platform inline substitution (works on both GNU and BSD sed)
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
        "port": 8787,
        "mode": "local",
        "bind": "loopback",
        "auth": { "mode": "token", "token": "TOKEN_PLACEHOLDER" },
        "tailscale": { "mode": "off", "resetOnExit": false }
    },
    "channels": {
        "whatsapp": {
            "dmPolicy": "allowlist",
            "allowFrom": [PHONE_JSON_PLACEHOLDER],
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
    # .env lives in credentials/ for security; symlinked from $AI_HOME/.env
    mkdir -p "$AI_HOME/credentials"
    chmod 700 "$AI_HOME/credentials"
    local env_file="$AI_HOME/credentials/.env"

    if [[ ! -f "$env_file" ]]; then
        {
            # --- Gateway & auth ---
            # OPENCLAW_GATEWAY_TOKEN: used by openclaw gateway for API auth
            echo "OPENCLAW_GATEWAY_TOKEN=$TOKEN"
            # JWT_SECRET_KEY: used by the dashboard UI for session authentication
            [[ -n "${JWT_SECRET_KEY:-}" ]] && echo "JWT_SECRET_KEY=$JWT_SECRET_KEY"

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
            echo "AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=${AUTO_INSTALL_OPENCLAW:-1}"
            echo "AI_EMPLOYEE_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER:-0}"

            # Disables mDNS/Bonjour service discovery in openclaw (not needed for local mode)
            echo "OPENCLAW_DISABLE_BONJOUR=1"

            echo "TZ=${TZ:-UTC}"
            # Repo location (used by run.sh to locate the Node backend/frontend).
            # Only record when SCRIPT_DIR is a real persistent clone — not a temp dir.
            if [[ -f "$SCRIPT_DIR/backend/server.js" && -f "$SCRIPT_DIR/frontend/package.json" ]]; then
                echo "AI_EMPLOYEE_REPO_DIR=$SCRIPT_DIR"
            fi
        } > "$env_file"
        chmod 600 "$env_file"
        ok ".env created in credentials/"
    else
        ok ".env already exists — not overwritten"
    fi

    # Symlink .env for backward compatibility
    ln -sf "$AI_HOME/credentials/.env" "$AI_HOME/.env" 2>/dev/null || true

    # Ensure runtime self-healing flags exist for older installs.
    grep -q "^AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=" "$env_file" \
        || echo "AI_EMPLOYEE_AUTO_INSTALL_OPENCLAW=${AUTO_INSTALL_OPENCLAW:-1}" >> "$env_file"
    grep -q "^AI_EMPLOYEE_AUTO_INSTALL_DOCKER=" "$env_file" \
        || echo "AI_EMPLOYEE_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER:-0}" >> "$env_file"
    # Only record repo dir when SCRIPT_DIR is a real persistent clone (backend/server.js present).
    # This prevents a quick-install temp dir from being saved and later deleted, breaking run.sh.
    if [[ -f "$SCRIPT_DIR/backend/server.js" && -f "$SCRIPT_DIR/frontend/package.json" ]]; then
        grep -q "^AI_EMPLOYEE_REPO_DIR=" "$env_file" \
            || echo "AI_EMPLOYEE_REPO_DIR=$SCRIPT_DIR" >> "$env_file"
    fi

    # Keep gateway token in .env aligned with config.json to avoid auth mismatch.
    local cfg_token
    cfg_token="$(python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]);
try:
 d=json.loads(p.read_text()); print(d.get("gateway",{}).get("auth",{}).get("token",""))
except Exception:
 print("")' "$AI_HOME/config.json" 2>/dev/null)"
        if [[ -n "${cfg_token:-}" ]]; then
            if grep -q "^OPENCLAW_GATEWAY_TOKEN=" "$env_file"; then
                perl -pi -e "s|^OPENCLAW_GATEWAY_TOKEN=.*|OPENCLAW_GATEWAY_TOKEN=$cfg_token|" "$env_file"
            else
                echo "OPENCLAW_GATEWAY_TOKEN=$cfg_token" >> "$env_file"
            fi
        fi

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
    local dist_index="$SCRIPT_DIR/frontend/dist/index.html"
    if [[ -f "$dist_index" && -s "$dist_index" ]]; then
        ok "Static dashboard ready: runtime serves frontend/dist"
    else
        warn "frontend/dist not found at $SCRIPT_DIR — UI bundle not yet built."
        warn "To build it, run these steps from the repo:"
        warn "  1) npm --prefix frontend install"
        warn "  2) npm --prefix frontend run build"
    fi
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
    # If the bot is already running (UI responds on /health), just open the browser.
    # If it isn't running, launch run.sh in a new terminal window (or background).
    local launcher_script="$AI_HOME/bin/ai-employee-launcher"
    cat > "$launcher_script" << 'LAUNCHER'
#!/usr/bin/env bash
# AI Employee Smart Launcher
# • If the bot is already running  → open the dashboard in the browser
# • If the bot is NOT running      → start the bot, then open the browser

AI_HOME="${AI_HOME:-$HOME/.ai-employee}"

# Load .env so ports and repo path are respected
if [[ -f "$AI_HOME/.env" ]]; then
    set -a; source "$AI_HOME/.env"; set +a
fi

UI_PORT="${PROBLEM_SOLVER_UI_PORT:-8787}"
DASHBOARD_URL="http://127.0.0.1:${UI_PORT}"
mkdir -p "$AI_HOME/logs"

# Locate the best startup script:
# 1. Installed agent run.sh  2. Repo-relative run.sh  3. Full start.sh fallback
_find_run_sh() {
    local installed="$AI_HOME/agents/problem-solver-ui/run.sh"
    [[ -x "$installed" ]] && echo "$installed" && return 0
    if [[ -n "${AI_EMPLOYEE_REPO_DIR:-}" ]]; then
        local repo_run="$AI_EMPLOYEE_REPO_DIR/runtime/agents/problem-solver-ui/run.sh"
        [[ -x "$repo_run" ]] && echo "$repo_run" && return 0
    fi
    [[ -x "$AI_HOME/start.sh" ]] && echo "$AI_HOME/start.sh" && return 0
    echo ""
}

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
    # Try /health first (Node backend), fall back to root URL
    curl -sf --max-time 2 "${DASHBOARD_URL}/health" >/dev/null 2>&1 \
        || curl -sf --max-time 2 "${DASHBOARD_URL}" >/dev/null 2>&1
}

_wait_for_bot() {
    local tries=0 max=40
    printf "  Waiting for AI Employee"
    while [[ $tries -lt $max ]]; do
        if _bot_running; then
            printf "  ✓ Ready!\n"
            return 0
        fi
        printf "."
        sleep 2
        tries=$(( tries + 1 ))
    done
    printf "\n  ⚠ Timed out — opening browser anyway…\n"
}

if _bot_running; then
    echo "AI Employee is running — opening dashboard…"
    _open_url "$DASHBOARD_URL"
else
    echo "Starting AI Employee…"
    _RUN_SH="$(_find_run_sh)"
    _TERM_OPENED=0

    if [[ -n "$_RUN_SH" ]]; then
        if command -v gnome-terminal >/dev/null 2>&1; then
            gnome-terminal -- bash -c "\"$_RUN_SH\"; exec bash" && _TERM_OPENED=1
        elif command -v xterm >/dev/null 2>&1; then
            xterm -e bash -c "\"$_RUN_SH\"; exec bash" & _TERM_OPENED=1
        elif command -v konsole >/dev/null 2>&1; then
            konsole -e bash -c "\"$_RUN_SH\"; exec bash" & _TERM_OPENED=1
        elif command -v xfce4-terminal >/dev/null 2>&1; then
            xfce4-terminal -e "bash -c \"\\\"$_RUN_SH\\\"; exec bash\"" & _TERM_OPENED=1
        elif command -v tilix >/dev/null 2>&1; then
            tilix -e "bash -c \"\\\"$_RUN_SH\\\"; exec bash\"" & _TERM_OPENED=1
        fi
    fi

    if [[ "$_TERM_OPENED" -eq 0 ]]; then
        # Headless / no terminal emulator — run in background and poll
        if [[ -n "$_RUN_SH" ]]; then
            nohup bash "$_RUN_SH" >> "$AI_HOME/logs/launcher.log" 2>&1 &
        else
            cd "$AI_HOME" && nohup ./start.sh >> "$AI_HOME/logs/launcher.log" 2>&1 &
        fi
        echo "Bot started in background (logs: $AI_HOME/logs/launcher.log)"
        _wait_for_bot
    fi

    _open_url "$DASHBOARD_URL"
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
    echo "  0. Activate PATH in current shell:"
    echo "     source ~/.bashrc"
    echo "     (or: export PATH=\"\$HOME/.ai-employee/bin:\$PATH\")"
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
    setup_jwt_secret
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
    _restart_runtime_and_validate
    done_message
}

# MAIN
main
