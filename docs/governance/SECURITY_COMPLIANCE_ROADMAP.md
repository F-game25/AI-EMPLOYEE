# Security, Reliability & Compliance Roadmap — AI-EMPLOYEE / Nexus OS / Ascend Forge

**Horizon:** Jul → Dec 2026 (6 goal-milestones, 2-week sprint cadence)
**Status:** APPROVED by Lars (2026-06-30) — canonical security/governance/compliance track
**Relationship:** This is the security/governance/compliance track of the canonical system plan
([docs/SYSTEM_COHERENCE_PLAN.md](../SYSTEM_COHERENCE_PLAN.md)). Where they overlap, that plan is the
parent; this doc is the authoritative detail for the security/legal milestones.

---

## 1. Context — why this roadmap exists

A system audit of the vibe-coded AI-OS (plus independent research on how AI-generated apps fail)
showed the same pattern: **the happy path works, but security, governance, edge-cases, observability
and legal-readiness lag behind feature velocity.** The fix is not more features — it is a
**governance/security/compliance layer that automatically proves every future change is safe.**

**Decisions locked (with Lars):**

| Decision | Choice | Effect on roadmap |
|---|---|---|
| Deploy target (next ~3 mo) | **Local-desktop only** | Agent-autonomy, sandbox integrity, correctness lead. Remote-exposure gates (TLS, DAST, public-`/workspace`, strict prod CSP) are **built defensively but unforced locally** — a switch, not a rebuild. |
| First deliverable | **Governance docs first** | M1 produces grounded registers before module code. |
| Legal scope | **Full Compliance Center** | M4–M5; all generated legal text is **DRAFT, requires Lars's human/legal review** (not legal advice). |
| External-agent learning | **Moltbook = untrusted signal source** | M6; read-only, HITL-gated, no raw content into memory/training. |

---

## 2. North-Star Goals (outcome, not task — "work per goal")

| # | Goal (success = provable, not "it runs") | Proof artifact |
|---|---|---|
| G1 | **Every sensitive route, tool and agent action is permissioned by default** — deny-by-default, machine-verified in CI | Route-auth scanner green; capability-firewall manifests enforced |
| G2 | **No agent can exceed its authority** — bounded tools, network, budget, autonomy, with human approval on consequential actions | Per-agent capability manifests + HITL audit trail |
| G3 | **No fake success anywhere** — every "done" carries evidence (tests, diff, artifact hash, audit event) | System-wide response contract + green suite |
| G4 | **The system is provably safe to run untrusted input** — prompt-injection, RAG-poisoning, tenant-leak, sandbox-escape all fail closed under test | Adversarial test suites in CI |
| G5 | **The system is legally defensible** — AI-Act classification, data-processing register, consent/retention, audit export, draft policies | Compliance Center + LEGAL_READINESS_REGISTER |
| G6 | **The system can learn from external AI networks without contamination** — untrusted agent content never becomes instruction, memory, tool-call, secret, or training data | Moltbook Learning Lab: isolation contract tests green |

**Operating principles (enforced every milestone):** deny-by-default · no hardcoded values
(config from `security.yml` / manifests) · evidence before "done" · smallest safe change ·
treat all external input as hostile · additive + reversible · scaling kept in mind.

---

## 3. Verified current state (grounded — corrects stale audit claims)

| Area | Reality (evidence) | Real gap to close |
|---|---|---|
| Route auth | 782 routes / 806 `requireAuth` refs in `backend/` (the "44/119" was stale) | **Automated** scanner proving each sensitive route is gated |
| CI security | bandit + CodeQL + Black Duck run (`.github/workflows/ci.yml`, `.github/codeql/`) | bandit non-blocking (`\|\| true`); no secret-scan / route-auth / tenant-leak / injection gate |
| Sandbox | Docker + Process fallback w/ `ALLOWED_COMMANDS` (`backend/infra/sandbox/executor.js`) | `SANDBOX_REQUIRE_DOCKER` hard-fail for staging/prod |
| Governance/GDPR | governance subsystem + GDPR Art.15/20 tests (`tests/test_compliance_safeguards.py`) + envelope-encryption design (`docs/PRIVACY_ARCHITECTURE.md`) | AI-Act classifier, data-processing register, audit export, capability firewall |
| `/workspace` | public `express.static`, `index:false` (`backend/server.js`) | auth / signed token / content-type allowlist / sanitization (lower urgency local) |
| CSP | `unsafe-inline` script+style (`backend/server.js`) | dev/desktop/staging/prod CSP split |
| Agent autonomy | `hitl_gate.py` + scattered `risk_level` + `agent_capabilities.json` | **formal per-agent capability manifest** |
| No-fake-success | enforced in `runtime/core/tool_registry.py` | promote to system-wide response contract |

**Reuse — do NOT rebuild:** `requireAuth` · `hitl_gate.py` · `backend/infra/governance/` +
`governance_digest.py` · `test_compliance_safeguards.py` · `runtime/config/security.yml` ·
`sandbox/executor.js` · `tool_registry.py` (no-fake-success) · `tenancy.py` ·
`agent_capabilities.json` · `NODE_ENV` · `state/audit.db`.

---

## 4. Roadmap at a glance

| Milestone | Window | Goal | Exit proof |
|---|---|---|---|
| **M1 — See & Stabilise** | Jul 2026 | Full visibility + in-flight items closed + suite green | 6 docs reviewed; `npm test` green; route-auth scanner live |
| **M2 — Capability Firewall** | Aug 2026 | No agent exceeds its authority; prod-mode scaffold | Manifests enforced at dispatch; mode gates pass negative tests |
| **M3 — Prove Safe Under Attack** | Sep 2026 | Adversarial inputs fail closed; CI gate blocks | Injection/tenant-leak/sandbox-escape suites green & blocking |
| **M4 — Compliance Center (core)** | Oct 2026 | AI-Act classification + data register + audit export | Classifier + register + export round-trip tested |
| **M5 — Legal Drafts + Scale-Readiness** | Nov 2026 | Draft policies + Postgres/observability path | DRAFT ToS/Privacy w/ review banner; scale plan signed |
| **M6 — Moltbook Learning Lab** | Dec 2026 | Learn from an untrusted AI-agent network without contamination | Raw content provably cannot reach trusted memory / tools / secrets; read-only; HITL-gated lessons |

Cadence: **2-week sprints**, review at each boundary. Sizes are T-shirt (S/M/L). Dates are
goal-targets, re-baselined each sprint review.

---

## 5. Milestones in detail

### M1 — See & Stabilise (Jul 2026) — *Goal: nothing hidden, nothing broken*

**Why:** You cannot govern what you cannot see. Produce the grounded map + registers, close the
already-started tactical fixes so the suite is green and no security item dangles.

**Tasks**
1. **(L) Produce 6 governance docs** under `docs/governance/`, every claim citing `file:line`:
   `SYSTEM_MAP.md`, `SECURITY_RISK_REGISTER.md`, `LEGAL_READINESS_REGISTER.md`,
   `IMPLEMENTATION_PLAN.md`, `TEST_MATRIX.md`, `CLAUDE_TASKS.md`.
2. **(S) Reproduce full suite** (`npm test`) to capture the exact failing set.
3. **(M) Fix skill-router routing precedence** — `_match_executable_skillbase` (step 0) over-grabs
   generic goals. Tighten step-0; add a regression test asserting the intended route.
4. **(S) Fix the 2nd failing test** once reproduced.
5. **(M) Harden `shell_exec`** — drop `shell=True`; `shlex`-parse; allowlist `argv[0]` basename
   **sourced from `security.yml`** (no hardcoded list). Unit tests (allowed/blocked/metachars/secrets-stripped).
6. **(M) Route-auth scanner v1** — `backend/security/route_auth_scanner.js`: classify each route
   public/protected, fail on sensitive-but-unprotected. CI job (non-blocking → blocking once clean).
7. **(S) Confirm JWT pins** stay (`algorithms:['HS256']` at all HMAC verify sites); document.

**DoD:** 6 docs reviewed · `npm test` green · scanner reports 0 unannotated sensitive routes ·
shell_exec tests pass. **Depends on:** none. **Rollback:** docs additive; code localized + git-reverts.

### M2 — Capability Firewall (Aug 2026) — *Goal: bounded agents, bounded modes*

**Why:** OWASP LLM06 "Excessive Agency" is the top risk for a tool-using, memory-writing,
web-researching, sandbox-executing agent fleet. Make authority explicit and enforced.

**Tasks**
1. **(L) Agent capability manifest** (config-driven, extends `agent_capabilities.json`): per agent →
   `allowed_tools`, `forbidden_tools`, `data_access`, `network` (domain allowlist), `budget`,
   `human_approval_required_for`, `logging`, `risk_level`.
2. **(L) Enforce at dispatch** (`tool_registry.py` / `react_tools.py` / `engine/agent/agent_loop.py`):
   deny-by-default; consequential actions via `hitl_gate`; every decision audited to `audit.db`.
3. **(M) Production-mode scaffold** — unified mode (`dev-local`/`desktop-local`/`staging`/`production`);
   gate registry (`SANDBOX_REQUIRE_DOCKER`, no-public-`/workspace`, strict-CSP) active only in staging/prod.
4. **(M) Workspace isolation** — `/workspace` behind signed preview token + content-type allowlist + CSP sandbox.
5. **(M) No-fake-success contract** — shared schema
   `{ok,status,evidence,missing_requirements,next_safe_action,user_approval_required}`; CI lint flags
   success returns lacking evidence.

**DoD:** every agent has a manifest · forbidden tool → blocked + audited · prod-mode negative tests
fail closed · contract adopted by ≥ the 5 default exec skills. **Depends on:** M1.
**Rollback:** manifests + enforcement behind a feature flag.

### M3 — Prove Safe Under Attack (Sep 2026) — *Goal: untrusted input fails closed*

**Why:** RAG results, web/browser content, files, GitHub issues, model output, memory entries are all
hostile per CLAUDE.md. Prove they cannot become commands or cross tenants.

**Tasks**
1. **(L) Prompt-injection / RAG-poisoning suite** — malicious docs/pages/memories must not override
   policy or trigger forbidden tools; injection markers treated as data.
2. **(M) Tenant-leak suite** — tenant A can never read tenant B state; fuzz JWT `tenant_id` swaps.
3. **(M) Sandbox-escape suite** — path traversal, env exfil, metachar break-out; process-fallback
   forbidden in prod; `setrlimit` caps + secret-strip hold.
4. **(M) Upload validation suite** — content-type-by-magic-bytes, path normalisation, quarantine.
5. **(M) CI security gate hardening** — bandit **blocking** (drop `\|\| true`); secret-scan
   (gitleaks/trufflehog); wire route-auth scanner + new suites as required; evidence report per build.

**DoD:** all adversarial suites green & **required** in CI · secret-scan clean · bandit blocking ·
evidence report emitted. **Depends on:** M2. **Rollback:** gates start as warnings → flip to blocking.

### M4 — Compliance Center, core (Oct 2026) — *Goal: legally defensible operations*

**Why:** EU AI Act obligations land 2 Aug 2026; PLD 9 Dec 2026.

**Tasks**
1. **(L) AI-Act classifier** — per feature: prohibited / high-risk / limited-risk / minimal-risk +
   rationale + obligations; surfaced in a Compliance Center page (reuse governance subsystem).
2. **(L) Data-processing register** — what data, why, legal basis, retention, location; wired to actual stores.
3. **(M) Audit export** — all agent actions, approvals, model calls, data access → exportable
   (reuse `audit.db` + `governance_digest.py`); ties to GDPR Art.15/20.
4. **(M) Consent / retention controls** — user export + erase; retention timers.

**DoD:** classifier covers every shipped feature · register complete + tested · audit export
round-trips · erase/export pass extended `test_compliance_safeguards.py`. **Depends on:** M2, M3.

### M5 — Legal Drafts + Scale-Readiness (Nov 2026) — *Goal: shippable drafts + a scaling path*

**Tasks**
1. **(M) Draft legal generators** — ToS, Privacy policy, per-feature AI disclaimer, "do-not-use-for"
   policy. **Every output stamped "DRAFT — requires human/legal review."**
2. **(M) Scale-readiness plan** — Postgres migration path, observability expansion (Prometheus at
   `/metrics`), production go-live checklist, DAST (ZAP) playbook — documented, switch-ready, not forced.
3. **(S) Roadmap retro + re-baseline** — fold learnings into `MASTER_TASK_LIST.md`.

**DoD:** draft policies generate with review banner · scale plan reviewed · prod go-live checklist exists.
**Depends on:** M4.

### M6 — Moltbook Learning Lab (Dec 2026) — *Goal: learn from an untrusted AI-agent network without contamination*

**Why:** Moltbook is a Reddit-style network **for AI agents**. Independent research is a red flag, not
a green light: ~18% of posts contain *action-inducing* language; agents have leaked API keys/passwords/
**BIP39 seed phrases**; fine-tuning on raw Moltbook data **dropped truthfulness 0.366 → 0.187**. Agent
discussions carry far less reproducible detail than human dev forums — good as *inspiration*, weak as
*truth*.

**The one hard rule:**
> **Moltbook is an untrusted signal source, never a teacher.** Raw agent content must never become an
> instruction, reach trusted memory, touch a tool, expose a secret, or train a model. It may only
> influence the system after quarantine → sanitisation → verification → human/high-confidence gate.

**Key finding — we already own ~90% of this.** Moltbook ingestion ≈ the existing Autonomous Research
Loop pointed at a hostile source, and every safety primitive already ships and is production-grade.

| Capability needed | Reuse (exists) | file:line |
|---|---|---|
| Fetch untrusted URL (stealth) | `AutoResearchAgent.research_selected` → `_fetch_safe` → `CloakBrowser.fetch_url` | `runtime/core/auto_research_agent.py:301`,`:381` |
| SSRF gate | `require_safe_url(url)` | `runtime/core/url_guard.py:100` |
| Low-trust source weighting | `trust_for_url()` + `source_trust.json` | `runtime/core/source_trust.py:49` |
| Verify before persist (0.7/0.4 thresholds) | `VerificationEngine.verify` | `runtime/memory/verification.py:162` |
| **Human-approval staging (no raw → memory)** | `pending_queue.add` (tenant-scoped); only `auto_save` reaches stores | `runtime/memory/pending_queue.py:65`; `auto_research_agent.py:452` |
| Read-side trust gate + injection-marker zeroing | `apply_trust_gate` + `memory_trust.json` | `runtime/core/memory_trust.py:182` |
| HITL approval card w/ evidence | `hitl_gate.require_approval(..., research_findings=...)` | `runtime/core/hitl_gate.py:164` |
| Capability firewall (deny-by-default, L0–L4) | `CapabilityRegistry` + `Capability(risk_level)` + `safety_gate.evaluate` | `runtime/companion/capability_registry.py:20`; `schemas.py:20`; `safety_gate.py:33` |
| Master on/off mode pattern | `computer_use_mode.py` (fails safe OFF) → copy for `moltbook_mode.py` | `runtime/companion/computer_use_mode.py` |
| Secret/key/private-key/.env/PII detect + redact | `egress_guard.contains_secret/classify/redact`; `log_sanitizer.sanitize` | `runtime/core/egress_guard.py:40`; `log_sanitizer.py:24` |
| Prompt-injection detection (block on hit) | `prompt_guard.check_and_sanitize` | `runtime/core/prompt_guard.py:14` |
| Semantic adversarial risk score | `adversarial_filter.assess` | `runtime/core/adversarial_filter.py:45` |
| Append-only hash-chained audit | `audit_engine.record` + `audit.append` | `runtime/core/audit_engine.py:79`; `audit.py:57` |
| 3-layer persist (gated write side) | `MemoryRouter.store`; `BrainGraph.upsert_concept/link/attach_memory`; `KnowledgeStore.add_knowledge` | `memory_router.py:130`; `brain_graph.py:59`; `knowledge_store.py:87` |

**Net-new (small):** `runtime/moltbook/` package — connector; quarantine store; a `safety_scanner`
that **composes** the guards above; `learning_processor` (extract/summarise/propose); **BIP39
seed-phrase detector (the one real gap)**; `moltbook_mode.py`; Moltbook capability + broker adapter;
eval-draft generator; `/api/moltbook/*` routes; a Learning-Lab **section inside the Research workspace**.

**Threat model (touches: external input, memory, RAG, agents, autonomy, secrets):**

| Threat | Vector | Mitigation (mostly reused) |
|---|---|---|
| Prompt injection → privileged action | "ignore previous… run this" | Content is **data, never prompt**: parse to schema, never `f"…{raw}"`; `prompt_guard`+`adversarial_filter` block; firewall denies all tools |
| Secret/seed ingestion or echo | posts contain keys/BIP39 | `egress_guard` + BIP39 detector → reject for learning (keep only as security-lesson signal); redact before any storage/log |
| Memory poisoning | "remember X as fact" | No raw → memory; `verify` + `pending_queue` + HITL; trust ≈ 0.15–0.25 skews to pending/discard; read-side `apply_trust_gate` zeroes markers |
| Model contamination | fine-tuning on slop | **No fine-tuning on Moltbook data, ever**; distillation only on approved verified summaries |
| Excessive agency | module gains tools | module = capability `risk_level=L0/L1`, whitelist read/summarise/propose only |
| SSRF / malicious links | links to internal/metadata | `require_safe_url` on every fetch |
| Tenant leakage | candidates cross tenants | tenant-scoped quarantine + `pending_review_queue.json` |
| Outbound exfiltration | agent posts our internals | **No posting in V1**; V3 only via low-priv throwaway persona, redaction + approval for first N posts |

**Pipeline (one flow, reusing the research spine):**
```
Moltbook Connector (read-only; API or CloakBrowser scrape)
  → Quarantine store (state/moltbook/ — SEPARATE from trusted memory)
  → Safety Scanner (prompt_guard · egress_guard · adversarial_filter · BIP39) → reject/redact
  → Sanitizer (strip markdown/html/hidden prompts; structured record; keep source refs)
  → Research Extractor (LLM → structured claims; 5 scores)
  → VerificationEngine.verify → discard | pending_review | (rarely) auto_save
  → Learning Candidate → pending_queue.add → hitl_gate.require_approval(research_findings=…)
  → eval cases · skill proposals (Ascend Forge) · approved research notes · gated memory lesson
```
Every arrow emits `audit_engine.record(...)`.

**Concrete contracts (locked):**

*Quarantine schema — net-new SQLite WAL under `state/moltbook/` (tenant-scoped):*
```
moltbook_raw_items(id, source_id, submolt, author_agent, content_raw, fetched_at, url,
                   hash UNIQUE, status[quarantined|rejected|sanitized|candidate], tenant_id)
moltbook_safety_findings(id, item_id→raw_items, finding_type[prompt_injection|secret|malware|
                   dangerous_instruction|pii|spam|low_quality], severity, evidence_snippet, decision)
moltbook_learning_candidates(id, source_item_ids[json], candidate_type[idea|warning|eval_case|
                   skill_upgrade|architecture_pattern|bug_pattern], summary, evidence_score,
                   risk_score, novelty_score, usefulness_score, reproducibility_score,
                   status[proposed|approved|rejected|implemented], tenant_id)
```
Dedupe by `hash`; retention cap (config, not hardcoded). Scores are **0–100**.

*Gate policy — what the High-Confidence Gate may auto-approve vs must send to HITL:*
- ✅ auto-approve **only** (low risk + high evidence/reproducibility): eval-case **draft** · research-note **draft** · warning pattern · dashboard insight
- ⛔ **never auto-approve** (always `hitl_gate.require_approval`): code changes · core-personality/memory writes · tool-permission changes · security-policy changes · model fine-tuning · outbound posting

*Module layout (`runtime/moltbook/`):* `connector.py` (thin, wraps research loop) · `safety_scanner.py`
(thin orchestrator composing existing guards) · `research_extractor.py` · `eval_generator.py` ·
`learning_gate.py` (thin: verify → candidate store → hitl_gate) · `mode.py` (copy of computer_use_mode,
default OFF) · BIP39 detector.

*Surfaces:* Node routes (all `requireAuth`): `GET /api/moltbook/status` · `POST /fetch` ·
`GET /quarantine` · `POST /analyze` · `GET /candidates` · `POST /candidates/:id/approve|reject`.
WS: `moltbook:candidate_ready`, `moltbook:approval_required`.
**UI — intentional divergence from the source dossier:** dossier says "new page"; Lars's UI rule
forbids new top-level tabs → build as a **section inside the Research workspace** with 8 internal
sub-tabs (Overview · Quarantine · Safety Findings · Learning Candidates · Generated Evals ·
Approved Lessons · Audit Log · Outbound[disabled]).

**Autonomy ladder (cap at 2 now):** `0 Observe · 1 Summarise+propose · 2 Evals/research notes ·
3 Suggest code via Ascend Forge · 4 Post`. V1 ceiling = 2, enforced by `moltbook_mode.max_autonomy_level`
+ capability risk levels.

**Phasing:**
- **V1 (this milestone):** read-only ingest · quarantine · scanner · sanitizer · extractor · candidate
  UI · eval **drafts** · audit. No posting, no auto memory writes, no fine-tuning.
- **V2:** approved research notes → gated lessons; eval-runner (before/after); Forge skill-proposal path;
  dashboard scoring; `MOLTBOOK_RESEARCH_LOOP` (ingest→scan→summarize→extract→generate evals→propose→test→write notes).
- **V3:** bounded autonomous loop *only after evals prove improvement* — rollback, drift + truthfulness-
  regression detection, prompt-injection red-team suite, optional human-approved outbound research persona.

**DoD:** mode OFF by default · raw content provably isolated (contract tests green) · every
fetch/scan/decision audited · candidates only enter trusted system via HITL/high-confidence gate ·
BIP39+secret+injection rejected · Learning Lab lives inside Research workspace.
**Verify:** `pytest tests/test_moltbook_*.py -q` (security-contract + scanner + isolation); manual:
enable mode → fetch a fixture with an injected key+seed-phrase → assert rejected, redacted, audited,
nothing in memory.
**Depends on:** reuses already-shipped guards, so not blocked by M2/M3 — but its security contract
**should be asserted by M3's adversarial harness**, and it consumes M2's capability-manifest enforcement.
**Scheduled after M5** ("finish before starting new"). **Rollback:** whole module behind `moltbook_mode`
(OFF) + feature flag; additive; quarantine/state removable; no change to existing memory write-path
(only a new low-trust caller of it). **Risk:** scanner false-negatives → mitigated by low trust score +
mandatory verify + human gate + audit; nothing auto-applies.

**Resolved decisions:** (A) transport — connector built source-agnostic; quick web check for a public
Moltbook API at kickoff. (B) sequencing — M6 after M5. (C) scope — V1 as above (read-only, autonomy ≤ 2).
(D) this roadmap persisted to the repo (this document).

---

## 6. Cross-cutting — the persistent Security & Legal Gate

Built incrementally across M1–M3, the lasting outcome: **every future PR runs** route-auth scan ·
SAST (bandit, CodeQL) · SCA (Black Duck/OSV) · secret-scan · tenant-leak · prompt-injection ·
sandbox-escape · upload-validation · capability-manifest lint · no-fake-success lint → **emits an
evidence report and blocks on failure.** After M3, no feature merges without passing it. M6's Moltbook
isolation contract joins this gate.

## 7. KPIs / success metrics (tracked at each sprint review)

| KPI | Baseline | Target |
|---|---|---|
| Sensitive routes auto-verified | 0% (manual) | 100% |
| Agents with enforced capability manifest | 0 | all (110+) |
| Adversarial suites in CI (blocking) | 0 | 4 (injection, tenant, sandbox, upload) + Moltbook isolation |
| CI security gates blocking | partial (CodeQL) | full (incl. bandit, secrets, route-auth) |
| Features with AI-Act classification | 0 | 100% of shipped |
| Moltbook raw content reaching trusted memory | n/a | 0 (provably, by test) |
| Suite status | 1+ failing | green |

## 8. Top risks (local-desktop-adjusted)

| Risk | Sev | Mitigation |
|---|---|---|
| Excessive agency (LLM06) | High | M2 capability firewall, deny-by-default |
| Prompt-injection turning data into commands | High | M3 suite + M6 "retrieved text is never authority" |
| `/workspace` agent-generated HTML/JS | Med (local) | M2 isolation + prod-mode public-off |
| Sandbox process-fallback weaker than Docker | Med | M2 `SANDBOX_REQUIRE_DOCKER` in prod |
| Legal misclassification / unreviewed legal text | Med | M4 advisory + M5 mandatory-review banner |
| Untrusted external-agent contamination (Moltbook) | Med | M6 quarantine + scanner + verify + HITL; no fine-tuning |
| Scale (JSON/SQLite → multi-customer) | Low now | M5 Postgres path documented, switch-ready |

## 9. Definition of Done (overall, per CLAUDE.md rule 30)

Code builds · suite green · permissions enforced (deny-by-default) · unsafe input handled & tested ·
secrets protected · logs redacted · dangerous actions HITL-gated · rollback possible · changed files
listed · remaining risks documented · **every "done" backed by evidence.**
