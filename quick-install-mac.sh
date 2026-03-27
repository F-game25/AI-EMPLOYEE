#!/usr/bin/env bash
# AI Employee — macOS Quick Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/mac/quick-install-mac.sh | bash
set -euo pipefail

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; NC='\033[0m'

GITHUB_USER="F-game25"
GITHUB_REPO="AI-EMPLOYEE"
GITHUB_BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}"

err()  { echo -e "${R}✗ $1${NC}"; exit 1; }
ok()   { echo -e "${G}✓ $1${NC}"; }
log()  { echo -e "${C}▸ $1${NC}"; }
warn() { echo -e "${Y}⚠ $1${NC}"; }

# ── Pre-flight checks ──────────────────────────────────────────────────────────
[ "$EUID" -eq 0 ] && err "Do not run as root. Run as your regular user."
command -v curl >/dev/null 2>&1 || err "curl is required. Install it first: brew install curl"

# Verify that the installer file exists on the target branch
if ! curl -fsSL --head "$BASE_URL/install-mac.sh" 2>/dev/null | grep -q "200"; then
    err "Cannot reach install-mac.sh on the '${GITHUB_BRANCH}' branch. Check your internet connection or try: bash create-branches.sh && git push origin main"
fi

# macOS check
if [[ "$(uname)" != "Darwin" ]]; then
    err "This installer is for macOS only.
  Linux:   curl -fsSL https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/main/quick-install.sh | bash
  Windows: Download install-windows.ps1 from the windows branch on GitHub"
fi

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║      AI EMPLOYEE - macOS Quick Installer             ║"
echo "  ║  curl | bash one-liner for Mac                       ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

# ── Download installer + runtime ───────────────────────────────────────────────
log "Downloading AI Employee macOS installer..."

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

cd "$TEMP_DIR"

# Download macOS install script
curl -fsSL "$BASE_URL/install-mac.sh" -o install-mac.sh || err "Failed to download install-mac.sh"
chmod +x install-mac.sh

# Download runtime directory structure
log "Downloading runtime files..."
mkdir -p runtime/{bin,config,improvements}
mkdir -p runtime/bots/{problem-solver,problem-solver-ui,polymarket-trader,status-reporter,scheduler-runner,discovery}

dl() {
    local rel="$1"
    curl -fsSL "$BASE_URL/runtime/$rel" -o "runtime/$rel" 2>/dev/null || warn "Could not download runtime/$rel"
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

ok "Files downloaded"

# ── Run installer ──────────────────────────────────────────────────────────────
log "Running macOS installer..."
# Redirect stdin from /dev/tty so wizard prompts work even when piped through curl
bash install-mac.sh < /dev/tty
ok "Installation complete!"
