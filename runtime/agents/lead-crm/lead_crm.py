"""Lead CRM — Deal pipeline, lead scoring, and follow-up scheduling.

Manages the full sales pipeline from first contact to closed deal:
  - Deal pipeline stages: new_lead → qualified → proposal_sent → negotiation → closed_won → closed_lost
  - AI-powered lead scoring (0-100)
  - Follow-up scheduling with reminders
  - Pipeline analytics and stage counts

Commands (via chat / WhatsApp / Dashboard):
  crm add <name> <company> <email>    — add a new lead
  crm list                            — list all leads
  crm pipeline                        — show pipeline by stage
  crm score <id>                      — AI-score a lead
  crm stage <id> <stage>             — move lead to new stage
  crm followup <id> <date>           — schedule a follow-up
  crm status                          — pipeline summary

State files:
  ~/.ai-employee/state/leads-crm.json
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
CRM_FILE = AI_HOME / "state" / "leads-crm.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("lead-crm")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

PIPELINE_STAGES = [
    "new_lead",
    "qualified",
    "proposal_sent",
    "negotiation",
    "closed_won",
    "closed_lost",
]

__all__ = [
    "list_leads",
    "get_lead",
    "add_lead",
    "update_lead",
    "delete_lead",
    "move_stage",
    "schedule_followup",
    "get_pipeline",
    "score_lead",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_crm() -> dict:
    if not CRM_FILE.exists():
        return {"leads": []}
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return {"leads": []}


def _save_crm(data: dict) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(data, indent=2))


def list_leads(stage: Optional[str] = None, search: Optional[str] = None) -> list:
    """Return all leads, optionally filtered by stage or search term."""
    data = _load_crm()
    leads = data.get("leads", [])
    if stage:
        leads = [l for l in leads if l.get("stage") == stage]
    if search:
        q = search.lower()
        leads = [
            l for l in leads
            if q in l.get("name", "").lower()
            or q in l.get("company", "").lower()
            or q in l.get("email", "").lower()
        ]
    return sorted(leads, key=lambda x: x.get("created_at", ""), reverse=True)


def get_lead(lead_id: str) -> Optional[dict]:
    """Return a single lead by ID."""
    data = _load_crm()
    return next((l for l in data["leads"] if l["id"] == lead_id), None)


def add_lead(
    name: str,
    company: str = "",
    email: str = "",
    phone: str = "",
    source: str = "",
    notes: str = "",
    value: float = 0.0,
    tags: Optional[list] = None,
) -> dict:
    """Create a new lead in the new_lead stage."""
    data = _load_crm()
    lead = {
        "id": str(uuid.uuid4()),
        "name": name,
        "company": company,
        "email": email,
        "phone": phone,
        "source": source,
        "notes": notes,
        "value": value,
        "tags": tags or [],
        "stage": "new_lead",
        "score": 0,
        "score_reason": "",
        "followup_at": None,
        "followup_note": "",
        "stage_history": [{"stage": "new_lead", "at": _now_iso()}],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["leads"].append(lead)
    _save_crm(data)
    logger.info("Lead added: %s", lead["id"])
    return lead


def update_lead(lead_id: str, updates: dict) -> Optional[dict]:
    """Update lead fields. Returns updated lead or None if not found."""
    data = _load_crm()
    for i, lead in enumerate(data["leads"]):
        if lead["id"] == lead_id:
            # Prevent overwriting protected fields
            updates.pop("id", None)
            updates.pop("stage_history", None)
            updates.pop("created_at", None)
            data["leads"][i].update(updates)
            data["leads"][i]["updated_at"] = _now_iso()
            _save_crm(data)
            return data["leads"][i]
    return None


def delete_lead(lead_id: str) -> bool:
    """Delete a lead. Returns True if deleted."""
    data = _load_crm()
    before = len(data["leads"])
    data["leads"] = [l for l in data["leads"] if l["id"] != lead_id]
    if len(data["leads"]) < before:
        _save_crm(data)
        return True
    return False


def move_stage(lead_id: str, new_stage: str) -> Optional[dict]:
    """Move a lead to a new pipeline stage."""
    if new_stage not in PIPELINE_STAGES:
        raise ValueError(f"Invalid stage '{new_stage}'. Must be one of: {PIPELINE_STAGES}")
    data = _load_crm()
    for i, lead in enumerate(data["leads"]):
        if lead["id"] == lead_id:
            data["leads"][i]["stage"] = new_stage
            data["leads"][i]["updated_at"] = _now_iso()
            data["leads"][i].setdefault("stage_history", []).append(
                {"stage": new_stage, "at": _now_iso()}
            )
            _save_crm(data)
            return data["leads"][i]
    return None


def schedule_followup(lead_id: str, followup_at: str, note: str = "") -> Optional[dict]:
    """Schedule a follow-up for a lead."""
    data = _load_crm()
    for i, lead in enumerate(data["leads"]):
        if lead["id"] == lead_id:
            data["leads"][i]["followup_at"] = followup_at
            data["leads"][i]["followup_note"] = note
            data["leads"][i]["updated_at"] = _now_iso()
            _save_crm(data)
            return data["leads"][i]
    return None


def get_pipeline() -> dict:
    """Return pipeline view: count and total value per stage."""
    data = _load_crm()
    pipeline = {stage: {"count": 0, "value": 0.0, "leads": []} for stage in PIPELINE_STAGES}
    for lead in data.get("leads", []):
        stage = lead.get("stage", "new_lead")
        if stage in pipeline:
            pipeline[stage]["count"] += 1
            pipeline[stage]["value"] += float(lead.get("value", 0))
            pipeline[stage]["leads"].append({
                "id": lead["id"],
                "name": lead["name"],
                "company": lead.get("company", ""),
                "value": lead.get("value", 0),
                "score": lead.get("score", 0),
                "followup_at": lead.get("followup_at"),
            })
    return pipeline


def score_lead(lead_id: str) -> Optional[dict]:
    """AI-score a lead 0-100 based on their profile."""
    lead = get_lead(lead_id)
    if not lead:
        return None

    if _AI_AVAILABLE:
        prompt = (
            f"Score this sales lead from 0-100 based on their potential.\n\n"
            f"Name: {lead.get('name', '')}\n"
            f"Company: {lead.get('company', '')}\n"
            f"Email: {lead.get('email', '')}\n"
            f"Phone: {lead.get('phone', '')}\n"
            f"Source: {lead.get('source', '')}\n"
            f"Notes: {lead.get('notes', '')}\n"
            f"Deal Value: ${lead.get('value', 0)}\n"
            f"Current Stage: {lead.get('stage', 'new_lead')}\n\n"
            f"Respond ONLY with valid JSON: "
            f'{{\"score\": <0-100>, \"reason\": \"<brief explanation>\"}}'
        )
        try:
            result = _query_ai_for_agent("lead-crm", prompt)
            content = result.get("content", result.get("text", ""))
            parsed = json.loads(content[content.find("{"):content.rfind("}") + 1])
            score = max(0, min(100, int(parsed.get("score", 50))))
            reason = parsed.get("reason", "")
        except Exception:
            score = _heuristic_score(lead)
            reason = "Heuristic scoring (AI unavailable)"
    else:
        score = _heuristic_score(lead)
        reason = "Heuristic scoring (AI not configured)"

    updated = update_lead(lead_id, {"score": score, "score_reason": reason})
    return updated


def _heuristic_score(lead: dict) -> int:
    """Simple heuristic scoring when AI is not available."""
    score = 30
    if lead.get("email"):
        score += 15
    if lead.get("phone"):
        score += 10
    if lead.get("company"):
        score += 10
    if float(lead.get("value", 0)) > 1000:
        score += 20
    if float(lead.get("value", 0)) > 10000:
        score += 10
    if lead.get("notes"):
        score += 5
    return min(score, 100)
