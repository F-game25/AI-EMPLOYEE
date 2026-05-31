"""
Phase 4 Import Validation Tests

Ensures all Phase 4 modules can be imported without errors.
This is a fast smoke test to verify module structure integrity.
"""
import sys
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))


def test_learning_imports():
    """Test all learning module imports."""
    from infra.cognitive.learning import (
        get_outcome_tracker,
        get_reinforcement_engine,
        record,
        get_recent,
        compute,
        generate_suggestions,
        list_suggestions,
        accept,
        record_ordering,
        get_preferences,
        OutcomeRecord,
        RoutingAdjustment,
        EffectivenessScore,
    )
    assert get_outcome_tracker is not None
    assert get_reinforcement_engine is not None


def test_teammate_imports():
    """Test all teammate module imports."""
    from infra.cognitive.teammate import (
        get_identity_manager,
        get_proactive_engine,
        get_or_create,
        increment_interaction,
        update_persona,
        list_insights,
        dismiss,
        record,
        get_context,
        record_event,
        get_habits,
        get_profile,
        update_from_response,
        TeammateIdentity,
        HabitPattern,
        ProactiveInsight,
    )
    assert get_identity_manager is not None
    assert get_proactive_engine is not None


def test_temporal_imports():
    """Test all temporal module imports."""
    from infra.cognitive.temporal import (
        get_deadline_tracker,
        compute_urgency,
        create,
        list_upcoming,
        store_cycle,
        get_cycles,
        create_schedule,
        get_schedule,
        Deadline,
        UrgencyScore,
        OperationalCycle,
    )
    assert get_deadline_tracker is not None
    assert compute_urgency is not None


def test_router_imports():
    """Test that all routers can be imported."""
    from infra.cognitive.learning.learning_routes import router as learning_router
    from infra.cognitive.teammate.teammate_routes import router as teammate_router
    from infra.cognitive.temporal.temporal_routes import router as temporal_router

    assert learning_router is not None
    assert teammate_router is not None
    assert temporal_router is not None


def test_phase4_router_import():
    """Test that Phase 4 aggregator router can be imported."""
    from infra.api.phase4_routes import phase4_router

    assert phase4_router is not None
    assert hasattr(phase4_router, 'routes')
    assert len(phase4_router.routes) > 0


def test_database_import():
    """Test database module can be imported."""
    from infra.cognitive.db import cognitive_conn

    assert cognitive_conn is not None


def test_schema_classes():
    """Test that all schema classes instantiate correctly."""
    from infra.cognitive.learning.schema import (
        OutcomeRecord,
        RoutingAdjustment,
        EffectivenessScore,
    )
    from infra.cognitive.teammate.schema import (
        TeammateIdentity,
        HabitPattern,
        ProactiveInsight,
    )
    from infra.cognitive.temporal.schema import (
        Deadline,
        UrgencyScore,
        OperationalCycle,
    )
    import time

    # Learning
    outcome = OutcomeRecord(
        workflow_id="test",
        agent_id="test",
        tenant_id="test",
        success=True,
        quality_score=0.8,
        duration_ms=1000.0,
    )
    assert outcome.workflow_id == "test"

    routing = RoutingAdjustment(
        task_type="test",
        from_agent="a",
        to_agent="b",
        tenant_id="test",
        confidence=0.8,
        sample_size=50,
        quality_delta=0.2,
    )
    assert routing.confidence == 0.8

    eff = EffectivenessScore(
        agent_id="test",
        tenant_id="test",
        score=0.85,
        sample_count=50,
        trend="improving",
    )
    assert eff.score == 0.85

    # Teammate
    identity = TeammateIdentity(tenant_id="test")
    assert identity.name == "Aeternus"

    habit = HabitPattern(
        user_id="test",
        tenant_id="test",
        workflow_type="test",
        typical_hour=14,
        frequency=3,
        confidence=0.8,
    )
    assert habit.confidence == 0.8

    insight = ProactiveInsight(
        tenant_id="test",
        title="Test",
        body="Test body",
        insight_type="anomaly",
    )
    assert insight.insight_type == "anomaly"

    # Temporal
    deadline = Deadline(
        initiative_id="test",
        tenant_id="test",
        deadline_ts=time.time() + 3600,
    )
    assert deadline.status == "pending"

    urgency = UrgencyScore(
        initiative_id="test",
        base_priority=5,
        time_remaining_s=3600,
        urgency=50.0,
    )
    assert urgency.urgency == 50.0

    cycle = OperationalCycle(
        workflow_type="test",
        tenant_id="test",
        period_days=7,
        confidence=0.8,
        last_peak=time.time(),
    )
    assert cycle.period_days == 7


if __name__ == "__main__":
    test_learning_imports()
    test_teammate_imports()
    test_temporal_imports()
    test_router_imports()
    test_phase4_router_import()
    test_database_import()
    test_schema_classes()
    print("✅ All Phase 4 imports verified successfully!")
