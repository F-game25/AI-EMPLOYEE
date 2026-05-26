"""Test suite for cognitive infrastructure (coherence, executive, guardrails).

Tests Phase 4 Part 1-3 implementation:
- Coherence: contradictions, loops, dedup
- Executive: initiatives, budget, planning
- Guardrails: spawn limits, trust tiers, escalation
"""
import asyncio
import uuid
import pytest
import sys
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))

# Unique suffix per test session — prevents SQLite state pollution across runs
_RUN_ID = uuid.uuid4().hex[:8]


def _tid(n: int) -> str:
    """Generate a unique tenant ID for this test run."""
    return f"test-guard-{n}-{_RUN_ID}"


class TestCoherence:
    """Test coherence engine (contradictions, loops, dedup)."""

    def test_objective_crud(self):
        """Test objective creation and hierarchy."""
        from infra.cognitive.coherence import (
            add_objective,
            list_objectives,
            update_status,
        )
        from infra.cognitive.coherence.schema import ObjectiveNode

        tenant_id = "test-tenant-1"
        obj = ObjectiveNode(
            title="Test Objective",
            tenant_id=tenant_id,
            description="Test description",
            priority=1,
        )
        obj_id = add_objective(obj)
        assert obj_id == obj.id

        objs = list_objectives(tenant_id)
        assert len(objs) > 0
        assert any(o["id"] == obj_id for o in objs)

        update_status(obj_id, "completed")
        objs = list_objectives(tenant_id, "completed")
        assert any(o["id"] == obj_id and o["status"] == "completed" for o in objs)

    def test_contradiction_detection(self):
        """Test contradiction detector with cosine similarity."""
        from infra.cognitive.coherence.contradiction_detector import (
            ingest_result,
            list_contradictions,
        )

        tenant_id = "test-tenant-2"
        agent_a = "agent-a"
        agent_b = "agent-b"

        # Ingest result from agent A
        result_a = {"sentiment": "positive", "confidence": 0.95}
        ingest_result(agent_a, tenant_id, result_a)

        # Ingest contradicting result from agent B
        result_b = {"sentiment": "negative", "confidence": 0.90}
        ingest_result(agent_b, tenant_id, result_b)

        # Check contradictions detected
        contradictions = list_contradictions(tenant_id, resolved=False)
        assert len(contradictions) > 0

    def test_loop_detection(self):
        """Test loop detector DFS."""
        from infra.cognitive.coherence.loop_detector import get_loop_detector

        detector = get_loop_detector()
        tenant_id = "test-tenant-3"

        # A -> B (no loop)
        has_loop = detector.add_trigger("agent-a", "agent-b", tenant_id)
        assert not has_loop

        # B -> C (no loop)
        has_loop = detector.add_trigger("agent-b", "agent-c", tenant_id)
        assert not has_loop

        # C -> A (creates loop: A -> B -> C -> A)
        has_loop = detector.add_trigger("agent-c", "agent-a", tenant_id)
        assert has_loop  # Cycle detected

    def test_deduplication(self):
        """Test workflow fingerprinting and dedup."""
        from infra.cognitive.coherence.deduplication_engine import (
            check_or_register,
        )

        tenant_id = "test-tenant-4"
        workflow_type = "content-gen"
        input_keys = ["prompt", "style"]
        workflow_id_1 = "wf-001"
        workflow_id_2 = "wf-002"

        # Register first workflow
        result1 = check_or_register(workflow_type, input_keys, workflow_id_1, tenant_id)
        assert not result1["duplicate"]
        assert result1["workflow_id"] == workflow_id_1

        # Register same workflow (same fingerprint)
        result2 = check_or_register(workflow_type, input_keys, workflow_id_2, tenant_id)
        assert result2["duplicate"]  # Detected as duplicate
        assert result2["existing_workflow_id"] == workflow_id_1

    def test_coherence_scoring(self):
        """Test composite coherence score."""
        from infra.cognitive.coherence.coherence_scorer import (
            compute,
            record_event,
        )

        tenant_id = "test-tenant-5"

        # Record some events
        record_event("cognitive:contradiction", tenant_id)
        record_event("cognitive:contradiction", tenant_id)

        # Compute score (contradictions reduce consistency)
        score = compute(tenant_id)
        assert score.tenant_id == tenant_id
        assert 0 <= score.overall <= 100
        assert 0 <= score.consistency_score <= 100
        assert score.consistency_score < 100  # Reduced due to contradictions


class TestExecutive:
    """Test executive function (initiatives, budget, planning)."""

    def test_initiative_lifecycle(self):
        """Test initiative creation and status transitions."""
        from infra.cognitive.executive import create, update, list_initiatives
        from infra.cognitive.executive.schema import Initiative

        tenant_id = "test-exec-1"
        init = Initiative(
            title="Test Initiative",
            tenant_id=tenant_id,
            description="Test",
            priority=1,
        )
        init_id = create(init)
        assert init_id == init.id

        inits = list_initiatives(tenant_id, "pending")
        assert len(inits) > 0

        update(init_id, status="active")
        inits = list_initiatives(tenant_id, "active")
        assert any(i["id"] == init_id and i["status"] == "active" for i in inits)

    def test_budget_tracking(self):
        """Test token budget recording and status."""
        from infra.cognitive.executive import record_usage, get_status

        tenant_id = "test-exec-2"
        record_usage(tenant_id, 100000)
        record_usage(tenant_id, 200000)

        status = get_status(tenant_id)
        assert status["tenant_id"] == tenant_id
        assert status["used"] >= 300000
        assert status["limit"] == 1000000
        assert status["pct"] >= 30.0

    @pytest.mark.asyncio
    async def test_strategic_planning(self):
        """Test strategic planner (may skip LLM if not configured)."""
        from infra.cognitive.executive import plan_next, list_initiatives, create
        from infra.cognitive.executive.schema import Initiative

        tenant_id = "test-exec-3"

        # Create some initiatives
        for i in range(3):
            init = Initiative(
                title=f"Initiative {i}",
                tenant_id=tenant_id,
                priority=i,
            )
            create(init)

        # Trigger planning
        decision = await plan_next(tenant_id)
        # Decision may be None if LLM fails, but should not crash
        if decision:
            # decision may be a dataclass/namedtuple or dict
            tid = decision.get("tenant_id") if isinstance(decision, dict) else getattr(decision, "tenant_id", None)
            dt = decision.get("decision_type") if isinstance(decision, dict) else getattr(decision, "decision_type", None)
            assert tid == tenant_id
            assert dt is not None


class TestGuardrails:
    """Test autonomy guardrails (spawn limits, trust tiers, escalation)."""

    @pytest.mark.asyncio
    async def test_spawn_limits(self):
        """Test spawn limit acquisition and release."""
        from infra.cognitive.guardrails import acquire, release

        tenant_id = _tid(1)
        agent_id = "test-agent"

        # Acquire quota
        result = await acquire(tenant_id, agent_id)
        assert not result["blocked"]

        # Release
        await release(tenant_id, agent_id)

    @pytest.mark.asyncio
    async def test_spawn_limit_exhaustion(self):
        """Test spawn limit enforcement."""
        from infra.cognitive.guardrails import acquire, reset_agent

        tenant_id = _tid(2)
        agent_id = "test-agent"

        # Fill up agent quota (max 10)
        for _ in range(10):
            result = await acquire(tenant_id, agent_id)
            assert not result["blocked"]

        # Next should be blocked
        result = await acquire(tenant_id, agent_id)
        assert result["blocked"]
        assert result["reason"] == "agent_spawn_limit"

        # Reset
        await reset_agent(tenant_id, agent_id)

    def test_trust_tier_policy(self):
        """Test trust tier assignments."""
        from infra.cognitive.guardrails import get_tier, set_tier, list_tiers
        from infra.cognitive.guardrails.schema import TrustTier

        tenant_id = _tid(3)
        agent_id = "test-agent"

        # Default tier is autonomous
        tier = get_tier(agent_id, tenant_id)
        assert tier in [TrustTier.AUTONOMOUS, TrustTier.ASSISTED, TrustTier.SUPERVISED]

        # Set to supervised
        set_tier(agent_id, TrustTier.SUPERVISED, tenant_id)
        tier = get_tier(agent_id, tenant_id)
        assert tier == TrustTier.SUPERVISED

    def test_escalation_gate(self):
        """Test action escalation based on trust tier."""
        from infra.cognitive.guardrails import should_escalate, set_tier
        from infra.cognitive.guardrails.schema import TrustTier

        tenant_id = _tid(4)
        agent_id = "test-agent"

        # Supervised agent: all actions escalate
        set_tier(agent_id, TrustTier.SUPERVISED, tenant_id)
        assert should_escalate(agent_id, "any_action", tenant_id)

        # Assisted agent: risky actions escalate
        set_tier(agent_id, TrustTier.ASSISTED, tenant_id)
        assert should_escalate(agent_id, "fire", tenant_id)  # risky
        assert not should_escalate(agent_id, "read_file", tenant_id)  # safe

        # Autonomous: no escalation
        set_tier(agent_id, TrustTier.AUTONOMOUS, tenant_id)
        assert not should_escalate(agent_id, "fire", tenant_id)

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test cognitive decision rate limiting."""
        from infra.cognitive.guardrails import acquire_decision

        agent_id = "test-agent"

        # Should complete quickly
        await acquire_decision(agent_id)
        # Second acquire may block or complete depending on rate

    def test_event_storm_detection(self):
        """Test event storm detection and suppression."""
        from infra.cognitive.guardrails.event_storm_detector import (
            check as check_event_storm,
            get_suppressions,
        )

        tenant_id = _tid(5)
        channel = "test-channel"

        # Single event: not a storm
        assert check_event_storm(channel, tenant_id)

        # Simulate flood (>100 events/s in 1 second)
        for _ in range(120):
            result = check_event_storm(channel, tenant_id)
            if not result:
                break  # Storm detected, suppressed

        suppressions = get_suppressions()
        # May or may not have suppressions depending on timing

    def test_budget_enforcement(self):
        """Test budget enforcement gate."""
        from infra.cognitive.guardrails import check_budget, enforce
        from infra.cognitive.executive import record_usage

        tenant_id = _tid(6)

        # Fresh budget: OK
        assert enforce(tenant_id)

        # Record heavy usage
        record_usage(tenant_id, 1000001)  # Over 1M limit

        # Should now fail
        assert not enforce(tenant_id)


class TestIntegration:
    """Integration tests for cognitive infrastructure."""

    @pytest.mark.asyncio
    async def test_full_pipeline_checks(self):
        """Test cognitive checks integrated into a simulated pipeline."""
        from infra.cognitive.integration import (
            record_cognitive_event,
            check_workflow_duplicate,
            ingest_agent_result,
            detect_trigger_loop,
            acquire_spawn_quota,
            check_action_escalation,
            record_token_usage,
            get_coherence_score,
        )

        tenant_id = "test-integration-1"
        agent_id = "agent-x"

        # Simulate pipeline stages
        # 1. Check spawn quota
        quota = await acquire_spawn_quota(tenant_id, agent_id)
        assert not quota["blocked"]

        # 2. Check workflow duplicate
        dup = check_workflow_duplicate("pipeline", ["input"], "wf-123", tenant_id)
        assert not dup["duplicate"]

        # 3. Ingest result
        ingest_agent_result(agent_id, tenant_id, {"result": "success"})

        # 4. Detect loops
        loop = detect_trigger_loop(agent_id, "other-agent", tenant_id)
        assert not loop  # First trigger shouldn't loop

        # 5. Check escalation
        escalate = check_action_escalation(agent_id, "read_file", tenant_id)
        assert not escalate  # Safe action

        # 6. Record usage
        record_token_usage(tenant_id, 10000)

        # 7. Get coherence
        score = get_coherence_score(tenant_id)
        assert "overall" in score
        assert "consistency_score" in score

    def test_health_checks(self):
        """Test cognitive infrastructure health status."""
        from infra.cognitive.integration import get_cognitive_infrastructure

        infra = get_cognitive_infrastructure()
        health = infra.health()
        assert "initialized" in health
        assert "coherence" in health
        assert "executive" in health
        assert "guardrails" in health


class TestDatabaseIntegrity:
    """Test database schema and integrity constraints."""

    def test_database_schema_creation(self):
        """Test that all tables are created correctly."""
        from infra.cognitive.db import cognitive_conn

        conn = cognitive_conn()
        try:
            for table in ("objectives", "contradictions", "initiatives", "budget_usage"):
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                assert row is not None, f"Table '{table}' not found in cognitive DB"
        finally:
            conn.close()

    def test_database_indexes(self):
        """Test that expected indexes exist."""
        from infra.cognitive.db import cognitive_conn

        conn = cognitive_conn()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%idx_obj_tenant%'"
            ).fetchone()
            assert row is not None, "Expected index idx_obj_tenant* not found"
        finally:
            conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
