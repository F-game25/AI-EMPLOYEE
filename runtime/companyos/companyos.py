"""CompanyOS facade — the validate-before-build company lifecycle.

Enforces the anti-Polsia guarantee in code: a company cannot enter 'building'
until validation returns 'build' (or a human explicitly overrides, which is logged
as a transparent decision). Delegates real work to existing engines; never fakes.
"""
from __future__ import annotations

import threading

from .company_store import get_company_store
from .founder_intake import get_founder_intake
from .validation_engine import get_validation_engine


class CompanyOS:
    def __init__(self) -> None:
        self._store = get_company_store()
        self._intake = get_founder_intake()
        self._validator = get_validation_engine()

    # 1) Intake — idea → brief (surfaces gaps; doesn't build).
    def start_company(self, *, name: str, idea: str, answers: dict | None = None) -> dict:
        intake = self._intake.build_brief(idea, answers)
        company = self._store.create(name=name, brief=intake["brief"])
        self._store.log_decision(company["id"], what="intake",
                                 why=f"ready={intake['ready']}; {len(intake['open_questions'])} open questions")
        return {"ok": True, "company": company, "intake": intake,
                "next": ("answer_open_questions" if not intake["ready"] else "validate")}

    # 2) Validate — the gate. Refuses weak ideas.
    def validate_company(self, company_id: str) -> dict:
        c = self._store.get(company_id)
        if c is None:
            return {"ok": False, "error": "company not found"}
        self._store.update(company_id, {"status": "validating"})
        verdict = self._validator.validate(c.get("brief") or {})
        new_status = "validated" if verdict["verdict"] == "build" else (
            "rejected" if verdict["verdict"] == "reject" else "intake")
        self._store.update(company_id, {"validation": verdict, "status": new_status})
        self._store.log_decision(
            company_id, what=f"validation:{verdict['verdict']}",
            why=f"composite={verdict['composite']} conf={verdict['confidence']} — {verdict['recommendation']}")
        return {"ok": True, "company_id": company_id, "validation": verdict,
                "status": new_status,
                "can_build": verdict["verdict"] == "build"}

    # 3) Build gate — STRUCTURALLY blocks until validated 'build' (or explicit override).
    def begin_build(self, company_id: str, *, override: bool = False, override_reason: str = "") -> dict:
        c = self._store.get(company_id)
        if c is None:
            return {"ok": False, "error": "company not found"}
        v = c.get("validation")
        validated_ok = bool(v and v.get("verdict") == "build")
        if not validated_ok and not override:
            return {
                "ok": False,
                "blocked": True,
                "reason": ("Validation has not returned 'build'. CompanyOS does not build on "
                           "unvalidated demand (the #1 way these systems waste money). "
                           "Validate first, or pass an explicit override."),
                "validation": v,
            }
        if not validated_ok and override:
            if not override_reason.strip():
                return {"ok": False, "error": "override requires a reason"}
            self._store.log_decision(company_id, what="build_override",
                                     why=f"human override of weak/absent validation: {override_reason}",
                                     by="operator")
        self._store.update(company_id, {"status": "building"})
        self._store.log_decision(company_id, what="begin_build",
                                 why="validated" if validated_ok else "human-overridden")
        return {"ok": True, "company_id": company_id, "status": "building",
                "validated": validated_ok, "overridden": (not validated_ok and override),
                "next": "wire roadmap → M7 swarm + Forge build (approval-gated)"}

    def get_company(self, company_id: str) -> dict:
        c = self._store.get(company_id)
        return {"ok": bool(c), "company": c} if c else {"ok": False, "error": "not found"}

    def list_companies(self) -> dict:
        return {"ok": True, "companies": self._store.list()}


_instance: CompanyOS | None = None
_instance_lock = threading.Lock()


def get_companyos() -> CompanyOS:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CompanyOS()
    return _instance
