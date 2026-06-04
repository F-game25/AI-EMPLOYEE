"""Heuristic task complexity classifier — no LLM call."""
from __future__ import annotations

POOL_CAP = {'simple': 100, 'medium': 400, 'complex': 800, 'critical': 1500}
ROUNDS   = {'simple': 2,   'medium': 4,   'complex': 6,   'critical': 8}

_CRITICAL_KEYWORDS = {
    'delete all', 'drop', 'rm -rf', 'wipe', 'irreversible',
    'production deploy', 'financial', 'pay', 'transfer funds',
}
_QUESTION_WORDS = {
    'how', 'why', 'what', 'which', 'compare', 'analyze', 'plan',
    'design', 'build', 'implement', 'create', 'refactor',
}
_COMPLEX_CONNECTORS = {
    'and', 'then', 'after', 'before', 'while', 'also',
    'additionally', 'furthermore', 'step', 'phase',
}


def classify(goal: str, context: dict | None = None) -> str:
    """Returns 'simple' | 'medium' | 'complex' | 'critical'."""
    lower = goal.lower()
    tokens = lower.split()

    for kw in _CRITICAL_KEYWORDS:
        if kw in lower:
            return 'critical'

    word_count = len(tokens)
    has_question = bool(_QUESTION_WORDS & set(tokens))

    if word_count <= 8 and not has_question:
        return 'simple'

    connector_count = sum(1 for t in tokens if t in _COMPLEX_CONNECTORS)
    if word_count > 30 or connector_count >= 3:
        return 'complex'

    return 'medium'
