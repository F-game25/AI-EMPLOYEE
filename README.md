# 🤖 AI Employee

> **Your AI leverage machine for solo founders & small agencies** — one install, one command, and your AI employee starts generating leads, writing sales emails, and automating your ops.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Who is this for?

**AI Employee is built for solo founders and small agencies** who want leverage — not complexity.

You run a business. You don't have time to manage 20 agents and 126 skills. You just want results:
- 10 qualified leads today
- A sales email in your inbox
- Your customer support running on autopilot

That's exactly what AI Employee does. One AI employee that handles your tasks — powered by specialist AI agents working behind the scenes.

---

## ⚡ Quickstart — Your First Business Result in 15 Minutes

### Option A — Zero-config (recommended for new users, no questions asked):

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

Installs with safe defaults: local Ollama model, Starter mode, 5 agents. No API keys required.

### Option B — Advanced install (choose your model, mode, integrations):

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

### After install — generate your first results:

```bash
cd ~/.ai-employee && ./start.sh   # Start your AI employee (opens dashboard)
ai-employee onboard               # Run the First 15 Minutes Value Flow
```

The onboard command auto-runs 3 tasks and shows you the estimated value generated:

```
✅ Generated 10 leads for your business
✅ Wrote 1 sales email
✅ Analysed 1 competitor

✅ Estimated value generated: €1,000 potential
⏱️  Estimated time saved: 4 hours
```

---

## 🎯 Send Any Task

```bash
ai-employee do "find 10 leads for my web design agency"
ai-employee do "write a cold sales email for my SaaS product"
ai-employee do "analyse my competitor and find 3 gaps I can exploit"
ai-employee do "create a 30-day content calendar for LinkedIn"
```

Your AI employee handles it — routing to the right specialist agents internally. From the outside, it's just one AI you talk to.

---

## 🗂️ Three Modes — Start Simple, Scale When Ready

```bash
ai-employee mode starter    # 3 agents, 5 commands — zero overwhelm
ai-employee mode business   # templates, ROI tracking, scheduling (recommended)
ai-employee mode power      # all 20 agents, 126 skills, full dashboard
```

| Mode | Agents | What you see | Best for |
|---|---|---|---|
| **Starter** | 3 | 5 commands, no dashboard overload | Getting your first results |
| **Business** | 8 | Templates, ROI, scheduling | Daily business automation |
| **Power** | 20 | Everything — full dashboard, all skills | Advanced users |

Change mode any time: `ai-employee mode business`

---

## 📋 Goal-Based Templates

Deploy a pre-configured AI team in one click from the **📋 Templates** tab:

| Goal | Time to first result | Est. value |
|---|---|---|
| **Get 10 Qualified Leads in 24h** | 24 hours | €200–€1,000/week |
| **Close Your First €1k Deal** | 1 week | €1,000–€8,000/month |
| **Automate Customer Support in 1 Hour** | 1 hour | €2,500–€5,000/month saved |
| **Hire Your Best Candidate Faster** | 2 weeks | €4,000–€10,000/hire saved |
| **10x Your Content Output This Week** | 1 week | €2,000–€6,000/month |
| **Run Your E-commerce Store on Autopilot** | 3 days | €5,000–€15,000/month saved |

```bash
ai-employee do "deploy template get-10-leads-24h"
```

---

## 🖥️ Dashboard (Primary Control)

Open the dashboard at **http://localhost:8787** after starting.

The dashboard is your primary control center. Use it for full control over tasks, scheduling, ROI tracking, and agent management.

| Tab | What it shows |
|---|---|
| 📊 Dashboard | Bot status overview, quick actions |
| 💬 Chat | Send tasks, view chat history |
| 🚀 Tasks | Build & launch multi-agent tasks |
| 🐝 Swarm | All agents — status, workload |
| 📅 Scheduler | Create & manage scheduled tasks |
| 👷 Workers | Start/stop individual bots |
| 📈 ROI | Tasks done, leads, hours saved, €€ saved |
| 📋 Templates | Deploy goal-based templates in one click |
| 🔒 Guardrails | Approval queue, safety logs |
| 🧠 Memory | Client CRM, interaction history |
| 🔌 Integrations | Gmail, Sheets, Telegram, Slack, OpenAI |

---

## 📱 WhatsApp — Quick Commands & Notifications

> **WhatsApp is for quick checks and notifications — not your primary control system.**
> Use the dashboard for full control.

After starting, link WhatsApp optionally:

```bash
openclaw channels login   # Scan QR code once
```

WhatsApp lets you:

| Command | What it does |
|---|---|
| `status` | Quick status check |
| `workers` | List running bots |
| `help` | Show available commands |

Get notified when tasks complete, leads are generated, or deals close — without leaving your phone.

For everything else: **use the dashboard**.

---

## 🔧 CLI Reference

```bash
ai-employee do <task>               # Send any task to your AI employee
ai-employee start                   # Start all services
ai-employee stop                    # Stop all services
ai-employee status                  # Show running bots
ai-employee logs <bot>              # Tail logs
ai-employee doctor                  # Health check (✅/❌ per service)
ai-employee onboard                 # First 15 Minutes Value Flow
ai-employee mode [starter|business|power]  # Show or set mode
ai-employee ui                      # Open dashboard in browser
```

### Health Check

```bash
ai-employee doctor
```

Outputs:

```
── Dependencies ──────────────────────────────
  ✅ python3    : Python 3.11.2
  ✅ curl       : curl 7.88.1
  ✅ openclaw   : 2.1.0
  ⚠️  ollama    : not installed (optional)

── Services ──────────────────────────────────
  ✅ Gateway        : running (port 18789)
  ✅ Dashboard      : running (port 3000) → http://localhost:3000
  ✅ Problem Solver : running (port 8787) → http://localhost:8787
  ⚠️  Ollama API    : not reachable (start with: ollama serve)

── API Keys ──────────────────────────────────
  ⚠️  Anthropic API key : not set (optional)
  ✅ JWT secret       : set

── Configuration ─────────────────────────────
  ✅ Mode           : business
```

---

## 📈 ROI Metrics

Track the business value your AI team creates:

```bash
ai-employee do "metrics"             # Show ROI summary
ai-employee do "metrics record lead_generated"
ai-employee do "metrics record deal_closed:5000"
```

**Tracked automatically:**
- ✅ Tasks completed
- 🎯 Leads generated
- 📧 Emails sent
- 📝 Content created
- 💰 Deals closed (with revenue)
- ⏱️ Hours saved (auto-calculated per event type)
- 💶 Cost saved (hours × €75/h by default — customise with `AI_EMPLOYEE_HOURLY_RATE`)

---

## 🔒 Guardrails

High-risk actions require your approval before execution:

```bash
ai-employee do "guardrails"          # View pending approvals
ai-employee do "approve <action_id>"
ai-employee do "reject <action_id>"
```

**Default approval required for:**
- Sending bulk emails
- Posting to social media
- Making purchases or placing orders
- Deleting or modifying data

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| **Linux / macOS / WSL** | — | Ubuntu/Debian/Mint/macOS/WSL2 |
| **curl** | any | for downloading |
| **Python 3** | 3.10+ | for the dashboard UI |
| **OpenSSL** | any | for token generation |
| **Node.js** | 20+ | recommended (for OpenClaw gateway) |
| **Ollama** | any | optional — free local AI, no API key needed |

Quick check:
```bash
ai-employee doctor   # checks everything automatically
```

---

## Install Options

### Zero-config (fastest, no questions):
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```
- No questions asked
- Uses Ollama local model (free, private)
- Starter mode (3 agents)
- No API keys required
- Change settings later in `~/.ai-employee/.env`

### Advanced install (choose everything):
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```
- Choose your LLM (Ollama local or cloud)
- Configure API keys
- Select mode (starter/business/power)
- Set ports and number of agents

Everything is installed into **`~/.ai-employee/`**.

### Update (re-run installer):
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```
Re-running upgrades runtime files **without overwriting** your existing config or `.env`.

---

## Start / Stop

```bash
# Start (opens dashboard automatically)
cd ~/.ai-employee && ./start.sh

# Stop
cd ~/.ai-employee && ./stop.sh

# Or use the CLI from anywhere:
ai-employee start
ai-employee stop
ai-employee status
```

**Desktop launchers** are created automatically:
- Linux: double-click `~/Desktop/ai-employee.desktop` or search *"AI Employee"* in app menu
- macOS: double-click `~/Desktop/Start AI Employee.command`
- Autostart: `systemctl --user enable --now ai-employee`

---

## The 20 Agents (Power Mode)

Under the hood, AI Employee routes your tasks to specialist agents. In **Starter** and **Business** modes, these are hidden — you just talk to one AI. In **Power** mode, you can address agents directly.

### Core Business Team
| Agent | What it does |
|---|---|
| **task-orchestrator** | Decomposes tasks, assigns agents, runs parallel workflows |
| **company-builder** | Business plans, simulations, GTM, org design |
| **hr-manager** | Hiring pipeline, onboarding, org charts |
| **finance-wizard** | P&L models, fundraising prep, unit economics |
| **brand-strategist** | Brand naming, identity, positioning, messaging |
| **growth-hacker** | Viral loops, A/B tests, retention, referrals |
| **project-manager** | Sprints, roadmaps, risk registers |

### Specialist Bots
| Agent | What it does |
|---|---|
| **lead-hunter** | B2B lead generation + cold outreach |
| **content-master** | SEO blog posts + long-form content |
| **social-guru** | Viral social media + captions + hashtags |
| **intel-agent** | Competitor monitoring + market research |
| **email-ninja** | Cold email sequences + deliverability |
| **support-bot** | Customer support + FAQ + ticket routing |
| **data-analyst** | Market trends + reports + KPI tracking |
| **creative-studio** | Ad copy + design briefs + campaign concepts |
| **web-sales** | Website audits + UX + sales pitches |

---

## 🔌 Integrations

Configure in the **🔌 Integrations** tab:

| Integration | Use |
|---|---|
| **Gmail / Google Workspace** | Send/receive email |
| **Google Sheets** | Read/write CRM data |
| **Telegram Bot** | Receive commands, send alerts |
| **Slack** | Post to channels |
| **OpenAI / Anthropic** | Cloud AI providers |
| **Outbound Webhook** | Forward events to Zapier, Make, n8n |

---

## Where Everything Is Stored

```
~/.ai-employee/
  .env                  # API keys, mode, config
  config.json           # OpenClaw gateway config
  start.sh / stop.sh    # Start/stop scripts
  logs/                 # Per-bot log files
  state/                # Bot state, metrics, memory
  config/               # Per-bot .env config files
  workspace-*/          # Agent workspaces and skills
```

---

## Security

See [SECURITY.md](SECURITY.md) for full details. Key points:

- All services bind to `127.0.0.1` by default (not exposed to network)
- JWT authentication on the dashboard API
- Guardrails require human approval for high-risk actions
- API keys stored in `~/.ai-employee/.env` (chmod 600)

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
