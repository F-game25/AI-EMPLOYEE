# Security Audit Report

**Date:** 2026-03-27  
**Version:** 2.0.0 (server.py `app_version`)  
**Auditor:** GitHub Copilot Coding Agent — full automated audit  
**Scope:** Entire `F-game25/AI-EMPLOYEE` repository

---

## Summary

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | No secrets committed to repo | ✅ | No real API keys, tokens, or private keys found |
| 2 | JWT validation on startup | ✅ | Server refuses to start if missing, < 32 chars, or known default |
| 3 | Passwords bcrypt hashed | ✅ | bcrypt cost-12 via `security.py`; stored hash only in `users.json` |
| 4 | JWT expiry enforced | ✅ | `exp` claim set on every token (default 30 min) |
| 5 | Algorithm "none" blocked | ✅ | `algorithms=[self.algorithm]` in `verify_token()` — `none` rejected |
| 6 | Rate limiting on auth endpoints | ✅ | 5/minute per IP on `/auth/register` and `/auth/login` |
| 7 | `/auth/login` endpoint present | ✅ | Added with bcrypt verification and no user-enumeration |
| 8 | Path traversal blocked | ✅ | `InputSanitizer.validate_path()` enforces allowed base dir |
| 9 | Bot name injection blocked | ✅ | Regex `[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}` enforced in server + CLI |
| 10 | Chat message sanitized | ✅ | `InputSanitizer.sanitize_input(max_length=10000)` + null-byte strip |
| 11 | API keys redacted in chatlog | ✅ | `_API_KEY_PATTERN` sub applied before every chatlog write |
| 12 | Server binds localhost only | ✅ | `HOST = "127.0.0.1"` — no `0.0.0.0` in `server.py` |
| 13 | Webhook default binding changed | ✅ | `webhook_server.py` now defaults to `127.0.0.1`; `0.0.0.0` documented as opt-in |
| 14 | Security headers present | ✅ | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `CSP` on every response |
| 15 | CORS localhost only | ✅ | Only `http://localhost:8787` and `http://127.0.0.1:8787` |
| 16 | No secrets in log output | ✅ | Only "set / not set" logged; API keys never logged by value |
| 17 | `.env` chmod 600 after install | ✅ | `install.sh` line 755: `chmod 600 "$AI_HOME/.env"` |
| 18 | `state/` dir chmod 700 | ✅ | Added to `install.sh` and `start.sh` |
| 19 | `users.json` not exposed via HTTP | ✅ | `state/` not mounted as static; FastAPI has no route for it |
| 20 | `users.json` in `.gitignore` | ✅ | Added `state/users.json` to `.gitignore` |
| 21 | No eval() on user input | ✅ | No `eval()`/`exec()` calls on user-controlled data found |
| 22 | Python version check | ✅ | `server.py` exits with clear error on Python < 3.10 |
| 23 | Dependencies pinned | ✅ | All `>=` replaced with `==` in `requirements.txt` |
| 24 | Vulnerable dependencies fixed | ✅ | `cryptography` → 46.0.5; `python-jose` → 3.4.0 (both CVE-free) |
| 25 | `.gitignore` covers key files | ✅ | Added `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx` |
| 26 | JWT_SECRET_KEY never hardcoded | ✅ | Always read from env; placeholder detected and rejected at startup |
| 27 | Mode command injection blocked | ✅ | `case` only accepts `starter\|business\|power` |
| 28 | `ai-employee` bin bot name validated | ✅ | Added regex guard in `start_bot()` and `stop_bot()` shell functions |

---

## Critical Issues Fixed

### 1. Server started despite missing/weak JWT_SECRET_KEY
- **File:** `runtime/bots/problem-solver-ui/server.py` lines 13–105
- **Was:** `except (ValueError, Exception): _security_config = None` — app started in degraded mode
- **Fix:** Added `_validate_jwt_secret_on_startup()` called at module import time. Server now calls `sys.exit(1)` if JWT_SECRET_KEY is empty, < 32 chars, or a known default value.
- **Test:** `JWT_SECRET_KEY="" python3 server.py` → `❌ STARTUP BLOCKED` + exit 1

### 2. Bot name injection (path traversal via subprocess)
- **Files:**
  - `runtime/bots/problem-solver-ui/server.py` — `/api/bots/start`, `/api/bots/stop`, `handle_command()`
  - `runtime/bin/ai-employee` — `start_bot()`, `stop_bot()`
- **Was:** User-supplied bot name passed directly to `ai_employee("start", bot)` / `nohup "$entry"` without validation
- **Fix:** Added `_BOT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")` and validation in all four code paths. Shell script uses `[[ ! "$bot" =~ ^[a-zA-Z0-9]... ]]` guard.
- **Test:** `POST /api/bots/start {"bot": "../../evil"}` → HTTP 400

---

## High-Severity Issues Fixed

### 3. No rate limiting on `/auth/register` (brute-force vector)
- **File:** `runtime/bots/problem-solver-ui/server.py`
- **Was:** No `@limiter.limit()` on `/auth/register`
- **Fix:** Added explicit 5/minute per-IP check via `limiter._check_request_limit()` in both `/auth/register` and the new `/auth/login`

### 4. No `/auth/login` endpoint
- **Was:** Only `/auth/register` existed — no way to authenticate existing users; no password verification path existed to test brute-force protection
- **Fix:** Added `/auth/login` endpoint with bcrypt password verification, 5/minute rate limiting, and no user enumeration (same 401 for wrong user and wrong password)

### 5. Chat message length not enforced
- **File:** `runtime/bots/problem-solver-ui/server.py`, `/api/chat`
- **Was:** Unlimited message length accepted
- **Fix:** `InputSanitizer.sanitize_input(raw_message, max_length=10000)` applied before processing; null-byte stripping also applied

### 6. Vulnerable dependencies: `cryptography` and `python-jose`
- **File:** `runtime/bots/problem-solver-ui/requirements.txt`
- **Was:** `cryptography>=42.0.0` (vulnerable ≤ 46.0.4), `python-jose>=3.3.0` (algorithm confusion CVE < 3.4.0)
- **Fix:** Pinned to `cryptography==46.0.5` and `python-jose[cryptography]==3.4.0` (both CVE-free per GitHub Advisory Database)

---

## Medium-Severity Issues Fixed

### 7. API keys could leak into chatlog
- **File:** `runtime/bots/problem-solver-ui/server.py`
- **Fix:** Added `_API_KEY_PATTERN` regex and `_sanitize_for_log()` function; applied to both user message and bot response before every chatlog write

### 8. `webhook_server.py` defaulted to `0.0.0.0`
- **File:** `runtime/bots/whatsapp-webhook/webhook_server.py`
- **Was:** `WEBHOOK_HOST = os.environ.get("WHATSAPP_WEBHOOK_HOST", "0.0.0.0")`
- **Fix:** Changed default to `127.0.0.1`; `0.0.0.0` documented as opt-in only when Twilio needs direct access, with warning that `TWILIO_AUTH_TOKEN` MUST be set in that case

### 9. `state/` directory not protected
- **Files:** `install.sh`, `runtime/start.sh`
- **Fix:** Added `chmod 700 "$AI_HOME/state"` to both files

### 10. Dependencies used `>=` version specifiers
- **File:** `runtime/bots/problem-solver-ui/requirements.txt`
- **Fix:** All packages now pinned with `==` to prevent silent upgrades to vulnerable versions

### 11. `.gitignore` missing certificate and key extensions
- **File:** `.gitignore`
- **Fix:** Added `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`, and `state/users.json`

### 12. Python version not checked at startup
- **File:** `runtime/bots/problem-solver-ui/server.py`
- **Fix:** Added `sys.version_info < (3, 10)` check that calls `sys.exit(1)` with a clear error

---

## Items Verified as Already Passing (No Changes Required)

- ✅ No real API keys, tokens, or private keys in any committed file
- ✅ JWT uses HS256 — algorithm "none" is explicitly rejected by `python-jose`
- ✅ JWT tokens carry an `exp` claim (default 30 minutes, configurable)
- ✅ `server.py` binds to `127.0.0.1` — never `0.0.0.0`
- ✅ All 4 security headers set on every HTTP response via middleware
- ✅ CORS restricted to localhost origins only
- ✅ `JWT_SECRET_KEY` read exclusively from environment, never hardcoded
- ✅ `security.yml` placeholder detected and rejected by `_check_jwt_secret()`
- ✅ `mode` command in CLI validates against `starter|business|power` only
- ✅ No `eval()` or `exec()` on user-controlled data anywhere in the codebase
- ✅ `InputSanitizer.validate_path()` exists to prevent path traversal in file operations
- ✅ `.env` set to `chmod 600` by `install.sh`
- ✅ `credentials/` directory set to `chmod 700` by `install.sh`
- ✅ `users.json` is NOT served via any HTTP route (state directory not mounted as static)
- ✅ Log statements never write raw API key values — only "set / not set" indicators

---

## How to Verify Security Yourself

### 1. Verify no secrets in repo
```bash
grep -rn "sk-ant-" . --include="*.py" --include="*.sh" --include="*.env" | grep -v ".git"
grep -rn "-----BEGIN.*PRIVATE KEY-----" . | grep -v ".git"
```
Expected: No output.

### 2. Verify server refuses weak JWT_SECRET_KEY
```bash
JWT_SECRET_KEY="" python3 ~/.ai-employee/bots/problem-solver-ui/server.py
# Expected: ❌ STARTUP BLOCKED: JWT_SECRET_KEY is not set ... (exit 1)

JWT_SECRET_KEY="short" python3 ~/.ai-employee/bots/problem-solver-ui/server.py
# Expected: ❌ STARTUP BLOCKED: JWT_SECRET_KEY must be at least 32 characters (exit 1)

JWT_SECRET_KEY="secret" python3 ~/.ai-employee/bots/problem-solver-ui/server.py
# Expected: ❌ STARTUP BLOCKED (known default) (exit 1)
```

### 3. Verify fake JWT returns 401
```bash
curl -s -X GET http://127.0.0.1:8787/api/status \
  -H "Authorization: Bearer fake.token.here"
# Expected: 401 Unauthorized (or no auth required on status — check /auth/login first)

curl -s -X POST http://127.0.0.1:8787/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"WrongPass1!"}' 
# Expected: {"detail":"Invalid username or password."}
```

### 4. Verify brute-force protection (rate limiting)
```bash
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8787/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"x","password":"y"}')
  echo "Attempt $i: HTTP $code"
done
# Expected: HTTP 429 before attempt 6 (5/minute limit)
```

### 5. Verify bot name injection is blocked
```bash
curl -s -X POST http://127.0.0.1:8787/api/bots/start \
  -H "Content-Type: application/json" \
  -d '{"bot": "../../evil"}'
# Expected: {"detail":"Invalid bot name. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{0,63}."}
```

### 6. Verify security headers
```bash
curl -sI http://127.0.0.1:8787/health
# Expected headers present:
#   X-Content-Type-Options: nosniff
#   X-Frame-Options: DENY
#   X-XSS-Protection: 1; mode=block
#   Content-Security-Policy: default-src 'self' ...
```

### 7. Verify server only binds localhost
```bash
grep "0\.0\.0\.0" ~/.ai-employee/bots/problem-solver-ui/server.py
# Expected: No output
```

### 8. Verify users.json is not accessible via HTTP
```bash
curl -s http://127.0.0.1:8787/state/users.json
# Expected: 404 Not Found

curl -s http://127.0.0.1:8787/../.env
# Expected: 400 or 404
```

### 9. Verify .env permissions
```bash
ls -la ~/.ai-employee/.env
# Expected: -rw------- (chmod 600)

ls -la ~/.ai-employee/state/
# Expected: drwx------ (chmod 700)
```

### 10. Run the built-in safety self-test
```bash
python3 ~/.ai-employee/bots/bot_selftest.py
# Expected: All required checks ✅ — overall result green

# Send a live Discord ping to verify webhook:
python3 ~/.ai-employee/bots/bot_selftest.py --live
```

### 11. Verify no vulnerable dependencies
```bash
pip install pip-audit
pip-audit -r ~/.ai-employee/bots/problem-solver-ui/requirements.txt
# Expected: No vulnerabilities found
```

---

## Security Recommendations (Not Blocking)

1. **Rotate JWT_SECRET_KEY every 90 days** — set a calendar reminder. Regenerate with:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Enable HTTPS** when exposing any service beyond localhost. Use a reverse proxy (nginx/Caddy) with Let's Encrypt.

3. **Set `TWILIO_AUTH_TOKEN`** when running `webhook_server.py` with `WHATSAPP_WEBHOOK_HOST=0.0.0.0`. Twilio signature validation is already implemented — it just needs the token to be set.

4. **Run `pip-audit` regularly** — add it to your CI/CD pipeline to catch new CVEs in pinned versions.

5. **Limit dashboard access** — if running on a shared machine, consider adding IP allowlist at the reverse proxy level.

---

*All critical and high-severity issues have been fixed. The codebase meets the pass criteria.*
