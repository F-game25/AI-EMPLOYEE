#!/bin/bash
set -euo pipefail

R='\033[0;31m';G='\033[0;32m';Y='\033[1;33m';B='\033[0;34m';C='\033[0;36m';NC='\033[0m'

GITHUB_USER="F-game25"
GITHUB_REPO="AI-EMPLOYEE"
GITHUB_BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main"

banner() {
clear
cat << 'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║              AI EMPLOYEE - ONE-CLICK INSTALLER v3.1              ║
╚════════════════════════════════════════════════════════════════��═╝
BANNER
echo ""
}

err() { echo -e "${R}✗ $1${NC}"; exit 1; }
ok() { echo -e "${G}✓ $1${NC}"; }
log() { echo -e "${C}▸ $1${NC}"; }

check_requirements() {
    log "Checking requirements..."
    [ "$EUID" -eq 0 ] && err "Don't run as root!"
    command -v curl >/dev/null 2>&1 || err "curl required"
    command -v docker >/dev/null 2>&1 || err "Docker required"
    docker info >/dev/null 2>&1 || err "Docker not running!"
    command -v node >/dev/null 2>&1 || err "Node.js 22+ required"
    NODE_V=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    [ "$NODE_V" -lt 22 ] && err "Node.js 22+ required"
    command -v python3 >/dev/null 2>&1 || err "python3 required"
    command -v openssl >/dev/null 2>&1 || err "openssl required"
    ok "Requirements met"
}

download_files() {
    log "Downloading from GitHub..."
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    curl -fsSL "$BASE_URL/install.sh" -o install.sh || err "Download failed"
    chmod +x install.sh
    ok "Files downloaded"
}

run_installer() {
    log "Running installer..."
    bash install.sh
    [ $? -eq 0 ] && ok "Installation complete!" || err "Installation failed"
}

cleanup() {
    cd ~
    rm -rf "$TEMP_DIR" 2>/dev/null || true
}

show_next_steps() {
    clear
    banner
    echo -e "${G}✅ INSTALLATION COMPLETE!${NC}"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo "  1. cd ~/.ai-employee && ./start.sh"
    echo "  2. openclaw channels login  (new terminal)"
    echo "  3. Open http://localhost:3000"
    echo "  4. Problem Solver UI: http://127.0.0.1:8787"
    echo ""
}

main() {
    banner
    check_requirements
    download_files
    run_installer
    cleanup
    show_next_steps
}

main
