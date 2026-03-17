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
```

Example task:

```text
find 20 SaaS CTOs in Netherlands
```

---

## 5) Web UI (Dashboard)

After starting, open:

- **Web UI:** http://localhost:3000  
- **Gateway API:** http://localhost:18789

### What the Web UI is
The Web UI is a simple local dashboard:
- shows which agents exist
- shows “quick actions” and usage hints
- runs locally on your machine (served from `~/.ai-employee/ui`)

### Restart only the Web UI
If you want to run just the Web UI server:

```bash
cd ~/.ai-employee/ui
./serve.sh
```

---

## 6) Where everything is stored

Main folder:

- `~/.ai-employee/` (all AI Employee files)

Important files:
- `~/.ai-employee/config.json` (OpenClaw config)
- `~/.ai-employee/.env` (token + optional API keys)
- `~/.ai-employee/logs/` (logs)
- `~/.ai-employee/workspace-*/` (agent workspaces)
- `~/.openclaw/openclaw.json` (symlink to config, if supported)

---

## 7) Maintenance / Updates

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

---

## 8) Uninstall / Remove everything

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
- Don’t share `~/.ai-employee/.env` or `~/.ai-employee/config.json`.
- Review scripts before running, especially if you modify install sources.

