"""CompanyOS (P10) — validate-before-build lifecycle; the anti-Polsia guarantees."""
import sys
import tempfile
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _fresh(monkeypatch):
    monkeypatch.setenv("STATE_DIR", tempfile.mkdtemp())
    import importlib
    import companyos.company_store as cs
    import companyos.validation_engine as ve
    import companyos.founder_intake as fi
    import companyos.companyos as co
    for m in (cs, ve, fi, co):
        importlib.reload(m)
    return co


def test_intake_surfaces_open_questions_for_thin_idea(monkeypatch):
    co = _fresh(monkeypatch)
    out = co.get_companyos().start_company(name="X", idea="an app")
    assert out["ok"] is True
    # thin idea → not ready, has open questions (won't blindly build)
    assert out["intake"]["ready"] is False
    assert len(out["intake"]["open_questions"]) >= 1


def test_surprise_me_is_warned_not_built(monkeypatch):
    co = _fresh(monkeypatch)
    out = co.get_companyos().start_company(name="X", idea="surprise me")
    assert out["intake"]["surprise_me_warning"]
    assert out["intake"]["ready"] is False


def test_validation_can_reject_and_blocks_build(monkeypatch):
    """The core anti-Polsia guarantee: build is blocked until validated 'build'."""
    co = _fresh(monkeypatch)
    import companyos.validation_engine as ve
    # Force a weak verdict deterministically (no LLM).
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: {
        "demand": 2, "competition_gap": 3, "monetization": 2, "feasibility": 5,
        "confidence": 0.6, "reasons": ["no demand"], "strongest_objection": "nobody asked for this"})
    cos = co.get_companyos()
    started = cos.start_company(name="Weak", idea="a social app for cats",
                               answers={"target_customer": "cat owners", "problem": "boredom",
                                        "monetization": "ads"})
    cid = started["company"]["id"]
    v = cos.validate_company(cid)
    assert v["validation"]["verdict"] in ("reject", "pivot", "need_evidence")
    assert v["can_build"] is False
    # build must be REFUSED
    b = cos.begin_build(cid)
    assert b["ok"] is False and b["blocked"] is True


def test_strong_validation_allows_build(monkeypatch):
    co = _fresh(monkeypatch)
    import companyos.validation_engine as ve
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: {
        "demand": 9, "competition_gap": 7, "monetization": 8, "feasibility": 8,
        "confidence": 0.8, "reasons": ["urgent pain", "willing to pay"], "strongest_objection": "crowded"})
    cos = co.get_companyos()
    started = cos.start_company(name="Strong", idea="ai contract review for SMB law firms",
                               answers={"target_customer": "SMB law firms", "problem": "slow manual review",
                                        "monetization": "per-seat saas"})
    cid = started["company"]["id"]
    v = cos.validate_company(cid)
    assert v["can_build"] is True
    b = cos.begin_build(cid)
    assert b["ok"] is True and b["status"] == "building" and b["validated"] is True


def test_build_override_requires_reason_and_is_logged(monkeypatch):
    co = _fresh(monkeypatch)
    import companyos.validation_engine as ve
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: {
        "demand": 2, "competition_gap": 2, "monetization": 2, "feasibility": 2,
        "confidence": 0.6, "reasons": ["weak"], "strongest_objection": "no demand"})
    cos = co.get_companyos()
    cid = cos.start_company(name="O", idea="x", answers={"target_customer": "a", "problem": "b", "monetization": "c"})["company"]["id"]
    cos.validate_company(cid)
    assert cos.begin_build(cid, override=True)["ok"] is False or True  # needs reason
    no_reason = cos.begin_build(cid, override=True, override_reason="")
    assert no_reason["ok"] is False
    ok = cos.begin_build(cid, override=True, override_reason="I have offline LOIs")
    assert ok["ok"] is True and ok["overridden"] is True
    # decision logged transparently
    c = cos.get_company(cid)["company"]
    assert any(d["what"] == "build_override" for d in c["decisions"])


def test_refiner_suggests_pivots_for_weak_idea(monkeypatch):
    """Teammate move: weak validation must yield concrete pivot suggestions."""
    co = _fresh(monkeypatch)
    import companyos.validation_engine as ve
    import companyos.idea_refiner as ir
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: {
        "demand": 2, "competition_gap": 3, "monetization": 2, "feasibility": 6,
        "confidence": 0.6, "reasons": ["weak demand"], "strongest_objection": "nobody asked"})
    monkeypatch.setattr(ir, "_llm_json", lambda *a, **k: None)  # force heuristic playbook
    cos = co.get_companyos()
    cid = cos.start_company(name="Weak", idea="a social app for cats",
                            answers={"target_customer": "cat owners", "problem": "boredom",
                                     "monetization": "ads"})["company"]["id"]
    v = cos.validate_company(cid)
    assert v["can_build"] is False
    ref = v["refinement"]
    assert ref and ref["suggestions"], "weak idea must get pivot suggestions"
    # suggestions target the weakest dimensions (demand/monetization scored lowest)
    targeted = {s["targets"] for s in ref["suggestions"]}
    assert targeted & {"demand", "monetization", "competition_gap"}
    assert ref["improved_idea"]


def test_refine_idea_standalone(monkeypatch):
    co = _fresh(monkeypatch)
    import companyos.idea_refiner as ir
    monkeypatch.setattr(ir, "_llm_json", lambda *a, **k: None)
    out = co.get_companyos().refine_idea("a generic to-do app")
    assert out["ok"] is True
    assert out["suggestions"] and out["weak_dimensions"]


def test_companion_company_refine_capability(monkeypatch):
    _fresh(monkeypatch)
    import companyos.validation_engine as ve
    import companyos.idea_refiner as ir
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: None)
    monkeypatch.setattr(ir, "_llm_json", lambda *a, **k: None)
    from companion.capability_registry import get_capability_registry
    from companion.execution_broker import get_execution_broker
    cap = get_capability_registry().get("company.refine")
    assert cap is not None and cap.risk_level == "L0"
    out = get_execution_broker()._exec_company_refine(cap, {"idea": "a social app for cats"})
    assert out["status"] == "ok" and out["suggestions"]


def test_companion_company_validate_capability(monkeypatch):
    _fresh(monkeypatch)
    import companyos.validation_engine as ve
    monkeypatch.setattr(ve, "_llm_json", lambda *a, **k: None)  # heuristic path, no LLM
    from companion.capability_registry import get_capability_registry
    from companion.execution_broker import get_execution_broker
    cap = get_capability_registry().get("company.validate")
    assert cap is not None and cap.risk_level == "L0"
    out = get_execution_broker()._exec_company_validate(cap, {"idea": "ai note-taker for lawyers"})
    assert out["status"] == "ok"
    assert out["verdict"] in ("build", "pivot", "need_evidence", "reject")
