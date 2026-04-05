# Paperclip vs AI-EMPLOYEE: Feature Comparison

This document compares the open-source [Paperclip](https://github.com/paperclipai/paperclip) task-orchestration
platform against AI-EMPLOYEE and lists everything Paperclip has that AI-EMPLOYEE was missing (and that has now
been implemented or is on the roadmap).

---

## ✅ Features AI-EMPLOYEE Already Had

| Feature | AI-EMPLOYEE implementation |
|---|---|
| Multi-agent task decomposition | `task-orchestrator/task_orchestrator.py` |
| Per-agent task queues (JSONL) | `state/agent_tasks/<agent>.queue.jsonl` |
| AI model routing (local-first) | `ai-router/ai_router.py` — Ollama→NIM→Anthropic→OpenAI |
| Parallel execution (up to 10 workers) | `ThreadPoolExecutor` in task-orchestrator |
| Dependency tracking between subtasks | `depends_on` field in subtask DAG |
| Cron-like task scheduling | `scheduler-runner/scheduler.py` |
| Peer-review validation | `TASK_ORCHESTRATOR_PEER_REVIEW` in orchestrator |
| Autonomous agent loop | `blacklight/blacklight.py` |
| Self-improvement / patching | `ascend-forge/ascend_forge.py` |
| Persistent memory | `memory/` (MemoryStore + VectorMemory) |
| Discord / WhatsApp / Telegram notifications | `tools/` + `discord-bot/` |
| Skills library | `config/skills_library.json` (147 skills) |
| Security guardrails | `config/security.yml` + `problem-solver-ui/security.py` |
| 63+ specialised agents | `runtime/agents/` |
| Web search fallback chain | DuckDuckGo→Wikipedia→NewsAPI→Tavily→SerpAPI |

---

## ❌ Features Paperclip Had That AI-EMPLOYEE Was Missing (Now Implemented)

### 1. 🏢 Org Chart & Agent Hierarchy
**Paperclip:** Roles, reporting lines, job descriptions, CEO→CTO→Engineer delegation.  
**AI-EMPLOYEE before:** Flat list of 63 agents — no hierarchy, no reporting lines, no roles.  
**Now implemented:** `runtime/agents/org-chart/org_chart.py`
- Define roles (CEO, CTO, Developer, Marketing Lead, etc.) and reporting lines
- Job descriptions per role
- Delegation: top-level goals flow down to sub-agents via `assign_task()`
- `GET /api/org/chart`, `POST /api/org/roles`, `POST /api/org/assign`

---

### 2. 💰 Per-Agent Budget Tracking & Enforcement
**Paperclip:** Monthly budget per agent. 80% warning. 100% hard stop. Granular cost dashboard.  
**AI-EMPLOYEE before:** No budget tracking — runaway costs possible.  
**Now implemented:** `runtime/agents/budget-tracker/budget_tracker.py`
- Per-agent monthly budget (USD) configurable in `config/budgets.json`
- Token usage tracked per API call via `record_usage(agent_id, tokens, model)`
- 80% threshold → warning logged and surfaced in UI
- 100% threshold → agent tasks paused until budget resets or is increased
- `GET /api/budget/status`, `POST /api/budget/set`, `POST /api/budget/reset`

---

### 3. 🎯 Goal Alignment & Goal Ancestry
**Paperclip:** Every task carries full goal ancestry (Company Mission → Project Goal → Task).  
Agents always know *what* to do and *why*.  
**AI-EMPLOYEE before:** Tasks were standalone; no hierarchical context inheritance.  
**Now implemented:** `runtime/agents/goal-alignment/goal_alignment.py`
- Company mission stored in `config/company_goals.json`
- Projects with goals attached to agents/roles
- Goal ancestry injected into every task prompt automatically
- `GET /api/goals/company`, `POST /api/goals/company`, `POST /api/goals/project`

---

### 4. 🎫 Ticket System with Full Audit Trail
**Paperclip:** Every conversation traced, every decision explained, full tool-call tracing, immutable audit log.  
**AI-EMPLOYEE before:** Chatlog (JSONL) exists but no formal ticket system with threading, statuses, or immutable audit.  
**Now implemented:** `runtime/agents/ticket-system/ticket_system.py`
- Tickets with ID, title, status (`open`, `in_progress`, `blocked`, `done`, `cancelled`)
- Thread of comments on each ticket (immutable append-only)
- Each task created by the orchestrator creates/updates a ticket
- Full audit log of every status change and action
- `GET /api/tickets`, `POST /api/tickets`, `GET /api/tickets/{id}`, `POST /api/tickets/{id}/comment`

---

### 5. 🛡️ Governance / Board Controls
**Paperclip:** Human "board" can approve hires/fires, override strategy, pause/terminate agents at any time.  
**AI-EMPLOYEE before:** ASCEND_FORGE has patch approval, but no formal governance board for task-level control.  
**Now implemented:** `runtime/agents/governance/governance.py`
- Approval gates for high-impact agent actions (configurable risk thresholds)
- Board can approve, reject, or override any pending action
- Agents can be paused or terminated via governance commands
- Configurable auto-approve for LOW risk actions
- Immutable governance audit trail
- `GET /api/governance/pending`, `POST /api/governance/{id}/approve`, `POST /api/governance/{id}/reject`, `POST /api/governance/pause/{agent}`

---

### 6. 🏗️ Multi-Company Support
**Paperclip:** One deployment, many companies. Complete data isolation. One control plane.  
**AI-EMPLOYEE before:** Single-company only — all state files in one flat directory.  
**Now implemented:** `runtime/agents/company-manager/company_manager.py`
- Multiple companies in one AI-EMPLOYEE deployment
- Company-scoped state directories: `state/companies/<company_id>/`
- Switch active company via `POST /api/companies/switch`
- Each company has separate agent roster, goals, tickets, budgets
- `GET /api/companies`, `POST /api/companies`, `DELETE /api/companies/{id}`

---

### 7. 📦 Company Export / Import (Templates)
**Paperclip:** Export/import entire org structure — agents, skills, goals — with secret scrubbing and collision handling.  
**AI-EMPLOYEE before:** No export/import of company configuration.  
**Now implemented:** `runtime/agents/company-manager/company_manager.py` (export/import endpoints)
- Export company: agents, goals, org chart, skills, schedules (secrets scrubbed automatically)
- Import company template with collision detection
- `GET /api/companies/{id}/export`, `POST /api/companies/import`

---

### 8. 🔒 Atomic Task Checkout (Prevent Double-Work)
**Paperclip:** Task checkout and budget enforcement are atomic — no double-work, no runaway spend.  
**AI-EMPLOYEE before:** Task queues used JSONL without locking — race conditions possible under parallel load.  
**Now implemented:** `runtime/agents/task-orchestrator/task_orchestrator.py` (updated)
- `filelock`-based atomic checkout for task queue items
- Only one agent/worker can hold a task at a time
- Prevents duplicate execution under parallel thread-pool load

---

### 9. 💓 Heartbeat-Based Agent Wake Cycle
**Paperclip:** Agents wake on schedule, check for work, act. Delegation flows up and down the org chart.  
**AI-EMPLOYEE before:** Scheduler runner exists but agents don't self-register heartbeats.  
**Now implemented:** `runtime/agents/org-chart/org_chart.py` heartbeat integration
- Agents register heartbeat interval in org chart config
- OrgChart manager dispatches work to agents at heartbeat intervals
- Heartbeat triggers check for tasks assigned via delegation

---

### 10. 📱 Mobile-Ready Dashboard
**Paperclip:** React/TypeScript dashboard is fully mobile-responsive.  
**AI-EMPLOYEE before:** Problem-solver UI works but is not explicitly mobile-optimised.  
**Improvement added:** Responsive CSS meta-viewport and media queries added to the UI template in `server.py`.

---

### 11. 🔌 Bring Your Own Agent (BYOA) Adapter Standard
**Paperclip:** Any agent can be hired if it can receive a heartbeat. Standardised adapter interface.  
**AI-EMPLOYEE before:** Custom agents can be added but there is no standard adapter contract.  
**Now implemented:** `runtime/agents/org-chart/org_chart.py` adapter spec
- Standard `AgentAdapter` interface: `heartbeat()`, `assign_task()`, `get_status()`
- HTTP webhook adapter (for any HTTP-capable agent)
- CLI adapter (for bash/script agents)
- Registered in `config/agent_adapters.json`

---

## 📊 Summary Table

| Feature | Paperclip | AI-EMPLOYEE (before) | AI-EMPLOYEE (after) |
|---|:---:|:---:|:---:|
| Multi-agent orchestration | ✅ | ✅ | ✅ |
| AI model routing | ✅ | ✅ | ✅ |
| Task scheduling (cron) | ✅ | ✅ | ✅ |
| Persistent agent memory | ✅ | ✅ | ✅ |
| Self-improvement / patching | ✅ | ✅ | ✅ |
| 60+ specialised agents | ✅ | ✅ | ✅ |
| **Org Chart & Hierarchy** | ✅ | ❌ | ✅ |
| **Per-Agent Budget Enforcement** | ✅ | ❌ | ✅ |
| **Goal Alignment / Ancestry** | ✅ | ❌ | ✅ |
| **Ticket System + Audit Log** | ✅ | ❌ | ✅ |
| **Governance / Board Controls** | ✅ | ❌ | ✅ |
| **Multi-Company Isolation** | ✅ | ❌ | ✅ |
| **Company Export / Import** | ✅ | ❌ | ✅ |
| **Atomic Task Checkout** | ✅ | ❌ | ✅ |
| **Heartbeat Agent Wake Cycle** | ✅ | Partial | ✅ |
| **BYOA Adapter Standard** | ✅ | Partial | ✅ |
| Local-first AI (Ollama) | ❌ | ✅ | ✅ |
| NVIDIA NIM integration | ❌ | ✅ | ✅ |
| WhatsApp / Telegram integration | ❌ | ✅ | ✅ |
| Autonomous money-making loop | ❌ | ✅ | ✅ |
| Vector memory + deduplication | ❌ | ✅ | ✅ |
| Feedback loop / A/B templates | ❌ | ✅ | ✅ |
| Financial deep-search | ❌ | ✅ | ✅ |
| Lead intelligence pipeline | ❌ | ✅ | ✅ |

---

## 🚀 AI-EMPLOYEE Advantages Over Paperclip

Areas where AI-EMPLOYEE goes beyond Paperclip:

1. **Local-first AI** — Ollama (free, private) runs everything locally before cloud fallback
2. **NVIDIA NIM** — Free-tier GPU-accelerated models (Nemotron, Qwen, Llama 8B)
3. **63 specialised agents** vs Paperclip's bring-your-own approach
4. **WhatsApp / Telegram / Discord** — Native multi-channel messaging
5. **Autonomous money-making loop** — BLACKLIGHT finds leads and generates revenue
6. **Self-improvement engine** — ASCEND_FORGE patches itself and improves the system
7. **Financial deep-search** — SEC EDGAR + yfinance + DuckDuckGo for research
8. **Lead intelligence pipeline** — 4-stage lead scoring and vector deduplication
9. **Feedback loop** — Automatic A/B template scoring for outreach
10. **Vector memory** — Cosine similarity deduplication across all agents

---

*Generated by AI-EMPLOYEE Copilot — see implementation in `runtime/agents/`*
