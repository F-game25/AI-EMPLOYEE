"""Business Health Check — one-click audit with A-D grade and recommendations."""
import json
import time
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/health-check", tags=["health"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "health_checks.json"


def _read_state(fname: str) -> dict:
    p = _HOME / fname
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"reports": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.post("/run")
async def run_health_check():
    crm = _read_state("crm.json")
    email = _read_state("email_marketing.json")
    finance = _read_state("finance.json")
    support = _read_state("support.json")

    leads = crm.get("leads", [])
    invoices = finance.get("invoices", [])
    tickets = support.get("tickets", [])
    campaigns = email.get("campaigns", [])

    scores: dict[str, int] = {}
    issues = []
    strengths = []

    # CRM health
    if not leads:
        scores["crm"] = 0
        issues.append({
            "area": "CRM", "severity": "critical",
            "issue": "No leads in pipeline",
            "suggestion": "Start adding leads and contacts to your CRM",
        })
    else:
        won_leads = [l for l in leads if l.get("stage") == "won"]
        if not won_leads:
            scores["crm"] = 40
            issues.append({
                "area": "CRM", "severity": "warning",
                "issue": "No won deals yet",
                "suggestion": "Focus on moving qualified leads to proposal stage",
            })
        else:
            scores["crm"] = 80
            strengths.append("Active sales pipeline with won deals")

    # Finance health
    overdue = [i for i in invoices if i.get("status") == "sent"]
    if overdue:
        scores["finance"] = 50
        issues.append({
            "area": "Finance", "severity": "warning",
            "issue": f"{len(overdue)} unpaid invoice(s)",
            "suggestion": "Follow up with clients on outstanding invoices",
        })
    elif not invoices:
        scores["finance"] = 20
        issues.append({
            "area": "Finance", "severity": "info",
            "issue": "No invoices created",
            "suggestion": "Create your first invoice to start tracking revenue",
        })
    else:
        scores["finance"] = 90
        strengths.append("All invoices paid up to date")

    # Email health
    if not campaigns:
        scores["email"] = 0
        issues.append({
            "area": "Email Marketing", "severity": "warning",
            "issue": "No email campaigns",
            "suggestion": "Launch a cold outreach campaign to generate leads",
        })
    else:
        total_sent = sum(c.get("sent", 0) for c in campaigns)
        total_opened = sum(c.get("opened", 0) for c in campaigns)
        open_rate = total_opened / max(total_sent, 1) * 100
        scores["email"] = min(int(open_rate * 3), 100)
        if open_rate < 20:
            issues.append({
                "area": "Email Marketing", "severity": "warning",
                "issue": f"Low open rate: {open_rate:.1f}%",
                "suggestion": "A/B test subject lines and optimize send times",
            })
        else:
            strengths.append(f"Healthy email open rate of {open_rate:.1f}%")

    # Support health
    open_tickets = len([t for t in tickets if t.get("status") == "open"])
    if open_tickets > 10:
        scores["support"] = 30
        issues.append({
            "area": "Support", "severity": "warning",
            "issue": f"{open_tickets} open tickets",
            "suggestion": "Clear backlog — aim for 24h response time",
        })
    else:
        scores["support"] = 90

    overall = int(sum(scores.values()) / max(len(scores), 1))
    grade = "A" if overall >= 80 else "B" if overall >= 60 else "C" if overall >= 40 else "D"

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "overall_score": overall,
        "grade": grade,
        "scores": scores,
        "issues": issues,
        "strengths": strengths,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data = _load()
    data["reports"].append(report)
    data["reports"] = data["reports"][-12:]
    _save(data)
    return JSONResponse(report)


@router.get("/latest")
def get_latest():
    data = _load()
    if data["reports"]:
        return JSONResponse(data["reports"][-1])
    return JSONResponse({"message": "No health check run yet. Click Run to start."})


@router.get("/history")
def get_history():
    return JSONResponse(_load()["reports"])
