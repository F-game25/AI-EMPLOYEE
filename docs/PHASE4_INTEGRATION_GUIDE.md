# Phase 4 Integration Guide: Using Cognitive Infrastructure in Your Code

This guide shows how to integrate resilience, observability, and scale features into agent workflows and core services.

---

## Pattern 1: Wrapping Agent Execution with Resilience + Observability

**Scenario**: Execute an agent with automatic failure recovery, span tracing, and anomaly detection.

```python
import asyncio
from uuid import uuid4
from runtime.infra.cognitive.resilience import (
    get_subsystem_isolator,
    get_adaptive_throttler,
    get_event_prioritizer,
)
from runtime.infra.cognitive.resilience.schema import EventTier
from runtime.infra.cognitive.observability import get_tracer
from runtime.core.bus import get_message_bus

async def execute_agent_with_resilience(agent_id: str, task: dict, tenant_id: str):
    """Execute agent with automatic recovery, span tracing, and load management."""
    
    # 1. Set up observability
    trace_id = str(uuid4())
    tracer = get_tracer()
    span = tracer.start_span(trace_id, f"agent_execute:{agent_id}", tenant_id)
    
    try:
        # 2. Check system load (adaptive throttling)
        throttler = get_adaptive_throttler()
        if throttler.should_throttle("p1"):
            # System is under load; defer non-critical tasks
            logger.warning(f"System throttled, deferring agent {agent_id}")
            await asyncio.sleep(1)
        
        # 3. Wrap execution in subsystem isolator (automatic restart on failure)
        isolator = get_subsystem_isolator()
        
        async def run_agent():
            # Create child span for agent work
            agent_span = tracer.start_span(
                trace_id,
                f"agent_logic:{agent_id}",
                tenant_id,
                parent_span_id=span.id
            )
            try:
                # Actually run the agent
                result = await agent_main(agent_id, task)
                tracer.end_span(agent_span.id, status="success")
                return result
            except Exception as e:
                tracer.end_span(agent_span.id, status="error", error_message=str(e))
                raise
        
        await isolator.run_isolated(f"agent_{agent_id}", run_agent)
        result = await run_agent()
        
        # 4. Publish completion event with priority queuing
        prioritizer = get_event_prioritizer()
        await prioritizer.enqueue(EventTier.P1, {
            "event": "agent_completed",
            "agent_id": agent_id,
            "task_id": task.get("id"),
            "status": "success",
            "trace_id": trace_id,
        })
        
        # 5. End root span
        tracer.end_span(span.id, status="success")
        
        return result
    
    except Exception as e:
        # Log anomaly for correlation
        from runtime.infra.cognitive.observability import get_anomaly_correlator
        correlator = get_anomaly_correlator()
        correlator.record_anomaly(
            anomaly_id=str(uuid4()),
            tenant_id=tenant_id,
            subsystem_id=f"agent_{agent_id}",
            error_message=str(e),
        )
        
        tracer.end_span(span.id, status="error", error_message=str(e))
        
        # Publish error event with high priority
        prioritizer = get_event_prioritizer()
        await prioritizer.enqueue(EventTier.P0, {
            "event": "agent_failed",
            "agent_id": agent_id,
            "error": str(e),
            "trace_id": trace_id,
        })
        
        raise
```

---

## Pattern 2: Monitoring Task Queue with Backpressure

**Scenario**: Producer publishes tasks to a queue; consumer applies backpressure when queue fills.

```python
from runtime.infra.cognitive.resilience import get_backpressure_propagator
from runtime.core.bus import get_message_bus
import asyncio

class TaskConsumer:
    def __init__(self, subsystem_id: str):
        self.subsystem_id = subsystem_id
        self.task_queue = asyncio.Queue()
        self.propagator = get_backpressure_propagator()
    
    async def process_loop(self):
        """Main consumer loop with automatic backpressure."""
        while True:
            # 1. Check queue depth
            queue_depth = self.task_queue.qsize()
            
            # 2. Check and emit backpressure signal
            is_backpressured = self.propagator.check_and_emit(
                self.subsystem_id,
                queue_depth,
                queue_max=1000,
            )
            
            if is_backpressured:
                # Queue is full; reduce processing rate
                logger.warning(f"Queue backpressured: {queue_depth}/1000")
                await asyncio.sleep(2)
            else:
                # Normal processing
                try:
                    task = self.task_queue.get_nowait()
                    await self.process_task(task)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)
    
    async def process_task(self, task):
        # ... agent execution ...
        pass

class TaskProducer:
    def __init__(self):
        self.propagator = get_backpressure_propagator()
    
    async def enqueue_task(self, consumer: TaskConsumer, task: dict):
        """Publish task, respecting backpressure from consumer."""
        
        while True:
            if not self.propagator.is_backpressured(consumer.subsystem_id):
                # Consumer is ready; enqueue
                await consumer.task_queue.put(task)
                return
            else:
                # Consumer is backpressured; wait before retrying
                logger.info(f"Producer waiting for {consumer.subsystem_id} to drain")
                await asyncio.sleep(1)
```

---

## Pattern 3: Caching Expensive Computations

**Scenario**: Compute coherence scores (expensive LLM calls); cache results for 60s.

```python
from runtime.infra.cognitive.scale import get_adaptive_cache
from runtime.infra.cognitive.observability import get_heatmap_aggregator

async def compute_org_coherence(org_id: str, tenant_id: str) -> float:
    """
    Compute org coherence, using cache to avoid repeated LLM calls.
    """
    cache = get_adaptive_cache()
    heatmap = get_heatmap_aggregator()
    
    cache_key = f"coherence_score:{org_id}"
    
    # 1. Try cache first
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Cache hit for {cache_key}")
        return cached
    
    # 2. Cache miss; compute
    logger.debug(f"Cache miss for {cache_key}; computing...")
    score = await call_coherence_llm(org_id, tenant_id)
    
    # 3. Store in cache (LRU evicts oldest if full)
    cache.set(cache_key, score)
    
    # 4. Record execution in heatmap
    heatmap.record_execution(f"coherence_engine", action_type="llm_call")
    
    return score

# Usage:
score = await compute_org_coherence("org_123", "tenant_abc")
print(f"Coherence: {score}")

# Later, invalidate cache on org update:
cache = get_adaptive_cache()
cache.invalidate("coherence_score:org_123")
# Or invalidate all org caches:
cache.invalidate_pattern("coherence_score:org_*")
```

---

## Pattern 4: Handling High-Frequency Events

**Scenario**: Agents emit 100+ "task_completed" events per second; compress to reduce load.

```python
from runtime.infra.cognitive.scale import get_event_compressor
from runtime.infra.cognitive.resilience import get_event_prioritizer
from runtime.infra.cognitive.resilience.schema import EventTier

class EventBatcher:
    def __init__(self):
        self.compressor = get_event_compressor()
        self.prioritizer = get_event_prioritizer()
    
    async def record_task_completion(self, task_id: str, agent_id: str):
        """Record task completion; auto-compress if event storm detected."""
        
        result = self.compressor.record_event(
            event_type="task_completed",
            agent_id=agent_id,
        )
        
        if result["compressed"]:
            # Event storm: 5+ events in 1 second → compressed
            logger.info(
                f"Compressed {result['count']} task_completed events from {agent_id}"
            )
            # Emit single event with count
            await self.prioritizer.enqueue(EventTier.P1, {
                "event": "task_completed_batch",
                "agent_id": agent_id,
                "count": result["count"],
                "period_s": result["period_s"],
            })
        else:
            # Normal event
            await self.prioritizer.enqueue(EventTier.P1, {
                "event": "task_completed",
                "task_id": task_id,
                "agent_id": agent_id,
            })

# Usage in agent main loop:
batcher = EventBatcher()
for task in completed_tasks:
    await batcher.record_task_completion(task["id"], "content_generator")
```

---

## Pattern 5: WebSocket Message Batching

**Scenario**: Dashboard subscribes to real-time updates; batch messages to avoid overwhelming network.

```python
from fastapi import WebSocket
from runtime.infra.cognitive.scale import get_ws_batcher
import json

class DashboardWebSocketHandler:
    def __init__(self):
        self.batcher = get_ws_batcher()
        self.active_ws = []
    
    async def send_update(self, update: dict):
        """Send update to all connected dashboards (batched)."""
        await self.batcher.enqueue_message(update)
    
    async def start_batch_flusher(self):
        """Background task to flush batched messages every 50ms."""
        async def flush_handler(batch: list[dict]):
            for ws in self.active_ws:
                try:
                    await ws.send_text(json.dumps({
                        "type": "batch_update",
                        "updates": batch,
                    }))
                except Exception:
                    # Connection closed; remove from active list
                    self.active_ws = [w for w in self.active_ws if w != ws]
        
        await self.batcher.start_auto_flush(flush_handler)
    
    async def handle_connection(self, websocket: WebSocket):
        await websocket.accept()
        self.active_ws.append(websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except Exception:
            self.active_ws.remove(websocket)

# Usage in FastAPI:
handler = DashboardWebSocketHandler()

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await handler.handle_connection(websocket)

# Somewhere else, publish updates:
await handler.send_update({
    "agent_id": "content_generator",
    "status": "idle",
    "tasks_completed": 142,
})
```

---

## Pattern 6: Tracing Complex Workflows

**Scenario**: A workflow spawns multiple child workflows; trace full lineage + reasoning steps.

```python
from uuid import uuid4
from runtime.infra.cognitive.observability import (
    get_tracer,
    get_lineage_tracker,
    get_reasoning_lineage_tracker,
)

async def execute_workflow(workflow_id: str, tenant_id: str, task: dict):
    """Execute workflow with full tracing and lineage."""
    
    trace_id = str(uuid4())
    tracer = get_tracer()
    lineage = get_lineage_tracker()
    reasoning = get_reasoning_lineage_tracker()
    
    # Root span
    root_span = tracer.start_span(trace_id, "workflow:main", tenant_id)
    
    try:
        # Step 1: Reasoning phase
        reasoning_span = tracer.start_span(
            trace_id,
            "phase:reasoning",
            tenant_id,
            parent_span_id=root_span.id,
        )
        reasoning.record_step(trace_id, 0, {
            "type": "intent_classification",
            "input": task["input"],
            "output": "intent: create_content",
            "duration_ms": 50,
        })
        reasoning.record_step(trace_id, 1, {
            "type": "plan_generation",
            "input": "intent: create_content",
            "output": "plan: [research, draft, edit]",
            "duration_ms": 120,
        })
        tracer.end_span(reasoning_span.id, status="success")
        
        # Step 2: Execution phase (spawn child workflows)
        exec_span = tracer.start_span(
            trace_id,
            "phase:execution",
            tenant_id,
            parent_span_id=root_span.id,
        )
        
        # Spawn research workflow
        research_wf_id = str(uuid4())
        lineage.record(workflow_id, research_wf_id, tenant_id)  # Parent → Child
        research_result = await execute_research_workflow(research_wf_id, tenant_id, task)
        
        # Spawn draft workflow
        draft_wf_id = str(uuid4())
        lineage.record(workflow_id, draft_wf_id, tenant_id)  # Parent → Child
        draft_result = await execute_draft_workflow(draft_wf_id, tenant_id, research_result)
        
        tracer.end_span(exec_span.id, status="success")
        
        # Step 3: Validation
        validation_span = tracer.start_span(
            trace_id,
            "phase:validation",
            tenant_id,
            parent_span_id=root_span.id,
        )
        is_valid = await validate_output(draft_result)
        tracer.end_span(validation_span.id, status="success")
        
        tracer.end_span(root_span.id, status="success")
        
        return draft_result
    
    except Exception as e:
        tracer.end_span(root_span.id, status="error", error_message=str(e))
        raise

# Later, retrieve full workflow trace:
tracer = get_tracer()
trace_tree = tracer.get_trace(trace_id, tenant_id)
# → Full span tree with durations, parent-child relationships, reasoning steps

lineage_tracker = get_lineage_tracker()
ancestors = lineage_tracker.get_ancestry(workflow_id, tenant_id)
descendants = lineage_tracker.get_descendants_tree(workflow_id, tenant_id)
# → Full workflow family tree
```

---

## Pattern 7: Detecting System-Wide Issues

**Scenario**: Multiple subsystems fail simultaneously; detect correlation and alert.

```python
from runtime.infra.cognitive.observability import get_anomaly_correlator
from runtime.infra.cognitive.resilience import get_event_prioritizer
from runtime.infra.cognitive.resilience.schema import EventTier

class AnomalyDetector:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.correlator = get_anomaly_correlator()
        self.prioritizer = get_event_prioritizer()
    
    async def record_failure(self, subsystem_id: str, error: str):
        """Record subsystem failure; auto-detect correlations."""
        
        correlation = self.correlator.record_anomaly(
            anomaly_id=str(uuid4()),
            tenant_id=self.tenant_id,
            subsystem_id=subsystem_id,
            error_message=error,
        )
        
        if correlation is not None:
            # Multiple subsystems failed within 60s → systemic issue
            logger.critical(
                f"SYSTEMIC ISSUE DETECTED: {len(correlation.affected_subsystems)} subsystems affected"
                f" (confidence: {correlation.confidence:.2f})"
            )
            logger.critical(f"Affected: {', '.join(correlation.affected_subsystems)}")
            
            # Escalate to P0 (healing action needed)
            await self.prioritizer.enqueue(EventTier.P0, {
                "event": "systemic_failure_detected",
                "correlation_id": correlation.id,
                "subsystems": correlation.affected_subsystems,
                "confidence": correlation.confidence,
                "action_needed": True,
            })

# Usage:
detector = AnomalyDetector("org_123")
try:
    await execute_neural_brain()
except Exception as e:
    await detector.record_failure("neural_brain", str(e))

try:
    await execute_task_executor()
except Exception as e:
    await detector.record_failure("task_executor", str(e))

# If both fail within 60s, correlation is detected and P0 alert fires
```

---

## Pattern 8: Scheduled Memory Compaction

**Scenario**: Weekly maintenance task to compact memories and rebuild indexes.

```python
from runtime.infra.cognitive.scale import get_memory_compactor
import asyncio

async def start_maintenance_loop():
    """Start weekly memory maintenance."""
    compactor = get_memory_compactor()
    
    # Start background loop (wakes up every 7 days)
    asyncio.create_task(compactor.start_weekly_compaction_loop())
    
    logger.info("Memory compaction loop started (weekly schedule)")

# Or trigger manually:
async def trigger_manual_compaction():
    compactor = get_memory_compactor()
    stats = await compactor.compact_memories()
    logger.info(f"Compaction completed: {stats}")
    # {compactions_run, memories_archived, memories_consolidated, tokens_saved_estimate}
```

---

## Pattern 9: Monitoring System Health

**Scenario**: Dashboard displays real-time system health (CPU, queue depths, cache hit rate).

```python
from fastapi import APIRouter
from runtime.infra.cognitive.resilience import (
    get_adaptive_throttler,
    get_backpressure_propagator,
    get_event_prioritizer,
)
from runtime.infra.cognitive.scale import get_adaptive_cache
from runtime.infra.cognitive.observability import get_anomaly_correlator

router = APIRouter()

@router.get("/system-health")
async def get_system_health():
    """Real-time system health snapshot."""
    
    throttler = get_adaptive_throttler()
    propagator = get_backpressure_propagator()
    prioritizer = get_event_prioritizer()
    cache = get_adaptive_cache()
    correlator = get_anomaly_correlator()
    
    return {
        "timestamp": time.time(),
        
        # System load
        "system_load": throttler.get_status(),
        
        # Queue health
        "queue_stats": prioritizer.get_stats(),
        
        # Backpressure
        "backpressured_subsystems": [
            subsys_id
            for subsys_id, state in propagator.get_all_states().items()
            if state.is_backpressured
        ],
        
        # Cache performance
        "cache_metrics": cache.get_metrics(),
        
        # Recent anomalies
        "recent_anomalies": correlator.get_correlations("all_tenants", limit=10),
    }

# Usage:
# curl http://localhost:8790/system-health | jq
# {
#   "timestamp": 1715607600.123,
#   "system_load": {"cpu_percent": 45.2, "degradation_level": "none"},
#   "queue_stats": {
#     "p0": {"total": 1234, "dropped": 0, "queue_size": 12},
#     ...
#   },
#   "cache_metrics": {"hits": 890, "misses": 110, "hit_rate": 0.89, ...}
# }
```

---

## Pattern 10: Emergency Mode Activation

**Scenario**: System approaching critical load; activate emergency mode (P0 only).

```python
from runtime.infra.cognitive.resilience import (
    get_adaptive_throttler,
    get_load_shedder,
    get_event_prioritizer,
)
from runtime.infra.cognitive.resilience.schema import DegradationLevel, EventTier

async def monitor_system_load():
    """Background task; activate emergency mode if needed."""
    throttler = get_adaptive_throttler()
    shedder = get_load_shedder()
    prioritizer = get_event_prioritizer()
    
    while True:
        await asyncio.sleep(5)
        
        status = throttler.get_status()
        degradation = DegradationLevel(status["degradation_level"])
        
        if degradation == DegradationLevel.CRITICAL:
            logger.critical("EMERGENCY MODE: Accepting P0 events only")
            
            # All P1-P3 events are now dropped
            queue_stats = prioritizer.get_stats()
            await prioritizer.enqueue(EventTier.P0, {
                "event": "emergency_mode_activated",
                "queue_stats": queue_stats,
                "action": "shed_p1_p2_p3",
            })

# Start monitoring at server startup:
asyncio.create_task(monitor_system_load())
```

---

## API Reference Quick Lookup

| Function | Import | Purpose |
|----------|--------|---------|
| `get_event_prioritizer()` | `runtime.infra.cognitive.resilience` | Priority queue management |
| `get_subsystem_isolator()` | `runtime.infra.cognitive.resilience` | Failure isolation + restart |
| `get_adaptive_throttler()` | `runtime.infra.cognitive.resilience` | Load-based throttling |
| `get_load_shedder()` | `runtime.infra.cognitive.resilience` | Queue depth-based shedding |
| `get_backpressure_propagator()` | `runtime.infra.cognitive.resilience` | Slow-down signaling |
| `get_tracer()` | `runtime.infra.cognitive.observability` | Span tracing |
| `get_lineage_tracker()` | `runtime.infra.cognitive.observability` | Workflow relationships |
| `get_reasoning_lineage_tracker()` | `runtime.infra.cognitive.observability` | Reasoning step tracking |
| `get_heatmap_aggregator()` | `runtime.infra.cognitive.observability` | 24×7 execution patterns |
| `get_anomaly_correlator()` | `runtime.infra.cognitive.observability` | Multi-subsystem anomalies |
| `get_adaptive_cache()` | `runtime.infra.cognitive.scale` | LRU result caching |
| `get_graph_partitioner()` | `runtime.infra.cognitive.scale` | Neo4j sharding |
| `get_memory_compactor()` | `runtime.infra.cognitive.scale` | Memory maintenance |
| `get_ws_batcher()` | `runtime.infra.cognitive.scale` | WebSocket message batching |
| `get_event_compressor()` | `runtime.infra.cognitive.scale` | Event deduplication |

---

## Best Practices

1. **Always use tenancy**: Pass `tenant_id` to all observability methods
2. **Span parent-child relationships**: Use `parent_span_id` to build hierarchies
3. **Cache invalidation**: Invalidate on data changes; use patterns for bulk ops
4. **Backpressure is bidirectional**: Producers must respect consumer backpressure
5. **Monitor the monitors**: Check `get_adaptive_cache().get_metrics()` regularly
6. **Priority queuing**: Use P0 for healing actions, P1 for agents, P2 for UI, P3 for logs
7. **Error context**: Include stack traces in `error_message` for debugging
8. **Batch updates**: Use WebSocket batcher for 100+ msg/s scenarios

---

## Troubleshooting

**"Span not found in trace"**
- Ensure span.id matches when calling `end_span()`

**"Backpressure never clears"**
- Check threshold_clear value (default 40% of queue_max)

**"Cache hit rate <50%"**
- TTL too short, or key cardinality too high; increase TTL or use pattern-based storage

**"Memory compaction hangs"**
- Check if memory_router is available; may timeout waiting

For more help, see `/docs/PHASE4_COGNITIVE_INFRASTRUCTURE.md`
