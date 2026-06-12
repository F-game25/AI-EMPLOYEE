"""Build a structured spec from a goal; flag vague goals for clarification.

Vagueness heuristics (short goal / too few words / no action verb / bare
pronoun target) drive ``status='needs_clarification'`` with explicit
``open_questions`` — the planner refuses to plan an unclarified spec.
"""
from __future__ import annotations

import os
import re

from forge.lifecycle.acceptance_criteria import ACTION_VERBS, CLAUSE_SPLIT, derive_criteria

_VAGUE_PRONOUNS = {"it", "this", "that", "stuff", "thing", "things", "something"}
_MIN_GOAL_CHARS = int(os.environ.get("FORGE_SPEC_MIN_CHARS", "15"))
_MIN_GOAL_WORDS = int(os.environ.get("FORGE_SPEC_MIN_WORDS", "4"))
_PRONOUN_WORD_CEIL = int(os.environ.get("FORGE_SPEC_PRONOUN_WORD_CEIL", "8"))


def build_spec(goal: str, context: dict | None = None) -> dict:
    """-> {spec: {...}, open_questions: [...], status: 'ready'|'needs_clarification'}"""
    context = context or {}
    g = (goal or "").strip()
    words = re.findall(r"[a-zA-Z]+", g.lower())
    wset = set(words)

    open_questions: list[str] = []
    if len(g) < _MIN_GOAL_CHARS:
        open_questions.append("Goal is too short — what exactly should be built or changed?")
    if len(words) < _MIN_GOAL_WORDS:
        open_questions.append("Goal has too few words to scope — name the component and the outcome.")
    if not (wset & ACTION_VERBS):
        open_questions.append("No action verb found — what should the system DO?")
    if (wset & _VAGUE_PRONOUNS) and len(words) < _PRONOUN_WORD_CEIL:
        open_questions.append("Goal points at 'it/this/that' without naming the target — name the file, feature, or system.")

    derived = derive_criteria(g, context)
    if not derived["criteria"] and not open_questions:
        open_questions.append("Could not derive any checkable acceptance criterion — restate the goal as actions.")

    assumptions = list(context.get("assumptions", []))
    if not assumptions:
        assumptions = ["No additional context provided; existing repo conventions assumed."]

    return {
        "spec": {
            "goal": g,
            "in_scope": [c.strip() for c in CLAUSE_SPLIT.split(g) if c.strip()],
            "out_of_scope": list(context.get("out_of_scope", [])),
            "assumptions": assumptions,
            "acceptance_criteria": derived["criteria"],
        },
        "open_questions": open_questions,
        "status": "needs_clarification" if open_questions else "ready",
    }
