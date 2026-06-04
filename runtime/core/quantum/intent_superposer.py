"""Intent superposition — heuristic reframings, LLM hook available."""
from __future__ import annotations
import logging
from core.quantum.search.schema import IntentCandidate

log = logging.getLogger(__name__)

_AMBIGUITY_WORDS = {
    'how', 'why', 'what', 'which', 'compare', 'analyze', 'plan',
    'design', 'build', 'implement', 'create', 'refactor', 'or', 'either',
}


def _is_simple(text: str) -> bool:
    tokens = text.lower().split()
    return len(tokens) <= 8 and not bool(_AMBIGUITY_WORDS & set(tokens))


def _action_focused(text: str) -> str:
    import re
    tokens = text.split()
    verbs = [t for t in tokens if t.lower() in {
        'create', 'build', 'implement', 'generate', 'analyze', 'review',
        'update', 'fix', 'deploy', 'run', 'test', 'search', 'find', 'write',
        'design', 'refactor', 'optimize', 'delete', 'add', 'remove', 'send',
    }]
    nouns = [t for t in tokens if len(t) > 4 and t not in verbs and not t.lower() in {
        'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'also',
    }]
    if verbs and nouns:
        return f"{verbs[0]} the {nouns[0]}"
    return text


class IntentSuperposer:
    def generate(self, raw_input: str, context: dict | None = None) -> list[IntentCandidate]:
        if _is_simple(raw_input):
            return [IntentCandidate(text=raw_input, amplitude=1.0)]

        # Try LLM reframing (non-blocking, heuristic fallback on any failure)
        # TODO: replace heuristics with low-temp LLM sampling for production
        try:
            import asyncio, time
            start = time.monotonic()
            from engine.api import generate  # type: ignore
            loop = asyncio.new_event_loop()
            prompt = (
                f"Reframe this goal in one sentence, action-focused, no preamble:\n{raw_input}"
            )
            llm_text = loop.run_until_complete(
                asyncio.wait_for(generate(prompt, max_tokens=60), timeout=0.5)
            )
            loop.close()
            if llm_text and time.monotonic() - start < 0.5:
                return [
                    IntentCandidate(text=raw_input, amplitude=0.6),
                    IntentCandidate(text=llm_text.strip(), amplitude=0.8),
                    IntentCandidate(text=f"achieve: {raw_input}", amplitude=0.4),
                ]
        except Exception:
            pass

        return [
            IntentCandidate(text=raw_input, amplitude=0.6),
            IntentCandidate(text=_action_focused(raw_input), amplitude=0.5),
            IntentCandidate(text=f"achieve: {raw_input}", amplitude=0.4),
        ]

    def select(self, candidates: list[IntentCandidate]) -> IntentCandidate:
        return max(candidates, key=lambda c: c.amplitude)
