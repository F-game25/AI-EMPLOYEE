# AI Employee

Enterprise-grade AI operations platform for founders, agencies, and lean teams that need to ship faster, reduce manual work, and convert more pipeline into revenue.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Specialist Agents](https://img.shields.io/badge/Specialist%20Agents-113-blueviolet.svg)](runtime/config/agent_capabilities.json)
[![Skills](https://img.shields.io/badge/Skills-570-orange.svg)](runtime/config/skills_library.json)
[![Multi-tenant](https://img.shields.io/badge/Multi--tenant-yes-success.svg)](#platform-subsystems)

---

## ⚡ Quick Start (No Terminal Required)

**Windows**: Double-click `run.bat`  
**macOS/Linux**: Double-click `run.sh` (or `bash run.sh`)

Your browser will open automatically. Follow the setup wizard (installs everything automatically) and you're ready to go.

👉 **[Full Getting Started Guide →](GETTING_STARTED.md)**

---

## Why teams use AI Employee

- **Save time on repetitive work**: automate lead discovery, content drafting, outreach workflows, and operational reporting.
- **Increase revenue throughput**: run built-in monetization pipelines with measurable estimated ROI and conversion steps.
- **Operate with control**: keep risky actions gated behind approvals while still running high-speed automation for safe tasks.
- **Scale without headcount shock**: move from a starter setup to a full specialist-agent stack as workload grows.

---

## Business outcomes: save time and make more money

| Business objective | How AI Employee helps | Time saved | Revenue impact |
|---|---|---|---|
| Fill top of funnel | Lead pipeline automates scrape → qualify → store | Cuts manual prospecting hours | More qualified leads entering CRM |
| Create demand content | Content pipeline drafts platform-specific posts and tracks engagement | Replaces repetitive content production work | More traffic and conversion opportunities |
| Improve close rates | Opportunity pipeline tracks outreach responses and projected conversions | Reduces campaign ops overhead | Better conversion follow-up and ROI visibility |
| Improve decisions | Product dashboard consolidates tasks, pipelines, value, and top skills | Eliminates manual KPI aggregation | Faster decisions on what to scale |

---

## Core capabilities

### 1) Central orchestration
- `AgentController` is the central task orchestrator for planning, execution, validation, and feedback loops.
- `/api/tasks/run` routes goal execution through this controller and returns normalized task contracts.

### 2) Enterprise API surface
Key system endpoints include:
- `/api/mode`, `/api/changelog`, `/api/skills`
- `/api/tasks/run`, `/api/tasks/recent`
- `/api/actions/pending`, `/api/actions/{id}/approve`, `/api/actions/{id}/reject`, `/api/actions/metrics`
- `/api/money/content-pipeline`, `/api/money/lead-pipeline`, `/api/money/opportunity-pipeline`, `/api/money/affiliate-draft`
- `/api/automation/control`, `/api/memory/insights`, `/api/product/dashboard`

### 3) Monetization pipelines
`MoneyMode` ships with three measurable flows:
1. `content_publish_track`
2. `data_scrape_filter_store`
3. `outreach_response_conversion`

Each run is logged to pipeline telemetry and returned with estimated ROI metrics.

### 4) Skills system
- `runtime/config/skills_library.json` ships **570 skills**: 200 hand-curated (including a native fork-enrichment layer for engineering, finance, money, autonomy, wallet, and channel work) plus 370 generated to back **every** capability the agent catalog advertises — so no agent references a skill that doesn't exist.
- Every skill carries structured quality metadata (`input_format`, `output_format`, `quality_standards`, `error_handling`, `best_practices`, `execution_steps`) and a `system_prompt`, so it is dispatchable and runs the real LLM via the agent controller / companion `skills.run` path.
- The library is regenerated from the agent catalog by `scripts/backfill_agent_skills.py` (idempotent), keeping skills and agent capabilities in sync.

### 5) Dashboard feature modules
The dashboard is served by **30+ backend route modules** (`backend/routes/`) spanning CRM and business ops, ecommerce ops, AscendForge controlled code execution, the companion/voice teammate, compute fabric, research, intelligence and learning, media, security ops, secret vault, workflow automation, self-evolution, sessions, settings, and system controls.

---

## Capacity and operating modes

All specialist agents run at **full capacity** — there are no tiers, paywalled agents, or "ghost" entries. The catalog registers **113 specialist agents** (across 124 agent directories) in `runtime/config/agent_capabilities.json`, organized into 28 categories (sales, marketing, content, research, analytics, operations, ecommerce, social, coordination, and more), each discovered from a `runtime/agents/<name>/` directory.

Runtime behavior is governed by orthogonal modes rather than agent tiers:

| Control | Values | Effect |
|---|---|---|
| Automation (`/api/mode`) | `AUTO` · `MANUAL` · `BLACKLIGHT` | Whether safe tasks execute autonomously or wait for operator approval |
| Evolution (`EVOLUTION_MODE`) | `AUTO` · `SAFE` · `OFF` | Whether the system self-patches, proposes only, or stays static |
| Research (`AUTO_RESEARCH_MODE`) | `ask` · `auto` · `off` | Whether missing context triggers autonomous web research |
| LLM backend (`LLM_BACKEND`) | `anthropic` · `ollama` | Cloud or local-first inference |

---

## Platform subsystems

Beyond the agent catalog, the platform ships several production subsystems:

- **Multi-tenancy** — full tenant isolation with per-tenant state and config directories; JWT carries a `tenant_id` claim enforced by both Node and FastAPI middleware (`runtime/core/tenancy.py`).
- **Unified pipeline** — all input flows through an enforced 10-phase pipeline (retrieve → context → classify → LLM → validate → execute → format → update graph → monitor → integrity check) in `runtime/core/unified_pipeline.py`.
- **Autonomous research loop** — when a goal lacks context, a sufficiency score triggers `AutoResearchAgent` to run adaptive-depth web research and persist findings to the vector store, brain graph, and knowledge base (`runtime/core/auto_research_agent.py`).
- **Companion / voice teammate** — one unified conversational runtime (`runtime/companion/`) with an intent classifier, capability registry, execution broker, and safety gate behind it.
- **Self-evolution** — controlled patch generation, validation, and safe deployment gated by `EVOLUTION_MODE` (`runtime/core/self_evolution/`).
- **Observability** — Prometheus-style `/metrics` endpoint, a 1-second metrics collector, a JSONL event stream, and an immutable audit log in `state/audit.db`.
- **Local-first access** — on `localhost` the dashboard authenticates automatically via `/api/auth/auto-token` (no operator secret required); a secret is only requested for remote access.

---

## Autonomous business operations

The platform runs operations end-to-end, with consequential steps gated behind approval:

- **CompanyOS** — a validate-before-build company builder: refine a raw idea (`runtime/companyos/idea_refiner.py`), validate it, then orchestrate the build (`runtime/companyos/`, `/api/company/*`).
- **Work acquisition → delivery** — an opportunity → quote → deliver pipeline (`runtime/money/work_engine/`), HITL-gated before anything leaves the system.
- **Content Factory** — multi-platform content generation with an approval-gated publish queue (`runtime/content/content_factory.py`).
- **FinanceOps** — advisory-only finance drafts that require sign-off; it never moves money on its own (`runtime/finance/financeops.py`).
- **Business Swarm** — decompose → assign → execute → aggregate across real agent contracts (`runtime/core/swarm/`, `runtime/agents/business_swarm/`).
- **AscendForge** — a controlled code-execution engine with sandboxing and UI-quality auditing (`runtime/forge/`), surfaced via `/api/forge/*`.
- **Computer-Use mode** — an explicit master switch (`/api/computer-use/mode`) that lets the teammate drive a real browser only when toggled ON.

Honest execution is enforced system-wide: pipelines do real work or report real failures — there is no fabricated "success."

---

## Installation

### Fastest path (Linux, zero-config)
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

### Other install options
- Linux & macOS (advanced): `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash` — auto-detects your OS
- Windows: use `quick-install-windows.bat` or `install-windows.ps1`

Full guide: [INSTALL.md](INSTALL.md)

---

## Quickstart

```bash
# Start platform
cd ~/.ai-employee && ./start.sh

# Optional CLI shortcuts
ai-employee start
ai-employee onboard
```

Dashboard: `http://127.0.0.1:8787`

Run goal-driven tasks:
```bash
ai-employee do "find 20 qualified leads for my agency"
ai-employee do "write a 5-step outbound sequence for SaaS buyers"
ai-employee do "build a 30-day LinkedIn content plan for B2B founders"
```

---

## Monetization playbooks (practical)

### Content growth engine
Use `/api/money/content-pipeline` to generate and queue platform content with engagement tracking.

### Lead generation engine
Use `/api/money/lead-pipeline` to ingest audience data and create qualified lead records for downstream outreach.

### Opportunity conversion engine
Use `/api/money/opportunity-pipeline` to simulate and run outreach execution with response and conversion projections.

### Daily executive control
Use `/api/product/dashboard` to monitor:
- task throughput and success rate
- pipeline performance
- revenue + value-generated components
- top-performing skills and strategies

---

## Governance and safety

- Human-in-the-loop (HITL) approval gate blocks consequential actions by high-risk agents until an operator approves from the dashboard.
- Approval queue for sensitive actions via ActionBus endpoints, with action metrics exposed for operational monitoring.
- Tenant isolation: state and config are segregated per tenant, and JWT `tenant_id` claims are enforced at every route.
- Mode controls support `AUTO`, `MANUAL`, and `BLACKLIGHT` operating contexts.
- Built-in validation and feedback loop architecture for deterministic orchestration, plus an immutable audit log (`state/audit.db`) for compliance.

See also: [SECURITY.md](SECURITY.md), [SECURITY_AUDIT.md](SECURITY_AUDIT.md)

---

## Contributor workflow

From repo root:

```bash
npm run lint
npm test
```

Notes:
- `lint` compiles Python agent modules for syntax validation.
- `test` runs `pytest` plus `runtime/agents/agent_selftest.py`.

---

## Documentation index

- [INSTALL.md](INSTALL.md) — cross-platform installation and operations
- [EXAMPLES.md](EXAMPLES.md) — usage examples
- [TEAM_ONBOARDING_HANDBOOK.md](TEAM_ONBOARDING_HANDBOOK.md) — onboarding and behavior standards
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution process

---

## License

MIT — see [LICENSE](LICENSE)
