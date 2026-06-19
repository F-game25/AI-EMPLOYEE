"""Business Swarm Layer (Master Plan V3 — Module 7).

Formalizes the real 59+ agent catalog into typed governance contracts and provides a
decompose → assign → parallel → aggregate flow with honest approval gating.
"""

from .agent_contracts import AgentContract
from .registry import BusinessSwarmRegistry, get_registry
from .swarm import BusinessSwarm, get_business_swarm

__all__ = [
    "AgentContract",
    "BusinessSwarmRegistry",
    "get_registry",
    "BusinessSwarm",
    "get_business_swarm",
]
