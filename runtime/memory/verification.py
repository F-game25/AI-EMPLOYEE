"""Memory verification engine — cross-reference, multi-source check, confidence scoring.

Used by AutoResearchAgent (and any caller producing factual claims) to decide
whether a claim should be auto-saved, queued for human review, or discarded.

Public API:
    get_engine() -> VerificationEngine
    VerificationEngine.verify(claim, sources=[], context=None) -> VerificationResult
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)


@dataclass
class CrossReference:
    source: str            # URL or memory id
    agrees: bool           # True if reference supports the claim
    score: float           # 0-1 strength of agreement/contradiction
    excerpt: str           # short excerpt (max 240 chars)


@dataclass
class VerificationResult:
    claim: str
    confidence: float                          # 0.0 - 1.0
    decision: str                              # 'auto_save' | 'pending_review' | 'discard'
    cross_references: List[CrossReference] = field(default_factory=list)
    contradictions: List[CrossReference] = field(default_factory=list)
    source_count: int = 0
    source_trust_avg: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'claim': self.claim,
            'confidence': self.confidence,
            'decision': self.decision,
            'cross_references': [asdict(c) for c in self.cross_references],
            'contradictions': [asdict(c) for c in self.contradictions],
            'source_count': self.source_count,
            'source_trust_avg': self.source_trust_avg,
            'reasoning': self.reasoning,
        }


# Thresholds (tunable per plan)
AUTO_SAVE_THRESHOLD = 0.7
PENDING_REVIEW_THRESHOLD = 0.4


class VerificationEngine:
    def __init__(self):
        self._adapter = None
        self._llm = None
        self._adapter_failed = False
        self._llm_failed = False

    # ── lazy dependencies ────────────────────────────────────────────
    def _get_adapter(self):
        if self._adapter is None and not self._adapter_failed:
            try:
                from memory.memory_adapter import get_adapter
                self._adapter = get_adapter()
            except Exception as e:
                log.warning(f"MemoryAdapter unavailable for verification: {e}")
                self._adapter_failed = True
        return self._adapter

    def _get_llm(self):
        if self._llm is None and not self._llm_failed:
            try:
                from core.orchestrator import LLMClient
                self._llm = LLMClient()
            except Exception as e:
                log.warning(f"LLMClient unavailable for verification: {e}")
                self._llm_failed = True
        return self._llm

    @staticmethod
    def _trust_for(source: str) -> float:
        try:
            from core.source_trust import trust_for_url
            return float(trust_for_url(source))
        except Exception:
            return 0.5

    # ── helpers ──────────────────────────────────────────────────────
    def _find_related_memories(self, claim: str, top_k: int = 5) -> List[Dict]:
        adapter = self._get_adapter()
        if not adapter:
            return []
        try:
            matches = adapter.search(claim, top_k=top_k)
            return [
                {'id': m.id, 'text': m.text, 'score': m.score, 'metadata': m.metadata}
                for m in matches
            ]
        except Exception as e:
            log.warning(f"Memory search failed during verification: {e}")
            return []

    def _classify_relationship(self, claim: str, related_text: str) -> Dict[str, Any]:
        """Classify if related_text supports/contradicts/is unrelated to claim.

        Returns {relationship, score, excerpt, reason}.
        Falls back to keyword-overlap heuristic when LLM is unavailable.
        """
        llm = self._get_llm()
        excerpt = (related_text or "")[:240]
        if not llm:
            claim_tokens = set(re.findall(r"\w+", (claim or "").lower()))
            text_tokens = set(re.findall(r"\w+", (related_text or "").lower()))
            if not claim_tokens:
                return {'relationship': 'unrelated', 'score': 0.0, 'excerpt': excerpt, 'reason': 'no llm, empty claim'}
            overlap = len(claim_tokens & text_tokens) / max(len(claim_tokens), 1)
            if overlap > 0.4:
                return {'relationship': 'supports', 'score': round(overlap, 3), 'excerpt': excerpt, 'reason': 'keyword overlap'}
            return {'relationship': 'unrelated', 'score': 0.0, 'excerpt': excerpt, 'reason': 'low keyword overlap'}

        prompt = (
            "Classify the relationship between a claim and a related memory.\n\n"
            f"CLAIM: {claim}\n\n"
            f"RELATED MEMORY: {(related_text or '')[:500]}\n\n"
            'Respond ONLY with strict JSON: '
            '{"relationship": "supports" or "contradicts" or "unrelated", '
            '"score": 0.0-1.0, "reason": "<short reason>"}'
        )
        try:
            response = llm.complete(
                prompt=prompt,
                system="You are a precise relationship classifier. Output only JSON.",
            )
            text = ""
            if isinstance(response, dict):
                text = response.get('output') or response.get('content') or ""
            else:
                text = str(response)
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                obj = json.loads(m.group(0))
                rel = obj.get('relationship', 'unrelated')
                if rel not in ('supports', 'contradicts', 'unrelated'):
                    rel = 'unrelated'
                score = float(obj.get('score', 0.0))
                return {
                    'relationship': rel,
                    'score': max(0.0, min(1.0, score)),
                    'excerpt': excerpt,
                    'reason': str(obj.get('reason', ''))[:200],
                }
        except Exception as e:
            log.warning(f"LLM classification failed: {e}")
        return {'relationship': 'unrelated', 'score': 0.0, 'excerpt': excerpt, 'reason': 'classifier fallback'}

    # ── main entry point ─────────────────────────────────────────────
    def verify(self, claim: str, sources: Optional[List[str]] = None,
               context: Optional[Dict] = None) -> VerificationResult:
        """Verify a claim and return a structured VerificationResult."""
        sources = sources or []
        result = VerificationResult(claim=claim, confidence=0.5, decision='pending_review')

        # 1. Source diversity + trust averaging
        unique_domains = set()
        trust_scores = []
        for s in sources:
            try:
                domain = urlparse(s).netloc or s
                unique_domains.add(domain)
                trust_scores.append(self._trust_for(s))
            except Exception:
                pass
        result.source_count = len(unique_domains)
        result.source_trust_avg = round(
            sum(trust_scores) / len(trust_scores) if trust_scores else 0.5, 3
        )

        # 2. Cross-reference with existing memories (skip if claim is empty)
        if claim and claim.strip():
            related = self._find_related_memories(claim, top_k=5)
            for rel in related:
                classification = self._classify_relationship(claim, rel.get('text', ''))
                cr = CrossReference(
                    source=rel.get('id', ''),
                    agrees=classification['relationship'] == 'supports',
                    score=classification.get('score', 0.0),
                    excerpt=classification.get('excerpt', '')[:240],
                )
                if classification['relationship'] == 'supports':
                    result.cross_references.append(cr)
                elif classification['relationship'] == 'contradicts':
                    result.contradictions.append(cr)

        # 3. Compute confidence
        # Base from source diversity + trust
        base = min(1.0, (result.source_count * 0.25) + (result.source_trust_avg * 0.5))
        # Boost for supporting cross-references
        support_boost = min(0.25, len(result.cross_references) * 0.08)
        # Penalty for contradictions
        contradict_penalty = min(0.5, len(result.contradictions) * 0.25)
        # Hard cap when a contradiction is strong (score >= 0.7)
        hard_cap = any(cr.score >= 0.7 for cr in result.contradictions)

        confidence = base + support_boost - contradict_penalty
        if hard_cap:
            confidence = min(confidence, 0.5)
        confidence = max(0.0, min(1.0, confidence))
        result.confidence = round(confidence, 3)

        # 4. Decide
        if result.confidence >= AUTO_SAVE_THRESHOLD:
            result.decision = 'auto_save'
        elif result.confidence >= PENDING_REVIEW_THRESHOLD:
            result.decision = 'pending_review'
        else:
            result.decision = 'discard'

        # 5. Reasoning summary
        parts = [
            f"{result.source_count} unique source(s)",
            f"trust avg {result.source_trust_avg:.2f}",
            f"{len(result.cross_references)} supporting memory match(es)",
            f"{len(result.contradictions)} contradiction(s)",
        ]
        if hard_cap:
            parts.append("HARD CAP triggered by strong contradiction")
        result.reasoning = " · ".join(parts)
        return result


_singleton: Optional[VerificationEngine] = None


def get_engine() -> VerificationEngine:
    global _singleton
    if _singleton is None:
        _singleton = VerificationEngine()
    return _singleton
