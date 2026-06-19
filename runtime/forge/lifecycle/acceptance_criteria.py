"""Derive machine-checkable acceptance criteria from a goal statement.

Heuristic core: split the goal into clauses, keep clauses anchored on an
action verb, and turn each into a testable statement. Optional guarded LLM
enrichment may APPEND advisory criteria but never changes the heuristic ones.
"""
from __future__ import annotations

import json
import re

from forge.lifecycle._llm import try_generate

ACTION_VERBS = {
    "add", "build", "create", "implement", "fix", "support", "return", "returns",
    "validate", "render", "expose", "store", "log", "send", "parse", "test",
    "show", "display", "update", "remove", "delete", "migrate", "refactor",
    "optimize", "secure", "cache", "stream", "upload", "download", "export",
    "import", "generate", "compute", "track", "wire", "connect", "integrate",
    "deploy", "serve", "handle", "write", "read", "list", "block", "gate",
}
_BUILD_WORDS = {"build", "compile", "lint", "bundle", "package", "deploy"}
_MANUAL_WORDS = {"look", "looks", "design", "style", "styling", "layout",
                 "visual", "animation", "polish", "color", "colour"}


class _ClauseSplitter:
    def split(self, text: str) -> list[str]:
        bounded = (text or "")[:4000]
        for marker in ("\n", ";", ","):
            bounded = bounded.replace(marker, ".")
        bounded = re.sub(r"\s+(?:and|then)\s+", ".", bounded, flags=re.IGNORECASE)
        return bounded.split(".")


CLAUSE_SPLIT = _ClauseSplitter()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _checkable_via(clause_words: set[str]) -> str:
    if clause_words & _MANUAL_WORDS:
        return "manual"
    if clause_words & _BUILD_WORDS:
        return "build"
    return "test"


def _llm_extra(goal: str, have: int) -> list[dict]:
    """Optional advisory criteria from the LLM — guarded, additive only."""
    raw = try_generate(
        "Return a JSON array (max 3) of extra acceptance-criterion statements "
        f"for this goal, no prose:\n{goal}")
    if not raw:
        return []
    try:
        items = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        return [{"id": f"AC-{have + i + 1}", "statement": str(s)[:200],
                 "checkable_via": "manual", "priority": "could", "source": "llm"}
                for i, s in enumerate(items) if isinstance(s, str) and s.strip()][:3]
    except Exception:
        return []


def derive_criteria(goal: str, context: dict | None = None) -> dict:
    """-> {criteria: [{id, statement, checkable_via, priority}], confidence}"""
    goal = (goal or "").strip()
    clauses = [c.strip() for c in CLAUSE_SPLIT.split(goal) if c.strip()]
    criteria: list[dict] = []
    for clause in clauses:
        cw = _words(clause)
        if not (cw & ACTION_VERBS):
            continue
        criteria.append({
            "id": f"AC-{len(criteria) + 1}",
            "statement": f"System must {clause[0].lower() + clause[1:]}",
            "checkable_via": _checkable_via(cw),
            "priority": "must" if not criteria else "should",
        })
    if criteria:
        confidence = round(min(1.0, 0.4 + 0.6 * len(criteria) / max(1, len(clauses))), 2)
    else:
        confidence = 0.1
    criteria.extend(_llm_extra(goal, len(criteria)))
    return {"criteria": criteria, "confidence": confidence}
