#!/usr/bin/env python3
"""AI Employee — Safety & Health Self-Test

Runs a visible series of checks across all critical components so you can
confirm that everything is wired up correctly before going live.

Usage:
    python3 ~/.ai-employee/bots/bot_selftest.py

Or via the CLI (after install):
    ai-employee selftest

Each check prints a clear ✅ (pass) or ❌ (fail) line with a short
explanation.  A summary at the end shows the overall health score.

Exit codes:
    0  — all required checks passed
    1  — one or more required checks failed
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Setup ─────────────────────────────────────────────────────────────────────

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

_GREEN  = "\033[0;32m"
_RED    = "\033[0;31m"
_YELLOW = "\033[1;33m"
_CYAN   = "\033[0;36m"
_BOLD   = "\033[1m"
_NC     = "\033[0m"

_results: list[tuple[str, bool, str, bool]] = []  # (name, passed, detail, required)


def _ok(name: str, detail: str = "", required: bool = True) -> None:
    print(f"  {_GREEN}✅{_NC} {name}{(' — ' + detail) if detail else ''}")
    _results.append((name, True, detail, required))


def _fail(name: str, detail: str = "", required: bool = True) -> None:
    marker = f"{_RED}❌{_NC}" if required else f"{_YELLOW}⚠️ {_NC}"
    print(f"  {marker} {name}{(' — ' + detail) if detail else ''}")
    _results.append((name, False, detail, required))


def _section(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}── {title} {'─' * max(0, 44 - len(title))}{_NC}")


# ── Individual checks ─────────────────────────────────────────────────────────


def check_python_version() -> None:
    """Python 3.10+ is required."""
    v = sys.version_info
    if v >= (3, 10):
        _ok("Python version", f"{v.major}.{v.minor}.{v.micro}")
    else:
        _fail("Python version", f"{v.major}.{v.minor} — needs 3.10+")


def check_env_file() -> None:
    """~/.ai-employee/.env must exist."""
    env_path = AI_HOME / ".env"
    if env_path.exists():
        _ok(".env file", str(env_path))
    else:
        _fail(".env file", f"not found at {env_path} — run install.sh first")


def check_required_env_vars() -> None:
    """JWT_SECRET_KEY must be set (security requirement)."""
    val = os.environ.get("JWT_SECRET_KEY", "")
    if val:
        _ok("JWT_SECRET_KEY", "set ✓")
    else:
        _fail("JWT_SECRET_KEY", "not set — generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\"")


def check_state_dir() -> None:
    """State directory must exist (created by first run)."""
    state_dir = AI_HOME / "state"
    if state_dir.exists():
        _ok("State directory", str(state_dir))
    else:
        _fail("State directory", f"missing: {state_dir} — start ai-employee once first", required=False)


def check_crm_file() -> None:
    """CRM file check — optional but recommended."""
    crm_path = AI_HOME / "state" / "lead-generator-crm.json"
    if not crm_path.exists():
        _fail("CRM file", "not found — will be created on first lead generation", required=False)
        return
    try:
        data = json.loads(crm_path.read_text())
        count = len(data.get("items", []))
        _ok("CRM file", f"{count} leads in CRM")
    except Exception as exc:
        _fail("CRM file", f"JSON parse error: {exc}")


def check_discord_webhook() -> None:
    """DISCORD_WEBHOOK_URL must be set and reachable (optional)."""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        _fail("Discord webhook URL", "DISCORD_WEBHOOK_URL not set — add to .env", required=False)
        return
    if not url.startswith("https://discord.com/api/webhooks/"):
        _fail("Discord webhook URL", "URL does not look like a Discord webhook", required=False)
        return
    # Probe the webhook with a GET (Discord returns 200 with webhook info)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                _ok("Discord webhook URL", "reachable ✓")
            else:
                _fail("Discord webhook URL", f"HTTP {resp.status}", required=False)
    except Exception as exc:
        _fail("Discord webhook URL", f"not reachable: {exc}", required=False)


def check_discord_bot_token() -> None:
    """DISCORD_BOT_TOKEN must be set if the discord-bot is to be used (optional)."""
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        _fail("Discord bot token", "DISCORD_BOT_TOKEN not set — add to .env to use !commands", required=False)
        return
    # Basic format check: Discord tokens are 3 Base64url segments separated by dots
    parts = token.split(".")
    if len(parts) == 3 and all(parts):
        _ok("Discord bot token", "format OK ✓ (not verified live — start bot to confirm)")
    else:
        _fail("Discord bot token", "unexpected format — check your token", required=False)


def check_discord_notify_module() -> None:
    """discord_notify helper module must be importable."""
    _tools_path = AI_HOME / "bots" / "tools"
    if str(_tools_path) not in sys.path:
        sys.path.insert(0, str(_tools_path))
    try:
        mod = importlib.import_module("discord_notify")
        _ok("discord_notify module", "importable ✓")
        configured = mod.is_discord_configured()
        if configured:
            _ok("discord_notify configured", "DISCORD_WEBHOOK_URL loaded by module ✓")
        else:
            _fail("discord_notify configured", "DISCORD_WEBHOOK_URL not loaded — check .env", required=False)
    except ImportError as exc:
        _fail("discord_notify module", f"import failed: {exc}")


def check_discord_bot_module() -> None:
    """discord.py library must be installed for the Discord bot."""
    try:
        import importlib.metadata
        version = importlib.metadata.version("discord.py")
        _ok("discord.py library", f"v{version}")
    except importlib.metadata.PackageNotFoundError:
        _fail("discord.py library", "not installed — run: pip install discord.py", required=False)
    except Exception as exc:
        _fail("discord.py library", str(exc), required=False)


def check_whatsapp_config() -> None:
    """Twilio / WhatsApp credentials (optional)."""
    sid  = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth = os.environ.get("TWILIO_AUTH_TOKEN", "")
    frm  = os.environ.get("TWILIO_WHATSAPP_FROM", "")
    if sid and auth and frm:
        _ok("Twilio / WhatsApp config", "credentials set ✓", required=False)
    else:
        missing = [k for k, v in [
            ("TWILIO_ACCOUNT_SID", sid),
            ("TWILIO_AUTH_TOKEN", auth),
            ("TWILIO_WHATSAPP_FROM", frm),
        ] if not v]
        _fail("Twilio / WhatsApp config", f"missing: {', '.join(missing)}", required=False)


def check_ai_router() -> None:
    """AI router module must be importable and LOCAL_AI_FIRST should be enabled."""
    _router_path = AI_HOME / "bots" / "ai-router"
    if str(_router_path) not in sys.path:
        sys.path.insert(0, str(_router_path))
    try:
        mod = importlib.import_module("ai_router")
        _ok("ai_router module", "importable ✓")
        local_first = getattr(mod, "LOCAL_AI_FIRST", None)
        if local_first is True:
            _ok(
                "LOCAL_AI_FIRST routing",
                "enabled ✓ — Ollama + NIM (Layer 1) tried before paid APIs (Layer 2)",
            )
        elif local_first is False:
            _fail(
                "LOCAL_AI_FIRST routing",
                "disabled — paid cloud APIs may be called before Ollama/NIM. "
                "Remove LOCAL_AI_FIRST=0 from .env to restore two-layer routing.",
                required=False,
            )
        else:
            _fail("LOCAL_AI_FIRST routing", "attribute not found in ai_router", required=False)
    except ImportError as exc:
        _fail("ai_router module", f"import failed: {exc}")


def check_nvidia_nim_config() -> None:
    """NVIDIA NIM API key configuration check (optional but recommended)."""
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        _fail(
            "NVIDIA NIM API key",
            "NVIDIA_API_KEY not set — free models won't be used. "
            "Get a key at https://build.nvidia.com",
            required=False,
        )
        return
    if not api_key.startswith("nvapi-"):
        _fail(
            "NVIDIA NIM API key",
            "key does not start with 'nvapi-' — check your key format",
            required=False,
        )
        return
    _ok("NVIDIA NIM API key", "set (nvapi-…) ✓")


def check_nvidia_nim_client() -> None:
    """NVIDIA NIM client module must be importable."""
    _nim_path = AI_HOME / "bots" / "nvidia-nim"
    if str(_nim_path) not in sys.path:
        sys.path.insert(0, str(_nim_path))
    try:
        importlib.import_module("nim_client")
        _ok("nim_client module", "importable ✓")
    except ImportError as exc:
        _fail("nim_client module", f"import failed: {exc}", required=False)


def check_vector_memory() -> None:
    """Vector memory module must be importable."""
    _mem_path = AI_HOME / "bots" / "memory"
    if str(_mem_path) not in sys.path:
        sys.path.insert(0, str(_mem_path))
    try:
        importlib.import_module("vector_memory")
        _ok("vector_memory module", "importable ✓")
    except ImportError as exc:
        _fail("vector_memory module", f"import failed: {exc}", required=False)


def check_lead_intelligence_agents() -> None:
    """Lead intelligence agent modules must be importable."""
    _li_path = AI_HOME / "bots" / "lead-intelligence"
    if str(_li_path) not in sys.path:
        sys.path.insert(0, str(_li_path))
    for module_name in (
        "lead_hunter_agent",
        "lead_scoring_agent",
        "outreach_agent",
        "deal_matching_agent",
    ):
        try:
            importlib.import_module(module_name)
            _ok(f"{module_name} module", "importable ✓")
        except ImportError as exc:
            _fail(f"{module_name} module", f"import failed: {exc}", required=False)


def check_follow_up_agent() -> None:
    """follow_up_agent module must be importable."""
    _fu_path = AI_HOME / "bots" / "follow-up-agent"
    if str(_fu_path) not in sys.path:
        sys.path.insert(0, str(_fu_path))
    try:
        importlib.import_module("follow_up_agent")
        _ok("follow_up_agent module", "importable ✓")
    except ImportError as exc:
        _fail("follow_up_agent module", f"import failed: {exc}")


def _check_bot_module(bot_dir_name: str, module_name: str) -> None:
    """Check that a bot's Python module is importable and its run.sh is executable."""
    bot_dir = AI_HOME / "bots" / bot_dir_name
    if str(bot_dir) not in sys.path:
        sys.path.insert(0, str(bot_dir))
    try:
        importlib.import_module(module_name)
        _ok(f"{module_name} module", "importable ✓")
    except ImportError as exc:
        _fail(f"{module_name} module", f"import failed: {exc}")
    run_sh = bot_dir / "run.sh"
    if run_sh.exists() and run_sh.stat().st_mode & 0o111:
        _ok(f"{bot_dir_name} run.sh", "executable ✓")
    else:
        _fail(f"{bot_dir_name} run.sh", "not executable — run: chmod +x run.sh")


def check_engineering_assistant() -> None:
    """engineering_assistant module must be importable and its run.sh executable."""
    _check_bot_module("engineering-assistant", "engineering_assistant")


def check_ui_designer() -> None:
    """ui_designer module must be importable and its run.sh executable."""
    _check_bot_module("ui-designer", "ui_designer")


def check_qa_tester() -> None:
    """qa_tester module must be importable and its run.sh executable."""
    _check_bot_module("qa-tester", "qa_tester")


def check_paid_media_specialist() -> None:
    """paid_media_specialist module must be importable and its run.sh executable."""
    _check_bot_module("paid-media-specialist", "paid_media_specialist")


def check_financial_deepsearch() -> None:
    """financial_deepsearch module must be importable and its run.sh executable."""
    _check_bot_module("financial-deepsearch", "financial_deepsearch")


def check_blacklight() -> None:
    """blacklight module must be importable and its run.sh executable."""
    _check_bot_module("blacklight", "blacklight")


def check_discord_bot_state() -> None:
    """If the Discord bot ran before, its state file should say 'running'."""
    state = AI_HOME / "state" / "discord-bot.state.json"
    if not state.exists():
        _fail("Discord bot state", "never started — run: python3 discord_bot.py", required=False)
        return
    try:
        data = json.loads(state.read_text())
        status = data.get("status", "unknown")
        user   = data.get("discord_user", "?")
        ts     = data.get("ts", "?")
        if status == "running":
            _ok("Discord bot state", f"running as {user} (last seen {ts})")
        else:
            _fail("Discord bot state", f"status={status} — bot may have stopped", required=False)
    except Exception as exc:
        _fail("Discord bot state", f"could not read state: {exc}", required=False)


def check_gateway_reachable() -> None:
    """OpenClaw gateway should be reachable at localhost:18789."""
    url = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
    try:
        req = urllib.request.Request(f"{url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status < 400:
                _ok("OpenClaw gateway", f"reachable at {url}")
            else:
                _fail("OpenClaw gateway", f"HTTP {resp.status}", required=False)
    except Exception:
        _fail("OpenClaw gateway", f"not reachable at {url} — run: cd ~/.ai-employee && ./start.sh", required=False)


def check_problem_solver_ui() -> None:
    """Problem Solver UI should be reachable at localhost:8787 (default)."""
    port = os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787")
    url  = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status < 400:
                _ok("Problem Solver UI", f"reachable at {url}")
            else:
                _fail("Problem Solver UI", f"HTTP {resp.status}", required=False)
    except Exception:
        _fail("Problem Solver UI", f"not reachable at {url} — run: ./start.sh", required=False)


def send_test_discord_message() -> None:
    """Optionally fire a live test message to Discord (only when --live flag given)."""
    if "--live" not in sys.argv:
        return
    _tools_path = AI_HOME / "bots" / "tools"
    if str(_tools_path) not in sys.path:
        sys.path.insert(0, str(_tools_path))
    try:
        from discord_notify import notify_discord, is_discord_configured  # type: ignore
        if not is_discord_configured():
            _fail("Live Discord test message", "DISCORD_WEBHOOK_URL not set", required=False)
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ok_sent = notify_discord(f"🧪 AI Employee selftest — live ping {ts}")
        if ok_sent:
            _ok("Live Discord test message", "sent ✓ — check your Discord channel")
        else:
            _fail("Live Discord test message", "send failed — check DISCORD_WEBHOOK_URL", required=False)
    except Exception as exc:
        _fail("Live Discord test message", str(exc), required=False)


# ── Runner ────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"\n{_BOLD}{'=' * 52}{_NC}")
    print(f"{_BOLD}  🧪 AI Employee — Safety & Health Self-Test{_NC}")
    print(f"{_BOLD}{'=' * 52}{_NC}")
    print(f"  AI_HOME : {AI_HOME}")
    print(f"  Time    : {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    if "--live" in sys.argv:
        print(f"  Mode    : {_YELLOW}LIVE (will send a real Discord message){_NC}")
    else:
        print(f"  Mode    : dry-run  (add --live to also test real Discord send)")

    _section("Environment")
    check_python_version()
    check_env_file()
    check_required_env_vars()
    check_state_dir()
    check_crm_file()

    _section("Discord")
    check_discord_notify_module()
    check_discord_webhook()
    check_discord_bot_token()
    check_discord_bot_module()
    check_discord_bot_state()
    send_test_discord_message()

    _section("Integrations")
    check_whatsapp_config()

    _section("Bot Modules")
    check_ai_router()
    check_follow_up_agent()
    check_engineering_assistant()
    check_ui_designer()
    check_qa_tester()
    check_paid_media_specialist()
    check_financial_deepsearch()
    check_blacklight()

    _section("NVIDIA NIM Integration")
    check_nvidia_nim_config()
    check_nvidia_nim_client()
    check_vector_memory()
    check_lead_intelligence_agents()

    _section("Running Services")
    check_gateway_reachable()
    check_problem_solver_ui()

    # ── Summary ───────────────────────────────────────────────────────────────
    total    = len(_results)
    passed   = sum(1 for _, ok, _, _ in _results if ok)
    req_fail = sum(1 for _, ok, _, req in _results if not ok and req)
    opt_fail = sum(1 for _, ok, _, req in _results if not ok and not req)

    print(f"\n{_BOLD}{'=' * 52}{_NC}")
    print(f"{_BOLD}  Result: {passed}/{total} checks passed{_NC}")
    if req_fail:
        print(f"  {_RED}❌ {req_fail} required check(s) FAILED — fix before going live{_NC}")
    if opt_fail:
        print(f"  {_YELLOW}⚠️  {opt_fail} optional check(s) need attention{_NC}")
    if req_fail == 0:
        print(f"  {_GREEN}✅ All required checks passed — bot is safe to run!{_NC}")
    print(f"{_BOLD}{'=' * 52}{_NC}\n")

    sys.exit(1 if req_fail else 0)


if __name__ == "__main__":
    # Load .env before running checks so env vars are available
    env_path = AI_HOME / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    main()
