import logging
from agents.base import BaseAgent, _LegacyAgentWrapper

logger = logging.getLogger(__name__)
_ENTRY_POINTS = ('run', 'execute', 'process', 'handle', 'main')


def _detect_entry_point(obj):
    for name in _ENTRY_POINTS:
        if callable(getattr(obj, name, None)):
            return name
    return '__call__' if callable(obj) else None


def auto_wrap(agent_obj, agent_id: str = 'unknown'):
    """Return agent_obj unchanged if it's already a BaseAgent, else wrap it."""
    if isinstance(agent_obj, BaseAgent):
        return agent_obj
    entry = _detect_entry_point(agent_obj)
    if entry is None:
        logger.warning("auto_wrap: no entry point on %s, using 'run'", agent_id)
        entry = 'run'
    else:
        logger.debug("auto_wrap: %s entry=%s", agent_id, entry)
    return _LegacyAgentWrapper(agent_obj, agent_id, entry)
