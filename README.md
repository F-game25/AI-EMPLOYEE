# AI Employee — Nexus OS

Enterprise-grade **AI operating system** for founders, agencies, and lean teams. It turns
intent into real-world outcomes through an orchestrated workforce of specialist agents,
versioned skills, and atomic tools — with every risky action gated behind approvals.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Specialist Agents](https://img.shields.io/badge/Specialist%20Agents-113-blueviolet.svg)](runtime/config/agent_capabilities.json)
[![Skills](https://img.shields.io/badge/Skills-869-orange.svg)](runtime/config/skills_library.json)
[![Multi-tenant](https://img.shields.io/badge/Multi--tenant-yes-success.svg)](#multi-tenancy)
[![Voice](https://img.shields.io/badge/Voice-hear%20%2B%20speak-ff69b4.svg)](#13-voice-system-hear--speak)

> This is not a model wrapper. It is a production automation engine: **intent → structured
> workflow → real-world outcome**, observable and reversible at every step.

---

## Table of contents

- [Quick start](#quick-start)
- [Architecture](#architecture) · [How a request flows](#how-a-request-flows)
- **Features (how each works):**
  [1. Orchestrator](#1-orchestrator--task-contracts) ·
  [2. Companion teammate](#2-companion--conversational-teammate) ·
  [3. Skills](#3-skills-system) ·
  [4. Agents](#4-agent-catalog) ·
  [5. Money Mode](#5-money-mode--monetization-pipelines) ·
  [6. Business operations](#6-autonomous-business-operations) ·
  [7. AscendForge](#7-ascendforge--controlled-code-execution) ·
  [8. Computer-use](#8-computer-use--browser-automation) ·
  [9. Research loop](#9-autonomous-research-loop) ·
  [10. Memory](#10-memory-system) ·
  [11. Model routing](#11-model-routing) ·
  [12. Multi-tenancy](#12-multi-tenancy) ·
  [13. Voice](#13-voice-system-hear--speak) ·
  [14. Security](#14-security--governance) ·
  [15. Observability](#15-observability) ·
  [16. Self-evolution](#16-self-evolution) ·
  [17. Desktop app](#17-desktop-app--packaging)
- [Complete skills catalog (869)](#complete-skills-catalog) · [Complete agent catalog (113)](#complete-agent-catalog)
- [API surface](#api-surface) · [Configuration & modes](#configuration--modes) · [Installation](#installation)
- [Development & testing](#development--testing) · [Project structure](#project-structure) · [Security model](#security-model)

---

## Quick start

**No terminal:** Windows → double-click `run.bat`. macOS/Linux → double-click `run.sh` (or `bash run.sh`). Your browser opens to the setup wizard.

**Terminal:**
```bash
bash start.sh          # builds the frontend, starts the Python AI backend + Node server
# Dashboard: http://localhost:8787
bash stop.sh           # stop everything
```

**Desktop app:** download a native installer (see [Desktop app](#17-desktop-app--packaging)) — bundles the whole system.

---

## Architecture

Three strict layers — the non-negotiable execution model:

```
            ┌──────────────────────────────────────────────────────────┐
  Intent ─► │ ORCHESTRATOR  understand intent → plan → select skills →  │
            │ (global brain) coordinate workflow → monitor outcomes      │
            └───────────────┬──────────────────────────────────────────┘
                            │ selects (never executes tools directly)
            ┌───────────────▼──────────────────────────────────────────┐
  SKILLS  ► │ versioned, domain-specific workflows that compose tools    │
            │ into a complete business capability (validated output)     │
            └───────────────┬──────────────────────────────────────────┘
                            │ composes
            ┌───────────────▼──────────────────────────────────────────┐
  TOOLS   ► │ atomic actions: web search, browser, db, email, file,      │
            │ LLM inference, API request — strict I/O schemas, no logic  │
            └──────────────────────────────────────────────────────────┘
```

**Two runtimes communicate over HTTP:**

- **Node.js backend** ([backend/server.js](backend/server.js), port **8787**) — Express + WebSocket. Serves the built React frontend, handles all `/api/*` routes, and proxies chat to the Python backend. Internals: agent catalog loader, orchestrator/task routing, subsystems, gateway, security (secrets, API-gateway protector, anomaly responder).
- **Python AI backend** ([runtime/agents/problem-solver-ui/server.py](runtime/agents/problem-solver-ui/server.py), port **18790**) — FastAPI/uvicorn running the real LLM pipeline + companion runtime. Without it, chat degrades to keyword-matched placeholders.
- **React frontend** ([frontend/](frontend/)) — Vite SPA built into `frontend/dist/`.

### How a request flows

Every user input is forced through a **10-phase pipeline** ([runtime/core/unified_pipeline.py](runtime/core/unified_pipeline.py)) — no shortcuts:

```
Input → retrieve_relevant_nodes → build_context → classify_decision → call_llm
      → validate_tasks → execute_tasks → format_response → update_graph
      → monitor_and_improve → validate_pipeline_integrity → Output
```

A conversational turn additionally runs the **companion runtime** ([runtime/companion/conversation_runtime.py](runtime/companion/conversation_runtime.py)): `load session memory → resolve context/option → classify intent → response policy → select model target → critique → act-by-mode → persist session`. Set `STRICT_PIPELINE=1` to disable graceful fallbacks (CI/staging).

---

## Features (and how each works)

### 1) Orchestrator & task contracts
- [`AgentController`](runtime/core/agent_controller.py) is the central orchestrator — a **Planner → Executor → Validator** loop. `/api/tasks/run` routes goal execution through it and returns a normalized contract.
- [`TaskGraph` / `TaskNode`](runtime/core/contracts.py) are the dataclasses passed between every layer.
- [`LLMClient`](runtime/core/orchestrator.py) wraps Anthropic/Ollama with retry + JSONL call logging; [`SimpleMessageBus`](runtime/core/bus.py) is in-process pub/sub persisted to `state/bus.jsonl`.
- **How it works:** the orchestrator *selects skills* and coordinates flow — it never executes tools directly. Before running a goal it scores context sufficiency and may trigger the [research loop](#9-autonomous-research-loop).

### 2) Companion / conversational teammate
One unified runtime ([runtime/companion/](runtime/companion/)) handles chat **and** voice turns through the same brain:
- **Intent classifier** → conversation / analysis / planning / execution / debugging / monitoring / approval.
- **Capability registry** + **execution broker** dispatch real subsystem actions; the **safety gate** + **critique engine** challenge consequential requests before acting.
- **Conversation depth:** the *whole running dialogue* (not just the last reply) is rendered into the model context, bounded by turn/char budgets — env-tunable via `COMPANION_DIALOGUE_TURNS` / `COMPANION_DIALOGUE_LINE_CLIP` / `COMPANION_DIALOGUE_CHAR_BUDGET`. Follow-ups like "option 2" / "do that" resolve against the assistant's own last offer ([session_state.py](runtime/companion/session_state.py)).
- **Honest by design:** replies never claim actions that weren't taken; approval-gated actions surface as approval cards.

### 3) Skills system
A **skill** is a reusable, versioned, domain-specific workflow that composes tools into a complete capability with validated output. [`runtime/config/skills_library.json`](runtime/config/skills_library.json) registers **869 dispatchable skills** in the live catalog. They are composed of **859 validated executable skills** plus first-class tool-composing skills:
- **200 hand-curated** (incl. a native fork-enrichment layer for engineering, finance, money, autonomy, wallet, and channel work),
- **370 generated** to back capabilities the agent catalog advertises, regenerated idempotently by [`scripts/backfill_agent_skills.py`](scripts/backfill_agent_skills.py),
- **+289 auto-generated capability skills** layered on at load (`generated_defs`) so **every** agent-advertised capability is backed by a real, validated executable skill — 859 validated total,
- **+ first-class tool-composing skills** (`context-research`, `product-video`, `document-qa`, `last30days`) and default dispatch skills → **869** registered.

Each skill carries structured metadata: `input_format`, `output_format`, `quality_standards`, `error_handling`, `best_practices`, `execution_steps`, and a `system_prompt`. The [skill catalog](runtime/skills/catalog.py) registers them as dispatchable units; **first-class executable skills** (e.g. `context-research`, `product-video`, `document-qa`, `last30days`) run real tool chains, while library skills run via the LLM guided by their own `system_prompt`. Goal dispatch (`dispatch_for_goal`) field-weight-matches a goal to the best skill and runs the same chain the Executor uses.

👉 **[Complete skills catalog — all 869 (571 documented + 289 generated)](#complete-skills-catalog)**

### 4) Agent catalog
**113 specialist agents** ([runtime/config/agent_capabilities.json](runtime/config/agent_capabilities.json)) across **27 categories**, each a directory `runtime/agents/<name>/` with `<name>.py` (a `BaseAgent`), `run.sh`, and `requirements.txt`. `run.sh` sources `~/.ai-employee/.env` + per-agent config before exec. All agents run at **full capacity** — no tiers, no paywalled or "ghost" agents. Discovered on startup by [backend/agents/index.js](backend/agents/index.js); behavior templates in [agent_behavior_templates.json](runtime/config/agent_behavior_templates.json).

👉 **[Complete agent catalog — all 113 by category](#complete-agent-catalog)**

### 5) Money Mode & monetization pipelines
[`MoneyMode`](runtime/core/money_mode.py) ships three measurable flows, each logged to telemetry with estimated ROI:
1. `content_publish_track` — generate → publish → track engagement.
2. `data_scrape_filter_store` — scrape → filter → persist leads.
3. `outreach_response_conversion` — outreach → response → projected conversion (supports `research_first=True`).

Surfaced via `/api/money/*` (content, lead, opportunity, affiliate pipelines).

### 6) Autonomous business operations
End-to-end operations, consequential steps approval-gated:
- **CompanyOS** ([runtime/companyos/](runtime/companyos/), `/api/company/*`) — validate-before-build company builder (refine idea → validate → orchestrate build).
- **Work acquisition → delivery** ([runtime/money/work_engine/](runtime/money/work_engine/)) — opportunity → quote → deliver, HITL-gated.
- **Content Factory** ([runtime/content/content_factory.py](runtime/content/content_factory.py)) — multi-platform content with an approval-gated publish queue.
- **FinanceOps** ([runtime/finance/financeops.py](runtime/finance/financeops.py)) — advisory-only finance drafts; never moves money on its own.
- **Business Swarm** ([runtime/core/swarm/](runtime/core/swarm/)) — decompose → assign → execute → aggregate across real agent contracts.

### 7) AscendForge — controlled code execution
[runtime/forge/](runtime/forge/) (surfaced via `/api/forge/*`) is a sandboxed code-execution + autopilot engine with UI-quality auditing. Generated code runs in a sandbox with allowlisted commands, path-traversal blocks, timeouts, and captured stdout/stderr.

### 8) Computer-use & browser automation
An explicit master switch (`/api/computer-use/mode`) lets the teammate drive a **real browser** only when toggled ON. Stealth fetches use `CloakBrowser`; all browser actions are permissioned and audited.

### 9) Autonomous research loop
When a goal lacks context, a sufficiency score (<0.6, [context_evaluator.py](runtime/core/context_evaluator.py)) triggers [`AutoResearchAgent`](runtime/core/auto_research_agent.py): adaptive-depth research (3→6→10 sources, up to 3 hops) — `search_web` → stealth `CloakBrowser.fetch_url` → LLM summarize → 3-layer persist (vector store + Neo4j brain graph + `state/knowledge_store.json`). Modes via `AUTO_RESEARCH_MODE` (`ask`/`auto`/`off`); budgets via `RESEARCH_MAX_HOPS`, `RESEARCH_MAX_PAGES_PER_DAY`. Per-source trust scoring in [source_trust.py](runtime/core/source_trust.py).

### 10) Memory system
[runtime/memory/](runtime/memory/): a `memory_router`, vector store, short-term cache, and strategy store. Four memory classes — **working** (active task), **user** (preferences/history), **operational** (system performance), **skill** (execution patterns) — plus per-session rolling state ([session_state.py](runtime/companion/session_state.py)). Retrieved content is always treated as untrusted **data**, never instructions.

### 11) Model routing
[`engine.api`](runtime/engine/api.py) is the single LLM surface (`process_input`, `generate`, `embed`, `memory_store`, `memory_retrieve`). `LLM_BACKEND` selects `anthropic` (cloud) or `ollama` (local-first). Paid/cloud targets require explicit opt-in **and** come back requiring approval — never a silent fallback to an external model. Model lanes/quantization and remote compute are routed by cost + data-classification rules; the model/provider used is logged.

### 12) Multi-tenancy
Full tenant isolation. Each tenant lives in `~/.ai-employee/tenants/{tenant_id}/` with its own `state/` and `config/`. JWT carries a `tenant_id` claim enforced by both Node ([backend/tenancy.js](backend/tenancy.js)) and FastAPI ([runtime/core/tenant_middleware.py](runtime/core/tenant_middleware.py)) middleware; state files are segregated via lock-protected `_tenant_data` ([file_lock.py](runtime/core/file_lock.py)). Migrate single-tenant data with `python3 scripts/migrate_to_multitenant.py`.

### 13) Voice system (hear + speak)
Full-duplex voice on the existing subsystem ([backend/services/voice/](backend/services/voice/)):
- **Hear (STT/ASR):** engine-aware [`transcribeWav`](backend/services/voice/voice_runtime_manager.js) selects from `config.asr.engine` = `auto` | `nemotron` | `whisper` (env `VOICE_ASR_ENGINE`). **Nemotron-3.5-ASR streaming 0.6B** (onnxruntime-genai, CPU int4, no torch — [runner](runtime/agents/voice/nemotron_asr.py), [adapter](backend/services/voice/nemotron_asr.js)) is preferred when installed; **whisper.cpp** is the always-available fallback, with Silero VAD. `auto` degrades gracefully and a Nemotron failure also falls back to whisper.
- **Speak (TTS):** Kokoro 82M ([kokoro.js](backend/services/voice/kokoro.js)), a bundled CPU "voice core", and optional Fish Speech S2. `POST /api/voice/speak` (live playback) and `POST /api/voice/narrate` (saved artifact).
- **Avatar** reacts per phase (listening → thinking → speaking). All processing is **local by default**; external call/narration is approval-gated + egress-guarded. Full plan: [docs/VOICE_SYSTEM_PLAN.md](docs/VOICE_SYSTEM_PLAN.md).

### 14) Security & governance
Defense-in-depth, deny-by-default:
- **Auth:** JWT issue/refresh with rotation, 12+ char password policy, auth-route rate limiting; `requireAuth` middleware on protected routes; localhost auto-token for the local dashboard.
- **Authorization & autonomy:** RBAC, per-action autonomy levels, and **HITL gates** ([hitl_gate.py](runtime/core/hitl_gate.py)) that block consequential actions by high-risk agents until a human approves.
- **Sandboxing:** allowlisted commands, path-traversal + symlink-escape blocks, command timeouts, captured output.
- **Secrets:** environment/secret-manager only; redaction in logs/errors; a **secret vault** (`/api/vault/*`). Never committed.
- **Egress guard** for outward-facing actions; **immutable audit log** in `state/audit.db`; security dashboard (`/api/security-ops/*`).
- **All retrieved/agent/model/file/web content is untrusted data** — never command authority.

### 15) Observability
Prometheus-style `/metrics` (port 8787) exposing `ai_employee_*` (uptime, agents active, tasks total/completed/failed, errors, API calls); a 1-second [metrics collector](runtime/core/observability/metrics_collector.py); a JSONL [event stream](runtime/core/observability/event_stream.py); and the immutable audit log + rotated `state/python-backend.log`.

### 16) Self-evolution
[runtime/core/self_evolution/](runtime/core/self_evolution/): controlled patch generation → validation → safe deployment, gated by `EVOLUTION_MODE` (`AUTO` / `SAFE` / `OFF`). On idle cycles it schedules passive knowledge acquisition.

### 17) Desktop app & packaging
Ships as a native desktop app (**AETERNUS NEXUS**) bundling backend + runtime + built dashboard. Cross-platform installers are produced by [.github/workflows/release-desktop.yml](.github/workflows/release-desktop.yml) on native runners:

| OS | Installers |
|---|---|
| Linux | `.AppImage`, `.deb` |
| macOS | `.dmg`, `.zip` (x64 + arm64) |
| Windows | NSIS installer, portable `.exe` (x64) |

Push a `v*` tag (or run the workflow manually) → all three build and attach to a **draft** GitHub Release. Builds are currently unsigned (add signing certs as repo secrets); first run provisions the local Python core + optional local LLM. A Tauri shell ([src-tauri/](src-tauri/)) provides the native "Nexus OS" window.

---

## Complete skills catalog

**869 dispatchable skills** live in the catalog. The **571 documented library skills** below are organized into 25 rich categories; the **289 auto-generated capability skills** (which complete the 859 validated total) are listed in their own section at the end. All run via the agent controller / companion `skills.run` path. Expand a category to see every skill.

<details>
<summary><b>Content & Writing</b> (30)</summary>

- `ad_copywriting` — **Ad Copywriting**: Write high-converting ad copy for Google Ads, Meta Ads, and LinkedIn Ads including headlines and descriptions.
- `blog_writing` — **Blog Post Writing**: Write long-form SEO-optimised blog posts (500–3000 words) on any topic with structured headings and meta descriptions.
- `case_study_writing` — **Case Study Writing**: Write detailed customer success case studies following the problem–solution–results structure.
- `content_calendar` — **Content Calendar Planning**: Plan a monthly content calendar across channels with topic ideas, publish dates, and content types.
- `content_pipeline_planner` — **Content Pipeline Planner**: Content Pipeline Planner: production-ready Money Mode and operations skill for content operations workflows.
- `content_quality_reviewer` — **Content Quality Reviewer**: Content Quality Reviewer: production-ready Money Mode and operations skill for content quality workflows.
- `content_strategy_brief_builder` — **Content Strategy Brief Builder**: Content Strategy Brief Builder: production-ready operating skill for content strategy workflows.
- `copywriting_quality_reviewer` — **Copywriting Quality Reviewer**: Copywriting Quality Reviewer: production-ready operating skill for content quality workflows.
- `email_copywriting` — **Email Copywriting**: Craft persuasive marketing emails and subject lines that drive opens, clicks, and conversions.
- `headline_generation` — **Headline Generation**: Generate multiple headline options using proven frameworks (numbers, curiosity, how-to, controversy).
- `image_prompt_quality_reviewer` — **Image Prompt Quality Reviewer**: Image Prompt Quality Reviewer: production-ready operating skill for creative direction workflows.
- `lesson_writing` — **Lesson Writing**: Lesson Writing: execute this capability end-to-end and return a structured, decision-ready result for Content & Writing…
- `newsletter_writing` — **Newsletter Writing**: Write engaging email newsletters with a consistent structure: opener, main story, tips, and CTA.
- `press_releases` — **Press Release Writing**: Write professional press releases following AP style for product launches, funding rounds, or company milestones.
- `product_descriptions` — **Product Description Writing**: Write compelling e-commerce product descriptions that highlight benefits, use sensory language, and convert browsers in…
- `proofreading` — **Proofreading & Editing**: Proofread and edit text for grammar, style, clarity, and consistency with brand voice guidelines.
- `publish_approval_planner` — **Publish Approval Planner**: Publish Approval Planner: production-ready Money Mode and operations skill for publishing approval workflows.
- `quiz_generation` — **Quiz Generation**: Quiz Generation: execute this capability end-to-end and return a structured, decision-ready result for Content & Writin…
- `seo_optimization` — **SEO Optimization**: SEO Optimization: execute this capability end-to-end and return a structured, decision-ready result for Content & Writi…
- `sales_copy_reviewer` — **Sales Copy Reviewer**: Sales Copy Reviewer: production-ready operating skill for content quality workflows.
- `scene_extraction` — **Scene Extraction**: Scene Extraction: execute this capability end-to-end and return a structured, decision-ready result for Content & Writi…
- `script_outline_builder` — **Script Outline Builder**: Script Outline Builder: production-ready operating skill for content production workflows.
- `scripting` — **Scripting**: Scripting: execute this capability end-to-end and return a structured, decision-ready result for Content & Writing work…
- `social_captions` — **Social Media Captions**: Write platform-optimised captions for Instagram, Facebook, LinkedIn, and X with relevant hashtags.
- `tone_adaptation` — **Tone of Voice Adaptation**: Rewrite existing content in a different tone (formal, casual, expert, friendly) for different audiences or channels.
- `translation_assistance` — **Translation & Localisation**: Translate content into target languages and localise idioms, currency, dates, and cultural references.
- `visual_prompt_art_director` — **Visual Prompt Art Director**: Visual Prompt Art Director: production-ready operating skill for creative direction workflows.
- `voiceover_script_reviewer` — **Voiceover Script Reviewer**: Voiceover Script Reviewer: production-ready operating skill for content production workflows.
- `whitepaper_writing` — **Whitepaper Writing**: Write authoritative whitepapers or thought-leadership reports with executive summaries and data citations.
- `youtube_scripts` — **YouTube Video Scripts**: Write full video scripts (hook, body, CTA) for YouTube including timestamps and b-roll notes.

</details>

<details>
<summary><b>Research & Analysis</b> (29)</summary>

- `browser_research_skill` — **Browser Research Skill**: Browser Research Skill: production-ready system skill for browser research workflows.
- `competitive_positioning_analyzer` — **Competitive Positioning Analyzer**: Competitive Positioning Analyzer: production-ready operating skill for market research workflows.
- `competitor_analysis` — **Competitor Analysis**: Identify key competitors, analyse their products/pricing/positioning, and highlight differentiation opportunities.
- `context-research` — **Context Research**: Evaluate context sufficiency for a goal and auto-research knowledge gaps online (web search → CloakBrowser stealth fetc…
- `customer_profiling` — **Customer Persona Profiling**: Build detailed buyer personas including demographics, goals, pain points, channels, and objections.
- `data_interpretation` — **Data Interpretation**: Interpret datasets, identify patterns, and translate numbers into clear business insights and recommendations.
- `defensive_osint_brief_builder` — **Defensive OSINT Brief Builder**: Defensive OSINT Brief Builder: production-ready governance skill for research security workflows.
- `fact_checking_workflow_runner` — **Fact Checking Workflow Runner**: Fact Checking Workflow Runner: production-ready operating skill for research quality workflows.
- `industry_report` — **Industry Report Generation**: Generate structured industry reports covering market dynamics, regulatory environment, and future outlook.
- `keyword_search_plan_builder` — **Keyword Search Plan Builder**: Keyword Search Plan Builder: production-ready skill for search research workflows.
- `last30days` — **Last 30 Days Multi-Source Research**: Research what people actually say about a topic in the last 30 days across Reddit, X, YouTube, TikTok, Hacker News, Pol…
- `literature_review` — **Literature Review & Summarisation**: Summarise research papers, industry reports, or long documents into concise, actionable briefs.
- `market_monitoring_brief_builder` — **Market Monitoring Brief Builder**: Market Monitoring Brief Builder: production-ready operating skill for market intelligence workflows.
- `market_positioning` — **Market Positioning**: Market Positioning: execute this capability end-to-end and return a structured, decision-ready result for Research & An…
- `market_research` — **Market Research**: Research market size, growth trends, customer segments, and key drivers for a given industry or niche.
- `market_trend_synthesizer` — **Market Trend Synthesizer**: Market Trend Synthesizer: production-ready operating skill for market research workflows.
- `pricing_analysis` — **Pricing Analysis**: Analyse competitive pricing, evaluate pricing models, and recommend optimal pricing strategy.
- `research_brief_synthesizer` — **Research Brief Synthesizer**: Research Brief Synthesizer: production-ready operating skill for research workflows.
- `risk_assessment` — **Risk Assessment**: Identify and score business, market, or operational risks, with mitigation strategies for each.
- `swot_analysis` — **SWOT Analysis**: Perform a structured SWOT (Strengths, Weaknesses, Opportunities, Threats) analysis for a company or product.
- `sentiment_analysis` — **Sentiment Analysis**: Analyse sentiment from customer reviews, social media posts, or news articles for any topic or brand.
- `source_credibility_checker` — **Source Credibility Checker**: Source Credibility Checker: production-ready system skill for research quality workflows.
- `source_synthesis_reviewer` — **Source Synthesis Reviewer**: Source Synthesis Reviewer: production-ready governance skill for research quality workflows.
- `survey_design` — **Survey Design**: Design research surveys with well-structured questions to gather actionable customer or market insights.
- `synthesis_quality_reviewer` — **Synthesis Quality Reviewer**: Synthesis Quality Reviewer: production-ready governance skill for research quality workflows.
- `topic_researcher` — **Topic Researcher**: Topic Researcher: production-ready operating skill for research workflows.
- `trend_identification` — **Trend Identification**: Identify emerging trends from news, social media, and search data to inform strategy and content.
- `web_fetch_safety_reviewer` — **Web Fetch Safety Reviewer**: Web Fetch Safety Reviewer: production-ready operating skill for research workflow workflows.
- `web_search_plan_builder` — **Web Search Plan Builder**: Web Search Plan Builder: production-ready operating skill for research workflow workflows.

</details>

<details>
<summary><b>Trading & Finance</b> (16)</summary>

- `arbitrage_detection` — **Arbitrage Detection**: Identify cross-exchange or cross-market arbitrage opportunities with entry size, expected profit, and execution risk.
- `crypto_signals` — **Crypto Trading Signals**: Generate crypto trading signals based on technical and on-chain data with entry, stop-loss, and target levels.
- `defi_analysis` — **DeFi Protocol Analysis**: Analyse DeFi protocols: TVL, yields, smart contract risks, tokenomics, and investment thesis.
- `earnings_analysis` — **Earnings Report Analysis**: Analyse quarterly earnings reports, compare to estimates, and assess impact on stock/crypto price.
- `fundamental_analysis` — **Fundamental Analysis**: Evaluate the intrinsic value of assets by analysing financials, moat, management, and macro factors.
- `market_sentiment_scoring` — **Market Sentiment Scoring**: Score overall market sentiment (0–100) from news, social, and on-chain signals with a directional outlook.
- `mirofish_prediction` — **MiroFish Swarm Prediction**: Run MiroFish-inspired swarm simulations to predict market outcome probabilities using crowd-intelligence modelling.
- `options_strategy` — **Options Strategy Development**: Develop options trading strategies (covered calls, spreads, straddles) with breakeven and max profit/loss analysis.
- `performance_tracking` — **Performance Tracking**: Performance Tracking: execute this capability end-to-end and return a structured, decision-ready result for Trading & F…
- `polymarket_research` — **Polymarket Research**: Research Polymarket prediction market events, estimate edge, and identify high-probability trading opportunities.
- `portfolio_optimisation` — **Portfolio Optimisation**: Optimise portfolio allocation using risk/return analysis, correlation matrices, and position sizing.
- `prediction_market_analysis` — **Prediction Market Analysis**: Prediction Market Analysis: execute this capability end-to-end and return a structured, decision-ready result for Tradi…
- `price_prediction` — **Price Prediction**: Price Prediction: execute this capability end-to-end and return a structured, decision-ready result for Trading & Finan…
- `swarm_simulation` — **Swarm Simulation**: Swarm Simulation: execute this capability end-to-end and return a structured, decision-ready result for Trading & Finan…
- `technical_analysis` — **Technical Analysis**: Perform chart pattern recognition and technical indicator analysis (RSI, MACD, Bollinger Bands) for assets.
- `risk_management` — **Trading Risk Management**: Calculate position sizes, Kelly criterion, max drawdown limits, and risk-of-ruin for a trading strategy.

</details>

<details>
<summary><b>Social Media</b> (14)</summary>

- `community_management` — **Community Management**: Draft community management responses, moderation guidelines, and pinned posts for Discord, Reddit, and Facebook Groups.
- `hashtag_research` — **Hashtag Research**: Research and categorise optimal hashtags by volume and competition for Instagram, TikTok, and LinkedIn.
- `influencer_outreach` — **Influencer Outreach Messaging**: Write personalised influencer partnership proposals and outreach DMs that lead to collaboration discussions.
- `instagram_caption` — **Instagram Caption Writing**: Write visually evocative Instagram captions with storytelling, emojis, and 20–30 targeted hashtags.
- `linkedin_post` — **LinkedIn Post Writing**: Write professional LinkedIn posts that drive engagement, establish thought leadership, and grow connections.
- `linkedin_optimization` — **Linkedin Optimization**: Linkedin Optimization: execute this capability end-to-end and return a structured, decision-ready result for Social Med…
- `engagement_strategy` — **Social Engagement Strategy**: Develop a platform-specific engagement strategy: comment approach, DM funnels, community triggers, and growth hacks.
- `social_analytics` — **Social Media Analytics Interpretation**: Interpret social media metrics (reach, engagement rate, saves, shares) and provide optimisation recommendations.
- `thought_leadership` — **Thought Leadership**: Thought Leadership: execute this capability end-to-end and return a structured, decision-ready result for Social Media …
- `tiktok_hooks` — **TikTok Hook Writing**: Write pattern-interrupting TikTok hooks for the first 3 seconds to stop the scroll and maximise watch time.
- `tiktok_scripting` — **Tiktok Scripting**: Tiktok Scripting: execute this capability end-to-end and return a structured, decision-ready result for Social Media wo…
- `twitter_thread` — **Twitter/X Thread Writing**: Write engaging, educational Twitter/X threads with a strong hook, numbered points, and call-to-follow ending.
- `viral_content_creation` — **Viral Content Creation**: Viral Content Creation: execute this capability end-to-end and return a structured, decision-ready result for Social Me…
- `viral_content_ideas` — **Viral Content Ideation**: Generate viral content ideas using trending formats, meme frameworks, and platform algorithm triggers.

</details>

<details>
<summary><b>Lead Generation & Sales</b> (53)</summary>

- `ab_testing` — **A/B Testing Framework**: Design and analyze A/B tests for outreach sequences, subject lines, CTAs, and messaging. Returns test variants, success…
- `proposal_writing` — **Business Proposal Writing**: Write professional business proposals and statements of work with problem statement, solution, timeline, and pricing.
- `crm_enrichment` — **CRM Lead Enrichment**: Enrich CRM records with additional data points: company funding status, tech stack, recent news, employee growth, job o…
- `crm_notes` — **CRM Update Note Generation**: Generate structured CRM call/meeting notes from raw bullet points, including next steps and deal stage updates.
- `crm_update_planner` — **CRM Update Planner**: CRM Update Planner: production-ready Money Mode and operations skill for crm workflows.
- `cold_email_draft_reviewer` — **Cold Email Draft Reviewer**: Cold Email Draft Reviewer: production-ready operating skill for outreach safety workflows.
- `cold_email_outreach` — **Cold Email Outreach Sequences**: Write 3–5 touch cold email sequences with subject lines, personalisation hooks, and automated follow-ups.
- `cold_email_sequence_planner` — **Cold Email Sequence Planner**: Cold Email Sequence Planner: production-ready operating skill for outreach safety workflows.
- `cold_outreach_risk_reviewer` — **Cold Outreach Risk Reviewer**: Cold Outreach Risk Reviewer: production-ready operating skill for outreach safety workflows.
- `sequence_builder` — **Cold Sequence Builder**: Build multi-channel cold outreach sequences with day-by-day touchpoints across email, LinkedIn, and WhatsApp. Includes …
- `customer_segment_analyzer` — **Customer Segment Analyzer**: Customer Segment Analyzer: production-ready operating skill for growth research workflows.
- `dns_verification_checklist_builder` — **DNS Verification Checklist Builder**: DNS Verification Checklist Builder: production-ready skill for email infra workflows.
- `close_deal` — **Deal Closing Scripts**: Generate proven closing scripts and techniques for B2B deals including assumptive close, urgency creation, summary clos…
- `discovery_call_prep` — **Discovery Call Preparation**: Prepare discovery call question frameworks, research checklists, and talk tracks for sales reps.
- `email_campaign_approval_planner` — **Email Campaign Approval Planner**: Email Campaign Approval Planner: production-ready operating skill for email operations workflows.
- `email_deliverability_checker` — **Email Deliverability Checker**: Email Deliverability Checker: production-ready operating skill for email operations workflows.
- `email_personalizer` — **Email Personalizer**: Email Personalizer: production-ready Money Mode and operations skill for outreach workflows.
- `follow_up_automation_planner` — **Follow-Up Automation Planner**: Follow-Up Automation Planner: production-ready skill for sales ops workflows.
- `follow_up_message_writer` — **Follow-Up Message Writer**: Follow-Up Message Writer: production-ready skill for sales ops workflows.
- `follow_up_sequence_reviewer` — **Follow-Up Sequence Reviewer**: Follow-Up Sequence Reviewer: production-ready skill for sales ops workflows.
- `icp_match_score_reviewer` — **ICP Match Score Reviewer**: ICP Match Score Reviewer: production-ready operating skill for sales qualification workflows.
- `icp_researcher` — **ICP Researcher**: ICP Researcher: production-ready Money Mode and operations skill for lead generation workflows.
- `icp_scoring_model_reviewer` — **ICP Scoring Model Reviewer**: ICP Scoring Model Reviewer: production-ready operating skill for sales qualification workflows.
- `lead_enrichment_validator` — **Lead Enrichment Validator**: Lead Enrichment Validator: production-ready operating skill for sales data quality workflows.
- `lead_generation_campaign_planner` — **Lead Generation Campaign Planner**: Lead Generation Campaign Planner: production-ready operating skill for sales campaigns workflows.
- `lead_hunting_researcher` — **Lead Hunting Researcher**: Lead Hunting Researcher: production-ready operating skill for sales research workflows.
- `qualification_scoring` — **Lead Qualification Scoring**: Score inbound and outbound leads against your Ideal Customer Profile (ICP) using firmographic, technographic, and inten…
- `lead_scoring` — **Lead Scoring Framework**: Build a lead scoring model with demographic and behavioural signals, point weights, and MQL/SQL thresholds.
- `lead_scraping` — **Lead Scraping**: Scrape B2B leads from public directories, LinkedIn-style sources, and business databases. Returns enriched lead lists w…
- `lead_source_finder` — **Lead Source Finder**: Lead Source Finder: production-ready Money Mode and operations skill for lead generation workflows.
- `linkedin_prospecting` — **LinkedIn Prospecting**: Write LinkedIn connection requests, InMails, and follow-up messages for targeted B2B prospecting.
- `list_segmentation` — **List Segmentation**: List Segmentation: execute this capability end-to-end and return a structured, decision-ready result for Lead Generatio…
- `negotiation_tactics` — **Negotiation Tactics**: Provide negotiation strategies and tactical scripts for B2B deals including anchoring, value stacking, concession plann…
- `niche_targeting_reviewer` — **Niche Targeting Reviewer**: Niche Targeting Reviewer: production-ready operating skill for growth research workflows.
- `objection_handling` — **Objection Handling Scripts**: Create objection-handling scripts for top sales objections with empathy statements and counter-questions.
- `open_rate_experiment_analyzer` — **Open Rate Experiment Analyzer**: Open Rate Experiment Analyzer: production-ready operating skill for email operations workflows.
- `outreach_script_generator` — **Outreach Script Generator**: Generate personalized outreach scripts for cold email, LinkedIn, and WhatsApp tailored to the lead's context, pain poin…
- `outreach_sequence_planner` — **Outreach Sequence Planner**: Outreach Sequence Planner: production-ready Money Mode and operations skill for outreach workflows.
- `outreach_sequencing` — **Outreach Sequencing**: Outreach Sequencing: execute this capability end-to-end and return a structured, decision-ready result for Lead Generat…
- `partner_scoring` — **Partnership Fit Scoring**: Score potential partners on audience overlap, complementary offerings, reach, brand alignment, and deal feasibility. Re…
- `pitch_deck_generator` — **Partnership Pitch Deck Generator**: Generate partnership pitch deck outlines and slide content for JV proposals, affiliate arrangements, and co-marketing c…
- `prospect_qualifier` — **Prospect Qualifier**: Prospect Qualifier: production-ready Money Mode and operations skill for lead qualification workflows.
- `prospect_research` — **Prospect Research**: Prospect Research: execute this capability end-to-end and return a structured, decision-ready result for Lead Generatio…
- `reply_tracker` — **Reply & Engagement Tracker**: Track reply rates, engagement signals, and conversation status across outreach sequences. Surfaces hot leads and recomm…
- `closing_scripts` — **Sales Closing Scripts**: Write assumptive close, trial close, and urgency close scripts tailored to specific deal scenarios.
- `follow_up_sequences` — **Sales Follow-Up Sequences**: Write multi-touch post-demo or post-meeting follow-up sequences with value-add content and soft nudges.
- `sales_forecast_reviewer` — **Sales Forecast Reviewer**: Sales Forecast Reviewer: production-ready operating skill for sales forecasting workflows.
- `objection_handler` — **Sales Objection Handler**: Generate word-for-word responses to common sales objections using empathy-bridge-ask technique and proven frameworks. C…
- `sales_pipeline_health_checker` — **Sales Pipeline Health Checker**: Sales Pipeline Health Checker: production-ready operating skill for sales operations workflows.
- `sales_pitch_deck` — **Sales Pitch Deck Outline**: Create structured sales pitch deck outlines with slide-by-slide content briefs and key messages.
- `spam_risk_analyzer` — **Spam Risk Analyzer**: Spam Risk Analyzer: production-ready operating skill for outreach safety workflows.
- `warmup_planning` — **Warmup Planning**: Warmup Planning: execute this capability end-to-end and return a structured, decision-ready result for Lead Generation …
- `website_audit` — **Website Audit**: Website Audit: execute this capability end-to-end and return a structured, decision-ready result for Lead Generation & …

</details>

<details>
<summary><b>Customer Support</b> (16)</summary>

- `churn_prevention` — **Churn Prevention Outreach**: Write at-risk customer outreach messages, win-back emails, and cancellation-flow save scripts.
- `customer_notification_approval_planner` — **Customer Notification Approval Planner**: Customer Notification Approval Planner: production-ready operating skill for customer communications workflows.
- `customer_service_workflow_planner` — **Customer Service Workflow Planner**: Customer Service Workflow Planner: production-ready operating skill for customer support ops workflows.
- `customer_status_update_writer` — **Customer Status Update Writer**: Customer Status Update Writer: production-ready operating skill for customer communications workflows.
- `customer_success_checkin` — **Customer Success Check-ins**: Write QBR agendas, check-in email templates, and health score messaging for customer success workflows.
- `customer_support_triager` — **Customer Support Triager**: Customer Support Triager: production-ready Money Mode and operations skill for customer support workflows.
- `escalation_handling` — **Escalation Handling**: Write escalation scripts and manager-level response frameworks for angry customers, legal threats, and media escalation…
- `faq_generation` — **FAQ Document Generation**: Generate comprehensive FAQ documents from product documentation, past tickets, or knowledge base articles.
- `faq_knowledge_base_builder` — **FAQ Knowledge Base Builder**: FAQ Knowledge Base Builder: production-ready operating skill for customer support knowledge workflows.
- `feature_request_logging` — **Feature Request Logging**: Generate structured feature request cards from raw customer feedback for product teams.
- `refund_communication` — **Refund & Returns Communication**: Write clear, empathetic refund, cancellation, and returns communication that reduces churn and preserves goodwill.
- `refund_case_reviewer` — **Refund Case Reviewer**: Refund Case Reviewer: production-ready operating skill for customer support risk workflows.
- `support_response_reviewer` — **Support Response Reviewer**: Support Response Reviewer: production-ready Money Mode and operations skill for customer support workflows.
- `response_templates` — **Support Response Templates**: Create a library of polished, empathetic support response templates for common issues, bugs, and billing questions.
- `support_ticket_tracker` — **Support Ticket Tracker**: Support Ticket Tracker: production-ready operating skill for customer support ops workflows.
- `ticket_triage` — **Support Ticket Triage**: Categorise, prioritise, and suggest responses for inbound support tickets using a structured triage framework.

</details>

<details>
<summary><b>Development & Technical</b> (63)</summary>

- `ai_scan_plan_builder` — **AI Scan Plan Builder**: AI Scan Plan Builder: production-ready governance skill for ai engineering workflows.
- `ai_ml_implementation_reviewer` — **AI/ML Implementation Reviewer**: AI/ML Implementation Reviewer: production-ready governance skill for ai engineering workflows.
- `api_documentation` — **API Documentation Writing**: Write clear OpenAPI/REST API documentation with endpoint descriptions, parameters, examples, and error codes.
- `api_route_inspector` — **API Route Inspector**: API Route Inspector: production-ready system skill for api workflows.
- `anomaly_alert_rule_planner` — **Anomaly Alert Rule Planner**: Anomaly Alert Rule Planner: production-ready reliability skill for observability workflows.
- `architecture_mapper` — **Architecture Mapper**: Architecture Mapper: production-ready system skill for architecture workflows.
- `backend_health_checker` — **Backend Health Checker**: Backend Health Checker: production-ready system skill for backend workflows.
- `bug_finder` — **Bug Finder**: Bug Finder: production-ready system skill for debugging workflows.
- `bug_report_analysis` — **Bug Report Analysis**: Analyse bug reports, identify root causes, assign severity, and suggest fixes or investigation steps.
- `changelog_writer` — **Changelog Writer**: Changelog Writer: production-ready reliability skill for release ops workflows.
- `code_review` — **Code Review**: Review code for bugs, security vulnerabilities, performance issues, and adherence to best practices.
- `codebase_reader` — **Codebase Reader**: Codebase Reader: production-ready system skill for code intelligence workflows.
- `command_safety_classifier` — **Command Safety Classifier**: Command Safety Classifier: production-ready system skill for command safety workflows.
- `context_injection_safety_reviewer` — **Context Injection Safety Reviewer**: Context Injection Safety Reviewer: production-ready governance skill for prompt security workflows.
- `coverage_gap_analyzer` — **Coverage Gap Analyzer**: Coverage Gap Analyzer: production-ready governance skill for testing workflows.
- `dashboard_skill_sync_checker` — **Dashboard Skill Sync Checker**: Dashboard Skill Sync Checker: production-ready system skill for dashboard workflows.
- `db_query_optimisation` — **Database Query Optimisation**: Analyse and optimise SQL queries for performance, suggest indexes, and rewrite inefficient patterns.
- `database_schema_analyzer` — **Database Schema Analyzer**: Database Schema Analyzer: production-ready system skill for database workflows.
- `dependency_vulnerability_checker` — **Dependency Vulnerability Checker**: Dependency Vulnerability Checker: production-ready system skill for security workflows.
- `deployment_state_tracker` — **Deployment State Tracker**: Deployment State Tracker: production-ready reliability skill for release ops workflows.
- `devops_automation` — **DevOps & CI/CD Automation**: Write CI/CD pipeline configs, Dockerfile, Kubernetes manifests, and deployment scripts.
- `devops_infrastructure_reviewer` — **DevOps Infrastructure Reviewer**: DevOps Infrastructure Reviewer: production-ready governance skill for devops workflows.
- `diagnostic_report_builder` — **Diagnostic Report Builder**: Diagnostic Report Builder: production-ready reliability skill for observability workflows.
- `documentation_writer` — **Documentation Writer**: Documentation Writer: production-ready system skill for documentation workflows.
- `error_trace_analyzer` — **Error Trace Analyzer**: Error Trace Analyzer: production-ready system skill for debugging workflows.
- `failure_forensics_analyzer` — **Failure Forensics Analyzer**: Failure Forensics Analyzer: production-ready system skill for reliability workflows.
- `frontend_build_checker` — **Frontend Build Checker**: Frontend Build Checker: production-ready system skill for frontend workflows.
- `human_approval_gate_planner` — **Human Approval Gate Planner**: Human Approval Gate Planner: production-ready system skill for approval workflows.
- `local_file_reader` — **Local File Reader**: Local File Reader: production-ready system skill for filesystem workflows.
- `local_file_writer` — **Local File Writer**: Local File Writer: production-ready system skill for filesystem workflows.
- `ollama_model_checker` — **Ollama Model Checker**: Ollama Model Checker: production-ready system skill for model runtime workflows.
- `patch_rollout_planner` — **Patch Rollout Planner**: Patch Rollout Planner: production-ready reliability skill for release ops workflows.
- `persona_creation` — **Persona Creation**: Persona Creation: execute this capability end-to-end and return a structured, decision-ready result for Development & T…
- `prompt_injection_scan_planner` — **Prompt Injection Scan Planner**: Prompt Injection Scan Planner: production-ready governance skill for prompt security workflows.
- `provider_fallback_planner` — **Provider Fallback Planner**: Provider Fallback Planner: production-ready reliability skill for runtime resilience workflows.
- `python_implementation_planner` — **Python Implementation Planner**: Python Implementation Planner: production-ready governance skill for python workflows.
- `python_service_health_checker` — **Python Service Health Checker**: Python Service Health Checker: production-ready system skill for python workflows.
- `refactor_planner` — **Refactor Planner**: Refactor Planner: production-ready system skill for maintenance workflows.
- `regression_detector` — **Regression Detector**: Regression Detector: production-ready system skill for testing workflows.
- `release_versioning_checker` — **Release Versioning Checker**: Release Versioning Checker: production-ready reliability skill for release ops workflows.
- `remote_compute_planner` — **Remote Compute Planner**: Remote Compute Planner: production-ready system skill for compute workflows.
- `resource_usage_optimizer` — **Resource Usage Optimizer**: Resource Usage Optimizer: production-ready system skill for performance workflows.
- `rollback_plan_reviewer` — **Rollback Plan Reviewer**: Rollback Plan Reviewer: production-ready reliability skill for release ops workflows.
- `sandbox_test_runner` — **Sandbox Test Runner**: Sandbox Test Runner: production-ready system skill for testing workflows.
- `secure_code_reviewer` — **Secure Code Reviewer**: Secure Code Reviewer: production-ready system skill for security review workflows.
- `security_checklist` — **Security Audit Checklist**: Generate context-specific security audit checklists covering OWASP Top 10, auth, data handling, and infrastructure.
- `security_audit_planner` — **Security Audit Planner**: Security Audit Planner: production-ready governance skill for security workflows.
- `security_test_plan_builder` — **Security Test Plan Builder**: Security Test Plan Builder: production-ready governance skill for security workflows.
- `security_threat_modeler` — **Security Threat Modeler**: Security Threat Modeler: production-ready system skill for security workflows.
- `session_persistence_checker` — **Session Persistence Checker**: Session Persistence Checker: production-ready reliability skill for runtime resilience workflows.
- `shell_command_execution_reviewer` — **Shell Command Execution Reviewer**: Shell Command Execution Reviewer: production-ready governance skill for command safety workflows.
- `skill_registry_validator` — **Skill Registry Validator**: Skill Registry Validator: production-ready system skill for skill system workflows.
- `architecture_review` — **System Architecture Review**: Review system architecture for scalability, reliability, security, and cost efficiency with improvement recommendations.
- `system_startup_diagnostics` — **System Startup Diagnostics**: System Startup Diagnostics: production-ready system skill for health workflows.
- `system_status_reporter` — **System Status Reporter**: System Status Reporter: production-ready reliability skill for observability workflows.
- `technical_spec` — **Technical Specification Writing**: Write detailed technical specs, system design documents, and architecture decision records (ADRs).
- `test_case_generation` — **Test Case Generation**: Generate comprehensive test cases (unit, integration, edge cases) from feature descriptions or code.
- `test_generator` — **Test Generator**: Test Generator: production-ready system skill for testing workflows.
- `trading_bot_coding` — **Trading Bot Coding**: Trading Bot Coding: execute this capability end-to-end and return a structured, decision-ready result for Development &…
- `ui_ux_auditor` — **UI/UX Auditor**: UI/UX Auditor: production-ready system skill for ui quality workflows.
- `ux_writing` — **UX Writing**: UX Writing: execute this capability end-to-end and return a structured, decision-ready result for Development & Technic…
- `vault_index_health_checker` — **Vault Index Health Checker**: Vault Index Health Checker: production-ready reliability skill for knowledge runtime workflows.
- `vault_retrieval_quality_checker` — **Vault Retrieval Quality Checker**: Vault Retrieval Quality Checker: production-ready reliability skill for knowledge runtime workflows.

</details>

<details>
<summary><b>Data Analysis</b> (18)</summary>

- `ab_test_analysis` — **A/B Test Analysis**: Analyse A/B test results for statistical significance, effect size, and practical recommendations.
- `anomaly_detection` — **Anomaly Detection**: Detect data anomalies, outliers, and unusual patterns in time-series or cross-sectional datasets.
- `csv_insights` — **CSV Data Insights**: Extract key insights, trends, and anomalies from CSV or tabular data with actionable recommendations.
- `csv_output_validator` — **CSV Output Validator**: CSV Output Validator: production-ready reliability skill for data quality workflows.
- `cohort_analysis` — **Cohort Analysis**: Perform cohort analysis on user/customer data to identify retention curves, LTV trends, and churn patterns.
- `funnel_analysis` — **Conversion Funnel Analysis**: Analyse conversion funnels, identify drop-off points, and generate optimisation hypotheses.
- `daily_report_builder` — **Daily Report Builder**: Daily Report Builder: production-ready operating skill for reporting workflows.
- `data_cleaning_plan` — **Data Cleaning Plan**: Create a data cleaning and quality assurance plan for raw datasets including deduplication, normalisation, and validati…
- `data_export_validator` — **Data Export Validator**: Data Export Validator: production-ready reliability skill for data pipeline workflows.
- `data_extraction_planner` — **Data Extraction Planner**: Data Extraction Planner: production-ready reliability skill for data pipeline workflows.
- `forecasting` — **Data-Driven Forecasting**: Generate statistical forecasts using historical data trends, seasonality, and growth rate analysis.
- `executive_summary_writer` — **Executive Summary Writer**: Executive Summary Writer: production-ready operating skill for reporting workflows.
- `kpi_dashboard_design` — **KPI Dashboard Design**: Design KPI dashboard structures with metric definitions, visualisation types, and data source mappings.
- `message_performance_tracking` — **Message Performance Tracking**: Message Performance Tracking: execute this capability end-to-end and return a structured, decision-ready result for Dat…
- `order_aggregation` — **Order Aggregation**: Order Aggregation: execute this capability end-to-end and return a structured, decision-ready result for Data Analysis …
- `profit_margin_calc` — **Profit Margin Calc**: Profit Margin Calc: execute this capability end-to-end and return a structured, decision-ready result for Data Analysis…
- `report_generation` — **Report Generation**: Report Generation: execute this capability end-to-end and return a structured, decision-ready result for Data Analysis …
- `trend_analysis` — **Trend Analysis**: Trend Analysis: execute this capability end-to-end and return a structured, decision-ready result for Data Analysis wor…

</details>

<details>
<summary><b>E-commerce & Product</b> (35)</summary>

- `affiliate_offer_evaluator` — **Affiliate Offer Evaluator**: Affiliate Offer Evaluator: production-ready Money Mode and operations skill for affiliate workflows.
- `amazon_listing` — **Amazon Listing Optimisation**: Optimise Amazon product titles, bullet points, descriptions, and backend keywords for search rank and conversion.
- `amazon_product_researcher` — **Amazon Product Researcher**: Amazon Product Researcher: production-ready operating skill for commerce research workflows.
- `auto_reorder_policy_reviewer` — **Auto-Reorder Policy Reviewer**: Auto-Reorder Policy Reviewer: production-ready operating skill for inventory ops workflows.
- `review_analysis` — **Customer Review Analysis**: Analyse product reviews to identify top praise themes, recurring complaints, and product improvement opportunities.
- `dropshipping_research` — **Dropshipping Research**: Identify winning dropshipping products using saturation scores, supplier quality, and ad spend signals.
- `ecommerce_product_validator` — **Ecommerce Product Validator**: Ecommerce Product Validator: production-ready Money Mode and operations skill for ecommerce research workflows.
- `ecommerce_trend_detector` — **Ecommerce Trend Detector**: Ecommerce Trend Detector: production-ready operating skill for commerce research workflows.
- `inventory_forecasting` — **Inventory Forecasting**: Forecast inventory requirements using sales velocity, lead times, seasonality, and safety stock formulas.
- `inventory_signal_analyzer` — **Inventory Signal Analyzer**: Inventory Signal Analyzer: production-ready Money Mode and operations skill for inventory workflows.
- `listing_automation_planner` — **Listing Automation Planner**: Listing Automation Planner: production-ready operating skill for commerce ops workflows.
- `low_stock_alert_planner` — **Low Stock Alert Planner**: Low Stock Alert Planner: production-ready operating skill for inventory ops workflows.
- `marketplace_competition_analyzer` — **Marketplace Competition Analyzer**: Marketplace Competition Analyzer: production-ready operating skill for commerce research workflows.
- `marketplace_listing_optimizer` — **Marketplace Listing Optimizer**: Marketplace Listing Optimizer: production-ready Money Mode and operations skill for marketplace workflows.
- `order_routing_rule_auditor` — **Order Routing Rule Auditor**: Order Routing Rule Auditor: production-ready operating skill for order ops workflows.
- `order_tracking_status_reporter` — **Order Tracking Status Reporter**: Order Tracking Status Reporter: production-ready operating skill for order ops workflows.
- `order_workflow_auditor` — **Order Workflow Auditor**: Order Workflow Auditor: production-ready Money Mode and operations skill for order operations workflows.
- `price_comparison_researcher` — **Price Comparison Researcher**: Price Comparison Researcher: production-ready operating skill for commerce pricing workflows.
- `price_monitoring_rule_planner` — **Price Monitoring Rule Planner**: Price Monitoring Rule Planner: production-ready operating skill for commerce pricing workflows.
- `pricing_strategy` — **Pricing Strategy Development**: Develop dynamic pricing strategies including cost-plus, value-based, and competitive pricing frameworks.
- `product_design_brief_reviewer` — **Product Design Brief Reviewer**: Product Design Brief Reviewer: production-ready operating skill for product ops workflows.
- `product_launch_plan` — **Product Launch Plan**: Create a structured product launch plan with pre-launch, launch-day, and post-launch phases and KPIs.
- `product_research` — **Product Research**: Research product opportunities using demand signals, competition analysis, and margin estimates.
- `returns_reduction` — **Returns Rate Reduction**: Identify root causes of high returns and develop listing, fulfilment, and post-purchase strategies to reduce them.
- `shipment_tracking_update_writer` — **Shipment Tracking Update Writer**: Shipment Tracking Update Writer: production-ready operating skill for order communications workflows.
- `shopify_publish_approval_planner` — **Shopify Publish Approval Planner**: Shopify Publish Approval Planner: production-ready reliability skill for commerce approval workflows.
- `stock_monitoring_reporter` — **Stock Monitoring Reporter**: Stock Monitoring Reporter: production-ready operating skill for inventory ops workflows.
- `supplier_api_contract_reviewer` — **Supplier API Contract Reviewer**: Supplier API Contract Reviewer: production-ready operating skill for supplier ops workflows.
- `supplier_api_sync_checker` — **Supplier API Sync Checker**: Supplier API Sync Checker: production-ready operating skill for supplier ops workflows.
- `supplier_evaluation` — **Supplier Evaluation**: Evaluate and score suppliers across quality, lead time, MOQ, price, and reliability criteria.
- `supplier_risk_checker` — **Supplier Risk Checker**: Supplier Risk Checker: production-ready Money Mode and operations skill for supplier risk workflows.
- `tiktok_trend_scanning` — **Tiktok Trend Scanning**: Tiktok Trend Scanning: execute this capability end-to-end and return a structured, decision-ready result for E-commerce…
- `top_product_ranking_reviewer` — **Top Product Ranking Reviewer**: Top Product Ranking Reviewer: production-ready operating skill for commerce research workflows.
- `trend_spotting_brief_builder` — **Trend Spotting Brief Builder**: Trend Spotting Brief Builder: production-ready operating skill for commerce research workflows.
- `upsell_strategy` — **Upsell & Cross-sell Strategy**: Design upsell and cross-sell sequences for e-commerce checkouts, post-purchase flows, and email triggers.

</details>

<details>
<summary><b>Marketing & SEO</b> (21)</summary>

- `budget_allocator` — **Ad Budget Allocator**: Calculate optimal budget allocation across ad channels, campaigns, and audience segments based on CPM benchmarks, conve…
- `ad_copy_generator` — **Ad Copy Generator**: Generate high-converting ad copy for Meta, Google, and LinkedIn ads including headlines, primary text, descriptions, an…
- `performance_analyzer` — **Ad Performance Analyzer**: Analyze ad campaign performance data, identify underperformers, surface optimization opportunities, and recommend bid/b…
- `brand_voice_guide` — **Brand Voice Guide Creation**: Create a comprehensive brand voice and tone guide with do/don't examples across channels.
- `email_automation_flow` — **Email Automation Flow Design**: Design triggered email automation flows (welcome series, drip campaigns, re-engagement) with branch logic.
- `google_ads_copy` — **Google Ads Copy**: Write responsive search ad headlines and descriptions following Google Ads best practices and character limits.
- `landing_page_copy` — **Landing Page Copywriting**: Write conversion-optimised landing page copy with hero, benefits, social proof, and CTA sections.
- `link_building` — **Link Building Strategy**: Develop a white-hat link building strategy with prospect lists, outreach templates, and content assets.
- `marketing_analytics` — **Marketing Analytics Interpretation**: Interpret marketing dashboards (GA4, Meta Ads, HubSpot) and translate metrics into strategic recommendations.
- `messaging_framework` — **Messaging Framework**: Messaging Framework: execute this capability end-to-end and return a structured, decision-ready result for Marketing & …
- `meta_ads_strategy` — **Meta Ads Strategy**: Meta Ads Strategy: execute this capability end-to-end and return a structured, decision-ready result for Marketing & SE…
- `on_page_seo` — **On-Page SEO Optimisation**: Audit and optimise on-page SEO: title tags, meta descriptions, headings, internal links, and schema markup.
- `ppc_campaign_architecture` — **PPC Campaign Architecture**: PPC Campaign Architecture: execute this capability end-to-end and return a structured, decision-ready result for Market…
- `performance_diagnosis` — **Performance Diagnosis**: Performance Diagnosis: execute this capability end-to-end and return a structured, decision-ready result for Marketing …
- `performance_prediction` — **Performance Prediction**: Performance Prediction: execute this capability end-to-end and return a structured, decision-ready result for Marketing…
- `rss_fetching` — **Rss Fetching**: Rss Fetching: execute this capability end-to-end and return a structured, decision-ready result for Marketing & SEO wor…
- `keyword_research` — **SEO Keyword Research**: Research and cluster SEO keywords by intent, volume, and competition to build a content and ranking strategy.
- `schema_markup` — **Schema Markup**: Schema Markup: execute this capability end-to-end and return a structured, decision-ready result for Marketing & SEO wo…
- `subscriber_management` — **Subscriber Management**: Subscriber Management: execute this capability end-to-end and return a structured, decision-ready result for Marketing …
- `touchpoint_mapping` — **Touchpoint Mapping**: Touchpoint Mapping: execute this capability end-to-end and return a structured, decision-ready result for Marketing & S…
- `visual_identity_brief` — **Visual Identity Brief**: Visual Identity Brief: execute this capability end-to-end and return a structured, decision-ready result for Marketing …

</details>

<details>
<summary><b>Automation & Productivity</b> (53)</summary>

- `action_item_tracker` — **Action Item Tracker**: Action Item Tracker: production-ready operating skill for productivity workflows.
- `agent_memory_health_checker` — **Agent Memory Health Checker**: Agent Memory Health Checker: production-ready governance skill for agent runtime workflows.
- `agent_performance_reviewer` — **Agent Performance Reviewer**: Agent Performance Reviewer: production-ready Money Mode and operations skill for agent ops workflows.
- `archive_retention_planner` — **Archive Retention Planner**: Archive Retention Planner: production-ready reliability skill for resilience workflows.
- `automation_runbook_writer` — **Automation Runbook Writer**: Automation Runbook Writer: production-ready Money Mode and operations skill for workflow automation workflows.
- `backup_readiness_checker` — **Backup Readiness Checker**: Backup Readiness Checker: production-ready reliability skill for resilience workflows.
- `batch_job_planner` — **Batch Job Planner**: Batch Job Planner: production-ready reliability skill for job automation workflows.
- `calendar_schedule_planner` — **Calendar Schedule Planner**: Calendar Schedule Planner: production-ready Money Mode and operations skill for productivity workflows.
- `candidate_outreach_message_reviewer` — **Candidate Outreach Message Reviewer**: Candidate Outreach Message Reviewer: production-ready skill for people ops workflows.
- `chat_task_dispatch_reviewer` — **Chat Task Dispatch Reviewer**: Chat Task Dispatch Reviewer: production-ready governance skill for agent runtime workflows.
- `chatbot_flow_reviewer` — **Chatbot Flow Reviewer**: Chatbot Flow Reviewer: production-ready governance skill for conversation design workflows.
- `compensation_benchmark_brief_builder` — **Compensation Benchmark Brief Builder**: Compensation Benchmark Brief Builder: production-ready skill for people ops workflows.
- `content_curation_planner` — **Content Curation Planner**: Content Curation Planner: production-ready skill for content ops workflows.
- `context_compressor` — **Context Compressor**: Context Compressor: production-ready system skill for context engineering workflows.
- `conversation_flow_designer` — **Conversation Flow Designer**: Conversation Flow Designer: production-ready governance skill for conversation design workflows.
- `cron_schedule_auditor` — **Cron Schedule Auditor**: Cron Schedule Auditor: production-ready reliability skill for job automation workflows.
- `custom_agent_spec_builder` — **Custom Agent Spec Builder**: Custom Agent Spec Builder: production-ready governance skill for agent runtime workflows.
- `customer_audit_trail_reviewer` — **Customer Audit Trail Reviewer**: Customer Audit Trail Reviewer: production-ready skill for customer ops workflows.
- `document_generation_reviewer` — **Document Generation Reviewer**: Document Generation Reviewer: production-ready skill for document ops workflows.
- `document_templates` — **Document Template Creation**: Create reusable business document templates (SOW, NDAs, proposals, reports) with variable placeholders.
- `improvement_proposal_prioritizer` — **Improvement Proposal Prioritizer**: Improvement Proposal Prioritizer: production-ready skill for strategy ops workflows.
- `infrastructure_cost_optimizer` — **Infrastructure Cost Optimizer**: Infrastructure Cost Optimizer: production-ready governance skill for runtime cost workflows.
- `integration_health_checker` — **Integration Health Checker**: Integration Health Checker: production-ready Money Mode and operations skill for integration health workflows.
- `interview_schedule_planner` — **Interview Schedule Planner**: Interview Schedule Planner: production-ready skill for people ops workflows.
- `llm_output_judge` — **LLM Output Judge**: LLM Output Judge: production-ready system skill for evaluation workflows.
- `learning_dataset_curator` — **Learning Dataset Curator**: Learning Dataset Curator: production-ready Money Mode and operations skill for learning data workflows.
- `long_term_memory_policy_reviewer` — **Long-Term Memory Policy Reviewer**: Long-Term Memory Policy Reviewer: production-ready governance skill for memory workflows.
- `meeting_note_structurer` — **Meeting Note Structurer**: Meeting Note Structurer: production-ready operating skill for productivity workflows.
- `meeting_notes` — **Meeting Notes & Action Items**: Summarise meeting transcripts or raw notes into structured minutes with decisions and action items.
- `meeting_summary_writer` — **Meeting Summary Writer**: Meeting Summary Writer: production-ready Money Mode and operations skill for productivity workflows.
- `memory_linker` — **Memory Linker**: Memory Linker: production-ready system skill for memory workflows.
- `memory_writeback_reviewer` — **Memory Writeback Reviewer**: Memory Writeback Reviewer: production-ready governance skill for memory workflows.
- `model_router_evaluator` — **Model Router Evaluator**: Model Router Evaluator: production-ready system skill for model routing workflows.
- `multi_stage_reasoning_planner` — **Multi-Stage Reasoning Planner**: Multi-Stage Reasoning Planner: production-ready governance skill for reasoning workflows.
- `okr_setting` — **OKR Setting & Tracking**: Define quarterly OKRs with measurable key results, confidence scores, and weekly check-in cadences.
- `product_dashboard_metric_mapper` — **Product Dashboard Metric Mapper**: Product Dashboard Metric Mapper: production-ready Money Mode and operations skill for dashboard metrics workflows.
- `project_planning` — **Project Planning**: Create project plans with milestones, task breakdowns, resource assignments, and risk mitigation.
- `prompt_optimizer` — **Prompt Optimizer**: Prompt Optimizer: production-ready system skill for context engineering workflows.
- `reporting_automation` — **Reporting Automation**: Design automated reporting workflows that pull data, format insights, and distribute to stakeholders.
- `sop_creation` — **SOP (Standard Operating Procedure) Creation**: Write detailed SOPs with step-by-step instructions, decision trees, checklists, and roles.
- `schedule_conflict_planner` — **Schedule Conflict Planner**: Schedule Conflict Planner: production-ready operating skill for productivity workflows.
- `self_improvement` — **Self Improvement**: Self Improvement: execute this capability end-to-end and return a structured, decision-ready result for Automation & Pr…
- `skill_gap_prioritizer` — **Skill Gap Prioritizer**: Skill Gap Prioritizer: production-ready governance skill for skill system workflows.
- `skill_generation_planner` — **Skill Generation Planner**: Skill Generation Planner: production-ready governance skill for skill system workflows.
- `skill_search_relevance_checker` — **Skill Search Relevance Checker**: Skill Search Relevance Checker: production-ready governance skill for skill system workflows.
- `task_prioritisation` — **Task Prioritisation Framework**: Prioritise a task list using Eisenhower Matrix, ICE scoring, or MoSCoW frameworks with rationale.
- `task_routing_policy_reviewer` — **Task Routing Policy Reviewer**: Task Routing Policy Reviewer: production-ready governance skill for agent runtime workflows.
- `template_quality_scorer` — **Template Quality Scorer**: Template Quality Scorer: production-ready reliability skill for automation quality workflows.
- `token_budget_planner` — **Token Budget Planner**: Token Budget Planner: production-ready operating skill for resource planning workflows.
- `transcript_insight_extractor` — **Transcript Insight Extractor**: Transcript Insight Extractor: production-ready operating skill for productivity workflows.
- `trigger_rule_auditor` — **Trigger Rule Auditor**: Trigger Rule Auditor: production-ready reliability skill for automation governance workflows.
- `workflow_automation` — **Workflow Automation Design**: Design process automation workflows with triggers, conditions, actions, and tool integration specs.
- `workflow_template_builder` — **Workflow Template Builder**: Workflow Template Builder: production-ready Money Mode and operations skill for workflow automation workflows.

</details>

<details>
<summary><b>Company Building & Strategy</b> (18)</summary>

- `business_plan_generation` — **Business Plan Generation**: Generate comprehensive business plans including executive summary, market analysis, operations plan, and 3-year financi…
- `candidate_screening_assistant` — **Candidate Screening Assistant**: Candidate Screening Assistant: production-ready operating skill for people ops workflows.
- `company_simulation` — **Company Growth Simulation**: Run detailed business simulations with month-by-month projections, scenario modeling (best/base/worst case), and decisi…
- `company_operating_system_mapper` — **Company Operating System Mapper**: Company Operating System Mapper: production-ready operating skill for company ops workflows.
- `culture_operating_principles_writer` — **Culture Operating Principles Writer**: Culture Operating Principles Writer: production-ready operating skill for people ops workflows.
- `go_to_market` — **Go-to-Market Strategy**: Develop detailed GTM strategies with ICP definition, channel prioritization, launch sequences, and first customer acqui…
- `hiring_role_brief_writer` — **Hiring Role Brief Writer**: Hiring Role Brief Writer: production-ready operating skill for people ops workflows.
- `interview_plan_builder` — **Interview Plan Builder**: Interview Plan Builder: production-ready operating skill for people ops workflows.
- `market_entry_strategy` — **Market Entry Strategy**: Market Entry Strategy: execute this capability end-to-end and return a structured, decision-ready result for Company Bu…
- `mission_progress_tracker` — **Mission Progress Tracker**: Mission Progress Tracker: production-ready operating skill for company ops workflows.
- `mitigation_planning` — **Mitigation Planning**: Mitigation Planning: execute this capability end-to-end and return a structured, decision-ready result for Company Buil…
- `org_chart_design` — **Org Chart & Team Structure Design**: Design organizational charts with department structure, reporting lines, role definitions, hiring roadmap, and compensa…
- `org_hierarchy_mapper` — **Org Hierarchy Mapper**: Org Hierarchy Mapper: production-ready operating skill for company ops workflows.
- `reporting_line_reviewer` — **Reporting Line Reviewer**: Reporting Line Reviewer: production-ready operating skill for company ops workflows.
- `storytelling` — **Storytelling**: Storytelling: execute this capability end-to-end and return a structured, decision-ready result for Company Building & …
- `strategic_analysis` — **Strategic Analysis**: Strategic Analysis: execute this capability end-to-end and return a structured, decision-ready result for Company Build…
- `team_onboarding_planner` — **Team Onboarding Planner**: Team Onboarding Planner: production-ready operating skill for people ops workflows.
- `workload_balance_checker` — **Workload Balance Checker**: Workload Balance Checker: production-ready operating skill for company ops workflows.

</details>

<details>
<summary><b>Crypto & Web3</b> (4)</summary>

- `smart_contract_parameters` — **Smart Contract Parameters**: Smart Contract Parameters: execute this capability end-to-end and return a structured, decision-ready result for Crypto…
- `token_launch_strategy` — **Token Launch Strategy**: Create viral token launch campaigns including pre-launch hype building, launch day coordination, influencer activation,…
- `tokenomics_design` — **Tokenomics Design**: Design complete tokenomics models including supply, distribution, vesting schedules, deflationary mechanics, and launch…
- `viral_marketing` — **Viral Marketing**: Viral Marketing: execute this capability end-to-end and return a structured, decision-ready result for Crypto & Web3 wo…

</details>

<details>
<summary><b>Finance & Investment</b> (35)</summary>

- `backtest_plan_reviewer` — **Backtest Plan Reviewer**: Backtest Plan Reviewer: production-ready operating skill for trading research workflows.
- `budget_guardrail_planner` — **Budget Guardrail Planner**: Budget Guardrail Planner: production-ready operating skill for finance governance workflows.
- `burn_rate_analysis` — **Burn Rate & Runway Analysis**: Calculate and analyze monthly burn rate, cash runway, and provide recommendations for extending runway and fundraising …
- `conversion_tracking_checker` — **Conversion Tracking Checker**: Conversion Tracking Checker: production-ready skill for analytics workflows.
- `cost_roi_calculator` — **Cost ROI Calculator**: Cost ROI Calculator: production-ready Money Mode and operations skill for finance ops workflows.
- `daily_profit_alert_reviewer` — **Daily Profit Alert Reviewer**: Daily Profit Alert Reviewer: production-ready governance skill for finance reporting workflows.
- `data_analysis_plan_reviewer` — **Data Analysis Plan Reviewer**: Data Analysis Plan Reviewer: production-ready skill for analytics workflows.
- `earnings_quality_reviewer` — **Earnings Quality Reviewer**: Earnings Quality Reviewer: production-ready skill for finance research workflows.
- `engagement_tracking_reporter` — **Engagement Tracking Reporter**: Engagement Tracking Reporter: production-ready skill for analytics workflows.
- `expense_categorizer` — **Expense Categorizer**: Expense Categorizer: production-ready operating skill for finance ops workflows.
- `financial_analysis_brief_builder` — **Financial Analysis Brief Builder**: Financial Analysis Brief Builder: production-ready operating skill for finance research workflows.
- `financial_modeling` — **Financial Modeling**: Build detailed 3-year financial models with monthly P&L, cash flow projections, unit economics, and scenario analysis.
- `financial_report_reviewer` — **Financial Report Reviewer**: Financial Report Reviewer: production-ready operating skill for finance reporting workflows.
- `fundraising_readiness_reviewer` — **Fundraising Readiness Reviewer**: Fundraising Readiness Reviewer: production-ready governance skill for finance ops workflows.
- `investor_pitch_deck` — **Investor Pitch Deck**: Create investor-grade pitch deck outlines with compelling narratives, financial slides, and market opportunity framing.
- `investor_update_writer` — **Investor Update Writer**: Investor Update Writer: production-ready governance skill for finance communications workflows.
- `invoice_draft_reviewer` — **Invoice Draft Reviewer**: Invoice Draft Reviewer: production-ready operating skill for finance ops workflows.
- `invoice_workflow_checker` — **Invoice Workflow Checker**: Invoice Workflow Checker: production-ready governance skill for finance ops workflows.
- `operating_cost_tracking_reviewer` — **Operating Cost Tracking Reviewer**: Operating Cost Tracking Reviewer: production-ready skill for ops finance workflows.
- `payment_followup_planner` — **Payment Followup Planner**: Payment Followup Planner: production-ready operating skill for finance ops workflows.
- `payment_tracking_reconciler` — **Payment Tracking Reconciler**: Payment Tracking Reconciler: production-ready governance skill for finance ops workflows.
- `payment_validation_reviewer` — **Payment Validation Reviewer**: Payment Validation Reviewer: production-ready governance skill for finance ops workflows.
- `pnl_statement_reviewer` — **PnL Statement Reviewer**: PnL Statement Reviewer: production-ready governance skill for finance reporting workflows.
- `portfolio_optimization_risk_reviewer` — **Portfolio Optimization Risk Reviewer**: Portfolio Optimization Risk Reviewer: production-ready operating skill for finance research workflows.
- `portfolio_tracking_reporter` — **Portfolio Tracking Reporter**: Portfolio Tracking Reporter: production-ready operating skill for finance research workflows.
- `profit_loss_draft_builder` — **Profit/Loss Draft Builder**: Profit/Loss Draft Builder: production-ready governance skill for finance reporting workflows.
- `profit_loss_projection_reviewer` — **Profit/Loss Projection Reviewer**: Profit/Loss Projection Reviewer: production-ready governance skill for finance reporting workflows.
- `sec_filing_analysis_brief_builder` — **SEC Filing Analysis Brief Builder**: SEC Filing Analysis Brief Builder: production-ready governance skill for finance research workflows.
- `tax_calculation_reviewer` — **Tax Calculation Reviewer**: Tax Calculation Reviewer: production-ready governance skill for finance compliance workflows.
- `tax_prep_checklist_builder` — **Tax Prep Checklist Builder**: Tax Prep Checklist Builder: production-ready operating skill for finance compliance workflows.
- `trading_alert_format_reviewer` — **Trading Alert Format Reviewer**: Trading Alert Format Reviewer: production-ready skill for trading comms workflows.
- `trading_signal_aggregator` — **Trading Signal Aggregator**: Trading Signal Aggregator: production-ready operating skill for trading research workflows.
- `trading_signal_quality_reviewer` — **Trading Signal Quality Reviewer**: Trading Signal Quality Reviewer: production-ready operating skill for trading research workflows.
- `unit_economics_analyzer` — **Unit Economics Analyzer**: Unit Economics Analyzer: production-ready operating skill for finance analysis workflows.
- `valuation_methodology_reviewer` — **Valuation Methodology Reviewer**: Valuation Methodology Reviewer: production-ready governance skill for finance ops workflows.

</details>

<details>
<summary><b>Branding & Identity</b> (14)</summary>

- `accessibility_audit_checker` — **Accessibility Audit Checker**: Accessibility Audit Checker: production-ready skill for ui quality workflows.
- `brand_guidelines` — **Brand Guidelines & Identity System**: Create complete brand identity systems including logo brief, color palette, typography, photography style, and usage gu…
- `brand_naming` — **Brand Naming**: Generate creative, ownable brand names with etymology, domain availability assessment, trademark risk, and strategic ra…
- `color_palette_system_reviewer` — **Color Palette System Reviewer**: Color Palette System Reviewer: production-ready skill for brand design workflows.
- `component_spec_writer` — **Component Spec Writer**: Component Spec Writer: production-ready skill for design system workflows.
- `dark_mode_accessibility_reviewer` — **Dark Mode Accessibility Reviewer**: Dark Mode Accessibility Reviewer: production-ready skill for ui quality workflows.
- `design_system_auditor` — **Design System Auditor**: Design System Auditor: production-ready operating skill for design quality workflows.
- `developer_handoff_package_reviewer` — **Developer Handoff Package Reviewer**: Developer Handoff Package Reviewer: production-ready skill for design system workflows.
- `image_prompt_brief_builder` — **Image Prompt Brief Builder**: Image Prompt Brief Builder: production-ready skill for creative ops workflows.
- `image_prompt_safety_reviewer` — **Image Prompt Safety Reviewer**: Image Prompt Safety Reviewer: production-ready skill for creative ops workflows.
- `responsive_layout_checker` — **Responsive Layout Checker**: Responsive Layout Checker: production-ready operating skill for design quality workflows.
- `typography_system` — **Typography System**: Typography System: execute this capability end-to-end and return a structured, decision-ready result for Branding & Ide…
- `ui_quality_issue_finder` — **UI Quality Issue Finder**: UI Quality Issue Finder: production-ready operating skill for design quality workflows.
- `user_flow_design` — **User Flow Design**: User Flow Design: execute this capability end-to-end and return a structured, decision-ready result for Branding & Iden…

</details>

<details>
<summary><b>Growth & Marketing</b> (35)</summary>

- `ab_test_design` — **A/B Test Design**: Design statistically rigorous A/B tests for landing pages, checkout flows, CTAs, and pricing pages. Includes hypothesis…
- `ab_test_plan_builder` — **A/B Test Plan Builder**: A/B Test Plan Builder: production-ready operating skill for experimentation workflows.
- `ad_copy_reviewer` — **Ad Copy Reviewer**: Ad Copy Reviewer: production-ready operating skill for paid ads workflows.
- `brand_positioning_reviewer` — **Brand Positioning Reviewer**: Brand Positioning Reviewer: production-ready skill for brand strategy workflows.
- `brand_voice_guardian` — **Brand Voice Guardian**: Brand Voice Guardian: production-ready operating skill for brand workflows.
- `campaign_idea_brief_builder` — **Campaign Idea Brief Builder**: Campaign Idea Brief Builder: production-ready skill for campaign planning workflows.
- `campaign_schedule_planner` — **Campaign Schedule Planner**: Campaign Schedule Planner: production-ready skill for campaign planning workflows.
- `comment_automation_safety_reviewer` — **Comment Automation Safety Reviewer**: Comment Automation Safety Reviewer: production-ready skill for social automation workflows.
- `competitive_brand_analysis_reviewer` — **Competitive Brand Analysis Reviewer**: Competitive Brand Analysis Reviewer: production-ready skill for brand strategy workflows.
- `funnel_analyzer` — **Conversion Funnel Analyzer**: Analyze conversion funnels stage by stage, identify drop-off points, benchmark against industry rates, and prioritize f…
- `conversion_funnel_analyzer` — **Conversion Funnel Analyzer**: Conversion Funnel Analyzer: production-ready operating skill for conversion workflows.
- `conversion_optimization_planner` — **Conversion Optimization Planner**: Conversion Optimization Planner: production-ready skill for growth experiments workflows.
- `crypto_community_growth_planner` — **Crypto Community Growth Planner**: Crypto Community Growth Planner: production-ready skill for web3 growth workflows.
- `drip_sequence_planner` — **Drip Sequence Planner**: Drip Sequence Planner: production-ready skill for email growth workflows.
- `email_ab_test_analyzer` — **Email A/B Test Analyzer**: Email A/B Test Analyzer: production-ready skill for email growth workflows.
- `email_composition_reviewer` — **Email Composition Reviewer**: Email Composition Reviewer: production-ready skill for email growth workflows.
- `email_deliverability_optimization_checker` — **Email Deliverability Optimization Checker**: Email Deliverability Optimization Checker: production-ready skill for email growth workflows.
- `email_sequence_planner` — **Email Sequence Planner**: Email Sequence Planner: production-ready skill for email growth workflows.
- `growth_ab_test_plan_reviewer` — **Growth A/B Test Plan Reviewer**: Growth A/B Test Plan Reviewer: production-ready skill for growth experiments workflows.
- `growth_loop_design` — **Growth Loop Design**: Design viral growth loops and flywheel mechanics that drive exponential, compound user and revenue growth.
- `growth_marketing_strategy_mapper` — **Growth Marketing Strategy Mapper**: Growth Marketing Strategy Mapper: production-ready operating skill for growth strategy workflows.
- `linkedin_optimizer` — **LinkedIn Profile Optimizer**: Optimize LinkedIn profiles for discoverability, credibility, and lead generation. Covers headline, about section, exper…
- `marketing_budget_allocation_reviewer` — **Marketing Budget Allocation Reviewer**: Marketing Budget Allocation Reviewer: production-ready skill for marketing ops workflows.
- `paid_ads_campaign_planner` — **Paid Ads Campaign Planner**: Paid Ads Campaign Planner: production-ready operating skill for paid ads workflows.
- `plg_strategy` — **Plg Strategy**: Plg Strategy: execute this capability end-to-end and return a structured, decision-ready result for Growth & Marketing …
- `incentive_calculator` — **Referral Incentive Calculator**: Calculate economically optimal referral incentives based on LTV, CAC, and desired viral coefficient. Models cash vs cre…
- `referral_program_design` — **Referral Program Design**: Design end-to-end referral programs including structure (one-sided/two-sided/tiered), reward mechanics, sharing flows, …
- `retention_analysis` — **Retention & Churn Analysis**: Develop retention strategies including churn prediction, re-engagement sequences, habit-forming mechanics, and power us…
- `seo_opportunity_auditor` — **SEO Opportunity Auditor**: SEO Opportunity Auditor: production-ready operating skill for seo workflows.
- `social_content_generation_reviewer` — **Social Content Generation Reviewer**: Social Content Generation Reviewer: production-ready skill for social content workflows.
- `social_post_pipeline_planner` — **Social Post Pipeline Planner**: Social Post Pipeline Planner: production-ready operating skill for social operations workflows.
- `technical_seo_checker` — **Technical SEO Checker**: Technical SEO Checker: production-ready operating skill for seo workflows.
- `video_script_writer` — **Video Script Writer**: Video Script Writer: production-ready operating skill for content production workflows.
- `viral_content_generator` — **Viral Content Generator**: Generate viral LinkedIn posts, carousels, and hook ideas using proven viral formulas (POV, story-lesson, controversial …
- `viral_mechanics` — **Viral Mechanics**: Viral Mechanics: execute this capability end-to-end and return a structured, decision-ready result for Growth & Marketi…

</details>

<details>
<summary><b>Project Management</b> (33)</summary>

- `agent_composition_designer` — **Agent Composition Designer**: Agent Composition Designer: production-ready reliability skill for agent orchestration workflows.
- `agent_coordination_planner` — **Agent Coordination Planner**: Agent Coordination Planner: production-ready reliability skill for agent orchestration workflows.
- `agent_dispatch_auditor` — **Agent Dispatch Auditor**: Agent Dispatch Auditor: production-ready reliability skill for agent orchestration workflows.
- `agent_selection_evaluator` — **Agent Selection Evaluator**: Agent Selection Evaluator: production-ready reliability skill for agent orchestration workflows.
- `agent_task_decomposer` — **Agent Task Decomposer**: Agent Task Decomposer: production-ready system skill for agent orchestration workflows.
- `agent_task_planner` — **Agent Task Planner**: Agent Task Planner: production-ready system skill for agent orchestration workflows.
- `bot_lifecycle_manager` — **Bot Lifecycle Manager**: Bot Lifecycle Manager: production-ready reliability skill for agent orchestration workflows.
- `end_to_end_task_executor` — **End-to-End Task Executor**: End-to-End Task Executor: production-ready system skill for execution workflows.
- `gantt_timeline_reviewer` — **Gantt Timeline Reviewer**: Gantt Timeline Reviewer: production-ready operating skill for project planning workflows.
- `goal_decomposition_reviewer` — **Goal Decomposition Reviewer**: Goal Decomposition Reviewer: production-ready operating skill for goal ops workflows.
- `goal_health_reviewer` — **Goal Health Reviewer**: Goal Health Reviewer: production-ready operating skill for goal ops workflows.
- `implementation_plan_writer` — **Implementation Plan Writer**: Implementation Plan Writer: production-ready system skill for planning workflows.
- `milestone_tracking` — **Milestone & Roadmap Planning**: Create detailed project roadmaps with milestones, dependencies, critical path analysis, and contingency planning.
- `milestone_plan_builder` — **Milestone Plan Builder**: Milestone Plan Builder: production-ready operating skill for planning workflows.
- `multi_agent_coordination_reviewer` — **Multi-Agent Coordination Reviewer**: Multi-Agent Coordination Reviewer: production-ready reliability skill for agent orchestration workflows.
- `multi_agent_result_synthesizer` — **Multi-Agent Result Synthesizer**: Multi-Agent Result Synthesizer: production-ready reliability skill for agent orchestration workflows.
- `multi_agent_synthesis_reviewer` — **Multi-Agent Synthesis Reviewer**: Multi-Agent Synthesis Reviewer: production-ready reliability skill for agent orchestration workflows.
- `okr_progress_reviewer` — **OKR Progress Reviewer**: OKR Progress Reviewer: production-ready operating skill for planning workflows.
- `project_progress_reporter` — **Project Progress Reporter**: Project Progress Reporter: production-ready operating skill for project reporting workflows.
- `raci_matrix_builder` — **RACI Matrix Builder**: RACI Matrix Builder: production-ready operating skill for planning workflows.
- `retrospective_action_planner` — **Retrospective Action Planner**: Retrospective Action Planner: production-ready operating skill for project improvement workflows.
- `sprint_planning` — **Sprint Planning**: Create detailed sprint plans with user stories, acceptance criteria, story point estimation, capacity planning, and def…
- `stakeholder_update_writer` — **Stakeholder Update Writer**: Stakeholder Update Writer: production-ready operating skill for project communications workflows.
- `standup_report_writer` — **Standup Report Writer**: Standup Report Writer: production-ready operating skill for project communications workflows.
- `state_snapshot_aggregator` — **State Snapshot Aggregator**: State Snapshot Aggregator: production-ready reliability skill for state management workflows.
- `task_assignment_reviewer` — **Task Assignment Reviewer**: Task Assignment Reviewer: production-ready operating skill for team ops workflows.
- `task_schedule_optimizer` — **Task Schedule Optimizer**: Task Schedule Optimizer: production-ready operating skill for team ops workflows.
- `team_coordination_brief_builder` — **Team Coordination Brief Builder**: Team Coordination Brief Builder: production-ready operating skill for team ops workflows.
- `whatsapp_notifications` — **Whatsapp Notifications**: Whatsapp Notifications: execute this capability end-to-end and return a structured, decision-ready result for Project M…
- `work_breakdown_builder` — **Work Breakdown Builder**: Work Breakdown Builder: production-ready operating skill for project planning workflows.
- `workflow_design_reviewer` — **Workflow Design Reviewer**: Workflow Design Reviewer: production-ready operating skill for workflow ops workflows.
- `workflow_generation_planner` — **Workflow Generation Planner**: Workflow Generation Planner: production-ready operating skill for workflow ops workflows.
- `workflow_management_auditor` — **Workflow Management Auditor**: Workflow Management Auditor: production-ready operating skill for workflow ops workflows.

</details>

<details>
<summary><b>AETERNUS Engineering Skills</b> (23)</summary>

- `agent_skill_api_and_interface_design` — **Agent Skill: API And Interface Design**: Native engineering workflow skill converted from agent-skills: API And Interface Design.
- `agent_skill_browser_testing_with_devtools` — **Agent Skill: Browser Testing With Devtools**: Native engineering workflow skill converted from agent-skills: Browser Testing With Devtools.
- `agent_skill_ci_cd_and_automation` — **Agent Skill: CI CD And Automation**: Native engineering workflow skill converted from agent-skills: CI CD And Automation.
- `agent_skill_code_review_and_quality` — **Agent Skill: Code Review And Quality**: Native engineering workflow skill converted from agent-skills: Code Review And Quality.
- `agent_skill_code_simplification` — **Agent Skill: Code Simplification**: Native engineering workflow skill converted from agent-skills: Code Simplification.
- `agent_skill_context_engineering` — **Agent Skill: Context Engineering**: Native engineering workflow skill converted from agent-skills: Context Engineering.
- `agent_skill_debugging_and_error_recovery` — **Agent Skill: Debugging And Error Recovery**: Native engineering workflow skill converted from agent-skills: Debugging And Error Recovery.
- `agent_skill_deprecation_and_migration` — **Agent Skill: Deprecation And Migration**: Native engineering workflow skill converted from agent-skills: Deprecation And Migration.
- `agent_skill_documentation_and_adrs` — **Agent Skill: Documentation And ADRs**: Native engineering workflow skill converted from agent-skills: Documentation And ADRs.
- `agent_skill_doubt_driven_development` — **Agent Skill: Doubt Driven Development**: Native engineering workflow skill converted from agent-skills: Doubt Driven Development.
- `agent_skill_frontend_ui_engineering` — **Agent Skill: Frontend UI Engineering**: Native engineering workflow skill converted from agent-skills: Frontend UI Engineering.
- `agent_skill_git_workflow_and_versioning` — **Agent Skill: Git Workflow And Versioning**: Native engineering workflow skill converted from agent-skills: Git Workflow And Versioning.
- `agent_skill_idea_refine` — **Agent Skill: Idea Refine**: Native engineering workflow skill converted from agent-skills: Idea Refine.
- `agent_skill_incremental_implementation` — **Agent Skill: Incremental Implementation**: Native engineering workflow skill converted from agent-skills: Incremental Implementation.
- `agent_skill_interview_me` — **Agent Skill: Interview Me**: Native engineering workflow skill converted from agent-skills: Interview Me.
- `agent_skill_performance_optimization` — **Agent Skill: Performance Optimization**: Native engineering workflow skill converted from agent-skills: Performance Optimization.
- `agent_skill_planning_and_task_breakdown` — **Agent Skill: Planning And Task Breakdown**: Native engineering workflow skill converted from agent-skills: Planning And Task Breakdown.
- `agent_skill_security_and_hardening` — **Agent Skill: Security And Hardening**: Native engineering workflow skill converted from agent-skills: Security And Hardening.
- `agent_skill_shipping_and_launch` — **Agent Skill: Shipping And Launch**: Native engineering workflow skill converted from agent-skills: Shipping And Launch.
- `agent_skill_source_driven_development` — **Agent Skill: Source Driven Development**: Native engineering workflow skill converted from agent-skills: Source Driven Development.
- `agent_skill_spec_driven_development` — **Agent Skill: Spec Driven Development**: Native engineering workflow skill converted from agent-skills: Spec Driven Development.
- `agent_skill_test_driven_development` — **Agent Skill: Test Driven Development**: Native engineering workflow skill converted from agent-skills: Test Driven Development.
- `agent_skill_using_agent_skills` — **Agent Skill: Using Agent Skills**: Native engineering workflow skill converted from agent-skills: Using Agent Skills.

</details>

<details>
<summary><b>Autonomy Governance</b> (6)</summary>

- `autonomy_approval_gate` — **Autonomy Approval Gate**: Require human approval for dangerous actions.
- `autonomy_heartbeat_monitoring` — **Autonomy Heartbeat Monitoring**: Monitor long-running agent loops and heartbeat state.
- `autonomy_loop_detection` — **Autonomy Loop Detection**: Detect repeated ineffective action loops.
- `autonomy_policy_evaluation` — **Autonomy Policy Evaluation**: Evaluate actions against safe/caution/dangerous/forbidden policy.
- `autonomy_self_modification_audit` — **Autonomy Self Modification Audit**: Audit proposed self-modification before approval.
- `autonomy_tool_risk_classification` — **Autonomy Tool Risk Classification**: Classify tool calls before execution.

</details>

<details>
<summary><b>Communication Channels</b> (7)</summary>

- `channel_allowlist_routing` — **Channel Allowlist Routing**: Route messages only from allowed channels/senders.
- `channel_session_routing` — **Channel Session Routing**: Route channel sessions to assigned agents.
- `discord_notification_planner` — **Discord Notification Planner**: Discord Notification Planner: production-ready operating skill for notifications workflows.
- `channel_local_pairing` — **Local Channel Pairing**: Pair local dashboard/mobile sessions with explicit approval.
- `message_routing_auditor` — **Message Routing Auditor**: Message Routing Auditor: production-ready operating skill for communications workflows.
- `notifications` — **Notifications**: Notifications: execute this capability end-to-end and return a structured, decision-ready result for Communication Chan…
- `whatsapp_inbound_triager` — **WhatsApp Inbound Triager**: WhatsApp Inbound Triager: production-ready operating skill for communications workflows.

</details>

<details>
<summary><b>Supervised Finance Workflows</b> (10)</summary>

- `finance_workflow_earnings_reviewer` — **Finance Workflow: Earnings Reviewer**: Draft-only supervised finance workflow for equity-research work.
- `finance_workflow_gl_reconciler` — **Finance Workflow: GL Reconciler**: Draft-only supervised finance workflow for accounting work.
- `finance_workflow_kyc_screener` — **Finance Workflow: KYC Screener**: Draft-only supervised finance workflow for compliance work.
- `finance_workflow_market_researcher` — **Finance Workflow: Market Researcher**: Draft-only supervised finance workflow for markets work.
- `finance_workflow_meeting_prep` — **Finance Workflow: Meeting Prep Agent**: Draft-only supervised finance workflow for relationship-management work.
- `finance_workflow_model_builder` — **Finance Workflow: Model Builder**: Draft-only supervised finance workflow for financial-modeling work.
- `finance_workflow_month_end_closer` — **Finance Workflow: Month End Closer**: Draft-only supervised finance workflow for accounting work.
- `finance_workflow_pitch_agent` — **Finance Workflow: Pitch Agent**: Draft-only supervised finance workflow for investment-banking work.
- `finance_workflow_statement_auditor` — **Finance Workflow: Statement Auditor**: Draft-only supervised finance workflow for audit work.
- `finance_workflow_valuation_reviewer` — **Finance Workflow: Valuation Reviewer**: Draft-only supervised finance workflow for valuation work.

</details>

<details>
<summary><b>Money Mode</b> (16)</summary>

- `client_brief_analyzer` — **Client Brief Analyzer**: Client Brief Analyzer: production-ready Money Mode and operations skill for client work intake workflows.
- `client_delivery_reviewer` — **Client Delivery Reviewer**: Client Delivery Reviewer: production-ready Money Mode and operations skill for delivery quality workflows.
- `deliverable_packager` — **Deliverable Packager**: Deliverable Packager: production-ready Money Mode and operations skill for delivery workflows.
- `earnings_tracker` — **Earnings Tracker**: Earnings Tracker: production-ready Money Mode and operations skill for money mode reporting workflows.
- `money_delivery_approval` — **Money Delivery Approval**: Stage deliverables and block external delivery until approval.
- `money_earnings_lifecycle` — **Money Earnings Lifecycle**: Track pending, available, claimed, and reinvested earnings.
- `money_feedback_analyzer` — **Money Feedback Analyzer**: Money Feedback Analyzer: production-ready Money Mode and operations skill for money mode feedback workflows.
- `money_feedback_ingestion` — **Money Feedback Ingestion**: Convert client/task feedback into memory and improvement notes.
- `money_quote_drafting` — **Money Quote Drafting**: Draft price and delivery quote for owner review.
- `money_task_discovery` — **Money Task Discovery**: Find internal or approved external earning opportunities.
- `money_task_evaluation` — **Money Task Evaluation**: Evaluate fit, risk, scope, and expected value for a task.
- `opportunity_scanner` — **Opportunity Scanner**: Opportunity Scanner: production-ready Money Mode and operations skill for money mode discovery workflows.
- `paid_task_evaluator` — **Paid Task Evaluator**: Paid Task Evaluator: production-ready Money Mode and operations skill for money mode evaluation workflows.
- `proposal_writer` — **Proposal Writer**: Proposal Writer: production-ready Money Mode and operations skill for client work sales workflows.
- `quote_builder` — **Quote Builder**: Quote Builder: production-ready Money Mode and operations skill for pricing workflows.
- `scope_risk_assessor` — **Scope Risk Assessor**: Scope Risk Assessor: production-ready Money Mode and operations skill for client work risk workflows.

</details>

<details>
<summary><b>Wallet & Compute</b> (4)</summary>

- `wallet_compute_quote` — **External Compute Quote**: Draft external compute purchase quotes without executing purchase.
- `wallet_owner_vault_setup` — **Owner Wallet Vault Setup**: Create an encrypted owner-controlled local wallet vault.
- `wallet_claim_request` — **Wallet Claim Request**: Prepare owner claim requests for earned funds.
- `wallet_spend_approval` — **Wallet Spend Approval**: Require owner approval and limits before any spend.

</details>

<details>
<summary><b>Integration & Runtime</b> (9)</summary>

- `api_integration_contract_tester` — **API Integration Contract Tester**: API Integration Contract Tester: production-ready reliability skill for api integration workflows.
- `cross_channel_notification_planner` — **Cross-Channel Notification Planner**: Cross-Channel Notification Planner: production-ready reliability skill for notification ops workflows.
- `discord_integration_checker` — **Discord Integration Checker**: Discord Integration Checker: production-ready reliability skill for communications integration workflows.
- `email_platform_integration_checker` — **Email Platform Integration Checker**: Email Platform Integration Checker: production-ready reliability skill for email integration workflows.
- `quickbooks_sync_reconciler` — **QuickBooks Sync Reconciler**: QuickBooks Sync Reconciler: production-ready reliability skill for finance integration workflows.
- `shopify_inventory_sync_checker` — **Shopify Inventory Sync Checker**: Shopify Inventory Sync Checker: production-ready reliability skill for commerce integration workflows.
- `shopify_webhook_auditor` — **Shopify Webhook Auditor**: Shopify Webhook Auditor: production-ready reliability skill for commerce integration workflows.
- `stripe_data_ingestion_checker` — **Stripe Data Ingestion Checker**: Stripe Data Ingestion Checker: production-ready reliability skill for finance integration workflows.
- `twilio_integration_checker` — **Twilio Integration Checker**: Twilio Integration Checker: production-ready reliability skill for communications integration workflows.

</details>

<details>
<summary><b>Security & Governance</b> (9)</summary>

- `api_key_rotation_planner` — **API Key Rotation Planner**: API Key Rotation Planner: production-ready Money Mode and operations skill for secret operations workflows.
- `audit_log_reviewer` — **Audit Log Reviewer**: Audit Log Reviewer: production-ready Money Mode and operations skill for audit workflows.
- `contract_draft_reviewer` — **Contract Draft Reviewer**: Contract Draft Reviewer: production-ready governance skill for legal ops workflows.
- `legal_review_checklist_builder` — **Legal Review Checklist Builder**: Legal Review Checklist Builder: production-ready governance skill for legal ops workflows.
- `secrets_exposure_checker` — **Secrets Exposure Checker**: Secrets Exposure Checker: production-ready Money Mode and operations skill for security workflows.
- `tenant_isolation_checker` — **Tenant Isolation Checker**: Tenant Isolation Checker: production-ready Money Mode and operations skill for multi tenant security workflows.
- `threat_intelligence_brief_writer` — **Threat Intelligence Brief Writer**: Threat Intelligence Brief Writer: production-ready operating skill for security intelligence workflows.
- `tool_policy_review_planner` — **Tool Policy Review Planner**: Tool Policy Review Planner: production-ready operating skill for governance workflows.
- `web_monitoring_planner` — **Web Monitoring Planner**: Web Monitoring Planner: production-ready operating skill for monitoring workflows.

</details>


<details>
<summary><b>Auto-generated capability skills</b> (289) — generated by <code>scripts/backfill_agent_skills.py</code> to back every agent-advertised capability</summary>

- `a_b_testing` — **a_b_testing**: Produce a complete, professional A B Testing deliverable — specific, actionable, and structured. [executable:…
- `a_b_testing_emails` — **a_b_testing_emails**: Produce a complete, professional A B Testing Emails deliverable — specific, actionable, and structured. [exec…
- `ab_testing_framework` — **ab_testing_framework**: Produce a complete, professional A/B Testing Framework deliverable — specific, actionable, and structured. [e…
- `accessibility_audit` — **accessibility_audit**: Produce a complete, professional Accessibility Audit deliverable — specific, actionable, and structured. [exe…
- `accessibility_testing` — **accessibility_testing**: Produce a complete, professional Accessibility Testing deliverable — specific, actionable, and structured. [e…
- `action_item_extraction` — **action_item_extraction**: Produce a complete, professional Action Item Extraction deliverable — specific, actionable, and structured. […
- `ad_copy_creation` — **ad_copy_creation**: Produce a complete, professional Ad Copy Creation deliverable — specific, actionable, and structured. [execut…
- `agent_skill_generation` — **agent_skill_generation**: Produce a complete, professional Agent Skill Generation deliverable — specific, actionable, and structured. […
- `ai_ml_engineering` — **ai_ml_engineering**: Produce a complete, professional AI Ml Engineering deliverable — specific, actionable, and structured. [execu…
- `ai_powered_scanning` — **ai_powered_scanning**: Produce a complete, professional AI Powered Scanning deliverable — specific, actionable, and structured. [exe…
- `amazon_research` — **amazon_research**: Produce a complete, professional Amazon Research deliverable — specific, actionable, and structured. [executa…
- `anomaly_alerting` — **anomaly_alerting**: Produce a complete, professional Anomaly Alerting deliverable — specific, actionable, and structured. [execut…
- `api_integration` — **api_integration**: Produce a complete, professional API Integration deliverable — specific, actionable, and structured. [executa…
- `api_key_verification` — **api_key_verification**: Produce a complete, professional API Key Verification deliverable — specific, actionable, and structured. [ex…
- `api_testing` — **api_testing**: Produce a complete, professional API Testing deliverable — specific, actionable, and structured. [executable:…
- `approval_workflows` — **approval_workflows**: Produce a complete, professional Approval Workflows deliverable — specific, actionable, and structured. [exec…
- `archive_creation` — **archive_creation**: Produce a complete, professional Archive Creation deliverable — specific, actionable, and structured. [execut…
- `artifact_tracking` — **artifact_tracking**: Produce a complete, professional Artifact Tracking deliverable — specific, actionable, and structured. [execu…
- `audience_strategy` — **audience_strategy**: Produce a complete, professional Audience Strategy deliverable — specific, actionable, and structured. [execu…
- `audit_logging` — **audit_logging**: Produce a complete, professional Audit Logging deliverable — specific, actionable, and structured. [executabl…
- `audit_trail` — **audit_trail**: Produce a complete, professional Audit Trail deliverable — specific, actionable, and structured. [executable:…
- `auto_reorder` — **auto_reorder**: Produce a complete, professional Auto Reorder deliverable — specific, actionable, and structured. [executable…
- `automation_planning` — **automation_planning**: Produce a complete, professional Automation Planning deliverable — specific, actionable, and structured. [exe…
- `backend_architecture` — **backend_architecture**: Produce a complete, professional Backend Architecture deliverable — specific, actionable, and structured. [ex…
- `backtesting` — **backtesting**: Produce a complete, professional Backtesting deliverable — specific, actionable, and structured. [executable:…
- `bot_lifecycle` — **bot_lifecycle**: Produce a complete, professional Bot Lifecycle deliverable — specific, actionable, and structured. [executabl…
- `brand_positioning` — **brand_positioning**: Produce a complete, professional Brand Positioning deliverable — specific, actionable, and structured. [execu…
- `brand_voice` — **brand_voice**: Produce a complete, professional Brand Voice deliverable — specific, actionable, and structured. [executable:…
- `budget_allocation` — **budget_allocation**: Produce a complete, professional Budget Allocation deliverable — specific, actionable, and structured. [execu…
- `budget_enforcement` — **budget_enforcement**: Produce a complete, professional Budget Enforcement deliverable — specific, actionable, and structured. [exec…
- `bug_reporting` — **bug_reporting**: Produce a complete, professional Bug Reporting deliverable — specific, actionable, and structured. [executabl…
- `campaign_ideation` — **campaign_ideation**: Produce a complete, professional Campaign Ideation deliverable — specific, actionable, and structured. [execu…
- `candidate_outreach` — **candidate_outreach**: Produce a complete, professional Candidate Outreach deliverable — specific, actionable, and structured. [exec…
- `changelog_generation` — **changelog_generation**: Produce a complete, professional Changelog Generation deliverable — specific, actionable, and structured. [ex…
- `chatbot_design` — **chatbot_design**: Produce a complete, professional Chatbot Design deliverable — specific, actionable, and structured. [executab…
- `code_exec` — **code_exec**: Produce a complete, professional Code Exec deliverable — specific, actionable, and structured. [executable: v…
- `code_generation` — **code_generation**: Produce a complete, professional Code Generation deliverable — specific, actionable, and structured. [executa…
- `cold_email_sequences` — **cold_email_sequences**: Produce a complete, professional Cold Email Sequences deliverable — specific, actionable, and structured. [ex…
- `cold_email_writing` — **cold_email_writing**: Produce a complete, professional Cold Email Writing deliverable — specific, actionable, and structured. [exec…
- `cold_outreach` — **cold_outreach**: Produce a complete, professional Cold Outreach deliverable — specific, actionable, and structured. [executabl…
- `color_palette_design` — **color_palette_design**: Produce a complete, professional Color Palette Design deliverable — specific, actionable, and structured. [ex…
- `command_handling` — **command_handling**: Produce a complete, professional Command Handling deliverable — specific, actionable, and structured. [execut…
- `comment_automation` — **comment_automation**: Produce a complete, professional Comment Automation deliverable — specific, actionable, and structured. [exec…
- `company_management` — **company_management**: Produce a complete, professional Company Management deliverable — specific, actionable, and structured. [exec…
- `compensation_benchmarking` — **compensation_benchmarking**: Produce a complete, professional Compensation Benchmarking deliverable — specific, actionable, and structured…
- `competitive_analysis` — **competitive_analysis**: Produce a complete, professional Competitive Analysis deliverable — specific, actionable, and structured. [ex…
- `competitive_brand_analysis` — **competitive_brand_analysis**: Produce a complete, professional Competitive Brand Analysis deliverable — specific, actionable, and structure…
- `component_specification` — **component_specification**: Produce a complete, professional Component Specification deliverable — specific, actionable, and structured. …
- `content_curation` — **content_curation**: Produce a complete, professional Content Curation deliverable — specific, actionable, and structured. [execut…
- `content_generation` — **content_generation**: Produce a complete, professional Content Generation deliverable — specific, actionable, and structured. [exec…
- `content_optimization` — **content_optimization**: Produce a complete, professional Content Optimization deliverable — specific, actionable, and structured. [ex…
- `content_planning` — **content_planning**: Produce a complete, professional Content Planning deliverable — specific, actionable, and structured. [execut…
- `content_strategy` — **content_strategy**: Produce a complete, professional Content Strategy deliverable — specific, actionable, and structured. [execut…
- `context_checkpointing` — **context_checkpointing**: Produce a complete, professional Context Checkpointing deliverable — specific, actionable, and structured. [e…
- `context_injection` — **context_injection**: Produce a complete, professional Context Injection deliverable — specific, actionable, and structured. [execu…
- `contract_drafting` — **contract_drafting**: Produce a complete, professional Contract Drafting deliverable — specific, actionable, and structured. [execu…
- `conversation_flows` — **conversation_flows**: Produce a complete, professional Conversation Flows deliverable — specific, actionable, and structured. [exec…
- `conversion_optimization` — **conversion_optimization**: Produce a complete, professional Conversion Optimization deliverable — specific, actionable, and structured. …
- `conversion_tracking` — **conversion_tracking**: Produce a complete, professional Conversion Tracking deliverable — specific, actionable, and structured. [exe…
- `copywriting_expert` — **copywriting_expert**: Produce a complete, professional Copywriting Expert deliverable — specific, actionable, and structured. [exec…
- `cost_optimization` — **cost_optimization**: Produce a complete, professional Cost Optimization deliverable — specific, actionable, and structured. [execu…
- `cost_tracking` — **cost_tracking**: Produce a complete, professional Cost Tracking deliverable — specific, actionable, and structured. [executabl…
- `course_outline` — **course_outline**: Produce a complete, professional Course Outline deliverable — specific, actionable, and structured. [executab…
- `coverage_analysis` — **coverage_analysis**: Produce a complete, professional Coverage Analysis deliverable — specific, actionable, and structured. [execu…
- `creative_briefs` — **creative_briefs**: Produce a complete, professional Creative Briefs deliverable — specific, actionable, and structured. [executa…
- `crm_management` — **crm_management**: Produce a complete, professional CRM Management deliverable — specific, actionable, and structured. [executab…
- `crm_outcome_monitoring` — **crm_outcome_monitoring**: Produce a complete, professional CRM Outcome Monitoring deliverable — specific, actionable, and structured. […
- `cron_management` — **cron_management**: Produce a complete, professional Cron Management deliverable — specific, actionable, and structured. [executa…
- `crypto_community_building` — **crypto_community_building**: Produce a complete, professional Crypto Community Building deliverable — specific, actionable, and structured…
- `csv_generation` — **csv_generation**: Produce a complete, professional Csv Generation deliverable — specific, actionable, and structured. [executab…
- `culture_design` — **culture_design**: Produce a complete, professional Culture Design deliverable — specific, actionable, and structured. [executab…
- `custom_agent_builder` — **custom_agent_builder**: Produce a complete, professional Custom Agent Builder deliverable — specific, actionable, and structured. [ex…
- `customer_notification` — **customer_notification**: Produce a complete, professional Customer Notification deliverable — specific, actionable, and structured. [e…
- `customer_research` — **customer_research**: Produce a complete, professional Customer Research deliverable — specific, actionable, and structured. [execu…
- `customer_segmentation` — **customer_segmentation**: Produce a complete, professional Customer Segmentation deliverable — specific, actionable, and structured. [e…
- `customer_service` — **customer_service**: Produce a complete, professional Customer Service deliverable — specific, actionable, and structured. [execut…
- `cv_screening` — **cv_screening**: Produce a complete, professional Cv Screening deliverable — specific, actionable, and structured. [executable…
- `daily_profit_alerts` — **daily_profit_alerts**: Produce a complete, professional Daily Profit Alerts deliverable — specific, actionable, and structured. [exe…
- `daily_reports` — **daily_reports**: Produce a complete, professional Daily Reports deliverable — specific, actionable, and structured. [executabl…
- `dark_mode_design` — **dark_mode_design**: Produce a complete, professional Dark Mode Design deliverable — specific, actionable, and structured. [execut…
- `data_analysis` — **data_analysis**: Produce a complete, professional Data Analysis deliverable — specific, actionable, and structured. [executabl…
- `data_export` — **data_export**: Produce a complete, professional Data Export deliverable — specific, actionable, and structured. [executable:…
- `data_extraction` — **data_extraction**: Produce a complete, professional Data Extraction deliverable — specific, actionable, and structured. [executa…
- `database_design` — **database_design**: Produce a complete, professional Database Design deliverable — specific, actionable, and structured. [executa…
- `deal_matching` — **deal_matching**: Produce a complete, professional Deal Matching deliverable — specific, actionable, and structured. [executabl…
- `debugging` — **debugging**: Produce a complete, professional Debugging deliverable — specific, actionable, and structured. [executable: v…
- `defensive_osint` — **defensive_osint**: Produce a complete, professional Defensive Osint deliverable — specific, actionable, and structured. [executa…
- `deliverability_optimization` — **deliverability_optimization**: Produce a complete, professional Deliverability Optimization deliverable — specific, actionable, and structur…
- `demand_forecasting` — **demand_forecasting**: Produce a complete, professional Demand Forecasting deliverable — specific, actionable, and structured. [exec…
- `demand_validation` — **demand_validation**: Produce a complete, professional Demand Validation deliverable — specific, actionable, and structured. [execu…
- `deployment_tracking` — **deployment_tracking**: Produce a complete, professional Deployment Tracking deliverable — specific, actionable, and structured. [exe…
- `design_system_creation` — **design_system_creation**: Produce a complete, professional Design System Creation deliverable — specific, actionable, and structured. […
- `developer_handoff` — **developer_handoff**: Produce a complete, professional Developer Handoff deliverable — specific, actionable, and structured. [execu…
- `devops_infrastructure` — **devops_infrastructure**: Produce a complete, professional Devops Infrastructure deliverable — specific, actionable, and structured. [e…
- `diagnostic_reporting` — **diagnostic_reporting**: Produce a complete, professional Diagnostic Reporting deliverable — specific, actionable, and structured. [ex…
- `discord_integration` — **discord_integration**: Produce a complete, professional Discord Integration deliverable — specific, actionable, and structured. [exe…
- `discord_notifications` — **discord_notifications**: Produce a complete, professional Discord Notifications deliverable — specific, actionable, and structured. [e…
- `discord_whatsapp_notifications` — **discord_whatsapp_notifications**: Produce a complete, professional Discord Whatsapp Notifications deliverable — specific, actionable, and struc…
- `dns_verification` — **dns_verification**: Produce a complete, professional Dns Verification deliverable — specific, actionable, and structured. [execut…
- `document_generation` — **document_generation**: Produce a complete, professional Document Generation deliverable — specific, actionable, and structured. [exe…
- `documentation` — **documentation**: Produce a complete, professional Documentation deliverable — specific, actionable, and structured. [executabl…
- `drip_sequences` — **drip_sequences**: Produce a complete, professional Drip Sequences deliverable — specific, actionable, and structured. [executab…
- `earnings_quality` — **earnings_quality**: Produce a complete, professional Earnings Quality deliverable — specific, actionable, and structured. [execut…
- `email_campaigns` — **email_campaigns**: Produce a complete, professional Email Campaigns deliverable — specific, actionable, and structured. [executa…
- `email_composition` — **email_composition**: Produce a complete, professional Email Composition deliverable — specific, actionable, and structured. [execu…
- `email_deliverability` — **email_deliverability**: Produce a complete, professional Email Deliverability deliverable — specific, actionable, and structured. [ex…
- `email_personalization` — **email_personalization**: Produce a complete, professional Email Personalization deliverable — specific, actionable, and structured. [e…
- `email_sequence` — **email_sequence**: Produce a complete, professional Email Sequence deliverable — specific, actionable, and structured. [executab…
- `engagement_tracking` — **engagement_tracking**: Produce a complete, professional Engagement Tracking deliverable — specific, actionable, and structured. [exe…
- `executive_summary` — **executive_summary**: Produce a complete, professional Executive Summary deliverable — specific, actionable, and structured. [execu…
- `expense_categorisation` — **expense_categorisation**: Produce a complete, professional Expense Categorisation deliverable — specific, actionable, and structured. […
- `fact_verification` — **fact_verification**: Produce a complete, professional Fact Verification deliverable — specific, actionable, and structured. [execu…
- `faq_handling` — **faq_handling**: Produce a complete, professional Faq Handling deliverable — specific, actionable, and structured. [executable…
- `file_ops` — **file_ops**: Produce a complete, professional File Ops deliverable — specific, actionable, and structured. [executable: va…
- `financial_analysis` — **financial_analysis**: Produce a complete, professional Financial Analysis deliverable — specific, actionable, and structured. [exec…
- `financial_reporting` — **financial_reporting**: Produce a complete, professional Financial Reporting deliverable — specific, actionable, and structured. [exe…
- `follow_up_automation` — **follow_up_automation**: Produce a complete, professional Follow Up Automation deliverable — specific, actionable, and structured. [ex…
- `follow_up_generation` — **follow_up_generation**: Produce a complete, professional Follow Up Generation deliverable — specific, actionable, and structured. [ex…
- `follow_up_sequencing` — **follow_up_sequencing**: Produce a complete, professional Follow Up Sequencing deliverable — specific, actionable, and structured. [ex…
- `frontend_development` — **frontend_development**: Produce a complete, professional Frontend Development deliverable — specific, actionable, and structured. [ex…
- `fundraising_prep` — **fundraising_prep**: Produce a complete, professional Fundraising Prep deliverable — specific, actionable, and structured. [execut…
- `funnel_optimization` — **funnel_optimization**: Produce a complete, professional Funnel Optimization deliverable — specific, actionable, and structured. [exe…
- `gantt_planning` — **gantt_planning**: Produce a complete, professional Gantt Planning deliverable — specific, actionable, and structured. [executab…
- `goal_decomposition` — **goal_decomposition**: Produce a complete, professional Goal Decomposition deliverable — specific, actionable, and structured. [exec…
- `goal_management` — **goal_management**: Produce a complete, professional Goal Management deliverable — specific, actionable, and structured. [executa…
- `google_ads_strategy` — **google_ads_strategy**: Produce a complete, professional Google Ads Strategy deliverable — specific, actionable, and structured. [exe…
- `growth_okrs` — **growth_okrs**: Produce a complete, professional Growth Okrs deliverable — specific, actionable, and structured. [executable:…
- `hierarchy_modeling` — **hierarchy_modeling**: Produce a complete, professional Hierarchy Modeling deliverable — specific, actionable, and structured. [exec…
- `icp_matching` — **icp_matching**: Produce a complete, professional Icp Matching deliverable — specific, actionable, and structured. [executable…
- `icp_scoring` — **icp_scoring**: Produce a complete, professional Icp Scoring deliverable — specific, actionable, and structured. [executable:…
- `image_prompt_creation` — **image_prompt_creation**: Produce a complete, professional Image Prompt Creation deliverable — specific, actionable, and structured. [e…
- `image_prompt_generation` — **image_prompt_generation**: Produce a complete, professional Image Prompt Generation deliverable — specific, actionable, and structured. …
- `image_prompts` — **image_prompts**: Produce a complete, professional Image Prompts deliverable — specific, actionable, and structured. [executabl…
- `improvement_proposals` — **improvement_proposals**: Produce a complete, professional Improvement Proposals deliverable — specific, actionable, and structured. [e…
- `integration_mapping` — **integration_mapping**: Produce a complete, professional Integration Mapping deliverable — specific, actionable, and structured. [exe…
- `interview_frameworks` — **interview_frameworks**: Produce a complete, professional Interview Frameworks deliverable — specific, actionable, and structured. [ex…
- `investor_relations` — **investor_relations**: Produce a complete, professional Investor Relations deliverable — specific, actionable, and structured. [exec…
- `invoice_generation` — **invoice_generation**: Produce a complete, professional Invoice Generation deliverable — specific, actionable, and structured. [exec…
- `invoicing` — **invoicing**: Produce a complete, professional Invoicing deliverable — specific, actionable, and structured. [executable: v…
- `job_description_writing` — **job_description_writing**: Produce a complete, professional Job Description Writing deliverable — specific, actionable, and structured. …
- `keyword_search` — **keyword_search**: Produce a complete, professional Keyword Search deliverable — specific, actionable, and structured. [executab…
- `kpi_tracking` — **kpi_tracking**: Produce a complete, professional KPI Tracking deliverable — specific, actionable, and structured. [executable…
- `lead_enrichment` — **lead_enrichment**: Produce a complete, professional Lead Enrichment deliverable — specific, actionable, and structured. [executa…
- `lead_generation` — **lead_generation**: Produce a complete, professional Lead Generation deliverable — specific, actionable, and structured. [executa…
- `lead_hunting` — **lead_hunting**: Produce a complete, professional Lead Hunting deliverable — specific, actionable, and structured. [executable…
- `legal_review` — **legal_review**: Produce a complete, professional Legal Review deliverable — specific, actionable, and structured. [executable…
- `listing_automation` — **listing_automation**: Produce a complete, professional Listing Automation deliverable — specific, actionable, and structured. [exec…
- `listing_creation` — **listing_creation**: Produce a complete, professional Listing Creation deliverable — specific, actionable, and structured. [execut…
- `long_term_memory` — **long_term_memory**: Produce a complete, professional Long Term Memory deliverable — specific, actionable, and structured. [execut…
- `low_stock_alerts` — **low_stock_alerts**: Produce a complete, professional Low Stock Alerts deliverable — specific, actionable, and structured. [execut…
- `mailchimp_integration` — **mailchimp_integration**: Produce a complete, professional Mailchimp Integration deliverable — specific, actionable, and structured. [e…
- `market_monitoring` — **market_monitoring**: Produce a complete, professional Market Monitoring deliverable — specific, actionable, and structured. [execu…
- `market_trend_analysis` — **market_trend_analysis**: Produce a complete, professional Market Trend Analysis deliverable — specific, actionable, and structured. [e…
- `marketplace_analysis` — **marketplace_analysis**: Produce a complete, professional Marketplace Analysis deliverable — specific, actionable, and structured. [ex…
- `meeting_booking` — **meeting_booking**: Produce a complete, professional Meeting Booking deliverable — specific, actionable, and structured. [executa…
- `meeting_summarization` — **meeting_summarization**: Produce a complete, professional Meeting Summarization deliverable — specific, actionable, and structured. [e…
- `memory_retrieval` — **memory_retrieval**: Produce a complete, professional Memory Retrieval deliverable — specific, actionable, and structured. [execut…
- `memory_writeback` — **memory_writeback**: Produce a complete, professional Memory Writeback deliverable — specific, actionable, and structured. [execut…
- `milestone_planning` — **milestone_planning**: Produce a complete, professional Milestone Planning deliverable — specific, actionable, and structured. [exec…
- `mission_tracking` — **mission_tracking**: Produce a complete, professional Mission Tracking deliverable — specific, actionable, and structured. [execut…
- `model_budget_planning` — **model_budget_planning**: Produce a complete, professional Model Budget Planning deliverable — specific, actionable, and structured. [e…
- `multi_agent_synthesis` — **multi_agent_synthesis**: Produce a complete, professional Multi Agent Synthesis deliverable — specific, actionable, and structured. [e…
- `multi_platform_posting` — **multi_platform_posting**: Produce a complete, professional Multi Platform Posting deliverable — specific, actionable, and structured. […
- `multi_stage_reasoning` — **multi_stage_reasoning**: Produce a complete, professional Multi Stage Reasoning deliverable — specific, actionable, and structured. [e…
- `niche_targeting` — **niche_targeting**: Produce a complete, professional Niche Targeting deliverable — specific, actionable, and structured. [executa…
- `note_creation` — **note_creation**: Produce a complete, professional Note Creation deliverable — specific, actionable, and structured. [executabl…
- `offer_crafting` — **offer_crafting**: Produce a complete, professional Offer Crafting deliverable — specific, actionable, and structured. [executab…
- `onboarding_design` — **onboarding_design**: Produce a complete, professional Onboarding Design deliverable — specific, actionable, and structured. [execu…
- `open_rate_optimisation` — **open_rate_optimisation**: Produce a complete, professional Open Rate Optimisation deliverable — specific, actionable, and structured. […
- `opportunity_alerts` — **opportunity_alerts**: Produce a complete, professional Opportunity Alerts deliverable — specific, actionable, and structured. [exec…
- `order_processing` — **order_processing**: Produce a complete, professional Order Processing deliverable — specific, actionable, and structured. [execut…
- `order_tracking` — **order_tracking**: Produce a complete, professional Order Tracking deliverable — specific, actionable, and structured. [executab…
- `output_management` — **output_management**: Produce a complete, professional Output Management deliverable — specific, actionable, and structured. [execu…
- `outreach_sequences` — **outreach_sequences**: Produce a complete, professional Outreach Sequences deliverable — specific, actionable, and structured. [exec…
- `patch_management` — **patch_management**: Produce a complete, professional Patch Management deliverable — specific, actionable, and structured. [execut…
- `payment_reminders` — **payment_reminders**: Produce a complete, professional Payment Reminders deliverable — specific, actionable, and structured. [execu…
- `payment_tracking` — **payment_tracking**: Produce a complete, professional Payment Tracking deliverable — specific, actionable, and structured. [execut…
- `payment_validation` — **payment_validation**: Produce a complete, professional Payment Validation deliverable — specific, actionable, and structured. [exec…
- `performance_reviews` — **performance_reviews**: Produce a complete, professional Performance Reviews deliverable — specific, actionable, and structured. [exe…
- `performance_testing` — **performance_testing**: Produce a complete, professional Performance Testing deliverable — specific, actionable, and structured. [exe…
- `pipeline_management` — **pipeline_management**: Produce a complete, professional Pipeline Management deliverable — specific, actionable, and structured. [exe…
- `pitch_writing` — **pitch_writing**: Produce a complete, professional Pitch Writing deliverable — specific, actionable, and structured. [executabl…
- `pl_generation` — **pl_generation**: Produce a complete, professional P&L Generation deliverable — specific, actionable, and structured. [executab…
- `pl_projections` — **pl_projections**: Produce a complete, professional P&L Projections deliverable — specific, actionable, and structured. [executa…
- `pnl` — **pnl**: Produce a complete, professional Pnl deliverable — specific, actionable, and structured. [executable: validat…
- `portfolio_optimization` — **portfolio_optimization**: Produce a complete, professional Portfolio Optimization deliverable — specific, actionable, and structured. […
- `portfolio_tracking` — **portfolio_tracking**: Produce a complete, professional Portfolio Tracking deliverable — specific, actionable, and structured. [exec…
- `price_comparison` — **price_comparison**: Produce a complete, professional Price Comparison deliverable — specific, actionable, and structured. [execut…
- `price_monitoring` — **price_monitoring**: Produce a complete, professional Price Monitoring deliverable — specific, actionable, and structured. [execut…
- `product_design` — **product_design**: Produce a complete, professional Product Design deliverable — specific, actionable, and structured. [executab…
- `progress_tracking` — **progress_tracking**: Produce a complete, professional Progress Tracking deliverable — specific, actionable, and structured. [execu…
- `prompt_optimization` — **prompt_optimization**: Produce a complete, professional Prompt Optimization deliverable — specific, actionable, and structured. [exe…
- `prompt_scanning` — **prompt_scanning**: Produce a complete, professional Prompt Scanning deliverable — specific, actionable, and structured. [executa…
- `prospect_discovery` — **prospect_discovery**: Produce a complete, professional Prospect Discovery deliverable — specific, actionable, and structured. [exec…
- `provider_fallback` — **provider_fallback**: Produce a complete, professional Provider Fallback deliverable — specific, actionable, and structured. [execu…
- `python_development` — **python_development**: Produce a complete, professional Python Development deliverable — specific, actionable, and structured. [exec…
- `qualification_frameworks` — **qualification_frameworks**: Produce a complete, professional Qualification Frameworks deliverable — specific, actionable, and structured.…
- `quoting` — **quoting**: Produce a complete, professional Quoting deliverable — specific, actionable, and structured. [executable: val…
- `raci_matrix` — **raci_matrix**: Produce a complete, professional Raci Matrix deliverable — specific, actionable, and structured. [executable:…
- `readiness_certification` — **readiness_certification**: Produce a complete, professional Readiness Certification deliverable — specific, actionable, and structured. …
- `refactoring` — **refactoring**: Produce a complete, professional Refactoring deliverable — specific, actionable, and structured. [executable:…
- `refund_processing` — **refund_processing**: Produce a complete, professional Refund Processing deliverable — specific, actionable, and structured. [execu…
- `reporting_lines` — **reporting_lines**: Produce a complete, professional Reporting Lines deliverable — specific, actionable, and structured. [executa…
- `research_synthesis` — **research_synthesis**: Produce a complete, professional Research Synthesis deliverable — specific, actionable, and structured. [exec…
- `responsive_layout` — **responsive_layout**: Produce a complete, professional Responsive Layout deliverable — specific, actionable, and structured. [execu…
- `result_synthesis` — **result_synthesis**: Produce a complete, professional Result Synthesis deliverable — specific, actionable, and structured. [execut…
- `result_validation` — **result_validation**: Produce a complete, professional Result Validation deliverable — specific, actionable, and structured. [execu…
- `retrospective_facilitation` — **retrospective_facilitation**: Produce a complete, professional Retrospective Facilitation deliverable — specific, actionable, and structure…
- `revenue_tracking` — **revenue_tracking**: Produce a complete, professional Revenue Tracking deliverable — specific, actionable, and structured. [execut…
- `risk_scoring` — **risk_scoring**: Produce a complete, professional Risk Scoring deliverable — specific, actionable, and structured. [executable…
- `roi_calculation` — **roi_calculation**: Produce a complete, professional ROI Calculation deliverable — specific, actionable, and structured. [executa…
- `role_mapping` — **role_mapping**: Produce a complete, professional Role Mapping deliverable — specific, actionable, and structured. [executable…
- `sales_copy` — **sales_copy**: Produce a complete, professional Sales Copy deliverable — specific, actionable, and structured. [executable: …
- `sales_forecasting` — **sales_forecasting**: Produce a complete, professional Sales Forecasting deliverable — specific, actionable, and structured. [execu…
- `script_writing` — **script_writing**: Produce a complete, professional Script Writing deliverable — specific, actionable, and structured. [executab…
- `sec_filing_analysis` — **sec_filing_analysis**: Produce a complete, professional Sec Filing Analysis deliverable — specific, actionable, and structured. [exe…
- `secure_local_builds` — **secure_local_builds**: Produce a complete, professional Secure Local Builds deliverable — specific, actionable, and structured. [exe…
- `security_audit` — **security_audit**: Produce a complete, professional Security Audit deliverable — specific, actionable, and structured. [executab…
- `security_posture_analysis` — **security_posture_analysis**: Produce a complete, professional Security Posture Analysis deliverable — specific, actionable, and structured…
- `security_review` — **security_review**: Produce a complete, professional Security Review deliverable — specific, actionable, and structured. [executa…
- `security_testing` — **security_testing**: Produce a complete, professional Security Testing deliverable — specific, actionable, and structured. [execut…
- `seo_audit` — **seo_audit**: Produce a complete, professional SEO Audit deliverable — specific, actionable, and structured. [executable: v…
- `service_validation` — **service_validation**: Produce a complete, professional Service Validation deliverable — specific, actionable, and structured. [exec…
- `shell_exec` — **shell_exec**: Produce a complete, professional Shell Exec deliverable — specific, actionable, and structured. [executable: …
- `shopify_inventory_update` — **shopify_inventory_update**: Produce a complete, professional Shopify Inventory Update deliverable — specific, actionable, and structured.…
- `shopify_product_publish` — **shopify_product_publish**: Produce a complete, professional Shopify Product Publish deliverable — specific, actionable, and structured. …
- `shopify_webhook` — **shopify_webhook**: Produce a complete, professional Shopify Webhook deliverable — specific, actionable, and structured. [executa…
- `signal_aggregation` — **signal_aggregation**: Produce a complete, professional Signal Aggregation deliverable — specific, actionable, and structured. [exec…
- `signal_generation` — **signal_generation**: Produce a complete, professional Signal Generation deliverable — specific, actionable, and structured. [execu…
- `skill_gap_analysis` — **skill_gap_analysis**: Produce a complete, professional Skill Gap Analysis deliverable — specific, actionable, and structured. [exec…
- `skill_library` — **skill_library**: Produce a complete, professional Skill Library deliverable — specific, actionable, and structured. [executabl…
- `source_attribution` — **source_attribution**: Produce a complete, professional Source Attribution deliverable — specific, actionable, and structured. [exec…
- `source_synthesis` — **source_synthesis**: Produce a complete, professional Source Synthesis deliverable — specific, actionable, and structured. [execut…
- `spam_analysis` — **spam_analysis**: Produce a complete, professional Spam Analysis deliverable — specific, actionable, and structured. [executabl…
- `stakeholder_management` — **stakeholder_management**: Produce a complete, professional Stakeholder Management deliverable — specific, actionable, and structured. […
- `standup_reports` — **standup_reports**: Produce a complete, professional Standup Reports deliverable — specific, actionable, and structured. [executa…
- `state_aggregation` — **state_aggregation**: Produce a complete, professional State Aggregation deliverable — specific, actionable, and structured. [execu…
- `status_updates` — **status_updates**: Produce a complete, professional Status Updates deliverable — specific, actionable, and structured. [executab…
- `stock_monitoring` — **stock_monitoring**: Produce a complete, professional Stock Monitoring deliverable — specific, actionable, and structured. [execut…
- `stripe_data_pull` — **stripe_data_pull**: Produce a complete, professional Stripe Data Pull deliverable — specific, actionable, and structured. [execut…
- `structured_output` — **structured_output**: Produce a complete, professional Structured Output deliverable — specific, actionable, and structured. [execu…
- `supplier_api_integration` — **supplier_api_integration**: Produce a complete, professional Supplier API Integration deliverable — specific, actionable, and structured.…
- `supplier_vetting` — **supplier_vetting**: Produce a complete, professional Supplier Vetting deliverable — specific, actionable, and structured. [execut…
- `synthesis` — **synthesis**: Produce a complete, professional Synthesis deliverable — specific, actionable, and structured. [executable: v…
- `system_architecture` — **system_architecture**: Produce a complete, professional System Architecture deliverable — specific, actionable, and structured. [exe…
- `system_health_monitoring` — **system_health_monitoring**: Produce a complete, professional System Health Monitoring deliverable — specific, actionable, and structured.…
- `system_health_reporting` — **system_health_reporting**: Produce a complete, professional System Health Reporting deliverable — specific, actionable, and structured. …
- `task_assignment` — **task_assignment**: Produce a complete, professional Task Assignment deliverable — specific, actionable, and structured. [executa…
- `task_decomposition` — **task_decomposition**: Produce a complete, professional Task Decomposition deliverable — specific, actionable, and structured. [exec…
- `task_planning` — **task_planning**: Produce a complete, professional Task Planning deliverable — specific, actionable, and structured. [executabl…
- `task_resumption` — **task_resumption**: Produce a complete, professional Task Resumption deliverable — specific, actionable, and structured. [executa…
- `tax_calculation` — **tax_calculation**: Produce a complete, professional Tax Calculation deliverable — specific, actionable, and structured. [executa…
- `tax_preparation` — **tax_preparation**: Produce a complete, professional Tax Preparation deliverable — specific, actionable, and structured. [executa…
- `team_coordination` — **team_coordination**: Produce a complete, professional Team Coordination deliverable — specific, actionable, and structured. [execu…
- `technical_seo` — **technical_seo**: Produce a complete, professional Technical SEO deliverable — specific, actionable, and structured. [executabl…
- `template_management` — **template_management**: Produce a complete, professional Template Management deliverable — specific, actionable, and structured. [exe…
- `template_scoring` — **template_scoring**: Produce a complete, professional Template Scoring deliverable — specific, actionable, and structured. [execut…
- `test_automation_strategy` — **test_automation_strategy**: Produce a complete, professional Test Automation Strategy deliverable — specific, actionable, and structured.…
- `test_plan_creation` — **test_plan_creation**: Produce a complete, professional Test Plan Creation deliverable — specific, actionable, and structured. [exec…
- `threat_intelligence` — **threat_intelligence**: Produce a complete, professional Threat Intelligence deliverable — specific, actionable, and structured. [exe…
- `ticket_classification` — **ticket_classification**: Produce a complete, professional Ticket Classification deliverable — specific, actionable, and structured. [e…
- `ticket_tracking` — **ticket_tracking**: Produce a complete, professional Ticket Tracking deliverable — specific, actionable, and structured. [executa…
- `token_budget_planning` — **token_budget_planning**: Produce a complete, professional Token Budget Planning deliverable — specific, actionable, and structured. [e…
- `tool_policy_gating` — **tool_policy_gating**: Produce a complete, professional Tool Policy Gating deliverable — specific, actionable, and structured. [exec…
- `top_product_ranking` — **top_product_ranking**: Produce a complete, professional Top Product Ranking deliverable — specific, actionable, and structured. [exe…
- `topic_research` — **topic_research**: Produce a complete, professional Topic Research deliverable — specific, actionable, and structured. [executab…
- `tracking_updates` — **tracking_updates**: Produce a complete, professional Tracking Updates deliverable — specific, actionable, and structured. [execut…
- `transcript_analysis` — **transcript_analysis**: Produce a complete, professional Transcript Analysis deliverable — specific, actionable, and structured. [exe…
- `trend_detection` — **trend_detection**: Produce a complete, professional Trend Detection deliverable — specific, actionable, and structured. [executa…
- `trend_spotting` — **trend_spotting**: Produce a complete, professional Trend Spotting deliverable — specific, actionable, and structured. [executab…
- `twilio_integration` — **twilio_integration**: Produce a complete, professional Twilio Integration deliverable — specific, actionable, and structured. [exec…
- `ui_audit` — **ui_audit**: Produce a complete, professional UI Audit deliverable — specific, actionable, and structured. [executable: va…
- `unit_economics` — **unit_economics**: Produce a complete, professional Unit Economics deliverable — specific, actionable, and structured. [executab…
- `usage_analytics` — **usage_analytics**: Produce a complete, professional Usage Analytics deliverable — specific, actionable, and structured. [executa…
- `valuation_methodology` — **valuation_methodology**: Produce a complete, professional Valuation Methodology deliverable — specific, actionable, and structured. [e…
- `video_scripts` — **video_scripts**: Produce a complete, professional Video Scripts deliverable — specific, actionable, and structured. [executabl…
- `visual_prompts` — **visual_prompts**: Produce a complete, professional Visual Prompts deliverable — specific, actionable, and structured. [executab…
- `voiceover_generation` — **voiceover_generation**: Produce a complete, professional Voiceover Generation deliverable — specific, actionable, and structured. [ex…
- `web_fetch` — **web_fetch**: Produce a complete, professional Web Fetch deliverable — specific, actionable, and structured. [executable: v…
- `web_monitoring` — **web_monitoring**: Produce a complete, professional Web Monitoring deliverable — specific, actionable, and structured. [executab…
- `web_scraping` — **web_scraping**: Produce a complete, professional Web Scraping deliverable — specific, actionable, and structured. [executable…
- `web_search` — **web_search**: Produce a complete, professional Web Search deliverable — specific, actionable, and structured. [executable: …
- `whatsapp_inbound` — **whatsapp_inbound**: Produce a complete, professional Whatsapp Inbound deliverable — specific, actionable, and structured. [execut…
- `work_breakdown_structure` — **work_breakdown_structure**: Produce a complete, professional Work Breakdown Structure deliverable — specific, actionable, and structured.…
- `workflow_design` — **workflow_design**: Produce a complete, professional Workflow Design deliverable — specific, actionable, and structured. [executa…
- `workflow_generation` — **workflow_generation**: Produce a complete, professional Workflow Generation deliverable — specific, actionable, and structured. [exe…
- `workflow_management` — **workflow_management**: Produce a complete, professional Workflow Management deliverable — specific, actionable, and structured. [exe…
- `workflow_planning` — **workflow_planning**: Produce a complete, professional Workflow Planning deliverable — specific, actionable, and structured. [execu…
- `workload_tracking` — **workload_tracking**: Produce a complete, professional Workload Tracking deliverable — specific, actionable, and structured. [execu…

</details>

---

## Complete agent catalog

113 specialist agents across 27 categories, each a `runtime/agents/<name>/` directory
registered in [runtime/config/agent_capabilities.json](runtime/config/agent_capabilities.json).
Expand a category to see every agent and what it does.

<details>
<summary><b>Sales</b> (18)</summary>

- `appointment-setter` — **appointment-setter**: Appointment Setter — sales funnel orchestrator: prospect discovery, 5-touch outreach campaigns, pipeline tracking (pros…
- `cold-outreach-assassin` — **cold-outreach-assassin**: ColdOutreachAssassin — builds and executes multi-channel cold sequences (email, LinkedIn, WhatsApp) with A/B testing an…
- `crm-pipeline` — **crm-pipeline**: CRM Pipeline — deal pipeline manager: tracks deals through stages, flags stale deals, sends follow-up reminders, calcul…
- `email-marketer` — **email-marketer**: Email Marketing Agent — segments customers (new/abandoned-cart/repeat), generates personalised GPT-powered email copy, …
- `email-marketing` — **email-marketing**: Email Marketing — full email marketing automation: campaign planning, list segmentation, A/B test design, drip sequence…
- `email-ninja` — **email-ninja**: Cold Email Specialist — builds sequences, personalizes at scale, optimizes deliverability
- `email-warmup` — **email-warmup**: Email Warmup — email deliverability advisor: checks SPF/DKIM/DMARC configuration, estimates spam scores, generates warm…
- `follow-up-agent` — **follow-up-agent**: Follow-up Agent — sends 2–5 personalised follow-ups and adapts tone based on engagement
- `lead-crm` — **lead-crm**: Lead CRM — full sales pipeline management: deal stages (new→qualified→proposal→negotiation→closed), AI lead scoring 0–1…
- `lead-generator` — **lead-generator**: Lead Generator Bot — finds local business and real estate leads via web search, generates personalised cold emails usin…
- `lead-hunter` — **lead-hunter**: B2B Lead Generation Specialist — finds decision makers, emails, and qualifies leads
- `lead-hunter-elite` — **lead-hunter-elite**: Lead Hunter Elite — advanced B2B lead hunting with ICP definition, LinkedIn/web scraping simulation, email pattern gues…
- `lead-intelligence` — **lead-intelligence**: Lead Intelligence Pipeline — 4-agent system: lead-hunter (discover) → lead-scorer (rank by ICP) → deal-matcher (deal fi…
- `offer-agent` — **offer-agent**: Offer Agent — crafts a personalised pitch and offer per niche
- `partnership-matchmaker` — **partnership-matchmaker**: PartnershipMatchmaker — finds and pitches JV/partnership opportunities with partner scoring, pitch deck generation, and…
- `qualification-agent` — **qualification-agent**: Lead Qualification Agent — scores leads 0–10 on Budget/Interest/Need dimensions, flags unqualified leads, and focuses s…
- `sales-closer-pro` — **sales-closer-pro**: SalesCloserPro — handles negotiations, objection handling and deal closing via chat/email/call scripts using SPIN, Chal…
- `web-sales` — **web-sales**: Web Analysis & Sales Specialist — UX/SEO audits, find contacts, write personalized pitches

</details>

<details>
<summary><b>Operations</b> (11)</summary>

- `artifacts` — **artifacts**: Artifacts — track, version, and manage agent outputs (code, reports, campaigns, demos) as deployable artifacts.
- `budget-tracker` — **budget-tracker**: Budget Tracker — per-agent monthly cost tracking with token usage monitoring, configurable budget caps (USD), 80% warni…
- `company-manager` — **company-manager**: Company Manager — manages company information, team structure, operational workflows, and business processes for multi-…
- `contract-drafter` — **contract-drafter**: Contract Drafter — generates professional legal documents: NDAs, SOWs, SLAs, freelance contracts, partnership agreement…
- `export-backup` — **export-backup**: Export & Backup — exports system state as CSV/JSON: leads, tasks, revenue, activity logs; creates dated backup archives…
- `goal-alignment` — **goal-alignment**: Goal Alignment — hierarchical goal context injector: Company Mission → Project Goals → Task Context. Ensures every agen…
- `governance` — **governance**: Governance — board-level approval gates for high-impact agent actions. Risk levels: LOW (auto-approved), MEDIUM, HIGH, …
- `health-check` — **health-check**: Health Check — system health monitor: checks all services, verifies state file integrity, validates API keys, measures …
- `meeting-intelligence` — **meeting-intelligence**: Meeting Intelligence — meeting management and AI summarization: records transcripts, extracts key points/decisions/acti…
- `org-chart` — **org-chart**: Org Chart — agent hierarchy and reporting-structure management
- `workflow-builder` — **workflow-builder**: Workflow Builder — designs automation workflows: trigger→condition→action chains, saves as reusable JSON recipes, suppo…

</details>

<details>
<summary><b>Research</b> (8)</summary>

- `competitor-watch` — **competitor-watch**: Competitor Watch — competitive intelligence monitoring: competitor records, AI-powered analysis and positioning, alert …
- `data-scraper` — **data-scraper**: Data Scraper — scrapes public web data via DuckDuckGo/Tavily: LinkedIn-style profiles, G2 reviews, news articles, produ…
- `discovery` — **discovery**: Discovery Bot — scans skill gaps and market opportunities, proposes new skills or workflows using AI-powered analysis; …
- `financial-deepsearch` — **financial-deepsearch**: Financial DeepSearch — combines Yahoo Finance, SEC EDGAR, and DuckDuckGo for deep company research, earnings analysis, …
- `intel-agent` — **intel-agent**: Competitive Intelligence Analyst — monitors competitors: pricing, features, reviews, traffic
- `mirofish-researcher` — **mirofish-researcher**: MiroFish Researcher — standalone market-research agent (crowd-intelligence informed)
- `react_researcher` — **react_researcher**: ReAct Researcher Agent — searches, fetches, and synthesises information via iterative tool use
- `web-researcher` — **web-researcher**: Web Researcher — autonomous web research via DuckDuckGo/Wikipedia/Tavily/SerpAPI with source citations and cross-bot IP…

</details>

<details>
<summary><b>Marketing</b> (8)</summary>

- `ad-campaign-wizard` — **ad-campaign-wizard**: AdCampaignWizard — designs, launches and optimizes paid ads (Meta/Google/LinkedIn) with ROAS prediction, creative brief…
- `ad-copy-tester` — **ad-copy-tester**: Ad Copy Tester — generates 3–5 variants per angle for Facebook/Google/LinkedIn ads, scores each by estimated CTR-likeli…
- `brand-strategist` — **brand-strategist**: Brand Strategist — brand naming, identity systems, positioning, voice, and messaging frameworks
- `customer-journey-mapper` — **customer-journey-mapper**: Customer Journey Mapper — maps full buyer journeys: awareness→consideration→decision touchpoints, friction points, emot…
- `newsletter-bot` — **newsletter-bot**: Newsletter Bot — automated email newsletters with RSS curation, subscriber segmentation, HTML/text generation, and SMTP…
- `paid-media-specialist` — **paid-media-specialist**: Paid Media Specialist — Google Ads and Meta Ads strategy, campaign architecture, keyword research, ad copy, audience ta…
- `referral-rocket` — **referral-rocket**: ReferralRocket — builds automated referral programs with incentive calculation, tracking mechanics, and viral sharing c…
- `seo-agent` — **seo-agent**: SEO Agent — full on-page SEO: audits title/meta/headings/internal links, keyword clustering by intent, content gap anal…

</details>

<details>
<summary><b>Ecommerce</b> (7)</summary>

- `arbitrage-bot` — **arbitrage-bot**: Arbitrage Bot — scans Amazon/eBay/Walmart/StockX for ROI ≥ 20% price arbitrage opportunities with watchlist management …
- `ecom-agent` — **ecom-agent**: E-Commerce Agent — product research, AI listing copy for Shopify/Etsy, email marketing flows, Facebook/Google ad copy, …
- `inventory-sync` — **inventory-sync**: Inventory Sync Agent — monitors supplier stock levels, forecasts demand using 7-day sales averages, and triggers auto-r…
- `order-processor` — **order-processor**: E-commerce Order Processor — listens for new orders via webhook, validates payment, places supplier orders, and notifie…
- `print-on-demand` — **print-on-demand**: Print-on-Demand — merch automation for Printful, Teespring, and similar platforms
- `product-researcher` — **product-researcher**: Product Researcher — scans TikTok trends and Amazon bestsellers daily, validates demand via Google Trends / JungleScout…
- `product-scout` — **product-scout**: E-commerce Product Researcher — finds arbitrage opportunities, trending products, validates suppliers

</details>

<details>
<summary><b>Analytics</b> (7)</summary>

- `analytics-bi` — **analytics-bi**: Analytics BI — business intelligence dashboard: reads system state files to produce KPI summaries, revenue trends, pipe…
- `ceo-briefing` — **ceo-briefing**: CEO Briefing — daily executive summary: recent tasks, agent health, pipeline movements, revenue metrics, pending action…
- `conversion-rate-optimizer` — **conversion-rate-optimizer**: ConversionRateOptimizer — analyzes funnels, designs A/B tests, and provides CRO recommendations to increase conversion …
- `data-analyst` — **data-analyst**: Market Research Analyst — analyzes trends, generates SWOT, creates reports with data
- `ecom-dashboard` — **ecom-dashboard**: E-commerce Dashboard Agent — aggregates real-time metrics (revenue, profit margin, orders, top products) from Stripe + …
- `feedback-loop` — **feedback-loop**: Feedback Loop — tracks outreach message effectiveness by scoring templates based on reply/conversion outcomes, surfaces…
- `report-generator` — **report-generator**: Report Generator — compiles weekly/monthly business reports from system state: revenue, pipeline, content activity, age…

</details>

<details>
<summary><b>Coordination</b> (6)</summary>

- `orchestrator` — **orchestrator**: Master Orchestrator — routes tasks to specialist agents and coordinates multi-agent workflows
- `react_planner` — **react_planner**: ReAct Planner Agent — decomposes complex goals into structured subtask plans
- `scheduler-runner` — **scheduler-runner**: Scheduler Runner — reads a schedules config and triggers tasks (bot start/stop, chat commands, status reports) at defin…
- `skills-manager` — **skills-manager**: Skills Manager — 111-skill library with custom agent builder. Create, combine, and manage skill sets.
- `status-reporter` — **status-reporter**: Status Reporter — generates compact hourly system-health summaries and delivers them via WhatsApp and Discord; aggregat…
- `task-orchestrator` — **task-orchestrator**: Task Orchestrator — durable planner and multi-agent coordinator for enterprise upgrade missions, task decomposition, ag…

</details>

<details>
<summary><b>Social</b> (6)</summary>

- `linkedin-growth-hacker` — **linkedin-growth-hacker**: LinkedInGrowthHacker — LinkedIn profile optimization, connection campaigns, and viral content creation for B2B lead att…
- `personal-brand` — **personal-brand**: Personal Brand — builds complete personal brand: LinkedIn bio/headline/about, thought leadership content, speaking topi…
- `social-guru` — **social-guru**: Social Media Manager — finds viral content, writes engaging captions, generates hashtags
- `social-media-manager` — **social-media-manager**: Social Media Manager — full-pipeline content: brief intake, trend research, multi-platform content strategy, scripts, c…
- `social-poster` — **social-poster**: Social Media Poster — generates viral content scripts and images, schedules posts across Instagram/TikTok/Twitter at pe…
- `social-scheduler` — **social-scheduler**: Social Scheduler — schedules social media posts with timestamps, tracks posting status, generates AI content drafts, an…

</details>

<details>
<summary><b>Content</b> (5)</summary>

- `content-calendar` — **content-calendar**: Content Calendar — plans and schedules content across channels: generates topic ideas, assigns publish dates, content t…
- `content-master` — **content-master**: SEO Content Specialist — writes 2000+ word optimized articles with proper structure
- `course-creator` — **course-creator**: Course Creator — end-to-end online course automation: outlines, lesson writing (~1000 words each), quizzes, pricing tie…
- `creator-agency` — **creator-agency**: Creator Agency — creator/personal-brand automation: content planning, scripting, and scheduling
- `faceless-video` — **faceless-video**: Faceless Video — YouTube/TikTok production pipeline: scripts, scene extraction, voiceover text, Midjourney image prompt…

</details>

<details>
<summary><b>Trading</b> (4)</summary>

- `crypto-trader` — **crypto-trader**: Crypto Trading Analyst — technical analysis, patterns, risk assessment with confidence scores
- `polymarket-trader` — **polymarket-trader**: Polymarket Trader — prediction market trading with MiroFish swarm simulation for probability estimates, paper/live mode…
- `signal-community` — **signal-community**: Signal Community — aggregates polymarket-trader and MiroFish signals, formats for Telegram/Discord, tracks signal perfo…
- `turbo-quant` — **turbo-quant**: Turbo Quant — quantitative trading engine with signal generation, backtesting, risk scoring, and portfolio optimisation…

</details>

<details>
<summary><b>Development</b> (4)</summary>

- `api-tester` — **api-tester**: API Tester — generates HTTP test suites for REST APIs: validates responses, checks auth/rate limits, tests edge cases, …
- `bot-dev` — **bot-dev**: Trading Bot Developer — code review, feature implementation, optimization. Security-first
- `chatbot-builder` — **chatbot-builder**: Chatbot Builder — generates complete chatbot templates for niches (fitness, recipes, dating, customer service, coaching…
- `website-builder` — **website-builder**: Website Builder — generates complete landing page copy and structure: hero section, feature blocks, social proof, prici…

</details>

<details>
<summary><b>Finance</b> (4)</summary>

- `bookkeeper` — **bookkeeper**: AI Bookkeeper — pulls Stripe/PayPal transaction data, categorises expenses, generates P&L reports, and prepares quarter…
- `finance-wizard` — **finance-wizard**: Finance Wizard — P&L modeling, investor pitch financials, revenue models, and fundraising prep
- `financial-tools` — **financial-tools**: Financial Tools — invoice management, quotes, P&L, and payment reminders
- `invoicing` — **invoicing**: Invoicing — generates professional invoice drafts from deal data: line items, tax calculation, totals, payment terms, a…

</details>

<details>
<summary><b>Support</b> (3)</summary>

- `customer-support` — **customer-support**: Customer Support — support ticket triage: classifies issues (refund/bug/billing/onboarding), drafts empathetic reply te…
- `support-bot` — **support-bot**: E-commerce Support Bot — 24/7 customer service agent that classifies tickets, auto-resolves 90% of cases (refunds, trac…
- `ticket-system` — **ticket-system**: Ticket System — task tracking with an immutable audit trail

</details>

<details>
<summary><b>Strategy</b> (3)</summary>

- `company-builder` — **company-builder**: Company Builder — builds companies from scratch with simulations, business plans, and GTM strategy
- `pitch-deck-builder` — **pitch-deck-builder**: Pitch Deck Builder — builds investor-grade pitch decks: problem/solution/market/traction/team/financials/ask slides wit…
- `risk-analyst` — **risk-analyst**: Risk Analyst — business and project risk assessment: SWOT analysis, risk register with likelihood/impact matrix (1–5 sc…

</details>

<details>
<summary><b>Hr</b> (3)</summary>

- `hr-manager` — **hr-manager**: HR Manager — full hiring pipeline, onboarding, org design, and culture building
- `recruiter` — **recruiter**: Recruiter — recruitment automation: CV screening, candidate outreach, and interview scheduling
- `team-management` — **team-management**: Team Management — manages team roster, assigns tasks to members, tracks workload, generates standup reports, and monito…

</details>

<details>
<summary><b>Communication</b> (3)</summary>

- `discord-bot` — **discord-bot**: Discord Bot — admin control panel and notifications for the AI follow-up system over Discord
- `hermes-agent` — **hermes-agent**: Hermes Agent — multi-channel messaging orchestrator (WhatsApp/Telegram/Discord/SMS/email) with unified conversation con…
- `whatsapp-webhook` — **whatsapp-webhook**: WhatsApp Webhook — receives inbound Twilio WhatsApp messages and routes them into the system

</details>

<details>
<summary><b>Engineering</b> (2)</summary>

- `engineering-assistant` — **engineering-assistant**: Engineering Assistant — full-stack software engineering help: frontend (React/Vue/TS), backend (APIs/DBs), AI/ML engine…
- `react_coder` — **react_coder**: ReAct Coder Agent — writes, reads, and executes code iteratively using a Reason-Act-Observe loop

</details>

<details>
<summary><b>Infrastructure</b> (2)</summary>

- `ai-router` — **ai-router**: AI Router — two-layer model routing: Ollama/Gemma/NVIDIA NIM first, Anthropic/OpenAI cloud fallback. Keeps costs low by…
- `session-manager` — **session-manager**: Session Manager — persist agent task context across reboots so agents resume where they left off.

</details>

<details>
<summary><b>Creative</b> (1)</summary>

- `creative-studio` — **creative-studio**: Creative Director — design briefs, image prompts, brand voice, ad copy

</details>

<details>
<summary><b>Crypto</b> (1)</summary>

- `memecoin-creator` — **memecoin-creator**: Memecoin & Token Creator — full token launch from concept, tokenomics to viral community strategy

</details>

<details>
<summary><b>Growth</b> (1)</summary>

- `growth-hacker` — **growth-hacker**: Growth Hacker — viral loops, funnel optimization, A/B tests, retention, and product-led growth

</details>

<details>
<summary><b>Management</b> (1)</summary>

- `project-manager` — **project-manager**: Project Manager — sprint planning, milestones, risk registers, Gantt charts, and team coordination

</details>

<details>
<summary><b>Design</b> (1)</summary>

- `ui-designer` — **ui-designer**: UI Designer — design systems, component specs, accessibility audits (WCAG 2.1), color palettes, typography, responsive …

</details>

<details>
<summary><b>Testing</b> (1)</summary>

- `qa-tester` — **qa-tester**: QA Tester — test plans, test case generation, API testing, bug reports, performance testing, security testing (OWASP), …

</details>

<details>
<summary><b>Coding</b> (1)</summary>

- `obsidian-memory` — **obsidian-memory**: Obsidian Memory Base — AI knowledge-base integration with an Obsidian vault: ask questions saved as notes, keyword sear…

</details>

<details>
<summary><b>Orchestrator</b> (1)</summary>

- `ascend-forge` — **ascend-forge**: ASCEND FORGE — system overseer, vibecoding engineer, security specialist, patch/approval/rollback owner, and enterprise…

</details>

<details>
<summary><b>Intelligence</b> (1)</summary>

- `blacklight` — **blacklight**: BLACKLIGHT Security Operations — defensive OSINT, security posture analysis, policy-gated recon, audit logging, and hig…

</details>


---

## API surface

The Node backend mounts **38 route modules** ([backend/routes/](backend/routes/)) under `/api/*`, all protected routes behind `requireAuth`:

| Area | Modules / endpoints |
|---|---|
| Core & system | `health`, `system-ops`, `dashboard-api`, `services`, `settings`, `topics`, `index` |
| Tasks & chat | `tasks`, `tasks-chat`, `execution`, `/api/tasks/run`, `/api/tasks/recent` |
| Companion & voice | `companion`, `sessions`, `/api/voice/*` (runtime, sessions, speak, narrate, synthesize, config) |
| Agents & intelligence | `agents-brain`, `agents-monitor`, `intelligence`, `learning`, `research`, `search` |
| Money & business | `business-ops`, `work-engine`, `company`, `orders`, `ecom-ops`, `/api/money/*` |
| Forge & compute | `forge`, `forge-ops`, `compute`, `remote-compute`, `quantum` |
| Memory & media | `hybrid-memory-router`, `media`, `artifacts-tasks` |
| Security & ops | `security-ops`, `vault`, `api-keys`, `auth-identity` |
| Automation | `workflows`, `evolution`, `fork-integrations` |
| Actions/approvals | `/api/actions/pending`, `/api/actions/{id}/approve`, `/api/actions/{id}/reject`, `/api/actions/metrics` |
| Modes & observability | `/api/mode`, `/api/changelog`, `/api/skills`, `/api/computer-use/mode`, `/metrics` |

---

## Configuration & modes

Runtime behavior is governed by orthogonal modes, not agent tiers:

| Control | Values | Effect |
|---|---|---|
| Automation (`/api/mode`) | `AUTO` · `MANUAL` · `BLACKLIGHT` | Whether safe tasks execute autonomously or wait for approval |
| Evolution (`EVOLUTION_MODE`) | `AUTO` · `SAFE` · `OFF` | Self-patch, propose-only, or static |
| Research (`AUTO_RESEARCH_MODE`) | `ask` · `auto` · `off` | Whether missing context triggers autonomous web research |
| LLM backend (`LLM_BACKEND`) | `anthropic` · `ollama` | Cloud or local-first inference |
| ASR engine (`config.asr.engine` / `VOICE_ASR_ENGINE`) | `auto` · `nemotron` · `whisper` | Which "hear" engine transcribes voice |

**Key environment variables** (auto-sourced from `~/.ai-employee/.env` by `start.sh`):

| Variable | Purpose |
|---|---|
| `JWT_SECRET_KEY` | Token signing secret |
| `LLM_BACKEND` | `anthropic` (default) or `ollama` |
| `STRICT_PIPELINE` | `1` disables graceful pipeline fallbacks (CI/staging) |
| `LOG_LEVEL` | Python logging level (default INFO) |
| `EVOLUTION_MODE` | `AUTO` / `SAFE` / `OFF` |
| `AUTO_RESEARCH_MODE` | `ask` / `auto` / `off` |
| `RESEARCH_MAX_HOPS` · `RESEARCH_MAX_PAGES_PER_DAY` | Research budgets |
| `VOICE_ASR_ENGINE` · `VOICE_ASR_LANGUAGE` | Voice "hear" engine + language |
| `COMPANION_DIALOGUE_TURNS` · `_LINE_CLIP` · `_CHAR_BUDGET` | Conversation-depth budgets |
| `BRAVE_API_KEY` · `BING_API_KEY` | Optional search providers |

State lives under `state/` (`bus.jsonl`, `llm_calls.jsonl`, `python-backend.log`, `version.json`) and SQLite (`audit.db`, `forge_queue.db`, both WAL).

---

## Installation

### Fastest path (Linux, zero-config)
```bash
curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash -s -- --zero-config
```

### Other options
- Linux & macOS (advanced): `curl -fsSL https://raw.githubusercontent.com/F-game25/AI-EMPLOYEE/main/quick-install.sh | bash`
- Windows: `quick-install-windows.bat` or `install-windows.ps1`
- Native desktop app: see [Desktop app](#17-desktop-app--packaging)

Full guide: [INSTALL.md](INSTALL.md) · [GETTING_STARTED.md](GETTING_STARTED.md)

---

## Development & testing

```bash
# Hot-reload dev (two terminals)
PORT=8787 node backend/server.js          # Node backend
cd frontend && npm run dev                 # Vite dev server :5173 (proxies API to :8787)

# Tests
pip install -r requirements-test.txt
npm test                                   # pytest + agent_selftest.py
python3 -m pytest tests/test_<name>.py     # single Python test
node tests/test_<name>.js                  # single Node test (e.g. test:nemotron-asr, test:voice-runtime)
npm run lint                               # syntax-check all Python agent modules
```

Set `STRICT_PIPELINE=1` in CI to surface real failures instead of graceful fallbacks.

---

## Project structure

```
backend/            Node.js: server.js, routes/ (38 modules), agents/, orchestrator/,
                    subsystems/, gateway/, security/, services/voice/
runtime/
  core/             agent_controller, contracts, orchestrator, bus, hitl_gate,
                    money_mode, unified_pipeline, self_evolution/, swarm/, observability/
  companion/        conversational teammate (intent, capability registry, broker, safety)
  engine/           LLM engine public surface (engine.api)
  memory/           memory_router, vector store, strategy store
  skills/           catalog, library, definitions, vendor/ (e.g. last30days)
  agents/<name>/    113 specialist agents (<name>.py, run.sh, requirements.txt)
  forge/            AscendForge controlled code execution
  companyos/ money/ content/ finance/   business operation engines
  config/           agent_capabilities.json, skills_library.json, behavior templates
frontend/           Vite React SPA → frontend/dist
src-tauri/          native desktop shell (Nexus OS)
launcher/           Electron packager (cross-platform installers)
scripts/            build, migrate, backfill, packaging
state/              runtime state (JSON + WAL SQLite); audit.db, bus.jsonl
```

---

## Security model

Build assumption: this system will control **real files, browser sessions, local compute,
API keys, and customer projects**. Therefore: treat all external input as hostile; retrieved
text is data, never commands; every tool call is permissioned; dangerous actions (delete,
overwrite, shell side-effects, installs, auth/config edits, schema changes, deploys, external
messages, secret access, billing/routing changes) require explicit approval; secrets live only
in env/secret managers and are redacted everywhere; authorization is enforced server-side and
close to the action; execution is sandboxed; everything security-relevant is audited. Agents
have autonomy levels and cannot self-upgrade permissions or bypass approval by delegating.

A task is **done** only when: code builds, tests pass, permissions are enforced, unsafe input
is handled, secrets are protected, logs are redacted, dangerous actions are gated, rollback is
possible, changed files are listed, and remaining risks are documented.

---

## License

MIT — see [LICENSE](LICENSE).
