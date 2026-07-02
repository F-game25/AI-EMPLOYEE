# TEST_MATRIX — AI-EMPLOYEE / Nexus OS
**Generated:** 2026-06-25 · **Method:** static inspection + read-only pytest collection · **Milestone:** M1 (See & Stabilise) · part of [governance doc-set](SECURITY_COMPLIANCE_ROADMAP.md)

> Purpose: a grounded inventory of what the test suite **actually proves today** vs. what the
> [roadmap](SECURITY_COMPLIANCE_ROADMAP.md) still needs, so security work targets real gaps, not assumptions.
> Every "Existing tests" cell names a **real** `file::test` or `file` verified in the repo. Anything not yet
> built is marked **(planned)** and mapped to its milestone. Companion: [SYSTEM_MAP](SYSTEM_MAP.md).

## 1. How to run
| Command | Scope |
|---|---|
| `python3 -m pytest -q` | Full Python suite (pytest; `pytest.ini` adds coverage). Slow — prefer targeted runs locally. |
| `python3 -m pytest tests/test_<name>.py -q` | Single Python file (e.g. `tests/test_multitenant.py`). |
| `npm test` | pytest + `runtime/agents/agent_selftest.py` (see [package.json](../../package.json)). |
| `npm run lint` | Syntax-check all runtime Python modules. |
| `node tests/test_<name>.js` | One Node service test (each is a standalone script, e.g. `node tests/test_memory_trust_gate.js`). |
| CI: [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | `lint-python` → `test-python` (pytest `-x`, ignores `ui_automation`/`ui_e2e`) · `test-node` (8 scripts) · `build-frontend` · `security-scan` (bandit, advisory). Gate job `all-green` requires test-python + test-node + build-frontend. |

**CI runner env** (from `ci.yml`): `STATE_DIR=/tmp/ci-state`, `JWT_SECRET_KEY=ci-test-secret-not-real`, `STRICT_PIPELINE=0`, `PYTHONPATH=runtime:runtime/agents`. Install deps first: `pip install -r requirements-test.txt` (provides `pytest-timeout`).

## 2. Coverage matrix
Legend — **Coverage:** good = behaviour + negative paths proven · partial = some assertions, gaps remain · none = no test. **Blocking-in-CI?** now / target.

| Category | Existing tests (real file::test or file) | Coverage | Gap | Planned test | Milestone | Blocking-in-CI? (now/target) |
|---|---|---|---|---|---|---|
| **Auth / JWT** | `test_multitenant.py::test_extract_tenant_from_signed_jwt`, `::test_extract_tenant_rejects_forged_jwt`; `test_update_endpoint_auth.js` (remote→401); `test_boot_contract_routes.js` F1 (loopback bypass vs `requireAuth`) | good | No test asserts HS256-pinning at all 10 verify sites (SYSTEM_MAP §3); no refresh-rotation / expiry unit test | JWT-pin assertion + refresh-rotation test (planned) | M1 | partial / blocking |
| **RBAC / authorization** | `test_security.py::test_grant_and_check_permission`, `::test_no_permission_by_default`, `::test_revoke_permission`, `::test_require_without_permission_raises`, `::test_grant_unknown_permission_raises` | good | Tests cover the permission primitive, not `backend/infra/rbac/middleware.js` wired per-route | RBAC-middleware route-level deny tests (planned) | M2 | partial / blocking |
| **Route-auth coverage** | `test_boot_contract_routes.js` (F1 deny-by-default: remote→`requireAuth`); `test_update_endpoint_auth.js`; `test_file_upload.py::test_*_requires_auth` (upload/list/delete) | partial | No machine proof that **every** sensitive `/api/*` route is gated (806 `requireAuth` refs vs 782 handlers, unproven — SYSTEM_MAP §3) | Route-auth scanner: assert each sensitive route gated or explicitly public (planned) | **M1** | none / blocking |
| **Tenant isolation** | `test_multitenant.py` — `::test_multiple_tenants_isolated`, `::test_write_data_to_tenant`, `::test_file_structure_shows_isolation`, `::test_migrate_single_to_multitenant`, `::test_require_current_tenant`, +5 more (~12 total) | good | Happy-path isolation proven; no adversarial `tenant_id`-swap / cross-tenant fuzz | Tenant-leak fuzz (swap/forge `tenant_id`, assert no bleed) (planned) | M3 | partial / blocking |
| **Rate limiting** | `test_rate_limit_cache.js`; `test_security_hardening.py::test_makeRateLimit_exists_in_source`, `::test_makeRateLimit_is_used_not_just_defined` | partial | Source-presence + cache behaviour only; no live 429-on-burst integration test for auth routes | Auth-route burst→429 integration test (planned) | M2 | partial / blocking |
| **Sandbox execution** | `test_security.py::test_safe_code_passes`, `::test_eval_detected`, `::test_os_system_detected`, `::test_subprocess_detected`; `test_security_hardening.py::test_subprocess_run_fires`, `::test_eval_fires`, `::test_exec_fires` | partial | Validates static code-pattern detection, **not** runtime containment (DockerSandbox/ProcessSandbox, rlimits, no-net) — SYSTEM_MAP §6 | Sandbox-escape suite (break out of rootfs/net/rlimit; assert fail-closed) (planned) | M3 | partial / blocking |
| **shell_exec hardening** | `test_security.py::test_shell_injection_detected`; `test_security_hardening.py::test_subprocess_run_fires`, `::test_os_system_fires` | partial | `shell_exec.py` is `shell=True` + blocklist regex (SYSTEM_MAP §6); blocklist is bypassable, no allowlist proof | shell_exec → command allowlist + no-shell, with bypass-attempt tests (planned) | **M1** | partial / blocking |
| **Prompt-injection / RAG-poisoning** | `test_memory_trust.py::test_injection_is_hard_zeroed`; `test_memory_trust_gate.js` (`scoreFact: injection-bearing memory is hard-zeroed`, `gateMemories: drops … injection`) | partial | Trust-gate scores/drops poisoned **memory** facts, but no end-to-end proof retrieved RAG/web/file content can't become *instructions* (SYSTEM_MAP §8) | Prompt-injection / RAG-poisoning suite (retrieved content cannot override policy) (planned) | M3 | partial / blocking |
| **Memory / trust-gate** | `test_memory_trust.py` (8: `::test_gate_filters_and_caps`, `::test_gate_respects_limit`, `::test_kill_switch_passes_through_untouched`, `::test_trust_score_never_raises_on_garbage`, …); `test_memory_trust_gate.js` (8: ranking, cap, kill-switch, never-throws) | good | None major for the gate itself; depends on injection suite above for full assurance | — | — | partial / blocking |
| **Upload validation** | `test_file_upload.py::test_upload_disallowed_extension_returns_400`, `::test_upload_large_file_returns_413`, `::test_delete_path_traversal_blocked`, `::test_disallowed_extensions`, `::test_allowed_extensions`; `test_upload_unit.js` (ALLOWED_EXTENSIONS set, 50MB cap, route shape) | good | Extension/size/traversal covered; **content-type sniffing** (validate by content, not extension) not tested | Upload-validation suite: magic-byte type check + quarantine (planned) | M3 | good / blocking |
| **Secret scanning** | `test_security_hardening.py::test_dot_env_fires`, `::test_env_file_variant_fires`, `::test_normal_py_file_no_secret_rule`; egress side: `test_egress_guard.py::test_secret_blocked_to_every_remote_tier`, `test_compute_dispatch.js` (secret BLOCKED to every remote tier, PII redacted) | partial | Diff-rule fires on `.env`; **no repo-wide gitleaks scan in CI** (SYSTEM_MAP §9) | Secret-scan (gitleaks) as required CI gate (planned) | M3 | none / blocking |
| **SAST / SCA** | CI `security-scan` job runs **bandit** (`-r runtime/`, advisory) — [ci.yml](../../.github/workflows/ci.yml); `test_security_hardening.py` AST diff-policy patterns | partial | bandit is `continue-on-error: true` + `\|\| true` (non-blocking). **CodeQL and Black Duck/OSV SCA are not yet in `ci.yml`** | Add CodeQL + SCA (Black Duck/OSV) jobs; flip bandit blocking (planned) | M1→M3 | partial(advisory) / blocking |
| **Compliance / GDPR** | `test_compliance_safeguards.py` (~38): `::test_export_contains_chatlog_entries`, `::test_export_excludes_other_users`, `::test_erase_removes_chatlog_entries_for_user`, `::test_summary_legal_basis_article_15`, `::test_export_legal_basis_article_20`, `::test_gdpr_endpoints_registered`, + HITL approve/reject/timeout suite | good | Art.15/20 + HITL proven; **no AI-Act classifier / data-processing register / audit-export round-trip** (SYSTEM_MAP §12) | AI-Act classifier + data register + audit-export round-trip tests (planned) | M4 | good / blocking |
| **Capability firewall** | `test_hitl_coverage.py` (HITL gate as proxy: `::test_hitl_gate_blocks_outreach_before_deal_update`, `::test_emit_not_called_without_approval`, `::test_require_approval_called_once`); `test_compliance_safeguards.py::test_hitl_gate_triggered_for_high_risk_agents` | partial | HITL gates high-risk agents, but **no per-agent capability manifest** (allowed/forbidden tools, net allowlist, budget) enforced at dispatch — OWASP LLM06, SYSTEM_MAP §5 | Capability-manifest enforcement tests (deny forbidden tool/net/budget at dispatch) (planned) | M2 | partial / blocking |
| **No-fake-success contract** | `test_skill_chain.py::test_dispatch_no_skill_is_honest` (returns `no_skill`, not fabricated success); `test_tools_registry.py::test_call_tool_unknown_returns_error`, `::test_execute_missing_tool_returns_error`, `::test_execute_read_nonexistent_file` | partial | Honest-failure proven for skill-dispatch + tool registry; **no repo-wide lint** asserting every "done" carries evidence (roadmap G3) | No-fake-success contract lint across tools/skills/agents (planned) | M2 | partial / blocking |
| **Frontend / route-smoke** | `test_boot_contract_routes.js` (F2 boot-phase payload validation: bad-charset/over-long/CRLF rejected, detail truncated); `test_settings_routes.js`, `test_settings_frontend.js`; build-frontend job verifies `dist` output | partial | Boot-contract + settings smoke only; no broad SPA route / XSS-render smoke (`/workspace` serves agent HTML — SYSTEM_MAP §7) | Route-smoke + signed-preview-token / CSP-sandbox tests for `/workspace` (planned) | M2 | partial / blocking |
| **Regression (fixed bugs)** | `test_update_endpoint_auth.js` ("system update endpoint auth regression"); `test_robustness_safeguards.py`; `test_state_locking_c0.py` (concurrent-write lock); `test_security.py::test_forge_operation_with_injection_fails` | partial | Regressions added ad-hoc per fix; no convention requiring a regression test per security fix | Standing rule: each security fix ships a named regression test (process, not a single file) | M1 (ongoing) | partial / blocking |

## 3. Current suite status
Full-suite run (read-only, 2026-06-25, 75 min): **3 failed · 3215 passed · 194 skipped**. Ground truth — three real failures (the original audit said "2"; it was **3**):
1. `tests/test_skill_chain.py::test_dispatch_routes_to_executable_tool_skill` — skill router mis-routes the generic goal "research the market for a saas product"; expects `via == "skill_catalog_tools"` (tool-composing chain) but step-0 deepened-skill match (`_match_executable_skillbase`) grabs it first → `via == "executable_skillbase"`. Fix = routing precedence. → **M1**
2. `tests/test_companion_runtime.py::test_voice_channel_populates_voice_summary` — voice-summary assertion (location predicted correctly by static analysis, confirmed by the full run). → **M1**
3. `tests/test_companion_adapters.py::test_research_deep_start_does_not_block` — research-deep-start non-blocking assertion; **newly surfaced**, not in the audit's count. → **M1**
- CI runs pytest with `-x`, so any one fails the whole `test-python` job → red gate.
- **M1 goal:** **green suite** — fix all three, then `npm test` and the `all-green` gate pass.

## 4. CI gate evolution (blocking now → target)
| Check | Now | Target | When |
|---|---|---|---|
| pytest (`test-python`, `-x`) | **blocking** (gate `all-green`) | blocking + suite green | M1 |
| Node service tests (`test-node`, 8 scripts) | **blocking** | blocking | now |
| Frontend build (`build-frontend`) | **blocking** | blocking | now |
| bandit (SAST) | advisory (`continue-on-error` + `\|\| true`) | **blocking** (drop `\|\| true`) | M1 |
| CodeQL (SAST) | **not present** | add + blocking | M1→M3 |
| Black Duck / OSV (SCA) | **not present** | add + blocking | M1→M3 |
| Secret-scan (gitleaks) | **not present** | add + blocking | M3 |
| Route-auth scanner | **not present** | add + blocking | **M1** |
| Capability-manifest lint | **not present** | add + blocking | M2 |
| No-fake-success lint | **not present** | add + blocking | M2 |
| Adversarial suites (prompt-injection · tenant-leak · sandbox-escape · upload-validation) | **not present** | add + blocking (roadmap §4) | M3 |

> **Net M1 ask:** turn the suite green (skill-router fix) · add the **route-auth scanner** as a required check · flip **bandit** to blocking. CodeQL/SCA/secret-scan and the four adversarial suites land across M1→M3 per the [roadmap](SECURITY_COMPLIANCE_ROADMAP.md) §4 persistent gate.
