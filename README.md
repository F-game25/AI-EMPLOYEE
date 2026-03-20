# AI Employee

Autonomous multi-agent business assistant with a local gateway + Web UI.

- Install: 1 command
- Run: 1 command
- Control: via WhatsApp + local Web UI
- Files are installed into: `~/.ai-employee`

---

## Requirements (Linux / macOS / WSL)

You need:

- **curl**
- **Docker** (installed + running)
- **Node.js 22+**
- **bash**
- **Python 3** (for the Web UI static server)
- (recommended) **OpenSSL** (for token generation)

Check quickly:

```bash
curl --version
docker --version
docker info
node -v
python3 --version
```

---

## 1) Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

What this does:
- downloads `install.sh` from this repo
- installs/configures everything into `~/.ai-employee`
- prepares the Web UI files in `~/.ai-employee/ui`
- creates helper scripts: `~/.ai-employee/start.sh` and `~/.ai-employee/stop.sh`

During installation you will be asked for:
- Your WhatsApp number
- Anthropic API key (optional – required for **Claude Agent**)
- Claude model name (default: `claude-opus-4-5`)
- Ollama model name (default: `llama3`) and host (default: `http://localhost:11434`)

---

## 2) Start / Stop

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

### Stop
In another terminal:
```bash
cd ~/.ai-employee
./stop.sh
```

---

## 3) Connect WhatsApp (first time)

Open a **new terminal** and run:

```bash
openclaw channels login
```

Then scan the QR code in WhatsApp:
**WhatsApp → Linked Devices → Link a device**

---

## 4) Use (basic commands)

Send a WhatsApp message to yourself:

```text
Hello!
```

Switch agent:

```text
switch to lead-hunter
switch to claude-agent
switch to ollama-agent
```

Example task:

```text
find 20 SaaS CTOs in Netherlands
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

After starting, open:

- **Web UI:** http://localhost:3000
- **Gateway API:** http://localhost:18789

### What the Web UI is
The Web UI is a simple local dashboard:
- shows which agents exist
- shows "quick actions" and usage hints
- links to Claude Agent UI and Ollama Agent UI
- runs locally on your machine (served from `~/.ai-employee/ui`)

### Restart only the Web UI
If you want to run just the Web UI server:

```bash
cd ~/.ai-employee/ui
./serve.sh
```

---

## 8) Where everything is stored

Main folder:

- `~/.ai-employee/` (all AI Employee files)

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

### Update AI Employee to the latest version
Recommended approach (safe):

```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash
```

This will re-generate files in `~/.ai-employee`.

### View logs
Gateway logs (follow):

```bash
openclaw logs --follow
```

Bot-specific logs:
```bash
~/.ai-employee/bin/ai-employee logs claude-agent
~/.ai-employee/bin/ai-employee logs ollama-agent
```

---

## 10) Uninstall / Remove everything

### Stop services first
```bash
cd ~/.ai-employee
./stop.sh || true
```

### Remove the installed files
```bash
rm -rf ~/.ai-employee
```

### (Optional) remove OpenClaw config link
```bash
rm -f ~/.openclaw/openclaw.json
```

> Note: uninstalling does not remove Docker itself or Node.js.

---

## Security notes

- The installer generates a local token and stores it in `~/.ai-employee/.env`.
- Don't share `~/.ai-employee/.env` or `~/.ai-employee/config.json`.
- Review scripts before running, especially if you modify install sources.
- Your Anthropic API key is stored in `~/.ai-employee/.env` (chmod 600).
- The Ollama agent processes all data locally — no external API calls are made.
