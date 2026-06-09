# Phase 4 Integration Guide: Operational Intelligence

This guide explains how the three cognitive systems (Learning, Identity, Temporal) work together to enable self-improving, intelligent autonomous operations.

## System Interactions

### Learning System Feeds Identity System

```
Execution Outcome → Record quality_score
                  ↓
           Compute effectiveness trend
                  ↓
         Update agent performance profile
                  ↓
     Inform routing decisions (from learning)
                  ↓
    AI teammate recognizes: "Agent X is degrading"
                  ↓
    Surface proactive insight: "Consider switching to Agent Y"
```

**Example Flow:**
```python
# In workflow executor
outcome = OutcomeRecord(
    workflow_id="task-123",
    agent_id="agent-planner",
    quality_score=0.65,  # Below threshold
)
record(outcome)

# Learning system detects degradation
score = compute("agent-planner", "tenant-001")
if score.trend == "degrading":
    # Broadcast event
    _emit("learning:agent_degraded", "agent-planner", "tenant-001", 0.62)

# Teammate proactive engine picks up event
# Surfaces: "Agent-planner is degrading (0.62 → 0.58). Consider manual review."
```

---

### Identity System Enhances Temporal Scheduling

```
Detect user habits (when they typically work)
         ↓
    Recognize patterns: "Alice always reviews reports at 2pm"
         ↓
    Extract from relationship memory: "Alice cares about accuracy"
         ↓
    During temporal scheduling:
    - Bias deadlines toward times when Alice is typically working
    - Flag high-accuracy initiatives for Alice at her peak hours
```

**Example Flow:**
```python
# Teammate system detects habit
record_event("alice@acme.com", "tenant-001", "reporting")
habits = get_habits("alice@acme.com", "tenant-001")
# Returns: [HabitPattern(workflow_type="reporting", typical_hour=14, confidence=0.85)]

# Temporal system gets relationship context
ctx = get_context("alice@acme.com", "tenant-001")
# Returns: interaction_count=127, recent topics include "accuracy"

# Schedule initialization: prioritize reporting tasks at 2pm for Alice
initiatives = [
    {"id": "i1", "title": "Q3 Report", "deadline": tomorrow_2pm},
    {"id": "i2", "title": "Planning", "deadline": tomorrow_10am},
]
schedule = get_schedule(initiatives, "tenant-001")
# i1 (reporting at 2pm) gets higher priority due to habit matching
```

---

### Temporal System Drives Learning Feedback

```
Deadline approaching → Raise urgency
         ↓
   Agent executes under pressure
         ↓
  Outcome recorded with time_remaining flag
         ↓
  Quality score reflects deadline stress
         ↓
  Learning system: "Agent X performs worse under deadline pressure"
         ↓
  Routing suggestions: "Avoid assigning high-pressure tasks to Agent X"
```

**Example Flow:**
```python
# Temporal system detects deadline within 1 hour
deadline = list_upcoming("tenant-001", 1)[0]
urgency = compute_urgency(deadline["initiative_id"], 7, deadline["deadline_ts"])
# urgency.urgency = 95.2 (critical)

# Agent executes under pressure
outcome = OutcomeRecord(
    workflow_id=...,
    agent_id="agent-executor",
    success=True,
    quality_score=0.52,  # Lower than usual
    duration_ms=8500.0,  # Slower than usual
)
record(outcome)

# Learning system detects pattern
recent = get_recent("tenant-001", "agent-executor", limit=20)
# Last 5 outcomes under deadline pressure all have quality < 0.6
# Suggestion generated: "Reduce agent-executor assignment under deadline pressure"
```

---

## Message Bus Event Flow

All systems emit structured events to the message bus `/notifications` channel:

```
┌─────────────────────────────────────────────────────────────┐
│                   MESSAGE BUS: /notifications                │
└─────────────────────────────────────────────────────────────┘
         ↑         ↑              ↑              ↑
         │         │              │              │
    Learning   Teammate      Temporal      Executive
    System     System        System        System
         │         │              │              │
   Agent.degraded   │      Deadline.critical     │
   Agent.promoted   │      Deadline.missed       │
         │      Proactive.insight                │
         │      (habit, blocked, anomaly)        │
         │              │              │         │
         └──────────────┴──────────────┴─────────┘
                        ↓
                  Dashboard UI
                  Escalation Gate
                  Notification Service
                  Analytics Pipeline
```

### Event Schemas

**Learning Events:**
```json
{
  "event": "learning:agent_degraded",
  "agent_id": "agent-planner",
  "tenant_id": "tenant-001",
  "score": 0.58,
  "trend": "degrading"
}
```

**Teammate Events:**
```json
{
  "event": "teammate:proactive_insight",
  "tenant_id": "tenant-001",
  "insight": {
    "id": "insight-123",
    "title": "Initiative blocked",
    "body": "Project X waiting on approval",
    "insight_type": "blocked_initiative",
    "priority": 2
  }
}
```

**Temporal Events:**
```json
{
  "event": "temporal:deadline_critical",
  "tenant_id": "tenant-001",
  "initiative_id": "init-456",
  "hours_remaining": 18
}
```

---

## Multi-Tenant Data Flow

Each system enforces strict tenant isolation:

```
User Input (Tenant A)
    ↓
API Middleware extracts tenant_id from JWT
    ↓
Request.state.tenant_id = "tenant-A"
    ↓
Learning System: Uses tenant_id for outcome queries
Teammate System: Uses tenant_id for identity/habits
Temporal System: Uses tenant_id for deadline tracking
    ↓
Each system accesses ONLY tenant-A data
    ↓
Response isolated to tenant-A
```

**Example Multi-Tenant Safety:**
```python
# User from tenant-001 makes request
@router.get("/learning/status")
async def learning_status(req: Request):
    tid = _tenant(req)  # Extracts from JWT: "tenant-001"
    scores = get_all_scores(tid)  # Query: WHERE tenant_id = 'tenant-001'
    return {"agents": scores}

# User from tenant-002 makes request
# Same endpoint, different data returned (WHERE tenant_id = 'tenant-002')
```

---

## Real-World Scenario: Weekly Planning Cycle

Shows how all three systems orchestrate a weekly planning cycle:

### Day 1: Monday 10:00 AM

**User Action:** Alice logs in to plan the week

**Learning System:**
- Retrieves agent effectiveness scores from last week
- Identifies: planner-pro has 0.88 effectiveness (↑), executor-basic 0.61 (↓)

**Identity System:**
- Fetches Alice's identity context: 247 interactions, expert in strategy
- Detects habit: Alice always plans on Monday at 10am (confidence 0.92)
- Loads communication profile: prefers brief technical responses

**Temporal System:**
- Lists upcoming deadlines: 12 initiatives with deadlines this week
- Computes urgency: Q3-closure (critical, 5 days), regulatory (high, 7 days)

**Response to Alice:**
```json
{
  "week_overview": {
    "critical_initiatives": 2,
    "upcoming_count": 12,
    "recommended_focus": ["q3-closure", "regulatory-compliance"],
    "suggested_agents": {
      "planning": "planner-pro (↑ 0.88)",
      "execution": "executor-pro (↑ 0.89)"
    }
  },
  "ai_teammate": {
    "message": "Good morning! I've prepared your weekly plan. Based on last week's patterns, I've identified high-performers for critical deadlines."
  },
  "habits_detected": {
    "planning_monday_10am": "This is your typical planning time (92% confidence)"
  }
}
```

### Day 2-5: Execution

**Learning System (Background):**
- Records outcomes from agent executions
- Updates effectiveness scores continuously
- Detects: executor-basic struggling with deadline-pressure tasks

**Identity System (Background):**
- Records Alice's interactions during planning
- Updates her relationship memory with topics discussed
- Recognizes: Alice focuses heavily on risk mitigation

**Temporal System (Background):**
- Monitors deadlines every 60 seconds
- Escalates: Q3-closure now 3 days away (urgency 85+)
- Broadcasts: `temporal:deadline_critical` event

### Friday 4:00 PM: End-of-Week Review

**Alice Requests:** Weekly summary

**Response Synthesis (All Systems):**

```json
{
  "week_summary": {
    "initiatives_completed": 8,
    "on_track": 4,
    "at_risk": 1
  },
  "learning_insights": {
    "agent_changes": [
      {
        "agent": "executor-basic",
        "trend": "degrading",
        "score": 0.58,
        "recommendation": "Reduce deadline-pressure assignments"
      }
    ],
    "routing_suggestions": [
      {
        "from_agent": "executor-basic",
        "to_agent": "executor-pro",
        "quality_delta": 0.22,
        "confidence": 0.85
      }
    ]
  },
  "identity_insights": {
    "ai_teammate": {
      "name": "Aeternus",
      "interactions_this_week": 34,
      "focus_areas": ["risk mitigation", "regulatory compliance"],
      "persona_update": "Became more risk-aware through interactions with Alice"
    },
    "communication_preference_update": "Alice prefers bullet-point summaries"
  },
  "temporal_insights": {
    "cycles_detected": [
      {
        "workflow_type": "planning",
        "period_days": 7,
        "confidence": 0.89,
        "next_expected": "Monday 10am"
      }
    ],
    "next_critical_deadline": "q3-closure (60 hours remaining)"
  }
}
```

---

## API Call Sequencing

Typical AI system operation spans all three APIs:

```
GET /cognitive/learning/status
    → Assess agent health
        ↓
GET /cognitive/teammate/identity
    → Load AI identity + expertise
        ↓
GET /cognitive/teammate/habits/{user_id}
    → Get user operational patterns
        ↓
GET /cognitive/temporal/deadlines?hours_ahead=168
    → Get week's deadlines
        ↓
GET /cognitive/temporal/schedule
    → Generate optimized schedule
        ↓
POST /cognitive/learning/routing-suggestions/generate
    → Generate agent optimization suggestions
        ↓
POST /cognitive/learning/routing-suggestions/{id}/accept
    → User approves suggestion
        ↓
GET /cognitive/teammate/insights
    → Get proactive insights
        ↓
Response sent to user with:
  - AI identity
  - Recommended agents
  - Optimized schedule
  - Proactive alerts
  - Next steps
```

---

## Dashboard Integration Points

### Learning Dashboard
```
Agent Health Status:
  - agent-planner: 0.82 (improving) ✓
  - agent-executor: 0.58 (degrading) ⚠️
  
Routing Suggestions:
  [Accept] Switch task-type-X from executor-basic → executor-pro (+0.22)
  [Reject]
```

### Identity Dashboard
```
AI Teammate: Aeternus
- Formed: 342 interactions ago
- Expertise: Planning (97%), Execution (81%), Monitoring (73%)
- Personality: Risk-conscious, collaborative, detail-oriented

User Profiles:
  Alice: 247 interactions
    - Habit: Monday 10am planning (92% confidence)
    - Prefers: Brief technical responses
    - Focus: Risk mitigation
```

### Temporal Dashboard
```
Week Overview:
  Critical (< 24h):
    ⚠️ Q3 Closure — 18 hours remaining (urgency: 92)
  High Priority (1-3 days):
    • Regulatory Compliance — 52 hours remaining
  Normal (3+ days):
    ○ Q4 Planning — 168 hours remaining

Suggested Schedule:
  [1] Q3 Closure (critical)
  [2] Regulatory Compliance (high)
  [3] Q4 Planning (normal)
  [4] ...
```

---

## Monitoring & Observability

### Metrics to Track

**Learning System:**
- `learning.outcomes_recorded_total` — Total outcomes recorded
- `learning.effectiveness_average` — Mean agent effectiveness (0-1)
- `learning.agents_degraded` — Count of agents trending down
- `learning.routing_suggestions_accepted_rate` — % of suggestions accepted

**Identity System:**
- `teammate.interaction_count_total` — Total interactions recorded
- `teammate.habits_detected` — Number of habit patterns discovered
- `teammate.persona_synthesis_count` — Number of LLM persona updates
- `teammate.proactive_insights_generated` — Insights surfaced

**Temporal System:**
- `temporal.deadlines_tracked` — Active deadline count
- `temporal.deadline_miss_rate` — % of deadlines missed
- `temporal.urgency_average` — Mean urgency score (0-100)
- `temporal.cycles_detected` — Number of recurring patterns found

**System Health:**
- `cognitive.api_latency_ms` — Route response time
- `cognitive.error_rate` — Exception rate across APIs
- `cognitive.message_bus_events_published` — Events emitted

### Alerting Rules

```yaml
alert learning_agent_degrading:
  when: effectiveness.score < 0.6 AND trend == "degrading"
  duration: 5m
  action: surface_insight("Agent X degrading"), escalate_to_hitl

alert temporal_deadline_missed:
  when: deadline.status == "missed"
  duration: 1m
  action: emit_event("deadline_missed"), escalate_to_user

alert cognitive_api_slow:
  when: api_latency_p95 > 500ms
  duration: 10m
  action: log_performance_issue, alert_ops
```

---

## Testing Strategy

### Unit Tests
- Individual module function tests
- Schema instantiation tests
- Database operation tests

### Integration Tests
- Multi-module workflows
- Message bus event publishing
- Multi-tenant isolation

### System Tests
- End-to-end user workflows
- Concurrent user scenarios
- Load testing (1000+ QPS)

### Scenario Tests
- Weekly planning cycle
- Agent degradation detection
- Deadline escalation

---

## Troubleshooting Integration Issues

### Issue: Events not appearing in message bus
- Check: Message bus service is running
- Check: Event emission not wrapped in try/except silencing errors
- Check: Event channel name matches listener ("notifications")

### Issue: Routing suggestions not being generated
- Check: At least 50 outcome records per agent
- Check: Quality delta > 0.2 between agents
- Check: Call `generate_suggestions()` endpoint

### Issue: Habits not being detected
- Check: `record_event()` called on workflow start
- Check: Same workflow_type and hour appear 3+ times in 7 days
- Check: Confidence threshold (0.6) is met

### Issue: Deadlines not alerting
- Check: `DeadlineTracker` polling task is running
- Check: Deadline status is "pending" (not completed/archived)
- Check: deadline_ts is absolute timestamp

### Issue: Multi-tenant data leaking
- Check: All queries include `WHERE tenant_id = ?`
- Check: JWT token includes valid `tenant_id` claim
- Check: Middleware correctly extracts tenant_id

---

## Performance Optimization Tips

1. **Batch Outcome Recording**: Record multiple outcomes per transaction
2. **Cache Effectiveness Scores**: Memoize results for 60 seconds
3. **Async Cycle Detection**: Run FFT analysis in background worker
4. **Index Queries**: Use covered indexes for habit lookups
5. **Deadline Polling**: Run once per 60 seconds, not per request

---

## Future Integration Points

1. **Vector DB Integration**: Semantic memory for relationship context
2. **Real-Time Streaming**: WebSocket updates for metrics/insights
3. **Predictive Alerts**: ML-based anomaly detection
4. **Cross-Tenant Learning**: Anonymized learning aggregation
5. **Custom Metrics**: Domain-specific effectiveness formulas
