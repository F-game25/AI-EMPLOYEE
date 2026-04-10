"""Analytics & Insights Dashboard — cross-module BI, recommendations, trends."""
import json
import sys
import time
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Ensure runtime/ packages are importable from within features/
_RUNTIME_DIR = Path(__file__).parent.parent.parent.parent
for _p in [
    str(_RUNTIME_DIR),
    str(_RUNTIME_DIR / "core"),
    str(_RUNTIME_DIR / "actions"),
    str(_RUNTIME_DIR / "memory"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_HOME = Path.home() / ".ai-employee" / "state"


def _read(fname: str) -> dict:
    p = _HOME / fname
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


@router.get("/overview")
def analytics_overview():
    crm = _read("crm.json")
    email = _read("email_marketing.json")
    social = _read("social_media.json")
    finance = _read("finance.json")
    meetings = _read("meetings.json")

    leads = crm.get("leads", [])
    campaigns = email.get("campaigns", [])
    posts = social.get("posts", [])
    invoices = finance.get("invoices", [])
    meeting_list = meetings.get("meetings", [])

    total_sent = sum(c.get("sent", 0) for c in campaigns)
    total_opened = sum(c.get("opened", 0) for c in campaigns)

    return JSONResponse({
        "crm": {
            "total_leads": len(leads),
            "pipeline_value": sum(
                l.get("value", 0) for l in leads if l.get("stage") not in ("won", "lost")
            ),
            "won_deals": len([l for l in leads if l.get("stage") == "won"]),
            "conversion_rate": round(
                len([l for l in leads if l.get("stage") == "won"]) / max(len(leads), 1) * 100, 1
            ),
        },
        "email": {
            "campaigns": len(campaigns),
            "sent": total_sent,
            "open_rate": round(total_opened / max(total_sent, 1) * 100, 1),
        },
        "social": {
            "posts": len([p for p in posts if p.get("status") == "published"]),
            "total_likes": sum(p.get("likes", 0) for p in posts),
            "total_reach": sum(p.get("reach", 0) for p in posts),
        },
        "finance": {
            "revenue": sum(i.get("total", 0) for i in invoices if i.get("status") == "paid"),
            "pending": sum(
                i.get("total", 0) for i in invoices if i.get("status") in ("sent", "draft")
            ),
            "total_invoices": len(invoices),
        },
        "meetings": {
            "total": len(meeting_list),
            "analyzed": len([m for m in meeting_list if m.get("status") == "analyzed"]),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@router.get("/recommendations")
def get_recommendations():
    crm = _read("crm.json")
    email = _read("email_marketing.json")
    finance = _read("finance.json")

    leads = crm.get("leads", [])
    campaigns = email.get("campaigns", [])
    invoices = finance.get("invoices", [])

    recs = []

    if not leads:
        recs.append({
            "type": "crm", "priority": "high",
            "text": "Add your first leads to the CRM pipeline to start tracking deals.",
            "action": "Open CRM tab",
        })
    else:
        initial_leads = [l for l in leads if l.get("stage") == "lead"]
        if len(initial_leads) > 5:
            recs.append({
                "type": "crm", "priority": "medium",
                "text": f"{len(initial_leads)} leads in initial stage — start reaching out to qualify them.",
                "action": "Review Leads",
            })

    if not campaigns:
        recs.append({
            "type": "email", "priority": "high",
            "text": "Create your first email campaign to engage prospects.",
            "action": "Create Campaign",
        })

    overdue = [i for i in invoices if i.get("status") == "sent"]
    if overdue:
        recs.append({
            "type": "finance", "priority": "high",
            "text": f"{len(overdue)} unpaid invoice(s). Follow up with clients.",
            "action": "View Invoices",
        })

    if not recs:
        recs.append({
            "type": "general", "priority": "low",
            "text": "Business metrics look healthy. Keep up the momentum!",
            "action": None,
        })

    return JSONResponse({
        "recommendations": recs,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@router.get("/trends")
def get_trends():
    crm = _read("crm.json")
    leads = crm.get("leads", [])
    by_date: dict[str, int] = {}
    for lead in leads:
        date = lead.get("created_at", "")[:10]
        if date:
            by_date[date] = by_date.get(date, 0) + 1
    sorted_dates = sorted(by_date.items())[-30:]
    return JSONResponse({
        "lead_trend": [{"date": d, "count": c} for d, c in sorted_dates],
    })


# ── New endpoints — AI Employee system stats ──────────────────────────────────

@router.get("/daily-stats")
def get_daily_stats():
    """Return today's task execution stats + revenue estimate."""
    task_stats: dict = {"tasks_executed": 0, "success_rate": 0.0, "avg_score": 0.0}
    roi_summary: dict = {"events": 0, "total_tokens": 0, "total_revenue": 0.0, "roi": 0.0}
    best_strategies: list = []

    try:
        from core.task_engine import get_task_engine
        task_stats = get_task_engine().daily_stats()
    except Exception:
        pass

    try:
        from core.roi_tracker import get_roi_tracker
        roi_summary = get_roi_tracker().daily_summary()
    except Exception:
        pass

    try:
        from memory.strategy_store import get_strategy_store
        best_strategies = get_strategy_store().top_performers(limit=3)
    except Exception:
        pass

    return JSONResponse({
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "tasks": task_stats,
        "revenue": roi_summary,
        "best_strategies": best_strategies,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@router.get("/roi")
def get_roi(limit: int = Query(20, ge=1, le=200)):
    """Return recent ROI events and top-performing agents."""
    recent: list = []
    top_agents: list = []
    daily: dict = {}

    try:
        from core.roi_tracker import get_roi_tracker
        tracker = get_roi_tracker()
        recent = tracker.recent(limit=limit)
        top_agents = tracker.top_agents(limit=5)
        daily = tracker.daily_summary()
    except Exception:
        pass

    return JSONResponse({
        "daily_summary": daily,
        "top_agents": top_agents,
        "recent_events": recent,
    })
