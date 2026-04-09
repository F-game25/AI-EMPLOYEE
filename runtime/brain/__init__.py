"""brain package — Central Neural Intelligence of AI Employee.

Public API:
    from brain.brain import get_brain
    from brain.intelligence import get_intelligence

    brain = get_brain()
    action, conf = brain.get_action(state_tensor)
    brain.store_experience(state, action, reward, next_state)

    intel = get_intelligence()
    context = intel.build_context("user:default", message)
    intel.on_exchange("user:default", user_msg, response, agent_id)
"""

try:
    from .brain import Brain, get_brain  # noqa: F401
    _BRAIN_AVAILABLE = True
except ImportError:
    _BRAIN_AVAILABLE = False  # torch not installed

from .intelligence import (  # noqa: F401
    IntelligenceCore,
    UserProfile,
    FeatureEncoder,
    get_intelligence,
    extract_facts_from_text,
)

__all__ = [
    "Brain", "get_brain",
    "IntelligenceCore", "UserProfile", "FeatureEncoder",
    "get_intelligence", "extract_facts_from_text",
]
