# Phase 4 API Reference

Quick lookup for all 12 cognitive infrastructure modules and their public APIs.

---

## PART 10: OPERATIONAL RESILIENCE

### 10.1 EventPrioritizer

**Module**: `runtime.infra.cognitive.resilience.event_prioritizer`

```python
from runtime.infra.cognitive.resilience import get_event_prioritizer
from runtime.infra.cognitive.resilience.schema import EventTier

prioritizer = get_event_prioritizer()

# Enqueue event at priority tier
result: bool = await prioritizer.enqueue(EventTier.P0, event: Any) -> bool

# Process queues with degradation awareness
await prioritizer.process_queues(
    handler: Callable[[EventTier, Any], Any],
    degradation_factor: float = 1.0
)

# Get queue statistics
stats: dict = prioritizer.get_stats()
# {
#   "p0": {"total": int, "dropped": int, "queue_size": int},
#   "p1": {...},
#   "p2": {...},
#   "p3": {...}
# }
```

**Queue Limits**:
- P0 (Healing): 1,000 max
- P1 (Results): 5,000 max
- P2 (Notifications): 10,000 max
- P3 (Logs): 50,000 max

---

### 10.2 SubsystemIsolator

**Module**: `runtime.infra.cognitive.resilience.subsystem_isolator`

```python
from runtime.infra.cognitive.resilience import get_subsystem_isolator

isolator = get_subsystem_isolator()

# Run coroutine with automatic restart on failure
await isolator.run_isolated(subsystem_id: str, coro: Callable[[], Any])

# Get single subsystem status
status: SubsystemState = isolator.get_status(subsystem_id: str)

# Get all subsystems status
all_status: dict[str, SubsystemState] = isolator.get_all_status()

# Check if healthy
is_healthy: bool = isolator.is_healthy(subsystem_id: str)
```

**SubsystemState Fields**:
```python
@dataclass
class SubsystemState:
    id: str                          # Subsystem identifier
    status: str                      # running | failed | restarting | isolated
    task: Optional[asyncio.Task]     # Current task reference
    failure_count: int               # Number of failures
    last_failure_time: Optional[float]  # Timestamp of last failure
    restart_backoff_ms: int          # Backoff duration (1000, 2000, 4000, ...)
```

**Restart Logic**: Exponential backoff (1s → 2s → 4s → 8s → ... → 60s max), max 5 attempts

---

### 10.3 AdaptiveThrottler

**Module**: `runtime.infra.cognitive.resilience.adaptive_throttler`

```python
from runtime.infra.cognitive.resilience import get_adaptive_throttler

throttler = get_adaptive_throttler()

# Start background CPU/memory polling (every 5 seconds)
await throttler.start()

# Check if tier should be throttled
should_throttle: bool = throttler.should_throttle(tier_name: str)
# tier_name: "p0" | "p1" | "p2" | "p3"

# Get current system status
status: dict = throttler.get_status()
# {
#   "cpu_percent": float,
#   "mem_percent": float,
#   "degradation_level": str  # "none" | "light" | "moderate" | "severe" | "critical"
# }

# Stop polling
throttler.stop()
```

**Degradation Thresholds**:
- **NONE**: CPU <70% and Mem <70%
- **LIGHT**: CPU 70-85% or Mem 70-85%
- **MODERATE**: CPU 85-95% or Mem 85-95%
- **SEVERE**: CPU ≥95% or Mem ≥95%
- **CRITICAL**: Triggered by queue depth (see LoadShedder)

---

### 10.4 LoadShedder

**Module**: `runtime.infra.cognitive.resilience.load_shedder`

```python
from runtime.infra.cognitive.resilience import get_load_shedder
from runtime.infra.cognitive.resilience.schema import EventTier

shedder = get_load_shedder()

# Check if event should be shed (dropped)
should_drop: bool = shedder.should_shed(tier: EventTier, queue_depth: int)

# Get shedding statistics
stats: dict = shedder.get_stats()
# {
#   "total_shed": int,
#   "shed_by_tier": {"p0": 0, "p1": 45, "p2": 230, "p3": 1200}
# }
```

**Shedding Thresholds** (by queue depth):
- **>10,000**: Shed P3 (logs)
- **>50,000**: Shed P2 + P3 (notifications + logs)
- **>100,000**: Shed P1 + P2 + P3 (all except healing)

---

### 10.5 BackpressurePropagator

**Module**: `runtime.infra.cognitive.resilience.backpressure_propagator`

```python
from runtime.infra.cognitive.resilience import get_backpressure_propagator

propagator = get_backpressure_propagator()

# Check queue depth and emit backpressure signal if needed
is_backpressured: bool = propagator.check_and_emit(
    subsystem_id: str,
    queue_depth: int,
    queue_max: int = 10000
)
# Returns True if backpressured, False if normal

# Check if subsystem is currently backpressured
is_backpressured: bool = propagator.is_backpressured(subsystem_id: str)

# Get backpressure state for subsystem
state: Optional[BackpressureState] = propagator.get_state(subsystem_id: str)

# Get all subsystem states
all_states: dict[str, BackpressureState] = propagator.get_all_states()
```

**BackpressureState Fields**:
```python
@dataclass
class BackpressureState:
    subsystem_id: str
    queue_depth: int              # Current queue size
    queue_max_depth: int          # Max queue size (default 10000)
    is_backpressured: bool        # Currently signaling slow-down?
    backpressure_triggered_at: Optional[float]
    threshold_high: float = 0.8   # 80% of max → emit slow_down
    threshold_clear: float = 0.4  # 40% of max → clear slow_down
    timestamp: float
```

**Signals Emitted** (via message bus):
```python
# When queue depth > threshold_high:
bus.publish_sync("notifications", {
    "event": "backpressure:slow_down",
    "subsystem_id": "task_executor"
})

# When queue depth < threshold_clear:
bus.publish_sync("notifications", {
    "event": "backpressure:resume",
    "subsystem_id": "task_executor"
})
```

---

### 10.6 Resilience Schemas

**Module**: `runtime.infra.cognitive.resilience.schema`

```python
from runtime.infra.cognitive.resilience.schema import (
    DegradationLevel,
    EventTier,
    ResilienceEvent,
    BackpressureState,
    QueueMetrics,
)

# Enums
class DegradationLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"           # 70% CPU
    MODERATE = "moderate"     # 85% CPU
    SEVERE = "severe"         # 95% CPU
    CRITICAL = "critical"     # >100k queue

class EventTier(str, Enum):
    P0 = "p0"                 # Healing (never dropped)
    P1 = "p1"                 # Agent results
    P2 = "p2"                 # Notifications
    P3 = "p3"                 # Logs (dropped first)

# Dataclasses
@dataclass
class ResilienceEvent:
    id: str                                    # UUID
    tenant_id: str
    event_type: str                            # subsystem_failure, event_storm, etc.
    degradation_level: DegradationLevel
    message: str
    affected_subsystems: list[str]
    timestamp: float

@dataclass
class QueueMetrics:
    subsystem_id: str
    queue_depth: int
    peak_depth: int
    avg_depth: float
    p90_depth: int
    dropped_count: int
    sampled_at: float
```

---

## PART 11: ENTERPRISE OBSERVABILITY

### 11.1 DistributedTracer

**Module**: `runtime.infra.cognitive.observability.distributed_tracer`

```python
from runtime.infra.cognitive.observability import get_tracer
from runtime.infra.cognitive.observability.schema import Span

tracer = get_tracer()

# Start a new span
span: Span = tracer.start_span(
    trace_id: str,
    operation_name: str,
    tenant_id: str,
    parent_span_id: Optional[str] = None,
    attributes: dict = None
)

# End a span (marks completion, calculates duration_ms)
tracer.end_span(
    span_id: str,
    status: str = "success",    # "success" | "error"
    error_message: Optional[str] = None
)

# Retrieve full trace tree
trace: Optional[TraceTree] = tracer.get_trace(trace_id: str, tenant_id: str)
# → TraceTree with all spans ordered by start_time
```

**Span Fields**:
```python
@dataclass
class Span:
    id: str                          # UUID, unique span ID
    trace_id: str                    # Request-scoped ID
    parent_span_id: Optional[str]    # For hierarchy
    operation_name: str              # "llm_inference", "db_query", etc.
    start_time: float                # Unix timestamp
    end_time: Optional[float]        # When span ended
    duration_ms: float               # Calculated: (end_time - start_time) * 1000
    status: str                      # "pending" | "success" | "error"
    error_message: Optional[str]
    attributes: dict[str, Any]       # Custom metadata
```

**Database**: Persists to `spans` table (trace_id, parent_span_id indexed)

---

### 11.2 WorkflowLineage

**Module**: `runtime.infra.cognitive.observability.workflow_lineage`

```python
from runtime.infra.cognitive.observability import get_lineage_tracker

tracker = get_lineage_tracker()

# Record parent→child workflow relationship
tracker.record(parent_id: str, child_id: str, tenant_id: str)

# Get all parents (ancestry tree)
ancestry: list[dict] = tracker.get_ancestry(workflow_id: str, tenant_id: str)

# Get all children (descendants)
descendants: list[dict] = tracker.get_descendants_tree(workflow_id: str, tenant_id: str)
```

**Output Format** (ancestry):
```python
[
    {
        "workflow_id": "wf_123",
        "parents": [
            {
                "workflow_id": "wf_000",
                "children": [
                    {"workflow_id": "wf_456"},
                    {"workflow_id": "wf_789"}
                ]
            }
        ]
    }
]
```

**Database**: Persists to `workflow_lineage` table (parent_workflow_id indexed)

---

### 11.3 ReasoningLineage

**Module**: `runtime.infra.cognitive.observability.reasoning_lineage`

```python
from runtime.infra.cognitive.observability import get_reasoning_lineage_tracker

tracker = get_reasoning_lineage_tracker()

# Record individual reasoning step
tracker.record_step(
    trace_id: str,
    step_index: int,
    step_data: dict  # {type, input, output, duration_ms, timestamp}
)

# Retrieve reasoning steps for a trace
steps: list[dict] = tracker.get_trace(trace_id: str)

# Falls back to neural_brain if available
steps = tracker.get_from_neural_brain(trace_id: str)

# Clear trace
tracker.clear_trace(trace_id: str)
```

**Step Data Format**:
```python
{
    "index": 0,
    "type": "intent_classification",        # intent | plan | execute | validate
    "input": "user message text",
    "output": "intent: schedule_meeting",
    "duration_ms": 45,
    "timestamp": 1715607600.123
}
```

---

### 11.4 ExecutionHeatmap

**Module**: `runtime.infra.cognitive.observability.execution_heatmap`

```python
from runtime.infra.cognitive.observability import get_heatmap_aggregator

aggregator = get_heatmap_aggregator()

# Record agent execution
aggregator.record_execution(agent_id: str, action_type: str = "task")

# Get 24×7 matrix for agent
heatmap: dict = aggregator.get_heatmap(agent_id: str)
# {
#   0: {0: 42, 1: 15, 2: 8, ..., 6: 5},    # Hour 0: Mon=42, Tue=15, ..., Sun=5
#   1: {0: 38, 1: 12, ..., 6: 4},          # Hour 1: ...
#   ...
#   23: {0: 120, 1: 98, ..., 6: 45}        # Hour 23: ...
# }

# Get peak hours (top 3)
peak_hours: list[int] = aggregator.get_peak_hours(agent_id: str)
# → [14, 15, 9]  (hours 2pm, 3pm, 9am)

# Get all heatmaps
all_heatmaps: dict = aggregator.get_all_heatmaps()
# {agent_id: heatmap, ...}

# Reset agent heatmap
aggregator.reset_heatmap(agent_id: str)
```

**Matrix Dimensions**:
- **Rows** (X-axis): 24 hours (0-23)
- **Columns** (Y-axis): 7 days (0=Monday, 6=Sunday)
- **Values**: Execution count at (hour, day_of_week)

---

### 11.5 AnomalyCorrelator

**Module**: `runtime.infra.cognitive.observability.anomaly_correlator`

```python
from runtime.infra.cognitive.observability import get_anomaly_correlator
from runtime.infra.cognitive.observability.schema import AnomalyCorrelation

correlator = get_anomaly_correlator()

# Record anomaly; auto-detects correlation if 2+ subsystems fail in 60s
correlation: Optional[AnomalyCorrelation] = correlator.record_anomaly(
    anomaly_id: str,
    tenant_id: str,
    subsystem_id: str,
    error_message: str = ""
)
# Returns None if single anomaly, or AnomalyCorrelation if multi-subsystem

# Get all correlations for tenant
correlations: list[dict] = correlator.get_correlations(
    tenant_id: str,
    limit: int = 50
)
```

**AnomalyCorrelation Fields**:
```python
@dataclass
class AnomalyCorrelation:
    id: str                                   # UUID
    tenant_id: str
    anomaly_ids: list[str]                    # IDs of anomalies involved
    suspected_root_cause: str                 # "multiple_subsystems_affected"
    confidence: float                         # 0-1, min(0.9, count/10)
    affected_subsystems: list[str]
    detected_at: float                        # Unix timestamp
```

**Time Window**: 60 seconds (configurable in __init__)

---

### 11.6 Observability Schemas

**Module**: `runtime.infra.cognitive.observability.schema`

```python
from runtime.infra.cognitive.observability.schema import (
    Span,
    TraceTree,
    WorkflowLineage,
    AgentTelemetryRecord,
    AnomalyCorrelation,
)

@dataclass
class TraceTree:
    trace_id: str
    root_span_id: str           # ID of first span (parent_span_id=None)
    tenant_id: str
    spans: list[Span]           # All spans in execution order
    created_at: float

@dataclass
class WorkflowLineage:
    parent_workflow_id: str
    child_workflow_id: str
    tenant_id: str
    spawned_at: float

@dataclass
class AgentTelemetryRecord:
    agent_id: str
    tenant_id: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    success_rate: float        # 0-1
    sampled_at: float
```

---

## PART 12: PERFORMANCE + SCALE

### 12.1 AdaptiveCache

**Module**: `runtime.infra.cognitive.scale.adaptive_cache`

```python
from runtime.infra.cognitive.scale import get_adaptive_cache

cache = get_adaptive_cache()

# Get value (None if not found or expired)
value: Optional[Any] = cache.get(key: str)

# Set value (auto-evicts oldest if full)
cache.set(key: str, value: Any)

# Invalidate single key
cache.invalidate(key: str)

# Invalidate by pattern (substring match)
deleted_count: int = cache.invalidate_pattern(pattern: str)

# Clear entire cache
cache.clear()

# Get metrics
metrics: dict = cache.get_metrics()
# {hits, misses, hit_rate, entries, evictions}
```

**Config**:
- **Max entries**: 1,000
- **TTL**: 60 seconds
- **Eviction policy**: LRU (Least Recently Used)

---

### 12.2 GraphPartitioner

**Module**: `runtime.infra.cognitive.scale.graph_partitioner`

```python
from runtime.infra.cognitive.scale import get_graph_partitioner

partitioner = get_graph_partitioner()

# Generate shard ID from tenant + time window
shard_id: str = partitioner.partition_by_tenant_and_time(
    tenant_id: str,
    time_window_key: str        # "2025-01", "2025-02", etc.
)
# → "tenant_id_2025-01"

# Check if partitioning needed
should_partition: bool = partitioner.should_partition(
    shard_id: str,
    node_count: int
)
# Returns True if node_count > 50,000

# Attempt Neo4j partitioning
result: Optional[dict] = partitioner.try_partition_neo4j(
    tenant_id: str,
    node_count: int
)
# Returns None if Neo4j unavailable

# Get partition statistics
stats: dict = partitioner.get_partition_stats()
# {shard_id: {node_count, edge_count, partition_key}, ...}
```

**Partitioning Strategy**: Shard by `{tenant_id}_{time_window}` (e.g., "org1_2025-01")  
**Threshold**: Partition when node_count > 50,000

---

### 12.3 MemoryCompactor

**Module**: `runtime.infra.cognitive.scale.memory_compactor`

```python
from runtime.infra.cognitive.scale import get_memory_compactor

compactor = get_memory_compactor()

# Trigger manual compaction
stats: dict = await compactor.compact_memories()
# {
#   "compactions_run": int,
#   "memories_archived": int,
#   "memories_consolidated": int,
#   "tokens_saved_estimate": int
# }

# Start weekly background loop
await compactor.start_weekly_compaction_loop()

# Get stats
stats: dict = compactor.get_stats()

# Attempt Neo4j compaction
result: Optional[dict] = compactor.try_compact_neo4j()
```

**Tasks**:
1. Archive memories >90 days old
2. Consolidate similar memories
3. Rebuild indexes

**Schedule**: Every 7 days

---

### 12.4 WebSocketBatcher

**Module**: `runtime.infra.cognitive.scale.ws_batcher`

```python
from runtime.infra.cognitive.scale import get_ws_batcher

batcher = get_ws_batcher()

# Enqueue message (auto-flushes if buffer full)
await batcher.enqueue_message(message: Any)

# Manually flush batch
batch: list[Any] = await batcher.flush(handler: Optional[Callable] = None)

# Start auto-flush loop (every 50ms)
async def send_to_ws(batch: list[Any]):
    for ws in active_connections:
        await ws.send_json({"batch": batch})

await batcher.start_auto_flush(send_to_ws)

# Get metrics
metrics: dict = batcher.get_metrics()
# {
#   "total_messages": int,
#   "batches_sent": int,
#   "avg_batch_size": float,
#   "max_batch_size": int,
#   "pending_messages": int
# }
```

**Config**:
- **Batch window**: 50 milliseconds
- **Max batch size**: 50 messages
- **Flush trigger**: 50ms elapsed OR 50 messages (whichever first)

---

### 12.5 EventCompressor

**Module**: `runtime.infra.cognitive.scale.event_compressor`

```python
from runtime.infra.cognitive.scale import get_event_compressor

compressor = get_event_compressor()

# Record event; auto-compresses if storm detected
result: dict = compressor.record_event(
    event_type: str,
    agent_id: str = "unknown"
)
# {
#   "type": str,
#   "agent_id": str,
#   "compressed": bool,
#   "count": int (if compressed),           # Number of events combined
#   "period_s": float (if compressed)       # Time window
# }

# Get compression statistics
stats: dict = compressor.get_stats()
# {
#   "original_event_count": int,
#   "compressed_event_count": int,
#   "bytes_saved": int,
#   "compression_ratio": float              # 0-1
# }
```

**Config**:
- **Threshold**: 5+ events of same type in 1 second
- **Window**: 1 second
- **Bytes saved estimate**: `count × 50`

---

### 12.6 Scale Schemas

**Module**: `runtime.infra.cognitive.scale.schema`

```python
from runtime.infra.cognitive.scale.schema import (
    CacheMetrics,
    PartitionStats,
    CompressionStats,
    WebSocketBatchMetrics,
)

@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    entries_count: int = 0
    sample_time: float = field(default_factory=time.time)
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

@dataclass
class PartitionStats:
    shard_id: str
    node_count: int
    edge_count: int
    partition_key: str
    created_at: float

@dataclass
class CompressionStats:
    original_event_count: int = 0
    compressed_event_count: int = 0
    bytes_saved: int = 0
    sample_time: float = field(default_factory=time.time)
    
    @property
    def compression_ratio(self) -> float:
        if self.original_event_count == 0:
            return 0.0
        return 1.0 - (self.compressed_event_count / self.original_event_count)

@dataclass
class WebSocketBatchMetrics:
    total_messages: int = 0
    batches_sent: int = 0
    avg_batch_size: float = 0.0
    max_batch_size: int = 0
    sample_time: float = field(default_factory=time.time)
```

---

## FASTAPI ROUTES

All routes mounted at `/cognitive/{subsystem}/{endpoint}`

### Resilience Routes

```
GET  /cognitive/resilience/status
GET  /cognitive/resilience/events
GET  /cognitive/resilience/degradation
GET  /cognitive/resilience/queue-depths
POST /cognitive/resilience/emergency-stop
POST /cognitive/resilience/resume
```

### Observability Routes

```
GET  /cognitive/observability/traces/{trace_id}
GET  /cognitive/observability/lineage/{workflow_id}
GET  /cognitive/observability/reasoning/{trace_id}
GET  /cognitive/observability/heatmap/{agent_id}
GET  /cognitive/observability/anomaly-correlations?limit=50
GET  /cognitive/observability/agent-telemetry
```

### Scale Routes

```
GET  /cognitive/scale/metrics
POST /cognitive/scale/compact-memory
POST /cognitive/scale/partition-graph
GET  /cognitive/scale/ws-stats
GET  /cognitive/scale/compression-stats
```

---

## DATABASE ACCESS

**Path**: `~/.ai-employee/cognitive.db` (SQLite, WAL mode)

```python
from runtime.infra.cognitive.db import cognitive_conn

with cognitive_conn() as c:
    rows = c.execute(
        "SELECT * FROM spans WHERE trace_id=? AND tenant_id=?",
        (trace_id, tenant_id)
    ).fetchall()
    for row in rows:
        print(dict(row))
```

**Tables**:
- `spans` — Distributed tracing
- `workflow_lineage` — Workflow relationships
- `anomaly_correlations` — System-wide anomalies

---

## QUICK START

```python
# 1. Resilience: Wrap agent execution
from runtime.infra.cognitive.resilience import (
    get_subsystem_isolator,
    get_event_prioritizer,
)
from runtime.infra.cognitive.resilience.schema import EventTier

isolator = get_subsystem_isolator()
await isolator.run_isolated("my_agent", agent_main)

# 2. Observability: Trace requests
from runtime.infra.cognitive.observability import get_tracer
from uuid import uuid4

tracer = get_tracer()
trace_id = str(uuid4())
span = tracer.start_span(trace_id, "my_operation", tenant_id="org1")
# ... do work ...
tracer.end_span(span.id, status="success")

# 3. Scale: Cache results
from runtime.infra.cognitive.scale import get_adaptive_cache

cache = get_adaptive_cache()
result = cache.get("my_key")
if result is None:
    result = expensive_computation()
    cache.set("my_key", result)
```

---

## CONFIGURATION

All defaults are production-safe. Override in `settings.json`:

```json
{
  "resilience": {
    "event_prioritizer_queue_limits": {
      "p0": 1000,
      "p1": 5000,
      "p2": 10000,
      "p3": 50000
    },
    "adaptive_throttle_poll_interval_s": 5,
    "subsystem_max_restarts": 5,
    "load_shedder_thresholds": [10000, 50000, 100000]
  },
  "observability": {
    "anomaly_correlation_time_window_s": 60,
    "trace_retention_days": 30
  },
  "scale": {
    "cache_max_entries": 1000,
    "cache_ttl_s": 60,
    "ws_batch_window_ms": 50,
    "ws_batch_max_size": 50,
    "graph_partition_node_limit": 50000,
    "event_compression_threshold": 5,
    "event_compression_window_s": 1.0
  }
}
```

---

## EXPORTS BY MODULE

```python
# Resilience
from runtime.infra.cognitive.resilience import (
    get_event_prioritizer,
    get_subsystem_isolator,
    get_adaptive_throttler,
    get_load_shedder,
    get_backpressure_propagator,
)

# Observability
from runtime.infra.cognitive.observability import (
    get_tracer,
    get_lineage_tracker,
    get_reasoning_lineage_tracker,
    get_heatmap_aggregator,
    get_anomaly_correlator,
)

# Scale
from runtime.infra.cognitive.scale import (
    get_adaptive_cache,
    get_graph_partitioner,
    get_memory_compactor,
    get_ws_batcher,
    get_event_compressor,
)

# All as singletons (module-level instances)
```

---

## VERSION

Phase 4 API Reference v1.0.0  
Python 3.10+  
FastAPI 0.100+  
SQLite 3.30+
