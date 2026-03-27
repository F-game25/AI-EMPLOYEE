"""Discovery bot — Skill & Market Discovery.

Observes available skills, state files, and market data to propose
new skills or markets that could benefit the AI employee system.

Uses Ollama (local LLM) as the primary AI for proposal generation.
Falls back to Anthropic Claude or OpenAI only when Ollama is unavailable.

SAFE: proposals are NEVER auto-applied. They require explicit user approval
via the UI or WhatsApp before any code changes are made.

Proposals are written to:  ~/.ai-employee/state/improvements.json
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
IMPROVEMENTS_FILE = AI_HOME / "state" / "improvements.json"
STATE_FILE = AI_HOME / "state" / "discovery.state.json"
IMPROVEMENTS_DIR = AI_HOME / "improvements"

SCAN_INTERVAL = int(os.environ.get("DISCOVERY_SCAN_INTERVAL", "3600"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("discovery")

# ── AI router (Ollama first, cloud fallback) ──────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai as _query_ai  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_improvements() -> list:
    if not IMPROVEMENTS_FILE.exists():
        return []
    try:
        return json.loads(IMPROVEMENTS_FILE.read_text())
    except Exception:
        return []


def save_improvements(improvements: list):
    IMPROVEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    IMPROVEMENTS_FILE.write_text(json.dumps(improvements, indent=2))


def existing_proposal_ids(improvements: list) -> set:
    return {imp.get("id", "") for imp in improvements}


def scan_skill_gaps(improvements: list) -> list:
    """Identify potential skill gaps based on workspace analysis.

    Uses AI router (Ollama first, cloud fallback) to generate dynamic proposals
    when available.  Falls back to a curated static list when no AI is reachable.
    """
    new_proposals = []
    existing_ids = existing_proposal_ids(improvements)

    # Scan existing skill files to understand coverage
    workspace_dirs = list(AI_HOME.glob("workspace-*/skills"))
    skill_count = sum(len(list(d.glob("*.md"))) for d in workspace_dirs)

    # Try AI-powered proposal generation first (Ollama → cloud fallback)
    ai_proposals = _ai_scan_skill_gaps(existing_ids, skill_count) if _AI_AVAILABLE else []
    if ai_proposals:
        return ai_proposals

    # Fallback: static curated candidate skills
    candidate_skills = [
        {
            "id": "skill_video_content",
            "title": "Video Content Script Generator",
            "description": "Generate scripts for YouTube/TikTok/Reels for the creative-studio agent",
            "agent": "creative-studio",
            "type": "new_skill",
            "effort": "low",
        },
        {
            "id": "skill_linkedin_outreach",
            "title": "LinkedIn Message Personalization",
            "description": "Generate personalized LinkedIn connection requests at scale for lead-hunter agent",
            "agent": "lead-hunter",
            "type": "new_skill",
            "effort": "low",
        },
        {
            "id": "skill_market_sentiment",
            "title": "Crypto Market Sentiment Analysis",
            "description": "Analyze social media sentiment for crypto assets in crypto-trader agent",
            "agent": "crypto-trader",
            "type": "new_skill",
            "effort": "medium",
        },
        {
            "id": "skill_polymarket_auto_research",
            "title": "Automated Polymarket Research Loop",
            "description": "Periodically scan Polymarket for high-edge opportunities using intel-agent + crypto-trader",
            "agent": "orchestrator",
            "type": "workflow",
            "effort": "medium",
        },
        {
            "id": "market_niche_research",
            "title": "Niche E-commerce Market Research",
            "description": "Use product-scout + data-analyst to identify underserved niches on Amazon/Etsy",
            "agent": "product-scout",
            "type": "workflow",
            "effort": "low",
        },
    ]

    for candidate in candidate_skills:
        cid = candidate["id"]
        if cid not in existing_ids:
            new_proposals.append(
                {
                    **candidate,
                    "status": "pending",
                    "proposed_at": now_iso(),
                    "proposed_by": "discovery-bot",
                    "auto_applied": False,
                }
            )

    return new_proposals


def _ai_scan_skill_gaps(existing_ids: set, current_skill_count: int) -> list:
    """Use the AI router to generate intelligent skill gap proposals."""
    existing_list = ", ".join(sorted(existing_ids)) if existing_ids else "none yet"

    prompt = (
        f"We have an AI employee system with {current_skill_count} skills across agents like "
        "lead-hunter, content-master, social-guru, intel-agent, product-scout, email-ninja, "
        "support-bot, data-analyst, creative-studio, crypto-trader, bot-dev, web-sales, orchestrator.\n\n"
        f"Existing proposal IDs (already suggested, do NOT repeat): {existing_list}\n\n"
        "Propose 3 new skills or workflow improvements that would genuinely help this system. "
        "For each proposal output a JSON object on a single line with keys: "
        "id (snake_case, unique), title, description, agent, type (new_skill|workflow|market), effort (low|medium|high). "
        "Output ONLY the JSON objects, one per line, nothing else."
    )
    system = (
        "You are a system architect proposing improvements for an AI employee automation platform. "
        "Output ONLY raw JSON objects, one per line. No markdown, no explanation."
    )

    try:
        result = _query_ai(prompt, system_prompt=system)
        if not result.get("answer"):
            return []

        proposals = []
        for line in result["answer"].splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                candidate = json.loads(line)
                cid = candidate.get("id", "").strip()
                if not cid or cid in existing_ids:
                    continue
                # Validate required fields
                if not all(k in candidate for k in ("title", "description", "agent", "type")):
                    continue
                proposals.append({
                    "id": cid,
                    "title": candidate["title"],
                    "description": candidate["description"],
                    "agent": candidate.get("agent", "orchestrator"),
                    "type": candidate.get("type", "new_skill"),
                    "effort": candidate.get("effort", "medium"),
                    "status": "pending",
                    "proposed_at": now_iso(),
                    "proposed_by": f"discovery-bot (via {result.get('provider', 'ai')})",
                    "auto_applied": False,
                })
            except (json.JSONDecodeError, KeyError):
                continue

        if proposals:
            logger.info("discovery: AI generated %d proposals via %s", len(proposals), result.get("provider"))
        return proposals

    except Exception as exc:
        logger.warning("discovery: AI proposal generation failed — %s", exc)
        return []


def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    ai_status = "Ollama-first routing active" if _AI_AVAILABLE else "AI router not available (using static proposals)"
    print(f"[{now_iso()}] discovery bot started; scan_interval={SCAN_INTERVAL}s; {ai_status}")
    IMPROVEMENTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        improvements = load_improvements()
        new_proposals = scan_skill_gaps(improvements)

        if new_proposals:
            improvements.extend(new_proposals)
            save_improvements(improvements)
            print(f"[{now_iso()}] discovery: added {len(new_proposals)} new proposals")
        else:
            print(f"[{now_iso()}] discovery: no new proposals this cycle")

        pending = sum(1 for imp in improvements if imp.get("status") == "pending")
        write_state(
            {
                "bot": "discovery",
                "ts": now_iso(),
                "status": "running",
                "total_proposals": len(improvements),
                "pending_proposals": pending,
                "note": "All proposals require explicit user approval before any changes are made.",
            }
        )

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
