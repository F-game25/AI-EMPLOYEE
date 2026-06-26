# LEGAL_READINESS_REGISTER — AI-EMPLOYEE / Nexus OS
**Generated:** 2026-06-25 · **Jurisdiction:** EU / Netherlands · **Owner:** Lars · part of [governance doc-set](SECURITY_COMPLIANCE_ROADMAP.md)

> ⚠️ **DRAFT — NOT LEGAL ADVICE.** This register is a forward-looking engineering aid produced by
> static inspection. **Every legal interpretation, classification, and "Applies?" call below is a
> draft assumption that REQUIRES the owner's human / qualified-legal review before any reliance.**
> Treat all generated legal text (and the [M5 draft policies](#6-gap-list--milestones)) the same way.

**Scope reality (locked with Lars):** next ~3 months = **local-desktop only, single user** → most
obligations are *latent*, not yet triggered. This register is forward-looking for the day the system
**serves customers**. Cites existing assets so we **extend, not duplicate**.

---

## 1. Why this exists
The system can publish content, scrape data, run outreach, act autonomously via 127 agents with real
tools, profile/remember, and is multi-tenant — surfaces that attract EU AI/data/product law **once
exposed to others**. The goal: know which regulation bites, on what trigger, and what we already have.

---

## 2. Role classification (owner must confirm) ⚠️
| Candidate role | Fit | Basis |
|---|---|---|
| **Provider / deployer of an AI system** | **most likely** | System composes & deploys AI workflows using **existing** external models (Anthropic / Ollama / OpenRouter via [orchestrator.py](../../runtime/core/orchestrator.py)); it does **not** train its own general-purpose model |
| Provider of a **GPAI model** | **unlikely — *unless triggered*** | Would apply only if the owner **significantly modifies / fine-tunes**, **distributes**, or **offers** a general-purpose model under their own name/brand |

**Decision the owner must confirm:** if any GPAI-provider trigger above becomes true, GPAI-provider
obligations attach — **technical documentation, an EU-copyright-law compliance policy, and a public
summary of training content**. Until confirmed: assume **AI-system provider/deployer** (no GPAI duties).
(Provider-vs-deployer split within "AI system" also needs confirmation once customers exist.)

---

## 3. Legal readiness register
*Applies legend:* **yes** = applies now · **likely** = applies once customers/exposure · **conditional** = only if a trigger fires · **later** = future-dated obligation.
*Status legend:* **have** / **partial** / **gap**.

| Regulation | Applies? | Trigger in THIS system | Current status | Required action | M |
|---|---|---|---|---|---|
| **AI Act — prohibited practices** | yes (already in force 2 Feb 2025) | Autonomous agents + profiling/memory could drift into banned manipulation/social-scoring patterns | partial — [HITL gate](../../runtime/core/hitl_gate.py), no formal screen | Add prohibited-practice checklist to classifier; assert none shipped | M4 |
| **AI Act — transparency / limited-risk** | likely | Money-Mode **outreach** ([money_mode.py](../../runtime/core/money_mode.py)) = AI talking to people → must disclose "AI" | gap | AI-disclosure on all outreach/generated content; mark AI-generated output | M4/M5 |
| **AI Act — high-risk** | conditional | Only if used for a high-risk Annex-III purpose (e.g. employment/recruiting decisions) — agent catalog *could* be configured that way | gap — no use-restriction policy | "Do-not-use-for" policy + classifier gate to block high-risk configs | M4/M5 |
| **AI Act — GPAI model duties** | conditional | Only on GPAI-provider trigger (§2) | n/a unless triggered | If triggered: tech docs + copyright policy + training-content summary | M4 |
| **GDPR** | yes (in force 2018) | Personal data in tenants, scraped data, memory/profiling, outreach contacts | **partial — strong base**: Art.15/20 rights tested ([test_compliance_safeguards.py](../../tests/test_compliance_safeguards.py)); envelope-encryption design ([PRIVACY_ARCHITECTURE.md](../PRIVACY_ARCHITECTURE.md)); [audit.db](../../state/audit.db) | Data-processing register; legal basis + consent/retention; scraping lawful-basis review; Art.17 erasure | M4 |
| **DSA (Digital Services Act)** | conditional (applicable since 17 Feb 2024) | Only if a **marketplace / UGC / hosting** surface is *published* (e.g. `/api/marketplace`) | gap — local only today | Defer until any hosting/UGC surface goes public; then notice-&-action + T&Cs | M4 |
| **Product Liability Directive (revised)** | later (MS apply from 9 Dec 2026) | Explicitly covers **software & AI** as products → defective-output liability once a product is placed/served | gap | Quality/defect-evidence trail (extends [no-fake-success](SECURITY_COMPLIANCE_ROADMAP.md) G3); ToS disclaimers; logging for defect defence | M5 |
| **CRA (Cyber Resilience Act)** | later | Security duties for products with digital elements **placed on the market** — not yet (local only) | partial — security roadmap underway | Track; map M1–M3 security gate as evidence base; revisit before any distribution | — |
| **NIS2** | later / likely-not | Applies to in-scope essential/important *entities*; a single-user desktop tool is **likely out of scope** | n/a | Re-assess only if operated as an in-scope service entity | — |
| **Data Act** | conditional | B2B data-sharing / IoT-style data access obligations — only if such data-sharing offerings emerge | n/a today | Monitor; revisit if data-sharing/portability-to-third-parties features ship | — |

---

## 4. AI-Act risk class of the system's own features (advisory ⚠️)
*Engineering self-assessment — confirm with legal.*

| Feature | Likely class | Why | Control owed |
|---|---|---|---|
| **Money-Mode outreach** (`outreach_response_conversion`) | **limited-risk (transparency)** | AI interacts with humans | **Disclose it's AI** on every message |
| **Generated content publish** (`content_publish_track`) | limited-risk | AI-generated content | Label/mark AI-generated output |
| **Agents acting autonomously** (127, real tools) | minimal *(unless purpose makes it high-risk)* | General automation isn't per-se high-risk | HITL + capability firewall (security, not legal) |
| **Memory / profiling** (vector + Neo4j + `state/knowledge_store.json`) | minimal AI-Act / **GDPR-heavy** | Profiling = GDPR concern more than AI-Act class | Lawful basis, retention, erasure (§3 GDPR row) |
| **Data scrape & store** (`data_scrape_filter_store`) | minimal AI-Act / **GDPR + DSA-adjacent** | Class hinges on personal data + source ToS | Lawful-basis + source-ToS review |
| **Manipulation / social-scoring** | **prohibited if present** | Banned category | **Assert NOT built**; classifier screen |

---

## 5. Timeline callout — align Compliance Center to hard dates
| Date | Event | Implication for delivery |
|---|---|---|
| 2 Feb 2025 | AI Act prohibited-practice bans + AI-literacy duties **already apply** | Prohibited-practice screen is **not optional later** — fold into M4 |
| 2 Aug 2025 | GPAI-model obligations apply | Relevant **only if** GPAI trigger (§2) fires |
| **2 Aug 2026** | Majority of AI-Act obligations (most high-risk + transparency) apply | **Compliance Center core (M4, Oct 2026) lands after this** → transparency/disclosure must be ready by M4 |
| **9 Dec 2026** | Revised **PLD** applies in member states (software + AI = products) | **M5 (Nov 2026) draft ToS/disclaimers + defect-evidence trail must precede** any product being served |
| 2 Aug 2027 | Certain Annex-I high-risk obligations apply | Future; revisit if high-risk configs ever enabled |

> Net: M4–M5 (Oct–Nov 2026) is correctly timed **provided** outreach AI-disclosure (AI Act) and
> ToS/disclaimers (PLD) are treated as gating, not stretch.

---

## 6. Gap list → milestones
*Maps the [SYSTEM_MAP §12 gap list](SYSTEM_MAP.md) into legal deliverables. Extend existing assets — don't rebuild.*

**M4 — Compliance Center (core), Oct 2026**
- **AI-Act classifier** — per-feature risk class + prohibited-practice screen; gate high-risk configs.
- **Data-processing register** — purposes, categories, legal basis, retention, recipients (incl. external model providers); ties to [PRIVACY_ARCHITECTURE.md](../PRIVACY_ARCHITECTURE.md).
- **Audit export** — extend [audit.db](../../state/audit.db) → exportable compliance/forensic report (DSAR + defect-defence evidence).
- **Consent / retention controls** — consent capture + retention/erasure jobs; build on tested Art.15/20 rights ([test_compliance_safeguards.py](../../tests/test_compliance_safeguards.py)).

**M5 — Legal Drafts + Scale, Nov 2026** *(all DRAFT, human/legal review banner mandatory)*
- **Draft Terms of Service.**
- **Draft Privacy Policy** (GDPR-aligned; references envelope-encryption design).
- **AI disclaimer / disclosure copy** — AI-Act limited-risk transparency for outreach + generated content.
- **"Do-not-use-for" policy** — block high-risk Annex-III purposes; PLD defect-liability disclaimers.

---

## 7. Open legal decisions (for the owner)
1. **Role confirmation** — AI-system provider/deployer vs GPAI-model provider (§2). Any GPAI trigger planned?
2. **Provider vs deployer** split once customers exist (affects which AI-Act duties attach).
3. **Scraping lawful basis** — personal-data scraping needs a GDPR basis + source-ToS review *(needs verification)*.
4. **Customer-facing date** — first non-local exposure date drives DSA/PLD/CRA activation.
5. Whether any Annex-III high-risk use will *ever* be enabled (decides high-risk obligations).

> Every item above is a **draft** for human/legal sign-off. Where facts were not verifiable in-repo,
> they are marked **(needs verification)**.
