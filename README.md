# 🤖 AI Employee

> **Autonomous 20-agent AI company** — download, install, and run 20 AI workers controlled via WhatsApp and a local web dashboard. Give the AI any task — it self-selects agents, decomposes the work, and executes in parallel.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

AI Employee is a self-hosted AI workforce that runs on your own machine (Linux, macOS, or WSL). You control your agents via **WhatsApp** or the **local dashboard**, give them tasks in plain English, and watch them collaborate autonomously.

| Feature | Details |
|---|---|
| **20 AI agents** | Full company team: strategy, finance, HR, brand, growth, PM + specialist bots |
| **Task Orchestrator** | Give any task → AI decomposes it → assigns agents → runs in parallel → aggregates results |
| **ROI Dashboard** | Track tasks completed, leads generated, hours saved, and cost/revenue metrics |
| **Agent Templates** | Pre-built plug-and-play templates: Sales Agent, Support Bot, Recruitment Bot, and more |
| **Guardrails** | Approval queue for high-risk actions, action logging, and rate limits |
| **Memory** | Persistent client/customer memory across all sessions and conversations |
| **Integrations** | Configuration UI for Gmail, Google Sheets, Telegram, Slack, OpenAI, Anthropic, Webhooks |
| Control | WhatsApp + Web Dashboard (14-tab dashboard) |
| Local LLM | Ollama support (privacy-first) or cloud (Anthropic/OpenAI) |
| Persistence | State survives restarts; bots auto-restart on crash |
| Scheduling | Schedule tasks via UI or WhatsApp |
| 126 skills | 17 categories covering every business function |
| Continuous improvement | Discovery bot proposes new skills; you approve |

---

## 📊 Dashboard (14 Tabs)

Open the dashboard at **http://localhost:8787** after starting:

| Tab | What it shows |
|---|---|
| 📊 Dashboard | Bot status overview, quick actions, system info |
| 💬 Chat | Send tasks, view chat history (mirrors WhatsApp) |
| 🚀 Tasks | Build & launch multi-agent tasks, track active/recent tasks |
| 🐝 Swarm | All 20 agents — capabilities, status, workload |
| 📜 Commands | Full command reference, searchable by category |
| 📅 Scheduler | Create & manage scheduled tasks (interval/daily) |
| 👷 Workers | Start/stop individual bots, manage Worker Bundles |
| 💡 Improvements | Review & approve AI-proposed skill upgrades |
| 🛠️ Skills | Browse 126-skill library, create custom agents |
| 📈 ROI | KPI metrics: tasks done, leads generated, hours saved, €€ saved |
| 📋 Templates | Pre-built agent templates — deploy a full AI team in one click |
| 🔒 Guardrails | Action approval queue, safety logs, rate limit configuration |
| 🧠 Memory | Client CRM memory, recent interactions, context tracking |
| 🔌 Integrations | Configure Gmail, Sheets, Telegram, Slack, OpenAI, Webhooks |

---

## 📈 ROI Metrics

Track the business value your AI team creates:

```bash
# Via WhatsApp / Chat:
metrics                    # Show ROI summary
metrics record lead_generated  # Log an event
metrics record deal_closed:5000  # Log deal worth €5000
```

**Tracked metrics:**
- ✅ Tasks completed
- 🎯 Leads generated
- 📧 Emails sent
- 📝 Content created
- 📞 Calls booked
- 💰 Deals closed (with revenue)
- ⏱️ Hours saved (auto-calculated per event type)
- 💶 Cost saved (hours × €75/h by default — customise with `AI_EMPLOYEE_HOURLY_RATE` env var)

---

## 📋 Agent Templates

Deploy a pre-configured AI team in one click from the **📋 Templates** tab:

| Template | Agents | Est. ROI |
|---|---|---|
| **Sales Agent** | lead-hunter, email-ninja, growth-hacker, intel-agent | €3,000–€8,000/month |
| **Customer Support Bot** | support-bot, data-analyst | €2,500–€5,000/month |
| **Recruitment Bot** | recruiter, hr-manager, email-ninja | €4,000–€10,000/month |
| **Lead Generation Machine** | lead-hunter, intel-agent, data-analyst | 150 leads/week |
| **Content Automation Engine** | content-master, social-guru, email-ninja, creative-studio | €2,000–€6,000/month |
| **E-commerce Operations** | 8 specialist agents | €5,000–€15,000/month |

```bash
# Via WhatsApp / Chat:
templates                  # List all templates
template deploy sales-agent  # Deploy the Sales Agent template
```

---

## 🔒 Guardrails

Prevent the AI from taking dangerous actions without your approval:

**Default approval required for:**
- Sending bulk emails
- Posting to social media
- Making purchases / placing orders
- Deleting or modifying data

```bash
# Via WhatsApp / Chat:
guardrails                 # View pending approvals
approve <action_id>        # Approve an action
reject <action_id>         # Reject an action
```

**API:**
```bash
POST /api/guardrails/request        # Submit action for approval (used by agents)
POST /api/guardrails/{id}/approve   # Approve
POST /api/guardrails/{id}/reject    # Reject
GET  /api/guardrails                # List pending + logs
POST /api/guardrails/settings       # Update settings
```

---

## 🧠 Memory

The AI remembers your clients across all conversations and tasks:

```bash
# Via WhatsApp / Chat:
memory                         # Show all clients
clients                        # Alias
client add John Smith          # Add a client
client add John Acme Corp      # With company name
```

**API:**
```bash
GET    /api/memory                       # All clients + recent interactions
POST   /api/memory/clients               # Add client
PATCH  /api/memory/clients/{id}          # Update (status, notes, etc.)
DELETE /api/memory/clients/{id}          # Remove
POST   /api/memory/interactions          # Log an interaction (used by agents)
```

---

## 🔌 Integrations

Configure connections in the **🔌 Integrations** tab or via API:

| Integration | Use |
|---|---|
| **Gmail / Google Workspace** | Send/receive email, create drafts |
| **Google Sheets** | Read/write CRM data, reports |
| **Telegram Bot** | Receive commands, send alerts |
| **Slack** | Post to channels, receive commands |
| **OpenAI** | GPT-4 cloud AI fallback |
| **Anthropic Claude** | Claude AI provider |
| **Outbound Webhook** | Forward events to Zapier, Make, n8n, etc. |

**API:**
```bash
GET   /api/integrations             # List all integrations with status
PATCH /api/integrations/{id}        # Save config
POST  /api/integrations/{id}/test   # Test connection
```

---


## 🤖 The 20 Agents

### Core Business Team (NEW)
| Agent | Prefix | What it does |
|---|---|---|
| **task-orchestrator** | `task <description>` | 🧠 Master brain — decomposes tasks, assigns agents, runs parallel workflows |
| **company-builder** | `company build <idea>` | 🏢 Build companies from scratch: plans, simulations, GTM, org design |
| **memecoin-creator** | `memecoin create <concept>` | 🪙 Full token launch: tokenomics, whitepaper, viral marketing |
| **hr-manager** | `hr hire <role>` | 👔 Hiring pipeline, onboarding, org charts, culture docs |
| **finance-wizard** | `finance model <business>` | 💰 P&L models, fundraising prep, unit economics, valuation |
| **brand-strategist** | `brand identity <company>` | 🎨 Brand naming, identity systems, positioning, messaging |
| **growth-hacker** | `growth loop <product>` | 🚀 Viral loops, A/B tests, retention, referral programs |
| **project-manager** | `pm start <project>` | 📋 Sprints, roadmaps, risk registers, Gantt charts |

### Specialist Bots (Original 13)
| Agent | What it does |
|---|---|
| **orchestrator** | WhatsApp command routing + task coordination |
| **lead-hunter** | B2B lead generation + cold outreach CRM |
| **content-master** | SEO blog posts + long-form content |
| **social-guru** | Viral social media + captions + hashtags |
| **intel-agent** | Competitor monitoring + market research |
| **product-scout** | E-commerce product research + arbitrage |
| **email-ninja** | Cold email sequences + deliverability |
| **support-bot** | Customer support + FAQ + ticket routing |
| **data-analyst** | Market trends + reports + KPI tracking |
| **creative-studio** | Ad copy + design briefs + campaign concepts |
| **crypto-trader** | Technical analysis + trading signals |
| **bot-dev** | Python bot development + code review |
| **web-sales** | Website audits + sales pitches + UX analysis |

---

## 🧠 Multi-Agent Task Orchestration

The **Task Orchestrator** is the system's brain. Give it any goal:

```
task Build a SaaS company for remote team productivity
```

The orchestrator will:
1. **Decompose** the task into 3-8 subtasks using AI
2. **Assign** each subtask to the most capable agent
3. **Run** parallel tasks simultaneously (up to 5 at once)
4. **Monitor** progress and handle dependencies
5. **Aggregate** all results into a comprehensive answer

### Example Multi-Agent Tasks

```bash
# Build a full company from scratch
task Build an AI tutoring platform: create business plan, brand identity, hiring roadmap, and GTM strategy

# Launch a memecoin
task Launch a dog-themed memecoin: design tokenomics, draft whitepaper, create viral community strategy

# Market research to content pipeline
task Research the AI productivity tools market and create 3 SEO blog posts targeting decision makers

# Complete startup package
task Create a complete startup package for a fintech app: validate idea, model financials, design brand, plan first sprint
```

### Standalone Commands

Every agent also works independently:

```bash
# Company Building
company build <idea>          # full launch package
company validate <idea>       # viability check
company simulate <scenario>   # growth simulation
company pitch <company>       # investor pitch deck

# Memecoin Creation
memecoin create <concept>     # full launch package
memecoin tokenomics <name>    # design tokenomics
memecoin whitepaper <name>    # draft whitepaper
memecoin viral <name>         # viral campaign

# HR & People
hr hire <role>                # full hiring package
hr screen <cv>                # AI CV scoring
hr onboard <role>             # 90-day onboarding plan
hr culture <company>          # culture & values doc

# Finance
finance model <business>      # 3-year financial model
finance raise <stage> for <amount>  # fundraising prep
finance unit <product> at <price>   # unit economics

# Brand
brand identity <company>      # full brand system
brand name <industry>         # name generation
brand voice <company>         # voice & tone guide

# Growth
growth loop <product>         # viral growth loop
growth abtests <feature>      # A/B test framework
growth referral <product>     # referral program design

# Project Management
pm start <project>            # kick off project
pm sprint <goal>              # sprint planning
pm gantt <project>            # Gantt chart
pm risks <project>            # risk register
```

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
7. Number of workers (1–20, default: 20)

Everything is installed into **`~/.ai-employee/`**.

### Update (re-run installer)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

Re-running upgrades runtime files **without overwriting** your existing config files or `.env`.

During installation you will be asked for:
- Your WhatsApp number
- Anthropic API key (optional – required for **Claude Agent**)
- Claude model name (default: `claude-opus-4-5`)
- Ollama model name (default: `llama3`) and host (default: `http://localhost:11434`)

---

## Start / Stop

### Start

```bash
cd ~/.ai-employee
./start.sh
```

You should see:
- Web UI: `http://localhost:3000`
- Gateway: `http://localhost:18789`
- Problem Solver UI: `http://127.0.0.1:8787`
- **Claude AI Agent UI**: `http://127.0.0.1:8788`
- **Ollama Local Agent UI**: `http://127.0.0.1:8789`
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

## Start without a terminal (desktop launcher)

The installer creates a **desktop launcher** so you can start AI Employee by double-clicking — no terminal needed after the first-time WhatsApp link.

| Platform | How to start |
|---|---|
| **Linux** | Double-click `~/Desktop/ai-employee.desktop` **or** search *"AI Employee"* in your app menu |
| **macOS** | Double-click `~/Desktop/Start AI Employee.command` |
| **Autostart on login** | `systemctl --user enable --now ai-employee` |

> **Note:** You still need a terminal **once** to scan the WhatsApp QR code (`openclaw channels login`).  After that, everything is controllable via WhatsApp messages and the web dashboard.

Once running, open the dashboard in your browser:
- **Full Dashboard:** http://127.0.0.1:8787
- **Simple Dashboard:** http://localhost:3000

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

```text
switch to lead-hunter
switch to claude-agent
switch to ollama-agent
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

## 5) Claude AI Agent (separate agent)

The **Claude Agent** is a standalone bot that uses the Anthropic Claude API directly. It runs independently of the main gateway and provides a dedicated web UI.

### Requirements
- An **Anthropic API key** (`ANTHROPIC_API_KEY` in `~/.ai-employee/.env`)

### Web UI
After starting AI Employee, open:
**http://127.0.0.1:8788**

### Features
- Multi-turn conversation with persistent history
- Configurable Claude model (set `CLAUDE_MODEL` in `~/.ai-employee/config/claude-agent.env`)
- Token usage reporting
- Accessible via WhatsApp: `switch to claude-agent`

### Configuration
Edit `~/.ai-employee/config/claude-agent.env`:
```env
CLAUDE_AGENT_HOST=127.0.0.1
CLAUDE_AGENT_PORT=8788
CLAUDE_MODEL=claude-opus-4-5
CLAUDE_MAX_TOKENS=4096
```

---

## 6) Ollama Local Agent (run AI locally)

The **Ollama Agent** runs a local LLM via [Ollama](https://ollama.ai/) — no data leaves your machine.

### Requirements
1. Install Ollama: https://ollama.ai/download
2. Pull your chosen model:
   ```bash
   ollama pull llama3
   # or: ollama pull mistral
   # or: ollama pull codellama
   ```
3. Ollama must be running (`ollama serve`) when you start AI Employee

### Web UI
After starting AI Employee, open:
**http://127.0.0.1:8789**

### Features
- Privacy-first: all processing on your local machine
- Multi-turn conversation with persistent history
- Configurable model and Ollama host
- Accessible via WhatsApp: `switch to ollama-agent`

### Configuration
Edit `~/.ai-employee/config/ollama-agent.env`:
```env
OLLAMA_AGENT_HOST=127.0.0.1
OLLAMA_AGENT_PORT=8789
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

## 7) Web UI (Dashboard)
## Scheduling

Schedule tasks in the **Scheduler tab** of the dashboard, or edit:

- **Web UI:** http://localhost:3000
- **Gateway API:** http://localhost:18789

### What the Web UI is
The Web UI is a simple local dashboard:
- shows which agents exist
- shows "quick actions" and usage hints
- links to Claude Agent UI and Ollama Agent UI
- runs locally on your machine (served from `~/.ai-employee/ui`)
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

## 8) Where everything is stored
## Adjusting Workers

You can enable/disable individual bots in the **Workers tab** or via WhatsApp:

```
start status-reporter
stop polymarket-trader
```

Important files:
- `~/.ai-employee/config.json` (OpenClaw config)
- `~/.ai-employee/.env` (token + API keys including `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, `OLLAMA_MODEL`)
- `~/.ai-employee/logs/` (logs)
- `~/.ai-employee/workspace-*/` (agent workspaces)
- `~/.ai-employee/bots/claude-agent/` (Claude AI standalone bot)
- `~/.ai-employee/bots/ollama-agent/` (Ollama local AI standalone bot)
- `~/.ai-employee/config/claude-agent.env` (Claude agent config)
- `~/.ai-employee/config/ollama-agent.env` (Ollama agent config)
- `~/.openclaw/openclaw.json` (symlink to config, if supported)

---

## 9) Maintenance / Updates
The **problem-solver watchdog** auto-restarts any enabled bot that crashes.

---

## Skills Library (100+ Skills)

AI Employee includes a library of **111 reusable skills** across 11 categories. Skills are the building blocks for creating custom specialised agents.

### Categories & skill counts

| Category | Skills |
|---|---|
| Content & Writing | 15 |
| Research & Analysis | 12 |
| Trading & Finance | 12 |
| Social Media | 10 |
| Lead Generation & Sales | 10 |
| Development & Technical | 10 |
| E-commerce & Product | 10 |
| Data Analysis | 8 |
| Customer Support | 8 |
| Marketing & SEO | 8 |
| Automation & Productivity | 8 |

### Managing skills via the Dashboard

Open the **🛠️ Skills** tab (http://127.0.0.1:8787):
- **Browse** all 111 skills with search and category filters
- **Click** skill cards to select them
- **Create** a new custom agent from the selected skills
- **View** and delete your custom agents

### Managing skills via WhatsApp / Chat

```
skills                              → show library summary
skills categories                   → list all categories
skills list Trading & Finance       → list skills in a category
skills search blog                  → search by name/tag/description
agents                              → list all custom agents
agent My Content Writer             → show agent details
create agent My Writer with blog_writing, headline_generation, seo_optimization
add skill keyword_research to My Writer
remove skill keyword_research from My Writer
delete agent My Writer
```

### skills-manager agent

The `skills-manager` runs in the background, polls the chatlog every 5 seconds, and processes all skills commands.  Custom agents are stored in `~/.ai-employee/config/custom_agents.json`.

Each custom agent has a generated **system prompt** that describes all its assigned skills, ready to use with any LLM.

Configure in `~/.ai-employee/config/skills-manager.env`:
```env
SKILLS_MANAGER_POLL_INTERVAL=5   # seconds between chatlog polls
SKILLS_MANAGER_MAX_SKILLS=20     # max skills per agent
```

### External signals for MiroFish skills

When `mirofish_prediction` skill is used, populate `~/.ai-employee/config/mirofish_signals.json` with signals for each market (see MiroFish section above).

---

## OpenClaw 2.0 Integration

> **Note:** If you have an `openclaw-2.0` (safe version) repository, place its `main` file at:
> ```
> ~/.ai-employee/bin/openclaw2
> ```
> Then set `OPENCLAW_BIN=openclaw2` in `~/.ai-employee/.env` to have the start script use it instead of the standard `openclaw` binary.  The `start.sh` script already reads `OPENCLAW_BIN` from the environment for this purpose.
>
> *Share your openclaw 2.0 repo URL to integrate it directly into this repo.*

---

## MiroFish Swarm Intelligence

[MiroFish](https://github.com/666ghj/MiroFish) is an open-source multi-agent prediction engine that simulates thousands of autonomous agents to forecast real-world outcomes.  AI Employee integrates MiroFish in two ways:

### Inline predictor (polymarket-trader)

The trader runs a lightweight swarm simulation on every market quote to estimate the probability of YES resolution.  Each agent has a random personality (optimism bias, herd tendency, expertise) and iteratively updates its belief by blending its own signal processing with the emerging crowd consensus.

Configure in `~/.ai-employee/config/polymarket-trader.env`:

```env
MIROFISH_ENABLED=true
MIROFISH_AGENTS=200    # agents per simulation (lower = faster)
MIROFISH_ROUNDS=15     # interaction rounds per simulation
```

### mirofish-researcher agent (separate)

A dedicated background agent that runs deeper simulations (more agents, more rounds, multi-scenario analysis) and writes probability estimates to `~/.ai-employee/config/polymarket_estimates.json`.  The polymarket-trader automatically reads these and blends them (60 % researcher weight, 40 % inline simulation) for higher-quality signals.

**Start / stop:**
```bash
~/.ai-employee/bin/ai-employee start mirofish-researcher
~/.ai-employee/bin/ai-employee stop  mirofish-researcher
~/.ai-employee/bin/ai-employee logs  mirofish-researcher
```

**Configure markets to research** — edit `~/.ai-employee/config/mirofish-researcher.env`:
```env
MIROFISH_RESEARCH_INTERVAL=300   # seconds between research cycles
MIROFISH_AGENTS=500
MIROFISH_ROUNDS=20
MIROFISH_SCENARIOS=5
RESEARCH_MARKETS=market-id-1,market-id-2
```

**Provide external signals** — edit `~/.ai-employee/config/mirofish_signals.json`:
```json
{
  "your-market-id": {
    "sentiment":    0.3,
    "volume_trend": 0.1,
    "news_impact":  0.2
  }
}
```
Each signal is in `[-1, 1]`: `-1` = very bearish/negative/declining, `+1` = very bullish/positive/increasing.

**Research output** is available at:
- `~/.ai-employee/state/mirofish-researcher.state.json` — full per-market report with distribution analysis and scenario confidence intervals
- `~/.ai-employee/config/polymarket_estimates.json` — prob_yes per market (consumed by trader)

The hourly WhatsApp status report now includes a MiroFish research summary line.

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
│   ├── problem-solver/     Watchdog — keeps other bots alive
│   ├── problem-solver-ui/  Full dashboard (FastAPI)
│   ├── polymarket-trader/  Trading bot with inline MiroFish predictor
│   ├── mirofish-researcher/ MiroFish deep market research agent
│   ├── status-reporter/    Hourly WhatsApp status
│   ├── scheduler-runner/   Task scheduler
│   └── discovery/          Skill & market discovery
├── config/              Config files (never overwritten on update)
│   ├── status-reporter.env
│   ├── problem-solver-ui.env
│   ├── polymarket-trader.env
│   ├── mirofish-researcher.env
│   ├── mirofish_signals.json  External market signals for MiroFish
│   ├── polymarket_estimates.json  MiroFish probability estimates (auto-written)
│   ├── schedules.json   Scheduled tasks
│   └── ...
├── state/               Persistent bot state (JSON)
│   ├── chatlog.jsonl    Chat/task history
│   ├── improvements.json Skill proposals
│   ├── mirofish-researcher.state.json  Full MiroFish research report
│   └── *.state.json     Per-bot state files
├── logs/                Log files
├── improvements/        Approved improvement files
└── workspace-*/         Per-agent workspaces + skills
```

---

## Troubleshooting

### Terminal shows "openclaw.bash: file not found" on every open

The openclaw installer adds a `source` line to your `~/.bashrc` but does not always
create the target file.  One-time fix:

```bash
mkdir -p ~/.openclaw/completions
touch ~/.openclaw/completions/openclaw.bash
```

Re-open your terminal — the error will be gone.  
The AI Employee installer now creates this stub automatically, so fresh installs are not affected.

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

Bot-specific logs:
```bash
~/.ai-employee/bin/ai-employee logs claude-agent
~/.ai-employee/bin/ai-employee logs ollama-agent
```

---

## 10) Uninstall / Remove everything
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

## Security notes

- The installer generates a local token and stores it in `~/.ai-employee/.env`.
- Don't share `~/.ai-employee/.env` or `~/.ai-employee/config.json`.
- Review scripts before running, especially if you modify install sources.
- Your Anthropic API key is stored in `~/.ai-employee/.env` (chmod 600).
- The Ollama agent processes all data locally — no external API calls are made.
## License

MIT — see [LICENSE](LICENSE)
