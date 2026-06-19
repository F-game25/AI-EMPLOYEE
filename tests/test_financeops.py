"""M6 FinanceOps — advisory-only finance drafts; never executes, always sign-off-gated."""
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from finance.financeops import get_financeops  # noqa: E402


def test_revenue_forecast_is_deterministic_advisory():
    fo = get_financeops()
    out = fo.revenue_forecast({"price": 50, "customers": 100, "monthly_growth_pct": 10, "months": 6})
    assert out["ok"] is True
    assert out["advisory"] is True and out["requires_human_signoff"] is True
    assert out["executed"] is False and out["is_estimate"] is True
    assert len(out["projection"]) == 6
    # compound growth → later months >= earlier (estimate, not measured)
    assert out["projection"][-1]["revenue_est"] >= out["projection"][0]["revenue_est"]


def test_every_output_is_advisory_and_signoff_gated(monkeypatch):
    # Force LLM offline → honest 'unavailable', never fabricated figures.
    import finance.financeops as fofmod
    monkeypatch.setattr(fofmod, "_llm", lambda *a, **k: None)
    fo = get_financeops()
    for call in (lambda: fo.business_model("an ai note-taker"),
                 lambda: fo.pricing_analysis("pro tier"),
                 lambda: fo.pitch_memo("Acme")):
        out = call()
        # offline → ok False + unavailable, but still advisory + sign-off flagged, never executed
        assert out["requires_human_signoff"] is True
        assert out["executed"] is False
        assert out["ok"] is False and out["status"] == "unavailable"


def test_business_model_with_llm(monkeypatch):
    import finance.financeops as fofmod
    monkeypatch.setattr(fofmod, "_llm", lambda *a, **k: "Value prop: X. Revenue: subscription (est).")
    out = get_financeops().business_model("an ai note-taker")
    assert out["ok"] is True and out["advisory"] is True
    assert "draft" in out and out["draft"]
    assert "Advisory draft only" in out["disclaimer"]


def test_draft_dispatch_picks_kind(monkeypatch):
    import finance.financeops as fofmod
    monkeypatch.setattr(fofmod, "_llm", lambda *a, **k: "draft text")
    fo = get_financeops()
    assert fo.draft("pricing analysis for pro tier")["kind"] == "pricing_analysis"
    assert fo.draft("write an investor pitch memo")["kind"] == "pitch_memo"
    assert fo.draft("draft a business model for X")["kind"] == "business_model"
    # forecast routes to the deterministic path (no LLM needed)
    assert fo.draft("revenue forecast", inputs={"price": 10, "customers": 5})["kind"] == "revenue_forecast"


def test_no_transaction_keys_ever_present():
    """Defense: FinanceOps must never emit anything that looks like an executed txn."""
    out = get_financeops().revenue_forecast({"price": 1, "customers": 1})
    blob = str(out).lower()
    assert "executed': true" not in blob.replace('"', "'")
    assert out["executed"] is False


def test_companion_finance_capability_registered_and_runs(monkeypatch):
    import finance.financeops as fofmod
    monkeypatch.setattr(fofmod, "_llm", lambda *a, **k: "advisory draft body")
    from companion.capability_registry import get_capability_registry
    from companion.execution_broker import get_execution_broker
    cap = get_capability_registry().get("finance.draft")
    assert cap is not None and cap.risk_level == "L1"
    out = get_execution_broker()._exec_finance_draft(cap, {"request": "business model for an ai tool"})
    assert out["status"] == "ok"
    assert out["advisory"] is True and out["requires_human_signoff"] is True
