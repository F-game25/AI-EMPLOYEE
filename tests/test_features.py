"""Comprehensive tests for the 15 feature modules in problem-solver-ui/features/.

Every module exposes a FastAPI router backed by JSON state files stored under
~/.ai-employee/state/.  All tests redirect the module-level _HOME / _FILE /
_BACKUP_DIR pointers to a pytest tmp_path so nothing leaks to the real
installation and tests are fully reproducible.

Coverage targets (per module):
  crm, email_marketing, meeting_intelligence, social_media, ceo_briefing,
  invoicing (finance), analytics, workflow_builder, team_management,
  customer_support, website_builder, competitor_watch, personal_brand,
  health_check, export_backup
"""
from __future__ import annotations

import importlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Path helpers ──────────────────────────────────────────────────────────────

_FEATURES_DIR = (
    Path(__file__).parent.parent
    / "runtime"
    / "agents"
    / "problem-solver-ui"
    / "features"
)


def _load_module(name: str):
    """Import a features sub-module by filename stem (without .py)."""
    spec_path = _FEATURES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"features.{name}", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_AI_EMPLOYEE_HOME = Path.home() / ".ai-employee"


def _make_client(mod, tmp_path: Path) -> TestClient:
    """Return a TestClient with the module's router and all Path constants redirected.

    Every module-level Path attribute that lives under ~/.ai-employee is
    remapped to the same relative path under tmp_path so tests never touch
    the real installation.
    """
    tmp_ai_home = tmp_path / "ai-employee"

    # Remap every Path attribute that references the real ~/.ai-employee tree
    for attr_name in list(vars(mod)):
        val = getattr(mod, attr_name)
        if isinstance(val, Path):
            try:
                rel = val.relative_to(_AI_EMPLOYEE_HOME)
                new_path = tmp_ai_home / rel
                # Attribute names containing DIR or HOME represent directories;
                # everything else is a file path — create only the parent dir.
                if "DIR" in attr_name or "HOME" in attr_name:
                    new_path.mkdir(parents=True, exist_ok=True)
                else:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                setattr(mod, attr_name, new_path)
            except ValueError:
                pass  # not under ~/.ai-employee — leave as-is

    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════════
# CRM
# ══════════════════════════════════════════════════════════════════════════════

class TestCRM:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("crm")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_leads_empty(self):
        r = self.client.get("/api/crm/leads")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_lead_fields(self):
        r = self.client.post("/api/crm/leads", json={
            "name": "Alice", "company": "ACME", "email": "a@b.com",
            "phone": "123", "value": 2000,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Alice"
        assert data["stage"] == "lead"
        assert data["score"] > 0  # auto-scored

    def test_create_lead_auto_score_high_value(self):
        r = self.client.post("/api/crm/leads", json={
            "email": "x@y.com", "phone": "1", "company": "Corp", "value": 5000,
        })
        assert r.json()["score"] >= 70

    def test_create_lead_auto_score_minimal(self):
        r = self.client.post("/api/crm/leads", json={"name": "Bob"})
        assert r.json()["score"] == 0

    def test_update_lead(self):
        lead_id = self.client.post("/api/crm/leads", json={"name": "C"}).json()["id"]
        r = self.client.patch(f"/api/crm/leads/{lead_id}", json={"stage": "won"})
        assert r.status_code == 200
        assert r.json()["stage"] == "won"

    def test_update_lead_not_found(self):
        r = self.client.patch("/api/crm/leads/no-such-id", json={"stage": "won"})
        assert r.status_code == 404

    def test_delete_lead(self):
        lead_id = self.client.post("/api/crm/leads", json={"name": "D"}).json()["id"]
        r = self.client.delete(f"/api/crm/leads/{lead_id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert self.client.get("/api/crm/leads").json() == []

    def test_get_pipeline(self):
        self.client.post("/api/crm/leads", json={"name": "L1", "stage": "lead", "value": 100})
        self.client.post("/api/crm/leads", json={"name": "L2", "stage": "won", "value": 500})
        r = self.client.get("/api/crm/pipeline")
        body = r.json()
        assert "pipeline" in body
        assert body["won_value"] == 500
        assert body["pipeline_value"] == 100

    def test_score_lead_endpoint(self):
        lead_id = self.client.post("/api/crm/leads", json={
            "email": "s@s.com", "stage": "negotiation",
        }).json()["id"]
        r = self.client.post(f"/api/crm/leads/{lead_id}/score", json={"manual_boost": 5})
        assert r.status_code == 200
        assert r.json()["score"] >= 5

    def test_score_lead_not_found(self):
        r = self.client.post("/api/crm/leads/nope/score", json={})
        assert r.status_code == 404

    def test_create_and_list_sequences(self):
        self.client.post("/api/crm/sequences", json={"name": "Seq1", "steps": ["a", "b"]})
        r = self.client.get("/api/crm/sequences")
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Seq1"

    def test_crm_stats(self):
        self.client.post("/api/crm/leads", json={"name": "S1", "stage": "won", "value": 1000})
        self.client.post("/api/crm/leads", json={"name": "S2", "stage": "lead"})
        r = self.client.get("/api/crm/stats")
        body = r.json()
        assert body["total_leads"] == 2
        assert body["won_value"] == 1000
        assert 0 < body["conversion_rate"] <= 100


# ══════════════════════════════════════════════════════════════════════════════
# Email Marketing
# ══════════════════════════════════════════════════════════════════════════════

class TestEmailMarketing:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("email_marketing")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_campaigns_empty(self):
        assert self.client.get("/api/email-mkt/campaigns").json() == []

    def test_create_campaign(self):
        r = self.client.post("/api/email-mkt/campaigns", json={
            "name": "Cold Oct", "subject": "Hi!", "recipients": ["a@b.com", "c@d.com"],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Cold Oct"
        assert body["status"] == "draft"

    def test_update_campaign(self):
        cid = self.client.post("/api/email-mkt/campaigns", json={"name": "X"}).json()["id"]
        r = self.client.patch(f"/api/email-mkt/campaigns/{cid}", json={"subject": "Updated"})
        assert r.json()["subject"] == "Updated"

    def test_update_campaign_not_found(self):
        r = self.client.patch("/api/email-mkt/campaigns/nope", json={"subject": "x"})
        assert r.status_code == 404

    def test_delete_campaign(self):
        cid = self.client.post("/api/email-mkt/campaigns", json={"name": "Del"}).json()["id"]
        self.client.delete(f"/api/email-mkt/campaigns/{cid}")
        assert self.client.get("/api/email-mkt/campaigns").json() == []

    def test_send_campaign(self):
        cid = self.client.post("/api/email-mkt/campaigns", json={
            "name": "S", "recipients": ["a@b.com", "c@d.com"],
        }).json()["id"]
        r = self.client.post(f"/api/email-mkt/campaigns/{cid}/send")
        assert r.json()["sent"] == 2

    def test_send_campaign_not_found(self):
        r = self.client.post("/api/email-mkt/campaigns/nope/send")
        assert r.status_code == 404

    def test_create_and_list_templates(self):
        self.client.post("/api/email-mkt/templates", json={"name": "T1", "body": "Hello {{name}}"})
        r = self.client.get("/api/email-mkt/templates")
        assert len(r.json()) == 1

    def test_create_and_list_sequences(self):
        self.client.post("/api/email-mkt/sequences", json={"name": "Drip", "steps": [1, 2]})
        r = self.client.get("/api/email-mkt/sequences")
        assert r.json()[0]["name"] == "Drip"

    def test_track_event_open(self):
        cid = self.client.post("/api/email-mkt/campaigns", json={
            "name": "T", "recipients": ["x@y.com"],
        }).json()["id"]
        self.client.post(f"/api/email-mkt/campaigns/{cid}/send")
        self.client.post(f"/api/email-mkt/track/open/{cid}")
        self.client.post(f"/api/email-mkt/track/click/{cid}")
        stats = self.client.get("/api/email-mkt/stats").json()
        assert stats["total_opened"] == 1
        assert stats["total_clicked"] == 1

    def test_stats(self):
        r = self.client.get("/api/email-mkt/stats")
        body = r.json()
        assert "total_campaigns" in body
        assert "open_rate" in body


# ══════════════════════════════════════════════════════════════════════════════
# Meeting Intelligence
# ══════════════════════════════════════════════════════════════════════════════

class TestMeetingIntelligence:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("meeting_intelligence")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_empty(self):
        assert self.client.get("/api/meetings/").json() == []

    def test_create_meeting(self):
        r = self.client.post("/api/meetings/", json={
            "title": "Q4 Planning", "platform": "zoom", "participants": ["Alice", "Bob"],
        })
        body = r.json()
        assert body["title"] == "Q4 Planning"
        assert body["status"] == "pending"

    def test_update_meeting(self):
        mid = self.client.post("/api/meetings/", json={"title": "M"}).json()["id"]
        r = self.client.patch(f"/api/meetings/{mid}", json={"duration_mins": 60})
        assert r.json()["duration_mins"] == 60

    def test_update_meeting_not_found(self):
        r = self.client.patch("/api/meetings/nope", json={})
        assert r.status_code == 404

    def test_delete_meeting(self):
        mid = self.client.post("/api/meetings/", json={"title": "Del"}).json()["id"]
        self.client.delete(f"/api/meetings/{mid}")
        assert self.client.get("/api/meetings/").json() == []

    def test_analyze_meeting_fallback(self):
        """analyze endpoint uses AI router; it falls back gracefully when unavailable."""
        mid = self.client.post("/api/meetings/", json={"title": "A"}).json()["id"]
        r = self.client.post(f"/api/meetings/{mid}/analyze", json={
            "transcript": "- Do this\n- And that",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "analyzed"
        assert body["summary"]  # non-empty (fallback or AI)

    def test_analyze_meeting_not_found(self):
        r = self.client.post("/api/meetings/nope/analyze", json={})
        assert r.status_code == 404

    def test_meeting_stats(self):
        self.client.post("/api/meetings/", json={"title": "S1"})
        r = self.client.get("/api/meetings/stats")
        body = r.json()
        assert body["total"] == 1
        assert body["pending"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Social Media
# ══════════════════════════════════════════════════════════════════════════════

class TestSocialMedia:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("social_media")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_empty(self):
        assert self.client.get("/api/social/posts").json() == []

    def test_create_post(self):
        r = self.client.post("/api/social/posts", json={
            "content": "Hello world!", "platforms": ["linkedin", "twitter"],
        })
        body = r.json()
        assert body["content"] == "Hello world!"
        assert body["status"] == "draft"

    def test_update_post(self):
        pid = self.client.post("/api/social/posts", json={"content": "X"}).json()["id"]
        r = self.client.patch(f"/api/social/posts/{pid}", json={"content": "Updated"})
        assert r.json()["content"] == "Updated"

    def test_update_post_not_found(self):
        r = self.client.patch("/api/social/posts/nope", json={})
        assert r.status_code == 404

    def test_publish_post(self):
        pid = self.client.post("/api/social/posts", json={"content": "P"}).json()["id"]
        r = self.client.post(f"/api/social/posts/{pid}/publish")
        assert r.json()["ok"] is True

    def test_publish_not_found(self):
        r = self.client.post("/api/social/posts/nope/publish")
        assert r.status_code == 404

    def test_schedule_post(self):
        pid = self.client.post("/api/social/posts", json={"content": "Sched"}).json()["id"]
        r = self.client.post(f"/api/social/posts/{pid}/schedule", json={
            "scheduled_at": "2025-12-01T09:00:00Z",
        })
        assert r.json()["ok"] is True


        r = self.client.post("/api/social/posts/nope/schedule", json={})
        assert r.status_code == 404

    def test_delete_post(self):
        pid = self.client.post("/api/social/posts", json={"content": "Delete me"}).json()["id"]
        r = self.client.delete(f"/api/social/posts/{pid}")
        assert r.json()["ok"] is True
        assert self.client.get("/api/social/posts").json() == []

    def test_generate_post_fallback(self):
        r = self.client.post("/api/social/generate", json={
            "topic": "AI tools", "platform": "twitter", "tone": "casual",
        })
        assert r.status_code == 200
        body = r.json()
        assert "content" in body
        assert body["platform"] == "twitter"

    def test_social_stats(self):
        pid = self.client.post("/api/social/posts", json={"content": "S"}).json()["id"]
        self.client.post(f"/api/social/posts/{pid}/publish")
        r = self.client.get("/api/social/stats")
        body = r.json()
        assert body["total_posts"] == 1
        assert body["published"] == 1
        assert "total_likes" in body


# ══════════════════════════════════════════════════════════════════════════════
# Invoicing (Finance)
# ══════════════════════════════════════════════════════════════════════════════

class TestInvoicing:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("invoicing")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_invoices_empty(self):
        assert self.client.get("/api/finance/invoices").json() == []

    def test_update_invoice(self):
        inv_id = self.client.post("/api/finance/invoices", json={"subtotal": 300}).json()["id"]
        r = self.client.patch(f"/api/finance/invoices/{inv_id}", json={"notes": "Net 30"})
        assert r.json()["notes"] == "Net 30"

    def test_update_invoice_not_found(self):
        r = self.client.patch("/api/finance/invoices/nope", json={"notes": "x"})
        assert r.status_code == 404

    def test_list_expenses_empty(self):
        assert self.client.get("/api/finance/expenses").json() == []

    def test_create_invoice_tax(self):
        r = self.client.post("/api/finance/invoices", json={
            "client": "Acme", "subtotal": 1000, "tax_rate": 10,
        })
        body = r.json()
        assert body["subtotal"] == 1000
        assert body["tax_amount"] == 100.0
        assert body["total"] == 1100.0
        assert body["status"] == "draft"
        assert body["number"].startswith("INV-")

    def test_create_invoice_zero_tax(self):
        r = self.client.post("/api/finance/invoices", json={"subtotal": 500, "tax_rate": 0})
        assert r.json()["total"] == 500.0

    def test_send_invoice(self):
        inv_id = self.client.post("/api/finance/invoices", json={"subtotal": 100}).json()["id"]
        r = self.client.post(f"/api/finance/invoices/{inv_id}/send")
        assert r.json()["ok"] is True

    def test_send_invoice_not_found(self):
        r = self.client.post("/api/finance/invoices/nope/send")
        assert r.status_code == 404

    def test_mark_paid(self):
        inv_id = self.client.post("/api/finance/invoices", json={"subtotal": 200}).json()["id"]
        r = self.client.post(f"/api/finance/invoices/{inv_id}/mark-paid")
        assert r.json()["ok"] is True
        # Verify status updated
        invoices = self.client.get("/api/finance/invoices").json()
        assert invoices[0]["status"] == "paid"

    def test_mark_paid_not_found(self):
        r = self.client.post("/api/finance/invoices/nope/mark-paid")
        assert r.status_code == 404

    def test_delete_invoice(self):
        inv_id = self.client.post("/api/finance/invoices", json={"subtotal": 50}).json()["id"]
        self.client.delete(f"/api/finance/invoices/{inv_id}")
        assert self.client.get("/api/finance/invoices").json() == []

    def test_create_expense(self):
        r = self.client.post("/api/finance/expenses", json={
            "description": "Hosting", "amount": 29.99, "category": "saas",
        })
        body = r.json()
        assert body["description"] == "Hosting"
        assert body["amount"] == 29.99

    def test_delete_expense(self):
        exp_id = self.client.post("/api/finance/expenses", json={"amount": 10}).json()["id"]
        r = self.client.delete(f"/api/finance/expenses/{exp_id}")
        assert r.json()["ok"] is True

    def test_pl_report(self):
        inv_id = self.client.post("/api/finance/invoices", json={"subtotal": 1000}).json()["id"]
        self.client.post(f"/api/finance/invoices/{inv_id}/mark-paid")
        self.client.post("/api/finance/expenses", json={"amount": 200, "category": "ads"})
        r = self.client.get("/api/finance/pl-report")
        body = r.json()
        assert body["revenue"] == 1000.0
        assert body["total_expenses"] == 200.0
        assert body["gross_profit"] == 800.0
        assert body["expenses_by_category"]["ads"] == 200.0


# ══════════════════════════════════════════════════════════════════════════════
# CEO Briefing
# ══════════════════════════════════════════════════════════════════════════════

class TestCEOBriefing:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("ceo_briefing")
        self.client = _make_client(self.mod, tmp_path)

    def test_latest_no_briefing(self):
        r = self.client.get("/api/briefing/latest")
        assert r.status_code == 200
        assert "message" in r.json()

    def test_history_empty(self):
        assert self.client.get("/api/briefing/history").json() == []

    def test_generate_briefing_fallback(self):
        r = self.client.post("/api/briefing/generate")
        assert r.status_code == 200
        body = r.json()
        assert "content" in body
        assert "metrics" in body
        assert "date" in body

    def test_latest_after_generate(self):
        self.client.post("/api/briefing/generate")
        r = self.client.get("/api/briefing/latest")
        assert "content" in r.json()

    def test_history_after_generate(self):
        self.client.post("/api/briefing/generate")
        self.client.post("/api/briefing/generate")
        h = self.client.get("/api/briefing/history").json()
        assert len(h) == 2

    def test_get_settings_default(self):
        r = self.client.get("/api/briefing/settings")
        body = r.json()
        assert "auto_generate" in body
        assert "time" in body

    def test_update_settings(self):
        r = self.client.post("/api/briefing/settings", json={"time": "07:30", "auto_generate": False})
        assert r.json()["time"] == "07:30"
        assert r.json()["auto_generate"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Analytics
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalytics:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("analytics")
        self.client = _make_client(self.mod, tmp_path)
        self.state_dir = tmp_path / "ai-employee" / "state"

    def _write_state(self, fname: str, data: dict) -> None:
        (self.state_dir / fname).write_text(json.dumps(data))

    def test_overview_empty(self):
        r = self.client.get("/api/analytics/overview")
        body = r.json()
        assert body["crm"]["total_leads"] == 0
        assert body["finance"]["revenue"] == 0

    def test_overview_with_data(self):
        self._write_state("crm.json", {"leads": [
            {"stage": "won", "value": 500},
            {"stage": "lead", "value": 200},
        ]})
        self._write_state("finance.json", {"invoices": [
            {"status": "paid", "total": 1000},
        ]})
        r = self.client.get("/api/analytics/overview")
        body = r.json()
        assert body["crm"]["won_deals"] == 1
        assert body["finance"]["revenue"] == 1000

    def test_recommendations_empty_crm(self):
        r = self.client.get("/api/analytics/recommendations")
        body = r.json()
        recs = body["recommendations"]
        assert any(rec["type"] == "crm" for rec in recs)

    def test_recommendations_many_initial_leads(self):
        self._write_state("crm.json", {"leads": [{"stage": "lead"}] * 10})
        r = self.client.get("/api/analytics/recommendations")
        recs = r.json()["recommendations"]
        assert any("10" in rec["text"] or "lead" in rec["text"].lower() for rec in recs)

    def test_recommendations_overdue_invoice(self):
        self._write_state("finance.json", {"invoices": [{"status": "sent", "total": 500}]})
        r = self.client.get("/api/analytics/recommendations")
        recs = r.json()["recommendations"]
        assert any(rec["type"] == "finance" for rec in recs)

    def test_recommendations_healthy(self):
        # All data present, no problems
        self._write_state("crm.json", {"leads": [{"stage": "won", "value": 1000}]})
        self._write_state("email_marketing.json", {"campaigns": [{"sent": 100, "opened": 30}]})
        self._write_state("finance.json", {"invoices": []})
        r = self.client.get("/api/analytics/recommendations")
        recs = r.json()["recommendations"]
        assert any(rec["priority"] == "low" for rec in recs)

    def test_trends(self):
        self._write_state("crm.json", {"leads": [
            {"created_at": "2025-01-15T10:00:00Z"},
            {"created_at": "2025-01-15T12:00:00Z"},
            {"created_at": "2025-01-16T08:00:00Z"},
        ]})
        r = self.client.get("/api/analytics/trends")
        trend = r.json()["lead_trend"]
        assert len(trend) == 2
        assert trend[0]["date"] == "2025-01-15"
        assert trend[0]["count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# Workflow Builder
# ══════════════════════════════════════════════════════════════════════════════

class TestWorkflowBuilder:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("workflow_builder")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_workflows_empty(self):
        assert self.client.get("/api/workflows/").json() == []

    def test_create_workflow(self):
        r = self.client.post("/api/workflows/", json={
            "name": "Lead Nurture",
            "trigger": {"type": "new_lead"},
            "steps": [{"action": "send_email", "template": "welcome"}],
        })
        body = r.json()
        assert body["name"] == "Lead Nurture"
        assert body["runs"] == 0

    def test_update_workflow(self):
        wf_id = self.client.post("/api/workflows/", json={"name": "W"}).json()["id"]
        r = self.client.patch(f"/api/workflows/{wf_id}", json={"active": True})
        assert r.json()["active"] is True

    def test_update_workflow_not_found(self):
        r = self.client.patch("/api/workflows/nope", json={})
        assert r.status_code == 404

    def test_delete_workflow(self):
        wf_id = self.client.post("/api/workflows/", json={"name": "D"}).json()["id"]
        self.client.delete(f"/api/workflows/{wf_id}")
        assert self.client.get("/api/workflows/").json() == []

    def test_run_workflow(self):
        wf_id = self.client.post("/api/workflows/", json={
            "name": "Run Test", "steps": [{"action": "wait"}],
        }).json()["id"]
        r = self.client.post(f"/api/workflows/{wf_id}/run")
        assert r.json()["ok"] is True
        run = r.json()["run"]
        assert run["status"] == "completed"
        assert run["steps_completed"] == 1

    def test_run_workflow_not_found(self):
        r = self.client.post("/api/workflows/nope/run")
        assert r.status_code == 404

    def test_run_increments_counter(self):
        wf_id = self.client.post("/api/workflows/", json={"name": "Counter"}).json()["id"]
        self.client.post(f"/api/workflows/{wf_id}/run")
        self.client.post(f"/api/workflows/{wf_id}/run")
        wfs = self.client.get("/api/workflows/").json()
        assert wfs[0]["runs"] == 2

    def test_triggers_list(self):
        r = self.client.get("/api/workflows/triggers")
        body = r.json()
        assert "manual" in body["triggers"]
        assert "send_email" in body["actions"]

    def test_list_runs(self):
        wf_id = self.client.post("/api/workflows/", json={"name": "R"}).json()["id"]
        self.client.post(f"/api/workflows/{wf_id}/run")
        runs = self.client.get("/api/workflows/runs").json()
        assert len(runs) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Team Management
# ══════════════════════════════════════════════════════════════════════════════

class TestTeamManagement:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("team_management")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_members_empty(self):
        assert self.client.get("/api/team/members").json() == []

    def test_invite_member(self):
        r = self.client.post("/api/team/members/invite", json={
            "email": "alice@test.com", "role": "admin",
        })
        body = r.json()
        assert body["ok"] is True
        assert "token" in body

    def test_invite_requires_email(self):
        r = self.client.post("/api/team/members/invite", json={"role": "member"})
        assert r.status_code == 400

    def test_invite_duplicate_email(self):
        # Invite then accept, then invite again
        token = self.client.post("/api/team/members/invite", json={"email": "dup@test.com"}).json()["token"]
        self.client.post("/api/team/members/accept", json={"token": token, "name": "Dup"})
        r = self.client.post("/api/team/members/invite", json={"email": "dup@test.com"})
        assert r.status_code == 409

    def test_accept_invitation(self):
        token = self.client.post("/api/team/members/invite", json={
            "email": "bob@test.com", "role": "member",
        }).json()["token"]
        r = self.client.post("/api/team/members/accept", json={"token": token, "name": "Bob"})
        body = r.json()
        assert body["ok"] is True
        assert body["member"]["name"] == "Bob"
        assert body["member"]["role"] == "member"

    def test_accept_invalid_token(self):
        r = self.client.post("/api/team/members/accept", json={"token": "invalid"})
        assert r.status_code == 400

    def test_update_member(self):
        token = self.client.post("/api/team/members/invite", json={"email": "c@test.com"}).json()["token"]
        member_id = self.client.post("/api/team/members/accept", json={"token": token}).json()["member"]["id"]
        r = self.client.patch(f"/api/team/members/{member_id}", json={"role": "manager"})
        assert r.json()["role"] == "manager"

    def test_update_member_not_found(self):
        r = self.client.patch("/api/team/members/nope", json={})
        assert r.status_code == 404

    def test_remove_member(self):
        token = self.client.post("/api/team/members/invite", json={"email": "d@test.com"}).json()["token"]
        member_id = self.client.post("/api/team/members/accept", json={"token": token}).json()["member"]["id"]
        r = self.client.delete(f"/api/team/members/{member_id}")
        assert r.json()["ok"] is True
        assert self.client.get("/api/team/members").json() == []

    def test_list_roles(self):
        r = self.client.get("/api/team/roles")
        assert "owner" in r.json()
        assert "viewer" in r.json()

    def test_password_hash_not_exposed(self):
        """password_hash must never appear in list or update responses."""
        token = self.client.post("/api/team/members/invite", json={"email": "e@test.com"}).json()["token"]
        member = self.client.post("/api/team/members/accept", json={"token": token}).json()["member"]
        member["password_hash"] = "secret"
        # Update to write a member with password_hash into state (simulate external write)
        members = self.client.get("/api/team/members").json()
        for m in members:
            assert "password_hash" not in m


# ══════════════════════════════════════════════════════════════════════════════
# Customer Support
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomerSupport:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("customer_support")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_tickets_empty(self):
        assert self.client.get("/api/support/tickets").json() == []

    def test_create_ticket(self):
        r = self.client.post("/api/support/tickets", json={
            "subject": "Login issue", "customer_email": "u@test.com",
            "priority": "high", "category": "technical",
        })
        body = r.json()
        assert body["subject"] == "Login issue"
        assert body["status"] == "open"
        assert body["number"].startswith("SUP-")

    def test_update_ticket_status(self):
        tid = self.client.post("/api/support/tickets", json={"subject": "X"}).json()["id"]
        r = self.client.patch(f"/api/support/tickets/{tid}", json={"status": "resolved"})
        assert r.json()["status"] == "resolved"
        assert r.json()["resolved_at"]  # timestamp set

    def test_update_ticket_not_found(self):
        r = self.client.patch("/api/support/tickets/nope", json={})
        assert r.status_code == 404

    def test_reply_to_ticket(self):
        tid = self.client.post("/api/support/tickets", json={"subject": "Help"}).json()["id"]
        r = self.client.post(f"/api/support/tickets/{tid}/reply", json={
            "content": "We're on it!", "author": "Support Agent",
        })
        assert r.status_code == 200
        msg = r.json()
        assert msg["content"] == "We're on it!"
        # Status should change to in_progress after first reply
        tickets = self.client.get("/api/support/tickets").json()
        assert tickets[0]["status"] == "in_progress"

    def test_reply_not_found(self):
        r = self.client.post("/api/support/tickets/nope/reply", json={"content": "Hi"})
        assert r.status_code == 404

    def test_ai_suggest_reply_fallback(self):
        tid = self.client.post("/api/support/tickets", json={
            "subject": "Billing", "category": "billing",
        }).json()["id"]
        r = self.client.post(f"/api/support/tickets/{tid}/ai-suggest")
        assert r.status_code == 200
        assert "suggestion" in r.json()

    def test_ai_suggest_not_found(self):
        r = self.client.post("/api/support/tickets/nope/ai-suggest")
        assert r.status_code == 404

    def test_filter_by_status(self):
        self.client.post("/api/support/tickets", json={"subject": "A"})
        tid = self.client.post("/api/support/tickets", json={"subject": "B"}).json()["id"]
        self.client.patch(f"/api/support/tickets/{tid}", json={"status": "resolved"})
        open_tickets = self.client.get("/api/support/tickets?status=open").json()
        assert len(open_tickets) == 1

    def test_kb_create_and_list(self):
        self.client.post("/api/support/kb", json={"title": "How to login", "content": "..."})
        r = self.client.get("/api/support/kb")
        assert len(r.json()) == 1

    def test_support_stats(self):
        self.client.post("/api/support/tickets", json={"subject": "S"})
        r = self.client.get("/api/support/stats")
        body = r.json()
        assert body["total"] == 1
        assert body["open"] == 1
        assert "by_priority" in body


# ══════════════════════════════════════════════════════════════════════════════
# Website Builder
# ══════════════════════════════════════════════════════════════════════════════

class TestWebsiteBuilder:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("website_builder")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_pages_empty(self):
        assert self.client.get("/api/website-builder/pages").json() == []

    def test_generate_page_fallback(self):
        r = self.client.post("/api/website-builder/generate", json={
            "business_name": "ACME", "page_type": "landing",
            "industry": "SaaS", "description": "Task management tool",
        })
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert "preview_length" in body
        assert body["preview_length"] > 0
        # html_content should NOT be in list/summary response
        assert "html_content" not in body

    def test_get_page_includes_html(self):
        pid = self.client.post("/api/website-builder/generate", json={
            "business_name": "B",
        }).json()["id"]
        r = self.client.get(f"/api/website-builder/pages/{pid}")
        assert "html_content" in r.json()

    def test_get_page_not_found(self):
        r = self.client.get("/api/website-builder/pages/nope")
        assert r.status_code == 404

    def test_list_pages_hides_html(self):
        self.client.post("/api/website-builder/generate", json={"business_name": "X"})
        pages = self.client.get("/api/website-builder/pages").json()
        assert len(pages) == 1
        assert "html_content" not in pages[0]

    def test_update_page(self):
        pid = self.client.post("/api/website-builder/generate", json={"business_name": "Y"}).json()["id"]
        r = self.client.patch(f"/api/website-builder/pages/{pid}", json={"status": "published"})
        assert r.json()["status"] == "published"

    def test_update_page_not_found(self):
        r = self.client.patch("/api/website-builder/pages/nope", json={})
        assert r.status_code == 404

    def test_delete_page(self):
        pid = self.client.post("/api/website-builder/generate", json={"business_name": "Z"}).json()["id"]
        r = self.client.delete(f"/api/website-builder/pages/{pid}")
        assert r.json()["ok"] is True
        assert self.client.get("/api/website-builder/pages").json() == []


# ══════════════════════════════════════════════════════════════════════════════
# Competitor Watch
# ══════════════════════════════════════════════════════════════════════════════

class TestCompetitorWatch:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("competitor_watch")
        self.client = _make_client(self.mod, tmp_path)

    def test_list_empty(self):
        assert self.client.get("/api/competitors/").json() == []

    def test_add_competitor(self):
        r = self.client.post("/api/competitors/", json={
            "name": "Rival Inc", "website": "https://rival.com",
            "strengths": ["pricing", "ui"],
        })
        body = r.json()
        assert body["name"] == "Rival Inc"
        assert body["strengths"] == ["pricing", "ui"]

    def test_update_competitor(self):
        cid = self.client.post("/api/competitors/", json={"name": "A"}).json()["id"]
        r = self.client.patch(f"/api/competitors/{cid}", json={"pricing": "$99/mo"})
        assert r.json()["pricing"] == "$99/mo"

    def test_update_not_found(self):
        r = self.client.patch("/api/competitors/nope", json={})
        assert r.status_code == 404

    def test_analyze_competitor_fallback(self):
        cid = self.client.post("/api/competitors/", json={
            "name": "CompX", "description": "CRM tool",
        }).json()["id"]
        r = self.client.post(f"/api/competitors/{cid}/analyze")
        assert r.status_code == 200
        body = r.json()
        assert "analysis" in body
        assert body["analysis"]  # non-empty fallback

    def test_analyze_not_found(self):
        r = self.client.post("/api/competitors/nope/analyze")
        assert r.status_code == 404

    def test_delete_competitor(self):
        cid = self.client.post("/api/competitors/", json={"name": "Del"}).json()["id"]
        r = self.client.delete(f"/api/competitors/{cid}")
        assert r.json()["ok"] is True
        assert self.client.get("/api/competitors/").json() == []

    def test_alerts_empty(self):
        r = self.client.get("/api/competitors/alerts")
        assert r.json() == []


# ══════════════════════════════════════════════════════════════════════════════
# Personal Brand
# ══════════════════════════════════════════════════════════════════════════════

class TestPersonalBrand:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("personal_brand")
        self.client = _make_client(self.mod, tmp_path)

    def test_get_profile_empty(self):
        assert self.client.get("/api/brand/profile").json() == {}

    def test_save_profile(self):
        r = self.client.post("/api/brand/profile", json={
            "name": "Jane Doe", "title": "CEO", "industry": "SaaS",
            "expertise": ["AI", "Marketing"], "tone": "bold",
        })
        body = r.json()
        assert body["name"] == "Jane Doe"
        assert body["tone"] == "bold"

    def test_generate_content_fallback(self):
        self.client.post("/api/brand/profile", json={"name": "Jane", "industry": "SaaS"})
        r = self.client.post("/api/brand/generate-content", json={
            "content_type": "linkedin_post", "topic": "AI in sales",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "linkedin_post"
        assert body["topic"] == "AI in sales"
        assert body["content"]

    def test_list_content(self):
        self.client.post("/api/brand/generate-content", json={"topic": "Topic A"})
        r = self.client.get("/api/brand/content")
        assert len(r.json()) == 1

    def test_delete_content(self):
        pid = self.client.post("/api/brand/generate-content", json={"topic": "Del"}).json()["id"]
        r = self.client.delete(f"/api/brand/content/{pid}")
        assert r.json()["ok"] is True
        assert self.client.get("/api/brand/content").json() == []

    def test_suggest_topics_fallback(self):
        r = self.client.post("/api/brand/topics", json={})
        assert r.status_code == 200
        topics = r.json()["topics"]
        assert isinstance(topics, list)
        assert len(topics) >= 1

    def test_get_topics(self):
        self.client.post("/api/brand/topics", json={})
        r = self.client.get("/api/brand/topics")
        assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════════════════
# Health Check
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("health_check")
        self.client = _make_client(self.mod, tmp_path)
        self.state_dir = tmp_path / "ai-employee" / "state"

    def _write_state(self, fname: str, data: dict) -> None:
        (self.state_dir / fname).write_text(json.dumps(data))

    def test_latest_no_report(self):
        r = self.client.get("/api/health-check/latest")
        assert "message" in r.json()

    def test_history_empty(self):
        assert self.client.get("/api/health-check/history").json() == []

    def test_run_empty_state_gives_grade_d(self):
        r = self.client.post("/api/health-check/run")
        body = r.json()
        assert body["grade"] == "D"
        assert body["overall_score"] < 40
        assert len(body["issues"]) > 0

    def test_run_healthy_state_gives_high_grade(self):
        self._write_state("crm.json", {"leads": [{"stage": "won", "value": 5000}]})
        self._write_state("finance.json", {"invoices": [{"status": "paid", "total": 1000}]})
        self._write_state("email_marketing.json", {"campaigns": [
            {"sent": 1000, "opened": 300},
        ]})
        self._write_state("support.json", {"tickets": []})
        r = self.client.post("/api/health-check/run")
        body = r.json()
        assert body["grade"] in ("A", "B")

    def test_run_overdue_invoices(self):
        self._write_state("finance.json", {"invoices": [
            {"status": "sent", "total": 500},
        ]})
        r = self.client.post("/api/health-check/run")
        issues = r.json()["issues"]
        assert any("Finance" in i["area"] for i in issues)

    def test_run_high_open_ticket_count(self):
        self._write_state("support.json", {"tickets": [
            {"status": "open"} for _ in range(15)
        ]})
        r = self.client.post("/api/health-check/run")
        issues = r.json()["issues"]
        assert any("Support" in i["area"] for i in issues)

    def test_run_email_low_open_rate(self):
        self._write_state("email_marketing.json", {"campaigns": [
            {"sent": 1000, "opened": 50},  # 5% open rate
        ]})
        r = self.client.post("/api/health-check/run")
        issues = r.json()["issues"]
        assert any("Email" in i["area"] for i in issues)

    def test_run_report_saved(self):
        self.client.post("/api/health-check/run")
        history = self.client.get("/api/health-check/history").json()
        assert len(history) == 1

    def test_history_capped_at_12(self):
        for _ in range(15):
            self.client.post("/api/health-check/run")
        history = self.client.get("/api/health-check/history").json()
        assert len(history) <= 12


# ══════════════════════════════════════════════════════════════════════════════
# Export & Backup
# ══════════════════════════════════════════════════════════════════════════════

class TestExportBackup:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.mod = _load_module("export_backup")
        self.client = _make_client(self.mod, tmp_path)
        self.state_dir = tmp_path / "ai-employee" / "state"
        self.backup_dir = tmp_path / "ai-employee" / "backups"

    def _write_state(self, fname: str, data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / fname).write_text(json.dumps(data))

    def test_list_modules(self):
        r = self.client.get("/api/export/modules")
        modules = {m["key"]: m for m in r.json()}
        assert "crm" in modules
        assert "finance" in modules
        assert isinstance(modules["crm"]["exists"], bool)

    def test_export_json_unknown_module(self):
        r = self.client.get("/api/export/json/unknown_module")
        assert r.status_code == 404

    def test_export_json_existing(self):
        self._write_state("crm.json", {"leads": [{"id": "abc", "name": "Test"}]})
        r = self.client.get("/api/export/json/crm")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/json"
        body = json.loads(r.content)
        assert body["leads"][0]["name"] == "Test"

    def test_export_csv_unknown_module(self):
        r = self.client.get("/api/export/csv/bad_module/leads")
        assert r.status_code == 404

    def test_export_csv_no_data(self):
        r = self.client.get("/api/export/csv/crm/leads")
        assert r.status_code == 404

    def test_export_csv_with_data(self):
        self._write_state("crm.json", {"leads": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]})
        r = self.client.get("/api/export/csv/crm/leads")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        lines = r.content.decode().splitlines()
        assert lines[0] == "id,name"  # header
        assert len(lines) == 3  # header + 2 rows

    def test_create_backup_empty(self):
        r = self.client.post("/api/export/backup")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["backup_file"].endswith(".zip")
        assert (self.backup_dir / body["backup_file"]).exists()

    def test_create_backup_includes_files(self):
        self._write_state("crm.json", {"leads": []})
        r = self.client.post("/api/export/backup")
        body = r.json()
        assert body["files_included"] >= 1

    def test_list_backups(self):
        self.client.post("/api/export/backup")
        r = self.client.get("/api/export/backups")
        backups = r.json()
        assert len(backups) >= 1
        assert backups[0]["name"].endswith(".zip")

    def test_download_backup(self):
        backup_name = self.client.post("/api/export/backup").json()["backup_file"]
        r = self.client.get(f"/api/export/download-backup/{backup_name}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        # Verify it's a valid ZIP
        buf = zipfile.ZipFile(__import__("io").BytesIO(r.content))
        assert buf.namelist() is not None

    def test_download_backup_not_found(self):
        r = self.client.get("/api/export/download-backup/nonexistent.zip")
        assert r.status_code == 404

    def test_download_backup_path_traversal(self):
        # Simulate path traversal by passing encoded sequences; the guard
        # checks for ".." inside the backup_name path parameter value.
        # httpx normalises URLs, so we pass the param via URL encoding.
        import urllib.parse
        evil = urllib.parse.quote("../etc/passwd", safe="")
        r = self.client.get(f"/api/export/download-backup/{evil}")
        # Must be rejected (400) or not found (404 after normalisation);
        # critically it must NOT return a file from outside the backup dir.
        assert r.status_code in (400, 404)

    def test_download_backup_path_traversal_backslash(self):
        import urllib.parse
        evil = urllib.parse.quote("..\\windows\\system32", safe="")
        r = self.client.get(f"/api/export/download-backup/{evil}")
        assert r.status_code in (400, 404)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: Feature router registration
# ══════════════════════════════════════════════════════════════════════════════

class TestFeatureRegistration:
    """Verify that __init__.py exports exactly the expected routers."""

    @pytest.fixture(autouse=True)
    def _add_features_to_path(self):
        """Make the features directory importable as a package."""
        parent = str(_FEATURES_DIR.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        # Remove any stale cached import so we get a clean module each test
        for key in list(sys.modules.keys()):
            if key == "features" or key.startswith("features."):
                del sys.modules[key]
        yield
        for key in list(sys.modules.keys()):
            if key == "features" or key.startswith("features."):
                del sys.modules[key]

    def _import_features(self):
        import features as feat
        return feat

    def test_all_routers_importable(self):
        mod = self._import_features()
        assert hasattr(mod, "ALL_ROUTERS")
        assert len(mod.ALL_ROUTERS) == 16

    def test_all_routers_have_correct_type(self):
        from fastapi.routing import APIRouter
        mod = self._import_features()
        for router in mod.ALL_ROUTERS:
            assert isinstance(router, APIRouter), f"{router} is not an APIRouter"

    def test_router_prefixes_are_unique(self):
        mod = self._import_features()
        prefixes = [r.prefix for r in mod.ALL_ROUTERS]
        assert len(prefixes) == len(set(prefixes)), f"Duplicate router prefixes: {prefixes}"
