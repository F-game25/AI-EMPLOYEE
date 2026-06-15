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
from .idea_refiner import get_idea_refiner
from .company_planner import get_company_planner
from .export_engine import get_export_engine


class CompanyOS:
    def __init__(self) -> None:
        self._store = get_company_store()
        self._intake = get_founder_intake()
        self._validator = get_validation_engine()
        self._refiner = get_idea_refiner()
        self._planner = get_company_planner()
        self._exporter = get_export_engine()

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
        brief = c.get("brief") or {}
        verdict = self._validator.validate(brief)
        new_status = "validated" if verdict["verdict"] == "build" else (
            "rejected" if verdict["verdict"] == "reject" else "intake")
        # Teammate move: when the idea isn't strong enough, don't just stop —
        # propose concrete pivots that turn it into a buildable one.
        refinement = None
        if verdict["verdict"] != "build":
            refinement = self._refiner.refine(brief, verdict)
        self._store.update(company_id, {"validation": verdict, "status": new_status,
                                        "refinement": refinement})
        self._store.log_decision(
            company_id, what=f"validation:{verdict['verdict']}",
            why=f"composite={verdict['composite']} conf={verdict['confidence']} — {verdict['recommendation']}")
        return {"ok": True, "company_id": company_id, "validation": verdict,
                "status": new_status,
                "can_build": verdict["verdict"] == "build",
                "refinement": refinement}

    # Standalone refiner — turn a weak idea into a usable one (no company needed).
    def refine_idea(self, idea: str, validation: dict | None = None) -> dict:
        brief = {"idea": (idea or "").strip()}
        if not brief["idea"]:
            return {"ok": False, "error": "idea required"}
        v = validation or self._validator.validate(brief)
        out = self._refiner.refine(brief, v)
        return {"ok": True, "validation": v, **out}

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

    # 4) Plan — only after the build gate (company must be 'building').
    def plan_company(self, company_id: str) -> dict:
        c = self._store.get(company_id)
        if c is None:
            return {"ok": False, "error": "company not found"}
        if c.get("status") not in ("building", "operating"):
            return {"ok": False, "blocked": True,
                    "reason": "Plan only after the build gate clears (validate → build first)."}
        roadmap = self._planner.build_roadmap(c.get("brief") or {}, c.get("validation"))
        self._store.update(company_id, {"roadmap": roadmap})
        self._store.log_decision(company_id, what="roadmap",
                                 why=f"{len(roadmap.get('milestones', []))} milestones planned")
        return {"ok": roadmap.get("ok", True), "company_id": company_id, "roadmap": roadmap}

    # 5) Run one orchestrated cycle via the M7 swarm (approval-gated).
    def run_company_cycle(self, company_id: str) -> dict:
        c = self._store.get(company_id)
        if c is None:
            return {"ok": False, "error": "company not found"}
        if c.get("status") not in ("building", "operating"):
            return {"ok": False, "blocked": True,
                    "reason": "Company must be building/operating to run a cycle."}
        goal = (c.get("roadmap") or {}).get("goal") or str((c.get("brief") or {}).get("idea") or "")
        result = self._planner.run_cycle(goal)
        self._store.update(company_id, {"status": "operating"})
        self._store.log_decision(company_id, what="cycle",
                                 why=f"executed={result.get('executed')} approvals={len(result.get('approvals_required') or [])}")
        return {"ok": result.get("ok", True), "company_id": company_id, "cycle": result}

    # 6) Export — full local ownership (no lock-in).
    def export_company(self, company_id: str) -> dict:
        c = self._store.get(company_id)
        if c is None:
            return {"ok": False, "error": "company not found"}
        return self._exporter.export(c)

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
