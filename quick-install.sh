#!/bin/bash
set -euo pipefail

R='\033[0;31m';G='\033[0;32m';Y='\033[1;33m';B='\033[0;34m';C='\033[0;36m';NC='\033[0m'
GITHUB_USER="F-game25"
GITHUB_REPO="AI-EMPLOYEE"
GITHUB_BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/$GITHUB_BRANCH"

banner() {
clear
cat << 'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║         AI EMPLOYEE - ONE-CLICK INSTALLER v3.2                   ║
║              Docker Optional • Works Everywhere                   ║
╚══════════════════════════════════════════════════════════════════╝
BANNER
}

err() { echo -e "${R}✗ $1${NC}"; exit 1; }
ok() { echo -e "${G}✓ $1${NC}"; }
log() { echo -e "${C}▸ $1${NC}"; }
warn() { echo -e "${Y}⚠ $1${NC}"; }

check_requirements() {
    log "Checking requirements..."
    [ "$EUID" -eq 0 ] && err "Don't run as root!"
    command -v curl >/dev/null 2>&1 || err "curl required"
    command -v node >/dev/null 2>&1 || err "Node.js 22+ required"
    NODE_V=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    [ "$NODE_V" -lt 22 ] && err "Node.js 22+ required (you have v$NODE_V)"
    
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        ok "Docker available"
        export USE_DOCKER=true
    else
        warn "Docker not found - using local mode"
        export USE_DOCKER=false
    fi
    ok "Requirements met"
}

main() {
    banner
    echo ""
    check_requirements
    log "Downloading installer..."
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    curl -fsSL "$BASE_URL/install.sh" -o install.sh || err "Download failed"
    chmod +x install.sh
    log "Running installer..."
    bash install.sh
    cd ~ && rm -rf "$TEMP_DIR"
    clear
    banner
    echo -e "\n${G}✅ Installation complete!${NC}\n"
    echo "Next steps:"
    echo "  1. cd ~/.ai-employee && ./start.sh"
    echo "  2. openclaw channels login"
    echo "  3. Open http://localhost:3000"
    echo ""
}

main
