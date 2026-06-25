# CLAUDE_TASKS — Atomic Task Cards
**Source of truth:** [SECURITY_COMPLIANCE_ROADMAP](SECURITY_COMPLIANCE_ROADMAP.md) (M1–M5) · **Grounding:** [SYSTEM_MAP](SYSTEM_MAP.md) · **Generated:** 2026-06-25 (read-only inspection)

> Pick-up-and-execute cards. One outcome each, in dependency order. A card is **done** only with the **Verify** evidence in hand (CLAUDE.md rule 30). `(verify)` = path/line inferred, confirm before editing. Operating rules: deny-by-default · no hardcoded values (config from `security.yml`/manifests) · smallest safe change · additive + reversible · all external input hostile.

**Legend:** Size `S`≤½d · `M`≤2d · `L`>2d · **Status** `todo` until Verify passes · IDs `M<n>-T<k>`.

---

## Milestone M1 — See & Stabilise (Jul 2026)
Goal: visibility up, in-flight work closed, suite green, route-auth machine-proven. Exit: 6 docs reviewed · `npm test` green · route-auth scanner live.

---

### M1-T1 — Governance doc-set complete (6 docs)
- **Size:** M · **Milestone:** M1 · **Depends on:** —
- **Goal:** All six governance registers exist, cross-link correctly, and are reviewed — the security/legal work targets reality, not assumptions.
- **Files to inspect:** [docs/governance/SECURITY_COMPLIANCE_ROADMAP.md](SECURITY_COMPLIANCE_ROADMAP.md), [SYSTEM_MAP.md](SYSTEM_MAP.md), [SECURITY_RISK_REGISTER.md](SECURITY_RISK_REGISTER.md), [LEGAL_READINESS_REGISTER.md](LEGAL_READINESS_REGISTER.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **Files to modify/create:** `docs/governance/TEST_MATRIX.md` (missing), this `CLAUDE_TASKS.md`
- **Steps:** 1. Confirm 5 existing docs present + linked from the roadmap index. 2. Author `TEST_MATRIX.md` (per-milestone suites → assertion → evidence), matching house style. 3. Cross-link sibling docs (bare filename) and repo files (`../../`). 4. Submit set for Lars review.
- **Verify:** `ls docs/governance/*.md` lists 6 files; every roadmap index link resolves (`grep -o '[A-Z_]*\.md' SECURITY_COMPLIANCE_ROADMAP.md` → each exists); review sign-off recorded.
- **Rollback:** Docs are additive; `git rm` new file. Zero runtime impact.
- **Security/legal reason:** Grounded registers are the precondition for every later control; prevents fixing imagined surfaces (G1–G5).
- **Status:** todo

---

### M1-T2 — Reproduce + green the full suite (baseline)
- **Size:** S · **Milestone:** M1 · **Depends on:** —
- **Goal:** A known-good, reproducible baseline so every later card has a regression floor. **Done 2026-06-25 (full run, 75 min): 3 failed · 3215 passed · 194 skipped.** Failures: skill-router (→T3); `test_companion_runtime.py::test_voice_channel_populates_voice_summary` + `test_companion_adapters.py::test_research_deep_start_does_not_block` (→T4).
- **Files to inspect:** [.github/workflows/ci.yml](../../.github/workflows/ci.yml), [package.json](../../package.json), `requirements-test.txt`, `tests/`
- **Files to modify/create:** none (record-only; failures feed T3/T4)
- **Steps:** 1. `pip install -r requirements-test.txt`. 2. Run `npm test` (pytest + `agent_selftest.py`). 3. Capture pass/fail per test; flag the skill-router failure (→ T3) and the voice-summary + research-deep-start failures (→ T4). 4. Save raw output as evidence.
- **Verify:** `npm test` output stored; failing test names enumerated; baseline count recorded (becomes the floor for T3–T5).
- **Rollback:** Read-only. N/A.
- **Security/legal reason:** No fake success — every later "done" is measured against a real, reproduced baseline (G3).
- **Status:** todo

---

### M1-T3 — Fix skill-router precedence (`_match_executable_skillbase` over-matches)
- **Size:** M · **Milestone:** M1 · **Depends on:** M1-T2
- **Goal:** Generic goals route to the **tool-composing chain**, not a coincidentally-named domain skill — e.g. `"research the market"` → `market_research` (`via: skill_catalog_tools`), **not** `competitive_positioning_analyzer` via description-token match.
- **Files to inspect:** [runtime/skills/catalog.py](../../runtime/skills/catalog.py) (`_match_executable_skillbase` L273–299, `dispatch_for_goal` L301–367, `find_for_goal` L237–240), [tests/test_skill_chain.py](../../tests/test_skill_chain.py) (existing assertion L17–27 already expects `skill_catalog_tools` for this goal)
- **Files to modify/create:** `runtime/skills/catalog.py`, `tests/test_skill_chain.py`
- **Steps:** 1. Reproduce: assert current dispatch of `"research the market for a saas product"` resolves via executable-skillbase (description match) instead of `skill_catalog_tools`. 2. Tighten step-0 match — require an **id/name (weight-3) hit**, not description-only, before a v2.0 SkillBase wins; OR consult the exec-skill registry (`find_for_goal`/`_exec_skills`) first and only fall through to `_match_executable_skillbase` when no tool-composing skill matches. 3. Keep deny-of-fake-success and HITL library-path contract (L327–333) intact. 4. Add regression test in `tests/test_skill_chain.py` pinning `via == "skill_catalog_tools"` for ≥2 generic goals + one that *should* hit a domain skill (no over-correction).
- **Verify:** `python3 -m pytest tests/test_skill_chain.py -q` green incl. new cases; existing L17 test still passes.
- **Rollback:** `git revert` the catalog.py hunk; matching reverts to prior precedence (behaviour-only change, no schema/state).
- **Security/legal reason:** Correct routing keeps consequential goals inside the validated tool chain (auditable, HITL-gated) instead of an LLM-prompt path that can silently skip side-effect controls (G2/G3).
- **Status:** todo

---

### M1-T4 — Fix the remaining 2 failing tests (voice-summary + research-deep-start)
- **Size:** S · **Milestone:** M1 · **Depends on:** M1-T2
- **Goal:** Suite is fully green; the two remaining failures — `tests/test_companion_runtime.py::test_voice_channel_populates_voice_summary` and `tests/test_companion_adapters.py::test_research_deep_start_does_not_block` — are fixed without masking a real defect.
- **Files to inspect:** `tests/test_companion_runtime.py`, `tests/test_companion_adapters.py`, and the companion modules they exercise (`runtime/companion/`)
- **Files to modify/create:** the failing tests and/or their target modules (smallest safe surface)
- **Steps:** 1. Reproduce each in isolation (`pytest tests/test_companion_runtime.py::test_voice_channel_populates_voice_summary -q`; same for the adapters one) — confirm not state-leak/ordering flakes. 2. Decide per failure: product bug vs stale test. 3. Fix the smallest safe surface; if a test was wrong, correct the assertion and note why. 4. Re-run each file, then full suite.
- **Verify:** `python3 -m pytest tests/<file>.py -q` green; full `npm test` green (no `-x` early-exit).
- **Rollback:** `git revert` the fix hunk.
- **Security/legal reason:** A green suite is the regression floor every gate (T6) builds on; never disable to pass (G3).
- **Status:** todo

---

### M1-T5 — Harden `shell_exec` (drop `shell=True`, shlex parse, config-sourced argv[0] allowlist)
- **Size:** M · **Milestone:** M1 · **Depends on:** M1-T2
- **Goal:** Shell tool cannot be injected or used to run arbitrary binaries — `argv` is parsed (no shell metachar evaluation) and `argv[0]` basename must be on an **allowlist sourced from `security.yml`** (no hardcoded list).
- **Files to inspect:** [runtime/tools/implementations/shell_exec.py](../../runtime/tools/implementations/shell_exec.py) (currently `shell=True` L66 + blocklist regex L16–30, env-strip L32–56 already present), [runtime/config/security.yml](../../runtime/config/security.yml) (no shell-allowlist section yet — must add)
- **Files to modify/create:** `runtime/tools/implementations/shell_exec.py`, `runtime/config/security.yml` (add e.g. `tools.shell_exec.allowed_commands: [...]`), new unit test `tests/test_shell_exec.py` (verify)
- **Steps:** 1. Add `tools.shell_exec.allowed_commands` to `security.yml` (overridable via `security.local.yml`). 2. In `shell_exec`: `shlex.split(command)` → reject empty/`shell` operators; resolve `os.path.basename(argv[0])`; deny if not in the loaded allowlist (deny-by-default, fail-closed). 3. Replace `subprocess.run(..., shell=True)` with `shell=False` passing the argv list; keep cwd-scope, env-strip, timeout cap, output truncation. 4. Keep blocklist regex as defence-in-depth. 5. Unit tests: allowed cmd runs; metachar (`;`, `|`, `$()`, backticks) blocked; non-allowlisted basename blocked; traversal/`sudo` blocked; missing-config → deny.
- **Verify:** `python3 -m pytest tests/test_shell_exec.py -q` green; a manual `shell_exec("echo hi; rm -rf .")` returns `ok:false` (blocked).
- **Rollback:** `git revert` tool hunk + remove `security.yml` key; tool returns to blocklist-only (degraded but functional).
- **Security/legal reason:** Closes command-injection / arbitrary-binary execution (CLAUDE.md §7 sandbox, OWASP A03). Allowlist-from-config satisfies "no hardcoded values" (G1).
- **Status:** todo

---

### M1-T6 — Route-auth scanner (`route_auth_scanner.js`) + CI wiring
- **Size:** L · **Milestone:** M1 · **Depends on:** M1-T2 (green floor)
- **Goal:** Every sensitive Express route is machine-proven to require auth or be explicitly allowlisted-public — closing the "806 `requireAuth` refs vs 782 handlers, not machine-proven" gap (SYSTEM_MAP §3).
- **Files to inspect:** [backend/server.js](../../backend/server.js) (mounts L528–806; `requireAuth` L329), [backend/infra/rbac/middleware.js](../../backend/infra/rbac/middleware.js), [.github/workflows/ci.yml](../../.github/workflows/ci.yml), risk-ranked surfaces (SYSTEM_MAP §2: `secrets`,`remote-compute`,`compute`,`sandbox`,`forge`,`evolution`,`deployment`,`orders`,`marketplace`,`memory`,`rag`)
- **Files to modify/create:** `backend/security/route_auth_scanner.js` (new), `runtime/config/security.yml` or sibling config for the **public-route allowlist** (no hardcoded list), `.github/workflows/ci.yml` (new job), `tests/test_route_auth_scanner.js` (verify)
- **Steps:** 1. Walk the mounted Express router stack; enumerate `{method, path, middleware[]}`. 2. Load sensitive-prefix list + explicit public allowlist from config. 3. Flag any sensitive route whose middleware chain lacks `requireAuth` (and isn't allowlisted). 4. Exit non-zero on findings; emit a report artifact. 5. Wire a CI job **non-blocking first** (`continue-on-error`), confirm zero false-positives over a sprint, then **flip to blocking** (add to `all-green` `needs`).
- **Verify:** `node backend/security/route_auth_scanner.js` exits 0 with current tree (or lists genuinely-public routes only); CI job present; after flip, an injected unauthed sensitive route fails CI.
- **Rollback:** Remove CI job (revert workflow) → advisory only; scanner script is read-only, safe to keep.
- **Security/legal reason:** Deny-by-default, CI-verified authorization is North-Star **G1**; turns an unproven count into a hard gate.
- **Status:** todo

---

### M1-T7 — Confirm JWT algorithm pins (regression lock)
- **Size:** S · **Milestone:** M1 · **Depends on:** —
- **Goal:** All HMAC verify sites stay pinned to `algorithms:['HS256']` (already applied at 10 sites) — locked against regression / `alg:none` confusion.
- **Files to inspect:** server.js, tenancy.js, `rbac/middleware.js`, `ws-auth.js`, `token-manager.js` (×3), `health.js`, `oidc-verify.js` (10 sites per SYSTEM_MAP §3); OIDC asymmetric path pins RS/ES
- **Files to modify/create:** `tests/test_jwt_alg_pin.js` (verify) — assertion/guard only; no code change expected
- **Steps:** 1. Grep every `jwt.verify(` for an explicit `algorithms:` option. 2. Add a guard test asserting each call passes a non-empty algorithms array (HS256 for HMAC, RS/ES for OIDC). 3. (Optional) lint rule flagging `jwt.verify` without `algorithms`.
- **Verify:** `grep -rn "jwt.verify" backend/` → every hit has `algorithms`; `node tests/test_jwt_alg_pin.js` green.
- **Rollback:** Remove guard test (advisory). No production code touched.
- **Security/legal reason:** Prevents algorithm-confusion / `alg:none` auth bypass (OWASP A07); keeps an applied fix from silently regressing (G1).
- **Status:** todo

---

## Milestone M2 — Capability Firewall (Aug 2026)
Goal: no agent exceeds its authority; production-mode scaffold. Exit: manifests enforced at dispatch; mode gates pass negative tests.

---

### M2-T1 — Per-agent capability manifest schema
- **Size:** M · **Milestone:** M2 · **Depends on:** M1-T6
- **Goal:** Each agent declares a bounded contract (`allowed_tools`, `forbidden_tools`, `data_access`, `network` allowlist, `budget`, `human_approval_required_for`, `logging`, `risk_level`) extending the existing catalog.
- **Files to inspect:** [runtime/config/agent_capabilities.json](../../runtime/config/agent_capabilities.json), `runtime/config/agent_behavior_templates.json` (verify), [runtime/core/hitl_gate.py](../../runtime/core/hitl_gate.py)
- **Files to modify/create:** `runtime/config/agent_capabilities.json` (extend), manifest schema + loader (verify), manifest-lint test
- **Steps:** 1. Define the manifest fields + JSON schema. 2. Backfill all 127 agents with conservative deny-by-default defaults. 3. Add a lint asserting every agent dir has a valid manifest.
- **Verify:** manifest-lint passes for all 127 agents; schema-invalid manifest fails the lint.
- **Rollback:** Revert JSON; loader treats missing manifest as fully-denied (fail-closed) or prior behaviour behind a flag.
- **Security/legal reason:** OWASP **LLM06 Excessive Agency** control; foundation of G2.
- **Status:** todo

---

### M2-T2 — Enforce manifests at dispatch (deny-by-default)
- **Size:** L · **Milestone:** M2 · **Depends on:** M2-T1
- **Goal:** No tool/network/budget call exceeds the agent's manifest; consequential actions route via HITL; every decision audited.
- **Files to inspect:** [runtime/tools/registry.py](../../runtime/tools/registry.py), [runtime/tools/react_tools.py](../../runtime/tools/react_tools.py), [runtime/engine/agent/agent_loop.py](../../runtime/engine/agent/agent_loop.py), [runtime/core/hitl_gate.py](../../runtime/core/hitl_gate.py), `state/audit.db`
- **Files to modify/create:** the three dispatch modules above; audit-write helper; enforcement tests
- **Steps:** 1. At tool dispatch, load caller manifest; deny if tool ∉ `allowed_tools` or ∈ `forbidden_tools`. 2. Enforce network allowlist + budget ceiling. 3. Route `human_approval_required_for` actions through `hitl_gate`. 4. Append every allow/deny to `state/audit.db`. 5. Tests: forbidden-tool denied; over-budget denied; approval-gated action blocks until approved.
- **Verify:** enforcement tests green; audit rows present for allow + deny; an agent calling a forbidden tool is denied + logged.
- **Rollback:** Feature-flag enforcement OFF → log-only mode (still records, doesn't block).
- **Security/legal reason:** Turns the manifest into a real firewall — **G2** ("no agent exceeds its authority").
- **Status:** todo

---

### M2-T3 — Production-mode scaffold (env-driven gates)
- **Size:** M · **Milestone:** M2 · **Depends on:** M2-T1
- **Goal:** Four modes (`dev-local`/`desktop-local`/`staging`/`production`) from env; `SANDBOX_REQUIRE_DOCKER`, no-public-`/workspace`, strict-CSP gates active **only** in staging/prod.
- **Files to inspect:** [backend/server.js](../../backend/server.js), [backend/infra/sandbox/executor.js](../../backend/infra/sandbox/executor.js) (Docker→Process fallback), [runtime/config/security.yml](../../runtime/config/security.yml)
- **Files to modify/create:** mode resolver (verify), `backend/server.js`, sandbox executor gate, mode config
- **Steps:** 1. Resolve mode from env (default local). 2. In staging/prod: hard-fail if Docker sandbox unavailable; disable public `/workspace`; enforce strict CSP. 3. Local modes keep current behaviour. 4. Negative tests per mode.
- **Verify:** mode negative tests pass (prod mode + no Docker → boot fails closed; prod mode → `/workspace` not public).
- **Rollback:** Default mode = local; gates inert. Revert resolver.
- **Security/legal reason:** Defensive remote-exposure gates built now, unforced locally (roadmap §2 decision) — supports G1/G4 at scale.
- **Status:** todo

---

### M2-T4 — `/workspace` isolation (signed token + content-type allowlist + CSP sandbox)
- **Size:** M · **Milestone:** M2 · **Depends on:** M2-T3
- **Goal:** Agent-generated HTML/JS at `/workspace` can't be served unauthenticated or execute as trusted — signed preview token, content-type allowlist, CSP sandbox header.
- **Files to inspect:** [backend/server.js](../../backend/server.js) **L528** (`app.use('/workspace', express.static(...))` — public now), [backend/routes/media.js](../../backend/routes/media.js) (`unsafe-inline` CSP L170 verify)
- **Files to modify/create:** `backend/server.js` (workspace handler), signed-token util (verify), tests
- **Steps:** 1. Gate `/workspace` behind a signed, short-lived preview token. 2. Allowlist served content-types. 3. Set `Content-Security-Policy: sandbox` + frame restrictions. 4. Tests: no/invalid token → 401/403; disallowed type rejected.
- **Verify:** request without token → denied; with valid token → served with sandbox CSP header.
- **Rollback:** Revert to `express.static` public (current). Behaviour-only.
- **Security/legal reason:** Stored-XSS / drive-by from agent output (SYSTEM_MAP §7 gap); G4.
- **Status:** todo

---

### M2-T5 — Promote no-fake-success contract to shared module
- **Size:** S · **Milestone:** M2 · **Depends on:** M2-T2
- **Goal:** A single shared "honest result" contract (only real `executed`/`success` count) reused everywhere, promoted from `tool_registry.py`.
- **Files to inspect:** [runtime/core/tool_registry.py](../../runtime/core/tool_registry.py), [runtime/skills/catalog.py](../../runtime/skills/catalog.py) (`AgentDispatchSkill.execute` L67–84 already encodes the rule)
- **Files to modify/create:** shared contract module (verify), call-sites that hand-roll the check, contract test
- **Steps:** 1. Extract the canonical status→ok mapping. 2. Replace duplicated inline checks with the shared helper. 3. Contract test pins: `unknown_action`/`error` → `failed`, never fabricated success.
- **Verify:** contract test green; `grep` shows call-sites import the shared helper (no duplicate logic).
- **Rollback:** Revert extraction; inline checks remain.
- **Security/legal reason:** Eliminates silent-success drift across modules — **G3**.
- **Status:** todo

---

## Milestone M3 — Prove Safe Under Attack (Sep 2026)
Goal: untrusted input fails closed; CI gate blocks. Exit: injection/tenant-leak/sandbox-escape suites green & blocking.

---

### M3-T1 — Prompt-injection / RAG-poisoning suite
- **Size:** L · **Milestone:** M3 · **Depends on:** M2-T2
- **Goal:** Proven that retrieved/web/memory content cannot override system policy (data ≠ command authority).
- **Files to inspect:** `runtime/memory/` (vector_store, memory_router, unified_store — SYSTEM_MAP §8), [runtime/core/auto_research_agent.py](../../runtime/core/auto_research_agent.py), `runtime/core/source_trust.py` (verify)
- **Files to modify/create:** `tests/test_prompt_injection.py` (verify), poisoned-fixture corpus
- **Steps:** 1. Seed memory/RAG with injection payloads ("ignore previous instructions", tool-call smuggling). 2. Assert the agent does not execute embedded instructions / escalate tools. 3. Assert source-trust labelling holds.
- **Verify:** `pytest tests/test_prompt_injection.py -q` green; injected command is treated as data, not executed.
- **Rollback:** Tests are additive.
- **Security/legal reason:** OWASP **LLM01 Prompt Injection** — top residual risk (SYSTEM_MAP summary #2); G4.
- **Status:** todo

---

### M3-T2 — Tenant-leak fuzz suite
- **Size:** M · **Milestone:** M3 · **Depends on:** M2-T2
- **Goal:** Tenant A can never read/write tenant B; `tenant_id` swaps fail closed.
- **Files to inspect:** [runtime/core/tenancy.py](../../runtime/core/tenancy.py), `tenant_middleware.py` + [backend/tenancy.js](../../backend/tenancy.js) (verify), `runtime/core/file_lock.py`
- **Files to modify/create:** `tests/test_tenant_leak.py` (verify)
- **Steps:** 1. Create 2 tenants with distinct data. 2. Fuzz `tenant_id` in JWT/context across state reads/writes. 3. Assert `A != B` isolation and forged-tenant denial.
- **Verify:** `pytest tests/test_tenant_leak.py -q` green; cross-tenant read denied.
- **Rollback:** Additive.
- **Security/legal reason:** Multi-tenant data isolation (SYSTEM_MAP §4 gap); GDPR confidentiality; G4.
- **Status:** todo

---

### M3-T3 — Sandbox-escape suite
- **Size:** M · **Milestone:** M3 · **Depends on:** M1-T5, M2-T3
- **Goal:** Process-fallback forbidden in prod; `setrlimit` + env-secret-strip hold under hostile code.
- **Files to inspect:** [backend/infra/sandbox/executor.js](../../backend/infra/sandbox/executor.js), [runtime/core/sandbox_manager.py](../../runtime/core/sandbox_manager.py), shell_exec (post M1-T5)
- **Files to modify/create:** `tests/test_sandbox_escape.py` / `.js` (verify)
- **Steps:** 1. Assert prod mode refuses ProcessSandbox fallback. 2. Assert rlimits cap CPU/mem; secrets stripped from child env. 3. Attempt path-traversal / env-exfil → blocked.
- **Verify:** escape tests green; secret env var absent in sandbox; fallback denied in prod mode.
- **Rollback:** Additive.
- **Security/legal reason:** Sandbox escape → host compromise (CLAUDE.md §7); G4.
- **Status:** todo

---

### M3-T4 — Upload-validation suite
- **Size:** S · **Milestone:** M3 · **Depends on:** —
- **Goal:** Uploads validated by **magic bytes** (not extension) with path normalisation; malicious/oversized/traversal rejected.
- **Files to inspect:** upload handlers (verify), `limits.max_file_upload_size_mb` in [security.yml](../../runtime/config/security.yml)
- **Files to modify/create:** `tests/test_upload_validation.py` (verify); validator hardening if gaps found
- **Steps:** 1. Content-type via magic bytes. 2. Normalise + reject `../` traversal. 3. Enforce size cap. 4. Tests for spoofed-extension, traversal, oversize.
- **Verify:** upload tests green; `.php` renamed `.png` rejected by magic-byte check.
- **Rollback:** Additive (+ revert any validator hardening hunk).
- **Security/legal reason:** Malicious-upload / path-traversal (CLAUDE.md §8); G4.
- **Status:** todo

---

### M3-T5 — CI gate hardening (bandit blocking + gitleaks + suites required + evidence)
- **Size:** M · **Milestone:** M3 · **Depends on:** M3-T1, M3-T2, M3-T3, M3-T4
- **Goal:** Security gate **blocks** on failure: bandit blocking (drop `|| true`), gitleaks secret-scan added, adversarial suites wired as required, evidence report emitted.
- **Files to inspect:** [.github/workflows/ci.yml](../../.github/workflows/ci.yml) (`bandit ... -ll -q || true` **L196**, `continue-on-error: true` **L182/L197**, `all-green` `needs` **L205**)
- **Files to modify/create:** `.github/workflows/ci.yml`
- **Steps:** 1. Remove `|| true` + `continue-on-error` from the bandit job. 2. Add gitleaks secret-scan job. 3. Add M3-T1..T4 suites + M1-T6 scanner to required `all-green` `needs`. 4. Emit an aggregated evidence report artifact.
- **Verify:** an injected bandit HIGH or planted secret fails CI; `all-green` lists the new required jobs; report artifact present.
- **Rollback:** Re-add `continue-on-error` → advisory mode.
- **Security/legal reason:** Persistent gate that proves every future change safe (roadmap §4) — G1/G3/G4.
- **Status:** todo

---

## Milestone M4 — Compliance Center (core) (Oct 2026)
Goal: AI-Act classification + data register + audit export. Exit: classifier + register + export round-trip tested.

---

### M4-T1 — AI-Act feature classifier
- **Size:** M · **Milestone:** M4 · **Depends on:** M1-T1
- **Goal:** Every shipped feature classified `prohibited` / `high` / `limited` / `minimal` risk.
- **Files to inspect:** [LEGAL_READINESS_REGISTER.md](LEGAL_READINESS_REGISTER.md), `backend/infra/governance/` (verify), `runtime/agents/governance/` (verify)
- **Files to modify/create:** classifier module + `feature → risk-class` register (verify), tests
- **Steps:** 1. Enumerate features (esp. Money-Mode/outreach → limited-risk transparency). 2. Assign + justify a class each. 3. Lint: every shipped feature has a class.
- **Verify:** classifier lint green; 100% of shipped features classified (KPI table).
- **Rollback:** Additive docs/config.
- **Security/legal reason:** EU **AI-Act** obligation (G5).
- **Status:** todo

---

### M4-T2 — Data-processing register
- **Size:** S · **Milestone:** M4 · **Depends on:** M4-T1
- **Goal:** Authoritative record of what personal data is processed, where, why, retention.
- **Files to inspect:** [PRIVACY_ARCHITECTURE.md](../PRIVACY_ARCHITECTURE.md), `privacy.*_retention_days` in [security.yml](../../runtime/config/security.yml), `state/` data-flow map (SYSTEM_MAP §8/§9)
- **Files to modify/create:** data-processing register doc/config (verify)
- **Steps:** 1. Map each store → data categories, purpose, lawful basis, retention. 2. Cross-link to SYSTEM_MAP surfaces.
- **Verify:** register reviewed; every state store in SYSTEM_MAP §8/§9 appears.
- **Rollback:** Additive.
- **Security/legal reason:** GDPR **Art.30** record of processing (G5).
- **Status:** todo

---

### M4-T3 — Audit export (reuse `audit.db` + `governance_digest.py`)
- **Size:** M · **Milestone:** M4 · **Depends on:** M2-T2
- **Goal:** Compliance-grade audit export round-trips from the existing immutable trail.
- **Files to inspect:** `state/audit.db`, [runtime/core/governance_digest.py](../../runtime/core/governance_digest.py)
- **Files to modify/create:** export endpoint/CLI (verify), export round-trip test
- **Steps:** 1. Export audit records (signed/digested) in a portable format. 2. Round-trip verify integrity. 3. Scope export by tenant.
- **Verify:** export round-trip test green; digest verifies; tenant-scoped.
- **Rollback:** Read-only export; remove endpoint.
- **Security/legal reason:** Auditability / accountability (G5); reuses existing trail (no new sink).
- **Status:** todo

---

### M4-T4 — Consent / retention controls (extend GDPR safeguards)
- **Size:** M · **Milestone:** M4 · **Depends on:** M4-T2
- **Goal:** Consent capture + retention enforcement, extending the existing Art.15/20 tests.
- **Files to inspect:** [tests/test_compliance_safeguards.py](../../tests/test_compliance_safeguards.py) (Art.15/20 present), `privacy.*_retention_days` in [security.yml](../../runtime/config/security.yml)
- **Files to modify/create:** consent store + retention job (verify), extend `tests/test_compliance_safeguards.py`
- **Steps:** 1. Capture/record consent with source + timestamp. 2. Enforce retention windows (purge job). 3. Extend tests for consent + retention alongside Art.15/20.
- **Verify:** `pytest tests/test_compliance_safeguards.py -q` green incl. consent/retention cases.
- **Rollback:** Feature-flag retention job OFF; revert test additions.
- **Security/legal reason:** GDPR consent + storage-limitation (Art.5/6/7); G5.
- **Status:** todo

---

## Milestone M5 — Legal Drafts + Scale (Nov 2026)
Goal: draft policies + Postgres/observability path. Exit: DRAFT ToS/Privacy w/ review banner; scale plan signed.

---

### M5-T1 — Draft legal generators (ToS / Privacy / AI-disclaimer / do-not-use-for)
- **Size:** M · **Milestone:** M5 · **Depends on:** M4-T1, M4-T2
- **Goal:** Generate draft policies, **every output stamped** `"DRAFT — requires human/legal review"`.
- **Files to inspect:** [LEGAL_READINESS_REGISTER.md](LEGAL_READINESS_REGISTER.md), M4 classifier + data register outputs
- **Files to modify/create:** legal-generator module + templates (verify), generator test
- **Steps:** 1. Generators for ToS, Privacy, AI disclaimer, do-not-use-for. 2. Pull facts from M4 register/classifier. 3. Enforce the DRAFT banner on every output.
- **Verify:** generator test asserts the DRAFT banner is present in **every** generated document.
- **Rollback:** Additive.
- **Security/legal reason:** Legal text must never auto-ship as final — roadmap legal-scope decision (G5).
- **Status:** todo

---

### M5-T2 — Scale-readiness plan (Postgres path + observability + go-live + ZAP DAST)
- **Size:** L · **Milestone:** M5 · **Depends on:** M3-T5
- **Goal:** Signed plan to scale beyond JSON/SQLite with observability and a remote go-live checklist.
- **Files to inspect:** SYSTEM_MAP §1/§4 (JSON+SQLite state, file_lock), `/metrics` (port 8787) + `runtime/core/observability/` (verify), M2-T3 prod mode
- **Files to modify/create:** scale-readiness plan doc (verify); no production migration in this card
- **Steps:** 1. Document JSON/SQLite → Postgres migration path (tenant-aware). 2. Observability via existing `/metrics`. 3. Prod go-live checklist + ZAP DAST playbook.
- **Verify:** plan reviewed + signed by Lars; migration path + DAST playbook present.
- **Rollback:** Doc-only; no infra change.
- **Security/legal reason:** Scaling kept in mind (operating principle); DAST extends the gate to runtime (G4).
- **Status:** todo

---

## Dependency order (execution sequence)
`M1-T1 · M1-T2 · M1-T7` (parallel) → `M1-T3 · M1-T4 · M1-T5` → `M1-T6` →
`M2-T1` → `M2-T2 · M2-T3` → `M2-T4 · M2-T5` →
`M3-T1 · M3-T2 · M3-T3 · M3-T4` → `M3-T5` →
`M4-T1` → `M4-T2 · M4-T3` → `M4-T4` →
`M5-T1` → `M5-T2`.
