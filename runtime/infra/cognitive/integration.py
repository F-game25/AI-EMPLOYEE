"""Cognitive infrastructure integration and initialization.

Unified interface for:
- Coherence monitoring (contradictions, loops, dedup)
- Executive function (initiatives, workload, budget)
- Autonomy guardrails (spawn limits, trust tiers, escalation)
- Health checks and diagnostics
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CognitiveInfrastructure:
    """Unified cognitive infrastructure manager.

    Coordinates coherence, executive, and guardrail subsystems.
    Provides health checks, initialization, and shutdown.
    """

    def __init__(self):
        self._initialized = False
        self._coherence = None
        self._executive = None
        self._guardrails = None
        self._loop_detector = None
        self._exec_mgr = None
        self._workload = None

    async def initialize(self) -> None:
        """Initialize all cognitive subsystems.

        Starts background tasks:
        - Loop detector (detects autonomy cycles)
        - Initiative lifecycle manager
        - Workload balancer polling
        """
        if self._initialized:
            logger.debug("Cognitive infrastructure already initialized")
            return

        try:
            # Initialize coherence
            from .coherence import get_loop_detector
            self._loop_detector = get_loop_detector()

            # Initialize executive
            from .executive import get_initiative_manager, get_workload_balancer
            self._exec_mgr = get_initiative_manager()
            self._workload = get_workload_balancer()

            # Start background tasks
            import asyncio
            asyncio.create_task(self._loop_detector.start())
            asyncio.create_task(self._exec_mgr.start_lifecycle_loop())
            asyncio.create_task(self._workload.start())

            logger.info("Cognitive infrastructure initialized")
            self._initialized = True
        except Exception as e:
            logger.error(f"Cognitive infrastructure init failed: {e}")
            raise

    def shutdown(self) -> None:
        """Shutdown all background tasks."""
        try:
            if self._loop_detector:
                self._loop_detector.stop()
            if self._exec_mgr:
                self._exec_mgr.stop()
            if self._workload:
                self._workload.stop()
            logger.info("Cognitive infrastructure shutdown complete")
        except Exception as e:
            logger.error(f"Cognitive infrastructure shutdown error: {e}")

    def health(self) -> dict:
        """Return health status of all subsystems."""
        return {
            "initialized": self._initialized,
            "coherence": "ok" if self._loop_detector else "not_ready",
            "executive": "ok" if self._exec_mgr else "not_ready",
            "guardrails": "ok",  # guardrails are stateless
        }


# Global singleton
_instance: Optional[CognitiveInfrastructure] = None


def get_cognitive_infrastructure() -> CognitiveInfrastructure:
    """Get singleton cognitive infrastructure."""
    global _instance
    if _instance is None:
        _instance = CognitiveInfrastructure()
    return _instance


# ──────────────────────────────────────────────────────────────────────────
# Convenience functions for common operations
# ──────────────────────────────────────────────────────────────────────────


def record_cognitive_event(event_type: str, tenant_id: str, metadata: dict = None) -> None:
    """Record a cognitive event (contradiction, loop, duplicate)."""
    try:
        from .coherence import record_event
        record_event(event_type, tenant_id, metadata)
    except Exception as e:
        logger.debug(f"Record event failed: {e}")


def check_workflow_duplicate(workflow_type: str, input_keys: list, workflow_id: str, tenant_id: str) -> dict:
    """Check if workflow is duplicate and register if not."""
    try:
        from .coherence import check_or_register
        return check_or_register(workflow_type, input_keys, workflow_id, tenant_id)
    except Exception as e:
        logger.error(f"Workflow dedup check failed: {e}")
        return {"duplicate": False, "workflow_id": workflow_id}


def ingest_agent_result(agent_id: str, tenant_id: str, result: dict) -> None:
    """Ingest agent result for contradiction detection."""
    try:
        from .coherence import ingest_result
        ingest_result(agent_id, tenant_id, result)
    except Exception as e:
        logger.debug(f"Ingest result failed: {e}")


def detect_trigger_loop(source_agent: str, triggered_agent: str, tenant_id: str) -> bool:
    """Detect if agent trigger creates a loop."""
    try:
        from .coherence import get_loop_detector
        detector = get_loop_detector()
        return detector.add_trigger(source_agent, triggered_agent, tenant_id)
    except Exception as e:
        logger.error(f"Loop detection failed: {e}")
        return False


async def acquire_spawn_quota(tenant_id: str, agent_id: str) -> dict:
    """Acquire spawn quota for agent. Returns {blocked: bool, reason?: str}."""
    try:
        from .guardrails import acquire
        return await acquire(tenant_id, agent_id)
    except Exception as e:
        logger.error(f"Spawn quota failed: {e}")
        return {"blocked": True, "reason": "quota_check_error"}


async def release_spawn_quota(tenant_id: str, agent_id: str) -> None:
    """Release spawn quota when agent completes."""
    try:
        from .guardrails import release
        await release(tenant_id, agent_id)
    except Exception as e:
        logger.debug(f"Release quota failed: {e}")


def check_action_escalation(agent_id: str, action_type: str, tenant_id: str = "system") -> bool:
    """Check if action requires human-in-the-loop escalation."""
    try:
        from .guardrails import should_escalate
        return should_escalate(agent_id, action_type, tenant_id)
    except Exception as e:
        logger.error(f"Escalation check failed: {e}")
        return False


def record_token_usage(tenant_id: str, tokens: int) -> None:
    """Record token usage against daily budget."""
    try:
        from .executive import record_usage
        record_usage(tenant_id, tokens)
    except Exception as e:
        logger.debug(f"Record token usage failed: {e}")


def check_token_budget(tenant_id: str) -> bool:
    """Check if tenant has remaining token budget."""
    try:
        from .guardrails import enforce
        return enforce(tenant_id)
    except Exception as e:
        logger.error(f"Budget check failed: {e}")
        return False


def get_coherence_score(tenant_id: str) -> dict:
    """Get composite coherence score for tenant."""
    try:
        from .coherence import get_coherence_scorer
        scorer = get_coherence_scorer()
        score = scorer.compute(tenant_id)
        import dataclasses
        return dataclasses.asdict(score)
    except Exception as e:
        logger.error(f"Coherence score failed: {e}")
        return {
            "tenant_id": tenant_id,
            "overall": 100.0,
            "consistency_score": 100.0,
            "dedup_score": 100.0,
            "loop_free_score": 100.0,
        }


async def trigger_strategic_planning(tenant_id: str) -> Optional[dict]:
    """Trigger strategic planning for tenant."""
    try:
        from .executive import plan_next
        decision = await plan_next(tenant_id)
        if decision:
            import dataclasses
            return dataclasses.asdict(decision)
    except Exception as e:
        logger.error(f"Strategic planning failed: {e}")
    return None
