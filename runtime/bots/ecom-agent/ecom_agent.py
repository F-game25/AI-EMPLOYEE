"""E-Commerce Agent Bot — product research, AI listing copy, email flows, ad copy & customer service.

Researches trending products via web search, generates complete Shopify/Etsy listing copy,
email marketing sequences, Facebook/Google ad copy, and customer service reply templates.

Commands (via chatlog):
  ecom research <niche>            — find top 5 trending product opportunities with scores
  ecom listing <product>           — full listing: title, description, bullets, tags, price
  ecom email <type> <product>      — email flow: welcome|abandoned_cart|post_purchase|win_back|promotion
  ecom service <issue>             — customer service reply template
  ecom trends                      — current trending products/niches via web search
  ecom ads <product>               — Facebook/Google ad copy (headline + body + CTA)
  ecom status                      — total listings, emails, research sessions generated

Config env vars:
  ECOM_AGENT_POLL_INTERVAL  — chatlog poll seconds (default: 5)
  ECOM_NICHE                — default product niche
  ECOM_PLATFORM             — target platform: shopify|etsy (default: shopify)
  ECOM_TARGET_MARGIN        — target margin % (default: 40)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE   = AI_HOME / "state" / "ecom-agent.state.json"
CHATLOG      = AI_HOME / "state" / "chatlog.jsonl"
LISTINGS_FILE = AI_HOME / "state" / "ecom-agent-listings.json"

POLL_INTERVAL   = int(os.environ.get("ECOM_AGENT_POLL_INTERVAL", "5"))
DEFAULT_NICHE   = os.environ.get("ECOM_NICHE", "")
PLATFORM        = os.environ.get("ECOM_PLATFORM", "shopify")
TARGET_MARGIN   = int(os.environ.get("ECOM_TARGET_MARGIN", "40"))

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def append_chatlog(e: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")


def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("ecom-agent", prompt, system_prompt=system) or {}).get("answer", "")


def _web(query: str) -> str:
    if not _AI_AVAILABLE:
        return "[search unavailable]"
    try:
        results = _search_web(query) or []
        return "\n".join(
            f"{r.get('title','')}: {r.get('url','')}\n{r.get('snippet','')}"
            for r in results[:6]
        )
    except Exception:
        return "[search error]"


# ── Listings store ────────────────────────────────────────────────────────────

def load_listings() -> dict:
    if not LISTINGS_FILE.exists():
        return {"listings": [], "emails": [], "research": [], "ads": []}
    try:
        return json.loads(LISTINGS_FILE.read_text())
    except Exception:
        return {"listings": [], "emails": [], "research": [], "ads": []}


def save_listings(data: dict) -> None:
    LISTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LISTINGS_FILE.write_text(json.dumps(data, indent=2))


def _append_record(category: str, record: dict) -> None:
    data = load_listings()
    data.setdefault(category, []).append(record)
    save_listings(data)


# ── Core logic ────────────────────────────────────────────────────────────────

def research_niche(niche: str) -> str:
    """Find top 5 trending product opportunities in a niche."""
    raw = _web(f"trending {niche} products 2024 dropshipping winning products")
    result = _ai(
        f"Analyse this web data for the niche '{niche}' and identify the top 5 product "
        f"opportunities. For each provide: product name, trend score (1-10), estimated price "
        f"range, target audience, competition level (low/med/high), and one key selling point.\n\n"
        f"Data:\n{raw}",
        system="You are an expert e-commerce product researcher specialising in dropshipping "
               "and private label. Be specific, data-driven, and practical. Format as a "
               "numbered list.",
    )
    record = {"niche": niche, "result": result, "ts": now_iso(), "platform": PLATFORM}
    _append_record("research", record)
    return f"Product Research — {niche}:\n\n{result}"


def generate_listing(product: str) -> str:
    """Generate a complete product listing for the target platform."""
    result = _ai(
        f"Generate a complete {PLATFORM} product listing for: {product}\n"
        f"Target margin: {TARGET_MARGIN}%\n\n"
        "Include:\n"
        "1. SEO Title (under 80 chars)\n"
        "2. Description (200 words, benefit-focused, SEO-optimised)\n"
        "3. Bullet Points (5 key features/benefits)\n"
        "4. Tags/Keywords (15 relevant tags)\n"
        "5. Suggested Price (USD) with rationale\n"
        "6. Dropshipping Notes (supplier tip, shipping estimate)",
        system=f"You are an expert {PLATFORM} seller and SEO copywriter with 10 years "
               "experience. Write compelling, conversion-optimised product copy. "
               "Use emotional triggers and clear value propositions.",
    )
    record = {"product": product, "listing": result, "ts": now_iso(), "platform": PLATFORM}
    _append_record("listings", record)
    return f"Product Listing — {product} ({PLATFORM}):\n\n{result}"


_EMAIL_TYPES = {
    "welcome": "a welcome series email (first email after signup). Build trust, introduce brand, set expectations.",
    "abandoned_cart": "an abandoned cart recovery email. Remind them of items, create urgency, offer small incentive.",
    "post_purchase": "a post-purchase follow-up email. Thank them, set delivery expectations, ask for review.",
    "win_back": "a win-back/re-engagement email for lapsed customers. Remind them of value, offer comeback deal.",
    "promotion": "a promotional/sale announcement email. Create excitement, highlight deal, drive urgency.",
}


def generate_email(email_type: str, product: str) -> str:
    """Generate an email marketing message for the given type and product."""
    email_type = email_type.lower()
    description = _EMAIL_TYPES.get(email_type, f"a {email_type} marketing email")

    result = _ai(
        f"Write {description}\n"
        f"Product/Store context: {product}\n\n"
        "Include: Subject line, Preview text, Email body (with personalisation tokens like "
        "{{first_name}}), and CTA button text.",
        system="You are an expert e-commerce email marketer with a track record of 30%+ "
               "open rates. Write engaging, on-brand emails that convert. "
               "Use proven copywriting frameworks (AIDA, PAS).",
    )
    record = {"type": email_type, "product": product, "email": result, "ts": now_iso()}
    _append_record("emails", record)
    return f"Email Marketing ({email_type}) — {product}:\n\n{result}"


def generate_service_reply(issue: str) -> str:
    """Generate a customer service reply template."""
    result = _ai(
        f"Write a professional, empathetic customer service reply template for this issue:\n{issue}\n\n"
        "Include: Subject line, greeting, acknowledgement, solution/next steps, closing, "
        "and signature placeholder. Add [VARIABLE] placeholders where personalisation is needed.",
        system="You are a top-tier customer service specialist for e-commerce. Write replies "
               "that resolve issues quickly, retain customers, and protect brand reputation. "
               "Be empathetic but efficient.",
    )
    return f"Customer Service Template — {issue}:\n\n{result}"


def find_trends() -> str:
    """Find current trending products and niches."""
    raw = _web("trending products ecommerce 2024 winning niches dropshipping")
    result = _ai(
        "Summarise the top trending e-commerce niches and products right now based on this data.\n"
        "List 8 niches with: niche name, trend direction (↑↑/↑/→), best platform, "
        "key products, and one action tip.\n\nData:\n{raw}".format(raw=raw),
        system="You are an e-commerce trend analyst. Be specific, actionable, and data-driven.",
    )
    return f"E-Commerce Trends:\n\n{result}"


def generate_ads(product: str) -> str:
    """Generate Facebook and Google ad copy for a product."""
    result = _ai(
        f"Generate Facebook and Google ad copy for this product: {product}\n\n"
        "Provide:\n"
        "FACEBOOK AD:\n- Primary Text (125 chars)\n- Headline (40 chars)\n"
        "- Description (30 chars)\n- CTA button\n\n"
        "GOOGLE AD:\n- Headline 1 (30 chars)\n- Headline 2 (30 chars)\n"
        "- Headline 3 (30 chars)\n- Description 1 (90 chars)\n- Description 2 (90 chars)\n\n"
        "Also suggest 5 interest/keyword targets.",
        system="You are a performance marketing expert specialising in e-commerce paid ads. "
               "Write high-CTR, conversion-focused ad copy. Use power words, urgency, "
               "and social proof cues.",
    )
    record = {"product": product, "ads": result, "ts": now_iso()}
    _append_record("ads", record)
    return f"Ad Copy — {product}:\n\n{result}"


def show_status() -> str:
    data = load_listings()
    return (
        f"Ecom Agent Status:\n"
        f"  Listings generated: {len(data.get('listings', []))}\n"
        f"  Email flows created: {len(data.get('emails', []))}\n"
        f"  Research sessions: {len(data.get('research', []))}\n"
        f"  Ad copies generated: {len(data.get('ads', []))}\n"
        f"  Platform: {PLATFORM} | Target margin: {TARGET_MARGIN}%"
    )


# ── Chatlog processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        if msg_lower.startswith("ecom research "):
            niche = msg[len("ecom research "):].strip() or DEFAULT_NICHE or "general"
            result = research_niche(niche)
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom listing "):
            product = msg[len("ecom listing "):].strip()
            result = generate_listing(product) if product else "Usage: ecom listing <product>"
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom email "):
            rest = msg[len("ecom email "):].strip()
            parts = rest.split(maxsplit=1)
            email_type = parts[0] if parts else "promotion"
            product = parts[1] if len(parts) > 1 else "my store"
            result = generate_email(email_type, product)
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom service "):
            issue = msg[len("ecom service "):].strip()
            result = generate_service_reply(issue) if issue else "Usage: ecom service <issue>"
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom trends"):
            result = find_trends()
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom ads "):
            product = msg[len("ecom ads "):].strip()
            result = generate_ads(product) if product else "Usage: ecom ads <product>"
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("ecom status"):
            result = show_status()
            append_chatlog({"type": "bot", "bot": "ecom-agent", "message": result, "ts": now_iso()})

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] ecom-agent started (platform={PLATFORM}, margin={TARGET_MARGIN}%)")
    last_idx = len(load_chatlog())
    data = load_listings()
    write_state({
        "bot": "ecom-agent",
        "ts": now_iso(),
        "status": "starting",
        "platform": PLATFORM,
        "listings": len(data.get("listings", [])),
    })

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            data = load_listings()
            write_state({
                "bot": "ecom-agent",
                "ts": now_iso(),
                "status": "running",
                "platform": PLATFORM,
                "listings": len(data.get("listings", [])),
                "emails": len(data.get("emails", [])),
                "research": len(data.get("research", [])),
                "ads": len(data.get("ads", [])),
            })
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
