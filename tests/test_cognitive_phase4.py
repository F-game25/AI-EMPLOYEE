"""
Phase 4 Cognitive Infrastructure Tests — Parts 7-9

Tests for:
- Part 7: Continuous Learning System (outcome tracking, reinforcement, routing optimization)
- Part 8: AI Teammate Identity (identity, relationships, habits, communication, proactivity)
- Part 9: System-Wide Temporal Awareness (deadlines, urgency, cycles, scheduling)
"""
import sys
import os
import time
import pytest
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))

# PART 7: LEARNING SYSTEM TESTS
def test_outcome_tracker_schema():
    """Test OutcomeRecord schema."""
    from infra.cognitive.learning.schema import OutcomeRecord
    record = OutcomeRecord(
        workflow_id="wf-001",
        agent_id="agent-001",
        tenant_id="tenant-001",
        success=True,
        quality_score=0.85,
        duration_ms=1500.0,
        cost_tokens=100,
    )
    assert record.workflow_id == "wf-001"
    assert record.quality_score == 0.85
    assert record.success is True


def test_outcome_tracker_record():
    """Test outcome tracker recording."""
    from infra.cognitive.learning.outcome_tracker import record, get_recent
    from infra.cognitive.learning.schema import OutcomeRecord

    outcome = OutcomeRecord(
        workflow_id="wf-test-001",
        agent_id="agent-test",
        tenant_id="test-tenant",
        success=True,
        quality_score=0.9,
        duration_ms=1000.0,
        cost_tokens=50,
    )
    outcome_id = record(outcome)
    assert outcome_id == outcome.id

    # Retrieve and verify
    recent = get_recent("test-tenant", "agent-test", limit=10)
    assert len(recent) > 0
    assert recent[0]["workflow_id"] == "wf-test-001"


def test_reinforcement_engine():
    """Test reinforcement engine effectiveness computation."""
    from infra.cognitive.learning.reinforcement_engine import compute

    score = compute("test-agent", "test-tenant")
    assert score.agent_id == "test-agent"
    assert score.tenant_id == "test-tenant"
    assert 0.0 <= score.score <= 1.0
    assert score.trend in ["improving", "degrading", "stable"]


def test_routing_optimizer():
    """Test routing optimizer suggestion generation."""
    from infra.cognitive.learning.routing_optimizer import generate_suggestions, list_suggestions

    suggestions = generate_suggestions("test-tenant")
    assert isinstance(suggestions, list)

    # List suggestions
    listed = list_suggestions("test-tenant")
    assert isinstance(listed, list)


def test_strategy_optimizer():
    """Test strategy optimizer for sequencing."""
    from infra.cognitive.learning.strategy_optimizer import get_preferences

    prefs = get_preferences("test-tenant")
    assert isinstance(prefs, list)


# PART 8: TEAMMATE IDENTITY TESTS
def test_teammate_identity_schema():
    """Test TeammateIdentity schema."""
    from infra.cognitive.teammate.schema import TeammateIdentity

    identity = TeammateIdentity(
        tenant_id="tenant-001",
        name="Aeternus",
        persona_summary="Enterprise AI intelligence",
        expertise_areas=["planning", "execution", "monitoring"]
    )
    assert identity.name == "Aeternus"
    assert "planning" in identity.expertise_areas


def test_identity_manager():
    """Test identity manager get or create."""
    from infra.cognitive.teammate.identity_manager import get_or_create, increment_interaction

    identity = get_or_create("test-tenant-identity")
    assert identity.tenant_id == "test-tenant-identity"
    assert identity.name == "Aeternus"

    # Increment interaction
    increment_interaction("test-tenant-identity")
    updated = get_or_create("test-tenant-identity")
    assert updated.interaction_count == identity.interaction_count + 1


def test_relationship_memory():
    """Test relationship memory recording and retrieval."""
    from infra.cognitive.teammate.relationship_memory import record, get_context

    record("user-001", "test-tenant", "Discussed project roadmap", "planning")
    context = get_context("user-001", "test-tenant")

    assert context["user_id"] == "user-001"
    assert context["interaction_count"] >= 1
    assert len(context["recent"]) >= 0


def test_habit_recognizer():
    """Test habit pattern recognition."""
    from infra.cognitive.teammate.habit_recognizer import record_event, get_habits

    # Record multiple events
    for i in range(5):
        record_event("user-habit-test", "test-tenant", "reporting")

    habits = get_habits("user-habit-test", "test-tenant")
    assert isinstance(habits, list)


def test_communication_adapter():
    """Test communication profile adaptation."""
    from infra.cognitive.teammate.communication_adapter import get_profile, update_from_response

    # Update profile
    update_from_response("user-comm", "test-tenant", 50, True)
    profile = get_profile("user-comm", "test-tenant")

    assert profile["user_id"] == "user-comm"


def test_proactive_engine_schema():
    """Test ProactiveInsight schema."""
    from infra.cognitive.teammate.schema import ProactiveInsight

    insight = ProactiveInsight(
        tenant_id="test-tenant",
        user_id="user-001",
        title="Initiative blocked",
        body="Project X is waiting on approval",
        insight_type="blocked_initiative",
        priority=2,
    )
    assert insight.title == "Initiative blocked"
    assert insight.insight_type == "blocked_initiative"


def test_proactive_insights():
    """Test proactive insight listing."""
    from infra.cognitive.teammate.proactive_engine import list_insights, dismiss

    insights = list_insights("test-tenant")
    assert isinstance(insights, list)


# PART 9: TEMPORAL AWARENESS TESTS
def test_deadline_schema():
    """Test Deadline schema."""
    from infra.cognitive.temporal.schema import Deadline
    import time

    deadline = Deadline(
        initiative_id="init-001",
        tenant_id="test-tenant",
        deadline_ts=time.time() + 86400,
        priority=5,
    )
    assert deadline.initiative_id == "init-001"
    assert deadline.status == "pending"


def test_deadline_tracker():
    """Test deadline tracker creation and retrieval."""
    from infra.cognitive.temporal.deadline_tracker import create, list_upcoming
    from infra.cognitive.temporal.schema import Deadline
    import time

    deadline = Deadline(
        initiative_id="deadline-test",
        tenant_id="temporal-test-tenant",
        deadline_ts=time.time() + 3600,
    )
    deadline_id = create(deadline)
    assert deadline_id == deadline.id

    upcoming = list_upcoming("temporal-test-tenant", 24)
    assert isinstance(upcoming, list)


def test_urgency_engine():
    """Test urgency computation."""
    from infra.cognitive.temporal.urgency_engine import compute_urgency
    import time

    deadline_ts = time.time() + 86400
    urgency = compute_urgency("init-001", 5, deadline_ts)

    assert urgency.initiative_id == "init-001"
    assert 0.0 <= urgency.urgency <= 100.0


def test_urgency_decay():
    """Test that urgency increases as deadline approaches."""
    from infra.cognitive.temporal.urgency_engine import compute_urgency
    import time

    now = time.time()

    # Far in future
    far_urgency = compute_urgency("init-far", 5, now + 7 * 86400).urgency

    # Soon
    soon_urgency = compute_urgency("init-soon", 5, now + 3600).urgency

    assert soon_urgency > far_urgency, "Urgency should increase as deadline approaches"


def test_cycle_detector():
    """Test operational cycle detection."""
    from infra.cognitive.temporal.cycle_detector import get_cycles

    cycles = get_cycles("test-tenant")
    assert isinstance(cycles, list)


def test_scheduling_intelligence():
    """Test scheduling intelligence."""
    from infra.cognitive.temporal.scheduling_intelligence import get_schedule
    import time

    initiatives = [
        {
            "id": "init-1",
            "title": "Project A",
            "priority": 5,
            "deadline": time.time() + 86400,
        },
        {
            "id": "init-2",
            "title": "Project B",
            "priority": 3,
            "deadline": time.time() + 172800,
        },
    ]

    schedule = get_schedule(initiatives, "test-tenant")
    assert "schedule" in schedule
    assert isinstance(schedule["schedule"], list)
    assert schedule["count"] >= 0


# INTEGRATION TESTS
def test_learning_routes_import():
    """Test that learning routes can be imported."""
    from infra.cognitive.learning.learning_routes import router
    assert router is not None
    assert hasattr(router, 'routes')


def test_teammate_routes_import():
    """Test that teammate routes can be imported."""
    from infra.cognitive.teammate.teammate_routes import router
    assert router is not None
    assert hasattr(router, 'routes')


def test_temporal_routes_import():
    """Test that temporal routes can be imported."""
    from infra.cognitive.temporal.temporal_routes import router
    assert router is not None
    assert hasattr(router, 'routes')


def test_phase4_routes_integration():
    """Test that Phase 4 routes can be imported and used."""
    from infra.api.phase4_routes import phase4_router
    assert phase4_router is not None


def test_database_operations():
    """Test that database operations are functional."""
    from infra.cognitive.db import cognitive_conn

    # Test connection
    with cognitive_conn() as c:
        result = c.execute("SELECT 1").fetchone()
        assert result is not None


# SCHEMA VALIDATION TESTS
def test_routing_adjustment_schema():
    """Test RoutingAdjustment schema."""
    from infra.cognitive.learning.schema import RoutingAdjustment

    adjustment = RoutingAdjustment(
        task_type="general",
        from_agent="agent-a",
        to_agent="agent-b",
        tenant_id="test-tenant",
        confidence=0.85,
        sample_size=50,
        quality_delta=0.15,
    )
    assert adjustment.confidence == 0.85
    assert adjustment.quality_delta == 0.15


def test_effectiveness_score_schema():
    """Test EffectivenessScore schema."""
    from infra.cognitive.learning.schema import EffectivenessScore

    score = EffectivenessScore(
        agent_id="agent-001",
        tenant_id="test-tenant",
        score=0.82,
        sample_count=100,
        trend="improving",
    )
    assert score.score == 0.82
    assert score.trend == "improving"


def test_habit_pattern_schema():
    """Test HabitPattern schema."""
    from infra.cognitive.teammate.schema import HabitPattern

    habit = HabitPattern(
        user_id="user-001",
        tenant_id="test-tenant",
        workflow_type="reporting",
        typical_hour=14,
        frequency=3,
        confidence=0.85,
    )
    assert habit.workflow_type == "reporting"
    assert habit.confidence == 0.85


def test_operational_cycle_schema():
    """Test OperationalCycle schema."""
    from infra.cognitive.temporal.schema import OperationalCycle
    import time

    cycle = OperationalCycle(
        workflow_type="weekly_planning",
        tenant_id="test-tenant",
        period_days=7,
        confidence=0.8,
        last_peak=time.time(),
    )
    assert cycle.period_days == 7
    assert cycle.confidence == 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
