#!/bin/bash
set -euo pipefail

GITHUB_USER="F-game25"
GITHUB_REPO="AI-EMPLOYEE"
BASE_URL="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main"

echo "╔════════════════════════════════════════╗"
echo "║   AI EMPLOYEE INSTALLER v3.2          ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check requirements (Docker optional)
command -v curl >/dev/null || { echo "❌ curl required"; exit 1; }
command -v node >/dev/null || { echo "❌ Node.js required"; exit 1; }

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    export USE_DOCKER=true
    echo "✓ Docker available"
else
    export USE_DOCKER=false
    echo "⚠ Docker not found (will use local mode)"
fi

# Download and run
TEMP=$(mktemp -d)
cd "$TEMP"
curl -fsSL "$BASE_URL/install.sh" -o install.sh || { echo "❌ Download failed"; exit 1; }
chmod +x install.sh
bash install.sh
cd ~ && rm -rf "$TEMP"

echo ""
echo "✅ Done! Run: cd ~/.ai-employee && ./start.sh"
