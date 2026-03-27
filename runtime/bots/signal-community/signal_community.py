"""Signal Community Bot — crypto/trading signal community management.

Reads state from polymarket-trader and mirofish-researcher bots, generates
formatted signal messages for Telegram and Discord, manages community content,
and tracks signal performance over time.

Commands:
  signals                               — show current top signals
  signal post <analysis>                — generate a formatted signal post
  signal daily                          — generate daily market summary
  signal performance                    — show signal win/loss tracking
  signal telegram                       — format signals as Telegram message blocks
  signal discord                        — format signals as Discord markdown
  signal alert <market> <dir> <conf>    — generate alert for a specific market
  community update                      — generate community newsletter/update
  signal status                         — bot status and total signals generated
"""
import json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE   = AI_HOME / "state" / "signal-community.state.json"
CHATLOG      = AI_HOME / "state" / "chatlog.jsonl"
POSTS_LOG    = AI_HOME / "state" / "signal-community-posts.jsonl"
POLY_STATE   = AI_HOME / "state" / "polymarket-trader.state.json"
MIRO_STATE   = AI_HOME / "state" / "mirofish-researcher.state.json"
PERF_STATE   = AI_HOME / "state" / "trader-strategy-performance.json"

POLL_INTERVAL        = int(os.environ.get("SIGNAL_COMMUNITY_POLL_INTERVAL", "5"))
COMMUNITY_NAME       = os.environ.get("SIGNAL_COMMUNITY_NAME", "AI Trading Signals")
SIGNAL_MIN_CONF      = float(os.environ.get("SIGNAL_MIN_CONFIDENCE", "0.6"))
TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL  = os.environ.get("DISCORD_WEBHOOK_URL", "")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai as _query_ai  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── helpers ──────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def load_chatlog():
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []

def append_chatlog(e):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")

def append_post(post: dict):
    POSTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTS_LOG, "a") as f:
        f.write(json.dumps(post) + "\n")

def load_posts():
    if not POSTS_LOG.exists():
        return []
    try:
        return [json.loads(l) for l in POSTS_LOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []

def load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable — install deps]"
    return (_query_ai(prompt, system_prompt=system) or {}).get("answer", "")

def _conf_bar(conf: float) -> str:
    filled = int(conf * 10)
    return "█" * filled + "░" * (10 - filled)


# ── signal extraction ─────────────────────────────────────────────────────────

def get_signals_from_state() -> list[dict]:
    """Pull signals from polymarket-trader and mirofish-researcher state files."""
    signals: list[dict] = []
    poly = load_json_file(POLY_STATE)
    miro = load_json_file(MIRO_STATE)

    # Extract from polymarket state
    for action in poly.get("actions", []):
        conf = float(action.get("confidence", 0))
        if conf >= SIGNAL_MIN_CONF:
            signals.append({
                "source": "polymarket",
                "market": action.get("market", "Unknown"),
                "direction": action.get("direction", "YES"),
                "confidence": conf,
                "rationale": action.get("rationale", ""),
                "ts": action.get("ts", now_iso()),
            })

    # Extract from mirofish research results
    for item in miro.get("results", []):
        conf = float(item.get("signal_confidence", 0))
        if conf >= SIGNAL_MIN_CONF:
            signals.append({
                "source": "mirofish",
                "market": item.get("topic", "Unknown"),
                "direction": item.get("direction", "LONG"),
                "confidence": conf,
                "rationale": item.get("summary", ""),
                "ts": item.get("ts", now_iso()),
            })

    # Sort by confidence descending
    return sorted(signals, key=lambda x: x["confidence"], reverse=True)


# ── formatters ────────────────────────────────────────────────────────────────

def _direction_emoji(direction: str) -> str:
    d = direction.upper()
    if d in ("YES", "LONG", "BUY", "UP"):
        return "🟢"
    if d in ("NO", "SHORT", "SELL", "DOWN"):
        return "🔴"
    return "🟡"

def format_telegram(signals: list[dict], title: str = "") -> str:
    """Format signals as a Telegram-ready message (MarkdownV2 compatible)."""
    header = f"*{COMMUNITY_NAME}* 📊\n{'─' * 28}\n"
    if title:
        header += f"_{title}_\n\n"
    if not signals:
        return header + "_No signals above confidence threshold right now\\._"
    lines = [header]
    for i, sig in enumerate(signals[:8], 1):
        emoji = _direction_emoji(sig["direction"])
        conf_pct = int(sig["confidence"] * 100)
        bar = _conf_bar(sig["confidence"])
        market_safe = re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", sig["market"])
        rationale_safe = re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1",
                                sig.get("rationale", "")[:120])
        lines.append(
            f"{emoji} *{i}\\. {market_safe}*\n"
            f"Direction: `{sig['direction']}` | Conf: `{conf_pct}%` `{bar}`\n"
            f"_{rationale_safe}_\n"
        )
    lines.append(f"_Generated {now_iso()} by {COMMUNITY_NAME}_")
    return "\n".join(lines)

def format_discord(signals: list[dict], title: str = "") -> str:
    """Format signals as a Discord-ready message (Discord markdown)."""
    header = f"## 📊 {COMMUNITY_NAME}\n{'─' * 30}\n"
    if title:
        header += f"**{title}**\n\n"
    if not signals:
        return header + "*No signals above confidence threshold right now.*"
    lines = [header]
    for i, sig in enumerate(signals[:8], 1):
        emoji = _direction_emoji(sig["direction"])
        conf_pct = int(sig["confidence"] * 100)
        bar = _conf_bar(sig["confidence"])
        rationale = sig.get("rationale", "")[:140]
        lines.append(
            f"{emoji} **{i}. {sig['market']}**\n"
            f"> Direction: `{sig['direction']}` | Confidence: `{conf_pct}%` `{bar}`\n"
            f"> _{rationale}_\n"
        )
    lines.append(f"\n*Generated {now_iso()} by {COMMUNITY_NAME}*")
    return "\n".join(lines)


# ── command handlers ──────────────────────────────────────────────────────────

def cmd_signals() -> str:
    signals = get_signals_from_state()
    if not signals:
        return f"[{now_iso()}] No signals above {int(SIGNAL_MIN_CONF*100)}% confidence threshold."
    out = [f"[{now_iso()}] Top {len(signals)} signals:\n"]
    for i, s in enumerate(signals[:8], 1):
        emoji = _direction_emoji(s["direction"])
        out.append(
            f"  {i}. {emoji} {s['market']} | {s['direction']} "
            f"| {int(s['confidence']*100)}% | src={s['source']}"
        )
    return "\n".join(out)

def cmd_signal_post(analysis: str) -> str:
    prompt = (
        f"You are a professional crypto/trading analyst. "
        f"Generate a concise, confident signal post for a trading community from this analysis:\n\n{analysis}\n\n"
        f"Format: title, direction (LONG/SHORT/YES/NO), confidence %, rationale (2 sentences), risk note."
    )
    content = _ai(prompt, system="You write crisp, high-signal trading content for communities.")
    post = {
        "id": f"post_{int(time.time())}",
        "type": "manual",
        "analysis_input": analysis[:200],
        "content": content,
        "ts": now_iso(),
    }
    append_post(post)
    return f"[{now_iso()}] Signal post generated:\n{content}"

def cmd_signal_daily() -> str:
    poly = load_json_file(POLY_STATE)
    miro = load_json_file(MIRO_STATE)
    context = (
        f"Polymarket state summary: {json.dumps(poly)[:800]}\n"
        f"Mirofish research summary: {json.dumps(miro)[:800]}"
    )
    prompt = (
        "Generate a daily trading market summary for a signal community. Include:\n"
        "1. Overall market sentiment (2 sentences)\n"
        "2. Top 3 trading signals with direction and confidence\n"
        "3. Key risk factors today\n"
        "4. Recommended positioning\n\n"
        f"Context:\n{context}"
    )
    content = _ai(prompt, system="You are a professional trading analyst writing a daily briefing.")
    post = {"id": f"daily_{int(time.time())}", "type": "daily", "content": content, "ts": now_iso()}
    append_post(post)
    return f"[{now_iso()}] Daily summary:\n{content}"

def cmd_signal_performance() -> str:
    perf = load_json_file(PERF_STATE)
    if not perf:
        return f"[{now_iso()}] No strategy performance data found at {PERF_STATE}"
    wins   = perf.get("wins", 0)
    losses = perf.get("losses", 0)
    total  = wins + losses
    winrate = (wins / total * 100) if total else 0
    pnl     = perf.get("total_pnl", 0)
    lines = [
        f"[{now_iso()}] Signal Performance Report",
        f"  Signals tracked : {total}",
        f"  Wins / Losses   : {wins} / {losses}",
        f"  Win rate        : {winrate:.1f}%",
        f"  Total PnL       : {pnl:+.4f}",
    ]
    recent = perf.get("recent_signals", [])
    if recent:
        lines.append("  Recent signals  :")
        for s in recent[-5:]:
            result_emoji = "✅" if s.get("result") == "win" else "❌"
            lines.append(f"    {result_emoji} {s.get('market','?')} | {s.get('direction','?')} | {s.get('pnl',0):+.4f}")
    return "\n".join(lines)

def cmd_signal_telegram() -> str:
    signals = get_signals_from_state()
    msg = format_telegram(signals, title="Live Signals Update")
    if not TELEGRAM_BOT_TOKEN:
        note = ("NOTE: TELEGRAM_BOT_TOKEN is not set. "
                "Set it to enable automatic Telegram posting via Bot API.")
    else:
        note = "NOTE: Telegram posting stub active — implement HTTP send to enable live dispatch."
    return f"[{now_iso()}] Telegram-formatted message:\n\n{msg}\n\n{note}"

def cmd_signal_discord() -> str:
    signals = get_signals_from_state()
    msg = format_discord(signals, title="Live Signals Update")
    if not DISCORD_WEBHOOK_URL:
        note = ("NOTE: DISCORD_WEBHOOK_URL is not set. "
                "Set it to enable automatic Discord webhook posting.")
    else:
        note = "NOTE: Discord posting stub active — implement HTTP POST to webhook URL to enable live dispatch."
    return f"[{now_iso()}] Discord-formatted message:\n\n{msg}\n\n{note}"

def cmd_signal_alert(market: str, direction: str, confidence: str) -> str:
    try:
        conf = float(confidence)
    except ValueError:
        conf = 0.75
    conf = max(0.0, min(1.0, conf))
    emoji = _direction_emoji(direction)
    conf_pct = int(conf * 100)
    bar = _conf_bar(conf)
    prompt = (
        f"Write a short, urgent trading alert message (3-4 sentences) for:\n"
        f"Market: {market}\nDirection: {direction}\nConfidence: {conf_pct}%\n"
        "Include: why now, key level to watch, risk management note."
    )
    ai_rationale = _ai(prompt, system="You write concise, actionable trading alerts.")
    tg_msg = (
        f"🚨 *SIGNAL ALERT* 🚨\n\n"
        f"{emoji} *{market}*\n"
        f"Direction: `{direction.upper()}`\n"
        f"Confidence: `{conf_pct}%` `{bar}`\n\n"
        f"_{ai_rationale[:300]}_\n\n"
        f"_— {COMMUNITY_NAME} | {now_iso()}_"
    )
    post = {
        "id": f"alert_{int(time.time())}",
        "type": "alert",
        "market": market,
        "direction": direction,
        "confidence": conf,
        "content": tg_msg,
        "ts": now_iso(),
    }
    append_post(post)
    return f"[{now_iso()}] Alert generated:\n{tg_msg}"

def cmd_community_update() -> str:
    poly = load_json_file(POLY_STATE)
    miro = load_json_file(MIRO_STATE)
    perf = load_json_file(PERF_STATE)
    context = (
        f"Polymarket: {json.dumps(poly)[:600]}\n"
        f"Research: {json.dumps(miro)[:600]}\n"
        f"Performance: wins={perf.get('wins',0)} losses={perf.get('losses',0)}"
    )
    prompt = (
        "Generate a community newsletter update for a trading signal community. Include sections:\n"
        "1. 📈 Market Overview (2-3 sentences)\n"
        "2. 🎯 Top Signals This Week\n"
        "3. 📊 Performance Update\n"
        "4. 🔮 What to Watch Next\n"
        "5. 📢 Community Note\n\n"
        f"Context:\n{context}"
    )
    content = _ai(prompt, system="You write engaging, professional trading community newsletters.")
    post = {"id": f"update_{int(time.time())}", "type": "community_update", "content": content, "ts": now_iso()}
    append_post(post)
    return f"[{now_iso()}] Community update:\n{content}"

def cmd_signal_status() -> str:
    posts = load_posts()
    by_type: dict[str, int] = {}
    for p in posts:
        by_type[p.get("type", "unknown")] = by_type.get(p.get("type", "unknown"), 0) + 1
    state = load_json_file(STATE_FILE)
    lines = [
        f"[{now_iso()}] Signal Community Bot Status",
        f"  Community name  : {COMMUNITY_NAME}",
        f"  Min confidence  : {int(SIGNAL_MIN_CONF*100)}%",
        f"  Poll interval   : {POLL_INTERVAL}s",
        f"  Total posts     : {len(posts)}",
        f"  By type         : {json.dumps(by_type)}",
        f"  Telegram token  : {'set' if TELEGRAM_BOT_TOKEN else 'NOT SET'}",
        f"  Discord webhook : {'set' if DISCORD_WEBHOOK_URL else 'NOT SET'}",
        f"  Bot status      : {state.get('status', 'unknown')}",
        f"  Last heartbeat  : {state.get('ts', 'n/a')}",
    ]
    return "\n".join(lines)


# ── chatlog processor ─────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        response: str | None = None

        if msg_lower == "signals":
            response = cmd_signals()
        elif msg_lower.startswith("signal post "):
            analysis = msg[len("signal post "):].strip()
            response = cmd_signal_post(analysis) if analysis else "Usage: signal post <analysis>"
        elif msg_lower == "signal daily":
            response = cmd_signal_daily()
        elif msg_lower == "signal performance":
            response = cmd_signal_performance()
        elif msg_lower == "signal telegram":
            response = cmd_signal_telegram()
        elif msg_lower == "signal discord":
            response = cmd_signal_discord()
        elif msg_lower.startswith("signal alert "):
            parts = msg.split()[2:]  # market direction confidence
            if len(parts) >= 3:
                response = cmd_signal_alert(parts[0], parts[1], parts[2])
            else:
                response = "Usage: signal alert <market> <direction> <confidence>"
        elif msg_lower == "community update":
            response = cmd_community_update()
        elif msg_lower == "signal status":
            response = cmd_signal_status()

        if response:
            print(response)
            append_chatlog({"type": "bot", "bot": "signal-community", "message": response, "ts": now_iso()})

    return new_idx


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{now_iso()}] signal-community started; poll={POLL_INTERVAL}s")
    last_idx = len(load_chatlog())
    write_state({"bot": "signal-community", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] signal-community error: {exc}")
        write_state({"bot": "signal-community", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
