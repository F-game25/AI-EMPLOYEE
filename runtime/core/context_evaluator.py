"""Context sufficiency evaluator.

Scores whether the system has enough existing context to answer/execute a
goal at high quality. If not, returns specific knowledge gaps that the
:class:`AutoResearchAgent` can use as targeted research queries.

Score: 0.0 = nothing relevant in memory; 1.0 = rich, redundant coverage.
``sufficient`` flips at ``min_score`` (default 0.6).
"""
from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "up", "out", "as", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "this",
    "that", "these", "those", "i", "you", "he", "she", "we", "they", "it", "me",
    "my", "your", "their", "our", "find", "show", "tell", "give", "get", "make",
    "list", "top", "best", "some", "any", "all", "no",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _STOPWORDS and len(t) > 2]


class ContextSufficiencyEvaluator:
    """Decide whether the system already knows enough about a goal."""

    def __init__(
        self,
        memory_router: Any,
        brain_graph: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        *,
        knowledge_store: Optional[Any] = None,
        min_score: float = 0.6,
    ) -> None:
        self._memory = memory_router
        self._graph = brain_graph
        self._llm = llm_client
        self._knowledge = knowledge_store
        self._min_score = float(min_score)
        # LLM-judgment cache: query → (judgment, ts)
        self._llm_cache: dict[str, tuple[dict, float]] = {}
        self._llm_cache_ttl = 300.0

    # ── public API ────────────────────────────────────────────────────────
    def evaluate(self, goal: str, *, min_score: Optional[float] = None) -> dict:
        threshold = float(min_score if min_score is not None else self._min_score)
        goal = (goal or "").strip()
        if not goal:
            return {"score": 0.0, "sufficient": False, "gaps": [], "memory_hits": 0, "graph_hits": 0}

        memories = self._safe_retrieve(goal, top_k=10)
        graph_hits = self._graph_hits(goal)
        knowledge_hits = self._knowledge_hits(goal)

        score = self._coverage_score(goal, memories, graph_hits, knowledge_hits)

        # Borderline → ask LLM (if available) for a tighter score + gap list
        gaps: list[str] = []
        if self._llm and (threshold - 0.10) < score < (threshold + 0.10):
            judgment = self._llm_assess(goal, memories)
            if judgment:
                score = float(judgment.get("score", score))
                gaps = list(judgment.get("gaps", []) or [])

        if not gaps:
            gaps = self._extract_keyword_gaps(goal, memories)

        return {
            "score": round(max(0.0, min(1.0, score)), 3),
            "sufficient": score >= threshold,
            "gaps": gaps[:5],
            "memory_hits": len(memories),
            "graph_hits": graph_hits,
            "knowledge_hits": knowledge_hits,
        }

    # ── scoring internals ─────────────────────────────────────────────────
    def _coverage_score(self, goal: str, memories: list[dict], graph_hits: int, knowledge_hits: int) -> float:
        if not memories and graph_hits == 0 and knowledge_hits == 0:
            return 0.0
        # Average relevance of top hits + log-scaled hit count
        scores = [float(m.get("_score") or 0.0) for m in memories]
        top = scores[0] if scores else 0.0
        avg = (sum(scores) / len(scores)) if scores else 0.0
        density = math.log10(1 + len(memories)) / math.log10(11)  # normalize 0..1 at 10 hits
        base = (0.5 * top) + (0.3 * avg) + (0.2 * density)
        # Graph + knowledge_store boosts
        if graph_hits > 0:
            base += 0.10
        if knowledge_hits > 0:
            base += 0.10
        # Token overlap floor: if zero goal tokens appear in any memory text, cap low
        if memories:
            goal_tokens = set(_tokens(goal))
            covered = 0
            for m in memories:
                txt = (m.get("text") or "").lower()
                if any(tok in txt for tok in goal_tokens):
                    covered += 1
            coverage_ratio = covered / max(len(memories), 1)
            base *= (0.5 + 0.5 * coverage_ratio)
        return float(base)

    def _safe_retrieve(self, query: str, *, top_k: int) -> list[dict]:
        try:
            return self._memory.retrieve(query, top_k=top_k) or []
        except Exception as e:
            logger.debug("memory retrieve failed: %s", e)
            return []

    def _graph_hits(self, goal: str) -> int:
        """Approximate graph match count by checking how many goal-token concepts exist."""
        if not self._graph or not getattr(self._graph, "available", False):
            return 0
        try:
            tokens = _tokens(goal)[:8]
            if not tokens:
                return 0
            # Use neighborhood with no seeds as a cheap "any concept in graph?" probe
            snap = self._graph.neighborhood(seed_ids=None, depth=1, limit=200)
            labels = {
                (n.get("label") or "").lower() for n in (snap.get("nodes") or []) if isinstance(n, dict)
            }
            return sum(1 for t in tokens if any(t in lab for lab in labels))
        except Exception as e:
            logger.debug("graph hits probe failed: %s", e)
            return 0

    def _knowledge_hits(self, goal: str) -> int:
        if not self._knowledge:
            return 0
        try:
            return len(self._knowledge.search_knowledge(goal) or [])
        except Exception:
            return 0

    def _extract_keyword_gaps(self, goal: str, memories: list[dict]) -> list[str]:
        goal_tokens = _tokens(goal)
        if not goal_tokens:
            return [goal]
        covered: set[str] = set()
        for m in memories:
            for t in _tokens(m.get("text") or ""):
                if t in goal_tokens:
                    covered.add(t)
        missing = [t for t in goal_tokens if t not in covered]
        if not missing:
            return [goal]
        # Pair missing tokens back with the goal for richer queries
        gaps = [f"{tok} {goal}".strip() for tok in missing[:3]]
        if goal not in gaps:
            gaps.insert(0, goal)
        return gaps[:5]

    # ── LLM judgment (optional) ───────────────────────────────────────────
    def _llm_assess(self, goal: str, memories: list[dict]) -> Optional[dict]:
        cached = self._llm_cache.get(goal)
        if cached and (time.time() - cached[1]) < self._llm_cache_ttl:
            return cached[0]

        try:
            snippets = "\n---\n".join(
                f"[{i + 1}] {(m.get('text') or '')[:500]}" for i, m in enumerate(memories[:6])
            ) or "(no memory snippets available)"
            prompt = (
                f"Goal: {goal}\n\n"
                f"Memory snippets:\n{snippets}\n\n"
                "Rate context sufficiency from 0.0 (nothing useful) to 1.0 (rich coverage). "
                "List 2-5 short, search-ready knowledge gaps (web-query style) needed to fully answer.\n"
                'Reply as JSON only: {"score": 0.0-1.0, "gaps": ["...", "..."]}'
            )
            resp = self._llm.complete(prompt=prompt, system="You are a precise context-sufficiency rater.")
            text = (resp.get("text") if isinstance(resp, dict) else str(resp)) or ""
            parsed = self._parse_json_blob(text)
            if parsed and "score" in parsed:
                judgment = {
                    "score": float(parsed.get("score", 0.0)),
                    "gaps": [str(g) for g in (parsed.get("gaps") or [])][:5],
                }
                self._llm_cache[goal] = (judgment, time.time())
                return judgment
        except Exception as e:
            logger.debug("LLM assessment failed: %s", e)
        return None

    @staticmethod
    def _parse_json_blob(text: str) -> Optional[dict]:
        import json
        text = (text or "").strip()
        # Tolerate fenced code blocks
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


_instance: Optional[ContextSufficiencyEvaluator] = None


def get_context_evaluator() -> ContextSufficiencyEvaluator:
    """Singleton accessor — lazy-wires memory router, brain graph, LLM, knowledge store."""
    global _instance
    if _instance is None:
        from memory.memory_router import get_memory_router
        try:
            from neural_brain.graph.brain_graph import BrainGraph
            from neural_brain.graph.neo4j_adapter import Neo4jAdapter
            graph: Optional[Any] = BrainGraph(Neo4jAdapter())
        except Exception:
            graph = None
        try:
            from core.orchestrator import get_llm_client
            llm: Optional[Any] = get_llm_client()
        except Exception:
            llm = None
        try:
            from core.knowledge_store import get_knowledge_store
            ks: Optional[Any] = get_knowledge_store()
        except Exception:
            ks = None
        _instance = ContextSufficiencyEvaluator(
            memory_router=get_memory_router(),
            brain_graph=graph,
            llm_client=llm,
            knowledge_store=ks,
        )
    return _instance
