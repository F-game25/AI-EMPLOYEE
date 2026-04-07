"""Competitor Watch Agent — Track, monitor, and analyze competitors with AI.

Keeps tabs on your competitive landscape:
  - Competitor records: name, website, notes, tags
  - AI-powered competitor analysis and positioning
  - Alert system: new insights stored when analyses run
  - Competitive landscape overview

Commands (via chat / WhatsApp / Dashboard):
  competitor add <name> <website>   — track a new competitor
  competitor list                   — list all competitors
  competitor analyze <id>           — AI-analyze a competitor
  competitor alerts                 — recent competitive alerts
  competitor status                 — overview of tracked competitors

State files:
  ~/.ai-employee/state/competitors.json
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
COMPETITORS_FILE = AI_HOME / "state" / "competitors.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("competitor-watch")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

__all__ = [
    "list_competitors",
    "get_competitor",
    "add_competitor",
    "update_competitor",
    "delete_competitor",
    "analyze_competitor",
    "get_alerts",
    "dismiss_alert",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_competitors() -> dict:
    if not COMPETITORS_FILE.exists():
        return {"competitors": [], "alerts": []}
    try:
        return json.loads(COMPETITORS_FILE.read_text())
    except Exception:
        return {"competitors": [], "alerts": []}


def _save_competitors(data: dict) -> None:
    COMPETITORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMPETITORS_FILE.write_text(json.dumps(data, indent=2))


def list_competitors(search: Optional[str] = None) -> list:
    """Return all tracked competitors."""
    data = _load_competitors()
    competitors = data.get("competitors", [])
    if search:
        q = search.lower()
        competitors = [
            c for c in competitors
            if q in c.get("name", "").lower()
            or q in c.get("website", "").lower()
            or q in c.get("notes", "").lower()
        ]
    return sorted(competitors, key=lambda x: x.get("tracked_since", ""), reverse=True)


def get_competitor(competitor_id: str) -> Optional[dict]:
    """Return a single competitor by ID."""
    data = _load_competitors()
    return next((c for c in data["competitors"] if c["id"] == competitor_id), None)


def add_competitor(
    name: str,
    website: str = "",
    notes: str = "",
    tags: Optional[list] = None,
    pricing: str = "",
    target_market: str = "",
) -> dict:
    """Add a new competitor to track."""
    data = _load_competitors()
    competitor = {
        "id": str(uuid.uuid4()),
        "name": name,
        "website": website,
        "notes": notes,
        "tags": tags or [],
        "pricing": pricing,
        "target_market": target_market,
        "tracked_since": _now_iso(),
        "last_analyzed": None,
        "analysis": "",
        "strengths": [],
        "weaknesses": [],
        "opportunities": [],
        "threats": [],
        "alert_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["competitors"].append(competitor)
    _save_competitors(data)
    logger.info("Competitor added: %s", name)
    return competitor


def update_competitor(competitor_id: str, updates: dict) -> Optional[dict]:
    """Update competitor fields."""
    data = _load_competitors()
    for i, comp in enumerate(data["competitors"]):
        if comp["id"] == competitor_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            data["competitors"][i].update(updates)
            data["competitors"][i]["updated_at"] = _now_iso()
            _save_competitors(data)
            return data["competitors"][i]
    return None


def delete_competitor(competitor_id: str) -> bool:
    """Delete a competitor from tracking."""
    data = _load_competitors()
    before = len(data["competitors"])
    data["competitors"] = [c for c in data["competitors"] if c["id"] != competitor_id]
    if len(data["competitors"]) < before:
        _save_competitors(data)
        return True
    return False


def analyze_competitor(competitor_id: str, your_product: str = "") -> Optional[dict]:
    """AI-analyze a competitor and store insights as an alert."""
    competitor = get_competitor(competitor_id)
    if not competitor:
        return None

    if _AI_AVAILABLE:
        prompt = (
            f"Analyze this competitor for a business intelligence report.\n\n"
            f"Competitor: {competitor.get('name', '')}\n"
            f"Website: {competitor.get('website', '')}\n"
            f"Notes: {competitor.get('notes', '')}\n"
            f"Their pricing: {competitor.get('pricing', 'unknown')}\n"
            f"Their target market: {competitor.get('target_market', 'unknown')}\n"
            f"Our product/context: {your_product or 'AI employee automation platform'}\n\n"
            f"Provide a SWOT analysis and strategic recommendations.\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"analysis": "2-3 sentence overview", '
            f'"strengths": ["s1", "s2"], '
            f'"weaknesses": ["w1", "w2"], '
            f'"opportunities": ["o1"], '
            f'"threats": ["t1"], '
            f'"recommendation": "strategic recommendation"}}'
        )
        try:
            result = _query_ai_for_agent("competitor-watch", prompt)
            content = result.get("content", result.get("text", ""))
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                # Store alert
                _add_alert(
                    competitor_id=competitor_id,
                    competitor_name=competitor.get("name", ""),
                    alert_type="analysis_complete",
                    message=parsed.get("recommendation", "New analysis available"),
                    severity="info",
                )
                updated = update_competitor(competitor_id, {
                    "analysis": parsed.get("analysis", ""),
                    "strengths": parsed.get("strengths", []),
                    "weaknesses": parsed.get("weaknesses", []),
                    "opportunities": parsed.get("opportunities", []),
                    "threats": parsed.get("threats", []),
                    "last_analyzed": _now_iso(),
                    "alert_count": competitor.get("alert_count", 0) + 1,
                })
                return updated
        except Exception:
            pass

    # Fallback
    analysis = f"Competitor '{competitor.get('name')}' is active in the market. Manual review recommended."
    _add_alert(
        competitor_id=competitor_id,
        competitor_name=competitor.get("name", ""),
        alert_type="analysis_complete",
        message=f"Analysis completed for {competitor.get('name')}",
        severity="info",
    )
    return update_competitor(competitor_id, {
        "analysis": analysis,
        "last_analyzed": _now_iso(),
        "alert_count": competitor.get("alert_count", 0) + 1,
    })


def _add_alert(
    competitor_id: str,
    competitor_name: str,
    alert_type: str,
    message: str,
    severity: str = "info",
) -> dict:
    """Store a new alert."""
    data = _load_competitors()
    alert = {
        "id": str(uuid.uuid4()),
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
        "dismissed": False,
        "created_at": _now_iso(),
    }
    if "alerts" not in data:
        data["alerts"] = []
    data["alerts"].append(alert)
    # Keep last 200 alerts
    data["alerts"] = data["alerts"][-200:]
    _save_competitors(data)
    return alert


def get_alerts(competitor_id: Optional[str] = None, dismissed: bool = False) -> list:
    """Return alerts, optionally filtered by competitor."""
    data = _load_competitors()
    alerts = data.get("alerts", [])
    if competitor_id:
        alerts = [a for a in alerts if a.get("competitor_id") == competitor_id]
    if not dismissed:
        alerts = [a for a in alerts if not a.get("dismissed", False)]
    return sorted(alerts, key=lambda x: x.get("created_at", ""), reverse=True)


def dismiss_alert(alert_id: str) -> bool:
    """Dismiss an alert."""
    data = _load_competitors()
    for i, alert in enumerate(data.get("alerts", [])):
        if alert["id"] == alert_id:
            data["alerts"][i]["dismissed"] = True
            _save_competitors(data)
            return True
    return False
