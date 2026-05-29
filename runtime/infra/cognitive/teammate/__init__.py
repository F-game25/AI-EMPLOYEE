from .identity_manager import get_identity_manager, get_or_create, increment_interaction, update_persona
from .proactive_engine import get_proactive_engine, list_insights, dismiss
from .relationship_memory import record, get_context
from .habit_recognizer import record_event, get_habits
from .communication_adapter import get_profile, update_from_response
from .schema import TeammateIdentity, HabitPattern, ProactiveInsight

__all__ = [
    "get_identity_manager",
    "get_proactive_engine",
    "get_or_create",
    "increment_interaction",
    "update_persona",
    "list_insights",
    "dismiss",
    "record",
    "get_context",
    "record_event",
    "get_habits",
    "get_profile",
    "update_from_response",
    "TeammateIdentity",
    "HabitPattern",
    "ProactiveInsight",
]
