# 🚀 AI Employee — Easy Install Guide

Get your AI Employee running in under 5 minutes with copy-paste terminal commands.

---

## ⚡ TL;DR (fastest path — no questions asked)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

This installs everything with safe defaults: **local Ollama AI (free & private), Starter mode, 5 agents — no API keys required.**

---

## Prerequisites — install these first if missing

| Tool | Why | Install command |
|---|---|---|
| **curl** | downloads the installer | `sudo apt install curl` |
| **Python 3.10+** | runs all bots | `sudo apt install python3` |
| **OpenSSL** | generates security tokens | `sudo apt install openssl` |
| **Node.js 20+** | recommended for gateway | see https://nodejs.org |
| **Ollama** | free local AI (no API key) | see https://ollama.com/download |

Install Ollama on Linux with one command:

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2
```

> **Note:** Do **not** run as root (`sudo`). Run as your normal user.

---

## 🐧 Linux (Ubuntu / Debian / Mint / Fedora)

### Option A — Zero-config (recommended first-time)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

### Option B — Advanced (choose your AI model, API keys, ports)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

### Option C — Clone and run locally

```bash
git clone https://github.com/F-game25/AI-EMPLOYEE.git
cd AI-EMPLOYEE
bash install.sh
```

---

## 🍎 macOS (Monterey 12+, Ventura, Sonoma)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-mac.sh | bash
```

> Homebrew is required. The installer will offer to install it automatically if missing.

---

## 🪟 Windows 10 / 11

### Option A — One-click batch file (easiest)

1. Download [`quick-install-windows.bat`](https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-windows.bat)
2. Double-click the file — no admin rights needed

### Option B — PowerShell

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
Invoke-WebRequest https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/install-windows.ps1 -OutFile install-windows.ps1
.\install-windows.ps1
```

---

## What the installer does

1. Checks requirements (Python, curl, OpenSSL)
2. Installs **Ollama** (free local AI — no API key needed)
3. Creates `~/.ai-employee/` with all bot files and configs
4. Generates a secure `JWT_SECRET_KEY` automatically
5. Installs Python dependencies for all bots
6. Creates a `ai-employee` command available everywhere
7. Adds a desktop launcher (Linux/macOS)

Everything lives in **`~/.ai-employee/`** — uninstall by deleting that folder.

---

## After Install — Start Your AI Employee

```bash
# Start everything (opens dashboard in browser automatically)
cd ~/.ai-employee && ./start.sh

# Or from anywhere after install:
ai-employee start
```

Dashboard opens at: **http://127.0.0.1:8787**

---

## Your First Tasks (run after start)

```bash
# Run the onboarding wizard (generates first results in ~2 minutes)
ai-employee onboard

# Or jump straight to a task:
ai-employee do "find 10 leads for my business"
ai-employee do "write a cold email for my SaaS"
ai-employee do "analyse my top competitor"
```

---

## Configuration — API Keys (optional, for cloud AI)

Edit `~/.ai-employee/.env` to add API keys:

```bash
nano ~/.ai-employee/.env
```

Key settings:

```bash
# Use OpenAI GPT-4o instead of local Ollama (better quality, costs money)
OPENAI_API_KEY=sk-...

# Use Anthropic Claude (best for analysis)
ANTHROPIC_API_KEY=sk-ant-...

# WhatsApp notifications via Twilio (optional)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

After editing, restart:

```bash
cd ~/.ai-employee && ./stop.sh && ./start.sh
```

---

## Stop / Restart / Update

```bash
# Stop all services
cd ~/.ai-employee && ./stop.sh

# Check health
ai-employee doctor

# Update to latest version (re-runs installer, keeps your config)
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

---

## Switch Modes

```bash
ai-employee mode starter    # 3 agents — great for getting started
ai-employee mode business   # 8 agents — templates, ROI tracking
ai-employee mode power      # 20 agents — everything unlocked
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: ai-employee` | Run `source ~/.bashrc` or open a new terminal |
| Dashboard won't open | Check `~/.ai-employee/logs/` for errors |
| `JWT_SECRET_KEY` error | Run: `export JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")` |
| Port already in use | Change port in `~/.ai-employee/.env`: `PROBLEM_SOLVER_UI_PORT=8788` |
| Ollama not found | Install Ollama: https://ollama.com/download then run `ollama pull llama3.2` |
| Python < 3.10 | Install: `sudo apt install python3.10` or `sudo apt install python3.11` |

---

## Uninstall

```bash
ai-employee stop 2>/dev/null || true
rm -rf ~/.ai-employee
# Remove the shell alias/PATH entry (edit ~/.bashrc or ~/.zshrc and remove the ai-employee line)
```

---

## Need Help?

- Check logs: `~/.ai-employee/logs/`
- Run diagnostics: `ai-employee doctor`
- Open an issue: https://github.com/F-game25/AI-EMPLOYEE/issues
