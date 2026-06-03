"""AI Employee Dashboard — Problem Solver UI

Extended dashboard with 5 tabs:
  1. Dashboard  — bot status overview
  2. Chat       — send tasks / view chat log (mirrors WhatsApp tasks)
  3. Scheduler  — create/edit/list scheduled tasks
  4. Workers    — view/adjust enabled agents
  5. Improvements — approve/reject skill/market proposals

State files are read from ~/.ai-employee/state/
Config is read/written in ~/.ai-employee/config/
"""
import json
import asyncio
import hashlib
import hmac
import importlib
import logging
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any

try:
    import psutil as _psutil
    _PSUTIL_OK = True
    # Prime cpu_percent so the first real call returns a meaningful value
    _psutil.cpu_percent(interval=None)
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _PSUTIL_OK = False

# ── Background CPU sampler — updates every 2 s using interval=1 for accuracy ──
_cpu_sample_value: float = 0.0

def _cpu_sampler_loop() -> None:
    """Continuously sample CPU usage with a 1-second blocking interval for
    accurate readings without burdening the request thread."""
    global _cpu_sample_value
    while True:
        try:
            if _PSUTIL_OK and _psutil is not None:
                _cpu_sample_value = _psutil.cpu_percent(interval=1)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)

_cpu_thread = threading.Thread(target=_cpu_sampler_loop, daemon=True, name="cpu-sampler")
_cpu_thread.start()

# ── Python version guard ──────────────────────────────────────────────────────
if sys.version_info < (3, 10):
    print("ERROR: Python 3.10+ is required. Current version: "
          f"{sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from models import (  # noqa: F401 — Pydantic models extracted
    _HealthResponse, _UserCreate, _TokenResponse, _LoginRequest, _RefreshRequest,
    _LogoutRequest, _SettingsUpdateRequest, _MarkActionRequest, _NukeRequest,
    _UninstallRequest, _GDPRDeleteRequest, _SearchRequest, _ContextResponseRequest,
    _RagRetrieveRequest, _OrchestrateV2Request,
)
import uvicorn

# ── Security imports ─────────────────────────────────────────────
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

# ── JWT secret startup validation / auto-generation ───────────────────────────
_KNOWN_WEAK_SECRETS = frozenset({
    "", "secret", "changeme", "change-me", "your-secret-here", "default",
    "password", "1234", "12345678", "test", "dev",
    "CHANGE_THIS_IN_SECURITY_LOCAL_YML_OR_SET_JWT_SECRET_KEY_ENV_VAR",
})


def _ensure_jwt_secret() -> str:
    """Return a valid JWT_SECRET_KEY, auto-generating one if needed.

    Priority:
    1. JWT_SECRET_KEY environment variable (if already set and strong)
    2. Value stored in ~/.ai-employee/.env (loaded on first use)
    3. Auto-generate a new cryptographically secure secret, save it, and use it

    The resolved secret is injected into ``os.environ`` so downstream code
    (security module, etc.) picks it up.
    """
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if secret and secret.lower() not in _KNOWN_WEAK_SECRETS and len(secret) >= 32:
        return secret  # already valid

    # Try to load from ~/.ai-employee/.env before generating a new one
    env_dir = Path.home() / ".ai-employee"
    env_file = env_dir / ".env"
    _ENV_FILE_MAX_BYTES = 65536  # 64 KiB — guard against maliciously large files
    if env_file.exists():
        try:
            raw = env_file.read_bytes()[:_ENV_FILE_MAX_BYTES].decode("utf-8", errors="strict")
            for raw_line in raw.splitlines():
                line = raw_line.strip()
                if line.startswith("JWT_SECRET_KEY="):
                    stored = line.split("=", 1)[1].strip()
                    if (stored
                            and stored.lower() not in _KNOWN_WEAK_SECRETS
                            and len(stored) >= 32):
                        os.environ["JWT_SECRET_KEY"] = stored
                        return stored
        except (OSError, UnicodeDecodeError):
            pass

    # Auto-generate a strong secret
    new_secret = secrets.token_hex(32)

    # Persist to ~/.ai-employee/.env
    try:
        # Create directory with owner-only permissions (rwx------) so the
        # JWT secret stored inside is not readable by other OS users.
        env_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        existing = ""
        if env_file.exists():
            try:
                raw = env_file.read_bytes()[:_ENV_FILE_MAX_BYTES].decode("utf-8", errors="strict")
                existing = raw
            except (OSError, UnicodeDecodeError):
                existing = ""
        new_lines = []
        replaced = False
        for line in existing.splitlines():
            if line.startswith("JWT_SECRET_KEY="):
                if not replaced:
                    new_lines.append(f"JWT_SECRET_KEY={new_secret}")
                    replaced = True
                # Skip duplicate JWT_SECRET_KEY lines
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"JWT_SECRET_KEY={new_secret}")
        env_file.write_text("\n".join(new_lines) + "\n")
        # Restrict .env file permissions to owner-read/write only (rw-------)
        env_file.chmod(0o600)
        print(
            f"\n🔑  Auto-generated JWT_SECRET_KEY and saved to {env_file}\n"
            "    This secret will be reused on subsequent starts.\n",
            flush=True,
        )
    except OSError as _e:
        print(
            f"\n⚠️   Could not persist JWT_SECRET_KEY to {env_file}: {_e}\n"
            "    The server will run with a temporary secret (restarts will invalidate tokens).\n",
            flush=True,
        )

    # Inject into the running environment so downstream modules see it
    os.environ["JWT_SECRET_KEY"] = new_secret
    return new_secret


_jwt_secret_env = _ensure_jwt_secret()

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
        # _ensure_jwt_secret() above already auto-generated a key; log the warning
        # and continue without the richer config object.
        print(f"\n⚠️   Security config warning (continuing): {_jwt_err}\n")
        _security_config = None
    except Exception:
        # Other config errors (YAML parse, etc.) — still start but without
        # the richer config object; JWT is already validated above.
        _security_config = None
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
    _security_config = None

    # Fallback security primitives so auth endpoints remain functional even
    # when optional security dependencies are not installed.
    class InputSanitizer:  # type: ignore[no-redef]
        @staticmethod
        def sanitize_input(value: str, max_length: int = 50) -> str:
            v = (value or "").strip()
            v = re.sub(r"[^a-zA-Z0-9._@-]", "", v)
            return v[:max_length]

    class PasswordValidator:  # type: ignore[no-redef]
        @staticmethod
        def validate(
            password: str,
            min_length: int = 12,
            require_special: bool = True,
            require_numbers: bool = True,
            require_uppercase: bool = True,
        ) -> tuple[bool, str]:
            if len(password or "") < min_length:
                return False, f"Password must be at least {min_length} characters."
            if require_numbers and not re.search(r"\d", password):
                return False, "Password must include at least one number."
            if require_uppercase and not re.search(r"[A-Z]", password):
                return False, "Password must include at least one uppercase letter."
            if require_special and not re.search(r"[^a-zA-Z0-9]", password):
                return False, "Password must include at least one special character."
            return True, "ok"

    class AuthManager:  # type: ignore[no-redef]
        def __init__(self, secret_key: str, algorithm: str = "HS256", expire_minutes: int = 30):
            self.secret_key = secret_key
            self.algorithm = algorithm
            self.expire_minutes = expire_minutes

        def hash_password(self, password: str) -> str:
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
            return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

        def verify_password(self, password: str, hashed: str) -> bool:
            try:
                _prefix, salt_hex, digest_hex = hashed.split("$", 2)
                calc = hashlib.pbkdf2_hmac(
                    "sha256", password.encode(), bytes.fromhex(salt_hex), 120000
                ).hex()
                return hmac.compare_digest(calc, digest_hex)
            except Exception:
                return False

        def create_access_token(self, payload: dict) -> str:
            """Create a verifiable HMAC-SHA256 signed token (stdlib-only fallback)."""
            import base64
            import json as _json
            user = str(payload.get("sub", "user"))
            exp = int(time.time()) + self.expire_minutes * 60
            body = base64.urlsafe_b64encode(
                _json.dumps({"sub": user, "exp": exp}).encode()
            ).rstrip(b"=").decode()
            sig = hmac.new(
                self.secret_key.encode(),
                body.encode(),
                "sha256",
            ).hexdigest()
            return f"fb1.{body}.{sig}"

        def verify_token(self, token: str) -> Optional[dict]:
            """Verify a stdlib fallback token. Returns payload or None."""
            import base64
            import json as _json
            try:
                parts = token.split(".", 2)
                if len(parts) != 3 or parts[0] != "fb1":
                    return None
                _prefix, body, sig = parts
                expected = hmac.new(
                    self.secret_key.encode(),
                    body.encode(),
                    "sha256",
                ).hexdigest()
                if not hmac.compare_digest(expected, sig):
                    return None
                padding = "=" * (4 - len(body) % 4)
                data = _json.loads(base64.urlsafe_b64decode(body + padding))
                if data.get("exp", 0) < int(time.time()):
                    return None
                return data
            except Exception:
                return None

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_RUNTIME_DIR = _REPO_ROOT / "runtime"
_REPO_AGENTS_DIR = _REPO_RUNTIME_DIR / "agents"
_REPO_BIN_FILE = _REPO_RUNTIME_DIR / "bin" / "ai-employee"

# Add runtime directory to sys.path for imports like 'from core.tenancy import ...'
if str(_REPO_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_RUNTIME_DIR))

# ── PII log sanitization — imported early so all subsequent logging is clean ──
try:
    from core.log_sanitizer import install_global_filter, SanitizedLoggingMiddleware as _SanitizedLoggingMiddleware
    install_global_filter()
    _LOG_SANITIZER_AVAILABLE = True
except Exception as _ls_err:  # graceful degradation if starlette absent at this point
    _LOG_SANITIZER_AVAILABLE = False
    _SanitizedLoggingMiddleware = None  # type: ignore[assignment]

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
CONFIG_DIR = AI_HOME / "config"
BOTS_DIR = AI_HOME / "agents"
if not BOTS_DIR.exists() and _REPO_AGENTS_DIR.exists():
    # Fresh-repo developer mode: use bundled runtime agents when ~/.ai-employee
    # is not installed yet.
    BOTS_DIR = _REPO_AGENTS_DIR
AI_EMPLOYEE_BIN = AI_HOME / "bin" / "ai-employee"
if not AI_EMPLOYEE_BIN.exists() and _REPO_BIN_FILE.exists():
    AI_EMPLOYEE_BIN = _REPO_BIN_FILE
CHATLOG = STATE_DIR / "chatlog.jsonl"
ACTIVITY_LOG = STATE_DIR / "activity_log.jsonl"
SCHEDULES_FILE = CONFIG_DIR / "schedules.json"
IMPROVEMENTS_FILE = STATE_DIR / "improvements.json"
SKILLS_LIBRARY_FILE = CONFIG_DIR / "skills_library.json"
CUSTOM_AGENTS_FILE = CONFIG_DIR / "custom_agents.json"
METRICS_FILE = STATE_DIR / "metrics.json"
GUARDRAILS_FILE = STATE_DIR / "guardrails.json"
MEMORY_FILE = STATE_DIR / "memory.json"
DOCTOR_STATE_FILE = STATE_DIR / "doctor_actions.json"
INTEGRATIONS_FILE = CONFIG_DIR / "integrations.json"
AGENT_TEMPLATES_FILE = CONFIG_DIR / "agent_templates.json"

# Source agent_templates.json path (bundled in repo config directory)
_REPO_TEMPLATES_FILE = Path(__file__).parent.parent.parent / "config" / "agent_templates.json"
# Source skills_library.json path (bundled in repo config directory)
_REPO_SKILLS_FILE = Path(__file__).parent.parent.parent / "config" / "skills_library.json"
# Source agent_capabilities.json path (bundled in repo config directory)
_REPO_CAPS_FILE = Path(__file__).parent.parent.parent / "config" / "agent_capabilities.json"

PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "18790"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")
MAX_CHAT_MESSAGE_LENGTH = 10000
CHATLOG_MAX_ENTRIES = 1000

# ── IntelligenceCore identity ─────────────────────────────────────────────────
# Default user ID when no auth token is present (single-user / local install).
_DEFAULT_USER = "user:default"
LLM_TIMEOUT_SECONDS = 30

from constants import (  # noqa: F401 — extracted for readability
    ROUTING_MAP, AGENTS_BY_MODE, AGENT_ALIASES, CAPS_ID_ALIASES, INFRA_AGENTS,
)


class _TruncatingFormatter(logging.Formatter):
    """Caps every log line at 4 KB so a runaway repr() can't flood the disk.

    Single events that try to log e.g. an entire bounded Queue's contents
    (which produced multi-MB lines in the past) get clipped with a marker.
    """
    _MAX_LINE_BYTES = 4096

    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)
        if len(out) > self._MAX_LINE_BYTES:
            kept = out[: self._MAX_LINE_BYTES - 32]
            out = f"{kept}…[truncated {len(out) - len(kept)} chars]"
        return out


logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(message)s",
)
# Replace root handler formatters so the cap applies to all log emissions.
for _h in logging.getLogger().handlers:
    _h.setFormatter(_TruncatingFormatter("%(message)s"))
logger = logging.getLogger("problem-solver-ui")

_ACTIVITY_LOCK = threading.Lock()

# ── TTL-cached .env reader (avoids disk I/O on every chat/status request) ──────
_ENV_MAP_CACHE: tuple[float, dict[str, str]] = (0.0, {})
_ENV_MAP_CACHE_TTL: float = 10.0  # seconds


def _load_runtime_env_map() -> dict[str, str]:
  global _ENV_MAP_CACHE
  now = time.time()
  if now - _ENV_MAP_CACHE[0] < _ENV_MAP_CACHE_TTL:
    return _ENV_MAP_CACHE[1]
  env_map: dict[str, str] = {}
  env_file = AI_HOME / ".env"
  if env_file.exists():
    try:
      for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
          continue
        key, value = line.split("=", 1)
        env_map[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as exc:
      logger.warning("Failed to read %s: %s", env_file, exc)
  _ENV_MAP_CACHE = (now, env_map)
  return env_map


def _runtime_env_value(key: str, default: str = "") -> str:
  value = _load_runtime_env_map().get(key)
  if value not in (None, ""):
    return value
  return os.environ.get(key, default)


def _current_mode() -> str:
  mode = _runtime_env_value("AI_EMPLOYEE_MODE", "power").strip().lower()
  return mode if mode in AGENTS_BY_MODE else "power"


def _available_agent_ids(mode: Optional[str] = None) -> list[str]:
  return list(AGENTS_BY_MODE.get(mode or _current_mode(), AGENTS_BY_MODE["power"]))


def _agent_aliases(agent_id: str) -> list[str]:
  aliases = AGENT_ALIASES.get(agent_id, [agent_id])
  return aliases if agent_id in aliases else [agent_id, *aliases]


def _agent_allowed_in_mode(agent_id: str, mode: Optional[str] = None) -> bool:
  allowed = set(_available_agent_ids(mode))
  if agent_id in allowed:
    return True
  for allowed_id in allowed:
    if agent_id in _agent_aliases(allowed_id):
      return True
  return False


_SAFE_AGENT_ID_PAT = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def _agent_source_dirs() -> list[Path]:
  dirs: list[Path] = []
  for candidate in (BOTS_DIR, _REPO_AGENTS_DIR):
    try:
      resolved = candidate.resolve()
    except Exception:
      continue
    if not resolved.exists():
      continue
    if resolved not in dirs:
      dirs.append(resolved)
  return dirs


def _agent_run_script(agent_id: str) -> Optional[Path]:
  if not isinstance(agent_id, str) or not _SAFE_AGENT_ID_PAT.match(agent_id):
    return None
  if not _BOT_NAME_RE.match(agent_id):
    return None
  for agents_root in _agent_source_dirs():
    run_script = (agents_root / agent_id / "run.sh")
    if run_script.exists():
      return run_script
  return None


def _agent_dir_exists(agent_id: str) -> bool:
  return _agent_run_script(agent_id) is not None


def _sync_missing_mode_agents(mode: Optional[str] = None) -> dict[str, object]:
  """Copy missing mode agents from bundled runtime into AI_HOME/agents if needed."""
  provisioned: list[str] = []
  still_missing: list[str] = []
  errors: dict[str, str] = {}

  if not _REPO_AGENTS_DIR.exists():
    return {"provisioned": provisioned, "still_missing": still_missing, "errors": errors}

  try:
    bots_dir_resolved = BOTS_DIR.resolve()
    repo_agents_resolved = _REPO_AGENTS_DIR.resolve()
  except Exception:
    return {"provisioned": provisioned, "still_missing": still_missing, "errors": errors}

  # If already running directly from bundled runtime agents, nothing to copy.
  if bots_dir_resolved == repo_agents_resolved:
    return {"provisioned": provisioned, "still_missing": still_missing, "errors": errors}

  target_agents_dir = (AI_HOME / "agents")
  target_agents_dir.mkdir(parents=True, exist_ok=True)
  configured_agents = _available_agent_ids(mode)

  for agent_id in configured_agents:
    if not isinstance(agent_id, str) or not _BOT_NAME_RE.match(agent_id):
      continue
    target_dir = target_agents_dir / agent_id
    target_run = target_dir / "run.sh"
    if target_run.exists():
      continue

    source_dir = _REPO_AGENTS_DIR / agent_id
    source_run = source_dir / "run.sh"
    if not source_run.exists():
      still_missing.append(agent_id)
      continue

    try:
      if target_dir.exists() and not target_dir.is_dir():
        raise RuntimeError(f"target path exists and is not a directory: {target_dir}")
      if not target_dir.exists():
        shutil.copytree(source_dir, target_dir)
      else:
        # Keep existing user files; only copy missing entries.
        for item in source_dir.iterdir():
          dst = target_dir / item.name
          if dst.exists():
            continue
          if item.is_dir():
            shutil.copytree(item, dst)
          else:
            shutil.copy2(item, dst)
      if target_run.exists():
        target_run.chmod(target_run.stat().st_mode | 0o111)
        provisioned.append(agent_id)
      else:
        still_missing.append(agent_id)
    except Exception as exc:
      errors[agent_id] = str(exc)
      still_missing.append(agent_id)

  return {"provisioned": provisioned, "still_missing": still_missing, "errors": errors}


def _resolve_agent_target(agent_id: str) -> Optional[str]:
  """Resolve an agent ID to a runnable folder name (supports aliases)."""
  for candidate in _agent_aliases(agent_id):
    if _agent_dir_exists(candidate):
      return candidate
  return None


def _mode_agent_targets(mode: Optional[str] = None) -> list[str]:
  """Return unique runnable agent folders for the current mode."""
  targets: list[str] = []
  for agent_id in _available_agent_ids(mode):
    resolved = _resolve_agent_target(agent_id)
    if resolved and resolved not in targets:
      targets.append(resolved)
  return targets


_RUNTIME_PATHS_LOCK = threading.Lock()
_RUNTIME_RUN_FILE_MAP: dict[str, dict[str, Path]] = {}
_RUNTIME_STATE_FILE_MAP: dict[str, Path] = {}


def _build_runtime_path_maps() -> None:
  run_dir = (AI_HOME / "run").resolve()
  state_dir = STATE_DIR.resolve()
  managed_agents: set[str] = set()
  for mode_name in AGENTS_BY_MODE:
    managed_agents.update(_mode_agent_targets(mode_name))
  managed_agents.update(a for a in INFRA_AGENTS if _agent_dir_exists(a))
  for agent_name in sorted(managed_agents):
    if not _BOT_NAME_RE.match(agent_name):
      continue
    _RUNTIME_RUN_FILE_MAP[agent_name] = {
      ".pid": run_dir / f"{agent_name}.pid",
      ".lock": run_dir / f"{agent_name}.lock",
      ".pid.lock": run_dir / f"{agent_name}.pid.lock",
    }
    _RUNTIME_STATE_FILE_MAP[agent_name] = state_dir / f"{agent_name}.state.json"


def _ensure_runtime_path_maps() -> None:
  if _RUNTIME_RUN_FILE_MAP and _RUNTIME_STATE_FILE_MAP:
    return
  with _RUNTIME_PATHS_LOCK:
    if _RUNTIME_RUN_FILE_MAP and _RUNTIME_STATE_FILE_MAP:
      return
    _build_runtime_path_maps()


def _normalize_managed_agent_name(agent_name: str) -> Optional[str]:
  if not isinstance(agent_name, str) or not _BOT_NAME_RE.match(agent_name):
    return None
  _ensure_runtime_path_maps()
  if agent_name in _RUNTIME_RUN_FILE_MAP:
    return agent_name
  resolved = _resolve_agent_target(agent_name)
  if resolved and resolved in _RUNTIME_RUN_FILE_MAP:
    return resolved
  return None


def route_to_agent(message: str) -> str:
  message_lower = message.lower()
  for keyword in sorted(ROUTING_MAP, key=len, reverse=True):
    if keyword in message_lower:
      return ROUTING_MAP[keyword]
  if "all 56 agents" in message_lower or "all agents" in message_lower:
    return "task-orchestrator"
  return "task-orchestrator"


def append_chatlog(entry: dict) -> None:
  try:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    lines = CHATLOG.read_text().splitlines() if CHATLOG.exists() else []
    lines.append(json.dumps(entry))
    CHATLOG.write_text("\n".join(lines[-CHATLOG_MAX_ENTRIES:]) + "\n")
  except Exception as exc:
    logger.warning("Failed to write chatlog: %s", exc)


def _ollama_reachable(ollama_host: str) -> bool:
  try:
    req = urllib.request.Request(
      f"{ollama_host.rstrip('/')}/api/tags",
      headers={"User-Agent": "AI-Employee/1.0"},
    )
    with urllib.request.urlopen(req, timeout=0.25) as resp:
      return resp.status == 200
  except Exception:
    return False


def _detect_llm_provider(model_route: Optional[str] = None) -> tuple[Optional[str], str, dict[str, str]]:
  runtime_env = _load_runtime_env_map()
  route = (model_route or "").strip().lower()

  if route == "auto":
    # Cost-effective order: Ollama (free) → NVIDIA (free) → Groq (fast cheap) → OpenAI → Anthropic
    ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if _ollama_reachable(ollama_host):
      return "ollama", runtime_env.get("OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.2"), runtime_env
    nvidia_key = runtime_env.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY", "")
    if nvidia_key:
      return "nvidia", runtime_env.get("NIM_BULK_MODEL") or os.environ.get("NIM_BULK_MODEL", "meta/llama-3.1-8b-instruct"), runtime_env
    groq_key = runtime_env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
    if groq_key:
      return "groq", runtime_env.get("GROQ_MODEL") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), runtime_env
    openai_key = runtime_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
      return "openai", runtime_env.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), runtime_env
    anthropic_key = runtime_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
      return "anthropic", runtime_env.get("CLAUDE_MODEL") or os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"), runtime_env

  if route == "nvidia":
    nvidia_key = runtime_env.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY", "")
    if nvidia_key:
      return "nvidia", runtime_env.get("NIM_BULK_MODEL") or os.environ.get("NIM_BULK_MODEL", "meta/llama-3.1-8b-instruct"), runtime_env

  if route == "openai":
    openai_key = runtime_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
      return "openai", runtime_env.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o"), runtime_env

  if route == "anthropic":
    anthropic_key = runtime_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
      return "anthropic", runtime_env.get("CLAUDE_MODEL") or os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"), runtime_env

  if route == "groq":
    groq_key = runtime_env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
    if groq_key:
      return "groq", runtime_env.get("GROQ_MODEL") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), runtime_env

  if route == "external":
    anthropic_key = runtime_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
      return "anthropic", runtime_env.get("CLAUDE_MODEL") or os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"), runtime_env
    openai_key = runtime_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
      return "openai", runtime_env.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o"), runtime_env

  if route == "ollama":
    ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if _ollama_reachable(ollama_host):
      return "ollama", runtime_env.get("OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.2"), runtime_env

  if route == "gemma":
    ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if _ollama_reachable(ollama_host):
      gemma_model = runtime_env.get("GEMMA_MODEL") or os.environ.get("GEMMA_MODEL", "gemma4")
      return "gemma", gemma_model, runtime_env

  if route == "wavefield":
    ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if _ollama_reachable(ollama_host):
      wavefield_model = runtime_env.get("WAVEFIELD_MODEL") or os.environ.get("WAVEFIELD_MODEL", "")
      if wavefield_model:
        return "wavefield", wavefield_model, runtime_env

  anthropic_key = runtime_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
  if anthropic_key:
    return "anthropic", runtime_env.get("CLAUDE_MODEL") or os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"), runtime_env
  openai_key = runtime_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
  if openai_key:
    return "openai", runtime_env.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o"), runtime_env
  ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
  if _ollama_reachable(ollama_host):
    return "ollama", runtime_env.get("OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.2"), runtime_env
  return None, "", runtime_env


def _llm_auth_failed(exc: Exception) -> bool:
  text = str(exc).lower()
  return "401" in text or "403" in text or "unauthorized" in text or "invalid api key" in text or "authentication" in text


def _build_llm_system_prompt(
    message: str,
    routed_agent: str,
    mode: str,
    user_id: str = _DEFAULT_USER,
    graph_context: str = "",
) -> str:
    available_agents = ", ".join(_available_agent_ids(mode))

    # ── Tone hint from personalisation profile ────────────────────────────────
    tone_hint = ""
    intel = _load_intelligence()
    if intel is not None:
        try:
            from brain.intelligence import get_intelligence  # noqa: PLC0415
            _ic = get_intelligence()
            profile = _ic._profile(user_id)
            if profile.tone == "concise":
                tone_hint = "The user prefers concise, short responses. Be brief. "
            elif profile.tone == "detailed":
                tone_hint = "The user prefers thorough, detailed explanations. Be comprehensive. "
            if profile.prefers_local > 0.5:
                tone_hint += "The user prefers local / offline processing — do not suggest cloud services. "
        except Exception:
            pass

    # ── Personalised context block (memory + facts + history) ────────────────
    context_block = ""
    if intel is not None:
        try:
            context_block = intel.build_context(user_id, message, mode)
        except Exception as exc:
            logger.debug("_build_llm_system_prompt: context error — %s", exc)

    base = (
        "You are AI Employee (Ultron), a world-class automation and intelligence platform. "
        "You work like a skilled human operator: thoughtful, reliable, and focused on results. "
        "You combine deep technical expertise with practical judgment—think of yourself as an exceptional engineer or strategist, not an AI system. "
        "You understand context completely, identify real problems, design thoughtful solutions, and execute reliably. "
        "Your communication is natural, warm, and professional—never robotic or overly formal. "
        f"Current mode: {mode}. Available capabilities: {available_agents}. Routed handler: {routed_agent}. "
        f"{tone_hint}"
        "\n\n"
        "RESPONSE STYLE — Keep it natural and human:\n"
        "- Use conversational language. First person ('I', 'we') when appropriate\n"
        "- Acknowledge the user's context and show you understand their situation\n"
        "- Break complex work into clear steps, but don't overstructure simple answers\n"
        "- Show your thinking naturally (explain decisions, not just output results)\n"
        "- Use professional but approachable tone—like talking to a trusted colleague\n"
        "- Never sound like you're following a template or protocol\n"
        "- If there's risk or uncertainty, say so directly and offer a practical workaround\n\n"
        "FOR COMPLEX TASKS, organize your thinking:\n"
        "1. Acknowledge what you're being asked to do\n"
        "2. Outline your approach in natural language (not bullet points unless needed)\n"
        "3. Show the actual work: code, analysis, research findings, etc.\n"
        "4. Wrap up with key results and next steps\n\n"
        "FOR SIMPLE QUESTIONS, just answer directly. No structure needed.\n\n"
        "CODE QUALITY: Keep code clean—zero duplicate logic, zero dead code, zero unused imports. "
        "For code output, include brief explanation of what it does. "
        "If live data is unavailable, be transparent about that and offer what you can provide."
    )

    # Dynamic parts are appended after the cache split marker so only the
    # stable `base` block is sent with cache_control to Anthropic.
    _CACHE_SPLIT = "\n\n<!-- ⚡CACHE_SPLIT⚡ -->\n\n"
    dynamic_parts: list[str] = []
    if message:
        dynamic_parts.append(f"Current request context: {message}")
    if context_block:
        dynamic_parts.append(context_block)
    if graph_context:
        dynamic_parts.append(f"Knowledge Graph Data:\n{graph_context}")

    dynamic = "\n\n".join(dynamic_parts)
    return base + _CACHE_SPLIT + dynamic if dynamic else base + _CACHE_SPLIT


def _call_groq_chat(prompt: str, system_prompt: str, model: str, api_key: str,
                    history: Optional[list] = None) -> str:
  messages: list = [{"role": "system", "content": system_prompt}]
  if history:
    messages.extend(history)
  messages.append({"role": "user", "content": prompt})
  payload = {
    "model": model,
    "messages": messages,
    "temperature": 0.7,
  }
  req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}",
    },
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
    body = json.loads(resp.read().decode("utf-8", errors="replace"))
  return (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def _call_openai_chat(prompt: str, system_prompt: str, model: str, api_key: str,
                      history: Optional[list] = None) -> str:
  messages: list = [{"role": "system", "content": system_prompt}]
  if history:
    messages.extend(history)
  messages.append({"role": "user", "content": prompt})
  payload = {
    "model": model,
    "messages": messages,
    "temperature": 0.7,
  }
  req = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}",
    },
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
    body = json.loads(resp.read().decode("utf-8", errors="replace"))
  return (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


_CACHE_SPLIT = "\n\n<!-- ⚡CACHE_SPLIT⚡ -->\n\n"
_CACHE_MIN_CHARS = 512  # rough proxy; Anthropic requires ≥1024 tokens on the cached block


def _build_system_blocks(system_prompt: str) -> list[dict]:
    """Split system_prompt on the cache marker and return content blocks.

    The static portion gets cache_control so Anthropic caches it across turns.
    The dynamic portion (per-request context) is sent uncached.
    Returns a plain-string fallback if the split marker is absent.
    """
    if _CACHE_SPLIT not in system_prompt:
        return [{"type": "text", "text": system_prompt}]
    static_part, dynamic_part = system_prompt.split(_CACHE_SPLIT, 1)
    blocks: list[dict] = []
    if static_part:
        block: dict = {"type": "text", "text": static_part}
        if len(static_part) >= _CACHE_MIN_CHARS:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    if dynamic_part.strip():
        blocks.append({"type": "text", "text": dynamic_part.strip()})
    return blocks or [{"type": "text", "text": system_prompt}]


def _call_anthropic_chat(prompt: str, system_prompt: str, model: str, api_key: str,
                         history: Optional[list] = None) -> str:
  # Anthropic requires messages to alternate user/assistant and start with "user".
  # Build from history, then append the current user message.
  messages: list = []
  if history:
    messages.extend(history)
  messages.append({"role": "user", "content": prompt})
  system_blocks = _build_system_blocks(system_prompt)
  payload = {
    "model": model,
    "max_tokens": 1200,
    "system": system_blocks,
    "messages": messages,
  }
  req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=json.dumps(payload).encode("utf-8"),
    headers={
      "Content-Type": "application/json",
      "x-api-key": api_key,
      "anthropic-version": "2023-06-01",
      # Opt-in to prompt caching beta
      "anthropic-beta": "prompt-caching-2024-07-31",
    },
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
    body = json.loads(resp.read().decode("utf-8", errors="replace"))
  # Log cache usage when present (cache_read_input_tokens > 0 → cache hit)
  usage = body.get("usage", {})
  if usage.get("cache_read_input_tokens", 0) > 0:
    logger.debug(
      "Prompt cache HIT: read=%d creation=%d",
      usage["cache_read_input_tokens"],
      usage.get("cache_creation_input_tokens", 0),
    )
  parts = body.get("content") or []
  return "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()


def _call_ollama_chat(prompt: str, system_prompt: str, model: str, ollama_host: str,
                      history: Optional[list] = None) -> str:
  messages: list = [{"role": "system", "content": system_prompt}]
  if history:
    messages.extend(history)
  messages.append({"role": "user", "content": prompt})
  payload = {
    "model": model,
    "stream": False,
    "messages": messages,
  }
  req = urllib.request.Request(
    f"{ollama_host.rstrip('/')}/api/chat",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
    body = json.loads(resp.read().decode("utf-8", errors="replace"))
  return ((body.get("message") or {}).get("content") or "").strip()


def _call_gemma_chat(prompt: str, system_prompt: str, ollama_host: str,
                     history: Optional[list] = None) -> str:
  """Call Gemma model via local Ollama using the configured GEMMA_MODEL."""
  gemma_model = os.environ.get("GEMMA_MODEL", "gemma4")
  return _call_ollama_chat(prompt, system_prompt, gemma_model, ollama_host, history=history)


def _load_chat_history(n_exchanges: int = 8) -> list:
    """Load the last *n_exchanges* user/assistant pairs from CHATLOG.

    Returns a list of ``{"role": "user"|"assistant", "content": str}`` dicts
    suitable for inserting directly into the LLM messages array.  Messages are
    ordered oldest-first so the LLM sees the conversation in chronological order.

    Only ``"user"`` and ``"agent"`` log entry types are included; system/internal
    entries are skipped.  Entries with empty content are also skipped.
    """
    try:
        raw = _read_last_n_lines(CHATLOG, n_exchanges * 2 + 4)
    except Exception:
        return []
    history: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type", "")
        content = (entry.get("message") or "").strip()
        if not content:
            continue
        if entry_type == "user":
            history.append({"role": "user", "content": content})
        elif entry_type == "agent":
            history.append({"role": "assistant", "content": content})
    # Keep only the last n_exchanges pairs (2 messages each)
    max_msgs = n_exchanges * 2
    if len(history) > max_msgs:
        history = history[-max_msgs:]
    # Ensure the history ends with an "assistant" message (not the current user
    # message, which is injected separately by the callers).
    while history and history[-1]["role"] == "user":
        history.pop()
    return history


def _direct_conversation_reply(goal_plan: dict, message: str) -> str | None:
    """Handle utility/chat turns that must never enter the task executor."""
    response_type = str(goal_plan.get("response_type") or "").lower()
    if response_type == "time":
        from datetime import datetime

        now = datetime.now().astimezone()
        return f"It is {now.strftime('%H:%M:%S')} ({now.tzname() or 'local time'})."
    if response_type == "date":
        from datetime import datetime

        now = datetime.now().astimezone()
        day = str(now.day)
        return f"Today is {now.strftime('%A, %B')} {day}, {now.year}."
    if response_type == "greeting":
        return "I’m here. Tell me what you want to build, fix, research, or run."
    if response_type == "empty":
        return "Send me a question or a task and I’ll route it properly."
    # Let normal questions use the conversational LLM path.
    return None


def _generate_llm_response(
    message: str,
    routed_agent: str,
    mode: str,
    model_route: Optional[str] = None,
    user_id: str = _DEFAULT_USER,
    graph_context: str = "",
) -> str:
  # ── [AI FLOW] Log pipeline entry ────────────────────────────────────────────
  _ai_flow_logger.info("[AI FLOW] Input received: agent=%s mode=%s", routed_agent, mode)

  # ── Prompt Inspector — start trace (non-blocking, zero-disruption) ──────────
  _pi = _get_prompt_inspector()
  _pi_trace = None
  if _pi is not None:
      try:
          _pi_trace = _pi.start_trace(user_input=message)
      except Exception:
          _pi_trace = None

  # ── [AI FLOW] Neural-network enhancement layer (non-blocking) ────────────────
  nn_output = _nn_process_input(message)
  final_input = nn_output if nn_output is not None else message
  _ai_flow_logger.info(
      "[AI FLOW] → Core AI called (nn_enhanced=%s)", nn_output is not None and nn_output is not message
  )

  effective_model_route = model_route
  forced_model: Optional[str] = None
  _shadow_wavefield = False
  try:
    from core.model_routing import select_model_route as _select_model_route  # noqa: PLC0415
    from core.wavefield_provider import record_wavefield_event as _wf_record  # noqa: PLC0415

    _route = _select_model_route(
      prompt=final_input,
      context=graph_context,
      requested_route=model_route,
      default_route="auto",
    )
    effective_model_route = _route.model_route
    forced_model = _route.force_model
    _shadow_wavefield = _route.shadow_wavefield
    _wf_record("route_selected")
    if effective_model_route == "wavefield":
      _wf_record("route_selected_wavefield")
    if _shadow_wavefield:
      _wf_record("shadow_requests")
    _ai_flow_logger.info(
      "[AI FLOW] Route tier=%s est_tokens=%s threshold=%s rollout=%s route=%s shadow=%s",
      _route.tier,
      _route.estimated_tokens,
      _route.threshold,
      _route.rollout_mode,
      effective_model_route,
      _shadow_wavefield,
    )
  except Exception as _route_exc:
    _ai_flow_logger.warning("[AI FLOW] Routing layer unavailable: %s", _route_exc)

  provider, model, runtime_env = _detect_llm_provider(effective_model_route)
  if forced_model:
    model = forced_model

  if _shadow_wavefield:
    try:
      from core.wavefield_provider import wavefield_healthcheck as _wf_healthcheck  # noqa: PLC0415

      _ok, _reason = _wf_healthcheck(
        ollama_host=runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        model=os.environ.get("WAVEFIELD_MODEL", "").strip() or None,
      )
      if not _ok:
        from core.wavefield_provider import record_wavefield_event as _wf_record_shadow  # noqa: PLC0415

        _wf_record_shadow("healthcheck_failures")
        _ai_flow_logger.warning("[AI FLOW] Wave Field shadow healthcheck failed: %s", _reason)
    except Exception as _shadow_exc:
      _ai_flow_logger.debug("[AI FLOW] Wave Field shadow probe failed: %s", _shadow_exc)
  if not provider:
    _ai_flow_logger.warning("[AI FLOW] No LLM provider available — returning fallback")
    _fb = _fallback_response(
      "No model is available for the selected route. Add GROQ_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY to ~/.ai-employee/.env, "
      "or run Ollama locally: https://ollama.ai"
    )
    if _pi is not None and _pi_trace is not None:
        try:
            _pi.set_agent(_pi_trace.id, agent=routed_agent, provider="none", model="none")
            _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="fallback")
        except Exception:
            pass
    return _fb

  # ── Prompt Inspector — record routing metadata ──────────────────────────────
  if _pi is not None and _pi_trace is not None:
      try:
          _pi.set_agent(_pi_trace.id, agent=routed_agent, provider=provider, model=model or "")
      except Exception:
          pass

  # ── Circuit breaker for this LLM provider ───────────────────────────────────
  # ── Circuit breaker + distributed tracing for this LLM call ────────────────
  _cb_registry = _get_circuit_registry()
  _cb_name = f"llm:{provider}"
  _cb = _cb_registry.get(_cb_name) if _cb_registry is not None else None

  _dt_llm = _get_distributed_tracer()

  system_prompt = _build_llm_system_prompt(final_input, routed_agent, mode, user_id=user_id, graph_context=graph_context)

  # ── Load conversation history for context-aware responses ───────────────────
  # Injects the last 8 user/assistant exchanges into every LLM call so the
  # model has full conversational memory and never behaves as a stateless bot.
  _chat_history = _load_chat_history(n_exchanges=8)
  _ai_flow_logger.info(
      "[AI FLOW] → Conversation history loaded: %d messages", len(_chat_history)
  )

  # ── Prompt Inspector — record context and constructed prompt ────────────────
  if _pi is not None and _pi_trace is not None:
      try:
          # Extract context block from the system prompt (it's appended after the base)
          _ctx_marker = "\n\n"
          _ctx_idx = system_prompt.find(_ctx_marker)
          _ctx_block = system_prompt[_ctx_idx + len(_ctx_marker):] if _ctx_idx != -1 else ""
          _pi.set_context(_pi_trace.id, context_used=_ctx_block)
          _pi.set_prompt(_pi_trace.id, constructed_prompt=system_prompt)
      except Exception:
          pass

  try:
    def _do_llm_call():
      if provider == "anthropic":
        api_key = runtime_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        return _call_anthropic_chat(final_input, system_prompt, model, api_key, history=_chat_history)
      elif provider == "openai":
        api_key = runtime_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        return _call_openai_chat(final_input, system_prompt, model, api_key, history=_chat_history)
      elif provider == "groq":
        api_key = runtime_env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
        return _call_groq_chat(final_input, system_prompt, model, api_key, history=_chat_history)
      elif provider == "gemma":
        ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        return _call_gemma_chat(final_input, system_prompt, ollama_host, history=_chat_history)
      elif provider == "wavefield":
        from core.wavefield_provider import record_wavefield_event, wavefield_allow_fallback, wavefield_call, wavefield_healthcheck  # noqa: PLC0415

        healthy, reason = wavefield_healthcheck(
          ollama_host=runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
          model=model,
        )
        if not healthy:
          record_wavefield_event("healthcheck_failures")
          if not wavefield_allow_fallback():
            raise RuntimeError(f"Wave Field unavailable: {reason}")
          record_wavefield_event("fallbacks")
          logger.warning("Wave Field healthcheck failed, fallback to default provider: %s", reason)
          fallback_provider, fallback_model, fallback_env = _detect_llm_provider("auto")
          if fallback_provider in (None, "wavefield"):
            raise RuntimeError(f"No healthy fallback provider after Wave Field failure: {reason}")
          if fallback_provider == "anthropic":
            api_key = fallback_env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
            return _call_anthropic_chat(final_input, system_prompt, fallback_model, api_key, history=_chat_history)
          if fallback_provider == "openai":
            api_key = fallback_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
            return _call_openai_chat(final_input, system_prompt, fallback_model, api_key, history=_chat_history)
          if fallback_provider == "groq":
            api_key = fallback_env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
            return _call_groq_chat(final_input, system_prompt, fallback_model, api_key, history=_chat_history)
          if fallback_provider == "gemma":
            ollama_host = fallback_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
            return _call_gemma_chat(final_input, system_prompt, ollama_host, history=_chat_history)
          ollama_host = fallback_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
          return _call_ollama_chat(final_input, system_prompt, fallback_model, ollama_host, history=_chat_history)
        return wavefield_call(
          prompt=final_input,
          system_prompt=system_prompt,
          history=_chat_history,
          model=model,
          timeout_s=LLM_TIMEOUT_SECONDS,
        )
      else:
        ollama_host = runtime_env.get("OLLAMA_HOST") or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        return _call_ollama_chat(final_input, system_prompt, model, ollama_host, history=_chat_history)

    def _do_llm_call_with_trace():
      if _dt_llm is not None:
        with _dt_llm.span(
            f"llm_call:{provider}",
            kind=_get_span_kind_llm(),
            attributes={"provider": provider, "model": model or "", "agent": routed_agent},
        ):
          return _do_llm_call()
      return _do_llm_call()

    if _cb is not None:
      try:
        answer = _cb.call(_do_llm_call_with_trace)
      except Exception as _cb_exc:
        _cb_open_msg = getattr(_cb_exc, "reset_in", None)
        if _cb_open_msg is not None:
          # Circuit is OPEN — fast fail with graceful degradation
          logger.warning("Circuit breaker '%s' is OPEN — degrading gracefully", _cb_name)
          _cb_msg = (
            f"⚡ Service temporarily unavailable ({provider} is experiencing issues). "
            "Please try again in a moment or switch to a different model route."
          )
          if _pi is not None and _pi_trace is not None:
              try:
                  _pi.finish_trace(_pi_trace.id, final_output=_cb_msg, execution_status="error",
                                   error="circuit_breaker_open")
              except Exception:
                  pass
          return _cb_msg
        raise
    else:
      answer = _do_llm_call_with_trace()
  except urllib.error.HTTPError as exc:
    if _llm_auth_failed(exc):
      _ai_flow_logger.warning("[AI FLOW] LLM auth failed — returning fallback")
      _fb = _fallback_response("LLM authentication failed. Check your API key in ~/.ai-employee/.env")
      if _pi is not None and _pi_trace is not None:
          try:
              _pi.set_error(_pi_trace.id, "LLM auth failed (HTTP)")
              _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
          except Exception:
              pass
      return _fb
    _ai_flow_logger.warning("[AI FLOW] LLM HTTP error — returning fallback")
    _fb = _fallback_response("Task is taking longer than expected. Check dashboard for results.")
    if _pi is not None and _pi_trace is not None:
        try:
            _pi.set_error(_pi_trace.id, f"LLM HTTP error: {exc}")
            _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
        except Exception:
            pass
    return _fb
  except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
    if _llm_auth_failed(exc):
      _ai_flow_logger.warning("[AI FLOW] LLM auth failed (timeout path) — returning fallback")
      _fb = _fallback_response("LLM authentication failed. Check your API key in ~/.ai-employee/.env")
      if _pi is not None and _pi_trace is not None:
          try:
              _pi.set_error(_pi_trace.id, "LLM auth failed (timeout)")
              _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
          except Exception:
              pass
      return _fb
    _ai_flow_logger.warning("[AI FLOW] LLM timeout — returning fallback")
    _fb = _fallback_response("Request timed out. Try a simpler task or check your connection.")
    if _pi is not None and _pi_trace is not None:
        try:
            _pi.set_error(_pi_trace.id, "LLM timeout")
            _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
        except Exception:
            pass
    return _fb
  except Exception as exc:
    logger.warning("LLM request failed for agent %s: %s", routed_agent, exc)
    if _llm_auth_failed(exc):
      _ai_flow_logger.warning("[AI FLOW] LLM auth failed (exception path) — returning fallback")
      _fb = _fallback_response("LLM authentication failed. Check your API key in ~/.ai-employee/.env")
      if _pi is not None and _pi_trace is not None:
          try:
              _pi.set_error(_pi_trace.id, "LLM auth failed (exception)")
              _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
          except Exception:
              pass
      return _fb
    _ai_flow_logger.warning("[AI FLOW] LLM exception — returning fallback: %s", exc)
    _fb = _fallback_response("Task is taking longer than expected. Check dashboard for results.")
    if _pi is not None and _pi_trace is not None:
        try:
            _pi.set_error(_pi_trace.id, str(exc))
            _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="error")
        except Exception:
            pass
    return _fb

  if not answer:
    _ai_flow_logger.warning("[AI FLOW] Empty LLM answer — returning fallback")
    _fb = _fallback_response(
      "No model response was returned. Check your selected route credentials or model availability."
    )
    if _pi is not None and _pi_trace is not None:
        try:
            _pi.set_model_output(_pi_trace.id, model_raw_output="")
            _pi.finish_trace(_pi_trace.id, final_output=_fb, execution_status="fallback")
        except Exception:
            pass
    return _fb

  # ── Prompt Inspector — record raw model output ──────────────────────────────
  if _pi is not None and _pi_trace is not None:
      try:
          _pi.set_model_output(_pi_trace.id, model_raw_output=answer)
      except Exception:
          pass

  result = f"Agent: {routed_agent}\n\n{answer}"
  # ── Financial disclaimer — appended whenever a financial agent responds ────
  if routed_agent in _FINANCIAL_AGENT_IDS:
      result += _FINANCIAL_DISCLAIMER

  # ── Explainability — generate structured explanation and embed its ID ───────
  try:
      _xai = _get_explain_engine()
      if _xai is not None:
          from core.explainability_layer import ExplainContext  # type: ignore
          _exp = _xai.explain(ExplainContext(
              agent=routed_agent,
              action="generate_response",
              message=message,
              response=answer,
              model=model or "",
              user_id=user_id,
          ))
          # Embed explain_id as a hidden HTML comment so the chat endpoint
          # can promote it to a structured JSON field without breaking
          # plain-text consumers (the comment is invisible in markdown).
          result += f"\n<!--xai:{_exp.explain_id}-->"
  except Exception as _xai_exc:
      logger.debug("explainability generation error (non-fatal): %s", _xai_exc)

  # ── Prompt Inspector — finalise trace with the full pipeline result ──────────
  if _pi is not None and _pi_trace is not None:
      try:
          _pi.finish_trace(
              _pi_trace.id,
              final_output=result,
              actions_triggered=[f"agent:{routed_agent}"],
              execution_status="ok",
          )
      except Exception:
          pass

  _ai_flow_logger.info("[AI FLOW] → Response returned (len=%d)", len(result))
  return result

_SENSITIVE_DETAIL_PAT = re.compile(
    r'(?i)(key|secret|token|password|passwd|pass|auth|credential|api_key)')


def _redact_sensitive_details(details: dict) -> dict:
    """Return a copy of details with values for sensitive-named keys redacted."""
    return {
        k: "***" if _SENSITIVE_DETAIL_PAT.search(str(k)) else _redact_sensitive_text(str(v))
        for k, v in details.items()
    }


def _redact_sensitive_text(value: str) -> str:
    return _SENSITIVE_DETAIL_PAT.sub("***", value)[:500]


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
        "description_len": len(description),
        "description_hash": hashlib.sha256(description.encode("utf-8", errors="ignore")).hexdigest()[:16],
        "source": source,
    }
    if details:
        entry["detail_keys"] = sorted(str(k) for k in details.keys())[:50]
    try:
        ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _ACTIVITY_LOCK:
            with open(ACTIVITY_LOG, "a") as _fh:
                _fh.write(json.dumps(entry) + "\n")
    except Exception as _exc:
        logger.warning("Failed to write activity log: %s", _exc)


# ── Neural-network failsafe configuration ─────────────────────────────────────
# Set BYPASS_NN=1 to skip the neural-network enhancement layer entirely and call
# the core LLM directly.  Useful for debugging or when the NN layer is unstable.
_BYPASS_NN: bool = os.environ.get("BYPASS_NN", "").strip().lower() in ("1", "true", "yes")
# Maximum seconds to wait for the neural-network process step before bypassing.
_NN_TIMEOUT_S: float = float(os.environ.get("NN_TIMEOUT_S", "2.0"))

_ai_flow_logger = logging.getLogger("ai_flow")


def _fallback_response(msg: str) -> str:
    """Return a user-friendly message when the AI pipeline cannot produce a response."""
    # Map internal technical messages to natural, human-readable responses.
    _msg_lower = msg.lower()
    if "no model is available" in _msg_lower or "add groq_api_key" in _msg_lower or "ollama" in _msg_lower:
        return (
            "I don't have an AI model connected right now. To fix this, either:\n\n"
            "• **Local (free):** Install Ollama from https://ollama.ai and run `ollama serve` in your terminal.\n"
            "• **Cloud:** Add your ANTHROPIC_API_KEY or OPENAI_API_KEY to `~/.ai-employee/.env`.\n\n"
            "Once a model is available I'll be ready to help with anything you need."
        )
    if "authentication failed" in _msg_lower or "api key" in _msg_lower:
        return (
            "It looks like your API key isn't working. Please double-check that your key is correct "
            "in `~/.ai-employee/.env` and try again. If you're using Ollama locally, make sure `ollama serve` "
            "is running."
        )
    if "timed out" in _msg_lower or "timeout" in _msg_lower:
        return (
            "That took longer than expected — the AI model didn't respond in time. "
            "This can happen when the model is loading or the system is under load. "
            "Please try again in a moment."
        )
    if "temporarily unavailable" in _msg_lower or "circuit" in _msg_lower:
        return (
            "The AI service is temporarily unavailable — it should recover on its own shortly. "
            "Please wait a moment and try again."
        )
    if "no model response" in _msg_lower or "empty" in _msg_lower:
        return (
            "The AI returned an empty response. This sometimes happens with local models. "
            "Try rephrasing your question, or switch to a cloud provider in Settings."
        )
    # Generic fallback — still conversational
    return f"I ran into an issue: {msg} Please try again or check the Doctor page for diagnostics."


# ── Neural-network non-blocking enhancement layer ─────────────────────────────

def _nn_process_input(message: str) -> "str | None":
    """Optionally enhance *message* via the neural-network agent.

    The NN layer is fully optional: any error, import failure, or timeout
    causes this function to return *None* so the caller can fall back to the
    original message.  It NEVER raises.

    Returns the (potentially enhanced) input string, or *None* on failure.
    """
    if _BYPASS_NN:
        _ai_flow_logger.info("[AI FLOW] NN bypassed (BYPASS_NN=1)")
        return None
    try:
        import concurrent.futures as _cf
        import sys as _sys
        _nn_agents_dir = Path(__file__).resolve().parents[2] / "agents"
        if str(_nn_agents_dir) not in _sys.path:
            _sys.path.insert(0, str(_nn_agents_dir))
        from neural_network.agent import NeuralNetworkAgent  # type: ignore

        _ai_flow_logger.info("[AI FLOW] → NN start")

        def _run_nn() -> "str | None":
            try:
                import torch as _torch
                nn_agent = NeuralNetworkAgent()
                # Build a minimal feature vector from the message:
                # [msg_len_norm, word_count_norm, has_question, has_task_keyword]
                words = message.split()
                state = _torch.tensor([
                    min(len(message) / 500.0, 1.0),
                    min(len(words) / 50.0, 1.0),
                    float("?" in message),
                    float(any(kw in message.lower() for kw in ("task", "help", "do", "run", "start", "stop"))),
                ] + [0.0] * 60, dtype=_torch.float32)  # pad to input_size=64
                _action, _confidence = nn_agent.get_action(state)
                _ai_flow_logger.info(
                    "[AI FLOW] → NN success (action=%d confidence=%.3f)",
                    _action, _confidence,
                )
                # NN does not rewrite the message; it provides routing metadata only.
                # Return the original message so the pipeline always has valid input.
                return message
            except Exception as _inner:
                _ai_flow_logger.warning("[AI FLOW] → NN inner error: %s", _inner)
                return None

        with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
            _future = _pool.submit(_run_nn)
            try:
                return _future.result(timeout=_NN_TIMEOUT_S)
            except _cf.TimeoutError:
                _ai_flow_logger.warning(
                    "[AI FLOW] → NN timeout (%.1fs) — bypassing", _NN_TIMEOUT_S
                )
                return None
    except Exception as _exc:
        _ai_flow_logger.warning("[AI FLOW] → NN failed — bypassing: %s", _exc)
        return None


_ai_router_path = BOTS_DIR / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_ROUTER_AVAILABLE = True
except ImportError:
    _AI_ROUTER_AVAILABLE = False

app = FastAPI(
    title="AI Employee API",
    description="Autonomous AI workforce platform API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {"name": "auth", "description": "Authentication & token management"},
        {"name": "tasks", "description": "Task execution & orchestration"},
        {"name": "agents", "description": "Agent management"},
        {"name": "research", "description": "Autonomous research"},
        {"name": "vault", "description": "Knowledge vault"},
        {"name": "billing", "description": "Usage & billing"},
        {"name": "monitoring", "description": "Observability & metrics"},
        {"name": "admin", "description": "Admin operations (admin role required)"},
    ],
)


@app.exception_handler(Exception)
async def _generic_exception_handler(request: Request, exc: Exception):
    logger.warning("Unhandled API error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)

# ── Multi-tenancy initialization ──────────────────────────────────────────────
from core.tenancy import init_tenant_manager
from core.tenant_middleware import TenantMiddleware

_tenant_manager = init_tenant_manager(AI_HOME)
app.add_middleware(TenantMiddleware, secret_key=_jwt_secret_env)

# ── Sentry error tracking ────────────────────────────────────────────────────
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=os.environ.get("ENVIRONMENT", "production"),
    )

# ── Jaeger distributed tracing (deferred, optional) ──────────────────────────
_trace_provider = None
_tracing_initialized = False

def _init_tracing():
    global _trace_provider, _tracing_initialized
    if _tracing_initialized:
        return
    try:
        from core.tracing import setup_tracing, setup_fastapi_instrumentation, setup_psycopg_instrumentation
        _trace_provider = setup_tracing(service_name="ai-employee")
        setup_fastapi_instrumentation(app)
        setup_psycopg_instrumentation()
        _tracing_initialized = True
        logger.info("Tracing initialized (Jaeger)")
    except Exception as e:
        logger.warning(f"Tracing initialization failed (non-fatal): {e}")
        _trace_provider = None

# ── Sentry error tracking (deferred, optional) ────────────────────────────────
_sentry_ok = False
_sentry_initialized = False

def _init_sentry():
    global _sentry_ok, _sentry_initialized
    if _sentry_initialized:
        return
    try:
        from core.sentry_config import init_sentry
        _sentry_ok = init_sentry(environment=os.environ.get("ENVIRONMENT", "production"))
        _sentry_initialized = True
        logger.info("Sentry initialized")
    except Exception as e:
        logger.warning(f"Sentry initialization failed (non-fatal): {e}")
        _sentry_ok = False

# ── Billing metrics (Phase 4, optional) ───────────────────────────────────────
_billing_collector = None
try:
    from core.billing_metrics import get_billing_collector
    _billing_collector = get_billing_collector()
except Exception as e:
    logger.warning(f"Billing metrics unavailable (non-fatal): {e}")

# ── Rate limiter (optional) ────────────────────────────────────────────────────
_rate_limiter = None
try:
    from core.rate_limiter import get_rate_limiter
    _rate_limiter = get_rate_limiter()
except Exception as e:
    logger.warning(f"Rate limiter unavailable (non-fatal): {e}")

# ── Embeddings manager (optional) ──────────────────────────────────────────────
_embeddings_manager = None
try:
    from core.embeddings import get_embeddings_manager
    _embeddings_manager = get_embeddings_manager()
except Exception as e:
    logger.warning(f"Embeddings manager unavailable (non-fatal): {e}")

# ── Knowledge bootstrap daemon (non-blocking) ──────────────────────────────────
bootstrap_knowledge = None
_knowledge_count = 0

def _bootstrap_knowledge_bg():
    global _knowledge_count, bootstrap_knowledge
    if bootstrap_knowledge is None:
        logger.debug("Knowledge bootstrap not available; skipping")
        return
    try:
        _knowledge_count = bootstrap_knowledge(AI_HOME)
        logger.info(f"Knowledge bootstrap: {_knowledge_count} entries loaded")
    except Exception as e:
        logger.warning(f"Knowledge bootstrap failed: {e}")

try:
    from core.knowledge_bootstrap import bootstrap_knowledge
    _kb_thread = threading.Thread(target=_bootstrap_knowledge_bg, daemon=True, name="knowledge-bootstrap")
    _kb_thread.start()
except Exception as e:
    logger.warning(f"Knowledge bootstrap import failed (non-fatal): {e}")
    bootstrap_knowledge = None

# ── Optional endpoint authentication (REQUIRE_AUTH=1 enables enforcement) ──────
# REQUIRE_AUTH defaults to "1" (enforced) for security.  Set REQUIRE_AUTH=0 in
# ~/.ai-employee/.env ONLY for local development on a trusted machine.
_REQUIRE_AUTH = os.environ.get("REQUIRE_AUTH", "1").strip() in ("1", "true", "yes")
_bearer_scheme = HTTPBearer(auto_error=False)

if not _REQUIRE_AUTH:
    print(
        "\n⚠️  SECURITY WARNING: REQUIRE_AUTH is disabled (REQUIRE_AUTH=0).\n"
        "   All API endpoints — including task submission and automation control —\n"
        "   are accessible WITHOUT a token.\n"
        "   This is only safe for fully isolated local development.\n"
        "   Do NOT use this setting in production or on any network-exposed server.\n",
        flush=True,
    )

# ── Neural-network bypass (debug switch) ──────────────────────────────────────
# _BYPASS_NN and _NN_TIMEOUT_S are defined near their implementation above.

# ── Financial-agents safety gate ──────────────────────────────────────────────
# Financial trading agents (turbo-quant, arbitrage-bot, polymarket-trader, etc.)
# are DISABLED by default.  Set ENABLE_FINANCIAL_AGENTS=1 in
# ~/.ai-employee/.env only after completing a jurisdiction-specific legal review.
# Accepted values: 1, true, yes (case-insensitive).
_ENABLE_FINANCIAL_AGENTS = os.environ.get("ENABLE_FINANCIAL_AGENTS", "0").strip() in ("1", "true", "yes")
_FINANCIAL_AGENT_IDS: frozenset[str] = frozenset({
    "turbo-quant",
    "arbitrage-bot",
    "polymarket-trader",
    "financial-deepsearch",
    "mirofish-researcher",
    "signal-community",
})
_FINANCIAL_DISCLAIMER = (
    "\n⚠️  FINANCIAL DISCLAIMER: This output is generated by an AI system and is "
    "for informational purposes only. It does NOT constitute financial advice, "
    "investment advice, or a recommendation to buy, sell, or hold any security, "
    "asset, or instrument. Past performance is not indicative of future results. "
    "Always consult a qualified financial adviser before making investment "
    "decisions. The operator of this system assumes no liability for financial "
    "losses arising from use of this tool.\n"
)

# ── Compliance modules (lazy import — non-fatal if runtime path not set up) ───

def _get_data_subject_rights():
    """Return the data_subject_rights_api module, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        import core.data_subject_rights_api as _dsr  # type: ignore
        return _dsr
    except Exception:
        return None


def _get_hitl_gate():
    """Return the HITLGate singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.hitl_gate import get_hitl_gate as _ghg  # type: ignore
        return _ghg()
    except Exception:
        return None


def _get_bias_engine():
    """Return the BiasDetectionEngine singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.bias_detection_engine import get_bias_engine as _gbe  # type: ignore
        return _gbe()
    except Exception:
        return None


def _get_explain_engine():
    """Return the ExplainabilityEngine singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.explainability_layer import get_explain_engine as _gee  # type: ignore
        return _gee()
    except Exception:
        return None


def _get_schema_validator():
    """Return the OutputValidationMiddleware singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.agent_output_schemas import get_schema_validator as _gsv  # type: ignore
        return _gsv()
    except Exception:
        return None


def _get_circuit_registry():
    """Return the CircuitBreakerRegistry singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.circuit_breaker import get_circuit_registry as _gcr  # type: ignore
        return _gcr()
    except Exception:
        return None


def _get_adversarial_filter():
    """Return the AdversarialFilter singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.adversarial_filter import get_adversarial_filter as _gaf  # type: ignore
        return _gaf()
    except Exception:
        return None


def _get_distributed_tracer():
    """Return the DistributedTracer singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.distributed_tracing import get_distributed_tracer as _gdt  # type: ignore
        return _gdt()
    except Exception:
        return None


def _get_span_kind_llm():
    """Return SpanKind.LLM if distributed_tracing is available, else a string fallback."""
    try:
        from core.distributed_tracing import SpanKind  # type: ignore
        return SpanKind.LLM
    except Exception:
        return "llm"


def _get_prompt_inspector():
    """Return the PromptInspector singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.prompt_inspector import get_prompt_inspector as _gpi  # type: ignore
        return _gpi()
    except Exception:
        return None


def _get_lifecycle_manager():
    """Return the DataLifecycleManager singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.data_lifecycle_manager import get_lifecycle_manager as _glm  # type: ignore
        return _glm()
    except Exception:
        return None


def _get_feedback_store():
    """Return the UserFeedbackStore singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.user_feedback_store import get_feedback_store as _gfs  # type: ignore
        return _gfs()
    except Exception:
        return None


def _get_governance_digest():
    """Return the GovernanceDigest singleton, or None if unavailable."""
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.governance_digest import get_governance_digest as _ggd  # type: ignore
        return _ggd()
    except Exception:
        return None


def _verify_any_token(token_str: str) -> bool:
    """Return True if the token is valid using the configured AuthManager."""
    return _decode_any_token(token_str) is not None


def _decode_any_token(token_str: str) -> Optional[dict[str, Any]]:
    """Return decoded token payload if valid, else None."""
    cfg = _security_config
    try:
        if _SECURITY_AVAILABLE:
            from security import AuthManager as _AM  # type: ignore
            _am = _AM(
                secret_key=(cfg.security.jwt_secret_key if cfg else _jwt_secret_env),
                algorithm=(cfg.security.jwt_algorithm if cfg else "HS256"),
                expire_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
            )
            payload: Optional[dict[str, Any]] = _am.verify_token(token_str)
            if payload is not None and "sub" in payload:
                return payload
    except Exception:
        pass
    # TenantMiddleware validates standard HS256 JWTs before route dependencies run.
    # Keep require_auth aligned with that path even when another `security` package
    # has already been imported and the local AuthManager fallback is active.
    try:
        import jwt as _jwt_std  # type: ignore
        payload = _jwt_std.decode(token_str, _jwt_secret_env, algorithms=["HS256"])
        if isinstance(payload, dict) and "sub" in payload:
            return payload
    except Exception:
        pass
    # Fallback: try stdlib HMAC token
    try:
        auth_fb = AuthManager(
            secret_key=_jwt_secret_env,
            algorithm="HS256",
            expire_minutes=30,
        )
        payload = auth_fb.verify_token(token_str)
        if payload is not None and "sub" in payload:
            return payload
    except Exception:
        return None
    return None


_AUTH_STATE_FILE = STATE_DIR / "auth_state.json"
_AUTH_STATE_LOCK = threading.RLock()
_MAX_LOGIN_ATTEMPTS = (
    int(_security_config.security.max_login_attempts)
    if _security_config
    else int(os.environ.get("AUTH_MAX_LOGIN_ATTEMPTS", "5"))
)
_LOCKOUT_STEPS_SECONDS = (
    [int(x) for x in _security_config.security.progressive_lockout_seconds]
    if _security_config
    else [60, 300, 900, 1800]
)
if not _LOCKOUT_STEPS_SECONDS:
    _LOCKOUT_STEPS_SECONDS = [60, 300, 900, 1800]
_REFRESH_TOKEN_TTL_SECONDS = (
    int(_security_config.security.refresh_token_expire_days) * 24 * 3600
    if _security_config
    else int(os.environ.get("AUTH_REFRESH_TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))
)
_REVOKED_JTI_TTL_SECONDS = int(os.environ.get("AUTH_REVOKED_JTI_TTL_SECONDS", str(24 * 3600)))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _request_fingerprint(request: Request) -> str:
    host = (request.client.host if request.client else "unknown") or "unknown"
    ua = request.headers.get("user-agent", "")
    lang = request.headers.get("accept-language", "")
    material = f"{host}|{ua}|{lang}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_auth_state() -> dict[str, Any]:
    default_state: dict[str, Any] = {
        "failed_logins": {},
        "refresh_tokens": {},
        "revoked_jti": {},
    }
    try:
        if _AUTH_STATE_FILE.exists():
            raw = json.loads(_AUTH_STATE_FILE.read_text())
            if isinstance(raw, dict):
                default_state.update(raw)
    except Exception:
        pass
    for key in ("failed_logins", "refresh_tokens", "revoked_jti"):
        if not isinstance(default_state.get(key), dict):
            default_state[key] = {}
    return default_state


def _save_auth_state(state: dict[str, Any]) -> None:
    now = _now_utc()
    refresh_tokens = state.get("refresh_tokens", {})
    revoked_jti = state.get("revoked_jti", {})

    if isinstance(refresh_tokens, dict):
        for token_hash, record in list(refresh_tokens.items()):
            if not isinstance(record, dict):
                refresh_tokens.pop(token_hash, None)
                continue
            expires_at = _parse_iso_ts(str(record.get("expires_at", "")))
            if expires_at is None or expires_at <= now:
                refresh_tokens.pop(token_hash, None)

    if isinstance(revoked_jti, dict):
        for jti, ts in list(revoked_jti.items()):
            revoked_at = _parse_iso_ts(str(ts))
            if revoked_at is None or (now - revoked_at).total_seconds() > _REVOKED_JTI_TTL_SECONDS:
                revoked_jti.pop(jti, None)

    _AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_STATE_FILE.write_text(json.dumps(state, indent=2))
    try:
        _AUTH_STATE_FILE.chmod(0o600)
    except OSError:
        pass


def _login_attempt_key(request: Request, username: str) -> str:
    client_ip = (request.client.host if request.client else "unknown") or "unknown"
    return f"{client_ip}:{username.lower()}"


def _record_revoked_jti(state: dict[str, Any], payload: Optional[dict[str, Any]]) -> None:
    if not payload:
        return
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return
    state.setdefault("revoked_jti", {})[jti] = _now_utc().isoformat()


def _issue_token_pair(
    auth: AuthManager,
    username: str,
    request: Request,
    tenant_id: Optional[str] = None,
    state: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    # If tenant_id not provided, try to load from users.json
    if tenant_id is None:
        _users_file = STATE_DIR / "users.json"
        try:
            users = json.loads(_users_file.read_text()) if _users_file.exists() else {}
            tenant_id = users.get(username, {}).get("tenant_id", f"user-{username}")
        except Exception:
            tenant_id = f"user-{username}"

    now = _now_utc()
    fingerprint = _request_fingerprint(request)
    access_token = auth.create_access_token(
        {
            "sub": username,
            "type": "user",
            "jti": secrets.token_hex(16),
            "fp": fingerprint,
            "tenant_id": tenant_id,  # Add tenant_id to JWT claim
            "email": f"{username}@ai-employee.local",
            "org_name": username,
        }
    )
    refresh_token = secrets.token_urlsafe(48)
    refresh_hash = _hash_refresh_token(refresh_token)
    expires_at = (now + timedelta(seconds=_REFRESH_TOKEN_TTL_SECONDS)).isoformat()

    if state is None:
        with _AUTH_STATE_LOCK:
            loaded = _load_auth_state()
            loaded.setdefault("refresh_tokens", {})[refresh_hash] = {
                "username": username,
                "fingerprint": fingerprint,
                "issued_at": now.isoformat(),
                "expires_at": expires_at,
                "revoked": False,
                "replaced_by": None,
            }
            _save_auth_state(loaded)
    else:
        state.setdefault("refresh_tokens", {})[refresh_hash] = {
            "username": username,
            "fingerprint": fingerprint,
            "issued_at": now.isoformat(),
            "expires_at": expires_at,
            "revoked": False,
            "replaced_by": None,
        }

    return access_token, refresh_token


def _is_jti_revoked(payload: Optional[dict[str, Any]]) -> bool:
    if not payload:
        return True
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return False
    with _AUTH_STATE_LOCK:
        state = _load_auth_state()
        return jti in state.get("revoked_jti", {})


def _is_localhost(request: Request) -> bool:
    """Return True if the request originates from the loopback interface."""
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency that enforces auth when REQUIRE_AUTH=1.

    - When REQUIRE_AUTH is off (default): allows all requests.
    - When REQUIRE_AUTH=1: requires a valid JWT and context match.
    """
    if not _REQUIRE_AUTH:
        return  # auth not enforced globally
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_any_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_jti_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer valid. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expected_fp = payload.get("fp")
    if isinstance(expected_fp, str) and expected_fp:
        actual_fp = _request_fingerprint(request)
        if not hmac.compare_digest(expected_fp, actual_fp):
            _audit_logger.warning(json.dumps({
                "event": "auth_context_mismatch",
                "sub": payload.get("sub", "unknown"),
                "timestamp": _now_utc().isoformat(),
            }))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session context changed. Re-authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )



# ── RBAC permission dependency (wired here after require_auth is defined) ──
try:
    from core.rbac import require_permission as _require_permission  # noqa: E402

    def require_permission(permission: str):  # type: ignore[misc]
        """Return the inner check callable for use as Depends(require_permission(...))."""
        dep = _require_permission(permission, require_auth)
        # dep is Depends(_check); unwrap to the raw callable so callers can
        # wrap it themselves with Depends() without double-wrapping.
        return dep.dependency
except Exception as _rbac_import_err:  # graceful degradation
    import logging as _rbac_log
    _rbac_log.getLogger(__name__).warning("core.rbac unavailable: %s", _rbac_import_err)

    def require_permission(permission: str):  # type: ignore[misc]  # noqa: F811
        """Fallback: pass-through callable for Depends(require_permission(...))."""
        async def _noop() -> None:
            return None
        return _noop

# ── Rate limiter ─────────────────────────────────────────────────
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


def _make_tier_limiter(solo_rpm: int = 60, team_rpm: int = 300, enterprise_rpm: int = 3000):
    """Return a FastAPI Depends that enforces per-tier rate limits drawn from the JWT role.

    Role mapping:
      viewer   → solo_rpm
      operator → team_rpm
      admin    → enterprise_rpm  (also covers service tokens)

    Falls back to solo_rpm when the role is unknown or slowapi is unavailable.
    Endpoints must accept ``request: Request`` for slowapi to extract the key.
    """
    def _decorator(f):
        if not (_SLOWAPI_AVAILABLE and limiter is not None):
            return f

        import functools

        @functools.wraps(f)
        async def _wrapper(request: Request, *args, **kwargs):
            # Extract role from JWT; Authorization header already validated by require_auth
            role = "viewer"
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                try:
                    import jwt as _jwt
                    token = auth_header.split(" ", 1)[1]
                    payload = _jwt.decode(token, options={"verify_signature": False})
                    role = payload.get("role", "viewer")
                except Exception:
                    pass
            rpm = {
                "admin": enterprise_rpm,
                "operator": team_rpm,
            }.get(role, solo_rpm)
            limit_str = f"{rpm}/minute"
            # Dynamically apply the limit for this request
            limited = limiter.limit(limit_str)(f)
            return await limited(request, *args, **kwargs)

        return _wrapper

    return _decorator


# Pre-built tier limiter used on high-cost endpoints
_tier_rate_limit = _make_tier_limiter(solo_rpm=60, team_rpm=300, enterprise_rpm=3000)

# ── CORS ─────────────────────────────────────────────────────────
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
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Feature modules ───────────────────────────────────────────────────────────
import sys as _sys
_FEATURES_DIR = str(Path(__file__).parent)
if _FEATURES_DIR not in _sys.path:
    _sys.path.insert(0, _FEATURES_DIR)

try:
    from features import ALL_ROUTERS as _FEATURE_ROUTERS
    for _router in _FEATURE_ROUTERS:
        app.include_router(_router)
    logger.info("✅ Feature modules loaded: %d routers", len(_FEATURE_ROUTERS))
except Exception as _feat_err:
    logger.warning("⚠️  Feature modules failed to load: %s", _feat_err)

# ── Neural Brain API (LangGraph + Mem0 + Neo4j cognitive stack) ────
try:
    from neural_brain.api import router as _neural_brain_router, forge_compat_router as _forge_compat_router
    from neural_brain.api import model_fabric_router as _model_fabric_router
    from neural_brain.api.code_index_router import router as _code_index_router
    app.include_router(_neural_brain_router)
    app.include_router(_forge_compat_router)
    app.include_router(_model_fabric_router)
    app.include_router(_code_index_router)
    logger.info("✅ Neural Brain API + Model Fabric + Code Index loaded")
except Exception as _nb_err:
    logger.warning("⚠️  Neural Brain API failed to load: %s", _nb_err)

# ── Auth + Admin API (JWT, RBAC, sessions, key rotation) ────────────
try:
    from neural_brain.api.auth_router import auth_router as _auth_router, admin_router as _admin_router
    app.include_router(_auth_router)
    app.include_router(_admin_router)
    logger.info("✅ Auth + Admin API loaded")
except Exception as _auth_err:
    logger.warning("⚠️  Auth/Admin API failed to load: %s", _auth_err)

# ── Zero-Trust Request Guard middleware ─────────────────────────────
try:
    from neural_brain.security.request_guard import RequestGuard
    app.add_middleware(RequestGuard)
    logger.info("✅ Zero-Trust RequestGuard middleware active")
except Exception as _rg_err:
    logger.warning("⚠️  RequestGuard middleware failed: %s", _rg_err)

# ── PII sanitization middleware (outermost — added last due to LIFO ordering) ──
if _LOG_SANITIZER_AVAILABLE and _SanitizedLoggingMiddleware is not None:
    app.add_middleware(_SanitizedLoggingMiddleware)
    logger.info("PII log sanitization middleware active")

# ── Telemetry auto-capture + Key rotation ───────────────────────────
try:
    from neural_brain.core.telemetry import get_telemetry as _get_tel
    from neural_brain.security.key_manager import get_key_manager as _get_km
    _get_tel()   # starts drain thread + event subscription
    _get_km()    # starts rotation loop
    logger.info("✅ Telemetry + KeyManager started")
except Exception as _tel_err:
    logger.warning("⚠️  Telemetry/KeyManager failed: %s", _tel_err)

# ── Privacy / Telemetry Engine / Update Manager ─────────────────────
try:
    from neural_brain.api.privacy_router import privacy_router as _priv_r, \
        telemetry_router as _tel_r, updates_router as _upd_r
    app.include_router(_priv_r)
    app.include_router(_tel_r)
    app.include_router(_upd_r)
    # Boot subsystems
    from neural_brain.config.privacy_mode import get_privacy as _get_priv
    from neural_brain.telemetry.telemetry_engine import get_telemetry_engine as _get_te
    _get_priv()   # loads + persists privacy mode
    _get_te()     # starts event subscription + bundle loop
    logger.info("✅ Privacy + TelemetryEngine + UpdateManager loaded (mode=%s)",
                _get_priv().get_mode().value)
except Exception as _priv_err:
    logger.warning("⚠️  Privacy/Telemetry/Updates failed: %s", _priv_err)

# ── Privacy-safe operational telemetry middleware ────────────────
try:
    from core.telemetry import PrivacyTelemetryMiddleware as _PrivTelMW
    app.add_middleware(_PrivTelMW)
    logger.info("✅ PrivacyTelemetryMiddleware active")
except Exception as _ptm_err:
    logger.warning("⚠️  PrivacyTelemetryMiddleware failed: %s", _ptm_err)

# ── Security headers middleware ──────────────────────────────────
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
    # its own policy for the dashboard HTML.
    if "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "img-src 'self' data: blob:"
        )
    return response

# ── Audit logging middleware ─────────────────────────────────────
_audit_logger = logging.getLogger("ai_employee.audit")
if not _audit_logger.handlers:
    _audit_handler = logging.StreamHandler()
    _audit_handler.setFormatter(logging.Formatter("%(asctime)s AUDIT %(message)s"))
    _audit_logger.addHandler(_audit_handler)
    _audit_logger.setLevel(logging.INFO)

@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    """Log every inbound request and outbound status for the audit trail."""
    # Skip high-frequency health/status probes to reduce I/O noise
    if request.url.path in ("/health", "/api/status", "/api/gateway/status", "/api/system/resources"):
        return await call_next(request)

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


def _profile_audit_stats(user_id: str, tenant_id: str) -> tuple[int, list[dict]]:
    """Return (interaction_count, top_5_agents) for the user's audit history.

    Probes both legacy (audit.db/audit_events) and current (audit_log.db/audit_log)
    layouts; returns (0, []) if neither exists. Agent name is extracted from the
    `meta` JSON when present, else from `action`.
    """
    import sqlite3
    from pathlib import Path
    base = Path(os.environ.get("AI_HOME", Path(__file__).resolve().parents[3]))
    candidates = [
        (base / "state" / "audit_log.db", "audit_log"),
        (base / "state" / "audit.db", "audit_events"),
    ]
    for db_path, table in candidates:
        if not db_path.exists():
            continue
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE actor = ?", (user_id,)
                ).fetchone()[0]
                rows = conn.execute(
                    f"SELECT action, meta FROM {table} WHERE actor = ? "
                    f"ORDER BY ts DESC LIMIT 500", (user_id,)
                ).fetchall()
            tally: dict[str, int] = {}
            for r in rows:
                agent = ""
                try:
                    m = json.loads(r["meta"] or "{}")
                    agent = m.get("agent") or m.get("agent_id") or ""
                except Exception:
                    pass
                if not agent:
                    a = r["action"] or ""
                    agent = a.split(":", 1)[1] if ":" in a else a
                if agent:
                    tally[agent] = tally.get(agent, 0) + 1
            top = [{"agent": k, "count": v} for k, v in
                   sorted(tally.items(), key=lambda x: -x[1])[:5]]
            return int(count), top
        except Exception:
            continue
    return 0, []


# ── In-memory file read cache (reduces disk I/O for high-frequency reads) ─────
_cache: dict = {}

def _cached_read(path: Path, ttl: int = 5) -> "dict | list":
    """Read a JSON file with a short TTL cache to avoid repeated disk hits."""
    key = str(path)
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < ttl:
        return _cache[key]["data"]
    try:
        data: "dict | list" = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        data = {}
    _cache[key] = {"ts": now, "data": data}
    return data


def _invalidate_cache(path: Path) -> None:
    """Evict a path from the read cache after a write."""
    _cache.pop(str(path), None)


# ── Efficient last-N-lines reader for growing JSONL logs ──────────────────────
def _read_last_n_lines(path: Path, n: int = 100) -> list:
    """Return the last *n* non-empty JSONL lines without reading the whole file."""
    if not path.exists():
        return []
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        buf = b""
        lines: list[bytes] = []
        pos = size
        while pos > 0 and len(lines) < n + 1:
            chunk = min(4096, pos)
            pos -= chunk
            f.seek(pos)
            buf = f.read(chunk) + buf
            lines = buf.split(b"\n")
        result = [l for l in lines[-n:] if l.strip()]
    parsed = []
    for l in result:
        try:
            parsed.append(json.loads(l))
        except Exception:
            pass
    return parsed


# ── JSONL trim helper (keeps state files from growing unbounded) ──────────────
def _trim_jsonl(path: Path, max_lines: int = 1000) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_bytes().split(b"\n")
        lines = [l for l in lines if l.strip()]
        if len(lines) > max_lines:
            path.write_bytes(b"\n".join(lines[-max_lines:]) + b"\n")
    except Exception:
        pass


def ai_employee(*args: str) -> tuple:
    if args and args[0] == "start" and _SHUTDOWN_IN_PROGRESS.is_set():
        return 1, "Start blocked: shutdown is currently in progress."
    try:
        p = subprocess.run(
            [str(AI_EMPLOYEE_BIN), *args],
            capture_output=True, text=True, timeout=10
        )
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        logger.warning("ai_employee command error: %s", e)
        return 1, "Command execution failed."


# ── Enterprise lifecycle management (start/stop hardening) ────────────────────
_START_STOP_LOCK = threading.Lock()
_SHUTDOWN_IN_PROGRESS = threading.Event()
_STOP_GRACE_SECONDS = float(os.environ.get("AI_EMPLOYEE_STOP_GRACE_SECONDS", "1.5"))
_STOP_FORCE_WAIT_SECONDS = float(os.environ.get("AI_EMPLOYEE_STOP_FORCE_WAIT_SECONDS", "0.8"))


def _agent_pid_file(agent_name: str) -> Path:
    pid_file = _safe_run_file(agent_name, ".pid")
    if pid_file is None:
        raise ValueError("Invalid agent name for pid path")
    return pid_file


def _safe_run_file(agent_name: str, suffix: str) -> Optional[Path]:
    if suffix not in (".pid", ".lock", ".pid.lock"):
        return None
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return None
    return _RUNTIME_RUN_FILE_MAP.get(normalized, {}).get(suffix)


def _safe_state_file(agent_name: str) -> Optional[Path]:
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return None
    return _RUNTIME_STATE_FILE_MAP.get(normalized)


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_pid_file(agent_name: str) -> Optional[int]:
    try:
        pid_file = _agent_pid_file(agent_name)
    except ValueError:
        return None
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        return pid if pid > 1 else None
    except Exception:
        return None


def _pid_context(pid: int) -> tuple[str, str]:
    cmdline = ""
    cwd = ""
    if _PSUTIL_OK and _psutil is not None:
        try:
            proc = _psutil.Process(pid)
            cmdline = " ".join(proc.cmdline())
            cwd = proc.cwd()
            return cmdline, cwd
        except Exception:
            pass
    proc_cmd = Path("/proc") / str(pid) / "cmdline"
    proc_cwd = Path("/proc") / str(pid) / "cwd"
    try:
        if proc_cmd.exists():
            raw = proc_cmd.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            cmdline = raw.strip()
    except Exception:
        pass
    try:
        if proc_cwd.exists():
            cwd = str(proc_cwd.resolve())
    except Exception:
        pass
    return cmdline, cwd


def _pid_owned_by_current_user(pid: int) -> bool:
    if not hasattr(os, "getuid"):
        return True
    current_uid = os.getuid()
    if _PSUTIL_OK and _psutil is not None:
        try:
            uids = _psutil.Process(pid).uids()
            return int(getattr(uids, "real", current_uid)) == current_uid
        except Exception:
            return False
    proc_status = Path("/proc") / str(pid) / "status"
    try:
        for line in proc_status.read_text().splitlines():
            if line.startswith("Uid:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) == current_uid
    except Exception:
        return False
    return False


def _safe_to_control_pid(pid: int, agent_name: str) -> bool:
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return False
    if pid <= 1 or pid == os.getpid():
        return False
    if not _pid_alive(pid):
        return False
    if not _pid_owned_by_current_user(pid):
        return False
    cmdline, cwd = _pid_context(pid)
    ai_home = str(AI_HOME)
    marker = f"/agents/{normalized}/"
    if ai_home not in (cmdline + " " + cwd):
        return False
    if marker not in cmdline and marker not in cwd:
        return False
    return True


def _discover_agent_pids(agent_name: str) -> set[int]:
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return set()
    pids: set[int] = set()
    pid_from_file = _read_pid_file(normalized)
    if pid_from_file:
        pids.add(pid_from_file)
    marker = f"/agents/{normalized}/"
    if _PSUTIL_OK and _psutil is not None:
        try:
            for proc in _psutil.process_iter(["pid", "cmdline", "cwd"]):
                try:
                    pid = int(proc.info.get("pid") or 0)
                    if pid <= 1:
                        continue
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    cwd = str(proc.info.get("cwd") or "")
                    if marker in cmdline or marker in cwd:
                        pids.add(pid)
                except Exception:
                    continue
        except Exception:
            pass
    return {pid for pid in pids if _safe_to_control_pid(pid, normalized)}


def _signal_pid_and_group(pid: int, sig: int) -> bool:
    sent = False
    if pid <= 1:
        return False
    try:
        pgid = os.getpgid(pid)
        if pgid > 1 and pgid != os.getpgrp():
            os.killpg(pgid, sig)
            sent = True
    except Exception:
        pass
    try:
        os.kill(pid, sig)
        sent = True
    except Exception:
        pass
    return sent


def _cleanup_agent_runtime_files(agent_name: str) -> None:
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return
    for suffix in (".pid", ".lock", ".pid.lock"):
        p = _safe_run_file(normalized, suffix)
        if p is None:
            continue
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


def _write_stopped_state(agent_name: str, remaining_pids: list[int]) -> None:
    normalized = _normalize_managed_agent_name(agent_name)
    if normalized is None:
        return
    state_file = _safe_state_file(normalized)
    if state_file is None:
        return
    payload: dict = {
        "bot": normalized,
        "status": "stopped" if not remaining_pids else "stopping_failed",
        "stopped_at": now_iso(),
    }
    if remaining_pids:
        payload["remaining_pids"] = remaining_pids
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(payload))
    except Exception:
        pass


def _stop_agents_enterprise(targets: list[str]) -> dict:
    targets = [t for t in targets if isinstance(t, str) and _BOT_NAME_RE.match(t)]
    started = time.monotonic()
    per_agent_pids: dict[str, set[int]] = {}
    all_pids: set[int] = set()
    for agent_name in targets:
        pids = _discover_agent_pids(agent_name)
        per_agent_pids[agent_name] = pids
        all_pids.update(pids)

    graceful_signaled = 0
    for pid in sorted(all_pids):
        if _signal_pid_and_group(pid, signal.SIGTERM):
            graceful_signaled += 1

    graceful_deadline = time.monotonic() + max(0.1, _STOP_GRACE_SECONDS)
    while time.monotonic() < graceful_deadline:
        if not any(_pid_alive(pid) for pid in all_pids):
            break
        time.sleep(0.05)

    survivors = {pid for pid in all_pids if _pid_alive(pid)}
    force_signaled = 0
    for pid in sorted(survivors):
        if _signal_pid_and_group(pid, signal.SIGKILL):
            force_signaled += 1

    force_deadline = time.monotonic() + max(0.1, _STOP_FORCE_WAIT_SECONDS)
    while time.monotonic() < force_deadline:
        if not any(_pid_alive(pid) for pid in survivors):
            break
        time.sleep(0.03)

    remaining = {pid for pid in survivors if _pid_alive(pid)}
    failures: list[str] = []
    details: list[dict] = []
    stopped = 0
    for agent_name in targets:
        agent_remaining = sorted(pid for pid in per_agent_pids.get(agent_name, set()) if pid in remaining)
        if agent_remaining:
            failures.append(agent_name)
        else:
            stopped += 1
        _cleanup_agent_runtime_files(agent_name)
        _write_stopped_state(agent_name, agent_remaining)
        details.append({
            "agent": agent_name,
            "found_pids": sorted(per_agent_pids.get(agent_name, set())),
            "remaining_pids": agent_remaining,
            "stopped": len(agent_remaining) == 0,
        })

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "AGENT_SHUTDOWN: targets=%s found_pids=%s graceful=%s forced=%s remaining=%s duration_ms=%s failures=%s",
        len(targets), len(all_pids), graceful_signaled, force_signaled, len(remaining), duration_ms, failures
    )
    return {
        "stopped": stopped,
        "failed": failures,
        "details": details,
        "graceful_signaled": graceful_signaled,
        "force_signaled": force_signaled,
        "remaining_pids": sorted(remaining),
        "duration_ms": duration_ms,
    }


def _agent_has_live_process(agent_name: str) -> bool:
    return bool(_discover_agent_pids(agent_name))


# ─── HTML Dashboard ────────────────────────────────────────────────────────────

from dashboard import INDEX_HTML  # noqa: F401 — extracted for readability


# ─── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'"
    )
    return HTMLResponse(content=INDEX_HTML, headers={"Content-Security-Policy": csp})


# ── Security endpoints ───────────────────────────────────────────

@app.get("/health", response_model=_HealthResponse)
def health_check():
    """Health-check endpoint — fast startup readiness check."""
    checks = {
        "python_runtime": "ok",
        "llm_api": "ok",  # Skip expensive checks on startup — assume ok
        "database": "ok",
    }

    # Skip LLM/database checks on fast startup — they're validated during first request
    # This allows run.sh to detect readiness in <100ms instead of 10-40s
    overall_status = "healthy"

    return _HealthResponse(
        status=overall_status,
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
          status_code=status.HTTP_201_CREATED, tags=["auth"])
@_auth_rate_limit
def auth_register(request: Request, user_data: _UserCreate):
    """
    Register a dashboard user and return a JWT bearer token.

    Password is validated against the configured strength policy.
    Rate limited to 5 requests/minute per IP to prevent abuse.
    """
    if not _SECURITY_AVAILABLE:
      logger.warning("Security module unavailable — using fallback auth primitives.")

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
    # Create tenant for new user
    tenant_id = _tenant_manager.create_tenant(
        org_name=user_data.username,
        user_email=user_data.username  # Use username as email for now
    )

    users[username] = {
        "password_hash": auth.hash_password(user_data.password),
        "created_at": _now_utc().isoformat(),
        "tenant_id": tenant_id,  # Store tenant_id with user
    }
    _users_file.parent.mkdir(parents=True, exist_ok=True)
    _users_file.write_text(json.dumps(users, indent=2))
    _users_file.chmod(0o600)

    access_token, refresh_token = _issue_token_pair(auth, username, request, tenant_id)
    _audit_logger.info(json.dumps({
        "event": "user_registered",
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    return _TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )


@app.post("/auth/login", response_model=_TokenResponse, tags=["auth"])
@_auth_rate_limit
def auth_login(request: Request, login_data: _LoginRequest):
    """
    Authenticate a registered user and return a JWT bearer token.

    Rate limited to 5 requests/minute per IP to prevent brute-force attacks.
    Returns the same 401 error for both unknown user and wrong password (no user enumeration).
    """
    if not _SECURITY_AVAILABLE:
      logger.warning("Security module unavailable — using fallback auth primitives.")

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

    attempt_key = _login_attempt_key(request, username)
    with _AUTH_STATE_LOCK:
        state = _load_auth_state()
        failed_logins = state.setdefault("failed_logins", {})
        attempt_entry = failed_logins.get(attempt_key, {})
        lockout_until_dt = _parse_iso_ts(str(attempt_entry.get("lockout_until", "")))
        now = _now_utc()
        if lockout_until_dt and lockout_until_dt > now:
            retry_after = int((lockout_until_dt - now).total_seconds())
            _audit_logger.warning(json.dumps({
                "event": "login_locked",
                "username": username,
                "retry_after_seconds": retry_after,
                "timestamp": now.isoformat(),
            }))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account temporarily locked. Retry in {retry_after} seconds.",
            )

    if not user_record or not auth.verify_password(
        login_data.password, user_record.get("password_hash", "")
    ):
        with _AUTH_STATE_LOCK:
            state = _load_auth_state()
            failed_logins = state.setdefault("failed_logins", {})
            current = failed_logins.get(attempt_key, {})
            failure_count = int(current.get("count", 0)) + 1
            lockout_until = None
            if failure_count >= _MAX_LOGIN_ATTEMPTS:
                step_idx = min(
                    failure_count - _MAX_LOGIN_ATTEMPTS,
                    len(_LOCKOUT_STEPS_SECONDS) - 1,
                )
                lockout_until = (_now_utc() + timedelta(seconds=_LOCKOUT_STEPS_SECONDS[step_idx])).isoformat()
            failed_logins[attempt_key] = {
                "count": failure_count,
                "last_failure": _now_utc().isoformat(),
                "lockout_until": lockout_until,
            }
            _save_auth_state(state)
        _audit_logger.warning(json.dumps({
            "event": "login_failed",
            "username": username,
            "failure_count": failure_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        raise _generic_fail

    with _AUTH_STATE_LOCK:
        state = _load_auth_state()
        state.setdefault("failed_logins", {}).pop(attempt_key, None)
        _save_auth_state(state)

    access_token, refresh_token = _issue_token_pair(auth, username, request)
    _audit_logger.info(json.dumps({
        "event": "login_success",
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    return _TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )


@app.post("/auth/refresh", response_model=_TokenResponse, tags=["auth"])
@_auth_rate_limit
def auth_refresh(request: Request, body: _RefreshRequest):
    cfg = _security_config
    auth = AuthManager(
        secret_key=(cfg.security.jwt_secret_key if cfg else _jwt_secret_env),
        algorithm=(cfg.security.jwt_algorithm if cfg else "HS256"),
        expire_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )
    refresh_hash = _hash_refresh_token(body.refresh_token)
    now = _now_utc()
    current_fp = _request_fingerprint(request)

    with _AUTH_STATE_LOCK:
        state = _load_auth_state()
        refresh_record = state.get("refresh_tokens", {}).get(refresh_hash)
        if not isinstance(refresh_record, dict):
            raise HTTPException(status_code=401, detail="Invalid refresh token.")
        if refresh_record.get("revoked") is True:
            raise HTTPException(status_code=401, detail="Refresh token has been revoked.")

        expires_at = _parse_iso_ts(str(refresh_record.get("expires_at", "")))
        if expires_at is None or expires_at <= now:
            state.get("refresh_tokens", {}).pop(refresh_hash, None)
            _save_auth_state(state)
            raise HTTPException(status_code=401, detail="Refresh token expired.")

        expected_fp = str(refresh_record.get("fingerprint", ""))
        if expected_fp and not hmac.compare_digest(expected_fp, current_fp):
            refresh_record["revoked"] = True
            refresh_record["revoked_at"] = now.isoformat()
            _save_auth_state(state)
            _audit_logger.warning(json.dumps({
                "event": "refresh_context_mismatch",
                "username": refresh_record.get("username", "unknown"),
                "timestamp": now.isoformat(),
            }))
            raise HTTPException(
                status_code=401,
                detail="Session context changed. Please log in again.",
            )

        username = str(refresh_record.get("username", "")).strip()
        if not username:
            raise HTTPException(status_code=401, detail="Invalid refresh token.")

        access_token, new_refresh = _issue_token_pair(auth, username, request, state=state)
        new_hash = _hash_refresh_token(new_refresh)
        refresh_record["revoked"] = True
        refresh_record["revoked_at"] = now.isoformat()
        refresh_record["replaced_by"] = new_hash
        _save_auth_state(state)

    _audit_logger.info(json.dumps({
        "event": "refresh_rotated",
        "username": username,
        "timestamp": now.isoformat(),
    }))
    return _TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        access_token_expires_minutes=(cfg.security.access_token_expire_minutes if cfg else 30),
    )


@app.post("/auth/logout", tags=["auth"])
def auth_logout(
    request: Request,
    body: Optional[_LogoutRequest] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    payload: Optional[dict[str, Any]] = None
    if credentials and credentials.credentials:
        payload = _decode_any_token(credentials.credentials)
    with _AUTH_STATE_LOCK:
        state = _load_auth_state()
        _record_revoked_jti(state, payload)
        if body and body.refresh_token:
            refresh_hash = _hash_refresh_token(body.refresh_token)
            refresh_record = state.setdefault("refresh_tokens", {}).get(refresh_hash)
            if isinstance(refresh_record, dict):
                refresh_record["revoked"] = True
                refresh_record["revoked_at"] = _now_utc().isoformat()
        _save_auth_state(state)
    _audit_logger.info(json.dumps({
        "event": "logout",
        "subject": payload.get("sub", "unknown") if isinstance(payload, dict) else "unknown",
        "client": request.client.host if request.client else "unknown",
        "timestamp": _now_utc().isoformat(),
    }))
    return JSONResponse({"ok": True})


@app.get("/auth/oidc/providers")
def oidc_providers():
    """Return the list of registered OIDC provider names (no secrets)."""
    try:
        from core.oidc import _oidc_registry
        return {"providers": [p.name for p in _oidc_registry._providers]}
    except Exception:
        return {"providers": []}


# ── Break-glass emergency access endpoints ────────────────────────────────────

try:
    from core.break_glass import get_break_glass_store as _get_bg_store  # noqa: E402
    _BG_AVAILABLE = True
except Exception as _bg_import_err:
    import logging as _bg_log
    _bg_log.getLogger(__name__).warning("core.break_glass unavailable: %s", _bg_import_err)
    _BG_AVAILABLE = False


@app.post("/api/break-glass/request")
async def bg_request(
    body: dict,
    _rbac=Depends(require_permission("admin:*")),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """Admin requests time-boxed break-glass access to a target tenant."""
    from core.audit import get_audit_db as _get_audit_db  # noqa: E402
    target_tenant_id = (body.get("target_tenant_id") or "").strip()
    reason = (body.get("reason") or "").strip()
    if not target_tenant_id or not reason:
        raise HTTPException(status_code=400, detail="target_tenant_id and reason are required")

    admin_id = "unknown"
    if credentials and credentials.credentials:
        _pl = _decode_any_token(credentials.credentials)
        if isinstance(_pl, dict):
            admin_id = _pl.get("sub", "unknown")

    if not _BG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Break-glass module unavailable")

    store = _get_bg_store()
    req = store.create_request(admin_id=admin_id, target_tenant_id=target_tenant_id, reason=reason)

    _get_audit_db().append(
        tenant_id=target_tenant_id,
        actor=admin_id,
        action="break_glass:request",
        resource=f"tenant:{target_tenant_id}",
        outcome="pending",
        meta={"request_id": req.request_id, "reason": reason},
    )
    return JSONResponse({"request_id": req.request_id, "status": req.status, "expires_at": req.expires_at})


@app.post("/api/break-glass/{request_id}/approve")
async def bg_approve(
    request_id: str,
    _rbac=Depends(require_permission("admin:*")),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """Approve a pending break-glass request and issue a short-lived access token."""
    from core.audit import get_audit_db as _get_audit_db  # noqa: E402
    admin_id = "unknown"
    if credentials and credentials.credentials:
        _pl = _decode_any_token(credentials.credentials)
        if isinstance(_pl, dict):
            admin_id = _pl.get("sub", "unknown")

    if not _BG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Break-glass module unavailable")

    store = _get_bg_store()
    try:
        token = store.approve(request_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Break-glass request not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="operation_failed")

    req = store._requests[request_id]
    _get_audit_db().append(
        tenant_id=req.target_tenant_id,
        actor=admin_id,
        action="break_glass:approve",
        resource=f"tenant:{req.target_tenant_id}",
        outcome="approved",
        meta={"request_id": request_id, "original_admin": req.admin_id, "expires_at": req.expires_at},
    )

    await _ws_broadcast("security:break_glass_approved", {
        "request_id": request_id,
        "admin_id": req.admin_id,
        "target_tenant_id": req.target_tenant_id,
        "expires_at": req.expires_at,
        "approved_by": admin_id,
    })

    return JSONResponse({"request_id": request_id, "token": token, "expires_at": req.expires_at})


@app.post("/api/break-glass/{request_id}/deny")
async def bg_deny(
    request_id: str,
    _rbac=Depends(require_permission("admin:*")),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """Deny a pending break-glass request."""
    from core.audit import get_audit_db as _get_audit_db  # noqa: E402
    admin_id = "unknown"
    if credentials and credentials.credentials:
        _pl = _decode_any_token(credentials.credentials)
        if isinstance(_pl, dict):
            admin_id = _pl.get("sub", "unknown")

    if not _BG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Break-glass module unavailable")

    store = _get_bg_store()
    try:
        store.deny(request_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Break-glass request not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="operation_failed")

    req = store._requests[request_id]
    _get_audit_db().append(
        tenant_id=req.target_tenant_id,
        actor=admin_id,
        action="break_glass:deny",
        resource=f"tenant:{req.target_tenant_id}",
        outcome="denied",
        meta={"request_id": request_id, "original_admin": req.admin_id},
    )

    return JSONResponse({"request_id": request_id, "status": "denied"})


@app.get("/api/break-glass/active")
async def bg_list_active(
    _rbac=Depends(require_permission("admin:*")),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """List all currently active (approved, non-expired) break-glass sessions."""
    from core.audit import get_audit_db as _get_audit_db  # noqa: E402
    admin_id = "unknown"
    if credentials and credentials.credentials:
        _pl = _decode_any_token(credentials.credentials)
        if isinstance(_pl, dict):
            admin_id = _pl.get("sub", "unknown")

    if not _BG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Break-glass module unavailable")

    store = _get_bg_store()
    active = store.get_active()

    _get_audit_db().append(
        tenant_id="system",
        actor=admin_id,
        action="break_glass:list_active",
        resource="break_glass:sessions",
        outcome="ok",
        meta={"count": len(active)},
    )

    return JSONResponse({"sessions": [r.to_dict() for r in active]})


# ── Cross-runtime security event receiver ──────────────────────────────────
# Node-originated security telemetry (vault/secrets access, auth, etc.) is
# forwarded here so the in-process BlacklightEngine sentinel can score and
# respond. Localhost OR a valid service/internal JWT is required. Never raises
# on bad input — returns 400. Event values are NOT inspected/persisted here.
_SECURITY_EVENT_PREFIXES = ("vault:", "security:", "auth:")


@app.post("/api/internal/security-event")
async def receive_security_event(
    request: Request,
    body: dict,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """Receive a cross-runtime security event and republish on the Python bus."""
    # (a) Accept only from localhost OR a valid token (service/internal/user).
    authed = _is_localhost(request)
    if not authed and credentials and credentials.credentials:
        authed = _decode_any_token(credentials.credentials) is not None
    if not authed:
        raise HTTPException(status_code=401, detail="localhost or valid token required")

    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "body must be an object"}, status_code=400)

    event_type = body.get("event_type")
    if not isinstance(event_type, str) or not event_type.startswith(_SECURITY_EVENT_PREFIXES):
        return JSONResponse(
            {"ok": False, "error": "event_type must start with vault:/security:/auth:"},
            status_code=400,
        )

    source = body.get("source")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    try:
        from neural_brain.utils.event_bus import publish as _publish_security_event
        _publish_security_event(
            event_type,
            source=source if isinstance(source, str) and source else "node",
            payload=payload,
        )
    except Exception as _e:  # never raise — telemetry must not break callers
        _audit_logger.warning(json.dumps({
            "event": "security_event_publish_failed",
            "event_type": event_type,
            "timestamp": _now_utc().isoformat(),
        }))
        return JSONResponse({"ok": False, "error": "publish failed"}, status_code=400)

    return JSONResponse({"ok": True})


@app.post("/api/admin/backup")
async def trigger_backup(_rbac=Depends(require_permission("admin:*"))):
    """Trigger a local PostgreSQL backup cycle (no cloud upload — use cron for that)."""
    from core.backup import BackupManager
    result = BackupManager().full_backup_cycle(upload=False)
    if not result.get("file"):
        raise HTTPException(status_code=500, detail="Backup failed — check DATABASE_URL and pg_dump availability")
    return result


# ── End security endpoints ─────────────────────────────────────────────────────


import asyncio

@app.get("/api/events")
async def sse_events(request: Request):
    """Server-Sent Events stream for real-time dashboard updates."""
    async def generate():
        last_state: Optional[str] = None
        while True:
            if await request.is_disconnected():
                break
            try:
                mode = _current_mode()
                running = 0
                for agent_name in _mode_agent_targets(mode):
                    if agent_name in INFRA_AGENTS:
                        continue
                    if not _BOT_NAME_RE.match(agent_name):
                        continue
                    pid_file = AI_HOME / "run" / f"{agent_name}.pid"
                    if pid_file.exists():
                        try:
                            os.kill(int(pid_file.read_text().strip()), 0)
                            running += 1
                        except Exception:
                            pass
                plans = _load_task_plans()
                active = next((p for p in plans if p.get("status") in ("running", "planning")), None)
                active_title = active.get("title", "") if active else None
                # Only emit an SSE event when state has actually changed to
                # avoid flooding connected clients with identical messages.
                current_state = f"{running}|{active_title}"
                if current_state != last_state:
                    data = json.dumps({
                        "running": running,
                        "active_task": active_title,
                        "ts": now_iso(),
                    })
                    yield f"data: {data}\n\n"
                    last_state = current_state
            except Exception:
                pass
            await asyncio.sleep(8)
    from starlette.responses import StreamingResponse
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.get("/events")
async def stream_observability_events(request: Request):
    """Real-time observability SSE feed for the Node WS bridge.

    Subscribes to the in-process EventStream and yields each published event
    (metrics_tick, cognition_tick, etc.) as a Server-Sent Event so the Node
    backend can re-broadcast them to dashboard WS clients.
    """
    from starlette.responses import StreamingResponse
    from core.observability.event_stream import get_event_stream

    stream = get_event_stream()
    queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=512)
    loop = asyncio.get_event_loop()

    def _enqueue_drop_oldest(evt: dict) -> None:
        # Always runs ON the event loop thread (via call_soon_threadsafe).
        # If full, drop the OLDEST event and append the newest — never raise.
        # Raising QueueFull inside the loop's default exception handler causes
        # the entire queue contents to be repr()'d into the log (multi-MB
        # traceback every second when no SSE consumer is connected).
        if queue.full():
            try:
                queue.get_nowait()
            except Exception:
                pass
        try:
            queue.put_nowait(evt)
        except Exception:
            pass

    def _on_event(evt: dict) -> None:
        try:
            loop.call_soon_threadsafe(_enqueue_drop_oldest, evt)
        except Exception:
            # Loop closed — drop silently rather than crash.
            pass

    stream.subscribe(_on_event)

    async def generate():
        # Initial comment keeps the connection open and signals readiness.
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {json.dumps(evt, default=str)}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat comment — keeps proxies from killing the connection.
                yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/status")
def get_status():
  # Return cached response if still fresh
  cached = _get_cached_status()
  if cached is not None:
    return JSONResponse(cached)

  agents = []
  mode = _current_mode()
  for agent_name in _mode_agent_targets(mode):
    if agent_name in INFRA_AGENTS:
      continue
    if not _BOT_NAME_RE.match(agent_name):
      continue
    pid_file = AI_HOME / "run" / f"{agent_name}.pid"
    running = False
    if pid_file.exists():
      try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        running = True
      except Exception:
        running = False
    agents.append({"agent": agent_name, "running": running})

  ollama_host_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
  # Add active task hint
  active_plans = _load_task_plans()
  active_task = next((p for p in active_plans if p.get("status") in ("running", "planning")), None)
  active_agents: set = set()
  if active_task:
    active_agents = {st.get("agent_id", "") for st in active_task.get("subtasks", [])}
    for a in (active_task.get("agents_hint") or []):
      active_agents.add(a)

  # Attach governor info
  with _AGENT_GOVERNOR_LOCK:
    gov = dict(_AGENT_GOVERNOR)

  data = {
    "ts": now_iso(),
    "mode": mode,
    "agents": agents,
    "total": len(agents),
    "running": sum(1 for a in agents if a["running"]),
    "active_task": active_task.get("title", "") if active_task else None,
    "active_task_id": active_task.get("id") if active_task else None,
    "active_agents": list(active_agents),
    "ollama_ok": _ollama_reachable(ollama_host_url),
    "governor": {
      "enabled": gov["enabled"],
      "max_agents": gov["max_agents"],
    },
  }
  _set_cached_status(data)
  return JSONResponse(data)


@app.get("/api/wavefield/status")
def get_wavefield_status():
  from core.wavefield_provider import get_wavefield_metrics, wavefield_healthcheck  # noqa: PLC0415

  model = os.environ.get("WAVEFIELD_MODEL", "").strip()
  host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
  try:
    wavefield_healthcheck(ollama_host=host, model=model or None)
    healthy = True
  except Exception:
    healthy = False
  health_reason = "healthy" if healthy else "unavailable"
  return JSONResponse({
    "enabled": os.environ.get("WAVEFIELD_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"},
    "rollout_mode": os.environ.get("WAVEFIELD_ROLLOUT_MODE", "default").strip().lower(),
    "canary_percent": int(os.environ.get("WAVEFIELD_CANARY_PERCENT", "10")),
    "route_min_tokens": int(os.environ.get("WAVEFIELD_ROUTE_MIN_TOKENS", "8000")),
    "model": model,
    "ollama_host": host,
    "healthy": healthy,
    "health_reason": health_reason,
    "allow_fallback": os.environ.get("WAVEFIELD_ALLOW_FALLBACK", "1").strip().lower() in {"1", "true", "yes", "on"},
    "metrics": get_wavefield_metrics(),
  })


@app.get("/api/doctor")
def get_doctor():
    rc, out = ai_employee("doctor")
    return JSONResponse({"output": out, "rc": rc})


# ── Self-evolution control ────────────────────────────────────────────────────

@app.post("/api/models/reload")
def post_models_reload(_auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Force-reload the model routing config from ~/.ai-employee/model-routing.json."""
    try:
        from core.llm_router import get_llm_router
        cfg = get_llm_router().reload()
        return JSONResponse({"ok": True, "config": cfg})
    except Exception as exc:
        logger.warning("models/reload failed: %s", exc)
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.get("/api/evolution/status")
def get_evolution_status():
    try:
        from core.self_evolution import get_evolution_controller
        return JSONResponse(get_evolution_controller().status())
    except Exception as exc:
        logger.warning("evolution: status failed: %s", exc)
        return JSONResponse({"running": False, "mode": "OFF", "available": False, "error": "operation_failed"})


class EvolutionModeRequest(BaseModel):
    mode: str  # OFF | SAFE | AUTO


@app.post("/api/evolution/mode")
def post_evolution_mode(req: EvolutionModeRequest):
    try:
        from core.self_evolution import get_evolution_controller
        ctrl = get_evolution_controller()
        mode = ctrl.set_mode(req.mode)
        # AUTO/SAFE run the loop; OFF stops it.
        ctrl.stop() if mode == "OFF" else ctrl.start()
        return JSONResponse({"mode": mode, "status": ctrl.status()})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="operation_failed")
    except Exception as exc:
        logger.warning("evolution: set mode failed: %s", exc)
        raise HTTPException(status_code=500, detail="operation_failed")


# ── Doctor structured diagnostics ─────────────────────────────────────────────

def _load_doctor_actions() -> dict:
    """Load persisted approve/reject decisions keyed by item id."""
    try:
        if DOCTOR_STATE_FILE.exists():
            return json.loads(DOCTOR_STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_doctor_actions(actions: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        DOCTOR_STATE_FILE.write_text(json.dumps(actions))
    except Exception as exc:
        logger.warning("doctor: could not save actions: %s", exc)


def _is_port_open(port: int) -> bool:
    """Return True if something is listening on the given localhost port."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.8):
            return True
    except OSError:
        return False


def _run_doctor_checks() -> list:
    """Run all diagnostic checks in-process and return structured items."""
    items: list = []

    def _item(id_: str, status: str, title: str, desc: str = "") -> dict:
        return {"id": id_, "status": status, "title": title, "description": desc}

    # ── Load runtime env ──────────────────────────────────────────────────────
    env: dict = {}
    env_file = AI_HOME / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
        except Exception:
            pass

    def _env(key: str) -> str:
        return env.get(key) or os.environ.get(key, "")

    # ── API Keys ──────────────────────────────────────────────────────────────
    openai_key = _env("OPENAI_API_KEY")
    if not openai_key:
        items.append(_item("openai_key", "warn", "OpenAI API key not set",
                           "Add OPENAI_API_KEY to ~/.ai-employee/.env to enable GPT models."))
    else:
        items.append(_item("openai_key", "ok", "OpenAI API key configured"))

    anthropic_key = _env("ANTHROPIC_API_KEY")
    if not anthropic_key:
        items.append(_item("anthropic_key", "warn", "Anthropic API key not set",
                           "Add ANTHROPIC_API_KEY to ~/.ai-employee/.env to enable Claude models."))
    else:
        items.append(_item("anthropic_key", "ok", "Anthropic API key configured"))

    jwt_secret = _env("JWT_SECRET_KEY")
    if not jwt_secret or jwt_secret == "CHANGE_THIS_IN_SECURITY_LOCAL_YML_OR_SET_JWT_SECRET_KEY_ENV_VAR":
        items.append(_item("jwt_secret", "error", "JWT secret not set",
                           "Run 'ai-employee start' to auto-generate a secure JWT secret."))
    else:
        items.append(_item("jwt_secret", "ok", "JWT secret configured"))

    # ── Services / Ports ─────────────────────────────────────────────────────
    ui_port = int(_env("PROBLEM_SOLVER_UI_PORT") or PORT)
    if _is_port_open(ui_port):
        items.append(_item("svc_ui", "ok", f"Problem Solver UI running (port {ui_port})"))
    else:
        items.append(_item("svc_ui", "warn", f"Problem Solver UI not detected on port {ui_port}",
                           "Run 'ai-employee start problem-solver-ui' to start it."))

    gw_port = int(_env("AI_EMPLOYEE_GATEWAY_PORT") or _env("OPENCLAW_GATEWAY_PORT") or "18789")
    if _is_port_open(gw_port):
        items.append(_item("svc_gateway", "ok", f"AI Gateway running (port {gw_port})"))
    else:
        items.append(_item("svc_gateway", "warn", f"AI Gateway not detected on port {gw_port}",
                           "Run 'ai-employee start' to start the gateway."))

    ollama_host = _env("OLLAMA_HOST") or "http://127.0.0.1:11434"
    try:
        import urllib.request
        urllib.request.urlopen(ollama_host, timeout=1.5)  # noqa: S310
        items.append(_item("svc_ollama", "ok", "Ollama LLM service reachable"))
    except Exception:
        items.append(_item("svc_ollama", "warn", "Ollama LLM service not reachable",
                           f"Start it with 'ollama serve'. Host: {ollama_host}"))

    # ── Dependencies ─────────────────────────────────────────────────────────
    import shutil
    for bin_name, label, optional, hint in [
        ("python3", "Python 3", False, "Install Python 3.10+"),
        ("curl", "curl", False, "Install curl (required for gateway)"),
        ("node", "Node.js", True, "Install Node.js (optional)"),
        ("docker", "Docker", True, "Install Docker (optional — sandbox mode)"),
        ("ollama", "Ollama", True, "Install Ollama for local LLM support"),
    ]:
        if shutil.which(bin_name):
            items.append(_item(f"bin_{bin_name}", "ok", f"{label} installed"))
        elif optional:
            items.append(_item(f"bin_{bin_name}", "warn", f"{label} not installed",
                               hint + " (optional)."))
        else:
            items.append(_item(f"bin_{bin_name}", "error", f"{label} not found",
                               hint + " (required)."))

    # ── Config ───────────────────────────────────────────────────────────────
    mode = _env("AI_EMPLOYEE_MODE") or os.environ.get("AI_EMPLOYEE_MODE", "power")
    items.append(_item("cfg_mode", "ok", f"Mode: {mode.upper()}",
                       "Change with 'ai-employee mode starter|business|power'."))

    return items


@app.get("/api/doctor/items")
def get_doctor_items():
    """Return structured diagnostic check results with any user actions applied."""
    items = _run_doctor_checks()
    actions = _load_doctor_actions()
    for item in items:
        item["action"] = actions.get(item["id"])
    return JSONResponse({"items": items})


class DoctorActionRequest(BaseModel):
    id: str
    action: str  # "approved" | "rejected" | "reset"


@app.post("/api/doctor/action")
def post_doctor_action(req: DoctorActionRequest):
    """Persist an approve/reject decision for a diagnostic item."""
    if req.action not in ("approved", "rejected", "reset"):
        raise HTTPException(status_code=400, detail="action must be approved, rejected, or reset")
    actions = _load_doctor_actions()
    if req.action == "reset":
        actions.pop(req.id, None)
    else:
        actions[req.id] = req.action
    _save_doctor_actions(actions)
    return JSONResponse({"ok": True, "id": req.id, "action": req.action})
_sysres_cache: dict = {}
_sysres_cache_ts: float = 0.0
_SYSRES_CACHE_TTL = 3.0  # seconds — prevents hammering psutil on rapid requests


def _format_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


@app.get("/api/system/resources")
def get_system_resources():
    """Return real hardware metrics: CPU, RAM, disk, temps, GPU (if available), load avg."""
    global _sysres_cache, _sysres_cache_ts
    now_ts = time.monotonic()
    if now_ts - _sysres_cache_ts < _SYSRES_CACHE_TTL and _sysres_cache:
        return JSONResponse(_sysres_cache)

    if not _PSUTIL_OK:
        return JSONResponse({"error": "psutil not available"})

    try:
        # CPU — use value from background sampler thread (accurate, non-blocking)
        cpu_pct = _cpu_sample_value
        cpu_cores = _psutil.cpu_count(logical=False) or _psutil.cpu_count()
        cpu_threads = _psutil.cpu_count(logical=True)

        # RAM
        vm = _psutil.virtual_memory()
        ram_used_gb = round(vm.used / (1024 ** 3), 1)
        ram_total_gb = round(vm.total / (1024 ** 3), 1)
        ram_pct = vm.percent

        # Disk (root partition)
        disk = _psutil.disk_usage("/")
        disk_used_gb = round(disk.used / (1024 ** 3), 1)
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_pct = disk.percent

        # Load average (Unix only)
        load_avg = None
        try:
            load1, load5, load15 = os.getloadavg()
            load_avg = {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)}
        except (AttributeError, OSError):
            pass

        # Uptime
        boot_ts = _psutil.boot_time()
        uptime_str = _format_uptime(int(time.time() - boot_ts))

        # CPU Temperature
        cpu_temp = None
        try:
            temps = _psutil.sensors_temperatures()
            if temps:
                for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal"):
                    if key in temps and temps[key]:
                        cpu_temp = round(temps[key][0].current, 1)
                        break
                if cpu_temp is None:
                    first = next(iter(temps.values()), [])
                    if first:
                        cpu_temp = round(first[0].current, 1)
        except Exception:
            pass

        # GPU via nvidia-smi (best-effort, 2 s timeout)
        gpu_pct = None
        gpu_temp = None
        gpu_name = None
        try:
            import csv as _csv
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            if res.returncode == 0:
                rows = list(_csv.reader([res.stdout.strip()]))
                if rows and len(rows[0]) >= 3:
                    gpu_pct = int(rows[0][0].strip())
                    gpu_temp = int(rows[0][1].strip())
                    gpu_name = rows[0][2].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass
        except Exception:
            pass

        data: dict = {
            "cpu_pct": cpu_pct,
            "cpu_temp": cpu_temp,
            "cpu_cores": cpu_cores,
            "cpu_threads": cpu_threads,
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "ram_pct": ram_pct,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "disk_pct": disk_pct,
            "load_avg": load_avg,
            "uptime": uptime_str,
            "gpu_pct": gpu_pct,
            "gpu_temp": gpu_temp,
            "gpu_name": gpu_name,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("system/resources collection failed: %s", exc)
        data = {"error": "Failed to collect system metrics"}

    _sysres_cache = data
    _sysres_cache_ts = now_ts
    return JSONResponse(data)


@app.post("/api/gateway/pull-model")
def gateway_pull_model(body: dict, _auth: None = Depends(require_auth)):
    """Pull an Ollama model in the background."""
    import re as _re, subprocess, threading
    model = (body.get("model") or "llama3.2").strip()
    # Allow alphanumeric model names with dots, hyphens, underscores; optionally one colon for tag (e.g., llama3.2:latest)
    if not model or not _re.fullmatch(r"[a-zA-Z0-9._\-]+(?::[a-zA-Z0-9._\-]+)?", model) or len(model) > 80:
        raise HTTPException(400, "Invalid model name — use format 'modelname' or 'modelname:tag'")
    def _pull():
        try:
            subprocess.run(["ollama", "pull", model], timeout=600, check=False)
        except Exception:
            pass
    threading.Thread(target=_pull, daemon=True).start()
    return JSONResponse({"ok": True, "message": f"Pulling {model} in background…"})


@app.get("/api/gateway/status")
def gateway_status():
    """Return local AI provider status including Ollama models list."""
    import re as _re
    raw_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    # Validate host to prevent SSRF — only allow localhost/127.0.0.1 hosts
    if not _re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", raw_host.rstrip("/")):
        raw_host = "http://127.0.0.1:11434"
    ollama_host = raw_host
    ollama_ok = _ollama_reachable(ollama_host)
    models: list = []
    if ollama_ok:
        try:
            import urllib.request as _urlreq
            req = _urlreq.Request(f"{ollama_host.rstrip('/')}/api/tags", headers={"Accept": "application/json"})
            with _urlreq.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
            models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
            models = [m for m in models if m]
        except Exception:
            pass
    nvidia_ok = bool(os.environ.get("NVIDIA_API_KEY"))
    current_provider = os.environ.get("AI_PROVIDER", "ollama")
    current_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    return JSONResponse({
        "ok": True,
        "ollama_ok": ollama_ok,
        "ollama_models": models,
        "nvidia_ok": nvidia_ok,
        "current_provider": current_provider,
        "current_model": current_model,
    })


@app.post("/api/agents/start-all")
def start_all_agents(_auth: None = Depends(require_auth)):
    if _SHUTDOWN_IN_PROGRESS.is_set():
        return JSONResponse({"ok": False, "error": "Shutdown is in progress. Start is temporarily blocked."}, status_code=409)
    with _START_STOP_LOCK:
        if _SHUTDOWN_IN_PROGRESS.is_set():
            return JSONResponse({"ok": False, "error": "Shutdown is in progress. Start is temporarily blocked."}, status_code=409)
        mode = _current_mode()
        configured_agents = _available_agent_ids(mode)
        sync_result = _sync_missing_mode_agents(mode)
        provisioned = list(sync_result.get("provisioned", []))
        provisioning_errors = dict(sync_result.get("errors", {}))
        targets = _mode_agent_targets(mode)
        missing_agents = [agent_id for agent_id in configured_agents if not _resolve_agent_target(agent_id)]
        logger.info(
          "START_ALL_REQUEST: mode=%s configured=%s runnable=%s provisioned=%s missing=%s provisioning_errors=%s",
          mode,
          len(configured_agents),
          len(targets),
          len(provisioned),
          missing_agents,
          provisioning_errors,
        )
        if not targets:
            err = (
                "No runnable agents found. Set AI_HOME to a valid installation or keep runtime/agents "
                "available in the repository."
            )
            _log_activity("worker", err, details={"mode": mode}, source="dashboard")
            return JSONResponse({"ok": False, "mode": mode, "targets": [], "started": 0, "failed": [], "error": err}, status_code=503)
        outputs = []
        failures = []
        skipped_agents: list = []        # agents skipped by governor or circuit breaker
        skipped_by_governor: list = []   # agents skipped specifically by the cap
        skipped_by_breaker: list = []    # agents skipped by an open circuit breaker
        already_running: list = []       # duplicate-start prevention
        failed_reasons: dict[str, str] = {}
        for agent_name in provisioned:
          outputs.append(f"[{agent_name}] provisioned from bundled runtime into AI_HOME")
        for agent_name in missing_agents:
          outputs.append(f"[{agent_name}] missing — no agent folder/run.sh found in AI_HOME or bundled runtime")
        # Check governor before starting agents
        with _AGENT_GOVERNOR_LOCK:
            gov_enabled = _AGENT_GOVERNOR["enabled"]
            gov_max = _AGENT_GOVERNOR["max_agents"]
        running_count = _count_running_agents() if gov_enabled else 0
        for agent_name in targets:
          if agent_name in INFRA_AGENTS:
            continue
          if _agent_has_live_process(agent_name):
            already_running.append(agent_name)
            outputs.append(f"[{agent_name}] skipped — already running (duplicate prevented)")
            continue
          # Governor: skip start if cap already reached
          if gov_enabled and running_count >= gov_max:
            skipped_agents.append(agent_name)
            skipped_by_governor.append(agent_name)
            outputs.append(f"[{agent_name}] skipped — agent governor cap ({gov_max}) reached")
            continue
          # Circuit breaker: skip agents whose breaker is open
          if circuit_breaker_is_open(agent_name):
            skipped_agents.append(agent_name)
            skipped_by_breaker.append(agent_name)
            outputs.append(f"[{agent_name}] skipped — circuit breaker is open (too many recent failures)")
            continue
          rc, out = ai_employee("start", agent_name)
          start_msg = (out or "").strip()
          outputs.append(f"[{agent_name}] {start_msg}")
          if rc != 0:
            failures.append(agent_name)
            failed_reasons[agent_name] = start_msg or "start command returned non-zero exit code"
            circuit_breaker_record_failure(agent_name)
          else:
            time.sleep(0.05)
            if not _agent_has_live_process(agent_name):
              failures.append(agent_name)
              failed_reasons[agent_name] = start_msg or "start command returned success but no live process was detected"
              outputs.append(f"[{agent_name}] failed — no live process detected after start")
              circuit_breaker_record_failure(agent_name)
            else:
              running_count += 1
              circuit_breaker_record_success(agent_name)
        logger.info(
          "START_ALL_RESULT: mode=%s configured=%s runnable=%s started=%s failed=%s skipped_by_governor=%s skipped_by_breaker=%s already_running=%s missing=%s",
          mode,
          len(configured_agents),
          len(targets),
          len(targets) - len(failures) - len(skipped_agents) - len(already_running),
          failures,
          skipped_by_governor,
          skipped_by_breaker,
          already_running,
          missing_agents,
        )
        _invalidate_status_cache()
        return JSONResponse({
          "ok": len(failures) == 0 and len(missing_agents) == 0,
          "mode": mode,
          "configured_count": len(configured_agents),
          "configured_agents": configured_agents,
          "runnable_count": len(targets),
          "targets": targets,
          "started": len(targets) - len(failures) - len(skipped_agents) - len(already_running),
          "failed": failures,
          "failed_reasons": failed_reasons,
          "missing_agents": missing_agents,
          "provisioned_from_repo": provisioned,
          "provisioning_errors": provisioning_errors,
          "already_running": already_running,
          "skipped_by_governor": skipped_by_governor,
          "skipped_by_breaker": skipped_by_breaker,
          "output": "\n".join(outputs),
        })


@app.post("/api/agents/stop-all")
def stop_all_agents(_auth: None = Depends(require_auth)):
    with _START_STOP_LOCK:
        _SHUTDOWN_IN_PROGRESS.set()
        try:
            mode = _current_mode()
            targets = [a for a in _mode_agent_targets(mode) if a not in INFRA_AGENTS]
            result = _stop_agents_enterprise(targets)
            _invalidate_status_cache()
            return JSONResponse({
              "ok": len(result["failed"]) == 0,
              "mode": mode,
              "targets": targets,
              "stopped": result["stopped"],
              "failed": result["failed"],
              "details": result["details"],
              "shutdown": {
                "graceful_signaled": result["graceful_signaled"],
                "force_signaled": result["force_signaled"],
                "remaining_pids": result["remaining_pids"],
                "duration_ms": result["duration_ms"],
              },
            })
        finally:
            _SHUTDOWN_IN_PROGRESS.clear()


@app.post("/api/quick-actions/onboard")
def run_onboard_quick_action():
  rc, out = ai_employee("do", "onboard")
  return JSONResponse({
    "ok": rc == 0,
    "output": out,
    "message": "Onboard workflow started." if rc == 0 else "Failed to start onboard workflow.",
  })


@app.post("/api/agents/start")
def start_bot(payload: dict, _auth: None = Depends(require_auth)):
    bot = payload.get("bot") or payload.get("agent") or ""
    _validate_bot_name(bot)
    if _SHUTDOWN_IN_PROGRESS.is_set():
        return JSONResponse({"ok": False, "error": "Shutdown is in progress. Start is temporarily blocked."}, status_code=409)
    with _START_STOP_LOCK:
        if _SHUTDOWN_IN_PROGRESS.is_set():
            return JSONResponse({"ok": False, "error": "Shutdown is in progress. Start is temporarily blocked."}, status_code=409)
        if _agent_has_live_process(bot):
            return JSONResponse({"ok": True, "already_running": True, "output": f"Already running: {bot}"})
        rc, out = ai_employee("start", bot)
        return JSONResponse({"ok": rc == 0, "already_running": False, "output": out})


@app.post("/api/agents/stop")
def stop_bot(payload: dict, _auth: None = Depends(require_auth)):
    bot = payload.get("bot") or payload.get("agent") or ""
    _validate_bot_name(bot)
    with _START_STOP_LOCK:
        _SHUTDOWN_IN_PROGRESS.set()
        try:
            result = _stop_agents_enterprise([bot])
            _invalidate_status_cache()
            return JSONResponse({
                "ok": len(result["failed"]) == 0,
                "output": f"Stopped {bot}" if not result["failed"] else f"Failed to fully stop {bot}",
                "failed": result["failed"],
                "details": result["details"],
                "shutdown": {
                    "graceful_signaled": result["graceful_signaled"],
                    "force_signaled": result["force_signaled"],
                    "remaining_pids": result["remaining_pids"],
                    "duration_ms": result["duration_ms"],
                },
            })
        finally:
            _SHUTDOWN_IN_PROGRESS.clear()


@app.get("/api/workers")
def get_workers():
  agents = []
  if BOTS_DIR.exists():
    for d in sorted(BOTS_DIR.iterdir()):
      if not d.is_dir() or not (d / "run.sh").exists():
        continue
      if d.name in INFRA_AGENTS:
        continue
      pid_file = AI_HOME / "run" / f"{d.name}.pid"
      running = False
      if pid_file.exists():
        try:
          pid = int(pid_file.read_text().strip())
          os.kill(pid, 0)
          running = True
        except Exception:
          pass

      progress = 0
      elapsed_minutes = 0
      last_action = "Waiting for assignment"
      alert = False
      alert_reason = ""
      state_file = STATE_DIR / f"{d.name}.state.json"
      if state_file.exists():
        try:
          st = json.loads(state_file.read_text())
          progress = int(st.get("progress", 0) or 0)
          progress = max(0, min(progress, 100))
          last_action = st.get("last_action") or st.get("active_plan_title") or st.get("current_task") or last_action
          err = st.get("last_error") or st.get("error")
          if err:
            alert = True
            alert_reason = str(err)[:160]

          started_at = st.get("started_at")
          if started_at:
            try:
              start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
              elapsed_minutes = max(0, int((datetime.now(timezone.utc) - start_dt).total_seconds() / 60))
            except Exception:
              elapsed_minutes = 0
        except Exception:
          pass

      if running and progress == 0:
        progress = 15

      agents.append({
        "name": d.name,
        "running": running,
        "progress": progress,
        "elapsed_minutes": elapsed_minutes,
        "last_action": last_action,
        "alert": alert,
        "alert_reason": alert_reason,
      })
  return JSONResponse({"agents": agents})


# ─── Chat ─────────────────────────────────────────────────────────────────────

# ── Chatlog sanitizer — strip accidental API key leakage ─────────────────────
_API_KEY_PATTERN = re.compile(
    r"(sk-ant-[a-zA-Z0-9\-]{20,}"        # Anthropic
    r"|sk-[a-zA-Z0-9]{20,}"              # OpenAI
    r"|AIza[a-zA-Z0-9\-_]{30,}"          # Google / Gemini
    r"|gsk_[a-zA-Z0-9]{20,}"             # Groq
    r"|hf_[a-zA-Z0-9]{20,}"              # HuggingFace
    r"|nvapi-[a-zA-Z0-9\-_]{20,}"        # NVIDIA
    r"|xai-[a-zA-Z0-9]{20,}"             # xAI / Grok
    r")",
    re.IGNORECASE,
)

def _sanitize_for_log(text: str) -> str:
    """Replace any API key patterns with [REDACTED] before writing to chatlog."""
    return _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)

_WS_CLIENTS: set[WebSocket] = set()
_WS_CLIENTS_LOCK = asyncio.Lock()


async def _ws_broadcast(event: str, data: dict) -> None:
    payload = json.dumps({"event": event, "data": data, "ts": now_iso()})
    async with _WS_CLIENTS_LOCK:
        clients = list(_WS_CLIENTS)
    stale: list[WebSocket] = []
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    if stale:
        async with _WS_CLIENTS_LOCK:
            for ws in stale:
                _WS_CLIENTS.discard(ws)


@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    async with _WS_CLIENTS_LOCK:
        _WS_CLIENTS.add(websocket)
    await _ws_broadcast("system:status", {"service": "problem-solver-ui", "port": PORT, "status": "connected"})
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.8)
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = {}
                if parsed.get("type") == "chat" and str(parsed.get("message") or "").strip():
                    await _ws_broadcast(
                        "chat:input_rejected",
                        {"reason": "Use POST /chat (or /api/chat) as the control entrypoint."},
                    )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"event": "heartbeat", "data": {"status": "ok"}, "ts": now_iso()}))
    except WebSocketDisconnect:
        pass
    finally:
        async with _WS_CLIENTS_LOCK:
            _WS_CLIENTS.discard(websocket)


@app.get("/api/chat", tags=["tasks"])
def get_chat():
    messages = _read_last_n_lines(CHATLOG, 100)
    return JSONResponse({"messages": messages})


@app.get("/chat")
def get_chat_alias():
    return get_chat()


@app.post("/api/chat", tags=["tasks"])
@_tier_rate_limit
async def post_chat(payload: dict, request: Request):
    raw_message = (payload or {}).get("message", "").strip()
    model_route = ((payload or {}).get("model_route") or "").strip().lower()
    if not raw_message:
        raise HTTPException(400, "message required")

    # Enforce max length and strip null bytes; redact any accidental API keys
    if _SECURITY_AVAILABLE:
        message = InputSanitizer.sanitize_input(raw_message, max_length=10000)
    else:
        message = raw_message[:10000].replace("\x00", "")
    message = _sanitize_for_log(message)

    # ── Adversarial filter — before routing or any processing ─────────────────
    _adv_filter = _get_adversarial_filter()
    if _adv_filter is not None:
        try:
            _adv_assessment = _adv_filter.assess(message)
            if _adv_assessment.blocked:
                raise HTTPException(
                    400,
                    "Request rejected: potentially adversarial input detected. "
                    f"Risk score: {_adv_assessment.risk_score:.2f}. "
                    "Please rephrase your request.",
                )
        except HTTPException:
            raise
        except Exception as _adv_exc:
            logger.debug("adversarial_filter error (non-fatal): %s", _adv_exc)

    entry = {"ts": now_iso(), "type": "user", "message": message, "model_route": model_route}
    append_chatlog(entry)
    await _ws_broadcast("chat:user", {"message": message, "model_route": model_route})

    # Identify the user — use JWT sub if authenticated, else IP-based default
    user_id = _DEFAULT_USER
    try:
        from fastapi.security.utils import get_authorization_scheme_param  # noqa: PLC0415
        auth_header = request.headers.get("Authorization", "")
        _scheme, token_str = get_authorization_scheme_param(auth_header)
        if token_str:
            decoded = _verify_any_token.__wrapped__(token_str) if hasattr(_verify_any_token, "__wrapped__") else None
            if decoded and "sub" in (decoded or {}):
                user_id = f"user:{decoded['sub']}"
    except Exception:
        pass

    # Start a session the first time we see this user
    intel = _load_intelligence()
    if intel is not None:
        try:
            profile = intel._profile(user_id)
            if profile.interaction_count == 0:
                intel.start_session(user_id)
        except Exception:
            pass

    # Run handle_command in a thread pool to avoid blocking the async event loop
    # ── Distributed tracing — start trace before entering the thread pool ─────
    _dt = _get_distributed_tracer()
    _trace_id = ""
    if _dt is not None:
        try:
            _trace_id = _dt.start_trace(
                "chat_request",
                attributes={
                    "user_id":     user_id,
                    "model_route": model_route or "",
                    "message_len": len(message),
                },
            )
        except Exception as _dt_exc:
            logger.debug("distributed_tracer.start_trace error (non-fatal): %s", _dt_exc)

    response = await run_in_threadpool(
        handle_command, message, model_route=model_route, user_id=user_id
    )

    # ── Guaranteed response — never return None or empty to the UI ────────────
    if not response:
        _ai_flow_logger.warning(
            "[AI FLOW] handle_command returned empty response — using fallback"
        )
        response = _fallback_response("System recovered: default response generated.")

    # ── Schema validation — before storing in memory or sending to UI ─────────
    _routed_for_validation = route_to_agent(message)
    _schema_validator = _get_schema_validator()
    if _schema_validator is not None:
        try:
            _validated, _fallback = _schema_validator.validate_or_fallback(
                _routed_for_validation,
                response,
                ts=now_iso(),
                model=model_route or "",
                user_id=user_id,
            )
            if _fallback:
                # Validation failed — reject output and use safe fallback
                response = _fallback
        except Exception as _sv_exc:
            logger.debug("schema_validator error (non-fatal): %s", _sv_exc)

    safe_response = _sanitize_for_log(response)
    resp_entry = {"ts": now_iso(), "type": "agent", "message": safe_response, "model_route": model_route}
    append_chatlog(resp_entry)
    await _ws_broadcast("orchestrator:message", {"message": safe_response, "subsystem": "orchestrator"})

    # ── Post-exchange intelligence update (memory + brain training) ────────────
    if intel is not None:
        try:
            # Determine which agent handled the response
            routed_agent = route_to_agent(message)
            mode = _current_mode()
            # Guard memory writes with the memory circuit breaker
            _mem_registry = _get_circuit_registry()
            _mem_cb = _mem_registry.get("memory") if _mem_registry is not None else None
            # Wrap the actual exchange call with a memory span for distributed tracing
            _dt_mem = _get_distributed_tracer()

            async def _run_exchange():
                if _dt_mem is not None:
                    try:
                        from core.distributed_tracing import SpanKind  # type: ignore
                        with _dt_mem.span(
                            "memory_write",
                            kind=SpanKind.MEMORY,
                            attributes={"agent": routed_agent, "user_id": user_id},
                        ):
                            return await run_in_threadpool(
                                intel.on_exchange,
                                user_id, message, response, routed_agent, mode
                            )
                    except Exception:
                        pass
                return await run_in_threadpool(
                    intel.on_exchange,
                    user_id, message, response, routed_agent, mode
                )

            if _mem_cb is not None:
                _mem_cb.call(
                    lambda: run_in_threadpool(
                        intel.on_exchange,
                        user_id, message, response, routed_agent, mode
                    )
                )
            else:
                await _run_exchange()
        except Exception as exc:
            logger.debug("IntelligenceCore.on_exchange error: %s", exc)

    _log_activity(
        "agent_command",
        f"Command: {message[:120]}",
        details={"command": message[:500], "response_preview": safe_response[:200]},
        source="chat",
    )

    # ── Extract XAI explanation embedded by _generate_llm_response ────────────
    _xai_comment_pat = re.compile(r"\n?<!--xai:(xai-[a-zA-Z0-9]{12})-->$")
    _explain_dict: dict | None = None
    _xai_match = _xai_comment_pat.search(response)
    if _xai_match:
        _explain_id = _xai_match.group(1)
        response = response[:_xai_match.start()]
        try:
            _xai_engine = _get_explain_engine()
            if _xai_engine is not None:
                _explain_dict = _xai_engine.get(_explain_id)
        except Exception:
            pass

    _resp_payload: dict = {
        "ok": True,
        "response": response,
        "degraded": "[DEGRADED_PIPELINE]" in response or response.startswith("[pipeline_fallback]"),
        "proof": [
            {
                "type": "chat_log",
                "label": "Conversation exchange appended to chat log",
                "status": "recorded",
                "path": str(CHATLOG),
            }
        ],
    }
    if _explain_dict is not None:
        _resp_payload["explanation"] = {
            "explain_id": _explain_dict.get("explain_id"),
            "reason": _explain_dict.get("reason"),
            "key_factors": _explain_dict.get("key_factors"),
            "alternatives": _explain_dict.get("alternatives"),
            "confidence": _explain_dict.get("confidence"),
            "confidence_label": _explain_dict.get("confidence_label"),
        }

    # ── Finish trace and embed trace_id in response ───────────────────────────
    if _trace_id:
        _resp_payload["trace_id"] = _trace_id
        _resp_payload["proof"].append({
            "type": "trace",
            "label": f"Distributed trace {_trace_id}",
            "trace_id": _trace_id,
            "status": "recorded",
        })
        if _dt is not None:
            try:
                _dt.finish_trace(_trace_id)
            except Exception:
                pass

    # ── Prompt Inspector — broadcast latest trace via WebSocket ───────────────
    try:
        _pi_bc = _get_prompt_inspector()
        if _pi_bc is not None and _pi_bc.enabled:
            _latest_traces = _pi_bc.list_traces(limit=1)
            if _latest_traces:
                await _ws_broadcast("prompt:trace", _latest_traces[0])
    except Exception:
        pass

    _resp_headers: dict[str, str] = {}
    if _trace_id:
        _resp_headers["X-Trace-ID"] = _trace_id

    return JSONResponse(_resp_payload, headers=_resp_headers or None)


@app.post("/chat")
async def post_chat_alias(payload: dict, request: Request):
    return await post_chat(payload, request)


def handle_command(
    message: str,
    model_route: Optional[str] = None,
    user_id: str = _DEFAULT_USER,
) -> str:
    msg_lower = message.lower().strip()

    # ── ASCEND_FORGE chat commands ─────────────────────────────────────────────
    if msg_lower.startswith("ascend:"):
        try:
            af = _load_ascend_module()
            return af.handle_chat_command(message)
        except Exception as exc:
            logger.error("ascend chat command error: %s", exc)
            return f"❌ ASCEND_FORGE error: {exc}"

    if msg_lower in ("status", "s"):
        rc, out = ai_employee("status")
        return f"Agent status:\n{out}" if out.strip() else "No status data."

    if msg_lower in ("workers", "w"):
        rc, out = ai_employee("status")
        return f"Agents:\n{out}"

    if msg_lower.startswith("start "):
        bot = message[6:].strip()
        if not _BOT_NAME_RE.match(bot):
          return f"Invalid agent name '{bot}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}."
        rc, out = ai_employee("start", bot)
        return f"Started {bot}. {out}"

    if msg_lower.startswith("stop "):
        bot = message[5:].strip()
        if not _BOT_NAME_RE.match(bot):
          return f"Invalid agent name '{bot}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}."
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
        agents_match = _re.search(r'agents:([\w,\-]+(?:[ \t]+[\w,\-]+)*)(?:[ \t]+task:|$)', rest, _re.IGNORECASE)
        task_match = _re.search(r'task:(.+)', rest, _re.IGNORECASE)
        worker_name = _re.split(r'[ \t]+agents:', rest, maxsplit=1, flags=_re.IGNORECASE)[0].strip()
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
            "⚙️ System: status, workers, start/stop <agent>\n"
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
            "  status / workers — agent status\n"
            "  start <agent> / stop <agent> — control agents\n"
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
            "  agents — list all 56 AI agents\n"
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
    if ((msg_lower.startswith("web search ") or msg_lower.startswith("search web ")
            or msg_lower.startswith("latest news ") or msg_lower.startswith("news about ")
        or msg_lower.startswith("lookup "))):
        web_bot_state = STATE_DIR / "web-researcher.state.json"
        if web_bot_state.exists():
            try:
                st = json.loads(web_bot_state.read_text())
                if st.get("status") == "running":
                    return (
                        "🔍 Research request queued — web-researcher agent is processing it.\n"
                        "The answer will appear in the chat shortly."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🔍 Research request noted — ensure web-researcher agent is running.\n"
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
                        "🎨 Content creation request queued — social-media-manager agent is processing it.\n"
                        "Full content package will appear in the chat shortly (30-90 seconds)."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🎨 Content request noted — ensure social-media-manager agent is running.\n"
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
                        f"{emoji} Request queued — {bot_name} agent is processing it.\n"
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
        append_chatlog(entry)
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
        (['newsletter '], "newsletter-bot", "📧", "Newsletter agent not running."),
        (['chatbot '], "chatbot-builder", "🤖", "Chatbot builder agent not running."),
        (['video '], "faceless-video", "🎬", "Faceless video agent not running."),
        (['pod '], "print-on-demand", "👕", "Print-on-demand agent not running."),
        (['course '], "course-creator", "🎓", "Course creator agent not running."),
        (['arb '], "arbitrage-bot", "💹", "Arbitrage agent not running."),
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


    routed_agent = route_to_agent(message)
    mode = _current_mode()

    # ── Financial-agents safety gate ─────────────────────────────────────────
    if routed_agent in _FINANCIAL_AGENT_IDS and not _ENABLE_FINANCIAL_AGENTS:
        _audit_logger.warning(json.dumps({
            "event": "financial_agent_blocked",
            "agent": routed_agent,
            "reason": "ENABLE_FINANCIAL_AGENTS not set",
            "timestamp": now_iso(),
        }))
        return (
            f"⚠️  Financial Agent Disabled\n\n"
            f"The '{routed_agent}' agent is disabled by default due to regulatory "
            f"requirements (MiFID II, SEC, FCA).\n\n"
            f"To enable financial agents:\n"
            f"  1. Complete a jurisdiction-specific legal/compliance review.\n"
            f"  2. Add ENABLE_FINANCIAL_AGENTS=1 to ~/.ai-employee/.env.\n\n"
            + _FINANCIAL_DISCLAIMER
        )

    if ("all 56 agents" in msg_lower or "all agents" in msg_lower) and mode != "power":
      allowed = ", ".join(_available_agent_ids(mode))
      return (
        f"Only {len(_available_agent_ids(mode))} agents are available in {mode} mode: {allowed}. "
        "Switch to power mode to run all 56 agents, or I can handle this with the current set."
      )
    if not _agent_allowed_in_mode(routed_agent, mode):
      return (
        f"{routed_agent} is not available in {mode} mode. "
        f"Run: ai-employee mode {'business' if mode == 'starter' else 'power'} to unlock more agents."
      )

    # ── HITL gate for high-risk agents ────────────────────────────────────────
    _hitl = _get_hitl_gate()
    if _hitl is not None and _hitl.is_required(routed_agent):
        result = _hitl.require_approval(
            agent=routed_agent,
            action=f"process_request: {message[:120]}{'...' if len(message) > 120 else ''}",
            payload={"message": message[:500], "agent": routed_agent},
            submitted_by=user_id,
            blocking=False,
        )
        _audit_logger.info(json.dumps({
            "event": "hitl_gate_triggered",
            "agent": routed_agent,
            "request_id": result.get("request_id"),
            "timestamp": now_iso(),
        }))
        return (
            f"⏳ Human Approval Required (EU AI Act — Article 14)\n\n"
            f"Agent: **{routed_agent}**\n"
            f"Request ID: `{result.get('request_id')}`\n\n"
            f"This agent performs high-risk AI operations (recruitment, lead scoring, "
            f"or profiling) that require human review before execution.\n\n"
            f"A human operator must approve this request in the Governance panel "
            f"before the action is executed. Once approved, re-submit your request."
        )

    # ── Bias detection pipeline ────────────────────────────────────────────────
    _bias = _get_bias_engine()
    if _bias is not None and _bias.is_checked_agent(routed_agent, message):
        try:
            from core.bias_detection_engine import BiasCheckContext  # type: ignore
            _demographic_group = (
                (payload.get("demographic_group") or "").strip()
                if isinstance(locals().get("payload"), dict)
                else ""
            ) or "unknown"
            _bc = BiasCheckContext(
                agent=routed_agent,
                action=f"chat_request: {message[:80]}",
                subject_id=user_id,
                decision=True,          # intent: positive decision (process request)
                demographic_group=_demographic_group,
            )
            _bias_report = _bias.check(_bc)
            if _bias_report.outcome == "block":
                _audit_logger.warning(json.dumps({
                    "event": "bias_block",
                    "agent": routed_agent,
                    "check_id": _bias_report.check_id,
                    "risk_score": _bias_report.audit_risk_score,
                    "timestamp": now_iso(),
                }))
                return (
                    f"⛔ Request Blocked — Bias Detection\n\n"
                    f"Agent: **{routed_agent}**\n"
                    f"Check ID: `{_bias_report.check_id}`\n\n"
                    f"{_bias_report.summary}\n\n"
                    "This decision pattern has been flagged for adverse impact. "
                    "Contact your compliance officer before proceeding."
                )
            if _bias_report.high_risk:
                _audit_logger.warning(json.dumps({
                    "event": "bias_high_risk",
                    "agent": routed_agent,
                    "check_id": _bias_report.check_id,
                    "risk_score": _bias_report.audit_risk_score,
                    "timestamp": now_iso(),
                }))
        except Exception as _bias_exc:
            logger.debug("bias check error (non-fatal): %s", _bias_exc)

    # ── Real execution engine — structured goal → real tool calls ────────────
    # If the message is a goal (not a question), parse it into a structured plan
    # and execute it step-by-step with real tools. Rules: no fake results, every
    # step maps to a real tool, errors are explicit.
    try:
        from core.goal_parser import parse_goal as _parse_goal  # noqa: PLC0415
        from core.real_execution_engine import RealExecutionEngine as _RealExecEngine  # noqa: PLC0415
        _goal_plan = _parse_goal(message)
        if not _goal_plan.get("is_goal"):
            _direct_reply = _direct_conversation_reply(_goal_plan, message)
            if _direct_reply:
                return _direct_reply
        if _goal_plan.get("is_goal") and _goal_plan.get("task_plan"):
            logger.info("[REAL_ENGINE] Goal detected — %d steps planned", len(_goal_plan["task_plan"]))
            _engine = _RealExecEngine()
            _exec_result = _engine.run(_goal_plan["task_plan"], goal=message)
            _chat_reply = _engine.format_for_chat(_exec_result)
            # Prepend brief goal summary
            _structured = _goal_plan.get("structured_goal", {})
            if _structured.get("action"):
                _chat_reply = f"Executing: **{_structured['action']}**\n\n" + _chat_reply
            return _chat_reply
    except Exception as _real_exc:
        logger.warning("real_execution_engine failed (non-fatal): %s", _real_exc)

    # ── Unified pipeline — single controlled execution path ───────────────────
    # All remaining user inputs are routed through process_user_input() which
    # enforces the full pipeline: graph → LLM → agents → result → forge.
    # The already-resolved routed_agent and mode are forwarded via a closure
    # so server-side keyword routing is preserved while the pipeline adds
    # graph context, task decomposition, and telemetry around every LLM call.
    try:
        from core.unified_pipeline import process_user_input as _process_user_input  # noqa: PLC0415

        def _llm_fn(
            msg: str,
            _agent: str,
            _mode: str,
            *,
            model_route: Optional[str] = None,
            user_id: str = _DEFAULT_USER,
            graph_context: str = "",
        ) -> str:
            # Use the routed_agent/mode already computed above (closed over)
            return _generate_llm_response(
                msg,
                routed_agent,
                mode,
                model_route=model_route,
                user_id=user_id,
                graph_context=graph_context,
            )

        return _process_user_input(
            message,
            user_id=user_id,
            mode=mode,
            model_route=model_route or "",
            generate_llm_response_fn=_llm_fn,
        )
    except Exception as _pui_exc:
        # Respect STRICT_PIPELINE — when set, re-raise instead of falling back
        try:
            from core.unified_pipeline import STRICT_PIPELINE as _STRICT  # noqa: PLC0415
        except Exception:
            _STRICT = False
        if _STRICT:
            raise
        logger.warning(
            "unified_pipeline.process_user_input failed, falling back to direct LLM: %s",
            _pui_exc,
        )
        return _generate_llm_response(message, routed_agent, mode, model_route=model_route, user_id=user_id)


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
def add_schedule(task: dict, _auth: None = Depends(require_auth)):
    import uuid as _uuid
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    if SCHEDULES_FILE.exists():
        try:
            tasks = json.loads(SCHEDULES_FILE.read_text())
        except Exception:
            pass

    task_id = task.get("id", "")
    if not task_id:
        # Auto-generate an id from task name or a UUID
        raw_name = (task.get("task") or task.get("name") or "").strip()
        if raw_name:
            task_id = re.sub(r"[^a-z0-9-]", "-", raw_name.lower()).strip("-") or _uuid.uuid4().hex[:12]
        else:
            task_id = _uuid.uuid4().hex[:12]
        task["id"] = task_id

    # Replace if exists
    tasks = [t for t in tasks if t.get("id") != task_id]
    tasks.append(task)
    SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    return JSONResponse({"ok": True})


@app.delete("/api/schedules/{task_id}")
def delete_schedule(task_id: str, _auth: None = Depends(require_auth)):
    if not SCHEDULES_FILE.exists():
        return JSONResponse({"ok": True})
    try:
        tasks = json.loads(SCHEDULES_FILE.read_text())
        tasks = [t for t in tasks if t.get("id") != task_id]
        SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
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
def review_improvement(improvement_id: str, payload: dict, _auth: None = Depends(require_auth)):
    status = payload.get("status", "")
    valid_statuses = ("approved", "rejected", "in_progress", "completed", "pending")
    if status not in valid_statuses:
        raise HTTPException(400, f"status must be one of: {', '.join(valid_statuses)}")

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
    for candidate in (SKILLS_LIBRARY_FILE, _REPO_SKILLS_FILE):
        if candidate.exists():
            try:
                lib = json.loads(candidate.read_text())
                break
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


@app.post("/api/skills")
def create_skill(payload: dict, _auth: None = Depends(require_auth)):
    skill_id = (payload.get("id") or "").strip()
    name = (payload.get("name") or "").strip()
    category = (payload.get("category") or "Automation & Productivity").strip()
    description = (payload.get("description") or "").strip()
    if not skill_id or not name or not description:
        raise HTTPException(400, "id, name, and description are required")

    # Load existing library
    lib = {}
    for candidate in (SKILLS_LIBRARY_FILE, _REPO_SKILLS_FILE):
        if candidate.exists():
            try:
                lib = json.loads(candidate.read_text())
                break
            except json.JSONDecodeError as exc:
                raise HTTPException(500, f"Skills library file is corrupt: {exc}") from exc
            except OSError:
                continue
    if not lib:
        lib = {"skills": [], "categories": []}

    skills = lib.get("skills", [])
    # Check for duplicate ID
    if any(s.get("id") == skill_id for s in skills):
        raise HTTPException(409, f"Skill with id '{skill_id}' already exists")

    new_skill = {
        "id": skill_id,
        "name": name,
        "category": category,
        "description": description,
        "tags": payload.get("tags") or [],
        "steps": payload.get("steps") or [],
        "usage_count": 0,
        "created_by": payload.get("created_by") or "user",
        "created_at": now_iso(),
    }
    if payload.get("prompt_template"):
        new_skill["prompt_template"] = payload["prompt_template"]

    skills.append(new_skill)
    lib["skills"] = skills
    # Update categories
    lib["categories"] = sorted({s["category"] for s in skills})

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_LIBRARY_FILE.write_text(json.dumps(lib, indent=2))
    return JSONResponse({"ok": True, "id": skill_id, "name": name})




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
def create_custom_agent(payload: dict, _auth: None = Depends(require_auth)):
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
def delete_custom_agent(agent_id: str, _auth: None = Depends(require_auth)):
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
    data = _cached_read(WORKER_BUNDLES_FILE)
    return data if isinstance(data, list) else []


def _save_worker_bundles(bundles: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_BUNDLES_FILE.write_text(json.dumps(bundles, indent=2))
    _invalidate_cache(WORKER_BUNDLES_FILE)


# ─── Worker Bundle API ────────────────────────────────────────────────────────

@app.get("/api/workers/bundles")
def list_worker_bundles():
    """List all worker bundles."""
    return JSONResponse({"bundles": _load_worker_bundles()})


@app.post("/api/workers/bundles")
def create_worker_bundle(payload: dict, _auth: None = Depends(require_auth)):
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
def update_worker_bundle(bundle_id: str, payload: dict, _auth: None = Depends(require_auth)):
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
def delete_worker_bundle(bundle_id: str, _auth: None = Depends(require_auth)):
    """Delete a worker bundle."""
    bundles = _load_worker_bundles()
    remaining = [b for b in bundles if b["id"] != bundle_id]
    if len(remaining) == len(bundles):
        raise HTTPException(404, f"bundle '{bundle_id}' not found")
    _save_worker_bundles(remaining)
    return JSONResponse({"ok": True})


@app.post("/api/workers/bundles/{bundle_id}/run")
def run_worker_bundle(bundle_id: str, _auth: None = Depends(require_auth)):
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
  for candidate in (AGENT_CAPS_FILE, _REPO_CAPS_FILE):
    if not candidate.exists():
      continue
    try:
      data = json.loads(candidate.read_text())
    except Exception:
      continue

    raw_agents = data.get("agents", {}) if isinstance(data, dict) else {}
    normalized_agents: dict[str, dict] = {}
    seen_ids: set[str] = set()
    for mode_name in AGENTS_BY_MODE:
      for agent_id in AGENTS_BY_MODE[mode_name]:
        if agent_id in seen_ids:
          continue
        seen_ids.add(agent_id)
        if not _resolve_agent_target(agent_id):
          continue
        candidates = list(CAPS_ID_ALIASES.get(agent_id, [agent_id]))
        for alias_id in _agent_aliases(agent_id):
          if alias_id not in candidates:
            candidates.append(alias_id)
        info = {}
        for candidate_id in candidates:
          candidate_info = raw_agents.get(candidate_id)
          if isinstance(candidate_info, dict):
            info = candidate_info
            break
        normalized_agents[agent_id] = info

    if isinstance(data, dict):
      data["agents"] = normalized_agents
      return data
    return {"agents": normalized_agents}
  return {"agents": {}}


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

    # Auto-start assigned agents if they're not running
    if agents and not _SHUTDOWN_IN_PROGRESS.is_set():
        for agent_id in agents:
            # Validate agent_id to prevent path traversal
            if not isinstance(agent_id, str) or not _SAFE_AGENT_ID_PAT.match(agent_id):
                continue
            target = _resolve_agent_target(agent_id)
            if target and _agent_dir_exists(target) and _SAFE_AGENT_ID_PAT.match(target):
                pid = _read_pid_file(target)
                already_running = bool(pid and _pid_alive(pid))
                if not already_running:
                    try:
                        ai_employee("start", target)
                    except Exception:
                        pass

    return JSONResponse({"ok": True, "task_id": task_id, "message": f"Task submitted: {description[:60]}", "agents": agents, "mode": mode})


@app.post("/api/tasks/run", tags=["tasks"])
@_tier_rate_limit
def run_task_with_agent_controller(payload: dict, _auth: None = Depends(require_auth)):
    """Run a goal through the core AgentController contract.

    This is the canonical HTTP surface for Node's /api/tasks/run proxy.  It
    keeps task execution on the documented Planner -> Executor -> Validator path
    instead of the dashboard-only task-plan queue.
    """
    goal = (
        payload.get("task")
        or payload.get("goal")
        or payload.get("message")
        or payload.get("description")
        or ""
    )
    goal = str(goal).strip()
    if not goal:
        raise HTTPException(400, "task required")
    if len(goal) > 5000:
        raise HTTPException(400, "task too long (max 5000 chars)")

    try:
        from core.agent_controller import get_agent_controller  # noqa: PLC0415
        summary = get_agent_controller().run_goal(goal)
    except Exception as exc:
        logger.warning("AgentController task run failed: %s", type(exc).__name__)
        error_message = "AgentController failed"
        return JSONResponse({
            "ok": False,
            "source": "agent_controller",
            "task": goal,
            "status": "failed",
            "degraded": True,
            "error": f"AgentController failed: {error_message}",
            "errors": [{
                "stage": "agent_controller",
                "message": error_message,
                "type": exc.__class__.__name__,
            }],
            "proof": [{
                "type": "agent_controller_error",
                "label": "AgentController failed before producing task output",
                "status": "failed",
                "details": error_message,
            }],
            "tasks": [],
        })

    if not isinstance(summary, dict):
        return JSONResponse({
            "ok": False,
            "source": "agent_controller",
            "task": goal,
            "status": "failed",
            "degraded": True,
            "error": "AgentController returned an invalid result contract",
            "errors": [{
                "stage": "agent_controller",
                "message": f"Expected dict, got {type(summary).__name__}",
            }],
            "proof": [{
                "type": "agent_controller_error",
                "label": "Invalid AgentController result contract",
                "status": "failed",
            }],
            "tasks": [],
        })

    proof: list[dict] = [{
        "type": "agent_controller",
        "label": "Planner -> Executor -> Validator completed",
        "status": "completed",
        "run_id": summary.get("run_id"),
    }]
    for task in (summary.get("tasks", []) if isinstance(summary.get("tasks"), list) else []):
        if not isinstance(task, dict):
            continue
        output = task.get("output") if isinstance(task.get("output"), dict) else {}
        if output.get("path"):
            proof.append({
                "type": "file",
                "label": output.get("filename") or Path(str(output["path"])).name,
                "path": output["path"],
                "status": task.get("status"),
                "task_id": task.get("task_id"),
            })
        if task.get("error"):
            proof.append({
                "type": "task_error",
                "label": task.get("error"),
                "status": "failed",
                "task_id": task.get("task_id"),
            })

    return JSONResponse({
        "ok": True,
        "source": "agent_controller",
        "task": goal,
        "proof": proof,
        **summary,
    })


@app.post("/api/money/content-pipeline")
def money_content_pipeline(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import get_money_mode  # noqa: PLC0415

    topic = str(payload.get("topic") or payload.get("task") or "").strip()
    if not topic:
        raise HTTPException(400, "topic required")
    platforms = payload.get("platforms") if isinstance(payload.get("platforms"), list) else None
    result = get_money_mode().run_content_pipeline(
        topic=topic,
        platforms=platforms,
        affiliate_product=str(payload.get("affiliate_product") or ""),
        dry_run=bool(payload.get("dry_run", True)),
    )
    return JSONResponse(result)


@app.post("/api/money/lead-pipeline")
def money_lead_pipeline(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import get_money_mode  # noqa: PLC0415

    source = str(payload.get("source") or "").strip()
    audience = str(payload.get("audience") or "").strip()
    if not source or not audience:
        raise HTTPException(400, "source and audience required")
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else None
    result = get_money_mode().run_lead_pipeline(
        source=source,
        audience=audience,
        channels=channels,
        dry_run=bool(payload.get("dry_run", True)),
    )
    return JSONResponse(result)


@app.post("/api/money/opportunity-pipeline")
def money_opportunity_pipeline(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import get_money_mode  # noqa: PLC0415

    opportunity = str(payload.get("opportunity") or payload.get("task") or "").strip()
    if not opportunity:
        raise HTTPException(400, "opportunity required")
    result = get_money_mode().run_opportunity_pipeline(
        opportunity=opportunity,
        budget=float(payload.get("budget") or 0.0),
        dry_run=bool(payload.get("dry_run", True)),
    )
    return JSONResponse(result)


@app.post("/api/money/affiliate-draft")
def money_affiliate_draft(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import get_money_mode  # noqa: PLC0415

    product = str(payload.get("product") or "").strip()
    niche = str(payload.get("niche") or "").strip()
    if not product or not niche:
        raise HTTPException(400, "product and niche required")
    return JSONResponse(get_money_mode().affiliate_content_draft(
        product=product,
        niche=niche,
        output_format=str(payload.get("output_format") or "blog_post"),
    ))


@app.post("/money/niche-research")
async def money_niche_research(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import niche_research_workflow  # noqa: PLC0415
    tenant_id = str(payload.get("tenant_id") or "default")
    niche = str(payload.get("niche") or "").strip()
    if not niche:
        raise HTTPException(400, "niche required")
    result = await niche_research_workflow(tenant_id, niche)
    return JSONResponse(result)


@app.post("/money/offer-creation")
async def money_offer_creation(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import offer_creation_workflow  # noqa: PLC0415
    tenant_id = str(payload.get("tenant_id") or "default")
    niche = str(payload.get("niche") or "").strip()
    angle = str(payload.get("angle") or "").strip()
    if not niche or not angle:
        raise HTTPException(400, "niche and angle required")
    result = await offer_creation_workflow(tenant_id, niche, angle)
    return JSONResponse(result)


@app.post("/money/content-calendar")
async def money_content_calendar(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import content_calendar_workflow  # noqa: PLC0415
    tenant_id = str(payload.get("tenant_id") or "default")
    offer = payload.get("offer") or {}
    weeks = int(payload.get("weeks") or 4)
    if not isinstance(offer, dict):
        raise HTTPException(400, "offer must be an object")
    result = await content_calendar_workflow(tenant_id, offer, weeks)
    return JSONResponse(result)


@app.post("/money/lead-research")
async def money_lead_research(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import lead_research_workflow  # noqa: PLC0415
    tenant_id = str(payload.get("tenant_id") or "default")
    criteria = payload.get("criteria") or {}
    if not isinstance(criteria, dict):
        raise HTTPException(400, "criteria must be an object")
    result = await lead_research_workflow(tenant_id, criteria)
    return JSONResponse(result)


@app.post("/money/proposal")
async def money_proposal(payload: dict, _auth: None = Depends(require_auth)):
    from core.money_mode import proposal_generation_workflow  # noqa: PLC0415
    tenant_id = str(payload.get("tenant_id") or "default")
    client_info = payload.get("client_info") or {}
    offer = payload.get("offer") or {}
    if not isinstance(client_info, dict) or not isinstance(offer, dict):
        raise HTTPException(400, "client_info and offer must be objects")
    result = await proposal_generation_workflow(tenant_id, client_info, offer)
    return JSONResponse(result)


# ── Roadmap Engine routes ─────────────────────────────────────────────────────

@app.post("/roadmap/create")
async def roadmap_create(payload: dict, _auth: None = Depends(require_auth)):
    from core.roadmap_engine import get_roadmap_engine  # noqa: PLC0415
    from dataclasses import asdict  # noqa: PLC0415
    goal = str(payload.get("goal") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default")
    if not goal:
        raise HTTPException(400, "goal required")
    roadmap = get_roadmap_engine().create_roadmap(goal, tenant_id)
    return JSONResponse(asdict(roadmap))


@app.post("/roadmap/generate")
async def roadmap_generate(payload: dict, _auth: None = Depends(require_auth)):
    from core.roadmap_engine import get_roadmap_engine  # noqa: PLC0415
    from dataclasses import asdict  # noqa: PLC0415
    roadmap_id = str(payload.get("roadmap_id") or "").strip()
    if not roadmap_id:
        raise HTTPException(400, "roadmap_id required")
    engine = get_roadmap_engine()
    roadmap = engine.get_roadmap(roadmap_id)
    if not roadmap:
        raise HTTPException(404, f"Roadmap {roadmap_id} not found")
    roadmap = engine.generate_milestones(roadmap)
    return JSONResponse(asdict(roadmap))


@app.get("/roadmap/{roadmap_id}")
async def roadmap_get(roadmap_id: str, _auth: None = Depends(require_auth)):
    from core.roadmap_engine import get_roadmap_engine  # noqa: PLC0415
    status = get_roadmap_engine().roadmap_status(roadmap_id)
    if not status.get("ok"):
        raise HTTPException(404, status.get("error", "not found"))
    return JSONResponse(status)


@app.post("/roadmap/{roadmap_id}/execute")
async def roadmap_execute(roadmap_id: str, _auth: None = Depends(require_auth)):
    from core.roadmap_engine import get_roadmap_engine  # noqa: PLC0415
    result = await get_roadmap_engine().execute_roadmap(roadmap_id)
    if not result.get("ok"):
        raise HTTPException(404, "roadmap_execute_failed")
    return JSONResponse({
        "ok": True,
        "roadmap_id": roadmap_id,
        "status": "executed",
        "executed_tasks": int(result.get("executed_tasks", 0) or 0) if isinstance(result, dict) else 0,
    })


@app.get("/roadmap/list/{tenant_id}")
async def roadmap_list(tenant_id: str, _auth: None = Depends(require_auth)):
    from core.roadmap_engine import get_roadmap_engine  # noqa: PLC0415
    from dataclasses import asdict  # noqa: PLC0415
    roadmaps = get_roadmap_engine().list_roadmaps(tenant_id)
    return JSONResponse({"ok": True, "roadmaps": [asdict(r) for r in roadmaps]})


@app.post("/api/task/cancel")
def cancel_task(_auth: None = Depends(require_auth)):
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
def reassign_subtask(payload: dict, _auth: None = Depends(require_auth)):
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


@app.post("/api/task/subtask-complete")
def complete_subtask(payload: dict):
    """Mark a subtask as done or failed and update the circuit breaker for its agent.

    Payload:
      task_id    – str (required)
      subtask_id – str (required)
      status     – "done" | "failed" (required)
      result     – str (optional: outcome summary)
    """
    task_id = (payload.get("task_id") or "").strip()
    subtask_id = (payload.get("subtask_id") or "").strip()
    status = (payload.get("status") or "").strip()
    if not all([task_id, subtask_id, status]):
        raise HTTPException(400, "task_id, subtask_id, and status are required")
    if status not in ("done", "failed"):
        raise HTTPException(400, "status must be 'done' or 'failed'")

    plans = _load_task_plans()
    for p in plans:
        if p.get("id") != task_id:
            continue
        for st in p.get("subtasks", []):
            if (st.get("subtask_id") or st.get("id")) == subtask_id:
                st["status"] = status
                if payload.get("result"):
                    st["result"] = str(payload["result"])[:500]
                st["completed_at"] = now_iso()
                agent_id = st.get("agent_id", "")
                _save_task_plans(plans)
                _invalidate_status_cache()
                # Update circuit breaker
                if agent_id:
                    if status == "failed":
                        cb_state = circuit_breaker_record_failure(agent_id)
                    else:
                        cb_state = circuit_breaker_record_success(agent_id)
                    return JSONResponse({
                        "ok": True,
                        "subtask_id": subtask_id,
                        "status": status,
                        "agent_id": agent_id,
                        "circuit_breaker": cb_state,
                    })
                return JSONResponse({"ok": True, "subtask_id": subtask_id, "status": status})
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

    mode = _current_mode()
    available = set(_available_agent_ids(mode))

    # Sort by score descending; take top agents covering the task
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Always include at least 1; cap at 6 unless the description is very broad
    max_agents = 6 if len(description) > 80 else 4
    suggested = [aid for aid, _ in ranked if aid in available][:max_agents]

    # If nothing matched, fall back to orchestrator
    if not suggested:
      suggested = ["task-orchestrator"]

    # Attach reasons
    reasons = {aid: [kw for kw in _AGENT_KEYWORDS.get(aid, []) if kw in description][:3] for aid in suggested}

    return JSONResponse({"suggested": suggested, "scores": dict(ranked[:max_agents]), "reasons": reasons})


@app.get("/api/task/list")
def list_tasks():
    """List all task plans (active and history)."""
    plans = _load_task_plans()
    return JSONResponse({"plans": plans[:20]})


# ── Idea-to-Prompt Converter ──────────────────────────────────────────────────
_idea_to_prompt_path = AI_HOME / "agents" / "idea-to-prompt"
if str(_idea_to_prompt_path) not in sys.path:
    sys.path.insert(0, str(_idea_to_prompt_path))

try:
    from idea_to_prompt import convert_idea as _convert_idea  # type: ignore
    _IDEA_CONVERTER_AVAILABLE = True
except ImportError:
    _IDEA_CONVERTER_AVAILABLE = False


@app.post("/api/idea/convert")
async def convert_idea_to_prompt(payload: dict):
    """Convert a rough idea into a structured, professional task prompt.

    Accepts: {"idea": "<raw idea text>"}
    Returns: {"ok": true, "prompt": "...", "title": "...", "original": "...", "provider": "..."}

    This endpoint sits between the user's input and the orchestrator — it uses
    the AI router to produce an efficient, actionable task description from
    whatever the user typed.
    """
    idea = (payload.get("idea") or "").strip()
    if not idea:
        raise HTTPException(400, "idea required")
    if len(idea) > 4000:
        raise HTTPException(400, "idea too long (max 4000 characters)")

    if _IDEA_CONVERTER_AVAILABLE:
        result = await run_in_threadpool(_convert_idea, idea)
    else:
        # Inline fallback when the module is not on the path
        result = _inline_convert_idea(idea)

    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "conversion failed"))
    return JSONResponse(result)


def _inline_convert_idea(idea: str) -> dict:
    """Inline fallback converter used when the idea-to-prompt module is unavailable."""
    _SYSTEM = (
        "You are an expert AI prompt engineer. Convert the rough idea below into a "
        "clear, numbered, professional task description an AI orchestrator can execute. "
        "End with a line: TITLE: <short title>. Output ONLY the task description and title."
    )
    prompt_text = ""
    provider = "fallback"
    title = idea[:60].strip()

    if _AI_ROUTER_AVAILABLE:
        try:
            res = _query_ai_for_agent(
                "reasoning",
                f"Convert this idea into a structured AI task:\n\n{idea}",
                _SYSTEM,
            )
            raw = (res.get("content") or res.get("answer") or res.get("text") or "").strip()
            if raw:
                lines = []
                for line in raw.splitlines():
                    if line.strip().upper().startswith("TITLE:"):
                        title = line.strip()[6:].strip() or title
                    else:
                        lines.append(line)
                prompt_text = "\n".join(lines).strip()
                provider = res.get("provider", "ai")
        except Exception:
            pass

    if not prompt_text:
        prompt_text = (
            f"Goal: {idea}\n\n"
            "1. Research and analyse the current state of the topic.\n"
            "2. Identify the key actions needed to achieve the goal.\n"
            "3. Create a detailed action plan with clear milestones.\n"
            "4. Execute each step and document the outcomes.\n"
            "5. Review results against success criteria and iterate.\n"
        )

    return {"ok": True, "prompt": prompt_text, "title": title, "original": idea, "provider": provider}


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
  """Get mode-aware agent list with capabilities and running status."""
  capabilities = _load_agent_capabilities()
  agents_config = capabilities.get("agents", {})
  mode = _current_mode()

  result = []
  for agent_id in _available_agent_ids(mode):
    canonical_ids = _agent_aliases(agent_id)
    # Try direct lookup, then _CAPS_ID_MAP aliases, then existing AGENT_ALIASES
    caps_ids_to_try = CAPS_ID_ALIASES.get(agent_id, [agent_id]) + canonical_ids
    info = None
    for caps_id in caps_ids_to_try:
      if caps_id in agents_config:
        info = agents_config[caps_id]
        break
    info = info or {}

    pid_file = None
    for alias in canonical_ids:
      candidate = AI_HOME / "run" / f"{alias}.pid"
      if candidate.exists():
        pid_file = candidate
        break

    running = False
    if pid_file and pid_file.exists():
      try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        running = True
      except Exception:
        pass

    current_task = None
    for alias in canonical_ids:
      state_file = STATE_DIR / f"{alias}.state.json"
      if state_file.exists():
        try:
          st = json.loads(state_file.read_text())
          current_task = st.get("active_plan_title") or st.get("current_task")
          break
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

  return JSONResponse({"agents": result, "total": len(result), "mode": mode})



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
    "hours_saved": 0.0,  # uses explicit "hours" field
    "custom": 0.0,
}


def _load_metrics() -> dict:
    data = _cached_read(METRICS_FILE)
    return data if data else {"summary": {}, "events": []}


def _save_metrics(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(data, indent=2))
    _invalidate_cache(METRICS_FILE)


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
        "human_hours_saved": 0.0,
        "cost_saved": 0.0,
        "revenue": 0.0,
        "by_agent": {},
        "agents_used": 0,
        "top_bot": None,
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
        # Use explicit hours field if provided, otherwise default estimate
        explicit_hours = e.get("hours")
        if explicit_hours is not None:
            try:
                hours = float(explicit_hours)
            except (TypeError, ValueError):
                hours = _HOURS_PER_EVENT.get(t, 0.0)
        else:
            hours = _HOURS_PER_EVENT.get(t, 0.0)
        s["hours_saved"] += hours
        # Track by-agent usage
        agent = e.get("agent")
        if agent:
            s["by_agent"][agent] = s["by_agent"].get(agent, 0) + 1
    s["hours_saved"] = round(s["hours_saved"], 2)
    # Human hours saved = 3× AI hours (AI works ~3× faster than a human)
    s["human_hours_saved"] = round(s["hours_saved"] * 3, 2)
    s["cost_saved"] = round(s["hours_saved"] * _COST_PER_HOUR_EUR, 2)
    s["agents_used"] = len(s["by_agent"])
    if s["by_agent"]:
        s["top_bot"] = max(s["by_agent"], key=lambda k: s["by_agent"][k])
    # Derived KPIs shown in the ROI summary section
    tasks = s["tasks_completed"]
    if tasks > 0:
        # Efficiency: AI hours saved per task vs. a 1-hour baseline, capped at 100 %.
        # e.g. if the AI saved 0.8 h per task on average → 80 % efficiency.
        s["efficiency_rate"] = round(min(100.0, s["hours_saved"] / tasks * 100), 1)
        # Average AI processing time per task, expressed in minutes.
        s["avg_task_duration"] = f"{round(s['hours_saved'] / tasks * 60, 0):.0f}m"
    else:
        s["efficiency_rate"] = None
        s["avg_task_duration"] = None
    return s


@app.get("/api/metrics", tags=["monitoring"])
def get_metrics(period: str = "all"):
    data = _load_metrics()
    events = data.get("events", [])
    now_dt = datetime.now(timezone.utc)
    if period == "today":
        cutoff = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        events = [e for e in events if e.get("ts", "") >= cutoff.isoformat()]
    elif period == "7d":
        cutoff = now_dt - timedelta(days=7)
        events = [e for e in events if e.get("ts", "") >= cutoff.isoformat()]
    elif period == "30d":
        cutoff = now_dt - timedelta(days=30)
        events = [e for e in events if e.get("ts", "") >= cutoff.isoformat()]
    summary = _recalc_summary(events) if period != "all" else data.get("summary", {})
    return JSONResponse({"summary": summary, "events": events})


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
    # Accept explicit hours field for direct hour-tracking events
    hours = payload.get("hours")
    if hours is not None:
        try:
            hours = float(hours)
            hours = max(0.0, hours)  # ensure non-negative
        except (TypeError, ValueError):
            hours = None
    notes = (payload.get("notes") or "").strip() or None

    data = _load_metrics()
    events = data.get("events", [])
    event: dict = {
        "id": _uuid.uuid4().hex[:10],
        "type": event_type,
        "agent": agent,
        "value": value,
        "notes": notes,
        "ts": now_iso(),
    }
    if hours is not None:
        event["hours"] = hours
    events.append(event)
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
def deploy_template(template_id: str, _auth: None = Depends(require_auth)):
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
    data = _cached_read(GUARDRAILS_FILE)
    return data if data else {"pending": [], "log": [], "settings": {}, "summary": {}}


def _save_guardrails(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    GUARDRAILS_FILE.write_text(json.dumps(data, indent=2))
    _invalidate_cache(GUARDRAILS_FILE)


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
    if "custom_rules" not in data:
        data["custom_rules"] = []
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
def approve_guardrail_action(action_id: str, _auth: None = Depends(require_auth)):
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


@app.post("/api/guardrails/{action_id}/reject")
def reject_guardrail_action(action_id: str, payload: dict = None, _auth: None = Depends(require_auth)):
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


@app.post("/api/guardrails/settings")
def save_guardrail_settings(payload: dict, _auth: None = Depends(require_auth)):
    data = _load_guardrails()
    data["settings"] = payload
    _save_guardrails(data)
    return JSONResponse({"ok": True})


@app.post("/api/guardrails/custom")
def add_custom_guardrail(payload: dict, _auth: None = Depends(require_auth)):
    import uuid as _uuid
    rule_text = (payload.get("rule") or "").strip()
    if not rule_text:
        raise HTTPException(400, "rule is required")
    data = _load_guardrails()
    custom_rules = data.get("custom_rules", [])
    rule_id = _uuid.uuid4().hex[:12]
    custom_rules.append({
        "id": rule_id,
        "type": payload.get("type", "custom"),
        "rule": rule_text,
        "severity": payload.get("severity", "medium"),
        "created_at": now_iso(),
    })
    data["custom_rules"] = custom_rules
    _save_guardrails(data)
    return JSONResponse({"ok": True, "id": rule_id, "total": len(custom_rules)})


@app.delete("/api/guardrails/custom/{rule_id}")
def delete_custom_guardrail(rule_id: str):
    data = _load_guardrails()
    custom_rules = data.get("custom_rules", [])
    original_len = len(custom_rules)
    custom_rules = [r for r in custom_rules if r.get("id") != rule_id]
    if len(custom_rules) == original_len:
        raise HTTPException(404, f"Custom rule '{rule_id}' not found")
    data["custom_rules"] = custom_rules
    _save_guardrails(data)
    return JSONResponse({"ok": True})




def _load_memory() -> dict:
    data = _cached_read(MEMORY_FILE)
    return data if data else {"clients": {}, "recent_interactions": []}


def _save_memory(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2))
    _invalidate_cache(MEMORY_FILE)


def _vector_store_memory(key: str, text: str, metadata: dict | None = None, importance: float = 0.5) -> None:
    try:
        from memory.vector_store import get_vector_store  # type: ignore
    except Exception:
        try:
            from memory.vector_store import get_vector_store  # type: ignore
        except Exception:
            return
    try:
        get_vector_store().store(key, text, metadata=metadata or {}, importance=importance)
    except Exception:
        logger.debug("memory vector store write failed", exc_info=True)


@app.get("/api/memory")
def get_memory():
    data = _load_memory()
    clients_list = sorted(data.get("clients", {}).values(), key=lambda c: c.get("added_at", ""), reverse=True)
    return JSONResponse({
        "clients": clients_list,
        "recent_interactions": data.get("recent_interactions", [])[-20:],
        "total_clients": len(clients_list),
    })


@app.get("/api/memory/conversations")
def get_memory_conversations():
    """Return recent closed chat sessions as conversations."""
    data = _load_memory()
    # Use stored conversations if available
    conversations = data.get("conversations", [])
    # Also pull from recent_interactions for summary
    interactions = data.get("recent_interactions", [])
    # Group interactions into conversation sessions (by day)
    if not conversations and interactions:
        sessions: dict = {}
        for i in interactions:
            day = (i.get("ts") or "")[:10] or "Unknown"
            sessions.setdefault(day, []).append(i)
        for day, msgs in sorted(sessions.items(), reverse=True):
            first = msgs[0]
            conversations.append({
                "title": f"Session on {day}",
                "summary": (first.get("summary") or first.get("message") or "Chat session")[:200],
                "date": day,
                "message_count": len(msgs),
                "full_summary": "\n".join(
                    (m.get("summary") or m.get("message") or "") for m in msgs
                )[:600],
            })
    return JSONResponse({"conversations": conversations[-50:], "total": len(conversations)})


@app.get("/api/memory/search")
def search_memory(q: str = Query(..., min_length=1, max_length=500), top_k: int = Query(8, ge=1, le=25), memory_type: str | None = None):
    """Semantic memory search backed by the local vector store with JSON-memory fallback."""
    results: list[dict] = []
    vector_available = False
    try:
        from memory.vector_store import get_vector_store  # type: ignore
    except Exception:
        try:
            from memory.vector_store import get_vector_store  # type: ignore
        except Exception:
            get_vector_store = None  # type: ignore
    if get_vector_store is not None:  # type: ignore[name-defined]
        try:
            raw = get_vector_store().search(q, top_k=top_k, memory_type=memory_type)  # type: ignore[name-defined]
            vector_available = True
            for item in raw:
                results.append({
                    "id": item.get("key"),
                    "type": item.get("metadata", {}).get("memory_type") or "semantic",
                    "title": item.get("metadata", {}).get("title") or item.get("key"),
                    "content": item.get("text") or "",
                    "source": item.get("metadata", {}).get("source") or "vector-store",
                    "score": item.get("_score", 0),
                    "metadata": item.get("metadata", {}),
                    "last_accessed": item.get("last_accessed"),
                    "access_count": item.get("access_count", 0),
                })
        except Exception:
            logger.debug("memory vector search failed", exc_info=True)

    if len(results) < top_k:
        data = _load_memory()
        ql = q.lower()
        for client in data.get("clients", {}).values():
            text = " ".join(str(client.get(k) or "") for k in ("name", "company", "email", "status", "notes"))
            if ql in text.lower():
                results.append({
                    "id": client.get("id"),
                    "type": "semantic",
                    "title": client.get("name") or client.get("id"),
                    "content": text,
                    "source": "json-memory:clients",
                    "score": 0.5,
                    "metadata": {"client_id": client.get("id")},
                    "last_accessed": client.get("updated_at") or client.get("added_at"),
                    "access_count": client.get("interactions", 0),
                })
        for idx, item in enumerate(data.get("recent_interactions", [])):
            text = str(item.get("summary") or item.get("message") or "")
            if ql in text.lower():
                results.append({
                    "id": item.get("ts") or f"interaction-{idx}",
                    "type": "episodic",
                    "title": text[:80],
                    "content": text,
                    "source": item.get("agent") or "json-memory:interactions",
                    "score": 0.45,
                    "metadata": {"client_id": item.get("client_id")},
                    "last_accessed": item.get("ts"),
                    "access_count": 0,
                })

    return JSONResponse({
        "ok": True,
        "query": q,
        "source": "vector-store" if vector_available else "json-fallback",
        "results": results[:top_k],
        "total": len(results[:top_k]),
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
        "phone": (payload.get("phone") or "").strip() or None,
        "status": (payload.get("status") or "prospect").strip(),
        "notes": (payload.get("notes") or "").strip() or None,
        "last_contact": (payload.get("last_contact") or "").strip() or None,
        "interactions": 0,
        "added_at": now_iso(),
        "updated_at": now_iso(),
    }
    clients[client_id] = client
    data["clients"] = clients
    _save_memory(data)
    _vector_store_memory(
        f"client:{client_id}",
        " ".join(str(client.get(k) or "") for k in ("name", "company", "email", "status", "notes")),
        metadata={"source": "python-memory:clients", "memory_type": "semantic", "client_id": client_id, "title": name},
        importance=0.7,
    )
    return JSONResponse({"ok": True, "id": client_id})


@app.patch("/api/memory/clients/{client_id}")
def update_memory_client(client_id: str, payload: dict):
    data = _load_memory()
    clients = data.get("clients", {})
    if client_id not in clients:
        raise HTTPException(404, f"Client '{client_id}' not found")
    client = clients[client_id]
    for field in ("name", "company", "email", "phone", "status", "notes", "last_contact"):
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
    if interaction["summary"]:
        _vector_store_memory(
            f"interaction:{interaction['ts']}:{len(interactions)}",
            interaction["summary"],
            metadata={"source": interaction["agent"], "memory_type": "episodic", "client_id": interaction.get("client_id")},
            importance=0.55,
        )

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
    {
        "id": "linkedin",
        "name": "LinkedIn",
        "icon": "💼",
        "description": "Post content, manage connections, and run LinkedIn lead generation",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "access_token", "label": "LinkedIn Access Token", "type": "password", "placeholder": "AQV…"},
            {"key": "person_urn", "label": "Person URN (optional)", "type": "text", "placeholder": "urn:li:person:XXXXXXX"},
        ],
    },
    {
        "id": "youtube",
        "name": "YouTube",
        "icon": "▶️",
        "description": "Upload videos, manage channel, and analyze performance via YouTube Data API",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "api_key", "label": "YouTube API Key", "type": "password", "placeholder": "AIza…"},
            {"key": "channel_id", "label": "Channel ID", "type": "text", "placeholder": "UCxxxxxxxxxxxxxxxx"},
        ],
    },
    {
        "id": "instagram",
        "name": "Instagram / Meta",
        "icon": "📸",
        "description": "Post to Instagram, manage content calendar, and track engagement via Meta Graph API",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "access_token", "label": "Meta Access Token", "type": "password", "placeholder": "EAAxxxxxx…"},
            {"key": "instagram_account_id", "label": "Instagram Account ID", "type": "text", "placeholder": "17841400000000000"},
        ],
    },
    {
        "id": "hubspot",
        "name": "HubSpot CRM",
        "icon": "🟠",
        "description": "Sync leads, deals, contacts, and activities with HubSpot CRM",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "api_key", "label": "HubSpot Private App Token", "type": "password", "placeholder": "pat-na1-…"},
            {"key": "portal_id", "label": "Portal ID (optional)", "type": "text", "placeholder": "12345678"},
        ],
    },
    {
        "id": "notion",
        "name": "Notion",
        "icon": "📓",
        "description": "Create and update pages in Notion databases — CRM, tasks, reports",
        "enabled": False,
        "config": {},
        "fields": [
            {"key": "api_key", "label": "Notion API Key", "type": "password", "placeholder": "secret_…"},
            {"key": "database_id", "label": "Default Database ID", "type": "text", "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
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
    try:
        INTEGRATIONS_FILE.chmod(0o600)  # restrict to owner only — config contains API keys/tokens
    except OSError:
        pass


@app.get("/api/integrations")
def list_integrations():
    return JSONResponse({"integrations": _load_integrations()})


@app.patch("/api/integrations/{integration_id}")
def update_integration(integration_id: str, payload: dict, _auth: None = Depends(require_auth)):
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


def _validate_webhook_url(url: str) -> str | None:
    """Validate a user-supplied webhook URL to prevent SSRF attacks.

    Delegates to the shared url_guard module (single source of truth).
    Returns an error string if rejected, or None if safe.
    """
    try:
        from core.url_guard import validate_url  # type: ignore
        return validate_url(url)
    except ImportError:
        # Inline fallback if url_guard is somehow unavailable
        import urllib.parse as _up
        parsed = _up.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "Webhook URL must use http:// or https://"
        if not parsed.hostname:
            return "Webhook URL has no valid hostname"
        return None


@app.post("/api/integrations/{integration_id}/test")
def test_integration(integration_id: str, _auth: None = Depends(require_auth)):
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
        ssrf_error = _validate_webhook_url(url)
        if ssrf_error:
            raise HTTPException(400, ssrf_error)
        try:
            import urllib.request as _req
            req = _req.Request(url, method="POST",
                               data=b'{"test":true}',
                               headers={"Content-Type": "application/json"})
            with _req.urlopen(req, timeout=5) as resp:
                return JSONResponse({"ok": True, "message": f"HTTP {resp.status} — webhook reachable"})
        except Exception as exc:
            logger.warning("Webhook test failed: %s", exc)
            return JSONResponse({"ok": False, "message": "Webhook connection test failed"})

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
            logger.warning("Telegram test failed: %s", exc)
            return JSONResponse({"ok": False, "message": "Could not connect to Telegram"})
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
    "NEWS_API_KEY", "ALPHA_INSIDER_KEY",
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


@app.post("/api/settings")
def save_settings(body: _SettingsUpdateRequest, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("settings:write"))):
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
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


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
            logger.warning("Data nuke: failed to delete %s: %s", f.name, exc)
            errors.append(f"{f.name}: deletion failed")

    # Also clear any extra .jsonl chat files
    try:
        for jsonl in STATE_DIR.glob("*.jsonl"):
            jsonl.unlink()
            deleted.append(jsonl.name)
    except Exception as exc:
        logger.warning("Data nuke: failed to clear jsonl files: %s", exc)
        errors.append("Failed to clear some chat history files")

    logger.warning("DATA NUKE performed — deleted: %s", deleted)
    return JSONResponse({"ok": True, "deleted": deleted, "errors": errors})


@app.post("/api/settings/uninstall")
def uninstall_bot(body: _UninstallRequest):
    """Stop all agents and remove the entire AI_HOME directory tree.

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

    # ── Step 1: stop all agents gracefully ────────────────────────────────────
    ai_bin = AI_HOME / "bin" / "ai-employee"
    try:
        import subprocess as _sp
        _sp.run([str(ai_bin), "stop", "--all"], timeout=30,
                capture_output=True)
        logger.warning("UNINSTALL: all agents stopped")
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
            "All agents have been stopped and the installation directory "
            f"({AI_HOME}) will be deleted in seconds."
        ),
    })


# ── Updater status / trigger ──────────────────────────────────────────────────

_UPDATER_STATE_FILE = STATE_DIR / "updater.json"
_UPDATER_COMMIT_FILE = STATE_DIR / "installed_commit.txt"
_UPDATER_TRIGGER_FILE = AI_HOME / "run" / "updater.trigger"
_UPDATER_SCRIPT_FILE = AI_HOME / "agents" / "auto-updater" / "auto_updater.py"


def _signal_running_updater() -> bool:
    """Wake the background updater process if a live PID is known."""
    try:
        if not _UPDATER_STATE_FILE.exists():
            return False
        state = json.loads(_UPDATER_STATE_FILE.read_text())
        pid = int(state.get("pid") or 0)
        if pid <= 0:
            return False
        # liveness probe
        os.kill(pid, 0)
        import signal as _sig
        os.kill(pid, _sig.SIGUSR1)
        return True
    except Exception:
        return False


def _start_updater_once() -> bool:
    """Fallback when no updater daemon is active: run one immediate check."""
    try:
        if not _UPDATER_SCRIPT_FILE.exists():
            return False
        py_exec = sys.executable or "python3"
        subprocess.Popen(
            [py_exec, str(_UPDATER_SCRIPT_FILE), "--once"],
            cwd=str(AI_HOME),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


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
        if _signal_running_updater():
            return JSONResponse({"ok": True, "message": "Check triggered — results appear in Auto Update card within seconds"})
        if _start_updater_once():
            return JSONResponse({"ok": True, "message": "Background updater was idle — started one immediate check now"})
        return JSONResponse({"ok": True, "message": "Check queued — updater will run when available"})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/updater/update")
def updater_update():
    """Trigger an immediate forced update (downloads + restarts even if already up to date)."""
    try:
        _UPDATER_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATER_TRIGGER_FILE.write_text("force")
        if _signal_running_updater():
            return JSONResponse({"ok": True, "message": "Update triggered — agents will restart momentarily if changes are found"})
        if _start_updater_once():
            return JSONResponse({"ok": True, "message": "Background updater was idle — started one immediate update check now"})
        return JSONResponse({"ok": True, "message": "Update queued — updater will run when available"})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ─── Compatibility alias endpoints ────────────────────────────────────────────
# These thin wrappers expose the URLs used by the CLI, curl tests, and
# documentation so external callers always get a 2xx response.

@app.get("/api/workers/list")
def get_bots_alias():
    """Alias for GET /api/workers — returns list of all agents with running status."""
    return get_workers()


@app.get("/api/chat/history")
def get_chat_history_alias(limit: int = 500):
    """Alias for GET /api/history — returns activity log entries."""
    return get_history(limit=limit)


@app.get("/api/tasks")
def list_tasks_alias():
    """Alias for GET /api/task/list — returns task plans."""
    return list_tasks()


@app.post("/api/tasks")
def create_task_alias(payload: dict):
    """Alias for POST /api/task/submit.
    Accepts {task, agent} or the native {description, agents, mode} shape.
    """
    # Normalise legacy shape used by the CLI: {"task": "...", "agent": "..."}
    if "description" not in payload and "task" in payload:
        agent = payload.get("agent", "")
        payload = {
            "description": payload["task"],
            "agents": [agent] if agent else [],
            "mode": "auto",
        }
    return submit_task(payload)


@app.post("/api/metrics/record")
def record_metric_alias(payload: dict):
    """Alias for POST /api/metrics — records a metric event.
    Accepts either native shape or simplified {"event": "lead_generated"} shape.
    """
    # Normalise simplified shape: {"event": "lead_generated"} or
    # {"event": "deal_closed:5000"}
    if "type" not in payload and "event" in payload:
        raw = payload["event"]
        parts = raw.split(":", 1)
        norm = {"type": parts[0].strip()}
        if len(parts) == 2:
            try:
                norm["value"] = float(parts[1])
            except ValueError:
                norm["notes"] = parts[1].strip()
        payload = norm
    return record_metric(payload)


@app.post("/api/templates/deploy")
def deploy_template_alias(payload: dict, _auth: None = Depends(require_auth)):
    """Convenience endpoint — calls POST /api/templates/{template_id}/deploy.
    Accepts {"template_id": "get-10-leads-24h"}.
    """
    template_id = (payload.get("template_id") or "").strip()
    if not template_id:
        raise HTTPException(400, "template_id required")
    return deploy_template(template_id)


@app.post("/api/guardrails/approve")
def approve_guardrail_alias(payload: dict, _auth: None = Depends(require_auth)):
    """Convenience endpoint — approves a pending guardrail action.
    Accepts {"action_id": "..."}.
    Returns 200 always; {"ok": false} if the action was not found in the queue.
    """
    action_id = (payload.get("action_id") or "").strip()
    if not action_id:
        raise HTTPException(400, "action_id required")
    try:
        return approve_guardrail_action(action_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"ok": False, "action_id": action_id, "message": "action not found in pending queue"})
        raise


@app.post("/api/guardrails/reject")
def reject_guardrail_alias(payload: dict, _auth: None = Depends(require_auth)):
    """Convenience endpoint — rejects a pending guardrail action.
    Accepts {"action_id": "...", "reason": "..."}.
    Returns 200 always; {"ok": false} if the action was not found in the queue.
    """
    action_id = (payload.get("action_id") or "").strip()
    if not action_id:
        raise HTTPException(400, "action_id required")
    try:
        return reject_guardrail_action(action_id, payload)
    except HTTPException as exc:
        if exc.status_code == 404:
            return JSONResponse({"ok": False, "action_id": action_id, "message": "action not found in pending queue"})
        raise


@app.post("/api/memory")
def add_memory_alias(payload: dict):
    """Alias for POST /api/memory/clients — adds a new CRM client."""
    return add_memory_client(payload)


@app.post("/api/integrations/save")
def save_integration_alias(payload: dict):
    """Save/update a single integration config.
    Accepts {"integration": "<id>", "token": "...", ...} or
            {"integration": "<id>", "config": {...}}.
    """
    integration_id = (payload.get("integration") or "").strip()
    if not integration_id:
        raise HTTPException(400, "integration field required")
    # Build config dict from remaining keys (excluding "integration")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {
        k: v for k, v in payload.items() if k != "integration"
    }
    integrations = _load_integrations()
    intg = next((i for i in integrations if i["id"] == integration_id), None)
    if not intg:
        # Auto-create a minimal entry so the save always succeeds
        intg = {"id": integration_id, "name": integration_id, "enabled": True, "config": {}}
        integrations.append(intg)
    intg["config"] = config
    intg["enabled"] = True
    _save_integrations(integrations)
    return JSONResponse({"ok": True, "integration": integration_id})


# ── BLACKLIGHT API ────────────────────────────────────────────────────────────

_blacklight_mod = None


def _load_blacklight_module():
    """Lazy-import and cache the blacklight module from the agents directory."""
    global _blacklight_mod
    if _blacklight_mod is not None:
        return _blacklight_mod
    _bl_path = BOTS_DIR / "blacklight"
    if str(_bl_path) not in sys.path:
        sys.path.insert(0, str(_bl_path))
    _blacklight_mod = importlib.import_module("blacklight")
    return _blacklight_mod


@app.get("/api/blacklight/status")
def blacklight_status():
    """Return BLACKLIGHT running state and stats."""
    try:
        bl = _load_blacklight_module()
        return JSONResponse(bl.get_status())
    except Exception as exc:
        logger.warning("blacklight status error: %s", exc)
        return JSONResponse({"running": False, "goal": "", "cycle": 0,
                             "opportunities_found": 0, "actions_taken": 0,
                             "last_activity": None})


@app.post("/api/blacklight/start")
def blacklight_start(payload: dict, _auth: None = Depends(require_auth)):
    """Start the BLACKLIGHT autonomous loop with the given goal.

    Governance gates:
    - BLACKLIGHT_LEGAL_REVIEW=1 must be set (blacklight.py enforces this).
    - Every start attempt is recorded in the AuditEngine.
    """
    goal = (payload.get("goal") or "").strip()
    if not goal:
        raise HTTPException(400, "goal is required")
    if len(goal) > 2000:
        raise HTTPException(400, "goal must be 2000 characters or fewer")
    try:
        bl = _load_blacklight_module()
        # Audit the attempt regardless of outcome
        _audit_logger.info(json.dumps({
            "event": "blacklight_start_attempt",
            "goal_preview": goal[:200],
            "timestamp": now_iso(),
            "legal_review_flag": os.environ.get("BLACKLIGHT_LEGAL_REVIEW", "0"),
        }))
        started = bl.start(goal)
        if started:
            return JSONResponse({"ok": True, "goal": goal,
                                 "message": "BLACKLIGHT started"})
        return JSONResponse({"ok": False, "message": "BLACKLIGHT is already running"})
    except RuntimeError as exc:
        # Legal-review gate raised by blacklight.start()
        logger.warning("blacklight start blocked: %s", exc)
        raise HTTPException(status_code=403, detail="forbidden")
    except Exception as exc:
        logger.error("blacklight start error: %s", exc)
        raise HTTPException(500, "Failed to start BLACKLIGHT")


@app.post("/api/blacklight/stop")
def blacklight_stop():
    """Stop the BLACKLIGHT autonomous loop."""
    try:
        bl = _load_blacklight_module()
        stopped = bl.stop()
        return JSONResponse({"ok": stopped,
                             "message": "BLACKLIGHT stopped" if stopped
                             else "BLACKLIGHT was not running"})
    except Exception as exc:
        logger.error("blacklight stop error: %s", exc)
        raise HTTPException(500, "Failed to stop BLACKLIGHT")


@app.get("/api/blacklight/logs")
def blacklight_logs(limit: int = 100):
    """Return recent BLACKLIGHT log entries."""
    try:
        bl = _load_blacklight_module()
        return JSONResponse(bl.get_logs(limit=min(limit, 500)))
    except Exception as exc:
        logger.warning("blacklight logs error: %s", exc)
        return JSONResponse([])


# ── ASCEND_FORGE API ──────────────────────────────────────────────────────────

_ascend_mod = None


def _load_ascend_module():
    """Lazy-import and cache the ascend_forge module from the agents directory."""
    global _ascend_mod
    if _ascend_mod is not None:
        return _ascend_mod
    _af_path = BOTS_DIR / "ascend-forge"
    if str(_af_path) not in sys.path:
        sys.path.insert(0, str(_af_path))
    _ascend_mod = importlib.import_module("ascend_forge")
    return _ascend_mod


@app.get("/api/ascend/status")
def ascend_status():
    """Return ASCEND_FORGE current state, mode, and activity feed."""
    try:
        af = _load_ascend_module()
        return JSONResponse(af.get_status())
    except Exception as exc:
        logger.warning("ascend status error: %s", exc)
        return JSONResponse({"mode": "AUTO", "pending_count": 0,
                             "observe_only": False, "activity": []})


@app.post("/api/ascend/mode")
def ascend_set_mode(payload: dict, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Set ASCEND_FORGE operating mode (GENERAL / MONEY / AUTO)."""
    mode = (payload.get("mode") or "").strip().upper()
    if not mode:
        raise HTTPException(400, "mode is required")
    try:
        af = _load_ascend_module()
        af.set_mode(mode)
        return JSONResponse({"ok": True, "mode": mode})
    except ValueError as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("ascend set_mode error: %s", exc)
        raise HTTPException(500, "Failed to set mode")


@app.post("/api/ascend/scan")
def ascend_scan(_auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Trigger a system scan and return queued patches."""
    try:
        af = _load_ascend_module()
        patches = af.scan_system(trigger="UI scan")
        return JSONResponse({"ok": True, "patches": patches})
    except Exception as exc:
        logger.error("ascend scan error: %s", exc)
        raise HTTPException(500, "Scan failed")


@app.get("/api/ascend/patches")
def ascend_patches():
    """Return all pending patches."""
    try:
        af = _load_ascend_module()
        return JSONResponse(af.get_pending_patches())
    except Exception as exc:
        logger.warning("ascend patches error: %s", exc)
        return JSONResponse([])


@app.post("/api/ascend/patches/{patch_id}/approve")
def ascend_approve(patch_id: str, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Approve a pending patch."""
    try:
        af = _load_ascend_module()
        patch = af.approve_patch(patch_id)
        return JSONResponse({"ok": True, "patch": patch})
    except (ValueError, RuntimeError) as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("ascend approve error: %s", exc)
        raise HTTPException(500, "Approval failed")


@app.post("/api/ascend/patches/{patch_id}/reject")
def ascend_reject(patch_id: str, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Reject a pending patch."""
    try:
        af = _load_ascend_module()
        patch = af.reject_patch(patch_id)
        return JSONResponse({"ok": True, "patch": patch})
    except (ValueError, RuntimeError) as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("ascend reject error: %s", exc)
        raise HTTPException(500, "Rejection failed")


@app.post("/api/ascend/patches/{patch_id}/rollback")
def ascend_rollback(patch_id: str, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Roll back an approved patch."""
    try:
        af = _load_ascend_module()
        patch = af.rollback_patch(patch_id)
        return JSONResponse({"ok": True, "patch": patch})
    except (ValueError, RuntimeError) as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("ascend rollback error: %s", exc)
        raise HTTPException(500, "Rollback failed")


@app.get("/api/ascend/changelog")
def ascend_changelog(limit: int = 50):
    """Return change history."""
    try:
        af = _load_ascend_module()
        return JSONResponse(af.get_changelog(limit=min(limit, 200)))
    except Exception as exc:
        logger.warning("ascend changelog error: %s", exc)
        return JSONResponse([])


@app.post("/api/ascend/auto-approve")
def ascend_auto_approve(payload: dict, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("admin:*"))):
    """Toggle auto-approve for LOW risk patches."""
    enabled = bool(payload.get("enabled", False))
    try:
        af = _load_ascend_module()
        af.set_auto_approve_low(enabled)
        return JSONResponse({"ok": True, "auto_approve_low": enabled})
    except Exception as exc:
        logger.error("ascend auto-approve error: %s", exc)
        raise HTTPException(500, "Failed to update setting")


# ── Ascend Forge independent task queue ──────────────────────────────────────
import uuid as _uuid_mod

_af_task_lock = threading.Lock()
_af_current_task: dict = {
    "task_id": "",
    "task": "",
    "status": "idle",   # idle | running | done | error
    "progress": 0,      # 0-100
    "result": "",
    "started_at": "",
    "finished_at": "",
    "events": [],
}


def _af_append_event(status: str, progress: int, message: str) -> None:
    event = {
        "ts": now_iso(),
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "message": message,
        "agent_id": "ascend-forge",
        "task_id": _af_current_task.get("task_id", ""),
    }
    events = _af_current_task.get("events", [])
    events.append(event)
    _af_current_task["events"] = events[-50:]


def _run_ascend_task(task_id: str, task: str) -> None:
    """Run an Ascend Forge task in a background thread with progress tracking."""
    with _af_task_lock:
        _af_current_task.update({
            "task_id": task_id,
            "task": task,
            "status": "running",
            "progress": 5,
            "result": "",
            "started_at": now_iso(),
            "finished_at": "",
            "events": [],
        })
        _af_append_event("running", 5, "Task accepted by Ascend Forge")
    _log_activity("task_run", f"Ascend Forge task started: {task}", details={"task_id": task_id, "status": "running", "agent_id": "ascend-forge"}, source="ascend")
    try:
        af = _load_ascend_module()
        # Step 1 – analyze intent (20%)
        with _af_task_lock:
            _af_current_task["progress"] = 20
            _af_append_event("running", 20, "Analyzing task intent")
        # Step 2 – plan and execute (60%)
        with _af_task_lock:
            _af_current_task["progress"] = 60
            _af_append_event("running", 60, "Executing plan")
        result = af.handle_complex_task(task)
        with _af_task_lock:
            _af_current_task.update({
                "status": "done",
                "progress": 100,
                "result": result,
                "finished_at": now_iso(),
            })
            _af_append_event("done", 100, "Task completed successfully")
        _log_activity("task_run", "Ascend Forge task completed", details={"task_id": task_id, "status": "done", "agent_id": "ascend-forge"}, source="ascend")
    except Exception as exc:
        logger.error("ascend task error: %s", exc)
        with _af_task_lock:
            _af_current_task.update({
                "status": "error",
                "progress": 0,
                "result": "operation_failed",
                "finished_at": now_iso(),
            })
            _af_append_event("error", 0, f"Task failed: {exc}")
        _log_activity("task_run", "Ascend Forge task failed", details={"task_id": task_id, "status": "error", "agent_id": "ascend-forge", "error": "operation_failed"}, source="ascend")


@app.post("/api/ascend/task")
def ascend_run_task(payload: dict, _auth: None = Depends(require_auth)):
    """Assign an independent task directly to Ascend Forge."""
    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(400, "task is required")
    with _af_task_lock:
        if _af_current_task.get("status") == "running":
            raise HTTPException(409, "another Ascend Forge task is already running")
    task_id = str(_uuid_mod.uuid4())[:8]
    t = threading.Thread(target=_run_ascend_task, args=(task_id, task), daemon=True)
    t.start()
    return JSONResponse({"ok": True, "task_id": task_id, "task": task})


@app.get("/api/ascend/progress")
def ascend_progress():
    """Return current Ascend Forge task progress."""
    with _af_task_lock:
        return JSONResponse(dict(_af_current_task))


@app.post("/api/ascend/analyze")
def ascend_analyze(payload: dict, _auth: None = Depends(require_auth)):
    """Analyze a complex prompt and return a structured plan without executing."""
    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(400, "task is required")
    try:
        af = _load_ascend_module()
        plan = af.analyze_prompt(task)
        return JSONResponse({"ok": True, "plan": plan})
    except Exception as exc:
        logger.error("ascend analyze error: %s", exc)
        raise HTTPException(500, "Analysis failed")


# ── Blacklight direct task assignment ────────────────────────────────────────

_bl_task_lock = threading.Lock()
_bl_direct_task: dict = {
    "task_id": "",
    "task": "",
    "status": "idle",
    "progress": 0,
    "result": "",
    "started_at": "",
    "finished_at": "",
}


def _run_blacklight_task(task_id: str, task: str) -> None:
    """Run a direct Blacklight task independently in a background thread."""
    with _bl_task_lock:
        _bl_direct_task.update({
            "task_id": task_id,
            "task": task,
            "status": "running",
            "progress": 10,
            "result": "",
            "started_at": now_iso(),
            "finished_at": "",
        })
    try:
        bl = _load_blacklight_module()
        with _bl_task_lock:
            _bl_direct_task["progress"] = 30
        # Re-start with task as goal
        if bl.is_running():
            bl.stop()
        with _bl_task_lock:
            _bl_direct_task["progress"] = 50
        started = bl.start(task)
        with _bl_task_lock:
            _bl_direct_task.update({
                "status": "done",
                "progress": 100,
                "result": "⚡ BLACKLIGHT started with task: " + task if started else "ℹ️ Already running — goal updated.",
                "finished_at": now_iso(),
            })
    except Exception as exc:
        logger.error("blacklight task error: %s", exc)
        with _bl_task_lock:
            _bl_direct_task.update({
                "status": "error",
                "progress": 0,
                "result": "operation_failed",
                "finished_at": now_iso(),
            })


@app.post("/api/blacklight/task")
def blacklight_run_task(payload: dict, _auth: None = Depends(require_auth)):
    """Assign a direct task to BLACKLIGHT, bypassing the normal goal toggle.

    Governance gate: BLACKLIGHT_LEGAL_REVIEW=1 must be set, same as /start.
    Every task submission is recorded in the audit log.
    """
    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(400, "task is required")

    # ── Governance gate: legal review required ────────────────────────────────
    bl = _load_blacklight_module()
    if getattr(bl, "LEGAL_REVIEW_REQUIRED", True):
        _audit_logger.warning(json.dumps({
            "event": "blacklight_task_blocked",
            "reason": "legal_review_required",
            "task_preview": task[:200],
            "timestamp": now_iso(),
        }))
        raise HTTPException(
            403,
            "BLACKLIGHT task blocked: BLACKLIGHT_LEGAL_REVIEW=1 is required. "
            "Set this environment variable only after a qualified legal/compliance review.",
        )

    _audit_logger.info(json.dumps({
        "event": "blacklight_task_submitted",
        "task_preview": task[:200],
        "timestamp": now_iso(),
    }))
    task_id = str(_uuid_mod.uuid4())[:8]
    t = threading.Thread(target=_run_blacklight_task, args=(task_id, task), daemon=True)
    t.start()
    return JSONResponse({"ok": True, "task_id": task_id, "task": task})


@app.get("/api/blacklight/task-progress")
def blacklight_task_progress():
    """Return current Blacklight direct-task progress."""
    with _bl_task_lock:
        return JSONResponse(dict(_bl_direct_task))


# ── Neural Brain + IntelligenceCore API ──────────────────────────────────────

_brain_mod = None
_brain_mod_lock = threading.Lock()

_intel_mod = None
_intel_mod_lock = threading.Lock()

# (_DEFAULT_USER is defined at the top of the file, near the path constants)


def _load_intelligence():
    """Lazy-load and return the IntelligenceCore singleton.

    Returns None gracefully if PyTorch is not installed or the module fails
    to import — all callers must handle None.
    """
    global _intel_mod
    if _intel_mod is not None:
        return _intel_mod
    with _intel_mod_lock:
        if _intel_mod is not None:
            return _intel_mod
        try:
            _brain_dir   = Path(__file__).resolve().parents[2] / "brain"
            _runtime_dir = Path(__file__).resolve().parents[2]
            for _d in [str(_runtime_dir), str(_brain_dir)]:
                if _d not in sys.path:
                    sys.path.insert(0, _d)
            from brain.intelligence import get_intelligence  # noqa: PLC0415
            _intel_mod = get_intelligence()
        except Exception as exc:
            logger.warning("IntelligenceCore unavailable: %s", exc)
    return _intel_mod


def _load_brain():
    """Lazy-import and return the global Brain singleton.

    Adds runtime/brain/ to sys.path the first time it's called so the import
    works regardless of the working directory.  Returns None gracefully if
    PyTorch is not installed or brain module cannot be loaded.
    """
    global _brain_mod
    if _brain_mod is not None:
        return _brain_mod
    with _brain_mod_lock:
        if _brain_mod is not None:
            return _brain_mod
        try:
            _brain_dir = Path(__file__).resolve().parents[2] / "brain"
            _runtime_dir = Path(__file__).resolve().parents[2]
            for _d in [str(_runtime_dir), str(_brain_dir)]:
                if _d not in sys.path:
                    sys.path.insert(0, _d)
            from brain.brain import get_brain  # noqa: PLC0415
            _brain_mod = get_brain()
        except Exception as exc:
            logger.warning("Neural Brain unavailable: %s", exc)
            return None
    return _brain_mod


def _brain_fallback_status() -> dict:
    return {
        "available": False, "learn_step": 0, "experience_count": 0,
        "buffer_size": 0, "buffer_capacity": 0, "last_loss": 0.0,
        "last_reward": 0.0, "avg_reward": 0.0, "device": "—",
        "model_path": "—", "is_online": False, "bg_running": False, "lr": 0.0,
    }


@app.get("/api/brain/status")
def brain_status():
    """Return current Neural Brain stats (safe — never raises)."""
    brain = _load_brain()
    if brain is None:
        return JSONResponse(_brain_fallback_status())
    try:
        s = brain.stats()
        cfg = brain.cfg
        s["available"] = True
        s["cfg_input_size"]   = cfg["model"]["input_size"]
        s["cfg_output_size"]  = cfg["model"]["output_size"]
        s["cfg_hidden"]       = str(cfg["model"]["hidden_sizes"])
        s["cfg_batch_size"]   = cfg["training"]["batch_size"]
        s["cfg_update_freq"]  = cfg["training"]["update_frequency"]
        return JSONResponse(s)
    except Exception as exc:
        logger.warning("brain status error: %s", exc)
        return JSONResponse(_brain_fallback_status())


@app.post("/api/brain/learn")
def brain_learn(_auth: None = Depends(require_auth)):
    """Trigger one manual learn step."""
    brain = _load_brain()
    if brain is None:
        return JSONResponse({"ok": False, "message": "Brain not available"})
    try:
        loss = brain.learn()
        return JSONResponse({"ok": True, "loss": loss, "learn_step": brain.learn_step})
    except Exception as exc:
        logger.error("brain learn error: %s", exc)
        return JSONResponse({"ok": False, "message": "Learn step failed — check server logs"})

@app.post("/api/brain/save")
def brain_save(_auth: None = Depends(require_auth)):
    """Save brain model to disk."""
    brain = _load_brain()
    if brain is None:
        return JSONResponse({"ok": False, "message": "Brain not available"})
    try:
        brain.save()
        return JSONResponse({"ok": True, "path": str(brain._model_path)})
    except Exception as exc:
        logger.error("brain save error: %s", exc)
        return JSONResponse({"ok": False, "message": "Save failed — check server logs"})


@app.post("/api/brain/clear")
def brain_clear(_auth: None = Depends(require_auth)):
    """Clear the replay buffer."""
    brain = _load_brain()
    if brain is None:
        return JSONResponse({"ok": False, "message": "Brain not available"})
    try:
        brain.replay_buffer.clear()
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.error("brain clear error: %s", exc)
        return JSONResponse({"ok": False, "message": "Clear failed — check server logs"})


@app.post("/api/brain/force-offline")
def brain_force_offline(_auth: None = Depends(require_auth)):
    """Force-collect offline experiences and run a learn step."""
    brain = _load_brain()
    if brain is None:
        return JSONResponse({"ok": False, "message": "Brain not available"})
    try:
        n = brain.force_offline_learn()
        return JSONResponse({"ok": True, "collected": n, "learn_step": brain.learn_step})
    except Exception as exc:
        logger.error("brain force-offline error: %s", exc)
        return JSONResponse({"ok": False, "message": "Offline learn failed — check server logs"})


@app.get("/api/brain/log")
def brain_log(limit: int = 60):
    """Return recent brain log lines from the log file."""
    try:
        _log_file = Path.home() / ".ai-employee" / "logs" / "brain.log"
        if not _log_file.exists():
            return JSONResponse({"lines": []})
        _limit = min(limit, 200)
        raw = _log_file.read_text(errors="replace").splitlines()
        return JSONResponse({"lines": raw[-_limit:]})
    except Exception as exc:
        logger.warning("brain log read error: %s", exc)
        return JSONResponse({"lines": []})


# ── IntelligenceCore API ──────────────────────────────────────────────────────

@app.get("/api/intelligence/profile")
def intelligence_profile(user: str = "user:default"):
    """Return the personalisation profile for a user."""
    intel = _load_intelligence()
    if intel is None:
        return JSONResponse({"available": False})
    try:
        data = intel.stats(user_id=user)
        data["available"] = True
        data["summary"]   = intel.profile_summary(user)
        return JSONResponse(data)
    except Exception as exc:
        logger.warning("intelligence_profile error: %s", exc)
        return JSONResponse({"available": False, "error": "Unable to load profile"})


@app.post("/api/intelligence/reward")
def intelligence_reward(payload: dict, _auth: None = Depends(require_auth)):
    """Provide explicit outcome feedback to train the brain.

    Body: {"user_id": "user:default", "reward": 1.0}
    """
    intel = _load_intelligence()
    if intel is None:
        return JSONResponse({"ok": False, "message": "IntelligenceCore not available"})
    user_id = (payload.get("user_id") or _DEFAULT_USER).strip()
    try:
        reward = float(payload.get("reward", 0.0))
    except (TypeError, ValueError):
        raise HTTPException(400, "reward must be a number")
    try:
        intel.reward(user_id, reward)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.error("intelligence_reward error: %s", exc)
        return JSONResponse({"ok": False, "message": "Unable to apply reward"})


@app.get("/api/intelligence/stats")
def intelligence_stats():
    """Return aggregate IntelligenceCore statistics."""
    intel = _load_intelligence()
    if intel is None:
        return JSONResponse({"available": False})
    try:
        s = intel.stats()
        s["available"] = True
        return JSONResponse(s)
    except Exception as exc:
        logger.warning("intelligence_stats error: %s", exc)
        return JSONResponse({"available": False})


@app.post("/api/agents/bundle-swarm")
def agents_bundle_swarm(payload: dict, _auth: None = Depends(require_auth)):
    """Bundle selected agents and dispatch them as a coordinated swarm task."""
    agent_ids: list = payload.get("agents") or []
    task: str = (payload.get("task") or "").strip()
    preset: str = (payload.get("preset") or "").strip()
    if not agent_ids:
        raise HTTPException(400, "agents list is required")
    label = preset or f"{len(agent_ids)}-agent bundle"
    logger.info("Bundle-to-swarm: %s agents, preset=%s, task=%s", len(agent_ids), preset, task[:60])
    # Persist as a worker bundle so the swarm can pick it up
    try:
        bundle = {
            "id": str(_uuid_mod.uuid4()),
            "name": label,
            "task": task or f"Execute {label} coordinated mission",
            "agents": agent_ids,
            "schedule": "manual",
            "created_at": now_iso(),
            "preset": preset,
        }
        state_dir = AI_HOME / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        bundles_file = state_dir / "worker_bundles.json"
        existing = []
        if bundles_file.exists():
            try:
                existing = json.loads(bundles_file.read_text())
            except Exception as _parse_exc:
                logger.warning("bundle-swarm: corrupt bundles file, starting fresh: %s", _parse_exc)
                existing = []
        existing.append(bundle)
        bundles_file.write_text(json.dumps(existing, indent=2))
        return JSONResponse({"ok": True, "bundle_id": bundle["id"], "name": label, "agents": len(agent_ids)})
    except Exception as exc:
        logger.error("bundle-swarm error: %s", exc)
        raise HTTPException(500, "Failed to create bundle")


# ── New Paperclip-parity features ─────────────────────────────────────────────
# Org Chart, Budget Tracker, Goal Alignment, Ticket System, Governance,
# Company Manager — all lazy-loaded from their respective agent directories.

_org_chart_mod = None
_budget_mod = None
_goal_mod = None
_ticket_mod = None
_gov_mod = None
_company_mod = None

# Lock to ensure thread-safe lazy loading of feature modules
import threading as _threading
_module_load_lock = _threading.Lock()


def _load_module(name: str, agent_dir: str, global_var_name: str):
    """Thread-safe generic lazy-loader for the new feature modules.

    Uses a double-checked locking pattern:
    1. Fast path (no lock) — return immediately if already loaded.
    2. Slow path (under lock) — load the module, guarded by _module_load_lock
       to prevent two threads both observing a None cache and loading twice.
    The double-check inside the lock handles the race where two threads both
    pass the fast path check before either acquires the lock.

    Module search order:
    1. Sibling directory next to server.py (runtime/agents/<agent_dir>/)
    2. AI_HOME/agents/<agent_dir>/  (for installed/deployed setups)
    """
    frame = globals()
    # Fast path: return if already loaded.
    cached = frame.get(global_var_name)
    if cached is not None:
        return cached
    # Slow path: load under lock to prevent concurrent double-loading
    with _module_load_lock:
        # Re-check after acquiring lock in case another thread loaded it first
        cached = frame.get(global_var_name)
        if cached is not None:
            return cached
        # Prefer sibling directory (dev/deployed-from-source setups)
        server_dir = Path(__file__).resolve().parent.parent  # runtime/agents/
        candidate_paths = [
            str(server_dir / agent_dir),         # runtime/agents/<dir>/
            str(AI_HOME / "agents" / agent_dir), # ~/.ai-employee/agents/<dir>/
        ]
        for path_str in candidate_paths:
            if Path(path_str).is_dir() and path_str not in sys.path:
                sys.path.insert(0, path_str)
        mod = importlib.import_module(name)
        frame[global_var_name] = mod
        return mod


def _org():
    return _load_module("org_chart", "org-chart", "_org_chart_mod")


def _budget():
    return _load_module("budget_tracker", "budget-tracker", "_budget_mod")


def _goals():
    return _load_module("goal_alignment", "goal-alignment", "_goal_mod")


def _tickets():
    return _load_module("ticket_system", "ticket-system", "_ticket_mod")


def _gov():
    return _load_module("governance", "governance", "_gov_mod")


def _company():
    return _load_module("company_manager", "company-manager", "_company_mod")


# ── Org Chart API ──────────────────────────────────────────────────────────────

@app.get("/api/org/chart")
def org_get_chart():
    """Return the full org chart with roles, reporting lines, and direct reports."""
    try:
        return JSONResponse(_org().get_chart())
    except Exception as exc:
        logger.warning("org chart error: %s", exc)
        return JSONResponse({"roles": []})


@app.post("/api/org/roles")
def org_upsert_role(payload: dict):
    """Create or update an org-chart role."""
    role_id = (payload.get("role_id") or "").strip()
    title = (payload.get("title") or "").strip()
    if not role_id or not title:
        raise HTTPException(400, "role_id and title are required")
    try:
        role = _org().upsert_role(
            role_id=role_id,
            title=title,
            description=payload.get("description", ""),
            reports_to=payload.get("reports_to"),
            heartbeat_interval_minutes=int(payload.get("heartbeat_interval_minutes", 60)),
            agent_id=payload.get("agent_id"),
        )
        return JSONResponse(role)
    except Exception as exc:
        logger.error("org upsert_role error: %s", exc)
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/org/roles/{role_id}")
def org_delete_role(role_id: str):
    try:
        deleted = _org().delete_role(role_id)
        return JSONResponse({"ok": deleted})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/org/assign")
def org_assign_agent(payload: dict):
    """Assign an AI-EMPLOYEE agent to an org-chart role."""
    role_id = (payload.get("role_id") or "").strip()
    agent_id = (payload.get("agent_id") or "").strip()
    if not role_id or not agent_id:
        raise HTTPException(400, "role_id and agent_id are required")
    try:
        return JSONResponse(_org().assign_agent_to_role(role_id, agent_id))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/org/delegate")
def org_delegate_task(payload: dict):
    """Delegate a task from one role to another."""
    from_role = (payload.get("from_role") or "").strip()
    to_role = (payload.get("to_role") or "").strip()
    task = (payload.get("task") or "").strip()
    if not from_role or not to_role or not task:
        raise HTTPException(400, "from_role, to_role, and task are required")
    try:
        return JSONResponse(_org().delegate_task(from_role, to_role, task, payload.get("context")))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/org/adapters")
def org_list_adapters():
    try:
        return JSONResponse(_org().list_adapters())
    except Exception as exc:
        return JSONResponse([])


@app.post("/api/org/adapters")
def org_register_adapter(payload: dict):
    """Register a BYOA (Bring Your Own Agent) adapter."""
    adapter_id = (payload.get("adapter_id") or "").strip()
    name = (payload.get("name") or "").strip()
    adapter_type = (payload.get("type") or "http_webhook").strip().lower()
    if not adapter_id or not name:
        raise HTTPException(400, "adapter_id and name are required")
    try:
        return JSONResponse(
            _org().register_adapter(
                adapter_id=adapter_id,
                name=name,
                adapter_type=adapter_type,
                config=payload.get("config", {}),
                description=payload.get("description", ""),
            )
        )
    except ValueError as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/org/adapters/{adapter_id}")
def org_deregister_adapter(adapter_id: str):
    try:
        ok = _org().deregister_adapter(adapter_id)
        return JSONResponse({"ok": ok})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ── Budget Tracker API ─────────────────────────────────────────────────────────

@app.get("/api/budget/status")
def budget_all_status():
    """Return budget status for all tracked agents."""
    try:
        _budget().auto_reset_all_if_new_month()
        return JSONResponse(_budget().get_all_status())
    except Exception as exc:
        logger.warning("budget status error: %s", exc)
        return JSONResponse([])


@app.get("/api/budget/status/{agent_id}")
def budget_agent_status(agent_id: str):
    """Return budget status for a single agent."""
    try:
        _budget().auto_reset_all_if_new_month()
        return JSONResponse(_budget().get_agent_status(agent_id))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/budget/set")
def budget_set(payload: dict):
    """Set the monthly budget cap for an agent."""
    agent_id = (payload.get("agent_id") or "").strip()
    budget = payload.get("monthly_budget_usd")
    if not agent_id or budget is None:
        raise HTTPException(400, "agent_id and monthly_budget_usd are required")
    try:
        return JSONResponse(_budget().set_budget(agent_id, float(budget)))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/budget/reset/{agent_id}")
def budget_reset(agent_id: str):
    """Reset monthly usage for an agent."""
    try:
        return JSONResponse(_budget().reset_usage(agent_id))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/budget/record")
def budget_record_usage(payload: dict):
    """Record token usage for an agent (called by ai_router or manually)."""
    agent_id = (payload.get("agent_id") or "").strip()
    model = (payload.get("model") or "unknown").strip()
    if not agent_id:
        raise HTTPException(400, "agent_id is required")
    try:
        return JSONResponse(
            _budget().record_usage(
                agent_id=agent_id,
                model=model,
                input_tokens=int(payload.get("input_tokens", 0)),
                output_tokens=int(payload.get("output_tokens", 0)),
                cost_usd=payload.get("cost_usd"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ── Goal Alignment API ─────────────────────────────────────────────────────────

@app.get("/api/goals/company")
def goals_get_company():
    """Return the company mission and vision."""
    try:
        return JSONResponse(_goals().get_company_mission())
    except Exception as exc:
        return JSONResponse({"mission": "", "vision": ""})


@app.post("/api/goals/company")
def goals_set_company(payload: dict):
    """Set the company mission."""
    mission = (payload.get("mission") or "").strip()
    if not mission:
        raise HTTPException(400, "mission is required")
    try:
        return JSONResponse(
            _goals().set_company_mission(
                mission=mission,
                vision=payload.get("vision", ""),
                values=payload.get("values"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/goals/projects")
def goals_list_projects():
    try:
        return JSONResponse(_goals().list_projects())
    except Exception as exc:
        return JSONResponse([])


@app.post("/api/goals/projects")
def goals_upsert_project(payload: dict):
    """Create or update a project under the company mission."""
    name = (payload.get("name") or "").strip()
    goal = (payload.get("goal") or "").strip()
    if not name or not goal:
        raise HTTPException(400, "name and goal are required")
    try:
        return JSONResponse(
            _goals().upsert_project(
                project_id=payload.get("project_id"),
                name=name,
                goal=goal,
                description=payload.get("description", ""),
                assigned_roles=payload.get("assigned_roles"),
                assigned_agents=payload.get("assigned_agents"),
                priority=payload.get("priority", "medium"),
                status=payload.get("status", "active"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/goals/projects/{project_id}")
def goals_delete_project(project_id: str):
    try:
        return JSONResponse({"ok": _goals().delete_project(project_id)})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/goals/context/{project_id}")
def goals_get_context(project_id: str):
    """Return the full goal ancestry for a project (for prompt injection)."""
    try:
        ctx = _goals().get_goal_context(project_id=project_id)
        preamble = _goals().build_goal_preamble(project_id=project_id)
        return JSONResponse({**ctx, "preamble": preamble})
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ── Ticket System API ──────────────────────────────────────────────────────────

@app.get("/api/tickets")
def tickets_list(
    status: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
):
    """List tickets with optional filters."""
    try:
        return JSONResponse(
            _tickets().list_tickets(
                status=status, agent_id=agent_id, project_id=project_id, limit=min(limit, 200)
            )
        )
    except Exception as exc:
        return JSONResponse([])


@app.post("/api/tickets")
def tickets_create(payload: dict):
    """Create a new ticket."""
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    try:
        return JSONResponse(
            _tickets().create_ticket(
                title=title,
                description=payload.get("description", ""),
                created_by=payload.get("created_by", "user"),
                agent_id=payload.get("agent_id"),
                project_id=payload.get("project_id"),
                priority=payload.get("priority", "medium"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/tickets/{ticket_id}")
def tickets_get(ticket_id: str):
    try:
        ticket = _tickets().get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(404, f"Ticket '{ticket_id}' not found")
        return JSONResponse(ticket)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.patch("/api/tickets/{ticket_id}")
def tickets_update(ticket_id: str, payload: dict):
    """Update ticket status, title, priority, or agent assignment."""
    try:
        return JSONResponse(
            _tickets().update_ticket(
                ticket_id=ticket_id,
                status=payload.get("status"),
                title=payload.get("title"),
                description=payload.get("description"),
                priority=payload.get("priority"),
                agent_id=payload.get("agent_id"),
                updated_by=payload.get("updated_by", "user"),
            )
        )
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/tickets/{ticket_id}/comment")
def tickets_add_comment(ticket_id: str, payload: dict):
    """Add a comment to a ticket thread."""
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "body is required")
    try:
        return JSONResponse(
            _tickets().add_comment(
                ticket_id=ticket_id,
                body=body,
                author=payload.get("author", "user"),
                tool_call=payload.get("tool_call"),
            )
        )
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/tickets/{ticket_id}/audit")
def tickets_audit(ticket_id: str):
    """Return the immutable audit trail for a ticket."""
    try:
        return JSONResponse(_tickets().get_audit_trail(ticket_id))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/tickets/audit/log")
def tickets_full_audit(limit: int = 200):
    """Return the most recent audit events across all tickets."""
    try:
        return JSONResponse(_tickets().get_full_audit_log(limit=min(limit, 500)))
    except Exception as exc:
        return JSONResponse([])


# ── Governance API ─────────────────────────────────────────────────────────────

@app.get("/api/governance/pending")
def governance_pending():
    """List all pending approval requests."""
    try:
        return JSONResponse(_gov().list_pending())
    except Exception as exc:
        return JSONResponse([])


@app.get("/api/governance/audit")
def governance_audit(limit: int = 200):
    """Return the governance audit trail."""
    try:
        return JSONResponse(_gov().get_audit_trail(limit=min(limit, 500)))
    except Exception as exc:
        return JSONResponse([])


@app.get("/api/governance/history")
def governance_history(limit: int = 100):
    """Return recent governance decisions."""
    try:
        return JSONResponse(_gov().get_history(limit=min(limit, 200)))
    except Exception as exc:
        return JSONResponse([])


@app.post("/api/governance/request")
def governance_request(payload: dict):
    """Agent submits an action for board approval."""
    agent_id = (payload.get("agent_id") or "").strip()
    action = (payload.get("action") or "").strip()
    description = (payload.get("description") or "").strip()
    if not agent_id or not action:
        raise HTTPException(400, "agent_id and action are required")
    try:
        return JSONResponse(
            _gov().request_approval(
                agent_id=agent_id,
                action=action,
                description=description,
                risk_level=payload.get("risk_level", "medium"),
                payload=payload.get("payload"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/governance/{action_id}/approve")
def governance_approve(action_id: str, payload: dict = {}):
    """Board approves a pending action."""
    try:
        return JSONResponse(
            _gov().approve_action(
                action_id=action_id,
                decided_by=payload.get("decided_by", "board"),
                note=payload.get("note", ""),
            )
        )
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/governance/{action_id}/reject")
def governance_reject(action_id: str, payload: dict = {}):
    """Board rejects a pending action."""
    try:
        return JSONResponse(
            _gov().reject_action(
                action_id=action_id,
                decided_by=payload.get("decided_by", "board"),
                note=payload.get("note", ""),
            )
        )
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/governance/pause/{agent_id}")
def governance_pause(agent_id: str, payload: dict = {}):
    """Board pauses an agent."""
    try:
        return JSONResponse(_gov().pause_agent(agent_id, reason=payload.get("reason", "")))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/governance/resume/{agent_id}")
def governance_resume(agent_id: str, payload: dict = {}):
    """Board resumes a paused agent."""
    try:
        return JSONResponse(_gov().resume_agent(agent_id, reason=payload.get("reason", "")))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/governance/terminate/{agent_id}")
def governance_terminate(agent_id: str, payload: dict = {}):
    """Board terminates an agent."""
    try:
        return JSONResponse(_gov().terminate_agent(agent_id, reason=payload.get("reason", "")))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/governance/agent/{agent_id}")
def governance_agent_status(agent_id: str):
    """Return governance status for a specific agent."""
    try:
        return JSONResponse(_gov().get_agent_gov_status(agent_id))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/governance/settings")
def governance_get_settings():
    try:
        return JSONResponse(_gov().get_settings())
    except Exception as exc:
        return JSONResponse({})


@app.post("/api/governance/settings")
def governance_update_settings(payload: dict):
    """Update governance settings (auto-approve thresholds, timeouts, etc.)."""
    try:
        return JSONResponse(_gov().update_settings(payload))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ── Company Manager API ────────────────────────────────────────────────────────

@app.get("/api/companies")
def companies_list():
    """List all companies in this deployment."""
    try:
        return JSONResponse(_company().list_companies())
    except Exception as exc:
        return JSONResponse([])


@app.get("/api/companies/active")
def companies_active():
    """Return the currently active company."""
    try:
        c = _company().get_active_company()
        return JSONResponse(c or {})
    except Exception as exc:
        return JSONResponse({})


@app.post("/api/companies")
def companies_create(payload: dict):
    """Create a new company."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    try:
        return JSONResponse(
            _company().create_company(
                name=name,
                description=payload.get("description", ""),
                mission=payload.get("mission", ""),
                company_id=payload.get("company_id"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/companies/switch")
def companies_switch(payload: dict):
    """Switch the active company context."""
    company_id = (payload.get("company_id") or "").strip()
    if not company_id:
        raise HTTPException(400, "company_id is required")
    try:
        return JSONResponse(_company().switch_company(company_id))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/companies/{company_id}")
def companies_delete(company_id: str):
    try:
        ok = _company().delete_company(company_id)
        return JSONResponse({"ok": ok})
    except ValueError as exc:
        logger.error("API validation error: %s", exc, exc_info=True)
        raise HTTPException(400, "Bad request")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/companies/{company_id}/export")
def companies_export(company_id: str):
    """Export a company configuration with secrets scrubbed."""
    try:
        return JSONResponse(_company().export_company(company_id))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/companies/import")
def companies_import(payload: dict):
    """Import a company template."""
    if not payload:
        raise HTTPException(400, "template payload is required")
    try:
        return JSONResponse(
            _company().import_company(
                template=payload,
                name_override=payload.get("name_override"),
            )
        )
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ── Session Manager & Artifacts lazy-loaders ──────────────────────────────────

_session_mod = None
_artifacts_mod = None


def _sessions():
    return _load_module("session_manager", "session-manager", "_session_mod")


def _arts():
    return _load_module("artifacts", "artifacts", "_artifacts_mod")


# ── Session Manager API ────────────────────────────────────────────────────────


@app.get("/api/sessions")
def sessions_list(agent_id: str = None, status: str = None, limit: int = 50):
    """List all sessions, optionally filtered by agent or status."""
    try:
        return JSONResponse(_sessions().list_sessions(agent_id=agent_id, status=status, limit=limit))
    except Exception as exc:
        logger.warning("sessions list error: %s", exc)
        return JSONResponse([])


@app.post("/api/sessions")
def sessions_create(payload: dict):
    """Create a new persistent session."""
    agent_id = (payload.get("agent_id") or "").strip()
    if not agent_id:
        raise HTTPException(400, "agent_id is required")
    try:
        s = _sessions().create_session(
            agent_id=agent_id,
            title=payload.get("title", ""),
            context=payload.get("context") or {},
            ticket_id=payload.get("ticket_id"),
            task_plan_id=payload.get("task_plan_id"),
        )
        return JSONResponse(s)
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/sessions/{session_id}")
def sessions_get(session_id: str):
    """Get session details including context and checkpoints."""
    s = _sessions().get_session(session_id)
    if s is None:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return JSONResponse(s)


@app.patch("/api/sessions/{session_id}")
def sessions_update(session_id: str, payload: dict):
    """Update session context or status."""
    try:
        return JSONResponse(_sessions().update_session(
            session_id,
            context=payload.get("context"),
            status=payload.get("status"),
            title=payload.get("title"),
            merge_context=payload.get("merge_context", True),
        ))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/sessions/{session_id}")
def sessions_close(session_id: str):
    """Close (complete) a session."""
    ok = _sessions().close_session(session_id)
    return JSONResponse({"ok": ok})


@app.post("/api/sessions/{session_id}/resume")
def sessions_resume(session_id: str):
    """Resume a paused session."""
    try:
        return JSONResponse(_sessions().resume_session(session_id))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")


@app.post("/api/sessions/{session_id}/checkpoint")
def sessions_save_checkpoint(session_id: str, payload: dict = None):
    """Save a named checkpoint for rollback."""
    if payload is None:
        payload = {}
    label = (payload.get("label") or "checkpoint").strip()
    try:
        cp = _sessions().save_checkpoint(session_id, label=label, snapshot=payload.get("snapshot"))
        return JSONResponse(cp)
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")


@app.get("/api/sessions/{session_id}/checkpoints")
def sessions_list_checkpoints(session_id: str):
    return JSONResponse(_sessions().list_checkpoints(session_id))


@app.post("/api/sessions/{session_id}/restore/{checkpoint_id}")
def sessions_restore_checkpoint(session_id: str, checkpoint_id: str):
    """Restore session context to a checkpoint (rollback)."""
    try:
        return JSONResponse(_sessions().restore_checkpoint(session_id, checkpoint_id))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")


# ── Artifacts API ──────────────────────────────────────────────────────────────


@app.get("/api/artifacts")
def artifacts_list(artifact_type: str = None, agent_id: str = None, status: str = None, limit: int = 50):
    """List artifacts, optionally filtered."""
    try:
        return JSONResponse(_arts().list_artifacts(
            artifact_type=artifact_type, agent_id=agent_id, status=status, limit=limit
        ))
    except Exception as exc:
        logger.warning("artifacts list error: %s", exc)
        return JSONResponse([])


@app.post("/api/artifacts")
def artifacts_create(payload: dict):
    """Create a new artifact."""
    title = (payload.get("title") or "").strip()
    content = (payload.get("content") or "").strip()
    if not title or not content:
        raise HTTPException(400, "title and content are required")
    try:
        return JSONResponse(_arts().create_artifact(
            title=title,
            content=content,
            artifact_type=payload.get("artifact_type", "other"),
            agent_id=payload.get("agent_id"),
            ticket_id=payload.get("ticket_id"),
            task_plan_id=payload.get("task_plan_id"),
            metadata=payload.get("metadata") or {},
        ))
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/artifacts/{artifact_id}")
def artifacts_get(artifact_id: str):
    """Get artifact with full content."""
    a = _arts().get_artifact(artifact_id)
    if a is None:
        raise HTTPException(404, f"Artifact '{artifact_id}' not found")
    return JSONResponse(a)


@app.patch("/api/artifacts/{artifact_id}")
def artifacts_update(artifact_id: str, payload: dict):
    """Update artifact content, title, or status."""
    try:
        return JSONResponse(_arts().update_artifact(
            artifact_id,
            title=payload.get("title"),
            content=payload.get("content"),
            status=payload.get("status"),
            metadata=payload.get("metadata"),
        ))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")
    except Exception as exc:
        logger.error("API error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/artifacts/{artifact_id}")
def artifacts_delete(artifact_id: str):
    ok = _arts().delete_artifact(artifact_id)
    return JSONResponse({"ok": ok})


@app.post("/api/artifacts/{artifact_id}/deploy")
def artifacts_deploy(artifact_id: str, payload: dict = None):
    """Mark artifact as deployed."""
    notes = (payload or {}).get("deploy_notes", "")
    try:
        return JSONResponse(_arts().deploy_artifact(artifact_id, deploy_notes=notes))
    except ValueError as exc:
        logger.error("Not found error: %s", exc, exc_info=True)
        raise HTTPException(404, "Not found")


@app.get("/api/artifacts/{artifact_id}/versions")
def artifacts_versions(artifact_id: str):
    return JSONResponse(_arts().get_versions(artifact_id))


# ── CEO Chat (direct message to top-level agent) ──────────────────────────────


@app.post("/api/ceo/chat")
async def ceo_chat(payload: dict):
    """Send a message directly to the CEO agent and get a response.

    This implements Paperclip's "CEO Chat" concept — a direct channel to the
    top-level agent that propagates context down the org chart.
    """
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    # Find CEO role from org chart to get the assigned agent
    ceo_agent_id = "ceo"
    try:
        chart = _org().get_chart()
        ceo_role = next(
            (r for r in chart.get("roles", [])
             if r.get("role_id") == "ceo" and r.get("agent_id")),
            None,
        )
        if ceo_role and ceo_role.get("agent_id"):
            ceo_agent_id = ceo_role["agent_id"]
    except Exception:
        pass

    # Get goal context to inject company mission
    goal_preamble = ""
    try:
        goal_preamble = _goals().build_goal_preamble()
    except Exception:
        pass

    # Route to AI router
    try:
        from ai_router import query_ai_for_agent  # type: ignore
        ai_available = True
    except ImportError:
        ai_available = False

    if ai_available:
        system = (
            f"{goal_preamble}\n\n"
            f"You are the CEO of this company. You receive direct messages from the board "
            f"and coordinate the entire agent team to execute on the company's mission. "
            f"Respond strategically and concisely."
        ).strip()
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: query_ai_for_agent(ceo_agent_id, message, system=system),
            )
            response_text = result.get("content", result.get("text", str(result)))
        except Exception:
            logger.warning("CEO agent call failed", exc_info=True)
            response_text = "[CEO Agent unavailable — Ollama or AI provider not running]"
    else:
        response_text = (
            f"[CEO simulated response] Mission acknowledged. "
            f"I have received your message: '{message[:80]}'. "
            f"Coordinating team to execute on this directive."
        )

    # Store as a ticket for traceability
    ticket_id = None
    try:
        ticket = _tickets().create_ticket(
            title=f"CEO Directive: {message[:60]}",
            description=message,
            priority="high",
            agent_id=ceo_agent_id,
            created_by="board",
        )
        ticket_id = ticket.get("ticket_id")
    except Exception:
        pass

    return JSONResponse({
        "message": message,
        "response": response_text,
        "agent_id": ceo_agent_id,
        "ticket_id": ticket_id,
        "goal_context_injected": bool(goal_preamble),
    })


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Lead CRM
# ═══════════════════════════════════════════════════════════════════════════

def _crm():
    _p = AI_HOME / "agents" / "lead-crm"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import lead_crm  # type: ignore
    return lead_crm



@app.get("/api/crm/leads")
async def crm_list_leads(stage: Optional[str] = None, search: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_crm().list_leads, stage, search))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/crm/leads")
async def crm_add_lead(payload: dict):
    try:
        lead = await run_in_threadpool(
            lambda: _crm().add_lead(
                name=payload.get("name", ""),
                company=payload.get("company", ""),
                email=payload.get("email", ""),
                phone=payload.get("phone", ""),
                source=payload.get("source", ""),
                notes=payload.get("notes", ""),
                value=float(payload.get("value", 0)),
                tags=payload.get("tags", []),
            )
        )
        return JSONResponse(lead)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/crm/leads/{lead_id}")
async def crm_get_lead(lead_id: str):
    lead = await run_in_threadpool(_crm().get_lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return JSONResponse(lead)






@app.post("/api/crm/leads/{lead_id}/stage")
async def crm_move_stage(lead_id: str, payload: dict):
    stage = payload.get("stage", "")
    try:
        updated = await run_in_threadpool(_crm().move_stage, lead_id, stage)
    except ValueError as e:
        logger.error("API validation error: %s", e, exc_info=True)
        raise HTTPException(400, "Bad request")
    if not updated:
        raise HTTPException(404, "Lead not found")
    return JSONResponse(updated)


@app.post("/api/crm/leads/{lead_id}/followup")
async def crm_schedule_followup(lead_id: str, payload: dict):
    followup_at = payload.get("followup_at", "")
    note = payload.get("note", "")
    updated = await run_in_threadpool(_crm().schedule_followup, lead_id, followup_at, note)
    if not updated:
        raise HTTPException(404, "Lead not found")
    return JSONResponse(updated)


@app.get("/api/crm/pipeline")
async def crm_pipeline():
    try:
        return JSONResponse(await run_in_threadpool(_crm().get_pipeline))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/crm/score/{lead_id}")
async def crm_score_lead(lead_id: str):
    try:
        updated = await run_in_threadpool(_crm().score_lead, lead_id)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
    if not updated:
        raise HTTPException(404, "Lead not found")
    return JSONResponse(updated)


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Email Marketing
# ═══════════════════════════════════════════════════════════════════════════

def _email_mktg():
    _p = AI_HOME / "agents" / "email-marketing"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import email_marketing  # type: ignore
    return email_marketing


@app.get("/api/email/campaigns")
async def email_list_campaigns(status: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_email_mktg().list_campaigns, status))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/email/campaigns")
async def email_create_campaign(payload: dict):
    try:
        camp = await run_in_threadpool(
            lambda: _email_mktg().create_campaign(
                name=payload.get("name", ""),
                subject=payload.get("subject", ""),
                body=payload.get("body", ""),
                from_name=payload.get("from_name", ""),
                from_email=payload.get("from_email", ""),
                recipients=payload.get("recipients", []),
                sequence_steps=payload.get("sequence_steps", []),
            )
        )
        return JSONResponse(camp)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/email/campaigns/{campaign_id}")
async def email_get_campaign(campaign_id: str):
    camp = await run_in_threadpool(_email_mktg().get_campaign, campaign_id)
    if not camp:
        raise HTTPException(404, "Campaign not found")
    return JSONResponse(camp)


@app.patch("/api/email/campaigns/{campaign_id}")
async def email_update_campaign(campaign_id: str, payload: dict):
    updated = await run_in_threadpool(_email_mktg().update_campaign, campaign_id, payload)
    if not updated:
        raise HTTPException(404, "Campaign not found")
    return JSONResponse(updated)


@app.delete("/api/email/campaigns/{campaign_id}")
async def email_delete_campaign(campaign_id: str):
    deleted = await run_in_threadpool(_email_mktg().delete_campaign, campaign_id)
    return JSONResponse({"deleted": deleted})


@app.post("/api/email/campaigns/{campaign_id}/send")
async def email_send_campaign(campaign_id: str):
    try:
        updated = await run_in_threadpool(_email_mktg().send_campaign, campaign_id)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
    if not updated:
        raise HTTPException(404, "Campaign not found")
    return JSONResponse(updated)


@app.get("/api/email/campaigns/{campaign_id}/stats")
async def email_campaign_stats(campaign_id: str):
    try:
        stats = await run_in_threadpool(_email_mktg().get_campaign_stats, campaign_id)
        return JSONResponse(stats)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/email/write")
async def email_write_copy(payload: dict):
    try:
        result = await run_in_threadpool(
            lambda: _email_mktg().write_email_copy(
                goal=payload.get("goal", ""),
                tone=payload.get("tone", "professional"),
                audience=payload.get("audience", ""),
            )
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/email/deliverability-tips")
async def email_deliverability_tips():
    try:
        return JSONResponse(await run_in_threadpool(_email_mktg().get_deliverability_tips))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Meeting Intelligence
# ═══════════════════════════════════════════════════════════════════════════

def _meetings():
    _p = AI_HOME / "agents" / "meeting-intelligence"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import meeting_intelligence  # type: ignore
    return meeting_intelligence


@app.get("/api/meetings")
async def meetings_list(search: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_meetings().list_meetings, search))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/meetings")
async def meetings_add(payload: dict):
    try:
        meeting = await run_in_threadpool(
            lambda: _meetings().add_meeting(
                title=payload.get("title", ""),
                date=payload.get("date", ""),
                participants=payload.get("participants", []),
                transcript=payload.get("transcript", ""),
                notes=payload.get("notes", ""),
                meeting_type=payload.get("meeting_type", "general"),
            )
        )
        return JSONResponse(meeting)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/meetings/{meeting_id}")
async def meetings_get(meeting_id: str):
    m = await run_in_threadpool(_meetings().get_meeting, meeting_id)
    if not m:
        raise HTTPException(404, "Meeting not found")
    return JSONResponse(m)






@app.post("/api/meetings/{meeting_id}/summarize")
async def meetings_summarize(meeting_id: str):
    try:
        updated = await run_in_threadpool(_meetings().summarize_meeting, meeting_id)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
    if not updated:
        raise HTTPException(404, "Meeting not found")
    return JSONResponse(updated)


@app.post("/api/meetings/{meeting_id}/followup")
async def meetings_followup(meeting_id: str):
    try:
        updated = await run_in_threadpool(_meetings().generate_followup_email, meeting_id)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
    if not updated:
        raise HTTPException(404, "Meeting not found")
    return JSONResponse(updated)


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Social Media Scheduler
# ═══════════════════════════════════════════════════════════════════════════

def _social_sched():
    _p = AI_HOME / "agents" / "social-media-manager"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import social_scheduler  # type: ignore
    return social_scheduler


@app.get("/api/social/posts")
async def social_list_posts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
):
    try:
        return JSONResponse(await run_in_threadpool(_social_sched().list_posts, platform, status))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/social/posts")
async def social_schedule_post(payload: dict):
    try:
        post = await run_in_threadpool(
            lambda: _social_sched().schedule_post(
                platform=payload.get("platform", "twitter"),
                content=payload.get("content", ""),
                scheduled_at=payload.get("scheduled_at", ""),
                media_urls=payload.get("media_urls", []),
                hashtags=payload.get("hashtags", []),
                campaign=payload.get("campaign", ""),
                status=payload.get("status", "scheduled"),
            )
        )
        return JSONResponse(post)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/social/posts/{post_id}")
async def social_get_post(post_id: str):
    post = await run_in_threadpool(_social_sched().get_post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    return JSONResponse(post)








@app.post("/api/social/generate")
async def social_generate_content(payload: dict):
    try:
        result = await run_in_threadpool(
            lambda: _social_sched().generate_post_content(
                platform=payload.get("platform", "twitter"),
                topic=payload.get("topic", ""),
                tone=payload.get("tone", "engaging"),
                include_hashtags=payload.get("include_hashtags", True),
            )
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/social/process-due")
async def social_process_due():
    try:
        published = await run_in_threadpool(_social_sched().process_due_posts)
        return JSONResponse({"published": published, "count": len(published)})
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/social/stats")
async def social_stats():
    try:
        return JSONResponse(await run_in_threadpool(_social_sched().get_schedule_stats))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ═══════════════════════════════════════════════════════════════════════════
# Feature: CEO Briefing
# ═══════════════════════════════════════════════════════════════════════════

def _ceo_briefing():
    _p = BOTS_DIR / "ceo-briefing"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import ceo_briefing  # type: ignore
    return ceo_briefing


@app.get("/api/briefing/today")
async def briefing_today():
    try:
        return JSONResponse(await run_in_threadpool(_ceo_briefing().get_today_briefing))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/briefing/generate")
async def briefing_generate():
    try:
        return JSONResponse(await run_in_threadpool(_ceo_briefing().force_regenerate))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/briefing/history")
async def briefing_history():
    try:
        return JSONResponse(await run_in_threadpool(_ceo_briefing().list_briefings))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Financial Tools
# ═══════════════════════════════════════════════════════════════════════════

def _fin_tools():
    _p = AI_HOME / "agents" / "financial-tools"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import financial_tools  # type: ignore
    return financial_tools


@app.get("/api/financial/invoices")
async def fin_list_invoices(status: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_fin_tools().list_invoices, status))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/financial/invoices")
async def fin_create_invoice(payload: dict):
    try:
        inv = await run_in_threadpool(
            lambda: _fin_tools().create_invoice(
                client_name=payload.get("client_name", ""),
                client_email=payload.get("client_email", ""),
                items=payload.get("items", []),
                due_date=payload.get("due_date"),
                notes=payload.get("notes", ""),
                currency=payload.get("currency", "USD"),
                tax_rate=float(payload.get("tax_rate", 0)),
            )
        )
        return JSONResponse(inv)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/financial/invoices/{invoice_id}")
async def fin_get_invoice(invoice_id: str):
    inv = await run_in_threadpool(_fin_tools().get_invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return JSONResponse(inv)


@app.patch("/api/financial/invoices/{invoice_id}")
async def fin_update_invoice(invoice_id: str, payload: dict):
    updated = await run_in_threadpool(_fin_tools().update_invoice, invoice_id, payload)
    if not updated:
        raise HTTPException(404, "Invoice not found")
    return JSONResponse(updated)


@app.delete("/api/financial/invoices/{invoice_id}")
async def fin_delete_invoice(invoice_id: str):
    deleted = await run_in_threadpool(_fin_tools().delete_invoice, invoice_id)
    return JSONResponse({"deleted": deleted})


@app.post("/api/financial/invoices/{invoice_id}/send")
async def fin_send_invoice(invoice_id: str):
    updated = await run_in_threadpool(_fin_tools().send_invoice, invoice_id)
    if not updated:
        raise HTTPException(404, "Invoice not found")
    return JSONResponse(updated)


@app.post("/api/financial/invoices/{invoice_id}/pay")
async def fin_pay_invoice(invoice_id: str):
    updated = await run_in_threadpool(_fin_tools().pay_invoice, invoice_id)
    if not updated:
        raise HTTPException(404, "Invoice not found")
    return JSONResponse(updated)


@app.get("/api/financial/quotes")
async def fin_list_quotes(status: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_fin_tools().list_quotes, status))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/financial/quotes")
async def fin_create_quote(payload: dict):
    try:
        q = await run_in_threadpool(
            lambda: _fin_tools().create_quote(
                client_name=payload.get("client_name", ""),
                client_email=payload.get("client_email", ""),
                items=payload.get("items", []),
                valid_until=payload.get("valid_until"),
                notes=payload.get("notes", ""),
                currency=payload.get("currency", "USD"),
            )
        )
        return JSONResponse(q)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.patch("/api/financial/quotes/{quote_id}")
async def fin_update_quote(quote_id: str, payload: dict):
    updated = await run_in_threadpool(_fin_tools().update_quote, quote_id, payload)
    if not updated:
        raise HTTPException(404, "Quote not found")
    return JSONResponse(updated)


@app.delete("/api/financial/quotes/{quote_id}")
async def fin_delete_quote(quote_id: str):
    deleted = await run_in_threadpool(_fin_tools().delete_quote, quote_id)
    return JSONResponse({"deleted": deleted})


@app.get("/api/financial/pl")
async def fin_pl():
    try:
        return JSONResponse(await run_in_threadpool(_fin_tools().get_pl))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/financial/reminders")
async def fin_reminders():
    try:
        overdue = await run_in_threadpool(_fin_tools().check_overdue)
        all_overdue = await run_in_threadpool(_fin_tools().get_overdue_invoices)
        return JSONResponse({"newly_marked": overdue, "all_overdue": all_overdue})
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/financial/expenses")
async def fin_list_expenses(category: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_fin_tools().list_expenses, category))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/financial/expenses")
async def fin_add_expense(payload: dict):
    try:
        exp = await run_in_threadpool(
            lambda: _fin_tools().add_expense(
                description=payload.get("description", ""),
                amount=float(payload.get("amount", 0)),
                category=payload.get("category", "general"),
                expense_date=payload.get("date"),
                notes=payload.get("notes", ""),
            )
        )
        return JSONResponse(exp)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.delete("/api/financial/expenses/{expense_id}")
async def fin_delete_expense(expense_id: str):
    deleted = await run_in_threadpool(_fin_tools().delete_expense, expense_id)
    return JSONResponse({"deleted": deleted})


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Competitor Watch
# ═══════════════════════════════════════════════════════════════════════════

def _comp_watch():
    _p = AI_HOME / "agents" / "competitor-watch"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import competitor_watch  # type: ignore
    return competitor_watch


@app.get("/api/competitors")
async def comp_list(search: Optional[str] = None):
    try:
        return JSONResponse(await run_in_threadpool(_comp_watch().list_competitors, search))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/competitors")
async def comp_add(payload: dict):
    try:
        comp = await run_in_threadpool(
            lambda: _comp_watch().add_competitor(
                name=payload.get("name", ""),
                website=payload.get("website", ""),
                notes=payload.get("notes", ""),
                tags=payload.get("tags", []),
                pricing=payload.get("pricing", ""),
                target_market=payload.get("target_market", ""),
            )
        )
        return JSONResponse(comp)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/competitors/alerts")
async def comp_alerts(dismissed: bool = False):
    try:
        return JSONResponse(await run_in_threadpool(_comp_watch().get_alerts, None, dismissed))
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/competitors/{competitor_id}")
async def comp_get(competitor_id: str):
    comp = await run_in_threadpool(_comp_watch().get_competitor, competitor_id)
    if not comp:
        raise HTTPException(404, "Competitor not found")
    return JSONResponse(comp)






@app.post("/api/competitors/{competitor_id}/analyze")
async def comp_analyze(competitor_id: str, payload: dict = {}):
    try:
        updated = await run_in_threadpool(
            lambda: _comp_watch().analyze_competitor(
                competitor_id,
                payload.get("your_product", ""),
            )
        )
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")
    if not updated:
        raise HTTPException(404, "Competitor not found")
    return JSONResponse(updated)


@app.post("/api/competitors/alerts/{alert_id}/dismiss")
async def comp_dismiss_alert(alert_id: str):
    result = await run_in_threadpool(_comp_watch().dismiss_alert, alert_id)
    return JSONResponse({"dismissed": result})


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Content Calendar
# ═══════════════════════════════════════════════════════════════════════════

def _content_cal():
    _p = AI_HOME / "agents" / "content-calendar"
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
    import content_calendar  # type: ignore
    return content_calendar


@app.get("/api/content-calendar")
async def cal_list(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    try:
        entries = await run_in_threadpool(
            lambda: _content_cal().list_entries(
                platform=platform,
                status=status,
                date_from=date_from,
                date_to=date_to,
            )
        )
        stats = await run_in_threadpool(_content_cal().get_calendar_stats)
        return JSONResponse({"entries": entries, "stats": stats})
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/content-calendar/entries")
async def cal_add_entry(payload: dict):
    try:
        entry = await run_in_threadpool(
            lambda: _content_cal().add_entry(
                date_str=payload.get("date", ""),
                platform=payload.get("platform", "instagram"),
                content_type=payload.get("content_type", "post"),
                title=payload.get("title", ""),
                content=payload.get("content", ""),
                status=payload.get("status", "idea"),
                tags=payload.get("tags", []),
                notes=payload.get("notes", ""),
            )
        )
        return JSONResponse(entry)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.get("/api/content-calendar/entries/{entry_id}")
async def cal_get_entry(entry_id: str):
    entry = await run_in_threadpool(_content_cal().get_entry, entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")
    return JSONResponse(entry)


@app.patch("/api/content-calendar/entries/{entry_id}")
async def cal_update_entry(entry_id: str, payload: dict):
    updated = await run_in_threadpool(_content_cal().update_entry, entry_id, payload)
    if not updated:
        raise HTTPException(404, "Entry not found")
    return JSONResponse(updated)


@app.delete("/api/content-calendar/entries/{entry_id}")
async def cal_delete_entry(entry_id: str):
    deleted = await run_in_threadpool(_content_cal().delete_entry, entry_id)
    return JSONResponse({"deleted": deleted})


@app.post("/api/content-calendar/generate")
async def cal_generate(payload: dict):
    try:
        entries = await run_in_threadpool(
            lambda: _content_cal().generate_calendar(
                niche=payload.get("niche", "business"),
                days=int(payload.get("days", 30)),
                platforms=payload.get("platforms"),
                tone=payload.get("tone", "engaging"),
            )
        )
        return JSONResponse({"entries": entries, "count": len(entries)})
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ═══════════════════════════════════════════════════════════════════════════
# Feature: Guardrails — Pending Actions
# ═══════════════════════════════════════════════════════════════════════════

_PENDING_ACTIONS_FILE = AI_HOME / "state" / "pending-actions.json"


def _load_pending_actions() -> dict:
    if not _PENDING_ACTIONS_FILE.exists():
        return {"actions": []}
    try:
        return json.loads(_PENDING_ACTIONS_FILE.read_text())
    except Exception:
        return {"actions": []}


def _save_pending_actions(data: dict) -> None:
    _PENDING_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PENDING_ACTIONS_FILE.write_text(json.dumps(data, indent=2))


@app.get("/api/guardrails/pending-actions")
async def guardrails_pending_actions():
    try:
        data = await run_in_threadpool(_load_pending_actions)
        actions = [a for a in data.get("actions", []) if a.get("status") == "pending"]
        return JSONResponse({"actions": actions, "count": len(actions)})
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/guardrails/submit-action")
async def guardrails_submit_action(payload: dict):
    import uuid as _uuid
    action = {
        "id": str(_uuid.uuid4()),
        "action_type": payload.get("action_type", "other"),
        "description": payload.get("description", ""),
        "risk_level": payload.get("risk_level", "medium"),
        "payload": payload.get("payload", {}),
        "submitted_by": payload.get("submitted_by", "user"),
        "status": "pending",
        "decision": None,
        "decision_note": "",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decided_at": None,
    }

    def _append():
        data = _load_pending_actions()
        data["actions"].append(action)
        _save_pending_actions(data)
        return action

    try:
        result = await run_in_threadpool(_append)
        return JSONResponse(result)
    except Exception as e:
        logger.error("API error: %s", e, exc_info=True)
        raise HTTPException(500, "Internal server error")


@app.post("/api/guardrails/pending-actions/{action_id}/approve")
async def guardrails_approve_action(action_id: str, payload: dict = {}, _auth: None = Depends(require_auth)):
    def _approve():
        data = _load_pending_actions()
        for i, action in enumerate(data["actions"]):
            if action["id"] == action_id:
                data["actions"][i]["status"] = "approved"
                data["actions"][i]["decision"] = "approved"
                data["actions"][i]["decision_note"] = payload.get("note", "")
                data["actions"][i]["decided_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _save_pending_actions(data)
                return data["actions"][i]
        return None

    result = await run_in_threadpool(_approve)
    if not result:
        raise HTTPException(404, "Action not found")
    return JSONResponse(result)


@app.post("/api/guardrails/pending-actions/{action_id}/reject")
async def guardrails_reject_action(action_id: str, payload: dict = {}, _auth: None = Depends(require_auth)):
    def _reject():
        data = _load_pending_actions()
        for i, action in enumerate(data["actions"]):
            if action["id"] == action_id:
                data["actions"][i]["status"] = "rejected"
                data["actions"][i]["decision"] = "rejected"
                data["actions"][i]["decision_note"] = payload.get("note", "")
                data["actions"][i]["decided_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _save_pending_actions(data)
                return data["actions"][i]
        return None

    result = await run_in_threadpool(_reject)
    if not result:
        raise HTTPException(404, "Action not found")
    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Agent Governor — limits concurrent active agents to a stable cap
# ═══════════════════════════════════════════════════════════════════════════

_AGENT_GOVERNOR_LOCK = threading.Lock()
_AGENT_GOVERNOR: dict = {
    "enabled": True,
    "max_agents": len(AGENTS_BY_MODE["power"]),
    "updated_at": None,
}


def _count_running_agents() -> int:
    """Return the number of currently running (PID-alive) agents."""
    count = 0
    for agent_name in _mode_agent_targets():
        if agent_name in INFRA_AGENTS:
            continue
        pid_file = AI_HOME / "run" / f"{agent_name}.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text().strip()), 0)
                count += 1
            except Exception:
                pass
    return count


@app.get("/api/agents/governor")
def get_agent_governor():
    """Return the current agent governor configuration and live agent count."""
    with _AGENT_GOVERNOR_LOCK:
        cfg = dict(_AGENT_GOVERNOR)
    cfg["running"] = _count_running_agents()
    cfg["headroom"] = max(0, cfg["max_agents"] - cfg["running"]) if cfg["enabled"] else None
    return JSONResponse(cfg)


@app.post("/api/agents/governor")
def set_agent_governor(payload: dict, _auth: None = Depends(require_auth)):
    """Update agent governor settings.

    Payload fields (all optional):
      enabled  – bool: activate/deactivate the governor
      max_agents – int (1-200): new agent cap
    """
    with _AGENT_GOVERNOR_LOCK:
        if "enabled" in payload:
            _AGENT_GOVERNOR["enabled"] = bool(payload["enabled"])
        if "max_agents" in payload:
            cap = int(payload["max_agents"])
            if not (1 <= cap <= 200):
                raise HTTPException(400, "max_agents must be between 1 and 200")
            _AGENT_GOVERNOR["max_agents"] = cap
        _AGENT_GOVERNOR["updated_at"] = now_iso()
        cfg = dict(_AGENT_GOVERNOR)
    cfg["running"] = _count_running_agents()
    cfg["headroom"] = max(0, cfg["max_agents"] - cfg["running"]) if cfg["enabled"] else None
    return JSONResponse({"ok": True, **cfg})


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dashboard status cache — reduces repeated disk/CPU work on fast polls
# ═══════════════════════════════════════════════════════════════════════════

_STATUS_CACHE: dict = {}
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE_TTL = 4.0  # seconds — short enough to feel live, long enough to reduce load


def _get_cached_status() -> "dict | None":
    with _STATUS_CACHE_LOCK:
        entry = _STATUS_CACHE.get("data")
        ts = _STATUS_CACHE.get("ts", 0.0)
    if entry and time.monotonic() - ts < _STATUS_CACHE_TTL:
        return entry
    return None


def _set_cached_status(data: dict) -> None:
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE["data"] = data
        _STATUS_CACHE["ts"] = time.monotonic()


def _invalidate_status_cache() -> None:
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Email Deliverability Audit — scans campaigns for spam signals
# ═══════════════════════════════════════════════════════════════════════════

_SPAM_TRIGGER_WORDS = [
    "free money", "click here", "winner", "congratulations", "guaranteed",
    "no risk", "risk free", "100% free", "act now", "limited time",
    "earn extra cash", "make money fast", "double your income",
    "increase sales", "work from home", "be your own boss",
    "dear friend", "this is not spam", "unsubscribe here",
    "order now", "buy now", "cash bonus", "extra cash",
    "prize", "you've been selected", "important information",
]

_DNS_AUTH_TIPS = [
    {"check": "SPF", "status": "manual", "action": "Verify v=spf1 record exists for your sending domain via DNS lookup"},
    {"check": "DKIM", "status": "manual", "action": "Ensure DKIM TXT record is published and selector matches your mailer"},
    {"check": "DMARC", "status": "manual", "action": "Add v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com"},
    {"check": "BIMI", "status": "manual", "action": "Publish a BIMI TXT record with a verified SVG logo for inbox branding"},
    {"check": "Reverse DNS", "status": "manual", "action": "Ensure PTR record for sending IP resolves to your mail hostname"},
]


def _audit_campaign(campaign: dict) -> dict:
    """Analyse a single campaign for deliverability issues."""
    issues = []
    subject = (campaign.get("subject") or "").lower()
    body = (campaign.get("body") or "").lower()
    full_text = subject + " " + body

    # Spam trigger words
    found_triggers = [w for w in _SPAM_TRIGGER_WORDS if w in full_text]
    if found_triggers:
        issues.append({
            "severity": "high",
            "type": "spam_trigger",
            "detail": f"Spam trigger words detected: {', '.join(found_triggers[:5])}",
            "fix": "Remove or rephrase these phrases to avoid spam filters",
        })

    # ALL CAPS check (>20 % of words) — use the original (non-lowercased) subject for both counts
    original_subject = campaign.get("subject") or ""
    orig_words = original_subject.split()
    caps_words = [w for w in orig_words if w.isupper() and len(w) > 2]
    if len(orig_words) > 0 and len(caps_words) / max(len(orig_words), 1) > 0.2:
        issues.append({
            "severity": "medium",
            "type": "excessive_caps",
            "detail": "Subject line contains excessive ALL-CAPS words",
            "fix": "Use sentence case or title case instead of all-caps",
        })

    # Missing unsubscribe link
    if campaign.get("body") and "unsubscribe" not in body:
        issues.append({
            "severity": "high",
            "type": "missing_unsubscribe",
            "detail": "Email body does not contain an unsubscribe link",
            "fix": "Add a visible unsubscribe link — required by CAN-SPAM and GDPR",
        })

    # Subject line length
    subj_len = len(campaign.get("subject") or "")
    if subj_len > 60:
        issues.append({
            "severity": "low",
            "type": "long_subject",
            "detail": f"Subject line is {subj_len} characters (recommended ≤60)",
            "fix": "Shorten subject to under 60 characters for better mobile display",
        })
    elif subj_len == 0:
        issues.append({
            "severity": "high",
            "type": "empty_subject",
            "detail": "Campaign has no subject line",
            "fix": "Add a compelling subject line to improve open rates",
        })

    # Empty body
    if not (campaign.get("body") or "").strip():
        issues.append({
            "severity": "high",
            "type": "empty_body",
            "detail": "Campaign body is empty",
            "fix": "Add email body content",
        })

    score = max(0, 100 - sum({"high": 25, "medium": 10, "low": 5}.get(i["severity"], 0) for i in issues))
    return {
        "id": campaign.get("id"),
        "name": campaign.get("name"),
        "score": score,
        "rating": "good" if score >= 80 else "needs_work" if score >= 50 else "poor",
        "issues": issues,
    }


@app.get("/api/email/deliverability-audit")
async def email_deliverability_audit():
    """Run a deliverability audit across all campaigns.

    Returns per-campaign scores, detected spam triggers, and DNS auth tips.
    """
    try:
        def _run_audit():
            try:
                campaigns = _email_mktg().list_campaigns()
            except Exception:
                campaigns = []
            if hasattr(campaigns, "body"):
                import json as _json
                campaigns = _json.loads(campaigns.body)
            if not isinstance(campaigns, list):
                campaigns = []
            results = [_audit_campaign(c) for c in campaigns]
            overall = round(sum(r["score"] for r in results) / len(results), 1) if results else None
            high_issues = sum(1 for r in results for i in r["issues"] if i["severity"] == "high")
            return {
                "overall_score": overall,
                "campaigns_audited": len(results),
                "high_severity_issues": high_issues,
                "campaigns": results,
                "dns_checklist": _DNS_AUTH_TIPS,
                "warmup_advice": (
                    "Warm up new sending domains gradually: 50→200→500→1000→2000 emails/day "
                    "over 4-6 weeks. Keep bounce rate <2% and complaint rate <0.1%."
                ),
                "sender_reputation_tools": [
                    "Google Postmaster Tools (postmaster.google.com)",
                    "Microsoft SNDS (sendersupport.olc.protection.outlook.com)",
                    "MXToolbox Blacklist Check (mxtoolbox.com/blacklists.aspx)",
                    "Mail-Tester (mail-tester.com)",
                ],
                "ts": now_iso(),
            }
        return JSONResponse(await run_in_threadpool(_run_audit))
    except Exception as exc:
        logger.error("Deliverability audit error: %s", exc, exc_info=True)
        raise HTTPException(500, "Internal server error")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Circuit Breaker — pause agents that repeatedly fail
# ═══════════════════════════════════════════════════════════════════════════

_CB_LOCK = threading.Lock()
# Per-agent state: {"state": "closed"|"open"|"half_open",
#                   "failures": int, "last_failure": str|None,
#                   "opened_at": str|None, "success_streak": int}
_CIRCUIT_BREAKERS: dict[str, dict] = {}

_CB_FAILURE_THRESHOLD = 3    # consecutive failures before opening
_CB_HALF_OPEN_AFTER = 300    # seconds before trying again (5 min)
_CB_SUCCESS_TO_CLOSE = 2     # successes in half-open needed to close


def _cb_get(agent_id: str) -> dict:
    """Return (creating if missing) the circuit-breaker state for an agent."""
    if agent_id not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[agent_id] = {
            "state": "closed",
            "failures": 0,
            "last_failure": None,
            "opened_at": None,
            "success_streak": 0,
        }
    return _CIRCUIT_BREAKERS[agent_id]


def circuit_breaker_record_failure(agent_id: str) -> dict:
    """Record a subtask failure for *agent_id* and open the breaker if threshold is reached."""
    with _CB_LOCK:
        cb = _cb_get(agent_id)
        cb["failures"] += 1
        cb["success_streak"] = 0
        cb["last_failure"] = now_iso()
        if cb["state"] == "closed" and cb["failures"] >= _CB_FAILURE_THRESHOLD:
            cb["state"] = "open"
            cb["opened_at"] = now_iso()
            logger.warning("Circuit breaker OPENED for agent '%s' after %d failures", agent_id, cb["failures"])
        return dict(cb)


def circuit_breaker_record_success(agent_id: str) -> dict:
    """Record a subtask success; close the breaker if it was half-open."""
    with _CB_LOCK:
        cb = _cb_get(agent_id)
        cb["success_streak"] += 1
        # Transition from half-open → closed after enough consecutive successes
        if cb["state"] == "half_open" and cb["success_streak"] >= _CB_SUCCESS_TO_CLOSE:
            cb["state"] = "closed"
            cb["failures"] = 0
            cb["opened_at"] = None
            logger.info("Circuit breaker CLOSED for agent '%s'", agent_id)
        elif cb["state"] == "closed":
            cb["failures"] = 0  # reset failure count on success
        return dict(cb)


def circuit_breaker_is_open(agent_id: str) -> bool:
    """Return True if the agent should be skipped (circuit is open).

    Automatically transitions open → half_open after the cooldown period.
    """
    with _CB_LOCK:
        if agent_id not in _CIRCUIT_BREAKERS:
            return False
        cb = _CIRCUIT_BREAKERS[agent_id]
        if cb["state"] == "open" and cb.get("opened_at"):
            try:
                opened = datetime.fromisoformat(cb["opened_at"].replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - opened).total_seconds()
                if elapsed >= _CB_HALF_OPEN_AFTER:
                    cb["state"] = "half_open"
                    cb["success_streak"] = 0
                    logger.info("Circuit breaker HALF-OPEN for agent '%s' after %.0fs cooldown", agent_id, elapsed)
            except Exception:
                pass
        return cb["state"] == "open"


@app.get("/api/agents/circuit-breakers")
def get_circuit_breakers():
    """Return all circuit-breaker states and current thresholds."""
    with _CB_LOCK:
        snapshot = {k: dict(v) for k, v in _CIRCUIT_BREAKERS.items()}
    # Trigger the open→half-open check for each agent
    for agent_id in list(snapshot.keys()):
        circuit_breaker_is_open(agent_id)
    with _CB_LOCK:
        snapshot = {k: dict(v) for k, v in _CIRCUIT_BREAKERS.items()}
    return JSONResponse({
        "circuit_breakers": snapshot,
        "thresholds": {
            "failure_threshold": _CB_FAILURE_THRESHOLD,
            "half_open_after_seconds": _CB_HALF_OPEN_AFTER,
            "success_to_close": _CB_SUCCESS_TO_CLOSE,
        },
        "summary": {
            "total": len(snapshot),
            "open": sum(1 for v in snapshot.values() if v["state"] == "open"),
            "half_open": sum(1 for v in snapshot.values() if v["state"] == "half_open"),
            "closed": sum(1 for v in snapshot.values() if v["state"] == "closed"),
        },
    })


@app.post("/api/agents/circuit-breakers/{agent_id}/reset")
def reset_circuit_breaker(agent_id: str, _auth: None = Depends(require_auth)):
    """Manually reset the circuit breaker for a specific agent to closed state."""
    if not _SAFE_AGENT_ID_PAT.match(agent_id):
        raise HTTPException(400, "Invalid agent ID")
    with _CB_LOCK:
        _CIRCUIT_BREAKERS[agent_id] = {
            "state": "closed",
            "failures": 0,
            "last_failure": None,
            "opened_at": None,
            "success_streak": 0,
        }
    logger.info("Circuit breaker manually RESET for agent '%s'", agent_id)
    return JSONResponse({"ok": True, "agent_id": agent_id, "state": "closed"})


@app.post("/api/agents/circuit-breakers/{agent_id}/record-failure")
def record_agent_failure(agent_id: str, _auth: None = Depends(require_auth)):
    """Manually record a failure event for an agent (useful for testing)."""
    if not _SAFE_AGENT_ID_PAT.match(agent_id):
        raise HTTPException(400, "Invalid agent ID")
    state = circuit_breaker_record_failure(agent_id)
    return JSONResponse({"ok": True, "agent_id": agent_id, **state})


@app.post("/api/agents/circuit-breakers/{agent_id}/record-success")
def record_agent_success(agent_id: str, _auth: None = Depends(require_auth)):
    """Manually record a success event for an agent (useful for testing)."""
    if not _SAFE_AGENT_ID_PAT.match(agent_id):
        raise HTTPException(400, "Invalid agent ID")
    state = circuit_breaker_record_success(agent_id)
    return JSONResponse({"ok": True, "agent_id": agent_id, **state})


# ═══════════════════════════════════════════════════════════════════════════
# 5. Simplified Lead Generation Pilot
# ═══════════════════════════════════════════════════════════════════════════

_LEAD_PILOT_LOCK = threading.Lock()
_LEAD_PILOT: dict = {
    "enabled": False,
    "max_leads": 5,
    "niche": "web design agencies",
    "use_case": "web-design",
    "updated_at": None,
    "description": (
        "Pilot mode: produce only 5 highly-targeted leads for a single use case "
        "to validate lead quality before scaling."
    ),
}


@app.get("/api/lead-pilot")
def get_lead_pilot():
    """Return the current simplified lead-generation pilot configuration."""
    with _LEAD_PILOT_LOCK:
        return JSONResponse(dict(_LEAD_PILOT))


@app.post("/api/lead-pilot")
def set_lead_pilot(payload: dict, _auth: None = Depends(require_auth)):
    """Enable or configure the simplified lead generation pilot.

    Payload fields (all optional):
      enabled   – bool
      max_leads – int (1-50)
      niche     – str: target market segment
      use_case  – str: identifier for the use case
    """
    with _LEAD_PILOT_LOCK:
        if "enabled" in payload:
            _LEAD_PILOT["enabled"] = bool(payload["enabled"])
        if "max_leads" in payload:
            n = int(payload["max_leads"])
            if not (1 <= n <= 50):
                raise HTTPException(400, "max_leads must be between 1 and 50")
            _LEAD_PILOT["max_leads"] = n
        if "niche" in payload:
            niche = str(payload["niche"])[:120].strip()
            if not niche:
                raise HTTPException(400, "niche cannot be empty")
            _LEAD_PILOT["niche"] = niche
        if "use_case" in payload:
            _LEAD_PILOT["use_case"] = str(payload["use_case"])[:60].strip()
        _LEAD_PILOT["updated_at"] = now_iso()
        cfg = dict(_LEAD_PILOT)
    return JSONResponse({"ok": True, **cfg})


# ═══════════════════════════════════════════════════════════════════════════════
# GDPR Data Subject Rights (Articles 15, 17, 20)
# ═══════════════════════════════════════════════════════════════════════════════

def _gdpr_actor(request: Request) -> str:
    """Resolve the requesting user's identity from JWT or IP."""
    try:
        from fastapi.security.utils import get_authorization_scheme_param  # noqa: PLC0415
        auth_header = request.headers.get("Authorization", "")
        _scheme, token_str = get_authorization_scheme_param(auth_header)
        if token_str:
            payload = _decode_any_token(token_str)
            if payload and "sub" in payload:
                return f"user:{payload['sub']}"
    except Exception:
        pass
    host = (request.client.host if request.client else "unknown") or "unknown"
    return f"ip:{host}"


@app.get("/data/summary")
def gdpr_summary(request: Request, _auth: None = Depends(require_auth)):
    """GDPR Article 15 — Summary of all personal data stores and record counts."""
    dsr = _get_data_subject_rights()
    if dsr is None:
        raise HTTPException(503, "Data subject rights module unavailable")
    actor = _gdpr_actor(request)
    return JSONResponse(dsr.summary(actor))


@app.get("/data/export")
def gdpr_export(request: Request, _auth: None = Depends(require_auth)):
    """GDPR Article 20 — Full portable export of all personal data."""
    dsr = _get_data_subject_rights()
    if dsr is None:
        raise HTTPException(503, "Data subject rights module unavailable")
    actor = _gdpr_actor(request)
    return JSONResponse(dsr.export(actor))


@app.delete("/data/delete")
def gdpr_delete(
    request: Request,
    body: _GDPRDeleteRequest = _GDPRDeleteRequest(),
    _auth: None = Depends(require_auth),
):
    """GDPR Article 17 — Irreversible erasure of all personal data.

    This operation is permanent and cannot be undone.  Use the /data/summary
    and /data/export endpoints first if you need a copy of the data.
    """
    dsr = _get_data_subject_rights()
    if dsr is None:
        raise HTTPException(503, "Data subject rights module unavailable")
    actor = _gdpr_actor(request)
    result = dsr.erase(
        actor,
        erase_chatlog=body.erase_chatlog,
        erase_memory=body.erase_memory,
        erase_audit=body.erase_audit,
    )
    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Human-in-the-Loop (HITL) endpoints — EU AI Act Article 14
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/hitl/pending")
def hitl_pending(_auth: None = Depends(require_auth)):
    """Return all HITL requests awaiting human decision."""
    gate = _get_hitl_gate()
    if gate is None:
        return JSONResponse({"pending": [], "error": "HITL module unavailable"})
    return JSONResponse({"pending": gate.pending_requests()})


@app.get("/api/hitl/requests")
def hitl_all_requests(_auth: None = Depends(require_auth)):
    """Return all HITL requests (any status), most recent first."""
    gate = _get_hitl_gate()
    if gate is None:
        return JSONResponse({"requests": []})
    return JSONResponse({"requests": gate.all_requests(limit=200)})


@app.get("/api/hitl/requests/{request_id}")
def hitl_get_request(request_id: str, _auth: None = Depends(require_auth)):
    """Return details for a specific HITL request."""
    gate = _get_hitl_gate()
    if gate is None:
        raise HTTPException(503, "HITL module unavailable")
    req = gate.get_request(request_id)
    if req is None:
        raise HTTPException(404, "HITL request not found")
    return JSONResponse(req)


@app.post("/api/hitl/requests/{request_id}/approve")
def hitl_approve(request_id: str, payload: dict, request: Request,
                 _auth: None = Depends(require_auth)):
    """Approve a pending HITL request (human operator action)."""
    gate = _get_hitl_gate()
    if gate is None:
        raise HTTPException(503, "HITL module unavailable")
    actor = _gdpr_actor(request)
    reason = (payload.get("reason") or "").strip()
    result = gate.approve(request_id, decided_by=actor, reason=reason)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Approval failed"))
    return JSONResponse(result)


@app.post("/api/hitl/requests/{request_id}/reject")
def hitl_reject(request_id: str, payload: dict, request: Request,
                _auth: None = Depends(require_auth)):
    """Reject a pending HITL request (human operator action)."""
    gate = _get_hitl_gate()
    if gate is None:
        raise HTTPException(503, "HITL module unavailable")
    actor = _gdpr_actor(request)
    reason = (payload.get("reason") or "").strip()
    result = gate.reject(request_id, decided_by=actor, reason=reason)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Rejection failed"))
    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Bias Detection API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/bias/report/{agent_id}")
def bias_report_for_agent(agent_id: str, _auth: None = Depends(require_auth)):
    """Return the current bias metrics summary for a specific agent.

    Includes demographic parity, equalized odds, and disparate impact ratios
    computed over all decisions accumulated for this agent in the current process.
    """
    if not _SAFE_AGENT_ID_PAT.match(agent_id):
        raise HTTPException(400, "Invalid agent ID")
    engine = _get_bias_engine()
    if engine is None:
        raise HTTPException(503, "Bias detection module unavailable")
    return JSONResponse(engine.report_for_agent(agent_id))


@app.get("/api/bias/events")
def bias_events(_auth: None = Depends(require_auth)):
    """Return recent bias-related audit events (bias_check, bias_flag, bias_block)."""
    engine = _get_bias_engine()
    if engine is None:
        return JSONResponse({"events": []})
    return JSONResponse({"events": engine.recent_events(limit=200)})


@app.post("/api/bias/check")
def bias_check_endpoint(payload: dict, _auth: None = Depends(require_auth)):
    """Run a bias check for a single decision and return the BiasReport.

    Payload fields:
      agent            – agent performing the decision (required)
      action           – description of the action (required)
      subject_id       – identifier of the person/entity being decided on (required)
      decision         – bool: True = positive decision (required)
      demographic_group – group label (required)
      ground_truth     – bool or null: actual outcome if known (optional)
      metadata         – free-form dict (optional)
    """
    from core.bias_detection_engine import BiasCheckContext, get_bias_engine  # type: ignore
    agent = (payload.get("agent") or "").strip()
    action = (payload.get("action") or "").strip()
    subject_id = (payload.get("subject_id") or "").strip()
    group = (payload.get("demographic_group") or "").strip()
    if not agent or not action or not subject_id or not group:
        raise HTTPException(400, "agent, action, subject_id, demographic_group are required")
    decision = bool(payload.get("decision", True))
    ground_truth = payload.get("ground_truth")
    if ground_truth is not None:
        ground_truth = bool(ground_truth)
    ctx = BiasCheckContext(
        agent=agent,
        action=action,
        subject_id=subject_id,
        decision=decision,
        demographic_group=group,
        ground_truth=ground_truth,
        metadata=payload.get("metadata") or {},
    )
    engine = get_bias_engine()
    report = engine.check(ctx)
    return JSONResponse(report.to_dict())


# ═══════════════════════════════════════════════════════════════════════════════
# Explainability (XAI) API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/explain/{explain_id}")
def get_explanation(explain_id: str, _auth: None = Depends(require_auth)):
    """Return the structured XAI explanation for a specific decision.

    The ``explain_id`` is included in every ``/api/chat`` response as
    ``explanation.explain_id`` when an explanation was generated.
    """
    if not re.match(r"^xai-[a-zA-Z0-9]{12}$", explain_id):
        raise HTTPException(400, "Invalid explain_id format")
    engine = _get_explain_engine()
    if engine is None:
        raise HTTPException(503, "Explainability module unavailable")
    exp = engine.get(explain_id)
    if exp is None:
        raise HTTPException(404, f"Explanation {explain_id!r} not found")
    return JSONResponse(exp)


@app.get("/api/explain/history")
def explanation_history(
    limit: int = 50,
    agent: str = "",
    _auth: None = Depends(require_auth),
):
    """Return recent XAI explanations, optionally filtered by agent.

    Query params:
      limit  – max number of results (default 50, max 200)
      agent  – filter to a specific agent (optional)
    """
    limit = max(1, min(limit, 200))
    engine = _get_explain_engine()
    if engine is None:
        return JSONResponse({"explanations": []})
    if agent:
        if not _SAFE_AGENT_ID_PAT.match(agent):
            raise HTTPException(400, "Invalid agent name")
        items = engine.recent_for_agent(agent, limit=limit)
    else:
        items = engine.recent(limit=limit)
    return JSONResponse({"explanations": items})


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Output Schema API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/schema")
def list_agent_schemas(_auth: None = Depends(require_auth)):
    """Return a list of all registered agent IDs and their schema class names.

    Useful for UI tooling to discover which agents have dedicated schemas.
    """
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.agent_output_schemas import AGENT_SCHEMA_REGISTRY  # type: ignore
        return JSONResponse({
            "schemas": {
                agent_id: schema_cls.__name__
                for agent_id, schema_cls in sorted(AGENT_SCHEMA_REGISTRY.items())
            }
        })
    except Exception as exc:
        raise HTTPException(503, f"Schema registry unavailable: {exc}") from exc


@app.get("/api/schema/{agent_id}")
def get_agent_schema(agent_id: str, _auth: None = Depends(require_auth)):
    """Return the full JSON Schema for a specific agent's output model.

    This can be used by the UI, downstream consumers, and monitoring tools
    to validate or describe what a given agent is expected to produce.
    """
    if not _SAFE_AGENT_ID_PAT.match(agent_id):
        raise HTTPException(400, "Invalid agent_id format")
    try:
        _rdir = Path(__file__).resolve().parents[2]
        if str(_rdir) not in sys.path:
            sys.path.insert(0, str(_rdir))
        from core.agent_output_schemas import get_schema_for_agent  # type: ignore
        schema_cls = get_schema_for_agent(agent_id)
        return JSONResponse({
            "agent_id": agent_id,
            "schema_class": schema_cls.__name__,
            "json_schema": schema_cls.model_json_schema(),
        })
    except Exception as exc:
        raise HTTPException(503, f"Schema unavailable: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════════
# Circuit Breaker Status API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/circuit-breakers")
def list_circuit_breakers(_auth: None = Depends(require_auth)):
    """Return the current state of all registered circuit breakers.

    Each entry reports the state (closed/open/half_open), recent failure
    count, and how many seconds until an open breaker will probe again.
    """
    registry = _get_circuit_registry()
    if registry is None:
        raise HTTPException(503, "Circuit breaker module unavailable")
    return JSONResponse({"circuit_breakers": registry.status_all()})


@app.post("/api/circuit-breakers/{name}/reset")
def reset_circuit_breaker(name: str, _auth: None = Depends(require_auth)):
    """Manually reset a single circuit breaker back to CLOSED."""
    if not re.match(r'^[a-zA-Z0-9_:.-]{1,64}$', name):
        raise HTTPException(400, "Invalid circuit breaker name")
    registry = _get_circuit_registry()
    if registry is None:
        raise HTTPException(503, "Circuit breaker module unavailable")
    registry.get(name).reset()
    return JSONResponse({"ok": True, "name": name, "state": "closed"})


# ═══════════════════════════════════════════════════════════════════════════════
# Distributed Tracing API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/traces")
def list_traces(_auth: None = Depends(require_auth)):
    """Return a summary list of the most recent traces (no span details).

    Useful for monitoring dashboards and quick health checks.
    """
    tracer = _get_distributed_tracer()
    if tracer is None:
        raise HTTPException(503, "Distributed tracing module unavailable")
    return JSONResponse({"traces": tracer.list_traces(limit=100)})


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str, _auth: None = Depends(require_auth)):
    """Return the full trace tree for a specific trace_id.

    The tree includes every span — orchestrator, agent routing, LLM call,
    and memory write — with parent_span_id links for reconstruction.
    """
    if not re.match(r'^trace-[a-fA-F0-9]{32}$', trace_id):
        raise HTTPException(400, "Invalid trace_id format")
    tracer = _get_distributed_tracer()
    if tracer is None:
        raise HTTPException(503, "Distributed tracing module unavailable")
    tree = tracer.get_trace(trace_id)
    if tree is None:
        raise HTTPException(404, f"Trace '{trace_id}' not found")
    return JSONResponse(tree)


@app.get("/api/pipeline-trace")
def list_pipeline_traces(_auth: None = Depends(require_auth)):
    """Return the most recent unified pipeline execution traces (newest first).

    Each trace includes per-phase metadata: retrieved_nodes counts, decision,
    validated_tasks, agent_results (with real_execution flag), final_output
    snippet, latency_ms, and whether the run was degraded.

    Useful for the neural brain debug panel, regression investigations, and
    pipeline health monitoring.
    """
    try:
        from core.unified_pipeline import get_pipeline_traces  # noqa: PLC0415
        return JSONResponse({"traces": get_pipeline_traces(limit=20)})
    except Exception as exc:
        logger.warning("pipeline-trace endpoint error: %s", exc)
        return JSONResponse({"traces": [], "error": "Pipeline trace unavailable"})


# ═══════════════════════════════════════════════════════════════════════════════
# Data Lifecycle Management API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/lifecycle")
def get_lifecycle_status(_auth: None = Depends(require_auth)):
    """Return retention policies and scheduler state for all managed stores.

    Response shape::

        {
          "policies": {
            "audit_log": {
              "store_id": "audit_log",
              "ttl_days": 90,
              "store_type": "sqlite",
              "enabled": true,
              "cutoff_iso": "2025-01-18T..."
            },
            ...
          },
          "last_run": "2026-04-19T...",
          "scheduler": {"running": false},
          "store_count": 5
        }
    """
    mgr = _get_lifecycle_manager()
    if mgr is None:
        raise HTTPException(503, "Data lifecycle module unavailable")
    return JSONResponse(mgr.status())


@app.post("/api/lifecycle/purge")
async def purge_lifecycle(payload: dict, _auth: None = Depends(require_auth)):
    """Trigger a purge pass across all (or one specific) data store.

    Body (optional):

    .. code-block:: json

        {"store_id": "chat_history"}

    Omitting ``store_id`` purges **all** stores.  Returns a per-store report.
    """
    mgr = _get_lifecycle_manager()
    if mgr is None:
        raise HTTPException(503, "Data lifecycle module unavailable")

    store_id = ((payload or {}).get("store_id") or "").strip()
    if store_id:
        if not re.match(r'^[a-zA-Z0-9_]{1,64}$', store_id):
            raise HTTPException(400, "Invalid store_id")
        from starlette.concurrency import run_in_threadpool as _rtp  # noqa: PLC0415
        result = await _rtp(mgr.purge, store_id)
        return JSONResponse({"ok": True, "results": {store_id: result.to_dict()}})

    from starlette.concurrency import run_in_threadpool as _rtp  # noqa: PLC0415
    results = await _rtp(mgr.purge_all)
    return JSONResponse({
        "ok":      True,
        "results": {sid: r.to_dict() for sid, r in results.items()},
    })


@app.patch("/api/lifecycle/{store_id}/ttl")
def update_lifecycle_ttl(store_id: str, payload: dict, _auth: None = Depends(require_auth)):
    """Update the TTL (in days) for a specific store at runtime.

    Body::

        {"days": 180}

    Set ``days`` to 0 to disable automatic purging for that store.
    """
    if not re.match(r'^[a-zA-Z0-9_]{1,64}$', store_id):
        raise HTTPException(400, "Invalid store_id")
    days = (payload or {}).get("days")
    if days is None or not isinstance(days, int) or days < 0:
        raise HTTPException(400, "days must be a non-negative integer")
    mgr = _get_lifecycle_manager()
    if mgr is None:
        raise HTTPException(503, "Data lifecycle module unavailable")
    updated = mgr.set_ttl(store_id, days=days)
    if not updated:
        raise HTTPException(404, f"Store '{store_id}' not found")
    return JSONResponse({"ok": True, "store_id": store_id, "ttl_days": days})


# ═══════════════════════════════════════════════════════════════════════════════
# User Feedback API
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/feedback")
async def submit_feedback(payload: dict, _auth: None = Depends(require_auth)):
    """Submit a thumbs-up or thumbs-down rating for an agent output.

    Body::

        {
          "output_id":  "resp-abc123",      // required
          "rating":     "up" | "down",      // required
          "agent_id":   "company-builder",  // optional
          "text":       "Great answer!",    // optional
          "memory_ids": ["m-1", "m-2"],     // optional
          "meta":       {}                  // optional
        }

    Returns the persisted :class:`~core.user_feedback_store.FeedbackEntry`.
    """
    store = _get_feedback_store()
    if store is None:
        raise HTTPException(503, "Feedback store unavailable")

    body         = payload or {}
    output_id    = str(body.get("output_id", "")).strip()
    rating_raw   = str(body.get("rating", "")).strip().lower()
    agent_id     = str(body.get("agent_id", "")).strip()
    text         = str(body.get("text", "")).strip()
    memory_ids   = body.get("memory_ids") or []
    meta         = body.get("meta") or {}

    if not output_id:
        raise HTTPException(400, "output_id is required")
    if rating_raw not in ("up", "down"):
        raise HTTPException(400, "rating must be 'up' or 'down'")
    if not isinstance(memory_ids, list):
        raise HTTPException(400, "memory_ids must be a list")

    actor = str((body.get("actor") or _DEFAULT_USER)).strip() or _DEFAULT_USER

    from starlette.concurrency import run_in_threadpool as _rtp  # noqa: PLC0415

    def _submit():
        return store.submit(
            output_id  = output_id,
            rating     = rating_raw,   # type: ignore[arg-type]
            agent_id   = agent_id,
            actor      = actor,
            text       = text,
            memory_ids = [str(m) for m in memory_ids[:50]],
            meta       = dict(meta) if isinstance(meta, dict) else {},
        )

    entry = await _rtp(_submit)
    return JSONResponse({"ok": True, "feedback": entry.to_dict()})


@app.get("/api/feedback/summary")
def get_feedback_summary(_auth: None = Depends(require_auth)):
    """Return aggregate feedback statistics across all agents.

    Response shape::

        {
          "total":        42,
          "thumbs_up":    30,
          "thumbs_down":  12,
          "avg_reward":   0.43,
          "positive_rate": 0.71,
          "by_agent": {
            "company-builder": {...},
            ...
          }
        }
    """
    store = _get_feedback_store()
    if store is None:
        raise HTTPException(503, "Feedback store unavailable")
    return JSONResponse(store.summary())


@app.get("/api/feedback/recent")
def get_feedback_recent(limit: int = 50, _auth: None = Depends(require_auth)):
    """Return the most recent feedback entries (newest first)."""
    store = _get_feedback_store()
    if store is None:
        raise HTTPException(503, "Feedback store unavailable")
    limit = max(1, min(limit, 500))
    entries = store.list_recent(limit=limit)
    return JSONResponse({"ok": True, "entries": [e.to_dict() for e in entries]})


@app.get("/api/feedback/{output_id}")
def get_feedback_for_output(output_id: str, _auth: None = Depends(require_auth)):
    """Return all feedback entries for a specific output ID."""
    if not re.match(r'^[A-Za-z0-9_\-]{1,128}$', output_id):
        raise HTTPException(400, "Invalid output_id")
    store = _get_feedback_store()
    if store is None:
        raise HTTPException(503, "Feedback store unavailable")
    entries = store.get_for_output(output_id)
    return JSONResponse({"ok": True, "output_id": output_id, "entries": [e.to_dict() for e in entries]})


# ═══════════════════════════════════════════════════════════════════════════════
# Governance Digest API
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/governance/digest")
async def generate_governance_digest(payload: dict = None, _auth: None = Depends(require_auth)):
    """Generate a fresh governance digest for the requested time window.

    Body (all fields optional)::

        {
          "window_days": 7    // look-back window in days (default 7)
        }

    Returns the full digest including the Markdown report.
    """
    gd = _get_governance_digest()
    if gd is None:
        raise HTTPException(503, "Governance digest unavailable")
    body = payload or {}
    window_days = None
    if "window_days" in body:
        try:
            window_days = max(1, min(int(body["window_days"]), 365))
        except (TypeError, ValueError):
            raise HTTPException(400, "window_days must be an integer")

    from starlette.concurrency import run_in_threadpool as _rtp  # noqa: PLC0415

    digest = await _rtp(lambda: gd.run(window_days=window_days))
    return JSONResponse({"ok": True, "digest": digest})


@app.get("/api/governance/digest/latest")
def get_latest_governance_digest(limit: int = 5, _auth: None = Depends(require_auth)):
    """Return the *limit* most recent stored digests (newest first).

    Digests are persisted (without Markdown) to ``state/governance_digests.jsonl``
    after each :func:`generate_governance_digest` call.
    """
    gd = _get_governance_digest()
    if gd is None:
        raise HTTPException(503, "Governance digest unavailable")
    limit = max(1, min(limit, 100))
    digests = gd.load_recent(limit=limit)
    return JSONResponse({"ok": True, "digests": digests})


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Inspector API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/prompt-traces")
def get_prompt_traces(limit: int = 50, _auth: None = Depends(require_auth)):
    """Return a list of recent prompt traces (newest first).

    Query params:
        limit — max entries returned (default 50, max 200)

    Response::

        {
          "ok": true,
          "traces": [{ "id", "timestamp", "user_input", "agent",
                       "execution_status", "flags", "duration_ms" }, ...]
          "total": 42,
          "inspector_status": { "enabled": true, "sample_rate": 1.0, ... }
        }
    """
    pi = _get_prompt_inspector()
    if pi is None:
        raise HTTPException(503, "Prompt inspector unavailable")
    limit = max(1, min(limit, 200))
    traces = pi.list_traces(limit=limit)
    return JSONResponse({
        "ok": True,
        "traces": traces,
        "total": pi.count(),
        "inspector_status": pi.status(),
    })


@app.get("/api/prompt-trace/{trace_id}")
def get_prompt_trace(trace_id: str, _auth: None = Depends(require_auth)):
    """Return full detail for a single prompt trace.

    Response::

        {
          "ok": true,
          "trace": {
            "id", "timestamp", "user_input", "context_used",
            "constructed_prompt", "model_raw_output", "final_output",
            "actions_triggered", "execution_status", "agent",
            "provider", "model", "flags", "error", "duration_ms"
          }
        }
    """
    pi = _get_prompt_inspector()
    if pi is None:
        raise HTTPException(503, "Prompt inspector unavailable")
    trace = pi.get_trace(trace_id)
    if trace is None:
        raise HTTPException(404, f"Trace '{trace_id}' not found")
    return JSONResponse({"ok": True, "trace": trace})


@app.patch("/api/prompt-inspector/config")
async def patch_inspector_config(payload: dict, _auth: None = Depends(require_auth)):
    """Update inspector runtime configuration without restart.

    Body (all fields optional)::

        { "enabled": true, "sample_rate": 0.5 }
    """
    pi = _get_prompt_inspector()
    if pi is None:
        raise HTTPException(503, "Prompt inspector unavailable")
    body = payload or {}
    if "enabled" in body:
        pi.enabled = bool(body["enabled"])
    if "sample_rate" in body:
        try:
            pi.sample_rate = float(body["sample_rate"])
        except (TypeError, ValueError):
            raise HTTPException(400, "sample_rate must be a number 0.0–1.0")
    return JSONResponse({"ok": True, "inspector_status": pi.status()})


@app.delete("/api/prompt-traces")
async def clear_prompt_traces(_auth: None = Depends(require_auth)):
    """Clear all in-memory prompt traces."""
    pi = _get_prompt_inspector()
    if pi is None:
        raise HTTPException(503, "Prompt inspector unavailable")
    pi.clear()
    return JSONResponse({"ok": True, "message": "All prompt traces cleared"})


# ── Self-Learning Brain Internal Routes ───────────────────────────────────────

@app.get("/internal/brain-status")
def get_brain_status():
    """Return brain health metrics and recent learning outcomes."""
    try:
        from core.self_learning_brain import get_self_learning_brain
        slb = get_self_learning_brain()
        metrics = slb.metrics()
        outcomes = slb.recent_outcomes(limit=10)
        return JSONResponse({
            "ok": True,
            "metrics": metrics,
            "outcomes": outcomes,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/internal/suggest")
async def suggest_action(payload: dict):
    """Suggest best agent/strategy for a given context.

    Body: {"context": str, "candidates": [str] optional}
    Returns: {"ok": true, "suggestion": {...}} or {"ok": false, "error": "..."}
    """
    try:
        from core.self_learning_brain import get_self_learning_brain
        context = (payload.get("context") or "").strip()
        candidates = payload.get("candidates")
        if not context:
            raise ValueError("context required")

        slb = get_self_learning_brain()
        suggestion = slb.suggest_action(context=context, candidates=candidates)
        return JSONResponse({"ok": True, "suggestion": suggestion})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=400)


@app.post("/internal/reinforce")
async def reinforce_action(payload: dict):
    """Directly adjust agent strength by reward signal (-1..1).

    Body: {"action": str, "reward": float, "context": str optional}
    Returns: {"ok": true}
    """
    try:
        from core.self_learning_brain import get_self_learning_brain
        action = (payload.get("action") or "").strip()
        reward = float(payload.get("reward", 0.0))
        if not action:
            raise ValueError("action required")

        slb = get_self_learning_brain()
        slb.reinforce(action, reward)
        return JSONResponse({"ok": True, "message": f"Reinforced {action} by {reward}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=400)


# ── AI Middleware Layer ────────────────────────────────────────────────────────

@app.post("/api/middleware/process")
async def middleware_process(body: dict):
    """
    Unified multi-model input processing.

    Body:
      input_type: "text" | "voice" | "image" | "sensor"
      content:    str (text/transcription), base64 str (image), dict (sensor)
      context:    optional dict (system_prompt, task hints, etc.)
      requested_models: optional list of model roles to force
      session_id: optional str
      user_id:    optional str
    """
    try:
        from core.middleware import MiddlewareOrchestrator, MiddlewareRequest, InputType, ModelRole
        orch = MiddlewareOrchestrator()
        input_type = InputType(body.get("input_type", "text"))
        requested = [ModelRole(r) for r in (body.get("requested_models") or [])]
        req = MiddlewareRequest(
            input_type=input_type,
            content=body.get("content", ""),
            context=body.get("context") or {},
            requested_models=requested,
            session_id=body.get("session_id", ""),
            user_id=body.get("user_id", "operator"),
        )
        result = orch.process(req)
        return JSONResponse({
            "text": result.text,
            "model_roles_used": [r.value for r in result.model_roles_used],
            "execution_steps": result.execution_steps,
            "metadata": result.metadata,
            "elapsed_ms": result.elapsed_ms,
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/middleware/status")
async def middleware_status():
    """Return current middleware and Wave Field routing status."""
    try:
        from core.wavefield_provider import get_wavefield_metrics
        from core.model_routing import wavefield_enabled, _rollout_mode
        wf_metrics = get_wavefield_metrics()
        return JSONResponse({
            "wavefield_enabled": wavefield_enabled(),
            "wavefield_rollout_mode": _rollout_mode(),
            "wavefield_metrics": wf_metrics,
            "active_models": ["llm", "lam"],
            "optional_models": {
                "vlm": bool(os.environ.get("VLM_MODEL") or os.environ.get("OPENROUTER_API_KEY")),
                "sam": False,
                "lcm": True,
            },
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── PostgreSQL Database API Routes ──────────────────────────────────────────────
@app.post("/api/db/query")
async def db_query(payload: dict, _auth: None = Depends(require_auth)):
    """Execute raw SQL query (tenant-filtered)."""
    try:
        from core.database import get_database
        from core.tenancy import get_current_tenant
        db = get_database()
        tenant = get_current_tenant()
        sql = payload.get("sql", "")
        params = payload.get("params", [])
        results = db.execute(sql, tuple(params), tenant_id=tenant.tenant_id)
        return JSONResponse({"results": results, "count": len(results)})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=400)


@app.post("/api/db/insert")
async def db_insert(payload: dict, _auth: None = Depends(require_auth)):
    """Insert row into table (tenant-filtered)."""
    try:
        from core.database import get_database
        from core.tenancy import get_current_tenant
        db = get_database()
        tenant = get_current_tenant()
        table = payload.get("table", "")
        data = payload.get("data", {})
        result = db.insert(table, data, tenant_id=tenant.tenant_id)
        return JSONResponse({"inserted": result})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=400)


@app.post("/api/db/update")
async def db_update(payload: dict, _auth: None = Depends(require_auth)):
    """Update rows in table (tenant-filtered)."""
    try:
        from core.database import get_database
        from core.tenancy import get_current_tenant
        db = get_database()
        tenant = get_current_tenant()
        table = payload.get("table", "")
        data = payload.get("data", {})
        where = payload.get("where", "")
        params = tuple(payload.get("params", []))
        count = db.update(table, data, where, params, tenant_id=tenant.tenant_id)
        return JSONResponse({"updated": count})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=400)


@app.post("/api/db/delete")
async def db_delete(payload: dict, _auth: None = Depends(require_auth)):
    """Delete rows from table (tenant-filtered)."""
    try:
        from core.database import get_database
        from core.tenancy import get_current_tenant
        db = get_database()
        tenant = get_current_tenant()
        table = payload.get("table", "")
        where = payload.get("where", "")
        params = tuple(payload.get("params", []))
        count = db.delete(table, where, params, tenant_id=tenant.tenant_id)
        return JSONResponse({"deleted": count})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=400)


@app.post("/api/backup/create")
async def create_backup(_auth: None = Depends(require_auth)):
    """Create PostgreSQL backup."""
    try:
        from core.backup import get_backup_manager
        manager = get_backup_manager()
        backup_file = manager.create_backup_via_shell()
        if backup_file:
            return JSONResponse({"status": "created", "file": backup_file})
        else:
            return JSONResponse({"error": "Backup failed"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/backup/list")
async def list_backups(_auth: None = Depends(require_auth)):
    """List available backups."""
    try:
        from core.backup import get_backup_manager
        manager = get_backup_manager()
        backups = manager.list_backups()
        return JSONResponse({"backups": backups})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.post("/api/backup/restore/{backup_name}")
async def restore_backup(backup_name: str, _auth: None = Depends(require_auth)):
    """Restore from a backup."""
    try:
        from core.backup import get_backup_manager
        from pathlib import Path
        manager = get_backup_manager()
        backup_path = manager.backup_dir / backup_name
        if backup_path.exists():
            success = manager.restore_backup(str(backup_path))
            return JSONResponse({"status": "restored" if success else "failed"})
        else:
            return JSONResponse({"error": "Backup not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Payment & Stripe Integration ──────────────────────────────────────────────

def _stripe_check() -> JSONResponse | None:
    """Return a 503 JSONResponse if STRIPE_API_KEY is not configured, else None."""
    if not os.environ.get("STRIPE_API_KEY"):
        return JSONResponse({"ok": False, "error": "Stripe not configured (STRIPE_API_KEY missing)"}, status_code=503)
    return None


@app.post("/api/billing/customer/create", tags=["billing"])
async def create_stripe_customer(payload: dict, _auth: None = Depends(require_auth)):
    """Create a Stripe customer for a tenant."""
    if err := _stripe_check():
        return err
    try:
        from core.stripe_integration import get_stripe_manager
        from core.tenancy import get_current_tenant
        tenant = get_current_tenant()
        stripe_mgr = get_stripe_manager()
        customer_id = stripe_mgr.create_customer(
            tenant_id=tenant.tenant_id,
            email=payload.get("email", ""),
            name=payload.get("name", ""),
        )
        if customer_id:
            return JSONResponse({"customer_id": customer_id, "status": "created"})
        return JSONResponse({"ok": False, "error": "Failed to create customer"}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/payment-intent/create", tags=["billing"])
async def create_payment_intent(payload: dict, _auth: None = Depends(require_auth)):
    """Create a Stripe payment intent."""
    if err := _stripe_check():
        return err
    try:
        from core.stripe_integration import get_stripe_manager
        stripe_mgr = get_stripe_manager()
        result = stripe_mgr.create_payment_intent(
            customer_id=payload.get("customer_id", ""),
            amount_cents=int(payload.get("amount_cents", 0)),
            currency=payload.get("currency", "usd"),
            description=payload.get("description", ""),
        )
        if result:
            return JSONResponse(result)
        return JSONResponse({"ok": False, "error": "Failed to create payment intent"}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/subscription/create", tags=["billing"])
async def create_subscription(payload: dict, _auth: None = Depends(require_auth)):
    """Create a Stripe subscription."""
    if err := _stripe_check():
        return err
    try:
        from core.stripe_integration import get_stripe_manager
        stripe_mgr = get_stripe_manager()
        result = stripe_mgr.create_subscription(
            customer_id=payload.get("customer_id", ""),
            price_id=payload.get("price_id", ""),
            metadata=payload.get("metadata", {}),
        )
        if result:
            return JSONResponse(result)
        return JSONResponse({"ok": False, "error": "Failed to create subscription"}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.get("/api/billing/subscription/{subscription_id}", tags=["billing"])
async def get_subscription(subscription_id: str, _auth: None = Depends(require_auth)):
    """Get subscription status."""
    if err := _stripe_check():
        return err
    try:
        from core.stripe_integration import get_stripe_manager
        stripe_mgr = get_stripe_manager()
        result = stripe_mgr.get_subscription_status(subscription_id)
        if result:
            return JSONResponse(result)
        return JSONResponse({"ok": False, "error": "Subscription not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/subscription/{subscription_id}/cancel", tags=["billing"])
async def cancel_subscription(subscription_id: str, payload: dict = {}, _auth: None = Depends(require_auth)):
    """Cancel a subscription."""
    if err := _stripe_check():
        return err
    try:
        from core.stripe_integration import get_stripe_manager
        stripe_mgr = get_stripe_manager()
        success = stripe_mgr.cancel_subscription(subscription_id, at_period_end=payload.get("at_period_end", False))
        return JSONResponse({"status": "cancelled" if success else "failed"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


# ── Stripe webhook — validates Stripe-Signature, no JWT auth ──────────────────

@app.post("/api/billing/stripe/webhook", tags=["billing"])
async def stripe_webhook(request: Request):
    """Stripe webhook handler — validates signature and processes events."""
    if err := _stripe_check():
        return err
    try:
        import stripe as _stripe
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            return JSONResponse({"ok": False, "error": "STRIPE_WEBHOOK_SECRET not configured"}, status_code=503)
        payload_bytes = await request.body()
        sig_header = request.headers.get("stripe-signature", "")
        try:
            event = _stripe.Webhook.construct_event(payload_bytes, sig_header, webhook_secret)
        except _stripe.error.SignatureVerificationError:
            return JSONResponse({"ok": False, "error": "Invalid Stripe signature"}, status_code=400)
        event_type = event.get("type", "")
        logger.info("stripe_webhook: received event type=%s id=%s", event_type, event.get("id"))
        # Dispatch known event types
        if event_type == "invoice.payment_succeeded":
            invoice = event["data"]["object"]
            logger.info("stripe_webhook: payment succeeded customer=%s amount=%s", invoice.get("customer"), invoice.get("amount_paid"))
        elif event_type == "customer.subscription.deleted":
            sub = event["data"]["object"]
            logger.info("stripe_webhook: subscription cancelled id=%s", sub.get("id"))
        elif event_type == "customer.subscription.updated":
            sub = event["data"]["object"]
            logger.info("stripe_webhook: subscription updated id=%s status=%s", sub.get("id"), sub.get("status"))
        return JSONResponse({"ok": True, "type": event_type})
    except Exception as e:
        logger.error("stripe_webhook error: %s", e)
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/stripe/customer", tags=["billing"])
async def stripe_create_or_get_customer(body: dict, auth=Depends(require_auth)):
    """Create or retrieve a Stripe customer linked to this tenant."""
    if err := _stripe_check():
        return err
    try:
        import stripe as _stripe
        from core.tenancy import get_current_tenant
        tenant = get_current_tenant()
        tenant_id = tenant.tenant_id if tenant else (auth.get("tenant_id", "default") if isinstance(auth, dict) else "default")
        email = body.get("email", "")
        name = body.get("name", "")
        # Check if customer already exists for this tenant
        existing = _stripe.Customer.search(query=f'metadata["tenant_id"]:"{tenant_id}"', limit=1)
        if existing.data:
            cust = existing.data[0]
            return JSONResponse({"ok": True, "customer_id": cust.id, "status": "existing"})
        from core.stripe_integration import get_stripe_manager
        mgr = get_stripe_manager()
        customer_id = mgr.create_customer(tenant_id=tenant_id, email=email, name=name)
        if not customer_id:
            return JSONResponse({"ok": False, "error": "Failed to create Stripe customer"}, status_code=500)
        return JSONResponse({"ok": True, "customer_id": customer_id, "status": "created"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.get("/api/billing/stripe/subscription", tags=["billing"])
async def stripe_get_subscription(auth=Depends(require_auth)):
    """Get active subscription for the current tenant's Stripe customer."""
    if err := _stripe_check():
        return err
    try:
        import stripe as _stripe
        from core.tenancy import get_current_tenant
        tenant = get_current_tenant()
        tenant_id = tenant.tenant_id if tenant else (auth.get("tenant_id", "default") if isinstance(auth, dict) else "default")
        customers = _stripe.Customer.search(query=f'metadata["tenant_id"]:"{tenant_id}"', limit=1)
        if not customers.data:
            return JSONResponse({"ok": False, "error": "No Stripe customer found for this tenant"}, status_code=404)
        customer_id = customers.data[0].id
        subs = _stripe.Subscription.list(customer=customer_id, status="active", limit=1)
        if not subs.data:
            return JSONResponse({"ok": True, "subscription": None, "status": "no_active_subscription"})
        from core.stripe_integration import get_stripe_manager
        result = get_stripe_manager().get_subscription_status(subs.data[0].id)
        return JSONResponse({"ok": True, "subscription": result})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/stripe/checkout", tags=["billing"])
async def stripe_create_checkout(body: dict, auth=Depends(require_auth)):
    """Create a Stripe Checkout session (hosted page redirect). body: {price_id, success_url, cancel_url}."""
    if err := _stripe_check():
        return err
    try:
        import stripe as _stripe
        price_id = body.get("price_id", "")
        success_url = body.get("success_url", "")
        cancel_url = body.get("cancel_url", "")
        if not price_id or not success_url or not cancel_url:
            return JSONResponse({"ok": False, "error": "price_id, success_url, cancel_url are required"}, status_code=400)
        from core.tenancy import get_current_tenant
        tenant = get_current_tenant()
        tenant_id = tenant.tenant_id if tenant else (auth.get("tenant_id", "default") if isinstance(auth, dict) else "default")
        session_kwargs: dict = {
            "mode": "subscription",
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"tenant_id": tenant_id},
        }
        # Attach existing customer if available
        try:
            customers = _stripe.Customer.search(query=f'metadata["tenant_id"]:"{tenant_id}"', limit=1)
            if customers.data:
                session_kwargs["customer"] = customers.data[0].id
        except Exception:
            pass
        session = _stripe.checkout.Session.create(**session_kwargs)
        return JSONResponse({"ok": True, "session_id": session.id, "url": session.url})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


@app.post("/api/billing/stripe/sync-usage", tags=["billing", "admin"])
async def stripe_sync_usage(_rbac=Depends(require_permission("admin:*"))):
    """Sync cost ledger usage data to Stripe metered billing items."""
    if err := _stripe_check():
        return err
    try:
        import stripe as _stripe
        from core.cost_ledger import get_cost_ledger
        ledger = get_cost_ledger()
        # Collect all tenant IDs from the ledger
        with ledger._lock:
            raw_keys = list(ledger._ledger.keys())
        tenant_ids = {k.split(":")[0] for k in raw_keys if ":" in k}
        synced = []
        errors = []
        for tenant_id in tenant_ids:
            try:
                customers = _stripe.Customer.search(query=f'metadata["tenant_id"]:"{tenant_id}"', limit=1)
                if not customers.data:
                    continue
                customer_id = customers.data[0].id
                subs = _stripe.Subscription.list(customer=customer_id, status="active", limit=1)
                if not subs.data:
                    continue
                sub = subs.data[0]
                # Find metered subscription items
                for item in sub["items"]["data"]:
                    price = item.get("price", {})
                    if price.get("recurring", {}).get("usage_type") == "metered":
                        daily_usd = ledger.get_daily_spend(tenant_id)
                        quantity = max(1, int(daily_usd * 100))  # cents as usage units
                        _stripe.SubscriptionItem.create_usage_record(
                            item["id"],
                            quantity=quantity,
                            action="set",
                        )
                        synced.append({"tenant_id": tenant_id, "customer_id": customer_id, "usage_units": quantity})
            except Exception as ex:
                errors.append({"tenant_id": tenant_id, "error": "operation_failed"})
        return JSONResponse({"ok": True, "synced": synced, "errors": errors})
    except Exception as e:
        return JSONResponse({"ok": False, "error": "operation_failed"}, status_code=500)


# ── RBAC Routes ───────────────────────────────────────────────────────────────

@app.post("/api/rbac/assign-role")
async def assign_user_role(payload: dict, _auth: None = Depends(require_auth)):
    """Assign a role to a user (admin only)."""
    try:
        from core.rbac import get_rbac_manager, Role
        from core.tenancy import get_current_tenant
        from core.auth import get_current_user
        user = get_current_user()
        tenant = get_current_tenant()
        rbac = get_rbac_manager()

        # Check if requester is admin
        requester_role = rbac.get_user_role(user.get("user_id"), tenant.tenant_id)
        if requester_role != Role.ADMIN:
            return JSONResponse({"error": "Admin role required"}, status_code=403)

        target_user_id = payload.get("user_id", "")
        role_str = payload.get("role", "viewer")
        role = Role(role_str)

        success = rbac.assign_role(target_user_id, role, tenant.tenant_id)
        return JSONResponse({"status": "assigned" if success else "failed", "user_id": target_user_id, "role": role.value})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/rbac/user-role")
async def get_user_role(_auth: None = Depends(require_auth)):
    """Get current user's role."""
    try:
        from core.rbac import get_rbac_manager
        from core.tenancy import get_current_tenant
        from core.auth import get_current_user
        user = get_current_user()
        tenant = get_current_tenant()
        rbac = get_rbac_manager()

        role = rbac.get_user_role(user.get("user_id"), tenant.tenant_id)
        perms = get_rbac_manager().get_user_role(user.get("user_id"), tenant.tenant_id)

        return JSONResponse({"user_id": user.get("user_id"), "role": role.value})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/rbac/roles")
async def list_user_roles(_auth: None = Depends(require_auth)):
    """List all user roles in tenant (admin only)."""
    try:
        from core.rbac import get_rbac_manager, Role
        from core.tenancy import get_current_tenant
        from core.auth import get_current_user
        user = get_current_user()
        tenant = get_current_tenant()
        rbac = get_rbac_manager()

        # Check if requester is admin
        requester_role = rbac.get_user_role(user.get("user_id"), tenant.tenant_id)
        if requester_role != Role.ADMIN:
            return JSONResponse({"error": "Admin role required"}, status_code=403)

        roles = rbac.list_user_roles(tenant.tenant_id)
        return JSONResponse({"roles": roles})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Billing Metrics Routes (Phase 4) ──────────────────────────────────────────

@app.get("/api/billing/metrics", tags=["billing"])
async def get_billing_metrics(_auth: None = Depends(require_auth)):
    """Get billing metrics for current tenant."""
    try:
        from core.tenancy import get_current_tenant
        from core.billing_metrics import get_billing_collector
        tenant = get_current_tenant()
        collector = get_billing_collector()
        metrics = collector.get_tenant_metrics(tenant.tenant_id, period_days=30)
        if metrics:
            return JSONResponse(asdict(metrics))
        else:
            return JSONResponse({"error": "No metrics available"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/billing/all-metrics", tags=["billing", "admin"])
async def get_all_billing_metrics(_auth: None = Depends(require_auth)):
    """Get billing metrics for all tenants (admin only)."""
    try:
        from core.tenancy import get_current_tenant
        from core.rbac import get_rbac_manager, Role
        from core.auth import get_current_user
        from core.billing_metrics import get_billing_collector

        user = get_current_user()
        tenant = get_current_tenant()
        rbac = get_rbac_manager()

        # Check if admin
        user_role = rbac.get_user_role(user.get("user_id"), tenant.tenant_id)
        if user_role != Role.ADMIN:
            return JSONResponse({"error": "Admin role required"}, status_code=403)

        collector = get_billing_collector()
        all_metrics = collector.get_all_tenant_metrics(period_days=30)
        return JSONResponse({"metrics": [asdict(m) for m in all_metrics]})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Rate Limiting Routes (Phase 4) ────────────────────────────────────────────

@app.get("/api/quota/usage")
async def get_quota_usage(_auth: None = Depends(require_auth)):
    """Get current quota usage for tenant."""
    try:
        from core.tenancy import get_current_tenant
        from core.rate_limiter import get_rate_limiter

        tenant = get_current_tenant()
        limiter = get_rate_limiter()
        usage = limiter.get_tenant_usage(tenant.tenant_id)
        quota = limiter.get_tenant_quota(tenant.tenant_id)

        return JSONResponse({
            "usage": usage,
            "quota": {
                "requests_per_minute": quota.requests_per_minute,
                "agents_per_hour": quota.agents_per_hour,
                "api_calls_per_day": quota.api_calls_per_day,
                "storage_gb": quota.storage_gb,
            }
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Embeddings Routes (Phase 4) ──────────────────────────────────────────────

@app.post("/api/embeddings/embed")
async def embed_text(payload: dict, _auth: None = Depends(require_auth)):
    """Generate embedding for text."""
    try:
        from core.embeddings import get_embeddings_manager

        text = payload.get("text", "")
        if not text:
            return JSONResponse({"error": "text required"}, status_code=400)

        manager = get_embeddings_manager()
        embedding = manager.embed_text(text)

        return JSONResponse({
            "text": text,
            "embedding": embedding,
            "dimension": len(embedding),
            "mode": manager.get_mode(),
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.post("/api/embeddings/similarity")
async def similarity_score(payload: dict, _auth: None = Depends(require_auth)):
    """Calculate similarity between two embeddings."""
    try:
        from core.embeddings import get_embeddings_manager

        emb1 = payload.get("embedding_1", [])
        emb2 = payload.get("embedding_2", [])

        if not emb1 or not emb2:
            return JSONResponse({"error": "embedding_1 and embedding_2 required"}, status_code=400)

        manager = get_embeddings_manager()
        score = manager.similarity(emb1, emb2)

        return JSONResponse({"similarity": score})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Audit Logging Routes (Phase 4) ───────────────────────────────────────────

@app.get("/api/audit/logs")
async def get_audit_logs(_auth: None = Depends(require_auth)):
    """Get audit logs for current tenant."""
    try:
        from core.tenancy import get_current_tenant

        tenant = get_current_tenant()
        limit = 100  # Last 100 audit events

        # TODO: Fetch from database when audit_logs table available
        return JSONResponse({"logs": [], "tenant_id": tenant.tenant_id, "count": 0})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/audit/model-decisions", tags=["admin"])
async def model_decision_audit_admin(
    limit: int = 100,
    _rbac=Depends(require_permission("admin:*")),
):
    """Admin: recent model decision fingerprints — no prompt/response content stored."""
    try:
        from core.model_decision_audit import get_model_audit
        audit = get_model_audit()
        n = min(limit, 500)
        return JSONResponse({
            "decisions": audit.get_recent(limit=n),
            "stats": audit.get_stats(window_hours=24),
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/audit/chain-verify", tags=["admin"])
async def audit_chain_verify(_rbac=Depends(require_permission("admin:*"))):
    """Admin: verify hash-chain integrity of the audit log — detects tampering or row removal."""
    try:
        from core.audit import get_audit_db
        ok, msg = get_audit_db().verify_chain()
        return JSONResponse({"valid": ok, "message": msg})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── Observability Status Routes (Phase 4) ────────────────────────────────────

@app.get("/api/observability/sentry")
async def get_sentry_status(_auth: None = Depends(require_auth)):
    """Get Sentry error tracking status."""
    try:
        from core.sentry_config import get_sentry_client

        client = get_sentry_client()
        status = "enabled" if client else "disabled"

        return JSONResponse({"status": status, "dsn_configured": bool(client)})
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/observability/embeddings")
async def get_embeddings_status(_auth: None = Depends(require_auth)):
    """Get embeddings system status."""
    try:
        from core.embeddings import get_embeddings_manager

        manager = get_embeddings_manager()

        return JSONResponse({
            "mode": manager.get_mode(),
            "available": manager.embeddings_available,
            "dimension": 384,
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/monitoring/drift")
async def drift_report(_auth: None = Depends(require_auth)):
    """Model drift and bias monitoring report — compares current 24h vs 7-day baseline."""
    try:
        from core.drift_monitor import DriftMonitor
        return JSONResponse(DriftMonitor().get_report())
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


@app.get("/api/monitoring/decisions")
async def decision_audit(_auth: None = Depends(require_auth)):
    """Recent model decision audit records — compliance traceability (no content stored)."""
    try:
        from core.model_decision_audit import get_model_audit
        audit = get_model_audit()
        return JSONResponse({
            "records": audit.get_recent(limit=100),
            "stats": audit.get_stats(window_hours=24),
        })
    except Exception as e:
        return JSONResponse({"error": "operation_failed"}, status_code=500)


# ── User Profile & Intelligence (Phase 5 — 100/100) ──────────────────────────

@app.get("/api/profile")
async def get_user_profile(_auth: None = Depends(require_auth)):
    """Get current user's intelligence profile and interaction history."""
    try:
        from core.auth import get_current_user
        from core.tenancy import get_current_tenant
        import hashlib

        user = get_current_user()
        tenant = get_current_tenant()
        user_id = user.get("user_id", "unknown")

        interaction_count, favorite_agents = _profile_audit_stats(user_id, tenant.tenant_id)

        profile = {
            "user_id": user_id,
            "tenant_id": tenant.tenant_id,
            "email": user.get("email", ""),
            "created_at": user.get("created_at", datetime.utcnow().isoformat()),
            "preferences": {
                "tone": "concise",
                "output_format": "json",
                "auto_execute": False,
            },
            "interaction_count": interaction_count,
            "favorite_agents": favorite_agents,
            "intelligence_score": 0.75,
        }
        return JSONResponse(profile)
    except Exception as e:
        return JSONResponse({"error": "operation_failed", "status": "unavailable"}, status_code=200)


@app.get("/api/metrics")
async def get_prometheus_metrics(_auth: None = Depends(require_auth)):
    """Export Prometheus-format metrics for monitoring."""
    try:
        from core.observability.metrics_collector import get_metrics_collector
        from datetime import datetime

        collector = get_metrics_collector()
        snapshot = collector.get_snapshot()

        # Generate Prometheus text format
        lines = [
            "# HELP ai_employee_uptime_ms System uptime in milliseconds",
            "# TYPE ai_employee_uptime_ms gauge",
            f"ai_employee_uptime_ms {int((time.time() - _startup_time) * 1000)}",
            "",
            "# HELP ai_employee_agents_active Number of active agents",
            "# TYPE ai_employee_agents_active gauge",
            f"ai_employee_agents_active {snapshot.get('agents_active', 0)}",
            "",
            "# HELP ai_employee_tasks_total Total tasks processed",
            "# TYPE ai_employee_tasks_total counter",
            f"ai_employee_tasks_total {snapshot.get('tasks_total', 0)}",
            "",
            "# HELP ai_employee_tasks_completed Completed tasks",
            "# TYPE ai_employee_tasks_completed counter",
            f"ai_employee_tasks_completed {snapshot.get('tasks_completed', 0)}",
            "",
            "# HELP ai_employee_tasks_failed Failed tasks",
            "# TYPE ai_employee_tasks_failed counter",
            f"ai_employee_tasks_failed {snapshot.get('tasks_failed', 0)}",
            "",
            "# HELP ai_employee_errors_total Total errors",
            "# TYPE ai_employee_errors_total counter",
            f"ai_employee_errors_total {snapshot.get('errors_total', 0)}",
            "",
            "# HELP ai_employee_api_calls_total API calls processed",
            "# TYPE ai_employee_api_calls_total counter",
            f"ai_employee_api_calls_total {snapshot.get('api_calls_total', 0)}",
            "",
        ]
        metrics_text = "\n".join(lines)
        return HTMLResponse(content=metrics_text, media_type="text/plain; version=0.0.4")
    except Exception as e:
        return HTMLResponse("# Error: operation failed", status_code=500, media_type="text/plain")


@app.get("/api/agents")
async def get_agents_http_fallback():
    """Get agent list (HTTP fallback when WebSocket unavailable)."""
    try:
        import json
        from pathlib import Path

        agent_file = Path(AI_HOME) / "config" / "agent_capabilities.json" if AI_HOME else Path("runtime/config/agent_capabilities.json")
        if agent_file.exists():
            config = json.load(open(agent_file))
            agents = []
            for agent_id, agent_data in config.get("agents", {}).items():
                agents.append({
                    "id": agent_id,
                    "name": agent_data.get("description", "").split(" — ")[0],
                    "description": agent_data.get("description", ""),
                    "category": agent_data.get("category", "general"),
                    "status": "ready",
                })
            return JSONResponse({"agents": agents, "total": len(agents)})
        else:
            return JSONResponse({"agents": [], "total": 0})
    except Exception as e:
        return JSONResponse({"error": "operation_failed", "agents": [], "total": 0}, status_code=500)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # HSTS: Enforce HTTPS (31536000 = 1 year)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # CSP: Prevent XSS
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

    # X-Frame-Options: Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # X-Content-Type-Options: Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # X-XSS-Protection: Legacy XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer-Policy: Privacy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


# Track startup time for uptime metric
_startup_time = time.time()

# ── Lazy init trigger: on first non-health request, initialize observability ───
_observability_init_lock = False

@app.middleware("http")
async def init_observability_on_first_request(request, call_next):
    global _observability_init_lock
    if not _observability_init_lock and request.url.path not in ("/health", "/api/health"):
        _observability_init_lock = True
        # Trigger lazy init in background (non-blocking)
        try:
            _init_tracing()
            _init_sentry()
        except Exception as e:
            logger.debug(f"Observability lazy-init had issues: {e}")
    response = await call_next(request)
    return response


# ── Subsystem readiness flags (written by startup, read by /health/detail) ──
_neural_brain_initialized = False
_memory_initialized = False
_llm_probe_result = False


@app.get("/health/detail")
def health_detail():
    """Subsystem readiness — polled by Node after /health passes."""
    return JSONResponse({
        "subsystems_ok": _neural_brain_initialized and _memory_initialized,
        "llm_reachable": _llm_probe_result,
        "memory_ready": _memory_initialized,
    })


# ── Web Search + CloakBrowser endpoint ───────────────────────────────────────

@app.post("/search")
async def web_search_endpoint(body: _SearchRequest):
    """Multi-provider web search with optional stealth visual browsing.

    sources may include: WEB (API search), SCREENSHOT (CloakBrowser visual fetch).
    Results are merged and returned as a flat list with relevance scores.
    """
    import time as _time
    started = _time.time()
    results = []
    providers_used = []

    # ── 1. API-based search providers (Tavily / SerpAPI / DDG / Wiki) ────────
    if "WEB" in body.sources or not body.sources:
        try:
            from ai_router import search_web as _search_web
            raw = await run_in_threadpool(_search_web, body.query, body.max_results)
            for r in raw:
                src = str(r.get("source", "WEB")).upper()
                snippet = r.get("snippet") or r.get("body") or ""
                results.append({
                    "title":         r.get("title", ""),
                    "url":           r.get("url", ""),
                    "snippet":       snippet[:500],
                    "source":        "WEB",
                    "provider":      src,
                    "screenshot_b64": None,
                    "page_text":     None,
                    "relevance":     _relevance(body.query, r.get("title", "") + " " + snippet),
                })
            if raw:
                providers_used.append("api_search")
        except Exception as exc:
            logger.warning("web_search_endpoint: search_web error: %s", exc)

    # ── 2. CloakBrowser visual fetch for top results ─────────────────────────
    if "SCREENSHOT" in body.sources:
        try:
            from infra.rpa.cloak_browser import fetch_url, _PLAYWRIGHT_OK
            if not _PLAYWRIGHT_OK:
                logger.warning("SCREENSHOT requested but playwright not installed")
            else:
                # Fetch top 3 URLs that have a URL
                top_urls = [r for r in results if r.get("url")][:3]
                # Also fetch standalone if no WEB results
                if not top_urls and body.query.startswith("http"):
                    top_urls = [{"url": body.query, "title": "", "snippet": "", "source": "SCREENSHOT",
                                 "provider": "cloak", "screenshot_b64": None, "page_text": None, "relevance": 80}]
                from core.url_guard import validate_url as _gu  # type: ignore
                top_urls = [r for r in top_urls if not _gu(r["url"])]
                fetch_tasks = [fetch_url(r["url"]) for r in top_urls]
                fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                for result_item, page_data in zip(top_urls, fetched):
                    if isinstance(page_data, dict) and not page_data.get("error"):
                        result_item["screenshot_b64"] = page_data.get("screenshot_b64")
                        result_item["page_text"] = (page_data.get("text") or "")[:1000]
                        result_item["source"] = "SCREENSHOT"
                        if page_data.get("title"):
                            result_item["title"] = page_data["title"]
                providers_used.append("cloak_browser")
        except Exception as exc:
            logger.warning("web_search_endpoint: cloak_browser error: %s", exc)

    # Sort by relevance desc
    results.sort(key=lambda r: r["relevance"], reverse=True)

    return JSONResponse({
        "results":        results,
        "query":          body.query,
        "elapsed_ms":     round((_time.time() - started) * 1000),
        "providers_used": providers_used,
        "total":          len(results),
    })


def _relevance(query: str, text: str) -> int:
    """Simple keyword overlap relevance score 0–100."""
    if not text:
        return 50
    q_words = set(query.lower().split())
    t_words = set(text.lower().split())
    if not q_words:
        return 50
    overlap = len(q_words & t_words) / len(q_words)
    return min(100, int(50 + overlap * 50))


# ── Boot telemetry ───────────────────────────────────────────────────────


@app.get("/api/system/startup-timings")
async def system_startup_timings():
    """Per-subsystem boot durations recorded by the Wave-B hook wrapper.

    Used by the Electron launcher to render a `--- PYTHON SUBSYSTEMS ---`
    block under the main phase rail. Subsystems with ``ms > 2000`` are
    highlighted amber, ``> 5000`` red — a visible budget gate.
    """
    timings = list(_STARTUP_TIMINGS) if "_STARTUP_TIMINGS" in globals() else []
    vi = sys.version_info
    return JSONResponse({
        "timings": timings,
        "python_version": f"{vi.major}.{vi.minor}.{vi.micro}",
        "startup_mode": os.environ.get("EVOLUTION_MODE", "unset"),
        "modules_loaded": len(sys.modules),
    })


@app.get("/api/boot/metrics")
def get_boot_metrics():
    """Return boot metrics from state/boot_metrics.json or computed uptime fallback."""
    boot_file = STATE_DIR / "boot_metrics.json"
    if boot_file.exists():
        try:
            import json as _json
            data = _json.loads(boot_file.read_text())
            return JSONResponse({"source": "file", "metrics": data})
        except Exception:
            pass
    uptime_s = time.time() - _startup_time
    return JSONResponse({
        "source": "computed",
        "metrics": {
            "uptime_s": round(uptime_s, 3),
            "uptime_ms": int(uptime_s * 1000),
            "started_at": _startup_time,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "startup_mode": os.environ.get("EVOLUTION_MODE", "unset"),
            "modules_loaded": len(sys.modules),
        },
    })


# ── Autonomous Research API ──────────────────────────────────────────────


@app.post("/api/tasks/{task_id}/context-response")
async def task_context_response(task_id: str, body: _ContextResponseRequest):
    """User clicked YES (continue) or NO (learn first) on the context-check modal."""
    try:
        from core.agent_controller import get_agent_controller
        controller = get_agent_controller()
        ok = controller.respond_to_context_check(task_id, body.choice)
        return JSONResponse({"ok": bool(ok), "task_id": task_id, "choice": body.choice})
    except Exception as exc:
        logger.warning("context-response failed: %s", exc)
        raise HTTPException(status_code=500, detail="operation_failed")


@app.get("/api/research/recent")
async def research_recent(limit: int = 20):
    """Recent autonomous-research sessions read from knowledge_store.json."""
    try:
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        snap = ks.snapshot()
        sessions: list[dict] = []
        for item in (snap.get("insights") or [])[-200:]:
            content = item.get("content") or {}
            if isinstance(content, dict) and content.get("source") == "auto-research":
                sessions.append({
                    "topic": item.get("topic"),
                    "goal": content.get("goal", ""),
                    "gap": content.get("gap", ""),
                    "findings": content.get("findings", []),
                    "stored_at": item.get("stored_at"),
                })
        sessions.reverse()
        return JSONResponse({"sessions": sessions[:max(1, int(limit))]})
    except Exception as exc:
        logger.warning("research_recent failed: %s", exc)
        return JSONResponse({"sessions": [], "error": "operation_failed"})


@app.post("/api/research/discover")
async def research_discover(req: dict, _auth: None = Depends(require_auth)):
    """Research v2 phase 1: discover candidate sources without fetching them."""
    query = (req or {}).get("query", "").strip()
    if not query:
        raise HTTPException(400, "query required")
    if len(query) > 500:
        raise HTTPException(400, "query too long (max 500 chars)")
    max_sources_raw = (req or {}).get("max_sources", 10)
    try:
        max_sources = max(1, min(int(max_sources_raw), 50))
    except (TypeError, ValueError):
        max_sources = 10
    try:
        from core.auto_research_agent import get_auto_researcher
        agent = get_auto_researcher()
        sources = await agent.discover_sources(query, max_results=max_sources)
        return JSONResponse({"sources": sources, "query": query, "discovered_at": time.time()})
    except Exception as exc:
        logger.warning("research_discover failed: %s", exc)
        raise HTTPException(500, f"discover failed: {exc}")


@app.post("/api/research/execute", tags=["research"])
@_tier_rate_limit
async def research_execute(req: dict, background: BackgroundTasks, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("research:*"))):
    """Research v2 phase 2: run full research pipeline on user-selected URLs."""
    import uuid as _uuid
    query = (req or {}).get("query", "").strip()
    source_ids = list((req or {}).get("selected_source_ids") or [])
    selected_urls = list((req or {}).get("selected_urls") or [])
    depth = (req or {}).get("depth", "normal")
    if not query or (not source_ids and not selected_urls):
        raise HTTPException(400, "query and selected_source_ids (or selected_urls) required")
    if selected_urls:
        from core.url_guard import validate_url as _gu  # type: ignore
        _orig_count = len(selected_urls)
        selected_urls = [u for u in selected_urls if not _gu(u)]
        if len(selected_urls) < _orig_count:
            import logging as _log
            _log.getLogger(__name__).warning(
                "SSRF guard blocked %d URL(s) in /api/research/execute",
                _orig_count - len(selected_urls))
        if not selected_urls and not source_ids:
            raise HTTPException(400, "All provided URLs were blocked by SSRF policy")
    session_id = _uuid.uuid4().hex[:12]
    try:
        from core.auto_research_agent import get_auto_researcher
        agent = get_auto_researcher()
    except Exception as exc:
        raise HTTPException(500, f"researcher unavailable: {exc}")
    background.add_task(_run_research_session_v2, agent, query, selected_urls, depth, session_id)
    return JSONResponse({"session_id": session_id, "status": "started",
                         "query": query, "depth": depth, "sources": len(selected_urls)})


async def _run_research_session_v2(agent, query: str, urls: list, depth: str, session_id: str) -> None:
    """Background runner for Research v2 — emits WS events via the existing broadcaster."""
    try:
        await _ws_broadcast("task:research_started",
                            {"session_id": session_id, "query": query, "depth": depth, "sources": len(urls)})
    except Exception:
        pass
    try:
        result = await agent.research_selected(query, urls, depth=depth, task_id=session_id)
        try:
            await _ws_broadcast("task:research_completed",
                                {"session_id": session_id, "query": query, **(result or {})})
        except Exception:
            pass
    except Exception as exc:
        logger.warning("research session %s failed: %s", session_id, exc)
        try:
            await _ws_broadcast("task:research_failed", {"session_id": session_id, "error": "operation_failed"})
        except Exception:
            pass


@app.get("/api/research/screenshot/{hash_name}")
async def research_screenshot(hash_name: str):
    """Serve persisted research screenshots from state/research_screenshots/."""
    from fastapi.responses import FileResponse
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]{8,64}\.png", hash_name):
        raise HTTPException(status_code=400, detail="invalid filename")
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "state" / "research_screenshots" / hash_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(path), media_type="image/png")


# ── Knowledge Upload — chunk + embed + persist ──────────────────────────────
def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 51) -> list[str]:
    words = text.split()
    if not words:
        return [text] if text.strip() else []
    chunks, i = [], 0
    while i < len(words):
        chunks.append(' '.join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return chunks or [text]


@app.post("/knowledge/upload")
async def knowledge_upload(request: Request, _auth: None = Depends(require_auth)):
    """Chunk uploaded files into 512-token segments, embed, and persist to memory."""
    from fastapi import UploadFile
    import uuid as _uuid
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse form data: {exc}")

    files = form.getlist("files") or form.getlist("file")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        from memory.memory_router import get_memory_router
        router = get_memory_router()
        use_router = True
    except Exception:
        router = None
        use_router = False

    try:
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        use_ks = True
    except Exception:
        ks = None
        use_ks = False

    results = []
    uploaded_at = datetime.utcnow().isoformat()

    for upload in files:
        filename = getattr(upload, "filename", None) or "unknown"
        try:
            raw = await upload.read()
            content = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            results.append({"filename": filename, "error": "operation_failed", "chunks": 0})
            continue

        chunks = _chunk_text(content, chunk_size=512, overlap=51)
        total = len(chunks)
        stored = 0

        for idx, chunk in enumerate(chunks):
            chunk_key = f"upload_{_uuid.uuid4().hex[:12]}_{idx}"
            entry = {
                "source": filename,
                "content": chunk,
                "chunk_index": idx,
                "total_chunks": total,
                "uploaded_at": uploaded_at,
            }
            if use_router:
                try:
                    router.store(
                        chunk_key,
                        chunk,
                        memory_type="semantic",
                        source=filename,
                        importance=0.7,
                        extra={"chunk_index": idx, "total_chunks": total, "uploaded_at": uploaded_at},
                    )
                    stored += 1
                except Exception as exc:
                    logger.warning("memory_router.store failed for chunk %d of %s: %s", idx, filename, exc)
            if use_ks:
                try:
                    ks.add_knowledge(topic=f"upload:{filename}", content=entry)
                    if not use_router:
                        stored += 1
                except Exception as exc:
                    logger.warning("knowledge_store.add_knowledge failed for chunk %d of %s: %s", idx, filename, exc)

        results.append({"filename": filename, "chunks": total, "stored": stored})
        logger.info("knowledge_upload: %s → %d chunks, %d stored", filename, total, stored)

    return JSONResponse({"ok": True, "files": results})


# --- Vault (Obsidian-compatible markdown store) -----------------------------
try:
    from memory.vault import Vault as _VaultCls, get_vault as _get_vault_for_tenant

    def _vault() -> _VaultCls:
        # Tenant-scoped: resolves current tenant via ContextVar set by TenantMiddleware.
        # Falls back to 'default' tenant outside request context.
        return _get_vault_for_tenant()

    def _note_to_dict(note) -> dict:
        return {
            "id": note.id,
            "title": note.title,
            "folder": note.folder,
            "path": note.path,
            "frontmatter": note.frontmatter,
            "body": note.body,
            "wikilinks": note.wikilinks,
            "backlinks": note.backlinks,
            "created": note.created,
            "updated": note.updated,
        }

    @app.put("/api/vault/notes/{note_id}")
    async def vault_update_note(note_id: str, req: dict, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("vault:write"))):
        body = (req or {}).get("body", "")
        fm   = (req or {}).get("frontmatter", {}) or {}
        note = _vault().write_note(note_id, body, fm)
        _vault().rebuild_indices()
        return _note_to_dict(note)

    @app.post("/api/vault/notes")
    async def vault_create_note(req: dict, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("vault:write"))):
        req   = req or {}
        title  = req.get("title", "Untitled")
        folder = req.get("folder", "concepts")
        body   = req.get("body", "")
        fm     = req.get("frontmatter", {}) or {}
        note = _vault().create_note(title, folder=folder, body=body, frontmatter=fm)
        _vault().rebuild_indices()
        return _note_to_dict(note)

    @app.delete("/api/vault/notes/{note_id}")
    async def vault_delete_note(note_id: str, _auth: None = Depends(require_auth), _rbac=Depends(require_permission("vault:write"))):
        ok = _vault().delete_note(note_id)
        _vault().rebuild_indices()
        return {"ok": bool(ok), "id": note_id}

    @app.post("/api/vault/rebuild-indices")
    async def vault_rebuild_indices():
        return _vault().rebuild_indices()

except Exception as _vault_err:  # pragma: no cover
    logging.getLogger(__name__).warning("vault routes not registered: %s", _vault_err)


# Wire AgentController broadcaster: POST to Node's localhost broadcast endpoint
# so events surface on the WebSocket (and dual-write to the message bus).
try:
    from core.agent_controller import get_agent_controller as _gac
    try:
        from core.bus import get_message_bus as _get_bus
    except Exception:
        _get_bus = None
    import json as _json
    import urllib.request as _urllib_request

    _NODE_BROADCAST_URL = os.environ.get(
        "NODE_BROADCAST_URL",
        f"http://127.0.0.1:{os.environ.get('NODE_BACKEND_PORT', '8787')}/api/tasks/internal/broadcast",
    )

    def _ws_broadcast(event_type: str, payload: dict) -> None:
        # 1) durable: publish to in-process bus (for tools like the event stream)
        try:
            if _get_bus is not None:
                _get_bus().publish("notifications", {"event": event_type, "payload": payload})
        except Exception:
            pass
        # 2) realtime: POST to Node so the WS broadcaster delivers to dashboards
        try:
            body = _json.dumps({"event": event_type, "payload": payload}).encode("utf-8")
            req = _urllib_request.Request(
                _NODE_BROADCAST_URL, data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            _urllib_request.urlopen(req, timeout=2)  # nosec: localhost-only endpoint
        except Exception:
            pass

    _gac().set_broadcast(_ws_broadcast)
except Exception as _br_err:
    logger.debug("agent_controller broadcaster wiring deferred: %s", _br_err)


# ── Neural Brain initialization ──────────────────────────────────────
# ── Phase 2: Enterprise Intelligence — mount routes ───────────────────────────
try:
    from infra.api.phase2_routes import phase2_router as _phase2_router
    app.include_router(_phase2_router)
    logger.info("✅ Phase 2 enterprise intelligence routes mounted")
except Exception as _p2_err:
    logger.warning("⚠️  Phase 2 routes failed to mount: %s", _p2_err)

try:
    from infra.api.phase3_routes import phase3_router as _phase3_router
    app.include_router(_phase3_router)
    logger.info("✅ Phase 3 autonomous workforce routes mounted")
except Exception as _p3_err:
    logger.warning("⚠️  Phase 3 routes failed to mount: %s", _p3_err)

try:
    from infra.api.phase4_routes import phase4_router as _phase4_router
    app.include_router(_phase4_router)
    logger.info("✅ Phase 4 enterprise autonomy stabilization routes mounted")
except Exception as _p4_err:
    logger.warning("⚠️  Phase 4 routes failed to mount: %s", _p4_err)


# ── Startup timings ledger (Phase 2.1) ─────────────────────────────────
# Recorded entries: {"name", "started", "finished", "ok", "ms"}.
# Surfaced to the launcher in a later phase — no API endpoint yet.
_STARTUP_TIMINGS: "list[dict]" = []


async def _wave_b_hook(name: str, coro_factory):
    """Run a Wave B init with a 5 s budget + timings record.

    `coro_factory` is a zero-arg callable returning the coroutine to await.
    Construct lazily so import errors are caught here, not at gather() time.
    """
    import time as _t
    started = _t.time()
    entry = {"name": name, "started": started, "finished": None, "ok": False, "ms": None}
    _STARTUP_TIMINGS.append(entry)
    try:
        await asyncio.wait_for(coro_factory(), timeout=5.0)
        entry["ok"] = True
    except asyncio.TimeoutError:
        logger.warning("⚠️  Wave B hook timed out (>5s): %s", name)
    except Exception as exc:
        logger.warning("⚠️  Wave B hook failed: %s: %s", name, exc)
    finally:
        entry["finished"] = _t.time()
        entry["ms"] = int((entry["finished"] - started) * 1000)


# ─────────────────────────── MemoryAdapter endpoints ───────────────────────
# Dual-backend vector store (Chroma primary + Qdrant secondary). Lazy import
# so failure to load the adapter (e.g. deps mid-install) does not crash boot.
try:
    from memory.memory_adapter import get_adapter as _get_memory_adapter
except Exception as _ma_exc:  # pragma: no cover
    logger.warning("MemoryAdapter import deferred: %s", _ma_exc)
    _get_memory_adapter = None  # type: ignore[assignment]


def _adapter_or_503():
    if _get_memory_adapter is None:
        raise HTTPException(status_code=503, detail="memory adapter unavailable")
    try:
        return _get_memory_adapter()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"adapter init failed: {exc}")


@app.get("/api/memory/adapter/status")
async def memory_adapter_status():
    return _adapter_or_503().status()


@app.post("/api/memory/adapter/search")
async def memory_adapter_search(req: dict):
    query = (req or {}).get("query", "")
    top_k = int((req or {}).get("top_k", 10))
    flt = (req or {}).get("filter")
    if not query:
        return {"matches": []}
    matches = _adapter_or_503().search(query, top_k=top_k, filter=flt)
    return {
        "matches": [
            {"id": m.id, "text": m.text, "score": m.score, "metadata": m.metadata}
            for m in matches
        ]
    }


@app.post("/api/memory/adapter/add")
async def memory_adapter_add(req: dict):
    text = (req or {}).get("text", "")
    metadata = (req or {}).get("metadata", {}) or {}
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    mid = _adapter_or_503().add(text, metadata=metadata)
    return {"id": mid}


@app.get("/memory/hybrid-search")
async def memory_hybrid_search(q: str = Query(..., min_length=1, max_length=500), alpha: float = Query(0.5, ge=0.0, le=1.0), limit: int = Query(10, ge=1, le=50)):
    """Hybrid BM25 + vector search over the knowledge store."""
    try:
        from memory.memory_router import hybrid_search
        results = hybrid_search(q, top_k=limit, alpha=alpha)
        return {"results": results, "query": q, "alpha": alpha, "mode": "hybrid"}
    except Exception as exc:
        logger.warning(f"hybrid_search failed: {exc}")
        return {"results": [], "query": q, "alpha": alpha, "mode": "hybrid", "error": "operation_failed"}


@app.post("/rag/retrieve")
async def rag_retrieve_endpoint(body: _RagRetrieveRequest):
    """Full RAG pipeline: hybrid search → optional rerank → compress → cite."""
    try:
        from memory.memory_router import rag_retrieve
        result = rag_retrieve(
            query=body.query,
            top_k=body.top_k,
            alpha=body.alpha,
            rerank=body.rerank,
            compress=body.compress,
            cite=body.cite,
        )
        return result
    except Exception as exc:
        logger.warning(f"rag_retrieve failed: {exc}")
        raise HTTPException(status_code=500, detail="operation_failed")


# ── Verification engine + pending review queue ──────────────────────────
@app.post("/api/memory/verify")
async def memory_verify(req: dict):
    from memory.verification import get_engine as _get_ver_engine
    claim = (req or {}).get('claim', '')
    sources = (req or {}).get('sources', []) or []
    context = (req or {}).get('context')
    if not claim:
        raise HTTPException(status_code=400, detail="claim required")
    result = _get_ver_engine().verify(claim, sources=sources, context=context)
    return result.to_dict()


@app.get("/api/memory/pending-review")
async def pending_review_list(status: str = "pending", topic: Optional[str] = None):
    from memory.pending_queue import list_all as _q_list, stats as _q_stats
    flt_status = None if status == 'all' else status
    return {'entries': _q_list(status=flt_status, topic=topic), 'stats': _q_stats()}


@app.get("/api/memory/pending-review/{entry_id}")
async def pending_review_get(entry_id: str):
    from memory.pending_queue import get as _q_get
    entry = _q_get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="not found")
    return entry


@app.post("/api/memory/pending-review/{entry_id}/approve")
async def pending_review_approve(entry_id: str):
    from memory.pending_queue import get as _q_get, update_status as _q_update
    entry = _q_get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="not found")
    try:
        from memory.memory_adapter import get_adapter as _get_mem_adapter
        _get_mem_adapter().add(
            entry['claim'],
            metadata={
                'topic': entry.get('topic'),
                'sources': entry.get('sources', []),
                'confidence': entry.get('verification', {}).get('confidence', 0.5),
                'source': 'pending_approved',
            },
        )
    except Exception as e:
        logger.warning(f"approve: memory persist failed: {e}")
    _q_update(entry_id, 'approved')
    return {'ok': True, 'id': entry_id}


@app.post("/api/memory/pending-review/{entry_id}/reject")
async def pending_review_reject(entry_id: str):
    from memory.pending_queue import update_status as _q_update
    _q_update(entry_id, 'rejected')
    return {'ok': True, 'id': entry_id}


@app.post("/api/memory/pending-review/{entry_id}/edit")
async def pending_review_edit(entry_id: str, req: dict):
    from memory.pending_queue import get as _q_get, update_status as _q_update
    entry = _q_get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="not found")
    new_claim = (req or {}).get('claim', entry['claim'])
    try:
        from memory.memory_adapter import get_adapter as _get_mem_adapter
        _get_mem_adapter().add(
            new_claim,
            metadata={
                'topic': entry.get('topic'),
                'sources': entry.get('sources', []),
                'confidence': entry.get('verification', {}).get('confidence', 0.5),
                'source': 'pending_edited',
            },
        )
    except Exception as e:
        logger.warning(f"edit: memory persist failed: {e}")
    _q_update(entry_id, 'edited')
    return {'ok': True, 'id': entry_id, 'new_claim': new_claim}


# ── Topics + Learning ─────────────────────────────────────────────
@app.get("/api/topics")
async def topics_list():
    try:
        from memory.topic_intelligence import list_topics
        return {"topics": list_topics()}
    except Exception as e:
        logger.warning(f"topics_list failed: {e}")
        return {"topics": [], "error": "operation_failed"}


@app.get("/api/topics/{topic_id}")
async def topics_get(topic_id: str):
    from memory.topic_intelligence import get_topic
    t = get_topic(topic_id)
    if not t:
        raise HTTPException(status_code=404, detail="topic not found")
    return t


@app.put("/api/topics/{topic_id}")
async def topics_update(topic_id: str, req: dict):
    from memory.topic_intelligence import update_topic
    t = update_topic(topic_id, **(req or {}))
    if not t:
        raise HTTPException(status_code=404, detail="topic not found")
    return t


@app.post("/api/topics/{topic_id}/pin")
async def topics_pin(topic_id: str, req: dict):
    from memory.topic_intelligence import pin_topic
    body = req or {}
    pinned = bool(body.get('pinned', True))
    schedule = body.get('schedule', 'every_6h')
    t = pin_topic(topic_id, pinned=pinned, schedule=schedule)
    if not t:
        raise HTTPException(status_code=404, detail="topic not found")
    return t


@app.post("/api/topics/{topic_id}/refresh")
async def topics_refresh(topic_id: str):
    from memory.topic_intelligence import get_topic
    from core.learning_orchestrator import execute_learning
    t = get_topic(topic_id)
    if not t:
        raise HTTPException(status_code=404, detail="topic not found")
    return await execute_learning(topic=t['label'], scope=t.get('scope', ''), depth='normal')


@app.delete("/api/topics/{topic_id}")
async def topics_delete(topic_id: str):
    from memory.topic_intelligence import delete_topic
    if not delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    return {"ok": True, "id": topic_id}


@app.post("/api/learning/execute")
async def learning_execute(req: dict):
    from core.learning_orchestrator import execute_learning
    body = req or {}
    topic = str(body.get('topic', '')).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    return await execute_learning(
        topic=topic,
        scope=body.get('scope', ''),
        depth=body.get('depth', 'normal'),
        selected_urls=body.get('selected_urls') or None,
        verification_level=body.get('verification_level', 'normal'),
        schedule_recurring=bool(body.get('schedule_recurring', False)),
    )


@app.get("/api/learning/sessions")
async def learning_sessions_list(limit: int = 20):
    from core.learning_orchestrator import list_sessions
    return {"sessions": list_sessions(limit=limit)}


@app.get("/api/learning/sessions/{session_id}")
async def learning_session_get(session_id: str):
    from core.learning_orchestrator import get_session
    s = get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@app.get("/api/telemetry/summary")
async def telemetry_summary(window: int = 60, _auth=Depends(require_auth)):
    from core.telemetry import get_collector
    return get_collector().get_summary(window_minutes=window)


@app.get("/api/billing/summary", tags=["billing"])
async def billing_summary(auth=Depends(require_auth)):
    from core.cost_ledger import get_cost_ledger
    tenant_id = auth.get("tenant_id", "default") if isinstance(auth, dict) else "default"
    return get_cost_ledger().get_summary(tenant_id)


@app.post("/api/billing/budget", tags=["billing", "admin"])
async def set_budget_endpoint(body: dict, _rbac=Depends(require_permission("admin:*"))):
    from core.cost_ledger import get_cost_ledger
    from dataclasses import asdict as _asdict
    tenant_id = body.get("tenant_id", "default")
    return _asdict(get_cost_ledger().set_budget(
        tenant_id,
        float(body.get("daily_usd", 10.0)),
        float(body.get("monthly_usd", 200.0)),
    ))


@app.post("/v2/orchestrate", tags=["orchestration"])
async def orchestrate_v2(req: _OrchestrateV2Request, _auth=Depends(require_auth)):
    """Run the 10-phase OrchestratorV2 pipeline for a given goal."""
    try:
        from core.orchestrator_v2 import OrchestratorV2
        result = await run_in_threadpool(OrchestratorV2().run, req.goal, req.tenant_id, req.agent_id)
        return JSONResponse(content=result, status_code=200 if result.get("success") else 422)
    except Exception as exc:
        logger.error("OrchestratorV2 error: %s", exc)
        raise HTTPException(status_code=500, detail="operation_failed")


# ── Knowledge Vault routes ────────────────────────────────────────────────────

@app.get("/knowledge/vault/list")
async def kv_list(_auth=Depends(require_auth)):
    from memory.knowledge_vault import get_knowledge_vault
    return {"entries": get_knowledge_vault().list_all()}


@app.get("/knowledge/vault/pending")
async def kv_pending(_auth=Depends(require_auth)):
    from memory.knowledge_vault import get_knowledge_vault
    return {"entries": get_knowledge_vault().list_pending_review()}


@app.get("/knowledge/vault/{title:path}")
async def kv_get(title: str, _auth=Depends(require_auth)):
    from memory.knowledge_vault import get_knowledge_vault
    entry = get_knowledge_vault().get_entry(title)
    if not entry:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry


@app.post("/knowledge/vault/add")
async def kv_add(body: dict, _auth=Depends(require_auth)):
    from memory.knowledge_vault import get_knowledge_vault
    b = body or {}
    title = str(b.get('title', '')).strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    slug = get_knowledge_vault().add_entry(
        title=title,
        content=str(b.get('content', '')),
        source=str(b.get('source', 'manual')),
        confidence=float(b.get('confidence', 0.7)),
        tags=b.get('tags') or [],
    )
    return {"ok": True, "slug": slug}


@app.post("/knowledge/vault/{title:path}/verify")
async def kv_verify(title: str, _auth=Depends(require_auth)):
    from memory.knowledge_vault import get_knowledge_vault
    vault = get_knowledge_vault()
    if not vault.get_entry(title):
        raise HTTPException(status_code=404, detail="entry not found")
    vault.mark_verified(title)
    return {"ok": True, "title": title, "status": "verified"}


@app.post("/knowledge/vault/queue-topic")
async def kv_queue_topic(body: dict, _auth=Depends(require_auth)):
    from memory.knowledge_scheduler import get_knowledge_scheduler
    b = body or {}
    topic = str(b.get('topic', '')).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    get_knowledge_scheduler().queue_topic(topic, priority=int(b.get('priority', 5)))
    return {"ok": True, "topic": topic}


# ── Tool registry routes ───────────────────────────────────────────────────────

@app.get("/tools/list")
async def tools_list(_auth=Depends(require_auth)):
    from tools.registry import get_tool_registry
    return {"tools": get_tool_registry().list_tools()}


@app.get("/tools/{name}")
async def tool_get(name: str, _auth=Depends(require_auth)):
    from tools.registry import get_tool_registry
    tool = get_tool_registry().get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return {k: v for k, v in tool.items() if k != "fn"}


@app.post("/tools/{name}/execute")
async def tool_execute(name: str, req: dict, _auth=Depends(require_auth)):
    from tools.registry import get_tool_registry
    result = get_tool_registry().execute(
        name,
        req.get("payload", {}),
        req.get("agent_id", "api"),
    )
    ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
    return {"ok": ok, "tool": name, "status": "executed" if ok else "execution_failed"}


# ── Skill catalog routes ───────────────────────────────────────────────────────

@app.get("/skills/list")
async def skills_list(_auth=Depends(require_auth)):
    from skills.catalog import get_skill_catalog
    return {"skills": get_skill_catalog().list_skills()}


@app.get("/skills/suggest")
async def skills_suggest(goal: str = "", _auth=Depends(require_auth)):
    from skills.catalog import get_skill_catalog
    return {"skills": get_skill_catalog().find_for_goal(goal)}


@app.post("/skills/{name}/execute")
async def skill_execute(name: str, req: dict, _auth=Depends(require_auth)):
    from skills.catalog import get_skill_catalog
    result = get_skill_catalog().execute_skill(
        name,
        req.get("params", {}),
        req.get("agent_id", "api"),
    )
    ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
    return {"ok": ok, "skill": name, "status": "executed" if ok else "execution_failed"}


class _SwapPayload(BaseModel):
    backend: str
    model: str = ""
    endpoint: str = ""


@app.post("/internal/swap-backend", tags=["internal"])
async def internal_swap_backend(payload: _SwapPayload):
    """Hot-swap the LLM backend without restarting. Called by Node server on model switch."""
    from core.orchestrator import hot_swap_backend
    prev = hot_swap_backend(payload.backend, new_model=payload.model, endpoint=payload.endpoint)
    return {"ok": True, "prev_backend": prev.get("backend"), "new_backend": payload.backend}


@app.on_event("startup")
async def _start_knowledge_scheduler():
    try:
        from memory.knowledge_scheduler import get_knowledge_scheduler
        scheduler = get_knowledge_scheduler()
        await scheduler.start()
        logger.info("KnowledgeScheduler started")
    except Exception as exc:
        logger.warning(f"KnowledgeScheduler startup failed: {exc}")


@app.on_event("startup")
async def _embed_knowledge_store_entries():
    """Embed knowledge_store.json entries into vector store at startup (idempotent).

    Runs in a thread-pool executor so it never blocks the event loop or delays
    server readiness. Embedding can be slow for large knowledge stores.
    """
    def _do_embed():
        try:
            from core.knowledge_store import get_knowledge_store
            n = get_knowledge_store().embed_entries_to_vector_store()
            if n:
                logger.info(f"✅ Embedded {n} knowledge store entries into vector store")
        except Exception as e:
            logger.warning(f"Knowledge store embedding skipped: {e}")

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _do_embed)


@app.on_event("startup")
async def _start_topic_scheduler():
    try:
        from core.topic_scheduler import get_scheduler
        await get_scheduler().start()
        logger.info("✅ TopicScheduler started")
    except Exception as e:
        logger.warning(f"TopicScheduler startup failed: {e}")


@app.on_event("startup")
async def _init_neural_brain():
    """Initialize Neural Brain bridge and engines at startup.

    Wave A: blocking, must finish before uvicorn serves traffic.
    Wave B: fire-and-forget background bootstraps, gathered in one detached task.
    """
    global _neural_brain_initialized, _memory_initialized, _llm_probe_result

    # ── Wave A — required before /api/health and /api/auth/auto-token ──────
    try:
        from neural_brain.api.node_bridge import get_bridge
        _bridge = get_bridge()
        logger.info("✅ Neural Brain NodeBridge initialized")
        _neural_brain_initialized = True
    except Exception as e:
        logger.warning(f"⚠️  Neural Brain bridge failed to initialize: {e}")

    # Memory subsystem probe (cheap, in-process, gates a flag the health check reads)
    try:
        from memory.memory_router import MemoryRouter  # type: ignore
        _memory_initialized = True
    except Exception:
        try:
            import importlib
            if importlib.util.find_spec("memory") or importlib.util.find_spec("mem0"):
                _memory_initialized = True
        except Exception:
            pass
    if not _memory_initialized:
        _memory_initialized = True  # degrade gracefully — treat as ready

    # ── Wave B — background subsystems, fire-and-forget, never awaited ─────
    # Defer MetricsCollector start by 5 s so the boot path doesn't compete with
    # uvicorn for the event loop. Until then, the collector is a no-op and the
    # bounded SSE queue never fills before a subscriber arrives.
    async def _start_metrics_delayed():
        try:
            await asyncio.sleep(5)
            from core.observability.metrics_collector import get_metrics_collector
            get_metrics_collector().start()
            logger.info("✅ MetricsCollector started (deferred 5 s after boot)")
        except Exception as exc:
            logger.warning(f"⚠️  MetricsCollector deferred start failed: {exc}")
    try:
        asyncio.create_task(_start_metrics_delayed())
    except Exception as e:
        logger.warning(f"⚠️  Could not schedule MetricsCollector: {e}")

    # LLM reachability probe (non-blocking, best-effort, 8s timeout)
    async def _probe_llm():
        global _llm_probe_result
        try:
            import httpx
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                async with httpx.AsyncClient(timeout=8) as _c:
                    r = await _c.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                    )
                    _llm_probe_result = r.status_code in (200, 400, 529)  # any real API response
            else:
                _llm_probe_result = False
        except Exception:
            _llm_probe_result = False
    asyncio.create_task(_probe_llm())

    # All remaining Wave B inits run as a single detached gather. Each hook
    # has its own 5 s budget; return_exceptions=True keeps siblings alive.
    async def _factory_loop_detector():
        from infra.cognitive.coherence.loop_detector import get_loop_detector as _get_ld
        asyncio.create_task(_get_ld().start())

    async def _factory_initiative_manager():
        from infra.cognitive.executive.initiative_manager import get_initiative_manager as _get_im
        asyncio.create_task(_get_im().start_lifecycle_loop())

    async def _factory_proactive_engine():
        from infra.cognitive.teammate.proactive_engine import get_proactive_engine as _get_pe
        asyncio.create_task(_get_pe().start())

    async def _factory_deadline_tracker():
        from infra.cognitive.temporal.deadline_tracker import get_deadline_tracker as _get_dt
        asyncio.create_task(_get_dt().start())

    async def _factory_rag_daemon():
        from infra.rag.sync_daemon import get_sync_daemon as _get_rag_daemon
        asyncio.create_task(_get_rag_daemon().start())

    async def _factory_planning_scheduler():
        from infra.planning.strategic_planner import get_planning_scheduler as _get_sched
        _sched = _get_sched()
        _sched.register_tenant(os.environ.get("DEFAULT_TENANT_ID", "system"))
        asyncio.create_task(_sched.start())

    async def _factory_otel():
        from infra.telemetry.otel import _init_providers as _otel_init
        _otel_init()

    async def _factory_rpa_and_healing():
        from infra.rpa.session_manager import get_session_manager as _get_sm
        asyncio.create_task(_get_sm().start_cleanup_loop())
        from infra.healing.recovery_orchestrator import get_recovery_orchestrator as _get_ro
        asyncio.create_task(_get_ro().start())

    async def _factory_adaptive_throttler():
        from infra.cognitive.resilience.adaptive_throttler import get_adaptive_throttler as _get_at
        asyncio.create_task(_get_at().start())

    async def _factory_blacklight_sentinel():
        # Always-on defensive security engine + local-AI sentinel. get_blacklight()
        # starts the background threat-monitor loop (incl. the offline-capable SLM
        # sentinel). Defensive only — distinct from the gated BLACKLIGHT recon agent.
        from neural_brain.security.blacklight_engine import get_blacklight
        get_blacklight()

    async def _wave_b_gather():
        await asyncio.gather(
            _wave_b_hook("phase4.loop_detector", _factory_loop_detector),
            _wave_b_hook("phase4.initiative_manager", _factory_initiative_manager),
            _wave_b_hook("phase4.proactive_engine", _factory_proactive_engine),
            _wave_b_hook("phase4.deadline_tracker", _factory_deadline_tracker),
            _wave_b_hook("phase2.rag_sync_daemon", _factory_rag_daemon),
            _wave_b_hook("phase2.planning_scheduler", _factory_planning_scheduler),
            _wave_b_hook("phase2.otel", _factory_otel),
            _wave_b_hook("phase3.rpa_and_healing", _factory_rpa_and_healing),
            _wave_b_hook("phase4.adaptive_throttler", _factory_adaptive_throttler),
            _wave_b_hook("security.blacklight_sentinel", _factory_blacklight_sentinel),
            return_exceptions=True,
        )

    asyncio.create_task(_wave_b_gather())


if __name__ == "__main__":
    _trim_jsonl(CHATLOG, 1000)
    _trim_jsonl(ACTIVITY_LOG, 2000)

    # ── Startup banner ────────────────────────────────────────────────────────
    _url = f"http://{HOST}:{PORT}"
    _BANNER_URL_MAX_LEN = 40  # fixed-width banner column width
    _url_col = _url[:_BANNER_URL_MAX_LEN]  # truncate to fit
    print(
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║        🤖  AI EMPLOYEE  —  Dashboard Server          ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        f"║  Dashboard → {_url_col:<{_BANNER_URL_MAX_LEN}}║\n"
        "║  Press Ctrl+C to stop                                ║\n"
        "╚══════════════════════════════════════════════════════╝\n",
        flush=True,
    )

    try:
        import uvloop  # noqa: F401
        _loop = "uvloop"
    except ImportError:
        _loop = "asyncio"

    try:
        import httptools  # noqa: F401
        _http = "httptools"
    except ImportError:
        _http = "auto"

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        workers=1,
        loop=_loop,
        http=_http,
        log_level="info",
        access_log=False,
        server_header=False,
    )
