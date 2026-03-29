# 🤖 AI Employee

> **Your AI leverage machine for solo founders & small agencies** — one install, one command, and your AI employee starts generating leads, writing sales emails, and automating your ops.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-informational.svg)](#-install--choose-your-platform)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-lightgrey.svg)](#-install--choose-your-platform)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078d4.svg)](#-install--choose-your-platform)
[![Agents: 35](https://img.shields.io/badge/Agents-35-success.svg)](#-new-niche-specialists--ai-growth-agency)
[![Skills: 147](https://img.shields.io/badge/Skills-147-orange.svg)](#skills-library-147-skills)

---

## 📑 Table of Contents

- [Who is this for?](#who-is-this-for)
- [✨ Key Features](#-key-features)
- [⚡ Quickstart](#-quickstart--your-first-business-result-in-15-minutes)
- [🎯 Use Cases](#-use-cases)
- [🗂️ Three Modes](#️-three-modes--start-simple-scale-when-ready)
- [📋 Goal-Based Templates](#-goal-based-templates)
- [🏗️ Architecture Overview](#️-architecture-overview)
- [🖥️ Dashboard](#️-dashboard-primary-control)
- [📱 WhatsApp Commands](#-whatsapp--quick-commands--notifications)
- [🔧 CLI Reference](#-cli-reference)
- [📈 ROI Metrics](#-roi-metrics)
- [🔒 Guardrails](#-guardrails)
- [Requirements](#requirements)
- [🖥️ Install](#️-install--choose-your-platform)
- [🎮 Discord Bot](#-discord-bot--control-panel--live-notifications)
- [🔌 Integrations](#-integrations)
- [🚀 New Niche Specialists](#-new-niche-specialists--ai-growth-agency)
- [Skills Library](#skills-library-147-skills)
- [🧪 Safety Self-Test](#-safety-self-test--verify-everything-works)
- [💻 Complete Terminal Reference](#-complete-terminal-command-reference)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [🤝 Contributing](#-contributing)
- [License](#license)

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🤖 **35 Specialist Agents** | A full team of AI agents — each expert in a specific business domain |
| 🛠️ **147 Reusable Skills** | Modular skill library you can compose into custom agents |
| 🖥️ **Web Dashboard** | Full control panel at `http://127.0.0.1:8787` — no terminal needed |
| 🗂️ **Three Modes** | Start with 3 agents (Starter), grow to 8 (Business), or unleash all 35 (Power) |
| 📋 **Goal Templates** | One-click business templates: 10 leads in 24h, close €1k deal, automate support |
| 🧠 **AI Router** | Automatically routes tasks to the best model (GPT-4o, Claude, or local Ollama) |
| 📊 **ROI Tracking** | Tracks leads generated, deals closed, hours saved, and € value created |
| 🔒 **Guardrails** | Human-in-the-loop approval queue for high-risk actions (bulk email, purchases) |
| 📱 **WhatsApp + Discord** | Get notified and send commands from your phone or Discord server |
| 🆓 **Works Locally** | Fully operational without any paid API — uses Ollama for free local AI |
| 🔄 **Memory & CRM** | Built-in lead CRM with follow-up tracking and per-lead memory |
| ⏱️ **Scheduler** | Schedule recurring tasks (daily lead generation, weekly reports, etc.) |

---

## Who is this for?

**AI Employee is built for solo founders and small agencies** who want leverage — not complexity.

You run a business. You don't have time to manage 35 agents and 147 skills. You just want results:
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

## 🎯 Use Cases

AI Employee is designed for real-world business automation. Here are common scenarios:

### 🏢 Solo Founder / Freelancer
> *"I need leads but can't afford a sales team."*

```bash
ai-employee do "find 10 qualified leads for my web design agency in London"
ai-employee do "write personalised cold emails for each lead"
ai-employee do "schedule follow-up messages for leads that don't reply in 3 days"
```

**Result:** Automated lead generation + outreach pipeline running 24/7 — no SDR needed.

---

### 🛍️ E-commerce Store Owner
> *"I spend hours on content and customer support every day."*

```bash
ai-employee do "deploy template run-ecommerce-on-autopilot"
ai-employee do "create 30-day Instagram content calendar for my supplement brand"
ai-employee do "draft answers for the top 20 FAQs from my customers"
```

**Result:** Content created in minutes, support FAQs handled automatically, store running on autopilot.

---

### 📊 Digital Marketing Agency
> *"I need to deliver reports and campaigns faster for more clients."*

```bash
ai-employee do "analyse competitor SEO for my client in the fitness niche"
ai-employee do "create Meta ad copy with 3 variants for A/B testing"
ai-employee do "generate monthly performance report with KPIs"
```

**Result:** Deliverables produced at 10× speed — handle more clients without more headcount.

---

### 💼 B2B Sales Professional
> *"I need to hit my quota but prospecting takes all my time."*

```bash
ai-employee do "hunt 20 qualified SaaS leads in Germany"
ai-employee do "build a 5-step cold outreach sequence for fintech decision makers"
ai-employee do "help me handle the objection: it's too expensive"
```

**Result:** Fully automated prospecting + personalised outreach + objection-handling scripts on demand.

---

### 📱 Content Creator / Coach
> *"I can't keep up with posting consistently across platforms."*

```bash
ai-employee do "repurpose this blog post into 5 LinkedIn posts and 3 tweet threads"
ai-employee do "write a YouTube video script about my coaching framework for online entrepreneurs"
ai-employee do "create a 30-day LinkedIn growth plan to reach 10k followers"
```

**Result:** One piece of content becomes a full multi-platform campaign in seconds.

---

## 🏗️ Architecture Overview

AI Employee is a multi-layer system where a single user command fans out across specialised agents:

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
│   Dashboard (port 8787)  │  CLI (ai-employee do)  │  WhatsApp  │
│                          │                        │  Discord   │
└──────────────────────────┬─────────────────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Problem     │
                    │  Solver      │  ← Watchdog + task router
                    │  (Orchestr.) │
                    └──────┬───────┘
                           │
             ┌─────────────┼─────────────────┐
             │             │                 │
      ┌──────▼──────┐ ┌────▼─────┐  ┌───────▼──────┐
      │  AI Router  │ │ Scheduler│  │  Guardrails  │
      │ (GPT-4o /   │ │ (cron-   │  │  (approval   │
      │  Claude /   │ │  based)  │  │   queue)     │
      │  Ollama)    │ └──────────┘  └──────────────┘
      └──────┬──────┘
             │
   ┌─────────┼─────────────────────────────────┐
   │         │                                 │
┌──▼──┐  ┌───▼───┐  ┌───────┐  ┌──────────┐  ┌▼──────────────┐
│Lead │  │Content│  │Sales  │  │Analytics │  │ 27+ more      │
│Hunt.│  │Master │  │Closer │  │& Reports │  │ specialist    │
│Elite│  │       │  │Pro    │  │          │  │ agents...     │
└──┬──┘  └───┬───┘  └───┬───┘  └────┬─────┘  └───────┬───────┘
   │         │           │           │                │
   └─────────┴───────────┴───────────┴────────────────┘
                         │
               ┌─────────▼──────────┐
               │  Shared Services   │
               │  Memory / CRM      │
               │  ROI Tracker       │
               │  Feedback Loop     │
               └────────────────────┘
```

**Key components:**

| Component | Role |
|---|---|
| **Problem Solver** | Orchestrator — watches all bots, routes tasks, restarts crashed bots |
| **AI Router** | Picks the best LLM per task type (sales→GPT-4o, analysis→Claude, local→Ollama) |
| **35 Specialist Agents** | Each expert in one domain; task execution mode: Auto (orchestrator decides), Parallel (all at once), or Single (one agent) |
| **Skills Library** | 147 reusable building blocks composed into agents |
| **Memory / CRM** | Per-lead memory and interaction history persisted in JSON |
| **Guardrails** | Human approval queue for high-risk actions before execution |
| **Scheduler** | Cron-based task runner for recurring automation |

---

## 🗂️ Three Modes — Start Simple, Scale When Ready

```bash
ai-employee mode starter    # 3 agents, 5 commands — zero overwhelm
ai-employee mode business   # templates, ROI tracking, scheduling (recommended)
ai-employee mode power      # all 39 agents, 147+ skills, full dashboard
```

| Mode | Agents | What you see | Best for |
|---|---|---|---|
| **Starter** | 3 | 5 commands, no dashboard overload | Getting your first results |
| **Business** | 8 | Templates, ROI, scheduling | Daily business automation |
| **Power** | 39 | Everything — full dashboard, all skills | Advanced users |

Change mode any time: `ai-employee mode business`

---

## 🆕 New Agent Divisions (inspired by [agency-agents](https://github.com/msitarzewski/agency-agents))

Four new specialist divisions have been added, bringing the total to **39 agents**:

### 💻 Engineering Division
| Agent | Commands | What it does |
|---|---|---|
| **Engineering Assistant** | `eng frontend`, `eng backend`, `eng aiml`, `eng review`, `eng devops`, `eng database`, `eng security`, `eng architecture`, `eng refactor`, `eng debug` | Full-stack dev help: React/Vue, FastAPI/Node, AI/ML engineering, code review, Docker/K8s, PostgreSQL, OWASP security, system architecture |

### 🎨 Design Division
| Agent | Commands | What it does |
|---|---|---|
| **UI Designer** | `design system`, `design component`, `design audit`, `design colors`, `design typography`, `design layout`, `design accessibility`, `design darkmode`, `design flows`, `design handoff` | Design systems, WCAG accessibility, component specs, color palettes, dark mode strategy, developer handoff |

### 🧪 Testing Division
| Agent | Commands | What it does |
|---|---|---|
| **QA Tester** | `qa plan`, `qa testcases`, `qa api`, `qa bug`, `qa performance`, `qa security`, `qa accessibility`, `qa coverage`, `qa readiness`, `qa automate` | Test plans, BDD test cases, API testing, load testing, OWASP security tests, production readiness certification |

### 💰 Paid Media Division
| Agent | Commands | What it does |
|---|---|---|
| **Paid Media Specialist** | `ppc build`, `ppc audit`, `ppc budget`, `ppc keywords`, `ppc adcopy`, `ppc audiences`, `ppc tracking`, `ppc report`, `ppc forecast`, `ppc diagnose` | Google Ads/Meta Ads strategy, account architecture, PPC audits, ad copy (RSA), audience targeting, conversion tracking |

### 🤖 Claude Code Integration (`.claude/agents/`)

AI Employee now includes agent prompt files compatible with **[Claude Code](https://docs.anthropic.com/en/docs/claude-code/)**. Copy them to activate in your Claude Code sessions:

```bash
# Copy agents to your Claude Code directory
cp -r .claude/agents/* ~/.claude/agents/

# Then activate in Claude Code:
# "Activate Engineering Assistant and review this code for security issues"
# "Activate UI Designer and create a design system for my SaaS product"
# "Activate QA Tester and write test cases for the checkout flow"
# "Activate PPC Strategist and build a Google Ads campaign structure"
```

**Available Claude Code agents:**
- `engineering-frontend-developer.md` — React/Vue/TypeScript, performance, accessibility
- `engineering-backend-architect.md` — APIs, databases, microservices, cloud
- `engineering-ai-engineer.md` — ML models, LLM integration, MLOps
- `engineering-security-engineer.md` — threat modeling, OWASP, secure code review
- `design-ui-designer.md` — design systems, WCAG, component specs
- `testing-reality-checker.md` — evidence-based QA certification
- `product-manager.md` — PRDs, roadmaps, sprint planning, outcome measurement
- `sales-outbound-strategist.md` — signal-based prospecting, ICP, sequences
- `paid-media-ppc-strategist.md` — Google Ads, Meta Ads, campaign architecture
- `marketing-growth-hacker.md` — viral loops, funnel optimization, experiments

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
| **Hunt 20 Qualified Leads in 24h** | 24 hours | €500–€5,000/week pipeline |
| **Launch Cold Outreach Campaign** | 2 hours | €2,000–€15,000/month |
| **LinkedIn Growth Blitz (30 Days)** | 30 days | €3,000–€20,000 pipeline |
| **Close 5 Deals This Week** | 1 week | €5,000–€50,000 |
| **Launch Paid Ads with 3x ROAS** | 1 day | €5,000–€50,000/month |
| **Launch a Referral Program** | 3 days | 20% new revenue from referrals |
| **Build JV Partnership Pipeline** | 1 week | €2,000–€20,000/partner/mo |
| **Boost Conversion Rate by 50%** | 1 week | €1,000–€30,000/month |

```bash
ai-employee do "deploy template hunt-20-leads-24h"
ai-employee do "deploy template cold-outreach-campaign"
ai-employee do "deploy template get-10-leads-24h"
```

---

## 🖥️ Dashboard (Primary Control)

Open the dashboard at **http://127.0.0.1:8787** after starting.

The dashboard is your primary control center. Use it for full control over tasks, scheduling, ROI tracking, and agent management.

| Tab | What it shows |
|---|---|
| 📊 Dashboard | Bot status overview, quick actions |
| 💬 Chat | Send tasks, view chat history |
| 🚀 Tasks | Build & launch multi-agent tasks |
| 🐝 Swarm | All agents — status, workload (filterable by category) |
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
ai-employee logs <bot>              # Tail logs for a specific bot
ai-employee doctor                  # Health check (✅/❌ per service)
ai-employee selftest                # Safety self-test (see below)
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
| **Linux** | Ubuntu 20.04+ / Debian / Mint / Fedora | `main` branch |
| **macOS** | 12+ (Monterey or newer) | `main` branch |
| **Windows** | Windows 10/11 (PowerShell 5.1+) | `main` branch |
| **Python 3** | 3.10+ | for bots and dashboard |
| **curl** | any | for downloading |
| **OpenSSL** | any | for token generation |
| **Node.js** | 20+ | recommended (for OpenClaw gateway) |
| **Ollama** | any | optional — free local AI, no API key needed |

Quick check:
```bash
ai-employee doctor   # checks everything automatically
```

---

## 🖥️ Install — Choose Your Platform

### 🐧 Linux (Ubuntu / Debian / Mint / Fedora / Arch)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

Or download directly:
```bash
# Clone or download from the 'main' branch
bash install.sh
```

### 🍎 macOS (Monterey 12+ / Ventura / Sonoma)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/mac/quick-install-mac.sh | bash
```

Or download directly from the **`mac` branch** on GitHub:
1. Go to → https://github.com/F-game25/AI-EMPLOYEE/tree/mac
2. Download `install-mac.sh`
3. Open Terminal and run: `bash ~/Downloads/install-mac.sh`

> **Requires Homebrew.** The installer will offer to install it automatically.

### 🪟 Windows 10 / 11

**No WSL or Git Bash required** — fully native PowerShell installer.

**One-click install:**
1. Go to → https://github.com/F-game25/AI-EMPLOYEE/tree/windows
2. Download **`quick-install-windows.bat`**
3. Double-click the file to install

Or run from PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1
```
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

### macOS native installer:
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-mac.sh | bash
```
macOS-specific installer with Homebrew integration, automatic dependency setup, and `.command` desktop launcher.

### Windows native installer (PowerShell):
```powershell
# Run in PowerShell as your regular user:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
Invoke-WebRequest https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/install-windows.ps1 -OutFile install-windows.ps1
.\install-windows.ps1
```
Or use the one-click batch file: download and run `quick-install-windows.bat`.
No WSL or Git Bash required — installs Python, Git, Ollama, and all 35 bots natively.

Everything is installed into **`~/.ai-employee/`** (Linux/macOS) or **`%USERPROFILE%\.ai-employee\`** (Windows).

### Update (re-run installer):
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```
Re-running upgrades runtime files **without overwriting** your existing config or `.env`.

### What the installer asks (advanced mode)

The step-by-step wizard asks:

1. WhatsApp phone number (E.164 format, e.g. `+31612345678`)
2. Local LLM via Ollama? (yes/no + model name)
3. Anthropic / OpenAI API keys (optional)
4. Alpha Insider, Tavily, NewsAPI keys (optional)
5. Telegram / Discord / SMTP (optional)
6. Enable hourly WhatsApp status updates?
7. Dashboard port (default: 8787)
8. Number of workers (1–35, default: 35)

---

## Start / Stop

### 🐧 Linux / 🍎 macOS


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

Stop: `./stop.sh` or Ctrl+C in the terminal.

**Desktop launchers** (created by installer — smart, no terminal needed):

The desktop button is *smart*: it checks whether the bot is already running.
- **Bot running** → opens the dashboard in your browser instantly
- **Bot not running** → starts the bot (which opens the browser automatically)

| Platform | Button | How it works |
|---|---|---|
| **Linux** | `~/Desktop/ai-employee.desktop` or "AI Employee" in app menu | Smart launcher: open UI or start bot |
| **macOS** | `~/Desktop/AI-Employee.command` | Smart launcher: open UI or start bot in Terminal |
| **Windows** | `AI Employee.bat` on Desktop | Smart launcher: open UI or start bot in PowerShell |
| **Linux autostart** | `systemctl --user enable --now ai-employee` | Auto-starts on login |
| **macOS autostart** | `launchctl load -w ~/Library/LaunchAgents/com.ai-employee.plist` | Auto-starts on login |

### 🪟 Windows

Double-click **`Start AI Employee.bat`** on your Desktop.

Or run from PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.ai-employee\start-windows.ps1"
```

Stop: Double-click **`Stop AI Employee.bat`** on your Desktop.

### All platforms — browser URLs

After starting, the browser opens automatically. URLs:
- **Full Dashboard:** http://127.0.0.1:8787 ← main UI
- **Simple Dashboard:** http://localhost:3000
- **Gateway API:** http://localhost:18789

---

## Update

Re-run the installer for your platform to upgrade runtime files without touching your config.

- **Linux:** `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash`
- **macOS:** `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/mac/quick-install-mac.sh | bash`
- **Windows:** Re-run `quick-install-windows.bat` or `install-windows.ps1`

---

## Connect WhatsApp (first time)

After starting, open a **new terminal** (Linux/macOS) or PowerShell (Windows) and run:

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

## 🎮 Discord Bot — Control Panel & Live Notifications

> **Why Discord?** Keep an eye on your AI employee from your phone or PC — without leaving Discord. The bot posts automatic alerts when leads are found or follow-ups are sent, and lets you control the CRM with simple `!commands`.

### There are two Discord features:

| Feature | What it does | What you need |
|---|---|---|
| **Incoming Webhook** | Bot *posts* automatic alerts to a channel | A Discord webhook URL |
| **Discord Bot (!commands)** | You *talk to* the bot with `!lead list` etc. | A Discord Bot Token |

You can use one or both.

---

### 🔔 Part 1 — Automatic Notifications via Webhook (easiest)

When a webhook URL is set the system automatically posts:
- 🎯 **New leads found** (how many, for which niche)
- 📤 **Follow-ups sent** (which leads, attempt number)
- 🤖 **Hourly status report** (all bot statuses)

#### Step 1 — Create a webhook in Discord

1. Open Discord → go to the channel where you want notifications
2. Click the ⚙️ gear icon next to the channel name → **Edit Channel**
3. Click **Integrations** → **Webhooks** → **New Webhook**
4. Give it a name (e.g. `AI Employee`) and click **Copy Webhook URL**

#### Step 2 — Add the URL to your config

Open `~/.ai-employee/.env` in a text editor:

```bash
nano ~/.ai-employee/.env
```

Add (or uncomment) this line:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

Save (`Ctrl+X → Y → Enter`) and restart:

```bash
cd ~/.ai-employee && ./stop.sh && ./start.sh
```

That's it — the next time a lead is found you'll see a message in Discord. ✅

---

### 🤖 Part 2 — Discord Bot with !commands (interactive control panel)

The bot lets you manage leads and trigger follow-ups directly from Discord.

#### Step 1 — Create a Discord application & bot

1. Go to → https://discord.com/developers/applications
2. Click **New Application** → give it a name (e.g. `AI Employee`)
3. In the left menu click **Bot** → click **Add Bot** → confirm
4. Under **Privileged Gateway Intents** turn ON **Message Content Intent**
5. Click **Reset Token** → **Copy** the token (you only see it once!)

#### Step 2 — Invite the bot to your server

1. Still in the Developer Portal → click **OAuth2** → **URL Generator**
2. Under **Scopes** tick `bot`
3. Under **Bot Permissions** tick `Send Messages` and `Read Message History`
4. Copy the generated URL → open it in your browser → select your server → **Authorize**

#### Step 3 — Add the token to your config

```bash
nano ~/.ai-employee/.env
```

Add:

```env
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DISCORD_COMMAND_PREFIX=!
```

#### Step 4 — Start the Discord bot

```bash
cd ~/.ai-employee/bots/discord-bot
python3 discord_bot.py
```

Or start it in the background (it will keep running):

```bash
nohup python3 ~/.ai-employee/bots/discord-bot/discord_bot.py \
  >> ~/.ai-employee/logs/discord-bot.log 2>&1 &
echo "Discord bot started (PID $!)"
```

#### Step 5 — Test it

In Discord, type in the channel where the bot is present:

```
!help
```

You should see the command overview. 🎉

---

### 📋 Discord Bot Commands Reference

| Command | What it does |
|---|---|
| `!help` | Show all available commands |
| `!lead list` | List all leads in the CRM |
| `!lead show <id>` | Show full details of a lead |
| `!lead add <name>\|<niche>\|<phone>` | Add a new lead (pipe-separated) |
| `!lead lost <id>` | Mark a lead as lost |
| `!followup run` | Process all leads due for a follow-up |
| `!followup status` | Show follow-up stats for every lead |
| `!followup lead <id>` | Force a follow-up for one specific lead |
| `!followup reset <id>` | Reset the follow-up counter for a lead |

**Example:**
```
!lead add Jan de Vries|webdesign|+31612345678
!followup run
!lead list
```

---

### 🛠️ Discord Bot Logs

```bash
# View live logs
tail -f ~/.ai-employee/logs/discord-bot.log

# Stop the background bot
kill $(pgrep -f discord_bot.py)
```

---

## 🔌 Integrations

The full dashboard runs at **http://127.0.0.1:8787** and has 9 tabs:

| Integration | Use |
|---|---|
| 📊 **Dashboard** | Live bot status, system info, WhatsApp quick-commands panel |
| 💬 **Chat** | Send tasks (same as WhatsApp), view chat history |
| 🚀 **Tasks** | **Task agent selection** — describe goal → auto-select agents → launch |
| 🐝 **Swarm** | All 20 agents: capabilities, status, workload |
| 📜 **Commands** | Full WhatsApp commands reference — searchable, click to copy |
| 📅 **Scheduler** | Create/edit/delete scheduled tasks |
| 👷 **Workers** | Start/stop/toggle individual bots |
| 💡 **Improvements** | Review and approve/reject skill proposals |
| 🛠️ **Skills** | Browse and search 126+ business skills |

### Tasks tab — Agent Selection & Auto-Assign

1. **Describe your goal** in plain English
2. Click **🤖 Auto-Select Agents** — AI picks the best agents for your task
3. Review/adjust the agent grid (select All, None, or manual picks)
4. Choose execution mode: **Auto** (orchestrator decides), **Parallel** (all at once), **Single** (first agent)
5. Click **🚀 Launch Task**

### Commands tab — WhatsApp Controls

The Commands tab lists every WhatsApp command grouped by category with search:
- Copy any command to clipboard with one click
- Works directly in the Chat tab too — same commands work on WhatsApp and in the UI

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

## 🚀 New Niche Specialists — AI Growth Agency

8 specialist agents focused on B2B growth, lead generation, and revenue — added on top of the existing 27 general agents.

### Agent overview

| Agent | Command prefix | What it does |
|---|---|---|
| **LeadHunterElite** | `leadelite` | Scrapes, qualifies (ICP scoring) and enriches B2B leads; generates outreach scripts |
| **ColdOutreachAssassin** | `outreach` | Multi-channel sequences (email/LinkedIn/WhatsApp), A/B testing, reply tracking |
| **SalesCloserPro** | `closer` | Objection handling, negotiation tactics, deal-closing scripts (SPIN / MEDDIC) |
| **LinkedInGrowthHacker** | `linkedin` | Profile optimisation, viral post creation, connection campaigns |
| **AdCampaignWizard** | `ads` | Ad copy (Meta/Google/LinkedIn), budget allocation, ROAS prediction, performance analysis |
| **ReferralRocket** | `referral` | Referral program design, incentive modelling, launch plan |
| **PartnershipMatchmaker** | `partner` | JV/partner scoring, pitch deck outlines, deal structure templates |
| **ConversionRateOptimizer** | `cro` | Funnel analysis, A/B test design, quick-win CRO recommendations |

### Usage examples

```bash
# Via CLI
ai-employee do "Hunt 15 leads for my SaaS product"
ai-employee do "Build cold outreach sequence for B2B agencies"
ai-employee do "Close deal with objection: it's too expensive"
ai-employee do "Optimize my LinkedIn profile for lead generation"
ai-employee do "Launch Meta ads for my course with 3x ROAS target"
ai-employee do "Design referral program for SaaS with €500 LTV"
ai-employee do "Find JV partners in the marketing niche"
ai-employee do "Analyze conversion funnel and suggest A/B tests"

# Via direct commands in Chat / WhatsApp
leadelite hunt Get 20 qualified SaaS leads in Germany
outreach sequence saas-founders email
closer objection it's too expensive
linkedin content thought leadership post about AI tools
ads roas my online course 30
referral design my subscription product
partner find digital marketing agency space
cro audit landing page 12% conversion rate
```

### Auto-routing

The problem-solver automatically routes tasks to the right specialist agent:

| Keywords in your task | Routed to |
|---|---|
| "leads hunt", "b2b leads", "find leads", "hunt leads" | LeadHunterElite |
| "cold outreach", "cold sequence", "outreach sequence" | ColdOutreachAssassin |
| "close deal", "objection", "negotiate", "closing" | SalesCloserPro |
| "linkedin growth", "linkedin content", "linkedin profile" | LinkedInGrowthHacker |
| "paid ads", "meta ads", "google ads", "roas", "ppc" | AdCampaignWizard |
| "referral program", "refer a friend", "k-factor" | ReferralRocket |
| "partnership", "joint venture", "jv partner" | PartnershipMatchmaker |
| "conversion rate", "cro", "funnel optimization", "ab test" | ConversionRateOptimizer |

### New skills added (147 total)

21 new reusable skills: `lead_scraping`, `qualification_scoring`, `crm_enrichment`, `outreach_script_generator`, `sequence_builder`, `ab_testing`, `reply_tracker`, `objection_handler`, `negotiation_tactics`, `close_deal`, `linkedin_optimizer`, `viral_content_generator`, `ad_copy_generator`, `budget_allocator`, `performance_analyzer`, `referral_program_design`, `incentive_calculator`, `partner_scoring`, `pitch_deck_generator`, `funnel_analyzer`, `ab_test_design`.

---

## Skills Library (147 Skills)

AI Employee includes a library of **147 reusable skills** across 13 categories. Skills are the building blocks for creating custom specialised agents.

### Categories & skill counts

| Category | Skills |
|---|---|
| Content & Writing | 15 |
| Research & Analysis | 12 |
| Trading & Finance | 12 |
| Social Media | 10 |
| Lead Generation & Sales | 19 |
| Development & Technical | 10 |
| E-commerce & Product | 10 |
| Data Analysis | 8 |
| Customer Support | 8 |
| Marketing & SEO | 14 |
| Automation & Productivity | 8 |
| Growth & Marketing | 11 |
| **Total** | **147** |

### Managing skills via the Dashboard

Open the **🛠️ Skills** tab (http://127.0.0.1:8787):
- **Browse** all 147 skills with search and category filters
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

## 🧪 Safety Self-Test — Verify Everything Works

Before going live, run the safety self-test. It checks every component and shows a clear ✅ or ❌ for each:

```bash
python3 ~/.ai-employee/bots/bot_selftest.py
```

Or (after install):

```bash
ai-employee selftest
```

**What it checks:**

| Category | Checks |
|---|---|
| Environment | Python version, `.env` file, `JWT_SECRET_KEY`, state directory, CRM file |
| Discord | Webhook URL reachable, bot token format, `discord.py` installed, bot last state |
| Integrations | Twilio / WhatsApp credentials |
| Bot modules | `ai_router`, `follow_up_agent` importable |
| Running services | OpenClaw gateway, Problem Solver UI |

**Example output:**

```
====================================================
  🧪 AI Employee — Safety & Health Self-Test
====================================================
  AI_HOME : /home/you/.ai-employee
  Time    : 2026-03-27T20:00:00Z

── Environment ──────────────────────────────────────
  ✅ Python version — 3.11.2
  ✅ .env file — /home/you/.ai-employee/.env
  ✅ JWT_SECRET_KEY — set ✓
  ✅ State directory — /home/you/.ai-employee/state
  ✅ CRM file — 24 leads in CRM

── Discord ──────────────────────────────────────────
  ✅ discord_notify module — importable ✓
  ✅ Discord webhook URL — reachable ✓
  ✅ Discord bot token — format OK ✓
  ✅ discord.py library — v2.3.2
  ✅ Discord bot state — running as MyBot#1234

── Integrations ─────────────────────────────────────
  ✅ Twilio / WhatsApp config — credentials set ✓

── Bot Modules ──────────────────────────────────────
  ✅ ai_router module — importable ✓
  ✅ follow_up_agent module — importable ✓

── Running Services ─────────────────────────────────
  ✅ OpenClaw gateway — reachable at http://localhost:18789
  ✅ Problem Solver UI — reachable at http://127.0.0.1:8787

====================================================
  Result: 14/14 checks passed
  ✅ All required checks passed — bot is safe to run!
====================================================
```

**Send a real Discord test ping** (proves the webhook actually works):

```bash
python3 ~/.ai-employee/bots/bot_selftest.py --live
```

---

## 💻 Complete Terminal Command Reference

Everything you can do from your terminal, in one place.

### Install & Update

```bash
# Install (Linux / macOS — zero config)
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config

# Install (Linux / macOS — choose your settings)
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash

# Install (macOS — native installer with Homebrew)
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-mac.sh | bash

# Update (re-run installer — does NOT overwrite .env or config)
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

### Start / Stop

```bash
# Start everything (opens dashboard in browser automatically)
cd ~/.ai-employee && ./start.sh

# Stop everything
cd ~/.ai-employee && ./stop.sh

# Or use the CLI from any directory
ai-employee start
ai-employee stop
ai-employee status          # Shows which bots are running
```

### Send Tasks

```bash
ai-employee do "find 10 leads for my web design agency in Amsterdam"
ai-employee do "write a cold sales email for my SaaS product"
ai-employee do "analyse my competitor and find 3 gaps I can exploit"
ai-employee do "create a 30-day content calendar for LinkedIn"
ai-employee do "deploy template get-10-leads-24h"
```

### Modes

```bash
ai-employee mode                  # Show current mode
ai-employee mode starter          # 3 agents — no overwhelm
ai-employee mode business         # 8 agents — recommended
ai-employee mode power            # All 20 agents, full dashboard
```

### Logs & Debugging

```bash
ai-employee logs <bot>                     # Tail logs for a bot
ai-employee logs discord-bot               # Discord bot logs
ai-employee logs follow-up-agent           # Follow-up agent logs
ai-employee logs lead-generator            # Lead generator logs
ai-employee logs status-reporter           # Status reporter logs
ai-employee logs problem-solver-ui         # Dashboard logs
ai-employee doctor                         # Health check
ai-employee selftest                       # Safety self-test (✅/❌)
python3 ~/.ai-employee/bots/bot_selftest.py         # Same — direct
python3 ~/.ai-employee/bots/bot_selftest.py --live  # + real Discord ping
```

### ROI & Metrics

```bash
ai-employee do "metrics"                        # Show ROI summary
ai-employee do "metrics record lead_generated"
ai-employee do "metrics record deal_closed:5000"
```

### CRM & Leads (via chatlog / dashboard chat)

```
leads webdesign Amsterdam          # Find 10 leads, add to CRM
leads status                       # CRM stats (total/contacted/won/…)
leads pipeline                     # Recent leads with status
leads followup                     # Follow-up leads silent for 3+ days
leads export                       # Dump CRM as CSV text
outreach <lead_id> email           # Send personalised email to a lead
outreach <lead_id> whatsapp        # Send personalised WhatsApp to a lead
```

### Follow-Up Agent (via chatlog / dashboard chat)

```
followup run                       # Process all leads due for a follow-up
followup lead <lead_id>            # Force a follow-up for one lead
followup status                    # Show follow-up stats
followup reset <lead_id>           # Reset follow-up counter for a lead
```

### Discord Bot Commands (in Discord)

```
!help                              # Show all commands
!lead list                         # List all leads
!lead show <id>                    # Show details for one lead
!lead add Name|Niche|+31612345678  # Add a new lead
!lead lost <id>                    # Mark a lead as lost
!followup run                      # Trigger follow-ups now
!followup status                   # Follow-up stats
!followup lead <id>                # Follow-up for one lead
!followup reset <id>               # Reset follow-up counter
```

### Discord Bot (terminal)

```bash
# Start the Discord bot
python3 ~/.ai-employee/bots/discord-bot/discord_bot.py

# Start in background (stays running after you close terminal)
nohup python3 ~/.ai-employee/bots/discord-bot/discord_bot.py \
  >> ~/.ai-employee/logs/discord-bot.log 2>&1 &
echo "Discord bot PID: $!"

# View Discord bot logs
tail -f ~/.ai-employee/logs/discord-bot.log

# Stop the Discord bot
kill $(pgrep -f discord_bot.py)
```

### WhatsApp

```bash
openclaw channels login            # Link WhatsApp (scan QR code once)
```

### Individual Bots

```bash
ai-employee start <bot>            # Start one bot
ai-employee stop <bot>             # Stop one bot
ai-employee logs <bot>             # Tail logs for one bot
ai-employee start --all            # Start all enabled bots
ai-employee stop --all             # Stop all bots

# Direct bot start (fallback if CLI unavailable)
python3 ~/.ai-employee/bots/status-reporter/status_reporter.py
python3 ~/.ai-employee/bots/follow-up-agent/follow_up_agent.py
python3 ~/.ai-employee/bots/lead-generator/lead_generator.py
python3 ~/.ai-employee/bots/discord-bot/discord_bot.py
```

### Config & Environment

```bash
# Edit your config
nano ~/.ai-employee/.env

# Generate a new JWT secret (security)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Check what bots are configured
cat ~/.ai-employee/config.json | python3 -m json.tool
```

### Guardrails (Approval Queue)

```bash
ai-employee do "guardrails"        # View pending approvals
ai-employee do "approve <id>"      # Approve a high-risk action
ai-employee do "reject <id>"       # Reject a high-risk action
```

### MiroFish (Trading / Prediction)

```bash
ai-employee start mirofish-researcher
ai-employee stop  mirofish-researcher
ai-employee logs  mirofish-researcher
```

### Onboarding

```bash
ai-employee onboard                # First 15 Minutes Value Flow (first time)
ai-employee ui                     # Open dashboard in browser
```

### Uninstall

```bash
cd ~/.ai-employee && ./stop.sh || true
rm -rf ~/.ai-employee
rm -f ~/.openclaw/openclaw.json
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
## Keeping Your Local Copy Up to Date

### One-time sync (manual):
```bash
bash scripts/sync.sh
```

### Auto-sync every 30 minutes (runs in terminal):
```bash
bash scripts/sync-watch.sh
```

### Auto-sync via cron (runs in background, survives terminal close):
```bash
bash scripts/setup-cron.sh
```

### View sync history:
```bash
cat ~/.ai-employee/logs/sync.log
```

### Stop auto-sync:
```bash
crontab -e   # delete the sync line
```

---

## 🤝 Contributing

Contributions are welcome! Whether you're fixing a bug, adding a new agent skill, or improving documentation — every contribution helps.

### How to contribute

1. **Fork** the repository and create your branch from `main`
2. **Make your changes** — follow the existing code style and patterns
3. **Test your changes** locally with `ai-employee selftest`
4. **Open a Pull Request** with a clear description of what you changed and why

### Ideas for contributions

- 🤖 **New agent skills** — add skills to the 147-skill library (see `runtime/bots/skills/`)
- 🐛 **Bug fixes** — check the [open issues](https://github.com/F-game25/AI-EMPLOYEE/issues)
- 📖 **Documentation** — improve guides, add examples, fix typos
- 🌍 **Translations** — translate the README or UI to other languages
- 🔌 **Integrations** — add new platform integrations (Slack, Notion, HubSpot, etc.)

### Reporting bugs

Open an [issue](https://github.com/F-game25/AI-EMPLOYEE/issues) and include:
- Your operating system and Python version (`python3 --version`)
- The exact command or action that triggered the bug
- The error output from `ai-employee logs <bot>` or `ai-employee doctor`

---

## License

MIT — see [LICENSE](LICENSE)
