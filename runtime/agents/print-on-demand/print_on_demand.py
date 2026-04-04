"""Print-on-Demand Bot — merch automation for Printful, Teespring, and Redbubble.

Researches trending niches using web search, generates detailed AI image prompts
for Stable Diffusion / DALL-E / Midjourney, writes SEO-optimised product listings,
creates Facebook and Google ad copy, and maintains a registry of all designs so
nothing falls through the cracks.

Commands:
  pod research <niche>      — web-search trending POD opportunities, return top 5 with demand score
  pod design <niche>        — 5 detailed Midjourney image prompts for the niche
  pod listing <design_idea> — full Printful/Etsy listing: title, description, tags, price
  pod ads <product>         — 3 Facebook ad variations + Google Shopping title
  pod mockup <design_idea>  — mockup description + lifestyle photography Midjourney prompt
  pod trends                — web-search current hot POD niches
  pod status                — total designs, listings, niches covered
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "print-on-demand.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
POLL_INTERVAL = int(os.environ.get("POD_POLL_INTERVAL", "5"))
DEFAULT_PLATFORM = os.environ.get("POD_DEFAULT_PLATFORM", "printful")
TARGET_MARGIN = int(os.environ.get("POD_TARGET_MARGIN", "40"))
DEFAULT_NICHE = os.environ.get("POD_NICHE", "")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

DESIGN_REGISTRY = AI_HOME / "state" / "pod-designs.json"


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
    return (_query_ai_for_agent("print-on-demand", prompt, system_prompt=system) or {}).get("answer", "")


def _search(query):
    if not _AI_AVAILABLE:
        return "[search unavailable]"
    try:
        return (_search_web(query) or {}).get("results", "[no results]")
    except Exception:
        return "[search error]"


def _load_registry() -> list:
    if not DESIGN_REGISTRY.exists():
        return []
    try:
        return json.loads(DESIGN_REGISTRY.read_text())
    except Exception:
        return []


def _save_registry(registry: list):
    DESIGN_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    DESIGN_REGISTRY.write_text(json.dumps(registry, indent=2))


def _register_design(entry: dict):
    registry = _load_registry()
    entry["id"] = f"pod-{len(registry) + 1:04d}"
    entry["created_at"] = now_iso()
    registry.append(entry)
    _save_registry(registry)
    return entry["id"]


# ── generation helpers ────────────────────────────────────────────────────────

def _gen_research(niche: str) -> str:
    search_results = _search(f"trending print-on-demand {niche} designs 2025 bestsellers")
    system = "You are a print-on-demand market research expert with deep knowledge of Etsy, Redbubble, and Merch by Amazon."
    prompt = (
        f"Research trending POD opportunities in the '{niche}' niche.\n"
        f"Web search results:\n{search_results}\n\n"
        "Return the top 5 opportunities as a numbered list. For each include:\n"
        "- Niche/design concept\n"
        "- Demand score (1-10)\n"
        "- Best products (t-shirt / mug / poster / hoodie)\n"
        "- Key buyer persona\n"
        "- Example bestselling phrase or design angle\n"
        "- Competition level (low/medium/high)"
    )
    return _ai(prompt, system)


def _gen_design_prompts(niche: str) -> str:
    system = "You are an expert at writing Midjourney prompts for print-on-demand t-shirt and merch designs."
    prompt = (
        f"Generate 5 detailed AI image prompts for print-on-demand designs in the '{niche}' niche.\n"
        "Each prompt should be Midjourney-style: detailed, specific style, colors, mood.\n"
        "Format each as:\n"
        "PROMPT N:\n"
        "[detailed prompt], t-shirt graphic design, flat vector, transparent background, "
        "bold colors, no text, --ar 1:1 --v 6\n\n"
        "Cover a mix of: minimalist, retro, funny, inspirational, and detailed illustration styles."
    )
    return _ai(prompt, system)


def _gen_listing(design_idea: str) -> dict:
    system = "You are an expert Etsy/Printful SEO copywriter who maximises organic traffic and conversion."
    prompt = (
        f"Generate a complete product listing for: '{design_idea}'\n"
        "Return JSON with keys:\n"
        "  title: SEO product title (max 140 chars, keyword-rich, no ALL CAPS)\n"
        "  description: 200-word engaging product description with bullet features\n"
        "  tags: array of 13 Etsy tags (max 20 chars each, mix short and long-tail)\n"
        "  base_cost: estimated base production cost in USD\n"
        "  sell_price: recommended sell price for 40% margin\n"
        "  margin_note: brief pricing rationale\n"
        "Return ONLY valid JSON."
    )
    raw = _ai(prompt, system)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception:
        data = {}
    return {
        "title": data.get("title", design_idea),
        "description": data.get("description", ""),
        "tags": data.get("tags", []),
        "base_cost": data.get("base_cost", ""),
        "sell_price": data.get("sell_price", ""),
        "margin_note": data.get("margin_note", f"Target {TARGET_MARGIN}% margin"),
    }


def _gen_ads(product: str) -> str:
    system = "You are a direct-response Facebook ad copywriter specialising in e-commerce merch."
    prompt = (
        f"Write ad copy for this print-on-demand product: '{product}'.\n\n"
        "Produce 3 Facebook ad variations:\n"
        "1. PROBLEM-AWARE: Opens with a relatable pain point or identity statement\n"
        "2. NICHE-SPECIFIC: Uses insider language and humour for the target community\n"
        "3. VIRAL/GIFTING: Positions as the perfect gift, shareable angle\n\n"
        "For each variation include: Primary text (125 chars), Headline (40 chars), Description (30 chars).\n\n"
        "Also provide:\n"
        "GOOGLE SHOPPING TITLE: (max 150 chars, brand + key attributes + niche keyword)"
    )
    return _ai(prompt, system)


def _gen_mockup(design_idea: str) -> str:
    system = "You are a product photographer and Midjourney prompt expert."
    prompt = (
        f"Generate a mockup brief and Midjourney lifestyle photography prompt for: '{design_idea}'\n\n"
        "Include:\n"
        "MOCKUP DESCRIPTION:\n"
        "- Product type, placement, folding style, background colour\n"
        "- Recommended Printful/Placeit mockup template type\n\n"
        "MIDJOURNEY LIFESTYLE PROMPT:\n"
        "- Person wearing/using the product in a relatable scene (no face close-ups)\n"
        "- Lighting, setting, mood, camera style\n"
        "- End with: --ar 4:5 --v 6 --style raw"
    )
    return _ai(prompt, system)


def _gen_trends() -> str:
    search_results = _search("best print-on-demand niches 2025 high demand low competition trending")
    system = "You are a POD market analyst tracking what sells on Etsy, Redbubble, Merch by Amazon."
    prompt = (
        "Based on these search results, identify the top trending POD niches right now:\n"
        f"{search_results}\n\n"
        "Return a ranked list of 10 niches with:\n"
        "- Niche name\n"
        "- Why it's trending\n"
        "- Best product type\n"
        "- Example design angle\n"
        "- Estimated competition level"
    )
    return _ai(prompt, system)


def _bot_reply(message: str):
    append_chatlog({"type": "bot", "bot": "print-on-demand", "message": message, "ts": now_iso()})
    print(f"[{now_iso()}] print-on-demand reply: {message[:120]}")


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

        if not msg_lower.startswith("pod"):
            continue

        # pod status
        if msg_lower in ("pod status", "pod stats"):
            registry = _load_registry()
            niches = list({r.get("niche", "") for r in registry if r.get("niche")})
            listings = [r for r in registry if r.get("type") == "listing"]
            tip = (
                "Target 40% margins. "
                "Viral niche design at 100 sales/day = $4K+/mo. "
                "Focus: pets, gaming, nurses, funny quotes."
            )
            reply = (
                f"🖨️ Print-on-Demand Bot Status\n"
                f"  Total designs/entries : {len(registry)}\n"
                f"  Listings generated    : {len(listings)}\n"
                f"  Niches covered        : {len(niches)}\n"
                f"  Default platform      : {DEFAULT_PLATFORM}\n"
                f"  Target margin         : {TARGET_MARGIN}%\n"
                f"  💰 Revenue tip: {tip}"
            )
            _bot_reply(reply)
            continue

        # pod trends
        if msg_lower in ("pod trends", "pod trend"):
            _bot_reply("🔍 Searching for current POD trends…")
            trends = _gen_trends()
            _bot_reply(f"📈 Trending POD Niches:\n\n{trends}")
            continue

        # pod research <niche>
        if msg_lower.startswith("pod research "):
            niche = msg[len("pod research "):].strip()
            if not niche:
                _bot_reply("Usage: pod research <niche>")
                continue
            _bot_reply(f"🔍 Researching POD opportunities in '{niche}'…")
            result = _gen_research(niche)
            _register_design({"type": "research", "niche": niche, "result": result})
            _bot_reply(f"📊 POD Research — {niche}:\n\n{result}")
            continue

        # pod design <niche>
        if msg_lower.startswith("pod design "):
            niche = msg[len("pod design "):].strip()
            if not niche:
                _bot_reply("Usage: pod design <niche>")
                continue
            prompts = _gen_design_prompts(niche)
            _register_design({"type": "design_prompts", "niche": niche, "prompts": prompts})
            _bot_reply(f"🎨 Design Prompts — {niche}:\n\n{prompts}")
            continue

        # pod listing <design_idea>
        if msg_lower.startswith("pod listing "):
            design = msg[len("pod listing "):].strip()
            if not design:
                _bot_reply("Usage: pod listing <design idea>")
                continue
            listing = _gen_listing(design)
            design_id = _register_design({"type": "listing", "niche": design, **listing})
            reply = (
                f"🏷️ Product Listing [{design_id}] — {design}\n"
                f"  Title      : {listing['title']}\n"
                f"  Base cost  : {listing['base_cost']}\n"
                f"  Sell price : {listing['sell_price']}\n"
                f"  Tags       : {', '.join((listing.get('tags') or [])[:6])}…\n"
                f"  Margin note: {listing['margin_note']}\n\n"
                f"Description:\n{listing['description']}"
            )
            _bot_reply(reply)
            continue

        # pod ads <product>
        if msg_lower.startswith("pod ads "):
            product = msg[len("pod ads "):].strip()
            if not product:
                _bot_reply("Usage: pod ads <product>")
                continue
            ads = _gen_ads(product)
            _register_design({"type": "ads", "niche": product, "copy": ads})
            _bot_reply(f"📣 Ad Copy — {product}:\n\n{ads}")
            continue

        # pod mockup <design_idea>
        if msg_lower.startswith("pod mockup "):
            design = msg[len("pod mockup "):].strip()
            if not design:
                _bot_reply("Usage: pod mockup <design idea>")
                continue
            mockup = _gen_mockup(design)
            _bot_reply(f"📸 Mockup Brief — {design}:\n\n{mockup}")
            continue

    return new_idx


def main():
    print(f"[{now_iso()}] print-on-demand started")
    last_idx = len(load_chatlog())
    write_state({"bot": "print-on-demand", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] print-on-demand error: {exc}")
        write_state({"bot": "print-on-demand", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
