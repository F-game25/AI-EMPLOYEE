"""Arbitrage Bot — price arbitrage detection and alert service.

Monitors price differences across Amazon, eBay, Walmart, StockX, and other
platforms using web search.  Scores opportunities by margin potential, generates
buyer/seller action alerts, maintains a watchlist for repeated scanning, and
persists a full opportunity history so trends can be reviewed over time.

Commands:
  arb scan <product>                       — search price differences across platforms, return top 3 opportunities
  arb trends                               — find currently hot arbitrage categories via web search
  arb alert <product> <buy_price> <sell>   — manually add alert, calculate margin/ROI/profit
  arb opportunities                        — show all tracked opportunities sorted by ROI
  arb subscribe <product>                  — add product to watchlist for regular scanning
  arb watchlist                            — show watchlist products
  arb status                               — total opportunities found, best ROI, alert count
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "arbitrage-bot.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
POLL_INTERVAL = int(os.environ.get("ARB_BOT_POLL_INTERVAL", "5"))
MIN_ROI = int(os.environ.get("ARB_MIN_ROI", "20"))
SCAN_INTERVAL = int(os.environ.get("ARB_SCAN_INTERVAL", "3600"))

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

OPP_FILE = AI_HOME / "state" / "arb-opportunities.json"
WATCHLIST_FILE = AI_HOME / "config" / "arb-watchlist.json"


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


def _ai(prompt, system=""):
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("arbitrage-bot", prompt, system_prompt=system) or {}).get("answer", "")


def _search(query):
    if not _AI_AVAILABLE:
        return "[search unavailable]"
    try:
        return (_search_web(query) or {}).get("results", "[no results]")
    except Exception:
        return "[search error]"


# ── opportunity store ─────────────────────────────────────────────────────────

def _load_opportunities() -> list:
    if not OPP_FILE.exists():
        return []
    try:
        return json.loads(OPP_FILE.read_text())
    except Exception:
        return []


def _save_opportunities(opps: list):
    OPP_FILE.parent.mkdir(parents=True, exist_ok=True)
    OPP_FILE.write_text(json.dumps(opps, indent=2))


def _add_opportunity(opp: dict) -> str:
    opps = _load_opportunities()
    opp_id = f"arb-{len(opps) + 1:05d}"
    opp["id"] = opp_id
    opp.setdefault("created_at", now_iso())
    opp.setdefault("status", "active")
    opps.append(opp)
    _save_opportunities(opps)
    return opp_id


# ── watchlist ─────────────────────────────────────────────────────────────────

def _load_watchlist() -> list:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        return json.loads(WATCHLIST_FILE.read_text())
    except Exception:
        return []


def _save_watchlist(wl: list):
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_FILE.write_text(json.dumps(wl, indent=2))


def _add_to_watchlist(product: str) -> bool:
    wl = _load_watchlist()
    if product.lower() in [w.get("product", "").lower() for w in wl]:
        return False
    wl.append({"product": product, "added_at": now_iso(), "last_scanned": None})
    _save_watchlist(wl)
    return True


# ── margin / ROI calculations ─────────────────────────────────────────────────

def _calculate_roi(buy_price: float, sell_price: float, fees_pct: float = 13.0) -> dict:
    """Return margin, ROI percent, and net profit after estimated fees."""
    fees = sell_price * (fees_pct / 100)
    net_sell = sell_price - fees
    profit = net_sell - buy_price
    margin = (profit / sell_price * 100) if sell_price > 0 else 0
    roi = (profit / buy_price * 100) if buy_price > 0 else 0
    return {
        "buy_price": round(buy_price, 2),
        "sell_price": round(sell_price, 2),
        "estimated_fees": round(fees, 2),
        "net_profit": round(profit, 2),
        "margin": round(margin, 1),
        "roi_percent": round(roi, 1),
    }


# ── generation helpers ────────────────────────────────────────────────────────

def _gen_scan(product: str) -> list:
    search_q = f"{product} price site:amazon.com OR site:ebay.com OR site:walmart.com OR site:stockx.com 2025"
    results = _search(search_q)
    system = (
        "You are an expert retail arbitrage analyst. "
        "Identify price differences across platforms and score opportunities by ROI potential."
    )
    prompt = (
        f"Analyse arbitrage opportunities for: '{product}'\n"
        f"Search results:\n{results}\n\n"
        "Find the top 3 buy-low/sell-high opportunities. For each return JSON:\n"
        "[\n"
        "  {\n"
        "    \"product\": \"...\",\n"
        "    \"buy_platform\": \"...\",\n"
        "    \"buy_price\": 0.0,\n"
        "    \"sell_platform\": \"...\",\n"
        "    \"sell_price\": 0.0,\n"
        "    \"margin\": 0.0,\n"
        "    \"roi_percent\": 0.0,\n"
        "    \"notes\": \"...\"\n"
        "  }\n"
        "]\n"
        "Use realistic prices from the search results where available. "
        "Return ONLY a valid JSON array."
    )
    raw = _ai(prompt, system)
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        items = json.loads(m.group()) if m else []
    except Exception:
        items = []
    return items


def _gen_trends() -> str:
    results = _search("best arbitrage products 2025 sneakers electronics collectibles high ROI flip")
    system = "You are a professional retail arbitrage coach who finds winning product categories."
    prompt = (
        "Based on these search results, identify the top trending arbitrage categories right now:\n"
        f"{results}\n\n"
        "Return a ranked list of 8 categories with:\n"
        "- Category name\n"
        "- Why it's hot for arbitrage\n"
        "- Best platforms to buy vs sell\n"
        "- Typical ROI range\n"
        "- Risk level (low/medium/high)\n"
        "- Example product to flip right now"
    )
    return _ai(prompt, system)


def _bot_reply(message: str):
    append_chatlog({"type": "bot", "bot": "arbitrage-bot", "message": message, "ts": now_iso()})
    print(f"[{now_iso()}] arbitrage-bot reply: {message[:120]}")


# ── command processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        if not msg_lower.startswith("arb"):
            continue

        # arb status
        if msg_lower in ("arb status", "arb stats"):
            opps = _load_opportunities()
            active = [o for o in opps if o.get("status") == "active"]
            rois = [o.get("roi_percent", 0) for o in opps if isinstance(o.get("roi_percent"), (int, float))]
            best_roi = max(rois) if rois else 0
            wl = _load_watchlist()
            tip = (
                "Subscription at $50/mo for alerts. "
                "1K subs = $50K/mo. "
                "Focus: sneakers (StockX vs local), electronics, limited edition items."
            )
            reply = (
                f"📊 Arbitrage Bot Status\n"
                f"  Total opportunities : {len(opps)}\n"
                f"  Active              : {len(active)}\n"
                f"  Best ROI tracked    : {best_roi:.1f}%\n"
                f"  Watchlist size      : {len(wl)}\n"
                f"  Min ROI threshold   : {MIN_ROI}%\n"
                f"  Scan interval       : {SCAN_INTERVAL}s\n"
                f"  💰 Revenue tip: {tip}"
            )
            _bot_reply(reply)
            continue

        # arb watchlist
        if msg_lower in ("arb watchlist", "arb watch list"):
            wl = _load_watchlist()
            if not wl:
                _bot_reply("📋 Watchlist is empty. Use: arb subscribe <product>")
                continue
            lines = ["📋 Arbitrage Watchlist:"]
            for i, item in enumerate(wl, 1):
                last = item.get("last_scanned") or "never"
                lines.append(f"  {i}. {item['product']} (added: {item['added_at'][:10]}, last scan: {last})")
            _bot_reply("\n".join(lines))
            continue

        # arb opportunities
        if msg_lower in ("arb opportunities", "arb opps", "arb list"):
            opps = _load_opportunities()
            if not opps:
                _bot_reply("📭 No opportunities tracked yet. Use: arb scan <product>")
                continue
            sorted_opps = sorted(opps, key=lambda o: o.get("roi_percent", 0), reverse=True)
            lines = [f"💹 Tracked Opportunities (sorted by ROI) — {len(opps)} total:"]
            for o in sorted_opps[:15]:
                flag = "✅" if o.get("roi_percent", 0) >= MIN_ROI else "⚠️"
                lines.append(
                    f"  {flag} [{o.get('id')}] {o.get('product', 'unknown')}"
                    f" | Buy ${o.get('buy_price', '?')} ({o.get('buy_platform', '?')})"
                    f" → Sell ${o.get('sell_price', '?')} ({o.get('sell_platform', '?')})"
                    f" | ROI: {o.get('roi_percent', 0):.1f}%"
                    f" | Margin: {o.get('margin', 0):.1f}%"
                    f" | {o.get('status', 'active')}"
                )
            if len(opps) > 15:
                lines.append(f"  … and {len(opps) - 15} more")
            _bot_reply("\n".join(lines))
            continue

        # arb subscribe <product>
        if msg_lower.startswith("arb subscribe "):
            product = msg[len("arb subscribe "):].strip()
            if not product:
                _bot_reply("Usage: arb subscribe <product>")
                continue
            added = _add_to_watchlist(product)
            if added:
                wl = _load_watchlist()
                _bot_reply(f"✅ '{product}' added to watchlist ({len(wl)} items). Will be scanned every {SCAN_INTERVAL}s.")
            else:
                _bot_reply(f"ℹ️ '{product}' is already on the watchlist.")
            continue

        # arb trends
        if msg_lower in ("arb trends", "arb trend"):
            _bot_reply("🔍 Searching for hot arbitrage categories…")
            trends = _gen_trends()
            _bot_reply(f"🔥 Trending Arbitrage Categories:\n\n{trends}")
            continue

        # arb alert <product> <buy_price> <sell_price>
        if msg_lower.startswith("arb alert "):
            rest = msg[len("arb alert "):].strip()
            # parse: last two tokens are prices, everything before is product name
            tokens = rest.split()
            if len(tokens) < 3:
                _bot_reply("Usage: arb alert <product name> <buy_price> <sell_price>\nExample: arb alert Nike Air Jordan 1 85 145")
                continue
            try:
                sell_price = float(tokens[-1])
                buy_price = float(tokens[-2])
                product = " ".join(tokens[:-2])
            except ValueError:
                _bot_reply("❌ Prices must be numbers. Usage: arb alert <product> <buy_price> <sell_price>")
                continue
            calc = _calculate_roi(buy_price, sell_price)
            opp_id = _add_opportunity({
                "product": product,
                "buy_platform": "manual",
                "buy_price": calc["buy_price"],
                "sell_platform": "manual",
                "sell_price": calc["sell_price"],
                "margin": calc["margin"],
                "roi_percent": calc["roi_percent"],
                "source": "manual",
            })
            roi_flag = "✅" if calc["roi_percent"] >= MIN_ROI else "⚠️ Below threshold"
            reply = (
                f"📌 Alert Saved [{opp_id}] — {product}\n"
                f"  Buy price       : ${calc['buy_price']}\n"
                f"  Sell price      : ${calc['sell_price']}\n"
                f"  Est. fees (~13%): ${calc['estimated_fees']}\n"
                f"  Net profit      : ${calc['net_profit']}\n"
                f"  Margin          : {calc['margin']}%\n"
                f"  ROI             : {calc['roi_percent']}%  {roi_flag}"
            )
            _bot_reply(reply)
            continue

        # arb scan <product>
        if msg_lower.startswith("arb scan "):
            product = msg[len("arb scan "):].strip()
            if not product:
                _bot_reply("Usage: arb scan <product>")
                continue
            _bot_reply(f"🔍 Scanning prices for '{product}' across platforms…")
            try:
                items = _gen_scan(product)
                if not items:
                    _bot_reply(f"⚠️ No clear arbitrage opportunities found for '{product}'. Try a more specific product name.")
                    continue
                lines = [f"💹 Arbitrage Scan — {product} ({len(items)} opportunities):"]
                saved_ids = []
                for item in items[:3]:
                    # recalculate ROI locally for consistency
                    buy = float(item.get("buy_price") or 0)
                    sell = float(item.get("sell_price") or 0)
                    if buy > 0 and sell > buy:
                        calc = _calculate_roi(buy, sell)
                        item["margin"] = calc["margin"]
                        item["roi_percent"] = calc["roi_percent"]
                    item["source"] = "web_search"
                    opp_id = _add_opportunity(item)
                    saved_ids.append(opp_id)
                    roi_flag = "✅" if item.get("roi_percent", 0) >= MIN_ROI else "⚠️"
                    lines.append(
                        f"\n  {roi_flag} [{opp_id}] Buy on {item.get('buy_platform', '?')}"
                        f" @ ${item.get('buy_price', '?')}"
                        f" → Sell on {item.get('sell_platform', '?')}"
                        f" @ ${item.get('sell_price', '?')}"
                        f"\n    ROI: {item.get('roi_percent', 0):.1f}%"
                        f"  |  Margin: {item.get('margin', 0):.1f}%"
                        f"\n    Notes: {item.get('notes', '')}"
                    )
                lines.append(f"\n  💾 Saved opportunity IDs: {', '.join(saved_ids)}")
                _bot_reply("\n".join(lines))
            except Exception as exc:
                _bot_reply(f"❌ Scan error: {exc}")
            continue

    return new_idx


def main():
    print(f"[{now_iso()}] arbitrage-bot started")
    last_idx = len(load_chatlog())
    write_state({"bot": "arbitrage-bot", "ts": now_iso(), "status": "starting"})

    last_watchlist_scan = 0.0

    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx

            # periodic watchlist scanning
            now_ts = time.time()
            if now_ts - last_watchlist_scan >= SCAN_INTERVAL:
                wl = _load_watchlist()
                for item in wl:
                    product = item.get("product", "")
                    if not product:
                        continue
                    try:
                        items = _gen_scan(product)
                        for opp in items:
                            buy = float(opp.get("buy_price") or 0)
                            sell = float(opp.get("sell_price") or 0)
                            if buy > 0 and sell > buy:
                                calc = _calculate_roi(buy, sell)
                                opp["margin"] = calc["margin"]
                                opp["roi_percent"] = calc["roi_percent"]
                                if calc["roi_percent"] >= MIN_ROI:
                                    opp["source"] = "watchlist_auto"
                                    _add_opportunity(opp)
                                    append_chatlog({
                                        "type": "bot",
                                        "bot": "arbitrage-bot",
                                        "message": (
                                            f"🔔 Watchlist Alert — {product}: "
                                            f"Buy ${buy} ({opp.get('buy_platform')}) → "
                                            f"Sell ${sell} ({opp.get('sell_platform')}) "
                                            f"| ROI: {calc['roi_percent']}%"
                                        ),
                                        "ts": now_iso(),
                                    })
                        item["last_scanned"] = now_iso()
                    except Exception as exc:
                        print(f"[{now_iso()}] arbitrage-bot watchlist scan error ({product}): {exc}")
                _save_watchlist(wl)
                last_watchlist_scan = now_ts

        except Exception as exc:
            print(f"[{now_iso()}] arbitrage-bot error: {exc}")

        write_state({"bot": "arbitrage-bot", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
