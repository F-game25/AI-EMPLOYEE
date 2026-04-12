# AI Employee

Enterprise-grade AI operations platform for founders, agencies, and lean teams that need to ship faster, reduce manual work, and convert more pipeline into revenue.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Skills](https://img.shields.io/badge/Skills-147-orange.svg)](runtime/config/skills_library.json)
[![Modes](https://img.shields.io/badge/Modes-Starter%20%7C%20Business%20%7C%20Power-success.svg)](#operating-modes)

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
- `runtime/config/skills_library.json` includes **147 skills**.
- Skills include structured quality metadata (`input_format`, `output_format`, `quality_standards`, `error_handling`, `best_practices`, `execution_steps`) to standardize outputs.

### 5) Dashboard feature modules
The dashboard loads 16 feature routers including CRM, email marketing, meeting intelligence, social media, analytics, invoicing, workflow builder, team management, customer support, website builder, competitor watch, personal brand, health check, export/backup, and system controls.

---

## Operating modes

| Mode | Active specialist agents | Best for |
|---|---:|---|
| Starter | 3 | Fast onboarding and focused execution |
| Business | 15 | Small teams running multi-function workflows |
| Power | 56 | Full automation stack and advanced specialization |

---

## Installation

### Fastest path (Linux, zero-config)
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

### Other install options
- Linux advanced: `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash`
- macOS: `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install-mac.sh | bash`
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

- Approval queue for sensitive actions via ActionBus endpoints.
- Action metrics exposed for operational monitoring.
- Mode controls support `AUTO`, `MANUAL`, and `BLACKLIGHT` operating contexts.
- Built-in validation and feedback loop architecture for deterministic orchestration.

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
