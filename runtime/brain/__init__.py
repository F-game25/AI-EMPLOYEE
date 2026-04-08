"""brain package — Central Neural Intelligence of AI Employee.

Public API:
    from brain.brain import get_brain

    brain = get_brain()
    action, conf = brain.get_action(state_tensor)
    brain.store_experience(state, action, reward, next_state)
"""

from .brain import Brain, get_brain  # noqa: F401

__all__ = ["Brain", "get_brain"]
