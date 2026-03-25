# AI Employee — Usage Examples

This guide shows practical examples for running and interacting with AI Employee,
including the security features integrated from openclaw-2.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/F-game25/AI-EMPLOYEE.git
cd AI-EMPLOYEE

# 2. Quick install (recommended)
bash quick-install.sh

# — OR — manual install
bash install.sh
```

---

## Starting AI Employee

```bash
# Standard start (starts OpenClaw gateway + all bots + dashboard)
cd ~/.ai-employee && bash start.sh

# The dashboard opens automatically at:
#   http://127.0.0.1:8787   (Problem Solver UI / main dashboard)
#   http://localhost:3000    (static info dashboard)
```

---

## Security Setup (openclaw-2)

### 1. Generate a secure JWT secret

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Set it as an environment variable

```bash
export JWT_SECRET_KEY="your-generated-64-char-hex-secret"

# Or add to ~/.ai-employee/.env so it persists across restarts:
echo 'JWT_SECRET_KEY=your-generated-64-char-hex-secret' >> ~/.ai-employee/.env
```

### 3. (Optional) Create a local security override

```bash
cp runtime/config/security.yml security.local.yml
# Edit security.local.yml — it is gitignored and will never be committed
```

---

## Dashboard API Examples

The Problem Solver UI runs at `http://127.0.0.1:8787`.

### Health check

```bash
curl http://127.0.0.1:8787/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "secure_mode": true,
  "privacy_mode": true
}
```

### Security status

```bash
curl http://127.0.0.1:8787/security/status
```

Expected response:
```json
{
  "secure_mode": true,
  "encryption_enabled": true,
  "rate_limiting_enabled": true,
  "external_calls_blocked": false,
  "telemetry_disabled": true,
  "warnings": []
}
```

### Register a dashboard user

```bash
curl -X POST http://127.0.0.1:8787/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "SecureP@ss123!"}'
```

Expected response:
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

### Bot status

```bash
curl http://127.0.0.1:8787/api/status
```

### Start / stop bots

```bash
# Start all bots
curl -X POST http://127.0.0.1:8787/api/bots/start-all

# Start a specific bot
curl -X POST http://127.0.0.1:8787/api/bots/start \
  -H "Content-Type: application/json" \
  -d '{"bot": "lead-generator"}'

# Stop a specific bot
curl -X POST http://127.0.0.1:8787/api/bots/stop \
  -H "Content-Type: application/json" \
  -d '{"bot": "lead-generator"}'
```

---

## WhatsApp / Chat Commands

Once the gateway is connected (`openclaw channels login`):

```
# ROI metrics
metrics
metrics record lead_generated
metrics record deal_closed:5000

# Memory / CRM
memory
clients
client add John Smith
client add Jane Acme Corp

# Templates
templates
template deploy sales-agent

# Guardrails
guardrails
approve <action_id>
reject <action_id>

# Task orchestration
task Build a marketing plan for a SaaS product
```

---

## Monitoring Logs

```bash
# Application log
tail -f ~/.ai-employee/logs/gateway.log

# Security audit log (openclaw-2)
tail -f ~/.ai-employee/logs/audit.log

# Filter for failed authentication attempts
grep "registration_failed\|auth_failed" ~/.ai-employee/logs/audit.log

# Dashboard/UI log
tail -f ~/.ai-employee/logs/problem-solver-ui.log
```

---

## Python Client Example

```python
import requests

BASE = "http://127.0.0.1:8787"

# Check health
print(requests.get(f"{BASE}/health").json())

# Register and get a token
resp = requests.post(f"{BASE}/auth/register", json={
    "username": "botuser",
    "password": "SecureP@ss123!"
})
token = resp.json()["access_token"]

# Check security status
print(requests.get(f"{BASE}/security/status").json())
```

---

## Updating

```bash
# Pull latest changes
git -C ~/AI-EMPLOYEE pull origin main

# Re-run installer to pick up new runtime files
cd ~/AI-EMPLOYEE && bash install.sh

# Update Python dependencies
pip3 install --user -r ~/.ai-employee/bots/problem-solver-ui/requirements.txt --upgrade
```

---

## Security Best Practices

1. **Always use a strong JWT secret** — minimum 32 bytes, cryptographically generated
2. **Keep localhost binding** — don't change `host` to `0.0.0.0` unless necessary
3. **Monitor audit logs** — check `logs/audit.log` for suspicious activity
4. **Update dependencies regularly** — `pip install -r requirements.txt --upgrade`
5. **Use environment variables** — never commit secrets to version control
6. **Enable all security features** — review `SECURITY.md` for the full checklist

---

## Troubleshooting

### "JWT secret must be changed from default"

```bash
export JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

### Application won't start

```bash
# Check the log
tail -50 ~/.ai-employee/logs/gateway.log

# Verify dependencies
pip3 install --user -r ~/.ai-employee/bots/problem-solver-ui/requirements.txt

# Check Python version (3.8+ required)
python3 --version
```

### Cannot connect to dashboard

```bash
# Verify it's running
curl http://127.0.0.1:8787/health

# Check for port conflicts
lsof -i :8787
```

For more help:
- Check `logs/` for detailed error messages
- Review `SECURITY.md` for security-related questions
- File an issue on the GitHub repository
