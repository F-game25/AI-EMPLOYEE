# Getting Started — AI-Employee

## Quick Start (No Terminal Required)

### Windows
1. **Double-click** `run.bat` in the project folder
2. A browser will open automatically
3. Follow the on-screen setup wizard
4. Done! Dashboard opens when ready

### macOS / Linux
1. **Double-click** `run.sh` in the project folder (or open Terminal and run `bash run.sh`)
2. A browser will open automatically
3. Follow the on-screen setup wizard
4. Done! Dashboard opens when ready

## What Happens During Boot

The **Bootstrap Server** (`bootstrap.js`) starts automatically and does the following:

### Phase 1: System Check
- Verifies Node.js and Python 3 are available
- Displays progress in real-time

### Phase 2: Install Dependencies (if needed)
- **Python**: Installs `fastapi`, `uvicorn`, `anthropic`, `psutil`, and other core packages from `requirements-core.txt`
- **Node**: Installs dependencies for backend and frontend

### Phase 3: Build Frontend
- Compiles React components into production-ready assets
- Uses cached builds if source hasn't changed (fast boot)

### Phase 4: Generate Identity
- Creates a unique identity for your installation
- Generates random instance name (e.g., "Aurora-Prime", "Zenith-Elite")
- Sets random color palette (premium purples and golds)
- Stored at `~/.ai-employee/identity.json` (unique per machine)

### Phase 5: Onboarding (Optional)
Once everything is ready:
1. Enter your name (how the system addresses you)
2. Override instance name if desired
3. Choose voice tone (Professional, Friendly, Creative, Concise)
4. Pick a color palette variant
5. Click "Complete Setup"

The system then starts fully and shows the dashboard.

## Under the Hood

```
User double-clicks run.sh/run.bat
         ↓
bootstrap.js starts (minimal footprint)
         ↓
Shows installation wizard in browser
         ↓
Parallel install: Python deps + Node deps
         ↓
Build frontend (cached if source unchanged)
         ↓
Generate identity (~/.ai-employee/identity.json)
         ↓
All ready → "Enter Dashboard" button activates
         ↓
Backend server (backend/server.js) starts
         ↓
Dashboard loads at http://localhost:8787
```

## Directory Structure

After first boot, this is created at `~/.ai-employee/`:

```
~/.ai-employee/
├── identity.json           # Your unique identity (instance name, colors, tenant ID)
├── .env                    # Environment variables (JWT secret, API keys)
├── state/
│   ├── audit.db            # Audit trail (for growth tracking)
│   ├── bus.jsonl           # Event stream
│   └── python-backend.log  # Python server logs
├── tenants/                # Multi-tenant data (if used)
├── credentials/            # Encrypted API keys (future)
├── capabilities/           # Feature manifest
├── models/                 # Downloaded models (embeddings, etc.)
└── logs/                   # System logs
```

## Environment Variables

The system auto-generates `~/.ai-employee/.env` with defaults. You can customize:

```bash
# Required (add your own)
ANTHROPIC_API_KEY=sk-...

# Optional (defaults provided)
PORT=8787
PYTHON_PORT=18790
LLM_BACKEND=anthropic           # or: ollama
LOG_LEVEL=INFO
EVOLUTION_MODE=AUTO             # or: SAFE, OFF
```

## Troubleshooting

### "Browser didn't open"
- Manually open http://localhost:8787 in your browser

### "Python dependencies failed"
- Check `~/.ai-employee/logs/` for error details
- Ensure Python 3.10+ is installed: `python3 --version`
- Try manual install: `pip3 install -r runtime/requirements-core.txt`

### "Frontend build failed"
- Check frontend logs in bootstrap UI
- Ensure Node 18+ is installed: `node --version`
- Try manual build: `cd frontend && npm run build`

### "Can't find ~/.ai-employee"
- The directory is created automatically on first boot
- Check `echo $HOME` (macOS/Linux) or `%USERPROFILE%` (Windows) to verify home directory

## Next Steps

1. **Add your API key**: Edit `~/.ai-employee/.env` and add your `ANTHROPIC_API_KEY`
2. **Explore the dashboard**: System metrics, agent swarm, revenue intelligence
3. **Customize your identity**: Dashboard → Settings → Identity to change colors and tone
4. **Enable features**: Use the "Modules" panel to enable optional capabilities (Mailchimp, Stripe, etc.)

## Development Mode

For live hot-reload during development:

```bash
# Terminal 1: Backend (watches API changes)
PORT=8787 node backend/server.js

# Terminal 2: Frontend (watches React changes, hot reload at :5173)
cd frontend && npm run dev
```

Then open http://localhost:5173 (Vite dev server proxies API calls to backend on :8787).

## Architecture

- **Bootstrap Server** (`bootstrap.js`): Minimal installer UI, runs once
- **Backend** (`backend/server.js`): Express + WebSocket, port 8787
- **Python AI** (`runtime/agents/problem-solver-ui/server.py`): FastAPI/uvicorn, port 18790
- **Frontend** (`frontend/`): React + Vite, compiled to `frontend/dist/`

All three start automatically via `run.sh` or `run.bat` after dependencies are installed.

## Support

- **Logs**: Check `~/.ai-employee/logs/` and `~/.ai-employee/state/`
- **GitHub Issues**: Report bugs at https://github.com/anthropics/claude-code/issues
- **Feedback**: /help (in Claude Code) or email
