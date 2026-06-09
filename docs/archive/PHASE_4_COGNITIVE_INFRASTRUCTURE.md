# Phase 4 Cognitive Infrastructure: Learning, Identity & Temporal Reasoning

## Overview

Phase 4 Parts 7-9 implement three critical cognitive systems that enable self-improvement, human-AI partnership, and intelligent temporal planning:

- **Part 7**: Continuous Learning System (outcome tracking, reinforcement learning, routing optimization)
- **Part 8**: AI Teammate Identity (persistent identity, relationship memory, habit recognition, communication adaptation)
- **Part 9**: System-Wide Temporal Awareness (deadline tracking, urgency computation, operational cycles, intelligent scheduling)

## Part 7: Continuous Learning System

### Purpose
Enable the system to learn from execution outcomes and optimize agent selection through data-driven insights.

### Architecture

#### Outcome Tracker (`outcome_tracker.py`)
Records execution outcomes and computes quality scores.

**Quality Score Calculation:**
- Range: 0.0 (complete failure) to 1.0 (perfect execution)
- Components: success + no_errors + within_budget
- Tracked: success flag, duration_ms, cost_tokens, user_feedback

**API:**
```python
from infra.cognitive.learning import record, get_recent

# Record an execution outcome
record(OutcomeRecord(
    workflow_id="wf-123",
    agent_id="agent-xyz",
    tenant_id="tenant-001",
    success=True,
    quality_score=0.87,
    duration_ms=2500.0,
    cost_tokens=150
))

# Retrieve recent outcomes for an agent
outcomes = get_recent("tenant-001", "agent-xyz", limit=50)
```

**Storage:**
- SQLite table: `outcome_records`
- Indexed by: agent_id, tenant_id, recorded_at
- Retention: unlimited (append-only log)

#### Reinforcement Engine (`reinforcement_engine.py`)
Computes effectiveness scores using Exponential Moving Average (EMA).

**Algorithm:**
- Window: last 50 outcomes per agent
- EMA smoothing: α = 0.1 (10% current, 90% historical)
- Trend analysis: improving (+5%), stable (±5%), degrading (-5%)
- Events: agent_degraded (< 0.6), agent_promoted (> 0.9)

**API:**
```python
from infra.cognitive.learning import compute

# Compute effectiveness for an agent
score = compute("agent-xyz", "tenant-001")
# Returns: EffectivenessScore(score=0.82, trend="improving", sample_count=50)
```

**Storage:**
- SQLite table: `effectiveness_scores`
- Primary key: (agent_id, tenant_id)
- Updated: on each call, memoized for 60 seconds

#### Routing Optimizer (`routing_optimizer.py`)
Identifies agent routing improvements based on comparative performance.

**Decision Threshold:**
- Minimum samples: 50 outcomes per agent
- Minimum quality delta: 20% (0.2 score points)
- Confidence: min(0.95, delta × 2)

**API:**
```python
from infra.cognitive.learning import generate_suggestions, list_suggestions, accept

# Generate routing suggestions
suggestions = generate_suggestions("tenant-001")
# Returns: [RoutingAdjustment(from_agent=..., to_agent=..., confidence=0.85, quality_delta=0.22)]

# List pending suggestions
pending = list_suggestions("tenant-001")

# Accept or reject a suggestion
accept("suggestion-id-123", accept=True)
```

**Storage:**
- SQLite table: `routing_suggestions`
- Fields: from_agent, to_agent, quality_delta, confidence, accepted (nullable)

#### Strategy Optimizer (`strategy_optimizer.py`)
Learns optimal initiative sequencing patterns.

**Learning:**
- Key: sequence of up to 3 initiative IDs joined by "->"
- Records: quality score achieved with this ordering
- Confidence: rolling average over samples
- Threshold: confidence > 0.7 for recommendation

**API:**
```python
from infra.cognitive.learning import record_ordering, get_preferences

# Record successful sequence
record_ordering(["init-1", "init-2", "init-3"], quality_score=0.92, tenant_id="tenant-001")

# Get preferred orderings
prefs = get_preferences("tenant-001")
# Returns top 20 orderings with confidence > 0.7
```

### Routes

**GET /cognitive/learning/status**
```json
{"total_agents": 47, "degraded": 2, "tenant_id": "tenant-001"}
```

**GET /cognitive/learning/outcomes?agent_id=agent-xyz**
```json
{"outcomes": [{workflow_id, success, quality_score, recorded_at}, ...]}
```

**GET /cognitive/learning/effectiveness**
```json
{"agents": [{agent_id, score, trend, sample_count}, ...]}
```

**GET /cognitive/learning/routing-suggestions**
```json
{"suggestions": [{from_agent, to_agent, quality_delta, confidence}, ...]}
```

**POST /cognitive/learning/routing-suggestions/generate**
```json
{"ok": true, "generated": 3}
```

**POST /cognitive/learning/routing-suggestions/{id}/accept**
```json
{"ok": true}
```

**GET /cognitive/learning/strategy-preferences**
```json
{"preferences": [{seq_key, confidence, sample_count}, ...]}
```

---

## Part 8: AI Teammate Identity

### Purpose
Create a persistent, evolving AI teammate identity that understands individual users and adapts communication.

### Architecture

#### Identity Manager (`identity_manager.py`)
Maintains the core identity of the AI teammate.

**Identity Evolution:**
- Default name: "Aeternus"
- Persona synthesized: every 100 interactions (via LLM)
- Expertise areas: derived from agent capabilities and user feedback
- Operational focus: shifts based on most common workflow types

**API:**
```python
from infra.cognitive.teammate import get_or_create, increment_interaction, update_persona

# Get or create identity
identity = get_or_create("tenant-001")
# Returns: TeammateIdentity(name="Aeternus", persona_summary="...", expertise_areas=[...])

# Increment on user interaction
increment_interaction("tenant-001")

# Update persona (triggered at interaction_count % 100 == 0)
update_persona("tenant-001", "Evolved summary based on 100 interactions...")
```

**Storage:**
- SQLite table: `teammate_identity`
- One row per tenant
- Fields: name, persona_summary, operational_focus, expertise_areas (JSON)

#### Relationship Memory (`relationship_memory.py`)
Maintains per-user interaction history.

**History:**
- Stores: 500 most recent interactions per user
- Fields: summary (condensed interaction), topic, recorded_at
- Sliding window: keeps only last 500

**API:**
```python
from infra.cognitive.teammate import record, get_context

# Record an interaction
record(
    user_id="user-alice",
    tenant_id="tenant-001",
    summary="Discussed Q3 revenue targets",
    topic="planning"
)

# Get user context
context = get_context("user-alice", "tenant-001")
# Returns: {
#   user_id: "user-alice",
#   interaction_count: 47,
#   recent: [{summary, topic, recorded_at}, ...]
# }
```

**Storage:**
- SQLite table: `conversation_memory`
- Indexed by: user_id, tenant_id, recorded_at
- Retention: 500 most recent per user

#### Habit Recognizer (`habit_recognizer.py`)
Detects recurring user behavior patterns.

**Detection Algorithm:**
- Window: 7-day sliding window
- Trigger: same workflow type appears ≥3 times at same hour
- Confidence: frequency / total events in window
- Threshold: confidence ≥ 0.6

**Habits Tracked:**
- workflow_type: category of work (e.g., "reporting", "planning")
- typical_hour: hour of day (0-23) when this work happens
- frequency: number of times in window
- confidence: 0.0-1.0

**API:**
```python
from infra.cognitive.teammate import record_event, get_habits

# Record a workflow event
record_event("user-alice", "tenant-001", "reporting")

# Get detected habits
habits = get_habits("user-alice", "tenant-001")
# Returns: [
#   HabitPattern(workflow_type="reporting", typical_hour=14, frequency=3, confidence=0.8),
#   ...
# ]
```

**Storage:**
- SQLite table: `user_habits`
- Indexed by: user_id, tenant_id
- Retention: all detected patterns

#### Communication Adapter (`communication_adapter.py`)
Learns user communication preferences.

**Preference Tracking:**
- prefers_brief: 1 if recent responses < 100 tokens, else 0
- technical_depth: scale 0-3 based on technical content in responses
- formality: scale 0-3 based on formal language
- emoji_ok: 1 if user has responded positively to emoji, else 0
- sample_count: number of interactions used to establish profile

**API:**
```python
from infra.cognitive.teammate import get_profile, update_from_response

# Update profile after response
update_from_response(
    user_id="user-alice",
    tenant_id="tenant-001",
    response_length=150,
    has_technical=True
)

# Get communication profile
profile = get_profile("user-alice", "tenant-001")
# Returns: {
#   user_id: "user-alice",
#   prefers_brief: 1,
#   technical_depth: 2,
#   formality: 1,
#   emoji_ok: 0
# }
```

**Storage:**
- SQLite table: `comm_profiles`
- Primary key: (user_id, tenant_id)
- Updated: after each response

#### Proactive Engine (`proactive_engine.py`)
Surfaces relevant insights without user prompting.

**Cycle:** Runs every 15 minutes

**Insight Types:**
- `habit_reminder`: "You usually do X at 2pm"
- `blocked_initiative`: "3 initiatives waiting on approval"
- `anomaly`: Unusual activity patterns detected

**API:**
```python
from infra.cognitive.teammate import list_insights, dismiss

# Get non-dismissed insights
insights = list_insights("tenant-001")
# Returns: [
#   ProactiveInsight(
#     title="Initiative blocked",
#     body="Project X waiting on approval",
#     insight_type="blocked_initiative",
#     priority=2
#   ),
#   ...
# ]

# Dismiss an insight (user feedback)
dismiss("insight-id-123")
```

**Storage:**
- SQLite table: `proactive_insights`
- Indexed by: tenant_id, dismissed
- Fields: insight_type, priority, title, body

### Routes

**GET /cognitive/teammate/identity**
```json
{
  "tenant_id": "tenant-001",
  "name": "Aeternus",
  "persona_summary": "Enterprise intelligence system...",
  "operational_focus": "general",
  "expertise_areas": ["planning", "execution", "monitoring"],
  "interaction_count": 342
}
```

**GET /cognitive/teammate/relationship/{user_id}**
```json
{
  "user_id": "user-alice",
  "interaction_count": 47,
  "recent": [
    {"summary": "Discussed Q3 targets", "topic": "planning", "recorded_at": 1234567890}
  ]
}
```

**GET /cognitive/teammate/habits/{user_id}**
```json
{
  "habits": [
    {"workflow_type": "reporting", "typical_hour": 14, "frequency": 3, "confidence": 0.8}
  ]
}
```

**GET /cognitive/teammate/insights**
```json
{
  "insights": [
    {
      "id": "insight-123",
      "title": "Blocked initiatives",
      "body": "3 projects awaiting approval",
      "insight_type": "blocked_initiative",
      "priority": 2
    }
  ]
}
```

**POST /cognitive/teammate/insights/{id}/dismiss**
```json
{"ok": true}
```

**GET /cognitive/teammate/communication-profile/{user_id}**
```json
{
  "user_id": "user-alice",
  "prefers_brief": 1,
  "technical_depth": 2,
  "formality": 1,
  "emoji_ok": 0
}
```

---

## Part 9: System-Wide Temporal Awareness

### Purpose
Enable deadline-aware scheduling, urgency-driven prioritization, and cycle-based predictions.

### Architecture

#### Deadline Tracker (`deadline_tracker.py`)
Monitors and escalates approaching deadlines.

**Tracking:**
- Status: pending, completed, archived, missed
- Polling: every 60 seconds
- Critical threshold: < 24 hours remaining
- Escalation: to HITL if deadline missed

**Events:**
- `temporal:deadline_critical`: < 24h remaining
- `temporal:deadline_missed`: deadline passed without completion

**API:**
```python
from infra.cognitive.temporal import create, list_upcoming

# Create a deadline
deadline = Deadline(
    initiative_id="init-123",
    tenant_id="tenant-001",
    deadline_ts=time.time() + 86400,
    priority=5
)
deadline_id = create(deadline)

# List upcoming deadlines (next 24 hours)
upcoming = list_upcoming("tenant-001", hours_ahead=24)
# Returns: [{id, initiative_id, deadline_ts, priority, status}, ...]
```

**Storage:**
- SQLite table: `deadlines`
- Indexed by: tenant_id, status
- Retention: all until completed/archived

#### Urgency Engine (`urgency_engine.py`)
Computes real-time urgency scores with exponential decay.

**Algorithm:**
```
urgency(t) = base_priority × 10 × exp(decay_rate × (-remaining_seconds))

where:
  base_priority: 1-10
  decay_rate: 0.01 (> 72h), 0.05 (< 72h)  // accelerates in last 3 days
  result: 0-100 scale
```

**Behavior:**
- Far future (7+ days): low urgency (~10-20)
- 3 days: moderate urgency (~30-50)
- 1 day: high urgency (~70-85)
- < 1 hour: critical urgency (~90+)

**API:**
```python
from infra.cognitive.temporal import compute_urgency

# Compute urgency for initiative
urgency = compute_urgency(
    initiative_id="init-123",
    base_priority=5,
    deadline_ts=time.time() + 3600
)
# Returns: UrgencyScore(urgency=87.5, time_remaining_s=3600)
```

#### Cycle Detector (`cycle_detector.py`)
Identifies recurring operational patterns.

**Detection Method:**
- FFT-based period detection (numpy-based)
- Fallback: manual correlation analysis for small datasets
- Window: 90-day execution history
- Confidence threshold: > 0.7

**Cycles Detected:**
- Daily: recurring tasks at same time
- Weekly: Monday/Friday patterns
- Monthly: end-of-month spikes

**API:**
```python
from infra.cognitive.temporal import store_cycle, get_cycles

# Store detected cycle
cycle = OperationalCycle(
    workflow_type="weekly_planning",
    tenant_id="tenant-001",
    period_days=7,
    confidence=0.82,
    last_peak=time.time()
)
store_cycle(cycle)

# Retrieve detected cycles
cycles = get_cycles("tenant-001")
# Returns: [
#   {workflow_type: "weekly_planning", period_days: 7, confidence: 0.82},
#   ...
# ]
```

**Storage:**
- SQLite table: `op_cycles`
- Primary key: (workflow_type, tenant_id)
- Only stores: confidence > 0.7

#### Scheduling Intelligence (`scheduling_intelligence.py`)
Generates deadline-aware initiative schedules.

**Algorithm (Greedy with Conflict Backoff):**
1. Compute urgency for each initiative
2. Sort by urgency descending
3. Respect dependencies and cycles
4. Backoff if conflicts detected
5. Return top 10 initiatives

**Inputs:**
- initiatives: list with id, title, deadline, priority
- tenant_id: for cycle lookup

**API:**
```python
from infra.cognitive.temporal import get_schedule

initiatives = [
    {"id": "i1", "title": "Project A", "deadline": time.time() + 86400},
    {"id": "i2", "title": "Project B", "deadline": time.time() + 172800},
]

schedule = get_schedule(initiatives, "tenant-001")
# Returns: {
#   "schedule": [initiatives ordered by urgency],
#   "count": 2,
#   "tenant_id": "tenant-001"
# }
```

### Routes

**GET /cognitive/temporal/status**
```json
{"upcoming_count": 12, "tenant_id": "tenant-001"}
```

**GET /cognitive/temporal/deadlines?hours_ahead=24**
```json
{
  "deadlines": [
    {"id": "d-1", "initiative_id": "i-1", "deadline_ts": 1234567890, "priority": 5, "status": "pending"}
  ]
}
```

**GET /cognitive/temporal/urgency/{initiative_id}**
```json
{
  "initiative_id": "i-123",
  "urgency": 72.5,
  "time_remaining_s": 3600,
  "base_priority": 5
}
```

**GET /cognitive/temporal/cycles**
```json
{
  "cycles": [
    {"workflow_type": "weekly_planning", "period_days": 7, "confidence": 0.82}
  ]
}
```

**GET /cognitive/temporal/schedule**
```json
{
  "schedule": [{id, title, deadline, priority, urgency}, ...],
  "count": 8,
  "tenant_id": "tenant-001"
}
```

---

## Integration Points

### With Executive System
- Deadline alerts feed into initiative suspension/escalation
- Cycle detection informs strategic planning priorities
- Urgency scores override manual priority settings

### With Learning System
- Recording outcomes triggers reinforcement learning updates
- Strategy optimizer results inform initiative ordering

### With Teammate Identity
- Habit patterns are used for proactive habit reminders
- Interaction records update persona synthesis
- Communication profiles shape response generation

### Message Bus Integration
All systems emit events to `/notifications` channel:
```
learning:agent_degraded
learning:agent_promoted
temporal:deadline_critical
temporal:deadline_missed
teammate:proactive_insight
```

---

## Performance Characteristics

| System | Latency | Storage | QPS |
|--------|---------|---------|-----|
| Outcome Tracker | <1ms write | 1MB/1000 records | 1000+ |
| Reinforcement Engine | 5-10ms compute | 10KB per agent | 100 |
| Routing Optimizer | 20-50ms | 50KB | 10 |
| Identity Manager | <1ms read/write | 1KB per tenant | 1000 |
| Relationship Memory | 2-5ms | 500KB per user | 500 |
| Habit Recognizer | 1-2ms | 10KB per user | 1000 |
| Proactive Engine | 100-500ms (15min cycle) | 100KB | - |
| Deadline Tracker | <1ms create | 1MB | 1000 |
| Urgency Engine | <1ms compute | - | 10000 |
| Cycle Detector | 50-200ms (async) | 50KB | 10 |

---

## Configuration & Tuning

### Learning System
```python
# outcome_tracker.py
# No tuning needed — append-only, linear scaling

# reinforcement_engine.py
_ALPHA = 0.1  # EMA smoothing (0.0-1.0, higher = more weight to recent)
_DEGRADE_THRESHOLD = 0.6  # Alert if effectiveness falls below
_PROMOTE_THRESHOLD = 0.9  # Alert if effectiveness exceeds
_MIN_SAMPLES = 10  # Minimum outcomes to compute trend

# routing_optimizer.py
_MIN_MARGIN = 0.2  # Minimum quality delta to recommend change
_MIN_SAMPLES = 50  # Minimum outcomes per agent to suggest
```

### Teammate Identity
```python
# identity_manager.py
_PERSONA_SYNTHESIS_INTERVAL = 100  # Interactions before LLM synthesis

# habit_recognizer.py
_window = {}  # In-memory 7-day sliding window (3.5MB per 1000 users)
_HABIT_THRESHOLD = 0.6  # Confidence to store habit
```

### Temporal
```python
# deadline_tracker.py
POLL_INTERVAL = 60  # Seconds between checks

# urgency_engine.py
decay_rate = 0.01  # Normal decay
decay_rate = 0.05  # Accelerated in last 72 hours

# cycle_detector.py
CONFIDENCE_THRESHOLD = 0.7  # Minimum to store cycle
```

---

## Testing

Comprehensive test suite in `/tests/test_cognitive_phase4.py`:
- 30+ unit tests covering all schemas and core functions
- Integration tests for route imports
- Schema validation tests
- Database operation tests

Run tests:
```bash
pytest tests/test_cognitive_phase4.py -v
```

---

## Future Enhancements

1. **Multi-model preferences**: Store multiple communication styles per user
2. **Temporal confidence intervals**: Range estimates for cycle periods
3. **Cross-tenant learning**: Anonymized learning from other tenants (opt-in)
4. **Active learning**: Proactively ask users about preferences
5. **Predictive cycle detection**: ML-based forecasting of cycle changes
6. **Integration with Vector DB**: Semantic memory alongside relational storage
