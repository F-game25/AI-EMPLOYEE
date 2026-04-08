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
  echo -e "${G}║   Defaults: Starter mode, Ollama local, 5 agents     ║${NC}"
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

# ── Download installer ─────────────────────────────────────────────────────────
log "Downloading AI Employee installer (Linux)..."

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

cd "$TEMP_DIR"

# Download install.sh — the installer downloads all runtime files itself
curl -fsSL "$BASE_URL/install.sh" -o install.sh || err "Failed to download install.sh"
chmod +x install.sh

ok "Installer downloaded"

# ── Run installer ──────────────────────────────────────────────────────────────
log "Running installer..."
if [[ "$ZERO_CONFIG" == "1" ]]; then
  # Zero-config: no stdin required (no questions asked)
  ZERO_CONFIG=1 bash install.sh
else
  # Redirect stdin from /dev/tty so wizard prompts work even when piped through curl
  bash install.sh < /dev/tty
fi
ok "Installation complete!"

