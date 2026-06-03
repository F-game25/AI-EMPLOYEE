# AI Employee — Windows Setup Guide

## Quickest path: Docker Desktop (recommended)

No Python or Node.js installation required.

### Step 1 — Install Docker Desktop
Download from https://www.docker.com/products/docker-desktop  
During install, enable **WSL 2** when prompted.

### Step 2 — Clone or download the repo
```
git clone https://github.com/F-game25/AI-EMPLOYEE.git
cd AI-EMPLOYEE
```

### Step 3 — Create your `.env` file
Copy the example and fill in your API key:
```
copy .env.example .env.local
notepad .env.local
```
Minimum required:
```
JWT_SECRET_KEY=<paste output of: python -c "import secrets; print(secrets.token_hex(32))">
ANTHROPIC_API_KEY=sk-ant-...
```
To use OpenRouter instead of Anthropic:
```
LLM_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o
```

### Step 4 — Start
Double-click **start.bat** or run in a terminal:
```
start.bat
```
Docker will build the image (~2 min first time), then open http://localhost:8787 automatically.

### Step 5 — Stop
Double-click **stop.bat** or:
```
stop.bat
```

---

## Native mode (no Docker — requires Node.js + Python)

If you prefer not to use Docker:

### Prerequisites
| Tool | Version | Download |
|------|---------|----------|
| Node.js | 20 LTS | https://nodejs.org |
| Python | 3.11+ | https://python.org |
| Git | any | https://git-scm.com |

### Start
```
start.bat
```
The script detects Git Bash / WSL / native Node automatically.

---

## Troubleshooting

**"Docker not running"** — Start Docker Desktop from the Start Menu and wait for the whale icon in the system tray to stop animating.

**Port 8787 already in use** — Run `stop.bat` first, or change `ports: "8787:8787"` to `"8788:8787"` in `docker-compose.dev.yml`.

**Slow first start** — Docker is downloading/building the image. Subsequent starts take ~5s.

**Chat returns stub responses** — The Python AI backend may still be starting. Wait 20–30s after startup, then refresh.

**OpenRouter models not loading** — Go to Settings → LLM → select OpenRouter → enter your `sk-or-...` key → Test Connection → Save.
