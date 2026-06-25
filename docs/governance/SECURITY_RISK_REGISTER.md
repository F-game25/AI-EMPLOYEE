# SECURITY_RISK_REGISTER — AI-EMPLOYEE / Nexus OS
**Generated:** 2026-06-25 · part of [governance doc-set](SECURITY_COMPLIANCE_ROADMAP.md) · see [SYSTEM_MAP.md](SYSTEM_MAP.md)

**Severity:** Critical / High / Med / Low (intrinsic). **Likelihood** is **local-desktop-adjusted**
(single trusted user, localhost) — many drop a tier vs a remote/multi-customer deployment; the
"remote" column shows what they become when the deploy target flips (tracked for M2 prod-mode gates).
**Status:** open / in-progress / mitigated / accepted.

## Active risks
| ID | Area | Risk | Sev | Likelihood (local / remote) | Evidence | Mitigation → Milestone | Status |
|---|---|---|---|---|---|---|---|
| SR-01 | Agent autonomy | **Excessive agency** (OWASP LLM06): 127 agents with real tools (shell/code/web/file), no enforced per-agent capability manifest | High | Med / High | `runtime/config/agent_capabilities.json`, `runtime/core/hitl_gate.py`, `runtime/tools/registry.py` | Capability firewall (allowed/forbidden tools, net allowlist, budget, approval) → **M2** | open |
| SR-02 | Command exec | `shell_exec` uses `shell=True` + **blocklist** regex (bypassable; CLAUDE.md mandates allowlist) | High | Med / High | [shell_exec.py:68](../../runtime/tools/implementations/shell_exec.py#L68), blocklist L16-30 | Allowlist `argv[0]` from `security.yml`, drop shell=True → **M1** | in-progress |
| SR-03 | RAG / memory | **Prompt-injection / RAG-poisoning**: retrieved web/file/memory text could become instructions | High | Med / High | `runtime/core/auto_research_agent.py`, `runtime/memory/` | Injection suite + "retrieved text = data, not authority" → **M3** | open |
| SR-04 | AuthZ | Route-auth high but **not machine-proven** per route (806 refs / 782 handlers) | High | Low / High | `backend/` route grep; no scanner | Route-auth scanner in CI → **M1** | open |
| SR-05 | Tenancy | Tenant isolation exists but **not leak-fuzz-tested** (JWT tenant_id swaps) | High | Low (single-user) / High | `runtime/core/tenancy.py`, `tests/test_multitenant.py` (no leak fuzz) | Tenant-leak suite → **M3** | open |
| SR-06 | Static exposure | `/workspace` serves **agent-generated HTML/JS publicly**, no auth/signed-token/sanitisation | Med | Med / High | [server.js:528](../../backend/server.js#L528) | Signed preview token + content-type allowlist + CSP sandbox; prod public-off → **M2** | open |
| SR-07 | Sandbox | Docker sandbox **silently falls back** to weaker process mode; no require-docker | Med | Med / High | `backend/infra/sandbox/executor.js` (`available()`/fallback) | `SANDBOX_REQUIRE_DOCKER` hard-fail in staging/prod → **M2** | open |
| SR-08 | Config | CSP `unsafe-inline` (script+style); no dev/prod split | Low | Low / Med | [server.js:462](../../backend/server.js#L462), [media.js:170](../../backend/routes/media.js#L170), `backend/middleware/csp.js:30` | Mode-split CSP, strict in prod → **M2** | open |
| SR-09 | CI gate | bandit **non-blocking** (`\|\| true`); no secret-scan/DAST/route-auth gate | Med | Med / Med | `.github/workflows/ci.yml` | bandit blocking + gitleaks + wire suites → **M3** | open |
| SR-10 | Reliability | No **system-wide no-fake-success** contract (only in `tool_registry.py`) | Med | Med / Med | `runtime/core/tool_registry.py` | Promote shared `{ok,status,evidence,…}` contract + lint → **M2** | open |
| SR-11 | Model routing | Sensitive local data may reach **external models** without redaction/classification | Med | Med / High | `runtime/core/orchestrator.py`, `runtime/engine/inference/llm.py` | Redact-before-remote + data-classification + provider logging → **M3** | open |
| SR-12 | Money-Mode | Consequential external actions (publish/scrape/outreach) without enforced approval | High | Med / High | `runtime/core/money_mode.py`, `/api/orders` | Capability firewall `human_approval_required_for` → **M2** | open |
| SR-13 | Secrets | No automated secret-scan; risk of committed/logged credentials | Med | Med / Med | `backend/security/secrets.js`, `~/.ai-employee/.env` | gitleaks in CI + redaction tests → **M3** | open |
| SR-16 | Sandbox | In-proc Python `sandbox_manager` exec is **escapable** (object-graph) even after hardening | Med | Med / High | `runtime/core/sandbox_manager.py` | env-strip + rlimits are blast-radius controls; route untrusted code to container → **M2** | partial |

## Fixed this session (evidence of progress — pending keep-confirm)
| ID | Fix | Evidence | Commit |
|---|---|---|---|
| SR-14 | **JWT algorithm-confusion** — pinned `algorithms:['HS256']` at all 10 HMAC verify sites (server.js, tenancy.js, rbac/middleware.js, ws-auth.js, token-manager.js ×3, health.js, oidc-verify.js); OIDC asymmetric path already pinned RS/ES | edited working tree (uncommitted) | this session |
| SR-15 | **Sandbox manager** — builtins-dict fix (was non-functional), env secret-strip, POSIX `setrlimit` CPU/mem/proc caps, `repr()`-embedding to stop triple-quote break-out | `runtime/core/sandbox_manager.py` | 9898a6a9 |
| SR-17 | **iframe-token JWT** — removed empty-secret fallback + pinned algorithm | `backend/routes/media.js`, `artifacts-tasks.js` | 7ae9632c |

## Accepted / out-of-scope (noted, not in this roadmap)
| ID | Item | Why accepted (local-desktop) |
|---|---|---|
| SR-18 | Dual desktop shell (Electron + Tauri) | Maintenance/attack-surface debt; tracked in [DESKTOP_APP_PLAN.md](../DESKTOP_APP_PLAN.md), not a security blocker locally |

## Verified-correct (no action — credit where due)
Cross-platform `file_lock.py` (fcntl/msvcrt) · parameterised SQL in `orders_store.py` (no injection) ·
CORS explicit allowlist w/ credentials (not `*`) · `path.basename` on file-serving routes ·
no `pickle`/`yaml.load`, no `verify=False`/`rejectUnauthorized:false`, no `dangerouslySetInnerHTML` ·
server fails-fast on missing `JWT_SECRET_KEY`.
