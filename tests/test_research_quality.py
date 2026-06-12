"""Module 8 — Research Quality Engine tests.

Offline and deterministic: no LLM, no network. The fixture mirrors the
persisted shape of core.deep_research_engine.DeepResearchReport
(sections=[{title,content}], citations=[{url,title,sub_question}], ...).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:  # conftest does this too; standalone safety
    sys.path.insert(0, str(_RUNTIME))

from research.quality import reviewer_panel
from research.quality.citation_anchor import anchor_claims
from research.quality.claim_auditor import audit_claims
from research.quality.integrity_gate import gate
from research.quality.material_passport import build_passport, content_hash
from research.quality.report_builder import finalize
from research.quality.research_planner import STAGES, plan_stages
from research.quality.source_verifier import verify_sources

_SRC_ENERGY = "https://www.energy.gov/solar-efficiency-2024"
_SRC_WIKI = "https://en.wikipedia.org/wiki/Perovskite_solar_cell"
_FAKE_URL = "https://fake-journal.example.com/study"

_CLAIM_KEYWORD = (
    "Solar panel efficiency improvements continued through 2024 "
    "with record gains in commercial modules."
)
_CLAIM_ALIEN = (
    "Bananas are rich in potassium and grow best in tropical climates around the world."
)


def make_report(**overrides) -> dict:
    """Persisted DeepResearchReport shape (see DeepResearchReport.to_dict)."""
    report = {
        "id": "abcd1234efgh5678",
        "topic": "Solar panel efficiency",
        "created_at": 1718000000.0,
        "status": "done",
        "sub_questions": [
            "What is the current efficiency of solar panels?",
            "What role do perovskite cells play?",
        ],
        "sources_found": 2,
        "sources_fetched": 2,
        "executive_summary": (
            "Solar panel efficiency kept improving in 2024, driven by perovskite "
            "cell research and better commercial modules. Laboratory perovskite "
            "designs crossed thirty percent efficiency [en.wikipedia.org]."
        ),
        "sections": [
            {
                "title": "What is the current efficiency of solar panels?",
                "content": (
                    "Solar panel efficiency improvements reached new records in "
                    "2024 [energy.gov]. Commercial module efficiency now exceeds "
                    "twenty-two percent in mainstream products [energy.gov]."
                ),
            },
            {
                "title": "What role do perovskite cells play?",
                "content": (
                    "Perovskite solar cell designs pushed laboratory efficiency "
                    "above thirty percent [en.wikipedia.org]."
                ),
            },
        ],
        "key_findings": [
            "Commercial solar module efficiency exceeds 22 percent.",
            "Perovskite lab cells crossed 30 percent efficiency.",
        ],
        "gaps_identified": ["Long-term perovskite degradation data is sparse."],
        "citations": [
            {
                "url": _SRC_ENERGY,
                "title": "Solar panel efficiency improvements 2024",
                "sub_question": "What is the current efficiency of solar panels?",
            },
            {
                "url": _SRC_WIKI,
                "title": "Perovskite solar cell",
                "sub_question": "What role do perovskite cells play?",
            },
        ],
        "report_md": "# Deep Research Report: Solar panel efficiency",
        "committed_to_memory": False,
        "error": "",
        "duration_s": 42.5,
    }
    report.update(overrides)
    return report


def with_section_sentence(report: dict, sentence: str) -> dict:
    out = copy.deepcopy(report)
    out["sections"][0]["content"] += " " + sentence
    return out


@pytest.fixture(autouse=True)
def _offline_deterministic(monkeypatch):
    """Live verification OFF, reviewer LLM OFF unless a test opts back in."""
    monkeypatch.delenv("RESEARCH_VERIFY_LIVE", raising=False)
    monkeypatch.setenv("RESEARCH_REVIEW_LLM", "0")


# ── citation_anchor ──────────────────────────────────────────────────────────

def test_anchor_keyword_overlap_true_alien_false():
    report = make_report()
    report["sections"][0]["content"] = f"{_CLAIM_KEYWORD} {_CLAIM_ALIEN}"
    by_text = {c["text"]: c for c in anchor_claims(report)["claims"]}

    keyword = by_text[_CLAIM_KEYWORD]
    assert keyword["anchored"] is True
    assert _SRC_ENERGY in keyword["source_urls"]

    alien = by_text[_CLAIM_ALIEN]
    assert alien["anchored"] is False
    assert alien["source_urls"] == []


def test_anchor_inline_bracket_domain_anchors():
    result = anchor_claims(make_report())
    assert result["total"] >= 3
    assert all(c["anchored"] for c in result["claims"])
    assert result["anchored_ratio"] == 1.0


# ── claim_auditor ────────────────────────────────────────────────────────────

def test_auditor_fabricated_inline_url_blocks():
    report = with_section_sentence(
        make_report(),
        f"A 2023 meta-analysis confirmed degradation rates below one percent ({_FAKE_URL}).",
    )
    audit = audit_claims(report)
    assert _FAKE_URL in audit["fabricated_refs"]
    assert audit["verdict"] == "block"


def test_auditor_clean_report_passes():
    audit = audit_claims(make_report())
    assert audit["fabricated_refs"] == []
    assert audit["unsupported"] == []
    assert audit["verdict"] == "pass"


def test_auditor_unsupported_below_threshold_warns():
    report = with_section_sentence(make_report(), _CLAIM_ALIEN)
    audit = audit_claims(report)
    assert audit["fabricated_refs"] == []
    assert len(audit["unsupported"]) == 1
    assert audit["verdict"] == "warn"


# ── source_verifier (live OFF → honest 'unchecked') ─────────────────────────

def test_verifier_offline_reports_unchecked_and_malformed():
    report = make_report()
    report["citations"].append({"url": "ftp://bad.example/file", "title": "bad"})
    result = verify_sources(report)
    by_url = {s["url"]: s for s in result["sources"]}
    assert by_url[_SRC_ENERGY]["status"] == "unchecked"
    assert by_url[_SRC_WIKI]["status"] == "unchecked"
    assert by_url["ftp://bad.example/file"]["status"] == "malformed"
    assert result["summary"]["live_checked"] is False
    assert result["summary"]["unchecked"] == 2


# ── integrity_gate ───────────────────────────────────────────────────────────

def test_gate_blocks_on_fabricated_ref():
    report = with_section_sentence(make_report(), f"Confirmed independently ({_FAKE_URL}).")
    result = gate(report)
    assert result["passed"] is False
    assert any(_FAKE_URL in b for b in result["blockers"])


def test_gate_passes_clean_report_unchecked_is_warning_not_blocker():
    result = gate(make_report())
    assert result["passed"] is True
    assert result["blockers"] == []
    assert any("unchecked" in w for w in result["warnings"])
    assert result["audit"]["claims"]["verdict"] == "pass"
    assert result["audit"]["sources"]["summary"]["live_checked"] is False


# ── reviewer_panel heuristic fallback ────────────────────────────────────────

def test_reviewer_panel_falls_back_to_heuristic_when_llm_raises(monkeypatch):
    monkeypatch.setenv("RESEARCH_REVIEW_LLM", "1")  # attempt the LLM path

    def _boom(prompt, timeout):
        raise RuntimeError("no live LLM in tests")

    monkeypatch.setattr(reviewer_panel, "_llm_generate", _boom)
    result = reviewer_panel.review(make_report(), n_reviewers=3)

    assert len(result["reviews"]) == 3
    assert {r["role"] for r in result["reviews"]} == set(reviewer_panel.ROLES)
    assert all(r["method"] == "heuristic" for r in result["reviews"])
    for r in result["reviews"]:
        assert set(r["scores"]) == {"rigor", "coverage", "clarity"}
        assert all(0.0 <= v <= 10.0 for v in r["scores"].values())
    assert isinstance(result["composite"], float)
    assert result["devils_advocate"]["strongest_objection"]


def test_reviewer_panel_is_deterministic_in_heuristic_mode():
    assert reviewer_panel.review(make_report()) == reviewer_panel.review(make_report())


# ── material_passport ────────────────────────────────────────────────────────

def test_passport_hash_stable_and_change_sensitive():
    p1 = build_passport(make_report())
    p2 = build_passport(make_report())
    assert p1["hash"] == p2["hash"] == content_hash(make_report())

    modified = make_report()
    modified["sections"][1]["content"] += " Extra finding."
    assert build_passport(modified)["hash"] != p1["hash"]

    assert p1["source_count"] == 2
    assert p1["verified_sources"] == 0  # live off → nothing claimed verified
    assert p1["tool_versions"] == {"engine": "deep_research_engine"}
    assert p1["reproducibility"]["sub_questions"] == make_report()["sub_questions"]


# ── report_builder ───────────────────────────────────────────────────────────

def test_finalize_attaches_quality_without_mutating_original():
    report = make_report()
    snapshot = copy.deepcopy(report)
    result = finalize(report)

    assert report == snapshot  # input untouched (deep compare)
    out = result["report"]
    assert out["sections"] == snapshot["sections"]
    assert out["executive_summary"] == snapshot["executive_summary"]
    assert out["citations"] == snapshot["citations"]

    quality = result["quality"]
    assert out["quality"] is quality
    assert quality["publishable"] is True
    assert quality["gate"]["passed"] is True
    assert quality["anchored_ratio"] == 1.0
    assert len(quality["reviews"]["reviews"]) == 3
    assert quality["passport"]["hash"] == content_hash(snapshot)


def test_finalize_blocked_gate_sets_publishable_false_with_reasons():
    report = with_section_sentence(make_report(), f"Proven by experts ({_FAKE_URL}).")
    quality = finalize(report)["quality"]
    assert quality["publishable"] is False
    assert quality["gate"]["passed"] is False
    assert quality["reasons"] == quality["gate"]["blockers"]
    assert any(_FAKE_URL in r for r in quality["reasons"])


# ── research_planner ─────────────────────────────────────────────────────────

def test_plan_stages_mirrors_staged_flow():
    plan = plan_stages("  Solar panel efficiency ")
    assert plan["topic"] == "Solar panel efficiency"
    assert plan["stages"] == list(STAGES)
    assert plan["stages"] == [
        "decompose", "collect", "verify", "synthesize", "audit", "review", "passport",
    ]
    assert set(plan["notes"]) == set(STAGES)
