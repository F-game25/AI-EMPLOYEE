#!/usr/bin/env bash
# AI Employee — Quick Installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
#
# ─── Platform guide ────────────────────────────────────────────────────────────
#   Linux:   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
#   macOS:   curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-mac.sh | bash
#   Windows: Download quick-install-windows.bat from the main branch on GitHub
# ───────────────────────────────────────────────────────────────────────────────
set -euo pipefail


R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; NC='\033[0m'

GITHUB_USER="F-game25"
GITHUB_REPO="AI-EMPLOYEE"
GITHUB_BRANCH="main"
CLONE_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
BASE_URL="https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}"

# Parse flags
ZERO_CONFIG=0
for arg in "$@"; do
  case "$arg" in
    --zero-config) ZERO_CONFIG=1 ;;
    --advanced)    ZERO_CONFIG=0 ;;
  esac
done
export ZERO_CONFIG

err()  { echo -e "${R}✗ $1${NC}"; exit 1; }
ok()   { echo -e "${G}✓ $1${NC}"; }
log()  { echo -e "${C}▸ $1${NC}"; }
warn() { echo -e "${Y}⚠ $1${NC}"; }

if [[ "$ZERO_CONFIG" == "1" ]]; then
  echo ""
  echo -e "${G}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${G}║   Zero-config install — no questions asked           ║${NC}"
  echo -e "${G}║   Defaults: Starter mode, Ollama local               ║${NC}"
  echo -e "${G}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
fi

# ── Pre-flight checks ──────────────────────────────────────────────────────────
[ "$EUID" -eq 0 ] && err "Do not run as root. Run as your regular user."
command -v curl >/dev/null 2>&1 || err "curl is required. Install it first."

# ── Platform detection ─────────────────────────────────────────────────────────
OS="$(uname -s)"
if [[ "$OS" == "Darwin" ]]; then
  log "macOS detected — redirecting to macOS-specific installer..."
  exec bash <(curl -fsSL "$BASE_URL/quick-install-mac.sh") "$@"
fi
# Linux falls through to the standard installer below

# ── Clone or update the full repository to a permanent location ────────────────
# Running install.sh from a permanent repo directory is required so that:
#   • backend/server.js and frontend/ exist when the installer builds the UI
#   • AI_EMPLOYEE_REPO_DIR written to .env points to a real, persistent path
#     (not a temp dir that gets deleted after this script exits)
INSTALL_DIR="$HOME/AI-EMPLOYEE"

if command -v git >/dev/null 2>&1; then
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Updating existing clone at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null \
      || warn "git pull failed — continuing with existing clone"
  else
    log "Cloning AI Employee repository to $INSTALL_DIR..."
    git clone --depth=1 "$CLONE_URL" "$INSTALL_DIR" \
      || err "Failed to clone repository. Check your internet connection and try again."
  fi
  ok "Repository ready at $INSTALL_DIR"
  cd "$INSTALL_DIR"

  # ── Run installer from the permanent repo clone ──────────────────────────────
  log "Running installer..."
  if [[ "$ZERO_CONFIG" == "1" ]]; then
    ZERO_CONFIG=1 bash install.sh
  else
    bash install.sh < /dev/tty
  fi

else
  # ── Fallback: git not available — download install.sh only (limited install) ──
  warn "git not found. Falling back to script-only install."
  warn "The UI (port 8787) requires the full repository. For the complete experience:"
  warn "  1) Install git:  sudo apt install git"
  warn "  2) Re-run:       curl -fsSL ${BASE_URL}/quick-install.sh | bash"
  echo ""

  TEMP_DIR=$(mktemp -d)
  trap 'rm -rf "$TEMP_DIR"' EXIT
  cd "$TEMP_DIR"

  # Download install.sh — the installer downloads all runtime files itself
  # NOTE: For maximum security, verify the commit SHA or pin a specific release tag
  # in the URL rather than using 'main'. Example:
  #   BASE_URL="https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/<commit-sha>"
  curl -fsSL "$BASE_URL/install.sh" -o install.sh || err "Failed to download install.sh"
  chmod +x install.sh

  ok "Installer downloaded"

  log "Running installer (limited — UI requires git clone for full setup)..."
  if [[ "$ZERO_CONFIG" == "1" ]]; then
    ZERO_CONFIG=1 bash install.sh
  else
    bash install.sh < /dev/tty
  fi
fi

ok "Installation complete!"

