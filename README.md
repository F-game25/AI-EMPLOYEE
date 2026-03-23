# 🤖 AI Employee

> **Autonomous multi-agent AI system** — download, install, and run 13 AI workers controlled via WhatsApp and a local web dashboard.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

AI Employee is a self-hosted AI workforce that runs on your own machine (Linux, macOS, or WSL). You control your agents via **WhatsApp** or the **local dashboard**, schedule tasks, and receive compact hourly status updates — no cloud subscription required.

| Feature | Details |
|---|---|
| 13 AI agents | lead-hunter, content-master, social-guru, intel-agent, product-scout, email-ninja, support-bot, data-analyst, creative-studio, crypto-trader, bot-dev, web-sales, orchestrator |
| Control | WhatsApp + Web Dashboard |
| Local LLM | Ollama support (privacy-first) or cloud (Anthropic/OpenAI) |
| Persistence | State survives restarts; bots auto-restart on crash |
| Scheduling | Schedule tasks via UI or WhatsApp |
| Status updates | Compact hourly WhatsApp reports |
| Continuous improvement | Discovery bot proposes new skills; you approve |

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| **Linux / macOS / WSL** | — | Ubuntu/Debian/Mint/macOS/WSL2 |
| **curl** | any | for downloading |
| **Python 3** | 3.10+ | for the dashboard UI (fastapi/uvicorn) |
| **OpenSSL** | any | for token generation |
| **Node.js** | 20+ | recommended (for OpenClaw) |
| **Docker** | any | optional (sandbox mode) |

Quick check:

```bash
curl --version
python3 --version
openssl version
node -v          # optional
docker --version # optional
```

---

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

The installer runs a **step-by-step wizard** that asks:

1. WhatsApp phone number (E.164 format, e.g. `+31612345678`)
2. Local LLM via Ollama? (yes/no + model name)
3. Anthropic / OpenAI API keys (optional)
4. Trading bot path (optional)
5. Enable hourly WhatsApp status updates?
6. Dashboard port (default: 3000) and UI port (default: 8787)
7. Number of workers (1–13, default: 13)

Everything is installed into **`~/.ai-employee/`**.

### Update (re-run installer)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

Re-running upgrades runtime files **without overwriting** your existing config files or `.env`.

---

## Start / Stop

### Start

```bash
cd ~/.ai-employee
./start.sh
```

The UI **opens automatically** in your browser. If it doesn't, open manually:

- **Full Dashboard:** http://127.0.0.1:8787
- **Simple Dashboard:** http://localhost:3000
- **Gateway API:** http://localhost:18789

### Stop

In a new terminal:

```bash
cd ~/.ai-employee
./stop.sh
```

---

## Connect WhatsApp (first time)

After starting, open a **new terminal** and run:

```bash
openclaw channels login
```

Scan the QR code in WhatsApp:  
**WhatsApp → Linked Devices → Link a device**

Wait for "Connected" ✓ — then send yourself a WhatsApp message to test.

---

## WhatsApp Commands

Send these to your own WhatsApp number:

| Command | Description |
|---|---|
| `Hello!` | Start a conversation with the orchestrator |
| `status` | Compact status report of all bots |
| `workers` | List active workers and their state |
| `switch to lead-hunter` | Switch to a specific agent |
| `schedule` | List scheduled tasks |
| `improvements` | Show pending skill proposals |
| `help` | Show all available commands |

**Example tasks:**

```
find 20 SaaS CTOs in the Netherlands
write a 2000 word SEO article about AI tools
analyze competitor pricing for Notion
```

---

## Dashboard (UI)

The full dashboard runs at **http://127.0.0.1:8787** and has 5 tabs:

| Tab | Description |
|---|---|
| 📊 **Dashboard** | Live bot status, system info, quick start/stop |
| 💬 **Chat** | Send tasks (same as WhatsApp), view chat history |
| 📅 **Scheduler** | Create/edit/delete scheduled tasks |
| 👷 **Workers** | Start/stop individual bots |
| 💡 **Improvements** | Review and approve/reject skill proposals |

---

## Hourly Status Updates

The **status-reporter** bot sends a compact WhatsApp message every hour:

```
🤖 AI Employee Status — 2026-03-22T10:00:00Z
─────────────────
Bots:
  🟢 problem-solver-ui
  🟢 polymarket-trader
  🔴 scheduler-runner
Trading: PAPER | signals: 0
─────────────────
Reply: status, workers, schedule, improvements
```

Configure interval in `~/.ai-employee/config/status-reporter.env`:

```bash
STATUS_REPORT_INTERVAL_SECONDS=3600  # 1 hour default
```

---

## Scheduling

Schedule tasks in the **Scheduler tab** of the dashboard, or edit:

```
~/.ai-employee/config/schedules.json
```

Example schedule entry:

```json
{
  "id": "hourly_status",
  "label": "Hourly status report",
  "action": "status_report",
  "type": "interval",
  "interval_minutes": 60,
  "enabled": true
}
```

---

## Continuous Improvement

The **discovery bot** scans your agents and proposes new skills/markets. Proposals appear in:

- Dashboard → Improvements tab
- WhatsApp: send `improvements`
- File: `~/.ai-employee/state/improvements.json`

**Nothing is changed automatically.** You approve or reject each proposal.

---

## Adjusting Workers

You can enable/disable individual bots in the **Workers tab** or via WhatsApp:

```
start status-reporter
stop polymarket-trader
```

The **problem-solver watchdog** auto-restarts any enabled bot that crashes.

---

## Where Everything is Stored

```
~/.ai-employee/
├── config.json          OpenClaw gateway config (token, phone allowlist, agents)
├── .env                 Secret keys + environment vars
├── start.sh             Start all services (auto-opens UI)
├── stop.sh              Stop all services
├── bin/
│   └── ai-employee      Multi-bot CLI runner
├── bots/                Bot code (overwritten on update)
│   ├── problem-solver/  Watchdog — keeps other bots alive
│   ├── problem-solver-ui/  Full dashboard (FastAPI)
│   ├── polymarket-trader/  Trading bot (paper mode default)
│   ├── status-reporter/ Hourly WhatsApp status
│   ├── scheduler-runner/ Task scheduler
│   └── discovery/       Skill & market discovery
├── config/              Config files (never overwritten on update)
│   ├── status-reporter.env
│   ├── problem-solver-ui.env
│   ├── schedules.json   Scheduled tasks
│   └── ...
├── state/               Persistent bot state (JSON)
│   ├── chatlog.jsonl    Chat/task history
│   ├── improvements.json Skill proposals
│   └── *.state.json     Per-bot state files
├── logs/                Log files
├── improvements/        Approved improvement files
└── workspace-*/         Per-agent workspaces + skills
```

---

## Troubleshooting

### Docker not running
```
⚠ Docker installed but not running.
```
Start Docker: `sudo systemctl start docker` (Linux) or open Docker Desktop (macOS/Windows).  
Agents work without Docker (local exec mode).

### Node.js version too old
```
⚠ Node.js 20+ recommended
```
Upgrade: https://nodejs.org or `nvm install 22`

### Python / pip not found
```
⚠ pip3 not found
```
Install: `sudo apt install python3-pip` or `brew install python3`  
Then manually: `pip3 install --user fastapi uvicorn`

### OpenClaw "Missing config" error
This means the config was not linked correctly. Fix:
```bash
mkdir -p ~/.openclaw
ln -sf ~/.ai-employee/config.json ~/.openclaw/openclaw.json
openclaw gateway --config ~/.ai-employee/config.json
```

### OpenClaw gateway won't start
Check that `gateway.mode` is set to `local` in your config:
```bash
grep '"mode"' ~/.ai-employee/config.json | head -3
```
Should show: `"mode": "local"`

### WhatsApp messages not received
1. Check phone format in config: must be E.164 (`+31612345678`)
2. Check allowlist: `grep allowFrom ~/.ai-employee/config.json`
3. Re-link: `openclaw channels login`

### UI not opening
Start it manually:
```bash
cd ~/.ai-employee/bots/problem-solver-ui
python3 server.py
```
Then open: http://127.0.0.1:8787

### Check bot logs
```bash
~/.ai-employee/bin/ai-employee logs problem-solver-ui
~/.ai-employee/bin/ai-employee logs status-reporter
~/.ai-employee/bin/ai-employee status
```

---

## Security Notes

- The installer generates a random token stored in `~/.ai-employee/.env`
- **Never share** `~/.ai-employee/.env` or `~/.ai-employee/config.json`
- The gateway only listens on `loopback` (localhost) by default
- WhatsApp `dmPolicy: allowlist` ensures only your phone can send commands
- The discovery bot is read-only — proposals require explicit approval
- API keys are stored locally and never sent to third parties by this software

---

## Uninstall

```bash
cd ~/.ai-employee && ./stop.sh || true
rm -rf ~/.ai-employee
rm -f ~/.openclaw/openclaw.json
```

> This does not uninstall Docker, Node.js, Python, or OpenClaw itself.

---

## License

MIT — see [LICENSE](LICENSE)
