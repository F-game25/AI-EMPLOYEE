"""Iterative amplitude amplification."""
from __future__ import annotations
from core.quantum.candidate import Candidate


class AmplitudeAmplifier:
    def amplify(self, candidates: list[Candidate], rounds: int) -> list[Candidate]:
        if not candidates:
            return candidates

        for _ in range(rounds):
            candidates.sort(key=lambda c: c.amplitude)
            n = len(candidates)
            top_cut = max(1, n // 4)
            bot_cut = max(1, n // 4)

            for c in candidates[-top_cut:]:
                c.amplitude = min(c.amplitude * 1.15, 1.0)
            for c in candidates[:bot_cut]:
                c.amplitude = max(c.amplitude * 0.85, 0.0)

        max_amp = max((c.amplitude for c in candidates), default=0.0)
        if max_amp > 0:
            for c in candidates:
                c.amplitude = c.amplitude / max_amp

        return candidates
