"""Execution broker for the Companion Gateway.

Routes a classified intent to capabilities, runs the SAFE ones through real
read-only calls where one cheaply exists, and turns everything risky into an
*approval request* — it NEVER executes a capability the safety gate did not
clear. The broker sits between the orchestrator (which knows mode/intent) and
the subsystems (which do the actual work).

Honesty invariant
------------------
A capability is either:
  - wired to a genuine read-only subsystem call (real data), OR
  - returned as ``{status: 'not_implemented', cap: <id>}`` — a clearly marked
    stub. The broker never fabricates subsystem data. Adapters for the rest are
    a later phase (P6).

Safety invariant
----------------
Every candidate capability is run through ``safety_gate.evaluate``. Only
``allowed and not requires_approval`` capabilities execute. Anything requiring
approval is added to ``approvals_required`` and NOT executed. Any execution
error is captured as ``{status: 'error', ...}`` — the broker never crashes.
"""
from __future__ import annotations

import logging
import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from companion.capability_registry import get_capability_registry
from companion.safety_gate import get_safety_gate
from companion.schemas import Capability

logger = logging.getLogger("companion.execution_broker")

# How many candidate capabilities to consider per intent (best-first from the
# registry). Keeps a single turn bounded and cheap.
_MAX_CANDIDATES = 4

# Subsystems gated behind the master Computer-Use mode toggle.
_COMPUTER_USE_SUBSYSTEMS = frozenset({"browser", "desktop"})


def _computer_use_on() -> bool:
    """Master Computer-Use switch (fails safe → OFF if unreadable)."""
    try:
        from companion.computer_use_mode import computer_use_enabled
        return computer_use_enabled()
    except Exception:  # noqa: BLE001
        return False

# Fine-grained system-info intents → the read-only tool that answers them.
# Routed deterministically (Phase 7.1.4) so "what time is it on my PC?" always
# reaches the real local-time tool. These are L0 OS probes (real measured values,
# never fabricated) — no safety gate needed: the teammate ANSWERS instead of
# explaining how the user could check manually.
_SYSTEM_INFO_TOOLS: dict[str, str] = {
    "system_info.local_time": "system_local_time",
    "system_info.hardware": "system_hardware",
    "system_info.cwd": "system_cwd",
}

_EXACT_TASK_CAPS: dict[str, str] = {
    "briefing.morning": "briefing.morning",
    "teammate.routine.status": "teammate.routine.status",
    "teammate.routine.configure": "teammate.routine.configure",
    "teammate.briefing.create_task": "teammate.briefing.create_task",
    # Business "do real work" intents go straight to the skill catalog (which
    # selects the right one of the ~859 executable skills) — not coincidental
    # token-overlap with a system capability.
    "skill": "skills.run",
    # "deep research X" goes to the real multi-hop engine, not a shallow skill.
    "research.deep": "research.deep.start",
}

# ── Adapter bounds (keep every executor cheap, read-only, non-destructive) ────
_LOG_SEARCH_MAX_LINES = 50      # max matching log lines returned
_LOG_SCAN_MAX_BYTES = 2_000_000  # tail at most ~2MB of a log file
_CODE_SEARCH_MAX_MATCHES = 40   # cap code-search hits
_CODE_SEARCH_MAX_FILE_BYTES = 600_000  # skip files larger than this
_TEST_TIMEOUT_S = 120           # forge.run_tests hard timeout
_TEST_OUTPUT_CAP = 6000         # chars of pytest output retained

# Directories never walked by forge.search_code (vendored / generated / heavy).
_CODE_SEARCH_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    "venv-codex", ".pytest_cache", "models", "state", "logs", ".cache",
}
# File suffixes searched by forge.search_code (source only).
_CODE_SEARCH_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".sh", ".md", ".css",
    ".html", ".yml", ".yaml", ".toml",
}

# Risk lexicon for the heuristic action scorer (security.score_action).
_RISK_TERMS = {
    # destructive
    "delete": 0.4, "drop": 0.4, "rm ": 0.4, "rm -rf": 0.6, "truncate": 0.4,
    "wipe": 0.4, "destroy": 0.4, "purge": 0.3, "format": 0.3,
    # deployment / mutation
    "deploy": 0.3, "push": 0.2, "force": 0.2, "overwrite": 0.25,
    "apply_patch": 0.3, "migrate": 0.2,
    # money / outreach side effects
    "spend": 0.35, "pay": 0.3, "charge": 0.3, "purchase": 0.3, "transfer": 0.35,
    "send": 0.2, "email": 0.2, "message": 0.15, "post": 0.15, "publish": 0.2,
    # secrets / access
    "credential": 0.4, "secret": 0.35, "password": 0.35, "token": 0.25,
    "api key": 0.35, "private key": 0.4,
    # scope amplifiers
    "production": 0.25, "all ": 0.15, "everything": 0.2, "prod": 0.2,
}


class ExecutionBroker:
    """Routes an intent to capabilities; executes the safe ones, gates the rest."""

    def __init__(self) -> None:
        self._registry = get_capability_registry()
        self._gate = get_safety_gate()
        # capability id -> real read-only executor. Honest dispatch only:
        # entries here are genuinely-available read-only calls.
        self._dispatch: dict[str, Callable[[Capability, dict], dict]] = {
            "system.health.read": self._exec_system_health,
            "system.tasks.active": self._exec_system_tasks_active,
            "system.overview": self._exec_system_overview,
            "system.logs.search": self._exec_system_logs_search,
            "briefing.morning": self._exec_morning_briefing,
            "teammate.routine.status": self._exec_teammate_routine_status,
            "teammate.routine.configure": self._exec_teammate_routine_configure,
            "teammate.briefing.create_task": self._exec_teammate_briefing_create_task,
            "memory.search": self._exec_memory_search,
            "memory.write_structured": self._exec_memory_write_structured,
            "research.deep.start": self._exec_research_deep_start,
            "money.analyze_idea": self._exec_money_analyze_idea,
            "forge.search_code": self._exec_forge_search_code,
            "forge.plan_change": self._exec_forge_plan_change,
            "forge.run_tests": self._exec_forge_run_tests,
            "security.score_action": self._exec_security_score_action,
            "browser.open": self._exec_browser_open,
            "browser.snapshot": self._exec_browser_snapshot,
            "browser.extract": self._exec_browser_extract,
            "browser.capture": self._exec_browser_capture,
            "browser.close": self._exec_browser_close,
            "context.retrieve": self._exec_context_retrieve,
            "context.write": self._exec_context_write,
            "context.compress_session": self._exec_context_compress_session,
            "forge.lifecycle_plan": self._exec_forge_lifecycle_plan,
            "research.audit_quality": self._exec_research_audit_quality,
            "skills.run": self._exec_skills_run,
            "content.produce": self._exec_content_produce,
            "finance.draft": self._exec_finance_draft,
            "company.validate": self._exec_company_validate,
            "company.refine": self._exec_company_refine,
            # NOTE: forge.apply_patch is deliberately absent — it is L3 and stays
            # approval-gated. It must never auto-run from the broker.
            # NOTE: browser.act is deliberately absent — it is L3 and stays
            # approval-gated. It must never auto-run from the broker.
        }

    def execute(
        self,
        intent: dict[str, Any],
        resolved: dict[str, Any],
        request_context: dict[str, Any],
        *,
        only_subsystems: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        """Route ``intent`` to capabilities and execute the safe ones.

        Returns::
            {
              results: list[dict],         # one per executed/blocked capability
              approvals_required: list,    # human-readable approval requests
              executed: list[str],         # cap ids actually run
              blocked: list[str],          # cap ids gated behind approval
            }
        """
        intent = intent or {}
        resolved = resolved or {}
        ctx = dict(request_context or {})

        results: list[dict[str, Any]] = []
        approvals_required: list[dict[str, Any]] = []
        executed: list[str] = []
        blocked: list[str] = []

        mode = str(intent.get("mode", ""))
        task_type = intent.get("task_type")

        # System-info intents are answered directly by a read-only OS probe via
        # the tool registry — the teammate returns the real value instead of a
        # tutorial. No capability/gate routing needed (L0, read-only).
        tool_name = _SYSTEM_INFO_TOOLS.get(str(task_type))
        if tool_name:
            try:
                from tools.registry import get_tool_registry
                envelope = get_tool_registry().execute(tool_name, ctx)
                ok = bool((envelope or {}).get("ok", False))
                # Unwrap the registry envelope → the tool's real payload.
                out = (envelope or {}).get("result") or envelope or {}
                status = "executed" if ok else "error"
            except Exception as exc:  # noqa: BLE001 — never raise out of a turn
                out, status = {"error": str(exc)}, "error"
            return {
                "results": [{"status": status, "cap": tool_name,
                             "subsystem": "system", "result": out}],
                "approvals_required": [],
                "executed": [tool_name] if status == "executed" else [],
                "blocked": [],
            }

        # An explicit imperative ("fix the build") lets L2 capabilities run
        # without a separate approval round-trip (the safety gate honours this).
        if intent.get("is_command"):
            ctx.setdefault("explicitly_commanded", True)

        # find_for_intent does token-overlap matching against capability
        # id/name/description/subsystem. The bare mode rarely overlaps, so route
        # on mode + the resolved (context-bound) text together — that's what
        # makes "what is the system doing?" reach system.health.read and
        # "apply the rate-limit patch" reach forge.apply_patch.
        routing_text = " ".join(
            s for s in (mode, str(resolved.get("resolved_text", "")
                                  or ctx.get("text", ""))) if s
        ).strip()
        candidates = self._registry.find_for_intent(routing_text, task_type)
        exact_cap_id = _EXACT_TASK_CAPS.get(str(task_type))
        if exact_cap_id:
            exact = self._registry.get(exact_cap_id)
            candidates = [exact] if exact is not None else []
        else:
            # These companion actions are intentionally opt-in. Generic
            # monitoring/questions should not accidentally produce a briefing or
            # mutate teammate/task state just because token overlap is high.
            candidates = [c for c in candidates if c.id not in set(_EXACT_TASK_CAPS.values())]
        if only_subsystems is not None:
            candidates = [c for c in candidates if c.subsystem in only_subsystems]
        candidates = candidates[:_MAX_CANDIDATES]

        # Hard rule (plan §A5): PC-control/browser actions require an execution-grade
        # local reasoner (Gemma Q4/QAT or stronger) to be INSTALLED. Resolve once.
        _exec_status: dict = {"available": True}
        if any(c.subsystem in _COMPUTER_USE_SUBSYSTEMS for c in candidates):
            try:
                from core.model_role_resolver import execution_reasoning_ready
                _exec_status = execution_reasoning_ready()
            except Exception as exc:  # noqa: BLE001 — resolver failure → fail safe (block)
                _exec_status = {"available": False, "reason": f"resolver error: {exc}",
                                "install_suggestion": "gemma3:4b-it-qat"}

        for cap in candidates:
            # Master Computer-Use switch: browser/desktop capabilities are refused
            # entirely until the user enables Computer-Use mode from the UI. This is
            # a hard gate (not an approval) — both voice and chat inherit it because
            # both flow through this broker.
            if cap.subsystem in _COMPUTER_USE_SUBSYSTEMS and not _computer_use_on():
                blocked.append(cap.id)
                results.append({
                    "status": "disabled", "cap": cap.id, "subsystem": cap.subsystem,
                    "reason": "Computer Use mode is off — enable it from the UI to let "
                              "the teammate use a browser/computer.",
                })
                continue
            # Even with Computer-Use ON, never drive the PC/browser with a weak model.
            if cap.subsystem in _COMPUTER_USE_SUBSYSTEMS and not _exec_status.get("available"):
                blocked.append(cap.id)
                sugg = _exec_status.get("install_suggestion") or "gemma3:4b-it-qat"
                results.append({
                    "status": "blocked_no_model", "cap": cap.id, "subsystem": cap.subsystem,
                    "reason": ("No execution-grade local model is installed for PC/browser "
                               f"control ({_exec_status.get('reason', '')}). Pull one first, "
                               f"e.g. `ollama pull {sugg}` — refusing to drive the computer "
                               "with a weak model."),
                    "install_suggestion": sugg,
                })
                continue
            try:
                decision = self._gate.evaluate(cap, ctx)
            except Exception as exc:  # gate itself failing → block, never run
                logger.warning("safety gate raised for %s: %s", cap.id, exc)
                blocked.append(cap.id)
                results.append({"status": "blocked", "cap": cap.id,
                                "error": f"safety gate error: {exc}"})
                continue

            if decision.get("allowed") and not decision.get("requires_approval"):
                results.append(self._run(cap, intent, resolved, ctx))
                executed.append(cap.id)
            elif decision.get("requires_approval"):
                approvals_required.append(self._approval_request(cap, decision, resolved))
                blocked.append(cap.id)
            else:
                # Not allowed and not pending approval (e.g. gate declined) —
                # surface it without executing.
                blocked.append(cap.id)
                results.append({"status": "blocked", "cap": cap.id,
                                "reason": decision.get("reason", "not allowed")})

        return {
            "results": results,
            "approvals_required": approvals_required,
            "executed": executed,
            "blocked": blocked,
        }

    # ── Dispatch ────────────────────────────────────────────────────────────────

    def _run(self, cap: Capability, intent: dict, resolved: dict, ctx: dict) -> dict:
        """Invoke a cleared capability. Errors are captured, never raised."""
        fn = self._dispatch.get(cap.id)
        if fn is None:
            # Honest stub — adapter not wired yet (P6).
            return {"status": "not_implemented", "cap": cap.id,
                    "subsystem": cap.subsystem,
                    "note": "adapter not yet wired (P6)"}
        try:
            out = fn(cap, ctx)
            return {"status": "ok", "cap": cap.id, "data": out}
        except Exception as exc:  # noqa: BLE001 — broker must never crash
            logger.warning("capability %s execution failed: %s", cap.id, exc)
            return {"status": "error", "cap": cap.id, "error": str(exc)}

    # ── Real read-only executors ─────────────────────────────────────────────────

    @staticmethod
    def _exec_system_health(cap: Capability, ctx: dict) -> dict:
        """Live system health/resource snapshot (best-effort, read-only)."""
        from engine.compute.resource_manager import get_resource_manager
        return get_resource_manager().to_dict()

    @staticmethod
    def _exec_memory_search(cap: Capability, ctx: dict) -> dict:
        """Substring search across the engine memory store (read-only)."""
        from engine.api import memory_search
        query = str(ctx.get("query") or ctx.get("text") or "").strip()
        if not query:
            return {"results": [], "note": "no query provided"}
        top_k = int(ctx.get("top_k", 5) or 5)
        return {"results": memory_search(query=query, top_k=top_k)}

    @staticmethod
    def _exec_memory_write_structured(cap: Capability, ctx: dict) -> dict:
        """Persist a structured fact/note into the engine memory store (L1 write).

        Read-of-product-files-only invariant is not violated: this writes to the
        engine's own key/value memory store, the capability's declared side
        effect. No external action, no spending, no source edits.
        """
        from engine.api import memory_store
        key = str(ctx.get("key") or "").strip()
        value = ctx.get("value", ctx.get("content"))
        if not key:
            return {"stored": False, "note": "no key provided"}
        if value is None:
            return {"stored": False, "note": "no value/content provided"}
        namespace = str(ctx.get("namespace") or "companion").strip() or "companion"
        record = {"value": value}
        tags = ctx.get("tags")
        if tags:
            record["tags"] = list(tags) if isinstance(tags, (list, tuple, set)) else [tags]
        memory_store(key=key, value=record, namespace=namespace)
        return {"stored": True, "key": key, "namespace": namespace}

    # ── system.tasks.active ───────────────────────────────────────────────────────

    @staticmethod
    def _exec_system_overview(cap: Capability, ctx: dict) -> dict:
        """Enterprise status report: aggregate REAL system state — active tasks,
        agent count, system health, recent activity — read-only, always honest
        (no fabricated numbers; missing sources degrade to 0/empty)."""
        import json
        sd = _state_dir()
        ov: dict[str, Any] = {}
        # Active tasks (reuse the tasks executor).
        try:
            tasks = ExecutionBroker._exec_system_tasks_active(cap, ctx).get("tasks") or []
        except Exception:
            tasks = []
        ov["active_tasks"] = len(tasks)
        ov["tasks"] = tasks[:10]
        # Agent count from the catalog.
        try:
            from pathlib import Path as _P
            ac = json.loads((_P(__file__).resolve().parents[1] / "config" / "agent_capabilities.json").read_text(encoding="utf-8"))
            agents = ac.get("agents", ac) if isinstance(ac, dict) else ac
            ov["agents_total"] = len(agents)
        except Exception:
            ov["agents_total"] = 0
        # System health.
        try:
            h = ExecutionBroker._exec_system_health(cap, ctx)
            ov["health"] = {k: h.get(k) for k in ("cpu_percent", "memory_percent", "gpu_percent", "status") if k in h} or h
        except Exception:
            ov["health"] = {}
        # Recent activity (event-bus tail).
        try:
            bus = sd / "bus.jsonl"
            lines = bus.read_text(encoding="utf-8").splitlines()[-8:] if bus.exists() else []
            acts = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    acts.append(obj.get("event") or obj.get("type") or str(obj)[:80])
                except Exception:
                    acts.append(line[:80])
            ov["recent_activity"] = acts[-8:]
        except Exception:
            ov["recent_activity"] = []
        summary = (f"{ov['active_tasks']} active task(s), {ov['agents_total']} agents available, "
                   f"system {ov.get('health', {}).get('status', 'ok')}.")
        return {"overview": ov, "summary": summary}

    @staticmethod
    def _exec_system_tasks_active(cap: Capability, ctx: dict) -> dict:
        """Active (running/queued) tasks from state/tasks.json (read-only).

        Honest empty list when the file is absent or empty. Reads through the
        fcntl file-lock helper when available, else a guarded plain JSON read.
        """
        tasks_path = _state_dir() / "tasks.json"
        data: Any = {}
        try:
            from core.file_lock import read_json_safe
            data = read_json_safe(tasks_path, default={})
        except Exception:
            try:
                if tasks_path.exists():
                    import json
                    data = json.loads(tasks_path.read_text(encoding="utf-8"))
            except Exception as exc:
                return {"tasks": [], "note": f"could not read tasks file: {exc}"}

        # tasks.json shape is {"tasks": {<id>: {...}}} (may also be a list).
        raw = data.get("tasks", data) if isinstance(data, dict) else data
        items: list[dict] = []
        if isinstance(raw, dict):
            for tid, t in raw.items():
                if isinstance(t, dict):
                    items.append({"id": tid, **t})
        elif isinstance(raw, list):
            items = [t for t in raw if isinstance(t, dict)]

        active_states = {"running", "queued", "pending", "in_progress", "active"}
        active = [
            t for t in items
            if str(t.get("status", "")).lower() in active_states
        ]
        # If nothing carries a recognisable status, return all as-is (honest).
        tasks = active if active else (items if not any(
            "status" in t for t in items) else [])
        return {"tasks": tasks, "total_known": len(items),
                "source": str(tasks_path)}

    # ── system.logs.search ────────────────────────────────────────────────────────

    @staticmethod
    def _exec_system_logs_search(cap: Capability, ctx: dict) -> dict:
        """Search recent backend logs for a query string (read-only, bounded).

        Tails up to ``_LOG_SCAN_MAX_BYTES`` of the newest available log file and
        returns the last N matching lines. Empty + honest note when no log.
        """
        query = str(ctx.get("query") or ctx.get("text") or "").strip()
        if not query:
            return {"lines": [], "note": "no query provided"}
        limit = max(1, min(int(ctx.get("limit", _LOG_SEARCH_MAX_LINES) or _LOG_SEARCH_MAX_LINES),
                           _LOG_SEARCH_MAX_LINES))

        sd = _state_dir()
        # Prefer the canonical backend log; fall back to other logs that exist.
        candidates = [
            sd / "python-backend.log",
            sd / "server.log",
        ]
        candidates += sorted(sd.glob("*.log"), key=lambda p: _safe_mtime(p), reverse=True)
        log_path = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
        if log_path is None:
            return {"lines": [], "note": "no non-empty log file found",
                    "searched": [str(c) for c in candidates[:2]]}

        ql = query.lower()
        matches: list[str] = []
        try:
            size = log_path.stat().st_size
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                if size > _LOG_SCAN_MAX_BYTES:
                    fh.seek(size - _LOG_SCAN_MAX_BYTES)
                    fh.readline()  # discard partial line
                for line in fh:
                    if ql in line.lower():
                        matches.append(line.rstrip("\n"))
        except Exception as exc:
            return {"lines": [], "note": f"could not read log: {exc}",
                    "log": str(log_path)}
        return {"lines": matches[-limit:], "matched": len(matches),
                "log": str(log_path)}

    # ── briefing.morning ────────────────────────────────────────────────────────

    @staticmethod
    def _exec_morning_briefing(cap: Capability, ctx: dict) -> dict:
        """Build a conversational morning brief from real local state.

        Read-only by design: this does not call the CEO briefing generator because
        that path may append a cached briefing record. Missing files are reported
        honestly as absent sources; no metrics are fabricated.
        """
        from datetime import datetime

        sd = _state_dir()
        sources: list[str] = []
        missing: list[str] = []

        def _json_file(name: str, default: Any) -> Any:
            path = sd / name
            if not path.exists():
                missing.append(name)
                return default
            sources.append(str(path))
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                return {"_read_error": str(exc)}

        def _jsonl_file(name: str, limit: int = 300) -> list[dict]:
            path = sd / name
            if not path.exists():
                missing.append(name)
                return []
            sources.append(str(path))
            rows: list[dict] = []
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
            except Exception:
                return []
            return rows[-limit:]

        today = datetime.now().date().isoformat()

        tasks_info = ExecutionBroker._exec_system_tasks_active(cap, ctx)
        active_tasks = tasks_info.get("tasks") if isinstance(tasks_info, dict) else []
        active_tasks = active_tasks if isinstance(active_tasks, list) else []

        crm = _json_file("leads-crm.json", {})
        leads = crm.get("leads", []) if isinstance(crm, dict) else []
        if not isinstance(leads, list):
            leads = []
        leads_by_stage: dict[str, int] = {}
        pipeline_value = 0.0
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            stage = str(lead.get("stage") or "new_lead")
            leads_by_stage[stage] = leads_by_stage.get(stage, 0) + 1
            try:
                pipeline_value += float(lead.get("value", 0) or 0)
            except Exception:
                pass

        invoices_data = _json_file("invoices.json", {})
        invoices = invoices_data.get("invoices", []) if isinstance(invoices_data, dict) else []
        if not isinstance(invoices, list):
            invoices = []
        revenue_paid = 0.0
        invoices_overdue = 0
        invoices_pending = 0
        for inv in invoices:
            if not isinstance(inv, dict):
                continue
            status = str(inv.get("status") or "").lower()
            try:
                total = float(inv.get("total", inv.get("amount", 0)) or 0)
            except Exception:
                total = 0.0
            if status == "paid":
                revenue_paid += total
            elif status == "overdue":
                invoices_overdue += 1
            elif status in ("sent", "draft", "pending"):
                invoices_pending += 1

        social = _json_file("social-schedule.json", {})
        posts = social.get("posts", []) if isinstance(social, dict) else []
        if not isinstance(posts, list):
            posts = []
        social_posts_today = sum(
            1 for post in posts
            if isinstance(post, dict)
            and str(post.get("published_at") or post.get("scheduled_at") or "").startswith(today)
        )

        guardrails = _jsonl_file("guardrails.jsonl")
        guardrail_flags = sum(
            1 for row in guardrails
            if str(row.get("status") or "").lower() in ("pending", "blocked", "needs_approval")
        )

        chat_rows = _jsonl_file("chatlog.jsonl", 500)
        chat_messages_today = sum(
            1 for row in chat_rows
            if str(row.get("timestamp") or row.get("ts") or "").startswith(today)
        )

        runtime_state = _json_file("runtime_state.json", {})
        activity = runtime_state.get("activityFeed", []) if isinstance(runtime_state, dict) else []
        execution_logs = runtime_state.get("executionLogs", []) if isinstance(runtime_state, dict) else []
        recent_activity = [
            str((item or {}).get("message") or (item or {}).get("title") or (item or {}).get("event") or "")[:140]
            for item in (activity if isinstance(activity, list) else [])[:5]
            if isinstance(item, dict)
        ]
        recent_failures = [
            str((item or {}).get("message") or (item or {}).get("error") or "")[:160]
            for item in (execution_logs if isinstance(execution_logs, list) else [])[:8]
            if isinstance(item, dict) and str(item.get("status") or "").lower() == "failed"
        ]

        active_pipeline = sum(
            count for stage, count in leads_by_stage.items()
            if stage not in {"closed_won", "closed_lost"}
        )
        metrics = {
            "active_tasks": len(active_tasks),
            "known_tasks": tasks_info.get("total_known", len(active_tasks)) if isinstance(tasks_info, dict) else len(active_tasks),
            "chat_messages_today": chat_messages_today,
            "leads_total": len(leads),
            "active_pipeline_leads": active_pipeline,
            "leads_by_stage": leads_by_stage,
            "pipeline_value": round(pipeline_value, 2),
            "revenue_paid": round(revenue_paid, 2),
            "invoices_overdue": invoices_overdue,
            "invoices_pending": invoices_pending,
            "social_posts_today": social_posts_today,
            "guardrail_flags": guardrail_flags,
            "recent_failures": len(recent_failures),
        }

        focus: list[str] = []
        if invoices_overdue:
            focus.append(f"Collect or resolve {invoices_overdue} overdue invoice{'s' if invoices_overdue != 1 else ''}.")
        if guardrail_flags:
            focus.append(f"Clear {guardrail_flags} pending guardrail or approval item{'s' if guardrail_flags != 1 else ''}.")
        negotiation = leads_by_stage.get("negotiation", 0) + leads_by_stage.get("proposal", 0)
        if negotiation:
            focus.append(f"Follow up on {negotiation} late-stage lead{'s' if negotiation != 1 else ''}.")
        if active_tasks:
            first = active_tasks[0]
            label = first.get("title") or first.get("task") or first.get("id") or "the active task"
            focus.append(f"Check progress on {label}.")
        if not focus:
            focus.append("Use the first work block for one revenue-moving task; no urgent local blockers were found.")

        risks: list[str] = []
        if invoices_overdue:
            risks.append(f"{invoices_overdue} overdue invoice{'s' if invoices_overdue != 1 else ''}.")
        if recent_failures:
            risks.append(f"{len(recent_failures)} recent failed execution log entr{'ies' if len(recent_failures) != 1 else 'y'}.")
        if guardrail_flags:
            risks.append(f"{guardrail_flags} pending guardrail item{'s' if guardrail_flags != 1 else ''}.")
        if not risks:
            risks.append("No revenue, guardrail, or execution risks found in local state.")

        headline = f"Morning brief for {today}"
        summary = (
            f"{len(active_tasks)} active task{'s' if len(active_tasks) != 1 else ''}, "
            f"{active_pipeline} active pipeline lead{'s' if active_pipeline != 1 else ''}, "
            f"${pipeline_value:,.0f} pipeline value, "
            f"${revenue_paid:,.0f} collected revenue."
        )
        spoken_summary = (
            f"Morning brief: {summary} First focus: {focus[0]} "
            f"Main risk: {risks[0]} Ask me what to tackle first if you want to work through it."
        )

        return {
            "status": "ok",
            "kind": "morning_briefing",
            "date": today,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "headline": headline,
            "summary": summary,
            "spoken_summary": spoken_summary,
            "focus": focus[:5],
            "risks": risks[:5],
            "metrics": metrics,
            "recent_activity": recent_activity,
            "recent_failures": recent_failures[:5],
            "sources": sources,
            "missing_sources": missing,
            "read_only": True,
            "follow_up_prompt": "Ask me which item to prioritize, why it matters, or to turn one item into a plan.",
        }

    # ── teammate.* ───────────────────────────────────────────────────────────────

    @staticmethod
    def _exec_teammate_routine_status(cap: Capability, ctx: dict) -> dict:
        """Read local teammate preferences/routines."""
        from companion.teammate_state import load_teammate_state

        tenant_id = str((ctx or {}).get("tenant_id") or "default")
        state = load_teammate_state(tenant_id)
        return {
            "status": "ok",
            "preferences": state.get("preferences", {}),
            "routines": state.get("routines", {}),
            "source": str(_state_dir() / "teammate_state.json"),
            "read_only": True,
        }

    @staticmethod
    def _exec_teammate_routine_configure(cap: Capability, ctx: dict) -> dict:
        """Persist a local teammate routine preference. No scheduler is started."""
        from companion.teammate_state import configure_morning_brief, normalize_time

        ctx = ctx or {}
        text = str(ctx.get("text") or "").lower()
        tenant_id = str(ctx.get("tenant_id") or "default")
        disabled = any(phrase in text for phrase in (
            "disable", "turn off", "cancel", "stop briefing", "stop the brief",
        ))
        briefing_time = normalize_time(str(ctx.get("time") or ctx.get("text") or ""))
        channel = str(ctx.get("channel") or ("chat" if "chat" in text else "voice"))
        routine = configure_morning_brief(
            enabled=not disabled,
            briefing_time=briefing_time,
            channel=channel,
            tenant_id=tenant_id,
        )
        return {
            "status": "stored",
            "routine": "morning_brief",
            "config": routine,
            "stored": True,
            "external_side_effects": False,
            "note": (
                "Saved the local teammate routine preference. A background "
                "scheduler must read this state before automatic delivery runs."
            ),
        }

    @staticmethod
    def _exec_teammate_briefing_create_task(cap: Capability, ctx: dict) -> dict:
        """Turn a recent morning-brief focus item into a local pending task."""
        ctx = ctx or {}
        briefing = _recent_briefing_data(ctx)
        if not briefing:
            return {
                "status": "needs_briefing",
                "stored": False,
                "note": "No recent morning brief found in this session. Ask for a morning brief first.",
            }
        focus = briefing.get("focus") if isinstance(briefing.get("focus"), list) else []
        if not focus:
            return {
                "status": "no_focus",
                "stored": False,
                "note": "The recent morning brief did not contain focus items.",
            }

        idx = _focus_index_from_text(str(ctx.get("text") or ""))
        idx = max(0, min(idx, len(focus) - 1))
        title = str(ctx.get("title") or focus[idx]).strip()
        if title.endswith("."):
            title = title[:-1]

        now = datetime.now().isoformat(timespec="seconds")
        task_id = f"voice-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "title": title[:180],
            "status": "pending",
            "priority": "high" if _briefing_has_risk(briefing, title) else "normal",
            "source": "voice_morning_brief",
            "created_at": now,
            "context": {
                "briefing_date": briefing.get("date"),
                "focus_index": idx + 1,
                "source_capability": "briefing.morning",
            },
        }

        tasks_path = _state_dir() / "tasks.json"
        try:
            from core.file_lock import read_json_safe, write_json_safe

            data = read_json_safe(tasks_path, default={})
            updated = _append_task(data, task)
            stored = write_json_safe(tasks_path, updated)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "stored": False,
                "error": str(exc),
                "task": task,
            }
        return {
            "status": "created" if stored else "error",
            "stored": bool(stored),
            "task": task,
            "source_focus": focus[idx],
            "external_side_effects": False,
            "source": str(tasks_path),
        }

    # ── research.deep.start ───────────────────────────────────────────────────────

    @staticmethod
    def _exec_research_deep_start(cap: Capability, ctx: dict) -> dict:
        """Emit a deep-research DIRECTIVE for the UI to run + visualize live.

        Previously this spawned a dead daemon thread with no progress feedback, so a
        chat 'deep research X' looked fake (confirmation, then nothing). Now it returns
        a structured directive; the chat renders the live DeepResearchInline card,
        which starts the run via POST /api/research/deep/start — the SAME path as the
        Deep Research button (real multi-hop engine + live WS progress + the report).
        """
        import re as _re
        raw = str(ctx.get("topic") or ctx.get("text") or "").strip()
        if not raw:
            return {"status": "error", "note": "no topic provided"}
        # Strip the command framing so the topic is just the subject.
        topic = _re.sub(
            r"^(please\s+)?(do|run|start|perform|conduct|give me|i want|can you)?\s*"
            r"(a|an|the)?\s*(deep[\s-]?(dive|research)|in[\s-]?depth research|thorough research|"
            r"comprehensive research|exhaustive research|research(\s+report)?)\s*"
            r"(on|into|about|of|for)?\s*",
            "", raw, flags=_re.I).strip() or raw
        if len(topic) > 600:
            topic = topic[:600]
        depth = str(ctx.get("depth") or "deep")
        if depth not in ("shallow", "normal", "deep"):
            depth = "deep"
        return {
            "status": "directive",
            "directive": "deep_research",
            "topic": topic,
            "depth": depth,
            "note": "Launching deep research — live progress + the full report appear below.",
        }

    # ── money.analyze_idea ────────────────────────────────────────────────────────

    @staticmethod
    def _exec_money_analyze_idea(cap: Capability, ctx: dict) -> dict:
        """Lightweight, read-only analysis of a monetization idea — NO spending.

        Composes a structured draft analysis from MoneyMode's planning helper
        (_step_generate_idea) plus a simple heuristic score. Executes NO pipeline
        steps that touch the ActionBus / external systems / ROI ledger.
        """
        idea = str(ctx.get("idea") or ctx.get("text") or "").strip()
        if not idea:
            return {"status": "error", "note": "no idea provided"}

        breakdown: dict[str, Any] = {}
        try:
            from core.money_mode import MoneyMode
            mm = MoneyMode()
            # Read-only planning helper: returns an idea sketch, no side effects.
            if hasattr(mm, "_step_generate_idea"):
                step = mm._step_generate_idea(idea, "")  # affiliate_product=""
                breakdown["idea_sketch"] = step.get("output", step)
        except Exception as exc:
            breakdown["idea_sketch_error"] = str(exc)

        # Heuristic, fully local scoring — clearly labelled as a draft estimate.
        low = idea.lower()
        signals = {
            "recurring_revenue": any(k in low for k in
                ("subscription", "saas", "recurring", "membership", "retainer")),
            "low_capital": any(k in low for k in
                ("digital", "content", "service", "affiliate", "newsletter")),
            "scalable": any(k in low for k in
                ("automate", "software", "platform", "api", "scale")),
            "clear_audience": any(k in low for k in
                ("b2b", "smb", "developers", "founders", "agencies", "ecommerce")),
        }
        score = round(min(1.0, 0.35 + 0.15 * sum(signals.values())), 3)
        breakdown["signals"] = signals
        breakdown["rationale"] = (
            "Heuristic draft: +score for recurring/scalable/low-capital/"
            "audience signals. Not a market study — research.deep.start can "
            "validate before any spend."
        )
        return {
            "status": "draft",
            "idea": idea,
            "score": score,
            "breakdown": breakdown,
            "spent": False,
            "note": "read-only analysis; no money pipeline executed",
        }

    # ── forge.search_code ─────────────────────────────────────────────────────────

    @staticmethod
    def _exec_forge_search_code(cap: Capability, ctx: dict) -> dict:
        """Bounded, read-only code search across the repo (ripgrep or os.walk).

        Returns file:line matches, capped at ``_CODE_SEARCH_MAX_MATCHES``. Never
        edits anything. Prefers ripgrep when present, else a guarded os.walk.
        """
        query = str(ctx.get("query") or ctx.get("text") or "").strip()
        if not query:
            return {"matches": [], "note": "no query provided"}
        root = _repo_root()
        sub = str(ctx.get("path") or "").strip()
        search_root = (root / sub).resolve() if sub else root
        # Containment guard: never escape the repo.
        try:
            search_root.relative_to(root)
        except ValueError:
            search_root = root
        if not search_root.exists():
            return {"matches": [], "note": f"path not found: {sub}"}

        rg = _which("rg")
        if rg:
            out = ExecutionBroker._rg_search(rg, query, search_root)
            if out is not None:
                return out
        # Fallback: os.walk + substring match.
        return ExecutionBroker._walk_search(query, search_root, root)

    @staticmethod
    def _rg_search(rg: str, query: str, search_root: Path) -> dict | None:
        import subprocess
        try:
            proc = subprocess.run(
                [rg, "--no-heading", "--line-number", "--fixed-strings",
                 "--max-count", "5", "-m", str(_CODE_SEARCH_MAX_MATCHES),
                 query, str(search_root)],
                capture_output=True, text=True, timeout=20,
            )
        except Exception:
            return None
        matches: list[dict] = []
        for line in (proc.stdout or "").splitlines():
            parts = line.split(":", 2)
            if len(parts) == 3:
                matches.append({"file": parts[0], "line": int(parts[1])
                                if parts[1].isdigit() else parts[1],
                                "text": parts[2].strip()[:300]})
            if len(matches) >= _CODE_SEARCH_MAX_MATCHES:
                break
        return {"matches": matches, "count": len(matches), "engine": "ripgrep"}

    @staticmethod
    def _walk_search(query: str, search_root: Path, root: Path) -> dict:
        ql = query.lower()
        matches: list[dict] = []
        for dirpath, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [d for d in dirnames if d not in _CODE_SEARCH_SKIP_DIRS
                           and not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix not in _CODE_SEARCH_EXTS:
                    continue
                fp = Path(dirpath) / fn
                try:
                    if fp.stat().st_size > _CODE_SEARCH_MAX_FILE_BYTES:
                        continue
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                        for i, line in enumerate(fh, 1):
                            if ql in line.lower():
                                matches.append({
                                    "file": str(fp.relative_to(root)),
                                    "line": i, "text": line.strip()[:300],
                                })
                                if len(matches) >= _CODE_SEARCH_MAX_MATCHES:
                                    return {"matches": matches,
                                            "count": len(matches),
                                            "engine": "walk", "truncated": True}
                except Exception:
                    continue
        return {"matches": matches, "count": len(matches), "engine": "walk"}

    # ── forge.plan_change ─────────────────────────────────────────────────────────

    @staticmethod
    def _exec_forge_plan_change(cap: Capability, ctx: dict) -> dict:
        """Draft a change PLAN via the LLM — planning only, writes NO files.

        Defensive: if the LLM is unavailable, returns a structured
        "planning unavailable" note rather than fabricating a plan.
        """
        goal = str(ctx.get("goal") or ctx.get("text") or "").strip()
        if not goal:
            return {"status": "error", "note": "no goal provided"}
        scope = ctx.get("scope")
        scope_txt = (", ".join(map(str, scope)) if isinstance(scope, (list, tuple))
                     else str(scope or "")).strip()
        try:
            from engine.api import generate
            prompt = (
                "Produce a concise, numbered implementation PLAN for this change. "
                "Do NOT write code or diffs — list steps, files likely touched, "
                "risks, and a test idea. Keep it under 200 words.\n\n"
                f"Goal: {goal}\n"
                + (f"Scope hint: {scope_txt}\n" if scope_txt else "")
            )
            plan_text = generate(
                prompt=prompt,
                system="You are a senior engineer writing a short change plan. "
                       "Planning only — never produce edits.",
                timeout=60,
            )
            plan_text = (plan_text or "").strip()
            if not plan_text:
                raise RuntimeError("empty plan from LLM")
            return {"status": "draft", "goal": goal,
                    "plan": {"text": plan_text, "scope": scope_txt or None},
                    "writes_files": False}
        except Exception as exc:
            logger.info("forge.plan_change LLM unavailable: %s", exc)
            return {"status": "planning_unavailable", "goal": goal,
                    "note": "LLM offline — no plan generated (no fabrication)",
                    "error": str(exc), "writes_files": False}

    # ── forge.run_tests ───────────────────────────────────────────────────────────

    @staticmethod
    def _exec_forge_run_tests(cap: Capability, ctx: dict) -> dict:
        """Run pytest against a NAMED target (read-only w.r.t. product code).

        Requires an explicit target (selector/target/path). With no target this
        returns a 'target required' note rather than running the whole suite
        unprompted — running everything is expensive and easy to trigger by
        accident. Heavily guarded: timeout + capped output, never raises.
        """
        target = str(ctx.get("selector") or ctx.get("target")
                     or ctx.get("path") or "").strip()
        if not target:
            return {"status": "target_required",
                    "note": "name a test target (e.g. tests/test_x.py) — "
                            "the broker will not run the full suite unprompted"}

        root = _repo_root()
        # Containment + existence guard: only run targets inside the repo.
        candidate = (root / target).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return {"status": "error", "note": "target escapes repo root",
                    "target": target}
        # Allow pytest node ids like file::test — check the file part exists.
        file_part = target.split("::", 1)[0]
        if file_part and not (root / file_part).exists():
            return {"status": "error", "note": f"target not found: {file_part}",
                    "target": target}

        import subprocess
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(root), str(root / "runtime"), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest", target, "-q",
                 "--no-header", "-p", "no:cacheprovider"],
                cwd=str(root), env=env, capture_output=True, text=True,
                timeout=_TEST_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "target": target,
                    "note": f"tests exceeded {_TEST_TIMEOUT_S}s"}
        except Exception as exc:
            return {"status": "error", "target": target, "error": str(exc)}

        out = (proc.stdout or "") + (proc.stderr or "")
        passed, failed = _parse_pytest_summary(out)
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "target": target,
            "exit_code": proc.returncode,
            "passed": passed,
            "failed": failed,
            "report": out[-_TEST_OUTPUT_CAP:],
        }

    # ── security.score_action ─────────────────────────────────────────────────────

    @staticmethod
    def _exec_security_score_action(cap: Capability, ctx: dict) -> dict:
        """Heuristic, read-only risk score for a described action.

        Clearly labelled as a heuristic — keyword-driven, no model. Higher score
        = riskier. Used to triage before deeper review; never blocks/executes.
        """
        action = str(ctx.get("action") or ctx.get("text") or "").strip()
        if not action:
            return {"status": "error", "note": "no action provided"}
        payload = ctx.get("payload")
        haystack = action.lower()
        if isinstance(payload, dict):
            haystack += " " + " ".join(str(v).lower() for v in payload.values())

        score = 0.0
        reasons: list[str] = []
        for term, weight in _RISK_TERMS.items():
            if term in haystack:
                score += weight
                reasons.append(f"contains '{term.strip()}' (+{weight})")
        score = round(min(1.0, score), 3)
        if score >= 0.6:
            level = "high"
        elif score >= 0.3:
            level = "medium"
        elif score > 0.0:
            level = "low"
        else:
            level = "minimal"
        return {
            "status": "ok",
            "method": "heuristic",
            "action": action,
            "risk_level": level,
            "score": score,
            "risk_score": score,
            "reasons": reasons or ["no risk keywords detected"],
            "factors": reasons,
        }

    # ── browser.* (defensive: browser missing → honest status, never throw) ──────

    @staticmethod
    def _exec_browser_open(cap: Capability, ctx: dict) -> dict:
        """Open a URL in a fresh ephemeral browser session (URL-guarded).

        The URL policy runs BEFORE any chromium launch — a blocked URL is a
        structured ``{status: 'refused'}``, never an exception or a fetch.
        """
        url = str(ctx.get("url") or ctx.get("text") or "").strip()
        if not url:
            return {"status": "error", "note": "no url provided"}
        try:
            from tools.browser.browser_service import check_url, get_browser_service
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"browser service not importable: {exc}"}
        err = check_url(url)
        if err:
            return {"status": "refused", "url": url, "note": err}
        try:
            return {"status": "ok",
                    **get_browser_service().open(url, profile=str(
                        ctx.get("profile") or "ephemeral"))}
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}

    @staticmethod
    def _exec_browser_snapshot(cap: Capability, ctx: dict) -> dict:
        """Stable-ref accessibility snapshot of an open session (read-only)."""
        sid = str(ctx.get("session_id") or "").strip()
        if not sid:
            return {"status": "error", "note": "no session_id provided"}
        try:
            from tools.browser.accessibility_snapshot import snapshot
            from tools.browser.browser_service import get_browser_service
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"browser service not importable: {exc}"}
        sess = get_browser_service().get_session(sid)
        if sess is None:
            return {"status": "error", "note": f"unknown session: {sid}"}
        try:
            return {"status": "ok", **snapshot(sess)}
        except Exception as exc:
            return {"status": "error", "session_id": sid, "error": str(exc)}

    @staticmethod
    def _exec_browser_extract(cap: Capability, ctx: dict) -> dict:
        """Bounded content extraction from an open session (read-only)."""
        sid = str(ctx.get("session_id") or "").strip()
        if not sid:
            return {"status": "error", "note": "no session_id provided"}
        try:
            from tools.browser.browser_service import get_browser_service
            from tools.browser.extract import extract
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"browser service not importable: {exc}"}
        sess = get_browser_service().get_session(sid)
        if sess is None:
            return {"status": "error", "note": f"unknown session: {sid}"}
        try:
            out = extract(sess, str(ctx.get("kind") or "text"),
                          ctx.get("target") or ctx.get("selector"))
            return {"status": "ok" if out.get("ok") else "error", **out}
        except Exception as exc:
            return {"status": "error", "session_id": sid, "error": str(exc)}

    @staticmethod
    def _exec_browser_capture(cap: Capability, ctx: dict) -> dict:
        """Screenshot/PDF of an open session into the rotated captures dir."""
        sid = str(ctx.get("session_id") or "").strip()
        if not sid:
            return {"status": "error", "note": "no session_id provided"}
        try:
            from tools.browser.browser_service import get_browser_service
            from tools.browser.capture import capture
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"browser service not importable: {exc}"}
        sess = get_browser_service().get_session(sid)
        if sess is None:
            return {"status": "error", "note": f"unknown session: {sid}"}
        try:
            out = capture(sess, str(ctx.get("kind") or "screenshot"))
            return {"status": "ok" if out.get("ok") else "error", **out}
        except Exception as exc:
            return {"status": "error", "session_id": sid, "error": str(exc)}

    @staticmethod
    def _exec_browser_close(cap: Capability, ctx: dict) -> dict:
        """Close one session, or all sessions when no session_id is given."""
        try:
            from tools.browser.browser_service import get_browser_service
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"browser service not importable: {exc}"}
        sid = str(ctx.get("session_id") or "").strip()
        try:
            svc = get_browser_service()
            out = svc.close(sid) if sid else svc.close_all()
            return {"status": "ok", **out}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ── context.* (defensive: context_db missing → honest status, never throw) ──

    @staticmethod
    def _exec_context_retrieve(cap: Capability, ctx: dict) -> dict:
        """Hybrid L0/L1 retrieval over the context tree — read-only, traced."""
        query = str(ctx.get("query") or ctx.get("text") or "").strip()
        if not query:
            return {"status": "error", "note": "no query provided"}
        try:
            from memory.context_db.recursive_retriever import retrieve
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"context_db not importable: {exc}"}
        try:
            filters = ctx.get("filters")
            out = retrieve(
                query,
                project_id=str(ctx.get("project_id") or "default"),
                filters=filters if isinstance(filters, dict) else None,
                top_k=int(ctx.get("top_k", 8) or 8),
            )
            return {"status": "ok", **out}
        except Exception as exc:
            return {"status": "error", "query": query, "error": str(exc)}

    @staticmethod
    def _exec_context_write(cap: Capability, ctx: dict) -> dict:
        """Write one validated node into the context tree (L1 write).

        Unsafe paths (traversal / bad root) come back as a structured
        ``{status: 'refused'}`` — never an exception, never a write.
        """
        path = str(ctx.get("path") or "").strip()
        content = ctx.get("content", ctx.get("value"))
        if not path:
            return {"status": "error", "note": "no path provided"}
        if content is None:
            return {"status": "error", "note": "no content provided"}
        try:
            from memory.context_db.context_tree import ContextTree
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"context_db not importable: {exc}"}
        try:
            tenant = str(ctx.get("tenant") or "default")
            metadata = ctx.get("metadata")
            node_id = ContextTree(tenant=tenant).write(
                path, str(content),
                metadata=metadata if isinstance(metadata, dict) else None)
            return {"status": "ok", "node_id": node_id, "path": path,
                    "tenant": tenant}
        except ValueError as exc:
            return {"status": "refused", "path": path, "note": str(exc)}
        except Exception as exc:
            return {"status": "error", "path": path, "error": str(exc)}

    @staticmethod
    def _exec_context_compress_session(cap: Capability, ctx: dict) -> dict:
        """Compress a conversation into durable context nodes (heuristic)."""
        messages = ctx.get("messages")
        if not isinstance(messages, list) or not messages:
            return {"status": "error",
                    "note": "messages must be a non-empty list"}
        try:
            from memory.context_db.session_compressor import compress_session
        except Exception as exc:
            return {"status": "unavailable",
                    "note": f"context_db not importable: {exc}"}
        try:
            out = compress_session(
                messages, project_id=str(ctx.get("project_id") or "default"),
                tenant=str(ctx.get("tenant") or "default"))
            return {"status": "ok", **out}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_forge_lifecycle_plan(cap: Capability, ctx: dict) -> dict:
        """Run the spec->plan->ship-gate lifecycle for a goal — planning only, no edits."""
        goal = str(ctx.get("goal") or ctx.get("text") or "").strip()
        if not goal:
            return {"status": "error", "note": "no goal provided"}
        try:
            from forge.lifecycle.lifecycle import run_lifecycle
        except Exception as exc:
            return {"status": "unavailable", "note": f"forge lifecycle not importable: {exc}"}
        try:
            out = run_lifecycle(goal, context=ctx.get("context") if isinstance(ctx.get("context"), dict) else None)
            return {"status": "ok", **out}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_research_audit_quality(cap: Capability, ctx: dict) -> dict:
        """Audit a research report for fabricated refs + run the integrity gate (read-only)."""
        report = ctx.get("report")
        if not isinstance(report, dict) or not report:
            return {"status": "error", "note": "report must be a non-empty dict"}
        try:
            from research.quality.report_builder import finalize
        except Exception as exc:
            return {"status": "unavailable", "note": f"research quality not importable: {exc}"}
        try:
            out = finalize(report)
            quality = out.get("quality", {})
            return {"status": "ok",
                    "quality": quality,
                    "publishable": bool(quality.get("publishable", quality.get("gate", {}).get("passed", False)))}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_skills_run(cap: Capability, ctx: dict) -> dict:
        """Run the goal through the ONE shared skill chain.

        Coherence: the companion no longer has its own skill-execution path — it
        delegates to ``SkillCatalog.dispatch_for_goal`` (the same catalog the
        AgentController Executor uses). That tries a tool-composing executable
        skill first, then the library LLM-prompt path. Two entry shapes (by-goal
        here, by-name in the Executor), one chain.
        """
        goal = str(ctx.get("goal") or ctx.get("text") or "").strip()
        if not goal:
            return {"status": "error", "note": "no goal provided"}
        try:
            from skills.catalog import get_skill_catalog
            return get_skill_catalog().dispatch_for_goal(goal, ctx)
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"skill catalog unavailable: {exc}"}

    @staticmethod
    def _exec_content_produce(cap: Capability, ctx: dict) -> dict:
        """Produce multi-platform content via the Content Factory (staged for approval)."""
        topic = str(ctx.get("topic") or ctx.get("goal") or ctx.get("text") or "").strip()
        if not topic:
            return {"status": "error", "note": "no topic provided"}
        try:
            from content.content_factory import get_content_factory
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"content factory not importable: {exc}"}
        try:
            brief = {"topic": topic,
                     "platforms": ctx.get("platforms"),
                     "content_type": ctx.get("content_type"),
                     "variants": ctx.get("variants")}
            out = get_content_factory().produce(brief)
            return {"status": "ok" if out.get("ok") else "error", **out}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_finance_draft(cap: Capability, ctx: dict) -> dict:
        """Advisory finance draft (business model / pricing / forecast / pitch). No execution."""
        request = str(ctx.get("request") or ctx.get("goal") or ctx.get("text") or "").strip()
        if not request:
            return {"status": "error", "note": "no finance request provided"}
        try:
            from finance.financeops import get_financeops
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"financeops not importable: {exc}"}
        try:
            out = get_financeops().draft(
                request,
                context=str(ctx.get("context") or ""),
                inputs=ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else None,
            )
            return {"status": "ok" if out.get("ok") else out.get("status", "error"), **out}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_company_validate(cap: Capability, ctx: dict) -> dict:
        """Validate a business idea before building (CompanyOS validate-before-build)."""
        idea = str(ctx.get("idea") or ctx.get("goal") or ctx.get("text") or "").strip()
        if not idea:
            return {"status": "error", "note": "no idea provided"}
        try:
            from companyos.validation_engine import get_validation_engine
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"companyos not importable: {exc}"}
        try:
            brief = {"idea": idea}
            ans = ctx.get("answers")
            if isinstance(ans, dict):
                brief.update(ans)
            out = get_validation_engine().validate(brief)
            return {"status": "ok", **out}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _exec_company_refine(cap: Capability, ctx: dict) -> dict:
        """Turn a weak idea into a buildable one (validate + pivot suggestions)."""
        idea = str(ctx.get("idea") or ctx.get("goal") or ctx.get("text") or "").strip()
        if not idea:
            return {"status": "error", "note": "no idea provided"}
        try:
            from companyos import get_companyos
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"companyos not importable: {exc}"}
        try:
            out = get_companyos().refine_idea(idea)
            return {"status": "ok" if out.get("ok") else "error", **out}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)}

    # ── Approval request shaping ─────────────────────────────────────────────────

    @staticmethod
    def _approval_request(cap: Capability, decision: dict, resolved: dict) -> dict:
        """Human-readable approval card for a gated capability."""
        focus = resolved.get("focus") or {}
        affects = focus.get("label") if isinstance(focus, dict) else None
        rollback = None
        if cap.id == "forge.apply_patch":
            rollback = "git checkout -- <files> / git stash to discard the patch"
        elif "delete" in cap.id or "remove" in cap.id:
            rollback = "restore from the most recent state/ backup"
        return {
            "cap": cap.id,
            "action": cap.name,
            "summary": cap.description,
            "why": decision.get("reason", "risk level requires approval"),
            "risk": decision.get("risk_level", cap.risk_level),
            "affects": affects or cap.subsystem,
            "side_effects": list(cap.side_effects),
            "rollback": rollback,
            "needs_explicit_confirm": bool(decision.get("needs_explicit_confirm")),
            "approval": decision.get("approval"),
        }


# ── Module helpers ───────────────────────────────────────────────────────────


def _state_dir() -> Path:
    """Canonical runtime state directory (falls back to repo ./state)."""
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:
        return _repo_root() / "state"


def _repo_root() -> Path:
    """Repository root (this file lives at runtime/companion/execution_broker.py)."""
    return Path(__file__).resolve().parents[2]


def _which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def _safe_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


def _recent_briefing_data(ctx: dict) -> dict[str, Any] | None:
    tool_results = (ctx or {}).get("recent_tool_results") or []
    if not isinstance(tool_results, list):
        return None
    for item in reversed(tool_results):
        if not isinstance(item, dict) or item.get("cap") != "briefing.morning":
            continue
        data = item.get("data")
        if isinstance(data, dict):
            return data
    return None


def _focus_index_from_text(text: str) -> int:
    low = str(text or "").lower()
    ordinals = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
        "fifth": 4,
        "5th": 4,
    }
    for token, idx in ordinals.items():
        if token in low:
            return idx
    m = re.search(r"\b([1-5])\b", low)
    return int(m.group(1)) - 1 if m else 0


def _briefing_has_risk(briefing: dict, title: str) -> bool:
    risk_text = " ".join(str(item).lower() for item in briefing.get("risks", []) or [])
    title_text = str(title or "").lower()
    return any(word in risk_text or word in title_text for word in (
        "overdue", "failed", "pending guardrail", "approval", "risk",
    ))


def _append_task(data: Any, task: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, dict) and "tasks" in data:
        out = dict(data)
        tasks = out.get("tasks")
    elif isinstance(data, dict):
        out = {"tasks": dict(data)}
        tasks = out["tasks"]
    elif isinstance(data, list):
        out = {"tasks": list(data)}
        tasks = out["tasks"]
    else:
        out = {"tasks": {}}
        tasks = out["tasks"]

    if isinstance(tasks, dict):
        tasks[task["id"]] = task
    elif isinstance(tasks, list):
        tasks.append(task)
    else:
        out["tasks"] = {task["id"]: task}
    return out


def _parse_pytest_summary(output: str) -> tuple[Optional[int], Optional[int]]:
    """Extract (passed, failed) counts from a pytest summary line. Best-effort."""
    passed = failed = None
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    if failed is None and ("error" in output.lower() and "passed" not in output.lower()):
        failed = 0  # collection error → unknown count, treat as not-all-green
    return passed, failed


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[ExecutionBroker] = None
_instance_lock = threading.Lock()


def get_execution_broker() -> ExecutionBroker:
    """Return the process-wide ``ExecutionBroker`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ExecutionBroker()
    return _instance
