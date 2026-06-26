# Security, Reliability & Compliance Roadmap — AI-EMPLOYEE / Nexus OS / Ascend Forge
**Horizon:** Jul → Nov 2026 (5 goal-milestones, 2-week sprint cadence)
**Status:** APPROVED 2026-06-25 · **Canonical copy** (planning original at `~/.claude/plans/`)

> This is the index for the governance doc-set. Companions in this folder:
> [SYSTEM_MAP](SYSTEM_MAP.md) · [SECURITY_RISK_REGISTER](SECURITY_RISK_REGISTER.md) ·
> [LEGAL_READINESS_REGISTER](LEGAL_READINESS_REGISTER.md) · [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md) ·
> [TEST_MATRIX](TEST_MATRIX.md) · [CLAUDE_TASKS](CLAUDE_TASKS.md)

## 1. Why this exists
A system audit + research on AI-generated app failure modes showed the same pattern: the happy
path works, but security, governance, edge-cases, observability and legal-readiness lag feature
velocity. The fix is a **governance/security/compliance layer that automatically proves every
future change is safe** — not more features.

**Decisions locked (with Lars):**
| Decision | Choice | Effect |
|---|---|---|
| Deploy target (next ~3 mo) | **Local-desktop only** | Agent-autonomy, sandbox, correctness lead; remote-exposure gates built defensively but unforced locally |
| First deliverable | **Governance docs first** | M1 produces 6 grounded registers before module code |
| Legal scope | **Full Compliance Center** | M4–M5; all generated legal text is DRAFT, requires human/legal review |

## 2. North-Star Goals (outcome, not task)
- **G1** Every sensitive route/tool/agent action permissioned by default (deny-by-default, CI-verified).
- **G2** No agent can exceed its authority (bounded tools/network/budget/autonomy + HITL).
- **G3** No fake success anywhere (every "done" carries evidence).
- **G4** Provably safe under untrusted input (injection/RAG-poisoning/tenant-leak/sandbox-escape tests).
- **G5** Legally defensible (AI-Act classification, data register, consent/retention, audit export, draft policies).

**Operating principles:** deny-by-default · no hardcoded values (config from `security.yml`/manifests) ·
evidence before "done" · smallest safe change · treat all external input as hostile · additive +
reversible · scaling kept in mind.

## 3. Roadmap at a glance
| Milestone | Window | Goal | Exit proof |
|---|---|---|---|
| **M1 — See & Stabilise** | Jul 2026 | Visibility + in-flight closed + suite green | 6 docs reviewed; `npm test` green; route-auth scanner live |
| **M2 — Capability Firewall** | Aug 2026 | No agent exceeds authority; prod-mode scaffold | Manifests enforced; mode gates pass negative tests |
| **M3 — Prove Safe Under Attack** | Sep 2026 | Untrusted input fails closed; CI gate blocks | Injection/tenant-leak/sandbox-escape suites green & blocking |
| **M4 — Compliance Center (core)** | Oct 2026 | AI-Act class + data register + audit export | Classifier + register + export round-trip tested |
| **M5 — Legal Drafts + Scale** | Nov 2026 | Draft policies + Postgres/observability path | DRAFT ToS/Privacy w/ review banner; scale plan signed |

Milestone detail lives in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); risks in
[SECURITY_RISK_REGISTER.md](SECURITY_RISK_REGISTER.md); tasks in [CLAUDE_TASKS.md](CLAUDE_TASKS.md).

## 4. Persistent Security & Legal Gate (built across M1–M3)
Every future PR runs: route-auth scan · SAST (bandit, CodeQL) · SCA (Black Duck/OSV) · secret-scan ·
tenant-leak · prompt-injection · sandbox-escape · upload-validation · capability-manifest lint ·
no-fake-success lint → emits an evidence report and **blocks on failure**.

## 5. KPIs (tracked each sprint review)
| KPI | Baseline | Target |
|---|---|---|
| Sensitive routes auto-verified | 0% (manual) | 100% |
| Agents with enforced capability manifest | 0 | all (127) |
| Adversarial suites in CI (blocking) | 0 | 4 |
| CI security gates blocking | partial (CodeQL) | full |
| Features with AI-Act classification | 0 | 100% of shipped |
| Suite status | 1+ failing | green |

## 6. Open decisions (M1 kickoff)
1. `shell_exec` policy — strict no-shell (recommend) vs controlled pipelines.
2. Keep already-applied JWT pins? (recommend: keep)
3. Sprint cadence (2-week) + first milestone to execute.
4. ~~Persist roadmap into repo~~ → **done** (this file).

## 7. Definition of Done (overall, per CLAUDE.md rule 30)
Code builds · suite green · permissions enforced (deny-by-default) · unsafe input handled & tested ·
secrets protected · logs redacted · dangerous actions HITL-gated · rollback possible · changed files
listed · remaining risks documented · **every "done" backed by evidence.**
