"""BusinessSwarmRegistry — holds all derived contracts; goal/capability matching."""

from __future__ import annotations

import re
from typing import Optional

from .agent_contracts import AgentContract
from .capability_profiles import build_contracts


class BusinessSwarmRegistry:
    """Read-only registry of AgentContracts derived from the real catalog."""

    def __init__(self, contracts: Optional[dict[str, AgentContract]] = None):
        self._contracts: dict[str, AgentContract] = contracts or build_contracts()

    # ── Lookups ──────────────────────────────────────────────────────────────
    def get(self, agent_id: str) -> Optional[AgentContract]:
        return self._contracts.get(agent_id)

    def all(self) -> list[AgentContract]:
        return list(self._contracts.values())

    def ids(self) -> list[str]:
        return list(self._contracts.keys())

    def by_category(self, category: str) -> list[AgentContract]:
        cat = category.lower()
        return [c for c in self._contracts.values() if c.category == cat]

    def by_capability(self, capability: str) -> list[AgentContract]:
        """Agents whose capabilities/role/category match the (sub)string `capability`."""
        needle = capability.lower().strip()
        if not needle:
            return []
        matches: list[AgentContract] = []
        for c in self._contracts.values():
            haystack = " ".join(
                [c.category, c.role.lower()] + [s.lower() for s in c.capabilities]
            )
            if needle in haystack or any(needle in cap.lower() for cap in c.capabilities):
                matches.append(c)
        return matches

    def _score(self, contract: AgentContract, tokens: set[str]) -> int:
        score = 0
        cap_text = " ".join(contract.capabilities).lower()
        role_text = contract.role.lower()
        for tok in tokens:
            if tok in cap_text:
                score += 2
            if tok in role_text:
                score += 1
            if tok == contract.category:
                score += 1
        return score

    def find_for_goal(self, goal: str) -> list[AgentContract]:
        """Rank contracts by keyword/capability overlap with `goal`. Best first."""
        tokens = {t for t in re.split(r"[^a-z0-9]+", goal.lower()) if len(t) > 2}
        if not tokens:
            return []
        scored = [(self._score(c, tokens), c) for c in self._contracts.values()]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda sc: (-sc[0], sc[1].id))
        return [c for _, c in scored]


_REGISTRY: Optional[BusinessSwarmRegistry] = None


def get_registry() -> BusinessSwarmRegistry:
    """Singleton accessor."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = BusinessSwarmRegistry()
    return _REGISTRY
