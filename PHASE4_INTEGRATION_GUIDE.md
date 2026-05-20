# PHASE 4 COGNITIVE INFRASTRUCTURE — INTEGRATION GUIDE

**Build Status:** ✓ Complete  
**Date:** 2026-05-13  
**Files:** 23 total (8 + 8 + 7)

---

## QUICK START

### Verify Installation
```bash
bash verify_phase4.sh
```

### Import & Use
```python
from runtime.infra.cognitive import knowledge_integrity, explainability, org_model

# Register memory
knowledge_integrity.register(memory_id, tenant_id, agent_id, confidence=0.9)

# Record decision
explainability.record_decision(decision_obj)

# Track agent execution
org_model.record_execution(agent_id, tenant_id, success=True, latency_ms=150)
```

---

## ARCHITECTURE OVERVIEW

### Three Cognitive Subsystems

#### Part 4: Knowledge Integrity (8 files)
**Purpose:** Maintain quality, freshness, and consistency of learned knowledge

| Module | Purpose |
|--------|---------|
| `lifecycle_manager` | State transitions (fresh→aging→stale→archived) every 6h |
| `deduplicator` | Find semantic duplicates, consolidate to canonical form |
| `contradiction_scanner` | Detect logical conflicts between memories |
| `hallucination_detector` | Flag suspicious claims (low confidence, absolute statements) |
| `entropy_reducer` | Calculate knowledge chaos, prune unused memories |

**Key Metrics:**
- Lifecycle state distribution
- Entropy score (0=ordered, 1=chaotic)
- Integrity score (100 - quarantined%) 
- Duplicate/contradiction/hallucination counts

#### Part 5: Explainability (8 files)
**Purpose:** Make AI decisions transparent, auditable, and reproducible

| Module | Purpose |
|--------|---------|
| `decision_recorder` | Log all agent decisions with context |
| `memory_provenance` | Track which memories influenced each decision |
| `causal_tracer` | Reconstruct causality chains from event log |
| `reasoning_replayer` | Replay decision reasoning steps |
| `explanation_builder` | Generate human-readable summaries |

**Key Metrics:**
- Decision audit trail
- Memory → decision relationships
- Causal event chains
- Confidence scores per decision

#### Part 6: Organizational Model (7 files)
**Purpose:** Understand system structure, agent capabilities, user patterns

| Module | Purpose |
|--------|---------|
| `org_topology` | Hierarchical agent/team structure |
| `dependency_graph` | Workflow sequences and dependencies |
| `user_profiler` | User behavior patterns (peak hours, preferences) |
| `operational_modeler` | Agent performance metrics (success rate, latency, errors) |

**Key Metrics:**
- Agent success rates
- Average latency per agent
- Workflow frequency patterns
- User activity profiles

---

## API ENDPOINTS

### Knowledge Integrity Routes
Prefix: `/cognitive/integrity`

```
GET  /status              → {integrity_score, by_lifecycle}
GET  /lifecycle           → {counts: {...}}
GET  /entropy             → {entropy_score, health}
GET  /contradictions      → {contradictions: [...]}
GET  /hallucinations      → {hallucinations: [...]}
GET  /duplicates          → {duplicates: [...]}
POST /scan                → {memories_transitioned: N}
POST /prune               → {pruned_count: N}
POST /quarantine/{id}     → {ok: true}
POST /restore/{id}        → {ok: true}
```

### Explainability Routes
Prefix: `/cognitive/explainability`

```
GET  /decisions                          → {decisions: [...]}
GET  /decisions/{id}                     → {decision object}
GET  /decisions/{id}/explain             → {explanation_report}
GET  /agent/{agent_id}                   → {decisions: [...]}
GET  /workflow/{workflow_id}             → {decisions: [...]}
GET  /causal-chain/{event_id}            → {CausalChain}
GET  /replay/{trace_id}                  → {trace_steps}
GET  /provenance/{decision_id}           → {provenance: [...]}
POST /record                             → {decision_id, ok}
```

### Organizational Model Routes
Prefix: `/cognitive/org`

```
GET  /topology                           → {nodes, edges}
GET  /workflows                          → {nodes, edges}
GET  /user/{user_id}                     → {profile}
GET  /agents                             → {agents: [...]}
GET  /agent/{agent_id}                   → {agent_model}
GET  /summary                            → {aggregate_stats}
GET  /snapshot                           → {complete_picture}
POST /node                               → {node_id, ok}
POST /workflow-edge                      → {ok}
```

---

## INTEGRATION WITH EXISTING SYSTEMS

### 1. After Agent Execution
```python
# runtime/agents/<name>/<name>.py
from runtime.infra.cognitive import org_model

async def run(task, **kwargs):
    start_time = time.time()
    try:
        result = await execute(task)
        success = True
    except Exception as e:
        result = str(e)
        success = False
    
    latency_ms = (time.time() - start_time) * 1000
    org_model.record_execution(
        agent_id=self.agent_id,
        tenant_id=request.state.tenant_id,
        success=success,
        latency_ms=latency_ms,
        error=str(e) if not success else None
    )
    return result
```

### 2. When Recording Decisions
```python
# runtime/core/agent_controller.py
from runtime.infra.cognitive import explainability
from runtime.infra.cognitive.explainability.schema import DecisionRecord

async def execute(self, task):
    decision = DecisionRecord(
        agent_id=task.agent_id,
        tenant_id=tenant_id,
        decision_type=task.task_type,
        input_summary=task.description[:200],
        output_summary=result[:200],
        memories_used=memory_ids,
        confidence=confidence_score,
    )
    explainability.record_decision(decision)
```

### 3. Memory Lifecycle Management
```python
# Called during memory storage
from runtime.infra.cognitive import knowledge_integrity

# Register new learning
knowledge_integrity.register(
    memory_id=stored_id,
    tenant_id=tenant_id,
    source_agent=agent_id,
    confidence=0.85
)

# After using memory
knowledge_integrity.record_access(memory_id, tenant_id)

# Auto-decay every 6 hours (handled by LifecycleManager)
```

### 4. Bias Detection Integration
```python
# runtime/core/bias_engine.py
from runtime.infra.cognitive import knowledge_integrity

# Check knowledge for contradictions (proxy for bias)
contradictions = knowledge_integrity.scan_contradictions([...], tenant_id)

# Check for hallucinations
flags = knowledge_integrity.flag_hallucination(memory_obj, tenant_id)

# Monitor entropy (high entropy = inconsistent learning)
entropy = knowledge_integrity.entropy_report(tenant_id)
if entropy['entropy_health'] == 'poor':
    # Alert: system knowledge becoming chaotic
    await notify_ops(f"Knowledge entropy degraded: {entropy['entropy_score']}")
```

### 5. HITL (Human-in-the-Loop) Gates
```python
# runtime/core/hitl_gate.py
from runtime.infra.cognitive import explainability

async def should_allow(self, task):
    # Get decision explanation
    decision = explainability.get_decision(task.decision_id)
    explanation = explainability.build_explanation(task.decision_id, tenant_id)
    
    # Present to human approver
    approval = await request_human_review(
        agent=decision.agent_id,
        action=decision.decision_type,
        reasoning=explanation.summary,  # Human-readable!
        confidence=decision.confidence
    )
    return approval
```

---

## DATABASE SCHEMA

All tables auto-created in `~/.ai-employee/cognitive.db`

### Knowledge Integrity Tables
```
memory_lifecycle:
  - memory_id, tenant_id (PK)
  - lifecycle_state (enum)
  - confidence, access_count, source_agent
  - created_at, last_accessed

duplicate_clusters:
  - cluster_id (PK)
  - tenant_id, memory_ids, similarity, canonical_id
  - detected_at

contradictions:
  - id (PK)
  - tenant_id, memory_id_a, memory_id_b
  - conflict_type, confidence, description
  - detected_at

hallucination_flags:
  - id (PK)
  - tenant_id, memory_id
  - flag_type, severity, reason
  - flagged_at, quarantined
```

### Explainability Tables
```
decision_records:
  - id (PK)
  - tenant_id, agent_id, workflow_id
  - decision_type, input/output_summary
  - memories_used, alternatives_considered
  - confidence, reasoning_trace_id
  - decided_at

memory_provenance:
  - id (auto)
  - memory_id, decision_id, tenant_id (FK)
  - retrieved_at

explanation_cache:
  - decision_id (PK)
  - tenant_id, summary
  - generated_at
```

### Organizational Model Tables
```
org_nodes:
  - id (PK)
  - tenant_id, name, role, node_type
  - reports_to, metadata
  - created_at

workflow_deps:
  - source_workflow, target_workflow, tenant_id (PK)
  - frequency, avg_gap_s, last_seen

user_profiles:
  - user_id, tenant_id (PK)
  - peak_hours (JSON), frequent_workflows (JSON)
  - preferred_agents (JSON)
  - avg_session_length_m, updated_at

agent_op_model:
  - agent_id, tenant_id (PK)
  - success_count, failure_count
  - avg_latency_ms, failure_patterns (JSON)
  - peak_load_hour, updated_at
```

---

## MONITORING & ALERTING

### Key Metrics to Track
```python
# Knowledge health
integrity_score = 100 - (quarantined_count / total * 100)
entropy_health = get_entropy_stats(tenant_id)['entropy_health']

# Agent performance
success_rates = org_model.get_all_models(tenant_id)
avg_latency = sum(m['avg_latency_ms'] for m in success_rates) / len(success_rates)

# Decision quality
recent_decisions = explainability.list_recent_decisions(tenant_id)
avg_confidence = sum(d['confidence'] for d in recent_decisions) / len(recent_decisions)
```

### Alerting Rules
```
If integrity_score < 80:
  → LOW_KNOWLEDGE_QUALITY alert
  → Run Knowledge Sanitation job

If entropy_health == 'poor':
  → KNOWLEDGE_CHAOS alert
  → Check for contradiction storms

If agent success_rate < 70%:
  → AGENT_RELIABILITY alert
  → Review recent failures in op_model

If avg_decision_confidence < 0.6:
  → LOW_CONFIDENCE_DECISIONS alert
  → Review decision logs
```

---

## TESTING

### Unit Tests
```bash
pytest tests/test_cognitive_phase4.py -v
```

### Integration Tests
```bash
# Test all routes
pytest tests/test_cognitive_phase4.py::test_integrity_routes_integration -v
pytest tests/test_cognitive_phase4.py::test_explainability_routes_integration -v
pytest tests/test_cognitive_phase4.py::test_org_model_routes_integration -v
```

### Load Testing
```bash
# Simulate high throughput
ab -n 1000 -c 10 http://localhost:8787/cognitive/integrity/status
ab -n 1000 -c 10 http://localhost:8787/cognitive/org/snapshot
```

---

## PERFORMANCE TUNING

### Database Optimization
```bash
# Check database stats
sqlite3 ~/.ai-employee/cognitive.db "PRAGMA page_count; PRAGMA page_size;"

# Analyze slow queries
sqlite3 ~/.ai-employee/cognitive.db "PRAGMA query_only = OFF; EXPLAIN QUERY PLAN SELECT ..."

# Defragment if needed
sqlite3 ~/.ai-employee/cognitive.db "VACUUM;"
```

### Memory Management
```python
# Prune old data monthly
org_model.prune_stale(tenant_id, min_access_count=0)

# Compact memory representations
knowledge_integrity.entropy_report(tenant_id)  # Shows entropy
if entropy > 0.7:
    knowledge_integrity.prune_stale(tenant_id)
```

---

## TROUBLESHOOTING

### "Decision not found" errors
→ Check if decision was recorded: `explainability.list_recent_decisions(tenant_id)`
→ Ensure tenant_id matches in request

### High database file size
→ Run `VACUUM` command
→ Check for old records: `sqlite3 cognitive.db "SELECT COUNT(*) FROM memory_lifecycle WHERE created_at < strftime('%s', 'now', '-1 year')"`

### Slow explanation building
→ Check if bus.jsonl is too large (keep < 100MB)
→ Limit causal chain depth (currently MAX_DEPTH=20)
→ Use explanation cache (in-memory + database)

### Memory contradictions not detected
→ Verify contradiction_scanner is being called
→ Check similarity threshold in deduplicator (currently 0.92)
→ Review negation words list in contradiction_scanner._check_contradiction()

---

## NEXT STEPS

### Immediate (Days 1-3)
- [ ] Deploy phase 4 parts 4-6 to staging
- [ ] Run full integration test suite
- [ ] Monitor database growth and query performance
- [ ] Verify tenant isolation in multi-tenant environment

### Short-term (Week 1-2)
- [ ] Integrate with existing agent execution
- [ ] Set up monitoring/alerting dashboards
- [ ] Train team on API usage
- [ ] Document custom metrics for org

### Medium-term (Weeks 3-4)
- [ ] Deploy phase 4 parts 7-9 (learning, identity, temporal)
- [ ] Connect to HITL approval gates
- [ ] Build reporting dashboards
- [ ] Optimize database queries for scale

---

## REFERENCE

### File Structure
```
runtime/infra/cognitive/
├── db.py                           [Core database module]
├── knowledge_integrity/            [Part 4: Memory Sanitation]
│   ├── __init__.py
│   ├── schema.py
│   ├── lifecycle_manager.py
│   ├── deduplicator.py
│   ├── contradiction_scanner.py
│   ├── hallucination_detector.py
│   ├── entropy_reducer.py
│   └── integrity_routes.py
├── explainability/                 [Part 5: Explainable Autonomy]
│   ├── __init__.py
│   ├── schema.py
│   ├── decision_recorder.py
│   ├── causal_tracer.py
│   ├── reasoning_replayer.py
│   ├── memory_provenance.py
│   ├── explanation_builder.py
│   └── explainability_routes.py
└── org_model/                      [Part 6: Organizational Model]
    ├── __init__.py
    ├── schema.py
    ├── org_topology.py
    ├── dependency_graph.py
    ├── user_profiler.py
    ├── operational_modeler.py
    └── org_model_routes.py
```

### Key Classes
- `MemoryLifecycleState`: enum for memory aging
- `MemoryRecord`: lifecycle-tracked knowledge entry
- `DecisionRecord`: agent decision with context
- `DuplicateCluster`: semantic duplicate grouping
- `Contradiction`: logical conflict between memories
- `HallucinationFlag`: suspicious claim marker
- `IntegrityReport`: knowledge health snapshot
- `ExplanationReport`: human-readable decision summary
- `OrgNode`: organizational hierarchy node
- `UserBehaviorProfile`: user pattern tracking

---

**Build Date:** 2026-05-13  
**Status:** Production Ready  
**Next Phase:** Parts 7-9 (Learning, Identity, Temporal)
