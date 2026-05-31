"""
Test Phase 4 Cognitive Infrastructure
Tests for resilience, observability, and scale hardening modules
"""
import pytest
import asyncio
import time
from uuid import uuid4


class TestResilience:
    """Test operational resilience subsystem"""

    def test_event_prioritizer_creation(self):
        from runtime.infra.cognitive.resilience import get_event_prioritizer
        from runtime.infra.cognitive.resilience.schema import EventTier

        prioritizer = get_event_prioritizer()
        assert prioritizer is not None
        assert EventTier.P0.value in prioritizer.queues
        assert EventTier.P3.value in prioritizer.queues

    def test_event_prioritizer_enqueue(self):
        from runtime.infra.cognitive.resilience import get_event_prioritizer
        from runtime.infra.cognitive.resilience.schema import EventTier

        prioritizer = get_event_prioritizer()
        result = asyncio.run(prioritizer.enqueue(EventTier.P0, {"msg": "test"}))
        assert result is True

    def test_subsystem_isolator_creation(self):
        from runtime.infra.cognitive.resilience import get_subsystem_isolator

        isolator = get_subsystem_isolator()
        assert isolator is not None
        assert isolator.max_restarts == 5

    def test_subsystem_isolator_status(self):
        from runtime.infra.cognitive.resilience import get_subsystem_isolator

        isolator = get_subsystem_isolator()
        status = isolator.get_all_status()
        assert isinstance(status, dict)

    def test_adaptive_throttler_status(self):
        from runtime.infra.cognitive.resilience import get_adaptive_throttler

        throttler = get_adaptive_throttler()
        status = throttler.get_status()
        assert "cpu_percent" in status
        assert "mem_percent" in status
        assert "degradation_level" in status

    def test_load_shedder_creation(self):
        from runtime.infra.cognitive.resilience import get_load_shedder
        from runtime.infra.cognitive.resilience.schema import EventTier

        shedder = get_load_shedder()
        assert shedder is not None
        assert shedder.should_shed(EventTier.P3, 15000) is True
        assert shedder.should_shed(EventTier.P0, 150000) is False

    def test_backpressure_propagator_creation(self):
        from runtime.infra.cognitive.resilience import get_backpressure_propagator

        propagator = get_backpressure_propagator()
        assert propagator is not None
        assert len(propagator.get_all_states()) >= 0

    def test_backpressure_state_check(self):
        from runtime.infra.cognitive.resilience import get_backpressure_propagator

        propagator = get_backpressure_propagator()
        is_bp = propagator.check_and_emit("test_subsystem", 7000, 10000)
        assert isinstance(is_bp, bool)

    def test_backpressure_clear(self):
        from runtime.infra.cognitive.resilience import get_backpressure_propagator

        propagator = get_backpressure_propagator()
        propagator.check_and_emit("test_subsystem_2", 9000, 10000)
        is_bp = propagator.is_backpressured("test_subsystem_2")
        assert isinstance(is_bp, bool)

    def test_degradation_level_enum(self):
        from runtime.infra.cognitive.resilience.schema import DegradationLevel

        assert DegradationLevel.NONE.value == "none"
        assert DegradationLevel.LIGHT.value == "light"
        assert DegradationLevel.MODERATE.value == "moderate"
        assert DegradationLevel.SEVERE.value == "severe"
        assert DegradationLevel.CRITICAL.value == "critical"

    def test_event_tier_enum(self):
        from runtime.infra.cognitive.resilience.schema import EventTier

        assert EventTier.P0.value == "p0"
        assert EventTier.P1.value == "p1"
        assert EventTier.P2.value == "p2"
        assert EventTier.P3.value == "p3"


class TestObservability:
    """Test enterprise observability subsystem"""

    def test_distributed_tracer_creation(self):
        from runtime.infra.cognitive.observability import get_tracer

        tracer = get_tracer()
        assert tracer is not None

    def test_distributed_tracer_span_lifecycle(self):
        from runtime.infra.cognitive.observability import get_tracer

        tracer = get_tracer()
        trace_id = str(uuid4())
        tenant_id = "test_tenant"

        span = tracer.start_span(trace_id, "test_operation", tenant_id)
        assert span is not None
        assert span.trace_id == trace_id
        assert span.operation_name == "test_operation"
        assert span.status == "pending"

        tracer.end_span(span.id, "success")
        assert span.status == "success"
        assert span.duration_ms > 0

    def test_workflow_lineage_tracker_creation(self):
        from runtime.infra.cognitive.observability import get_lineage_tracker

        tracker = get_lineage_tracker()
        assert tracker is not None

    def test_workflow_lineage_record(self):
        from runtime.infra.cognitive.observability import get_lineage_tracker

        tracker = get_lineage_tracker()
        parent_id = str(uuid4())
        child_id = str(uuid4())
        tenant_id = "test_tenant"

        tracker.record(parent_id, child_id, tenant_id)
        ancestry = tracker.get_ancestry(child_id, tenant_id)
        assert isinstance(ancestry, list)

    def test_reasoning_lineage_tracker_creation(self):
        from runtime.infra.cognitive.observability import get_reasoning_lineage_tracker

        tracker = get_reasoning_lineage_tracker()
        assert tracker is not None

    def test_reasoning_lineage_record_step(self):
        from runtime.infra.cognitive.observability import get_reasoning_lineage_tracker

        tracker = get_reasoning_lineage_tracker()
        trace_id = str(uuid4())
        step_data = {
            "type": "inference",
            "input": "test input",
            "output": "test output",
            "duration_ms": 100,
            "timestamp": time.time(),
        }

        tracker.record_step(trace_id, 0, step_data)
        steps = tracker.get_trace(trace_id)
        assert len(steps) == 1
        assert steps[0]["type"] == "inference"

    def test_execution_heatmap_aggregator_creation(self):
        from runtime.infra.cognitive.observability import get_heatmap_aggregator

        aggregator = get_heatmap_aggregator()
        assert aggregator is not None

    def test_execution_heatmap_recording(self):
        from runtime.infra.cognitive.observability import get_heatmap_aggregator

        aggregator = get_heatmap_aggregator()
        agent_id = "test_agent"

        aggregator.record_execution(agent_id)
        heatmap = aggregator.get_heatmap(agent_id)
        assert isinstance(heatmap, dict)
        assert len(heatmap) == 24  # 24 hours

    def test_anomaly_correlator_creation(self):
        from runtime.infra.cognitive.observability import get_anomaly_correlator

        correlator = get_anomaly_correlator()
        assert correlator is not None

    def test_anomaly_correlator_single_anomaly(self):
        from runtime.infra.cognitive.observability import get_anomaly_correlator

        correlator = get_anomaly_correlator()
        anomaly_id = str(uuid4())
        tenant_id = "test_tenant"
        subsystem_id = "test_subsystem"

        result = correlator.record_anomaly(anomaly_id, tenant_id, subsystem_id)
        assert result is None  # Single anomaly, no correlation

    def test_anomaly_correlator_multiple_anomalies(self):
        from runtime.infra.cognitive.observability import get_anomaly_correlator

        correlator = get_anomaly_correlator()
        tenant_id = "test_tenant_2"

        anomaly_ids = [str(uuid4()) for _ in range(3)]
        subsystems = ["subsystem_a", "subsystem_b", "subsystem_c"]

        for anomaly_id, subsys in zip(anomaly_ids, subsystems):
            result = correlator.record_anomaly(anomaly_id, tenant_id, subsys)
            if result is not None:
                assert result.tenant_id == tenant_id
                break

    def test_span_schema(self):
        from runtime.infra.cognitive.observability.schema import Span

        span = Span(trace_id="trace123", operation_name="test_op")
        assert span.trace_id == "trace123"
        assert span.operation_name == "test_op"
        assert span.status == "pending"
        assert span.parent_span_id is None


class TestScale:
    """Test performance + scale hardening"""

    def test_adaptive_cache_creation(self):
        from runtime.infra.cognitive.scale import get_adaptive_cache

        cache = get_adaptive_cache()
        assert cache is not None
        assert cache.max_entries == 1000

    def test_adaptive_cache_set_get(self):
        from runtime.infra.cognitive.scale import get_adaptive_cache

        cache = get_adaptive_cache()
        cache.clear()

        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"

    def test_adaptive_cache_miss(self):
        from runtime.infra.cognitive.scale import get_adaptive_cache

        cache = get_adaptive_cache()
        cache.clear()

        result = cache.get("nonexistent")
        assert result is None

    def test_adaptive_cache_metrics(self):
        from runtime.infra.cognitive.scale import get_adaptive_cache

        cache = get_adaptive_cache()
        cache.clear()

        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("nonexistent")

        metrics = cache.get_metrics()
        assert "hits" in metrics
        assert "misses" in metrics
        assert "hit_rate" in metrics

    def test_graph_partitioner_creation(self):
        from runtime.infra.cognitive.scale import get_graph_partitioner

        partitioner = get_graph_partitioner()
        assert partitioner is not None
        assert partitioner.shard_node_limit == 50000

    def test_graph_partitioner_partition_key(self):
        from runtime.infra.cognitive.scale import get_graph_partitioner

        partitioner = get_graph_partitioner()
        shard_id = partitioner.partition_by_tenant_and_time("tenant1", "2025-01")
        assert "tenant1" in shard_id
        assert "2025-01" in shard_id

    def test_graph_partitioner_threshold(self):
        from runtime.infra.cognitive.scale import get_graph_partitioner

        partitioner = get_graph_partitioner()
        shard_id = partitioner.partition_by_tenant_and_time("tenant2", "2025-02")
        should_partition = partitioner.should_partition(shard_id, 60000)
        assert should_partition is True

    def test_memory_compactor_creation(self):
        from runtime.infra.cognitive.scale import get_memory_compactor

        compactor = get_memory_compactor()
        assert compactor is not None

    def test_memory_compactor_stats(self):
        from runtime.infra.cognitive.scale import get_memory_compactor

        compactor = get_memory_compactor()
        stats = compactor.get_stats()
        assert "compactions_run" in stats
        assert "memories_archived" in stats

    def test_ws_batcher_creation(self):
        from runtime.infra.cognitive.scale import get_ws_batcher

        batcher = get_ws_batcher()
        assert batcher is not None

    def test_ws_batcher_metrics(self):
        from runtime.infra.cognitive.scale import get_ws_batcher

        batcher = get_ws_batcher()
        metrics = batcher.get_metrics()
        assert "total_messages" in metrics
        assert "batches_sent" in metrics
        assert "pending_messages" in metrics

    def test_event_compressor_creation(self):
        from runtime.infra.cognitive.scale import get_event_compressor

        compressor = get_event_compressor()
        assert compressor is not None

    def test_event_compressor_single_event(self):
        from runtime.infra.cognitive.scale import get_event_compressor

        compressor = get_event_compressor()
        result = compressor.record_event("test_event", "agent1")
        assert result["type"] == "test_event"
        assert result["compressed"] is False

    def test_event_compressor_multiple_events(self):
        from runtime.infra.cognitive.scale import get_event_compressor

        compressor = get_event_compressor()
        for _ in range(6):
            result = compressor.record_event("rapid_event", "agent2")

        stats = compressor.get_stats()
        assert stats["original_event_count"] > 0

    def test_cache_metrics_schema(self):
        from runtime.infra.cognitive.scale.schema import CacheMetrics

        metrics = CacheMetrics(hits=100, misses=50)
        assert metrics.hit_rate == pytest.approx(0.666, rel=0.01)

    def test_compression_stats_schema(self):
        from runtime.infra.cognitive.scale.schema import CompressionStats

        stats = CompressionStats(original_event_count=100, compressed_event_count=20)
        assert stats.compression_ratio == pytest.approx(0.8, rel=0.01)


class TestIntegration:
    """Integration tests combining resilience, observability, and scale"""

    def test_resilience_observability_integration(self):
        from runtime.infra.cognitive.resilience import get_event_prioritizer, get_adaptive_throttler
        from runtime.infra.cognitive.observability import get_heatmap_aggregator

        prioritizer = get_event_prioritizer()
        throttler = get_adaptive_throttler()
        heatmap = get_heatmap_aggregator()

        throttler_status = throttler.get_status()
        prioritizer_stats = prioritizer.get_stats()
        heatmap_exists = heatmap is not None

        assert isinstance(throttler_status, dict)
        assert isinstance(prioritizer_stats, dict)
        assert heatmap_exists is True

    def test_scale_performance_integration(self):
        from runtime.infra.cognitive.scale import (
            get_adaptive_cache,
            get_event_compressor,
            get_ws_batcher,
        )

        cache = get_adaptive_cache()
        compressor = get_event_compressor()
        batcher = get_ws_batcher()

        cache_metrics = cache.get_metrics()
        compressor_stats = compressor.get_stats()
        batcher_metrics = batcher.get_metrics()

        assert "hit_rate" in cache_metrics
        assert "compression_ratio" in compressor_stats
        assert "pending_messages" in batcher_metrics

    def test_schema_dataclass_compatibility(self):
        from runtime.infra.cognitive.resilience.schema import (
            ResilienceEvent,
            BackpressureState,
        )
        from runtime.infra.cognitive.observability.schema import Span

        event = ResilienceEvent(
            tenant_id="tenant1",
            event_type="test_event",
            message="Test message",
        )
        assert event.tenant_id == "tenant1"

        state = BackpressureState(subsystem_id="subsys1", queue_depth=5000)
        assert state.queue_depth == 5000

        span = Span(trace_id="trace1", operation_name="op1")
        assert span.trace_id == "trace1"
