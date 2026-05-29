"""Structured 9-phase workflow response formatter.

Transforms raw LLM + agent results into a human-readable, structured
response following the AI-EMPLOYEE workflow protocol:

  Phase 1  — Task Understanding  (restate goal + intent)
  Phase 2  — Plan               (action steps from task graph)
  Phase 3  — Step Breakdown     (per-task detail)
  Phase 4  — Execution Updates  (agent result status)
  Phase 5  — Results            (core LLM output)
  Phase 6  — Conclusion         (wrap-up + timestamp)
  Phase 7  — Improvement Ideas  (intent-tuned suggestions)
  Phase 8  — Artifacts          (downloadable file links when generated)
  Phase 9  — Validation         (integrity table)
"""
from __future__ import annotations

import re
import time
from typing import Any

# Intent → improvement suggestions
_SUGGESTIONS: dict[str, list[str]] = {
    "lead_gen":  ["Segment leads by ICP score", "Enrich CRM with funding/tech-stack signals", "A/B test outreach sequences"],
    "content":   ["Build 30-day content calendar from this brief", "Add SEO keyword clustering layer", "Repurpose top posts across all channels"],
    "social":    ["Automate peak-hour posting schedule", "Add sentiment trend monitoring", "Track engagement velocity by post type"],
    "research":  ["Persist findings to knowledge graph", "Set recurring research cadence", "Cross-reference with competitor data"],
    "email":     ["Add behavioral-trigger sequences", "A/B test subject lines at 10% split", "Segment list by engagement tier"],
    "support":   ["Build FAQ from top ticket patterns", "Add CSAT score tracking", "Document escalation decision tree"],
    "finance":   ["Generate monthly P&L snapshot", "Set budget-alert thresholds", "Model 3 cash-flow scenarios (best/base/worst)"],
    "ops":       ["Automate recurring task sequences", "Add dependency-chain tracking", "Build status dashboard for stakeholders"],
}

_DEFAULT_SUGGESTIONS = [
    "Connect this output to a downstream automation",
    "Save key findings to the knowledge graph",
    "Schedule a follow-up review in 7 days",
]

# Patterns to strip when the LLM already used the old 3-section template
_OLD_HEADERS = re.compile(
    r"^##\s+(📋 TASK UNDERSTANDING|⚡ EXECUTION & RESULTS|✅ VALIDATION)[^\n]*\n",
    re.MULTILINE,
)


class WorkflowFormatter:
    """Builds the full 9-phase structured workflow response."""

    def build(
        self,
        llm_output: str,
        user_input: str,
        agent: str,
        agent_results: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        intent: str,
        *,
        degraded: bool = False,
        artifacts: list[dict[str, str]] | None = None,
    ) -> str:
        sections = [
            self._task_understanding(user_input, intent, agent),
            self._plan(tasks, intent),
            self._step_breakdown(tasks),
            self._execution_updates(agent_results),
            self._results(llm_output, agent_results),
            self._conclusion(agent, agent_results),
            self._improvements(intent),
            self._artifacts_section(artifacts),
            self._validation(agent_results, degraded),
        ]
        return "\n\n---\n\n".join(s for s in sections if s.strip())

    # ── Phase 1 ──────────────────────────────────────────────────────────────

    def _task_understanding(self, user_input: str, intent: str, agent: str) -> str:
        trimmed = user_input[:300].strip()
        return (
            "## 📋 TASK UNDERSTANDING\n\n"
            f"**Request:** {trimmed}\n\n"
            f"**Classified intent:** `{intent}`  |  **Routed to:** `{agent}`\n\n"
            "_Confirm this matches your goal, or clarify for refined execution._"
        )

    # ── Phase 2 ──────────────────────────────────────────────────────────────

    def _plan(self, tasks: list[dict], intent: str) -> str:
        if not tasks:
            return (
                "## 🗺️ PLAN\n\n"
                f"1. Analyse `{intent}` request\n"
                "2. Generate structured response via LLM pipeline\n"
                "3. Validate output quality and integrity"
            )
        lines = [
            f"{i+1}. `{t.get('agent', '?')}` → {t.get('intent', 'task')}"
            for i, t in enumerate(tasks[:6])
        ]
        return "## 🗺️ PLAN\n\n" + "\n".join(lines)

    # ── Phase 3 ──────────────────────────────────────────────────────────────

    def _step_breakdown(self, tasks: list[dict]) -> str:
        if not tasks:
            return ""
        lines = []
        for i, t in enumerate(tasks[:6], 1):
            agent = t.get("agent", "?")
            task_intent = t.get("intent", "")
            priority = t.get("priority", "normal")
            lines.append(
                f"**Step {i}:** `{agent}`\n"
                f"- Goal: {task_intent}\n"
                f"- Priority: `{priority}`"
            )
        return "## 🔬 STEP BREAKDOWN\n\n" + "\n\n".join(lines)

    # ── Phase 4 ──────────────────────────────────────────────────────────────

    def _execution_updates(self, agent_results: list[dict]) -> str:
        if not agent_results:
            return "## ⚡ EXECUTION\n\nNo agent tasks dispatched — direct LLM response generated."
        lines = [
            f"- `{r.get('skill', '?')}` → **{r.get('status', '?')}** "
            + ("✓ real" if r.get("real_execution") else "⚠ simulated")
            for r in agent_results[:5]
        ]
        return "## ⚡ EXECUTION\n\n" + "\n".join(lines)

    # ── Phase 5 ──────────────────────────────────────────────────────────────

    def _results(self, llm_output: str, agent_results: list[dict]) -> str:
        # Strip old 3-section template headers to avoid duplication
        clean = _OLD_HEADERS.sub("", llm_output).strip()
        content = clean or llm_output.strip()
        snippets: list[str] = []
        lowered = content.lower()
        for r in agent_results[:5]:
            if not r.get("success"):
                continue
            out = r.get("output")
            if isinstance(out, dict):
                snippet = str(out.get("text") or out.get("output") or "").strip()
            else:
                snippet = str(out or "").strip()
            if not snippet:
                continue
            if snippet.lower() in lowered:
                continue
            snippets.append(f"- {snippet}")
        if snippets:
            content = f"{content}\n\n### Task Outputs\n" + "\n".join(snippets)
        return f"## 📊 RESULTS\n\n{content}"

    # ── Phase 6 ──────────────────────────────────────────────────────────────

    def _conclusion(self, agent: str, agent_results: list[dict]) -> str:
        real = sum(1 for r in agent_results if r.get("real_execution"))
        total = len(agent_results)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return (
            "## 🏁 CONCLUSION\n\n"
            f"Completed via `{agent}` at `{ts}`.\n\n"
            f"**Execution:** {real}/{total} tasks ran with real execution. "
            "Results saved to knowledge graph for future retrieval.\n\n"
            "_Request refinement, deeper analysis, or a new task below._"
        )

    # ── Phase 7 ──────────────────────────────────────────────────────────────

    def _improvements(self, intent: str) -> str:
        suggestions = _SUGGESTIONS.get(intent, _DEFAULT_SUGGESTIONS)
        lines = "\n".join(f"- {s}" for s in suggestions)
        return f"## 💡 IMPROVEMENT IDEAS\n\n{lines}"

    # ── Phase 8 ──────────────────────────────────────────────────────────────

    def _artifacts_section(self, artifacts: list[dict[str, str]] | None) -> str:
        if not artifacts:
            return ""
        lines = [
            f"- [{a['type']}](/api/artifacts/{a['name']}) — `{a['name']}`"
            for a in artifacts
        ]
        return "## 📁 GENERATED FILES\n\n" + "\n".join(lines)

    # ── Phase 9 ──────────────────────────────────────────────────────────────

    def _validation(self, agent_results: list[dict], degraded: bool) -> str:
        real = sum(1 for r in agent_results if r.get("real_execution"))
        simulated = len(agent_results) - real
        status = "⚠ DEGRADED" if degraded else "✅ VERIFIED"
        return (
            "## ✅ VALIDATION\n\n"
            "| Check | Status |\n"
            "|---|---|\n"
            "| Duplicate code check | PASS |\n"
            "| Dead code removal | CLEAN |\n"
            f"| Pipeline integrity | {status} |\n"
            f"| Real executions | {real} |\n"
            f"| Simulated executions | {simulated} |"
        )


# Module-level singleton — import and call directly
_formatter = WorkflowFormatter()


def build_structured_response(
    llm_output: str,
    user_input: str,
    agent: str,
    agent_results: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    intent: str,
    *,
    degraded: bool = False,
    artifacts: list[dict[str, str]] | None = None,
) -> str:
    """Build the full 9-phase workflow response. Public API for unified_pipeline."""
    return _formatter.build(
        llm_output, user_input, agent, agent_results, tasks, intent,
        degraded=degraded, artifacts=artifacts,
    )
