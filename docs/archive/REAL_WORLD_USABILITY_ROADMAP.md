# Real-World Usability Roadmap

**Purpose:** Transform Ultron from a capable system into a production-grade platform that users actually enjoy using and trust.  
**Timeline:** Phased improvements for immediate wins → long-term stability  
**Owner:** All teams  

---

## Current State Assessment

### What Works Well
- Core agent execution pipeline is solid (unified pipeline, orchestrator, brain integration)
- LLM backends work (Anthropic, OpenRouter, Ollama)
- WebSocket real-time updates functional
- Voice/tone is now humanized (not robotic)
- First-time setup detection ready
- Task progress tracking architecture in place

### What Needs Improvement
1. **Visibility & Feedback** — Users don't see what's happening during long tasks
2. **Error Recovery** — Failures are silent or cryptic; no graceful fallbacks
3. **Performance** — Multi-step tasks can feel slow without progress signals
4. **Trust** — System feels "black box"; users can't verify quality
5. **Configuration** — Setting up models/keys is not discoverable
6. **Observability** — No user-facing logs or task history
7. **Reliability** — No retry logic, timeout handling, or fallback strategies
8. **Mobile Experience** — UI works but not optimized for phone/tablet
9. **Onboarding** — First-time users don't know what the system can do
10. **Limits** — No clear boundaries on task complexity, time, or cost

---

## Phase 1: Critical Foundations (This Sprint)

### 1.1 Live Task Progress in Chat (In Progress → Complete)

**Status:** Architecture documented; needs implementation  
**What:** Display live step-by-step progress in chat messages as tasks execute

```
┌─────────────────────────────────────────┐
│ Analyzing your request...                │
│                                         │
│ ○ Classifying intent      [0.2s]        │
│ ● Retrieving context     [2.5s →]       │
│ ○ Generating response                   │
│ ○ Validating output                     │
│                                         │
│ Step 2/4 • Estimated: 8s remaining      │
└─────────────────────────────────────────┘
```

**Owners:** Frontend (ChatPanel), Backend (task tracking)  
**Effort:** 2-3 days

**Tasks:**
- Wire TaskProgressBlock component into chat message rendering
- Backend: emit step progress events during unified pipeline execution
- Real-time WebSocket updates for step state changes
- Visual polish: animations, color coding, time estimates

**Success Criteria:**
- Long tasks show multi-step progress in real-time
- Users can see which agent is running and how long it's taking
- No blocking — chat stays responsive during execution

---

### 1.2 Error Recovery & Graceful Degradation

**Status:** Needs implementation  
**What:** When agents fail, show users what went wrong and what happens next

**Implementation:**

```python
# In agent response validation (orchestrator.py)
class AgentResult:
    status: str  # 'success' | 'partial' | 'failed'
    confidence: float  # 0.0-1.0
    result: dict
    errors: list[str]
    fallback_action: str  # "using cached result", "trying alternate agent", "asking user"
    retry_strategy: str  # "auto-retry at 15s", "manual retry", "skip"
```

**User-Facing Behavior:**
- Agent fails → show clear error in chat with context
- If fallback exists → apply it (use cache, try alternate agent)
- If critical → ask user for input (e.g., "Want me to try with fewer leads?")
- All errors logged for troubleshooting

**Owners:** Backend (agents, orchestrator), Frontend (error UI)  
**Effort:** 3-4 days  

---

### 1.3 Task History & Visibility

**Status:** Partial (bus logs exist; needs UI)  
**What:** Users can see what they asked, what happened, and what the results were

**Implementation:**

**Backend:** `/api/history` endpoint returns last 50 tasks with:
```json
{
  "task_id": "uuid",
  "timestamp": "2026-04-27T14:30:00Z",
  "input": "Find SaaS leads in us",
  "status": "completed" | "failed" | "partial",
  "duration_ms": 12500,
  "agent_sequence": ["lead_hunter", "lead_scorer", "email_ninja"],
  "result_preview": "Found 47 leads, 23 high-quality",
  "cost_estimate_usd": 0.15,
  "confidence": 0.92
}
```

**Frontend:** New "History" tab in sidebar showing:
- Search/filter by agent, date, status
- Click to expand task details
- "Rerun with same settings" button
- Cost breakdown per task

**Owners:** Backend (history API), Frontend (sidebar tab)  
**Effort:** 2-3 days

---

## Phase 2: User Experience Polish (1 Week)

### 2.1 Model/Provider Selection UI

**Status:** API exists; needs frontend improvement  
**What:** Make it trivial to switch between Claude/OpenRouter/Ollama

**Current State:** Settings page has basic dropdowns  
**Needed:** 
- Visual indicators showing which models are available right now
- One-click key setup (generate API key links)
- Test button ("Verify this works")
- Estimated cost per task displayed upfront

**Owners:** Frontend  
**Effort:** 1 day

---

### 2.2 Onboarding Wizard

**Status:** First-run detection exists; needs guidance  
**What:** New users see a 3-minute setup tour

**Flow:**
1. **Welcome screen** — "Hi! I'm Ultron. Here's what I can do." (5 sec)
2. **Set your model** — "Pick Claude, OpenRouter, or local Ollama" (30 sec)
3. **Add API key** — "Grab your key from anthropic.com" (1 min)
4. **Try a sample** — "Ask me something simple to test" (1.5 min)
5. **You're ready!** — "Explore the dashboard or ask your first question"

**Owners:** Frontend, Backend (step progression API)  
**Effort:** 2-3 days

---

### 2.3 Mobile Responsiveness

**Status:** Web UI exists; tablet/phone not tested  
**What:** Optimize layout for portrait/small screens

**Changes:**
- Stack chat + sidebar vertically on mobile
- Collapse Settings into hamburger menu
- Task progress block uses smaller fonts but same info
- Buttons are thumb-sized (48px+)

**Owners:** Frontend  
**Effort:** 1-2 days

---

## Phase 3: Trustworthiness & Transparency (2 Weeks)

### 3.1 Confidence Scoring

**Status:** Agents return confidence; not displayed  
**What:** Show users how sure we are about results

**Example:**

```
✓ Found 47 leads
  Confidence: 87% (based on data freshness + validation rate)
  
⚠ 5 leads missing contact info
  Confidence: 92% (we're sure about this limitation)
  
→ Recommendation: Enrich these 5 before outreach
```

**Owners:** Backend (confidence calculation), Frontend (display)  
**Effort:** 2-3 days

---

### 3.2 Quality Metrics per Agent

**Status:** Partial (metrics in logs)  
**What:** Users can see how well each agent is performing

**Dashboard Widget:**
```
Agent Performance (Last 30 days)
┌─────────────────────────────────┐
│ Lead Hunter       ✓✓✓  92%       │
│ Email Ninja       ✓✓   74%       │
│ Sales Closer      ✓✓✓  88%       │
│ Data Analyst      ✓✓✓  96%       │
└─────────────────────────────────┘
[View details] [Switch agent]
```

**Owners:** Backend (metrics aggregation), Frontend (dashboard widget)  
**Effort:** 2-3 days

---

### 3.3 Cost Transparency

**Status:** Estimated costs exist in logs  
**What:** Show users exactly what they're paying for

**Implementation:**
- Cost estimate before task execution ("This will cost ~$0.32")
- Actual cost in task history
- Monthly usage report
- Cost breakdown by agent and model

**Owners:** Backend (cost tracking), Frontend (cost UI)  
**Effort:** 2-3 days

---

## Phase 4: Reliability & Performance (2-3 Weeks)

### 4.1 Timeout Management

**Status:** Basic timeouts exist; needs graceful handling  
**What:** Tasks that take too long fail gracefully with partial results

**Implementation:**
```python
# orchestrator.py
PHASE_TIMEOUTS = {
    'classify': 5,           # 5 second max
    'retrieve': 10,          # 10 seconds max
    'generate': 30,          # 30 seconds max (LLM calls)
    'validate': 5,
}

# When timeout approaches, agent gets warning:
# "You have 5s left. Return best-effort results now or I'll timeout."
```

**Owners:** Backend (orchestrator, agent timeout signaling)  
**Effort:** 2-3 days

---

### 4.2 Retry Strategy & Exponential Backoff

**Status:** No retry logic  
**What:** Failed tasks automatically retry with backoff

**Rules:**
- Transient errors (rate limit, timeout): auto-retry after 2s, 5s, 10s
- Agent failure: try alternate agent if available
- Critical failure: ask user
- Max 3 retries per task

**Owners:** Backend (orchestrator)  
**Effort:** 2 days

---

### 4.3 Caching & Memory Optimization

**Status:** Partial (brain exists; not optimized)  
**What:** Reuse previous results to speed up repeated tasks

**Example:**
```
User: "Find SaaS leads in the US"
  → Agent checks brain: "I found these last week, confidence 0.8"
  → Return cached + mark as potentially stale
  → Refresh in background if older than 7 days

User: "Find SaaS leads in US but new ones only"
  → Run full search, but use cached as baseline for "new" detection
```

**Owners:** Backend (brain, cache layer)  
**Effort:** 3-4 days

---

## Phase 5: Advanced Features (Following Sprints)

### 5.1 A/B Testing Framework (Item #4)

**Goals:**
- Test different agent approaches (style A vs. B)
- Measure user engagement/satisfaction
- Auto-optimize based on results

**Implementation:**
```python
class ABTest:
    test_id: str
    variant: str  # "A" or "B"
    agent_id: str
    variant_params: dict  # system prompt tweaks, model choice, etc.
    metrics: dict  # engagement, satisfaction, quality
    
# Usage:
task = orchestrator.run_task(
    input="...",
    ab_test="lead_hunter_v2",  # A/B test lead hunter variants
)
# Logs which variant ran
# Tracks outcome metrics
```

**Owners:** Backend (test harness), Frontend (variant selection)  
**Effort:** 3-4 days

---

### 5.2 Emotion-Aware Response Generation (Item #5)

**Goals:**
- Detect user emotion (frustrated, confused, happy, goal-focused)
- Adjust tone and detail level accordingly

**Implementation:**
```python
def analyze_user_emotion(message: str) -> str:
    """Return: 'frustrated' | 'confused' | 'satisfied' | 'focused'"""
    # Simple signals:
    # - Exclamation marks + rephrasing = frustrated
    # - Question marks + unclear phrasing = confused
    # - "thanks", "great", "perfect" = satisfied
    # - Specific requests = focused
    
    prompt = f"Classify user emotion: '{message}'"
    emotion = llm.complete(prompt)
    return emotion

def adjust_response_for_emotion(base_response: str, emotion: str) -> str:
    """Adjust detail level and tone based on emotion"""
    if emotion == 'frustrated':
        return base_response + "\n\n💡 Tip: Try asking differently or use fewer criteria."
    elif emotion == 'confused':
        return base_response + "\n\n📚 Need more detail? I can explain any part in depth."
    elif emotion == 'satisfied':
        return base_response + "\n\nGlad that worked! Ask me anything else."
    return base_response
```

**Owners:** Backend (emotion detection), all agents (response adjustment)  
**Effort:** 3-4 days

---

### 5.3 User Feedback Loop

**Status:** No feedback mechanism  
**What:** Users can rate results and provide feedback for improvement

**Implementation:**
```
After each response:
┌──────────────────────────────────┐
│ ✓ Helpful? Rate this response:   │
│ [👎] [👌] [👍]  [💬 Feedback]    │
│                                  │
│ → Stores feedback in memory      │
│ → Train on good/bad patterns     │
│ → Improves similar future tasks  │
└──────────────────────────────────┘
```

**Owners:** Frontend (feedback UI), Backend (feedback ingestion + learning)  
**Effort:** 2-3 days

---

## Implementation Checklist

### Week 1 (Phase 1)
- [ ] TaskProgressBlock component integration
- [ ] Error recovery & graceful degradation
- [ ] Task history API + UI

### Week 2 (Phase 2)
- [ ] Model selection UI improvements
- [ ] Onboarding wizard
- [ ] Mobile responsiveness

### Week 3 (Phase 3)
- [ ] Confidence scoring display
- [ ] Agent performance metrics dashboard
- [ ] Cost transparency

### Week 4 (Phase 4)
- [ ] Timeout management & early termination
- [ ] Retry strategy with exponential backoff
- [ ] Caching & memory optimization

### Follow-Up Sprints (Phase 5)
- [ ] A/B testing framework
- [ ] Emotion-aware response generation
- [ ] User feedback loop integration

---

## Success Metrics

### User Experience
- Chat response time < 5s (perceived, including progress updates)
- Task completion rate > 95% (before manual intervention)
- User satisfaction score > 4.2/5 (post-task survey)

### Reliability
- Error recovery rate > 85% (auto-retry success)
- System uptime > 99.5%
- Silent failure rate < 0.1%

### Trust & Transparency
- Users can explain why a result was returned
- Confidence scores correlate with actual accuracy > 0.8
- Cost estimates within 10% of actual

### Performance
- Long task progress updates every 1-2 seconds
- Cached results serve 50ms; fresh searches < 15s
- Mobile load time < 3s on 4G

---

## Notes

- Each phase should be reviewed for regressions before moving to next
- User feedback drives priority within phases
- Document all new features in the dashboard help section
- Update CLAUDE.md when architecture changes significantly

---

**Version:** 1.0  
**Last Updated:** 2026-04-27  
**Owner:** Product Team  
