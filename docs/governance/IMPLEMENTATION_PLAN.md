# IMPLEMENTATION_PLAN — module technical design (M1–M5)
**Generated:** 2026-06-25 · part of [governance doc-set](SECURITY_COMPLIANCE_ROADMAP.md) · risks in [SECURITY_RISK_REGISTER.md](SECURITY_RISK_REGISTER.md) · atomic cards in [CLAUDE_TASKS.md](CLAUDE_TASKS.md)

> Design-level specs for each module: how it's built, what it touches, how it's proven, how it
> rolls back. **Principles:** deny-by-default · config-driven (no hardcoded values) · additive +
> reversible · enforce server-side · every "done" backed by evidence.

---

## M1 — See & Stabilise

### 1. Route-auth scanner  ·  Sev SR-04  ·  size M
- **Goal:** machine-prove every sensitive Express route is gated or explicitly public.
- **Inspect:** [backend/server.js](../../backend/server.js) router mounts; `requireAuth` ([server.js:325](../../backend/server.js#L325)); `backend/routes/*`; `backend/infra/rbac/middleware.js`.
- **Create:** `backend/security/route_auth_scanner.js`; CI job in `.github/workflows/ci.yml`.
- **Approach:** load the app, walk `app._router.stack` (+ mounted sub-routers) → for each route record method, path, and the middleware chain; classify `protected` if chain includes `requireAuth`/RBAC, else `public`. A **config allowlist of intentionally-public routes** lives in `security.yml` (no hardcoded paths). Fail if a non-allowlisted route lacks auth. Emit JSON evidence report.
- **Risk:** dynamic mounts missed → mitigate by asserting total scanned ≈ known handler count; first run **non-blocking** to baseline, then blocking.
- **Tests:** unit (mock router → unprotected sensitive route fails; allowlisted public passes). **Verify:** `node backend/security/route_auth_scanner.js` exits non-zero on a seeded unprotected route.
- **Rollback:** delete file + CI job (additive). **Reason:** SR-04 broken-access-control is OWASP #1.

### 2. shell_exec hardening  ·  SR-02  ·  size M
- **Goal:** replace bypassable blocklist with an allowlist; remove shell metachar injection.
- **Inspect/modify:** [runtime/tools/implementations/shell_exec.py](../../runtime/tools/implementations/shell_exec.py); add allowlist to `runtime/config/security.yml`.
- **Approach:** `shell=False`; `shlex.split`; resolve `argv[0]` basename; **allowlist sourced from `security.yml`** (`shell_exec.allowed_commands`) — no hardcoded list. Reject shell metacharacters (`; | & > < $() \` && || \n`) under the strict policy (open decision: strict-no-shell vs controlled-pipelines). Keep existing env-sanitisation + cwd + timeout. Callers: `runtime/tools/react_tools.py`, `runtime/engine/agent/agent_loop.py`.
- **Risk:** breaks `react_coder` if allowlist too tight → allowlist is config (owner-tunable); default = read-only inspection + dev toolchain.
- **Tests:** `tests/test_shell_exec_hardening.py` — allowed runs; disallowed blocked; metachar blocked; `os.environ` secret absent from child env. **Verify:** `python3 -m pytest tests/test_shell_exec_hardening.py -q`.
- **Rollback:** revert single file + config key. **Reason:** SR-02; sandbox metachar injection.

### 3. Skill-router precedence fix  ·  size M  ·  (closes confirmed test failure)
- **Goal:** generic goals reach the intended tool-composing chain, not an over-eager 859-skill match.
- **Inspect/modify:** [runtime/skills/catalog.py](../../runtime/skills/catalog.py) `_match_executable_skillbase` (L273) + `dispatch_for_goal` (L301); test [tests/test_skill_chain.py](../../tests/test_skill_chain.py).
- **Approach:** step-0 (deepened-skillbase match) currently grabs "research the market…" → `competitive_positioning_analyzer` before the tool-composing `_exec_skills` chain runs. Fix = raise step-0 specificity (require a higher field-weighted score and/or a minimum distinct-token match), OR consult the exec-skill registry first for high-confidence generic goals. Add a regression assertion for the intended route.
- **Risk:** tightening may shift other routings → run full skill-chain suite; assert the other 4 cases unchanged.
- **Tests/Verify:** `python3 -m pytest tests/test_skill_chain.py -q` green. **Rollback:** revert catalog.py change. **Reason:** correctness + G3 (no fake routing).

---

## M2 — Capability Firewall

### 4. Agent capability manifest + enforcement  ·  SR-01, SR-12  ·  size L
- **Goal:** no agent exceeds its authority; deny-by-default; consequential actions gated + audited.
- **Inspect:** `runtime/config/agent_capabilities.json`; `runtime/core/hitl_gate.py`; `runtime/tools/registry.py`; `runtime/tools/react_tools.py`; `runtime/engine/agent/agent_loop.py`; `state/audit.db`.
- **Create/modify:** manifest schema (extend `agent_capabilities.json` or new `agent_capabilities_manifest.json`): `allowed_tools`, `forbidden_tools`, `data_access{pii,secrets}`, `network{allowed,domains_allowlist}`, `budget{max_tokens,max_runtime_s}`, `human_approval_required_for[]`, `logging`, `risk_level`. Enforcement hook at tool-dispatch in the registry: **unmanifested agent or unlisted tool → blocked** (fail-closed); approval-required actions → `hitl_gate`; every decision → `audit.db`.
- **Approach:** config-driven, central enforcement (no duplicated checks); generate default manifests for all 127 agents from existing `risk_level`, then tighten high-risk ones by hand.
- **Risk:** silent over-allow if manifest missing → default-deny + CI lint that every registered agent has a manifest.
- **Tests:** forbidden tool blocked + audited; budget exceeded → stop; approval-required → HITL. **Verify:** `pytest tests/security/test_capability_firewall.py -q`.
- **Rollback:** feature flag (`CAPABILITY_FIREWALL=1`); revert flag. **Reason:** OWASP LLM06 Excessive Agency.

### 5. Production-mode enforcement  ·  SR-07, SR-06, SR-08  ·  size M
- **Goal:** one mode switch (`dev-local`/`desktop-local`/`staging`/`production`) hard-gates unsafe config.
- **Inspect:** `NODE_ENV` (15 sites); `backend/infra/sandbox/executor.js`; helmet CSP ([server.js:457](../../backend/server.js#L457)).
- **Create:** `backend/security/runtime_mode.js` (+ python equiv) reading env → gate registry: `SANDBOX_REQUIRE_DOCKER`, `WORKSPACE_PUBLIC=false`, strict-CSP — **active only in staging/production**; built now, **unforced on local-desktop**.
- **Risk:** over-gating breaks local dev → gates no-op in local modes; negative tests prove they fire in prod.
- **Tests/Verify:** `AI_ENV=production` boot without Docker → hard-fail; local boot unaffected. **Rollback:** mode module additive. **Reason:** safe-by-default at every stage; a switch, not a rebuild.

### 6. Workspace isolation  ·  SR-06  ·  size M
- **Goal:** `/workspace` cannot serve unsanitised agent HTML/JS to a trusting context.
- **Inspect/modify:** [server.js:528](../../backend/server.js#L528) static mount; media CSP ([media.js:170](../../backend/routes/media.js#L170)).
- **Approach:** signed preview token (HMAC, short TTL) + content-type allowlist + CSP-sandbox header + no-listing (already `index:false`). Enforced in prod mode; available locally. **Reason:** SR-06.
- **Tests/Verify:** unsigned request 401 in prod mode; disallowed content-type rejected. **Rollback:** revert mount.

### 7. No-fake-success contract  ·  SR-10  ·  size M
- **Goal:** every success carries evidence; promote `tool_registry`'s pattern system-wide.
- **Inspect:** `runtime/core/tool_registry.py`.
- **Create:** shared schema `{ok,status:blocked|failed|partial|success,evidence[],missing_requirements[],next_safe_action,user_approval_required}` + helper; adopt in the 5 default exec skills + agent results; CI lint flags `status:success` with empty `evidence`.
- **Tests/Verify:** lint fails a seeded evidence-less success. **Rollback:** schema additive. **Reason:** G3.

---

## M3 — Prove Safe Under Attack

### 8. Adversarial test suites  ·  SR-03, SR-05, SR-16, SR-13  ·  size L
- **Create** `tests/security/`: prompt-injection/RAG-poisoning (malicious doc/page/memory must not override policy or trigger forbidden tools); tenant-leak (fuzz JWT `tenant_id`; A can't read B's deals/tasks/memory/audit); sandbox-escape (path traversal, env exfil, metachar break-out; process-fallback forbidden in prod; `setrlimit`+secret-strip hold); upload-validation (magic-byte content-type, path normalisation, quarantine).
- **Approach:** deterministic fixtures, **no live network**. **Verify:** `pytest tests/security/ -q` green & required in CI. **Reason:** treat all external input as hostile.

### 9. CI security gate hardening  ·  SR-09, SR-13  ·  size M
- **Modify** `.github/workflows/ci.yml`: bandit **blocking** (drop `\|\| true`); add gitleaks/trufflehog secret-scan; wire route-auth scanner + adversarial suites + capability-manifest lint + no-fake-success lint as **required** checks; emit JSON/MD evidence report per build. Keep CodeQL + Black Duck.
- **Risk:** flakiness erodes trust → suites deterministic; gates start as warnings then flip blocking once baseline clean. **Rollback:** revert workflow. **Reason:** SR-09 logging/alerting + supply-chain.

---

## M4 — Compliance Center (core)  ·  size L
- **AI-Act classifier:** per-feature prohibited/high/limited/minimal + obligations; surfaced via governance subsystem (`backend/infra/governance/`, `runtime/core/governance_digest.py`); **advisory, human-reviewed**.
- **Data-processing register:** what data, why, legal basis, retention, storage — wired to real stores (deals/tasks/memory/knowledge).
- **Audit export:** agent actions, approvals, model calls, data access → export (reuse `state/audit.db` + `governance_digest.py`); ties to existing GDPR Art.15/20 ([test_compliance_safeguards.py](../../tests/test_compliance_safeguards.py)).
- **Consent/retention:** extend existing data-subject export/erase + retention timers.
- **Verify:** extend `tests/test_compliance_safeguards.py`; audit-export round-trip. **Depends on:** M2 (audit), M3 (tenant isolation proven). See [LEGAL_READINESS_REGISTER.md](LEGAL_READINESS_REGISTER.md).

## M5 — Legal Drafts + Scale-Readiness  ·  size M
- **Draft legal generators:** ToS (liability limits), Privacy, per-feature AI disclaimer, "do-not-use-for" policy — **every output stamped "DRAFT — requires human/legal review"; nothing ships unreviewed.**
- **Scale-readiness (documented, switch-ready, not forced):** Postgres migration path from JSON/SQLite (`runtime/core/file_lock.py` → DB); observability via existing Prometheus `/metrics`; prod go-live checklist; ZAP DAST playbook.
- **Verify:** generated policy asserts DRAFT banner; checklist walkthrough. **Reason:** close legal loop + de-risk growth without committing to remote now.

---

## Sequencing & dependencies
`M1(scanner, shell_exec, skill-fix, docs)` → `M2(firewall ⇠ needs M1 scanner+docs; mode; workspace; contract)`
→ `M3(suites ⇠ assert against M2 firewall; CI gate)` → `M4(⇠ needs M2 audit + M3 isolation proof)` → `M5(⇠ needs M4)`.
Every module is additive/flag-gated → per-module `git revert` is the rollback.
