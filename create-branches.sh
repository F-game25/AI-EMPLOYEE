#!/usr/bin/env bash
# AI Employee — Create platform branches
# Run this script once from the 'main' branch to create 'mac' and 'windows' branches.
#
# Usage: bash create-branches.sh
# Requirements: git, must be run from the repo root with main branch checked out
set -euo pipefail

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; R='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "${G}✓${NC} $1"; }
log()  { echo -e "${C}▸${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }
err()  { echo -e "${R}✗${NC} $1"; exit 1; }

echo ""
echo -e "${C}━━━ AI Employee — Create Platform Branches ━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Verify we're on main ────────────────────────────────────────────────────────
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    warn "Not on 'main' branch (current: $CURRENT_BRANCH)"
    read -r -p "Continue anyway? [y/N]: " cont
    [[ "$cont" =~ ^[Yy]$ ]] || exit 0
fi

# ── Verify repo root ────────────────────────────────────────────────────────────
[[ -f "install.sh" ]] || err "Run this from the repo root (where install.sh is)"

# ── Create mac branch ──────────────────────────────────────────────────────────
log "Creating 'mac' branch..."

if git show-ref --quiet refs/heads/mac; then
    warn "Branch 'mac' already exists locally — deleting and recreating"
    git branch -D mac
fi

git checkout -b mac

# On mac branch: remove Windows-specific files, keep macOS files
log "Removing Windows-only files from mac branch..."
git rm -f install.bat start.bat quick-install-windows.bat 2>/dev/null || true

# Replace the main install.sh with the mac installer
if [[ -f "install-mac.sh" ]]; then
    cp install-mac.sh install.sh
    git add install.sh
fi

# Replace quick-install.sh with mac version
if [[ -f "quick-install-mac.sh" ]]; then
    cp quick-install-mac.sh quick-install.sh
    git add quick-install.sh
fi

# Remove start.ps1 (Windows-only)
git rm -f start.ps1 start-windows.ps1 install-windows.ps1 2>/dev/null || true

git commit -m "mac: macOS-specific installer and quick-install" || true
ok "mac branch created"

# ── Create windows branch ──────────────────────────────────────────────────────
log "Creating 'windows' branch..."
git checkout main

if git show-ref --quiet refs/heads/windows; then
    warn "Branch 'windows' already exists locally — deleting and recreating"
    git branch -D windows
fi

git checkout -b windows

# On windows branch: remove Linux/macOS specific files
log "Removing Linux/macOS-only files from windows branch..."
git rm -f install.sh install-mac.sh quick-install.sh quick-install-mac.sh 2>/dev/null || true
git rm -f runtime/start.sh runtime/stop.sh 2>/dev/null || true

# The main installer on windows branch is install-windows.ps1
# install.bat already calls install-windows.ps1

# Replace start.ps1 with the Windows-native version  
if [[ -f "start-windows.ps1" ]]; then
    cp start-windows.ps1 start.ps1
    git add start.ps1
fi

git commit -m "windows: Windows-specific installer and starter" || true
ok "windows branch created"

# ── Return to main ─────────────────────────────────────────────────────────────
git checkout main
ok "Back on main branch"

echo ""
echo -e "${G}✓ Branches created successfully!${NC}"
echo ""
echo "Next: push the branches to GitHub:"
echo "  git push origin mac"
echo "  git push origin windows"
echo ""
echo "Users can then download per OS:"
echo "  Linux:   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash"
echo "  macOS:   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/mac/quick-install-mac.sh | bash"
echo "  Windows: Download quick-install-windows.bat from the 'windows' branch"
echo ""
