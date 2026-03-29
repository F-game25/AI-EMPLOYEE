"""AI Employee Dashboard — Problem Solver UI

Extended dashboard with 5 tabs:
  1. Dashboard  — bot status overview
  2. Chat       — send tasks / view chat log (mirrors WhatsApp tasks)
  3. Scheduler  — create/edit/list scheduled tasks
  4. Workers    — view/adjust enabled bots
  5. Improvements — approve/reject skill/market proposals

State files are read from ~/.ai-employee/state/
Config is read/written in ~/.ai-employee/config/
"""
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Python version guard ──────────────────────────────────────────────────────
if sys.version_info < (3, 10):
    print("ERROR: Python 3.10+ is required. Current version: "
          f"{sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# ── Security imports (openclaw-2) ─────────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _SLOWAPI_AVAILABLE = True
except ImportError:
    _SLOWAPI_AVAILABLE = False

# Locate security module relative to this file
_SEC_DIR = Path(__file__).parent
if str(_SEC_DIR) not in sys.path:
    sys.path.insert(0, str(_SEC_DIR))

# ── JWT secret startup validation ─────────────────────────────────────────────
_KNOWN_WEAK_SECRETS = frozenset({
    "", "secret", "changeme", "change-me", "your-secret-here", "default",
    "password", "1234", "12345678", "test", "dev",
    "CHANGE_THIS_IN_SECURITY_LOCAL_YML_OR_SET_JWT_SECRET_KEY_ENV_VAR",
})

def _validate_jwt_secret_on_startup(secret: str) -> None:
    """Refuse to start if JWT_SECRET_KEY is missing, too short, or a known default."""
    # Normalise to lowercase for case-insensitive weak-value detection
    if secret.lower() in _KNOWN_WEAK_SECRETS:
        print(
            "\n❌  STARTUP BLOCKED: JWT_SECRET_KEY is not set or uses a known default.\n"
            "    Generate a strong secret and export it:\n\n"
            "        export JWT_SECRET_KEY=$(python3 -c "
            "\"import secrets; print(secrets.token_hex(32))\")\n\n"
            "    Or add JWT_SECRET_KEY=<value> to ~/.ai-employee/.env\n"
        )
        sys.exit(1)
    if len(secret) < 32:
        print(
            "\n❌  STARTUP BLOCKED: JWT_SECRET_KEY must be at least 32 characters.\n"
            "    Generate a strong secret:\n\n"
            "        python3 -c \"import secrets; print(secrets.token_hex(32))\"\n"
        )
        sys.exit(1)

_jwt_secret_env = os.environ.get("JWT_SECRET_KEY", "")
_validate_jwt_secret_on_startup(_jwt_secret_env)

# ── Bot name validation ────────────────────────────────────────────────────────
_BOT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

def _validate_bot_name(name: str) -> str:
    """Raise HTTP 400 if *name* is not a valid bot name. Returns the name unchanged."""
    if not name or not _BOT_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Invalid bot name. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{0,63}.",
        )
    return name

try:
    from security import AuthManager, InputSanitizer, PasswordValidator
    from config_manager import load_config, validate_security_config, Config as _Cfg
    _security_config: Optional[_Cfg] = None
    try:
        _security_config = load_config()
    except ValueError as _jwt_err:
        # load_config() raises ValueError when JWT_SECRET_KEY is missing/default.
        # _validate_jwt_secret_on_startup() above already handles the empty-env case;
        # this catches the case where security.yml still has the placeholder value.
        print(f"\n❌  STARTUP BLOCKED: {_jwt_err}\n")
        sys.exit(1)
    except Exception:
        # Other config errors (YAML parse, etc.) — still start but without
        # the richer config object; JWT is already validated above.
        _security_config = None
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
    _security_config = None

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
CONFIG_DIR = AI_HOME / "config"
BOTS_DIR = AI_HOME / "bots"
CHATLOG = STATE_DIR / "chatlog.jsonl"
ACTIVITY_LOG = STATE_DIR / "activity_log.jsonl"
SCHEDULES_FILE = CONFIG_DIR / "schedules.json"
IMPROVEMENTS_FILE = STATE_DIR / "improvements.json"
SKILLS_LIBRARY_FILE = CONFIG_DIR / "skills_library.json"
CUSTOM_AGENTS_FILE = CONFIG_DIR / "custom_agents.json"
METRICS_FILE = STATE_DIR / "metrics.json"
GUARDRAILS_FILE = STATE_DIR / "guardrails.json"
MEMORY_FILE = STATE_DIR / "memory.json"
INTEGRATIONS_FILE = CONFIG_DIR / "integrations.json"
AGENT_TEMPLATES_FILE = CONFIG_DIR / "agent_templates.json"

# Source agent_templates.json path (bundled in repo config directory)
_REPO_TEMPLATES_FILE = Path(__file__).parent.parent.parent / "config" / "agent_templates.json"

PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")
MAX_CHAT_MESSAGE_LENGTH = 10000

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(message)s",
)
logger = logging.getLogger("problem-solver-ui")

_ACTIVITY_LOCK = threading.Lock()

def _log_activity(
    event_type: str,
    description: str,
    details: "dict | None" = None,
    source: str = "system",
) -> None:
    """Append one entry to the persistent activity log (activity_log.jsonl)."""
    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "description": description,
        "source": source,
    }
    if details:
        entry["details"] = details
    try:
        ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _ACTIVITY_LOCK:
            with open(ACTIVITY_LOG, "a") as _fh:
                _fh.write(json.dumps(entry) + "\n")
    except Exception as _exc:
        logger.warning("Failed to write activity log: %s", _exc)


_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai as _query_ai  # type: ignore
    _AI_ROUTER_AVAILABLE = True
except ImportError:
    _AI_ROUTER_AVAILABLE = False

app = FastAPI(title="AI Employee Dashboard")

# ── Rate limiter (openclaw-2) ─────────────────────────────────────────────────
if _SLOWAPI_AVAILABLE:
    _rate_limit = (
        f"{_security_config.security.rate_limit_per_minute}/minute"
        if _security_config else "60/minute"
    )
    limiter = Limiter(key_func=get_remote_address, default_limits=[_rate_limit])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    limiter = None


def _auth_rate_limit(f):
    """Apply 5/minute per-IP rate limit to auth endpoints.

    Uses the slowapi limiter if available; otherwise returns the function unchanged
    (rate limiting is then handled only by the global default limit).
    Endpoints must accept ``request: Request`` as a parameter for the decorator to work.
    """
    if _SLOWAPI_AVAILABLE and limiter is not None:
        return limiter.limit("5/minute")(f)
    return f

# ── CORS (openclaw-2) ─────────────────────────────────────────────────────────
_cors_origins = (
    _security_config.security.cors_origins
    if _security_config
    else ["http://localhost:8787", "http://127.0.0.1:8787"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# ── Security headers middleware (openclaw-2) ──────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach HTTP security headers to every response.

    The index route (/) generates its own tighter CSP with a per-request nonce
    for the inline script block.  This middleware only sets the CSP fallback for
    all other routes (JSON API endpoints) that don't set one themselves.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Only set the fallback CSP when the index route has not already applied
    # a tighter nonce-based policy for the dashboard HTML.
    if "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "img-src 'self' data: blob:"
        )
    return response

# ── Audit logging middleware (openclaw-2) ─────────────────────────────────────
_audit_logger = logging.getLogger("ai_employee.audit")
if not _audit_logger.handlers:
    _audit_handler = logging.StreamHandler()
    _audit_handler.setFormatter(logging.Formatter("%(asctime)s AUDIT %(message)s"))
    _audit_logger.addHandler(_audit_handler)
    _audit_logger.setLevel(logging.INFO)

@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    """Log every inbound request and outbound status for the audit trail."""
    _audit_enabled = (
        _security_config.logging.audit_enabled if _security_config else True
    )
    if not _audit_enabled:
        return await call_next(request)

    start = datetime.now(timezone.utc)
    _audit_logger.info(json.dumps({
        "event": "request",
        "timestamp": start.isoformat(),
        "method": request.method,
        "path": request.url.path,
        "client": request.client.host if request.client else "unknown",
    }))
    response = await call_next(request)
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    _audit_logger.info(json.dumps({
        "event": "response",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_seconds": round(duration, 4),
    }))
    return response


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ai_employee(*args: str) -> tuple:
    try:
        p = subprocess.run(
            [str(AI_HOME / "bin" / "ai-employee"), *args],
            capture_output=True, text=True, timeout=10
        )
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        return 1, str(e)


# ─── HTML Dashboard ────────────────────────────────────────────────────────────

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Employee Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg:#080e1a;--surface:#0d1626;--surface2:#111d30;--border:#1e2d45;
      --primary:#6366f1;--primary-dark:#4f46e5;--accent:#22d3ee;
      --success:#10b981;--danger:#ef4444;--warning:#f59e0b;
      --text:#e2e8f0;--text-muted:#64748b;--text-secondary:#94a3b8;
      --radius:12px;--radius-sm:8px;--shadow:0 4px 24px rgba(0,0,0,.4);
      --glow-primary:0 0 20px rgba(99,102,241,.35);
      --glow-success:0 0 20px rgba(16,185,129,.35);
      --glow-danger:0 0 20px rgba(239,68,68,.35);
    }
    *{box-sizing:border-box;margin:0;padding:0}
    html{scroll-behavior:smooth}
    body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar{width:6px;height:6px}
    ::-webkit-scrollbar-track{background:var(--surface)}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
    ::-webkit-scrollbar-thumb:hover{background:#2a3d5a}

    /* ── Layout ── */
    .app{display:flex;flex-direction:column;min-height:100vh}

    /* ── Keyframe animations ── */
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
    @keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
    @keyframes slideInLeft{from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:none}}
    @keyframes slideInRight{from{opacity:0;transform:translateX(18px)}to{opacity:1;transform:none}}
    @keyframes slideInUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
    @keyframes pulseRing{0%{transform:scale(1);opacity:.8}70%{transform:scale(1.9);opacity:0}100%{transform:scale(1.9);opacity:0}}
    @keyframes gradientShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
    @keyframes shimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}
    @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
    @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
    @keyframes countUp{from{opacity:0;transform:scale(.85)}to{opacity:1;transform:scale(1)}}
    @keyframes headerGlow{0%,100%{box-shadow:0 2px 30px rgba(99,102,241,.2)}50%{box-shadow:0 2px 50px rgba(99,102,241,.45)}}

    /* ── Header ── */
    header{
      background:linear-gradient(135deg,#1e1b4b 0%,#312e81 35%,var(--primary-dark) 65%,#1e1b4b 100%);
      background-size:300% 300%;
      animation:gradientShift 12s ease infinite, headerGlow 6s ease infinite;
      padding:16px 28px;display:flex;align-items:center;justify-content:space-between;
      border-bottom:1px solid rgba(99,102,241,.3);
      position:sticky;top:0;z-index:100;backdrop-filter:blur(12px);
    }
    .header-left{display:flex;align-items:center;gap:14px}
    .logo{
      width:44px;height:44px;
      background:linear-gradient(135deg,rgba(99,102,241,.3),rgba(34,211,238,.2));
      border-radius:12px;display:flex;align-items:center;justify-content:center;
      font-size:1.5em;border:1px solid rgba(255,255,255,.2);
      animation:float 4s ease-in-out infinite;
      box-shadow:0 0 14px rgba(99,102,241,.4);
    }
    .header-title h1{color:#fff;font-size:1.25em;font-weight:700;letter-spacing:-.02em;
      text-shadow:0 0 20px rgba(255,255,255,.3)}
    .header-title .sub{color:rgba(255,255,255,.65);font-size:.8em;margin-top:2px}
    .header-right{display:flex;align-items:center;gap:10px}
    .status-pill{display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.08);
      border:1px solid rgba(255,255,255,.15);border-radius:20px;
      padding:6px 14px;font-size:.8em;color:rgba(255,255,255,.8);
      backdrop-filter:blur(6px);transition:all .3s}
    .status-pill:hover{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.25)}
    .status-dot{width:8px;height:8px;border-radius:50%;background:var(--success);
      box-shadow:0 0 8px var(--success);animation:blink 2s infinite;flex-shrink:0}
    /* Header quick-control buttons */
    .hdr-ctrl{display:flex;align-items:center;gap:8px}
    .hdr-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border:none;
      border-radius:20px;cursor:pointer;font-size:.78em;font-weight:600;
      transition:all .2s;font-family:inherit;white-space:nowrap;position:relative;overflow:hidden}
    .hdr-btn-start{background:rgba(16,185,129,.2);color:var(--success);border:1px solid rgba(16,185,129,.35)}
    .hdr-btn-start:hover{background:rgba(16,185,129,.35);box-shadow:var(--glow-success);transform:translateY(-1px)}
    .hdr-btn-stop{background:rgba(239,68,68,.15);color:var(--danger);border:1px solid rgba(239,68,68,.3)}
    .hdr-btn-stop:hover{background:rgba(239,68,68,.28);box-shadow:var(--glow-danger);transform:translateY(-1px)}
    .hdr-btn:disabled{opacity:.45;cursor:not-allowed;transform:none!important;box-shadow:none!important}

    /* ── Navigation ── */
    nav{background:var(--surface);border-bottom:1px solid var(--border);
      padding:0 28px;display:flex;gap:2px;overflow-x:auto;
      box-shadow:0 2px 12px rgba(0,0,0,.3)}
    nav button{
      background:none;border:none;color:var(--text-secondary);
      padding:12px 16px;cursor:pointer;font-size:.875em;font-weight:500;
      border-bottom:2px solid transparent;transition:all .25s;
      white-space:nowrap;display:flex;align-items:center;gap:6px;
      font-family:inherit;position:relative;
    }
    nav button::after{content:'';position:absolute;bottom:0;left:50%;right:50%;height:2px;
      background:var(--primary);border-radius:2px 2px 0 0;transition:all .25s}
    nav button:hover{color:var(--text);background:rgba(255,255,255,.04)}
    nav button:hover::after{left:0;right:0}
    nav button.active{color:var(--primary);background:rgba(99,102,241,.06)}
    nav button.active::after{left:0;right:0}

    /* ── Main content ── */
    main{flex:1;padding:24px 28px;max-width:1280px;margin:0 auto;width:100%}
    @media(max-width:768px){main{padding:14px}}

    /* ── Tab panels ── */
    .tab-content{display:none}
    .tab-content.active{display:block;animation:fadeIn .28s ease}

    /* ── Cards ── */
    .card{
      background:var(--surface);border:1px solid var(--border);
      border-radius:var(--radius);padding:20px;margin-bottom:16px;
      transition:border-color .3s,box-shadow .3s;
    }
    .card:hover{border-color:rgba(99,102,241,.2);box-shadow:0 4px 20px rgba(0,0,0,.25)}
    .card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
    .card-title{font-size:.95em;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px}
    .card-title .icon{color:var(--primary)}
    .section-title{font-size:.8em;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}

    /* ── Grid layouts ── */
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
    .grid-stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
    @media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}

    /* ── Stat cards ── */
    .stat-card{
      background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:18px 16px;display:flex;align-items:center;gap:13px;
      transition:all .3s;cursor:default;position:relative;overflow:hidden;
    }
    .stat-card::before{
      content:'';position:absolute;top:0;left:0;right:0;height:2px;
      background:linear-gradient(90deg,transparent,var(--stat-color,var(--primary)),transparent);
      opacity:0;transition:opacity .3s;
    }
    .stat-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.3)}
    .stat-card:hover::before{opacity:1}
    .stat-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;
      justify-content:center;font-size:1.2em;flex-shrink:0;transition:transform .3s}
    .stat-card:hover .stat-icon{transform:scale(1.1) rotate(-4deg)}
    .stat-icon.green{background:rgba(16,185,129,.15);color:var(--success);--stat-color:var(--success)}
    .stat-icon.blue{background:rgba(99,102,241,.15);color:var(--primary);--stat-color:var(--primary)}
    .stat-icon.cyan{background:rgba(34,211,238,.15);color:var(--accent);--stat-color:var(--accent)}
    .stat-icon.yellow{background:rgba(245,158,11,.15);color:var(--warning);--stat-color:var(--warning)}
    .stat-body .val{font-size:1.55em;font-weight:700;color:var(--text);
      animation:countUp .4s ease;letter-spacing:-.02em}
    .stat-body .lbl{font-size:.78em;color:var(--text-muted);margin-top:2px}

    /* ── System control hero ── */
    .sys-control{
      background:linear-gradient(135deg,rgba(99,102,241,.08) 0%,rgba(34,211,238,.05) 100%);
      border:1px solid rgba(99,102,241,.25);border-radius:var(--radius);
      padding:24px 28px;margin-bottom:16px;
      display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;
      position:relative;overflow:hidden;
    }
    .sys-control::before{
      content:'';position:absolute;top:-50%;right:-10%;width:300px;height:300px;
      background:radial-gradient(circle,rgba(99,102,241,.08) 0%,transparent 70%);
      pointer-events:none;animation:float 8s ease-in-out infinite;
    }
    .sys-control-left{display:flex;align-items:center;gap:18px}
    .sys-status-ring{position:relative;width:56px;height:56px;flex-shrink:0}
    .sys-status-ring .ring-bg{
      width:56px;height:56px;border-radius:50%;
      border:3px solid rgba(99,102,241,.2);
      display:flex;align-items:center;justify-content:center;
      font-size:1.6em;background:rgba(99,102,241,.08);
    }
    .sys-status-ring .ring-pulse{
      position:absolute;inset:0;border-radius:50%;
      border:3px solid var(--success);
      animation:pulseRing 2.5s ease-out infinite;
    }
    .sys-status-ring.offline .ring-pulse{border-color:var(--danger)}
    .sys-control-info h2{font-size:1.1em;font-weight:700;color:var(--text);margin-bottom:3px}
    .sys-control-info p{font-size:.84em;color:var(--text-secondary)}
    .sys-control-right{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .btn-hero{
      display:inline-flex;align-items:center;gap:8px;padding:12px 28px;border:none;
      border-radius:10px;cursor:pointer;font-size:.95em;font-weight:600;
      transition:all .25s;font-family:inherit;white-space:nowrap;
      position:relative;overflow:hidden;
    }
    .btn-hero::after{
      content:'';position:absolute;top:50%;left:50%;width:0;height:0;
      background:rgba(255,255,255,.15);border-radius:50%;
      transform:translate(-50%,-50%);transition:width .4s ease,height .4s ease,opacity .4s ease;
      opacity:0;
    }
    .btn-hero:active::after{width:300px;height:300px;opacity:0}
    .btn-hero-start{
      background:linear-gradient(135deg,#059669,#10b981);
      color:#fff;box-shadow:0 4px 16px rgba(16,185,129,.3);
    }
    .btn-hero-start:hover{
      background:linear-gradient(135deg,#10b981,#34d399);
      box-shadow:0 6px 24px rgba(16,185,129,.5);transform:translateY(-2px);
    }
    .btn-hero-stop{
      background:linear-gradient(135deg,#b91c1c,#ef4444);
      color:#fff;box-shadow:0 4px 16px rgba(239,68,68,.3);
    }
    .btn-hero-stop:hover{
      background:linear-gradient(135deg,#ef4444,#f87171);
      box-shadow:0 6px 24px rgba(239,68,68,.5);transform:translateY(-2px);
    }
    .btn-hero:disabled{opacity:.45;cursor:not-allowed;transform:none!important;box-shadow:none!important}
    .btn-hero .btn-icon{font-size:1.1em}

    /* ── Bot health progress bar ── */
    .health-bar-wrap{margin:10px 0 4px;position:relative}
    .health-bar-track{height:6px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden}
    .health-bar-fill{
      height:100%;border-radius:3px;
      background:linear-gradient(90deg,var(--success),#34d399);
      transition:width .8s cubic-bezier(.4,0,.2,1);
      box-shadow:0 0 8px rgba(16,185,129,.4);
      width:0%;
    }
    .health-bar-fill.warn{background:linear-gradient(90deg,var(--warning),#fbbf24)}
    .health-bar-fill.danger{background:linear-gradient(90deg,var(--danger),#f87171)}
    .health-label{display:flex;justify-content:space-between;font-size:.74em;color:var(--text-muted);margin-top:4px}

    /* ── Bot rows ── */
    .bot-row{
      display:flex;align-items:center;gap:10px;padding:9px 8px;
      border-bottom:1px solid var(--border);border-radius:6px;
      transition:background .2s;animation:slideInLeft .3s ease both;
    }
    .bot-row:last-child{border-bottom:none}
    .bot-row:hover{background:rgba(255,255,255,.03)}
    .dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;transition:all .4s;position:relative}
    .dot.on{background:var(--success);box-shadow:0 0 8px rgba(16,185,129,.6)}
    .dot.on::after{
      content:'';position:absolute;inset:-3px;border-radius:50%;
      border:1.5px solid rgba(16,185,129,.4);
      animation:pulseRing 2.5s ease-out infinite;
    }
    .dot.off{background:#374151}
    .dot.unknown{background:var(--warning)}
    .bot-name{flex:1;font-size:.875em;color:var(--text)}

    /* ── Badges ── */
    .badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:20px;
      font-size:.75em;font-weight:600;letter-spacing:.01em}
    .badge.running,.badge.approved{background:rgba(16,185,129,.12);color:var(--success);border:1px solid rgba(16,185,129,.25)}
    .badge.stopped,.badge.rejected{background:rgba(239,68,68,.12);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .badge.pending{background:rgba(245,158,11,.12);color:var(--warning);border:1px solid rgba(245,158,11,.25)}
    .badge.enabled{background:rgba(99,102,241,.12);color:var(--primary);border:1px solid rgba(99,102,241,.25)}
    .badge.disabled{background:rgba(100,116,139,.12);color:var(--text-muted);border:1px solid rgba(100,116,139,.25)}

    /* ── Buttons ── */
    .btn{
      display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border:none;
      border-radius:var(--radius-sm);cursor:pointer;font-size:.875em;font-weight:500;
      transition:all .22s;font-family:inherit;text-decoration:none;white-space:nowrap;
      position:relative;overflow:hidden;
    }
    .btn::after{
      content:'';position:absolute;top:50%;left:50%;width:0;height:0;
      background:rgba(255,255,255,.12);border-radius:50%;
      transform:translate(-50%,-50%);transition:width .35s ease,height .35s ease,opacity .35s ease;
      opacity:0;
    }
    .btn:active::after{width:240px;height:240px;opacity:0}
    .btn-primary{background:var(--primary);color:#fff}
    .btn-primary:hover{background:var(--primary-dark);transform:translateY(-1px);box-shadow:0 4px 14px rgba(99,102,241,.45)}
    .btn-danger{background:rgba(239,68,68,.15);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .btn-danger:hover{background:rgba(239,68,68,.28);box-shadow:0 3px 10px rgba(239,68,68,.25)}
    .btn-success{background:rgba(16,185,129,.15);color:var(--success);border:1px solid rgba(16,185,129,.25)}
    .btn-success:hover{background:rgba(16,185,129,.28);box-shadow:0 3px 10px rgba(16,185,129,.25)}
    .btn-ghost{background:rgba(255,255,255,.05);color:var(--text-secondary);border:1px solid var(--border)}
    .btn-ghost:hover{background:rgba(255,255,255,.09);color:var(--text);border-color:rgba(99,102,241,.3)}
    .btn-sm{padding:5px 11px;font-size:.8em}
    .btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}

    /* ── Form controls ── */
    .form-group{margin-bottom:14px}
    label{display:block;font-size:.82em;font-weight:500;color:var(--text-secondary);margin-bottom:5px}
    input,textarea,select{
      width:100%;background:var(--surface2);border:1px solid var(--border);
      color:var(--text);border-radius:var(--radius-sm);padding:9px 12px;
      font-size:.875em;font-family:inherit;transition:border-color .2s,box-shadow .2s;outline:none}
    input:focus,textarea:focus,select:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.14)}
    input:hover,select:hover{border-color:rgba(99,102,241,.35)}
    textarea{resize:vertical;min-height:80px}
    select option{background:var(--surface)}

    /* ── Toggle (enhanced) ── */
    .toggle{position:relative;display:inline-block;width:42px;height:24px;flex-shrink:0}
    .toggle input{opacity:0;width:0;height:0}
    .slider{
      position:absolute;cursor:pointer;inset:0;
      background:var(--border);border-radius:24px;
      transition:.35s cubic-bezier(.4,0,.2,1);
      box-shadow:inset 0 1px 3px rgba(0,0,0,.3);
    }
    .slider:before{
      content:"";position:absolute;width:18px;height:18px;left:3px;top:3px;
      background:#64748b;border-radius:50%;
      transition:.35s cubic-bezier(.4,0,.2,1);
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    }
    input:checked+.slider{background:var(--primary);box-shadow:0 0 10px rgba(99,102,241,.4)}
    input:checked+.slider:before{transform:translateX(18px);background:#fff}

    /* ── Code / pre ── */
    pre{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;overflow:auto;font-size:.82em;max-height:280px;
      white-space:pre-wrap;word-break:break-word;color:var(--text-secondary);
      font-family:'JetBrains Mono','Fira Code',monospace}
    code{background:rgba(99,102,241,.12);color:var(--primary);
      padding:1px 6px;border-radius:4px;font-size:.88em;font-family:monospace}

    /* ── Chat ── */
    #chat-log{max-height:400px;overflow-y:auto;padding:12px;border:1px solid var(--border);
      border-radius:var(--radius-sm);background:var(--bg);margin-bottom:12px}
    .chat-msg{padding:10px 14px;border-radius:10px;margin-bottom:8px;max-width:82%;
      word-break:break-word;animation:slideInUp .2s ease}
    .chat-msg.user{background:linear-gradient(135deg,var(--primary),var(--primary-dark));
      margin-left:auto;text-align:right;color:#fff;box-shadow:0 2px 10px rgba(99,102,241,.3)}
    .chat-msg.bot{background:var(--surface2);border:1px solid var(--border);color:var(--text)}
    .chat-msg .ts{font-size:.72em;opacity:.55;margin-top:4px}
    .chat-input-row{display:flex;gap:8px;align-items:flex-end}

    /* ── Improvements ── */
    .improv-row{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;margin-bottom:10px;background:var(--surface2);
      transition:border-color .25s,transform .2s,box-shadow .25s}
    .improv-row:hover{border-color:rgba(99,102,241,.35);transform:translateX(3px);box-shadow:var(--glow-primary)}
    .improv-row h4{color:var(--text);font-size:.9em;margin-bottom:4px}
    .improv-row p{font-size:.83em;color:var(--text-secondary);margin-bottom:8px;line-height:1.5}

    /* ── Scheduler ── */
    .sched-row{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:12px 14px;margin-bottom:10px;background:var(--surface2);
      display:flex;align-items:flex-start;gap:12px;
      transition:border-color .25s,box-shadow .25s}
    .sched-row:hover{border-color:rgba(99,102,241,.3);box-shadow:0 2px 12px rgba(0,0,0,.2)}
    .sched-info{flex:1}
    .sched-info h4{color:var(--text);font-size:.88em;margin-bottom:3px;display:flex;align-items:center;gap:8px}
    .sched-info p{font-size:.8em;color:var(--text-muted)}

    /* ── Skills ── */
    .skill-card{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:12px;margin-bottom:8px;cursor:pointer;
      transition:all .22s;background:var(--surface2)}
    .skill-card:hover{border-color:rgba(99,102,241,.4);background:rgba(99,102,241,.06);
      transform:translateY(-1px);box-shadow:0 3px 12px rgba(0,0,0,.2)}
    .skill-card.selected{border-color:var(--success);background:rgba(16,185,129,.06);
      box-shadow:0 0 12px rgba(16,185,129,.15)}
    .skill-card h5{color:var(--text);font-size:.88em;margin-bottom:3px;font-weight:600}
    .skill-card p{font-size:.8em;color:var(--text-muted);margin:0;line-height:1.4}
    .skill-card .tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
    .tag{background:rgba(99,102,241,.12);color:var(--primary);border-radius:4px;
      padding:2px 7px;font-size:.72em;font-weight:500}
    .cat-pill{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.8em;
      cursor:pointer;border:1px solid var(--border);color:var(--text-secondary);
      margin:2px;transition:all .2s;font-weight:500}
    .cat-pill:hover{border-color:var(--primary);color:var(--primary)}
    .cat-pill.active{background:var(--primary);color:#fff;border-color:var(--primary);
      box-shadow:0 2px 8px rgba(99,102,241,.3)}
    .skill-grid{max-height:500px;overflow-y:auto;padding-right:4px}
    .agent-card{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;margin-bottom:8px;background:var(--surface2);transition:all .2s}
    .agent-card:hover{border-color:rgba(99,102,241,.3);transform:translateY(-1px)}
    .agent-card h4{color:var(--text);margin-bottom:4px;font-size:.9em;font-weight:600}
    .agent-card p{font-size:.83em;color:var(--text-muted)}
    #skill-search{margin-bottom:10px}

    /* ── Toast ── */
    #toast{
      position:fixed;bottom:24px;right:24px;min-width:240px;padding:13px 20px;
      border-radius:10px;color:#fff;opacity:0;
      transition:opacity .3s,transform .3s;pointer-events:none;z-index:9999;
      font-size:.875em;font-weight:500;box-shadow:0 8px 32px rgba(0,0,0,.5);
      transform:translateY(12px);display:flex;align-items:center;gap:10px;
      border-left:3px solid rgba(255,255,255,.3);
    }
    #toast.show{opacity:1;transform:translateY(0)}

    /* ── Empty states ── */
    .empty{text-align:center;padding:32px 16px;color:var(--text-muted)}
    .empty .icon{font-size:2.5em;margin-bottom:10px;opacity:.4}
    .empty p{font-size:.88em}

    /* ── Spinner (for button loading states) ── */
    .spinner{display:inline-block;animation:spin .8s linear infinite}

    /* ── Divider ── */
    hr{border:none;border-top:1px solid var(--border);margin:16px 0}

    /* ── Quick actions bar ── */
    .actions-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}

    /* ── Cmd reference ── */
    .cmd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}
    .cmd-item{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:10px 14px;transition:all .2s;cursor:pointer}
    .cmd-item:hover{border-color:rgba(99,102,241,.3);background:rgba(99,102,241,.05)}
    .cmd-item code{display:block;margin-bottom:4px;font-size:.82em}
    .cmd-item span{font-size:.78em;color:var(--text-muted)}

    /* ── Staggered animation delays for bot rows ── */
    .bot-row:nth-child(1){animation-delay:.02s}
    .bot-row:nth-child(2){animation-delay:.04s}
    .bot-row:nth-child(3){animation-delay:.06s}
    .bot-row:nth-child(4){animation-delay:.08s}
    .bot-row:nth-child(5){animation-delay:.1s}
    .bot-row:nth-child(6){animation-delay:.12s}
    .bot-row:nth-child(7){animation-delay:.14s}
    .bot-row:nth-child(8){animation-delay:.16s}
    .bot-row:nth-child(9){animation-delay:.18s}
    .bot-row:nth-child(n+10){animation-delay:.2s}
  </style>
</head>
<body>
<div class="app">

<!-- ── Header ── -->
<header>
  <div class="header-left">
    <div class="logo">🤖</div>
    <div class="header-title">
      <h1>AI Employee</h1>
      <div class="sub" id="header-sub">Loading…</div>
    </div>
  </div>
  <div class="header-right">
    <div class="hdr-ctrl">
      <button class="hdr-btn hdr-btn-start" id="hdr-start-btn" onclick="startAll()" title="Start all bots">▶ Start</button>
      <button class="hdr-btn hdr-btn-stop" id="hdr-stop-btn" onclick="stopAll()" title="Stop all bots">■ Stop</button>
    </div>
    <div class="status-pill"><div class="status-dot"></div><span id="header-status">Running</span></div>
  </div>
</header>

<!-- ── Navigation ── -->
<nav>
  <button class="active" onclick="switchTab('dashboard',this)">📊 Dashboard</button>
  <button onclick="switchTab('chat',this)">💬 Chat</button>
  <button onclick="switchTab('tasks',this)">🚀 Tasks</button>
  <button onclick="switchTab('swarm',this)">🐝 Swarm</button>
  <button onclick="switchTab('commands',this)">📜 Commands</button>
  <button onclick="switchTab('scheduler',this)">📅 Scheduler</button>
  <button onclick="switchTab('workers',this)">👷 Workers</button>
  <button onclick="switchTab('improvements',this)">💡 Improvements</button>
  <button onclick="switchTab('skills',this)">🛠️ Skills</button>
  <button onclick="switchTab('metrics',this)">📈 ROI</button>
  <button onclick="switchTab('templates',this)">📋 Templates</button>
  <button onclick="switchTab('guardrails',this)">🔒 Guardrails</button>
  <button onclick="switchTab('memory',this)">🧠 Memory</button>
  <button onclick="switchTab('integrations',this)">🔌 Integrations</button>
  <button onclick="switchTab('history',this)">🕐 History</button>
  <button onclick="switchTab('options',this)">⚙️ Options</button>
</nav>

<main>

<!-- ── Dashboard ── -->
<div id="tab-dashboard" class="tab-content active">

  <!-- System Control Hero -->
  <div class="sys-control">
    <div class="sys-control-left">
      <div class="sys-status-ring" id="sys-ring">
        <div class="ring-bg">🤖</div>
        <div class="ring-pulse"></div>
      </div>
      <div class="sys-control-info">
        <h2>AI Employee System</h2>
        <p id="sys-control-sub">Loading system status…</p>
        <div class="health-bar-wrap" style="min-width:200px">
          <div class="health-bar-track"><div class="health-bar-fill" id="health-bar"></div></div>
          <div class="health-label"><span id="health-label-left">Bot Health</span><span id="health-label-right">–</span></div>
        </div>
      </div>
    </div>
    <div class="sys-control-right">
      <button class="btn-hero btn-hero-start" id="hero-start-btn" onclick="startAll()">
        <span class="btn-icon">▶</span> Start All Bots
      </button>
      <button class="btn-hero btn-hero-stop" id="hero-stop-btn" onclick="stopAll()">
        <span class="btn-icon">■</span> Stop All Bots
      </button>
    </div>
  </div>

  <div class="grid-stat" id="stat-cards">
    <div class="stat-card">
      <div class="stat-icon green">🟢</div>
      <div class="stat-body"><div class="val" id="stat-running">–</div><div class="lbl">Bots Running</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon blue">🤖</div>
      <div class="stat-body"><div class="val" id="stat-total">–</div><div class="lbl">Total Bots</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">📡</div>
      <div class="stat-body"><div class="val" id="stat-gateway">–</div><div class="lbl">Gateway</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon yellow">⏱️</div>
      <div class="stat-body"><div class="val" id="stat-uptime">–</div><div class="lbl">Uptime</div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🤖</span> Bot Status</div>
        <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Refresh</button>
      </div>
      <div id="bot-status-list"><div class="empty"><div class="icon">🔍</div><p>Loading bots…</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⚡</span> Quick Actions</div>
      </div>
      <div class="actions-bar">
        <button class="btn btn-success" onclick="startAll()">▶ Start All</button>
        <button class="btn btn-danger" onclick="stopAll()">■ Stop All</button>
        <a class="btn btn-ghost btn-sm" href="http://localhost:18789" target="_blank">📡 Gateway</a>
      </div>
      <hr>
      <div class="card-title" style="margin-bottom:10px"><span class="icon">🔧</span> System Info</div>
      <pre id="system-info" style="font-size:.78em">Click Refresh on the left to load…</pre>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> WhatsApp Commands</div>
    </div>
    <div class="cmd-grid">
      <div class="cmd-item"><code>status</code><span>Get current status report</span></div>
      <div class="cmd-item"><code>workers</code><span>List active workers</span></div>
      <div class="cmd-item"><code>schedule</code><span>List scheduled tasks</span></div>
      <div class="cmd-item"><code>improvements</code><span>List pending proposals</span></div>
      <div class="cmd-item"><code>switch to &lt;agent&gt;</code><span>Switch active agent</span></div>
      <div class="cmd-item"><code>help</code><span>Show all commands</span></div>
    </div>
  </div>
</div>

<!-- ── Chat ── -->
<div id="tab-chat" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> Chat / Task Input</div>
      <button class="btn btn-ghost btn-sm" onclick="loadChatLog()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">
      Send tasks here — same as WhatsApp. Tasks are processed by the active agent.
    </p>
    <div id="chat-log"><div class="empty"><div class="icon">💬</div><p>No messages yet.</p></div></div>
    <div class="chat-input-row">
      <div style="flex:1">
        <textarea id="chat-input" placeholder="Type a task or question…" rows="2"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat()}"></textarea>
      </div>
      <button class="btn btn-primary" onclick="sendChat()" style="height:44px">Send ↗</button>
    </div>
    <p style="font-size:.75em;color:var(--text-muted);margin-top:6px">Press Enter to send · Shift+Enter for new line</p>
  </div>
</div>

<!-- ── Scheduler ── -->
<div id="tab-scheduler" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📅</span> Scheduled Tasks</div>
        <button class="btn btn-ghost btn-sm" onclick="loadSchedules()">↻ Refresh</button>
      </div>
      <div id="schedule-list"><div class="empty"><div class="icon">📅</div><p>No tasks yet.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">➕</span> Add New Task</div>
      </div>
      <div class="form-group"><label>Task ID (unique)</label><input id="sched-id" placeholder="my_task_1"/></div>
      <div class="form-group"><label>Label</label><input id="sched-label" placeholder="Hourly status report"/></div>
      <div class="form-group">
        <label>Action</label>
        <select id="sched-action">
          <option value="log">Log message</option>
          <option value="start_bot">Start bot</option>
          <option value="stop_bot">Stop bot</option>
          <option value="status_report">Send status report</option>
        </select>
      </div>
      <div class="form-group" id="sched-bot-row" style="display:none">
        <label>Bot name</label><input id="sched-bot" placeholder="status-reporter"/>
      </div>
      <div class="form-group"><label>Message (for log action)</label><input id="sched-msg" placeholder="Task ran"/></div>
      <div class="form-group">
        <label>Schedule type</label>
        <select id="sched-type">
          <option value="interval">Interval (every N minutes)</option>
          <option value="daily">Daily at time (UTC)</option>
        </select>
      </div>
      <div class="form-group" id="sched-interval-row">
        <label>Interval (minutes)</label><input id="sched-interval" type="number" value="60" min="1"/>
      </div>
      <div class="form-group" id="sched-daily-row" style="display:none">
        <label>Run at (HH:MM UTC)</label><input id="sched-daily-time" placeholder="08:00"/>
      </div>
      <button class="btn btn-success" onclick="addSchedule()">➕ Add Task</button>
    </div>
  </div>
</div>

<!-- ── Workers ── -->
<div id="tab-workers" class="tab-content">

  <!-- Worker Bundles section -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🏭</span> Worker Bundles</div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="loadWorkers()">↻ Refresh</button>
        <button class="btn btn-primary btn-sm" onclick="openCreateWorker()">＋ New Worker</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Bundle agents together with a recurring task. Workers run on a schedule and always perform their assigned role.
      <strong style="color:var(--accent)">Ecom Workers auto-preset</strong> is included below.
    </p>
    <div id="bundle-list"><div class="empty"><div class="icon">🏭</div><p>No worker bundles yet. Click <strong>+ New Worker</strong> to create one.</p></div></div>
  </div>

  <!-- Create / Edit Worker Bundle form (inline, hidden by default) -->
  <div id="worker-form-card" class="card" style="display:none;border:2px solid var(--primary)">
    <div class="card-header">
      <div class="card-title"><span class="icon">✏️</span> <span id="worker-form-title">Create Worker Bundle</span></div>
      <button class="btn btn-ghost btn-sm" onclick="closeWorkerForm()">✕ Cancel</button>
    </div>
    <div class="grid2" style="gap:12px">
      <div>
        <div class="form-group">
          <label>Worker Name</label>
          <input id="wf-name" placeholder="e.g. Ecom Order Processor" />
        </div>
        <div class="form-group">
          <label>Recurring Task / Role Description</label>
          <textarea id="wf-task" rows="3" placeholder="e.g. Monitor new Shopify orders, validate payments, place Printful orders, send customer tracking emails"
            style="width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:10px;font-family:inherit;resize:vertical"></textarea>
        </div>
        <div class="form-group">
          <label>Schedule</label>
          <select id="wf-schedule" style="width:100%">
            <option value="continuous">Continuous (always on)</option>
            <option value="hourly">Every hour</option>
            <option value="every6h">Every 6 hours</option>
            <option value="daily">Daily (2 AM)</option>
            <option value="3x_daily">3× daily (9 AM / 3 PM / 8 PM)</option>
            <option value="weekly">Weekly</option>
            <option value="manual">Manual trigger only</option>
          </select>
        </div>
        <div class="form-group">
          <label>Description (optional)</label>
          <input id="wf-desc" placeholder="Short description of what this worker does" />
        </div>
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <label style="font-weight:600">Assign Agents <span id="wf-agent-count" style="color:var(--primary)"></span></label>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="wfSelectAll()">All</button>
            <button class="btn btn-ghost btn-sm" onclick="wfClearAll()">None</button>
          </div>
        </div>
        <div id="wf-agent-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:5px;max-height:300px;overflow-y:auto"></div>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn btn-success" onclick="saveWorkerBundle()" style="flex:1" id="wf-save-btn">💾 Save Worker</button>
      <button class="btn btn-ghost" onclick="presetEcomWorker()" title="Fill in the full ecom automation preset">🛒 Ecom Preset</button>
    </div>
    <div id="wf-save-result" style="margin-top:8px;font-size:.84em"></div>
    <input type="hidden" id="wf-editing-id" value="" />
  </div>

  <!-- Bot Workers section (raw bots start/stop) -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">👷</span> Bot Workers</div>
      <button class="btn btn-ghost btn-sm" onclick="loadWorkers()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      Start or stop individual bots. The problem-solver watchdog auto-restarts enabled bots if they crash.
    </p>
    <div id="worker-list"><div class="empty"><div class="icon">👷</div><p>Loading workers…</p></div></div>
  </div>
</div>

<!-- ── Improvements ── -->
<div id="tab-improvements" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💡</span> Improvement Proposals</div>
      <button class="btn btn-ghost btn-sm" onclick="loadImprovements()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">
      The discovery bot proposes new skills and markets. Review and approve or reject below.
      <strong style="color:var(--warning)">No changes are applied automatically.</strong>
    </p>
    <div id="improvement-list"><div class="empty"><div class="icon">💡</div><p>No proposals yet. The discovery bot will add proposals over time.</p></div></div>
  </div>
</div>

<!-- ── Skills ── -->
<div id="tab-skills" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🛠️</span> Skills Library <span id="skill-total-badge" style="font-size:.8em;color:var(--text-muted)"></span></div>
      </div>
      <input id="skill-search" placeholder="Search skills…" oninput="filterSkills()" />
      <div id="category-pills" style="margin:10px 0"></div>
      <div id="skill-grid" class="skill-grid"><div class="empty"><div class="icon">🛠️</div><p>Loading skills…</p></div></div>
    </div>
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🤖</span> Create Custom Agent</div>
        </div>
        <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">Select skills from the library, name your agent, then click Create.</p>
        <div class="form-group"><label>Agent Name</label><input id="agent-name-input" placeholder="e.g. My Content Writer"/></div>
        <div class="form-group"><label>Description (optional)</label><input id="agent-desc-input" placeholder="What this agent does"/></div>
        <div class="form-group">
          <label>Selected Skills <span id="selected-count" style="color:var(--primary)">(0)</span></label>
          <div id="selected-skills-list" style="font-size:.82em;color:var(--text-muted);min-height:24px">No skills selected. Click cards on the left.</div>
        </div>
        <button class="btn btn-success" onclick="createAgent()">➕ Create Agent</button>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">👥</span> Custom Agents</div>
          <button class="btn btn-ghost btn-sm" onclick="loadAgents()">↻ Refresh</button>
        </div>
        <div id="agents-list"><div class="empty"><div class="icon">👥</div><p>No agents yet.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Tasks ── -->
<div id="tab-tasks" class="tab-content">

  <!-- Task Builder -->
  <div class="grid2" style="align-items:start">
    <!-- Left: build a task -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🚀</span> Build a Task</div>
          <span id="task-step-badge" style="font-size:.78em;background:var(--primary);color:#fff;padding:2px 8px;border-radius:10px">Step 1</span>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Describe any goal — agents will be auto-selected. You can adjust everything before launching.</p>

        <!-- Step 1: description -->
        <div id="task-step1">
          <div class="form-group">
            <label>Task Description</label>
            <textarea id="task-input" rows="4"
              placeholder="e.g. Build a SaaS company for remote team management — create business plan, brand identity, hiring plan, financial model, and go-to-market strategy"
              style="width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:10px;font-family:inherit;resize:vertical"
              oninput="onTaskInputChange()"></textarea>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" onclick="runAutoSelect()" style="flex:1" id="btn-autoselect" disabled>🤖 Auto-Select Agents</button>
            <button class="btn btn-ghost btn-sm" onclick="showManualAgentPicker()" title="Manually pick agents">⚙️ Manual</button>
          </div>
          <div id="autoselect-status" style="margin-top:8px;font-size:.82em;color:var(--text-muted)"></div>
        </div>

        <!-- Step 2: agent picker (hidden until auto-select or manual click) -->
        <div id="task-step2" style="display:none;margin-top:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <label style="font-weight:600">🤖 Agent Selection <span id="agent-sel-count" style="color:var(--primary);font-weight:700"></span></label>
            <div style="display:flex;gap:6px">
              <button class="btn btn-ghost btn-sm" onclick="selectAllAgents()">All</button>
              <button class="btn btn-ghost btn-sm" onclick="clearAllAgents()">None</button>
              <button class="btn btn-ghost btn-sm" onclick="resetToAutoSelected()">Auto</button>
            </div>
          </div>
          <div id="agent-picker-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:6px;max-height:340px;overflow-y:auto;padding:2px"></div>
        </div>

        <!-- Step 3: mode + submit (hidden until agents selected) -->
        <div id="task-step3" style="display:none;margin-top:16px">
          <div class="form-group">
            <label>Execution Mode</label>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px" id="mode-selector">
              <label id="mode-auto" onclick="setMode('auto')" style="cursor:pointer;border:2px solid var(--primary);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">🧠</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Auto</div>
                <div style="font-size:.68em;color:var(--text-muted)">Orchestrator decides</div>
              </label>
              <label id="mode-parallel" onclick="setMode('parallel')" style="cursor:pointer;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">⚡</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Parallel</div>
                <div style="font-size:.68em;color:var(--text-muted)">All agents at once</div>
              </label>
              <label id="mode-single" onclick="setMode('single')" style="cursor:pointer;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 4px;text-align:center;background:var(--surface2)">
                <div style="font-size:1.2em">1️⃣</div>
                <div style="font-size:.75em;font-weight:600;margin-top:2px">Single</div>
                <div style="font-size:.68em;color:var(--text-muted)">First selected agent</div>
              </label>
            </div>
          </div>
          <button class="btn btn-success" onclick="submitTask()" style="width:100%;margin-top:4px" id="btn-launch">🚀 Launch Task</button>
          <div id="task-submit-result" style="margin-top:10px;font-size:.88em"></div>
        </div>
      </div>
    </div>

    <!-- Right: active task -->
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span> Active Task</div>
        <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
      </div>
      <div id="active-task-panel"><div class="empty"><div class="icon">🚀</div><p>No active task.</p></div></div>
    </div>
  </div>

  <!-- Task History -->
  <div class="card" style="margin-top:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Recent Tasks</div>
    </div>
    <div id="task-history-list"><div class="empty"><p>No task history yet.</p></div></div>
  </div>
</div>

<!-- ── Swarm ── -->
<div id="tab-swarm" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🐝</span> Agent Swarm Overview</div>
      <button class="btn btn-ghost btn-sm" onclick="loadSwarm()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:12px">All AI agents — their capabilities, current status, and workload.</p>
    <div id="swarm-filter-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px">
      <button class="btn btn-ghost btn-sm swarm-pill active" onclick="filterSwarm('all',this)">All</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('sales',this)">💼 Sales</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('marketing',this)">📢 Marketing</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('social',this)">📱 Social</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('analytics',this)">📊 Analytics</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('content',this)">✍️ Content</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('ecommerce',this)">🛒 E-commerce</button>
      <button class="btn btn-ghost btn-sm swarm-pill" onclick="filterSwarm('coordination',this)">🎯 Core</button>
    </div>
    <div id="swarm-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px"><div class="empty"><div class="icon">🐝</div><p>Loading agents…</p></div></div>
  </div>
</div>

<!-- ── Commands ── -->
<div id="tab-commands" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">📜</span> WhatsApp Commands Reference</div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Every command works on WhatsApp AND in the Chat tab. Click any command to copy it.</p>
    <input id="cmd-search" placeholder="🔍 Search commands…" oninput="filterCommands()" style="width:100%;margin-bottom:14px" />
    <div id="cmd-category-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>
    <div id="cmd-list"></div>
  </div>
</div>

<!-- ── ROI Metrics ── -->
<div id="tab-metrics" class="tab-content">
  <div class="grid-stat" id="roi-stat-cards">
    <div class="stat-card">
      <div class="stat-icon blue">✅</div>
      <div class="stat-body"><div class="val" id="m-tasks">–</div><div class="lbl">Tasks Completed</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">🎯</div>
      <div class="stat-body"><div class="val" id="m-leads">–</div><div class="lbl">Leads Generated</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon green">⏱️</div>
      <div class="stat-body"><div class="val" id="m-hours">–</div><div class="lbl">Hours Saved</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon yellow">💶</div>
      <div class="stat-body"><div class="val" id="m-saved">–</div><div class="lbl">Cost Saved (€)</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon green">📧</div>
      <div class="stat-body"><div class="val" id="m-emails">–</div><div class="lbl">Emails Sent</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">📝</div>
      <div class="stat-body"><div class="val" id="m-content">–</div><div class="lbl">Content Created</div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span> Activity Log</div>
        <button class="btn btn-ghost btn-sm" onclick="loadMetrics()">↻ Refresh</button>
      </div>
      <div id="metrics-events"><div class="empty"><div class="icon">📊</div><p>No events yet. Run some tasks to start tracking ROI.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">➕</span> Record Activity</div>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">Manually log a business result to track ROI.</p>
      <div class="form-group">
        <label>Event Type</label>
        <select id="metric-type">
          <option value="task_completed">Task Completed</option>
          <option value="lead_generated">Lead Generated</option>
          <option value="email_sent">Email Sent</option>
          <option value="content_created">Content Created</option>
          <option value="call_booked">Call Booked</option>
          <option value="deal_closed">Deal Closed</option>
          <option value="ticket_resolved">Ticket Resolved</option>
          <option value="custom">Custom</option>
        </select>
      </div>
      <div class="form-group"><label>Agent / Source</label><input id="metric-agent" placeholder="e.g. lead-hunter"/></div>
      <div class="form-group"><label>Value (€, optional)</label><input id="metric-value" type="number" placeholder="e.g. 500" min="0"/></div>
      <div class="form-group"><label>Notes (optional)</label><input id="metric-notes" placeholder="e.g. Closed deal with Acme Corp"/></div>
      <button class="btn btn-success" onclick="recordMetric()">📊 Record Event</button>
    </div>
  </div>
</div>

<!-- ── Templates ── -->
<div id="tab-templates" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Agent Templates</div>
      <button class="btn btn-ghost btn-sm" onclick="loadTemplates()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:16px">
      Pre-built plug-and-play templates for common business use-cases. One click to deploy a full AI team.
    </p>
    <div id="templates-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px">
      <div class="empty"><div class="icon">📋</div><p>Loading templates…</p></div>
    </div>
  </div>
</div>

<!-- ── Guardrails ── -->
<div id="tab-guardrails" class="tab-content">
  <div class="grid-stat">
    <div class="stat-card">
      <div class="stat-icon yellow">⏳</div>
      <div class="stat-body"><div class="val" id="g-pending">–</div><div class="lbl">Pending Approvals</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon green">✅</div>
      <div class="stat-body"><div class="val" id="g-approved">–</div><div class="lbl">Approved (total)</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon blue">🚫</div>
      <div class="stat-body"><div class="val" id="g-rejected">–</div><div class="lbl">Rejected (total)</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">📋</div>
      <div class="stat-body"><div class="val" id="g-total">–</div><div class="lbl">All Actions Logged</div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⏳</span> Pending Approvals</div>
        <button class="btn btn-ghost btn-sm" onclick="loadGuardrails()">↻ Refresh</button>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
        High-risk actions require manual confirmation before execution.
        <strong style="color:var(--warning)">Review carefully before approving.</strong>
      </p>
      <div id="guardrails-pending"><div class="empty"><div class="icon">✅</div><p>No pending approvals. All clear!</p></div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📋</span> Action Log</div>
        <button class="btn btn-ghost btn-sm" onclick="loadGuardrails()">↻ Refresh</button>
      </div>
      <div id="guardrails-log"><div class="empty"><div class="icon">📋</div><p>No actions logged yet.</p></div></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">⚙️</span> Guardrail Settings</div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">Configure which actions require approval and rate limits per agent.</p>
    <div class="grid2">
      <div>
        <div class="section-title">Actions Requiring Approval</div>
        <div id="guardrail-settings-list" style="font-size:.88em">
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-send-email" checked /> Send bulk emails
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-social-post" checked /> Post to social media
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-make-purchase" checked /> Make purchases / place orders
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
            <input type="checkbox" id="gr-delete-data" checked /> Delete or modify data
          </label>
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0">
            <input type="checkbox" id="gr-api-calls" /> External API calls with side-effects
          </label>
        </div>
      </div>
      <div>
        <div class="section-title">Rate Limits</div>
        <div class="form-group"><label>Max emails / day</label><input id="rl-emails" type="number" value="200" min="1"/></div>
        <div class="form-group"><label>Max social posts / day</label><input id="rl-posts" type="number" value="10" min="1"/></div>
        <div class="form-group"><label>Max API calls / hour</label><input id="rl-api" type="number" value="100" min="1"/></div>
        <button class="btn btn-primary" onclick="saveGuardrailSettings()">💾 Save Settings</button>
      </div>
    </div>
  </div>
</div>

<!-- ── Memory ── -->
<div id="tab-memory" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">👥</span> Client Memory</div>
        <button class="btn btn-ghost btn-sm" onclick="loadMemory()">↻ Refresh</button>
      </div>
      <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">The AI remembers your clients across all conversations and tasks.</p>
      <div id="memory-clients"><div class="empty"><div class="icon">👥</div><p>No clients remembered yet.</p></div></div>
    </div>

    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">➕</span> Add Client</div>
        </div>
        <div class="form-group"><label>Name</label><input id="mem-name" placeholder="e.g. John Smith"/></div>
        <div class="form-group"><label>Company</label><input id="mem-company" placeholder="e.g. Acme Corp"/></div>
        <div class="form-group"><label>Email</label><input id="mem-email" type="email" placeholder="john@acme.com"/></div>
        <div class="form-group">
          <label>Status</label>
          <select id="mem-status">
            <option value="prospect">Prospect</option>
            <option value="lead">Lead</option>
            <option value="customer">Customer</option>
            <option value="churned">Churned</option>
          </select>
        </div>
        <div class="form-group"><label>Notes</label><textarea id="mem-notes" rows="3" placeholder="Any important context…"></textarea></div>
        <button class="btn btn-success" onclick="addClient()">➕ Add Client</button>
      </div>

      <div class="card" style="margin-top:0">
        <div class="card-header">
          <div class="card-title"><span class="icon">📝</span> Recent Interactions</div>
        </div>
        <div id="memory-recent"><div class="empty"><div class="icon">📝</div><p>No recent interactions.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Integrations ── -->
<div id="tab-integrations" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🔌</span> Integrations</div>
      <button class="btn btn-ghost btn-sm" onclick="loadIntegrations()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:16px">
      Connect your tools and services. The AI uses these integrations to take real actions across your business.
    </p>
    <div id="integrations-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px">
      <div class="empty"><div class="icon">🔌</div><p>Loading integrations…</p></div>
    </div>
  </div>
</div>

<!-- ── History ── -->
<div id="tab-history" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🕐</span> Activity History</div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn btn-ghost btn-sm" onclick="loadHistory()">↻ Refresh</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--danger)"
                onclick="clearHistory()">🗑️ Clear</button>
      </div>
    </div>
    <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
      A persistent log of all agent activities, security checks, settings changes and more — from all time.
    </p>

    <!-- Filter bar -->
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;align-items:center">
      <input id="history-search" placeholder="🔍 Search…"
             style="flex:1;min-width:160px;max-width:280px;font-size:.84em"
             oninput="filterHistory()"/>
      <select id="history-type-filter" style="font-size:.84em;min-width:160px"
              onchange="filterHistory()">
        <option value="">All event types</option>
        <option value="security_check">🛡️ Security Check</option>
        <option value="security_action_done">✅ Security Action</option>
        <option value="settings_saved">⚙️ Settings Saved</option>
        <option value="guardrail_approved">✅ Guardrail Approved</option>
        <option value="guardrail_rejected">🚫 Guardrail Rejected</option>
        <option value="agent_command">💬 Agent Command</option>
        <option value="task_run">🚀 Task Run</option>
        <option value="worker_triggered">👷 Worker</option>
        <option value="system">ℹ️ System</option>
      </select>
      <select id="history-source-filter" style="font-size:.84em;min-width:140px"
              onchange="filterHistory()">
        <option value="">All sources</option>
        <option value="chat">Chat</option>
        <option value="dashboard">Dashboard</option>
        <option value="guardrails">Guardrails</option>
        <option value="security-checklist">Security</option>
        <option value="system">System</option>
      </select>
      <span id="history-count" style="font-size:.78em;color:var(--text-muted);white-space:nowrap"></span>
    </div>

    <div id="history-timeline">
      <div class="empty"><div class="icon">🕐</div><p>Loading history…</p></div>
    </div>
  </div>
</div>

<!-- ── Options ── -->
<div id="tab-options" class="tab-content">
  <div class="grid2">

    <!-- Left column: API Keys -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔑</span> API Keys</div>
          <button class="btn btn-ghost btn-sm" onclick="loadOptions()">↻ Refresh</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Secret values are masked. Paste a new value to update; leave unchanged to keep existing.
        </p>
        <div id="opt-api-keys"></div>
        <button class="btn btn-primary" style="margin-top:10px;width:100%" onclick="saveSettings('api_keys')">💾 Save API Keys</button>
      </div>
    </div>

    <!-- Right column -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">⚙️</span> Preferences</div>
        </div>
        <div id="opt-preferences"></div>
        <button class="btn btn-primary" style="margin-top:10px;width:100%" onclick="saveSettings('preferences')">💾 Save Preferences</button>
      </div>

      <!-- Auto-Update -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔄</span> Auto Update</div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="checkForUpdates()">🔍 Check Now</button>
            <button class="btn btn-success btn-sm" onclick="triggerUpdate()">⬇ Update Now</button>
          </div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:12px">
          The bot auto-updates from GitHub while running. Only changed bots are restarted — the rest stay live.
        </p>
        <div id="opt-updater-status" style="font-size:.84em"></div>
      </div>

      <!-- Security Check -->
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🛡️</span> Security Checklist</div>
          <button class="btn btn-ghost btn-sm" onclick="runSecurityCheck()">↻ Re-run</button>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:4px">
          <strong style="color:var(--text)">Before running in production</strong> — verify all 11 points below.
        </p>
        <ol style="color:var(--text-muted);font-size:.78em;margin:0 0 12px 16px;padding:0;line-height:1.8">
          <li>JWT_SECRET_KEY changed from the default placeholder</li>
          <li>Strong passwords configured</li>
          <li>Application bound to localhost only (or properly secured if networked)</li>
          <li>Rate limiting enabled <code style="font-size:.9em">security.rate_limit_enabled: true</code></li>
          <li>Encryption at rest enabled <code style="font-size:.9em">privacy.encrypt_data_at_rest: true</code></li>
          <li>Telemetry disabled <code style="font-size:.9em">privacy.telemetry_enabled: false</code></li>
          <li>Audit logging enabled <code style="font-size:.9em">logging.audit_enabled: true</code></li>
          <li>Security headers verified <code style="font-size:.9em">curl -I http://127.0.0.1:8787</code></li>
          <li>Dependencies updated <code style="font-size:.9em">pip install -r requirements.txt --upgrade</code></li>
          <li>File permissions secured <code style="font-size:.9em">chmod 600 .env security.local.yml</code></li>
          <li>No secrets committed to version control</li>
        </ol>
        <div id="opt-security-results"><p style="color:var(--text-muted);font-size:.85em">Loading…</p></div>
      </div>

      <!-- Danger Zone -->
      <div class="card" style="border-color:rgba(239,68,68,.35)">
        <div class="card-header">
          <div class="card-title" style="color:var(--danger)"><span class="icon">💣</span> Danger Zone</div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Permanently delete all runtime data — chat logs, metrics, memory, guardrails, improvements.
          Your <code>.env</code> and config files are <strong style="color:var(--text)">not</strong> deleted.
        </p>
        <div class="form-group">
          <label>Type <strong style="color:var(--danger)">DELETE ALL DATA</strong> to confirm</label>
          <input id="nuke-confirm" placeholder="DELETE ALL DATA" style="border-color:rgba(239,68,68,.3)" autocomplete="off"/>
        </div>
        <button class="btn btn-danger" style="width:100%" onclick="nukeData()">🗑️ Delete All Runtime Data</button>
        <div id="nuke-result" style="margin-top:8px;font-size:.82em"></div>
      </div>

      <!-- Delete Complete Bot -->
      <div class="card" style="border-color:rgba(239,68,68,.6);margin-top:0">
        <div class="card-header">
          <div class="card-title" style="color:var(--danger)"><span class="icon">☠️</span> Delete Complete Bot</div>
        </div>
        <p style="color:var(--text-muted);font-size:.84em;margin-bottom:14px">
          Stops all running bots and <strong style="color:var(--danger)">permanently removes</strong>
          the entire <code>~/.ai-employee</code> installation — all data, config, and code.
          <strong style="color:var(--text)">This cannot be undone.</strong>
        </p>

        <!-- Step 1 -->
        <div id="uninstall-step1">
          <div class="form-group" style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <input type="checkbox" id="uninstall-check1" style="width:auto;margin:0;cursor:pointer;accent-color:var(--danger)"/>
            <label for="uninstall-check1" style="margin:0;font-size:.86em;cursor:pointer">
              I understand this will <strong style="color:var(--danger)">permanently delete</strong> everything
            </label>
          </div>
          <div class="form-group" style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <input type="checkbox" id="uninstall-check2" style="width:auto;margin:0;cursor:pointer;accent-color:var(--danger)"/>
            <label for="uninstall-check2" style="margin:0;font-size:.86em;cursor:pointer">
              I have backed up anything I want to keep
            </label>
          </div>
          <button class="btn btn-danger" style="width:100%" onclick="deleteBotStep2()">
            ☠️ Continue to Final Confirmation…
          </button>
        </div>

        <!-- Step 2 (hidden until step 1 passes) -->
        <div id="uninstall-step2" style="display:none;border-top:1px solid rgba(239,68,68,.3);padding-top:14px;margin-top:14px">
          <div class="form-group">
            <label>Type <strong style="color:var(--danger)">UNINSTALL AI EMPLOYEE</strong> to confirm</label>
            <input id="uninstall-confirm" placeholder="UNINSTALL AI EMPLOYEE"
              style="border-color:rgba(239,68,68,.5);background:rgba(239,68,68,.05)"
              autocomplete="off"/>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" style="flex:1" onclick="deleteBotCancel()">↩ Cancel</button>
            <button class="btn btn-danger" style="flex:2" onclick="deleteBotFinal()">
              ☠️ PERMANENTLY DELETE EVERYTHING
            </button>
          </div>
        </div>

        <div id="uninstall-result" style="margin-top:10px;font-size:.82em"></div>
      </div>
    </div>

  </div>
</div>

</main>

<div id="toast"></div>

<script nonce="__CSP_NONCE__">
let currentTab = 'dashboard';
const _startTime = Date.now();

function switchTab(tab, btn) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  btn.classList.add('active');
  currentTab = tab;
  if (tab === 'dashboard') loadDashboard();
  if (tab === 'chat') loadChatLog();
  if (tab === 'scheduler') loadSchedules();
  if (tab === 'workers') { loadWorkers(); if (!_allAgents.length) loadSwarm(); }
  if (tab === 'improvements') loadImprovements();
  if (tab === 'skills') loadSkills();
  if (tab === 'tasks') loadTasks();
  if (tab === 'swarm') loadSwarm();
  if (tab === 'commands') loadCommandsTab();
  if (tab === 'metrics') loadMetrics();
  if (tab === 'templates') loadTemplates();
  if (tab === 'guardrails') loadGuardrails();
  if (tab === 'memory') loadMemory();
  if (tab === 'integrations') loadIntegrations();
  if (tab === 'history') loadHistory();
  if (tab === 'options') { loadOptions(); loadUpdaterStatus(); runSecurityCheck(); }
}

function toast(msg, color='#10b981') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = color;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

async function api(path, opts={}) {
  try {
    const r = await fetch(path, opts);
    return r.json();
  } catch(e) {
    return {error: String(e)};
  }
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// Escape a value for safe embedding inside a JS string literal (single-quoted onclick="…")
function jsEsc(str) {
  return String(str ?? '').replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'\\"');
}

// ── Animated count-up helper ─────────────────────────────────────────────────
function animateCount(id, target) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = parseInt(el.textContent) || 0;
  if (prev === target) return;
  const duration = 500;
  const startTime = performance.now();
  const diff = target - prev;
  const round = diff >= 0 ? Math.ceil : Math.floor;
  function step(now) {
    const elapsed = Math.min(now - startTime, duration);
    const eased = 1 - Math.pow(1 - elapsed / duration, 3);
    el.textContent = round(prev + diff * eased);
    if (elapsed < duration) requestAnimationFrame(step);
    else el.textContent = target;
  }
  requestAnimationFrame(step);
}

// ── Disable / re-enable all start-stop controls during action ────────────────
function _setStartStopDisabled(disabled) {
  ['hero-start-btn','hero-stop-btn','hdr-start-btn','hdr-stop-btn'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = disabled;
  });
}

async function loadDashboard() {
  const d = await api('/api/status');
  const bots = d.bots || [];
  const running = bots.filter(b => b.running).length;
  const total = bots.length;

  // Animate stat numbers
  animateCount('stat-running', running);
  animateCount('stat-total', total);
  document.getElementById('header-sub').textContent = `${running}/${total} bots running`;

  // Update system control hero
  const pct = total > 0 ? Math.round((running / total) * 100) : 0;
  const healthBar = document.getElementById('health-bar');
  const sysRing = document.getElementById('sys-ring');
  const sysControlSub = document.getElementById('sys-control-sub');
  healthBar.style.width = pct + '%';
  healthBar.className = 'health-bar-fill' + (pct < 40 ? ' danger' : pct < 70 ? ' warn' : '');
  document.getElementById('health-label-right').textContent = pct + '%';
  document.getElementById('health-label-left').textContent = running + ' / ' + total + ' running';
  if (pct === 0 && total > 0) {
    sysRing.classList.add('offline');
    sysControlSub.textContent = 'All bots stopped — click Start All to launch';
  } else if (pct === 100) {
    sysRing.classList.remove('offline');
    sysControlSub.textContent = 'All systems operational ✓';
  } else if (total === 0) {
    sysRing.classList.add('offline');
    sysControlSub.textContent = 'No bot state data yet — start bots first';
  } else {
    sysRing.classList.remove('offline');
    sysControlSub.textContent = `${running} of ${total} bots active`;
  }

  // Uptime
  const secs = Math.floor((Date.now() - _startTime) / 1000);
  document.getElementById('stat-uptime').textContent =
    secs < 60 ? secs + 's' : secs < 3600 ? Math.floor(secs/60) + 'm' : Math.floor(secs/3600) + 'h';

  // Gateway status (try to ping)
  fetch('http://localhost:18789', {mode:'no-cors',signal:AbortSignal.timeout(1500)})
    .then(() => document.getElementById('stat-gateway').textContent = 'Online')
    .catch(() => document.getElementById('stat-gateway').textContent = 'Offline');

  const el = document.getElementById('bot-status-list');
  if (!bots.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🤖</div><p>No bot state data yet. Start the bots first.</p></div>';
  } else {
    el.innerHTML = bots.map(b => {
      const cls = b.running ? 'on' : 'off';
      const lbl = b.running ? 'running' : 'stopped';
      return `<div class="bot-row">
        <div class="dot ${cls}"></div>
        <span class="bot-name">${b.bot}</span>
        <span class="badge ${lbl}">${lbl}</span>
      </div>`;
    }).join('');
  }

  const sys = await api('/api/doctor');
  document.getElementById('system-info').textContent = sys.output || '(no output)';
}

async function startAll() {
  _setStartStopDisabled(true);
  // Update hero button text to show loading state
  const heroBtn = document.getElementById('hero-start-btn');
  if (heroBtn) heroBtn.innerHTML = '<span class="spinner">⟳</span> Starting…';
  await api('/api/bots/start-all', {method:'POST'});
  toast('▶ Starting all bots…');
  setTimeout(() => {
    loadDashboard();
    _setStartStopDisabled(false);
    if (heroBtn) heroBtn.innerHTML = '<span class="btn-icon">▶</span> Start All Bots';
  }, 2500);
}

async function stopAll() {
  if (!confirm('Stop all running bots?')) return;
  _setStartStopDisabled(true);
  const heroBtn = document.getElementById('hero-stop-btn');
  if (heroBtn) heroBtn.innerHTML = '<span class="spinner">⟳</span> Stopping…';
  await api('/api/bots/stop-all', {method:'POST'});
  toast('■ Stopping all bots…', '#ef4444');
  setTimeout(() => {
    loadDashboard();
    _setStartStopDisabled(false);
    if (heroBtn) heroBtn.innerHTML = '<span class="btn-icon">■</span> Stop All Bots';
  }, 2000);
}

// ── Chat ────────────────────────────────────────────────────────────────────
async function loadChatLog() {
  const data = await api('/api/chat');
  const log = document.getElementById('chat-log');
  const msgs = data.messages || [];
  if (!msgs.length) {
    log.innerHTML = '<div class="empty"><div class="icon">💬</div><p>No messages yet.</p></div>';
    return;
  }
  log.innerHTML = msgs.slice(-60).map(m => {
    const type = m.type === 'user' ? 'user' : 'bot';
    const raw = m.message || m.question || JSON.stringify(m);
    // HTML-escape to prevent XSS, then convert newlines to <br>
    const text = raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                    .replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/\n/g,'<br>');
    const ts = (m.ts||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div class="chat-msg ${type}"><div>${text}</div><div class="ts">${ts}</div></div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  await api('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message: q})});
  loadChatLog();
}

// ── Scheduler ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('sched-action').addEventListener('change', function() {
    document.getElementById('sched-bot-row').style.display = (this.value==='start_bot'||this.value==='stop_bot') ? '' : 'none';
  });
  document.getElementById('sched-type').addEventListener('change', function() {
    document.getElementById('sched-interval-row').style.display = this.value==='interval' ? '' : 'none';
    document.getElementById('sched-daily-row').style.display = this.value==='daily' ? '' : 'none';
  });
});

async function loadSchedules() {
  const data = await api('/api/schedules');
  const tasks = data.tasks || [];
  const el = document.getElementById('schedule-list');
  if (!tasks.length) { el.innerHTML = '<div class="empty"><div class="icon">📅</div><p>No scheduled tasks yet.</p></div>'; return; }
  el.innerHTML = tasks.map(t => {
    const info = t.type==='interval' ? `every ${t.interval_minutes||60}m` : `daily at ${t.run_at_utc||'?'} UTC`;
    const enabled = t.enabled !== false;
    return `<div class="sched-row">
      <div class="sched-info">
        <h4>${t.label||t.id} <span class="badge ${enabled?'enabled':'disabled'}">${enabled?'enabled':'disabled'}</span></h4>
        <p>${t.action} · ${info}</p>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteSchedule('${t.id}')">✕</button>
    </div>`;
  }).join('');
}

async function addSchedule() {
  const id = document.getElementById('sched-id').value.trim();
  const label = document.getElementById('sched-label').value.trim();
  const action = document.getElementById('sched-action').value;
  const bot = document.getElementById('sched-bot').value.trim();
  const msg = document.getElementById('sched-msg').value.trim();
  const type = document.getElementById('sched-type').value;
  const interval = parseInt(document.getElementById('sched-interval').value) || 60;
  const dailyTime = document.getElementById('sched-daily-time').value.trim();

  if (!id || !label) { toast('ID and label are required', '#ef4444'); return; }

  const task = {id, label, action, type, enabled: true,
    ...(bot && {bot}), ...(msg && {message: msg}),
    ...(type==='interval' && {interval_minutes: interval}),
    ...(type==='daily' && {run_at_utc: dailyTime||'08:00'}),
  };

  const r = await api('/api/schedules', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(task)});
  if (r.ok) { toast('Task added!'); loadSchedules(); }
  else { toast(r.error||'Error', '#ef4444'); }
}

async function deleteSchedule(id) {
  if (!confirm(`Delete task "${id}"?`)) return;
  const r = await api(`/api/schedules/${id}`, {method:'DELETE'});
  if (r.ok) { toast('Task deleted'); loadSchedules(); }
}

// ── Workers ─────────────────────────────────────────────────────────────────
// ── Bundle management ───────────────────────────────────────────────────────
let _wfSelectedAgents = new Set();

async function loadWorkers() {
  // Load bundles
  const bd = await api('/api/workers/bundles');
  const bundles = (bd && bd.bundles) || [];
  const bundleEl = document.getElementById('bundle-list');
  if (!bundles.length) {
    bundleEl.innerHTML = '<div class="empty"><div class="icon">🏭</div><p>No worker bundles yet. Click <strong>+ New Worker</strong> to create one.</p></div>';
  } else {
    bundleEl.innerHTML = bundles.map(b => {
      const enabled = b.enabled !== false;
      const statusColor = enabled ? '#10b981' : '#64748b';
      const agents = (b.agents || []).map(a => `<span style="background:var(--surface2);padding:1px 6px;border-radius:3px;font-size:.73em">${escHtml(a)}</span>`).join(' ');
      const schedMap = {continuous:'🔄 Continuous', hourly:'⏰ Hourly', every6h:'⏰ Every 6h', daily:'🌙 Daily 2AM', '3x_daily':'☀️ 3× Daily', weekly:'📅 Weekly', manual:'🖱 Manual'};
      const schedLabel = schedMap[b.schedule] || b.schedule || 'manual';
      const lastRun = b.last_run ? `Last: ${b.last_run.split('T')[0]}` : 'Never run';
      return `<div style="border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin-bottom:10px;border-left:4px solid ${statusColor}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <div style="flex:1">
            <div style="font-weight:700;font-size:.95em;display:flex;align-items:center;gap:6px">
              🏭 ${escHtml(b.name)}
              <span style="font-size:.72em;background:${statusColor};color:#fff;border-radius:3px;padding:1px 6px">${enabled ? 'enabled' : 'disabled'}</span>
              <span style="font-size:.72em;color:var(--text-muted)">${schedLabel}</span>
            </div>
            <div style="font-size:.82em;color:var(--text-secondary);margin:4px 0">${escHtml(b.description || b.task_description || '')}</div>
            <div style="font-size:.8em;color:var(--text-muted);margin-bottom:6px;line-height:1.5">${escHtml((b.task_description||'').slice(0,120))}${(b.task_description||'').length>120?'…':''}</div>
            <div style="display:flex;flex-wrap:wrap;gap:3px">${agents}</div>
            <div style="font-size:.72em;color:var(--text-muted);margin-top:5px">${lastRun}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;min-width:90px">
            <button class="btn btn-primary btn-sm" onclick="runBundle('${escHtml(b.id)}')">▶ Run</button>
            <button class="btn btn-ghost btn-sm" onclick="editBundle(${escHtml(JSON.stringify(b))})">✏️ Edit</button>
            <button class="btn btn-ghost btn-sm" onclick="toggleBundle('${escHtml(b.id)}', ${!enabled})">${enabled ? '⏸ Disable' : '▶ Enable'}</button>
            <button class="btn btn-danger btn-sm" onclick="deleteBundle('${escHtml(b.id)}')">🗑</button>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  // Load bot workers
  const wd = await api('/api/workers');
  const bots = (wd && wd.bots) || [];
  const el = document.getElementById('worker-list');
  if (!bots.length) { el.innerHTML = '<div class="empty"><div class="icon">👷</div><p>No bots found.</p></div>'; return; }
  el.innerHTML = bots.map(b => {
    const cls = b.running ? 'on' : 'off';
    const lbl = b.running ? 'running' : 'stopped';
    const startBtn = b.running ? '' : `<button class="btn btn-success btn-sm" onclick="startBot('${b.name}')">▶ Start</button>`;
    const stopBtn = b.running ? `<button class="btn btn-danger btn-sm" onclick="stopBot('${b.name}')">■ Stop</button>` : '';
    return `<div class="sched-row">
      <div class="dot ${cls}" style="margin-top:4px;flex-shrink:0"></div>
      <div class="sched-info"><h4>${b.name} <span class="badge ${lbl}">${lbl}</span></h4></div>
      <div style="display:flex;gap:6px">${startBtn}${stopBtn}</div>
    </div>`;
  }).join('');
}

function openCreateWorker(prefill) {
  document.getElementById('wf-editing-id').value = '';
  document.getElementById('wf-name').value = (prefill && prefill.name) || '';
  document.getElementById('wf-task').value = (prefill && prefill.task_description) || '';
  document.getElementById('wf-desc').value = (prefill && prefill.description) || '';
  document.getElementById('wf-schedule').value = (prefill && prefill.schedule) || 'continuous';
  document.getElementById('worker-form-title').textContent = 'Create Worker Bundle';
  document.getElementById('wf-save-btn').textContent = '💾 Save Worker';
  document.getElementById('wf-save-result').textContent = '';
  _wfSelectedAgents = new Set((prefill && prefill.agents) || []);
  renderWfAgentGrid();
  document.getElementById('worker-form-card').style.display = 'block';
  document.getElementById('worker-form-card').scrollIntoView({behavior:'smooth', block:'start'});
}

function editBundle(b) {
  openCreateWorker(b);
  document.getElementById('wf-editing-id').value = b.id;
  document.getElementById('worker-form-title').textContent = 'Edit Worker Bundle';
  document.getElementById('wf-save-btn').textContent = '💾 Update Worker';
}

function closeWorkerForm() {
  document.getElementById('worker-form-card').style.display = 'none';
  _wfSelectedAgents.clear();
}

function renderWfAgentGrid() {
  const grid = document.getElementById('wf-agent-grid');
  if (!_allAgents.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:.82em">Agents not loaded yet. Open Tasks tab first to load agent list.</p>';
    return;
  }
  grid.innerHTML = _allAgents.map(a => {
    const sel = _wfSelectedAgents.has(a.id);
    const color = _catColors[a.category] || '#64748b';
    return `<div id="wfcard-${a.id}" onclick="toggleWfAgent('${escHtml(a.id)}')"
      style="cursor:pointer;border:2px solid ${sel ? color : 'var(--border)'};border-radius:var(--radius-sm);padding:6px;background:${sel ? 'var(--surface2)' : 'var(--surface)'};transition:all .15s">
      <div style="font-size:.75em;font-weight:600;color:${sel ? color : 'var(--text)'}">${escHtml(a.id)}</div>
      <div style="font-size:.65em;color:var(--text-muted)">${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
  document.getElementById('wf-agent-count').textContent = `(${_wfSelectedAgents.size} selected)`;
}

function toggleWfAgent(id) {
  if (_wfSelectedAgents.has(id)) _wfSelectedAgents.delete(id);
  else _wfSelectedAgents.add(id);
  const a = _allAgents.find(x => x.id === id);
  const card = document.getElementById('wfcard-' + id);
  if (!card || !a) return;
  const sel = _wfSelectedAgents.has(id);
  const color = _catColors[a.category] || '#64748b';
  card.style.border = `2px solid ${sel ? color : 'var(--border)'}`;
  card.style.background = sel ? 'var(--surface2)' : 'var(--surface)';
  card.querySelector('div').style.color = sel ? color : 'var(--text)';
  document.getElementById('wf-agent-count').textContent = `(${_wfSelectedAgents.size} selected)`;
}

function wfSelectAll() { _allAgents.forEach(a => _wfSelectedAgents.add(a.id)); renderWfAgentGrid(); }
function wfClearAll()  { _wfSelectedAgents.clear(); renderWfAgentGrid(); }

function presetEcomWorker() {
  const preset = {
    name: 'E-commerce Automation Worker',
    description: 'Full 100% automated e-commerce operation — orders, support, inventory, marketing, and reporting.',
    task_description: 'Run the full e-commerce automation pipeline: process new orders via Shopify webhook, handle customer support tickets, sync inventory with supplier, run email marketing campaigns, post to social media, research new products, and generate daily P&L reports.',
    schedule: 'continuous',
    agents: ['order-processor','support-bot','bookkeeper','inventory-sync','email-marketer','social-poster','product-researcher','ecom-dashboard']
  };
  openCreateWorker(preset);
  toast('E-commerce preset loaded! Adjust agents and save.', '#10b981');
}

async function saveWorkerBundle() {
  const name = document.getElementById('wf-name').value.trim();
  const task_description = document.getElementById('wf-task').value.trim();
  const description = document.getElementById('wf-desc').value.trim();
  const schedule = document.getElementById('wf-schedule').value;
  const agents = [..._wfSelectedAgents];
  const editingId = document.getElementById('wf-editing-id').value.trim();
  const resultEl = document.getElementById('wf-save-result');

  if (!name) { toast('Worker name is required', '#ef4444'); return; }
  if (!task_description) { toast('Task description is required', '#ef4444'); return; }
  if (!agents.length) { toast('Select at least one agent', '#ef4444'); return; }

  resultEl.textContent = '⏳ Saving…';
  const payload = {name, description, task_description, schedule, agents, enabled: true};

  let r;
  if (editingId) {
    r = await api(`/api/workers/bundles/${editingId}`, {method:'PATCH', body: JSON.stringify(payload)});
  } else {
    r = await api('/api/workers/bundles', {method:'POST', body: JSON.stringify(payload)});
  }

  if (r && r.ok !== false) {
    resultEl.innerHTML = `<span style="color:var(--success)">✅ Worker ${editingId ? 'updated' : 'created'}!</span>`;
    setTimeout(() => { closeWorkerForm(); loadWorkers(); }, 800);
  } else {
    resultEl.innerHTML = `<span style="color:var(--danger)">❌ Save failed. Check API.</span>`;
  }
}

async function runBundle(id) {
  const r = await api(`/api/workers/bundles/${id}/run`, {method:'POST'});
  if (r && r.ok !== false) toast('Worker triggered ▶', '#10b981');
  else toast('Run failed', '#ef4444');
  setTimeout(loadWorkers, 1500);
}

async function toggleBundle(id, enabled) {
  const r = await api(`/api/workers/bundles/${id}`, {method:'PATCH', body: JSON.stringify({enabled})});
  if (r && r.ok !== false) toast(enabled ? 'Worker enabled ✅' : 'Worker disabled ⏸', enabled ? '#10b981' : '#f59e0b');
  else toast('Update failed', '#ef4444');
  loadWorkers();
}

async function deleteBundle(id) {
  if (!confirm('Delete this worker bundle?')) return;
  const r = await api(`/api/workers/bundles/${id}`, {method:'DELETE'});
  if (r && r.ok !== false) { toast('Worker deleted', '#ef4444'); loadWorkers(); }
  else toast('Delete failed', '#ef4444');
}

async function startBot(name) {
  await api('/api/bots/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Starting ${name}…`);
  setTimeout(loadWorkers, 1800);
}

async function stopBot(name) {
  if (!confirm(`Stop ${name}?`)) return;
  await api('/api/bots/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Stopping ${name}…`, '#ef4444');
  setTimeout(loadWorkers, 1800);
}

// ── Improvements ────────────────────────────────────────────────────────────
async function loadImprovements() {
  const data = await api('/api/improvements');
  const items = data.improvements || [];
  const el = document.getElementById('improvement-list');
  if (!items.length) { el.innerHTML = '<div class="empty"><div class="icon">💡</div><p>No proposals yet. The discovery bot will add them over time.</p></div>'; return; }
  el.innerHTML = items.map(imp => `
    <div class="improv-row">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <h4>${imp.title||imp.id} <span class="badge ${imp.status||'pending'}">${imp.status||'pending'}</span></h4>
        ${imp.status==='pending' ? `<div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn btn-success btn-sm" onclick="reviewImprovement('${imp.id}','approved')">✓ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="reviewImprovement('${imp.id}','rejected')">✕ Reject</button>
        </div>` : ''}
      </div>
      <p>${imp.description||''}</p>
      ${imp.agent ? `<p style="font-size:.78em;color:var(--primary);margin-top:4px">Agent: ${imp.agent} · Type: ${imp.type||'?'} · Effort: ${imp.effort||'?'}</p>` : ''}
    </div>`).join('');
}

async function reviewImprovement(id, decision) {
  const r = await api(`/api/improvements/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: decision})});
  if (r.ok) { toast(decision==='approved' ? '✓ Approved' : '✕ Rejected', decision==='approved'?'#10b981':'#ef4444'); loadImprovements(); }
}

// ── Skills ───────────────────────────────────────────────────────────────────
let allSkills = [];
let selectedSkillIds = new Set();
let activeCategory = '';

const CAT_COLORS = {
  'Content & Writing':'#f472b6','Research & Analysis':'#60a5fa',
  'Trading & Finance':'#34d399','Social Media':'#fb923c',
  'Lead Generation & Sales':'#a78bfa','Customer Support':'#fbbf24',
  'Development & Technical':'#22d3ee','Data Analysis':'#4ade80',
  'E-commerce & Product':'#f87171','Marketing & SEO':'#c084fc',
  'Automation & Productivity':'#e2e8f0',
};

async function loadSkills() {
  const data = await api('/api/skills');
  allSkills = data.skills || [];
  document.getElementById('skill-total-badge').textContent = `(${allSkills.length})`;
  renderCategoryPills(data.categories || []);
  renderSkillGrid(allSkills);
  loadAgents();
}

function renderCategoryPills(cats) {
  const el = document.getElementById('category-pills');
  el.innerHTML = `<span class="cat-pill active" onclick="setCat('',this)">All</span>` +
    cats.map(c => `<span class="cat-pill" onclick="setCat(${JSON.stringify(c)},this)">${c}</span>`).join('');
}

function setCat(cat, btn) {
  activeCategory = cat;
  document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  filterSkills();
}

function filterSkills() {
  const q = (document.getElementById('skill-search').value || '').toLowerCase();
  const filtered = allSkills.filter(s => {
    const catMatch = !activeCategory || s.category === activeCategory;
    const textMatch = !q || s.id.includes(q) || s.name.toLowerCase().includes(q) ||
                      s.description.toLowerCase().includes(q) ||
                      (s.tags||[]).some(t => t.toLowerCase().includes(q));
    return catMatch && textMatch;
  });
  renderSkillGrid(filtered);
}

function renderSkillGrid(skills) {
  const el = document.getElementById('skill-grid');
  if (!skills.length) { el.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>No skills match.</p></div>'; return; }
  el.innerHTML = skills.map(s => {
    const color = CAT_COLORS[s.category] || '#94a3b8';
    const sel = selectedSkillIds.has(s.id);
    const tags = (s.tags||[]).slice(0,4).map(t=>`<span class="tag">${t}</span>`).join('');
    return `<div class="skill-card${sel?' selected':''}" onclick="toggleSkill(${JSON.stringify(s.id)},this)">
      <h5>${s.name} <span style="color:${color};font-size:.72em;font-weight:500">${s.category}</span></h5>
      <p>${s.description.slice(0,110)}${s.description.length>110?'…':''}</p>
      <div class="tags">${tags}</div>
    </div>`;
  }).join('');
}

function toggleSkill(id, card) {
  if (selectedSkillIds.has(id)) { selectedSkillIds.delete(id); card.classList.remove('selected'); }
  else { selectedSkillIds.add(id); card.classList.add('selected'); }
  updateSelectedPanel();
}

function updateSelectedPanel() {
  const count = selectedSkillIds.size;
  document.getElementById('selected-count').textContent = `(${count})`;
  const el = document.getElementById('selected-skills-list');
  if (!count) { el.textContent = 'No skills selected. Click cards on the left.'; return; }
  el.innerHTML = [...selectedSkillIds].map(id => {
    const s = allSkills.find(x => x.id === id);
    return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 4px 2px 0;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.8em">
      ${s ? s.name : id}
      <span onclick="selectedSkillIds.delete(${JSON.stringify(id)});updateSelectedPanel();filterSkills();"
        style="cursor:pointer;color:var(--danger);font-weight:bold;margin-left:2px">×</span>
    </span>`;
  }).join('');
}

async function createAgent() {
  const name = document.getElementById('agent-name-input').value.trim();
  const desc = document.getElementById('agent-desc-input').value.trim();
  if (!name) { toast('Agent name is required', '#ef4444'); return; }
  if (!selectedSkillIds.size) { toast('Select at least one skill', '#ef4444'); return; }
  const r = await api('/api/agents/custom', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, description: desc, skills: [...selectedSkillIds]}),
  });
  if (r.ok) {
    toast(`Agent "${name}" created with ${r.skill_count} skills!`);
    document.getElementById('agent-name-input').value = '';
    document.getElementById('agent-desc-input').value = '';
    selectedSkillIds.clear();
    updateSelectedPanel();
    filterSkills();
    loadAgents();
  } else { toast(r.error || 'Error creating agent', '#ef4444'); }
}

async function loadAgents() {
  const data = await api('/api/agents/custom');
  const agents = data.agents || [];
  const el = document.getElementById('agents-list');
  if (!agents.length) { el.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No agents yet. Create one above.</p></div>'; return; }
  el.innerHTML = agents.map(a => `
    <div class="agent-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <h4>${a.name}</h4>
        <button class="btn btn-danger btn-sm" onclick="deleteAgent('${a.id}')">🗑</button>
      </div>
      <p>${a.description || 'No description'}</p>
      <p style="margin-top:6px;color:var(--primary);font-size:.78em">${a.skill_count} skills: ${(a.skills||[]).slice(0,5).join(', ')}${a.skill_count>5?'…':''}</p>
    </div>`).join('');
}

async function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  const r = await api('/api/agents/custom/' + id, {method:'DELETE'});
  if (r.ok) { toast('Agent deleted', '#ef4444'); loadAgents(); }
}

// ── Tasks — agent selector state ─────────────────────────────────────────────
let _allAgents = [];          // full list from /api/agents
let _autoSelectedIds = new Set(); // IDs suggested by auto-select
let _selectedAgentIds = new Set(); // currently selected (user may adjust)
let _taskMode = 'auto';       // 'auto' | 'parallel' | 'single'

function onTaskInputChange() {
  const v = document.getElementById('task-input').value.trim();
  document.getElementById('btn-autoselect').disabled = !v;
  document.getElementById('autoselect-status').textContent = '';
}

function setMode(m) {
  _taskMode = m;
  ['auto','parallel','single'].forEach(id => {
    const el = document.getElementById('mode-' + id);
    el.style.border = id === m ? '2px solid var(--primary)' : '1px solid var(--border)';
  });
}

async function runAutoSelect() {
  const desc = document.getElementById('task-input').value.trim();
  if (!desc) return;
  const statusEl = document.getElementById('autoselect-status');
  statusEl.textContent = '⏳ Analysing task…';
  document.getElementById('btn-autoselect').disabled = true;

  // Fetch all agents if we don't have them yet
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { const d = await r.json(); _allAgents = d.agents || []; }
  }

  const r = await api('/api/task/auto-agents', {method:'POST', body: JSON.stringify({description: desc})});
  if (r.ok) {
    const d = await r.json();
    _autoSelectedIds = new Set(d.suggested || []);
    _selectedAgentIds = new Set(_autoSelectedIds);
    statusEl.innerHTML = `<span style="color:var(--success)">✅ ${_autoSelectedIds.size} agent${_autoSelectedIds.size!==1?'s':''} auto-selected</span>`;
    renderAgentPicker();
    document.getElementById('task-step2').style.display = 'block';
    document.getElementById('task-step3').style.display = 'block';
    document.getElementById('task-step-badge').textContent = 'Step 2';
  } else {
    statusEl.innerHTML = '<span style="color:var(--danger)">❌ Auto-select failed — use Manual to pick agents</span>';
    showManualAgentPicker();
  }
  document.getElementById('btn-autoselect').disabled = false;
}

async function showManualAgentPicker() {
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { const d = await r.json(); _allAgents = d.agents || []; }
  }
  renderAgentPicker();
  document.getElementById('task-step2').style.display = 'block';
  document.getElementById('task-step3').style.display = 'block';
  document.getElementById('task-step-badge').textContent = 'Step 2';
}

const _catColors = {
  coordination:'#6366f1', sales:'#10b981', content:'#22d3ee', social:'#f59e0b',
  research:'#3b82f6', ecommerce:'#ec4899', analytics:'#8b5cf6', creative:'#ef4444',
  trading:'#f97316', development:'#14b8a6', hr:'#84cc16', finance:'#eab308',
  marketing:'#06b6d4', growth:'#a855f7', management:'#64748b', crypto:'#f59e0b',
  strategy:'#6366f1', support:'#10b981'
};
const _catEmoji = {
  coordination:'🎯', sales:'💼', content:'✍️', social:'📱', research:'🔍',
  ecommerce:'🛒', analytics:'📊', creative:'🎨', trading:'📈', development:'💻',
  hr:'👔', finance:'💰', marketing:'🚀', growth:'📈', management:'📋',
  crypto:'🪙', strategy:'🏢', support:'🎧'
};

function renderAgentPicker() {
  const grid = document.getElementById('agent-picker-grid');
  if (!_allAgents.length) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:.84em">No agents loaded. Check /api/agents.</p>';
    return;
  }
  grid.innerHTML = _allAgents.map(a => {
    const selected = _selectedAgentIds.has(a.id);
    const wasAuto = _autoSelectedIds.has(a.id);
    const color = _catColors[a.category] || '#64748b';
    const emoji = _catEmoji[a.category] || '🤖';
    const dotColor = a.running ? '#10b981' : '#64748b';
    return `<div id="agentcard-${a.id}"
      onclick="toggleAgent('${escHtml(a.id)}')"
      title="${escHtml(a.description||'')}"
      style="cursor:pointer;border:2px solid ${selected ? color : 'var(--border)'};border-radius:var(--radius-sm);padding:8px 6px;background:${selected ? 'var(--surface2)' : 'var(--surface)'};transition:all .15s;position:relative;user-select:none">
      ${wasAuto ? `<span style="position:absolute;top:3px;right:3px;font-size:.6em;background:${color};color:#fff;border-radius:3px;padding:1px 4px">AUTO</span>` : ''}
      <div style="display:flex;align-items:center;gap:4px;margin-bottom:3px">
        <span style="font-size:1em">${emoji}</span>
        <span style="width:6px;height:6px;border-radius:50%;background:${dotColor};flex-shrink:0"></span>
      </div>
      <div style="font-size:.78em;font-weight:600;color:${selected ? color : 'var(--text)'};line-height:1.2">${escHtml(a.id)}</div>
      <div style="font-size:.68em;color:var(--text-muted);margin-top:1px">${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
  updateAgentSelCount();
}

function toggleAgent(id) {
  if (_selectedAgentIds.has(id)) _selectedAgentIds.delete(id);
  else _selectedAgentIds.add(id);
  const a = _allAgents.find(x => x.id === id);
  const card = document.getElementById('agentcard-' + id);
  if (!card || !a) return;
  const selected = _selectedAgentIds.has(id);
  const color = _catColors[a.category] || '#64748b';
  card.style.border = `2px solid ${selected ? color : 'var(--border)'}`;
  card.style.background = selected ? 'var(--surface2)' : 'var(--surface)';
  card.querySelector('div:last-child').previousElementSibling.style.color = selected ? color : 'var(--text)';
  updateAgentSelCount();
}

function selectAllAgents() {
  _allAgents.forEach(a => _selectedAgentIds.add(a.id));
  renderAgentPicker();
}
function clearAllAgents() {
  _selectedAgentIds.clear();
  renderAgentPicker();
}
function resetToAutoSelected() {
  _selectedAgentIds = new Set(_autoSelectedIds);
  renderAgentPicker();
}

function updateAgentSelCount() {
  const n = _selectedAgentIds.size;
  document.getElementById('agent-sel-count').textContent = `(${n} selected)`;
}

async function submitTask() {
  const desc = document.getElementById('task-input').value.trim();
  if (!desc) { toast('Please enter a task description', '#ef4444'); return; }
  const resultEl = document.getElementById('task-submit-result');
  resultEl.innerHTML = '⏳ Submitting…';
  const agents = [..._selectedAgentIds];
  const r = await api('/api/task/submit', {method:'POST', body: JSON.stringify({
    description: desc,
    agents: agents,
    mode: _taskMode
  })});
  if (r.ok) {
    const d = await r.json();
    resultEl.innerHTML = `<span style="color:var(--success)">✅ Task launched! ID: <code>${d.task_id||'?'}</code> | ${agents.length || 'auto'} agent${agents.length!==1?'s':''} | mode: ${_taskMode}</span>`;
    document.getElementById('task-input').value = '';
    _selectedAgentIds.clear();
    _autoSelectedIds.clear();
    document.getElementById('task-step2').style.display = 'none';
    document.getElementById('task-step3').style.display = 'none';
    document.getElementById('task-step-badge').textContent = 'Step 1';
    document.getElementById('autoselect-status').textContent = '';
    setTimeout(loadTasks, 2000);
  } else {
    resultEl.innerHTML = '<span style="color:var(--danger)">❌ Failed to submit. Is task-orchestrator running?</span>';
  }
}

async function loadTasks() {
  const r = await api('/api/task/list');
  if (!r.ok) return;
  const d = await r.json();
  const plans = d.plans || [];

  const activePanel = document.getElementById('active-task-panel');
  const active = plans.find(p => p.status === 'running' || p.status === 'planning');
  if (active) {
    const subtasks = active.subtasks || [];
    const done = subtasks.filter(s => s.status === 'done').length;
    const pct = subtasks.length ? Math.round(done/subtasks.length*100) : 0;
    const statusEmoji = {running:'⏳',planning:'🧠',done:'✅',failed:'❌'}[active.status]||'?';
    const modeTag = active.mode ? `<span style="font-size:.72em;background:var(--surface2);padding:1px 6px;border-radius:3px;margin-left:6px">${active.mode}</span>` : '';
    activePanel.innerHTML = `
      <div style="margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:4px">${statusEmoji} ${escHtml(active.title||active.id)}${modeTag}</div>
        <div style="font-size:.82em;color:var(--text-muted)">ID: ${active.id} | ${done}/${subtasks.length} subtasks</div>
        <div style="background:var(--border);border-radius:4px;height:6px;margin:8px 0">
          <div style="background:var(--primary);height:100%;width:${pct}%;border-radius:4px;transition:width .3s"></div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${subtasks.map(st => {
          const e = {done:'✅',running:'⏳',pending:'⏸️',failed:'❌',skipped:'⏭️'}[st.status]||'?';
          const agColor = _catColors[(_allAgents.find(a=>a.id===st.agent_id)||{}).category] || '#64748b';
          return `<div style="display:flex;align-items:center;gap:8px;font-size:.84em;padding:4px 6px;border-radius:4px;background:var(--surface)">
            <span>${e}</span>
            <span style="color:${agColor};font-weight:600;min-width:110px;font-size:.9em">${escHtml(st.agent_id||'?')}</span>
            <span style="color:var(--text-secondary);flex:1">${escHtml(st.title||st.subtask_id||'')}</span>
            ${st.status==='pending' ? `<button class="btn btn-ghost btn-sm" style="padding:1px 6px;font-size:.7em" onclick="reassignSubtask('${escHtml(active.id)}','${escHtml(st.subtask_id||'')}')">↩ Reassign</button>` : ''}
          </div>`;
        }).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn btn-ghost btn-sm" style="color:var(--danger)" onclick="cancelTask()">🛑 Cancel</button>
        <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
      </div>
    `;
    setTimeout(loadTasks, 5000);
  } else {
    activePanel.innerHTML = '<div class="empty"><div class="icon">🚀</div><p>No active task. Build one on the left.</p></div>';
  }

  const histEl = document.getElementById('task-history-list');
  const history = plans.filter(p => !['running','planning'].includes(p.status)).slice(0,10);
  if (!history.length) { histEl.innerHTML = '<div class="empty"><p>No task history yet.</p></div>'; return; }
  histEl.innerHTML = history.map(p => {
    const e = {done:'✅',failed:'❌',cancelled:'🛑',timed_out:'⏰'}[p.status]||'?';
    const agents = [...new Set((p.subtasks||[]).map(s=>s.agent_id).filter(Boolean))].join(', ');
    const mode = p.mode ? ` · ${p.mode}` : '';
    return `<div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div>
        <div style="font-weight:500">${e} ${escHtml(p.title||p.id)}</div>
        <div style="font-size:.78em;color:var(--text-muted)">${(p.subtasks||[]).length} subtasks${mode} | Agents: ${escHtml(agents)||'—'} | ${p.created_at||''}</div>
      </div>
      <span style="font-size:.78em;background:var(--surface2);padding:2px 8px;border-radius:4px;color:var(--text-secondary)">${p.status}</span>
    </div>`;
  }).join('');
}

async function cancelTask() {
  const r = await api('/api/task/cancel', {method:'POST'});
  if (r.ok) { toast('Task cancelled', '#f59e0b'); loadTasks(); }
}

async function reassignSubtask(taskId, subtaskId) {
  if (!_allAgents.length) {
    const r = await api('/api/agents');
    if (r.ok) { const d = await r.json(); _allAgents = d.agents || []; }
  }
  const agentId = prompt(
    'Reassign subtask to which agent?\nAvailable: ' +
    _allAgents.map(a=>a.id).join(', ')
  );
  if (!agentId) return;
  const r = await api('/api/task/reassign', {method:'POST', body: JSON.stringify({task_id: taskId, subtask_id: subtaskId, agent_id: agentId.trim()})});
  if (r.ok) { toast('Subtask reassigned ✅', '#10b981'); loadTasks(); }
  else toast('Reassign failed', '#ef4444');
}

// ── Swarm ────────────────────────────────────────────────────────────────────
async function loadSwarm() {
  const r = await api('/api/agents');
  if (!r.ok) return;
  const d = await r.json();
  const agents = d.agents || [];
  _allAgents = agents; // cache for task picker
  renderSwarmGrid(agents);
}

function renderSwarmGrid(agents) {
  const grid = document.getElementById('swarm-grid');
  if (!agents.length) {
    grid.innerHTML = '<div class="empty"><div class="icon">🐝</div><p>No agent data.</p></div>';
    return;
  }
  grid.innerHTML = agents.map(a => {
    const color = _catColors[a.category] || '#64748b';
    const dotColor = a.running ? '#10b981' : '#ef4444';
    const runningDot = `<span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;margin-left:6px"></span>`;
    const skills = (a.skills||[]).slice(0,4).map(s => `<span style="background:var(--surface);padding:2px 6px;border-radius:3px;font-size:.73em;color:var(--text-secondary)">${escHtml(s)}</span>`).join('');
    return `<div data-category="${escHtml(a.category||'')}" style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;border-top:3px solid ${color}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div style="font-weight:600;font-size:.95em">${escHtml(a.id)}</div>
        ${runningDot}
      </div>
      <div style="font-size:.8em;color:var(--text-secondary);margin-bottom:10px;line-height:1.4">${escHtml(a.description||'')}</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${skills}${(a.skills||[]).length > 4 ? `<span style="font-size:.73em;color:var(--text-muted)">+${(a.skills||[]).length-4} more</span>` : ''}</div>
      <div style="margin-top:8px;font-size:.75em;color:var(--text-muted)">Category: ${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
}

function filterSwarm(category, btn) {
  document.querySelectorAll('.swarm-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  const filtered = category === 'all' ? _allAgents : _allAgents.filter(a => a.category === category);
  renderSwarmGrid(filtered);
}

// ── Commands Tab ─────────────────────────────────────────────────────────────
const COMMAND_GROUPS = [
  {
    cat: '⚙️ System',
    cmds: [
      ['status', 'Get current bot status report'],
      ['workers', 'List all active workers'],
      ['start <bot>', 'Start a specific bot'],
      ['stop <bot>', 'Stop a specific bot'],
      ['schedule', 'List all scheduled tasks'],
      ['improvements', 'List pending skill proposals'],
      ['skills', 'Show skills library summary'],
      ['agents', 'List all AI agents'],
      ['help', 'Show full command list'],
      ['cmds', 'Show this commands reference'],
    ]
  },
  {
    cat: '🏭 Worker Bundles',
    cmds: [
      ['worker list', 'List all worker bundles'],
      ['worker create <name> agents:<a1,a2> task:<desc>', 'Create a worker bundle'],
      ['worker run <name>', 'Manually trigger a worker'],
      ['worker enable <name>', 'Enable a worker bundle'],
      ['worker disable <name>', 'Pause a worker bundle'],
      ['worker delete <name>', 'Delete a worker bundle'],
      ['worker status <name>', 'Show worker details & last run'],
      ['worker ecom', 'Create full e-commerce automation worker preset'],
    ]
  },
  {
    cat: '🛒 E-commerce Automation',
    cmds: [
      ['ecom metrics', 'Real-time revenue / profit / orders dashboard'],
      ['ecom research <niche>', 'Find top 5 trending product opportunities'],
      ['ecom listing <product>', 'Generate full Shopify listing (title/desc/tags/price)'],
      ['ecom email <type> <product>', 'Email flow: welcome|abandoned_cart|post_purchase|upsell'],
      ['ecom ads <product>', 'Facebook/Google ad copy (headline + body + CTA)'],
      ['ecom trends', 'Current trending products & niches'],
      ['ecom service <issue>', 'Customer service reply template'],
      ['ecom status', 'Listings, emails, and research session count'],
      ['order process <order_id>', 'Process a specific order'],
      ['order status <order_id>', 'Get order fulfillment status'],
      ['inventory check', 'Current stock levels across all products'],
      ['inventory forecast', '7-day demand forecast & reorder recommendations'],
      ['inventory reorder', 'Trigger auto-reorder for low-stock items'],
      ['support ticket <issue>', 'Classify & auto-resolve a support ticket'],
      ['support refund <order_id>', 'Process a refund automatically'],
      ['books daily', 'Daily P&L summary from Stripe'],
      ['books pl', 'Full P&L report (revenue / COGS / ads / profit)'],
      ['books tax', 'Quarterly tax export'],
      ['email campaign <segment>', 'Launch email campaign (new/abandoned/repeat)'],
      ['email abtest <subject1> vs <subject2>', 'Run A/B subject line test'],
      ['social post <product>', 'Generate & schedule viral social post'],
      ['social script <topic>', 'TikTok viral script'],
      ['product scan', 'Daily TikTok/Amazon trending product scan'],
      ['product validate <idea>', 'Demand validation via Google Trends / JungleScout'],
      ['product publish <product>', 'Auto-generate listing and publish to Shopify'],
    ]
  },
  {
    cat: '🚀 Tasks & Orchestration',
    cmds: [
      ['task <description>', 'Submit a multi-agent task'],
      ['task status', 'Show status of active task'],
      ['task list', 'List recent tasks'],
      ['task cancel', 'Cancel active task'],
      ['task agents <a1,a2>', 'Set agents for next task'],
      ['task mode auto|parallel|single', 'Set execution mode'],
      ['task config', 'Show current task configuration'],
      ['assign <agent> <subtask>', 'Manually dispatch a subtask'],
    ]
  },
  {
    cat: '🏢 Company Building',
    cmds: [
      ['company build <idea>', 'Full company launch package'],
      ['company validate <idea>', 'Viability check & SWOT'],
      ['company plan <idea>', 'Business plan only'],
      ['company simulate <scenario>', 'Growth simulation'],
      ['company gtm <idea>', 'Go-to-market strategy'],
      ['company pitch <company>', 'Investor pitch deck'],
      ['company org <company>', 'Org chart design'],
      ['company swot <topic>', 'SWOT analysis'],
    ]
  },
  {
    cat: '🪙 Memecoin & Web3',
    cmds: [
      ['memecoin create <concept>', 'Full token launch package'],
      ['memecoin name <concept>', 'Generate token names'],
      ['memecoin tokenomics <name>', 'Design tokenomics model'],
      ['memecoin whitepaper <name>', 'Draft whitepaper'],
      ['memecoin community <name>', 'Community strategy'],
      ['memecoin viral <name>', 'Viral launch campaign'],
    ]
  },
  {
    cat: '💰 Finance',
    cmds: [
      ['finance model <business>', '3-year financial model'],
      ['finance pl <business>', 'P&L projections'],
      ['finance runway <burn> <cash>', 'Burn rate & runway'],
      ['finance raise <stage> <amount>', 'Fundraising prep'],
      ['finance unit <product> <price>', 'Unit economics (CAC/LTV)'],
      ['finance pricing <product>', 'Pricing strategy'],
      ['finance pitch <company>', 'Investor pitch financials'],
      ['finance valuation <company>', 'Valuation methodology'],
    ]
  },
  {
    cat: '👔 HR & People',
    cmds: [
      ['hr hire <role>', 'Full hiring package'],
      ['hr jd <role>', 'Write job description'],
      ['hr screen <cv-text>', 'AI CV screening & scoring'],
      ['hr interview <role>', 'Interview question pack'],
      ['hr onboard <role>', '90-day onboarding plan'],
      ['hr review <role>', 'Performance review template'],
      ['hr org <company>', 'Org chart design'],
      ['hr culture <company>', 'Culture & values document'],
    ]
  },
  {
    cat: '🎨 Brand',
    cmds: [
      ['brand identity <company>', 'Full brand identity system'],
      ['brand name <industry>', 'Brand name generation (15 options)'],
      ['brand position <company>', 'Brand positioning strategy'],
      ['brand voice <company>', 'Brand voice & tone guide'],
      ['brand messaging <company>', 'Messaging framework'],
      ['brand story <company>', 'Brand story & narrative'],
      ['brand audit <company>', 'Competitive brand audit'],
    ]
  },
  {
    cat: '📈 Growth',
    cmds: [
      ['growth loop <product>', 'Viral growth loop design'],
      ['growth funnel <product>', 'Conversion funnel optimization'],
      ['growth abtests <feature>', 'A/B test framework'],
      ['growth retention <product>', 'Retention strategy'],
      ['growth referral <product>', 'Referral program design'],
      ['growth plg <product>', 'Product-led growth strategy'],
      ['growth experiments <product>', 'ICE-scored experiment backlog'],
    ]
  },
  {
    cat: '📋 Project Management',
    cmds: [
      ['pm start <project>', 'Kick off a project'],
      ['pm breakdown <project>', 'Work breakdown structure'],
      ['pm sprint <goal>', '2-week sprint plan'],
      ['pm roadmap <project>', 'Project roadmap & milestones'],
      ['pm risks <project>', 'Risk register & mitigation'],
      ['pm raci <project>', 'RACI responsibility matrix'],
      ['pm gantt <project>', 'Gantt chart (text-based)'],
      ['pm retro <sprint>', 'Sprint retrospective facilitation'],
    ]
  },
  {
    cat: '✍️ Content & Social',
    cmds: [
      ['content <brief>', 'Full content package'],
      ['social <brief>', 'Social media content pack'],
      ['social plan <brief>', 'Strategy plan only'],
      ['video <topic>', 'Faceless video full pipeline'],
      ['video script <topic>', 'Video script only'],
      ['video seo <topic>', 'YouTube SEO pack'],
      ['newsletter create <topic>', 'Generate newsletter issue'],
      ['course create <topic>', 'Full course package'],
      ['course outline <topic>', 'Course structure only'],
    ]
  },
  {
    cat: '💼 Sales & Leads',
    cmds: [
      ['leads <niche> <location>', 'Local business lead generation'],
      ['outreach <campaign>', 'Outreach campaign'],
      ['email <brief>', 'Cold email sequence'],
      ['prospect <niche> <location>', 'Appointment setter prospects'],
      ['websales audit <url>', 'Website audit + sales pitch'],
      ['recruit <role> <requirements>', 'Find & screen candidates'],
    ]
  },
  {
    cat: '📈 Crypto & Trading',
    cmds: [
      ['crypto <pair>', 'Technical analysis with signals'],
      ['trade <pair>', 'Trading signal & risk analysis'],
      ['signals', 'Current trading signals'],
      ['signal daily', 'Daily market summary'],
      ['arb scan <product>', 'Arbitrage opportunity scan'],
      ['arb opportunities', 'Top arbitrage opportunities'],
    ]
  },
  {
    cat: '📅 Scheduling',
    cmds: [
      ['schedule', 'List all scheduled tasks'],
      ['schedule add <label> <action> <cron>', 'Add scheduled task (via UI)'],
    ]
  },
];

let _cmdActiveFilter = null;
let _renderedCmds = [];

function loadCommandsTab() {
  // Category pills
  const pills = document.getElementById('cmd-category-pills');
  pills.innerHTML = `<span onclick="setCmdFilter(null)" id="cmd-pill-all"
    style="cursor:pointer;padding:4px 10px;border-radius:10px;font-size:.8em;background:var(--primary);color:#fff">All</span>` +
    COMMAND_GROUPS.map((g,i) => `<span onclick="setCmdFilter(${i})" id="cmd-pill-${i}"
      style="cursor:pointer;padding:4px 10px;border-radius:10px;font-size:.8em;background:var(--surface2);color:var(--text-secondary)">${g.cat}</span>`
    ).join('');
  renderCommands();
}

function setCmdFilter(idx) {
  _cmdActiveFilter = idx;
  document.getElementById('cmd-pill-all').style.background = idx===null ? 'var(--primary)' : 'var(--surface2)';
  document.getElementById('cmd-pill-all').style.color = idx===null ? '#fff' : 'var(--text-secondary)';
  COMMAND_GROUPS.forEach((_,i) => {
    const p = document.getElementById('cmd-pill-' + i);
    if (!p) return;
    p.style.background = i===idx ? 'var(--primary)' : 'var(--surface2)';
    p.style.color = i===idx ? '#fff' : 'var(--text-secondary)';
  });
  renderCommands();
}

function filterCommands() { renderCommands(); }

function renderCommands() {
  const q = (document.getElementById('cmd-search')?.value || '').toLowerCase();
  const groups = _cmdActiveFilter !== null ? [COMMAND_GROUPS[_cmdActiveFilter]] : COMMAND_GROUPS;
  const list = document.getElementById('cmd-list');
  if (!list) return;
  list.innerHTML = groups.map(g => {
    const rows = g.cmds
      .filter(([cmd, desc]) => !q || cmd.toLowerCase().includes(q) || desc.toLowerCase().includes(q))
      .map(([cmd, desc]) => `
        <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)">
          <code onclick="copyCmd('${escHtml(cmd)}')" title="Click to copy" style="cursor:pointer;min-width:200px;background:var(--surface2);padding:3px 8px;border-radius:4px;font-size:.84em;color:var(--accent)">${escHtml(cmd)}</code>
          <span style="color:var(--text-secondary);font-size:.85em;flex:1">${escHtml(desc)}</span>
          <button class="btn btn-ghost btn-sm" onclick="copyCmd('${escHtml(cmd)}')" style="padding:2px 8px;font-size:.72em">📋</button>
        </div>`
      ).join('');
    if (!rows) return '';
    return `<div style="margin-bottom:16px">
      <div style="font-weight:700;font-size:.9em;color:var(--text);margin-bottom:4px">${g.cat}</div>
      ${rows}
    </div>`;
  }).join('');
}

function copyCmd(cmd) {
  navigator.clipboard.writeText(cmd).then(() => toast(`Copied: ${cmd}`, '#6366f1')).catch(() => {});
}

// ── ROI Metrics ──────────────────────────────────────────────────────────────
async function loadMetrics() {
  const d = await api('/api/metrics');
  const s = d.summary || {};
  document.getElementById('m-tasks').textContent  = (s.tasks_completed   || 0).toLocaleString();
  document.getElementById('m-leads').textContent  = (s.leads_generated   || 0).toLocaleString();
  document.getElementById('m-hours').textContent  = (s.hours_saved       || 0).toLocaleString();
  document.getElementById('m-saved').textContent  = '€' + (s.cost_saved  || 0).toLocaleString();
  document.getElementById('m-emails').textContent = (s.emails_sent       || 0).toLocaleString();
  document.getElementById('m-content').textContent= (s.content_created   || 0).toLocaleString();

  const events = d.events || [];
  const el = document.getElementById('metrics-events');
  if (!events.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📊</div><p>No events yet. Run tasks to start tracking ROI.</p></div>';
    return;
  }
  const typeIcon = {task_completed:'✅',lead_generated:'🎯',email_sent:'📧',content_created:'📝',call_booked:'📞',deal_closed:'💰',ticket_resolved:'🎫',custom:'⭐'};
  el.innerHTML = events.slice(-30).reverse().map(e => {
    const icon = typeIcon[e.type] || '⭐';
    const val = e.value ? ` <span style="color:var(--success);font-weight:600">€${e.value}</span>` : '';
    const agent = e.agent ? ` <code style="font-size:.72em">${escHtml(e.agent)}</code>` : '';
    const note = e.notes ? `<div style="font-size:.77em;color:var(--text-muted);margin-top:2px">${escHtml(e.notes)}</div>` : '';
    const ts = (e.ts||'').split('T')[0];
    return `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:1.1em;margin-top:1px">${icon}</span>
      <div style="flex:1">
        <div style="font-size:.86em">${escHtml(e.type.replace(/_/g,' '))}${agent}${val}</div>
        ${note}
      </div>
      <span style="font-size:.73em;color:var(--text-muted);white-space:nowrap">${ts}</span>
    </div>`;
  }).join('');
}

async function recordMetric() {
  const type  = document.getElementById('metric-type').value;
  const agent = document.getElementById('metric-agent').value.trim();
  const value = parseFloat(document.getElementById('metric-value').value) || null;
  const notes = document.getElementById('metric-notes').value.trim();
  const r = await api('/api/metrics', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({type, agent: agent||null, value, notes: notes||null})});
  if (r.ok) {
    toast('Metric recorded!');
    document.getElementById('metric-value').value = '';
    document.getElementById('metric-notes').value = '';
    loadMetrics();
  } else { toast(r.detail || r.error || 'Error', '#ef4444'); }
}

// ── Templates ────────────────────────────────────────────────────────────────
async function loadTemplates() {
  const d = await api('/api/templates');
  const templates = d.templates || [];
  const el = document.getElementById('templates-grid');
  if (!templates.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📋</div><p>No templates found.</p></div>';
    return;
  }
  const catColors = {Sales:'rgba(16,185,129,.15)',Support:'rgba(99,102,241,.15)',HR:'rgba(34,211,238,.15)',Content:'rgba(245,158,11,.15)','E-commerce':'rgba(239,68,68,.15)'};
  el.innerHTML = templates.map(t => {
    const col = catColors[t.category] || 'rgba(99,102,241,.12)';
    const agents = (t.agents||[]).map(a => `<span style="background:var(--surface);padding:1px 6px;border-radius:3px;font-size:.72em;border:1px solid var(--border)">${escHtml(a)}</span>`).join(' ');
    const expected = t.expected_results || {};
    const roi = expected.estimated_monthly_revenue || expected.estimated_monthly_savings || expected.estimated_monthly_value || '';
    const steps = (t.setup_steps||[]).map(s => `<li style="margin-bottom:4px">${escHtml(s)}</li>`).join('');
    return `<div style="border:1px solid var(--border);border-radius:var(--radius);padding:18px;background:var(--surface2)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:1.8em">${escHtml(t.icon||'📋')}</span>
        <div>
          <div style="font-weight:700;font-size:.95em">${escHtml(t.name)}</div>
          <span style="font-size:.73em;background:${col};padding:2px 8px;border-radius:4px;color:var(--text-secondary)">${escHtml(t.category)}</span>
        </div>
        ${roi ? `<span style="margin-left:auto;font-size:.78em;color:var(--success);font-weight:600;background:rgba(16,185,129,.1);padding:3px 8px;border-radius:6px">${escHtml(roi)}</span>` : ''}
      </div>
      <p style="font-size:.83em;color:var(--text-secondary);margin-bottom:10px;line-height:1.5">${escHtml(t.description)}</p>
      <div style="margin-bottom:10px">
        <div style="font-size:.73em;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">Agents</div>
        <div style="display:flex;flex-wrap:wrap;gap:3px">${agents}</div>
      </div>
      <details style="margin-bottom:10px">
        <summary style="cursor:pointer;font-size:.8em;color:var(--accent);font-weight:600">📋 Setup Steps</summary>
        <ol style="font-size:.8em;color:var(--text-muted);margin:8px 0 0 16px;line-height:1.6">${steps}</ol>
      </details>
      <button class="btn btn-success" style="width:100%" onclick="deployTemplate('${jsEsc(t.id)}','${jsEsc(t.name)}')">🚀 Deploy Template</button>
    </div>`;
  }).join('');
}

async function deployTemplate(id, name) {
  if (!confirm(`Deploy template "${name}"?\n\nThis will create a new Worker Bundle with pre-configured agents and schedule.`)) return;
  const r = await api(`/api/templates/${id}/deploy`, {method:'POST'});
  if (r.ok) {
    toast(`✅ Template "${name}" deployed! Check Workers tab.`, '#10b981');
  } else { toast(r.detail || r.error || 'Deployment failed', '#ef4444'); }
}

// ── Guardrails ───────────────────────────────────────────────────────────────
async function loadGuardrails() {
  const d = await api('/api/guardrails');
  const pending  = d.pending  || [];
  const log      = d.log      || [];
  const summary  = d.summary  || {};

  document.getElementById('g-pending').textContent  = pending.length;
  document.getElementById('g-approved').textContent = summary.approved || 0;
  document.getElementById('g-rejected').textContent = summary.rejected || 0;
  document.getElementById('g-total').textContent    = summary.total    || 0;

  const pEl = document.getElementById('guardrails-pending');
  if (!pending.length) {
    pEl.innerHTML = '<div class="empty"><div class="icon">✅</div><p>No pending approvals. All clear!</p></div>';
  } else {
    const riskColor = {high:'#ef4444', medium:'#f59e0b', low:'#10b981'};
    pEl.innerHTML = pending.map(a => {
      const col = riskColor[a.risk_level] || '#f59e0b';
      return `<div style="border:1px solid ${col};border-radius:var(--radius-sm);padding:12px;margin-bottom:10px;background:var(--surface2)">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <div style="flex:1">
            <div style="font-size:.88em;font-weight:600">${escHtml(a.action_type||'Action')}</div>
            <div style="font-size:.82em;color:var(--text-secondary);margin:3px 0">${escHtml(a.description||'')}</div>
            <div style="font-size:.77em;color:var(--text-muted)">Agent: <code>${escHtml(a.agent||'?')}</code> · Risk: <span style="color:${col};font-weight:600">${escHtml(a.risk_level||'medium')}</span></div>
          </div>
          <div style="display:flex;gap:5px;flex-shrink:0">
            <button class="btn btn-success btn-sm" onclick="approveAction('${jsEsc(a.id)}')">✅ Approve</button>
            <button class="btn btn-danger btn-sm" onclick="rejectAction('${jsEsc(a.id)}')">🚫 Reject</button>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  const lEl = document.getElementById('guardrails-log');
  if (!log.length) {
    lEl.innerHTML = '<div class="empty"><div class="icon">📋</div><p>No actions logged yet.</p></div>';
  } else {
    const statusIcon = {approved:'✅', rejected:'🚫', pending:'⏳', auto_approved:'✔️'};
    lEl.innerHTML = log.slice(-20).reverse().map(e => {
      const icon = statusIcon[e.status] || '📋';
      const ts = (e.ts||'').replace('T',' ').slice(0,16);
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:.83em">
        <span>${icon}</span>
        <div style="flex:1">
          <span>${escHtml(e.action_type||'action')}</span>
          <code style="font-size:.77em;margin-left:4px">${escHtml(e.agent||'?')}</code>
        </div>
        <span style="font-size:.73em;color:var(--text-muted)">${ts}</span>
      </div>`;
    }).join('');
  }
}

async function approveAction(id) {
  const r = await api(`/api/guardrails/${id}/approve`, {method:'POST'});
  if (r.ok) { toast('Action approved ✅'); loadGuardrails(); }
  else { toast(r.detail || 'Error', '#ef4444'); }
}

async function rejectAction(id) {
  const reason = prompt('Reason for rejection (optional):') || '';
  const r = await api(`/api/guardrails/${id}/reject`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({reason})});
  if (r.ok) { toast('Action rejected 🚫', '#ef4444'); loadGuardrails(); }
  else { toast(r.detail || 'Error', '#ef4444'); }
}

async function saveGuardrailSettings() {
  const settings = {
    require_approval_for: {
      send_email:    document.getElementById('gr-send-email').checked,
      social_post:   document.getElementById('gr-social-post').checked,
      make_purchase: document.getElementById('gr-make-purchase').checked,
      delete_data:   document.getElementById('gr-delete-data').checked,
      api_calls:     document.getElementById('gr-api-calls').checked,
    },
    rate_limits: {
      emails_per_day: parseInt(document.getElementById('rl-emails').value) || 200,
      posts_per_day:  parseInt(document.getElementById('rl-posts').value) || 10,
      api_per_hour:   parseInt(document.getElementById('rl-api').value) || 100,
    }
  };
  const r = await api('/api/guardrails/settings', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(settings)});
  if (r.ok) { toast('Settings saved ✅'); }
  else { toast(r.detail || 'Error', '#ef4444'); }
}

// ── Memory ───────────────────────────────────────────────────────────────────
async function loadMemory() {
  const d = await api('/api/memory');
  const clients = d.clients || [];
  const recent  = d.recent_interactions || [];

  const cEl = document.getElementById('memory-clients');
  if (!clients.length) {
    cEl.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No clients remembered yet. Add one below.</p></div>';
  } else {
    const statusColor = {prospect:'rgba(245,158,11,.2)', lead:'rgba(34,211,238,.2)', customer:'rgba(16,185,129,.2)', churned:'rgba(239,68,68,.12)'};
    cEl.innerHTML = clients.map(c => {
      const col = statusColor[c.status] || 'var(--surface)';
      return `<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:8px;background:var(--surface2)">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-weight:600;font-size:.9em">${escHtml(c.name)}</div>
            ${c.company ? `<div style="font-size:.8em;color:var(--text-secondary)">${escHtml(c.company)}</div>` : ''}
            ${c.email   ? `<div style="font-size:.77em;color:var(--text-muted)">${escHtml(c.email)}</div>`   : ''}
          </div>
          <span style="font-size:.73em;background:${col};padding:2px 8px;border-radius:4px;border:1px solid var(--border)">${escHtml(c.status||'prospect')}</span>
        </div>
        ${c.notes ? `<div style="font-size:.78em;color:var(--text-muted);margin-top:6px;line-height:1.4">${escHtml(c.notes)}</div>` : ''}
        <div style="font-size:.72em;color:var(--text-muted);margin-top:4px">${(c.interactions||0)} interactions · added ${(c.added_at||'').split('T')[0]}</div>
        <div style="margin-top:8px;display:flex;gap:5px">
          <button class="btn btn-ghost btn-sm" onclick="updateClientStatus('${jsEsc(c.id)}','customer')" title="Mark as customer">Mark customer</button>
          <button class="btn btn-danger btn-sm" onclick="deleteClient('${jsEsc(c.id)}')">🗑</button>
        </div>
      </div>`;
    }).join('');
  }

  const rEl = document.getElementById('memory-recent');
  if (!recent.length) {
    rEl.innerHTML = '<div class="empty"><div class="icon">📝</div><p>No recent interactions.</p></div>';
  } else {
    rEl.innerHTML = recent.slice(-10).reverse().map(i => {
      const ts = (i.ts||'').replace('T',' ').slice(0,16);
      return `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:.83em">
        <div>${escHtml(i.summary||i.message||'interaction')}</div>
        <div style="font-size:.77em;color:var(--text-muted);margin-top:2px">${ts} · ${escHtml(i.agent||'system')}</div>
      </div>`;
    }).join('');
  }
}

async function addClient() {
  const name    = document.getElementById('mem-name').value.trim();
  const company = document.getElementById('mem-company').value.trim();
  const email   = document.getElementById('mem-email').value.trim();
  const status  = document.getElementById('mem-status').value;
  const notes   = document.getElementById('mem-notes').value.trim();
  if (!name) { toast('Name is required', '#ef4444'); return; }
  const r = await api('/api/memory/clients', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, company: company||null, email: email||null, status, notes: notes||null})});
  if (r.ok) {
    toast('Client added ✅');
    document.getElementById('mem-name').value    = '';
    document.getElementById('mem-company').value = '';
    document.getElementById('mem-email').value   = '';
    document.getElementById('mem-notes').value   = '';
    loadMemory();
  } else { toast(r.detail || 'Error', '#ef4444'); }
}

async function updateClientStatus(id, status) {
  await api(`/api/memory/clients/${id}`, {method:'PATCH',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({status})});
  loadMemory();
}

async function deleteClient(id) {
  if (!confirm('Delete this client from memory?')) return;
  await api(`/api/memory/clients/${id}`, {method:'DELETE'});
  loadMemory();
}

// ── Integrations ─────────────────────────────────────────────────────────────
async function loadIntegrations() {
  const d = await api('/api/integrations');
  const integrations = d.integrations || [];
  const el = document.getElementById('integrations-grid');
  if (!integrations.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🔌</div><p>No integrations configured.</p></div>';
    return;
  }
  el.innerHTML = integrations.map(intg => {
    const enabled = intg.enabled === true;
    const statusCol = enabled ? 'var(--success)' : 'var(--text-muted)';
    const fields = (intg.fields||[]).map(f => `
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:.78em">${escHtml(f.label)}</label>
        <input type="${f.type||'text'}" id="intg-${escHtml(intg.id)}-${escHtml(f.key)}"
          placeholder="${escHtml(f.placeholder||'')}"
          value="${escHtml(intg.config && intg.config[f.key] ? String(intg.config[f.key]) : '')}"
          ${f.type==='password'?'autocomplete="off"':''}/>
      </div>`).join('');
    return `<div style="border:1px solid var(--border);border-radius:var(--radius);padding:18px;background:var(--surface2)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:1.6em">${escHtml(intg.icon||'🔌')}</span>
        <div style="flex:1">
          <div style="font-weight:700;font-size:.95em">${escHtml(intg.name)}</div>
          <div style="font-size:.8em;color:var(--text-muted)">${escHtml(intg.description||'')}</div>
        </div>
        <span style="font-size:.73em;font-weight:600;color:${statusCol}">${enabled ? '● Connected' : '○ Not configured'}</span>
      </div>
      <div>${fields}</div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="btn btn-primary btn-sm" style="flex:1" onclick="saveIntegration('${jsEsc(intg.id)}')">💾 Save</button>
        <button class="btn btn-ghost btn-sm" onclick="testIntegration('${jsEsc(intg.id)}')">🔍 Test</button>
      </div>
      <div id="intg-result-${escHtml(intg.id)}" style="margin-top:6px;font-size:.8em"></div>
    </div>`;
  }).join('');
}

async function saveIntegration(id) {
  const d = await api('/api/integrations');
  const intg = (d.integrations||[]).find(i => i.id === id);
  if (!intg) { toast('Integration not found', '#ef4444'); return; }
  const config = {};
  (intg.fields||[]).forEach(f => {
    const el = document.getElementById(`intg-${id}-${f.key}`);
    if (el) config[f.key] = el.value;
  });
  const enabled = Object.values(config).some(v => v.trim && v.trim());
  const r = await api(`/api/integrations/${id}`, {method:'PATCH',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({config, enabled})});
  if (r.ok) { toast(`${intg.name} saved ✅`); loadIntegrations(); }
  else { toast(r.detail || 'Error', '#ef4444'); }
}

async function testIntegration(id) {
  const el = document.getElementById(`intg-result-${id}`);
  if (el) el.textContent = '⏳ Testing…';
  const r = await api(`/api/integrations/${id}/test`, {method:'POST'});
  if (el) {
    if (r.ok) { el.style.color = 'var(--success)'; el.textContent = '✅ ' + (r.message || 'Connection OK'); }
    else       { el.style.color = 'var(--danger)';  el.textContent = '❌ ' + (r.message || r.detail || 'Test failed'); }
  }
}


// ── Options / Settings ────────────────────────────────────────────────────────
async function loadOptions() {
  const d = await api('/api/settings');
  renderSettingsSection('opt-api-keys',   d.api_keys    || []);
  renderSettingsSection('opt-preferences', d.preferences || []);
}

function renderSettingsSection(containerId, fields) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = fields.map(f => `
    <div class="form-group" style="margin-bottom:10px">
      <label style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span>${escHtml(f.label)}</span>
        ${f.has_value
          ? '<span style="font-size:.73em;color:var(--success);font-weight:600">● set</span>'
          : '<span style="font-size:.73em;color:var(--text-muted)">○ not set</span>'}
      </label>
      <div style="display:flex;gap:6px">
        <input id="opt-field-${escHtml(f.key)}"
          type="${f.type === 'password' ? 'password' : 'text'}"
          placeholder="${escHtml(f.placeholder)}"
          value="${escHtml(f.value)}"
          autocomplete="off"
          style="flex:1"/>
        ${f.type === 'password'
          ? `<button class="btn btn-ghost btn-sm" style="flex-shrink:0;padding:5px 9px"
               onclick="toggleSecret('opt-field-${jsEsc(f.key)}',this)" title="Show/hide">👁</button>`
          : ''}
      </div>
    </div>`).join('');
}

function toggleSecret(inputId, btn) {
  const el = document.getElementById(inputId);
  if (!el) return;
  el.type = el.type === 'password' ? 'text' : 'password';
  btn.textContent = el.type === 'password' ? '👁' : '🙈';
}

async function saveSettings(category) {
  const containerId = 'opt-' + category.replace(/_/g, '-');
  const inputs = document.querySelectorAll('#' + containerId + ' input');
  const updates = {};
  inputs.forEach(el => {
    const key = el.id.replace('opt-field-', '');
    if (key) updates[key] = el.value;
  });
  if (!Object.keys(updates).length) { toast('Nothing to save'); return; }
  const r = await api('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({updates})
  });
  if (r.ok) {
    const msg = r.saved
      ? `✅ Saved ${r.saved} setting${r.saved !== 1 ? 's' : ''}`
      : 'No changes (all values were unchanged)';
    toast(msg, r.saved ? '#10b981' : '#64748b');
    if (r.saved) loadOptions();
  } else {
    toast(r.detail || 'Error saving', '#ef4444');
  }
}

async function runSecurityCheck() {
  const el = document.getElementById('opt-security-results');
  el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Running security checklist…</p>';
  const d = await api('/api/settings/security-check');
  const findings = d.findings || [];

  const colorMap   = {ok:'var(--success)', warning:'#f59e0b', error:'var(--danger)', info:'var(--accent)'};
  const iconMap    = {ok:'✅', warning:'⚠️', error:'❌', info:'ℹ️'};
  const badgeMap   = {ok:'DONE', warning:'ACTION NEEDED', error:'NOT DONE', info:'INFO'};
  const badgeBgMap = {
    ok:      'rgba(34,197,94,.15)',
    warning: 'rgba(245,158,11,.15)',
    error:   'rgba(239,68,68,.15)',
    info:    'rgba(99,102,241,.15)',
  };
  const warnColor = colorMap.warning;

  if (!findings.length) {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em">No findings.</p>';
    return;
  }

  const done    = findings.filter(f => f.level === 'ok').length;
  const errors  = findings.filter(f => f.level === 'error').length;
  const warns   = findings.filter(f => f.level === 'warning').length;
  const summaryColor = errors ? 'var(--danger)' : warns ? warnColor : 'var(--success)';
  const summaryIcon  = errors ? '❌' : warns ? '⚠️' : '✅';
  const summaryText  = errors
    ? `${errors} critical issue${errors>1?'s':''} found`
    : warns
      ? `${warns} warning${warns>1?'s':''} — review recommended`
      : 'All checks passed — ready for production';

  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:7px;
         background:var(--surface2);border:1px solid var(--border);margin-bottom:10px">
      <span style="font-size:1.2em">${summaryIcon}</span>
      <div>
        <div style="font-size:.88em;font-weight:700;color:${summaryColor}">${summaryText}</div>
        <div style="font-size:.76em;color:var(--text-muted);margin-top:2px">
          ${done} passed · ${errors} critical · ${warns} warnings · ${findings.filter(f=>f.level==='info').length} info
        </div>
      </div>
    </div>
    ${findings.map((f, idx) => {
      const color   = colorMap[f.level]   || 'var(--text)';
      const icon    = iconMap[f.level]    || '•';
      const badge   = badgeMap[f.level]   || f.level.toUpperCase();
      const badgeBg = badgeBgMap[f.level] || 'rgba(255,255,255,.1)';

      let actionHtml = '';
      if (f.action) {
        if (f.action_type === 'command') {
          actionHtml = `
            <div style="margin-top:7px">
              <div style="font-size:.74em;color:var(--text-muted);margin-bottom:3px;font-weight:600;letter-spacing:.03em">▶ COMMAND</div>
              <code style="display:block;background:var(--bg);border:1px solid var(--border);border-radius:5px;
                   padding:6px 10px;font-size:.78em;color:var(--accent);word-break:break-all;
                   white-space:pre-wrap">${escHtml(f.action)}</code>
            </div>`;
        } else if (f.action_type === 'config') {
          actionHtml = `
            <div style="margin-top:7px">
              <div style="font-size:.74em;color:var(--text-muted);margin-bottom:3px;font-weight:600;letter-spacing:.03em">⚙️ ADD TO security.local.yml</div>
              <code style="display:block;background:var(--bg);border:1px solid var(--border);border-radius:5px;
                   padding:6px 10px;font-size:.78em;color:${warnColor};word-break:break-all;
                   white-space:pre-wrap">${escHtml(f.action)}</code>
            </div>`;
        } else {
          actionHtml = `<div style="margin-top:5px;font-size:.78em;color:var(--text-muted)">💡 ${escHtml(f.action)}</div>`;
        }
      }

      let markDoneHtml = '';
      if (f.level !== 'ok' && f.action) {
        const btnId = `sec-done-btn-${idx}`;
        const fbId  = `sec-done-fb-${idx}`;
        markDoneHtml = `
          <div style="margin-top:8px;padding-left:26px;display:flex;align-items:center;gap:8px" id="${fbId}">
            <button id="${btnId}" class="btn btn-ghost btn-sm"
                    style="font-size:.74em;padding:3px 10px;border-color:var(--border)"
                    onclick="markSecurityActionDone(${idx+1},${JSON.stringify(f.title)},${JSON.stringify(f.action)},${JSON.stringify(f.action_type)},'${btnId}','${fbId}')">
              ${f.action_type === 'command' ? '📋 Copy & Mark Done' : '✓ Mark Done'}
            </button>
          </div>`;
      }

      return `
        <div style="display:flex;gap:10px;padding:10px 12px;border-radius:7px;
             background:var(--surface2);border:1px solid var(--border);margin-bottom:6px;
             border-left:3px solid ${color};align-items:flex-start">
          <span style="flex-shrink:0;font-size:1.05em;margin-top:1px">${icon}</span>
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span style="font-size:.76em;color:var(--text-muted);font-weight:600;min-width:18px">${idx+1}.</span>
              <span style="font-size:.87em;font-weight:600;color:${color}">${escHtml(f.title)}</span>
              <span style="font-size:.7em;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:99px;
                   background:${badgeBg};color:${color};border:1px solid ${color}55;flex-shrink:0">${badge}</span>
            </div>
            <div style="font-size:.8em;color:var(--text-muted);margin-top:3px;padding-left:26px">
              ${escHtml(f.detail)}
            </div>
            ${actionHtml ? `<div style="padding-left:26px">${actionHtml}</div>` : ''}
            ${markDoneHtml}
          </div>
        </div>`;
    }).join('')}`;
}

async function markSecurityActionDone(num, title, action, actionType, btnId, fbId) {
  const btn = document.getElementById(btnId);
  const fb  = document.getElementById(fbId);
  if (btn) btn.disabled = true;
  if (actionType === 'command' && action) {
    try { await navigator.clipboard.writeText(action); } catch(e) {}
  }
  await api('/api/history/mark-action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({title, action, action_type: actionType, check_number: num}),
  });
  if (fb) {
    fb.innerHTML = `<span style="font-size:.78em;color:var(--success);font-weight:600">
      ✅ ${actionType === 'command' ? 'Copied to clipboard — ' : ''}Marked as done and logged to History
    </span>`;
  }
}


// ── Activity History ──────────────────────────────────────────────────────────
let _historyEntries = [];

async function loadHistory() {
  const el = document.getElementById('history-timeline');
  if (!el) return;
  el.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>Loading…</p></div>';
  const d = await api('/api/history?limit=1000');
  _historyEntries = d.entries || [];
  document.getElementById('history-count').textContent =
    `${_historyEntries.length} entr${_historyEntries.length === 1 ? 'y' : 'ies'}`;
  renderHistory(_historyEntries);
}

function filterHistory() {
  const q      = (document.getElementById('history-search')?.value || '').toLowerCase();
  const type   = document.getElementById('history-type-filter')?.value || '';
  const source = document.getElementById('history-source-filter')?.value || '';
  const filtered = _historyEntries.filter(e => {
    if (type   && e.event_type !== type)   return false;
    if (source && e.source     !== source) return false;
    if (q) {
      const hay = (e.description + ' ' + e.event_type + ' ' + (e.source||'')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  document.getElementById('history-count').textContent =
    `${filtered.length} / ${_historyEntries.length} entr${_historyEntries.length === 1 ? 'y' : 'ies'}`;
  renderHistory(filtered);
}

function renderHistory(entries) {
  const el = document.getElementById('history-timeline');
  if (!el) return;
  if (!entries.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🕐</div><p>No activity recorded yet.</p></div>';
    return;
  }

  const typeColor = {
    security_check:       'var(--accent)',
    security_action_done: 'var(--success)',
    settings_saved:       '#6366f1',
    guardrail_approved:   'var(--success)',
    guardrail_rejected:   'var(--danger)',
    agent_command:        'var(--text)',
    task_run:             'var(--accent)',
    worker_triggered:     '#f59e0b',
    system:               'var(--text-muted)',
  };

  // Group entries by date
  const groups = {};
  for (const e of entries) {
    const day = e.ts ? e.ts.slice(0, 10) : 'Unknown';
    (groups[day] = groups[day] || []).push(e);
  }

  el.innerHTML = Object.entries(groups).map(([day, items]) => `
    <div style="margin-bottom:18px">
      <div style="font-size:.74em;font-weight:700;color:var(--text-muted);letter-spacing:.06em;
           text-transform:uppercase;margin-bottom:8px;padding-left:4px">${escHtml(day)}</div>
      ${items.map(e => {
        const color = typeColor[e.event_type] || 'var(--text-muted)';
        const ts    = e.ts ? e.ts.slice(11, 19) : '';
        let detailsHtml = '';
        if (e.details && Object.keys(e.details).length) {
          const dLines = Object.entries(e.details)
            .filter(([,v]) => v !== '' && v !== null && v !== undefined)
            .map(([k, v]) => `<span style="color:var(--text-muted)">${escHtml(k)}:</span> ${escHtml(String(v))}`)
            .join('  ·  ');
          if (dLines) detailsHtml = `
            <div style="font-size:.76em;color:var(--text-muted);margin-top:3px;
                 white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${dLines}</div>`;
        }
        return `
          <div style="display:flex;gap:10px;padding:9px 12px;border-radius:6px;
               background:var(--surface2);border:1px solid var(--border);margin-bottom:5px;
               border-left:3px solid ${color};align-items:flex-start">
            <span style="flex-shrink:0;font-size:1em">${escHtml(e.icon||'📋')}</span>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span style="font-size:.86em;font-weight:600;color:${color}">${escHtml(e.description)}</span>
                <span style="font-size:.7em;padding:1px 7px;border-radius:99px;background:var(--bg);
                     border:1px solid var(--border);color:var(--text-muted);flex-shrink:0">
                  ${escHtml(e.source || e.event_type || '')}
                </span>
              </div>
              ${detailsHtml}
            </div>
            <span style="flex-shrink:0;font-size:.74em;color:var(--text-muted);white-space:nowrap;
                 padding-top:2px">${escHtml(ts)}</span>
          </div>`;
      }).join('')}
    </div>`).join('');
}

async function clearHistory() {
  if (!confirm('Clear all activity history? This cannot be undone.')) return;
  const r = await api('/api/history/clear', {method:'POST'});
  if (r.ok) { _historyEntries = []; renderHistory([]); toast('History cleared'); }
  else toast('Failed to clear history', '#ef4444');
}

// ── Auto-updater ──────────────────────────────────────────────────────────────
  const el = document.getElementById('opt-updater-status');
  if (!el) return;
  const d = await api('/api/updater/status');
  if (d.error) {
    el.innerHTML = '<p style="color:var(--text-muted)">Updater not running yet — starts automatically with the bot.</p>';
    return;
  }
  const statusColor = {
    up_to_date: 'var(--success)', updated: 'var(--accent)',
    updating: 'var(--warning)', check_failed: 'var(--danger)',
    started: 'var(--text-muted)', initialized: 'var(--text-muted)',
  };
  const local  = d.local_sha  ? d.local_sha.slice(0,8)  : '—';
  const remote = d.remote_sha ? d.remote_sha.slice(0,8) : '—';
  const col    = statusColor[d.status] || 'var(--text-muted)';
  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px">
        <div style="font-size:.75em;color:var(--text-muted);margin-bottom:2px">INSTALLED</div>
        <code style="font-size:.9em">${escHtml(local)}</code>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px">
        <div style="font-size:.75em;color:var(--text-muted);margin-bottom:2px">LATEST ON ${escHtml((d.branch||'main').toUpperCase())}</div>
        <code style="font-size:.9em">${escHtml(remote)}</code>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:.8em;font-weight:700;color:${col}">${escHtml(d.status||'unknown')}</span>
      ${d.last_check ? `<span style="font-size:.76em;color:var(--text-muted)">Last check: ${escHtml(d.last_check.slice(0,19).replace('T',' '))} UTC</span>` : ''}
    </div>
    ${d.last_update ? `<div style="font-size:.78em;color:var(--text-muted)">Last update: ${escHtml(d.last_update.slice(0,19).replace('T',' '))} UTC</div>` : ''}
    ${d.restarted_bots && d.restarted_bots.length
      ? `<div style="font-size:.78em;color:var(--text-muted);margin-top:4px">Restarted: ${escHtml(d.restarted_bots.join(', '))}</div>` : ''}
    <div style="font-size:.76em;color:var(--text-muted);margin-top:6px">
      Polls every ${d.interval_seconds || 300}s · Repo: ${escHtml(d.repo||'F-game25/AI-EMPLOYEE')}
    </div>`;
}

async function checkForUpdates() {
  const el = document.getElementById('opt-updater-status');
  if (el) el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Checking GitHub…</p>';
  const r = await api('/api/updater/check', {method:'POST'});
  if (r.ok) {
    toast(r.message || 'Check triggered');
    setTimeout(loadUpdaterStatus, 3000);
  } else {
    toast(r.detail || 'Check failed', '#ef4444');
  }
}

async function triggerUpdate() {
  const el = document.getElementById('opt-updater-status');
  if (el) el.innerHTML = '<p style="color:var(--text-muted);font-size:.85em;padding:8px 0">⏳ Downloading update…</p>';
  const r = await api('/api/updater/update', {method:'POST'});
  if (r.ok) {
    toast(r.message || 'Update triggered — affected bots restarting…', '#22d3ee');
    setTimeout(loadUpdaterStatus, 8000);
  } else {
    toast(r.detail || 'Update failed', '#ef4444');
  }
}

// ── Nuke data ─────────────────────────────────────────────────────────────────
async function nukeData() {
  const confirm_val = document.getElementById('nuke-confirm').value;
  const el = document.getElementById('nuke-result');
  el.textContent = '⏳ Processing…';
  el.style.color = 'var(--text-muted)';
  const r = await api('/api/settings/nuke', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm: confirm_val})
  });
  if (r.ok) {
    el.style.color = 'var(--success)';
    el.textContent = `✅ Deleted ${r.deleted.length} file(s)${r.deleted.length ? ': ' + r.deleted.join(', ') : ''}`;
    document.getElementById('nuke-confirm').value = '';
    if (r.errors && r.errors.length) {
      el.textContent += ' | Errors: ' + r.errors.join(', ');
      el.style.color = 'var(--warning)';
    }
  } else {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ ' + (r.detail || 'Error');
  }
}

// ── Delete Complete Bot (two-step confirmation) ───────────────────────────────
function deleteBotStep2() {
  const c1 = document.getElementById('uninstall-check1');
  const c2 = document.getElementById('uninstall-check2');
  const el = document.getElementById('uninstall-result');
  if (!c1 || !c2) return;
  if (!c1.checked || !c2.checked) {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ Please tick both checkboxes before continuing.';
    return;
  }
  el.textContent = '';
  document.getElementById('uninstall-step2').style.display = 'block';
  document.getElementById('uninstall-confirm').focus();
}

function deleteBotCancel() {
  document.getElementById('uninstall-step2').style.display = 'none';
  document.getElementById('uninstall-confirm').value = '';
  document.getElementById('uninstall-check1').checked = false;
  document.getElementById('uninstall-check2').checked = false;
  const el = document.getElementById('uninstall-result');
  el.textContent = '';
}

async function deleteBotFinal() {
  const confirm_val = document.getElementById('uninstall-confirm').value;
  const el = document.getElementById('uninstall-result');
  el.style.color = 'var(--text-muted)';
  el.textContent = '⏳ Stopping all bots and removing installation…';
  const r = await api('/api/settings/uninstall', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({confirm: confirm_val})
  });
  if (r.ok) {
    el.style.color = 'var(--success)';
    el.textContent = '✅ AI Employee has been fully uninstalled. You can close this tab.';
    // Disable all further interaction
    document.querySelectorAll('#tab-options button, #tab-options input').forEach(b => b.disabled = true);
  } else {
    el.style.color = 'var(--danger)';
    el.textContent = '❌ ' + (r.detail || 'Uninstall failed');
    document.getElementById('uninstall-confirm').value = '';
  }
}

// Auto-refresh dashboard every 30s
setInterval(() => { if (currentTab === 'dashboard') loadDashboard(); }, 30000);
</script>
</body>
</html>"""


# ─── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    nonce = secrets.token_urlsafe(16)
    html = INDEX_HTML.replace("__CSP_NONCE__", nonce)
    csp = (
        "default-src 'self'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'"
    )
    return HTMLResponse(content=html, headers={"Content-Security-Policy": csp})


# ── Security endpoints (openclaw-2) ───────────────────────────────────────────

class _HealthResponse(BaseModel):
    status: str
    version: str
    secure_mode: bool
    privacy_mode: bool


class _UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12)


class _TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.get("/health", response_model=_HealthResponse)
def health_check():
    """Health-check endpoint — always responds with current security posture."""
    return _HealthResponse(
        status="healthy",
        version=_security_config.app_version if _security_config else "2.0.0",
        secure_mode=_SECURITY_AVAILABLE,
        privacy_mode=(
            not _security_config.privacy.telemetry_enabled
            if _security_config else True
        ),
    )


@app.get("/security/status")
def security_status():
    """Return the current security configuration posture and any warnings."""
    warnings = validate_security_config(_security_config) if _security_config else []
    return JSONResponse({
        "secure_mode": _SECURITY_AVAILABLE,
        "encryption_enabled": (
            _security_config.privacy.encrypt_data_at_rest if _security_config else False
        ),
        "rate_limiting_enabled": (
            _security_config.security.rate_limit_enabled if _security_config else False
        ),
        "external_calls_blocked": (
            _security_config.privacy.external_api_calls_disabled if _security_config else False
        ),
        "telemetry_disabled": (
            not _security_config.privacy.telemetry_enabled if _security_config else True
        ),
        "security_module_loaded": _SECURITY_AVAILABLE,
        "warnings": warnings,
    })


@app.post("/auth/register", response_model=_TokenResponse,
          status_code=status.HTTP_201_CREATED)
@_auth_rate_limit
def auth_register(request: Request, user_data: _UserCreate):
    """
    Register a dashboard user and return a JWT bearer token.

    Password is validated against the configured strength policy (openclaw-2).
    Rate limited to 5 requests/minute per IP to prevent abuse.
    """
    if not _SECURITY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security module not available. Install security dependencies.",
        )

    cfg = _security_config
    is_valid, err_msg = PasswordValidator.validate(
        user_data.password,
        min_length=cfg.security.min_password_length if cfg else 12,
        require_special=cfg.security.require_special_chars if cfg else True,
        require_numbers=cfg.security.require_numbers if cfg else True,
        require_uppercase=cfg.security.require_uppercase if cfg else True,
    )
    if not is_valid:
        _audit_logger.warning(json.dumps({
            "event": "registration_failed",
            "reason": "weak_password",
            "username": user_data.username,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

    username = InputSanitizer.sanitize_input(user_data.username, max_length=50)

    # ── Persist user with bcrypt-hashed password ───────────────────────────────
    _users_file = STATE_DIR / "users.json"
    try:
        users: dict = json.loads(_users_file.read_text()) if _users_file.exists() else {}
    except Exception as _ue:
        logger.warning("users.json could not be parsed (%s) — starting with empty store", _ue)
        users = {}
    if username in users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Username already exists.")
    auth = AuthManager(
        secret_key=(cfg.security.jwt_secret_key if cfg else _jwt_secret_env),
        algorithm=(cfg.security.jwt_algorithm if cfg else "HS256"),
        expire_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )
    users[username] = {"password_hash": auth.hash_password(user_data.password)}
    _users_file.parent.mkdir(parents=True, exist_ok=True)
    _users_file.write_text(json.dumps(users, indent=2))
    _users_file.chmod(0o600)

    token = auth.create_access_token({"sub": username, "type": "user"})
    _audit_logger.info(json.dumps({
        "event": "user_registered",
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    return _TokenResponse(access_token=token)


class _LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


@app.post("/auth/login", response_model=_TokenResponse)
@_auth_rate_limit
def auth_login(request: Request, login_data: _LoginRequest):
    """
    Authenticate a registered user and return a JWT bearer token.

    Rate limited to 5 requests/minute per IP to prevent brute-force attacks.
    Returns the same 401 error for both unknown user and wrong password (no user enumeration).
    """
    if not _SECURITY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security module not available.",
        )

    cfg = _security_config
    username = InputSanitizer.sanitize_input(login_data.username, max_length=50)

    _users_file = STATE_DIR / "users.json"
    try:
        users: dict = json.loads(_users_file.read_text()) if _users_file.exists() else {}
    except Exception as _ue:
        logger.warning("users.json could not be parsed (%s) — treating as empty", _ue)
        users = {}

    _generic_fail = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_record = users.get(username)
    auth = AuthManager(
        secret_key=(cfg.security.jwt_secret_key if cfg else _jwt_secret_env),
        algorithm=(cfg.security.jwt_algorithm if cfg else "HS256"),
        expire_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )

    if not user_record or not auth.verify_password(
        login_data.password, user_record.get("password_hash", "")
    ):
        _audit_logger.warning(json.dumps({
            "event": "login_failed",
            "username": username,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        raise _generic_fail

    token = auth.create_access_token({"sub": username, "type": "user"})
    _audit_logger.info(json.dumps({
        "event": "login_success",
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    return _TokenResponse(access_token=token)

# ── End security endpoints ─────────────────────────────────────────────────────


@app.get("/api/status")
def get_status():
    state_file = STATE_DIR / "problem-solver.state.json"
    if state_file.exists():
        try:
            return JSONResponse(json.loads(state_file.read_text()))
        except Exception:
            pass
    return JSONResponse({"ts": None, "bots": [], "note": "No state yet. Start problem-solver."})


@app.get("/api/doctor")
def get_doctor():
    rc, out = ai_employee("doctor")
    return JSONResponse({"output": out, "rc": rc})


@app.post("/api/bots/start-all")
def start_all_bots():
    rc, out = ai_employee("start", "--all")
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/stop-all")
def stop_all_bots():
    rc, out = ai_employee("stop", "--all")
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/start")
def start_bot(payload: dict):
    bot = payload.get("bot", "")
    _validate_bot_name(bot)
    rc, out = ai_employee("start", bot)
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/stop")
def stop_bot(payload: dict):
    bot = payload.get("bot", "")
    _validate_bot_name(bot)
    rc, out = ai_employee("stop", bot)
    return JSONResponse({"ok": rc == 0, "output": out})


@app.get("/api/workers")
def get_workers():
    bots = []
    if BOTS_DIR.exists():
        for d in sorted(BOTS_DIR.iterdir()):
            if d.is_dir():
                pid_file = AI_HOME / "run" / f"{d.name}.pid"
                running = False
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        os.kill(pid, 0)
                        running = True
                    except Exception:
                        pass
                bots.append({"name": d.name, "running": running})
    return JSONResponse({"bots": bots})


# ─── Chat ─────────────────────────────────────────────────────────────────────

# ── Chatlog sanitizer — strip accidental API key leakage ─────────────────────
_API_KEY_PATTERN = re.compile(
    r"(sk-ant-[a-zA-Z0-9\-]{20,}|sk-[a-zA-Z0-9]{20,}|AIza[a-zA-Z0-9\-_]{30,})",
    re.IGNORECASE,
)

def _sanitize_for_log(text: str) -> str:
    """Replace any API key patterns with [REDACTED] before writing to chatlog."""
    return _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)


@app.get("/api/chat")
def get_chat():
    messages = []
    if CHATLOG.exists():
        try:
            for line in CHATLOG.read_text().splitlines():
                if line.strip():
                    messages.append(json.loads(line))
        except Exception:
            pass
    return JSONResponse({"messages": messages[-100:]})


@app.post("/api/chat")
def post_chat(payload: dict):
    raw_message = (payload or {}).get("message", "").strip()
    if not raw_message:
        raise HTTPException(400, "message required")

    # Enforce max length and strip null bytes; redact any accidental API keys
    if _SECURITY_AVAILABLE:
        message = InputSanitizer.sanitize_input(raw_message, max_length=10000)
    else:
        message = raw_message[:10000].replace("\x00", "")
    message = _sanitize_for_log(message)

    entry = {"ts": now_iso(), "type": "user", "message": message}
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Simple command handling
    response = handle_command(message)
    safe_response = _sanitize_for_log(response)
    resp_entry = {"ts": now_iso(), "type": "bot", "message": safe_response}
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(resp_entry) + "\n")

    _log_activity(
        "agent_command",
        f"Command: {message[:120]}",
        details={"command": message[:500], "response_preview": safe_response[:200]},
        source="chat",
    )
    return JSONResponse({"ok": True, "response": response})


def handle_command(message: str) -> str:
    msg_lower = message.lower().strip()

    if msg_lower in ("status", "s"):
        rc, out = ai_employee("status")
        return f"Bot status:\n{out}" if out.strip() else "No status data."

    if msg_lower in ("workers", "w"):
        rc, out = ai_employee("status")
        return f"Workers:\n{out}"

    if msg_lower.startswith("start "):
        bot = message[6:].strip()
        if not _BOT_NAME_RE.match(bot):
            return f"Invalid bot name '{bot}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}."
        rc, out = ai_employee("start", bot)
        return f"Started {bot}. {out}"

    if msg_lower.startswith("stop "):
        bot = message[5:].strip()
        if not _BOT_NAME_RE.match(bot):
            return f"Invalid bot name '{bot}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}."
        rc, out = ai_employee("stop", bot)
        return f"Stopped {bot}. {out}"

    # ── Task configuration commands ───────────────────────────────────────────
    if msg_lower in ("task status", "task list"):
        plans = _load_task_plans()
        active = next((p for p in plans if p.get("status") in ("running", "planning")), None)
        if active:
            subs = active.get("subtasks", [])
            done = sum(1 for s in subs if s.get("status") == "done")
            agents_used = ", ".join({s.get("agent_id","?") for s in subs if s.get("agent_id")})
            return (
                f"🚀 Active task: {active.get('title','?')}\n"
                f"Status: {active.get('status')} | Mode: {active.get('mode','auto')}\n"
                f"Progress: {done}/{len(subs)} subtasks\n"
                f"Agents: {agents_used or '—'}"
            )
        recent = [p for p in plans[:5] if p.get("status") not in ("running", "planning")]
        if recent:
            lines = [f"• {p.get('title','?')[:40]} [{p.get('status')}]" for p in recent]
            return "No active task. Recent tasks:\n" + "\n".join(lines)
        return "No tasks found."

    if msg_lower == "task cancel":
        plans = _load_task_plans()
        for p in plans:
            if p.get("status") in ("running", "planning"):
                p["status"] = "cancelled"
                p["completed_at"] = now_iso()
                _save_task_plans(plans)
                return f"🛑 Cancelled task: {p.get('title','?')}"
        return "No active task to cancel."

    # task agents <agent1,agent2,...> — set agents for next task submitted via WhatsApp
    if msg_lower.startswith("task agents "):
        agents_raw = message[12:].strip()
        agent_list = [a.strip() for a in agents_raw.replace(";", ",").split(",") if a.strip()]
        capabilities = _load_agent_capabilities()
        valid = list(capabilities.get("agents", {}).keys())
        invalid = [a for a in agent_list if a not in valid]
        if invalid:
            return (
                f"❌ Unknown agents: {', '.join(invalid)}\n"
                f"Available: {', '.join(valid[:10])}…\n"
                f"Tip: use exact IDs e.g. company-builder, finance-wizard"
            )
        # Store in a temp config file so next 'task <description>' via WhatsApp uses them
        _task_cfg_file = CONFIG_DIR / "whatsapp_task_config.json"
        cfg = {}
        if _task_cfg_file.exists():
            try:
                cfg = json.loads(_task_cfg_file.read_text())
            except Exception:
                pass
        cfg["agents"] = agent_list
        _task_cfg_file.write_text(json.dumps(cfg))
        return f"✅ Agents set for next task: {', '.join(agent_list)}\nNow send: task <description>"

    # task mode auto|parallel|single
    if msg_lower.startswith("task mode "):
        mode = message[10:].strip().lower()
        if mode not in ("auto", "parallel", "single"):
            return "❌ Valid modes: auto, parallel, single\nExample: task mode parallel"
        _task_cfg_file = CONFIG_DIR / "whatsapp_task_config.json"
        cfg = {}
        if _task_cfg_file.exists():
            try:
                cfg = json.loads(_task_cfg_file.read_text())
            except Exception:
                pass
        cfg["mode"] = mode
        _task_cfg_file.write_text(json.dumps(cfg))
        mode_desc = {"auto": "🧠 Orchestrator decides agent assignments", "parallel": "⚡ All selected agents run simultaneously", "single": "1️⃣ Only first/best agent runs"}[mode]
        return f"✅ Task mode set to: {mode}\n{mode_desc}\nNext task will use this mode."

    # task config — show current WhatsApp task config
    if msg_lower in ("task config", "task settings"):
        _task_cfg_file = CONFIG_DIR / "whatsapp_task_config.json"
        cfg = {}
        if _task_cfg_file.exists():
            try:
                cfg = json.loads(_task_cfg_file.read_text())
            except Exception:
                pass
        agents = cfg.get("agents", [])
        mode = cfg.get("mode", "auto")
        return (
            f"📋 Current task config:\n"
            f"Mode: {mode}\n"
            f"Agents: {', '.join(agents) if agents else 'auto-select'}\n"
            f"\nChange with:\n"
            f"  task mode <auto|parallel|single>\n"
            f"  task agents <agent1,agent2>\n"
            f"  task agents clear"
        )

    # task agents clear
    if msg_lower in ("task agents clear", "task agents reset"):
        _task_cfg_file = CONFIG_DIR / "whatsapp_task_config.json"
        if _task_cfg_file.exists():
            try:
                cfg = json.loads(_task_cfg_file.read_text())
                cfg.pop("agents", None)
                _task_cfg_file.write_text(json.dumps(cfg))
            except Exception:
                pass
        return "✅ Agent selection cleared. Next task will use auto-select."

    # ── Worker bundle commands ─────────────────────────────────────────────────
    # worker list
    if msg_lower in ("worker list", "workers list", "workers"):
        bundles = _load_worker_bundles()
        if not bundles:
            return "🏭 No worker bundles yet.\nCreate one: worker create <name> agents:<a1,a2> task:<description>"
        lines = []
        for b in bundles:
            enabled_tag = "✅" if b.get("enabled", True) else "⏸"
            agents_short = ", ".join((b.get("agents") or [])[:3])
            if len(b.get("agents") or []) > 3:
                agents_short += f" +{len(b['agents'])-3} more"
            lines.append(f"{enabled_tag} *{b['name']}* [{b.get('schedule','manual')}]\n   Agents: {agents_short}")
        return f"🏭 Worker Bundles ({len(bundles)}):\n\n" + "\n\n".join(lines)

    # worker create <name> agents:<a1,a2> task:<description>
    if msg_lower.startswith("worker create "):
        rest = message[14:].strip()
        # Parse agents: param
        import re as _re
        agents_match = _re.search(r'agents:\s*([\w,\- ]+?)(?:\s+task:|$)', rest, _re.IGNORECASE)
        task_match = _re.search(r'task:\s*(.+)', rest, _re.IGNORECASE)
        worker_name = _re.split(r'\s+agents:', rest, flags=_re.IGNORECASE)[0].strip()
        if not worker_name:
            return "❌ Usage: worker create <name> agents:<a1,a2> task:<description>"
        agents_raw = agents_match.group(1).strip() if agents_match else ""
        agent_list = [a.strip() for a in agents_raw.replace(";", ",").split(",") if a.strip()] if agents_raw else []
        task_desc = task_match.group(1).strip() if task_match else ""
        if not task_desc:
            return "❌ Usage: worker create <name> agents:<a1,a2> task:<description>"
        if not agent_list:
            return "❌ Specify at least one agent: agents:order-processor,support-bot"
        # Validate agents
        capabilities = _load_agent_capabilities()
        valid_agents = set(capabilities.get("agents", {}).keys())
        invalid = [a for a in agent_list if a not in valid_agents]
        if invalid:
            return (f"❌ Unknown agents: {', '.join(invalid)}\n"
                    f"Available: {', '.join(list(valid_agents)[:10])}…")
        import uuid as _uuid
        bundle = {
            "id": _uuid.uuid4().hex[:10],
            "name": worker_name,
            "description": "Created via WhatsApp",
            "task_description": task_desc,
            "schedule": "continuous",
            "agents": agent_list,
            "enabled": True,
            "created_at": now_iso(),
            "last_run": None,
        }
        bundles = _load_worker_bundles()
        bundles.append(bundle)
        _save_worker_bundles(bundles)
        return (f"✅ Worker created: *{worker_name}*\n"
                f"Agents: {', '.join(agent_list)}\n"
                f"Task: {task_desc[:80]}\n"
                f"Use *worker run {worker_name}* to trigger it now.")

    # worker run <name>
    if msg_lower.startswith("worker run "):
        w_name = message[11:].strip()
        bundles = _load_worker_bundles()
        match = next((b for b in bundles if b["name"].lower() == w_name.lower()), None)
        if not match:
            names = [b["name"] for b in bundles]
            return f"❌ Worker '{w_name}' not found.\nKnown workers: {', '.join(names) or '(none)'}"
        agents = match.get("agents", [])
        agents_str = f" [agents:{','.join(agents)}]" if agents else ""
        msg = f"task {match.get('task_description','')}{agents_str}"
        entry = {"ts": now_iso(), "type": "user", "message": msg}
        CHATLOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHATLOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        match["last_run"] = now_iso()
        _save_worker_bundles(bundles)
        return (f"▶ Worker *{match['name']}* triggered!\n"
                f"Agents: {', '.join(agents)}\n"
                f"Check *task status* for progress.")

    # worker enable / disable <name>
    if msg_lower.startswith("worker enable ") or msg_lower.startswith("worker disable "):
        enable = msg_lower.startswith("worker enable ")
        w_name = message[14:].strip() if enable else message[15:].strip()
        bundles = _load_worker_bundles()
        match = next((b for b in bundles if b["name"].lower() == w_name.lower()), None)
        if not match:
            return f"❌ Worker '{w_name}' not found. Use *worker list* to see workers."
        match["enabled"] = enable
        _save_worker_bundles(bundles)
        return f"{'✅ Enabled' if enable else '⏸ Disabled'}: *{match['name']}*"

    # worker delete <name>
    if msg_lower.startswith("worker delete "):
        w_name = message[14:].strip()
        bundles = _load_worker_bundles()
        remaining = [b for b in bundles if b["name"].lower() != w_name.lower()]
        if len(remaining) == len(bundles):
            return f"❌ Worker '{w_name}' not found. Use *worker list* to see workers."
        _save_worker_bundles(remaining)
        return f"🗑 Worker '{w_name}' deleted."

    # worker status <name>
    if msg_lower.startswith("worker status "):
        w_name = message[14:].strip()
        bundles = _load_worker_bundles()
        match = next((b for b in bundles if b["name"].lower() == w_name.lower()), None)
        if not match:
            return f"❌ Worker '{w_name}' not found. Use *worker list* to see workers."
        agents = ", ".join(match.get("agents") or [])
        last = match.get("last_run") or "Never"
        enabled = "✅ Enabled" if match.get("enabled", True) else "⏸ Disabled"
        return (f"🏭 Worker: *{match['name']}*\n"
                f"Status: {enabled}\n"
                f"Schedule: {match.get('schedule','manual')}\n"
                f"Agents: {agents}\n"
                f"Task: {match.get('task_description','')[:100]}\n"
                f"Last run: {last}")

    # worker ecom — create the e-commerce preset worker
    if msg_lower in ("worker ecom", "worker ecom preset", "ecom worker"):
        ecom_agents = ["order-processor","support-bot","bookkeeper","inventory-sync","email-marketer","social-poster","product-researcher","ecom-dashboard"]
        capabilities = _load_agent_capabilities()
        known = set(capabilities.get("agents", {}).keys())
        available = [a for a in ecom_agents if a in known]
        import uuid as _uuid
        bundle = {
            "id": _uuid.uuid4().hex[:10],
            "name": "E-commerce Automation Worker",
            "description": "Full 100% automated e-commerce operation",
            "task_description": "Run the full e-commerce automation pipeline: process new orders, handle customer support, sync inventory, run email campaigns, post to social media, research new products, and generate daily P&L reports.",
            "schedule": "continuous",
            "agents": available,
            "enabled": True,
            "created_at": now_iso(),
            "last_run": None,
        }
        bundles = _load_worker_bundles()
        # Avoid duplicate
        if not any(b["name"] == bundle["name"] for b in bundles):
            bundles.append(bundle)
            _save_worker_bundles(bundles)
        return (f"🛒 E-commerce Worker created!\n"
                f"Agents ({len(available)}): {', '.join(available)}\n"
                f"Use *worker run E-commerce Automation Worker* to start.")

    # cmds / commands — show command categories
    if msg_lower in ("cmds", "commands", "cmd list"):
        return (
            "📜 Command categories — open *📜 Commands* tab in dashboard for full list.\n\n"
            "⚙️ System: status, workers, start/stop <bot>\n"
            "🏭 Workers: worker list, worker create, worker run, worker enable/disable, worker delete, worker ecom\n"
            "🚀 Tasks: task <desc>, task agents <a1,a2>, task mode <m>, task config, task cancel\n"
            "🏢 Company: company build/validate/plan/simulate/gtm/pitch/org/swot\n"
            "🪙 Crypto: memecoin create/tokenomics/whitepaper, crypto <pair>, signals\n"
            "💰 Finance: finance model/pl/runway/raise/unit/pricing/pitch/valuation\n"
            "👔 HR: hr hire/jd/screen/interview/onboard/review/org/culture\n"
            "🎨 Brand: brand identity/name/position/voice/messaging/story/audit\n"
            "📈 Growth: growth loop/funnel/abtests/retention/referral/plg\n"
            "📋 PM: pm start/breakdown/sprint/roadmap/risks/raci/gantt/retro\n"
            "✍️ Content: content/social/video/newsletter/course\n"
            "💼 Sales: leads/outreach/email/recruit/websales\n"
            "Type *help* for the full command list."
        )

    if msg_lower == "help":
        return (
            "Available commands:\n"
            "  status / workers — bot status\n"
            "  start <bot> / stop <bot> — control bots\n"
            "  schedule / improvements — view tasks & proposals\n"
            "  skills / agents — skills library & custom agents\n"
            "  worker list — list all worker bundles\n"
            "  worker create <name> agents:<a1,a2> task:<desc> — create bundle\n"
            "  worker run <name> — trigger a worker now\n"
            "  worker enable/disable/delete/status <name> — manage workers\n"
            "  worker ecom — create full e-commerce automation worker\n"
            "  research <query> — web research\n"
            "  find <topic> / web search <query> / latest news <topic>\n"
            "  social <brief> — full social media content package\n"
            "  social plan <brief> — strategy plan only\n"
            "  content <brief> — same as social\n"
            "  leads <niche> <location> — local business lead generation\n"
            "  leads real-estate <location> — real estate leads\n"
            "  leads status / leads pipeline / leads followup\n"
            "  recruit <role> <requirements> — find candidates\n"
            "  recruit screen <cv_text> — AI CV screening\n"
            "  recruit candidates / recruit status\n"
            "  ecom research <niche> — trending product research\n"
            "  ecom listing <product> — generate full product listing\n"
            "  ecom email <type> <product> — email marketing flow\n"
            "  ecom trends / ecom ads <product>\n"
            "  creator plan <topic> — 30-day content calendar\n"
            "  creator dm-funnel <style> — DM funnel sequence\n"
            "  creator upsell <tier> — upsell scripts\n"
            "  creator brand <name> <niche> — full brand kit\n"
            "  signals — current trading signals (Telegram/Discord)\n"
            "  signal daily — daily market summary\n"
            "  signal post <analysis> — post a manual signal\n"
            "  community update — community newsletter\n"
            "  prospect <niche> <location> — appointment setter prospects\n"
            "  outreach <campaign> — generate outreach campaign\n"
            "  pipeline / setter followup / setter scripts\n"
            "  newsletter create <topic> — generate newsletter issue\n"
            "  newsletter subscribe <email> — add subscriber\n"
            "  newsletter send <issue_id> — send newsletter\n"
            "  chatbot create <niche> — build niche chatbot\n"
            "  chatbot flow <niche> — conversation flow\n"
            "  chatbot scripts <niche> — response scripts\n"
            "  video <topic> — faceless video full pipeline\n"
            "  video script <topic> — video script only\n"
            "  video seo <topic> — YouTube SEO pack\n"
            "  video tiktok <topic> — TikTok short-form\n"
            "  pod research <niche> — print-on-demand trends\n"
            "  pod design <niche> — AI design prompts\n"
            "  pod listing <product> — full POD listing\n"
            "  pod ads <product> — ad copy\n"
            "  course create <topic> — full course package\n"
            "  course outline <topic> — course structure\n"
            "  course lesson <module> <title> — lesson content\n"
            "  course market <topic> — marketing pack\n"
            "  arb scan <product> — arbitrage scan\n"
            "  arb trends — hot arbitrage categories\n"
            "  arb opportunities / arb watchlist\n"
            "  task <description> — multi-agent orchestration\n"
            "  task status / task list / task cancel\n"
            "  agents — list all 20 AI agents\n"
            "  assign <agent> <subtask> — manual agent dispatch\n"
            "  company build <idea> — build a company from scratch\n"
            "  company validate / plan / simulate / gtm / pitch / org / swot\n"
            "  memecoin create <concept> — full token launch package\n"
            "  memecoin name / tokenomics / whitepaper / community / viral\n"
            "  hr hire <role> — full hiring package\n"
            "  hr jd / screen / interview / onboard / review / org / culture\n"
            "  finance model <business> — full financial model\n"
            "  finance pl / runway / raise / unit / pricing / pitch / valuation\n"
            "  brand identity <company> — full brand system\n"
            "  brand name / position / voice / messaging / story / audit\n"
            "  growth loop <product> — viral growth loop\n"
            "  growth funnel / abtests / retention / referral / plg / experiments\n"
            "  pm start <project> — kick off a project\n"
            "  pm breakdown / sprint / roadmap / risks / raci / gantt / retro\n"
            "  help — this help"
        )

    if msg_lower in ("schedule", "schedules"):
        if SCHEDULES_FILE.exists():
            try:
                tasks = json.loads(SCHEDULES_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                tasks = []
            if tasks:
                lines = [f"• {t.get('label',t.get('id'))} ({t.get('action')})" for t in tasks[:10]]
                return "Scheduled tasks:\n" + "\n".join(lines)
        return "No scheduled tasks."

    if msg_lower in ("improvements", "i"):
        if IMPROVEMENTS_FILE.exists():
            try:
                items = json.loads(IMPROVEMENTS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                items = []
            pending = [i for i in items if i.get("status") == "pending"]
            if pending:
                lines = [f"• {i.get('title', i.get('id'))}" for i in pending[:5]]
                return f"{len(pending)} pending proposals:\n" + "\n".join(lines) + "\nGo to UI > Improvements to approve."
        return "No pending improvements."

    # ── Skills commands (pass-through; skills-manager processes these) ──
    if (msg_lower.startswith("skills") or msg_lower.startswith("agents")
            or msg_lower.startswith("agent ") or msg_lower.startswith("create agent")
            or msg_lower.startswith("add skill") or msg_lower.startswith("remove skill")
            or msg_lower.startswith("delete agent")):
        if SKILLS_LIBRARY_FILE.exists():
            try:
                lib = json.loads(SKILLS_LIBRARY_FILE.read_text())
                total = len(lib.get("skills", []))
                cats = len(lib.get("categories", []))
                return (
                    f"📚 Skills Library: {total} skills in {cats} categories.\n"
                    "The skills-manager is processing your command — check the chat in a moment.\n"
                    "Tip: open the *🛠️ Skills* tab in the dashboard for the full interactive UI."
                )
            except (json.JSONDecodeError, OSError):
                pass
        return "Skills library not loaded yet. Ensure skills-manager is running."

    # ── Research commands (pass-through; web-researcher processes these) ──
    if (msg_lower.startswith("research ") or msg_lower.startswith("find ")
            or msg_lower.startswith("web search ") or msg_lower.startswith("search web ")
            or msg_lower.startswith("latest news ") or msg_lower.startswith("news about ")
            or msg_lower.startswith("lookup ")):
        web_bot_state = STATE_DIR / "web-researcher.state.json"
        if web_bot_state.exists():
            try:
                st = json.loads(web_bot_state.read_text())
                if st.get("status") == "running":
                    return (
                        "🔍 Research request queued — web-researcher bot is processing it.\n"
                        "The answer will appear in the chat shortly."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🔍 Research request noted — ensure web-researcher bot is running.\n"
            "Start it: `start web-researcher`"
        )

    # ── Social media commands (pass-through; social-media-manager processes these) ──
    if (msg_lower.startswith("social ") or msg_lower.startswith("content ")
            or msg_lower.startswith("create content ") or msg_lower.startswith("create social ")):
        social_bot_state = STATE_DIR / "social-media-manager.state.json"
        if social_bot_state.exists():
            try:
                st = json.loads(social_bot_state.read_text())
                if st.get("status") == "running":
                    return (
                        "🎨 Content creation request queued — social-media-manager bot is processing it.\n"
                        "Full content package will appear in the chat shortly (30-90 seconds)."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🎨 Content request noted — ensure social-media-manager bot is running.\n"
            "Start it: `start social-media-manager`"
        )

    # ── Pass-through routing helper ───────────────────────────────────────────
    def _bot_passthrough(prefixes: list, bot_name: str, emoji: str, desc: str) -> str | None:
        """Return a pass-through ack if msg matches any prefix, else None."""
        if not any(msg_lower.startswith(p) for p in prefixes):
            return None
        st_file = STATE_DIR / f"{bot_name}.state.json"
        if st_file.exists():
            try:
                st = json.loads(st_file.read_text())
                if st.get("status") == "running":
                    return (
                        f"{emoji} Request queued — {bot_name} bot is processing it.\n"
                        f"Result will appear in chat shortly."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return f"{emoji} {desc}\nStart it: `start {bot_name}`"

    # Special handler for 'task <description>' — injects stored agent/mode config
    if msg_lower.startswith("task "):
        # Load stored WhatsApp task config
        _task_cfg_file = CONFIG_DIR / "whatsapp_task_config.json"
        _task_cfg: dict = {}
        if _task_cfg_file.exists():
            try:
                _task_cfg = json.loads(_task_cfg_file.read_text())
            except Exception:
                pass
        _agents_hint = _task_cfg.get("agents", [])
        _mode_hint = _task_cfg.get("mode", "auto")
        desc_part = message[5:].strip()
        # Append hints to the chat message for task-orchestrator to parse
        agents_str = f" [agents:{','.join(_agents_hint)}]" if _agents_hint else ""
        mode_str = f" [mode:{_mode_hint}]" if _mode_hint and _mode_hint != "auto" else ""
        enriched_msg = f"task {desc_part}{agents_str}{mode_str}"
        entry = {"ts": now_iso(), "type": "user", "message": enriched_msg}
        CHATLOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHATLOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        config_note = ""
        if _agents_hint:
            config_note = f"\nAgents: {', '.join(_agents_hint)} | Mode: {_mode_hint}"
        elif _mode_hint and _mode_hint != "auto":
            config_note = f"\nMode: {_mode_hint}"
        else:
            config_note = "\nAgents: auto-selected | Mode: auto"
        return (
            f"🚀 Task queued: '{desc_part[:60]}'{config_note}\n"
            f"Tip: use *task config* to see/change agent settings."
        )

    for _prefixes, _bot, _emoji, _desc in [
        (["leads ", "outreach "], "lead-generator", "📋", "Lead generator not running."),
        (["recruit "], "recruiter", "👔", "Recruiter not running."),
        (["ecom "], "ecom-agent", "🛒", "Ecom agent not running."),
        (["creator "], "creator-agency", "🎭", "Creator agency not running."),
        (["signals", "signal ", "community update"], "signal-community", "📊", "Signal community not running."),
        (["prospect ", "pipeline", "setter "], "appointment-setter", "📅", "Appointment setter not running."),
        (["newsletter "], "newsletter-bot", "📧", "Newsletter bot not running."),
        (["chatbot "], "chatbot-builder", "🤖", "Chatbot builder not running."),
        (["video "], "faceless-video", "🎬", "Faceless video bot not running."),
        (["pod "], "print-on-demand", "👕", "Print-on-demand bot not running."),
        (["course "], "course-creator", "🎓", "Course creator not running."),
        (["arb "], "arbitrage-bot", "💹", "Arbitrage bot not running."),
        (["orchestrate "], "task-orchestrator", "🚀", "Task orchestrator not running. Start it: `start task-orchestrator`"),
        (["company "], "company-builder", "🏢", "Company builder not running. Start it: `start company-builder`"),
        (["memecoin "], "memecoin-creator", "🪙", "Memecoin creator not running. Start it: `start memecoin-creator`"),
        (["hr "], "hr-manager", "👔", "HR manager not running. Start it: `start hr-manager`"),
        (["finance "], "finance-wizard", "💰", "Finance wizard not running. Start it: `start finance-wizard`"),
        (["brand "], "brand-strategist", "🎨", "Brand strategist not running. Start it: `start brand-strategist`"),
        (["growth "], "growth-hacker", "🚀", "Growth hacker not running. Start it: `start growth-hacker`"),
        (["pm "], "project-manager", "📋", "Project manager not running. Start it: `start project-manager`"),
    ]:
        _reply = _bot_passthrough(_prefixes, _bot, _emoji, _desc)
        if _reply is not None:
            return _reply

    # ── ROI / Metrics commands ────────────────────────────────────────────────
    if msg_lower in ("metrics", "roi", "stats", "kpis"):
        data = _load_metrics()
        s = data.get("summary", {})
        lines = [
            "📊 ROI Summary",
            f"Tasks completed : {s.get('tasks_completed', 0)}",
            f"Leads generated : {s.get('leads_generated', 0)}",
            f"Emails sent     : {s.get('emails_sent', 0)}",
            f"Content created : {s.get('content_created', 0)}",
            f"Hours saved     : {s.get('hours_saved', 0):.1f}h",
            f"Cost saved      : €{s.get('cost_saved', 0):.0f}",
            f"Revenue tracked : €{s.get('revenue', 0):.0f}",
            "",
            "Open *📈 ROI* tab for full dashboard.",
        ]
        return "\n".join(lines)

    if msg_lower.startswith("metrics record "):
        parts = message[15:].strip().split(":")
        event_type = parts[0].strip() if parts else "custom"
        value = None
        if len(parts) > 1:
            try:
                value = float(parts[1].strip())
            except ValueError:
                pass
        valid_types = list(_HOURS_PER_EVENT.keys())
        if event_type not in valid_types:
            return f"❌ Unknown type. Valid: {', '.join(valid_types)}"
        data = _load_metrics()
        events = data.get("events", [])
        import uuid as _uuid
        events.append({"id": _uuid.uuid4().hex[:8], "type": event_type, "value": value, "ts": now_iso(), "agent": "manual"})
        data["events"] = events[-500:]
        data["summary"] = _recalc_summary(data["events"])
        _save_metrics(data)
        return f"✅ Recorded: {event_type}" + (f" · €{value:.0f}" if value else "")

    # ── Guardrails commands ───────────────────────────────────────────────────
    if msg_lower in ("guardrails", "pending approvals", "approvals"):
        data = _load_guardrails()
        pending = data.get("pending", [])
        if not pending:
            return "🔒 Guardrails: No pending approvals. All clear!"
        lines = [f"🔒 {len(pending)} pending approval(s):"]
        for a in pending[:5]:
            lines.append(f"  [{a['id']}] {a.get('action_type','?')} by {a.get('agent','?')} — risk:{a.get('risk_level','?')}")
        lines.append("\nOpen *🔒 Guardrails* tab to approve/reject.")
        return "\n".join(lines)

    if msg_lower.startswith("approve "):
        action_id = message[8:].strip()
        data = _load_guardrails()
        pending = data.get("pending", [])
        action = next((a for a in pending if a["id"] == action_id), None)
        if not action:
            return f"❌ Action '{action_id}' not found in pending queue."
        action["status"] = "approved"
        action["resolved_at"] = now_iso()
        data["pending"] = [a for a in pending if a["id"] != action_id]
        data.setdefault("log", []).append(action)
        data["log"] = data["log"][-200:]
        _save_guardrails(data)
        return f"✅ Action {action_id} approved."

    if msg_lower.startswith("reject "):
        action_id = message[7:].strip()
        data = _load_guardrails()
        pending = data.get("pending", [])
        action = next((a for a in pending if a["id"] == action_id), None)
        if not action:
            return f"❌ Action '{action_id}' not found in pending queue."
        action["status"] = "rejected"
        action["resolved_at"] = now_iso()
        data["pending"] = [a for a in pending if a["id"] != action_id]
        data.setdefault("log", []).append(action)
        data["log"] = data["log"][-200:]
        _save_guardrails(data)
        return f"🚫 Action {action_id} rejected."

    # ── Memory commands ───────────────────────────────────────────────────────
    if msg_lower in ("memory", "clients", "crm"):
        data = _load_memory()
        clients = list(data.get("clients", {}).values())
        if not clients:
            return "🧠 Memory: No clients yet.\nAdd one: `client add <name> <company>`"
        lines = [f"🧠 {len(clients)} client(s) in memory:"]
        for c in clients[:10]:
            status = c.get("status", "prospect")
            lines.append(f"  • {c['name']} ({c.get('company','?')}) [{status}]")
        if len(clients) > 10:
            lines.append(f"  … and {len(clients)-10} more. Open *🧠 Memory* tab for full list.")
        return "\n".join(lines)

    if msg_lower.startswith("client add "):
        rest = message[11:].strip().split(" ", 1)
        name = rest[0] if rest else ""
        company = rest[1] if len(rest) > 1 else None
        if not name:
            return "❌ Usage: client add <name> [company]"
        data = _load_memory()
        clients = data.get("clients", {})
        import re as _re
        import uuid as _uuid
        client_id = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-") or _uuid.uuid4().hex[:8]
        clients[client_id] = {
            "id": client_id, "name": name, "company": company,
            "status": "prospect", "interactions": 0, "added_at": now_iso(), "updated_at": now_iso(),
        }
        data["clients"] = clients
        _save_memory(data)
        return f"✅ Client added: {name}" + (f" ({company})" if company else "")

    # ── Templates commands ────────────────────────────────────────────────────
    if msg_lower in ("templates", "template list"):
        templates = _load_templates()
        if not templates:
            return "📋 No templates found."
        lines = [f"📋 {len(templates)} available templates:"]
        for t in templates:
            roi = (t.get("expected_results") or {}).get("estimated_monthly_revenue") or (t.get("expected_results") or {}).get("estimated_monthly_savings") or ""
            roi_str = f" · {roi}" if roi else ""
            lines.append(f"  {t.get('icon','📋')} {t['name']}{roi_str}")
        lines.append("\nDeploy: `template deploy <id>` or use *📋 Templates* tab.")
        return "\n".join(lines)

    if msg_lower.startswith("template deploy "):
        tmpl_id = message[16:].strip()
        templates = _load_templates()
        tmpl = next((t for t in templates if t["id"] == tmpl_id), None)
        if not tmpl:
            ids = [t["id"] for t in templates]
            return f"❌ Template '{tmpl_id}' not found.\nAvailable: {', '.join(ids)}"
        import uuid as _uuid
        agents = tmpl.get("agents") or []
        bundle = {
            "id": _uuid.uuid4().hex[:10],
            "name": tmpl["name"],
            "description": tmpl.get("description", "")[:200],
            "task_description": tmpl.get("task_description", ""),
            "schedule": tmpl.get("schedule", "manual"),
            "agents": agents,
            "enabled": True,
            "template_id": tmpl_id,
            "created_at": now_iso(),
            "last_run": None,
        }
        bundles = _load_worker_bundles()
        bundles.append(bundle)
        _save_worker_bundles(bundles)
        return (f"🚀 Template deployed: *{tmpl['name']}*\n"
                f"Agents: {', '.join(agents)}\n"
                f"Schedule: {tmpl.get('schedule','manual')}\n"
                f"Use `worker run {tmpl['name']}` to start it now.")


    if _AI_ROUTER_AVAILABLE:
        try:
            result = _query_ai(
                message,
                system_prompt=(
                    "You are an AI employee assistant. "
                    "Help the user with their task or question concisely and practically. "
                    "If the task requires running a specific bot command, suggest the right command."
                ),
            )
            if result.get("answer"):
                provider = result.get("provider", "ai")
                suffix = f"\n_[{provider}]_" if provider not in ("error",) else ""
                return result["answer"] + suffix
        except Exception as exc:
            logger.debug("handle_command: AI router error — %s", exc)

    return (
        f"Task queued: '{message}'\n"
        "Tip: use 'start <bot>', 'stop <bot>', 'status', 'help' for commands."
    )


# ─── Schedules ────────────────────────────────────────────────────────────────

@app.get("/api/schedules")
def get_schedules():
    if SCHEDULES_FILE.exists():
        try:
            return JSONResponse({"tasks": json.loads(SCHEDULES_FILE.read_text())})
        except Exception:
            pass
    return JSONResponse({"tasks": []})


@app.post("/api/schedules")
def add_schedule(task: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    if SCHEDULES_FILE.exists():
        try:
            tasks = json.loads(SCHEDULES_FILE.read_text())
        except Exception:
            pass

    task_id = task.get("id", "")
    if not task_id:
        raise HTTPException(400, "id required")

    # Replace if exists
    tasks = [t for t in tasks if t.get("id") != task_id]
    tasks.append(task)
    SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    return JSONResponse({"ok": True})


@app.delete("/api/schedules/{task_id}")
def delete_schedule(task_id: str):
    if not SCHEDULES_FILE.exists():
        return JSONResponse({"ok": True})
    try:
        tasks = json.loads(SCHEDULES_FILE.read_text())
        tasks = [t for t in tasks if t.get("id") != task_id]
        SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    except Exception as e:
        raise HTTPException(500, str(e))
    return JSONResponse({"ok": True})


# ─── Improvements ─────────────────────────────────────────────────────────────

@app.get("/api/improvements")
def get_improvements():
    if IMPROVEMENTS_FILE.exists():
        try:
            return JSONResponse({"improvements": json.loads(IMPROVEMENTS_FILE.read_text())})
        except Exception:
            pass
    return JSONResponse({"improvements": []})


@app.patch("/api/improvements/{improvement_id}")
def review_improvement(improvement_id: str, payload: dict):
    status = payload.get("status", "")
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be 'approved' or 'rejected'")

    if not IMPROVEMENTS_FILE.exists():
        raise HTTPException(404, "no improvements found")

    try:
        items = json.loads(IMPROVEMENTS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"improvements file is corrupt: {exc}") from exc
    found = False
    for item in items:
        if item.get("id") == improvement_id:
            item["status"] = status
            item["reviewed_at"] = now_iso()
            found = True
            break

    if not found:
        raise HTTPException(404, f"improvement {improvement_id!r} not found")

    IMPROVEMENTS_FILE.write_text(json.dumps(items, indent=2))
    return JSONResponse({"ok": True, "id": improvement_id, "status": status})


# ─── Skills Library ────────────────────────────────────────────────────────────

@app.get("/api/skills")
def get_skills(category: str = "", q: str = ""):
    lib = {}
    if SKILLS_LIBRARY_FILE.exists():
        try:
            lib = json.loads(SKILLS_LIBRARY_FILE.read_text())
        except Exception:
            pass
    skills = lib.get("skills", [])
    categories = lib.get("categories", sorted({s["category"] for s in skills}))
    if category:
        skills = [s for s in skills if s["category"].lower() == category.lower()]
    if q:
        ql = q.lower()
        skills = [
            s for s in skills
            if (ql in s["id"].lower() or ql in s["name"].lower()
                or ql in s["description"].lower()
                or any(ql in t.lower() for t in s.get("tags", [])))
        ]
    return JSONResponse({"skills": skills, "categories": categories, "total": len(skills)})


# ─── Custom Agents ─────────────────────────────────────────────────────────────

def _load_library():
    if SKILLS_LIBRARY_FILE.exists():
        try:
            return json.loads(SKILLS_LIBRARY_FILE.read_text())
        except Exception:
            pass
    return {"skills": []}


def _load_custom_agents() -> dict:
    if CUSTOM_AGENTS_FILE.exists():
        try:
            return json.loads(CUSTOM_AGENTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_custom_agents(agents: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_AGENTS_FILE.write_text(json.dumps(agents, indent=2))


def _build_system_prompt(name: str, skill_ids: list, library: dict) -> str:
    skills_map = {s["id"]: s for s in library.get("skills", [])}
    lines = [f"You are {name}, a specialised AI assistant with the following expertise:", ""]
    for sid in skill_ids:
        s = skills_map.get(sid)
        if s:
            lines.append(f"- **{s['name']}** ({s['category']}): {s['description']}")
        else:
            lines.append(f"- {sid}")
    lines += ["", "Apply your full expertise when responding. Be precise, actionable, and thorough."]
    return "\n".join(lines)


@app.get("/api/agents/custom")
def list_custom_agents():
    agents = _load_custom_agents()
    result = []
    for a in agents.values():
        result.append({
            "id": a["id"],
            "name": a["name"],
            "description": a.get("description", ""),
            "skills": a.get("skills", []),
            "skill_count": len(a.get("skills", [])),
            "created_at": a.get("created_at", ""),
            "updated_at": a.get("updated_at", ""),
        })
    return JSONResponse({"agents": result})


@app.post("/api/agents/custom")
def create_custom_agent(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    skill_ids = [str(s).strip() for s in (payload.get("skills") or []) if str(s).strip()]
    description = (payload.get("description") or "").strip()

    library = _load_library()
    known_ids = {s["id"] for s in library.get("skills", [])}
    valid_ids = [s for s in skill_ids if s in known_ids][:20]
    unknown = [s for s in skill_ids if s not in known_ids]

    import re as _re
    agent_id = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    agents = _load_custom_agents()
    ts = now_iso()
    agent = {
        "id": agent_id,
        "name": name,
        "description": description,
        "skills": valid_ids,
        "created_at": agents.get(agent_id, {}).get("created_at", ts),
        "updated_at": ts,
        "system_prompt": _build_system_prompt(name, valid_ids, library),
    }
    agents[agent_id] = agent
    _save_custom_agents(agents)
    return JSONResponse({
        "ok": True,
        "id": agent_id,
        "skill_count": len(valid_ids),
        "unknown_skills": unknown,
    })


@app.delete("/api/agents/custom/{agent_id}")
def delete_custom_agent(agent_id: str):
    agents = _load_custom_agents()
    if agent_id not in agents:
        raise HTTPException(404, f"agent '{agent_id}' not found")
    del agents[agent_id]
    _save_custom_agents(agents)
    return JSONResponse({"ok": True})


@app.get("/api/agents/custom/{agent_id}")
def get_custom_agent(agent_id: str):
    agents = _load_custom_agents()
    if agent_id not in agents:
        raise HTTPException(404, f"agent '{agent_id}' not found")
    return JSONResponse(agents[agent_id])


# ─── Task Orchestration API ────────────────────────────────────────────────────

AGENT_CAPS_FILE = CONFIG_DIR / "agent_capabilities.json"
TASK_PLANS_FILE = CONFIG_DIR / "task_plans.json"
AGENT_TASKS_DIR = STATE_DIR / "agent_tasks"
WORKER_BUNDLES_FILE = CONFIG_DIR / "worker_bundles.json"


def _load_worker_bundles() -> list:
    if not WORKER_BUNDLES_FILE.exists():
        return []
    try:
        return json.loads(WORKER_BUNDLES_FILE.read_text())
    except Exception:
        return []


def _save_worker_bundles(bundles: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_BUNDLES_FILE.write_text(json.dumps(bundles, indent=2))


# ─── Worker Bundle API ────────────────────────────────────────────────────────

@app.get("/api/workers/bundles")
def list_worker_bundles():
    """List all worker bundles."""
    return JSONResponse({"bundles": _load_worker_bundles()})


@app.post("/api/workers/bundles")
def create_worker_bundle(payload: dict):
    """Create a new worker bundle."""
    import uuid as _uuid
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    agents = payload.get("agents") or []
    if not agents:
        raise HTTPException(400, "at least one agent required")
    task_description = (payload.get("task_description") or "").strip()
    if not task_description:
        raise HTTPException(400, "task_description required")
    schedule = (payload.get("schedule") or "manual").strip()
    description = (payload.get("description") or "").strip()
    enabled = payload.get("enabled", True)

    # Validate agents
    capabilities = _load_agent_capabilities()
    known_agents = set(capabilities.get("agents", {}).keys())
    invalid = [a for a in agents if a not in known_agents]
    if invalid:
        raise HTTPException(400, f"Unknown agents: {', '.join(invalid)}")

    bundle = {
        "id": _uuid.uuid4().hex[:10],
        "name": name,
        "description": description,
        "task_description": task_description,
        "schedule": schedule,
        "agents": agents,
        "enabled": enabled,
        "created_at": now_iso(),
        "last_run": None,
    }
    bundles = _load_worker_bundles()
    bundles.append(bundle)
    _save_worker_bundles(bundles)
    return JSONResponse({"ok": True, "bundle": bundle})


@app.patch("/api/workers/bundles/{bundle_id}")
def update_worker_bundle(bundle_id: str, payload: dict):
    """Update an existing worker bundle."""
    bundles = _load_worker_bundles()
    for b in bundles:
        if b["id"] == bundle_id:
            for field in ("name", "description", "task_description", "schedule", "agents", "enabled"):
                if field in payload:
                    b[field] = payload[field]
            b["updated_at"] = now_iso()
            _save_worker_bundles(bundles)
            return JSONResponse({"ok": True, "bundle": b})
    raise HTTPException(404, f"bundle '{bundle_id}' not found")


@app.delete("/api/workers/bundles/{bundle_id}")
def delete_worker_bundle(bundle_id: str):
    """Delete a worker bundle."""
    bundles = _load_worker_bundles()
    remaining = [b for b in bundles if b["id"] != bundle_id]
    if len(remaining) == len(bundles):
        raise HTTPException(404, f"bundle '{bundle_id}' not found")
    _save_worker_bundles(remaining)
    return JSONResponse({"ok": True})


@app.post("/api/workers/bundles/{bundle_id}/run")
def run_worker_bundle(bundle_id: str):
    """Manually trigger a worker bundle — submits its task to the orchestrator chatlog."""
    bundles = _load_worker_bundles()
    for b in bundles:
        if b["id"] != bundle_id:
            continue
        desc = b.get("task_description", "")
        agents = b.get("agents", [])
        agents_str = f" [agents:{','.join(agents)}]" if agents else ""
        msg = f"task {desc}{agents_str}"
        entry = {"ts": now_iso(), "type": "user", "message": msg}
        CHATLOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHATLOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        b["last_run"] = now_iso()
        _save_worker_bundles(bundles)
        return JSONResponse({"ok": True, "message": f"Worker '{b['name']}' triggered", "agents": agents})
    raise HTTPException(404, f"bundle '{bundle_id}' not found")


def _load_agent_capabilities() -> dict:
    if not AGENT_CAPS_FILE.exists():
        return {}
    try:
        return json.loads(AGENT_CAPS_FILE.read_text())
    except Exception:
        return {}


def _load_task_plans() -> list:
    if not TASK_PLANS_FILE.exists():
        return []
    try:
        return json.loads(TASK_PLANS_FILE.read_text())
    except Exception:
        return []


def _save_task_plans(plans: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TASK_PLANS_FILE.write_text(json.dumps(plans, indent=2))


@app.post("/api/task/submit")
def submit_task(payload: dict):
    """Submit a task for multi-agent orchestration via chatlog.
    Accepts optional 'agents' list and 'mode' string.
    """
    description = (payload.get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description required")

    agents: list = payload.get("agents") or []
    mode: str = (payload.get("mode") or "auto").strip()

    # Build the chat message so task-orchestrator can pick it up
    agents_hint = ""
    if agents:
        agents_hint = f" [agents:{','.join(agents)}]"
    mode_hint = f" [mode:{mode}]" if mode and mode != "auto" else ""
    task_msg = f"task {description}{agents_hint}{mode_hint}"

    entry = {"ts": now_iso(), "type": "user", "message": task_msg}
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Create a pending plan entry so the UI can show it immediately
    import uuid as _uuid
    task_id = _uuid.uuid4().hex[:12]
    plan = {
        "id": task_id,
        "title": description[:80],
        "status": "planning",
        "mode": mode,
        "agents_hint": agents,
        "subtasks": [],
        "created_at": now_iso(),
    }
    plans = _load_task_plans()
    plans.insert(0, plan)
    _save_task_plans(plans[:50])  # keep last 50

    return JSONResponse({"ok": True, "task_id": task_id, "message": f"Task submitted: {description[:60]}", "agents": agents, "mode": mode})


@app.post("/api/task/cancel")
def cancel_task():
    """Cancel the currently running task plan."""
    plans = _load_task_plans()
    for p in plans:
        if p.get("status") in ("running", "planning"):
            p["status"] = "cancelled"
            p["completed_at"] = now_iso()
            _save_task_plans(plans)
            return JSONResponse({"ok": True, "cancelled_id": p["id"]})
    return JSONResponse({"ok": False, "message": "No active task found"})


@app.post("/api/task/reassign")
def reassign_subtask(payload: dict):
    """Reassign a pending subtask to a different agent."""
    task_id = (payload.get("task_id") or "").strip()
    subtask_id = (payload.get("subtask_id") or "").strip()
    agent_id = (payload.get("agent_id") or "").strip()
    if not all([task_id, subtask_id, agent_id]):
        raise HTTPException(400, "task_id, subtask_id, and agent_id are required")

    # Validate agent exists
    capabilities = _load_agent_capabilities()
    if agent_id not in capabilities.get("agents", {}):
        raise HTTPException(400, f"Unknown agent '{agent_id}'")

    plans = _load_task_plans()
    for p in plans:
        if p.get("id") != task_id:
            continue
        for st in p.get("subtasks", []):
            if (st.get("subtask_id") or st.get("id")) == subtask_id:
                if st.get("status") not in ("pending", "failed"):
                    raise HTTPException(400, f"Can only reassign pending/failed subtasks (current: {st.get('status')})")
                old = st.get("agent_id")
                st["agent_id"] = agent_id
                st["status"] = "pending"
                _save_task_plans(plans)
                return JSONResponse({"ok": True, "subtask_id": subtask_id, "old_agent": old, "new_agent": agent_id})
        raise HTTPException(404, f"Subtask '{subtask_id}' not found in task '{task_id}'")
    raise HTTPException(404, f"Task '{task_id}' not found")


# Agent keyword→category scoring map used by auto-select.
# Keys use task-description vocabulary (not agent skill IDs), so this intentionally
# differs from agent_capabilities.json.  It is derived from each agent's specialties
# and kept here for fast, dependency-free lookup.  Update when adding new agents.
_AGENT_KEYWORDS: dict[str, list[str]] = {
    "company-builder":   ["company", "startup", "build", "launch", "found", "business plan", "enterprise", "venture", "gtm", "go-to-market", "mvp", "market entry", "b2b", "b2c"],
    "brand-strategist":  ["brand", "logo", "identity", "name", "naming", "visual", "design", "positioning", "voice", "messaging", "tagline", "story", "rebrand"],
    "finance-wizard":    ["finance", "financial", "revenue", "profit", "pl", "p&l", "model", "valuation", "fundrais", "investor", "pitch", "vc", "budget", "unit economics", "burn", "runway", "cac", "ltv"],
    "hr-manager":        ["hire", "hiring", "recruit", "hr", "team", "culture", "onboard", "job description", "interview", "employee", "headcount", "org chart", "talent", "people"],
    "growth-hacker":     ["grow", "growth", "viral", "funnel", "retention", "referral", "plg", "activation", "conversion", "ab test", "churn", "user acquisition", "marketing channel"],
    "project-manager":   ["project", "sprint", "roadmap", "milestone", "gantt", "risk", "plan", "timeline", "deadline", "deliverable", "backlog", "agile", "scrum", "scope"],
    "content-master":    ["content", "blog", "article", "seo", "write", "copywrite", "post", "long-form", "keyword", "headline", "editorial"],
    "social-guru":       ["social", "instagram", "twitter", "tiktok", "linkedin", "facebook", "viral post", "caption", "hashtag", "reel", "story", "thread", "community"],
    "intel-agent":       ["research", "competitor", "market", "intelligence", "swot", "analyse", "analyze", "landscape", "benchmark", "trend", "industry", "sector"],
    "lead-hunter":       ["lead", "prospect", "b2b list", "cold outreach", "decision maker", "crm", "pipeline", "contact list"],
    "email-ninja":       ["email", "cold email", "drip", "sequence", "deliverability", "open rate", "subject line", "newsletter email"],
    "creative-studio":   ["ad", "creative", "banner", "image prompt", "ad copy", "campaign", "visual", "design brief"],
    "crypto-trader":     ["crypto", "bitcoin", "ethereum", "trade", "trading", "chart", "technical analysis", "signal", "defi", "altcoin"],
    "memecoin-creator":  ["memecoin", "token", "tokenomics", "whitepaper", "web3", "nft", "meme coin", "launch token", "smart contract"],
    "data-analyst":      ["data", "analytics", "dashboard", "kpi", "metric", "report", "insight", "survey", "statistic"],
    "support-bot":       ["support", "faq", "ticket", "customer service", "helpdesk", "escalat", "sentiment", "complaint", "refund", "customer complaint", "help desk", "return", "exchange"],
    "product-scout":     ["product", "ecommerce", "shopify", "amazon", "arbitrage", "dropship", "supplier", "niche product", "trend product"],
    "bot-dev":           ["code", "develop", "python", "script", "api", "bot", "automate", "integration", "endpoint", "webhook"],
    "web-sales":         ["website", "landing page", "ux", "conversion rate", "seo audit", "pitch website", "sales page"],
    "orchestrator":      ["coordinate", "orchestrate", "multi-agent", "full pipeline", "end-to-end", "all agents"],
    # Ecom agents
    "order-processor":   ["order", "shopify", "webhook", "printful", "fulfill", "dispatch", "tracking", "payment validation", "supplier order"],
    "bookkeeper":        ["bookkeeping", "accounting", "p&l", "expense", "stripe data", "quickbooks", "tax", "profit report", "daily report"],
    "inventory-sync":    ["inventory", "stock", "reorder", "supplier sync", "demand forecast", "low stock", "out of stock", "printful sync"],
    "email-marketer":    ["email campaign", "mailchimp", "welcome email", "abandoned cart", "drip sequence", "newsletter campaign", "segment customers"],
    "social-poster":     ["tiktok post", "instagram post", "twitter post", "social schedule", "viral script", "auto post", "social media automation"],
    "product-researcher":["product research", "trending product", "tiktok trend", "amazon trend", "junglescout", "product listing", "auto-list", "shopify product"],
    "ecom-dashboard":    ["ecom metrics", "revenue report", "profit margin report", "daily digest", "order analytics", "ecommerce kpi", "ecom dashboard"],
    # Niche Growth Agency specialists
    "lead-hunter-elite": ["leads hunt", "b2b leads", "lead scraping", "qualify leads", "enrich crm", "lead enrichment", "icp scoring", "find leads", "hunt leads", "lead list", "prospect list", "decision maker"],
    "cold-outreach-assassin": ["cold outreach", "cold sequence", "outreach sequence", "email sequence", "linkedin sequence", "whatsapp outreach", "multi-channel outreach", "follow-up sequence", "ab test outreach", "reply rate", "cold email campaign"],
    "sales-closer-pro": ["close deal", "closing", "objection", "negotiate", "negotiation", "sales script", "deal close", "handle objection", "sales closer", "spin sell", "meddic", "sales pipeline"],
    "linkedin-growth-hacker": ["linkedin growth", "linkedin profile", "linkedin content", "linkedin campaign", "linkedin audience", "linkedin connections", "linkedin post", "linkedin optimize", "ssi score", "linkedin leads"],
    "ad-campaign-wizard": ["paid ads", "meta ads", "google ads", "linkedin ads", "facebook ads", "ad campaign", "ad copy", "roas", "budget allocation", "ad performance", "ppc", "cpm", "performance marketing"],
    "referral-rocket": ["referral program", "referral", "viral referral", "refer a friend", "referral incentive", "referral tracking", "ambassador program", "word of mouth", "k-factor"],
    "partnership-matchmaker": ["partnership", "joint venture", "jv partner", "affiliate partner", "co-marketing", "partnership pitch", "partner scoring", "business development", "biz dev", "strategic alliance"],
    "conversion-rate-optimizer": ["conversion rate", "cro", "funnel optimization", "ab test", "a/b test", "landing page cro", "checkout optimization", "conversion funnel", "funnel analysis", "funnel leak", "optimize conversion"],
}


@app.post("/api/task/auto-agents")
def auto_select_agents(payload: dict):
    """Return suggested agent IDs for a given task description using keyword scoring."""
    description = (payload.get("description") or "").strip().lower()
    if not description:
        raise HTTPException(400, "description required")

    scores: dict[str, int] = {}
    for agent_id, keywords in _AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in description)
        if score > 0:
            scores[agent_id] = score

    # Sort by score descending; take top agents covering the task
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Always include at least 1; cap at 6 unless the description is very broad
    max_agents = 6 if len(description) > 80 else 4
    suggested = [aid for aid, _ in ranked[:max_agents]]

    # If nothing matched, fall back to orchestrator
    if not suggested:
        suggested = ["orchestrator"]

    # Attach reasons
    reasons = {aid: [kw for kw in _AGENT_KEYWORDS.get(aid, []) if kw in description][:3] for aid in suggested}

    return JSONResponse({"suggested": suggested, "scores": dict(ranked[:max_agents]), "reasons": reasons})


@app.get("/api/task/list")
def list_tasks():
    """List all task plans (active and history)."""
    plans = _load_task_plans()
    return JSONResponse({"plans": plans[:20]})


@app.get("/api/task/status/{task_id}")
def get_task_status(task_id: str):
    """Get status of a specific task plan."""
    plans = _load_task_plans()
    for p in plans:
        if p.get("id") == task_id:
            return JSONResponse(p)
    raise HTTPException(404, f"task '{task_id}' not found")


@app.get("/api/agents")
def get_all_agents():
    """Get all 20 agents with capabilities and running status."""
    capabilities = _load_agent_capabilities()
    agents_config = capabilities.get("agents", {})

    result = []
    for agent_id, info in agents_config.items():
        pid_file = AI_HOME / "run" / f"{agent_id}.pid"
        running = False
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                running = True
            except Exception:
                pass

        # Get current state if available
        state_file = STATE_DIR / f"{agent_id}.state.json"
        current_task = None
        if state_file.exists():
            try:
                st = json.loads(state_file.read_text())
                current_task = st.get("active_plan_title") or st.get("current_task")
            except Exception:
                pass

        result.append({
            "id": agent_id,
            "description": info.get("description", ""),
            "category": info.get("category", ""),
            "skills": info.get("skills", []),
            "commands": info.get("commands", []),
            "specialties": info.get("specialties", []),
            "parallel_capable": info.get("parallel_capable", True),
            "running": running,
            "current_task": current_task,
        })

    return JSONResponse({"agents": result, "total": len(result)})



# ─── ROI Metrics API ─────────────────────────────────────────────────────────

# Cost-per-hour estimate used to calculate cost savings from hours saved
_COST_PER_HOUR_EUR = float(os.environ.get("AI_EMPLOYEE_HOURLY_RATE", "75"))
# Hours saved estimate per task type
_HOURS_PER_EVENT = {
    "task_completed": 0.5,
    "lead_generated": 0.1,
    "email_sent": 0.05,
    "content_created": 1.5,
    "call_booked": 0.25,
    "deal_closed": 0.0,
    "ticket_resolved": 0.2,
    "custom": 0.0,
}


def _load_metrics() -> dict:
    if not METRICS_FILE.exists():
        return {"summary": {}, "events": []}
    try:
        return json.loads(METRICS_FILE.read_text())
    except Exception:
        return {"summary": {}, "events": []}


def _save_metrics(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(data, indent=2))


def _recalc_summary(events: list) -> dict:
    s: dict = {
        "tasks_completed": 0,
        "leads_generated": 0,
        "emails_sent": 0,
        "content_created": 0,
        "calls_booked": 0,
        "deals_closed": 0,
        "tickets_resolved": 0,
        "hours_saved": 0.0,
        "cost_saved": 0.0,
        "revenue": 0.0,
    }
    for e in events:
        t = e.get("type", "")
        if t == "task_completed":
            s["tasks_completed"] += 1
        elif t == "lead_generated":
            s["leads_generated"] += 1
        elif t == "email_sent":
            s["emails_sent"] += 1
        elif t == "content_created":
            s["content_created"] += 1
        elif t == "call_booked":
            s["calls_booked"] += 1
        elif t == "deal_closed":
            s["deals_closed"] += 1
            if e.get("value"):
                s["revenue"] += float(e["value"])
        elif t == "ticket_resolved":
            s["tickets_resolved"] += 1
        hours = _HOURS_PER_EVENT.get(t, 0.0)
        s["hours_saved"] += hours
    s["hours_saved"] = round(s["hours_saved"], 2)
    s["cost_saved"] = round(s["hours_saved"] * _COST_PER_HOUR_EUR, 2)
    return s


@app.get("/api/metrics")
def get_metrics():
    data = _load_metrics()
    return JSONResponse(data)


@app.post("/api/metrics")
def record_metric(payload: dict):
    import uuid as _uuid
    event_type = (payload.get("type") or "custom").strip()
    valid_types = list(_HOURS_PER_EVENT.keys())
    if event_type not in valid_types:
        event_type = "custom"
    agent = (payload.get("agent") or "").strip() or None
    value = payload.get("value")
    if value is not None:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
    notes = (payload.get("notes") or "").strip() or None

    data = _load_metrics()
    events = data.get("events", [])
    events.append({
        "id": _uuid.uuid4().hex[:10],
        "type": event_type,
        "agent": agent,
        "value": value,
        "notes": notes,
        "ts": now_iso(),
    })
    # Keep last 500 events
    data["events"] = events[-500:]
    data["summary"] = _recalc_summary(data["events"])
    _save_metrics(data)
    return JSONResponse({"ok": True, "summary": data["summary"]})


# ─── Agent Templates API ──────────────────────────────────────────────────────

def _load_templates() -> list:
    # Prefer installed copy; fall back to repo copy
    for candidate in (AGENT_TEMPLATES_FILE, _REPO_TEMPLATES_FILE):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text()).get("templates", [])
            except Exception:
                pass
    return []


@app.get("/api/templates")
def list_templates():
    return JSONResponse({"templates": _load_templates()})


@app.post("/api/templates/{template_id}/deploy")
def deploy_template(template_id: str):
    import uuid as _uuid
    templates = _load_templates()
    tmpl = next((t for t in templates if t["id"] == template_id), None)
    if not tmpl:
        raise HTTPException(404, f"Template '{template_id}' not found")

    capabilities = _load_agent_capabilities()
    known_agents = set(capabilities.get("agents", {}).keys())
    agents = [a for a in (tmpl.get("agents") or []) if a in known_agents]
    if not agents:
        # Accept unknown agents — they may be installed later
        agents = tmpl.get("agents") or []

    bundle = {
        "id": _uuid.uuid4().hex[:10],
        "name": tmpl["name"],
        "description": tmpl.get("description", "")[:200],
        "task_description": tmpl.get("task_description", ""),
        "schedule": tmpl.get("schedule", "manual"),
        "agents": agents,
        "enabled": True,
        "template_id": template_id,
        "created_at": now_iso(),
        "last_run": None,
    }
    bundles = _load_worker_bundles()
    bundles.append(bundle)
    _save_worker_bundles(bundles)
    return JSONResponse({"ok": True, "bundle_id": bundle["id"], "name": bundle["name"]})


# ─── Guardrails API ───────────────────────────────────────────────────────────

def _load_guardrails() -> dict:
    if not GUARDRAILS_FILE.exists():
        return {"pending": [], "log": [], "settings": {}, "summary": {}}
    try:
        return json.loads(GUARDRAILS_FILE.read_text())
    except Exception:
        return {"pending": [], "log": [], "settings": {}, "summary": {}}


def _save_guardrails(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    GUARDRAILS_FILE.write_text(json.dumps(data, indent=2))


def _recalc_guardrail_summary(data: dict) -> dict:
    log = data.get("log", [])
    return {
        "total": len(log),
        "approved": sum(1 for e in log if e.get("status") == "approved"),
        "rejected": sum(1 for e in log if e.get("status") == "rejected"),
        "auto_approved": sum(1 for e in log if e.get("status") == "auto_approved"),
        "pending": len(data.get("pending", [])),
    }


@app.get("/api/guardrails")
def get_guardrails():
    data = _load_guardrails()
    data["summary"] = _recalc_guardrail_summary(data)
    return JSONResponse(data)


@app.post("/api/guardrails/request")
def request_guardrail_action(payload: dict):
    """Submit an action for approval (called by agents before performing risky actions)."""
    import uuid as _uuid
    action_type = (payload.get("action_type") or "unknown").strip()
    agent = (payload.get("agent") or "system").strip()
    description = (payload.get("description") or "").strip()
    risk_level = (payload.get("risk_level") or "medium").strip()
    if risk_level not in ("low", "medium", "high"):
        risk_level = "medium"

    data = _load_guardrails()
    settings = data.get("settings", {})
    require_approval = settings.get("require_approval_for", {})

    # Map action types to setting keys
    action_key_map = {
        "send_email": "send_email",
        "email": "send_email",
        "bulk_email": "send_email",
        "social_post": "social_post",
        "post": "social_post",
        "social": "social_post",
        "tweet": "social_post",
        "publish": "social_post",
        "purchase": "make_purchase",
        "order": "make_purchase",
        "buy": "make_purchase",
        "checkout": "make_purchase",
        "delete": "delete_data",
        "remove": "delete_data",
        "drop": "delete_data",
        "api_call": "api_calls",
        "webhook": "api_calls",
    }
    # Try full action_type first, then first word of action_type
    at_lower = action_type.lower()
    at_prefix = at_lower.split("_")[0] if at_lower else ""
    setting_key = action_key_map.get(at_lower) or action_key_map.get(at_prefix, None)
    needs_approval = require_approval.get(setting_key, False) if setting_key else risk_level in ("high",)

    action = {
        "id": _uuid.uuid4().hex[:10],
        "action_type": action_type,
        "agent": agent,
        "description": description,
        "risk_level": risk_level,
        "status": "pending" if needs_approval else "auto_approved",
        "ts": now_iso(),
    }

    if needs_approval:
        data.setdefault("pending", []).append(action)
    else:
        data.setdefault("log", []).append(action)

    # Keep log to last 200 entries
    data["log"] = data.get("log", [])[-200:]
    _save_guardrails(data)
    return JSONResponse({"ok": True, "id": action["id"], "status": action["status"], "needs_approval": needs_approval})


@app.post("/api/guardrails/{action_id}/approve")
def approve_guardrail_action(action_id: str):
    data = _load_guardrails()
    pending = data.get("pending", [])
    action = next((a for a in pending if a["id"] == action_id), None)
    if not action:
        raise HTTPException(404, f"Action '{action_id}' not found in pending queue")
    action["status"] = "approved"
    action["resolved_at"] = now_iso()
    data["pending"] = [a for a in pending if a["id"] != action_id]
    data.setdefault("log", []).append(action)
    data["log"] = data["log"][-200:]
    _save_guardrails(data)
    _log_activity(
        "guardrail_approved",
        f"Guardrail action approved: {action.get('action_type', action_id)}",
        details={"action_id": action_id,
                 "action_type": action.get("action_type"),
                 "description": action.get("description", "")},
        source="guardrails",
    )
    return JSONResponse({"ok": True, "action_id": action_id})
def reject_guardrail_action(action_id: str, payload: dict = None):
    data = _load_guardrails()
    pending = data.get("pending", [])
    action = next((a for a in pending if a["id"] == action_id), None)
    if not action:
        raise HTTPException(404, f"Action '{action_id}' not found in pending queue")
    action["status"] = "rejected"
    action["resolved_at"] = now_iso()
    if payload and payload.get("reason"):
        action["reject_reason"] = payload["reason"]
    data["pending"] = [a for a in pending if a["id"] != action_id]
    data.setdefault("log", []).append(action)
    data["log"] = data["log"][-200:]
    _save_guardrails(data)
    _log_activity(
        "guardrail_rejected",
        f"Guardrail action rejected: {action.get('action_type', action_id)}",
        details={"action_id": action_id,
                 "action_type": action.get("action_type"),
                 "description": action.get("description", ""),
                 "reason": action.get("reject_reason", "")},
        source="guardrails",
    )
    return JSONResponse({"ok": True, "action_id": action_id})
def save_guardrail_settings(payload: dict):
    data = _load_guardrails()
    data["settings"] = payload
    _save_guardrails(data)
    return JSONResponse({"ok": True})


# ─── Memory API ───────────────────────────────────────────────────────────────

def _load_memory() -> dict:
    if not MEMORY_FILE.exists():
        return {"clients": {}, "recent_interactions": []}
    try:
        return json.loads(MEMORY_FILE.read_text())
    except Exception:
        return {"clients": {}, "recent_interactions": []}


def _save_memory(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2))


@app.get("/api/memory")
def get_memory():
    data = _load_memory()
    clients_list = sorted(data.get("clients", {}).values(), key=lambda c: c.get("added_at", ""), reverse=True)
    return JSONResponse({
        "clients": clients_list,
        "recent_interactions": data.get("recent_interactions", [])[-20:],
        "total_clients": len(clients_list),
    })


@app.post("/api/memory/clients")
def add_memory_client(payload: dict):
    import uuid as _uuid
    import re as _re
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    data = _load_memory()
    clients = data.get("clients", {})
    client_id = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-") or _uuid.uuid4().hex[:8]
    # Ensure unique id
    base_id = client_id
    counter = 1
    while client_id in clients:
        client_id = f"{base_id}-{counter}"
        counter += 1
    client = {
        "id": client_id,
        "name": name,
        "company": (payload.get("company") or "").strip() or None,
        "email": (payload.get("email") or "").strip() or None,
        "status": (payload.get("status") or "prospect").strip(),
        "notes": (payload.get("notes") or "").strip() or None,
        "interactions": 0,
        "added_at": now_iso(),
        "updated_at": now_iso(),
    }
    clients[client_id] = client
    data["clients"] = clients
    _save_memory(data)
    return JSONResponse({"ok": True, "id": client_id})


@app.patch("/api/memory/clients/{client_id}")
def update_memory_client(client_id: str, payload: dict):
    data = _load_memory()
    clients = data.get("clients", {})
    if client_id not in clients:
        raise HTTPException(404, f"Client '{client_id}' not found")
    client = clients[client_id]
    for field in ("name", "company", "email", "status", "notes"):
        if field in payload:
            client[field] = payload[field]
    client["updated_at"] = now_iso()
    _save_memory(data)
    return JSONResponse({"ok": True})


@app.delete("/api/memory/clients/{client_id}")
def delete_memory_client(client_id: str):
    data = _load_memory()
    clients = data.get("clients", {})
    if client_id not in clients:
        raise HTTPException(404, f"Client '{client_id}' not found")
    del clients[client_id]
    _save_memory(data)
    return JSONResponse({"ok": True})


@app.post("/api/memory/interactions")
def record_interaction(payload: dict):
    """Record a new interaction/event in memory (called by agents)."""
    data = _load_memory()
    interaction = {
        "ts": now_iso(),
        "agent": (payload.get("agent") or "system").strip(),
        "summary": (payload.get("summary") or "").strip(),
        "client_id": (payload.get("client_id") or "").strip() or None,
    }
    interactions = data.get("recent_interactions", [])
    interactions.append(interaction)
    data["recent_interactions"] = interactions[-200:]

    # Increment interaction count for client if specified
    client_id = interaction.get("client_id")
    if client_id and client_id in data.get("clients", {}):
        data["clients"][client_id]["interactions"] = data["clients"][client_id].get("interactions", 0) + 1
        data["clients"][client_id]["updated_at"] = now_iso()

    _save_memory(data)
    return JSONResponse({"ok": True})


# ─── Integrations API ─────────────────────────────────────────────────────────

_DEFAULT_INTEGRATIONS = [
    {
        "id": "gmail",
        "name": "Gmail / Google Workspace",
        "icon": "📧",
        "description": "Send and receive emails, read inbox, create drafts",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "email", "label": "Gmail address", "type": "email", "placeholder": "you@gmail.com"},
            {"key": "client_id", "label": "OAuth Client ID", "type": "text", "placeholder": "...apps.googleusercontent.com"},
            {"key": "client_secret", "label": "OAuth Client Secret", "type": "password", "placeholder": "GOCSPX-…"},
        ],
    },
    {
        "id": "google_sheets",
        "name": "Google Sheets / CRM",
        "icon": "📊",
        "description": "Read/write leads, pipeline, and data to Google Sheets",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "spreadsheet_id", "label": "Spreadsheet ID", "type": "text", "placeholder": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"},
            {"key": "service_account_json", "label": "Service Account JSON path", "type": "text", "placeholder": "/path/to/service-account.json"},
        ],
    },
    {
        "id": "telegram",
        "name": "Telegram Bot",
        "icon": "✈️",
        "description": "Send messages and receive commands via Telegram",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "bot_token", "label": "Bot Token", "type": "password", "placeholder": "123456:ABC-DEF…"},
            {"key": "chat_id", "label": "Chat / Channel ID", "type": "text", "placeholder": "-1001234567890"},
        ],
    },
    {
        "id": "slack",
        "name": "Slack",
        "icon": "💬",
        "description": "Post messages, receive commands, and manage channels via Slack",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "bot_token", "label": "Bot OAuth Token", "type": "password", "placeholder": "xoxb-…"},
            {"key": "channel", "label": "Default Channel", "type": "text", "placeholder": "#general"},
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI (Cloud Fallback)",
        "icon": "🤖",
        "description": "Use GPT-4 as a cloud AI fallback when Ollama is unavailable",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "api_key", "label": "OpenAI API Key", "type": "password", "placeholder": "sk-…"},
            {"key": "model", "label": "Model", "type": "text", "placeholder": "gpt-4o"},
        ],
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "icon": "🧠",
        "description": "Use Claude as an AI provider for complex reasoning tasks",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "api_key", "label": "Anthropic API Key", "type": "password", "placeholder": "sk-ant-…"},
            {"key": "model", "label": "Model", "type": "text", "placeholder": "claude-3-5-sonnet-20241022"},
        ],
    },
    {
        "id": "webhook",
        "name": "Outbound Webhook",
        "icon": "🔗",
        "description": "Send task results and events to any URL (Zapier, Make, n8n, custom API)",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "url", "label": "Webhook URL", "type": "url", "placeholder": "https://hooks.zapier.com/…"},
            {"key": "secret", "label": "Shared Secret (optional)", "type": "password", "placeholder": "mysecret"},
        ],
    },
]


def _load_integrations() -> list:
    if not INTEGRATIONS_FILE.exists():
        return _DEFAULT_INTEGRATIONS[:]
    try:
        saved = json.loads(INTEGRATIONS_FILE.read_text())
    except Exception:
        saved = []
    # Merge saved configs into defaults so new integrations always appear
    saved_map = {i["id"]: i for i in saved if isinstance(i, dict)}
    merged = []
    for default in _DEFAULT_INTEGRATIONS:
        intg = dict(default)
        if default["id"] in saved_map:
            intg["enabled"] = saved_map[default["id"]].get("enabled", False)
            intg["config"] = saved_map[default["id"]].get("config", {})
        merged.append(intg)
    return merged


def _save_integrations(integrations: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Only save id + enabled + config (not the field definitions)
    slim = [{"id": i["id"], "enabled": i.get("enabled", False), "config": i.get("config", {})} for i in integrations]
    INTEGRATIONS_FILE.write_text(json.dumps(slim, indent=2))


@app.get("/api/integrations")
def list_integrations():
    return JSONResponse({"integrations": _load_integrations()})


@app.patch("/api/integrations/{integration_id}")
def update_integration(integration_id: str, payload: dict):
    integrations = _load_integrations()
    intg = next((i for i in integrations if i["id"] == integration_id), None)
    if not intg:
        raise HTTPException(404, f"Integration '{integration_id}' not found")
    if "enabled" in payload:
        intg["enabled"] = bool(payload["enabled"])
    if "config" in payload and isinstance(payload["config"], dict):
        intg["config"] = payload["config"]
    _save_integrations(integrations)
    return JSONResponse({"ok": True, "id": integration_id, "enabled": intg["enabled"]})


@app.post("/api/integrations/{integration_id}/test")
def test_integration(integration_id: str):
    """Basic connectivity test for an integration."""
    integrations = _load_integrations()
    intg = next((i for i in integrations if i["id"] == integration_id), None)
    if not intg:
        raise HTTPException(404, f"Integration '{integration_id}' not found")

    config = intg.get("config", {})

    if integration_id == "webhook":
        url = config.get("url", "").strip()
        if not url:
            return JSONResponse({"ok": False, "message": "No webhook URL configured"})
        try:
            import urllib.request as _req
            req = _req.Request(url, method="POST",
                               data=b'{"test":true}',
                               headers={"Content-Type": "application/json"})
            with _req.urlopen(req, timeout=5) as resp:
                return JSONResponse({"ok": True, "message": f"HTTP {resp.status} — webhook reachable"})
        except Exception as exc:
            return JSONResponse({"ok": False, "message": str(exc)})

    if integration_id in ("openai", "anthropic"):
        key_field = "api_key"
        key = config.get(key_field, "").strip()
        if not key:
            return JSONResponse({"ok": False, "message": "No API key configured"})
        return JSONResponse({"ok": True, "message": "API key present — live test requires the key to be used in a real request"})

    if integration_id == "telegram":
        token = config.get("bot_token", "").strip()
        if not token:
            return JSONResponse({"ok": False, "message": "No bot token configured"})
        try:
            import urllib.request as _req
            url = f"https://api.telegram.org/bot{token}/getMe"
            with _req.urlopen(url, timeout=5) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    name = result.get("result", {}).get("username", "?")
                    return JSONResponse({"ok": True, "message": f"Connected as @{name}"})
                return JSONResponse({"ok": False, "message": "Telegram returned error"})
        except Exception as exc:
            return JSONResponse({"ok": False, "message": str(exc)})

    # Generic: just check required fields are filled
    required_fields = [f["key"] for f in intg.get("fields", []) if not f.get("optional")]
    missing = [k for k in required_fields if not config.get(k, "").strip()]
    if missing:
        return JSONResponse({"ok": False, "message": f"Missing required fields: {', '.join(missing)}"})
    return JSONResponse({"ok": True, "message": "Configuration looks complete — deploy agents to test live"})


# ── Settings: read/write .env + security audit + data nuke ────────────────────

_SECRET_KEYS: frozenset = frozenset({
    "JWT_SECRET_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "SENDGRID_API_KEY",
    "SMTP_PASS", "DISCORD_BOT_TOKEN", "TELEGRAM_BOT_TOKEN",
    "WHATSAPP_TOKEN", "TAVILY_API_KEY", "SERP_API_KEY",
    "NEWS_API_KEY", "ELEVEN_LABS_KEY", "ALPHA_INSIDER_KEY",
    "DISCORD_WEBHOOK_URL",
})
_MASK = "••••••••"

_SETTINGS_SCHEMA: list = [
    # (key, label, input_type, placeholder, category)
    # API Keys
    ("OPENAI_API_KEY",        "OpenAI API Key",              "password", "sk-…",                          "api_keys"),
    ("ANTHROPIC_API_KEY",     "Anthropic API Key",           "password", "sk-ant-…",                      "api_keys"),
    ("TAVILY_API_KEY",        "Tavily Search Key",           "password", "tvly-…",                        "api_keys"),
    ("SERP_API_KEY",          "SerpAPI Key",                 "password", "your-serpapi-key",              "api_keys"),
    ("NEWS_API_KEY",          "NewsAPI Key",                 "password", "your-newsapi-key",              "api_keys"),
    ("ELEVEN_LABS_KEY",       "ElevenLabs API Key",          "password", "your-elevenlabs-key",           "api_keys"),
    ("ALPHA_INSIDER_KEY",     "Alpha Insider Key",           "password", "your-key",                      "api_keys"),
    ("DISCORD_BOT_TOKEN",     "Discord Bot Token",           "password", "MTxxxxxxx",                     "api_keys"),
    ("DISCORD_WEBHOOK_URL",   "Discord Webhook URL",         "password", "https://discord.com/api/webhooks/…", "api_keys"),
    ("TELEGRAM_BOT_TOKEN",    "Telegram Bot Token",          "password", "1234567:ABC…",                  "api_keys"),
    ("TWILIO_ACCOUNT_SID",    "Twilio Account SID",          "password", "ACxxxxxxxx",                    "api_keys"),
    ("TWILIO_AUTH_TOKEN",     "Twilio Auth Token",           "password", "your-auth-token",               "api_keys"),
    ("TWILIO_WHATSAPP_FROM",  "Twilio WhatsApp Number",      "text",     "whatsapp:+14155238886",         "api_keys"),
    ("SENDGRID_API_KEY",      "SendGrid API Key",            "password", "SG.…",                          "api_keys"),
    ("WHATSAPP_TOKEN",        "WhatsApp Cloud API Token",    "password", "your-meta-token",               "api_keys"),
    ("WHATSAPP_PHONE_ID",     "WhatsApp Phone ID",           "text",     "your-phone-id",                 "api_keys"),
    ("SMTP_USER",             "SMTP Username / Email",       "text",     "you@example.com",               "api_keys"),
    ("SMTP_PASS",             "SMTP Password",               "password", "your-app-password",             "api_keys"),
    # Preferences
    ("PROBLEM_SOLVER_UI_PORT","Dashboard Port",              "text",     "8787",                          "preferences"),
    ("DASHBOARD_PORT",        "Legacy Dashboard Port",       "text",     "3000",                          "preferences"),
    ("OLLAMA_HOST",           "Ollama Host URL",             "text",     "http://localhost:11434",        "preferences"),
    ("OLLAMA_MODEL",          "Ollama Model",                "text",     "llama3.2",                      "preferences"),
    ("LOG_LEVEL",             "Log Level",                   "text",     "INFO",                          "preferences"),
    ("RATE_LIMIT_PER_MINUTE", "Rate Limit (req/min)",        "text",     "60",                            "preferences"),
    ("TASK_ORCHESTRATOR_MAX_PARALLEL", "Max Parallel Tasks", "text",    "10",                            "preferences"),
    ("TASK_ORCHESTRATOR_PEER_REVIEW",  "Peer Review",        "text",    "true",                          "preferences"),
    ("MEMORY_MAX_CONVERSATION","Memory Max Turns",           "text",     "50",                            "preferences"),
    ("EMAIL_DRY_RUN",         "Email Dry Run",               "text",     "false",                         "preferences"),
    ("WHATSAPP_DRY_RUN",      "WhatsApp Dry Run",            "text",     "false",                         "preferences"),
    ("SMTP_HOST",             "SMTP Host",                   "text",     "smtp.gmail.com",                "preferences"),
    ("SMTP_PORT",             "SMTP Port",                   "text",     "587",                           "preferences"),
    ("SMTP_FROM",             "SMTP From Address",           "text",     "you@example.com",               "preferences"),
    ("AI_EMPLOYEE_REPO",      "GitHub Repo (owner/name)",    "text",     "F-game25/AI-EMPLOYEE",          "preferences"),
    ("AI_EMPLOYEE_BRANCH",    "GitHub Branch",               "text",     "main",                          "preferences"),
    ("AI_EMPLOYEE_UPDATE_INTERVAL", "Update Poll Interval (s)", "text", "300",                           "preferences"),
]


def _env_path() -> Path:
    return AI_HOME / ".env"


def _read_env() -> dict:
    result: dict = {}
    p = _env_path()
    if not p.exists():
        return result
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            result[key] = val
    return result


def _write_env(updates: dict) -> None:
    p = _env_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
    updated_keys: set = set()
    new_lines: list = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")
    # Atomic write via temp file
    tmp = p.parent / f".env.tmp.{os.getpid()}"
    try:
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        tmp.replace(p)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    try:
        p.chmod(0o600)
    except Exception:
        pass


@app.get("/api/settings")
def get_settings():
    env = _read_env()
    result: dict = {"api_keys": [], "preferences": []}
    for key, label, input_type, placeholder, category in _SETTINGS_SCHEMA:
        raw = env.get(key, "")
        is_secret = key in _SECRET_KEYS
        result[category].append({
            "key":         key,
            "label":       label,
            "type":        input_type,
            "placeholder": placeholder,
            "value":       _MASK if (is_secret and raw) else raw,
            "has_value":   bool(raw),
        })
    return JSONResponse(result)


class _SettingsUpdateRequest(BaseModel):
    updates: dict = Field(default_factory=dict)


@app.post("/api/settings")
def save_settings(body: _SettingsUpdateRequest):
    # Skip masked values — user didn't change them
    clean = {k: v for k, v in body.updates.items() if v != _MASK and k.strip()}
    if not clean:
        return JSONResponse({"ok": True, "saved": 0})
    _write_env(clean)
    keys_saved = [k for k in clean if k not in _SECRET_KEYS]
    secret_count = sum(1 for k in clean if k in _SECRET_KEYS)
    desc = f"Settings saved: {', '.join(keys_saved)}" + (
        f" + {secret_count} secret key(s)" if secret_count else ""
    )
    _log_activity("settings_saved", desc,
                  details={"count": len(clean)}, source="dashboard")
    return JSONResponse({"ok": True, "saved": len(clean)})


@app.get("/api/settings/security-check")
def security_check():
    findings: list = []
    env = _read_env()
    cfg = _security_config

    def _add(level: str, title: str, detail: str,
             action: str = "", action_type: str = "") -> None:
        findings.append({
            "level": level, "title": title, "detail": detail,
            "action": action, "action_type": action_type,
        })

    # ── 1. JWT_SECRET_KEY changed from default placeholder ────────────────────
    jwt = env.get("JWT_SECRET_KEY", os.environ.get("JWT_SECRET_KEY", ""))
    _gen_cmd = 'python3 -c "import secrets; print(secrets.token_hex(32))"'
    if not jwt or jwt.lower() in _KNOWN_WEAK_SECRETS:
        _add("error", "JWT_SECRET_KEY is still the default placeholder",
             "Replace it with a random 64-char hex string before going to production.",
             action=_gen_cmd, action_type="command")
    elif len(jwt) < 32:
        _add("error", "JWT_SECRET_KEY is too short",
             f"Current length: {len(jwt)} chars. Minimum: 32 characters.",
             action=_gen_cmd, action_type="command")
    elif len(jwt) < 64:
        _add("warning", "JWT_SECRET_KEY could be stronger",
             f"Length {len(jwt)} is acceptable but 64+ chars is recommended.",
             action=_gen_cmd, action_type="command")
    else:
        _add("ok", "JWT_SECRET_KEY changed from default placeholder",
             f"Key length: {len(jwt)} characters.")

    # ── 2. Strong passwords configured ───────────────────────────────────────
    if cfg:
        min_len = cfg.security.min_password_length
        has_special = cfg.security.require_special_chars
        has_numbers = cfg.security.require_numbers
        has_upper = cfg.security.require_uppercase
        if min_len >= 12 and has_special and has_numbers and has_upper:
            _add("ok", "Strong passwords configured",
                 f"Min length: {min_len}, requires uppercase, numbers and special chars.")
        else:
            issues = []
            if min_len < 12:
                issues.append(f"min_password_length={min_len} (needs ≥12)")
            if not has_special:
                issues.append("require_special_chars=false")
            if not has_numbers:
                issues.append("require_numbers=false")
            if not has_upper:
                issues.append("require_uppercase=false")
            _add("warning", "Password policy not fully enforced",
                 f"Issues: {', '.join(issues)}",
                 action="Edit security.local.yml: set min_password_length≥12, "
                        "require_special_chars/numbers/uppercase: true",
                 action_type="info")
    else:
        _add("warning", "Strong passwords — config not loaded",
             "Using built-in defaults (min 12 chars, all checks enabled). "
             "Create security.local.yml to customise.")

    # ── 3. Application bound to localhost only ────────────────────────────────
    host = os.environ.get("PROBLEM_SOLVER_UI_HOST", HOST)
    if host in ("0.0.0.0", "::"):
        _add("warning", "Application NOT bound to localhost",
             f"HOST={host} — anyone on the network can reach the dashboard.",
             action="Set HOST=127.0.0.1 in ~/.ai-employee/.env",
             action_type="info")
    else:
        _add("ok", "Application bound to localhost only", f"HOST={host}")

    # ── 4. Rate limiting enabled ──────────────────────────────────────────────
    if cfg:
        if cfg.security.rate_limit_enabled:
            _add("ok", "Rate limiting enabled",
                 f"security.rate_limit_enabled=true "
                 f"({cfg.security.rate_limit_per_minute} req/min)")
        else:
            _add("error", "Rate limiting disabled",
                 "Enable it to protect against brute-force and DoS attacks.",
                 action="security.rate_limit_enabled: true",
                 action_type="config")
    else:
        _add("warning", "Rate limiting — config not loaded",
             "Defaulting to 60 req/min. Create security.local.yml to confirm.")

    # ── 5. Encryption at rest enabled ─────────────────────────────────────────
    if cfg:
        if cfg.privacy.encrypt_data_at_rest:
            _add("ok", "Encryption at rest enabled",
                 f"privacy.encrypt_data_at_rest=true "
                 f"(algorithm: {cfg.privacy.encryption_algorithm})")
        else:
            _add("error", "Encryption at rest disabled",
                 "Sensitive data is stored unencrypted.",
                 action="privacy.encrypt_data_at_rest: true",
                 action_type="config")
    else:
        _add("warning", "Encryption at rest — config not loaded",
             "Default is enabled (encrypt_data_at_rest=true). "
             "Create security.local.yml to confirm.")

    # ── 6. Telemetry disabled ─────────────────────────────────────────────────
    if cfg:
        tel = cfg.privacy.telemetry_enabled
        ana = cfg.privacy.analytics_enabled
        if not tel and not ana:
            _add("ok", "Telemetry disabled",
                 "privacy.telemetry_enabled=false, analytics_enabled=false")
        else:
            extra = []
            if tel:
                extra.append("privacy.telemetry_enabled: false")
            if ana:
                extra.append("privacy.analytics_enabled: false")
            _add("warning", "Telemetry / analytics is enabled",
                 "Disable to prevent external data collection.",
                 action="\n".join(extra), action_type="config")
    else:
        _add("ok", "Telemetry disabled",
             "Defaults: telemetry_enabled=false, analytics_enabled=false")

    # ── 7. Audit logging enabled ──────────────────────────────────────────────
    if cfg:
        if cfg.logging.audit_enabled:
            _add("ok", "Audit logging enabled",
                 "logging.audit_enabled=true — auth, file access and API calls are logged.")
        else:
            _add("error", "Audit logging disabled",
                 "Failed logins and sensitive operations will not be recorded.",
                 action="logging.audit_enabled: true",
                 action_type="config")
    else:
        _add("warning", "Audit logging — config not loaded",
             "Default is enabled (audit_enabled=true). "
             "Create security.local.yml to confirm.")

    # ── 8. Security headers verified ─────────────────────────────────────────
    if _SECURITY_AVAILABLE:
        _add("ok", "Security headers active",
             "CSP, X-Frame-Options, X-Content-Type-Options and more are set automatically.",
             action="curl -I http://127.0.0.1:8787",
             action_type="command")
    else:
        _add("warning", "Security headers — module not loaded",
             "The security module is unavailable. Verify headers manually.",
             action="curl -I http://127.0.0.1:8787",
             action_type="command")

    # ── 9. Dependencies updated ───────────────────────────────────────────────
    req_file = Path(__file__).resolve().parent / "requirements.txt"
    if req_file.exists():
        _add("info", "Dependencies — keep up to date",
             "Run this command regularly to pull the latest security patches.",
             action="pip install -r requirements.txt --upgrade",
             action_type="command")
    else:
        _add("warning", "requirements.txt not found",
             "Could not locate requirements.txt to check dependencies.")

    # ── 10. File permissions secured ──────────────────────────────────────────
    env_file = _env_path()
    sec_local = Path("security.local.yml")
    insecure: list[str] = []
    if env_file.exists():
        if env_file.stat().st_mode & 0o077:
            insecure.append(str(env_file))
    else:
        insecure.append(str(env_file) + " (missing)")
    if sec_local.exists() and sec_local.stat().st_mode & 0o077:
        insecure.append("security.local.yml")
    if insecure:
        _add("warning", "File permissions not secured",
             f"World/group-readable: {', '.join(insecure)}",
             action="chmod 600 ~/.ai-employee/.env security.local.yml",
             action_type="command")
    else:
        mode = oct(env_file.stat().st_mode & 0o777) if env_file.exists() else "N/A"
        _add("ok", "File permissions secured",
             f".env permissions: {mode}")

    # ── 11. No secrets committed to version control ───────────────────────────
    repo_root = Path(__file__).resolve().parents[3]
    git_dir = repo_root / ".git"
    gitignore = repo_root / ".gitignore"
    if git_dir.exists():
        if gitignore.exists():
            gi_content = gitignore.read_text(errors="replace")
            required = [".env", "security.local.yml", "*.key", "*.pem"]
            missing = [p for p in required if p not in gi_content]
            if not missing:
                _add("ok", "No secrets committed to version control",
                     ".env, security.local.yml, *.key and *.pem are in .gitignore")
            else:
                lines = "\n".join(missing)
                _add("warning", "Some secret patterns missing from .gitignore",
                     f"Missing entries: {', '.join(missing)}",
                     action=f"printf '{lines}' >> .gitignore",
                     action_type="command")
        else:
            _add("warning", ".gitignore not found",
                 "Create a .gitignore to prevent accidental secret commits.",
                 action="printf '.env\\nsecurity.local.yml\\n*.key\\n*.pem\\n' >> .gitignore",
                 action_type="command")
    else:
        _add("info", "No secrets check — not a git repository",
             "No .git directory found; version-control check skipped.")

    _ok  = sum(1 for f in findings if f["level"] == "ok")
    _err = sum(1 for f in findings if f["level"] == "error")
    _wrn = sum(1 for f in findings if f["level"] == "warning")
    _log_activity(
        "security_check",
        f"Security checklist run: {_ok} passed, {_err} critical, {_wrn} warnings",
        details={"passed": _ok, "errors": _err, "warnings": _wrn,
                 "total": len(findings)},
        source="security-checklist",
    )
    return JSONResponse({"findings": findings})


# ─── Activity History API ──────────────────────────────────────────────────────

_ACTIVITY_EVENT_ICONS: dict = {
    "security_check":      "🛡️",
    "security_action_done": "✅",
    "settings_saved":      "⚙️",
    "guardrail_approved":  "✅",
    "guardrail_rejected":  "🚫",
    "agent_command":       "💬",
    "task_run":            "🚀",
    "agent_started":       "▶️",
    "agent_stopped":       "⏹️",
    "worker_triggered":    "👷",
    "system":              "ℹ️",
}


@app.get("/api/history")
def get_history(limit: int = 500):
    """Return the most recent *limit* activity log entries, newest first."""
    entries: list = []
    if ACTIVITY_LOG.exists():
        try:
            for line in ACTIVITY_LOG.read_text(errors="replace").splitlines():
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    entries = entries[:limit]
    # Attach display icons
    for e in entries:
        e["icon"] = _ACTIVITY_EVENT_ICONS.get(e.get("event_type", ""), "📋")
    return JSONResponse({"entries": entries, "total": len(entries)})


class _MarkActionRequest(BaseModel):
    title: str = ""
    action: str = ""
    action_type: str = ""
    check_number: int = 0


@app.post("/api/history/mark-action")
def mark_security_action(body: _MarkActionRequest):
    """Record that the user acknowledged a security checklist action."""
    desc = f"Security action acknowledged: {body.title}" if body.title else \
           "Security checklist action acknowledged"
    _log_activity(
        "security_action_done",
        desc,
        details={
            "check_number": body.check_number,
            "title": body.title,
            "action": body.action[:200] if body.action else "",
            "action_type": body.action_type,
        },
        source="security-checklist",
    )
    return JSONResponse({"ok": True})


@app.post("/api/history/clear")
def clear_history():
    """Wipe the activity log."""
    try:
        if ACTIVITY_LOG.exists():
            ACTIVITY_LOG.unlink()
        _log_activity("system", "Activity history cleared", source="dashboard")
        return JSONResponse({"ok": True})
    except Exception as exc:
        raise HTTPException(500, str(exc))


class _NukeRequest(BaseModel):
    confirm: str = ""


@app.post("/api/settings/nuke")
def nuke_data(body: _NukeRequest):
    if body.confirm != "DELETE ALL DATA":
        raise HTTPException(
            400,
            "Confirmation text does not match. "
            "Type exactly: DELETE ALL DATA",
        )
    deleted: list = []
    errors:  list = []

    targets = [
        CHATLOG,
        ACTIVITY_LOG,
        METRICS_FILE,
        MEMORY_FILE,
        GUARDRAILS_FILE,
        IMPROVEMENTS_FILE,
        STATE_DIR / "guardrails_settings.json",
        STATE_DIR / "memory_interactions.json",
    ]
    for f in targets:
        try:
            if f.exists():
                f.unlink()
                deleted.append(f.name)
        except Exception as exc:
            errors.append(f"{f.name}: {exc}")

    # Also clear any extra .jsonl chat files
    try:
        for jsonl in STATE_DIR.glob("*.jsonl"):
            jsonl.unlink()
            deleted.append(jsonl.name)
    except Exception as exc:
        errors.append(str(exc))

    logger.warning("DATA NUKE performed — deleted: %s", deleted)
    return JSONResponse({"ok": True, "deleted": deleted, "errors": errors})


class _UninstallRequest(BaseModel):
    confirm: str = ""


@app.post("/api/settings/uninstall")
def uninstall_bot(body: _UninstallRequest):
    """Stop all bots and remove the entire AI_HOME directory tree.

    Requires the exact confirmation phrase "UNINSTALL AI EMPLOYEE".
    This endpoint stops accepting requests mid-execution since the process
    itself is inside AI_HOME — the response is sent before the directory
    is removed.
    """
    if body.confirm != "UNINSTALL AI EMPLOYEE":
        raise HTTPException(
            400,
            "Confirmation text does not match. "
            "Type exactly: UNINSTALL AI EMPLOYEE",
        )

    import shutil
    import threading

    errors: list = []

    # ── Step 1: stop all bots gracefully ──────────────────────────────────────
    ai_bin = AI_HOME / "bin" / "ai-employee"
    try:
        import subprocess as _sp
        _sp.run([str(ai_bin), "stop", "--all"], timeout=30,
                capture_output=True)
        logger.warning("UNINSTALL: all bots stopped")
    except Exception as exc:
        errors.append(f"stop-all: {exc}")
        logger.warning("UNINSTALL: stop-all warning: %s", exc)

    logger.warning("UNINSTALL initiated by user — removing %s", AI_HOME)

    # ── Step 2: remove the directory tree in a background thread ──────────────
    # We respond first so the browser gets the confirmation, then delete.
    def _do_remove():
        import time as _t
        _t.sleep(1)   # give uvicorn time to flush the HTTP response
        try:
            if AI_HOME.exists():
                shutil.rmtree(AI_HOME, ignore_errors=True)
        except Exception as exc:
            logger.error("UNINSTALL rmtree error: %s", exc)

    threading.Thread(target=_do_remove, daemon=True).start()

    return JSONResponse({
        "ok": True,
        "message": (
            "AI Employee is being uninstalled. "
            "All bots have been stopped and the installation directory "
            f"({AI_HOME}) will be deleted in seconds."
        ),
    })


# ── Updater status / trigger ──────────────────────────────────────────────────

_UPDATER_STATE_FILE = STATE_DIR / "updater.json"
_UPDATER_COMMIT_FILE = STATE_DIR / "installed_commit.txt"
_UPDATER_TRIGGER_FILE = AI_HOME / "run" / "updater.trigger"


@app.get("/api/updater/status")
def updater_status():
    try:
        if _UPDATER_STATE_FILE.exists():
            data = json.loads(_UPDATER_STATE_FILE.read_text())
            return JSONResponse(data)
    except Exception:
        pass
    # Fallback: return minimal info
    local_sha = ""
    try:
        if _UPDATER_COMMIT_FILE.exists():
            local_sha = _UPDATER_COMMIT_FILE.read_text().strip()
    except Exception:
        pass
    return JSONResponse({
        "status":    "not_started",
        "local_sha": local_sha,
        "repo":      "F-game25/AI-EMPLOYEE",
        "branch":    "main",
    })


@app.post("/api/updater/check")
def updater_check():
    """Trigger an immediate update check by writing the trigger file."""
    try:
        _UPDATER_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATER_TRIGGER_FILE.write_text("check")
        return JSONResponse({"ok": True, "message": "Check triggered — results appear in Auto Update card within seconds"})
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/updater/update")
def updater_update():
    """Trigger an immediate forced update (downloads + restarts even if already up to date)."""
    try:
        _UPDATER_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATER_TRIGGER_FILE.write_text("force")
        # Also send SIGUSR1 to the updater process if its PID is known
        try:
            if _UPDATER_STATE_FILE.exists():
                state = json.loads(_UPDATER_STATE_FILE.read_text())
                pid = state.get("pid")
                if pid:
                    import signal as _sig
                    os.kill(int(pid), _sig.SIGUSR1)
        except Exception:
            pass
        return JSONResponse({"ok": True, "message": "Update triggered — bots will restart momentarily if changes are found"})
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
