"""Candidate wrapper for the cognitive layer."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.quantum.search.schema import NormalizedSearchResult


@dataclass
class Candidate:
    result: NormalizedSearchResult
    oracle_score: float = 0.0
    amplitude: float = 0.0
    interference: str = 'none'   # 'constructive' | 'destructive' | 'none'
    why: str = ''


def from_results(results: list[NormalizedSearchResult]) -> list[Candidate]:
    return [Candidate(result=r, amplitude=r.amplitude) for r in results]
