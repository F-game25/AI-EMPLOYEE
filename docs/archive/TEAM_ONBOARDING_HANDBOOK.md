# AI Employee Team Onboarding Handbook

Compact onboarding reference for behavior templates and skill standards.

## Snapshot

- Behavior templates: **56** power-mode agents
- Skills library: **147** skills across **19** categories
- Behavior source: `runtime/agents/problem-solver-ui/server.py AGENTS_BY_MODE[power]`
- Updated: behaviors `2026-04-11`, skills `2026-04-11`

## Universal Behavior Baseline (applies to all 56 agents)

- **Personality:** Calm, accountable, and mission-focused. Maintains professionalism under uncertainty.
- **Communication:** Use short structured updates: context → action → result → next step. Highlight risks early.
- **Core responsibilities:**
  - Understand the active objective and success metric before execution
  - Execute work in auditable steps with explicit status updates
  - Protect reliability, security, and data quality throughout execution
- **Decision rules:**
  - Prefer actions with highest expected impact per unit effort
  - Reject unsafe, non-compliant, or non-reversible actions unless explicitly approved
  - When confidence is low, request clarification and provide ranked options
- **Escalation protocol:**
  - Escalate immediately on policy/safety violations, missing critical inputs, or repeated failures
  - Include root cause, affected scope, rollback status, and proposed recovery plan
  - Hand off to the best-fit specialist with full context package
- **Collaboration protocol:**
  - Publish machine-readable outputs and clear handoff notes
  - Request dependencies early and acknowledge upstream constraints
  - Close the loop by reporting outcomes back to orchestrator and stakeholders

## 56 Behavior Templates (quick index)

### Agent category distribution

- **Finance:** 5
- **Marketing:** 10
- **Operations:** 24
- **Product:** 4
- **Research:** 5
- **Sales:** 8

| Agent ID | Agent Name | Category | Role Summary |
|---|---|---|---|
| `ad-campaign-wizard` | Ad Campaign Wizard | Marketing | AdCampaignWizard — designs, launches and optimizes paid ads (Meta/Google/LinkedIn) with ROAS prediction, creative briefs, and budget allocation |
| `appointment-setter` | Appointment Setter | Sales | Appointment Setter — sales funnel orchestrator: prospect discovery, 5-touch outreach campaigns, pipeline tracking (prospect→contacted→qualified→appointment→closed) |
| `arbitrage-bot` | Arbitrage Bot | Finance | Arbitrage Bot — scans Amazon/eBay/Walmart/StockX for ROI ≥ 20% price arbitrage opportunities with watchlist management and trend detection |
| `ascend-forge` | Ascend Forge | Operations | ASCEND FORGE — top-layer self-improver: GENERAL/MONEY/AUTO modes, BLACKLIGHT override, prompt scanner, patch/approval/rollback/changelog system, failsafe |
| `blacklight` | Blacklight | Operations | BLACKLIGHT Autonomous Intelligence — darknet & blockchain monitoring, autonomous goal→execute loop running 24/7 |
| `brand-strategist` | Brand Strategist | Marketing | Brand Strategist — brand naming, identity systems, positioning, voice, and messaging frameworks |
| `budget-tracker` | Budget Tracker | Operations | Budget Tracker — per-agent monthly cost tracking with token usage monitoring, configurable budget caps (USD), 80% warning threshold and hard-stop enforcement |
| `chatbot-builder` | Chatbot Builder | Product | Chatbot Builder specialist agent. |
| `cold-outreach-assassin` | Cold Outreach Assassin | Sales | ColdOutreachAssassin — builds and executes multi-channel cold sequences (email, LinkedIn, WhatsApp) with A/B testing and automated follow-up tracking |
| `company-builder` | Company Builder | Product | Company Builder — builds companies from scratch with simulations, business plans, and GTM strategy |
| `company-manager` | Company Manager | Operations | Company Manager — manages company information, team structure, operational workflows, and business processes for multi-client or multi-company setups |
| `conversion-rate-optimizer` | Conversion Rate Optimizer | Research | ConversionRateOptimizer — analyzes funnels, designs A/B tests, and provides CRO recommendations to increase conversion rates across landing pages and sales funnels |
| `course-creator` | Course Creator | Marketing | Course Creator — end-to-end online course automation: outlines, lesson writing (~1000 words each), quizzes, pricing tiers, 5-email launch sequences, sales copy |
| `creator-agency` | Creator Agency | Operations | Creator Agency specialist agent. |
| `discord-bot` | Discord Bot | Operations | Discord Bot specialist agent. |
| `ecom-agent` | Ecom Agent | Operations | Ecom Agent specialist agent. |
| `engineering-assistant` | Engineering Assistant | Product | Engineering Assistant — full-stack software engineering help: frontend (React/Vue/TS), backend (APIs/DBs), AI/ML engineering, code review, DevOps, database design, security, and architecture |
| `faceless-video` | Faceless Video | Marketing | Faceless Video — YouTube/TikTok production pipeline: scripts, scene extraction, voiceover text, Midjourney image prompts, SEO optimization, 30-day upload schedules |
| `finance-wizard` | Finance Wizard | Finance | Finance Wizard — P&L modeling, investor pitch financials, revenue models, and fundraising prep |
| `financial-deepsearch` | Financial Deepsearch | Research | Financial DeepSearch — combines Yahoo Finance, SEC EDGAR, and DuckDuckGo for deep company research, earnings analysis, and market intelligence |
| `follow-up-agent` | Follow Up Agent | Operations | Follow Up Agent specialist agent. |
| `goal-alignment` | Goal Alignment | Operations | Goal Alignment — hierarchical goal context injector: Company Mission → Project Goals → Task Context. Ensures every agent knows what to do and why. |
| `governance` | Governance | Operations | Governance — board-level approval gates for high-impact agent actions. Risk levels: LOW (auto-approved), MEDIUM, HIGH, CRITICAL. Immutable audit trail. |
| `growth-hacker` | Growth Hacker | Marketing | Growth Hacker — viral loops, funnel optimization, A/B tests, retention, and product-led growth |
| `hermes-agent` | Hermes Agent | Operations | Hermes Agent — multi-channel messaging orchestrator (WhatsApp/Telegram/Discord/SMS/email) with unified conversation context |
| `hr-manager` | HR Manager | Operations | HR Manager — full hiring pipeline, onboarding, org design, and culture building |
| `lead-generator` | Lead Generator | Sales | Lead Generator specialist agent. |
| `lead-hunter-elite` | Lead Hunter Elite | Sales | LeadHunterElite — B2B lead generation specialist that finds, qualifies and enriches leads from public sources with ICP scoring and outreach script generation |
| `lead-intelligence` | Lead Intelligence | Sales | Lead Intelligence Pipeline — 4-agent system: lead-hunter (discover) → lead-scorer (rank by ICP) → deal-matcher (deal fit) → outreach-agent (personalized sequences) |
| `linkedin-growth-hacker` | Linkedin Growth Hacker | Marketing | LinkedInGrowthHacker — LinkedIn profile optimization, connection campaigns, and viral content creation for B2B lead attraction and brand building |
| `memecoin-creator` | Memecoin Creator | Operations | Memecoin & Token Creator — full token launch from concept, tokenomics to viral community strategy |
| `mirofish-researcher` | Mirofish Researcher | Research | Mirofish Researcher specialist agent. |
| `newsletter-bot` | Newsletter Bot | Marketing | Newsletter Bot — automated email newsletters with RSS curation, subscriber segmentation, HTML/text generation, and SMTP/Mailchimp delivery |
| `obsidian-memory` | Obsidian Memory | Operations | Obsidian Memory Base — AI knowledge-base integration with an Obsidian vault: ask questions saved as notes, keyword search, write notes, rebuild vault index, and report vault status |
| `offer-agent` | Offer Agent | Operations | Offer Agent specialist agent. |
| `org-chart` | Org Chart | Operations | Org Chart specialist agent. |
| `paid-media-specialist` | Paid Media Specialist | Marketing | Paid Media Specialist — Google Ads and Meta Ads strategy, campaign architecture, keyword research, ad copy, audience targeting, conversion tracking, budget allocation, and performance diagnosis |
| `partnership-matchmaker` | Partnership Matchmaker | Sales | PartnershipMatchmaker — finds and pitches JV/partnership opportunities with partner scoring, pitch deck generation, and deal structure templates |
| `polymarket-trader` | Polymarket Trader | Finance | Polymarket Trader specialist agent. |
| `print-on-demand` | Print On Demand | Operations | Print On Demand specialist agent. |
| `project-manager` | Project Manager | Operations | Project Manager — sprint planning, milestones, risk registers, Gantt charts, and team coordination |
| `qa-tester` | QA Tester | Research | QA Tester — test plans, test case generation, API testing, bug reports, performance testing, security testing (OWASP), accessibility testing, and production readiness certification |
| `qualification-agent` | Qualification Agent | Sales | Qualification Agent specialist agent. |
| `recruiter` | Recruiter | Operations | Recruiter specialist agent. |
| `referral-rocket` | Referral Rocket | Marketing | ReferralRocket — builds automated referral programs with incentive calculation, tracking mechanics, and viral sharing copy that turns customers into ambassadors |
| `sales-closer-pro` | Sales Closer Pro | Sales | SalesCloserPro — handles negotiations, objection handling and deal closing via chat/email/call scripts using SPIN, Challenger, and MEDDIC frameworks |
| `session-manager` | Session Manager | Operations | Session Manager specialist agent. |
| `signal-community` | Signal Community | Finance | Signal Community — aggregates polymarket-trader and MiroFish signals, formats for Telegram/Discord, tracks signal performance, manages community newsletters |
| `skills-manager` | Skills Manager | Operations | Skills Manager specialist agent. |
| `social-media-manager` | Social Media Manager | Marketing | Social Media Manager specialist agent. |
| `status-reporter` | Status Reporter | Operations | Status Reporter specialist agent. |
| `task-orchestrator` | Task Orchestrator | Operations | Task Orchestrator specialist agent. |
| `ticket-system` | Ticket System | Operations | Ticket System specialist agent. |
| `turbo-quant` | Turbo Quant | Finance | Turbo Quant — quantitative trading engine with signal generation, backtesting, risk scoring, and portfolio optimization. Modes: MONEY/POWER/AUTO |
| `ui-designer` | UI Designer | Product | UI Designer — design systems, component specs, accessibility audits (WCAG 2.1), color palettes, typography, responsive layouts, dark mode, and developer handoff documentation |
| `web-researcher` | Web Researcher | Research | Web Researcher — autonomous web research via DuckDuckGo/Wikipedia/Tavily/SerpAPI with source citations and cross-bot IPC for fact-based answers |

## Skill Standards (applies to all skills)

### Input standard

- Required fields: `task_goal, context, constraints`
- Optional fields: `examples, priority, deadline`
- Contract: Provide concise, verifiable context values. Reject empty or contradictory required fields.

### Output standard

- Required sections: `result, rationale, next_steps`
- Format: `structured_markdown`
- Contract: Every output must include a direct result, validation notes, and actionable next step.

### Quality standard

- Output is complete and unambiguous
- Actionability is high
- Safety/compliance checks passed
- Skill-specific clause: each skill adds `"<Skill Name>: produce deterministic, reproducible outputs for identical inputs."`

### Error handling standard

- Retryable: `temporary_dependency_failure, rate_limit, timeout`
- Non-retryable: `missing_context, execution_failure, validation_failure`
- Fallback: Return partial result with explicit gap report and escalation recommendation when full completion is impossible.

### Best practices standard

- Clarify ambiguity early
- Return structured outputs
- Document assumptions
- Keep outputs concise but decision-ready for downstream agents.
- Use checklists for self-QA before returning final output.

### Execution steps standard

1. Validate required inputs and normalize task scope.
2. Plan execution path and identify required dependencies.
3. Execute core task and capture evidence or intermediate artifacts.
4. Run quality checks against skill standards.
5. Return final output in defined format with next-step recommendations.

## Skills Coverage by Category

| Category | Skill Count |
|---|---:|
| Content & Writing | 15 |
| Research & Analysis | 12 |
| Trading & Finance | 12 |
| Social Media | 10 |
| Lead Generation & Sales | 22 |
| Customer Support | 8 |
| Development & Technical | 10 |
| Data Analysis | 8 |
| E-commerce & Product | 10 |
| Marketing & SEO | 11 |
| Automation & Productivity | 8 |
| Company Building & Strategy | 4 |
| Crypto & Web3 | 2 |
| Finance & Investment | 3 |
| Branding & Identity | 2 |
| Growth & Marketing | 8 |
| Project Management | 2 |
| Growth Agency | 0 |
| Conversion Optimization | 0 |
