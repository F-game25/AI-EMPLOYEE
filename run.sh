#!/bin/bash
# run.sh — Double-click friendly launcher for AI-Employee
# Opens browser and starts the bootstrap server automatically

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8787}"
URL="http://localhost:$PORT"

# Start bootstrap server in background
cd "$SCRIPT_DIR"
node bootstrap.js &
BOOTSTRAP_PID=$!

# Wait a moment for server to start
sleep 2

# Open browser (cross-platform)
if command -v open >/dev/null 2>&1; then
  # macOS
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  # Linux
  xdg-open "$URL"
elif command -v start >/dev/null 2>&1; then
  # Windows
  start "$URL"
fi

# Print info
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  🤖 AI-Employee Starting                   ║"
echo "║  Browser opening: $URL"
echo "║  Close this window when finished            ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Keep server running (trap Ctrl+C to clean up)
trap "kill $BOOTSTRAP_PID 2>/dev/null" EXIT
wait $BOOTSTRAP_PID
