# Cognitive Infrastructure Developer Guide

## Quick Start

All cognitive systems are mounted as FastAPI routers under `/cognitive/`:

```python
# Learning System
GET  /cognitive/learning/status
GET  /cognitive/learning/outcomes
GET  /cognitive/learning/effectiveness
GET  /cognitive/learning/routing-suggestions
POST /cognitive/learning/routing-suggestions/generate

# Teammate Identity
GET  /cognitive/teammate/identity
GET  /cognitive/teammate/relationship/{user_id}
GET  /cognitive/teammate/habits/{user_id}
GET  /cognitive/teammate/insights
POST /cognitive/teammate/insights/{id}/dismiss

# Temporal Awareness
GET  /cognitive/temporal/status
GET  /cognitive/temporal/deadlines
GET  /cognitive/temporal/urgency/{initiative_id}
GET  /cognitive/temporal/cycles
GET  /cognitive/temporal/schedule
```

## Core Patterns

### Recording Outcomes (Learning)

```python
from infra.cognitive.learning import record
from infra.cognitive.learning.schema import OutcomeRecord

outcome = OutcomeRecord(
    workflow_id="wf-task-123",
    agent_id="agent-planner",
    tenant_id="org-acme",
    success=True,
    quality_score=0.85,  # 0.0-1.0
    duration_ms=2500.0,
    cost_tokens=150
)

record(outcome)
```

### Tracking User Interactions (Teammate)

```python
from infra.cognitive.teammate import (
    increment_interaction,
    record,
    record_event,
    update_from_response
)

# In conversation loop:
increment_interaction(tenant_id)
record(user_id, tenant_id, "Discussed Q3 planning", topic="strategy")
record_event(user_id, tenant_id, "planning")  # For habit detection
update_from_response(user_id, tenant_id, len(response), has_technical=True)
```

### Creating Deadlines (Temporal)

```python
from infra.cognitive.temporal import create
from infra.cognitive.temporal.schema import Deadline
import time

deadline = Deadline(
    initiative_id="init-marketing-campaign",
    tenant_id="org-acme",
    deadline_ts=time.time() + 7*86400,  # 7 days
    priority=7
)

deadline_id = create(deadline)
```

## Common Tasks

### Get Agent Effectiveness

```python
from infra.cognitive.learning import compute

score = compute("agent-executor", "org-acme")
print(f"Effectiveness: {score.score}, Trend: {score.trend}")

if score.trend == "degrading":
    # Alert team, trigger investigation
    pass
```

### Get Routing Suggestions

```python
from infra.cognitive.learning import generate_suggestions, list_suggestions

# Generate new suggestions
suggestions = generate_suggestions("org-acme")

# List pending suggestions
pending = list_suggestions("org-acme")

for sugg in pending:
    if sugg['quality_delta'] > 0.25:
        # High confidence suggestion
        accept(sugg['id'], True)
```

### Get User Context

```python
from infra.cognitive.teammate import get_or_create, get_context, get_habits

# Get AI identity for this tenant
identity = get_or_create("org-acme")
print(f"I am {identity.name}, {identity.persona_summary}")

# Get context for specific user
ctx = get_context("alice@acme.com", "org-acme")
print(f"Known interactions: {ctx['interaction_count']}")

# Get habits
habits = get_habits("alice@acme.com", "org-acme")
for h in habits:
    print(f"Usually does {h['workflow_type']} at {h['typical_hour']}:00")
```

### Compute Urgency

```python
from infra.cognitive.temporal import compute_urgency
import time

deadline_ts = time.time() + 3600  # 1 hour
urgency = compute_urgency("init-123", base_priority=7, deadline_ts=deadline_ts)

if urgency.urgency > 80:
    # Critical — escalate
    pass
```

### Get Recommended Schedule

```python
from infra.cognitive.temporal import get_schedule

# Get top priorities based on deadlines
initiatives = [
    {"id": "i1", "title": "Review Q3", "deadline": time.time() + 3600, "priority": 7},
    {"id": "i2", "title": "Plan Q4", "deadline": time.time() + 86400, "priority": 5},
]

schedule = get_schedule(initiatives, "org-acme")
for init in schedule['schedule']:
    print(f"{init['title']}: urgency={init.get('urgency', 'N/A')}")
```

## Database Schema Reference

### Learning System Tables

**outcome_records**
```sql
id TEXT PRIMARY KEY
workflow_id TEXT
agent_id TEXT
tenant_id TEXT
success INTEGER (0|1)
quality_score REAL
duration_ms REAL
cost_tokens INTEGER
user_feedback INTEGER (nullable)
recorded_at REAL
```

**effectiveness_scores**
```sql
agent_id TEXT
tenant_id TEXT
score REAL
sample_count INTEGER
trend TEXT (improving|degrading|stable)
computed_at REAL
PRIMARY KEY (agent_id, tenant_id)
```

**routing_suggestions**
```sql
id TEXT PRIMARY KEY
task_type TEXT
from_agent TEXT
to_agent TEXT
tenant_id TEXT
confidence REAL
sample_size INTEGER
quality_delta REAL
suggested_at REAL
accepted INTEGER (nullable)
```

### Teammate Identity Tables

**teammate_identity**
```sql
tenant_id TEXT PRIMARY KEY
name TEXT
persona_summary TEXT
operational_focus TEXT
expertise_areas TEXT (JSON)
interaction_count INTEGER
formed_at REAL
updated_at REAL
```

**user_habits**
```sql
id TEXT PRIMARY KEY
user_id TEXT
tenant_id TEXT
workflow_type TEXT
typical_hour INTEGER
frequency INTEGER
confidence REAL
detected_at REAL
```

**conversation_memory**
```sql
id INTEGER PRIMARY KEY
user_id TEXT
tenant_id TEXT
summary TEXT
topic TEXT (nullable)
recorded_at REAL
```

### Temporal Tables

**deadlines**
```sql
id TEXT PRIMARY KEY
initiative_id TEXT
tenant_id TEXT
deadline_ts REAL
priority INTEGER
status TEXT (pending|completed|archived|missed)
created_at REAL
```

**op_cycles**
```sql
workflow_type TEXT
tenant_id TEXT
period_days INTEGER
confidence REAL
last_peak REAL
detected_at REAL
PRIMARY KEY (workflow_type, tenant_id)
```

## Error Handling

All systems degrade gracefully:

```python
try:
    score = compute("agent-x", "tenant-001")
except Exception as e:
    logger.warning(f"Failed to compute score: {e}")
    # Treat as unknown (score=1.0, trend="stable")
    score = EffectivenessScore(agent_id="agent-x", score=1.0, trend="stable", sample_count=0)
```

## Performance Tips

1. **Batch outcome recording**: Record multiple outcomes in single transaction
2. **Cache scores**: Reinforce scores are memoized for 60s
3. **Async cycle detection**: Run FFT-based detection in background worker
4. **Index queries**: habit_recognizer queries use sliding window in memory
5. **Deadline polling**: Runs every 60s, not on every request

## Testing

```bash
# Run all Phase 4 tests
pytest tests/test_cognitive_phase4.py -v

# Run specific test
pytest tests/test_cognitive_phase4.py::test_outcome_tracker_record -v

# Run with coverage
pytest tests/test_cognitive_phase4.py --cov=runtime.infra.cognitive
```

## Monitoring

Key metrics to track:

- **Learning System**: agent effectiveness scores, routing acceptance rate
- **Teammate**: interaction count growth, habit detection rate
- **Temporal**: deadline miss rate, average urgency at completion

Check dashboards at:
- `/cognitive/learning/effectiveness` — agent health
- `/cognitive/teammate/identity` — AI identity state
- `/cognitive/temporal/status` — upcoming deadline count

## Troubleshooting

### No outcomes recorded
- Check: is `record()` being called after each workflow?
- Verify: outcome.quality_score is 0.0-1.0
- Check: SQLite database is writable

### Habits not detected
- Check: `record_event()` called on each workflow start
- Verify: same workflow_type and hour appear 3+ times in 7 days
- Check: confidence > 0.6 threshold

### Deadlines not alerting
- Check: deadline_tracker polling is running (async task at startup)
- Verify: deadline_ts is absolute timestamp (time.time() + seconds)
- Check: status is "pending" (not completed/archived)

### Routes returning 404
- Check: Phase 4 routes mounted in server.py (line 26697)
- Verify: module imports succeed without errors
- Check: FastAPI app initialized before route mounting

## Further Reading

- Architecture: `PHASE_4_COGNITIVE_INFRASTRUCTURE.md`
- Schemas: `learning/schema.py`, `teammate/schema.py`, `temporal/schema.py`
- Tests: `tests/test_cognitive_phase4.py`
