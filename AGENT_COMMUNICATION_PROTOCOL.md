# Agent Communication Protocol

**Purpose:** Ensure all agents efficiently communicate with the orchestrator, brain, and each other.  
**Status:** Reference guide for all agent development.

---

## Communication Architecture

```
┌────────────────────────────────────┐
│       ORCHESTRATOR (Hub)           │
│  - Manages task queue              │
│  - Routes tasks to agents          │
│  - Collects results                │
│  - Coordinates parallel execution  │
└───────────┬────────────────────────┘
            │
    ┌───────┼───────┐
    │       │       │
┌──┴──┐  ┌─┴──┐  ┌─┴──┐
│Agent│  │Agent│  │Agent│
│  A  │  │  B │  │  C │
└──┬──┘  └─┬──┘  └─┬──┘
    │       │       │
    └───────┼───────┘
            │
    ┌───────┴──────────┐
    │                  │
┌──┴──────┐      ┌────┴────┐
│  BRAIN  │      │ KNOWLEDGE│
│         │      │  STORE   │
│ (learn) │      │ (context)│
└─────────┘      └──────────┘
```

---

## 1. Agent → Orchestrator Communication

### Input: Task Request

Agents receive work from the orchestrator as a standardized payload:

```python
{
    "task_id": "uuid",                    # Unique task identifier
    "agent_id": "email_ninja",             # Which agent to run
    "input": {                             # Agent-specific input
        "product": "...",
        "audience": "...",
        "sequence_length": 3,
        "task": "..."
    },
    "context": {                           # Shared context
        "user_id": "user:123",
        "conversation_id": "conv:456",
        "previous_results": {...},         # From prior agents in the workflow
        "time_budget_ms": 30000            # Max execution time
    }
}
```

### Output: Task Result

Agents return results in this standardized format:

```python
{
    "task_id": "uuid",                     # Echo back the task ID
    "agent_id": "email_ninja",             # Which agent executed
    "status": "ok" | "error" | "incomplete",
    "result": {                            # Agent-specific results
        "sequence": [...],
        "metrics": {...}
    },
    "tokens_used": 1234,                   # For billing/tracking
    "execution_time_ms": 2500,             # For performance tracking
    "error": null | "error message",
    "brain_updates": {                     # What to save to brain
        "key_findings": [...],
        "metrics": {...},
        "next_steps": [...]
    },
    "next_agent": "sales_closer" | null,   # Who should handle next?
    "confidence": 0.92                     # How confident in this result?
}
```

---

## 2. Agent → Brain Communication

### Adding Knowledge

Agents feed findings into the brain for learning and context:

```python
from brain.intelligence import get_intelligence

brain = get_intelligence()

# Store learnings from this task
brain.store_learning({
    "agent_id": "lead_hunter",
    "learning_type": "lead_quality_signal",
    "finding": "recent hiring in tech sector correlates with sales expansion",
    "confidence": 0.88,
    "evidence": ["3 of 5 tested companies with +20 hires also grew sales team"],
    "timestamp": datetime.now(timezone.utc).isoformat()
})

# Update context for future tasks
brain.update_context(user_id, "lead_search", {
    "last_searched_niches": ["SaaS", "MarTech"],
    "best_performing_angles": ["growth metrics", "hiring patterns"],
    "low_performing_angles": ["generic product benefits"]
})
```

### Retrieving Context

Agents query the brain for relevant context:

```python
# Get user intelligence
profile = brain.get_profile(user_id)  # Preferences, tone, history
niches = brain.get_past_searches(user_id)  # What they've searched before
learnings = brain.retrieve_learnings("lead_quality_signal", limit=5)  # Top insights

# Use this to personalize and improve performance
if "growth_metrics" in learnings:
    use_growth_signals_in_lead_research()
```

---

## 3. Agent → Agent Communication

### Via Orchestrator (Recommended)

Agents don't communicate directly. They coordinate through the orchestrator:

```
Agent A: "I found 10 leads. Next, Agent B should email them."
         ↓
Orchestrator: Routes the 10 leads to Agent B's input
         ↓
Agent B: Receives leads in context.previous_results
         ↓
Agent B: Uses those leads to generate emails
```

### Accessing Prior Results

Always check `context.previous_results` for inputs from earlier agents:

```python
def execute(self, payload):
    prior_leads = payload.get("context", {}).get("previous_results", {})
    leads = prior_leads.get("leads", [])
    
    if not leads:
        return {"error": "No leads provided from previous agent"}
    
    # Process the leads...
```

---

## 4. Status Reporting

### For Long-Running Tasks

Agents should report progress to the orchestrator via events:

```python
from core.bus import SimpleMessageBus

bus = SimpleMessageBus()

for i, lead in enumerate(leads):
    # Process lead...
    
    if i % 10 == 0:  # Report every 10 leads
        bus.publish('agent:progress', {
            'agent_id': self.agent_id,
            'task_id': task_id,
            'progress_percent': (i / len(leads)) * 100,
            'status': f'Processing {i} of {len(leads)} leads'
        })
```

### Subscribe to Events

Agents can subscribe to orchestrator events:

```python
bus.subscribe('orchestrator:stop_requested', self.handle_stop)
bus.subscribe('orchestrator:timeout_warning', self.save_and_prepare_partial)
```

---

## 5. Error Handling & Recovery

### Report Errors Clearly

```python
{
    "status": "error",
    "error": "API rate limit exceeded",
    "error_code": "RATE_LIMIT",
    "recovery_action": "retry in 60 seconds",
    "partial_result": {
        "processed": 25,
        "total": 50,
        "completed": [...]  # What we got before failure
    }
}
```

### Graceful Degradation

If an agent can't complete perfectly, provide partial results:

```python
def execute(self, payload):
    try:
        return analyze_all_data(data)
    except DataQualityError as e:
        # Return best effort with confidence score
        return {
            "result": partial_analysis,
            "confidence": 0.65,
            "data_quality_issue": str(e),
            "note": "Results based on 70% of data; 30% had quality issues"
        }
```

---

## 6. Context Passing: Best Practices

### Minimal & Relevant

Only pass context needed by downstream agents:

```python
# BAD: Pass everything (bloats messages, confuses agents)
return {
    "result": result,
    "full_execution_log": 10_000_char_log,
    "all_intermediate_values": big_dict,
    "raw_api_responses": huge_list
}

# GOOD: Pass refined results + decision metadata
return {
    "result": result,
    "reasoning": "Chose option A because...",
    "alternatives_considered": ["B", "C"],
    "confidence": 0.92,
    "next_agent_needs": ["Contact info from result above"]
}
```

### Clear Next Steps

Always signal what comes next:

```python
return {
    "result": final_leads,
    "next_agent": "email_ninja",  # Who should process this?
    "next_agent_input_format": {  # What format they expect
        "leads": "array of {name, company, contact}",
        "template": "cold outreach sequence"
    },
    "urgency": "high"  # Help orchestrator prioritize
}
```

---

## 7. Logging & Observability

### Automatic Logging

Base agent logs all execution:

```python
# Already handled by BaseAgent.run()
{
    "agent": "email_ninja",
    "timestamp": "2026-04-27T10:30:00Z",
    "status": "ok",
    "input": {...},
    "output": {...},
    "duration_ms": 2500,
    "tokens_used": 1234
}
```

### Custom Logging

Add specific insights for monitoring:

```python
self._log({
    "agent": self.agent_id,
    "event": "discovery_insight",
    "message": "Found that technical co-founders respond better to technical CTAs",
    "confidence": 0.88,
    "sample_size": 47
})
```

---

## 8. Performance Metrics

### What Every Agent Should Track

```python
{
    "tokens_used": 1234,              # LLM costs
    "execution_time_ms": 2500,        # Speed (for timeouts)
    "quality_score": 0.92,            # Accuracy of results
    "confidence_interval": (0.87, 0.97),  # Statistical confidence
    "cache_hit": true,                # Did we use cached knowledge?
    "dependencies_resolved": true     # All required context available?
}
```

### Sample Size & Statistical Validity

```python
# Always report sample size with metrics
{
    "average_lead_score": 0.75,
    "sample_size": 47,  # Important!
    "confidence": "This score is statistically valid for n=47",
    "caveat": "Results may not apply to niches outside SaaS"
}
```

---

## 9. Integration Checklist for New Agents

When creating a new agent:

- [ ] **Input:** Accept standardized task payload with context
- [ ] **Output:** Return standardized result format with status + result
- [ ] **Brain:** Store learnings and retrieve relevant context
- [ ] **Orchestrator:** Signal next agent and input format needed
- [ ] **Logging:** Implement `_log()` calls for observability
- [ ] **Errors:** Return error status with recovery action
- [ ] **Partial Results:** Can degrade gracefully if incomplete
- [ ] **Metrics:** Track execution time, tokens, confidence
- [ ] **Context Passing:** Include reasoning, confidence, next steps
- [ ] **System Prompt:** Detailed, professional prompt with responsibilities

---

## 10. Common Patterns

### Pattern A: Serial Workflow

```
Lead Hunter → Email Ninja → Send → Track Results
      ↓
   Brain logs learnings
      ↓
   Orchestrator orchestrates sequence
```

**Implementation:**
```python
# Lead Hunter returns:
{"result": leads, "next_agent": "email_ninja", ...}

# Orchestrator sees next_agent, routes to Email Ninja

# Email Ninja receives leads in context.previous_results
leads = payload['context']['previous_results']['result']
```

### Pattern B: Parallel Enrichment

```
                    ↓ Research Agent
Lead ID ────────┬→ ↓ Web Crawler
                    ↓ News Monitor
                    ↓
            Orchestrator (Collects all)
                    ↓
              Enriched Lead
```

**Implementation:**
```python
# Lead ID goes to multiple agents in parallel
# Orchestrator waits for all responses
# Combines: {research: {...}, web: {...}, news: {...}}
# Passes combined context to next agent
```

### Pattern C: Decision Tree

```
Lead Score → IF high: Email Ninja
          → IF medium: Nurture Queue
          → IF low: Monitor
```

**Implementation:**
```python
# Lead Scorer returns confidence + score
# Orchestrator checks score, routes accordingly
return {
    "result": {"score": 0.85},
    "next_agent": "email_ninja" if score > 0.75 else "nurture_bot",
    "confidence": 0.92
}
```

---

## References

- **Orchestrator:** `runtime/core/agent_controller.py`
- **Brain:** `runtime/brain/intelligence.py`
- **Message Bus:** `runtime/core/bus.py`
- **Base Agent:** `runtime/agents/base.py`
- **Unified Pipeline:** `runtime/core/unified_pipeline.py`

---

**Version:** 1.0  
**Last Updated:** 2026-04-27  
**Owner:** Ultron Agent Architecture
