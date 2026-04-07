"""Email Marketing Automation — Campaign management, sequences, and AI copy generation.

Full-pipeline email marketing system:
  - Campaign creation and management with multi-step sequences
  - Configurable step delays (day 1, 3, 7 follow-ups)
  - Mock tracking: open/click/reply events stored in JSONL
  - SPF/DKIM/DMARC deliverability tips
  - AI-powered email copy writing via ai_router

Commands (via chat / WhatsApp / Dashboard):
  email campaign <name>             — create a new campaign
  email list                        — list all campaigns
  email send <id>                   — trigger send simulation
  email stats <id>                  — show open/click/reply stats
  email write <goal>                — AI-generate email copy
  email status                      — campaigns overview

State files:
  ~/.ai-employee/state/email-campaigns.json
  ~/.ai-employee/state/email-events.jsonl
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
CAMPAIGNS_FILE = AI_HOME / "state" / "email-campaigns.json"
EVENTS_FILE = AI_HOME / "state" / "email-events.jsonl"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("email-marketing")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

DELIVERABILITY_TIPS = [
    "Set up SPF record: v=spf1 include:your-provider.com ~all",
    "Configure DKIM signing — 1024-bit minimum, 2048-bit recommended",
    "Add DMARC policy: v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com",
    "Warm up new sending domains gradually over 4-6 weeks",
    "Keep bounce rate under 2% and spam complaint rate under 0.1%",
    "Use a dedicated sending subdomain (e.g., mail.yourdomain.com)",
    "Authenticate with BIMI to display your logo in email clients",
    "Monitor your sender reputation via Google Postmaster Tools",
]

__all__ = [
    "list_campaigns",
    "get_campaign",
    "create_campaign",
    "update_campaign",
    "delete_campaign",
    "send_campaign",
    "get_campaign_stats",
    "write_email_copy",
    "get_deliverability_tips",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_campaigns() -> dict:
    if not CAMPAIGNS_FILE.exists():
        return {"campaigns": []}
    try:
        return json.loads(CAMPAIGNS_FILE.read_text())
    except Exception:
        return {"campaigns": []}


def _save_campaigns(data: dict) -> None:
    CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_FILE.write_text(json.dumps(data, indent=2))


def _append_event(campaign_id: str, event_type: str, step: int = 0, recipient: str = "") -> None:
    """Append a tracking event to the JSONL log."""
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "id": str(uuid.uuid4()),
        "campaign_id": campaign_id,
        "event_type": event_type,
        "step": step,
        "recipient": recipient,
        "at": _now_iso(),
    }
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


def _load_events(campaign_id: Optional[str] = None) -> list:
    if not EVENTS_FILE.exists():
        return []
    events = []
    try:
        for line in EVENTS_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
                if campaign_id is None or ev.get("campaign_id") == campaign_id:
                    events.append(ev)
            except Exception:
                pass
    except Exception:
        pass
    return events


def list_campaigns(status: Optional[str] = None) -> list:
    """Return all campaigns, optionally filtered by status."""
    data = _load_campaigns()
    campaigns = data.get("campaigns", [])
    if status:
        campaigns = [c for c in campaigns if c.get("status") == status]
    return sorted(campaigns, key=lambda x: x.get("created_at", ""), reverse=True)


def get_campaign(campaign_id: str) -> Optional[dict]:
    """Return a single campaign by ID."""
    data = _load_campaigns()
    return next((c for c in data["campaigns"] if c["id"] == campaign_id), None)


def create_campaign(
    name: str,
    subject: str,
    body: str,
    from_name: str = "",
    from_email: str = "",
    recipients: Optional[list] = None,
    sequence_steps: Optional[list] = None,
) -> dict:
    """Create a new email campaign with optional sequence steps.

    sequence_steps format:
      [{"day": 1, "subject": "...", "body": "..."},
       {"day": 3, "subject": "Follow-up", "body": "..."},
       {"day": 7, "subject": "Last chance", "body": "..."}]
    """
    data = _load_campaigns()
    campaign = {
        "id": str(uuid.uuid4()),
        "name": name,
        "subject": subject,
        "body": body,
        "from_name": from_name,
        "from_email": from_email,
        "recipients": recipients or [],
        "sequence_steps": sequence_steps or [],
        "status": "draft",
        "sent_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["campaigns"].append(campaign)
    _save_campaigns(data)
    logger.info("Campaign created: %s", campaign["id"])
    return campaign


def update_campaign(campaign_id: str, updates: dict) -> Optional[dict]:
    """Update campaign fields."""
    data = _load_campaigns()
    for i, camp in enumerate(data["campaigns"]):
        if camp["id"] == campaign_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            data["campaigns"][i].update(updates)
            data["campaigns"][i]["updated_at"] = _now_iso()
            _save_campaigns(data)
            return data["campaigns"][i]
    return None


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign. Returns True if deleted."""
    data = _load_campaigns()
    before = len(data["campaigns"])
    data["campaigns"] = [c for c in data["campaigns"] if c["id"] != campaign_id]
    if len(data["campaigns"]) < before:
        _save_campaigns(data)
        return True
    return False


def send_campaign(campaign_id: str) -> Optional[dict]:
    """Simulate sending a campaign. Records open/click events for each recipient."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None

    recipients = campaign.get("recipients", [])
    if not recipients:
        recipients = ["demo@example.com"]

    import random
    for recipient in recipients:
        _append_event(campaign_id, "sent", step=0, recipient=recipient)
        opened = random.random() < 0.42
        if opened:
            _append_event(campaign_id, "open", step=0, recipient=recipient)
        if opened and random.random() < 0.28:
            _append_event(campaign_id, "click", step=0, recipient=recipient)
        if opened and random.random() < 0.09:
            _append_event(campaign_id, "reply", step=0, recipient=recipient)

        for step_idx, step in enumerate(campaign.get("sequence_steps", []), 1):
            step_sent = random.random() < 0.30
            if step_sent:
                _append_event(campaign_id, "sent", step=step_idx, recipient=recipient)
            step_opened = step_sent and random.random() < 0.25
            if step_opened:
                _append_event(campaign_id, "open", step=step_idx, recipient=recipient)

    updated = update_campaign(campaign_id, {"status": "sent", "sent_at": _now_iso()})
    return updated


def get_campaign_stats(campaign_id: str) -> dict:
    """Return open/click/reply/sent counts for a campaign."""
    events = _load_events(campaign_id)
    stats = {"sent": 0, "opens": 0, "clicks": 0, "replies": 0, "open_rate": 0.0, "click_rate": 0.0}
    for ev in events:
        et = ev.get("event_type", "")
        if et == "sent":
            stats["sent"] += 1
        elif et == "open":
            stats["opens"] += 1
        elif et == "click":
            stats["clicks"] += 1
        elif et == "reply":
            stats["replies"] += 1
    if stats["sent"] > 0:
        stats["open_rate"] = round(stats["opens"] / stats["sent"] * 100, 1)
        stats["click_rate"] = round(stats["clicks"] / stats["sent"] * 100, 1)
    return stats


def write_email_copy(goal: str, tone: str = "professional", audience: str = "") -> dict:
    """AI-generate email subject and body for a given goal."""
    if _AI_AVAILABLE:
        prompt = (
            f"Write a high-converting email for the following goal:\n\n"
            f"Goal: {goal}\n"
            f"Tone: {tone}\n"
            f"Target audience: {audience or 'business professionals'}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"subject": "...", "body": "...", "preview_text": "..."}}'
        )
        try:
            result = _query_ai_for_agent("email-marketing", prompt)
            content = result.get("content", result.get("text", ""))
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                return {
                    "subject": parsed.get("subject", ""),
                    "body": parsed.get("body", ""),
                    "preview_text": parsed.get("preview_text", ""),
                    "ai_generated": True,
                }
        except Exception:
            pass

    return {
        "subject": f"[{goal[:40]}] — Important Update",
        "body": (
            f"Hi [First Name],\n\n"
            f"I wanted to reach out regarding {goal}.\n\n"
            f"[Add your compelling value proposition here]\n\n"
            f"Best regards,\n[Your Name]"
        ),
        "preview_text": f"Regarding {goal[:50]}...",
        "ai_generated": False,
    }


def get_deliverability_tips() -> list:
    """Return email deliverability best practices."""
    return DELIVERABILITY_TIPS
