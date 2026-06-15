# CompanyOS (P10) — Design to beat Polsia, using the whole system

**Date:** 2026-06-15 · **Goal:** an AI company-builder that is *more specialized and smarter* than Polsia by orchestrating the subsystems we've already built — and that structurally avoids Polsia's documented failures.

## How Polsia works (researched 2026-06-15)
Layered multi-agent: a **chat/strategist agent** → a **task system** → **specialized agents** (engineering/marketing/research/support) with *limited tools + bounded task scope* ("predictable, cheaper"). Persistent **memory layers** (company context, past decisions, user traits). Acts via connected accounts, platform-managed services, APIs, and **automated browser sessions**. Designed to **run unattended on recurring cycles** ("wakes at night, does work, sends a morning update"). User supplies idea, permissions, constraints, budget.

## Polsia's gaps (evidence-backed) → our edge → subsystem that delivers it
Trustpilot **2.1/5, 70% one-star** (May 2026). The complaints are precisely the things we already fixed.

| # | Polsia failure (evidence) | AI-EMPLOYEE edge | Delivered by (already built) |
|---|---|---|---|
| 1 | **No validation before building** — accepts "surprise me", provisions + launches immediately. (Rest of World: factory worker, months + $199/mo → 7 signups, 0 paying.) | **Validation-first: refuse to build on unvalidated demand.** A gate that scores demand/competition/feasibility and can say *"don't build this yet."* | **M8 Research Quality Engine** + **critique layer** (already pushes back) + new `validation_engine` |
| 2 | **Fake completion** — "tasks marked complete that don't actually work; products never deploy." (root of the 70% 1-star) | **Structurally impossible to fake success.** Placeholder output → task *fails*, honest errors everywhere. | **Reality-audit work** (unified_pipeline enforcement, honest failures, real artifacts) — done this session |
| 3 | **Credits burned on failed actions**, refunds denied. | **Honest cost; only real work counts; transparent spend with caps; no revenue share.** | compute spend caps + model_lanes cost + **local-first ownership** |
| 4 | **Unauthorized autonomous actions** — sent press outreach/emails w/ wrong names & prices, no approval. | **Approval gates on every external send/spend/deploy.** Nothing leaves without HITL. | **HITL gate + safety_gate + M4/M7 requires_approval_for + critique** |
| 5 | **Generic marketing**, no personal voice. | **Personalized, brand-voiced, memory-grounded output.** | **M5 Content Factory** + voice profiles + context_db memory + **skills.run** (147 real skills) |
| 6 | **Lock-in** — code hard to extract, lost if subscription lapses, unclear ownership. | **Full local ownership + export package** (code/data/memory/logs). No lock-in. | **local-first architecture** + new `export` in CompanyOS |
| 7 | **Aggressive economics** — $49/mo + 20% of revenue + 20% of ad spend; loses money/customer. | **You own it; runs on your hardware/keys; no take-rate.** Hardware-dynamic model tiers keep cost low. | **model_lanes** (local-first tiers) + compute fabric |
| 8 | **Poor transparency/support** — can't see what agents did/why; weeks-long support gaps. | **Every action logged + reasoning traces + avatar shows real state; you're the operator.** | audit logs + companion + decision logs |
| 9 | **"Surprise me" = riskiest** but heavily marketed. | **Teammate that challenges the idea** before spending your time/money. | **critique layer** (stance: recommend_against / need_info) |

**One-line positioning:** *Polsia executes fast on unvalidated ideas and hides failure; CompanyOS validates first, executes honestly, gates every consequential action, and you own everything.*

## CompanyOS architecture (thin orchestrator over existing engines)
`runtime/companyos/` — owns company/project entities + lifecycle; delegates real work to existing subsystems. **No duplication.**

1. **company_store** — Company/Project entities: brief, status, validation verdict, roadmap, agents, artifacts, metrics, risks, decisions. Persisted JSON (local = source of truth).
2. **founder_intake** — idea → clarifying questions (reuses **critique/intent**); produces a structured Founder Brief. Never accepts a blind "surprise me" without surfacing the risk.
3. **validation_engine** *(the killer feature)* — market/competitor/demand/feasibility scoring via **M8 Research Quality** + research engine; verdict `build | pivot | reject | need_evidence`. **Blocks the build path on a weak verdict** (overridable, but explicit).
4. **company_planner** — Founder Brief + validation → roadmap/milestones/agent task graph (reuses **M7 task_decomposer**).
5. **team_orchestrator** — maps roadmap tasks to **M7 Business Swarm** agent contracts (real contracts, approval-gated, no fake autonomy).
6. **task_cycle_engine** — recurring/daily cycles (Polsia's signature) **but every consequential step is HITL-gated**; idle scheduler runs only safe/approved work.
7. **build/market/finance/work adapters** — delegate to **Forge** (code, sandboxed), **M5 Content Factory** (marketing, approval-gated publish), **M6 FinanceOps** (advisory), **M4 Work Engine** (delivery), **M8** (research). Thin adapters, not reimplementations.
8. **metrics_tracker** — real revenue/cost/ROI from the economy ledger; honest (no projections shown as actuals).
9. **export_engine** — package a company's code/data/memory/logs/artifacts for full local ownership.
10. **company route + companion capability** — `/api/company/*` + `company.*` so the avatar/voice teammate runs the whole loop conversationally.

## Autonomy levels (carried from nr6, enforced via safety_gate)
L0 observe · L1 draft · L2 safe-local · L3 approved-external · L4 budget-bounded. Default low; spend/publish/email/deploy/core-mod always gated.

## Build order
1. company_store + founder_intake + **validation_engine** (the differentiator) + company route + companion capability — the spine that proves the "validate-first, honest" edge.
2. company_planner + team_orchestrator (wire M7).
3. build/market/finance/work adapters (wire M4/M5/M6/Forge/M8).
4. task_cycle_engine (gated recurring) + metrics_tracker + export_engine.
5. Frontend Company cockpit page.

## Non-negotiables (the anti-Polsia guarantees)
- **Validate before build** — can refuse. - **No fake success** (reality substrate). - **Approval on all external send/spend/deploy.** - **Local-first, fully exportable, no take-rate.** - **Transparent** action/decision logs. - **Teammate that pushes back.**
