"""Ascend Forge V5 project-intake runtime.

This module prepares project-level artifacts only.  It does not apply code,
publish externally, spend money, or bypass existing Forge approvals.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from core.compute_router import ComputeWorkload, decision_to_dict, get_compute_router
from core.forge_reasoning_orchestrator import get_forge_reasoning_orchestrator
from core.forge_sandbox_manager import get_forge_sandbox_manager

logger = logging.getLogger(__name__)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sentences(text: str) -> list[str]:
    normalized = (text or "")[:8000].replace("\n", ".").replace(";", ".")
    return [part.strip(" .\t") for part in normalized.split(".") if part.strip()]


# repo root = .../AI-EMPLOYEE (this file lives at runtime/core/forge_v5_runtime.py)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_HOME_ROOT = Path(os.environ.get("AI_HOME") or Path.home() / ".ai-employee").resolve()
_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv", "state", ".cache", "coverage"}
_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".sh", ".css"}
_STOPWORDS = {
    "the", "and", "for", "with", "use", "using", "that", "this", "from", "into", "make", "build",
    "improve", "should", "would", "could", "have", "will", "your", "their", "system", "needs",
    "want", "must", "never", "without", "require", "approval", "able", "more", "than", "then",
    "also", "real", "fake", "code", "work", "when", "what", "which", "where", "they", "them",
}


def _keywords(text: str, limit: int = 8) -> list[str]:
    seen: list[str] = []
    for tok in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{3,}", (text or "").lower()):
        if tok in _STOPWORDS or tok in seen:
            continue
        seen.append(tok)
        if len(seen) >= limit:
            break
    return seen


def _scan_codebase(keywords: list[str], root: Path | None = None, max_hits: int = 15) -> list[dict[str, Any]]:
    """Return repo files whose path matches brief keywords, as structured findings.

    Bounded, read-only. Each finding carries path, the matched keywords, a short
    human finding, a relevance reason, a confidence score, and source_type.
    """
    base = root or _REPO_ROOT
    if not keywords or not base.exists():
        return []
    hits: list[dict[str, Any]] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".") and "archive" not in d.lower()]
        for fn in filenames:
            if Path(fn).suffix not in _CODE_EXT:
                continue
            scanned += 1
            if scanned > 20000:  # hard ceiling to keep this fast
                return hits
            rel = str(Path(dirpath, fn).relative_to(base))
            low = rel.lower()
            matched = [k for k in keywords if k in low]
            if matched:
                # Confidence scales with how many distinct keywords the path hits.
                confidence = round(min(0.95, 0.45 + 0.15 * len(matched)), 2)
                hits.append({
                    "path": rel,
                    "matched_keywords": matched,
                    "finding": f"Existing {Path(fn).suffix.lstrip('.') or 'file'} at {rel} relates to: {', '.join(matched)}.",
                    "relevance": f"Path matches {len(matched)} brief keyword(s): {', '.join(matched)}.",
                    "confidence": confidence,
                    "source_type": "codebase",
                })
                if len(hits) >= max_hits:
                    # Sort the gathered hits by confidence before returning.
                    return sorted(hits, key=lambda h: h["confidence"], reverse=True)
    return sorted(hits, key=lambda h: h["confidence"], reverse=True)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_scan_root(project: dict[str, Any]) -> Path:
    target = str(project.get("root_path") or project.get("path") or "").strip()
    if target and "\x00" not in target:
        trusted_roots = {
            str(_REPO_ROOT): _REPO_ROOT,
            str(_AI_HOME_ROOT): _AI_HOME_ROOT,
        }
        if target in trusted_roots:
            return trusted_roots[target]
    return _REPO_ROOT


class ForgeV5Runtime:
    def __init__(self) -> None:
        self.reasoning = get_forge_reasoning_orchestrator()
        self.compute = get_compute_router()
        self.sandbox = get_forge_sandbox_manager()

    async def start_project(self, raw_input: str, project_id: str, project: dict[str, Any] | None = None) -> dict[str, Any]:
        brief = await self.start_project_brief(raw_input, project_id, project)
        research = await self.run_research(brief)
        goals_payload = await self.plan_goals(brief, research)
        report = await self.generate_report(project_id, brief=brief, research_pack=research, goals=goals_payload.get("goals", []))
        return {"brief": brief, "research_pack": research, "goals": goals_payload.get("goals", []), "reasoning": goals_payload.get("reasoning"), "report": report}

    async def start_project_brief(self, raw_input: str, project_id: str, project: dict[str, Any] | None = None) -> dict[str, Any]:
        text = (raw_input or "").strip()
        if not text:
            raise ValueError("raw_input required")
        parts = _sentences(text)
        title = (parts[0] if parts else text)[:90]
        constraints = [p for p in parts if any(w in p.lower() for w in ("must", "never", "without", "require", "approval", "no "))]
        return {
            "project_id": project_id,
            "raw_input": text,
            "title": title,
            "summary": text[:500],
            "user_intent": text,
            "desired_outcome": parts[-1] if parts else text,
            "scope": parts[:6],
            "constraints": constraints,
            "unknowns": [] if len(text.split()) >= 8 else ["Goal may need more detail before execution."],
            "success_definition": "Prepared goals can be executed through existing Forge runs and pass configured verification.",
            "required_research": ["codebase", "memory", "runtime"],
            "autonomy_level": "prepare_only",
            "project": project or {},
            "created_at": _now(),
        }

    async def run_research(self, brief: dict[str, Any]) -> dict[str, Any]:
        goal = brief.get("raw_input") or brief.get("summary") or ""
        context_eval: dict[str, Any]
        try:
            from core.context_evaluator import get_context_evaluator

            context_eval = get_context_evaluator().evaluate(goal)
        except Exception:
            logger.exception("Forge V5 context evaluation failed")
            context_eval = {"score": 0.0, "sufficient": False, "gaps": [], "error": "context_evaluation_failed"}

        # ── Real codebase inspection ─────────────────────────────────────────
        project = brief.get("project") or {}
        root = _safe_scan_root(project)
        # Derive keywords from the whole brief, not just raw input.
        kw_source = " ".join(str(x) for x in [
            brief.get("title"), brief.get("summary"), brief.get("desired_outcome"),
            brief.get("user_intent"), " ".join(brief.get("required_research") or []),
            " ".join(brief.get("constraints") or []), goal,
        ] if x)
        keywords = _keywords(kw_source)
        file_hits = _scan_codebase(keywords, root=root)
        codebase_findings = {
            "root": str(root),
            "keywords": keywords,
            "relevant_files": file_hits,
            "files_matched": len(file_hits),
        }
        if not file_hits:
            codebase_findings["note"] = "No files matched the brief keywords by path; goal may touch new areas."

        # ── Real memory retrieval ────────────────────────────────────────────
        memory_hits: list[dict[str, Any]] = []
        memory_error: str | None = None
        try:
            from memory.memory_router import get_memory_router

            for m in get_memory_router().retrieve(goal, top_k=10):
                memory_hits.append({
                    "key": m.get("key"),
                    "text": (m.get("text") or "")[:240],
                    "score": m.get("_score"),
                })
        except Exception:
            logger.exception("Forge V5 memory retrieval failed")
            memory_error = "memory_retrieval_failed"

        # ── Online research — honest availability only ───────────────────────
        search_keys = [k for k in ("BRAVE_API_KEY", "BING_API_KEY", "SERPAPI_API_KEY", "TAVILY_API_KEY") if os.getenv(k)]
        if search_keys:
            online_findings = {"available": True, "providers": search_keys, "results": [], "source_type": "online",
                               "note": "Provider configured; run web_research_tool to populate."}
        else:
            online_findings = {"available": False, "reason": "no search provider configured", "source_type": "online"}

        # ── Runtime research — real checks, honest unavailable otherwise ─────
        runtime_findings: dict[str, Any] = {"source_type": "runtime"}
        try:
            runtime_findings["compute_backends"] = self.compute.health()
        except Exception:
            logger.exception("Forge V5 compute health failed")
            runtime_findings["compute_backends"] = {"available": False, "reason": "unavailable"}
        try:
            runtime_findings["model_routing"] = self.reasoning.select_model("research", quality="balanced", privacy="local_ok")
        except Exception:
            logger.exception("Forge V5 model routing failed")
            runtime_findings["model_routing"] = {"available": False, "reason": "unavailable"}
        runtime_findings["approval_boundary"] = "Node Forge remains the execution and persistence boundary"

        # ── End-state recommended goals (not loose todos) ────────────────────
        focus = ", ".join(keywords[:3]) or "the target area"
        recommended_goals: list[str] = []
        if file_hits:
            top = file_hits[0]["path"]
            recommended_goals.append(
                f"The change for '{focus}' is implemented by extending existing modules (e.g. {top}) and verified green, with no duplicate parallel implementation."
            )
        else:
            recommended_goals.append(
                f"A new, well-scoped module for '{focus}' is added with tests, since no existing file covers it."
            )
        if not bool(context_eval.get("sufficient")):
            recommended_goals.append(
                "Context gaps identified in research are closed (via memory or targeted reading) before any code is applied."
            )
        recommended_goals.append(
            "Project runtime persists the research pack and the change is observable through the existing V5 UI and report."
        )

        return {
            "research_pack_id": f"rp-{uuid.uuid4().hex[:12]}",
            "project_id": brief["project_id"],
            "codebase_findings": codebase_findings,
            "memory_findings": {
                "context_score": context_eval.get("score", 0.0),
                "sufficient": bool(context_eval.get("sufficient")),
                "gaps": context_eval.get("gaps", []),
                "retrieved": memory_hits,
                "retrieved_count": len(memory_hits),
                "retrieval_error": memory_error,
            },
            "online_findings": online_findings,
            "runtime_findings": runtime_findings,
            "implementation_implications": [
                "Prepare goals first and require explicit execution.",
                "Use existing Forge runs as the execution unit.",
                f"{len(file_hits)} existing file(s) appear relevant — reuse before adding new modules.",
            ],
            "risks": [
                "Uncommitted worktree changes may conflict with generated edits.",
                "Missing verification commands make some quality dimensions unavailable.",
            ],
            "open_questions": context_eval.get("gaps", []),
            "recommended_goals": recommended_goals,
            "created_at": _now(),
        }

    async def plan_goals(self, brief: dict[str, Any], research_pack: dict[str, Any] | None = None) -> dict[str, Any]:
        text = brief.get("raw_input") or ""
        try:
            from forge.lifecycle.spec_engine import build_spec
            from forge.lifecycle.planning_engine import build_plan

            spec = build_spec(text, {"assumptions": brief.get("constraints") or []})
            plan = build_plan(spec)
            slices = plan.get("slices") or []
        except Exception:
            spec = {"status": "ready", "spec": {"acceptance_criteria": []}, "open_questions": []}
            plan = {"status": "planned", "slices": []}
            slices = []

        reasoning = await self.reasoning.reason(phase="goal_planning", goal=text, context={"brief": brief, "research_pack": research_pack or {}})
        qce_paths = reasoning.get("paths_considered") or []
        goals: list[dict[str, Any]] = []
        if slices:
            for idx, item in enumerate(slices, start=1):
                goals.append(self._goal_from_slice(brief, item, idx, qce_paths))
        else:
            goals = self._fallback_goals(brief, qce_paths)

        return {
            "project_id": brief["project_id"],
            "spec": spec,
            "plan": plan,
            "reasoning": reasoning,
            "goals": goals,
            "created_at": _now(),
        }

    async def execute_goal(self, goal: dict[str, Any], brief: dict[str, Any] | None = None, research_pack: dict[str, Any] | None = None) -> dict[str, Any]:
        # Codebase goals default to local_only — context never leaves the machine
        # unless a caller explicitly opts in via the goal's privacy_level.
        privacy_level = goal.get("privacy_level") or "local_only"
        workload = ComputeWorkload(
            task_type="forge_goal",
            heavy=goal.get("risk_level") == "high",
            privacy_level=privacy_level,
            external_allowed=bool(goal.get("external_allowed")),
            remote_allowed=bool(goal.get("remote_allowed")),
        )
        decision = self.compute.select(workload)
        compute = decision_to_dict(decision)
        reasoning = await self.reasoning.reason(phase="goal_execution_prepare", goal=goal.get("description") or goal.get("title") or "", context={"brief": brief or {}, "research_pack": research_pack or {}})
        return {
            "goal": goal,
            "reasoning": reasoning,
            "compute": compute,
            "privacy": {
                "privacy_level": privacy_level,
                "external_allowed": workload.external_allowed,
                "remote_allowed": workload.remote_allowed,
                "external_api_used": decision.backend == "external_api",
                "remote_compute_used": decision.backend == "remote_compute",
                "fallback_used": decision.backend == "local_cpu" and (workload.external_allowed or workload.remote_allowed),
            },
            "status": "prepared_for_existing_forge_run",
            "created_at": _now(),
        }

    def run_quality_gate(self, goal: dict[str, Any], run_result: dict[str, Any] | None = None, verification: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.sandbox.build_quality_gate(goal_id=goal.get("goal_id") or goal.get("id") or "", run_result=run_result, verification=verification)

    def write_memory(self, goal: dict[str, Any], quality_gate: dict[str, Any], reasoning: dict[str, Any] | None = None, compute: dict[str, Any] | None = None) -> dict[str, Any]:
        goal_id = goal.get("goal_id") or goal.get("id") or uuid.uuid4().hex[:8]
        reasoning = reasoning or {}
        compute = compute or {}
        qg_status = quality_gate.get("status", "unknown")
        result_quality = {"passed": "high", "partially_verified": "medium", "failed": "low", "blocked": "low"}.get(qg_status, "unknown")
        title = f"Forge V5: {goal.get('title') or goal_id}"
        lesson = {
            "type": "goal_lesson",
            "title": title,
            "summary": f"Goal '{goal.get('title') or goal_id}' finished with quality '{qg_status}'.",
            "content": {
                "goal": goal.get("title"),
                "description": goal.get("description"),
                "desired_end_state": goal.get("desired_end_state"),
                "quality_gate": quality_gate.get("summary") or quality_gate,
            },
            "source_project_id": goal.get("project_id"),
            "source_goal_id": goal_id,
            "source_artifacts": goal.get("evidence_requirements") or [],
            "tags": ["forge_v5", goal.get("risk_level") or "low", qg_status],
            "entities": reasoning.get("agents") or [],
            "problems_addressed": [goal.get("title")] if goal.get("title") else [],
            "solution_patterns": reasoning.get("chosen_path") or {},
            "failure_patterns": quality_gate.get("failures") or ([] if qg_status not in ("failed", "blocked") else [qg_status]),
            "reuse_when": goal.get("desired_end_state") or "Similar goal in the same area.",
            "do_not_use_when": "Goal failed or was blocked." if result_quality == "low" else "",
            "confidence": reasoning.get("confidence", 0.5),
            "reasoning_mode_used": reasoning.get("selected_mode"),
            "model_used": reasoning.get("model_used"),
            "compute_backend_used": compute.get("backend"),
            "sandbox_used": quality_gate.get("sandbox_used"),
            "validation_dimensions_checked": quality_gate.get("summary"),
            "result_quality": result_quality,
            "safety_notes": quality_gate.get("safety") or "",
            "efficiency_notes": quality_gate.get("efficiency") or "",
        }
        try:
            import json as _json
            from memory.memory_router import get_memory_router

            stored = get_memory_router().store(
                key=f"forge_v5_goal_{goal_id}",
                text=_json.dumps(lesson)[:4000],
                memory_type="semantic",
                source="forge_v5",
                importance=0.8,
                extra=lesson,
            )
            return {"ok": bool(stored.get("vector_stored") or stored.get("cache_key")), "lesson": lesson, **stored}
        except Exception as exc:
            logger.warning("Forge V5 write_memory failed: %s", type(exc).__name__, exc_info=True)
            return {"ok": False, "error": "forge_v5_memory_store_failed", "memory_stored": False, "lesson": lesson}

    async def generate_report(
        self,
        project_id: str,
        *,
        brief: dict[str, Any] | None = None,
        research_pack: dict[str, Any] | None = None,
        goals: list[dict[str, Any]] | None = None,
        reasoning: dict[str, Any] | None = None,
        quality_gates: list[dict[str, Any]] | None = None,
        memory_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        goals = goals or []
        quality_gates = quality_gates or []
        memory_results = memory_results or []

        completed = [g for g in goals if g.get("status") == "completed"]
        failed = [g for g in goals if g.get("status") == "failed"]
        blocked = [g for g in goals if g.get("status") in ("blocked", "waiting_approval")]

        # Aggregate honest, deduplicated execution metadata from whatever ran.
        models_used: list[str] = []
        modes_used: list[str] = []
        backends_used: list[str] = []

        def _add(lst: list[str], val: Any) -> None:
            if val and val not in lst:
                lst.append(val)

        _add(modes_used, (reasoning or {}).get("selected_mode"))
        _add(models_used, (reasoning or {}).get("model_used"))
        for g in goals:
            gr = g.get("reasoning") or {}
            _add(modes_used, gr.get("selected_mode"))
            _add(models_used, gr.get("model_used"))
        external_api_used = False
        remote_compute_used = False
        for qg in quality_gates:
            _add(backends_used, qg.get("compute_backend"))
            if qg.get("compute_backend") == "external_api":
                external_api_used = True
            if qg.get("compute_backend") == "remote_compute":
                remote_compute_used = True
        # If nothing executed yet, record the planning-time compute path honestly.
        if not backends_used:
            _add(backends_used, decision_to_dict(self.compute.select(ComputeWorkload(task_type="planning")))["backend"])

        memory_lessons = [
            {"key": m.get("cache_key") or m.get("key"), "stored": bool(m.get("ok", m.get("memory_stored", m.get("vector_stored", False)))),
             "title": (m.get("lesson") or {}).get("title")}
            for m in memory_results
        ]

        if failed and not completed:
            status = "failed"
        elif blocked and not completed:
            status = "blocked"
        elif completed and (failed or blocked or len(completed) < len(goals)):
            status = "partial"
        elif completed and len(completed) == len(goals) and goals:
            status = "completed"
        else:
            status = "prepared" if not goals else "planned"  # honest: never fake "done"

        # Summaries — say "unavailable" rather than empty fake success.
        quality_gate_summary = [{"goal_id": qg.get("goal_id"), "status": qg.get("status"), "summary": qg.get("summary")} for qg in quality_gates] or "unavailable — no goal executed yet"
        validation_summary = {qg.get("goal_id"): qg.get("summary") for qg in quality_gates} or "unavailable"
        sandbox_summary = [qg.get("sandbox_used") for qg in quality_gates if qg.get("sandbox_used")] or "unavailable"

        return {
            "project_id": project_id,
            "brief_summary": (brief or {}).get("summary", ""),
            "goals_completed": completed,
            "goals_failed": failed,
            "goals_blocked": blocked,
            "goals_prepared": len(goals),
            "evidence_summary": {
                "research_pack_id": (research_pack or {}).get("research_pack_id"),
                "context_sufficient": ((research_pack or {}).get("memory_findings") or {}).get("sufficient"),
                "relevant_files": ((research_pack or {}).get("codebase_findings") or {}).get("files_matched"),
                "quality_gates_recorded": len(quality_gates),
            },
            "quality_gate_summary": quality_gate_summary,
            "validation_summary": validation_summary,
            "sandbox_summary": sandbox_summary,
            "artifacts": ["brief", "research_pack", "goals", "reasoning"],
            "memory_lessons": memory_lessons,
            "reasoning_modes_used": modes_used,
            "models_used": models_used,
            "compute_backends_used": backends_used,
            "external_api_used": external_api_used,
            "remote_compute_used": remote_compute_used,
            "privacy_level_summary": "local_only (default for codebase goals)",
            "status": status,
            "created_at": _now(),
        }

    def _goal_from_slice(self, brief: dict[str, Any], item: dict[str, Any], idx: int, qce_paths: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "goal_id": f"v5g-{uuid.uuid4().hex[:10]}",
            "project_id": brief["project_id"],
            "title": item.get("title") or f"Goal {idx}",
            "description": item.get("title") or brief.get("summary", ""),
            "desired_end_state": "Acceptance criteria for this slice are satisfied and existing verification is green or explicitly unavailable.",
            "priority": max(1, 100 - idx),
            "status": "proposed",
            "dependencies": item.get("depends_on") or [],
            "evidence_requirements": item.get("acceptance_ids") or [],
            "risk_level": "medium" if idx == 1 else "low",
            "approval_required": True,
            "max_iterations": 3,
            "qce_paths_considered": qce_paths,
            "created_at": _now(),
        }

    def _fallback_goals(self, brief: dict[str, Any], qce_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        titles = [
            "Map current implementation and constraints",
            "Implement the smallest safe vertical slice",
            "Validate, report, and store lessons",
        ]
        return [
            {
                "goal_id": f"v5g-{uuid.uuid4().hex[:10]}",
                "project_id": brief["project_id"],
                "title": title,
                "description": f"{title}: {brief.get('summary', '')}",
                "desired_end_state": "Prepared for explicit execution through an existing Forge run.",
                "priority": 100 - idx,
                "status": "proposed",
                "dependencies": [],
                "evidence_requirements": ["brief", "research_pack", "verification_result"],
                "risk_level": "low",
                "approval_required": True,
                "max_iterations": 3,
                "qce_paths_considered": qce_paths,
                "created_at": _now(),
            }
            for idx, title in enumerate(titles)
        ]


def get_forge_v5_runtime() -> ForgeV5Runtime:
    return ForgeV5Runtime()
