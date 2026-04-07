#!/usr/bin/env bash
# AI-EMPLOYEE Dashboard — starts Node.js backend + React frontend dev server
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${C}▸${NC} $1"; }
ok()   { echo -e "${G}✓${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }

# Install backend deps if needed
if [ ! -d "$BACKEND_DIR/node_modules" ]; then
  log "Installing backend dependencies..."
  cd "$BACKEND_DIR" && npm install
fi

# Install frontend deps if needed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  log "Installing frontend dependencies..."
  cd "$FRONTEND_DIR" && npm install
fi

# Start backend
log "Starting AI-EMPLOYEE backend on port 3001..."
cd "$BACKEND_DIR"
node server.js &
BACKEND_PID=$!
ok "Backend started (PID $BACKEND_PID)"

# Give backend a moment to start
sleep 1

# Start frontend dev server
log "Starting frontend dev server on port 3000..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!
ok "Frontend started (PID $FRONTEND_PID)"

echo ""
echo -e "  ${C}🖥  Dashboard:${NC}  http://localhost:3000"
echo -e "  ${C}🔌 Backend:${NC}    http://localhost:3001"
echo -e "  ${C}🔗 WebSocket:${NC}  ws://localhost:3001/ws"
echo ""
echo -e "  Press ${Y}Ctrl+C${NC} to stop all services"

# Wait for any process to exit
wait $BACKEND_PID $FRONTEND_PID
