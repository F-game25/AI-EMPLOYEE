"""Chatbot Builder Bot — niche-specific custom chatbot generator.

Creates complete chatbot templates for target niches: fitness plans, recipe
generators, dating advice, customer service, and business coaching. Outputs
full chatbot configs including persona, system prompts, FAQ libraries,
conversation flows, and SaaS pricing tiers for a rental model.

Commands:
  chatbot create <niche>   — generate complete chatbot (persona + prompts + FAQs + flow)
  chatbot flow <niche>     — generate conversation flow diagram (text tree)
  chatbot scripts <niche>  — generate 30 pre-written response scripts
  chatbot pricing <niche>  — generate SaaS pricing tiers (basic/pro/enterprise)
  chatbot deploy <name>    — generate deployment guide for the chatbot
  chatbot list             — list all created chatbots
  chatbot status           — total bots created, niches covered
"""
import json, os, re, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME     = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE  = AI_HOME / "state" / "chatbot-builder.state.json"
CHATLOG     = AI_HOME / "state" / "chatlog.jsonl"
BOTS_DIR    = AI_HOME / "state" / "chatbots"

POLL_INTERVAL    = int(os.environ.get("CHATBOT_BUILDER_POLL_INTERVAL", "5"))
DEFAULT_LANGUAGE = os.environ.get("CHATBOT_DEFAULT_LANGUAGE", "nl")

SUPPORTED_NICHES = [
    "fitness", "recipe", "dating", "customer-service", "business-coaching",
    "real-estate", "e-commerce", "health", "education", "finance",
]

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── helpers ───────────────────────────────────────────────────────────────────

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

def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable — install deps]"
    return (_query_ai_for_agent("chatbot-builder", prompt, system_prompt=system) or {}).get("answer", "")

def slug(niche: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "-", niche.lower().strip())

def bot_path(niche: str) -> Path:
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    return BOTS_DIR / f"{slug(niche)}_chatbot.json"

def load_bot(niche: str) -> dict | None:
    p = bot_path(niche)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

def save_bot(bot: dict):
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = BOTS_DIR / f"{slug(bot['niche'])}_chatbot.json"
    path.write_text(json.dumps(bot, indent=2))

def list_bots() -> list[dict]:
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    bots: list[dict] = []
    for p in sorted(BOTS_DIR.glob("*_chatbot.json")):
        try:
            bots.append(json.loads(p.read_text()))
        except Exception:
            pass
    return bots


# ── niche persona library ─────────────────────────────────────────────────────

NICHE_DEFAULTS: dict[str, dict] = {
    "fitness": {
        "name": "FitBot",
        "personality": "Energetic, motivating, science-backed fitness expert",
        "tone": "upbeat, encouraging, direct",
        "language_hint": "Use simple, jargon-free fitness language.",
    },
    "recipe": {
        "name": "ChefBot",
        "personality": "Creative home chef who loves experimenting with flavours",
        "tone": "warm, enthusiastic, approachable",
        "language_hint": "Use ingredient-first language, mention cook times.",
    },
    "dating": {
        "name": "MatchBot",
        "personality": "Empathetic relationship coach with a sense of humour",
        "tone": "supportive, witty, non-judgmental",
        "language_hint": "Focus on authentic connection and confidence.",
    },
    "customer-service": {
        "name": "SupportBot",
        "personality": "Professional, patient, solution-focused support agent",
        "tone": "formal but friendly, clear, concise",
        "language_hint": "Always acknowledge feelings before solving.",
    },
    "business-coaching": {
        "name": "CoachBot",
        "personality": "High-performance business coach with startup experience",
        "tone": "direct, challenging, results-oriented",
        "language_hint": "Use ROI framing and action-oriented language.",
    },
}


# ── content generators ────────────────────────────────────────────────────────

def generate_persona_and_system_prompt(niche: str) -> dict:
    defaults = NICHE_DEFAULTS.get(slug(niche), {
        "name": f"{niche.title()}Bot",
        "personality": f"Expert AI assistant specialised in {niche}",
        "tone": "professional, helpful, knowledgeable",
        "language_hint": f"Always stay focused on {niche} topics.",
    })
    prompt = (
        f"Create a detailed chatbot persona and system prompt for a {niche} chatbot.\n"
        f"Starting persona: name={defaults['name']}, personality={defaults['personality']}\n\n"
        f"Provide:\n"
        f"1. Final persona name (creative, memorable)\n"
        f"2. Personality description (3 sentences)\n"
        f"3. Tone descriptor (3-5 words)\n"
        f"4. System prompt (150-200 words) that defines the bot's role, boundaries, "
        f"language style, and default language: {DEFAULT_LANGUAGE}\n"
    )
    ai_output = _ai(prompt, system="You design world-class AI chatbot personas and system prompts.")

    # Parse sections from AI output with fallbacks
    name_m = re.search(r"(?:name[:\s]+)([A-Z][a-zA-Z]+(?:Bot|AI|Coach)?)", ai_output)
    persona_name = name_m.group(1) if name_m else defaults["name"]

    system_m = re.search(r"(?:system prompt[:\n]+)(.*?)(?:\n\d\.|\Z)", ai_output, re.DOTALL | re.IGNORECASE)
    system_prompt = system_m.group(1).strip()[:600] if system_m else ai_output[:400]

    return {
        "name": persona_name,
        "personality": defaults["personality"],
        "tone": defaults["tone"],
        "system_prompt": system_prompt,
        "language": DEFAULT_LANGUAGE,
    }

def generate_faqs(niche: str, persona_name: str) -> list[dict]:
    prompt = (
        f"Generate 20 FAQ question-answer pairs for a {niche} chatbot named {persona_name}.\n"
        f"Each answer should be 2-4 sentences, helpful, and in the bot's tone.\n"
        f"Format each as:\nQ: [question]\nA: [answer]\n\n"
        f"Cover: beginner questions, common problems, how-to requests, "
        f"pricing/service questions, and edge cases."
    )
    ai_output = _ai(prompt, system=f"You write FAQ libraries for {niche} chatbots.")
    faqs: list[dict] = []
    qa_pattern = re.compile(r"Q:\s*(.+?)\nA:\s*(.+?)(?=\nQ:|\Z)", re.DOTALL)
    for m in qa_pattern.finditer(ai_output):
        faqs.append({"q": m.group(1).strip(), "a": m.group(2).strip()})
        if len(faqs) >= 20:
            break
    # Pad if AI returned fewer than 20
    while len(faqs) < 20:
        faqs.append({"q": f"What can you help me with in {niche}?",
                     "a": f"I specialise in {niche} and can answer questions, give advice, and help you reach your goals."})
    return faqs

def generate_conversation_flow(niche: str) -> str:
    prompt = (
        f"Generate a text-based conversation flow tree for a {niche} chatbot.\n"
        f"Use ASCII tree format with these stages:\n"
        f"GREETING → QUALIFY (understand user need) → SOLVE (provide value) → UPSELL (premium tier) → CLOSE (CTA)\n\n"
        f"For each stage show 2-3 example bot messages and 2 user response branches.\n"
        f"Include a fallback/error branch.\n"
        f"Format as an indented tree with arrows (→) and branch markers (├─, └─)."
    )
    return _ai(prompt, system=f"You design chatbot conversation flows for {niche} applications.")

def generate_scripts(niche: str, persona_name: str) -> list[str]:
    prompt = (
        f"Generate 30 pre-written response scripts for a {niche} chatbot named {persona_name}.\n"
        f"Cover these categories (6 scripts each):\n"
        f"1. Greetings & openers\n"
        f"2. Clarifying questions\n"
        f"3. Core {niche} advice responses\n"
        f"4. Upsell / upgrade prompts\n"
        f"5. Conversation closers & CTAs\n\n"
        f"Number each script (1-30). Keep each 1-3 sentences."
    )
    ai_output = _ai(prompt, system=f"You write pre-scripted responses for {niche} chatbots.")
    scripts: list[str] = []
    for line in ai_output.split("\n"):
        line = line.strip()
        if re.match(r"^\d+[\.\)]\s+", line):
            scripts.append(re.sub(r"^\d+[\.\)]\s+", "", line))
        elif line and scripts:
            scripts[-1] += " " + line  # continuation lines
        if len(scripts) >= 30:
            break
    while len(scripts) < 30:
        scripts.append(f"I'm here to help with your {niche} journey! What would you like to know?")
    return scripts[:30]

def generate_pricing_tiers(niche: str) -> dict:
    prompt = (
        f"Generate SaaS pricing tiers for renting a {niche} chatbot.\n"
        f"Create 3 tiers: Basic, Pro, Enterprise.\n"
        f"For each tier provide:\n"
        f"- Price (monthly, in EUR)\n"
        f"- 5-7 features\n"
        f"- Ideal customer description (1 sentence)\n"
        f"- Message limit per month\n"
        f"- Support level\n"
        f"Format clearly with tier names as headers."
    )
    ai_output = _ai(prompt, system="You design SaaS pricing for AI chatbot rental services.")

    tiers: dict[str, dict] = {}
    for tier_name in ("Basic", "Pro", "Enterprise"):
        pattern = re.compile(
            rf"{tier_name}.*?(?=\n(?:Basic|Pro|Enterprise|\Z))", re.DOTALL | re.IGNORECASE
        )
        m = pattern.search(ai_output)
        price_m = re.search(r"€?\s*(\d+(?:\.\d+)?)\s*(?:/month|per month|monthly)", 
                            m.group(0) if m else "", re.IGNORECASE)
        price = float(price_m.group(1)) if price_m else {"Basic": 29, "Pro": 79, "Enterprise": 199}[tier_name]
        tiers[tier_name.lower()] = {
            "name":    tier_name,
            "price":   price,
            "content": (m.group(0)[:600] if m else f"{tier_name} tier for {niche} chatbot — €{price}/mo"),
        }
    return {"tiers": tiers, "full_text": ai_output}

def generate_deployment_guide(bot: dict) -> str:
    niche = bot["niche"]
    name  = bot.get("persona", {}).get("name", f"{niche.title()}Bot")
    prompt = (
        f"Generate a concise deployment guide for a {niche} chatbot named '{name}'.\n\n"
        f"Include sections:\n"
        f"1. Prerequisites (API keys needed, hosting requirements)\n"
        f"2. Quick-start setup (5 steps)\n"
        f"3. Integration options: Website widget, WhatsApp (Twilio), Telegram Bot API, "
        f"   Facebook Messenger, Discord bot\n"
        f"4. Customisation: how to update system prompt, add FAQs, change persona\n"
        f"5. Monitoring & analytics tips\n"
        f"6. Scaling to multiple clients (SaaS rental notes)\n\n"
        f"System prompt excerpt: {bot.get('system_prompt','')[:200]}"
    )
    return _ai(prompt, system="You write developer-friendly deployment guides for AI chatbots.")


# ── command handlers ──────────────────────────────────────────────────────────

def cmd_chatbot_create(niche: str) -> str:
    print(f"[{now_iso()}] Generating chatbot for niche '{niche}'...")

    persona_data   = generate_persona_and_system_prompt(niche)
    faqs           = generate_faqs(niche, persona_data["name"])
    flow           = generate_conversation_flow(niche)
    scripts        = generate_scripts(niche, persona_data["name"])
    pricing        = generate_pricing_tiers(niche)

    bot = {
        "id":           str(uuid.uuid4())[:8],
        "niche":        niche,
        "persona":      {
            "name":        persona_data["name"],
            "personality": persona_data["personality"],
            "tone":        persona_data["tone"],
        },
        "system_prompt":     persona_data["system_prompt"],
        "language":          DEFAULT_LANGUAGE,
        "faqs":              faqs,
        "conversation_flow": flow,
        "scripts":           scripts,
        "pricing_tiers":     pricing,
        "created_at":        now_iso(),
        "updated_at":        now_iso(),
    }
    save_bot(bot)

    return (
        f"[{now_iso()}] Chatbot '{bot['persona']['name']}' created for niche '{niche}' [id={bot['id']}]\n"
        f"  FAQs generated     : {len(faqs)}\n"
        f"  Scripts generated  : {len(scripts)}\n"
        f"  Pricing tiers      : {', '.join(pricing['tiers'].keys())}\n"
        f"  Language           : {DEFAULT_LANGUAGE}\n"
        f"  Saved to           : {bot_path(niche)}\n\n"
        f"System prompt preview:\n{persona_data['system_prompt'][:300]}..."
    )

def cmd_chatbot_flow(niche: str) -> str:
    bot = load_bot(niche)
    if bot and bot.get("conversation_flow"):
        flow = bot["conversation_flow"]
    else:
        flow = generate_conversation_flow(niche)
        if bot:
            bot["conversation_flow"] = flow
            bot["updated_at"] = now_iso()
            save_bot(bot)
    return f"[{now_iso()}] Conversation flow for '{niche}':\n\n{flow}"

def cmd_chatbot_scripts(niche: str) -> str:
    bot = load_bot(niche)
    if bot and bot.get("scripts"):
        scripts = bot["scripts"]
        persona_name = bot.get("persona", {}).get("name", f"{niche.title()}Bot")
    else:
        persona_name = f"{niche.title()}Bot"
        scripts = generate_scripts(niche, persona_name)
        if bot:
            bot["scripts"] = scripts
            bot["updated_at"] = now_iso()
            save_bot(bot)

    lines = [f"[{now_iso()}] 30 Response Scripts for '{niche}' ({persona_name}):\n"]
    categories = ["Greetings & Openers", "Clarifying Questions",
                  f"Core {niche.title()} Advice", "Upsell / Upgrade",
                  "Closers & CTAs"]
    for i, script in enumerate(scripts[:30], 1):
        if (i - 1) % 6 == 0:
            cat = categories[(i - 1) // 6] if (i - 1) // 6 < len(categories) else "Additional"
            lines.append(f"\n── {cat} ──")
        lines.append(f"  {i:2d}. {script}")
    return "\n".join(lines)

def cmd_chatbot_pricing(niche: str) -> str:
    bot = load_bot(niche)
    if bot and bot.get("pricing_tiers"):
        pricing_text = bot["pricing_tiers"].get("full_text", "")
        if pricing_text:
            return f"[{now_iso()}] Pricing tiers for '{niche}':\n\n{pricing_text}"

    pricing = generate_pricing_tiers(niche)
    if bot:
        bot["pricing_tiers"] = pricing
        bot["updated_at"] = now_iso()
        save_bot(bot)
    return f"[{now_iso()}] Pricing tiers for '{niche}':\n\n{pricing['full_text']}"

def cmd_chatbot_deploy(bot_name: str) -> str:
    # Find bot by name or niche
    bots = list_bots()
    bot = next(
        (b for b in bots if b.get("persona", {}).get("name", "").lower() == bot_name.lower()
         or slug(b.get("niche", "")) == slug(bot_name)),
        None
    )
    if not bot:
        return (
            f"[{now_iso()}] Chatbot '{bot_name}' not found. "
            f"Use 'chatbot list' to see available bots, or 'chatbot create <niche>' first."
        )
    guide = generate_deployment_guide(bot)
    return f"[{now_iso()}] Deployment guide for '{bot_name}':\n\n{guide}"

def cmd_chatbot_list() -> str:
    bots = list_bots()
    if not bots:
        return f"[{now_iso()}] No chatbots created yet. Use 'chatbot create <niche>' to get started."
    lines = [f"[{now_iso()}] Created chatbots ({len(bots)} total):\n"]
    for bot in bots:
        persona = bot.get("persona", {})
        faq_count = len(bot.get("faqs", []))
        script_count = len(bot.get("scripts", []))
        tiers = ", ".join(bot.get("pricing_tiers", {}).get("tiers", {}).keys()) or "n/a"
        lines.append(
            f"  [{bot['id']}] {persona.get('name', '?'):20s} | niche={bot['niche']:<20s} "
            f"| FAQs={faq_count:2d} | scripts={script_count:2d} | tiers={tiers} "
            f"| created={bot.get('created_at','?')[:10]}"
        )
    return "\n".join(lines)

def cmd_chatbot_status() -> str:
    bots = list_bots()
    niches = list({bot.get("niche", "unknown") for bot in bots})
    state: dict = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    lines = [
        f"[{now_iso()}] Chatbot Builder Status",
        f"  Default language : {DEFAULT_LANGUAGE}",
        f"  Total bots built : {len(bots)}",
        f"  Niches covered   : {', '.join(niches) if niches else 'none yet'}",
        f"  Supported niches : {', '.join(SUPPORTED_NICHES)}",
        f"  Storage dir      : {BOTS_DIR}",
        f"  Bot status       : {state.get('status', 'unknown')}",
        f"  Last heartbeat   : {state.get('ts', 'n/a')}",
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

        if msg_lower.startswith("chatbot create "):
            niche = msg[len("chatbot create "):].strip()
            response = cmd_chatbot_create(niche) if niche else "Usage: chatbot create <niche>"
        elif msg_lower.startswith("chatbot flow "):
            niche = msg[len("chatbot flow "):].strip()
            response = cmd_chatbot_flow(niche) if niche else "Usage: chatbot flow <niche>"
        elif msg_lower.startswith("chatbot scripts "):
            niche = msg[len("chatbot scripts "):].strip()
            response = cmd_chatbot_scripts(niche) if niche else "Usage: chatbot scripts <niche>"
        elif msg_lower.startswith("chatbot pricing "):
            niche = msg[len("chatbot pricing "):].strip()
            response = cmd_chatbot_pricing(niche) if niche else "Usage: chatbot pricing <niche>"
        elif msg_lower.startswith("chatbot deploy "):
            name = msg[len("chatbot deploy "):].strip()
            response = cmd_chatbot_deploy(name) if name else "Usage: chatbot deploy <name>"
        elif msg_lower == "chatbot list":
            response = cmd_chatbot_list()
        elif msg_lower == "chatbot status":
            response = cmd_chatbot_status()

        if response:
            print(response)
            append_chatlog({"type": "bot", "bot": "chatbot-builder", "message": response, "ts": now_iso()})

    return new_idx


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{now_iso()}] chatbot-builder started; poll={POLL_INTERVAL}s")
    last_idx = len(load_chatlog())
    write_state({"bot": "chatbot-builder", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] chatbot-builder error: {exc}")
        write_state({"bot": "chatbot-builder", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
