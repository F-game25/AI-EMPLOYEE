"""Discord Bot — admin control panel for the AI follow-up system.

Connects to Discord as a bot and provides commands to manage the CRM and
trigger follow-ups without leaving Discord.

Commands:
    !followup run              — process all leads that are due for a follow-up
    !followup status           — show follow-up stats per lead
    !followup lead <id>        — force a follow-up for a specific lead
    !lead add <name>|<niche>|<phone>  — add a new lead (pipe-separated)
    !lead list                 — list all leads in the CRM
    !lead show <id>            — show full details of a lead
    !lead lost <id>            — manually mark a lead as lost
    !help                      — show this command overview

Config env vars:
    DISCORD_BOT_TOKEN         — Discord bot token (REQUIRED)
    DISCORD_COMMAND_PREFIX    — command prefix (default: !)
    AI_HOME                   — path to the AI Employee data directory
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── AI_HOME / path setup ──────────────────────────────────────────────────────

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
CRM_FILE = AI_HOME / "state" / "lead-generator-crm.json"
STATE_FILE = AI_HOME / "state" / "discord-bot.state.json"

# Add follow-up-agent to path so we can reuse its functions directly
_followup_path = AI_HOME / "bots" / "follow-up-agent"
if str(_followup_path) not in sys.path:
    sys.path.insert(0, str(_followup_path))

try:
    from follow_up_agent import (  # type: ignore
        run_followups,
        followup_lead,
        followup_status,
        reset_followup,
        load_crm as _fu_load_crm,
        save_crm as _fu_save_crm,
        now_iso,
    )
    _FOLLOWUP_AVAILABLE = True
except ImportError:
    _FOLLOWUP_AVAILABLE = False

# Add financial-deepsearch to path so we can reuse its functions directly
_deepsearch_path = AI_HOME / "bots" / "financial-deepsearch"
if str(_deepsearch_path) not in sys.path:
    sys.path.insert(0, str(_deepsearch_path))

try:
    from financial_deepsearch import (  # type: ignore
        cmd_company as _ds_company,
        cmd_market as _ds_market,
        cmd_news as _ds_news,
        cmd_compare as _ds_compare,
        cmd_macro as _ds_macro,
        cmd_sec as _ds_sec,
        cmd_earnings as _ds_earnings,
        cmd_status as _ds_status,
    )
    _DEEPSEARCH_AVAILABLE = True
except ImportError:
    _DEEPSEARCH_AVAILABLE = False

import discord
from discord.ext import commands

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(asctime)s [discord-bot] %(levelname)s %(message)s",
)
logger = logging.getLogger("discord-bot")

# ── Config ────────────────────────────────────────────────────────────────────

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
COMMAND_PREFIX = os.environ.get("DISCORD_COMMAND_PREFIX", "!")

# Maximum number of characters to show from the last message in !lead show
MAX_PREVIEW_LENGTH = 300

# ── Fallback CRM helpers (used when follow_up_agent import fails) ─────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_crm() -> dict:
    if _FOLLOWUP_AVAILABLE:
        return _fu_load_crm()
    if not CRM_FILE.exists():
        return {"items": []}
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return {"items": []}


def _save_crm(crm: dict) -> None:
    if _FOLLOWUP_AVAILABLE:
        _fu_save_crm(crm)
        return
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(crm, indent=2))


def _new_lead(name: str, niche: str, phone: str) -> dict:
    ts = _now_iso()
    return {
        "id": str(uuid.uuid4())[:8],
        "name": name.strip(),
        "niche": niche.strip(),
        "location": "",
        "website": "",
        "phone": phone.strip(),
        "email": "",
        "status": "new",
        "outreach_messages": [],
        "notes": "",
        "created_at": ts,
        "updated_at": ts,
        "next_followup": "",
    }


# ── Status emoji helper ───────────────────────────────────────────────────────

_STATUS_EMOJI = {
    "new": "🆕",
    "contacted": "📤",
    "replied": "💬",
    "qualified": "✅",
    "appointment": "📅",
    "won": "🏆",
    "lost": "❌",
}


def _emoji(status: str) -> str:
    return _STATUS_EMOJI.get(status, "❓")


# ── Discord bot setup ─────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready() -> None:
    logger.info("Discord bot logged in as %s (id=%s)", bot.user, bot.user.id)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "bot": "discord-bot",
        "status": "running",
        "ts": _now_iso(),
        "discord_user": str(bot.user),
    }, indent=2))


# ── !help ─────────────────────────────────────────────────────────────────────


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    """Show available commands."""
    lines = [
        "**AI Follow-Up Control Panel**",
        "",
        "`!followup run` — process all leads due for a follow-up",
        "`!followup status` — show follow-up stats per lead",
        "`!followup lead <id>` — force a follow-up for a specific lead",
        "`!followup reset <id>` — reset the follow-up counter for a lead",
        "",
        "`!lead add <name>|<niche>|<phone>` — add a new lead (pipe-separated)",
        "`!lead list` — list all leads",
        "`!lead show <id>` — show full details of a lead",
        "`!lead lost <id>` — manually mark a lead as lost",
        "",
        "**Financial DeepSearch (Dexter AI)**",
        "`!deepsearch company <ticker>` — comprehensive company deep-dive",
        "`!deepsearch market <sector>` — sector market analysis",
        "`!deepsearch news <ticker>` — latest financial news synthesis",
        "`!deepsearch compare <t1> vs <t2>` — side-by-side company comparison",
        "`!deepsearch macro <topic>` — macroeconomic analysis",
        "`!deepsearch sec <ticker>` — SEC EDGAR filing insights",
        "`!deepsearch earnings <ticker>` — earnings deep dive",
        "`!deepsearch status` — recent searches & active sources",
    ]
    await ctx.send("\n".join(lines))


# ── !followup ─────────────────────────────────────────────────────────────────


@bot.group(name="followup", invoke_without_command=True)
async def followup_group(ctx: commands.Context) -> None:
    await ctx.send("Usage: `!followup run | status | lead <id> | reset <id>`")


@followup_group.command(name="run")
async def followup_run(ctx: commands.Context) -> None:
    """Process all leads due for a follow-up."""
    if not _FOLLOWUP_AVAILABLE:
        await ctx.send("❌ follow_up_agent module not available.")
        return
    await ctx.send("⏳ Processing follow-ups…")
    try:
        result = run_followups()
        # Discord has a 2000-char limit per message; split if needed
        for chunk in _split_message(result, 1900):
            await ctx.send(f"```\n{chunk}\n```")
    except Exception as exc:
        logger.exception("followup run error")
        await ctx.send(f"❌ Error: {exc}")


@followup_group.command(name="status")
async def followup_status_cmd(ctx: commands.Context) -> None:
    """Show follow-up stats for all leads."""
    if not _FOLLOWUP_AVAILABLE:
        await ctx.send("❌ follow_up_agent module not available.")
        return
    try:
        result = followup_status()
        for chunk in _split_message(result, 1900):
            await ctx.send(f"```\n{chunk}\n```")
    except Exception as exc:
        logger.exception("followup status error")
        await ctx.send(f"❌ Error: {exc}")


@followup_group.command(name="lead")
async def followup_lead_cmd(ctx: commands.Context, lead_id: str = "") -> None:
    """Force a follow-up for a specific lead."""
    if not lead_id:
        await ctx.send("Usage: `!followup lead <lead_id>`")
        return
    if not _FOLLOWUP_AVAILABLE:
        await ctx.send("❌ follow_up_agent module not available.")
        return
    await ctx.send(f"⏳ Sending follow-up for lead `{lead_id}`…")
    try:
        result = followup_lead(lead_id)
        for chunk in _split_message(result, 1900):
            await ctx.send(f"```\n{chunk}\n```")
    except Exception as exc:
        logger.exception("followup lead error")
        await ctx.send(f"❌ Error: {exc}")


@followup_group.command(name="reset")
async def followup_reset_cmd(ctx: commands.Context, lead_id: str = "") -> None:
    """Reset the follow-up counter for a lead."""
    if not lead_id:
        await ctx.send("Usage: `!followup reset <lead_id>`")
        return
    if not _FOLLOWUP_AVAILABLE:
        await ctx.send("❌ follow_up_agent module not available.")
        return
    try:
        result = reset_followup(lead_id)
        await ctx.send(f"✅ {result}")
    except Exception as exc:
        logger.exception("followup reset error")
        await ctx.send(f"❌ Error: {exc}")


# ── !lead ─────────────────────────────────────────────────────────────────────


@bot.group(name="lead", invoke_without_command=True)
async def lead_group(ctx: commands.Context) -> None:
    await ctx.send("Usage: `!lead add <name>|<niche>|<phone>` | `list` | `show <id>` | `lost <id>`")


@lead_group.command(name="add")
async def lead_add(ctx: commands.Context, *, args: str = "") -> None:
    """Add a new lead. Format: !lead add Name|Niche|+31612345678"""
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 3 or not all(parts[:3]):
        await ctx.send(
            "Usage: `!lead add <name>|<niche>|<phone>`\n"
            "Example: `!lead add John Doe|e-commerce|+31612345678`"
        )
        return
    name, niche, phone = parts[0], parts[1], parts[2]

    crm = _load_crm()
    lead = _new_lead(name, niche, phone)
    crm.setdefault("items", []).append(lead)
    _save_crm(crm)

    await ctx.send(
        f"✅ Lead added!\n"
        f"**ID:** `{lead['id']}`\n"
        f"**Name:** {lead['name']}\n"
        f"**Niche:** {lead['niche']}\n"
        f"**Phone:** {lead['phone']}\n"
        f"**Status:** {_emoji(lead['status'])} {lead['status']}"
    )
    logger.info("Lead added via Discord: %s (%s)", lead["id"], lead["name"])


@lead_group.command(name="list")
async def lead_list(ctx: commands.Context) -> None:
    """List all leads in the CRM."""
    crm = _load_crm()
    items = crm.get("items", [])
    if not items:
        await ctx.send("CRM is empty.")
        return
    lines = ["**Leads**", "```"]
    for lead in items:
        attempts = sum(
            1 for m in lead.get("outreach_messages", []) if m.get("channel") == "followup"
        )
        lines.append(
            f"[{lead['id']}] {lead['name']:<20} "
            f"{_emoji(lead['status'])} {lead['status']:<12} "
            f"follow-ups: {attempts}/5  "
            f"niche: {lead.get('niche', '')}"
        )
    lines.append("```")
    for chunk in _split_message("\n".join(lines), 1900):
        await ctx.send(chunk)


@lead_group.command(name="show")
async def lead_show(ctx: commands.Context, lead_id: str = "") -> None:
    """Show full details for a lead."""
    if not lead_id:
        await ctx.send("Usage: `!lead show <lead_id>`")
        return
    crm = _load_crm()
    lead = next((l for l in crm.get("items", []) if l["id"] == lead_id), None)
    if not lead:
        await ctx.send(f"❌ Lead `{lead_id}` not found.")
        return
    attempts = sum(
        1 for m in lead.get("outreach_messages", []) if m.get("channel") == "followup"
    )
    last_msg = ""
    if lead.get("outreach_messages"):
        last = lead["outreach_messages"][-1]
        last_msg = f"\n**Last message ({last.get('ts','')}):**\n> {last.get('message','')[:MAX_PREVIEW_LENGTH]}"
    await ctx.send(
        f"**Lead: {lead['name']}** (`{lead['id']}`)\n"
        f"**Niche:** {lead.get('niche', 'n/a')}\n"
        f"**Phone:** {lead.get('phone', 'n/a')}\n"
        f"**Status:** {_emoji(lead['status'])} {lead['status']}\n"
        f"**Follow-ups sent:** {attempts}/5\n"
        f"**Next follow-up:** {lead.get('next_followup') or 'not scheduled'}\n"
        f"**Created:** {lead.get('created_at', '')}"
        f"{last_msg}"
    )


@lead_group.command(name="lost")
async def lead_lost(ctx: commands.Context, lead_id: str = "") -> None:
    """Manually mark a lead as lost."""
    if not lead_id:
        await ctx.send("Usage: `!lead lost <lead_id>`")
        return
    crm = _load_crm()
    lead = next((l for l in crm.get("items", []) if l["id"] == lead_id), None)
    if not lead:
        await ctx.send(f"❌ Lead `{lead_id}` not found.")
        return
    lead["status"] = "lost"
    lead["updated_at"] = _now_iso()
    _save_crm(crm)
    await ctx.send(f"❌ Lead `{lead_id}` ({lead['name']}) marked as **lost**.")


# ── !deepsearch ───────────────────────────────────────────────────────────────


@bot.group(name="deepsearch", invoke_without_command=True)
async def deepsearch_group(ctx: commands.Context) -> None:
    await ctx.send(
        "Usage: `!deepsearch company <ticker>` | `market <sector>` | "
        "`news <ticker>` | `compare <t1> vs <t2>` | `macro <topic>` | "
        "`sec <ticker>` | `earnings <ticker>` | `status`"
    )


@deepsearch_group.command(name="company")
async def deepsearch_company_cmd(ctx: commands.Context, *, ticker: str = "") -> None:
    """Comprehensive company deep-dive analysis."""
    if not ticker:
        await ctx.send("Usage: `!deepsearch company <ticker>` — e.g. `!deepsearch company AAPL`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"🔬 Running deep financial search for `{ticker.upper()}`… (this may take a moment)")
    try:
        result = _ds_company(ticker)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch company error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="market")
async def deepsearch_market_cmd(ctx: commands.Context, *, sector: str = "") -> None:
    """Market sector deep analysis."""
    if not sector:
        await ctx.send("Usage: `!deepsearch market <sector>` — e.g. `!deepsearch market technology`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"📊 Analysing `{sector}` sector… (this may take a moment)")
    try:
        result = _ds_market(sector)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch market error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="news")
async def deepsearch_news_cmd(ctx: commands.Context, *, ticker: str = "") -> None:
    """Latest financial news synthesis for a ticker."""
    if not ticker:
        await ctx.send("Usage: `!deepsearch news <ticker>` — e.g. `!deepsearch news TSLA`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"📰 Gathering financial news for `{ticker.upper()}`…")
    try:
        result = _ds_news(ticker)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch news error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="compare")
async def deepsearch_compare_cmd(ctx: commands.Context, *, args: str = "") -> None:
    """Side-by-side company comparison. Format: !deepsearch compare AAPL vs MSFT"""
    if not args:
        await ctx.send("Usage: `!deepsearch compare <t1> vs <t2>` — e.g. `!deepsearch compare AAPL vs MSFT`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    parts = args.upper().split(" VS ")
    if len(parts) == 2:
        t1, t2 = parts[0].strip(), parts[1].strip()
    else:
        tokens = args.split()
        if len(tokens) >= 2:
            t1, t2 = tokens[0].upper(), tokens[-1].upper()
        else:
            await ctx.send("Usage: `!deepsearch compare AAPL vs MSFT`")
            return
    await ctx.send(f"⚖️ Comparing `{t1}` vs `{t2}`… (this may take a moment)")
    try:
        result = _ds_compare(t1, t2)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch compare error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="macro")
async def deepsearch_macro_cmd(ctx: commands.Context, *, topic: str = "") -> None:
    """Macroeconomic deep research."""
    if not topic:
        await ctx.send("Usage: `!deepsearch macro <topic>` — e.g. `!deepsearch macro inflation`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"🌍 Running macro deep-search: `{topic}`…")
    try:
        result = _ds_macro(topic)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch macro error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="sec")
async def deepsearch_sec_cmd(ctx: commands.Context, *, ticker: str = "") -> None:
    """SEC EDGAR filing insights for a ticker."""
    if not ticker:
        await ctx.send("Usage: `!deepsearch sec <ticker>` — e.g. `!deepsearch sec NVDA`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"📋 Fetching SEC filings for `{ticker.upper()}` from EDGAR…")
    try:
        result = _ds_sec(ticker)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch sec error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="earnings")
async def deepsearch_earnings_cmd(ctx: commands.Context, *, ticker: str = "") -> None:
    """Earnings history and quality analysis."""
    if not ticker:
        await ctx.send("Usage: `!deepsearch earnings <ticker>` — e.g. `!deepsearch earnings AMZN`")
        return
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    await ctx.send(f"📈 Earnings deep-dive for `{ticker.upper()}`…")
    try:
        result = _ds_earnings(ticker)
        for chunk in _split_message(result, 1900):
            await ctx.send(chunk)
    except Exception as exc:
        logger.exception("deepsearch earnings error")
        await ctx.send(f"❌ Error: {exc}")


@deepsearch_group.command(name="status")
async def deepsearch_status_cmd(ctx: commands.Context) -> None:
    """Show recent financial deep searches and active data sources."""
    if not _DEEPSEARCH_AVAILABLE:
        await ctx.send("❌ financial_deepsearch module not available.")
        return
    try:
        result = _ds_status()
        await ctx.send(result)
    except Exception as exc:
        logger.exception("deepsearch status error")
        await ctx.send(f"❌ Error: {exc}")


# ── Utility ───────────────────────────────────────────────────────────────────


def _split_message(text: str, limit: int = 1900) -> list[str]:
    """Split a long string into chunks that fit within Discord's message limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error(
            "DISCORD_BOT_TOKEN is not set. "
            "Create a bot at https://discord.com/developers/applications, "
            "copy the token, and set it in ~/.ai-employee/.env"
        )
        raise SystemExit(1)

    logger.info("Starting Discord bot (prefix='%s')…", COMMAND_PREFIX)
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
