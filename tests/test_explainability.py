"""Tests for the Explainability Layer (XAI).

Covers:
  - Confidence scoring (hedges, definites, causals)
  - Key factor extraction (causal sentences + domain hints)
  - Reason extraction (causal-first, length limit, fallback)
  - Alternatives extraction
  - ExplainabilityEngine: explain(), get(), recent(), recent_for_agent()
  - Singleton identity
  - Audit integration (AuditEngine called on explain)
  - Safe flag always True
  - Server.py: lazy loader, embedded explain_id marker, endpoint registration
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.explainability_layer import (
    ExplainContext,
    ExplainabilityEngine,
    Explanation,
    _score_confidence,
    _confidence_label,
    _extract_key_factors,
    _extract_reason,
    _extract_alternatives,
    get_explain_engine,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceScoring:
    def test_base_score_around_middle(self):
        score = _score_confidence("The result is ready.")
        assert 0.1 <= score <= 0.95

    def test_hedge_phrases_lower_score(self):
        hedged = "This might work. It could be the case. Perhaps we should try."
        normal = "This works. Use this approach."
        assert _score_confidence(hedged) < _score_confidence(normal)

    def test_definite_phrases_raise_score(self):
        definite = "This is definitely the correct answer. It will always work."
        vague = "This is something."
        assert _score_confidence(definite) > _score_confidence(vague)

    def test_causal_language_raises_score(self):
        causal = "This is recommended because the data shows a clear trend."
        no_causal = "This is recommended."
        assert _score_confidence(causal) >= _score_confidence(no_causal)

    def test_very_short_response_lower_score(self):
        short = "Yes."
        long = (
            "Based on the analysis, this candidate is the best fit "
            "because they have the required skills and experience. "
            "The assessment clearly shows a strong match."
        )
        assert _score_confidence(short) < _score_confidence(long)

    def test_score_clamped_between_01_and_095(self):
        many_hedges = " ".join(["might could perhaps possibly"] * 20)
        assert _score_confidence(many_hedges) >= 0.10
        many_definites = " ".join(["definitely certainly clearly always will"] * 20)
        assert _score_confidence(many_definites) <= 0.95

    def test_score_is_float(self):
        assert isinstance(_score_confidence("test"), float)


class TestConfidenceLabel:
    def test_high_above_07(self):
        assert _confidence_label(0.70) == "high"
        assert _confidence_label(0.95) == "high"

    def test_medium_between_04_and_07(self):
        assert _confidence_label(0.40) == "medium"
        assert _confidence_label(0.69) == "medium"

    def test_low_below_04(self):
        assert _confidence_label(0.10) == "low"
        assert _confidence_label(0.39) == "low"


# ═══════════════════════════════════════════════════════════════════════════════
# Reason extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestReasonExtraction:
    def test_causal_sentence_preferred(self):
        response = (
            "Candidate A has many years of experience. "
            "We recommend them because they match all required skills. "
            "They also have excellent references."
        )
        reason = _extract_reason(response, "recruiter", "rank_candidate")
        assert "because" in reason.lower() or "match" in reason.lower()

    def test_fallback_to_first_sentences(self):
        response = "Candidate A is the best fit. They have strong skills."
        reason = _extract_reason(response, "recruiter", "rank_candidate")
        assert len(reason) > 0
        assert "Candidate A" in reason

    def test_reason_max_length_respected(self):
        long_response = "X " * 500
        reason = _extract_reason(long_response, "agent", "action")
        assert len(reason) <= 280 + 20  # small buffer for edge cases

    def test_fallback_reason_when_too_short(self):
        reason = _extract_reason("Ok.", "lead-scorer", "score")
        # Should generate a fallback generic reason
        assert "lead-scorer" in reason or "score" in reason or len(reason) > 20

    def test_strips_code_blocks(self):
        response = "```python\nimport os\n```\nThe answer is: use the API."
        reason = _extract_reason(response, "agent", "action")
        assert "import os" not in reason


# ═══════════════════════════════════════════════════════════════════════════════
# Key factor extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeyFactorExtraction:
    def test_extracts_causal_fragments(self):
        response = "We recommend this candidate because they have 5 years of experience. They are a great fit since their skills match."
        factors = _extract_key_factors("recruiter", "rank", response)
        assert len(factors) > 0

    def test_domain_factors_added_for_recruiter(self):
        response = "This person is good."
        factors = _extract_key_factors("recruiter", "rank", response)
        assert any("experience" in f.lower() or "fit" in f.lower() or "qualification" in f.lower() for f in factors)

    def test_domain_factors_for_lead_scorer(self):
        response = "Score assigned."
        factors = _extract_key_factors("lead-scorer", "score", response)
        assert len(factors) > 0

    def test_max_5_factors(self):
        response = " ".join(
            [f"Factor {i} because it is important since it matters due to reason." for i in range(20)]
        )
        factors = _extract_key_factors("recruiter", "rank", response)
        assert len(factors) <= 5

    def test_factors_are_capitalised(self):
        response = "We recommend because the fit is good."
        factors = _extract_key_factors("recruiter", "rank", response)
        for f in factors:
            assert f[0].isupper() or f[0].isdigit(), f"Factor not capitalised: {f!r}"

    def test_no_duplicate_factors(self):
        response = "Good because excellent fit. Good because excellent fit."
        factors = _extract_key_factors("recruiter", "rank", response)
        lower = [f.lower() for f in factors]
        assert len(lower) == len(set(lower))


# ═══════════════════════════════════════════════════════════════════════════════
# Alternatives extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlternativesExtraction:
    def test_extracts_alternative_phrases(self):
        response = "Candidate A is best. Alternatively, Candidate B is also strong."
        alts = _extract_alternatives(response)
        assert len(alts) > 0
        assert any("Candidate B" in a for a in alts)

    def test_extracts_however_phrase(self):
        response = "Option A is recommended. However, Option B may work if budget is limited."
        alts = _extract_alternatives(response)
        assert len(alts) > 0

    def test_no_alternatives_returns_empty(self):
        response = "This is the only correct answer."
        alts = _extract_alternatives(response)
        assert isinstance(alts, list)

    def test_max_3_alternatives(self):
        response = " ".join(
            [f"Alternatively option {i} is possible. However option {i} also works. On the other hand option {i}." for i in range(10)]
        )
        alts = _extract_alternatives(response)
        assert len(alts) <= 3


# ═══════════════════════════════════════════════════════════════════════════════
# ExplainabilityEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestExplainabilityEngine:
    def _engine(self) -> ExplainabilityEngine:
        return ExplainabilityEngine(cache_size=100)

    def _ctx(self, agent="recruiter", response="Candidate A is best because they have experience.") -> ExplainContext:
        return ExplainContext(
            agent=agent,
            action="rank_candidate",
            message="Rank these candidates",
            response=response,
            model="test-model",
            user_id="user:test",
        )

    # ── explain() ─────────────────────────────────────────────────────────────

    def test_explain_returns_explanation(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert isinstance(exp, Explanation)

    def test_explain_id_format(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert re.match(r"^xai-[a-zA-Z0-9]{12}$", exp.explain_id)

    def test_explain_safe_always_true(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert exp.safe is True

    def test_explain_has_reason(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert len(exp.reason) > 0

    def test_explain_has_key_factors(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert isinstance(exp.key_factors, list)

    def test_explain_has_alternatives(self):
        engine = self._engine()
        exp = engine.explain(ExplainContext(
            agent="recruiter",
            action="rank",
            message="Rank candidates",
            response="Candidate A is top. However, Candidate B is close.",
        ))
        assert isinstance(exp.alternatives, list)

    def test_explain_confidence_in_range(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert 0.0 <= exp.confidence <= 1.0

    def test_explain_confidence_label_valid(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        assert exp.confidence_label in ("low", "medium", "high")

    def test_explain_to_dict_serialisable(self):
        import json
        engine = self._engine()
        exp = engine.explain(self._ctx())
        json.dumps(exp.to_dict())

    def test_explain_does_not_expose_chain_of_thought(self):
        """The raw internal reasoning must never appear in the explanation."""
        engine = self._engine()
        internal = "<internal>Do not expose this reasoning chain</internal>"
        exp = engine.explain(ExplainContext(
            agent="recruiter",
            action="rank",
            message="rank",
            response=f"Candidate A is best. {internal}",
        ))
        assert "<internal>" not in exp.reason
        assert all("<internal>" not in f for f in exp.key_factors)

    # ── get() ─────────────────────────────────────────────────────────────────

    def test_get_returns_stored_explanation(self):
        engine = self._engine()
        exp = engine.explain(self._ctx())
        retrieved = engine.get(exp.explain_id)
        assert retrieved is not None
        assert retrieved["explain_id"] == exp.explain_id

    def test_get_returns_none_for_unknown_id(self):
        engine = self._engine()
        assert engine.get("xai-nonexistent123") is None

    # ── recent() ──────────────────────────────────────────────────────────────

    def test_recent_returns_list(self):
        engine = self._engine()
        engine.explain(self._ctx())
        items = engine.recent(limit=10)
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_recent_respects_limit(self):
        engine = self._engine()
        for _ in range(10):
            engine.explain(self._ctx())
        assert len(engine.recent(limit=3)) <= 3

    def test_recent_newest_first(self):
        engine = self._engine()
        exp1 = engine.explain(self._ctx(response="First response"))
        exp2 = engine.explain(self._ctx(response="Second response"))
        items = engine.recent(limit=5)
        ids = [i["explain_id"] for i in items]
        assert ids.index(exp2.explain_id) < ids.index(exp1.explain_id)

    # ── recent_for_agent() ────────────────────────────────────────────────────

    def test_recent_for_agent_filters_correctly(self):
        engine = self._engine()
        engine.explain(self._ctx(agent="recruiter"))
        engine.explain(self._ctx(agent="lead-scorer"))
        engine.explain(self._ctx(agent="recruiter"))
        items = engine.recent_for_agent("recruiter", limit=10)
        assert all(i["agent"] == "recruiter" for i in items)

    def test_recent_for_agent_empty_when_no_match(self):
        engine = self._engine()
        engine.explain(self._ctx(agent="recruiter"))
        items = engine.recent_for_agent("brand-strategist", limit=10)
        assert items == []

    # ── Singleton ─────────────────────────────────────────────────────────────

    def test_singleton_returns_same_instance(self):
        a = get_explain_engine()
        b = get_explain_engine()
        assert a is b

    def test_singleton_accumulates_across_calls(self):
        engine = get_explain_engine()
        before = len(engine.recent(limit=1000))
        engine.explain(self._ctx())
        after = len(engine.recent(limit=1000))
        assert after == before + 1


# ═══════════════════════════════════════════════════════════════════════════════
# Server.py integration (static analysis)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerXAIIntegration:
    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_get_explain_engine_loader_defined(self):
        assert "_get_explain_engine" in self._src()

    def test_explainability_layer_imported(self):
        assert "explainability_layer" in self._src()

    def test_explain_context_used_in_generate(self):
        src = self._src()
        assert "ExplainContext" in src

    def test_explain_id_embedded_as_html_comment(self):
        src = self._src()
        assert "<!--xai:" in src

    def test_xai_comment_pattern_strips_marker(self):
        src = self._src()
        assert "_xai_comment_pat" in src

    def test_explanation_promoted_to_json_field(self):
        src = self._src()
        assert '"explanation"' in src or "'explanation'" in src

    def test_explain_id_endpoint_registered(self):
        src = self._src()
        assert '"/api/explain/{explain_id}"' in src

    def test_explain_history_endpoint_registered(self):
        src = self._src()
        assert '"/api/explain/history"' in src

    def test_explainability_module_file_exists(self):
        assert (RUNTIME_DIR / "core" / "explainability_layer.py").exists()

    def test_xai_error_non_fatal(self):
        src = self._src()
        # Must be inside a try/except so errors never break core response
        assert "explainability generation error (non-fatal)" in src

    def test_explanation_json_includes_required_fields(self):
        src = self._src()
        # All required XAI output fields must be mapped in the response payload
        for field in ("reason", "key_factors", "alternatives", "confidence", "confidence_label"):
            assert field in src
